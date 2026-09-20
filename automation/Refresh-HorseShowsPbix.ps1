<#
.SYNOPSIS
    Refresh PowerBI\HorseShows.pbix from the local HorseShows SQL Server.

.DESCRIPTION
    Power BI Desktop does not expose a supported refresh API. This runner opens the pbix,
    connects to the local Analysis Services instance Desktop hosts, issues a full TMSL
    refresh, then Ctrl+S so the file on disk matches the in-memory model.

    It is meant to be called by the local Cursor agent (Run-HorseShowsPbixRefreshAgent.ps1)
    or directly. It must run in an interactive Windows session on the machine that has
    Power BI Desktop and the HorseShows database.

.EXAMPLE
    .\Refresh-HorseShowsPbix.ps1
    .\Refresh-HorseShowsPbix.ps1 -DryRun
    .\Refresh-HorseShowsPbix.ps1 -TimeoutMinutes 60
    .\Refresh-HorseShowsPbix.ps1 -CloseWhenDone
#>
[CmdletBinding()]
param(
    [string]$PbixPath,

    [ValidateRange(5, 180)]
    [int]$TimeoutMinutes = 45,

    # Default is to leave Power BI Desktop open after refresh. Pass -CloseWhenDone
    # only when this run launched Desktop and you want it closed afterward.
    [switch]$CloseWhenDone,

    # Deprecated alias for leaving Desktop open (now the default).
    [switch]$KeepOpen,

    [switch]$SkipSave,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $PSScriptRoot
if ($env:RESULTS_AUTOMATION_HOME) {
    $AutomationHome = $env:RESULTS_AUTOMATION_HOME
}
elseif ($env:OS -eq 'Windows_NT') {
    $AutomationHome = 'C:\Users\mw\ResultsAutomation'
}
else {
    $AutomationHome = $null
}
$script:LogFile = $null
$script:LaunchedDesktop = $false
$script:DesktopProcess = $null
$script:UsedSharedLog = $false

function Get-RefreshTempDir {
    if ($env:TEMP) { return $env:TEMP }
    if ($env:TMPDIR) { return $env:TMPDIR }
    return [System.IO.Path]::GetTempPath()
}

function Initialize-RefreshLog {
    $common = if ($AutomationHome) { Join-Path $AutomationHome 'Common.ps1' } else { $null }
    if ($common -and (Test-Path -LiteralPath $common)) {
        . $common
        $script:UsedSharedLog = $true
        if (Get-Command Start-RunLog -ErrorAction SilentlyContinue) {
            Start-RunLog -Name 'horse_shows_pbix_refresh' | Out-Null
        }
        return
    }

    $logDir = Join-Path (Get-RefreshTempDir) 'HorseShowsPbixRefresh'
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }
    $script:LogFile = Join-Path $logDir ('refresh-{0:yyyyMMdd-HHmmss}.log' -f (Get-Date))
}

function Write-RefreshLog {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR')]
        [string]$Level = 'INFO'
    )
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    if ($script:LogFile) {
        Add-Content -LiteralPath $script:LogFile -Value $line
    }
    if ($script:UsedSharedLog -and (Get-Command Write-Log -ErrorAction SilentlyContinue)) {
        Write-Log $Message $Level
    }
}

function Get-ResolvedPbixPath {
    if ($PbixPath) { return (Resolve-Path -LiteralPath $PbixPath).Path }
    $candidate = Join-Path (Join-Path $Repo 'PowerBI') 'HorseShows.pbix'
    if (-not (Test-Path -LiteralPath $candidate)) {
        throw "HorseShows.pbix not found at $candidate"
    }
    return (Resolve-Path -LiteralPath $candidate).Path
}

function Test-GitLfsPointer {
    param([Parameter(Mandatory)][string]$Path)
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -gt 1024) { return $false }
    $first = Get-Content -LiteralPath $Path -TotalCount 1 -ErrorAction SilentlyContinue
    return [bool]($first -and $first -like 'version https://git-lfs.github.com/*')
}

function Assert-PbixReadyToOpen {
    param([Parameter(Mandatory)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    if (Test-GitLfsPointer -Path $Path) {
        throw "HorseShows.pbix is still a Git LFS pointer ($($item.Length) bytes). Run: git lfs pull --include=`"PowerBI/HorseShows.pbix`""
    }
    # This report is ~442 MB. Tiny files mean OneDrive has not hydrated the real pbix yet.
    if ($item.Length -lt 50MB) {
        throw ("HorseShows.pbix is only {0:N0} bytes — too small to be the real report. If it is on OneDrive, right-click the file → Always keep on this device, wait for the full download, then retry." -f $item.Length)
    }
    # Cloud-only / not fully recalled attributes (Windows / OneDrive).
    try {
        $attrs = [int]$item.Attributes
        # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
        if (($attrs -band 0x00400000) -ne 0) {
            throw "HorseShows.pbix is still an OneDrive cloud placeholder. Right-click → Always keep on this device, wait until Size on disk is hundreds of MB, then retry."
        }
    }
    catch [System.Management.Automation.RuntimeException] {
        throw
    }
    catch {
        # Attribute probe is best-effort on non-Windows.
    }
}

function Start-PowerBIDesktopWithPbix {
    param(
        [Parameter(Mandatory)][string]$DesktopExe,
        [Parameter(Mandatory)][string]$PbixPath
    )
    # Do NOT use Start-Process -ArgumentList @(...) with an OneDrive path.
    # Windows PowerShell 5.1 splits on the space in "OneDrive - timberwilde.net",
    # so PBIDesktop only receives C:\Users\mw\OneDrive and never loads the pbix.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $DesktopExe
    $psi.Arguments = '"' + $PbixPath + '"'
    $psi.WorkingDirectory = [System.IO.Path]::GetDirectoryName($PbixPath)
    $psi.UseShellExecute = $true
    Write-RefreshLog ("Starting: {0} {1}" -f $DesktopExe, $psi.Arguments)
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc) {
        throw "Failed to start Power BI Desktop for $PbixPath"
    }
    return $proc
}

function Get-PowerBIDesktopExe {
    if ($env:OS -ne 'Windows_NT') { return $null }
    $candidates = @(
        (Join-Path ${env:ProgramFiles} 'Microsoft Power BI Desktop\bin\PBIDesktop.exe'),
        (Join-Path ${env:ProgramFiles} 'Microsoft Power BI Desktop\PBIDesktop.exe'),
        (Join-Path ${env:LocalAppData} 'Microsoft\WindowsApps\PBIDesktop.exe')
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }

    $cmd = Get-Command PBIDesktop.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    Get-ChildItem -Path "$env:LOCALAPPDATA\Packages" -Filter 'Microsoft.MicrosoftPowerBIDesktop_*' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object {
            Get-ChildItem -Path $_.FullName -Filter 'PBIDesktop.exe' -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
        } |
        Where-Object { $_ } |
        Select-Object -First 1
}

function Get-AnalysisServicesWorkspaceRoots {
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop\AnalysisServicesWorkspaces')
    )
    Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Packages') -Filter 'Microsoft.MicrosoftPowerBIDesktop_*' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object {
            $roots += (Join-Path $_.FullName 'LocalState\AnalysisServicesWorkspaces')
        }
    $roots | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
}

function Read-MsmdsrvPortFile {
    param([Parameter(Mandatory)][string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $text = if ($bytes.Length -ge 2 -and $bytes[1] -eq 0) {
        [System.Text.Encoding]::Unicode.GetString($bytes)
    }
    else {
        [System.IO.File]::ReadAllText($Path)
    }
    $text = $text.Trim().Trim([char]0)
    $port = 0
    if (-not [int]::TryParse($text, [ref]$port)) {
        throw "Could not parse Analysis Services port from $Path (content '$text')"
    }
    return $port
}

function Get-Win32Processes {
    param([Parameter(Mandatory)][string]$Name)
    Get-CimInstance Win32_Process -Filter "Name = '$Name'" -ErrorAction SilentlyContinue
}

function Get-OpenPowerBIDesktopForPbix {
    param([Parameter(Mandatory)][string]$TargetPbix)
    $needle = $TargetPbix.Replace('/', '\').ToLowerInvariant()
    foreach ($proc in @(Get-Win32Processes -Name 'PBIDesktop.exe')) {
        $cmd = [string]$proc.CommandLine
        if (-not $cmd) { continue }
        if ($cmd.ToLowerInvariant().Contains($needle)) {
            try { return Get-Process -Id $proc.ProcessId -ErrorAction Stop } catch { }
        }
    }
    $null
}

function Get-ChildMsmdsrv {
    param([Parameter(Mandatory)][int]$ParentPid)
    foreach ($proc in @(Get-Win32Processes -Name 'msmdsrv.exe')) {
        if ([int]$proc.ParentProcessId -eq $ParentPid) { return $proc }
    }
    $null
}

function Get-PortFromMsmdsrvProcess {
    param($Msmdsrv)
    if (-not $Msmdsrv) { return $null }
    $cmd = [string]$Msmdsrv.CommandLine
    if ($cmd -match '-s\s+"([^"]+)"' -or $cmd -match '-s\s+(\S+)') {
        $dataDir = $Matches[1].TrimEnd('\')
        $portFile = Join-Path $dataDir 'msmdsrv.port.txt'
        if (Test-Path -LiteralPath $portFile) {
            return Read-MsmdsrvPortFile -Path $portFile
        }
    }
    $null
}

function Get-NewestWorkspacePort {
    $files = foreach ($root in @(Get-AnalysisServicesWorkspaceRoots)) {
        Get-ChildItem -Path $root -Filter 'msmdsrv.port.txt' -Recurse -ErrorAction SilentlyContinue
    }
    $newest = $files | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newest) { return Read-MsmdsrvPortFile -Path $newest.FullName }
    $null
}

function Wait-ForDesktopModelPort {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Desktop,
        [Parameter(Mandatory)][datetime]$Deadline
    )
    do {
        $desktop.Refresh()
        if ($desktop.HasExited) {
            throw "Power BI Desktop exited before the model loaded (pid $($desktop.Id))"
        }
        $msmdsrv = Get-ChildMsmdsrv -ParentPid $desktop.Id
        $port = Get-PortFromMsmdsrvProcess -Msmdsrv $msmdsrv
        if (-not $port) {
            $running = @(Get-Win32Processes -Name 'msmdsrv.exe')
            if ($running.Count -eq 1) { $port = Get-NewestWorkspacePort }
        }
        if ($port) { return $port }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $Deadline)

    throw "Timed out waiting for the Power BI Desktop Analysis Services port after launching pid $($desktop.Id)"
}

function Import-TabularObjectModel {
    $dllNames = @(
        'Microsoft.AnalysisServices.Core.dll',
        'Microsoft.AnalysisServices.dll',
        'Microsoft.AnalysisServices.Tabular.dll'
    )
    $searchRoots = @(
        (Join-Path ${env:ProgramFiles} 'Microsoft Power BI Desktop\bin'),
        (Join-Path (Get-RefreshTempDir) 'tom_nuget/Microsoft.AnalysisServices.retail.amd64/lib/net45'),
        (Join-Path (Get-RefreshTempDir) 'tom_nuget/Microsoft.AnalysisServices.retail.amd64/lib/net8.0')
    )
    Get-ChildItem -Path "$env:LOCALAPPDATA\Packages" -Filter 'Microsoft.MicrosoftPowerBIDesktop_*' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { $searchRoots += (Join-Path $_.FullName 'LocalCache\Local\Microsoft\Power BI Desktop\bin') }

    foreach ($root in $searchRoots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        $core = Join-Path $root 'Microsoft.AnalysisServices.Core.dll'
        $tabular = Join-Path $root 'Microsoft.AnalysisServices.Tabular.dll'
        if ((Test-Path -LiteralPath $core) -and (Test-Path -LiteralPath $tabular)) {
            foreach ($name in $dllNames) {
                $dll = Join-Path $root $name
                if (-not (Test-Path -LiteralPath $dll)) { continue }
                try {
                    Add-Type -Path $dll
                }
                catch {
                    if ($_.Exception.Message -notmatch 'already exists|duplicate') { throw }
                }
            }
            Write-RefreshLog "Loaded TOM assemblies from $root"
            return $root
        }
    }
    throw 'Microsoft.AnalysisServices.Tabular.dll not found. Install Power BI Desktop (recommended) or nuget package Microsoft.AnalysisServices.retail.amd64 under %TEMP%\tom_nuget.'
}

function Invoke-TabularFullRefresh {
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][datetime]$Deadline
    )

    $server = New-Object Microsoft.AnalysisServices.Tabular.Server
    try {
        $remaining = [int][Math]::Max(60, ($Deadline - (Get-Date)).TotalSeconds)
        $cs = 'Data Source=localhost:{0};Application Name=HorseShowsPbixRefresh;Connect Timeout={1}' -f $Port, $remaining
        Write-RefreshLog "Connecting to localhost:$Port"
        $server.Connect($cs)
        if ($server.Databases.Count -lt 1) {
            throw "No tabular database is loaded on localhost:$Port"
        }
        $db = $server.Databases[0]
        $before = $db.LastProcessed
        Write-RefreshLog ("Model '{0}' LastProcessed before refresh: {1}" -f $db.Name, $before)

        $tmsl = '{{ "refresh": {{ "type": "full", "objects": [ {{ "database": "{0}" }} ] }} }}' -f $db.Name
        Write-RefreshLog 'Starting full TMSL refresh'
        $results = $server.Execute($tmsl)
        $errors = New-Object System.Collections.Generic.List[string]
        foreach ($result in @($results)) {
            foreach ($msg in @($result.Messages)) {
                $text = [string]$msg
                if ($msg.GetType().Name -match 'Error' -or $text -match '(?i)error|failed') {
                    $errors.Add($text) | Out-Null
                }
                else {
                    Write-RefreshLog $text
                }
            }
        }
        if ($errors.Count -gt 0) {
            throw ("TMSL refresh reported error(s): {0}" -f ($errors -join ' | '))
        }

        $db.Refresh()
        $after = $db.LastProcessed
        Write-RefreshLog ("Model '{0}' LastProcessed after refresh: {1}" -f $db.Name, $after)
        return [pscustomobject]@{
            Database     = $db.Name
            Port         = $Port
            LastProcessed = $after
        }
    }
    finally {
        if ($server.Connected) { $server.Disconnect() }
    }
}

function Save-PowerBIDesktopPbix {
    param(
        [Parameter(Mandatory)][System.Diagnostics.Process]$Desktop,
        [Parameter(Mandatory)][string]$TargetPbix,
        [Parameter(Mandatory)][datetime]$Deadline
    )

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName Microsoft.VisualBasic

    $before = (Get-Item -LiteralPath $TargetPbix).LastWriteTimeUtc
    Write-RefreshLog ("Saving pbix (LastWriteTimeUtc {0:o})" -f $before)

    do {
        $desktop.Refresh()
        if ($desktop.HasExited) {
            throw 'Power BI Desktop exited before the pbix could be saved'
        }
        if ($desktop.MainWindowHandle -ne [IntPtr]::Zero) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $Deadline)

    [Microsoft.VisualBasic.Interaction]::AppActivate($desktop.Id) | Out-Null
    Start-Sleep -Milliseconds 800
    [System.Windows.Forms.SendKeys]::SendWait('^s')

    do {
        Start-Sleep -Seconds 2
        $after = (Get-Item -LiteralPath $TargetPbix).LastWriteTimeUtc
        if ($after -gt $before) {
            Write-RefreshLog ("Saved pbix (LastWriteTimeUtc {0:o})" -f $after)
            return $after
        }
    } while ((Get-Date) -lt $Deadline)

    throw "Ctrl+S did not update $TargetPbix before the timeout. Leave Power BI Desktop open and save manually if the in-memory refresh succeeded."
}

function Save-LastRunStatus {
    param([Parameter(Mandatory)]$Status)
    $json = $Status | ConvertTo-Json -Depth 6
    $targets = @()
    if ($AutomationHome -and (Test-Path -LiteralPath $AutomationHome)) {
        $stateDir = Join-Path $AutomationHome 'state'
        if (-not (Test-Path -LiteralPath $stateDir)) {
            New-Item -ItemType Directory -Path $stateDir | Out-Null
        }
        $targets += (Join-Path $stateDir 'horse_shows_pbix_refresh.json')
    }
    if ($script:LogFile) {
        $targets += (Join-Path (Split-Path -Parent $script:LogFile) 'last-run.json')
    }
    foreach ($path in $targets) {
        Set-Content -LiteralPath $path -Value $json -Encoding UTF8
        Write-RefreshLog "Wrote run status $path"
    }
}

Initialize-RefreshLog
$exitCode = 1
$resolvedPbix = $null
$desktopExe = $null
$status = [ordered]@{
    StartedUtc    = [datetime]::UtcNow
    Success       = $false
    PbixPath      = $null
    Port          = $null
    Database      = $null
    LastProcessed = $null
    LastWriteTime = $null
    LogFile       = $script:LogFile
    Error         = $null
}

try {
    $resolvedPbix = Get-ResolvedPbixPath
    $status.PbixPath = $resolvedPbix
    $desktopExe = Get-PowerBIDesktopExe
    $isPointer = Test-GitLfsPointer -Path $resolvedPbix
    $fileInfo = Get-Item -LiteralPath $resolvedPbix
    $runningOnWindows = ($env:OS -eq 'Windows_NT')

    Write-RefreshLog "Repo:    $Repo"
    Write-RefreshLog "Pbix:    $resolvedPbix"
    Write-RefreshLog ("Size:    {0:N0} bytes, LastWriteTime {1:o}" -f $fileInfo.Length, $fileInfo.LastWriteTimeUtc)
    Write-RefreshLog ("Desktop: {0}" -f $(if ($desktopExe) { $desktopExe } else { '(not found)' }))

    if (-not $runningOnWindows) {
        $msg = 'Refresh-HorseShowsPbix.ps1 must run on Windows with Power BI Desktop'
        if (-not $DryRun) { throw $msg }
        Write-RefreshLog $msg 'WARN'
    }
    if ($isPointer) {
        $msg = 'HorseShows.pbix is still a Git LFS pointer. Run: git lfs pull --include="PowerBI/HorseShows.pbix"'
        if (-not $DryRun) { throw $msg }
        Write-RefreshLog $msg 'WARN'
    }
    if (-not $desktopExe) {
        $msg = 'Power BI Desktop was not found. Install it, then re-run.'
        if (-not $DryRun) { throw $msg }
        Write-RefreshLog $msg 'WARN'
    }

    if ($DryRun) {
        Write-RefreshLog 'Dry run: paths resolved, no refresh started'
        $status.Success = $true
        $exitCode = 0
    }
    else {

    Assert-PbixReadyToOpen -Path $resolvedPbix

    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    $existing = Get-OpenPowerBIDesktopForPbix -TargetPbix $resolvedPbix
    if ($existing) {
        Write-RefreshLog ("Reusing open Power BI Desktop pid {0}" -f $existing.Id)
        $script:DesktopProcess = $existing
        $script:LaunchedDesktop = $false
    }
    else {
        Write-RefreshLog "Launching Power BI Desktop with fully-quoted pbix path"
        $script:DesktopProcess = Start-PowerBIDesktopWithPbix -DesktopExe $desktopExe -PbixPath $resolvedPbix
        $script:LaunchedDesktop = $true
        # Large import models need time before msmdsrv publishes a port.
        Write-RefreshLog 'Waiting 15s for Power BI Desktop to begin loading the pbix...'
        Start-Sleep -Seconds 15
    }

    $port = Wait-ForDesktopModelPort -Desktop $script:DesktopProcess -Deadline $deadline
    $status.Port = $port
    Write-RefreshLog "Analysis Services port $port"

    Import-TabularObjectModel | Out-Null
    $refresh = Invoke-TabularFullRefresh -Port $port -Deadline $deadline
    $status.Database = $refresh.Database
    $status.LastProcessed = $refresh.LastProcessed

    if (-not $SkipSave) {
        $status.LastWriteTime = Save-PowerBIDesktopPbix -Desktop $script:DesktopProcess -TargetPbix $resolvedPbix -Deadline $deadline
    }
    else {
        Write-RefreshLog 'SkipSave set; in-memory model was refreshed but the pbix was not saved'
        $status.LastWriteTime = (Get-Item -LiteralPath $resolvedPbix).LastWriteTimeUtc
    }

        $status.Success = $true
        $exitCode = 0
        Write-RefreshLog 'HorseShows.pbix refresh succeeded'
    }
}
catch {
    $status.Error = $_.Exception.Message
    Write-RefreshLog $_.Exception.Message 'ERROR'
    if ($_.ScriptStackTrace) { Write-RefreshLog $_.ScriptStackTrace 'ERROR' }
    $exitCode = 1
}
finally {
    if ($script:LaunchedDesktop -and $script:DesktopProcess -and -not $script:DesktopProcess.HasExited -and $CloseWhenDone -and -not $KeepOpen) {
        Write-RefreshLog ("Closing Power BI Desktop pid {0}" -f $script:DesktopProcess.Id)
        try {
            $script:DesktopProcess.CloseMainWindow() | Out-Null
            if (-not $script:DesktopProcess.WaitForExit(20000)) {
                Stop-Process -Id $script:DesktopProcess.Id -ErrorAction SilentlyContinue
            }
        }
        catch {
            Write-RefreshLog ("Could not close Power BI Desktop: {0}" -f $_.Exception.Message) 'WARN'
        }
    }
    elseif ($script:LaunchedDesktop -and $script:DesktopProcess -and -not $script:DesktopProcess.HasExited) {
        Write-RefreshLog ("Leaving Power BI Desktop open (pid {0}). Pass -CloseWhenDone to close it." -f $script:DesktopProcess.Id)
    }
    $status.FinishedUtc = [datetime]::UtcNow
    try { Save-LastRunStatus -Status ([pscustomobject]$status) } catch { }
    if ($script:UsedSharedLog -and (Get-Command Complete-RunLog -ErrorAction SilentlyContinue)) {
        try { Complete-RunLog | Out-Null } catch { }
    }
}

# When launched via & from the space-free ResultsAutomation runner, do not
# exit the parent process. Callers set PBIX_REFRESH_NO_EXIT=1.
if ($env:PBIX_REFRESH_NO_EXIT -eq '1') {
    return $exitCode
}
exit $exitCode

