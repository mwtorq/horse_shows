<#
.SYNOPSIS
    One-shot enable + smoke test for the HorseShows.pbix 8-hour refresh task.
#>
[CmdletBinding()]
param(
    [switch]$SkipRegister,
    [switch]$SkipDryRun,
    [switch]$InvokeNow
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$repo = Split-Path -Parent $here
$register = Join-Path $here 'Register-HorseShowsPbixRefreshTask.ps1'
$launchDir = if ($env:RESULTS_AUTOMATION_HOME) {
    Join-Path $env:RESULTS_AUTOMATION_HOME 'HorseShowsPbixRefresh'
} else {
    'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
}

Write-Host "Repo:     $repo"
Write-Host "Register: $register"
Write-Host "Launcher: $launchDir"
Write-Host ''

if (-not (Test-Path -LiteralPath $register)) {
    throw "Register script missing. Checkout branch cursor/horseshows-pbix-refresh-automation first."
}

Set-Location -LiteralPath $repo

if (-not $SkipRegister) {
    Write-Host '=== Re-registering scheduled task (space-free ResultsAutomation launcher) ==='
    & $register -Force
    Write-Host ''
}

if (-not $SkipDryRun) {
    $dry = Join-Path $launchDir 'DryRun.cmd'
    if (-not (Test-Path -LiteralPath $dry)) {
        throw "DryRun.cmd missing at $dry — registration did not install the launcher."
    }
    Write-Host "=== Dry-run via $dry ==="
    cmd.exe /c "`"$dry`""
    if ($LASTEXITCODE -ne 0) { throw "Dry-run failed with exit $LASTEXITCODE" }
    Write-Host ''
    Write-Host 'Dry-run succeeded. Path quoting is OK.'
}

if ($InvokeNow) {
    Write-Host '=== Starting scheduled task now ==='
    Start-ScheduledTask -TaskPath '\ResultsAutomation\' -TaskName 'ResultsAutomation - Horse Shows PBIX Refresh'
    Write-Host 'Started.'
}

Write-Host ''
Write-Host 'Done. Real refresh:'
Write-Host ("  cmd /c `"{0}`"" -f (Join-Path $launchDir 'Run.cmd'))
