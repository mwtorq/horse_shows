# ASCII-only. Windows PowerShell 5.1 safe.
# Open HorseShows.pbix, refresh model via TOM (Analysis Services), Ctrl+S save,
# then Home > Publish to Power BI Service (Replace if prompted).
# Falls back to UI Automation / SendKeys if TOM is unavailable.
# Use Run-PbixRefresh.cmd (relative -File) or call in-process with &.

[CmdletBinding()]
param(
    [string]$PbixPath = '',
    [string]$LogPath = '',
    [int]$LoadTimeoutSec = 420,
    [int]$RefreshWaitSec = 300,
    [int]$PublishTimeoutSec = 900,
    [string]$WorkspaceName = 'My workspace',
    [switch]$QuickTest,
    [switch]$UiOnly,
    [switch]$SkipPublish,
    [switch]$PublishOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($QuickTest) {
    $LoadTimeoutSec = 120
    $RefreshWaitSec = 90
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$KnownPbix = 'C:\Users\mw\OneDrive - timberwilde.net\repos\horse_shows\PowerBI\HorseShows.pbix'
if (-not $PbixPath) {
    $fromRepo = Join-Path (Join-Path $RepoRoot 'PowerBI') 'HorseShows.pbix'
    if (Test-Path -LiteralPath $fromRepo) { $PbixPath = $fromRepo } else { $PbixPath = $KnownPbix }
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

function Get-TomSearchRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    try {
        $exe = Get-PbiExe
        $roots.Add((Split-Path -Parent $exe)) | Out-Null
    } catch { }
    foreach ($r in @(
        (Join-Path ${env:ProgramFiles} 'Microsoft Power BI Desktop\bin'),
        (Join-Path ${env:ProgramFiles} 'Microsoft Power BI Desktop'),
        (Join-Path ${env:LocalAppData} 'Microsoft\Power BI Desktop')
    )) {
        if ($r) { $roots.Add($r) | Out-Null }
    }
    Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Packages') -Filter 'Microsoft.MicrosoftPowerBIDesktop_*' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object {
            $roots.Add((Join-Path $_.FullName 'LocalCache\Local\Microsoft\Power BI Desktop\bin')) | Out-Null
            $roots.Add((Join-Path $_.FullName 'LocalCache\Local\Microsoft\Power BI Desktop')) | Out-Null
        }
    $tomHome = if ($env:RESULTS_AUTOMATION_HOME) {
        Join-Path $env:RESULTS_AUTOMATION_HOME 'tom_nuget'
    } else {
        'C:\Users\mw\ResultsAutomation\tom_nuget'
    }
    $roots.Add((Join-Path $tomHome 'Microsoft.AnalysisServices.retail.amd64\lib\net45')) | Out-Null
    $roots.Add((Join-Path $tomHome 'Microsoft.AnalysisServices.retail.amd64\lib\net472')) | Out-Null
    $roots.Add((Join-Path $tomHome 'Microsoft.AnalysisServices.retail.amd64\lib\net8.0')) | Out-Null
    $roots.Add((Join-Path $env:TEMP 'tom_nuget\Microsoft.AnalysisServices.retail.amd64\lib\net45')) | Out-Null
    $roots.Add((Join-Path $env:TEMP 'tom_nuget\Microsoft.AnalysisServices.retail.amd64\lib\net8.0')) | Out-Null
    return @($roots | Select-Object -Unique)
}

function Find-TomDirectory {
    $need = 'Microsoft.AnalysisServices.Tabular.dll'
    foreach ($root in Get-TomSearchRoots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        $direct = Join-Path $root $need
        if (Test-Path -LiteralPath $direct) { return $root }
        $hit = Get-ChildItem -Path $root -Filter $need -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($hit) { return $hit.DirectoryName }
    }
    return $null
}

function Get-TomNugetLibDir {
    $tomHome = if ($env:RESULTS_AUTOMATION_HOME) {
        Join-Path $env:RESULTS_AUTOMATION_HOME 'tom_nuget'
    } else {
        'C:\Users\mw\ResultsAutomation\tom_nuget'
    }
    foreach ($rel in @(
        'Microsoft.AnalysisServices.retail.amd64\lib\net472',
        'Microsoft.AnalysisServices.retail.amd64\lib\net45',
        'Microsoft.AnalysisServices.retail.amd64\lib\net8.0',
        'Microsoft.AnalysisServices.retail.amd64\lib\netstandard2.0'
    )) {
        $cand = Join-Path $tomHome $rel
        if (Test-Path -LiteralPath (Join-Path $cand 'Microsoft.AnalysisServices.Tabular.dll')) {
            return $cand
        }
    }
    # Any Tabular.dll under tom_nuget
    $hit = Get-ChildItem -Path $tomHome -Filter 'Microsoft.AnalysisServices.Tabular.dll' -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($hit) { return $hit.DirectoryName }
    return $null
}

function Install-TomFromNuget {
    $tomHome = if ($env:RESULTS_AUTOMATION_HOME) {
        Join-Path $env:RESULTS_AUTOMATION_HOME 'tom_nuget'
    } else {
        'C:\Users\mw\ResultsAutomation\tom_nuget'
    }
    New-Item -ItemType Directory -Force -Path $tomHome | Out-Null
    $existing = Get-TomNugetLibDir
    if ($existing) {
        Write-Log ("TOM NuGet already present: {0}" -f $existing)
        return $existing
    }
    $pkgDir = Join-Path $tomHome 'Microsoft.AnalysisServices.retail.amd64'
    $zip = Join-Path $tomHome 'Microsoft.AnalysisServices.retail.amd64.nupkg.zip'
    $url = 'https://www.nuget.org/api/v2/package/Microsoft.AnalysisServices.retail.amd64'
    Write-Log ("DOWNLOADING TOM NuGet from {0}" -f $url)
    Write-Host ">>> DOWNLOADING TOM NuGet package (one-time)..."
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    $len = (Get-Item -LiteralPath $zip).Length
    Write-Log ("Downloaded nupkg size={0:N0} bytes -> {1}" -f $len, $zip)
    Write-Host (">>> Downloaded {0:N0} bytes" -f $len)
    if (Test-Path -LiteralPath $pkgDir) { Remove-Item -LiteralPath $pkgDir -Recurse -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $pkgDir)
    Write-Log ("Extracted TOM NuGet to {0}" -f $pkgDir)
    Write-Host ">>> Extracted TOM NuGet"
    $lib = Get-TomNugetLibDir
    if (-not $lib) { throw "NuGet extract did not contain Microsoft.AnalysisServices.Tabular.dll under $tomHome" }
    return $lib
}

function Import-TomAssemblies {
    Write-Log 'Ensuring TOM assemblies (NuGet preferred)...'
    # Always ensure NuGet package exists first so we never depend on PBI bin shipping TOM.
    $dir = Install-TomFromNuget
    if (-not $dir) { $dir = Find-TomDirectory }
    if (-not $dir) {
        throw 'Microsoft.AnalysisServices.Tabular.dll not found after NuGet install.'
    }
    Write-Log ("Using TOM directory: {0}" -f $dir)
    $names = @(
        'Microsoft.AnalysisServices.Core.dll',
        'Microsoft.AnalysisServices.dll',
        'Microsoft.AnalysisServices.Tabular.dll'
    )
    foreach ($n in $names) {
        $dll = Join-Path $dir $n
        if (-not (Test-Path -LiteralPath $dll)) {
            Write-Log ("DLL not in folder (will try others): {0}" -f $dll) 'WARN'
            continue
        }
        Write-Log ("Loading {0}" -f $dll)
        try { Add-Type -Path $dll } catch {
            if ($_.Exception.Message -notmatch 'already exists|duplicate') { throw }
        }
    }
    $tabular = Join-Path $dir 'Microsoft.AnalysisServices.Tabular.dll'
    if (-not (Test-Path -LiteralPath $tabular)) {
        throw "Missing required DLL: $tabular"
    }
    try { Add-Type -Path $tabular } catch {
        if ($_.Exception.Message -notmatch 'already exists|duplicate') { throw }
    }
    Write-Log ("Loaded TOM from {0}" -f $dir)
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
            throw ("PBIDesktop exited while loading (pid {0}, code {1})." -f $Process.Id, $Process.ExitCode)
        }
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) { return }
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

function Read-MsmdsrvPortFile([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $text = if ($bytes.Length -ge 2 -and $bytes[1] -eq 0) {
        [System.Text.Encoding]::Unicode.GetString($bytes)
    } else {
        [System.IO.File]::ReadAllText($Path)
    }
    $text = $text.Trim().Trim([char]0)
    $port = 0
    if (-not [int]::TryParse($text, [ref]$port)) {
        throw "Could not parse AS port from $Path ('$text')"
    }
    return $port
}

function Wait-ModelPort([System.Diagnostics.Process]$Desktop, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $Desktop.Refresh()
        if ($Desktop.HasExited) { throw "PBIDesktop exited before model port (pid $($Desktop.Id))" }
        foreach ($p in Get-CimInstance Win32_Process -Filter "Name = 'msmdsrv.exe'" -ErrorAction SilentlyContinue) {
            if ([int]$p.ParentProcessId -ne $Desktop.Id) { continue }
            $cmd = [string]$p.CommandLine
            if ($cmd -match '-s\s+"([^"]+)"' -or $cmd -match '-s\s+(\S+)') {
                $portFile = Join-Path $Matches[1].TrimEnd('\') 'msmdsrv.port.txt'
                if (Test-Path -LiteralPath $portFile) {
                    $port = Read-MsmdsrvPortFile $portFile
                    Write-Log ("Model port {0} from {1}" -f $port, $portFile)
                    return $port
                }
            }
        }
        Start-Sleep -Seconds 3
    }
    throw "Timed out waiting for msmdsrv port after $($TimeoutSec)s"
}

function Invoke-TomFullRefresh([int]$Port) {
    Import-TomAssemblies
    $server = New-Object Microsoft.AnalysisServices.Tabular.Server
    try {
        $cs = 'Data Source=localhost:{0};Application Name=HorseShowsPbixSimple;Connect Timeout=120' -f $Port
        Write-Log ("TOM connect {0}" -f $cs)
        $server.Connect($cs)
        # Full model refresh against SQL can take a long time; default timeouts are too low.
        try { $server.Timeout = 7200 } catch { Write-Log ("Could not set server.Timeout: {0}" -f $_.Exception.Message) 'WARN' }
        if ($server.Databases.Count -lt 1) { throw "No tabular DB on localhost:$Port" }
        $db = $server.Databases[0]
        Write-Log ("TOM refresh database '{0}' (LastProcessed={1})" -f $db.Name, $db.LastProcessed)
        $tmsl = '{{ "refresh": {{ "type": "full", "objects": [ {{ "database": "{0}" }} ] }} }}' -f $db.Name
        Write-Log 'Starting full TMSL refresh NOW. This often takes 10-40+ minutes. Leave Power BI open; more log lines appear when it finishes.'
        Write-Host '>>> TMSL refresh running (can take a long time). Do not close Power BI.'
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $results = $server.Execute($tmsl)
        $sw.Stop()
        Write-Log ("TMSL Execute returned after {0:mm\:ss}" -f $sw.Elapsed)
        $errors = @()
        foreach ($result in @($results)) {
            foreach ($msg in @($result.Messages)) {
                $text = [string]$msg
                if ($msg.GetType().Name -match 'Error' -or $text -match '(?i)error|failed') {
                    $errors += $text
                } else {
                    Write-Log $text
                }
            }
        }
        if ($errors.Count -gt 0) { throw ("TMSL errors: {0}" -f ($errors -join ' | ')) }
        $db.Refresh()
        Write-Log ("TOM refresh done. LastProcessed={0}" -f $db.LastProcessed)
    }
    finally {
        if ($server.Connected) { $server.Disconnect() }
    }
}

function Get-UiaWindow([int]$ProcessId) {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcessId)
    return $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
}

function Invoke-UiaByName([System.Windows.Automation.AutomationElement]$Window, [string]$Name) {
    if (-not $Window) { return $false }
    $nameCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, $Name)
    $el = $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $nameCond)
    if (-not $el) { return $false }
    try {
        $pat = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $pat.Invoke()
        Write-Log ("UIA Invoke '{0}'" -f $Name)
        return $true
    } catch {
        Write-Log ("UIA Invoke '{0}' failed: {1}" -f $Name, $_.Exception.Message) 'WARN'
        return $false
    }
}

function Invoke-UiRefresh([System.Diagnostics.Process]$Process) {
    Add-Type -AssemblyName System.Windows.Forms
    Focus-ProcessWindow -Process $Process
    $win = $null
    try { $win = Get-UiaWindow -ProcessId $Process.Id } catch {
        Write-Log ("UIA window lookup failed: {0}" -f $_.Exception.Message) 'WARN'
    }
    if (Invoke-UiaByName -Window $win -Name 'Refresh') { return $true }

    Write-Log 'UIA Refresh not found; trying SendKeys Alt+H,R / F10 H R' 'WARN'
    foreach ($seq in @(
        { [System.Windows.Forms.SendKeys]::SendWait('%hr') },
        {
            [System.Windows.Forms.SendKeys]::SendWait('%')
            Start-Sleep -Milliseconds 800
            [System.Windows.Forms.SendKeys]::SendWait('h')
            Start-Sleep -Milliseconds 800
            [System.Windows.Forms.SendKeys]::SendWait('r')
        },
        {
            [System.Windows.Forms.SendKeys]::SendWait('{F10}')
            Start-Sleep -Milliseconds 800
            [System.Windows.Forms.SendKeys]::SendWait('h')
            Start-Sleep -Milliseconds 800
            [System.Windows.Forms.SendKeys]::SendWait('r')
        }
    )) {
        Focus-ProcessWindow -Process $Process
        & $seq
        Start-Sleep -Seconds 3
    }
    return $false
}

function Save-Pbix([System.Diagnostics.Process]$Process, [string]$Path, [datetime]$BeforeUtc, [int]$TimeoutSec) {
    Add-Type -AssemblyName System.Windows.Forms
    Focus-ProcessWindow -Process $Process
    $win = $null
    try { $win = Get-UiaWindow -ProcessId $Process.Id } catch { }
    if (-not (Invoke-UiaByName -Window $win -Name 'Save')) {
        Write-Log 'SendKeys Ctrl+S'
        [System.Windows.Forms.SendKeys]::SendWait('^s')
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        $after = (Get-Item -LiteralPath $Path -Force).LastWriteTimeUtc
        if ($after -gt $BeforeUtc) {
            Write-Log ("Saved. LastWrite={0:o}" -f $after)
            return $true
        }
    }
    return $false
}

function Find-UiaByName([System.Windows.Automation.AutomationElement]$Root, [string]$Name, [bool]$Exact = $true) {
    if (-not $Root) { return $null }
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    if ($Exact) {
        $cond = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, $Name)
        return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    }
    $all = $Root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($el in $all) {
        $n = [string]$el.Current.Name
        if ($n -and $n.IndexOf($Name, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $el }
    }
    return $null
}

function Invoke-UiaElement([System.Windows.Automation.AutomationElement]$Element, [string]$Label) {
    if (-not $Element) { return $false }
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    try {
        $pat = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $pat.Invoke()
        Write-Log ("UIA Invoke '{0}'" -f $Label)
        return $true
    } catch { }
    try {
        $sel = $Element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $sel.Select()
        Write-Log ("UIA Select '{0}'" -f $Label)
        return $true
    } catch { }
    try {
        # Fallback: set focus + Enter for list rows that lack Invoke/SelectionItem.
        $Element.SetFocus()
        Start-Sleep -Milliseconds 200
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
        Write-Log ("UIA Focus+Enter '{0}'" -f $Label)
        return $true
    } catch {
        Write-Log ("UIA action '{0}' failed: {1}" -f $Label, $_.Exception.Message) 'WARN'
        return $false
    }
}

function Get-PublishUiRoot([System.Diagnostics.Process]$Process) {
    # Prefer a dedicated dialog/window over the main ribbon (avoids re-hitting ribbon Publish).
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $pidCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $Process.Id)
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)
    $best = $null
    foreach ($w in $wins) {
        $n = [string]$w.Current.Name
        if ($n -match '(?i)publish|replace|power bi') { return $w }
        if (-not $best) { $best = $w }
    }
    if ($best) { return $best }
    try { return Get-UiaWindow -ProcessId $Process.Id } catch { return $null }
}

function Publish-Pbix(
    [System.Diagnostics.Process]$Process,
    [int]$TimeoutSec,
    [string]$WorkspaceName = 'My workspace'
) {
    # Desktop Publish sequence (do not steal focus in a loop):
    # 1) Home > Publish (once)
    # 2) Select workspace ("My workspace")
    # 3) Select / Publish in that dialog
    # 4) Replace overwrite (once)
    # 5) Got it when complete
    Add-Type -AssemblyName System.Windows.Forms
    Write-Log ("Publishing to Power BI Service (workspace='{0}')..." -f $WorkspaceName)
    Write-Host '>>> Publishing to Power BI Service. Leave dialogs alone unless sign-in is required.'

    # Focus once to start Publish only.
    Focus-ProcessWindow -Process $Process
    $win = $null
    try { $win = Get-UiaWindow -ProcessId $Process.Id } catch {
        Write-Log ("UIA window lookup failed before Publish: {0}" -f $_.Exception.Message) 'WARN'
    }
    if (-not (Invoke-UiaByName -Window $win -Name 'Publish')) {
        Write-Log 'UIA Publish not found; trying key tips Alt+H, P, U' 'WARN'
        Focus-ProcessWindow -Process $Process
        [System.Windows.Forms.SendKeys]::SendWait('%')
        Start-Sleep -Milliseconds 600
        [System.Windows.Forms.SendKeys]::SendWait('h')
        Start-Sleep -Milliseconds 800
        [System.Windows.Forms.SendKeys]::SendWait('p')
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait('u')
    }
    Start-Sleep -Seconds 2

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $stage = 'workspace'   # workspace -> select -> replace -> uploading -> done
    $workspaceSelected = $false
    $selectClicked = $false
    $replaceClicked = $false
    $gotItClicked = $false
    $uploadIdle = 0

    while ((Get-Date) -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) {
            Write-Log 'PBIDesktop exited during Publish.' 'ERROR'
            return $false
        }

        # Do NOT Focus-ProcessWindow here - that steals the user's Cursor/other windows.
        $ui = Get-PublishUiRoot -Process $Process
        if (-not $ui) {
            Start-Sleep -Seconds 2
            continue
        }

        if ($stage -eq 'workspace' -and -not $workspaceSelected) {
            $ws = Find-UiaByName -Root $ui -Name $WorkspaceName -Exact $true
            if (-not $ws) { $ws = Find-UiaByName -Root $ui -Name $WorkspaceName -Exact $false }
            if ($ws -and (Invoke-UiaElement -Element $ws -Label ("workspace:{0}" -f $WorkspaceName))) {
                $workspaceSelected = $true
                $stage = 'select'
                Start-Sleep -Seconds 1
                continue
            }
        }

        if (($stage -eq 'select' -or ($stage -eq 'workspace' -and $workspaceSelected)) -and -not $selectClicked) {
            foreach ($btn in @('Select', 'Publish')) {
                $el = Find-UiaByName -Root $ui -Name $btn -Exact $true
                # Avoid ribbon Publish: only click if we are past workspace selection or name is Select.
                if ($btn -eq 'Publish' -and -not $workspaceSelected) { continue }
                if ($el -and (Invoke-UiaElement -Element $el -Label $btn)) {
                    $selectClicked = $true
                    $stage = 'replace'
                    Start-Sleep -Seconds 2
                    break
                }
            }
            if ($selectClicked) { continue }
        }

        if ($stage -eq 'replace' -and -not $replaceClicked) {
            foreach ($btn in @('Replace', 'Replace it')) {
                $el = Find-UiaByName -Root $ui -Name $btn -Exact $true
                if (-not $el) { $el = Find-UiaByName -Root $ui -Name $btn -Exact $false }
                if ($el -and (Invoke-UiaElement -Element $el -Label $btn)) {
                    $replaceClicked = $true
                    $stage = 'uploading'
                    Write-Log 'Replace confirmed; waiting for upload/success dialog (no focus steal)...'
                    Start-Sleep -Seconds 3
                    break
                }
            }
            if ($replaceClicked) { continue }
            # Replace dialog may take a moment after Select.
            $uploadIdle++
            if ($uploadIdle -gt 15 -and $selectClicked) {
                # Some tenants skip Replace if first publish; treat as uploading.
                Write-Log 'No Replace dialog yet; assuming upload in progress.' 'WARN'
                $stage = 'uploading'
                $uploadIdle = 0
            }
        }

        if ($stage -eq 'uploading' -and -not $gotItClicked) {
            foreach ($btn in @('Got it', 'Close')) {
                $el = Find-UiaByName -Root $ui -Name $btn -Exact $true
                if ($el -and (Invoke-UiaElement -Element $el -Label $btn)) {
                    $gotItClicked = $true
                    Write-Log 'Publish success dialog dismissed.'
                    return $true
                }
            }
            $success = Find-UiaByName -Root $ui -Name 'Successfully published' -Exact $false
            if ($success) {
                $uploadIdle++
                # Visible success text but button not found yet.
            } else {
                $uploadIdle++
            }
            if ($uploadIdle -gt 0 -and ($uploadIdle % 30) -eq 0) {
                Write-Log ("Still waiting for success dialog after Replace (poll={0})..." -f $uploadIdle)
            }
        }

        Start-Sleep -Seconds 2
    }

    Write-Log ("Publish timed out after {0}s (workspace={1} select={2} replace={3} gotIt={4})." -f `
        $TimeoutSec, $workspaceSelected, $selectClicked, $replaceClicked, $gotItClicked) 'ERROR'
    return $false
}

# ---- main ----
Write-Log '==== simple refresh start ===='
Write-Log ("PSVersion={0} User={1}\{2}" -f $PSVersionTable.PSVersion, $env:USERDOMAIN, $env:USERNAME)
Write-Log ("Pbix={0}" -f $PbixPath)

if ($env:OS -ne 'Windows_NT') { throw 'Must run on Windows with Power BI Desktop.' }
if (-not (Test-Path -LiteralPath $PbixPath)) { throw "Missing pbix: $PbixPath" }

$item = Get-Item -LiteralPath $PbixPath -Force
Write-Log ("Pbix size={0:N0} LastWrite={1:o}" -f $item.Length, $item.LastWriteTimeUtc)
if ($item.Length -lt 1MB) {
    throw ("HorseShows.pbix is only {0:N0} bytes (LFS/OneDrive stub). git lfs pull --include=`"PowerBI/HorseShows.pbix`" then Always keep on this device." -f $item.Length)
}

$beforeWrite = $item.LastWriteTimeUtc
$proc = Get-OpenPbixProcess $PbixPath

if ($PublishOnly) {
    Write-Log 'PublishOnly: skipping refresh/save.'
    if (-not $proc) {
        throw 'PublishOnly requires HorseShows.pbix already open in Power BI Desktop.'
    }
    Wait-MainWindow -Process $proc -TimeoutSec ([Math]::Min(90, $LoadTimeoutSec))
    $published = Publish-Pbix -Process $proc -TimeoutSec $PublishTimeoutSec -WorkspaceName $WorkspaceName
    if (-not $published) {
        Write-Log 'PublishOnly failed or timed out.' 'ERROR'
        Write-Log '==== simple refresh FAILED (publish) ====' 'ERROR'
        exit 3
    }
    Write-Log '==== PublishOnly done (Desktop left open) ===='
    exit 0
}

if (-not $proc) {
    $exe = Get-PbiExe
    Write-Log ("Opening via cmd start: {0}" -f $exe)
    $arg = '/c start "" "' + $exe + '" "' + $PbixPath + '"'
    Start-Process -FilePath 'cmd.exe' -ArgumentList $arg -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds([Math]::Min(90, $LoadTimeoutSec))
    while ((Get-Date) -lt $deadline -and -not $proc) {
        Start-Sleep -Seconds 2
        $proc = Get-OpenPbixProcess $PbixPath
        if (-not $proc) {
            $proc = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue |
                Sort-Object StartTime -Descending | Select-Object -First 1
        }
    }
    if (-not $proc) {
        Write-Log 'Fallback Invoke-Item' 'WARN'
        Invoke-Item -LiteralPath $PbixPath
        Start-Sleep -Seconds 10
        $proc = Get-OpenPbixProcess $PbixPath
        if (-not $proc) {
            $proc = Get-Process -Name PBIDesktop -ErrorAction SilentlyContinue |
                Sort-Object StartTime -Descending | Select-Object -First 1
        }
    }
    if (-not $proc) { throw 'Power BI Desktop did not start.' }
    Write-Log ("Started pid {0}; waiting for window..." -f $proc.Id)
    Wait-MainWindow -Process $proc -TimeoutSec $LoadTimeoutSec
}
else {
    Write-Log ("Already open pid {0}" -f $proc.Id)
    Wait-MainWindow -Process $proc -TimeoutSec ([Math]::Min(90, $LoadTimeoutSec))
}

$proc.Refresh()
if ($proc.HasExited) { throw 'Power BI Desktop exited before refresh.' }

$refreshed = $false
if (-not $UiOnly) {
    try {
        Write-Log 'Waiting for Analysis Services model port...'
        $port = Wait-ModelPort -Desktop $proc -TimeoutSec $LoadTimeoutSec
        Invoke-TomFullRefresh -Port $port
        $refreshed = $true
    } catch {
        Write-Log ("TOM refresh failed: {0}" -f $_.Exception.Message) 'WARN'
        Write-Log 'Falling back to UI Refresh click / SendKeys' 'WARN'
    }
}

if (-not $refreshed) {
    [void](Invoke-UiRefresh -Process $proc)
    Write-Log ("Waiting {0}s after UI refresh keys/click..." -f $RefreshWaitSec)
    Start-Sleep -Seconds $RefreshWaitSec
}

$proc.Refresh()
if ($proc.HasExited) { throw 'Power BI Desktop exited during/after refresh.' }

$saved = Save-Pbix -Process $proc -Path $PbixPath -BeforeUtc $beforeWrite -TimeoutSec 180
$after = Get-Item -LiteralPath $PbixPath -Force
Write-Log ("Pbix LastWrite before={0:o} after={1:o} size={2:N0} tom={3} saved={4}" -f $beforeWrite, $after.LastWriteTimeUtc, $after.Length, $refreshed, $saved)

if (-not $refreshed -and -not $saved) {
    Write-Log 'Refresh and save both unverified. Check Desktop for dialogs.' 'ERROR'
    Write-Log '==== simple refresh FAILED ====' 'ERROR'
    exit 1
}
if ($refreshed -and -not $saved) {
    Write-Log 'TOM refresh OK but file timestamp unchanged - save manually (Ctrl+S) once.' 'WARN'
    Write-Log '==== simple refresh finished with WARN ====' 'WARN'
    exit 2
}

$published = $false
if ($SkipPublish) {
    Write-Log 'SkipPublish set; not publishing to Power BI Service.'
} else {
    $proc.Refresh()
    if ($proc.HasExited) {
        Write-Log 'PBIDesktop exited before Publish.' 'ERROR'
        Write-Log '==== simple refresh FAILED (no publish) ====' 'ERROR'
        exit 1
    }
    $published = Publish-Pbix -Process $proc -TimeoutSec $PublishTimeoutSec -WorkspaceName $WorkspaceName
    if (-not $published) {
        Write-Log 'Refresh/save OK but Publish failed or timed out.' 'ERROR'
        Write-Log '==== simple refresh FAILED (publish) ====' 'ERROR'
        exit 3
    }
    Write-Log 'Publish to Power BI Service completed (UI path).'
}

Write-Log ("==== simple refresh done (tom={0} saved={1} published={2}; Desktop left open) ====" -f $refreshed, $saved, $published)
exit 0
