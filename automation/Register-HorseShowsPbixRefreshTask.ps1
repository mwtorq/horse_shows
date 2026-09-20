<#
.SYNOPSIS
    Register the 8-hour HorseShows.pbix refresh task using a space-free launcher.

.DESCRIPTION
    Writes C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.ps1 (no spaces)
    and points Task Scheduler at:
      powershell.exe -File C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.ps1

    That Run.ps1 invokes the OneDrive refresh script with -Command and a
    single-quoted path. powershell -File is never given an OneDrive path.
#>
[CmdletBinding()]
param(
    [datetime]$At = '06:00',
    [ValidateRange(1, 24)][int]$RepeatHours = 8,
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
$Repo = Split-Path -Parent $PSScriptRoot
if ($ReposRoot) {
    $candidate = Join-Path $ReposRoot 'horse_shows'
    if (Test-Path -LiteralPath $candidate) { $Repo = $candidate }
}
$Refresh = Join-Path (Join-Path $Repo 'automation') 'Refresh-HorseShowsPbix.ps1'
if (-not (Test-Path -LiteralPath $Refresh)) { throw "Refresh script missing: $Refresh" }

if (-not $LauncherDir) {
    $resultsHome = if ($env:RESULTS_AUTOMATION_HOME) { $env:RESULTS_AUTOMATION_HOME } else { 'C:\Users\mw\ResultsAutomation' }
    $LauncherDir = Join-Path $resultsHome 'HorseShowsPbixRefresh'
}
if ($LauncherDir -match '\s') { throw "LauncherDir must not contain spaces: $LauncherDir" }

$existing = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
if ($Unregister) {
    if (-not $existing) { Write-Host "Not present: $TaskName"; return }
    if ($existing.State -eq 'Running' -and -not $Force) { throw "$TaskName is running; pass -Force" }
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
    Write-Host "Removed: $TaskPath$TaskName"
    return
}
if ($existing -and $existing.State -eq 'Running' -and -not $Force) {
    throw "$TaskName is running; pass -Force"
}

New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null
$runPath = Join-Path $LauncherDir 'Run.ps1'
$dryPath = Join-Path $LauncherDir 'DryRun.ps1'
$refreshLiteral = $Refresh.Replace("'", "''")

$runLines = @(
    'param('
    '    [switch]$DryRun,'
    '    [int]$TimeoutMinutes = 90'
    ')'
    '$ErrorActionPreference = ''Stop'''
    ('$refresh = ''{0}''' -f $refreshLiteral)
    'if (-not (Test-Path -LiteralPath $refresh)) { throw "Missing $refresh" }'
    '$dry = '''''
    'if ($DryRun) { $dry = '' -DryRun'' }'
    ('$inner = ''$env:PBIX_REFRESH_NO_EXIT=''''1''''; $c = & ''''{0}'''' -TimeoutMinutes '' + $TimeoutMinutes + $dry + ''; if ($null -eq $c) {{ if ($LASTEXITCODE -ne $null) {{ $c = $LASTEXITCODE }} else {{ $c = 0 }} }}; exit ([int]$c)''' -f $refreshLiteral)
    '$psi = New-Object System.Diagnostics.ProcessStartInfo'
    '$psi.FileName = ''powershell.exe'''
    '$psi.Arguments = ''-NoProfile -ExecutionPolicy Bypass -Command "'' + $inner + ''"'''
    '$psi.UseShellExecute = $false'
    '$psi.CreateNoWindow = $true'
    '$p = [System.Diagnostics.Process]::Start($psi)'
    '$p.WaitForExit()'
    'exit $p.ExitCode'
)
Set-Content -LiteralPath $runPath -Value $runLines -Encoding ASCII

$dryLines = @(
    '$ErrorActionPreference = ''Stop'''
    ('$run = ''{0}''' -f $runPath.Replace("'", "''"))
    '$psi = New-Object System.Diagnostics.ProcessStartInfo'
    '$psi.FileName = ''powershell.exe'''
    '$psi.Arguments = ''-NoProfile -ExecutionPolicy Bypass -File "'' + $run + ''" -DryRun'''
    ('$psi.WorkingDirectory = ''{0}''' -f $LauncherDir.Replace("'", "''"))
    '$psi.UseShellExecute = $false'
    '$psi.CreateNoWindow = $true'
    '$p = [System.Diagnostics.Process]::Start($psi)'
    '$p.WaitForExit()'
    'exit $p.ExitCode'
)
Set-Content -LiteralPath $dryPath -Value $dryLines -Encoding ASCII

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $runPath) `
    -WorkingDirectory $LauncherDir

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

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'HorseShows.pbix refresh every 8 hours via ResultsAutomation Run.ps1 (no OneDrive in -File).' `
    -Force | Out-Null

Write-Host ("Registered: {0}{1}" -f $TaskPath, $TaskName)
Write-Host ("            -File {0}" -f $runPath)
Write-Host ("Smoke test: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`"" -f $dryPath)

if ($InvokeNow) {
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    Write-Host ("Started: {0}{1}" -f $TaskPath, $TaskName)
}
