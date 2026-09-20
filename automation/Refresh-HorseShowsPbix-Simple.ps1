# ASCII-only. Windows PowerShell 5.1 safe.
# Opens HorseShows.pbix, Home>Refresh (Alt+H,R), Ctrl+S. Leaves Desktop open.
# Call in-process (& .\Refresh-HorseShowsPbix-Simple.ps1) or via Run-PbixRefresh.cmd
# in this folder (relative -File after cd - never pass a full OneDrive -File path).

[CmdletBinding()]
param(
    [string]$PbixPath = '',
    [string]$LogPath = '',
    [int]$LoadTimeoutSec = 300,
    [int]$RefreshWaitSec = 300,
    [switch]$QuickTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($QuickTest) {
    $LoadTimeoutSec = 90
    $RefreshWaitSec = 60
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$KnownPbix = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\PowerBI\HorseShows.pbix'
if (-not $PbixPath) {
    $fromRepo = Join-Path (Join-Path $RepoRoot 'PowerBI') 'HorseShows.pbix'
    if (Test-Path -LiteralPath $fromRepo) {
        $PbixPath = $fromRepo
    } else {
        $PbixPath = $KnownPbix
    }
}
if (-not $LogPath) {
    $launch = if ($env:RESULTS_AUTOMATION_HOME) {
        Join-Path $env:RESULTS_AUTOMATION_HOME 'HorseShowsPbixRefresh'
    } else {
        'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
    }
    if (-not (Test-Path -LiteralPath $launch)) {
        New-Item -ItemType Directory -Force -Path $launch | Out-Null
    }
    $LogPath = Join-Path $launch 'refresh.log'
}

function Write-Log([string]$Message, [string]$Level = 'INFO') {
    $line = '{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}' -f (Get-Date), $Level, $Message
    Write-Host $line
    try { Add-Content -LiteralPath $LogPath -Value $line } catch { }
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class PbixFocus {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
    public const int SW_RESTORE = 9;
}
'@ -ErrorAction SilentlyContinue

function Get-PbiExe {
    foreach ($c in @(
        "$env:ProgramFiles\Microsoft Power BI Desktop\bin\PBIDesktop.exe",
        "$env:ProgramFiles\Microsoft Power BI Desktop\PBIDesktop.exe"
    )) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command PBIDesktop.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw 'PBIDesktop.exe not found. Install Power BI Desktop.'
}

function Get-OpenPbixProcess([string]$Path) {
    $needle = $Path.Replace('/', '\').ToLowerInvariant()
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name = 'PBIDesktop.exe'" -ErrorAction SilentlyContinue) {
        $cl = [string]$p.CommandLine
        if ($cl -and $cl.ToLowerInvariant().Contains($needle)) {
            try { return Get-Process -Id $p.ProcessId -ErrorAction Stop } catch { }
        }
    }
    return $null
}

function Wait-MainWindow([System.Diagnostics.Process]$Process, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw ("PBIDesktop exited while loading (pid {0}, code {1}). Open the pbix manually once." -f $Process.Id, $Process.ExitCode)
        }
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw ("Timed out after {0}s waiting for Power BI main window (pid {1})." -f $TimeoutSec, $Process.Id)
}

function Focus-ProcessWindow([System.Diagnostics.Process]$Process) {
    $Process.Refresh()
    $hwnd = $Process.MainWindowHandle
    if ($hwnd -eq [IntPtr]::Zero) { throw "No main window for pid $($Process.Id)" }
    if ([PbixFocus]::IsIconic($hwnd)) {
        [void][PbixFocus]::ShowWindowAsync($hwnd, [PbixFocus]::SW_RESTORE)
        Start-Sleep -Milliseconds 500
    }
    $ok = [PbixFocus]::SetForegroundWindow($hwnd)
    Write-Log ("SetForegroundWindow pid {0} hwnd {1} ok={2}" -f $Process.Id, $hwnd, $ok)
    Start-Sleep -Seconds 1
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction SilentlyContinue
        [Microsoft.VisualBasic.Interaction]::AppActivate($Process.Id) | Out-Null
    } catch {
        Write-Log ("AppActivate failed: {0}" -f $_.Exception.Message) 'WARN'
    }
    Start-Sleep -Seconds 1
}

Write-Log '==== simple refresh start ===='
Write-Log ("PSVersion={0} User={1}\{2}" -f $PSVersionTable.PSVersion, $env:USERDOMAIN, $env:USERNAME)
Write-Log ("Pbix={0}" -f $PbixPath)
Write-Log ("Log={0}" -f $LogPath)

if ($env:OS -ne 'Windows_NT') { throw 'This script must run on Windows with Power BI Desktop.' }
if (-not (Test-Path -LiteralPath $PbixPath)) { throw "Missing pbix: $PbixPath" }

$item = Get-Item -LiteralPath $PbixPath -Force
Write-Log ("Pbix size={0:N0} bytes LastWrite={1:o}" -f $item.Length, $item.LastWriteTimeUtc)
if ($item.Length -lt 1MB) {
    throw ("HorseShows.pbix is only {0:N0} bytes (LFS pointer or empty). Run: git lfs pull --include=`"PowerBI/HorseShows.pbix`" then OneDrive -> Always keep on this device." -f $item.Length)
}
if ($item.Length -lt 50MB) {
    Write-Log ("Pbix is only {0:N0} bytes - expected ~442MB. Continuing, but refresh may be wrong file." -f $item.Length) 'WARN'
}

$beforeWrite = $item.LastWriteTimeUtc
$proc = Get-OpenPbixProcess $PbixPath

if (-not $proc) {
    $exe = Get-PbiExe
    Write-Log ("PBI exe: {0}" -f $exe)
    Write-Log 'Opening pbix via cmd start (quoted paths)...'
    # start "" "exe" "pbix" - reliable with spaces in OneDrive path
    $arg = '/c start "" "' + $exe + '" "' + $PbixPath + '"'
    Start-Process -FilePath 'cmd.exe' -ArgumentList $arg -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds([Math]::Min(60, $LoadTimeoutSec))
    while ((Get-Date) -lt $deadline -and -not $proc) {
        Start-Sleep -Seconds 2
        $proc = Get-OpenPbixProcess $PbixPath
        if (-not $proc) {
            $proc = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue |
                Sort-Object StartTime -Descending |
                Select-Object -First 1
        }
    }
    if (-not $proc) {
        Write-Log 'cmd start did not yield PBIDesktop; trying Invoke-Item (shell association)...' 'WARN'
        Invoke-Item -LiteralPath $PbixPath
        Start-Sleep -Seconds 10
        $proc = Get-OpenPbixProcess $PbixPath
        if (-not $proc) {
            $proc = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue |
                Sort-Object StartTime -Descending |
                Select-Object -First 1
        }
    }
    if (-not $proc) { throw 'Power BI Desktop did not start. Open HorseShows.pbix manually once, then re-run.' }
    Write-Log ("Started pid {0}; waiting for main window (up to {1}s)..." -f $proc.Id, $LoadTimeoutSec)
    Wait-MainWindow -Process $proc -TimeoutSec $LoadTimeoutSec
    # Extra settle time after window appears (model still loading).
    $settle = [Math]::Min(60, [Math]::Max(15, [int]($LoadTimeoutSec / 5)))
    Write-Log ("Window up; settling {0}s more for model load..." -f $settle)
    Start-Sleep -Seconds $settle
}
else {
    Write-Log ("Already open pid {0}" -f $proc.Id)
    Wait-MainWindow -Process $proc -TimeoutSec ([Math]::Min(60, $LoadTimeoutSec))
}

$proc.Refresh()
if ($proc.HasExited) { throw 'Power BI Desktop exited before refresh.' }

Add-Type -AssemblyName System.Windows.Forms
Focus-ProcessWindow -Process $proc

Write-Log 'SendKeys: Alt, H, R (Home > Refresh)'
[System.Windows.Forms.SendKeys]::SendWait('%')
Start-Sleep -Milliseconds 600
[System.Windows.Forms.SendKeys]::SendWait('h')
Start-Sleep -Milliseconds 600
[System.Windows.Forms.SendKeys]::SendWait('r')

Write-Log ("Waiting {0}s for refresh to finish..." -f $RefreshWaitSec)
Start-Sleep -Seconds $RefreshWaitSec

$proc.Refresh()
if ($proc.HasExited) {
    throw 'Power BI Desktop exited during refresh wait. Keys may have hit the wrong window.'
}

Focus-ProcessWindow -Process $proc
Write-Log 'SendKeys: Ctrl+S (Save)'
[System.Windows.Forms.SendKeys]::SendWait('^s')
Start-Sleep -Seconds 30

$after = Get-Item -LiteralPath $PbixPath -Force
Write-Log ("Pbix LastWrite before={0:o} after={1:o} size={2:N0}" -f $beforeWrite, $after.LastWriteTimeUtc, $after.Length)
if ($after.LastWriteTimeUtc -le $beforeWrite) {
    Write-Log 'WARNING: pbix LastWriteTime did not advance. Refresh/Save may not have worked. Leave Desktop open and check for dialogs.' 'WARN'
    Write-Log '==== simple refresh finished with WARN ====' 'WARN'
    exit 2
}

Write-Log '==== simple refresh done (Desktop left open) ===='
exit 0
