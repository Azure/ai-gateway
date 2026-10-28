---
title: Federate MCP tools behind one endpoint
summary: Register a remote MCP server in AI Gateway, add a second backend under its own namespace, and connect curl, VS Code, and Python to one governed MCP endpoint.
category: tools
level: Beginner
duration: 30
tracks: [portal, cli, iac, code]
order: 4
illustration: diagrams/mcp-federation.svg
tags: [MCP, tools, federation, toolServers, Streamable HTTP, namespace, protocol versions, VS Code]
objectives:
  - Explain the four tool source types and how AI Gateway namespaces the tools of each backend
  - Register the public Microsoft Learn MCP server in the portal, with the Azure CLI, or with Bicep and azd
  - Federate a second backend into the same MCP server and mark it optional
  - Choose the MCP protocol versions the server supports and check what clients negotiate
  - Connect curl, VS Code, and a Python MCP client to the governed endpoint with a runtime key
prereqs:
  - 01-provision-gateway
---

# Federate MCP tools behind one endpoint

Your agent teams want tools: documentation search, ticketing, internal APIs. If every agent connects to every
tool server directly, you end up with credentials in many places and no single point of control. In this lab
the platform team publishes **one governed MCP endpoint** on the gateway, starting with the public Microsoft
Learn MCP server, so agents get tools through the same front door they already use for models.

![One MCP endpoint on the gateway federates tools from several backends](../assets/diagrams/mcp-federation.svg "Clients connect to one MCP endpoint. The gateway authenticates them, applies policies, and federates the namespaced tools of every backend.")

## Before you begin

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, the `learn` MCP server, and a key, so you can skip
> this section. You need only [Azure Cloud Shell](https://shell.azure.com), or the Azure Developer CLI (`azd`), the
> Azure CLI, and Git on your machine.

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md).
- A runtime API key, for example `app-first-call` from [lab 02](../02-first-model-call/README.md). If you don't have
  one yet, create it in the portal under **Access** › **Keys**, or, after
  you set the variables below, run
  `az aigateway api-key create -g "$RG" --gateway-name "$GATEWAY" -n app-first-call --display-name app-first-call`
  and read its value with
  `az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" -n app-first-call --query primaryKey -o tsv`.
- For the CLI track: the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or
  later, signed in with `az login`, the `aigateway` extension
  ([install it](../01-provision-gateway/README.md#before-you-begin)), and `jq` for the Bash snippets.
- For the **Verify** scripts: `curl` and `jq` (Bash) or PowerShell 7 or later. The Code track also uses
  Python 3.10 or later and, optionally, VS Code.
- Permission to change the gateway, for example **Contributor** on the resource group.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export WS="https://management.azure.com$GATEWAY_ID/workspaces/default"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG         = "<resource-group>"
$GATEWAY    = "<gateway>"

$API        = "api-version=2025-09-01-preview"
$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$WS         = "https://management.azure.com$GATEWAY_ID/workspaces/default"
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

## How it works

An **MCP server** in AI Gateway is a federation point. You give it one or more **backends**, and the gateway
publishes all their tools at one Streamable HTTP endpoint:
`https://<gateway>.eastus2-01.ai.gateway.azure.com/default/toolservers/<server-name>/mcp`.

| Backend type | What you provide | What clients see |
|---|---|---|
| **MCP server** (remote) | A URL that speaks SSE or Streamable HTTP | The server's tools |
| **OpenAPI spec** | A JSON or YAML OpenAPI document (upload, URL, or inline) | Selected operations as tools. The operation summary or description becomes the tool description. |
| **Built-in connector** | A managed connection to a SaaS app, such as Microsoft 365, SharePoint, GitHub, or Salesforce | The connector's operations as tools |
| **Foundry Toolbox** | A Microsoft Foundry Toolbox source | The toolbox's tools |

Each backend can have a **namespace**. The gateway prefixes that backend's tools with it, as in
`learn_microsoft_docs_search`, so two backends can expose tools with the same name without conflict.

The gateway authenticates **clients**. In this lab they send a runtime key in the `api-key` header.
It authenticates to each **backend** separately, with **None**, **API key** (a header name and value),
**OAuth 2.0**, or **Managed identity**. Backend credentials are stored securely, are never exposed to clients,
and appear under **Connections**.

> [!NOTE]
> Registering a backend doesn't mean that AI Gateway translates every backend protocol into MCP. Pick the
> backend type that matches what the backend actually serves.

## Register the Learn MCP server

Pick one track. Each track creates the same MCP server: **`learn`**, with one backend, the public Microsoft
Learn MCP server at `https://learn.microsoft.com/api/mcp`, under the namespace `learn`. That server needs no
credentials, so the backend authentication is **None**.

<!-- track: portal | Portal -->

### Start the workflow

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher.
Select **MCP servers** › **Add MCP server**. The full-page **Create MCP server** workflow has three steps:
**Basic info**, **Backends**, and **Tools**.

### Describe the server

On **Basic info**, set:

| Field | Value |
|---|---|
| **Name** | `learn` (part of the endpoint URL; it can't be changed after creation) |
| **Display name** | `Microsoft Learn` |
| **Description** | `Search and fetch official Microsoft documentation and code samples.` |

Agents and people read the description to decide when to use the server, so keep it specific. Select **Next**.

### Add the Learn backend

On **Backends**, select **Add backend**. In **Choose a backend type**, select **MCP server**, then set:

| Field | Value |
|---|---|
| **URL** | `https://learn.microsoft.com/api/mcp` |
| **Namespace** | `learn` |
| **Authentication** | **None** |

The backend appears in the table with its **URL**, **Type**, **Authentication**, **Namespace**, and
**Required** columns. Leave **Required** on. Select **Next**.

### Publish all tools

On **Tools**, under **Tool availability**, keep **Allow all tools** ("Expose every tool from these backends,
including tools added in the future."). You narrow this down in
[Control which tools agents can call](../05-mcp-tool-controls/README.md). Select **Create**.

### Copy the endpoint

The server's details page opens. When **Provisioning** shows that the server is ready, copy the
**Endpoint URL**. It ends in `/default/toolservers/learn/mcp`.

> **Checkpoint**
> **MCP servers** lists `learn`, and its details page shows an **Endpoint URL** and one backend with the
> namespace `learn`.

<!-- track: cli | Azure CLI -->

### Create the registration

`az aigateway mcp create` registers the MCP server. `--endpoints` takes the backends as a JSON array.

```bash title="Bash"
az aigateway mcp create -g "$RG" --gateway-name "$GATEWAY" -n learn \
  --display-name "Microsoft Learn" \
  --description "Search and fetch official Microsoft documentation and code samples." \
  --endpoints '[{"kind": "mcp", "namespace": "learn", "required": true,
                 "mcp": {"transport": "streamableHttp", "url": "https://learn.microsoft.com/api/mcp"}}]' \
  --query "{name:name,mcpEndpoint:properties.gatewayEndpoints[0].url}"
```

```powershell title="PowerShell"
ConvertTo-Json -Depth 10 -Compress -InputObject @(
  @{ kind = 'mcp'; namespace = 'learn'; required = $true
     mcp  = @{ transport = 'streamableHttp'; url = 'https://learn.microsoft.com/api/mcp' } }
) | Set-Content -Path endpoints.json
az aigateway mcp create -g $RG --gateway-name $GATEWAY -n learn `
  --display-name "Microsoft Learn" `
  --description "Search and fetch official Microsoft documentation and code samples." `
  --endpoints "@endpoints.json" `
  --query "{name:name,mcpEndpoint:properties.gatewayEndpoints[0].url}"
Remove-Item endpoints.json
```

`-n learn` is the MCP server name. `mcp create` fails with `This MCP registration already exists; use mcp update.`
if the name is taken, so change an existing registration with `az aigateway mcp update` or the `mcp source`
commands, as in the next section.

### Confirm the registration

The commands are the same in Bash and PowerShell.

```bash
az aigateway mcp list -g "$RG" --gateway-name "$GATEWAY" -o table
az aigateway mcp show -g "$RG" --gateway-name "$GATEWAY" -n learn \
  --query "properties.{endpoints:endpoints,url:gatewayEndpoints[0].url}"
```

> **Checkpoint**
> The table shows `learn` with `Microsoft Learn` in the **DisplayName** column and `1` in the **Sources** column.
> The second command returns one endpoint with `"namespace": "learn"` and `"kind": "mcp"`, and a `url` that ends
> in `/default/toolservers/learn/mcp`.

<!-- track: iac | Bicep + azd -->

**What you need:** [Azure Cloud Shell](https://shell.azure.com), in Bash or PowerShell, or [azd](https://aka.ms/azd-install),
the Azure CLI with the `aigateway` extension, and Git on your machine, signed in with `azd auth login` and `az login`.
This track doesn't use your gateway from lab 01: `azd up` creates a new one, so it works on its own.

### Clone the lab

The lab is a small azd project in the
[`labs/04-federate-mcp-tools`](https://github.com/Azure/ai-gateway/tree/main/labs/04-federate-mcp-tools) folder of
the GitHub repo. Clone the repo and move into that folder. If you cloned it for an earlier lab, move into
`ai-gateway/labs/04-federate-mcp-tools` instead.

```bash title="Bash"
git clone https://github.com/Azure/ai-gateway.git
cd ai-gateway/labs/04-federate-mcp-tools
```

```powershell title="PowerShell"
git clone https://github.com/Azure/ai-gateway.git
Set-Location ai-gateway/labs/04-federate-mcp-tools
```

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and calls lab 01's
[gateway.bicep](../01-provision-gateway/infra/gateway.bicep) for a gateway with no model. Then it calls
`infra/tool-server.bicep` for the `learn` MCP server and the `app-first-call` key. azd fills the `secondNamespace`
and `supportedVersions` parameters from the environment values `MCP_SECOND_NAMESPACE` and `MCP_SUPPORTED_VERSIONS`,
which the next sections set. Empty, they register one backend and keep the legacy MCP versions.

<!-- include: infra/main.bicep -->

`infra/tool-server.bicep` references the gateway and its `default` workspace, then declares one `toolServers`
resource and, when `apiKeyName` is set, the runtime key. The key's value is never an output. You can also deploy
the module on its own to a gateway you already have, with `az deployment group create`, as lab 24 does.

<!-- include: infra/tool-server.bicep -->

> [!WARNING]
> A Bicep deployment sends a `PUT`, which replaces the whole MCP server, including backends and tool rules
> that you added in the portal. Keep the template as the only source of truth for this server, and change it with
> `azd provision`.

### Deploy with azd up

Create an azd environment named `aigw-lab04` in your current subscription, then provision everything. It takes
about three minutes.

```bash title="Bash"
azd env new aigw-lab04 --location eastus2 --subscription "$(az account show --query id --output tsv)"
azd up
```

```powershell title="PowerShell"
azd env new aigw-lab04 --location eastus2 --subscription (az account show --query id --output tsv)
azd up
```

For another region, use its name from [Find the available
regions](../01-provision-gateway/README.md#find-the-available-regions).

### Read the outputs and the key

Set the variables that the next sections and **Verify** use from azd's environment values, and read the key from
the gateway, so that it never shows on screen.

```bash title="Bash"
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$(azd env get-value AI_GATEWAY_ID)/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
azd env get-value MCP_ENDPOINT
```

```powershell title="PowerShell"
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
azd env get-value MCP_ENDPOINT
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`, and the last command printed the MCP endpoint, ending in
> `/default/toolservers/learn/mcp`. In the portal, **MCP servers** lists `learn` with one backend, `learn`.

<!-- /tracks -->

## Federate a second backend

Federation pays off when one endpoint combines several backends. To see it without extra credentials, add the
same public Learn server again under a second namespace, `docs`. Both backends expose a tool called
`microsoft_docs_search`, and the namespaces keep them apart. Mark the new backend as **not required**: if an
optional backend is unavailable, the gateway skips it instead of failing the whole MCP server.

<!-- track: portal | Portal -->

### Add the backend

On the `learn` details page, select **Edit**, then go to **Backends**. Select **Add backend** › **MCP server**
and set **URL** to `https://learn.microsoft.com/api/mcp`, **Namespace** to `docs`, and **Authentication** to
**None**. In the backends table, turn **Required** off for the new row. Select **Save**.

<!-- track: cli | Azure CLI -->

### Add the source

`az aigateway mcp source add` appends one backend and changes only the list of backends. Other settings, such as
the description and policies, stay as they are.

```bash title="Bash"
az aigateway mcp source add -g "$RG" --gateway-name "$GATEWAY" -n learn \
  --namespace docs --kind mcp --required false \
  --mcp '{"transport": "streamableHttp", "url": "https://learn.microsoft.com/api/mcp"}' \
  --query "[].{namespace:namespace,required:required,url:mcp.url}" -o table
```

```powershell title="PowerShell"
@{ transport = 'streamableHttp'; url = 'https://learn.microsoft.com/api/mcp' } |
  ConvertTo-Json -Compress | Set-Content -Path mcp.json
az aigateway mcp source add -g $RG --gateway-name $GATEWAY -n learn `
  --namespace docs --kind mcp --required false --mcp "@mcp.json" `
  --query "[].{namespace:namespace,required:required,url:mcp.url}" -o table
Remove-Item mcp.json
```

The table lists every backend of the server. The command fails with "A source with namespace 'docs' already
exists on this MCP server registration." if you run it twice. For a backend that needs a key, pass the key with
`--credentials`.

<!-- track: iac | Bicep + azd -->

### Add the second namespace

When `secondNamespace` isn't empty, the template adds a second endpoint with `required: false`. Set it in the azd
environment and provision again. Only the MCP server changes.

```bash title="Bash"
azd env set MCP_SECOND_NAMESPACE docs
azd provision
```

```powershell title="PowerShell"
azd env set MCP_SECOND_NAMESPACE docs
azd provision
```

<!-- /tracks -->

> [!TIP]
> In production, the second backend is a different service. For an internal REST API, choose **OpenAPI spec**
> and point **Spec source** › **Fetch from URL** at its OpenAPI document. For an API that needs a key, set
> **Authentication** to **API key** with the **Header name** and **Key value** the backend expects. Clients
> never see that key.

> **Checkpoint**
> The `learn` server has two backends: `learn` (required) and `docs` (optional).

## Choose supported MCP versions

MCP is versioned by date. A client opens a connection by naming the protocol version it speaks, and the server
answers with the version both sides will use. AI Gateway negotiates one version for the whole MCP server, so
that version must work with **every backend** behind it.

| Supported MCP versions | What clients get |
|---|---|
| Not configured | The legacy defaults: `2025-06-18`, `2025-03-26`, and `2024-11-05`. The portal labels them **Legacy defaults**. |
| A list that you choose | Version restrictions. Clients negotiate only a version in the list, and a request whose `MCP-Protocol-Version` header names any other version is rejected with `400`. |

You can choose `2026-07-28`, `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`. Version
`2026-07-28` is the stateless revision of the specification: it replaces the `initialize` handshake and
sessions with a `server/discover` request, and every request carries `MCP-Protocol-Version`, `Mcp-Method`, and
`Mcp-Name` headers plus metadata in `params._meta`. Select it only when every backend supports it, and use an
MCP SDK that implements it rather than hand-written requests.

In this lab, pin the server to `2025-06-18`. At the time of writing, that's the version the Microsoft Learn MCP
server negotiates, so both backends, `learn` and `docs`, support it.

<!-- track: portal | Portal -->

### Pin the version

1. On the `learn` details page, find **Supported MCP versions**. Unless you changed it, it lists the legacy
   defaults.
2. Select **Edit**. On **Basic info**, open **Supported MCP versions** and keep only `2025-06-18` selected.
3. Go to **Backends**. Because the list changed, the portal asks you to recheck the backends: "Supported MCP
   versions changed. Edit and save each external MCP backend before saving this server." For each backend row,
   select **Edit**, then **Save** in **Edit MCP backend**. The portal checks which versions the backend
   supports before it saves the row.
4. Select **Save**.

If a backend doesn't support a selected version, **Edit MCP backend** shows "Backend isn't compatible with all
configured MCP versions." and lists the versions the backend reports. Return to **Basic info** and change the
list, or update the backend.

<!-- track: cli | Azure CLI -->

### Set the versions

The `aigateway` extension doesn't set MCP protocol versions yet, so call the Azure Resource Manager REST API with
`az rest`. A `PATCH` that sends only `properties.versions` keeps the backends, tool rules, and policies as they are.

```bash title="Bash"
az rest --method patch --url "$WS/toolServers/learn?$API" \
  --body '{"properties": {"versions": ["2025-06-18"]}}' --query properties.versions
```

```powershell title="PowerShell"
@{ properties = @{ versions = @('2025-06-18') } } | ConvertTo-Json -Depth 5 -Compress | Set-Content -Path body.json
az rest --method patch --url "$WS/toolServers/learn?$API" --body '@body.json' --query properties.versions
Remove-Item body.json
```

Unlike the portal, the API doesn't ask the backends which versions they support. If you list a version that a
backend can't speak, the `PATCH` succeeds and clients that negotiate that version fail. See
[Troubleshooting](#troubleshooting).

<!-- track: iac | Bicep + azd -->

### Pin the versions

The `supportedVersions` parameter takes a comma-separated list, such as `2025-06-18` or `2026-07-28,2025-06-18`,
and azd fills it from `MCP_SUPPORTED_VERSIONS`. Set it and provision again. The azd environment keeps
`MCP_SECOND_NAMESPACE`, so both backends stay.

```bash title="Bash"
azd env set MCP_SUPPORTED_VERSIONS 2025-06-18
azd provision
az aigateway mcp show -g "$RG" --gateway-name "$GATEWAY" -n learn --query properties.versions
```

```powershell title="PowerShell"
azd env set MCP_SUPPORTED_VERSIONS 2025-06-18
azd provision
az aigateway mcp show -g $RG --gateway-name $GATEWAY -n learn --query properties.versions
```

The last command prints a list that holds only `2025-06-18`. An empty value doesn't clear a list that the server already has, so
to change the versions later, set another list.

<!-- /tracks -->

### Check the negotiated version

Ask for an older version. The gateway answers with the version it will use:

```bash title="Bash"
curl -sS "${AI_GATEWAY_URL%/}/default/toolservers/learn/mcp" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26",
       "capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

```powershell title="PowerShell"
$mcp     = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/toolservers/learn/mcp"
$headers = @{ 'api-key' = $env:AI_GATEWAY_API_KEY; Accept = 'application/json, text/event-stream' }
$body    = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26",
             "capabilities":{},"clientInfo":{"name":"pwsh","version":"1.0"}}}'
(Invoke-WebRequest -Method Post -Uri $mcp -Headers $headers -ContentType 'application/json' -Body $body).Content
```

The result includes `"protocolVersion":"2025-06-18"`. Now send a request that names a version outside the list:

```bash title="Bash"
curl -sS -w "\nHTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/toolservers/learn/mcp" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2026-07-28" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

```powershell title="PowerShell"
$r = Invoke-WebRequest -Method Post -Uri $mcp -SkipHttpErrorCheck -ContentType 'application/json' `
  -Headers ($headers + @{ 'MCP-Protocol-Version' = '2026-07-28' }) -Body '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
"HTTP $($r.StatusCode) $($r.Content)"
```

The gateway rejects it with `400` and `Unsupported MCP-Protocol-Version` before any backend is called.

> **Checkpoint**
> **Supported MCP versions** shows `2025-06-18` on the details page and in **Catalog**, an `initialize` request
> for `2025-03-26` returns `2025-06-18`, and a `2026-07-28` request is rejected with `400`.

## Connect a client

Any MCP-compatible client or agent framework can use the endpoint. Store the runtime key in the client's
secret store, never in a file that you commit.

<!-- track: portal | Portal -->

### Use the Connect panel

On the `learn` details page, select **Connect**. The panel offers **VS Code** and **Cursor** (install through a
deep link) and **mcp.json** (raw configuration for any MCP-aware client). Replace any key placeholder with your
runtime key in the client's secret prompt, not in a committed file.

<!-- track: code | Code -->

### Add the server to VS Code

Create `.vscode/mcp.json` in a project, paste this configuration, and replace `<gateway>` with your gateway
name. The `inputs` entry makes VS Code prompt for the key instead of storing it in the file.

<!-- include: infra/mcp.json -->

On GitHub, open [infra/mcp.json](infra/mcp.json).

Start the `ai-gateway-learn` server from the `mcp.json` editor and paste your runtime key when prompted. In
Copilot Chat agent mode, the gateway's namespaced tools are now available, for example
`learn_microsoft_docs_search`.

### Call the tools from Python

This client uses the official [MCP Python SDK](https://pypi.org/project/mcp/) and sends the runtime key in the
`api-key` header.

<!-- include: infra/list_tools.py -->

On GitHub, open [infra/list_tools.py](infra/list_tools.py).

```bash title="Bash"
python -m venv .venv && source .venv/bin/activate
pip install -r infra/requirements.txt
python infra/list_tools.py learn learn_microsoft_docs_search "How do I add a token limit in AI Gateway?"
```

```powershell title="PowerShell"
python -m venv .venv; .venv/Scripts/Activate.ps1
pip install -r infra/requirements.txt
python infra/list_tools.py learn learn_microsoft_docs_search "How do I add a token limit in AI Gateway?"
```

<!-- /tracks -->

## Verify

<!-- steps -->

### List the published tools

MCP clients start with a handshake: `initialize`, then `notifications/initialized`, then `tools/list`. The
script runs that handshake through your gateway, reads JSON or server-sent event (SSE) responses, and prints
every published tool. Run it from the lab folder.

```bash title="Bash"
./infra/list-tools.sh learn
```

```powershell title="PowerShell"
./infra/list-tools.ps1 -Server learn
```

On GitHub, open [list-tools.sh](infra/list-tools.sh) or [list-tools.ps1](infra/list-tools.ps1).

Expected output (descriptions are shortened, and the tool list can change as the Learn server evolves):

```text
MCP endpoint: https://<gateway>.eastus2-01.ai.gateway.azure.com/default/toolservers/learn/mcp
Server: <server-name-reported-by-the-gateway>  protocol: <negotiated-version>

Tool                                          Description
learn_microsoft_docs_search                   Search official Microsoft/Azure documentation to find the most relevan
learn_microsoft_code_sample_search            Search for code snippets and examples in official Microsoft Learn docu
learn_microsoft_docs_fetch                    Fetch and convert a Microsoft Learn documentation webpage to markdown
docs_microsoft_docs_search                    Search official Microsoft/Azure documentation to find the most relevan
docs_microsoft_code_sample_search             Search for code snippets and examples in official Microsoft Learn docu
docs_microsoft_docs_fetch                     Fetch and convert a Microsoft Learn documentation webpage to markdown

6 tools published
```

Each tool carries its backend's namespace. Use the exact names that your output shows in the next steps.

### Call a tool through the gateway

```bash title="Bash"
./infra/list-tools.sh learn learn_microsoft_docs_search "How do I add a token limit in AI Gateway?"
```

```powershell title="PowerShell"
./infra/list-tools.ps1 -Server learn -Tool learn_microsoft_docs_search -Query "How do I add a token limit in AI Gateway?"
```

After the tool list, the script prints the start of the search results that Microsoft Learn returned through
your gateway.

### Send a raw JSON-RPC request

The docs show the smallest possible request: a single JSON-RPC `tools/list` call. Streamable HTTP clients
should also accept both JSON and SSE responses.

```bash
curl -sS "${AI_GATEWAY_URL%/}/default/toolservers/learn/mcp" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The answer is JSON or an SSE `data:` line with a `result.tools` array. If the server answers with a JSON-RPC
`error` instead, it requires the full handshake. Use the script, which runs it for you.

### Prove that the gateway checks the caller

Send the same request without the key:

```bash
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/toolservers/learn/mcp" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The gateway rejects the request, typically with `401`, and no backend is called. Microsoft Learn is public,
but your MCP endpoint isn't.

<!-- /steps -->

> **Checkpoint**
> The script lists namespaced tools from both backends, a tool call returns Microsoft Learn content, and a
> request without a key is rejected.

## Go further

- **Control the catalog.** Publish only approved tools, block risky ones, and rate-limit the server in
  [Control which tools agents can call](../05-mcp-tool-controls/README.md).
- **Screen tool traffic.** Content safety also screens tool inputs and responses on MCP servers. See
  [Screen prompts and responses with content safety](../08-content-safety/README.md).
- **Go keyless.** Grant callers the **AI Gateway User** role and send a Microsoft Entra token instead of a
  runtime key. See [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md).
- **Watch tool traffic.** When Application Insights is configured, tool executions appear in **Monitoring** ›
  **Tools**. See [Monitor usage, cost, and traces](../13-monitoring/README.md).
- **Onboard GitHub.** Add the GitHub MCP server, `https://api.githubcopilot.com/mcp/`, as an **MCP server**
  backend with **API key** authentication: **Header name** `Authorization` and **Key value**
  `Bearer <your-github-token>`. The gateway stores the token, and clients never see it.
- **Give tools to an agent.** Point an agent framework at the endpoint in [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md).

## Clean up

MCP servers don't add charges beyond the gateway itself. Keep `learn` if you continue with
[Control which tools agents can call](../05-mcp-tool-controls/README.md), which builds on it.

<!-- track: portal | Portal -->

### Remove the second backend or the server

To remove only the `docs` backend, select **Edit** on the `learn` details page, delete its row on **Backends**,
and select **Save**. To remove the whole server, select **Delete** on the details page.

<!-- track: cli | Azure CLI -->

### Remove the second source or the server

```bash title="Bash"
# Remove only the optional backend
az aigateway mcp source remove -g "$RG" --gateway-name "$GATEWAY" -n learn --namespace docs --query "[].namespace"

# Or remove the whole MCP server
az aigateway mcp delete -g "$RG" --gateway-name "$GATEWAY" -n learn --yes
```

```powershell title="PowerShell"
# Remove only the optional backend
az aigateway mcp source remove -g $RG --gateway-name $GATEWAY -n learn --namespace docs --query "[].namespace"

# Or remove the whole MCP server
az aigateway mcp delete -g $RG --gateway-name $GATEWAY -n learn --yes
```

`mcp source remove` prints the backends that remain. An MCP server needs at least one backend, so the command
refuses to remove the last one with "Cannot remove the last source." Delete the server instead.

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

In the `ai-gateway/labs/04-federate-mcp-tools` folder, delete the resource group with the gateway, the `learn` MCP
server, and the key. `--purge` also purges soft-deleted resources, and `--force` skips the confirmation. It takes
about ten minutes.

```bash
azd down --purge --force
```

To keep this gateway instead, skip `azd down`. To go back to one backend, run
`azd env set MCP_SECOND_NAMESPACE ""`, then `azd provision`.

<!-- track: code | Code -->

### Remove the client configuration

Delete the `ai-gateway-learn` entry from `.vscode/mcp.json` and the `.venv` folder you created.

<!-- /tracks -->

Keep your gateway from lab 01: the next labs reuse it. `azd down` doesn't touch it, because the Bicep + azd track
created its own gateway.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from the MCP endpoint | The key is missing, revoked, or sent in the wrong header | Send a runtime key from **Access** › **Keys** in the `api-key` header. |
| `404` from the MCP endpoint | Wrong server name in the URL, or the server is still provisioning | List the servers with `az aigateway mcp list -g "$RG" --gateway-name "$GATEWAY" -o table` and use the exact name in `/default/toolservers/<server-name>/mcp`. |
| `406` or an error about the `Accept` header | The client doesn't accept both JSON and SSE | Send `Accept: application/json, text/event-stream`, or use an MCP SDK. |
| `tools/list` returns an empty `tools` array | The registration is reachable but no backend returned tools | Check each backend's URL with `az aigateway mcp source list -g "$RG" --gateway-name "$GATEWAY" -n <server-name> -o table`, and check its authentication. |
| The whole server fails when one backend is down | That backend is **Required** | Turn **Required** off for backends that are nice-to-have, or fix the backend. |
| Backends or policies disappeared after a Bicep deployment | A Bicep deployment sends a `PUT`, which replaces an existing registration with the same name | Change existing servers with `az aigateway mcp update` or `az aigateway mcp source add` and `remove`, as in the CLI track, or deploy to a new name. |
| `mcp create` fails with "This MCP registration already exists; use mcp update." | A server with that name already exists | Change it with `az aigateway mcp update` or the `mcp source` commands, or choose another name. |
| `mcp source remove` fails with "Cannot remove the last source." | An MCP server needs at least one backend | Keep at least one backend, or delete the server with `az aigateway mcp delete`. |
| `400` with `Unsupported MCP-Protocol-Version` | The client sent an `MCP-Protocol-Version` header that isn't in **Supported MCP versions** | Add the version to the list if every backend supports it, or let the client negotiate a listed version. |
| `404` with "Federation tools/list failed: required endpoint '…' returned error: Backend selected protocol version '…' instead of '…'" | **Supported MCP versions** includes a version that this backend doesn't support, and the client negotiated it | Keep only versions that every backend supports. In the portal, edit and save each backend to recheck it. |
| `400` with JSON-RPC error `-32603`, "The request cannot be completed using the requested protocol version." | A `2026-07-28` request reached a backend that doesn't support `2026-07-28` | Remove `2026-07-28` from **Supported MCP versions** until every backend supports it. |
| `400` with JSON-RPC error `-32602`, "Required MCP request metadata is missing or malformed." | A `2026-07-28` request lacks the `Mcp-Method` or `Mcp-Name` header, or `params._meta` | Use an MCP SDK that implements `2026-07-28` instead of hand-written requests. |
| The portal shows "Backend isn't compatible with all configured MCP versions." | The backend doesn't report support for every selected version | Return to **Basic info** and change **Supported MCP versions**, or update the backend. |
| Creating a server fails with `502 Bad Gateway`, or a Bicep deployment keeps running | Another MCP server in the gateway already uses the same display name | Choose a unique display name, for example with the Bicep `displayName` parameter. |

## Next steps

- [Control which tools agents can call](../05-mcp-tool-controls/README.md): allow and block tools by name, and
  rate-limit the server.
- [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md): give an agent your governed tools and models.
- [Set gateway-wide policy baselines](../09-gateway-baselines/README.md): apply defaults to every MCP server and model.
- Docs: [Connect to MCP tools through AI Gateway](https://ai.gateway.azure.com/docs/mcp-access).
- Release: [October 16 release: MCP 2026-07-28 protocol versions](https://ai.gateway.azure.com/docs/releases/2026-10-16).
