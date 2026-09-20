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

1. Open **Windows PowerShell**.
2. Open `automation/PASTE_TO_INSTALL.ps1` on GitHub / in the repo, copy the whole file.
3. Paste into PowerShell and press Enter.

Or paste this short form after the branch exists locally:

```powershell
Set-Location 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
git fetch origin
git checkout cursor/horseshows-pbix-refresh-automation
git pull
Get-Content -LiteralPath .\automation\PASTE_TO_INSTALL.ps1 -Raw | Invoke-Expression
```

That writes `C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd` (no spaces)
and points the scheduled task at it. `Run.cmd` cds into the OneDrive automation
folder with quotes, then runs `-File .\Run-HorseShowsPbixRefreshAgent.ps1`.

## Manual run

```text
cmd /c C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\DryRun.cmd
cmd /c C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd -SkipAgent
```

## Optional `/loop`

While Cursor stays open: `/loop every 8 hours` and paste
`automation/HorseShowsPbixRefresh.prompt.txt`.
