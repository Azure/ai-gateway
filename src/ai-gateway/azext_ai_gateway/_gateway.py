# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import codecs
import json
import logging
import re
import time
from contextlib import contextmanager
from urllib.parse import quote, unquote

from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import send_raw_request

from azext_ai_gateway._progress import (
    long_running_progress,
    report_lro_accepted,
)

API_VERSION = "2025-09-01-preview"
DEFAULT_PUBLISHER_EMAIL = "noreply@aigateway.azure.com"
DEFAULT_PUBLISHER_NAME = "AI Gateway Administrator"
AI_GATEWAY_REGIONS = (
    {"name": "eastus2", "displayName": "East US 2"},
    {"name": "swedencentral", "displayName": "Sweden Central"},
)
PROVIDER_PATH = "Microsoft.ApiManagement/service"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300
_SENSITIVE_FIELD_NAMES = {
    "apikey",
    "clientsecret",
    "credentials",
    "headers",
    "secret",
}
_SENSITIVE_URL_SEGMENTS = (
    "/apikeys/",
    "/exporters/",
    "/modelproviders/",
    "/toolservers/",
)
_SERVICE_ERROR_CODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_SUBNET_RESOURCE_ID = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Network/virtualNetworks/[^/]+/subnets/[^/]+$",
    re.IGNORECASE,
)


def _resource_group_name(resource):
    segments = str(resource.get("id") or "").split("/")
    for index, segment in enumerate(segments[:-1]):
        if segment.casefold() == "resourcegroups":
            return unquote(segments[index + 1])
    return ""


def format_gateway_list_table(gateways):
    return [
        {
            "Name": gateway.get("name") or "",
            "ResourceGroup": _resource_group_name(gateway),
            "Location": gateway.get("location") or "",
            "Runtime URL": (gateway.get("properties") or {}).get("gatewayUrl")
            or "",
        }
        for gateway in gateways
    ]


class _DenyAllLogs(logging.Filter):

    def filter(self, record):
        del record
        return False


@contextmanager
def _suppress_raw_http_logging():
    raw_request_logger = logging.getLogger(send_raw_request.__module__)
    deny_filter = _DenyAllLogs()
    raw_request_logger.addFilter(deny_filter)
    try:
        yield
    finally:
        raw_request_logger.removeFilter(deny_filter)


def _contains_sensitive_data(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = str(key).replace("-", "").replace("_", "").casefold()
            if (
                normalized_key in _SENSITIVE_FIELD_NAMES
                or "secret" in normalized_key
            ):
                return True
            if _contains_sensitive_data(child):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_data(item) for item in value)
    return False


def _is_policy_only_body(body):
    if not isinstance(body, dict) or set(body) != {"properties"}:
        return False
    properties = body["properties"]
    return (
        isinstance(properties, dict)
        and set(properties) == {"policies"}
        and isinstance(properties["policies"], list)
    )


def _is_sensitive_request(url, body):
    if _is_policy_only_body(body) and not _contains_sensitive_data(body):
        return False
    normalized_url = str(url).rstrip("/").casefold()
    return (
        normalized_url.endswith("/listsecrets")
        or any(segment in normalized_url for segment in _SENSITIVE_URL_SEGMENTS)
        or _contains_sensitive_data(body)
    )


def _service_error_details(response):
    if response is None or not getattr(response, "content", None):
        return None, None, []
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return None, None, []
    if not isinstance(payload, dict):
        return None, None, []

    service_error = payload.get("error")
    if not isinstance(service_error, dict):
        service_error = payload
    code = service_error.get("code")
    description = service_error.get("message") or service_error.get("description")
    if isinstance(code, str):
        code = code.strip()
    if isinstance(description, str):
        description = description.strip()
    details = []
    for detail in service_error.get("details") or []:
        if not isinstance(detail, dict):
            continue
        detail_code = detail.get("code")
        target = detail.get("target")
        detail_description = detail.get("message") or detail.get("description")
        if isinstance(detail_code, str):
            detail_code = detail_code.strip()
        if not (
            isinstance(detail_code, str)
            and _SERVICE_ERROR_CODE_PATTERN.fullmatch(detail_code)
        ):
            detail_code = None
        if isinstance(target, str):
            target = target.strip() or None
        else:
            target = None
        if isinstance(detail_description, str):
            detail_description = detail_description.strip() or None
        else:
            detail_description = None
        if detail_code or target or detail_description:
            details.append(
                {
                    "code": detail_code,
                    "target": target,
                    "description": detail_description,
                }
            )
    return (
        code
        if isinstance(code, str) and _SERVICE_ERROR_CODE_PATTERN.fullmatch(code)
        else None,
        description if isinstance(description, str) and description else None,
        details,
    )


def _format_service_error_detail(detail):
    description = detail["description"]
    target = detail["target"]
    code = detail["code"]
    lines = [f"  - Target: {target}" if target else "  - Detail"]
    if code:
        lines.append(f"    Code: {code}")
    if description:
        lines.append(f"    Description: {description}")
    return "\n".join(lines)


def _http_error_message(method, error, include_description):
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", "unknown")
    reason = getattr(response, "reason", None)
    code, description, details = _service_error_details(response)

    lines = [
        f"{method.upper()} request failed.",
        f"HTTP status: {status_code}" + (f" {reason}" if reason else ""),
    ]
    if code:
        lines.append(f"Code: {code}")
    if include_description and description:
        lines.append(f"Description: {description.rstrip(':')}")
    if include_description and details:
        lines.append("Details:")
        lines.extend(_format_service_error_detail(detail) for detail in details)
    return "\n".join(lines)


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
    api_version=API_VERSION,
):
    request_kwargs = {}
    if headers:
        request_kwargs["headers"] = [
            f"{header_name}={header_value}"
            for header_name, header_value in headers.items()
        ]
    try:
        with _suppress_raw_http_logging():
            return send_raw_request(
                cmd.cli_ctx,
                method,
                url,
                uri_parameters=[f"api-version={api_version}"]
                if include_api_version
                else None,
                body=json.dumps(body) if body is not None else None,
                **request_kwargs,
            )
    except HTTPError as error:
        message = _http_error_message(
            method,
            error,
            include_description=not _is_sensitive_request(url, body),
        )
        raise HTTPError(message, error.response) from None


def _response_json(response):
    if not response.content:
        return None
    if response.content.startswith(codecs.BOM_UTF8):
        return json.loads(response.content.decode("utf-8-sig"))
    return response.json()


def _get_resource(cmd, path):
    return _response_json(_request(cmd, "GET", path))


def _raise_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(f"AI Gateway '{name}' was not found.") from None
    raise error


def _wait_for_gateway(cmd, path, name, deleted=False):
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    action = "deletion" if deleted else "provisioning"
    message = f"Waiting for AI Gateway '{name}' {action}"
    with long_running_progress(cmd, message) as progress:
        while time.monotonic() <= deadline:
            try:
                resource = _get_resource(cmd, path)
            except HTTPError as error:
                if deleted and error.response.status_code == 404:
                    return None
                _raise_not_found(error, name)

            state = (resource.get("properties") or {}).get(
                "provisioningState"
            )
            if deleted:
                progress.update(
                    f"{message}"
                    + (f" (state: {state})" if state else "")
                )
                progress.wait(POLL_INTERVAL_SECONDS)
                continue

            if state == "Succeeded":
                return resource
            if state in {"Failed", "Canceled", "Cancelled"}:
                raise AzureResponseError(
                    f"AI Gateway '{name}' provisioning ended in state "
                    f"'{state}'."
                )
            progress.update(
                f"{message}" + (f" (state: {state})" if state else "")
            )
            progress.wait(POLL_INTERVAL_SECONDS)

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


def _networking_properties(
    public_network_access,
    virtual_network_type,
    subnet_resource_id,
):
    properties = {}
    if public_network_access is not None:
        properties["publicNetworkAccess"] = public_network_access

    subnet = (
        subnet_resource_id.strip()
        if subnet_resource_id is not None
        else None
    )
    if subnet and not _SUBNET_RESOURCE_ID.fullmatch(subnet):
        raise InvalidArgumentValueError(
            "--subnet-resource-id must be a full Microsoft.Network "
            "virtual network subnet resource ID."
        )

    if virtual_network_type == "None":
        if subnet:
            raise InvalidArgumentValueError(
                "--virtual-network-type None cannot be combined with a "
                "non-empty --subnet-resource-id."
            )
        properties["virtualNetworkType"] = "None"
        properties["virtualNetworkConfiguration"] = None
    elif virtual_network_type == "External":
        if not subnet:
            raise InvalidArgumentValueError(
                "--subnet-resource-id is required when "
                "--virtual-network-type is External."
            )
        properties["virtualNetworkType"] = "External"
        properties["virtualNetworkConfiguration"] = {
            "subnetResourceId": subnet
        }
    elif subnet is not None:
        if subnet:
            properties["virtualNetworkType"] = "External"
            properties["virtualNetworkConfiguration"] = {
                "subnetResourceId": subnet
            }
        else:
            properties["virtualNetworkType"] = "None"
            properties["virtualNetworkConfiguration"] = None

    return properties


def create_gateway(
    cmd,
    name=None,
    resource_group_name=None,
    location=None,
    publisher_email=DEFAULT_PUBLISHER_EMAIL,
    publisher_name=DEFAULT_PUBLISHER_NAME,
    tags=None,
    mi_system_assigned=None,
    mi_user_assigned=None,
    no_wait=False,
    list_regions=False,
):
    if list_regions:
        return [dict(region) for region in AI_GATEWAY_REGIONS]

    missing_options = [
        option
        for option, value in [
            ("--name", name),
            ("--resource-group", resource_group_name),
            ("--location", location),
        ]
        if not value
    ]
    if missing_options:
        raise RequiredArgumentMissingError(
            f"Specify {', '.join(missing_options)} when creating an AI Gateway, "
            "or use --list-regions to list supported regions."
        )

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
    report_lro_accepted(
        cmd,
        f"AI Gateway '{name}' create request accepted.",
    )
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


def show_gateway(
    cmd,
    name,
    resource_group_name,
):
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

    properties = _networking_properties(
        public_network_access,
        virtual_network_type,
        subnet_resource_id,
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

    if properties:
        body["properties"] = properties

    response = _response_json(_request(cmd, "PATCH", path, body))
    report_lro_accepted(
        cmd,
        f"AI Gateway '{name}' update request accepted.",
    )
    if no_wait:
        return response
    return _wait_for_gateway(cmd, path, name)


def delete_gateway(cmd, name, resource_group_name, no_wait=False):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _gateway_path(subscription_id, resource_group_name, name)
    _request(cmd, "DELETE", path)
    report_lro_accepted(
        cmd,
        f"AI Gateway '{name}' delete request accepted.",
    )
    if no_wait:
        return None
    return _wait_for_gateway(cmd, path, name, deleted=True)
