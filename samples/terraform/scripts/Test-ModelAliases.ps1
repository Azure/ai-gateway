# Sends a short chat request to every configured model alias through the gateway.
# Run from samples/terraform after a successful apply, signed in with az login.
# Needs permission to read the gateway key (Microsoft.ApiManagement/service/apiKeys/listSecrets/action).
# Model calls incur inference charges.

$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
$outputsJson = & terraform "-chdir=$root" output -json
if ($LASTEXITCODE -ne 0) { throw "Cannot read Terraform outputs." }
$outputs = $outputsJson | ConvertFrom-Json
$gatewayUrl = ([string]$outputs.gateway_endpoint.value).TrimEnd('/')
$keyId = $outputs.gateway_api_key_id.value
$modelNames = @($outputs.model_deployment_ids.value.PSObject.Properties.Name)
if (!$gatewayUrl -or !$keyId -or $modelNames.Count -eq 0) {
    throw "Gateway endpoint, API key resource ID, or model aliases are missing."
}
$modelApis = $outputs.model_api_configuration.value
if (-not $modelApis) {
    throw "Missing model_api_configuration output. Review and apply the output update with your existing inputs/profile before testing."
}
foreach ($model in $modelNames) {
    $api = $modelApis.PSObject.Properties[$model].Value
    if ($api.api_format -cne 'OpenAIChatCompletions' -or
        @($api.endpoints) -cnotcontains '/openai/v1/chat/completions') {
        throw "Unsupported probe API for ${model}: requires OpenAIChatCompletions and /openai/v1/chat/completions. Use a model-specific test; this is not a network failure."
    }
}

$apiKey = $null
try {
    $apiKey = az rest --method post `
        --url "https://management.azure.com${keyId}/listSecrets?api-version=2025-09-01-preview" `
        --query primaryKey --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($apiKey)) {
        throw "Unable to retrieve the gateway key. Check your Azure identity and permissions."
    }
    $headers = @{ "Api-Key" = $apiKey }

    foreach ($model in $modelNames) {
        $body = @{
            model    = $model
            messages = @(@{ role = "user"; content = "Say hello in one short sentence." })
        } | ConvertTo-Json -Depth 5

        $reply = Invoke-RestMethod -Method Post `
            -Uri "$gatewayUrl/default/models/openai/v1/chat/completions" `
            -Headers $headers -ContentType "application/json" -Body $body

        if (!$reply.choices -or !$reply.choices[0].message.content) {
            throw "No chat-completion text returned for alias '$model'."
        }
        "{0}: {1}" -f $model, $reply.choices[0].message.content
    }
}
finally {
    $apiKey = $null
    $headers = $null
}
