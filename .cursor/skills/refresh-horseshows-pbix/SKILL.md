---
name: refresh-horseshows-pbix
description: Refresh the local HorseShows.pbix from SQL Server on this Windows machine. Use when asked to refresh HorseShows.pbix, refresh the Power BI report, or run the 8-hour pbix automation.
---

# Refresh HorseShows.pbix

Refresh the local import-mode Power BI file `PowerBI/HorseShows.pbix` from `HorseShows` on the machine's SQL Server. This is a local-desktop job. Do not try it from a cloud agent VM.

## When to use

- The user asks to refresh `HorseShows.pbix` or the HorseShows Power BI report
- The 8-hour scheduled local Cursor agent run starts
- `/loop` or a Windows Scheduled Task invokes this skill

## Do not

- Scrape HorseShowsOnline or Saddle Horse Report
- Commit or push `HorseShows.pbix` (Git LFS, ~442 MB, changes every refresh)
- Open a pull request
- Publish to Power BI Service unless the user explicitly asks
- Kill Power BI Desktop windows the user already had open
- Refresh from this Linux/cloud environment

## Preconditions (Windows, interactive session)

1. Repo cloned with Git LFS so `PowerBI/HorseShows.pbix` is the real binary, not a 130-byte pointer (`version https://git-lfs.github.com/spec/v1`).
2. Power BI Desktop installed.
3. SQL Server reachable with the model's `ServerName` / `DatabaseName` parameters (committed model uses `localhost` / `HorseShows`; this machine often uses `LDAHSAR\SQLEXPRESS`).
4. An interactive Windows logon. Power BI Desktop will not start from a non-interactive service session.

If the pbix is still an LFS pointer, run `git lfs pull --include="PowerBI/HorseShows.pbix"` and stop if that does not materialize a file larger than 1 MB.

## How to refresh

Run the repo script. Do not reinvent the TOM/UI flow in chat:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "automation\Refresh-HorseShowsPbix.ps1"
```

Useful switches:

| Switch | Purpose |
| --- | --- |
| `-DryRun` | Resolve paths, print the plan, do not start Power BI Desktop |
| `-KeepOpen` | (default) Leave Power BI Desktop running |
| `-CloseWhenDone` | Close Power BI Desktop if this run launched it |
| `-SkipSave` | Refresh the in-memory model only (do not Ctrl+S the pbix) |
| `-TimeoutMinutes 60` | Allow a longer VertiPaq refresh |

The script:

1. Verifies `HorseShows.pbix` is a real file (not a Git LFS pointer / tiny OneDrive stub)
2. Opens it in Power BI Desktop with a fully quoted path (OneDrive spaces break `Start-Process -ArgumentList`)
3. Finds the local Analysis Services port (`msmdsrv.port.txt` / `msmdsrv.exe`)
4. Issues a full TMSL refresh against the in-memory model
5. Sends Ctrl+S so the pbix on disk is updated; leaves Desktop open unless `-CloseWhenDone`

Shared logs live under `RESULTS_AUTOMATION_HOME` (default `C:\Users\mw\ResultsAutomation`) when `Common.ps1` is present. Otherwise the script writes to `%TEMP%\HorseShowsPbixRefresh`.

## Failures

Retry **once** after 30 seconds when:

- Power BI Desktop is still launching
- The Analysis Services port file is not there yet
- SQL Server returns a brief lock/timeout

Do not retry credential, missing-LFS, or "Power BI Desktop is not installed" errors. Report the log path and the exact exception.

## Success

The run succeeded only when all of these are true:

- The refresh script exited 0
- The pbix `LastWriteTime` moved forward (unless `-SkipSave`)
- The script printed a model `LastProcessed` timestamp or equivalent TOM confirmation
