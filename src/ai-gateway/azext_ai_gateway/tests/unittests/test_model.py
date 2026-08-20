# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_ai_gateway import _model
from azext_ai_gateway._validators import validate_policies, validate_policy


class FakeResponse:

    def __init__(self, body=None, headers=None):
        self._body = body
        self.headers = headers or {}
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


@patch("azext_ai_gateway._model.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_models_uses_cross_provider_path_and_follows_pages(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "value": [{"name": "one"}],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        FakeResponse({"value": [{"name": "two"}]}),
    ]

    result = _model.list_models(cmd, "gateway", "rg")

    assert [model["name"] for model in result] == ["one", "two"]
    first_url = send_request.call_args_list[0].args[2]
    assert first_url.endswith("/workspaces/default/models")
    assert send_request.call_args_list[1] == call(
        cmd.cli_ctx,
        "GET",
        "https://management.azure.com/next",
        uri_parameters=None,
        body=None,
    )


@patch("azext_ai_gateway._model.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_models_filters_by_provider_and_type(send_request, _, cmd):
    send_request.return_value = FakeResponse(
        {
            "value": [
                {
                    "name": "foundry-model",
                    "properties": {"providerKind": "Foundry"},
                },
                {
                    "name": "custom-model",
                    "properties": {"providerKind": "Custom"},
                },
            ]
        }
    )

    result = _model.list_models(
        cmd,
        "gateway",
        "rg",
        provider_name="provider",
        model_type="foundry",
    )

    assert [model["name"] for model in result] == ["foundry-model"]
    assert send_request.call_args.args[2].endswith(
        "/workspaces/default/modelProviders/provider/models"
    )


def test_format_model_list_table():
    models = [
        {
            "id": (
                "/workspaces/default/modelProviders/foundry-main/"
                "models/gpt-4o"
            ),
            "name": "gpt-4o",
            "properties": {
                "providerKind": "Foundry",
                "supportedEndpoints": [
                    "/openai/v1/chat/completions",
                    "/openai/v1/responses",
                ],
            },
        },
        {
            "id": (
                "/workspaces/default/modelproviders/custom/"
                "models/llama"
            ),
            "name": "llama",
            "properties": {"providerKind": "Custom"},
        },
    ]

    assert _model.format_model_list_table(models) == [
        {
            "Name": "gpt-4o",
            "Type": "Foundry",
            "Provider name": "foundry-main",
            "Endpoints": (
                "/openai/v1/chat/completions, /openai/v1/responses"
            ),
        },
        {
            "Name": "llama",
            "Type": "Custom",
            "Provider name": "custom",
            "Endpoints": "",
        },
    ]


@patch("azext_ai_gateway._model.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_model_builds_foundry_deployment_payload(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"name": "gpt-4o"})

    result = _model.create_model(
        cmd,
        "gpt-4o",
        "gateway",
        "rg",
        "foundry",
        display_name="GPT-4o",
        deployment_resource_id="/foundry/deployments/gpt-4o",
        deployment_model_name="gpt-4o",
        deployment_model_version="2024-11-20",
        supported_endpoints=["/v1/chat/completions"],
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "properties": {
            "displayName": "GPT-4o",
            "deployment": {
                "resourceId": "/foundry/deployments/gpt-4o",
                "modelName": "gpt-4o",
                "modelVersion": "2024-11-20",
            },
            "supportedEndpoints": ["/v1/chat/completions"],
        }
    }
    assert result["name"] == "gpt-4o"


def test_create_requires_model_name_for_deployment(cmd):
    with pytest.raises(RequiredArgumentMissingError):
        _model.create_model(
            cmd,
            "model",
            "gateway",
            "rg",
            "provider",
            deployment_resource_id="/deployment",
        )


def test_policy_validator_accepts_inline_array_and_rejects_missing_type():
    assert validate_policies(
        '[{"type":"tokenLimit","count":100,'
        '"period":"minute","counterKey":"IPAddress"}]'
    ) == [
        {
            "type": "tokenLimit",
            "count": 100,
            "period": "minute",
            "counterKey": "IPAddress",
        }
    ]
    with pytest.raises(Exception, match="each contain a non-empty string 'type'"):
        validate_policies('[{"count":100}]')
    with pytest.raises(Exception, match="non-empty string 'type'"):
        validate_policy('{"type": {}}')


@pytest.mark.parametrize(
    "policy",
    [
        {
            "type": "tokenLimit",
            "count": 100,
            "period": "minute",
            "counterKey": "IPAddress",
        },
        {
            "type": "costLimit",
            "amount": 200,
            "period": "month",
            "counterKey": "Identity",
            "displayName": "Monthly budget",
            "remainingCostHeaderName": "x-cost-remaining",
        },
        {
            "type": "requestRateLimit",
            "callsPerPeriod": 100,
            "periodSeconds": 60,
            "counterKey": "IPAddress",
        },
        {
            "type": "contentSafety",
            "hateSeverity": "Low",
            "violenceSeverity": "Medium",
            "sexualSeverity": "High",
            "selfHarmSeverity": "None",
        },
        {
            "type": "ipFilter",
            "action": "Allow",
            "cidrRanges": ["10.0.0.0/8"],
        },
        {"type": "futurePolicy", "customField": True},
    ],
)
def test_policy_validator_accepts_known_schemas_and_unknown_types(policy):
    serialized = json.dumps(policy)
    assert validate_policy(serialized) == policy
    assert validate_policies(f"[{serialized}]") == [policy]


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (
            {
                "type": "tokenLimit",
                "count": 0,
                "period": "minute",
                "counterKey": "IPAddress",
            },
            "Failed to validate tokenLimit policy at 'count': "
            "must be a positive integer",
        ),
        (
            {
                "type": "costLimit",
                "amount": 0,
                "period": "month",
                "counterKey": "Identity",
            },
            "Failed to validate costLimit policy at 'amount': must be a number",
        ),
        (
            {
                "type": "requestRateLimit",
                "callsPerPeriod": 100,
                "periodSeconds": "60",
                "counterKey": "IPAddress",
            },
            "Failed to validate requestRateLimit policy at 'periodSeconds': "
            "must be a positive integer",
        ),
        (
            {
                "type": "contentSafety",
                "hateSeverity": "Critical",
                "violenceSeverity": "Low",
                "sexualSeverity": "Low",
                "selfHarmSeverity": "Low",
            },
            "Failed to validate contentSafety policy at 'hateSeverity': "
            "must be one of",
        ),
        (
            {
                "type": "ipFilter",
                "action": "Allow",
                "cidrRanges": ["10.0.0.1"],
            },
            "Failed to validate ipFilter policy at 'cidrRanges': "
            "must contain valid IPv4 CIDR ranges",
        ),
    ],
)
def test_policy_validator_rejects_invalid_known_schemas(policy, message):
    with pytest.raises(Exception, match=message):
        validate_policy(json.dumps(policy))


def test_policy_validator_identifies_attempted_policy_and_missing_field():
    policy = {
        "type": "requestRateLimit",
        "callsPerPeriod": 200,
        "period": "day",
        "counterKey": "Identity",
    }

    with pytest.raises(InvalidArgumentValueError) as error:
        validate_policy(json.dumps(policy))

    assert str(error.value) == (
        "Failed to validate requestRateLimit policy at 'periodSeconds': "
        "must be a positive integer."
    )
