# horse_shows
Horse show rider results

## Automation

The runners in `automation\` are driven by Windows Scheduled Tasks under
`\ResultsAutomation\`. They share the helpers, logs and run state in
`C:\Users\mw\ResultsAutomation\`, whose README holds the operational detail.

- `Run-HorseShows.ps1` — the weekly collection: discover shows, scrape class results, repair
  partially loaded shows, then a **bounded** non-placing sweep. About ten minutes plus up to
  two hours for the sweep.
- `Run-HorseShowsNonPlacingBacklog.ps1` — the non-placing backlog burn-down, roughly 18 days
  of scraping at measured rates. Its own task, no time limit, restartable, newest shows
  first. Registered disabled by `Register-HorseShowsBacklogTask.ps1`.
- `Run-HorseShowsCatchup.ps1` — backfills a year of class results one month at a time.
- `NonPlacingQueue.ps1` — dot-sourced by both non-placing paths. Mirrors the queue query in
  `scrape_class_nonplacing_results.py` and works out where to enter it.

The weekly job is bounded on purpose. Its task is `MultipleInstances=IgnoreNew`, so a run
still going on the following Monday makes Task Scheduler skip that trigger — an unbounded
multi-day sweep would silently stop the collection of new results.
