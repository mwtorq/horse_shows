# PASTE THIS ENTIRE BLOCK into Windows PowerShell.
# Do not use: powershell -File C:\Users\mw\OneDrive - ...

$ErrorActionPreference = 'Stop'

$repo = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
$launchDir = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
$taskPath = '\ResultsAutomation\'
$taskName = 'ResultsAutomation - Horse Shows PBIX Refresh'

if (-not (Test-Path -LiteralPath $repo)) {
    throw "Repo not found: $repo"
}

Set-Location -LiteralPath $repo
git fetch origin

# Untracked local copies of automation/.cursor files block checkout/pull.
# Stash them (including untracked), then use main (launcher fix is merged).
$stashName = "pbix-refresh-install-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
git stash push -u -m $stashName -- 2>$null
git checkout main
git pull --ff-only origin main

$automationDir = Join-Path $repo 'automation'
$agent = Join-Path $automationDir 'Run-HorseShowsPbixRefreshAgent.ps1'
if (-not (Test-Path -LiteralPath $agent)) {
    throw "Agent script missing after pull: $agent"
}

New-Item -ItemType Directory -Force -Path $launchDir | Out-Null

$runCmd = @"
@echo off
cd /d "$automationDir"
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-HorseShowsPbixRefreshAgent.ps1" %*
exit /b %ERRORLEVEL%
"@
$dryCmd = @"
@echo off
cd /d "$automationDir"
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-HorseShowsPbixRefreshAgent.ps1" -SkipAgent -DryRun
exit /b %ERRORLEVEL%
"@

Set-Content -LiteralPath (Join-Path $launchDir 'Run.cmd') -Value $runCmd -Encoding ASCII
Set-Content -LiteralPath (Join-Path $launchDir 'DryRun.cmd') -Value $dryCmd -Encoding ASCII

Write-Host "Wrote $launchDir\Run.cmd"
Write-Host "Wrote $launchDir\DryRun.cmd"

$action = New-ScheduledTaskAction -Execute (Join-Path $launchDir 'Run.cmd') -WorkingDirectory $launchDir
$trigger = New-ScheduledTaskTrigger -Once -At '06:00' -RepetitionInterval (New-TimeSpan -Hours 8)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'HorseShows.pbix refresh every 8 hours via space-free ResultsAutomation launcher' -Force | Out-Null

Write-Host "Registered $taskPath$taskName -> $launchDir\Run.cmd"
Write-Host 'Running DryRun.cmd...'
cmd.exe /c "`"$launchDir\DryRun.cmd`""
if ($LASTEXITCODE -ne 0) { throw "DryRun.cmd exited $LASTEXITCODE" }

Write-Host ''
Write-Host 'SUCCESS. Path issue is fixed.'
Write-Host 'Real refresh now:  cmd /c C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd -SkipAgent'
Write-Host 'Or start task:     Start-ScheduledTask -TaskPath ''\ResultsAutomation\'' -TaskName ''ResultsAutomation - Horse Shows PBIX Refresh'''
Write-Host ''
Write-Host "Optional: review stashed local files with  git stash list"
