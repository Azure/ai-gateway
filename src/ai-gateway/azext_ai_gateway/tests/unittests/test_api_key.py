# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from azext_ai_gateway import _api_key


class FakeResponse:

    def __init__(self, body=None):
        self._body = body
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


def test_format_api_key_list_table():
    keys = [
        {
            "name": "production",
            "properties": {
                "state": "active",
                "createdDate": "2026-08-19T20:00:00Z",
                "expirationDate": "2027-08-19T20:00:00Z",
            },
        },
        {"name": "development", "properties": {}},
    ]

    assert _api_key.format_api_key_list_table(keys) == [
        {
            "Name": "production",
            "State": "active",
            "Created": "2026-08-19T20:00:00Z",
            "Expiration date": "2027-08-19T20:00:00Z",
        },
        {
            "Name": "development",
            "State": "",
            "Created": "",
            "Expiration date": "",
        },
    ]


@patch("azext_ai_gateway._api_key.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_uses_resource_name_as_default_display_name(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"name": "production"})

    _api_key.create_api_key(cmd, "production", "gateway", "rg")

    assert json.loads(send_request.call_args.kwargs["body"]) == {
        "properties": {"displayName": "production"}
    }


@patch("azext_ai_gateway._api_key.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_secrets_returns_explicit_secret_response(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"primaryKey": "primary", "secondaryKey": "secondary"}
    )

    result = _api_key.list_api_key_secrets(
        cmd,
        "production",
        "gateway",
        "rg",
    )

    assert result == {"primaryKey": "primary", "secondaryKey": "secondary"}
    assert send_request.call_args.args[2].endswith(
        "/apiKeys/production/listSecrets"
    )


@patch("azext_ai_gateway._api_key.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_regenerate_maps_key_type_to_service_action(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse()

    _api_key.regenerate_api_key(
        cmd,
        "production",
        "gateway",
        "rg",
        "secondary",
    )

    assert send_request.call_args.args[2].endswith(
        "/apiKeys/production/regenerateSecondaryKey"
    )
