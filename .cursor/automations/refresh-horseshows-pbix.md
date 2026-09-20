# Simple HorseShows.pbix refresh every 8 hours

## What it does

1. Opens `PowerBI\HorseShows.pbix` in Power BI Desktop (`cmd start`, OneDrive-safe)
2. Waits for the real main window (`SetForegroundWindow`)
3. Sends **Home -> Refresh** (Alt+H, R), waits, **Ctrl+S**
4. Leaves Power BI open; warns if the `.pbix` timestamp did not change

No Cursor agent. No TOM.

## Fastest manual run (after `git pull`)

Double-click:

```text
...\repos\horse_shows\automation\Run-PbixRefresh.cmd
```

Or in PowerShell (from that folder is fine; in-process is best):

```text
cd "C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\automation"
powershell -NoProfile -ExecutionPolicy Bypass -File .\Refresh-HorseShowsPbix-Simple.ps1
```

Log: `C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\refresh.log`

## Install the 8-hour task

Paste `automation/PASTE_TO_INSTALL.ps1` into Windows PowerShell (after `git pull`).

That copies the simple script to `C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Refresh.ps1`
(no spaces for Task Scheduler `-File`) and registers the task, then runs once in that window.

## Requirements

- Interactive Windows logon (SendKeys needs your desktop)
- Real `.pbix` on disk (~442 MB), not a Git LFS pointer / OneDrive stub
- English Power BI Desktop ribbon keytips (Alt+H, R)
- Do not use Task Scheduler -> Run for a first test; use `Run-PbixRefresh.cmd`
