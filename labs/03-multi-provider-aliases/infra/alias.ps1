# Lists, creates, retargets, and deletes AI Gateway model aliases with the REST API.
# The `az aigateway` extension doesn't manage the aigateways resource type yet, so this script wraps `az rest`.
# Requires PowerShell 7 or later and the Azure CLI 2.75 or later (signed in).
#
# Usage:
#   $RG = "<resource-group>"; $GATEWAY = "<gateway>"
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY list
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY show     <alias>
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY put      <alias> <provider-name> <backend-model> [tokens-per-minute]
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY retarget <alias> <provider-name> <backend-model>
#   ./alias.ps1 -ResourceGroup $RG -Gateway $GATEWAY delete   <alias>
#
# "put" creates or replaces the whole alias, including its policies. With tokens-per-minute it adds a
# per-caller token limit to the alias. "retarget" sends a PATCH with only backendModels, so the alias
# name, description, and policies stay as they are.
param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$Gateway,
  [Parameter(Position = 0)][ValidateSet('list', 'show', 'put', 'retarget', 'delete')][string]$Action = 'list',
  [Parameter(Position = 1)][string]$Alias,
  [Parameter(Position = 2)][string]$Provider,
  [Parameter(Position = 3)][string]$Model,
  [Parameter(Position = 4)][int]$TokensPerMinute = 0
)
$ErrorActionPreference = 'Stop'

$api = 'api-version=2025-09-01-preview'
$gatewayId = az resource show -g $ResourceGroup -n $Gateway --resource-type Microsoft.ApiManagement/aigateways --query id -o tsv
if (-not $gatewayId) { throw "Gateway '$Gateway' not found in resource group '$ResourceGroup'." }
$wsId = "$gatewayId/workspaces/default"
$arm = 'https://management.azure.com'

function Get-Aliases { @((az rest --method get --url "$arm$wsId/aliases?$api" -o json | ConvertFrom-Json).value) }

# The callable alias lives in properties.aliasName and can contain "/". The resource name can't, so look
# up an existing alias by its callable name first, and otherwise derive a resource name from it.
function Get-ResourceName([string]$Name) {
  $found = Get-Aliases | Where-Object { ($_.properties.aliasName ?? $_.name) -eq $Name } | Select-Object -First 1
  if ($found) { return $found.name }
  ($Name.ToLowerInvariant() -replace '[^a-z0-9_.-]+', '-').Trim('-', '.')
}

function Format-Alias($Items) {
  $Items | ForEach-Object {
    $target = $_.properties.backendModels | Select-Object -First 1 -ExpandProperty resourceId
    $parts = if ($target) { $target -split '/' } else { @() }
    $policies = @($_.properties.policies | Where-Object { $_ } | ForEach-Object {
        if ($_.type -eq 'tokenLimit') { "tokenLimit $($_.count)/$($_.period)" } else { $_.type }
      })
    [pscustomobject]@{
      Alias                    = $_.properties.aliasName ?? $_.name
      'Provider/backend model' = if ($parts.Count -gt 2) { "$($parts[-3])/$($parts[-1])" } else { '-' }
      'Alias policies'         = if ($policies.Count) { $policies -join ', ' } else { '-' }
    }
  } | Format-Table -AutoSize
}

function Send-Alias([string]$Method, [string]$Name, [hashtable]$Body) {
  $file = Join-Path (Get-Location) "alias-$([guid]::NewGuid().ToString('N')).json"
  try {
    $Body | ConvertTo-Json -Depth 10 -Compress | Set-Content -Path $file
    az rest --method $Method --url "$arm$wsId/aliases/$Name`?$api" --body "@$file" -o none
    if ($LASTEXITCODE -ne 0) { throw "az rest $Method failed for alias '$Name'." }
  }
  finally { Remove-Item -Path $file -ErrorAction SilentlyContinue }
  Format-Alias @(az rest --method get --url "$arm$wsId/aliases/$Name`?$api" -o json | ConvertFrom-Json)
}

function Assert-Value([string]$Value, [string]$Message) { if (-not $Value) { throw $Message } }

switch ($Action) {
  'list' { Format-Alias (Get-Aliases) }
  'show' {
    Assert-Value $Alias 'Pass the alias.'
    az rest --method get --url "$arm$wsId/aliases/$(Get-ResourceName $Alias)`?$api"
  }
  'put' {
    Assert-Value $Alias 'Pass the alias.'; Assert-Value $Provider 'Pass the model provider name.'; Assert-Value $Model 'Pass the backend model name.'
    $policies = @()
    if ($TokensPerMinute -gt 0) {
      $policies = @(@{ type = 'tokenLimit'; count = $TokensPerMinute; period = 'minute'; counterKey = @('identity') })
    }
    Send-Alias put (Get-ResourceName $Alias) @{ properties = @{
        aliasName     = $Alias
        backendModels = @(@{ resourceId = "$wsId/modelProviders/$Provider/models/$Model" })
        policies      = $policies
      } }
  }
  'retarget' {
    Assert-Value $Alias 'Pass the alias.'; Assert-Value $Provider 'Pass the model provider name.'; Assert-Value $Model 'Pass the backend model name.'
    Send-Alias patch (Get-ResourceName $Alias) @{ properties = @{
        backendModels = @(@{ resourceId = "$wsId/modelProviders/$Provider/models/$Model" })
      } }
  }
  'delete' {
    Assert-Value $Alias 'Pass the alias.'
    az rest --method delete --url "$arm$wsId/aliases/$(Get-ResourceName $Alias)`?$api"
    "Deleted alias $Alias"
  }
}
