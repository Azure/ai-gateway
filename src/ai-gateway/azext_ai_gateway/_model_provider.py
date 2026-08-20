# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import hashlib
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from urllib.parse import quote, unquote, urlsplit

import requests
from azure.cli.core._profile import Profile
from azure.cli.core.azclierror import (
    AzCLIError,
    HTTPError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import should_disable_connection_verify
from knack.log import get_logger
from knack.prompting import NoTTYException, prompt_pass

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
)

DEFAULT_WORKSPACE = "default"
FOUNDRY_API_VERSION = "2024-10-01"
ANTHROPIC_API_VERSION = "2023-06-01"
CUSTOM_DISCOVERY_TIMEOUT_SECONDS = 15
AI_GATEWAY_PORTAL_ORIGIN = "https://ai.gateway.azure.com"
CORS_PROXY_HOSTS = {
    "management.azure.com": "apimanagement-cors-proxy-prd.azure-api.net",
    "api-dogfood.resources.windows-int.net": (
        "apimanagement-cors-proxy-df.azure-api.net"
    ),
    "management.usgovcloudapi.net": (
        "apimanagement-cors-proxy-ff.azure-api.us"
    ),
    "management.chinacloudapi.cn": (
        "apimanagement-cors-proxy-mc.azure-api.cn"
    ),
}
CAPABILITY_ENDPOINTS = (
    ("chatCompletion", "/openai/v1/chat/completions"),
    ("responses", "/openai/v1/responses"),
    ("completion", "/openai/v1/completions"),
    ("embeddings", "/openai/v1/embeddings"),
    ("imageGenerations", "/openai/v1/images/generations"),
)
logger = get_logger(__name__)


def format_model_provider_list_table(providers):
    rows = []
    for provider in providers:
        properties = provider.get("properties") or {}
        provider_type = properties.get("kind") or ""
        config = properties.get(str(provider_type).casefold()) or {}
        rows.append(
            {
                "Name": provider.get("name") or "",
                "Provider type": provider_type,
                "Base endpoint": config.get("endpoint") or "",
                "Auth": (config.get("authentication") or {}).get("kind") or "",
            }
        )
    return rows


def _redact_provider_secrets(provider):
    if not provider:
        return provider
    redacted = deepcopy(provider)
    properties = redacted.get("properties") or {}
    for config_name in ["foundry", "custom"]:
        api_key = (
            ((properties.get(config_name) or {}).get("authentication") or {})
            .get("apiKey")
        )
        if api_key:
            api_key.pop("value", None)
    return redacted


def _providers_path(
    subscription_id,
    resource_group_name,
    resource_name,
    workspace_name,
    provider_name=None,
):
    path = (
        f"{_gateway_path(subscription_id, resource_group_name, resource_name)}"
        f"/workspaces/{quote(workspace_name, safe='')}/modelProviders"
    )
    if provider_name is not None:
        path += f"/{quote(provider_name, safe='')}"
    return path


def _raise_provider_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(
            f"Model provider '{name}' was not found."
        ) from None
    raise error


def _list_all(cmd, url):
    providers = []
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
        providers.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return [_redact_provider_secrets(provider) for provider in providers]


def _list_foundry_resources(cmd, url):
    resources = []
    include_api_version = True
    while url:
        page = _response_json(
            _request(
                cmd,
                "GET",
                url,
                include_api_version=include_api_version,
                api_version=FOUNDRY_API_VERSION,
            )
        )
        resources.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return resources


def _resource_name(resource):
    return str(resource.get("name") or "").rsplit("/", 1)[-1]


def _normalize_arm_name(name):
    normalized = re.sub(r"[^a-z0-9-]", "-", str(name).lower())
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def _model_details(deployment):
    return ((deployment.get("properties") or {}).get("model") or {})


def _matching_account_capabilities(deployment, account_models):
    deployment_model = _model_details(deployment)
    model_format = str(deployment_model.get("format") or "").strip().casefold()
    model_name = str(deployment_model.get("name") or "").strip().casefold()
    model_version = str(deployment_model.get("version") or "").strip().casefold()
    matches = [
        model
        for model in account_models
        if str(model.get("format") or "").strip().casefold() == model_format
        and str(model.get("name") or "").strip().casefold() == model_name
    ]
    if model_version:
        version_match = next(
            (
                model
                for model in matches
                if str(model.get("version") or "").strip().casefold()
                == model_version
            ),
            None,
        )
        if version_match:
            return version_match.get("capabilities")
    return matches[0].get("capabilities") if matches else None


def _supported_endpoints(model_format, capabilities):
    if str(model_format or "").strip().casefold() == "anthropic":
        return ["/anthropic/v1/messages"]
    endpoints = [
        endpoint
        for capability, endpoint in CAPABILITY_ENDPOINTS
        if str((capabilities or {}).get(capability, "")).strip().casefold()
        == "true"
    ]
    if endpoints:
        return endpoints
    has_capability_info = any(
        str(value or "").strip().casefold() == "true"
        for value in (capabilities or {}).values()
    )
    return [] if has_capability_info else ["/openai/v1/chat/completions"]


def _sync_model_properties(deployment, capabilities):
    deployment_name = _resource_name(deployment)
    model = _model_details(deployment)
    deployment_details = {
        "resourceId": deployment.get("id"),
        "modelName": deployment_name,
    }
    if model.get("version"):
        deployment_details["modelVersion"] = model["version"]
    return {
        "displayName": deployment_name,
        "supportedEndpoints": _supported_endpoints(
            model.get("format"),
            capabilities,
        ),
        "deployment": deployment_details,
    }


def _provider_models_path(provider_path):
    return f"{provider_path}/models"


def _all_models_path(provider_path):
    return provider_path.rsplit("/modelProviders/", 1)[0] + "/models"


def _build_sync_changes(
    provider_models,
    all_models,
    remote_models,
    delete_missing,
    missing_reason,
):
    provider_model_names = {
        str(model.get("name") or "") for model in provider_models
    }
    gateway_model_names = {
        _normalize_arm_name(model.get("name") or "") for model in all_models
    }
    remote_names = {model["name"] for model in remote_models}

    changes = []
    reserved_names = set(gateway_model_names)
    for remote_model in remote_models:
        name = remote_model["name"]
        if name in provider_model_names:
            continue
        if name in reserved_names:
            changes.append(
                {
                    "action": "skip",
                    "name": remote_model["displayName"],
                    "status": "conflict",
                    "reason": (
                        "A model with this name already exists in the gateway."
                    ),
                }
            )
            continue
        reserved_names.add(name)
        changes.append(
            {
                "action": "create",
                "name": name,
                "status": "planned",
                "properties": remote_model["properties"],
            }
        )

    for model in provider_models:
        name = str(model.get("name") or "")
        if name in remote_names:
            continue
        changes.append(
            {
                "action": "delete" if delete_missing else "skip",
                "name": name,
                "status": "planned" if delete_missing else "stale",
                "reason": missing_reason
                if delete_missing
                else "Use --delete-missing to remove this stale model.",
                "id": model.get("id"),
            }
        )
    return changes


def _foundry_sync_plan(cmd, provider, provider_path, delete_missing):
    foundry = (provider.get("properties") or {}).get("foundry") or {}
    resource_ids = foundry.get("resourceIds") or []
    if not resource_ids:
        raise InvalidArgumentValueError(
            "The Foundry model provider has no resource IDs to synchronize."
        )

    deployments = []
    for resource_id in resource_ids:
        account_deployments = _list_foundry_resources(
            cmd,
            f"{resource_id.rstrip('/')}/deployments",
        )
        account_models = []
        if any(
            (deployment.get("properties") or {}).get("capabilities") is None
            for deployment in account_deployments
        ):
            account_models = _list_foundry_resources(
                cmd,
                f"{resource_id.rstrip('/')}/models",
            )
        for deployment in account_deployments:
            capabilities = (deployment.get("properties") or {}).get(
                "capabilities"
            )
            if capabilities is None:
                capabilities = _matching_account_capabilities(
                    deployment,
                    account_models,
                )
            deployments.append((deployment, capabilities))

    provider_models = _list_all(cmd, _provider_models_path(provider_path))
    all_models = _list_all(cmd, _all_models_path(provider_path))
    remote_models = [
        {
            "name": _normalize_arm_name(_resource_name(deployment)),
            "displayName": _resource_name(deployment),
            "properties": _sync_model_properties(deployment, capabilities),
        }
        for deployment, capabilities in deployments
    ]
    return _build_sync_changes(
        provider_models,
        all_models,
        remote_models,
        delete_missing,
        "Foundry deployment no longer exists.",
    )


def _custom_models_url(endpoint):
    return f"{str(endpoint or '').strip().rstrip('/')}/v1/models"


def _validate_provider_endpoint(endpoint):
    endpoint = str(endpoint or "").strip()
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in endpoint
    ):
        raise InvalidArgumentValueError(
            "The model provider endpoint cannot contain control characters."
        )
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidArgumentValueError(
            "The model provider endpoint must be an absolute HTTPS URL without "
            "embedded credentials, a query string, or a fragment."
        )
    try:
        parsed.port
    except ValueError as error:
        raise InvalidArgumentValueError(
            "The model provider endpoint contains an invalid port."
        ) from error
    return endpoint.rstrip("/")


def _parse_custom_model_ids(response, request_url=""):
    if not response.ok:
        provider_code = None
        try:
            error_payload = response.json()
            provider_error = (
                error_payload.get("error")
                if isinstance(error_payload, dict)
                else None
            )
            if isinstance(provider_error, dict):
                provider_code = provider_error.get("code")
        except requests.exceptions.JSONDecodeError:
            pass
        error_suffix = (
            f" ({provider_code})"
            if isinstance(provider_code, str) and provider_code
            else ""
        )
        raise InvalidArgumentValueError(
            f"The provider's model-discovery request to {request_url} returned "
            f"HTTP {response.status_code}{error_suffix}. Check the endpoint "
            "URL and credentials."
        )
    try:
        payload = response.json()
    except requests.exceptions.JSONDecodeError as error:
        raise InvalidArgumentValueError(
            "Couldn't parse the response from the provider's /v1/models "
            "endpoint as JSON."
        ) from error
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise InvalidArgumentValueError(
            "Unexpected response from the provider's /v1/models endpoint. "
            "Is it OpenAI- or Anthropic-API-compatible?"
        )
    model_ids = sorted(
        {
            str(entry.get("id") or "").strip()
            for entry in data
            if isinstance(entry, dict) and str(entry.get("id") or "").strip()
        }
    )
    if not model_ids:
        raise InvalidArgumentValueError(
            "The provider returned no models from its /v1/models endpoint."
        )
    return model_ids


def _cors_proxy_context(cmd, provider_path):
    match = re.match(
        r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/"
        r"Microsoft\.ApiManagement/service/([^/]+)",
        provider_path,
        flags=re.IGNORECASE,
    )
    if cmd is None or match is None:
        return None
    subscription_id, resource_group, gateway_name = (
        unquote(value) for value in match.groups()
    )
    resource_manager = cmd.cli_ctx.cloud.endpoints.resource_manager.rstrip("/")
    resource_manager_host = resource_manager.split("://", 1)[-1].casefold()
    proxy_host = CORS_PROXY_HOSTS.get(
        resource_manager_host,
        CORS_PROXY_HOSTS["management.azure.com"],
    )
    token_type, token, _ = Profile(cmd.cli_ctx).get_raw_token(
        resource=resource_manager
    )[0]
    return {
        "url": f"https://{proxy_host}/send",
        "headers": {
            "Authorization": f"{token_type} {token}",
            "Origin": AI_GATEWAY_PORTAL_ORIGIN,
            "Referer": f"{AI_GATEWAY_PORTAL_ORIGIN}/",
            "Ocp-Apim-Subscription": subscription_id,
            "Ocp-Apim-Resource-Group": resource_group,
            "Ocp-Apim-Service-Name": gateway_name,
        },
    }


def _curl_get(url, headers):
    if any(
        "\r" in str(value) or "\n" in str(value)
        for item in headers.items()
        for value in item
    ):
        raise InvalidArgumentValueError(
            "Custom provider header names and values cannot contain newlines."
        )
    header_input = "".join(
        f"{name}: {value}\n" for name, value in headers.items()
    )
    try:
        result = subprocess.run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--max-time",
                str(CUSTOM_DISCOVERY_TIMEOUT_SECONDS),
                "--request",
                "GET",
                "--header",
                "@-",
                "--write-out",
                "\n%{http_code}",
                "--",
                url,
            ],
            input=header_input,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise InvalidArgumentValueError(
            "curl is required to discover models from a custom provider."
        ) from error
    if result.returncode != 0:
        raise requests.RequestException(
            result.stderr.strip() or "curl failed to reach the provider."
        )
    body, separator, status = result.stdout.rpartition("\n")
    if not separator or not status.isdigit():
        raise InvalidArgumentValueError(
            "curl returned an unexpected response while discovering models."
        )
    response = requests.Response()
    response.status_code = int(status)
    response._content = body.encode("utf-8")
    response.url = url
    return response


def _fetch_custom_model_ids(url, headers, proxy_context=None):
    request_options = {
        "timeout": CUSTOM_DISCOVERY_TIMEOUT_SECONDS,
        "verify": not should_disable_connection_verify(),
    }
    try:
        response = _curl_get(url, headers)
        return _parse_custom_model_ids(response, url)
    except (requests.RequestException, InvalidArgumentValueError) as direct_error:
        if not proxy_context:
            raise
        logger.debug(
            "Direct custom model discovery failed; retrying through the "
            "AI Gateway portal proxy: %s",
            direct_error,
        )
        proxy_headers = {
            **proxy_context["headers"],
            "Ocp-Apim-Url": url,
            "Ocp-Apim-Method": "GET",
            **{
                f"Ocp-Apim-Header-{name}": value
                for name, value in headers.items()
            },
        }
        response = requests.post(
            proxy_context["url"],
            headers=proxy_headers,
            **request_options,
        )
        return _parse_custom_model_ids(response, url)


def _discover_custom_models(
    provider,
    api_key_value=None,
    cmd=None,
    provider_path="",
):
    custom = (provider.get("properties") or {}).get("custom") or {}
    endpoint = custom.get("endpoint")
    if not endpoint:
        raise InvalidArgumentValueError(
            "The custom model provider has no endpoint to synchronize."
        )
    authentication = custom.get("authentication") or {}
    credentials = (
        authentication.get("apiKey")
        if authentication.get("kind") == "ApiKey"
        else authentication.get("header")
    ) or {}
    header_name = str(
        credentials.get("headerName") or credentials.get("name") or ""
    ).strip()
    api_key = (
        api_key_value
        if api_key_value is not None
        else credentials.get("value")
    )
    if not header_name or not api_key:
        raise InvalidArgumentValueError(
            "The custom model provider does not expose configured credentials. "
            "Update it with --api-key-header-name and --api-key-value before "
            "synchronizing."
        )
    api_key_bytes = str(api_key).encode("utf-8")
    logger.debug(
        "Custom provider credential: header=%s, length=%d, sha256=%s",
        header_name,
        len(api_key_bytes),
        hashlib.sha256(api_key_bytes).hexdigest(),
    )
    url = _custom_models_url(endpoint)
    attempts = (
        (
            "openai",
            {
                "Accept": "application/json",
                header_name: api_key,
            },
            "/v1/chat/completions",
        ),
        (
            "anthropic",
            {
                "Accept": "application/json",
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
            "/v1/messages",
        ),
    )
    proxy_context = _cors_proxy_context(cmd, provider_path)
    results = {}
    errors = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            name: executor.submit(
                _fetch_custom_model_ids,
                url,
                headers,
                proxy_context,
            )
            for name, headers, _ in attempts
        }
        for name, _, endpoint_path in attempts:
            try:
                results[name] = (futures[name].result(), endpoint_path)
            except (requests.RequestException, InvalidArgumentValueError) as error:
                errors.append(error)

    merged = {}
    for model_ids, endpoint_path in results.values():
        for model_id in model_ids:
            endpoints = merged.setdefault(model_id, [])
            if endpoint_path not in endpoints:
                endpoints.append(endpoint_path)
    if not merged:
        concrete_error = next(
            (
                error
                for error in errors
                if not isinstance(error, requests.Timeout)
            ),
            errors[0] if errors else None,
        )
        if isinstance(concrete_error, requests.Timeout):
            raise InvalidArgumentValueError(
                "Timed out reaching the provider's /v1/models endpoint."
            ) from concrete_error
        if concrete_error:
            raise concrete_error
        raise InvalidArgumentValueError(
            "Failed to discover models from the provider."
        )
    return [
        {
            "modelName": model_name,
            "supportedEndpoints": endpoints,
        }
        for model_name, endpoints in sorted(merged.items())
    ]


def _custom_sync_plan(
    cmd,
    provider,
    provider_path,
    delete_missing,
    api_key_value=None,
):
    discovered_models = _discover_custom_models(
        provider,
        api_key_value,
        cmd,
        provider_path,
    )
    provider_models = _list_all(cmd, _provider_models_path(provider_path))
    all_models = _list_all(cmd, _all_models_path(provider_path))
    remote_models = [
        {
            "name": _normalize_arm_name(model["modelName"]),
            "displayName": model["modelName"],
            "properties": {
                "displayName": model["modelName"],
                "supportedEndpoints": model["supportedEndpoints"],
                "deployment": {"modelName": model["modelName"]},
            },
        }
        for model in discovered_models
    ]
    return _build_sync_changes(
        provider_models,
        all_models,
        remote_models,
        delete_missing,
        "Provider model no longer exists.",
    )


def _sync_plan(
    cmd,
    provider,
    provider_path,
    delete_missing,
    api_key_value=None,
):
    if (provider.get("properties") or {}).get("kind") == "Custom":
        return _custom_sync_plan(
            cmd,
            provider,
            provider_path,
            delete_missing,
            api_key_value,
        )
    return _foundry_sync_plan(
        cmd,
        provider,
        provider_path,
        delete_missing,
    )


def _refresh_foundry_api_key(cmd, provider, provider_path):
    foundry = (provider.get("properties") or {}).get("foundry") or {}
    resource_ids = foundry.get("resourceIds") or []
    if not resource_ids:
        return
    keys = _response_json(
        _request(
            cmd,
            "POST",
            f"{resource_ids[0].rstrip('/')}/listKeys",
            {},
            api_version=FOUNDRY_API_VERSION,
        )
    )
    key = (keys or {}).get("key1")
    if not key:
        raise InvalidArgumentValueError(
            "The Foundry account did not return a primary API key."
        )
    _request(
        cmd,
        "PATCH",
        provider_path,
        {
            "properties": {
                "foundry": {
                    "endpoint": foundry.get("endpoint"),
                    "resourceIds": resource_ids,
                    "authentication": {
                        "kind": "ApiKey",
                        "apiKey": {
                            "headerName": "Authorization",
                            "value": f"Bearer {key}",
                        },
                    },
                }
            }
        },
    )


def format_model_provider_sync_table(result):
    return [
        {
            "Action": change["action"],
            "Name": change["name"],
            "Status": change["status"],
            "Reason": change.get("reason") or "",
        }
        for change in result.get("changes", [])
    ]


def _api_key_authentication(header_name, value):
    if not header_name:
        raise RequiredArgumentMissingError(
            "Specify --api-key-header-name when using API key authentication."
        )
    api_key = {"headerName": header_name}
    if value is not None:
        api_key["value"] = value
    return {
        "kind": "ApiKey",
        "apiKey": api_key,
    }


def _managed_identity_authentication(resource, client_id):
    if not resource:
        raise RequiredArgumentMissingError(
            "Specify --managed-identity-resource when using managed identity "
            "authentication."
        )
    managed_identity = {"resource": resource}
    if client_id is not None:
        managed_identity["clientId"] = client_id
    return {
        "kind": "ManagedIdentity",
        "managedIdentity": managed_identity,
    }


def _validate_authentication_options(
    auth_kind,
    api_key_header_name,
    api_key_value,
    managed_identity_resource,
    managed_identity_client_id,
):
    if auth_kind == "ApiKey":
        if (
            managed_identity_resource is not None
            or managed_identity_client_id is not None
        ):
            raise InvalidArgumentValueError(
                "Managed identity options cannot be used with API key "
                "authentication."
            )
        return _api_key_authentication(api_key_header_name, api_key_value)
    if auth_kind == "ManagedIdentity":
        if api_key_header_name is not None or api_key_value is not None:
            raise InvalidArgumentValueError(
                "API key options cannot be used with managed identity "
                "authentication."
            )
        return _managed_identity_authentication(
            managed_identity_resource,
            managed_identity_client_id,
        )
    raise InvalidArgumentValueError(
        f"Authentication kind '{auth_kind}' is not supported."
    )


def _build_provider_config(
    kind,
    endpoint,
    resource_ids,
    auth_kind,
    api_key_header_name,
    api_key_value,
    managed_identity_resource,
    managed_identity_client_id,
):
    if not endpoint:
        raise RequiredArgumentMissingError(
            "Specify --endpoint when configuring a model provider."
        )
    endpoint = _validate_provider_endpoint(endpoint)
    if kind == "Foundry":
        if not resource_ids:
            raise RequiredArgumentMissingError(
                "Specify --resource-ids for a Foundry model provider."
            )
        authentication = _validate_authentication_options(
            auth_kind or "ManagedIdentity",
            api_key_header_name,
            api_key_value,
            managed_identity_resource,
            managed_identity_client_id,
        )
        return "foundry", {
            "endpoint": endpoint,
            "resourceIds": resource_ids,
            "authentication": authentication,
        }
    if kind == "Custom":
        if resource_ids is not None:
            raise InvalidArgumentValueError(
                "--resource-ids is only valid for a Foundry model provider."
            )
        if auth_kind not in {None, "ApiKey"}:
            raise InvalidArgumentValueError(
                "Custom model providers only support API key authentication."
            )
        authentication = _validate_authentication_options(
            "ApiKey",
            api_key_header_name,
            api_key_value,
            managed_identity_resource,
            managed_identity_client_id,
        )
        return "custom", {
            "endpoint": endpoint,
            "authentication": authentication,
        }
    raise InvalidArgumentValueError(
        f"Model provider kind '{kind}' is not supported."
    )


def _build_create_properties(
    kind,
    display_name,
    description,
    endpoint,
    resource_ids,
    auth_kind,
    api_key_header_name,
    api_key_value,
    managed_identity_resource,
    managed_identity_client_id,
):
    config_name, config = _build_provider_config(
        kind,
        endpoint,
        resource_ids,
        auth_kind,
        api_key_header_name,
        api_key_value,
        managed_identity_resource,
        managed_identity_client_id,
    )
    properties = {
        "kind": kind,
        config_name: config,
    }
    if display_name is not None:
        properties["displayName"] = display_name
    if description is not None:
        properties["description"] = description
    return properties


def _build_update_properties(
    current,
    display_name,
    description,
    endpoint,
    resource_ids,
    auth_kind,
    api_key_header_name,
    api_key_value,
    managed_identity_resource,
    managed_identity_client_id,
):
    supplied_config = any(
        value is not None
        for value in [
            endpoint,
            resource_ids,
            auth_kind,
            api_key_header_name,
            api_key_value,
            managed_identity_resource,
            managed_identity_client_id,
        ]
    )
    if display_name is None and description is None and not supplied_config:
        raise RequiredArgumentMissingError(
            "Specify at least one model provider property to update."
        )

    properties = {}
    if display_name is not None:
        properties["displayName"] = display_name
    if description is not None:
        properties["description"] = description
    if not supplied_config:
        return properties

    current_properties = current.get("properties") or {}
    kind = current_properties.get("kind")
    config_name = "foundry" if kind == "Foundry" else "custom"
    current_config = deepcopy(current_properties.get(config_name) or {})
    current_auth = current_config.get("authentication") or {}
    resolved_auth_kind = auth_kind or current_auth.get("kind")
    resolved_endpoint = (
        endpoint if endpoint is not None else current_config.get("endpoint")
    )
    resolved_resource_ids = (
        resource_ids
        if resource_ids is not None
        else current_config.get("resourceIds")
    )
    current_api_key = current_auth.get("apiKey") or {}
    current_managed_identity = current_auth.get("managedIdentity") or {}
    preserve_api_key = current_auth.get("kind") == resolved_auth_kind == "ApiKey"
    preserve_managed_identity = (
        current_auth.get("kind")
        == resolved_auth_kind
        == "ManagedIdentity"
    )
    resolved_header_name = (
        api_key_header_name
        if api_key_header_name is not None
        else current_api_key.get("headerName") if preserve_api_key else None
    )
    resolved_managed_identity_resource = (
        managed_identity_resource
        if managed_identity_resource is not None
        else (
            current_managed_identity.get("resource")
            if preserve_managed_identity
            else None
        )
    )
    resolved_managed_identity_client_id = (
        managed_identity_client_id
        if managed_identity_client_id is not None
        else (
            current_managed_identity.get("clientId")
            if preserve_managed_identity
            else None
        )
    )

    config_name, config = _build_provider_config(
        kind,
        resolved_endpoint,
        resolved_resource_ids,
        resolved_auth_kind,
        resolved_header_name,
        api_key_value,
        resolved_managed_identity_resource,
        resolved_managed_identity_client_id,
    )
    properties[config_name] = config
    return properties


def list_model_providers(
    cmd,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _providers_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
    )
    return _list_all(cmd, path)


def show_model_provider(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _providers_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    try:
        return _redact_provider_secrets(
            _response_json(_request(cmd, "GET", path))
        )
    except HTTPError as error:
        _raise_provider_not_found(error, name)


def create_model_provider(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    kind,
    endpoint,
    workspace_name=DEFAULT_WORKSPACE,
    display_name=None,
    description=None,
    resource_ids=None,
    auth_kind=None,
    api_key_header_name=None,
    api_key_value=None,
    managed_identity_resource=None,
    managed_identity_client_id=None,
    no_sync=False,
):
    if (
        kind == "Custom"
        and auth_kind in {None, "ApiKey"}
        and api_key_value is None
    ):
        try:
            api_key_value = prompt_pass("Custom provider API key: ")
        except NoTTYException:
            raise RequiredArgumentMissingError(
                "Specify --api-key-value to create a custom model provider "
                "in a non-interactive session."
            ) from None
        if not api_key_value:
            raise RequiredArgumentMissingError(
                "A non-empty --api-key-value is required to create a custom "
                "model provider."
            )
    properties = _build_create_properties(
        kind,
        display_name,
        description,
        endpoint,
        resource_ids,
        auth_kind,
        api_key_header_name,
        api_key_value,
        managed_identity_resource,
        managed_identity_client_id,
    )
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _providers_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    logger.warning("Creating model provider '%s'...", name)
    created_provider = _response_json(
        _request(cmd, "PUT", path, {"properties": properties})
    )
    provider = _redact_provider_secrets(created_provider)
    if no_sync:
        logger.warning(
            "Model provider '%s' created; model synchronization was skipped.",
            name,
        )
        return provider

    logger.warning("Model provider '%s' created.", name)
    logger.warning("Discovering and importing models...")
    try:
        sync_provider = deepcopy(created_provider or {})
        sync_provider["id"] = sync_provider.get("id") or path
        sync_provider["name"] = sync_provider.get("name") or name
        # Use the submitted properties so custom discovery can use the API key
        # even when the create response intentionally omits secret values.
        sync_provider["properties"] = properties
        _synchronize_model_provider(
            cmd,
            sync_provider,
            path,
            name,
            dry_run=False,
            delete_missing=False,
            yes=False,
            api_key_value=api_key_value,
        )
    except Exception as error:
        raise AzCLIError(
            f"Model provider '{name}' was created successfully, but model "
            "import failed. Review the provider endpoint, authentication, "
            f"and discovery response. Inner error: {error}"
        ) from error
    logger.warning("Models imported.")
    return provider


def update_model_provider(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    display_name=None,
    description=None,
    endpoint=None,
    resource_ids=None,
    auth_kind=None,
    api_key_header_name=None,
    api_key_value=None,
    managed_identity_resource=None,
    managed_identity_client_id=None,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _providers_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    try:
        current = _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_provider_not_found(error, name)
    properties = _build_update_properties(
        current,
        display_name,
        description,
        endpoint,
        resource_ids,
        auth_kind,
        api_key_header_name,
        api_key_value,
        managed_identity_resource,
        managed_identity_client_id,
    )
    return _redact_provider_secrets(
        _response_json(
            _request(cmd, "PATCH", path, {"properties": properties})
        )
    )


def delete_model_provider(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _providers_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    _request(cmd, "DELETE", path)


def sync_model_provider(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    dry_run=False,
    delete_missing=False,
    yes=False,
    api_key_value=None,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _providers_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    try:
        provider = _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_provider_not_found(error, name)
    return _synchronize_model_provider(
        cmd,
        provider,
        path,
        name,
        dry_run,
        delete_missing,
        yes,
        api_key_value,
    )


def _synchronize_model_provider(
    cmd,
    provider,
    path,
    name,
    dry_run,
    delete_missing,
    yes,
    api_key_value=None,
):
    provider_kind = (provider.get("properties") or {}).get("kind")
    if provider_kind not in {"Foundry", "Custom"}:
        raise InvalidArgumentValueError(
            "Only Foundry and custom model providers can be synchronized."
        )
    if provider_kind == "Custom" and api_key_value is None:
        try:
            api_key_value = prompt_pass("Custom provider API key: ")
        except NoTTYException:
            raise RequiredArgumentMissingError(
                "Specify --api-key-value to synchronize a custom model "
                "provider in a non-interactive session."
            ) from None
    if provider_kind == "Custom" and not api_key_value:
        raise RequiredArgumentMissingError(
            "A non-empty --api-key-value is required to synchronize a custom "
            "model provider."
        )

    action = "Planning synchronization for" if dry_run else "Synchronizing"
    logger.warning("%s model provider '%s'...", action, name)
    if provider_kind == "Foundry":
        logger.warning(
            "Discovering Foundry deployments and gateway models..."
        )
    else:
        logger.warning("Discovering models from the custom provider...")
    changes = _sync_plan(
        cmd,
        provider,
        path,
        delete_missing,
        api_key_value,
    )
    if (
        not dry_run
        and not yes
        and any(change["action"] == "delete" for change in changes)
    ):
        raise RequiredArgumentMissingError(
            "Specify --yes to confirm deletion of stale model registrations."
        )
    if not dry_run:
        if provider_kind == "Foundry":
            logger.warning("Refreshing the Foundry account API key...")
            _refresh_foundry_api_key(cmd, provider, path)
        for change in changes:
            if change["action"] == "create":
                logger.warning("Creating model '%s'...", change["name"])
                model_path = (
                    f"{_provider_models_path(path)}/"
                    f"{quote(change['name'], safe='')}"
                )
                _request(
                    cmd,
                    "PUT",
                    model_path,
                    {"properties": change["properties"]},
                )
                change["status"] = "created"
            elif change["action"] == "delete":
                logger.warning("Deleting stale model '%s'...", change["name"])
                model_path = change.get("id") or (
                    f"{_provider_models_path(path)}/"
                    f"{quote(change['name'], safe='')}"
                )
                _request(cmd, "DELETE", model_path)
                change["status"] = "deleted"

    result = {
        "provider": {
            "id": provider.get("id") or path,
            "name": provider.get("name") or name,
        },
        "dryRun": dry_run,
        "deleteMissing": delete_missing,
        "summary": {
            "created": sum(
                change["status"] == "created" for change in changes
            ),
            "deleted": sum(
                change["status"] == "deleted" for change in changes
            ),
            "planned": sum(
                change["status"] == "planned" for change in changes
            ),
            "conflicts": sum(
                change["status"] == "conflict" for change in changes
            ),
            "stale": sum(
                change["status"] == "stale" for change in changes
            ),
        },
        "changes": changes,
    }
    summary = result["summary"]
    if dry_run:
        logger.warning(
            "Synchronization plan complete: %d change(s), %d conflict(s), "
            "%d stale model(s).",
            summary["planned"],
            summary["conflicts"],
            summary["stale"],
        )
    else:
        logger.warning(
            "Synchronization complete: %d created, %d deleted, "
            "%d conflict(s), %d stale model(s).",
            summary["created"],
            summary["deleted"],
            summary["conflicts"],
            summary["stale"],
        )
    return result
