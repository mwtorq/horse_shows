<#
.SYNOPSIS
    Install a simple 8-hour HorseShows.pbix refresh (open -> Refresh -> Save).

.DESCRIPTION
    Writes C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Refresh.ps1 + Run.cmd
    and registers scheduled task \ResultsAutomation\ResultsAutomation - Horse Shows PBIX Refresh.

    No Cursor agent. No Analysis Services / TOM. The scheduled task only ever
    uses -File against the ResultsAutomation path (no spaces).

    -InvokeNow runs Refresh.ps1 in the current interactive session (not by
    queuing the scheduled task), so SendKeys can reach Power BI Desktop.
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

if (-not (Test-Path -LiteralPath $Pbix)) { throw "Missing $Pbix" }

New-Item -ItemType Directory -Force -Path $LaunchDir | Out-Null
$refreshPath = Join-Path $LaunchDir 'Refresh.ps1'
$runCmdPath = Join-Path $LaunchDir 'Run.cmd'
$pbixLiteral = $Pbix.Replace("'", "''")
$logLiteral = (Join-Path $LaunchDir 'refresh.log').Replace("'", "''")

# Keep this template simple: cmd start + SendKeys.
$lines = @(
    '$ErrorActionPreference = ''Stop'''
    ('$pbix = ''{0}''' -f $pbixLiteral)
    ('$log  = ''{0}''' -f $logLiteral)
    '$loadWaitSec = 180'
    '$refreshWaitSec = 300'
    'function Write-Log([string]$Message) {'
    '    $line = ''{0:yyyy-MM-dd HH:mm:ss} {1}'' -f (Get-Date), $Message'
    '    Add-Content -LiteralPath $log -Value $line'
    '    Write-Host $line'
    '}'
    'function Get-PbiExe {'
    '    foreach ($c in @('
    '        "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",'
    '        "$env:ProgramFiles\Microsoft Power BI Desktop\PBIDesktop.exe"'
    '    )) { if (Test-Path -LiteralPath $c) { return $c } }'
    '    $cmd = Get-Command PBIDesktop.exe -ErrorAction SilentlyContinue'
    '    if ($cmd) { return $cmd.Source }'
    '    throw ''PBIDesktop.exe not found'''
    '}'
    'function Get-OpenPbixProcess([string]$Path) {'
    '    $needle = $Path.Replace(''/'', ''\'').ToLowerInvariant()'
    '    foreach ($p in Get-CimInstance Win32_Process -Filter "Name = ''PBIDesktop.exe''") {'
    '        $cl = [string]$p.CommandLine'
    '        if ($cl -and $cl.ToLowerInvariant().Contains($needle)) {'
    '            try { return Get-Process -Id $p.ProcessId -ErrorAction Stop } catch { }'
    '        }'
    '    }'
    '    return $null'
    '}'
    'Write-Log ''---- refresh start ----'''
    'if (-not (Test-Path -LiteralPath $pbix)) { throw "Missing $pbix" }'
    '$proc = Get-OpenPbixProcess $pbix'
    'if (-not $proc) {'
    '    $exe = Get-PbiExe'
    '    Write-Log "Opening: $pbix"'
    '    $arg = ''/c start "" "'' + $exe + ''" "'' + $pbix + ''"'''
    '    Start-Process -FilePath ''cmd.exe'' -ArgumentList $arg -WindowStyle Hidden | Out-Null'
    '    Write-Log "Waiting $loadWaitSec sec for Desktop to load..."'
    '    Start-Sleep -Seconds $loadWaitSec'
    '    $proc = Get-OpenPbixProcess $pbix'
    '    if (-not $proc) { $proc = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue | Sort-Object StartTime -Descending | Select-Object -First 1 }'
    '} else { Write-Log ("Already open pid {0}" -f $proc.Id) }'
    'if (-not $proc -or $proc.HasExited) { throw ''Power BI Desktop did not stay open.'' }'
    'Add-Type -AssemblyName System.Windows.Forms'
    'Add-Type -AssemblyName Microsoft.VisualBasic'
    'Write-Log ("Activate pid {0}" -f $proc.Id)'
    '[Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null'
    'Start-Sleep -Seconds 2'
    'Write-Log ''SendKeys Home > Refresh (Alt+H, R)'''
    '[System.Windows.Forms.SendKeys]::SendWait(''%'')'
    'Start-Sleep -Milliseconds 400'
    '[System.Windows.Forms.SendKeys]::SendWait(''h'')'
    'Start-Sleep -Milliseconds 400'
    '[System.Windows.Forms.SendKeys]::SendWait(''r'')'
    'Write-Log "Waiting $refreshWaitSec sec for refresh..."'
    'Start-Sleep -Seconds $refreshWaitSec'
    'Write-Log ''SendKeys Save (Ctrl+S)'''
    '[Microsoft.VisualBasic.Interaction]::AppActivate($proc.Id) | Out-Null'
    'Start-Sleep -Seconds 1'
    '[System.Windows.Forms.SendKeys]::SendWait(''^s'')'
    'Start-Sleep -Seconds 20'
    'Write-Log ''---- refresh done (Desktop left open) ----'''
)
Set-Content -LiteralPath $refreshPath -Value $lines -Encoding ASCII

$runCmd = @(
    '@echo off'
    'cd /d "%~dp0"'
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Refresh.ps1"'
    'exit /b %ERRORLEVEL%'
) -join "`r`n"
Set-Content -LiteralPath $runCmdPath -Value $runCmd -Encoding ASCII

# Compat for leftover agent launchers / scheduled actions.
$compatPs1 = @(
    '$ErrorActionPreference = ''Stop'''
    '& (Join-Path $PSScriptRoot ''Refresh.ps1'')'
    'exit $LASTEXITCODE'
) -join "`r`n"
Set-Content -LiteralPath (Join-Path $LaunchDir 'Run.ps1') -Value $compatPs1 -Encoding ASCII
Set-Content -LiteralPath (Join-Path $LaunchDir 'DryRun.ps1') -Value $compatPs1 -Encoding ASCII

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$refreshPath`"" -WorkingDirectory $LaunchDir
$trigger = New-ScheduledTaskTrigger -Once -At $At -RepetitionInterval (New-TimeSpan -Hours $RepeatHours)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Every 8 hours: open HorseShows.pbix, ribbon Refresh, Save. Leaves Desktop open.' -Force | Out-Null

Write-Host "Installed $refreshPath"
Write-Host "Run now:  $runCmdPath"
Write-Host "Task $TaskPath$TaskName every $RepeatHours hour(s) from $($At.ToString('t'))"
if ($InvokeNow) {
    Write-Host 'Running refresh in this session (SendKeys needs your desktop)...'
    # Run in-session so SendKeys can reach Power BI. Do not queue the scheduled task for this first run.
    & $refreshPath
    Write-Host "Done. Log: $(Join-Path $LaunchDir 'refresh.log')"
}
