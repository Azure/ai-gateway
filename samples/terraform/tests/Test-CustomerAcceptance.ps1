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
$monitoringGroup = "/subscriptions/$subscription/resourceGroups/managed-monitoring"
$dcr = "$monitoringGroup/providers/Microsoft.Insights/dataCollectionRules/gateway"
$dce = "$monitoringGroup/providers/Microsoft.Insights/dataCollectionEndpoints/gateway"
$amw = "$monitoringGroup/providers/Microsoft.Monitor/accounts/gateway"
$publisherRole = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb"
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
            gateway_monitoring = @{ value = @{ log_analytics_id = "$group/providers/Microsoft.OperationalInsights/workspaces/gateway" } }
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
        $f.resources[$workspaceId] = @{ properties = @{ provisioningState = 'Succeeded'; customerId = $tenant } }
    }
    $insightsId = $f.outputs.application_insights_ids.value.gateway
    $endpoints = @{
        metricsEndpoint = 'https://test.metrics.ingest.monitor.azure.com/dataCollectionRules/dcr-test/streams/Microsoft-OTLP-Metrics/otlp/v1/metrics'
        logsEndpoint = 'https://test.ingest.monitor.azure.com/dataCollectionRules/dcr-test/streams/Microsoft-OTLP-Logs/otlp/v1/logs'
        tracesEndpoint = 'https://test.ingest.monitor.azure.com/dataCollectionRules/dcr-test/streams/Microsoft-OTLP-Traces/otlp/v1/traces'
    }
    $f.resources[$insightsId].properties += @{
        AzureMonitorWorkspaceIngestionMode = 'Enabled'; DataCollectionRuleResourceId = $dcr
        OTLPMetricsEndpoint = $endpoints.metricsEndpoint; OTLPLogsEndpoint = $endpoints.logsEndpoint
        OTLPTracesEndpoint = $endpoints.tracesEndpoint
    }
    $f.resources[$monitoringGroup] = @{ managedBy = $insightsId }
    $f.resources[$dcr] = @{ properties = @{
        provisioningState = 'Succeeded'; immutableId = 'dcr-test'; dataCollectionEndpointId = $dce
        destinations = @{
            monitoringAccounts = @(@{ accountResourceId = $amw })
            logAnalytics = @(@{ workspaceResourceId = $f.resources[$insightsId].properties.WorkspaceResourceId })
        }
    } }
    $f.resources[$dce] = @{ properties = @{
        provisioningState = 'Succeeded'
        metricsIngestion = @{ endpoint = 'https://test.metrics.ingest.monitor.azure.com' }
        logsIngestion = @{ endpoint = 'https://test.ingest.monitor.azure.com' }
    } }
    $f.resources[$amw] = @{ properties = @{
        provisioningState = 'Succeeded'; metrics = @{ prometheusQueryEndpoint = 'https://test.prometheus.monitor.azure.com' }
    } }
    $f.publisherState = @{
        address = 'azapi_resource.role_assignment["gateway-monitoring-publisher"]'; mode = 'managed'
        values = @{
            id = "$dcr/providers/Microsoft.Authorization/roleAssignments/$tenant"
            parent_id = $dcr; type = 'Microsoft.Authorization/roleAssignments@2022-04-01'
            body = @{ properties = @{ principalId = 'gateway-principal'; principalType = 'ServicePrincipal'; roleDefinitionId = $publisherRole } }
        }
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
        kind = 'OpenTelemetry'; payloadCapture = $false; applicationInsights = @{ resourceId = $insightsId }
        openTelemetry = $endpoints + @{ credentials = @{ managedIdentity = @{ resource = 'https://monitor.azure.com' } } }
    } }
    foreach ($binding in @(
        @($models, 'gateway-principal', '53ca6127-db72-4b80-b1b0-d745d6d5456d'),
        @($dcr, 'gateway-principal', '3913510d-42f4-4e42-8a64-420c390055eb'),
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
            @{ mode = 'managed'; values = @{ id = $gateway; type = 'Microsoft.ApiManagement/service@2025-09-01-preview' } },
            $f.publisherState
        )
        if ($f.scenario -eq 'extra-group') { $resources += @{ mode = 'managed'; values = @{ id = "$group-old"; type = 'Microsoft.Resources/resourceGroups@2021-04-01' } } }
        if ($f.scenario -eq 'unrelated-managed-looking-resource') {
            $resources += @{ mode = 'managed'; values = @{ id = "$monitoringGroup/providers/Microsoft.Storage/storageAccounts/unrelated"; type = 'Microsoft.Storage/storageAccounts@2024-01-01' } }
        }
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
    if ($url.StartsWith('https://api.loganalytics.io/')) {
        $decoded = [uri]::UnescapeDataString($url)
        if ($decoded -notmatch 'OTelSpans' -or $decoded -notmatch 'OTelLogs' -or $decoded -notmatch 'Kind =~ "Server"' -or
            $decoded -notmatch '== 200' -or $decoded -notmatch $f.traces[0] -or $decoded -notmatch $f.traces[1]) {
            throw 'OTLP query contract/correlation missing.'
        }
        $rows = @(@('trace', $f.traces[0]), @('trace', $f.traces[1]), @('log', $f.traces[0]))
        if ($f.scenario -eq 'missing-telemetry') { $rows = @() }
        if ($f.scenario -eq 'missing-logs') { $rows = @(@('trace', $f.traces[0]), @('trace', $f.traces[1])) }
        if ($f.scenario -eq 'uncorrelated-telemetry') { $rows = @(@('trace', ('d' * 32)), @('log', ('d' * 32))) }
        $columns = @(@{ name = 'Signal' }, @{ name = 'TraceId' })
        if ($f.scenario -eq 'telemetry-schema') { $columns = @(@{ name = 'operation_Id' }) }
        return (@{ tables = @(@{ columns = $columns; rows = $rows }) } | ConvertTo-Json -Depth 10)
    }
    if ($url.StartsWith('https://test.prometheus.monitor.azure.com/')) {
        $decoded = [uri]::UnescapeDataString($url)
        if ($decoded -notmatch 'azure.ai_gateway.client.token.usage' -or $decoded -notmatch 'microsoft.appresourceid' -or
            $decoded -notmatch '"azure.ai_gateway.workspace"="default"' -or 'https://prometheus.monitor.azure.com' -notin $args) {
            throw 'Prometheus scope/authentication missing.'
        }
        if ($f.scenario -eq 'metrics-error') { return '{"status":"error","error":"SECRET-DO-NOT-LOG"}' }
        $items = @(@{ metric = @{
            __name__ = 'azure.ai_gateway.client.token.usage'
            'microsoft.appresourceid' = $f.outputs.application_insights_ids.value.gateway.ToLowerInvariant()
            'azure.ai_gateway.workspace' = 'default'
        }; values = @(,@([DateTimeOffset]::UtcNow.ToUnixTimeSeconds(), '5')) })
        if ($f.scenario -eq 'missing-metrics') { $items = @() }
        if ($f.scenario -eq 'wrong-metric-scope') { $items[0].metric.'azure.ai_gateway.workspace' = 'other' }
        if ($f.scenario -eq 'stale-metrics') { $items[0].values[0][0] = [DateTimeOffset]::UtcNow.AddDays(-1).ToUnixTimeSeconds() }
        if ($f.scenario -eq 'nonfinite-metrics') { $items[0].values[0][1] = 'NaN' }
        return (@{ status = 'success'; data = @{ resultType = 'matrix'; result = $items } } | ConvertTo-Json -Depth 10)
    }
    $id = ([uri]$url).AbsolutePath
    if ($f.scenario -eq 'arm-error') { $global:LASTEXITCODE = 1; return 'SECRET-DO-NOT-LOG' }
    if (-not $f.resources.ContainsKey($id)) { throw "Unexpected fixture resource: $id" }
    $f.resources[$id] | ConvertTo-Json -Depth 20
}

$cases = [ordered]@{
    pass = @('PASS', 'runtime'); readonly = @('BLOCKED', 'runtime')
    'omitted-api-format' = @('PASS', 'runtime'); 'lowercase-exporter-kind' = @('PASS', 'runtime')
    'arm-dcr-fallback' = @('PASS', 'runtime')
    'missing-exporter-kind' = @('FAIL', 'monitoring'); 'null-exporter-kind' = @('FAIL', 'monitoring')
    'wrong-tenant' = @('FAIL', 'context'); 'wrong-scope' = @('FAIL', 'context')
    'missing-output' = @('FAIL', 'context'); malformed = @('FAIL', 'context')
    'terraform-error' = @('FAIL', 'context'); dirty = @('FAIL', 'context')
    'extra-group' = @('FAIL', 'placement'); 'arm-error' = @('FAIL', 'resources')
    'failed-endpoint' = @('FAIL', 'private-network'); 'wrong-alias' = @('FAIL', 'resources')
    'manual-approved' = @('PASS', 'runtime'); 'manual-pending' = @('FAIL', 'private-network')
    'manual-wrong-target' = @('FAIL', 'private-network'); 'mixed-connections' = @('FAIL', 'private-network')
    'wrong-api-format' = @('FAIL', 'resources'); 'wrong-exporter-kind' = @('FAIL', 'monitoring')
    drift = @('FAIL', 'drift'); 'plan-error' = @('FAIL', 'drift')
    'runtime-error' = @('FAIL', 'runtime'); 'missing-telemetry' = @('FAIL', 'telemetry')
    'cleanup-error' = @('FAIL', 'vm-cleanup'); 'running-vm' = @('FAIL', 'runtime')
    'missing-otlp-endpoint' = @('FAIL', 'monitoring'); 'wrong-otlp-endpoint' = @('FAIL', 'monitoring')
    'wrong-audience' = @('FAIL', 'monitoring'); 'legacy-exporter-kind' = @('FAIL', 'monitoring')
    'wrong-publisher-role' = @('FAIL', 'monitoring'); 'wrong-publisher-principal' = @('FAIL', 'monitoring')
    'wrong-publisher-state' = @('FAIL', 'placement'); 'unmanaged-helper-group' = @('FAIL', 'placement')
    'unrelated-managed-looking-resource' = @('FAIL', 'placement')
    'wrong-law' = @('FAIL', 'monitoring'); 'immutable-dcr-only' = @('FAIL', 'monitoring')
    'cross-subscription-dcr' = @('FAIL', 'monitoring')
    'missing-logs' = @('FAIL', 'telemetry'); 'missing-metrics' = @('FAIL', 'telemetry')
    'metrics-error' = @('FAIL', 'telemetry'); 'telemetry-schema' = @('FAIL', 'telemetry')
    'uncorrelated-telemetry' = @('FAIL', 'telemetry')
    'wrong-metric-scope' = @('FAIL', 'telemetry'); 'stale-metrics' = @('FAIL', 'telemetry')
    'nonfinite-metrics' = @('FAIL', 'telemetry'); 'relinked-law' = @('FAIL', 'monitoring')
    'wrong-dce-endpoint' = @('FAIL', 'monitoring'); 'unsafe-query-endpoint' = @('FAIL', 'monitoring')
}
$runtimeCases = @('pass', 'manual-approved', 'omitted-api-format', 'lowercase-exporter-kind', 'arm-dcr-fallback', 'runtime-error',
    'missing-telemetry', 'missing-logs', 'missing-metrics', 'metrics-error', 'telemetry-schema', 'uncorrelated-telemetry',
    'wrong-metric-scope', 'stale-metrics', 'nonfinite-metrics', 'cleanup-error')
try {
    foreach ($case in $cases.Keys) {
        New-Fixture
        $f = $global:acceptanceTest
        $f.scenario = $case
        if ($case -in @('manual-approved', 'manual-pending', 'manual-wrong-target', 'mixed-connections')) {
            $properties = $f.resources[$f.outputs.private_endpoint_ids.value.gateway].properties
            $properties.manualPrivateLinkServiceConnections = $properties.privateLinkServiceConnections
            if ($case -ne 'mixed-connections') { $properties.privateLinkServiceConnections = @() }
            if ($case -eq 'manual-pending') {
                $properties.manualPrivateLinkServiceConnections[0].properties.privateLinkServiceConnectionState.status = 'Pending'
            }
            if ($case -eq 'manual-wrong-target') {
                $properties.manualPrivateLinkServiceConnections[0].properties.privateLinkServiceId = $models
            }
        }
        switch ($case) {
            'wrong-scope' { $f.outputs.gateway_id.value = $gateway.Replace('/resourceGroups/test/', '/resourceGroups/other/') }
            'missing-output' { $f.outputs.Remove('resource_group_name') }
            'failed-endpoint' { $f.resources[$f.outputs.private_endpoint_ids.value.gateway].properties.provisioningState = 'Failed' }
            'wrong-alias' { $f.resources["$gateway/workspaces/default/aliases/full"].properties.aliasName = 'other' }
            'wrong-api-format' { $f.resources["$gateway/workspaces/default/modelProviders/foundry/models/full"].properties.apiFormat = 'Other' }
            'wrong-exporter-kind' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.kind = 'Other' }
            'lowercase-exporter-kind' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.kind = 'openTelemetry' }
            'legacy-exporter-kind' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.kind = 'applicationInsights' }
            'missing-otlp-endpoint' { $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.Remove('OTLPTracesEndpoint') }
            'wrong-otlp-endpoint' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.openTelemetry.logsEndpoint = 'https://other.ingest.monitor.azure.com/logs' }
            'wrong-audience' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.openTelemetry.credentials.managedIdentity.resource = 'https://wrong.example' }
            'wrong-publisher-role' { $f.resources["$dcr/providers/Microsoft.Authorization/roleAssignments"].value[0].properties.roleDefinitionId = 'wrong' }
            'wrong-publisher-principal' { $f.resources["$dcr/providers/Microsoft.Authorization/roleAssignments"].value[0].properties.principalId = 'wrong' }
            'wrong-publisher-state' { $f.publisherState.values.body.properties.principalId = 'wrong' }
            'unmanaged-helper-group' { $f.resources[$monitoringGroup].managedBy = "$group/providers/Microsoft.Monitor/accounts/unrelated" }
            'wrong-law' { $f.resources[$dcr].properties.destinations.logAnalytics[0].workspaceResourceId = "$group/providers/Microsoft.OperationalInsights/workspaces/agents" }
            'immutable-dcr-only' {
                $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.Remove('DataCollectionRuleResourceId')
                $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.DataCollectionRuleId = 'dcr-test'
            }
            'arm-dcr-fallback' {
                $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.Remove('DataCollectionRuleResourceId')
                $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.DataCollectionRuleId = $dcr
            }
            'cross-subscription-dcr' { $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.DataCollectionRuleResourceId = $dcr.Replace($subscription, $tenant) }
            'relinked-law' {
                $f.resources[$f.outputs.application_insights_ids.value.gateway].properties.WorkspaceResourceId = "$group/providers/Microsoft.OperationalInsights/workspaces/agents"
                $f.resources[$dcr].properties.destinations.logAnalytics[0].workspaceResourceId = "$group/providers/Microsoft.OperationalInsights/workspaces/agents"
            }
            'wrong-dce-endpoint' { $f.resources[$dce].properties.metricsIngestion.endpoint = 'https://other.metrics.ingest.monitor.azure.com' }
            'unsafe-query-endpoint' { $f.resources[$amw].properties.metrics.prometheusQueryEndpoint = 'https://unrelated.example' }
            'missing-exporter-kind' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.Remove('kind') }
            'null-exporter-kind' { $f.resources["$gateway/workspaces/default/telemetryExporters/appinsights"].properties.kind = $null }
            'omitted-api-format' {
                foreach ($name in @('full', 'mini')) { $f.resources["$gateway/workspaces/default/modelProviders/foundry/models/$name"].properties.Remove('apiFormat') }
            }
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
            ($cases[$case][0] -eq 'PASS' -and $caught) -or ($cases[$case][0] -ne 'PASS' -and -not $caught)) {
            throw "Case $case returned $($result.backendStatus); error=$caught; checks=$($result.checks | ConvertTo-Json -Depth 5 -Compress)"
        }
        $expectedCheck = $cases[$case][1]
        $expectedStatus = if ($cases[$case][0] -eq 'PASS') { 'PASS' } elseif ($case -eq 'readonly') { 'NOT RUN' } else { 'FAIL' }
        if ($result.checks.$expectedCheck.status -ne $expectedStatus) { throw "Wrong failure boundary in $case." }
        if ($case -in @('missing-exporter-kind', 'null-exporter-kind') -and
            $result.checks.monitoring.detail -notmatch 'portal cannot recognize') { throw "Missing portal diagnostic in $case." }
        if ($case -notin $runtimeCases -and
            @($f.calls | Where-Object { $_ -match '^vm (start|deallocate|run-command)' }).Count) { throw "Unexpected VM mutation in $case." }
        if ($case -in $runtimeCases -and $case -ne 'cleanup-error' -and $f.power -ne 'deallocated') { throw "VM left running in $case." }
        if ($f.scriptPath -and (Test-Path -LiteralPath $f.scriptPath)) { throw 'Probe transport file was not cleaned up.' }
        if ("$text`n$($console -join "`n")`n$caught" -match 'SECRET-DO-NOT-LOG') { throw "Secret leaked in $case." }
    }
    "Customer acceptance checks passed ($($cases.Count) scenarios; no Azure or model calls)."
}
finally { Remove-Item -LiteralPath $testDirectory -Recurse -Force }
