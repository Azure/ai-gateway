# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import (
    AzCLIError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_ai_gateway import _model_provider


class FakeResponse:
    def __init__(self, body=None):
        self._body = body
        self.headers = {}
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_model_providers_follows_pages(send_request, _, cmd):
    send_request.side_effect = [
        FakeResponse(
            {
                "value": [{"name": "foundry"}],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        FakeResponse({"value": [{"name": "custom"}]}),
    ]

    result = _model_provider.list_model_providers(cmd, "gateway", "rg")

    assert [provider["name"] for provider in result] == ["foundry", "custom"]
    assert send_request.call_args_list[0].args[2].endswith(
        "/workspaces/default/modelProviders"
    )
    assert send_request.call_args_list[1] == call(
        cmd.cli_ctx,
        "GET",
        "https://management.azure.com/next",
        uri_parameters=None,
        body=None,
    )


def test_format_model_provider_list_table():
    providers = [
        {
            "name": "foundry",
            "properties": {
                "kind": "Foundry",
                "foundry": {
                    "endpoint": "https://foundry.example.com",
                    "authentication": {"kind": "ManagedIdentity"},
                },
            },
        },
        {
            "name": "custom",
            "properties": {
                "kind": "Custom",
                "custom": {
                    "endpoint": "https://models.example.com",
                    "authentication": {"kind": "ApiKey"},
                },
            },
        },
    ]

    assert _model_provider.format_model_provider_list_table(providers) == [
        {
            "Name": "foundry",
            "Provider type": "Foundry",
            "Base endpoint": "https://foundry.example.com",
            "Auth": "ManagedIdentity",
        },
        {
            "Name": "custom",
            "Provider type": "Custom",
            "Base endpoint": "https://models.example.com",
            "Auth": "ApiKey",
        },
    ]


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_foundry_provider_builds_managed_identity_payload(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"name": "foundry"})
    resource_id = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.CognitiveServices/accounts/account"
    )

    _model_provider.create_model_provider(
        cmd,
        "foundry",
        "gateway",
        "rg",
        "Foundry",
        "https://foundry.example.com",
        display_name="Foundry",
        resource_ids=[resource_id],
        managed_identity_resource="https://cognitiveservices.azure.com",
        managed_identity_client_id="00000000-0000-0000-0000-000000000000",
        no_sync=True,
    )

    assert json.loads(send_request.call_args.kwargs["body"]) == {
        "properties": {
            "kind": "Foundry",
            "displayName": "Foundry",
            "foundry": {
                "endpoint": "https://foundry.example.com",
                "resourceIds": [resource_id],
                "authentication": {
                    "kind": "ManagedIdentity",
                    "managedIdentity": {
                        "resource": "https://cognitiveservices.azure.com",
                        "clientId": "00000000-0000-0000-0000-000000000000",
                    },
                },
            },
        }
    }


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_custom_provider_builds_api_key_payload(
    send_request,
    _,
    cmd,
):
    send_request.return_value = FakeResponse({"name": "custom"})

    _model_provider.create_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
        "Custom",
        "https://models.example.com",
        api_key_header_name="Authorization",
        api_key_value="secret",
        no_sync=True,
    )

    assert json.loads(send_request.call_args.kwargs["body"]) == {
        "properties": {
            "kind": "Custom",
            "custom": {
                "endpoint": "https://models.example.com",
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {
                        "headerName": "Authorization",
                        "value": "secret",
                    },
                },
            },
        }
    }


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._model_provider._synchronize_model_provider")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_provider_syncs_models_by_default(
    send_request,
    sync_provider,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {
            "name": "custom",
            "properties": {"kind": "Custom"},
        }
    )

    with patch.object(_model_provider.logger, "warning") as warning:
        result = _model_provider.create_model_provider(
            cmd,
            "custom",
            "gateway",
            "rg",
            "Custom",
            "https://models.example.com",
            api_key_header_name="Authorization",
            api_key_value="secret",
        )

    sync_provider.assert_called_once()
    sync_args = sync_provider.call_args
    assert sync_args.args[0] is cmd
    assert sync_args.args[1]["properties"]["custom"]["authentication"][
        "apiKey"
    ]["value"] == "secret"
    assert sync_args.args[3] == "custom"
    assert sync_args.kwargs == {
        "dry_run": False,
        "delete_missing": False,
        "yes": False,
        "api_key_value": "secret",
    }
    assert result == {
        "name": "custom",
        "properties": {"kind": "Custom"},
    }
    assert warning.call_args_list[0] == call(
        "Creating model provider '%s'...",
        "custom",
    )
    assert warning.call_args_list[-1] == call("Models imported.")


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch(
    "azext_ai_gateway._model_provider._synchronize_model_provider",
    side_effect=RuntimeError("discovery exploded"),
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_provider_reports_partial_success_when_sync_fails(
    send_request,
    _sync_provider,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"name": "custom", "properties": {"kind": "Custom"}}
    )

    with pytest.raises(
        AzCLIError,
        match=(
            "created successfully, but model import failed.*"
            "Inner error: discovery exploded"
        ),
    ):
        _model_provider.create_model_provider(
            cmd,
            "custom",
            "gateway",
            "rg",
            "Custom",
            "https://models.example.com",
            api_key_header_name="Authorization",
            api_key_value="secret",
        )

    assert send_request.call_count == 1


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch(
    "azext_ai_gateway._model_provider.prompt_pass",
    return_value="prompted-secret",
)
@patch("azext_ai_gateway._model_provider._synchronize_model_provider")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_custom_provider_prompts_before_creation(
    send_request,
    _sync_provider,
    prompt,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"name": "custom", "properties": {"kind": "Custom"}}
    )

    _model_provider.create_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
        "Custom",
        "https://models.example.com",
        api_key_header_name="Authorization",
    )

    prompt.assert_called_once_with("Custom provider API key: ")
    body = json.loads(send_request.call_args.kwargs["body"])
    assert body["properties"]["custom"]["authentication"]["apiKey"][
        "value"
    ] == "prompted-secret"


def test_create_foundry_provider_requires_resource_ids(cmd):
    with pytest.raises(RequiredArgumentMissingError, match="--resource-ids"):
        _model_provider.create_model_provider(
            cmd,
            "foundry",
            "gateway",
            "rg",
            "Foundry",
            "https://foundry.example.com",
            managed_identity_resource="https://cognitiveservices.azure.com",
        )


def test_custom_provider_rejects_managed_identity(cmd):
    with pytest.raises(
        InvalidArgumentValueError,
        match="only support API key",
    ):
        _model_provider.create_model_provider(
            cmd,
            "custom",
            "gateway",
            "rg",
            "Custom",
            "https://models.example.com",
            auth_kind="ManagedIdentity",
            managed_identity_resource="https://cognitiveservices.azure.com",
        )


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_display_name_does_not_send_provider_credentials(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "properties": {
                    "kind": "Custom",
                    "custom": {
                        "endpoint": "https://models.example.com",
                        "authentication": {
                            "kind": "ApiKey",
                            "apiKey": {"headerName": "Authorization"},
                        },
                    },
                }
            }
        ),
        FakeResponse({"name": "custom"}),
    ]

    _model_provider.update_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
        display_name="Custom Models",
    )

    assert json.loads(send_request.call_args_list[1].kwargs["body"]) == {
        "properties": {"displayName": "Custom Models"}
    }


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_api_key_preserves_endpoint_and_header(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "properties": {
                    "kind": "Custom",
                    "custom": {
                        "endpoint": "https://models.example.com",
                        "authentication": {
                            "kind": "ApiKey",
                            "apiKey": {"headerName": "Authorization"},
                        },
                    },
                }
            }
        ),
        FakeResponse({"name": "custom"}),
    ]

    _model_provider.update_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
        api_key_value="new-secret",
    )

    assert json.loads(send_request.call_args_list[1].kwargs["body"]) == {
        "properties": {
            "custom": {
                "endpoint": "https://models.example.com",
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {
                        "headerName": "Authorization",
                        "value": "new-secret",
                    },
                },
            }
        }
    }


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_foundry_api_key_omits_unchanged_write_only_value(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "properties": {
                    "kind": "Foundry",
                    "foundry": {
                        "endpoint": "https://old.example.com",
                        "resourceIds": ["/accounts/account"],
                        "authentication": {
                            "kind": "ApiKey",
                            "apiKey": {"headerName": "api-key"},
                        },
                    },
                }
            }
        ),
        FakeResponse({"name": "foundry"}),
    ]

    _model_provider.update_model_provider(
        cmd,
        "foundry",
        "gateway",
        "rg",
        endpoint="https://new.example.com",
    )

    body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert body["properties"]["foundry"]["authentication"]["apiKey"] == {
        "headerName": "api-key"
    }
    assert "value" not in str(body)


def test_provider_outputs_redact_api_key_values():
    provider = {
        "properties": {
            "foundry": {
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {"headerName": "api-key", "value": "secret"},
                }
            },
            "custom": {
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {
                        "headerName": "Authorization",
                        "value": "other-secret",
                    },
                }
            },
        }
    }

    redacted = _model_provider._redact_provider_secrets(provider)

    assert "value" not in redacted["properties"]["foundry"][
        "authentication"
    ]["apiKey"]
    assert "value" not in redacted["properties"]["custom"][
        "authentication"
    ]["apiKey"]
    assert provider["properties"]["custom"]["authentication"]["apiKey"][
        "value"
    ] == "other-secret"


def test_update_requires_a_property(cmd):
    with pytest.raises(RequiredArgumentMissingError):
        _model_provider._build_update_properties(
            {"properties": {"kind": "Custom"}},
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_show_and_delete_model_provider_use_resource_path(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse({"name": "custom"}),
        FakeResponse(),
    ]

    shown = _model_provider.show_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
    )
    deleted = _model_provider.delete_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
    )

    assert shown["name"] == "custom"
    assert deleted is None
    assert send_request.call_args_list[0].args[1] == "GET"
    assert send_request.call_args_list[1].args[1] == "DELETE"
    assert send_request.call_args_list[0].args[2].endswith(
        "/workspaces/default/modelProviders/custom"
    )


def test_supported_endpoints_follow_foundry_capabilities():
    assert _model_provider._supported_endpoints(
        "openai",
        {
            "chatCompletion": "true",
            "embeddings": "TRUE",
            "responses": "false",
        },
    ) == [
        "/openai/v1/chat/completions",
        "/openai/v1/embeddings",
    ]
    assert _model_provider._supported_endpoints("anthropic", {}) == [
        "/anthropic/v1/messages"
    ]
    assert _model_provider._supported_endpoints("openai", None) == [
        "/openai/v1/chat/completions"
    ]


def test_supported_endpoints_default_when_capabilities_are_empty():
    assert _model_provider._supported_endpoints("OpenAI", {}) == [
        "/openai/v1/chat/completions"
    ]


@patch("azext_ai_gateway._model_provider._request")
def test_foundry_listing_uses_foundry_api_version(request):
    request.side_effect = [
        FakeResponse(
            {
                "value": [{"name": "one"}],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        FakeResponse({"value": [{"name": "two"}]}),
    ]

    result = _model_provider._list_foundry_resources(
        None,
        "/accounts/account/deployments",
    )

    assert [item["name"] for item in result] == ["one", "two"]
    assert request.call_args_list[0].kwargs["api_version"] == "2024-10-01"
    assert request.call_args_list[1].kwargs == {
        "include_api_version": False,
        "api_version": "2024-10-01",
    }


@patch("azext_ai_gateway._model_provider._list_all")
@patch("azext_ai_gateway._model_provider._list_foundry_resources")
def test_sync_plan_creates_new_models_and_reports_stale_models(
    list_foundry,
    list_all,
):
    deployment = {
        "id": "/accounts/account/deployments/gpt-4o",
        "name": "gpt-4o",
        "properties": {
            "model": {
                "format": "OpenAI",
                "name": "gpt-4o",
                "version": "2024-11-20",
            }
        },
    }
    list_foundry.side_effect = [
        [deployment],
        [
            {
                "format": "OpenAI",
                "name": "gpt-4o",
                "version": "2024-11-20",
                "capabilities": {"responses": "true"},
            }
        ],
    ]
    list_all.side_effect = [
        [{"id": "/provider/models/old", "name": "old"}],
        [{"id": "/modelProviders/foundry/models/old", "name": "old"}],
    ]
    provider = {
        "name": "foundry",
        "properties": {
            "kind": "Foundry",
            "foundry": {"resourceIds": ["/accounts/account"]},
        },
    }

    changes = _model_provider._sync_plan(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/foundry",
        delete_missing=False,
    )

    assert changes == [
        {
            "action": "create",
            "name": "gpt-4o",
            "status": "planned",
            "properties": {
                "displayName": "gpt-4o",
                "supportedEndpoints": ["/openai/v1/responses"],
                "deployment": {
                    "resourceId": "/accounts/account/deployments/gpt-4o",
                    "modelName": "gpt-4o",
                    "modelVersion": "2024-11-20",
                },
            },
        },
        {
            "action": "skip",
            "name": "old",
            "status": "stale",
            "reason": "Use --delete-missing to remove this stale model.",
            "id": "/provider/models/old",
        },
    ]


@patch("azext_ai_gateway._model_provider._list_all")
@patch("azext_ai_gateway._model_provider._list_foundry_resources")
def test_sync_plan_skips_duplicate_and_cross_provider_names(
    list_foundry,
    list_all,
):
    def deployment(name, resource_id):
        return {
            "id": resource_id,
            "name": name,
            "properties": {
                "capabilities": {"chatCompletion": "true"},
                "model": {"format": "OpenAI", "name": name},
            },
        }

    list_foundry.side_effect = [
        [
            deployment("duplicate", "/one/duplicate"),
            deployment("duplicate", "/two/duplicate"),
            deployment("conflict", "/one/conflict"),
        ]
    ]
    list_all.side_effect = [
        [],
        [
            {
                "id": "/modelProviders/other/models/conflict",
                "name": "conflict",
            }
        ],
    ]
    provider = {
        "name": "foundry",
        "properties": {
            "kind": "Foundry",
            "foundry": {"resourceIds": ["/accounts/account"]},
        },
    }

    changes = _model_provider._sync_plan(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/foundry",
        delete_missing=True,
    )

    assert [
        (change["action"], change["name"], change["status"])
        for change in changes
    ] == [
        ("create", "duplicate", "planned"),
        ("skip", "duplicate", "conflict"),
        ("skip", "conflict", "conflict"),
    ]


@patch("azext_ai_gateway._model_provider._list_all")
@patch("azext_ai_gateway._model_provider._list_foundry_resources")
def test_sync_plan_normalizes_foundry_deployment_names(
    list_foundry,
    list_all,
):
    list_foundry.return_value = [
        {
            "id": "/accounts/account/deployments/gpt-4.1",
            "name": "gpt-4.1",
            "properties": {
                "capabilities": {"chatCompletion": "true"},
                "model": {
                    "format": "OpenAI",
                    "name": "gpt-4.1",
                    "version": "2025-04-14",
                },
            },
        }
    ]
    list_all.side_effect = [
        [{"id": "/provider/models/gpt-4-1", "name": "gpt-4-1"}],
        [{"id": "/provider/models/gpt-4-1", "name": "gpt-4-1"}],
    ]
    provider = {
        "name": "foundry",
        "properties": {
            "kind": "Foundry",
            "foundry": {"resourceIds": ["/accounts/account"]},
        },
    }

    changes = _model_provider._sync_plan(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/foundry",
        delete_missing=True,
    )

    assert changes == []


@patch("azext_ai_gateway._model_provider._list_all")
@patch("azext_ai_gateway._model_provider._list_foundry_resources")
def test_sync_plan_uses_normalized_resource_name_and_deployment_name(
    list_foundry,
    list_all,
):
    list_foundry.return_value = [
        {
            "id": "/accounts/account/deployments/o3.mini",
            "name": "o3.mini",
            "properties": {
                "capabilities": {"responses": "true"},
                "model": {
                    "format": "OpenAI",
                    "name": "o3-mini",
                    "version": "2",
                },
            },
        }
    ]
    list_all.side_effect = [[], []]
    provider = {
        "name": "foundry",
        "properties": {
            "kind": "Foundry",
            "foundry": {"resourceIds": ["/accounts/account"]},
        },
    }

    changes = _model_provider._sync_plan(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/foundry",
        delete_missing=False,
    )

    assert changes[0]["name"] == "o3-mini"
    assert changes[0]["properties"] == {
        "displayName": "o3.mini",
        "supportedEndpoints": ["/openai/v1/responses"],
        "deployment": {
            "resourceId": "/accounts/account/deployments/o3.mini",
            "modelName": "o3.mini",
            "modelVersion": "2",
        },
    }


def test_supported_endpoints_matches_portal_capability_semantics():
    capabilities = {
        "responses": "true",
        "chatCompletion": " TRUE ",
        "unknownCapability": "true",
    }

    assert _model_provider._supported_endpoints(
        " OpenAI ",
        capabilities,
    ) == [
        "/openai/v1/chat/completions",
        "/openai/v1/responses",
    ]
    assert _model_provider._supported_endpoints(
        "OpenAI",
        {"unknownCapability": "true"},
    ) == []
    assert _model_provider._supported_endpoints(
        " Anthropic ",
        {},
    ) == ["/anthropic/v1/messages"]


def test_custom_discovery_error_includes_provider_code():
    response = SimpleNamespace(
        ok=False,
        status_code=401,
        json=lambda: {"error": {"code": "invalid_api_key"}},
    )

    with pytest.raises(
        InvalidArgumentValueError,
        match=r"HTTP 401 \(invalid_api_key\)",
    ):
        _model_provider._parse_custom_model_ids(
            response,
            "https://models.example.com/v1/models",
        )


@patch("azext_ai_gateway._model_provider._request")
def test_refresh_foundry_api_key_matches_portal(request):
    request.side_effect = [FakeResponse({"key1": "secret"}), FakeResponse({})]
    provider = {
        "properties": {
            "foundry": {
                "endpoint": "https://account.openai.azure.com",
                "resourceIds": ["/accounts/account"],
                "authentication": {"kind": "ManagedIdentity"},
            }
        }
    }

    _model_provider._refresh_foundry_api_key(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/foundry",
    )

    assert request.call_args_list == [
        call(
            None,
            "POST",
            "/accounts/account/listKeys",
            {},
            api_version="2024-10-01",
        ),
        call(
            None,
            "PATCH",
            "/gateway/workspaces/default/modelProviders/foundry",
            {
                "properties": {
                    "foundry": {
                        "endpoint": "https://account.openai.azure.com",
                        "resourceIds": ["/accounts/account"],
                        "authentication": {
                            "kind": "ApiKey",
                            "apiKey": {
                                "headerName": "Authorization",
                                "value": "Bearer secret",
                            },
                        },
                    }
                }
            },
        ),
    ]


@patch("azext_ai_gateway._model_provider._list_all")
@patch("azext_ai_gateway._model_provider._list_foundry_resources")
def test_sync_plan_treats_every_gateway_model_name_as_reserved(
    list_foundry,
    list_all,
):
    list_foundry.return_value = [
        {
            "id": "/accounts/account/deployments/new",
            "name": "new",
            "properties": {
                "capabilities": {"chatCompletion": "true"},
                "model": {"format": "OpenAI", "name": "new"},
            },
        }
    ]
    list_all.side_effect = [
        [],
        [{"id": "/workspaces/default/models/new", "name": "new"}],
    ]
    provider = {
        "name": "foundry",
        "properties": {
            "kind": "Foundry",
            "foundry": {"resourceIds": ["/accounts/account"]},
        },
    }

    changes = _model_provider._sync_plan(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/foundry",
        delete_missing=False,
    )

    assert [(change["name"], change["status"]) for change in changes] == [
        ("new", "conflict")
    ]
@pytest.mark.parametrize(
    "endpoint",
    [
        "http://models.example.com",
        "https://user:password@models.example.com",
        "https://models.example.com?api-key=secret",
        "https://models.example.com/#fragment",
        "https://models.example.com\r\nX-Injected: value",
        "--config",
    ],
)
def test_provider_endpoint_rejects_unsafe_urls(endpoint):
    with pytest.raises(InvalidArgumentValueError):
        _model_provider._build_provider_config(
            "Custom",
            endpoint,
            None,
            "ApiKey",
            "api-key",
            "secret",
            None,
            None,
        )


def test_provider_endpoint_is_trimmed_and_normalized():
    _, configuration = _model_provider._build_provider_config(
        "Custom",
        "  https://models.example.com/base/  ",
        None,
        "ApiKey",
        "api-key",
        "secret",
        None,
        None,
    )

    assert configuration["endpoint"] == "https://models.example.com/base"


@patch("azext_ai_gateway._model_provider._fetch_custom_model_ids")
def test_discover_custom_models_merges_openai_and_anthropic(fetch):
    api_key_value = "Bearer " + "secret"

    def discover(_, headers, _proxy):
        if "anthropic-version" in headers:
            assert headers["x-api-key"] == api_key_value
            assert headers["anthropic-version"] == "2023-06-01"
            return ["claude-sonnet-4", "shared"]
        assert headers["api-key"] == api_key_value
        return ["gpt-4o", "shared"]

    fetch.side_effect = discover
    provider = {
        "properties": {
            "kind": "Custom",
            "custom": {
                "endpoint": " https://models.example.com/ ",
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {
                        "headerName": "api-key",
                        "value": api_key_value,
                    },
                },
            },
        },
    }

    models = _model_provider._discover_custom_models(provider)

    assert models == [
        {
            "modelName": "claude-sonnet-4",
            "supportedEndpoints": ["/v1/messages"],
        },
        {
            "modelName": "gpt-4o",
            "supportedEndpoints": ["/v1/chat/completions"],
        },
        {
            "modelName": "shared",
            "supportedEndpoints": [
                "/v1/chat/completions",
                "/v1/messages",
            ],
        },
    ]
    assert all(
        args.args[0] == "https://models.example.com/v1/models"
        for args in fetch.call_args_list
    )


@patch("azext_ai_gateway._model_provider._fetch_custom_model_ids")
def test_discover_authorization_provider_checks_both_apis(fetch):
    def discover(_, headers, _proxy):
        if "anthropic-version" in headers:
            raise InvalidArgumentValueError("Anthropic discovery failed.")
        return ["openai-model"]

    fetch.side_effect = discover
    provider = {
        "properties": {
            "custom": {
                "endpoint": "https://api.meta.ai",
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {"headerName": "Authorization"},
                },
            }
        }
    }

    models = _model_provider._discover_custom_models(
        provider,
        "Bearer exact-key",
    )

    assert models == [
        {
            "modelName": "openai-model",
            "supportedEndpoints": ["/v1/chat/completions"],
        }
    ]
    assert fetch.call_count == 2
    openai_headers = fetch.call_args_list[0].args[1]
    anthropic_headers = fetch.call_args_list[1].args[1]
    assert openai_headers["Authorization"] == "Bearer exact-key"
    assert anthropic_headers["x-api-key"] == "Bearer exact-key"
    assert anthropic_headers["anthropic-version"] == "2023-06-01"


@patch("azext_ai_gateway._model_provider._fetch_custom_model_ids")
def test_discover_custom_models_tolerates_one_failed_api(fetch):
    def discover(_, headers, _proxy):
        if "anthropic-version" in headers:
            return ["claude-sonnet-4"]
        raise InvalidArgumentValueError(
            "The provider's /v1/models endpoint returned HTTP 401."
        )

    fetch.side_effect = discover
    provider = {
        "properties": {
            "custom": {
                "endpoint": "https://models.example.com",
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {
                        "headerName": "x-api-key",
                        "value": "secret",
                    },
                },
            }
        }
    }

    assert _model_provider._discover_custom_models(provider) == [
        {
            "modelName": "claude-sonnet-4",
            "supportedEndpoints": ["/v1/messages"],
        }
    ]


@patch("azext_ai_gateway._model_provider._curl_get")
@patch("azext_ai_gateway._model_provider.requests.post")
@patch("azext_ai_gateway._model_provider.Profile")
def test_custom_model_discovery_falls_back_to_portal_cors_proxy(
    profile,
    post,
    curl_get,
):
    profile.return_value.get_raw_token.return_value = (
        ("Bearer", "arm-token", {}),
        "sub",
        "tenant",
    )
    post.return_value = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {"data": [{"id": "model"}]},
    )
    curl_get.return_value = SimpleNamespace(
        ok=False,
        status_code=401,
        json=lambda: {"error": {"code": "invalid_api_key"}},
    )
    cmd = SimpleNamespace(
        cli_ctx=SimpleNamespace(
            cloud=SimpleNamespace(
                endpoints=SimpleNamespace(
                    resource_manager="https://management.azure.com/",
                )
            )
        )
    )
    provider_path = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.ApiManagement/service/gateway/workspaces/default/"
        "modelProviders/custom"
    )

    context = _model_provider._cors_proxy_context(cmd, provider_path)
    models = _model_provider._fetch_custom_model_ids(
        "https://models.example.com/v1/models",
        {"Authorization": "exact-key"},
        context,
    )

    assert models == ["model"]
    curl_get.assert_called_once()
    assert post.call_args.args[0] == (
        "https://apimanagement-cors-proxy-prd.azure-api.net/send"
    )
    headers = post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer arm-token"
    assert headers["Origin"] == "https://ai.gateway.azure.com"
    assert headers["Referer"] == "https://ai.gateway.azure.com/"
    assert headers["Ocp-Apim-Subscription"] == "sub"
    assert headers["Ocp-Apim-Resource-Group"] == "rg"
    assert headers["Ocp-Apim-Service-Name"] == "gateway"
    assert headers["Ocp-Apim-Url"] == (
        "https://models.example.com/v1/models"
    )
    assert headers["Ocp-Apim-Method"] == "GET"
    assert headers["Ocp-Apim-Header-Authorization"] == "exact-key"


@patch("azext_ai_gateway._model_provider._curl_get")
@patch("azext_ai_gateway._model_provider.requests.post")
def test_custom_model_discovery_prefers_direct_request(post, curl_get):
    curl_get.return_value = SimpleNamespace(
        ok=True,
        status_code=200,
        json=lambda: {"data": [{"id": "model"}]},
    )

    models = _model_provider._fetch_custom_model_ids(
        "https://models.example.com/v1/models",
        {"Authorization": "exact-key"},
        {"url": "https://proxy.example.com/send", "headers": {}},
    )

    assert models == ["model"]
    post.assert_not_called()
    curl_get.assert_called_once_with(
        "https://models.example.com/v1/models",
        {"Authorization": "exact-key"},
    )


@patch("azext_ai_gateway._model_provider.subprocess.run")
def test_curl_get_passes_secret_through_stdin(run):
    run.return_value = SimpleNamespace(
        returncode=0,
        stdout='{"data":[{"id":"model"}]}\n200',
        stderr="",
    )

    response = _model_provider._curl_get(
        "https://models.example.com/v1/models",
        {
            "Accept": "application/json",
            "Authorization": "Bearer exact-key",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"data": [{"id": "model"}]}
    assert "exact-key" not in " ".join(run.call_args.args[0])
    assert run.call_args.args[0][-2:] == [
        "--",
        "https://models.example.com/v1/models",
    ]
    assert run.call_args.kwargs["input"] == (
        "Accept: application/json\n"
        "Authorization: Bearer exact-key\n"
    )


@patch("azext_ai_gateway._model_provider._fetch_custom_model_ids")
def test_discover_custom_models_fails_when_both_apis_fail(fetch):
    fetch.side_effect = InvalidArgumentValueError(
        "The provider's /v1/models endpoint returned HTTP 401."
    )
    provider = {
        "properties": {
            "custom": {
                "endpoint": "https://models.example.com",
                "authentication": {
                    "kind": "ApiKey",
                    "apiKey": {
                        "headerName": "api-key",
                        "value": "secret",
                    },
                },
            }
        }
    }

    with pytest.raises(InvalidArgumentValueError, match="HTTP 401"):
        _model_provider._discover_custom_models(provider)


@patch("azext_ai_gateway._model_provider._list_all")
@patch("azext_ai_gateway._model_provider._discover_custom_models")
def test_custom_sync_plan_creates_normalized_models_and_reports_stale(
    discover,
    list_all,
):
    discover.return_value = [
        {
            "modelName": "o3.mini",
            "supportedEndpoints": ["/v1/chat/completions"],
        }
    ]
    list_all.side_effect = [
        [{"id": "/provider/models/old", "name": "old"}],
        [{"id": "/provider/models/old", "name": "old"}],
    ]
    provider = {
        "properties": {
            "kind": "Custom",
            "custom": {"endpoint": "https://models.example.com"},
        }
    }

    changes = _model_provider._sync_plan(
        None,
        provider,
        "/gateway/workspaces/default/modelProviders/custom",
        delete_missing=False,
    )

    assert changes == [
        {
            "action": "create",
            "name": "o3-mini",
            "status": "planned",
            "properties": {
                "displayName": "o3.mini",
                "supportedEndpoints": ["/v1/chat/completions"],
                "deployment": {"modelName": "o3.mini"},
            },
        },
        {
            "action": "skip",
            "name": "old",
            "status": "stale",
            "reason": "Use --delete-missing to remove this stale model.",
            "id": "/provider/models/old",
        },
    ]


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._model_provider._refresh_foundry_api_key")
@patch("azext_ai_gateway._model_provider._sync_plan")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sync_supports_custom_provider(
    send_request,
    sync_plan,
    refresh_foundry_key,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {"name": "custom", "properties": {"kind": "Custom"}}
        ),
        FakeResponse({"name": "model"}),
    ]
    sync_plan.return_value = [
        {
            "action": "create",
            "name": "model",
            "status": "planned",
            "properties": {
                "displayName": "model",
                "supportedEndpoints": ["/v1/chat/completions"],
                "deployment": {"modelName": "model"},
            },
        }
    ]

    result = _model_provider.sync_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
        api_key_value="secret",
    )

    assert result["summary"]["created"] == 1
    assert sync_plan.call_args.args[-1] == "secret"
    refresh_foundry_key.assert_not_called()
    assert json.loads(send_request.call_args_list[1].kwargs["body"]) == {
        "properties": {
            "displayName": "model",
            "supportedEndpoints": ["/v1/chat/completions"],
            "deployment": {"modelName": "model"},
        }
    }


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch(
    "azext_ai_gateway._model_provider.prompt_pass",
    side_effect=_model_provider.NoTTYException(),
)
@patch("azext_ai_gateway._model_provider._sync_plan")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sync_custom_provider_requires_api_key(
    send_request,
    sync_plan,
    _prompt,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"name": "custom", "properties": {"kind": "Custom"}}
    )

    with pytest.raises(
        RequiredArgumentMissingError,
        match="--api-key-value",
    ):
        _model_provider.sync_model_provider(
            cmd,
            "custom",
            "gateway",
            "rg",
        )

    sync_plan.assert_not_called()


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch(
    "azext_ai_gateway._model_provider.prompt_pass",
    return_value="prompted-secret",
)
@patch("azext_ai_gateway._model_provider._sync_plan", return_value=[])
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sync_custom_provider_prompts_for_api_key(
    send_request,
    sync_plan,
    prompt,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"name": "custom", "properties": {"kind": "Custom"}}
    )

    result = _model_provider.sync_model_provider(
        cmd,
        "custom",
        "gateway",
        "rg",
    )

    prompt.assert_called_once_with("Custom provider API key: ")
    assert sync_plan.call_args.args[-1] == "prompted-secret"
    assert result["summary"]["created"] == 0


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._model_provider._sync_plan")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sync_applies_create_and_delete_changes(
    send_request,
    sync_plan,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {"name": "foundry", "properties": {"kind": "Foundry"}}
        ),
        FakeResponse({"name": "new"}),
        FakeResponse(),
    ]
    sync_plan.return_value = [
        {
            "action": "create",
            "name": "new",
            "status": "planned",
            "properties": {"displayName": "New"},
        },
        {
            "action": "delete",
            "name": "old",
            "status": "planned",
            "id": "/modelProviders/foundry/models/old",
            "reason": "Foundry deployment no longer exists.",
        },
    ]

    with (
        patch.object(_model_provider.logger, "warning") as warning,
        patch.object(
            _model_provider,
            "_refresh_foundry_api_key",
        ) as refresh_api_key,
    ):
        result = _model_provider.sync_model_provider(
            cmd,
            "foundry",
            "gateway",
            "rg",
            delete_missing=True,
            yes=True,
        )

    refresh_api_key.assert_called_once()
    assert result["summary"] == {
        "created": 1,
        "deleted": 1,
        "planned": 0,
        "conflicts": 0,
        "stale": 0,
    }
    assert send_request.call_args_list[1].args[1] == "PUT"
    assert send_request.call_args_list[2].args[1] == "DELETE"
    assert json.loads(send_request.call_args_list[1].kwargs["body"]) == {
        "properties": {"displayName": "New"}
    }
    assert call("Creating model '%s'...", "new") in warning.call_args_list
    assert call("Deleting stale model '%s'...", "old") in warning.call_args_list
    assert warning.call_args_list[-1] == call(
        "Synchronization complete: %d created, %d deleted, "
        "%d conflict(s), %d stale model(s).",
        1,
        1,
        0,
        0,
    )


@patch(
    "azext_ai_gateway._model_provider.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._model_provider._sync_plan")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sync_requires_confirmation_before_deleting(
    send_request,
    sync_plan,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"name": "foundry", "properties": {"kind": "Foundry"}}
    )
    sync_plan.return_value = [
        {
            "action": "delete",
            "name": "old",
            "status": "planned",
            "id": "/modelProviders/foundry/models/old",
        }
    ]

    with pytest.raises(RequiredArgumentMissingError, match="--yes"):
        _model_provider.sync_model_provider(
            cmd,
            "foundry",
            "gateway",
            "rg",
            delete_missing=True,
        )

    assert send_request.call_count == 1
