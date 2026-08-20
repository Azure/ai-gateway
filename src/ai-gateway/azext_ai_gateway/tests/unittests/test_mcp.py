# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_ai_gateway import _mcp
from azext_ai_gateway._validators import validate_endpoints


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


def test_format_mcp_list_table():
    servers = [
        {
            "name": "tools",
            "properties": {
                "description": "Shared engineering tools",
                "mcpEndpointUrl": "https://gateway.example.com/mcp/tools",
            },
        },
        {"name": "empty", "properties": {}},
    ]

    assert _mcp.format_mcp_list_table(servers) == [
        {
            "Name": "tools",
            "Description": "Shared engineering tools",
            "Endpoint": "https://gateway.example.com/mcp/tools",
        },
        {
            "Name": "empty",
            "Description": "",
            "Endpoint": "",
        },
    ]


@patch("azext_ai_gateway._mcp.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_mcp_strips_server_managed_oauth_fields(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"name": "tools"})
    endpoints = [
        {
            "namespace": "tickets",
            "kind": "mcp",
            "mcp": {"url": "https://example.test/mcp"},
            "credentials": {
                "type": "oauth2",
                "oauth2": {
                    "grantType": "authorizationCode",
                    "authorizationUrl": "https://login.test/authorize",
                    "tokenUrl": "https://login.test/token",
                    "clientId": "client",
                    "clientSecret": "secret",
                    "status": "connected",
                    "tokenKind": "refreshToken",
                },
            },
        }
    ]

    _mcp.create_mcp(cmd, "tools", "gateway", "rg", endpoints)

    body = json.loads(send_request.call_args.kwargs["body"])
    oauth = body["properties"]["endpoints"][0]["credentials"]["oauth2"]
    assert oauth["clientSecret"] == "secret"
    assert "status" not in oauth
    assert "tokenKind" not in oauth
    assert body["properties"]["type"] == "mcp"


@patch("azext_ai_gateway._mcp.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_preserves_secrets_and_uses_matching_etag(
    send_request,
    _,
    cmd,
):
    get_endpoint = {
        "id": "endpoint-1",
        "namespace": "tickets",
        "kind": "mcp",
        "mcp": {"url": "https://old.test/mcp"},
        "credentials": {"type": "oauth2", "oauth2": {"clientId": "client"}},
    }
    secret_endpoint = {
        "id": "endpoint-1",
        "credentials": {
            "type": "oauth2",
            "oauth2": {"clientId": "client", "clientSecret": "secret"},
        },
    }
    send_request.side_effect = [
        FakeResponse(
            {"properties": {"endpoints": [get_endpoint]}},
            {"ETag": "etag"},
        ),
        FakeResponse({"endpoints": [secret_endpoint]}, {"ETag": "etag"}),
        FakeResponse({"name": "tools"}),
    ]
    replacement = [
        {
            "id": "endpoint-1",
            "namespace": "tickets",
            "kind": "mcp",
            "mcp": {"url": "https://new.test/mcp"},
            "credentials": {
                "type": "oauth2",
                "oauth2": {"clientId": "client"},
            },
        }
    ]

    _mcp.update_mcp(
        cmd,
        "tools",
        "gateway",
        "rg",
        endpoints=replacement,
    )

    patch_call = send_request.call_args_list[2]
    assert patch_call.args[1] == "PUT"
    body = json.loads(patch_call.kwargs["body"])
    oauth = body["properties"]["endpoints"][0]["credentials"]["oauth2"]
    assert oauth["clientSecret"] == "secret"
    assert "If-Match=etag" in patch_call.kwargs["headers"]


@patch("azext_ai_gateway._mcp.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_authorize_uses_server_generated_endpoint_id(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {
            "loginLink": "https://login.test",
            "redirectUri": "https://management.azure.com/callback",
        }
    )

    result = _mcp.authorize_mcp(
        cmd,
        "tools",
        "endpoint/one",
        "gateway",
        "rg",
    )

    assert "/endpoints/endpoint%2Fone/oauth2/getLoginLinks" in (
        send_request.call_args.args[2]
    )
    assert result["loginLink"] == "https://login.test"


def test_update_requires_a_property(cmd):
    with pytest.raises(RequiredArgumentMissingError):
        _mcp.update_mcp(cmd, "tools", "gateway", "rg")


def test_endpoint_validator_requires_namespace_and_kind():
    assert validate_endpoints(
        '[{"namespace":"tools","kind":"mcp","mcp":{"url":"https://test"}}]'
    )[0]["namespace"] == "tools"
    with pytest.raises(Exception, match="namespace"):
        validate_endpoints('[{"kind":"mcp"}]')
