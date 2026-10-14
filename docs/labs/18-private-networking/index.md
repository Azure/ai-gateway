---
title: Lock down the gateway with private networking
summary: Join your AI Gateway to a virtual network, reach it through a private endpoint, call a private Foundry backend, and only then turn off public network access, with DNS checks at every step.
category: production
level: Advanced
duration: 45
tracks: [portal, cli, iac]
order: 18
illustration: diagrams/private-networking.svg
tags: [private endpoint, VNet integration, private DNS, privatelink.azure-api.net, NSG, public network access, zero trust]
objectives:
  - Explain why inbound private endpoints and outbound VNet integration are configured separately
  - Prepare a delegated integration subnet with an NSG that passes the gateway's prerequisite checks
  - Add an inbound private endpoint with the privatelink.azure-api.net zone and make a Foundry backend private
  - Prove name resolution and both traffic paths from a VM inside the virtual network
  - Disable public network access last, and roll it all back cleanly
prereqs:
  - 01-provision-gateway
  - 12-backend-identity
---

# Lock down the gateway with private networking

Your security team signs off on the AI platform only if model and tool traffic never crosses the public internet:
apps reach the gateway on a private IP, the gateway reaches Foundry on a private IP, and the public endpoint is
switched off. In this lab you build that topology step by step, verify each hop from a VM inside the virtual
network, and disable public access only after everything resolves and responds privately.

![Clients in a virtual network reach the gateway through a private endpoint, and the gateway reaches private backends through VNet integration](../assets/diagrams/private-networking.svg "Inbound and outbound are separate: a private endpoint brings clients in, VNet integration lets the gateway reach private backends, and private DNS ties both together.")

## Before you begin

- Complete [Provision your AI Gateway](../01-provision-gateway/README.md) and
  [Call backends with managed identities](../12-backend-identity/README.md). You need a gateway with an imported
  Foundry model that the gateway calls with its managed identity, a callable alias, and a runtime API key from
  **Access** › **Keys**.
- The [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.75 or later, signed in with
  `az login`, and the `aigateway` extension ([install it](https://github.com/Azure/ai-gateway/tree/main/cli#install)).
  Every track uses the CLI for the test VM and the verification steps.
- Permission to create network resources and to change the gateway and the Foundry resource, for example
  **Contributor** on their resource groups. Approving a private endpoint on the gateway also requires write access
  to the gateway.
- AI Gateway is in preview in East US 2 and Sweden Central. The virtual network for VNet integration must be in
  the gateway's region.

> [!IMPORTANT]
> This lab creates billable resources: private endpoints, private DNS zones, and a small Linux VM with a disk.
> AI Gateway itself is free during the preview. Follow [Clean up](#clean-up) when you finish.

Set these variables once. Every track and the **Verify** section reuse them.

```bash title="Bash"
export RG="<resource-group>"                 # the gateway's resource group; the lab adds the network here too
export GATEWAY="<gateway>"
export LOCATION="$(az aigateway show -g "$RG" -n "$GATEWAY" --query location -o tsv | tr -d ' ' | tr '[:upper:]' '[:lower:]')"

export VNET="vnet-aigw"
export INTEGRATION_SUBNET="snet-aigw-integration"
export PE_SUBNET="snet-private-endpoints"
export JUMPBOX_SUBNET="snet-jumpbox"
export NSG="nsg-aigw-integration"
export GATEWAY_PE="pe-$GATEWAY"
export JUMPBOX="vm-aigw-jumpbox"

# The Foundry resource behind the model you imported in the earlier labs
export FOUNDRY_ID="$(az cognitiveservices account show -g "<foundry-resource-group>" -n "<foundry-account-name>" --query id -o tsv)"

export AI_GATEWAY_URL="$(az aigateway show -g "$RG" -n "$GATEWAY" --query properties.gatewayUrl -o tsv)"
export AI_GATEWAY_MODEL="<model-name>"       # a callable alias, for example your Foundry deployment name
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
read -rsp "AI Gateway API key: " AI_GATEWAY_API_KEY && export AI_GATEWAY_API_KEY && echo
```

```powershell title="PowerShell"
$RG       = "<resource-group>"               # the gateway's resource group; the lab adds the network here too
$GATEWAY  = "<gateway>"
$LOCATION = (az aigateway show -g $RG -n $GATEWAY --query location -o tsv).Replace(' ', '').ToLower()

$VNET               = "vnet-aigw"
$INTEGRATION_SUBNET = "snet-aigw-integration"
$PE_SUBNET          = "snet-private-endpoints"
$JUMPBOX_SUBNET     = "snet-jumpbox"
$NSG                = "nsg-aigw-integration"
$GATEWAY_PE         = "pe-$GATEWAY"
$JUMPBOX            = "vm-aigw-jumpbox"

# The Foundry resource behind the model you imported in the earlier labs
$FOUNDRY_ID = az cognitiveservices account show -g "<foundry-resource-group>" -n "<foundry-account-name>" --query id -o tsv

$env:AI_GATEWAY_URL   = az aigateway show -g $RG -n $GATEWAY --query properties.gatewayUrl -o tsv
$env:AI_GATEWAY_MODEL = "<model-name>"       # a callable alias, for example your Foundry deployment name
# Paste the runtime key you created in Access › Keys. Don't commit it or write it to a file.
$env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
```

> [!TIP]
> The CLI snippets in the tracks use Bash line continuations (`\`). In PowerShell, replace them with a backtick
> (`` ` ``) or put the command on one line. The variable names are the same in both shells.

## How it works

Private networking has two directions, and you configure them separately. **Inbound**, a private endpoint gives
the gateway a private IP in your virtual network, and the `privatelink.azure-api.net` private DNS zone makes the
gateway's usual host name resolve to that IP for clients in linked networks. **Outbound**, VNet integration joins
the gateway to a delegated subnet, so it can call models, MCP servers, and APIs on private IPs. An inbound private
endpoint doesn't grant outbound reach, and VNet integration doesn't make the gateway private.

The order matters. Turn on VNet integration first, add the inbound private endpoint, make your backends private,
test both paths, and disable public network access last. Most connectivity problems are DNS: clients must resolve
the gateway to its private endpoint IP, and the gateway must resolve each backend to its private IP.

| Piece | Direction | Where you set it | Key values |
|---|---|---|---|
| Integration subnet | Outbound | Your virtual network | At least `/27` (`/24` recommended), dedicated to one gateway, delegated to `Microsoft.Web/serverFarms`, NSG allows outbound TCP 443 to `Storage` and `AzureKeyVault` |
| VNet integration | Outbound | **Networking** › **Outbound** › **Private routing** | `virtualNetworkType: External`, `virtualNetworkConfiguration.subnetResourceId` |
| Gateway private endpoint | Inbound | **Networking** › **Inbound** › **Private endpoints** | Group ID (sub-resource) `Gateway` |
| Gateway private DNS | Inbound | Private DNS zone linked to every client network | `privatelink.azure-api.net` |
| Backend private endpoints | Outbound | Each backend, plus its private DNS zones | Foundry uses the `account` group ID |
| Public network access | Inbound | **Networking** › **Public network access** | `publicNetworkAccess: Enabled` or `Disabled` |

## Prepare the virtual network

You create one virtual network with three subnets. The integration subnet belongs to the gateway alone, private
endpoints get their own subnet, and a small subnet hosts the test VM.

| Subnet | Prefix | Used for | Settings |
|---|---|---|---|
| `snet-aigw-integration` | `10.20.0.0/24` | Gateway VNet integration (outbound) | NSG `nsg-aigw-integration`, delegated to `Microsoft.Web/serverFarms`, nothing else deployed in it |
| `snet-private-endpoints` | `10.20.1.0/24` | Private endpoints to the gateway and to Foundry | None |
| `snet-jumpbox` | `10.20.2.0/27` | Test VM | None |

Pick one track. The tracks produce the same network. The IaC track also declares the private endpoints in the
same template; you turn them on in a later section.

<!-- track: portal | Portal -->

### Create the network security group

In the [Azure portal](https://portal.azure.com), create a network security group named `nsg-aigw-integration`
in your gateway's resource group and region. Add two **outbound** security rules:

| Name | Priority | Source | Destination (service tag) | Protocol | Destination port | Action |
|---|---|---|---|---|---|---|
| `AllowStorageOutbound` | 100 | `VirtualNetwork` | `Storage` | TCP | `443` | Allow |
| `AllowKeyVaultOutbound` | 110 | `VirtualNetwork` | `AzureKeyVault` | TCP | `443` | Allow |

### Create the virtual network and subnets

Create a virtual network named `vnet-aigw` in the **same region as the gateway**, with the address space
`10.20.0.0/16`. Add the three subnets from the table above. On `snet-aigw-integration`, select the
`nsg-aigw-integration` network security group and delegate the subnet to `Microsoft.Web/serverFarms`.

> **Checkpoint**
> The virtual network shows three subnets, and `snet-aigw-integration` lists the delegation
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
az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$JUMPBOX_SUBNET" --address-prefixes 10.20.2.0/27
```

> **Checkpoint**
> This command shows the `/24` prefix, the `Microsoft.Web/serverFarms` delegation, and the NSG:
>
> ```bash
> az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$INTEGRATION_SUBNET" \
>   --query "{prefix:addressPrefix, delegation:delegations[0].serviceName, nsg:networkSecurityGroup.id}"
> ```

<!-- track: iac | Bicep -->

### Choose what to declare

The template declares everything **around** the gateway: the NSG, the virtual network and subnets, the inbound
private endpoint with its `privatelink.azure-api.net` zone, and an optional private endpoint to Foundry. It
references the gateway as `existing` and never redeclares it. A Bicep deployment sends a `PUT`, and redeclaring
the gateway service risks resetting settings you didn't copy into the template. Turning on VNet integration and
disabling public access are `PATCH` operations, so you run them with `az aigateway network update`, exactly like
the CLI track.

The private endpoints are behind parameters (`includeGatewayPrivateEndpoint` and `foundryAccountId`), so you can
follow the recommended order: deploy the network now, enable VNet integration next, and redeploy with the private
endpoints after that.

### Review the template

<!-- include: infra/main.bicep -->

On GitHub, open [infra/main.bicep](infra/main.bicep).

### Deploy the network

From the lab folder, deploy the template with the private endpoints turned off:

```bash
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" location="$LOCATION" includeGatewayPrivateEndpoint=false \
  --query properties.outputs
```

> **Checkpoint**
> The outputs include `integrationSubnetId` and `privateEndpointSubnetId`. In the Azure portal, the virtual network
> `vnet-aigw` shows three subnets, and `snet-aigw-integration` is delegated to `Microsoft.Web/serverFarms`.

<!-- /tracks -->

## Route outbound traffic through the virtual network

VNet integration comes first. It lets the gateway reach private backends, and it's a change on the gateway that
must finish before you continue.

<!-- track: portal | Portal -->

### Select the integration subnet

Open the [AI Gateway portal](https://ai.gateway.azure.com) and select your gateway from the gateway switcher.
Select **Networking** ("Manage the gateway's network configuration."). Under **Outbound**, select
**Private routing** ("Allow access to private backends through secure outbound connections"). Choose `vnet-aigw`
under **Virtual network** and `snet-aigw-integration` under **Subnet**, then select **Save**.

If the portal shows **VNet integration prerequisites may not be met**, check each item it lists before you save:

- Virtual network in the same region as the gateway
- Subnet dedicated to this gateway
- Subnet size ≥ /27 (recommended /24)
- Subnet delegated to Microsoft.Web/serverFarms
- NSG allows outbound HTTPS to Storage and Key Vault

### Wait for the update to finish

While the change applies, the page says the gateway's networking configuration is locked while an update is in
progress. Wait until the message clears before you make the next change.

> **Checkpoint**
> **Networking** › **Outbound** shows **Private routing** with `vnet-aigw` and `snet-aigw-integration` selected.

<!-- track: cli | Azure CLI -->

### Join the gateway to the subnet

`--subnet` takes the full resource ID of the delegated subnet. The command sends only the networking properties
you set (`virtualNetworkType: External` plus the subnet ID) and doesn't create the subnet for you.

```bash
INTEGRATION_SUBNET_ID="$(az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$INTEGRATION_SUBNET" --query id -o tsv)"

az aigateway network update -g "$RG" -n "$GATEWAY" --subnet "$INTEGRATION_SUBNET_ID"
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600
```

### Confirm the configuration

```bash
az aigateway network show -g "$RG" -n "$GATEWAY"
```

> **Checkpoint**
> The output shows `"virtualNetworkType": "External"`, your subnet ID under
> `virtualNetworkConfiguration.subnetResourceId`, `"publicNetworkAccess": "Enabled"`, and
> `"provisioningState": "Succeeded"`.

<!-- track: iac | Bicep -->

### Join the gateway to the subnet

Read the subnet ID from the deployment outputs and apply it with a `PATCH` through the CLI:

```bash
INTEGRATION_SUBNET_ID="$(az deployment group show -g "$RG" -n main --query properties.outputs.integrationSubnetId.value -o tsv)"

az aigateway network update -g "$RG" -n "$GATEWAY" --subnet "$INTEGRATION_SUBNET_ID"
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600
az aigateway network show -g "$RG" -n "$GATEWAY"
```

The deployment name defaults to the template file name, `main`. If you passed `--name` when you deployed, use
that name instead.

> **Checkpoint**
> `network show` returns `"virtualNetworkType": "External"`, your subnet ID, and `"provisioningState": "Succeeded"`.

<!-- /tracks -->

## Add an inbound private endpoint

Now give the gateway a private IP in `snet-private-endpoints`, and make its host name resolve to that IP inside the
virtual network. Public access stays on for now, so existing clients keep working while you test.

<!-- track: portal | Portal -->

### Create the private endpoint

In the AI Gateway portal, select **Networking**. Under **Inbound** › **Private endpoints**, select
**Create a private endpoint**. The Azure portal opens in a new tab. Create the private endpoint in the gateway's
region with these choices:

| Setting | Value |
|---|---|
| Name | `pe-<gateway>` |
| Target sub-resource | `Gateway` |
| Virtual network and subnet | `vnet-aigw` › `snet-private-endpoints` |
| Private IP configuration | Dynamic allocation |
| Private DNS integration | Yes, with the `privatelink.azure-api.net` zone in your resource group |

### Check the connection state

Return to the AI Gateway portal and refresh **Networking**. The **Private endpoints** table lists your endpoint
with its **Connection state** and **Provisioning state**. If the connection state is **Pending**, select the row
and choose **Approve**.

> **Checkpoint**
> The private endpoint row shows the connection state **Approved**.

<!-- track: cli | Azure CLI -->

### Create the private endpoint

```bash
GATEWAY_ID="$(az aigateway show -g "$RG" -n "$GATEWAY" --query id -o tsv)"

az network private-endpoint create -g "$RG" -n "$GATEWAY_PE" -l "$LOCATION" \
  --vnet-name "$VNET" --subnet "$PE_SUBNET" \
  --private-connection-resource-id "$GATEWAY_ID" --group-id Gateway --connection-name gateway
```

### Register it in private DNS

Create the `privatelink.azure-api.net` zone, link it to the virtual network, and attach it to the endpoint so the
A record stays in sync with the endpoint's IP:

```bash
az network private-dns zone create -g "$RG" -n privatelink.azure-api.net

az network private-dns link vnet create -g "$RG" -z privatelink.azure-api.net \
  -n "$VNET-link" -v "$VNET" -e false

az network private-endpoint dns-zone-group create -g "$RG" --endpoint-name "$GATEWAY_PE" \
  -n default --private-dns-zone privatelink.azure-api.net --zone-name apim-gateway
```

Link the zone to **every** virtual network whose clients must resolve the gateway, for example peered spokes.

### Check the connection state

```bash
az aigateway network private-endpoint-connection list -g "$RG" --gateway-name "$GATEWAY" \
  --query "[].{name:name, status:properties.privateLinkServiceConnectionState.status, state:properties.provisioningState}" -o table
```

If the status is `Pending`, approve the connection by name:

```bash
az aigateway network private-endpoint-connection approve -g "$RG" --gateway-name "$GATEWAY" \
  -n "<connection-name>" --description "Approved for private access"
```

> **Checkpoint**
> The connection status is `Approved`, and `az network private-dns record-set a list -g "$RG" -z privatelink.azure-api.net -o table`
> shows an A record for your gateway with an IP from `10.20.1.0/24`.

<!-- track: iac | Bicep -->

### Redeploy with the private endpoint

Run the same template again with `includeGatewayPrivateEndpoint=true`. The network resources are unchanged, and
the template adds the private endpoint (group ID `Gateway`), the `privatelink.azure-api.net` zone, its virtual
network link, and a DNS zone group named `default` with the `apim-gateway` configuration.

```bash
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" location="$LOCATION" includeGatewayPrivateEndpoint=true \
  --query properties.outputs
```

> [!NOTE]
> Keep the subnet parameters identical when you redeploy. The integration subnet is now in use by the gateway,
> so changing its prefix, delegation, or NSG fails.

### Check the connection state

```bash
az aigateway network private-endpoint-connection list -g "$RG" --gateway-name "$GATEWAY" \
  --query "[].{name:name, status:properties.privateLinkServiceConnectionState.status}" -o table
```

> **Checkpoint**
> The connection status is `Approved`. If it's `Pending`, approve it with
> `az aigateway network private-endpoint-connection approve` as shown in the CLI track.

<!-- /tracks -->

## Reach the model backend privately

The gateway now sits in your virtual network, but it still calls Foundry on its public endpoint. Give the Foundry
resource a private endpoint in the same virtual network and link its private DNS zones, so the integrated gateway
resolves Foundry to a private IP. Then turn off Foundry's public access. The gateway keeps authenticating with its
managed identity from [Call backends with managed identities](../12-backend-identity/README.md); only the network
path changes.

> [!WARNING]
> Disabling public access on the Foundry resource also blocks anything else that calls it over the internet,
> including tools on your workstation. Use a dedicated Foundry resource for this lab if others depend on it.

<!-- track: portal | Portal -->

### Add a private endpoint to Foundry

In the Azure portal, open your Foundry resource and add a private endpoint in `vnet-aigw` › `snet-private-endpoints`
for the `account` sub-resource, with private DNS integration turned on. The private DNS zones for Foundry are
`privatelink.cognitiveservices.azure.com`, `privatelink.openai.azure.com`, and `privatelink.services.ai.azure.com`.
For the full walkthrough, see
[How to configure network isolation for Microsoft Foundry](https://learn.microsoft.com/azure/ai-foundry/how-to/configure-private-link).

### Turn off public access to Foundry

After the private endpoint shows as approved, open the Foundry resource's networking settings and disable public
network access. See [Configure virtual networks for Foundry Tools](https://learn.microsoft.com/azure/ai-services/cognitive-services-virtual-networks).

<!-- track: cli | Azure CLI -->

### Add a private endpoint to Foundry

```bash
az network private-endpoint create -g "$RG" -n "pe-foundry-$GATEWAY" -l "$LOCATION" \
  --vnet-name "$VNET" --subnet "$PE_SUBNET" \
  --private-connection-resource-id "$FOUNDRY_ID" --group-id account --connection-name foundry
```

### Link the Foundry private DNS zones

Create each zone, link it to the virtual network, and add it to the endpoint's DNS zone group:

```bash
first=true
for zone in privatelink.cognitiveservices.azure.com privatelink.openai.azure.com privatelink.services.ai.azure.com; do
  az network private-dns zone create -g "$RG" -n "$zone"
  az network private-dns link vnet create -g "$RG" -z "$zone" -n "$VNET-link" -v "$VNET" -e false
  if $first; then
    az network private-endpoint dns-zone-group create -g "$RG" --endpoint-name "pe-foundry-$GATEWAY" \
      -n default --private-dns-zone "$zone" --zone-name "${zone//./-}"
    first=false
  else
    az network private-endpoint dns-zone-group add -g "$RG" --endpoint-name "pe-foundry-$GATEWAY" \
      -n default --private-dns-zone "$zone" --zone-name "${zone//./-}"
  fi
done
```

### Turn off public access to Foundry

```bash
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Disabled \
  --query properties.publicNetworkAccess -o tsv
```

<!-- track: iac | Bicep -->

### Redeploy with the Foundry private endpoint

Pass the Foundry resource ID. The template adds a private endpoint with the `account` group ID, the three Foundry
private DNS zones, their virtual network links, and a DNS zone group.

```bash
az deployment group create -g "$RG" \
  --template-file infra/main.bicep \
  --parameters gatewayName="$GATEWAY" location="$LOCATION" includeGatewayPrivateEndpoint=true \
               foundryAccountId="$FOUNDRY_ID" \
  --query properties.outputs
```

### Turn off public access to Foundry

The Foundry resource lives in its own template, so change only its public access setting here instead of
redeclaring it:

```bash
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Disabled \
  --query properties.publicNetworkAccess -o tsv
```

If you deploy Foundry with Bicep yourself, set `publicNetworkAccess: 'Disabled'` in that template instead.

<!-- /tracks -->

> **Checkpoint**
> From your workstation, call the model through the gateway. Public access to the **gateway** is still on, but the
> gateway now reaches Foundry only through the private endpoint, so a `200` proves the outbound private path:
>
> ```bash
> curl -sS -o /dev/null -w 'HTTP %{http_code}\n' "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
>   -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
>   -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: ok\"}],\"max_completion_tokens\":128}"
> ```

## Test the private path from inside the network

Before you switch anything off, prove that a client inside the virtual network resolves the gateway to its private
IP and gets an HTTP answer. A small Linux VM without a public IP is enough. You run commands on it with
`az vm run-command invoke`, so you don't need SSH, a bastion, or a gateway key on the VM.

### Create the test VM

```bash title="Bash"
az vm create -g "$RG" -n "$JUMPBOX" -l "$LOCATION" \
  --image Ubuntu2204 --size Standard_B2s \
  --vnet-name "$VNET" --subnet "$JUMPBOX_SUBNET" \
  --public-ip-address "" --nsg "" \
  --os-disk-delete-option Delete --nic-delete-option Delete \
  --admin-username azureuser --generate-ssh-keys
```

```powershell title="PowerShell"
az vm create -g $RG -n $JUMPBOX -l $LOCATION `
  --image Ubuntu2204 --size Standard_B2s `
  --vnet-name $VNET --subnet $JUMPBOX_SUBNET `
  --public-ip-address '""' --nsg '""' `
  --os-disk-delete-option Delete --nic-delete-option Delete `
  --admin-username azureuser --generate-ssh-keys
```

`--public-ip-address ""` and `--nsg ""` create the VM without a public IP or its own NSG, and the delete options
remove its disk and network interface when you delete the VM. If `Standard_B2s` isn't available in your region,
pick another small size.

### Run the DNS and HTTPS checks

From the lab folder, run the script for your shell. It sends [jumpbox-check.sh](infra/jumpbox-check.sh) to the VM,
which runs `nslookup` on the gateway host and sends one HTTPS request without credentials.

```bash title="Bash"
./infra/test-private-path.sh "$RG" "$JUMPBOX"
```

```powershell title="PowerShell"
./infra/test-private-path.ps1 -ResourceGroup $RG -VmName $JUMPBOX
```

On GitHub, open [test-private-path.sh](infra/test-private-path.sh) or
[test-private-path.ps1](infra/test-private-path.ps1).

Expected output (trimmed; your IP differs):

```text
[stdout]
== DNS: <gateway>.azure-api.net
Non-authoritative answer:
<gateway>.azure-api.net	canonical name = <gateway>.privatelink.azure-api.net.
Name:	<gateway>.privatelink.azure-api.net
Address: 10.20.1.4
== HTTPS: POST https://<gateway>.azure-api.net/default/models/openai/v1/chat/completions (no credentials)
HTTP 401 from 10.20.1.4
```

The name resolves through `privatelink.azure-api.net` to an IP in `snet-private-endpoints`, and the gateway answers
from that IP. The request carries no key, so the gateway rejects it; any HTTP status code proves the network path.
`HTTP 000` means DNS or routing failed.

> **Checkpoint**
> Inside the virtual network, the gateway resolves to a `10.20.1.x` address and answers over HTTPS. From your
> workstation, the model call through the gateway still returns `200`.

## Disable public network access

Disable public access only after private DNS and both traffic paths work. From now on, only clients that reach
the gateway through a private endpoint can call it. Apps and agents outside the virtual network, including the
tools on your workstation, stop working until you re-enable public access.

<!-- track: portal | Portal -->

### Switch public access off

In the AI Gateway portal, select **Networking**. Under **Public network access**, select **Disable**
("Only allow access to your resources through private endpoints"), then **Save**. Wait for the update to finish.

<!-- track: cli | Azure CLI -->

### Switch public access off

```bash
az aigateway network update -g "$RG" -n "$GATEWAY" --public-network-access Disabled
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600
```

<!-- track: iac | Bicep -->

### Switch public access off

This is a `PATCH` on the gateway, so use the CLI, as in the outbound section:

```bash
az aigateway network update -g "$RG" -n "$GATEWAY" --public-network-access Disabled
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600
```

<!-- /tracks -->

## Verify

<!-- steps -->

### Check the gateway's network settings

```bash
az aigateway network show -g "$RG" -n "$GATEWAY"
```

Expected output (trimmed):

```json
{
  "publicNetworkAccess": "Disabled",
  "virtualNetworkType": "External",
  "virtualNetworkConfiguration": {
    "subnetResourceId": "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Network/virtualNetworks/vnet-aigw/subnets/snet-aigw-integration"
  },
  "provisioningState": "Succeeded"
}
```

### Call from inside the virtual network

Run the jumpbox checks again. The gateway still resolves to its private IP and answers over HTTPS.

```bash title="Bash"
./infra/test-private-path.sh "$RG" "$JUMPBOX"
```

```powershell title="PowerShell"
./infra/test-private-path.ps1 -ResourceGroup $RG -VmName $JUMPBOX
```

### Call from outside the virtual network

Send the model request from your workstation again:

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' "${AI_GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  -H "api-key: $AI_GATEWAY_API_KEY" -H "Content-Type: application/json" \
  -d "{\"model\":\"$AI_GATEWAY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: ok\"}],\"max_completion_tokens\":128}"
```

The call no longer succeeds, because your workstation reaches the gateway over the internet and public network
access is disabled.

### Review the Networking page

In the AI Gateway portal, open **Networking**. **Public network access** shows **Disable**, **Outbound** shows
**Private routing** with your subnet, and **Private endpoints** lists your endpoint as approved. Management
operations in the portal and the CLI keep working, because they go through Azure Resource Manager, not the
gateway's runtime endpoint.

<!-- /steps -->

> **Checkpoint**
> The gateway answers only on its private IP, it reaches Foundry through a private endpoint, and public network
> access is disabled on both.

## Go further

- **Hub-and-spoke networks.** Put the private endpoint in a hub, peer your spokes, and link
  `privatelink.azure-api.net` to every spoke that hosts clients. For on-premises clients, forward the zone from your
  DNS servers to Azure. See [Azure private endpoint DNS configuration](https://learn.microsoft.com/azure/private-link/private-endpoint-dns).
- **Private MCP servers and APIs.** Any backend with a private endpoint or a private IP that the integrated
  virtual network can reach works the same way. Remember the second half of the DNS rule: the gateway must resolve
  each backend to its private IP.
- **Endpoints in another region.** The inbound private endpoint can be in a different region from the gateway, as
  long as it's in the same region as its own virtual network.
- **Data residency.** Residency follows the whole request path, so account for where your backends, tools, logs,
  and clients live, not only the gateway region.

## Clean up

Other labs call the gateway from your workstation, so re-enable public access first. Then remove VNet
integration before you delete the subnet it uses.

<!-- track: portal | Portal -->

### Restore public access and routing

In the AI Gateway portal, select **Networking**. Set **Public network access** to **Enable** and **Outbound** to
**Public routing**, then **Save**. Wait for the update to finish.

### Remove the network resources

In the Azure portal, re-enable public network access on your Foundry resource. Then delete the test VM, both
private endpoints (`pe-<gateway>` and `pe-foundry-<gateway>`), the private DNS zones, the virtual network, and the
network security group. Deleting a private endpoint also removes its connection from **Networking** ›
**Private endpoints**.

<!-- track: cli | Azure CLI -->

### Restore public access and routing

```bash
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Enabled --query properties.publicNetworkAccess -o tsv

az aigateway network update -g "$RG" -n "$GATEWAY" --public-network-access Enabled
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600

az aigateway network update -g "$RG" -n "$GATEWAY" --disable-vnet-integration true
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600
```

### Remove the network resources

```bash
az vm delete -g "$RG" -n "$JUMPBOX" --yes
az network private-endpoint delete -g "$RG" -n "$GATEWAY_PE"
az network private-endpoint delete -g "$RG" -n "pe-foundry-$GATEWAY"

for zone in privatelink.azure-api.net privatelink.cognitiveservices.azure.com privatelink.openai.azure.com privatelink.services.ai.azure.com; do
  az network private-dns link vnet delete -g "$RG" -z "$zone" -n "$VNET-link" --yes
  az network private-dns zone delete -g "$RG" -n "$zone" --yes
done
```

Delete the virtual network and the NSG last. The VM's disk and network interface go with the VM, because you
created it with the `Delete` options.

```bash
az network vnet delete -g "$RG" -n "$VNET"
az network nsg delete -g "$RG" -n "$NSG"
```

<!-- track: iac | Bicep -->

### Restore public access and routing

```bash
az resource update --ids "$FOUNDRY_ID" --set properties.publicNetworkAccess=Enabled --query properties.publicNetworkAccess -o tsv

az aigateway network update -g "$RG" -n "$GATEWAY" --public-network-access Enabled
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600

az aigateway network update -g "$RG" -n "$GATEWAY" --disable-vnet-integration true
az aigateway network wait -g "$RG" -n "$GATEWAY" --updated --timeout 3600
```

### Remove the deployed resources

Delete the test VM, then the resources the template created: both private
endpoints, the four private DNS zones and their links, the virtual network, and the NSG. The CLI track lists the
commands. If you deployed into a dedicated network resource group, deleting that group removes everything at once.

<!-- /tracks -->

Keep the gateway, model, and key. The next labs reuse them.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `nslookup` on the VM returns a public IP, or no `privatelink.azure-api.net` alias | The zone isn't linked to the VM's virtual network, or the endpoint has no DNS zone group | Link `privatelink.azure-api.net` to the virtual network and add the zone group (`apim-gateway` configuration) to the endpoint. |
| The portal shows **VNet integration prerequisites may not be met** | The subnet is in another region, smaller than `/27`, shared with other resources, not delegated, or the NSG lacks the 443 rules | Fix each listed item. The NSG needs outbound TCP 443 allow rules to `Storage` and `AzureKeyVault`. |
| Model calls fail after you disable Foundry public access | The gateway resolves Foundry to its public IP, or VNet integration isn't on | Confirm `virtualNetworkType` is `External`, and that the Foundry private DNS zones are linked to the integrated virtual network. An inbound private endpoint alone doesn't give the gateway outbound reach. |
| The private endpoint connection stays **Pending** | You created the endpoint without write access to the gateway | Approve it in **Networking** › **Private endpoints** or with `az aigateway network private-endpoint-connection approve`. |
| Clients outside the virtual network stop working | Public network access is disabled | Expected. Route those clients through a peered or linked network, or re-enable public access while you migrate them. |
| **Networking** changes are rejected while another change runs | The networking configuration is locked during an update | Wait for `az aigateway network wait --updated` to return, then retry. |

## Next steps

- [Deploy an enterprise reference architecture](../21-enterprise-reference/README.md): put the gateway, models,
  tools, policies, and telemetry in one repeatable deployment.
- [Monitor usage, cost, and traces](../13-monitoring/README.md): confirm that private traffic still produces
  telemetry.
- [Go keyless with Microsoft Entra ID and RBAC](../11-entra-rbac/README.md): combine network isolation with identity.
- Docs: [Networking](https://ai.gateway.azure.com/docs/networking).
