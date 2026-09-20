<#
.SYNOPSIS
    Compatibility shim: old Cursor-agent task now runs the simple SendKeys refresh.

.DESCRIPTION
    The previous agent/TOM path failed on Windows PowerShell (encoding, OneDrive
    -File quoting, missing Cursor CLI). This script now only launches:

      C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh\Refresh.ps1

    If that file is missing, it installs it via Register-HorseShowsPbixRefreshTask.ps1
    first. Prefer double-clicking Run.cmd or pasting PASTE_TO_INSTALL.ps1.
#>
[CmdletBinding()]
param(
    [switch]$SkipAgent,   # kept for old callers; ignored
    [switch]$DryRun,      # prints path only; does not refresh
    [ValidateRange(5, 180)]
    [int]$TimeoutMinutes = 90  # kept for old callers; ignored by simple refresh
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LaunchDir = if ($env:RESULTS_AUTOMATION_HOME) {
    Join-Path $env:RESULTS_AUTOMATION_HOME 'HorseShowsPbixRefresh'
} else {
    'C:\Users\mw\ResultsAutomation\HorseShowsPbixRefresh'
}
$RefreshPath = Join-Path $LaunchDir 'Refresh.ps1'
$Register = Join-Path $PSScriptRoot 'Register-HorseShowsPbixRefreshTask.ps1'

Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [INFO] Deprecated agent entrypoint -> simple refresh" -f (Get-Date))
Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [INFO] Target: {1}" -f (Get-Date), $RefreshPath)

if ($DryRun) {
    Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [INFO] Dry run: would execute {1}" -f (Get-Date), $RefreshPath)
    exit 0
}

if (-not (Test-Path -LiteralPath $RefreshPath)) {
    Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [WARN] Refresh.ps1 missing; installing via Register..." -f (Get-Date))
    if (-not (Test-Path -LiteralPath $Register)) {
        throw "Missing $Register and $RefreshPath. Paste automation/PASTE_TO_INSTALL.ps1 first."
    }
    & $Register -Force
}

if (-not (Test-Path -LiteralPath $RefreshPath)) {
    throw "Refresh.ps1 still missing at $RefreshPath after register."
}

# In-process so SendKeys hits this interactive desktop session.
& $RefreshPath
$code = if ($null -ne $LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
exit $code
