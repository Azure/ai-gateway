# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import (
    HTTPError,
    InvalidArgumentValueError,
)
from requests import Response

from azext_ai_gateway import _import_discovery


SOURCE_ID = (
    "/subscriptions/source-sub/resourceGroups/source-rg/providers/"
    "Microsoft.ApiManagement/service/source"
)


def test_safe_url_handles_non_string_values():
    assert _import_discovery._safe_url({"url": "https://example.test"}) == (
        "<invalid>"
    )


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


@patch("azext_ai_gateway._import_discovery._request")
def test_optional_policy_accepts_bom_prefixed_raw_xml(request):
    policy = "<policies><inbound><base /></inbound></policies>"
    response = Response()
    response._content = policy.encode("utf-8-sig")
    response.encoding = "utf-8"
    request.return_value = response
    errors = []

    assert _import_discovery._optional_policy(None, SOURCE_ID, errors) == policy
    assert errors == []
    request.assert_called_once_with(
        None,
        "GET",
        f"{SOURCE_ID}/policies/policy?format=rawxml",
        api_version=_import_discovery.APIM_INVENTORY_API_VERSION,
    )


@patch("azext_ai_gateway._import_discovery._request")
def test_list_all_uses_source_version_only_on_each_explicit_page(request):
    request.side_effect = [
        FakeResponse(
            {
                "value": [{"name": "first"}],
                "nextLink": "https://management.azure.com/next?api-version=server",
            }
        ),
        FakeResponse({"value": [{"name": "second"}]}),
    ]

    result = _import_discovery._list_all(
        None,
        f"{SOURCE_ID}/apis",
        api_version=_import_discovery.APIM_INVENTORY_API_VERSION,
    )

    assert result == [{"name": "first"}, {"name": "second"}]
    assert request.call_args_list == [
        call(
            None,
            "GET",
            f"{SOURCE_ID}/apis",
            api_version=_import_discovery.APIM_INVENTORY_API_VERSION,
        ),
        call(
            None,
            "GET",
            "https://management.azure.com/next?api-version=server",
            include_api_version=False,
            api_version=_import_discovery.APIM_INVENTORY_API_VERSION,
        ),
    ]


@patch("azext_ai_gateway._import_discovery.time.sleep")
@patch("azext_ai_gateway._import_discovery._request")
def test_source_list_retries_throttling_and_honors_retry_after(request, sleep):
    response = Response()
    response.status_code = 429
    response.headers["Retry-After"] = "3"
    request.side_effect = [
        HTTPError("throttled", response),
        FakeResponse({"value": [{"name": "api"}]}),
    ]

    result = _import_discovery._list_all(
        None,
        f"{SOURCE_ID}/apis",
        api_version=_import_discovery.APIM_INVENTORY_API_VERSION,
    )

    assert result == [{"name": "api"}]
    sleep.assert_called_once_with(3.0)


@patch("azext_ai_gateway._import_discovery._request")
def test_optional_list_preserves_completed_pages_on_continuation_failure(request):
    response = Response()
    response.status_code = 403
    response._content = b'{"error":{"code":"AuthorizationFailed"}}'
    request.side_effect = [
        FakeResponse(
            {
                "value": [{"name": "observed"}],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        HTTPError("forbidden", response),
    ]
    errors = _import_discovery._DiscoveryErrors()

    result = _import_discovery._optional_list(
        None,
        f"{SOURCE_ID}/apis",
        errors,
        f"{SOURCE_ID}/apis",
        "apis",
    )

    assert result == [{"name": "observed"}]
    assert errors[0]["category"] == "authorization"
    assert errors.coverage[0]["status"] == "partial"
    assert errors.coverage[0]["observedCount"] == 1
    assert errors.coverage[0]["pagesCompleted"] == 1


def test_platform_health_error_is_structured_for_scale_unit_mismatch():
    response = Response()
    response.status_code = 400
    response.headers["x-ms-request-id"] = "request-id"
    response._content = b'{"error":{"code":"InvalidOperation"}}'
    error = HTTPError(
        "Scale unit 'unit' (family '0') requires family 'SkuV2'.",
        response,
    )

    details = _import_discovery._http_error(error)

    assert details["category"] == "platformHealth"
    assert details["retryable"] is False
    assert details["requestId"] == "request-id"
    assert "Resource Health" in details["remediation"]


def test_sanitize_properties_normalizes_secret_key_names():
    sanitized = _import_discovery._sanitize_properties(
        {
            "api-key": "secret",
            "access_token": "token",
            "Authorization": "Bearer secret",
            "authorizationServerId": "safe-id",
        }
    )

    assert sanitized == {
        "api-key": "<redacted>",
        "access_token": "<redacted>",
        "Authorization": "<redacted>",
        "authorizationServerId": "safe-id",
    }


def _record(
    name="asset",
    api_type="http",
    service_url="https://example.test",
    path="asset",
    backend=None,
    operations=None,
    policy=None,
):
    api_id = f"{SOURCE_ID}/apis/{name}"
    return {
        "api": {
            "id": api_id,
            "name": name,
            "properties": {
                "displayName": name.title(),
                "type": api_type,
                "path": path,
                "serviceUrl": service_url,
                "protocols": ["https"],
                "subscriptionRequired": False,
            },
        },
        "source": {
            "id": api_id,
            "name": name,
            "displayName": name.title(),
            "description": None,
            "workspace": None,
            "apiType": api_type,
            "path": path,
            "serviceUrl": service_url,
            "protocols": ["https"],
            "subscriptionRequired": False,
        },
        "policy": policy or _import_discovery._policy_summary(None, api_id),
        "inheritedPolicies": [],
        "backends": [backend] if backend else [],
        "operations": operations
        or [
            {
                "name": "invoke",
                "displayName": "Invoke",
                "method": "POST",
                "urlTemplate": "/invoke",
            }
        ],
    }


def _mcp_record(name="asset", passthrough=True):
    record = _record(
        name=name,
        api_type="mcp",
        service_url=(
            "https://mcp.example.test"
            if passthrough
            else None
        ),
    )
    if passthrough:
        record["api"]["properties"]["mcpProperties"] = {
            "transportType": "streamable",
            "endpoints": [{"name": "message", "uriTemplate": "/mcp"}],
        }
    else:
        record["tools"] = [
            {
                "name": "invoke",
                "operationId": (
                    f"{SOURCE_ID}/apis/backing/operations/invoke"
                ),
            }
        ]
    return record



def test_parse_apim_id_accepts_complete_service_resource_id():
    assert _import_discovery._parse_apim_id(SOURCE_ID) == {
        "subscription": "source-sub",
        "resource_group": "source-rg",
        "name": "source",
    }


@pytest.mark.parametrize(
    "resource_id",
    [
        "source",
        "/subscriptions/sub/resourceGroups/rg",
        f"{SOURCE_ID}/apis/api",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/sites/app",
    ],
)
def test_parse_apim_id_rejects_non_service_ids(resource_id):
    with pytest.raises(InvalidArgumentValueError):
        _import_discovery._parse_apim_id(resource_id)


def test_policy_summary_reports_names_without_exposing_values():
    policy = """
    <policies>
      <inbound>
        <base />
        <set-backend-service backend-id="model-backend" />
        <set-header name="api-key" exists-action="override">
          <value>super-secret</value>
        </set-header>
        <llm-token-limit counter-key="@(context.Subscription.Id)"
                         tokens-per-minute="1000" />
      </inbound>
    </policies>
    """

    summary = _import_discovery._policy_summary(policy, "api")

    assert summary["inheritsParent"] is True
    assert summary["backendIds"] == ["model-backend"]
    assert summary["recognizedStatements"] == [
        "llm-token-limit",
        "set-backend-service",
    ]
    assert summary["unsupportedStatements"] == ["set-header"]
    assert summary["translatedPolicies"] == [
        {
            "type": "tokenLimit",
            "period": "minute",
            "count": 1000,
            "counterKey": "Identity",
        }
    ]
    assert "subscription counters become AI Gateway Identity" in str(
        summary["translationWarnings"]
    )
    assert "super-secret" not in str(summary)


def test_policy_summary_blocks_malformed_xml():
    summary = _import_discovery._policy_summary("<policies>", "api")

    assert summary["parseError"]
    assert summary["inheritsParent"] is False


def test_policy_summary_treats_forward_request_as_structural():
    summary = _import_discovery._policy_summary(
        """
        <policies>
          <inbound><base /></inbound>
          <backend><forward-request /></backend>
        </policies>
        """,
        "api",
    )

    assert summary["statements"] == []
    assert summary["unsupportedStatements"] == []


def test_discover_source_inventories_service_and_workspace_apis():
    root_api = {
        "id": f"{SOURCE_ID}/apis/chat",
        "name": "chat",
        "properties": {
            "type": "http",
            "path": "chat",
            "backendId": "openai",
            "subscriptionRequired": False,
        },
    }
    workspace_id = f"{SOURCE_ID}/workspaces/team"
    workspace_api = {
        "id": f"{workspace_id}/apis/tools",
        "name": "tools",
        "properties": {
            "type": "mcp",
            "path": "tools",
            "subscriptionRequired": False,
        },
    }
    backend = {
        "id": f"{SOURCE_ID}/backends/openai",
        "name": "openai",
        "properties": {"url": "https://account.openai.azure.com"},
    }

    def optional_list(_cmd, url, _errors, _context, *_args, **_kwargs):
        values = {
            f"{SOURCE_ID}/loggers": [],
            f"{SOURCE_ID}/diagnostics": [],
            f"{SOURCE_ID}/backends": [backend],
            f"{SOURCE_ID}/apis": [root_api],
            (
                f"{SOURCE_ID}/apis?"
                "%24filter=type%20eq%20%27mcp%27"
            ): [],
            f"{root_api['id']}/operations": [
                {
                    "name": "chat",
                    "properties": {
                        "displayName": "Chat",
                        "method": "POST",
                        "urlTemplate": "/chat/completions",
                    },
                }
            ],
            f"{root_api['id']}/schemas": [],
            f"{root_api['id']}/releases": [],
            f"{root_api['id']}/products": [],
            f"{root_api['id']}/diagnostics": [],
            f"{SOURCE_ID}/workspaces": [
                {"id": workspace_id, "name": "team"}
            ],
            f"{workspace_id}/loggers": [],
            f"{workspace_id}/diagnostics": [],
            f"{workspace_id}/backends": [],
            f"{workspace_id}/apis": [workspace_api],
            f"{workspace_api['id']}/operations": [],
            f"{workspace_api['id']}/schemas": [],
            f"{workspace_api['id']}/releases": [],
            f"{workspace_api['id']}/products": [],
            f"{workspace_api['id']}/tools": [],
            f"{workspace_api['id']}/diagnostics": [],
            f"{SOURCE_ID}/subscriptions": [],
        }
        return values[url]

    def optional_policy(_cmd, scope_id, _errors):
        policies = {
            SOURCE_ID: "<policies><inbound><base /></inbound></policies>",
            root_api["id"]: (
                "<policies><inbound><base /></inbound></policies>"
            ),
            f"{root_api['id']}/operations/chat": None,
            workspace_id: None,
            workspace_api["id"]: None,
        }
        return policies[scope_id]

    source_resource = {
        "id": SOURCE_ID,
        "name": "source",
        "location": "eastus",
        "sku": {"name": "StandardV2"},
        "properties": {
            "gatewayUrl": "https://source.azure-api.net?sig=secret",
            "publicNetworkAccess": "Disabled",
            "virtualNetworkType": "External",
            "virtualNetworkConfiguration": {
                "subnetResourceId": (
                    "/subscriptions/source-sub/resourceGroups/network-rg/"
                    "providers/Microsoft.Network/virtualNetworks/vnet/"
                    "subnets/integration"
                )
            },
        },
    }
    with (
        patch.object(
            _import_discovery,
            "_request",
            return_value=FakeResponse(source_resource),
        ),
        patch.object(_import_discovery, "_optional_list", side_effect=optional_list),
        patch.object(_import_discovery, "_optional_policy", side_effect=optional_policy),
    ):
        result = _import_discovery._discover_source(None, SOURCE_ID)

    assert result["source"]["gatewayUrl"] == (
        "https://source.azure-api.net?sig=%3Credacted%3E"
    )
    assert result["source"]["networkConfiguration"] == {
        "publicNetworkAccess": "Disabled",
        "virtualNetworkType": "External",
        "subnetResourceId": (
            "/subscriptions/source-sub/resourceGroups/network-rg/providers/"
            "Microsoft.Network/virtualNetworks/vnet/subnets/integration"
        ),
        "privateEndpointConnectionCount": 0,
    }
    assert len(result["assets"]) == 2
    assert result["assets"][0]["backends"] == [backend]
    assert result["assets"][0]["operations"][0]["method"] == "POST"
    assert result["assets"][1]["source"]["workspace"] == "team"
    assert [
        policy["scope"]
        for policy in result["assets"][1]["inheritedPolicies"]
    ] == [workspace_id, SOURCE_ID]
    assert result["sourceApiCount"] == 2
    assert result["suppressedAssets"] == []
    assert result["assets"][1]["tools"] == []
    assert result["collectionCoverage"] == [
        {
            "scope": f"{workspace_id}/apis/*/tools",
            "configurationDomain": "mcpTools",
            "status": "notApplicable",
            "apiVersion": _import_discovery.APIM_MCP_API_VERSION,
            "observedCount": 0,
            "pagesCompleted": 0,
            "requiredForEnumeration": False,
            "reason": "APIM workspaces do not support MCP servers.",
        }
    ]


def test_mcp_server_suppresses_its_backing_rest_api():
    api_id = f"{SOURCE_ID}/apis/colors-api"
    mcp_id = f"{SOURCE_ID}/apis/colors-mcp"
    rest_api = _record(name="colors-api")
    mcp_api = _record(
        name="colors-mcp",
        api_type="mcp",
        service_url="https://source.azure-api.net/colors-mcp/mcp",
    )
    mcp_api["tools"] = [
        {
            "name": "get-color",
            "operationId": f"{api_id}/operations/get-color",
        }
    ]

    included, suppressed = _import_discovery._exclude_mcp_backing_apis(
        [rest_api, mcp_api]
    )

    assert [asset["source"]["id"] for asset in included] == [mcp_id]
    assert [asset["id"] for asset in suppressed] == [api_id]
    assert suppressed[0]["dependencyType"] == "mcpRestBackingApi"
    assert suppressed[0]["requiredBy"] == [mcp_id]
    assert suppressed[0]["reasonCode"] == "MCP_REST_BACKING_API"


def test_discover_source_rejects_non_v2_sku_before_asset_discovery():
    source_resource = {
        "id": SOURCE_ID,
        "name": "source",
        "sku": {"name": "Developer"},
        "properties": {},
    }

    with (
        patch.object(
            _import_discovery,
            "_request",
            return_value=FakeResponse(source_resource),
        ),
        patch.object(_import_discovery, "_optional_policy") as optional_policy,
        pytest.raises(InvalidArgumentValueError, match="BasicV2"),
    ):
        _import_discovery._discover_source(None, SOURCE_ID)

    optional_policy.assert_not_called()


def test_backend_summary_redacts_credential_values():
    backend = {
        "id": f"{SOURCE_ID}/backends/private",
        "name": "private",
        "properties": {
            "url": "https://private.example.test",
            "credentials": {
                "header": {"api-key": ["super-secret"]},
                "query": {"code": ["another-secret"]},
                "authorization": {
                    "scheme": "Basic",
                    "parameter": "encoded-secret",
                },
            },
        },
    }

    summary = _import_discovery._backend_summary(backend)

    assert summary["credentials"] == {
        "hasCredentials": True,
        "headerNames": ["api-key"],
        "queryParameterNames": ["code"],
        "authorizationScheme": "Basic",
        "namedValueReferences": [],
    }
    assert "super-secret" not in str(summary)
    assert "another-secret" not in str(summary)
    assert "encoded-secret" not in str(summary)


def test_safe_url_redacts_user_info_and_query_values():
    safe = _import_discovery._safe_url(
        "https://user:password@example.test/path?api-version=1&sig=secret"
    )

    assert safe == (
        "https://example.test/path?"
        "api-version=%3Credacted%3E&sig=%3Credacted%3E"
    )
    assert "user" not in safe
    assert "password" not in safe
    assert "secret" not in safe


def test_api_summary_preserves_complete_properties_and_redacts_secrets():
    api = {
        "id": f"{SOURCE_ID}/apis/chat",
        "name": "chat",
        "type": "Microsoft.ApiManagement/service/apis",
        "etag": "etag-value",
        "properties": {
            "displayName": "Chat",
            "apiRevision": "7",
            "apiRevisionDescription": "Production revision",
            "serviceUrl": (
                "https://user:password@example.test/openai?api-key=secret"
            ),
            "protocols": ["https"],
            "authenticationSettings": {
                "clientSecret": "secret",
                "accessToken": "token",
                "authorizationServerId": "server",
            },
            "subscriptionKeyParameterNames": {
                "header": "Ocp-Apim-Subscription-Key",
                "query": "subscription-key",
            },
        },
    }

    summary = _import_discovery._api_summary(api, "team")

    assert summary["type"] == "Microsoft.ApiManagement/service/apis"
    assert summary["etag"] == "etag-value"
    assert summary["properties"]["apiRevision"] == "7"
    assert summary["properties"]["apiRevisionDescription"] == (
        "Production revision"
    )
    assert summary["properties"]["serviceUrl"] == (
        "https://example.test/openai?api-key=%3Credacted%3E"
    )
    assert summary["properties"]["authenticationSettings"] == {
        "clientSecret": "<redacted>",
        "accessToken": "<redacted>",
        "authorizationServerId": "server",
    }
    assert summary["properties"]["subscriptionKeyParameterNames"] == {
        "header": "Ocp-Apim-Subscription-Key",
        "query": "subscription-key",
    }
    assert "password" not in str(summary)
    assert '"secret"' not in str(summary)
