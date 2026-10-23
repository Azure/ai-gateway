$ErrorActionPreference = 'Stop'
$runner = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts\Test-CustomerAcceptance.ps1'
$subscription = '00000000-0000-0000-0000-000000000001'
$tenant = '00000000-0000-0000-0000-000000000002'
$group = "/subscriptions/$subscription/resourceGroups/test"
$gateway = "$group/providers/Microsoft.ApiManagement/service/gateway"
$models = "$group/providers/Microsoft.CognitiveServices/accounts/models"
$agents = "$group/providers/Microsoft.CognitiveServices/accounts/agents"
$project = "$agents/projects/project"
$storage = "$group/providers/Microsoft.Storage/storageAccounts/storage"
$registry = "$group/providers/Microsoft.ContainerRegistry/registries/registry"
$vm = "$group/providers/Microsoft.Compute/virtualMachines/test"
$vnet = "$group/providers/Microsoft.Network/virtualNetworks/vnet"
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) "gateway-acceptance-tests-$([guid]::NewGuid().ToString('N'))"
$null = New-Item -ItemType Directory -Path $testDirectory

function New-Fixture {
    $global:acceptanceTest = @{
        scenario = ''; calls = [Collections.Generic.List[string]]::new(); power = 'deallocated'
        resources = @{}; traces = @(('a' * 32), ('b' * 32))
        outputs = @{
            resource_group_name = @{ value = 'test' }
            resource_groups = @{ value = @{ gateway = 'test'; models = 'test'; agents = 'test' } }
            gateway_id = @{ value = $gateway }; foundry_models_id = @{ value = $models }; project_id = @{ value = $project }
            storage_account_name = @{ value = 'storage' }; container_registry_endpoint = @{ value = 'registry.azurecr.io' }
            private_test_vm_id = @{ value = $vm }
            application_insights_ids = @{ value = @{} }; private_endpoint_ids = @{ value = @{} }
            model_deployment_ids = @{ value = @{} }; model_api_configuration = @{ value = @{} }
            private_probe_configuration = @{ value = @{
                gateway_id = $gateway; gateway_endpoint = 'https://gateway.example'; model_endpoint = 'https://models.example'
                model_names = @('full', 'mini'); private_endpoint_subnet = '10.247.1.0/24'
            } }
        }
    }
    $f = $global:acceptanceTest
    foreach ($id in @($gateway, $models, $agents, $project, $storage, $registry)) {
        $f.resources[$id] = @{ id = $id; name = $id.Split('/')[-1]; properties = @{ provisioningState = 'Succeeded' } }
    }
    $f.resources[$gateway].sku = @{ name = 'AIGateway' }
    $f.resources[$gateway].identity = @{ principalId = 'gateway-principal'; tenantId = $tenant }
    $f.resources[$project].identity = @{ principalId = 'project-principal'; tenantId = $tenant }
    $f.resources[$gateway].properties += @{ publicNetworkAccess = 'Enabled'; virtualNetworkType = 'External'; virtualNetworkConfiguration = @{ subnetResourceId = "$vnet/subnets/gateway" } }
    $f.resources[$models].properties += @{ publicNetworkAccess = 'Disabled'; networkAcls = @{ defaultAction = 'Deny' }; endpoint = 'https://models.example/' }
    $f.resources[$storage].properties.primaryEndpoints = @{ blob = 'https://storage.blob.core.windows.net/' }
    $f.resources[$registry].properties.loginServer = 'registry.azurecr.io'
    $f.resources["$vnet/subnets/endpoints"] = @{ properties = @{ addressPrefix = '10.247.1.0/24' } }
    foreach ($name in @('gateway', 'agents')) {
        $insightsId = "$group/providers/Microsoft.Insights/components/$name"
        $workspaceId = "$group/providers/Microsoft.OperationalInsights/workspaces/$name"
        $f.outputs.application_insights_ids.value[$name] = $insightsId
        $f.resources[$insightsId] = @{ properties = @{ provisioningState = 'Succeeded'; WorkspaceResourceId = $workspaceId; AppId = $tenant } }
        $f.resources[$workspaceId] = @{ properties = @{ provisioningState = 'Succeeded' } }
    }
    foreach ($name in @('full', 'mini')) {
        $deploymentId = "$models/deployments/$name"
        $catalogId = "$gateway/workspaces/default/modelProviders/foundry/models/$name"
        $f.outputs.model_deployment_ids.value[$name] = $deploymentId
        $f.outputs.model_api_configuration.value[$name] = @{ api_format = 'OpenAIChatCompletions'; endpoints = @('/openai/v1/chat/completions') }
        $f.resources[$deploymentId] = @{ properties = @{ provisioningState = 'Succeeded' } }
        $f.resources[$catalogId] = @{ properties = @{ deployment = @{ resourceId = $deploymentId }; apiFormat = 'OpenAIChatCompletions'; supportedEndpoints = @('/openai/v1/chat/completions') } }
        $f.resources["$gateway/workspaces/default/aliases/$name"] = @{ properties = @{ aliasName = $name; backendModels = @(@{ resourceId = $catalogId }) } }
    }
    foreach ($name in @('gateway', 'models')) {
        $endpointId = "$group/providers/Microsoft.Network/privateEndpoints/$name"
        $target = if ($name -eq 'gateway') { $gateway } else { $models }
        $groupIds = if ($name -eq 'gateway') { @('Gateway') } else { @('account') }
        $zones = if ($name -eq 'gateway') { @('privatelink.azure-api.net') } else {
            @('privatelink.cognitiveservices.azure.com', 'privatelink.openai.azure.com', 'privatelink.services.ai.azure.com')
        }
        $f.outputs.private_endpoint_ids.value[$name] = $endpointId
        $f.resources[$endpointId] = @{ properties = @{
            provisioningState = 'Succeeded'; subnet = @{ id = "$vnet/subnets/endpoints" }; privateLinkServiceConnections = @(@{ properties = @{
                privateLinkServiceId = $target; groupIds = @($groupIds); privateLinkServiceConnectionState = @{ status = 'Approved' }
            } })
        } }
        $configs = @($zones | ForEach-Object { @{ properties = @{ privateDnsZoneId = "$group/providers/Microsoft.Network/privateDnsZones/$_" } } })
        $f.resources["$endpointId/privateDnsZoneGroups/default"] = @{ properties = @{ provisioningState = 'Succeeded'; privateDnsZoneConfigs = $configs } }
        foreach ($zone in $zones) {
            $f.resources["$group/providers/Microsoft.Network/privateDnsZones/$zone/virtualNetworkLinks/gateway-vnet"] = @{
                properties = @{ provisioningState = 'Succeeded'; virtualNetwork = @{ id = $vnet } }
            }
        }
    }
    $f.resources["$project/connections"] = @{ value = @(
        @{ name = 'storage'; properties = @{ category = 'AzureStorageAccount'; authType = 'AAD'; target = 'https://storage.blob.core.windows.net/'; metadata = @{ ResourceId = $storage } } },
        @{ name = 'registry-conn'; properties = @{ category = 'ContainerRegistry'; authType = 'ManagedIdentity'; target = 'registry.azurecr.io'; metadata = @{ ResourceId = $registry } } }
    ) }
    $f.resources["$agents/connections"] = @{ value = @(
        @{ name = 'agents'; properties = @{ category = 'AppInsights'; authType = 'ApiKey'; target = $f.outputs.application_insights_ids.value.agents; metadata = @{ ResourceId = $f.outputs.application_insights_ids.value.agents } } }
    ) }
    $f.resources["$gateway/workspaces/default/modelProviders/foundry"] = @{ properties = @{ foundry = @{
        authentication = @{ kind = 'ManagedIdentity'; managedIdentity = @{ resource = 'https://cognitiveservices.azure.com/' } }
        resourceIds = @($models); endpoint = 'https://models.example/'
    } } }
    $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"] = @{ properties = @{
        kind = 'applicationInsights'; payloadCapture = $false; applicationInsights = @{ resourceId = $f.outputs.application_insights_ids.value.gateway }
    } }
    foreach ($binding in @(
        @($models, 'gateway-principal', '53ca6127-db72-4b80-b1b0-d745d6d5456d'),
        @($storage, 'project-principal', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'),
        @($registry, 'project-principal', '7f951dda-4ed3-4680-a7ca-43fe172d538d'),
        @($agents, 'project-principal', '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'),
        @($agents, 'project-principal', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'),
        @($agents, 'project-principal', 'a97b65f3-24c7-4388-baec-2e87135dc908')
    )) {
        $id = "$($binding[0])/providers/Microsoft.Authorization/roleAssignments"
        if (-not $f.resources.ContainsKey($id)) { $f.resources[$id] = @{ value = @() } }
        $f.resources[$id].value += @{ properties = @{
            scope = $binding[0]; principalId = $binding[1]; principalType = 'ServicePrincipal'
            roleDefinitionId = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/$($binding[2])"
        } }
    }
}

function git {
    $global:LASTEXITCODE = 0
    if ('rev-parse' -in $args) { return ('c' * 40) }
    if ($global:acceptanceTest.scenario -eq 'dirty') { ' M main.tf' }
}

function terraform {
    $global:LASTEXITCODE = 0
    $f = $global:acceptanceTest
    if ('output' -in $args) {
        if ($f.scenario -eq 'terraform-error') { $global:LASTEXITCODE = 1; return 'SECRET-DO-NOT-LOG' }
        if ($f.scenario -eq 'malformed') { return 'SECRET-DO-NOT-LOG-invalid-json' }
        return ($f.outputs | ConvertTo-Json -Depth 20)
    }
    if ('plan' -in $args) {
        if ('-var-file=profiles/private-connectivity.tfvars.json' -notin $args) { throw 'Private profile missing.' }
        if ($f.scenario -eq 'drift') { $global:LASTEXITCODE = 2 }
        if ($f.scenario -eq 'plan-error') { $global:LASTEXITCODE = 1 }
        return 'SECRET-DO-NOT-LOG'
    }
    if ('show' -in $args) {
        $resources = @(
            @{ mode = 'managed'; values = @{ id = $group; type = 'Microsoft.Resources/resourceGroups@2021-04-01' } },
            @{ mode = 'managed'; values = @{ id = $gateway; type = 'Microsoft.ApiManagement/service@2025-09-01-preview' } }
        )
        if ($f.scenario -eq 'extra-group') { $resources += @{ mode = 'managed'; values = @{ id = "$group-old"; type = 'Microsoft.Resources/resourceGroups@2021-04-01' } } }
        return (@{ values = @{ root_module = @{ resources = $resources } } } | ConvertTo-Json -Depth 10)
    }
    throw 'Unexpected Terraform command.'
}

function az {
    $global:LASTEXITCODE = 0
    $f = $global:acceptanceTest
    $f.calls.Add(($args -join ' '))
    if ($args[0] -eq 'account') {
        $actualTenant = if ($f.scenario -eq 'wrong-tenant') { $subscription } else { $tenant }
        return (@{ id = $subscription; tenantId = $actualTenant } | ConvertTo-Json)
    }
    if ($args[0] -eq 'vm') {
        if ($args[1] -eq 'get-instance-view') {
            return (@{ instanceView = @{ statuses = @(@{ code = "PowerState/$($f.power)" }) } } | ConvertTo-Json -Depth 5)
        }
        if ($args[1] -eq 'start') { $f.power = 'running'; return '{}' }
        if ($args[1] -eq 'deallocate') {
            if ($f.scenario -eq 'cleanup-error') { $global:LASTEXITCODE = 1; return 'SECRET-DO-NOT-LOG' }
            $f.power = 'deallocated'; return '{}'
        }
        if ($args[1] -eq 'run-command') {
            $path = ([string]$args[[Array]::IndexOf($args, '--scripts') + 1]).Substring(1)
            $source = Get-Content -LiteralPath $path -Raw
            if ($source -notmatch "python3 - '([^']+)'") { throw 'Missing probe configuration.' }
            $configuration = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Matches[1])) | ConvertFrom-Json
            $f.scriptPath = $path
            $probe = @{
                run_id = $configuration.run_id; passed = ($f.scenario -ne 'runtime-error')
                inference = @(
                    @{ model = 'full'; status = 200; reply = 'OK'; trace_id = $f.traces[0] },
                    @{ model = 'mini'; status = 200; reply = 'OK'; trace_id = $f.traces[1] }
                )
                authentication = @(@{ case = 'missing-key'; status = 401 }, @{ case = 'invalid-key'; status = 401 })
            }
            $message = $probe | ConvertTo-Json -Depth 10 -Compress
            return (@{ value = @(@{ message = $message }) } | ConvertTo-Json -Depth 5)
        }
        throw 'Unexpected VM operation.'
    }
    $url = [string]$args[[Array]::IndexOf($args, '--url') + 1]
    if ($url.StartsWith('https://api.applicationinsights.io/')) {
        $rows = if ($f.scenario -eq 'missing-telemetry') { @() } else { @(@($f.traces[0]), @($f.traces[1])) }
        return (@{ tables = @(@{ columns = @(@{ name = 'operation_Id' }); rows = $rows }) } | ConvertTo-Json -Depth 10)
    }
    $id = ([uri]$url).AbsolutePath
    if ($f.scenario -eq 'arm-error') { $global:LASTEXITCODE = 1; return 'SECRET-DO-NOT-LOG' }
    if (-not $f.resources.ContainsKey($id)) { throw "Unexpected fixture resource: $id" }
    $f.resources[$id] | ConvertTo-Json -Depth 20
}

$cases = [ordered]@{
    pass = @('PASS', 'runtime'); readonly = @('BLOCKED', 'runtime')
    'wrong-tenant' = @('FAIL', 'context'); 'wrong-scope' = @('FAIL', 'context')
    'missing-output' = @('FAIL', 'context'); malformed = @('FAIL', 'context')
    'terraform-error' = @('FAIL', 'context'); dirty = @('FAIL', 'context')
    'extra-group' = @('FAIL', 'placement'); 'arm-error' = @('FAIL', 'resources')
    'failed-endpoint' = @('FAIL', 'private-network'); 'wrong-alias' = @('FAIL', 'resources')
    drift = @('FAIL', 'drift'); 'plan-error' = @('FAIL', 'drift')
    'runtime-error' = @('FAIL', 'runtime'); 'missing-telemetry' = @('FAIL', 'telemetry')
    'cleanup-error' = @('FAIL', 'vm-cleanup'); 'running-vm' = @('FAIL', 'runtime')
}
try {
    foreach ($case in $cases.Keys) {
        New-Fixture
        $f = $global:acceptanceTest
        $f.scenario = $case
        switch ($case) {
            'wrong-scope' { $f.outputs.gateway_id.value = $gateway.Replace('/resourceGroups/test/', '/resourceGroups/other/') }
            'missing-output' { $f.outputs.Remove('resource_group_name') }
            'failed-endpoint' { $f.resources[$f.outputs.private_endpoint_ids.value.gateway].properties.provisioningState = 'Failed' }
            'wrong-alias' { $f.resources["$gateway/workspaces/default/aliases/full"].properties.aliasName = 'other' }
            'running-vm' { $f.power = 'running' }
        }
        $destination = Join-Path $testDirectory $case
        $caught = $null
        $console = @()
        try {
            $console = @(& $runner -SubscriptionId $subscription -TenantId $tenant -ResourceGroup test `
                -ReportDirectory $destination -RunPrivateProbe:($case -ne 'readonly') -TelemetryWaitSeconds 0 6>&1)
        }
        catch { $caught = $_.Exception.Message }
        $file = Get-ChildItem -LiteralPath $destination -Recurse -Filter acceptance.json
        $text = Get-Content -LiteralPath $file.FullName -Raw
        $result = $text | ConvertFrom-Json -Depth 30
        if ($result.backendStatus -ne $cases[$case][0] -or $result.overallStatus -eq 'PASS' -or
            ($case -eq 'pass' -and $caught) -or ($case -ne 'pass' -and -not $caught)) {
            throw "Case $case returned $($result.backendStatus); error=$caught; checks=$($result.checks | ConvertTo-Json -Depth 5 -Compress)"
        }
        $expectedCheck = $cases[$case][1]
        $expectedStatus = if ($case -eq 'pass') { 'PASS' } elseif ($case -eq 'readonly') { 'NOT RUN' } else { 'FAIL' }
        if ($result.checks.$expectedCheck.status -ne $expectedStatus) { throw "Wrong failure boundary in $case." }
        if ($case -notin @('pass', 'runtime-error', 'missing-telemetry', 'cleanup-error') -and
            @($f.calls | Where-Object { $_ -match '^vm (start|deallocate|run-command)' }).Count) { throw "Unexpected VM mutation in $case." }
        if ($case -in @('pass', 'runtime-error', 'missing-telemetry') -and $f.power -ne 'deallocated') { throw "VM left running in $case." }
        if ($f.scriptPath -and (Test-Path -LiteralPath $f.scriptPath)) { throw 'Probe transport file was not cleaned up.' }
        if ("$text`n$($console -join "`n")`n$caught" -match 'SECRET-DO-NOT-LOG') { throw "Secret leaked in $case." }
    }
    "Customer acceptance checks passed ($($cases.Count) scenarios; no Azure or model calls)."
}
finally { Remove-Item -LiteralPath $testDirectory -Recurse -Force }
