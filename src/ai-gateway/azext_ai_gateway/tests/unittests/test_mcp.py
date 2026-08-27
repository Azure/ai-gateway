# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.cli.core.azclierror import AzCLIError, RequiredArgumentMissingError

from azext_ai_gateway import _mcp
from azext_ai_gateway._validators import validate_endpoints


class FakeResponse:

    def __init__(self, body=None, headers=None, status_code=200, text=None):
        self._body = body
        self.headers = headers or {}
        self.status_code = status_code
        self.ok = 200 <= status_code < 400
        self.content = b"" if body is None else json.dumps(body).encode()
        self.text = text if text is not None else self.content.decode()

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


@patch(
    "azext_ai_gateway._mcp.show_gateway",
    return_value={
        "properties": {"gatewayUrl": "https://contoso-aigw.azure-api.net/"}
    },
)
@patch("azext_ai_gateway._mcp._list_all")
@patch("azext_ai_gateway._mcp.get_subscription_id", return_value="sub")
def test_list_mcp_adds_derived_runtime_endpoint(
    _,
    list_all,
    show_gateway,
    cmd,
):
    list_all.return_value = [
        {"name": "federated-mcp", "properties": {"description": "Tools"}}
    ]

    result = _mcp.list_mcp(cmd, "contoso-aigw", "rg")

    assert result[0]["properties"]["mcpEndpointUrl"] == (
        "https://contoso-aigw.azure-api.net/default/toolservers/"
        "federated-mcp/mcp"
    )
    show_gateway.assert_called_once_with(cmd, "contoso-aigw", "rg")


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
    assert "If-None-Match=*" in send_request.call_args.kwargs["headers"]


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


@pytest.mark.parametrize(
    ("failure_mode", "endpoints", "implication"),
    [
        (
            "failOpen",
            [],
            "successful test can return a partial tool list",
        ),
        (
            "failClosed",
            [],
            "required endpoint failure stops federation",
        ),
        (
            None,
            [],
            None,
        ),
        (
            None,
            [{"namespace": "optional", "required": False}],
            "tools/list result may be incomplete",
        ),
    ],
)
def test_failure_mode_announcement_explains_implication(
    failure_mode,
    endpoints,
    implication,
    caplog,
):
    _mcp._announce_failure_mode(failure_mode, endpoints)

    if failure_mode:
        assert f"Failure mode: {failure_mode}." in caplog.text
    else:
        assert "Failure mode:" not in caplog.text
    if implication:
        assert implication in caplog.text
    if any(endpoint.get("required") is False for endpoint in endpoints):
        assert any(
            record.levelname == "WARNING"
            and record.message.startswith("Warning:")
            and "tools/list result may be incomplete" in record.message
            for record in caplog.records
        )


@patch(
    "azext_ai_gateway._mcp.should_disable_connection_verify",
    return_value=False,
)
@patch("azext_ai_gateway._mcp.requests.post")
@patch("azext_ai_gateway._mcp.list_api_key_secrets")
@patch("azext_ai_gateway._mcp.show_gateway")
@patch("azext_ai_gateway._mcp.show_mcp")
def test_test_mcp_initializes_registered_runtime_endpoint(
    show_mcp,
    show_gateway,
    list_secrets,
    post,
    _,
    cmd,
    caplog,
):
    show_gateway.return_value = {
        "properties": {"gatewayUrl": "https://gateway.test/"}
    }
    show_mcp.return_value = {
        "properties": {
            "failureMode": "failOpen",
            "endpoints": [{"id": "endpoint-1"}],
        }
    }
    list_secrets.return_value = {
        "primaryKey": "secret",
        "secondaryKey": "secondary",
    }
    post.side_effect = [
        FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "tools", "version": "1.0"},
                },
            },
            {"Mcp-Session-Id": "session-1"},
        ),
        FakeResponse(status_code=202),
        FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search shared tools",
                        }
                    ]
                },
            }
        ),
    ]

    result = _mcp.test_mcp(
        cmd,
        "tools",
        "gateway",
        "rg",
        "production",
    )

    assert result["serverInfo"]["name"] == "tools"
    assert result["tools"] == [
        {"name": "search", "description": "Search shared tools"}
    ]
    assert result["diagnostic"]["failureMode"] == "failOpen"
    assert result["diagnostic"]["configuredEndpointCount"] == 1
    assert (
        "Testing MCP endpoint: "
        "https://gateway.test/default/toolservers/tools/mcp"
    ) in caplog.text
    assert "Failure mode: failOpen." in caplog.text
    assert "successful test can return a partial tool list" in caplog.text
    show_gateway.assert_called_once_with(cmd, "gateway", "rg")
    list_secrets.assert_called_once_with(
        cmd,
        "production",
        "gateway",
        "rg",
    )
    initialize_call, initialized_call, tools_call = post.call_args_list
    assert initialize_call.args == (
        "https://gateway.test/default/toolservers/tools/mcp",
    )
    assert initialize_call.kwargs["headers"]["Api-Key"] == "secret"
    assert initialize_call.kwargs["headers"]["Accept"] == (
        "application/json, text/event-stream"
    )
    assert initialize_call.kwargs["json"]["method"] == "initialize"
    assert initialize_call.kwargs["json"]["params"]["protocolVersion"] == (
        "2024-11-05"
    )
    assert initialize_call.kwargs["timeout"] == 15
    assert initialize_call.kwargs["verify"] is True
    assert initialized_call.kwargs["json"]["method"] == (
        "notifications/initialized"
    )
    assert initialized_call.kwargs["headers"]["Mcp-Session-Id"] == "session-1"
    assert tools_call.kwargs["json"]["method"] == "tools/list"
    assert tools_call.kwargs["headers"]["Mcp-Session-Id"] == "session-1"


@patch("azext_ai_gateway._mcp.requests.post")
@patch(
    "azext_ai_gateway._mcp.list_api_key_secrets",
    return_value={"primaryKey": "secret"},
)
@patch(
    "azext_ai_gateway._mcp.show_gateway",
    return_value={"properties": {"gatewayUrl": "https://gateway.test"}},
)
@patch(
    "azext_ai_gateway._mcp.show_mcp",
    return_value={"properties": {"failureMode": "failClosed"}},
)
def test_test_mcp_accepts_sse_initialize_response(
    _show_mcp,
    _show_gateway,
    _list_secrets,
    post,
    cmd,
):
    post.side_effect = [
        FakeResponse(
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            text=(
                "event: message\n"
                'data: {"jsonrpc":"2.0","id":1,"result":'
                '{"protocolVersion":"2024-11-05","capabilities":{}}}\n\n'
            ),
        ),
        FakeResponse(status_code=202),
        FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": []},
            }
        ),
    ]

    result = _mcp.test_mcp(
        cmd,
        "tools",
        "gateway",
        "rg",
        "production",
    )

    assert result["protocolVersion"] == "2024-11-05"
    assert result["tools"] == []


@patch("azext_ai_gateway._mcp.requests.post")
@patch(
    "azext_ai_gateway._mcp.list_api_key_secrets",
    return_value={"primaryKey": "secret"},
)
@patch(
    "azext_ai_gateway._mcp.show_gateway",
    return_value={"properties": {"gatewayUrl": "https://gateway.test"}},
)
@patch(
    "azext_ai_gateway._mcp.show_mcp",
    return_value={"properties": {"failureMode": "failClosed"}},
)
def test_test_mcp_surfaces_protocol_error(
    _show_mcp,
    _show_gateway,
    _list_secrets,
    post,
    cmd,
):
    post.return_value = FakeResponse(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
    )

    with pytest.raises(AzCLIError) as error:
        _mcp.test_mcp(
            cmd,
            "tools",
            "gateway",
            "rg",
            "production",
        )

    message = str(error.value)
    assert "Stage       Status" in message
    assert "initialize  Failed" in message
    assert "Error details:" not in message
    assert "Cause:" not in message
    assert "Method not found" in message
    assert "Response:" in message
    assert "Status: 200" in message
    assert '"code": -32601' in message
    assert "notifications/initialized" not in message


@patch("azext_ai_gateway._mcp.requests.post")
@patch(
    "azext_ai_gateway._mcp.list_api_key_secrets",
    return_value={"primaryKey": "secret"},
)
@patch(
    "azext_ai_gateway._mcp.show_gateway",
    return_value={"properties": {"gatewayUrl": "https://gateway.test"}},
)
@patch(
    "azext_ai_gateway._mcp.show_mcp",
    return_value={"properties": {"failureMode": "failClosed"}},
)
def test_test_mcp_diagnostic_identifies_tools_list_failure(
    _show_mcp,
    _show_gateway,
    _list_secrets,
    post,
    cmd,
):
    post.side_effect = [
        FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                },
            }
        ),
        FakeResponse(status_code=202),
        FakeResponse(
            {
                "statusCode": 404,
                "message": (
                    "Federation tools/list failed: required endpoint "
                    "'func-mcp-demo-a18f26' returned error: Endpoint "
                    "'func-mcp-demo-a18f26' init returned HTTP 403."
                ),
            },
            status_code=404,
        ),
    ]

    with pytest.raises(AzCLIError) as error:
        _mcp.test_mcp(
            cmd,
            "tools",
            "gateway",
            "rg",
            "production",
        )

    message = str(error.value)
    assert "Endpoint: https://gateway.test/default/toolservers/tools/mcp" in (
        message
    )
    stage_rows = [
        line.split()
        for line in message.splitlines()
        if line.startswith(
            ("initialize ", "notifications/initialized ", "tools/list ")
        )
    ]
    assert "Error details:" not in message
    assert "Cause:" not in message
    assert "Federation diagnosis:" in message
    assert "Endpoint: func-mcp-demo-a18f26" in message
    assert "Requirement: Required" in message
    assert "Downstream operation: initialize" in message
    assert "Downstream status: HTTP 403" in message
    assert [(row[0], " ".join(row[1:])) for row in stage_rows] == [
        ("initialize", "Succeeded"),
        ("notifications/initialized", "Succeeded"),
        ("tools/list", "Federation failed"),
    ]
    assert "Status: 404" in message
    assert "Headers: {}" in message
    assert "Body:" in message


@patch("azext_ai_gateway._mcp.requests.post")
@patch(
    "azext_ai_gateway._mcp.list_api_key_secrets",
    return_value={"secondaryKey": "secondary"},
)
@patch(
    "azext_ai_gateway._mcp.show_gateway",
    return_value={"properties": {"gatewayUrl": "https://gateway.test"}},
)
@patch(
    "azext_ai_gateway._mcp.show_mcp",
    return_value={"properties": {"failureMode": "failClosed"}},
)
def test_test_mcp_requires_primary_key_value(
    _show_mcp,
    _show_gateway,
    _list_secrets,
    post,
    cmd,
):

    with pytest.raises(AzCLIError, match="has no primary key value"):
        _mcp.test_mcp(
            cmd,
            "tools",
            "gateway",
            "rg",
            "production",
        )

    post.assert_not_called()
