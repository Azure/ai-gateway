---
title: Lock down backend traffic with private networking
summary: Create an AI Gateway with private routing through your virtual network, reach a Foundry backend over a private endpoint with its public access turned off, and learn which inbound options aren't available yet.
category: production
level: Advanced
duration: 45
tracks: [portal, cli, iac]
order: 18
illustration: diagrams/private-networking.svg
tags: [VNet integration, private routing, private endpoint, private DNS, NSG, backend subnet, Foundry, ipFilter]
objectives:
  - Explain which private networking options AI Gateway supports today, and why private routing is chosen at creation
  - Prepare a delegated integration subnet with an NSG that passes the gateway's subnet checks
  - Create a gateway with private routing through that subnet
  - Give Foundry a private endpoint and private DNS, turn off its public access, and prove the gateway still reaches it
  - Clean up in the right order, so the subnet and the Foundry resource are released
prereqs:
  - 01-provision-gateway
  - 12-backend-identity
---

# Lock down backend traffic with private networking

Your security team wants model traffic kept off the public internet wherever the platform allows it. With AI
Gateway today, that's the hop from the gateway to your backends. In this lab you create a gateway with **private
routing**, so its outbound calls leave through a subnet in your virtual network. Then you give the Foundry
resource a private endpoint, turn off Foundry's public access, and prove that the gateway still reaches the model
while the internet can't.

> [!IMPORTANT]
> Inbound private endpoints and disabling public network access aren't available for AI Gateway
> (`Microsoft.ApiManagement/aigateways`) yet. In the portal's create dialog, **Public network access** ›
> **Disabled** is greyed out with "Unavailable until private frontend access is supported", the gateway has no
> private endpoint connections, and setting `publicNetworkAccess` to `Disabled` through Azure Resource Manager has
> no effect. Clients keep calling the gateway on its public endpoint, so protect it with runtime keys or Microsoft
> Entra ID ([Issue and rotate runtime API keys](../10-api-keys/README.md),
> [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md)) and an `ipFilter` policy
> ([Set gateway-wide policy baselines](../09-gateway-baselines/README.md)).

## Before you begin

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md) and
  [Call backends with managed identities](../12-backend-identity/README.md). You need a Foundry resource with a
  chat model deployment, for example `gpt-4.1-mini`.
- Private routing can only be chosen when a gateway is created, so this lab creates a **new** gateway. The
  gateway from the earlier labs stays as it is.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login`, plus `jq` for the Bash snippets. Every track uses the CLI for the checks. The CLI track calls the
  Azure Resource Manager REST API with `az rest`, so you don't need a CLI extension.
- Permission to create a resource group, network resources, and a gateway, to change the Foundry resource, and
  to assign roles on it, for example **Owner**, or **Contributor** plus **Role Based Access Control
  Administrator**.
- AI Gateway is in preview in East US 2 and Sweden Central. The virtual network must be in the gateway's
  subscription and region.

> [!WARNING]
> Turning off public access on the Foundry resource blocks every caller that reaches it over the internet,
> including the gateway from the earlier labs, which has no private routing, and tools on your workstation. Use a
> dedicated Foundry resource for this lab if others depend on it, and re-enable public access when you clean up.

> [!IMPORTANT]
> This lab creates billable resources: a private endpoint and private DNS zones. The AI Gateway tier is free
> during the preview. Follow [Clean up](#clean-up) when you finish.

Set these variables once. Every track and the **Verify** section reuse them. The lab puts the new gateway and
the network in their own resource group, so clean-up is one command.

```bash title="Bash"
export RG="rg-ai-gateway-private"            # a new resource group for this lab
export LOCATION="eastus2"                    # eastus2 or swedencentral
export GATEWAY="<private-gateway>"           # a NEW, globally unique name, 24 characters or fewer
export API="api-version=2025-09-01-preview"
export SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
export GATEWAY_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
export GW="https://management.azure.com$GATEWAY_ID"
export WS="$GW/workspaces/default"

export VNET="vnet-aigw"
export INTEGRATION_SUBNET="snet-aigw-integration"
export PE_SUBNET="snet-private-endpoints"
export NSG="nsg-aigw-integration"
export FOUNDRY_PE="pe-foundry-$GATEWAY"

# The Foundry resource and deployment from the earlier labs
export FOUNDRY_RG="<foundry-resource-group>"
export FOUNDRY_ACCOUNT="<foundry-account-name>"
export DEPLOYMENT="gpt-4.1-mini"
export FOUNDRY_ID="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)"
export FOUNDRY_ENDPOINT="$(az cognitiveservices account show -g "$FOUNDRY_RG" -n "$FOUNDRY_ACCOUNT" --query properties.endpoint -o tsv)"

# What the lab publishes on the new gateway
export PROVIDER="foundry-private"
export ALIAS="private-chat"
export KEY_NAME="private-net-lab"

az group create -n "$RG" -l "$LOCATION" -o none
```

```powershell title="PowerShell"
$RG              = "rg-ai-gateway-private"   # a new resource group for this lab
$LOCATION        = "eastus2"                 # eastus2 or swedencentral
$GATEWAY         = "<private-gateway>"       # a NEW, globally unique name, 24 characters or fewer
$API             = "api-version=2025-09-01-preview"
$SUBSCRIPTION_ID = az account show --query id -o tsv
$GATEWAY_ID      = "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.ApiManagement/aigateways/$GATEWAY"
$GW              = "https://management.azure.com$GATEWAY_ID"
$WS              = "$GW/workspaces/default"

$VNET               = "vnet-aigw"
$INTEGRATION_SUBNET = "snet-aigw-integration"
$PE_SUBNET          = "snet-private-endpoints"
$NSG                = "nsg-aigw-integration"
$FOUNDRY_PE         = "pe-foundry-$GATEWAY"

# The Foundry resource and deployment from the earlier labs
$FOUNDRY_RG       = "<foundry-resource-group>"
$FOUNDRY_ACCOUNT  = "<foundry-account-name>"
$DEPLOYMENT       = "gpt-4.1-mini"
$FOUNDRY_ID       = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query id -o tsv
$FOUNDRY_ENDPOINT = az cognitiveservices account show -g $FOUNDRY_RG -n $FOUNDRY_ACCOUNT --query properties.endpoint -o tsv

# What the lab publishes on the new gateway
$PROVIDER = "foundry-private"
$ALIAS    = "private-chat"
$KEY_NAME = "private-net-lab"

az group create -n $RG -l $LOCATION -o none
```

> [!TIP]
> Single-line commands and the `az network` commands in the tracks work in both shells. In PowerShell, replace
> the Bash line continuation (`\`) with a backtick (`` ` ``) or put the command on one line. Snippets that build
> JSON bodies or URLs have separate Bash and PowerShell tabs.

## How it works

A gateway has two network directions. **Inbound**, clients call the gateway's frontend on
`https://<gateway>.<region>-01.ai.gateway.azure.com`. **Outbound**, the gateway calls models, MCP servers, and
APIs. With **private routing**, the gateway joins a dedicated, delegated subnet in your virtual network and sends
its outbound calls through it, so it can reach backends on private IPs. When a backend's private DNS zones are
linked to that virtual network, the gateway resolves the backend's usual host name to its private endpoint IP.

You choose private routing when you create the gateway, and you can't add, change, or remove it afterwards: "Virtual
network integration for Azure AI Gateway can only be configured during creation." Most connectivity problems
after that are DNS: the gateway must resolve each backend to its private IP.

| Piece | Direction | Available today | Where you set it | Key values |
|---|---|---|---|---|
| Integration subnet | Outbound | Yes | Your virtual network | At least `/27` (`/24` recommended), same subscription and region as the gateway, dedicated to one gateway, delegated to `Microsoft.Web/serverFarms`, NSG allows outbound TCP 443 to `Storage` and `AzureKeyVault` |
| Private routing | Outbound | Yes, at creation only | **Create AI gateway** › **Advanced** › **Private routing** | `properties.backend.subnet.id` set to the integration subnet |
| Backend private endpoints | Outbound | Yes | Each backend, plus its private DNS zones linked to the virtual network | Foundry uses the `account` group ID |
| Gateway private endpoint | Inbound | Not yet | — | The gateway has no private link resources |
| Public network access | Inbound | Always **Enabled** | — | **Disabled** is "Unavailable until private frontend access is supported" |
| IP filter | Inbound | Yes | Gateway-wide policy ([lab 09](../09-gateway-baselines/README.md)) | `ipFilter` with `action: Allow` and `cidrRanges` |

## Prepare the virtual network

You create one virtual network with two subnets. The integration subnet belongs to the new gateway alone, and
backend private endpoints get their own subnet.

| Subnet | Prefix | Used for | Settings |
|---|---|---|---|
| `snet-aigw-integration` | `10.20.0.0/24` | Gateway private routing (outbound) | NSG `nsg-aigw-integration`, delegated to `Microsoft.Web/serverFarms`, nothing else deployed in it |
| `snet-private-endpoints` | `10.20.1.0/24` | Private endpoints to backends such as Foundry | None |

Pick one track. The IaC track declares the network, the gateway, and the Foundry private endpoint in one
template, so you deploy it once in the next section.

<!-- track: portal | Portal -->

### Create the network security group

In the [Azure portal](https://portal.azure.com), create a network security group named `nsg-aigw-integration`
in the lab's resource group and region. Add two **outbound** security rules:

| Name | Priority | Source | Destination (service tag) | Protocol | Destination port | Action |
|---|---|---|---|---|---|---|
| `AllowStorageOutbound` | 100 | `VirtualNetwork` | `Storage` | TCP | `443` | Allow |
| `AllowKeyVaultOutbound` | 110 | `VirtualNetwork` | `AzureKeyVault` | TCP | `443` | Allow |

### Create the virtual network and subnets

Create a virtual network named `vnet-aigw` in the **same subscription and region as the new gateway**, with the
address space `10.20.0.0/16`. Add the two subnets from the table above. On `snet-aigw-integration`, select the
`nsg-aigw-integration` network security group and delegate the subnet to `Microsoft.Web/serverFarms`.

> **Checkpoint**
> The virtual network shows two subnets, and `snet-aigw-integration` lists the delegation
> `Microsoft.Web/serverFarms` and the NSG `nsg-aigw-integration`.

<!-- track: cli | Azure CLI -->

### Create the network security group

```bash
az network nsg create -g "$RG" -n "$NSG" -l "$LOCATION"

az network nsg rule create -g "$RG" --nsg-name "$NSG" -n AllowStorageOutbound \
  --priority 100 --direction Outbound --access Allow --protocol Tcp \
  --source-address-prefixes VirtualNetwork \
  --destination-address-prefixes Storage --destination-port-ranges 443

az network nsg rule create -g "$RG" --nsg-name "$NSG" -n AllowKeyVaultOutbound \
  --priority 110 --direction Outbound --access Allow --protocol Tcp \
  --source-address-prefixes VirtualNetwork \
  --destination-address-prefixes AzureKeyVault --destination-port-ranges 443
```

### Create the virtual network and subnets

```bash
az network vnet create -g "$RG" -n "$VNET" -l "$LOCATION" --address-prefixes 10.20.0.0/16

az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$INTEGRATION_SUBNET" \
  --address-prefixes 10.20.0.0/24 \
  --delegations Microsoft.Web/serverFarms --network-security-group "$NSG"

az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$PE_SUBNET" --address-prefixes 10.20.1.0/24
```

> **Checkpoint**
> This command shows the `/24` prefix, the `Microsoft.Web/serverFarms` delegation, and the NSG:
>
> ```bash
> az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$INTEGRATION_SUBNET" \
>   --query "{prefix:addressPrefix, delegation:delegations[0].serviceName, nsg:networkSecurityGroup.id}"
> ```

<!-- track: iac | Bicep -->

### Review the template

The template declares the NSG, the virtual network and its two subnets, and the gateway itself. It creates the
gateway with the template from [Provision your AI Gateway](../01-provision-gateway/README.md), used as a module,
and passes the integration subnet in its `backendSubnetId` parameter, which becomes
`properties.backend.subnet.id`. When you pass a Foundry resource ID in `foundryAccountId`, it also adds a private
endpoint to Foundry with the `account` group ID, the three Foundry private DNS zones, their virtual network
links, and a DNS zone group.

There's no inbound private endpoint and no `publicNetworkAccess: 'Disabled'` in the template, because the
`aigateways` resource type doesn't support them yet.

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep).

> **Checkpoint**
> You know which parameters you pass: `gatewayName`, `location`, and `foundryAccountId`. You deploy the template
> in the next section.

<!-- /tracks -->

## Create the gateway with private routing

Private routing is part of the create request. Select the integration subnet now: if you skip it, the only way to
add it later is to create another gateway.

<!-- track: portal | Portal -->

### Enter the gateway details

1. Open the [AI Gateway portal](https://ai.gateway.azure.com). Open the gateway switcher in the top bar and start
   creating a new gateway.
2. In **Create AI gateway**, enter the new gateway's **Name**, then choose the subscription, the
   `rg-ai-gateway-private` **Resource group** (**Existing**), and the **Region** that matches the virtual network.
3. Under **Advanced**, keep **Enable system-assigned managed identity** selected and **Public network access**
   set to **Enabled**. **Disabled** is greyed out: "Unavailable until private frontend access is supported".

### Choose private routing

1. Select **Private routing** ("Allow access to private backends through secure outbound connections").
2. In **Virtual network**, select `vnet-aigw`. In **Subnet**, select `snet-aigw-integration`.
3. The portal checks the subnet: same subscription and region as the gateway, at least `/27` (`/24` leaves room to
   scale), delegated to `Microsoft.Web/serverFarms`, dedicated to one gateway, and an NSG that allows outbound
   TCP 443 to the `Storage` and `AzureKeyVault` service tags. Fix anything it flags before you continue.
4. Select **Create gateway** and wait for provisioning to finish.

> **Checkpoint**
> The gateway switcher shows the new gateway, and **Home** opens with the setup guide.

<!-- track: cli | Azure CLI -->

### Register the resource providers

```bash
az provider register -n Microsoft.ApiManagement --wait
az provider register -n Microsoft.Web --wait
```

### Create the connector gateway

Every AI gateway has a companion `Microsoft.Web/connectorGateways` resource with the same name, created first.

```bash title="Bash"
az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/$GATEWAY?api-version=2026-05-01-preview" \
  --body "$(jq -cn --arg location "$LOCATION" '{location: $location, properties: {}}')" -o none
```

```powershell title="PowerShell"
@{ location = $LOCATION; properties = @{} } | ConvertTo-Json -Compress | Set-Content body.json
az rest --method put `
  --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG/providers/Microsoft.Web/connectorGateways/${GATEWAY}?api-version=2026-05-01-preview" `
  --body "@body.json" -o none
```

### Create the gateway in the integration subnet

The request is the same as in lab 01, plus `properties.backend.subnet.id`.

```bash title="Bash"
SUBNET_ID="$(az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$INTEGRATION_SUBNET" --query id -o tsv)"

az rest --method put --url "$GW?$API" \
  --body "$(jq -cn --arg location "$LOCATION" --arg subnet "$SUBNET_ID" \
    '{location: $location, identity: {type: "SystemAssigned"},
      properties: {publicNetworkAccess: "Enabled", backend: {subnet: {id: $subnet}}}}')" -o none

az resource wait --ids "$GATEWAY_ID" --api-version 2025-09-01-preview \
  --custom "properties.provisioningState=='Succeeded'"
```

```powershell title="PowerShell"
$SUBNET_ID = az network vnet subnet show -g $RG --vnet-name $VNET -n $INTEGRATION_SUBNET --query id -o tsv

@{
  location   = $LOCATION
  identity   = @{ type = "SystemAssigned" }
  properties = @{ publicNetworkAccess = "Enabled"; backend = @{ subnet = @{ id = $SUBNET_ID } } }
} | ConvertTo-Json -Depth 5 -Compress | Set-Content body.json
az rest --method put --url "${GW}?$API" --body "@body.json" -o none
Remove-Item body.json

az resource wait --ids $GATEWAY_ID --api-version 2025-09-01-preview `
  --custom "properties.provisioningState=='Succeeded'"
```

> **Checkpoint**
> `az resource wait` returns without an error, usually within a few minutes.

<!-- track: iac | Bicep -->

### Deploy the network, the gateway, and the Foundry private endpoint

From the lab folder, register the resource providers once, then deploy the template:

```bash title="Bash"
az provider register -n Microsoft.ApiManagement --wait
az provider register -n Microsoft.Web --wait

az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" location="$LOCATION" foundryAccountId="$FOUNDRY_ID" \
  --query properties.outputs
```

```powershell title="PowerShell"
az provider register -n Microsoft.ApiManagement --wait
az provider register -n Microsoft.Web --wait

az deployment group create -g $RG `
  --template-file infra/main.bicep `
  --parameters gatewayName=$GATEWAY location=$LOCATION foundryAccountId=$FOUNDRY_ID `
  --query properties.outputs
```

`BCP081` warnings about `Microsoft.ApiManagement/aigateways` and `Microsoft.Web/connectorGateways` are expected:
Bicep has no type definitions for these preview types yet.

> **Checkpoint**
> The outputs include `gatewayUrl`, `integrationSubnetId`, and `foundryPrivateEndpointName`
> (`pe-foundry-<private-gateway>`).

<!-- /tracks -->

Whichever track you used, load the runtime URL and confirm that the gateway uses the integration subnet:

```bash title="Bash"
export AI_GATEWAY_URL="https://$(az resource show --ids "$GATEWAY_ID" --query properties.frontend.defaultHostname -o tsv)"

az rest --url "$GW?$API" \
  --query "{state:properties.provisioningState, backendSubnet:properties.backend.subnet.id, host:properties.frontend.defaultHostname}"
```

```powershell title="PowerShell"
$env:AI_GATEWAY_URL = "https://$(az resource show --ids $GATEWAY_ID --query properties.frontend.defaultHostname -o tsv)"

az rest --url "${GW}?$API" `
  --query "{state:properties.provisioningState, backendSubnet:properties.backend.subnet.id, host:properties.frontend.defaultHostname}"
```

Expected output:

```json
{
  "state": "Succeeded",
  "backendSubnet": "/subscriptions/<subscription-id>/resourceGroups/rg-ai-gateway-private/providers/Microsoft.Network/virtualNetworks/vnet-aigw/subnets/snet-aigw-integration",
  "host": "<private-gateway>.eastus2-01.ai.gateway.azure.com"
}
```

## Give Foundry a private endpoint

The gateway now sends outbound calls through your virtual network, but Foundry still resolves to its public IP.
Give the Foundry resource a private endpoint in `snet-private-endpoints` and link its private DNS zones to the
virtual network, so the gateway resolves Foundry to a private IP.

<!-- track: portal | Portal -->

### Add a private endpoint to Foundry

In the Azure portal, open your Foundry resource and add a private endpoint named `pe-foundry-<private-gateway>`
in the lab's resource group, in `vnet-aigw` › `snet-private-endpoints`, for the `account` sub-resource, with
private DNS integration turned on. The private DNS zones for Foundry are
`privatelink.cognitiveservices.azure.com`, `privatelink.openai.azure.com`, and `privatelink.services.ai.azure.com`.
For the full walkthrough, see
[How to configure network isolation for Microsoft Foundry](https://learn.microsoft.com/azure/ai-foundry/how-to/configure-private-link).

<!-- track: cli | Azure CLI -->

### Add a private endpoint to Foundry

```bash
az network private-endpoint create -g "$RG" -n "$FOUNDRY_PE" -l "$LOCATION" \
  --vnet-name "$VNET" --subnet "$PE_SUBNET" \
  --private-connection-resource-id "$FOUNDRY_ID" --group-id account --connection-name foundry
```

### Link the Foundry private DNS zones

Create each zone, link it to the virtual network, and add it to the endpoint's DNS zone group:

```bash title="Bash"
first=true
for zone in privatelink.cognitiveservices.azure.com privatelink.openai.azure.com privatelink.services.ai.azure.com; do
  az network private-dns zone create -g "$RG" -n "$zone" -o none
  az network private-dns link vnet create -g "$RG" -z "$zone" -n "$VNET-link" -v "$VNET" -e false -o none
  if $first; then action=create; first=false; else action=add; fi
  az network private-endpoint dns-zone-group "$action" -g "$RG" --endpoint-name "$FOUNDRY_PE" \
    -n default --private-dns-zone "$zone" --zone-name "${zone//./-}" -o none
done
```

```powershell title="PowerShell"
$zones = "privatelink.cognitiveservices.azure.com", "privatelink.openai.azure.com", "privatelink.services.ai.azure.com"
foreach ($zone in $zones) {
  az network private-dns zone create -g $RG -n $zone -o none
  az network private-dns link vnet create -g $RG -z $zone -n "$VNET-link" -v $VNET -e false -o none
  $action = if ($zone -eq $zones[0]) { "create" } else { "add" }
  az network private-endpoint dns-zone-group $action -g $RG --endpoint-name $FOUNDRY_PE `
    -n default --private-dns-zone $zone --zone-name $zone.Replace('.', '-') -o none
}
```

<!-- track: iac | Bicep -->

### Check what the deployment created

You passed `foundryAccountId` in the previous section, so the deployment already created the private endpoint,
the three private DNS zones, their virtual network links, and the DNS zone group. If you left `foundryAccountId`
out, run the CLI track's commands for this section instead of redeploying, because the template also declares
the gateway, and its private routing can't change after creation.

<!-- /tracks -->

> **Checkpoint**
> The private endpoint is approved, and the Foundry host has an `A` record in the `10.20.1.0/24` range:
>
> ```bash
> az network private-endpoint show -g "$RG" -n "$FOUNDRY_PE" \
>   --query "privateLinkServiceConnections[0].privateLinkServiceConnectionState.status" -o tsv
> az network private-dns record-set a list -g "$RG" -z privatelink.cognitiveservices.azure.com \
>   --query "[].{name:name, ip:aRecords[0].ipv4Address}" -o table
> ```
>
> The first command prints `Approved`, and the table shows `<foundry-account-name>` with an IP like `10.20.1.4`.

## Publish a model on the new gateway

The new gateway starts empty. Publish your Foundry deployment on it, as in
[Make your first model call](../02-first-model-call/README.md), and create a runtime API key. The gateway calls
Foundry with its own system-assigned managed identity, which needs the **Foundry User** role on the account.

<!-- track: portal | Portal -->

### Import the deployment from Foundry

1. In the [AI Gateway portal](https://ai.gateway.azure.com), select the new gateway in the top bar.
2. Select **Models** › **Add models** › **Models from Microsoft Foundry**.
3. Select the subscription and resource group of your Foundry account, then select your deployment and keep
   **Managed identity** as the **Authentication method**.
4. Under **Aliases**, keep **Create an alias for each model** selected, then select **Add models**.
5. Open the imported model on **Models**, open the **Aliases** tab, and copy the alias exactly as shown.

### Create a runtime API key

Select **Access** › **Keys** › **Create API key**, enter `private-net-lab` in **Key name**, select **Create**,
and copy the value. Then set both values in your shell without echoing the key:

```bash title="Bash"
export AI_GATEWAY_MODEL="<model-name>"    # the alias from the Aliases tab
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$env:AI_GATEWAY_MODEL   = "<model-name>"  # the alias from the Aliases tab
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

<!-- track: cli | Azure CLI -->

### Grant the gateway access to Foundry

```bash title="Bash"
PRINCIPAL_ID="$(az resource show --ids "$GATEWAY_ID" --query identity.principalId -o tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID" -o none
```

```powershell title="PowerShell"
$PRINCIPAL_ID = az resource show --ids $GATEWAY_ID --query identity.principalId -o tsv
az role assignment create --assignee-object-id $PRINCIPAL_ID --assignee-principal-type ServicePrincipal `
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID -o none
```

`53ca6127-db72-4b80-b1b0-d745d6d5456d` is the **Foundry User** role.

### Publish the deployment and an alias

```bash title="Bash"
az rest --method put --url "$WS/modelProviders/$PROVIDER?$API" -o none \
  --body "$(jq -cn --arg endpoint "$FOUNDRY_ENDPOINT" --arg id "$FOUNDRY_ID" \
    '{properties: {kind: "Foundry", displayName: "Foundry (private)", foundry: {endpoint: $endpoint, resourceIds: [$id],
      authentication: {kind: "ManagedIdentity", managedIdentity: {resource: "https://cognitiveservices.azure.com/"}}}}}')"

az rest --method put --url "$WS/modelProviders/$PROVIDER/models/$DEPLOYMENT?$API" -o none \
  --body "$(jq -cn --arg d "$DEPLOYMENT" --arg id "$FOUNDRY_ID/deployments/$DEPLOYMENT" \
    '{properties: {displayName: $d, apiFormat: "OpenAIChatCompletions",
      supportedEndpoints: ["/openai/v1/chat/completions", "/openai/v1/responses"],
      deployment: {resourceId: $id, modelName: $d}}}')"

MODEL_ID="$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT"
az rest --method put --url "$WS/aliases/$ALIAS?$API" -o none \
  --body "$(jq -cn --arg m "$MODEL_ID" '{properties: {backendModels: [{resourceId: $m}]}}')"
```

```powershell title="PowerShell"
@{ properties = @{
    kind = "Foundry"; displayName = "Foundry (private)"
    foundry = @{
      endpoint = $FOUNDRY_ENDPOINT; resourceIds = @($FOUNDRY_ID)
      authentication = @{ kind = "ManagedIdentity"; managedIdentity = @{ resource = "https://cognitiveservices.azure.com/" } }
    } } } | ConvertTo-Json -Depth 10 -Compress | Set-Content body.json
az rest --method put --url "$WS/modelProviders/${PROVIDER}?$API" --body "@body.json" -o none

@{ properties = @{
    displayName = $DEPLOYMENT; apiFormat = "OpenAIChatCompletions"
    supportedEndpoints = @("/openai/v1/chat/completions", "/openai/v1/responses")
    deployment = @{ resourceId = "$FOUNDRY_ID/deployments/$DEPLOYMENT"; modelName = $DEPLOYMENT }
  } } | ConvertTo-Json -Depth 10 -Compress | Set-Content body.json
az rest --method put --url "$WS/modelProviders/$PROVIDER/models/${DEPLOYMENT}?$API" --body "@body.json" -o none

$MODEL_ID = "$GATEWAY_ID/workspaces/default/modelProviders/$PROVIDER/models/$DEPLOYMENT"
@{ properties = @{ backendModels = @(@{ resourceId = $MODEL_ID }) } } |
  ConvertTo-Json -Depth 10 -Compress | Set-Content body.json
az rest --method put --url "$WS/aliases/${ALIAS}?$API" --body "@body.json" -o none
Remove-Item body.json
```

### Create a runtime API key

Read the generated value straight into a variable, so it never appears on screen.

```bash title="Bash"
az rest --method put --url "$GW/apiKeys/$KEY_NAME?$API" --body '{"properties":{}}' -o none
AI_GATEWAY_API_KEY="$(az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" --query primaryKey -o tsv)" \
  && export AI_GATEWAY_API_KEY
export AI_GATEWAY_MODEL="$ALIAS"
```

```powershell title="PowerShell"
@{ properties = @{} } | ConvertTo-Json -Compress | Set-Content body.json
az rest --method put --url "$GW/apiKeys/${KEY_NAME}?$API" --body "@body.json" -o none
Remove-Item body.json
$env:AI_GATEWAY_API_KEY = az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" --query primaryKey -o tsv
$env:AI_GATEWAY_MODEL   = $ALIAS
```

<!-- track: iac | Bicep -->

### Deploy the model template from lab 02

The template from [Make your first model call](../02-first-model-call/README.md) publishes a Foundry deployment
on an existing gateway: it grants the gateway's identity the **Foundry User** role, creates the provider, the
model, and an alias, and creates a runtime API key. Run it from this lab's folder against the new gateway:

```bash title="Bash"
az deployment group create -g "$RG" \
  --template-file ../02-first-model-call/infra/main.bicep \
  --parameters gatewayName="$GATEWAY" foundryAccountId="$FOUNDRY_ID" deploymentName="$DEPLOYMENT" \
               providerName="$PROVIDER" aliasName="$ALIAS" apiKeyName="$KEY_NAME" \
  --query properties.outputs
```

```powershell title="PowerShell"
az deployment group create -g $RG `
  --template-file ../02-first-model-call/infra/main.bicep `
  --parameters gatewayName=$GATEWAY foundryAccountId=$FOUNDRY_ID deploymentName=$DEPLOYMENT `
               providerName=$PROVIDER aliasName=$ALIAS apiKeyName=$KEY_NAME `
  --query properties.outputs
```

### Read the alias and key

Template outputs never contain the key value. Read it straight into a variable.

```bash title="Bash"
export AI_GATEWAY_MODEL="$ALIAS"
AI_GATEWAY_API_KEY="$(az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" --query primaryKey -o tsv)" \
  && export AI_GATEWAY_API_KEY
```

```powershell title="PowerShell"
$env:AI_GATEWAY_MODEL   = $ALIAS
$env:AI_GATEWAY_API_KEY = az rest --method post --url "$GW/apiKeys/$KEY_NAME/listSecrets?$API" --query primaryKey -o tsv
```

<!-- /tracks -->

> **Checkpoint**
> Call the model through the new gateway. Foundry's public access is still on, so a `200` proves that the
> gateway, the model, and the key work before you lock anything down:
>
> ```bash title="Bash"
> curl -sS -o /dev/null -w 'HTTP %{http_code}\n' "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
>   -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
>   -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: ok\"}],\"max_completion_tokens\":128}"
> ```
>
> ```powershell title="PowerShell"
> $body = @{ model = $env:AI_GATEWAY_MODEL; max_completion_tokens = 128
>   messages = @(@{ role = "user"; content = "Reply with exactly one word: ok" }) } | ConvertTo-Json -Depth 5
> $r = Invoke-WebRequest -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
>   -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body -SkipHttpErrorCheck
> "HTTP $($r.StatusCode)"
> ```
>
> If the first call returns `401` or `403` from the backend, the role assignment hasn't taken effect yet. Wait a
> few minutes and try again.

## Turn off public access to Foundry

The gateway resolves Foundry through the private DNS zones, so its calls already use the private endpoint. Turn
off Foundry's public access, so the private endpoint is the only way in.

<!-- track: portal | Portal -->

### Disable public network access on Foundry

After the private endpoint shows as approved, open the Foundry resource's networking settings in the Azure portal
and disable public network access. See
[Configure virtual networks for Foundry Tools](https://learn.microsoft.com/azure/ai-services/cognitive-services-virtual-networks).

<!-- track: cli | Azure CLI -->

### Disable public network access on Foundry

```bash
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Disabled \
  --query properties.publicNetworkAccess -o tsv
```

<!-- track: iac | Bicep -->

### Disable public network access on Foundry

The Foundry resource lives in its own template, so change only its public access setting here instead of
redeclaring it:

```bash
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Disabled \
  --query properties.publicNetworkAccess -o tsv
```

If you deploy Foundry with Bicep yourself, set `publicNetworkAccess: 'Disabled'` in that template instead.

<!-- /tracks -->

The change can take a few minutes to apply.

## Verify

<!-- steps -->

### Check the gateway's private routing

```bash title="Bash"
az rest --url "$GW?$API" --query "properties.backend.subnet.id" -o tsv
```

```powershell title="PowerShell"
az rest --url "${GW}?$API" --query "properties.backend.subnet.id" -o tsv
```

The output ends with `/virtualNetworks/vnet-aigw/subnets/snet-aigw-integration`.

### Check name resolution for Foundry

```bash
az network private-dns record-set a list -g "$RG" -z privatelink.cognitiveservices.azure.com \
  --query "[].{name:name, ip:aRecords[0].ipv4Address}" -o table
```

The Foundry account resolves to an IP in `snet-private-endpoints` (`10.20.1.x`) for anything that uses the
virtual network's DNS, including the gateway.

### Call the model through the gateway

```bash title="Bash"
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: ok\"}],\"max_completion_tokens\":128}"
```

```powershell title="PowerShell"
$body = @{ model = $env:AI_GATEWAY_MODEL; max_completion_tokens = 128
  messages = @(@{ role = "user"; content = "Reply with exactly one word: ok" }) } | ConvertTo-Json -Depth 5
$r = Invoke-WebRequest -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
  -Headers @{ "api-key" = $env:AI_GATEWAY_API_KEY } -ContentType "application/json" -Body $body -SkipHttpErrorCheck
"HTTP $($r.StatusCode)"
```

The call still returns `HTTP 200`. Your workstation reaches the gateway on its public endpoint, and the gateway
reaches Foundry through the integration subnet and the private endpoint.

### Call Foundry directly from your workstation

```bash title="Bash"
TOKEN="$(az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv)"
curl -sS -w '\nHTTP %{http_code}\n' "${FOUNDRY_ENDPOINT%/}/openai/v1/models" -H "Authorization: Bearer $TOKEN"
```

```powershell title="PowerShell"
$TOKEN = az account get-access-token --resource https://cognitiveservices.azure.com --query accessToken -o tsv
$r = Invoke-WebRequest -Uri "$($FOUNDRY_ENDPOINT.TrimEnd('/'))/openai/v1/models" `
  -Headers @{ Authorization = "Bearer $TOKEN" } -SkipHttpErrorCheck
"HTTP $($r.StatusCode)"; $r.Content
```

The call returns `HTTP 403` with a message that public access is disabled: the internet can't reach Foundry
anymore, but the gateway can.

<!-- /steps -->

> **Checkpoint**
> The new gateway uses private routing through `snet-aigw-integration`, Foundry resolves to a `10.20.1.x` address
> inside the virtual network, model calls through the gateway return `200`, and direct calls to Foundry from the
> internet return `403`.

## Go further

- **Filter who can call the gateway.** While the frontend stays public, add a gateway-wide `ipFilter` policy
  (`action: Allow` with your egress `cidrRanges`) next to keys or Microsoft Entra ID. See
  [Set gateway-wide policy baselines](../09-gateway-baselines/README.md).
- **Hub-and-spoke networks.** Keep backend private endpoints and their private DNS zones in a hub, peer the
  gateway's virtual network to it, and link the zones to the integrated virtual network. If you use your own DNS
  servers, forward the `privatelink` zones to Azure DNS. See
  [Azure private endpoint DNS configuration](https://learn.microsoft.com/azure/private-link/private-endpoint-dns).
- **Private MCP servers and APIs.** Any backend with a private endpoint or a private IP that the integrated
  virtual network can reach works the same way, including the tool servers from
  [Federate MCP tools behind one endpoint](../04-federate-mcp-tools/README.md).
- **Data residency.** Residency follows the whole request path, so account for where your backends, tools, logs,
  and clients live, not only the gateway region.

## Clean up

Re-enable Foundry's public access first, because the gateway from the earlier labs and other callers reach it
over the internet. Then remove the new gateway's role assignment on Foundry and delete the lab's resource group,
which holds the gateway, its connector gateway, the private endpoint, the private DNS zones, the virtual network,
and the NSG.

```bash title="Bash"
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Enabled \
  --query properties.publicNetworkAccess -o tsv

PRINCIPAL_ID="$(az resource show --ids "$GATEWAY_ID" --query identity.principalId -o tsv)"
az role assignment delete --assignee "$PRINCIPAL_ID" --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope "$FOUNDRY_ID"

az group delete -n "$RG" --yes
```

```powershell title="PowerShell"
az resource update --ids $FOUNDRY_ID --set properties.publicNetworkAccess=Enabled `
  --query properties.publicNetworkAccess -o tsv

$PRINCIPAL_ID = az resource show --ids $GATEWAY_ID --query identity.principalId -o tsv
az role assignment delete --assignee $PRINCIPAL_ID --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" --scope $FOUNDRY_ID

az group delete -n $RG --yes
```

In the portal, you can do the same: re-enable public network access on the Foundry resource, remove the new
gateway's **Foundry User** role assignment in its **Access control (IAM)**, and delete `rg-ai-gateway-private`.

If you put the lab's resources in a resource group you want to keep, delete them in this order instead: the
gateway and its connector gateway, then the private endpoint, the private DNS zone links and zones, the virtual
network, and the NSG.

```bash title="Bash"
az resource delete --ids "$GATEWAY_ID" --api-version 2025-09-01-preview
az resource delete -g "$RG" -n "$GATEWAY" --resource-type Microsoft.Web/connectorGateways --api-version 2026-05-01-preview
```

```powershell title="PowerShell"
az resource delete --ids $GATEWAY_ID --api-version 2025-09-01-preview
az resource delete -g $RG -n $GATEWAY --resource-type Microsoft.Web/connectorGateways --api-version 2026-05-01-preview
```

Keep the gateway, model, and key from the earlier labs. The next labs reuse them.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| The create dialog flags the subnet, or the create request fails with a subnet error | The subnet is in another subscription or region, smaller than `/27`, not delegated to `Microsoft.Web/serverFarms`, used by another gateway or resource, or its NSG lacks the 443 rules | Fix each item. The NSG needs outbound TCP 443 allow rules to the `Storage` and `AzureKeyVault` service tags. |
| "Virtual network integration for Azure AI Gateway can only be configured during creation." | You tried to add, change, or remove private routing on an existing gateway | Create a new gateway with private routing. |
| Model calls through the new gateway fail after you turn off Foundry public access | The gateway resolves Foundry to its public IP: the zones aren't linked to the integrated virtual network, the private endpoint has no DNS zone group, or the gateway was created without private routing | Check the `A` records and zone links, and confirm that `properties.backend.subnet.id` points to the integration subnet. |
| The gateway from the earlier labs, or another app, now gets `403` from Foundry | It reaches Foundry over the internet, and Foundry's public access is disabled | Expected. Use a dedicated Foundry resource for this lab, or re-enable public access when you finish. |
| The first call after the import returns `401` or `403` from the backend | The **Foundry User** role assignment hasn't propagated yet | Wait a few minutes, and confirm that the role is assigned to the new gateway's principal ID on the Foundry resource. |
| **Public network access** › **Disabled** is greyed out, or a `PATCH` to `Disabled` doesn't stick | Private frontend access isn't available for AI Gateway yet | Expected. Protect the public endpoint with keys or Microsoft Entra ID and an `ipFilter` policy. |
| Deleting the resource group or the virtual network fails because the subnet is in use | The service is still releasing the gateway's integration subnet | Wait a few minutes after the gateway is gone, then delete again. |

## Next steps

- [Deploy an enterprise reference architecture](../21-enterprise-reference/README.md): put the gateway, models,
  tools, policies, and telemetry in one repeatable deployment.
- [Set gateway-wide policy baselines](../09-gateway-baselines/README.md): add an IP filter to the public
  frontend.
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): combine network isolation with identity.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): confirm that private traffic still produces
  telemetry.
- Docs: [Networking](https://ai.gateway.azure.com/docs/networking).
