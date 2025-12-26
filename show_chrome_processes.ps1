# Show all Chrome processes with PID, start time, and last active time
Write-Host "=== Chrome Processes ===" -ForegroundColor Cyan

# Get all Chrome processes
$chromeProcs = Get-Process chrome -ErrorAction SilentlyContinue

if (-not $chromeProcs) {
    Write-Host "No Chrome processes found" -ForegroundColor Yellow
    exit
}

Write-Host "Found $($chromeProcs.Count) Chrome process(es)`n" -ForegroundColor Cyan

$results = @()

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
        
        # Get last window interaction time
        # Note: Windows doesn't directly track per-process "last window interaction"
        # We'll approximate using process state and thread activity
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
                            # Note: StartTime may require elevated permissions
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
                    # Use most recent thread time if it's after start time, otherwise use current time
                    if ($latestThreadTime -and $latestThreadTime -gt $startTime) {
                        $lastActive = $latestThreadTime
                    } else {
                        # Process is responding with a window - assume recently active
                        $lastActive = Get-Date
                    }
                } else {
                    # Process has window but not responding - may be hung
                    # Use latest thread time or start time
                    if ($latestThreadTime) {
                        $lastActive = $latestThreadTime
                    } elseif ($startTime) {
                        $lastActive = $startTime
                    }
                }
            } else {
                # No main window - background process
                # Use latest thread time or current time
                if ($latestThreadTime) {
                    $lastActive = $latestThreadTime
                } else {
                    $lastActive = Get-Date
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
        
        # Get CPU time
        $cpuTimeStr = if ($proc.CPU) { $proc.CPU.ToString("hh\:mm\:ss\.fff") } else { "N/A" }
        
        $results += [PSCustomObject]@{
            PID = $proc.Id
            StartTime = $startTime
            LastActive = $lastActive
            ParentPID = $parentPID
            ParentName = $parentName
            MemoryMB = $memoryMB
            CPUTime = $cpuTimeStr
            Threads = $proc.Threads.Count
        }
    } catch {
        Write-Warning "Error processing Chrome PID $($proc.Id): $_"
    }
}

# Sort by start time (oldest first), processes with null StartTime go to end
$results = $results | Sort-Object @{Expression={if ($_.StartTime) { $_.StartTime } else { [DateTime]::MaxValue }}}

# Display results
Write-Host "=== Chrome Process Details ===`n" -ForegroundColor Cyan

# Format table with custom properties
$results | Format-Table -Property @(
    @{Label="PID"; Expression={$_.PID}; Width=8},
    @{Label="Start Time"; Expression={if ($_.StartTime) { $_.StartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }}; Width=20},
    @{Label="Last Active"; Expression={if ($_.LastActive) { $_.LastActive.ToString("yyyy-MM-dd HH:mm:ss") } else { "N/A" }}; Width=20},
    @{Label="Parent"; Expression={"$($_.ParentName) ($($_.ParentPID))"}; Width=25},
    @{Label="Memory (MB)"; Expression={$_.MemoryMB}; Width=12},
    @{Label="CPU Time"; Expression={$_.CPUTime}; Width=12},
    @{Label="Threads"; Expression={$_.Threads}; Width=8}
) -AutoSize

# Summary statistics
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$total = $results.Count
$oldest = $results | Where-Object { $_.StartTime } | Sort-Object StartTime | Select-Object -First 1
$newest = $results | Where-Object { $_.StartTime } | Sort-Object StartTime | Select-Object -Last 1
$totalMemory = ($results | Measure-Object -Property MemoryMB -Sum).Sum

Write-Host "Total Chrome processes: $total"
if ($oldest) {
    Write-Host "Oldest process started: $($oldest.StartTime.ToString("yyyy-MM-dd HH:mm:ss")) (PID: $($oldest.PID))"
} else {
    Write-Host "Oldest process: Unable to determine start time"
}
if ($newest) {
    Write-Host "Newest process started: $($newest.StartTime.ToString("yyyy-MM-dd HH:mm:ss")) (PID: $($newest.PID))"
} else {
    Write-Host "Newest process: Unable to determine start time"
}
Write-Host "Total memory usage: $([math]::Round($totalMemory, 2)) MB"

# Show processes by parent
Write-Host "`n=== Processes by Parent ===" -ForegroundColor Cyan
$byParent = $results | Group-Object ParentName | Sort-Object Count -Descending
foreach ($group in $byParent) {
    Write-Host "  $($group.Name): $($group.Count) process(es)" -ForegroundColor Yellow
    $group.Group | ForEach-Object {
        $startTimeStr = if ($_.StartTime) { $_.StartTime.ToString("HH:mm:ss") } else { "N/A" }
        Write-Host "    PID $($_.PID) - Started: $startTimeStr" -ForegroundColor Gray
    }
}

