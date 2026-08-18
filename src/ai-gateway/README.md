# AI Gateway Azure CLI extension

This package provides the `ai-gateway` extension for the Azure CLI.

Implemented gateway commands:

```bash
az ai-gateway create --name <name> --resource-group <group> --location <region>
az ai-gateway list [--resource-group <group>]
az ai-gateway show --name <name> --resource-group <group>
az ai-gateway update --name <name> --resource-group <group> [options]
az ai-gateway delete --name <name> --resource-group <group>
```

Model commands are nested beneath a gateway and model provider:

```bash
az ai-gateway model create --gateway-name <gateway> --resource-group <group> \
  --provider-name <provider> --name <model> [options]
az ai-gateway model list --gateway-name <gateway> --resource-group <group> \
  [--provider-name <provider>]
az ai-gateway model show|update|delete --gateway-name <gateway> \
  --resource-group <group> --provider-name <provider> --name <model>
```

MCP tool servers use JSON endpoint definitions so every endpoint and
authentication kind in the control-plane contract remains available:

```bash
az ai-gateway mcp create --gateway-name <gateway> --resource-group <group> \
  --name <server> --endpoints @endpoints.json
az ai-gateway mcp list --gateway-name <gateway> --resource-group <group>
az ai-gateway mcp show|update|delete --gateway-name <gateway> \
  --resource-group <group> --name <server>
az ai-gateway mcp authorize --gateway-name <gateway> --resource-group <group> \
  --name <server> --endpoint-id <endpoint>
```

`mcp update` reads secret fragments only to preserve omitted values during an
endpoint replacement. It never emits those secret fragments.

Example `endpoints.json` for a remote MCP server:

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
      "type": "none"
    }
  }
]
```

API keys and gateway managed identities have dedicated command groups:

```bash
az ai-gateway api-key create|list|show|delete|list-secrets|regenerate ...
az ai-gateway identity show|assign|remove ...
```

`api-key list` and `show` return metadata only. `list-secrets` is the explicit
secret-output operation. Identity assignment and removal preserve identities
that were not selected by the command.

Policies are inline objects hosted by models or MCP tool servers. `policy list`
returns synthesized IDs used by `show`, `update`, and `delete`:

```bash
az ai-gateway policy create --gateway-name <gateway> --resource-group <group> \
  --scope-type model --scope-name <model> --provider-name <provider> \
  --policy @policy.json
az ai-gateway policy list --gateway-name <gateway> --resource-group <group>
az ai-gateway policy show|delete --gateway-name <gateway> \
  --resource-group <group> --policy-id <policy-id>
az ai-gateway policy update --gateway-name <gateway> --resource-group <group> \
  --policy-id <policy-id> --policy @policy.json
```

Policy updates replace the complete inline object. MCP policy mutations preserve
endpoint secrets internally and never include them in command output.
Policy IDs contain `#`; quote them when passing a literal ID to a shell.

## Assess an import from API Management

Use `--dry-run` to discover service-level and workspace APIs in a classic API
Management service. The result classifies model, agent, MCP, and REST tool
assets; inventories operations, backends, and policy statement types; checks
destination conflicts; and reports each asset as `ready`, `blocked`, or
`skipped`. Credential values and URL query values are not included in output.

```bash
az ai-gateway import --name <gateway> --resource-group <group> \
  --source-apim-id /subscriptions/<sub>/resourceGroups/<group>/providers/Microsoft.ApiManagement/service/<apim> \
  --dry-run --output table
```

Use `--include models tools` to limit the inventory and `--conflict-policy
fail|skip|overwrite` to preview conflict handling. Import writes are not
implemented yet, so omitting `--dry-run` fails explicitly. Use `--output json`
for the complete nested configuration and `--output table` for a compact
compatibility summary. Both formats retain the complete source API property bag;
the table serializes it in the `Properties` column. Related operation and
backend property bags are included in JSON. Credential values, embedded URL
credentials, and URL query values are redacted.

Supported APIM AI policies are projected in each asset's
`configuration.destinationPolicies`:

- `llm-token-limit` and `azure-openai-token-limit` rate limits become
  `tokenLimit` policies with a `minute` period. Hourly and daily quotas map to
  `hour` and `day`. Longer quota periods, arbitrary expressions, estimation,
  and response headers or variables produce warnings.
- `llm-content-safety` category thresholds become `contentSafety` severities.
  Backend selection, prompt shielding, completion enforcement, windows, and
  blocklists produce warnings because the inline contract has no equivalent.

Conditional policies and operation- or product-scoped policies are inventoried
but not promoted to asset scope. Unsupported policy statements are also
retained in the inventory and reported as omitted instead of being silently
dropped.

Query the executable compatibility registry directly:

```bash
az ai-gateway policy import-support list --output table
az ai-gateway policy import-support show --name llm-content-safety
```

See [APIM policy translation](docs/apim-policy-translation.md) for the complete
mapping contract, warning behavior, scope rules, and required workflow for
adding future policy capabilities.

Optional mappings can supply destination names and model metadata that cannot
be derived from APIM:

```json
{
  "models": {
    "source-api-name": {
      "name": "destination-model",
      "providerName": "foundry",
      "deploymentResourceId": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account/deployments/deployment",
      "modelName": "gpt-4o",
      "modelVersion": "2024-11-20"
    }
  },
  "tools": {
    "source-tool-api": {
      "name": "destination-tool",
      "namespace": "orders"
    }
  }
}
```

## Install from a local build

Build from the repository root:

```bash
python -m pip install build
python -m build --wheel --outdir dist src/ai-gateway
az extension add --source dist/ai_gateway-1.0.0b1-py3-none-any.whl
az ai-gateway version
```

## Install from a GitHub release

```bash
az extension add \
  --source https://github.com/Azure/ai-gateway/releases/download/azure-cli-v1.0.0b1/ai_gateway-1.0.0b1-py3-none-any.whl
```

GitHub release installation uses a pinned version. Publishing the extension to an
Azure CLI extension index later will enable installation and updates by name.
