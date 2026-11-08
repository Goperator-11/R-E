Add-Type -Namespace Win32 -Name Power -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError=true)] public static extern uint SetThreadExecutionState(uint esFlags);'

$ES_CONTINUOUS      = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1

$lockPath = 'C:\dev\pq_afec\experiments\state\fixloop.lock'
$logPath  = 'C:\dev\measure_wakehold.log'
$deadline = (Get-Date).AddHours(20)
$waitSecs = 120

"$(Get-Date -Format s)  hold start  pid=$PID" | Out-File -FilePath $logPath -Append -Encoding utf8

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

while ((Test-Path $lockPath) -and ((Get-Date) -lt $deadline)) {
    [void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    Start-Sleep -Seconds 60
}

[void][Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS)
"$(Get-Date -Format s)  hold released (lock gone or deadline)" |
    Out-File -FilePath $logPath -Append -Encoding utf8
