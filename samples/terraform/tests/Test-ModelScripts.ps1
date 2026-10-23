$ErrorActionPreference = 'Stop'
$scripts = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts'
$global:modelScriptTest = @{}

function New-TestOutputs {
    @{
        gateway_endpoint = @{ value = 'https://gateway.example' }
        gateway_api_key_id = @{ value = '/subscriptions/test/providers/Microsoft.ApiManagement/service/test/apiKeys/default' }
        model_deployment_ids = @{ value = @{ mini = 'mini-id'; full = 'full-id' } }
        model_api_configuration = @{ value = @{
            mini = @{ api_format = 'OpenAIChatCompletions'; endpoints = @('/openai/v1/chat/completions') }
            full = @{ api_format = 'OpenAIChatCompletions'; endpoints = @('/openai/v1/chat/completions', '/openai/v1/responses') }
        } }
        private_probe_configuration = @{ value = @{ model_names = @('mini', 'full') } }
        private_test_vm_id = @{ value = '/subscriptions/test/resourceGroups/test/providers/Microsoft.Compute/virtualMachines/test' }
    }
}

function terraform {
    $global:LASTEXITCODE = $global:modelScriptTest.terraformExit
    $global:modelScriptTest.outputs | ConvertTo-Json -Depth 10
}

function az {
    $global:modelScriptTest.azCalls++
    $global:LASTEXITCODE = $global:modelScriptTest.azExit
    if ($args[0] -eq 'vm') {
        $index = [Array]::IndexOf($args, '--scripts')
        if ($index -lt 0) { throw 'Missing Run Command script.' }
        $path = ([string]$args[$index + 1]).Substring(1)
        $source = Get-Content -LiteralPath $path -Raw
        if ($source -notmatch "python3 - '([^']+)'") { throw 'Missing probe configuration.' }
        $configuration = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Matches[1])) | ConvertFrom-Json
        if ($configuration.model_apis.full.api_format -ne 'OpenAIChatCompletions' -or
            '/openai/v1/chat/completions' -notin $configuration.model_apis.full.endpoints) {
            throw 'The wrapper did not forward API metadata to the VM.'
        }
        $global:modelScriptTest.scriptPath = $path
        return (@{ value = @(@{ message = '{"passed":true}' }) } | ConvertTo-Json -Depth 5)
    }
    'test-key-must-not-appear'
}

function Invoke-RestMethod {
    param($Method, $Uri, $Headers, $ContentType, $Body)
    if ($Uri -ne 'https://gateway.example/default/models/openai/v1/chat/completions' -or
        $Headers['Api-Key'] -ne 'test-key-must-not-appear') {
        throw 'Unexpected inference target/authentication.'
    }
    $global:modelScriptTest.models.Add(($Body | ConvertFrom-Json).model)
    @{ choices = @(@{ message = @{ content = 'OK' } }) }
}

function Reset-Test {
    $global:modelScriptTest.outputs = New-TestOutputs
    $global:modelScriptTest.terraformExit = 0
    $global:modelScriptTest.azExit = 0
    $global:modelScriptTest.azCalls = 0
    $global:modelScriptTest.models = [System.Collections.Generic.List[string]]::new()
}

function Assert-Rejected {
    param([string]$ScriptName, [string]$Expected, [int]$ExpectedAzCalls = 0)
    $failure = $null
    try { & (Join-Path $scripts $ScriptName) | Out-Null }
    catch { $failure = $_.Exception.Message }
    if (-not $failure -or $failure -notmatch $Expected) {
        throw "Expected rejection matching '$Expected', got '$failure'."
    }
    if ($global:modelScriptTest.azCalls -ne $ExpectedAzCalls -or $global:modelScriptTest.models.Count -ne 0) {
        throw 'A rejected configuration reached an unexpected external call.'
    }
}

Reset-Test
$result = (& (Join-Path $scripts 'Test-ModelAliases.ps1')) -join "`n"
if ($global:modelScriptTest.azCalls -ne 1 -or $global:modelScriptTest.models.Count -ne 2 -or
    'mini' -notin $global:modelScriptTest.models -or 'full' -notin $global:modelScriptTest.models -or
    $result -match 'test-key-must-not-appear') {
    throw 'Compatible aliases were not all tested safely.'
}

foreach ($case in @('responses', 'format', 'missing-alias', 'missing-output', 'empty-endpoints')) {
    Reset-Test
    switch ($case) {
        'responses' { $global:modelScriptTest.outputs.model_api_configuration.value.full.endpoints = @('/openai/v1/responses') }
        'format' { $global:modelScriptTest.outputs.model_api_configuration.value.full.api_format = 'Other' }
        'missing-alias' { $global:modelScriptTest.outputs.model_api_configuration.value.Remove('full') }
        'missing-output' { $global:modelScriptTest.outputs.Remove('model_api_configuration') }
        'empty-endpoints' { $global:modelScriptTest.outputs.model_api_configuration.value.full.endpoints = @() }
    }
    Assert-Rejected 'Test-ModelAliases.ps1' 'Unsupported probe API|Missing model_api_configuration'
}

foreach ($name in @('Test-ModelAliases.ps1', 'Test-PrivateGateway.ps1')) {
    Reset-Test
    $global:modelScriptTest.terraformExit = 1
    Assert-Rejected $name 'Cannot read Terraform outputs'
}

Reset-Test
$global:modelScriptTest.outputs.Remove('model_api_configuration')
Assert-Rejected 'Test-PrivateGateway.ps1' 'Missing model_api_configuration'

Reset-Test
$global:modelScriptTest.azExit = 1
Assert-Rejected 'Test-ModelAliases.ps1' 'Unable to retrieve the gateway key' 1

Reset-Test
$privateResult = & (Join-Path $scripts 'Test-PrivateGateway.ps1') | ConvertFrom-Json
if (-not $privateResult.passed -or $global:modelScriptTest.azCalls -ne 1 -or
    (Test-Path -LiteralPath $global:modelScriptTest.scriptPath)) {
    throw 'Private wrapper metadata transport or temporary-file cleanup failed.'
}

'Model-script checks passed (11 cases; no Azure or model calls).'
