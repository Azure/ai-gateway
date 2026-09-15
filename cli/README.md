# AI Gateway CLI

Create an AI Gateway, register model providers and MCP servers, and manage
policies, keys, identities, and networking from your terminal with `az aigateway`.

> **Public preview**: commands and behavior may change before general availability.
> Current extension release: **1.0.0b6**.

[Install](#install) | [Quickstart](#quickstart) | [Command reference](command-reference.md) | [AI Gateway documentation](https://aka.ms/aigateway/docs)

## Install

Install [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
first (`az --version`). The extension declares Azure CLI **2.75.0 or later**;
using a current Azure CLI release is recommended.

**Bash (macOS / Linux)**

```bash
curl -fsSL https://aka.ms/aigateway-cli-install | sh
```

Requires `curl` and either `shasum` or `sha256sum`.

**PowerShell (Windows / macOS / Linux)**

```powershell
irm https://aka.ms/aigateway-cli-install-ps | iex
```

PowerShell does not need `curl`. Neither installer needs Git, GitHub CLI, a
separate Python installation, or an Azure login. Both need HTTPS access and
permission to write to your Azure CLI extension directory.

The installers download the published release, verify the wheel's SHA-256,
and install or upgrade the `aigateway` extension. To inspect a script before
running it, see [install.sh](install.sh) or [install.ps1](install.ps1).

### Verify

```bash
az aigateway version
az aigateway --help
```

`version` reports `extensionName: aigateway`, `extensionVersion: 1.0.0b6`,
and `apiVersion: 2025-09-01-preview`. Neither command needs an Azure login.

## Quickstart

Create a gateway and register the public
[Microsoft Learn MCP server](https://learn.microsoft.com/training/support/mcp).
This example uses **Bash**; replace the placeholder values before running it.
No model deployment or GitHub credential is needed.

### Before using Azure resources

You need an Azure subscription with access to the AI Gateway preview, a supported
region, and permission to create resources in the subscription or target resource
group (for example, Contributor at the appropriate scope). The
`Microsoft.ApiManagement` resource provider must be registered in the subscription;
ask your subscription administrator if registration is needed. See the
[AI Gateway documentation](https://aka.ms/aigateway/docs) for availability.

**This tutorial creates Azure resources.** The AI Gateway tier is currently free
during public preview; connected services and other Azure resources may incur
charges. Use a new, dedicated resource group and review pricing before proceeding.

### 1. Sign in and create a gateway

Choose a globally unique gateway name and a supported region.

```bash
az login
az account set --subscription "<subscription-id>"

RG="rg-aigateway-quickstart"
GATEWAY="<globally-unique-gateway-name>"
LOCATION="<supported-region>"

az group create --name "$RG" --location "$LOCATION"
az aigateway create --resource-group "$RG" --name "$GATEWAY" --location "$LOCATION"
az aigateway show --resource-group "$RG" --name "$GATEWAY" --output table
```

Creation waits for provisioning to finish. The gateway is an Azure API Management
resource (`Microsoft.ApiManagement/service`) with the `AIGateway` SKU; the CLI
selects the SKU for you.

### 2. Register an MCP server

The Learn endpoint does not require backend authentication. This command adds a
registration to your gateway; it does not deploy a new MCP server.

```bash
az aigateway mcp create \
  --resource-group "$RG" --gateway-name "$GATEWAY" --name learn \
  --endpoints '[{"kind":"mcp","namespace":"learn","mcp":{"transport":"streamableHttp","url":"https://learn.microsoft.com/api/mcp"}}]'

az aigateway mcp list --resource-group "$RG" --gateway-name "$GATEWAY" --output table
az aigateway mcp show --resource-group "$RG" --gateway-name "$GATEWAY" --name learn
```

Notice that `--name` now identifies the **MCP registration**; `--gateway-name`
identifies its parent gateway. The output shows the registered server and its
configuration, not a tool invocation. Use the
[coding-agent plugin](../README.md#coding-agent-plugin) to build an application
that consumes the gateway, or explore more commands in the
[command reference](command-reference.md).

### 3. Optional cleanup

Only run these commands for the dedicated tutorial resources. Gateway deletion
removes its registrations and retains an API Management soft-delete record;
the name may not be immediately reusable. Resource group deletion removes
**everything** remaining in that group. Both commands prompt for confirmation.

```bash
az aigateway delete --resource-group "$RG" --name "$GATEWAY"
az group delete --name "$RG"
```

## Uninstall

```bash
az extension remove --name aigateway
```

This removes the local CLI extension, not your Azure resources.
