#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid]$SubscriptionId,
    [Parameter(Mandatory)][guid]$TenantId,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9_.()-]+$')][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$ReportDirectory,
    [string[]]$AdditionalVarFile = @(),
    [switch]$RunPrivateProbe,
    [ValidateRange(0, 900)][int]$TelemetryWaitSeconds = 300
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$subscription = $SubscriptionId.ToString()
$tenant = $TenantId.ToString()
$groupId = "/subscriptions/$subscription/resourceGroups/$ResourceGroup"
$runId = [guid]::NewGuid().ToString('N')
$directory = Join-Path ([IO.Path]::GetFullPath($ReportDirectory)) $runId
$null = New-Item -ItemType Directory -Path $directory
$context = @{}
$checks = [ordered]@{}
$report = [ordered]@{
    schemaVersion = 1
    runId = $runId
    startedUtc = [DateTimeOffset]::UtcNow.ToString('o')
    subscriptionId = $subscription
    tenantId = $tenant
    resourceGroup = $ResourceGroup
    scope = 'Existing legacy gateway; private route, not private-only ingress or hosted-agent runtime'
    profile = 'profiles/private-connectivity.tfvars.json'
    commit = $null
    backendStatus = 'BLOCKED'
    overallStatus = 'BLOCKED'
    checks = $checks
    portal = @{ status = 'NOT RUN'; evidence = 'portal-evidence.json'; verification = 'operator-attested' }
}

function Stop-Check([string]$Message) { throw "ACCEPTANCE: $Message" }

function Read-Json([string]$Text) {
    try { $Text | ConvertFrom-Json -Depth 100 }
    catch { Stop-Check 'Invalid JSON response; raw content omitted.' }
}

function Invoke-AzureJson([string[]]$Arguments) {
    $text = & az @Arguments --subscription $subscription --only-show-errors --output json 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Check "Azure CLI failed (exit $LASTEXITCODE); response omitted." }
    Read-Json ($text -join "`n")
}

function Assert-GroupId([string]$Id) {
    if (-not $Id.StartsWith("$groupId/", [StringComparison]::OrdinalIgnoreCase) -or $Id -match '[?#]') {
        Stop-Check 'Unexpected resource scope in deployment outputs/state.'
    }
}

function Read-Arm([string]$Id, [string]$Version) {
    Assert-GroupId $Id
    Invoke-AzureJson @('rest', '--method', 'get', '--url', "https://management.azure.com${Id}?api-version=$Version")
}

function Read-ArmItems([string]$Id, [string]$Version, [switch]$LinkedDcr) {
    if ($LinkedDcr) {
        if (-not $context.monitoring -or $Id -ine "$($context.monitoring.dataCollectionRuleId)/providers/Microsoft.Authorization/roleAssignments") {
            Stop-Check 'Only the verified linked DCR role assignments may be read outside the application group.'
        }
    }
    else { Assert-GroupId $Id }
    $url = "https://management.azure.com${Id}?api-version=$Version"
    $seen = [Collections.Generic.HashSet[string]]::new()
    while ($url) {
        if (-not $url.StartsWith("https://management.azure.com${Id}?", [StringComparison]::OrdinalIgnoreCase) -or
            -not $seen.Add($url)) { Stop-Check 'Unexpected or repeated ARM pagination URL.' }
        $page = Invoke-AzureJson @('rest', '--method', 'get', '--url', $url)
        $page.value
        $url = $page.nextLink
    }
}

function Get-MonitoringTopology {
    if (-not $context.monitoring) {
        $context.monitoring = & (Join-Path $PSScriptRoot 'Get-GatewayMonitoring.ps1') `
            -SubscriptionId $SubscriptionId -ApplicationInsightsId $context.outputs.application_insights_ids.value.gateway `
            -ExpectedLogAnalyticsId $context.outputs.gateway_monitoring.value.log_analytics_id
    }
    $context.monitoring
}

function Assert-RoleBinding([string]$Name, [string]$Principal, [string]$Scope, [string]$Role, [switch]$LinkedDcr) {
    $roleId = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/$Role"
    $assignments = @(Read-ArmItems "$Scope/providers/Microsoft.Authorization/roleAssignments" '2022-04-01' -LinkedDcr:$LinkedDcr)
    $match = @($assignments | Where-Object {
        $_.properties.scope -ieq $Scope -and $_.properties.principalId -eq $Principal -and
        $_.properties.principalType -eq 'ServicePrincipal' -and
        $_.properties.roleDefinitionId -ieq $roleId -and -not $_.properties.condition
    })
    if ($match.Count -ne 1) { Stop-Check "Incorrect exact role binding: $Name" }
}

function Assert-Ready($Resource) {
    if ($Resource.properties.provisioningState -ne 'Succeeded') {
        Stop-Check "Resource not ready: $($Resource.id)"
    }
}

function Get-StateResources($Module) {
    $Module.resources
    foreach ($child in $Module.child_modules) { Get-StateResources $child }
}

function Invoke-Check([string]$Name, [string[]]$Needs, [scriptblock]$Action) {
    $checks[$Name] = @{ status = 'NOT RUN'; detail = ''; evidence = $null }
    $missing = @($Needs | Where-Object { $checks[$_].status -ne 'PASS' })
    if ($missing.Count) {
        $checks[$Name].status = 'BLOCKED'
        $checks[$Name].detail = "Prerequisites: $($missing -join ', ')"
    }
    else {
        try {
            $checks[$Name].evidence = & $Action
            $checks[$Name].status = 'PASS'
        }
        catch {
            $checks[$Name].status = 'FAIL'
            $message = $_.Exception.Message
            $checks[$Name].detail = if ($message -match '^(?:ACCEPTANCE|MONITORING): (.*)$') {
                $Matches[1]
            } else { 'Unexpected check error; raw error omitted to protect credentials.' }
        }
    }
    Write-Host "$Name`: $($checks[$Name].status) $($checks[$Name].detail)"
}

Invoke-Check 'context' @() {
    $account = Invoke-AzureJson @('account', 'show')
    if ($account.id -ne $subscription -or $account.tenantId -ne $tenant) { Stop-Check 'Subscription/tenant mismatch.' }
    $json = & terraform "-chdir=$root" output -json 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Check 'Cannot read Terraform outputs.' }
    $context.outputs = Read-Json ($json -join "`n")
    $o = $context.outputs
    if ($o.resource_group_name.value -ne $ResourceGroup -or
        @($o.resource_groups.value.PSObject.Properties).Count -ne 3 -or
        @(Compare-Object @('agents', 'gateway', 'models') @($o.resource_groups.value.PSObject.Properties.Name)).Count -or
        @($o.resource_groups.value.PSObject.Properties | Where-Object { $_.Value -ne $ResourceGroup }).Count) {
        Stop-Check 'Outputs do not identify the expected single resource group.'
    }
    $context.gatewayId = [string]$o.gateway_id.value
    $context.modelsId = [string]$o.foundry_models_id.value
    $context.projectId = [string]$o.project_id.value
    $context.agentsId = $context.projectId -replace '/projects/[^/]+$', ''
    $context.storageId = "$groupId/providers/Microsoft.Storage/storageAccounts/$($o.storage_account_name.value)"
    $context.registryId = "$groupId/providers/Microsoft.ContainerRegistry/registries/$(([string]$o.container_registry_endpoint.value).Split('.')[0])"
    foreach ($id in @($context.gatewayId, $context.modelsId, $context.projectId, $context.agentsId,
        $context.storageId, $context.registryId, $o.private_test_vm_id.value,
        $o.application_insights_ids.value.gateway, $o.application_insights_ids.value.agents,
        $o.gateway_monitoring.value.log_analytics_id)) {
        Assert-GroupId ([string]$id)
    }
    $commit = & git -C $root rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Check 'Cannot identify source commit.' }
    $dirty = & git -C $root status --porcelain --untracked-files=normal 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Check 'Cannot inspect source checkout.' }
    if ($dirty) { Stop-Check 'Customer acceptance requires a clean tracked checkout; commit reviewed changes first.' }
    $report.commit = [string]$commit
    @{ gatewayId = $context.gatewayId; projectId = $context.projectId }
}

Invoke-Check 'placement' @('context') {
    $json = & terraform "-chdir=$root" show -json 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Check 'Cannot inspect managed resource placement.' }
    $state = Read-Json ($json -join "`n")
    $resources = @(Get-StateResources $state.values.root_module | Where-Object { $_.mode -eq 'managed' })
    if (-not $resources.Count) { Stop-Check 'No managed resources found.' }
    $groups = @($resources | Where-Object { $_.values.type -like 'Microsoft.Resources/resourceGroups@*' })
    if ($groups.Count -ne 1 -or $groups[0].values.id -ine $groupId) {
        Stop-Check 'State must manage exactly one application resource group; migration retention must be finished.'
    }
    foreach ($resource in $resources) {
        if ($resource -in $groups) { continue }
        if ($resource.values.type -like 'Microsoft.Authorization/roleDefinitions@*') {
            $scopes = @($resource.values.body.properties.assignableScopes)
            if ($scopes.Count -ne 1 -or $scopes[0] -ine $groupId) { Stop-Check 'Unexpected custom-role assignable scope.' }
        }
        elseif ($resource.address -eq 'azapi_resource.role_assignment["gateway-monitoring-publisher"]') {
            $topology = Get-MonitoringTopology
            $gateway = Read-Arm $context.gatewayId '2025-09-01-preview'
            $properties = $resource.values.body.properties
            $rolePrefix = "$($topology.dataCollectionRuleId)/providers/Microsoft.Authorization/roleAssignments/"
            if ($resource.values.parent_id -ine $topology.dataCollectionRuleId -or
                -not ([string]$resource.values.id).StartsWith($rolePrefix, [StringComparison]::OrdinalIgnoreCase) -or
                ([string]$resource.values.id).Substring($rolePrefix.Length) -notmatch '^[a-fA-F0-9-]{36}$' -or
                -not $gateway.identity.principalId -or $gateway.identity.tenantId -ne $tenant -or
                $properties.principalId -ne $gateway.identity.principalId -or
                $properties.principalType -ne 'ServicePrincipal' -or $properties.condition -or
                $properties.roleDefinitionId -ine "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb") {
                Stop-Check 'External publishing assignment is not the exact Insights-linked DCR/gateway identity/role.'
            }
        }
        else { Assert-GroupId ([string]$resource.values.id) }
    }
    @{ managedResources = $resources.Count; applicationGroups = 1 }
}

Invoke-Check 'resources' @('context') {
    $context.gateway = Read-Arm $context.gatewayId '2025-09-01-preview'
    $context.models = Read-Arm $context.modelsId '2025-04-01-preview'
    $context.agents = Read-Arm $context.agentsId '2025-04-01-preview'
    $context.project = Read-Arm $context.projectId '2025-04-01-preview'
    $context.storage = Read-Arm $context.storageId '2024-01-01'
    $context.registry = Read-Arm $context.registryId '2023-07-01'
    foreach ($key in @('gateway', 'models', 'agents', 'project', 'storage', 'registry')) { Assert-Ready $context[$key] }
    if ($context.gateway.sku.name -ne 'AIGateway') { Stop-Check 'Unexpected gateway SKU.' }
    foreach ($resource in @($context.gateway, $context.project)) {
        if (-not $resource.identity.principalId -or $resource.identity.tenantId -ne $tenant) {
            Stop-Check 'Missing or wrong-tenant runtime identity.'
        }
    }
    $deployments = @($context.outputs.model_deployment_ids.value.PSObject.Properties)
    if (-not $deployments.Count) { Stop-Check 'No model deployments configured.' }
    foreach ($deployment in $deployments) {
        Assert-Ready (Read-Arm $deployment.Value '2025-04-01-preview')
        $metadata = $context.outputs.model_api_configuration.value.($deployment.Name)
        if ($metadata.api_format -ne 'OpenAIChatCompletions' -or '/openai/v1/chat/completions' -notin $metadata.endpoints) {
            Stop-Check 'Every alias must have compatible chat-completions metadata before runtime testing.'
        }
        $catalogId = "$($context.gatewayId)/workspaces/default/modelProviders/foundry/models/$($deployment.Name)"
        $catalog = Read-Arm $catalogId '2025-09-01-preview'
        $alias = Read-Arm "$($context.gatewayId)/workspaces/default/aliases/$($deployment.Name)" '2025-09-01-preview'
        if ($catalog.properties.deployment.resourceId -ine $deployment.Value -or
            ('apiFormat' -in $catalog.properties.PSObject.Properties.Name -and $catalog.properties.apiFormat -ne $metadata.api_format) -or
            '/openai/v1/chat/completions' -notin $catalog.properties.supportedEndpoints -or
            $alias.properties.aliasName -ne $deployment.Name -or
            @($alias.properties.backendModels).Count -ne 1 -or
            $alias.properties.backendModels[0].resourceId -ine $catalogId) { Stop-Check 'Catalog model or alias route mismatch.' }
    }
    @{
        modelAliases = @($deployments.Name); gatewaySku = 'AIGateway'
        apiFormatVerification = 'Output contract and live supported endpoints; apiFormat checked when returned (preview GET can omit it).'
    }
}

Invoke-Check 'roles' @('resources') {
    $bindings = @(
        @('gateway-foundry-user', $context.gateway.identity.principalId, $context.modelsId, '53ca6127-db72-4b80-b1b0-d745d6d5456d'),
        @('project-storage', $context.project.identity.principalId, $context.storageId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'),
        @('project-acr-pull', $context.project.identity.principalId, $context.registryId, '7f951dda-4ed3-4680-a7ca-43fe172d538d'),
        @('project-contributor', $context.project.identity.principalId, $context.agentsId, '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'),
        @('project-openai-user', $context.project.identity.principalId, $context.agentsId, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'),
        @('project-user', $context.project.identity.principalId, $context.agentsId, 'a97b65f3-24c7-4388-baec-2e87135dc908')
    )
    foreach ($binding in $bindings) {
        Assert-RoleBinding $binding[0] $binding[1] $binding[2] $binding[3]
    }
    @{ verifiedBindings = 6; additionalDeveloperRoles = 'Not certified by this check' }
}

Invoke-Check 'connections' @('resources') {
    $projectConnections = @(Read-ArmItems "$($context.projectId)/connections" '2025-04-01-preview')
    $accountConnections = @(Read-ArmItems "$($context.agentsId)/connections" '2025-06-01')
    $insightsId = $context.outputs.application_insights_ids.value.agents
    $expected = @(
        @{ name = $context.storage.name; items = $projectConnections; category = 'AzureStorageAccount'; auth = 'AAD'; target = $context.storage.properties.primaryEndpoints.blob; resource = $context.storageId },
        @{ name = "$($context.registry.name)-conn"; items = $projectConnections; category = 'ContainerRegistry'; auth = 'ManagedIdentity'; target = $context.registry.properties.loginServer; resource = $context.registryId },
        @{ name = $insightsId.Split('/')[-1]; items = $accountConnections; category = 'AppInsights'; auth = 'ApiKey'; target = $insightsId; resource = $insightsId }
    )
    foreach ($connection in $expected) {
        $match = @($connection.items | Where-Object {
            $_.name -eq $connection.name -and $_.properties.category -eq $connection.category -and
            $_.properties.authType -eq $connection.auth -and $_.properties.target -eq $connection.target -and
            $_.properties.metadata.ResourceId -ieq $connection.resource
        })
        if ($match.Count -ne 1) { Stop-Check "Connection metadata mismatch: $($connection.name)" }
    }
    $provider = Read-Arm "$($context.gatewayId)/workspaces/default/modelProviders/foundry" '2025-09-01-preview'
    $foundry = $provider.properties.foundry
    if ($foundry.authentication.kind -ne 'ManagedIdentity' -or
        $foundry.authentication.managedIdentity.resource -ne 'https://cognitiveservices.azure.com/' -or
        @($foundry.resourceIds).Count -ne 1 -or $foundry.resourceIds[0] -ine $context.modelsId -or
        ([string]$foundry.endpoint).TrimEnd('/') -ne ([string]$context.models.properties.endpoint).TrimEnd('/')) {
        Stop-Check 'Gateway model-provider configuration mismatch.'
    }
    @{ verifiedConnections = 3; backendAuthentication = 'ManagedIdentity' }
}

Invoke-Check 'monitoring' @('resources') {
    foreach ($name in @('gateway', 'agents')) {
        $insights = Read-Arm $context.outputs.application_insights_ids.value.$name '2020-02-02'
        Assert-Ready $insights
        Assert-Ready (Read-Arm $insights.properties.WorkspaceResourceId '2023-09-01')
    }
    $topology = Get-MonitoringTopology
    $exporter = Read-Arm "$($context.gatewayId)/workspaces/default/telemetryExporters/appinsights" '2025-09-01-preview'
    if ([string]::IsNullOrWhiteSpace([string]$exporter.properties.kind)) {
        Stop-Check 'Telemetry exporter kind is missing; the portal cannot recognize the OpenTelemetry configuration.'
    }
    if ($exporter.properties.kind -ne 'OpenTelemetry' -or
        $exporter.properties.payloadCapture -ne $false -or
        $exporter.properties.applicationInsights.resourceId -ine $topology.insightsId -or
        $exporter.properties.applicationInsights.connectionString -or
        $exporter.properties.openTelemetry.credentials.managedIdentity.resource -cne 'https://monitor.azure.com' -or
        $exporter.properties.openTelemetry.credentials.managedIdentity.clientId -or
        $exporter.properties.openTelemetry.credentials.headers) {
        Stop-Check 'Telemetry exporter kind, target or payload-capture mismatch.'
    }
    foreach ($name in @('metricsEndpoint', 'logsEndpoint', 'tracesEndpoint')) {
        if ($exporter.properties.openTelemetry.$name -cne $topology.endpoints[$name]) {
            Stop-Check "Exporter $name differs from the actual Insights OTLP endpoint."
        }
    }
    Assert-RoleBinding 'gateway-monitoring-publisher' $context.gateway.identity.principalId `
        $topology.dataCollectionRuleId '3913510d-42f4-4e42-8a64-420c390055eb' -LinkedDcr
    @{
        readyMonitoringStacks = 2; delivery = 'Requires telemetry check'
        verifiedPublisherBindings = 1; destination = $topology
        exporterVerification = 'OpenTelemetry, all endpoints, system identity audience, linked destination and exact DCR role checked; delivery/UI are separate gates.'
    }
}

Invoke-Check 'private-network' @('resources') {
    if ($context.models.properties.publicNetworkAccess -ne 'Disabled' -or
        $context.models.properties.networkAcls.defaultAction -ne 'Deny' -or
        $context.gateway.properties.publicNetworkAccess -ne 'Enabled' -or
        $context.gateway.properties.virtualNetworkType -ne 'External') { Stop-Check 'Private profile posture mismatch.' }
    $subnetId = [string]$context.gateway.properties.virtualNetworkConfiguration.subnetResourceId
    Assert-GroupId $subnetId
    $endpointSubnetId = ($subnetId -replace '/subnets/[^/]+$', '/subnets/endpoints')
    $endpointSubnet = Read-Arm $endpointSubnetId '2024-05-01'
    if (-not $context.outputs.private_probe_configuration.value.private_endpoint_subnet -or
        $endpointSubnet.properties.addressPrefix -ne $context.outputs.private_probe_configuration.value.private_endpoint_subnet) {
        Stop-Check 'Probe subnet does not match the deployed endpoint subnet.'
    }
    foreach ($name in @('gateway', 'models')) {
        $endpointId = $context.outputs.private_endpoint_ids.value.$name
        $endpoint = Read-Arm $endpointId '2024-05-01'
        Assert-Ready $endpoint
        $connections = @(
            @($endpoint.properties.privateLinkServiceConnections) +
            @($endpoint.properties.manualPrivateLinkServiceConnections) |
                Where-Object { $null -ne $_ }
        )
        $target = if ($name -eq 'gateway') { $context.gatewayId } else { $context.modelsId }
        $group = if ($name -eq 'gateway') { 'Gateway' } else { 'account' }
        if ($connections.Count -ne 1 -or
            $connections[0].properties.privateLinkServiceConnectionState.status -ne 'Approved' -or
            $connections[0].properties.privateLinkServiceId -ine $target -or
            @($connections[0].properties.groupIds).Count -ne 1 -or $connections[0].properties.groupIds[0] -ne $group -or
            $endpoint.properties.subnet.id -ine $endpointSubnetId) { Stop-Check "Private endpoint mismatch: $name" }
        $zoneGroup = Read-Arm "$endpointId/privateDnsZoneGroups/default" '2024-05-01'
        Assert-Ready $zoneGroup
        $zones = @($zoneGroup.properties.privateDnsZoneConfigs)
        $expectedZones = if ($name -eq 'gateway') { @('privatelink.azure-api.net') } else {
            @('privatelink.cognitiveservices.azure.com', 'privatelink.openai.azure.com', 'privatelink.services.ai.azure.com')
        }
        $actualIds = @($zones | ForEach-Object { $_.properties.privateDnsZoneId })
        if ($actualIds.Count -ne $expectedZones.Count) { Stop-Check "DNS zone count mismatch: $name" }
        foreach ($zone in $expectedZones) {
            $zoneId = "$groupId/providers/Microsoft.Network/privateDnsZones/$zone"
            if ($zoneId -notin $actualIds) { Stop-Check "Missing private DNS zone: $zone" }
            $link = Read-Arm "$zoneId/virtualNetworkLinks/gateway-vnet" '2020-06-01'
            Assert-Ready $link
            if ($link.properties.virtualNetwork.id -ine ($subnetId -replace '/subnets/[^/]+$', '')) {
                Stop-Check 'Private DNS link targets the wrong VNet.'
            }
        }
    }
    @{ gatewayPublicAccess = 'Enabled'; modelsPublicAccess = 'Disabled'; privateOnlyIngress = 'NOT certified' }
}

Invoke-Check 'drift' @('context') {
    if ($env:TF_CLI_ARGS -or $env:TF_CLI_ARGS_plan) { Stop-Check 'Remove hidden TF_CLI_ARGS/TF_CLI_ARGS_plan before checking drift.' }
    $arguments = @("-chdir=$root", 'plan', '-input=false', '-no-color', '-lock-timeout=15s', '-detailed-exitcode')
    foreach ($file in $AdditionalVarFile) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { Stop-Check 'Additional var-file does not exist; use an absolute path.' }
        $arguments += "-var-file=$([IO.Path]::GetFullPath($file))"
    }
    $arguments += '-var-file=profiles/private-connectivity.tfvars.json'
    $previous = $env:ARM_SKIP_PROVIDER_REGISTRATION
    try {
        $env:ARM_SKIP_PROVIDER_REGISTRATION = 'true'
        $raw = & terraform @arguments 2>&1
        $code = $LASTEXITCODE
        $raw = $null
    }
    finally { $env:ARM_SKIP_PROVIDER_REGISTRATION = $previous }
    if ($code -ne 0) { Stop-Check "Terraform drift check exit $code (2 = pending changes, 1 = error); raw plan omitted." }
    @{ terraformExitCode = 0 }
}

$runtimeNeeds = @('context', 'placement', 'resources', 'roles', 'connections', 'monitoring', 'private-network', 'drift')
if ($RunPrivateProbe) {
    Invoke-Check 'runtime' $runtimeNeeds {
        $vmId = $context.outputs.private_test_vm_id.value
        $view = Invoke-AzureJson @('vm', 'get-instance-view', '--ids', $vmId)
        if ('PowerState/deallocated' -notin @($view.instanceView.statuses.code)) {
            Stop-Check 'Test VM must be deallocated before this runner takes ownership of its power lifecycle.'
        }
        $context.testStartUtc = [DateTimeOffset]::UtcNow
        try {
            $null = Invoke-AzureJson @('vm', 'start', '--ids', $vmId)
            $probe = & (Join-Path $PSScriptRoot 'Test-PrivateGateway.ps1') -RunId $runId | ConvertFrom-Json
            if (-not $probe.passed -or $probe.run_id -ne $runId) { Stop-Check 'Private probe did not return this run ID and a pass.' }
            $aliases = @($context.outputs.model_deployment_ids.value.PSObject.Properties.Name)
            $tested = @($probe.inference | ForEach-Object { $_.model })
            if (@(Compare-Object $aliases $tested).Count -or @($probe.inference).Count -ne $aliases.Count -or
                @($probe.inference | Where-Object { $_.status -ne 200 -or $_.reply -ne 'OK' -or $_.trace_id -notmatch '^[a-f0-9]{32}$' }).Count) {
                Stop-Check 'Private probe alias results are incomplete.'
            }
            if (@($probe.authentication).Count -ne 2 -or
                @($probe.authentication | Where-Object { $_.status -notin @(401, 403) }).Count -or
                @(Compare-Object @('missing-key', 'invalid-key') @($probe.authentication.case)).Count) { Stop-Check 'Negative authentication evidence is incomplete.' }
            $context.probe = $probe
            $probe
        }
        finally {
            $context.testEndUtc = [DateTimeOffset]::UtcNow
            Invoke-Check 'vm-cleanup' @() {
                $null = Invoke-AzureJson @('vm', 'deallocate', '--ids', $vmId)
                $view = Invoke-AzureJson @('vm', 'get-instance-view', '--ids', $vmId)
                if ('PowerState/deallocated' -notin @($view.instanceView.statuses.code)) {
                    Stop-Check 'VM deallocation not confirmed; operator intervention required.'
                }
                @{ powerState = 'PowerState/deallocated' }
            }
            if ($checks['vm-cleanup'].status -ne 'PASS') { Stop-Check 'Test VM cleanup failed; deallocate it manually now.' }
        }
    }
}
else {
    $checks.runtime = @{ status = 'NOT RUN'; detail = 'Requires explicit -RunPrivateProbe (billable calls and VM start/deallocation).'; evidence = $null }
}

Invoke-Check 'telemetry' @('runtime', 'monitoring') {
    $traces = @($context.probe.inference.trace_id | Sort-Object -Unique)
    if ($traces.Count -ne @($context.probe.inference).Count) { Stop-Check 'Trace IDs must be unique per model call.' }
    $traceFilter = ($traces | ForEach-Object { "'$_'" }) -join ','
    $start = $context.testStartUtc.AddMinutes(-1).UtcDateTime.ToString('o')
    $end = $context.testEndUtc.AddMinutes(1).UtcDateTime.ToString('o')
    $filter = "TimeGenerated between (datetime($start) .. datetime($end)) and TraceId in ($traceFilter)"
    $query = @"
union
(OTelSpans | where $filter | where Kind =~ "Server"
| extend Route=tostring(Attributes["http.route"])
| extend Workspace=coalesce(tostring(Attributes["azure.ai_gateway.workspace"]), extract(@"/([^/]+)/models/", 1, Route))
| where Workspace == "default" and Route contains "/models/"
| where coalesce(toint(Attributes["http.response.status_code"]), toint(Attributes["http.status_code"]), toint(ResultCode)) == 200
| project Signal="trace", TraceId),
(OTelLogs | where $filter | project Signal="log", TraceId)
| distinct Signal, TraceId
"@
    $url = "https://api.loganalytics.io/v1/workspaces/$($context.monitoring.logAnalyticsWorkspaceId)/query?query=$([uri]::EscapeDataString($query))"
    $insightsLabel = $context.monitoring.insightsId.ToLowerInvariant() | ConvertTo-Json -Compress
    $selector = '{__name__="azure.ai_gateway.client.token.usage","microsoft.appresourceid"=' + $insightsLabel + ',"azure.ai_gateway.workspace"="default"}'
    $startUnix = ([DateTimeOffset]::Parse($start)).ToUnixTimeSeconds()
    $endUnix = ([DateTimeOffset]::Parse($end)).ToUnixTimeSeconds()
    # Exclude samples from before the test window that Prometheus lookback can carry forward.
    $metricQuery = "($selector > 0) and (timestamp($selector) >= $startUnix)"
    $metricUrl = "$($context.monitoring.prometheusQueryEndpoint)/api/v1/query_range?query=$([uri]::EscapeDataString($metricQuery))&start=$([uri]::EscapeDataString($start))&end=$([uri]::EscapeDataString($end))&step=15s"
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TelemetryWaitSeconds)
    do {
        $response = Invoke-AzureJson @('rest', '--method', 'get', '--resource', 'https://api.loganalytics.io', '--url', $url)
        if ($response.error -or @($response.tables).Count -ne 1) { Stop-Check 'Telemetry API returned an error or unexpected schema.' }
        $table = $response.tables[0]
        if (@($table.columns).Count -ne 2 -or $table.columns[0].name -ne 'Signal' -or $table.columns[1].name -ne 'TraceId') {
            Stop-Check 'Telemetry correlation schema unsupported; delivery not proven.'
        }
        $found = @($table.rows | Where-Object { $_[0] -eq 'trace' } | ForEach-Object { $_[1] })
        $logs = @($table.rows | Where-Object { $_[0] -eq 'log' -and $_[1] -in $traces } | ForEach-Object { $_[1] })
        $metrics = Invoke-AzureJson @('rest', '--method', 'get', '--resource', 'https://prometheus.monitor.azure.com', '--url', $metricUrl)
        if ($metrics.status -ne 'success' -or $metrics.error -or $metrics.data.resultType -ne 'matrix' -or $metrics.warnings) {
            Stop-Check 'Prometheus query failed or returned incomplete/unsupported results.'
        }
        $series = @($metrics.data.result | Where-Object {
            $_.metric.__name__ -ceq 'azure.ai_gateway.client.token.usage' -and
            $_.metric.'microsoft.appresourceid' -ceq $context.monitoring.insightsId.ToLowerInvariant() -and
            $_.metric.'azure.ai_gateway.workspace' -ceq 'default'
        })
        $samples = @($series | ForEach-Object { $_.values } | Where-Object {
            $value = 0.0
            $timestamp = 0.0
            @($_).Count -eq 2 -and [double]::TryParse([string]$_[0], [Globalization.NumberStyles]::Float,
                [Globalization.CultureInfo]::InvariantCulture, [ref]$timestamp) -and
            $timestamp -ge $startUnix -and $timestamp -le $endUnix -and
            [double]::TryParse([string]$_[1], [Globalization.NumberStyles]::Float,
                [Globalization.CultureInfo]::InvariantCulture, [ref]$value) -and [double]::IsFinite($value) -and $value -gt 0
        })
        if (@($traces | Where-Object { $_ -notin $found }).Count -eq 0 -and $logs.Count -gt 0 -and $samples.Count -gt 0) {
            return @{
                matchedTraceIds = $traces; loggedTraceIds = $logs; query = $query
                metricQuery = $metricQuery; positiveMetricSamples = $samples.Count
                metricAttribution = 'Insights/workspace/window scoped; not an exact per-trace token total.'
                windowStartUtc = $start; windowEndUtc = $end
            }
        }
        $remaining = ($deadline - [DateTimeOffset]::UtcNow).TotalSeconds
        if ($remaining -le 0) { break }
        Start-Sleep -Seconds ([Math]::Min(15, [Math]::Ceiling($remaining)))
    } while ($true)
    Stop-Check 'OTLP delivery unproven: require successful server spans for every probe trace, at least one correlated log, and positive scoped token metric samples within the bounded wait.'
}

$statuses = @($checks.Values | ForEach-Object { $_.status })
$report.backendStatus = if ('FAIL' -in $statuses) { 'FAIL' } elseif (@($statuses | Where-Object { $_ -ne 'PASS' }).Count) { 'BLOCKED' } else { 'PASS' }
$report.completedUtc = [DateTimeOffset]::UtcNow.ToString('o')
$report.overallStatus = if ($report.backendStatus -eq 'FAIL') { 'FAIL' } else { 'BLOCKED' }
$report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $directory 'acceptance.json') -Encoding utf8
$portalChecks = @('resource-context', 'configuration', 'playground', 'metrics', 'error-states', 'browser-health')
$portal = [ordered]@{
    schemaVersion = 1; runId = $runId; subscriptionId = $subscription; tenantId = $tenant
    resourceGroup = $ResourceGroup; commit = $report.commit; reviewedUtc = ''; reviewer = ''
    method = 'authenticated-browser'; checks = @($portalChecks | ForEach-Object {
        @{ name = $_; status = 'NOT RUN'; evidence = ''; observed = '' }
    })
    metrics = @{ source = ''; windowStartUtc = ''; windowEndUtc = ''; portalValue = $null; referenceValue = $null; explanation = '' }
}
$portal | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $directory 'portal-evidence.json') -Encoding utf8
Write-Host "Backend: $($report.backendStatus); overall: $($report.overallStatus). Evidence: $directory"
if ($report.backendStatus -ne 'PASS') { throw 'Customer backend acceptance incomplete. See sanitized acceptance.json.' }
Write-Host 'Backend passed. Portal acceptance is still required; use Complete-PortalAcceptance.ps1 after the browser review.'
