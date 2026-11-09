# Windows 개발 측정 launcher

[launcher.py](../experiments/v33/lib/launcher.py)는 Windows 감독자를 분리 실행하고, 감독자가 로컬 보존 스크립트의 `wsl -d Ubuntu --exec bash <run.sh>` 호출 종료를 기다린다. [계획](../g3/v33/plans/final_bundle_v1.json)의 필수 과제를 하나씩 실행한다. 측정은 development이며 confirmatory가 아니다. 실제 QUIC smoke와 호출 셸 종료 뒤 측정 생존은 F26에서 확인한다.

## 실행 계획

Windows 저장소 루트에서 호출한다. 아래 명령은 F26에서 실행할 M0 예시이며 F25에서 측정을 시작했다는 뜻은 아니다. 산출물 경로 자리는 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/measurements/final_m0`로 바꾼다. `--until`은 절전 방지 종료 시각이다. 계획의 예상 시간과 사망 확인 여유 60분을 합한 시각보다 뒤여야 한다.

```powershell
python -I -B experiments/v33/lib/launcher.py --smoke --run-id final_m0 --artifacts-dir '<로컬 보존 산출물 경로>' --until 2026-11-14T23:00:00+09:00
```

M1은 `--run --task M1`, 후속 과제는 `--run --task X1`처럼 호출한다. X1·X9·X6에는 `--m1-result`로 같은 계획의 M1 결과 파일을 지정한다. `--plan` 기본값은 계획 JSON, `--lock` 기본값은 로컬 보존 경로 `C:/dev/codex_handoff/final/state/MEASURE_LOCK.json`이다. 원자료 경로와 바이너리 사본은 launcher가 정한다.

launcher와 감독자, WSL 준비 단계가 각각 살아 있는 devbed를 확인한다. 조회 실패를 프로세스 없음으로 취급하지 않는다. Windows 감독자는 같은 세션의 named mutex를 측정 종료까지 보유한다. 다른 세션에서 시작한 실행도 devbed의 atomic measurement lock을 얻어야 첫 단위를 실행할 수 있다.

계획의 커밋 바이트, M1 입력과 WSL 기본 Python의 reporter·SciPy를 실행 전에 확인한다. Python은 `-I -B`, namespace 진입은 `unshare -Urnm`이다. 새로운 실행 ID에서 기존 원자료를 발견하면 중단한다. plan과 companion 문서는 읽기만 한다.

## Windows 감독자와 절전 방지

[launch_windows.py](../experiments/v33/lib/launch_windows.py)는 `CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB`와 `SW_HIDE`를 쓴다. 실패 이유를 기록한 뒤 PowerShell의 `Win32_Process.Create`를 한 번 호출한다. WMI 경로도 숨긴 창과 BREAKAWAY를 지정하고 `ReturnValue`와 실제 PID를 확인한다. 약한 플래그로 다시 시도하지 않는다.

반환된 PID와 로컬 보존 자료 `receipt.json`의 `created`는 감독자 생성만 뜻한다. 감독자는 WMI 경로에서도 자체 로그와 환경을 설정한다. Windows 감독자 PID, Windows의 wsl.exe PID, 측정 잠금의 Linux PID는 별도 값이다. 감독자는 WSL의 종료 코드를 보존하며 상태 파일 기록이 실패해도 이미 시작한 WSL 자식을 기다린다.

감독자는 Windows 절전 방지 요청의 반환값을 확인하고, 로컬 보존 도구 `C:/dev/codex_handoff/final/tools/wakehold_v33.py <끝 시각> <감독자 PID> --ignore-stop`도 함께 띄운다. STOP은 이 helper를 끝내지 않지만 지정 시각이나 감독자 종료는 종료 조건이다. helper의 PID만으로 API 성공을 판정하지 않는다. 감독자의 요청도 지정 시각 또는 WSL 종료 뒤 해제한다. 지정 시각이 지나도 WSL을 강제로 끝내지는 않는다.

로컬 보존 도구 `start_loop.ps1`이 충전 중 덮개 설정을 0으로 둔 동안만 덮개를 닫아도 된다. 시작 메뉴 전원, 로그아웃, 배터리 소진은 측정을 죽인다. STOP이나 실행기 종료로 덮개 설정이 복원된 뒤에는 이 조건이 성립하는지 다시 확인한다. launcher는 전원 설정을 바꾸지 않는다. 실행 직전 AC 덮개 값이 0이 아니거나 배터리 상태이면 로컬 보존 진행 보고 `C:/dev/codex_handoff/final/runs/MORNING_REPORT.md` 첫 줄에 경고를 추가하고 계속 실행한다.

## 파일 배치와 상태

제어 자료는 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/launches/<run-id>/<호출 ID>/`에 둔다. `config.json`, `run.sh`, `receipt.json`, `launch_status.json`, `preflight.json`, 감독자·WSL·wakehold 로그가 여기에 있다. 원자료와 PEM이 있는 폴더에 launcher 로그를 미리 쓰지 않는다.

실행 사본은 로컬 보존 경로 `~/v33_runs/<run-id>/bin/<binary-id>/qamp`다. 모든 `.srcsha`와 gen33의 `.sha256`을 원본 바이트로 함께 보존한다. 복사 전후와 매 단위마다 계획에 기록한 바이너리 SHA·srcsha를 검사한다. 같은 이름의 기존 사본이 다르거나 재개할 사본이 없으면 덮어쓰지 않고 실패한다. 원본 동결 바이너리와 설치본은 읽기만 한다.

devbed는 로컬 보존 원자료 폴더의 `status_<run-id>.json`, `DONE_<run-id>`과 measurement lock을 관리한다. 상태에는 실제 사본을 쓰는 Linux 재개 argv가 있고 5초 주기의 heartbeat가 들어간다. launcher의 `updated_at`은 감독자의 상태 갱신 시각이며 측정 heartbeat가 아니다.

로컬 보존 자료 `launch_status.json`은 Windows에서 그대로 호출할 `resume_command`와 `report_only_command` argv를 보존한다. plan·과제·run ID·M1·lock·artifacts와 절전 방지 시각이 유지되고, 사본 경로는 같은 run ID에서 다시 검증한다. PowerShell에서 argv 배열의 첫 항목을 프로그램으로, 나머지를 인자로 전달한다.

```powershell
$launchState = Get-Content -Raw -Encoding UTF8 '<launch_status.json>' | ConvertFrom-Json
$launchArgv = $launchState.resume_command
& $launchArgv[0] $launchArgv[1..($launchArgv.Length - 1)]
```

## 완료와 복구

devbed가 DONE을 만든 뒤에도 보고서·SHA 검증이 실패하면 잠금이 남는다. 감독자는 WSL 종료 코드 0, 같은 실행의 DONE·완료 상태, devbed의 잠금 해제, 결과 식별자와 SHA 목록을 함께 확인해야 `complete`를 기록한다. 결과의 checks는 별도로 보존한다. 생성 성공을 측정 기준 통과로 해석하지 않는다.

DONE 없이 죽은 실행은 루프 규칙의 사망 조건을 확인하고 해당 프로세스를 끝낸 뒤 잠금을 처리한다. 그 뒤 `resume_command`를 쓴다. launcher는 잠금을 삭제하거나 자동 재시도하지 않는다. 재개 시작 시 로컬 보존 호출 폴더의 `resume_claim.json`을 독점 생성하므로 launcher를 통한 측정 재개는 한 번만 허용한다. 재부팅 후 재개도 여기에 포함된다. 재개가 실패한 뒤 이 파일을 지워 횟수를 초기화하지 않는다.

DONE 뒤 보고 실패는 `report_only_command`를 쓴다. devbed가 기존 잠금의 실행 식별과 죽은 PID를 확인하고 보고만 재생성한다. manifest·저널·원자료가 완전하지 않으면 실패한다. launcher는 status나 DONE을 대신 쓰지 않는다. 미완료 실행을 report-only로 완료 처리하지 않는다.

## 검증 범위

F25의 fixture는 분리 플래그·WMI 실패, 감독자 대기와 종료 코드, 경로 인용, 중복 시작, 사본 변조, 재개 입력과 보고 성공 경계를 검사한다. 실행 명령과 출력은 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/`의 `F25_accept.txt`, `F25_commands.json`, `F25_summary.json`에 둔다.

F26에서는 실제 launcher smoke를 시작한 셸을 종료하고 측정 종료까지 heartbeat 간격 15초 이하, DONE·결과·SHA·잠금 해제, WSL uptime 감소 없음과 사본 지문을 확인한다. 사본이 바이너리 ID별 디렉터리에 있으므로 카드의 `bin/*` 대조는 `bin/*/qamp`와 각 sidecar의 대조로 수행한다. 파일 자체의 SHA와 `.srcsha`에 저장된 소스 지문은 서로 다른 값이다.
