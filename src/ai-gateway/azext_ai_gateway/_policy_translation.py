# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from pathlib import Path
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
POLICY_INDEX_PATH = Path(__file__).with_name("apim_policy_index.json")


def _load_policy_index():
    with POLICY_INDEX_PATH.open(encoding="utf-8") as index_file:
        index = json.load(index_file)
    policies = index["policies"]
    catalog = {policy["statement"]: policy for policy in policies}
    if len(catalog) != len(policies):
        raise ValueError("APIM policy index contains duplicate statements.")
    return index, catalog


APIM_POLICY_INDEX, POLICY_TRANSLATION_CATALOG = _load_policy_index()
RECOGNIZED_POLICY_ELEMENTS = {
    statement
    for statement, capability in POLICY_TRANSLATION_CATALOG.items()
    if capability["action"] == "import"
}
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


def _consume_forward_request(_element, _section):
    return [], []


POLICY_CONFIGURATION_HANDLERS = {
    "forward-request": _consume_forward_request,
    "set-backend-service": _translate_backend_service,
}


_UNKNOWN_CRITICALITY_PATTERNS = (
    (
        "authentication",
        re.compile(
            r"(?:auth|authoriz|credential|identity|jwt|token|certificate|"
            r"header-check|check-header|ip-filter)"
        ),
    ),
    (
        "backend",
        re.compile(r"(?:backend|upstream|endpoint|service-discovery)"),
    ),
    (
        "routing",
        re.compile(
            r"(?:route|routing|forward|proxy|redirect|rewrite|dispatch|"
            r"set-method|return-response|mock-response)"
        ),
    ),
)


def classify_policy_statement(statement):
    normalized = str(statement or "").strip().casefold()
    capability = POLICY_TRANSLATION_CATALOG.get(normalized)
    if capability is not None:
        return {**deepcopy(capability), "indexed": True}
    criticality = "unknown"
    for candidate, pattern in _UNKNOWN_CRITICALITY_PATTERNS:
        if pattern.search(normalized):
            criticality = candidate
            break
    action = "block" if criticality != "unknown" else "warn"
    return {
        "statement": normalized,
        "docsUrl": APIM_POLICY_INDEX["source"]["url"],
        "validScopes": [],
        "validSections": [],
        "applicableAssets": ["model", "mcpServer"],
        "applicableSubtypes": ["*"],
        "destinationCapability": {"mode": "none", "policyTypes": []},
        "supportLevel": "unsupported",
        "action": action,
        "criticality": criticality,
        "omittedBehavior": "The statement is not present in the reviewed index.",
        "guidance": (
            "Do not import until its authentication, routing, or backend "
            "semantics are mapped."
            if action == "block"
            else "Review the source statement and recreate required behavior."
        ),
        "handler": None,
        "indexed": False,
    }


def _nested_policy_names(element):
    executable_policies = set(POLICY_TRANSLATORS).union(
        POLICY_CONFIGURATION_HANDLERS
    )
    return sorted(
        {
            _local_name(nested.tag)
            for nested in element.iter()
            if _local_name(nested.tag) in executable_policies
        }
    )


def policy_handler(capability):
    handler = capability.get("handler")
    if not handler:
        return None
    registry = (
        POLICY_TRANSLATORS
        if handler["kind"] == "translator"
        else POLICY_CONFIGURATION_HANDLERS
    )
    registered = registry.get(capability["statement"])
    if registered is None or registered.__name__ != handler["name"]:
        return None
    return registered


def _policy_translation_records(root):
    records = []
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
                records.extend(
                    {
                        "statement": name,
                        "section": section_name,
                        "policy": policy,
                    }
                    for policy in policies
                )
                warnings.extend(policy_warnings)
                continue
            nested_policy_names = _nested_policy_names(element)
            if nested_policy_names:
                warnings.append(
                    "Conditionally or structurally nested policies cannot be "
                    "translated without changing when they apply: "
                    + ", ".join(nested_policy_names)
                )
                continue
            capability = classify_policy_statement(name)
            if name not in STRUCTURAL_POLICY_ELEMENTS:
                warnings.append(
                    f"{name} is classified action={capability['action']} "
                    f"({capability['criticality']}); "
                    f"{capability['omittedBehavior']}"
                )
                continue
    return records, warnings


def _policy_translations(root):
    records, warnings = _policy_translation_records(root)
    return [record["policy"] for record in records], warnings


def _statement_occurrences(root):
    occurrences = set()
    for section in root:
        section_name = _local_name(section.tag)
        for element in section.iter():
            if element is section:
                continue
            name = _local_name(element.tag)
            capability = POLICY_TRANSLATION_CATALOG.get(name)
            if name not in STRUCTURAL_POLICY_ELEMENTS or (
                capability is not None and capability.get("handler")
            ):
                occurrences.add((name, section_name))
    return [
        {"statement": statement, "section": section}
        for statement, section in sorted(occurrences)
    ]


def _policy_origin(policy):
    return (
        f"{policy.get('scopeType', 'api')} policy "
        f"'{policy.get('scope', '')}'"
    )


def _applies_to_asset(capability, asset_type, asset_subtype):
    applicable_assets = {
        str(value).casefold()
        for value in capability.get("applicableAssets", [])
    }
    if str(asset_type or "").casefold() not in applicable_assets:
        return False
    applicable_subtypes = {
        str(value).casefold()
        for value in capability.get("applicableSubtypes", [])
    }
    return (
        "*" in applicable_subtypes
        or str(asset_subtype or "").casefold() in applicable_subtypes
    )


def translate_effective_policies(
    effective_policy_summaries,
    asset_type,
    asset_subtype=None,
):
    """Assess and translate effective APIM policies for a destination asset."""
    destination_policies = []
    reduced_warnings = []
    unsupported_warnings = []
    critical_blockers = []

    for policy in effective_policy_summaries or []:
        origin = _policy_origin(policy)
        scope_type = str(policy.get("scopeType") or "api").casefold()
        occurrences = policy.get("statementOccurrences")
        if occurrences is None:
            occurrences = [
                {
                    "statement": assessment["statement"],
                    "section": None,
                }
                for assessment in policy.get("statementAssessments", [])
            ]

        occurrence_decisions = {}
        for occurrence in occurrences:
            statement = occurrence.get("statement")
            section = occurrence.get("section")
            capability = classify_policy_statement(statement)
            valid_scope = scope_type in {
                str(value).casefold()
                for value in capability.get("validScopes", [])
            }
            valid_section = section is None or section.casefold() in {
                str(value).casefold()
                for value in capability.get("validSections", [])
            }
            applicable = _applies_to_asset(
                capability,
                asset_type,
                asset_subtype,
            )
            can_import = (
                capability["action"] == "import"
                and applicable
                and valid_scope
                and valid_section
                and scope_type not in {"product", "operation"}
            )
            occurrence_decisions[(statement, section)] = can_import

            location = (
                f"{origin}, {section} section"
                if section
                else origin
            )
            if capability["indexed"] and not applicable:
                unsupported_warnings.append(
                    f"{location}: {statement} does not apply to destination "
                    f"asset type '{asset_type}'"
                    + (
                        f" subtype '{asset_subtype}'"
                        if asset_subtype is not None
                        else ""
                    )
                    + " and will not be imported."
                )
                continue
            if capability["indexed"] and not valid_scope:
                unsupported_warnings.append(
                    f"{location}: {statement} is not valid at APIM scope "
                    f"'{scope_type}' and will not be imported."
                )
                continue
            if capability["indexed"] and not valid_section:
                unsupported_warnings.append(
                    f"{location}: {statement} is not valid in the APIM "
                    f"'{section}' section and will not be imported."
                )
                continue
            if capability["action"] == "block":
                critical_blockers.append(
                    f"{location}: {statement} is unsupported and blocks import; "
                    f"{capability['omittedBehavior']} {capability['guidance']}"
                )
                continue
            if capability["action"] == "warn":
                unsupported_warnings.append(
                    f"{location}: {statement} is unsupported; "
                    f"{capability['omittedBehavior']} {capability['guidance']}"
                )
                continue
            if capability["supportLevel"] == "reduced":
                reduced_warnings.append(
                    f"{location}: {statement} has a reduced destination "
                    f"mapping; {capability['omittedBehavior']} "
                    f"{capability['guidance']}"
                )

        if scope_type in {"service", "workspace"} and any(
            occurrence_decisions.values()
        ):
            reduced_warnings.append(
                f"{origin}: translated policies must be replicated onto each "
                "destination asset; shared counters and inheritance boundaries "
                "may change."
            )
        if scope_type in {"product", "operation"} and policy.get("present"):
            reduced_warnings.append(
                f"{origin}: this scope cannot be preserved as a destination "
                "inline policy and translated policies will not be imported."
            )

        for warning in policy.get("translationWarnings", []):
            reduced_warnings.append(f"{origin}: {warning}")

        if scope_type in {"product", "operation"}:
            continue
        translated_records = policy.get("translatedPolicyRecords")
        if translated_records is None:
            if any(occurrence_decisions.values()):
                destination_policies.extend(
                    deepcopy(policy.get("translatedPolicies", []))
                )
            continue
        for record in translated_records:
            if occurrence_decisions.get(
                (record.get("statement"), record.get("section")),
                False,
            ):
                destination_policies.append(deepcopy(record["policy"]))

    return {
        "destinationPolicies": destination_policies,
        "reducedMappingWarnings": reduced_warnings,
        "unsupportedNoncriticalWarnings": unsupported_warnings,
        "unsupportedCriticalBlockers": critical_blockers,
    }


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
        "statementAssessments": [],
        "statementOccurrences": [],
        "translatedPolicyRecords": [],
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
    occurrences = _statement_occurrences(root)
    assessment_sections = {}
    for occurrence in occurrences:
        assessment_sections.setdefault(occurrence["statement"], []).append(
            occurrence["section"]
        )
    assessments = []
    for name, sections in sorted(assessment_sections.items()):
        assessment = classify_policy_statement(name)
        assessment["observedSections"] = sorted(set(sections))
        assessments.append(assessment)
    unsupported = sorted(
        assessment["statement"]
        for assessment in assessments
        if assessment["action"] != "import"
    )
    translated_records, translation_warnings = _policy_translation_records(root)
    translated = [record["policy"] for record in translated_records]
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
        "statementAssessments": assessments,
        "statementOccurrences": occurrences,
        "translatedPolicyRecords": translated_records,
    }


def list_policy_translation_support(support_level=None):
    capabilities = [
        deepcopy(capability)
        for capability in POLICY_TRANSLATION_CATALOG.values()
        if support_level is None
        or capability["supportLevel"] == support_level
    ]
    return sorted(capabilities, key=lambda item: item["statement"])


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
            "SourcePolicy": capability["statement"],
            "Support": capability["supportLevel"],
            "Action": capability["action"],
            "Criticality": capability["criticality"],
            "Mode": capability["destinationCapability"]["mode"],
            "Destination": ",".join(
                capability["destinationCapability"]["policyTypes"]
            ),
            "Sections": ",".join(capability["validSections"]),
            "Scopes": ",".join(capability["validScopes"]),
            "Guidance": capability["guidance"],
        }
        for capability in capabilities
    ]
