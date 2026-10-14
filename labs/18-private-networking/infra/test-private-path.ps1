# Tests the private path to your gateway from a VM inside the virtual network.
# Uses `az vm run-command invoke`, so the VM needs no public IP, no SSH session, and no gateway key.
# It runs jumpbox-check.sh on the VM: DNS lookup of the gateway host, then one HTTPS request.
#
# Usage:
#   $env:AI_GATEWAY_URL = "https://<gateway>.azure-api.net"
#   ./test-private-path.ps1 -ResourceGroup <resource-group> -VmName <vm-name>
param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$VmName
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to https://<gateway>.azure-api.net' }

$gatewayHost = ([uri]$env:AI_GATEWAY_URL).Host
$checkScript = Join-Path $PSScriptRoot 'jumpbox-check.sh'

Write-Host "Running checks for $gatewayHost on $VmName (this takes about a minute)..."
az vm run-command invoke -g $ResourceGroup -n $VmName --command-id RunShellScript `
  --scripts "@$checkScript" --parameters $gatewayHost `
  --query "value[0].message" -o tsv
if ($LASTEXITCODE -ne 0) { throw "az vm run-command invoke failed with exit code $LASTEXITCODE" }
