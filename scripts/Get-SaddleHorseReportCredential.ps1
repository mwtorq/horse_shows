<#
.SYNOPSIS
    Load the DPAPI-encrypted Saddle Horse Report credential for unattended scrapes.

.DESCRIPTION
    Dot-source this file, then call Get-SaddleHorseReportCredential.
    Default path is RESULTS_AUTOMATION_HOME\saddlehorsereport.cred
    (created by Save-SaddleHorseReportCredential.ps1).

.EXAMPLE
    . .\Get-SaddleHorseReportCredential.ps1
    $cred = Get-SaddleHorseReportCredential
#>

function Get-SaddleHorseReportCredential {
    param(
        [string]$Path
    )

    if (-not $Path) {
        $automationHome = if ($env:RESULTS_AUTOMATION_HOME) {
            $env:RESULTS_AUTOMATION_HOME
        } else {
            'C:\Users\mw\ResultsAutomation'
        }
        $Path = Join-Path $automationHome 'saddlehorsereport.cred'
    }

    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $credential = Import-Clixml -LiteralPath $Path
        if (-not $credential.UserName -or -not $credential.Password) {
            Write-Warning "Stored Saddle Horse Report credential at $Path is incomplete."
            return $null
        }
        return $credential
    }
    catch {
        Write-Warning ("Could not read the Saddle Horse Report credential at {0}: {1}" -f $Path, $_.Exception.Message)
        return $null
    }
}
