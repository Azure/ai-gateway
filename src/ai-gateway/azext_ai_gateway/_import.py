# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)
from xml.etree import ElementTree

from azure.cli.core.azclierror import (
    AzCLIError,
    HTTPError,
    InvalidArgumentValueError,
)
from azure.cli.core._output import set_output_format
from azure.cli.core.commands.client_factory import get_subscription_id
from knack.log import get_logger
from knack.output import _TableOutput
from requests import RequestException

from azext_ai_gateway._gateway import (
    _SUBNET_RESOURCE_ID,
    _gateway_path,
    _networking_properties,
    _request,
    _response_json,
)
from azext_ai_gateway._model_provider import (
    _discover_custom_models,
    _sync_plan,
)
from azext_ai_gateway._import_execution import (
    build_import_actions,
    execute_import_actions,
    sanitize_assets_for_output,
)
from azext_ai_gateway._policy_translation import (
    summarize_policy,
    translate_effective_policies,
)

DEFAULT_WORKSPACE = "default"
APIM_ID_PATTERN = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/"
    r"resourceGroups/(?P<resource_group>[^/]+)/providers/"
    r"Microsoft\.ApiManagement/service/(?P<name>[^/]+)/?$",
    re.IGNORECASE,
)
SUPPORTED_SOURCE_SKUS = {"basicv2", "standardv2", "premiumv2"}
logger = get_logger(__name__)
MODEL_HOST_SUFFIXES = (
    ".openai.azure.com",
    ".models.ai.azure.com",
    ".models.inference.ai.azure.com",
    "api.anthropic.com",
    "api.openai.com",
    "generativelanguage.googleapis.com",
)
SENSITIVE_PROPERTY_NAMES = {
    "accesskey",
    "apikey",
    "certificate",
    "clientcertificate",
    "clientsecret",
    "connectionstring",
    "instrumentationkey",
    "key",
    "password",
    "secret",
    "subscriptionkey",
    "token",
}
MAPPING_FIELDS = {
    "network": {"subnetResourceId"},
    "models": {
        "apiFormat",
        "deploymentResourceId",
        "modelName",
        "modelVersion",
        "name",
        "providerName",
    },
    "mcpServers": {"name", "namespace", "transport"},
}
ASSOCIATED_SUPPORT_STATES = {
    "importable",
    "reduced",
    "deferred",
    "unsupported-critical",
    "unsupported-noncritical",
}


def _parse_apim_id(resource_id):
    match = APIM_ID_PATTERN.fullmatch((resource_id or "").strip())
    if not match:
        raise InvalidArgumentValueError(
            "--source-apim-id must be a complete Azure API Management service "
            "resource ID."
        )
    return match.groupdict()


def _read_mapping(mapping_file):
    if mapping_file is None:
        return {}
    try:
        if hasattr(mapping_file, "read"):
            mapping = json.load(mapping_file)
        else:
            mapping = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as error:
        raise InvalidArgumentValueError(
            f"Unable to read --mapping-file as JSON: {error}"
        ) from error
    if not isinstance(mapping, dict):
        raise InvalidArgumentValueError(
            "--mapping-file must contain a JSON object."
        )
    invalid_sections = set(mapping) - set(MAPPING_FIELDS)
    if invalid_sections:
        raise InvalidArgumentValueError(
            "--mapping-file contains unsupported sections: "
            + ", ".join(sorted(invalid_sections))
        )
    network_mapping = mapping.get("network")
    if network_mapping is not None:
        if not isinstance(network_mapping, dict):
            raise InvalidArgumentValueError(
                "Mapping section 'network' must be a JSON object."
            )
        invalid_fields = set(network_mapping) - MAPPING_FIELDS["network"]
        if invalid_fields:
            raise InvalidArgumentValueError(
                "Network mapping contains unsupported fields: "
                + ", ".join(sorted(invalid_fields))
            )
        for field, value in network_mapping.items():
            if not isinstance(value, str) or not value.strip():
                raise InvalidArgumentValueError(
                    f"Network mapping field '{field}' must be a non-empty string."
                )
            if (
                field == "subnetResourceId"
                and not _SUBNET_RESOURCE_ID.fullmatch(value.strip())
            ):
                raise InvalidArgumentValueError(
                    "Network mapping field 'subnetResourceId' must be a full "
                    "Microsoft.Network virtual network subnet resource ID."
                )
            network_mapping[field] = value.strip()
    for section in ("models", "mcpServers"):
        entries = mapping.get(section)
        if entries is None:
            continue
        if not isinstance(entries, dict):
            raise InvalidArgumentValueError(
                f"Mapping section '{section}' must be a JSON object."
            )
        for source_name, entry in entries.items():
            if not isinstance(entry, dict):
                raise InvalidArgumentValueError(
                    f"Mapping for '{source_name}' must be a JSON object."
                )
            invalid_fields = set(entry) - MAPPING_FIELDS[section]
            if invalid_fields:
                raise InvalidArgumentValueError(
                    f"Mapping for '{source_name}' contains unsupported fields: "
                    + ", ".join(sorted(invalid_fields))
                )
            for field, value in entry.items():
                if not isinstance(value, str) or not value.strip():
                    raise InvalidArgumentValueError(
                        f"Mapping field '{field}' for '{source_name}' must be "
                        "a non-empty string."
                    )
    return mapping


def _list_all(cmd, url):
    resources = []
    include_api_version = True
    while url:
        page = _response_json(
            _request(
                cmd,
                "GET",
                url,
                include_api_version=include_api_version,
            )
        )
        resources.extend((page or {}).get("value", []))
        url = (page or {}).get("nextLink")
        include_api_version = False
    return resources


def _http_error(error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return status, str(error)


def _optional_list(
    cmd,
    url,
    errors,
    context,
    domain=None,
    required=True,
):
    try:
        return _list_all(cmd, url)
    except HTTPError as error:
        status, message = _http_error(error)
        if status == 404:
            return []
        errors.append(
            {
                "scope": context,
                "statusCode": status,
                "message": message,
                "configurationDomain": domain,
                "required": required,
            }
        )
        return []


def _optional_policy(cmd, scope_id, errors):
    try:
        response = _request(
            cmd,
            "GET",
            f"{scope_id}/policies/policy?format=rawxml",
        )
    except HTTPError as error:
        status, message = _http_error(error)
        if status == 404:
            return None
        errors.append(
            {
                "scope": f"{scope_id}/policies/policy",
                "statusCode": status,
                "message": message,
                "configurationDomain": "policies",
                "required": True,
            }
        )
        return None
    text = getattr(response, "text", None)
    if isinstance(text, str):
        text = text.removeprefix("\ufeff")
        if text.lstrip().startswith("<"):
            return text
    body = _response_json(response)
    if isinstance(body, dict):
        value = (body.get("properties") or {}).get("value") or body.get("value")
        if isinstance(value, str):
            return value
    return text if isinstance(text, str) else None


def _managed_identity_authentications(policy_xml):
    if not policy_xml:
        return []
    try:
        root = ElementTree.fromstring(policy_xml)
    except ElementTree.ParseError:
        return []
    settings = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != (
            "authentication-managed-identity"
        ):
            continue
        settings.append(
            {
                "resource": _safe_url(element.attrib.get("resource")),
                "clientId": element.attrib.get("client-id"),
                "outputTokenVariableName": element.attrib.get(
                    "output-token-variable-name"
                ),
                "ignoreError": element.attrib.get("ignore-error"),
            }
        )
    return settings


def _policy_summary(policy_xml, scope, scope_type="api"):
    summary = summarize_policy(policy_xml, scope, scope_type)
    summary["managedIdentityAuthentications"] = (
        _managed_identity_authentications(policy_xml)
    )
    return summary


def _credential_summary(credentials):
    credentials = credentials or {}
    authorization = credentials.get("authorization") or {}
    return {
        "hasCredentials": bool(credentials),
        "headerNames": sorted((credentials.get("header") or {}).keys()),
        "queryParameterNames": sorted((credentials.get("query") or {}).keys()),
        "authorizationScheme": authorization.get("scheme"),
        "namedValueReferences": _named_value_references(credentials),
    }


def _named_value_references(value):
    references = set()

    def collect(item):
        if isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)
        elif isinstance(item, str):
            references.update(
                match.strip()
                for match in re.findall(r"\{\{([^{}]+)\}\}", item)
                if match.strip()
            )

    collect(value)
    return sorted(references)


def _safe_url(value):
    if not value:
        return value
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname or ""
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
    except (TypeError, ValueError):
        return "<invalid>"
    redacted_query = urlencode(
        [(name, "<redacted>") for name, _ in parse_qsl(parsed.query)]
    )
    return urlunparse(
        (
            parsed.scheme,
            hostname,
            parsed.path,
            parsed.params,
            redacted_query,
            "<redacted>" if parsed.fragment else "",
        )
    )


def _url_safety(value):
    if not value:
        return False, False
    parsed = urlparse(value)
    return bool(parsed.username or parsed.password), bool(parsed.query)


def _sanitize_properties(value, property_name=None):
    normalized_name = str(property_name or "").casefold()
    if (
        normalized_name in SENSITIVE_PROPERTY_NAMES
        or normalized_name.endswith("token")
        or any(
            marker in normalized_name
            for marker in ("password", "secret", "tokenvalue")
        )
    ):
        return "<redacted>" if value is not None else None
    if normalized_name == "credentials" and isinstance(value, dict):
        return _credential_summary(value)
    if isinstance(value, dict):
        return {
            key: _sanitize_properties(item, key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_properties(item, property_name) for item in value]
    if isinstance(value, str) and (
        value.casefold().startswith(("http://", "https://"))
        or normalized_name in {"endpoint", "uri", "uritemplate", "url"}
    ):
        return _safe_url(value)
    return value


def _backend_summary(backend):
    if not backend:
        return None
    properties = backend.get("properties") or {}
    return {
        "id": backend.get("id"),
        "name": backend.get("name"),
        "url": _safe_url(properties.get("url")),
        "protocol": properties.get("protocol"),
        "resourceId": properties.get("resourceId"),
        "credentials": _credential_summary(properties.get("credentials")),
        "properties": _sanitize_properties(properties),
    }


def _identity_summary(resource):
    identity = resource.get("identity") or {}
    identity_type = identity.get("type")
    user_assigned = identity.get("userAssignedIdentities") or {}
    return {
        "type": identity_type,
        "systemAssigned": (
            {
                "principalId": identity.get("principalId"),
                "tenantId": identity.get("tenantId"),
            }
            if "systemassigned" in str(identity_type or "").casefold()
            else None
        ),
        "userAssigned": [
            {
                "resourceId": resource_id,
                "clientId": properties.get("clientId"),
                "principalId": properties.get("principalId"),
            }
            for resource_id, properties in sorted(user_assigned.items())
        ],
    }


def _diagnostic_summary(diagnostic, scope_type):
    properties = diagnostic.get("properties") or {}
    return {
        "id": diagnostic.get("id"),
        "name": diagnostic.get("name"),
        "scopeType": scope_type,
        "loggerId": properties.get("loggerId"),
        "properties": _sanitize_properties(properties),
    }


def _logger_summary(logger_resource):
    properties = logger_resource.get("properties") or {}
    return {
        "id": logger_resource.get("id"),
        "name": logger_resource.get("name"),
        "loggerType": properties.get("loggerType"),
        "isBuffered": properties.get("isBuffered"),
        "resourceId": properties.get("resourceId"),
        "credentials": _credential_summary(properties.get("credentials")),
        "properties": _sanitize_properties(properties),
    }


def _referenced_loggers(diagnostics, loggers):
    by_reference = {}
    for logger_resource in loggers:
        summary = _logger_summary(logger_resource)
        for reference in (summary.get("id"), summary.get("name")):
            if reference:
                by_reference[str(reference).rstrip("/").casefold()] = summary
    referenced = []
    seen = set()
    for diagnostic in diagnostics:
        logger_id = (diagnostic.get("properties") or {}).get("loggerId")
        if not logger_id:
            continue
        key = str(logger_id).rstrip("/").casefold()
        summary = by_reference.get(key)
        if summary is None:
            summary = {"id": logger_id, "name": None, "unresolved": True}
        identity = str(summary.get("id") or summary.get("name")).casefold()
        if identity not in seen:
            seen.add(identity)
            referenced.append(summary)
    return referenced


def _subscription_summary(subscription, rank):
    properties = subscription.get("properties") or {}
    return {
        "id": subscription.get("id"),
        "name": subscription.get("name"),
        "displayName": properties.get("displayName"),
        "scope": properties.get("scope"),
        "state": properties.get("state"),
        "relationship": "api" if rank == 0 else "product",
    }


def _api_summary(api, workspace_name):
    properties = api.get("properties") or {}
    return {
        "id": api.get("id"),
        "name": api.get("name"),
        "type": api.get("type"),
        "etag": api.get("etag"),
        "displayName": properties.get("displayName"),
        "description": properties.get("description"),
        "workspace": workspace_name,
        "apiType": properties.get("type") or properties.get("apiType"),
        "path": properties.get("path"),
        "serviceUrl": _safe_url(properties.get("serviceUrl")),
        "protocols": properties.get("protocols") or [],
        "subscriptionRequired": bool(properties.get("subscriptionRequired")),
        "properties": _sanitize_properties(properties),
    }


def _operation_summary(operation, policy):
    properties = operation.get("properties") or {}
    return {
        "id": operation.get("id"),
        "name": operation.get("name"),
        "type": operation.get("type"),
        "displayName": properties.get("displayName"),
        "method": properties.get("method"),
        "urlTemplate": properties.get("urlTemplate"),
        "properties": _sanitize_properties(properties),
        "policy": policy,
    }


def _product_summary(product, policy):
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        "type": product.get("type"),
        "properties": _sanitize_properties(product.get("properties") or {}),
        "policy": policy,
    }


def _tool_summary(tool):
    properties = tool.get("properties") or {}
    return {
        "id": tool.get("id"),
        "name": tool.get("name"),
        "type": tool.get("type"),
        "displayName": properties.get("displayName"),
        "description": properties.get("description"),
        "operationId": properties.get("operationId"),
        "properties": _sanitize_properties(properties),
    }


def _discover_scope(
    cmd,
    scope_id,
    workspace_name,
    parent_policy,
    errors,
    scope_policy=None,
    service_diagnostics=None,
    service_loggers=None,
):
    scope_label = (
        f"workspace '{workspace_name}'"
        if workspace_name is not None
        else "service scope"
    )
    logger.warning("Checking backends and APIs in APIM %s...", scope_label)
    backends = _optional_list(
        cmd,
        f"{scope_id}/backends",
        errors,
        f"{scope_id}/backends",
        "backends",
    )
    backend_by_name = {
        str(backend.get("name", "")).casefold(): backend for backend in backends
    }
    if scope_policy is None:
        scope_policy_xml = _optional_policy(cmd, scope_id, errors)
        scope_policy = _policy_summary(
            scope_policy_xml,
            scope_id,
            "workspace" if workspace_name is not None else "service",
        )
    apis = _optional_list(
        cmd,
        f"{scope_id}/apis",
        errors,
        f"{scope_id}/apis",
        "apis",
    )
    scope_loggers = list(service_loggers or [])
    if workspace_name is not None:
        scope_loggers.extend(
            _optional_list(
                cmd,
                f"{scope_id}/loggers",
                errors,
                f"{scope_id}/loggers",
                "loggers",
                required=False,
            )
        )
    discovered = []
    for index, api in enumerate(apis, start=1):
        logger.warning(
            "Checking API '%s' in APIM %s (%d of %d)...",
            api.get("name") or "(unnamed)",
            scope_label,
            index,
            len(apis),
        )
        api_id = api.get("id") or (
            f"{scope_id}/apis/{quote(str(api.get('name') or ''), safe='')}"
        )
        policy_xml = _optional_policy(cmd, api_id, errors)
        policy = _policy_summary(policy_xml, api_id, "api")
        backend_ids = list(policy["backendIds"])
        api_backend_id = (api.get("properties") or {}).get("backendId")
        if api_backend_id:
            backend_ids.append(unquote(str(api_backend_id).rsplit("/", 1)[-1]))
        resolved_backends = [
            backend_by_name[backend_id.casefold()]
            for backend_id in dict.fromkeys(backend_ids)
            if backend_id.casefold() in backend_by_name
        ]
        operations = _optional_list(
            cmd,
            f"{api_id}/operations",
            errors,
            f"{api_id}/operations",
            "operations",
        )
        operation_summaries = []
        operation_policies = []
        for operation in operations:
            operation_id = operation.get("id") or (
                f"{api_id}/operations/"
                f"{quote(str(operation.get('name') or ''), safe='')}"
            )
            operation_policy = _policy_summary(
                _optional_policy(cmd, operation_id, errors),
                operation_id,
                "operation",
            )
            operation_policies.append(operation_policy)
            operation_summaries.append(
                _operation_summary(operation, operation_policy)
            )
        products = _optional_list(
            cmd,
            f"{api_id}/products",
            errors,
            f"{api_id}/products",
            "products",
            required=bool(
                (api.get("properties") or {}).get("subscriptionRequired")
            ),
        )
        product_summaries = []
        product_policies = []
        for product in products:
            product_id = product.get("id")
            if not product_id:
                continue
            product_policy = _policy_summary(
                _optional_policy(cmd, product_id, errors),
                product_id,
                "product",
            )
            product_policies.append(product_policy)
            product_summaries.append(
                _product_summary(product, product_policy)
            )
        tools = []
        if str(
            (api.get("properties") or {}).get("type")
            or (api.get("properties") or {}).get("apiType")
            or ""
        ).casefold() == "mcp":
            tools = [
                _tool_summary(tool)
                for tool in _optional_list(
                    cmd,
                    f"{api_id}/tools",
                    errors,
                    f"{api_id}/tools",
                    "mcpTools",
                )
            ]
        api_diagnostic_resources = _optional_list(
            cmd,
            f"{api_id}/diagnostics",
            errors,
            f"{api_id}/diagnostics",
            "diagnostics",
            required=False,
        )
        all_diagnostic_resources = [
            *(service_diagnostics or []),
            *api_diagnostic_resources,
        ]
        diagnostics = [
            *[
                _diagnostic_summary(diagnostic, "service")
                for diagnostic in service_diagnostics or []
            ],
            *[
                _diagnostic_summary(diagnostic, "api")
                for diagnostic in api_diagnostic_resources
            ],
        ]
        inherited_policies = []
        if not policy["present"] or policy["inheritsParent"]:
            inherited_policies.append(scope_policy)
            if (
                workspace_name is not None
                and (
                    not scope_policy["present"]
                    or scope_policy["inheritsParent"]
                )
            ):
                if parent_policy is not None:
                    inherited_policies.append(parent_policy)
        discovered.append(
            {
                "api": api,
                "source": _api_summary(api, workspace_name),
                "policy": policy,
                "inheritedPolicies": inherited_policies,
                "backends": resolved_backends,
                "operations": operation_summaries,
                "operationPolicies": operation_policies,
                "products": product_summaries,
                "productPolicies": product_policies,
                "tools": tools,
                "diagnostics": diagnostics,
                "loggers": _referenced_loggers(
                    all_diagnostic_resources,
                    scope_loggers,
                ),
                "subscriptions": [],
            }
        )
    return discovered, scope_policy


def _exclude_mcp_backing_apis(assets):
    backing_api_references = {}
    for asset in assets:
        if str(asset["source"].get("apiType") or "").casefold() != "mcp":
            continue
        for tool in asset.get("tools") or []:
            operation_id = tool.get("operationId")
            if (
                not isinstance(operation_id, str)
                or "/apis/" not in operation_id.casefold()
                or "/operations/" not in operation_id.casefold()
            ):
                continue
            backing_api_id = re.sub(
                r"/operations/[^/]+/?$",
                "",
                operation_id,
                flags=re.IGNORECASE,
            ).casefold()
            backing_api_references.setdefault(backing_api_id, set()).add(
                asset["source"]["id"]
            )
    included = []
    suppressed = []
    for asset in assets:
        source_id = asset["source"]["id"]
        required_by = backing_api_references.get(source_id.casefold())
        if required_by:
            suppressed.append(
                {
                    **asset["source"],
                    "dependencyType": "mcpRestBackingApi",
                    "requiredBy": sorted(required_by),
                    "reasonCode": "MCP_REST_BACKING_API",
                    "reason": (
                        "This REST API backs an MCP server and is retained as "
                        "a dependency rather than a standalone import candidate."
                    ),
                }
            )
        else:
            included.append(asset)
    return included, suppressed


def _subscription_scope_rank(subscription, asset):
    properties = subscription.get("properties") or {}
    if str(properties.get("state") or "active").casefold() != "active":
        return None
    scope = str(properties.get("scope") or "").rstrip("/").casefold()
    api_id = asset["source"]["id"].rstrip("/").casefold()
    api_name = str(asset["source"].get("name") or "").casefold()
    if scope in {api_id, f"/apis/{api_name}"}:
        return 0
    product_scopes = {
        str(product.get("id") or "").rstrip("/").casefold()
        for product in asset.get("products") or []
    }
    product_scopes.update(
        f"/products/{str(product.get('name') or '').casefold()}"
        for product in asset.get("products") or []
        if product.get("name")
    )
    return 1 if scope in product_scopes else None


def _attach_mcp_subscription_credentials(
    cmd,
    source_apim_id,
    assets,
    errors,
    subscriptions=None,
):
    protected_assets = [
        asset
        for asset in assets
        if str(asset["source"].get("apiType") or "").casefold() == "mcp"
        and asset.get("tools")
        and asset["source"].get("subscriptionRequired")
    ]
    if not protected_assets:
        return
    if subscriptions is None:
        subscriptions = _optional_list(
            cmd,
            f"{source_apim_id}/subscriptions",
            errors,
            f"{source_apim_id}/subscriptions",
            "subscriptions",
        )
    for asset in protected_assets:
        candidates = sorted(
            (
                (rank, str(subscription.get("name") or ""), subscription)
                for subscription in subscriptions
                if (
                    rank := _subscription_scope_rank(subscription, asset)
                ) is not None
            ),
            key=lambda candidate: (candidate[0], candidate[1].casefold()),
        )
        if not candidates:
            asset["subscriptionCredential"] = {
                "available": False,
                "error": (
                    "No active API or product subscription was found for the "
                    "REST-backed MCP server."
                ),
            }
            continue
        _, _, subscription = candidates[0]
        subscription_id = subscription.get("id") or (
            f"{source_apim_id}/subscriptions/"
            f"{quote(str(subscription.get('name') or ''), safe='')}"
        )
        try:
            secrets = _response_json(
                _request(
                    cmd,
                    "POST",
                    f"{subscription_id}/listSecrets",
                    {},
                )
            ) or {}
        except HTTPError as error:
            asset["subscriptionCredential"] = {
                "available": False,
                "subscriptionId": subscription_id,
                "error": str(error),
            }
            continue
        if not secrets.get("primaryKey"):
            asset["subscriptionCredential"] = {
                "available": False,
                "subscriptionId": subscription_id,
                "error": "The selected APIM subscription has no primary key.",
            }
            continue
        key_names = (
            (asset["api"].get("properties") or {}).get(
                "subscriptionKeyParameterNames"
            )
            or {}
        )
        asset["subscriptionCredential"] = {
            "available": True,
            "subscriptionId": subscription_id,
            "subscriptionName": subscription.get("name"),
            "headerName": key_names.get("header")
            or "Ocp-Apim-Subscription-Key",
            "value": "<redacted>",
            "_value": secrets["primaryKey"],
            "candidateCount": len(candidates),
        }


def _attach_subscription_relationships(assets, subscriptions):
    for asset in assets:
        relationships = []
        for subscription in subscriptions:
            rank = _subscription_scope_rank(subscription, asset)
            if rank is not None:
                relationships.append(
                    _subscription_summary(subscription, rank)
                )
        asset["subscriptions"] = sorted(
            relationships,
            key=lambda relationship: (
                relationship["relationship"],
                str(relationship.get("name") or "").casefold(),
            ),
        )


def _discover_source(cmd, source_apim_id):
    errors = []
    logger.warning("Checking source APIM resource and service policy...")
    source = _response_json(_request(cmd, "GET", source_apim_id))
    source_sku = str((source.get("sku") or {}).get("name", ""))
    if source_sku.casefold() not in SUPPORTED_SOURCE_SKUS:
        raise InvalidArgumentValueError(
            "--source-apim-id must identify an API Management service using "
            "the BasicV2, StandardV2, or PremiumV2 SKU."
        )
    source_policy_xml = _optional_policy(cmd, source_apim_id, errors)
    source_policy = _policy_summary(
        source_policy_xml,
        source_apim_id,
        "service",
    )
    service_loggers = _optional_list(
        cmd,
        f"{source_apim_id}/loggers",
        errors,
        f"{source_apim_id}/loggers",
        "loggers",
        required=False,
    )
    service_diagnostics = _optional_list(
        cmd,
        f"{source_apim_id}/diagnostics",
        errors,
        f"{source_apim_id}/diagnostics",
        "diagnostics",
        required=False,
    )
    root_assets, _ = _discover_scope(
        cmd,
        source_apim_id,
        None,
        source_policy,
        errors,
        scope_policy=source_policy,
        service_diagnostics=service_diagnostics,
        service_loggers=service_loggers,
    )
    assets = list(root_assets)
    logger.warning("Checking APIM workspaces...")
    workspaces = _optional_list(
        cmd,
        f"{source_apim_id}/workspaces",
        errors,
        f"{source_apim_id}/workspaces",
        "workspaces",
        required=False,
    )
    for workspace in workspaces:
        workspace_name = workspace.get("name")
        if not workspace_name:
            continue
        workspace_id = workspace.get("id") or (
            f"{source_apim_id}/workspaces/"
            f"{quote(str(workspace_name), safe='')}"
        )
        workspace_assets, _ = _discover_scope(
            cmd,
            workspace_id,
            workspace_name,
            source_policy,
            errors,
            service_diagnostics=service_diagnostics,
            service_loggers=service_loggers,
        )
        assets.extend(workspace_assets)
    source_api_count = len(assets)
    assets, suppressed_assets = _exclude_mcp_backing_apis(assets)
    subscriptions = _optional_list(
        cmd,
        f"{source_apim_id}/subscriptions",
        errors,
        f"{source_apim_id}/subscriptions",
        "subscriptions",
        required=any(
            asset["source"].get("subscriptionRequired")
            for asset in assets
        ),
    )
    _attach_subscription_relationships(assets, subscriptions)
    _attach_mcp_subscription_credentials(
        cmd,
        source_apim_id,
        assets,
        errors,
        subscriptions,
    )
    properties = source.get("properties") or {}
    return {
        "source": {
            "id": source.get("id") or source_apim_id,
            "name": source.get("name"),
            "location": source.get("location"),
            "sku": source_sku,
            "gatewayUrl": _safe_url(properties.get("gatewayUrl")),
            "networkConfiguration": _network_configuration(source),
            "managedIdentities": _identity_summary(source),
        },
        "assets": assets,
        "sourceApiCount": source_api_count,
        "suppressedAssets": suppressed_assets,
        "errors": errors,
    }


def _provider_path(destination_id):
    return f"{destination_id}/workspaces/{DEFAULT_WORKSPACE}/modelProviders"


def _destination_inventory(cmd, destination_id):
    destination = _response_json(_request(cmd, "GET", destination_id))
    if (
        str((destination.get("sku") or {}).get("name", "")).casefold()
        != "aigateway"
    ):
        raise InvalidArgumentValueError(
            "The destination resource must use the AIGateway SKU."
        )
    providers = _list_all(cmd, _provider_path(destination_id))
    models = _list_all(cmd, f"{destination_id}/workspaces/default/models")
    tools = _list_all(cmd, f"{destination_id}/workspaces/default/toolServers")
    model_keys = set()
    unscoped_model_names = set()
    for model in models:
        model_name = str(model.get("name", "")).casefold()
        match = re.search(
            r"/modelProviders/([^/]+)/models/([^/]+)$",
            str(model.get("id") or ""),
            re.IGNORECASE,
        )
        if match:
            model_keys.add(
                (
                    unquote(match.group(1)).casefold(),
                    unquote(match.group(2)).casefold(),
                )
            )
        else:
            unscoped_model_names.add(model_name)
    return {
        "resource": {
            "id": destination.get("id") or destination_id,
            "name": destination.get("name"),
            "location": destination.get("location"),
            "networkConfiguration": _network_configuration(destination),
        },
        "providers": providers,
        "modelKeys": model_keys,
        "unscopedModelNames": unscoped_model_names,
        "toolNames": {
            str(tool.get("name", "")).casefold() for tool in tools
        },
    }


def _network_configuration(resource):
    properties = resource.get("properties") or {}
    virtual_network = properties.get("virtualNetworkConfiguration") or {}
    return {
        "publicNetworkAccess": properties.get("publicNetworkAccess") or "Enabled",
        "virtualNetworkType": properties.get("virtualNetworkType") or "None",
        "subnetResourceId": virtual_network.get("subnetResourceId"),
        "privateEndpointConnectionCount": len(
            properties.get("privateEndpointConnections") or []
        ),
    }


def _assess_network(source, destination, mapping):
    source_configuration = source.get("networkConfiguration") or {}
    current_configuration = destination.get("networkConfiguration") or {}
    public_network_access = (
        source_configuration.get("publicNetworkAccess") or "Enabled"
    )
    virtual_network_type = (
        source_configuration.get("virtualNetworkType") or "None"
    )
    subnet_resource_id = (
        mapping.get("subnetResourceId")
        or source_configuration.get("subnetResourceId")
    )
    if virtual_network_type == "None":
        subnet_resource_id = None
    reasons = []
    warnings = []
    target_configuration = {
        "publicNetworkAccess": public_network_access,
        "virtualNetworkType": virtual_network_type,
        "subnetResourceId": subnet_resource_id,
    }
    if public_network_access not in {"Enabled", "Disabled"}:
        reasons.append(
            "Public network access value "
            f"'{public_network_access}' cannot be imported."
        )
    if virtual_network_type == "None" and mapping.get("subnetResourceId"):
        reasons.append(
            "network.subnetResourceId can only be mapped when the source uses "
            "External virtual network integration."
        )
    if virtual_network_type not in {"None", "External"}:
        reasons.append(
            f"Virtual network type '{virtual_network_type}' cannot be imported; "
            "AI Gateway supports only None or External."
        )
    else:
        try:
            normalized = _networking_properties(
                public_network_access,
                virtual_network_type,
                subnet_resource_id,
            )
            target_configuration = {
                "publicNetworkAccess": normalized.get("publicNetworkAccess"),
                "virtualNetworkType": normalized.get("virtualNetworkType"),
                "subnetResourceId": (
                    normalized.get("virtualNetworkConfiguration") or {}
                ).get("subnetResourceId"),
            }
        except InvalidArgumentValueError as error:
            reasons.append(str(error))
    if (
        virtual_network_type == "External"
        and not mapping.get("subnetResourceId")
    ):
        warnings.append(
            "The source integration subnet will be reused. APIM v2 integration "
            "subnets are dedicated to one service; map network.subnetResourceId "
            "if the source remains active."
        )
    private_endpoint_count = source_configuration.get(
        "privateEndpointConnectionCount",
        0,
    )
    if private_endpoint_count:
        warnings.append(
            f"{private_endpoint_count} private endpoint connection(s) cannot be "
            "copied; create destination private endpoints separately."
        )
    comparable_current = {
        key: current_configuration.get(key)
        for key in target_configuration
    }
    status = "blocked" if reasons else "ready"
    return {
        "order": 1,
        "source": {
            "name": source.get("name"),
            **source_configuration,
        },
        "destination": {
            "name": destination.get("name"),
            "current": comparable_current,
            "target": target_configuration,
        },
        "assessment": {
            "status": status,
            "canImport": not reasons,
            "changesRequired": comparable_current != target_configuration,
            "reasons": reasons,
            "warnings": warnings,
        },
    }


def _effective_url(record, source):
    properties = record["api"].get("properties") or {}
    if properties.get("serviceUrl"):
        return properties["serviceUrl"]
    backend_urls = [
        (backend.get("properties") or {}).get("url")
        for backend in record["backends"]
        if (backend.get("properties") or {}).get("url")
    ]
    if len(set(backend_urls)) == 1:
        return backend_urls[0]
    gateway_url = source.get("gatewayUrl")
    path = properties.get("path")
    if gateway_url and path:
        return f"{gateway_url.rstrip('/')}/{path.strip('/')}"
    return gateway_url


def _classification(
    disposition,
    reason_code,
    reason,
    evidence,
    asset_type=None,
    asset_subtype=None,
):
    return {
        "disposition": disposition,
        "assetType": asset_type,
        "assetSubtype": asset_subtype,
        "reasonCode": reason_code,
        "reason": reason,
        "evidence": evidence,
    }


def _operation_paths(record):
    return sorted(
        {
            str(operation.get("urlTemplate") or "")
            .partition("?")[0]
            .rstrip("/")
            .casefold()
            for operation in record.get("operations") or []
            if operation.get("urlTemplate")
        }
    )


def _model_operation_paths(record):
    paths = _operation_paths(record)
    return [path for path in paths if _is_model_endpoint_path(path)]


def _is_model_endpoint_path(path):
    supported_suffixes = (
        "/chat/completions",
        "/completions",
        "/embeddings",
        "/messages",
        "/responses",
    )
    return path.endswith(supported_suffixes) or bool(
        re.search(
            r"/models/[^/]+:"
            r"(counttokens|embedcontent|generatecontent|streamgeneratecontent)$",
            path,
        )
    )


def _mcp_properties(record):
    properties = (record.get("api") or {}).get("properties") or {}
    mcp_properties = properties.get("mcpProperties")
    return mcp_properties if isinstance(mcp_properties, dict) else {}


def _mcp_endpoint_values(mcp_properties):
    if not isinstance(mcp_properties, dict):
        return []
    endpoints = mcp_properties.get("endpoints")
    if endpoints is None:
        return []
    return endpoints if isinstance(endpoints, (list, tuple)) else [endpoints]


def _is_valid_mcp_endpoint_uri(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlparse(value)
        parsed.port
    except (TypeError, ValueError):
        return False
    return True


def _mcp_endpoint_names(mcp_properties):
    names = set()
    for endpoint in _mcp_endpoint_values(mcp_properties):
        if isinstance(endpoint, str) and endpoint:
            if _is_valid_mcp_endpoint_uri(endpoint):
                names.add(_sanitize_properties(endpoint, "endpoint"))
        elif (
            isinstance(endpoint, dict)
            and isinstance(endpoint.get("name"), str)
            and endpoint["name"]
        ):
            if _is_valid_mcp_endpoint_uri(endpoint["name"]):
                names.add(_sanitize_properties(endpoint["name"], "endpoint"))
    return sorted(names)


def _mcp_endpoint_uri_template(mcp_properties, endpoint_name):
    endpoints = _mcp_endpoint_values(mcp_properties)
    for endpoint in endpoints:
        if (
            isinstance(endpoint, dict)
            and str(endpoint.get("name") or "").casefold() == endpoint_name
            and endpoint.get("uriTemplate")
        ):
            uri_template = endpoint["uriTemplate"]
            if not isinstance(uri_template, str):
                return None, "The MCP endpoint URI template must be a string."
            if not _is_valid_mcp_endpoint_uri(uri_template):
                return None, "The MCP endpoint URI template is malformed."
            return uri_template, None

    string_endpoints = [
        endpoint for endpoint in endpoints if isinstance(endpoint, str) and endpoint
    ]
    if len(string_endpoints) > 1:
        return (
            None,
            "Multiple unnamed MCP endpoints cannot be mapped automatically.",
        )
    if not string_endpoints:
        return None, None
    if not _is_valid_mcp_endpoint_uri(string_endpoints[0]):
        return None, "The MCP endpoint URI template is malformed."
    return string_endpoints[0], None


def _classify(record, effective_url):
    properties = record["api"].get("properties") or {}
    api_type = str(
        properties.get("type") or properties.get("apiType") or ""
    ).casefold()
    if api_type == "mcp":
        if record.get("tools"):
            backing_api_ids = sorted(
                {
                    re.sub(
                        r"/operations/[^/]+/?$",
                        "",
                        str(tool.get("operationId")),
                        flags=re.IGNORECASE,
                    )
                    for tool in record["tools"]
                    if tool.get("operationId")
                }
            )
            return _classification(
                "candidate",
                "SUPPORTED_MCP_REST_BACKED",
                "The MCP API exposes tools backed by APIM REST operations.",
                [
                    {
                        "kind": "mcpTools",
                        "toolCount": len(record["tools"]),
                        "backingApiIds": backing_api_ids,
                    }
                ],
                "mcpServer",
                "mcpApi",
            )
        if properties.get("mcpProperties"):
            mcp_properties = _mcp_properties(record)
            return _classification(
                "candidate",
                "SUPPORTED_MCP_PASSTHROUGH",
                "The MCP API has passthrough transport configuration.",
                [
                    {
                        "kind": "mcpProperties",
                        "transportType": mcp_properties.get("transportType"),
                        "endpointNames": _mcp_endpoint_names(mcp_properties),
                    }
                ],
                "mcpServer",
                "mcpPassthrough",
            )
        return _classification(
            "ignored",
            "MCP_CONFIGURATION_NOT_RECOGNIZED",
            (
                "The MCP API has neither REST-backed tools nor passthrough "
                "transport configuration."
            ),
            [{"kind": "apiType", "value": "mcp"}],
        )

    if api_type not in {"", "http"}:
        return _classification(
            "ignored",
            "UNSUPPORTED_API_TYPE",
            f"APIM API type '{api_type}' is not supported for import.",
            [{"kind": "apiType", "value": api_type}],
        )

    operation_paths = _operation_paths(record)
    model_operation_paths = _model_operation_paths(record)
    effective_path = (
        urlparse(effective_url or "").path.rstrip("/").casefold()
    )
    model_endpoint_paths = list(model_operation_paths)
    if (
        effective_path
        and _is_model_endpoint_path(effective_path)
        and effective_path not in model_endpoint_paths
    ):
        model_endpoint_paths.append(effective_path)
        model_endpoint_paths.sort()
    backend_resource_ids = sorted(
        {
            str(
                (backend.get("properties") or {}).get("resourceId") or ""
            ).casefold()
            for backend in record["backends"]
            if (backend.get("properties") or {}).get("resourceId")
        }
    )
    foundry_resource_ids = [
        resource_id
        for resource_id in backend_resource_ids
        if (
            "microsoft.cognitiveservices/accounts" in resource_id
            or "microsoft.machinelearningservices/workspaces" in resource_id
        )
    ]
    backend_urls = [
        (backend.get("properties") or {}).get("url")
        for backend in record["backends"]
        if (backend.get("properties") or {}).get("url")
    ]
    model_backend_hosts = sorted(
        {
            (urlparse(url).hostname or "").casefold()
            for url in backend_urls
            if (
                "/openai" in urlparse(url).path.casefold()
                or "/deployments/" in urlparse(url).path.casefold()
                or (urlparse(url).hostname or "").casefold().endswith(
                    (
                        ".openai.azure.com",
                        ".models.ai.azure.com",
                        ".models.inference.ai.azure.com",
                    )
                )
            )
        }
    )
    has_models_index = "/models" in operation_paths
    has_chat_completions = any(
        path.endswith("/chat/completions") for path in operation_paths
    )
    if foundry_resource_ids and (model_endpoint_paths or model_backend_hosts):
        evidence = [
            {
                "kind": "foundryBackendResources",
                "resourceIds": foundry_resource_ids,
            }
        ]
        if model_endpoint_paths:
            evidence.append(
                {
                    "kind": "modelEndpoints",
                    "paths": model_endpoint_paths,
                }
            )
        if model_backend_hosts:
            evidence.append(
                {
                    "kind": "modelBackendHosts",
                    "hosts": model_backend_hosts,
                }
            )
        return _classification(
            "candidate",
            "SUPPORTED_FOUNDRY_API",
            "The API has a Foundry backend and model endpoint evidence.",
            evidence,
            "model",
            "foundry",
        )
    if (
        has_models_index
        and has_chat_completions
        and len(record["backends"]) > 1
    ):
        return _classification(
            "deferred",
            "UNIFIED_MODEL_API_DEFERRED",
            (
                "Unified model APIs are known but require model aliases and "
                "backend routes to be mapped individually."
            ),
            [{"kind": "operationPaths", "values": operation_paths}],
            "model",
            "unified",
        )
    if model_endpoint_paths:
        return _classification(
            "candidate",
            "SUPPORTED_LLM_API",
            "The API exposes a supported language model operation.",
            [{"kind": "modelEndpoints", "paths": model_endpoint_paths}],
            "model",
            "llm",
        )

    parsed_url = urlparse(effective_url or "")
    if (
        parsed_url.hostname
        and parsed_url.hostname.casefold().endswith(".services.ai.azure.com")
        and "/agents/" in parsed_url.path.casefold()
    ):
        return _classification(
            "ignored",
            "AGENT_API_NOT_SUPPORTED",
            "Azure AI agent APIs are not import candidates.",
            [
                {
                    "kind": "endpoint",
                    "host": parsed_url.hostname.casefold(),
                    "path": parsed_url.path,
                }
            ],
        )
    return _classification(
        "ignored",
        "NO_SUPPORTED_API_EVIDENCE",
        (
            "The API has no supported model operations, Foundry backend "
            "evidence, or MCP configuration."
        ),
        [{"kind": "operationPaths", "values": operation_paths}],
    )


def _mapping_for(mapping, asset_type, source):
    section = mapping.get(f"{asset_type}s") or {}
    return section.get(source.get("id")) or section.get(source.get("name")) or {}


def _model_api_format(record):
    paths = " ".join(
        operation.get("urlTemplate") or "" for operation in record["operations"]
    ).casefold()
    url = _effective_url(record, {})
    host = (urlparse(url or "").hostname or "").casefold()
    path = urlparse(url or "").path.casefold()
    endpoint_paths = f"{path} {paths}"
    if (
        host == "generativelanguage.googleapis.com"
        and "/openai/" not in endpoint_paths
    ) or any(
        operation in paths
        for operation in (
            ":counttokens",
            ":embedcontent",
            ":generatecontent",
            ":streamgeneratecontent",
        )
    ):
        return "Gemini"
    if "/responses" in endpoint_paths:
        return "ResponsesApi"
    if "/messages" in endpoint_paths or "anthropic" in host:
        return "AnthropicMessages"
    if any(
        endpoint in endpoint_paths
        for endpoint in (
            "/chat/completions",
            "/completions",
            "/embeddings",
            "/models",
        )
    ) or any(host.endswith(suffix) for suffix in MODEL_HOST_SUFFIXES):
        return "OpenAIChatCompletions"
    return None


def _deployment_id(record, mapping):
    mapped = mapping.get("deploymentResourceId")
    if mapped:
        return mapped
    resource_ids = [
        (backend.get("properties") or {}).get("resourceId")
        for backend in record["backends"]
        if (backend.get("properties") or {}).get("resourceId")
    ]
    if len(set(resource_ids)) != 1:
        return None
    resource_id = resource_ids[0].rstrip("/")
    if "/deployments/" in resource_id.casefold():
        return resource_id
    effective_url = _effective_url(record, {})
    match = re.search(
        r"/(?:openai/)?deployments/([^/?]+)",
        urlparse(effective_url or "").path,
        re.IGNORECASE,
    )
    if match:
        return f"{resource_id}/deployments/{match.group(1)}"
    return resource_id


def _same_endpoint_origin(left, right):
    if not left or not right:
        return False
    left_url = urlparse(left or "")
    right_url = urlparse(right or "")
    return (
        left_url.scheme.casefold(),
        left_url.hostname.casefold() if left_url.hostname else None,
        left_url.port,
    ) == (
        right_url.scheme.casefold(),
        right_url.hostname.casefold() if right_url.hostname else None,
        right_url.port,
    )


def _provider_for(deployment_id, effective_url, providers, mapping):
    if mapping.get("providerName"):
        return mapping["providerName"]
    matches = []
    for provider in providers:
        properties = provider.get("properties") or {}
        kind = str(properties.get("kind") or "").casefold()
        if kind == "foundry" and deployment_id:
            resource_ids = (
                (properties.get("foundry") or {}).get("resourceIds") or []
            )
            if any(
                deployment_id.casefold().startswith(
                    resource_id.rstrip("/").casefold()
                )
                for resource_id in resource_ids
            ):
                matches.append(provider.get("name"))
        elif kind == "custom" and _same_endpoint_origin(
            effective_url,
            (properties.get("custom") or {}).get("endpoint"),
        ):
            matches.append(provider.get("name"))
    return matches[0] if len(matches) == 1 else None


def _model_name(deployment_id, mapping):
    if mapping.get("modelName"):
        return mapping["modelName"]
    if not deployment_id:
        return None
    match = re.search(r"/deployments/([^/]+)$", deployment_id, re.IGNORECASE)
    return match.group(1) if match else None


def _foundry_account_id(deployment_id):
    if not deployment_id:
        return None
    return re.split(
        r"/deployments/",
        deployment_id.rstrip("/"),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]


def _provider_endpoint(effective_url):
    parsed = urlparse(effective_url or "")
    if not parsed.scheme or not parsed.hostname:
        return None
    hostname = parsed.hostname
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunparse((parsed.scheme, hostname, "", "", "", ""))


def _policy_assessment(record, asset_type, asset_subtype):
    effective_policies = [record["policy"], *record["inheritedPolicies"]]
    scoped_policies = [
        *record.get("operationPolicies", []),
        *record.get("productPolicies", []),
    ]
    policies = [*effective_policies, *scoped_policies]
    parse_errors = [
        {"scope": policy["scope"], "message": policy["parseError"]}
        for policy in policies
        if policy["parseError"]
    ]
    decision = translate_effective_policies(
        policies,
        asset_type,
        asset_subtype,
    )
    return (
        policies,
        decision["unsupportedCriticalBlockers"],
        parse_errors,
        decision["destinationPolicies"],
        [
            *decision["reducedMappingWarnings"],
            *decision["unsupportedNoncriticalWarnings"],
        ],
    )


def _base_assessment(record, errors, asset_type, asset_subtype):
    (
        policies,
        policy_blockers,
        parse_errors,
        destination_policies,
        translation_warnings,
    ) = _policy_assessment(record, asset_type, asset_subtype)
    reasons = list(policy_blockers)
    warnings = list(translation_warnings)
    if parse_errors:
        reasons.append("One or more APIM policies could not be parsed.")
    api_id = record["source"]["id"].casefold()
    api_scope = api_id.rsplit("/apis/", 1)[0]
    inherited_scopes = {
        policy["scope"].casefold() for policy in record["inheritedPolicies"]
    }
    failed_scopes = []
    for error in errors:
        if error.get("required", True) is False:
            continue
        error_scope = error["scope"].casefold()
        subscription_error = (
            error.get("configurationDomain") == "subscriptions"
            and record["source"].get("subscriptionRequired")
        )
        scope_policy_error = any(
            error_scope.startswith(f"{scope}/policies/")
            for scope in inherited_scopes
        )
        scope_dependency_error = (
            error_scope.startswith(f"{api_scope}/backends")
            or error_scope.startswith(f"{api_scope}/policies/")
        )
        if (
            error_scope.startswith(api_id)
            or scope_policy_error
            or scope_dependency_error
            or subscription_error
        ):
            failed_scopes.append(error["scope"])
    if failed_scopes:
        reasons.append(
            "Discovery was incomplete for: " + ", ".join(failed_scopes)
        )
    return reasons, warnings, policies, destination_policies


def _support_state(state, items=None, discovery_errors=None, reason=None):
    if state not in ASSOCIATED_SUPPORT_STATES:
        raise ValueError(f"Unknown associated configuration state '{state}'.")
    result = {
        "supportState": state,
        "items": items or [],
    }
    if discovery_errors:
        result["discoveryErrors"] = discovery_errors
    if reason:
        result["reason"] = reason
    return result


def _domain_errors(record, errors, domain):
    api_id = str(record["source"].get("id") or "").casefold()
    asset_scope = api_id.rsplit("/apis/", 1)[0]
    service_id = asset_scope.split("/workspaces/", 1)[0]

    def applies(error):
        error_scope = str(error.get("scope") or "").casefold()
        if "/apis/" in error_scope:
            return error_scope.startswith(api_id)
        if "/workspaces/" in error_scope:
            return error_scope.startswith(asset_scope)
        return error_scope.startswith(service_id)

    return [
        error
        for error in errors
        if error.get("configurationDomain") == domain
        and applies(error)
    ]


def _effective_managed_identity_authentications(record):
    policies = [
        record["policy"],
        *record.get("inheritedPolicies", []),
        *record.get("operationPolicies", []),
        *record.get("productPolicies", []),
    ]
    return [
        {
            "scope": policy["scope"],
            "scopeType": policy["scopeType"],
            **settings,
        }
        for policy in policies
        for settings in policy.get("managedIdentityAuthentications", [])
    ]


def _mcp_dependencies(record):
    dependencies = {}
    for tool in record.get("tools") or []:
        operation_id = tool.get("operationId")
        if not operation_id:
            continue
        api_id = re.sub(
            r"/operations/[^/]+/?$",
            "",
            str(operation_id),
            flags=re.IGNORECASE,
        )
        dependency = dependencies.setdefault(
            api_id,
            {
                "apiId": api_id,
                "operationIds": [],
                "toolIds": [],
            },
        )
        dependency["operationIds"].append(operation_id)
        if tool.get("id") or tool.get("name"):
            dependency["toolIds"].append(tool.get("id") or tool.get("name"))
    return [
        {
            **dependency,
            "operationIds": sorted(set(dependency["operationIds"])),
            "toolIds": sorted(set(dependency["toolIds"])),
        }
        for _, dependency in sorted(dependencies.items())
    ]


def _associated_configuration(
    record,
    source,
    classification,
    errors,
):
    backend_summaries = [
        _backend_summary(backend) for backend in record.get("backends") or []
    ]
    credential_backends = [
        backend
        for backend in backend_summaries
        if (backend.get("credentials") or {}).get("hasCredentials")
    ]
    named_values = sorted(
        {
            reference
            for backend in credential_backends
            for reference in (
                backend.get("credentials") or {}
            ).get("namedValueReferences", [])
        }
    )
    managed_identity_authentications = (
        _effective_managed_identity_authentications(record)
    )
    backend_resource_ids = sorted(
        {
            (backend.get("properties") or {}).get("resourceId")
            for backend in record.get("backends") or []
            if (backend.get("properties") or {}).get("resourceId")
            and any(
                provider in str(
                    (backend.get("properties") or {}).get("resourceId")
                ).casefold()
                for provider in (
                    "microsoft.cognitiveservices/accounts",
                    "microsoft.machinelearningservices/workspaces",
                )
            )
        }
    )
    rbac_intents = [
        {
            "targetResourceId": resource_id,
            "tokenAudience": authentication.get("resource"),
            "sourceClientId": authentication.get("clientId"),
            "intent": (
                "Grant the selected destination managed identity permission "
                "to invoke this backend."
            ),
        }
        for resource_id in backend_resource_ids
        for authentication in managed_identity_authentications
    ]
    products = record.get("products") or []
    subscriptions = record.get("subscriptions") or []
    identities = source.get("managedIdentities") or {}
    has_identities = bool(
        identities.get("systemAssigned") or identities.get("userAssigned")
    )
    diagnostic_errors = _domain_errors(record, errors, "diagnostics")
    logger_errors = _domain_errors(record, errors, "loggers")
    subscription_errors = _domain_errors(record, errors, "subscriptions")
    associated = {
        "backendCredentials": _support_state(
            (
                "unsupported-critical"
                if credential_backends
                else "importable"
            ),
            credential_backends,
            reason=(
                "Backend credential values are not written by dry-run import."
                if credential_backends
                else None
            ),
        ),
        "namedValueReferences": _support_state(
            "deferred" if named_values else "importable",
            [{"name": name, "value": "<redacted>"} for name in named_values],
            reason=(
                "Named-value references require an explicit destination "
                "credential mapping."
                if named_values
                else None
            ),
        ),
        "products": _support_state(
            "unsupported-noncritical" if products else "importable",
            products,
            reason=(
                "Product membership and product policy scope are inventoried "
                "but are not destination asset relationships."
                if products
                else None
            ),
        ),
        "subscriptions": _support_state(
            (
                "unsupported-critical"
                if record["source"].get("subscriptionRequired")
                else (
                    "unsupported-noncritical"
                    if subscriptions
                    else "importable"
                )
            ),
            subscriptions,
            subscription_errors,
            reason=(
                "APIM subscription relationships are not destination "
                "subscriptions."
                if subscriptions or record["source"].get("subscriptionRequired")
                else None
            ),
        ),
        "managedIdentities": _support_state(
            "deferred" if has_identities else "importable",
            [identities] if has_identities else [],
            reason=(
                "Source identities are inventoried for explicit destination "
                "identity selection."
                if has_identities
                else None
            ),
        ),
        "managedIdentityAuthentication": _support_state(
            (
                "unsupported-critical"
                if managed_identity_authentications
                else "importable"
            ),
            managed_identity_authentications,
            reason=(
                "authentication-managed-identity policy settings require "
                "destination identity and audience configuration."
                if managed_identity_authentications
                else None
            ),
        ),
        "requiredRbac": _support_state(
            "deferred" if rbac_intents else "importable",
            rbac_intents,
            reason=(
                "RBAC intent is inventoried only; no role assignment is made."
                if rbac_intents
                else None
            ),
        ),
        "diagnostics": _support_state(
            (
                "unsupported-noncritical"
                if record.get("diagnostics") or diagnostic_errors
                else "importable"
            ),
            record.get("diagnostics") or [],
            diagnostic_errors,
            reason=(
                "APIM diagnostics are inventoried for separate telemetry "
                "configuration."
                if record.get("diagnostics") or diagnostic_errors
                else None
            ),
        ),
        "loggerReferences": _support_state(
            (
                "unsupported-noncritical"
                if record.get("loggers") or logger_errors
                else "importable"
            ),
            record.get("loggers") or [],
            logger_errors,
            reason=(
                "APIM logger references are inventoried but not copied."
                if record.get("loggers") or logger_errors
                else None
            ),
        ),
    }
    if classification["assetType"] == "mcpServer":
        mcp_properties = (
            (record["api"].get("properties") or {}).get("mcpProperties") or {}
        )
        dependencies = _mcp_dependencies(record)
        associated["mcpConfiguration"] = _support_state(
            "reduced" if dependencies else "importable",
            [
                {
                    "mcpProperties": _sanitize_properties(mcp_properties),
                    "tools": record.get("tools") or [],
                    "dependencies": dependencies,
                }
            ],
            reason=(
                "REST backing APIs remain dependencies of the MCP server "
                "rather than standalone destination assets."
                if dependencies
                else None
            ),
        )
    associated["supportStateCounts"] = {
        state: sum(
            domain.get("supportState") == state
            for domain in associated.values()
            if isinstance(domain, dict)
        )
        for state in sorted(ASSOCIATED_SUPPORT_STATES)
    }
    return associated


def _resolved_backend(record):
    if len(record["backends"]) == 1:
        return record["backends"][0]
    return None


def _resolve_apim_credential_value(cmd, source_apim_id, value):
    match = re.fullmatch(r"\{\{([^{}]+)\}\}", str(value or "").strip())
    if not match:
        return value
    named_value_id = quote(match.group(1).strip(), safe="")
    response = _response_json(
        _request(
            cmd,
            "POST",
            f"{source_apim_id}/namedValues/{named_value_id}/listValue",
            {},
        )
    ) or {}
    return response.get("value")


def _apim_backend_api_key(cmd, record, provider):
    backend = _resolved_backend(record)
    if not backend:
        return None
    credentials = (backend.get("properties") or {}).get("credentials") or {}
    headers = credentials.get("header") or {}
    custom = ((provider.get("properties") or {}).get("custom") or {})
    authentication = custom.get("authentication") or {}
    configured = (
        authentication.get("apiKey")
        if authentication.get("kind") == "ApiKey"
        else authentication.get("header")
    ) or {}
    configured_header = str(
        configured.get("headerName") or configured.get("name") or ""
    ).strip()
    header_name = next(
        (
            name
            for name in headers
            if configured_header
            and name.casefold() == configured_header.casefold()
        ),
        None,
    )
    if header_name is None:
        preferred_names = ("authorization", "api-key", "x-api-key")
        header_name = next(
            (
                name
                for preferred in preferred_names
                for name in headers
                if name.casefold() == preferred
            ),
            None,
        )
    if header_name is None and len(headers) == 1:
        header_name = next(iter(headers))
    values = headers.get(header_name) if header_name else None
    if isinstance(values, str):
        values = [values]
    if header_name and isinstance(values, list) and len(values) == 1:
        source_apim_id = record["source"]["id"].rsplit("/apis/", 1)[0]
        try:
            value = _resolve_apim_credential_value(
                cmd,
                source_apim_id,
                values[0],
            )
        except HTTPError as error:
            return {"error": str(error)}
        if value:
            return {"headerName": header_name, "value": value}
    authorization = credentials.get("authorization") or {}
    scheme = str(authorization.get("scheme") or "").strip()
    parameter = authorization.get("parameter")
    if scheme and parameter:
        source_apim_id = record["source"]["id"].rsplit("/apis/", 1)[0]
        try:
            value = _resolve_apim_credential_value(
                cmd,
                source_apim_id,
                parameter,
            )
        except HTTPError as error:
            return {"error": str(error)}
        if value:
            return {
                "headerName": "Authorization",
                "value": f"{scheme} {value}",
            }
    return None


def _custom_provider_models(
    cmd,
    provider,
    destination_id,
    api_key_header_name=None,
    api_key_value=None,
):
    cache_key = "_importModelDiscovery"
    use_cache = api_key_value is None
    if use_cache and cache_key in provider:
        return provider[cache_key]
    provider_name = provider.get("name") or ""
    provider_path = (
        provider.get("id")
        or f"{_provider_path(destination_id)}/{quote(provider_name, safe='')}"
    )
    discovery_provider = provider
    if api_key_header_name:
        discovery_provider = deepcopy(provider)
        custom = (
            discovery_provider.setdefault("properties", {})
            .setdefault("custom", {})
        )
        custom["authentication"] = {
            "kind": "ApiKey",
            "apiKey": {"headerName": api_key_header_name},
        }
    try:
        discovery_kwargs = {
            "cmd": cmd,
            "provider_path": provider_path,
        }
        if api_key_value is not None:
            discovery_kwargs["api_key_value"] = api_key_value
        result = {
            "models": _discover_custom_models(
                discovery_provider,
                **discovery_kwargs,
            ),
            "error": None,
        }
    except (AzCLIError, OSError, RequestException) as error:
        logger.debug(
            "Custom model discovery failed for provider '%s': %s",
            provider_name,
            error,
        )
        result = {"models": [], "error": str(error)}
    if use_cache:
        provider[cache_key] = result
    return result


def _foundry_provider_models(cmd, provider, destination_id):
    provider_name = provider.get("name") or ""
    provider_path = (
        provider.get("id")
        or f"{_provider_path(destination_id)}/{quote(provider_name, safe='')}"
    )
    try:
        changes = _sync_plan(cmd, provider, provider_path)
    except (AzCLIError, OSError, RequestException) as error:
        logger.debug(
            "Foundry model discovery failed for provider '%s': %s",
            provider_name,
            error,
        )
        return {"models": [], "error": str(error)}
    models = []
    for change in changes:
        if change.get("action") != "create":
            continue
        properties = change.get("properties") or {}
        deployment = properties.get("deployment") or {}
        model_name = deployment.get("modelName")
        if model_name:
            models.append(
                {
                    "modelName": model_name,
                    "supportedEndpoints": (
                        properties.get("supportedEndpoints") or []
                    ),
                    "deployment": deployment,
                }
            )
    return {"models": models, "error": None}


def _assess_unified_model(record, mapping, effective_url, errors):
    reasons, warnings, policies, destination_policies = _base_assessment(
        record,
        errors,
        "model",
        "unified",
    )
    if not effective_url:
        reasons.append("No unified model API endpoint URL could be resolved.")
    has_user_info, has_query = _url_safety(effective_url)
    if has_user_info:
        reasons.append(
            "The unified model API endpoint URL contains embedded credentials "
            "that cannot be copied safely."
        )
    if has_query:
        warnings.append(
            "Unified model API endpoint query values were redacted and require "
            "review."
        )
    reasons.append(
        "Unified model API import requires its model aliases and backend routes "
        "to be mapped individually; automatic mapping is not yet available."
    )
    destination_name = mapping.get("name") or record["source"]["name"]
    return (
        destination_name,
        {
            "name": destination_name,
            "resourceType": None,
        },
        {
            "apiFormat": "OpenAIChatCompletions",
            "deployment": None,
            "backends": [
                _backend_summary(backend) for backend in record["backends"]
            ],
            "operations": record["operations"],
            "products": record.get("products", []),
            "policies": policies,
            "destinationPolicies": destination_policies,
        },
        reasons,
        warnings,
    )


def _assess_model(
    record,
    subtype,
    destination,
    mapping,
    effective_url,
    errors,
    cmd=None,
    destination_id="",
):
    if subtype == "unified":
        return _assess_unified_model(
            record,
            mapping,
            effective_url,
            errors,
        )
    reasons, warnings, policies, destination_policies = _base_assessment(
        record,
        errors,
        "model",
        subtype,
    )
    backend = _resolved_backend(record)
    deployment_id = _deployment_id(record, mapping)
    provider_name = _provider_for(
        deployment_id,
        effective_url,
        destination["providers"],
        mapping,
    )
    provider = next(
        (
            candidate
            for candidate in destination["providers"]
            if str(candidate.get("name", "")).casefold()
            == str(provider_name or "").casefold()
        ),
        None,
    )
    provider_was_existing = provider is not None
    provider_create = None
    if not provider:
        proposed_name = provider_name or (
            f"{record['source']['name']}-provider"
        )
        if subtype == "foundry" and deployment_id:
            account_id = _foundry_account_id(deployment_id)
            provider_create = {
                "name": proposed_name,
                "kind": "Foundry",
                "endpoint": _provider_endpoint(effective_url),
                "resourceIds": [account_id],
                "authKind": "ApiKey",
                "apiKeyHeaderName": "api-key",
                "secretRefs": [f"{account_id}:primaryKey"],
            }
        elif subtype == "llm" and effective_url:
            provisional_provider = {
                "name": proposed_name,
                "properties": {
                    "kind": "Custom",
                    "custom": {"endpoint": _provider_endpoint(effective_url)},
                },
            }
            backend_api_key = _apim_backend_api_key(
                cmd,
                record,
                provisional_provider,
            )
            if (backend_api_key or {}).get("value"):
                provider_create = {
                    "name": proposed_name,
                    "kind": "Custom",
                    "endpoint": _provider_endpoint(effective_url),
                    "authKind": "ApiKey",
                    "apiKeyHeaderName": backend_api_key["headerName"],
                    "_apiKeyValue": backend_api_key["value"],
                    "secretRefs": [
                        (
                            f"{record['source']['id']}:backend:"
                            f"{backend_api_key['headerName']}"
                        )
                    ],
                }
        if provider_create:
            provider_name = proposed_name
            provider = {
                "name": proposed_name,
                "properties": {
                    "kind": provider_create["kind"],
                    str(provider_create["kind"]).casefold(): {
                        "endpoint": provider_create.get("endpoint"),
                        "resourceIds": provider_create.get("resourceIds"),
                        "authentication": {
                            "kind": provider_create.get("authKind"),
                            "apiKey": {
                                "headerName": provider_create.get(
                                    "apiKeyHeaderName"
                                )
                            },
                        },
                    },
                },
            }
    provider_kind = str(
        ((provider or {}).get("properties") or {}).get("kind") or ""
    )
    model_name = _model_name(deployment_id, mapping)
    provider_models = None
    provider_only = False
    has_user_info, has_query = _url_safety(effective_url)
    if not effective_url:
        reasons.append("No model backend URL could be resolved.")
    if has_user_info:
        reasons.append(
            "The model endpoint URL contains embedded credentials that cannot "
            "be copied safely."
        )
    if has_query:
        warnings.append(
            "Model endpoint query values were redacted and require review."
        )
    if len(record["backends"]) > 1:
        reasons.append("Multiple APIM backends cannot be mapped automatically.")
    if not provider_name:
        reasons.append(
            "No existing destination provider matched and the source endpoint, "
            "resource IDs, or authentication were insufficient to create one "
            "safely; provide providerName in the mapping file."
        )
    elif not provider:
        reasons.append(
            f"Destination model provider '{provider_name}' does not exist."
        )
    elif provider_kind.casefold() not in {"custom", "foundry"}:
        reasons.append(
            f"Destination model provider '{provider_name}' has unsupported "
            f"kind '{provider_kind or '(missing)'}'."
        )
    elif provider_kind.casefold() == "foundry" and not deployment_id:
        reasons.append(
            "No deployment resource ID was found for the Foundry provider; "
            "provide one in the mapping file."
        )
    if not model_name and provider_kind.casefold() in {"custom", "foundry"}:
        backend_api_key = None
        if provider_kind.casefold() == "custom":
            backend_api_key = _apim_backend_api_key(cmd, record, provider)
            discovery = _custom_provider_models(
                cmd,
                provider,
                destination_id,
                api_key_header_name=(
                    (backend_api_key or {}).get("headerName")
                ),
                api_key_value=(backend_api_key or {}).get("value"),
            )
        else:
            discovery = _foundry_provider_models(
                cmd,
                provider,
                destination_id,
            )
        provider_models = discovery["models"]
        provider_only = not provider_models
        if not provider_models and discovery["error"]:
            if (backend_api_key or {}).get("error"):
                warnings.append(
                    "The source APIM backend credential could not be resolved: "
                    f"{backend_api_key['error']}"
                )
            warnings.append(
                f"Models could not be discovered from {provider_kind} provider "
                f"'{provider_name}'. Import will continue with the provider "
                "only; models can be synchronized later. Discovery error: "
                f"{discovery['error']}"
            )
    elif not model_name and provider_kind:
        reasons.append(
            "No deployment model name was found; provide modelName in "
            "the mapping file."
        )
    destination_name = mapping.get("name") or record["source"]["name"]
    detected_api_format = _model_api_format(record)
    api_format = mapping.get("apiFormat") or detected_api_format
    if detected_api_format == "Gemini":
        reasons.append(
            "Native Gemini APIs cannot be imported. Use an OpenAI-compatible "
            "or Anthropic API."
        )
    elif api_format not in {
        "AnthropicMessages",
        "OpenAIChatCompletions",
        "ResponsesApi",
    }:
        if subtype == "llm" and api_format is None:
            reasons.append(
                "The language model API is not OpenAI-compatible, Responses, "
                "or Anthropic Messages."
            )
        else:
            reasons.append(f"Model API format '{api_format}' is not supported.")
    deployment = {
        "modelName": model_name,
        "modelVersion": mapping.get("modelVersion"),
    }
    if deployment_id and provider_kind.casefold() == "foundry":
        deployment["resourceId"] = deployment_id
    configuration = {
        "apiFormat": api_format,
        "deployment": deployment if model_name else None,
        "providerModels": provider_models,
        "providerOnly": provider_only,
        "supportedEndpoints": sorted(
            {
                operation["urlTemplate"]
                for operation in record["operations"]
                if operation.get("urlTemplate")
            }
        ),
        "backend": _backend_summary(backend),
        "operations": record["operations"],
        "products": record.get("products", []),
        "policies": policies,
        "destinationPolicies": destination_policies,
        "providerCreate": provider_create,
        "providerExists": provider_was_existing,
        "providerCredentialMapped": bool(provider),
    }
    return (
        destination_name,
        {
            "name": destination_name,
            "providerName": provider_name,
            "resourceType": "model",
        },
        configuration,
        reasons,
        warnings,
    )


def _assess_tool(
    record,
    subtype,
    destination,
    mapping,
    effective_url,
    errors,
):
    reasons, warnings, policies, destination_policies = _base_assessment(
        record,
        errors,
        "mcpServer",
        subtype,
    )
    subscription_credential = record.get("subscriptionCredential") or {}
    if subtype == "mcpUnknown":
        reasons.append(
            "The MCP API has neither tool resources nor passthrough "
            "mcpProperties, so its server type cannot be determined."
        )
    if not effective_url:
        reasons.append("No tool endpoint URL could be resolved.")
    has_user_info, has_query = _url_safety(effective_url)
    if has_user_info:
        reasons.append(
            "The tool endpoint URL contains embedded credentials that cannot "
            "be copied safely."
        )
    if has_query:
        warnings.append(
            "Tool endpoint query values were redacted and require review."
        )
    if len(record["backends"]) > 1:
        reasons.append("Multiple APIM backends cannot be mapped automatically.")
    backend = _resolved_backend(record)
    credentials = _credential_summary(
        ((backend or {}).get("properties") or {}).get("credentials")
    )
    if credentials["hasCredentials"]:
        reasons.append(
            "APIM backend credentials require an explicit destination mapping."
        )
    if (
        record["source"]["subscriptionRequired"]
        and not (record["api"].get("properties") or {}).get("serviceUrl")
        and not backend
    ):
        if (
            subtype == "mcpApi"
            and record.get("tools")
            and subscription_credential.get("available")
        ):
            if subscription_credential.get("candidateCount", 0) > 1:
                warnings.append(
                    "Multiple active APIM subscriptions were available; "
                    f"selected '{subscription_credential.get('subscriptionName')}'."
                )
        else:
            reasons.append(
                subscription_credential.get("error")
                or "The fallback APIM gateway endpoint requires a subscription key."
            )
    destination_name = mapping.get("name") or record["source"]["name"]
    endpoint = {
        "namespace": mapping.get("namespace") or destination_name,
        "kind": "mcp",
        "required": True,
    }
    mcp_properties = _mcp_properties(record)
    source_transport = mcp_properties.get("transportType")
    if source_transport == "streamable":
        source_transport = "streamableHttp"
    transport = mapping.get("transport") or source_transport or "streamableHttp"
    if transport not in {"sse", "streamableHttp"}:
        reasons.append(f"MCP transport '{transport}' is not supported.")
    endpoint_url = effective_url
    if subtype == "mcpPassthrough":
        endpoint_name = "sse" if transport == "sse" else "message"
        source_endpoint, endpoint_error = _mcp_endpoint_uri_template(
            mcp_properties,
            endpoint_name,
        )
        if endpoint_error:
            reasons.append(endpoint_error)
        elif source_endpoint:
            try:
                endpoint_url = urljoin(
                    f"{str(effective_url or '').rstrip('/')}/",
                    source_endpoint,
                )
            except (TypeError, ValueError):
                reasons.append("The MCP endpoint URI template is malformed.")
    endpoint_has_user_info, endpoint_has_query = _url_safety(endpoint_url)
    if endpoint_has_user_info and not has_user_info:
        reasons.append(
            "The MCP endpoint URI template contains embedded credentials that "
            "cannot be copied safely."
        )
    if endpoint_has_query and not has_query:
        warnings.append(
            "MCP endpoint URI template query values were redacted and require "
            "review."
        )
    endpoint["mcp"] = {
        "url": endpoint_url,
        "transport": transport,
    }
    if subscription_credential.get("available"):
        endpoint["credentials"] = {
            "type": "header",
            "headers": {
                subscription_credential["headerName"]: [
                    subscription_credential["value"]
                ]
            },
        }
    return (
        destination_name,
        {
            "name": destination_name,
            "resourceType": "toolServer",
        },
        {
            "endpoint": endpoint,
            "backend": _backend_summary(backend),
            "operations": record["operations"],
            "tools": record.get("tools", []),
            "products": record.get("products", []),
            "policies": policies,
            "destinationPolicies": destination_policies,
        },
        reasons,
        warnings,
    )


def _apply_conflict(
    asset_type,
    target,
    destination,
    conflict_policy,
    reasons,
    warnings,
):
    destination_name = target["name"]
    if asset_type == "model":
        provider_name = target.get("providerName")
        conflict = destination_name.casefold() in destination[
            "unscopedModelNames"
        ]
        if provider_name:
            conflict = conflict or (
                provider_name.casefold(),
                destination_name.casefold(),
            ) in destination["modelKeys"]
    else:
        conflict = destination_name.casefold() in destination["toolNames"]
    if not conflict:
        return None
    if conflict_policy == "fail":
        reasons.append(
            f"A destination {asset_type} named '{destination_name}' already exists."
        )
        return "fail"
    if conflict_policy == "skip":
        warnings.append(
            f"Existing destination {asset_type} '{destination_name}' will be skipped."
        )
        return "skip"
    warnings.append(
        f"Existing destination {asset_type} '{destination_name}' will be overwritten."
    )
    return "overwrite"


def _inventory_asset(
    record,
    source,
    destination,
    mapping,
    conflict_policy,
    errors,
    cmd=None,
    destination_id="",
    classification=None,
):
    effective_url = _effective_url(record, source)
    classification = classification or _classify(record, effective_url)
    if classification["disposition"] != "candidate":
        return None
    asset_type = classification["assetType"]
    subtype = classification["assetSubtype"]
    asset_mapping = _mapping_for(mapping, asset_type, record["source"])
    if not isinstance(asset_mapping, dict):
        raise InvalidArgumentValueError(
            f"Mapping for '{record['source']['name']}' must be a JSON object."
        )
    if asset_type == "model":
        assessed = _assess_model(
            record,
            subtype,
            destination,
            asset_mapping,
            effective_url,
            errors,
            cmd,
            destination_id,
        )
    else:
        assessed = _assess_tool(
            record,
            subtype,
            destination,
            asset_mapping,
            effective_url,
            errors,
        )
    destination_name, target, configuration, reasons, warnings = assessed
    associated_configuration = _associated_configuration(
        record,
        source,
        classification,
        errors,
    )
    provider_models = configuration.get("providerModels")
    if asset_type == "model" and provider_models:
        model_conflicts = {}
        for model in provider_models:
            model_name = model.get("name") or model.get("modelName")
            model_reasons = []
            model_warnings = []
            model_conflicts[model_name] = _apply_conflict(
                "model",
                {
                    "name": model_name,
                    "providerName": target.get("providerName"),
                },
                destination,
                conflict_policy,
                model_reasons,
                model_warnings,
            )
            reasons.extend(model_reasons)
            warnings.extend(model_warnings)
        configuration["modelConflicts"] = model_conflicts
        conflict = None
    elif asset_type == "model" and configuration.get("deployment") is None:
        conflict = None
    else:
        conflict = _apply_conflict(
            asset_type,
            target,
            destination,
            conflict_policy,
            reasons,
            warnings,
        )
    if conflict == "skip":
        status = "skipped"
    elif reasons:
        status = "blocked"
    else:
        status = "ready"
    result = {
        "order": 2,
        "assetType": asset_type,
        "assetSubtype": subtype,
        "classification": classification,
        "inventory": _subtype_inventory(
            record,
            classification,
            configuration,
        ),
        "associatedConfiguration": associated_configuration,
        "source": record["source"],
        "destination": target,
        "configuration": configuration,
        "assessment": {
            "status": status,
            "canImport": status == "ready",
            "conflict": conflict,
            "reasons": reasons,
            "warnings": warnings,
        },
    }
    if (record.get("subscriptionCredential") or {}).get("_value"):
        result["_executionSecrets"] = {
            "subscriptionKey": record["subscriptionCredential"]["_value"]
        }
    return result


def _subtype_inventory(record, classification, configuration):
    subtype = classification["assetSubtype"]
    if subtype in {"llm", "foundry"}:
        inventory = {
            "apiFormat": configuration.get("apiFormat"),
            "operationPaths": _operation_paths(record),
        }
        if subtype == "foundry":
            inventory["backendResourceIds"] = sorted(
                {
                    (backend.get("properties") or {}).get("resourceId")
                    for backend in record["backends"]
                    if (backend.get("properties") or {}).get("resourceId")
                }
            )
        return inventory
    if subtype == "mcpPassthrough":
        mcp = (record["api"].get("properties") or {}).get("mcpProperties") or {}
        return {
            "mcpProperties": _sanitize_properties(mcp),
            "tools": record.get("tools") or [],
            "dependencies": _mcp_dependencies(record),
        }
    return {
        "mcpProperties": _sanitize_properties(
            (record["api"].get("properties") or {}).get("mcpProperties") or {}
        ),
        "tools": record.get("tools") or [],
        "dependencies": _mcp_dependencies(record),
    }


def _summary(assets, discovery_errors, discovered_total):
    by_type = {}
    by_status = {}
    for asset in assets:
        asset_type = asset["assetType"]
        status = asset["assessment"]["status"]
        by_type[asset_type] = by_type.get(asset_type, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "discovered": discovered_total,
        "included": len(assets),
        "ready": by_status.get("ready", 0),
        "blocked": by_status.get("blocked", 0),
        "skipped": by_status.get("skipped", 0),
        "byType": {
            "models": by_type.get("model", 0),
            "mcpServers": by_type.get("mcpServer", 0),
        },
        "discoveryComplete": not discovery_errors,
        "discoveryErrorCount": len(discovery_errors),
    }


def format_import_table(result):
    if result.get("dryRun") is False and any(
        "status" in action for action in result.get("actions") or []
    ):
        return [
            {
                "Type": action.get("type"),
                "Source": action.get("name"),
                "Workspace": "",
                "Destination": action.get("target"),
                "Status": action.get("status"),
            }
            for action in result["actions"]
        ]
    rows = []
    network = result.get("networkConfiguration") or {}
    if network:
        source = network.get("source") or {}
        destination = network.get("destination") or {}
        assessment = network.get("assessment") or {}
        rows.append(
            {
                "Type": "network",
                "Source": source.get("name"),
                "Workspace": "(service)",
                "Destination": destination.get("name"),
                "Status": assessment.get("status"),
            }
        )
    for asset in result.get("assets") or []:
        source = asset.get("source") or {}
        destination = asset.get("destination") or {}
        assessment = asset.get("assessment") or {}
        destination_name = destination.get("name") or ""
        provider_name = destination.get("providerName")
        configuration = asset.get("configuration") or {}
        provider_sync = (
            asset.get("assetType") == "model"
            and (
                configuration.get("providerModels") is not None
                or configuration.get("providerOnly")
            )
        )
        if provider_sync:
            destination_name = provider_name or destination_name
        elif provider_name:
            destination_name = f"{provider_name}/{destination_name}"
        rows.append(
            {
                "Type": _asset_display_type(asset),
                "Source": source.get("name"),
                "Workspace": source.get("workspace") or "(service)",
                "Destination": destination_name,
                "Status": assessment.get("status"),
            }
        )
    for error in result.get("discoveryErrors") or []:
        rows.append(
            {
                "Type": "discovery",
                "Source": error.get("scope"),
                "Workspace": "",
                "Destination": "",
                "Status": (
                    "error"
                    if error.get("required", True)
                    else "warning"
                ),
            }
        )
    return rows


def _asset_display_type(asset):
    if asset.get("assetSubtype") == "provider":
        return "provider"
    subtype = asset.get("assetSubtype")
    labels = {
        "llm": "llm",
        "foundry": "foundry",
        "unified": "unified",
        "mcpApi": "mcp-api",
        "mcpPassthrough": "mcp-passthrough",
        "mcpUnknown": "mcp",
    }
    return labels.get(subtype, subtype or asset.get("assetType") or "asset")


def _inventory_row(
    asset_type,
    source,
    workspace,
    target_type,
    target,
    status,
):
    return {
        "Type": asset_type,
        "Source": source or "-",
        "Workspace": workspace or "(service)",
        "Target type": target_type or "-",
        "Target": target or "-",
        "Status": status,
    }


def _source_sort_key(source):
    return (
        str(source.get("workspace") or "").casefold(),
        str(source.get("name") or "").casefold(),
        str(source.get("id") or "").casefold(),
    )


def _model_target(destination):
    provider_name = destination.get("providerName")
    model_name = destination.get("name")
    if not provider_name or not model_name:
        return None
    return f"{provider_name}/{model_name}"


def _asset_target(asset):
    destination = asset.get("destination") or {}
    configuration = asset.get("configuration") or {}
    if asset.get("assetType") == "model":
        provider_sync = (
            configuration.get("providerModels") is not None
            or configuration.get("providerOnly")
        )
        if provider_sync:
            return "Model provider", destination.get("providerName")
        return "Model", _model_target(destination)
    if asset.get("assetType") == "mcpServer":
        return "Tool server", destination.get("name")
    return None, None


def _has_noncritical_configuration_caveat(asset):
    caveat_states = {
        "reduced",
        "deferred",
        "unsupported-noncritical",
    }
    return any(
        details.get("supportState") in caveat_states
        for details in (asset.get("associatedConfiguration") or {}).values()
        if isinstance(details, dict)
    )


def _has_critical_configuration_blocker(asset):
    configuration = asset.get("configuration") or {}
    credential = (configuration.get("endpoint") or {}).get("credentials") or {}
    for domain, details in (asset.get("associatedConfiguration") or {}).items():
        if (
            not isinstance(details, dict)
            or details.get("supportState") != "unsupported-critical"
        ):
            continue
        if (
            domain == "backendCredentials"
            and asset.get("assetType") == "model"
            and configuration.get("providerCredentialMapped")
        ):
            continue
        if (
            domain == "subscriptions"
            and asset.get("assetSubtype") == "mcpApi"
            and credential.get("type") == "header"
            and credential.get("headers")
        ):
            continue
        return True
    return False


def _has_intrinsically_unsupported_configuration(asset):
    configuration = asset.get("configuration") or {}
    if asset.get("assetType") == "model":
        api_format = str(configuration.get("apiFormat") or "").casefold()
        if api_format and api_format not in {
            "anthropicmessages",
            "openaichatcompletions",
            "responsesapi",
        }:
            return True
    if asset.get("assetType") != "mcpServer":
        return False
    mcp_properties = (
        (asset.get("inventory") or {}).get("mcpProperties") or {}
    )
    source_transport = str(
        mcp_properties.get("transportType") or ""
    ).casefold()
    if source_transport == "streamable":
        source_transport = "streamablehttp"
    return source_transport not in {"", "sse", "streamablehttp"}


def _asset_inventory_status(asset):
    assessment = asset.get("assessment") or {}
    if _has_intrinsically_unsupported_configuration(asset):
        return "unsupported"
    if assessment.get("status") == "skipped":
        return "skipped"
    if (
        assessment.get("status") == "blocked"
        or _has_critical_configuration_blocker(asset)
    ):
        return "blocked"
    if assessment.get("warnings") or _has_noncritical_configuration_caveat(asset):
        return "warn"
    return "ready"


def _provider_model_status(asset, model):
    if _has_intrinsically_unsupported_configuration(asset):
        return "unsupported"
    model_name = model.get("name") or model.get("modelName")
    conflict = (
        (asset.get("configuration") or {}).get("modelConflicts") or {}
    ).get(model_name)
    if conflict == "skip":
        return "skipped"
    if conflict == "fail":
        return "blocked"
    return _asset_inventory_status(asset)


def _provider_model_rows(asset):
    source = asset.get("source") or {}
    destination = asset.get("destination") or {}
    provider_name = destination.get("providerName")
    models = (asset.get("configuration") or {}).get("providerModels") or []
    rows = []
    for model in sorted(
        models,
        key=lambda item: str(
            item.get("name") or item.get("modelName") or ""
        ).casefold(),
    ):
        model_name = model.get("name") or model.get("modelName")
        rows.append(
            _inventory_row(
                "Model",
                model_name,
                source.get("workspace"),
                "Model" if provider_name and model_name else None,
                (
                    f"{provider_name}/{model_name}"
                    if provider_name and model_name
                    else None
                ),
                _provider_model_status(asset, model),
            )
        )
    return rows


def _asset_inventory_rows(asset):
    source = asset.get("source") or {}
    target_type, target = _asset_target(asset)
    rows = [
        _inventory_row(
            "Model" if asset.get("assetType") == "model" else "MCP",
            source.get("name"),
            source.get("workspace"),
            target_type,
            target,
            _asset_inventory_status(asset),
        )
    ]
    if (
        asset.get("assetType") == "model"
        and (asset.get("configuration") or {}).get("providerModels") is not None
    ):
        rows.extend(_provider_model_rows(asset))
    return rows


def _deferred_api_inventory_rows(api):
    classification = api.get("classification") or {}
    asset_type = classification.get("assetType") or api.get("assetType")
    return [
        _inventory_row(
            "Model" if asset_type == "model" else "MCP",
            api.get("name"),
            api.get("workspace"),
            None,
            None,
            "blocked",
        )
    ]


def _ignored_api_inventory_rows(api):
    classification = api.get("classification") or {}
    reason_code = classification.get("reasonCode") or api.get("reasonCode")
    source_api_type = str(api.get("apiType") or "").casefold()
    if reason_code == "AGENT_API_NOT_SUPPORTED":
        asset_type = "A2A"
    elif (
        classification.get("assetType") == "mcpServer"
        or source_api_type == "mcp"
    ):
        asset_type = "MCP"
    elif classification.get("assetType") == "model":
        asset_type = "Model"
    else:
        asset_type = "API"
    return [
        _inventory_row(
            asset_type,
            api.get("name"),
            api.get("workspace"),
            None,
            None,
            "skipped",
        )
    ]


def _suppressed_api_inventory_rows(api):
    return [
        _inventory_row(
            "API",
            api.get("name"),
            api.get("workspace"),
            None,
            None,
            "skipped",
        )
    ]


def _workspace_inventory_rows(api_sources):
    workspaces = sorted(
        {
            str(source.get("workspace"))
            for source in api_sources
            if source.get("workspace")
        },
        key=str.casefold,
    )
    return [
        _inventory_row(
            "Gateway",
            workspace,
            workspace,
            "workspace",
            DEFAULT_WORKSPACE,
            "ready" if workspace == DEFAULT_WORKSPACE else "warn",
        )
        for workspace in workspaces
    ]


def _identity_inventory_rows(result):
    identities = (result.get("source") or {}).get("managedIdentities") or {}
    rows = []
    if identities.get("systemAssigned"):
        rows.append(
            _inventory_row(
                "Identity",
                "system-assigned",
                None,
                "Identity",
                None,
                "warn",
            )
        )
    rows.extend(
        _inventory_row(
            "Identity",
            identity.get("resourceId") or identity.get("clientId"),
            None,
            "Identity",
            None,
            "warn",
        )
        for identity in sorted(
            identities.get("userAssigned") or [],
            key=lambda item: str(
                item.get("resourceId") or item.get("clientId") or ""
            ).casefold(),
        )
    )
    return rows


def _key_inventory_rows(assets):
    named_values = {}
    subscription_keys = {}
    for asset in sorted(
        assets,
        key=lambda item: _source_sort_key(item.get("source") or {}),
    ):
        source = asset.get("source") or {}
        workspace = source.get("workspace")
        associated = asset.get("associatedConfiguration") or {}
        for item in (
            (associated.get("namedValueReferences") or {}).get("items") or []
        ):
            name = item.get("name")
            if name:
                named_values.setdefault(
                    str(name).casefold(),
                    _inventory_row(
                        "Keys",
                        name,
                        workspace,
                        "Keys",
                        None,
                        "blocked",
                    ),
                )
        endpoint = (asset.get("configuration") or {}).get("endpoint") or {}
        if not (endpoint.get("credentials") or {}).get("headers"):
            continue
        target_type, target = _asset_target(asset)
        for subscription in (
            (associated.get("subscriptions") or {}).get("items") or []
        ):
            name = subscription.get("name") or subscription.get("displayName")
            if name:
                subscription_keys.setdefault(
                    str(subscription.get("id") or name).casefold(),
                    _inventory_row(
                        "Keys",
                        name,
                        workspace,
                        target_type,
                        target,
                        _asset_inventory_status(asset),
                    ),
                )
    return [
        named_values[key] for key in sorted(named_values)
    ] + [
        subscription_keys[key] for key in sorted(subscription_keys)
    ]


def _source_gateway_inventory_row(result):
    source = result.get("source") or {}
    network = result.get("networkConfiguration") or {}
    network_source = network.get("source") or {}
    destination = result.get("destination") or {}
    network_destination = network.get("destination") or {}
    source_name = source.get("name") or network_source.get("name")
    destination_name = destination.get("name") or network_destination.get("name")
    if not source_name:
        return None
    assessment = network.get("assessment") or {}
    status = "blocked" if assessment.get("status") == "blocked" else "ready"
    if status == "ready" and assessment.get("warnings"):
        status = "warn"
    return _inventory_row(
        "Gateway",
        source_name,
        None,
        "gateway" if destination_name else None,
        destination_name,
        status,
    )


def format_import_inventory(result):
    api_entries = []
    api_sources = []
    for asset in result.get("assets") or []:
        source = asset.get("source") or {}
        api_entries.append((_source_sort_key(source), _asset_inventory_rows(asset)))
        api_sources.append(source)
    for api in result.get("deferredApis") or []:
        api_entries.append(
            (_source_sort_key(api), _deferred_api_inventory_rows(api))
        )
        api_sources.append(api)
    for api in result.get("ignoredApis") or []:
        api_entries.append(
            (_source_sort_key(api), _ignored_api_inventory_rows(api))
        )
        api_sources.append(api)
    for api in result.get("suppressedAssets") or []:
        api_entries.append(
            (_source_sort_key(api), _suppressed_api_inventory_rows(api))
        )
        api_sources.append(api)

    rows = []
    gateway_row = _source_gateway_inventory_row(result)
    if gateway_row:
        rows.append(gateway_row)
    rows.extend(_identity_inventory_rows(result))
    rows.extend(_key_inventory_rows(result.get("assets") or []))
    rows.extend(_workspace_inventory_rows(api_sources))
    for _, api_rows in sorted(api_entries, key=lambda item: item[0]):
        rows.extend(api_rows)
    return rows


def _report_items(result):
    issues = []
    warnings = []
    network = result.get("networkConfiguration") or {}
    if network:
        assessment = network.get("assessment") or {}
        destination = (network.get("destination") or {}).get("name") or ""
        item = {
            "label": "network",
            "destination": destination,
        }
        if assessment.get("reasons"):
            issues.append({**item, "messages": assessment["reasons"]})
        if assessment.get("warnings"):
            warnings.append({**item, "messages": assessment["warnings"]})
    for asset in result.get("assets") or []:
        source = asset.get("source") or {}
        destination = asset.get("destination") or {}
        assessment = asset.get("assessment") or {}
        destination_name = destination.get("name") or ""
        provider_name = destination.get("providerName")
        configuration = asset.get("configuration") or {}
        provider_sync = (
            asset.get("assetType") == "model"
            and (
                configuration.get("providerModels") is not None
                or configuration.get("providerOnly")
            )
        )
        if provider_sync:
            destination_name = provider_name or destination_name
        elif provider_name:
            destination_name = f"{provider_name}/{destination_name}"
        item = {
            "label": (
                f"{source.get('name') or '(unnamed)'} "
                f"[{_asset_display_type(asset)}]"
            ),
            "destination": destination_name,
        }
        if assessment.get("reasons"):
            issues.append({**item, "messages": assessment["reasons"]})
        if assessment.get("warnings"):
            warnings.append({**item, "messages": assessment["warnings"]})
    for error in result.get("discoveryErrors") or []:
        item = {
            "label": f"{error.get('scope') or '(unknown)'} [discovery]",
            "destination": "",
            "messages": [error.get("message") or "Discovery failed."],
        }
        if error.get("required", True):
            issues.append(item)
        else:
            warnings.append(item)
    notice_types = {
        "identityPrerequisite",
        "relationshipNotice",
        "diagnosticNotice",
        "configurationNotice",
    }
    for action in result.get("actions") or []:
        if action.get("type") not in notice_types:
            continue
        assessment = action.get("assessment") or {}
        item = {
            "label": (
                f"{action.get('name') or '(unnamed)'} "
                f"[{action.get('type')}]"
            ),
            "destination": action.get("target") or "",
        }
        if assessment.get("reasons"):
            issues.append({**item, "messages": assessment["reasons"]})
        if assessment.get("warnings"):
            warnings.append({**item, "messages": assessment["warnings"]})
    return issues, warnings


def _format_report_section(title, items):
    if not items:
        return ""
    lines = [title]
    for item in items:
        lines.extend(["", item["label"]])
        if item["destination"]:
            lines.append(f"  Destination: {item['destination']}")
        lines.extend(f"  - {message}" for message in item["messages"])
    return "\n".join(lines)


def format_import_report(result):
    inventory_rows = format_import_inventory(result)
    issues, warnings = _report_items(result)
    status_counts = {}
    for row in inventory_rows:
        status = str(row["Status"]).casefold()
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = result.get("summary") or {}
    source_name = (
        (result.get("source") or {}).get("name")
        or ((result.get("networkConfiguration") or {}).get("source") or {}).get(
            "name"
        )
        or "APIM"
    )
    sections = [
        "DRY-RUN ASSESSMENT",
        "",
        f"{str(source_name).upper()} INVENTORY",
        _TableOutput().dump(inventory_rows).rstrip(),
    ]
    issue_section = _format_report_section(
        "ISSUES REQUIRING ACTION",
        issues,
    )
    warning_section = _format_report_section("WARNINGS", warnings)
    if issue_section:
        sections.extend(["", issue_section])
    if warning_section:
        sections.extend(["", warning_section])
    sections.extend(
        [
            "",
            "SUMMARY",
            (
                f"Ready: {status_counts.get('ready', 0)}  "
                f"Warn: {status_counts.get('warn', 0)}  "
                f"Blocked: {status_counts.get('blocked', 0)}  "
                f"Skipped: {status_counts.get('skipped', 0)}  "
                f"Unsupported: {status_counts.get('unsupported', 0)}  "
                f"Warnings: {sum(len(item['messages']) for item in warnings)}  "
                f"Importable: {'yes' if summary.get('canImport') else 'no'}"
            ),
        ]
    )
    return "\n".join(sections)


def _use_human_report(cmd):
    cli_ctx = getattr(cmd, "cli_ctx", None)
    if cli_ctx is None or not hasattr(cli_ctx, "invocation"):
        return False
    safe_params = set((getattr(cli_ctx, "data", None) or {}).get("safe_params", []))
    return not safe_params.intersection({"--output", "-o", "--query"})


def import_from_apim(
    cmd,
    name,
    resource_group_name,
    source_apim_id,
    include=None,
    conflict_policy="fail",
    mapping_file=None,
    dry_run=False,
    yes=False,
    no_wait=False,
):
    if not dry_run and not yes:
        raise AzCLIError(
            "APIM import changes the destination AI Gateway. Specify --yes "
            "to execute the import, or use --dry-run to review the action graph."
        )
    source_parts = _parse_apim_id(source_apim_id)
    source_apim_id = (
        f"/subscriptions/{source_parts['subscription']}"
        f"/resourceGroups/{source_parts['resource_group']}"
        "/providers/Microsoft.ApiManagement/service/"
        f"{source_parts['name']}"
    )
    mapping = _read_mapping(mapping_file)
    destination_subscription = get_subscription_id(cmd.cli_ctx)
    destination_id = _gateway_path(
        destination_subscription,
        resource_group_name,
        name,
    )
    if source_apim_id.casefold() == destination_id.casefold():
        raise InvalidArgumentValueError(
            "The source APIM service and destination AI Gateway must differ."
        )

    logger.warning("Discovering assets in source APIM '%s'...", source_parts["name"])
    discovered = _discover_source(cmd, source_apim_id)
    logger.warning("Checking destination AI Gateway '%s'...", name)
    destination = _destination_inventory(cmd, destination_id)
    logger.warning("Assessing network configuration compatibility...")
    network = _assess_network(
        discovered["source"],
        destination["resource"],
        mapping.get("network") or {},
    )
    selected_types = set(include or ["models", "mcp-servers"])
    singular = {"models": "model", "mcp-servers": "mcpServer"}
    selected = {singular[value] for value in selected_types}
    logger.warning(
        "Assessing import compatibility for %d discovered assets...",
        len(discovered["assets"]),
    )
    classified_records = [
        (
            record,
            _classify(
                record,
                _effective_url(record, discovered["source"]),
            ),
        )
        for record in discovered["assets"]
    ]
    candidate_records = [
        (record, classification)
        for record, classification in classified_records
        if classification["disposition"] == "candidate"
    ]
    deferred_assets = [
        {**record["source"], **classification}
        for record, classification in classified_records
        if classification["disposition"] == "deferred"
    ]
    ignored_assets = [
        {**record["source"], **classification}
        for record, classification in classified_records
        if classification["disposition"] == "ignored"
    ]
    assets = [
        _inventory_asset(
            record,
            discovered["source"],
            destination,
            mapping,
            conflict_policy,
            discovered["errors"],
            cmd,
            destination_id,
            classification,
        )
        for record, classification in candidate_records
    ]
    discovered_total = len(candidate_records)
    assets = [
        asset for asset in assets if asset["assetType"] in selected
    ]
    summary = _summary(
        assets,
        discovered["errors"],
        discovered_total,
    )
    summary["networkStatus"] = network["assessment"]["status"]
    summary["suppressedMcpBackingApiCount"] = len(
        discovered.get("suppressedAssets") or []
    )
    summary["ignoredApiCount"] = len(ignored_assets)
    summary["totalSourceApiCount"] = discovered.get(
        "sourceApiCount",
        (
            discovered_total
            + len(deferred_assets)
            + len(ignored_assets)
            + summary["suppressedMcpBackingApiCount"]
        ),
    )
    summary["candidateApiCount"] = discovered_total
    summary["deferredApiCount"] = len(deferred_assets)
    summary["suppressedDependencyCount"] = summary[
        "suppressedMcpBackingApiCount"
    ]
    selected_deferred_assets = (
        deferred_assets if "model" in selected else []
    )
    actions = build_import_actions(
        network,
        assets,
        selected_deferred_assets,
        discovered["errors"],
    )
    graph_blocked = any(
        action["assessment"]["status"] == "blocked"
        for action in actions
    )
    summary["canImport"] = (
        not graph_blocked
        and not any(
            error.get("required", True)
            for error in discovered["errors"]
        )
        and summary["blocked"] == 0
    )
    result = {
        "dryRun": dry_run,
        "source": discovered["source"],
        "destination": destination["resource"],
        "summary": summary,
        "networkConfiguration": network,
        "assets": sanitize_assets_for_output(assets),
        "actions": actions,
        "deferredApis": deferred_assets,
        "ignoredApis": ignored_assets,
        "suppressedAssets": discovered.get("suppressedAssets") or [],
        "discoveryErrors": discovered["errors"],
    }
    if dry_run:
        logger.warning("Dry-run assessment complete.")
    else:
        if no_wait and any(action["dependsOn"] for action in actions):
            raise InvalidArgumentValueError(
                "--no-wait is not supported for APIM import because the "
                "ordered action graph must complete prerequisites before "
                "dependent writes."
            )
        logger.warning("Executing APIM import action graph...")
        execution = execute_import_actions(
            cmd,
            name,
            resource_group_name,
            actions,
            assets,
        )
        result["actions"] = execution["actions"]
        result["execution"] = {
            **execution["summary"],
            "completed": execution["completed"],
        }
        logger.warning("APIM import execution complete.")
    if dry_run and _use_human_report(cmd):
        print(format_import_report(result), flush=True)
        set_output_format(cmd.cli_ctx, "none")
    return result
