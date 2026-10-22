# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_ai_gateway._import_discovery import (
    _backend_summary,
    _policy_summary,
    _safe_url,
    _sanitize_properties,
)


_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_FILES = 10000
_UNRESOLVED = object()
_COLLECTION_TYPES = {
    "apis": "api",
    "operations": "operation",
    "backends": "backend",
    "namedvalues": "namedValue",
    "policyfragments": "policyFragment",
    "products": "product",
    "subscriptions": "subscription",
    "diagnostics": "diagnostic",
    "loggers": "logger",
    "certificates": "certificate",
    "groups": "group",
    "identityproviders": "identityProvider",
    "authorizationproviders": "authorizationProvider",
}
_RELATED_FIELDS = {
    "namedValue": ("displayName", "secret", "tags"),
    "policyFragment": ("description", "format"),
    "product": (
        "displayName",
        "description",
        "subscriptionRequired",
        "approvalRequired",
        "state",
    ),
    "subscription": ("displayName", "scope", "state"),
    "diagnostic": ("loggerId", "alwaysLog", "sampling"),
    "logger": ("loggerType", "isBuffered", "resourceId", "credentials"),
    "certificate": ("subject", "thumbprint", "expirationDate"),
    "group": ("displayName", "description", "type", "externalId"),
    "identityProvider": ("type", "allowedTenants", "authority"),
    "authorizationProvider": ("displayName", "identityProvider"),
}


def _normalized(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _name(value):
    value = str(value or "").strip()
    if not value or "[" in value or "]" in value:
        return None
    return value.rsplit("/", 1)[-1]


def _child_id(parent_id, collection, name):
    return f"{parent_id}/{collection}/{quote(name, safe='')}"


def _evidence(source_type, path):
    return {
        "sourceType": source_type,
        "authority": "administratorExport",
        "path": path,
    }


def _safe_property(value, name):
    if _normalized(name) == "urltemplate" and isinstance(value, str):
        return _safe_url(value)
    return _sanitize_properties(value, name)


def _without_arm_expressions(
    value,
    source_type,
    logical_path,
    resource_index,
    warnings,
    property_path="properties",
):
    if isinstance(value, str) and value.strip().startswith("["):
        warnings.append(
            {
                "sourceType": source_type,
                "path": logical_path,
                "code": "UnresolvedArmExpression",
                "resourceIndex": resource_index,
                "propertyPath": property_path,
            }
        )
        return _UNRESOLVED
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            sanitized = _without_arm_expressions(
                item,
                source_type,
                logical_path,
                resource_index,
                warnings,
                f"{property_path}.{key}",
            )
            if sanitized is not _UNRESOLVED:
                result[key] = sanitized
        return result
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            sanitized = _without_arm_expressions(
                item,
                source_type,
                logical_path,
                resource_index,
                warnings,
                f"{property_path}[{index}]",
            )
            if sanitized is not _UNRESOLVED:
                result.append(sanitized)
        return result
    return value




def _read_text(path):
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            raise InvalidArgumentValueError(
                f"Export artifact '{path.name}' exceeds the 10 MiB limit."
            )
        return path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise InvalidArgumentValueError(
            f"Unable to read export artifact '{path.name}': {error}"
        ) from error


def _read_json(path):
    try:
        value = json.loads(_read_text(path))
    except ValueError as error:
        raise InvalidArgumentValueError(
            f"Export artifact '{path.name}' is not valid JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise InvalidArgumentValueError(
            f"Export artifact '{path.name}' must contain a JSON object."
        )
    return value


def _export_metadata(payload, source_id, source, allow_completeness):
    container = payload.get("metadata") or {}
    metadata = container.get("aiGatewayMigration") if isinstance(container, dict) else None
    if payload.get("kind") == "AiGatewayApimExportEvidence":
        metadata = payload
    if metadata is None:
        return {
            "sourceResourceId": None,
            "sourceSku": None,
            "exportedAt": None,
            "sourceEtag": None,
            "completenessClaims": [],
        }
    if not isinstance(metadata, dict):
        raise InvalidArgumentValueError(
            "Export evidence metadata must be a JSON object."
        )
    metadata_source_id = metadata.get("sourceResourceId")
    if metadata_source_id and (
        str(metadata_source_id).rstrip("/").casefold()
        != source_id.rstrip("/").casefold()
    ):
        raise InvalidArgumentValueError(
            "Export evidence sourceResourceId does not match --source-apim-id."
        )
    metadata_sku = metadata.get("sourceSku")
    live_sku = source.get("sku")
    if metadata_sku and live_sku and (
        str(metadata_sku).casefold() != str(live_sku).casefold()
    ):
        raise InvalidArgumentValueError(
            "Export evidence sourceSku does not match the live APIM resource."
        )
    exported_at = metadata.get("exportedAt")
    metadata_etag = metadata.get("sourceEtag")
    live_etag = source.get("etag")
    if metadata_etag and live_etag and metadata_etag != live_etag:
        raise InvalidArgumentValueError(
            "Export evidence sourceEtag does not match the live APIM resource."
        )

    if exported_at is not None:
        if not isinstance(exported_at, str):
            raise InvalidArgumentValueError(
                "Export evidence exportedAt must be an ISO 8601 string."
            )
        try:
            parsed = datetime.fromisoformat(exported_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise InvalidArgumentValueError(
                "Export evidence exportedAt must be an ISO 8601 string."
            ) from error
        if parsed.tzinfo is None:
            raise InvalidArgumentValueError(
                "Export evidence exportedAt must include a UTC offset."
            )
    claims = metadata.get("completeDomains") or []
    if not isinstance(claims, list):
        raise InvalidArgumentValueError(
            "Export evidence completeDomains must be an array."
        )
    if allow_completeness and claims and (
        not metadata_source_id or not exported_at
    ):
        raise InvalidArgumentValueError(
            "Authoritative completeDomains require sourceResourceId and exportedAt."
        )
    normalized_claims = []
    if allow_completeness:
        for claim in claims:
            if not isinstance(claim, dict):
                raise InvalidArgumentValueError(
                    "Each completeDomains entry must be a JSON object."
                )
            scope = claim.get("scope")
            domain = claim.get("configurationDomain")
            if scope == "service":
                scope = source_id
            if not isinstance(scope, str) or not isinstance(domain, str):
                raise InvalidArgumentValueError(
                    "Each completeDomains entry requires scope and configurationDomain."
                )
            normalized_claims.append(
                {
                    "scope": scope.rstrip("/"),
                    "configurationDomain": domain,
                }
            )
    return {
        "sourceResourceId": metadata_source_id,
        "sourceSku": metadata_sku,
        "exportedAt": exported_at,
        "sourceEtag": metadata_etag,
        "completenessClaims": sorted(
            normalized_claims,
            key=lambda item: (
                item["scope"].casefold(),
                item["configurationDomain"].casefold(),
            ),
        ),
    }

def _files(path_value, allow_directory):
    path = Path(path_value).expanduser()
    if not path.exists():
        raise InvalidArgumentValueError(
            f"Export artifact path '{path_value}' does not exist."
        )
    if path.is_symlink():
        raise InvalidArgumentValueError(
            "Export artifact paths must not be symbolic links."
        )
    if path.is_file():
        return path.parent.resolve(), [path.resolve()]
    if not allow_directory or not path.is_dir():
        raise InvalidArgumentValueError(
            f"Export artifact path '{path_value}' must be a JSON file."
        )
    root = path.resolve()
    result = []
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink():
            raise InvalidArgumentValueError(
                f"APIOps artifact contains symbolic link '{candidate.name}'."
            )
        if not candidate.is_file():
            continue
        if candidate.suffix.casefold() not in {".json", ".xml"}:
            continue
        resolved = candidate.resolve()
        if root not in resolved.parents:
            continue
        result.append(resolved)
        if len(result) > _MAX_FILES:
            raise InvalidArgumentValueError(
                "The APIOps artifact contains more than 10000 files."
            )
    return root, result


def _relative(root, path):
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _api_payload(source_id, name, properties, workspace, provenance):
    scope_id = (
        _child_id(source_id, "workspaces", workspace) if workspace else source_id
    )
    stable_id = _child_id(scope_id, "apis", name)
    properties = properties if isinstance(properties, dict) else {}
    api_type = properties.get("type") or properties.get("apiType")
    safe_properties = {
        field: _sanitize_properties(properties.get(field), field)
        for field in (
            "displayName", "description", "path", "serviceUrl", "protocols",
            "subscriptionRequired", "type", "apiType", "apiRevision",
            "apiRevisionDescription", "isCurrent", "apiVersion",
            "apiVersionSetId", "mcpProperties", "backendId",
        )
        if field in properties
    }
    return {
        "id": stable_id,
        "stableId": stable_id,
        "scope": {
            "type": "workspace" if workspace else "service",
            "workspace": workspace,
        },
        "api": {
            "id": stable_id,
            "name": name,
            "displayName": properties.get("displayName"),
            "description": properties.get("description"),
            "workspace": workspace,
            "apiType": api_type,
            "path": properties.get("path"),
            "serviceUrl": _safe_url(properties.get("serviceUrl")),
            "protocols": properties.get("protocols") or [],
            "subscriptionRequired": bool(properties.get("subscriptionRequired")),
            "properties": safe_properties,
        },
        "revision": {
            field: properties.get(field)
            for field in (
                "apiRevision", "apiRevisionDescription", "isCurrent",
                "apiVersion", "apiVersionSetId",
            )
        },
        "mcpProperties": _sanitize_properties(properties.get("mcpProperties") or {}),
        "backends": [],
        "policies": {"api": None, "inherited": [], "operations": [], "products": []},
        "operations": [],
        "schemas": [],
        "releases": [],
        "products": [],
        "subscriptions": [],
        "tools": [],
        "mcpDependencies": [],
        "diagnostics": [],
        "loggerReferences": [],
        "provenance": [provenance],
        "provenanceAuthority": provenance["sourceType"],
    }


def _operation_payload(stable_id, name, properties, provenance):
    properties = properties if isinstance(properties, dict) else {}
    return {
        "id": stable_id,
        "name": name,
        "displayName": properties.get("displayName"),
        "method": properties.get("method"),
        "urlTemplate": _safe_property(properties.get("urlTemplate"), "urlTemplate"),
        "properties": {
            field: _safe_property(properties.get(field), field)
            for field in (
                "displayName", "description", "method", "urlTemplate",
                "templateParameters", "request", "responses",
            )
            if field in properties
        },
        "policy": None,
        "provenance": [provenance],
        "provenanceAuthority": provenance["sourceType"],
    }


def _related_payload(stable_id, name, kind, properties, provenance):
    properties = properties if isinstance(properties, dict) else {}
    result = {
        "id": stable_id,
        "name": name,
        "type": kind,
        "properties": {
            field: _sanitize_properties(properties.get(field), field)
            for field in _RELATED_FIELDS.get(kind, ())
            if field in properties
        },
        "provenance": [provenance],
        "provenanceAuthority": provenance["sourceType"],
    }
    if kind == "namedValue":
        result.update({
            "displayName": properties.get("displayName"),
            "secret": bool(properties.get("secret")),
            "tags": properties.get("tags") or [],
            "value": "<redacted>",
        })
    if kind == "policyFragment":
        result.update({
            "hasValue": properties.get("value") is not None,
            "value": "<redacted>" if properties.get("value") is not None else None,
        })
    return result


def _record(source_id, kind, name, properties, provenance, workspace=None, api_name=None):
    scope_id = (
        _child_id(source_id, "workspaces", workspace) if workspace else source_id
    )
    if kind == "api":
        payload = _api_payload(source_id, name, properties, workspace, provenance)
        return {"kind": kind, "stableId": payload["id"], "scopeId": scope_id,
                "payload": payload, "provenance": provenance}
    if kind == "operation" and api_name:
        api_id = _child_id(scope_id, "apis", api_name)
        stable_id = _child_id(api_id, "operations", name)
        return {"kind": kind, "stableId": stable_id, "scopeId": scope_id,
                "apiId": api_id,
                "payload": _operation_payload(stable_id, name, properties, provenance),
                "provenance": provenance}
    collection = {value: key for key, value in _COLLECTION_TYPES.items()}.get(kind)
    if not collection:
        return None
    stable_id = _child_id(scope_id, collection, name)
    if kind == "backend":
        payload = _backend_summary(
            {"id": stable_id, "name": name, "properties": properties}
        )
        payload["provenance"] = [provenance]
    else:
        payload = _related_payload(stable_id, name, kind, properties, provenance)
    return {"kind": kind, "stableId": stable_id, "scopeId": scope_id,
            "payload": payload, "provenance": provenance}


def _apiops_location(path):
    parts = Path(path).parts
    normalized = [_normalized(part) for part in parts]
    workspace = None
    api_name = None
    if "workspaces" in normalized:
        index = normalized.index("workspaces")
        workspace = _name(parts[index + 1]) if len(parts) > index + 1 else None
    if "apis" in normalized:
        index = normalized.index("apis")
        api_name = _name(parts[index + 1]) if len(parts) > index + 1 else None
    for index in range(len(parts) - 1, -1, -1):
        kind = _COLLECTION_TYPES.get(normalized[index])
        if kind and len(parts) > index + 1:
            return kind, _name(parts[index + 1]), workspace, api_name
    return None, None, workspace, api_name


def _template_records(source_id, template, source_type, logical_path, warnings):
    records = []

    def visit(resources, parent_types=(), parent_names=()):
        if not isinstance(resources, list):
            return
        for index, resource in enumerate(resources):
            if not isinstance(resource, dict):
                continue
            resource_type = str(resource.get("type") or "")
            resource_name = str(resource.get("name") or "")
            if not resource_type or not resource_name or "[" in resource_name:
                warnings.append({"sourceType": source_type, "path": logical_path,
                                 "code": "UnresolvedArmExpression",
                                 "resourceIndex": index})
                continue
            if resource_type.casefold().startswith("microsoft.apimanagement/"):
                types = resource_type.split("/")[1:]
                names = resource_name.split("/")
            else:
                types = [*parent_types, *resource_type.split("/")]
                names = [*parent_names, *resource_name.split("/")]
            normalized = [_normalized(part) for part in types]
            source_name = source_id.rstrip("/").rsplit("/", 1)[-1]
            if normalized and normalized[0] == "service" and (
                not names or str(names[0]).casefold() != source_name.casefold()
            ):
                continue
            if normalized and normalized[0] == "service":
                workspace = None
                api_name = None
                kind = None
                name = None
                for part_index, segment in enumerate(normalized):
                    if segment == "workspaces" and len(names) > part_index:
                        workspace = _name(names[part_index])
                    if segment == "apis" and len(names) > part_index:
                        api_name = _name(names[part_index])
                    if segment in _COLLECTION_TYPES and len(names) > part_index:
                        kind = _COLLECTION_TYPES[segment]
                        name = _name(names[part_index])
                if kind and name:
                    properties = _without_arm_expressions(
                        resource.get("properties") or {},
                        source_type,
                        logical_path,
                        index,
                        warnings,
                    )
                    candidate = _record(
                        source_id, kind, name, properties,
                        _evidence(source_type, logical_path), workspace, api_name,
                    )
                    if candidate:
                        records.append(candidate)
            visit(resource.get("resources"), types, names)

    visit(template.get("resources"))
    return records


def _load_apiops(source_id, source, path_value):
    root, files = _files(path_value, True)
    records = []
    warnings = []
    metadata = _export_metadata({}, source_id, source, True)
    metadata_file = next(
        (
            path
            for path in files
            if _relative(root, path).casefold() == "inventory-metadata.json"
        ),
        None,
    )
    if metadata_file:
        metadata = _export_metadata(
            _read_json(metadata_file), source_id, source, True
        )
    for path in files:
        if path == metadata_file:
            continue
        relative = _relative(root, path)
        kind, name, workspace, api_name = _apiops_location(relative)
        if path.suffix.casefold() == ".xml":
            if path.name.casefold() != "policy.xml" or not api_name:
                continue
            scope_id = (
                _child_id(source_id, "workspaces", workspace)
                if workspace else source_id
            )
            api_id = _child_id(scope_id, "apis", api_name)
            policy = _policy_summary(_read_text(path), api_id, "api")
            for key in ("translatedPolicies", "translatedPolicyRecords", "translationWarnings"):
                policy.pop(key, None)
            provenance = _evidence("apiops", relative)
            records.append({"kind": "apiPolicy", "apiId": api_id,
                            "stableId": f"{api_id}/policies/policy",
                            "scopeId": scope_id, "payload": policy,
                            "provenance": provenance})
            continue
        payload = _read_json(path)
        if "resources" in payload:
            records.extend(_template_records(
                source_id, payload, "apiops", relative, warnings
            ))
        elif kind and name:
            candidate = _record(
                source_id, kind, name, payload.get("properties") or payload,
                _evidence("apiops", relative), workspace, api_name,
            )
            if candidate:
                records.append(candidate)
    observed = sorted(
        {(record["scopeId"], record["kind"]) for record in records}
    )
    return records, {
        "sourceType": "apiops",
        "path": Path(path_value).name,
        "filesRead": len(files),
        **metadata,
        "observedResources": [
            {"scope": scope, "resourceType": kind}
            for scope, kind in observed
        ],
    }, warnings


def _load_template(source_id, source, path_value):
    root, files = _files(path_value, False)
    path = files[0]
    if path.suffix.casefold() != ".json":
        raise InvalidArgumentValueError("--arm-template-file must identify a JSON file.")
    payload = _read_json(path)
    metadata = _export_metadata(payload, source_id, source, False)
    if not isinstance(payload.get("resources"), list):
        raise InvalidArgumentValueError(
            "--arm-template-file must contain an ARM template resources array."
        )
    warnings = []
    records = _template_records(
        source_id, payload, "armTemplate", _relative(root, path), warnings
    )
    observed = sorted(
        {(record["scopeId"], record["kind"]) for record in records}
    )
    return records, {
        "sourceType": "armTemplate",
        "path": path.name,
        "filesRead": 1,
        **metadata,
        "completenessClaims": [],
        "observedResources": [
            {"scope": scope, "resourceType": kind}
            for scope, kind in observed
        ],
    }, warnings


def _append_provenance(resource, evidence):
    resource.setdefault("provenanceAuthority", evidence["sourceType"])
    provenance = resource.setdefault("provenance", [])
    if evidence not in provenance:
        provenance.append(deepcopy(evidence))
        provenance.sort(key=lambda item: (
            item.get("sourceType") != "arm", str(item.get("sourceType") or ""),
            str(item.get("path") or ""),
        ))


def _annotate_live(result):
    evidence = {"sourceType": "arm", "authority": "live",
                "resourceId": (result.get("source") or {}).get("id")}
    _append_provenance(result["source"], evidence)
    for scope in result.get("scopes") or []:
        _append_provenance(scope, evidence)
        for family in ("backends", "diagnostics", "loggers"):
            for resource in scope.get(family) or []:
                _append_provenance(resource, evidence)
        for resources in (scope.get("relatedResources") or {}).values():
            for resource in resources:
                _append_provenance(resource, evidence)
    for api in result.get("apis") or []:
        _append_provenance(api, evidence)
        for family in ("backends", "operations", "products", "subscriptions",
                       "tools", "diagnostics", "loggerReferences"):
            for resource in api.get(family) or []:
                if isinstance(resource, dict):
                    _append_provenance(resource, evidence)
    for resources in (result.get("relatedResources") or {}).values():
        if isinstance(resources, list):
            for resource in resources:
                _append_provenance(resource, evidence)


def _incomplete(result, scope_id, domain):
    normalized_scope = scope_id.rstrip("/").casefold()
    workspace_marker = "/workspaces/"
    matching = []
    for item in result.get("collectionCoverage") or []:
        coverage_scope = str(item.get("scope") or "").rstrip("/").casefold()
        if (
            item.get("configurationDomain") != domain
            or (
                coverage_scope != normalized_scope
                and not coverage_scope.startswith(f"{normalized_scope}/")
            )
        ):
            continue
        if (
            workspace_marker not in normalized_scope
            and coverage_scope[len(normalized_scope):].startswith(
                workspace_marker
            )
        ):
            continue
        matching.append(item)
    return not matching or any(
        item.get("status") in {"failed", "partial"} for item in matching
    )


def _conflict(conflicts, stable_id, field, selected, other):
    value = {"stableId": stable_id, "field": field,
             "selectedSource": selected, "otherSource": other}
    if value not in conflicts:
        conflicts.append(value)


def _semantic_resource(resource, family):
    ignored = {
        "etag",
        "id",
        "name",
        "properties",
        "provenance",
        "provenanceAuthority",
        "scopeType",
        "type",
    }
    semantic_fields = {
        "operations": (
            "displayName",
            "description",
            "method",
            "urlTemplate",
            "templateParameters",
            "request",
            "responses",
        ),
        "backends": ("url", "protocol", "resourceId", "credentials"),
        "namedValues": _RELATED_FIELDS["namedValue"],
        "policyFragments": _RELATED_FIELDS["policyFragment"],
        "products": _RELATED_FIELDS["product"],
        "subscriptions": _RELATED_FIELDS["subscription"],
        "diagnostics": _RELATED_FIELDS["diagnostic"],
        "loggers": _RELATED_FIELDS["logger"],
        "certificates": _RELATED_FIELDS["certificate"],
        "groups": _RELATED_FIELDS["group"],
        "identityProviders": _RELATED_FIELDS["identityProvider"],
        "authorizationProviders": _RELATED_FIELDS["authorizationProvider"],
    }.get(family)
    properties = resource.get("properties") or {}
    if semantic_fields is not None:
        result = {
            field: deepcopy(
                resource[field]
                if field in resource
                else properties.get(field)
            )
            for field in semantic_fields
        }
        if family == "operations":
            result["urlTemplate"] = _safe_url(result.get("urlTemplate"))
        return result
    result = deepcopy(properties)
    for key, value in resource.items():
        if key not in ignored and key != "policy":
            result[key] = deepcopy(value)
    return result


def _semantic_api(api):
    properties = api.get("properties") or {}
    fields = (
        "apiRevision",
        "apiRevisionDescription",
        "apiType",
        "apiVersion",
        "apiVersionSetId",
        "backendId",
        "description",
        "displayName",
        "isCurrent",
        "mcpProperties",
        "path",
        "protocols",
        "serviceUrl",
        "subscriptionRequired",
        "workspace",
    )
    return {
        field: deepcopy(
            api[field] if field in api else properties.get(field)
        )
        for field in fields
    }


def _merge_list(resources, candidate, evidence, conflicts, field):
    key = str(candidate.get("id") or candidate.get("name") or "").casefold()
    existing = next((item for item in resources
                     if str(item.get("id") or item.get("name") or "").casefold() == key), None)
    if existing is None:
        resources.append(deepcopy(candidate))
        return
    if _semantic_resource(existing, field) != _semantic_resource(
        candidate,
        field,
    ):
        selected = existing.get("provenanceAuthority")
        _conflict(conflicts, candidate.get("id"), field, selected, evidence["sourceType"])
    _append_provenance(existing, evidence)


def _scope(result, scope_id, workspace, evidence):
    existing = next((item for item in result.get("scopes") or []
                     if str(item.get("id") or "").casefold() == scope_id.casefold()), None)
    if existing:
        _append_provenance(existing, evidence)
        return existing
    value = {"id": scope_id, "name": workspace,
             "scopeType": "workspace" if workspace else "service", "apiIds": [],
             "policy": None, "backends": [], "diagnostics": [], "loggers": [],
             "relatedResources": {"namedValues": [], "policyFragments": [],
                                  "products": [], "subscriptions": []},
             "provenance": [evidence]}
    result.setdefault("scopes", []).append(value)
    return value


def _merge(result, records, conflicts):
    apis = {str(item.get("stableId") or item.get("id") or "").casefold(): item
            for item in result.get("apis") or []}
    records = sorted(records, key=lambda item: (
        item["stableId"].casefold(), item["kind"], item["provenance"].get("path", "")
    ))
    for record in records:
        kind = record["kind"]
        evidence = record["provenance"]
        candidate_scope = record.get("payload", {}).get("scope")
        workspace = (
            candidate_scope.get("workspace") if isinstance(candidate_scope, dict) else None
        )
        scope = _scope(result, record["scopeId"], workspace, evidence)
        if kind == "api":
            existing = apis.get(record["stableId"].casefold())
            if existing is None:
                existing = deepcopy(record["payload"])
                result.setdefault("apis", []).append(existing)
                apis[record["stableId"].casefold()] = existing
                scope["apiIds"].append(record["stableId"])
            else:
                differs = _semantic_api(
                    existing.get("api") or {}
                ) != _semantic_api(record["payload"].get("api") or {})
                previous_source = existing.get("provenanceAuthority")
                ranks = {"arm": 0, "armTemplate": 1, "apiops": 2}
                selected_rank = ranks.get(
                    existing.get("provenanceAuthority"), 0
                )
                candidate_rank = ranks[evidence["sourceType"]]
                if (
                    _incomplete(result, record["scopeId"], "apis")
                    and candidate_rank > selected_rank
                ):
                    for field in ("api", "revision", "mcpProperties"):
                        if record["payload"].get(field):
                            existing[field] = deepcopy(record["payload"][field])
                    existing["provenanceAuthority"] = evidence["sourceType"]
                if differs:
                    _conflict(
                        conflicts,
                        record["stableId"],
                        "api",
                        existing.get("provenanceAuthority"),
                        (
                            previous_source
                            if existing.get("provenanceAuthority")
                            != previous_source
                            else evidence["sourceType"]
                        ),
                    )
                _append_provenance(existing, evidence)
        elif kind in {"operation", "apiPolicy"}:
            api = apis.get(str(record.get("apiId") or "").casefold())
            if not api:
                continue
            if kind == "operation":
                _merge_list(api.setdefault("operations", []), record["payload"],
                            evidence, conflicts, "operations")
            else:
                current = api.setdefault("policies", {}).get("api")
                differs = current and current != record["payload"]
                previous_source = api.get("provenanceAuthority")
                use_export = current is None or _incomplete(
                    result,
                    record["scopeId"],
                    "policies",
                )
                if use_export:
                    api["policies"]["api"] = deepcopy(record["payload"])
                if differs:
                    _conflict(
                        conflicts,
                        record["stableId"],
                        "policy",
                        (
                            evidence["sourceType"]
                            if use_export
                            else previous_source
                        ),
                        (
                            previous_source
                            if use_export
                            else evidence["sourceType"]
                        ),
                    )
                _append_provenance(api, evidence)
        elif kind == "backend":
            _merge_list(scope["backends"], record["payload"], evidence,
                        conflicts, "backends")
        else:
            family = {"namedValue": "namedValues", "policyFragment": "policyFragments",
                      "product": "products", "subscription": "subscriptions"}.get(kind)
            if family:
                target = scope["relatedResources"].setdefault(family, [])
            else:
                family = {"diagnostic": "diagnostics", "logger": "loggers"}.get(kind)
                target = scope.setdefault(family, []) if family else None
            if target is None:
                family = {"certificate": "certificates", "group": "groups",
                          "identityProvider": "identityProviders",
                          "authorizationProvider": "authorizationProviders"}.get(kind)
                target = result.setdefault("relatedResources", {}).setdefault(family, []) if family else None
            if target is not None:
                _merge_list(target, record["payload"], evidence, conflicts, family)


def _ledger_entry(resource_id, kind, scope, provenance, details):
    return {"id": f"{resource_id}#behavior/{kind}",
            "sourceResourceId": resource_id, "behaviorType": kind,
            "scope": scope, "provenance": deepcopy(provenance or []),
            "details": _sanitize_properties(details)}


def _ledger(result):
    values = []
    for api in result.get("apis") or []:
        api_id = api.get("stableId") or api.get("id")
        if not api_id:
            continue
        scope = api.get("scope") or {}
        source = api.get("api") or {}
        provenance = api.get("provenance") or []
        values.append(_ledger_entry(api_id, "apiConfiguration", scope, provenance, {
            "name": source.get("name"), "apiType": source.get("apiType"),
            "path": source.get("path"), "serviceUrl": source.get("serviceUrl"),
            "protocols": source.get("protocols") or [],
            "subscriptionRequired": source.get("subscriptionRequired"),
        }))
        for operation in api.get("operations") or []:
            if operation.get("id"):
                values.append(_ledger_entry(
                    operation["id"], "operation", scope,
                    operation.get("provenance") or provenance,
                    {"name": operation.get("name"), "method": operation.get("method"),
                     "urlTemplate": operation.get("urlTemplate")}
                ))
        occurrences = (((api.get("policies") or {}).get("api") or {}).get(
            "statementOccurrences") or [])
        for index, occurrence in enumerate(occurrences):
            values.append(_ledger_entry(
                f"{api_id}/policies/policy/{index}", "policyStatement",
                scope, provenance, occurrence
            ))
        for family, kind in (("backends", "backendDependency"),
                             ("products", "productRelationship"),
                             ("subscriptions", "subscriptionRelationship"),
                             ("tools", "mcpTool"), ("diagnostics", "diagnostic"),
                             ("loggerReferences", "loggerReference")):
            for resource in api.get(family) or []:
                resource_id = resource.get("id") or resource.get("name")
                if resource_id:
                    values.append(_ledger_entry(
                        resource_id, kind, scope,
                        resource.get("provenance") or provenance,
                        {"name": resource.get("name"),
                         "properties": resource.get("properties")}
                    ))
    for scope in result.get("scopes") or []:
        scope_ref = {"type": scope.get("scopeType"), "workspace": scope.get("name")}
        families = {"backends": scope.get("backends") or [],
                    "diagnostics": scope.get("diagnostics") or [],
                    "loggers": scope.get("loggers") or [],
                    **(scope.get("relatedResources") or {})}
        for family, resources in families.items():
            for resource in resources:
                resource_id = resource.get("id") or resource.get("name")
                if resource_id:
                    values.append(_ledger_entry(
                        resource_id, family, scope_ref,
                        resource.get("provenance") or scope.get("provenance"),
                        {"name": resource.get("name"),
                         "properties": resource.get("properties")}
                    ))
    return sorted({item["id"]: item for item in values}.values(),
                  key=lambda item: item["id"].casefold())



def _domain_for_resource(resource_type):
    return {
        "api": "apis",
        "operation": "operations",
        "apiPolicy": "policies",
        "backend": "backends",
        "namedValue": "namedValues",
        "policyFragment": "policyFragments",
        "product": "products",
        "subscription": "subscriptions",
        "diagnostic": "diagnostics",
        "logger": "loggers",
        "certificate": "certificates",
        "group": "groups",
        "identityProvider": "identityProviders",
        "authorizationProvider": "authorizationProviders",
    }.get(resource_type)


def _coverage_owner(scope, source_id):
    scope = str(scope or "").rstrip("/")
    lower = scope.casefold()
    marker = "/workspaces/"
    if marker in lower:
        marker_index = lower.index(marker) + len(marker)
        suffix = scope[marker_index:]
        workspace = suffix.split("/", 1)[0]
        return f"{scope[:marker_index]}{workspace}"
    return source_id.rstrip("/")


def _source_has_domain(source, owner, domain):
    for observed in source.get("observedResources") or []:
        if (
            str(observed.get("scope") or "").rstrip("/").casefold()
            == owner.rstrip("/").casefold()
            and _domain_for_resource(observed.get("resourceType")) == domain
        ):
            return True
    return False


def _source_claims_domain(source, owner, domain):
    return any(
        str(claim.get("scope") or "").rstrip("/").casefold()
        == owner.rstrip("/").casefold()
        and claim.get("configurationDomain") == domain
        for claim in source.get("completenessClaims") or []
    )


def _domain_has_conflict(conflicts, owner, domain):
    field_domains = {
        "api": "apis",
        "policy": "policies",
        "operations": "operations",
    }
    return any(
        str(conflict.get("stableId") or "").casefold().startswith(
            owner.rstrip("/").casefold()
        )
        and field_domains.get(conflict.get("field"), conflict.get("field"))
        == domain
        for conflict in conflicts
    )


def _reconcile_coverage(result, export_sources, conflicts, source_id):
    summary = result.setdefault("summary", {})
    summary["liveArmDiscoveryComplete"] = summary.get("discoveryComplete", False)
    summary["liveArmRequiredDiscoveryComplete"] = summary.get(
        "requiredDiscoveryComplete", False
    )
    authorities = []
    recovered = set()
    for coverage in result.get("collectionCoverage") or []:
        domain = coverage.get("configurationDomain")
        owner = _coverage_owner(coverage.get("scope"), source_id)
        original_status = coverage.get("status")
        if original_status in {"complete", "empty", "notApplicable"}:
            authorities.append(
                {
                    "scope": owner,
                    "configurationDomain": domain,
                    "authority": "arm",
                    "evidenceRole": "authoritative",
                    "establishesCompleteness": True,
                    "originalStatus": original_status,
                    "effectiveStatus": original_status,
                    "evidenceSources": ["arm"],
                }
            )
            continue
        apiops = next(
            (
                source
                for source in export_sources
                if source.get("sourceType") == "apiops"
                and (
                    _source_has_domain(source, owner, domain)
                    or _source_claims_domain(source, owner, domain)
                )
            ),
            None,
        )
        template = next(
            (
                source
                for source in export_sources
                if source.get("sourceType") == "armTemplate"
                and _source_has_domain(source, owner, domain)
            ),
            None,
        )
        evidence_sources = [
            source_type
            for source_type, source in (
                ("apiops", apiops),
                ("armTemplate", template),
                ("arm", True),
            )
            if source
        ]
        conflict = _domain_has_conflict(conflicts, owner, domain)
        authoritative_apiops = (
            apiops is not None
            and _source_claims_domain(apiops, owner, domain)
            and not conflict
        )
        if authoritative_apiops:
            coverage["originalStatus"] = original_status
            coverage["status"] = "complete"
            coverage["recoveredBy"] = "apiops"
            coverage["authoritative"] = True
            recovered.add((owner.casefold(), domain))
            authority = "apiops"
            role = "authoritative"
            effective_status = "recovered"
        else:
            authority = None
            role = "blocked" if conflict or not evidence_sources[:-1] else "supplemental"
            effective_status = "blocked"
        authorities.append(
            {
                "scope": owner,
                "configurationDomain": domain,
                "authority": authority,
                "evidenceRole": role,
                "establishesCompleteness": authoritative_apiops,
                "originalStatus": original_status,
                "effectiveStatus": effective_status,
                "evidenceSources": evidence_sources,
            }
        )
    for error in result.get("discoveryErrors") or []:
        key = (
            _coverage_owner(error.get("scope"), source_id).casefold(),
            error.get("configurationDomain"),
        )
        if key in recovered:
            error["effectiveStatus"] = "recovered"
            error["recoveredBy"] = "apiops"
    authorities.sort(
        key=lambda item: (
            item["scope"].casefold(),
            str(item.get("configurationDomain") or "").casefold(),
        )
    )
    result["domainAuthority"] = authorities
    coverage = result.get("collectionCoverage") or []
    coverage_complete = (
        all(
            item.get("status") in {"complete", "empty", "notApplicable"}
            for item in coverage
        )
        if coverage else not result.get("discoveryErrors")
    )
    required_incomplete = any(
        error.get("required", True)
        and error.get("effectiveStatus") != "recovered"
        for error in result.get("discoveryErrors") or []
    )
    summary["discoveryComplete"] = coverage_complete and not conflicts
    summary["requiredDiscoveryComplete"] = (
        not required_incomplete and not conflicts
    )
    summary["inventoryStatus"] = (
        "complete" if summary["discoveryComplete"] else "partial"
    )
def apply_export_fallbacks(inventory, source_id, apiops_artifact=None,
                           arm_template_file=None,
                           approve_export_evidence=False):
    result = deepcopy(inventory)
    if (apiops_artifact or arm_template_file) and not approve_export_evidence:
        raise InvalidArgumentValueError(
            "Export evidence requires explicit --approve-export-evidence."
        )
    _annotate_live(result)
    inputs = [{"sourceType": "arm", "authority": "live", "resourceId": source_id}]
    warnings = []
    conflicts = []
    if apiops_artifact:
        records, source, found_warnings = _load_apiops(source_id, result["source"], apiops_artifact)
        inputs.append(source)
        warnings.extend(found_warnings)
        _merge(result, records, conflicts)
    if arm_template_file:
        records, source, found_warnings = _load_template(source_id, result["source"], arm_template_file)
        inputs.append(source)
        warnings.extend(found_warnings)
        _merge(result, records, conflicts)
    result["apis"] = sorted(result.get("apis") or [], key=lambda item: str(
        item.get("stableId") or item.get("id") or "").casefold())
    for scope in result.get("scopes") or []:
        scope["apiIds"] = sorted(set(scope.get("apiIds") or []), key=str.casefold)
        for family in ("backends", "diagnostics", "loggers"):
            scope[family] = sorted(scope.get(family) or [], key=lambda item: str(
                item.get("id") or item.get("name") or "").casefold())
        for family, resources in (scope.get("relatedResources") or {}).items():
            scope["relatedResources"][family] = sorted(resources, key=lambda item: str(
                item.get("id") or item.get("name") or "").casefold())
    result["scopes"] = sorted(result.get("scopes") or [], key=lambda item: (
        item.get("scopeType") != "service", str(item.get("name") or "").casefold()
    ))
    service_scope = next(
        (scope for scope in result["scopes"] if scope.get("scopeType") == "service"),
        None,
    )
    if service_scope:
        named_values = service_scope.get("relatedResources", {}).get("namedValues", [])
        result.setdefault("relatedResources", {})["namedValues"] = named_values
    conflicts.sort(key=lambda item: (str(item.get("stableId") or "").casefold(),
                                     item["field"], item["otherSource"]))
    warnings.sort(key=lambda item: (item["sourceType"], item["path"],
                                    str(item.get("resourceIndex") or "")))
    result["provenance"] = {
        "authorityOrder": ["completeLiveArm", "apiops", "armTemplate", "partialLiveArm"],
        "exportEvidenceApproved": approve_export_evidence,
        "inputs": inputs, "conflicts": conflicts, "warnings": warnings,
    }
    _reconcile_coverage(result, inputs[1:], conflicts, source_id)
    result["sourceBehaviorLedger"] = _ledger(result)
    summary = result.setdefault("summary", {})
    summary["apiCount"] = len(result["apis"])
    summary["workspaceCount"] = sum(
        scope.get("scopeType") == "workspace" for scope in result["scopes"]
    )
    summary["behaviorCount"] = len(result["sourceBehaviorLedger"])
    summary["provenanceConflictCount"] = len(conflicts)
    summary["fallbackSourceCount"] = len(inputs) - 1
    return result
