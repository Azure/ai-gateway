# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from copy import deepcopy
from urllib.parse import quote

from azext_ai_gateway._import_discovery import (
    _backend_summary,
    _discover_source,
    _mcp_dependencies,
    _optional_list,
    _parse_apim_id,
    _sanitize_properties,
)
from azext_ai_gateway._inventory_exports import apply_export_fallbacks


INVENTORY_SCHEMA_VERSION = "3.0"
V2_SKU_CAPABILITIES = {
    "basicv2": {
        "workspaces": True,
        "serviceLevelMcp": True,
        "workspaceMcp": False,
        "inboundPrivateEndpoint": False,
        "outboundVnetIntegration": False,
        "fullVnetInjection": False,
        "availabilityZones": False,
        "multiRegion": False,
    },
    "standardv2": {
        "workspaces": True,
        "serviceLevelMcp": True,
        "workspaceMcp": False,
        "inboundPrivateEndpoint": True,
        "outboundVnetIntegration": True,
        "fullVnetInjection": False,
        "availabilityZones": False,
        "multiRegion": False,
    },
    "premiumv2": {
        "workspaces": True,
        "serviceLevelMcp": True,
        "workspaceMcp": False,
        "inboundPrivateEndpoint": True,
        "outboundVnetIntegration": True,
        "fullVnetInjection": True,
        "availabilityZones": True,
        "multiRegion": False,
    },
}


def _sort_resources(resources):
    return sorted(
        resources or [],
        key=lambda item: str(item.get("id") or item.get("name") or "").casefold(),
    )


def _resource_metadata(resource, fields):
    properties = resource.get("properties") or {}
    return {
        "id": resource.get("id"),
        "name": resource.get("name"),
        "type": resource.get("type"),
        "properties": {
            field: _sanitize_properties(properties.get(field), field)
            for field in fields
            if field in properties
        },
    }


def _named_value_metadata(resource):
    properties = resource.get("properties") or {}
    return {
        "id": resource.get("id"),
        "name": resource.get("name"),
        "type": resource.get("type"),
        "displayName": properties.get("displayName"),
        "secret": bool(properties.get("secret")),
        "tags": properties.get("tags") or [],
        "value": "<redacted>",
    }


def _certificate_metadata(resource):
    return _resource_metadata(
        resource,
        (
            "subject",
            "thumbprint",
            "expirationDate",
        ),
    )


def _policy_fragment_metadata(resource):
    properties = resource.get("properties") or {}
    return {
        **_resource_metadata(resource, ("description", "format")),
        "hasValue": properties.get("value") is not None,
        "value": "<redacted>" if properties.get("value") is not None else None,
    }


def _policy_inventory(policy):
    if not policy:
        return policy
    return {
        key: deepcopy(value)
        for key, value in policy.items()
        if key
        not in {
            "translatedPolicies",
            "translatedPolicyRecords",
            "translationWarnings",
        }
    }


def _scoped_resource_inventory(resource):
    result = deepcopy(resource)
    if "policy" in result:
        result["policy"] = _policy_inventory(result["policy"])
    return result


def _api_inventory(record):
    api = record.get("api") or {}
    properties = api.get("properties") or {}
    return {
        "id": record["source"].get("id"),
        "stableId": record["source"].get("id"),
        "scope": {
            "type": "workspace" if record["source"].get("workspace") else "service",
            "workspace": record["source"].get("workspace"),
        },
        "api": deepcopy(record["source"]),
        "revision": {
            "apiRevision": properties.get("apiRevision"),
            "apiRevisionDescription": properties.get("apiRevisionDescription"),
            "isCurrent": properties.get("isCurrent"),
            "apiVersion": properties.get("apiVersion"),
            "apiVersionSetId": properties.get("apiVersionSetId"),
        },
        "mcpProperties": _sanitize_properties(
            properties.get("mcpProperties") or {}
        ),
        "backends": _sort_resources([
            _backend_summary(backend)
            for backend in record.get("backends") or []
        ]),
        "policies": {
            "api": _policy_inventory(record.get("policy")),
            "inherited": [
                _policy_inventory(policy)
                for policy in record.get("inheritedPolicies") or []
            ],
            "operations": [
                _policy_inventory(policy)
                for policy in record.get("operationPolicies") or []
            ],
            "products": [
                _policy_inventory(policy)
                for policy in record.get("productPolicies") or []
            ],
        },
        "operations": _sort_resources([
            _scoped_resource_inventory(operation)
            for operation in record.get("operations") or []
        ]),
        "schemas": _sort_resources([
            {
                **_resource_metadata(schema, ("contentType",)),
                "hasDocument": bool(
                    (schema.get("properties") or {}).get("document")
                ),
            }
            for schema in record.get("schemas") or []
        ]),
        "releases": _sort_resources([
            _resource_metadata(
                release,
                ("apiId", "notes", "createdDateTime"),
            )
            for release in record.get("releases") or []
        ]),
        "products": _sort_resources([
            _scoped_resource_inventory(product)
            for product in record.get("products") or []
        ]),
        "subscriptions": _sort_resources(record.get("subscriptions")),
        "tools": _sort_resources(record.get("tools")),
        "mcpDependencies": _mcp_dependencies(record),
        "diagnostics": _sort_resources(record.get("diagnostics")),
        "loggerReferences": _sort_resources(record.get("loggers")),
    }


def _scope_inventory(apis):
    scopes = {}
    for api in apis:
        workspace = (api.get("scope") or {}).get("workspace")
        key = workspace or "(service)"
        scope = scopes.setdefault(
            key,
            {
                "type": "workspace" if workspace else "service",
                "name": workspace,
                "apiIds": [],
            },
        )
        scope["apiIds"].append(api["id"])
    for scope in scopes.values():
        scope["apiIds"].sort(key=lambda value: str(value or "").casefold())
    return sorted(
        scopes.values(),
        key=lambda item: (
            item["type"] != "service",
            str(item.get("name") or "").casefold(),
        ),
    )


def _health_incidents(errors):
    incidents = {}
    for error in errors:
        if error.get("category") != "platformHealth":
            continue
        key = error.get("code")
        incident = incidents.setdefault(
            key,
            {
                "category": "platformHealth",
                "code": error.get("code"),
                "message": error.get("message"),
                "retryable": error.get("retryable", False),
                "remediation": error.get("remediation"),
                "affectedDomains": [],
                "requestIds": [],
                "correlationRequestIds": [],
            },
        )
        domain = error.get("configurationDomain")
        if domain:
            incident["affectedDomains"].append(domain)
        if error.get("requestId"):
            incident["requestIds"].append(error["requestId"])
        if error.get("correlationRequestId"):
            incident["correlationRequestIds"].append(
                error["correlationRequestId"]
            )
    for incident in incidents.values():
        for field in (
            "affectedDomains",
            "requestIds",
            "correlationRequestIds",
        ):
            incident[field] = sorted(set(incident[field]))
    return sorted(
        incidents.values(),
        key=lambda item: str(item.get("code") or ""),
    )


def import_inventory(
    cmd,
    source_apim_id,
    apiops_artifact=None,
    arm_template_file=None,
    approve_export_evidence=False,
):
    source_parts = _parse_apim_id(source_apim_id)
    normalized_source_id = (
        f"/subscriptions/{source_parts['subscription']}"
        f"/resourceGroups/{source_parts['resource_group']}"
        "/providers/Microsoft.ApiManagement/service/"
        f"{source_parts['name']}"
    )
    discovered = _discover_source(
        cmd,
        normalized_source_id,
        suppress_mcp_backing_apis=False,
        resolve_subscription_credentials=False,
        require_supported_sku=False,
    )
    errors = discovered["errors"]
    families = {
        "certificates": (
            "certificates",
            _certificate_metadata,
        ),
        "groups": (
            "groups",
            lambda resource: _resource_metadata(
                resource,
                ("displayName", "description", "type", "externalId"),
            ),
        ),
        "identityProviders": (
            "identityProviders",
            lambda resource: _resource_metadata(
                resource,
                ("type", "allowedTenants", "authority"),
            ),
        ),
        "authorizationProviders": (
            "authorizationProviders",
            lambda resource: _resource_metadata(
                resource,
                ("displayName", "identityProvider"),
            ),
        ),
    }
    related_resources = {}
    for output_name, (path, projector) in families.items():
        resources = _optional_list(
            cmd,
            f"{normalized_source_id}/{path}",
            errors,
            f"{normalized_source_id}/{path}",
            output_name,
            required=False,
        )
        related_resources[output_name] = _sort_resources(
            [projector(resource) for resource in resources]
        )

    apis = sorted(
        (_api_inventory(record) for record in discovered["assets"]),
        key=lambda item: str(item.get("id") or "").casefold(),
    )
    discovered_scopes = discovered.get("scopes") or _scope_inventory(apis)
    scope_families = {
        "namedValues": (
            "namedValues",
            _named_value_metadata,
        ),
        "policyFragments": (
            "policyFragments",
            _policy_fragment_metadata,
        ),
        "products": (
            "products",
            lambda resource: _resource_metadata(
                resource,
                (
                    "displayName",
                    "description",
                    "subscriptionRequired",
                    "approvalRequired",
                    "state",
                ),
            ),
        ),
        "subscriptions": (
            "subscriptions",
            lambda resource: _resource_metadata(
                resource,
                ("displayName", "scope", "state"),
            ),
        ),
    }
    scopes = []
    for scope in discovered_scopes:
        scope_type = scope.get("scopeType", scope.get("type"))
        workspace = scope.get("name") if scope_type == "workspace" else None
        scope_id = scope.get("id") or (
            f"{normalized_source_id}/workspaces/"
            f"{quote(str(workspace), safe='')}"
            if workspace
            else normalized_source_id
        )
        scoped_resources = {}
        for output_name, (path, projector) in scope_families.items():
            resources = _optional_list(
                cmd,
                f"{scope_id}/{path}",
                errors,
                f"{scope_id}/{path}",
                output_name,
                required=False,
            )
            scoped_resources[output_name] = _sort_resources(
                [projector(resource) for resource in resources]
            )
        scopes.append(
            {
                "id": scope_id,
                "name": scope.get("name"),
                "scopeType": scope_type,
                "apiIds": sorted(
                    api["id"]
                    for api in apis
                    if (api.get("scope") or {}).get("workspace") == workspace
                ),
                "policy": _policy_inventory(scope.get("policy")),
                "backends": _sort_resources(scope.get("backends")),
                "diagnostics": _sort_resources(scope.get("diagnostics")),
                "loggers": _sort_resources(scope.get("loggers")),
                "relatedResources": scoped_resources,
            }
        )
    scopes.sort(
        key=lambda item: (
            item.get("scopeType", item.get("type")) != "service",
            str(item.get("name") or "").casefold(),
        )
    )
    service_scope = next(
        (scope for scope in scopes if scope["scopeType"] == "service"),
        None,
    )
    related_resources["namedValues"] = (
        ((service_scope or {}).get("relatedResources") or {}).get(
            "namedValues",
            [],
        )
    )
    coverage = sorted(
        discovered.get("collectionCoverage") or [],
        key=lambda item: (
            str(item.get("scope") or "").casefold(),
            str(item.get("configurationDomain") or "").casefold(),
        ),
    )
    coverage_complete = (
        all(
            item.get("status") in {"complete", "empty", "notApplicable"}
            for item in coverage
        )
        if coverage
        else not errors
    )
    source = deepcopy(discovered["source"])
    normalized_sku = str(source.get("sku") or "").casefold()
    source["migrationCompatibility"] = {
        "skuFamily": "v2" if normalized_sku in V2_SKU_CAPABILITIES else "other",
        "supportedV2Sku": normalized_sku in V2_SKU_CAPABILITIES,
        "inventoryApiVersion": "2024-05-01",
        "mcpApiVersion": "2025-09-01-preview",
        "capabilities": V2_SKU_CAPABILITIES.get(normalized_sku, {}),
    }
    inventory = {
        "schemaVersion": INVENTORY_SCHEMA_VERSION,
        "kind": "AiGatewayApimImportInventory",
        "source": source,
        "summary": {
            "apiCount": len(apis),
            "workspaceCount": sum(
                scope.get("scopeType", scope.get("type")) == "workspace"
                for scope in scopes
            ),
            "discoveryComplete": coverage_complete,
            "requiredDiscoveryComplete": not any(
                error.get("required", True) for error in errors
            ),
            "discoveryErrorCount": len(errors),
            "inventoryStatus": "complete" if coverage_complete else "partial",
        },
        "scopes": scopes,
        "apis": apis,
        "relatedResources": related_resources,
        "collectionCoverage": coverage,
        "healthIncidents": _health_incidents(errors),
        "discoveryErrors": sorted(
            errors,
            key=lambda item: (
                str(item.get("scope") or "").casefold(),
                str(item.get("configurationDomain") or "").casefold(),
            ),
        ),
        "excludedResourceFamilies": [
            {
                "name": "users",
                "reason": (
                    "User identities are not destination AI Gateway configuration."
                ),
            },
            {
                "name": "notifications",
                "reason": (
                    "Administrative notification templates are not migration "
                    "inputs for AI Gateway."
                ),
            },
        ],
    }

    return apply_export_fallbacks(
        inventory,
        normalized_source_id,
        apiops_artifact=apiops_artifact,
        arm_template_file=arm_template_file,
        approve_export_evidence=approve_export_evidence,
    )


def format_import_inventory_table(result):
    summary = result.get("summary") or {}
    return [
        {
            "Source": (result.get("source") or {}).get("name"),
            "SKU": (result.get("source") or {}).get("sku"),
            "Schema": result.get("schemaVersion"),
            "Status": summary.get("inventoryStatus"),
            "APIs": summary.get("apiCount"),
            "Workspaces": summary.get("workspaceCount"),
            "Complete": summary.get("discoveryComplete"),
            "Errors": summary.get("discoveryErrorCount"),
        }
    ]
