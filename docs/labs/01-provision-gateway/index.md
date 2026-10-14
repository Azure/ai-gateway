---
title: Provision your AI Gateway
summary: Create the shared AI Gateway that your apps and agents will call, from the AI Gateway portal, the Azure CLI, or Bicep, then take a guided tour of the portal.
category: foundations
level: Beginner
duration: 15
tracks: [portal, cli, iac]
order: 1
illustration: illustrations/portal-provision-gateway.svg
tags: [provisioning, AIGateway SKU, az aigateway create, Bicep, managed identity, regions]
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

![Provisioning an AI Gateway](../assets/illustrations/portal-provision-gateway.svg "One gateway per environment is the usual starting point. Every later lab publishes models, tools, keys, and policies on it.")

## Before you begin

- An Azure subscription with access to the AI Gateway preview. The AI Gateway tier is free during public
  preview. Connected services, such as Foundry inference and Application Insights, are billed normally.
- Permission to create the gateway, for example **Contributor** on the resource group, or on the subscription
  if you create a new resource group. Creating a gateway needs write access to both API Management and
  connector gateways.
- For the portal track: a browser and your Azure account.
- For the CLI and IaC tracks: the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or
  later, signed in with `az login`. The CLI track and the **Verify** section also use the `aigateway` extension
  ([install it](https://github.com/Azure/ai-gateway/tree/main/cli#install)).
- Recommended reading: [How AI Gateway works](../00-how-ai-gateway-works/README.md).

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
az account set --subscription "<subscription-id>"

export RG="<resource-group>"               # for example rg-ai-gateway-labs
export GATEWAY="<gateway>"                 # globally unique, it becomes part of the runtime URL
export LOCATION="<location>"               # eastus2 or swedencentral
```

```powershell title="PowerShell"
az account set --subscription "<subscription-id>"

$RG       = "<resource-group>"             # for example rg-ai-gateway-labs
$GATEWAY  = "<gateway>"                    # globally unique, it becomes part of the runtime URL
$LOCATION = "<location>"                   # eastus2 or swedencentral
```

> [!IMPORTANT]
> During public preview, AI Gateway is available in **East US 2** (`eastus2`) and **Sweden Central**
> (`swedencentral`). Create the resource group in one of these regions so that defaults line up.

## How it works

An AI Gateway is an Azure API Management service that runs the **AI Gateway** tier (SKU `AIGateway`). You
manage it in the [AI Gateway portal](https://ai.gateway.azure.com), which is separate from the Azure portal,
or through Azure Resource Manager with the CLI, REST, or Bicep. The capacity is defined by the service, so the
only real decisions are the name, the region, and the resource group.

| Property | Value |
|---|---|
| Resource type | `Microsoft.ApiManagement/service` with SKU `AIGateway` |
| Regions (preview) | East US 2 (`eastus2`), Sweden Central (`swedencentral`) |
| Runtime URL | `properties.gatewayUrl`, for example `https://<gateway>.azure-api.net` |
| Runtime routes | Models under `/default/models/…`, MCP servers under `/default/toolservers/<server>/mcp` |
| Outbound identity | A system-assigned managed identity, used to call Foundry and other Microsoft Entra–protected backends |
| Provisioning time | About a minute |

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

Choose the subscription, the resource group, a globally unique gateway name, and the region (**East US 2** or
**Sweden Central**).

![Creating a gateway in the AI Gateway portal](../assets/illustrations/portal-create-gateway.svg "Choose a subscription, resource group, name, and preview region, then create the gateway.")

> [!NOTE]
> The subscription picker lists every subscription you can see. Subscriptions where you lack write permission
> for API Management and connector gateways are disabled, and the portal explains why.

### Watch it provision

Create the gateway. The portal shows provisioning progress in place, and a new gateway is typically ready in
about a minute.

### Open the setup guide on Home

When provisioning finishes, **Home** opens with a setup guide for publishing models, adding MCP servers, and
creating runtime access. Leave it for now. You publish your first model in the next lab, and the guide stays
on **Home** until you finish it.

> **Checkpoint**
> The gateway switcher in the top bar shows `<gateway>`, and **Home** shows the setup guide.

<!-- track: cli | Azure CLI -->

### Create a resource group

```bash
az group create --name "$RG" --location "$LOCATION"
```

### Start creating the gateway

`az aigateway create` selects the AI Gateway SKU for you. `--no-wait` returns as soon as Azure accepts the
request, which is handy in scripts. Leave it out and the command waits for provisioning instead.

```bash
az aigateway create -g "$RG" -n "$GATEWAY" --location "$LOCATION" \
  --system-assigned true --tags workload=ai-gateway-labs owner=platform-team \
  --no-wait
```

The managed identity is shown explicitly here. `--publisher-email` and `--publisher-name` are optional and
default to `noreply@aigateway.azure.com` and `AI Gateway Administrator`.

### Wait for provisioning

```bash
az aigateway wait -g "$RG" -n "$GATEWAY" --created --interval 15
```

The command returns when `provisioningState` reaches `Succeeded`, usually in about a minute.

### Read the runtime URL and identity

```bash
az aigateway show -g "$RG" -n "$GATEWAY" \
  --query "{name:name, location:location, state:properties.provisioningState, url:properties.gatewayUrl, principalId:identity.principalId}" \
  -o table
```

> **Checkpoint**
> The table shows `Succeeded`, a `url` that starts with `https://`, and a `principalId` GUID.

<!-- track: iac | Bicep -->

### Review the template

The template mirrors the [reference sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway):
an API Management service with SKU `AIGateway`, capacity `1`, and a system-assigned identity, plus a
`Microsoft.Web/connectorGateways` resource with the same name. Keep both resources together in your own
templates.

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep).

### Create a resource group

```bash
az group create --name "$RG" --location "$LOCATION"
```

### Deploy the template

Run the deployment from the lab folder. The gateway inherits the resource group's region unless you pass
`location`.

```bash title="Bash"
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" \
  --query properties.outputs
```

```powershell title="PowerShell"
az deployment group create -g $RG `
  --template-file infra/main.bicep `
  --parameters gatewayName=$GATEWAY `
  --query properties.outputs
```

Expected output (trimmed):

```json
{
  "gatewayName": { "type": "String", "value": "<gateway>" },
  "gatewayUrl":  { "type": "String", "value": "https://<gateway>.azure-api.net" },
  "gatewayId":   { "type": "String", "value": "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ApiManagement/service/<gateway>" },
  "principalId": { "type": "String", "value": "00000000-0000-0000-0000-000000000000" }
}
```

> [!TIP]
> `BCP081` warnings about `Microsoft.Web/connectorGateways` mean that Bicep has no local type definitions
> for this preview resource. They don't block the deployment.

> **Checkpoint**
> The deployment succeeds and the outputs show `gatewayUrl` and `principalId`.

<!-- /tracks -->

## Verify

<!-- steps -->

### Call the runtime URL

Read the URL from the gateway rather than building it yourself, then send a request without a key. Any HTTP
status, typically `401`, proves that DNS, TLS, and the gateway are up. You add a model and a key in the next lab.

```bash title="Bash"
export AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.gatewayUrl -o tsv)"
echo "$AI_GATEWAY_URL"

curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_URL = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv
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
| **Discover** | Browse published models and MCP servers, try them in the playground, and copy endpoints and code samples | [Lab 02](../02-first-model-call/README.md) |
| **Access** | Create runtime API keys on the **Keys** tab and grant Microsoft Entra roles on the **Entra ID** tab | [Lab 10](../10-api-keys/README.md), [Lab 11](../11-entra-rbac/README.md) |
| **Models** | Import Foundry deployments, add custom models from other providers, and manage aliases | [Lab 02](../02-first-model-call/README.md), [Lab 03](../03-multi-provider-aliases/README.md) |
| **MCP servers** | Publish MCP servers and control which tools are available | [Lab 04](../04-federate-mcp-tools/README.md), [Lab 05](../05-mcp-tool-controls/README.md) |
| **Policies** | Add token and request rate limits, cost limits, content safety, and IP filters at gateway or asset scope | [Lab 06](../06-token-limits/README.md), [Lab 09](../09-gateway-baselines/README.md) |
| **Monitoring** | Send telemetry to an OTLP destination and use the built-in dashboard and traces | [Lab 13](../13-monitoring/README.md) |
| **Networking** | Configure private endpoints and outbound virtual network integration | [Lab 18](../18-private-networking/README.md) |
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
- **Tag for ownership and chargeback.** `az aigateway update` sets tags, and it replaces the whole tag set, so
  include every tag you want to keep:

  ```bash
  az aigateway update -g "$RG" -n "$GATEWAY" --tags workload=ai-gateway-labs owner=platform-team costCenter=1234
  ```
- **Use a user-assigned identity.** When several gateways must share one backend identity, add a
  user-assigned identity on **Managed identities**. See
  [Call backends with managed identities](../12-backend-identity/README.md).

## Clean up

The gateway is free during preview, and every later lab reuses it. **Keep it** until you finish the labs you
plan to do.

When you're done with all the labs, delete the resource group. That removes the gateway and everything else in
the group. The command asks for confirmation.

```bash title="Bash"
az group delete --name "$RG"
```

```powershell title="PowerShell"
az group delete --name $RG
```

Deleting a gateway keeps an API Management soft-delete record, so the name might not be reusable right away. To
reuse the name immediately, purge the record. Purging is permanent.

```bash
az apim deletedservice purge --service-name "$GATEWAY" --location "$LOCATION"
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Your subscription is disabled in the portal's subscription picker | You lack write permission for API Management or connector gateways in that subscription | Ask for **Contributor** on the subscription or resource group, or pick another subscription. |
| The deployment fails because the region isn't supported | The resource group or `--location` is outside the preview regions | Use `eastus2` or `swedencentral`. In Bicep, pass `location=eastus2` if the resource group is elsewhere. |
| The name is rejected as unavailable | Gateway names are globally unique, or a soft-deleted gateway still holds the name | Pick another name, or purge your own soft-deleted gateway with `az apim deletedservice purge`. |
| `MissingSubscriptionRegistration` | The resource provider isn't registered in the subscription | Run `az provider register --namespace Microsoft.ApiManagement` (and `Microsoft.Web` for the Bicep track), or ask your subscription administrator. |
| `Could not resolve host` when you call the URL | Provisioning or DNS isn't finished | Run `az aigateway wait -g "$RG" -n "$GATEWAY" --created` and retry. |
| `az aigateway: 'create' is misspelled or not recognized` | The CLI extension isn't installed | [Install the extension](https://github.com/Azure/ai-gateway/tree/main/cli#install) and run `az aigateway version`. |

## Next steps

- [Publish a Foundry model and make your first call](../02-first-model-call/README.md): import a model, create a key, and call it.
- [Issue and rotate runtime API keys](../10-api-keys/README.md): give each app its own key.
- [How AI Gateway works](../00-how-ai-gateway-works/README.md): the concepts behind models, tools, policies, and identity.
- Docs: [Configure AI Gateway in the portal](https://ai.gateway.azure.com/docs/quickstarts/portal) and
  [AI Gateway CLI quickstart](https://ai.gateway.azure.com/docs/quickstarts/cli).
