# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_ai_gateway import _monitoring


class FakeResponse:

    def __init__(self, body=None, status_code=200):
        self._body = body
        self.status_code = status_code
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://otel.example.com/v1/traces",
        "https://user%3Aname@otel.example.com/v1/traces",
        "https://otel.example.com/v1/traces?api-key=value",
        "https://otel.example.com/v1/traces#fragment",
        "https://otel.example.com/v1/traces\r\nX-Injected: value",
    ],
)
def test_validate_endpoint_rejects_unsafe_urls(endpoint):
    with pytest.raises(InvalidArgumentValueError):
        _monitoring._validate_endpoint(endpoint, "--traces-endpoint")


@patch("azext_ai_gateway._monitoring.get_subscription_id", return_value="gateway-sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_configure_existing_application_insights(send_request, _, cmd):
    app_insights_id = (
        "/subscriptions/monitor-sub/resourceGroups/monitor-rg/providers/"
        "Microsoft.Insights/components/app"
    )
    dcr_id = (
        "/subscriptions/monitor-sub/resourceGroups/monitor-rg/providers/"
        "Microsoft.Insights/dataCollectionRules/dcr"
    )
    send_request.side_effect = [
        FakeResponse(
            {
                "identity": {
                    "type": "SystemAssigned",
                    "principalId": "principal",
                }
            }
        ),
        FakeResponse(
            {
                "id": app_insights_id,
                "properties": {
                    "DataCollectionRuleResourceId": dcr_id,
                    "OTLPMetricsEndpoint": "https://metrics/v1/metrics",
                    "OTLPLogsEndpoint": "https://logs/v1/logs",
                    "OTLPTracesEndpoint": "https://logs/v1/traces",
                },
            }
        ),
        FakeResponse({"properties": {}}),
        FakeResponse(
            {
                "name": "appinsights",
                "properties": {"kind": "OpenTelemetry"},
            }
        ),
    ]

    result = _monitoring.configure_application_insights(
        cmd,
        "gateway",
        "gateway-rg",
        app_insights_id,
        payload_capture=True,
    )

    role_call = send_request.call_args_list[2]
    role_body = json.loads(role_call.kwargs["body"])
    assert role_call.args[1] == "PUT"
    assert role_call.args[2].startswith(f"{dcr_id}/providers/")
    assert role_body["properties"] == {
        "roleDefinitionId": (
            "/subscriptions/monitor-sub/providers/Microsoft.Authorization/"
            "roleDefinitions/"
            f"{_monitoring.MONITORING_METRICS_PUBLISHER_ROLE_ID}"
        ),
        "principalId": "principal",
        "principalType": "ServicePrincipal",
    }

    exporter_call = send_request.call_args_list[3]
    exporter_body = json.loads(exporter_call.kwargs["body"])
    assert exporter_call.args[2].endswith(
        "/workspaces/default/telemetryExporters/appinsights"
    )
    assert exporter_body == {
        "properties": {
            "kind": "OpenTelemetry",
            "tracing": True,
            "payloadCapture": True,
            "applicationInsights": {"resourceId": app_insights_id},
            "openTelemetry": {
                "metricsEndpoint": "https://metrics/v1/metrics",
                "logsEndpoint": "https://logs/v1/logs",
                "tracesEndpoint": "https://logs/v1/traces",
                "managedIdentity": {
                    "resource": "https://monitor.azure.com",
                },
            },
        }
    }
    assert result["properties"]["kind"] == "openTelemetry"


@patch("azext_ai_gateway._monitoring.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._monitoring._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_configure_enables_identity_and_synthesizes_otlp_endpoints(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    app_insights_id = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.Insights/components/app"
    )
    dcr_id = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.Insights/dataCollectionRules/dcr"
    )
    dce_id = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.Insights/dataCollectionEndpoints/dce"
    )
    wait_for_gateway.return_value = {
        "identity": {
            "type": "SystemAssigned",
            "principalId": "principal",
        }
    }
    send_request.side_effect = [
        FakeResponse({"identity": {"type": "None"}}),
        FakeResponse({"properties": {"provisioningState": "Updating"}}),
        FakeResponse({"id": app_insights_id, "properties": {}}),
        FakeResponse(),
        FakeResponse(
            {
                "id": app_insights_id,
                "properties": {"DataCollectionRuleResourceId": dcr_id},
            }
        ),
        FakeResponse(
            {
                "id": dcr_id,
                "properties": {
                    "immutableId": "dcr-immutable",
                    "dataCollectionEndpointId": dce_id,
                },
            }
        ),
        FakeResponse(
            {
                "properties": {
                    "metricsIngestion": {"endpoint": "https://metrics/"},
                    "logsIngestion": {"endpoint": "https://logs/"},
                }
            }
        ),
        FakeResponse({"properties": {}}),
        FakeResponse({"properties": {"kind": "OpenTelemetry"}}),
    ]

    _monitoring.configure_application_insights(
        cmd,
        "gateway",
        "rg",
        app_insights_id,
    )

    identity_body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert identity_body == {"identity": {"type": "SystemAssigned"}}
    otlp_call = send_request.call_args_list[3]
    assert json.loads(otlp_call.kwargs["body"]) == {
        "properties": {"AzureMonitorWorkspaceIngestionMode": "Enabled"}
    }
    exporter_body = json.loads(send_request.call_args_list[-1].kwargs["body"])
    assert exporter_body["properties"]["openTelemetry"][
        "metricsEndpoint"
    ] == (
        "https://metrics/dataCollectionRules/dcr-immutable/streams/"
        "Microsoft-OtelMetrics/otlp/v1/metrics"
    )


def test_application_insights_id_must_be_complete(cmd):
    with pytest.raises(
        InvalidArgumentValueError,
        match="complete Azure Application Insights",
    ):
        _monitoring.configure_application_insights(
            cmd,
            "gateway",
            "rg",
            "app",
        )


@patch("azext_ai_gateway._monitoring.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_unassigned_explicit_identity_fails_without_enabling_system_identity(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"identity": {"type": "None"}})

    with pytest.raises(
        InvalidArgumentValueError,
        match="is not assigned",
    ):
        _monitoring.configure_application_insights(
            cmd,
            "gateway",
            "rg",
            (
                "/subscriptions/sub/resourceGroups/rg/providers/"
                "Microsoft.Insights/components/app"
            ),
            identity_client_id="client-id",
        )

    assert send_request.call_count == 1


@patch("azext_ai_gateway._monitoring.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_configure_custom_otlp_with_headers(send_request, _, cmd):
    send_request.return_value = FakeResponse(
        {"properties": {"kind": "OpenTelemetry"}}
    )

    result = _monitoring.configure_monitoring(
        cmd,
        "gateway",
        "rg",
        metrics_endpoint="https://otel.example.com/v1/metrics",
        logs_endpoint="https://otel.example.com/v1/logs",
        traces_endpoint="https://otel.example.com/v1/traces",
        headers={" x-api-key ": "secret"},
    )

    assert send_request.call_count == 1
    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "properties": {
            "kind": "OpenTelemetry",
            "tracing": True,
            "payloadCapture": False,
            "openTelemetry": {
                "metricsEndpoint": "https://otel.example.com/v1/metrics",
                "logsEndpoint": "https://otel.example.com/v1/logs",
                "tracesEndpoint": "https://otel.example.com/v1/traces",
                "headers": {"x-api-key": "secret"},
            },
        }
    }
    assert result["properties"]["kind"] == "openTelemetry"


@patch("azext_ai_gateway._monitoring.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_configure_custom_otlp_with_user_assigned_identity(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "identity": {
                    "type": "UserAssigned",
                    "userAssignedIdentities": {
                        "/identities/otel": {
                            "clientId": "client",
                            "principalId": "principal",
                        }
                    },
                }
            }
        ),
        FakeResponse({"properties": {"kind": "OpenTelemetry"}}),
    ]

    _monitoring.configure_monitoring(
        cmd,
        "gateway",
        "rg",
        metrics_endpoint="https://otel.example.com/v1/metrics",
        logs_endpoint="https://otel.example.com/v1/logs",
        traces_endpoint="https://otel.example.com/v1/traces",
        managed_identity_resource="https://otel.example.com",
        identity_client_id="client",
    )

    body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert "applicationInsights" not in body["properties"]
    assert body["properties"]["openTelemetry"]["managedIdentity"] == {
        "resource": "https://otel.example.com",
        "clientId": "client",
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (
            {"metrics_endpoint": "https://otel.example.com/v1/metrics"},
            "together",
        ),
        (
            {
                "metrics_endpoint": "http://otel.example.com/v1/metrics",
                "logs_endpoint": "https://otel.example.com/v1/logs",
                "traces_endpoint": "https://otel.example.com/v1/traces",
                "headers": {"x-api-key": "secret"},
            },
            "absolute HTTPS URL",
        ),
        (
            {
                "metrics_endpoint": "https://otel.example.com/v1/metrics",
                "logs_endpoint": "https://otel.example.com/v1/logs",
                "traces_endpoint": "https://otel.example.com/v1/traces",
            },
            "--headers or --managed-identity-resource",
        ),
        (
            {
                "metrics_endpoint": "https://otel.example.com/v1/metrics",
                "logs_endpoint": "https://otel.example.com/v1/logs",
                "traces_endpoint": "https://otel.example.com/v1/traces",
                "headers": {"Authorization": "secret"},
            },
            "Authorization header is reserved",
        ),
    ],
)
def test_custom_otlp_validation(cmd, kwargs, message):
    with pytest.raises(InvalidArgumentValueError, match=message):
        _monitoring.configure_monitoring(cmd, "gateway", "rg", **kwargs)


def test_deterministic_guid_matches_portal_algorithm():
    assert _monitoring._deterministic_guid("principal", "/scope", "role") == (
        "d97b46bb-ea06-49d5-9b43-3f85336ca5e8"
    )
