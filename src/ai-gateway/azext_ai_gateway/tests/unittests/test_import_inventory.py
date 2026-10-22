# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from unittest.mock import patch

from azext_ai_gateway import _import_inventory


SOURCE_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.ApiManagement/service/source"
)


def test_v2_sku_capability_matrix_covers_all_v2_tiers():
    assert set(_import_inventory.V2_SKU_CAPABILITIES) == {
        "basicv2",
        "standardv2",
        "premiumv2",
    }
    assert all(
        capabilities["workspaces"]
        and capabilities["serviceLevelMcp"]
        and not capabilities["workspaceMcp"]
        and not capabilities["multiRegion"]
        for capabilities in _import_inventory.V2_SKU_CAPABILITIES.values()
    )
    assert not _import_inventory.V2_SKU_CAPABILITIES["basicv2"][
        "outboundVnetIntegration"
    ]
    assert _import_inventory.V2_SKU_CAPABILITIES["standardv2"][
        "outboundVnetIntegration"
    ]
    assert _import_inventory.V2_SKU_CAPABILITIES["premiumv2"][
        "availabilityZones"
    ]


def _policy(scope):
    return {
        "scope": scope,
        "scopeType": "api",
        "present": True,
        "statements": ["set-header"],
        "statementOccurrences": [
            {
                "statement": "set-header",
                "section": "inbound",
                "conditional": False,
            }
        ],
        "statementAssessments": [
            {
                "statement": "set-header",
                "supportLevel": "unsupported",
            }
        ],
        "translatedPolicies": [{"type": "must-not-be-returned"}],
        "translatedPolicyRecords": [{"secret": "must-not-be-returned"}],
        "translationWarnings": ["deterministic mapping output"],
    }


def _record(name="chat", workspace=None):
    api_id = (
        f"{SOURCE_ID}/workspaces/{workspace}/apis/{name}"
        if workspace
        else f"{SOURCE_ID}/apis/{name}"
    )
    return {
        "api": {
            "id": api_id,
            "properties": {
                "apiRevision": "2",
                "apiVersion": "v1",
                "mcpProperties": {
                    "endpoint": "https://example.test/mcp?key=secret"
                },
            },
        },
        "source": {
            "id": api_id,
            "name": name,
            "workspace": workspace,
            "displayName": name.title(),
            "apiType": "http",
            "properties": {
                "serviceUrl": "https://example.test?api-key=<redacted>"
            },
        },
        "policy": _policy(api_id),
        "inheritedPolicies": [],
        "operationPolicies": [],
        "productPolicies": [],
        "backends": [
            {
                "id": f"{SOURCE_ID}/backends/model",
                "name": "model",
                "properties": {
                    "url": "https://backend.test?api-key=secret",
                    "credentials": {"header": {"api-key": ["secret"]}},
                },
            }
        ],
        "operations": [],
        "products": [],
        "subscriptions": [],
        "tools": [],
        "diagnostics": [],
        "loggers": [],
    }


@patch("azext_ai_gateway._import_inventory._optional_list")
@patch("azext_ai_gateway._import_inventory._discover_source")
def test_inventory_is_versioned_complete_and_does_not_resolve_secrets(
    discover_source,
    optional_list,
):
    discover_source.return_value = {
        "source": {
            "id": SOURCE_ID,
            "name": "source",
            "sku": "StandardV2",
        },
        "assets": [_record("workspace-api", "team"), _record()],
        "errors": [],
    }
    optional_list.return_value = []

    result = _import_inventory.import_inventory(None, SOURCE_ID)

    discover_source.assert_called_once_with(
        None,
        SOURCE_ID,
        suppress_mcp_backing_apis=False,
        resolve_subscription_credentials=False,
        require_supported_sku=False,
    )
    assert result["schemaVersion"] == "3.0"
    assert result["kind"] == "AiGatewayApimImportInventory"
    assert result["source"]["migrationCompatibility"] == {
        "skuFamily": "v2",
        "supportedV2Sku": True,
        "inventoryApiVersion": "2024-05-01",
        "mcpApiVersion": "2025-09-01-preview",
        "capabilities": _import_inventory.V2_SKU_CAPABILITIES["standardv2"],
    }
    assert result["summary"] == {
        "apiCount": 2,
        "workspaceCount": 1,
        "discoveryComplete": True,
        "requiredDiscoveryComplete": True,
        "discoveryErrorCount": 0,
        "inventoryStatus": "complete",
        "behaviorCount": 5,
        "provenanceConflictCount": 0,
        "fallbackSourceCount": 0,
        "liveArmDiscoveryComplete": True,
        "liveArmRequiredDiscoveryComplete": True,
    }
    assert [api["id"] for api in result["apis"]] == [
        f"{SOURCE_ID}/apis/chat",
        f"{SOURCE_ID}/workspaces/team/apis/workspace-api",
    ]
    assert result["scopes"] == [
        {
            "id": SOURCE_ID,
            "name": None,
            "scopeType": "service",
            "apiIds": [f"{SOURCE_ID}/apis/chat"],
            "policy": None,
            "backends": [],
            "diagnostics": [],
            "loggers": [],
            "relatedResources": {
                "namedValues": [],
                "policyFragments": [],
                "products": [],
                "subscriptions": [],
            },
            "provenance": [
                {
                    "sourceType": "arm",
                    "authority": "live",
                    "resourceId": SOURCE_ID,
                }
            ],
            "provenanceAuthority": "arm",
        },
        {
            "id": f"{SOURCE_ID}/workspaces/team",
            "name": "team",
            "scopeType": "workspace",
            "apiIds": [
                f"{SOURCE_ID}/workspaces/team/apis/workspace-api"
            ],
            "policy": None,
            "backends": [],
            "diagnostics": [],
            "loggers": [],
            "relatedResources": {
                "namedValues": [],
                "policyFragments": [],
                "products": [],
                "subscriptions": [],
            },
            "provenance": [
                {
                    "sourceType": "arm",
                    "authority": "live",
                    "resourceId": SOURCE_ID,
                }
            ],
            "provenanceAuthority": "arm",
        },
    ]


@patch("azext_ai_gateway._import_inventory._optional_list")
@patch("azext_ai_gateway._import_inventory._discover_source")
def test_inventory_returns_facts_not_deterministic_policy_translations(
    discover_source,
    optional_list,
):
    record = _record()
    record["operations"] = [
        {
            "id": f"{SOURCE_ID}/apis/chat/operations/invoke",
            "name": "invoke",
            "policy": _policy(
                f"{SOURCE_ID}/apis/chat/operations/invoke"
            ),
        }
    ]
    record["products"] = [
        {
            "id": f"{SOURCE_ID}/products/starter",
            "name": "starter",
            "policy": _policy(f"{SOURCE_ID}/products/starter"),
        }
    ]
    discover_source.return_value = {
        "source": {"id": SOURCE_ID, "name": "source"},
        "assets": [record],
        "errors": [],
    }
    optional_list.return_value = []

    result = _import_inventory.import_inventory(None, SOURCE_ID)
    policy = result["apis"][0]["policies"]["api"]

    assert policy["statements"] == ["set-header"]
    assert policy["statementAssessments"][0]["supportLevel"] == "unsupported"
    assert "translatedPolicies" not in policy
    assert "translatedPolicyRecords" not in policy
    assert "translationWarnings" not in policy
    assert "translatedPolicies" not in result["apis"][0]["operations"][0]["policy"]
    assert "translatedPolicies" not in result["apis"][0]["products"][0]["policy"]


@patch("azext_ai_gateway._import_inventory._optional_list")
@patch("azext_ai_gateway._import_inventory._discover_source")
def test_inventory_redacts_credentials_urls_and_named_values(
    discover_source,
    optional_list,
):
    discover_source.return_value = {
        "source": {"id": SOURCE_ID, "name": "source"},
        "assets": [_record()],
        "errors": [],
    }

    def related_resources(_cmd, url, *_args, **_kwargs):
        if url.endswith("/namedValues"):
            return [
                {
                    "id": f"{SOURCE_ID}/namedValues/provider-key",
                    "name": "provider-key",
                    "properties": {
                        "displayName": "Provider key",
                        "secret": True,
                        "value": "raw-secret",
                    },
                }
            ]
        return []

    optional_list.side_effect = related_resources

    result = _import_inventory.import_inventory(None, SOURCE_ID)

    assert "raw-secret" not in str(result)
    assert "api-key=secret" not in str(result)
    assert result["relatedResources"]["namedValues"][0]["value"] == "<redacted>"
    backend = result["apis"][0]["backends"][0]
    assert backend["credentials"]["headerNames"] == ["api-key"]
    assert "secret" not in str(backend["credentials"])


@patch("azext_ai_gateway._import_inventory._optional_list")
@patch("azext_ai_gateway._import_inventory._discover_source")
def test_inventory_preserves_partial_discovery_errors(
    discover_source,
    optional_list,
):
    discover_source.return_value = {
        "source": {"id": SOURCE_ID, "name": "source"},
        "assets": [],
        "errors": [
            {
                "scope": f"{SOURCE_ID}/apis",
                "configurationDomain": "apis",
                "required": True,
                "message": "forbidden",
            }
        ],
    }
    optional_list.return_value = []

    result = _import_inventory.import_inventory(None, SOURCE_ID)

    assert result["summary"]["discoveryComplete"] is False
    assert result["summary"]["discoveryErrorCount"] == 1
    assert result["discoveryErrors"][0]["message"] == "forbidden"


@patch("azext_ai_gateway._import_inventory._optional_list")
@patch("azext_ai_gateway._import_inventory._discover_source")
def test_inventory_exposes_coverage_and_collapses_platform_health_incident(
    discover_source,
    optional_list,
):
    error = {
        "scope": f"{SOURCE_ID}/apis",
        "configurationDomain": "apis",
        "required": True,
        "statusCode": 400,
        "code": "InvalidOperation",
        "message": "Scale unit family mismatch requires family SkuV2.",
        "category": "platformHealth",
        "retryable": False,
        "remediation": "Check APIM Resource Health.",
        "requestId": "request-1",
        "correlationRequestId": "correlation-1",
    }
    discover_source.return_value = {
        "source": {"id": SOURCE_ID, "name": "source", "sku": "BasicV2"},
        "assets": [],
        "errors": [error, {**error, "configurationDomain": "backends"}],
        "collectionCoverage": [
            {
                "scope": f"{SOURCE_ID}/apis",
                "configurationDomain": "apis",
                "status": "failed",
                "apiVersion": "2024-05-01",
                "observedCount": 0,
                "pagesCompleted": 0,
                "requiredForEnumeration": True,
                "error": error,
            }
        ],
    }
    optional_list.return_value = []

    result = _import_inventory.import_inventory(None, SOURCE_ID)

    assert result["summary"]["inventoryStatus"] == "partial"
    assert result["summary"]["discoveryComplete"] is False
    assert result["collectionCoverage"][0]["status"] == "failed"
    assert result["healthIncidents"] == [
        {
            "category": "platformHealth",
            "code": "InvalidOperation",
            "message": "Scale unit family mismatch requires family SkuV2.",
            "retryable": False,
            "remediation": "Check APIM Resource Health.",
            "affectedDomains": ["apis", "backends"],
            "requestIds": ["request-1"],
            "correlationRequestIds": ["correlation-1"],
        }
    ]


def test_inventory_table_surfaces_sku_schema_and_partial_status():
    assert _import_inventory.format_import_inventory_table(
        {
            "schemaVersion": "3.0",
            "source": {"name": "source", "sku": "BasicV2"},
            "summary": {
                "inventoryStatus": "partial",
                "apiCount": 1,
                "workspaceCount": 0,
                "discoveryComplete": False,
                "discoveryErrorCount": 2,
            },
        }
    ) == [
        {
            "Source": "source",
            "SKU": "BasicV2",
            "Schema": "3.0",
            "Status": "partial",
            "APIs": 1,
            "Workspaces": 0,
            "Complete": False,
            "Errors": 2,
        }
    ]
