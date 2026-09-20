<#
.SYNOPSIS
    Compatibility shim: old Cursor-agent task runs the simple SendKeys refresh.

.DESCRIPTION
    Calls automation\Refresh-HorseShowsPbix-Simple.ps1 in-process from this repo.
    Does not require ResultsAutomation to already exist. Does not use Cursor CLI
    or TOM. Prefer automation\Run-PbixRefresh.cmd for manual runs.
#>
[CmdletBinding()]
param(
    [switch]$SkipAgent,
    [switch]$DryRun,
    [switch]$QuickTest,
    [ValidateRange(5, 180)]
    [int]$TimeoutMinutes = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Simple = Join-Path $PSScriptRoot 'Refresh-HorseShowsPbix-Simple.ps1'
if (-not (Test-Path -LiteralPath $Simple)) {
    throw "Missing $Simple - git pull on branch/main that includes the simple refresh."
}

Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [INFO] Agent shim -> {1}" -f (Get-Date), $Simple)

if ($DryRun) {
    Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [INFO] Dry run OK (would run simple refresh)" -f (Get-Date))
    exit 0
}

$params = @{}
if ($QuickTest) { $params['QuickTest'] = $true }

# In-process: no powershell -File against OneDrive; SendKeys uses this desktop session.
& $Simple @params
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 0 }
if ($code -ne 0) {
    Write-Host ("{0:yyyy-MM-dd HH:mm:ss} [ERROR] Simple refresh exit {1}" -f (Get-Date), $code)
}
exit [int]$code
