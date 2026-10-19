param()

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$outputsJson = & terraform "-chdir=$root" output -json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Terraform outputs.' }
$outputs = $outputsJson | ConvertFrom-Json
$configuration = $outputs.private_probe_configuration.value
$vmId = $outputs.private_test_vm_id.value
if (-not $configuration -or -not $vmId) {
    throw 'Enable and apply private networking and the test client first.'
}
$subscription = ($vmId -split '/')[2]
$configurationJson = $configuration | ConvertTo-Json -Depth 10 -Compress
$configuration64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($configurationJson))
$source64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'private-path-probe.py')))
$script = @"
set -eu
python3 - '$configuration64' <<'PY'
import base64
import sys
sys.argv = ["private-path-probe.py", "--configuration", base64.b64decode(sys.argv[1]).decode()]
exec(compile(base64.b64decode("$source64"), "private-path-probe.py", "exec"))
PY
"@
$scriptPath = [IO.Path]::GetTempFileName()
try {
    [IO.File]::WriteAllText($scriptPath, $script.Replace("`r`n", "`n"), [Text.UTF8Encoding]::new($false))
    $raw = & az vm run-command invoke --subscription $subscription --ids $vmId `
        --command-id RunShellScript --scripts "@$scriptPath" --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'Azure VM Run Command failed.' }
    $result = $raw | ConvertFrom-Json
    $reports = @(
        foreach ($entry in $result.value) {
            foreach ($line in ($entry.message -split '\r?\n')) {
                if ($line.TrimStart().StartsWith('{')) {
                    $line | ConvertFrom-Json
                }
            }
        }
    )
    if ($reports.Count -ne 1) {
        throw "Expected one probe report. VM result: $($result | ConvertTo-Json -Depth 10 -Compress)"
    }
    $reports[0] | ConvertTo-Json -Depth 10
    if ($reports[0].passed -ne $true) { throw 'The private gateway probe failed.' }
}
finally {
    [IO.File]::Delete($scriptPath)
}
