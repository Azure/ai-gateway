# Azure AI Gateway quick start: deploys a gateway with a published Foundry model in one deployment, reads the
# runtime API key without printing it, and makes the first model call. Takes about five minutes.
#
# Usage, from labs/quickstart:
#   ./infra/quickstart.ps1 [-ResourceGroup rg-aigw-quickstart] [-Location eastus2]
# Requires PowerShell 7 or later and the Azure CLI, signed in with az login.
param(
  [string]$ResourceGroup = 'rg-aigw-quickstart',
  [ValidateSet('eastus2', 'swedencentral')]
  [string]$Location = 'eastus2'
)
$ErrorActionPreference = 'Stop'
$api = 'api-version=2025-09-01-preview'
$timer = [Diagnostics.Stopwatch]::StartNew()

$subscription = az account show --query name -o tsv 2>$null
if (-not $subscription) { throw 'Sign in first: az login' }
Write-Host "Subscription: $subscription"
$PSNativeCommandUseErrorActionPreference = $true

Write-Host "[1/3] Deploying a gateway and a Foundry model to $ResourceGroup in $Location. This takes about 3 minutes..."
az group create --name $ResourceGroup --location $Location --output none
$outputs = az deployment group create --resource-group $ResourceGroup --name quickstart `
  --template-file (Join-Path $PSScriptRoot 'main.bicep') --parameters location=$Location `
  --query properties.outputs --output json --only-show-errors | ConvertFrom-Json
$gatewayId = $outputs.gatewayId.value
$keyName = $outputs.apiKeyName.value
$env:AI_GATEWAY_URL = $outputs.gatewayUrl.value
$env:AI_GATEWAY_MODEL = $outputs.aliasName.value
Write-Host "      Gateway $($outputs.gatewayName.value) is ready at $env:AI_GATEWAY_URL"

Write-Host "[2/3] Reading the runtime key $keyName. The script doesn't print it."
$env:AI_GATEWAY_API_KEY = az rest --method post `
  --url "https://management.azure.com$gatewayId/apiKeys/$keyName/listSecrets?$api" `
  --query primaryKey --output tsv

Write-Host "[3/3] Calling $env:AI_GATEWAY_MODEL through the gateway"
$body = @{
  model    = $env:AI_GATEWAY_MODEL
  messages = @(@{ role = 'user'; content = 'In one sentence, what does an AI gateway do?' })
} | ConvertTo-Json -Depth 5
$maxAttempts = 18
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
  $response = Invoke-WebRequest -Method Post -Uri "$env:AI_GATEWAY_URL/default/models/openai/v1/chat/completions" `
    -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } -ContentType 'application/json' -Body $body -SkipHttpErrorCheck
  if ($response.StatusCode -eq 200) { break }
  # A new key, alias, or role assignment can take a minute to apply.
  if ($response.StatusCode -in 401, 403, 404 -and $attempt -lt $maxAttempts) {
    Write-Host "      HTTP $($response.StatusCode) while the new settings apply. Retrying in 10 seconds..."
    Start-Sleep -Seconds 10
    continue
  }
  throw "HTTP $($response.StatusCode): $($response.Content)"
}
$reply = $response.Content | ConvertFrom-Json

Write-Host ''
Write-Host "HTTP 200 from $($reply.model):"
Write-Host "  $($reply.choices[0].message.content)"
Write-Host ''
Write-Host ("Done in {0} min {1} s." -f [int][math]::Floor($timer.Elapsed.TotalMinutes), $timer.Elapsed.Seconds)
Write-Host "  Model endpoint  $($outputs.modelEndpoint.value)"
Write-Host "  Alias           $env:AI_GATEWAY_MODEL"
Write-Host '  Portal          https://ai.gateway.azure.com'
Write-Host ''
Write-Host 'This session now has AI_GATEWAY_URL, AI_GATEWAY_MODEL, and AI_GATEWAY_API_KEY set.'
Write-Host ''
Write-Host "Clean up when you're done:"
Write-Host "  az group delete --name $ResourceGroup --yes"
Write-Host "  az cognitiveservices account purge --name $($outputs.foundryAccountName.value) --resource-group $ResourceGroup --location $Location"
