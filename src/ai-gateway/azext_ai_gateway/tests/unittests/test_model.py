# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_ai_gateway import _model
from azext_ai_gateway._validators import validate_policies


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


@patch("azext_ai_gateway._model.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_uses_etag_and_preserves_existing_deployment_fields(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "etag": "body-etag",
                "properties": {
                    "deployment": {
                        "resourceId": "/deployment",
                        "modelName": "gpt-4o",
                        "modelVersion": "old",
                    }
                },
            },
            headers={"ETag": "header-etag"},
        ),
        FakeResponse({"name": "gpt-4o"}),
    ]

    _model.update_model(
        cmd,
        "gpt-4o",
        "gateway",
        "rg",
        "foundry",
        deployment_model_version="new",
    )

    patch_call = send_request.call_args_list[1]
    assert "If-Match=header-etag" in patch_call.kwargs["headers"]
    assert json.loads(patch_call.kwargs["body"]) == {
        "properties": {
            "deployment": {
                "resourceId": "/deployment",
                "modelName": "gpt-4o",
                "modelVersion": "new",
            }
        }
    }


def test_update_requires_a_property(cmd):
    with pytest.raises(RequiredArgumentMissingError):
        _model.update_model(
            cmd,
            "model",
            "gateway",
            "rg",
            "provider",
        )


def test_policy_validator_accepts_inline_array_and_rejects_missing_type():
    assert validate_policies('[{"type":"tokenLimit","count":100}]') == [
        {"type": "tokenLimit", "count": 100}
    ]
    with pytest.raises(Exception, match="each contain 'type'"):
        validate_policies('[{"count":100}]')

