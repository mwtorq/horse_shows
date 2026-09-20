<#
.SYNOPSIS
    Local Cursor agent run that refreshes PowerBI\HorseShows.pbix.

.DESCRIPTION
    Launches Cursor CLI in headless mode against this repo with the pbix-refresh
    prompt. The agent follows .cursor/skills/refresh-horseshows-pbix and runs
    Refresh-HorseShowsPbix.ps1.

    If Cursor CLI is not installed or not authenticated, this wrapper falls back
    to the refresh script so the 8-hour schedule still updates the file.

    Never launches powershell -File with a full OneDrive path. Nested refresh
    runs use WorkingDirectory + relative -File (.\Refresh-HorseShowsPbix.ps1).
    Windows PowerShell 5.1 / Task Scheduler both split on the space in
    "OneDrive - timberwilde.net".

.EXAMPLE
    .\Run-HorseShowsPbixRefreshAgent.ps1
    .\Run-HorseShowsPbixRefreshAgent.ps1 -DryRun
    .\Run-HorseShowsPbixRefreshAgent.ps1 -SkipAgent
#>
[CmdletBinding()]
param(
    [switch]$SkipAgent,
    [switch]$DryRun,

    [ValidateRange(5, 180)]
    [int]$TimeoutMinutes = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $PSScriptRoot
$PromptFile = Join-Path $PSScriptRoot 'HorseShowsPbixRefresh.prompt.txt'
$RefreshScript = Join-Path $PSScriptRoot 'Refresh-HorseShowsPbix.ps1'
if ($env:RESULTS_AUTOMATION_HOME) {
    $AutomationHome = $env:RESULTS_AUTOMATION_HOME
}
elseif ($env:OS -eq 'Windows_NT') {
    $AutomationHome = 'C:\Users\mw\ResultsAutomation'
}
else {
    $AutomationHome = $null
}

function Write-AgentLog {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR')]
        [string]$Level = 'INFO'
    )
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    if ($script:LogFile) { Add-Content -LiteralPath $script:LogFile -Value $line }
    if (Get-Command Write-Log -ErrorAction SilentlyContinue) { Write-Log $Message $Level }
}

$common = if ($AutomationHome) { Join-Path $AutomationHome 'Common.ps1' } else { $null }
$script:LogFile = $null
if ($common -and (Test-Path -LiteralPath $common)) {
    . $common
    if (Get-Command Start-RunLog -ErrorAction SilentlyContinue) {
        Start-RunLog -Name 'horse_shows_pbix_refresh_agent' | Out-Null
    }
}
else {
    $tempRoot = if ($env:TEMP) { $env:TEMP } elseif ($env:TMPDIR) { $env:TMPDIR } else { [System.IO.Path]::GetTempPath() }
    $logDir = Join-Path $tempRoot 'HorseShowsPbixRefresh'
    if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $script:LogFile = Join-Path $logDir ('agent-{0:yyyyMMdd-HHmmss}.log' -f (Get-Date))
}

function Get-CursorAgentExe {
    foreach ($name in @('agent', 'agent.exe')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    $homeDir = if ($env:USERPROFILE) { $env:USERPROFILE } else { $env:HOME }
    $candidates = @()
    if ($homeDir) {
        $candidates += (Join-Path $homeDir '.local/bin/agent.exe')
        $candidates += (Join-Path $homeDir '.local/bin/agent')
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA 'cursor-agent/agent.exe')
        $candidates += (Join-Path $env:LOCALAPPDATA 'Programs/cursor-agent/agent.exe')
    }
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    $null
}

function Invoke-DirectRefresh {
    param([string]$Reason)
    if ($Reason) { Write-AgentLog $Reason 'WARN' }

    # Never Start-Process powershell -File against an OneDrive path (spaces break
    # -File). Call the refresh script in-process with PBIX_REFRESH_NO_EXIT=1.
    $refreshScript = Join-Path $PSScriptRoot 'Refresh-HorseShowsPbix.ps1'
    Write-AgentLog ("Running refresh in-process: {0}" -f $refreshScript)
    $prior = $env:PBIX_REFRESH_NO_EXIT
    $env:PBIX_REFRESH_NO_EXIT = '1'
    try {
        $refreshParams = @{ TimeoutMinutes = $TimeoutMinutes }
        if ($DryRun) { $refreshParams['DryRun'] = $true }
        $code = & $refreshScript @refreshParams
        if ($null -eq $code) { $code = 0 }
        return [int]$code
    }
    catch {
        Write-AgentLog $_.Exception.Message 'ERROR'
        return 1
    }
    finally {
        if ($null -eq $prior) { Remove-Item Env:PBIX_REFRESH_NO_EXIT -ErrorAction SilentlyContinue }
        else { $env:PBIX_REFRESH_NO_EXIT = $prior }
    }
}

function Start-CursorAgentProcess {
    param(
        [Parameter(Mandatory)][string]$AgentExe,
        [Parameter(Mandatory)][string]$Workspace,
        [Parameter(Mandatory)][string]$PromptText
    )

    # Single Arguments string — Start-Process array ArgumentList mishandles spaces on PS 5.1.
    function Quote-Arg([string]$Value) {
        if ($null -eq $Value) { return '""' }
        return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
    }

    $argLine = @(
        '-p', '--force', '--trust', '--sandbox', 'disabled',
        '--output-format', 'text',
        '--workspace', (Quote-Arg $Workspace),
        (Quote-Arg $PromptText)
    ) -join ' '

    Write-AgentLog ("Starting Cursor agent: {0} {1}" -f $AgentExe, $argLine)
    $proc = Start-Process -FilePath $AgentExe -ArgumentList $argLine -WorkingDirectory $Workspace -Wait -PassThru -NoNewWindow
    return $proc.ExitCode
}

if (-not (Test-Path -LiteralPath $PromptFile)) { throw "Prompt file missing: $PromptFile" }
if (-not (Test-Path -LiteralPath $RefreshScript)) { throw "Refresh script missing: $RefreshScript" }

$prompt = ((Get-Content -LiteralPath $PromptFile -Raw) -replace '\s+', ' ').Trim()
Write-AgentLog "Repo:    $Repo"
Write-AgentLog "Prompt:  $PromptFile"

$exitCode = 1
try {
    if ($SkipAgent) {
        $exitCode = Invoke-DirectRefresh -Reason 'SkipAgent set; running Refresh-HorseShowsPbix.ps1 without Cursor CLI'
    }
    else {
        $agent = Get-CursorAgentExe
        if (-not $agent) {
            $exitCode = Invoke-DirectRefresh -Reason 'Cursor CLI (agent) was not on PATH. Install with irm https://cursor.com/install?win32=true | iex, or set CURSOR_API_KEY. Falling back to the refresh script.'
        }
        elseif ($DryRun) {
            Write-AgentLog ("Would run Cursor agent against workspace: {0}" -f $Repo)
            $exitCode = Invoke-DirectRefresh
        }
        else {
            $exitCode = Start-CursorAgentProcess -AgentExe $agent -Workspace $Repo -PromptText $prompt
            Write-AgentLog ("Cursor agent exited {0}" -f $exitCode)
            if ($exitCode -ne 0) {
                $exitCode = Invoke-DirectRefresh -Reason 'Cursor agent failed; retrying with Refresh-HorseShowsPbix.ps1'
            }
        }
    }
}
catch {
    Write-AgentLog $_.Exception.Message 'ERROR'
    if ($_.ScriptStackTrace) { Write-AgentLog $_.ScriptStackTrace 'ERROR' }
    try { $exitCode = Invoke-DirectRefresh -Reason 'Agent wrapper error; falling back to the refresh script' } catch { $exitCode = 1 }
}
finally {
    if (Get-Command Complete-RunLog -ErrorAction SilentlyContinue) {
        try { Complete-RunLog | Out-Null } catch { }
    }
}

exit $exitCode
