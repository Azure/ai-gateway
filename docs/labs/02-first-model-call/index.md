---
title: Publish a Foundry model and make your first call
summary: Publish a Microsoft Foundry model deployment through your gateway with its managed identity, create a runtime API key, try the model in the Catalog playground, and call it from curl, PowerShell, Python, TypeScript, and C#.
category: foundations
level: Beginner
duration: 25
tracks: [portal, cli, iac, code]
order: 2
illustration: diagrams/request-lifecycle.svg
tags: [Microsoft Foundry, model provider, alias, API key, Chat Completions, Responses API, OpenAI SDK, managed identity]
objectives:
  - Publish a Foundry model deployment through the gateway, authenticated with the gateway's managed identity
  - Create a runtime API key and keep its value out of code
  - Call the model through the gateway with the Chat Completions and Responses APIs
  - Explain what the gateway does with a request between your app and the model
prereqs:
  - 01-provision-gateway
---

# Publish a Foundry model and make your first call

The first product team wants to use `gpt-6-luna`, which already runs in your Microsoft Foundry account. You
don't want to hand every team the Foundry endpoint and a provider key. In this lab you publish the deployment
through your gateway, give the team a runtime API key of its own, and make the first call from the playground,
a shell, and code. The gateway authenticates to Foundry with its own managed identity, so the app never sees a
Foundry credential.

![A request travels from the app through the gateway to the model and back](../assets/diagrams/request-lifecycle.svg "The gateway checks the caller's key, applies policies, calls the backend with its own identity, and records telemetry on the way back.")

## Before you begin

> [!TIP]
> On the **Bicep + azd** track, `azd up` creates its own gateway, Foundry account, model, and key, so you can skip
> this section. You need only [Cloud Shell or the azd tools](../SETUP.md#choose-where-to-run-commands), plus the
> language runtime for the code track if you follow it.

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md). You need the gateway, its resource
  group, and its runtime URL.
- A model deployment in a Microsoft Foundry (Azure AI Services) or Azure OpenAI account, for example
  `gpt-6-luna`. If you don't have one, deploy the optional template described below.
- Permission to grant the gateway access to the account: **Owner**, **User Access Administrator**, or **Role
  Based Access Control Administrator** on the Foundry account. You also need to change the gateway, for example
  **Contributor** on its resource group.
- For the CLI track and the **Verify** steps: the Azure CLI with the
  [`aigateway` extension](../SETUP.md#install-the-aigateway-extension), [signed in](../SETUP.md#sign-in-to-azure), and
  `jq` for the Bash snippets.
- For the code track: Python 3.9 or later, Node.js 22.18 or later, or the .NET 8 SDK.
- For the scripts and samples: the labs repo, [cloned](../SETUP.md#clone-the-labs-repo). Run them from the lab
  folder, `~/ai-gateway/labs/02-first-model-call`.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"
export GATEWAY="<gateway>"
export FOUNDRY_RG="<foundry-resource-group>"      # resource group of the Foundry account
export FOUNDRY_ACCOUNT="<foundry-account-name>"   # the account name, not a project or deployment name
export DEPLOYMENT="gpt-6-luna"                    # the model deployment to publish
export PROVIDER="foundry-models"                  # CLI track: the gateway provider to create

export GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
```

```powershell title="PowerShell"
$RG              = "<resource-group>"
$GATEWAY         = "<gateway>"
$FOUNDRY_RG      = "<foundry-resource-group>"     # resource group of the Foundry account
$FOUNDRY_ACCOUNT = "<foundry-account-name>"       # the account name, not a project or deployment name
$DEPLOYMENT      = "gpt-6-luna"                   # the model deployment to publish
$PROVIDER        = "foundry-models"               # CLI track: the gateway provider to create

$GATEWAY_ID = az aigateway show -g $RG -n $GATEWAY --query id -o tsv
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
```

<details>
<summary>No Foundry deployment yet? Create one with Bicep.</summary>

[infra/foundry.bicep](infra/foundry.bicep) creates an Azure AI Services account with a `gpt-6-luna`
`GlobalStandard` deployment, mirroring the reference sample. Pick a region where the model is available. Model
inference is billed per use.

```bash
az group create --name "$FOUNDRY_RG" --location eastus2
az deployment group create -g "$FOUNDRY_RG" \
  --template-file infra/foundry.bicep \
  --parameters accountName="$FOUNDRY_ACCOUNT" deploymentName="$DEPLOYMENT" \
  --query properties.outputs.deploymentId.value -o tsv
```

</details>

## How it works

Publishing a model has three parts. A **model provider** tells the gateway where the Foundry account is and
how to authenticate to it. A **backend model** registers one deployment under that provider. A callable
**alias** is the stable name that clients send in the request `model` field. Importing from Foundry creates all
three for you.

Clients call one runtime URL with a gateway API key. The gateway validates the key before anything else, runs
the policies that apply, swaps the caller's key for its own managed identity token, and forwards the request
unchanged to Foundry. The response comes back as is, and the gateway records token usage for monitoring.

| Step | What happens | Where you set it |
|---|---|---|
| Inbound authentication | An active runtime key in the `api-key` header, or as `Authorization: Bearer <key>` (what the OpenAI SDKs send), or the call fails with `401` | **Access** › **Keys** |
| Routing | `/default/models/openai/v1/chat/completions` or `/responses`, and `model` must equal an alias | Model details and its **Aliases** tab |
| Policies | Token limits, cost limits, and content safety run before the backend call | **Policies** (labs 06–09) |
| Backend authentication | The gateway's managed identity, with the **Foundry User** role on the account | Model provider |
| Telemetry | Tokens, latency, and the API key that made the call | **Monitoring** (lab 13) |

<!-- widget: request-lifecycle -->

## Publish the model and create a key

Pick one track. Each track publishes the deployment, gives you a callable alias, and creates a runtime API key.
The Bicep + azd track also creates its own gateway and Foundry deployment, so it doesn't need lab 01's gateway.

<!-- track: portal | Portal -->

### Import the deployment from Foundry

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top bar.
2. Select **Models** › **Add** › **Models from Microsoft Foundry**. (On **Home**, **Add from Microsoft Foundry** in
   the **Set up your gateway** guide starts the same import.)
3. Select the subscription and resource group of your Foundry account. The wizard discovers the deployments
   automatically. Deployments that are already in this gateway can't be selected again.
4. Select the `gpt-6-luna` deployment and keep **Managed identity** as the **Authentication method**.
5. Under **Aliases**, keep **Create an alias for each model** selected, then select **Add models**.

> [!NOTE]
> The gateway calls Foundry with its system-assigned managed identity, which needs the **Foundry User** role on
> the account. If your first call returns `403` from the backend, assign the role yourself and wait a few
> minutes for it to take effect:
>
> ```bash
> PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
> FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
> az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
>   --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID"
> ```

### Copy the callable alias

Open the imported model on **Models**. The model details show its base URL and supported interfaces, such as
**OpenAI Chat Completions** and **OpenAI Responses**. Open the **Aliases** tab and copy the alias exactly as
shown, then save it in your shell. Portal imports usually name it after the provider and the deployment, for
example `<foundry-account-name>/gpt-6-luna`.

```bash title="Bash"
export AI_GATEWAY_MODEL="<model-name>"    # the alias from the Aliases tab
```

```powershell title="PowerShell"
$env:AI_GATEWAY_MODEL = "<model-name>"    # the alias from the Aliases tab
```

### Create a runtime API key

1. Select **Access** › **Keys** › **Create API key**. Some portal versions show **Keys** directly in the left
   navigation.
2. In **Key name**, enter a name for the app that will use it, for example `app-first-call`, and select
   **Create**.
3. Copy the value from **API key created successfully**, for example with **Copy & done**. Copy it now: treat
   the value as shown only once.
4. Paste it into your shell without echoing it or writing it to a file:

```bash title="Bash"
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

> **Checkpoint**
> **Models** lists the Foundry deployment, its **Aliases** tab shows an alias, and **Access** › **Keys** shows
> `app-first-call`.

<!-- track: cli | Azure CLI -->

### Look up the Foundry account

Use the account name and resource group to look up its resource ID and endpoint. No need to copy a long ID from
the portal.

```bash title="Bash"
export FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
FOUNDRY_ENDPOINT="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query properties.endpoint -o tsv)"
export FOUNDRY_ENDPOINT="${FOUNDRY_ENDPOINT%/}/"    # the provider expects a trailing slash
echo "$FOUNDRY_ID"
```

```powershell title="PowerShell"
$FOUNDRY_ID       = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
$FOUNDRY_ENDPOINT = (az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query properties.endpoint -o tsv).TrimEnd('/') + '/'
$FOUNDRY_ID
```

### Grant the gateway access to the account

The portal import does three things for you: it grants the gateway's identity access to the account, creates the
provider, and registers the deployments. From the command line, you do each step yourself. First, give the gateway's
system-assigned identity the **Foundry User** role on the account.

```bash title="Bash"
PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID" --query id -o tsv    # Foundry User
```

```powershell title="PowerShell"
$PRINCIPAL_ID = az aigateway show -g $RG -n $GATEWAY --query identity.principalId -o tsv
az role assignment create --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal `
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID --query id -o tsv    # Foundry User
```

### Create the Foundry provider

The provider tells the gateway where the account is and to authenticate with its managed identity.

```bash title="Bash"
az aigateway model-provider create -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" \
  --kind Foundry --display-name "Foundry models" \
  --foundry "$(jq -cn --arg endpoint "$FOUNDRY_ENDPOINT" --arg id "$FOUNDRY_ID" '{
      endpoint: $endpoint, resourceIds: [$id],
      authentication: {kind: "ManagedIdentity",
                       managedIdentity: {resource: "https://cognitiveservices.azure.com/"}}}')" \
  --query "{name:name, kind:properties.kind, endpoint:properties.foundry.endpoint}"
```

```powershell title="PowerShell"
@{
  endpoint       = $FOUNDRY_ENDPOINT
  resourceIds    = @($FOUNDRY_ID)
  authentication = @{ kind = "ManagedIdentity"; managedIdentity = @{ resource = "https://cognitiveservices.azure.com/" } }
} | ConvertTo-Json -Depth 10 -Compress | Set-Content foundry.json
az aigateway model-provider create -g $RG --gateway-name $GATEWAY -n $PROVIDER `
  --kind Foundry --display-name "Foundry models" --foundry "@foundry.json" `
  --query "{name:name, kind:properties.kind, endpoint:properties.foundry.endpoint}"
Remove-Item foundry.json
```

### Register the deployment

A backend model registers one deployment under the provider. Name it after the deployment.

```bash title="Bash"
az aigateway model create -g "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" -n "$DEPLOYMENT" \
  --display-name "$DEPLOYMENT" --api-format OpenAIChatCompletions \
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses \
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$DEPLOYMENT,modelName:$DEPLOYMENT}" \
  --query "{name:name, deployment:properties.deployment.modelName}"
```

```powershell title="PowerShell"
az aigateway model create -g $RG --gateway-name $GATEWAY --provider-name $PROVIDER -n $DEPLOYMENT `
  --display-name $DEPLOYMENT --api-format OpenAIChatCompletions `
  --supported-endpoints /openai/v1/chat/completions /openai/v1/responses `
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$DEPLOYMENT,modelName:$DEPLOYMENT}" `
  --query "{name:name, deployment:properties.deployment.modelName}"
```

`--deployment-config` uses the Azure CLI shorthand syntax, so the same value works in Bash and PowerShell.

To publish more deployments, repeat this step and the next one for each name that
`az cognitiveservices account deployment list -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query "[].name" -o tsv`
returns.

> [!TIP]
> `az aigateway model create --foundry-resource-id "$FOUNDRY_ID" --deployment "$DEPLOYMENT"` does the last three
> steps in one command, like the portal import: it grants the gateway's identity **Foundry User** on the account,
> creates a provider named after the account, and registers the deployment. You can run it again safely. It doesn't
> publish an alias, so you still run the next step. This lab creates each piece itself so you see how they fit together.

### Publish an alias

Clients send an alias in the request `model` field, not the backend model name. Publish one named after the
deployment that points at the model you registered.

```bash title="Bash"
export AI_GATEWAY_MODEL="$DEPLOYMENT"
MODEL_ID="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT"
az aigateway model-alias create -g "$RG" --gateway-name "$GATEWAY" -n "$AI_GATEWAY_MODEL" \
  --backend-model resource-id="$MODEL_ID" \
  --query "{alias:properties.aliasName, target:properties.backendModels[0].resourceId}"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_MODEL = $DEPLOYMENT
$MODEL_ID = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT"
az aigateway model-alias create -g $RG --gateway-name $GATEWAY -n $env:AI_GATEWAY_MODEL `
  --backend-model resource-id="$MODEL_ID" `
  --query "{alias:properties.aliasName, target:properties.backendModels[0].resourceId}"
```

The command warns that the service doesn't enforce atomic alias creation. That's expected: it only matters when
two people create the same alias at the same time. If the alias already exists, `create` fails; change it with
`az aigateway model-alias update` and the same arguments instead.

### Create a runtime API key

`api-key create` returns metadata only. Read the generated value with `list-secrets` straight into a variable so
it never appears on screen. The service assigns the key's display name itself, so any `--display-name` works.

```bash title="Bash"
az aigateway api-key create -g "$RG" --gateway-name "$GATEWAY" -n app-first-call --display-name app-first-call \
  --query "{name:name, state:properties.state}"

AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets -g "$RG" --gateway-name "$GATEWAY" -n app-first-call \
  --query primaryKey -o tsv)" && export AI_GATEWAY_API_KEY
```

```powershell title="PowerShell"
az aigateway api-key create -g $RG --gateway-name $GATEWAY -n app-first-call --display-name app-first-call `
  --query "{name:name, state:properties.state}"

$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets -g $RG --gateway-name $GATEWAY -n app-first-call `
  --query primaryKey -o tsv
```

> **Checkpoint**
> `az aigateway model list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, provider:properties.providerKind}" -o table`
> lists your deployment with the provider `Foundry`, the alias command returned your model's ID as `target`, and
> `az aigateway api-key list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, state:properties.state}" -o table`
> shows `app-first-call` as `active`, next to the built-in `master` key.

<!-- track: iac | Bicep + azd -->

**What you need:** [Cloud Shell or the azd tools](../SETUP.md#choose-where-to-run-commands) with the
[`aigateway` extension](../SETUP.md#install-the-aigateway-extension), [signed in](../SETUP.md#sign-in-to-azure). The
template assigns a role, so you need **Owner** on the subscription, or **Contributor** and **Role Based Access Control
Administrator**. This track doesn't use your gateway from lab 01: `azd up` creates a new one, so it works on its own.

### Clone the lab

The lab is a small azd project in the
[`labs/02-first-model-call`](https://github.com/Azure/ai-gateway/tree/main/labs/02-first-model-call) folder.
[Clone the labs repo](../SETUP.md#clone-the-labs-repo) if you haven't yet, then move into the lab's folder.

```bash title="Bash or PowerShell"
cd ~/ai-gateway/labs/02-first-model-call
```

### Review the templates

`infra/main.bicep` creates the resource group `rg-<environment name>` and composes three templates. It calls lab
01's [gateway.bicep](../01-provision-gateway/infra/gateway.bicep) for the gateway, `infra/foundry.bicep` for the
Foundry account and its `gpt-6-luna` deployment, and then `infra/publish-model.bicep` to publish the deployment
through the gateway:

<!-- include: infra/main.bicep -->

`infra/foundry.bicep` creates an Azure AI Services account with local key authentication disabled, and a
`gpt-6-luna` `GlobalStandard` deployment. Skip it in your own templates if you already have a deployment:

<!-- include: infra/foundry.bicep -->

`infra/publish-model.bicep` adds to the gateway. It grants the gateway's identity the **Foundry User** role on the
account (in the account's own resource group, with
[foundry-user-role.bicep](infra/foundry-user-role.bicep)), and only then creates a Foundry model provider that
authenticates with the managed identity. It registers the deployment as a backend model with a per-caller token
limit, publishes an alias, and creates a runtime API key. It only references the gateway and the account, so you
can also deploy it on its own to a gateway you already have, with `az deployment group create`:

<!-- include: infra/publish-model.bicep -->

### Deploy with azd up

Create an azd environment named `aigw-lab02` in your current subscription, then provision everything. It takes
about three minutes.

```bash title="Bash"
azd env new aigw-lab02 --location eastus2 --subscription "$(az account show --query id --output tsv)"
azd up
```

```powershell title="PowerShell"
azd env new aigw-lab02 --location eastus2 --subscription (az account show --query id --output tsv)
azd up
```

For another region, pick one where AI Gateway and the `gpt-6-luna` model are available, as in [Find the available
regions](../SETUP.md#find-the-available-regions).

### Read the outputs and the key

Set the variables from **Before you begin**, which the next sections and **Verify** use, from azd's environment
values. Template outputs never contain the key value, so read it from the gateway straight into a variable, where
it never shows on screen.

```bash title="Bash"
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY="$(azd env get-value AI_GATEWAY_NAME)"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_ID)"
export FOUNDRY_RG="$RG"
export FOUNDRY_ACCOUNT="$(azd env get-value FOUNDRY_ACCOUNT_NAME)"
export DEPLOYMENT="$(azd env get-value AI_GATEWAY_BACKEND_MODEL)"
export PROVIDER="$(azd env get-value AI_GATEWAY_PROVIDER)"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
echo "$AI_GATEWAY_MODEL"
```

```powershell title="PowerShell"
$RG                     = azd env get-value AZURE_RESOURCE_GROUP
$GATEWAY                = azd env get-value AI_GATEWAY_NAME
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$FOUNDRY_RG             = $RG
$FOUNDRY_ACCOUNT        = azd env get-value FOUNDRY_ACCOUNT_NAME
$DEPLOYMENT             = azd env get-value AI_GATEWAY_BACKEND_MODEL
$PROVIDER               = azd env get-value AI_GATEWAY_PROVIDER
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$env:AI_GATEWAY_MODEL   = azd env get-value AI_GATEWAY_MODEL
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
$env:AI_GATEWAY_MODEL
```

> **Checkpoint**
> `azd up` ended with `SUCCESS`, and the last command printed the alias, `gpt-6-luna`. In the portal, select the
> new gateway in the gateway switcher: **Models** lists `gpt-6-luna`.

### Change the token limit

The template gives each caller 10,000 tokens per minute on the model. The value comes from the
`TOKENS_PER_MINUTE` azd environment value, with the default in `infra/main.parameters.json`. To change it, set the
value and provision again. Only the model changes.

```bash title="Bash"
azd env set TOKENS_PER_MINUTE 20000
azd provision
```

```powershell title="PowerShell"
azd env set TOKENS_PER_MINUTE 20000
azd provision
```

<!-- /tracks -->

> [!IMPORTANT]
> Role assignments can take a few minutes to take effect. Until then, calls can fail with `403` from the
> backend. Wait and retry.

## Make your first call

Use the same alias and key everywhere. The gateway exposes the OpenAI-compatible base URL
`<gateway URL>/default/models/openai/v1`, so OpenAI SDKs only need a different base URL and the runtime key.

<!-- track: portal | Playground -->

### Try the model in Catalog

1. Select **Catalog** and pick your model.
2. Send a prompt in the built-in playground, for example `Write a one-sentence status update.`
3. Copy the endpoint and the code samples (cURL, PowerShell 7+, Python, TypeScript, and .NET) for your app.

> [!TIP]
> If the playground asks you to **Sign in again**, your portal session expired. Sign in and resend the prompt.

<!-- track: cli | curl and PowerShell -->

### Call Chat Completions

```bash title="Bash"
curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Write a one-sentence status update.\"}]}" \
  | jq -r '.choices[0].message.content'
```

```powershell title="PowerShell"
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "Write a one-sentence status update." })
} | ConvertTo-Json -Depth 5

$reply = Invoke-RestMethod -Method Post `
  -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
$reply.choices[0].message.content
```

### Call the Responses API

```bash title="Bash"
curl -sS "${AI_GATEWAY_URL%/}/default/models/openai/v1/responses" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"input\":\"Summarize what an AI gateway does in one sentence.\"}" \
  | jq -r '[.output[] | select(.type == "message") | .content[] | select(.type == "output_text") | .text] | join("")'
```

```powershell title="PowerShell"
$body = @{ model = $env:AI_GATEWAY_MODEL; input = "Summarize what an AI gateway does in one sentence." } |
  ConvertTo-Json

$reply = Invoke-RestMethod -Method Post `
  -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/responses" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
($reply.output | Where-Object type -eq "message").content.text -join ""
```

### Run both calls with a script

The script prints the HTTP status and the reply for each interface, which makes failures easier to read.

<!-- include: infra/call-model.sh -->

On GitHub, open [infra/call-model.sh](infra/call-model.sh) or [infra/call-model.ps1](infra/call-model.ps1).

```bash title="Bash"
./infra/call-model.sh
```

```powershell title="PowerShell"
./infra/call-model.ps1
```

<!-- track: code | Code -->

### Install the SDK

Each sample reads `AI_GATEWAY_URL`, `AI_GATEWAY_MODEL`, and `AI_GATEWAY_API_KEY` from the environment, so the
key never lives in code. Run the commands from the lab folder.

```bash title="Python"
cd infra
pip install -r requirements.txt     # the openai package
```

```bash title="TypeScript"
cd infra
npm install                         # the openai npm package
```

```bash title="C#"
cd infra/dotnet
dotnet restore                      # no extra packages: HttpClient and System.Text.Json
```

### Call the model from code

The OpenAI SDKs send their API key as `Authorization: Bearer <key>`, which the model endpoint accepts, so the
runtime key goes straight into the SDK. Don't also add an `api-key` default header: the gateway rejects a request
that has both with `400`. The .NET sample uses `HttpClient`, like the .NET samples in the AI Gateway docs, so it
sends the `api-key` header explicitly.

```python title="Python"
import os

from openai import OpenAI

gateway_url = os.environ["AI_GATEWAY_URL"].rstrip("/")
model = os.environ["AI_GATEWAY_MODEL"]

client = OpenAI(
    base_url=f"{gateway_url}/default/models/openai/v1",
    api_key=os.environ["AI_GATEWAY_API_KEY"],
)

response = client.responses.create(model=model, input="Write a one-sentence status update.")
print(f"Responses API:    {response.output_text}")

completion = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Describe an AI gateway in one sentence."}],
)
print(f"Chat Completions: {completion.choices[0].message.content}")
```

```typescript title="TypeScript"
import OpenAI from "openai";

const gatewayUrl = process.env.AI_GATEWAY_URL!.replace(/\/+$/, "");
const model = process.env.AI_GATEWAY_MODEL!;

const client = new OpenAI({
  baseURL: `${gatewayUrl}/default/models/openai/v1`,
  apiKey: process.env.AI_GATEWAY_API_KEY!,
});

const response = await client.responses.create({ model, input: "Write a one-sentence status update." });
console.log(`Responses API:    ${response.output_text}`);

const completion = await client.chat.completions.create({
  model,
  messages: [{ role: "user", content: "Describe an AI gateway in one sentence." }],
});
console.log(`Chat Completions: ${completion.choices[0].message.content}`);
```

```csharp title="C#"
using System.Net.Http.Json;
using System.Text.Json;

var gatewayUrl = Environment.GetEnvironmentVariable("AI_GATEWAY_URL")!.TrimEnd('/');
var model = Environment.GetEnvironmentVariable("AI_GATEWAY_MODEL")!;

using var http = new HttpClient { BaseAddress = new Uri($"{gatewayUrl}/default/models/openai/v1/") };
http.DefaultRequestHeaders.Add("api-key", Environment.GetEnvironmentVariable("AI_GATEWAY_API_KEY"));

using var reply = await http.PostAsJsonAsync("chat/completions", new
{
    model,
    messages = new[] { new { role = "user", content = "Describe an AI gateway in one sentence." } },
});
reply.EnsureSuccessStatusCode();
using var json = JsonDocument.Parse(await reply.Content.ReadAsStringAsync());
Console.WriteLine(json.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString());
```

The full samples in `infra` also call the Responses API from C# and print token usage: open
[first-call.py](infra/first-call.py), [first-call.ts](infra/first-call.ts), and
[dotnet/Program.cs](infra/dotnet/Program.cs).

### Run the sample

```bash title="Python"
python first-call.py
```

```bash title="TypeScript"
node first-call.ts      # Node.js 22.18 or later; on older versions run: npx tsx first-call.ts
```

```bash title="C#"
dotnet run
```

Expected output (your text differs):

```text
Responses API:    All systems are running normally and the release is on track for Friday.
Chat Completions: An AI gateway is a governed entry point that routes, secures, and observes calls to AI models and tools.
```

<!-- /tracks -->

> **Checkpoint**
> The model answers through the gateway, and you never used a Foundry key or endpoint.

## Verify

<!-- steps -->

### Confirm the model is published

```bash title="Bash"
az aigateway model list -g "$RG" --gateway-name "$GATEWAY" --query "[].{name:name, provider:properties.providerKind}" -o table
```

```powershell title="PowerShell"
az aigateway model list -g $RG --gateway-name $GATEWAY --query "[].{name:name, provider:properties.providerKind}" -o table
```

The list includes your deployment. In the portal, **Catalog** lists the model too.

### Get a 200 with the key

```bash title="Bash"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
```

```powershell title="PowerShell"
$body = @{ model = $env:AI_GATEWAY_MODEL; messages = @(@{ role = "user"; content = "ping" }) } | ConvertTo-Json -Depth 5
(Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body -SkipHttpErrorCheck).StatusCode
```

Expect `HTTP 200`.

### Get a 401 without the key

Send the same request without the `api-key` header. The gateway rejects it before any policy runs or the
backend is called.

```bash title="Bash"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}"
```

```powershell title="PowerShell"
(Invoke-WebRequest -Method Post -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -ContentType "application/json" -Body $body -SkipHttpErrorCheck).StatusCode
```

Expect `HTTP 401`.

### Check that the alias is what clients call

Change one character in `model` and resend the request with the key. The call fails with `404` and
`model_not_found` because `model` must match an alias exactly. Backend model names and Foundry deployment names
aren't callable unless an alias with that name exists.

<!-- /steps -->

> **Checkpoint**
> You got `200` with the key, `401` without it, and an error for a name that isn't an alias.

## Go further

- **Publish more deployments.** After you add deployments in Foundry, rerun the portal import, or repeat the
  CLI track's **Register the deployment** and **Publish an alias** steps for each new deployment.
- **Add a per-caller token limit.** The Bicep + azd track already sets `tokensPerMinute`, and its **Change the
  token limit** step changes it. Learn how limits behave in
  [Throttle tokens per caller with token limits](../06-token-limits/README.md).
- **Publish models from other providers.** Put OpenAI, Anthropic, AWS Bedrock, or Google Vertex AI models behind
  the same gateway in [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md).

## Clean up

The portal and CLI tracks of the next labs reuse the gateway, model, alias, and key, so keep them until you finish
the labs you plan to do.

<!-- track: cli | Portal and Azure CLI -->

### Delete what you published

When you're done with the labs, delete the key, the alias, and the provider, then remove the role assignment that
the gateway received on the Foundry account. Delete the alias first: deleting the provider also deletes its
models, but not the aliases that point at them. Deleting a model from the gateway doesn't delete the Foundry
deployment. The commands use the names from the CLI track. If you imported in the portal, use the provider
and alias names shown on **Models**.

```bash title="Bash"
az aigateway api-key delete -g "$RG" --gateway-name "$GATEWAY" -n app-first-call --yes
az aigateway model-alias delete -g "$RG" --gateway-name "$GATEWAY" -n "$DEPLOYMENT" --yes
az aigateway model-provider delete -g "$RG" --gateway-name "$GATEWAY" -n "$PROVIDER" --yes

PRINCIPAL_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query identity.principalId -o tsv)"
FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
az role assignment delete --assignee "$PRINCIPAL_ID" --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID"
```

```powershell title="PowerShell"
az aigateway api-key delete -g $RG --gateway-name $GATEWAY -n app-first-call --yes
az aigateway model-alias delete -g $RG --gateway-name $GATEWAY -n $DEPLOYMENT --yes
az aigateway model-provider delete -g $RG --gateway-name $GATEWAY -n $PROVIDER --yes

$PRINCIPAL_ID = az aigateway show -g $RG -n $GATEWAY --query identity.principalId -o tsv
$FOUNDRY_ID = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
az role assignment delete --assignee $PRINCIPAL_ID --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID
```

If you created the Foundry account with `infra/foundry.bicep`, delete its resource group with
`az group delete --name "$FOUNDRY_RG"`.

<!-- track: iac | Bicep + azd -->

### Delete everything azd created

You don't need to keep this gateway for the Bicep + azd tracks of later labs: each of them creates its own. If you
continue with the portal or CLI track of [lab 03](../03-multi-provider-aliases/README.md), you can keep it instead:
it has what that lab needs, the `gpt-6-luna` alias and the `app-first-call` key, in the resource group
`rg-aigw-lab02`.

Otherwise, in the `ai-gateway/labs/02-first-model-call` folder, delete the resource group with the gateway and the
Foundry account. [`--purge`](../SETUP.md#delete-what-azd-created) also purges the soft-deleted Foundry account. It
takes up to fifteen minutes.

```bash
azd down --purge --force
```

`azd down` doesn't touch the gateway from lab 01, because this track created its own.

<!-- /tracks -->

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` from the gateway | The key is missing, misspelled, or deleted | Send an active runtime key in the `api-key` header or as the SDK API key. Create a new key if you lost the value. |
| `400` with `Specify either an API key or an Authorization header, not both` | The client sends an `api-key` header and an `Authorization` header, such as an SDK placeholder key | Pass the runtime key as the SDK API key and remove the `api-key` default header. |
| `403` mentioning permissions on the Foundry account | The gateway's identity lacks **Foundry User**, or the assignment hasn't propagated yet | Wait a few minutes. If it persists, assign the role as shown in the portal track. |
| `404` with `model_not_found` | `model` doesn't match an alias exactly | Copy the alias from the model's **Aliases** tab or from **Catalog**. |
| `400` `unsupported_parameter` for `max_tokens` or `temperature` | `gpt-6-luna` is a reasoning model | Send `max_completion_tokens` instead of `max_tokens`. Set `temperature` only together with `reasoning_effort: "none"`. |
| `200` with empty `content` and `finish_reason` `length` | Reasoning used the whole `max_completion_tokens` budget | Raise the budget, or send `reasoning_effort: "none"` for short, direct replies. |
| The Responses API call fails while Chat Completions works | The model doesn't advertise the Responses interface | Check the supported interfaces on the model details page and call only those. |
| The import wizard doesn't list your account | It's already imported into this gateway, or you can't read it in that subscription | Check **Models** for an existing provider, or ask for read access to the account. |
| `AuthorizationFailed` on `roleAssignments` during deployment | You can't create role assignments on the Foundry account | Ask for **Role Based Access Control Administrator** on the account, or have an owner grant the role. |

## Next steps

- [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md): add other providers and retarget aliases.
- [Issue and rotate runtime API keys](../10-api-keys/README.md): give each app its own key and rotate it safely.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): protect the deployment from noisy neighbors.
- Docs: [Access models through AI Gateway](https://ai.gateway.azure.com/docs/model-access) and
  [Microsoft Foundry and AI Gateway](https://ai.gateway.azure.com/docs/foundry).
