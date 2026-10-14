---
title: Deploy a Foundry hosted agent behind AI Gateway
summary: Deploy the Daily Repo Digest sample with azd. A Microsoft Agent Framework agent runs in Foundry Hosted Agents, and its model calls and read-only GitHub MCP calls go through AI Gateway. Then run it locally, schedule it, watch it in Monitoring, and cap its tokens.
category: agents
level: Intermediate
duration: 45
tracks: [iac, code]
order: 16
illustration: diagrams/hosted-agent.svg
tags: [Foundry Hosted Agents, azd, Microsoft Agent Framework, Foundry Toolbox, GitHub MCP, routines, Bicep]
objectives:
  - Deploy the Daily Repo Digest sample with azd up and explain what each Bicep module creates
  - Run the agent locally and invoke the hosted agent and its scheduled routine
  - Trace the agent's model and GitHub MCP calls in AI Gateway Monitoring
  - Cap the agent's token use with a gateway policy, without changing its code
prereqs:
  - 01-provision-gateway
---

# Deploy a Foundry hosted agent behind AI Gateway

Your team wants an agent that posts a daily digest of a GitHub repository: new pull requests, issues, and failed
workflow runs. Foundry Hosted Agents can run and schedule it, but the platform team needs every model call and every
GitHub call to be governed and visible. In this lab you deploy the reference sample, where the agent never talks to a
model or to GitHub directly: both paths go through AI Gateway.

![A Foundry hosted agent calls models and GitHub MCP tools through AI Gateway](../assets/diagrams/hosted-agent.svg "Foundry runs the agent. AI Gateway governs its model calls and its GitHub MCP calls.")

## Before you begin

- Read [Provision your AI Gateway](../01-provision-gateway/README.md). The sample creates its **own** gateway, in its
  own resource group, so the gateway from that lab stays untouched.
- An Azure subscription where you can create resource groups, Foundry resources, and role assignments, for example
  **Owner** on the subscription. The template runs at subscription scope.
- A GitHub account.
- These tools, as the sample README requires:
  - Python 3.13 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/)
  - [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) (azd) 1.27.0
    or later
  - [GitHub CLI](https://cli.github.com/) (gh), signed in to GitHub
  - [PowerShell 7](https://learn.microsoft.com/powershell/scripting/install/installing-powershell) on Windows
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), because the sample's hooks call `az`.
  The CLI tip in the token limit task also uses the `aigateway` extension from lab 01.
- Sign in with `azd auth login` and `az login` to the same tenant.

> [!WARNING]
> The sample creates billable resources, including Foundry model deployments, a Premium container registry, and Log
> Analytics workspaces. Run [Clean up](#clean-up) when you're done.

## How it works

The sample is the [Daily Repo Digest](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway).
A Microsoft Agent Framework agent runs in Foundry Hosted Agents and answers on a Responses endpoint. A Foundry routine
invokes it every day at 9 AM Pacific time.

The agent has two outbound paths, and both end at AI Gateway:

- **Models.** The agent's OpenAI client points at the gateway's model endpoint with the gateway key in the
  `Api-Key` header. The gateway calls the Foundry deployments with its managed identity, because the model account
  has local authentication disabled.
- **Tools.** The agent gets its tools from a Foundry Toolbox. The Toolbox connects to the gateway's `github` MCP
  server with the same key. The gateway calls the GitHub MCP server with the GitHub credential you provide, limited
  to three read-only tools.

| Piece | Name in the sample | Owner |
|---|---|---|
| Models | `gpt-latest`, which the agent calls, and `gpt-mini-latest` | AI Gateway |
| MCP server | `github`, at `/default/toolservers/github/mcp` | AI Gateway |
| Runtime key | `default` ("Default hosted agent key") | AI Gateway |
| Toolbox and its connection | `repo-digest-tools`, connection `aigw-github` | Foundry |
| Hosted agent | `simple-foundry-hosted-agent-python-aigateway` | Foundry |
| Routine | `daily-repo-digest` | Foundry |

Foundry runs the agent. AI Gateway decides what the agent may call and records every call.

## Deploy the sample

<!-- steps -->

### Clone the sample and install the extension

```bash
gh repo clone Azure-Samples/simple-foundry-hosted-agent-python-aigateway
cd simple-foundry-hosted-agent-python-aigateway

azd ext install microsoft.foundry
```

### Check your GitHub sign-in

The deployment reuses your GitHub CLI sign-in to give the gateway's `github` MCP server a GitHub credential.

```bash
gh auth status --hostname github.com
```

If you aren't signed in, run `gh auth login --hostname github.com`. If you use more than one GitHub account, set
`GITHUB_MCP_GH_USER` to the login to use before you deploy.

> [!IMPORTANT]
> Your CLI sign-in is account-wide, and the hook stores the credential in the gateway's MCP server. For anything beyond
> a quick test, the sample strongly recommends a read-only, repository-scoped fine-grained token. Follow
> [Set up the GitHub credential](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/IMPLEMENTATION_NOTES.md#tighten-the-github-credential-to-least-privilege)
> in the sample.

### Provision and deploy

```bash
azd up
uv sync
```

`azd up` asks for an environment name, a subscription, and a location. The location must be one where Foundry
routines are available: `eastus`, `eastus2`, `westus`, `northcentralus`, `swedencentral`, or `japaneast`. The gateway
goes to `eastus2` unless you change `aiGatewayLocation` in `infra/main.bicep`.

Near the end, the postprovision hook calls `gpt-latest` through the gateway and waits until it answers. Expected
output includes:

```text
AI Gateway model route is ready.
Connecting Foundry Toolbox to the AI Gateway GitHub ToolServer.
AI Gateway setup complete. Bicep owns Azure resources; this hook injects the GitHub credential, connects Foundry Toolbox to AI Gateway, and saves the runtime key.
```

After provisioning, azd builds the agent image remotely and deploys the hosted agent.

<!-- /steps -->

> **Checkpoint**
> `azd up` finished without errors. In the [AI Gateway portal](https://ai.gateway.azure.com), the gateway switcher
> lists `aigw-<token>`, **Models** lists two models from the `foundry` provider, and **MCP servers** lists
> **GitHub repository digest** (`github`).

## Understand what you deployed

Pick the part you want to study: the **Bicep** track walks through the infrastructure, and the **Code** track walks
through the agent. Both read the files in the sample you cloned.

<!-- track: iac | Bicep -->

### Find the three resource groups

[`infra/main.bicep`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/infra/main.bicep)
runs at subscription scope and creates three resource groups, one module each:

| Resource group | Module | Contents |
|---|---|---|
| `rg-<env>-<token>-gateway` | `infra/ai-gateway/main.bicep` | AI Gateway, its connector namespace, model provider and models, runtime key, Log Analytics and Application Insights |
| `rg-<env>-<token>-foundrymodels` | `infra/foundry-models/main.bicep` | A Foundry account with only the model deployments, local authentication disabled |
| `rg-<env>-<token>-foundryagents` | `infra/foundry-agents/main.bicep` | The Foundry project, storage, container registry, the agent's own monitoring, connections, and role assignments |

The only runtime permission across groups is the gateway's system-assigned identity holding the **Foundry User**
role on the model account. Keeping models in their own account means the agent has no direct route to them.

### Read the model registrations

The gateway module adds a `Foundry` model provider named `foundry` that authenticates with the gateway's managed
identity, then one model per deployment: `gpt-latest` (`gpt-5.6-sol`, capacity 20) and `gpt-mini-latest`
(`gpt-5.4-mini`, capacity 200). Each model's display name is the catalog model name. Each model gets a token limit
of capacity × 1,000 tokens per minute for each caller identity, so 20,000 for `gpt-latest`:

```bicep
policies: model.?policies ?? [
  {
    type: 'tokenLimit'
    period: 'minute'
    count: model.?tokenLimit ?? 10000
    counterKey: 'Identity'
  }
]
```

The deployment name, not the catalog model name, is the `model` value the agent sends. Both models publish
`/openai/v1/chat/completions` and `/openai/v1/responses`.

### Read the monitoring resources

The gateway module creates a Log Analytics workspace, a workspace-based Application Insights component named
`<gateway>-insights`, and a telemetry exporter:

```bicep
resource telemetryExporter 'Microsoft.ApiManagement/service/workspaces/telemetryExporters@2025-09-01-preview' = if (enableMonitoring && deployApimGatewayViaBicep) {
  parent: defaultWorkspace
  name: telemetryExporterName
  properties: {
    kind: 'applicationInsights'
    payloadCapture: false
    applicationInsights: {
      connectionString: appInsights!.properties.ConnectionString
      resourceId: appInsights!.id
    }
  }
}
```

The portal now treats exporters of kind `applicationInsights` as legacy. You reconnect it in
[Observe the agent in AI Gateway](#observe-the-agent-in-ai-gateway). The agent has a separate Application Insights
component in the Foundry resource group, so each platform keeps its own telemetry.

### Read the postprovision hook

Bicep creates the Azure resources. The postprovision hook,
[`infra/scripts/configure-ai-gateway.sh`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/infra/scripts/configure-ai-gateway.sh),
does the parts that need secrets or Foundry data-plane calls:

1. Creates or updates the `github` MCP server, pointing at `https://api.githubcopilot.com/mcp/` with your GitHub
   credential, `failureMode: failClosed`, and the headers `X-MCP-Readonly: true` and
   `X-MCP-Tools: list_pull_requests,list_issues,actions_list`. The agent can only read, and only those three tools.
2. Reads the `default` runtime key and checks that `gpt-latest` answers through the gateway.
3. Saves the endpoint, alias names, key, and repository in the azd environment, so `azd deploy` passes them to
   the hosted agent.
4. Creates the Foundry connection `aigw-github`, which sends the gateway key in the `Api-Key` header, and the
   Toolbox `repo-digest-tools` that uses it.

The GitHub credential goes only into the gateway's MCP server. It isn't written to Bicep outputs, the azd
environment, `.env`, or the agent's environment variables.

<!-- track: code | Code -->

### Read the model client

[`repo_digest_agent.py`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/repo_digest_agent.py)
builds the agent. Its model client points at the gateway, not at Foundry:

```python
return OpenAIChatClient(
    model=os.environ.get("AZURE_AI_GATEWAY_MODEL", DEFAULT_GATEWAY_MODEL),
    base_url=gateway_endpoint + "/default/models/openai/v1/",
    # This OpenAI transport placeholder suppresses its Bearer header.
    api_key=OPENAI_NO_BEARER_AUTH,
    default_headers={"Api-Key": gateway_key},
)
```

`DEFAULT_GATEWAY_MODEL` is `gpt-latest`. The gateway key goes in the `Api-Key` header, not in
`Authorization: Bearer`. This is the same pattern as
[Connect agent frameworks to models and tools](../15-agent-frameworks/README.md).

### Read the tool wiring

The agent gets its tools from the Foundry Toolbox, authenticated with Microsoft Entra ID:

```python
def _github_toolbox() -> FoundryToolbox:
    return FoundryToolbox(
        DefaultAzureCredential(
            exclude_managed_identity_credential=not bool(
                os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT")
            )
        ),
        timeout=60,
    )
```

The Toolbox has one MCP source, declared in
[`toolbox.yaml`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/toolbox.yaml):

```yaml
tools:
  - type: mcp
    server_label: aigw-github
    project_connection_id: aigw-github
    require_approval: "never"
```

The `aigw-github` connection targets the gateway's `/default/toolservers/github/mcp` endpoint. So the tool path is
agent → Foundry Toolbox → AI Gateway → GitHub MCP. Approval is off because all three tools are read-only and the
scheduled routine can't stop for approval.
[`github_mcp_middleware.py`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/github_mcp_middleware.py)
bounds tool arguments and trims results before the follow-up model call, and the agent caps each response at 2,048
output tokens.

### Read the host and the routine

[`main.py`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/main.py) serves
the agent with the Agent Framework hosting server, which exposes the Responses protocol:

```python
def main() -> None:
    ResponsesHostServer(build_agent()).run()
```

[`azure.yaml`](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/azure.yaml)
declares the hosted agent (0.5 CPU, 1 GiB, built remotely from the `Dockerfile`), passes the `AZURE_AI_GATEWAY_*`,
`TOOLBOX_*`, and `GITHUB_REPOSITORY` values to it, and declares the `daily-repo-digest` routine with cron
`0 9 * * *` in `America/Los_Angeles`.

<!-- /tracks -->

## Run the agent

<!-- steps -->

### Run it locally

Create a local `.env` from the azd environment, then start the agent:

```bash title="Bash"
./scripts/create-dev-env.sh
uv run python main.py
```

```powershell title="PowerShell"
pwsh ./scripts/create-dev-env.ps1
uv run python main.py
```

The script writes only the values the agent needs, restricts the file to your user, and doesn't print the key. The
agent listens on `http://localhost:8088`. Locally, `DefaultAzureCredential` uses your Azure sign-in to reach the
Toolbox.

### Ask for a digest

In a second terminal, from the same folder, send a request to the local Responses endpoint:

```bash
curl -sS -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Create a concise daily repo digest for microsoft/agent-framework.", "stream": false}'
```

Or use the console client. Press Enter to send the default prompt, and type `exit` to quit:

```bash
uv run chat.py
```

Expected output: a digest with a one-line summary, pull requests and issues updated in the last 24 hours, workflow
failures, and suggested next actions. Sections with no items say "None found". Stop the local agent with **Ctrl+C**
when you're done.

### Invoke the hosted agent

Call the deployed agent in Foundry:

```bash
azd ai agent invoke "Create a concise daily repo digest for microsoft/agent-framework."
```

Then run the scheduled routine now, instead of waiting for 9 AM Pacific time:

```bash
azd ai routine dispatch daily-repo-digest
```

### Change the default repository

The agent uses `GITHUB_REPOSITORY` when a request doesn't name a repository. The default is
`microsoft/agent-framework`.

```bash
azd env set GITHUB_REPOSITORY "owner/repo"
azd provision
```

Replace `owner/repo` with a repository your GitHub credential can read. The routine keeps its explicit
`microsoft/agent-framework` prompt. To use the new value locally, run `./scripts/create-dev-env.sh --force`.

<!-- /steps -->

> **Checkpoint**
> The local agent and the hosted agent both return a digest for `microsoft/agent-framework`, and the routine dispatch
> completes without an error.

## Observe the agent in AI Gateway

<!-- steps -->

### Reconnect the gateway's telemetry

In the [AI Gateway portal](https://ai.gateway.azure.com), select the sample's gateway (`aigw-<token>`), then
**Monitoring** › **Settings**. Because the sample's exporter has kind `applicationInsights`, **Settings** says the
legacy exporter no longer activates OTLP signals.

1. Select **Settings** › **General** › **Disable monitoring**.
2. Select **Configure telemetry**. On **Destination**, select **Existing Azure Application Insights resource** and
   pick `aigw-<token>-insights`. Select **Next**.
3. On **Authentication**, leave **Include recommended token claims in telemetry** selected and select **Next**.
4. On **Review and apply**, select **Apply**.

This is the same reconnection as in [Monitor usage, cost, and traces](../13-monitoring/README.md). If you run
`azd provision` again, the template declares the legacy exporter again, so check **Settings** afterwards.

### Generate and find agent traffic

Invoke the hosted agent or dispatch the routine once more, wait a few minutes, then open **Monitoring**:

- **Overview**: **Model calls** and **Tool calls** both grew.
- **Models**: the model behind `gpt-latest`, with its calls, tokens, and estimated cost. The caller identity is
  the sample's `default` key.
- **Tools**: the GitHub tool server under **Usage by tool server**, with the GitHub tools the agent called under
  **Top tools within tool servers**.
- **Traces**: one row per model or tool call, with the policies the gateway applied.

Each digest makes at least one model call that asks for tools, the GitHub tool calls, and a follow-up model call that
writes the digest.

<!-- /steps -->

> **Checkpoint**
> **Monitoring** › **Tools** lists the GitHub tool server, and **Models** shows calls to the model behind
> `gpt-latest` from the sample's key.

## Cap the agent's tokens

The sample already gives `gpt-latest` a token limit of 20,000 tokens per minute for each caller identity. Add a much
stricter limit for the alias the agent calls, then watch the gateway enforce it without any change to the agent.

<!-- steps -->

### Set your variables

```bash title="Bash"
export RG="$(azd env get-value AI_GATEWAY_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export AI_GATEWAY_URL="$(azd env get-value AZURE_AI_GATEWAY_ENDPOINT)"
export AI_GATEWAY_API_KEY="$(azd env get-value AZURE_AI_GATEWAY_API_KEY)"
```

```powershell title="PowerShell"
$RG = azd env get-value AI_GATEWAY_RESOURCE_GROUP
$GATEWAY = azd env get-value AI_GATEWAY_NAME
$env:AI_GATEWAY_URL = azd env get-value AZURE_AI_GATEWAY_ENDPOINT
$env:AI_GATEWAY_API_KEY = azd env get-value AZURE_AI_GATEWAY_API_KEY
```

### Add a token limit for the agent's alias

In the portal, select **Policies** › **Add policy**. On **Type**, select **Token rate limit**. On **Scope**, select
**Individual assets** and pick `gpt-latest`, the name the agent sends as its model. On **Configure**, set **Time
period** to **Per minute**, **Allowed tokens** to `1000`, and **Counter dimensions** to **Caller identity**, then
select **Create**.

Every applicable limit is checked, so the stricter one wins. For the details, see
[Throttle tokens per caller with token limits](../06-token-limits/README.md).

> [!TIP]
> To change the model's own limit from the CLI instead, run
> `az aigateway model policy set-token-limit -g "$RG" --gateway-name "$GATEWAY" --provider-name foundry -n gpt-latest --token-limit 1000`.
> Bicep declares that limit, so the next `azd provision` sets it back to capacity × 1,000. To keep a different
> value, change `tokenLimit` in `infra/main.bicep`.

### Trigger the limit

Invoke the agent, then immediately send one request with the same key:

```bash title="Bash"
azd ai agent invoke "Create a concise daily repo digest for microsoft/agent-framework."

curl -sS -o /dev/null -w '%{http_code}\n' -X POST "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "Api-Key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-latest", "messages": [{"role": "user", "content": "Reply with exactly one word: ok"}], "max_completion_tokens": 128}'
```

```powershell title="PowerShell"
azd ai agent invoke "Create a concise daily repo digest for microsoft/agent-framework."

$body = @{
  model = "gpt-latest"
  messages = @(@{ role = "user"; content = "Reply with exactly one word: ok" })
  max_completion_tokens = 128
} | ConvertTo-Json -Depth 5
(Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "Api-Key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body `
  -SkipHttpErrorCheck).StatusCode
```

Expected output: `429`. One digest uses more than 1,000 tokens, and the agent and your request share the `default`
key, so they share one counter. If you see `200`, the minute had already rolled over: invoke the agent and send the
request again. The agent's own follow-up model call can be throttled too, whatever its code does.

### Find the blocked calls

After a few minutes, open **Monitoring** › **Policies**. **Token rate limit** shows **Blocked requests**. In
**Traces**, the blocked calls have the token limit under **Applied policies**.

### Remove the stricter limit

Select **Policies**, open the **Token rate limit** you created for `gpt-latest`, and delete it. The model's
20,000-token limit from Bicep stays. If you used the CLI tip, run `azd provision` or `set-token-limit` with
`--token-limit 20000` to restore it.

<!-- /steps -->

## Verify

> **Verify**
> - `azd ai agent invoke` returns a digest from the hosted agent.
> - **Monitoring** shows the agent's `gpt-latest` calls and its `github` tool calls, both from the `default` key.
> - With the stricter token limit in place, a request with the agent's key got `429`, and **Monitoring** ›
>   **Policies** counted the blocked requests.

## Go further

- **Give the agent its own key.** The agent and the Toolbox connection share the `default` key, so anyone else
  using that key shares its limits. Issue a dedicated key, as in
  [Issue and rotate runtime API keys](../10-api-keys/README.md), and the agent's usage and limits stay separate.
- **Use .NET.** The [.NET sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-dotnet-aigateway)
  deploys the same digest with .NET 10 and Microsoft Agent Framework. It needs the .NET SDK 10.0.302 or later.
- **Narrow the tools further.** Review the `github` server's tool controls with
  [Control which tools agents can call](../05-mcp-tool-controls/README.md).
- **Charge the agent back.** Attribute its tokens and estimated cost with
  [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md).

## Clean up

Delete everything the sample created, including its gateway, model deployments, and the agent:

```bash
azd down --purge
```

`--purge` also purges soft-deleted resources so you can reuse the names. The sample's postdown hook purges the
soft-deleted gateway and waits for its identity cleanup. Delete your local `.env`, because it holds the gateway key.

The gateway from [Provision your AI Gateway](../01-provision-gateway/README.md) isn't affected.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `azd up` fails and leaves a failed AI Gateway, after an activation or managed identity conflict | A transient provisioning failure | Run `azd up` again. The preprovision hook deletes only the failed gateway that belongs to this environment, purges it, and waits for identity cleanup. If its wait expires, follow the retry guidance it prints. |
| The hook says GitHub authentication is required | GitHub CLI isn't signed in | Run `gh auth login --hostname github.com`. In CI, provide `GH_TOKEN`. Then run `azd provision`. |
| `403 Forbidden` or empty results from the GitHub tools | The GitHub credential can't read the repository | Create a read-only fine-grained token as the sample's [credential guide](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/blob/main/IMPLEMENTATION_NOTES.md#tighten-the-github-credential-to-least-privilege) describes, then run `azd provision`. |
| `AI Gateway model route failed with HTTP …` during provisioning | The gateway or model route wasn't ready within the hook's retries | Run `azd provision` again. If it persists, check that the `gpt-latest` deployment exists in the model resource group. |
| `create-dev-env.sh` says `.env already exists` | The script never overwrites by default | Run `./scripts/create-dev-env.sh --force`. |
| The Monitoring dashboard is empty | The sample's exporter is the legacy kind | Reconnect the telemetry as in [Observe the agent in AI Gateway](#observe-the-agent-in-ai-gateway), then send new traffic. |

## Next steps

- [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md): wire other frameworks to the
  gateway the same way.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): design limits for agents and apps.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): tour the dashboards in depth.
- Docs: [Run a sample app](https://ai.gateway.azure.com/docs/quickstarts/sample) and
  [Connect Microsoft Foundry to AI Gateway](https://ai.gateway.azure.com/docs/foundry)
