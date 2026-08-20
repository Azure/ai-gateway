# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_ai_gateway import _telemetry_exporter


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


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_exporters_follows_pages_and_redacts_headers(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "value": [
                    {
                        "name": "custom",
                        "properties": {
                            "kind": "OpenTelemetry",
                            "openTelemetry": {
                                "credentials": {
                                    "headers": {"x-api-key": "stored-value"}
                                }
                            },
                        },
                    }
                ],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        FakeResponse(
            {
                "value": [
                    {
                        "name": "appinsights",
                        "properties": {"kind": "OpenTelemetry"},
                    }
                ]
            }
        ),
    ]

    result = _telemetry_exporter.list_telemetry_exporters(
        cmd,
        "gateway",
        "rg",
        workspace_name="custom workspace",
    )

    assert [exporter["name"] for exporter in result] == [
        "custom",
        "appinsights",
    ]
    assert result[0]["properties"]["openTelemetry"]["credentials"][
        "headers"
    ] == {"x-api-key": "******"}
    assert result[1]["properties"]["kind"] == "openTelemetry"
    first_call, second_call = send_request.call_args_list
    assert first_call.args[2].endswith(
        "/workspaces/custom%20workspace/telemetryExporters"
    )
    assert second_call.args[2] == "https://management.azure.com/next"
    assert second_call.kwargs["uri_parameters"] is None


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_delete_exporter_uses_concurrency_precondition(send_request, _, cmd):
    send_request.return_value = FakeResponse()

    _telemetry_exporter.delete_telemetry_exporter(
        cmd,
        "custom/exporter",
        "gateway",
        "rg",
    )

    assert send_request.call_args.args[1:3] == (
        "DELETE",
        (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.ApiManagement/service/gateway/workspaces/default/"
            "telemetryExporters/custom%2Fexporter"
        ),
    )
    assert send_request.call_args.kwargs["headers"] == ["If-Match=*"]


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
        _telemetry_exporter._validate_endpoint(endpoint, "--traces-endpoint")


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="gateway-sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_exporter_for_existing_application_insights(send_request, _, cmd):
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

    result = _telemetry_exporter.create_telemetry_exporter(
        cmd,
        "gateway",
        "gateway-rg",
        "appinsights",
        application_insights=app_insights_id,
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
            f"{_telemetry_exporter.MONITORING_METRICS_PUBLISHER_ROLE_ID}"
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
            "payloadCapture": True,
            "applicationInsights": {"resourceId": app_insights_id},
            "openTelemetry": {
                "metricsEndpoint": "https://metrics/v1/metrics",
                "logsEndpoint": "https://logs/v1/logs",
                "tracesEndpoint": "https://logs/v1/traces",
                "credentials": {
                    "managedIdentity": {
                        "resource": "https://monitor.azure.com",
                    },
                },
            },
        }
    }
    assert result["properties"]["kind"] == "openTelemetry"


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._telemetry_exporter._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_exporter_enables_identity_and_synthesizes_otlp_endpoints(
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

    _telemetry_exporter.create_telemetry_exporter(
        cmd,
        "gateway",
        "rg",
        "appinsights",
        application_insights=app_insights_id,
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
        _telemetry_exporter.create_telemetry_exporter(
            cmd,
            "gateway",
            "rg",
            "appinsights",
            application_insights="app",
        )


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
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
        _telemetry_exporter.create_telemetry_exporter(
            cmd,
            "gateway",
            "rg",
            "appinsights",
            application_insights=(
                "/subscriptions/sub/resourceGroups/rg/providers/"
                "Microsoft.Insights/components/app"
            ),
            identity_client_id="client-id",
        )

    assert send_request.call_count == 1


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_custom_otlp_exporter_with_headers(send_request, _, cmd):
    send_request.return_value = FakeResponse(
        {"properties": {"kind": "OpenTelemetry"}}
    )

    result = _telemetry_exporter.create_telemetry_exporter(
        cmd,
        "gateway",
        "rg",
        "custom-otlp",
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
            "payloadCapture": False,
            "openTelemetry": {
                "metricsEndpoint": "https://otel.example.com/v1/metrics",
                "logsEndpoint": "https://otel.example.com/v1/logs",
                "tracesEndpoint": "https://otel.example.com/v1/traces",
                "credentials": {
                    "headers": {"x-api-key": "secret"},
                },
            },
        }
    }
    assert result["properties"]["kind"] == "openTelemetry"


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_custom_otlp_exporter_with_user_assigned_identity(
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

    _telemetry_exporter.create_telemetry_exporter(
        cmd,
        "gateway",
        "rg",
        "custom-otlp",
        metrics_endpoint="https://otel.example.com/v1/metrics",
        logs_endpoint="https://otel.example.com/v1/logs",
        traces_endpoint="https://otel.example.com/v1/traces",
        managed_identity_resource="https://otel.example.com",
        identity_client_id="client",
    )

    body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert "applicationInsights" not in body["properties"]
    assert body["properties"]["openTelemetry"]["credentials"][
        "managedIdentity"
    ] == {
        "resource": "https://otel.example.com",
        "clientId": "client",
    }


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_unauthenticated_traces_only_exporter(send_request, _, cmd):
    send_request.return_value = FakeResponse(
        {"properties": {"kind": "OpenTelemetry"}}
    )

    _telemetry_exporter.create_telemetry_exporter(
        cmd,
        "gateway",
        "rg",
        "custom-otlp",
        traces_endpoint="https://otel.example.com/v1/traces",
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "properties": {
            "kind": "OpenTelemetry",
            "payloadCapture": False,
            "openTelemetry": {
                "tracesEndpoint": "https://otel.example.com/v1/traces",
            },
        }
    }


@patch(
    "azext_ai_gateway._telemetry_exporter.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_custom_exporter_allows_authorization_header(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"properties": {"kind": "OpenTelemetry"}}
    )

    _telemetry_exporter.create_telemetry_exporter(
        cmd,
        "gateway",
        "rg",
        "custom-otlp",
        metrics_endpoint="https://otel.example.com/v1/metrics",
        headers={"Authorization": "Bearer secret"},
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body["properties"]["openTelemetry"]["credentials"] == {
        "headers": {"Authorization": "Bearer secret"},
    }


@pytest.mark.parametrize(
    "kwargs, message",
    [
        (
            {
                "metrics_endpoint": "http://otel.example.com/v1/metrics",
                "logs_endpoint": "https://otel.example.com/v1/logs",
                "traces_endpoint": "https://otel.example.com/v1/traces",
                "headers": {"x-api-key": "secret"},
            },
            "absolute HTTPS URL",
        ),
    ],
)
def test_custom_otlp_validation(cmd, kwargs, message):
    with pytest.raises(InvalidArgumentValueError, match=message):
        _telemetry_exporter.create_telemetry_exporter(
            cmd,
            "gateway",
            "rg",
            "custom-otlp",
            **kwargs,
        )


def test_deterministic_guid_matches_portal_algorithm():
    assert _telemetry_exporter._deterministic_guid(
        "principal",
        "/scope",
        "role",
    ) == (
        "d97b46bb-ea06-49d5-9b43-3f85336ca5e8"
    )
