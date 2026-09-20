# HorseShows.pbix local refresh automation

Scheduled local Cursor agent that refreshes `PowerBI/HorseShows.pbix` every 8 hours
on the Windows machine that holds SQL Server and Power BI Desktop.

## Why OneDrive breaks `powershell -File`

The clone lives under `C:\Users\mw\OneDrive - timberwilde.net\...` (spaces).
Any of these fail with `Processing -File 'C:\Users\mw\OneDrive' failed...`:

```text
powershell -File C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\...
powershell -File "C:\Users\mw\OneDrive - timberwilde.net\..."   # Task Scheduler strips quotes
```

## Install (paste into PowerShell — do not use -File)

Open **Windows PowerShell** and paste the block in `automation/PASTE_TO_INSTALL.ps1`
(or the same block from the agent chat). It stashes conflicting untracked files,
updates `main`, writes the space-free launcher, and dry-runs.

Do **not** run `powershell -File` against any path under OneDrive.

## Manual run

```text
cmd /c C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\DryRun.cmd
cmd /c C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd -SkipAgent
```

## Optional `/loop`

While Cursor stays open: `/loop every 8 hours` and paste
`automation/HorseShowsPbixRefresh.prompt.txt`.
