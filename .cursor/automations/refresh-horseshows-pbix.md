# HorseShows.pbix local refresh automation

Scheduled local Cursor agent that refreshes `PowerBI/HorseShows.pbix` every 8 hours on the Windows machine that holds SQL Server and Power BI Desktop.

This cannot run as a Cursor cloud automation unless that automation is pinned to a self-hosted worker on this PC with computer use. The durable path is Windows Task Scheduler launching Cursor CLI (`agent -p`) on the local clone.

## Prompt

Use the text in `automation/HorseShowsPbixRefresh.prompt.txt` unchanged.

## Enable on the Windows machine

1. Clone the repo with Git LFS and pull the pbix:

   ```powershell
   git clone https://github.com/mwtorq/horse_shows.git
   cd horse_shows
   git lfs pull --include="PowerBI/HorseShows.pbix"
   ```

2. Install Cursor CLI if needed (`irm 'https://cursor.com/install?win32=true' | iex`) and sign in, or set `CURSOR_API_KEY`.

3. Register the 8-hour task (enabled, IgnoreNew, interactive logon):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\automation\Register-HorseShowsPbixRefreshTask.ps1
   ```

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
