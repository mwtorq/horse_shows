<#
.SYNOPSIS
    Register the 8-hour local Cursor agent task that refreshes HorseShows.pbix.

.DESCRIPTION
    Creates \ResultsAutomation\ResultsAutomation - Horse Shows PBIX Refresh.

    The task does NOT execute anything under OneDrive. It runs
    C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd (no spaces in
    that path). That .cmd cds into the repo automation folder with a quoted
    path, then uses a relative -File .\Run-HorseShowsPbixRefreshAgent.ps1.

    This avoids the powershell.exe error:
      Processing -File 'C:\Users\mw\OneDrive' failed because the file does not
      have a '.ps1' extension
    which happens whenever -File is given the full OneDrive path (spaces).

.EXAMPLE
    # Preferred: paste automation\PASTE_TO_INSTALL.ps1 into PowerShell, or:
    Set-Location 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
    & .\automation\Register-HorseShowsPbixRefreshTask.ps1 -InvokeNow
#>
[CmdletBinding()]
param(
    [datetime]$At = '06:00',

    [ValidateRange(1, 24)]
    [int]$RepeatHours = 8,

    [string]$ReposRoot,

    [string]$LauncherDir,

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

if (-not $LauncherDir) {
    $home = if ($env:RESULTS_AUTOMATION_HOME) { $env:RESULTS_AUTOMATION_HOME } else { 'C:\Users\mw\ResultsAutomation' }
    $LauncherDir = Join-Path $home 'HorseShowsPbixRefresh'
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
$automationDir = Split-Path -Parent $Script
$prompt = Join-Path $automationDir 'HorseShowsPbixRefresh.prompt.txt'
$refresh = Join-Path $automationDir 'Refresh-HorseShowsPbix.ps1'
foreach ($required in @($prompt, $refresh)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required file missing: $required" }
}

if ($existing -and $existing.State -eq 'Running' -and -not $Force) {
    throw "$TaskName is running. Re-registering would end that run; pass -Force if that is what you want."
}

if ($LauncherDir -match '\s') {
    throw "LauncherDir must not contain spaces (got '$LauncherDir'). Use C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh."
}

New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null

# cmd.exe cd /d with quotes handles OneDrive spaces; -File stays relative.
$runCmdPath = Join-Path $LauncherDir 'Run.cmd'
$dryCmdPath = Join-Path $LauncherDir 'DryRun.cmd'
$repoCmd = Join-Path $LauncherDir 'RepoPath.txt'

$runCmd = @"
@echo off
REM Space-free task entrypoint. Do not edit the scheduled task to point at OneDrive.
cd /d "$automationDir"
if errorlevel 1 (
  echo Failed to cd into automation dir.
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-HorseShowsPbixRefreshAgent.ps1" %*
exit /b %ERRORLEVEL%
"@

$dryCmd = @"
@echo off
cd /d "$automationDir"
if errorlevel 1 (
  echo Failed to cd into automation dir.
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-HorseShowsPbixRefreshAgent.ps1" -SkipAgent -DryRun
exit /b %ERRORLEVEL%
"@

Set-Content -LiteralPath $runCmdPath -Value $runCmd -Encoding ASCII
Set-Content -LiteralPath $dryCmdPath -Value $dryCmd -Encoding ASCII
Set-Content -LiteralPath $repoCmd -Value $Repo -Encoding ASCII

Write-Host ("Launcher:  {0}" -f $runCmdPath)
Write-Host ("Automation:{0}" -f $automationDir)

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

# Execute a path with NO spaces. Arguments empty — Run.cmd owns the rest.
$action = New-ScheduledTaskAction `
    -Execute $runCmdPath `
    -WorkingDirectory $LauncherDir

Write-Host ("Task action: {0}" -f $runCmdPath)
Write-Host ("Task cwd:    {0}" -f $LauncherDir)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Every 8 hours: local Cursor agent refreshes PowerBI\HorseShows.pbix. Entrypoint is ResultsAutomation\HorseShowsPbixRefresh\Run.cmd (avoids OneDrive spaces in powershell -File).' `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
Write-Host ("Registered: {0}{1}" -f $TaskPath, $TaskName)
Write-Host ("            -> {0}" -f $runCmdPath)
Write-Host ("            every {0} hour(s) from {1:t}, state {2}, time limit {3}, {4}" -f
    $RepeatHours, $At, $task.State, $task.Settings.ExecutionTimeLimit, $task.Settings.MultipleInstances)
Write-Host ''
Write-Host 'Smoke-test without Task Scheduler:'
Write-Host ('  cmd /c "{0}"' -f $dryCmdPath)
Write-Host ''

if ($InvokeNow) {
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    Write-Host ('Started: {0}{1}' -f $TaskPath, $TaskName)
}
else {
    Write-Host 'To run once now:'
    Write-Host ("  Start-ScheduledTask -TaskPath '{0}' -TaskName '{1}'" -f $TaskPath, $TaskName)
    Write-Host ('  cmd /c "{0}"' -f $runCmdPath)
}
