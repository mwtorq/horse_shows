<#
.SYNOPSIS
    Burn down the HorseShowsOnline non-placing entry backlog, newest shows first.

.DESCRIPTION
    scrape_class_nonplacing_results.py fills in the entries that did not place: classes
    where Entries > Placings, saved with Place = 0. As of 2026-08-17 that queue holds
    7,378 shows and 70,977 classes, about 340,000 rows. At the measured production rates
    of 17 shows, 155 classes and 1,300 rows an hour, clearing it takes roughly 435 hours -
    about 18 days of continuous scraping.

    That cannot live inside the weekly job. Its task is registered MultipleInstances=
    IgnoreNew, so while a run is in progress the Monday trigger is skipped outright: a
    multi-day sweep would silently stop the collection of new results, which is the whole
    point of the weekly job. Run-HorseShows.ps1 therefore takes only the newest few hundred
    classes and this runner owns the rest.

    Nothing is checkpointed, deliberately. The queue is the checkpoint: a class leaves it
    when NonPlacingComplete is set or its Place = 0 rows reach Entries - Placings, so a
    killed or rebooted run resumes simply by being started again. Each chunk is its own
    Python process, which bounds how much a crash costs and gives Chrome a fresh start.

    Chunks are sized by class count rather than by show, because class counts per show vary
    from one to several hundred and the class rate is what the elapsed time follows. Each
    chunk enters the queue with --start-from, the only bound that script offers; see
    NonPlacingQueue.ps1 for why a year cannot be expressed. Working newest first means the
    freshest results land first, and it matches the order the weekly run uses, so the two
    never duplicate each other's work.

    Two guards keep this out of the weekly job's way, since both drive Chrome against the
    same site and write to the same database:

      1. An exclusive lock file, state\horse_shows.scrape.lock, held for the duration of
         each chunk and released between chunks. It is a held file handle, so it cannot go
         stale: Windows drops it when the process dies.
      2. Before every chunk this runner reads the weekly task's own schedule. If that job
         is running it waits; if the weekly trigger would fire mid-chunk it shortens the
         chunk to fit before the trigger, or ends the pass when too little time remains.

.EXAMPLE
    .\Run-HorseShowsNonPlacingBacklog.ps1 -DryRun
    .\Run-HorseShowsNonPlacingBacklog.ps1
    .\Run-HorseShowsNonPlacingBacklog.ps1 -MaxHours 12
    .\Run-HorseShowsNonPlacingBacklog.ps1 -ClassesPerChunk 500 -MaxChunks 1
#>
[CmdletBinding()]
param(
    [string]$Python,

    # About 9.7 hours per chunk at 155 classes/hour. Larger chunks waste less time
    # re-querying and re-walking the handful of classes that never reach their expected
    # count; smaller chunks report progress more often and lose less to a crash.
    [ValidateRange(1, 1000000)]
    [int]$ClassesPerChunk = 1500,

    # 0 means run until the backlog is empty. Both budgets are checked between chunks
    # only, so a run overshoots -MaxHours by up to one chunk.
    [ValidateRange(0, 100000)]
    [int]$MaxChunks = 0,
    [ValidateRange(0, 100000)]
    [double]$MaxHours = 0,

    # Below this, a chunk squeezed in before the weekly trigger is not worth starting.
    [ValidateRange(1, 1000000)]
    [int]$MinimumChunkClasses = 100,

    # A dead show page or a withdrawn class logs errors and the sweep moves on, so a chunk
    # of hundreds of classes is expected to log a few.
    [int]$ErrorTolerancePerChunk = 25,

    # How long to wait for the weekly run, or for the scrape lock, before ending the pass.
    # Ending is cheap: the task's repeating trigger starts a fresh pass a few hours later.
    [ValidateRange(0, 168)]
    [double]$YieldHours = 6,
    [ValidateRange(0, 10080)]
    [int]$LockWaitMinutes = 10,

    # For running this by hand while the weekly task is deliberately out of the picture.
    [switch]$IgnoreWeeklyTask,

    [switch]$DryRun
)

$AutomationHome = if ($env:RESULTS_AUTOMATION_HOME) { $env:RESULTS_AUTOMATION_HOME } else { 'C:\Users\mw\ResultsAutomation' }
$CommonPath     = Join-Path $AutomationHome 'Common.ps1'
if (-not (Test-Path -LiteralPath $CommonPath)) {
    throw "Shared helpers not found at $CommonPath. Set RESULTS_AUTOMATION_HOME to the folder holding Common.ps1."
}

. $CommonPath
. (Join-Path $PSScriptRoot 'NonPlacingQueue.ps1')
$script:AutomationDryRun = [bool]$DryRun

$Repo           = Split-Path -Parent $PSScriptRoot
$Server         = 'LDAHSAR\SQLEXPRESS'
$Database       = 'HorseShows'
$WeeklyTaskName = 'ResultsAutomation - Horse Shows'
$WeeklyTaskPath = '\ResultsAutomation\'

Start-RunLog -Name 'horse_shows_nonplacing' | Out-Null
$lock = $null

# $null when the task cannot be read, which is treated as "no guard available" rather than
# as a reason to stop an 18-day job.
function Get-WeeklyTaskState {
    try {
        $task = Get-ScheduledTask -TaskName $WeeklyTaskName -TaskPath $WeeklyTaskPath -ErrorAction Stop
        return [pscustomobject]@{
            State       = [string]$task.State
            NextRunTime = ($task | Get-ScheduledTaskInfo).NextRunTime
        }
    }
    catch {
        return $null
    }
}

# How many classes the next chunk may take: the request, a smaller number that fits before
# the weekly trigger, or 0 meaning end the pass.
function Resolve-ChunkBudget {
    param([Parameter(Mandatory)][int]$RequestedClasses)

    if ($script:AutomationDryRun -or $IgnoreWeeklyTask) { return $RequestedClasses }

    $deadline = (Get-Date).AddHours($YieldHours)
    while ($true) {
        $weekly = Get-WeeklyTaskState
        if (-not $weekly) {
            Write-Log ("Could not read {0}{1}, so this pass runs without the schedule guard." -f $WeeklyTaskPath, $WeeklyTaskName) 'WARN'
            return $RequestedClasses
        }

        if ($weekly.State -eq 'Running') {
            if ((Get-Date) -ge $deadline) {
                Request-Attention ("The weekly horse_shows run was still going after {0}h of waiting, so this pass is ending without scraping. The repeating trigger starts another pass later." -f $YieldHours)
                return 0
            }
            Write-Log 'Weekly horse_shows run in progress; waiting 5 minutes rather than scraping alongside it.'
            Start-Sleep -Seconds 300
            continue
        }

        if ($weekly.NextRunTime -and $weekly.NextRunTime -gt (Get-Date)) {
            $requestedHours = $RequestedClasses / [double]$script:NonPlacingClassesPerHour
            # Quarter-hour margin so the chunk is finished and the lock released before the
            # trigger, not racing it.
            $untilTrigger = ($weekly.NextRunTime - (Get-Date)).TotalHours - 0.25
            if ($untilTrigger -lt $requestedHours) {
                $fitted = [int][math]::Floor($untilTrigger * $script:NonPlacingClassesPerHour)
                if ($fitted -lt $MinimumChunkClasses) {
                    Write-Log ("Weekly trigger is due {0}, too soon for a useful chunk; ending this pass so the weekly run has the machine." -f $weekly.NextRunTime)
                    return 0
                }
                Write-Log ("Weekly trigger is due {0}; shortening this chunk to {1} class(es) so it finishes first." -f $weekly.NextRunTime, $fitted)
                return $fitted
            }
        }

        return $RequestedClasses
    }
}

try {
    $py = Resolve-PythonPath -Preferred $Python
    Write-Log "Python: $py"
    Write-Log "Repo:   $Repo"

    $ScrapeScript = Join-Path $Repo 'scrape_class_nonplacing_results.py'
    if (-not (Test-Path -LiteralPath $ScrapeScript)) {
        throw "scrape_class_nonplacing_results.py not found under $Repo"
    }

    $startBacklog = Get-NonPlacingBacklog -Python $py -Server $Server -Database $Database
    if (-not $startBacklog) {
        throw 'Could not read the non-placing backlog. Refusing to start a multi-day sweep blind.'
    }

    Write-Log ("Backlog: {0} show(s), {1} class(es), {2} non-placing row(s) outstanding" -f
        $startBacklog.Shows, $startBacklog.Classes, $startBacklog.Rows)
    Write-Log ("Estimate to clear it: {0}" -f (Get-NonPlacingEtaText -Classes $startBacklog.Classes))
    Write-Log ("Chunk size: {0} class(es), about {1:N1}h each" -f
        $ClassesPerChunk, ($ClassesPerChunk / [double]$script:NonPlacingClassesPerHour))
    if ($MaxChunks -gt 0) { Write-Log ("Chunk budget: {0}" -f $MaxChunks) }
    if ($MaxHours -gt 0)  { Write-Log ("Time budget: {0:N1}h, checked between chunks" -f $MaxHours) }

    $rowsBefore = Get-DbCount -Python $py -Server $Server -Database $Database -TimeoutSeconds 300 `
        -Query 'SELECT COUNT(*) FROM sResults.ShowResults WHERE Place = 0'

    $runStart        = Get-Date
    $chunk           = 0
    $previousClasses = $startBacklog.Classes

    while ($true) {
        if ($MaxChunks -gt 0 -and $chunk -ge $MaxChunks) {
            Write-Log ("Reached the {0}-chunk budget; stopping." -f $MaxChunks)
            break
        }
        $elapsedHours = ((Get-Date) - $runStart).TotalHours
        if ($MaxHours -gt 0 -and $elapsedHours -ge $MaxHours) {
            Write-Log ("Reached the {0:N1}h budget after {1:N1}h; stopping." -f $MaxHours, $elapsedHours)
            break
        }

        $limit = Resolve-ChunkBudget -RequestedClasses $ClassesPerChunk
        if ($limit -le 0) { break }
        $shortened = ($limit -lt $ClassesPerChunk)

        $entry = Get-NonPlacingEntryPoint -Python $py -Server $Server -Database $Database -ClassLimit $limit
        if ($entry.Status -eq 'Empty') {
            Write-Log 'Nothing is waiting on non-placing entries. Backlog clear.'
            break
        }
        if ($entry.Status -ne 'OK') {
            Request-Attention 'Could not work out where to enter the non-placing queue, so this pass scraped nothing. The database was most likely too busy to answer; the repeating trigger will try again.'
            break
        }

        $chunk++
        $lock = Enter-ScrapeLock -Name 'horse_shows.scrape' -WaitMinutes $LockWaitMinutes
        if (-not $lock) {
            Request-Attention ("Could not take the scrape lock within {0} minute(s); another horse_shows run holds it. Ending this pass rather than scraping alongside it." -f $LockWaitMinutes)
            break
        }

        try {
            Invoke-Step -Name ("Non-placing sweep chunk {0}: newest {1} class(es) from ShowGUID {2}" -f $chunk, $entry.Classes, $entry.ShowGUID) `
                -Exe $py -WorkingDirectory $Repo `
                -Arguments @('scrape_class_nonplacing_results.py', '--start-from', $entry.ShowGUID) `
                -ErrorTolerance $ErrorTolerancePerChunk | Out-Null
        }
        finally {
            Exit-ScrapeLock -Lock $lock
            $lock = $null
        }

        if ($script:AutomationDryRun) {
            Write-Log 'Dry run: stopping after one chunk. A real run keeps going until the backlog is empty.'
            break
        }

        $current = Get-NonPlacingBacklog -Python $py -Server $Server -Database $Database
        if (-not $current) {
            Write-Log 'Backlog count unavailable after this chunk; continuing on the next one.' 'WARN'
        }
        else {
            Write-Log ("Chunk {0} cleared {1} class(es). Outstanding: {2} show(s), {3} class(es), {4} row(s), {5}" -f
                $chunk, ($previousClasses - $current.Classes), $current.Shows, $current.Classes, $current.Rows,
                (Get-NonPlacingEtaText -Classes $current.Classes))

            if ($current.Classes -le 0) {
                Write-Log 'Backlog is clear.'
                break
            }
            # A chunk that clears nothing means the sweep is failing rather than working, and
            # the same chunk would be selected again. Stop instead of spinning on it.
            if ($current.Classes -ge $previousClasses) {
                Request-Attention ("Chunk {0} cleared no classes. Stopping rather than retrying the same work; check this log for per-class errors." -f $chunk)
                break
            }
            $previousClasses = $current.Classes
        }

        if ($shortened) {
            Write-Log 'That chunk was shortened for the weekly window; ending this pass so the weekly run has the machine.'
            break
        }
    }

    $rowsAfter = Get-DbCount -Python $py -Server $Server -Database $Database -TimeoutSeconds 300 `
        -Query 'SELECT COUNT(*) FROM sResults.ShowResults WHERE Place = 0'
    Add-Metric -Label 'sResults.ShowResults (Place = 0)' -Before $rowsBefore -After $rowsAfter

    $finalBacklog = Get-NonPlacingBacklog -Python $py -Server $Server -Database $Database
    if ($finalBacklog) {
        Add-Metric -Label 'Non-placing classes outstanding' -Before $startBacklog.Classes -After $finalBacklog.Classes
        Write-Log ("Remaining after {0} chunk(s): {1} show(s), {2} class(es), {3} row(s), {4}" -f
            $chunk, $finalBacklog.Shows, $finalBacklog.Classes, $finalBacklog.Rows,
            (Get-NonPlacingEtaText -Classes $finalBacklog.Classes))
    }
}
catch {
    Write-Log ("Unhandled error: {0}" -f $_.Exception.Message) 'ERROR'
    Write-Log ($_.ScriptStackTrace) 'ERROR'
    $script:CurrentRun.Steps.Add([pscustomobject]@{ Name = 'runner'; Status = 'FAILED'; ExitCode = 1; Seconds = 0 })
}
finally {
    Exit-ScrapeLock -Lock $lock
}

exit (Complete-RunLog)
