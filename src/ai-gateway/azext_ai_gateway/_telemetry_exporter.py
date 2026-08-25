# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

"""Telemetry exporter command implementations."""

import hashlib
import re
import time
from copy import deepcopy
from urllib.parse import quote, urlsplit

from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    InvalidArgumentValueError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from knack.log import get_logger

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
    _wait_for_gateway,
)
from azext_ai_gateway._progress import (
    long_running_progress,
    report_lro_accepted,
)

APP_INSIGHTS_API_VERSION = "2020-02-02"
APP_INSIGHTS_OTLP_API_VERSION = "2020-02-02-preview"
MONITOR_API_VERSION = "2023-03-11"
RESOURCE_GRAPH_API_VERSION = "2022-10-01"
ROLE_ASSIGNMENTS_API_VERSION = "2022-04-01"
IDENTITY_API_VERSION = "2024-05-01"
DEFAULT_WORKSPACE = "default"
logger = get_logger(__name__)
MONITORING_METRICS_PUBLISHER_ROLE_ID = (
    "3913510d-42f4-4e42-8a64-420c390055eb"
)
MONITOR_AUDIENCE = "https://monitor.azure.com"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120
APP_INSIGHTS_ID_PATTERN = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/resourceGroups/[^/]+/"
    r"providers/Microsoft\.Insights/components/[^/]+$",
    re.IGNORECASE,
)
IMMUTABLE_ID_PATTERN = re.compile(
    r"/dataCollectionRules/([^/?]+)",
    re.IGNORECASE,
)


def _validate_app_insights_id(resource_id):
    resource_id = (resource_id or "").strip().rstrip("/")
    match = APP_INSIGHTS_ID_PATTERN.fullmatch(resource_id)
    if not match:
        raise InvalidArgumentValueError(
            "--application-insights must be a complete Azure Application "
            "Insights component resource ID."
        )
    return resource_id, match.group("subscription")


def _validate_endpoint(endpoint, option_name):
    endpoint = (endpoint or "").strip()
    if any(
        ord(character) < 32 or ord(character) == 127
        for character in endpoint
    ):
        raise InvalidArgumentValueError(
            f"{option_name} cannot contain control characters."
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
            f"{option_name} must be an absolute HTTPS URL without embedded "
            "credentials, a query string, or a fragment, and must include the "
            "full signal path."
        )
    try:
        parsed.port
    except ValueError as error:
        raise InvalidArgumentValueError(
            f"{option_name} contains an invalid port."
        ) from error
    return endpoint


def _custom_configuration(
    metrics_endpoint,
    logs_endpoint,
    traces_endpoint,
):
    endpoints = {
        "metrics_endpoint": (metrics_endpoint, "--metrics-endpoint"),
        "logs_endpoint": (logs_endpoint, "--logs-endpoint"),
        "traces_endpoint": (traces_endpoint, "--traces-endpoint"),
    }
    configuration = {
        name: _validate_endpoint(value, option_name)
        for name, (value, option_name) in endpoints.items()
        if value and value.strip()
    }
    if not configuration:
        return None
    return configuration


def _validate_headers(headers):
    if headers is None:
        return None
    if not isinstance(headers, dict) or not headers:
        raise InvalidArgumentValueError(
            "--headers must contain non-empty string names and values."
        )
    normalized = {}
    normalized_names = set()
    for name, value in headers.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(value, str)
            or not value.strip()
        ):
            raise InvalidArgumentValueError(
                "--headers must contain non-empty string names and values."
            )
        normalized_name = name.strip().casefold()
        if normalized_name in normalized_names:
            raise InvalidArgumentValueError(
                "Header names must be unique, ignoring case."
            )
        normalized_names.add(normalized_name)
        normalized[name.strip()] = value
    return normalized


def _deterministic_guid(*parts):
    digest = bytearray(
        hashlib.sha256("|".join(parts).encode("utf-8")).digest()[:16]
    )
    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80
    value = digest.hex()
    return (
        f"{value[:8]}-{value[8:12]}-{value[12:16]}-"
        f"{value[16:20]}-{value[20:]}"
    )


def _get(cmd, path, api_version):
    return _response_json(
        _request(cmd, "GET", path, api_version=api_version)
    )


def _get_app_insights(cmd, resource_id):
    try:
        return _get(cmd, resource_id, APP_INSIGHTS_API_VERSION)
    except HTTPError as error:
        if error.response.status_code == 404:
            raise ResourceNotFoundError(
                f"Application Insights resource '{resource_id}' was not found."
            ) from None
        raise


def _dcr_resource_id(resource):
    properties = resource.get("properties") or {}
    current = str(properties.get("DataCollectionRuleResourceId") or "").strip()
    if current:
        return current
    legacy = str(properties.get("DataCollectionRuleId") or "").strip()
    return legacy if legacy.startswith("/") else None


def _dcr_immutable_id(resource):
    properties = resource.get("properties") or {}
    legacy = str(properties.get("DataCollectionRuleId") or "").strip()
    if legacy and not legacy.startswith("/"):
        return legacy
    for property_name in [
        "OTLPMetricsEndpoint",
        "OTLPLogsEndpoint",
        "OTLPTracesEndpoint",
    ]:
        match = IMMUTABLE_ID_PATTERN.search(
            str(properties.get(property_name) or "")
        )
        if match:
            return match.group(1)
    return None


def _direct_configuration(resource):
    properties = resource.get("properties") or {}
    configuration = {
        "dcr_id": _dcr_resource_id(resource),
        "metrics_endpoint": properties.get("OTLPMetricsEndpoint"),
        "logs_endpoint": properties.get("OTLPLogsEndpoint"),
        "traces_endpoint": properties.get("OTLPTracesEndpoint"),
    }
    if all(configuration.values()):
        return configuration
    return None


def _find_dcr(cmd, immutable_id):
    escaped = immutable_id.replace("'", "''")
    query = (
        "resources\n"
        "| where type =~ 'microsoft.insights/datacollectionrules'\n"
        f"| where tostring(properties.immutableId) =~ '{escaped}'\n"
        "| project id\n"
        "| take 1"
    )
    response = _response_json(
        _request(
            cmd,
            "POST",
            "/providers/Microsoft.ResourceGraph/resources",
            {"query": query},
            api_version=RESOURCE_GRAPH_API_VERSION,
        )
    )
    rows = response.get("data") or []
    return rows[0].get("id") if rows else None


def _synthesize_configuration(cmd, resource):
    dcr_id = _dcr_resource_id(resource)
    if not dcr_id:
        immutable_id = _dcr_immutable_id(resource)
        if immutable_id:
            dcr_id = _find_dcr(cmd, immutable_id)
    if not dcr_id:
        return None

    dcr = _get(cmd, dcr_id, MONITOR_API_VERSION)
    properties = dcr.get("properties") or {}
    immutable_id = properties.get("immutableId")
    dce_id = properties.get("dataCollectionEndpointId")
    if not immutable_id or not dce_id:
        return None

    dce = _get(cmd, dce_id, MONITOR_API_VERSION)
    dce_properties = dce.get("properties") or {}
    logs_base = ((dce_properties.get("logsIngestion") or {}).get("endpoint"))
    metrics_base = (
        (dce_properties.get("metricsIngestion") or {}).get("endpoint")
    )
    if not logs_base or not metrics_base:
        return None

    prefix = f"/dataCollectionRules/{immutable_id}/streams"
    return {
        "dcr_id": dcr.get("id") or dcr_id,
        "metrics_endpoint": (
            f"{metrics_base.rstrip('/')}{prefix}/"
            "Microsoft-OtelMetrics/otlp/v1/metrics"
        ),
        "logs_endpoint": (
            f"{logs_base.rstrip('/')}{prefix}/"
            "Microsoft-OTLP-Logs/otlp/v1/logs"
        ),
        "traces_endpoint": (
            f"{logs_base.rstrip('/')}{prefix}/"
            "Microsoft-OTLP-Traces/otlp/v1/traces"
        ),
    }


def _resolve_otlp_configuration(cmd, resource_id):
    resource = _get_app_insights(cmd, resource_id)
    configuration = (
        _direct_configuration(resource)
        or _synthesize_configuration(cmd, resource)
    )
    if configuration:
        return resource, configuration

    _request(
        cmd,
        "PATCH",
        resource_id,
        {"properties": {"AzureMonitorWorkspaceIngestionMode": "Enabled"}},
        api_version=APP_INSIGHTS_OTLP_API_VERSION,
    )
    report_lro_accepted(
        cmd,
        "Application Insights OpenTelemetry enablement request accepted.",
    )
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    message = "Waiting for Application Insights OpenTelemetry endpoints"
    with long_running_progress(cmd, message) as progress:
        while time.monotonic() <= deadline:
            resource = _get_app_insights(cmd, resource_id)
            configuration = (
                _direct_configuration(resource)
                or _synthesize_configuration(cmd, resource)
            )
            if configuration:
                return resource, configuration
            progress.wait(POLL_INTERVAL_SECONDS)

        raise AzureResponseError(
            "Timed out waiting for Application Insights OTLP endpoints after "
            f"{POLL_TIMEOUT_SECONDS} seconds."
        )


def _identity_candidates(identity):
    candidates = []
    identity_type = identity.get("type") or ""
    if "SystemAssigned" in identity_type and identity.get("principalId"):
        candidates.append(
            {
                "principal_id": identity["principalId"],
                "client_id": None,
            }
        )
    for details in (identity.get("userAssignedIdentities") or {}).values():
        if details.get("principalId"):
            candidates.append(
                {
                    "principal_id": details["principalId"],
                    "client_id": details.get("clientId"),
                }
            )
    return candidates


def _resolve_identity(
    cmd,
    gateway_path,
    gateway_name,
    identity_client_id,
):
    gateway = _get(cmd, gateway_path, IDENTITY_API_VERSION)
    candidates = _identity_candidates(gateway.get("identity") or {})
    if not candidates and identity_client_id:
        raise InvalidArgumentValueError(
            f"Managed identity client ID '{identity_client_id}' is not "
            f"assigned to AI Gateway '{gateway_name}'."
        )
    if not candidates:
        _request(
            cmd,
            "PATCH",
            gateway_path,
            {"identity": {"type": "SystemAssigned"}},
            api_version=IDENTITY_API_VERSION,
        )
        report_lro_accepted(
            cmd,
            f"Identity assignment for AI Gateway '{gateway_name}' accepted.",
        )
        gateway = _wait_for_gateway(cmd, gateway_path, gateway_name)
        candidates = _identity_candidates(gateway.get("identity") or {})

    if identity_client_id:
        for candidate in candidates:
            if (
                str(candidate.get("client_id") or "").casefold()
                == identity_client_id.casefold()
            ):
                return candidate
        raise InvalidArgumentValueError(
            f"Managed identity client ID '{identity_client_id}' is not "
            f"assigned to AI Gateway '{gateway_name}'."
        )
    if not candidates:
        raise AzureResponseError(
            f"AI Gateway '{gateway_name}' has no usable managed identity."
        )
    return candidates[0]


def _assign_monitoring_role(
    cmd,
    scope,
    subscription_id,
    principal_id,
):
    assignment_id = _deterministic_guid(
        principal_id,
        scope,
        MONITORING_METRICS_PUBLISHER_ROLE_ID,
    )
    role_definition_id = (
        f"/subscriptions/{subscription_id}/providers/"
        "Microsoft.Authorization/roleDefinitions/"
        f"{MONITORING_METRICS_PUBLISHER_ROLE_ID}"
    )
    path = (
        f"{scope.rstrip('/')}/providers/Microsoft.Authorization/"
        f"roleAssignments/{assignment_id}"
    )
    try:
        _request(
            cmd,
            "PUT",
            path,
            {
                "properties": {
                    "roleDefinitionId": role_definition_id,
                    "principalId": principal_id,
                    "principalType": "ServicePrincipal",
                }
            },
            api_version=ROLE_ASSIGNMENTS_API_VERSION,
        )
    except HTTPError as error:
        if error.response.status_code != 409:
            raise


def _exporter_path(
    gateway_path,
    workspace_name,
    exporter_name=None,
):
    path = (
        f"{gateway_path}/workspaces/{quote(workspace_name, safe='')}"
        "/telemetryExporters"
    )
    if exporter_name is not None:
        path += f"/{quote(exporter_name, safe='')}"
    return path


def _normalize_exporter(exporter):
    if not exporter:
        return exporter
    normalized = deepcopy(exporter)
    properties = normalized.get("properties") or {}
    if properties.get("kind") == "OpenTelemetry":
        properties["kind"] = "openTelemetry"
    open_telemetry = properties.get("openTelemetry") or {}
    credentials = open_telemetry.get("credentials") or {}
    headers = credentials.get("headers")
    if isinstance(headers, dict):
        credentials["headers"] = {
            name: "******"
            for name in headers
        }
    legacy_headers = open_telemetry.get("headers")
    if isinstance(legacy_headers, dict):
        open_telemetry["headers"] = {
            name: "******"
            for name in legacy_headers
        }
    return normalized


def list_telemetry_exporters(
    cmd,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    gateway_path = _gateway_path(
        subscription_id,
        resource_group_name,
        gateway_name,
    )
    url = _exporter_path(gateway_path, workspace_name)
    exporters = []
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
        exporters.extend(
            _normalize_exporter(exporter)
            for exporter in page.get("value", [])
        )
        url = page.get("nextLink")
        include_api_version = False
    return exporters


def delete_telemetry_exporter(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    gateway_path = _gateway_path(
        subscription_id,
        resource_group_name,
        gateway_name,
    )
    _request(
        cmd,
        "DELETE",
        _exporter_path(gateway_path, workspace_name, name),
        headers={"If-Match": "*"},
    )


def create_telemetry_exporter(
    cmd,
    gateway_name,
    resource_group_name,
    name,
    application_insights=None,
    workspace_name=DEFAULT_WORKSPACE,
    identity_client_id=None,
    metrics_endpoint=None,
    logs_endpoint=None,
    traces_endpoint=None,
    headers=None,
    managed_identity_resource=None,
    payload_capture=False,
):
    if payload_capture:
        logger.warning(
            "Payload capture exports AI Gateway request and response content. "
            "Confirm that the telemetry destination and retention policy are "
            "approved for potentially sensitive data."
        )
    custom_configuration = _custom_configuration(
        metrics_endpoint,
        logs_endpoint,
        traces_endpoint,
    )
    if bool(application_insights) == bool(custom_configuration):
        raise InvalidArgumentValueError(
            "Specify either --application-insights or at least one custom "
            "OpenTelemetry endpoint option."
        )
    headers = _validate_headers(headers)
    if headers is not None and managed_identity_resource:
        raise InvalidArgumentValueError(
            "--headers and --managed-identity-resource cannot be used together."
        )
    if application_insights and (headers is not None or managed_identity_resource):
        raise InvalidArgumentValueError(
            "Custom --headers and --managed-identity-resource options cannot "
            "be used with --application-insights."
        )
    if custom_configuration and identity_client_id and not managed_identity_resource:
        raise InvalidArgumentValueError(
            "--identity-client-id requires --managed-identity-resource for a "
            "custom OpenTelemetry destination."
        )
    if managed_identity_resource:
        managed_identity_resource = _validate_endpoint(
            managed_identity_resource,
            "--managed-identity-resource",
        )
    insights_subscription = None
    if application_insights:
        application_insights, insights_subscription = (
            _validate_app_insights_id(application_insights)
        )

    gateway_subscription = get_subscription_id(cmd.cli_ctx)
    gateway_path = _gateway_path(
        gateway_subscription,
        resource_group_name,
        gateway_name,
    )
    application_insights_properties = None
    managed_identity = None
    if application_insights:
        identity = _resolve_identity(
            cmd,
            gateway_path,
            gateway_name,
            identity_client_id,
        )
        resource, configuration = _resolve_otlp_configuration(
            cmd,
            application_insights,
        )
        _assign_monitoring_role(
            cmd,
            configuration["dcr_id"],
            insights_subscription,
            identity["principal_id"],
        )
        application_insights_properties = {
            "resourceId": resource.get("id") or application_insights
        }
        managed_identity = {"resource": MONITOR_AUDIENCE}
        if identity["client_id"]:
            managed_identity["clientId"] = identity["client_id"]
    else:
        configuration = custom_configuration
        if managed_identity_resource:
            identity = _resolve_identity(
                cmd,
                gateway_path,
                gateway_name,
                identity_client_id,
            )
            managed_identity = {"resource": managed_identity_resource}
            if identity["client_id"]:
                managed_identity["clientId"] = identity["client_id"]

    open_telemetry = {}
    for configuration_name, property_name in [
        ("metrics_endpoint", "metricsEndpoint"),
        ("logs_endpoint", "logsEndpoint"),
        ("traces_endpoint", "tracesEndpoint"),
    ]:
        if configuration.get(configuration_name):
            open_telemetry[property_name] = configuration[configuration_name]
    credentials = {}
    if headers is not None:
        credentials["headers"] = headers
    if managed_identity:
        credentials["managedIdentity"] = managed_identity
    if credentials:
        open_telemetry["credentials"] = credentials
    properties = {
        "kind": "OpenTelemetry",
        "payloadCapture": payload_capture,
        "openTelemetry": open_telemetry,
    }
    if application_insights_properties:
        properties["applicationInsights"] = application_insights_properties
    exporter = _response_json(
        _request(
            cmd,
            "PUT",
            _exporter_path(gateway_path, workspace_name, name),
            {"properties": properties},
        )
    )
    return _normalize_exporter(exporter)
