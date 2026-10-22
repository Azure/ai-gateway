# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from datetime import datetime
import re


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_AUTHORITIES = {
    "authoritative",
    "corroborated",
    "advisory",
    "conflicted",
    "insufficient",
    "unknown",
}
_READY_AUTHORITIES = {"authoritative", "corroborated"}


def _issue(code, path, message):
    return {"code": code, "path": path, "message": message}


def _object(value, path, required, allowed, errors):
    if not isinstance(value, dict):
        errors.append(_issue("schema-type", path, "Value must be an object."))
        return False
    for field in sorted(required - set(value)):
        errors.append(
            _issue(
                "schema-required",
                f"{path}/{field}",
                f"Required field '{field}' is missing.",
            )
        )
    for field in sorted(set(value) - allowed):
        errors.append(
            _issue(
                "schema-additional-property",
                f"{path}/{field}",
                f"Unexpected field '{field}'.",
            )
        )
    return True


def _array(value, path, errors, minimum=0):
    if not isinstance(value, list):
        errors.append(_issue("schema-type", path, "Value must be an array."))
        return False
    if len(value) < minimum:
        errors.append(
            _issue(
                "schema-min-items",
                path,
                f"Array must contain at least {minimum} item(s).",
            )
        )
    return True


def _string(value, path, errors, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value:
        errors.append(
            _issue("schema-type", path, "Value must be a non-empty string.")
        )


def _enum(value, values, path, errors):
    try:
        invalid = value not in values
    except TypeError:
        invalid = True
    if invalid:
        errors.append(
            _issue(
                "schema-enum",
                path,
                (
                    "Value must be one of: "
                    + ", ".join(sorted(repr(item) for item in values))
                    + "."
                ),
            )
        )


def _boolean(value, path, errors):
    if not isinstance(value, bool):
        errors.append(_issue("schema-type", path, "Value must be a boolean."))


def _integer(value, path, errors):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(
            _issue(
                "schema-type",
                path,
                "Value must be a non-negative integer.",
            )
        )


def _digest(value, path, errors, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        errors.append(
            _issue(
                "schema-format",
                path,
                "Value must be a sha256 digest.",
            )
        )


def _date_time(value, path, errors, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str):
        errors.append(
            _issue("schema-format", path, "Value must be an RFC 3339 date-time.")
        )
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        errors.append(
            _issue("schema-format", path, "Value must be an RFC 3339 date-time.")
        )


def _command(value, path, errors, nullable=False):
    if nullable and value is None:
        return
    if not _array(value, path, errors, minimum=1):
        return
    for index, item in enumerate(value):
        _string(item, f"{path}/{index}", errors)


def _string_array(value, path, errors, minimum=0, unique=False):
    if not _array(value, path, errors, minimum=minimum):
        return
    for index, item in enumerate(value):
        _string(item, f"{path}/{index}", errors)
    if (
        unique
        and all(isinstance(item, str) for item in value)
        and len(value) != len(set(value))
    ):
        errors.append(
            _issue("schema-unique", path, "Array values must be unique.")
        )


def _validate_context(context, errors):
    fields = {
        "schemaVersion",
        "generationId",
        "phase",
        "completionStatus",
        "source",
        "destination",
        "sourceInventory",
        "capabilityContract",
        "planValidation",
        "digests",
        "extension",
        "residualSummary",
        "verificationSummary",
        "timestamps",
        "lastVerifiedCheckpoint",
        "sourceHandoffs",
    }
    if not _object(context, "/context", fields, fields, errors):
        return
    _enum(context.get("schemaVersion"), {"2.0"}, "/context/schemaVersion", errors)
    _string(context.get("generationId"), "/context/generationId", errors)
    _enum(
        context.get("phase"),
        {
            "context",
            "source-inventory",
            "destination-inventory",
            "mapping",
            "plan-validation",
            "approval",
            "execution",
            "behavior-verification",
            "complete",
            "blocked",
        },
        "/context/phase",
        errors,
    )
    _enum(
        context.get("completionStatus"),
        {
            "not-started",
            "in-progress",
            "incomplete",
            "blocked",
            "failed",
            "cancelled",
            "complete",
            "complete-with-accepted-residuals",
        },
        "/context/completionStatus",
        errors,
    )
    source_fields = {
        "resourceId",
        "subscriptionId",
        "sku",
        "provisioningState",
        "targetProvisioningState",
    }
    source = context.get("source")
    if _object(
        source,
        "/context/source",
        source_fields,
        source_fields,
        errors,
    ):
        _string(source.get("resourceId"), "/context/source/resourceId", errors)
        _string(
            source.get("subscriptionId"),
            "/context/source/subscriptionId",
            errors,
        )
        for field in ("sku", "provisioningState", "targetProvisioningState"):
            _string(
                source.get(field),
                f"/context/source/{field}",
                errors,
                nullable=True,
            )
    destination = context.get("destination")
    destination_fields = {
        "resourceId",
        "subscriptionId",
        "resourceGroup",
        "name",
        "region",
    }
    if destination is not None and _object(
        destination,
        "/context/destination",
        destination_fields,
        destination_fields,
        errors,
    ):
        _string(
            destination.get("resourceId"),
            "/context/destination/resourceId",
            errors,
            nullable=True,
        )
        for field in ("subscriptionId", "resourceGroup", "name"):
            _string(
                destination.get(field),
                f"/context/destination/{field}",
                errors,
            )
        _string(
            destination.get("region"),
            "/context/destination/region",
            errors,
            nullable=True,
        )
    inventory = context.get("sourceInventory")
    inventory_fields = {
        "schemaVersion",
        "kind",
        "authority",
        "inventoryStatus",
        "authoritativeForAbsence",
        "artifactDigest",
        "provenanceDigest",
        "behaviorLedgerDigest",
    }
    if inventory is not None and _object(
        inventory,
        "/context/sourceInventory",
        inventory_fields,
        inventory_fields,
        errors,
    ):
        _enum(
            inventory.get("schemaVersion"),
            {"3.0"},
            "/context/sourceInventory/schemaVersion",
            errors,
        )
        _enum(
            inventory.get("kind"),
            {"AiGatewayApimImportInventory"},
            "/context/sourceInventory/kind",
            errors,
        )
        _enum(
            inventory.get("authority"),
            _AUTHORITIES,
            "/context/sourceInventory/authority",
            errors,
        )
        _enum(
            inventory.get("inventoryStatus"),
            {"complete", "partial", "blocked"},
            "/context/sourceInventory/inventoryStatus",
            errors,
        )
        _boolean(
            inventory.get("authoritativeForAbsence"),
            "/context/sourceInventory/authoritativeForAbsence",
            errors,
        )
        for field in (
            "artifactDigest",
            "provenanceDigest",
            "behaviorLedgerDigest",
        ):
            _digest(
                inventory.get(field),
                f"/context/sourceInventory/{field}",
                errors,
            )
    contract = context.get("capabilityContract")
    contract_fields = {
        "schemaVersion",
        "contractVersion",
        "kind",
        "generatedBy",
        "contractDigest",
        "status",
        "command",
        "capturedAt",
    }
    if contract is not None and _object(
        contract,
        "/context/capabilityContract",
        contract_fields,
        contract_fields,
        errors,
    ):
        _enum(
            contract.get("schemaVersion"),
            {"1.0"},
            "/context/capabilityContract/schemaVersion",
            errors,
        )
        _string(
            contract.get("contractVersion"),
            "/context/capabilityContract/contractVersion",
            errors,
        )
        _enum(
            contract.get("kind"),
            {"AiGatewayMigrationCapabilityContract"},
            "/context/capabilityContract/kind",
            errors,
        )
        generated_fields = {"extension", "command"}
        generated = contract.get("generatedBy")
        if _object(
            generated,
            "/context/capabilityContract/generatedBy",
            generated_fields,
            generated_fields,
            errors,
        ):
            _enum(
                generated.get("extension"),
                {"ai-gateway"},
                "/context/capabilityContract/generatedBy/extension",
                errors,
            )
            _enum(
                generated.get("command"),
                {"az ai-gateway migration-capability show"},
                "/context/capabilityContract/generatedBy/command",
                errors,
            )
        _digest(
            contract.get("contractDigest"),
            "/context/capabilityContract/contractDigest",
            errors,
        )
        _enum(
            contract.get("status"),
            {"current", "stale", "unavailable"},
            "/context/capabilityContract/status",
            errors,
        )
        _command(
            contract.get("command"),
            "/context/capabilityContract/command",
            errors,
        )
        _date_time(
            contract.get("capturedAt"),
            "/context/capabilityContract/capturedAt",
            errors,
        )
    _validate_context_plan_validation(context.get("planValidation"), errors)
    digest_fields = {
        "sourceContent",
        "sourceCoverage",
        "sourceArtifact",
        "destinationContent",
        "capabilityContract",
        "mapping",
        "todos",
        "plan",
        "generationManifest",
    }
    digests = context.get("digests")
    if _object(
        digests,
        "/context/digests",
        digest_fields,
        digest_fields,
        errors,
    ):
        for field in digest_fields:
            _digest(
                digests.get(field),
                f"/context/digests/{field}",
                errors,
                nullable=True,
            )
    extension_fields = {"name", "version"}
    extension = context.get("extension")
    if _object(
        extension,
        "/context/extension",
        extension_fields,
        extension_fields,
        errors,
    ):
        _enum(
            extension.get("name"),
            {"ai-gateway"},
            "/context/extension/name",
            errors,
        )
        _string(
            extension.get("version"),
            "/context/extension/version",
            errors,
        )
    _validate_summary(context.get("residualSummary"), "residualSummary", errors)
    _validate_verification_summary(context.get("verificationSummary"), errors)
    timestamps = context.get("timestamps")
    timestamp_fields = {"createdAt", "updatedAt"}
    if _object(
        timestamps,
        "/context/timestamps",
        timestamp_fields,
        timestamp_fields,
        errors,
    ):
        for field in timestamp_fields:
            _date_time(
                timestamps.get(field),
                f"/context/timestamps/{field}",
                errors,
            )
    checkpoint = context.get("lastVerifiedCheckpoint")
    checkpoint_fields = {"generationId", "manifestDigest", "verifiedAt"}
    if checkpoint is not None and _object(
        checkpoint,
        "/context/lastVerifiedCheckpoint",
        checkpoint_fields,
        checkpoint_fields,
        errors,
    ):
        _string(
            checkpoint.get("generationId"),
            "/context/lastVerifiedCheckpoint/generationId",
            errors,
        )
        _digest(
            checkpoint.get("manifestDigest"),
            "/context/lastVerifiedCheckpoint/manifestDigest",
            errors,
        )
        _date_time(
            checkpoint.get("verifiedAt"),
            "/context/lastVerifiedCheckpoint/verifiedAt",
            errors,
        )
    handoffs = context.get("sourceHandoffs")
    if _array(handoffs, "/context/sourceHandoffs", errors):
        handoff_fields = {
            "previousResourceId",
            "newResourceId",
            "reason",
            "decisionId",
            "approvedAt",
        }
        for index, handoff in enumerate(handoffs):
            path = f"/context/sourceHandoffs/{index}"
            if _object(
                handoff,
                path,
                handoff_fields,
                handoff_fields,
                errors,
            ):
                for field in handoff_fields - {"approvedAt"}:
                    _string(handoff.get(field), f"{path}/{field}", errors)
                _date_time(handoff.get("approvedAt"), f"{path}/approvedAt", errors)
    if context.get("completionStatus") in {
        "complete",
        "complete-with-accepted-residuals",
    }:
        _enum(context.get("phase"), {"complete"}, "/context/phase", errors)
        if not isinstance(destination, dict):
            errors.append(
                _issue(
                    "schema-type",
                    "/context/destination",
                    "Completed state requires a destination object.",
                )
            )
        else:
            _string(
                destination.get("resourceId"),
                "/context/destination/resourceId",
                errors,
            )
            _string(
                destination.get("region"),
                "/context/destination/region",
                errors,
            )
        if isinstance(source, dict):
            _enum(
                source.get("sku"),
                {"BasicV2", "StandardV2", "PremiumV2"},
                "/context/source/sku",
                errors,
            )
            _enum(
                source.get("provisioningState"),
                {"Succeeded"},
                "/context/source/provisioningState",
                errors,
            )
            _enum(
                source.get("targetProvisioningState"),
                {None, "Succeeded"},
                "/context/source/targetProvisioningState",
                errors,
            )


def _validate_context_plan_validation(value, errors):
    path = "/context/planValidation"
    fields = {
        "schemaVersion",
        "validatorVersion",
        "kind",
        "status",
        "planDigest",
        "resultDigest",
        "capabilityContractDigest",
        "sourceInventoryDigest",
        "command",
        "validatedAt",
        "errorCount",
        "warningCount",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("status"),
        {"not-run", "valid", "invalid", "stale", "failed"},
        f"{path}/status",
        errors,
    )
    for field in ("schemaVersion", "validatorVersion", "kind"):
        _string(value.get(field), f"{path}/{field}", errors, nullable=True)
    for field in (
        "planDigest",
        "resultDigest",
        "capabilityContractDigest",
        "sourceInventoryDigest",
    ):
        _digest(value.get(field), f"{path}/{field}", errors, nullable=True)
    _command(value.get("command"), f"{path}/command", errors, nullable=True)
    _date_time(value.get("validatedAt"), f"{path}/validatedAt", errors, nullable=True)
    _integer(value.get("errorCount"), f"{path}/errorCount", errors)
    _integer(value.get("warningCount"), f"{path}/warningCount", errors)
    if value.get("status") in {"valid", "invalid"}:
        _enum(value.get("schemaVersion"), {"1.0"}, f"{path}/schemaVersion", errors)
        _enum(
            value.get("kind"),
            {"AiGatewayMigrationPlanValidation"},
            f"{path}/kind",
            errors,
        )
        _string(value.get("validatorVersion"), f"{path}/validatorVersion", errors)
        for field in (
            "planDigest",
            "resultDigest",
            "capabilityContractDigest",
            "sourceInventoryDigest",
        ):
            _digest(value.get(field), f"{path}/{field}", errors)
        _command(value.get("command"), f"{path}/command", errors)
        _date_time(value.get("validatedAt"), f"{path}/validatedAt", errors)
    if value.get("status") == "valid" and value.get("errorCount") != 0:
        errors.append(
            _issue(
                "schema-const",
                f"{path}/errorCount",
                "Valid plan validation must have zero errors.",
            )
        )


def _validate_summary(value, name, errors):
    fields = {"total", "pendingAcceptance", "accepted", "rejected"}
    path = f"/context/{name}"
    if _object(value, path, fields, fields, errors):
        for field in fields:
            _integer(value.get(field), f"{path}/{field}", errors)


def _validate_verification_summary(value, errors):
    fields = {
        "resourceStatus",
        "behaviorStatus",
        "resourcePending",
        "resourceFailed",
        "behaviorPending",
        "behaviorFailed",
    }
    path = "/context/verificationSummary"
    if not _object(value, path, fields, fields, errors):
        return
    for field in ("resourceStatus", "behaviorStatus"):
        _enum(
            value.get(field),
            {"not-run", "partial", "passed", "failed"},
            f"{path}/{field}",
            errors,
        )
    for field in fields - {"resourceStatus", "behaviorStatus"}:
        _integer(value.get(field), f"{path}/{field}", errors)


def _validate_mapping(mapping, errors):
    fields = {
        "schemaVersion",
        "generationId",
        "sourceInventoryDigest",
        "capabilityContractDigest",
        "items",
    }
    if not _object(mapping, "/mapping", fields, fields, errors):
        return
    _enum(mapping.get("schemaVersion"), {"2.0"}, "/mapping/schemaVersion", errors)
    _string(mapping.get("generationId"), "/mapping/generationId", errors)
    for field in ("sourceInventoryDigest", "capabilityContractDigest"):
        _digest(mapping.get(field), f"/mapping/{field}", errors)
    items = mapping.get("items")
    if _array(items, "/mapping/items", errors):
        for index, item in enumerate(items):
            _validate_mapping_item(item, f"/mapping/items/{index}", errors)


def _validate_mapping_item(item, path, errors):
    fields = {
        "id",
        "recordType",
        "sourceStableIds",
        "sourceBehaviorIds",
        "classification",
        "authority",
        "sourceEvidence",
        "capabilityEvidence",
        "destination",
        "dependencies",
        "decisions",
        "question",
        "residual",
        "verification",
    }
    if not _object(item, path, fields, fields, errors):
        return
    _string(item.get("id"), f"{path}/id", errors)
    _enum(
        item.get("recordType"),
        {
            "source-item",
            "source-behavior",
            "coverage-gap",
            "provenance-conflict",
        },
        f"{path}/recordType",
        errors,
    )
    _string_array(
        item.get("sourceStableIds"),
        f"{path}/sourceStableIds",
        errors,
        minimum=1,
        unique=True,
    )
    _string_array(
        item.get("sourceBehaviorIds"),
        f"{path}/sourceBehaviorIds",
        errors,
        unique=True,
    )
    _enum(
        item.get("classification"),
        {"ready", "needs-input", "cannot-import"},
        f"{path}/classification",
        errors,
    )
    _enum(item.get("authority"), _AUTHORITIES, f"{path}/authority", errors)
    source_evidence = item.get("sourceEvidence")
    if _array(source_evidence, f"{path}/sourceEvidence", errors, minimum=1):
        for index, evidence in enumerate(source_evidence):
            _validate_source_evidence(
                evidence,
                f"{path}/sourceEvidence/{index}",
                errors,
            )
    capability_evidence = item.get("capabilityEvidence")
    if _array(
        capability_evidence,
        f"{path}/capabilityEvidence",
        errors,
        minimum=1,
    ):
        for index, evidence in enumerate(capability_evidence):
            _validate_capability_evidence(
                evidence,
                f"{path}/capabilityEvidence/{index}",
                errors,
            )
    destination = item.get("destination")
    if destination is not None and not isinstance(destination, dict):
        errors.append(
            _issue(
                "schema-type",
                f"{path}/destination",
                "Value must be an object or null.",
            )
        )
    _string_array(
        item.get("dependencies"),
        f"{path}/dependencies",
        errors,
        unique=True,
    )
    decisions = item.get("decisions")
    if _array(decisions, f"{path}/decisions", errors):
        for index, decision in enumerate(decisions):
            _validate_decision(decision, f"{path}/decisions/{index}", errors)
    _string(item.get("question"), f"{path}/question", errors, nullable=True)
    _validate_residual(item.get("residual"), f"{path}/residual", errors)
    _validate_mapping_verification(
        item.get("verification"),
        f"{path}/verification",
        errors,
    )
    classification = item.get("classification")
    residual_status = (item.get("residual") or {}).get("status")
    if classification == "ready":
        _enum(item.get("authority"), _READY_AUTHORITIES, f"{path}/authority", errors)
        _enum(residual_status, {"none"}, f"{path}/residual/status", errors)
    if classification == "needs-input":
        _string(item.get("question"), f"{path}/question", errors)
    if classification == "cannot-import":
        _enum(
            residual_status,
            {"pending-acceptance", "accepted", "rejected"},
            f"{path}/residual/status",
            errors,
        )
    if item.get("recordType") == "source-behavior" and not item.get(
        "sourceBehaviorIds"
    ):
        errors.append(
            _issue(
                "schema-min-items",
                f"{path}/sourceBehaviorIds",
                "Source-behavior records require at least one behavior ID.",
            )
        )
    if item.get("recordType") in {"coverage-gap", "provenance-conflict"}:
        _enum(
            classification,
            {"needs-input"},
            f"{path}/classification",
            errors,
        )
    if residual_status in {"pending-acceptance", "accepted", "rejected"}:
        _enum(
            classification,
            {"cannot-import"},
            f"{path}/classification",
            errors,
        )
    if residual_status == "accepted":
        _enum(
            (item.get("verification") or {}).get("status"),
            {"residual-accepted"},
            f"{path}/verification/status",
            errors,
        )


def _validate_source_evidence(value, path, errors):
    fields = {
        "sourceKind",
        "artifactId",
        "jsonPointer",
        "authority",
        "evidenceDigest",
    }
    if not _object(value, path, fields, fields, errors):
        return
    for field in ("sourceKind", "artifactId"):
        _string(value.get(field), f"{path}/{field}", errors)
    if not isinstance(value.get("jsonPointer"), str):
        errors.append(
            _issue("schema-type", f"{path}/jsonPointer", "Value must be a string.")
        )
    _enum(value.get("authority"), _AUTHORITIES, f"{path}/authority", errors)
    _digest(value.get("evidenceDigest"), f"{path}/evidenceDigest", errors)


def _validate_capability_evidence(value, path, errors):
    fields = {
        "capabilityId",
        "contractDigest",
        "support",
        "destinationCommands",
        "limitations",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _string(value.get("capabilityId"), f"{path}/capabilityId", errors)
    _digest(value.get("contractDigest"), f"{path}/contractDigest", errors)
    _enum(
        value.get("support"),
        {"supported", "conditional", "unsupported", "unknown"},
        f"{path}/support",
        errors,
    )
    commands = value.get("destinationCommands")
    if _array(commands, f"{path}/destinationCommands", errors):
        for index, command in enumerate(commands):
            _command(command, f"{path}/destinationCommands/{index}", errors)
    _string_array(value.get("limitations"), f"{path}/limitations", errors)


def _validate_decision(value, path, errors):
    fields = {"id", "type", "decision", "decidedAt"}
    if not _object(value, path, fields, fields, errors):
        return
    _string(value.get("id"), f"{path}/id", errors)
    _enum(
        value.get("type"),
        {
            "mapping",
            "conflict-resolution",
            "residual-acceptance",
            "behavior-verification",
        },
        f"{path}/type",
        errors,
    )
    _string(value.get("decision"), f"{path}/decision", errors)
    _date_time(value.get("decidedAt"), f"{path}/decidedAt", errors)


def _validate_residual(value, path, errors):
    fields = {
        "status",
        "reason",
        "impact",
        "remediation",
        "acceptanceDecisionId",
        "acceptancePlanDigest",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("status"),
        {"none", "pending-acceptance", "accepted", "rejected"},
        f"{path}/status",
        errors,
    )
    for field in ("reason", "impact", "remediation", "acceptanceDecisionId"):
        _string(value.get(field), f"{path}/{field}", errors, nullable=True)
    _digest(
        value.get("acceptancePlanDigest"),
        f"{path}/acceptancePlanDigest",
        errors,
        nullable=True,
    )
    if value.get("status") in {"accepted", "rejected"}:
        _string(
            value.get("acceptanceDecisionId"),
            f"{path}/acceptanceDecisionId",
            errors,
        )
        _digest(
            value.get("acceptancePlanDigest"),
            f"{path}/acceptancePlanDigest",
            errors,
        )


def _validate_mapping_verification(value, path, errors):
    fields = {"required", "mode", "criteria", "status", "evidenceDigest"}
    if not _object(value, path, fields, fields, errors):
        return
    _boolean(value.get("required"), f"{path}/required", errors)
    _enum(
        value.get("mode"),
        {"structural", "behavioral", "structural-and-behavioral", "manual"},
        f"{path}/mode",
        errors,
    )
    _string_array(value.get("criteria"), f"{path}/criteria", errors)
    _enum(
        value.get("status"),
        {"pending", "passed", "failed", "residual-accepted"},
        f"{path}/status",
        errors,
    )
    _digest(
        value.get("evidenceDigest"),
        f"{path}/evidenceDigest",
        errors,
        nullable=True,
    )
    if value.get("status") in {"passed", "residual-accepted"}:
        _digest(value.get("evidenceDigest"), f"{path}/evidenceDigest", errors)


def _validate_todos(todos, errors):
    fields = {
        "schemaVersion",
        "generationId",
        "sourceInventoryDigest",
        "capabilityContractDigest",
        "planDigest",
        "validation",
        "items",
    }
    if not _object(todos, "/todos", fields, fields, errors):
        return
    _enum(todos.get("schemaVersion"), {"2.0"}, "/todos/schemaVersion", errors)
    _string(todos.get("generationId"), "/todos/generationId", errors)
    for field in (
        "sourceInventoryDigest",
        "capabilityContractDigest",
        "planDigest",
    ):
        _digest(todos.get(field), f"/todos/{field}", errors)
    _validate_todo_validation(todos.get("validation"), errors)
    items = todos.get("items")
    if _array(items, "/todos/items", errors):
        for index, item in enumerate(items):
            _validate_todo(item, f"/todos/items/{index}", errors)


def _validate_todo_validation(value, errors):
    path = "/todos/validation"
    fields = {
        "schemaVersion",
        "status",
        "validatorVersion",
        "kind",
        "planDigest",
        "capabilityContractDigest",
        "sourceInventoryDigest",
        "resultDigest",
        "errors",
        "warnings",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("status"),
        {"not-run", "valid", "invalid", "stale", "failed"},
        f"{path}/status",
        errors,
    )
    for field in ("schemaVersion", "validatorVersion", "kind"):
        _string(value.get(field), f"{path}/{field}", errors, nullable=True)
    for field in (
        "planDigest",
        "capabilityContractDigest",
        "sourceInventoryDigest",
        "resultDigest",
    ):
        _digest(value.get(field), f"{path}/{field}", errors, nullable=True)
    for field in ("errors", "warnings"):
        issues = value.get(field)
        if _array(issues, f"{path}/{field}", errors):
            for index, issue in enumerate(issues):
                _validate_issue(issue, f"{path}/{field}/{index}", errors)
    if value.get("status") in {"valid", "invalid"}:
        _enum(value.get("schemaVersion"), {"1.0"}, f"{path}/schemaVersion", errors)
        _enum(
            value.get("kind"),
            {"AiGatewayMigrationPlanValidation"},
            f"{path}/kind",
            errors,
        )
        _string(value.get("validatorVersion"), f"{path}/validatorVersion", errors)
        for field in (
            "planDigest",
            "capabilityContractDigest",
            "sourceInventoryDigest",
            "resultDigest",
        ):
            _digest(value.get(field), f"{path}/{field}", errors)
    if value.get("status") == "valid" and value.get("errors"):
        errors.append(
            _issue(
                "schema-max-items",
                f"{path}/errors",
                "Valid plan validation cannot contain errors.",
            )
        )


def _validate_issue(value, path, errors):
    fields = {"code", "path", "message"}
    if not _object(value, path, fields, fields, errors):
        return
    _string(value.get("code"), f"{path}/code", errors)
    if not isinstance(value.get("path"), str):
        errors.append(
            _issue("schema-type", f"{path}/path", "Value must be a string.")
        )
    _string(value.get("message"), f"{path}/message", errors)


def _validate_todo(value, path, errors):
    fields = {
        "id",
        "mappingId",
        "sourceBehaviorIds",
        "capabilityRefs",
        "dependencies",
        "status",
        "approvalClass",
        "operation",
        "commandTemplate",
        "precondition",
        "idempotency",
        "approval",
        "verification",
        "rollback",
        "attempts",
        "blockingReason",
    }
    if not _object(value, path, fields, fields, errors):
        return
    for field in ("id", "mappingId"):
        _string(value.get(field), f"{path}/{field}", errors)
    for field, minimum in (
        ("sourceBehaviorIds", 0),
        ("capabilityRefs", 1),
        ("dependencies", 0),
    ):
        _string_array(
            value.get(field),
            f"{path}/{field}",
            errors,
            minimum=minimum,
            unique=True,
        )
    _enum(
        value.get("status"),
        {
            "pending",
            "approved",
            "in-progress",
            "mutation-unknown",
            "resource-verified",
            "behavior-verified",
            "failed",
            "blocked",
            "skipped",
        },
        f"{path}/status",
        errors,
    )
    _enum(
        value.get("approvalClass"),
        {"safe-batch", "consequential"},
        f"{path}/approvalClass",
        errors,
    )
    _validate_operation(value.get("operation"), f"{path}/operation", errors)
    _command(value.get("commandTemplate"), f"{path}/commandTemplate", errors)
    _validate_precondition(
        value.get("precondition"),
        f"{path}/precondition",
        errors,
    )
    _validate_idempotency(
        value.get("idempotency"),
        f"{path}/idempotency",
        errors,
    )
    _validate_approval(value.get("approval"), f"{path}/approval", errors)
    _validate_todo_verification(
        value.get("verification"),
        f"{path}/verification",
        errors,
    )
    _validate_rollback(value.get("rollback"), f"{path}/rollback", errors)
    attempts = value.get("attempts")
    if _array(attempts, f"{path}/attempts", errors):
        for index, attempt in enumerate(attempts):
            _validate_attempt(attempt, f"{path}/attempts/{index}", errors)
    _string(
        value.get("blockingReason"),
        f"{path}/blockingReason",
        errors,
        nullable=True,
    )
    status = value.get("status")
    operation_kind = (value.get("operation") or {}).get("kind")
    attempts = value.get("attempts") if isinstance(value.get("attempts"), list) else []
    if (
        status in {"resource-verified", "behavior-verified"}
        and operation_kind in {"create", "update", "delete", "sync", "action"}
        and not attempts
    ):
        errors.append(
            _issue(
                "schema-min-items",
                f"{path}/attempts",
                "Verified mutation TODOs require an execution attempt.",
            )
        )
    if status == "mutation-unknown" and not any(
        isinstance(attempt, dict) and attempt.get("outcome") == "unknown"
        for attempt in attempts
    ):
        errors.append(
            _issue(
                "schema-contains",
                f"{path}/attempts",
                "Mutation-unknown TODOs require an unknown outcome attempt.",
            )
        )
    source_behavior_ids = value.get("sourceBehaviorIds")
    behaviors = (value.get("verification") or {}).get("behaviors")
    requires_behavior_checks = (
        isinstance(source_behavior_ids, list) and bool(source_behavior_ids)
    )
    if requires_behavior_checks and not behaviors:
        errors.append(
            _issue(
                "schema-min-items",
                f"{path}/verification/behaviors",
                "TODO source behaviors require behavior verification records.",
            )
        )
    resource = (value.get("verification") or {}).get("resource") or {}
    if status in {"resource-verified", "behavior-verified"}:
        _enum(
            resource.get("status"),
            {"passed"},
            f"{path}/verification/resource/status",
            errors,
        )
    if status == "behavior-verified":
        for index, behavior in enumerate(behaviors or []):
            if isinstance(behavior, dict):
                _enum(
                    behavior.get("status"),
                    {"passed"},
                    f"{path}/verification/behaviors/{index}/status",
                    errors,
                )


def _validate_operation(value, path, errors):
    fields = {"kind", "commandGroup", "commandName", "targetKey"}
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("kind"),
        {"create", "update", "delete", "sync", "action", "verify"},
        f"{path}/kind",
        errors,
    )
    for field in fields - {"kind"}:
        _string(value.get(field), f"{path}/{field}", errors)


def _validate_precondition(value, path, errors):
    fields = {"commandTemplate", "expectedOutcome", "stateDigest", "status"}
    if not _object(value, path, fields, fields, errors):
        return
    _command(value.get("commandTemplate"), f"{path}/commandTemplate", errors)
    _string(value.get("expectedOutcome"), f"{path}/expectedOutcome", errors)
    _digest(
        value.get("stateDigest"),
        f"{path}/stateDigest",
        errors,
        nullable=True,
    )
    _enum(
        value.get("status"),
        {"not-checked", "satisfied", "changed", "inconclusive"},
        f"{path}/status",
        errors,
    )


def _validate_idempotency(value, path, errors):
    fields = {
        "strategy",
        "idempotencyKey",
        "desiredStateDigest",
        "retryPolicy",
        "unknownOutcomeAction",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("strategy"),
        {
            "read-before-create",
            "compare-before-update",
            "preview-before-sync",
            "verify-only",
            "non-repeatable",
        },
        f"{path}/strategy",
        errors,
    )
    _string(value.get("idempotencyKey"), f"{path}/idempotencyKey", errors)
    _digest(
        value.get("desiredStateDigest"),
        f"{path}/desiredStateDigest",
        errors,
        nullable=True,
    )
    _enum(
        value.get("retryPolicy"),
        {"safe", "verify-first", "never"},
        f"{path}/retryPolicy",
        errors,
    )
    _enum(
        value.get("unknownOutcomeAction"),
        {"read-current-state-before-retry"},
        f"{path}/unknownOutcomeAction",
        errors,
    )


def _validate_approval(value, path, errors):
    fields = {
        "status",
        "batchId",
        "approvedPlanDigest",
        "approvedPreconditionDigest",
        "approvedAt",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("status"),
        {"not-required", "pending", "approved", "invalidated", "rejected"},
        f"{path}/status",
        errors,
    )
    _string(value.get("batchId"), f"{path}/batchId", errors, nullable=True)
    for field in ("approvedPlanDigest", "approvedPreconditionDigest"):
        _digest(
            value.get(field),
            f"{path}/{field}",
            errors,
            nullable=True,
        )
    _date_time(value.get("approvedAt"), f"{path}/approvedAt", errors, nullable=True)
    if value.get("status") == "approved":
        for field in ("approvedPlanDigest", "approvedPreconditionDigest"):
            _digest(value.get(field), f"{path}/{field}", errors)
        _date_time(value.get("approvedAt"), f"{path}/approvedAt", errors)


def _validate_todo_verification(value, path, errors):
    fields = {"resource", "behaviors"}
    if not _object(value, path, fields, fields, errors):
        return
    resource = value.get("resource")
    resource_fields = {
        "commandTemplate",
        "expectedStateDigest",
        "observedStateDigest",
        "status",
        "evidence",
    }
    resource_path = f"{path}/resource"
    if _object(
        resource,
        resource_path,
        resource_fields,
        resource_fields,
        errors,
    ):
        _command(
            resource.get("commandTemplate"),
            f"{resource_path}/commandTemplate",
            errors,
        )
        for field in ("expectedStateDigest", "observedStateDigest"):
            _digest(
                resource.get(field),
                f"{resource_path}/{field}",
                errors,
                nullable=True,
            )
        _enum(
            resource.get("status"),
            {"not-run", "passed", "failed", "inconclusive"},
            f"{resource_path}/status",
            errors,
        )
        _string_array(
            resource.get("evidence"),
            f"{resource_path}/evidence",
            errors,
        )
    behaviors = value.get("behaviors")
    if _array(behaviors, f"{path}/behaviors", errors):
        for index, behavior in enumerate(behaviors):
            _validate_behavior(
                behavior,
                f"{path}/behaviors/{index}",
                errors,
            )


def _validate_behavior(value, path, errors):
    fields = {
        "behaviorId",
        "method",
        "expected",
        "observedDigest",
        "status",
        "evidence",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _string(value.get("behaviorId"), f"{path}/behaviorId", errors)
    _enum(
        value.get("method"),
        {
            "control-plane-read",
            "data-plane-probe",
            "administrator-attestation",
            "accepted-residual",
        },
        f"{path}/method",
        errors,
    )
    _string(value.get("expected"), f"{path}/expected", errors)
    _digest(
        value.get("observedDigest"),
        f"{path}/observedDigest",
        errors,
        nullable=True,
    )
    _enum(
        value.get("status"),
        {"not-run", "passed", "failed", "inconclusive", "not-applicable"},
        f"{path}/status",
        errors,
    )
    _string_array(value.get("evidence"), f"{path}/evidence", errors)


def _validate_rollback(value, path, errors):
    fields = {"mode", "commandTemplate", "guidance", "limitations"}
    if not _object(value, path, fields, fields, errors):
        return
    _enum(
        value.get("mode"),
        {"automatic", "manual", "none"},
        f"{path}/mode",
        errors,
    )
    _command(
        value.get("commandTemplate"),
        f"{path}/commandTemplate",
        errors,
        nullable=True,
    )
    _string(value.get("guidance"), f"{path}/guidance", errors, nullable=True)
    _string_array(value.get("limitations"), f"{path}/limitations", errors)


def _validate_attempt(value, path, errors):
    fields = {
        "attemptId",
        "startedAt",
        "finishedAt",
        "exitStatus",
        "outcome",
        "resultDigest",
        "reconciliation",
    }
    if not _object(value, path, fields, fields, errors):
        return
    _string(value.get("attemptId"), f"{path}/attemptId", errors)
    _date_time(value.get("startedAt"), f"{path}/startedAt", errors)
    _date_time(value.get("finishedAt"), f"{path}/finishedAt", errors, nullable=True)
    exit_status = value.get("exitStatus")
    if exit_status is not None and (
        isinstance(exit_status, bool) or not isinstance(exit_status, int)
    ):
        errors.append(
            _issue(
                "schema-type",
                f"{path}/exitStatus",
                "Value must be an integer or null.",
            )
        )
    _enum(
        value.get("outcome"),
        {"no-op", "applied", "unknown", "failed"},
        f"{path}/outcome",
        errors,
    )
    _digest(
        value.get("resultDigest"),
        f"{path}/resultDigest",
        errors,
        nullable=True,
    )
    reconciliation = value.get("reconciliation")
    reconciliation_fields = {
        "status",
        "observedStateDigest",
        "safeSummary",
    }
    reconciliation_path = f"{path}/reconciliation"
    if _object(
        reconciliation,
        reconciliation_path,
        reconciliation_fields,
        reconciliation_fields,
        errors,
    ):
        _enum(
            reconciliation.get("status"),
            {
                "not-required",
                "pending",
                "effect-present",
                "effect-absent",
                "ambiguous",
            },
            f"{reconciliation_path}/status",
            errors,
        )
        _digest(
            reconciliation.get("observedStateDigest"),
            f"{reconciliation_path}/observedStateDigest",
            errors,
            nullable=True,
        )
        _string(
            reconciliation.get("safeSummary"),
            f"{reconciliation_path}/safeSummary",
            errors,
            nullable=True,
        )


def validate_migration_state(context, mapping, todos):
    errors = []
    _validate_context(context, errors)
    _validate_mapping(mapping, errors)
    _validate_todos(todos, errors)
    return errors
