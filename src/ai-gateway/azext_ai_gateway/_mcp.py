# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from copy import deepcopy
from urllib.parse import quote

from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
)

DEFAULT_WORKSPACE = "default"
MAX_SECRET_READ_ATTEMPTS = 3
OAUTH_SERVER_MANAGED_FIELDS = {
    "status",
    "statusUpdatedUtc",
    "tokenKind",
    "tokenExpiresUtc",
    "refreshToken",
}


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
    return _list_all(cmd, path)


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
