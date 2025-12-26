# Kill Chrome processes that have been inactive for more than 30 minutes
param(
    [int]$InactiveMinutes = 30,
    [switch]$WhatIf
)

Write-Host "=== Killing Inactive Chrome Processes ===" -ForegroundColor Cyan
Write-Host "Inactive threshold: $InactiveMinutes minutes`n" -ForegroundColor Gray

# Get all Chrome processes
$chromeProcs = Get-Process chrome -ErrorAction SilentlyContinue

if (-not $chromeProcs) {
    Write-Host "No Chrome processes found" -ForegroundColor Yellow
    exit
}

Write-Host "Found $($chromeProcs.Count) Chrome process(es)`n" -ForegroundColor Cyan

$results = @()
$currentTime = Get-Date

foreach ($proc in $chromeProcs) {
    try {
        # Get start time (may be null for some processes)
        $startTime = $null
        try {
            $startTime = $proc.StartTime
        } catch {
            # StartTime may not be available
        }
        
        # If StartTime is null, try to get from CIMInstance
        if (-not $startTime) {
            try {
                $cimProc = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue
                if ($cimProc -and $cimProc.CreationDate) {
                    $startTime = $cimProc.CreationDate
                }
            } catch {
                # Ignore
            }
        }
        
        # Get last window interaction time (same logic as show_chrome_processes.ps1)
        $lastActive = $null
        
        try {
            # Check if process has a main window (indicates GUI/window interaction)
            $hasWindow = $false
            $isResponding = $false
            try {
                $hasWindow = ($proc.MainWindowHandle -ne [IntPtr]::Zero) -and ($proc.MainWindowTitle -ne "")
                $isResponding = $proc.Responding
            } catch {
                # Ignore
            }
            
            # Get most recent thread activity from process threads
            $latestThreadTime = $null
            try {
                # Use process's thread collection to find most recent thread
                if ($proc.Threads -and $proc.Threads.Count -gt 0) {
                    foreach ($thread in $proc.Threads) {
                        try {
                            # Get thread start time (approximation of activity)
                            $threadStartTime = $null
                            try {
                                $threadStartTime = $thread.StartTime
                            } catch {
                                # StartTime may not be accessible
                            }
                            
                            if ($threadStartTime) {
                                if (-not $latestThreadTime -or $threadStartTime -gt $latestThreadTime) {
                                    $latestThreadTime = $threadStartTime
                                }
                            }
                        } catch {
                            # Ignore individual thread errors
                        }
                    }
                }
            } catch {
                # Ignore thread access errors
            }
            
            # Determine last active time based on window interaction indicators
            if ($hasWindow) {
                if ($isResponding) {
                    # Process has window and is responding - likely recently interacted with
                    if ($latestThreadTime -and $latestThreadTime -gt $startTime) {
                        $lastActive = $latestThreadTime
                    } else {
                        # Process is responding with a window - assume recently active
                        $lastActive = $currentTime
                    }
                } else {
                    # Process has window but not responding - may be hung
                    if ($latestThreadTime) {
                        $lastActive = $latestThreadTime
                    } elseif ($startTime) {
                        $lastActive = $startTime
                    }
                }
            } else {
                # No main window - background process
                if ($latestThreadTime) {
                    $lastActive = $latestThreadTime
                } else {
                    $lastActive = $currentTime
                }
            }
        } catch {
            # Fallback: use start time if available
            if ($startTime) {
                $lastActive = $startTime
            }
        }
        
        # Final fallback: if still no last active and we have start time, use start time
        if (-not $lastActive -and $startTime) {
            $lastActive = $startTime
        }
        
        # Calculate inactive duration
        $inactiveDuration = $null
        $isInactive = $false
        if ($lastActive) {
            $inactiveDuration = $currentTime - $lastActive
            $isInactive = $inactiveDuration.TotalMinutes -gt $InactiveMinutes
        }
        
        # Get parent process info
        $parentPID = $null
        $parentName = $null
        try {
            $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction Stop
            $parentPID = $procInfo.ParentProcessId
            if ($parentPID) {
                $parentProc = Get-Process -Id $parentPID -ErrorAction SilentlyContinue
                if ($parentProc) {
                    $parentName = $parentProc.ProcessName
                } else {
                    $parentName = "(terminated)"
                }
            }
        } catch {
            # Ignore
        }
        
        # Get memory usage
        $memoryMB = [math]::Round($proc.WorkingSet64 / 1MB, 2)
        
        $results += [PSCustomObject]@{
            PID = $proc.Id
            StartTime = $startTime
            LastActive = $lastActive
            InactiveMinutes = if ($inactiveDuration) { [math]::Round($inactiveDuration.TotalMinutes, 1) } else { $null }
            IsInactive = $isInactive
            ParentPID = $parentPID
            ParentName = $parentName
            MemoryMB = $memoryMB
            HasWindow = $hasWindow
            IsResponding = $isResponding
        }
    } catch {
        Write-Warning "Error processing Chrome PID $($proc.Id): $_"
    }
}

# Separate active and inactive processes
$activeProcesses = $results | Where-Object { -not $_.IsInactive }
$inactiveProcesses = $results | Where-Object { $_.IsInactive }

Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "Total Chrome processes: $($results.Count)"
Write-Host "Active processes (inactive < $InactiveMinutes minutes): $($activeProcesses.Count)" -ForegroundColor Green
Write-Host "Inactive processes (inactive >= $InactiveMinutes minutes): $($inactiveProcesses.Count)" -ForegroundColor Red

if ($inactiveProcesses.Count -eq 0) {
    Write-Host "`nNo inactive Chrome processes to kill." -ForegroundColor Yellow
    exit
}

# Show inactive processes
Write-Host "`n=== Inactive Chrome Processes ===" -ForegroundColor Red
$inactiveProcesses | Format-Table -Property @(
    @{Label="PID"; Expression={$_.PID}; Width=8},
    @{Label="Last Active"; Expression={if ($_.LastActive) { $_.LastActive.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }}; Width=20},
    @{Label="Inactive (min)"; Expression={if ($_.InactiveMinutes) { $_.InactiveMinutes } else { "N/A" }}; Width=15},
    @{Label="Parent"; Expression={"$($_.ParentName) ($($_.ParentPID))"}; Width=25},
    @{Label="Memory (MB)"; Expression={$_.MemoryMB}; Width=12}
) -AutoSize

# Kill inactive processes
if ($WhatIf) {
    Write-Host "`n=== What-If Mode: Would Kill ===" -ForegroundColor Yellow
    foreach ($proc in $inactiveProcesses) {
        Write-Host "  Would kill PID $($proc.PID) - Inactive for $($proc.InactiveMinutes) minutes" -ForegroundColor Gray
    }
} else {
    Write-Host "`n=== Killing Inactive Processes ===" -ForegroundColor Magenta
    $killed = @()
    $failed = @()
    
    foreach ($proc in $inactiveProcesses) {
        try {
            $process = Get-Process -Id $proc.PID -ErrorAction Stop
            Stop-Process -Id $proc.PID -Force -ErrorAction Stop
            $killed += $proc
            Write-Host "  Killed PID $($proc.PID) - Inactive for $($proc.InactiveMinutes) minutes" -ForegroundColor Green
        } catch {
            $failed += $proc
            Write-Warning "  Failed to kill PID $($proc.PID): $_"
        }
    }
    
    Write-Host "`n=== Kill Summary ===" -ForegroundColor Cyan
    Write-Host "Successfully killed: $($killed.Count) process(es)" -ForegroundColor Green
    if ($killed.Count -gt 0) {
        Write-Host "PIDs: $($killed.PID -join ', ')"
        $totalMemoryFreed = ($killed | Measure-Object -Property MemoryMB -Sum).Sum
        Write-Host "Memory freed: $([math]::Round($totalMemoryFreed, 2)) MB" -ForegroundColor Green
    }
    if ($failed.Count -gt 0) {
        Write-Host "Failed to kill: $($failed.Count) process(es)" -ForegroundColor Red
        Write-Host "PIDs: $($failed.PID -join ', ')"
    }
}

# Show remaining active processes
if ($activeProcesses.Count -gt 0) {
    Write-Host "`n=== Remaining Active Processes ===" -ForegroundColor Green
    $activeProcesses | Format-Table -Property @(
        @{Label="PID"; Expression={$_.PID}; Width=8},
        @{Label="Last Active"; Expression={if ($_.LastActive) { $_.LastActive.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }}; Width=20},
        @{Label="Inactive (min)"; Expression={if ($_.InactiveMinutes) { $_.InactiveMinutes } else { "N/A" }}; Width=15},
        @{Label="Parent"; Expression={"$($_.ParentName) ($($_.ParentPID))"}; Width=25}
    ) -AutoSize
}

