# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import re
from copy import deepcopy
from xml.etree import ElementTree

from azure.cli.core.azclierror import ResourceNotFoundError

STRUCTURAL_POLICY_ELEMENTS = {
    "backend",
    "base",
    "blocklists",
    "categories",
    "category",
    "forward-request",
    "id",
    "inbound",
    "on-error",
    "outbound",
    "policies",
    "value",
}
TOKEN_LIMIT_ELEMENTS = {
    "azure-openai-token-limit",
    "llm-token-limit",
}
TOKEN_LIMIT_NON_DESTINATION_ATTRIBUTES = {
    "estimate-prompt-tokens",
    "remaining-quota-tokens-header-name",
    "remaining-quota-tokens-variable-name",
    "remaining-tokens-header-name",
    "remaining-tokens-variable-name",
    "retry-after-header-name",
    "retry-after-variable-name",
    "tokens-consumed-header-name",
    "tokens-consumed-variable-name",
}
CONTENT_SAFETY_FIELDS = {
    "hate": "hateSeverity",
    "selfharm": "selfHarmSeverity",
    "sexual": "sexualSeverity",
    "violence": "violenceSeverity",
}
SCOPES = {
    "imported": ["service", "workspace", "api"],
    "inventoryOnly": ["product", "operation"],
}


def _capability(
    source_policy,
    support_level,
    translation_mode,
    destination_policy_types,
    supported_source_fields,
    unsupported_source_fields,
    supported_sections,
    notes,
):
    return {
        "sourcePolicy": source_policy,
        "supportLevel": support_level,
        "translationMode": translation_mode,
        "destinationPolicyTypes": destination_policy_types,
        "supportedSourceFields": supported_source_fields,
        "unsupportedSourceFields": unsupported_source_fields,
        "supportedSections": supported_sections,
        "scopes": deepcopy(SCOPES),
        "notes": notes,
    }


POLICY_TRANSLATION_CATALOG = {
    "llm-token-limit": _capability(
        "llm-token-limit",
        "partial",
        "inlinePolicy",
        ["tokenLimit"],
        [
            "counter-key",
            "tokens-per-minute",
            "token-quota",
            "token-quota-period:Hourly",
            "token-quota-period:Daily",
        ],
        sorted(TOKEN_LIMIT_NON_DESTINATION_ATTRIBUTES)
        + [
            "token-quota-period:Monthly",
            "token-quota-period:Weekly",
            "token-quota-period:Yearly",
        ],
        ["inbound"],
        (
            "Literal rates and hourly/daily quotas are translated. Counter keys "
            "must match a supported IP address or identity expression."
        ),
    ),
    "azure-openai-token-limit": _capability(
        "azure-openai-token-limit",
        "partial",
        "inlinePolicy",
        ["tokenLimit"],
        [
            "counter-key",
            "tokens-per-minute",
            "token-quota",
            "token-quota-period:Hourly",
            "token-quota-period:Daily",
        ],
        sorted(TOKEN_LIMIT_NON_DESTINATION_ATTRIBUTES)
        + [
            "token-quota-period:Monthly",
            "token-quota-period:Weekly",
            "token-quota-period:Yearly",
        ],
        ["inbound"],
        "Uses the same translation as llm-token-limit.",
    ),
    "llm-content-safety": _capability(
        "llm-content-safety",
        "partial",
        "inlinePolicy",
        ["contentSafety"],
        [
            "categories.category:Hate",
            "categories.category:SelfHarm",
            "categories.category:Sexual",
            "categories.category:Violence",
            "categories.output-type",
        ],
        [
            "backend-id",
            "blocklists",
            "enforce-on-completions",
            "shield-prompt",
            "window-overlap-size",
            "window-size",
        ],
        ["inbound", "outbound"],
        (
            "Literal category thresholds are normalized to Low, Medium, or High. "
            "Request/response placement must be reviewed."
        ),
    ),
    "set-backend-service": _capability(
        "set-backend-service",
        "consumed",
        "configuration",
        [],
        ["backend-id"],
        ["base-url"],
        ["inbound", "backend"],
        "backend-id is consumed while resolving the source APIM backend.",
    ),
    "authentication-managed-identity": _capability(
        "authentication-managed-identity",
        "unsupported",
        "none",
        [],
        [],
        ["client-id", "ignore-error", "output-token-variable-name", "resource"],
        ["inbound"],
        (
            "Destination credentials require an explicit endpoint or provider "
            "mapping that is not implemented."
        ),
    ),
    "rewrite-uri": _capability(
        "rewrite-uri",
        "unsupported",
        "none",
        [],
        [],
        ["copy-unmatched-params", "template"],
        ["inbound"],
        "URI rewriting has no destination inline-policy equivalent.",
    ),
    "set-query-parameter": _capability(
        "set-query-parameter",
        "unsupported",
        "none",
        [],
        [],
        ["exists-action", "name", "value"],
        ["inbound", "outbound"],
        "Query mutation has no destination inline-policy equivalent.",
    ),
}
RECOGNIZED_POLICY_ELEMENTS = set(POLICY_TRANSLATION_CATALOG)
POLICY_TRANSLATORS = {}


def _register_translator(*policy_names):
    def decorator(translator):
        for policy_name in policy_names:
            if policy_name in POLICY_TRANSLATORS:
                raise ValueError(
                    f"Translator already registered for '{policy_name}'."
                )
            POLICY_TRANSLATORS[policy_name] = translator
        return translator

    return decorator


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def _positive_integer(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _translate_counter_key(value):
    normalized = re.sub(r"\s+", "", str(value or "").casefold())
    if normalized in {
        "@(context.request.ipaddress)",
        "ipaddress",
    }:
        return "IPAddress", None
    if normalized in {
        "@(context.subscription.id)",
        "@(context.user.email)",
        "@(context.user.id)",
        "@(context.user?.email)",
        "api-key",
        "identity",
    }:
        warning = None
        if normalized == "@(context.subscription.id)":
            warning = (
                "APIM subscription counters become AI Gateway Identity "
                "counters; verify that the destination identity scope matches."
            )
        return "Identity", warning
    return None, (
        "The counter-key expression cannot be represented by the destination "
        "IPAddress or Identity counter."
    )


def _token_limit_policy(count, period, counter_key):
    return {
        "type": "tokenLimit",
        "period": period,
        "count": count,
        "counterKey": counter_key,
    }


@_register_translator(*TOKEN_LIMIT_ELEMENTS)
def _translate_token_limit(element, section):
    source_name = _local_name(element.tag)
    warnings = []
    translated = []
    if section != "inbound":
        return [], [
            f"{source_name} in the {section} section cannot be represented; "
            "token limits are translated only from inbound policies."
        ]
    counter_key, counter_warning = _translate_counter_key(
        element.attrib.get("counter-key")
    )
    if counter_warning:
        warnings.append(counter_warning)

    rate_value = element.attrib.get("tokens-per-minute")
    if rate_value is not None:
        rate = _positive_integer(rate_value)
        if rate is None:
            warnings.append(
                f"{source_name} tokens-per-minute is not a positive integer "
                "literal and cannot be translated."
            )
        elif counter_key:
            translated.append(
                _token_limit_policy(rate, "minute", counter_key)
            )
        else:
            warnings.append(
                f"{source_name} token rate '{rate}' will not be translated "
                "because its counter-key is unsupported."
            )

    quota_value = element.attrib.get("token-quota")
    quota_period = element.attrib.get("token-quota-period")
    if quota_value is not None or quota_period is not None:
        quota = _positive_integer(quota_value)
        period = {
            "hourly": "hour",
            "daily": "day",
        }.get(str(quota_period or "").casefold())
        if quota is None:
            warnings.append(
                f"{source_name} token-quota is not a positive integer literal "
                "and cannot be translated."
            )
        if period is None:
            warnings.append(
                f"{source_name} quota period '{quota_period}' is not supported; "
                "AI Gateway supports minute, hour, and day."
            )
        if quota is not None and period is not None and counter_key:
            translated.append(
                _token_limit_policy(quota, period, counter_key)
            )
        elif quota is not None and period is not None:
            warnings.append(
                f"{source_name} token quota '{quota}' will not be translated "
                "because its counter-key is unsupported."
            )

    if rate_value is None and quota_value is None:
        warnings.append(
            f"{source_name} has no token rate or quota to translate."
        )
    if rate_value is not None and quota_value is not None and translated:
        warnings.append(
            f"{source_name} combines a rate and quota; it is split into "
            "separate destination tokenLimit policies."
        )
    unsupported_attributes = sorted(
        TOKEN_LIMIT_NON_DESTINATION_ATTRIBUTES.intersection(element.attrib)
    )
    if unsupported_attributes:
        warnings.append(
            f"{source_name} attributes are not supported and will be omitted: "
            + ", ".join(unsupported_attributes)
        )
    return translated, warnings


def _severity_from_threshold(value):
    threshold = _positive_integer(value)
    if threshold is None and str(value) == "0":
        threshold = 0
    if threshold is None or threshold > 7:
        return None
    if threshold <= 2:
        return "Low"
    if threshold <= 4:
        return "Medium"
    return "High"


@_register_translator("llm-content-safety")
def _translate_content_safety(element, section):
    translated = {"type": "contentSafety"}
    warnings = []
    categories = next(
        (
            child
            for child in element
            if _local_name(child.tag) == "categories"
        ),
        None,
    )
    if categories is not None:
        output_type = categories.attrib.get("output-type")
        if output_type and output_type not in {
            "FourSeverityLevels",
            "EightSeverityLevels",
        }:
            warnings.append(
                "llm-content-safety has an unrecognized categories "
                f"output-type '{output_type}'."
            )
        for category in categories:
            if _local_name(category.tag) != "category":
                continue
            source_category = str(category.attrib.get("name") or "")
            field = CONTENT_SAFETY_FIELDS.get(
                source_category.replace("-", "").casefold()
            )
            severity = _severity_from_threshold(
                category.attrib.get("threshold")
            )
            if field is None:
                warnings.append(
                    "llm-content-safety category "
                    f"'{source_category}' is not supported."
                )
            elif severity is None:
                warnings.append(
                    f"llm-content-safety {source_category} threshold is not a "
                    "literal integer from 0 through 7 and cannot be translated."
                )
            else:
                translated[field] = severity

    blocklist_ids = [
        child
        for blocklists in element
        if _local_name(blocklists.tag) == "blocklists"
        for child in blocklists
        if _local_name(child.tag) == "id"
    ]
    if blocklist_ids:
        warnings.append(
            "llm-content-safety blocklists are not supported and will be omitted."
        )
    unsupported_attributes = sorted(
        set(element.attrib).intersection(
            {
                "backend-id",
                "enforce-on-completions",
                "shield-prompt",
                "window-overlap-size",
                "window-size",
            }
        )
    )
    if unsupported_attributes:
        warnings.append(
            "llm-content-safety attributes are not supported and will be "
            "omitted: "
            + ", ".join(unsupported_attributes)
        )
    if section == "outbound":
        warnings.append(
            "An outbound llm-content-safety policy cannot preserve its "
            "request/response placement in the destination inline policy."
        )
    else:
        warnings.append(
            "An inbound llm-content-safety policy is converted to an asset-level "
            "inline policy; verify request and response enforcement behavior."
        )
    if len(translated) == 1:
        warnings.append(
            "llm-content-safety has no literal supported category thresholds "
            "to translate."
        )
        return [], warnings
    return [translated], warnings


@_register_translator("set-backend-service")
def _translate_backend_service(element, _section):
    if element.attrib.get("base-url"):
        return [], [
            "set-backend-service base-url is not supported; only backend-id is "
            "used for source backend resolution."
        ]
    if not element.attrib.get("backend-id"):
        return [], [
            "set-backend-service has no backend-id to use for source backend "
            "resolution."
        ]
    return [], []


def _unsupported_configuration_translator(element, _section):
    name = _local_name(element.tag)
    return [], [
        f"{name} has no implemented destination mapping and will be omitted."
    ]


for _policy_name in (
    "authentication-managed-identity",
    "rewrite-uri",
    "set-query-parameter",
):
    _register_translator(_policy_name)(_unsupported_configuration_translator)


def _nested_policy_names(element):
    return sorted(
        {
            _local_name(nested.tag)
            for nested in element.iter()
            if _local_name(nested.tag) in POLICY_TRANSLATORS
        }
    )


def _policy_translations(root):
    translated = []
    warnings = []
    for section in root:
        section_name = _local_name(section.tag)
        if section_name not in {"inbound", "outbound"}:
            nested_policy_names = _nested_policy_names(section)
            if nested_policy_names:
                warnings.append(
                    f"Policies in the {section_name} section cannot be "
                    "translated: "
                    + ", ".join(nested_policy_names)
                )
            continue
        for element in section:
            name = _local_name(element.tag)
            translator = POLICY_TRANSLATORS.get(name)
            if translator:
                policies, policy_warnings = translator(element, section_name)
                translated.extend(policies)
                warnings.extend(policy_warnings)
                continue
            nested_policy_names = _nested_policy_names(element)
            if nested_policy_names:
                warnings.append(
                    "Conditionally or structurally nested policies cannot be "
                    "translated without changing when they apply: "
                    + ", ".join(nested_policy_names)
                )
    return translated, warnings


def summarize_policy(policy_xml, scope, scope_type="api"):
    empty = {
        "scope": scope,
        "scopeType": scope_type,
        "present": False,
        "inheritsParent": True,
        "statements": [],
        "recognizedStatements": [],
        "unsupportedStatements": [],
        "backendIds": [],
        "parseError": None,
        "translatedPolicies": [],
        "translationWarnings": [],
    }
    if not policy_xml:
        return empty
    try:
        root = ElementTree.fromstring(policy_xml)
    except ElementTree.ParseError as error:
        return {
            **empty,
            "present": True,
            "inheritsParent": False,
            "parseError": str(error),
        }

    statements = []
    backend_ids = []
    inherits_parent = False
    for element in root.iter():
        name = _local_name(element.tag)
        if name == "base":
            inherits_parent = True
        if name == "set-backend-service":
            backend_id = element.attrib.get("backend-id")
            if backend_id:
                backend_ids.append(backend_id)
        if name not in STRUCTURAL_POLICY_ELEMENTS:
            statements.append(name)

    statements = sorted(set(statements))
    recognized = sorted(
        name for name in statements if name in RECOGNIZED_POLICY_ELEMENTS
    )
    unsupported = sorted(
        name for name in statements if name not in RECOGNIZED_POLICY_ELEMENTS
    )
    translated, translation_warnings = _policy_translations(root)
    return {
        **empty,
        "present": True,
        "inheritsParent": inherits_parent,
        "statements": statements,
        "recognizedStatements": recognized,
        "unsupportedStatements": unsupported,
        "backendIds": sorted(set(backend_ids)),
        "translatedPolicies": translated,
        "translationWarnings": translation_warnings,
    }


def list_policy_translation_support(support_level=None):
    capabilities = [
        deepcopy(capability)
        for capability in POLICY_TRANSLATION_CATALOG.values()
        if support_level is None
        or capability["supportLevel"] == support_level
    ]
    return sorted(capabilities, key=lambda item: item["sourcePolicy"])


def show_policy_translation_support(name):
    capability = POLICY_TRANSLATION_CATALOG.get(name)
    if capability is None:
        raise ResourceNotFoundError(
            f"APIM policy translation capability '{name}' was not found."
        )
    return deepcopy(capability)


def format_policy_translation_table(result):
    capabilities = result if isinstance(result, list) else [result]
    return [
        {
            "SourcePolicy": capability["sourcePolicy"],
            "Support": capability["supportLevel"],
            "Mode": capability["translationMode"],
            "Destination": ",".join(capability["destinationPolicyTypes"]),
            "Sections": ",".join(capability["supportedSections"]),
            "ImportedScopes": ",".join(
                capability["scopes"]["imported"]
            ),
            "Notes": capability["notes"],
        }
        for capability in capabilities
    ]
