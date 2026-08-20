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
| `create` | `az ai-gateway telemetry-exporter create [options] --resource-name <gateway> -g <group>` |
| `delete` | `az ai-gateway telemetry-exporter delete [-n <exporter>] [--workspace-name <workspace>] --resource-name <gateway> -g <group>` |
| `list` | `az ai-gateway telemetry-exporter list [--workspace-name <workspace>] --resource-name <gateway> -g <group>` |

### `az ai-gateway telemetry-exporter create`

Create or replace a telemetry exporter backed by an existing Application
Insights resource or custom OpenTelemetry endpoint.

#### Options

| Option | Description |
| --- | --- |
| `--name`, `-n` | Telemetry exporter name. Defaults to `appinsights`. |
| `--workspace-name` | Gateway workspace name. Defaults to `default`. |
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

`list` redacts custom header values. `delete` defaults to the `appinsights`
exporter in the `default` workspace and prompts for confirmation.

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
