# PASTE THIS WHOLE BLOCK into Windows PowerShell.
# One job: every 8 hours, open HorseShows.pbix, Refresh, Save.
# No Cursor agent. No TOM. No powershell -File against OneDrive.

$ErrorActionPreference = 'Stop'

$pbix = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\PowerBI\HorseShows.pbix'
$dir  = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
$taskPath = '\ResultsAutomation\'
$taskName = 'ResultsAutomation - Horse Shows PBIX Refresh'

if (-not (Test-Path -LiteralPath $pbix)) { throw "Missing $pbix" }
$size = (Get-Item -LiteralPath $pbix).Length
if ($size -lt 1MB) {
    throw "HorseShows.pbix is only $size bytes. Run: git lfs pull --include=`"PowerBI/HorseShows.pbix`" and keep the file local in OneDrive."
}

New-Item -ItemType Directory -Force -Path $dir | Out-Null

# This script lives under ResultsAutomation (NO spaces). Task Scheduler calls only this file.
$refreshPs1 = @'
$ErrorActionPreference = 'Stop'
$pbix = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\PowerBI\HorseShows.pbix'
$log  = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\refresh.log'
$loadWaitSec = 180
$refreshWaitSec = 300

function Write-Log([string]$Message) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $Message
    Add-Content -LiteralPath $log -Value $line
    Write-Host $line
}

function Get-PbiExe {
    foreach ($c in @(
        "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "$env:ProgramFiles\Microsoft Power BI Desktop\PBIDesktop.exe"
    )) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command PBIDesktop.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw 'PBIDesktop.exe not found'
}

function Get-OpenPbixProcess([string]$Path) {
    $needle = $Path.Replace('/', '\').ToLowerInvariant()
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name = 'PBIDesktop.exe'") {
        $cl = [string]$p.CommandLine
        if ($cl -and $cl.ToLowerInvariant().Contains($needle)) {
            try { return Get-Process -Id $p.ProcessId -ErrorAction Stop } catch { }
        }
    }
    return $null
}

Write-Log '---- refresh start ----'
if (-not (Test-Path -LiteralPath $pbix)) { throw "Missing $pbix" }

$proc = Get-OpenPbixProcess $pbix
if (-not $proc) {
    $exe = Get-PbiExe
    Write-Log "Opening: $pbix"
    # cmd START quotes paths with spaces correctly. Do not use powershell -File / -ArgumentList here.
    $arg = '/c start "" "' + $exe + '" "' + $pbix + '"'
    Start-Process -FilePath 'cmd.exe' -ArgumentList $arg -WindowStyle Hidden | Out-Null
    Write-Log "Waiting $loadWaitSec sec for Desktop to load..."
    Start-Sleep -Seconds $loadWaitSec
    $proc = Get-OpenPbixProcess $pbix
    if (-not $proc) {
        $proc = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1
    }
}
else {
    Write-Log ("Already open pid {0}" -f $proc.Id)
}

if (-not $proc -or $proc.HasExited) { throw 'Power BI Desktop did not stay open. Open the pbix manually once to confirm it loads.' }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

Write-Log ("Activate pid {0}" -f $proc.Id)
[Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null
Start-Sleep -Seconds 2

# English ribbon: Alt, H, R = Home > Refresh
Write-Log 'SendKeys Home > Refresh (Alt+H, R)'
[System.Windows.Forms.SendKeys]::SendWait('%')
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait('h')
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait('r')

Write-Log "Waiting $refreshWaitSec sec for refresh..."
Start-Sleep -Seconds $refreshWaitSec

Write-Log 'SendKeys Save (Ctrl+S)'
[Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null
Start-Sleep -Seconds 1
[System.Windows.Forms.SendKeys]::SendWait('^s')
Start-Sleep -Seconds 20

Write-Log '---- refresh done (Desktop left open) ----'
'@

$refreshPath = Join-Path $dir 'Refresh.ps1'
Set-Content -LiteralPath $refreshPath -Value $refreshPs1 -Encoding ASCII

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
Write-Host "Task: $taskPath$taskName every 8 hours"
Write-Host ''
Write-Host 'Run once now? Starting...'
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Write-Host 'Started. Watch Power BI Desktop and C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\refresh.log'
