# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import re
import sys
from urllib.parse import quote, unquote

import requests

from azure.cli.core._profile import Profile
from azure.cli.core.azclierror import (
    AzCLIError,
    AzureResponseError,
    HTTPError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import should_disable_connection_verify
from knack.log import get_logger

from azext_ai_gateway._api_key import list_api_key_secrets
from azext_ai_gateway._gateway import (
    API_VERSION,
    _gateway_path,
    _gateway_runtime_url,
    _request,
    _response_json,
    show_gateway,
)
from azext_ai_gateway._model import _models_path, show_model
from azext_ai_gateway._piped_input import parse_piped_resource_names
from azext_ai_gateway._progress import long_running_progress
from azext_ai_gateway._test_execution import (
    run_test_repetitions,
    validate_test_count,
)

DEFAULT_WORKSPACE = "default"
MODEL_TEST_TIMEOUT_SECONDS = 30
AI_GATEWAY_TOKEN_AUDIENCE = "https://ai.gateway.azure.com"
logger = get_logger(__name__)
_ALIAS_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_](?:[A-Za-z0-9_.\-/]{0,254}[A-Za-z0-9_])?$"
)
_BACKEND_MODEL_PATTERN = re.compile(
    r"/modelProviders/([^/]+)/models/([^/]+)/*$",
    re.IGNORECASE,
)
_TEST_PROTOCOLS = (
    ("chat-completions", "chat-completions", "/chat/completions"),
    ("responses", "responses", "/responses"),
    ("messages", "anthropic-messages", "/messages"),
)
_ALIAS_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_](?:[A-Za-z0-9_.-]{0,78}[A-Za-z0-9_])?$"
)
_ALIAS_ID_MAX_LENGTH = 80


def _callable_name(alias):
    properties = alias.get("properties") or {}
    return str(properties.get("aliasName") or "").strip() or (
        alias.get("name") or ""
    )


def _backend_model_id(alias):
    backend_models = (alias.get("properties") or {}).get("backendModels") or []
    return (backend_models[0] if backend_models else {}).get("resourceId") or ""


def _backend_model_names(alias):
    match = _BACKEND_MODEL_PATTERN.search(_backend_model_id(alias))
    if not match:
        return "", ""
    return unquote(match.group(1)), unquote(match.group(2))


def _normalize_resource_id(resource_id):
    return re.sub(r"/+", "/", str(resource_id or "").strip()).rstrip(
        "/"
    ).casefold()


def _hash_text(value):
    result = 0x811C9DC5
    for character in value:
        result ^= ord(character)
        result = (result * 0x01000193) & 0xFFFFFFFF
    return f"{result:08x}"


def _normalize_alias_resource_id(callable_name):
    normalized = re.sub(
        r"[^a-z0-9_.-]+",
        "-",
        str(callable_name or "").strip().lower(),
    )
    normalized = re.sub(r"^[^a-z0-9_]+|[^a-z0-9_]+$", "", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    return normalized or "alias"


def _append_alias_resource_id_hash(normalized, hash_source):
    suffix = _hash_text(str(hash_source).strip().lower())
    prefix_length = max(
        1,
        _ALIAS_ID_MAX_LENGTH - len(suffix) - 1,
    )
    candidate = f"{normalized[:prefix_length]}-{suffix}"
    if _ALIAS_ID_PATTERN.fullmatch(candidate):
        return candidate
    return f"alias-{suffix}"


def generate_alias_resource_id(callable_name, aliases=()):
    normalized = _normalize_alias_resource_id(callable_name)
    occupied = {
        str(alias.get("name") or "").casefold() for alias in aliases
    }
    if (
        len(normalized) <= _ALIAS_ID_MAX_LENGTH
        and _ALIAS_ID_PATTERN.fullmatch(normalized)
        and normalized.casefold() not in occupied
    ):
        return normalized
    for attempt in range(1, 1001):
        hash_source = (
            callable_name
            if attempt == 1
            else f"{str(callable_name).strip()}-{attempt}"
        )
        candidate = _append_alias_resource_id_hash(
            normalized,
            hash_source,
        )
        if candidate.casefold() not in occupied:
            return candidate
    raise InvalidArgumentValueError(
        "Unable to generate an available model alias resource ID."
    )


def classify_alias(aliases, alias_name, target_resource_id):
    normalized_name = str(alias_name).strip().casefold()
    normalized_target = _normalize_resource_id(target_resource_id)
    existing = next(
        (
            alias
            for alias in aliases
            if _callable_name(alias).casefold() == normalized_name
        ),
        None,
    )
    if existing is None:
        return "available", None
    if _normalize_resource_id(_backend_model_id(existing)) == normalized_target:
        return "existing", existing
    return "conflict", existing


def format_model_alias_list_table(aliases):
    rows = []
    for alias in aliases:
        provider_name, model_name = _backend_model_names(alias)
        rows.append(
            {
                "Name (alias)": _callable_name(alias),
                "Backend model": model_name,
                "Provider": provider_name,
            }
        )
    return rows


def _aliases_path(
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    alias_id=None,
):
    path = (
        f"{_gateway_path(subscription_id, resource_group_name, gateway_name)}"
        f"/workspaces/{quote(workspace_name, safe='')}/aliases"
    )
    if alias_id is not None:
        path += f"/{quote(alias_id, safe='')}"
    return path


def _raise_alias_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(
            f"Model alias '{name}' was not found."
        ) from None
    raise error


def _list_all(cmd, url, api_version=API_VERSION):
    aliases = []
    include_api_version = True
    while url:
        page = _response_json(
            _request(
                cmd,
                "GET",
                url,
                include_api_version=include_api_version,
                api_version=api_version,
            )
        )
        aliases.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return aliases


def _response_etag(response, body):
    return (
        response.headers.get("ETag")
        or response.headers.get("etag")
        or (body or {}).get("etag")
    )


def _validate_alias_name(alias_name):
    value = str(alias_name or "").strip()
    if not _ALIAS_NAME_PATTERN.fullmatch(value):
        raise InvalidArgumentValueError(
            "Alias names must be 1-256 characters, use only letters, "
            "numbers, underscores, hyphens, periods, or slashes, and begin "
            "and end with a letter, number, or underscore."
        )
    return value


def _validate_description(description):
    if description is not None and len(description) > 1024:
        raise InvalidArgumentValueError(
            "Alias descriptions must be 1024 characters or fewer."
        )


def _target_model_id(
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    model_provider,
    model_name,
):
    if bool(model_provider) != bool(model_name):
        raise RequiredArgumentMissingError(
            "Specify --model-provider and --model-name together."
        )
    if not model_provider:
        return None
    return _models_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        model_provider,
        model_name,
    )


def _backend_model_reference(alias, alias_name):
    provider_name, model_name = _backend_model_names(alias)
    if not provider_name or not model_name:
        raise InvalidArgumentValueError(
            f"Model alias '{alias_name}' does not reference a valid backend "
            "model."
        )
    return provider_name, model_name


def _test_endpoint(model, alias_name, requested_endpoint=None):
    configured_endpoints = (
        (model.get("properties") or {}).get("supportedEndpoints") or []
    )
    endpoints = []
    for endpoint in configured_endpoints:
        normalized = str(endpoint or "").strip()
        if normalized:
            endpoints.append(
                normalized if normalized.startswith("/") else f"/{normalized}"
            )

    if len(endpoints) > 1 and requested_endpoint is None:
        raise RequiredArgumentMissingError(
            f"Model alias '{alias_name}' targets a model with multiple "
            f"endpoints: {', '.join(endpoints)}. Specify --endpoint with "
            "chat-completions, responses, or messages."
        )

    candidates = []
    for option, protocol, suffix in _TEST_PROTOCOLS:
        candidates.extend(
            (option, protocol, endpoint)
            for endpoint in endpoints
            if endpoint.casefold().endswith(suffix)
        )

    if requested_endpoint is not None:
        for option, protocol, endpoint in candidates:
            if option == requested_endpoint:
                return protocol, endpoint
        available = ", ".join(
            option for option, _, _ in candidates
        ) or "none"
        raise InvalidArgumentValueError(
            f"Endpoint '{requested_endpoint}' is not supported by model alias "
            f"'{alias_name}'. Available test endpoint values: {available}."
        )

    if candidates:
        _, protocol, endpoint = candidates[0]
        return protocol, endpoint

    supported = ", ".join(endpoints) or "none"
    raise InvalidArgumentValueError(
        f"Model alias '{alias_name}' targets a model without a supported "
        "generative test endpoint. Expected chat completions, responses, or "
        f"Anthropic messages; found: {supported}."
    )


def _test_payload(protocol, alias_name, prompt):
    if protocol == "chat-completions":
        return {
            "model": alias_name,
            "messages": [{"role": "user", "content": prompt}],
        }
    if protocol == "responses":
        return {
            "model": alias_name,
            "input": prompt,
        }
    return {
        "model": alias_name,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": prompt}],
    }


def _test_response_body(response):
    try:
        return response.json()
    except (requests.exceptions.JSONDecodeError, ValueError):
        return response.text


def _test_authentication_headers(
    cmd,
    api_key_name,
    gateway_name,
    resource_group_name,
):
    if not api_key_name:
        logger.warning(
            "Acquiring a Microsoft Entra access token for %s...",
            AI_GATEWAY_TOKEN_AUDIENCE,
        )
        token_type, token, _ = Profile(cmd.cli_ctx).get_raw_token(
            resource=AI_GATEWAY_TOKEN_AUDIENCE
        )[0]
        logger.warning(
            "Acquired a Microsoft Entra access token using the signed-in "
            "Azure identity."
        )
        return {"Authorization": f"{token_type} {token}"}

    secrets = list_api_key_secrets(
        cmd,
        api_key_name,
        gateway_name,
        resource_group_name,
    )
    api_key_value = (secrets or {}).get("primaryKey")
    if not api_key_value:
        raise InvalidArgumentValueError(
            f"API key resource '{api_key_name}' has no primary key value."
        )
    return {"Api-Key": api_key_value}


def list_model_aliases(
    cmd,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    api_version=API_VERSION,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    return _list_all(
        cmd,
        _aliases_path(
            subscription_id,
            resource_group_name,
            gateway_name,
            workspace_name,
        ),
        api_version,
    )


def show_model_alias(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    api_version=API_VERSION,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _aliases_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    try:
        return _response_json(
            _request(cmd, "GET", path, api_version=api_version)
        )
    except HTTPError as error:
        _raise_alias_not_found(error, name)


def test_model_alias(
    cmd,
    name=None,
    gateway_name=None,
    resource_group_name=None,
    api_key_name=None,
    workspace_name=DEFAULT_WORKSPACE,
    prompt="Reply with OK.",
    endpoint=None,
    api_version=API_VERSION,
    n=1,
):
    validate_test_count(n)
    if not gateway_name:
        raise RequiredArgumentMissingError(
            "Specify --resource-name or configure the ai-gateway default."
        )
    if not resource_group_name:
        raise RequiredArgumentMissingError(
            "Specify --resource-group or configure the group default."
        )
    if name is None:
        if sys.stdin.isatty():
            raise RequiredArgumentMissingError(
                "Specify --name or pipe the output of "
                "'az ai-gateway model-alias list --output json'."
            )
        names = parse_piped_resource_names(
            sys.stdin,
            "az ai-gateway model-alias list",
            "model alias",
        )
        results = []
        failures = []
        for alias_name in names:
            try:
                result = _test_model_alias(
                    cmd,
                    alias_name,
                    gateway_name,
                    resource_group_name,
                    api_key_name,
                    workspace_name,
                    prompt,
                    endpoint,
                    api_version,
                    n,
                )
                if n == 1:
                    results.append(result)
                else:
                    results.extend(result)
            except AzCLIError as error:
                failures.append((alias_name, str(error)))
                logger.warning(
                    "Status: Failed. Model alias resource '%s' could not be "
                    "tested: %s",
                    alias_name,
                    error,
                )
        if failures:
            failed_names = ", ".join(name for name, _ in failures)
            raise AzCLIError(
                f"Model alias batch test completed with "
                f"{len(names) - len(failures)} "
                f"succeeded and {len(failures)} failed. Failed aliases: "
                f"{failed_names}."
            )
        return results

    return _test_model_alias(
        cmd,
        name,
        gateway_name,
        resource_group_name,
        api_key_name,
        workspace_name,
        prompt,
        endpoint,
        api_version,
        n,
    )


def _test_model_alias(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    api_key_name,
    workspace_name,
    prompt,
    endpoint,
    api_version,
    n=1,
):
    alias = show_model_alias(
        cmd,
        name,
        gateway_name,
        resource_group_name,
        workspace_name,
        api_version,
    )
    alias_name = _callable_name(alias)
    provider_name, model_name = _backend_model_reference(alias, alias_name)
    model = show_model(
        cmd,
        model_name,
        gateway_name,
        resource_group_name,
        provider_name,
        workspace_name,
        api_version,
    )
    protocol, supported_endpoint = _test_endpoint(
        model,
        alias_name,
        endpoint,
    )

    gateway = show_gateway(
        cmd,
        gateway_name,
        resource_group_name,
        api_version=api_version,
    )
    gateway_url = _gateway_runtime_url(gateway)
    if not gateway_url:
        raise InvalidArgumentValueError(
            f"AI Gateway '{gateway_name}' has no runtime URL."
        )
    endpoint = (
        f"{gateway_url.rstrip('/')}/{workspace_name}/models"
        f"{supported_endpoint}"
    )

    headers = _test_authentication_headers(
        cmd,
        api_key_name,
        gateway_name,
        resource_group_name,
    )
    headers["Content-Type"] = "application/json"
    if protocol == "anthropic-messages":
        headers["anthropic-version"] = "2023-06-01"
    return run_test_repetitions(
        n,
        name,
        lambda: _send_model_alias_test(
            cmd, alias_name, protocol, endpoint, headers, prompt, api_key_name
        ),
    )


def _send_model_alias_test(
    cmd, alias_name, protocol, endpoint, headers, prompt, api_key_name
):
    progress_message = (
        f"Testing model alias '{alias_name}' using {protocol}"
    )
    with long_running_progress(cmd, progress_message):
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=_test_payload(protocol, alias_name, prompt),
                timeout=MODEL_TEST_TIMEOUT_SECONDS,
                verify=not should_disable_connection_verify(),
            )
        except requests.RequestException as error:
            raise AzCLIError(
                f"Model alias test failed for '{alias_name}' at {endpoint}: "
                f"{error}"
            ) from error
        response_body = _test_response_body(response)
        if not response.ok:
            raise AzCLIError(
                f"Model alias test failed for '{alias_name}' at {endpoint}. "
                f"HTTP {response.status_code}: {response_body}"
            )
    logger.warning(
        "Status: Succeeded. Model alias '%s' responded using %s.",
        alias_name,
        protocol,
    )
    authentication = (
        {
            "method": "ApiKey",
            "apiKeyName": api_key_name,
        }
        if api_key_name
        else {
            "method": "MicrosoftEntra",
            "resource": AI_GATEWAY_TOKEN_AUDIENCE,
        }
    )
    return {
        "status": "Succeeded",
        "aliasName": alias_name,
        "protocol": protocol,
        "authentication": authentication,
        "endpoint": endpoint,
        "response": response_body,
    }


def create_model_alias(
    cmd,
    name,
    alias_name,
    model_provider,
    model_name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    description=None,
    api_version=API_VERSION,
):
    alias_name = _validate_alias_name(alias_name)
    _validate_description(description)
    subscription_id = get_subscription_id(cmd.cli_ctx)
    target_id = _target_model_id(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        model_provider,
        model_name,
    )
    properties = {
        "aliasName": alias_name,
        "backendModels": [{"resourceId": target_id}],
    }
    if description is not None:
        properties["description"] = description
    path = _aliases_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    return _response_json(
        _request(
            cmd,
            "PUT",
            path,
            {"properties": properties},
            api_version=api_version,
        )
    )


def update_model_alias(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    alias_name=None,
    model_provider=None,
    model_name=None,
    description=None,
    if_match=None,
    api_version=API_VERSION,
):
    if all(
        value is None
        for value in [alias_name, model_provider, model_name, description]
    ):
        raise RequiredArgumentMissingError(
            "Specify --alias-name, --model-provider with --model-name, or "
            "--description."
        )
    _validate_description(description)
    subscription_id = get_subscription_id(cmd.cli_ctx)
    target_id = _target_model_id(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        model_provider,
        model_name,
    )
    properties = {}
    if alias_name is not None:
        properties["aliasName"] = _validate_alias_name(alias_name)
    if target_id is not None:
        properties["backendModels"] = [{"resourceId": target_id}]
    if description is not None:
        properties["description"] = description

    path = _aliases_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    etag = if_match
    if not etag:
        try:
            response = _request(cmd, "GET", path, api_version=api_version)
        except HTTPError as error:
            _raise_alias_not_found(error, name)
        current = _response_json(response)
        etag = _response_etag(response, current)
    if not etag:
        raise AzureResponseError(
            f"Model alias '{name}' did not return an ETag. Retry the command."
        )
    return _response_json(
        _request(
            cmd,
            "PATCH",
            path,
            {"properties": properties},
            headers={"If-Match": etag},
            api_version=api_version,
        )
    )


def delete_model_alias(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    if_match=None,
    api_version=API_VERSION,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _aliases_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    etag = if_match
    if not etag:
        try:
            response = _request(cmd, "GET", path, api_version=api_version)
        except HTTPError as error:
            _raise_alias_not_found(error, name)
        current = _response_json(response)
        etag = _response_etag(response, current)
    if not etag:
        raise AzureResponseError(
            f"Model alias '{name}' did not return an ETag. Retry the command."
        )
    try:
        _request(
            cmd,
            "DELETE",
            path,
            headers={"If-Match": etag},
            api_version=api_version,
        )
    except HTTPError as error:
        _raise_alias_not_found(error, name)
