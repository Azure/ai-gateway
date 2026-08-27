# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from types import SimpleNamespace
from unittest.mock import patch

from azure.cli.core.azclierror import AzCLIError

from azext_ai_gateway import _import_execution


def _network(changes=True):
    return {
        "destination": {
            "name": "gateway",
            "current": {
                "publicNetworkAccess": "Enabled",
                "virtualNetworkType": "None",
                "subnetResourceId": None,
            },
            "target": {
                "publicNetworkAccess": "Disabled",
                "virtualNetworkType": "None",
                "subnetResourceId": None,
            },
        },
        "assessment": {
            "status": "ready",
            "changesRequired": changes,
            "reasons": [],
            "warnings": [],
        },
    }


def _model_asset():
    return {
        "assetType": "model",
        "assetSubtype": "llm",
        "source": {
            "id": "source/apis/chat",
            "name": "chat",
            "displayName": "Chat",
            "description": "Chat model",
        },
        "destination": {"name": "gpt-4o", "providerName": "existing"},
        "configuration": {
            "apiFormat": "OpenAIChatCompletions",
            "deployment": {"modelName": "gpt-4o"},
            "supportedEndpoints": ["/chat/completions"],
            "destinationPolicies": [{"type": "tokenLimit", "count": 100}],
            "providerCredentialMapped": True,
        },
        "associatedConfiguration": {},
        "assessment": {
            "status": "ready",
            "conflict": None,
            "reasons": [],
            "warnings": [],
        },
    }


def _mcp_asset():
    return {
        "assetType": "mcpServer",
        "assetSubtype": "mcpApi",
        "source": {
            "id": "source/apis/tools",
            "name": "tools",
            "displayName": "Tools",
            "subscriptionRequired": True,
        },
        "destination": {"name": "tools"},
        "configuration": {
            "endpoint": {
                "namespace": "tools",
                "kind": "mcp",
                "required": True,
                "mcp": {
                    "url": "https://source.example.test/tools",
                    "transport": "streamableHttp",
                },
                "credentials": {
                    "type": "header",
                    "headers": {
                        "Ocp-Apim-Subscription-Key": ["<redacted>"]
                    },
                },
            },
            "destinationPolicies": [],
        },
        "_executionSecrets": {"subscriptionKey": "raw-secret"},
        "associatedConfiguration": {
            "subscriptions": {
                "supportState": "unsupported-critical",
                "items": [{"name": "source-subscription"}],
                "reason": "Subscriptions have no destination relationship.",
            }
        },
        "assessment": {
            "status": "ready",
            "conflict": None,
            "reasons": [],
            "warnings": [],
        },
    }


def test_build_actions_is_ordered_secret_safe_and_policies_are_last():
    actions = _import_execution.build_import_actions(
        _network(),
        [_mcp_asset(), _model_asset()],
    )

    assert actions == sorted(
        actions,
        key=lambda action: (
            action["order"],
            action["type"],
            action["target"],
        ),
    )
    assert all(
        set(action)
        == {
            "type",
            "name",
            "target",
            "order",
            "dependsOn",
            "desired",
            "current",
            "assessment",
            "operation",
            "secretRefs",
        }
        for action in actions
    )
    mcp = next(action for action in actions if action["type"] == "mcpServer")
    assert "raw-secret" not in str(actions)
    assert mcp["secretRefs"] == [
        "source-apim-subscription:source/apis/tools"
    ]
    subscription = next(
        action
        for action in actions
        if action["name"] == "subscriptions"
    )
    assert subscription["assessment"]["status"] == "warn"
    policy = next(action for action in actions if action["type"] == "policy")
    assert policy["order"] == 70
    assert policy["dependsOn"] == ["model:existing/gpt-4o"]


@patch("azext_ai_gateway._import_execution.create_model")
@patch("azext_ai_gateway._import_execution.update_gateway")
def test_execute_actions_runs_dependencies_and_applies_model_policy_last(
    update_gateway,
    create_model,
):
    asset = _model_asset()
    actions = _import_execution.build_import_actions(_network(), [asset])

    result = _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    assert result["summary"] == {
        "succeeded": 3,
        "failed": 0,
        "skipped": 1,
        "blocked": 0,
        "deferred": 0,
    }
    update_gateway.assert_called_once()
    assert create_model.call_count == 2
    assert create_model.call_args_list[-1].kwargs["policies"] == [
        {"type": "tokenLimit", "count": 100}
    ]


@patch("azext_ai_gateway._import_execution.update_gateway")
def test_blocked_graph_executes_no_writes(update_gateway):
    asset = _model_asset()
    asset["associatedConfiguration"] = {
        "managedIdentityAuthentication": {
            "supportState": "unsupported-critical",
            "items": [{"resource": "https://example.test"}],
            "reason": "Destination identity selection is required.",
        }
    }
    actions = _import_execution.build_import_actions(_network(), [asset])

    result = _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    assert result["summary"]["blocked"] == 1
    assert result["summary"]["deferred"] == 3
    update_gateway.assert_not_called()


@patch("azext_ai_gateway._import_execution.create_model")
@patch("azext_ai_gateway._import_execution.update_gateway")
def test_partial_failure_defers_dependent_policy(
    update_gateway,
    create_model,
):
    del update_gateway
    create_model.side_effect = AzCLIError("model write failed")
    asset = _model_asset()
    actions = _import_execution.build_import_actions(_network(), [asset])

    result = _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    assert result["summary"]["failed"] == 1
    assert result["summary"]["deferred"] == 1
    failed = next(
        action for action in result["actions"] if action["status"] == "failed"
    )
    assert failed["error"] == {
        "type": "AzCLIError",
        "message": "model write failed",
    }


@patch("azext_ai_gateway._import_execution.create_mcp")
def test_partial_failure_redacts_runtime_secret_from_error(create_mcp):
    create_mcp.side_effect = AzCLIError(
        "request rejected credential raw-secret"
    )
    asset = _mcp_asset()
    actions = _import_execution.build_import_actions(
        _network(changes=False),
        [asset],
    )

    result = _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    assert "raw-secret" not in str(result)
    failed = next(
        action for action in result["actions"] if action["status"] == "failed"
    )
    assert failed["error"]["message"] == (
        "request rejected credential <redacted>"
    )


@patch("azext_ai_gateway._import_execution.create_mcp")
def test_execution_restores_subscription_key_without_returning_it(create_mcp):
    asset = _mcp_asset()
    actions = _import_execution.build_import_actions(
        _network(changes=False),
        [asset],
    )

    result = _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    endpoint = create_mcp.call_args.kwargs["endpoints"][0]
    assert endpoint["credentials"]["headers"] == {
        "Ocp-Apim-Subscription-Key": ["raw-secret"]
    }
    assert "raw-secret" not in str(result)
    sanitized = _import_execution.sanitize_assets_for_output([asset])
    assert "raw-secret" not in str(sanitized)
    assert "_executionSecrets" not in sanitized[0]


@patch("azext_ai_gateway._import_execution.update_mcp")
def test_mcp_overwrite_replaces_existing_configuration(update_mcp):
    asset = _mcp_asset()
    asset["assessment"]["conflict"] = "overwrite"
    actions = _import_execution.build_import_actions(
        _network(changes=False),
        [asset],
    )

    _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    assert update_mcp.call_args.kwargs["replace"] is True


@patch("azext_ai_gateway._import_execution.create_mcp")
def test_query_endpoint_is_redacted_in_plan_but_preserved_for_execution(create_mcp):
    asset = _mcp_asset()
    asset["configuration"]["endpoint"]["mcp"]["url"] = (
        "https://source.example.test/tools?api-key=raw-query"
    )
    actions = _import_execution.build_import_actions(
        _network(changes=False),
        [asset],
    )

    _import_execution.execute_import_actions(
        SimpleNamespace(),
        "gateway",
        "group",
        actions,
        [asset],
    )

    assert "raw-query" not in str(actions)
    endpoint = create_mcp.call_args.kwargs["endpoints"][0]
    assert endpoint["mcp"]["url"].endswith("api-key=raw-query")
    assert "raw-query" not in str(
        _import_execution.sanitize_assets_for_output([asset])
    )


def test_duplicate_destination_targets_block_the_graph():
    first = _model_asset()
    second = _model_asset()
    second["source"] = {
        **second["source"],
        "id": "source/apis/other-chat",
        "name": "other-chat",
    }

    actions = _import_execution.build_import_actions(
        _network(),
        [first, second],
    )

    duplicates = [
        action
        for action in actions
        if action["target"] == "model:existing/gpt-4o"
        and action["type"] == "model"
    ]
    assert len(duplicates) == 2
    assert all(
        action["assessment"]["status"] == "blocked"
        and action["operation"] == "none"
        for action in duplicates
    )


def test_incompatible_shared_provider_proposals_block_provider_creation():
    first = _model_asset()
    first["destination"] = {
        "name": "first",
        "providerName": "new-provider",
    }
    first["configuration"]["providerCreate"] = {
        "name": "new-provider",
        "kind": "Custom",
        "endpoint": "https://one.example.test",
        "authKind": "ApiKey",
        "apiKeyHeaderName": "api-key",
        "secretRefs": ["source:one"],
    }
    second = _model_asset()
    second["source"] = {**second["source"], "id": "source/apis/second"}
    second["destination"] = {
        "name": "second",
        "providerName": "new-provider",
    }
    second["configuration"]["providerCreate"] = {
        **first["configuration"]["providerCreate"],
        "endpoint": "https://two.example.test",
        "secretRefs": ["source:two"],
    }

    actions = _import_execution.build_import_actions(
        _network(),
        [first, second],
    )

    provider = next(
        action for action in actions if action["target"] == "provider:new-provider"
    )
    assert provider["assessment"]["status"] == "blocked"
    assert "incompatible configuration" in str(
        provider["assessment"]["reasons"]
    )
