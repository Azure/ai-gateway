---
title: Deploy an enterprise reference architecture
summary: Deploy a production-shaped AI Gateway environment from modular Bicep, with a keyless Foundry backend, models and MCP tools behind RBAC, a key per app, layered policies, and monitoring. Then promote it from dev to prod with a GitHub Actions workflow that signs in with OpenID Connect and smoke-tests every deployment.
category: production
level: Advanced
duration: 60
tracks: [iac]
order: 21
illustration: diagrams/enterprise-reference.svg
tags: [Bicep, modules, reference architecture, managed identity, RBAC, policy layering, environments, GitHub Actions, OpenID Connect, smoke test]
objectives:
  - Explain the identity, policy, observability, and naming decisions behind a production AI Gateway deployment
  - Deploy a modular, subscription-scope Bicep template with separate parameter files for dev and prod
  - Layer gateway-wide baseline policies, applied by a merge-safe script, on top of model policies declared in Bicep
  - Automate preview, deployment, baselines, and a smoke test in GitHub Actions with OpenID Connect
  - Verify the model and MCP tool paths end to end, and clean up every resource
prereqs:
  - 09-gateway-baselines
  - 13-monitoring
  - 12-backend-identity
---

# Deploy an enterprise reference architecture

You've built every piece by hand in earlier labs: a keyless Foundry backend, aliases, MCP servers, per-caller
limits, a gateway-wide baseline, and monitoring. Now the platform team wants the whole setup as code. Dev and
prod should differ only in their parameters, every change should go through a pull request, and a pipeline
should deploy it without a stored secret. In this lab you deploy a modular reference architecture, apply the
baseline, prove it works with a smoke test, and wire it all into GitHub Actions.

![GitHub Actions deploys two resource groups: the gateway with its alias, model provider, MCP server, keys, and monitoring, and a Foundry account with key authentication disabled](../assets/diagrams/enterprise-reference.svg "One pipeline signs in with OpenID Connect, previews, deploys, applies the gateway baseline, and runs a smoke test. The gateway reaches Foundry with its managed identity.")

<!-- widget: policy-layers -->

## Before you begin

- Complete [Set gateway-wide policy baselines](../09-gateway-baselines/README.md),
  [Monitor usage, cost, and traces](../13-monitoring/README.md), and
  [Call backends with managed identities](../12-backend-identity/README.md). This lab builds on what you learned
  there, not on the resources you created: it deploys a new, separate environment.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login` to the subscription you deploy to, and the `aigateway` extension
  ([install it](../01-provision-gateway/README.md#before-you-begin)). The CLI installs Bicep the first time you
  deploy. You also need `curl` and `jq` (Bash) or PowerShell 7 or later. The smoke test reads the gateway and a
  key with the extension. The extension can't set gateway-scope policies yet, so the baseline script calls the
  management API with `az rest`.
- **Owner**, or **Contributor** plus **Role Based Access Control Administrator**, on the subscription. The
  template creates two resource groups and several role assignments.
- Quota for `gpt-6-luna` with the `GlobalStandard` SKU in the region you deploy to. The dev environment uses
  50 capacity units (50,000 tokens per minute).
- The resource providers `Microsoft.ApiManagement`, `Microsoft.Web`, `Microsoft.CognitiveServices`,
  `Microsoft.OperationalInsights`, and `Microsoft.Insights` registered on the subscription. Register any missing
  one with `az provider register --namespace <namespace>`.
- For [Automate deployments with GitHub Actions](#automate-deployments-with-github-actions): a GitHub
  repository where you can create environments and variables, the [GitHub CLI](https://cli.github.com/) signed
  in with `gh auth login`, and permission to create an app registration in Microsoft Entra ID.

Run every command from this lab's folder, `labs/21-enterprise-reference`, so the `infra/` paths resolve. Set
these variables once:

```bash title="Bash"
export LOCATION="eastus2"            # deployment metadata, the Foundry account, and the monitoring resources
export ENV_NAME="aigw-dev"           # deployment name, the same as environmentName in main.bicepparam
# main.bicepparam reads this to give you data-plane access to the Foundry account, the alias, and the MCP server.
export AZURE_PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)"
az account show --query "{subscription:name, id:id}" -o table
```

```powershell title="PowerShell"
$env:LOCATION = "eastus2"            # deployment metadata, the Foundry account, and the monitoring resources
$env:ENV_NAME = "aigw-dev"           # deployment name, the same as environmentName in main.bicepparam
# main.bicepparam reads this to give you data-plane access to the Foundry account, the alias, and the MCP server.
$env:AZURE_PRINCIPAL_ID = az ad signed-in-user show --query id -o tsv
az account show --query "{subscription:name, id:id}" -o table
```

## How it works

One subscription-scope template, `infra/main.bicep`, creates two resource groups and composes small modules.
Each module owns one concern, so the people who own that concern can review and change it on their own, and no
module outputs a secret. Parameter files hold everything that differs between environments.

Gateway-wide policies aren't in Bicep. They live on the gateway's `default` workspace, and declaring that
workspace in a template would replace it. Instead, a script merges them in after each deployment, as in
[Set gateway-wide policy baselines](../09-gateway-baselines/README.md).

| File | Resource group | Deploys |
|---|---|---|
| `modules/monitoring.bicep` | `…-gateway` | Log Analytics workspace and a workspace-based Application Insights component, `<gateway>-insights` |
| `modules/foundry.bicep` | `…-foundrymodels` | Foundry account with key authentication turned off, and the `gpt-6-luna` deployment |
| `modules/gateway.bicep` | `…-gateway` | The AI Gateway (`Microsoft.ApiManagement/aigateways`, system-assigned identity), its connector gateway, and **Foundry User** for the identity on the Foundry account |
| `modules/models.bicep` | `…-gateway` | A Foundry model provider that authenticates with the managed identity, the backend model with a token limit and content safety, the alias `chat`, and **AI Gateway Models User** on the alias |
| `modules/tools.bicep` | `…-gateway` | The Microsoft Learn MCP server `learn`, and **AI Gateway Tools User** on it |
| `modules/keys.bicep` | `…-gateway` | One runtime API key per app: `web-chat` and `batch-jobs` |
| `modules/telemetry.bicep` | `…-gateway` | The legacy Application Insights telemetry exporter, off by default |
| `scripts/apply-baselines.sh` | Not applicable | Gateway scope **Request rate limit** and **Cost limit** from `baselines.json` |

## Make the architecture decisions

Each decision below is already built into the templates. In your own environment, change the parameters first,
and change the shape only when your organization needs something different.

### Identity: no secrets between services or in the pipeline

Each trust boundary uses its own mechanism, and none of them needs a stored secret:

| Boundary | Mechanism | Where |
|---|---|---|
| Gateway to Foundry | The gateway's system-assigned identity has **Foundry User** on the account. The account sets `disableLocalAuth: true`, so Foundry keys don't work at all. | `gateway.bicep`, `foundry.bicep` |
| Apps to gateway | One runtime API key per app, so every app gets its own policy counters, its own row in **Monitoring**, and its own rotation. Or keyless Microsoft Entra calls through **AI Gateway Models User** on the alias and **AI Gateway Tools User** on the MCP server, granted to groups. | `keys.bicep`, `models.bicep`, `tools.bicep` |
| Pipeline to Azure | An OpenID Connect federated credential. GitHub exchanges a short-lived token for an Azure token, so there's no client secret to rotate or leak. | `deploy-workflow.yml` |

Roles are granted at the narrowest scope that works: the alias instead of the whole gateway, and one MCP server
instead of every tool. Templates output key **names** only, never key values. The smoke test reads a key with
`az aigateway api-key list-secrets` when it needs one.

### Policies: a gateway floor plus model limits

| Layer | Declared in | Policies | Counted per |
|---|---|---|---|
| Gateway | `baselines.json`, applied by `scripts/apply-baselines.sh` | **Request rate limit**: 120 calls per 60 seconds, on models and MCP servers. **Cost limit**: $20 per day, one budget across all models. | Caller identity |
| Model | `models.bicep` | **Token rate limit**: 20,000 tokens per minute in dev. **Content safety**: **Balanced** (`Medium`) for all four categories. | Caller identity |

The gateway evaluates every applicable policy before it forwards a request, and any one of them can block it.
The platform team owns the gateway floor, and app teams tune the model layer through parameters. Blocked calls
get `429` from a rate limit, `403` with `LlmCostQuotaExceeded` from the cost limit, and `400` from content
safety.

The baseline script reads the workspace's `policies` array, updates policies of the same type in place, appends
missing ones, and writes the array back with `PATCH`. Updating in place keeps a cost limit's `id`, its
portal-only overrides, and the spend it has already counted.

> [!NOTE]
> The portal writes `"scope": "workspace"` on Gateway scope rate and cost limits, so `baselines.json` does too.
> If the API rejects a field, create the policy once in the portal at **Gateway** scope, read the workspace with
> `az rest`, and copy that shape into `baselines.json`.

### Observability: the destination in Bicep, the connection in the portal

`monitoring.bicep` creates the Log Analytics workspace and the Application Insights component, with retention
set per environment. The sample also declares a telemetry exporter of kind `applicationInsights`, but the
current portal treats that kind as **legacy**: it no longer activates the OTLP signals the **Monitoring**
dashboard needs. The OpenTelemetry exporter that replaces it isn't documented for automation yet. So you
connect the component once in the portal after the first deployment. No module declares an exporter, so later
deployments leave that connection alone. The sample's exporter is still available as `telemetry.bicep`, behind
`enableLegacyAppInsightsExporter`.

### Naming, tags, and resource groups

- **Deterministic names.** A resource token, the first eight characters of
  `uniqueString(subscription, environmentName, location)`, goes into every name. Deploying again updates the
  same resources instead of creating new ones.
- **Two resource groups.** `rg-<env>-<token>-gateway` holds the gateway and its monitoring, and
  `rg-<env>-<token>-foundrymodels` holds model capacity. You can secure, scale, and delete them separately, and
  only the gateway's identity needs access to Foundry.
- **A unique gateway name.** The gateway is `aigw-<token>`, which becomes
  `https://aigw-<token>.<region>-01.ai.gateway.azure.com`. Set `aiGatewayName` to choose your own: up to 24
  letters, digits, and hyphens, starting with a letter.
- **Tags.** Resource groups and top-level resources get `environment` and `workload: ai-gateway`, plus the
  `tags` from the parameter file, such as `costCenter`.
- **Regions.** `aiGatewayLocation` defaults to `eastus2`. Set it to any region where AI Gateway is available, as in
  [Find the available regions](../01-provision-gateway/README.md#find-the-available-regions). The other resources follow the deployment's
  `--location`, so pick one where the model is available.

### Environments: one template, two parameter files

| Setting | `main.bicepparam` (dev) | `prod.bicepparam` (prod) |
|---|---|---|
| `environmentName` | `aigw-dev` | `aigw-prod` |
| Developer access (`principalId`) | You, from `AZURE_PRINCIPAL_ID` | None |
| Model capacity (`modelCapacity`) | 50 | 200 |
| Tokens per minute per caller (`tokensPerMinutePerCaller`) | 20,000 | 50,000 |
| Microsoft Entra access (`modelUsers`, `toolUsers`) | Your user only | Groups you add |
| Log retention (`logRetentionInDays`) | 30 days | 90 days |
| `costCenter` tag | `dev` | `platform` |

> [!TIP]
> Put prod in its own subscription so quotas, role assignments, and Azure Policy stay isolated from dev. The
> template is subscription-scoped, so it works unchanged. Use a separate deployment identity for each
> subscription.

### Delivery: GitHub Actions with OpenID Connect

The workflow installs the `aigateway` extension, previews every change with `what-if`, deploys, applies the
baseline, and runs the smoke test. A `prod` GitHub environment with required reviewers gates production, and a
concurrency group per environment stops two runs from deploying to the same environment at once. The deployment
identity needs **Contributor** and **Role Based Access Control Administrator** on the subscription, because the
template creates role assignments. To narrow that, you can add a condition that only lets it assign the roles the
template needs, as described in
[Delegate Azure access management to others](https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-overview).

## Review the templates

`main.bicep` wires the modules together and passes outputs from one to the next, so Bicep deploys them in the
right order: monitoring and Foundry first, then the gateway, then models, tools, and keys.

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep).

`gateway.bicep` is the only module that declares the gateway itself. The others reference it as `existing` and
only add child resources to it.

<!-- include: infra/modules/gateway.bicep -->

On GitHub, open [infra/modules/gateway.bicep](infra/modules/gateway.bicep).

> [!WARNING]
> Each deployment sends a `PUT` for the gateway with exactly the properties in `gateway.bicep`. If you change
> gateway settings outside Bicep, add them to this module. Otherwise, the next deployment can reset them.
> Outbound virtual network integration is the exception: you can set it only when the gateway is created.
> `gateway.bicep` accepts it as `backendSubnetId`, but `main.bicep` doesn't pass it. To use it, add a parameter
> to `main.bicep` before the first deployment and keep passing the same subnet on every later deployment. See
> [Lock down backend traffic with private networking](../18-private-networking/README.md).

`models.bicep` declares the model-level policies right on the backend model, so they're versioned with it:

<!-- include: infra/modules/models.bicep -->

On GitHub, open [infra/modules/models.bicep](infra/modules/models.bicep).

The gateway floor is a plain policy file that goes through code review like any template:

<!-- include: infra/baselines.json -->

On GitHub, open [infra/baselines.json](infra/baselines.json).

The other files are short. Open them on GitHub:
[monitoring.bicep](infra/modules/monitoring.bicep), [foundry.bicep](infra/modules/foundry.bicep),
[foundry-user-role.bicep](infra/modules/foundry-user-role.bicep), [tools.bicep](infra/modules/tools.bicep),
[keys.bicep](infra/modules/keys.bicep), [telemetry.bicep](infra/modules/telemetry.bicep),
[types.bicep](infra/modules/types.bicep), [main.bicepparam](infra/main.bicepparam), and
[prod.bicepparam](infra/prod.bicepparam).

## Deploy the dev environment

Deploy from your machine first, so you see each stage before you automate it.

<!-- steps -->

### Preview the changes

```bash title="Bash"
az deployment sub what-if -n "$ENV_NAME" -l "$LOCATION" \
  -f infra/main.bicep -p infra/main.bicepparam
```

```powershell title="PowerShell"
az deployment sub what-if -n $env:ENV_NAME -l $env:LOCATION `
  -f infra/main.bicep -p infra/main.bicepparam
```

On a first run, the preview lists the two resource groups and the resources in them as new. On later runs, it
shows only what your change would modify. Paste it into the pull request so reviewers see the effect, not just
the diff.

### Deploy

```bash title="Bash"
az deployment sub create -n "$ENV_NAME" -l "$LOCATION" \
  -f infra/main.bicep -p infra/main.bicepparam \
  --query properties.provisioningState -o tsv
```

```powershell title="PowerShell"
az deployment sub create -n $env:ENV_NAME -l $env:LOCATION `
  -f infra/main.bicep -p infra/main.bicepparam `
  --query properties.provisioningState -o tsv
```

Provisioning the gateway and the model deployment takes several minutes. The command prints `Succeeded` when
everything is in place.

### Load the outputs

Read the deployment outputs into the variables the scripts and the rest of the lab use:

```bash title="Bash"
OUTPUTS="$(az deployment sub show -n "$ENV_NAME" --query properties.outputs -o json)"
# Output names can come back with a different first-letter casing, so match them case-insensitively.
out() { jq -r --arg k "$1" 'to_entries[] | select((.key | ascii_upcase) == $k) | .value.value' <<<"$OUTPUTS"; }
export RG="$(out AI_GATEWAY_RESOURCE_GROUP)"
export GATEWAY="$(out AI_GATEWAY_NAME)"
export AI_GATEWAY_URL="$(out AI_GATEWAY_URL)"
export AI_GATEWAY_MODEL="$(out AI_GATEWAY_MODEL)"
export AI_GATEWAY_LOCATION="$(out AI_GATEWAY_LOCATION)"
export AI_GATEWAY_PRINCIPAL_ID="$(out AI_GATEWAY_PRINCIPAL_ID)"
export FOUNDRY_RG="$(out FOUNDRY_MODELS_RESOURCE_GROUP)"
export FOUNDRY_NAME="$(out FOUNDRY_MODELS_NAME)"
export FOUNDRY_ID="$(out FOUNDRY_MODELS_RESOURCE_ID)"
printf '%s\n' "$RG" "$GATEWAY" "$AI_GATEWAY_URL" "$AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
$outputs = az deployment sub show -n $env:ENV_NAME --query properties.outputs -o json | ConvertFrom-Json
$env:RG                      = $outputs.AI_GATEWAY_RESOURCE_GROUP.value
$env:GATEWAY                 = $outputs.AI_GATEWAY_NAME.value
$env:AI_GATEWAY_URL          = $outputs.AI_GATEWAY_URL.value
$env:AI_GATEWAY_MODEL        = $outputs.AI_GATEWAY_MODEL.value
$env:AI_GATEWAY_LOCATION     = $outputs.AI_GATEWAY_LOCATION.value
$env:AI_GATEWAY_PRINCIPAL_ID = $outputs.AI_GATEWAY_PRINCIPAL_ID.value
$env:FOUNDRY_RG              = $outputs.FOUNDRY_MODELS_RESOURCE_GROUP.value
$env:FOUNDRY_NAME            = $outputs.FOUNDRY_MODELS_NAME.value
$env:FOUNDRY_ID              = $outputs.FOUNDRY_MODELS_RESOURCE_ID.value
$env:RG, $env:GATEWAY, $env:AI_GATEWAY_URL, $env:AI_GATEWAY_MODEL
```

Expected output:

```text
rg-aigw-dev-<token>-gateway
aigw-<token>
https://aigw-<token>.eastus2-01.ai.gateway.azure.com
chat
```

### Connect telemetry in the portal

Open the [AI Gateway portal](https://ai.gateway.azure.com), select your gateway, then **Monitoring** ›
**Configure telemetry**. On **Destination**, select **Existing Azure Application Insights resource**, pick
`<gateway>-insights` in **Application Insights resource**, and select **Next**. On **Authentication**, leave
**Include recommended token claims in telemetry** selected and select **Next**. On **Review and apply**, select
**Apply** and wait for every step, ending with **Create telemetry exporter**.

The wizard assigns the gateway's identity a role on the Application Insights component, so it needs the same
role assignment rights you used for the deployment. You do this once per environment.

### Preview the gateway baseline

Print the merged policy array without changing anything:

```bash title="Bash"
DRY_RUN=1 ./infra/scripts/apply-baselines.sh
```

```powershell title="PowerShell"
./infra/scripts/apply-baselines.ps1 -DryRun
```

The output shows a `requestRateLimit` entry and a `costLimit` entry with a newly generated `id`, plus any
Gateway scope policies the gateway already has.

### Apply the gateway baseline

```bash title="Bash"
./infra/scripts/apply-baselines.sh
```

```powershell title="PowerShell"
./infra/scripts/apply-baselines.ps1
```

<!-- include: infra/scripts/apply-baselines.sh -->

On GitHub, open [infra/scripts/apply-baselines.sh](infra/scripts/apply-baselines.sh) or
[infra/scripts/apply-baselines.ps1](infra/scripts/apply-baselines.ps1).

Expected output (end):

```text
Applied. Current gateway-scope policy types:
requestRateLimit
costLimit
```

Run it again whenever `baselines.json` changes. It's idempotent: a second run gives the same array.

<!-- /steps -->

> **Checkpoint**
> The deployment printed `Succeeded`, `RG` and `GATEWAY` point at the new gateway, **Monitoring** shows the
> **Overview**, **Models**, **Tools**, **Policies**, and **Traces** tabs, and the baseline script lists
> `requestRateLimit` and `costLimit`.

## Automate deployments with GitHub Actions

Copy this lab's `infra/` folder to the root of your own repository, so the workflow finds `infra/main.bicep`.
Then create an identity that GitHub Actions can sign in as, trust your repository's environments, and add the
workflow. Learn more in
[Authenticate to Azure from GitHub Actions by OpenID Connect](https://learn.microsoft.com/azure/developer/github/connect-from-azure-openid-connect).

Set the repository once:

```bash title="Bash"
export GITHUB_REPO="<github-org>/<github-repo>"
```

```powershell title="PowerShell"
$env:GITHUB_REPO = "<github-org>/<github-repo>"
```

<!-- steps -->

### Create the deployment identity

Create an app registration and its service principal:

```bash title="Bash"
export APP_ID="$(az ad app create --display-name "github-aigw-deploy" --query appId -o tsv)"
export SP_ID="$(az ad sp create --id "$APP_ID" --query id -o tsv)"
```

```powershell title="PowerShell"
$env:APP_ID = az ad app create --display-name "github-aigw-deploy" --query appId -o tsv
$env:SP_ID  = az ad sp create --id $env:APP_ID --query id -o tsv
```

### Trust your GitHub environments

Add one federated credential per GitHub environment. The workflow's job declares `environment:`, so GitHub's
token subject is `repo:<github-org>/<github-repo>:environment:<name>`, and it must match exactly.

```bash title="Bash"
for ENV in dev prod; do
  cat > "credential-$ENV.json" <<EOF
{
  "name": "github-$ENV",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:$GITHUB_REPO:environment:$ENV",
  "description": "GitHub Actions deployments to the $ENV environment",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF
  az ad app federated-credential create --id "$APP_ID" --parameters "credential-$ENV.json" -o none
  rm "credential-$ENV.json"
done
```

```powershell title="PowerShell"
foreach ($envName in "dev", "prod") {
  $file = "credential-$envName.json"
  @{
    name        = "github-$envName"
    issuer      = "https://token.actions.githubusercontent.com"
    subject     = "repo:$($env:GITHUB_REPO):environment:$envName"
    description = "GitHub Actions deployments to the $envName environment"
    audiences   = @("api://AzureADTokenExchange")
  } | ConvertTo-Json | Set-Content -Path $file
  az ad app federated-credential create --id $env:APP_ID --parameters $file -o none
  Remove-Item $file
}
```

### Grant access to the subscription

```bash title="Bash"
export SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
for ROLE in "Contributor" "Role Based Access Control Administrator"; do
  az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
    --role "$ROLE" --scope "/subscriptions/$SUBSCRIPTION_ID" -o none
done
```

```powershell title="PowerShell"
$env:SUBSCRIPTION_ID = az account show --query id -o tsv
foreach ($role in "Contributor", "Role Based Access Control Administrator") {
  az role assignment create --assignee-object-id $env:SP_ID --assignee-principal-type ServicePrincipal `
    --role $role --scope "/subscriptions/$($env:SUBSCRIPTION_ID)" -o none
}
```

### Create the GitHub environments

In your repository on GitHub, select **Settings** › **Environments** › **New environment**, and create `dev`
and `prod`. On `prod`, turn on **Required reviewers** and add the people who approve production deployments.

Then store the sign-in details as environment variables. They identify the identity but can't authenticate
anyone on their own, so they're variables, not secrets.

```bash title="Bash"
TENANT_ID="$(az account show --query tenantId -o tsv)"
for ENV in dev prod; do
  gh variable set AZURE_CLIENT_ID --env "$ENV" --body "$APP_ID" -R "$GITHUB_REPO"
  gh variable set AZURE_TENANT_ID --env "$ENV" --body "$TENANT_ID" -R "$GITHUB_REPO"
  gh variable set AZURE_SUBSCRIPTION_ID --env "$ENV" --body "$SUBSCRIPTION_ID" -R "$GITHUB_REPO"
done
```

```powershell title="PowerShell"
$tenantId = az account show --query tenantId -o tsv
foreach ($envName in "dev", "prod") {
  gh variable set AZURE_CLIENT_ID --env $envName --body $env:APP_ID -R $env:GITHUB_REPO
  gh variable set AZURE_TENANT_ID --env $envName --body $tenantId -R $env:GITHUB_REPO
  gh variable set AZURE_SUBSCRIPTION_ID --env $envName --body $env:SUBSCRIPTION_ID -R $env:GITHUB_REPO
}
```

### Add the workflow

In your repository, copy the sample workflow into `.github/workflows/`, then commit and push both folders:

```bash
mkdir -p .github/workflows
cp infra/deploy-workflow.yml .github/workflows/deploy-ai-gateway.yml
```

<!-- include: infra/deploy-workflow.yml yaml -->

On GitHub, open [infra/deploy-workflow.yml](infra/deploy-workflow.yml).

A push to `main` that changes `infra/` deploys dev. Prod deploys only when you start the workflow manually and a
reviewer approves it.

### Run it

```bash
gh workflow run deploy-ai-gateway.yml -f environment=dev -R "$GITHUB_REPO"
gh run watch -R "$GITHUB_REPO"
```

Or, in GitHub, select **Actions** › **Deploy AI Gateway** › **Run workflow**. The pipeline deploys to the same
resource groups you created from your machine, because the resource token depends only on the subscription,
the environment name, and the location. The pipeline doesn't set `AZURE_PRINCIPAL_ID`, so it doesn't declare
your developer roles. Incremental deployments leave the ones you already have in place.

<!-- /steps -->

> **Checkpoint**
> The run's **Smoke test** step prints `Smoke test passed.`, and the run summary lists the gateway, its
> endpoint, and the alias `chat`.

## Verify

Prove that both runtime paths work, that the policy layers are in place, and that the identity boundaries hold.

<!-- steps -->

### Run the smoke test

The same script runs at the end of the pipeline. It calls the alias with the `web-chat` key, then runs the MCP
handshake and `tools/list` on the `learn` MCP server. New role assignments can take a few minutes to apply, so
it retries the model call for about a minute.

```bash title="Bash"
./infra/scripts/smoke-test.sh "$AI_GATEWAY_MODEL" web-chat learn
```

```powershell title="PowerShell"
./infra/scripts/smoke-test.ps1 -Alias $env:AI_GATEWAY_MODEL -KeyName web-chat -Server learn
```

On GitHub, open [infra/scripts/smoke-test.sh](infra/scripts/smoke-test.sh) or
[infra/scripts/smoke-test.ps1](infra/scripts/smoke-test.ps1).

Expected output (the tool list can change as the Learn server evolves):

```text
Gateway: https://aigw-<token>.eastus2-01.ai.gateway.azure.com
Model  : HTTP 200, model=<model>, reply=ok, total_tokens=<n>
Tools  : HTTP 200, 3 tools on learn
         learn_microsoft_docs_search
         learn_microsoft_code_sample_search
         learn_microsoft_docs_fetch
Smoke test passed.
```

That one model call passed every layer: the Gateway scope request rate and cost limits, then the model's token
limit and content safety. The gateway called Foundry with its managed identity.

### Review the policy layers in the portal

Select **Policies**. **Request rate limit** and **Cost limit** show **Gateway** in the **Scope** column.
**Token rate limit** and **Content safety** show the backend model instead. Select **Models** to see that
model and the alias `chat`, and **MCP servers** to see `learn`.

### Call the alias with your Microsoft Entra identity

The dev parameters gave you **AI Gateway Models User** on the alias, so you can call it without a key:

```bash title="Bash"
export AI_GATEWAY_TOKEN="$(az account get-access-token \
  --resource https://azure-api.net/aigateway --query accessToken -o tsv)"
curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "Authorization: Bearer $AI_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in five words.\"}]}" \
  | jq -r '.choices[0].message.content'
```

```powershell title="PowerShell"
$env:AI_GATEWAY_TOKEN = az account get-access-token `
  --resource https://azure-api.net/aigateway --query accessToken -o tsv
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "Say hello in five words." })
} | ConvertTo-Json -Depth 5
$response = Invoke-RestMethod -Method Post `
  -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ Authorization = "Bearer $($env:AI_GATEWAY_TOKEN)" } `
  -ContentType "application/json" -Body $body
$response.choices[0].message.content
```

The reply is a short greeting. Your Entra identity has its own counters, separate from the `web-chat` key's.

### Check the backend identity boundary

Confirm that the Foundry account rejects keys and that only the gateway's identity has **Foundry User** on it:

```bash title="Bash"
az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_NAME" --query properties.disableLocalAuth
az role assignment list --scope "$FOUNDRY_ID" --assignee "$AI_GATEWAY_PRINCIPAL_ID" \
  --query "[].roleDefinitionName" -o tsv
```

```powershell title="PowerShell"
az cognitiveservices account show -g $env:FOUNDRY_RG -n $env:FOUNDRY_NAME --query properties.disableLocalAuth
az role assignment list --scope $env:FOUNDRY_ID --assignee $env:AI_GATEWAY_PRINCIPAL_ID `
  --query "[].roleDefinitionName" -o tsv
```

Expected output:

```text
true
Foundry User
```

### Watch the traffic in Monitoring

Select **Monitoring**. After a few minutes, **Overview** shows the smoke test's calls under the `web-chat` key
and your Entra call under your identity, and **Traces** shows each request with its policy spans. Run the smoke
test a few more times if the charts are still empty.

<!-- /steps -->

> **Checkpoint**
> The smoke test passed, **Policies** shows two **Gateway** scope policies plus the model's own, a keyless
> call with your Entra token worked, the Foundry account has `disableLocalAuth` set to `true`, and
> **Monitoring** shows the traffic.

## Go further

- **Add a content safety floor.** Add a `contentSafety` entry to `baselines.json` with the shape from
  [Set gateway-wide policy baselines](../09-gateway-baselines/README.md), so MCP servers and future models get
  it too.
- **Go keyless everywhere.** Remove entries from `appNames`, move apps to Entra groups in `modelUsers` and
  `toolUsers`, and follow [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md).
- **Keep backend traffic private.** Create the gateway with outbound virtual network integration, and give the
  Foundry account a private endpoint, as in
  [Lock down backend traffic with private networking](../18-private-networking/README.md). Pass the integration
  subnet to `gateway.bicep` as `backendSubnetId` on the first deployment. Inbound private endpoints and turning
  off the gateway's public endpoint aren't available for AI Gateway yet.
- **Protect and govern tools.** Add [Agent 365 tool threat protection](../19-tool-threat-protection/README.md)
  to sensitive MCP servers in the portal, and [govern MCP servers with Agent 365](../20-agent-365-governance/README.md).
- **Charge back by team.** Attribute tokens and cost to callers with
  [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md).

## Clean up

The Foundry model deployment, Log Analytics, and Application Insights are billed normally. Delete both resource
groups. Each command waits until the group is gone, which can take several minutes:

```bash title="Bash"
az group delete -n "$RG" --yes
az group delete -n "$FOUNDRY_RG" --yes
```

```powershell title="PowerShell"
az group delete -n $env:RG --yes
az group delete -n $env:FOUNDRY_RG --yes
```

Deleted Foundry accounts keep soft-delete records that hold their names. To reuse the name right away, purge
it. Purging is permanent.

```bash title="Bash"
az cognitiveservices account purge -g "$FOUNDRY_RG" -n "$FOUNDRY_NAME" -l "$LOCATION"
```

```powershell title="PowerShell"
az cognitiveservices account purge -g $env:FOUNDRY_RG -n $env:FOUNDRY_NAME -l $env:LOCATION
```

If you set up GitHub Actions, remove the deployment identity's role assignments and the app registration, then
delete the `dev` and `prod` environments in **Settings** › **Environments**:

```bash title="Bash"
az role assignment delete --assignee "$SP_ID" --scope "/subscriptions/$SUBSCRIPTION_ID"
az ad app delete --id "$APP_ID"
```

```powershell title="PowerShell"
az role assignment delete --assignee $env:SP_ID --scope "/subscriptions/$($env:SUBSCRIPTION_ID)"
az ad app delete --id $env:APP_ID
```

If you deployed prod, repeat the clean-up with the `aigw-prod` deployment's outputs.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The deployment fails with `InsufficientQuota`, or the model or version isn't available | The region has no `GlobalStandard` quota for `gpt-6-luna`, or doesn't offer that version | Lower `modelCapacity`, request quota, or change `modelName`, `modelVersion`, or `--location` in your parameter file and command. |
| The gateway's `provisioningState` ends in `Failed` | Azure hit an activation or managed identity conflict, often after a gateway with the same name was deleted moments before | Delete the failed gateway and its connector gateway, wait about three minutes for the identity to be cleaned up, and deploy again. |
| The smoke test prints `Waiting for the model route` until it fails with `401`, `403`, or `404` | The new Foundry User role assignment or the model route hasn't propagated yet | Wait a few minutes and run the smoke test again. If it still fails, run the backend identity checks in [Verify](#verify). |
| **Settings** in **Monitoring** shows "This legacy exporter no longer activates OTLP signals" | You deployed with `enableLegacyAppInsightsExporter` set to `true` | Select **Settings** › **General** › **Disable monitoring**, then **Configure telemetry** again with the same Application Insights resource. |
| `apply-baselines` fails with a validation error from the `PATCH` | A field in `baselines.json` doesn't match the current API contract, for example `counterKey` as a string instead of an array such as `["identity"]` | Create the policy once in the portal at **Gateway** scope, read the workspace with `az rest`, and copy that shape into `baselines.json`. |
| `azure/login` fails with `AADSTS70021: No matching federated identity record found` | The token subject doesn't match a federated credential | Check that the subject is exactly `repo:<github-org>/<github-repo>:environment:<name>` and that the GitHub environment name matches the job's `environment:`. |

## Next steps

- Keep backend traffic off the public internet with
  [Lock down backend traffic with private networking](../18-private-networking/README.md).
- Attribute usage to teams with
  [Attribute tokens and cost with OpenTelemetry](../14-otel-chargeback/README.md).
- Govern your MCP servers across the organization with
  [Govern MCP servers with Agent 365](../20-agent-365-governance/README.md).
- Read about every policy type and scope in the [AI Gateway policies documentation](https://ai.gateway.azure.com/docs/policies).
