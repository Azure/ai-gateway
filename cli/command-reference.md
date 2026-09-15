# AI Gateway CLI command reference

Find a command, understand its arguments, and shape its output. This guide covers
the public command groups in **aigateway 1.0.0b6**; use your installed CLI's
`--help` for the full option list and examples for each command.

New to the CLI? Start with the [installation and quickstart](README.md).

[Find a command](#find-a-command) | [Command groups](#command-groups) | [Arguments](#read-the-arguments) | [Output and queries](#output-and-queries) | [Usage notes](#usage-notes)

## Find a command

Help works without signing in or creating resources. Start at the top, choose a
group, then ask for help on the command you want:

```bash
az aigateway --help
az aigateway mcp --help
az aigateway mcp create --help
```

Nested groups work the same way:

```bash
az aigateway model policy --help
az aigateway model policy set --help
```

Read the command summary, arguments marked `[Required]`, allowed values, and
examples. Some commands require a choice of inputs that is explained in the
help text rather than marked on a single argument. For example, MCP creation
needs `--endpoints` or the optional GitHub onboarding mode.

To check which release you are using:

```bash
az aigateway version
```

## Command groups

Prefix each entry with `az aigateway`. These are the public, non-deprecated
commands; each group and command accepts `--help`.

| Group | Commands | Use it to |
| --- | --- | --- |
| Top level | `create`, `show`, `list`, `update`, `delete`, `wait`, `version` | Manage gateways and inspect the CLI version. |
| `model-provider` | `create`, `show`, `list`, `update`, `delete` | Register model providers, including importing existing Foundry deployments. |
| `model` | `create`, `show`, `list`, `update`, `delete` | Register and manage individual models. |
| `model policy` | `set`, `set-token-limit`, `set-content-safety`, `list`, `remove` | Configure token limits and content safety on a model. |
| `mcp` | `create`, `show`, `list`, `update`, `delete`, `authorize` | Register MCP servers and start OAuth authorization where configured. |
| `mcp source` | `add`, `list`, `remove` | Manage individual backend sources on an MCP registration. |
| `api-key` | `create`, `show`, `list`, `delete`, `list-secrets`, `regenerate` | Manage gateway-wide client API keys. |
| `identity` | `assign`, `show`, `remove`, `wait` | Manage identities assigned to a gateway. |
| `network` | `show`, `update`, `wait` | Configure public access and outbound virtual network integration. |
| `network private-endpoint-connection` | `list`, `show`, `approve`, `reject`, `delete`, `wait` | Manage gateway-side private endpoint connections. |

For example, to find the options for importing a Foundry account's deployments:

```bash
az aigateway model-provider create --help
```

To find the options for adding a source to an existing MCP registration:

```bash
az aigateway mcp source add --help
```

## Read the arguments

The general shape is `az aigateway [group] command [arguments]`. Replace values
inside `<...>` with your own values; do not include the angle brackets.
Examples below use Bash quoting and line continuation.

### Select the right resource

| Target | Resource selectors in these examples |
| --- | --- |
| Gateway | `--resource-group <group> --name <gateway>` |
| MCP registration, model provider, or API key | `--resource-group <group> --gateway-name <gateway> --name <child>` |
| Individual model | `--resource-group <group> --gateway-name <gateway> --provider-name <provider> --name <model>` |

`-g` is short for `--resource-group`, and `-n` for `--name`. The meaning of
`--name` follows the resource being operated on; it is not always the gateway.
List commands generally omit the child name. Some commands accept `--ids`
instead of the separate resource selectors; check that command's help.

Create a gateway (all three arguments below are required):

```bash
az aigateway create \
  --resource-group "<resource-group>" --name "<gateway-name>" \
  --location "<supported-region>"
```

Inspect an existing MCP registration or model:

```bash
az aigateway mcp show \
  -g "<resource-group>" --gateway-name "<gateway-name>" -n "<mcp-name>"

az aigateway model show \
  -g "<resource-group>" --gateway-name "<gateway-name>" \
  --provider-name "<provider-name>" -n "<model-name>"
```

Select a subscription before working, or supply `--subscription` on a command:

```bash
az account set --subscription "<subscription-id>"
az aigateway list --subscription "<subscription-id>" --output table
```

### Structured values and choices

Use the help's exact allowed values and argument shapes. For example,
`mcp create --endpoints` takes an array of endpoint objects, not a URL string;
see the [quickstart](README.md#2-register-an-mcp-server) for a complete example.

For arguments whose help advertises JSON-file support, put the value in a local
JSON file and pass `@filename`. An `endpoints.json` file should contain the
endpoint array itself:

```bash
az aigateway mcp create \
  -g "<resource-group>" --gateway-name "<gateway-name>" -n "<mcp-name>" \
  --endpoints @endpoints.json
```

This also avoids shell-specific JSON escaping. Do not commit files containing
credentials.

## Output and queries

Use `--output table` (or `-o table`) for a quick overview, `--output json`
for the full result, and `--query` with `--output tsv` for individual values
in scripts. Queries use [JMESPath](https://learn.microsoft.com/cli/azure/query-azure-cli).

```bash
az aigateway list --output table
az aigateway show -g "<resource-group>" -n "<gateway-name>" --output json

az aigateway show -g "<resource-group>" -n "<gateway-name>" \
  --query properties.gatewayUrl --output tsv

az aigateway version --query extensionVersion --output tsv
```

Query JSON field names, not the formatted table headings. For example, the
gateway's state is `properties.provisioningState`, not `State`:

```bash
az aigateway show -g "<resource-group>" -n "<gateway-name>" \
  --query "{name:name,state:properties.provisioningState}" --output json
```

To list only models from one provider, use the command's filter:

```bash
az aigateway model list \
  -g "<resource-group>" --gateway-name "<gateway-name>" \
  --model-provider "<provider-name>" --output table
```

List commands that advertise `--max-items` and `--next-token` support paging.
When a limited result includes a continuation token, pass that value to
`--next-token` to resume. Use JSON output while inspecting a paged response
so you do not discard the token.

## Usage notes

- **Sign-in and permissions:** help and version are local; resource commands
  require `az login` and appropriate Azure permissions. Foundry onboarding with
  `--foundry-resource-id` also enables the gateway identity and assigns it the
  Foundry User role on the account, so the caller needs permission to create
  role assignments there. It registers existing deployments, not new ones.
- **Optional GitHub onboarding:** `az aigateway mcp create --github true` needs
  GitHub CLI (`gh`) and a usable GitHub credential, even when `GH_TOKEN` is set.
  The generic `--endpoints` path does not require `gh`.
- **Updates:** gateway `update --tags` replaces the existing tag set. Use
  `model policy` for token limits/content safety and `mcp source` to add or
  remove an individual source without supplying the full endpoint array.
- **Long-running operations:** where supported, `--no-wait` returns before
  provisioning finishes. Use the matching `wait` command with a condition such
  as `--created` or `--updated`; use `wait --help` for available conditions.
- **Keys:** `api-key list` and `show` return metadata, not key values.
  `list-secrets` explicitly returns credentials; keep them out of terminals
  being recorded, logs, and source control. Rotate one value at a time with
  `regenerate --key-type primary` or `secondary`, moving clients before
  rotating the other value.
- **Deletion:** deleting a gateway retains an API Management soft-delete record.
  Deleting a model registration does not delete its underlying deployment.
  Private endpoint connection commands manage only the gateway-side connection,
  not the backing private endpoint resource.

For service setup and application integration, see the
[AI Gateway documentation](https://aka.ms/aigateway/docs) and
[coding-agent plugin](../README.md#coding-agent-plugin).
