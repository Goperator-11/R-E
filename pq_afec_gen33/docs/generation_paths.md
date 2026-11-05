# 세대 경로와 역사 자료

2026-11-02 정정: 활성 정책은 v3.3.1-dev(상태 11)로 바뀌었지만 아래 `gen_id`는 세대 이름이라 `v3.3-dev` 그대로 두었다. `experiments/pipeline.py` 375행이 이 값으로 과거 파이프라인을 막기 때문이다. 근거 `docs/V33FIX_policy.md` 통합 정리 절.

`genconfig.json`은 작업 세대의 이름, 빌더 파일명, 지속 저장 바이너리, 설치 바이너리와 WSL 저장소 루트를 정한다. `experiments/generation.py`가 이 파일을 읽으며, 관문과 파이프라인은 설정된 경로를 사용한다. 설정의 `gen_id`는 `v3.3-dev`다. 정책과 저장 상태의 버전은 별도로 관리한다.

`gate_v3_parity.py`의 기본 바이너리는 `~/quicbed_gen33/bin/qamp`다. 빌더와 관문은 같은 파일 목록으로 srcsha를 계산한다. 대상은 모든 Go 파일, `build.sh`, 설정된 빌더, `go.mod`, `go.sum`이며 파일명을 정렬한 뒤 원시 바이트 SHA-256을 사용한다. 빌드 stage의 줄 끝 정규화와 원본 지문은 서로 다른 단계다.

빌더는 `-trimpath -buildvcs=false`를 사용하며 `qamp.buildinfo`에 `go version -m` 출력을 저장한다. 출력 위치는 gen33 전용이다. 동결 바이너리를 다시 빌드하거나 과거 빌더를 호출하지 않는다.

`tests/test_no_foreign_paths.py`는 Python, Go, Bash, PowerShell 소스와 실행 설정인 `genconfig.json`에서 다른 세대의 루트와 gen32 빌더 경로를 검사한다. gen33 루트가 이전 세대의 접두사로 오인되지 않는지도 검사한다. 역사 자료 예외는 다음 범위다.

| 위치 | 허용한 이유 |
|---|---|
| `p21_gencompare.py`의 `REGRESSION_STAGE2`, `DEV_DATA`, `DEV_EXT_GLOBS` | 봉인된 결과의 출처와 개발자료를 읽는 목록 |
| `g31_probe.py`의 `GEN3_QUICBED` | 과거 소스 지문을 읽는 위치 |
| `replay_g3.py`의 `P17_DEFAULT` | 과거 p17 저널을 읽는 기본 입력 |
| `test_p21_gencompare.py`의 역사 자료 목록 시험 | 위 목록이 원래 자료를 가리키는지 확인 |
| `g3/v33/archive/tools/create_archive.py` | 보호 원자료를 읽고 보존 폴더에 복사 |
| `g3/v33/archive/tools/archive_wsl.py` | 보호 바이너리를 읽고 최초 동결 사본을 보존 |
| `g3/v33/archive/tools/verify_gen2_origin.py` | git 객체에서 과거 소스를 읽고 출처를 대조 |

Python 역사 경로는 지정한 AST 상수 또는 시험 함수의 문자열에만 허용한다. 같은 파일의 실행 호출까지 허용하지 않는다. S1 도구 예외는 파일명과 SHA-256을 함께 고정한다. 도구가 바뀌면 예외를 다시 검토해야 한다. JSON 결과, 기준 벡터와 보존 기록은 실행 소스 검사 대상이 아니다.

과거 실행 명령이 남아 다른 세대 폴더로 이동하는 일을 막으려고 봉인 러너의 실행 안내를 제거했다. `g3_stage0.py`와 `g3_m1confirm.py`의 기본 CLI, 일회성 소스 패치 두 개, 과거 race 탐침과 진단 셸은 실행 초기에 거부한다. 기존 자동 루프와 비교 러너의 차단도 유지한다. 읽기 전용 재생은 원자료 경로와 gen33 출력 경로를 따로 받는다.

검증 명령은 다음과 같다. 측정 잠금이 있을 때는 실행하지 않는다.

```powershell
python -I -B -m pytest tests/test_gen32_runner_isolation.py tests/test_no_foreign_paths.py -q -p no:cacheprovider
wsl -d Ubuntu -- bash /mnt/c/dev/pq_afec_gen33/experiments/quicbed/build_gen33.sh
wsl -d Ubuntu -- python3 -I -B -m unittest discover -s /mnt/c/dev/pq_afec_gen33/tests -p test_gen32_build_staging.py -v
wsl -d Ubuntu -- python3 -I -B /mnt/c/dev/pq_afec_gen33/experiments/gate_v3_parity.py --out /mnt/c/dev/codex_handoff/v33/runs/manual_parity.json
```

관문 결과는 구현 일치 검증이며 네트워크 성능 측정이 아니다.
