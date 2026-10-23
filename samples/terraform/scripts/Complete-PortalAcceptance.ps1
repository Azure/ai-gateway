#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$BackendReport,
    [Parameter(Mandatory)][string]$PortalEvidence
)

$ErrorActionPreference = 'Stop'
$backend = Get-Content -LiteralPath $BackendReport -Raw | ConvertFrom-Json -Depth 50
$portal = Get-Content -LiteralPath $PortalEvidence -Raw | ConvertFrom-Json -Depth 20
if ($backend.schemaVersion -ne 1 -or $portal.schemaVersion -ne 1 -or $backend.backendStatus -ne 'PASS') {
    throw 'A passing version-1 backend report is required; portal observations cannot override backend failure.'
}
$requiredBackend = @('context', 'placement', 'resources', 'roles', 'connections', 'monitoring', 'private-network', 'drift', 'runtime', 'vm-cleanup', 'telemetry')
foreach ($name in $requiredBackend) {
    if ($backend.checks.$name.status -ne 'PASS') { throw "Missing passing backend check: $name" }
}
foreach ($field in @('runId', 'subscriptionId', 'tenantId', 'resourceGroup', 'commit')) {
    if (-not $backend.$field -or $portal.$field -cne $backend.$field) { throw "Portal context mismatch: $field" }
}
$reviewTime = [DateTimeOffset]::Parse($portal.reviewedUtc)
if ($reviewTime -lt [DateTimeOffset]::Parse($backend.completedUtc) -or $reviewTime -gt [DateTimeOffset]::UtcNow.AddMinutes(5) -or
    [string]::IsNullOrWhiteSpace($portal.reviewer) -or $portal.method -ne 'authenticated-browser') {
    throw 'Record a real authenticated-browser reviewer and a review time after backend acceptance.'
}
$expected = @('resource-context', 'configuration', 'playground', 'metrics', 'error-states', 'browser-health')
if (@($portal.checks).Count -ne $expected.Count -or
    @(Compare-Object $expected @($portal.checks.name)).Count) { throw 'Portal checklist is incomplete or contains duplicate/unknown checks.' }
$evidenceDirectory = Split-Path ([IO.Path]::GetFullPath($PortalEvidence)) -Parent
if ($evidenceDirectory -ne (Split-Path ([IO.Path]::GetFullPath($BackendReport)) -Parent)) {
    throw 'Keep the portal manifest and its evidence alongside the backend report.'
}
foreach ($check in $portal.checks) {
    if ($check.status -ne 'PASS' -or [string]::IsNullOrWhiteSpace($check.observed) -or
        [string]::IsNullOrWhiteSpace($check.evidence) -or [IO.Path]::IsPathRooted($check.evidence) -or
        '..' -in ($check.evidence -split '[/\\]') -or
        -not (Test-Path -LiteralPath (Join-Path $evidenceDirectory $check.evidence) -PathType Leaf)) {
        throw "Portal check requires PASS, an observation and a local relative evidence file: $($check.name)"
    }
}
$metrics = $portal.metrics
if ([string]::IsNullOrWhiteSpace($metrics.source) -or [string]::IsNullOrWhiteSpace($metrics.explanation) -or
    $null -eq $metrics.portalValue -or $null -eq $metrics.referenceValue -or
    $metrics.portalValue -is [string] -or $metrics.referenceValue -is [string] -or
    $metrics.portalValue -is [bool] -or $metrics.referenceValue -is [bool] -or
    [double]$metrics.portalValue -le 0 -or [double]$metrics.referenceValue -le 0 -or
    -not [double]::IsFinite([double]$metrics.portalValue) -or -not [double]::IsFinite([double]$metrics.referenceValue) -or
    [double]$metrics.portalValue -ne [double]$metrics.referenceValue) {
    throw 'Metrics require a positive numeric portal/reference match with a documented source and comparison.'
}
$windowStart = [DateTimeOffset]::Parse($metrics.windowStartUtc)
$windowEnd = [DateTimeOffset]::Parse($metrics.windowEndUtc)
$probeStart = [DateTimeOffset]::Parse($backend.checks.telemetry.evidence.windowStartUtc)
$probeEnd = [DateTimeOffset]::Parse($backend.checks.telemetry.evidence.windowEndUtc)
if ($windowEnd -le $windowStart -or $windowStart -gt $probeStart -or $windowEnd -lt $probeEnd -or
    $windowEnd -gt $reviewTime.AddMinutes(5) -or ($windowEnd - $windowStart).TotalHours -gt 24) {
    throw 'Use a bounded metrics window covering this probe, not historical/unrelated traffic.'
}
$backend.overallStatus = 'PASS'
$backend.portal = @{
    status = 'PASS'
    verification = 'operator-attested; evidence completeness validated, UI not automatically executed'
    evidence = [IO.Path]::GetFileName($PortalEvidence)
    reviewedUtc = $portal.reviewedUtc
}
$destination = Join-Path (Split-Path ([IO.Path]::GetFullPath($BackendReport)) -Parent) 'acceptance-with-portal.json'
if (Test-Path -LiteralPath $destination) { throw 'A completed report already exists. Preserve it; use a new acceptance run for another review.' }
$backend | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $destination -Encoding utf8
Write-Host "PASS: backend plus operator-attested portal acceptance. Report: $destination"
