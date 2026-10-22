# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import hashlib
import json
import math
import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from azure.cli.core.azclierror import (
    FileOperationError,
    InvalidArgumentValueError,
)
from azext_ai_gateway._migration_validation import validate_migration_state


CAPABILITY_SCHEMA_VERSION = "1.0"
CAPABILITY_CONTRACT_VERSION = "2026-08-28"
PLAN_VALIDATOR_VERSION = "1.0"
_DIGEST_PREFIX = "sha256:"
_ALLOWED_SUPPORT = {"supported", "conditional", "unsupported"}
_SUPPORTED_SOURCE_SKUS = ["BasicV2", "StandardV2", "PremiumV2"]
_RUNTIME_SECRET = re.compile(r"^\$\{RUNTIME_SECRET:[A-Za-z0-9._-]+\}$")
_RUNTIME_SECRET_REFERENCE = re.compile(
    r"\$\{RUNTIME_SECRET:[A-Za-z0-9._-]+\}"
)
_AUTHORITIES = {
    "authoritative",
    "corroborated",
    "advisory",
    "conflicted",
    "insufficient",
    "unknown",
}
_READY_AUTHORITIES = {"authoritative", "corroborated"}
_SOURCE_DOMAINS = {
    "apiConfiguration": "apis",
    "authorizationProviders": "relationships",
    "backendDependency": "backends",
    "backends": "backends",
    "certificates": "relationships",
    "diagnostic": "diagnostics",
    "diagnostics": "diagnostics",
    "group": "relationships",
    "groups": "relationships",
    "identityProvider": "relationships",
    "identityProviders": "relationships",
    "loggerReference": "telemetry",
    "loggers": "telemetry",
    "managedIdentity": "identity",
    "mcpTool": "mcp",
    "namedValues": "relationships",
    "networkConfiguration": "network",
    "operation": "operations",
    "policyFragments": "policies",
    "policyStatement": "policies",
    "productRelationship": "relationships",
    "products": "relationships",
    "subscriptionRelationship": "relationships",
    "subscriptions": "relationships",
}
_RUNTIME_KEYS = {
    "acceptedAt",
    "approvedAt",
    "createdAt",
    "decidedAt",
    "finishedAt",
    "generatedAt",
    "startedAt",
    "timestamp",
    "timestamps",
    "updatedAt",
    "validatedAt",
}


def _command_contract(command):
    name = command[-1]
    mutation = {
        "assign": "action",
        "create": "create",
        "sync": "sync",
        "update": "update",
    }.get(name, "action")
    idempotency = {
        "create": "read-before-create",
        "sync": "preview-before-sync",
        "update": "compare-before-update",
    }.get(name, "compare-before-update")
    return {
        "group": " ".join(command[1:-1]),
        "name": name,
        "prefix": command,
        "mutation": mutation,
        "idempotency": idempotency,
        "precondition": (
            "approved-dry-run"
            if name == "sync"
            else "read-current-state"
        ),
    }


def _capability(
    capability_id,
    source_behavior_types,
    support,
    destination_commands,
    approval_class,
    idempotency,
    verification,
    limitations,
):
    behavior_types = sorted(source_behavior_types)
    commands = sorted(destination_commands)
    structural_verification = [
        method for method in verification if method == "control-plane-read"
    ]
    return {
        "id": capability_id,
        "sourceBehaviorTypes": behavior_types,
        "sourceDomains": sorted(
            {
                _SOURCE_DOMAINS[behavior_type]
                for behavior_type in behavior_types
                if behavior_type in _SOURCE_DOMAINS
            }
        ),
        "supportedSourceSkus": _SUPPORTED_SOURCE_SKUS,
        "support": support,
        "destinationCommands": commands,
        "allowedCommands": [
            _command_contract(command) for command in commands
        ],
        "approvalClass": approval_class,
        "mutationSemantics": sorted(
            {_command_contract(command)["mutation"] for command in commands}
        )
        or ["verify"],
        "precondition": {
            "required": support != "unsupported",
            "stateDigestRequired": support != "unsupported",
            "unknownStateAction": "block",
        },
        "idempotency": idempotency,
        "verification": verification,
        "structuralVerification": structural_verification,
        "behaviorVerification": verification,
        "limitations": limitations,
    }


_CAPABILITIES = [
    _capability(
        "gateway.create",
        [],
        "supported",
        [["az", "ai-gateway", "create"]],
        "safe-batch",
        "read-before-create",
        ["control-plane-read"],
        ["The destination resource group must already exist."],
    ),
    _capability(
        "model-provider.configure",
        ["apiConfiguration", "backendDependency", "backends"],
        "conditional",
        [
            ["az", "ai-gateway", "model-provider", "create"],
            ["az", "ai-gateway", "model-provider", "update"],
            ["az", "ai-gateway", "model-provider", "sync"],
        ],
        "consequential",
        "compare-before-update",
        ["control-plane-read", "data-plane-probe"],
        [
            "Endpoint, authentication, and model mapping decisions are required.",
            "Secrets must be supplied only at execution time.",
        ],
    ),
    _capability(
        "model.configure",
        ["apiConfiguration", "operation"],
        "conditional",
        [["az", "ai-gateway", "model", "create"]],
        "safe-batch",
        "read-before-create",
        ["control-plane-read", "data-plane-probe"],
        ["Only model-compatible APIM APIs have a destination representation."],
    ),
    _capability(
        "mcp.configure",
        ["apiConfiguration", "operation", "mcpTool"],
        "conditional",
        [
            ["az", "ai-gateway", "mcp", "create"],
            ["az", "ai-gateway", "mcp", "update"],
        ],
        "consequential",
        "compare-before-update",
        ["control-plane-read", "data-plane-probe"],
        [
            "MCP dependencies and endpoint semantics require explicit mapping.",
        ],
    ),
    _capability(
        "policy.configure",
        ["policyStatement", "policyFragments"],
        "conditional",
        [
            ["az", "ai-gateway", "policy", "create"],
            ["az", "ai-gateway", "policy", "update"],
        ],
        "consequential",
        "compare-before-update",
        ["control-plane-read", "data-plane-probe"],
        [
            "Each statement must be supported by the policy import registry.",
            "Reduced or omitted semantics require explicit residual handling.",
        ],
    ),
    _capability(
        "identity.configure",
        ["managedIdentity"],
        "conditional",
        [["az", "ai-gateway", "identity", "assign"]],
        "consequential",
        "compare-before-update",
        ["control-plane-read", "administrator-attestation"],
        ["Identity assignment does not grant required Azure RBAC roles."],
    ),
    _capability(
        "telemetry.configure",
        ["diagnostic", "diagnostics", "loggerReference", "loggers"],
        "conditional",
        [["az", "ai-gateway", "telemetry-exporter", "create"]],
        "consequential",
        "read-before-create",
        ["control-plane-read", "administrator-attestation"],
        [
            "Application Insights setup can grant RBAC and enable OTLP export.",
            "Replacing an existing exporter can overwrite destination settings.",
            "Logger credentials and unsupported diagnostic settings are residuals.",
        ],
    ),
    _capability(
        "relationship.unsupported",
        [
            "authorizationProviders",
            "certificates",
            "group",
            "groups",
            "identityProvider",
            "identityProviders",
            "namedValues",
            "productRelationship",
            "products",
            "subscriptionRelationship",
            "subscriptions",
        ],
        "unsupported",
        [],
        "none",
        "verify-only",
        ["accepted-residual"],
        [
            "AI Gateway has no equivalent APIM product, subscription, group, or "
            "identity-provider resource."
        ],
    ),
    _capability(
        "network.manual",
        ["networkConfiguration"],
        "unsupported",
        [],
        "none",
        "verify-only",
        ["administrator-attestation", "accepted-residual"],
        [
            "Network topology and private endpoint creation require a separate "
            "administrator workflow."
        ],
    ),
]


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value):
    return _DIGEST_PREFIX + hashlib.sha256(_canonical_json(value)).hexdigest()


def _jcs_number(value):
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise ValueError("JCS does not support non-finite numbers.")
    if value == 0:
        return "0"
    rendered = repr(value).lower()
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        fixed = format(Decimal(rendered), "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed
    if "e" not in rendered:
        rendered = format(value, ".15e")
    coefficient, exponent = rendered.split("e", 1)
    coefficient = coefficient.rstrip("0").rstrip(".")
    exponent_value = int(exponent)
    exponent_sign = "+" if exponent_value >= 0 else ""
    return f"{coefficient}e{exponent_sign}{exponent_value}"


def _jcs_canonical_json(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _jcs_number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_jcs_canonical_json(item) for item in value) + "]"
    if isinstance(value, dict):
        ordered_keys = sorted(
            value,
            key=lambda key: key.encode("utf-16-be", "surrogatepass"),
        )
        return (
            "{"
            + ",".join(
                (
                    json.dumps(
                        key,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + ":"
                    + _jcs_canonical_json(value[key])
                )
                for key in ordered_keys
            )
            + "}"
        )
    raise ValueError(f"Unsupported JCS value type: {type(value).__name__}")


def _jcs_digest(value):
    try:
        payload = _jcs_canonical_json(value).encode("utf-8")
    except (UnicodeEncodeError, ValueError):
        return None
    return _DIGEST_PREFIX + hashlib.sha256(payload).hexdigest()


def show_migration_capability():
    result = {
        "schemaVersion": CAPABILITY_SCHEMA_VERSION,
        "contractVersion": CAPABILITY_CONTRACT_VERSION,
        "kind": "AiGatewayMigrationCapabilityContract",
        "generatedBy": {
            "extension": "ai-gateway",
            "command": "az ai-gateway migration-capability show",
        },
        "sourceConstraints": {
            "supportedSkus": _SUPPORTED_SOURCE_SKUS,
            "requiredProvisioningState": "Succeeded",
        },
        "capabilities": sorted(
            deepcopy(_CAPABILITIES),
            key=lambda item: item["id"],
        ),
    }
    result["contractDigest"] = _digest(result)
    return result


def format_migration_capability_table(result):
    return [
        {
            "Capability": item["id"],
            "Support": item["support"],
            "Approval": item["approvalClass"],
            "Behaviors": ",".join(item["sourceBehaviorTypes"]),
        }
        for item in result.get("capabilities", [])
    ]


def _load_document(value, option_name):
    try:
        if hasattr(value, "read"):
            payload = json.load(value)
        else:
            path = Path(value)
            if path.is_symlink():
                raise InvalidArgumentValueError(
                    f"{option_name} must not identify a symbolic link."
                )
            with path.open(encoding="utf-8-sig") as stream:
                payload = json.load(stream)
    except InvalidArgumentValueError:
        raise
    except OSError as error:
        raise FileOperationError(
            f"Unable to read {option_name}: {error}"
        ) from error
    except (TypeError, ValueError) as error:
        raise InvalidArgumentValueError(
            f"{option_name} must contain a JSON object: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidArgumentValueError(
            f"{option_name} must contain a JSON object."
        )
    return payload


def _without_runtime_state(value):
    if isinstance(value, dict):
        return {
            key: _without_runtime_state(item)
            for key, item in sorted(value.items())
            if key not in _RUNTIME_KEYS
        }
    if isinstance(value, list):
        return [_without_runtime_state(item) for item in value]
    return value


def _plan_projection(mapping, todos):
    mapped = deepcopy(mapping)
    todo_plan = deepcopy(todos)
    todo_plan.pop("planDigest", None)
    todo_plan.pop("validation", None)
    for item in mapped.get("items", []):
        if not isinstance(item, dict):
            continue
        for decision in item.get("decisions", []):
            if isinstance(decision, dict):
                decision.pop("decidedAt", None)
        residual = item.get("residual")
        if isinstance(residual, dict):
            residual.pop("acceptanceDecisionId", None)
            residual.pop("acceptancePlanDigest", None)
            if residual.get("status") in {"accepted", "rejected"}:
                residual["status"] = "pending-acceptance"
        verification = item.get("verification")
        if isinstance(verification, dict):
            verification.pop("status", None)
            verification.pop("evidenceDigest", None)
    for item in todo_plan.get("items", []):
        if not isinstance(item, dict):
            continue
        item.pop("status", None)
        item.pop("approval", None)
        item.pop("attempts", None)
        precondition = item.get("precondition")
        if isinstance(precondition, dict):
            precondition.pop("status", None)
        verification = item.get("verification")
        if isinstance(verification, dict):
            resource = verification.get("resource")
            if isinstance(resource, dict):
                resource.pop("observedStateDigest", None)
                resource.pop("status", None)
                resource.pop("evidence", None)
            for behavior in verification.get("behaviors", []):
                if isinstance(behavior, dict):
                    behavior.pop("observedDigest", None)
                    behavior.pop("status", None)
                    behavior.pop("evidence", None)
    return _without_runtime_state({"mapping": mapped, "todos": todo_plan})


def _issue(code, path, message):
    return {"code": code, "path": path, "message": message}


def _is_digest(value):
    if not isinstance(value, str) or not value.startswith(_DIGEST_PREFIX):
        return False
    digest = value[len(_DIGEST_PREFIX) :]
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _is_runtime_placeholder(value):
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return (
        not stripped
        or stripped.casefold() in {"<redacted>", "[redacted]", "redacted"}
        or stripped == "***"
        or _RUNTIME_SECRET.fullmatch(stripped) is not None
    )


def _contains_credential_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.username is not None or parsed.password is not None:
        return True
    sensitive_query_names = {
        "access_token",
        "api-key",
        "apikey",
        "code",
        "credential",
        "key",
        "password",
        "secret",
        "sig",
        "signature",
        "token",
    }
    return any(
        name.casefold() in sensitive_query_names
        and not _is_runtime_placeholder(query_value)
        for name, query_value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
    )


def _check_persisted_secrets(value, path, errors):
    sensitive_fields = {
        "accesstoken",
        "apikey",
        "apikeyvalue",
        "authorizationheader",
        "clientsecret",
        "connectionstring",
        "password",
        "primarykey",
        "refreshtoken",
        "secondarykey",
        "secret",
        "token",
    }
    sensitive_options = {
        "--access-token",
        "--api-key-value",
        "--client-secret",
        "--connection-string",
        "--headers",
        "--password",
        "--secret",
        "--token",
    }
    if isinstance(value, dict):
        if value.get("secret") is True and not _is_runtime_placeholder(
            value.get("value")
        ):
            errors.append(
                _issue(
                    "persisted-secret",
                    f"{path}/value",
                    "Secret values must not be persisted in migration state.",
                )
            )
        for key, item in value.items():
            child_path = f"{path}/{key}"
            normalized_key = re.sub(r"[-_]", "", key.casefold())
            if (
                normalized_key in sensitive_fields
                and not (
                    normalized_key == "secret"
                    and isinstance(item, bool)
                )
                and not _is_runtime_placeholder(item)
            ):
                errors.append(
                    _issue(
                        "persisted-secret",
                        child_path,
                        (
                            "Credential values must be supplied only at "
                            "runtime."
                        ),
                    )
                )
            _check_persisted_secrets(item, child_path, errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if (
                isinstance(item, str)
                and item in sensitive_options
                and index + 1 < len(value)
                and not (
                    _is_runtime_placeholder(value[index + 1])
                    or (
                        item == "--headers"
                        and isinstance(value[index + 1], str)
                        and _RUNTIME_SECRET_REFERENCE.search(
                            value[index + 1]
                        )
                    )
                )
            ):
                errors.append(
                    _issue(
                        "persisted-secret",
                        f"{path}/{index + 1}",
                        (
                            "Secret command arguments must use a runtime "
                            "placeholder."
                        ),
                    )
                )
            _check_persisted_secrets(item, f"{path}/{index}", errors)
    elif _contains_credential_url(value):
        errors.append(
            _issue(
                "persisted-secret",
                path,
                (
                    "Credential-bearing URLs must use redacted runtime "
                    "secret references."
                ),
            )
        )


def _check_document_version(document, name, errors):
    if document.get("schemaVersion") != "2.0":
        errors.append(
            _issue(
                "unsupported-schema-version",
                f"/{name}/schemaVersion",
                f"{name} schemaVersion must be '2.0'.",
            )
        )


def _check_generation(context, mapping, todos, errors):
    values = {
        "context": context.get("generationId"),
        "mapping": mapping.get("generationId"),
        "todos": todos.get("generationId"),
    }
    if len(set(values.values())) != 1 or None in values.values():
        errors.append(
            _issue(
                "generation-mismatch",
                "/generationId",
                "context, mapping, and todos must use one generationId.",
            )
        )


def _check_source_inventory(
    source_inventory,
    context,
    mapping,
    errors,
    warnings,
):
    if source_inventory.get("schemaVersion") != "3.0":
        errors.append(
            _issue(
                "unsupported-inventory-schema-version",
                "/sourceInventory/schemaVersion",
                "Source inventory schemaVersion must be '3.0'.",
            )
        )
    if source_inventory.get("kind") != "AiGatewayApimImportInventory":
        errors.append(
            _issue(
                "invalid-inventory-kind",
                "/sourceInventory/kind",
                (
                    "Source inventory kind must be "
                    "AiGatewayApimImportInventory."
                ),
            )
        )
    source = source_inventory.get("source")
    if not isinstance(source, dict):
        errors.append(
            _issue(
                "invalid-inventory-source",
                "/sourceInventory/source",
                "Source inventory must identify the APIM source.",
            )
        )
        source = {}
    context_source = context.get("source") or {}
    source_id = str(source.get("id") or "").rstrip("/")
    expected_source_id = str(
        context_source.get("resourceId") or ""
    ).rstrip("/")
    if not source_id or source_id.casefold() != expected_source_id.casefold():
        errors.append(
            _issue(
                "source-resource-mismatch",
                "/context/source/resourceId",
                "Context source resource ID does not match source inventory.",
            )
        )
    source_subscription = ""
    source_id_parts = source_id.split("/")
    if len(source_id_parts) > 2 and source_id_parts[1].casefold() == "subscriptions":
        source_subscription = source_id_parts[2]
    if (
        not source_subscription
        or source_subscription.casefold()
        != str(context_source.get("subscriptionId") or "").casefold()
    ):
        errors.append(
            _issue(
                "source-subscription-mismatch",
                "/context/source/subscriptionId",
                "Context source subscription does not match source inventory.",
            )
        )
    for field in ("sku", "provisioningState", "targetProvisioningState"):
        if context_source.get(field) != source.get(field):
            errors.append(
                _issue(
                    "source-property-mismatch",
                    f"/context/source/{field}",
                    (
                        f"Context source {field} does not match source "
                        "inventory."
                    ),
                )
            )
    source_sku = source.get("sku")
    if source_sku not in _SUPPORTED_SOURCE_SKUS:
        errors.append(
            _issue(
                "unsupported-source-sku",
                "/sourceInventory/source/sku",
                (
                    "Source SKU must be BasicV2, StandardV2, or PremiumV2."
                ),
            )
        )
    if str(source.get("provisioningState") or "").casefold() != "succeeded":
        errors.append(
            _issue(
                "source-not-ready",
                "/sourceInventory/source/provisioningState",
                "Source provisioning state must be Succeeded.",
            )
        )
    compatibility = source.get("migrationCompatibility") or {}
    if (
        compatibility.get("supportedV2Sku") is not True
        or compatibility.get("skuFamily") != "v2"
    ):
        errors.append(
            _issue(
                "invalid-source-capability-evidence",
                "/sourceInventory/source/migrationCompatibility",
                "Source inventory does not prove supported V2 SKU capability.",
            )
        )
    coverage = source_inventory.get("collectionCoverage")
    if not isinstance(coverage, list) or not coverage:
        errors.append(
            _issue(
                "missing-collection-coverage",
                "/sourceInventory/collectionCoverage",
                "Source inventory requires collection coverage records.",
            )
        )
        coverage = []
    allowed_coverage_statuses = {"complete", "empty", "notApplicable"}
    gap_mappings = {
        item.get("id"): item
        for item in mapping.get("items", [])
        if isinstance(item, dict)
        if item.get("recordType") == "coverage-gap"
    }
    for index, record in enumerate(coverage):
        path = f"/sourceInventory/collectionCoverage/{index}"
        if not isinstance(record, dict):
            errors.append(
                _issue(
                    "invalid-collection-coverage",
                    path,
                    "Each collection coverage record must be a JSON object.",
                )
            )
            continue
        status = record.get("status")
        if status not in allowed_coverage_statuses:
            errors.append(
                _issue(
                    "incomplete-collection-coverage",
                    f"{path}/status",
                    (
                        "Partial or failed collection coverage cannot "
                        "establish migration completeness or absence."
                    ),
                )
            )
            gap_id = (
                f"coverage-gap:{record.get('scope')}:"
                f"{record.get('configurationDomain')}"
            )
            disposition = gap_mappings.get(gap_id)
            if disposition is None or disposition.get(
                "classification"
            ) != "needs-input":
                errors.append(
                    _issue(
                        "missing-coverage-gap-mapping",
                        path,
                        (
                            f"Coverage gap '{gap_id}' requires an exact "
                            "needs-input mapping record."
                        ),
                    )
                )
        if (
            "/workspaces/" in str(record.get("scope") or "").casefold()
            and record.get("configurationDomain") == "mcpTools"
            and status != "notApplicable"
        ):
            errors.append(
                _issue(
                    "invalid-workspace-mcp-coverage",
                    f"{path}/status",
                    "Workspace MCP coverage must be notApplicable.",
                )
            )
    scopes = source_inventory.get("scopes")
    if not isinstance(scopes, list):
        errors.append(
            _issue(
                "invalid-inventory-scopes",
                "/sourceInventory/scopes",
                "Source inventory scopes must be an array.",
            )
        )
        scopes = []
    if not any(
        isinstance(scope, dict) and scope.get("scopeType") == "service"
        for scope in scopes
    ):
        errors.append(
            _issue(
                "missing-service-scope",
                "/sourceInventory/scopes",
                "Source inventory must include the APIM service scope.",
            )
        )
    workspace_count = sum(
        isinstance(scope, dict) and scope.get("scopeType") == "workspace"
        for scope in scopes
    )
    inventory_summary = source_inventory.get("summary") or {}
    has_conflicts = bool(
        (source_inventory.get("provenance") or {}).get("conflicts")
    )
    recomputed_complete = not has_conflicts and all(
        isinstance(record, dict)
        and record.get("status") in allowed_coverage_statuses
        for record in coverage
    )
    recomputed_required_complete = not has_conflicts and all(
        not isinstance(record, dict)
        or record.get("requiredForEnumeration", True) is False
        or record.get("status") in allowed_coverage_statuses
        for record in coverage
    )
    expected_inventory_status = (
        "complete" if recomputed_complete else "partial"
    )
    if inventory_summary.get("inventoryStatus") != expected_inventory_status:
        errors.append(
            _issue(
                "inventory-summary-mismatch",
                "/sourceInventory/summary/inventoryStatus",
                (
                    "Inventory status must be derived from collection "
                    "coverage."
                ),
            )
        )
    if (
        inventory_summary.get("requiredDiscoveryComplete")
        is not recomputed_required_complete
    ):
        errors.append(
            _issue(
                "inventory-summary-mismatch",
                "/sourceInventory/summary/requiredDiscoveryComplete",
                (
                    "Required discovery completeness must be derived from "
                    "required collection coverage."
                ),
            )
        )
    if inventory_summary.get("workspaceCount") != workspace_count:
        errors.append(
            _issue(
                "workspace-count-mismatch",
                "/sourceInventory/summary/workspaceCount",
                "Workspace summary does not match observed scopes.",
            )
        )
    normalized_coverage_scopes = [
        str(record.get("scope") or "").rstrip("/").casefold()
        for record in coverage
        if isinstance(record, dict)
    ]
    for index, scope in enumerate(scopes):
        if not isinstance(scope, dict):
            continue
        scope_id = str(scope.get("id") or "").rstrip("/").casefold()
        if not scope_id or not any(
            covered_scope == scope_id
            or covered_scope.startswith(scope_id + "/")
            for covered_scope in normalized_coverage_scopes
        ):
            errors.append(
                _issue(
                    "scope-coverage-missing",
                    f"/sourceInventory/scopes/{index}",
                    (
                        "Every service and workspace scope must have "
                        "collection coverage evidence."
                    ),
                )
            )
    apis = source_inventory.get("apis")
    if not isinstance(apis, list):
        errors.append(
            _issue(
                "invalid-inventory-apis",
                "/sourceInventory/apis",
                "Source inventory APIs must be an array.",
            )
        )
        apis = []
    if inventory_summary.get("apiCount") != len(apis):
        errors.append(
            _issue(
                "api-count-mismatch",
                "/sourceInventory/summary/apiCount",
                "API summary does not match observed representative assets.",
            )
        )
    source_digest = _digest(source_inventory)
    if mapping.get("sourceInventoryDigest") != source_digest:
        errors.append(
            _issue(
                "source-inventory-digest-mismatch",
                "/mapping/sourceInventoryDigest",
                (
                    "Mapping source inventory digest does not match "
                    "--source-inventory-file."
                ),
            )
        )
    context_inventory = context.get("sourceInventory") or {}
    if (
        context_inventory.get("schemaVersion") != "3.0"
        or context_inventory.get("kind")
        != "AiGatewayApimImportInventory"
    ):
        errors.append(
            _issue(
                "invalid-context-inventory",
                "/context/sourceInventory",
                "Context must bind a schema 3.0 APIM import inventory.",
            )
        )
    if context_inventory.get("artifactDigest") != source_digest:
        errors.append(
            _issue(
                "source-inventory-digest-mismatch",
                "/context/sourceInventory/artifactDigest",
                (
                    "Context source inventory digest does not match "
                    "--source-inventory-file."
                ),
            )
        )
    ledger = source_inventory.get("sourceBehaviorLedger")
    if not isinstance(ledger, list):
        errors.append(
            _issue(
                "invalid-source-behavior-ledger",
                "/sourceInventory/sourceBehaviorLedger",
                "sourceBehaviorLedger must be an array.",
            )
        )
        ledger = []
    ledger_by_id = {}
    for index, behavior in enumerate(ledger):
        path = f"/sourceInventory/sourceBehaviorLedger/{index}"
        if not isinstance(behavior, dict):
            errors.append(
                _issue(
                    "invalid-source-behavior",
                    path,
                    "Each source behavior must be a JSON object.",
                )
            )
            continue
        behavior_id = behavior.get("id")
        if not isinstance(behavior_id, str) or not behavior_id:
            errors.append(
                _issue(
                    "missing-source-behavior-id",
                    f"{path}/id",
                    "Source behavior ID is required.",
                )
            )
        elif behavior_id in ledger_by_id:
            errors.append(
                _issue(
                    "duplicate-source-behavior-id",
                    f"{path}/id",
                    f"Duplicate source behavior ID '{behavior_id}'.",
                )
            )
        else:
            ledger_by_id[behavior_id] = behavior
    provenance = source_inventory.get("provenance")
    if not isinstance(provenance, dict):
        errors.append(
            _issue(
                "invalid-provenance",
                "/sourceInventory/provenance",
                "Source inventory provenance must be a JSON object.",
            )
        )
        provenance = {}
    provenance_digest = _digest(provenance)
    if context_inventory.get("provenanceDigest") != provenance_digest:
        errors.append(
            _issue(
                "provenance-digest-mismatch",
                "/context/sourceInventory/provenanceDigest",
                "Context provenance digest does not match source inventory.",
            )
        )
    conflicts = provenance.get("conflicts", [])
    if not isinstance(conflicts, list):
        errors.append(
            _issue(
                "invalid-provenance-conflicts",
                "/sourceInventory/provenance/conflicts",
                "provenance.conflicts must be an array.",
            )
        )
        conflicts = []
    conflict_mappings = {
        stable_id: item
        for item in mapping.get("items", [])
        if isinstance(item, dict)
        if item.get("recordType") == "provenance-conflict"
        for stable_id in item.get("sourceStableIds", [])
    }
    for index, conflict in enumerate(conflicts):
        path = f"/sourceInventory/provenance/conflicts/{index}"
        if not isinstance(conflict, dict):
            errors.append(
                _issue(
                    "invalid-provenance-conflict",
                    path,
                    "Each provenance conflict must be a JSON object.",
                )
            )
            continue
        stable_id = conflict.get("stableId")
        disposition = conflict_mappings.get(stable_id)
        if disposition is None:
            errors.append(
                _issue(
                    "undisposed-provenance-conflict",
                    path,
                    (
                        f"Provenance conflict '{stable_id}' requires a "
                        "needs-input mapping record."
                    ),
                )
            )
        elif (
            disposition.get("classification") != "needs-input"
            or disposition.get("authority") != "conflicted"
        ):
            errors.append(
                _issue(
                    "invalid-provenance-conflict-disposition",
                    f"/mapping/items/{disposition.get('id', stable_id)}",
                    (
                        "Provenance conflicts must remain needs-input with "
                        "conflicted authority until resolved."
                    ),
                )
            )
    provenance_warnings = provenance.get("warnings", [])
    if not isinstance(provenance_warnings, list):
        errors.append(
            _issue(
                "invalid-provenance-warnings",
                "/sourceInventory/provenance/warnings",
                "provenance.warnings must be an array.",
            )
        )
    elif provenance_warnings:
        warnings.append(
            _issue(
                "source-provenance-warnings",
                "/sourceInventory/provenance/warnings",
                (
                    f"Source inventory contains {len(provenance_warnings)} "
                    "provenance warning(s)."
                ),
            )
        )
    behavior_ledger_digest = _digest(ledger)
    if (
        context_inventory.get("behaviorLedgerDigest")
        != behavior_ledger_digest
    ):
        errors.append(
            _issue(
                "behavior-ledger-digest-mismatch",
                "/context/sourceInventory/behaviorLedgerDigest",
                (
                    "Context behavior-ledger digest does not match source "
                    "inventory."
                ),
            )
        )
    inventory_status = (source_inventory.get("summary") or {}).get(
        "inventoryStatus"
    )
    if context_inventory.get("inventoryStatus") != inventory_status:
        errors.append(
            _issue(
                "inventory-status-mismatch",
                "/context/sourceInventory/inventoryStatus",
                "Context inventory status does not match source inventory.",
            )
        )
    if context_inventory.get("authority") not in _AUTHORITIES:
        errors.append(
            _issue(
                "invalid-inventory-authority",
                "/context/sourceInventory/authority",
                "Context inventory authority is not recognized.",
            )
        )
    if context_inventory.get("authoritativeForAbsence") is True and (
        inventory_status != "complete"
        or not recomputed_required_complete
        or not (source_inventory.get("summary") or {}).get(
            "requiredDiscoveryComplete"
        )
        or conflicts
    ):
        errors.append(
            _issue(
                "invalid-absence-authority",
                "/context/sourceInventory/authoritativeForAbsence",
                (
                    "Partial, conflicted, or incomplete inventory cannot "
                    "establish absence."
                ),
            )
        )
    return source_digest, ledger_by_id, source_sku


def _capabilities_by_id():
    contract = show_migration_capability()
    return contract, {
        item["id"]: item for item in contract["capabilities"]
    }


def _check_mapping(
    mapping,
    ledger_by_id,
    source_sku,
    capability_digest,
    capabilities,
    plan_digest,
    errors,
    warnings,
):
    mapping_ids = set()
    behavior_owners = {}
    for index, item in enumerate(mapping.get("items", [])):
        path = f"/mapping/items/{index}"
        if not isinstance(item, dict):
            errors.append(
                _issue(
                    "invalid-mapping-item",
                    path,
                    "Each mapping item must be a JSON object.",
                )
            )
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(
                _issue(
                    "missing-mapping-id",
                    f"{path}/id",
                    "Mapping ID is required.",
                )
            )
        elif item_id in mapping_ids:
            errors.append(
                _issue(
                    "duplicate-mapping-id",
                    f"{path}/id",
                    f"Duplicate mapping ID '{item_id}'.",
                )
            )
        else:
            mapping_ids.add(item_id)
        classification = item.get("classification")
        if classification not in {"ready", "needs-input", "cannot-import"}:
            errors.append(
                _issue(
                    "invalid-classification",
                    f"{path}/classification",
                    (
                        "Classification must be ready, needs-input, or "
                        "cannot-import."
                    ),
                )
            )
        if item.get("authority") not in _AUTHORITIES:
            errors.append(
                _issue(
                    "invalid-authority",
                    f"{path}/authority",
                    "Mapping authority is not recognized.",
                )
            )
        if (
            classification == "ready"
            and item.get("authority") not in _READY_AUTHORITIES
        ):
            errors.append(
                _issue(
                    "insufficient-authority",
                    f"{path}/authority",
                    (
                        "Ready mappings require authoritative or corroborated "
                        "evidence."
                    ),
                )
            )
        if (
            item.get("recordType") in {"coverage-gap", "provenance-conflict"}
            and classification != "needs-input"
        ):
            errors.append(
                _issue(
                    "unresolved-source-evidence",
                    f"{path}/classification",
                    (
                        "Coverage gaps and provenance conflicts must remain "
                        "needs-input until resolved."
                    ),
                )
            )
        behavior_ids = item.get("sourceBehaviorIds", [])
        if not isinstance(behavior_ids, list):
            errors.append(
                _issue(
                    "invalid-source-behaviors",
                    f"{path}/sourceBehaviorIds",
                    "sourceBehaviorIds must be an array.",
                )
            )
            behavior_ids = []
        for behavior_id in behavior_ids:
            behavior_owners.setdefault(behavior_id, []).append(item_id or path)
            if behavior_id not in ledger_by_id:
                errors.append(
                    _issue(
                        "unknown-source-behavior",
                        f"{path}/sourceBehaviorIds",
                        (
                            f"Source behavior '{behavior_id}' is not in "
                            "sourceBehaviorLedger."
                        ),
                    )
                )
        source_evidence = item.get("sourceEvidence", [])
        if not isinstance(source_evidence, list) or not source_evidence:
            errors.append(
                _issue(
                    "missing-source-evidence",
                    f"{path}/sourceEvidence",
                    "Each mapping requires source evidence.",
                )
            )
            source_evidence = []
        evidence_authorities = set()
        for evidence_index, evidence in enumerate(source_evidence):
            evidence_path = f"{path}/sourceEvidence/{evidence_index}"
            if not isinstance(evidence, dict):
                errors.append(
                    _issue(
                        "invalid-source-evidence",
                        evidence_path,
                        "Source evidence must be a JSON object.",
                    )
                )
                continue
            evidence_authorities.add(evidence.get("authority"))
            if evidence.get("authority") not in _AUTHORITIES:
                errors.append(
                    _issue(
                        "invalid-source-evidence-authority",
                        f"{evidence_path}/authority",
                        "Source evidence authority is not recognized.",
                    )
                )
            for field in ("sourceKind", "artifactId"):
                if (
                    not isinstance(evidence.get(field), str)
                    or not evidence.get(field)
                ):
                    errors.append(
                        _issue(
                            "incomplete-source-evidence",
                            f"{evidence_path}/{field}",
                            f"Source evidence requires {field}.",
                        )
                    )
            if not isinstance(evidence.get("jsonPointer"), str):
                errors.append(
                    _issue(
                        "incomplete-source-evidence",
                        f"{evidence_path}/jsonPointer",
                        "Source evidence requires a JSON pointer.",
                    )
                )
            if not _is_digest(evidence.get("evidenceDigest")):
                errors.append(
                    _issue(
                        "invalid-source-evidence-digest",
                        f"{evidence_path}/evidenceDigest",
                        "Source evidence requires a sha256 digest.",
                    )
                )
        if (
            classification == "ready"
            and not evidence_authorities.intersection(_READY_AUTHORITIES)
        ):
            errors.append(
                _issue(
                    "insufficient-source-evidence",
                    f"{path}/sourceEvidence",
                    (
                        "Ready mappings require authoritative or corroborated "
                        "source evidence."
                    ),
                )
            )
        evidence_values = item.get("capabilityEvidence", [])
        if not isinstance(evidence_values, list) or not evidence_values:
            errors.append(
                _issue(
                    "missing-capability-evidence",
                    f"{path}/capabilityEvidence",
                    "Each mapping requires capability evidence.",
                )
            )
            evidence_values = []
        covered_behavior_types = set()
        for evidence_index, evidence in enumerate(evidence_values):
            evidence_path = f"{path}/capabilityEvidence/{evidence_index}"
            if not isinstance(evidence, dict):
                errors.append(
                    _issue(
                        "invalid-capability-evidence",
                        evidence_path,
                        "Capability evidence must be a JSON object.",
                    )
                )
                continue
            if evidence.get("contractDigest") != capability_digest:
                errors.append(
                    _issue(
                        "capability-digest-mismatch",
                        f"{evidence_path}/contractDigest",
                        (
                            "Capability evidence does not match the installed "
                            "contract."
                        ),
                    )
                )
            capability_id = evidence.get("capabilityId")
            capability = capabilities.get(capability_id)
            if capability is None:
                errors.append(
                    _issue(
                        "unknown-capability",
                        f"{evidence_path}/capabilityId",
                        (
                            f"Capability '{capability_id}' is not in the "
                            "installed contract."
                        ),
                    )
                )
            else:
                covered_behavior_types.update(
                    capability["sourceBehaviorTypes"]
                )
                if source_sku not in capability["supportedSourceSkus"]:
                    errors.append(
                        _issue(
                            "capability-sku-mismatch",
                            f"{evidence_path}/capabilityId",
                            (
                                f"Capability '{capability_id}' does not "
                                f"support source SKU '{source_sku}'."
                            ),
                        )
                    )
            if capability is not None and evidence.get(
                "support"
            ) != capability["support"]:
                errors.append(
                    _issue(
                        "capability-support-mismatch",
                        f"{evidence_path}/support",
                        (
                            "Capability evidence support does not match the "
                            "installed contract."
                        ),
                    )
                )
            elif capability is not None and evidence.get(
                "destinationCommands"
            ) != capability[
                "destinationCommands"
            ]:
                errors.append(
                    _issue(
                        "capability-commands-mismatch",
                        f"{evidence_path}/destinationCommands",
                        (
                            "Capability evidence commands do not match the "
                            "installed contract."
                        ),
                    )
                )
            elif capability is not None and evidence.get(
                "limitations"
            ) != capability["limitations"]:
                errors.append(
                    _issue(
                        "capability-limitations-mismatch",
                        f"{evidence_path}/limitations",
                        (
                            "Capability evidence limitations do not match the "
                            "installed contract."
                        ),
                    )
                )
            if classification == "ready" and evidence.get("support") not in {
                "supported",
                "conditional",
            }:
                errors.append(
                    _issue(
                        "unsupported-ready-mapping",
                        f"{evidence_path}/support",
                        (
                            "Ready mappings require supported or conditional "
                            "capability evidence."
                        ),
                    )
                )
        for behavior_id in behavior_ids:
            behavior = ledger_by_id.get(behavior_id) or {}
            behavior_type = behavior.get("behaviorType")
            if (
                behavior_type
                and behavior_type not in covered_behavior_types
            ):
                errors.append(
                    _issue(
                        "capability-behavior-mismatch",
                        f"{path}/capabilityEvidence",
                        (
                            f"No cited capability covers behavior type "
                            f"'{behavior_type}'."
                        ),
                    )
                )
        residual = item.get("residual") or {}
        if not isinstance(residual, dict):
            errors.append(
                _issue(
                    "invalid-residual",
                    f"{path}/residual",
                    "Residual state must be a JSON object.",
                )
            )
            residual = {}
        residual_status = residual.get("status")
        if classification == "ready" and residual_status != "none":
            errors.append(
                _issue(
                    "ready-mapping-has-residual",
                    f"{path}/residual/status",
                    "Ready mappings cannot carry residual work.",
                )
            )
        if classification == "cannot-import" and residual_status not in {
            "pending-acceptance",
            "accepted",
            "rejected",
        }:
            errors.append(
                _issue(
                    "missing-residual",
                    f"{path}/residual/status",
                    "Cannot-import mappings require an explicit residual.",
                )
            )
        if residual_status != "none" and any(
            not isinstance(residual.get(field), str)
            or not residual.get(field).strip()
            for field in ("reason", "impact", "remediation")
        ):
            errors.append(
                _issue(
                    "incomplete-residual",
                    f"{path}/residual",
                    "Residuals require reason, impact, and remediation.",
                )
            )
        if residual_status in {"accepted", "rejected"} and residual.get(
            "acceptancePlanDigest"
        ) != plan_digest:
            errors.append(
                _issue(
                    "stale-residual-decision",
                    f"{path}/residual/acceptancePlanDigest",
                    (
                        "Residual decisions must bind to the current plan "
                        "digest."
                    ),
                )
            )
        decisions = item.get("decisions", [])
        if not isinstance(decisions, list):
            decisions = []
        acceptance_decision_id = residual.get("acceptanceDecisionId")
        if residual_status in {"accepted", "rejected"} and not any(
            isinstance(decision, dict)
            and decision.get("id") == acceptance_decision_id
            and decision.get("type") == "residual-acceptance"
            and decision.get("decidedAt")
            for decision in decisions
        ):
            errors.append(
                _issue(
                    "missing-residual-decision",
                    f"{path}/decisions",
                    (
                        "Accepted or rejected residuals require a matching "
                        "timestamped residual-acceptance decision."
                    ),
                )
            )
        if residual_status in {"accepted", "rejected"} and any(
            not isinstance(residual.get(field), str)
            or not residual.get(field).strip()
            for field in (
                "reason",
                "impact",
                "remediation",
                "acceptanceDecisionId",
            )
        ):
            errors.append(
                _issue(
                    "incomplete-residual-decision",
                    f"{path}/residual",
                    (
                        "Accepted or rejected residuals require reason, "
                        "impact, remediation, and acceptanceDecisionId."
                    ),
                )
            )
        if classification == "needs-input":
            errors.append(
                _issue(
                    "mapping-needs-input",
                    path,
                    (
                        f"Mapping '{item_id or index}' still requires "
                        "administrator input."
                    ),
                )
            )
        if residual_status in {"pending-acceptance", "rejected"}:
            errors.append(
                _issue(
                    "unaccepted-residual",
                    f"{path}/residual/status",
                    (
                        "Residuals must be explicitly accepted against the "
                        "current plan before approval or execution."
                    ),
                )
            )
    for behavior_id, owners in behavior_owners.items():
        if len(owners) > 1:
            errors.append(
                _issue(
                    "duplicate-behavior-mapping",
                    "/mapping/items",
                    (
                        f"Source behavior '{behavior_id}' is referenced by "
                        "multiple mappings."
                    ),
                )
            )
    for behavior_id in sorted(set(ledger_by_id) - set(behavior_owners)):
        errors.append(
            _issue(
                "unmapped-source-behavior",
                "/mapping/items",
                (
                    f"Source behavior '{behavior_id}' is not represented by "
                    "a mapping or explicit residual."
                ),
            )
        )
    _check_mapping_dependencies(mapping, errors)
    return mapping_ids


def _check_dependency_graph(items, root, entity, errors):
    item_ids = {
        item.get("id")
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    edges = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        path = f"/{root}/items/{index}"
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list):
            errors.append(
                _issue(
                    "invalid-dependencies",
                    f"{path}/dependencies",
                    "dependencies must be an array.",
                )
            )
            dependencies = []
        valid_dependencies = [
            dependency
            for dependency in dependencies
            if isinstance(dependency, str)
        ]
        if item_id in valid_dependencies:
            errors.append(
                _issue(
                    "self-dependency",
                    f"{path}/dependencies",
                    f"{entity} '{item_id}' depends on itself.",
                )
            )
        missing = sorted(set(valid_dependencies) - item_ids)
        for dependency in missing:
            errors.append(
                _issue(
                    "missing-dependency",
                    f"{path}/dependencies",
                    f"{entity} dependency '{dependency}' was not found.",
                )
            )
        if isinstance(item_id, str):
            edges[item_id] = [
                dependency
                for dependency in valid_dependencies
                if dependency in item_ids
            ]
    visiting = set()
    visited = set()

    def visit(item_id):
        if item_id in visiting:
            return True
        if item_id in visited:
            return False
        visiting.add(item_id)
        if any(visit(dependency) for dependency in edges.get(item_id, [])):
            return True
        visiting.remove(item_id)
        visited.add(item_id)
        return False

    if any(visit(item_id) for item_id in sorted(edges)):
        errors.append(
            _issue(
                "dependency-cycle",
                f"/{root}/items",
                f"{entity} dependencies must be acyclic.",
            )
        )


def _check_mapping_dependencies(mapping, errors):
    _check_dependency_graph(
        mapping.get("items", []),
        "mapping",
        "Mapping",
        errors,
    )


def _check_dependencies(todos, errors):
    _check_dependency_graph(
        todos.get("items", []),
        "todos",
        "TODO",
        errors,
    )


def _command_prefix(command):
    if not isinstance(command, list):
        return None
    return tuple(command[:4])


def _is_safe_precondition_command(command):
    if (
        not isinstance(command, list)
        or not all(isinstance(value, str) for value in command)
        or command[:2] != ["az", "ai-gateway"]
    ):
        return False
    option_index = next(
        (
            index
            for index, value in enumerate(command[2:], start=2)
            if value.startswith("-")
        ),
        len(command),
    )
    command_path = tuple(command[2:option_index])
    safe_paths = {
        ("show",),
        ("list",),
        ("model", "show"),
        ("model", "list"),
        ("model-provider", "show"),
        ("model-provider", "list"),
        ("mcp", "show"),
        ("mcp", "list"),
        ("api-key", "show"),
        ("api-key", "list"),
        ("identity", "show"),
        ("private-endpoint", "show"),
        ("private-endpoint", "list"),
        ("telemetry-exporter", "list"),
        ("policy", "show"),
        ("policy", "list"),
        ("migration-capability", "show"),
    }
    if command_path == ("model-provider", "sync"):
        return "--dry-run" in command
    return command_path in safe_paths


def _check_todos(
    todos,
    mapping_ids,
    mappings_by_id,
    ledger_by_id,
    capabilities,
    plan_digest,
    errors,
    warnings,
):
    todo_ids = set()
    ready_behaviors = set()
    for index, item in enumerate(todos.get("items", [])):
        path = f"/todos/items/{index}"
        if not isinstance(item, dict):
            errors.append(
                _issue(
                    "invalid-todo-item",
                    path,
                    "Each TODO item must be a JSON object.",
                )
            )
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(
                _issue(
                    "missing-todo-id",
                    f"{path}/id",
                    "TODO ID is required.",
                )
            )
        elif item_id in todo_ids:
            errors.append(
                _issue(
                    "duplicate-todo-id",
                    f"{path}/id",
                    f"Duplicate TODO ID '{item_id}'.",
                )
            )
        else:
            todo_ids.add(item_id)
        if item.get("mappingId") not in mapping_ids:
            errors.append(
                _issue(
                    "unknown-mapping",
                    f"{path}/mappingId",
                    "TODO mappingId was not found in mapping.json.",
                )
            )
        command = item.get("commandTemplate")
        if not isinstance(command, list) or command[:2] != ["az", "ai-gateway"]:
            errors.append(
                _issue(
                    "forbidden-command",
                    f"{path}/commandTemplate",
                    "Only granular 'az ai-gateway' commands are allowed.",
                )
            )
        capability_refs = item.get("capabilityRefs", [])
        if not isinstance(capability_refs, list):
            errors.append(
                _issue(
                    "invalid-capability-references",
                    f"{path}/capabilityRefs",
                    "capabilityRefs must be an array.",
                )
            )
            capability_refs = []
        allowed_commands = []
        expected_approval_classes = set()
        allowed_verification_methods = set()
        for capability_id in capability_refs:
            capability = capabilities.get(capability_id)
            if capability is None:
                errors.append(
                    _issue(
                        "unknown-capability",
                        f"{path}/capabilityRefs",
                        (
                            f"Capability '{capability_id}' is not in the "
                            "installed contract."
                        ),
                    )
                )
                continue
            allowed_commands.extend(capability["allowedCommands"])
            expected_approval_classes.add(capability["approvalClass"])
            allowed_verification_methods.update(
                capability["behaviorVerification"]
            )
        command_prefix = _command_prefix(command)
        matching_commands = [
            allowed
            for allowed in allowed_commands
            if isinstance(command, list)
            and command[: len(allowed["prefix"])] == allowed["prefix"]
        ]
        if command_prefix and not matching_commands:
            errors.append(
                _issue(
                    "command-not-allowed",
                    f"{path}/commandTemplate",
                    "Command is not allowed by the referenced capabilities.",
                )
            )
        operation = item.get("operation")
        if not isinstance(operation, dict):
            errors.append(
                _issue(
                    "invalid-operation",
                    f"{path}/operation",
                    "TODO operation must be a JSON object.",
                )
            )
            operation = {}
        if matching_commands:
            expected_operations = {
                (
                    allowed["group"],
                    allowed["name"],
                    allowed["mutation"],
                )
                for allowed in matching_commands
            }
            actual_operation = (
                operation.get("commandGroup"),
                operation.get("commandName"),
                operation.get("kind"),
            )
            if actual_operation not in expected_operations:
                errors.append(
                    _issue(
                        "operation-command-mismatch",
                        f"{path}/operation",
                        (
                            "TODO operation group, name, and kind must match "
                            "the allowed command."
                        ),
                    )
                )
        if not isinstance(operation.get("targetKey"), str) or not operation.get(
            "targetKey"
        ):
            errors.append(
                _issue(
                    "missing-target-key",
                    f"{path}/operation/targetKey",
                    "TODO operation requires a natural target key.",
                )
            )
        expected_approval = (
            "consequential"
            if "consequential" in expected_approval_classes
            else "safe-batch"
        )
        if expected_approval_classes and item.get(
            "approvalClass"
        ) != expected_approval:
            errors.append(
                _issue(
                    "approval-class-mismatch",
                    f"{path}/approvalClass",
                    (
                        "TODO approvalClass does not match the referenced "
                        "capabilities."
                    ),
                )
            )
        approval = item.get("approval") or {}
        if approval.get("status") == "approved" and approval.get(
            "approvedPlanDigest"
        ) != plan_digest:
            errors.append(
                _issue(
                    "stale-approval",
                    f"{path}/approval/approvedPlanDigest",
                    "Approval does not match the current plan digest.",
                )
            )
        precondition = item.get("precondition") or {}
        if not isinstance(precondition, dict):
            errors.append(
                _issue(
                    "invalid-precondition",
                    f"{path}/precondition",
                    "TODO precondition must be a JSON object.",
                )
            )
            precondition = {}
        if not _is_safe_precondition_command(
            precondition.get("commandTemplate")
        ):
            errors.append(
                _issue(
                    "unsafe-precondition-command",
                    f"{path}/precondition/commandTemplate",
                    (
                        "Preconditions must use a read-only az ai-gateway "
                        "command or sync --dry-run."
                    ),
                )
            )
        if (
            not isinstance(precondition.get("expectedOutcome"), str)
            or not precondition.get("expectedOutcome")
        ):
            errors.append(
                _issue(
                    "missing-precondition-outcome",
                    f"{path}/precondition/expectedOutcome",
                    "TODO precondition requires an expected outcome.",
                )
            )
        if approval.get("status") == "approved" and (
            precondition.get("status") != "satisfied"
            or not _is_digest(precondition.get("stateDigest"))
        ):
            errors.append(
                _issue(
                    "unsatisfied-approved-precondition",
                    f"{path}/precondition",
                    (
                        "Approved TODOs require a satisfied precondition with "
                        "a current state digest."
                    ),
                )
            )
        if approval.get("status") == "approved" and approval.get(
            "approvedPreconditionDigest"
        ) != precondition.get("stateDigest"):
            errors.append(
                _issue(
                    "stale-precondition-approval",
                    f"{path}/approval/approvedPreconditionDigest",
                    (
                        "Approval does not match the current precondition "
                        "digest."
                    ),
                )
            )
        idempotency = item.get("idempotency") or {}
        expected_idempotency = {
            allowed["idempotency"] for allowed in matching_commands
        }
        if expected_idempotency and idempotency.get(
            "strategy"
        ) not in expected_idempotency:
            errors.append(
                _issue(
                    "idempotency-mismatch",
                    f"{path}/idempotency/strategy",
                    (
                        "TODO idempotency strategy does not match the "
                        "referenced capabilities."
                    ),
                )
            )
        if not isinstance(idempotency.get("idempotencyKey"), str) or not (
            idempotency.get("idempotencyKey")
        ):
            errors.append(
                _issue(
                    "missing-idempotency-key",
                    f"{path}/idempotency/idempotencyKey",
                    "TODO idempotency requires a natural target key.",
                )
            )
        elif idempotency.get("idempotencyKey") != operation.get("targetKey"):
            errors.append(
                _issue(
                    "idempotency-key-mismatch",
                    f"{path}/idempotency/idempotencyKey",
                    (
                        "Idempotency key must match the operation natural "
                        "target key."
                    ),
                )
            )
        if operation.get("kind") != "verify" and not _is_digest(
            idempotency.get("desiredStateDigest")
        ):
            errors.append(
                _issue(
                    "missing-desired-state-digest",
                    f"{path}/idempotency/desiredStateDigest",
                    "Mutating TODOs require a desired-state digest.",
                )
            )
        if (
            idempotency.get("strategy") == "non-repeatable"
            and idempotency.get("retryPolicy") != "never"
        ):
            errors.append(
                _issue(
                    "unsafe-retry-policy",
                    f"{path}/idempotency/retryPolicy",
                    "Non-repeatable operations must never be auto-retried.",
                )
            )
        if (
            idempotency.get("unknownOutcomeAction")
            != "read-current-state-before-retry"
        ):
            errors.append(
                _issue(
                    "unsafe-unknown-outcome",
                    f"{path}/idempotency/unknownOutcomeAction",
                    (
                        "Unknown outcomes must be reconciled by read before "
                        "retry."
                    ),
                )
            )
        if (
            matching_commands
            and matching_commands[0]["group"] == "ai-gateway model-provider"
            and matching_commands[0]["name"] == "create"
            and "--no-sync" not in command
        ):
            errors.append(
                _issue(
                    "provider-create-requires-no-sync",
                    f"{path}/commandTemplate",
                    "Model provider creation must use --no-sync.",
                )
            )
        if (
            matching_commands
            and matching_commands[0]["name"] == "sync"
            and "--dry-run"
            not in (precondition.get("commandTemplate") or [])
        ):
            errors.append(
                _issue(
                    "sync-requires-approved-preview",
                    f"{path}/precondition/commandTemplate",
                    "Sync requires a matching dry-run precondition.",
                )
            )
        if item.get("status") == "mutation-unknown":
            warnings.append(
                _issue(
                    "mutation-outcome-unknown",
                    path,
                    (
                        f"TODO '{item_id or index}' requires reconciliation "
                        "before retry."
                    ),
                )
            )
        source_behavior_ids = item.get("sourceBehaviorIds", [])
        if not isinstance(source_behavior_ids, list):
            errors.append(
                _issue(
                    "invalid-source-behaviors",
                    f"{path}/sourceBehaviorIds",
                    "sourceBehaviorIds must be an array.",
                )
            )
            source_behavior_ids = []
        mapping_item = mappings_by_id.get(item.get("mappingId")) or {}
        mapping_behavior_ids = set(mapping_item.get("sourceBehaviorIds", []))
        for behavior_id in source_behavior_ids:
            if behavior_id not in ledger_by_id:
                errors.append(
                    _issue(
                        "unknown-source-behavior",
                        f"{path}/sourceBehaviorIds",
                        (
                            f"Source behavior '{behavior_id}' is not in "
                            "sourceBehaviorLedger."
                        ),
                    )
                )
            if behavior_id not in mapping_behavior_ids:
                errors.append(
                    _issue(
                        "todo-mapping-behavior-mismatch",
                        f"{path}/sourceBehaviorIds",
                        (
                            f"Source behavior '{behavior_id}' is not owned by "
                            "the referenced mapping."
                        ),
                    )
                )
        mapping_capabilities = {
            evidence.get("capabilityId")
            for evidence in mapping_item.get("capabilityEvidence", [])
            if isinstance(evidence, dict)
        }
        if set(capability_refs) - mapping_capabilities:
            errors.append(
                _issue(
                    "todo-mapping-capability-mismatch",
                    f"{path}/capabilityRefs",
                    (
                        "TODO capabilities must be cited by the referenced "
                        "mapping."
                    ),
                )
            )
        if item.get("status") == "skipped" and (
            (mapping_item.get("residual") or {}).get("status") != "accepted"
        ):
            errors.append(
                _issue(
                    "unaccepted-skipped-work",
                    f"{path}/status",
                    "Skipped work requires an accepted plan-bound residual.",
                )
            )
        ready_behaviors.update(source_behavior_ids)
        verification = item.get("verification") or {}
        if not isinstance(verification, dict):
            errors.append(
                _issue(
                    "invalid-verification",
                    f"{path}/verification",
                    "Verification must be a JSON object.",
                )
            )
            verification = {}
        resource = verification.get("resource") or {}
        if not isinstance(resource, dict):
            errors.append(
                _issue(
                    "invalid-resource-verification",
                    f"{path}/verification/resource",
                    "Resource verification must be a JSON object.",
                )
            )
            resource = {}
        if not _is_safe_precondition_command(resource.get("commandTemplate")):
            errors.append(
                _issue(
                    "unsafe-resource-verification",
                    f"{path}/verification/resource/commandTemplate",
                    (
                        "Resource verification must use a read-only "
                        "az ai-gateway command."
                    ),
                )
            )
        if resource.get("status") == "passed" and (
            not _is_digest(resource.get("expectedStateDigest"))
            or resource.get("observedStateDigest")
            != resource.get("expectedStateDigest")
            or not resource.get("evidence")
        ):
            errors.append(
                _issue(
                    "incomplete-resource-verification",
                    f"{path}/verification/resource",
                    (
                        "Passed resource verification requires matching "
                        "expected and observed digests plus redacted evidence."
                    ),
                )
            )
        if item.get("status") == "behavior-verified":
            behaviors = verification.get("behaviors", [])
            if not isinstance(behaviors, list):
                behaviors = []
            requires_behavior_checks = bool(source_behavior_ids)
            behavior_statuses = {
                behavior.get("status")
                for behavior in behaviors
                if isinstance(behavior, dict)
            }
            if (
                resource.get("status") != "passed"
                or (requires_behavior_checks and not behaviors)
                or not behavior_statuses.issubset({"passed"})
            ):
                errors.append(
                    _issue(
                        "invalid-behavior-verification",
                        f"{path}/verification",
                        (
                            "Behavior-verified TODOs require passing resource "
                            "and behavior checks."
                        ),
                    )
                )
        behavior_values = verification.get("behaviors", [])
        if not isinstance(behavior_values, list):
            errors.append(
                _issue(
                    "invalid-behavior-verification",
                    f"{path}/verification/behaviors",
                    "Behavior verification must be an array.",
                )
            )
            behavior_values = []
        verification_behavior_ids = [
            behavior.get("behaviorId")
            for behavior in behavior_values
            if isinstance(behavior, dict)
        ]
        if len(verification_behavior_ids) != len(
            set(verification_behavior_ids)
        ):
            errors.append(
                _issue(
                    "duplicate-behavior-verification",
                    f"{path}/verification/behaviors",
                    "Each TODO behavior must be verified exactly once.",
                )
            )
        if set(verification_behavior_ids) != set(source_behavior_ids):
            errors.append(
                _issue(
                    "incomplete-behavior-verification",
                    f"{path}/verification/behaviors",
                    (
                        "Behavior verification records must exactly cover "
                        "TODO sourceBehaviorIds."
                    ),
                )
            )
        for behavior_index, behavior in enumerate(behavior_values):
            if not isinstance(behavior, dict):
                errors.append(
                    _issue(
                        "invalid-behavior-verification",
                        f"{path}/verification/behaviors/{behavior_index}",
                        "Behavior verification must be a JSON object.",
                    )
                )
                continue
            if behavior.get("method") not in allowed_verification_methods:
                errors.append(
                    _issue(
                        "verification-method-mismatch",
                        (
                            f"{path}/verification/behaviors/"
                            f"{behavior_index}/method"
                        ),
                        (
                            "Behavior verification method is not allowed by "
                            "the referenced capabilities."
                        ),
                    )
                )
            if (
                behavior.get("method") == "accepted-residual"
                and (mapping_item.get("residual") or {}).get("status")
                != "accepted"
            ):
                errors.append(
                    _issue(
                        "unaccepted-residual-verification",
                        (
                            f"{path}/verification/behaviors/"
                            f"{behavior_index}/method"
                        ),
                        (
                            "accepted-residual verification requires a "
                            "current accepted mapping residual."
                        ),
                    )
                )
            if behavior.get("status") == "passed" and (
                not _is_digest(behavior.get("observedDigest"))
                or not behavior.get("evidence")
            ):
                errors.append(
                    _issue(
                        "incomplete-behavior-evidence",
                        f"{path}/verification/behaviors/{behavior_index}",
                        (
                            "Passed behavior verification requires an "
                            "observed digest and redacted evidence."
                        ),
                    )
                )
        rollback = item.get("rollback")
        if not isinstance(rollback, dict):
            errors.append(
                _issue(
                    "invalid-rollback",
                    f"{path}/rollback",
                    "TODO rollback must be a JSON object.",
                )
            )
            rollback = {}
        rollback_mode = rollback.get("mode")
        rollback_command = rollback.get("commandTemplate")
        if rollback_mode == "automatic" and (
            not isinstance(rollback_command, list)
            or rollback_command[:2] != ["az", "ai-gateway"]
        ):
            errors.append(
                _issue(
                    "unsafe-rollback-command",
                    f"{path}/rollback/commandTemplate",
                    (
                        "Automatic rollback must use a granular "
                        "az ai-gateway command."
                    ),
                )
            )
        if rollback_mode == "manual" and not rollback.get("guidance"):
            errors.append(
                _issue(
                    "missing-rollback-guidance",
                    f"{path}/rollback/guidance",
                    "Manual rollback requires guidance.",
                )
            )
        if rollback_mode == "none" and not rollback.get("limitations"):
            errors.append(
                _issue(
                    "missing-rollback-limitations",
                    f"{path}/rollback/limitations",
                    "Non-reversible work requires explicit limitations.",
                )
            )
        attempts = item.get("attempts", [])
        if not isinstance(attempts, list):
            errors.append(
                _issue(
                    "invalid-attempts",
                    f"{path}/attempts",
                    "TODO attempts must be an array.",
                )
            )
            attempts = []
        unresolved_unknown = False
        for attempt_index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                errors.append(
                    _issue(
                        "invalid-attempt",
                        f"{path}/attempts/{attempt_index}",
                        "Each execution attempt must be a JSON object.",
                    )
                )
                continue
            reconciliation = attempt.get("reconciliation") or {}
            if attempt.get("outcome") == "unknown" and reconciliation.get(
                "status"
            ) in {None, "pending", "ambiguous"}:
                unresolved_unknown = True
            elif unresolved_unknown:
                errors.append(
                    _issue(
                        "retry-before-reconciliation",
                        f"{path}/attempts/{attempt_index}",
                        (
                            "An unknown mutation outcome must be reconciled "
                            "before another attempt."
                        ),
                    )
                )
        if unresolved_unknown and item.get("status") != "mutation-unknown":
            errors.append(
                _issue(
                    "unreconciled-mutation-status",
                    f"{path}/status",
                    (
                        "Unresolved unknown outcomes require "
                        "status mutation-unknown."
                    ),
                )
            )
    _check_dependencies(todos, errors)
    items_by_id = {
        item.get("id"): item
        for item in todos.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    active_statuses = {
        "in-progress",
        "mutation-unknown",
        "resource-verified",
        "behavior-verified",
    }
    for index, item in enumerate(todos.get("items", [])):
        if not isinstance(item, dict) or item.get("status") not in active_statuses:
            continue
        for dependency_id in item.get("dependencies", []):
            dependency = items_by_id.get(dependency_id) or {}
            dependency_mapping = mappings_by_id.get(
                dependency.get("mappingId")
            ) or {}
            dependency_complete = dependency.get(
                "status"
            ) == "behavior-verified" or (
                dependency.get("status") == "skipped"
                and (dependency_mapping.get("residual") or {}).get("status")
                == "accepted"
            )
            if not dependency_complete:
                errors.append(
                    _issue(
                        "unsatisfied-dependency",
                        f"/todos/items/{index}/dependencies",
                        (
                            f"Dependency '{dependency_id}' is not "
                            "behavior-verified or covered by an accepted "
                            "residual."
                        ),
                    )
                )
    return ready_behaviors


def _derived_verification_summary(todos, mappings_by_id):
    resource_statuses = []
    behavior_statuses = []
    for item in todos.get("items", []):
        if not isinstance(item, dict):
            continue
        mapping_item = mappings_by_id.get(item.get("mappingId")) or {}
        accepted_skip = (
            item.get("status") == "skipped"
            and (mapping_item.get("residual") or {}).get("status")
            == "accepted"
        )
        if accepted_skip:
            continue
        verification = item.get("verification") or {}
        resource = verification.get("resource") or {}
        resource_statuses.append(resource.get("status"))
        behavior_statuses.extend(
            behavior.get("status")
            for behavior in verification.get("behaviors", [])
            if isinstance(behavior, dict)
        )

    def summarize(statuses):
        failed = statuses.count("failed")
        pending = sum(
            status not in {"passed", "failed"} for status in statuses
        )
        if failed:
            overall = "failed"
        elif pending:
            overall = "partial" if "passed" in statuses else "not-run"
        else:
            overall = "passed"
        return overall, pending, failed

    resource_status, resource_pending, resource_failed = summarize(
        resource_statuses
    )
    behavior_status, behavior_pending, behavior_failed = summarize(
        behavior_statuses
    )
    return {
        "resourceStatus": resource_status,
        "behaviorStatus": behavior_status,
        "resourcePending": resource_pending,
        "resourceFailed": resource_failed,
        "behaviorPending": behavior_pending,
        "behaviorFailed": behavior_failed,
    }


def _check_context_digests(
    context,
    source_inventory,
    capability_contract,
    mapping,
    todos,
    plan_digest,
    errors,
):
    recorded = context.get("digests") or {}
    expected = {
        "sourceArtifact": _jcs_digest(source_inventory),
        "capabilityContract": _jcs_digest(capability_contract),
        "mapping": _jcs_digest(mapping),
        "todos": _jcs_digest(todos),
        "plan": plan_digest,
    }
    for field, expected_digest in expected.items():
        recorded_digest = recorded.get(field)
        if recorded_digest is not None and recorded_digest != expected_digest:
            errors.append(
                _issue(
                    "context-digest-mismatch",
                    f"/context/digests/{field}",
                    f"Context {field} digest does not match its input.",
                )
            )
    checkpoint = context.get("lastVerifiedCheckpoint")
    if checkpoint is not None:
        if checkpoint.get("generationId") != context.get("generationId"):
            errors.append(
                _issue(
                    "checkpoint-generation-mismatch",
                    "/context/lastVerifiedCheckpoint/generationId",
                    (
                        "Last verified checkpoint generation does not match "
                        "the current generation."
                    ),
                )
            )
        if checkpoint.get("manifestDigest") != recorded.get(
            "generationManifest"
        ):
            errors.append(
                _issue(
                    "checkpoint-manifest-mismatch",
                    "/context/lastVerifiedCheckpoint/manifestDigest",
                    (
                        "Last verified checkpoint must bind the recorded "
                        "generation manifest digest."
                    ),
                )
            )
    if context.get("completionStatus") in {
        "complete",
        "complete-with-accepted-residuals",
    }:
        for field, expected_digest in expected.items():
            if recorded.get(field) != expected_digest:
                errors.append(
                    _issue(
                        "missing-completion-digest",
                        f"/context/digests/{field}",
                        (
                            f"Completed state requires a current {field} "
                            "digest."
                        ),
                    )
                )
        for field in (
            "sourceContent",
            "sourceCoverage",
            "destinationContent",
            "generationManifest",
        ):
            if not _is_digest(recorded.get(field)):
                errors.append(
                    _issue(
                        "missing-completion-digest",
                        f"/context/digests/{field}",
                        f"Completed state requires a {field} digest.",
                    )
                )
        if checkpoint is None:
            errors.append(
                _issue(
                    "missing-verified-checkpoint",
                    "/context/lastVerifiedCheckpoint",
                    (
                        "Completed state requires a verified generation "
                        "checkpoint."
                    ),
                )
            )


def _validate_migration_plan(
    context_file,
    mapping_file,
    todos_file,
    source_inventory_file,
):
    context = _load_document(context_file, "--context-file")
    mapping = _load_document(mapping_file, "--mapping-file")
    todos = _load_document(todos_file, "--todos-file")
    source_inventory = _load_document(
        source_inventory_file,
        "--source-inventory-file",
    )
    errors = []
    warnings = []
    schema_errors = validate_migration_state(context, mapping, todos)
    errors.extend(schema_errors)
    for name, document in (
        ("context", context),
        ("mapping", mapping),
        ("todos", todos),
        ("sourceInventory", source_inventory),
    ):
        _check_persisted_secrets(document, f"/{name}", errors)
    if schema_errors:
        errors.sort(
            key=lambda item: (item["path"], item["code"], item["message"])
        )
        result = {
            "schemaVersion": "1.0",
            "validatorVersion": PLAN_VALIDATOR_VERSION,
            "kind": "AiGatewayMigrationPlanValidation",
            "status": "invalid",
            "planDigest": _digest(
                {"mapping": mapping, "todos": todos}
            ),
            "capabilityContractDigest": show_migration_capability()[
                "contractDigest"
            ],
            "sourceInventoryDigest": _digest(source_inventory),
            "errors": errors,
            "warnings": [],
        }
        result["resultDigest"] = _digest(result)
        return result
    for name, document in (
        ("context", context),
        ("mapping", mapping),
        ("todos", todos),
    ):
        _check_document_version(document, name, errors)
    for name, document in (("mapping", mapping), ("todos", todos)):
        if not isinstance(document.get("items"), list):
            errors.append(
                _issue(
                    "invalid-items",
                    f"/{name}/items",
                    f"{name}.items must be an array.",
                )
            )
            document["items"] = []
    _check_generation(context, mapping, todos, errors)
    contract, capabilities = _capabilities_by_id()
    capability_digest = contract["contractDigest"]
    (
        source_inventory_digest,
        ledger_by_id,
        source_sku,
    ) = _check_source_inventory(
        source_inventory,
        context,
        mapping,
        errors,
        warnings,
    )
    if todos.get("sourceInventoryDigest") != source_inventory_digest:
        errors.append(
            _issue(
                "source-inventory-digest-mismatch",
                "/todos/sourceInventoryDigest",
                "Mapping and TODO source inventory digests differ.",
            )
        )
    if mapping.get("capabilityContractDigest") != capability_digest:
        errors.append(
            _issue(
                "stale-capability-contract",
                "/mapping/capabilityContractDigest",
                "Mapping does not use the installed capability contract.",
            )
        )
    if todos.get("capabilityContractDigest") != capability_digest:
        errors.append(
            _issue(
                "stale-capability-contract",
                "/todos/capabilityContractDigest",
                "TODOs do not use the installed capability contract.",
            )
        )
    context_contract = context.get("capabilityContract") or {}
    if (
        context_contract.get("contractDigest") != capability_digest
        or context_contract.get("status") != "current"
        or context_contract.get("kind")
        != "AiGatewayMigrationCapabilityContract"
        or context_contract.get("contractVersion")
        != CAPABILITY_CONTRACT_VERSION
        or context_contract.get("generatedBy") != contract["generatedBy"]
        or (context_contract.get("command") or [])[:4]
        != ["az", "ai-gateway", "migration-capability", "show"]
    ):
        errors.append(
            _issue(
                "stale-capability-contract",
                "/context/capabilityContract",
                (
                    "Context must bind the current installed capability "
                    "contract before validation."
                ),
            )
        )
    plan_digest = _digest(_plan_projection(mapping, todos))
    _check_context_digests(
        context,
        source_inventory,
        contract,
        mapping,
        todos,
        plan_digest,
        errors,
    )
    if todos.get("planDigest") != plan_digest:
        errors.append(
            _issue(
                "plan-digest-mismatch",
                "/todos/planDigest",
                "todos.json planDigest does not match the deterministic plan.",
            )
        )
    recorded_validation = context.get("planValidation") or {}
    if (
        recorded_validation.get("status") == "valid"
        and (
            recorded_validation.get("planDigest") != plan_digest
            or recorded_validation.get("capabilityContractDigest")
            != capability_digest
            or recorded_validation.get("sourceInventoryDigest")
            != source_inventory_digest
        )
    ):
        errors.append(
            _issue(
                "stale-plan-validation",
                "/context/planValidation/planDigest",
                "Context validation does not match the current plan digest.",
            )
        )
    todo_validation = todos.get("validation") or {}
    if todo_validation.get("status") in {"valid", "invalid"}:
        validation_payload = deepcopy(todo_validation)
        recorded_result_digest = validation_payload.pop(
            "resultDigest",
            None,
        )
        if recorded_result_digest != _digest(validation_payload):
            errors.append(
                _issue(
                    "invalid-validation-result-digest",
                    "/todos/validation/resultDigest",
                    (
                        "Stored TODO validation result digest does not match "
                        "its content."
                    ),
                )
            )
        if (
            recorded_validation.get("status") in {"valid", "invalid"}
            and recorded_validation.get("resultDigest")
            != recorded_result_digest
        ):
            errors.append(
                _issue(
                    "validation-result-mismatch",
                    "/context/planValidation/resultDigest",
                    (
                        "Context and TODO validation result digests differ."
                    ),
                )
            )
    if todo_validation.get("status") == "valid" and (
        todo_validation.get("planDigest") != plan_digest
        or todo_validation.get("capabilityContractDigest")
        != capability_digest
        or todo_validation.get("sourceInventoryDigest")
        != source_inventory_digest
    ):
        errors.append(
            _issue(
                "stale-plan-validation",
                "/todos/validation",
                "TODO validation does not match the current inputs.",
            )
        )
    mapping_ids = _check_mapping(
        mapping,
        ledger_by_id,
        source_sku,
        capability_digest,
        capabilities,
        plan_digest,
        errors,
        warnings,
    )
    mappings_by_id = {
        item.get("id"): item
        for item in mapping.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    todo_behaviors = _check_todos(
        todos,
        mapping_ids,
        mappings_by_id,
        ledger_by_id,
        capabilities,
        plan_digest,
        errors,
        warnings,
    )
    required_behaviors = {
        behavior_id
        for item in mapping.get("items", [])
        if isinstance(item, dict)
        if item.get("classification") == "ready"
        for behavior_id in item.get("sourceBehaviorIds", [])
    }
    for behavior_id in sorted(required_behaviors - todo_behaviors):
        errors.append(
            _issue(
                "unplanned-source-behavior",
                "/todos/items",
                (
                    f"Ready source behavior '{behavior_id}' has no executable "
                    "TODO."
                ),
            )
        )
    residual_statuses = [
        (item.get("residual") or {}).get("status")
        for item in mapping.get("items", [])
        if isinstance(item, dict)
    ]
    actual_residuals = {
        "total": sum(status != "none" for status in residual_statuses),
        "pendingAcceptance": residual_statuses.count("pending-acceptance"),
        "accepted": residual_statuses.count("accepted"),
        "rejected": residual_statuses.count("rejected"),
    }
    recorded_residuals = context.get("residualSummary") or {}
    for field, count in actual_residuals.items():
        if recorded_residuals.get(field) != count:
            errors.append(
                _issue(
                    "residual-summary-mismatch",
                    f"/context/residualSummary/{field}",
                    (
                        f"Recorded residual {field} does not match mapping "
                        "residuals."
                    ),
                )
            )
    recorded_verification = context.get("verificationSummary") or {}
    derived_verification = _derived_verification_summary(
        todos,
        mappings_by_id,
    )
    executable_todos = [
        item
        for item in todos.get("items", [])
        if isinstance(item, dict)
        if not (
            item.get("status") == "skipped"
            and (
                mappings_by_id.get(item.get("mappingId"), {}).get(
                    "residual"
                )
                or {}
            ).get("status")
            == "accepted"
        )
    ]
    for field in (
        "resourcePending",
        "resourceFailed",
        "behaviorPending",
        "behaviorFailed",
    ):
        if recorded_verification.get(field) != derived_verification[field]:
            errors.append(
                _issue(
                    "verification-summary-mismatch",
                    f"/context/verificationSummary/{field}",
                    (
                        f"Recorded {field} does not match TODO verification "
                        "state."
                    ),
                )
            )
    if executable_todos:
        for field in ("resourceStatus", "behaviorStatus"):
            if (
                recorded_verification.get(field)
                != derived_verification[field]
            ):
                errors.append(
                    _issue(
                        "verification-summary-mismatch",
                        f"/context/verificationSummary/{field}",
                        (
                            f"Recorded {field} does not match TODO "
                            "verification state."
                        ),
                    )
                )
    completion_status = context.get("completionStatus")
    if completion_status in {
        "complete",
        "complete-with-accepted-residuals",
    }:
        context_inventory = context.get("sourceInventory") or {}
        inventory_summary = source_inventory.get("summary") or {}
        provenance = source_inventory.get("provenance") or {}
        if (
            context_inventory.get("authority") not in _READY_AUTHORITIES
            or context_inventory.get("inventoryStatus") != "complete"
            or context_inventory.get("authoritativeForAbsence") is not True
            or inventory_summary.get("inventoryStatus") != "complete"
            or not inventory_summary.get("requiredDiscoveryComplete")
            or provenance.get("conflicts")
        ):
            errors.append(
                _issue(
                    "incomplete-source-authority",
                    "/context/sourceInventory",
                    (
                        "Complete migrations require conflict-free source "
                        "inventory that is authoritative for required "
                        "absence."
                    ),
                )
            )
        if context.get("phase") != "complete":
            errors.append(
                _issue(
                    "completion-phase-mismatch",
                    "/context/phase",
                    "Complete migrations require phase complete.",
                )
            )
        if recorded_validation.get("status") != "valid" or not _is_digest(
            recorded_validation.get("resultDigest")
        ):
            errors.append(
                _issue(
                    "missing-current-validation",
                    "/context/planValidation",
                    (
                        "Complete migrations require a current valid "
                        "persisted validation result."
                    ),
                )
            )
        if todo_validation.get("status") != "valid" or not _is_digest(
            todo_validation.get("resultDigest")
        ):
            errors.append(
                _issue(
                    "missing-current-validation",
                    "/todos/validation",
                    (
                        "Complete migrations require current valid TODO "
                        "validation."
                    ),
                )
            )
        incomplete_todos = [
            item.get("id")
            for item in todos.get("items", [])
            if isinstance(item, dict)
            if item.get("status") not in {"behavior-verified", "skipped"}
        ]
        if incomplete_todos:
            errors.append(
                _issue(
                    "incomplete-todos",
                    "/todos/items",
                    (
                        "Complete migrations require every executable TODO "
                        "to be behavior-verified."
                    ),
                )
            )
        if completion_status == "complete" and any(
            isinstance(item, dict) and item.get("status") == "skipped"
            for item in todos.get("items", [])
        ):
            errors.append(
                _issue(
                    "skipped-work-at-completion",
                    "/todos/items",
                    "Complete migrations cannot contain skipped work.",
                )
            )
        verification = context.get("verificationSummary") or {}
        if (
            verification.get("resourceStatus") != "passed"
            or verification.get("behaviorStatus") != "passed"
            or verification.get("resourcePending") != 0
            or verification.get("resourceFailed") != 0
            or verification.get("behaviorPending") != 0
            or verification.get("behaviorFailed") != 0
        ):
            errors.append(
                _issue(
                    "incomplete-verification",
                    "/context/verificationSummary",
                    (
                        "Complete migrations require passing resource and "
                        "behavior verification."
                    ),
                )
            )
        residuals = recorded_residuals
        if residuals.get("pendingAcceptance", 0) or residuals.get(
            "rejected", 0
        ):
            errors.append(
                _issue(
                    "unresolved-residuals",
                    "/context/residualSummary",
                    "Complete migrations cannot have unresolved residuals.",
                )
            )
        if completion_status == "complete" and residuals.get("total", 0):
            errors.append(
                _issue(
                    "residual-completion-mismatch",
                    "/context/completionStatus",
                    "Use complete only when there are no residuals.",
                )
            )
        if (
            completion_status == "complete-with-accepted-residuals"
            and residuals.get("accepted", 0) < 1
        ):
            errors.append(
                _issue(
                    "residual-completion-mismatch",
                    "/context/completionStatus",
                    (
                        "complete-with-accepted-residuals requires at least "
                        "one accepted residual."
                    ),
                )
            )
    errors.sort(key=lambda item: (item["path"], item["code"], item["message"]))
    warnings.sort(key=lambda item: (item["path"], item["code"], item["message"]))
    result = {
        "schemaVersion": "1.0",
        "validatorVersion": PLAN_VALIDATOR_VERSION,
        "kind": "AiGatewayMigrationPlanValidation",
        "status": "invalid" if errors else "valid",
        "planDigest": plan_digest,
        "capabilityContractDigest": capability_digest,
        "sourceInventoryDigest": source_inventory_digest,
        "errors": errors,
        "warnings": warnings,
    }
    result["resultDigest"] = _digest(result)
    return result


def validate_migration_plan(
    context_file,
    mapping_file,
    todos_file,
    source_inventory_file,
):
    try:
        return _validate_migration_plan(
            context_file,
            mapping_file,
            todos_file,
            source_inventory_file,
        )
    except (
        AttributeError,
        RecursionError,
        TypeError,
        UnicodeEncodeError,
        ValueError,
    ):
        contract_digest = show_migration_capability()["contractDigest"]
        result = {
            "schemaVersion": "1.0",
            "validatorVersion": PLAN_VALIDATOR_VERSION,
            "kind": "AiGatewayMigrationPlanValidation",
            "status": "invalid",
            "planDigest": _digest({}),
            "capabilityContractDigest": contract_digest,
            "sourceInventoryDigest": _digest({}),
            "errors": [
                _issue(
                    "invalid-document-shape",
                    "/",
                    (
                        "Migration documents contain values that cannot be "
                        "validated against the required schema."
                    ),
                )
            ],
            "warnings": [],
        }
        result["resultDigest"] = _digest(result)
        return result


def format_migration_plan_validation_table(result):
    return [
        {
            "Status": result.get("status"),
            "Errors": len(result.get("errors", [])),
            "Warnings": len(result.get("warnings", [])),
            "Plan digest": result.get("planDigest"),
        }
    ]
