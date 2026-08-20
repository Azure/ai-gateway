---
name: manage-ai-gateway
version: 1.0.0
updated: 2026-08-20
description: Create, configure, and operate Azure AI Gateway resources with the Azure CLI extension. Use this for administrators and platform engineers who manage gateways, model providers and models, MCP tool servers, policies, API keys, identities, telemetry, or APIM import assessments.
---

# Manage an Azure AI Gateway

> Invoked as `/ai-gateway:manage-ai-gateway` when installed via the plugin. It is
> also used by `/ai-gateway:create` and `/ai-gateway:manage`.

Use this skill for a gateway administrator or platform engineer who is authorized
to change AI Gateway resources. Use `skills/use-ai-gateway/SKILL.md` instead when
the user only wants to consume models or MCP tools from an existing gateway.

The management workflow is:

1. Confirm the Azure context and install or update the extension if needed.
2. Resolve or create the target gateway.
3. Inspect relevant current state before proposing a change.
4. Plan the smallest set of Azure CLI commands that achieves the request.
5. Confirm consequential changes, execute them, and verify the resulting state.

## Prerequisites and target resolution

The supported interface is the Azure CLI extension documented in
`src/ai-gateway/README.md`. Do not replace its commands with guessed ARM calls.

1. Check `az account show` and `az ai-gateway version`. If Azure CLI is not
   authenticated, ask the user to run `az login`. If the extension is absent,
   install it from the release URL in `src/ai-gateway/README.md`, or use the local
   wheel only when working in this repository and the user wants the local build.
2. Determine the subscription, resource group, and gateway name. Never infer the
   subscription when more than one is available. Use `az account set
   --subscription <subscription>` after confirmation.
3. The user may configure reusable defaults:

   ```bash
   az configure --defaults group=<resource-group> ai-gateway=<gateway>
   ```

   The `ai-gateway` default supplies `--name` for top-level gateway commands and
   `--resource-name` for nested commands. Explicit arguments take precedence.
4. Before changing an existing resource, run the matching `show` or `list`
   command. Distinguish “resource not found” from authorization and transient
   failures; do not silently treat every error as absence.

## Safety and execution rules

- Explain the intended changes before executing them.
- Ask for explicit confirmation immediately before deleting a gateway, provider,
  model, MCP server, policy, or API key; removing an identity; regenerating a key;
  overwriting a conflict; or synchronizing with `--delete-missing`.
- Prefer a dry run when supported. Model-provider synchronization supports
  `--dry-run`; APIM import currently requires `--dry-run` and cannot execute.
- Do not print, persist, or echo API-key values. Use environment variables or the
  CLI's masked interactive prompt. `api-key list` and `show` return metadata;
  `list-secrets` returns live secrets and should run only when the user explicitly
  needs a key value.
- Do not place secret values directly in shell history. For provider API keys and
  telemetry headers, prefer an existing environment variable or a protected
  `@file`. Never commit that file.
- Treat JSON supplied through `--endpoints`, `--policy`, `--mapping-file`, or
  `--headers` as configuration owned by the user. Inspect and validate it before
  use; do not invent provider URLs, credentials, policy semantics, or mappings.
- Use `--yes` only after the user has confirmed the exact destructive change.
- After mutation, verify from the command result and, where supported, run the
  corresponding `show` or `list` command. Summarize resource names and state
  without exposing secrets.

## Create a gateway

Collect the gateway name, resource group, and Azure region. Confirm whether the
resource group already exists; create it only if the user asks. Then run:

```bash
az ai-gateway create \
  --name <gateway> \
  --resource-group <resource-group> \
  --location <region>
```

Pass additional options only when requested and supported by
`az ai-gateway create --help`. Verify with:

```bash
az ai-gateway show --name <gateway> --resource-group <resource-group>
```

Optionally set CLI defaults after creation, but do not change the user's global
Azure CLI configuration without asking.

## Configure gateway assets

Inspect the relevant asset collection first. Choose only the section needed for
the user's request.

### Model providers and models

Use a **Foundry** provider when the user has one or more Microsoft Foundry account
resource IDs. It defaults to managed identity:

```bash
az ai-gateway model-provider create \
  --name <provider> \
  --kind Foundry \
  --resource-ids <foundry-resource-id> [<foundry-resource-id> ...] \
  --managed-identity-resource https://cognitiveservices.azure.com \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

Use a **Custom** provider for an OpenAI-compatible or Anthropic Messages
endpoint. Custom providers default to API-key authentication:

```bash
az ai-gateway model-provider create \
  --name <provider> \
  --kind Custom \
  --endpoint <https-endpoint> \
  --api-key-header-name <header-name> \
  --api-key-value "$PROVIDER_API_KEY" \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

The API-key value is sent exactly as entered, so do not add an authentication
scheme unless the upstream provider requires it. Add `--no-sync` to create the
provider without discovering models.

Preview provider reconciliation before applying it:

```bash
az ai-gateway model-provider sync \
  --name <provider> \
  --dry-run \
  --resource-name <gateway> \
  --resource-group <resource-group> \
  --output table
```

Run without `--dry-run` only after showing the plan. Stale model deletion requires
both `--delete-missing` and `--yes`, plus explicit user confirmation. Use
`az ai-gateway model create|show|list|update|delete` for individual registrations;
`create` requires `--provider-name`.

### MCP tool servers

`--endpoints` accepts an inline JSON array or `@file`; supported endpoint kinds
are `mcp`, `openApi`, and `http`.

```bash
az ai-gateway mcp create \
  --name <server> \
  --endpoints @endpoints.json \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

Inspect the endpoint file and obtain confirmation before create or update. If an
endpoint uses OAuth and requires interactive authorization, run:

```bash
az ai-gateway mcp authorize \
  --name <server> \
  --endpoint-id <endpoint> \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

Do not claim authorization succeeded until the CLI completes successfully.

### Policies

Policies can target a model or MCP server. Require an existing policy JSON file:

```bash
az ai-gateway policy create \
  --scope-type <model-or-mcp> \
  --scope-name <asset-name> \
  --policy @policy.json \
  [--provider-name <provider>] \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

Policy IDs contain `#`; quote literal IDs for `show`, `update`, and `delete`.
Before translating APIM policy behavior, inspect support with:

```bash
az ai-gateway policy import-support show --name <apim-policy>
az ai-gateway policy import-support list [--support-level <level>]
```

Support levels are `partial`, `consumed`, and `unsupported`.

### API keys

Create and inspect key metadata with `api-key create`, `list`, and `show`.
Retrieve live values only via an explicit `list-secrets` request. Regeneration is
destructive because clients using the old value can fail:

```bash
az ai-gateway api-key regenerate \
  --name <key> \
  --key-type primary \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

Confirm which key slot is being rotated and remind the user to update dependent
clients. Never include returned values in the final response.

### Managed identities

Assign or remove system- and user-assigned identities:

```bash
az ai-gateway identity assign \
  [--system-assigned] \
  [--user-assigned <resource-id> ...] \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

Use `identity show` before and after. Identity assignment does not itself grant
RBAC access; state that role assignments may still be required, but do not guess
which role or scope without knowing the upstream resource.

### Telemetry exporters

For an existing Application Insights component:

```bash
az ai-gateway telemetry-exporter create \
  --name <exporter> \
  --application-insights <component-resource-id> \
  --resource-name <gateway> \
  --resource-group <resource-group>
```

For custom OpenTelemetry, all three absolute HTTPS endpoints are required:
`--metrics-endpoint`, `--logs-endpoint`, and `--traces-endpoint`. Custom
`--headers` cannot include `Authorization` or be combined with managed identity.
`--identity-client-id` requires `--managed-identity-resource`. Enable
`--payload-capture` only after warning that request and response content may
contain sensitive data and receiving explicit confirmation.

## Operate and assess

Use `az ai-gateway list|show|update|delete` for gateway lifecycle operations and
the nested groups' `list|show|update|delete` commands for assets. Inspect state
before update or deletion and verify afterward.

To assess migration from an existing API Management resource:

```bash
az ai-gateway import \
  --name <gateway> \
  --resource-group <resource-group> \
  --source-apim-id <resource-id> \
  --dry-run \
  [--include models agents tools] \
  [--conflict-policy fail|skip|overwrite] \
  [--mapping-file @mapping.json] \
  --output table
```

Import execution is not available. Never remove `--dry-run` or claim the returned
plan was applied. Sensitive policy, credential, and URL values are redacted.

## Completion

Report:

- the subscription, resource group, and gateway operated on;
- resources created, updated, deleted, or left unchanged;
- verification state and any pending authorization or RBAC work;
- dry-run findings separately from applied changes.

Do not include credentials, secret-bearing headers, or unredacted sensitive
configuration in the report.
