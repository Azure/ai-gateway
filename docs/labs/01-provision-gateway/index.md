---
title: Provision your AI Gateway
summary: Create the shared AI Gateway that your apps and agents will call, from the AI Gateway portal, the Azure CLI, or Bicep, then take a guided tour of the portal.
category: foundations
level: Beginner
duration: 15
tracks: [portal, cli, iac]
order: 1
illustration: diagrams/provisioning.svg
tags: [provisioning, aigateways, az aigateway, Bicep, managed identity, regions]
objectives:
  - Create an AI Gateway in East US 2 or Sweden Central from the portal, the Azure CLI, or Bicep
  - Find the gateway's runtime URL and its system-assigned managed identity
  - Confirm that the runtime endpoint answers over HTTPS
  - Navigate the AI Gateway portal and know which area manages what
prereqs: []
---

# Provision your AI Gateway

Your platform team is about to put every model and tool that the company's apps and agents use behind one
governed entry point. Before anyone can publish a model, issue a key, or set a budget, you need the gateway
itself. In this lab you create a shared AI Gateway, find its runtime URL and managed identity, and learn your
way around the portal so you're ready for the rest of the labs.

<!-- video: media/walkthrough.mp4 | Narrated walkthrough: create an AI Gateway in the portal and tour it (3 min) -->

![What provisioning creates: you choose a name, resource group, and region; Azure creates the connector gateway, the AI Gateway, and its managed identity; you get a runtime URL, a default workspace, and the portal](../assets/diagrams/provisioning.svg "One gateway per environment is the usual starting point. Every later lab publishes models, tools, keys, and policies on it.")

## Before you begin

- An Azure subscription with access to the AI Gateway preview. The AI Gateway tier is free during public
  preview. Connected services, such as Foundry inference and Application Insights, are billed normally.
- Permission to create the gateway, for example **Contributor** on the resource group, or on the subscription
  if you create a new resource group. Creating a gateway needs write access to both API Management and
  connector gateways.
- For the portal track: a browser and your Azure account.
- For the CLI and IaC tracks and the **Verify** steps: the
  [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login`, the [`aigateway` extension](https://github.com/Azure/ai-gateway/tree/main/cli), and `jq` for the Bash snippets.
- Recommended reading: [How AI Gateway works](../00-how-ai-gateway-works/README.md).

Install or upgrade the `aigateway` extension, then check that the CLI loads it. The installer downloads the
published release, verifies it, and needs no Azure sign-in. Every later lab uses the same extension.

```bash title="Bash"
curl -fsSL https://aka.ms/aigateway-cli-install | sh
az aigateway version
```

```powershell title="PowerShell"
irm https://aka.ms/aigateway-cli-install-ps | iex
az aigateway version
```

`az aigateway version` prints the extension version and the API version it calls, `2025-09-01-preview`.

> [!NOTE]
> The labs use `az aigateway` commands wherever the extension covers an operation. A few operations, such as
> registering a model or setting policies, aren't in the extension yet. For those, the labs call the Azure
> Resource Manager REST API with `az rest` and say why.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
az account set --subscription "<subscription-id>"

export RG="<resource-group>"               # for example rg-ai-gateway-labs
export GATEWAY="<gateway>"                 # globally unique, 24 characters or fewer, part of the runtime URL
export LOCATION="<location>"               # eastus2 or swedencentral
export SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
```

```powershell title="PowerShell"
az account set --subscription "<subscription-id>"

$RG              = "<resource-group>"      # for example rg-ai-gateway-labs
$GATEWAY         = "<gateway>"             # globally unique, 24 characters or fewer, part of the runtime URL
$LOCATION        = "<location>"            # eastus2 or swedencentral
$SUBSCRIPTION_ID = az account show --query id -o tsv
```

> [!IMPORTANT]
> During public preview, AI Gateway is available in **East US 2** (`eastus2`) and **Sweden Central**
> (`swedencentral`). Create the resource group in one of these regions so that defaults line up. The gateway
> name must be 1–24 characters: letters, digits, and hyphens, starting with a letter and not ending with a hyphen.

## How it works

An AI Gateway is an Azure Resource Manager resource of type `Microsoft.ApiManagement/aigateways`. You manage it
in the [AI Gateway portal](https://ai.gateway.azure.com), which is separate from the Azure portal, or through
Azure Resource Manager with the CLI, REST, or Bicep. Each gateway has a companion connector gateway
(`Microsoft.Web/connectorGateways`) with the same name, which is created first. The service sets the SKU and
capacity itself, so the only real decisions are the name, the region, and the resource group.

| Property | Value |
|---|---|
| Resource type | `Microsoft.ApiManagement/aigateways` (API version `2025-09-01-preview`), plus `Microsoft.Web/connectorGateways` with the same name |
| Regions (preview) | East US 2 (`eastus2`), Sweden Central (`swedencentral`) |
| Name | 1–24 characters: letters, digits, and hyphens. It becomes the first label of the runtime host name |
| Runtime URL | `https://` + `properties.frontend.defaultHostname`, for example `https://<gateway>.eastus2-01.ai.gateway.azure.com` |
| Runtime routes | Models under `/default/models/…`, MCP servers under `/default/toolservers/<server>/mcp` |
| Outbound identity | A system-assigned managed identity, used to call Foundry and other Microsoft Entra–protected backends |
| Provisioning time | A few minutes, often less |

Everything you publish later lives in the gateway's `default` workspace. That's why every runtime route
starts with `/default/`. Applications authenticate **inbound** with an API key or a Microsoft Entra token. The
gateway authenticates **outbound** to each backend, usually with its managed identity, so apps never hold
provider credentials.

![AI Gateway architecture: apps and agents call one gateway that governs models and tools](../assets/diagrams/architecture.svg "Apps and agents call one runtime URL. The gateway applies access, policies, and telemetry before it routes to models and MCP servers.")

## Create the gateway

Pick one track. Each track produces the same result: a gateway named `<gateway>` in `<resource-group>`, with a
system-assigned managed identity.

<!-- track: portal | Portal -->

### Sign in to the AI Gateway portal

Open the [AI Gateway portal](https://ai.gateway.azure.com) and sign in with your Azure account. If this is your
first gateway, the portal takes you straight into gateway creation. If you already have a gateway, open the
gateway switcher in the top bar and start creating a new one from there.

### Enter the gateway details

In **Create AI gateway**, enter a globally unique **Name** of 24 characters or fewer, or select
**Generate a new name**. Then choose the subscription, a **Resource group** (**New** or **Existing**), and the
**Region** (**East US 2** or **Sweden Central**). Under **Advanced**, keep
**Enable system-assigned managed identity** selected, **Public network access** set to **Enabled**, and
**Public routing**. **Private routing** connects the gateway to private backends through a virtual network and
can only be chosen at creation. [Lab 18](../18-private-networking/README.md) covers it.

![What to choose in Create AI gateway: a unique name, a subscription, a resource group, and a preview region, with the Advanced defaults kept](../assets/diagrams/create-gateway.svg "Fill in the basics, keep the Advanced defaults, then select Create gateway.")

> [!NOTE]
> The subscription picker lists every subscription you can see. Subscriptions where you lack write permission
> for API Management and connector gateways are disabled, and the portal explains why.

### Watch it provision

Select **Create gateway**. The portal shows provisioning progress in place, and a new gateway is typically ready
in a few minutes.

### Open the setup guide on Home

When provisioning finishes, **Home** opens with a setup guide for publishing models, adding MCP servers, and
creating runtime access. Leave it for now. You publish your first model in the next lab, and the guide stays
on **Home** until you finish it.

> **Checkpoint**
> The gateway switcher in the top bar shows `<gateway>`, and **Home** shows the setup guide.

<!-- track: cli | Azure CLI -->

### Register the resource providers

The gateway lives in the `Microsoft.ApiManagement` resource provider and its connector gateway in
`Microsoft.Web`. Registering is a one-time step per subscription, and it returns quickly when a provider is
already registered.

```bash
az provider register -n Microsoft.ApiManagement --wait
az provider register -n Microsoft.Web --wait
```

### Create a resource group

```bash
az group create --name "$RG" --location "$LOCATION"
```

### Create the connector gateway

Every AI gateway has a companion `Microsoft.Web/connectorGateways` resource with the same name. The portal and
the Bicep template create it first, so do the same. The `aigateway` extension creates only the AI gateway, so
create the connector gateway through the Azure Resource Manager REST API with `az rest`.

```bash title="Bash"
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/$GATEWAY?api-version=2026-05-01-preview" \
  --body "$(jq -cn --arg location "$LOCATION" '{location: $location, properties: {}}')"
```

```powershell title="PowerShell"
@{ location = $LOCATION; properties = @{} } | ConvertTo-Json -Compress | Set-Content body.json
az rest --method put `
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/${GATEWAY}?api-version=2026-05-01-preview" `
  --body "@body.json"
Remove-Item body.json
```

### Create the AI gateway

`az aigateway create` only needs the name, the region, and the managed identity. There's no SKU, capacity, or
publisher to set: the service picks them, and public network access is enabled. The command waits until
provisioning finishes, usually within a few minutes.

```bash title="Bash"
az aigateway create -g "$RG" -n "$GATEWAY" --location "$LOCATION" --system-assigned true -o none
```

```powershell title="PowerShell"
az aigateway create -g $RG -n $GATEWAY --location $LOCATION --system-assigned true -o none
```

> [!TIP]
> Add `--no-wait` to return right away, then run `az aigateway wait -g "$RG" -n "$GATEWAY" --created` when you
> need the gateway.

### Read the runtime URL and identity

```bash title="Bash"
az aigateway show -g "$RG" -n "$GATEWAY" \
  --query "{name:name, location:location, state:properties.provisioningState, host:properties.frontend.defaultHostname, principalId:identity.principalId}" \
  -o table
```

```powershell title="PowerShell"
az aigateway show -g $RG -n $GATEWAY `
  --query "{name:name, location:location, state:properties.provisioningState, host:properties.frontend.defaultHostname, principalId:identity.principalId}" `
  -o table
```

> **Checkpoint**
> The table shows `Succeeded`, a `Host` like `<gateway>.eastus2-01.ai.gateway.azure.com`, and a `PrincipalId`
> GUID.

<!-- track: iac | Bicep -->

### Review the template

The template creates what the portal creates: a `Microsoft.Web/connectorGateways` resource first, then the AI
gateway (`Microsoft.ApiManagement/aigateways`) with the same name, a system-assigned identity, and public
network access enabled. There's no SKU, capacity, or publisher to set. Keep both resources together in your own
templates.

| Parameter | Description |
|---|---|
| `gatewayName` | Required. The gateway name, 24 characters or fewer |
| `location` | `eastus2` (default) or `swedencentral` |
| `tags` | Optional. Tags applied to both resources |
| `backendSubnetId` | Optional. A subnet for outbound virtual network integration, which can only be set at creation. See [Lab 18](../18-private-networking/README.md) |

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep).

### Create a resource group

```bash
az group create --name "$RG" --location "$LOCATION"
```

### Deploy the template

Run the deployment from the lab folder. The template defaults `location` to `eastus2`, so pass your region
explicitly.

```bash title="Bash"
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" location="$LOCATION" \
  --query properties.outputs
```

```powershell title="PowerShell"
az deployment group create -g $RG `
  --template-file infra/main.bicep `
  --parameters gatewayName=$GATEWAY location=$LOCATION `
  --query properties.outputs
```

Expected output (trimmed):

```json
{
  "connectorGatewayId": { "type": "String", "value": "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Web/connectorGateways/<gateway>" },
  "gatewayId":   { "type": "String", "value": "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/aigateways/<gateway>" },
  "gatewayName": { "type": "String", "value": "<gateway>" },
  "gatewayUrl":  { "type": "String", "value": "https://<gateway>.eastus2-01.ai.gateway.azure.com" },
  "principalId": { "type": "String", "value": "00000000-0000-0000-0000-000000000000" }
}
```

> [!TIP]
> `BCP081` warnings about `Microsoft.ApiManagement/aigateways` and `Microsoft.Web/connectorGateways` mean that
> Bicep has no local type definitions for these preview resources. They don't block the deployment.

> **Checkpoint**
> The deployment succeeds and the outputs show `gatewayUrl` and `principalId`.

<!-- /tracks -->

## Verify

<!-- steps -->

### Call the runtime URL

Read the host name from the gateway rather than building it yourself, then send a request without a key. Any
HTTP status proves that DNS, TLS, and the gateway are up. A new gateway with no models answers `404`; after you
add a model and a key in the next lab, a call without a key gets `400` or `401`.

```bash title="Bash"
export AI_GATEWAY_URL="https://$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.frontend.defaultHostname -o tsv)"
echo "$AI_GATEWAY_URL"

curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_URL = "https://$(az aigateway show -g $RG -n $GATEWAY --query properties.frontend.defaultHostname -o tsv)"
$env:AI_GATEWAY_URL

(Invoke-WebRequest -Uri "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions" `
  -SkipHttpErrorCheck).StatusCode
```

A `Could not resolve host` error means the gateway isn't ready yet. Wait a minute and try again.

### Find the gateway on Home

Open the [AI Gateway portal](https://ai.gateway.azure.com). If you created the gateway with the CLI or Bicep,
select it in the gateway switcher in the top bar. **Home** shows the setup guide for your new gateway.

### Check the managed identity

Select **Managed identities**. On the **Configure identities** tab, the system-assigned identity is enabled.
Its principal ID matches `principalId` from the CLI or Bicep output. In later labs you grant this identity
access to Foundry so that the gateway can call your models without keys.

![The Managed identities page with the system-assigned identity enabled](../assets/screens/managed-identities.png "Managed identities › Configure identities shows the system-assigned identity with its principal ID and tenant ID. You can add user-assigned identities here too.")

### Tour the portal

Use the left navigation to get familiar with each area. You visit most of them in later labs.

| Area | What you do there | Where you learn it |
|---|---|---|
| **Home** | Follow the setup guide for models, MCP servers, and runtime access | This lab |
| **Catalog** | Browse published models and MCP servers, try them in the playground, and copy endpoints and code samples | [Lab 02](../02-first-model-call/README.md) |
| **Access** | Create runtime API keys on the **Keys** tab and grant Microsoft Entra roles on the **Entra ID** tab | [Lab 10](../10-api-keys/README.md), [Lab 11](../11-entra-rbac/README.md) |
| **Models** | Import Foundry deployments, add custom models from other providers, and manage aliases | [Lab 02](../02-first-model-call/README.md), [Lab 03](../03-multi-provider-aliases/README.md) |
| **MCP servers** | Publish MCP servers and control which tools are available | [Lab 04](../04-federate-mcp-tools/README.md), [Lab 05](../05-mcp-tool-controls/README.md) |
| **Policies** | Add token and request rate limits, cost limits, content safety, and IP filters at gateway or asset scope | [Lab 06](../06-token-limits/README.md), [Lab 09](../09-gateway-baselines/README.md) |
| **Monitoring** | Send telemetry to an OTLP destination and use the built-in dashboard and traces | [Lab 13](../13-monitoring/README.md) |
| **Networking** | Review network access and outbound virtual network integration | [Lab 18](../18-private-networking/README.md) |
| **Managed identities** | Manage the identities that the gateway uses to call backends | [Lab 12](../12-backend-identity/README.md) |

The top bar holds the gateway switcher, **What's new**, notifications, and a command palette (Ctrl+K) to jump
to any page.

> [!NOTE]
> Some portal versions show **Keys** directly in the left navigation instead of **Access** › **Keys**. Both
> lead to the same runtime API keys.

<!-- /steps -->

> **Checkpoint**
> The runtime URL answers with an HTTP status, the gateway appears on **Home**, and **Managed identities**
> shows the system-assigned identity enabled.

## Go further

- **One gateway per environment.** Repeat the IaC track with a different `gatewayName` for dev, test, and
  production, and keep the template in source control next to your app.
- **Tag for ownership and chargeback.** The template's `tags` parameter applies the same tags to the gateway
  and its connector gateway, so set them when you create each environment's gateway:

  ```bash
  az deployment group create -g "$RG" --template-file infra/main.bicep \
    --parameters gatewayName="$GATEWAY" location="$LOCATION" \
                 tags='{"workload":"ai-gateway-labs","owner":"platform-team","costCenter":"1234"}'
  ```
- **Use a user-assigned identity.** When several gateways must share one backend identity, add a
  user-assigned identity on **Managed identities**. See
  [Call backends with managed identities](../12-backend-identity/README.md).

## Clean up

The gateway is free during preview, and every later lab reuses it. **Keep it** until you finish the labs you
plan to do.

When you're done with all the labs, delete the resource group. That removes the gateway, its connector gateway,
and everything else in the group. The command asks for confirmation.

```bash title="Bash"
az group delete --name "$RG"
```

```powershell title="PowerShell"
az group delete --name $RG
```

To keep the resource group, delete the AI gateway first and then its connector gateway. Deleting the gateway
also deletes everything you published on it.

```bash title="Bash"
az aigateway delete -g "$RG" -n "$GATEWAY" --yes
az resource delete -g "$RG" -n "$GATEWAY" --resource-type Microsoft.Web/connectorGateways --api-version 2026-05-01-preview
```

```powershell title="PowerShell"
az aigateway delete -g $RG -n $GATEWAY --yes
az resource delete -g $RG -n $GATEWAY --resource-type Microsoft.Web/connectorGateways --api-version 2026-05-01-preview
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Your subscription is disabled in the portal's subscription picker | You lack write permission for API Management or connector gateways in that subscription | Ask for **Contributor** on the subscription or resource group, or pick another subscription. |
| The deployment fails because the region isn't supported | `$LOCATION` or the template's `location` is outside the preview regions | Use `eastus2` or `swedencentral`. The template accepts only these two values and defaults to `eastus2`. |
| The name is rejected | Gateway names are globally unique and limited to 24 characters: letters, digits, and hyphens, starting with a letter | Pick another name that follows the rules. |
| `MissingSubscriptionRegistration` | A resource provider isn't registered in the subscription | Run `az provider register -n Microsoft.ApiManagement --wait` and `az provider register -n Microsoft.Web --wait`, or ask your subscription administrator. |
| `Could not resolve host` when you call the URL | Provisioning or DNS isn't finished | Run `az aigateway wait -g "$RG" -n "$GATEWAY" --created` and retry. |
| `'aigateway' is misspelled or not recognized by the system` | The `aigateway` extension isn't installed | Run the installer from [Before you begin](#before-you-begin), then `az aigateway version`. |

## Next steps

- [Publish a Foundry model and make your first call](../02-first-model-call/README.md): import a model, create a key, and call it.
- [Issue and rotate runtime API keys](../10-api-keys/README.md): give each app its own key.
- [How AI Gateway works](../00-how-ai-gateway-works/README.md): the concepts behind models, tools, policies, and identity.
- Docs: [Configure AI Gateway in the portal](https://ai.gateway.azure.com/docs/quickstarts/portal) and
  [AI Gateway CLI quickstart](https://ai.gateway.azure.com/docs/quickstarts/cli).
