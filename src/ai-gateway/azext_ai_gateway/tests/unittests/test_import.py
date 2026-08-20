# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import io
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError
from requests import Response

from azext_ai_gateway import _import


SOURCE_ID = (
    "/subscriptions/source-sub/resourceGroups/source-rg/providers/"
    "Microsoft.ApiManagement/service/source"
)
DESTINATION_ID = (
    "/subscriptions/destination-sub/resourceGroups/destination-rg/providers/"
    "Microsoft.ApiManagement/service/destination"
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}"

    def json(self):
        return self._payload


@patch("azext_ai_gateway._import._request")
def test_optional_policy_accepts_bom_prefixed_raw_xml(request):
    policy = "<policies><inbound><base /></inbound></policies>"
    response = Response()
    response._content = policy.encode("utf-8-sig")
    response.encoding = "utf-8"
    request.return_value = response
    errors = []

    assert _import._optional_policy(None, SOURCE_ID, errors) == policy
    assert errors == []


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
        "policy": policy or _import._policy_summary(None, api_id),
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


def _destination():
    return {
        "resource": {
            "id": DESTINATION_ID,
            "name": "destination",
            "location": "eastus",
        },
        "providers": [],
        "modelKeys": set(),
        "unscopedModelNames": set(),
        "toolNames": set(),
    }


def test_parse_apim_id_accepts_complete_service_resource_id():
    assert _import._parse_apim_id(SOURCE_ID) == {
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
        _import._parse_apim_id(resource_id)


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

    summary = _import._policy_summary(policy, "api")

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
    summary = _import._policy_summary("<policies>", "api")

    assert summary["parseError"]
    assert summary["inheritsParent"] is False


def test_token_rate_limit_translates_exact_fields_and_warns_on_omissions():
    summary = _import._policy_summary(
        """
        <policies>
          <inbound>
            <llm-token-limit
              counter-key="@(context.Request.IpAddress)"
              tokens-per-minute="5000"
              estimate-prompt-tokens="false"
              remaining-tokens-header-name="remaining" />
          </inbound>
        </policies>
        """,
        "api",
    )

    assert summary["translatedPolicies"] == [
        {
            "type": "tokenLimit",
            "period": "minute",
            "count": 5000,
            "counterKey": "IPAddress",
        }
    ]
    assert summary["translationWarnings"] == [
        "llm-token-limit attributes are not supported and will be omitted: "
        "estimate-prompt-tokens, remaining-tokens-header-name"
    ]


def test_token_quota_translates_hourly_and_rejects_longer_periods():
    hourly = _import._policy_summary(
        """
        <policies><inbound>
          <llm-token-limit counter-key="@(context.Subscription.Id)"
            token-quota="100000" token-quota-period="Hourly" />
        </inbound></policies>
        """,
        "api",
    )
    monthly = _import._policy_summary(
        """
        <policies><inbound>
          <llm-token-limit counter-key="@(context.Subscription.Id)"
            token-quota="100000" token-quota-period="Monthly" />
        </inbound></policies>
        """,
        "api",
    )

    assert hourly["translatedPolicies"] == [
        {
            "type": "tokenLimit",
            "period": "hour",
            "count": 100000,
            "counterKey": "Identity",
        }
    ]
    assert monthly["translatedPolicies"] == []
    assert "quota period 'Monthly' is not supported" in str(
        monthly["translationWarnings"]
    )


def test_compound_counter_key_is_not_reduced_to_ip_address():
    summary = _import._policy_summary(
        """
        <policies><inbound>
          <llm-token-limit
            counter-key="@(context.Request.IpAddress + context.Subscription.Id)"
            tokens-per-minute="5000" />
        </inbound></policies>
        """,
        "api",
    )

    assert summary["translatedPolicies"] == []
    assert "counter-key expression cannot be represented" in str(
        summary["translationWarnings"]
    )
    assert "token rate '5000' will not be translated" in str(
        summary["translationWarnings"]
    )


def test_four_level_content_safety_uses_documented_threshold_values():
    summary = _import._policy_summary(
        """
        <policies><inbound>
          <llm-content-safety backend-id="safety">
            <categories output-type="FourSeverityLevels">
              <category name="Hate" threshold="2" />
              <category name="Sexual" threshold="4" />
              <category name="Violence" threshold="6" />
            </categories>
          </llm-content-safety>
        </inbound></policies>
        """,
        "api",
    )

    assert summary["translatedPolicies"] == [
        {
            "type": "contentSafety",
            "hateSeverity": "Low",
            "sexualSeverity": "Medium",
            "violenceSeverity": "High",
        }
    ]


def test_content_safety_translates_thresholds_and_warns_on_lossy_features():
    summary = _import._policy_summary(
        """
        <policies><inbound>
          <llm-content-safety backend-id="safety-secret"
            shield-prompt="true">
            <categories output-type="EightSeverityLevels">
              <category name="Hate" threshold="0" />
              <category name="SelfHarm" threshold="2" />
              <category name="Sexual" threshold="4" />
              <category name="Violence" threshold="6" />
            </categories>
            <blocklists><id>private-blocklist</id></blocklists>
          </llm-content-safety>
        </inbound></policies>
        """,
        "api",
    )

    assert summary["translatedPolicies"] == [
        {
            "type": "contentSafety",
            "hateSeverity": "Low",
            "selfHarmSeverity": "Low",
            "sexualSeverity": "Medium",
            "violenceSeverity": "High",
        }
    ]
    assert "blocklists are not supported" in str(
        summary["translationWarnings"]
    )
    assert "backend-id, shield-prompt" in str(summary["translationWarnings"])
    assert "safety-secret" not in str(summary)
    assert "private-blocklist" not in str(summary)


def test_nested_policy_is_not_translated_unconditionally():
    summary = _import._policy_summary(
        """
        <policies><inbound>
          <choose>
            <when condition="@(context.Request.IpAddress != null)">
              <llm-token-limit
                counter-key="@(context.Request.IpAddress)"
                tokens-per-minute="5000" />
            </when>
          </choose>
        </inbound></policies>
        """,
        "api",
    )

    assert summary["translatedPolicies"] == []
    assert "nested policies cannot be translated" in str(
        summary["translationWarnings"]
    )


def test_policy_outside_supported_sections_produces_warning():
    summary = _import._policy_summary(
        """
        <policies><backend>
          <llm-token-limit counter-key="@(context.Request.IpAddress)"
            tokens-per-minute="5000" />
        </backend></policies>
        """,
        "api",
    )

    assert summary["translatedPolicies"] == []
    assert "backend section cannot be translated" in str(
        summary["translationWarnings"]
    )


def test_unsupported_policy_statement_becomes_warning_not_blocker():
    record = _record(
        policy=_import._policy_summary(
            """
            <policies><inbound>
              <validate-jwt header-name="Authorization" />
            </inbound></policies>
            """,
            f"{SOURCE_ID}/apis/asset",
        )
    )

    asset = _import._inventory_asset(
        record,
        {},
        _destination(),
        {},
        "fail",
        [],
    )

    assert asset["assessment"]["status"] == "ready"
    assert "validate-jwt" in str(asset["assessment"]["warnings"])
    assert asset["configuration"]["destinationPolicies"] == []


def test_operation_policy_is_inventoried_but_not_moved_to_asset_scope():
    record = _record()
    operation_policy = _import._policy_summary(
        """
        <policies><inbound>
          <llm-token-limit counter-key="@(context.Request.IpAddress)"
            tokens-per-minute="5000" />
        </inbound></policies>
        """,
        f"{record['source']['id']}/operations/invoke",
        "operation",
    )
    record["operationPolicies"] = [operation_policy]
    record["operations"][0]["policy"] = operation_policy

    asset = _import._inventory_asset(
        record,
        {},
        _destination(),
        {},
        "fail",
        [],
    )

    assert asset["assessment"]["status"] == "ready"
    assert "cannot preserve its scope" in str(asset["assessment"]["warnings"])
    assert asset["configuration"]["destinationPolicies"] == []
    assert asset["configuration"]["operations"][0]["policy"] == operation_policy


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

    def optional_list(_cmd, url, _errors, _context):
        values = {
            f"{SOURCE_ID}/backends": [backend],
            f"{SOURCE_ID}/apis": [root_api],
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
            f"{root_api['id']}/products": [],
            f"{SOURCE_ID}/workspaces": [
                {"id": workspace_id, "name": "team"}
            ],
            f"{workspace_id}/backends": [],
            f"{workspace_id}/apis": [workspace_api],
            f"{workspace_api['id']}/operations": [],
            f"{workspace_api['id']}/products": [],
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
        "sku": {"name": "Developer"},
        "properties": {
            "gatewayUrl": "https://source.azure-api.net?sig=secret"
        },
    }
    with (
        patch.object(
            _import,
            "_request",
            return_value=FakeResponse(source_resource),
        ),
        patch.object(_import, "_optional_list", side_effect=optional_list),
        patch.object(_import, "_optional_policy", side_effect=optional_policy),
    ):
        result = _import._discover_source(None, SOURCE_ID)

    assert result["source"]["gatewayUrl"] == (
        "https://source.azure-api.net?sig=%3Credacted%3E"
    )
    assert len(result["assets"]) == 2
    assert result["assets"][0]["backends"] == [backend]
    assert result["assets"][0]["operations"][0]["method"] == "POST"
    assert result["assets"][1]["source"]["workspace"] == "team"
    assert [
        policy["scope"]
        for policy in result["assets"][1]["inheritedPolicies"]
    ] == [workspace_id, SOURCE_ID]


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            _record(
                api_type="mcp",
                service_url="https://tools.example.test/mcp",
            ),
            ("tool", "mcp"),
        ),
        (
            _record(
                name="assistant-agent",
                service_url=(
                    "https://project.services.ai.azure.com/"
                    "api/projects/demo/agents/assistant"
                ),
            ),
            ("agent", "agent"),
        ),
        (
            _record(
                service_url=(
                    "https://account.openai.azure.com/openai/"
                    "deployments/gpt-4o"
                ),
            ),
            ("model", "model"),
        ),
        (
            _record(service_url="https://orders.example.test"),
            ("tool", "openApi"),
        ),
        (
            _record(api_type="soap"),
            ("tool", "unsupported"),
        ),
    ],
)
def test_classify_apim_apis(record, expected):
    assert _import._classify(
        record,
        _import._effective_url(record, {}),
    ) == expected


def test_classify_llm_policy_with_custom_backend_as_model():
    record = _record(
        service_url=None,
        backend={
            "name": "meta-ai",
            "properties": {"url": "https://api.meta.ai"},
        },
    )
    record["policy"] = _import._policy_summary(
        """
        <policies>
          <inbound>
            <llm-token-limit tokens-per-minute="1000" />
          </inbound>
        </policies>
        """,
        record["api"]["id"],
    )

    assert _import._classify(
        record,
        _import._effective_url(record, {}),
    ) == ("model", "model")


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

    summary = _import._backend_summary(backend)

    assert summary["credentials"] == {
        "hasCredentials": True,
        "headerNames": ["api-key"],
        "queryParameterNames": ["code"],
        "authorizationScheme": "Basic",
    }
    assert "super-secret" not in str(summary)
    assert "another-secret" not in str(summary)
    assert "encoded-secret" not in str(summary)


def test_safe_url_redacts_user_info_and_query_values():
    safe = _import._safe_url(
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

    summary = _import._api_summary(api, "team")

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


def test_model_inventory_maps_foundry_provider_and_deployment():
    account_id = (
        "/subscriptions/source-sub/resourceGroups/models-rg/providers/"
        "Microsoft.CognitiveServices/accounts/openai"
    )
    backend = {
        "id": f"{SOURCE_ID}/backends/openai",
        "name": "openai",
        "properties": {
            "url": (
                "https://openai.openai.azure.com/openai/"
                "deployments/gpt-4o"
            ),
            "resourceId": account_id,
        },
    }
    record = _record(
        name="chat",
        service_url=None,
        backend=backend,
        operations=[
            {
                "name": "chat",
                "displayName": "Chat",
                "method": "POST",
                "urlTemplate": "/chat/completions",
            }
        ],
    )
    record["policy"] = _import._policy_summary(
        """
        <policies><inbound><set-backend-service
        backend-id="openai" /></inbound></policies>
        """,
        record["source"]["id"],
    )
    destination = _destination()
    destination["providers"] = [
        {
            "name": "foundry",
            "properties": {
                "kind": "Foundry",
                "foundry": {"resourceIds": [account_id]},
            },
        }
    ]

    asset = _import._inventory_asset(
        record,
        {"gatewayUrl": "https://source.azure-api.net"},
        destination,
        {},
        "fail",
        [],
    )

    assert asset["assetType"] == "model"
    assert asset["destination"] == {
        "name": "chat",
        "providerName": "foundry",
        "resourceType": "model",
    }
    assert asset["configuration"]["deployment"] == {
        "resourceId": f"{account_id}/deployments/gpt-4o",
        "modelName": "gpt-4o",
        "modelVersion": None,
    }
    assert asset["assessment"]["status"] == "ready"


def test_agent_inventory_is_blocked_by_destination_contract():
    record = _record(
        name="assistant-agent",
        service_url=(
            "https://project.services.ai.azure.com/"
            "api/projects/demo/agents/assistant"
        ),
    )

    asset = _import._inventory_asset(
        record,
        {},
        _destination(),
        {},
        "fail",
        [],
    )

    assert asset["assetType"] == "agent"
    assert asset["assessment"]["status"] == "blocked"
    assert "does not define an agent resource" in str(
        asset["assessment"]["reasons"]
    )


@pytest.mark.parametrize(
    ("conflict_policy", "expected_status", "can_import"),
    [
        ("fail", "blocked", False),
        ("skip", "skipped", False),
        ("overwrite", "ready", True),
    ],
)
def test_tool_conflict_policy_changes_assessment(
    conflict_policy,
    expected_status,
    can_import,
):
    destination = _destination()
    destination["toolNames"].add("asset")

    asset = _import._inventory_asset(
        _record(),
        {},
        destination,
        {},
        conflict_policy,
        [],
    )

    assert asset["assessment"]["status"] == expected_status
    assert asset["assessment"]["canImport"] is can_import


def test_mapping_file_rejects_unknown_sections():
    with pytest.raises(InvalidArgumentValueError, match="unsupported sections"):
        _import._read_mapping(io.StringIO('{"unknown": {}}'))


def test_import_table_formats_assets_and_discovery_errors():
    result = {
        "assets": [
            {
                "assetType": "model",
                "source": {
                    "name": "chat",
                    "workspace": None,
                    "properties": {
                        "apiRevision": "7",
                        "protocols": ["https"],
                    },
                },
                "destination": {
                    "name": "chat",
                    "providerName": "foundry",
                },
                "assessment": {
                    "status": "ready",
                    "reasons": [],
                    "warnings": ["Policy translation is required."],
                },
            },
            {
                "assetType": "agent",
                "source": {
                    "name": "support",
                    "workspace": "team",
                },
                "destination": {
                    "name": "support",
                },
                "assessment": {
                    "status": "blocked",
                    "reasons": ["Agents are not supported."],
                    "warnings": [],
                },
            },
        ],
        "discoveryErrors": [
            {
                "scope": f"{SOURCE_ID}/workspaces/private/apis",
                "message": "Access denied.",
            }
        ],
    }

    assert _import.format_import_table(result) == [
        {
            "Type": "model",
            "Source": "chat",
            "Workspace": "(service)",
            "Destination": "foundry/chat",
            "Status": "ready",
        },
        {
            "Type": "agent",
            "Source": "support",
            "Workspace": "team",
            "Destination": "support",
            "Status": "blocked",
        },
        {
            "Type": "discovery",
            "Source": f"{SOURCE_ID}/workspaces/private/apis",
            "Workspace": "",
            "Destination": "",
            "Status": "error",
        },
    ]


def test_dry_run_returns_filtered_inventory_and_summary():
    records = [
        _record(name="tool"),
        _record(
            name="agent",
            service_url=(
                "https://project.services.ai.azure.com/"
                "api/projects/demo/agents/assistant"
            ),
        ),
    ]
    discovered = {
        "source": {
            "id": SOURCE_ID,
            "name": "source",
            "location": "eastus",
            "sku": "Developer",
            "gatewayUrl": "https://source.azure-api.net",
        },
        "assets": records,
        "errors": [],
    }
    cmd = SimpleNamespace(
        cli_ctx=SimpleNamespace(
            data={"subscription_id": "destination-sub"},
        )
    )

    with (
        patch.object(_import, "_discover_source", return_value=discovered),
        patch.object(
            _import,
            "_destination_inventory",
            return_value=_destination(),
        ),
        patch.object(
            _import,
            "get_subscription_id",
            return_value="destination-sub",
        ),
        patch.object(_import.logger, "warning") as warning,
    ):
        result = _import.import_from_apim(
            cmd,
            "destination",
            "destination-rg",
            SOURCE_ID,
            include=["tools"],
            dry_run=True,
        )

    assert result["dryRun"] is True
    assert result["summary"] == {
        "discovered": 2,
        "included": 1,
        "ready": 1,
        "blocked": 0,
        "skipped": 0,
        "byType": {"models": 0, "agents": 0, "tools": 1},
        "discoveryComplete": True,
        "discoveryErrorCount": 0,
    }
    assert [asset["source"]["name"] for asset in result["assets"]] == ["tool"]
    assert warning.call_args_list == [
        call("Discovering assets in source APIM '%s'...", "source"),
        call("Checking destination AI Gateway '%s'...", "destination"),
        call(
            "Assessing import compatibility for %d discovered assets...",
            2,
        ),
        call("Dry-run assessment complete."),
    ]
