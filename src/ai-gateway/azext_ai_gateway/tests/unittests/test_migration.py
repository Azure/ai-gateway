# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import io
import json

import pytest

from azext_ai_gateway import _migration, commands
from azext_ai_gateway._migration_validation import validate_migration_state


class _CommandGroup:

    def __init__(self, name, registrations):
        self._name = name
        self._registrations = registrations

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def custom_command(self, name, function, **_):
        self._registrations.add((self._name, name, function))

    def custom_show_command(self, name, function, **_):
        self._registrations.add((self._name, name, function))


class _CommandLoader:

    def __init__(self):
        self.registrations = set()

    def command_group(self, name):
        return _CommandGroup(name, self.registrations)


def _stream(value):
    return io.StringIO(json.dumps(value))


def _documents():
    contract = _migration.show_migration_capability()
    capability_digest = contract["contractDigest"]
    source_inventory = {
        "schemaVersion": "3.0",
        "kind": "AiGatewayApimImportInventory",
        "source": {
            "id": (
                "/subscriptions/sub/resourceGroups/rg/providers/"
                "Microsoft.ApiManagement/service/source"
            ),
            "sku": "BasicV2",
            "provisioningState": "Succeeded",
            "migrationCompatibility": {
                "skuFamily": "v2",
                "supportedV2Sku": True,
            },
        },
        "sourceBehaviorLedger": [
            {
                "id": "behavior-1",
                "behaviorType": "apiConfiguration",
            }
        ],
        "provenance": {
            "conflicts": [],
            "warnings": [],
        },
        "summary": {
            "apiCount": 1,
            "workspaceCount": 0,
            "inventoryStatus": "complete",
            "requiredDiscoveryComplete": True,
        },
        "collectionCoverage": [
            {
                "scope": (
                    "/subscriptions/sub/resourceGroups/rg/providers/"
                    "Microsoft.ApiManagement/service/source/apis"
                ),
                "configurationDomain": "apis",
                "status": "complete",
            }
        ],
        "scopes": [
            {
                "id": (
                    "/subscriptions/sub/resourceGroups/rg/providers/"
                    "Microsoft.ApiManagement/service/source"
                ),
                "scopeType": "service",
            }
        ],
        "apis": [{"stableId": "source/apis/chat"}],
    }
    source_digest = _migration._digest(  # pylint: disable=protected-access
        source_inventory
    )
    context = {
        "schemaVersion": "2.0",
        "generationId": "generation-1",
        "phase": "plan-validation",
        "completionStatus": "in-progress",
        "source": {
            "resourceId": source_inventory["source"]["id"],
            "subscriptionId": "sub",
            "sku": "BasicV2",
            "provisioningState": "Succeeded",
            "targetProvisioningState": None,
        },
        "destination": {
            "resourceId": (
                "/subscriptions/sub/resourceGroups/rg/providers/"
                "Microsoft.ApiManagement/service/target"
            ),
            "subscriptionId": "sub",
            "resourceGroup": "rg",
            "name": "target",
            "region": "eastus2",
        },
        "sourceInventory": {
            "schemaVersion": "3.0",
            "kind": "AiGatewayApimImportInventory",
            "authority": "authoritative",
            "inventoryStatus": "complete",
            "authoritativeForAbsence": True,
            "artifactDigest": source_digest,
            "provenanceDigest": _migration._digest(  # pylint: disable=protected-access
                source_inventory["provenance"]
            ),
            "behaviorLedgerDigest": _migration._digest(  # pylint: disable=protected-access
                source_inventory["sourceBehaviorLedger"]
            ),
        },
        "capabilityContract": {
            "schemaVersion": "1.0",
            "contractVersion": contract["contractVersion"],
            "kind": contract["kind"],
            "generatedBy": contract["generatedBy"],
            "contractDigest": capability_digest,
            "status": "current",
            "command": [
                "az",
                "ai-gateway",
                "migration-capability",
                "show",
                "--output",
                "json",
            ],
            "capturedAt": "2026-08-28T20:00:00Z",
        },
        "planValidation": {
            "schemaVersion": None,
            "validatorVersion": None,
            "kind": None,
            "status": "not-run",
            "planDigest": None,
            "resultDigest": None,
            "capabilityContractDigest": None,
            "sourceInventoryDigest": None,
            "command": None,
            "validatedAt": None,
            "errorCount": 0,
            "warningCount": 0,
        },
        "digests": {
            "sourceContent": None,
            "sourceCoverage": None,
            "sourceArtifact": _migration._jcs_digest(  # pylint: disable=protected-access
                source_inventory
            ),
            "destinationContent": None,
            "capabilityContract": _migration._jcs_digest(  # pylint: disable=protected-access
                contract
            ),
            "mapping": None,
            "todos": None,
            "plan": None,
            "generationManifest": None,
        },
        "extension": {
            "name": "ai-gateway",
            "version": "1.0.0b1",
        },
        "residualSummary": {
            "total": 0,
            "pendingAcceptance": 0,
            "accepted": 0,
            "rejected": 0,
        },
        "verificationSummary": {
            "resourceStatus": "not-run",
            "behaviorStatus": "not-run",
            "resourcePending": 1,
            "resourceFailed": 0,
            "behaviorPending": 1,
            "behaviorFailed": 0,
        },
        "timestamps": {
            "createdAt": "2026-08-28T20:00:00Z",
            "updatedAt": "2026-08-28T20:00:00Z",
        },
        "lastVerifiedCheckpoint": None,
        "sourceHandoffs": [],
    }
    model_capability = next(
        item
        for item in contract["capabilities"]
        if item["id"] == "model.configure"
    )
    mapping = {
        "schemaVersion": "2.0",
        "generationId": "generation-1",
        "sourceInventoryDigest": source_digest,
        "capabilityContractDigest": capability_digest,
        "items": [
            {
                "id": "model-chat",
                "recordType": "source-behavior",
                "sourceStableIds": ["source/apis/chat"],
                "classification": "ready",
                "authority": "authoritative",
                "sourceBehaviorIds": ["behavior-1"],
                "sourceEvidence": [
                    {
                        "sourceKind": "arm",
                        "artifactId": "source-inventory",
                        "jsonPointer": "/sourceBehaviorLedger/0",
                        "authority": "authoritative",
                        "evidenceDigest": source_digest,
                    }
                ],
                "capabilityEvidence": [
                    {
                        "capabilityId": "model.configure",
                        "contractDigest": capability_digest,
                        "support": "conditional",
                        "destinationCommands": model_capability[
                            "destinationCommands"
                        ],
                        "limitations": model_capability["limitations"],
                    }
                ],
                "destination": {
                    "modelName": "chat",
                },
                "dependencies": [],
                "decisions": [],
                "question": None,
                "residual": {
                    "status": "none",
                    "reason": None,
                    "impact": None,
                    "remediation": None,
                    "acceptanceDecisionId": None,
                    "acceptancePlanDigest": None,
                },
                "verification": {
                    "required": True,
                    "mode": "structural-and-behavioral",
                    "criteria": ["Model exists and responds to a safe probe."],
                    "status": "pending",
                    "evidenceDigest": None,
                },
            }
        ],
    }
    todos = {
        "schemaVersion": "2.0",
        "generationId": "generation-1",
        "sourceInventoryDigest": source_digest,
        "capabilityContractDigest": capability_digest,
        "validation": {
            "schemaVersion": None,
            "status": "not-run",
            "validatorVersion": None,
            "kind": None,
            "planDigest": None,
            "capabilityContractDigest": None,
            "sourceInventoryDigest": None,
            "resultDigest": None,
            "errors": [],
            "warnings": [],
        },
        "items": [
            {
                "id": "create-model-chat",
                "mappingId": "model-chat",
                "sourceBehaviorIds": ["behavior-1"],
                "capabilityRefs": ["model.configure"],
                "dependencies": [],
                "status": "pending",
                "approvalClass": "safe-batch",
                "commandTemplate": [
                    "az",
                    "ai-gateway",
                    "model",
                    "create",
                    "--name",
                    "chat",
                ],
                "operation": {
                    "kind": "create",
                    "commandGroup": "ai-gateway model",
                    "commandName": "create",
                    "targetKey": "chat",
                },
                "precondition": {
                    "commandTemplate": [
                        "az",
                        "ai-gateway",
                        "model",
                        "show",
                        "--name",
                        "chat",
                    ],
                    "expectedOutcome": "Destination model is absent.",
                    "stateDigest": source_digest,
                    "status": "satisfied",
                },
                "idempotency": {
                    "strategy": "read-before-create",
                    "idempotencyKey": "chat",
                    "desiredStateDigest": source_digest,
                    "retryPolicy": "safe",
                    "unknownOutcomeAction": "read-current-state-before-retry",
                },
                "approval": {
                    "status": "pending",
                    "batchId": None,
                    "approvedPlanDigest": None,
                    "approvedPreconditionDigest": None,
                    "approvedAt": None,
                },
                "verification": {
                    "resource": {
                        "commandTemplate": [
                            "az",
                            "ai-gateway",
                            "model",
                            "show",
                            "--name",
                            "chat",
                        ],
                        "expectedStateDigest": source_digest,
                        "observedStateDigest": None,
                        "status": "not-run",
                        "evidence": [],
                    },
                    "behaviors": [
                        {
                            "behaviorId": "behavior-1",
                            "method": "data-plane-probe",
                            "expected": "Model accepts a safe minimal probe.",
                            "observedDigest": None,
                            "status": "not-run",
                            "evidence": [],
                        }
                    ],
                },
                "rollback": {
                    "mode": "none",
                    "commandTemplate": None,
                    "guidance": None,
                    "limitations": ["Delete the model manually."],
                },
                "attempts": [],
                "blockingReason": None,
            }
        ],
    }
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )
    return source_inventory, context, mapping, todos


def _validate(source_inventory, context, mapping, todos):
    return _migration.validate_migration_plan(
        _stream(context),
        _stream(mapping),
        _stream(todos),
        _stream(source_inventory),
    )


def _bind_source_inventory(source_inventory, context, mapping, todos):
    source_digest = _migration._digest(  # pylint: disable=protected-access
        source_inventory
    )
    context["sourceInventory"]["artifactDigest"] = source_digest
    context["sourceInventory"][
        "provenanceDigest"
    ] = _migration._digest(  # pylint: disable=protected-access
        source_inventory["provenance"]
    )
    context["sourceInventory"][
        "behaviorLedgerDigest"
    ] = _migration._digest(  # pylint: disable=protected-access
        source_inventory["sourceBehaviorLedger"]
    )
    context["sourceInventory"]["inventoryStatus"] = source_inventory[
        "summary"
    ]["inventoryStatus"]
    context["digests"][
        "sourceArtifact"
    ] = _migration._jcs_digest(  # pylint: disable=protected-access
        source_inventory
    )
    mapping["sourceInventoryDigest"] = source_digest
    todos["sourceInventoryDigest"] = source_digest
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )
    return source_digest


def test_capability_contract_is_deterministic_and_sorted():
    first = _migration.show_migration_capability()
    second = _migration.show_migration_capability()

    assert first == second
    assert first["kind"] == "AiGatewayMigrationCapabilityContract"
    assert first["schemaVersion"] == "1.0"
    assert first["contractDigest"].startswith("sha256:")
    assert [item["id"] for item in first["capabilities"]] == sorted(
        item["id"] for item in first["capabilities"]
    )
    assert {
        item["support"] for item in first["capabilities"]
    } <= _migration._ALLOWED_SUPPORT  # pylint: disable=protected-access
    for capability in first["capabilities"]:
        assert {
            "allowedCommands",
            "behaviorVerification",
            "mutationSemantics",
            "precondition",
            "sourceDomains",
            "structuralVerification",
        } <= capability.keys()
        for command in capability["allowedCommands"]:
            assert command["prefix"][:2] == ["az", "ai-gateway"]
            assert command["group"]
            assert command["name"]
            assert command["mutation"]
            assert command["idempotency"]
    inventory_behavior_types = {
        "apiConfiguration",
        "authorizationProviders",
        "backendDependency",
        "backends",
        "certificates",
        "diagnostic",
        "diagnostics",
        "groups",
        "identityProviders",
        "loggerReference",
        "loggers",
        "mcpTool",
        "namedValues",
        "operation",
        "policyFragments",
        "policyStatement",
        "productRelationship",
        "products",
        "subscriptionRelationship",
        "subscriptions",
    }
    covered_behavior_types = {
        behavior_type
        for capability in first["capabilities"]
        for behavior_type in capability["sourceBehaviorTypes"]
    }
    assert inventory_behavior_types <= covered_behavior_types


def test_jcs_artifact_canonicalizer_uses_ecmascript_number_format():
    value = {
        "fixedLowerBoundary": 1e-6,
        "fixedUpperRange": 1e20,
        "negativeZero": -0.0,
        "scientificLowerRange": 1e-7,
        "scientificUpperBoundary": 1e21,
    }

    assert _migration._jcs_canonical_json(  # pylint: disable=protected-access
        value
    ) == (
        '{"fixedLowerBoundary":0.000001,'
        '"fixedUpperRange":100000000000000000000,'
        '"negativeZero":0,'
        '"scientificLowerRange":1e-7,'
        '"scientificUpperBoundary":1e+21}'
    )
    contract = _migration.show_migration_capability()
    assert _migration._jcs_digest(  # pylint: disable=protected-access
        contract
    ) != contract["contractDigest"]


def test_command_table_registers_migration_contract_and_validator():
    loader = _CommandLoader()

    commands.load_command_table(loader, None)

    assert (
        "ai-gateway migration-capability",
        "show",
        "show_migration_capability",
    ) in loader.registrations
    assert (
        "ai-gateway migration-plan",
        "validate",
        "validate_migration_plan",
    ) in loader.registrations


def test_validate_migration_plan_accepts_safe_deterministic_plan():
    source_inventory, context, mapping, todos = _documents()

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "valid"
    assert result["errors"] == []
    assert result["planDigest"] == todos["planDigest"]
    assert result["capabilityContractDigest"] == (
        _migration.show_migration_capability()["contractDigest"]
    )
    assert result == _validate(source_inventory, context, mapping, todos)


def test_validate_migration_plan_rejects_schema_invalid_state():
    source_inventory, context, mapping, todos = _documents()
    del context["timestamps"]
    mapping["items"][0]["unexpected"] = True
    del todos["items"][0]["operation"]["targetKey"]
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        (error["code"], error["path"]) for error in result["errors"]
    } >= {
        ("schema-additional-property", "/mapping/items/0/unexpected"),
        ("schema-required", "/context/timestamps"),
        ("schema-required", "/todos/items/0/operation/targetKey"),
    }


def test_completed_context_requires_stable_source_and_destination():
    _, context, mapping, todos = _documents()
    context["phase"] = "complete"
    context["completionStatus"] = "complete"
    context["source"]["targetProvisioningState"] = "Activating"
    context["destination"]["region"] = None

    errors = validate_migration_state(context, mapping, todos)

    assert {
        error["path"] for error in errors if error["code"] in {
            "schema-enum",
            "schema-type",
        }
    } >= {
        "/context/source/targetProvisioningState",
        "/context/destination/region",
    }


def test_mapping_conditionals_reject_ambiguous_residual_state():
    source_inventory, context, mapping, todos = _documents()
    item = mapping["items"][0]
    item["classification"] = "needs-input"
    item["sourceBehaviorIds"] = []
    item["question"] = None
    item["residual"].update(
        {
            "status": "pending-acceptance",
            "reason": "Behavior is not currently representable.",
            "impact": "Behavior would be omitted.",
            "remediation": "Resolve the mapping before approval.",
        }
    )
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    schema_issues = {
        (error["code"], error["path"]) for error in result["errors"]
    }
    assert schema_issues >= {
        ("schema-enum", "/mapping/items/0/classification"),
        ("schema-min-items", "/mapping/items/0/sourceBehaviorIds"),
        ("schema-type", "/mapping/items/0/question"),
    }


def test_validate_migration_plan_rejects_direct_command_and_cycle():
    source_inventory, context, mapping, todos = _documents()
    item = todos["items"][0]
    item["commandTemplate"] = ["az", "rest", "--method", "PUT"]
    item["dependencies"] = [item["id"]]
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        error["code"] for error in result["errors"]
    } >= {"forbidden-command", "self-dependency", "dependency-cycle"}


def test_validate_migration_plan_rejects_stale_residual_acceptance():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["sourceBehaviorLedger"] = [
        {
            "id": "behavior-1",
            "behaviorType": "products",
        }
    ]
    source_digest = _migration._digest(  # pylint: disable=protected-access
        source_inventory
    )
    context["sourceInventory"]["artifactDigest"] = source_digest
    mapping["sourceInventoryDigest"] = source_digest
    todos["sourceInventoryDigest"] = source_digest
    relationship = next(
        item
        for item in _migration.show_migration_capability()["capabilities"]
        if item["id"] == "relationship.unsupported"
    )
    mapping["items"][0].update({
        "id": "unsupported-relationship",
        "recordType": "source-behavior",
        "sourceStableIds": ["source/products/product"],
        "classification": "cannot-import",
        "authority": "authoritative",
        "sourceBehaviorIds": ["behavior-1"],
        "sourceEvidence": [
            {
                "sourceKind": "arm",
                "artifactId": "source-inventory",
                "jsonPointer": "/sourceBehaviorLedger/0",
                "authority": "authoritative",
                "evidenceDigest": source_digest,
            }
        ],
        "capabilityEvidence": [
            {
                "capabilityId": "relationship.unsupported",
                "contractDigest": mapping["capabilityContractDigest"],
                "support": "unsupported",
                "destinationCommands": relationship["destinationCommands"],
                "limitations": relationship["limitations"],
            }
        ],
        "destination": None,
        "dependencies": [],
        "decisions": [
            {
                "id": "decision-1",
                "type": "residual-acceptance",
                "decision": "Accept the unsupported relationship.",
                "decidedAt": "2026-08-28T20:00:00Z",
            }
        ],
        "question": None,
        "residual": {
            "status": "accepted",
            "reason": "No destination equivalent.",
            "impact": "Product grouping is not migrated.",
            "remediation": "Manage grouping outside AI Gateway.",
            "acceptanceDecisionId": "decision-1",
            "acceptancePlanDigest": "sha256:" + ("2" * 64),
        },
        "verification": {
            "required": True,
            "mode": "manual",
            "criteria": ["Residual acceptance is recorded."],
            "status": "residual-accepted",
            "evidenceDigest": "sha256:" + ("6" * 64),
        },
    })
    todos["items"] = []
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "stale-residual-decision" in {
        error["code"] for error in result["errors"]
    }


def test_validate_migration_plan_accepts_canonical_residual_binding():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["sourceBehaviorLedger"] = [
        {
            "id": "behavior-1",
            "behaviorType": "products",
        }
    ]
    source_digest = _bind_source_inventory(
        source_inventory,
        context,
        mapping,
        todos,
    )
    relationship = next(
        item
        for item in _migration.show_migration_capability()["capabilities"]
        if item["id"] == "relationship.unsupported"
    )
    mapping["items"] = [
        {
            "id": "unsupported-relationship",
            "recordType": "source-behavior",
            "sourceStableIds": ["source/products/product"],
            "classification": "cannot-import",
            "authority": "authoritative",
            "sourceBehaviorIds": ["behavior-1"],
            "sourceEvidence": [
                {
                    "sourceKind": "arm",
                    "artifactId": "source-inventory",
                    "jsonPointer": "/sourceBehaviorLedger/0",
                    "authority": "authoritative",
                    "evidenceDigest": source_digest,
                }
            ],
            "capabilityEvidence": [
                {
                    "capabilityId": "relationship.unsupported",
                    "contractDigest": mapping["capabilityContractDigest"],
                    "support": "unsupported",
                    "destinationCommands": relationship[
                        "destinationCommands"
                    ],
                    "limitations": relationship["limitations"],
                }
            ],
            "destination": None,
            "dependencies": [],
            "decisions": [
                {
                    "id": "decision-1",
                    "type": "residual-acceptance",
                    "decision": "Accept the unsupported relationship.",
                    "decidedAt": "2026-08-28T20:00:00Z",
                }
            ],
            "question": None,
            "residual": {
                "status": "pending-acceptance",
                "reason": "No destination equivalent.",
                "impact": "Product grouping is not migrated.",
                "remediation": "Manage grouping outside AI Gateway.",
                "acceptanceDecisionId": None,
                "acceptancePlanDigest": None,
            },
            "verification": {
                "required": True,
                "mode": "manual",
                "criteria": ["Residual acceptance is recorded."],
                "status": "pending",
                "evidenceDigest": None,
            },
        }
    ]
    todos["items"] = []
    plan_digest = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )
    residual = mapping["items"][0]["residual"]
    residual["status"] = "accepted"
    residual["acceptanceDecisionId"] = "decision-1"
    residual["acceptancePlanDigest"] = plan_digest
    mapping["items"][0]["verification"]["status"] = "residual-accepted"
    mapping["items"][0]["verification"]["evidenceDigest"] = (
        "sha256:" + ("6" * 64)
    )
    todos["planDigest"] = plan_digest
    context["residualSummary"] = {
        "total": 1,
        "pendingAcceptance": 0,
        "accepted": 1,
        "rejected": 0,
    }
    context["verificationSummary"] = {
        "resourceStatus": "not-run",
        "behaviorStatus": "not-run",
        "resourcePending": 0,
        "resourceFailed": 0,
        "behaviorPending": 0,
        "behaviorFailed": 0,
    }

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "valid"
    assert result["planDigest"] == plan_digest


def test_validate_migration_plan_returns_issues_for_invalid_item_shapes():
    source_inventory, context, mapping, todos = _documents()
    mapping["items"] = "not-an-array"
    todos["items"] = {"not": "an array"}

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        error["path"] for error in result["errors"]
    } >= {"/mapping/items", "/todos/items"}


def test_validate_migration_plan_requires_complete_ledger_coverage():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["sourceBehaviorLedger"].append(
        {
            "id": "behavior-2",
            "behaviorType": "operation",
        }
    )
    _bind_source_inventory(source_inventory, context, mapping, todos)

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "unmapped-source-behavior" in {
        error["code"] for error in result["errors"]
    }


def test_validate_migration_plan_rejects_undisposed_provenance_conflict():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["provenance"]["conflicts"] = [
        {
            "stableId": "source/apis/chat",
            "field": "api",
            "selectedSource": "apiops",
            "otherSource": "armTemplate",
        }
    ]
    source_inventory["summary"]["inventoryStatus"] = "partial"
    source_inventory["summary"]["requiredDiscoveryComplete"] = False
    _bind_source_inventory(source_inventory, context, mapping, todos)

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "undisposed-provenance-conflict" in {
        error["code"] for error in result["errors"]
    }
    assert "inventory-summary-mismatch" not in {
        error["code"] for error in result["errors"]
    }


def test_precondition_allowlist_uses_command_path_only():
    assert _migration._is_safe_precondition_command(  # pylint: disable=protected-access
        ["az", "ai-gateway", "model", "show", "--name", "test"]
    )
    assert not _migration._is_safe_precondition_command(  # pylint: disable=protected-access
        ["az", "ai-gateway", "api-key", "list-secrets", "--name", "key"]
    )


def test_validator_reports_malformed_arrays_and_commands_without_crashing():
    source_inventory, context, mapping, todos = _documents()
    item = todos["items"][0]
    item["dependencies"] = [{"invalid": "dependency"}]
    item["precondition"]["commandTemplate"] = [
        "az",
        "ai-gateway",
        1,
        "show",
    ]

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "schema-type" in {
        error["code"] for error in result["errors"]
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda source, _context, _mapping, _todos: source.__setitem__(
            "summary",
            "invalid",
        ),
        lambda _source, _context, mapping, _todos: mapping["items"][0].__setitem__(
            "residual",
            "invalid",
        ),
        lambda _source, context, _mapping, _todos: context.__setitem__(
            "completionStatus",
            [],
        ),
    ],
)
def test_validator_returns_structured_error_for_invalid_nested_shapes(mutate):
    source_inventory, context, mapping, todos = _documents()
    mutate(source_inventory, context, mapping, todos)

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert result["errors"]
    assert all(
        {"code", "path", "message"} <= set(error)
        for error in result["errors"]
    )


def test_validator_returns_structured_error_for_invalid_unicode():
    source_inventory, context, mapping, todos = _documents()
    mapping["items"][0]["destination"]["modelName"] = "\ud800"

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert result["errors"][0]["code"] == "invalid-document-shape"


def test_validate_migration_plan_rejects_unreliable_source_inventory():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["source"]["id"] = source_inventory["source"]["id"].replace(
        "/source",
        "/other",
    )
    source_inventory["source"]["sku"] = "Developer"
    source_inventory["source"]["provisioningState"] = "Failed"
    source_inventory["source"]["migrationCompatibility"] = {
        "skuFamily": "other",
        "supportedV2Sku": False,
    }
    source_inventory["collectionCoverage"][0]["status"] = "failed"
    _bind_source_inventory(source_inventory, context, mapping, todos)

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        error["code"] for error in result["errors"]
    } >= {
        "incomplete-collection-coverage",
        "inventory-summary-mismatch",
        "invalid-source-capability-evidence",
        "missing-coverage-gap-mapping",
        "source-not-ready",
        "source-resource-mismatch",
        "unsupported-source-sku",
    }


def test_validate_migration_plan_requires_workspace_scope_coverage():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["scopes"].append(
        {
            "id": (
                "/subscriptions/sub/resourceGroups/rg/providers/"
                "Microsoft.ApiManagement/service/source/workspaces/team"
            ),
            "scopeType": "workspace",
        }
    )
    source_inventory["summary"]["workspaceCount"] = 1
    _bind_source_inventory(source_inventory, context, mapping, todos)

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "scope-coverage-missing" in {
        error["code"] for error in result["errors"]
    }


def test_validate_migration_plan_rejects_persisted_runtime_secret():
    source_inventory, context, mapping, todos = _documents()
    mapping["items"][0]["destination"].update(
        {
            "connectionString": "raw-secret-value",
            "endpoint": "https://user:password@example.invalid/models",
        }
    )
    todos["items"][0]["commandTemplate"].extend(
        [
            "--api-key-value",
            "raw-secret-value",
            "--headers",
            "Authorization=raw-secret-value",
        ]
    )
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "persisted-secret" in {
        error["code"] for error in result["errors"]
    }
    assert "raw-secret-value" not in json.dumps(result)


def test_validate_migration_plan_allows_explicit_runtime_secret_reference():
    source_inventory, context, mapping, todos = _documents()
    mapping["items"][0]["destination"]["endpoint"] = (
        "https://example.invalid/models?"
        "api-key=${RUNTIME_SECRET:provider-api-key}"
    )
    todos["items"][0]["commandTemplate"].extend(
        [
            "--api-key-value",
            "${RUNTIME_SECRET:provider-api-key}",
            "--headers",
            "Authorization=Bearer ${RUNTIME_SECRET:provider-token}",
        ]
    )
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "valid"
    assert not any(
        error["code"] == "persisted-secret" for error in result["errors"]
    )


def test_runtime_secret_placeholder_syntax_is_strict():
    assert _migration._is_runtime_placeholder(  # pylint: disable=protected-access
        "${RUNTIME_SECRET:provider-api-key}"
    )
    assert _migration._is_runtime_placeholder(  # pylint: disable=protected-access
        "<redacted>"
    )
    assert not _migration._is_runtime_placeholder(  # pylint: disable=protected-access
        "${API_KEY}"
    )
    assert not _migration._is_runtime_placeholder(  # pylint: disable=protected-access
        "{{secret}}"
    )
    assert not _migration._is_runtime_placeholder(  # pylint: disable=protected-access
        "<runtime-secret>"
    )


def test_validate_migration_plan_rejects_unsafe_execution_contract():
    source_inventory, context, mapping, todos = _documents()
    item = todos["items"][0]
    item["operation"]["commandName"] = "update"
    item["idempotency"]["desiredStateDigest"] = None
    item["rollback"]["limitations"] = []
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        error["code"] for error in result["errors"]
    } >= {
        "missing-desired-state-digest",
        "missing-rollback-limitations",
        "operation-command-mismatch",
    }


def test_validator_enforces_capability_execution_contract():
    source_inventory, context, mapping, todos = _documents()
    contract = _migration.show_migration_capability()
    telemetry = next(
        item
        for item in contract["capabilities"]
        if item["id"] == "telemetry.configure"
    )
    assert telemetry["approvalClass"] == "consequential"
    source_inventory["sourceBehaviorLedger"] = [
        {
            "id": "behavior-1",
            "behaviorType": "diagnostic",
        }
    ]
    source_digest = _bind_source_inventory(
        source_inventory,
        context,
        mapping,
        todos,
    )
    mapping["items"][0].update(
        {
            "sourceBehaviorIds": ["behavior-1"],
            "sourceEvidence": [
                {
                    "sourceKind": "arm",
                    "artifactId": "source-inventory",
                    "jsonPointer": "/sourceBehaviorLedger/0",
                    "authority": "authoritative",
                    "evidenceDigest": source_digest,
                }
            ],
            "capabilityEvidence": [
                {
                    "capabilityId": "telemetry.configure",
                    "contractDigest": contract["contractDigest"],
                    "support": "conditional",
                    "destinationCommands": telemetry["destinationCommands"],
                    "limitations": telemetry["limitations"],
                }
            ],
        }
    )
    item = todos["items"][0]
    item.update(
        {
            "sourceBehaviorIds": ["behavior-1"],
            "capabilityRefs": ["telemetry.configure"],
            "approvalClass": "safe-batch",
            "commandTemplate": [
                "az",
                "ai-gateway",
                "telemetry-exporter",
                "create",
            ],
            "operation": {
                "kind": "create",
                "commandGroup": "ai-gateway telemetry-exporter",
                "commandName": "create",
                "targetKey": "exporter",
            },
        }
    )
    item["precondition"]["commandTemplate"] = [
        "az",
        "ai-gateway",
        "telemetry-exporter",
        "list",
    ]
    item["idempotency"].update(
        {
            "strategy": "compare-before-update",
            "idempotencyKey": "exporter",
        }
    )
    item["verification"]["resource"]["commandTemplate"] = [
        "az",
        "ai-gateway",
        "telemetry-exporter",
        "list",
    ]
    item["verification"]["behaviors"] = [
        {
            "behaviorId": "behavior-1",
            "method": "data-plane-probe",
            "expected": "Telemetry exporter is configured.",
            "observedDigest": None,
            "status": "not-run",
            "evidence": [],
        }
    ]
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        error["code"] for error in result["errors"]
    } >= {
        "approval-class-mismatch",
        "idempotency-mismatch",
        "verification-method-mismatch",
    }


def test_behavior_verified_allows_behaviorless_gateway_creation():
    source_inventory, context, mapping, todos = _documents()
    source_inventory["sourceBehaviorLedger"] = []
    source_digest = _bind_source_inventory(
        source_inventory,
        context,
        mapping,
        todos,
    )
    contract = _migration.show_migration_capability()
    gateway = next(
        item
        for item in contract["capabilities"]
        if item["id"] == "gateway.create"
    )
    mapping_item = mapping["items"][0]
    mapping_item.update(
        {
            "id": "destination-gateway",
            "recordType": "source-item",
            "sourceStableIds": [source_inventory["source"]["id"]],
            "sourceBehaviorIds": [],
            "sourceEvidence": [
                {
                    "sourceKind": "arm",
                    "artifactId": "source-inventory",
                    "jsonPointer": "/source",
                    "authority": "authoritative",
                    "evidenceDigest": source_digest,
                }
            ],
            "capabilityEvidence": [
                {
                    "capabilityId": "gateway.create",
                    "contractDigest": contract["contractDigest"],
                    "support": "supported",
                    "destinationCommands": gateway["destinationCommands"],
                    "limitations": gateway["limitations"],
                }
            ],
            "destination": {"name": "target"},
            "verification": {
                "required": True,
                "mode": "structural",
                "criteria": ["Gateway exists with the approved configuration."],
                "status": "pending",
                "evidenceDigest": None,
            },
        }
    )
    item = todos["items"][0]
    item.update(
        {
            "id": "create-destination-gateway",
            "mappingId": "destination-gateway",
            "sourceBehaviorIds": [],
            "capabilityRefs": ["gateway.create"],
            "status": "behavior-verified",
            "approvalClass": "safe-batch",
            "commandTemplate": [
                "az",
                "ai-gateway",
                "create",
                "--name",
                "target",
            ],
            "operation": {
                "kind": "create",
                "commandGroup": "ai-gateway",
                "commandName": "create",
                "targetKey": "target",
            },
        }
    )
    item["verification"]["behaviors"] = []
    resource = item["verification"]["resource"]
    resource["commandTemplate"] = [
        "az",
        "ai-gateway",
        "show",
        "--name",
        "target",
    ]
    resource["status"] = "passed"
    resource["observedStateDigest"] = resource["expectedStateDigest"]
    resource["evidence"] = ["Gateway read-back passed."]
    item["precondition"]["commandTemplate"] = list(
        resource["commandTemplate"]
    )
    item["idempotency"]["idempotencyKey"] = "target"
    item["attempts"] = [
        {
            "attemptId": "attempt-1",
            "startedAt": "2026-08-28T20:00:00Z",
            "finishedAt": "2026-08-28T20:00:01Z",
            "exitStatus": 0,
            "outcome": "applied",
            "resultDigest": "sha256:" + ("7" * 64),
            "reconciliation": {
                "status": "not-required",
                "observedStateDigest": resource["observedStateDigest"],
                "safeSummary": "Gateway creation succeeded.",
            },
        }
    ]
    context["verificationSummary"]["resourceStatus"] = "passed"
    context["verificationSummary"]["behaviorStatus"] = "passed"
    context["verificationSummary"]["resourcePending"] = 0
    context["verificationSummary"]["behaviorPending"] = 0
    todos["planDigest"] = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "valid", result["errors"]


def test_behavior_verified_rejects_missing_mapped_behavior_checks():
    source_inventory, context, mapping, todos = _documents()
    item = todos["items"][0]
    item["status"] = "behavior-verified"
    item["verification"]["behaviors"] = []
    resource = item["verification"]["resource"]
    resource["status"] = "passed"
    resource["observedStateDigest"] = resource["expectedStateDigest"]
    resource["evidence"] = ["Model read-back passed."]
    item["attempts"] = [
        {
            "attemptId": "attempt-1",
            "startedAt": "2026-08-28T20:00:00Z",
            "finishedAt": "2026-08-28T20:00:01Z",
            "exitStatus": 0,
            "outcome": "applied",
            "resultDigest": "sha256:" + ("7" * 64),
            "reconciliation": {
                "status": "not-required",
                "observedStateDigest": resource["observedStateDigest"],
                "safeSummary": "Model creation succeeded.",
            },
        }
    ]
    context["verificationSummary"] = {
        "resourceStatus": "passed",
        "behaviorStatus": "passed",
        "resourcePending": 0,
        "resourceFailed": 0,
        "behaviorPending": 0,
        "behaviorFailed": 0,
    }

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert (
        "schema-min-items",
        "/todos/items/0/verification/behaviors",
    ) in {
        (error["code"], error["path"]) for error in result["errors"]
    }


def test_resource_verified_requires_execution_attempt():
    source_inventory, context, mapping, todos = _documents()
    item = todos["items"][0]
    item["status"] = "resource-verified"
    resource = item["verification"]["resource"]
    resource["status"] = "passed"
    resource["observedStateDigest"] = resource["expectedStateDigest"]
    resource["evidence"] = ["Model read-back passed."]

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert (
        "schema-min-items",
        "/todos/items/0/attempts",
    ) in {
        (error["code"], error["path"]) for error in result["errors"]
    }


def test_mutation_unknown_requires_unknown_outcome_attempt():
    source_inventory, context, mapping, todos = _documents()
    item = todos["items"][0]
    item["status"] = "mutation-unknown"
    item["attempts"] = [
        {
            "attemptId": "attempt-1",
            "startedAt": "2026-08-28T20:00:00Z",
            "finishedAt": "2026-08-28T20:00:01Z",
            "exitStatus": 0,
            "outcome": "applied",
            "resultDigest": "sha256:" + ("7" * 64),
            "reconciliation": {
                "status": "not-required",
                "observedStateDigest": None,
                "safeSummary": "Mutation appeared to succeed.",
            },
        }
    ]

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert (
        "schema-contains",
        "/todos/items/0/attempts",
    ) in {
        (error["code"], error["path"]) for error in result["errors"]
    }


def test_verified_statuses_require_digests_and_evidence():
    source_inventory, context, mapping, todos = _documents()
    mapping["items"][0]["verification"]["status"] = "passed"
    mapping["items"][0]["verification"]["evidenceDigest"] = None
    item = todos["items"][0]
    item["status"] = "behavior-verified"
    resource = item["verification"]["resource"]
    resource["status"] = "passed"
    resource["observedStateDigest"] = None
    resource["evidence"] = []
    behavior = item["verification"]["behaviors"][0]
    behavior["status"] = "passed"
    behavior["observedDigest"] = None
    behavior["evidence"] = []
    item["attempts"] = [
        {
            "attemptId": "attempt-1",
            "startedAt": "2026-08-28T20:00:00Z",
            "finishedAt": "2026-08-28T20:00:01Z",
            "exitStatus": 0,
            "outcome": "applied",
            "resultDigest": "sha256:" + ("7" * 64),
            "reconciliation": {
                "status": "not-required",
                "observedStateDigest": None,
                "safeSummary": "Mutation completed.",
            },
        }
    ]
    context["verificationSummary"] = {
        "resourceStatus": "passed",
        "behaviorStatus": "passed",
        "resourcePending": 0,
        "resourceFailed": 0,
        "behaviorPending": 0,
        "behaviorFailed": 0,
    }

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert "schema-format" in {
        error["code"] for error in result["errors"]
    }
    assert any(
        error["path"] == "/mapping/items/0/verification/evidenceDigest"
        for error in result["errors"]
    )


def test_validator_recomputes_context_verification_summary():
    source_inventory, context, mapping, todos = _documents()
    context["verificationSummary"] = {
        "resourceStatus": "passed",
        "behaviorStatus": "passed",
        "resourcePending": 0,
        "resourceFailed": 0,
        "behaviorPending": 0,
        "behaviorFailed": 0,
    }

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    mismatches = {
        error["path"]
        for error in result["errors"]
        if error["code"] == "verification-summary-mismatch"
    }
    assert mismatches >= {
        "/context/verificationSummary/resourceStatus",
        "/context/verificationSummary/resourcePending",
        "/context/verificationSummary/behaviorStatus",
        "/context/verificationSummary/behaviorPending",
    }


def test_validator_cross_checks_artifact_and_checkpoint_digests():
    source_inventory, context, mapping, todos = _documents()
    context["digests"]["mapping"] = "sha256:" + ("0" * 64)
    context["digests"]["todos"] = "sha256:" + ("0" * 64)
    context["digests"]["plan"] = "sha256:" + ("0" * 64)
    context["digests"]["generationManifest"] = "sha256:" + ("1" * 64)
    context["lastVerifiedCheckpoint"] = {
        "generationId": "older-generation",
        "manifestDigest": "sha256:" + ("2" * 64),
        "verifiedAt": "2026-08-28T20:00:00Z",
    }

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "invalid"
    assert {
        error["code"] for error in result["errors"]
    } >= {
        "checkpoint-generation-mismatch",
        "checkpoint-manifest-mismatch",
        "context-digest-mismatch",
    }


def test_validate_migration_plan_accepts_verified_completion():
    source_inventory, context, mapping, todos = _documents()
    plan_digest = todos["planDigest"]
    capability_digest = mapping["capabilityContractDigest"]
    source_digest = mapping["sourceInventoryDigest"]
    validation = {
        "schemaVersion": "1.0",
        "validatorVersion": "1.0",
        "kind": "AiGatewayMigrationPlanValidation",
        "status": "valid",
        "planDigest": plan_digest,
        "capabilityContractDigest": capability_digest,
        "sourceInventoryDigest": source_digest,
        "errors": [],
        "warnings": [],
    }
    validation["resultDigest"] = _migration._digest(  # pylint: disable=protected-access
        validation
    )
    context_validation = {
        "schemaVersion": "1.0",
        "validatorVersion": "1.0",
        "kind": "AiGatewayMigrationPlanValidation",
        "status": "valid",
        "planDigest": plan_digest,
        "capabilityContractDigest": capability_digest,
        "sourceInventoryDigest": source_digest,
        "resultDigest": validation["resultDigest"],
        "command": [
            "az",
            "ai-gateway",
            "migration-plan",
            "validate",
        ],
        "validatedAt": "2026-08-28T20:00:00Z",
        "errorCount": 0,
        "warningCount": 0,
    }
    context.update(
        {
            "phase": "complete",
            "completionStatus": "complete",
            "planValidation": context_validation,
            "verificationSummary": {
                "resourceStatus": "passed",
                "behaviorStatus": "passed",
                "resourcePending": 0,
                "resourceFailed": 0,
                "behaviorPending": 0,
                "behaviorFailed": 0,
            },
        }
    )
    context["sourceInventory"].update(
        {
            "authority": "authoritative",
            "inventoryStatus": "complete",
            "authoritativeForAbsence": True,
        }
    )
    todos["validation"] = validation
    todos["items"][0]["status"] = "behavior-verified"
    resource = todos["items"][0]["verification"]["resource"]
    resource["status"] = "passed"
    resource["observedStateDigest"] = resource["expectedStateDigest"]
    resource["evidence"] = ["Gateway read-back matched desired state."]
    behavior = todos["items"][0]["verification"]["behaviors"][0]
    behavior["status"] = "passed"
    behavior["observedDigest"] = "sha256:" + ("8" * 64)
    behavior["evidence"] = ["Safe model probe passed."]
    todos["items"][0]["attempts"] = [
        {
            "attemptId": "attempt-1",
            "startedAt": "2026-08-28T20:00:00Z",
            "finishedAt": "2026-08-28T20:00:01Z",
            "exitStatus": 0,
            "outcome": "applied",
            "resultDigest": "sha256:" + ("7" * 64),
            "reconciliation": {
                "status": "not-required",
                "observedStateDigest": resource["observedStateDigest"],
                "safeSummary": "Model creation succeeded.",
            },
        }
    ]
    context["digests"].update(
        {
            "sourceContent": "sha256:" + ("5" * 64),
            "sourceCoverage": "sha256:" + ("4" * 64),
            "destinationContent": "sha256:" + ("3" * 64),
            "mapping": _migration._jcs_digest(  # pylint: disable=protected-access
                mapping
            ),
            "todos": _migration._jcs_digest(  # pylint: disable=protected-access
                todos
            ),
            "plan": plan_digest,
            "generationManifest": "sha256:" + ("2" * 64),
        }
    )
    context["lastVerifiedCheckpoint"] = {
        "generationId": context["generationId"],
        "manifestDigest": context["digests"]["generationManifest"],
        "verifiedAt": "2026-08-28T20:00:02Z",
    }

    result = _validate(source_inventory, context, mapping, todos)

    assert result["status"] == "valid"


def test_plan_projection_excludes_runtime_state_but_not_commands():
    _, _, mapping, todos = _documents()
    original = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )
    todos["items"][0]["approval"] = {
        "status": "approved",
        "approvedAt": "2026-08-28T20:00:00Z",
    }
    todos["items"][0]["attempts"] = [{"outcome": "applied"}]
    runtime_change = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )
    todos["items"][0]["commandTemplate"].append("--location")
    todos["items"][0]["commandTemplate"].append("westus2")
    plan_change = _migration._digest(  # pylint: disable=protected-access
        _migration._plan_projection(mapping, todos)  # pylint: disable=protected-access
    )

    assert runtime_change == original
    assert plan_change != original


def test_table_formatters_are_machine_result_summaries():
    capability = _migration.show_migration_capability()
    validation = {
        "status": "invalid",
        "errors": [{"code": "error"}],
        "warnings": [{"code": "warning"}],
        "planDigest": "sha256:" + ("0" * 64),
    }

    assert _migration.format_migration_capability_table(capability)[0][
        "Capability"
    ]
    assert _migration.format_migration_plan_validation_table(validation) == [
        {
            "Status": "invalid",
            "Errors": 1,
            "Warnings": 1,
            "Plan digest": "sha256:" + ("0" * 64),
        }
    ]
