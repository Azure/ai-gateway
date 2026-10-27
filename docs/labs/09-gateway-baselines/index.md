---
title: Set gateway-wide policy baselines
summary: Apply a baseline of token limit, request rate limit, content safety, and IP filter policies at Gateway scope so every model and MCP server, including the ones you add later, starts with the same guardrails, then layer stricter asset policies on top.
category: governance
level: Intermediate
duration: 25
tracks: [portal, rest, iac]
order: 9
illustration: diagrams/policy-scopes.svg
tags: [Gateway scope, baseline, tokenLimit, requestRateLimit, contentSafety, ipFilter, "403", policy as code]
objectives:
  - Explain how Gateway scope policies and asset policies layer, and why any applicable policy can block a call
  - Apply a token limit, request rate limit, content safety, and IP filter baseline at Gateway scope
  - Keep the baseline in a reviewed policy file and apply it with a merge-safe script
  - Verify the baseline from your own IP address and see a stricter model policy take effect on top of it
prereqs:
  - 06-token-limits
  - 08-content-safety
---

# Set gateway-wide policy baselines

Your gateway now serves several models and MCP servers, and teams add new ones every week. Some assets have
carefully tuned policies, and some have none at all. The platform and security teams agree on a baseline that
every asset gets by default: a generous token limit, a request rate limit, **Balanced** content safety, and
runtime access only from approved networks. In this lab you apply that baseline once, at **Gateway** scope,
and keep tighter asset policies on top of it.

![Policies at gateway scope and on models, aliases, MCP servers, and future assets](../assets/diagrams/policy-scopes.svg "A Gateway scope policy covers every compatible asset, including assets added later. Asset policies add narrower rules on top.")

<!-- widget: policy-layers -->

## Before you begin

- Complete [Throttle tokens per caller with token limits](../06-token-limits/README.md) and
  [Screen prompts and responses with content safety](../08-content-safety/README.md), including their
  **Clean up** sections. You need a gateway, an imported model, a callable alias, and a runtime API key from
  **Access** › **Keys**.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login`, the `aigateway` extension ([install it](../01-provision-gateway/README.md#before-you-begin)), and
  `jq` (Bash) or PowerShell 7 or later.
- For **Verify**: `curl` (Bash) or PowerShell 7 or later.
- Permission to change the gateway, for example **Contributor** on the resource group.
- The public IP addresses or CIDR ranges your callers use. Once the IP filter is on, calls from anywhere else get
  `403`.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"                 # 24 characters or fewer
export PROVIDER="<provider-name>"          # for example foundry-models
export MODEL="<model-name>"                # the backend model name under that provider

export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
# For Foundry imports, the default alias matches the deployment's model name.
export AI_GATEWAY_MODEL="$(az aigateway model show -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" \
  -n "$MODEL" --query properties.deployment.modelName -o tsv)"
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo

# The public IP address this machine uses on the internet, and the ranges the IP filter allows.
export MY_IP="$(curl -s https://api.ipify.org)" && echo "$MY_IP"
export ALLOWED_CIDRS="$MY_IP/32"           # comma-separated, for example "$MY_IP/32,198.51.100.0/24"
```

```powershell title="PowerShell"
$RG         = "<resource-group>"
$GATEWAY    = "<gateway>"                 # 24 characters or fewer
$PROVIDER   = "<provider-name>"           # for example foundry-models
$MODEL      = "<model-name>"              # the backend model name under that provider

$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
# For Foundry imports, the default alias matches the deployment's model name.
$env:AI_GATEWAY_MODEL = az aigateway model show -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER `
  -n $MODEL --query properties.deployment.modelName -o tsv
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput

# The public IP address this machine uses on the internet, and the ranges the IP filter allows.
$env:MY_IP = Invoke-RestMethod https://api.ipify.org; $env:MY_IP
$env:ALLOWED_CIDRS = "$($env:MY_IP)/32"    # comma-separated, for example "$($env:MY_IP)/32,198.51.100.0/24"
```

## How it works

A policy with **Gateway** scope is stored on the gateway's `default` workspace instead of on one asset. It
applies to every compatible model, alias, and MCP server, including assets you add later, without another
policy update. Asset policies keep working alongside it. The gateway evaluates every applicable policy before
it forwards a request, and if any one of them blocks, the client gets an error and the backend is never
called. So an asset policy can make the rules **tighter** for one asset, but it can't loosen the baseline.

This lab's baseline:

| Policy | Applies to | Baseline value | Blocked calls get |
|---|---|---|---|
| **Token rate limit** | Models | 100,000 tokens per minute, per caller identity | `429` with `Retry-After` |
| **Request rate limit** | Models and MCP servers | 600 calls per 60 seconds, per caller identity | `429` with `Retry-After` |
| **Content safety** | Models and MCP servers | **Balanced** (`Medium`) for all four categories | `400` |
| **IP filter** | Models and MCP servers | **Allow listed IPs only**: your CIDR ranges | `403` |

A Gateway scope **Cost limit** is one budget across all models; you can add it in
[Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md). Agent 365 tool threat
protection can't be set at Gateway scope; it applies to individual MCP servers.

> [!WARNING]
> The IP filter applies to **runtime** calls. You keep managing the gateway in the portal and with the Azure
> CLI, so you can always fix the list. But every caller outside it gets `403`: teammates, CI pipelines, hosted
> agents, and your own machine when you switch networks or VPN. Remove it in [Clean up](#clean-up).

## Apply the baseline

Pick one track. Each track creates the same four policies at **Gateway** scope. The `aigateway` extension
doesn't set Gateway scope policies yet, so both scripted tracks call the Azure Resource Manager REST API with
`az rest` against the gateway's `default` workspace.

<!-- track: portal | Portal -->

### Add the token rate limit

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher.
Select **Policies** › **Add policy**. On the **Type** step, select **Token rate limit**, then **Next**.

On the **Scope** step, select **Gateway** ("Apply to the entire gateway workspace, including applicable assets
added later."), then **Next**.

![The Add policy wizard on the Scope step with Gateway selected](../assets/screens/policy-gateway-scope.png "On the Scope step, Gateway applies the policy to every compatible asset, including assets added later.")

On the **Details** step (**Configure** in some portal versions), under **Parameters**, set:

| Field | Value |
|---|---|
| **Time period** | **Per minute** |
| **Allowed tokens** | `100000` |
| **Counter dimensions** | **Caller identity** |

Select **Create**.

### Add the request rate limit

Select **Add policy** again. Select **Request rate limit**, then **Gateway** scope, and set:

| Field | Value |
|---|---|
| **Calls** | `600` |
| **Renewal period** | **60 seconds** |
| **Counter dimensions** | **Caller identity** |

Select **Create**.

### Add content safety

Select **Add policy**. Under **Security**, select **Content safety**, then **Gateway** scope. Set **Hate**,
**Violence**, **Self-harm**, and **Sexual** to **Balanced**, then select **Create**.

### Add the IP filter

Select **Add policy**. Under **Security**, select **IP filter**, then **Gateway** scope, and set:

| Field | Value |
|---|---|
| **Action** | **Allow listed IPs only** |
| **IP addresses / CIDR ranges** | Your `ALLOWED_CIDRS` value, for example `198.51.100.7/32` |

Use CIDR notation for every entry: `/32` for a single IPv4 address. Check the value against `echo "$MY_IP"`
before you select **Create**.

> **Checkpoint**
> **Policies** lists four policies whose scope is **Gateway**: **Token rate limit**, **Request rate limit**,
> **Content safety**, and **IP filter**.

<!-- track: rest | REST API -->

### Read the Gateway scope policies

Gateway scope policies live inline in the `properties.policies` array of the gateway's `default` workspace.
A `PATCH` **replaces the whole array**, so always read it first and keep the policies you didn't mean to
change.

```bash title="Bash"
SUB="$(az account show --query id -o tsv)"
URL="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY/workspaces/default?api-version=2025-09-01-preview"

az rest --method get --url "$URL" --query properties.policies
```

```powershell title="PowerShell"
$SUB = az account show --query id -o tsv
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY/workspaces/default`?api-version=2025-09-01-preview"

az rest --method get --url $URL --query properties.policies
```

### Merge the baseline and keep everything else

The baseline replaces any existing policy of the same four types and keeps every other entry, such as a
Gateway scope cost limit.

```bash title="Bash"
BASELINE="$(jq -cn --arg cidrs "$ALLOWED_CIDRS" '[
  {"type":"tokenLimit","count":100000,"period":"minute","counterKey":["identity"],"scope":"workspace"},
  {"type":"requestRateLimit","callsPerPeriod":600,"periodSeconds":60,"counterKey":["identity"],"scope":"workspace"},
  {"type":"contentSafety","hateSeverity":"Medium","violenceSeverity":"Medium","sexualSeverity":"Medium","selfHarmSeverity":"Medium"},
  {"type":"ipFilter","action":"Allow","cidrRanges":($cidrs | split(",") | map(gsub("\\s"; "")) | map(select(length > 0)))}
]')"
jq '.[] | select(.type == "ipFilter")' <<<"$BASELINE"    # check the allowed ranges before you apply

POLICIES="$(az rest --method get --url "$URL" | jq -c --argjson baseline "$BASELINE" '
  [(.properties.policies // [])[] | select(.type | IN($baseline[].type) | not)] + $baseline')"

az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}"
```

```powershell title="PowerShell"
$baseline = @(
  [pscustomobject]@{ type = 'tokenLimit'; count = 100000; period = 'minute'; counterKey = @('identity'); scope = 'workspace' }
  [pscustomobject]@{ type = 'requestRateLimit'; callsPerPeriod = 600; periodSeconds = 60; counterKey = @('identity'); scope = 'workspace' }
  [pscustomobject]@{ type = 'contentSafety'; hateSeverity = 'Medium'; violenceSeverity = 'Medium'; sexualSeverity = 'Medium'; selfHarmSeverity = 'Medium' }
  [pscustomobject]@{ type = 'ipFilter'; action = 'Allow'; cidrRanges = @($env:ALLOWED_CIDRS -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
)
$baseline | Where-Object type -eq 'ipFilter' | ConvertTo-Json    # check the allowed ranges before you apply

$current  = az rest --method get --url $URL | ConvertFrom-Json
$policies = @($current.properties.policies | Where-Object { $_ -and $_.type -notin $baseline.type })
$policies += $baseline

$body = @{ properties = @{ policies = $policies } } | ConvertTo-Json -Depth 10 -Compress
$body | Set-Content -Path patch.json
az rest --method patch --url $URL --body '@patch.json'
Remove-Item patch.json
```

> [!NOTE]
> When you create a token or request rate limit at **Gateway** scope, the portal writes `"scope": "workspace"`
> into the policy object. The REST and Policy as code tracks include the same field so that every track creates
> the same policy. `counterKey` is an array: `["identity"]` gives each API key or Entra caller its own counter.
> If the API rejects a field, create the policy once in the portal, then copy its shape from the `GET` response.

> **Checkpoint**
> Running the `GET` again returns your other policies unchanged plus `tokenLimit` and `requestRateLimit` entries
> with `"counterKey": ["identity"]` and `"scope": "workspace"`, and `contentSafety` and `ipFilter` entries
> with your ranges in `cidrRanges`. The service adds `"scope": "resource"` to the last two.

<!-- track: iac | Policy as code -->

### Choose what to declare

Gateway scope policies live on the gateway's `default` workspace. The sample Bicep templates only reference
that workspace as `existing`. Declaring it in your own template would send a `PUT` that replaces the whole
workspace resource, including settings that the template doesn't list. Instead, keep the baseline in a policy
file that goes through code review, and apply it with a script that does the same `GET`, merge, and `PATCH` as
the REST track.

### Review the policy file

<!-- include: infra/baseline-policies.json -->

On GitHub, open [infra/baseline-policies.json](infra/baseline-policies.json).

The `ipFilter` entry holds a placeholder from the `203.0.113.0/24` documentation range. The script never applies
it: it replaces `cidrRanges` with your `ALLOWED_CIDRS` value and stops if that value is missing or isn't in CIDR
notation.

### Preview the change

From the lab folder, print the merged policy array without changing anything:

```bash title="Bash"
./infra/apply-baseline.sh --dry-run
```

```powershell title="PowerShell"
./infra/apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY -DryRun
```

The PowerShell script reads `$env:ALLOWED_CIDRS` unless you pass `-AllowedCidrs`.

### Apply it

```bash title="Bash"
./infra/apply-baseline.sh
```

```powershell title="PowerShell"
./infra/apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY
```

<!-- include: infra/apply-baseline.sh -->

On GitHub, open [infra/apply-baseline.sh](infra/apply-baseline.sh) or
[infra/apply-baseline.ps1](infra/apply-baseline.ps1).

> [!TIP]
> Run the script from a pipeline with an identity that can change the gateway, and change the baseline only
> through pull requests to `baseline-policies.json`. Post the `--dry-run` output in the pull request so
> reviewers see the exact policy array before it's applied.

> **Checkpoint**
> The script prints four Gateway scope policies (`tokenLimit`, `requestRateLimit`, `contentSafety`, and
> `ipFilter`) plus any other policies you already had.

<!-- /tracks -->

## Verify

Check that the baseline covers your model and MCP servers, that your own calls still pass, and that a tighter
asset policy still takes effect on top of it.

<!-- steps -->

### Review the baseline in the portal

Select **Policies**. The four baseline policies show **Gateway** in the **Scope** column. Policies you add to
a model, alias, or MCP server show that asset instead.

### Call the model from your IP address

From the lab folder, send one chat completion:

```bash title="Bash"
./infra/check-call.sh "$AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
./infra/check-call.ps1 -Model $env:AI_GATEWAY_MODEL
```

On GitHub, open [check-call.sh](infra/check-call.sh) or [check-call.ps1](infra/check-call.ps1).

Expected output:

```text
Status: 200
Reply:  A gateway-wide policy baseline is a default set of rules that applies to every asset ...
```

Your call passed all four baseline policies: your IP address is on the allow list, you're far below both rate
limits, and the prompt is benign. If you completed
[Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md), run
`../04-federate-mcp-tools/infra/list-tools.sh learn` (PowerShell:
`../04-federate-mcp-tools/infra/list-tools.ps1 -Server learn`). The MCP server is covered by the same IP
filter, request rate limit, and content safety policies, and it still lists its tools.

### Layer a stricter model policy

Add a deliberately low token limit to your model only, the same one you used in lab 06.
`az aigateway model policy set-token-limit` keeps every other policy on the model:

```bash title="Bash"
az aigateway model policy set-token-limit -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --token-limit 1000
```

```powershell title="PowerShell"
az aigateway model policy set-token-limit -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $MODEL `
  --token-limit 1000
```

Then send a burst with the script from lab 06:

```bash title="Bash"
../06-token-limits/infra/trigger-token-limit.sh "$AI_GATEWAY_MODEL" 8
```

```powershell title="PowerShell"
../06-token-limits/infra/trigger-token-limit.ps1 -Model $env:AI_GATEWAY_MODEL -Requests 8
```

After three or four requests, the gateway returns `429`. The baseline allows 100,000 tokens per minute, but the
model's tighter limit is evaluated too, and it blocks. Remove the model limit and run the burst again:

```bash title="Bash"
az aigateway model policy remove -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$MODEL" \
  --remove-token-limit true
```

```powershell title="PowerShell"
az aigateway model policy remove -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $MODEL `
  --remove-token-limit true
```

All eight requests now return `200`, because only the generous baseline applies.

### See the IP filter block a call (optional)

Point the allow list at a documentation address that can't be yours, call the model, then restore your range.

- **Portal:** in **Policies**, select **Edit** on the **IP filter** policy, set the ranges to
  `203.0.113.10/32`, and save.
- **Script (Bash):** `ALLOWED_CIDRS="203.0.113.10/32" ./infra/apply-baseline.sh`
- **Script (PowerShell):** `./infra/apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY -AllowedCidrs "203.0.113.10/32"`

Run `check-call` again. It now returns `Status: 403`, and the request never reaches the model. Restore your
range in the portal, or run the script again without the override (`./infra/apply-baseline.sh`, or the
PowerShell script without `-AllowedCidrs`), and check that `check-call` returns `200`. If you still see the old
result, wait a minute and retry.

### Watch outcomes in Monitoring

If you configured Application Insights in [Monitor usage, cost, and traces](../13-monitoring/README.md), open
**Monitoring** and compare `400`, `403`, and `429` outcomes before and after the baseline. A sudden rise in
`403` usually means a caller's network isn't on the allow list.

<!-- /steps -->

> **Checkpoint**
> **Policies** shows four **Gateway** scope policies. Your own call returned `200`, a stricter model limit
> still returned `429` on top of the baseline, and you know how a blocked IP address looks (`403`).

## Go further

- **Cap spend gateway-wide.** Add a **Cost limit** with **Gateway** scope for one budget across all models, as
  described in [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md).
- **Tighten tool traffic.** Keep the baseline and add stricter controls to individual MCP servers in
  [Control which tools agents can call](../05-mcp-tool-controls/README.md) and
  [Protect tool calls with Agent 365 threat protection](../19-tool-threat-protection/README.md).
- **Keep the allow list for inbound traffic.** Inbound private endpoints and turning off public network access
  aren't available for AI Gateway yet, so the IP filter is how you restrict who can call the gateway. To keep
  the gateway's traffic to your backends private, see
  [Lock down backend traffic with private networking](../18-private-networking/README.md).
- **Count Entra callers.** With `identity` counters, each Entra caller gets its own allowance. Move clients to
  keyless calls in [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md).

## Clean up

Remove the baseline before you continue, especially the IP filter: later labs call the gateway from hosted
agents and other networks, which would get `403`. In your own environment, you can keep the other three
policies and replace the IP filter with your organization's egress ranges.

<!-- track: portal | Portal -->

### Remove the baseline

Select **Policies**. For each of the four policies with **Gateway** scope, select **Delete**. Remove the
**IP filter** first.

<!-- track: rest | REST API -->

### Remove the baseline

```bash
POLICIES="$(az rest --method get --url "$URL" | jq -c '[(.properties.policies // [])[]
  | select(.type | IN("tokenLimit","requestRateLimit","contentSafety","ipFilter") | not)]')"
az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}"
```

Every other Gateway scope policy stays.

<!-- track: iac | Policy as code -->

### Remove the baseline

```bash title="Bash"
./infra/apply-baseline.sh --remove
```

```powershell title="PowerShell"
./infra/apply-baseline.ps1 -ResourceGroup $RG -Gateway $GATEWAY -Remove
```

The script removes the policy types listed in `baseline-policies.json` and keeps every other Gateway scope
policy.

<!-- /tracks -->

Keep the gateway, model, and key. The next labs reuse them.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Every call returns `403` | Your public IP address changed (new network, VPN, or hotspot), or your network reaches the gateway from a different address than the one `api.ipify.org` reported | Check `curl -s https://api.ipify.org` again and update the IP filter. If you use a proxy or split-tunnel VPN, ask your network team for the egress ranges. Management calls still work, so you can always fix the list. |
| Teammates, pipelines, or hosted agents get `403` | Their egress addresses aren't on the allow list | Add their CIDR ranges, or remove the IP filter until you know them. |
| Ordinary prompts return `400` | Content safety blocked them, from the baseline or from a stricter asset policy | Review every **Content safety** policy that covers the asset in **Policies**, and retest with representative prompts. |
| `429` much earlier than the baseline allows | A tighter token or request rate limit on the model, alias, or MCP server applies | Review **Policies** for every limit that covers the asset. The lowest applicable limit wins. |
| The `PATCH` returns a validation error about `counterKey` or `scope` | `counterKey` is a string such as `"Identity"` instead of an array, or the shape differs from what the API version expects | Use `"counterKey": ["identity"]`. If it still fails, create that policy once in the portal at **Gateway** scope, read the shape with the `GET`, and use it in your script or policy file. |
| `Set ALLOWED_CIDRS ...` or `Use CIDR notation ...` from the script | `ALLOWED_CIDRS` is empty, or an entry has no prefix length | Set it to comma-separated CIDR ranges, for example `"$MY_IP/32"`. |
| Other Gateway scope policies vanished after the REST call | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the REST track and the script. |
| `jq: command not found` | `jq` isn't installed | Install `jq`, or use the PowerShell commands. |

## Next steps

- [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md): add a spend limit to the
  baseline.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): track `400`, `403`, and `429` outcomes per
  policy.
- [Lock down backend traffic with private networking](../18-private-networking/README.md): route the gateway's
  backend traffic through your virtual network.
- Docs: [Policies in AI Gateway](https://ai.gateway.azure.com/docs/policies).
