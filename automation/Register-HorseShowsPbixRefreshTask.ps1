<#
.SYNOPSIS
    Install the simple 8-hour HorseShows.pbix refresh task.

.DESCRIPTION
    Copies automation\Refresh-HorseShowsPbix-Simple.ps1 to
    C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Refresh.ps1 (no spaces)
    and registers the interactive scheduled task.
#>
[CmdletBinding()]
param(
    [datetime]$At = '06:00',
    [ValidateRange(1, 24)][int]$RepeatHours = 8,
    [switch]$InvokeNow,
    [switch]$Unregister,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskPath = '\ResultsAutomation\'
$TaskName = 'ResultsAutomation - Horse Shows PBIX Refresh'
$Repo = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $PSScriptRoot 'Refresh-HorseShowsPbix-Simple.ps1'
$Pbix = Join-Path (Join-Path $Repo 'PowerBI') 'HorseShows.pbix'
$LaunchDir = if ($env:RESULTS_AUTOMATION_HOME) {
    Join-Path $env:RESULTS_AUTOMATION_HOME 'HorseShowsPbixRefresh'
} else {
    'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
}
if ($LaunchDir -match '\s') { throw "Launcher dir must not contain spaces: $LaunchDir" }

$existing = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
if ($Unregister) {
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
        Write-Host "Removed $TaskPath$TaskName"
    }
    return
}
if ($existing -and $existing.State -eq 'Running' -and -not $Force) {
    throw "$TaskName is running; pass -Force"
}

if (-not (Test-Path -LiteralPath $Src)) { throw "Missing $Src" }
if (-not (Test-Path -LiteralPath $Pbix)) { throw "Missing $Pbix" }

New-Item -ItemType Directory -Force -Path $LaunchDir | Out-Null
$refreshPath = Join-Path $LaunchDir 'Refresh.ps1'
$runCmdPath = Join-Path $LaunchDir 'Run.cmd'
Copy-Item -LiteralPath $Src -Destination $refreshPath -Force

$runCmd = @(
    '@echo off'
    'cd /d "%~dp0"'
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Refresh.ps1"'
    'exit /b %ERRORLEVEL%'
) -join "`r`n"
Set-Content -LiteralPath $runCmdPath -Value $runCmd -Encoding ASCII

$compat = @(
    '$ErrorActionPreference = ''Stop'''
    '& (Join-Path $PSScriptRoot ''Refresh.ps1'')'
    'exit $LASTEXITCODE'
) -join "`r`n"
Set-Content -LiteralPath (Join-Path $LaunchDir 'Run.ps1') -Value $compat -Encoding ASCII
Set-Content -LiteralPath (Join-Path $LaunchDir 'DryRun.ps1') -Value $compat -Encoding ASCII

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$refreshPath`"" -WorkingDirectory $LaunchDir
$trigger = New-ScheduledTaskTrigger -Once -At $At -RepetitionInterval (New-TimeSpan -Hours $RepeatHours)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Every 8 hours: open HorseShows.pbix, Refresh, Save, Publish. Leaves Desktop open.' -Force | Out-Null

Write-Host "Installed $refreshPath"
Write-Host "Run now:  $runCmdPath"
Write-Host "Repo cmd: $(Join-Path $PSScriptRoot 'Run-PbixRefresh.cmd')"
Write-Host "Task $TaskPath$TaskName every $RepeatHours hour(s) from $($At.ToString('t'))"
if ($InvokeNow) {
    Write-Host 'Running refresh in this session...'
    & $Src
    Write-Host "Done. Log: $(Join-Path $LaunchDir 'refresh.log')"
}
