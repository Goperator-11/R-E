# 배터리 감시기 — 저전력에서 측정을 **깨끗이** 멈추고 결과를 커밋한다.
#
# 왜 필요한가: 2026-08-29 에 충전기 없이 정밀도 실행을 이어갔다. 노트북이
# 그냥 꺼지면 진행 중이던 단위 하나를 잃는 것은 괜찮지만(저널이 단위마다
# fsync 한다), **커밋이 안 된 채로 꺼지면** 다음 세션이 어디까지 됐는지
# 알아내는 데 시간이 든다. 그래서 꺼지기 전에 스스로 갈무리한다.
#
# 하는 일:
#   1) 1 분마다 배터리를 본다
#   2) AC 가 다시 꽂히면 그냥 계속 지켜본다 (중단하지 않는다)
#   3) THRESHOLD 아래로 떨어지면
#        - fixloop/loop2/wsl 을 죽인다 (SIGKILL 이지만 저널은 안전하다)
#        - 락을 푼다
#        - pq_afec -> R-E 동기화 후 커밋·푸시
#        - 로그를 남긴다
#   4) 측정이 정상적으로 끝나도(락이 사라지면) 마지막 커밋을 하고 종료

$THRESHOLD = 15          # 이 % 아래면 갈무리한다
$SRC       = 'C:\dev\pq_afec'
$DST       = 'C:\dev\R-E'
$LOG       = 'C:\dev\battery_guard.log'

function Say($m) {
  $line = '{0}  {1}' -f (Get-Date -Format 'MM-dd HH:mm:ss'), $m
  Add-Content -Path $LOG -Value $line -Encoding UTF8
}

function Commit-Only($why) {
  # 측정을 **멈추지 않고** 지금까지의 결과만 커밋한다. 저널은 단위마다
  # fsync 되고 잘린 마지막 줄은 읽는 쪽이 버리므로, 도는 중에 복사해도 안전하다.
  robocopy $SRC (Join-Path $DST 'pq_afec') /MIR `
    /XD (Join-Path $SRC '.git') '__pycache__' (Join-Path $SRC 'experiments\_build') `
    /XF '*.pyc' 'fixloop.lock' '*.key' /NFL /NDL /NJH /NP /NS /NC | Out-Null
  Set-Location $DST
  & git add -A 2>&1 | Out-Null
  $n = (& git status --porcelain | Measure-Object).Count
  if ($n -gt 0) {
    & git commit -q -m "중간 저장 ($why) — battery_guard 자동 커밋

측정을 멈추지 않고 지금까지의 결과만 남긴다. 노트북이 갑자기 꺼져도
여기까지는 안전하다. 이어서 돌리는 법은 docs/다음 세션 인계.md §5.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>" 2>&1 | Out-Null
    & git push -q 2>&1 | Out-Null
    Say "  중간 커밋 완료 (변경 $n 개)"
  } else { Say '  변경 없음' }
}

function Save-And-Commit($why, $stopFirst = $true) {
  Say "갈무리 시작: $why"
  if (-not $stopFirst) { Commit-Only $why; return }
  # 1) 프로세스 정리
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'fixloop\.py|loop2\.py' } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Say ("  python " + $_.ProcessId + " 종료") } catch {} }
  Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" |
    Where-Object { $_.CommandLine -match 'pq_afec' } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Say ("  wsl " + $_.ProcessId + " 종료") } catch {} }
  Start-Sleep -Seconds 3
  Remove-Item (Join-Path $SRC 'experiments\state\fixloop.lock') -ErrorAction SilentlyContinue

  # 2) 저널 무결성 확인 (깨진 줄이 있으면 로그에 남긴다)
  $py = 'C:\Users\scien\AppData\Local\Programs\Python\Python314\python.exe'
  if (Test-Path $py) {
    $env:PYTHONIOENCODING = 'utf-8'
    $chk = & $py -c "
import json,glob,os
bad=0;tot=0
for f in glob.glob(r'$SRC\experiments\state\*_units.jsonl'):
    for ln in open(f,encoding='utf-8',errors='replace'):
        ln=ln.strip()
        if not ln: continue
        tot+=1
        try: json.loads(ln)
        except Exception: bad+=1
print('%d %d'%(tot,bad))
" 2>&1
    Say "  저널: $chk (총줄 깨진줄)"
  }

  # 3) 동기화 + 커밋
  robocopy $SRC (Join-Path $DST 'pq_afec') /MIR `
    /XD (Join-Path $SRC '.git') '__pycache__' (Join-Path $SRC 'experiments\_build') `
    /XF '*.pyc' 'fixloop.lock' '*.key' /NFL /NDL /NJH /NP /NS /NC | Out-Null
  Set-Location $DST
  & git add -A 2>&1 | Out-Null
  $n = (& git status --porcelain | Measure-Object).Count
  if ($n -gt 0) {
    $msg = "배터리 갈무리 ($why) — 측정 중단 지점 저장`n`n" +
           "battery_guard.ps1 이 자동으로 남긴 커밋이다. 노트북이 꺼지기 전에`n" +
           "진행 상황을 저장했다. 이어서 돌리는 법은 docs/다음 세션 인계.md §5.`n`n" +
           "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    & git commit -q -m $msg 2>&1 | Out-Null
    & git push -q 2>&1 | Out-Null
    Say "  커밋·푸시 완료 (변경 $n 개)"
  } else {
    Say '  변경 없음 - 커밋 안 함'
  }
  Say '갈무리 끝'
}

Say "=== 감시 시작 (임계 $THRESHOLD%) ==="
$warned = $false
$lastCommit = Get-Date
while ($true) {
  if (((Get-Date) - $lastCommit).TotalMinutes -ge 30) {
    Commit-Only "30 분 주기"
    $lastCommit = Get-Date
  }
  $b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
  $lock = Test-Path (Join-Path $SRC 'experiments\state\fixloop.lock')

  if (-not $lock) {
    Say '락이 사라졌다 - 측정이 끝났거나 죽었다. 마지막 갈무리를 한다.'
    Save-And-Commit '측정 종료'
    break
  }

  if ($b) {
    $pct = [int]$b.EstimatedChargeRemaining
    $onAC = ($b.BatteryStatus -eq 2)
    if ($onAC) {
      if ($warned) { Say "충전기가 다시 꽂혔다 ($pct%) - 계속 지켜본다"; $warned = $false }
    } else {
      if ($pct -le $THRESHOLD) {
        Save-And-Commit "배터리 $pct%"
        break
      }
      if ($pct -le 30 -and -not $warned) { Say "배터리 $pct% - 임계 $THRESHOLD% 에 가까워진다"; $warned = $true }
    }
  }
  Start-Sleep -Seconds 60
}
Say '=== 감시 종료 ==='
