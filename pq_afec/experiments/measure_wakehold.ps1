# Keeps the SYSTEM awake while the fixloop measurement lock exists.
# Display is NOT held - the screen sleeps normally.
# No powercfg / no persistent system setting is modified. Dies with the run.
#
# LIMITATION (measured 2026-09-01): ES_SYSTEM_REQUIRED blocks only IDLE sleep.
# It cannot stop an explicit suspend (SetSuspendState / lid / power menu).
# The 2026-09-01 13:31 run died to exactly that. Nothing in user space can.
#
# 2026-09-01 fix: wait for the lock to APPEAR first. Previously this exited in
# the same second it started, because the detached fixloop had not yet written
# the lock file when this checked for it (race).
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError=true)] public static extern uint SetThreadExecutionState(uint esFlags);'

$ES_CONTINUOUS      = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1

$lockPath = 'C:\dev\pq_afec\experiments\state\fixloop.lock'
$logPath  = 'C:\dev\measure_wakehold.log'
$deadline = (Get-Date).AddHours(20)
$waitSecs = 120

"$(Get-Date -Format s)  hold start  pid=$PID" | Out-File -FilePath $logPath -Append -Encoding utf8

# --- wait for the lock to appear (the launcher may still be starting) -------
$waited = 0
while (-not (Test-Path $lockPath)) {
    if ($waited -ge $waitSecs) {
        "$(Get-Date -Format s)  give up: no lock after $waitSecs s" |
            Out-File -FilePath $logPath -Append -Encoding utf8
        exit 1
    }
    Start-Sleep -Seconds 2
    $waited += 2
}
"$(Get-Date -Format s)  lock seen after $waited s - holding" |
    Out-File -FilePath $logPath -Append -Encoding utf8

# --- hold while the lock exists --------------------------------------------
while ((Test-Path $lockPath) -and ((Get-Date) -lt $deadline)) {
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    Start-Sleep -Seconds 60
}

[void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
"$(Get-Date -Format s)  hold released (lock gone or deadline)" |
    Out-File -FilePath $logPath -Append -Encoding utf8
