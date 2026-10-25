#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($command in @(
    @('init', '-backend=false', '-input=false', '-lockfile=readonly'),
    @('fmt', '-check', '-recursive'),
    @('validate'),
    @('test')
)) {
    & terraform "-chdir=$root" @command
    if ($LASTEXITCODE -ne 0) { throw "Terraform $($command[0]) failed." }
}
& python -B -m unittest discover -s (Join-Path $root 'tests') -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Python regression tests failed.' }
foreach ($path in Get-ChildItem -LiteralPath $root -Filter '*.ps1' -Recurse -File) {
    $tokens = $null
    $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($path.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "PowerShell parse failure: $($path.Name)" }
}
& (Join-Path $root 'tests\Test-ModelScripts.ps1')
& (Join-Path $root 'tests\Test-CustomerAcceptance.ps1')
& (Join-Path $root 'tests\Test-PortalAcceptance.ps1')
Write-Host 'Offline checks passed. This does not certify Azure deployment, model runtime or portal behavior.'
