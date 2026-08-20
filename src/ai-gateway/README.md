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

Manage AI Gateway resources.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway create -n <gateway> -g <group> -l <region> [options]` |
| `delete` | `az ai-gateway delete -n <gateway> -g <group>` |
| `import` | `az ai-gateway import -n <gateway> -g <group> --source-apim-id <id> --dry-run [options]` |
| `list` | `az ai-gateway list [-g <group>]` |
| `show` | `az ai-gateway show -n <gateway> -g <group>` |
| `update` | `az ai-gateway update -n <gateway> -g <group> [options]` |
| `version` | `az ai-gateway version` |


### Networking

Enable outbound VNet integration with a delegated subnet:

```bash
az ai-gateway update \
  --virtual-network-type External \
  --subnet-resource-id /subscriptions/<sub>/resourceGroups/<network-group>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet> \
  -n my-ai-gateway -g my-resource-group
```

A non-empty `--subnet-resource-id` without `--virtual-network-type` enables
`External` integration. `External` requires a full
`Microsoft.Network/virtualNetworks/subnets` resource ID. An explicitly empty
`--subnet-resource-id` disables VNet integration and clears the configuration.

Disable integration and clear `virtualNetworkConfiguration` with:

```bash
az ai-gateway update \
  --virtual-network-type None \
  -n my-ai-gateway -g my-resource-group
```

`None` cannot be combined with a non-empty `--subnet-resource-id`.
For compatibility, an explicitly empty `--subnet-resource-id ""` without
`--virtual-network-type` also disables VNet integration and clears the
configuration.

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
| `--mapping-file` | JSON source-to-destination mappings |
| `--output` | `json` for full details; `table` for a summary |

Import execution is not available. `--dry-run` is required. Sensitive policy,
credential, and URL values are redacted.

## `az ai-gateway model-provider`

Manage Foundry and custom model provider registrations.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway model-provider create -n <provider> --kind <Foundry-or-Custom> [--no-sync] [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway model-provider delete -n <provider> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway model-provider list --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway model-provider show -n <provider> --resource-name <gateway> -g <group>` |
| `sync` | `az ai-gateway model-provider sync -n <provider> [--api-key-value <key>] [--dry-run] [--delete-missing --yes] --resource-name <gateway> -g <group>` |
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
| `--managed-identity-resource` | Token audience used by Foundry managed identity authentication. |
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
  --managed-identity-resource https://cognitiveservices.azure.com \
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
| `--delete-missing` | Delete stale model registrations. Requires `--yes`. |
| `--yes`, `-y` | Confirm deletion of stale model registrations. |

Synchronize a Foundry provider:

```bash
az ai-gateway model-provider sync \
  --name foundry \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Synchronize a custom provider:

```bash
az ai-gateway model-provider sync \
  --name custom-openai \
  --api-key-value "$PROVIDER_API_KEY" \
  --resource-name my-ai-gateway \
  --resource-group my-resource-group
```

Add `--dry-run --output table` to preview changes. To also delete stale
registrations, add `--delete-missing --yes`.

## `az ai-gateway model`

Manage model registrations and their backing deployments.

| Command | Syntax |
| --- | --- |
| `create` | `az ai-gateway model create --provider-name <provider> -n <model> [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway model delete --provider-name <provider> -n <model> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway model list [--provider-name <provider>] --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway model show --provider-name <provider> -n <model> --resource-name <gateway> -g <group>` |
| `update` | `az ai-gateway model update --provider-name <provider> -n <model> [options] --resource-name <gateway> -g <group>` |

## `az ai-gateway mcp`

Manage MCP tool servers, endpoints, and OAuth authorization.

| Command | Syntax |
| --- | --- |
| `authorize` | `az ai-gateway mcp authorize -n <server> --endpoint-id <endpoint> --resource-name <gateway> -g <group>` |
| `create` | `az ai-gateway mcp create -n <server> --endpoints @endpoints.json [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway mcp delete -n <server> --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway mcp list --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway mcp show -n <server> --resource-name <gateway> -g <group>` |
| `update` | `az ai-gateway mcp update -n <server> [options] --resource-name <gateway> -g <group>` |

`--endpoints` accepts a JSON array or an `@file` path. Endpoint kinds: `mcp`,
`openApi`, and `http`.

### `az ai-gateway mcp create`

Create or replace an MCP tool server that federates one or more tool endpoints.

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
| `list` | `az ai-gateway policy list [--scope-type <model-or-mcp>] --resource-name <gateway> -g <group>` |
| `show` | `az ai-gateway policy show --policy-id '<id>' --resource-name <gateway> -g <group>` |
| `update` | `az ai-gateway policy update --policy-id '<id>' --policy @policy.json --resource-name <gateway> -g <group>` |

Policy IDs contain `#`; quote literal IDs.

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
