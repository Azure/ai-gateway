# AI Gateway CLI command reference

Find a command, understand its arguments, and shape its output. This guide covers
the public command groups in **aigateway 1.0.0b6**; use your installed CLI's
`--help` for the full option list and examples for each command.

New to the CLI? Start with the [installation and quickstart](README.md).

[Find a command](#find-a-command) | [Command groups](#command-groups) | [Arguments](#read-the-arguments) | [Model policies](#common-model-policies) | [Output and queries](#output-and-queries) | [Runtime tests](#test-models-with-additional-checks) | [Usage notes](#usage-notes)

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

For example, to find the options for importing a Foundry account's deployments
through a provider:

```bash
az aigateway model-provider create --help
```

For the complete variable-based import and inspection example, see
[Add models through a provider](README.md#3-add-models-through-a-provider).
That path registers every current deployment in an existing account and sets up
the gateway identity's access; it does not create the underlying deployments.

To find the options for adding a source to an existing MCP registration:

```bash
az aigateway mcp source add --help
```

## Read the arguments

The general shape is `az aigateway [group] command [arguments]`. Replace values
inside `<...>` with your own values; do not include the angle brackets.
Examples below use Bash quoting and line continuation.

### Set up example variables

Set these once in your shell before using the resource examples. If you followed
the quickstart, reuse your `RG`, `GATEWAY`, and `LOCATION` values. Set `PROVIDER`
and `MODEL` only if you use the model examples, choosing existing registrations.

```bash
SUBSCRIPTION="<subscription-id>"
RG="rg-aigateway-quickstart"
GATEWAY="<gateway-name>"
LOCATION="<supported-region>"
MCP_NAME="learn"
PROVIDER="<provider-name>"
MODEL="<model-name>"

az login
az account set --subscription "$SUBSCRIPTION"
```

The examples are independent, not a script to run from top to bottom. Creation
commands change Azure resources; see the [quickstart](README.md#quickstart) for
permissions, cost considerations, and cleanup.

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

Create a gateway in an existing resource group (all three arguments below are
required). Use a globally unique name for `GATEWAY`:

```bash
az aigateway create \
  --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION"
```

Inspect an existing MCP registration or model:

```bash
az aigateway mcp show \
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME"

az aigateway model show \
  -g "$RG" --gateway-name "$GATEWAY" \
  --provider-name "$PROVIDER" -n "$MODEL"
```

To override the selected subscription for one command, supply `--subscription`:

```bash
az aigateway list --subscription "$SUBSCRIPTION" --output table
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
  -g "$RG" --gateway-name "$GATEWAY" -n "$MCP_NAME" \
  --endpoints @endpoints.json
```

This also avoids shell-specific JSON escaping. Do not commit files containing
credentials.

## Common model policies

Use the [example variables](#set-up-example-variables) to target an existing
gateway model. The [quickstart](README.md#4-set-model-policies) shows how to set
token limits and content safety together. To change just one policy, use the
commands below; the other policy types are preserved.

**Token limit:** allow 10,000 tokens per minute for each identity:

```bash
az aigateway model policy set-token-limit \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --token-limit 10000 --token-period minute --token-counter-key Identity
```

`--token-limit` must be a positive integer. `--token-period` accepts `minute`,
`hour`, or `day`; `--token-counter-key` accepts `Identity` or `IPAddress`.
The defaults are `minute` and `Identity`. This controls token usage, not the
number of requests.

**Content safety:** set Medium severity across the four supported categories:

```bash
az aigateway model policy set-content-safety \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --content-safety Medium
```

`--content-safety` accepts `Low`, `Medium`, `High`, or `None`. It sets the
severity for hate, self-harm, sexual, and violence. Category overrides such as
`--hate-severity` and `--violence-severity` require `--content-safety` in the same
command. Choose thresholds for your application's needs rather than treating
these example settings as a universal recommendation.

Inspect the resulting configuration:

```bash
az aigateway model policy list \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL"
```

Policies apply to the selected gateway model only. Repeat for other models that
need the same controls; they do not govern direct calls to the backend.

## Output and queries

Use `--output table` (or `-o table`) for a quick overview, `--output json`
for the full result, and `--query` with `--output tsv` for individual values
in scripts. Queries use [JMESPath](https://learn.microsoft.com/cli/azure/query-azure-cli).
These examples reuse the [variables above](#set-up-example-variables).

```bash
az aigateway list --output table
az aigateway show -g "$RG" -n "$GATEWAY" --output json

az aigateway show -g "$RG" -n "$GATEWAY" \
  --query properties.gatewayUrl --output tsv

az aigateway version --query extensionVersion --output tsv
```

Query JSON field names, not the formatted table headings. For example, the
gateway's state is `properties.provisioningState`, not `State`:

```bash
az aigateway show -g "$RG" -n "$GATEWAY" \
  --query "{name:name,state:properties.provisioningState}" --output json
```

To list only models from one provider, use the command's filter:

```bash
az aigateway model list \
  -g "$RG" --gateway-name "$GATEWAY" \
  --model-provider "$PROVIDER" --output table
```

List commands that advertise `--max-items` and `--next-token` support paging.
When a limited result includes a continuation token, pass that value to
`--next-token` to resume. Use JSON output while inspecting a paged response
so you do not discard the token.

## Test models with additional checks

The [quickstart](README.md#5-test-the-gateway) uses a fresh gateway's default key
and a known Chat Completions route. The expanded examples below discover an
active key and the selected model's advertised endpoint instead. They stop if
required metadata or credentials are missing.

Use the gateway's runtime URL and API key, not an Azure management token or
Foundry backend credential. You need permission to read key values. Keep the key
in memory: do not print it, enable shell tracing, or paste it into source control.
Model calls can incur inference charges.

### Get the runtime URL and key

**Bash** -- reuse `RG` and `GATEWAY` from the quickstart:

```bash
AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" \
  --query properties.gatewayUrl -o tsv)" || exit 1
KEY_NAME="$(az aigateway api-key list -g "$RG" --gateway-name "$GATEWAY" \
  --query "[?properties.state=='active'].name | [0]" -o tsv)" || exit 1
if [ -z "$AI_GATEWAY_URL" ] || [ -z "$KEY_NAME" ]; then
  echo "No runtime URL or active API key found. Check the gateway configuration." >&2
  exit 1
fi
AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets \
  -g "$RG" --gateway-name "$GATEWAY" -n "$KEY_NAME" \
  --query primaryKey -o tsv)" || exit 1
if [ -z "$AI_GATEWAY_API_KEY" ]; then
  echo "No key value returned. Check your key-read permissions." >&2
  exit 1
fi
```

**PowerShell** -- set the same resource names in this shell:

```powershell
$RG = "rg-aigateway-quickstart"
$GATEWAY = "<your-gateway-name>"

$AI_GATEWAY_URL = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv
if ($LASTEXITCODE -ne 0) { throw "Unable to read the gateway URL." }
$KEY_NAME = az aigateway api-key list -g $RG --gateway-name $GATEWAY --query "[?properties.state=='active'].name | [0]" -o tsv
if ($LASTEXITCODE -ne 0) { throw "Unable to list API keys." }
if (!$AI_GATEWAY_URL -or !$KEY_NAME) { throw "No runtime URL or active API key found." }
$AI_GATEWAY_API_KEY = az aigateway api-key list-secrets -g $RG --gateway-name $GATEWAY -n $KEY_NAME --query primaryKey -o tsv
if ($LASTEXITCODE -ne 0 -or !$AI_GATEWAY_API_KEY) { throw "Unable to read the API key." }
```

For an MCP-only gateway, continue to [Test MCP tools](#test-mcp-tools).

### Select the endpoint and call the model

Use your chosen `PROVIDER` and `MODEL`. These examples select an advertised
`/chat/completions` path and preserve the exact runtime identifier from
`properties.deployment.modelName`, which can differ from the registration name.
If the model supports only Responses, Anthropic Messages, or non-chat
operations, choose a Chat Completions model for this test or use the
[coding-agent plugin](../README.md#coding-agent-plugin) to integrate its protocol.

**Bash / curl**

```bash
MODEL_PATH="$(az aigateway model show \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --query "properties.supportedEndpoints[?ends_with(@, '/chat/completions')] | [0]" -o tsv)" || exit 1
if [ -z "$MODEL_PATH" ]; then
  echo "This model does not advertise a Chat Completions endpoint." >&2
  exit 1
fi
BODY="$(az aigateway model show \
  -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --query "properties.deployment.modelName && {model:properties.deployment.modelName,messages:[{role:'user',content:'Say hello in one sentence.'}]}" -o json)" || exit 1
if [ -z "$BODY" ] || [ "$BODY" = "null" ]; then
  echo "This model has no runtime model identifier." >&2
  exit 1
fi

curl -fsS --max-time 60 "${AI_GATEWAY_URL%/}/default/models${MODEL_PATH}" \
  -H "Api-Key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  --data "$BODY"
```

**PowerShell / `irm`**

```powershell
$PROVIDER = "foundry-models"
$MODEL = "<imported-model-name>"
$modelInfo = az aigateway model show -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $MODEL -o json | ConvertFrom-Json -ErrorAction Stop
if ($LASTEXITCODE -ne 0) { throw "Unable to read the model." }
$modelPath = $modelInfo.properties.supportedEndpoints |
  Where-Object { $_.EndsWith("/chat/completions") } | Select-Object -First 1
if (!$modelPath -or !$modelInfo.properties.deployment.modelName) {
  throw "This model needs a Chat Completions endpoint and a runtime model identifier."
}
$body = @{
  model = $modelInfo.properties.deployment.modelName
  messages = @(@{ role = "user"; content = "Say hello in one sentence." })
} | ConvertTo-Json -Depth 5

$reply = irm -Method Post -Uri "$($AI_GATEWAY_URL.TrimEnd('/'))/default/models$modelPath" `
  -Headers @{ "Api-Key" = $AI_GATEWAY_API_KEY } -ContentType "application/json" `
  -Body $body -TimeoutSec 60 -ErrorAction Stop
$reply | ConvertTo-Json -Depth 20
```

A successful response contains `choices` with the model's reply. A `401` or
`403` means authentication or access needs attention; `404` means the route or
registration should be checked; `429` can mean a gateway token limit or backend
quota was reached. A successful call checks connectivity, not every policy's
enforcement behavior. When finished with all runtime tests, clear the key:

```bash
unset AI_GATEWAY_API_KEY
```

```powershell
Remove-Variable AI_GATEWAY_API_KEY
```

## Test MCP tools

After registering `learn` in the quickstart, first
[read the runtime URL and key](#get-the-runtime-url-and-key) in your
chosen shell. Reuse `AI_GATEWAY_URL` and `AI_GATEWAY_API_KEY` below. These
requests go through your gateway, not directly to Microsoft Learn.

MCP uses an initialization handshake before listing tools. Responses may be
JSON or server-sent events (SSE); for SSE, read the JSON in the `data:` lines.
An HTTP success alone is not enough: check for a JSON-RPC `result`, not `error`.

### Bash / curl

Initialize the connection and display the response headers and body:

```bash
MCP_NAME="learn"
MCP_URL="${AI_GATEWAY_URL%/}/default/toolservers/${MCP_NAME}/mcp"
MCP_HEADERS=(-H "Api-Key: $AI_GATEWAY_API_KEY"
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")

curl -fsS -i --max-time 60 "$MCP_URL" "${MCP_HEADERS[@]}" \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aigateway-quickstart","version":"1.0"}}}'
```

From that response, copy `result.protocolVersion` and the `Mcp-Session-Id`
header (if present). Leave `MCP_SESSION_ID` empty for a server that does not
return that header. Then acknowledge initialization and list tools:

```bash
MCP_PROTOCOL_VERSION="<returned-protocol-version>"
MCP_SESSION_ID=""
SESSION_HEADERS=()
if [ -n "$MCP_SESSION_ID" ]; then
  SESSION_HEADERS=(-H "Mcp-Session-Id: $MCP_SESSION_ID")
fi

curl -fsS --max-time 60 "$MCP_URL" "${MCP_HEADERS[@]}" "${SESSION_HEADERS[@]}" \
  -H "MCP-Protocol-Version: $MCP_PROTOCOL_VERSION" \
  --data '{"jsonrpc":"2.0","method":"notifications/initialized"}'

curl -fsS --max-time 60 "$MCP_URL" "${MCP_HEADERS[@]}" "${SESSION_HEADERS[@]}" \
  -H "MCP-Protocol-Version: $MCP_PROTOCOL_VERSION" \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### PowerShell / Invoke-RestMethod (`irm`)

This MCP example needs **PowerShell 7 or later** to capture response headers
with `-ResponseHeadersVariable`; it adds no requirement to the installer.

```powershell
$MCP_NAME = "learn"
$request = @{
  Method = "Post"
  Uri = "$($AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/$MCP_NAME/mcp"
  Headers = @{ "Api-Key" = $AI_GATEWAY_API_KEY; Accept = "application/json, text/event-stream" }
  ContentType = "application/json"
  TimeoutSec = 60
  ErrorAction = "Stop"
}
$init = irm @request -ResponseHeadersVariable responseHeaders `
  -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"aigateway-quickstart","version":"1.0"}}}'
if ($init -is [string]) { $init } else { $init | ConvertTo-Json -Depth 20 }
```

Copy `result.protocolVersion` from the JSON response (or SSE `data:` payload).
The next block forwards the session ID automatically when the server returned
one:

```powershell
$MCP_PROTOCOL_VERSION = "<returned-protocol-version>"
$request.Headers["MCP-Protocol-Version"] = $MCP_PROTOCOL_VERSION
if ($responseHeaders["Mcp-Session-Id"]) {
  $request.Headers["Mcp-Session-Id"] = [string]($responseHeaders["Mcp-Session-Id"] | Select-Object -First 1)
}
irm @request -Body '{"jsonrpc":"2.0","method":"notifications/initialized"}' | Out-Null
$tools = irm @request -Body '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
if ($tools -is [string]) { $tools } else { $tools | ConvertTo-Json -Depth 20 }
```

Expect a non-empty `result.tools` array describing the registered Learn tools.
An empty array means the registration is reachable but exposes no tools; check
the backend source configuration before integrating a client. This smoke test
checks initialization and tool discovery, not tool execution. Clear the key and
header variables afterward:

```bash
unset AI_GATEWAY_API_KEY MCP_HEADERS SESSION_HEADERS MCP_SESSION_ID
```

```powershell
Remove-Variable AI_GATEWAY_API_KEY, request, responseHeaders
```

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
