# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_ai_gateway._inventory_exports import (
    _semantic_resource,
    apply_export_fallbacks,
)


SOURCE_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.ApiManagement/service/source"
)


def _inventory(status="failed", apis=None):
    return {
        "source": {"id": SOURCE_ID, "name": "source", "sku": "BasicV2"},
        "summary": {"apiCount": len(apis or []), "workspaceCount": 0},
        "apis": apis or [],
        "scopes": [
            {
                "id": SOURCE_ID,
                "name": None,
                "scopeType": "service",
                "apiIds": [api["id"] for api in apis or []],
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
            }
        ],
        "relatedResources": {
            "certificates": [],
            "groups": [],
            "identityProviders": [],
            "authorizationProviders": [],
        },
        "collectionCoverage": [
            {
                "scope": f"{SOURCE_ID}/apis",
                "configurationDomain": "apis",
                "status": status,
            },
            {
                "scope": f"{SOURCE_ID}/policies/policy",
                "configurationDomain": "policies",
                "status": status,
            },
        ],
    }


def _live_api(path="live"):
    api_id = f"{SOURCE_ID}/apis/chat"
    return {
        "id": api_id,
        "stableId": api_id,
        "scope": {"type": "service", "workspace": None},
        "api": {
            "id": api_id,
            "name": "chat",
            "apiType": "http",
            "path": path,
            "serviceUrl": "https://live.example.test",
            "protocols": ["https"],
            "subscriptionRequired": False,
        },
        "revision": {},
        "mcpProperties": {},
        "backends": [],
        "policies": {
            "api": None,
            "inherited": [],
            "operations": [],
            "products": [],
        },
        "operations": [],
        "schemas": [],
        "releases": [],
        "products": [],
        "subscriptions": [],
        "tools": [],
        "mcpDependencies": [],
        "diagnostics": [],
        "loggerReferences": [],
    }
def _write_metadata(root, complete_domains, source_id=SOURCE_ID):
    _write_json(
        root / "inventory-metadata.json",
        {
            "kind": "AiGatewayApimExportEvidence",
            "schemaVersion": "1.0",
            "sourceResourceId": source_id,
            "sourceSku": "BasicV2",
            "exportedAt": "2026-08-28T20:00:00Z",
            "sourceEtag": "export-etag",
            "completeDomains": [
                {
                    "scope": "service",
                    "configurationDomain": domain,
                }
                for domain in complete_domains
            ],
        },
    )



def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_apiops_fills_failed_arm_before_template_and_builds_ledger(tmp_path):
    apiops = tmp_path / "apiops"
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {
            "properties": {
                "displayName": "Chat",
                "type": "http",
                "path": "apiops",
                "serviceUrl": "https://api.example.test?api-key=raw-url-key",
                "protocols": ["https"],
                "mcpProperties": {
                    "headers": {"api-key": "raw-header-key"}
                },
            }
        },
    )
    _write_json(
        apiops
        / "apis"
        / "chat"
        / "operations"
        / "invoke"
        / "information.json",
        {
            "properties": {
                "displayName": "Invoke",
                "method": "POST",
                "urlTemplate": "/invoke?sig=raw-operation-key",
            }
        },
    )
    _write_json(
        apiops / "named values" / "provider-key" / "information.json",
        {
            "properties": {
                "displayName": "Provider key",
                "secret": True,
                "value": "raw-named-value",
            }
        },
    )
    policy_path = apiops / "apis" / "chat" / "policy.xml"
    policy_path.write_text(
        "<policies><inbound><set-header name='x'><value>raw-policy-value"
        "</value></set-header></inbound></policies>",
        encoding="utf-8",
    )
    template = tmp_path / "template.json"
    _write_json(
        template,
        {
            "resources": [
                {
                    "type": "Microsoft.ApiManagement/service/apis",
                    "name": "source/chat",
                    "properties": {
                        "displayName": "Template Chat",
                        "type": "http",
                        "path": "template",
                    },
                },
                {
                    "type": "Microsoft.ApiManagement/service/apis",
                    "name": "source/template-only",
                    "properties": {
                        "displayName": "Template only",
                        "type": "http",
                        "path": "template-only",
                    },
                },
            ]
        },
    )

    result = apply_export_fallbacks(
        _inventory(),
        SOURCE_ID,
        apiops_artifact=str(apiops),
        arm_template_file=str(template),
        approve_export_evidence=True,
    )

    assert [api["api"]["path"] for api in result["apis"]] == [
        "apiops",
        "template-only",
    ]
    chat = result["apis"][0]
    assert chat["provenanceAuthority"] == "apiops"
    assert [item["sourceType"] for item in chat["provenance"]] == [
        "apiops",
        "apiops",
        "armTemplate",
    ]
    assert chat["operations"][0]["method"] == "POST"
    assert chat["policies"]["api"]["statements"] == ["set-header"]
    assert result["provenance"]["authorityOrder"] == [
        "completeLiveArm",
        "apiops",
        "armTemplate",
        "partialLiveArm",
    ]
    assert result["provenance"]["conflicts"] == [
        {
            "stableId": f"{SOURCE_ID}/apis/chat",
            "field": "api",
            "selectedSource": "apiops",
            "otherSource": "armTemplate",
        }
    ]
    assert result["summary"]["apiCount"] == 2
    assert result["summary"]["fallbackSourceCount"] == 2
    assert result["summary"]["behaviorCount"] == 5
    assert result["summary"]["provenanceConflictCount"] == 1
    assert {item["behaviorType"] for item in result["sourceBehaviorLedger"]} >= {
        "apiConfiguration",
        "operation",
        "policyStatement",
        "namedValues",
    }
    serialized = json.dumps(result, sort_keys=True)
    for secret in (
        "raw-url-key",
        "raw-header-key",
        "raw-operation-key",
        "raw-named-value",
        "raw-policy-value",
    ):
        assert secret not in serialized

    assert result == apply_export_fallbacks(
        _inventory(),
        SOURCE_ID,
        apiops_artifact=str(apiops),
        arm_template_file=str(template),
        approve_export_evidence=True,
    )


def test_complete_live_arm_wins_and_records_apiops_conflict(tmp_path):
    apiops = tmp_path / "apiops"
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {"properties": {"type": "http", "path": "apiops"}},
    )

    result = apply_export_fallbacks(
        _inventory(status="complete", apis=[_live_api()]),
        SOURCE_ID,
        apiops_artifact=str(apiops),
        approve_export_evidence=True,
    )

    assert result["apis"][0]["api"]["path"] == "live"
    assert result["apis"][0]["provenanceAuthority"] == "arm"
    assert result["provenance"]["conflicts"][0]["selectedSource"] == "arm"


def test_workspace_failure_does_not_override_complete_service_api(tmp_path):
    apiops = tmp_path / "apiops"
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {"properties": {"type": "http", "path": "apiops"}},
    )
    inventory = _inventory(status="complete", apis=[_live_api()])
    inventory["collectionCoverage"].append(
        {
            "scope": f"{SOURCE_ID}/workspaces/team/apis",
            "configurationDomain": "apis",
            "status": "failed",
        }
    )

    result = apply_export_fallbacks(
        inventory,
        SOURCE_ID,
        apiops_artifact=str(apiops),
        approve_export_evidence=True,
    )

    assert result["apis"][0]["api"]["path"] == "live"
    assert result["apis"][0]["provenanceAuthority"] == "arm"
    assert result["provenance"]["conflicts"][0]["selectedSource"] == "arm"


def test_equivalent_live_and_export_shapes_do_not_conflict(tmp_path):
    apiops = tmp_path / "apiops"
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {
            "properties": {
                "type": "http",
                "path": "live",
                "serviceUrl": "https://live.example.test",
                "protocols": ["https"],
                "subscriptionRequired": False,
            }
        },
    )
    _write_json(
        apiops / "named values" / "label" / "information.json",
        {
            "properties": {
                "displayName": "Label",
                "secret": False,
                "tags": ["migration"],
                "value": "safe",
            }
        },
    )
    inventory = _inventory(status="complete", apis=[_live_api()])
    named_value = {
        "id": f"{SOURCE_ID}/namedValues/label",
        "name": "label",
        "type": "Microsoft.ApiManagement/service/namedValues",
        "displayName": "Label",
        "secret": False,
        "tags": ["migration"],
        "value": "<redacted>",
    }
    inventory["scopes"][0]["relatedResources"]["namedValues"] = [named_value]
    inventory["relatedResources"]["namedValues"] = [named_value]

    result = apply_export_fallbacks(
        inventory,
        SOURCE_ID,
        apiops_artifact=str(apiops),
        approve_export_evidence=True,
    )

    assert result["provenance"]["conflicts"] == []
    assert result["summary"]["inventoryStatus"] == "complete"


@pytest.mark.parametrize(
    "family,live,exported",
    [
        (
            "operations",
            {
                "displayName": "Invoke",
                "method": "POST",
                "urlTemplate": "/invoke?sig=secret#fragment",
                "policy": {"present": False},
                "properties": {
                    "displayName": "Invoke",
                    "method": "POST",
                    "urlTemplate": "/invoke?sig=secret#fragment",
                    "x-live-only": "ignored",
                },
            },
            {
                "displayName": "Invoke",
                "method": "POST",
                "urlTemplate": "/invoke?sig=<redacted>#<redacted>",
                "policy": None,
                "properties": {
                    "displayName": "Invoke",
                    "method": "POST",
                    "urlTemplate": "/invoke?sig=<redacted>#<redacted>",
                },
            },
        ),
        (
            "diagnostics",
            {
                "loggerId": "logger",
                "properties": {
                    "loggerId": "logger",
                    "alwaysLog": "allErrors",
                    "verbosity": "information",
                },
            },
            {
                "properties": {
                    "loggerId": "logger",
                    "alwaysLog": "allErrors",
                },
            },
        ),
        (
            "loggers",
            {
                "loggerType": "applicationInsights",
                "properties": {
                    "loggerType": "applicationInsights",
                    "isBuffered": True,
                    "description": "live-only shape",
                },
            },
            {
                "properties": {
                    "loggerType": "applicationInsights",
                    "isBuffered": True,
                },
            },
        ),
        (
            "products",
            {
                "displayName": "Starter",
                "properties": {
                    "displayName": "Starter",
                    "subscriptionRequired": True,
                    "approvalRequired": False,
                    "state": "published",
                },
            },
            {
                "properties": {
                    "displayName": "Starter",
                    "subscriptionRequired": True,
                    "approvalRequired": False,
                    "state": "published",
                },
            },
        ),
    ],
)
def test_semantic_resource_comparison_ignores_projection_shape(
    family,
    live,
    exported,
):
    assert _semantic_resource(live, family) == _semantic_resource(
        exported,
        family,
    )


def test_template_skips_unresolved_arm_expressions(tmp_path):
    template = tmp_path / "template.json"
    _write_json(
        template,
        {
            "resources": [
                {
                    "type": "Microsoft.ApiManagement/service/apis",
                    "name": "[format('{0}/{1}', parameters('service'), 'chat')]",
                    "properties": {"path": "must-not-appear"},
                }
            ]
        },
    )

    result = apply_export_fallbacks(
        _inventory(), SOURCE_ID, arm_template_file=str(template),
        approve_export_evidence=True,
    )

    assert result["apis"] == []
    assert result["provenance"]["warnings"] == [
        {
            "sourceType": "armTemplate",
            "path": "template.json",
            "code": "UnresolvedArmExpression",
            "resourceIndex": 0,
        }
    ]


def test_template_omits_unresolved_property_expressions(tmp_path):
    template = tmp_path / "template.json"
    _write_json(
        template,
        {
            "resources": [
                {
                    "type": "Microsoft.ApiManagement/service/apis",
                    "name": "source/chat",
                    "properties": {
                        "displayName": "Chat",
                        "path": "[parameters('apiPath')]",
                        "serviceUrl": "[concat('https://', parameters('host'))]",
                        "type": "http",
                    },
                }
            ]
        },
    )

    result = apply_export_fallbacks(
        _inventory(),
        SOURCE_ID,
        arm_template_file=str(template),
        approve_export_evidence=True,
    )

    assert result["apis"][0]["api"]["path"] is None
    assert result["apis"][0]["api"]["serviceUrl"] is None
    assert {
        warning["propertyPath"]
        for warning in result["provenance"]["warnings"]
    } == {"properties.path", "properties.serviceUrl"}


def test_apiops_rejects_mismatched_service_etag(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(apiops, ["apis"])
    inventory = _inventory()
    inventory["source"]["etag"] = "live-etag"

    with pytest.raises(InvalidArgumentValueError, match="sourceEtag"):
        apply_export_fallbacks(
            inventory,
            SOURCE_ID,
            apiops_artifact=str(apiops),
            approve_export_evidence=True,
        )


def test_apiops_completeness_claim_recovers_only_eligible_domain(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(apiops, ["apis"])
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {"properties": {"type": "http", "path": "chat"}},
    )
    inventory = _inventory()
    inventory["summary"].update(
        {"discoveryComplete": False, "requiredDiscoveryComplete": False}
    )
    inventory["discoveryErrors"] = [
        {
            "scope": f"{SOURCE_ID}/apis",
            "configurationDomain": "apis",
            "required": True,
        },
        {
            "scope": f"{SOURCE_ID}/policies/policy",
            "configurationDomain": "policies",
            "required": True,
        },
    ]

    result = apply_export_fallbacks(
        inventory,
        SOURCE_ID,
        apiops_artifact=str(apiops),
        approve_export_evidence=True,
    )

    coverage = {
        item["configurationDomain"]: item
        for item in result["collectionCoverage"]
    }
    assert coverage["apis"]["status"] == "complete"
    assert coverage["apis"]["originalStatus"] == "failed"
    assert coverage["apis"]["recoveredBy"] == "apiops"
    assert coverage["policies"]["status"] == "failed"
    authority = {
        item["configurationDomain"]: item
        for item in result["domainAuthority"]
    }
    assert authority["apis"]["evidenceRole"] == "authoritative"
    assert authority["apis"]["establishesCompleteness"] is True
    assert authority["policies"]["evidenceRole"] == "blocked"
    assert result["summary"]["discoveryComplete"] is False
    assert result["summary"]["requiredDiscoveryComplete"] is False
    assert result["discoveryErrors"][0]["effectiveStatus"] == "recovered"
    assert "effectiveStatus" not in result["discoveryErrors"][1]
    apiops_input = result["provenance"]["inputs"][1]
    assert apiops_input["sourceResourceId"] == SOURCE_ID
    assert apiops_input["exportedAt"] == "2026-08-28T20:00:00Z"


def test_apiops_claims_can_recover_all_failed_domains(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(apiops, ["apis", "policies"])
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {"properties": {"type": "http", "path": "chat"}},
    )
    policy = apiops / "apis" / "chat" / "policy.xml"
    policy.write_text(
        "<policies><inbound><base /></inbound></policies>",
        encoding="utf-8",
    )
    inventory = _inventory()
    inventory["summary"].update(
        {"discoveryComplete": False, "requiredDiscoveryComplete": False}
    )
    inventory["discoveryErrors"] = [
        {
            "scope": f"{SOURCE_ID}/{domain}",
            "configurationDomain": domain,
            "required": True,
        }
        for domain in ("apis", "policies")
    ]

    result = apply_export_fallbacks(
        inventory,
        SOURCE_ID,
        apiops_artifact=str(apiops),
        approve_export_evidence=True,
    )

    assert result["summary"]["liveArmDiscoveryComplete"] is False
    assert result["summary"]["discoveryComplete"] is True
    assert result["summary"]["requiredDiscoveryComplete"] is True
    assert result["summary"]["inventoryStatus"] == "complete"


def test_conflict_blocks_claimed_domain_recovery(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(apiops, ["apis"])
    _write_json(
        apiops / "apis" / "chat" / "information.json",
        {"properties": {"type": "http", "path": "apiops"}},
    )
    inventory = _inventory(apis=[_live_api()])
    inventory["discoveryErrors"] = [
        {
            "scope": f"{SOURCE_ID}/apis",
            "configurationDomain": "apis",
            "required": True,
        }
    ]

    result = apply_export_fallbacks(
        inventory,
        SOURCE_ID,
        apiops_artifact=str(apiops),
        approve_export_evidence=True,
    )

    assert result["provenance"]["conflicts"]
    assert result["collectionCoverage"][0]["status"] == "failed"
    assert result["domainAuthority"][0]["evidenceRole"] == "blocked"
    assert result["summary"]["discoveryComplete"] is False
    assert result["summary"]["inventoryStatus"] == "partial"


def test_arm_template_never_establishes_absence(tmp_path):
    template = tmp_path / "template.json"
    _write_json(
        template,
        {
            "metadata": {
                "aiGatewayMigration": {
                    "sourceResourceId": SOURCE_ID,
                    "exportedAt": "2026-08-28T20:00:00Z",
                    "completeDomains": [
                        {"scope": "service", "configurationDomain": "apis"}
                    ],
                }
            },
            "resources": [],
        },
    )

    result = apply_export_fallbacks(
        _inventory(),
        SOURCE_ID,
        arm_template_file=str(template),
        approve_export_evidence=True,
    )

    assert result["collectionCoverage"][0]["status"] == "failed"
    assert result["domainAuthority"][0]["establishesCompleteness"] is False
    assert result["summary"]["discoveryComplete"] is False


def test_export_evidence_requires_explicit_approval(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(apiops, ["apis"])

    with pytest.raises(
        InvalidArgumentValueError,
        match="--approve-export-evidence",
    ):
        apply_export_fallbacks(
            _inventory(), SOURCE_ID, apiops_artifact=str(apiops)
        )


def test_export_source_identity_mismatch_is_rejected(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(
        apiops,
        ["apis"],
        source_id=f"{SOURCE_ID}-other",
    )

    with pytest.raises(InvalidArgumentValueError, match="sourceResourceId"):
        apply_export_fallbacks(
            _inventory(),
            SOURCE_ID,
            apiops_artifact=str(apiops),
            approve_export_evidence=True,
        )


def test_apiops_tree_rejects_any_symbolic_link(tmp_path):
    apiops = tmp_path / "apiops"
    _write_metadata(apiops, ["apis"])
    target = tmp_path / "outside.json"
    _write_json(target, {"properties": {"path": "outside"}})
    (apiops / "linked.json").symlink_to(target)

    with pytest.raises(InvalidArgumentValueError, match="symbolic link"):
        apply_export_fallbacks(
            _inventory(),
            SOURCE_ID,
            apiops_artifact=str(apiops),
            approve_export_evidence=True,
        )
