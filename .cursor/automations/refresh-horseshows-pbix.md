# HorseShows.pbix local refresh automation

Scheduled local Cursor agent that refreshes `PowerBI/HorseShows.pbix` every 8 hours on the Windows machine that holds SQL Server and Power BI Desktop.

This cannot run as a Cursor cloud automation unless that automation is pinned to a self-hosted worker on this PC with computer use. The durable path is Windows Task Scheduler launching Cursor CLI (`agent -p`) on the local clone.

## Prompt

Use the text in `automation/HorseShowsPbixRefresh.prompt.txt` unchanged.

## Enable on the Windows machine

The fix lives on branch `cursor/horseshows-pbix-refresh-automation` until the PR
is merged. A plain `git pull` on `main` will not pick it up.

```powershell
Set-Location 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows'
git fetch origin
git checkout cursor/horseshows-pbix-refresh-automation
git pull
& .\automation\Enable-HorseShowsPbixRefresh.ps1
```

That re-registers the task with a space-safe `-Command` action and runs a dry-run.
Do **not** use `powershell -File C:\Users\mw\OneDrive - ...` (unquoted OneDrive path).

For a real refresh after the dry-run looks good:

```powershell
& .\automation\Run-HorseShowsPbixRefreshAgent.ps1 -SkipAgent
```

Or from cmd.exe: `automation\Run-HorseShowsPbixRefreshAgent.cmd -SkipAgent`

4. Optional in-session loop while Cursor stays open:

   ```
   /loop every 8 hours
   ```

   then paste the prompt file. `/loop` stops if Cursor quits; the scheduled task does not.

## Optional Cursor Automation (self-hosted worker)

If this PC is running `agent worker start --computer-use`, create an automation at cursor.com/automations:

- Trigger: cron `0 */8 * * *` (every 8 hours)
- Repository: `mwtorq/horse_shows`
- Runtime: this machine's self-hosted worker
- Prompt: contents of `automation/HorseShowsPbixRefresh.prompt.txt`
- Pull requests: off
