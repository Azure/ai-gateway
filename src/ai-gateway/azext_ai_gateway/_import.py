# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import re
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
from azure.cli.core.commands.client_factory import get_subscription_id
from knack.log import get_logger

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
)
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
logger = get_logger(__name__)
MODEL_HOST_SUFFIXES = (
    ".openai.azure.com",
    ".models.ai.azure.com",
    ".models.inference.ai.azure.com",
    "api.anthropic.com",
    "api.openai.com",
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
    invalid_sections = set(mapping) - {"models", "agents", "tools"}
    if invalid_sections:
        raise InvalidArgumentValueError(
            "--mapping-file contains unsupported sections: "
            + ", ".join(sorted(invalid_sections))
        )
    for section, entries in mapping.items():
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
            }
        )
    return discovered, scope_policy


def _discover_source(cmd, source_apim_id):
    errors = []
    logger.warning("Checking source APIM resource and service policy...")
    source = _response_json(_request(cmd, "GET", source_apim_id))
    if str((source.get("sku") or {}).get("name", "")).casefold() == "aigateway":
        raise InvalidArgumentValueError(
            "--source-apim-id must identify a classic API Management service, "
            "not an AI Gateway."
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
    properties = source.get("properties") or {}
    return {
        "source": {
            "id": source.get("id") or source_apim_id,
            "name": source.get("name"),
            "location": source.get("location"),
            "sku": (source.get("sku") or {}).get("name"),
            "gatewayUrl": _safe_url(properties.get("gatewayUrl")),
        },
        "assets": assets,
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
        },
        "providers": providers,
        "modelKeys": model_keys,
        "unscopedModelNames": unscoped_model_names,
        "toolNames": {
            str(tool.get("name", "")).casefold() for tool in tools
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


def _provider_for(deployment_id, providers, mapping):
    if mapping.get("providerName"):
        return mapping["providerName"]
    if not deployment_id:
        return None
    deployment_id = deployment_id.casefold()
    matches = []
    for provider in providers:
        properties = provider.get("properties") or {}
        resource_ids = (properties.get("foundry") or {}).get("resourceIds") or []
        if any(
            deployment_id.startswith(resource_id.rstrip("/").casefold())
            for resource_id in resource_ids
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


def _assess_model(record, destination, mapping, effective_url, errors):
    reasons, warnings, policies, destination_policies = _base_assessment(
        record,
        errors,
    )
    backend = _resolved_backend(record)
    deployment_id = _deployment_id(record, mapping)
    provider_name = _provider_for(
        deployment_id,
        destination["providers"],
        mapping,
    )
    model_name = _model_name(deployment_id, mapping)
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
    if not deployment_id:
        reasons.append(
            "No deployment resource ID was found; provide one in the mapping file."
        )
    if not provider_name:
        reasons.append(
            "No destination model provider matches the deployment resource ID."
        )
    elif not any(
        str(provider.get("name", "")).casefold() == provider_name.casefold()
        for provider in destination["providers"]
    ):
        reasons.append(
            f"Destination model provider '{provider_name}' does not exist."
        )
    if not model_name:
        reasons.append(
            "No deployment model name was found; provide one in the mapping file."
        )
    destination_name = mapping.get("name") or record["source"]["name"]
    api_format = mapping.get("apiFormat") or _model_api_format(record)
    if api_format not in {
        "AnthropicMessages",
        "OpenAIChatCompletions",
        "ResponsesApi",
    }:
        reasons.append(f"Model API format '{api_format}' is not supported.")
    configuration = {
        "apiFormat": api_format,
        "deployment": {
            "resourceId": deployment_id,
            "modelName": model_name,
            "modelVersion": mapping.get("modelVersion"),
        },
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
        reasons.append(
            "The fallback APIM gateway endpoint requires a subscription key."
        )
    destination_name = mapping.get("name") or record["source"]["name"]
    endpoint = {
        "namespace": mapping.get("namespace") or destination_name,
        "kind": "mcp" if subtype == "mcp" else "openApi",
        "required": True,
    }
    if subtype == "mcp":
        transport = mapping.get("transport") or "streamableHttp"
        if transport not in {"sse", "streamableHttp"}:
            reasons.append(f"MCP transport '{transport}' is not supported.")
        endpoint["mcp"] = {
            "url": _safe_url(effective_url),
            "transport": transport,
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
):
    effective_url = _effective_url(record, source)
    asset_type, subtype = _classify(record, effective_url)
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
        "assetType": asset_type,
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
    for asset in result.get("assets") or []:
        source = asset.get("source") or {}
        destination = asset.get("destination") or {}
        assessment = asset.get("assessment") or {}
        destination_name = destination.get("name") or ""
        provider_name = destination.get("providerName")
        if provider_name:
            destination_name = f"{provider_name}/{destination_name}"
        rows.append(
            {
                "Type": asset.get("assetType"),
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
        )
        for record in discovered["assets"]
    ]
    discovered_total = len(assets)
    assets = [
        asset for asset in assets if asset["assetType"] in selected
    ]
    logger.warning("Dry-run assessment complete.")
    return {
        "dryRun": True,
        "source": discovered["source"],
        "destination": destination["resource"],
        "summary": _summary(
            assets,
            discovered["errors"],
            discovered_total,
        ),
        "assets": assets,
        "discoveryErrors": discovered["errors"],
    }
