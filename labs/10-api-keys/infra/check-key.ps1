<#
.SYNOPSIS
  Sends one small Chat Completions request through AI Gateway and reports whether the gateway accepted the
  runtime API key. Only the last four characters of the key are printed.

.EXAMPLE
  $env:AI_GATEWAY_URL     = "https://<gateway>.azure-api.net"
  $env:AI_GATEWAY_MODEL   = "<model-alias>"
  $env:AI_GATEWAY_API_KEY = Read-Host "AI Gateway API key" -MaskInput
  ./check-key.ps1 -Label "app-dev"

.EXAMPLE
  ./check-key.ps1 -ApiKey $oldKey -Label "old value"

.EXAMPLE
  ./check-key.ps1 -NoKey
#>
[CmdletBinding()]
param(
  [string]$ApiKey = $env:AI_GATEWAY_API_KEY,
  [string]$Label = "current key",
  [switch]$NoKey
)
$ErrorActionPreference = "Stop"

if (-not $env:AI_GATEWAY_URL)   { throw "Set `$env:AI_GATEWAY_URL to https://<gateway>.azure-api.net" }
if (-not $env:AI_GATEWAY_MODEL) { throw "Set `$env:AI_GATEWAY_MODEL to a callable model alias" }

$uri  = "$($env:AI_GATEWAY_URL.TrimEnd('/'))/default/models/openai/v1/chat/completions"
$body = @{ model = $env:AI_GATEWAY_MODEL; messages = @(@{ role = "user"; content = "ping" }) } | ConvertTo-Json -Depth 5

$headers = @{}
if ($NoKey) {
  $Label = "no key"
  $hint  = "-"
} else {
  if (-not $ApiKey) { throw "Pass -ApiKey or set `$env:AI_GATEWAY_API_KEY to the runtime key to test" }
  $headers["api-key"] = $ApiKey
  $hint = "..." + $ApiKey.Substring([Math]::Max(0, $ApiKey.Length - 4))
}

try {
  $status = (Invoke-WebRequest -Method Post -Uri $uri -Headers $headers -ContentType "application/json" `
    -Body $body -SkipHttpErrorCheck).StatusCode
} catch {
  Write-Warning $_.Exception.Message
  $status = 0
}

$result = switch ($status) {
  { $_ -ge 200 -and $_ -lt 300 } { "accepted"; break }
  401     { "rejected: the key is missing, invalid, rotated, or deleted"; break }
  0       { "no response: check AI_GATEWAY_URL and your network"; break }
  default { "key accepted, but the call failed: check AI_GATEWAY_MODEL and the gateway's policies" }
}

"{0,-14} {1,-8} HTTP {2}  {3}" -f $Label, $hint, $(if ($status) { $status } else { "---" }), $result
