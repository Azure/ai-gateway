# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from urllib.parse import quote

from azure.cli.core.azclierror import HTTPError, ResourceNotFoundError
from azure.cli.core.commands.client_factory import get_subscription_id

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
)


def _api_key_path(
    subscription_id,
    resource_group_name,
    gateway_name,
    name=None,
):
    path = (
        f"{_gateway_path(subscription_id, resource_group_name, gateway_name)}"
        "/apiKeys"
    )
    if name is not None:
        path += f"/{quote(name, safe='')}"
    return path


def _raise_api_key_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(f"API key '{name}' was not found.") from None
    raise error


def _list_all(cmd, url):
    keys = []
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
        keys.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return keys


def list_api_keys(cmd, gateway_name, resource_group_name):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _api_key_path(
        subscription_id,
        resource_group_name,
        gateway_name,
    )
    return _list_all(cmd, path)


def show_api_key(cmd, name, gateway_name, resource_group_name):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _api_key_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    try:
        return _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_api_key_not_found(error, name)


def create_api_key(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    display_name=None,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _api_key_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    body = {"properties": {"displayName": display_name or name}}
    return _response_json(_request(cmd, "PUT", path, body))


def delete_api_key(cmd, name, gateway_name, resource_group_name):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _api_key_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    _request(cmd, "DELETE", path)


def list_api_key_secrets(cmd, name, gateway_name, resource_group_name):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _api_key_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    try:
        return _response_json(_request(cmd, "POST", f"{path}/listSecrets", {}))
    except HTTPError as error:
        _raise_api_key_not_found(error, name)


def regenerate_api_key(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    key_type,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _api_key_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    action = (
        "regeneratePrimaryKey"
        if key_type.casefold() == "primary"
        else "regenerateSecondaryKey"
    )
    try:
        _request(cmd, "POST", f"{path}/{action}")
    except HTTPError as error:
        _raise_api_key_not_found(error, name)

