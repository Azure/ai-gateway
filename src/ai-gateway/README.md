# AI Gateway Azure CLI extension

## Install

```bash
# GitHub release
az extension add \
  --source https://github.com/Azure/ai-gateway/releases/download/azure-cli-v1.0.0b1/ai_gateway-1.0.0b1-py3-none-any.whl

# Local build
python -m pip install build
python -m build --wheel --outdir dist src/ai-gateway
az extension add --source dist/ai_gateway-1.0.0b1-py3-none-any.whl --upgrade --yes

# Or
make install-extension
```

## Configure defaults

Configure a default resource group and AI Gateway name to omit those arguments
from subsequent commands:

```bash
az configure --defaults group=my-resource-group ai-gateway=my-ai-gateway
```

The `ai-gateway` default supplies `--name` for top-level gateway commands and
`--resource-name` for nested commands. An explicitly supplied argument overrides
the configured default.

## `az ai-gateway`

Manage and use the AI Gateway SKU in Azure API Management.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway create -n <gateway> -g <group> -l <region> [options]` or `az ai-gateway create --list-regions` |
| `delete` | `az ai-gateway delete -n <gateway> -g <group>` |
| `import` | `az ai-gateway import -n <gateway> -g <group> --source-apim-id <id> --dry-run [options]` |
| `list` | `az ai-gateway list [-g <group>]` |
| `show` | `az ai-gateway show -n <gateway> -g <group> [--system-assigned] [--user-assigned]` |
| `update` | `az ai-gateway update -n <gateway> -g <group> [options]` |
| `version` | `az ai-gateway version` |

List the production regions supported by the AI Gateway SKU:

```bash
az ai-gateway create --list-regions --output table
```

Use `--system-assigned` or `--user-assigned` with `show` to return only the
selected managed identity details. Pass both options to return both identity
types. Without either option, `show` returns the complete gateway resource.


### Networking

Enable outbound VNet integration with a delegated subnet:

```bash
az ai-gateway update \
  --virtual-network-type External \
  --subnet-resource-id /subscriptions/<sub>/resourceGroups/<network-group>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet> \
  -n my-ai-gateway -g my-resource-group
```

Disable integration and clear `virtualNetworkConfiguration` with:

```bash
az ai-gateway update \
  --virtual-network-type None \
  -n my-ai-gateway -g my-resource-group
```

Disable public ingress:

```bash
az ai-gateway update \
  --public-network-access Disabled \
  -n my-ai-gateway -g my-resource-group
```

`--public-network-access` accepts `Enabled` or `Disabled`.

## `az ai-gateway private-endpoint`

Manage the service-side connections created when private endpoints target an
AI Gateway.

| Command | Syntax |
| --- | --- |
| `approve` | `az ai-gateway private-endpoint approve -n <connection> [--description <text>] [--no-wait] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway private-endpoint delete -n <connection> [--no-wait] --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway private-endpoint list --resource-name <gateway> -g <group>` |
| `reject` | `az ai-gateway private-endpoint reject -n <connection> [--description <text>] [--no-wait] --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway private-endpoint show -n <connection> --resource-name <gateway> -g <group>` |

`approve` and `reject` use `--description` for the connection-state reason and
wait for completion unless `--no-wait` is specified. If omitted, `approve` uses
`Approved` and `reject` uses `Rejected`. `delete` prompts for confirmation and
also supports `--no-wait`.

Create the backing private endpoint with the standard networking commands:

```bash
GATEWAY_ID=$(az ai-gateway show -n my-ai-gateway -g my-resource-group \
  --query id -o tsv)

az network private-endpoint create \
  -n my-ai-gateway-pe -g my-network-resource-group \
  --vnet-name my-vnet --subnet private-endpoints \
  --private-connection-resource-id "$GATEWAY_ID" \
  --group-id Gateway --connection-name my-ai-gateway-connection

PRIVATE_DNS_ZONE_ID=$(az network private-dns zone show \
  -n privatelink.azure-api.net -g my-network-resource-group \
  --query id -o tsv)

az network private-endpoint dns-zone-group create \
  --endpoint-name my-ai-gateway-pe -g my-network-resource-group \
  -n default --zone-name ai-gateway \
  --private-dns-zone "$PRIVATE_DNS_ZONE_ID"
```

Approve the resulting connection if it remains pending:

```bash
az ai-gateway private-endpoint approve \
  -n <connection-name> --resource-name my-ai-gateway \
  -g my-resource-group
```

Verify private DNS and traffic before disabling public network access. Deleting
a service-side connection does not delete its backing
`Microsoft.Network/privateEndpoints` resource.

### `az ai-gateway import`

Discover and import assess models, agents, tools, and policies from an APIM resource.

#### Options

| Option | Values |
| --- | --- |
| `--include` | `models`, `agents`, `tools` |
| `--conflict-policy` | `fail`, `skip`, `overwrite` |
| `--mapping-file` | JSON network and source-to-destination asset mappings |
| `--output` | Explicit structured output; `table` returns only the compact plan |

Import execution is not available. `--dry-run` is required. Sensitive policy,
credential, and URL values are redacted.

Without explicit output or a query, dry-run prints a compact ordered plan,
followed by grouped issues, warnings, and a readiness summary.

Custom-provider model discovery reuses provider sync for OpenAI-compatible and
Anthropic APIs. API-specific APIM backend credentials, including named values,
are used for discovery without exposing their values. If discovery fails, the
provider-only import remains ready. Successfully discovered models are grouped
by API protocol in a dedicated report section rather than shown as warnings.
Native Gemini APIs are not supported.

REST-backed MCP servers omit their referenced backing APIs from the separate
OpenAPI plan. When required, import retrieves an active scoped APIM subscription
key and configures it as redacted MCP header authentication.

## `az ai-gateway model-provider`

Manage Foundry and custom model provider registrations.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway model-provider create [-n <provider> --kind <Foundry-or-Custom>] [--no-sync] [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway model-provider delete -n <provider> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway model-provider list --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway model-provider show -n <provider> --resource-name <gateway> -g <group>` |
| `sync` | `az ai-gateway model-provider sync -n <provider> [--api-key-value <key>] [--dry-run] [--yes] --resource-name <gateway> -g <group>` |
| `update` | `az ai-gateway model-provider update -n <provider> [options] --resource-name <gateway> -g <group>` |

### `az ai-gateway model-provider create`

Create a Foundry or custom provider and import its available models.

#### Options

| Option | Description |
| --- | --- |
| `--kind` | Provider kind: `Foundry` or `Custom`. |
| `--endpoint` | Provider base endpoint. Required for custom providers; optional for Foundry providers. |
| `--resource-ids` | One or more space-separated Foundry account resource IDs. Required for Foundry providers. |
| `--auth-kind` | `ManagedIdentity` or `ApiKey`. Defaults to managed identity for Foundry and API key for custom providers. |
| `--api-key-header-name` | Header used by API-key authentication. |
| `--api-key-value` | Exact value sent in the API-key header. Add an authentication scheme only when required by the provider. |
| `--managed-identity-resource` | Token audience used by Foundry managed identity authentication. Defaults to `https://cognitiveservices.azure.com`. |
| `--managed-identity-client-id` | Optional user-assigned managed identity client ID. |
| `--no-sync` | Skip model discovery and import after provider creation. |

Create a Foundry provider and import its deployments:

```bash
az ai-gateway model-provider create \
  --name foundry \
  --kind Foundry \
  --resource-ids \
    /subscriptions/<sub>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account-1> \
    /subscriptions/<sub>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account-2> \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Create a custom provider and import its models. It supports OpenAI-compatible APIs
and Anthropic Messages API:

```bash
az ai-gateway model-provider create \
  --name custom-openai \
  --kind Custom \
  --endpoint https://models.example.com \
  --api-key-header-name Authorization \
  --api-key-value "$PROVIDER_API_KEY" \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Create multiple model providers from Foundry accounts:

```bash
az cognitiveservices account list | az ai-gateway model-provider create \
      --resource-name my-ai-gateway \
      --resource-group my-gateway-resource-group
```

By default, the command attempts to get models from the endpoint itself. Add `--no-sync` to either command to create only the provider. You can add models later with `az ai-gateway model create`.

The API-key value is sent exactly as entered. If your provider uses Bearer scheme,
enter "Bearer <key>".

### `az ai-gateway model-provider sync`

Discover models available from an existing provider and reconcile its model
registrations.

#### Options

| Option | Description |
| --- | --- |
| `--api-key-value` | Exact header value used to query a custom provider. When omitted interactively, a masked prompt is shown. |
| `--dry-run` | Return the synchronization plan without changing models. |
| `--yes`, `-y` | Confirm model creation and deletion. Required unless `--dry-run` is used. |

Synchronize a Foundry provider:

```bash
az ai-gateway model-provider sync \
  --name foundry \
  --yes \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Synchronize a custom provider:

```bash
az ai-gateway model-provider sync \
  --name custom-openai \
  --api-key-value "$PROVIDER_API_KEY" \
  --yes \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Add `--dry-run --output table` to preview all model creations and deletions.
If any discovered model name already belongs to another provider, synchronization
fails before creating or deleting any models.

## `az ai-gateway model`

Manage model registrations and their backing deployments.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway model create --provider-name <provider> -n <model> [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway model delete --provider-name <provider> -n <model> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway model list [--model-provider <provider>] [--type <Foundry-or-Custom>] --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway model show --provider-name <provider> -n <model> --resource-name <gateway> -g <group>` |

## `az ai-gateway mcp`

Manage MCP tool servers, endpoints, and OAuth authorization.

| Command | Syntax |
| --- | --- |
| `authorize` | `az ai-gateway mcp authorize -n <server> --endpoint-id <endpoint> --resource-name <gateway> -g <group>` |
| `create` | `az ai-gateway mcp create -n <server> --endpoints @endpoints.json [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway mcp delete -n <server> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway mcp list --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway mcp show -n <server> --resource-name <gateway> -g <group>` |
| `test` | `az ai-gateway mcp test -n <server> --api-key-name <key> --resource-name <gateway> -g <group>` |
| `update` | `az ai-gateway mcp update -n <server> [options] --resource-name <gateway> -g <group>` |

`--endpoints` accepts a JSON array or an `@file` path. Endpoint kinds: `mcp`,
`openApi`, and `http`. Table output from `mcp list` includes each server's
derived runtime endpoint.

### `az ai-gateway mcp create`

Create an MCP tool server that federates one or more tool endpoints. The command
fails if a server with the same name already exists; use `mcp update` to change
an existing server.

#### Options

| Option | Description |
| --- | --- |
| `--name`, `-n` | Required. MCP tool server name. |
| `--endpoints` | Required. Non-empty endpoint JSON array or `@file`. Use a file when the definition contains secrets. |
| `--display-name` | Display name of the MCP tool server. |
| `--description` | Description of the MCP tool server. |
| `--failure-mode` | Endpoint failure behavior: `failOpen` or `failClosed`. |
| `--policies` | Optional inline policy JSON array or `@file`. |

#### Endpoint schema

| Field | Required | Description |
| --- | --- | --- |
| `namespace` | Yes | Namespace exposed by the tool server. |
| `kind` | Yes | Endpoint kind: `mcp`, `openApi`, or `http`. |
| `required` | No | Whether the endpoint is required by the tool server. |
| `mcp.url` | For `mcp` | MCP server URL. |
| `mcp.transport` | No | `streamableHttp` (the default) or `sse`. |
| `openApi.specSource.type` | For `openApi` | OpenAPI document source: `url` or `inline`. |
| `openApi.specSource.url` | For URL sources | URL of the OpenAPI document. |
| `openApi.specSource.contentBase64` | For inline sources | Base64-encoded OpenAPI document. |
| `credentials.type` | No | Authentication type: `none`, `header`, `oauth2`, or `managedIdentity`. |
| `credentials.headers` | For header authentication | Header names mapped to arrays of string values. |
| `credentials.oauth2.grantType` | For OAuth 2.0 | Must be `authorizationCode`. |
| `credentials.oauth2.authorizationUrl` | For OAuth 2.0 | Authorization endpoint URL. |
| `credentials.oauth2.tokenUrl` | For OAuth 2.0 | Token endpoint URL. |
| `credentials.oauth2.clientId` | For OAuth 2.0 | OAuth client ID. |
| `credentials.oauth2.clientSecret` | No | OAuth client secret. |
| `credentials.oauth2.scopes` | No | OAuth scopes as an array of strings. |
| `credentials.managedIdentity.resource` | No | Token audience for managed identity authentication. |
| `credentials.managedIdentity.clientId` | No | Client ID of an assigned user-assigned identity. |

Create `endpoints.json` for an MCP endpoint authenticated with a header and an
OpenAPI endpoint without authentication:

```json
[
  {
    "namespace": "tickets",
    "kind": "mcp",
    "required": true,
    "mcp": {
      "url": "https://tools.example.com/mcp",
      "transport": "streamableHttp"
    },
    "credentials": {
      "type": "header",
      "headers": {
        "Authorization": ["Bearer <token>"]
      }
    }
  },
  {
    "namespace": "catalog",
    "kind": "openApi",
    "openApi": {
      "specSource": {
        "type": "url",
        "url": "https://api.example.com/openapi.json"
      }
    },
    "credentials": {
      "type": "none"
    }
  }
]
```

Create the tool server from the endpoint definition:

```bash
az ai-gateway mcp create \
  --name team-tools \
  --display-name "Team tools" \
  --description "Engineering tool federation" \
  --failure-mode failClosed \
  --endpoints @endpoints.json \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

For an OAuth endpoint, use the following credentials in its endpoint
definition:

```json
{
  "type": "oauth2",
  "oauth2": {
    "grantType": "authorizationCode",
    "authorizationUrl": "https://login.example.com/oauth2/authorize",
    "tokenUrl": "https://login.example.com/oauth2/token",
    "clientId": "<client-id>",
    "clientSecret": "<client-secret>",
    "scopes": ["tools.read"]
  }
}
```

After creation, get the server-generated endpoint ID with `mcp show`, then run
`az ai-gateway mcp authorize` to obtain the OAuth login link.

### `az ai-gateway mcp test`

Test a registered MCP tool server by sending an MCP `initialize` request to its
runtime endpoint, and attempting to list resources/tools.

```bash
az ai-gateway mcp test \
  --name tools \
  --api-key-name production \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

## `az ai-gateway api-key`

Manage gateway API keys and secret rotation.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway api-key create -n <key> [--display-name <name>] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway api-key delete -n <key> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway api-key list --resource-name <gateway> -g <group>` |
| `list-secrets` | `az ai-gateway api-key list-secrets -n <key> --resource-name <gateway> -g <group>` |
| `regenerate` | `az ai-gateway api-key regenerate -n <key> --key-type primary --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway api-key show -n <key> --resource-name <gateway> -g <group>` |

`list` and `show` return metadata. `list-secrets` returns key values.

## `az ai-gateway identity`

Manage system- and user-assigned managed identities.

| Command | Syntax |
| --- | --- |
| `assign` | `az ai-gateway identity assign [--system-assigned] [--user-assigned <id> ...] --resource-name <gateway> -g <group>` |
| `remove` | `az ai-gateway identity remove [--system-assigned] [--user-assigned <id> ...] --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway identity show --resource-name <gateway> -g <group>` |

## `az ai-gateway policy`

Manage policies on gateway assets.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway policy create --scope-type <model-or-mcp> --scope-name <resource> --policy @policy.json [--provider-name <provider>] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway policy delete --policy-id '<id>' --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway policy list [--scope-type <model-or-mcp> --scope-name <resource> [--provider-name <provider>]] --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway policy show --policy-id '<id>' --resource-name <gateway> -g <group>` |
| `update` | `az ai-gateway policy update --policy-id '<id>' --policy @policy.json --resource-name <gateway> -g <group>` |

Policy IDs contain `#`; quote literal IDs.

### `az ai-gateway policy create`

Add an new policy to an asset.

#### Options

| Option | Description |
| --- | --- |
| `--scope-type` | Required. Type of the scope at which the policy will be applied: `model` or `mcp`. |
| `--scope-name` | Required. Name of the asset at which the policy is attached. |
| `--policy` | Required. Policy JSON object or `@file`. The object must contain `type`. |
| `--provider-name` | Model provider name. Required when `--scope-type` is `model`. |

#### Policy schema

The CLI requires a JSON object with `type`. The schemas below cover
`tokenLimit`, `costLimit`, `requestRateLimit`, `contentSafety`, and `ipFilter`;
other policy types and fields are passed through unchanged.

| Field | Policy type | Description |
| --- | --- | --- |
| `type` | All | Required. Policy type: `tokenLimit`, `costLimit`, `requestRateLimit`, `contentSafety`, or `ipFilter`. |
| `period` | `tokenLimit` | Limit period: `minute`, `hour`, or `day`. |
| `count` | `tokenLimit` | Positive integer token limit for the period. |
| `displayName` | `costLimit` | Optional display name for the cost limit. |
| `amount` | `costLimit` | Cost limit amount for the period. |
| `period` | `costLimit` | Limit period: `hour`, `day`, `week`, `month`, or `year`. |
| `remainingCostHeaderName` | `costLimit` | Optional response header name for the remaining cost allowance. |
| `callsPerPeriod` | `requestRateLimit` | Positive integer request limit for the period. |
| `periodSeconds` | `requestRateLimit` | Positive integer duration of the request-limit period, in seconds. |
| `counterKey` | `tokenLimit`, `costLimit`, `requestRateLimit` | Counter scope: `IPAddress` or `Identity`. |
| `hateSeverity` | `contentSafety` | Hate-content threshold: `Low`, `Medium`, `High`, or `None`. |
| `selfHarmSeverity` | `contentSafety` | Self-harm-content threshold: `Low`, `Medium`, `High`, or `None`. |
| `sexualSeverity` | `contentSafety` | Sexual-content threshold: `Low`, `Medium`, `High`, or `None`. |
| `violenceSeverity` | `contentSafety` | Violence-content threshold: `Low`, `Medium`, `High`, or `None`. |
| `action` | `ipFilter` | Filter behavior: `Allow` or `Deny`. |
| `cidrRanges` | `ipFilter` | Array of IPv4 CIDR ranges, such as `["10.0.0.0/8"]`. Bare IP addresses are not accepted. |


Create `policy.json` with a token-limit policy:

```json
{
  "type": "tokenLimit",
  "period": "minute",
  "count": 5000,
  "counterKey": "IPAddress"
}
```

Add the policy to a model:

```bash
az ai-gateway policy create \
  --scope-type model \
  --scope-name gpt-4o \
  --provider-name foundry \
  --policy @policy.json \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

### `az ai-gateway policy import-support`

Inspect APIM policy import and translation capabilities.

| Command | Syntax |
| --- | --- |
| `list` | `az ai-gateway policy import-support list [--support-level <level>]` |
| `show` | `az ai-gateway policy import-support show -n <apim-policy>` |

Support levels: `partial`, `consumed`, and `unsupported`.

See [APIM policy translation](docs/apim-policy-translation.md).

## `az ai-gateway telemetry-exporter`

Manage gateway telemetry exporters.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway telemetry-exporter create -n <exporter> [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway telemetry-exporter delete -n <exporter> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway telemetry-exporter list --resource-name <gateway> -g <group>` |

### `az ai-gateway telemetry-exporter create`

Create or replace a telemetry exporter backed by an existing Application
Insights resource or custom OpenTelemetry endpoint.

#### Options

| Option | Description |
| --- | --- |
| `--name`, `-n` | Required. Telemetry exporter name. |
| `--application-insights` | Resource ID of an existing Application Insights component. Use this option by itself for the streamlined Application Insights setup. |
| `--metrics-endpoint` | Absolute HTTPS OTLP metrics endpoint. Each endpoint independently enables its signal; at least one is required for a custom destination. |
| `--logs-endpoint` | Absolute HTTPS OTLP logs endpoint. Each endpoint independently enables its signal; at least one is required for a custom destination. |
| `--traces-endpoint` | Absolute HTTPS OTLP traces endpoint. Each endpoint independently enables its signal; at least one is required for a custom destination. |
| `--headers` | Optional custom OTLP headers as a JSON object or `@file`. Cannot be combined with managed identity authentication. |
| `--managed-identity-resource` | HTTPS token audience for custom OTLP managed identity authentication. |
| `--identity-client-id` | Client ID of an assigned user-assigned identity. For custom OTLP, requires `--managed-identity-resource`. |
| `--payload-capture` | Include request and response payloads in exported telemetry. |


Configure Application Insights:

```bash
az ai-gateway telemetry-exporter create \
  --name appinsights \
  --application-insights /subscriptions/<sub>/resourceGroups/<group>/providers/Microsoft.Insights/components/<name> \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Configure a custom OpenTelemetry destination with headers:

```bash
az ai-gateway telemetry-exporter create \
  --name custom-otlp \
  --metrics-endpoint https://otel.example.com/v1/metrics \
  --logs-endpoint https://otel.example.com/v1/logs \
  --traces-endpoint https://otel.example.com/v1/traces \
  --headers '{"x-api-key":"secret"}' \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Configure an unauthenticated traces-only OpenTelemetry destination:

```bash
az ai-gateway telemetry-exporter create \
  --name custom-otlp \
  --traces-endpoint https://otel.example.com/v1/traces \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```
