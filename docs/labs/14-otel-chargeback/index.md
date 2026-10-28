---
title: Attribute tokens and cost with OpenTelemetry
summary: Export Microsoft Entra token claims with the gateway's logs, traces, and token metrics, then turn observed tokens into a per-tenant, per-app, and per-key chargeback report with KQL, PromQL, and a small Python script.
category: observability
level: Advanced
duration: 35
tracks: [portal, rest, iac]
order: 14
status: new
illustration: diagrams/observability.svg
tags: [OpenTelemetry, token claims, chargeback, estimated cost, KQL, PromQL, Prometheus, Microsoft Entra ID]
objectives:
  - Choose which JWT claims the gateway exports to logs, root traces, and token and cost metrics
  - Check which claims your callers' tokens actually carry before you rely on them
  - Build a chargeback report from request logs by tenant, client app, and API key
  - Query token and cost metrics with PromQL without double counting token types
prereqs:
  - 13-monitoring
  - 11-entra-rbac
---

# Attribute tokens and cost with OpenTelemetry

Three teams and a partner tenant share your gateway. Some call it with API keys, others with Microsoft Entra ID.
Finance wants a monthly report of who used which model and what it cost. In this lab you export the right token
claims with the gateway's telemetry, send traffic as both kinds of caller, and build that report from the data
Application Insights already collects.

![AI Gateway exports metrics, logs, and traces with caller attributes](../assets/diagrams/observability.svg "Token claims ride along with the telemetry the gateway already exports, so every log, root trace, and token metric can name its caller.")

## Before you begin

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, model, key, Application Insights, and role
> assignment, so you can skip this section. You need only [Azure Cloud Shell](https://shell.azure.com), or the Azure
> Developer CLI (`azd`), the Azure CLI, and Git on your machine, and permission to create role assignments, for
> example **Owner** on the subscription. The later sections also use Python 3.10 or later, and `curl` and `jq` or
> PowerShell 7, which Cloud Shell has.

- Complete [Monitor usage, cost, and traces](../13-monitoring/README.md) with **Configure telemetry**, so the
  gateway exports all three signals to Application Insights with an OpenTelemetry exporter.
- Complete [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md), or make sure your signed-in
  user has **AI Gateway Models User** (or **AI Gateway User**) on the gateway or on the model alias.
- Permission to change the gateway, for example **Contributor** on its resource group, and **Log Analytics Reader**
  on the workspace behind Application Insights.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with `az login`,
  the `aigateway` extension ([install it](../01-provision-gateway/README.md#before-you-begin)), Python 3.10 or
  later, and `curl` and `jq` (Bash) or PowerShell 7.

Set these variables once. If you named the Application Insights resource differently in lab 13, change
`$GATEWAY-insights`.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export AI_GATEWAY_MODEL="<model-name>"     # a callable alias
export API="api-version=2025-09-01-preview"

export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export WS="https://management.azure.com$GATEWAY_ID/workspaces/default"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo

APPI_ID="$(az resource show -g "$RG" -n "$GATEWAY-insights" --resource-type Microsoft.Insights/components --query id -o tsv)"
LAW_ID="$(az resource show --ids "$APPI_ID" --api-version 2020-02-02 --query properties.WorkspaceResourceId -o tsv)"
```

```powershell title="PowerShell"
$RG      = "<resource-group>"
$GATEWAY = "<gateway>"
$env:AI_GATEWAY_MODEL = "<model-name>"     # a callable alias
$API     = "api-version=2025-09-01-preview"

$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$WS         = "https://management.azure.com$GATEWAY_ID/workspaces/default"
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput

$APPI_ID = az resource show -g $RG -n "$GATEWAY-insights" --resource-type Microsoft.Insights/components --query id -o tsv
$LAW_ID  = az resource show --ids $APPI_ID --api-version 2020-02-02 --query properties.WorkspaceResourceId -o tsv
```

## How it works

Every request already carries its caller. An API key call is attributed by the key's ID
(`azure.ai_gateway.api_key_id`). A Microsoft Entra call carries a validated JWT, and **token claim attributes**
copy the claims you pick into telemetry as `azure.ai_gateway.identity.claims.<claim>`. For each claim you choose the
signals independently: **logs**, **root traces**, and **observed token and cost metrics**.

Logs hold the per-request token usage the backend reported, so they're the best source for a detailed report.
Metrics are cheaper to query over long ranges, but every exported claim value becomes a label, so keep metrics to
claims with a bounded number of values.

Estimated cost is **observed tokens × public pricing**. Treat it as an allocation key and reconcile the total with
provider billing or Azure Cost Management.

| Claim | Identifies | Recommended preset | Use it for |
|---|---|---|---|
| `tid` | The caller's tenant | Logs, Traces, Metrics | Tenant or customer totals. With `oid`, the dashboard's Entra caller. |
| `oid` | The user, service principal, or managed identity | Logs, Traces, Metrics | Per-caller totals |
| `appid` (v1 tokens), `azp` (v2 tokens) | The client application | Logs, Traces | Per-app chargeback. This lab adds Metrics. |
| A custom claim, such as `cost_center` | Whatever your tokens carry | You choose | Team chargeback, if the claim is in the token |

## Choose the claims to export

You keep the recommended preset and add **Metrics** for `appid` and `azp`, so token and cost metrics can also be
split by client app.

<!-- track: portal | Portal -->

### Open the token claim attributes

In the [AI Gateway portal](https://ai.gateway.azure.com), select your gateway, then **Monitoring** › **Settings**.
On the **Logging** tab, find **Token claim attributes**: "Add selected JWT claims to exported logs, root traces, and
observed token and cost metrics." Each row is a claim with **Logs**, **Traces**, and **Metrics** checkboxes.

![Monitoring settings with token claim attributes for tid, oid, appid, and azp](../assets/screens/monitoring-token-claim-attributes.png "The recommended preset: tid and oid go to logs, traces, and metrics; appid and azp go to logs and traces.")

> [!NOTE]
> No **Token claim attributes** section? It's only shown for OpenTelemetry exporters. Reconfigure monitoring as
> in [Monitor usage, cost, and traces](../13-monitoring/README.md). If the table is empty ("No token claims are
> included in exported telemetry"), add `tid`, `oid`, `appid`, and `azp` with **Add claim**.

### Add metrics for the client app

Select **Metrics** for `appid` and for `azp`. Leave `tid` and `oid` on all three signals: the dashboard needs
both on metrics to attribute Entra callers. Changes save automatically while "Saving changes…" is shown. Every
claim needs at least one signal.

> [!TIP]
> **Add claim** adds a row (the placeholder suggests `cost_center`) that starts with **Logs** and **Traces**.
> Only add claims that your callers' tokens carry. The next section shows how to check.

<!-- track: rest | REST API -->

### Read the current configuration

The claim attributes live on the gateway's telemetry exporter. The `aigateway` extension doesn't manage telemetry
exporters yet, so call the Azure Resource Manager REST API with `az rest`. List the exporters and their claims:

```bash title="Bash"
az rest --method get --url "$WS/telemetryExporters?$API" \
  --query "value[].{name:name, kind:properties.kind, claims:properties.telemetry.attributes}"
```

```powershell title="PowerShell"
az rest --method get --url "$WS/telemetryExporters?$API" `
  --query "value[].{name:name, kind:properties.kind, claims:properties.telemetry.attributes}"
```

Expected output: one exporter of kind `OpenTelemetry`, usually named `appinsights`, whose claims list `tid`, `oid`,
`appid`, and `azp`, each with its `signals`. A kind of `applicationInsights` is the legacy exporter. Reconfigure
monitoring as in [Monitor usage, cost, and traces](../13-monitoring/README.md) first.

### Change it in the portal

Make the change in the portal: open **Monitoring** › **Settings** › **Logging** › **Token claim attributes** and
select **Metrics** for `appid` and `azp`. To automate it, declare the claims in the exporter's
`telemetry.attributes` list, as the **Bicep + azd** track does. Then run the `GET` again. Both claims now list
`metrics` in their `signals`.

<!-- track: iac | Bicep + azd -->

**What you need:** [Azure Cloud Shell](https://shell.azure.com), in Bash or PowerShell, or [azd](https://aka.ms/azd-install),
the Azure CLI with the `aigateway` extension, and Git on your machine, signed in with `azd auth login` and `az login`.
This track doesn't use your gateway from the earlier labs: `azd up` creates a new one, so it works on its own.

### Choose what to declare

The templates reuse lab 13's and lab 11's. Lab 13's
[monitoring.bicep](../13-monitoring/infra/monitoring.bicep) creates the Application Insights destination with OTLP
ingestion turned on, and its [otel-exporter.bicep](../13-monitoring/infra/otel-exporter.bicep) creates the gateway's
OpenTelemetry exporter. The claim attributes are part of that exporter, in its `telemetry.attributes` list. Each
entry names a claim in `source` (`kind` is `claims`, `value` is the claim name, such as `tid`) and lists the signals
that carry it in `signals`: `logs`, `traces`, and `metrics`.

`infra/main.bicep` passes the recommended preset and adds `metrics` for `appid` and `azp`. It also calls lab 11's
[role-assignment.bicep](../11-entra-rbac/infra/role-assignment.bicep) to grant you **AI Gateway Models User** on
the gateway, for the Entra calls in the next section. As in lab 13, `azure.yaml` grants the gateway's managed
identity **Monitoring Metrics Publisher** on the Data Collection Rule in a `postprovision` hook, because the rule's
managed resource group blocks deployments.

### Clone the lab

The lab is a small azd project in the
[`labs/14-otel-chargeback`](https://github.com/Azure/ai-gateway/tree/main/labs/14-otel-chargeback) folder of the
GitHub repo. Clone the repo and move into that folder. If you cloned it for an earlier lab, move into
`ai-gateway/labs/14-otel-chargeback` instead. The next sections run the lab's scripts from this folder.

```bash title="Bash"
git clone https://github.com/Azure/ai-gateway.git
cd ai-gateway/labs/14-otel-chargeback
```

```powershell title="PowerShell"
git clone https://github.com/Azure/ai-gateway.git
Set-Location ai-gateway/labs/14-otel-chargeback
```

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and calls the quick start's
[resources.bicep](../quickstart/infra/resources.bicep) for the gateway, the Foundry model, its default alias, and the
`app-first-call` key. Then it calls lab 13's templates with the claims to export, and lab 11's role assignment for
the identity that runs azd. `azd` passes your object ID in `AZURE_PRINCIPAL_ID`:

<!-- include: infra/main.bicep -->

`azure.yaml` holds the `postprovision` hook that grants the role on the Data Collection Rule:

<!-- include: azure.yaml -->

### Deploy with azd up

Create an azd environment named `aigw-lab14` in your current subscription, then provision everything. It takes
about four minutes.

```bash title="Bash"
azd env new aigw-lab14 --location eastus2 --subscription "$(az account show --query id --output tsv)"
azd up
```

```powershell title="PowerShell"
azd env new aigw-lab14 --location eastus2 --subscription (az account show --query id --output tsv)
azd up
```

For another region, pick one where AI Gateway and the `gpt-6-luna` model are available, as in [Find the available
regions](../01-provision-gateway/README.md#find-the-available-regions).

### Read the outputs and the key

Set the variables that the next sections use from azd's environment values, and read the key from the gateway, so
that it never shows on screen. The last command lists the exporter's claims.

```bash title="Bash"
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"
export API="api-version=2025-09-01-preview"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_ID)"
export WS="https://management.azure.com$GATEWAY_ID/workspaces/default"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
APPI_ID="$(azd env get-value APP_INSIGHTS_ID)"
LAW_ID="$(azd env get-value LOG_ANALYTICS_WORKSPACE_ID)"
az rest --method get --url "$WS/telemetryExporters?$API" \
  --query "value[].{name:name, kind:properties.kind, claims:properties.telemetry.attributes}"
```

```powershell title="PowerShell"
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$env:AI_GATEWAY_MODEL   = azd env get-value AI_GATEWAY_MODEL
$API                    = "api-version=2025-09-01-preview"
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$WS                     = "https://management.azure.com$GATEWAY_ID/workspaces/default"
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
$APPI_ID                = azd env get-value APP_INSIGHTS_ID
$LAW_ID                 = azd env get-value LOG_ANALYTICS_WORKSPACE_ID
az rest --method get --url "$WS/telemetryExporters?$API" `
  --query "value[].{name:name, kind:properties.kind, claims:properties.telemetry.attributes}"
```

Expected output: `azd up` ended with `SUCCESS`, and the list shows one exporter, `appinsights`, of kind
`OpenTelemetry`, whose claims list `tid`, `oid`, `appid`, and `azp`, each with `logs`, `traces`, and `metrics` in
its `signals`.

### Change the claims

Each `azd provision` applies the claims in `infra/main.bicep` again. To go back to the recommended preset, without
metrics for the client app, set `CLIENT_APP_METRICS` to `false` and provision. Then run the `GET` again: `appid` and
`azp` list only `logs` and `traces`. If you try it now, set it back to `true` and provision again before you continue,
so that the PromQL section can split metrics by client app.

```bash title="Bash"
azd env set CLIENT_APP_METRICS false
azd provision
```

```powershell title="PowerShell"
azd env set CLIENT_APP_METRICS false
azd provision
```

To export a custom claim, such as `cost_center`, add an entry to the `claimAttributes` list in `infra/main.bicep`
and run `azd provision`. Check that your callers' tokens carry it first, as the next section shows. For the chargeback
report, follow the **REST API** track: it uses the variables you set here.

<!-- /tracks -->

> **Checkpoint**
> `tid` and `oid` export to logs, traces, and metrics, and `appid` and `azp` now export to all three as well.

## Send attributed traffic

<!-- steps -->

### Check what your token carries

A claim only appears in telemetry if the validated token has it. Decode your own token locally and look:

```bash title="Bash"
az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv \
  | python3 infra/show_claims.py cost_center
```

```powershell title="PowerShell"
az account get-access-token --resource https://azure-api.net/aigateway --query accessToken -o tsv |
  python infra/show_claims.py cost_center
```

On GitHub, open [infra/show_claims.py](infra/show_claims.py). The script prints `aud`, `ver`, `tid`, `oid`, `appid`,
`azp`, and `idtyp`, plus any claim names you pass. Nothing leaves your machine.

Expected output: `aud` is `https://azure-api.net/aigateway`, `tid` and `oid` are GUIDs, and either `appid` (v1
token) or `azp` (v2 token) holds the Azure CLI's client ID. `cost_center` is `(not in token)`.

> [!IMPORTANT]
> Tokens for AI Gateway are issued for its audience, `https://azure-api.net/aigateway`. Before you add a custom
> claim such as `cost_center` to **Token claim attributes**, decode a real token from that caller and confirm the
> claim is there. If it isn't, map client apps (`appid` or `azp`) to cost centers in your report instead.

### Call the gateway as two callers

Run the script for your shell. It sends five requests with your API key and five with your Entra token, each with an
`x-correlation-id` header.

```bash title="Bash"
./infra/send-attributed-traffic.sh "$AI_GATEWAY_MODEL" 5
```

```powershell title="PowerShell"
./infra/send-attributed-traffic.ps1 -Model $env:AI_GATEWAY_MODEL -Requests 5
```

On GitHub, open [send-attributed-traffic.sh](infra/send-attributed-traffic.sh) or
[send-attributed-traffic.ps1](infra/send-attributed-traffic.ps1).

Expected output: ten rows, all `200`, alternating between `api-key` and `entra`. A `401` or `403` on the `entra`
rows means your role assignment is missing or hasn't propagated yet.

### Find your callers in Monitoring

Wait a few minutes, then open **Monitoring** › **Models** with **1H** selected. In
**Model usage by caller identity**, your API key and your Entra identity appear as separate rows with their own
tokens and estimated cost. Entra callers are resolved from `tid` and `oid`. Callers with neither an API key nor
those claims show as **Unattributed**.

Then select **Traces**, open one of the Entra requests, and expand its log under **Correlated logs**. Look for
`azure.ai_gateway.identity.claims.tid`, `...oid`, and `...appid` or `...azp`. An API key request shows
`azure.ai_gateway.api_key_id` instead.

<!-- /steps -->

> **Checkpoint**
> Both callers appear on the **Models** tab, and an Entra request's correlated log shows its claims.

## Build a chargeback report

The report groups the token usage in request logs by owner and prices it with a price list you control. The query
is in [infra/chargeback.kql](infra/chargeback.kql):

<!-- include: infra/chargeback.kql kusto -->

On GitHub, open [infra/chargeback.kql](infra/chargeback.kql).

<!-- steps -->

### Prepare a price list

Copy [infra/prices.example.json](infra/prices.example.json) to `prices.json`. Replace `<model-name>` with each value
in the report's `Model` column, which is the model that answered (for example a versioned name), and copy current
prices per million tokens from your provider's pricing page or agreement. A versioned name such as
`my-model-2026-01-01` matches the key `my-model`.

> [!CAUTION]
> The example prices are placeholders. Don't publish a report until you've replaced them with real prices.

<!-- /steps -->

<!-- track: portal | Portal -->

### Run the query

In the [Azure portal](https://portal.azure.com), open the Log Analytics workspace behind your Application Insights
resource and select **Logs**. Switch to **KQL mode**, paste the contents of `infra/chargeback.kql`, and select
**Run**. You get one row per tenant, object ID, client app, API key, alias, and model.

### Export it

Select **Export** and choose CSV with all columns. Save the file as `usage.csv` in the lab folder.

### Price it

```bash title="Bash"
python3 infra/chargeback_report.py usage.csv prices.json --by Tenant,ClientApp,ApiKeyId --out chargeback.csv
```

```powershell title="PowerShell"
python infra/chargeback_report.py usage.csv prices.json --by Tenant,ClientApp,ApiKeyId --out chargeback.csv
```

<!-- track: rest | REST API -->

### Run the query

Send the query to the Log Analytics query API through Azure Resource Manager and save the response:

```bash title="Bash"
jq -n --rawfile q infra/chargeback.kql '{query: $q}' > query.json
az rest --method post \
  --url "https://management.azure.com${LAW_ID}/query?api-version=2017-10-01" \
  --body @query.json > usage.json
```

```powershell title="PowerShell"
@{ query = Get-Content infra/chargeback.kql -Raw } | ConvertTo-Json | Set-Content query.json
az rest --method post `
  --url "https://management.azure.com$LAW_ID/query?api-version=2017-10-01" `
  --body "@query.json" | Set-Content usage.json
```

The response holds a `tables` array with `columns` and `rows`, which the report script reads directly.

### Price it

```bash title="Bash"
python3 infra/chargeback_report.py usage.json prices.json --by Tenant,ClientApp,ApiKeyId --out chargeback.csv
```

```powershell title="PowerShell"
python infra/chargeback_report.py usage.json prices.json --by Tenant,ClientApp,ApiKeyId --out chargeback.csv
```

<!-- /tracks -->

On GitHub, open [infra/chargeback_report.py](infra/chargeback_report.py). It sums requests and tokens per group,
prices uncached input, cached input, and output tokens separately, and lists any model without a price. Group by
any column from the query, for example `--by CostCenter` or `--by ApiKeyId,Model`.

Expected output: a table with one row for your API key (`(none)` in `Tenant` and `ClientApp`) and one for your
Entra identity (your tenant ID and the Azure CLI's client ID), followed by a total.

> [!TIP]
> The report shows IDs. Resolve a client app's name with
> `az ad sp show --id <client-app-id> --query displayName -o tsv`, and an API key's name under **Access** › **Keys**.

> **Checkpoint**
> `chargeback.csv` has a priced row for each caller, and no model is listed under "No price for".

## Query token and cost metrics with PromQL

Token and cost metrics land in the Azure Monitor workspace (managed Prometheus) linked to Application Insights, as
`azure.ai_gateway.client.token.usage` and `azure.ai_gateway.client.token.cost`. They're the same metrics the
dashboard reads, and they carry the claims you enabled for **Metrics** as labels.

<!-- steps -->

### Find the Prometheus endpoint

```bash title="Bash"
AMW_ID="$(az resource show --ids "$APPI_ID" --api-version 2020-02-02 --query properties.AzureMonitorWorkspaceResourceId -o tsv)"
PROM_URL="$(az resource show --ids "$AMW_ID" --api-version 2023-04-03 --query properties.metrics.prometheusQueryEndpoint -o tsv)"
PROM_TOKEN="$(az account get-access-token --resource https://prometheus.monitor.azure.com --query accessToken -o tsv)"
```

```powershell title="PowerShell"
$AMW_ID     = az resource show --ids $APPI_ID --api-version 2020-02-02 --query properties.AzureMonitorWorkspaceResourceId -o tsv
$PROM_URL   = az resource show --ids $AMW_ID --api-version 2023-04-03 --query properties.metrics.prometheusQueryEndpoint -o tsv
$PROM_TOKEN = az account get-access-token --resource https://prometheus.monitor.azure.com --query accessToken -o tsv
```

### Query token usage for the last day

The metric names contain dots, so the selector uses quoted names. The `microsoft.appresourceid` label limits the
query to your Application Insights resource.

```bash title="Bash"
SELECTOR="{__name__=\"azure.ai_gateway.client.token.usage\",\"microsoft.appresourceid\"=\"$(echo "$APPI_ID" | tr '[:upper:]' '[:lower:]')\"}"
curl -sS -G "${PROM_URL%/}/api/v1/query" -H "Authorization: Bearer $PROM_TOKEN" \
  --data-urlencode "query=increase(${SELECTOR}[1d])" \
  | jq -r '.data.result[] | [.metric["gen_ai.response.model"], .metric["gen_ai.token.type"],
      (.metric["azure.ai_gateway.api_key_id"] // "-"), (.metric["azure.ai_gateway.identity.claims.tid"] // "-"),
      (.metric["azure.ai_gateway.identity.claims.appid"] // .metric["azure.ai_gateway.identity.claims.azp"] // "-"),
      (.value[1] | tonumber | round)] | @tsv'
```

```powershell title="PowerShell"
$selector = '{__name__="azure.ai_gateway.client.token.usage","microsoft.appresourceid"="' + $APPI_ID.ToLower() + '"}'
$result = Invoke-RestMethod -Uri "$($PROM_URL.TrimEnd('/'))/api/v1/query" `
  -Headers @{ Authorization = "Bearer $PROM_TOKEN" } -Body @{ query = 'increase(' + $selector + '[1d])' }
$result.data.result | ForEach-Object { [pscustomobject]@{
  Model     = $_.metric.'gen_ai.response.model'
  TokenType = $_.metric.'gen_ai.token.type'
  ApiKeyId  = $_.metric.'azure.ai_gateway.api_key_id'
  Tenant    = $_.metric.'azure.ai_gateway.identity.claims.tid'
  ClientApp = $_.metric.'azure.ai_gateway.identity.claims.appid' ?? $_.metric.'azure.ai_gateway.identity.claims.azp'
  Tokens    = [math]::Round([double]$_.value[1]) } } | Format-Table
```

Expected output: rows per model, token type, and caller. Your Entra rows carry your tenant ID and the client app.

> [!WARNING]
> Don't add up every token type. A model reports totals and details (for example `total_tokens` and
> `prompt_tokens_details.cached_tokens`) next to input and output, so a plain sum double counts. Use the total
> type if there is one, otherwise input plus output. Cached tokens are usually a subset of input tokens.

### Query estimated cost

Replace `azure.ai_gateway.client.token.usage` with `azure.ai_gateway.client.token.cost` and run the query again. Each
series carries `azure.ai_gateway.currency`. Series with `azure.ai_gateway.price_missing="true"` had no public price,
so their cost isn't counted.

<!-- /steps -->

> [!NOTE]
> Counters are cumulative, and `increase()` extrapolates and can miss the first sample of a brand new series, so
> treat short-range metric results as approximate. The docs show PromQL in its underscore form,
> `sum by (gen_ai_request_model) (gen_ai_client_token_usage)`, which is how some OTLP backends store these names.
> If a query returns nothing, list the names your backend stored with `count by (__name__) ({__name__=~".*token.*"})`.

## Verify

<!-- steps -->

### Compare the report with the dashboard

Open **Monitoring** › **Models** with **24H** selected. The input and output tokens of your two callers in
**Model usage by caller identity** are in the same range as their rows in `chargeback.csv`.

### Confirm the client app label

Run the PromQL query again. Your Entra rows show a client app ID, which comes from the **Metrics** signal you
enabled for `appid` and `azp`.

<!-- /steps -->

## Go further

- **Enforce what you measure.** A cost limit can give a different budget to a specific Entra identity or to a
  **Custom token claim combination**, such as an `appid` value. See
  [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md).
- **Send telemetry to another backend.** In the setup wizard, **Custom OpenTelemetry destination** takes a
  **Metrics endpoint**, **Logs endpoint**, and **Traces endpoint**, such as a collector, Grafana, Datadog, or any
  OTLP service. Authenticate with **Custom headers** (values are masked and never shown again after saving) or a
  **Managed identity** with a token audience. Claims are exported the same way. The built-in dashboard only reads
  Application Insights, so with a custom destination you build these views in that platform.
- **Fan out with a collector.** To keep claims in one place and send them to several backends, point the gateway at
  your own OpenTelemetry Collector and route from there.
- **Keep metric cardinality in check.** Every distinct claim value is a new series. Put high-cardinality claims such
  as `oid` on logs and traces for detail, and keep metrics to `tid`, client apps, and bounded custom claims.
- **Schedule the report.** Run the REST track monthly from a pipeline with a managed identity that has
  **Log Analytics Reader**, and store `chargeback.csv` with your finance data.

## Clean up

The exported files contain tenant and object IDs. Treat them as personal data.

<!-- track: portal | Portal -->

### Restore the preset

In **Monitoring** › **Settings** › **Logging** › **Token claim attributes**, clear **Metrics** for `appid` and
`azp`. Remove any custom claim you added.

### Delete the exported files

Delete `usage.csv`, `prices.json`, and `chargeback.csv` from the lab folder.

<!-- track: rest | REST API -->

### Restore the preset

In **Monitoring** › **Settings** › **Logging** › **Token claim attributes**, clear **Metrics** for `appid` and
`azp`, then run the `GET` from the start of the lab to confirm both claims list only `logs` and `traces`.

### Delete the exported files

```bash title="Bash"
rm -f query.json usage.json prices.json chargeback.csv
```

```powershell title="PowerShell"
Remove-Item query.json, usage.json, prices.json, chargeback.csv -ErrorAction SilentlyContinue
```

<!-- track: iac | Bicep + azd -->

### Delete the exported files

In the `ai-gateway/labs/14-otel-chargeback` folder, delete the files the report created:

```bash title="Bash"
rm -f query.json usage.json prices.json chargeback.csv
```

```powershell title="PowerShell"
Remove-Item query.json, usage.json, prices.json, chargeback.csv -ErrorAction SilentlyContinue
```

### Delete everything azd created

In the same folder, delete the resource group with the gateway, the Foundry account, the Application Insights
component, the Log Analytics workspace, and your role assignment on the gateway. Azure deletes the component's
managed resource group with it. `--purge` also purges the Foundry account, which would otherwise stay soft-deleted
for 48 hours and keep counting against your quota. It takes about ten minutes.

```bash
azd down --purge --force
```

To keep this gateway for other labs instead, skip `azd down` and restore the preset:
`azd env set CLIENT_APP_METRICS false`, then `azd provision`.

<!-- /tracks -->

Keep monitoring on if you continue: the agent labs use it to show where agent calls went. Otherwise, follow the
clean-up steps in [Monitor usage, cost, and traces](../13-monitoring/README.md). `azd down` doesn't touch the
gateway and monitoring from the earlier labs, because the Bicep + azd track created its own.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No **Token claim attributes** section in **Settings** | The exporter is the legacy `applicationInsights` kind | Disable monitoring and configure it again, as in [Monitor usage, cost, and traces](../13-monitoring/README.md). |
| The `entra` rows return `401` or `403` | Wrong token audience, or no **AI Gateway Models User** role yet | Get the token for `https://azure-api.net/aigateway`, check the role assignment, wait a few minutes, and get a new token. |
| Entra callers show as **Unattributed** on **Models** | `tid` or `oid` isn't exported to **Metrics** | Select **Metrics** for both and send new traffic. Earlier requests stay unattributed. |
| The chargeback query returns no rows | Telemetry hasn't arrived, the **Logs** signal is off, or your API reports usage under other names | Wait a few minutes, then run `OTelLogs \| where TimeGenerated > ago(1h) \| take 5` and compare the `Attributes` with the query. |
| `Tenant` or `ClientApp` is empty for Entra rows | The claim wasn't exported to **Logs** when the request ran | Enable **Logs** for the claim and send new traffic. |
| The Prometheus query returns `401` or `403` | Your account can't read the Azure Monitor workspace | Ask for a data read role on the Azure Monitor workspace, such as **Monitoring Data Reader**, then get a new token. |

## Next steps

- [Enforce cost budgets with per-caller overrides](../07-cost-budgets/README.md): turn the report into budgets per
  key, identity, or claim.
- [Connect agent frameworks to models and tools](../15-agent-frameworks/README.md): give each agent its own key or
  identity so the report shows it.
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): move callers from keys to identities
  that carry claims.
- Docs: [Observability](https://ai.gateway.azure.com/docs/observability)
