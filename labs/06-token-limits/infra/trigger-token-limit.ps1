# Sends a burst of chat completions through AI Gateway and prints the status code,
# the remaining-tokens header, and Retry-After so you can watch a token limit engage.
#
# Usage:
#   $env:AI_GATEWAY_URL = "https://<gateway>.eastus2-01.ai.gateway.azure.com"
#   $env:AI_GATEWAY_API_KEY = "..."      # never commit this value
#   ./trigger-token-limit.ps1 -Model <model-alias> [-Requests 8]
param(
  [Parameter(Mandatory = $true)][string]$Model,
  [int]$Requests = 8
)
$ErrorActionPreference = 'Stop'
if (-not $env:AI_GATEWAY_URL) { throw 'Set $env:AI_GATEWAY_URL to https://<gateway>.eastus2-01.ai.gateway.azure.com' }
if (-not $env:AI_GATEWAY_API_KEY) { throw 'Set $env:AI_GATEWAY_API_KEY to a runtime key from Access > Keys' }

$uri = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$body = @{
  model      = $Model
  max_tokens = 250
  messages   = @(@{ role = 'user'; content = 'Write a 150-word product update about an AI gateway that governs models and tools.' })
} | ConvertTo-Json -Depth 5

1..$Requests | ForEach-Object {
  $r = Invoke-WebRequest -Method Post -Uri $uri -Body $body -ContentType 'application/json' `
    -Headers @{ 'api-key' = $env:AI_GATEWAY_API_KEY } -SkipHttpErrorCheck
  $used = if ($r.StatusCode -eq 200) { ($r.Content | ConvertFrom-Json).usage.total_tokens } else { '-' }
  [pscustomobject]@{
    Request           = $_
    Status            = $r.StatusCode
    'remaining-tokens' = ($r.Headers['remaining-tokens'] | Select-Object -First 1) ?? '-'
    'Retry-After'      = ($r.Headers['Retry-After'] | Select-Object -First 1) ?? '-'
    'Tokens used'      = $used
  }
} | Format-Table -AutoSize
