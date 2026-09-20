# PASTE THIS WHOLE BLOCK into Windows PowerShell.
# Requires repo at the path below (git pull first). Installs 8-hour task + runs once.

$ErrorActionPreference = 'Stop'

$repo = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
$src  = Join-Path $repo 'automation\Refresh-HorseShowsPbix-Simple.ps1'
$pbix = Join-Path $repo 'PowerBI\HorseShows.pbix'
$dir  = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
$taskPath = '\ResultsAutomation\'
$taskName = 'ResultsAutomation - Horse Shows PBIX Refresh'

if (-not (Test-Path -LiteralPath $src)) {
    throw "Missing $src - run: cd `"$repo`"; git pull"
}
if (-not (Test-Path -LiteralPath $pbix)) { throw "Missing $pbix" }
$size = (Get-Item -LiteralPath $pbix).Length
if ($size -lt 1MB) {
    throw "HorseShows.pbix is only $size bytes. Run: git lfs pull --include=`"PowerBI/HorseShows.pbix`" and OneDrive -> Always keep on this device."
}
Write-Host ("Pbix OK: {0:N0} bytes" -f $size)

New-Item -ItemType Directory -Force -Path $dir | Out-Null
$refreshPath = Join-Path $dir 'Refresh.ps1'
Copy-Item -LiteralPath $src -Destination $refreshPath -Force

$runCmd = @"
@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Refresh.ps1"
exit /b %ERRORLEVEL%
"@
Set-Content -LiteralPath (Join-Path $dir 'Run.cmd') -Value $runCmd -Encoding ASCII

# Old agent launchers -> same refresh
$compat = @(
    '$ErrorActionPreference = ''Stop'''
    '& (Join-Path $PSScriptRoot ''Refresh.ps1'')'
    'exit $LASTEXITCODE'
) -join "`r`n"
Set-Content -LiteralPath (Join-Path $dir 'Run.ps1') -Value $compat -Encoding ASCII
Set-Content -LiteralPath (Join-Path $dir 'DryRun.ps1') -Value $compat -Encoding ASCII

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$refreshPath`"" `
    -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At '06:00' -RepetitionInterval (New-TimeSpan -Hours 8)
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -TaskPath $taskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Every 8 hours: open HorseShows.pbix, Refresh, Save. Leaves Power BI open.' `
    -Force | Out-Null

Write-Host "Installed: $refreshPath"
Write-Host "Manual:    $(Join-Path $dir 'Run.cmd')"
Write-Host "Also:      $(Join-Path $repo 'automation\Run-PbixRefresh.cmd')"
Write-Host "Task:      $taskPath$taskName every 8 hours"
Write-Host ''
Write-Host 'Running refresh NOW in this window (needs your desktop for SendKeys)...'
& $src
Write-Host "Done. Log: $(Join-Path $dir 'refresh.log')"
