# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import re
import time
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urlparse,
    urlunparse,
)
from xml.etree import ElementTree

from azure.cli.core.azclierror import (
    HTTPError,
    InvalidArgumentValueError,
)
from knack.log import get_logger
from requests import RequestException

from azext_ai_gateway._gateway import (
    _request,
    _response_json,
)
from azext_ai_gateway._policy_translation import summarize_policy

APIM_INVENTORY_API_VERSION = "2024-05-01"
APIM_MCP_API_VERSION = "2025-09-01-preview"
APIM_ID_PATTERN = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/"
    r"resourceGroups/(?P<resource_group>[^/]+)/providers/"
    r"Microsoft\.ApiManagement/service/(?P<name>[^/]+)/?$",
    re.IGNORECASE,
)
SUPPORTED_SOURCE_SKUS = {"basicv2", "standardv2", "premiumv2"}
logger = get_logger(__name__)
MODEL_HOST_SUFFIXES = (
    ".openai.azure.com",
    ".models.ai.azure.com",
    ".models.inference.ai.azure.com",
    "api.anthropic.com",
    "api.openai.com",
    "generativelanguage.googleapis.com",
)
SENSITIVE_PROPERTY_NAMES = {
    "accesskey",
    "apikey",
    "certificate",
    "clientcertificate",
    "clientsecret",
    "connectionstring",
    "instrumentationkey",
    "key",
    "password",
    "secret",
    "subscriptionkey",
    "token",
}
def _parse_apim_id(resource_id):
    match = APIM_ID_PATTERN.fullmatch((resource_id or "").strip())
    if not match:
        raise InvalidArgumentValueError(
            "--source-apim-id must be a complete Azure API Management service "
            "resource ID."
        )
    return match.groupdict()


class _PartialListError(Exception):
    def __init__(self, error, resources, pages_completed):
        super().__init__(str(error))
        self.error = error
        self.resources = resources
        self.pages_completed = pages_completed


class _ListResult(list):
    def __init__(self, resources, pages_completed):
        super().__init__(resources)
        self.pages_completed = pages_completed


class _DiscoveryErrors(list):
    def __init__(self):
        super().__init__()
        self.coverage = []


def _retry_delay(error, attempt):
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after_ms = headers.get("x-ms-retry-after-ms")
    if retry_after_ms:
        try:
            return min(float(retry_after_ms) / 1000, 30)
        except (TypeError, ValueError):
            pass
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), 30)
        except (TypeError, ValueError):
            pass
    return 2 ** attempt


def _source_request(
    cmd,
    method,
    url,
    *,
    api_version,
    include_api_version=True,
):
    attempts = 3
    for attempt in range(attempts):
        try:
            request_kwargs = {"api_version": api_version}
            if not include_api_version:
                request_kwargs["include_api_version"] = False
            return _request(cmd, method, url, **request_kwargs)
        except (HTTPError, RequestException) as error:
            response = getattr(error, "response", None)
            status = getattr(response, "status_code", None)
            transport_error = (
                isinstance(error, RequestException)
                and not isinstance(error, HTTPError)
            )
            if (
                not transport_error
                and status not in {408, 429, 500, 502, 503, 504}
            ) or attempt == attempts - 1:
                error._inventory_attempt_count = attempt + 1
                raise
            time.sleep(_retry_delay(error, attempt))
    raise AssertionError("Unreachable inventory retry state.")


def _list_all(cmd, url, *, api_version=None):
    resources = []
    include_api_version = True
    pages_completed = 0
    seen_links = set()
    while url:
        if url in seen_links:
            error = RequestException(
                "APIM pagination returned a repeated continuation link."
            )
            if resources:
                raise _PartialListError(
                    error,
                    resources,
                    pages_completed,
                )
            raise error
        seen_links.add(url)
        request_kwargs = {"include_api_version": include_api_version}
        if api_version is not None:
            request_kwargs["api_version"] = api_version
        try:
            if api_version is None:
                response = _request(cmd, "GET", url, **request_kwargs)
            else:
                response = _source_request(
                    cmd,
                    "GET",
                    url,
                    api_version=api_version,
                    include_api_version=include_api_version,
                )
            page = _response_json(response)
        except (HTTPError, RequestException) as error:
            if resources:
                raise _PartialListError(
                    error,
                    resources,
                    pages_completed,
                ) from error
            raise
        values = (page or {}).get("value", [])
        if not isinstance(values, list):
            error = RequestException(
                "APIM list response field 'value' must be an array."
            )
            if resources:
                raise _PartialListError(
                    error,
                    resources,
                    pages_completed,
                )
            raise error
        resources.extend(values)
        pages_completed += 1
        url = (page or {}).get("nextLink")
        include_api_version = False
    return _ListResult(resources, pages_completed)


def _http_error(error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    code = None
    try:
        payload = response.json() if response is not None else {}
        service_error = (payload or {}).get("error") or {}
        code = service_error.get("code")
    except (TypeError, ValueError):
        pass
    message = str(error)
    scale_unit_mismatch = (
        code == "InvalidOperation"
        and "scale unit" in message.casefold()
        and "requires family" in message.casefold()
    )
    headers = getattr(response, "headers", {}) or {}
    return {
        "statusCode": status,
        "code": code,
        "message": message,
        "category": (
            "platformHealth"
            if scale_unit_mismatch
            else (
                "authorization"
                if status in {401, 403}
                else (
                    "transient"
                    if status in {408, 429, 500, 502, 503, 504}
                    or isinstance(error, RequestException)
                    else "request"
                )
            )
        ),
        "retryable": (
            status in {408, 429, 500, 502, 503, 504}
            or isinstance(error, RequestException)
        ),
        "attemptCount": getattr(error, "_inventory_attempt_count", 1),
        "requestId": headers.get("x-ms-request-id"),
        "correlationRequestId": headers.get("x-ms-correlation-request-id"),
        "remediation": (
            "Check APIM Resource Health and Service Health, then open a "
            "Microsoft support request if the resource remains inconsistent."
            if scale_unit_mismatch
            else None
        ),
    }


def _optional_list(
    cmd,
    url,
    errors,
    context,
    domain=None,
    required=True,
    api_version=APIM_INVENTORY_API_VERSION,
    not_applicable_on_404=False,
):
    try:
        resources = _list_all(
            cmd,
            url,
            api_version=api_version,
        )
        if hasattr(errors, "coverage"):
            errors.coverage.append(
                {
                    "scope": context,
                    "configurationDomain": domain,
                    "status": "complete" if resources else "empty",
                    "apiVersion": api_version,
                    "observedCount": len(resources),
                    "pagesCompleted": resources.pages_completed,
                    "requiredForEnumeration": required,
                }
            )
        return resources
    except _PartialListError as partial:
        details = _http_error(partial.error)
        resources = partial.resources
        coverage_status = "partial"
        pages_completed = partial.pages_completed
    except (HTTPError, RequestException) as error:
        details = _http_error(error)
        if details["statusCode"] == 404 and not_applicable_on_404:
            if hasattr(errors, "coverage"):
                errors.coverage.append(
                    {
                        "scope": context,
                        "configurationDomain": domain,
                        "status": "notApplicable",
                        "apiVersion": api_version,
                        "observedCount": 0,
                        "pagesCompleted": 0,
                        "requiredForEnumeration": required,
                    }
                )
            return []
        resources = []
        coverage_status = "failed"
        pages_completed = 0
        errors.append(
            {
                "scope": context,
                "configurationDomain": domain,
                "required": required,
                **details,
            }
        )
    if coverage_status == "partial":
        errors.append(
            {
                "scope": context,
                "configurationDomain": domain,
                "required": required,
                **details,
            }
        )
    if hasattr(errors, "coverage"):
        errors.coverage.append(
            {
                "scope": context,
                "configurationDomain": domain,
                "status": coverage_status,
                "apiVersion": api_version,
                "observedCount": len(resources),
                "pagesCompleted": pages_completed,
                "requiredForEnumeration": required,
                "error": details,
            }
        )
    return resources


def _optional_policy(cmd, scope_id, errors):
    coverage = {
        "scope": f"{scope_id}/policies/policy",
        "configurationDomain": "policies",
        "apiVersion": APIM_INVENTORY_API_VERSION,
        "requiredForEnumeration": True,
    }
    try:
        response = _source_request(
            cmd,
            "GET",
            f"{scope_id}/policies/policy?format=rawxml",
            api_version=APIM_INVENTORY_API_VERSION,
        )
    except (HTTPError, RequestException) as error:
        details = _http_error(error)
        if details["statusCode"] == 404:
            if hasattr(errors, "coverage"):
                errors.coverage.append(
                    {
                        **coverage,
                        "status": "empty",
                        "observedCount": 0,
                        "pagesCompleted": 1,
                    }
                )
            return None
        errors.append(
            {
                "scope": f"{scope_id}/policies/policy",
                "configurationDomain": "policies",
                "required": True,
                **details,
            }
        )
        if hasattr(errors, "coverage"):
            errors.coverage.append(
                {
                    **coverage,
                    "status": "failed",
                    "observedCount": 0,
                    "pagesCompleted": 0,
                    "error": details,
                }
            )
        return None
    text = getattr(response, "text", None)
    if isinstance(text, str):
        text = text.removeprefix("\ufeff")
        if text.lstrip().startswith("<"):
            if hasattr(errors, "coverage"):
                errors.coverage.append(
                    {
                        **coverage,
                        "status": "complete",
                        "observedCount": 1,
                        "pagesCompleted": 1,
                    }
                )
            return text
    body = _response_json(response)
    if isinstance(body, dict):
        value = (body.get("properties") or {}).get("value") or body.get("value")
        if isinstance(value, str):
            if hasattr(errors, "coverage"):
                errors.coverage.append(
                    {
                        **coverage,
                        "status": "complete",
                        "observedCount": 1,
                        "pagesCompleted": 1,
                    }
                )
            return value
    if hasattr(errors, "coverage"):
        errors.coverage.append(
            {
                **coverage,
                "status": "empty",
                "observedCount": 0,
                "pagesCompleted": 1,
            }
        )
    return text if isinstance(text, str) else None


def _managed_identity_authentications(policy_xml):
    if not policy_xml:
        return []
    try:
        root = ElementTree.fromstring(policy_xml)
    except ElementTree.ParseError:
        return []
    settings = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != (
            "authentication-managed-identity"
        ):
            continue
        settings.append(
            {
                "resource": _safe_url(element.attrib.get("resource")),
                "clientId": element.attrib.get("client-id"),
                "outputTokenVariableName": element.attrib.get(
                    "output-token-variable-name"
                ),
                "ignoreError": element.attrib.get("ignore-error"),
            }
        )
    return settings


def _policy_summary(policy_xml, scope, scope_type="api"):
    summary = summarize_policy(policy_xml, scope, scope_type)
    summary["managedIdentityAuthentications"] = (
        _managed_identity_authentications(policy_xml)
    )
    return summary


def _credential_summary(credentials):
    credentials = credentials or {}
    authorization = credentials.get("authorization") or {}
    return {
        "hasCredentials": bool(credentials),
        "headerNames": sorted((credentials.get("header") or {}).keys()),
        "queryParameterNames": sorted((credentials.get("query") or {}).keys()),
        "authorizationScheme": authorization.get("scheme"),
        "namedValueReferences": _named_value_references(credentials),
    }


def _named_value_references(value):
    references = set()

    def collect(item):
        if isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)
        elif isinstance(item, str):
            references.update(
                match.strip()
                for match in re.findall(r"\{\{([^{}]+)\}\}", item)
                if match.strip()
            )

    collect(value)
    return sorted(references)


def _safe_url(value):
    if not value:
        return value
    if not isinstance(value, str):
        return "<invalid>"
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname or ""
        if parsed.port:
            hostname = f"{hostname}:{parsed.port}"
    except (TypeError, ValueError):
        return "<invalid>"
    redacted_query = urlencode(
        [(name, "<redacted>") for name, _ in parse_qsl(parsed.query)]
    )
    return urlunparse(
        (
            parsed.scheme,
            hostname,
            parsed.path,
            parsed.params,
            redacted_query,
            "<redacted>" if parsed.fragment else "",
        )
    )


def _url_safety(value):
    if not value:
        return False, False
    parsed = urlparse(value)
    return bool(parsed.username or parsed.password), bool(parsed.query)


def _sanitize_properties(value, property_name=None):
    normalized_name = re.sub(
        r"[^a-z0-9]",
        "",
        str(property_name or "").casefold(),
    )
    if normalized_name == "credentials" and isinstance(value, dict):
        return _credential_summary(value)
    sensitive_names = {
        re.sub(r"[^a-z0-9]", "", name.casefold())
        for name in SENSITIVE_PROPERTY_NAMES
    }
    if (
        normalized_name in sensitive_names
        or normalized_name in {"authorization", "authorizationheader"}
        or normalized_name.endswith("token")
        or any(
            marker in normalized_name
            for marker in (
                "cookie",
                "credential",
                "password",
                "secret",
                "tokenvalue",
            )
        )
    ):
        return "<redacted>" if value is not None else None
    if isinstance(value, dict):
        return {
            key: _sanitize_properties(item, key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_properties(item, property_name) for item in value]
    if isinstance(value, str) and (
        value.casefold().startswith(("http://", "https://"))
        or normalized_name in {
            "endpoint",
            "uri",
            "uritemplate",
            "url",
            "urltemplate",
        }
    ):
        return _safe_url(value)
    return value


def _backend_summary(backend):
    if not backend:
        return None
    properties = backend.get("properties") or {}
    return {
        "id": backend.get("id"),
        "name": backend.get("name"),
        "url": _safe_url(properties.get("url")),
        "protocol": properties.get("protocol"),
        "resourceId": properties.get("resourceId"),
        "credentials": _credential_summary(properties.get("credentials")),
        "properties": _sanitize_properties(properties),
    }


def _identity_summary(resource):
    identity = resource.get("identity") or {}
    identity_type = identity.get("type")
    user_assigned = identity.get("userAssignedIdentities") or {}
    return {
        "type": identity_type,
        "systemAssigned": (
            {
                "principalId": identity.get("principalId"),
                "tenantId": identity.get("tenantId"),
            }
            if "systemassigned" in str(identity_type or "").casefold()
            else None
        ),
        "userAssigned": [
            {
                "resourceId": resource_id,
                "clientId": properties.get("clientId"),
                "principalId": properties.get("principalId"),
            }
            for resource_id, properties in sorted(user_assigned.items())
        ],
    }


def _diagnostic_summary(diagnostic, scope_type):
    properties = diagnostic.get("properties") or {}
    return {
        "id": diagnostic.get("id"),
        "name": diagnostic.get("name"),
        "scopeType": scope_type,
        "loggerId": properties.get("loggerId"),
        "properties": _sanitize_properties(properties),
    }


def _logger_summary(logger_resource):
    properties = logger_resource.get("properties") or {}
    return {
        "id": logger_resource.get("id"),
        "name": logger_resource.get("name"),
        "loggerType": properties.get("loggerType"),
        "isBuffered": properties.get("isBuffered"),
        "resourceId": properties.get("resourceId"),
        "credentials": _credential_summary(properties.get("credentials")),
        "properties": _sanitize_properties(properties),
    }


def _referenced_loggers(diagnostics, loggers):
    by_reference = {}
    for logger_resource in loggers:
        summary = _logger_summary(logger_resource)
        for reference in (summary.get("id"), summary.get("name")):
            if reference:
                by_reference[str(reference).rstrip("/").casefold()] = summary
    referenced = []
    seen = set()
    for diagnostic in diagnostics:
        logger_id = (diagnostic.get("properties") or {}).get("loggerId")
        if not logger_id:
            continue
        key = str(logger_id).rstrip("/").casefold()
        summary = by_reference.get(key)
        if summary is None:
            summary = {"id": logger_id, "name": None, "unresolved": True}
        identity = str(summary.get("id") or summary.get("name")).casefold()
        if identity not in seen:
            seen.add(identity)
            referenced.append(summary)
    return referenced


def _subscription_summary(subscription, rank):
    properties = subscription.get("properties") or {}
    return {
        "id": subscription.get("id"),
        "name": subscription.get("name"),
        "displayName": properties.get("displayName"),
        "scope": properties.get("scope"),
        "state": properties.get("state"),
        "relationship": "api" if rank == 0 else "product",
    }


def _api_summary(api, workspace_name):
    properties = api.get("properties") or {}
    return {
        "id": api.get("id"),
        "name": api.get("name"),
        "type": api.get("type"),
        "etag": api.get("etag"),
        "displayName": properties.get("displayName"),
        "description": properties.get("description"),
        "workspace": workspace_name,
        "apiType": properties.get("type") or properties.get("apiType"),
        "path": properties.get("path"),
        "serviceUrl": _safe_url(properties.get("serviceUrl")),
        "protocols": properties.get("protocols") or [],
        "subscriptionRequired": bool(properties.get("subscriptionRequired")),
        "properties": _sanitize_properties(properties),
    }


def _operation_summary(operation, policy):
    properties = operation.get("properties") or {}
    return {
        "id": operation.get("id"),
        "name": operation.get("name"),
        "type": operation.get("type"),
        "displayName": properties.get("displayName"),
        "method": properties.get("method"),
        "urlTemplate": _safe_url(properties.get("urlTemplate")),
        "properties": _sanitize_properties(properties),
        "policy": policy,
    }


def _product_summary(product, policy):
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        "type": product.get("type"),
        "properties": _sanitize_properties(product.get("properties") or {}),
        "policy": policy,
    }


def _tool_summary(tool):
    properties = tool.get("properties") or {}
    return {
        "id": tool.get("id"),
        "name": tool.get("name"),
        "type": tool.get("type"),
        "displayName": properties.get("displayName"),
        "description": properties.get("description"),
        "operationId": properties.get("operationId"),
        "properties": _sanitize_properties(properties),
    }


def _discover_scope(
    cmd,
    scope_id,
    workspace_name,
    parent_policy,
    errors,
    scope_policy=None,
    service_diagnostics=None,
    service_loggers=None,
    apis_override=None,
    allow_mcp_tools=True,
):
    scope_label = (
        f"workspace '{workspace_name}'"
        if workspace_name is not None
        else "service scope"
    )
    logger.warning("Checking backends and APIs in APIM %s...", scope_label)
    backends = _optional_list(
        cmd,
        f"{scope_id}/backends",
        errors,
        f"{scope_id}/backends",
        "backends",
    )
    backend_by_name = {
        str(backend.get("name", "")).casefold(): backend for backend in backends
    }
    if scope_policy is None:
        scope_policy_xml = _optional_policy(cmd, scope_id, errors)
        scope_policy = _policy_summary(
            scope_policy_xml,
            scope_id,
            "workspace" if workspace_name is not None else "service",
        )
    apis = (
        apis_override
        if apis_override is not None
        else _optional_list(
            cmd,
            f"{scope_id}/apis",
            errors,
            f"{scope_id}/apis",
            "apis",
        )
    )
    scope_loggers = list(service_loggers or [])
    workspace_diagnostic_resources = []
    if workspace_name is not None:
        scope_loggers.extend(
            _optional_list(
                cmd,
                f"{scope_id}/loggers",
                errors,
                f"{scope_id}/loggers",
                "loggers",
                required=False,
            )
        )
        workspace_diagnostic_resources = _optional_list(
            cmd,
            f"{scope_id}/diagnostics",
            errors,
            f"{scope_id}/diagnostics",
            "diagnostics",
            required=False,
        )
    discovered = []
    for index, api in enumerate(apis, start=1):
        logger.warning(
            "Checking API '%s' in APIM %s (%d of %d)...",
            api.get("name") or "(unnamed)",
            scope_label,
            index,
            len(apis),
        )
        api_id = api.get("id") or (
            f"{scope_id}/apis/{quote(str(api.get('name') or ''), safe='')}"
        )
        api = {**api, "id": api_id}
        policy_xml = _optional_policy(cmd, api_id, errors)
        policy = _policy_summary(policy_xml, api_id, "api")
        backend_ids = list(policy["backendIds"])
        api_backend_id = (api.get("properties") or {}).get("backendId")
        if api_backend_id:
            backend_ids.append(unquote(str(api_backend_id).rsplit("/", 1)[-1]))
        resolved_backends = [
            backend_by_name[backend_id.casefold()]
            for backend_id in dict.fromkeys(backend_ids)
            if backend_id.casefold() in backend_by_name
        ]
        operations = _optional_list(
            cmd,
            f"{api_id}/operations",
            errors,
            f"{api_id}/operations",
            "operations",
        )
        schemas = _optional_list(
            cmd,
            f"{api_id}/schemas",
            errors,
            f"{api_id}/schemas",
            "schemas",
            required=False,
        )
        releases = _optional_list(
            cmd,
            f"{api_id}/releases",
            errors,
            f"{api_id}/releases",
            "releases",
            required=False,
        )
        operation_summaries = []
        operation_policies = []
        for operation in operations:
            operation_id = operation.get("id") or (
                f"{api_id}/operations/"
                f"{quote(str(operation.get('name') or ''), safe='')}"
            )
            operation_policy = _policy_summary(
                _optional_policy(cmd, operation_id, errors),
                operation_id,
                "operation",
            )
            operation_policies.append(operation_policy)
            operation_summaries.append(
                _operation_summary(
                    {**operation, "id": operation_id},
                    operation_policy,
                )
            )
        products = _optional_list(
            cmd,
            f"{api_id}/products",
            errors,
            f"{api_id}/products",
            "products",
            required=bool(
                (api.get("properties") or {}).get("subscriptionRequired")
            ),
        )
        product_summaries = []
        product_policies = []
        for product in products:
            product_id = product.get("id")
            if not product_id:
                continue
            product_policy = _policy_summary(
                _optional_policy(cmd, product_id, errors),
                product_id,
                "product",
            )
            product_policies.append(product_policy)
            product_summaries.append(
                _product_summary(product, product_policy)
            )
        tools = []
        if allow_mcp_tools and str(
            (api.get("properties") or {}).get("type")
            or (api.get("properties") or {}).get("apiType")
            or ""
        ).casefold() == "mcp":
            tools = [
                _tool_summary(tool)
                for tool in _optional_list(
                    cmd,
                    f"{api_id}/tools",
                    errors,
                    f"{api_id}/tools",
                    "mcpTools",
                    api_version=APIM_MCP_API_VERSION,
                )
            ]
        api_diagnostic_resources = _optional_list(
            cmd,
            f"{api_id}/diagnostics",
            errors,
            f"{api_id}/diagnostics",
            "diagnostics",
            required=False,
        )
        all_diagnostic_resources = [
            *(service_diagnostics or []),
            *workspace_diagnostic_resources,
            *api_diagnostic_resources,
        ]
        diagnostics = [
            *[
                _diagnostic_summary(diagnostic, "service")
                for diagnostic in service_diagnostics or []
            ],
            *[
                _diagnostic_summary(diagnostic, "workspace")
                for diagnostic in workspace_diagnostic_resources
            ],
            *[
                _diagnostic_summary(diagnostic, "api")
                for diagnostic in api_diagnostic_resources
            ],
        ]
        inherited_policies = []
        if not policy["present"] or policy["inheritsParent"]:
            inherited_policies.append(scope_policy)
            if (
                workspace_name is not None
                and (
                    not scope_policy["present"]
                    or scope_policy["inheritsParent"]
                )
            ):
                if parent_policy is not None:
                    inherited_policies.append(parent_policy)
        discovered.append(
            {
                "api": api,
                "source": _api_summary(api, workspace_name),
                "policy": policy,
                "inheritedPolicies": inherited_policies,
                "backends": resolved_backends,
                "operations": operation_summaries,
                "schemas": schemas,
                "releases": releases,
                "operationPolicies": operation_policies,
                "products": product_summaries,
                "productPolicies": product_policies,
                "tools": tools,
                "diagnostics": diagnostics,
                "loggers": _referenced_loggers(
                    all_diagnostic_resources,
                    scope_loggers,
                ),
                "subscriptions": [],
            }
        )
    return (
        discovered,
        scope_policy,
        {
            "id": scope_id,
            "name": workspace_name,
            "scopeType": "workspace" if workspace_name is not None else "service",
            "policy": scope_policy,
            "backends": [
                _backend_summary(backend)
                for backend in backends
            ],
            "diagnostics": [
                _diagnostic_summary(
                    diagnostic,
                    "workspace" if workspace_name is not None else "service",
                )
                for diagnostic in (
                    workspace_diagnostic_resources
                    if workspace_name is not None
                    else service_diagnostics or []
                )
            ],
            "loggers": [
                _logger_summary(logger_resource)
                for logger_resource in scope_loggers
            ],
        },
    )


def _exclude_mcp_backing_apis(assets):
    backing_api_references = {}
    for asset in assets:
        if str(asset["source"].get("apiType") or "").casefold() != "mcp":
            continue
        for tool in asset.get("tools") or []:
            operation_id = tool.get("operationId")
            if (
                not isinstance(operation_id, str)
                or "/apis/" not in operation_id.casefold()
                or "/operations/" not in operation_id.casefold()
            ):
                continue
            backing_api_id = re.sub(
                r"/operations/[^/]+/?$",
                "",
                operation_id,
                flags=re.IGNORECASE,
            ).casefold()
            backing_api_references.setdefault(backing_api_id, set()).add(
                asset["source"]["id"]
            )
    included = []
    suppressed = []
    for asset in assets:
        source_id = asset["source"]["id"]
        required_by = backing_api_references.get(source_id.casefold())
        if required_by:
            suppressed.append(
                {
                    **asset["source"],
                    "dependencyType": "mcpRestBackingApi",
                    "requiredBy": sorted(required_by),
                    "reasonCode": "MCP_REST_BACKING_API",
                    "reason": (
                        "This REST API backs an MCP server and is retained as "
                        "a dependency rather than a standalone import candidate."
                    ),
                }
            )
        else:
            included.append(asset)
    return included, suppressed


def _subscription_scope_rank(subscription, asset):
    properties = subscription.get("properties") or {}
    if str(properties.get("state") or "active").casefold() != "active":
        return None
    scope = str(properties.get("scope") or "").rstrip("/").casefold()
    api_id = asset["source"]["id"].rstrip("/").casefold()
    api_name = str(asset["source"].get("name") or "").casefold()
    if scope in {api_id, f"/apis/{api_name}"}:
        return 0
    product_scopes = {
        str(product.get("id") or "").rstrip("/").casefold()
        for product in asset.get("products") or []
    }
    product_scopes.update(
        f"/products/{str(product.get('name') or '').casefold()}"
        for product in asset.get("products") or []
        if product.get("name")
    )
    return 1 if scope in product_scopes else None


def _attach_subscription_relationships(assets, subscriptions):
    for asset in assets:
        relationships = []
        for subscription in subscriptions:
            rank = _subscription_scope_rank(subscription, asset)
            if rank is not None:
                relationships.append(
                    _subscription_summary(subscription, rank)
                )
        asset["subscriptions"] = sorted(
            relationships,
            key=lambda relationship: (
                relationship["relationship"],
                str(relationship.get("name") or "").casefold(),
            ),
        )


def _merge_api_inventories(stable_apis, preview_mcp_apis):
    merged = {}
    for api in [*stable_apis, *preview_mcp_apis]:
        identity = str(api.get("id") or api.get("name") or "").casefold()
        if not identity:
            continue
        existing = merged.get(identity) or {}
        properties = {
            **(existing.get("properties") or {}),
            **(api.get("properties") or {}),
        }
        merged[identity] = {**existing, **api, "properties": properties}
    return sorted(
        merged.values(),
        key=lambda item: str(item.get("id") or item.get("name") or "").casefold(),
    )


def _discover_source(
    cmd,
    source_apim_id,
    *,
    suppress_mcp_backing_apis=True,
    resolve_subscription_credentials=False,
    require_supported_sku=True,
):
    if resolve_subscription_credentials:
        raise InvalidArgumentValueError(
            "Read-only inventory discovery cannot retrieve subscription secrets."
        )
    errors = _DiscoveryErrors()
    logger.warning("Checking source APIM resource and service policy...")
    source = _response_json(
        _source_request(
            cmd,
            "GET",
            source_apim_id,
            api_version=APIM_INVENTORY_API_VERSION,
        )
    )
    source_sku = str((source.get("sku") or {}).get("name", ""))
    if (
        require_supported_sku
        and source_sku.casefold() not in SUPPORTED_SOURCE_SKUS
    ):
        raise InvalidArgumentValueError(
            "--source-apim-id must identify an API Management service using "
            "the BasicV2, StandardV2, or PremiumV2 SKU."
        )
    source_policy_xml = _optional_policy(cmd, source_apim_id, errors)
    source_policy = _policy_summary(
        source_policy_xml,
        source_apim_id,
        "service",
    )
    service_loggers = _optional_list(
        cmd,
        f"{source_apim_id}/loggers",
        errors,
        f"{source_apim_id}/loggers",
        "loggers",
        required=False,
    )
    service_diagnostics = _optional_list(
        cmd,
        f"{source_apim_id}/diagnostics",
        errors,
        f"{source_apim_id}/diagnostics",
        "diagnostics",
        required=False,
    )
    stable_root_apis = _optional_list(
        cmd,
        f"{source_apim_id}/apis",
        errors,
        f"{source_apim_id}/apis",
        "apis",
    )
    preview_mcp_apis = _optional_list(
        cmd,
        f"{source_apim_id}/apis?%24filter=type%20eq%20%27mcp%27",
        errors,
        f"{source_apim_id}/apis",
        "mcpApis",
        required=False,
        api_version=APIM_MCP_API_VERSION,
    )
    root_assets, _, root_scope = _discover_scope(
        cmd,
        source_apim_id,
        None,
        source_policy,
        errors,
        scope_policy=source_policy,
        service_diagnostics=service_diagnostics,
        service_loggers=service_loggers,
        apis_override=_merge_api_inventories(
            stable_root_apis,
            preview_mcp_apis,
        ),
    )
    assets = list(root_assets)
    scopes = [root_scope]
    logger.warning("Checking APIM workspaces...")
    workspaces = _optional_list(
        cmd,
        f"{source_apim_id}/workspaces",
        errors,
        f"{source_apim_id}/workspaces",
        "workspaces",
        required=True,
    )
    for workspace in workspaces:
        workspace_name = workspace.get("name")
        if not workspace_name:
            continue
        workspace_id = workspace.get("id") or (
            f"{source_apim_id}/workspaces/"
            f"{quote(str(workspace_name), safe='')}"
        )
        workspace_assets, _, workspace_scope = _discover_scope(
            cmd,
            workspace_id,
            workspace_name,
            source_policy,
            errors,
            service_diagnostics=service_diagnostics,
            service_loggers=service_loggers,
            allow_mcp_tools=False,
        )
        assets.extend(workspace_assets)
        scopes.append(workspace_scope)
        errors.coverage.append(
            {
                "scope": f"{workspace_id}/apis/*/tools",
                "configurationDomain": "mcpTools",
                "status": "notApplicable",
                "apiVersion": APIM_MCP_API_VERSION,
                "observedCount": 0,
                "pagesCompleted": 0,
                "requiredForEnumeration": False,
                "reason": "APIM workspaces do not support MCP servers.",
            }
        )
    source_api_count = len(assets)
    suppressed_assets = []
    if suppress_mcp_backing_apis:
        assets, suppressed_assets = _exclude_mcp_backing_apis(assets)
    subscriptions = _optional_list(
        cmd,
        f"{source_apim_id}/subscriptions",
        errors,
        f"{source_apim_id}/subscriptions",
        "subscriptions",
        required=any(
            asset["source"].get("subscriptionRequired")
            for asset in assets
        ),
    )
    _attach_subscription_relationships(assets, subscriptions)
    properties = source.get("properties") or {}
    return {
        "source": {
            "id": source.get("id") or source_apim_id,
            "name": source.get("name"),
            "etag": source.get("etag"),
            "location": source.get("location"),
            "sku": source_sku,
            "skuCapacity": (source.get("sku") or {}).get("capacity"),
            "zones": source.get("zones") or [],
            "customHostnames": _sanitize_properties(
                properties.get("hostnameConfigurations") or []
            ),
            "additionalLocations": _sanitize_properties(
                properties.get("additionalLocations") or []
            ),
            "gatewayUrl": _safe_url(properties.get("gatewayUrl")),
            "networkConfiguration": _network_configuration(source),
            "managedIdentities": _identity_summary(source),
            "provisioningState": properties.get("provisioningState"),
            "targetProvisioningState": properties.get(
                "targetProvisioningState"
            ),
        },
        "assets": assets,
        "scopes": scopes,
        "sourceApiCount": source_api_count,
        "suppressedAssets": suppressed_assets,
        "errors": errors,
        "collectionCoverage": errors.coverage,
    }

def _network_configuration(resource):
    properties = resource.get("properties") or {}
    virtual_network = properties.get("virtualNetworkConfiguration") or {}
    return {
        "publicNetworkAccess": properties.get("publicNetworkAccess") or "Enabled",
        "virtualNetworkType": properties.get("virtualNetworkType") or "None",
        "subnetResourceId": virtual_network.get("subnetResourceId"),
        "privateEndpointConnectionCount": len(
            properties.get("privateEndpointConnections") or []
        ),
    }


def _mcp_dependencies(record):
    dependencies = {}
    for tool in record.get("tools") or []:
        operation_id = tool.get("operationId")
        if not operation_id:
            continue
        api_id = re.sub(
            r"/operations/[^/]+/?$",
            "",
            str(operation_id),
            flags=re.IGNORECASE,
        )
        dependency = dependencies.setdefault(
            api_id,
            {
                "apiId": api_id,
                "operationIds": [],
                "toolIds": [],
            },
        )
        dependency["operationIds"].append(operation_id)
        if tool.get("id") or tool.get("name"):
            dependency["toolIds"].append(tool.get("id") or tool.get("name"))
    return [
        {
            **dependency,
            "operationIds": sorted(set(dependency["operationIds"])),
            "toolIds": sorted(set(dependency["toolIds"])),
        }
        for _, dependency in sorted(dependencies.items())
    ]
