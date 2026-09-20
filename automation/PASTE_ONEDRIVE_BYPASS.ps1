# PASTE into Windows PowerShell. OneDrive-safe (no git reset).
# Downloads latest simple refresh from the fix branch and runs TOM refresh + save.

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
# Branch has the TOM refresh fix; switch to /main after PR merge.
$base = 'https://raw.githubusercontent.com/mwtorq/horse_shows/cursor/pbix-paste-install-stash/automation'
$dir  = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
$taskPath = '\ResultsAutomation\'
$taskName = 'ResultsAutomation - Horse Shows PBIX Refresh'

Set-Location -LiteralPath $repo
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'automation') | Out-Null
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$gitDir = Join-Path $repo '.git'
if (Test-Path -LiteralPath $gitDir) {
    try { attrib +P $gitDir 2>$null } catch { }
    Remove-Item -LiteralPath (Join-Path $gitDir 'index.lock') -Force -ErrorAction SilentlyContinue
}

function Get-GitHubFile([string]$Name, [string]$Dest) {
    Write-Host "Downloading $Name ..."
    Invoke-WebRequest -Uri "$base/$Name" -OutFile $Dest -UseBasicParsing
    if (-not (Test-Path -LiteralPath $Dest) -or (Get-Item -LiteralPath $Dest).Length -lt 100) {
        throw "Download failed: $Name"
    }
}

$simpleRepo = Join-Path $repo 'automation\Refresh-HorseShowsPbix-Simple.ps1'
$cmdRepo    = Join-Path $repo 'automation\Run-PbixRefresh.cmd'
Get-GitHubFile 'Refresh-HorseShowsPbix-Simple.ps1' $simpleRepo
Get-GitHubFile 'Run-PbixRefresh.cmd' $cmdRepo

Copy-Item -LiteralPath $simpleRepo -Destination (Join-Path $dir 'Refresh.ps1') -Force
Set-Content -LiteralPath (Join-Path $dir 'Run.cmd') -Encoding ASCII -Value @"
@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Refresh.ps1"
exit /b %ERRORLEVEL%
"@

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $dir 'Refresh.ps1')`"" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At '06:00' -RepetitionInterval (New-TimeSpan -Hours 8)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Every 8 hours: HorseShows.pbix TOM refresh + Save' -Force | Out-Null

Write-Host "Installed task $taskPath$taskName"
Write-Host 'Running refresh NOW (TOM against open Desktop, then Ctrl+S)...'
Write-Host 'Leave the Power BI window alone until it finishes.'
& $simpleRepo
Write-Host "Log: $(Join-Path $dir 'refresh.log')"
