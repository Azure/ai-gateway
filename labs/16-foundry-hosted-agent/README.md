---
title: Deploy a Foundry hosted agent behind AI Gateway
summary: Deploy your own Microsoft Agent Framework agent to Foundry Hosted Agents with azd. The agent has no model deployment and no direct tool access, so its model calls and its Microsoft Learn MCP calls go through AI Gateway with a dedicated key. Run it locally, invoke it in Foundry, and cap its tokens without changing its code.
category: agents
level: Intermediate
duration: 40
tracks: [portal, cli, code]
order: 16
illustration: diagrams/hosted-agent.svg
tags: [Foundry Hosted Agents, azd, Microsoft Agent Framework, MCP, Microsoft Learn, API keys, token limits, Python]
objectives:
  - Give a hosted agent its own runtime API key, so its usage and limits stay separate from other apps
  - Wire an Agent Framework agent to the gateway's model and MCP endpoints with the right header for each
  - Run the agent locally with azd, then deploy it to Foundry Hosted Agents with azd up
  - Cap the agent's tokens with a gateway policy, without changing its code
prereqs:
  - 02-first-model-call
  - 04-federate-mcp-tools
---

# Deploy a Foundry hosted agent behind AI Gateway

Your team wants to run an agent in Microsoft Foundry, but the platform team needs every model call and every tool
call to be governed and visible in one place. In this lab you deploy a small Microsoft Agent Framework agent to
Foundry Hosted Agents. Its Foundry project has no model deployments and no tool connections: the agent reaches its
model and its tools only through AI Gateway, with a key of its own.

![A Foundry hosted agent calls a model alias and the Learn MCP server through AI Gateway](../assets/diagrams/hosted-agent.svg "Foundry runs the agent. AI Gateway governs its model calls and its MCP tool calls.")

## Before you begin

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md) and
  [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md). The agent calls the alias from lab 02 and the `learn` MCP
  server from lab 04.
- An Azure subscription where you can create a resource group and a Foundry resource, and assign roles, for example
  **Owner**. azd gives the agent's identity access to its Foundry project.
- These tools:
  - [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) (azd) 1.34.2
    or later, signed in with `azd auth login`
  - Python 3.13 or later. With [uv](https://docs.astral.sh/uv/getting-started/installation/) installed, azd uses it
    to create the agent's virtual environment.
  - Git
- For the Azure CLI track: the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later,
  signed in with `az login` to the same tenant, plus `jq` for the Bash snippets. The CLI track calls the Azure
  Resource Manager REST API with `az rest`, because the `az aigateway` extension doesn't manage the new
  `aigateways` resource type yet.

> [!WARNING]
> `azd up` creates a Foundry resource, and the hosted agent and its model calls are billable. Run
> [Clean up](#clean-up) when you're done.

## How it works

The agent lives in [`infra/`](infra/), a complete azd project:

| File | What it does |
|---|---|
| [`infra/azure.yaml`](infra/azure.yaml) | Declares a Foundry project with no model deployments, and the hosted agent `gateway-agent`: Python 3.13, code deploy, 0.5 CPU, 1 GiB, Responses protocol |
| [`infra/src/gateway-agent/main.py`](infra/src/gateway-agent/main.py) | The agent: one model client and one MCP tool, both pointing at the gateway |
| [`infra/src/gateway-agent/requirements.txt`](infra/src/gateway-agent/requirements.txt) | Pinned dependencies, compiled from `requirements.in`. Foundry builds the agent from this file. |

The agent has two outbound paths, and both end at AI Gateway:

- **Model.** An `OpenAIChatClient` points at the gateway's model endpoint, `/default/models/openai/v1/`, and sends
  your lab 02 alias as `model`. The runtime key is the SDK's API key, so it travels as `Authorization: Bearer`.
  The model endpoint accepts a runtime key either that way or in an `api-key` header.
- **Tools.** An `MCPStreamableHTTPTool` points at the gateway's `/default/toolservers/learn/mcp` endpoint with the
  same key in the `api-key` header. The MCP endpoint accepts keys only in that header: a bearer token there must be
  a Microsoft Entra token.

> [!IMPORTANT]
> Send a key in one header only. If a request carries both `api-key` and `Authorization`, the gateway rejects it
> with `400` and "Specify either an API key or an Authorization header, not both". Older samples set a placeholder
> API key and add an `api-key` header, which the OpenAI SDK turns into exactly that request.

| Piece | Name in this lab | Owner |
|---|---|---|
| Model alias | Your alias from lab 02, in `AI_GATEWAY_MODEL` | AI Gateway |
| MCP server | `learn`, at `/default/toolservers/learn/mcp` | AI Gateway |
| Runtime API key | `hosted-agent` | AI Gateway |
| Foundry resource and project | In resource group `rg-<env>`; the project is named after the azd environment | Foundry, created by azd |
| Hosted agent | `gateway-agent` | Foundry, created by azd |

Foundry runs the agent. AI Gateway decides what the agent may call, counts its tokens, and records every call.

## Give the agent its own key

A dedicated key makes the agent a separate caller identity: its token limits, cost limits, and Monitoring data
don't mix with other apps. Pick one track.

<!-- track: portal | Portal -->

### Create the key

1. In the [AI Gateway portal](https://ai.gateway.azure.com), open your gateway and select **Access** › **Keys**.
2. Select **Create API key**.
3. In **Key name**, enter `hosted-agent`, and select **Create**.
4. The **API key created successfully** dialog shows the value. Select **Copy & done**.

### Load the values in your shell

Paste the key without echoing it, then set the gateway URL from the gateway's **Overview** page and the alias from
lab 02:

```bash title="Bash"
read -rsp "hosted-agent key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
export AI_GATEWAY_URL="https://<gateway>.<region>-01.ai.gateway.azure.com"
export AI_GATEWAY_MODEL="<model-alias>"    # the alias from lab 02
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = Read-Host "hosted-agent key" -MaskInput
$env:AI_GATEWAY_URL = "https://<gateway>.<region>-01.ai.gateway.azure.com"
$env:AI_GATEWAY_MODEL = "<model-alias>"    # the alias from lab 02
```

<!-- track: cli | Azure CLI -->

### Set your variables

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export AI_GATEWAY_MODEL="<model-alias>"    # the alias from lab 02

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az resource show -g "$RG" -n "$GATEWAY" --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv)"
export GW="https://management.azure.com$GATEWAY_ID"
export WS="$GW/workspaces/default"
export AI_GATEWAY_URL="https://$(az resource show --ids "$GATEWAY_ID" --query properties.frontend.defaultHostname -o tsv)"
```

```powershell title="PowerShell"
$RG                   = "<resource-group>"
$GATEWAY              = "<gateway>"
$env:AI_GATEWAY_MODEL = "<model-alias>"    # the alias from lab 02

$API        = "api-version=2025-09-01-preview"
$GATEWAY_ID = az resource show -g $RG -n $GATEWAY --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv
$GW         = "https://management.azure.com$GATEWAY_ID"
$WS         = "$GW/workspaces/default"
$env:AI_GATEWAY_URL = "https://$(az resource show --ids $GATEWAY_ID --query properties.frontend.defaultHostname -o tsv)"
```

### Create the key and load its value

```bash title="Bash"
az rest --method put --url "$GW/apiKeys/hosted-agent?$API" --body '{"properties":{}}' -o none
export AI_GATEWAY_API_KEY="$(az rest --method post --url "$GW/apiKeys/hosted-agent/listSecrets?$API" \
  --query primaryKey -o tsv)"
```

```powershell title="PowerShell"
'{"properties":{}}' | Set-Content apikey.json
az rest --method put --url "$GW/apiKeys/hosted-agent?$API" --body "@apikey.json" -o none
Remove-Item apikey.json
$env:AI_GATEWAY_API_KEY = az rest --method post --url "$GW/apiKeys/hosted-agent/listSecrets?$API" `
  --query primaryKey -o tsv
```

<!-- /tracks -->

> **Checkpoint**
> **Access** › **Keys** lists `hosted-agent` as active, and your shell has `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL`,
> and `AI_GATEWAY_API_KEY`.

## Configure the azd project

<!-- steps -->

### Get the lab files

```bash
git clone https://github.com/Azure/ai-gateway.git
cd ai-gateway/labs/16-foundry-hosted-agent/infra
azd ext install microsoft.foundry
```

`microsoft.foundry` installs the Foundry extensions for azd, including `azure.ai.agents`, which adds the
`azd ai agent` commands.

### Create an azd environment

The environment name also names the resource group, `rg-<env>`, and the Foundry project. Choose a region where
Foundry Hosted Agents are available, for example `eastus2`.

```bash
azd env new aigw-lab16 --location eastus2
```

### Pass the gateway settings to the agent

[`azure.yaml`](infra/azure.yaml) maps four azd environment values to the agent's environment variables:

```yaml
env:
  AI_GATEWAY_URL: ${AI_GATEWAY_URL}
  AI_GATEWAY_MODEL: ${AI_GATEWAY_MODEL}
  AI_GATEWAY_API_KEY: ${AI_GATEWAY_API_KEY}
  AI_GATEWAY_MCP_SERVER: ${AI_GATEWAY_MCP_SERVER}
```

Set them from your shell:

```bash title="Bash"
azd env set AI_GATEWAY_URL "$AI_GATEWAY_URL"
azd env set AI_GATEWAY_MODEL "$AI_GATEWAY_MODEL"
azd env set AI_GATEWAY_API_KEY "$AI_GATEWAY_API_KEY"
azd env set AI_GATEWAY_MCP_SERVER learn
```

```powershell title="PowerShell"
azd env set AI_GATEWAY_URL $env:AI_GATEWAY_URL
azd env set AI_GATEWAY_MODEL $env:AI_GATEWAY_MODEL
azd env set AI_GATEWAY_API_KEY $env:AI_GATEWAY_API_KEY
azd env set AI_GATEWAY_MCP_SERVER learn
```

azd keeps the values in `.azure/aigw-lab16/.env`, which Git ignores, and passes them to the agent locally and in
Foundry. Anyone who can read the agent's definition in Foundry can also read the key; see
[Go further](#go-further) for keyless options.

<!-- /steps -->

## Read the agent

[`main.py`](infra/src/gateway-agent/main.py) is the whole agent. The model client and the MCP tool are the only
places it talks to the network, and both point at the gateway:

```python
client = OpenAIChatClient(
    model=model,
    base_url=f"{gateway_url}/default/models/openai/v1/",
    api_key=api_key,
)

tools = MCPStreamableHTTPTool(
    name="gateway-tools",
    url=f"{gateway_url}/default/toolservers/{mcp_server}/mcp",
    static_headers={"api-key": api_key},
    approval_mode="never_require",
    load_prompts=False,
    request_timeout=60,
)
```

`ResponsesHostServer` serves the agent on the Responses protocol at port 8088, the same way locally and in Foundry.
The agent sets `store` to `false` on its model calls, because the hosting server already keeps the conversation
history. Tool approval is off because the Learn tools are read-only.

<!-- include: infra/src/gateway-agent/main.py -->

On GitHub, open [main.py](infra/src/gateway-agent/main.py) and [azure.yaml](infra/azure.yaml).

## Run the agent locally

<!-- steps -->

### Start the agent

From the `infra` folder:

```bash
azd ai agent run
```

azd creates a virtual environment, installs `requirements.txt`, starts the agent on `http://localhost:8088`, and
opens Agent Inspector, where you can chat with the agent and see its tool calls. Add `--no-client` to skip Agent
Inspector.

### Ask a question

In a second terminal, from the same folder:

```bash
azd ai agent invoke --local "Which Learn page explains Azure API Management key concepts? One sentence and the URL."
```

Expected output: an answer that cites a `learn.microsoft.com` URL, for example:

```text
[local] The Learn page "What is Azure API Management?" explains its key concepts.
URL: https://learn.microsoft.com/azure/api-management/api-management-key-concepts
```

Behind that answer, the agent made a model call that asked for a tool, one or more Learn tool calls, and a model
call that wrote the answer, all through the gateway. Stop the agent with **Ctrl+C**.

<!-- /steps -->

> **Checkpoint**
> The local agent answers with a Microsoft Learn URL.

## Deploy to Foundry

<!-- steps -->

### Provision and deploy

```bash
azd up
```

azd asks for a subscription if the environment doesn't have one. Then it creates `rg-aigw-lab16` with a Foundry
resource and a project that has hosted agents enabled, uploads `src/gateway-agent` as a code package, and creates the
hosted agent. Foundry builds it from `requirements.txt`. It takes about five minutes, and ends with:

```text
SUCCESS: Your application was deployed to Azure in 2 minutes 31 seconds.
```

### Invoke the hosted agent

```bash
azd ai agent invoke gateway-agent "Which Learn page explains Azure API Management key concepts? One sentence and the URL."
```

Expected output: the same kind of answer, now from Foundry. The first call can take 10 to 20 seconds while the
agent starts.

```text
Agent:        gateway-agent (remote)
...
[gateway-agent] The Learn page titled "What is Azure API Management?" explains Azure API Management key concepts.
URL: https://learn.microsoft.com/azure/api-management/api-management-key-concepts
```

azd keeps the conversation, so a second `invoke`, such as `"Shorten that to ten words."`, continues it. Add
`--new-conversation` to start over.

### Find the agent in Foundry

```bash
azd ai agent show gateway-agent
```

The output shows **Status** `active`, the agent's own identity, its Responses endpoint, and a **Playground URL**.
Open that URL to chat with the agent in the Foundry portal.

<!-- /steps -->

> **Checkpoint**
> `azd ai agent show gateway-agent` reports `active`, and `azd ai agent invoke` returns an answer with a Learn URL.

## See the agent in Monitoring

The `hosted-agent` key is a caller identity of its own. With monitoring set up as in
[Monitor usage, cost, and traces](../13-monitoring/README.md), invoke the agent a few times, wait a few minutes, then
open **Monitoring** in the portal:

- **Models**: use the **All caller identities** filter to select `hosted-agent`. You see the agent's calls, tokens,
  and estimated cost for your alias.
- **Tools**: the `learn` tool server under **Usage by tool server**, with the tools the agent called under
  **Top tools within tool servers**.
- **Traces**: one row per model or tool call, with the policies the gateway applied.

## Cap the agent's tokens

Give the agent's alias a strict token limit counted per caller identity, then watch the gateway enforce it without
any change to the agent. Pick one track.

<!-- track: portal | Portal -->

### Add the token limit

1. Select **Policies** › **Add policy**.
2. On **Type**, select **Token rate limit**.
3. On **Scope**, select **Individual assets** and pick your alias.
4. On **Configure**, set **Time period** to **Per minute**, **Allowed tokens** to `1000`, and
   **Counter dimensions** to **Caller identity**, then select **Create**.

<!-- track: cli | Azure CLI -->

### Add the token limit

Find the alias resource by its alias name, which works even when a portal-created alias contains `/`. A `PATCH` of
`properties.policies` replaces the whole array, so these commands keep the alias's other policies:

```bash title="Bash"
ALIAS_ID="$(az rest --url "$WS/aliases?$API" \
  --query "value[?properties.aliasName=='$AI_GATEWAY_MODEL'].id | [0]" -o tsv)"
ALIAS_URL="https://management.azure.com$ALIAS_ID"
az rest --url "$ALIAS_URL?$API" -o json \
  | jq -c '{properties:{policies:([(.properties.policies // [])[] | select(.type != "tokenLimit") | del(.scope)] + [{type:"tokenLimit",period:"minute",count:1000,counterKey:["identity"]}])}}' > policies.json
az rest --method patch --url "$ALIAS_URL?$API" --body @policies.json --query properties.policies
```

```powershell title="PowerShell"
$ALIAS_ID = az rest --url "$WS/aliases?$API" `
  --query "value[?properties.aliasName=='$($env:AI_GATEWAY_MODEL)'].id | [0]" -o tsv
$ALIAS_URL = "https://management.azure.com$ALIAS_ID"
$alias = az rest --url "$ALIAS_URL`?$API" -o json | ConvertFrom-Json
$p = @($alias.properties.policies | Where-Object { $_ -and $_.type -ne 'tokenLimit' } |
  Select-Object * -ExcludeProperty scope) +
  @(@{ type = 'tokenLimit'; period = 'minute'; count = 1000; counterKey = @('identity') })
@{ properties = @{ policies = $p } } | ConvertTo-Json -Depth 10 -Compress | Set-Content policies.json
az rest --method patch --url "$ALIAS_URL`?$API" --body "@policies.json" --query properties.policies
```

<!-- /tracks -->

<!-- steps -->

### Trigger the limit

Wait about 30 seconds for the policy to apply, then invoke the hosted agent twice:

```bash
azd ai agent invoke gateway-agent --new-conversation "Summarize Azure API Management in three sentences with Learn links."
azd ai agent invoke gateway-agent --new-conversation "Summarize Azure API Management in three sentences with Learn links."
```

The gateway counts tokens when a call completes, so the first invoke usually succeeds and uses well over 1,000
tokens, because Learn tool results are long. The second invoke fails, and the agent reports the gateway's `429`:

```text
ERROR: agent failed (server_error): (... Error code: 429 - {'statusCode': 429, 'message': 'Token limit is exceeded. Try again in <n> seconds.'} ...)
```

The counter belongs to the `hosted-agent` key. Your other apps, with their own keys, keep their full allowance on
the same alias. For more on limits, see
[Throttle tokens per caller with token limits](../06-token-limits/README.md).

### Remove the limit

In the portal, select **Policies**, open the **Token rate limit** you created for your alias, and delete it. With
the CLI, remove the `tokenLimit` policy the same way you added it:

```bash title="Bash"
az rest --url "$ALIAS_URL?$API" -o json \
  | jq -c '{properties:{policies:[(.properties.policies // [])[] | select(.type != "tokenLimit") | del(.scope)]}}' > policies.json
az rest --method patch --url "$ALIAS_URL?$API" --body @policies.json --query properties.policies
rm policies.json
```

```powershell title="PowerShell"
$alias = az rest --url "$ALIAS_URL`?$API" -o json | ConvertFrom-Json
$p = @($alias.properties.policies | Where-Object { $_ -and $_.type -ne 'tokenLimit' } |
  Select-Object * -ExcludeProperty scope)
@{ properties = @{ policies = $p } } | ConvertTo-Json -Depth 10 -Compress | Set-Content policies.json
az rest --method patch --url "$ALIAS_URL`?$API" --body "@policies.json" --query properties.policies
Remove-Item policies.json
```

If your alias had its own token limit before this lab, the CLI commands remove it too: add it back with the count
it had.

<!-- /steps -->

## Verify

> **Verify**
> - `azd ai agent invoke --local` and `azd ai agent invoke` both return an answer with a Microsoft Learn URL.
> - The Foundry project has no model deployments, yet the agent answers: its model calls go through the gateway.
> - With the token limit in place, the agent got `429` from the gateway without any code change.
> - With monitoring set up, **Monitoring** › **Models** shows calls from the `hosted-agent` caller identity.

## Go further

- **Go keyless.** The hosted agent has its own Microsoft Entra identity, shown by `azd ai agent show gateway-agent`.
  Give it the **AI Gateway User** role, which covers models and MCP tools, as in
  [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md). Then send a Microsoft Entra token from
  `DefaultAzureCredential` to both endpoints instead of the key.
- **Keep the key out of the agent definition.** Store it in Azure Key Vault and read it at startup with the agent's
  identity, instead of passing it as an environment variable.
- **Lock down egress.** Foundry can restrict where a hosted agent may connect. Allow only your gateway's host name,
  so the gateway is the agent's only way out. See the
  [egress control sample](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses/18-egress-control).
- **Use another framework.** Swap the agent's internals for the OpenAI Agents SDK or LangGraph, as in
  [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md). The gateway settings stay the
  same.
- **Charge the agent back.** Attribute its tokens and estimated cost with
  [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md).

## Clean up

Delete the Foundry resource group and the hosted agent. `--purge` also purges the soft-deleted Foundry resource so
you can reuse its name:

```bash
azd down --purge
```

Then delete the `hosted-agent` key: in **Access** › **Keys**, select **…** (**More actions**) on its row and delete
it, or run `az rest --method delete --url "$GW/apiKeys/hosted-agent?$API"`. Delete the `.azure` folder in `infra` if
you no longer need the environment, because it holds the key value.

Your gateway, its alias, and the `learn` MCP server aren't affected.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `400` "Specify either an API key or an Authorization header, not both" | The code sends the key as the SDK's API key and also in an `api-key` header | Pass the key only as the SDK's `api_key`, and remove the `api-key` default header from the model client. |
| `401` from the MCP endpoint | The key went in `Authorization: Bearer` | The MCP endpoint takes keys only in the `api-key` header, as in `main.py`. |
| `401` from the model endpoint | The key is wrong, suspended, or deleted | Check `hosted-agent` in **Access** › **Keys**, load the value again, run `azd env set AI_GATEWAY_API_KEY`, then `azd deploy`. |
| `404` from the model endpoint | `AI_GATEWAY_MODEL` doesn't match an alias | Copy the alias exactly from the model's **Aliases** tab, run `azd env set AI_GATEWAY_MODEL`, then `azd deploy`. |
| `429` "Token limit is exceeded" | A token limit on the alias, such as the one from this lab | Wait for the time in the message, or remove the policy. |
| `429` from tool calls | A request rate limit on the `learn` server, for example from [Control which tools agents can call](../05-mcp-tool-controls/README.md) | Wait for the `Retry-After` time, or remove the policy from the MCP server. |
| `RuntimeError: Set AI_GATEWAY_URL` | An azd environment value is missing | Run `azd env set` for the missing value, then `azd ai agent run` or `azd deploy`. |
| The hosted agent still uses an old value | Foundry reads environment variables when the agent version is created | Run `azd deploy` after every `azd env set`. |
| `[CodeError] [tool.poetry] section not found` during deployment | A `pyproject.toml` without a lock file was added to `src/gateway-agent` | Keep `requirements.txt` as the dependency file, or commit a `uv.lock` next to `pyproject.toml`. |
| `azd ai agent run` can't download packages, with a certificate error | A proxy on your network inspects TLS traffic | Set `UV_SYSTEM_CERTS=true` (`UV_NATIVE_TLS=true` in older uv versions) so uv trusts your system certificates, then run it again. |

## Next steps

- [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md): wire other frameworks to the
  gateway the same way.
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): replace the key with the agent's
  identity.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): tour the dashboards in depth.
- Docs: [Connect Microsoft Foundry to AI Gateway](https://ai.gateway.azure.com/docs/foundry) and
  [Deploy a hosted agent](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent)
