import sys
sys.dont_write_bytecode = True
import hashlib
from pathlib import Path


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
driver = RUNS / "l3_joint_driver_v1.py"
checksum = hashlib.sha256(driver.read_bytes()).hexdigest()
source = r'''Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = 'C:\dev\codex_handoff\v33\runs'
$root = 'C:\dev\pq_afec_gen33'
$driver = Join-Path $base 'l3_joint_driver_v1.py'
$python = 'C:\Users\scien\AppData\Local\Programs\Python\Python314\python.exe'
$collectionPath = Join-Path $base 'L3_full_v1.finished.json'
$collection = Get-Content -LiteralPath $collectionPath -Raw -Encoding UTF8 | ConvertFrom-Json
$driverSha = (Get-FileHash -LiteralPath $driver -Algorithm SHA256).Hash.ToLowerInvariant()
if ($driverSha -ne 'DRIVER_SHA') { throw 'Frozen driver differs.' }
if ($collection.status -ne 'complete' -or $collection.jobs -ne 90 -or $collection.expected_jobs -ne 90 -or $null -ne $collection.error) { throw 'Whole collection must complete.' }
if ($collection.plan_sha256 -ne '4e48e8d951fe1b9b6ce24babb1119775eb49d4e45bf2964be1d6152da31fb9c5') { throw 'Collection plan differs.' }
if (Test-Path -LiteralPath 'C:\dev\codex_handoff\v33\state\MEASURE_LOCK.json') { throw 'Physical measurement lock exists.' }
$dirty = & git -C $root status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Commit the prepared analysis first.' }
$stdout = Join-Path $base 'L3_joint_plan_launcher_v1.stdout.txt'
$stderr = Join-Path $base 'L3_joint_plan_launcher_v1.stderr.txt'
$launchPath = Join-Path $base 'L3_joint_plan_launch_v1.json'
foreach ($path in @($stdout, $stderr, $launchPath, (Join-Path $base 'L3_joint_action_family_v1.json'), (Join-Path $base 'L3_joint_plan_v1.started.json'), (Join-Path $base 'L3_joint_plan_v1.finished.json'))) {
    if (Test-Path -LiteralPath $path) { throw ('Plan launch requires new paths: ' + $path) }
}
$started = [DateTimeOffset]::Now.ToString('o')
$process = Start-Process -FilePath $python -ArgumentList @('-I', '-B', $driver, 'plan') -WindowStyle Hidden -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$launch = [ordered]@{
    schema = 'padfec.v33.l3_joint_plan_launch/1'
    started_kst = $started
    driver_pid = $process.Id
    process_start_kst = $process.StartTime.ToString('o')
    driver_path = $driver
    driver_sha256 = $driverSha
    collection_receipt_path = $collectionPath
    collection_receipt_sha256 = (Get-FileHash -LiteralPath $collectionPath -Algorithm SHA256).Hash.ToLowerInvariant()
    command = @($python, '-I', '-B', $driver, 'plan')
    launch_script_path = $PSCommandPath
    launch_script_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    stdout_path = $stdout
    stderr_path = $stderr
    scope = 'One finite complete-input validation and joint action union preparation; no performance-based selection.'
}
[System.IO.File]::WriteAllText($launchPath, ($launch | ConvertTo-Json -Depth 8) + "`n", [System.Text.UTF8Encoding]::new($false))
$launch | ConvertTo-Json -Depth 8
'''
with (RUNS / "launch_l3_joint_plan_v1.ps1").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source.replace("DRIVER_SHA", checksum))
