---
title: Protect tool calls with Agent 365 threat protection
summary: Have Microsoft Defender and Microsoft Purview evaluate every tool call on an MCP server, before the tool runs, after it returns, or both, and see how a fail-closed denial reaches the caller.
category: production
level: Advanced
duration: 30
tracks: [portal]
order: 19
status: emerging
illustration: diagrams/threat-protection.svg
tags: [Agent 365, tool threat protection, Microsoft Defender, Microsoft Purview, prompt injection, MCP, on-behalf-of, Entra ID]
objectives:
  - Explain what the before-invocation and after-invocation stages evaluate and what each one can and can't prevent
  - Add an Agent 365 tool threat protection policy to an MCP server in the AI Gateway portal
  - Call a protected tool with a delegated Microsoft Entra ID token and read the result
  - Recognize the documented denial codes and why a key-only call fails closed
prereqs:
  - 04-federate-mcp-tools
  - 11-entra-rbac
---

# Protect tool calls with Agent 365 threat protection

Your agents call tools that read web pages, tickets, and documents, and any of that content can carry a prompt
injection or leak sensitive data back to the model. Content filters on the model don't see what goes into a tool
or what comes out of it. In this lab you add **Agent 365 tool threat protection** to an MCP server, so Microsoft
Defender and Microsoft Purview evaluate each tool request, each tool result, or both, and the gateway only lets
allowed calls through.

![The gateway sends the tool request and the tool result to Microsoft Defender and Microsoft Purview for an allow decision](../assets/diagrams/threat-protection.svg "The gateway asks for an allow decision before the tool runs, after it returns, or both. Anything other than an allow fails closed.")

<!-- widget: request-lifecycle -->

## Before you begin

- Complete [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md). This lab protects the
  `learn` MCP server from that lab. Any MCP server in your gateway works.
- Complete [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md). Tool threat protection
  only works for callers that send a **delegated** Microsoft Entra ID bearer token issued for AI Gateway.
- A **Microsoft Defender or Microsoft Purview license** in your tenant.
- Permission to manage policies on the gateway, for example **Contributor** on its resource group, and permission
  to create role assignments if your user doesn't have a data-plane role yet.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login` as a **user** (not a service principal). The CLI snippets call the Azure Resource Manager REST API
  with `az rest`, because the `az aigateway` extension doesn't manage the new `aigateways` resource type yet.
- For the test scripts and the Bash snippets: `curl` and `jq` (Bash) or PowerShell 7 or later.

> [!NOTE]
> Agent 365 tool threat protection is an emerging capability of the AI Gateway tier preview, which is available
> in East US 2 and Sweden Central. Labels and behavior can change; see the
> [release note](https://ai.gateway.azure.com/docs/releases/2026-10-08-tool-threat-protection). AI Gateway itself
> is free during the preview; Defender and Purview are licensed separately.

Set these variables once. The steps and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export MCP_SERVER="learn"                    # the MCP server you protect in this lab

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az resource show -g "$RG" -n "$GATEWAY" --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv)"
export GW="https://management.azure.com$GATEWAY_ID"
export WS="$GW/workspaces/default"
export AI_GATEWAY_URL="https://$(az resource show --ids "$GATEWAY_ID" --query properties.frontend.defaultHostname -o tsv)"
# Paste the runtime key you created in Access › Keys. You use it once to see a key-only call fail closed.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG         = "<resource-group>"
$GATEWAY    = "<gateway>"
$MCP_SERVER = "learn"                        # the MCP server you protect in this lab

$API                = "api-version=2025-09-01-preview"
$GATEWAY_ID         = az resource show -g $RG -n $GATEWAY --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv
$GW                 = "https://management.azure.com$GATEWAY_ID"
$WS                 = "$GW/workspaces/default"
$env:AI_GATEWAY_URL = "https://$(az resource show --ids $GATEWAY_ID --query properties.frontend.defaultHostname -o tsv)"
# Paste the runtime key you created in Access › Keys. You use it once to see a key-only call fail closed.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

## How it works

Tool threat protection is a policy on one MCP server. It covers every tool on that server, whether the server is
backed by remote MCP endpoints, OpenAPI services, or both, and every caller. The gateway first runs its usual
authentication, authorization, and policies. Only requests that pass are sent for evaluation.

For each `tools/call`, the gateway exchanges the caller's delegated token on behalf of the user (OBO) and asks
Microsoft Defender and Microsoft Purview for a verdict on malicious content, prompt injection, and sensitive-data
risks. Discovery and session traffic, such as `initialize`, `tools/list`, and notifications, isn't evaluated.

The evaluation must return a valid **allow**. A denial, timeout, token-exchange failure, malformed verdict, or
unavailable evaluator fails closed: the caller gets a normal tool result over HTTP `200` with `isError: true`, a
denial code, and a correlation ID.

| Stage | What's evaluated | What it prevents | Cost |
|---|---|---|---|
| **Before tool invocation** | The tool name and arguments | The tool never runs, so there are no side effects | One evaluation round trip |
| **After tool invocation** | The tool result, including error results | The result never reaches the agent. The tool **already ran**. | One evaluation round trip |
| **Both** | Both of the above | Requires two allow decisions | Up to two round trips per call |

## Prepare a delegated caller

The policy evaluates each call on behalf of the signed-in user, so you test it with your own user token. Give
your user permission to call tools on the server, then make one call **before** you add the policy. That proves
the token and the role work, so any later failure comes from the policy.

<!-- steps -->

### Grant yourself the AI Gateway Tools User role

In the AI Gateway portal, select **Access**, then **Add role assignments**. Choose the **AI Gateway Tools User**
role, scope it to the `learn` MCP server, search for your user, and select **Review + assign**. The
[Entra ID lab](../11-entra-rbac/README.md) walks through this page.

The same assignment with the Azure CLI:

```bash
az role assignment create \
  --assignee-object-id "$(az ad signed-in-user show --query id -o tsv)" \
  --assignee-principal-type User \
  --role "dce03f8d-857f-4e40-a90d-67770fa6ecd2" \
  --scope "$GATEWAY_ID/workspaces/default/toolServers/$MCP_SERVER"
```

```powershell
az role assignment create `
  --assignee-object-id (az ad signed-in-user show --query id -o tsv) `
  --assignee-principal-type User `
  --role "dce03f8d-857f-4e40-a90d-67770fa6ecd2" `
  --scope "$GATEWAY_ID/workspaces/default/toolServers/$MCP_SERVER"
```

If you already have **AI Gateway User** or **AI Gateway Tools User** at the gateway scope, skip this step. Role
assignments can take several minutes to apply.

### Call a tool with your user token

The script below gets a token for `https://azure-api.net/aigateway` from the Azure CLI, checks that it's a
delegated user token, runs the MCP handshake, and calls the server's search tool with a harmless question.

<!-- include: infra/call-protected-tool.sh -->

On GitHub, open [infra/call-protected-tool.sh](infra/call-protected-tool.sh) or
[infra/call-protected-tool.ps1](infra/call-protected-tool.ps1).

```bash
chmod +x infra/call-protected-tool.sh
./infra/call-protected-tool.sh token "$MCP_SERVER"
```

```powershell
./infra/call-protected-tool.ps1 -Auth token -Server $MCP_SERVER
```

```text title="Expected output"
Delegated token for the signed-in user (scp: ...)
MCP endpoint: https://<gateway>.eastus2-01.ai.gateway.azure.com/default/toolservers/learn/mcp
tools/list: HTTP 200, <n> tools (discovery isn't evaluated)
tools/call: learn_microsoft_docs_search with query: What is Azure API Management?
HTTP status: 200
isError: false (the result was returned)
...
```

The tool names and count depend on your server and can change as the Learn server evolves. If `tools/call` fails with HTTP `401` or `403`, fix the token or
the role before you continue.

<!-- /steps -->

> **Checkpoint**
> A tool call with your delegated token returns a result with `isError: false`.

## Add tool threat protection

You add the policy in the AI Gateway portal. Each MCP server can have only one tool threat protection policy,
and you can't set it at gateway scope or on a single tool.

<!-- steps -->

### Start a new policy

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher.
Select **Policies**, then **Add policy**.

### Choose the policy type

On the **Type** step, under **Security**, select **Agent 365 tool threat protection**. Its card carries the
**MCP server** badge and reads "Evaluate tool calls and results with Microsoft Defender and Microsoft Purview
for threats, prompt injection, and sensitive-data risks." Select **Next**.

![The Add policy wizard on the Type step, with Agent 365 tool threat protection selected under Security](../assets/screens/policy-tool-threat-protection.jpeg "Agent 365 tool threat protection sits in the Security group, next to Content safety and IP filter. It applies to MCP servers only.")

### Select the MCP server

On the **Scope** step, the wizard notes that this policy applies to individual MCP servers. Select the `learn`
MCP server, then select **Next**.

### Choose the evaluation stages

On the **Details** step, the wizard reminds you that Microsoft Entra ID is required for this policy, because the
evaluation runs on behalf of the caller. Select both stages:

- **Before tool invocation: Evaluate the request payload**
- **After tool invocation: Evaluate the tool output**

You must select at least one stage. Then select **Create**.

### Confirm the policy

The new policy appears in the **Policies** overview. The policy is stored on the MCP server, so you can also read
it with a control-plane `GET`:

```bash
az rest --method get --url "$WS/toolServers/$MCP_SERVER?$API" --query "properties.policies"
```

```powershell
az rest --method get --url "$WS/toolServers/${MCP_SERVER}?$API" --query "properties.policies"
```

The list includes an entry with `"type": "toolThreatProtection"`, `"preInvocation": true`, and
`"postInvocation": true`. The service adds `"scope": "resource"` when it returns a policy set on the server.

<!-- /steps -->

> **Checkpoint**
> The `learn` MCP server has one `toolThreatProtection` policy with both stages turned on.

> [!CAUTION]
> A post-invocation denial withholds the result, but it can't undo what the tool already did. The gateway doesn't
> retry or reverse the call. Build agents so they **don't automatically retry** a tool call whose result was
> withheld, especially for tools that write, send, or delete. For those tools, keep **Before tool invocation**
> turned on so a risky request never runs.

## Understand verdicts and failures

The gateway doesn't decide what's risky. Microsoft Defender does, in the policy mode your security team sets in
Microsoft Defender. You can't change that mode at the gateway.

| Defender policy mode | Behavior |
|---|---|
| **Disabled** | A permanent fail-open state. No inspection occurs. |
| **Audit** | Tool calls are logged without blocking. If the service lags or drops out, calls fail open. |
| **Block** | Explicit enforcement that fails closed. Withholding a result after invocation requires Block mode. |

When a call fails closed, the caller sees one of these codes in the result's
`_meta["com.microsoft.azure.ai.gateway/denial"].code`:

| Code | Meaning |
|---|---|
| `ToolEvaluationIdentityRequired` | The request has no usable bearer token, or the gateway can't read the token tenant it needs for the OBO exchange |
| `ToolEvaluationDenied` | The evaluation service denied the request or the result |
| `ToolEvaluationInvalidRequest` | The evaluation input isn't valid |
| `ToolEvaluationRequestTooLarge` | The evaluation input exceeds the supported size |
| `ToolEvaluationUnavailable` | Token exchange or evaluation failed, timed out, returned an invalid verdict, or was unavailable |

A denied call looks like this. The HTTP status is still `200`, so clients must check `result.isError`:

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "isError": true,
    "content": [
      { "type": "text", "text": "Tool 'mcp_tail_logs' requires a validated delegated caller token." }
    ],
    "_meta": {
      "com.microsoft.azure.ai.gateway/denial": {
        "code": "ToolEvaluationIdentityRequired",
        "correlationId": "9f2c1b6e-..."
      }
    }
  }
}
```

> [!TIP]
> Log the `correlationId` with every denial in your agent. It's the value to share when you investigate a
> denial with your security team.

## Verify

<!-- steps -->

### Call the protected tool with your user token

Run the same benign call as before. Allow a few seconds per call, because each enabled stage adds an evaluation
round trip.

```bash
./infra/call-protected-tool.sh token "$MCP_SERVER"
```

```powershell
./infra/call-protected-tool.ps1 -Auth token -Server $MCP_SERVER
```

```text title="Expected output"
...
tools/list: HTTP 200, <n> tools (discovery isn't evaluated)
tools/call: learn_microsoft_docs_search with query: What is Azure API Management?
HTTP status: 200
isError: false (the result was returned)
...
```

A harmless question about Azure is allowed at both stages, so the result comes back as before. If you see
`ToolEvaluationUnavailable` or `ToolEvaluationDenied` instead, see [Troubleshooting](#troubleshooting).

### Call it with a runtime key only

Now call the same tool with the API key and no bearer token. The key still authenticates you to the gateway, so
`initialize` and `tools/list` succeed. The `tools/call` needs an evaluation, and without a delegated token the
gateway can't run one, so it fails closed.

```bash
./infra/call-protected-tool.sh key "$MCP_SERVER"
```

```powershell
./infra/call-protected-tool.ps1 -Auth key -Server $MCP_SERVER
```

```text title="Expected output"
...
tools/list: HTTP 200, <n> tools (discovery isn't evaluated)
tools/call: learn_microsoft_docs_search with query: What is Azure API Management?
HTTP status: 200
isError: true
Denial code: ToolEvaluationIdentityRequired
Correlation ID: <guid>
Tool '...' requires a validated delegated caller token.
```

The denial text can differ. The code is what matters.

### Look for the call in Monitoring

If you set up Application Insights in [Monitor usage, cost, and traces](../13-monitoring/README.md), open
**Monitoring**. The **Tools** tab shows MCP tool executions, and **Traces** shows each request with its policy
steps. Find your calls by time and compare the allowed call with the key-only call.

<!-- /steps -->

> **Checkpoint**
> A delegated call returns its result. A key-only call to the same tool returns `isError: true` with
> `ToolEvaluationIdentityRequired`, while `tools/list` still works.

## Go further

- **Choose stages per server.** Keep **Before tool invocation** on for tools with side effects, such as sending
  mail or changing records. Add **After tool invocation** for tools that return untrusted content, such as web
  pages, tickets, or documents. For read-only tools that only return trusted content, weigh the extra round trip.
- **Move your agents to delegated tokens.** Agents that call tools with runtime keys or app-only tokens, such as a
  managed identity, can't use protected servers. Plan an on-behalf-of flow with the scope
  `https://azure-api.net/aigateway/Data.All` before you protect a server they depend on.
- **Roll out in Audit mode first.** Ask your security team to start Defender in **Audit**, review what it flags,
  and then switch to **Block**. Defender's
  [runtime protection guidance](https://learn.microsoft.com/defender-endpoint/configure-ai-agent-runtime-protection#enable-runtime-protection)
  recommends the same phased rollout, with alerts reviewed in the Microsoft Defender portal.
- **Automate the policy.** The policy is the `toolThreatProtection` entry in the MCP server's
  `properties.policies`, as described in
  [Protect tool calls with Defender and Purview](https://learn.microsoft.com/azure/api-management/ai-gateway-policy-tool-threat).
  A `PATCH` replaces the whole `policies` array, so read the current array first and keep any other policies,
  such as the request rate limits from [Control which tools agents can call](../05-mcp-tool-controls/README.md):

  ```bash title="Bash"
  TS_URL="$WS/toolServers/$MCP_SERVER"
  az rest --url "$TS_URL?$API" --query properties -o json \
    | jq -c '{properties:{policies:([(.policies // [])[] | select(.type != "toolThreatProtection") | del(.scope)]
        + [{type:"toolThreatProtection",preInvocation:true,postInvocation:true}])}}' > policies.json
  az rest --method patch --url "$TS_URL?$API" --body @policies.json --query properties.policies
  rm policies.json
  ```

  ```powershell title="PowerShell"
  $TS_URL = "$WS/toolServers/$MCP_SERVER"
  $p = az rest --url "$TS_URL`?$API" --query properties.policies -o json | ConvertFrom-Json
  $p = @($p | Where-Object { $_ -and $_.type -ne 'toolThreatProtection' } | Select-Object * -ExcludeProperty scope) +
       @(@{ type = 'toolThreatProtection'; preInvocation = $true; postInvocation = $true })
  @{ properties = @{ policies = $p } } | ConvertTo-Json -Depth 10 -Compress | Set-Content policies.json
  az rest --method patch --url "$TS_URL`?$API" --body "@policies.json" --query properties.policies
  Remove-Item policies.json
  ```

- **Govern servers centrally.** [Govern MCP servers with Agent 365](../20-agent-365-governance/README.md) adds
  inventory and blocking from the Microsoft 365 admin center on top of this policy.

## Clean up

<!-- steps -->

### Delete the policy

In the AI Gateway portal, select **Policies**, select the **Agent 365 tool threat protection** policy, and select
**Delete**. Confirm with **Delete**. Tool calls with a runtime key work again.

### Remove the role assignment

If you added **AI Gateway Tools User** only for this lab, remove it in **Access**, or run:

```bash
az role assignment delete \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "dce03f8d-857f-4e40-a90d-67770fa6ecd2" \
  --scope "$GATEWAY_ID/workspaces/default/toolServers/$MCP_SERVER"
```

```powershell
az role assignment delete `
  --assignee (az ad signed-in-user show --query id -o tsv) `
  --role "dce03f8d-857f-4e40-a90d-67770fa6ecd2" `
  --scope "$GATEWAY_ID/workspaces/default/toolServers/$MCP_SERVER"
```

<!-- /steps -->

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Every protected call returns `ToolEvaluationIdentityRequired` | The call has no bearer token, or the token isn't a delegated user token. App-only tokens and runtime keys can't be used for OBO. | Sign in with `az login` as a user, get a token for `https://azure-api.net/aigateway`, and send it as `Authorization: Bearer`. Check that the token has an `scp` claim. |
| `tools/call` returns HTTP `401` or `403` with a bearer token | The user has no data-plane role on the MCP server, or the assignment hasn't applied yet | Assign **AI Gateway Tools User** at the MCP server or gateway scope and wait a few minutes |
| Calls return `ToolEvaluationUnavailable` | The token exchange or the evaluation failed, timed out, returned an invalid verdict, or the evaluator was unavailable | Retry later. If it persists, confirm the Microsoft Defender or Microsoft Purview license and the Defender policy mode with your security team, and share the `correlationId`. |
| A benign call returns `ToolEvaluationDenied` | Defender or Purview flagged the request or the result | Review the call with your security team using the `correlationId`. If the tool already ran (after-invocation stage), don't retry it automatically. |
| You can't add a second tool threat protection policy to the server | Each MCP server can have only one tool threat protection policy | Keep the existing policy, or delete it and add a new one with the stages you want |
| Tool calls got noticeably slower | Each enabled stage adds an evaluation round trip | Keep both stages where you need them, and use only **Before tool invocation** where results are trusted |

## Next steps

- [Govern MCP servers with Agent 365](../20-agent-365-governance/README.md)
- [Control which tools agents can call](../05-mcp-tool-controls/README.md)
- [Lock down backend traffic with private networking](../18-private-networking/README.md)
- [Protect tool calls with Defender and Purview](https://learn.microsoft.com/azure/api-management/ai-gateway-policy-tool-threat) on Microsoft Learn
