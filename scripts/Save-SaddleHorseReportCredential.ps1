<#
.SYNOPSIS
    Store the Saddle Horse Report login once so the weekly job can run unattended.

.DESCRIPTION
    Prompts for the Saddle Horse Report email and password and writes them to
    saddlehorsereport.cred via Export-Clixml (Windows DPAPI). The encrypted file is
    written under RESULTS_AUTOMATION_HOME (default C:\Users\mw\ResultsAutomation),
    not into this repo.

    Run this once. Re-run whenever the Saddle Horse Report password changes.

.EXAMPLE
    .\Save-SaddleHorseReportCredential.ps1
    .\Save-SaddleHorseReportCredential.ps1 -Show
#>
[CmdletBinding()]
param(
    [switch]$Show,
    [switch]$Remove,
    [string]$CredPath
)

$AutomationHome = if ($env:RESULTS_AUTOMATION_HOME) { $env:RESULTS_AUTOMATION_HOME } else { 'C:\Users\mw\ResultsAutomation' }
if (-not $CredPath) {
    $CredPath = Join-Path $AutomationHome 'saddlehorsereport.cred'
}

if ($Remove) {
    if (Test-Path -LiteralPath $CredPath) {
        Remove-Item -LiteralPath $CredPath -Force
        Write-Host "Removed $CredPath"
    }
    else {
        Write-Host "Nothing to remove; $CredPath does not exist."
    }
    return
}

if ($Show) {
    if (-not (Test-Path -LiteralPath $CredPath)) {
        Write-Host "No stored credential. Run this script with no arguments to create one."
        return
    }
    $stored = Import-Clixml -LiteralPath $CredPath
    Write-Host "Stored Saddle Horse Report user: $($stored.UserName)"
    Write-Host "File: $CredPath"
    Write-Host "Password is DPAPI-encrypted for $env:USERDOMAIN\$env:USERNAME on $env:COMPUTERNAME."
    return
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CredPath) | Out-Null

Write-Host 'Enter the Saddle Horse Report login for https://www.saddlehorsereport.com'
$cred = Get-Credential -Message 'Saddle Horse Report login (email as the user name)'
if (-not $cred) {
    Write-Warning 'Cancelled; nothing was saved.'
    return
}

$cred | Export-Clixml -LiteralPath $CredPath -Force

$check = Import-Clixml -LiteralPath $CredPath
$plain = [System.Net.NetworkCredential]::new('', $check.Password).Password
if ([string]::IsNullOrEmpty($plain)) {
    throw "Saved $CredPath but the password did not decrypt; the weekly run would fail."
}

Write-Host "Saved $CredPath for $($check.UserName) (password length $($plain.Length))."
Write-Host 'The weekly Horse Shows job will now import Saddle Horse Report data without prompting.'
