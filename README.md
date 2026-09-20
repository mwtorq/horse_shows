# horse_shows
Horse show rider results

## Automation

The runners in `automation\` are driven by Windows Scheduled Tasks under
`\ResultsAutomation\`. They share the helpers, logs and run state in
`C:\Users\mw\ResultsAutomation\`, whose README holds the operational detail.

- `Run-HorseShows.ps1` — the weekly collection: discover shows, scrape class results, repair
  partially loaded shows, a **bounded** non-placing sweep, then Saddle Horse Report enrichment
  (judges / judge cards / horse pedigree) when a DPAPI credential is stored. About ten minutes
  plus up to two hours for the non-placing sweep (SHR time varies).
- `Run-HorseShowsNonPlacingBacklog.ps1` — the non-placing backlog burn-down, roughly 18 days
  of scraping at measured rates. Its own task, no time limit, restartable, newest shows
  first. Registered disabled by `Register-HorseShowsBacklogTask.ps1`.
- `Run-HorseShowsCatchup.ps1` — backfills a year of class results one month at a time.
- `NonPlacingQueue.ps1` — dot-sourced by both non-placing paths. Mirrors the queue query in
  `scrape_class_nonplacing_results.py` and works out where to enter it.
- `Run-HorseShowsPbixRefreshAgent.ps1` — local Cursor agent that refreshes
  `PowerBI\HorseShows.pbix` from SQL Server. `Register-HorseShowsPbixRefreshTask.ps1`
  (or `Register-HorseShowsPbixRefreshTask.cmd`) schedules it every **8 hours**
  (interactive logon, IgnoreNew). Quote the `-File` path under OneDrive — the
  folder name contains spaces. The agent follows `.cursor/skills/refresh-horseshows-pbix`
  and runs `Refresh-HorseShowsPbix.ps1`. If Cursor CLI is missing, the wrapper runs
  the refresh script directly. Setup: `.cursor/automations/refresh-horseshows-pbix.md`.
  This does **not** commit the pbix.

## Scripts

- `scripts\Save-SaddleHorseReportCredential.ps1` — store SHR login once (DPAPI file under
  `RESULTS_AUTOMATION_HOME`, not in the repo).
- `scripts\Get-SaddleHorseReportCredential.ps1` — load that credential for
  `Run-HorseShows.ps1` / unattended scrapes.

Captured SHR pages are written under `saddlehorsereport\{year}\{kind}\` as
`debug_shr_*.html` and matching `*_raw.txt` files, where `kind` is `horse`,
`judges`, `results`, or `other` (same idea as `jrtca_results\{year}\debug_trialvault_*.html`).

The weekly job is bounded on purpose. Its task is `MultipleInstances=IgnoreNew`, so a run
still going on the following Monday makes Task Scheduler skip that trigger — an unbounded
multi-day sweep would silently stop the collection of new results.
