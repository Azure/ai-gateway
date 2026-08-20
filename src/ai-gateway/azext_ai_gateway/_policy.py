# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from urllib.parse import quote

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from knack.log import get_logger

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
)
from azext_ai_gateway._mcp import (
    _clean_endpoints,
    _get_with_secrets,
    _list_all as _list_all_mcp,
    _mcp_path,
)
from azext_ai_gateway._model import (
    _list_all as _list_all_models,
    _models_path,
)

DEFAULT_WORKSPACE = "default"
POLICY_ID_MARKER = "#policies/"
logger = get_logger(__name__)
_MODEL_HOST_PATTERN = re.compile(
    r"/workspaces/([^/]+)/modelProviders/([^/]+)/models/([^/]+)$",
    re.IGNORECASE,
)
_MCP_HOST_PATTERN = re.compile(
    r"/workspaces/([^/]+)/toolServers/([^/]+)$",
    re.IGNORECASE,
)


def format_policy_list_table(policies):
    return [
        {
            "ScopeName": policy.get("scopeName") or "",
            "ScopeType": policy.get("scopeType") or "",
            "WorkspaceName": policy.get("workspaceName") or "",
            "Type": policy.get("type") or "",
        }
        for policy in policies
    ]


def _fingerprint(policy):
    serialized = _stable_stringify(policy)
    value = 0x811C9DC5
    encoded = serialized.encode("utf-16-le")
    for offset in range(0, len(encoded), 2):
        code_unit = int.from_bytes(encoded[offset:offset + 2], "little")
        value ^= code_unit
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def _stable_stringify(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, list):
        return f"[{','.join(_stable_stringify(item) for item in value)}]"
    if isinstance(value, dict):
        entries = (
            f"{json.dumps(key, ensure_ascii=False)}:{_stable_stringify(value[key])}"
            for key in sorted(value)
        )
        return f"{{{','.join(entries)}}}"
    raise InvalidArgumentValueError("Policy contains an unsupported JSON value.")


def _policy_id(host_id, index, policy):
    return (
        f"{host_id}{POLICY_ID_MARKER}{index}/"
        f"{quote(policy['type'], safe='')}/{_fingerprint(policy)}"
    )


def _parse_policy_id(policy_id):
    marker_at = policy_id.rfind(POLICY_ID_MARKER)
    if marker_at < 0:
        raise InvalidArgumentValueError("Invalid policy ID.")
    host_id = policy_id[:marker_at]
    parts = policy_id[marker_at + len(POLICY_ID_MARKER):].split("/")
    if len(parts) != 3:
        raise InvalidArgumentValueError("Invalid policy ID.")
    try:
        index = int(parts[0])
    except ValueError as error:
        raise InvalidArgumentValueError("Invalid policy ID.") from error
    if index < 0 or not parts[1] or not parts[2]:
        raise InvalidArgumentValueError("Invalid policy ID.")
    return {
        "host_id": host_id,
        "index": index,
        "type": parts[1],
        "fingerprint": parts[2],
    }


def _host_ref(host_id):
    model_match = _MODEL_HOST_PATTERN.search(host_id)
    if model_match:
        return {
            "host_id": host_id,
            "scope_type": "model",
            "workspace_name": model_match.group(1),
            "provider_name": model_match.group(2),
            "scope_name": model_match.group(3),
        }
    mcp_match = _MCP_HOST_PATTERN.search(host_id)
    if mcp_match:
        return {
            "host_id": host_id,
            "scope_type": "mcp",
            "workspace_name": mcp_match.group(1),
            "provider_name": None,
            "scope_name": mcp_match.group(2),
        }
    raise InvalidArgumentValueError(
        "Policy host must be a model or MCP tool server."
    )


def _result(host_ref, index, policy):
    return {
        "id": _policy_id(host_ref["host_id"], index, policy),
        "type": policy["type"],
        "scopeType": host_ref["scope_type"],
        "scopeName": host_ref["scope_name"],
        "workspaceName": host_ref["workspace_name"],
        "providerName": host_ref["provider_name"],
        "policy": policy,
    }


def _locate(policies, locator):
    if locator["index"] < len(policies):
        candidate = policies[locator["index"]]
        if (
            candidate.get("type") == locator["type"]
            and _fingerprint(candidate) == locator["fingerprint"]
        ):
            return locator["index"]
    return next(
        (
            index
            for index, policy in enumerate(policies)
            if policy.get("type") == locator["type"]
            and _fingerprint(policy) == locator["fingerprint"]
        ),
        -1,
    )


def _gateway_and_host(
    cmd,
    gateway_name,
    resource_group_name,
    policy_id,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    gateway_path = _gateway_path(
        subscription_id,
        resource_group_name,
        gateway_name,
    )
    locator = _parse_policy_id(policy_id)
    if not locator["host_id"].casefold().startswith(
        f"{gateway_path}/workspaces/".casefold()
    ):
        raise InvalidArgumentValueError(
            "Policy ID does not belong to the specified AI Gateway."
        )
    return locator, _host_ref(locator["host_id"])


def _host_for_scope(
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    scope_type,
    scope_name,
    provider_name=None,
):
    if scope_type == "model":
        if not provider_name:
            raise InvalidArgumentValueError(
                "--provider-name is required for a model policy."
            )
        host_id = _models_path(
            subscription_id,
            resource_group_name,
            gateway_name,
            workspace_name,
            provider_name,
            scope_name,
        )
    else:
        host_id = _mcp_path(
            subscription_id,
            resource_group_name,
            gateway_name,
            workspace_name,
            scope_name,
        )
    return _host_ref(host_id)


def _read_host(cmd, host_ref):
    response = _request(cmd, "GET", host_ref["host_id"])
    host = _response_json(response)
    etag = (
        response.headers.get("ETag")
        or response.headers.get("etag")
        or host.get("etag")
    )
    return host, etag


def _mutate_policies(cmd, host_ref, mutate):
    if host_ref["scope_type"] == "mcp":
        properties, etag = _get_with_secrets(
            cmd,
            host_ref["host_id"],
            host_ref["scope_name"],
        )
        properties = deepcopy(properties)
        policies = list(properties.get("policies") or [])
        result = mutate(policies)
        if result is None:
            return None
        properties["policies"] = policies
        properties["endpoints"] = _clean_endpoints(
            properties.get("endpoints") or []
        )
        for field in ["mcpEndpointUrl", "state", "provisioningState"]:
            properties.pop(field, None)
        headers = {"If-Match": etag} if etag else None
        _response_json(
            _request(
                cmd,
                "PUT",
                host_ref["host_id"],
                {"properties": properties},
                headers=headers,
            )
        )
        return result

    host, etag = _read_host(cmd, host_ref)
    policies = list((host.get("properties") or {}).get("policies") or [])
    result = mutate(policies)
    if result is None:
        return None
    headers = {"If-Match": etag} if etag else None
    _response_json(
        _request(
            cmd,
            "PATCH",
            host_ref["host_id"],
            {"properties": {"policies": policies}},
            headers=headers,
        )
    )
    return result


def _list_model_hosts(
    cmd,
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    provider_name=None,
    model_name=None,
):
    if model_name:
        return [
            _host_for_scope(
                subscription_id,
                resource_group_name,
                gateway_name,
                workspace_name,
                "model",
                model_name,
                provider_name,
            )
        ]

    gateway_path = _gateway_path(
        subscription_id,
        resource_group_name,
        gateway_name,
    )
    if provider_name:
        providers = [{"name": provider_name}]
    else:
        providers_path = (
            f"{gateway_path}/workspaces/{quote(workspace_name, safe='')}"
            "/modelProviders"
        )
        providers = _list_all_models(cmd, providers_path)

    hosts = []
    for provider in providers:
        models_path = _models_path(
            subscription_id,
            resource_group_name,
            gateway_name,
            workspace_name,
            provider["name"],
        )
        for model in _list_all_models(cmd, models_path):
            hosts.append(
                _host_for_scope(
                    subscription_id,
                    resource_group_name,
                    gateway_name,
                    workspace_name,
                    "model",
                    model["name"],
                    provider["name"],
                )
            )
    return hosts


def _list_mcp_hosts(
    cmd,
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    mcp_name=None,
):
    if mcp_name:
        return [
            _host_for_scope(
                subscription_id,
                resource_group_name,
                gateway_name,
                workspace_name,
                "mcp",
                mcp_name,
            )
        ]
    path = _mcp_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
    )
    return [
        _host_for_scope(
            subscription_id,
            resource_group_name,
            gateway_name,
            workspace_name,
            "mcp",
            server["name"],
        )
        for server in _list_all_mcp(cmd, path)
    ]


def list_policies(
    cmd,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
    scope_type=None,
    scope_name=None,
    provider_name=None,
):
    if scope_name and not scope_type:
        raise InvalidArgumentValueError(
            "--scope-name requires --scope-type."
        )
    if scope_type == "model" and scope_name and not provider_name:
        raise InvalidArgumentValueError(
            "--provider-name is required when listing one model."
        )

    logger.warning(
        "Retrieving and compiling policies across gateway resources..."
    )
    subscription_id = get_subscription_id(cmd.cli_ctx)
    hosts = []
    if scope_type in {None, "model"}:
        hosts.extend(
            _list_model_hosts(
                cmd,
                subscription_id,
                resource_group_name,
                gateway_name,
                workspace_name,
                provider_name,
                scope_name if scope_type == "model" else None,
            )
        )
    if scope_type in {None, "mcp"}:
        hosts.extend(
            _list_mcp_hosts(
                cmd,
                subscription_id,
                resource_group_name,
                gateway_name,
                workspace_name,
                scope_name if scope_type == "mcp" else None,
            )
        )

    results = []
    for host_ref in hosts:
        host, _ = _read_host(cmd, host_ref)
        for index, policy in enumerate(
            (host.get("properties") or {}).get("policies") or []
        ):
            results.append(_result(host_ref, index, policy))
    return results


def show_policy(
    cmd,
    gateway_name,
    resource_group_name,
    policy_id,
):
    locator, host_ref = _gateway_and_host(
        cmd,
        gateway_name,
        resource_group_name,
        policy_id,
    )
    host, _ = _read_host(cmd, host_ref)
    policies = (host.get("properties") or {}).get("policies") or []
    index = _locate(policies, locator)
    if index < 0:
        raise ResourceNotFoundError("Policy was not found.")
    return _result(host_ref, index, policies[index])


def create_policy(
    cmd,
    gateway_name,
    resource_group_name,
    scope_type,
    scope_name,
    policy,
    workspace_name=DEFAULT_WORKSPACE,
    provider_name=None,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    host_ref = _host_for_scope(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        scope_type,
        scope_name,
        provider_name,
    )

    def append_policy(policies):
        policies.append(policy)
        return len(policies) - 1

    index = _mutate_policies(cmd, host_ref, append_policy)
    return _result(host_ref, index, policy)


def update_policy(
    cmd,
    gateway_name,
    resource_group_name,
    policy_id,
    policy,
):
    locator, host_ref = _gateway_and_host(
        cmd,
        gateway_name,
        resource_group_name,
        policy_id,
    )
    def replace_policy(policies):
        index = _locate(policies, locator)
        if index < 0:
            raise ResourceNotFoundError("Policy was not found.")
        policies[index] = policy
        return index

    index = _mutate_policies(cmd, host_ref, replace_policy)
    return _result(host_ref, index, policy)


def delete_policy(
    cmd,
    gateway_name,
    resource_group_name,
    policy_id,
):
    locator, host_ref = _gateway_and_host(
        cmd,
        gateway_name,
        resource_group_name,
        policy_id,
    )
    def remove_policy(policies):
        index = _locate(policies, locator)
        if index < 0:
            return None
        policies.pop(index)
        return True

    _mutate_policies(cmd, host_ref, remove_policy)
