# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from copy import deepcopy
from urllib.parse import urlparse

from azure.cli.core.azclierror import AzCLIError
from requests import RequestException

from azext_ai_gateway._gateway import update_gateway
from azext_ai_gateway._mcp import create_mcp, update_mcp
from azext_ai_gateway._model import create_model
from azext_ai_gateway._model_provider import (
    _foundry_account_key,
    create_model_provider,
)


_SECRET_FIELD_MARKERS = (
    "apikey",
    "clientsecret",
    "credential",
    "password",
    "secret",
    "subscriptionkey",
    "token",
)


def _redact(value, field_name=""):
    if isinstance(value, dict):
        return {key: _redact(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, field_name) for item in value]
    normalized = str(field_name).replace("-", "").replace("_", "").casefold()
    if any(marker in normalized for marker in _SECRET_FIELD_MARKERS):
        return "<redacted>" if value is not None else None
    if isinstance(value, str) and value.casefold().startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            hostname = parsed.hostname or ""
            if parsed.port:
                hostname = f"{hostname}:{parsed.port}"
            return parsed._replace(
                netloc=hostname,
                query="<redacted>" if parsed.query else "",
                fragment="<redacted>" if parsed.fragment else "",
            ).geturl()
    return value


def _action(
    action_type,
    name,
    target,
    order,
    depends_on,
    desired,
    current,
    status,
    operation,
    reasons=None,
    warnings=None,
    secret_refs=None,
):
    return {
        "type": action_type,
        "name": name,
        "target": target,
        "order": order,
        "dependsOn": sorted(set(depends_on)),
        "desired": _redact(desired),
        "current": _redact(current),
        "assessment": {
            "status": status,
            "reasons": list(reasons or []),
            "warnings": list(warnings or []),
        },
        "operation": operation,
        "secretRefs": sorted(set(secret_refs or [])),
    }


def _network_action(network):
    destination = network.get("destination") or {}
    assessment = network.get("assessment") or {}
    changes = bool(assessment.get("changesRequired"))
    return _action(
        "network",
        "network-configuration",
        f"gateway:{destination.get('name') or ''}",
        10,
        [],
        destination.get("target") or {},
        destination.get("current") or {},
        assessment.get("status") or "blocked",
        "update" if changes else "none",
        assessment.get("reasons"),
        assessment.get("warnings"),
    )


def _subscription_is_mapped(asset):
    if asset.get("assetSubtype") != "mcpApi":
        return False
    credentials = (
        ((asset.get("configuration") or {}).get("endpoint") or {}).get(
            "credentials"
        )
        or {}
    )
    return credentials.get("type") == "header" and bool(credentials.get("headers"))


def _configuration_actions(asset, asset_target, network_target):
    actions = []
    associated = asset.get("associatedConfiguration") or {}
    domain_types = {
        "managedIdentities": "identityPrerequisite",
        "managedIdentityAuthentication": "identityPrerequisite",
        "requiredRbac": "identityPrerequisite",
        "products": "relationshipNotice",
        "subscriptions": "relationshipNotice",
        "diagnostics": "diagnosticNotice",
        "loggerReferences": "diagnosticNotice",
    }
    for domain in sorted(associated):
        details = associated.get(domain)
        if not isinstance(details, dict):
            continue
        support_state = details.get("supportState")
        if support_state in {None, "importable", "reduced"}:
            continue
        allow_mapped_subscription = (
            domain == "subscriptions" and _subscription_is_mapped(asset)
        )
        allow_mapped_provider_credential = (
            domain == "backendCredentials"
            and asset.get("assetType") == "model"
            and bool(
                (asset.get("configuration") or {}).get(
                    "providerCredentialMapped"
                )
            )
        )
        critical = support_state == "unsupported-critical"
        status = (
            "blocked"
            if (
                critical
                and not allow_mapped_subscription
                and not allow_mapped_provider_credential
            )
            else ("deferred" if support_state == "deferred" else "warn")
        )
        reason = details.get("reason")
        actions.append(
            _action(
                domain_types.get(domain, "configurationNotice"),
                domain,
                f"{asset_target}/configuration/{domain}",
                20 if domain_types.get(domain) == "identityPrerequisite" else 60,
                [network_target],
                {"supportState": support_state, "items": details.get("items") or []},
                None,
                status,
                "inventory",
                [reason] if status == "blocked" and reason else [],
                [reason] if status != "blocked" and reason else [],
            )
        )
    return actions


def _provider_action(asset, network_target):
    destination = asset.get("destination") or {}
    configuration = asset.get("configuration") or {}
    provider_name = destination.get("providerName")
    if not provider_name:
        reasons = (asset.get("assessment") or {}).get("reasons") or []
        return _action(
            "provider",
            "unresolved-provider",
            "provider:unresolved",
            30,
            [network_target],
            None,
            None,
            "blocked",
            "none",
            reasons,
        )
    target = f"provider:{provider_name}"
    proposal = configuration.get("providerCreate")
    if proposal:
        secret_refs = proposal.get("secretRefs") or []
        return _action(
            "provider",
            provider_name,
            target,
            30,
            [network_target],
            proposal,
            None,
            "ready",
            "create",
            secret_refs=secret_refs,
        )
    if not configuration.get("providerExists", True):
        return _action(
            "provider",
            provider_name,
            target,
            30,
            [network_target],
            {"name": provider_name},
            {"exists": False},
            "blocked",
            "none",
            (asset.get("assessment") or {}).get("reasons"),
        )
    return _action(
        "provider",
        provider_name,
        target,
        30,
        [network_target],
        {"name": provider_name},
        {"exists": True},
        "ready",
        "use",
    )


def _model_actions(asset, network_target, provider_target):
    destination = asset.get("destination") or {}
    configuration = asset.get("configuration") or {}
    provider_name = destination.get("providerName")
    models = configuration.get("providerModels")
    if models is None:
        deployment = configuration.get("deployment")
        models = (
            [
                {
                    "name": destination.get("name"),
                    "displayName": (asset.get("source") or {}).get("displayName"),
                    "description": (asset.get("source") or {}).get("description"),
                    "apiFormat": configuration.get("apiFormat"),
                    "deployment": deployment,
                    "supportedEndpoints": configuration.get("supportedEndpoints") or [],
                }
            ]
            if deployment
            else []
        )
    actions = []
    for model in sorted(
        models,
        key=lambda item: str(
            item.get("name") or item.get("modelName") or ""
        ),
    ):
        model_name = model.get("name") or model.get("modelName")
        target = f"model:{provider_name}/{model_name}"
        conflict = (configuration.get("modelConflicts") or {}).get(
            model_name,
            (asset.get("assessment") or {}).get("conflict"),
        )
        status = "skipped" if conflict == "skip" else "ready"
        operation = "skip" if status == "skipped" else (
            "overwrite" if conflict == "overwrite" else "create"
        )
        desired = {
            "displayName": model.get("displayName"),
            "description": model.get("description"),
            "apiFormat": model.get("apiFormat") or configuration.get("apiFormat"),
            "deployment": model.get("deployment"),
            "supportedEndpoints": model.get("supportedEndpoints") or [],
        }
        actions.append(
            _action(
                "model",
                model_name,
                target,
                40,
                [provider_target or network_target],
                desired,
                {"exists": bool(conflict)},
                status,
                operation,
            )
        )
        policies = configuration.get("destinationPolicies") or []
        if policies:
            actions.append(
                _action(
                    "policy",
                    f"{model_name}-policies",
                    f"{target}/policies",
                    70,
                    [target],
                    policies,
                    None,
                    status,
                    "apply" if status == "ready" else "skip",
                )
            )
    return actions


def _mcp_actions(asset, network_target):
    destination = asset.get("destination") or {}
    configuration = asset.get("configuration") or {}
    name = destination.get("name")
    target = f"mcpServer:{name}"
    conflict = (asset.get("assessment") or {}).get("conflict")
    status = "skipped" if conflict == "skip" else "ready"
    operation = "skip" if status == "skipped" else (
        "overwrite" if conflict == "overwrite" else "create"
    )
    endpoint = configuration.get("endpoint") or {}
    credential = endpoint.get("credentials") or {}
    secret_refs = []
    if credential:
        subscription = (asset.get("source") or {}).get("id") or name
        secret_refs.append(f"source-apim-subscription:{subscription}")
    action = _action(
        "mcpServer",
        name,
        target,
        50,
        [network_target],
        {
            "displayName": (asset.get("source") or {}).get("displayName"),
            "description": (asset.get("source") or {}).get("description"),
            "endpoints": [endpoint],
        },
        {"exists": bool(conflict)},
        status,
        operation,
        secret_refs=secret_refs,
    )
    actions = [action]
    policies = configuration.get("destinationPolicies") or []
    if policies:
        actions.append(
            _action(
                "policy",
                f"{name}-policies",
                f"{target}/policies",
                70,
                [target],
                policies,
                None,
                status,
                "apply" if status == "ready" else "skip",
            )
        )
    return actions


def build_import_actions(
    network,
    assets,
    deferred_apis=None,
    discovery_errors=None,
):
    actions = [_network_action(network)]
    network_target = actions[0]["target"]
    for error in sorted(
        discovery_errors or [],
        key=lambda item: str(item.get("scope") or ""),
    ):
        required = error.get("required", True)
        actions.append(
            _action(
                "discoveryNotice",
                "incomplete-discovery",
                f"discovery:{error.get('scope') or ''}",
                15,
                [],
                None,
                None,
                "blocked" if required else "warn",
                "inventory",
                [error.get("message")] if required else [],
                [error.get("message")] if not required else [],
            )
        )
    provider_actions = {}
    for asset in sorted(
        assets,
        key=lambda item: (
            str(item.get("assetType") or ""),
            str((item.get("destination") or {}).get("providerName") or ""),
            str((item.get("destination") or {}).get("name") or ""),
        ),
    ):
        destination = asset.get("destination") or {}
        asset_target = (
            f"model:{destination.get('providerName')}/{destination.get('name')}"
            if asset.get("assetType") == "model"
            else f"mcpServer:{destination.get('name')}"
        )
        actions.extend(_configuration_actions(asset, asset_target, network_target))
        assessment = asset.get("assessment") or {}
        provider_target = None
        if asset.get("assetType") == "model":
            provider = _provider_action(asset, network_target)
            provider_target = provider["target"]
            existing_provider = provider_actions.get(provider_target)
            if existing_provider is None:
                provider_actions[provider_target] = provider
                actions.append(provider)
            elif existing_provider["desired"] != provider["desired"]:
                existing_provider["assessment"]["status"] = "blocked"
                existing_provider["assessment"]["reasons"].append(
                    "Multiple source assets propose incompatible "
                    f"configuration for destination provider '{provider['name']}'."
                )
        if assessment.get("status") == "blocked":
            actions.append(
                _action(
                    asset.get("assetType") or "asset",
                    destination.get("name") or "",
                    asset_target,
                    40 if asset.get("assetType") == "model" else 50,
                    [provider_target or network_target],
                    asset.get("configuration") or {},
                    None,
                    "blocked",
                    "none",
                    assessment.get("reasons"),
                    assessment.get("warnings"),
                )
            )
            continue
        if asset.get("assetType") == "model":
            actions.extend(_model_actions(asset, network_target, provider_target))
        else:
            actions.extend(_mcp_actions(asset, network_target))
    for deferred in sorted(
        deferred_apis or [],
        key=lambda item: str(item.get("id") or item.get("name") or ""),
    ):
        actions.append(
            _action(
                "deferredAsset",
                deferred.get("name") or "",
                f"deferred:{deferred.get('id') or deferred.get('name') or ''}",
                60,
                [network_target],
                deferred,
                None,
                "blocked" if deferred.get("assetSubtype") == "unified" else "deferred",
                "inventory",
                (
                    [deferred.get("reason")]
                    if deferred.get("assetSubtype") == "unified"
                    else []
                ),
                (
                    [deferred.get("reason")]
                    if deferred.get("assetSubtype") != "unified"
                    else []
                ),
            )
        )
    write_targets = {}
    for action in actions:
        if action["type"] not in {"model", "mcpServer"}:
            continue
        write_targets.setdefault(action["target"], []).append(action)
    for target, target_actions in write_targets.items():
        if len(target_actions) < 2:
            continue
        for action in target_actions:
            action["assessment"]["status"] = "blocked"
            action["assessment"]["reasons"].append(
                "Multiple source assets map to the same destination target "
                f"'{target}'. Provide unique destination mappings."
            )
            action["operation"] = "none"
    return sorted(
        actions,
        key=lambda item: (item["order"], item["type"], item["target"]),
    )


def sanitize_assets_for_output(assets):
    sanitized = deepcopy(assets)
    for asset in sanitized:
        asset.pop("_executionSecrets", None)
        configuration = asset.get("configuration") or {}
        endpoint = configuration.get("endpoint") or {}
        credentials = endpoint.get("credentials")
        if credentials:
            endpoint["credentials"] = _redact_credential_values(credentials)
        provider_create = configuration.get("providerCreate")
        if isinstance(provider_create, dict):
            provider_create.pop("_apiKeyValue", None)
    return _redact(sanitized)


def _redact_credential_values(value, field_name=""):
    if isinstance(value, dict):
        return {
            key: _redact_credential_values(item, key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_credential_values(item, field_name)
            for item in value
        ]
    if str(field_name).casefold() in {
        "headername",
        "kind",
        "name",
        "type",
    }:
        return value
    return "<redacted>" if value is not None else None


def _asset_index(assets):
    index = {}
    for asset in assets:
        destination = asset.get("destination") or {}
        if asset.get("assetType") == "model":
            provider = destination.get("providerName")
            configuration = asset.get("configuration") or {}
            models = configuration.get("providerModels")
            if models is None:
                models = [{"name": destination.get("name")}]
            for model in models:
                name = model.get("name") or model.get("modelName")
                index[f"model:{provider}/{name}"] = (asset, model)
        else:
            index[f"mcpServer:{destination.get('name')}"] = (asset, None)
    return index


def _provider_asset_index(assets):
    index = {}
    for asset in sorted(
        assets,
        key=lambda item: str((item.get("source") or {}).get("id") or ""),
    ):
        provider_name = (asset.get("destination") or {}).get("providerName")
        if provider_name and (asset.get("configuration") or {}).get(
            "providerCreate"
        ):
            index.setdefault(f"provider:{provider_name}", asset)
    return index


def _execute_action(
    cmd,
    gateway_name,
    resource_group_name,
    action,
    asset_index,
    provider_asset_index,
):
    desired = action["desired"] or {}
    if action["type"] == "network":
        return update_gateway(
            cmd,
            gateway_name,
            resource_group_name,
            public_network_access=desired.get("publicNetworkAccess"),
            virtual_network_type=desired.get("virtualNetworkType"),
            subnet_resource_id=desired.get("subnetResourceId"),
        )
    if action["type"] == "provider":
        asset = provider_asset_index[action["target"]]
        proposal = (asset.get("configuration") or {}).get("providerCreate") or {}
        api_key_value = proposal.get("_apiKeyValue")
        resource_ids = proposal.get("resourceIds") or []
        if proposal.get("kind") == "Foundry" and not api_key_value:
            api_key_value = _foundry_account_key(cmd, resource_ids[0])
        return create_model_provider(
            cmd,
            name=action["name"],
            gateway_name=gateway_name,
            resource_group_name=resource_group_name,
            kind=proposal.get("kind"),
            endpoint=proposal.get("endpoint"),
            resource_ids=resource_ids or None,
            auth_kind=proposal.get("authKind"),
            api_key_header_name=proposal.get("apiKeyHeaderName"),
            api_key_value=api_key_value,
            no_sync=True,
        )
    if action["type"] == "model":
        asset, model = asset_index[action["target"]]
        configuration = asset.get("configuration") or {}
        deployment = (
            (model or {}).get("deployment")
            or configuration.get("deployment")
            or {}
        )
        deployment_model_name = (
            deployment.get("modelName") if deployment else None
        )
        return create_model(
            cmd,
            action["name"],
            gateway_name,
            resource_group_name,
            (asset.get("destination") or {}).get("providerName"),
            display_name=(model or {}).get("displayName")
            or (asset.get("source") or {}).get("displayName"),
            description=(model or {}).get("description")
            or (asset.get("source") or {}).get("description"),
            api_format=(model or {}).get("apiFormat") or configuration.get("apiFormat"),
            deployment_resource_id=deployment.get("resourceId"),
            deployment_model_name=deployment_model_name,
            deployment_model_version=deployment.get("modelVersion"),
            supported_endpoints=(model or {}).get("supportedEndpoints")
            or configuration.get("supportedEndpoints")
            or [],
        )
    if action["type"] == "mcpServer":
        asset, _ = asset_index[action["target"]]
        configuration = asset.get("configuration") or {}
        endpoint = deepcopy(configuration.get("endpoint") or {})
        subscription_key = (
            asset.get("_executionSecrets") or {}
        ).get("subscriptionKey")
        if subscription_key:
            headers = (endpoint.get("credentials") or {}).get("headers") or {}
            for header_name, values in headers.items():
                headers[header_name] = [
                    subscription_key if value == "<redacted>" else value
                    for value in values
                ]
        kwargs = {
            "cmd": cmd,
            "name": action["name"],
            "gateway_name": gateway_name,
            "resource_group_name": resource_group_name,
            "endpoints": [endpoint],
            "display_name": (asset.get("source") or {}).get("displayName"),
            "description": (asset.get("source") or {}).get("description"),
        }
        if action["operation"] == "overwrite":
            return update_mcp(**kwargs, replace=True)
        return create_mcp(**kwargs)
    if action["type"] == "policy":
        parent_target = action["dependsOn"][0]
        asset, model = asset_index[parent_target]
        configuration = asset.get("configuration") or {}
        policies = configuration.get("destinationPolicies") or []
        if parent_target.startswith("mcpServer:"):
            return update_mcp(
                cmd,
                action["name"].removesuffix("-policies"),
                gateway_name,
                resource_group_name,
                policies=policies,
            )
        deployment = (
            (model or {}).get("deployment")
            or configuration.get("deployment")
            or {}
        )
        return create_model(
            cmd,
            (model or {}).get("name")
            or (model or {}).get("modelName")
            or (asset.get("destination") or {}).get("name"),
            gateway_name,
            resource_group_name,
            (asset.get("destination") or {}).get("providerName"),
            display_name=(model or {}).get("displayName")
            or (asset.get("source") or {}).get("displayName"),
            description=(model or {}).get("description")
            or (asset.get("source") or {}).get("description"),
            api_format=(model or {}).get("apiFormat") or configuration.get("apiFormat"),
            deployment_resource_id=deployment.get("resourceId"),
            deployment_model_name=deployment.get("modelName"),
            deployment_model_version=deployment.get("modelVersion"),
            supported_endpoints=(model or {}).get("supportedEndpoints")
            or configuration.get("supportedEndpoints")
            or [],
            policies=policies,
        )
    return None


def _safe_error_message(error, assets):
    message = str(error)
    secrets = []
    for asset in assets:
        secrets.extend(
            str(value)
            for value in (asset.get("_executionSecrets") or {}).values()
            if value
        )
        configuration = asset.get("configuration") or {}
        provider_create = configuration.get("providerCreate") or {}
        if provider_create.get("_apiKeyValue"):
            secrets.append(str(provider_create["_apiKeyValue"]))
        credentials = (
            (configuration.get("endpoint") or {}).get("credentials") or {}
        )
        headers = credentials.get("headers") or {}
        for values in headers.values():
            if not isinstance(values, list):
                values = [values]
            secrets.extend(str(value) for value in values if value)
    for secret in sorted(set(secrets), key=len, reverse=True):
        message = message.replace(secret, "<redacted>")
    return message


def execute_import_actions(cmd, gateway_name, resource_group_name, actions, assets):
    graph_blocked = any(
        action["assessment"]["status"] == "blocked" for action in actions
    )
    results = []
    statuses = {}
    asset_index = _asset_index(assets)
    provider_asset_index = _provider_asset_index(assets)
    for action in actions:
        assessment_status = action["assessment"]["status"]
        if assessment_status == "blocked":
            status = "blocked"
        elif assessment_status in {"deferred", "warn"} or action["operation"] in {
            "inventory",
            "none",
            "use",
        }:
            status = "deferred" if assessment_status == "deferred" else "skipped"
        elif assessment_status == "skipped" or action["operation"] == "skip":
            status = "skipped"
        elif graph_blocked:
            status = "deferred"
        elif any(
            statuses.get(dependency) in {"failed", "blocked", "deferred"}
            for dependency in action["dependsOn"]
        ):
            status = "deferred"
        else:
            try:
                _execute_action(
                    cmd,
                    gateway_name,
                    resource_group_name,
                    action,
                    asset_index,
                    provider_asset_index,
                )
                status = "succeeded"
            except (AzCLIError, OSError, RequestException) as error:
                status = "failed"
                results.append(
                    {
                        **action,
                        "status": status,
                        "error": {
                            "type": type(error).__name__,
                            "message": _safe_error_message(error, assets),
                        },
                    }
                )
                statuses[action["target"]] = status
                continue
        results.append({**action, "status": status})
        statuses[action["target"]] = status
    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("succeeded", "failed", "skipped", "blocked", "deferred")
    }
    return {
        "actions": results,
        "summary": counts,
        "completed": counts["failed"] == 0 and counts["blocked"] == 0,
    }
