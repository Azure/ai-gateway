# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import time
from urllib.parse import quote

from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import send_raw_request

API_VERSION = "2025-09-01-preview"
DEFAULT_PUBLISHER_EMAIL = "noreply@aigateway.azure.com"
DEFAULT_PUBLISHER_NAME = "AI Gateway Administrator"
PROVIDER_PATH = "Microsoft.ApiManagement/service"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300


def _gateway_path(subscription_id, resource_group_name, name):
    return (
        f"/subscriptions/{quote(subscription_id, safe='')}"
        f"/resourceGroups/{quote(resource_group_name, safe='')}"
        f"/providers/{PROVIDER_PATH}/{quote(name, safe='')}"
    )


def _list_path(subscription_id, resource_group_name=None):
    prefix = f"/subscriptions/{quote(subscription_id, safe='')}"
    if resource_group_name:
        prefix += f"/resourceGroups/{quote(resource_group_name, safe='')}"
    return f"{prefix}/providers/{PROVIDER_PATH}"


def _request(
    cmd,
    method,
    url,
    body=None,
    include_api_version=True,
    headers=None,
):
    request_kwargs = {}
    if headers:
        request_kwargs["headers"] = [
            f"{header_name}={header_value}"
            for header_name, header_value in headers.items()
        ]
    return send_raw_request(
        cmd.cli_ctx,
        method,
        url,
        uri_parameters=[f"api-version={API_VERSION}"] if include_api_version else None,
        body=json.dumps(body) if body is not None else None,
        **request_kwargs,
    )


def _response_json(response):
    if not response.content:
        return None
    return response.json()


def _get_resource(cmd, path):
    return _response_json(_request(cmd, "GET", path))


def _raise_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(f"AI Gateway '{name}' was not found.") from None
    raise error


def _wait_for_gateway(cmd, path, name, deleted=False):
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() <= deadline:
        try:
            resource = _get_resource(cmd, path)
        except HTTPError as error:
            if deleted and error.response.status_code == 404:
                return None
            _raise_not_found(error, name)

        if deleted:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        state = (resource.get("properties") or {}).get("provisioningState")
        if state == "Succeeded":
            return resource
        if state in {"Failed", "Canceled", "Cancelled"}:
            raise AzureResponseError(
                f"AI Gateway '{name}' provisioning ended in state '{state}'."
            )
        time.sleep(POLL_INTERVAL_SECONDS)

    action = "deletion" if deleted else "provisioning"
    raise AzureResponseError(
        f"Timed out waiting for AI Gateway '{name}' {action} after "
        f"{POLL_TIMEOUT_SECONDS} seconds."
    )


def _identity_payload(system_assigned, user_assigned_ids):
    user_assigned = {resource_id: {} for resource_id in user_assigned_ids}
    if system_assigned and user_assigned:
        identity_type = "SystemAssigned, UserAssigned"
    elif system_assigned:
        identity_type = "SystemAssigned"
    elif user_assigned:
        identity_type = "UserAssigned"
    else:
        identity_type = "None"

    identity = {"type": identity_type}
    if user_assigned:
        identity["userAssignedIdentities"] = user_assigned
    return identity


def _current_identity(resource):
    identity = resource.get("identity") or {}
    identity_type = identity.get("type") or "None"
    return (
        "SystemAssigned" in identity_type,
        list((identity.get("userAssignedIdentities") or {}).keys()),
    )


def create_gateway(
    cmd,
    name,
    resource_group_name,
    location,
    publisher_email=DEFAULT_PUBLISHER_EMAIL,
    publisher_name=DEFAULT_PUBLISHER_NAME,
    tags=None,
    mi_system_assigned=None,
    mi_user_assigned=None,
    no_wait=False,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, name)
    body = {
        "location": location,
        "sku": {"name": "AIGateway", "capacity": 1},
        "properties": {
            "publisherEmail": publisher_email,
            "publisherName": publisher_name,
        },
    }
    if tags is not None:
        body["tags"] = tags
    if mi_system_assigned is not None or mi_user_assigned is not None:
        body["identity"] = _identity_payload(
            bool(mi_system_assigned),
            mi_user_assigned or [],
        )

    response = _response_json(_request(cmd, "PUT", path, body))
    if no_wait:
        return response
    return _wait_for_gateway(cmd, path, name)


def list_gateways(cmd, resource_group_name=None):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    url = _list_path(subscription_id, resource_group_name)
    include_api_version = True
    gateways = []

    while url:
        page = _response_json(
            _request(
                cmd,
                "GET",
                url,
                include_api_version=include_api_version,
            )
        )
        gateways.extend(
            gateway
            for gateway in page.get("value", [])
            if str((gateway.get("sku") or {}).get("name", "")).casefold()
            == "aigateway"
        )
        url = page.get("nextLink")
        include_api_version = False

    return gateways


def show_gateway(cmd, name, resource_group_name):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, name)
    try:
        return _get_resource(cmd, path)
    except HTTPError as error:
        _raise_not_found(error, name)


def update_gateway(
    cmd,
    name,
    resource_group_name,
    tags=None,
    mi_system_assigned=None,
    mi_user_assigned=None,
    public_network_access=None,
    virtual_network_type=None,
    subnet_resource_id=None,
    no_wait=False,
):
    if all(
        value is None
        for value in [
            tags,
            mi_system_assigned,
            mi_user_assigned,
            public_network_access,
            virtual_network_type,
            subnet_resource_id,
        ]
    ):
        raise RequiredArgumentMissingError(
            "Specify at least one property to update."
        )

    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, name)
    body = {}

    if tags is not None:
        body["tags"] = tags

    if mi_system_assigned is not None or mi_user_assigned is not None:
        try:
            current = _get_resource(cmd, path)
        except HTTPError as error:
            _raise_not_found(error, name)
        current_system, current_users = _current_identity(current)
        body["identity"] = _identity_payload(
            current_system if mi_system_assigned is None else mi_system_assigned,
            current_users if mi_user_assigned is None else mi_user_assigned,
        )

    properties = {}
    if public_network_access is not None:
        properties["publicNetworkAccess"] = public_network_access
    if virtual_network_type is not None:
        properties["virtualNetworkType"] = virtual_network_type
    if subnet_resource_id is not None:
        subnet_resource_id = subnet_resource_id.strip()
        properties["virtualNetworkConfiguration"] = (
            {"subnetResourceId": subnet_resource_id}
            if subnet_resource_id
            else None
        )
    if properties:
        body["properties"] = properties

    response = _response_json(_request(cmd, "PATCH", path, body))
    if no_wait:
        return response
    return _wait_for_gateway(cmd, path, name)


def delete_gateway(cmd, name, resource_group_name, no_wait=False):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, name)
    _request(cmd, "DELETE", path)
    if no_wait:
        return None
    return _wait_for_gateway(cmd, path, name, deleted=True)
