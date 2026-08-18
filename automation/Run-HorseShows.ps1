<#
.SYNOPSIS
    Weekly HorseShowsOnline collection: discover new shows, scrape class results and
    non-placing entries into HorseShows.sResults.

.DESCRIPTION
    Wraps the existing horse_shows pipeline. The scrapers write straight to SQL Server,
    so there is no separate import step. New-work detection is built in: scrape_class_results.py
    skips shows that already have ShowClass/ShowResults rows and only processes shows whose
    EndDate has passed.

    This machine's hostname is LDAHSAR, which the scripts detect to use Windows
    authentication, so no password prompt appears.

    Shared helpers live outside this repo because all three result-collection repos
    use them. Override the location with the RESULTS_AUTOMATION_HOME environment
    variable. Logs and run state are written there, not into this repo.

    The non-placing sweep is bounded. Unbounded, it walks every class in the database
    where Entries > Placings, which as of 2026-08-17 is 7,378 shows and 70,977 classes -
    roughly 435 hours of scraping. That does not fit in a weekly job, and because the task
    is registered MultipleInstances=IgnoreNew, a run still going on the following Monday
    makes Task Scheduler skip that trigger: a multi-day sweep silently stops the collection
    of new results. So this run takes only the newest -NonPlacingClassLimit classes, and
    Run-HorseShowsNonPlacingBacklog.ps1 burns down the rest as its own task.

.EXAMPLE
    .\Run-HorseShows.ps1
    .\Run-HorseShows.ps1 -Years 2026,2025
    .\Run-HorseShows.ps1 -DiscoverYears 2026,2025
    .\Run-HorseShows.ps1 -NonPlacingClassLimit 0   # old behaviour: sweep everything
#>
[CmdletBinding()]
param(
    [string]$Python,

    # Years for the database-driven sweeps. Cheap, so widening this is low risk.
    [string]$Years,

    # Years for the show-list walk. Kept separate from $Years and defaulted to the current
    # year. scrape_shows_by_year.py now reads each row's ShowGUID from the grid and only
    # clicks into shows it has never seen, so a completed prior year costs minutes rather
    # than hours. Widen this to backfill a year whose shows were never discovered.
    [string]$DiscoverYears,

    [switch]$SkipDiscovery,
    [switch]$SkipMissingSweep,
    [switch]$SkipNonPlacing,

    # Ceiling on the non-placing sweep, counted newest first. 300 classes is about two
    # hours at the measured 155 classes/hour, which keeps the whole weekly run inside the
    # task's execution time limit. 0 restores the old unbounded sweep - weeks of work.
    [int]$NonPlacingClassLimit = 300,

    # How long to wait for the backlog task to release the scrape lock. The weekly run
    # proceeds regardless once this expires: collecting new results is the point of this
    # job, so it is never skipped, only flagged.
    [int]$LockWaitMinutes = 45,

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

$Repo     = Split-Path -Parent $PSScriptRoot
$Server   = 'LDAHSAR\SQLEXPRESS'
$Database = 'HorseShows'

Start-RunLog -Name 'horse_shows' | Out-Null
$lock = $null

try {
    $py = Resolve-PythonPath -Preferred $Python
    Write-Log "Python: $py"
    Write-Log "Repo:   $Repo"

    if (-not (Test-Path -LiteralPath (Join-Path $Repo 'scrape_class_results.py'))) {
        throw "horse_shows scripts not found under $Repo"
    }

    $yearList     = ConvertTo-YearList -Value $Years         -Default @((Get-Date).Year)
    $discoverList = ConvertTo-YearList -Value $DiscoverYears -Default @((Get-Date).Year)
    Write-Log ("Sweep year(s):    {0}" -f ($yearList -join ','))
    Write-Log ("Discover year(s): {0}" -f ($discoverList -join ','))

    # Held for the whole run: every step below drives Chrome against HorseShowsOnline and
    # writes to sResults, so the backlog task must not be doing the same at the same time.
    $lock = Enter-ScrapeLock -Name 'horse_shows.scrape' -WaitMinutes $LockWaitMinutes
    if (-not $lock) {
        Request-Attention ("Another horse_shows scrape still held the lock after {0} minute(s), most likely the non-placing backlog task. Collecting new results anyway, so the two runs will contend for the site and for SQL Express until one of them finishes." -f $LockWaitMinutes)
    }

    $showsBefore   = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowList'
    $classesBefore = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowClass'
    $resultsBefore = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowResults'
    Write-Log "Baseline: $showsBefore shows, $classesBefore classes, $resultsBefore results"

    if (-not $SkipDiscovery) {
        Invoke-Step -Name 'Discover shows and refresh ShowList' `
            -Exe $py -WorkingDirectory $Repo `
            -Arguments @('scrape_shows_by_year.py', ($discoverList -join ',')) | Out-Null
    }

    Invoke-Step -Name 'Scrape class results for newly completed shows' `
        -Exe $py -WorkingDirectory $Repo `
        -Arguments @('scrape_class_results.py', '--direct-url') | Out-Null

    # Catches shows that were partially loaded on an earlier run (class row exists, results missing).
    if (-not $SkipMissingSweep) {
        foreach ($year in $yearList) {
            Invoke-Step -Name "Fill missing class results for $year" `
                -Exe $py -WorkingDirectory $Repo `
                -Arguments @('scrape_class_results.py', '--direct-url', '--load-missing', '--year', "$year") | Out-Null
        }
    }

    if (-not $SkipNonPlacing) {
        $backlog = Get-NonPlacingBacklog -Python $py -Server $Server -Database $Database
        if ($backlog) {
            Write-Log ("Non-placing queue: {0} show(s), {1} class(es), {2} row(s) outstanding, {3}" -f
                $backlog.Shows, $backlog.Classes, $backlog.Rows, (Get-NonPlacingEtaText -Classes $backlog.Classes))
        }

        $stepName = 'Scrape non-placing entries'
        $stepArgs = @('scrape_class_nonplacing_results.py')
        $runSweep = $true

        if ($NonPlacingClassLimit -le 0) {
            Write-Log 'NonPlacingClassLimit is 0, so this run sweeps the entire backlog. Expect days to weeks, and no weekly trigger while it runs.' 'WARN'
            $stepName = 'Scrape non-placing entries (entire backlog)'
        }
        else {
            $entry = Get-NonPlacingEntryPoint -Python $py -Server $Server -Database $Database `
                -ClassLimit $NonPlacingClassLimit
            if ($entry.Status -eq 'Empty') {
                Write-Log 'No classes are waiting on non-placing entries; nothing to sweep.'
                $runSweep = $false
            }
            elseif ($entry.Status -ne 'OK') {
                # Sweeping unbounded would be the alternative, and that is the multi-week run
                # this split exists to prevent.
                Request-Attention 'Could not work out where to enter the non-placing queue, so the sweep was skipped this run. The backlog task covers the same work.'
                $runSweep = $false
            }
            else {
                # --start-from is a lower bound on ShowListID, so entering at this show
                # covers it and everything discovered after it, newest work first.
                if ($entry.Classes -gt $NonPlacingClassLimit) {
                    Write-Log ("The newest show still holds {0} class(es), over the {1}-class limit. Running it anyway rather than leaving new results uncollected." -f
                        $entry.Classes, $NonPlacingClassLimit) 'WARN'
                }
                Write-Log ("Bounding the sweep to the newest {0} class(es), entering at ShowGUID {1}. Everything older belongs to Run-HorseShowsNonPlacingBacklog.ps1." -f
                    $entry.Classes, $entry.ShowGUID)
                $stepName = "Scrape non-placing entries for the newest $($entry.Classes) class(es)"
                $stepArgs += @('--start-from', $entry.ShowGUID)
            }
        }

        if ($runSweep) {
            Invoke-Step -Name $stepName -Exe $py -WorkingDirectory $Repo -Arguments $stepArgs | Out-Null
        }
    }

    $showsAfter   = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowList'
    $classesAfter = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowClass'
    $resultsAfter = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowResults'
    Add-Metric -Label 'sResults.ShowList'    -Before $showsBefore   -After $showsAfter
    Add-Metric -Label 'sResults.ShowClass'   -Before $classesBefore -After $classesAfter
    Add-Metric -Label 'sResults.ShowResults' -Before $resultsBefore -After $resultsAfter
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
