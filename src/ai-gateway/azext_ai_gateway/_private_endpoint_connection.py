# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import time
from urllib.parse import quote

from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id

from azext_ai_gateway._gateway import (
    POLL_INTERVAL_SECONDS,
    POLL_TIMEOUT_SECONDS,
    _gateway_path,
    _request,
    _response_json,
)
from azext_ai_gateway._progress import (
    long_running_progress,
    report_lro_accepted,
)


def format_private_endpoint_connection_list_table(connections):
    rows = []
    for connection in connections:
        properties = connection.get("properties") or {}
        state = properties.get("privateLinkServiceConnectionState") or {}
        endpoint_id = (properties.get("privateEndpoint") or {}).get("id") or ""
        rows.append(
            {
                "Name": connection.get("name") or "",
                "Private endpoint": endpoint_id.rstrip("/").split("/")[-1],
                "Connection state": state.get("status") or "",
                "Provisioning state": properties.get("provisioningState") or "",
                "Description": state.get("description") or "",
            }
        )
    return rows


def _private_endpoint_connection_path(
    subscription_id,
    resource_group_name,
    gateway_name,
    name=None,
):
    path = (
        f"{_gateway_path(subscription_id, resource_group_name, gateway_name)}"
        "/privateEndpointConnections"
    )
    if name is not None:
        path += f"/{quote(name, safe='')}"
    return path


def _raise_connection_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(
            f"Private endpoint connection '{name}' was not found."
        ) from None
    raise error


def _get_connection(cmd, path, name):
    try:
        return _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_connection_not_found(error, name)


def _wait_for_connection(
    cmd,
    path,
    name,
    expected_status=None,
    deleted=False,
):
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    action = "deletion" if deleted else "provisioning"
    message = f"Waiting for private endpoint connection '{name}' {action}"
    with long_running_progress(cmd, message) as progress:
        while time.monotonic() <= deadline:
            try:
                connection = _response_json(_request(cmd, "GET", path))
            except HTTPError as error:
                if deleted and error.response.status_code == 404:
                    return None
                _raise_connection_not_found(error, name)

            properties = connection.get("properties") or {}
            provisioning_state = properties.get("provisioningState")
            connection_state = (
                properties.get("privateLinkServiceConnectionState") or {}
            ).get("status")
            states = ", ".join(
                state
                for state in [provisioning_state, connection_state]
                if state
            )
            progress.update(
                f"{message}" + (f" (state: {states})" if states else "")
            )

            if deleted:
                progress.wait(POLL_INTERVAL_SECONDS)
                continue

            if provisioning_state in {"Failed", "Canceled", "Cancelled"}:
                raise AzureResponseError(
                    f"Private endpoint connection '{name}' provisioning ended "
                    f"in state '{provisioning_state}'."
                )
            if provisioning_state in {None, "Succeeded"} and (
                expected_status is None or connection_state == expected_status
            ):
                return connection
            progress.wait(POLL_INTERVAL_SECONDS)

        raise AzureResponseError(
            f"Timed out waiting for private endpoint connection '{name}' "
            f"{action} after {POLL_TIMEOUT_SECONDS} seconds."
        )


def list_private_endpoint_connections(
    cmd,
    gateway_name,
    resource_group_name,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    url = _private_endpoint_connection_path(
        subscription_id,
        resource_group_name,
        gateway_name,
    )
    include_api_version = True
    connections = []
    while url:
        page = _response_json(
            _request(
                cmd,
                "GET",
                url,
                include_api_version=include_api_version,
            )
        )
        connections.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return connections


def show_private_endpoint_connection(
    cmd,
    name,
    gateway_name,
    resource_group_name,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _private_endpoint_connection_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    return _get_connection(cmd, path, name)


def _set_private_endpoint_connection_status(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    status,
    description,
    no_wait,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _private_endpoint_connection_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    body = {
        "properties": {
            "privateLinkServiceConnectionState": {
                "status": status,
                "description": description or status,
            }
        }
    }
    response = _response_json(_request(cmd, "PUT", path, body))
    report_lro_accepted(
        cmd,
        f"Private endpoint connection '{name}' {status.lower()} request "
        "accepted.",
    )
    if no_wait:
        return response
    return _wait_for_connection(cmd, path, name, expected_status=status)


def approve_private_endpoint_connection(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    description="Approved",
    no_wait=False,
):
    return _set_private_endpoint_connection_status(
        cmd,
        name,
        gateway_name,
        resource_group_name,
        "Approved",
        description,
        no_wait,
    )


def reject_private_endpoint_connection(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    description="Rejected",
    no_wait=False,
):
    return _set_private_endpoint_connection_status(
        cmd,
        name,
        gateway_name,
        resource_group_name,
        "Rejected",
        description,
        no_wait,
    )


def delete_private_endpoint_connection(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    no_wait=False,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _private_endpoint_connection_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        name,
    )
    _request(cmd, "DELETE", path)
    report_lro_accepted(
        cmd,
        f"Private endpoint connection '{name}' delete request accepted.",
    )
    if no_wait:
        return None
    return _wait_for_connection(cmd, path, name, deleted=True)
