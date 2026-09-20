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
$simple = Join-Path $here 'Refresh-HorseShowsPbix-Simple.ps1'
$runCmdRepo = Join-Path $here 'Run-PbixRefresh.cmd'
$launchDir = if ($env:RESULTS_AUTOMATION_HOME) {
    Join-Path $env:RESULTS_AUTOMATION_HOME 'HorseShowsPbixRefresh'
} else {
    'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
}

Write-Host "Repo:     $repo"
Write-Host "Simple:   $simple"
Write-Host "Launcher: $launchDir"
Write-Host ''

if (-not (Test-Path -LiteralPath $simple)) { throw "Missing $simple" }
if (-not (Test-Path -LiteralPath $register)) { throw "Register script missing." }

Set-Location -LiteralPath $repo

if (-not $SkipRegister) {
    Write-Host '=== Re-registering scheduled task ==='
    & $register -Force
    Write-Host ''
}

if ($InvokeNow) {
    Write-Host "=== Running $simple in this session ==="
    & $simple
    Write-Host ''
}

Write-Host 'Done.'
Write-Host "  Double-click: $runCmdRepo"
Write-Host "  Or:           $(Join-Path $launchDir 'Run.cmd')"
