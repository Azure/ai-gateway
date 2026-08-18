# AI Gateway Azure CLI extension

This package provides the `ai-gateway` extension for the Azure CLI. The current
scaffold includes a smoke-test command and the contract for importing existing
Azure API Management configuration. Resource operations will be wired to the
service API after its OpenAPI description is available.

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
