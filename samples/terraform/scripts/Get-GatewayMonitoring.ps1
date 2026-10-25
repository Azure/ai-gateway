#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][guid]$SubscriptionId,
    [Parameter(Mandatory)][string]$ApplicationInsightsId,
    [Parameter(Mandatory)][string]$ExpectedLogAnalyticsId,
    [ValidateRange(0, 600)][int]$WaitSeconds = 0
)

$ErrorActionPreference = 'Stop'
$subscription = $SubscriptionId.ToString()
function Stop-Monitoring([string]$Message) { throw "MONITORING: $Message" }

function Assert-MonitoringId([string]$Id, [string]$Type) {
    $pattern = '^/subscriptions/' + [regex]::Escape($subscription) +
        '/resourceGroups/[^/?#]+/providers/' + [regex]::Escape($Type) + '/[^/?#]+$'
    if ($Id -notmatch $pattern -or $Id -match '[%\\]') {
        Stop-Monitoring "Invalid or cross-subscription $Type linkage."
    }
}

function Read-MonitoringResource([string]$Id, [string]$Version) {
    $text = & az rest --method get --url "https://management.azure.com${Id}?api-version=$Version" `
        --subscription $subscription --only-show-errors --output json 2>$null
    if ($LASTEXITCODE -ne 0) { Stop-Monitoring "ARM read failed (exit $LASTEXITCODE); response omitted." }
    try { $text -join "`n" | ConvertFrom-Json -Depth 100 }
    catch { Stop-Monitoring 'Invalid ARM JSON; response omitted.' }
}

function Get-MonitoringUri([string]$Value) {
    $uri = $null
    if (-not [uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or -not $uri.IsDefaultPort -or $uri.UserInfo -or
        $uri.Query -or $uri.Fragment -or -not $uri.Host.EndsWith('.monitor.azure.com')) {
        Stop-Monitoring 'Expected a credential-free HTTPS Azure Monitor endpoint.'
    }
    $uri
}

Assert-MonitoringId $ApplicationInsightsId 'Microsoft.Insights/components'
Assert-MonitoringId $ExpectedLogAnalyticsId 'Microsoft.OperationalInsights/workspaces'
$applicationGroup = $ApplicationInsightsId -replace '/providers/.*$', ''
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($WaitSeconds)
do {
    $insights = Read-MonitoringResource $ApplicationInsightsId '2020-02-02'
    $p = $insights.properties
    $dcrId = [string]$p.DataCollectionRuleResourceId
    if (-not $dcrId) { $dcrId = [string]$p.DataCollectionRuleId }
    $endpoints = @{
        metricsEndpoint = [string]$p.OTLPMetricsEndpoint
        logsEndpoint = [string]$p.OTLPLogsEndpoint
        tracesEndpoint = [string]$p.OTLPTracesEndpoint
    }
    if ($p.AzureMonitorWorkspaceIngestionMode -eq 'Enabled' -and $dcrId -and
        @($endpoints.Values | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -eq 0) { break }
    $remaining = ($deadline - [DateTimeOffset]::UtcNow).TotalSeconds
    if ($remaining -le 0) { Stop-Monitoring 'OTLP destination metadata incomplete; bounded readiness wait expired. No exporter update is safe.' }
    Start-Sleep -Seconds ([Math]::Min(3, [Math]::Ceiling($remaining)))
} while ($true)

# Never guess a resource ID from an immutable DCR identifier or generated name.
Assert-MonitoringId $dcrId 'Microsoft.Insights/dataCollectionRules'
Assert-MonitoringId $p.WorkspaceResourceId 'Microsoft.OperationalInsights/workspaces'
if ($p.WorkspaceResourceId -ine $ExpectedLogAnalyticsId -or
    -not $p.WorkspaceResourceId.StartsWith("$applicationGroup/", [StringComparison]::OrdinalIgnoreCase)) {
    Stop-Monitoring 'Gateway Log Analytics workspace differs from the expected application destination.'
}
$law = Read-MonitoringResource $p.WorkspaceResourceId '2023-09-01'
if ($law.properties.customerId -notmatch '^[a-fA-F0-9-]{36}$') { Stop-Monitoring 'Missing Log Analytics query workspace ID.' }
$dcr = Read-MonitoringResource $dcrId '2024-03-11'
$dceId = [string]$dcr.properties.dataCollectionEndpointId
Assert-MonitoringId $dceId 'Microsoft.Insights/dataCollectionEndpoints'
$accounts = @($dcr.properties.destinations.monitoringAccounts)
$logDestinations = @($dcr.properties.destinations.logAnalytics)
if ($accounts.Count -ne 1 -or $logDestinations.Count -ne 1 -or
    $logDestinations[0].workspaceResourceId -ine $p.WorkspaceResourceId) {
    Stop-Monitoring 'DCR must reference one monitoring account and the existing gateway Log Analytics workspace.'
}
$amwId = [string]$accounts[0].accountResourceId
Assert-MonitoringId $amwId 'Microsoft.Monitor/accounts'
$amw = Read-MonitoringResource $amwId '2023-04-03'
$dce = Read-MonitoringResource $dceId '2024-03-11'
foreach ($resource in @($insights, $law, $dcr, $dce, $amw)) {
    if ($resource.properties.provisioningState -ne 'Succeeded') { Stop-Monitoring 'Linked monitoring resource is not provisioned successfully.' }
}
$immutableId = [string]$dcr.properties.immutableId
if ($immutableId -notmatch '^dcr-[a-zA-Z0-9]+$') { Stop-Monitoring 'Missing/invalid immutable DCR identifier.' }
foreach ($name in $endpoints.Keys) {
    $uri = Get-MonitoringUri $endpoints[$name]
    $base = if ($name -eq 'metricsEndpoint') { $dce.properties.metricsIngestion.endpoint } else { $dce.properties.logsIngestion.endpoint }
    $baseUri = Get-MonitoringUri $base
    if ($uri.Authority -ine $baseUri.Authority -or
        -not $uri.AbsolutePath.StartsWith("/dataCollectionRules/$immutableId/", [StringComparison]::Ordinal)) {
        Stop-Monitoring 'OTLP endpoint does not belong to the linked DCE/DCR.'
    }
}
$queryEndpoint = [string]$amw.properties.metrics.prometheusQueryEndpoint
$null = Get-MonitoringUri $queryEndpoint
$managedGroups = @(@($dcrId, $dceId, $amwId) | ForEach-Object { $_ -replace '/providers/.*$', '' } |
    Where-Object { $_ -ine $applicationGroup } | Sort-Object -Unique)
foreach ($id in $managedGroups) {
    $group = Read-MonitoringResource $id '2021-04-01'
    if ($group.managedBy -ine $ApplicationInsightsId -and $group.managedBy -ine $amwId) {
        Stop-Monitoring 'External monitoring group is not demonstrably managed by the linked Insights/Monitor account.'
    }
}
[pscustomobject]@{
    insightsId = $ApplicationInsightsId
    logAnalyticsId = [string]$p.WorkspaceResourceId
    logAnalyticsWorkspaceId = [string]$law.properties.customerId
    dataCollectionRuleId = $dcrId
    dataCollectionEndpointId = $dceId
    azureMonitorWorkspaceId = $amwId
    managedGroupIds = $managedGroups
    endpoints = $endpoints
    prometheusQueryEndpoint = $queryEndpoint.TrimEnd('/')
}
