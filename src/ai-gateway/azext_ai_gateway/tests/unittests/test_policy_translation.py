# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import ResourceNotFoundError

from azext_ai_gateway import _policy_translation


def test_every_catalog_entry_has_one_registered_translator():
    assert set(_policy_translation.POLICY_TRANSLATION_CATALOG) == set(
        _policy_translation.POLICY_TRANSLATORS
    )


def test_catalog_entries_expose_required_capability_metadata():
    required_fields = {
        "sourcePolicy",
        "supportLevel",
        "translationMode",
        "destinationPolicyTypes",
        "supportedSourceFields",
        "unsupportedSourceFields",
        "supportedSections",
        "scopes",
        "notes",
    }

    for source_policy, capability in (
        _policy_translation.POLICY_TRANSLATION_CATALOG.items()
    ):
        assert set(capability) == required_fields
        assert capability["sourcePolicy"] == source_policy
        assert capability["supportLevel"] in {
            "consumed",
            "partial",
            "unsupported",
        }
        assert capability["scopes"] == {
            "imported": ["service", "workspace", "api"],
            "inventoryOnly": ["product", "operation"],
        }


def test_list_policy_translation_support_filters_and_returns_copies():
    unsupported = _policy_translation.list_policy_translation_support(
        "unsupported"
    )

    assert [item["sourcePolicy"] for item in unsupported] == [
        "authentication-managed-identity",
        "rewrite-uri",
        "set-query-parameter",
    ]
    unsupported[0]["notes"] = "changed"
    assert (
        _policy_translation.POLICY_TRANSLATION_CATALOG[
            "authentication-managed-identity"
        ]["notes"]
        != "changed"
    )


def test_show_policy_translation_support_returns_detail():
    result = _policy_translation.show_policy_translation_support(
        "llm-token-limit"
    )

    assert result["supportLevel"] == "partial"
    assert result["destinationPolicyTypes"] == ["tokenLimit"]
    assert "tokens-per-minute" in result["supportedSourceFields"]


def test_show_policy_translation_support_rejects_unknown_policy():
    with pytest.raises(ResourceNotFoundError, match="was not found"):
        _policy_translation.show_policy_translation_support("validate-jwt")


def test_policy_translation_table_is_stable_and_compact():
    result = _policy_translation.show_policy_translation_support(
        "set-backend-service"
    )

    assert _policy_translation.format_policy_translation_table(result) == [
        {
            "SourcePolicy": "set-backend-service",
            "Support": "consumed",
            "Mode": "configuration",
            "Destination": "",
            "Sections": "inbound,backend",
            "ImportedScopes": "service,workspace,api",
            "Notes": (
                "backend-id is consumed while resolving the source APIM backend."
            ),
        }
    ]
