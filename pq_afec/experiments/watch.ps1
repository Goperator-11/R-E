$ErrorActionPreference = "SilentlyContinue"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "PQ-AFEC 실험 진행 감시"
Set-Location C:\dev\pq_afec

while ($true) {
    Clear-Host
    Write-Host ("=" * 88) -ForegroundColor DarkGray
    Write-Host "  PQ-AFEC 2차 전체 실험 — 실시간 진행" -ForegroundColor Cyan
    Write-Host ("  " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) -ForegroundColor DarkGray
    Write-Host ("=" * 88) -ForegroundColor DarkGray

    python experiments\pipeline.py --status 2>$null | Select-Object -Skip 2

    Write-Host ""
    Write-Host "--- 저널: 단계 내부 진행 (중단해도 여기서부터 이어짐) ---" -ForegroundColor Yellow
    Get-ChildItem experiments\state\*_units.jsonl 2>$null | ForEach-Object {
        $n = (Get-Content $_.FullName | Measure-Object -Line).Lines
        "{0,-14} {1,4} 단위" -f $_.BaseName.Replace("_units",""), $n
    }

    Write-Host ""
    Write-Host "--- WSL 안에서 실제로 도는 프로세스 ---" -ForegroundColor Yellow
    wsl -d Ubuntu -- bash -lc "ps -eo etime,pcpu,comm,args --sort=-pcpu 2>/dev/null | grep -E 'python3|qdata|qserver|qclient' | grep -v grep | head -6 | cut -c1-84" 2>$null

    Write-Host ""
    Write-Host "--- 최근 로그 ---" -ForegroundColor Yellow
    $log = Get-ChildItem experiments\state\log_*.txt 2>$null |
           Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log) {
        Write-Host ("  " + $log.Name) -ForegroundColor DarkGray
        Get-Content $log.FullName -Tail 8 2>$null | ForEach-Object { "   $_" }
    }

    Write-Host ""
    Write-Host "3초마다 갱신 · Ctrl+C 로 이 창만 닫힘(실험은 계속 진행)" -ForegroundColor DarkGray
    Start-Sleep -Seconds 3
}
