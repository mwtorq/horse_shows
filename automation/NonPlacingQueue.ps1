<#
.SYNOPSIS
    Shared queue arithmetic for the HorseShowsOnline non-placing entry sweep.

.DESCRIPTION
    Dot-sourced by Run-HorseShows.ps1 and Run-HorseShowsNonPlacingBacklog.ps1 after
    Common.ps1. Both need to know how large the non-placing queue is and where to enter
    it, so the SQL that mirrors get_classes_with_nonplacing_entries in
    scrape_class_nonplacing_results.py lives here once instead of in both runners.

    Why the queue is entered by ShowGUID rather than by year: that script offers exactly
    one bound, --start-from <ShowGUID>, which it resolves to a ShowListID and applies as
    sl.ID >= that id. There is no year, month, or count option. ShowList.ID is an identity
    column, so it orders by discovery and not by show year - the 2026 shows occupy ids
    9779-10734 while 2014's sit inside that range at 9914-10251. Starting from the first
    show of the current year therefore drags all of 2014 along with it: 548 shows and
    5,050 classes rather than 2026's own 335 and 3,337. A year is not expressible.

    What is expressible is a suffix of the id order, so both runners work newest first and
    slice the queue by cumulative class count. Get-NonPlacingEntryPoint answers "how far
    down the queue can I start and still stay inside this many classes", which bounds the
    weekly run and sizes each chunk of the backlog run.

    Rates are measured from production, not estimated. Recompute them from a run log if
    the site or the scraper changes.
#>

Set-StrictMode -Version Latest

$script:NonPlacingShowsPerHour   = 17
$script:NonPlacingClassesPerHour = 155
$script:NonPlacingRowsPerHour    = 1300

# Kept literally in step with the WHERE clause of get_classes_with_nonplacing_entries. A
# class leaves the queue when NonPlacingComplete is set or its Place = 0 rows reach
# Entries - Placings, which is what makes the sweep restartable: nothing is checkpointed,
# the queue itself is the checkpoint.
$script:NonPlacingQueueFrom = @"
FROM sResults.ShowClass sc
INNER JOIN sResults.ShowList sl ON sc.ShowListID = sl.ID
LEFT JOIN (
    SELECT ShowClassID, COUNT(*) AS NonPlacingCount
    FROM sResults.ShowResults
    WHERE Place = 0
    GROUP BY ShowClassID
) ec ON ec.ShowClassID = sc.ID
WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID <> ''
  AND sl.StartDate IS NOT NULL
  AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
  AND sc.Entries IS NOT NULL
  AND sc.Placings IS NOT NULL
  AND sc.Entries > sc.Placings
  AND ISNULL(sc.NonPlacingComplete, 0) = 0
  AND ISNULL(ec.NonPlacingCount, 0) < (sc.Entries - sc.Placings)
"@

# Returns Shows/Classes/Rows outstanding, or $null when the count could not be read.
function Get-NonPlacingBacklog {
    param(
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$Server,
        [Parameter(Mandatory)][string]$Database,
        [int]$TimeoutSeconds = 600
    )

    $query = @"
SELECT CAST(COUNT(DISTINCT sc.ShowListID) AS varchar(20)) + '|'
     + CAST(COUNT(*) AS varchar(20)) + '|'
     + CAST(ISNULL(SUM(sc.Entries - sc.Placings - ISNULL(ec.NonPlacingCount, 0)), 0) AS varchar(20))
$script:NonPlacingQueueFrom
"@

    $rows = Get-DbTextRows -Python $Python -Server $Server -Database $Database `
        -Query $query -TimeoutSeconds $TimeoutSeconds
    if (-not $rows -or @($rows).Count -eq 0) { return $null }

    $parts = @($rows)[0] -split '\|'
    if ($parts.Count -ne 3) {
        Write-Log ("Could not parse the non-placing backlog count: '{0}'" -f @($rows)[0]) 'WARN'
        return $null
    }

    return [pscustomobject]@{
        Shows   = [int]$parts[0]
        Classes = [int]$parts[1]
        Rows    = [int]$parts[2]
    }
}

# The deepest (lowest ShowListID) point the sweep can start from while keeping the queue at
# or under $ClassLimit classes, counting newest first. When even the newest show alone
# exceeds the limit it is returned anyway, so the sweep always makes progress; the caller
# sees the real class count and can say so in the log.
#
# Always returns an object with a Status of OK, Empty or Unavailable. An empty queue and a
# query that could not be answered must not look alike: reading a failure as "nothing left
# to do" would end a multi-day burn-down reporting success.
function Get-NonPlacingEntryPoint {
    param(
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$Server,
        [Parameter(Mandatory)][string]$Database,
        [Parameter(Mandatory)][int]$ClassLimit,
        [int]$TimeoutSeconds = 600
    )

    # The queue predicate scans every Place = 0 row in ShowResults, so it must be evaluated
    # exactly once. A common table expression is a definition, not a temp table: an earlier
    # version marked the newest show with a second reference to r, which re-ran the whole
    # scan and pushed the query past a 600-second timeout. ROW_NUMBER carries that marker
    # through the single pass instead. ISNULL guarantees a row, so no output means the query
    # failed rather than that the queue is empty.
    $query = @"
WITH q AS (
    SELECT sc.ShowListID, COUNT(*) AS Classes
    $script:NonPlacingQueueFrom
    GROUP BY sc.ShowListID
),
r AS (
    SELECT ShowListID,
           SUM(Classes) OVER (ORDER BY ShowListID DESC ROWS UNBOUNDED PRECEDING) AS Running,
           ROW_NUMBER() OVER (ORDER BY ShowListID DESC) AS Newest
    FROM q
)
SELECT ISNULL((
    SELECT TOP 1 sl.ShowGUID + '|' + CAST(r.Running AS varchar(20))
    FROM r
    INNER JOIN sResults.ShowList sl ON sl.ID = r.ShowListID
    WHERE r.Running <= $ClassLimit OR r.Newest = 1
    ORDER BY r.ShowListID ASC
), 'NONE|0')
"@

    $rows = Get-DbTextRows -Python $Python -Server $Server -Database $Database `
        -Query $query -TimeoutSeconds $TimeoutSeconds
    if (-not $rows -or @($rows).Count -eq 0) {
        return [pscustomobject]@{ Status = 'Unavailable'; ShowGUID = $null; Classes = 0 }
    }

    $answer = @($rows)[0]
    if ($answer -eq 'NONE|0') {
        return [pscustomobject]@{ Status = 'Empty'; ShowGUID = $null; Classes = 0 }
    }

    $parts = $answer -split '\|'
    if ($parts.Count -ne 2 -or -not $parts[0]) {
        Write-Log ("Could not parse the non-placing entry point: '{0}'" -f $answer) 'WARN'
        return [pscustomobject]@{ Status = 'Unavailable'; ShowGUID = $null; Classes = 0 }
    }

    return [pscustomobject]@{
        Status   = 'OK'
        ShowGUID = $parts[0]
        Classes  = [int]$parts[1]
    }
}

function Get-NonPlacingEtaText {
    param([Parameter(Mandatory)][int]$Classes)

    if ($Classes -le 0) { return 'nothing outstanding' }
    $hours = $Classes / [double]$script:NonPlacingClassesPerHour
    if ($hours -lt 24) { return '{0:N1}h at {1} classes/hour' -f $hours, $script:NonPlacingClassesPerHour }
    return '{0:N0}h ({1:N1} days) at {2} classes/hour' -f $hours, ($hours / 24), $script:NonPlacingClassesPerHour
}
