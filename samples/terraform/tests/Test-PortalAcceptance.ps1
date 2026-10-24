$ErrorActionPreference = 'Stop'
$script = Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts\Complete-PortalAcceptance.ps1'
$directory = Join-Path ([IO.Path]::GetTempPath()) "gateway-portal-tests-$([guid]::NewGuid().ToString('N'))"
$null = New-Item -ItemType Directory -Path $directory
$cases = @('pass', 'backend-fail', 'monitoring-fail', 'telemetry-fail', 'missing-backend-check', 'context', 'not-run', 'duplicate', 'no-evidence', 'old-review', 'old-metrics', 'different-metrics', 'zero-metrics', 'boolean-metrics')
try {
    foreach ($case in $cases) {
        $path = Join-Path $directory $case
        $null = New-Item -ItemType Directory -Path $path
        $now = [DateTimeOffset]::UtcNow
        $backend = @{
            schemaVersion = 1; backendStatus = 'PASS'; overallStatus = 'BLOCKED'; portal = @{}
            runId = 'test-run'; subscriptionId = 'test-subscription'; tenantId = 'test-tenant'; resourceGroup = 'test'; commit = 'test-commit'
            completedUtc = $now.AddMinutes(-1).ToString('o'); checks = @{}
        }
        foreach ($name in @('context', 'placement', 'resources', 'roles', 'connections', 'monitoring', 'private-network', 'drift', 'runtime', 'vm-cleanup', 'telemetry')) {
            $backend.checks[$name] = @{ status = 'PASS' }
        }
        $backend.checks.telemetry.evidence = @{ windowStartUtc = $now.AddMinutes(-4).ToString('o'); windowEndUtc = $now.AddMinutes(-2).ToString('o') }
        $portal = @{
            schemaVersion = 1; runId = $backend.runId; subscriptionId = $backend.subscriptionId; tenantId = $backend.tenantId
            resourceGroup = $backend.resourceGroup; commit = $backend.commit; reviewedUtc = $now.ToString('o')
            reviewer = 'test-operator'; method = 'authenticated-browser'
            checks = @(@('resource-context', 'configuration', 'playground', 'metrics', 'error-states', 'browser-health') | ForEach-Object {
                @{ name = $_; status = 'PASS'; evidence = 'observation.txt'; observed = 'Offline fixture, not a live UI test.' }
            })
            metrics = @{
                source = 'offline fixture'; windowStartUtc = $now.AddMinutes(-5).ToString('o'); windowEndUtc = $now.ToString('o')
                portalValue = 2; referenceValue = 2; explanation = 'Offline fixture, not real telemetry.'
            }
        }
        switch ($case) {
            'backend-fail' { $backend.backendStatus = 'FAIL' }
            'monitoring-fail' { $backend.checks.monitoring.status = 'FAIL' }
            'telemetry-fail' { $backend.checks.telemetry.status = 'FAIL' }
            'missing-backend-check' { $backend.checks.Remove('private-network') }
            'context' { $portal.runId = 'wrong-run' }
            'not-run' { $portal.checks[0].status = 'NOT RUN' }
            'duplicate' { $portal.checks[0].name = 'metrics' }
            'no-evidence' { $portal.checks[0].evidence = 'missing.txt' }
            'old-review' { $portal.reviewedUtc = $now.AddDays(-1).ToString('o') }
            'old-metrics' { $portal.metrics.windowStartUtc = $now.AddDays(-2).ToString('o') }
            'different-metrics' { $portal.metrics.portalValue = 3 }
            'zero-metrics' { $portal.metrics.portalValue = 0; $portal.metrics.referenceValue = 0 }
            'boolean-metrics' { $portal.metrics.portalValue = $true; $portal.metrics.referenceValue = $true }
        }
        $backendFile = Join-Path $path 'acceptance.json'
        $portalFile = Join-Path $path 'portal-evidence.json'
        $backend | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $backendFile
        $portal | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $portalFile
        'Offline fixture only.' | Set-Content -LiteralPath (Join-Path $path 'observation.txt')
        $failure = $null
        try { & $script -BackendReport $backendFile -PortalEvidence $portalFile 6>$null }
        catch { $failure = $_.Exception.Message }
        if (($case -eq 'pass' -and $failure) -or ($case -ne 'pass' -and -not $failure)) { throw "Portal case $case failed: $failure" }
        $completed = Join-Path $path 'acceptance-with-portal.json'
        if ((Test-Path -LiteralPath $completed) -ne ($case -eq 'pass')) { throw 'Incorrect completed-report publication.' }
    }
    "Portal evidence checks passed ($($cases.Count) scenarios; no browser interactions)."
}
finally { Remove-Item -LiteralPath $directory -Recurse -Force }
