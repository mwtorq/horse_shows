<#
.SYNOPSIS
    Backfill a year of HorseShowsOnline class results one month at a time.

.DESCRIPTION
    Run-HorseShows.ps1 scrapes newly completed shows in a single long process. That is fine
    for a weekly run of a handful of shows, but a multi-hundred-show backfill in one process
    means any crash, reboot or kill loses the whole run and restarts from the beginning.

    This script splits the same work by StartDate month, so each chunk is its own process.
    Nothing is checkpointed to a state file on purpose: scrape_class_results.py already skips
    shows that have ShowClass rows, so a finished month re-queries in seconds and moves on.
    That makes a resume simply a matter of running the script again.

    Chunks are sized by month rather than show count because show volume is seasonal, and a
    month boundary is something you can reason about when reading the log.

.EXAMPLE
    .\Run-HorseShowsCatchup.ps1 -Year 2026
    .\Run-HorseShowsCatchup.ps1 -Year 2026 -Months 4,5,6
    .\Run-HorseShowsCatchup.ps1 -Year 2026 -DryRun
#>
[CmdletBinding()]
param(
    [string]$Python,

    [int]$Year = (Get-Date).Year,

    # Defaults to every month that still has outstanding shows.
    [string]$Months,

    # The trailing load-missing pass catches classes whose results did not land during the
    # month chunks. It is slow, so it can be skipped when re-running just a month or two.
    [switch]$SkipMissingSweep,

    # Individual shows fail for benign reasons (page pulled, results withdrawn). Only raise
    # the attention flag when a month looks systemically broken.
    [int]$ErrorTolerancePerMonth = 5,

    [switch]$DryRun
)

$AutomationHome = if ($env:RESULTS_AUTOMATION_HOME) { $env:RESULTS_AUTOMATION_HOME } else { 'C:\Users\mw\ResultsAutomation' }
$CommonPath     = Join-Path $AutomationHome 'Common.ps1'
if (-not (Test-Path -LiteralPath $CommonPath)) {
    throw "Shared helpers not found at $CommonPath. Set RESULTS_AUTOMATION_HOME to the folder holding Common.ps1."
}

. $CommonPath
$script:AutomationDryRun = [bool]$DryRun

$Repo     = Split-Path -Parent $PSScriptRoot
$Server   = 'LDAHSAR\SQLEXPRESS'
$Database = 'HorseShows'

Start-RunLog -Name 'horse_shows_catchup' | Out-Null

function Get-OutstandingShowCount {
    param(
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][int]$Year,
        [int]$Month
    )

    # Mirrors the skip_processed branch of get_show_data_from_database so the plan in the log
    # matches what the scraper will actually pick up.
    $monthClause = if ($Month) { " AND MONTH(sl.StartDate) = $Month" } else { '' }
    $query = "SELECT COUNT(*) FROM sResults.ShowList sl WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID <> '' AND sl.StartDate IS NOT NULL AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE) AND (sl.ShowName NOT LIKE '%(INVALID SHOW%' OR sl.ShowName IS NULL) AND sl.Year = $Year$monthClause AND NOT EXISTS (SELECT 1 FROM sResults.ShowClass sc WHERE sc.ShowListID = sl.ID) AND NOT EXISTS (SELECT 1 FROM sResults.ShowResults sr INNER JOIN sResults.ShowClass sc2 ON sr.ShowClassID = sc2.ID WHERE sc2.ShowListID = sl.ID)"

    return Get-DbCount -Python $Python -Server $Server -Database $Database -Query $query -TimeoutSeconds 300
}

try {
    $py = Resolve-PythonPath -Preferred $Python
    Write-Log "Python: $py"
    Write-Log "Repo:   $Repo"
    Write-Log "Year:   $Year"

    if (-not (Test-Path -LiteralPath (Join-Path $Repo 'scrape_class_results.py'))) {
        throw "horse_shows scripts not found under $Repo"
    }

    $requestedMonths = if ($Months) {
        $Months -split '[,;\s]+' | Where-Object { $_ } | ForEach-Object { [int]$_ }
    } else {
        1..12
    }

    foreach ($m in $requestedMonths) {
        if ($m -lt 1 -or $m -gt 12) { throw "Month must be between 1 and 12, got '$m'" }
    }

    Write-Log 'Surveying outstanding shows by month...'
    $plan = [System.Collections.Generic.List[object]]::new()
    foreach ($m in $requestedMonths) {
        $count = Get-OutstandingShowCount -Python $py -Year $Year -Month $m
        if ($null -eq $count) {
            Write-Log ("Month {0:d2}: count query failed, will attempt the chunk anyway" -f $m) 'WARN'
            $count = -1
        }
        if ($count -ne 0) {
            $plan.Add([pscustomobject]@{ Month = $m; Shows = $count })
        }
        Write-Log ("  month {0:d2}: {1} show(s) outstanding" -f $m, $count)
    }

    if ($plan.Count -eq 0) {
        Write-Log "Nothing outstanding for $Year. No chunks to run."
    }
    else {
        $totalPlanned = ($plan | Where-Object { $_.Shows -gt 0 } | Measure-Object -Property Shows -Sum).Sum
        Write-Log ("Plan: {0} chunk(s), {1} show(s) total" -f $plan.Count, $totalPlanned)
    }

    $classesBefore = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowClass' -TimeoutSeconds 300
    $resultsBefore = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowResults' -TimeoutSeconds 300
    Write-Log "Baseline: $classesBefore classes, $resultsBefore results"

    foreach ($chunk in $plan) {
        $label = '{0}-{1:d2}' -f $Year, $chunk.Month
        Invoke-Step -Name "Backfill class results for $label ($($chunk.Shows) shows)" `
            -Exe $py -WorkingDirectory $Repo `
            -Arguments @('scrape_class_results.py', '--direct-url', '--year', "$Year", '--month', "$($chunk.Month)") `
            -ErrorTolerance $ErrorTolerancePerMonth | Out-Null

        if (-not $script:AutomationDryRun) {
            $remaining = Get-OutstandingShowCount -Python $py -Year $Year -Month $chunk.Month
            if ($null -ne $remaining -and $remaining -gt 0) {
                Write-Log ("Month {0:d2} still has {1} outstanding show(s); re-run to retry them" -f $chunk.Month, $remaining) 'WARN'
            }
        }
    }

    # One pass at the end rather than per month: this query scans the whole class table and
    # takes minutes, so paying for it twelve times would dwarf the scraping it feeds.
    if (-not $SkipMissingSweep) {
        Invoke-Step -Name "Fill missing class results for $Year" `
            -Exe $py -WorkingDirectory $Repo `
            -Arguments @('scrape_class_results.py', '--direct-url', '--load-missing', '--year', "$Year") `
            -ErrorTolerance $ErrorTolerancePerMonth | Out-Null
    }

    $classesAfter = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowClass' -TimeoutSeconds 300
    $resultsAfter = Get-DbCount -Python $py -Server $Server -Database $Database -Query 'SELECT COUNT(*) FROM sResults.ShowResults' -TimeoutSeconds 300
    Add-Metric -Label 'sResults.ShowClass'   -Before $classesBefore -After $classesAfter
    Add-Metric -Label 'sResults.ShowResults' -Before $resultsBefore -After $resultsAfter

    $stillOutstanding = Get-OutstandingShowCount -Python $py -Year $Year
    Write-Log ("Outstanding shows for {0} after this run: {1}" -f $Year, $stillOutstanding)
}
catch {
    Write-Log ("Unhandled error: {0}" -f $_.Exception.Message) 'ERROR'
    Write-Log ($_.ScriptStackTrace) 'ERROR'
    $script:CurrentRun.Steps.Add([pscustomobject]@{ Name = 'runner'; Status = 'FAILED'; ExitCode = 1; Seconds = 0 })
}

exit (Complete-RunLog)
