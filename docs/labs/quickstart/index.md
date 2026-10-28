---
title: Your first model call in 5 minutes
summary: Learn the building blocks of Azure AI Gateway, create a gateway with a Microsoft Foundry model in the portal, the Azure CLI, or Bicep with azd, and make your first model call, all in about five minutes.
category: foundations
level: Beginner
duration: 5
tracks: [portal, cli, iac]
order: -1
status: new
illustration: diagrams/quickstart.svg
tags: [quick start, getting started, first call, gateway, model provider, alias, API key, portal, Azure CLI, Cloud Shell, azd, Bicep, infrastructure as code]
objectives:
  - Name the building blocks that every AI Gateway call goes through
  - Create a gateway, publish a Foundry model behind an alias, and create a runtime API key in the portal, the Azure CLI, or Bicep with azd
  - Make your first model call through the gateway the way an app does, with an alias and a runtime API key
prereqs: []
---

# Your first model call in 5 minutes

Azure AI Gateway gives your apps and agents one governed endpoint for models and tools. In five minutes you create a
gateway, put a Microsoft Foundry model behind it, and call that model the way an app does: with the gateway's URL, an
alias in the `model` field, and a runtime API key. Click through the AI Gateway portal, paste a few Azure CLI
commands into Azure Cloud Shell, or clone a Bicep template and deploy it with one `azd up`.

![Create the gateway, a Foundry model, a provider, an alias, and a runtime key in the AI Gateway portal, with the Azure CLI in Cloud Shell, or with a Bicep template and azd up. Then your app calls the alias with the key, and the gateway routes the call to Foundry with its managed identity](../assets/diagrams/quickstart.svg "Set up once, in the portal, in Cloud Shell, or with azd up. Then every call goes through the gateway: it checks the key, routes the alias, and signs in to Foundry with its own identity.")

## Before you begin

You need an Azure subscription where you can create resources and role assignments, for example **Owner**, or
**Contributor** plus **Role Based Access Control Administrator**. The gateway gets a role on your Foundry account, so
that it can call the model with its own identity. Each track lists the tools that it needs at its start.

### Find the available regions

AI Gateway is in public preview, and the regions where you can create a gateway change as it rolls out. To list the
current ones, run this in [Azure Cloud Shell](https://shell.azure.com):

```bash title="Bash"
regions=$(az provider show --namespace Microsoft.ApiManagement \
  --query "resourceTypes[?resourceType=='aigateways'].locations | [0]" -o json)
az account list-locations -o json |
  jq -r --argjson regions "$regions" '
    ["Display Name", "Name"],
    (.[] | select(.displayName as $d | $regions | index($d)) | [.displayName, .name])
    | @tsv
  ' | column -t -s $'\t'
```

```powershell title="PowerShell"
$regions = az provider show --namespace Microsoft.ApiManagement `
  --query "resourceTypes[?resourceType=='aigateways'].locations | [0]" -o json | ConvertFrom-Json
az account list-locations -o json | ConvertFrom-Json |
  Where-Object { $regions -contains $_.displayName } |
  Format-Table @{ Label = 'Display Name'; Expression = { $_.displayName } }, @{ Label = 'Name'; Expression = { $_.name } }
```

Use a value from the **Name** column, such as `eastus2`, as the location in the Azure CLI and Bicep + azd tracks. The
portal lists the regions where it can create gateways, which can be fewer. Those two tracks also create the Foundry
account in the gateway's region, so pick a region where `gpt-6-luna` is available too. This command prints its
deployment types in a region, and prints nothing if the model isn't available there:

```bash title="Bash or PowerShell"
az cognitiveservices model list --location eastus2 --query "[?model.name=='gpt-6-luna'].model.skus[].name" -o tsv
```

## How it works

Every call that goes through AI Gateway uses the same building blocks. In this quick start you create one of each.

| Building block | What it does | In this quick start |
| :-- | :-- | :-- |
| **Gateway** | The Azure resource (`Microsoft.ApiManagement/aigateways`) that gives your apps one runtime URL for models and tools | Your gateway, at `https://<gateway>.<location>-01.ai.gateway.azure.com` |
| **Model provider** | A connection to a backend. The gateway signs in to it with its own managed identity, so your apps never hold a backend key | Your Foundry account. The Azure CLI and Bicep tracks name the provider `foundry-models` |
| **Model** | A backend deployment that the gateway can route to | The Foundry deployment `gpt-6-luna` |
| **Alias** | The name that apps send in the `model` field. The gateway routes the alias to one or more models | `<foundry-account-name>/gpt-6-luna` in the portal, `gpt-6-luna` in the Azure CLI and Bicep tracks |
| **Runtime API key** | Identifies the app that calls the gateway, for limits, cost, and monitoring | `app-first-call` |

Your app calls the OpenAI-compatible base URL `<gateway URL>/default/models/openai/v1`, so any OpenAI SDK works with
a different base URL and the runtime key. For the full tour, watch the 3-minute video in
[How Azure AI Gateway works](../00-how-ai-gateway-works/README.md).

## Create a gateway and make your first call

Pick one track. Each one creates the same building blocks, makes your first call through the gateway, and ends with
how to clean up.

<!-- track: portal | Portal -->

**What you need:** a browser, and a model deployment in a Microsoft Foundry account, for example `gpt-6-luna`.

<details>
<summary>No Foundry deployment yet? Create one in Cloud Shell.</summary>

Open [Azure Cloud Shell](https://shell.azure.com) in Bash and paste these commands. They create a Foundry account with
a `gpt-6-luna` deployment in a new resource group, in a minute or two. Then create the gateway in the same resource
group, so that you can clean up with one command. Model inference is billed per use.

```bash title="Bash"
RG="rg-aigw-quickstart"; FOUNDRY="aigw$(openssl rand -hex 3)"
az group create --name "$RG" --location eastus2 --output none
az cognitiveservices account create --resource-group "$RG" --name "$FOUNDRY" --location eastus2 \
  --kind AIServices --sku S0 --custom-domain "$FOUNDRY" --yes --output none
az cognitiveservices account deployment create --resource-group "$RG" --name "$FOUNDRY" \
  --deployment-name gpt-6-luna --model-name gpt-6-luna --model-version 2026-09-22 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10 --output none
echo "Foundry account $FOUNDRY in $RG"
```

</details>

### Create the gateway

1. Open the [AI Gateway portal](https://ai.gateway.azure.com) and sign in. For your first gateway, the portal opens
   **Create AI gateway** right away. Otherwise, open the gateway switcher in the top bar and select
   **Create new gateway**.

   ![The gateway switcher open in the top bar, with Recent gateways, View all gateways, and Create new gateway](../assets/screens/quickstart-01-switcher.webp "The gateway switcher lists your recent gateways. Create new gateway opens the Create AI gateway dialog.")

2. Enter a **Name**, or select **Generate a new name**. Then choose your **Subscription**, a **Resource group**, and
   a **Region**. For the resource group, select **New**, or select **Existing** and pick the resource group of your
   Foundry account, so that you can clean up both with one command.

   ![The Create AI gateway dialog with a name, the Existing resource group rg-aigw-quickstart, and the East US 2 region](../assets/screens/quickstart-02-create.webp "Create AI gateway: a generated name, the existing resource group of the Foundry account, and East US 2.")

3. Keep the **Advanced** defaults and select **Create gateway**. **All gateways** opens and shows the provisioning
   status, which moves from **Activating** to **Succeeded** in a few minutes. Then the portal selects your new
   gateway.

   ![All gateways with the banner Gateway creation is in progress and the new gateway in the Activating state](../assets/screens/quickstart-03-provisioning.webp "All gateways while the gateway provisions. You can keep using other gateways in the meantime.")

### Import the model from Foundry

1. **Home** opens with the **Set up your gateway** guide. Under **Add a model**, select
   **Add from Microsoft Foundry**.

   ![Home with the new gateway in the switcher and the Set up your gateway guide, with Add from Microsoft Foundry highlighted](../assets/screens/quickstart-04-home.webp "Set up your gateway walks you through three steps: add a model, test a model, and apply policies.")

   You can also start from **Models** › **Add** › **Models from Microsoft Foundry**.

   ![The Models page with the Add menu open on Models from Microsoft Foundry](../assets/screens/quickstart-05-add-menu.webp "Models › Add imports models from Microsoft Foundry or a custom provider, or creates an alias for a model that you already added.")

2. **Add models from Microsoft Foundry** discovers the model deployments in your subscriptions and selects all of
   them. In **Resource groups**, select only the resource group of your Foundry account. Then check that **Models**
   selects only your Foundry account with `gpt-6-luna`.
3. Keep **Managed identity** as the **Authentication method**, with the system-assigned managed identity, and keep
   **Create an alias for each model** selected. Then select **Add models**.

   ![Add models from Microsoft Foundry, filtered to one resource group, with Managed identity, Create an alias for each model, one selected Foundry account with gpt-6-luna, and the Add models button highlighted](../assets/screens/quickstart-06-import.webp "Filter by resource group, so that you import only the deployment that you need. The gateway calls Foundry with its managed identity.")

4. **Models** opens. The **Backend models** tab lists `gpt-6-luna`, and the **Aliases** tab shows the alias that
   apps call: `<foundry-account-name>/gpt-6-luna`. Note the alias.

   ![The Aliases tab of Models with the alias aigwb92bd1/gpt-6-luna, its backend model gpt-6-luna, and its provider](../assets/screens/quickstart-07-alias.webp "Each alias is named after the Foundry account and the deployment, and routes to the backend model gpt-6-luna.")

### Create a runtime API key

1. Select **Access**, then the **Keys** tab, then **Create API key**.

   ![Access with the Keys tab, the Create API key button, and the new key app-first-call in the list](../assets/screens/quickstart-08-keys.webp "Access › Keys lists the built-in all-access subscription and your keys. After the next step, app-first-call appears here.")

2. Enter `app-first-call` as the **Key name**, then select **Create**.

   ![The Create API key dialog with the key name app-first-call and the Create button](../assets/screens/quickstart-09-key-create.webp "Give the key a name that identifies the app. Limits, cost, and monitoring use it.")

3. In **API key created successfully**, select **Copy & done** to copy the key. Keep it somewhere safe: you paste it
   in the next steps. You can view, rotate, or delete it later in **Access** › **Keys**.

   ![The API key created successfully dialog with a masked key, the key name, and the Copy & done button](../assets/screens/quickstart-10-key-done.webp "The key stays masked until you select Show. Copy & done copies it and closes the dialog.")

### Make your first call

Call the model through the gateway in the playground, with your new key, the way an app does.

1. Select **Catalog**, then select your model.

   ![The Catalog with the model card aigwb92bd1/gpt-6-luna](../assets/screens/quickstart-11-catalog.webp "The Catalog lists the models and MCP servers that apps can call through this gateway.")

2. Under **Authentication**, choose `app-first-call` as the **API key**, so that the playground calls the gateway
   with your new key. Then send a prompt, for example `In one sentence, what does an AI gateway do?`.

   ![The model page with the API key app-first-call, the prompt, and the model's reply](../assets/screens/quickstart-12-playground.webp "The playground calls the gateway's endpoint with the key that you choose, and shows the reply, the latency, and the tokens.")

3. Optional: to make the same call from code, select **Continue in code**. It shows the endpoint URL and snippets
   for cURL, the OpenAI SDK, LangChain, Vercel AI, the GitHub Copilot SDK, and Microsoft Agent Framework, plus a
   prompt that installs the AI Gateway plugin in your coding agent.

   ![Continue in code with the cURL snippet selected, which calls the alias with the api-key header](../assets/screens/quickstart-13-code.webp "The cURL snippet has your gateway's URL and alias, and reads the key from the AI_GATEWAY_API_KEY environment variable.")

To run the cURL snippet, open [Azure Cloud Shell](https://shell.azure.com) in Bash, paste your key at this prompt so
that it never shows on screen, and then paste the snippet:

```bash title="Bash"
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

> **Checkpoint:** the playground answered with the key `app-first-call`. Your gateway is live, and your app never
> needs a Foundry key: only the gateway's managed identity calls Foundry.

### Clean up

To keep exploring, skip this step: [lab 03](../03-multi-provider-aliases/README.md) and the labs after it work on this
gateway. On the labs site, save the resource group and the gateway name in **Your values**. Otherwise, delete the
gateway.

1. Open the gateway switcher in the top bar and select **View all gateways**.

2. On your gateway's row, select **More actions** (**⋮**), and then select **Delete**.

   ![All gateways filtered to lucky-brook, with the More actions menu open on its row and Delete marked](../assets/screens/quickstart-14-delete.webp "The More actions menu on a gateway's row: open the gateway in the Azure portal, copy its resource ID, or delete it.")

3. To confirm, select **Delete** in the dialog. The row shows **Deleting** until Azure removes the gateway, in about
   five minutes.

   ![The dialog Delete "lucky-brook-5340"? with the Cancel and Delete buttons, and Delete marked](../assets/screens/quickstart-15-delete-confirm.webp "Deleting a gateway removes its models, aliases, keys, and policies. It can't be undone.")

Deleting the gateway keeps its resource group and your Foundry account. If you created them in Cloud Shell for this
quick start, delete the resource group and purge the Foundry account there too: deleted Foundry accounts stay
soft-deleted for 48 hours and keep counting against your quota until you purge them.

```bash title="Bash"
FOUNDRY="$(az cognitiveservices account list --resource-group rg-aigw-quickstart --query "[0].name" --output tsv)"
az group delete --name rg-aigw-quickstart --yes
az cognitiveservices account purge --name "$FOUNDRY" --resource-group rg-aigw-quickstart --location eastus2
```

> **Checkpoint:** after you refresh the page, **All gateways** no longer lists your gateway.

<!-- track: cli | Azure CLI -->

**What you need:** [Azure Cloud Shell](https://shell.azure.com), in Bash or PowerShell. It's already signed in and has
the Azure CLI, `curl`, and `jq`. A local Azure CLI 2.75 or later, signed in with `az login`, works too. The track
installs the `aigateway` CLI extension and creates the Foundry deployment for you.

### Set your variables

Paste the block for your shell. It installs or upgrades the `aigateway` extension, then sets the names. A random
suffix keeps the gateway and Foundry account names globally unique.

```bash title="Bash"
curl -fsSL https://aka.ms/aigateway-cli-install | sh

export RG="rg-aigw-quickstart"
export LOCATION="eastus2"                     # or another region from Find the available regions
SUFFIX="$(openssl rand -hex 3)"
export GATEWAY="aigw-$SUFFIX"                 # part of the runtime URL
export FOUNDRY="aigw$SUFFIX"                  # the Foundry account and its subdomain
export DEPLOYMENT="gpt-6-luna"
export PROVIDER="foundry-models"

export SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
export GATEWAY_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
```

```powershell title="PowerShell"
irm https://aka.ms/aigateway-cli-install-ps | iex

$RG         = "rg-aigw-quickstart"
$LOCATION   = "eastus2"                       # or another region from Find the available regions
$SUFFIX     = [guid]::NewGuid().ToString("N").Substring(0, 6)
$GATEWAY    = "aigw-$SUFFIX"                  # part of the runtime URL
$FOUNDRY    = "aigw$SUFFIX"                   # the Foundry account and its subdomain
$DEPLOYMENT = "gpt-6-luna"
$PROVIDER   = "foundry-models"

$SUBSCRIPTION_ID = az account show --query id --output tsv
$GATEWAY_ID      = "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
```

### Start creating the gateway

Register the resource providers, which is a one-time step for each subscription, and create a resource group. Then
create the gateway's companion connector gateway, which the extension doesn't create, and the gateway itself. With
`--no-wait`, Azure keeps provisioning the gateway in the background, so you can move on right away.

```bash title="Bash"
for ns in Microsoft.ApiManagement Microsoft.Web Microsoft.CognitiveServices; do az provider register --namespace "$ns" --wait; done
az group create --name "$RG" --location "$LOCATION" --output none

az rest --method put --output none \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/$GATEWAY?api-version=2026-05-01-preview" \
  --body "$(jq -cn --arg l "$LOCATION" '{location: $l, properties: {}}')"
az aigateway create --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION" --system-assigned true --no-wait
```

```powershell title="PowerShell"
foreach ($ns in "Microsoft.ApiManagement", "Microsoft.Web", "Microsoft.CognitiveServices") { az provider register --namespace $ns --wait }
az group create --name $RG --location $LOCATION --output none

@{ location = $LOCATION; properties = @{} } | ConvertTo-Json -Compress | Set-Content body.json
az rest --method put --output none --body "@body.json" `
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/${GATEWAY}?api-version=2026-05-01-preview"
Remove-Item body.json
az aigateway create --resource-group $RG --name $GATEWAY --location $LOCATION --system-assigned true --no-wait
```

### Deploy the model in Foundry

While the gateway provisions, create a Foundry account with a `gpt-6-luna` deployment. Then give the gateway's
managed identity the **Foundry User** role on the account. The gateway calls the model with this identity, so your
apps never hold a Foundry key.

```bash title="Bash"
az cognitiveservices account create --resource-group "$RG" --name "$FOUNDRY" --location "$LOCATION" \
  --kind AIServices --sku S0 --custom-domain "$FOUNDRY" --yes --output none
az cognitiveservices account deployment create --resource-group "$RG" --name "$FOUNDRY" \
  --deployment-name "$DEPLOYMENT" --model-name gpt-6-luna --model-version 2026-09-22 --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10 --output none

export FOUNDRY_ID="$(az cognitiveservices account show --resource-group "$RG" --name "$FOUNDRY" --query id --output tsv)"
PRINCIPAL_ID="$(az aigateway show --resource-group "$RG" --name "$GATEWAY" --query identity.principalId --output tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID" --output none    # Foundry User
```

```powershell title="PowerShell"
az cognitiveservices account create --resource-group $RG --name $FOUNDRY --location $LOCATION `
  --kind AIServices --sku S0 --custom-domain $FOUNDRY --yes --output none
az cognitiveservices account deployment create --resource-group $RG --name $FOUNDRY `
  --deployment-name $DEPLOYMENT --model-name gpt-6-luna --model-version 2026-09-22 --model-format OpenAI `
  --sku-name GlobalStandard --sku-capacity 10 --output none

$FOUNDRY_ID   = az cognitiveservices account show --resource-group $RG --name $FOUNDRY --query id --output tsv
$PRINCIPAL_ID = az aigateway show --resource-group $RG --name $GATEWAY --query identity.principalId --output tsv
az role assignment create --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal `
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID --output none    # Foundry User
```

### Publish the model

Wait for the gateway, then publish the deployment in three steps: a provider that points at the Foundry account and
signs in with the managed identity, a model for the deployment, and an alias that apps send in the `model` field.

```bash title="Bash"
az aigateway wait --resource-group "$RG" --name "$GATEWAY" --created

az aigateway model-provider create --resource-group "$RG" --gateway-name "$GATEWAY" --name "$PROVIDER" --output none \
  --kind Foundry --display-name "Foundry models" \
  --foundry "$(jq -cn --arg e "https://$FOUNDRY.cognitiveservices.azure.com/" --arg id "$FOUNDRY_ID" '{endpoint: $e,
      resourceIds: [$id], authentication: {kind: "ManagedIdentity", managedIdentity: {resource: "https://cognitiveservices.azure.com/"}}}')"
az aigateway model create --resource-group "$RG" --gateway-name "$GATEWAY" --provider-name "$PROVIDER" --name "$DEPLOYMENT" \
  --api-format OpenAIChatCompletions --supported-endpoints /openai/v1/chat/completions /openai/v1/responses \
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$DEPLOYMENT,modelName:$DEPLOYMENT}" --output none
az aigateway model-alias create --resource-group "$RG" --gateway-name "$GATEWAY" --name "$DEPLOYMENT" --only-show-errors \
  --backend-model resource-id="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT" \
  --query properties.aliasName --output tsv
```

```powershell title="PowerShell"
az aigateway wait --resource-group $RG --name $GATEWAY --created

@{ endpoint       = "https://$FOUNDRY.cognitiveservices.azure.com/"
   resourceIds    = @($FOUNDRY_ID)
   authentication = @{ kind = "ManagedIdentity"; managedIdentity = @{ resource = "https://cognitiveservices.azure.com/" } } } |
  ConvertTo-Json -Depth 10 -Compress | Set-Content foundry.json
az aigateway model-provider create --resource-group $RG --gateway-name $GATEWAY --name $PROVIDER --output none `
  --kind Foundry --display-name "Foundry models" --foundry "@foundry.json"
az aigateway model create --resource-group $RG --gateway-name $GATEWAY --provider-name $PROVIDER --name $DEPLOYMENT `
  --api-format OpenAIChatCompletions --supported-endpoints /openai/v1/chat/completions /openai/v1/responses `
  --deployment-config "{resourceId:$FOUNDRY_ID/deployments/$DEPLOYMENT,modelName:$DEPLOYMENT}" --output none
az aigateway model-alias create --resource-group $RG --gateway-name $GATEWAY --name $DEPLOYMENT --only-show-errors `
  --backend-model resource-id="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT" `
  --query properties.aliasName --output tsv
Remove-Item foundry.json
```

### Create a runtime API key

Create a key for your app. Then read the key, the gateway URL, and the alias into environment variables, so that
the key never shows on screen.

```bash title="Bash"
az aigateway api-key create --resource-group "$RG" --gateway-name "$GATEWAY" --name app-first-call \
  --display-name app-first-call --output none

export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --resource-group "$RG" --gateway-name "$GATEWAY" \
  --name app-first-call --query primaryKey --output tsv)"
export AI_GATEWAY_URL="https://$(az aigateway show --resource-group "$RG" --name "$GATEWAY" --query properties.frontend.defaultHostname --output tsv)"
export AI_GATEWAY_MODEL="$DEPLOYMENT"
echo "$AI_GATEWAY_URL"
```

```powershell title="PowerShell"
az aigateway api-key create --resource-group $RG --gateway-name $GATEWAY --name app-first-call `
  --display-name app-first-call --output none

$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --resource-group $RG --gateway-name $GATEWAY `
  --name app-first-call --query primaryKey --output tsv
$env:AI_GATEWAY_URL     = "https://" + (az aigateway show --resource-group $RG --name $GATEWAY --query properties.frontend.defaultHostname --output tsv)
$env:AI_GATEWAY_MODEL   = $DEPLOYMENT
$env:AI_GATEWAY_URL
```

> **Checkpoint:** the alias command printed `gpt-6-luna`, and the last command printed your gateway's runtime URL,
> for example `https://aigw-abc123.eastus2-01.ai.gateway.azure.com`.

### Make your first call

Send a Chat Completions request to the gateway's OpenAI-compatible base URL, the way an app does: the alias in the
`model` field and the key in the `api-key` header.

```bash title="Bash"
curl -sS "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"In one sentence, what does an AI gateway do?\"}]}" \
  | jq -r '.choices[0].message.content // .error.message'
```

```powershell title="PowerShell"
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "In one sentence, what does an AI gateway do?" })
} | ConvertTo-Json -Depth 5
$reply = Invoke-RestMethod -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
$reply.choices[0].message.content
```

> **Checkpoint:** the model answers in one sentence. Your gateway is live, and your app never needed a Foundry key:
> only the gateway's managed identity calls Foundry. If you get `403` or `404` in the first minute, the gateway's new
> role on the Foundry account is still taking effect. Wait a minute and run the call again.

To see what you created, open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top
bar: **Models**, **Access** › **Keys**, and the **Catalog** playground.

### Clean up

To keep exploring, skip this step: [lab 03](../03-multi-provider-aliases/README.md) and the labs after it work on this
gateway. On the labs site, save the resource group and the gateway name (`$RG` and `$GATEWAY`) in **Your values**.
Otherwise, delete the resource group, which holds the gateway and the Foundry account. Then purge the Foundry account:
deleted Foundry accounts stay soft-deleted for 48 hours and keep counting against your quota until you purge them.

```bash title="Bash"
az group delete --name "$RG" --yes
az cognitiveservices account purge --name "$FOUNDRY" --resource-group "$RG" --location "$LOCATION"
```

```powershell title="PowerShell"
az group delete --name $RG --yes
az cognitiveservices account purge --name $FOUNDRY --resource-group $RG --location $LOCATION
```

If Cloud Shell timed out, set `RG`, `FOUNDRY`, and `LOCATION` again with the names that you used: the suffix in
**Set your variables** is random.

> **Checkpoint:** `az group exists --name $RG` prints `false`.

<!-- track: iac | Bicep + azd -->

**What you need:** [Azure Cloud Shell](https://shell.azure.com), in Bash or PowerShell. It's already signed in and has
the Azure Developer CLI (`azd`), the Azure CLI, Git, `curl`, and `jq`. Locally,
[install azd](https://aka.ms/azd-install), the Azure CLI, and Git, and sign in with `azd auth login` and `az login`.
The template creates the Foundry deployment for you.

### Clone the template

The template is a small azd project in the
[`labs/quickstart`](https://github.com/Azure/ai-gateway/tree/main/labs/quickstart) folder of the GitHub repo: an
`azure.yaml` and a Bicep file for each scope. Clone the repo, then move into that folder. The clone also gets the
other labs, which you can use next.

```bash title="Bash"
git clone https://github.com/Azure/ai-gateway.git
cd ai-gateway/labs/quickstart
```

```powershell title="PowerShell"
git clone https://github.com/Azure/ai-gateway.git
Set-Location ai-gateway/labs/quickstart
```

`infra/main.bicep` creates the resource group `rg-<environment name>` and passes unique names to
`infra/resources.bicep`, which creates the building blocks in the same order as the other tracks:

<!-- include: infra/resources.bicep -->

### Deploy with azd up

Create an azd environment named `aigw-quickstart` in your current subscription, so that azd doesn't prompt you. Then
provision everything with one command. It takes about three minutes.

```bash title="Bash"
azd env new aigw-quickstart --location eastus2 --subscription "$(az account show --query id --output tsv)"
azd up
```

```powershell title="PowerShell"
azd env new aigw-quickstart --location eastus2 --subscription (az account show --query id --output tsv)
azd up
```

For another region, use its name from [Find the available regions](#find-the-available-regions). azd saves the
template's outputs, like the gateway URL and the alias, as environment values. The API key isn't an output, so it
never lands in a file or a deployment log.

### Read the URL, the alias, and the key

Read the outputs, and read the key from the gateway into an environment variable, so that it never shows on screen.

```bash title="Bash"
export AI_GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export AI_GATEWAY_MODEL="$(azd env get-value AI_GATEWAY_MODEL)"
export AI_GATEWAY_API_KEY="$(az aigateway api-key list-secrets --ids "$(azd env get-value AI_GATEWAY_ID)/apiKeys/app-first-call" \
  --query primaryKey --output tsv)"
echo "$AI_GATEWAY_URL"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_URL     = azd env get-value AI_GATEWAY_URL
$env:AI_GATEWAY_MODEL   = azd env get-value AI_GATEWAY_MODEL
$GATEWAY_ID             = azd env get-value AI_GATEWAY_ID
$env:AI_GATEWAY_API_KEY = az aigateway api-key list-secrets --ids "$GATEWAY_ID/apiKeys/app-first-call" `
  --query primaryKey --output tsv
$env:AI_GATEWAY_URL
```

> **Checkpoint:** `azd up` ended with `SUCCESS`, and the last command printed your gateway's runtime URL, for example
> `https://aigw-abc123.eastus2-01.ai.gateway.azure.com`.

### Make your first call

Send a Chat Completions request to the gateway's OpenAI-compatible base URL, the way an app does: the alias in the
`model` field and the key in the `api-key` header.

```bash title="Bash"
curl -sS "$AI_GATEWAY_URL/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"In one sentence, what does an AI gateway do?\"}]}" \
  | jq -r '.choices[0].message.content // .error.message'
```

```powershell title="PowerShell"
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = "user"; content = "In one sentence, what does an AI gateway do?" })
} | ConvertTo-Json -Depth 5
$reply = Invoke-RestMethod -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body
$reply.choices[0].message.content
```

> **Checkpoint:** the model answers in one sentence. Your gateway is live, and your app never needed a Foundry key:
> only the gateway's managed identity calls Foundry. If you get `403` or `404` in the first minute, the gateway's new
> role on the Foundry account is still taking effect. Wait a minute and run the call again.

To see what you created, open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway in the top
bar: **Models**, **Access** › **Keys**, and the **Catalog** playground.

### Clean up

To keep exploring, skip this step: [lab 03](../03-multi-provider-aliases/README.md) and the labs after it work on this
gateway. Otherwise, in the `ai-gateway/labs/quickstart` folder, delete everything that `azd up` created. `--purge` also purges
the Foundry account, which would otherwise stay soft-deleted for 48 hours and keep counting against your quota. It
takes about ten minutes.

```bash title="Bash"
azd down --purge --force
```

```powershell title="PowerShell"
azd down --purge --force
```

> **Checkpoint:** `azd down` ended with `SUCCESS`. The resource group `rg-aigw-quickstart` is gone, and you can delete
> the `ai-gateway` folder.

<!-- /tracks -->

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| A subscription is disabled in **Create AI gateway** | You can't write API Management or connector gateway resources in it | Pick another subscription, or ask for **Contributor** on it. |
| `AuthorizationFailed` on `Microsoft.Authorization/roleAssignments` | You can create resources but not role assignments | Ask for **Owner**, or **Role Based Access Control Administrator**, on the resource group. |
| `LocationNotAvailableForResourceType` | AI Gateway isn't available in the region | Pick a region from [Find the available regions](#find-the-available-regions). |
| `RequestDisallowedByAzure`: `The selected region is currently not accepting new customers` | The region has AI Gateway, but your subscription can't create new resources there | Pick another region from the list. |
| `InvalidResourceProperties`: `The specified SKU 'GlobalStandard' for model 'gpt-6-luna 2026-09-22' is not supported in this region` | `gpt-6-luna` isn't available in the region | Pick a region where the model check in [Find the available regions](#find-the-available-regions) prints `GlobalStandard`. |
| `InsufficientQuota` on the model deployment | The subscription has no `gpt-6-luna` capacity left in the region | Start again in another region: set `LOCATION` in the Azure CLI track, or run `azd env new` with a new name and another `--location` in the Bicep + azd track. Or free capacity in [Foundry](https://ai.azure.com). |
| `InvalidResourceGroupLocation` from `azd up` | The resource group `rg-<environment name>` already exists in another region | Run `azd env new` with a new environment name, or delete the old resource group. |
| `403` or `404` from the gateway in the first minute | The gateway's role on the Foundry account, or the new alias, is still taking effect | Wait a minute and call again. |
| `403` from the backend that doesn't go away | The gateway's managed identity has no role on the Foundry account | Assign it **Foundry User** on the account, as in the Azure CLI track's **Deploy the model in Foundry** step, and wait a few minutes. |
| `401` | The key is missing, wrong, or in the wrong header | Send it in the `api-key` header, or as `Authorization: Bearer <key>`. In the portal, copy it again from **Access** › **Keys**. |
| `400` that mentions authentication | The request has both an `api-key` and an `Authorization` header | Send only one of them. |
| `The subscription is not registered to use namespace` | A resource provider isn't registered yet | Run the `az provider register` loop from **Start creating the gateway**, then try again. |

## Next steps

- [How Azure AI Gateway works](../00-how-ai-gateway-works/README.md): a 3-minute video and a guided tour of every building block.
- [Provision your AI Gateway](../01-provision-gateway/README.md) and [Publish a Foundry model and make your first call](../02-first-model-call/README.md): the same setup in depth, with Bicep, the Responses API, and more SDKs.
- [Publish models from any provider behind stable aliases](../03-multi-provider-aliases/README.md): put models from several providers behind names your apps keep.
- [Throttle tokens per caller with token limits](../06-token-limits/README.md): give every app its own allowance.
