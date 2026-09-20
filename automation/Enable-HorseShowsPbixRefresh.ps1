<#
.SYNOPSIS
    One-shot enable + run for the HorseShows.pbix 8-hour refresh task.
#>
[CmdletBinding()]
param(
    [switch]$SkipRegister,
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
    throw "Register script missing."
}

Set-Location -LiteralPath $repo

if (-not $SkipRegister) {
    Write-Host '=== Re-registering scheduled task ==='
    & $register -Force
    Write-Host ''
}

$refresh = Join-Path $launchDir 'Refresh.ps1'
$runCmd = Join-Path $launchDir 'Run.cmd'
if (-not (Test-Path -LiteralPath $refresh)) {
    throw "Refresh.ps1 missing at $refresh - registration did not install the launcher."
}

if ($InvokeNow) {
    Write-Host "=== Running $refresh in this session ==="
    & $refresh
    Write-Host ''
}

Write-Host 'Done.'
Write-Host "  Double-click: $runCmd"
Write-Host "  Or: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$refresh`""
