<#
.SYNOPSIS
    One-shot enable + smoke test for the HorseShows.pbix 8-hour refresh task.

.DESCRIPTION
    Run this from any PowerShell prompt. It locates the repo from $PSScriptRoot,
    re-registers the scheduled task with a space-safe -Command action, then runs
    the refresh agent once with -SkipAgent -DryRun so you can confirm the path
    problem is gone before a real Power BI refresh.

.EXAMPLE
    Set-Location 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
    git fetch origin
    git checkout cursor/horseshows-pbix-refresh-automation
    git pull
    & .\automation\Enable-HorseShowsPbixRefresh.ps1
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
$agent = Join-Path $here 'Run-HorseShowsPbixRefreshAgent.ps1'

Write-Host "Repo:     $repo"
Write-Host "Register: $register"
Write-Host "Agent:    $agent"
Write-Host ''

if (-not (Test-Path -LiteralPath $register)) {
    throw "Register script missing. Checkout branch cursor/horseshows-pbix-refresh-automation first."
}

Set-Location -LiteralPath $repo

if (-not $SkipRegister) {
    Write-Host '=== Re-registering scheduled task (space-safe -Command action) ==='
    & $register -Force
    Write-Host ''
}

if (-not $SkipDryRun) {
    Write-Host '=== Dry-run agent (in-process, no powershell -File full path) ==='
    & $agent -SkipAgent -DryRun
    if ($LASTEXITCODE -ne 0) { throw "Dry-run failed with exit $LASTEXITCODE" }
    Write-Host ''
    Write-Host 'Dry-run succeeded. Path quoting is OK.'
}

if ($InvokeNow) {
    Write-Host '=== Starting scheduled task now ==='
    Start-ScheduledTask -TaskPath '\ResultsAutomation\' -TaskName 'ResultsAutomation - Horse Shows PBIX Refresh'
    Write-Host 'Started. Watch Task Scheduler History / ResultsAutomation logs.'
}

Write-Host ''
Write-Host 'Done. For a real refresh later:'
Write-Host "  & '$agent' -SkipAgent"
