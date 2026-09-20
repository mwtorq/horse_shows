# PASTE into Windows PowerShell in the horse_shows repo.
# Gets the simple refresh from GitHub main WITHOUT git reset (OneDrive-safe),
# installs ResultsAutomation launcher, runs once.

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
$base = 'https://raw.githubusercontent.com/mwtorq/horse_shows/main/automation'
$dir  = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
$taskPath = '\ResultsAutomation\'
$taskName = 'ResultsAutomation - Horse Shows PBIX Refresh'

Set-Location -LiteralPath $repo
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'automation') | Out-Null
New-Item -ItemType Directory -Force -Path $dir | Out-Null

# Prefer "Always keep on this device" for .git so future pulls work:
$gitDir = Join-Path $repo '.git'
if (Test-Path -LiteralPath $gitDir) {
    try { attrib +P $gitDir 2>$null } catch { }
    Remove-Item -LiteralPath (Join-Path $gitDir 'index.lock') -Force -ErrorAction SilentlyContinue
}

function Get-GitHubFile([string]$Name, [string]$Dest) {
    $url = "$base/$Name"
    Write-Host "Downloading $Name ..."
    Invoke-WebRequest -Uri $url -OutFile $Dest -UseBasicParsing
    if (-not (Test-Path -LiteralPath $Dest)) { throw "Failed to download $Name" }
}

$simpleRepo = Join-Path $repo 'automation\Refresh-HorseShowsPbix-Simple.ps1'
$cmdRepo    = Join-Path $repo 'automation\Run-PbixRefresh.cmd'
Get-GitHubFile 'Refresh-HorseShowsPbix-Simple.ps1' $simpleRepo
Get-GitHubFile 'Run-PbixRefresh.cmd' $cmdRepo

Copy-Item -LiteralPath $simpleRepo -Destination (Join-Path $dir 'Refresh.ps1') -Force
$runCmd = @"
@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Refresh.ps1"
exit /b %ERRORLEVEL%
"@
Set-Content -LiteralPath (Join-Path $dir 'Run.cmd') -Value $runCmd -Encoding ASCII

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $dir 'Refresh.ps1')`"" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At '06:00' -RepetitionInterval (New-TimeSpan -Hours 8)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Every 8 hours: HorseShows.pbix Refresh + Save' -Force | Out-Null

Write-Host "Installed task $taskPath$taskName"
Write-Host 'Running refresh NOW in this window...'
& $simpleRepo
Write-Host "Log: $(Join-Path $dir 'refresh.log')"
