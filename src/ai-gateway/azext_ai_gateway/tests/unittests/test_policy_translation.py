# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError

from azext_ai_gateway import _policy_translation


REQUIRED_POLICY_FIELDS = {
    "statement",
    "docsUrl",
    "validScopes",
    "validSections",
    "applicableAssets",
    "applicableSubtypes",
    "destinationCapability",
    "supportLevel",
    "action",
    "criticality",
    "omittedBehavior",
    "guidance",
    "handler",
}


def test_policy_index_is_json_and_statements_are_unique():
    with _policy_translation.POLICY_INDEX_PATH.open(encoding="utf-8") as file:
        index = json.load(file)

    statements = [policy["statement"] for policy in index["policies"]]

    assert index["schemaVersion"] == 1
    assert len(statements) == len(set(statements))
    assert statements == sorted(statements)
    assert len(statements) >= 67


def test_policy_index_covers_current_reference_and_legacy_handlers():
    expected = {
        "authentication-managed-identity",
        "azure-openai-token-limit",
        "choose",
        "forward-request",
        "llm-content-safety",
        "llm-token-limit",
        "rate-limit-by-key",
        "send-service-bus-message",
        "set-backend-service",
        "sql-data-source",
        "validate-jwt",
        "wait",
    }

    assert expected <= set(_policy_translation.POLICY_TRANSLATION_CATALOG)


def test_policy_index_entries_match_schema_and_enums():
    for statement, capability in (
        _policy_translation.POLICY_TRANSLATION_CATALOG.items()
    ):
        assert set(capability) == REQUIRED_POLICY_FIELDS
        assert capability["statement"] == statement
        assert capability["docsUrl"].startswith("https://learn.microsoft.com/")
        assert capability["supportLevel"] in {
            "exact",
            "reduced",
            "unsupported",
        }
        assert capability["action"] in {"import", "warn", "block"}
        assert capability["destinationCapability"]["mode"] in {
            "configuration",
            "inlinePolicy",
            "none",
        }
        assert isinstance(capability["omittedBehavior"], str)
        assert capability["omittedBehavior"]
        assert isinstance(capability["guidance"], str)
        assert capability["guidance"]


def test_every_import_action_resolves_to_declared_handler():
    imported = [
        capability
        for capability in _policy_translation.POLICY_TRANSLATION_CATALOG.values()
        if capability["action"] == "import"
    ]

    assert imported
    for capability in imported:
        assert capability["handler"] is not None
        assert _policy_translation.policy_handler(capability) is not None


def test_non_import_actions_do_not_claim_handlers():
    for capability in _policy_translation.POLICY_TRANSLATION_CATALOG.values():
        if capability["action"] != "import":
            assert capability["handler"] is None


def test_list_policy_translation_support_filters_and_returns_copies():
    reduced = _policy_translation.list_policy_translation_support("reduced")

    assert {item["statement"] for item in reduced} == {
        "azure-openai-token-limit",
        "forward-request",
        "llm-content-safety",
        "llm-token-limit",
        "set-backend-service",
    }
    reduced[0]["guidance"] = "changed"
    assert (
        _policy_translation.POLICY_TRANSLATION_CATALOG[
            reduced[0]["statement"]
        ]["guidance"]
        != "changed"
    )


def test_show_policy_translation_support_returns_index_metadata():
    result = _policy_translation.show_policy_translation_support(
        "llm-token-limit"
    )

    assert result["supportLevel"] == "reduced"
    assert result["action"] == "import"
    assert result["destinationCapability"]["policyTypes"] == ["tokenLimit"]
    assert result["handler"] == {
        "kind": "translator",
        "name": "_translate_token_limit",
    }


def test_show_policy_translation_support_rejects_unknown_policy():
    with pytest.raises(ResourceNotFoundError, match="was not found"):
        _policy_translation.show_policy_translation_support("future-policy")


@pytest.mark.parametrize(
    ("statement", "action", "criticality"),
    [
        ("future-jwt-authentication", "block", "authentication"),
        ("custom-backend-selector", "block", "backend"),
        ("dynamic-route", "block", "routing"),
        ("future-payload-transform", "warn", "unknown"),
    ],
)
def test_unknown_policy_classification_is_deterministic(
    statement,
    action,
    criticality,
):
    first = _policy_translation.classify_policy_statement(statement)
    second = _policy_translation.classify_policy_statement(statement)

    assert first == second
    assert first["action"] == action
    assert first["criticality"] == criticality
    assert first["supportLevel"] == "unsupported"


def test_summary_classifies_known_and_unknown_unsupported_statements():
    result = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <validate-jwt header-name="Authorization" />
          <future-transform />
        </inbound></policies>
        """,
        "api",
    )

    assessments = {
        item["statement"]: item for item in result["statementAssessments"]
    }
    assert result["unsupportedStatements"] == [
        "future-transform",
        "validate-jwt",
    ]
    assert assessments["validate-jwt"]["action"] == "block"
    assert assessments["future-transform"]["action"] == "warn"


def test_policy_translation_table_uses_index_fields():
    result = _policy_translation.show_policy_translation_support(
        "set-backend-service"
    )

    assert _policy_translation.format_policy_translation_table(result) == [
        {
            "SourcePolicy": "set-backend-service",
            "Support": "reduced",
            "Action": "import",
            "Criticality": "backend",
            "Mode": "configuration",
            "Destination": "",
            "Sections": "inbound,backend",
            "Scopes": "service,workspace,product,api,operation",
            "Guidance": (
                "Verify the resolved destination endpoint and any backend pool "
                "behavior."
            ),
        }
    ]


def test_translate_effective_policies_returns_model_translation_and_reduced_warning():
    summary = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <llm-token-limit
            counter-key="@(context.Request.IpAddress)"
            tokens-per-minute="1200" />
        </inbound></policies>
        """,
        "/services/source/apis/chat",
        "api",
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "model",
        "llm",
    )

    assert result["destinationPolicies"] == [
        {
            "type": "tokenLimit",
            "period": "minute",
            "count": 1200,
            "counterKey": "IPAddress",
        }
    ]
    assert "api policy '/services/source/apis/chat', inbound section" in str(
        result["reducedMappingWarnings"]
    )
    assert result["unsupportedNoncriticalWarnings"] == []
    assert result["unsupportedCriticalBlockers"] == []


def test_translate_effective_policies_keeps_exact_import_without_warning(
    monkeypatch,
):
    capability = {
        "statement": "exact-test-policy",
        "docsUrl": "https://learn.microsoft.com/example",
        "validScopes": ["api"],
        "validSections": ["inbound"],
        "applicableAssets": ["model"],
        "applicableSubtypes": ["llm"],
        "destinationCapability": {
            "mode": "inlinePolicy",
            "policyTypes": ["test"],
        },
        "supportLevel": "exact",
        "action": "import",
        "criticality": "behavioral",
        "omittedBehavior": "Nothing is omitted.",
        "guidance": "No review is required.",
        "handler": {"kind": "translator", "name": "_test"},
    }
    monkeypatch.setitem(
        _policy_translation.POLICY_TRANSLATION_CATALOG,
        capability["statement"],
        capability,
    )
    summary = {
        "scope": "api",
        "scopeType": "api",
        "present": True,
        "statementOccurrences": [
            {"statement": "exact-test-policy", "section": "inbound"}
        ],
        "translatedPolicyRecords": [
            {
                "statement": "exact-test-policy",
                "section": "inbound",
                "policy": {"type": "test"},
            }
        ],
        "translationWarnings": [],
    }

    result = _policy_translation.translate_effective_policies(
        [summary],
        "model",
        "llm",
    )

    assert result == {
        "destinationPolicies": [{"type": "test"}],
        "reducedMappingWarnings": [],
        "unsupportedNoncriticalWarnings": [],
        "unsupportedCriticalBlockers": [],
    }


def test_translate_effective_policies_does_not_mark_configuration_handlers_unsupported():
    summary = _policy_translation.summarize_policy(
        """
        <policies>
          <inbound><set-backend-service backend-id="backend" /></inbound>
          <backend><forward-request /></backend>
        </policies>
        """,
        "api",
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "mcpServer",
        "sse",
    )

    assert result["destinationPolicies"] == []
    assert "set-backend-service has a reduced destination mapping" in str(
        result["reducedMappingWarnings"]
    )
    assert "forward-request has a reduced destination mapping" in str(
        result["reducedMappingWarnings"]
    )
    assert result["unsupportedNoncriticalWarnings"] == []
    assert result["unsupportedCriticalBlockers"] == []


def test_translate_effective_policies_separates_mcp_warnings_and_blockers():
    summary = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <set-header name="x-test" exists-action="override">
            <value>test</value>
          </set-header>
          <validate-jwt header-name="Authorization" />
        </inbound></policies>
        """,
        "mcp-api",
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "mcpServer",
        "sse",
    )

    assert "set-header is unsupported" in str(
        result["unsupportedNoncriticalWarnings"]
    )
    assert "validate-jwt is unsupported and blocks import" in str(
        result["unsupportedCriticalBlockers"]
    )


def test_translate_effective_policies_checks_asset_subtype_and_section():
    subtype_summary = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <llm-content-safety>
            <categories><category name="Hate" threshold="2" /></categories>
          </llm-content-safety>
        </inbound></policies>
        """,
        "embedding-api",
    )
    section_summary = _policy_translation.summarize_policy(
        """
        <policies><outbound>
          <llm-token-limit
            counter-key="@(context.Request.IpAddress)"
            tokens-per-minute="100" />
        </outbound></policies>
        """,
        "chat-api",
    )

    subtype_result = _policy_translation.translate_effective_policies(
        [subtype_summary],
        "model",
        "embedding",
    )
    section_result = _policy_translation.translate_effective_policies(
        [section_summary],
        "model",
        "llm",
    )

    assert subtype_result["destinationPolicies"] == []
    assert "does not apply to destination asset type 'model'" in str(
        subtype_result["unsupportedNoncriticalWarnings"]
    )
    assert section_result["destinationPolicies"] == []
    assert "not valid in the APIM 'outbound' section" in str(
        section_result["unsupportedNoncriticalWarnings"]
    )


def test_block_action_that_does_not_apply_to_asset_is_only_inventoried():
    summary = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <validate-graphql-request />
        </inbound></policies>
        """,
        "service",
        "service",
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "model",
        "llm",
    )

    assert result["unsupportedCriticalBlockers"] == []
    assert "does not apply to destination asset type 'model'" in str(
        result["unsupportedNoncriticalWarnings"]
    )


@pytest.mark.parametrize("scope_type", ["service", "workspace"])
def test_translate_effective_policies_warns_when_shared_scope_is_replicated(
    scope_type,
):
    summary = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <llm-token-limit
            counter-key="@(context.Request.IpAddress)"
            tokens-per-minute="100" />
        </inbound></policies>
        """,
        f"{scope_type}-scope",
        scope_type,
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "model",
        "llm",
    )

    assert result["destinationPolicies"]
    assert (
        f"{scope_type} policy '{scope_type}-scope': translated policies must "
        "be replicated"
    ) in str(result["reducedMappingWarnings"])


@pytest.mark.parametrize("scope_type", ["product", "operation"])
def test_translate_effective_policies_does_not_flatten_unpreserved_scopes(
    scope_type,
):
    summary = _policy_translation.summarize_policy(
        """
        <policies><inbound>
          <llm-token-limit
            counter-key="@(context.Request.IpAddress)"
            tokens-per-minute="100" />
        </inbound></policies>
        """,
        f"{scope_type}-scope",
        scope_type,
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "model",
        "llm",
    )

    assert result["destinationPolicies"] == []
    assert (
        f"{scope_type} policy '{scope_type}-scope': this scope cannot be "
        "preserved"
    ) in str(result["reducedMappingWarnings"])


@pytest.mark.parametrize(
    ("statement", "result_key"),
    [
        ("future-payload-transform", "unsupportedNoncriticalWarnings"),
        ("future-authentication-filter", "unsupportedCriticalBlockers"),
        ("future-backend-router", "unsupportedCriticalBlockers"),
        ("future-route-selector", "unsupportedCriticalBlockers"),
    ],
)
def test_translate_effective_policies_classifies_unknown_statements(
    statement,
    result_key,
):
    summary = _policy_translation.summarize_policy(
        f"""
        <policies><inbound>
          <{statement} />
        </inbound></policies>
        """,
        "unknown-api",
    )

    result = _policy_translation.translate_effective_policies(
        [summary],
        "mcpServer",
        "sse",
    )

    assert statement in str(result[result_key])
