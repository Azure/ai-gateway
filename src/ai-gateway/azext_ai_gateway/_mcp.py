# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from urllib.parse import quote

import requests
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
    _gateway_path,
    _request,
    _response_json,
    show_gateway,
)

DEFAULT_WORKSPACE = "default"
MAX_SECRET_READ_ATTEMPTS = 3
MCP_INITIALIZE_TIMEOUT_SECONDS = 15
MCP_PROTOCOL_VERSION = "2024-11-05"
logger = get_logger(__name__)
_FEDERATION_ENDPOINT_ERROR = re.compile(
    r"(required|optional) endpoint '([^']+)' returned error: "
    r"Endpoint '([^']+)' (init|tools/list) returned HTTP (\d+)",
    re.IGNORECASE,
)
OAUTH_SERVER_MANAGED_FIELDS = {
    "status",
    "statusUpdatedUtc",
    "tokenKind",
    "tokenExpiresUtc",
    "refreshToken",
}


def format_mcp_list_table(servers):
    return [
        {
            "Name": server.get("name") or "",
            "Description": (server.get("properties") or {}).get(
                "description"
            )
            or "",
            "Endpoint": (server.get("properties") or {}).get(
                "mcpEndpointUrl"
            )
            or "",
        }
        for server in servers
    ]


def _mcp_path(
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    name=None,
):
    path = (
        f"{_gateway_path(subscription_id, resource_group_name, gateway_name)}"
        f"/workspaces/{quote(workspace_name, safe='')}/toolServers"
    )
    if name is not None:
        path += f"/{quote(name, safe='')}"
    return path


def _mcp_runtime_endpoint(gateway_url, workspace_name, name):
    return (
        f"{gateway_url.rstrip('/')}/{quote(workspace_name, safe='')}"
        f"/toolservers/{quote(name, safe='')}/mcp"
    )


def _raise_mcp_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(
            f"MCP tool server '{name}' was not found."
        ) from None
    raise error


def _response_etag(response, body):
    return (
        response.headers.get("ETag")
        or response.headers.get("etag")
        or (body or {}).get("etag")
    )


def _clean_endpoints(endpoints):
    cleaned = deepcopy(endpoints)
    for endpoint in cleaned:
        oauth = (endpoint.get("credentials") or {}).get("oauth2")
        if oauth:
            for field in OAUTH_SERVER_MANAGED_FIELDS:
                oauth.pop(field, None)
    return cleaned


def _endpoint_index(endpoints):
    by_id = {}
    by_namespace = {}
    for endpoint in endpoints:
        if endpoint.get("id"):
            by_id[endpoint["id"]] = endpoint
        if endpoint.get("namespace"):
            by_namespace[endpoint["namespace"]] = endpoint
    return by_id, by_namespace


def _matching_endpoint(endpoint, by_id, by_namespace):
    if endpoint.get("id") and endpoint["id"] in by_id:
        return by_id[endpoint["id"]]
    return by_namespace.get(endpoint.get("namespace"))


def _merge_secret_fragments(endpoints, secret_fragments):
    by_id, by_namespace = _endpoint_index(secret_fragments)
    merged = deepcopy(endpoints)
    for endpoint in merged:
        secret = _matching_endpoint(endpoint, by_id, by_namespace)
        if not secret:
            continue
        if "credentials" in secret:
            endpoint["credentials"] = deepcopy(secret["credentials"])
        if "openApi" in secret:
            endpoint["openApi"] = deepcopy(secret["openApi"])
    return merged


def _preserve_endpoint_secrets(endpoints, current_endpoints):
    by_id, by_namespace = _endpoint_index(current_endpoints)
    merged = deepcopy(endpoints)
    for endpoint in merged:
        current = _matching_endpoint(endpoint, by_id, by_namespace)
        if not current:
            continue

        if "credentials" not in endpoint and "credentials" in current:
            endpoint["credentials"] = deepcopy(current["credentials"])
        elif endpoint.get("credentials", {}).get("type") == "header":
            current_credentials = current.get("credentials") or {}
            if (
                "headers" not in endpoint["credentials"]
                and "headers" in current_credentials
            ):
                endpoint["credentials"]["headers"] = deepcopy(
                    current_credentials["headers"]
                )
        elif endpoint.get("credentials", {}).get("type") == "oauth2":
            current_oauth = (current.get("credentials") or {}).get("oauth2") or {}
            oauth = endpoint["credentials"].setdefault("oauth2", {})
            if "clientSecret" not in oauth and "clientSecret" in current_oauth:
                oauth["clientSecret"] = current_oauth["clientSecret"]

        current_source = ((current.get("openApi") or {}).get("specSource") or {})
        source = ((endpoint.get("openApi") or {}).get("specSource") or {})
        if (
            source.get("type") == "inline"
            and "contentBase64" not in source
            and "contentBase64" in current_source
        ):
            source["contentBase64"] = current_source["contentBase64"]
    return merged


def _get_with_secrets(cmd, path, name):
    for _ in range(MAX_SECRET_READ_ATTEMPTS):
        try:
            get_response = _request(cmd, "GET", path)
        except HTTPError as error:
            _raise_mcp_not_found(error, name)
        server = _response_json(get_response)
        secrets_response = _request(cmd, "POST", f"{path}/listSecrets")
        secrets = _response_json(secrets_response)
        get_etag = _response_etag(get_response, server)
        secrets_etag = _response_etag(secrets_response, secrets)
        if get_etag and secrets_etag and get_etag != secrets_etag:
            continue
        properties = deepcopy(server.get("properties") or {})
        properties["endpoints"] = _merge_secret_fragments(
            properties.get("endpoints") or [],
            (secrets or {}).get("endpoints") or [],
        )
        return properties, get_etag
    raise AzureResponseError(
        f"MCP tool server '{name}' changed while its secrets were read. Retry."
    )


def _list_all(cmd, url):
    servers = []
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
        servers.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return servers


def list_mcp(
    cmd,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
    )
    servers = _list_all(cmd, path)
    if not servers:
        return servers

    gateway = show_gateway(cmd, gateway_name, resource_group_name)
    gateway_url = (gateway.get("properties") or {}).get("gatewayUrl")
    if not gateway_url:
        raise InvalidArgumentValueError(
            f"AI Gateway '{gateway_name}' has no runtime URL."
        )
    for server in servers:
        name = server.get("name")
        if name:
            properties = server.get("properties")
            if not isinstance(properties, dict):
                properties = {}
                server["properties"] = properties
            properties["mcpEndpointUrl"] = _mcp_runtime_endpoint(
                gateway_url,
                workspace_name,
                name,
            )
    return servers


def show_mcp(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    try:
        return _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_mcp_not_found(error, name)


def create_mcp(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    endpoints,
    workspace_name=DEFAULT_WORKSPACE,
    display_name=None,
    description=None,
    failure_mode=None,
    policies=None,
):
    properties = {
        "type": "mcp",
        "endpoints": _clean_endpoints(endpoints),
    }
    if display_name is not None:
        properties["displayName"] = display_name
    if description is not None:
        properties["description"] = description
    if failure_mode is not None:
        properties["failureMode"] = failure_mode
    if policies is not None:
        properties["policies"] = policies

    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    return _response_json(
        _request(cmd, "PUT", path, {"properties": properties})
    )


def update_mcp(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    endpoints=None,
    display_name=None,
    description=None,
    failure_mode=None,
    policies=None,
    if_match=None,
):
    if all(
        value is None
        for value in [
            endpoints,
            display_name,
            description,
            failure_mode,
            policies,
        ]
    ):
        raise RequiredArgumentMissingError(
            "Specify at least one MCP tool server property to update."
        )

    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    replace_resource = endpoints is not None or policies is not None
    if replace_resource:
        current_properties, current_etag = _get_with_secrets(cmd, path, name)
        properties = deepcopy(current_properties)
        for field in ["mcpEndpointUrl", "state", "provisioningState"]:
            properties.pop(field, None)
        if endpoints is not None:
            properties["endpoints"] = _preserve_endpoint_secrets(
                endpoints,
                properties.get("endpoints") or [],
            )
        properties["endpoints"] = _clean_endpoints(
            properties.get("endpoints") or []
        )
    else:
        properties = {}
        try:
            current_response = _request(cmd, "GET", path)
        except HTTPError as error:
            _raise_mcp_not_found(error, name)
        current = _response_json(current_response)
        current_etag = _response_etag(current_response, current)

    if display_name is not None:
        properties["displayName"] = display_name
    if description is not None:
        properties["description"] = description
    if failure_mode is not None:
        properties["failureMode"] = failure_mode
    if policies is not None:
        properties["policies"] = policies

    etag = if_match or current_etag
    headers = {"If-Match": etag} if etag else None
    method = "PUT" if replace_resource else "PATCH"
    return _response_json(
        _request(
            cmd,
            method,
            path,
            {"properties": properties},
            headers=headers,
        )
    )


def delete_mcp(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    _request(cmd, "DELETE", path)


def authorize_mcp(
    cmd,
    name,
    endpoint_id,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        name,
    )
    action_path = (
        f"{path}/endpoints/{quote(endpoint_id, safe='')}/oauth2/getLoginLinks"
    )
    return _response_json(_request(cmd, "POST", action_path, {}))


def _initialize_payload():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "azure-ai-gateway-cli",
                "version": "1.0",
            },
        },
    }


def _mcp_response_json(response, operation):
    content_type = response.headers.get("Content-Type", "").casefold()
    try:
        if content_type.startswith("text/event-stream"):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line.removeprefix("data:").strip())
            raise ValueError("The event stream did not contain a data event.")
        return response.json()
    except (json.JSONDecodeError, ValueError) as error:
        raise AzCLIError(
            f"The MCP server returned an invalid {operation} response."
        ) from error


def _parse_mcp_response(response, endpoint, request_id, operation):
    if not response.ok:
        raise AzCLIError(
            f"The MCP {operation} request to {endpoint} returned "
            f"HTTP {response.status_code}."
        )

    payload = _mcp_response_json(response, operation)
    if not isinstance(payload, dict):
        raise AzCLIError(
            f"The MCP server returned an invalid {operation} response."
        )
    protocol_error = payload.get("error")
    if isinstance(protocol_error, dict):
        code = protocol_error.get("code")
        message = protocol_error.get("message") or "Unknown MCP error."
        code_suffix = f" ({code})" if code is not None else ""
        raise AzCLIError(
            f"The MCP server rejected {operation}{code_suffix}: {message}"
        )
    result = payload.get("result")
    if (
        payload.get("jsonrpc") != "2.0"
        or payload.get("id") != request_id
        or not isinstance(result, dict)
    ):
        raise AzCLIError(
            f"The MCP server returned an invalid {operation} response."
        )
    return result


def _parse_initialize_response(response, endpoint):
    result = _parse_mcp_response(response, endpoint, 1, "initialize")
    if not isinstance(result.get("protocolVersion"), str):
        raise AzCLIError(
            "The MCP server returned an invalid initialize response."
        )
    return result


def _parse_tools_list_response(response, endpoint):
    result = _parse_mcp_response(response, endpoint, 2, "tools/list")
    if not isinstance(result.get("tools"), list):
        raise AzCLIError(
            "The MCP server returned an invalid tools/list response."
        )
    return result


def _response_error_message(response):
    if response is None:
        return None
    try:
        payload = response.json()
    except (requests.exceptions.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    service_error = payload.get("error")
    if isinstance(service_error, dict):
        message = service_error.get("message")
        if isinstance(message, str) and message:
            return message
    return None


def _federation_diagnosis(response):
    message = _response_error_message(response)
    if not message:
        return None
    match = _FEDERATION_ENDPOINT_ERROR.search(message)
    if not match:
        return None

    requirement, _, endpoint, operation, status = match.groups()
    return {
        "endpoint": endpoint,
        "requirement": requirement.capitalize(),
        "operation": "initialize" if operation.casefold() == "init" else operation,
        "status": f"HTTP {status}",
    }


def _mcp_error_details(error, response):
    if response is None:
        return f"Connection error: {error}"
    details = [
        "Response:",
        f"Status: {response.status_code}",
        f"Headers: {dict(response.headers)}",
        "Body:",
        response.text,
    ]
    return "\n".join(details)


def _raise_mcp_diagnostic_failure(
    stage,
    endpoint,
    completed_stages,
    error,
    response=None,
):
    diagnosis = _federation_diagnosis(response)
    rows = [
        (completed_stage, "Succeeded")
        for completed_stage in completed_stages
    ]
    rows.append(
        (stage, "Federation failed" if diagnosis else "Failed")
    )
    stage_width = max(len("Stage"), *(len(row[0]) for row in rows))
    status_width = max(len("Status"), *(len(row[1]) for row in rows))
    table = [
        f"{'Stage':<{stage_width}}  {'Status':<{status_width}}",
        f"{'-' * stage_width}  {'-' * status_width}",
        *[
            f"{row_stage:<{stage_width}}  {status:<{status_width}}"
            for row_stage, status in rows
        ],
    ]
    diagnosis_output = ""
    if diagnosis:
        diagnosis_output = (
            "\n\nFederation diagnosis:\n"
            f"Endpoint: {diagnosis['endpoint']}\n"
            f"Requirement: {diagnosis['requirement']}\n"
            f"Downstream operation: {diagnosis['operation']}\n"
            f"Downstream status: {diagnosis['status']}"
        )
    raise AzCLIError(
        f"MCP diagnostic failed.\n"
        f"Endpoint: {endpoint}\n"
        f"{chr(10).join(table)}"
        f"{diagnosis_output}\n\n"
        f"{_mcp_error_details(error, response)}"
    ) from error


def _announce_failure_mode(failure_mode, endpoints):
    normalized = str(failure_mode or "").casefold()
    if normalized == "failopen":
        implication = (
            "Unavailable endpoints may be omitted, so a successful test can "
            "return a partial tool list."
        )
    elif normalized == "failclosed":
        implication = (
            "A required endpoint failure stops federation and is returned by "
            "the test."
        )
    else:
        implication = None
    if implication:
        logger.warning("Failure mode: %s. %s", failure_mode, implication)
    optional_count = sum(
        1
        for endpoint in endpoints
        if isinstance(endpoint, dict) and endpoint.get("required") is False
    )
    if optional_count:
        noun = "endpoint is" if optional_count == 1 else "endpoints are"
        availability = (
            "that endpoint is"
            if optional_count == 1
            else "any of those endpoints are"
        )
        logger.warning(
            "Warning: %d configured %s not required. The tools/list result "
            "may be incomplete if %s unavailable.",
            optional_count,
            noun,
            availability,
        )


def test_mcp(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    api_key_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    server = show_mcp(
        cmd,
        name,
        gateway_name,
        resource_group_name,
        workspace_name,
    )
    server_properties = server.get("properties") or {}
    failure_mode = server_properties.get("failureMode")
    configured_endpoints = server_properties.get("endpoints") or []
    _announce_failure_mode(failure_mode, configured_endpoints)

    gateway = show_gateway(
        cmd,
        gateway_name,
        resource_group_name,
    )
    gateway_url = (gateway.get("properties") or {}).get("gatewayUrl")
    if not gateway_url:
        raise InvalidArgumentValueError(
            f"AI Gateway '{gateway_name}' has no runtime URL."
        )
    endpoint = _mcp_runtime_endpoint(gateway_url, workspace_name, name)

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

    request_options = {
        "timeout": MCP_INITIALIZE_TIMEOUT_SECONDS,
        "verify": not should_disable_connection_verify(),
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Api-Key": api_key_value,
        "Content-Type": "application/json",
    }
    completed_stages = []
    initialize_response = None
    try:
        initialize_response = requests.post(
            endpoint,
            headers=headers,
            json=_initialize_payload(),
            **request_options,
        )
        initialize_result = _parse_initialize_response(
            initialize_response,
            endpoint,
        )
    except (requests.RequestException, AzCLIError) as error:
        _raise_mcp_diagnostic_failure(
            "initialize",
            endpoint,
            completed_stages,
            error,
            initialize_response,
        )
    completed_stages.append("initialize")

    session_headers = headers.copy()
    session_id = initialize_response.headers.get("Mcp-Session-Id")
    if session_id:
        session_headers["Mcp-Session-Id"] = session_id

    initialized_response = None
    try:
        initialized_response = requests.post(
            endpoint,
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            **request_options,
        )
        if not initialized_response.ok:
            raise AzCLIError(
                f"The MCP notifications/initialized request to {endpoint} "
                f"returned HTTP {initialized_response.status_code}. Check the "
                "server configuration and API key."
            )
    except (requests.RequestException, AzCLIError) as error:
        _raise_mcp_diagnostic_failure(
            "notifications/initialized",
            endpoint,
            completed_stages,
            error,
            initialized_response,
        )
    completed_stages.append("notifications/initialized")

    tools_response = None
    try:
        tools_response = requests.post(
            endpoint,
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            **request_options,
        )
        tools_result = _parse_tools_list_response(tools_response, endpoint)
    except (requests.RequestException, AzCLIError) as error:
        _raise_mcp_diagnostic_failure(
            "tools/list",
            endpoint,
            completed_stages,
            error,
            tools_response,
        )

    result = deepcopy(initialize_result)
    result["tools"] = tools_result["tools"]
    if "nextCursor" in tools_result:
        result["nextCursor"] = tools_result["nextCursor"]
    result["diagnostic"] = {
        "failureMode": failure_mode,
        "configuredEndpointCount": len(configured_endpoints),
        "status": "succeeded",
    }
    return result
