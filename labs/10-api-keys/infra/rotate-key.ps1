<#
.SYNOPSIS
  Regenerates one value (primary or secondary) of an AI Gateway runtime API key, reads the new value, and
  optionally stores it in Azure Key Vault. Only the last four characters of the key are printed.

.DESCRIPTION
  Zero-downtime rotation for clients that use the primary value today:
    1. ./rotate-key.ps1 -ResourceGroup $RG -Gateway $GATEWAY -KeyName support-bot -KeyType secondary
    2. Move every client to the secondary value.
    3. ./rotate-key.ps1 -ResourceGroup $RG -Gateway $GATEWAY -KeyName support-bot -KeyType primary
  Next time, swap the roles: regenerate primary first, move clients, then regenerate secondary.
  Requires the Azure CLI 2.75 or later. It calls the Azure Resource Manager REST API with az rest, because the
  az aigateway extension doesn't manage the Microsoft.ApiManagement/aigateways resource type yet.

.EXAMPLE
  ./rotate-key.ps1 -ResourceGroup $RG -Gateway $GATEWAY -KeyName support-bot -KeyType secondary -KeyVault $KEY_VAULT
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$ResourceGroup,
  [Parameter(Mandatory)] [string]$Gateway,
  [Parameter(Mandatory)] [string]$KeyName,
  [Parameter(Mandatory)] [ValidateSet("primary", "secondary")] [string]$KeyType,
  [string]$KeyVault
)
$ErrorActionPreference = "Stop"

$api = "api-version=2025-09-01-preview"
$gatewayId = az resource show -g $ResourceGroup -n $Gateway --resource-type Microsoft.ApiManagement/aigateways `
  --query id -o tsv
if ($LASTEXITCODE -ne 0 -or -not $gatewayId) { throw "Couldn't find AI Gateway '$Gateway' in '$ResourceGroup'." }
$keyUrl = "https://management.azure.com$gatewayId/apiKeys/$KeyName"
$action = if ($KeyType -eq "primary") { "regeneratePrimaryKey" } else { "regenerateSecondaryKey" }

az rest --method post --url "$keyUrl/${action}?$api" -o none
if ($LASTEXITCODE -ne 0) { throw "$action failed." }

$value = az rest --method post --url "$keyUrl/listSecrets?$api" --query "${KeyType}Key" -o tsv
if ($LASTEXITCODE -ne 0 -or -not $value) {
  throw "Couldn't read the new $KeyType value. You need the apiKeys/listSecrets/action permission."
}
Write-Host "Regenerated the $KeyType value of '$KeyName' (ends in ...$($value.Substring([Math]::Max(0, $value.Length - 4))))."

if ($KeyVault) {
  $secret = "$KeyName-api-key"
  az keyvault secret set --vault-name $KeyVault --name $secret --value $value `
    --tags "aigateway-key=$KeyName" "key-type=$KeyType" -o none
  if ($LASTEXITCODE -ne 0) { throw "az keyvault secret set failed." }
  Write-Host "Stored it in Key Vault '$KeyVault' as secret '$secret'."
} else {
  Write-Host "Read it with: az rest --method post --url '$keyUrl/listSecrets?$api' --query ${KeyType}Key -o tsv"
}
