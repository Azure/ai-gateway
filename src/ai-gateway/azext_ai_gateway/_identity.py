# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import (
    HTTPError,
    RequiredArgumentMissingError,
)
from azure.cli.core.commands.client_factory import get_subscription_id

from azext_ai_gateway._gateway import (
    _current_identity,
    _gateway_path,
    _raise_not_found,
    _request,
    _response_json,
    _wait_for_gateway,
)
from azext_ai_gateway._progress import report_lro_accepted


def _get_gateway(cmd, path, name):
    try:
        return _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_not_found(error, name)


def _identity_type(system_assigned, user_assigned):
    if system_assigned and user_assigned:
        return "SystemAssigned, UserAssigned"
    if system_assigned:
        return "SystemAssigned"
    if user_assigned:
        return "UserAssigned"
    return "None"


def show_identity(cmd, gateway_name, resource_group_name):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, gateway_name)
    gateway = _get_gateway(cmd, path, gateway_name)
    return gateway.get("identity") or {"type": "None"}


def assign_identity(
    cmd,
    gateway_name,
    resource_group_name,
    system_assigned=False,
    user_assigned=None,
    no_wait=False,
):
    if not system_assigned and not user_assigned:
        raise RequiredArgumentMissingError(
            "Specify --system-assigned or --user-assigned."
        )

    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, gateway_name)
    current = _get_gateway(cmd, path, gateway_name)
    current_system, current_users = _current_identity(current)
    additions = list(dict.fromkeys(user_assigned or []))
    all_users = list(dict.fromkeys(current_users + additions))
    identity = {
        "type": _identity_type(
            current_system or system_assigned,
            bool(all_users),
        )
    }
    if additions:
        identity["userAssignedIdentities"] = {
            resource_id: {} for resource_id in additions
        }

    response = _response_json(
        _request(cmd, "PATCH", path, {"identity": identity})
    )
    report_lro_accepted(
        cmd,
        f"Identity assignment for AI Gateway '{gateway_name}' accepted.",
    )
    if no_wait:
        return response
    gateway = _wait_for_gateway(cmd, path, gateway_name)
    return gateway.get("identity") or {"type": "None"}


def remove_identity(
    cmd,
    gateway_name,
    resource_group_name,
    system_assigned=False,
    user_assigned=None,
    no_wait=False,
):
    if not system_assigned and user_assigned is None:
        raise RequiredArgumentMissingError(
            "Specify --system-assigned or --user-assigned."
        )

    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, gateway_name)
    current = _get_gateway(cmd, path, gateway_name)
    current_system, current_users = _current_identity(current)
    removals = current_users if user_assigned == [] else (user_assigned or [])
    removal_set = set(removals)
    remaining_users = [
        resource_id
        for resource_id in current_users
        if resource_id not in removal_set
    ]
    identity = {
        "type": _identity_type(
            current_system and not system_assigned,
            bool(remaining_users),
        )
    }
    if removals:
        identity["userAssignedIdentities"] = {
            resource_id: None for resource_id in removals
        }

    response = _response_json(
        _request(cmd, "PATCH", path, {"identity": identity})
    )
    report_lro_accepted(
        cmd,
        f"Identity removal for AI Gateway '{gateway_name}' accepted.",
    )
    if no_wait:
        return response
    gateway = _wait_for_gateway(cmd, path, gateway_name)
    return gateway.get("identity") or {"type": "None"}
