---
title: Enforce cost budgets with per-caller overrides
summary: Give every app, agent, and user a dollar budget per hour, day, or month, raise or lower it for specific API keys and Microsoft Entra identities, and watch the gateway answer 403 LlmCostQuotaExceeded once a caller's estimated spend runs out.
category: governance
level: Intermediate
duration: 30
tracks: [portal, rest]
order: 7
illustration: diagrams/policy-scopes.svg
tags: [costLimit, budget, FinOps, LlmCostQuotaExceeded, "403", overrides, Entra ID, chargeback]
objectives:
  - Explain how a cost limit estimates spend and counts it per caller in fixed calendar windows
  - Add a daily cost limit to a model in the portal or with the REST API
  - Give specific API keys and Microsoft Entra identities their own budget with overrides
  - Trigger a 403 LlmCostQuotaExceeded response, find the remaining budget header, and review estimated spend in Monitoring
prereqs:
  - 06-token-limits
  - 10-api-keys
---

# Enforce cost budgets with per-caller overrides

Your FinOps team has a problem that token limits can't solve: a thousand tokens on a premium reasoning model
costs many times more than a thousand tokens on a mini model, so "tokens per day" says nothing about the bill.
They want every app to have a **daily budget in dollars**, a bigger envelope for the production support bot,
and a separate allowance for a data science lead who signs in with Microsoft Entra ID. In this lab you set
that up as a cost limit at the gateway, so a caller who runs out of budget is stopped before the model is
called.

![A cost limit can apply to one model or to the whole gateway, with overrides for specific callers](../assets/diagrams/policy-scopes.svg "A cost limit attached to a model budgets spend on that model. Attached at gateway scope, it tracks one budget per caller across all models.")

<!-- widget: budget {"amount":5,"period":"day"} -->

## Before you begin

- Complete [Throttle tokens per caller with token limits](../06-token-limits/README.md). This lab reuses the
  **Policies** › **Add policy** wizard and the idea of per-caller counters.
- Complete [Issue and rotate runtime API keys](../10-api-keys/README.md). You need **two** runtime keys from
  **Access** › **Keys**, for example `app-dev` (gets the default budget) and `support-bot` (gets an override).
- Recommended: configure Application Insights in [Monitor usage, cost, and traces](../13-monitoring/README.md)
  and send a few requests first, so **Monitoring** can show estimated spend before you choose a budget.
- Optional, for the Entra override: a user or service principal that can call the gateway with Microsoft
  Entra ID. [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md) shows how.
- For the variables below and the REST track: the
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login`, the `aigateway` extension ([install it](../01-provision-gateway/README.md#before-you-begin)), and
  `jq` for the Bash snippets.
- Permission to change the gateway, for example **Contributor** on the resource group.

Set these variables once. Both tracks and the **Verify** section reuse them. Use the `app-dev` key here.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"                 # 24 characters or fewer
export PROVIDER="<provider-name>"          # for example foundry-models
export MODEL="<model-name>"                # the backend model name under that provider

export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export WS="https://management.azure.com$GATEWAY_ID/workspaces/default"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
# For Foundry imports, the default alias matches the deployment's model name.
export AI_GATEWAY_MODEL="$(az aigateway model show -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" \
  -n "$MODEL" --query properties.deployment.modelName -o tsv)"
# Paste the app-dev runtime key from Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG         = "<resource-group>"
$GATEWAY    = "<gateway>"                 # 24 characters or fewer
$PROVIDER   = "<provider-name>"           # for example foundry-models
$MODEL      = "<model-name>"              # the backend model name under that provider

$API        = "api-version=2025-09-01-preview"
$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$WS         = "https://management.azure.com$GATEWAY_ID/workspaces/default"
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
# For Foundry imports, the default alias matches the deployment's model name.
$env:AI_GATEWAY_MODEL = az aigateway model show -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER `
  -n $MODEL --query properties.deployment.modelName -o tsv
# Paste the app-dev runtime key from Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

## How it works

After each model response, the gateway **estimates its cost** from the tokens the provider reported and the
model's public pricing, broken down by token category. A cost limit adds that estimate to the caller's
counter for the current renewal period. Before it forwards the next request, the gateway checks the counter.
Once spend reaches the budget, the gateway answers `403` with the error code `LlmCostQuotaExceeded` and never
calls the backend. Responses also carry a header with the remaining budget.

| Setting | Portal label | JSON field | Values |
|---|---|---|---|
| Budget | **Budget amount** | `amount` | US dollars, for example `5` |
| Window | **Renewal period** | `period` | `hour`, `day`, `week`, `month`, `year` (**Hourly** … **Yearly**) |
| Who gets a counter | **Counter dimensions** (shown as **Budget counted by**) | `counterKey` | An array: `["identity"]` (the API key, or the Entra tenant ID + object ID) or `["ipAddress"]` |
| Exceptions | **Overrides** | Portal only | A different amount for an API key or Entra identity |
| Policy identity | Not shown | `id` | Stable ID. Editing the amount keeps accumulated spend. |

Renewal periods are **fixed calendar windows**, not rolling windows: a **Daily** budget starts fresh at the
beginning of each day, not 24 hours after the first call. Attach the policy to a **model** to budget spend on
that model, or at **Gateway** scope to track **one budget per caller across all models**.

> [!IMPORTANT]
> A cost limit is a guardrail, not an invoice. Spend is estimated from public pricing, and because gateway
> instances update counters concurrently, concurrent requests can briefly **overshoot** the budget before every
> instance sees the latest spend.

<!-- widget: policy-layers -->

## Add a cost limit to the model

Pick one track. Both produce the same default budget on your model: **$5 per day for each caller identity**.
Overrides for specific callers are configured in the portal, so the REST track ends there too.

<!-- track: portal | Portal -->

### Start the policy wizard

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher.
Select **Policies** › **Add policy**. On the **Type** step, under **Cost & Rate Limits**, select
**Cost limit**, then **Next**.

### Choose where the budget applies

On the **Scope** step, select **Individual assets** ("Apply only to selected models, aliases, or MCP servers").
Select your model, then **Next**.

> [!TIP]
> Choose **Gateway** ("Apply to all compatible assets") when the budget should cover **every** model a caller
> uses, including models you import later. A gateway-scoped cost limit tracks one budget across all models
> instead of one per model.

### Set the default budget

On the **Details** step, under **Parameters**, set:

| Field | Value |
|---|---|
| **Budget amount** | `5` (US dollars) |
| **Renewal period** | **Daily** |
| **Counter dimensions** | **Caller identity** |

Select **Next**.

> [!NOTE]
> **Caller identity** gives each API key, and each Entra caller, its own counter. If you select no dimension, every
> caller shares one counter for the policy. **Caller IP address** can't be combined with overrides: the portal asks
> you to remove all overrides or switch to caller identity before saving.

### Give an API key a bigger budget

On the **Overrides** step, under **API keys**, select **Add**. In the new row, pick your `support-bot` key in
**API key** and set **Budget amount** to `50`. Each key can have only one override.

### Give a Microsoft Entra identity its own budget

Under **Microsoft Entra identities**, select **Add**. In **Add Microsoft Entra identities override**, choose how
**Match requests by** works:

- **Specific Microsoft Entra identity**: search for a user by name or email. For a service principal, enter its
  **object ID**, not its application (client) ID.
- **Custom token claim combination**: add one or more **Claim name** and **Value** pairs, for example `appid`
  and the client ID of an internal app. Every claim condition must match the validated token.

Set **Budget amount** to `20`, then select **Add**.

![The Overrides step with one Microsoft Entra identity override and one custom token claims override](../assets/screens/policy-cost-limit-entra-overrides.png "Overrides (optional): API key overrides match a specific key; Microsoft Entra overrides match one identity or a combination of validated token claims. The first matching override wins.")

Overrides are evaluated in the order you add them, and the **first match wins**. A claim combination never
pools callers into a shared budget: with identity counting, each matching identity gets the override amount
on its own counter.

### Create the policy

Select **Create**. Back in **Policies**, open the new **Cost limit** to review it.

![The Cost limit details page showing behavior, configuration, and the assets it applies to](../assets/screens/policy-cost-limit-details.png "The details page explains the trigger and the 403 LlmCostQuotaExceeded response, and lists Budget amount, Renewal period, Budget counted by, and Applies to.")

> **Checkpoint**
> The **Cost limit** details page shows **Budget amount** $5.00, **Renewal period** **Daily**, **Budget
> counted by** **Caller identity**, and your model under **Applies to**. Select **Edit** to see your overrides.

<!-- track: rest | REST API -->

### Read the current policies

This track calls the Azure Resource Manager REST API with `az rest`, because the `aigateway` extension doesn't
set cost limits. Policies live inline in the model's `properties.policies` array. A `PATCH` **replaces the
whole array**, so always read it first and keep the policies you didn't mean to change.

```bash
SUB="$(az account show --query id -o tsv)"
URL="https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY/workspaces/default/modelProviders/$PROVIDER/models/$MODEL?api-version=2025-09-01-preview"

az rest --method get --url "$URL" --query properties.policies
```

### Add or update the cost limit and keep everything else

A cost limit carries a stable `id`. Editing the amount of an existing policy **keeps its accumulated spend**,
so the merge below updates an existing `costLimit` in place (keeping its `id` and any overrides) and only
creates a new one, with a fresh GUID, when none exists.

```bash title="Bash"
BUDGET=5
PERIOD=day
POLICIES="$(az rest --method get --url "$URL" | jq -c \
  --argjson amount "$BUDGET" --arg period "$PERIOD" --arg id "$(uuidgen | tr 'A-Z' 'a-z')" '
  .properties.policies // [] | . as $p
  | if any($p[]; .type == "costLimit")
    then [$p[] | if .type == "costLimit"
                 then (.amount = $amount | .period = $period | .counterKey = ["identity"])
                 else . end]
    else $p + [{"type":"costLimit","id":$id,"amount":$amount,"period":$period,"counterKey":["identity"]}]
    end')"

az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}"
```

```powershell title="PowerShell"
$BUDGET = 5
$PERIOD = 'day'
$SUB = az account show --query id -o tsv
$URL = "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY/workspaces/default/modelProviders/$PROVIDER/models/$MODEL`?api-version=2025-09-01-preview"

$current  = az rest --method get --url $URL | ConvertFrom-Json
$policies = @($current.properties.policies | Where-Object { $_ })
$cost     = $policies | Where-Object { $_.type -eq 'costLimit' } | Select-Object -First 1
if ($cost) {
  $cost | Add-Member -NotePropertyName amount -NotePropertyValue $BUDGET -Force
  $cost | Add-Member -NotePropertyName period -NotePropertyValue $PERIOD -Force
  $cost | Add-Member -NotePropertyName counterKey -NotePropertyValue @('identity') -Force
} else {
  $policies += [pscustomobject]@{
    type = 'costLimit'; id = [guid]::NewGuid().ToString(); amount = $BUDGET; period = $PERIOD; counterKey = @('identity')
  }
}

$body = @{ properties = @{ policies = $policies } } | ConvertTo-Json -Depth 10 -Compress
$body | Set-Content -Path patch.json
az rest --method patch --url $URL --body '@patch.json'
Remove-Item patch.json
```

`period` accepts `hour`, `day`, `week`, `month`, or `year`. `counterKey` is an array: `["identity"]`, or
`["ipAddress"]` to count per client IP address.

### Add overrides in the portal

Configure overrides for API keys and Microsoft Entra identities in the portal: select **Policies**, open the
**Cost limit**, select **Edit**, and use the **Overrides** step as described in the portal track. The merge
above keeps those overrides when you change the amount later.

> **Checkpoint**
> Running the `GET` again returns your other policies unchanged plus one `costLimit` entry with its `id`,
> `"amount": 5.0`, `"period": "day"`, `"counterKey": ["identity"]`, and `"scope": "resource"`.

<!-- /tracks -->

## Verify

A $5 budget takes a while to spend, so temporarily lower it, run a short series of requests with the `app-dev`
key (which has no override), and watch the gateway switch from `200` to `403`.

<!-- steps -->

### Lower the budget for the test

In the portal, open the **Cost limit**, select **Edit**, set **Budget amount** to `0.01`, and **Save**. On the
REST track, run the merge again with `BUDGET=0.01` (PowerShell: `$BUDGET = 0.01`).

If your model is an inexpensive mini or nano model, use `0.001` so a handful of calls is enough. Because
editing keeps accumulated spend, the very first request might already be blocked if `app-dev` spent more than
the new budget earlier today.

### Run the requests

From the lab folder, run the script for your shell. It prints the status, the error code, the tokens used, and
any response header whose name mentions budget, cost, or remaining.

```bash title="Bash"
./infra/trigger-cost-limit.sh "$AI_GATEWAY_MODEL" 10
```

```powershell title="PowerShell"
./infra/trigger-cost-limit.ps1 -Model $env:AI_GATEWAY_MODEL -Requests 10
```

On GitHub, open [trigger-cost-limit.sh](infra/trigger-cost-limit.sh) or
[trigger-cost-limit.ps1](infra/trigger-cost-limit.ps1).

Expected output (your token counts, the number of successful calls, and the header values will differ):

```text
Request  Status  Error code               Tokens used  Budget headers
1        200     -                        220          …
2        200     -                        225          …
3        200     -                        218          …
4        403     LlmCostQuotaExceeded     -            …
5        403     LlmCostQuotaExceeded     -            …
```

How many calls succeed depends on the model's price. A call or two more than you expect is the small overshoot
described in [How it works](#how-it-works).

### Inspect one blocked response

Look at the full headers and body of a single blocked call:

```bash
curl -i "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
```

The status line is `HTTP/1.1 403`, and the body contains `LlmCostQuotaExceeded`. Scan the headers for the one
that reports the remaining budget, and compare it with a successful response from a key that still has budget.
Unlike a token limit, which frees up as the window rolls, the caller stays blocked until the next calendar
renewal period starts or you raise the budget.

### Prove the override and the per-caller counters

Set `AI_GATEWAY_API_KEY` to the `support-bot` key in a new terminal (repeat the variable block) and run the
script again. Every request succeeds, because that key has its own counter and a $50 override. If you added an
Entra override, call the gateway with that identity's token as shown in
[Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): it gets its own counter too, keyed
by tenant ID and object ID.

### Review estimated spend in Monitoring

If you configured Application Insights, open **Monitoring**. **Estimated model cost** and **Top models** show
the spend the gateway estimated, and the dashboard attributes it to individual API keys and models.

![The Monitoring overview with estimated model cost, model calls, and top models by estimated cost](../assets/screens/monitoring-overview.png "Monitoring estimates model cost from observed tokens and public pricing, and breaks it down by model and API key.")

<!-- /steps -->

> **Checkpoint**
> `app-dev` got `200` responses until its estimated spend reached the budget, then `403`
> `LlmCostQuotaExceeded`. `support-bot` wasn't affected, and the backend received no calls from `app-dev` while
> it was blocked.

## Go further

- **Cap spend across all models.** Add a second **Cost limit** with **Gateway** scope, for example $200
  **Monthly**. Each caller then has one budget across every model, including models you import later. With
  REST, run the same merge against the gateway workspace:
  `https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY/workspaces/default?api-version=2025-09-01-preview`
  (`"${WS}?$API"` from the variable block).
- **Combine with token limits.** Keep a per-minute **Token rate limit** to smooth bursts and a **Cost limit**
  to cap spend. Both are checked on every request, and either one can block.
- **Budget by role or app.** Use **Custom token claim combination** overrides, for example a `roles` claim with
  an app role value, so everyone with that role gets a different per-identity amount.
- **Chargeback by team.** Export `tid`, `oid`, or a custom claim to cost metrics in
  [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md).

## Clean up

A $0.01 budget blocks real traffic. Delete the policy, or raise it to a production value, before you continue.
Raising the amount takes effect immediately, because the accumulated spend is kept and compared with the new
budget.

<!-- track: portal | Portal -->

### Remove or raise the budget

Select **Policies**, open the **Cost limit** you created, and select **Delete**, or select **Edit** and set a
production **Budget amount**. If you created runtime keys only for this lab, revoke them in **Access** › **Keys**.

<!-- track: rest | REST API -->

### Remove the cost limit

```bash
POLICIES="$(az rest --method get --url "$URL" | jq -c '[(.properties.policies // [])[] | select(.type != "costLimit")]')"
az rest --method patch --url "$URL" --body "{\"properties\":{\"policies\":$POLICIES}}"
```

To keep the policy instead, run the merge again with a production budget, for example `BUDGET=100`.

<!-- /tracks -->

Keep the gateway, model, and keys. The next labs reuse them.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Every request returns `200`, never `403` | The cost limit is on a different model than the alias you call, your key has an override, or the model is so cheap that the calls haven't reached the budget | Check **Applies to** on the policy details page, use a key without an override, and lower the budget to `0.001` or send more requests. |
| `403` `LlmCostQuotaExceeded` on the first request | The key already spent more than the new amount in this period (spend is kept when you edit), or a **Gateway** scope cost limit is exhausted | Review every **Cost limit** in **Policies**. Raise the amount, or wait for the next renewal period. |
| An Entra override doesn't apply | An earlier override matched first, the caller used an API key, or you entered a service principal's application ID | Remove the earlier override and add them again in the order you want. Call with an Entra token. Use the service principal's **object ID**. |
| **Caller IP address** can't be selected in **Counter dimensions** | The policy has overrides | Remove all overrides, or keep **Caller identity**. |
| `429` instead of `403` | A **Token rate limit** or **Request rate limit** blocked the call, or the backend ran out of capacity | See [Throttle tokens per caller with token limits](../06-token-limits/README.md). |
| Other policies vanished after the REST call | `PATCH` replaces the whole `policies` array | Always `GET`, merge, then `PATCH`, as shown in the REST track. |
| `ValidationError` with target `counterKey` | `counterKey` is a string such as `"Identity"`, or it's missing | Send an array, for example `"counterKey": ["identity"]`. A cost limit always needs `counterKey`. |

## Next steps

- [Set gateway-wide policy baselines](../09-gateway-baselines/README.md): combine gateway-scoped budgets with other guardrails.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): see estimated spend by API key and model.
- [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md): build chargeback reports by team or identity.
- Docs: [Policies in AI Gateway](https://ai.gateway.azure.com/docs/policies).
