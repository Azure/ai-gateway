# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from azext_ai_gateway import _policy


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


def test_policy_id_round_trips_and_survives_array_reordering():
    first = {"type": "tokenLimit", "count": 100}
    target = {"type": "contentSafety", "hateSeverity": 2}
    policy_id = _policy._policy_id("/host", 1, target)
    locator = _policy._parse_policy_id(policy_id)

    assert _policy._locate([target, first], locator) == 0


@patch("azext_ai_gateway._policy.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_model_policy_appends_and_uses_etag(
    send_request,
    _,
    cmd,
):
    existing = {"type": "tokenLimit", "count": 100}
    created = {"type": "contentSafety", "hateSeverity": 2}
    send_request.side_effect = [
        FakeResponse(
            {"properties": {"policies": [existing]}},
            {"ETag": "etag"},
        ),
        FakeResponse({"properties": {"policies": [existing, created]}}),
    ]

    result = _policy.create_policy(
        cmd,
        "gateway",
        "rg",
        "model",
        "gpt-4o",
        created,
        provider_name="foundry",
    )

    patch_call = send_request.call_args_list[1]
    assert patch_call.args[1] == "PATCH"
    assert "If-Match=etag" in patch_call.kwargs["headers"]
    assert json.loads(patch_call.kwargs["body"]) == {
        "properties": {"policies": [existing, created]}
    }
    assert result["scopeType"] == "model"


@patch("azext_ai_gateway._policy.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._policy._get_with_secrets")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_mcp_policy_uses_secret_preserving_put(
    send_request,
    get_with_secrets,
    _,
    cmd,
):
    get_with_secrets.return_value = (
        {
            "type": "mcp",
            "endpoints": [
                {
                    "namespace": "tools",
                    "kind": "mcp",
                    "mcp": {"url": "https://tools.test/mcp"},
                    "credentials": {
                        "type": "header",
                        "headers": {"api-key": ["secret"]},
                    },
                }
            ],
        },
        "etag",
    )
    send_request.return_value = FakeResponse(
        {"properties": {"policies": [{"type": "tokenLimit"}]}}
    )

    result = _policy.create_policy(
        cmd,
        "gateway",
        "rg",
        "mcp",
        "tools",
        {"type": "tokenLimit"},
    )

    put_call = send_request.call_args
    assert put_call.args[1] == "PUT"
    body = json.loads(put_call.kwargs["body"])
    assert body["properties"]["endpoints"][0]["credentials"]["headers"] == {
        "api-key": ["secret"]
    }
    assert "endpoints" not in result
