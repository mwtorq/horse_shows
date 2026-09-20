<#
.SYNOPSIS
    Register the 8-hour local Cursor agent task that refreshes HorseShows.pbix.

.DESCRIPTION
    Creates \ResultsAutomation\ResultsAutomation - Horse Shows PBIX Refresh. The
    action is Run-HorseShowsPbixRefreshAgent.ps1, which launches Cursor CLI against
    this repo and falls back to Refresh-HorseShowsPbix.ps1.

    Settings:

      RepeatHours         8, indefinitely.
      MultipleInstances   IgnoreNew, so a refresh still running 8 hours later is
                          not stacked.
      ExecutionTimeLimit  2 hours. A 442 MB import model should finish well inside
                          that; a hung Power BI Desktop is terminated.
      LogonType           Interactive. Power BI Desktop needs a logged-on session.
      StartWhenAvailable  a missed firing (machine off / still logged out) runs
                          at the next logon.

.EXAMPLE
    # From PowerShell already in the repo (best — no -File full path):
    Set-Location 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
    & .\automation\Register-HorseShowsPbixRefreshTask.ps1 -InvokeNow

    # Or the .cmd launcher (cds into automation\, then uses a relative -File):
    .\automation\Register-HorseShowsPbixRefreshTask.cmd -InvokeNow

    .\Register-HorseShowsPbixRefreshTask.ps1 -At 06:00 -InvokeNow
    .\Register-HorseShowsPbixRefreshTask.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [datetime]$At = '06:00',

    [ValidateRange(1, 24)]
    [int]$RepeatHours = 8,

    # Optional override. Default is this script's repo (via $PSScriptRoot), which
    # is correct when you launch Register-HorseShowsPbixRefreshTask from the clone.
    # Only set this when registering a task that should point at a different checkout.
    [string]$ReposRoot,

    [switch]$Disabled,
    [switch]$InvokeNow,
    [switch]$Force,
    [switch]$Unregister
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskPath = '\ResultsAutomation\'
$TaskName = 'ResultsAutomation - Horse Shows PBIX Refresh'
$Repo     = Split-Path -Parent $PSScriptRoot
$Script   = Join-Path $PSScriptRoot 'Run-HorseShowsPbixRefreshAgent.ps1'
if ($ReposRoot) {
    $fromRoot = Join-Path $ReposRoot 'horse_shows\automation\Run-HorseShowsPbixRefreshAgent.ps1'
    if (-not (Test-Path -LiteralPath $fromRoot)) {
        throw "ReposRoot override did not contain the runner: $fromRoot"
    }
    $Script = $fromRoot
    $Repo = Split-Path -Parent (Split-Path -Parent $fromRoot)
}

$existing = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue

if ($Unregister) {
    if (-not $existing) {
        Write-Host "Not present: $TaskName"
        return
    }
    if ($existing.State -eq 'Running' -and -not $Force) {
        throw "$TaskName is running. Stop it first, or pass -Force to remove it mid-run."
    }
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
    Write-Host "Removed: $TaskPath$TaskName"
    return
}

if (-not (Test-Path -LiteralPath $Script)) { throw "Runner script missing: $Script" }
$prompt = Join-Path (Split-Path -Parent $Script) 'HorseShowsPbixRefresh.prompt.txt'
$refresh = Join-Path (Split-Path -Parent $Script) 'Refresh-HorseShowsPbix.ps1'
foreach ($required in @($prompt, $refresh)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required file missing: $required" }
}

if ($existing -and $existing.State -eq 'Running' -and -not $Force) {
    throw "$TaskName is running. Re-registering would end that run; pass -Force if that is what you want."
}

$trigger = New-ScheduledTaskTrigger -Once -At $At -RepetitionInterval (New-TimeSpan -Hours $RepeatHours)

$settingsArgs = @{
    ExecutionTimeLimit         = (New-TimeSpan -Hours 2)
    MultipleInstances          = 'IgnoreNew'
    StartWhenAvailable         = $true
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
}
if ($Disabled) { $settingsArgs['Disable'] = $true }
$settings = New-ScheduledTaskSettingsSet @settingsArgs

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

# Task Scheduler drops the double quotes around -File paths that contain spaces
# (OneDrive - timberwilde.net), so powershell.exe only sees C:\Users\mw\OneDrive.
# -Command with a single-quoted path survives that. Escape any ' in the path by doubling.
$workDir = Split-Path -Parent $Script
$scriptLiteral = $Script.Replace("'", "''")
$actionArgs = "-NoProfile -ExecutionPolicy Bypass -Command `"Set-Location -LiteralPath '{0}'; & '{1}'`"" -f
    $workDir.Replace("'", "''"),
    $scriptLiteral
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument $actionArgs `
    -WorkingDirectory $workDir

Write-Host ("Task action: powershell.exe {0}" -f $actionArgs)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Every 8 hours: local Cursor agent refreshes PowerBI\HorseShows.pbix from the HorseShows SQL Server. Interactive logon required for Power BI Desktop.' `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
Write-Host ("Registered: {0}{1}" -f $TaskPath, $TaskName)
Write-Host ("            -> {0}" -f $Script)
Write-Host ("            every {0} hour(s) from {1:t}, state {2}, time limit {3}, {4}" -f
    $RepeatHours, $At, $task.State, $task.Settings.ExecutionTimeLimit, $task.Settings.MultipleInstances)
Write-Host ''
Write-Host 'This task needs an interactive Windows session (Power BI Desktop).'
Write-Host 'Cursor CLI (agent) is preferred; the runner falls back to Refresh-HorseShowsPbix.ps1.'
Write-Host ''
Write-Host 'In Cursor, the in-session equivalent (stops when Cursor quits) is:'
Write-Host '  /loop every 8 hours'
Write-Host '  then paste automation\HorseShowsPbixRefresh.prompt.txt'
Write-Host ''

if ($InvokeNow) {
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    Write-Host "Started: $TaskPath$TaskName"
}
else {
    Write-Host 'To run once now:'
    Write-Host ("  Start-ScheduledTask -TaskPath '{0}' -TaskName '{1}'" -f $TaskPath, $TaskName)
}
