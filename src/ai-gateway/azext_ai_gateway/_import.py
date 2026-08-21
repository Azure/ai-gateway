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
    urlparse,
    urlunparse,
)

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
from azext_ai_gateway._model_provider import _discover_custom_models
from azext_ai_gateway._policy_translation import summarize_policy

DEFAULT_WORKSPACE = "default"
APIM_ID_PATTERN = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/"
    r"resourceGroups/(?P<resource_group>[^/]+)/providers/"
    r"Microsoft\.ApiManagement/service/(?P<name>[^/]+)/?$",
    re.IGNORECASE,
)
NON_REST_API_TYPES = {
    "graphql",
    "grpc",
    "soap",
    "websocket",
}
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
MODEL_POLICY_STATEMENTS = {
    "azure-openai-token-limit",
    "llm-content-safety",
    "llm-token-limit",
}
SENSITIVE_PROPERTY_NAMES = {
    "certificate",
    "clientcertificate",
    "clientsecret",
    "key",
    "password",
    "secret",
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
    "agents": {"name"},
    "tools": {"name", "namespace", "transport"},
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
    for section in ("models", "agents", "tools"):
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


def _optional_list(cmd, url, errors, context):
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


def _policy_summary(policy_xml, scope, scope_type="api"):
    return summarize_policy(policy_xml, scope, scope_type)


def _credential_summary(credentials):
    credentials = credentials or {}
    authorization = credentials.get("authorization") or {}
    return {
        "hasCredentials": bool(credentials),
        "headerNames": sorted((credentials.get("header") or {}).keys()),
        "queryParameterNames": sorted((credentials.get("query") or {}).keys()),
        "authorizationScheme": authorization.get("scheme"),
    }


def _safe_url(value):
    if not value:
        return value
    parsed = urlparse(value)
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
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
    if isinstance(value, str) and value.casefold().startswith(
        ("http://", "https://")
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
                )
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
            }
        )
    return discovered, scope_policy


def _exclude_mcp_backing_apis(assets):
    backing_api_ids = {
        re.sub(
            r"/operations/[^/]+/?$",
            "",
            operation_id,
            flags=re.IGNORECASE,
        ).casefold()
        for asset in assets
        if str(asset["source"].get("apiType") or "").casefold() == "mcp"
        for tool in asset.get("tools") or []
        if (
            isinstance((operation_id := tool.get("operationId")), str)
            and "/apis/" in operation_id.casefold()
            and "/operations/" in operation_id.casefold()
        )
    }
    included = []
    suppressed = []
    for asset in assets:
        if asset["source"]["id"].casefold() in backing_api_ids:
            suppressed.append(asset["source"])
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
    subscriptions = _optional_list(
        cmd,
        f"{source_apim_id}/subscriptions",
        errors,
        f"{source_apim_id}/subscriptions",
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
            "candidateCount": len(candidates),
        }


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
    root_assets, _ = _discover_scope(
        cmd,
        source_apim_id,
        None,
        source_policy,
        errors,
        scope_policy=source_policy,
    )
    assets = list(root_assets)
    logger.warning("Checking APIM workspaces...")
    workspaces = _optional_list(
        cmd,
        f"{source_apim_id}/workspaces",
        errors,
        f"{source_apim_id}/workspaces",
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
        )
        assets.extend(workspace_assets)
    assets, suppressed_assets = _exclude_mcp_backing_apis(assets)
    _attach_mcp_subscription_credentials(
        cmd,
        source_apim_id,
        assets,
        errors,
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
        },
        "assets": assets,
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


def _classify(record, effective_url):
    properties = record["api"].get("properties") or {}
    api_type = str(
        properties.get("type") or properties.get("apiType") or ""
    ).casefold()
    parsed = urlparse(effective_url or "")
    host = parsed.hostname or ""
    path = parsed.path.casefold()
    identity = " ".join(
        str(value or "")
        for value in [
            record["api"].get("name"),
            properties.get("displayName"),
            properties.get("path"),
        ]
    ).casefold()

    if api_type == "mcp":
        return "tool", "mcp"
    if (
        host.endswith(".agents.ai.azure.com")
        or "/agents/" in path
        or "/assistants/" in path
        or (
            "agent" in identity
            and host.endswith(".services.ai.azure.com")
            and "/api/projects/" in path
        )
    ):
        return "agent", "agent"
    backend_resource_ids = [
        str((backend.get("properties") or {}).get("resourceId") or "").casefold()
        for backend in record["backends"]
    ]
    policy_statements = {
        str(statement).casefold()
        for statement in (record.get("policy") or {}).get("statements", [])
    }
    if (
        any(host.endswith(suffix) for suffix in MODEL_HOST_SUFFIXES)
        or policy_statements & MODEL_POLICY_STATEMENTS
        or (
            host.endswith(".services.ai.azure.com")
            and ("/models" in path or "/openai" in path)
        )
        or any(
            "microsoft.cognitiveservices/accounts" in resource_id
            or "microsoft.machinelearningservices/workspaces" in resource_id
            for resource_id in backend_resource_ids
        )
    ):
        return "model", "model"
    if api_type in NON_REST_API_TYPES:
        return "tool", "unsupported"
    return "tool", "openApi"


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
    if (
        host == "generativelanguage.googleapis.com"
        and "/openai/" not in f"{path} {paths}"
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
    if "/responses" in paths:
        return "ResponsesApi"
    if "/messages" in paths or "anthropic" in host:
        return "AnthropicMessages"
    return "OpenAIChatCompletions"


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


def _policy_assessment(record):
    effective_policies = [record["policy"], *record["inheritedPolicies"]]
    scoped_policies = [
        *record.get("operationPolicies", []),
        *record.get("productPolicies", []),
    ]
    policies = [*effective_policies, *scoped_policies]
    unsupported = sorted(
        {
            statement
            for policy in effective_policies
            for statement in policy["unsupportedStatements"]
        }
    )
    parse_errors = [
        {"scope": policy["scope"], "message": policy["parseError"]}
        for policy in effective_policies
        if policy["parseError"]
    ]
    translated = [
        translated_policy
        for policy in effective_policies
        for translated_policy in policy["translatedPolicies"]
    ]
    translation_warnings = [
        f"{policy['scope']}: {warning}"
        for policy in effective_policies
        for warning in policy["translationWarnings"]
    ]
    translation_warnings.extend(
        (
            f"{policy['scope']}: translated {policy['scopeType']} policies are "
            "replicated onto each destination asset; shared counters and "
            "inheritance boundaries may change."
        )
        for policy in effective_policies
        if policy["scopeType"] in {"service", "workspace"}
        and policy["translatedPolicies"]
    )
    scoped_policy_warnings = [
        (
            f"{policy['scopeType'].capitalize()} policy '{policy['scope']}' "
            "cannot preserve its scope as a destination inline policy and "
            "will not be imported."
        )
        for policy in scoped_policies
        if policy["present"]
    ]
    translation_warnings.extend(scoped_policy_warnings)
    return (
        policies,
        unsupported,
        parse_errors,
        translated,
        translation_warnings,
    )


def _base_assessment(record, errors):
    (
        policies,
        unsupported,
        parse_errors,
        destination_policies,
        translation_warnings,
    ) = _policy_assessment(record)
    reasons = []
    warnings = list(translation_warnings)
    if unsupported:
        warnings.append(
            "Unsupported APIM policy statements will not be imported: "
            + ", ".join(unsupported)
        )
    if parse_errors:
        reasons.append("One or more APIM policies could not be parsed.")
    api_id = record["source"]["id"].casefold()
    api_scope = api_id.rsplit("/apis/", 1)[0]
    inherited_scopes = {
        policy["scope"].casefold() for policy in record["inheritedPolicies"]
    }
    failed_scopes = []
    for error in errors:
        error_scope = error["scope"].casefold()
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
        ):
            failed_scopes.append(error["scope"])
    if failed_scopes:
        reasons.append(
            "Discovery was incomplete for: " + ", ".join(failed_scopes)
        )
    return reasons, warnings, policies, destination_policies


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


def _assess_model(
    record,
    destination,
    mapping,
    effective_url,
    errors,
    cmd=None,
    destination_id="",
):
    reasons, warnings, policies, destination_policies = _base_assessment(
        record,
        errors,
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
            "No destination model provider could be resolved; provide "
            "providerName in the mapping file."
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
    if not model_name and provider_kind.casefold() == "custom":
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
        provider_models = discovery["models"]
        provider_only = not provider_models
        if not provider_models:
            if (backend_api_key or {}).get("error"):
                warnings.append(
                    "The source APIM backend credential could not be resolved: "
                    f"{backend_api_key['error']}"
                )
            warnings.append(
                f"Models could not be discovered from custom provider "
                f"'{provider_name}'. Import will continue with the provider "
                "only; models can be synchronized later. Discovery error: "
                f"{discovery['error']}"
            )
    elif not model_name:
        if provider_kind.casefold() != "custom":
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


def _assess_agent(record, mapping, effective_url, errors):
    reasons, warnings, policies, destination_policies = _base_assessment(
        record,
        errors,
    )
    reasons.append(
        "The AI Gateway control-plane contract does not define an agent resource."
    )
    destination_name = mapping.get("name") or record["source"]["name"]
    return (
        destination_name,
        {
            "name": destination_name,
            "resourceType": None,
        },
        {
            "endpointUrl": _safe_url(effective_url),
            "backend": _backend_summary(_resolved_backend(record)),
            "operations": record["operations"],
            "products": record.get("products", []),
            "policies": policies,
            "destinationPolicies": destination_policies,
        },
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
    )
    subscription_credential = record.get("subscriptionCredential") or {}
    if subtype == "unsupported":
        reasons.append(
            f"APIM API type '{record['source']['apiType']}' is not supported "
            "as an AI Gateway tool endpoint."
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
    if subtype == "openApi" and not record["operations"]:
        reasons.append("The REST API has no operations to include in an OpenAPI spec.")
    if (
        record["source"]["subscriptionRequired"]
        and not (record["api"].get("properties") or {}).get("serviceUrl")
        and not backend
    ):
        if (
            subtype == "mcp"
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
        "kind": "mcp" if subtype == "mcp" else "openApi",
        "required": True,
    }
    if subtype == "mcp":
        source_transport = (
            (
                (record["api"].get("properties") or {}).get("mcpProperties")
                or {}
            ).get("transportType")
        )
        if source_transport == "streamable":
            source_transport = "streamableHttp"
        transport = (
            mapping.get("transport")
            or source_transport
            or "streamableHttp"
        )
        if transport not in {"sse", "streamableHttp"}:
            reasons.append(f"MCP transport '{transport}' is not supported.")
        endpoint["mcp"] = {
            "url": _safe_url(effective_url),
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
    else:
        endpoint["openApi"] = {
            "specSource": {
                "type": "inline",
                "operationCount": len(record["operations"]),
            }
        }
        endpoint["serverUrl"] = _safe_url(effective_url)
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
    if asset_type == "agent" or not conflict:
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
):
    effective_url = _effective_url(record, source)
    asset_type, subtype = _classify(record, effective_url)
    model_mapping = _mapping_for(mapping, "model", record["source"])
    if model_mapping:
        asset_type, subtype = "model", "model"
    elif asset_type == "tool" and subtype == "openApi":
        operation_paths = " ".join(
            operation.get("urlTemplate") or ""
            for operation in record["operations"]
        ).casefold()
        custom_provider = _provider_for(
            None,
            effective_url,
            destination["providers"],
            {},
        )
        if custom_provider and any(
            path in operation_paths
            for path in (
                "/chat/completions",
                "/completions",
                "/embeddings",
                "/messages",
                "/responses",
            )
        ):
            asset_type, subtype = "model", "model"
    asset_mapping = _mapping_for(mapping, asset_type, record["source"])
    if not isinstance(asset_mapping, dict):
        raise InvalidArgumentValueError(
            f"Mapping for '{record['source']['name']}' must be a JSON object."
        )
    if asset_type == "model":
        assessed = _assess_model(
            record,
            destination,
            asset_mapping,
            effective_url,
            errors,
            cmd,
            destination_id,
        )
    elif asset_type == "agent":
        assessed = _assess_agent(
            record,
            asset_mapping,
            effective_url,
            errors,
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
    if (
        asset_type == "model"
        and configuration.get("deployment") is None
    ):
        subtype = "provider"
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
    return {
        "order": 2,
        "assetType": asset_type,
        "assetSubtype": subtype,
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
            "agents": by_type.get("agent", 0),
            "tools": by_type.get("tool", 0),
        },
        "discoveryComplete": not discovery_errors,
        "discoveryErrorCount": len(discovery_errors),
    }


def format_import_table(result):
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
        if asset.get("assetSubtype") == "provider":
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
                "Status": "error",
            }
        )
    return rows


def _asset_display_type(asset):
    if asset.get("assetSubtype") == "provider":
        return "provider"
    if asset.get("assetType") != "tool":
        return asset.get("assetType") or "asset"
    subtype = asset.get("assetSubtype")
    if subtype == "openApi":
        return "openapi"
    return subtype or "tool"


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
        if asset.get("assetSubtype") == "provider":
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
        issues.append(
            {
                "label": f"{error.get('scope') or '(unknown)'} [discovery]",
                "destination": "",
                "messages": [error.get("message") or "Discovery failed."],
            }
        )
    return issues, warnings


def _models_to_import(result):
    providers = []
    for asset in result.get("assets") or []:
        configuration = asset.get("configuration") or {}
        models = configuration.get("providerModels")
        if not models:
            continue
        provider_name = (
            (asset.get("destination") or {}).get("providerName")
            or "(unknown)"
        )
        groups = {}
        for model in models:
            endpoints = model.get("supportedEndpoints") or []
            api_names = set()
            if "/v1/messages" in endpoints:
                api_names.add("Anthropic API")
            if any(endpoint != "/v1/messages" for endpoint in endpoints):
                api_names.add("OpenAI-compatible API")
            if not api_names:
                api_names.add("Unknown API")
            for api_name in api_names:
                groups.setdefault(api_name, []).append(model["modelName"])
        providers.append(
            {
                "providerName": provider_name,
                "groups": {
                    api_name: sorted(model_names)
                    for api_name, model_names in sorted(groups.items())
                },
            }
        )
    return providers


def _format_models_to_import(providers):
    if not providers:
        return ""
    lines = ["MODELS TO IMPORT"]
    for provider in providers:
        lines.extend(["", f"{provider['providerName']} [custom provider]"])
        for api_name, model_names in provider["groups"].items():
            lines.append(
                f"  {api_name}: {len(model_names)} model(s)"
            )
            lines.extend(f"    - {model_name}" for model_name in model_names)
    return "\n".join(lines)


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
    plan_rows = [
        {
            "Type": row["Type"],
            "Source": row["Source"],
            "Workspace": row["Workspace"],
            "Destination": row["Destination"],
            "Status": row["Status"],
        }
        for row in format_import_table(result)
    ]
    issues, warnings = _report_items(result)
    status_counts = {}
    for row in plan_rows:
        status = str(row["Status"] or "unknown").casefold()
        status_counts[status] = status_counts.get(status, 0) + 1
    summary = result.get("summary") or {}
    sections = [
        "DRY-RUN ASSESSMENT",
        "",
        "IMPORT PLAN",
        _TableOutput().dump(plan_rows).rstrip(),
    ]
    issue_section = _format_report_section(
        "ISSUES REQUIRING ACTION",
        issues,
    )
    model_section = _format_models_to_import(_models_to_import(result))
    warning_section = _format_report_section("WARNINGS", warnings)
    if model_section:
        sections.extend(["", model_section])
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
                f"Blocked: {status_counts.get('blocked', 0)}  "
                f"Skipped: {status_counts.get('skipped', 0)}  "
                f"Errors: {status_counts.get('error', 0)}  "
                f"Warnings: {sum(len(item['messages']) for item in warnings)}  "
                f"Importable: {'yes' if summary.get('canImport') else 'no'}"
            ),
        ]
    )
    suppressed_count = summary.get("suppressedMcpBackingApiCount", 0)
    if suppressed_count:
        sections.append(f"MCP backing APIs omitted: {suppressed_count}")
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
    no_wait=False,
):
    del no_wait
    if not dry_run:
        raise AzCLIError(
            "Import execution is not implemented yet.",
            recommendation=(
                "Run the command with --dry-run to discover source assets and "
                "review their compatibility."
            ),
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
    selected_types = set(include or ["models", "agents", "tools"])
    singular = {"models": "model", "agents": "agent", "tools": "tool"}
    selected = {singular[value] for value in selected_types}
    logger.warning(
        "Assessing import compatibility for %d discovered assets...",
        len(discovered["assets"]),
    )
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
        )
        for record in discovered["assets"]
    ]
    discovered_total = len(assets)
    assets = [
        asset for asset in assets if asset["assetType"] in selected
    ]
    logger.warning("Dry-run assessment complete.")
    summary = _summary(
        assets,
        discovered["errors"],
        discovered_total,
    )
    summary["networkStatus"] = network["assessment"]["status"]
    summary["suppressedMcpBackingApiCount"] = len(
        discovered.get("suppressedAssets") or []
    )
    summary["canImport"] = (
        network["assessment"]["canImport"]
        and not discovered["errors"]
        and summary["blocked"] == 0
    )
    result = {
        "dryRun": True,
        "source": discovered["source"],
        "destination": destination["resource"],
        "summary": summary,
        "networkConfiguration": network,
        "assets": assets,
        "suppressedAssets": discovered.get("suppressedAssets") or [],
        "discoveryErrors": discovered["errors"],
    }
    if _use_human_report(cmd):
        print(format_import_report(result), flush=True)
        set_output_format(cmd.cli_ctx, "none")
    return result
