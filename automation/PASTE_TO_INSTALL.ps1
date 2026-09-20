# PASTE THIS ENTIRE BLOCK into Windows PowerShell NOW.
# -File is used ONLY for C:\Users\mw\ResultsAutomation\... (no spaces).

$ErrorActionPreference = 'Stop'

$repo = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
$launchDir = 'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
$taskPath = '\ResultsAutomation\'
$taskName = 'ResultsAutomation - Horse Shows PBIX Refresh'
$refresh = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\automation\Refresh-HorseShowsPbix.ps1'

if (-not (Test-Path -LiteralPath $refresh)) {
    throw "Missing $refresh"
}

New-Item -ItemType Directory -Force -Path $launchDir | Out-Null

# Child powershell is started with -Command and a single-quoted OneDrive path.
# Never pass an OneDrive path to powershell -File.
$runPs1 = @'
param(
    [switch]$DryRun,
    [int]$TimeoutMinutes = 90
)
$ErrorActionPreference = 'Stop'
$refresh = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\automation\Refresh-HorseShowsPbix.ps1'
if (-not (Test-Path -LiteralPath $refresh)) { throw "Missing $refresh" }
$refreshQ = $refresh.Replace("'", "''")
$dry = if ($DryRun) { ' -DryRun' } else { '' }
$command = "`$env:PBIX_REFRESH_NO_EXIT='1'; `$c = & '$refreshQ' -TimeoutMinutes $TimeoutMinutes$dry; if (`$null -eq `$c) { if (`$LASTEXITCODE -ne `$null) { `$c = `$LASTEXITCODE } else { `$c = 0 } }; exit ([int]`$c)"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'powershell.exe'
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -Command `"$command`""
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$p = [System.Diagnostics.Process]::Start($psi)
$p.WaitForExit()
exit $p.ExitCode
'@

$dryPs1 = @'
$ErrorActionPreference = 'Stop'
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'powershell.exe'
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\Run.ps1`" -DryRun"
$psi.WorkingDirectory = $PSScriptRoot
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$p = [System.Diagnostics.Process]::Start($psi)
$p.WaitForExit()
exit $p.ExitCode
'@

$runPath = Join-Path $launchDir 'Run.ps1'
$dryPath = Join-Path $launchDir 'DryRun.ps1'
Set-Content -LiteralPath $runPath -Value $runPs1 -Encoding ASCII
Set-Content -LiteralPath $dryPath -Value $dryPs1 -Encoding ASCII
Write-Host "Wrote $runPath"
Write-Host "Wrote $dryPath"

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runPath`"" -WorkingDirectory $launchDir
$trigger = New-ScheduledTaskTrigger -Once -At '06:00' -RepetitionInterval (New-TimeSpan -Hours 8)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'HorseShows.pbix refresh every 8h via ResultsAutomation Run.ps1 (no OneDrive in -File)' -Force | Out-Null
Write-Host "Registered $taskPath$taskName -> -File $runPath"

Write-Host 'Dry-running...'
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'powershell.exe'
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$dryPath`""
$psi.WorkingDirectory = $launchDir
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true
$p = [System.Diagnostics.Process]::Start($psi)
$stdout = $p.StandardOutput.ReadToEnd()
$stderr = $p.StandardError.ReadToEnd()
$p.WaitForExit()
Write-Host $stdout
if ($stderr) { Write-Host $stderr }
if ($p.ExitCode -ne 0) { throw "DryRun failed with exit $($p.ExitCode)" }

Write-Host 'SUCCESS. Path issue is fixed.'
Write-Host "Real refresh: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runPath`""
