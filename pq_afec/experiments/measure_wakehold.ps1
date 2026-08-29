# Keeps the SYSTEM awake only while the fixloop measurement lock exists.
# Display is NOT held - the screen sleeps normally.
# No powercfg / no persistent system setting is modified. Dies with the run.
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError=true)] public static extern uint SetThreadExecutionState(uint esFlags);'

$ES_CONTINUOUS      = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1

$lockPath = 'C:\dev\pq_afec\experiments\state\fixloop.lock'
$logPath  = 'C:\dev\measure_wakehold.log'
$deadline = (Get-Date).AddHours(20)

"$(Get-Date -Format s)  hold start  pid=$PID" | Out-File -FilePath $logPath -Append -Encoding utf8

while ((Test-Path $lockPath) -and ((Get-Date) -lt $deadline)) {
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    Start-Sleep -Seconds 60
}

[void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
"$(Get-Date -Format s)  hold released (lock gone or deadline)" | Out-File -FilePath $logPath -Append -Encoding utf8
