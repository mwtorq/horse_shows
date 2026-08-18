<#
.SYNOPSIS
    Register the scheduled task that burns down the HorseShowsOnline non-placing backlog.

.DESCRIPTION
    Deliberately separate from ResultsAutomation\Register-Tasks.ps1, which registers the
    three weekly collection tasks with -Force. This job can legitimately be mid-run for
    days, and re-registering a running task tears its instance down, so it is kept out of
    the way of routine re-registration.

    The task is registered DISABLED. Enabling it is a decision about when the machine can
    afford an 18-day scrape, not something a registration script should make.

    Settings and why:

      ExecutionTimeLimit  unlimited. The backlog needs about 435 hours and the runner ends
                          itself when the queue is clear or a budget expires. A limit would
                          have Task Scheduler terminate a healthy run mid-chunk instead.
      MultipleInstances   IgnoreNew, so the repeating trigger can never start a second
                          copy alongside a run that is already going.
      Trigger             every 4 hours, indefinitely. This is the restart mechanism: a run
                          lost to a crash, a wedged Chrome or a reboot is picked up within
                          four hours, and IgnoreNew makes every other firing a no-op. The
                          runner itself refuses to scrape while the weekly job is running.
      StartWhenAvailable  a firing missed because the machine was off runs at next logon.

.EXAMPLE
    .\Register-HorseShowsBacklogTask.ps1
    .\Register-HorseShowsBacklogTask.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [datetime]$At = '19:00',

    [ValidateRange(1, 24)]
    [int]$RepeatHours = 4,

    [string]$ReposRoot = 'c:\Users\mw\OneDrive - timberwilde.net\repos',

    # Registering enabled is possible but not the default; see above.
    [switch]$Enabled,

    # Required to replace the task while an instance of it is running.
    [switch]$Force,

    [switch]$Unregister
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskPath = '\ResultsAutomation\'
$TaskName = 'ResultsAutomation - Horse Shows Non-Placing Backlog'
$Script   = Join-Path $ReposRoot 'horse_shows\automation\Run-HorseShowsNonPlacingBacklog.ps1'

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
if ($existing -and $existing.State -eq 'Running' -and -not $Force) {
    throw "$TaskName is running. Re-registering would end that run; pass -Force if that is what you want."
}

# -Once with a repetition interval and no duration repeats indefinitely, which -Daily
# cannot express.
$trigger = New-ScheduledTaskTrigger -Once -At $At -RepetitionInterval (New-TimeSpan -Hours $RepeatHours)

$settingsArgs = @{
    ExecutionTimeLimit        = [TimeSpan]::Zero
    MultipleInstances         = 'IgnoreNew'
    StartWhenAvailable        = $true
    AllowStartIfOnBatteries   = $true
    DontStopIfGoingOnBatteries = $true
}
if (-not $Enabled) { $settingsArgs['Disable'] = $true }
$settings = New-ScheduledTaskSettingsSet @settingsArgs

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $Script) `
    -WorkingDirectory (Split-Path -Parent $Script)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Long-running burn-down of the HorseShowsOnline non-placing entry backlog into HorseShows.sResults. Registered disabled; enable when the machine can afford a multi-day scrape.' `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath
Write-Host ("Registered: {0}{1}" -f $TaskPath, $TaskName)
Write-Host ("            -> {0}" -f $Script)
Write-Host ("            state {0}, time limit '{1}', {2}" -f
    $task.State, $task.Settings.ExecutionTimeLimit, $task.Settings.MultipleInstances)
Write-Host ''
Write-Host 'To start it:'
Write-Host ("  Enable-ScheduledTask -TaskPath '{0}' -TaskName '{1}'" -f $TaskPath, $TaskName)
Write-Host ("  Start-ScheduledTask  -TaskPath '{0}' -TaskName '{1}'" -f $TaskPath, $TaskName)
Write-Host ''
Write-Host 'To stop it:'
Write-Host ("  Stop-ScheduledTask    -TaskPath '{0}' -TaskName '{1}'" -f $TaskPath, $TaskName)
Write-Host ("  Disable-ScheduledTask -TaskPath '{0}' -TaskName '{1}'" -f $TaskPath, $TaskName)
