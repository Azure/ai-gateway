---
title: Route an alias across models by priority and weight
summary: Put two Foundry models behind one alias, canary a new model version with an 80/20 weighted split, then prefer one model by priority, all without changing the model name that clients send.
category: models
level: Intermediate
duration: 25
tracks: [portal, cli, iac]
order: 3.5
status: new
illustration: diagrams/alias-routing.svg
tags: [model alias, routing, priority, weight, canary, A/B test, load balancing, provisioned throughput]
objectives:
  - Explain how priority and weight decide which backend model serves a request
  - Put two backend models behind one alias with an 80/20 weighted split
  - Tell which backend model served each request from the response
  - Prefer one backend model by priority, then promote the other without changing clients
prereqs:
  - 02-first-model-call
---

# Route an alias across models by priority and weight

Your team wants to try `gpt-6.1-sol`, but every app already sends `"model": "chat"`, and nobody wants a big-bang
switch. In this lab you put the current model and the new one behind the same alias, send a fifth of the traffic
to the new model, count where the requests land, and then use priority to choose which model is preferred. The
apps never change the model name they send.

![Clients call one alias. The gateway prefers the backend models with the lowest priority number and splits their traffic by weight](../assets/diagrams/alias-routing.svg "Priority picks the tier. Weight splits the traffic inside it.")

<!-- widget: alias-routing {"alias":"chat"} -->

## Before you begin

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, both models, the alias, and a key, so you can skip
> this section. You need only [Azure Cloud Shell](https://shell.azure.com), or the Azure Developer CLI (`azd`), the
> Azure CLI, Git, and `jq` on your machine.

- Complete [Publish a Foundry model and make your first call](../02-first-model-call/README.md). You need the
  gateway, a runtime API key, and the `gpt-6-luna` backend model. Lab 02 also gave the gateway the
  **Foundry User** role on your Foundry account, which covers the new deployment in this lab.
- Permission to change the gateway, for example **Contributor** on its resource group, and to create deployments
  in the Foundry account.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login`, the `aigateway` extension ([install it](../01-provision-gateway/README.md#before-you-begin)), and
  `jq` for the Bash snippets. The PowerShell commands need PowerShell 7 or later.
- Optional: [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md)
  explains aliases in more depth.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export FOUNDRY_RG="<foundry-resource-group>"     # resource group of the Foundry account from lab 02
export FOUNDRY_ACCOUNT="<foundry-account-name>"
export PROVIDER="foundry-models"                 # the gateway provider that holds gpt-6-luna
export PRIMARY="gpt-6-luna"                      # the backend model that serves today's traffic
export CANDIDATE="gpt-6.1-sol"                   # the new model to try
export CANDIDATE_VERSION="2026-09-29"
export ALIAS="chat"                              # the name that clients send in "model"

export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
# Paste the gateway runtime key from lab 02. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG                = "<resource-group>"
$GATEWAY           = "<gateway>"
$FOUNDRY_RG        = "<foundry-resource-group>"    # resource group of the Foundry account from lab 02
$FOUNDRY_ACCOUNT   = "<foundry-account-name>"
$PROVIDER          = "foundry-models"              # the gateway provider that holds gpt-6-luna
$PRIMARY           = "gpt-6-luna"                  # the backend model that serves today's traffic
$CANDIDATE         = "gpt-6.1-sol"                 # the new model to try
$CANDIDATE_VERSION = "2026-09-29"
$ALIAS             = "chat"                        # the name that clients send in "model"

$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$FOUNDRY_ID = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
# Paste the gateway runtime key from lab 02. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

The CLI and Bicep tracks of lab 02 name the provider `foundry-models`. A portal import names it after your
Foundry account. To check, list the backend models. The **Provider** column shows the provider of each one.

```bash title="Bash"
az aigateway model list -g "$RG" --gateway-name "$GATEWAY" -o table
```

```powershell title="PowerShell"
az aigateway model list -g $RG --gateway-name $GATEWAY -o table
```

Deploy the candidate model in the same Foundry account as `gpt-6-luna`. Pick a region where the model is
available. Model inference is billed per use.

```bash title="Bash"
az cognitiveservices account deployment create -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" \
  --deployment-name "$CANDIDATE" --model-name "$CANDIDATE" --model-version "$CANDIDATE_VERSION" \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10 \
  --query "{name:name, state:properties.provisioningState}"
```

```powershell title="PowerShell"
az cognitiveservices account deployment create -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT `
  --deployment-name $CANDIDATE --model-name $CANDIDATE --model-version $CANDIDATE_VERSION `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10 `
  --query "{name:name, state:properties.provisioningState}"
```

## How it works

An alias holds a list of backend models. Each one has a priority and a weight:

| Setting | Values | Default | What it does |
|---|---|---|---|
| **Priority** | Whole number from 0 to 100 | `0` | Lower numbers are preferred. Requests go to the backend models with the lowest priority number. |
| **Weight** | Whole number from 1 to 100 | `1` | Splits traffic among the backend models that share a priority, in proportion to their weights. |

A backend model's **Share within priority** is its weight divided by the sum of the weights at its priority.
Weights `80` and `20` give 80% and 20%; weights `3` and `1` give 75% and 25%. With one backend model, the alias
behaves like the single-target aliases of labs 02 and 03.

Pick the values from the job you need to do:

| Scenario | Priority | Weight |
|---|---|---|
| **Canary a new model version** | Same for both | Small share for the new version, for example `95` and `5`, then raise it |
| **A/B test two models** | Same for both | Equal, for example `50` and `50` |
| **Balance deployments** across regions or providers | Same for all | In proportion to each deployment's capacity, for example `3` and `1` |
| **Prefer purchased capacity** | Provisioned deployment `0`, pay-as-you-go `1` | Any |

A few rules keep every request answerable:

- Each backend model can appear only once in an alias.
- All backend models must support at least one interface in common, for example **OpenAI Chat Completions**.
  Mixing an Anthropic Messages model with an OpenAI model in one alias fails.
- The response tells you which backend served the request: the `model` field holds the backend's model name and
  version, for example `gpt-6.1-sol-2026-09-29`, and Foundry models also return an `x-ms-served-model` header.

> [!IMPORTANT]
> Priority sets a preference, not a guaranteed failover. In our tests, when the preferred backend returned an error
> such as `429` or `404`, the gateway passed that error to the client instead of retrying a lower-priority
> backend. Test how your gateway behaves under throttling before you rely on priority for
> availability, and keep retries in your clients.

## Split traffic 80/20 between two models

Register the candidate model in the gateway, then create the `chat` alias with both models at priority `0` and
weights `80` and `20`.

<!-- track: portal | Portal -->

### Import the candidate model

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top bar.
2. Select **Models** › **Add** › **Models from Microsoft Foundry**.
3. Select the subscription and resource group of your Foundry account, then select the `gpt-6.1-sol`
   deployment. Keep **Managed identity** as the **Authentication method**.
4. Select **Add models**. If the wizard also creates an alias named after the model, keep it; this lab doesn't
   use it.

### Create the chat alias

1. Select **Models** › **Aliases** › **Add alias**.
2. On **Basics**, set **Alias name** to `chat` and **Description** to `Canary: 80/20 between the current and the
   new model`. Select **Next**.
3. On **Select models**, select `gpt-6-luna` and `gpt-6.1-sol` in **Available backend models**. Select **Next**.
4. On **Priority and weights**, keep **Priority** at `0` for both models. Set **Weight** to `80` for
   `gpt-6-luna` and `20` for `gpt-6.1-sol`. **Share within priority** shows `80%` and `20%`. Select **Next**.
5. On **Review**, check the shares, then select **Create**.

![The Priority and weights step of Create alias, with Priority, Weight, and Share within priority columns for each backend model](../assets/screens/models-alias-routing.png "Priority and weights. This example from the product documentation uses three GPT-4o deployments: one at priority 0, and two at priority 1 that split 75/25.")

> **Checkpoint**
> **Models** › **Aliases** lists `chat`. Its **Backend models** tab shows `gpt-6-luna` and `gpt-6.1-sol`, both at
> priority `0`, with weights `80` and `20`.

<!-- track: cli | Azure CLI -->

### Register the candidate model

A backend model registers one deployment under the provider. This is the same command as in lab 02, with the
model version.

```bash title="Bash"
az aigateway model create -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$CANDIDATE" \
  --display-name "$CANDIDATE" --api-format OpenAIChatCompletions \
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses \
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$CANDIDATE,modelName:$CANDIDATE,modelVersion:$CANDIDATE_VERSION}" \
  --query "{name:name, version:properties.deployment.modelVersion}"
```

```powershell title="PowerShell"
az aigateway model create -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $CANDIDATE `
  --display-name $CANDIDATE --api-format OpenAIChatCompletions `
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses `
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$CANDIDATE,modelName:$CANDIDATE,modelVersion:$CANDIDATE_VERSION}" `
  --query "{name:name, version:properties.deployment.modelVersion}"
```

### Create the chat alias

Each `--backend-model` adds an entry to the alias's `backendModels` list, with a `resource-id`, a `priority`, and
a `weight`. With more than one backend model, each entry needs both a priority and a weight.

```bash title="Bash"
export MODELS="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"
az aigateway model-alias create -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" \
  --description "Canary: 80/20 between the current and the new model" \
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=80 \
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=0 weight=20 \
  --only-show-errors --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
$MODELS = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"
az aigateway model-alias create -g $RG --gateway-name $GATEWAY -n $ALIAS `
  --description "Canary: 80/20 between the current and the new model" `
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=80 `
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=0 weight=20 `
  --only-show-errors --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

If the alias already exists, `create` fails. Change it with `az aigateway model-alias update` and the same
arguments instead.

> **Checkpoint**
> The output shows `gpt-6-luna  priority 0  weight 80` and `gpt-6.1-sol  priority 0  weight 20`.

<!-- track: iac | Bicep + azd -->

**What you need:** [Azure Cloud Shell](https://shell.azure.com), in Bash or PowerShell, or [azd](https://aka.ms/azd-install),
the Azure CLI with the `aigateway` extension, Git, and `jq` on your machine, signed in with `azd auth login` and
`az login`. This track doesn't use your gateway from lab 02: `azd up` creates a new one, so it works on its own.

### Clone the lab

The lab is a small azd project in the
[`labs/22-model-routing`](https://github.com/Azure/ai-gateway/tree/main/labs/22-model-routing) folder of the GitHub
repo. Clone the repo and move into that folder. If you cloned it for the quick start, move into
`ai-gateway/labs/22-model-routing` instead.

```bash title="Bash"
git clone https://github.com/Azure/ai-gateway.git
cd ai-gateway/labs/22-model-routing
```

```powershell title="PowerShell"
git clone https://github.com/Azure/ai-gateway.git
Set-Location ai-gateway/labs/22-model-routing
```

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and calls the quick start's
[resources.bicep](../quickstart/infra/resources.bicep) for the gateway, `gpt-6-luna`, its default alias, and the
`app-first-call` key. Then it deploys the candidate model in the same Foundry account and publishes the `chat`
alias:

<!-- include: infra/main.bicep -->

`infra/candidate-deployment.bicep` deploys `gpt-6.1-sol` next to `gpt-6-luna`. The gateway's **Foundry User** role
on the account already covers it:

<!-- include: infra/candidate-deployment.bicep -->

`infra/alias-routing.bicep` registers the candidate deployment under the existing provider and publishes the alias.
It only references `gpt-6-luna`, so that model's settings stay as they are. Its `strategy` parameter switches
between a weighted split and a priority preference. You can also deploy it on its own to the gateway from lab 02:

<!-- include: infra/alias-routing.bicep -->

### Deploy with azd up

Create an azd environment named `aigw-lab22` in your current subscription, then provision everything. It takes
about five minutes.

```bash title="Bash"
azd env new aigw-lab22 --location eastus2 --subscription "$(az account show --query id --output tsv)"
azd up
```

```powershell title="PowerShell"
azd env new aigw-lab22 --location eastus2 --subscription (az account show --query id --output tsv)
azd up
```

For another region, pick one where AI Gateway and the `gpt-6-luna` and `gpt-6.1-sol` models are available, as in [Find
the available regions](../01-provision-gateway/README.md#find-the-available-regions). The parameters come from azd
environment values, with the defaults in `infra/main.parameters.json`: `ROUTING_STRATEGY` (`weighted`),
`ROUTING_CANDIDATE_WEIGHT` (`20`), `CANDIDATE_MODEL` (`gpt-6.1-sol`), and `CANDIDATE_MODEL_VERSION` (`2026-09-29`).

### Read the outputs and the key

Set the variables that the next sections and **Verify** use from azd's environment values, read the key from the
gateway so that it never shows on screen, then print the alias's routes.

```bash title="Bash"
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_ID)"
export PROVIDER="$(azd env get-value AI_GATEWAY_PROVIDER)"
export PRIMARY="$(azd env get-value AI_GATEWAY_BACKEND_MODEL)"
export CANDIDATE="$(azd env get-value AI_GATEWAY_CANDIDATE_MODEL)"
export ALIAS="$(azd env get-value AI_GATEWAY_MODEL)"
export MODELS="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"

az aigateway model-alias show -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$PROVIDER               = azd env get-value AI_GATEWAY_PROVIDER
$PRIMARY                = azd env get-value AI_GATEWAY_BACKEND_MODEL
$CANDIDATE              = azd env get-value AI_GATEWAY_CANDIDATE_MODEL
$ALIAS                  = azd env get-value AI_GATEWAY_MODEL
$MODELS                 = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models"
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv

az aigateway model-alias show -g $RG --gateway-name $GATEWAY -n $ALIAS --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`, and the last command printed `gpt-6-luna  priority 0  weight 80` and
> `gpt-6.1-sol  priority 0  weight 20`.

<!-- /tracks -->

## Watch the split

Send 20 requests to `chat` and count which backend model answered each one. The script sends one request every
half second and reads the `model` field of each response.

```bash title="Bash"
./infra/count-models.sh "$ALIAS" 20
```

```powershell title="PowerShell"
./infra/count-models.ps1 -Alias $ALIAS -Count 20
```

```text
Requests per backend model:
  16 gpt-6-luna-2026-09-22
   4 gpt-6.1-sol-2026-09-29
```

In our tests the gateway interleaved the two models, four requests to `gpt-6-luna` and then one to
`gpt-6.1-sol`, so 20 requests split exactly 16 and 4. Plan around the shares, not the exact order.

To see the header for a single call:

```bash title="Bash"
curl -sS -D - -o /dev/null "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\": \"$ALIAS\", \"max_completion_tokens\": 16, \"messages\": [{\"role\": \"user\", \"content\": \"Hi\"}]}" |
  grep -i "^x-ms-served-model"
```

```powershell title="PowerShell"
$body = @{ model = $ALIAS; max_completion_tokens = 16; messages = @(@{ role = "user"; content = "Hi" }) } | ConvertTo-Json -Compress
(Invoke-WebRequest -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body).Headers["x-ms-served-model"]
```

> **Checkpoint**
> About four of every five requests show `gpt-6-luna-…`, and the rest show `gpt-6.1-sol-…`. The client sent
> `"model": "chat"` every time.

## Prefer one model by priority

The canary looks good, but finance wants `gpt-6-luna` to handle the traffic until the new model is approved.
Give `gpt-6.1-sol` priority `1`. It stays in the alias, ready to promote, but requests go to `gpt-6-luna`.

<!-- track: portal | Portal -->

### Edit the alias

1. In **Models** › **Aliases**, open `chat` and select **Edit**.
2. Select **Next** until you reach **Priority and weights**.
3. Set **Priority** to `1` for `gpt-6.1-sol` and set both weights to `1`. `gpt-6-luna` now shows `100%` at
   priority `0`, and `gpt-6.1-sol` shows `100%` at priority `1`.
4. Select **Next**, then **Save**. New requests use the new settings immediately.

> **Checkpoint**
> The alias **Backend models** tab shows `gpt-6-luna` at priority `0` and `gpt-6.1-sol` at priority `1`.

<!-- track: cli | Azure CLI -->

### Update the priorities

`model-alias update` replaces the whole `backendModels` list, so pass both backend models.

```bash title="Bash"
az aigateway model-alias update -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" \
  --description "Prefer the current model" \
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=1 \
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=1 weight=1 \
  --only-show-errors --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
az aigateway model-alias update -g $RG --gateway-name $GATEWAY -n $ALIAS `
  --description "Prefer the current model" `
  --backend-model resource-id="$MODELS/$PRIMARY" priority=0 weight=1 `
  --backend-model resource-id="$MODELS/$CANDIDATE" priority=1 weight=1 `
  --only-show-errors --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

> **Checkpoint**
> The output shows `gpt-6-luna  priority 0  weight 1` and `gpt-6.1-sol  priority 1  weight 1`.

<!-- track: iac | Bicep + azd -->

### Provision the priority strategy

Set `ROUTING_STRATEGY` to `priority` and provision again. Only the alias changes: `gpt-6-luna` keeps priority `0`,
and `gpt-6.1-sol` gets priority `1`.

```bash title="Bash"
azd env set ROUTING_STRATEGY priority
azd provision
```

```powershell title="PowerShell"
azd env set ROUTING_STRATEGY priority
azd provision
```

To go back to the weighted split, run `azd env set ROUTING_STRATEGY weighted` and `azd provision`. Change
`ROUTING_CANDIDATE_WEIGHT` the same way to canary in steps.

> **Checkpoint**
> `azd provision` ended with `SUCCESS`. **Read the alias** in **Verify** shows `gpt-6-luna  priority 0  weight 1`
> and `gpt-6.1-sol  priority 1  weight 1`.

<!-- /tracks -->

## Verify

<!-- steps -->

### Read the alias

```bash title="Bash"
az aigateway model-alias show -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --query properties.backendModels -o json |
  jq -r '.[] | "\(.resourceId | split("/") | last)  priority \(.priority)  weight \(.weight)"'
```

```powershell title="PowerShell"
az aigateway model-alias show -g $RG --gateway-name $GATEWAY -n $ALIAS --query properties.backendModels -o json |
  ConvertFrom-Json | ForEach-Object { '{0}  priority {1}  weight {2}' -f ($_.resourceId -split '/')[-1], $_.priority, $_.weight }
```

### Count the requests again

```bash title="Bash"
./infra/count-models.sh "$ALIAS" 10
```

```powershell title="PowerShell"
./infra/count-models.ps1 -Alias $ALIAS -Count 10
```

> **Checkpoint**
> All 10 requests show `gpt-6-luna-…`. `gpt-6.1-sol` stays in the alias at priority `1`.

### Promote the new model

To finish the rollout, swap the priorities: `gpt-6.1-sol` at `0`, `gpt-6-luna` at `1`. Use the portal, or run
the `az aigateway model-alias update` command from the previous section with `$PRIMARY` and `$CANDIDATE`
swapped. Run the count again: every request now shows `gpt-6.1-sol-…`. To roll back, swap them again. Clients
never change.

<!-- /steps -->

## Go further

- **Canary in steps.** Move the weights from `95`/`5` to `80`/`20` to `50`/`50` while you watch errors, latency,
  and cost per model in [Monitor usage, cost, and traces](../13-monitoring/README.md). Weights must be at least
  `1`, so to stop sending traffic to a model, give it a higher priority number or remove it from the alias.
- **Prefer provisioned throughput.** Put a provisioned deployment at priority `0` and a pay-as-you-go
  deployment of the same model at priority `1`, so purchased capacity is used first. Test what happens when the
  provisioned deployment is saturated before you depend on it.
- **Balance regions or providers.** Register the same model from two Foundry accounts, or from Foundry and a
  custom provider, and give them weights in proportion to their quota.
- **Limit each model and the alias.** A token limit on a backend model, as in
  [Throttle tokens per caller with token limits](../06-token-limits/README.md), applies to that model. A limit
  on the alias applies to every request that calls `chat`.

## Clean up

Keep the gateway, the runtime key, and `gpt-6-luna` from lab 02. Later labs use them. Remove what you added in
this lab: the alias first, then the backend model, then the Foundry deployment.

<!-- track: portal | Portal -->

### Remove the alias and the candidate model

Open `chat` in **Models** › **Aliases** and select **Delete**. Requests that use the alias fail immediately; the
backend models stay in the gateway. Then delete the `gpt-6.1-sol` model, and any alias that the import created for
it, from **Models**. Finally, delete the `gpt-6.1-sol` deployment from your Foundry account, for example with the
last command of the CLI track.

<!-- track: cli | Azure CLI -->

### Remove the alias and the candidate model

```bash title="Bash"
az aigateway model-alias delete -g "$RG" --gateway-name "$GATEWAY" -n "$ALIAS" --yes
az aigateway model delete -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$CANDIDATE" --yes
az cognitiveservices account deployment delete -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --deployment-name "$CANDIDATE"
```

```powershell title="PowerShell"
az aigateway model-alias delete -g $RG --gateway-name $GATEWAY -n $ALIAS --yes
az aigateway model delete -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $CANDIDATE --yes
az cognitiveservices account deployment delete -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --deployment-name $CANDIDATE
```

If an alias that the portal import created still points to `gpt-6.1-sol`, delete that alias before the model.

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

In the `ai-gateway/labs/22-model-routing` folder, delete the resource group with the gateway, the Foundry account
and its two deployments, and the `chat` alias. `--purge` also purges the Foundry account, which would otherwise stay
soft-deleted for 48 hours and keep counting against your quota. It takes about ten minutes.

```bash
azd down --purge --force
```

<!-- /tracks -->

`azd down` doesn't touch the gateway, key, and `gpt-6-luna` from lab 02, because the Bicep + azd track created its
own gateway.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Select models with at least one common API format." | The selected backend models don't share an interface, for example an Anthropic Messages model and an OpenAI Chat Completions model | Put models that share an interface in the same alias. |
| "Weight must be a whole number from 1 to 100.", `Each target's weight must be a whole number from 1 to 100.`, or `weight must be between 1 and 100.` | A weight is `0`, negative, or above `100` | To stop traffic to a model, raise its priority number or remove it. |
| "Priority must be a whole number from 0 to 100.", `Each target's priority must be a whole number from 0 to 100.`, or `priority must be between 0 and 100.` | A priority is outside `0` to `100` | Use `0` for the preferred tier and higher numbers for the others. |
| "Each backend model can appear only once." or `backendModels must not contain duplicate model identities.` | The same backend model is listed twice | Combine the entries and adjust the weight. |
| `This model alias already exists; use model-alias update.` | You ran `az aigateway model-alias create` for an alias that exists | Run `az aigateway model-alias update` with the same arguments. |
| All requests go to one model | The models have different priorities, so only the lowest number receives traffic | Give the models the same priority to split by weight. |
| `404` with `DeploymentNotFound` | The candidate backend model points to a Foundry deployment that doesn't exist | Create the deployment, or fix `deployment.resourceId` on the backend model. |
| `429` from the preferred model | The preferred deployment is out of capacity, and the gateway returns the error | Retry in the client, add capacity, or spread traffic with weights at the same priority. |

## Next steps

- [Monitor usage, cost, and traces](../13-monitoring/README.md)
- [Throttle tokens per caller with token limits](../06-token-limits/README.md)
- [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md)
- [October 16 release: priority and weighted model routing](https://ai.gateway.azure.com/docs/releases/2026-10-16)
