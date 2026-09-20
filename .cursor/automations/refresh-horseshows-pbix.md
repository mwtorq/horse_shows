# Simple HorseShows.pbix refresh every 8 hours

## What it does

1. Opens `PowerBI\HorseShows.pbix` in Power BI Desktop (`cmd start`, handles OneDrive spaces)
2. Sends **Home → Refresh** (Alt+H, R)
3. Waits, then **Ctrl+S**
4. Leaves Power BI open

No Cursor agent. No TOM / Analysis Services scripting.

## Install (paste into Windows PowerShell)

Paste the contents of `automation/PASTE_TO_INSTALL.ps1`.

That writes:

- `C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Refresh.ps1`
- `C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd`
- scheduled task `\ResultsAutomation\ResultsAutomation - Horse Shows PBIX Refresh`

Then it **runs the refresh in that same PowerShell window** (needed for SendKeys).

## Run once

Double-click:

```text
C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Run.cmd
```

Or:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Refresh.ps1
```

Do **not** rely on Task Scheduler → Run for a manual test; use `Run.cmd` so SendKeys hits your desktop.

Log: `C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\refresh.log`

## Requirements

- Interactive Windows logon (SendKeys needs a desktop session)
- Real `.pbix` on disk (~442 MB), not a Git LFS pointer
- English Power BI Desktop ribbon keytips (Alt+H, R)
