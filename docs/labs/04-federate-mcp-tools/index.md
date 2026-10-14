---
title: Federate MCP tools behind one endpoint
summary: Register a remote MCP server in AI Gateway, add a second backend under its own namespace, and connect curl, VS Code, and Python to one governed MCP endpoint.
category: tools
level: Beginner
duration: 25
tracks: [portal, cli, iac, code]
order: 4
illustration: diagrams/mcp-federation.svg
tags: [MCP, tools, federation, toolServers, Streamable HTTP, namespace, VS Code]
objectives:
  - Explain the four tool source types and how AI Gateway namespaces the tools of each backend
  - Register the public Microsoft Learn MCP server in the portal, with the Azure CLI, or with Bicep
  - Federate a second backend into the same MCP server and mark it optional
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

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md).
- A runtime API key. If you don't have one yet, create it in the portal under **Access** › **Keys**, or run
  `az aigateway api-key create -g "$RG" --gateway-name "$GATEWAY" -n labs-tools --display-name labs-tools` and read its value with
  `az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" -n labs-tools --query primaryKey -o tsv`.
- For the CLI and IaC tracks: the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or
  later, signed in with `az login`, and the `aigateway` extension
  ([install it](https://github.com/Azure/ai-gateway/tree/main/cli#install)).
- For the **Verify** scripts: `curl` and `jq` (Bash) or PowerShell 7 or later. The Code track also uses
  Python 3.10 or later and, optionally, VS Code.
- Permission to change the gateway, for example **Contributor** on the resource group.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"

export AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.gatewayUrl -o tsv)"
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG      = "<resource-group>"
$GATEWAY = "<gateway>"

$env:AI_GATEWAY_URL = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

## How it works

An **MCP server** in AI Gateway is a federation point. You give it one or more **backends**, and the gateway
publishes all their tools at one Streamable HTTP endpoint:
`https://<gateway>.azure-api.net/default/toolservers/<server-name>/mcp`.

| Backend type | What you provide | What clients see |
|---|---|---|
| **MCP server** (remote) | A URL that speaks SSE or Streamable HTTP | The server's tools |
| **OpenAPI spec** | A JSON or YAML OpenAPI document (upload, URL, or inline) | Selected operations as tools. The operation summary or description becomes the tool description. |
| **Built-in connector** | A managed connection to a SaaS app, such as Microsoft 365, SharePoint, GitHub, or Salesforce | The connector's operations as tools |
| **Foundry Toolbox** | A Microsoft Foundry Toolbox source | The toolbox's tools |

Each backend can have a **namespace**. The gateway prefixes that backend's tools with it, as in
`learn___microsoft_docs_search`, so two backends can expose tools with the same name without conflict.

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

```bash
az aigateway mcp create -g "$RG" --gateway-name "$GATEWAY" --name learn \
  --display-name "Microsoft Learn" \
  --description "Search and fetch official Microsoft documentation and code samples." \
  --endpoints '[{"kind":"mcp","namespace":"learn","mcp":{"transport":"streamableHttp","url":"https://learn.microsoft.com/api/mcp"}}]'
```

`--name` identifies the MCP registration, and `--gateway-name` identifies its parent gateway. `mcp create`
refuses to replace a registration that already exists. Use `az aigateway mcp update` to change one.

### Confirm the registration

```bash
az aigateway mcp list -g "$RG" --gateway-name "$GATEWAY" -o table
az aigateway mcp source list -g "$RG" --gateway-name "$GATEWAY" -n learn -o json
az aigateway mcp show -g "$RG" --gateway-name "$GATEWAY" -n learn --query properties.provisioningState -o tsv
echo "MCP endpoint: ${AI_GATEWAY_URL%/}/default/toolservers/learn/mcp"
```

> **Checkpoint**
> `mcp list` shows `learn`, and `mcp source list` returns one source with `"namespace": "learn"` and
> `"kind": "mcp"`.

<!-- track: iac | Bicep -->

### Review the template

The template references your existing gateway and its `default` workspace, then declares one
`toolServers` resource. The optional `secondNamespace` parameter is used in the next section.

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep).

> [!WARNING]
> A Bicep deployment sends a `PUT`, which replaces the whole MCP server, including backends and tool rules
> that you added in the portal. Deploy the template to a new server name, or keep the template as the only
> source of truth for this server.

### Deploy it

```bash title="Bash"
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" serverName=learn namespace=learn \
  --query properties.outputs
```

```powershell title="PowerShell"
az deployment group create -g $RG `
  --template-file infra/main.bicep `
  --parameters gatewayName=$GATEWAY serverName=learn namespace=learn `
  --query properties.outputs
```

> **Checkpoint**
> The outputs include `mcpEndpoint`, ending in `/default/toolservers/learn/mcp`, and **MCP servers** in the
> portal lists `learn`.

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

```bash
az aigateway mcp source add -g "$RG" --gateway-name "$GATEWAY" -n learn \
  --namespace docs --kind mcp --required false \
  --mcp '{"url":"https://learn.microsoft.com/api/mcp","transport":"streamableHttp"}'

az aigateway mcp source list -g "$RG" --gateway-name "$GATEWAY" -n learn -o json
```

`mcp source add` reads the registration, appends the source, and updates only the endpoint list, so it keeps
your other settings. It fails if the namespace already exists on the server.

<!-- track: iac | Bicep -->

### Redeploy with a second namespace

```bash
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" serverName=learn namespace=learn secondNamespace=docs \
  --query properties.outputs
```

The template adds the second endpoint with `required: false`.

<!-- /tracks -->

> [!TIP]
> In production, the second backend is a different service. For an internal REST API, choose **OpenAPI spec**
> and point **Spec source** › **Fetch from URL** at its OpenAPI document. For an API that needs a key, set
> **Authentication** to **API key** with the **Header name** and **Key value** the backend expects. Clients
> never see that key.

> **Checkpoint**
> The `learn` server has two backends: `learn` (required) and `docs` (optional).

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
`learn___microsoft_docs_search`.

### Call the tools from Python

This client uses the official [MCP Python SDK](https://pypi.org/project/mcp/) and sends the runtime key in the
`api-key` header.

<!-- include: infra/list_tools.py -->

On GitHub, open [infra/list_tools.py](infra/list_tools.py).

```bash title="Bash"
python -m venv .venv && source .venv/bin/activate
pip install -r infra/requirements.txt
python infra/list_tools.py learn learn___microsoft_docs_search "How do I add a token limit in AI Gateway?"
```

```powershell title="PowerShell"
python -m venv .venv; .venv/Scripts/Activate.ps1
pip install -r infra/requirements.txt
python infra/list_tools.py learn learn___microsoft_docs_search "How do I add a token limit in AI Gateway?"
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
MCP endpoint: https://<gateway>.azure-api.net/default/toolservers/learn/mcp
Server: <server-name-reported-by-the-gateway>  protocol: <negotiated-version>

Tool                                          Description
learn___microsoft_docs_search                 Search official Microsoft/Azure documentation to find the most relevan
learn___microsoft_code_sample_search          Search for code snippets and examples in official Microsoft Learn docu
learn___microsoft_docs_fetch                  Fetch and convert a Microsoft Learn documentation webpage to markdown
docs___microsoft_docs_search                  Search official Microsoft/Azure documentation to find the most relevan
docs___microsoft_code_sample_search           Search for code snippets and examples in official Microsoft Learn docu
docs___microsoft_docs_fetch                   Fetch and convert a Microsoft Learn documentation webpage to markdown

6 tools published
```

Each tool carries its backend's namespace. Use the exact names that your output shows in the next steps.

### Call a tool through the gateway

```bash title="Bash"
./infra/list-tools.sh learn learn___microsoft_docs_search "How do I add a token limit in AI Gateway?"
```

```powershell title="PowerShell"
./infra/list-tools.ps1 -Server learn -Tool learn___microsoft_docs_search -Query "How do I add a token limit in AI Gateway?"
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
- **Onboard GitHub.** `az aigateway mcp create --github true` registers the read-only GitHub MCP server with your
  GitHub CLI credential. It requires `gh` and a usable GitHub sign-in.
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

```bash
# Remove only the optional backend
az aigateway mcp source remove -g "$RG" --gateway-name "$GATEWAY" -n learn --namespace docs

# Or remove the whole MCP server
az aigateway mcp delete -g "$RG" --gateway-name "$GATEWAY" -n learn --yes
```

`mcp source remove` refuses to remove the last remaining source. Delete the server instead.

<!-- track: iac | Bicep -->

### Redeploy or delete

Redeploy without `secondNamespace` to go back to one backend, or delete the server:

```bash
az aigateway mcp delete -g "$RG" --gateway-name "$GATEWAY" -n learn --yes
```

<!-- track: code | Code -->

### Remove the client configuration

Delete the `ai-gateway-learn` entry from `.vscode/mcp.json` and the `.venv` folder you created.

<!-- /tracks -->

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from the MCP endpoint | The key is missing, revoked, or sent in the wrong header | Send a runtime key from **Access** › **Keys** in the `api-key` header. |
| `404` from the MCP endpoint | Wrong server name in the URL, or the server is still provisioning | Run `az aigateway mcp list` and use the exact name in `/default/toolservers/<server-name>/mcp`. |
| `406` or an error about the `Accept` header | The client doesn't accept both JSON and SSE | Send `Accept: application/json, text/event-stream`, or use an MCP SDK. |
| `tools/list` returns an empty `tools` array | The registration is reachable but no backend returned tools | Check each backend's URL and authentication with `az aigateway mcp source list`. |
| The whole server fails when one backend is down | That backend is **Required** | Turn **Required** off for backends that are nice-to-have, or fix the backend. |
| `mcp create` or `mcp source add` fails with a conflict | The server name or the namespace already exists | Use `az aigateway mcp update`, pick another name, or remove the old source first. |

## Next steps

- [Control which tools agents can call](../05-mcp-tool-controls/README.md): allow and block tools by name, and
  rate-limit the server.
- [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md): give an agent your governed tools and models.
- [Set gateway-wide policy baselines](../09-gateway-baselines/README.md): apply defaults to every MCP server and model.
- Docs: [Connect to MCP tools through AI Gateway](https://ai.gateway.azure.com/docs/mcp-access).
