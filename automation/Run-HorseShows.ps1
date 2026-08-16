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

.EXAMPLE
    .\Run-HorseShows.ps1
    .\Run-HorseShows.ps1 -Years 2026,2025
    .\Run-HorseShows.ps1 -DiscoverYears 2026,2025
#>
[CmdletBinding()]
param(
    [string]$Python,

    # Years for the database-driven sweeps. Cheap, so widening this is low risk.
    [string]$Years,

    # Years for the show-list walk. Deliberately separate and defaulted to the current
    # year: scrape_shows_by_year.py clicks into every show of a year and reselects the
    # year picker each time, so a completed prior year costs hours and finds nothing.
    # Widen this only to backfill a year whose shows were never discovered.
    [string]$DiscoverYears,

    [switch]$SkipDiscovery,
    [switch]$SkipMissingSweep,
    [switch]$SkipNonPlacing,
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

Start-RunLog -Name 'horse_shows' | Out-Null

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
        Invoke-Step -Name 'Scrape non-placing entries' `
            -Exe $py -WorkingDirectory $Repo `
            -Arguments @('scrape_class_nonplacing_results.py') | Out-Null
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

exit (Complete-RunLog)
