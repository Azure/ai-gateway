# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import AzCLIError

from azext_ai_gateway import _model_alias


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


def test_format_model_alias_list_table_uses_callable_name_fallback():
    aliases = [
        {
            "name": "production-chat",
            "properties": {
                "aliasName": "production/chat",
                "description": "Production",
                "backendModels": [
                    {
                        "resourceId": (
                            "/modelProviders/foundry/models/gpt-4o"
                        )
                    }
                ],
            },
        },
        {
            "name": "fallback",
            "properties": {
                "backendModels": [
                    {
                        "resourceId": (
                            "/modelProviders/custom%20provider/models/"
                            "gpt%205"
                        )
                    }
                ]
            },
        },
    ]

    assert _model_alias.format_model_alias_list_table(aliases) == [
        {
            "Name (alias)": "production/chat",
            "Backend model": "gpt-4o",
            "Provider": "foundry",
        },
        {
            "Name (alias)": "fallback",
            "Backend model": "gpt 5",
            "Provider": "custom provider",
        },
    ]


@patch("azext_ai_gateway._model_alias.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_model_aliases_follows_pages(send_request, _, cmd):
    send_request.side_effect = [
        FakeResponse(
            {
                "value": [{"name": "one"}],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        FakeResponse({"value": [{"name": "two"}]}),
    ]

    result = _model_alias.list_model_aliases(cmd, "gateway", "rg")

    assert [alias["name"] for alias in result] == ["one", "two"]
    assert send_request.call_args_list[0].args[2].endswith(
        "/workspaces/default/aliases"
    )
    assert send_request.call_args_list[0].kwargs["uri_parameters"] == [
        "api-version=2026-09-01-preview"
    ]
    assert send_request.call_args_list[1] == call(
        cmd.cli_ctx,
        "GET",
        "https://management.azure.com/next",
        uri_parameters=None,
        body=None,
    )


@patch("azext_ai_gateway._model_alias.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_model_alias_builds_target_payload(send_request, _, cmd):
    send_request.return_value = FakeResponse({"name": "production-chat"})

    _model_alias.create_model_alias(
        cmd,
        "production-chat",
        "production/chat",
        "foundry",
        "gpt-4o",
        "gateway",
        "rg",
        description="Production",
    )

    assert send_request.call_args.args[1] == "PUT"
    assert send_request.call_args.args[2].endswith(
        "/workspaces/default/aliases/production-chat"
    )
    assert json.loads(send_request.call_args.kwargs["body"]) == {
        "type": "Microsoft.ApiManagement/aigateways/workspaces/aliases",
        "properties": {
            "aliasName": "production/chat",
            "description": "Production",
            "backendModels": [
                {
                    "resourceId": (
                        "/subscriptions/sub/resourceGroups/rg/providers/"
                        "Microsoft.ApiManagement/aigateways/gateway/workspaces/"
                        "default/modelProviders/foundry/models/gpt-4o"
                    )
                }
            ],
        }
    }


@patch("azext_ai_gateway._model_alias.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_model_alias_commands_accept_api_version_override(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"value": []})

    _model_alias.list_model_aliases(
        cmd,
        "gateway",
        "rg",
        api_version="2027-01-01-preview",
    )

    assert send_request.call_args.kwargs["uri_parameters"] == [
        "api-version=2027-01-01-preview"
    ]


@patch("azext_ai_gateway._model_alias.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_model_alias_gets_etag_and_patches_supplied_fields(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {"name": "production-chat", "properties": {}},
            {"ETag": 'W/"1"'},
        ),
        FakeResponse(
            {
                "name": "production-chat",
                "properties": {"aliasName": "production/chat-v2"},
            }
        ),
    ]

    _model_alias.update_model_alias(
        cmd,
        "production-chat",
        "gateway",
        "rg",
        alias_name="production/chat-v2",
    )

    patch_call = send_request.call_args_list[1]
    assert patch_call.args[1] == "PATCH"
    assert "If-Match=W/\"1\"" in patch_call.kwargs["headers"]
    assert json.loads(patch_call.kwargs["body"]) == {
        "type": "Microsoft.ApiManagement/aigateways/workspaces/aliases",
        "properties": {"aliasName": "production/chat-v2"}
    }


@patch("azext_ai_gateway._model_alias.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_delete_model_alias_uses_supplied_etag(send_request, _, cmd):
    send_request.return_value = FakeResponse()

    _model_alias.delete_model_alias(
        cmd,
        "production-chat",
        "gateway",
        "rg",
        if_match='W/"2"',
    )

    assert send_request.call_args.args[1] == "DELETE"
    assert "If-Match=W/\"2\"" in send_request.call_args.kwargs["headers"]


@pytest.mark.parametrize(
    "alias_name",
    ["", "/chat", "chat/", "chat name", "a" * 257],
)
def test_create_model_alias_rejects_invalid_callable_name(alias_name, cmd):
    with pytest.raises(Exception, match="Alias names must be"):
        _model_alias.create_model_alias(
            cmd,
            "production-chat",
            alias_name,
            "foundry",
            "gpt-4o",
            "gateway",
            "rg",
        )


@pytest.mark.parametrize(
    ("supported_endpoint", "protocol", "expected_payload"),
    [
        (
            "/openai/v1/chat/completions",
            "chat-completions",
            {
                "model": "production/chat",
                "messages": [{"role": "user", "content": "ping"}],
            },
        ),
        (
            "/openai/v1/responses",
            "responses",
            {
                "model": "production/chat",
                "input": "ping",
            },
        ),
        (
            "/anthropic/v1/messages",
            "anthropic-messages",
            {
                "model": "production/chat",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "ping"}],
            },
        ),
    ],
)
@patch(
    "azext_ai_gateway._model_alias.should_disable_connection_verify",
    return_value=False,
)
@patch("azext_ai_gateway._model_alias.Profile")
@patch("azext_ai_gateway._model_alias.requests.post")
@patch("azext_ai_gateway._model_alias.list_api_key_secrets")
@patch("azext_ai_gateway._model_alias.show_gateway")
@patch("azext_ai_gateway._model_alias.show_model")
@patch("azext_ai_gateway._model_alias.show_model_alias")
def test_test_model_alias_uses_backend_protocol(
    show_alias,
    show_model,
    show_gateway,
    list_secrets,
    post,
    profile,
    _,
    supported_endpoint,
    protocol,
    expected_payload,
    cmd,
    caplog,
):
    show_alias.return_value = {
        "name": "production-chat",
        "properties": {
            "aliasName": "production/chat",
            "backendModels": [
                {
                    "resourceId": (
                        "/subscriptions/sub/resourceGroups/rg/providers/"
                        "Microsoft.ApiManagement/aigateways/gateway/"
                        "workspaces/default/modelProviders/foundry/models/"
                        "gpt-4o"
                    )
                }
            ],
        },
    }
    show_model.return_value = {
        "properties": {"supportedEndpoints": [supported_endpoint]}
    }
    show_gateway.return_value = {
        "properties": {
            "frontend": {"defaultHostname": "gateway.test"}
        }
    }
    list_secrets.return_value = {"primaryKey": "secret"}
    post.return_value = FakeResponse({"id": "response-1"})

    with patch(
        "azext_ai_gateway._model_alias.long_running_progress"
    ) as progress:
        result = _model_alias.test_model_alias(
            cmd,
            "production-chat",
            "gateway",
            "rg",
            "production",
            prompt="ping",
        )

    assert result == {
        "status": "Succeeded",
        "aliasName": "production/chat",
        "protocol": protocol,
        "authentication": {
            "method": "ApiKey",
            "apiKeyName": "production",
        },
        "endpoint": (
            f"https://gateway.test/default/models{supported_endpoint}"
        ),
        "response": {"id": "response-1"},
    }
    show_model.assert_called_once_with(
        cmd,
        "gpt-4o",
        "gateway",
        "rg",
        "foundry",
        "default",
        "2026-09-01-preview",
    )
    show_gateway.assert_called_once_with(
        cmd,
        "gateway",
        "rg",
        api_version="2026-09-01-preview",
    )
    assert post.call_args.args == (
        f"https://gateway.test/default/models{supported_endpoint}",
    )
    assert post.call_args.kwargs["headers"]["Api-Key"] == "secret"
    profile.assert_not_called()
    assert post.call_args.kwargs["json"] == expected_payload
    assert post.call_args.kwargs["timeout"] == 30
    assert post.call_args.kwargs["verify"] is True
    progress.assert_called_once_with(
        cmd,
        f"Testing model alias 'production/chat' using {protocol}",
    )
    assert (
        f"Status: Succeeded. Model alias 'production/chat' responded using "
        f"{protocol}."
    ) in caplog.text
    if protocol == "anthropic-messages":
        assert post.call_args.kwargs["headers"]["anthropic-version"] == (
            "2023-06-01"
        )
    else:
        assert "anthropic-version" not in post.call_args.kwargs["headers"]


@patch(
    "azext_ai_gateway._model_alias.should_disable_connection_verify",
    return_value=False,
)
@patch("azext_ai_gateway._model_alias.Profile")
@patch("azext_ai_gateway._model_alias.requests.post")
@patch("azext_ai_gateway._model_alias.show_gateway")
@patch("azext_ai_gateway._model_alias.show_model")
@patch("azext_ai_gateway._model_alias.show_model_alias")
def test_test_model_alias_uses_entra_by_default(
    show_alias,
    show_model,
    show_gateway,
    post,
    profile,
    _,
    cmd,
    caplog,
):
    show_alias.return_value = {
        "properties": {
            "aliasName": "production/chat",
            "backendModels": [
                {
                    "resourceId": (
                        "/modelProviders/foundry/models/gpt-4o"
                    )
                }
            ],
        }
    }
    show_model.return_value = {
        "properties": {
            "supportedEndpoints": ["/openai/v1/chat/completions"]
        }
    }
    show_gateway.return_value = {
        "properties": {"gatewayUrl": "https://gateway.test"}
    }
    profile.return_value.get_raw_token.return_value = (
        ("Bearer", "entra-token", {}),
        "sub",
        "tenant",
    )
    post.return_value = FakeResponse({"id": "response-1"})

    result = _model_alias.test_model_alias(
        cmd,
        "production-chat",
        "gateway",
        "rg",
    )

    profile.assert_called_once_with(cmd.cli_ctx)
    profile.return_value.get_raw_token.assert_called_once_with(
        resource="https://ai.gateway.azure.com"
    )
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer entra-token"
    assert "Api-Key" not in headers
    assert (
        "Acquiring a Microsoft Entra access token for "
        "https://ai.gateway.azure.com"
    ) in caplog.text
    assert (
        "Acquired a Microsoft Entra access token using the signed-in "
        "Azure identity."
    ) in caplog.text
    assert result["authentication"] == {
        "method": "MicrosoftEntra",
        "resource": "https://ai.gateway.azure.com",
    }


@patch("azext_ai_gateway._model_alias.show_model")
@patch("azext_ai_gateway._model_alias.show_model_alias")
def test_test_model_alias_rejects_non_generative_endpoint(
    show_alias,
    show_model,
    cmd,
):
    show_alias.return_value = {
        "properties": {
            "aliasName": "embeddings",
            "backendModels": [
                {
                    "resourceId": (
                        "/modelProviders/foundry/models/text-embedding-3"
                    )
                }
            ],
        }
    }
    show_model.return_value = {
        "properties": {
            "supportedEndpoints": ["/openai/v1/embeddings"]
        }
    }

    with pytest.raises(Exception, match="without a supported generative"):
        _model_alias.test_model_alias(
            cmd,
            "embeddings",
            "gateway",
            "rg",
            "production",
        )


@patch("azext_ai_gateway._model_alias.show_model")
@patch("azext_ai_gateway._model_alias.show_model_alias")
def test_test_model_alias_requires_endpoint_for_multi_endpoint_model(
    show_alias,
    show_model,
    cmd,
):
    show_alias.return_value = {
        "properties": {
            "aliasName": "production/chat",
            "backendModels": [
                {"resourceId": "/modelProviders/foundry/models/gpt-4o"}
            ],
        }
    }
    show_model.return_value = {
        "properties": {
            "supportedEndpoints": [
                "/openai/v1/chat/completions",
                "/openai/v1/responses",
            ]
        }
    }

    with pytest.raises(
        Exception,
        match="multiple endpoints.*Specify --endpoint",
    ):
        _model_alias.test_model_alias(
            cmd,
            "production-chat",
            "gateway",
            "rg",
        )


def test_test_endpoint_selects_requested_multi_endpoint_protocol():
    model = {
        "properties": {
            "supportedEndpoints": [
                "/openai/v1/chat/completions",
                "/openai/v1/responses",
                "/anthropic/v1/messages",
            ]
        }
    }

    assert _model_alias._test_endpoint(
        model,
        "production/chat",
        "responses",
    ) == ("responses", "/openai/v1/responses")
    assert _model_alias._test_endpoint(
        model,
        "production/chat",
        "messages",
    ) == ("anthropic-messages", "/anthropic/v1/messages")


def test_test_endpoint_rejects_unavailable_requested_protocol():
    model = {
        "properties": {
            "supportedEndpoints": ["/openai/v1/chat/completions"]
        }
    }

    with pytest.raises(Exception, match="is not supported.*chat-completions"):
        _model_alias._test_endpoint(
            model,
            "production/chat",
            "responses",
        )


@patch("azext_ai_gateway._model_alias._test_model_alias")
def test_test_model_alias_from_pipe_tests_each_listed_alias(test_alias, cmd):
    test_alias.side_effect = [
        {"aliasName": "one"},
        {"aliasName": "two"},
    ]
    stream = StringIO(json.dumps([{"name": "one"}, {"name": "two"}]))

    with patch.object(_model_alias.sys, "stdin", stream):
        result = _model_alias.test_model_alias(
            cmd,
            gateway_name="gateway",
            resource_group_name="rg",
            api_key_name="master",
        )

    assert result == [{"aliasName": "one"}, {"aliasName": "two"}]
    assert test_alias.call_args_list == [
        call(
            cmd,
            "one",
            "gateway",
            "rg",
            "master",
            "default",
            "Reply with OK.",
            None,
            "2026-09-01-preview",
            1,
        ),
        call(
            cmd,
            "two",
            "gateway",
            "rg",
            "master",
            "default",
            "Reply with OK.",
            None,
            "2026-09-01-preview",
            1,
        ),
    ]


@patch("azext_ai_gateway._model_alias._test_model_alias")
def test_test_model_alias_from_pipe_continues_after_failures(
    test_alias,
    cmd,
    caplog,
):
    test_alias.side_effect = [
        {"aliasName": "one"},
        AzCLIError("backend model was not found"),
        {"aliasName": "three"},
    ]
    stream = StringIO(
        json.dumps(
            [{"name": "one"}, {"name": "two"}, {"name": "three"}]
        )
    )

    with (
        patch.object(_model_alias.sys, "stdin", stream),
        pytest.raises(
            AzCLIError,
            match=(
                "2 succeeded and 1 failed.*Failed aliases: two"
            ),
        ),
    ):
        _model_alias.test_model_alias(
            cmd,
            gateway_name="gateway",
            resource_group_name="rg",
            api_key_name="master",
        )

    assert [item.args[1] for item in test_alias.call_args_list] == [
        "one",
        "two",
        "three",
    ]
    assert (
        "Status: Failed. Model alias resource 'two' could not be tested: "
        "backend model was not found"
    ) in caplog.text
