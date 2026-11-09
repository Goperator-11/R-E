# 재현 절차

이 문서는 gen33 저장소(v3.3.1-dev)의 Python 시험, Go 빌드와 시험, 정책 관문, 시뮬레이션 재판정, 봉인 대조를 다시 돌리는 방법과 기대 출력을 적는다. 네트워크 측정은 이 문서로 다시 돌리지 않고 조건과 계획 파일만 7절에 연결한다. pytest 수와 Go 시험 수는 측정이 끝난 뒤 통합 관문에서 다시 재서 채우고, F65가 최종 커밋 기준 값으로 바꾼다. 다른 문서에 적힌 시험 수는 그 문서를 쓴 날의 값이다(docs/README 5절 규칙).

명령은 PowerShell에서 저장소 루트로 이동한 뒤 친다. `<새 출력 파일>`과 `<새 출력 폴더>`에는 저장소 밖 임시 폴더 안의 아직 없는 경로를 준다. 저장소 안이나 동결 세대 폴더를 출력 위치로 쓰지 않는다. `<qamp>`는 검사할 Go 바이너리의 WSL 경로다.

## 0. 명령 표

| 확인 | 명령 | 기대 출력 | 마지막 확인 |
|---|---|---|---|
| 전체 검증 한 번에 | `python -I -B tools/final_check.py --out <새 출력 파일>` | 마지막 줄 `{"passed": true, ...}`, rc 0. 측정 잠금이 있으면 아무것도 시작하지 않고 rc 2. pytest 수와 Go 수는 통합 관문 값으로 채움 | 2026-11-07, HEAD `ed71b1780`, `--install` 실행에서 passed true, 재시도 없음 |
| Python 시험 | `python -I -B -m pytest -q -p no:cacheprovider` | passed, skipped, deselected, subtests 네 수는 통합 관문 값으로 채움. failed 없음 | 2026-11-07 설치 검증에서 failed 없음 |
| Go vet, 시험, race, 빌드 | `wsl -d Ubuntu -- bash experiments/quicbed/build_gen33.sh --race` (실제 HOME으로 돌리면 설치본이 바뀌므로 먼저 3절을 읽는다) | `gen33 vet passed`, `gen33 race passed`, `gen33 build passed`, `gen33 tests pass <PASS 수> skip <SKIP 수>`. PASS 수와 SKIP 수는 통합 관문 값으로 채움. FAIL 0, race 보고 0 | 2026-11-07 설치 검증, FAIL 0, race 보고 0 |
| Python과 Go 정책 결정 일치 | `python -I -B experiments/gate_v3_parity.py --bin <qamp> --out <새 출력 파일>` | `"pass": true`, `"problems": []`, primitives 2800/2800, decisions 6720/6720, trajectories 5/5, fresh seed 20261005 | 2026-11-07 설치 검증 |
| L1 관문 | `wsl -d Ubuntu -- python3 -I -B experiments/gate_l1_go.py --ref g3/v33/V33FIX_policy_reference_v3.json --bin <qamp> --out <새 출력 파일>` | `"passed": true`, `"problems": []`, counts의 leaves 738663, bit_exact 738663, failures 0 | 2026-11-07 설치 검증 |
| 정책 참조 확인 | `wsl -d Ubuntu -- python3 -I -B g3/policy3_reference_gen.py --check` | `check: identical`, rc 0 | 2026-11-07 설치 검증 |
| credit과 parity wire 크기 | build stage 안에서 `go test -count=1 -run 'TestPolicyCreditMatchesDecoder|TestParityWireSize' -v ./cmd/qamp` (stage는 WSL 안에만 있다, 로컬 보존) | `--- PASS: TestPolicyCreditMatchesDecoder`, `--- PASS: TestParityWireSize`, `ok` | 2026-11-07 설치 검증의 전체 Go 실행에서 두 시험 PASS |
| 봉인 대조 | R-E 루트에서 6절의 첫 명령 | `"status": "PASS"`, files 107, matches 107, sha256_section_files 71 | F60(2026-11-07)과 이 문서 작성 때 R-E final 작업 트리. 공개 사본 확인은 F66 |
| 봉인 판정 재계산 | `python -I -B report_repro/recompute_v3_verdicts.py --out <새 출력 폴더>` | 한 줄 JSON에 items 18005, max_abs_diff_ms 0.0, all_verdicts_match true, seal_files 71, seal_mismatches 0, archive_entries 250. rc 0 | 2026-11-06 F05 기록 `report_repro/v3_verdict_recompute.json`, `report_repro/seal_rehash.json` |
| 측정 계획 v1 dry-run | `python -I -B experiments/v33/devbed.py --plan g3/v33/plans/final_bundle_v1.json --dry-run` | rc 0, stdout JSON의 schema `padfec3.devbed.dry_run/1`, kind "계획, 측정값 아님", plan_sha256 `74f58fbb6b0db5c30ef9abf0698ae13dd6bede861bef3215646e5ca3232154b6` | 이 문서를 쓸 때 실행하지 않았다. 측정 뒤 실행 |
| 측정 계획 v2 dry-run | `python -I -B experiments/v33/devbed.py --plan g3/v33/plans/final_bundle_v2.json --dry-run` | 위와 같은 schema와 kind, plan_sha256 `c34edb890fbdc1fd5685f189cf8b9629ae9e7339c27fa1365a42e9221bc8829b` | 이 문서를 쓸 때 실행하지 않았다. 측정 뒤 실행 |

마지막 확인 칸의 "2026-11-07 설치 검증"은 `tools/final_check.py --install`을 HEAD `ed71b1780`에서 돌린 한 번의 실행이다. 그 실행의 결과 JSON과 단계별 로그는 로컬 보존이다. plan_sha256은 계획 파일 바이트의 SHA-256이며 devbed가 같은 방식으로 계산한다.

## 1. 환경

Windows 쪽은 Python 3.14(이 PC는 3.14.2)와 [requirements.txt](../requirements.txt)의 고정 판(pytest 9.0.3, matplotlib 3.10.8, cryptography 50.0.1, scipy 1.18.1)을 쓴다. `pytest.ini`는 `tests` 폴더만 모으고 `historical` 표지가 붙은 시험을 뺀다.

WSL은 Ubuntu 배포판을 쓴다. 이 문서를 쓸 때 `wsl -l -v`로 본 이 PC의 WSL 기본 배포판은 kali-linux여서 `wsl`만 치면 다른 배포판에서 돈다. 모든 WSL 명령에 `wsl -d Ubuntu`를 붙인다. PowerShell에서 저장소 루트로 이동한 뒤 `wsl -d Ubuntu -- <명령>`을 치면 WSL의 작업 폴더가 같은 저장소가 된다. 같은 때 이 PC에서 `wsl -d Ubuntu --cd .`는 E_INVALIDARG로 실패했다.

Git Bash(MSYS)에서 wsl을 부르면 슬래시(/)로 시작하는 인자가 Windows 경로로 바뀔 수 있다. 이 문서의 명령은 PowerShell 기준이고, Git Bash에서 칠 때는 `MSYS_NO_PATHCONV=1`을 앞에 붙인다.

Go는 1.26.6(`experiments/quicbed/go.mod`의 `go 1.26.6`), quic-go는 v0.61.0이다. 빌드는 `GOPROXY=off`, `GOTOOLCHAIN=local`, `GOFLAGS=-mod=readonly`로 하므로 모듈이나 toolchain을 내려받지 않는다. 설치 상태는 `wsl -d Ubuntu -- bash tools/bootstrap_wsl.sh --check`(Go 1.26.6, ip, tc, unshare, 분리한 namespace의 netem)와 `python -I -B tools/doctor.py`(Python, 패키지, Go, 경로, autocrlf, 고른 WSL 배포판)로 확인한다. doctor.py는 문제를 찾으면 rc 1을 낸다.

## 2. Python 시험

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -I -B -m pytest -q -p no:cacheprovider
```

기대 출력은 `<passed> passed, <skipped> skipped, <deselected> deselected, <subtests> subtests passed` 한 줄이고 failed는 없다. 네 수는 통합 관문 값으로 채움. 건너뛰는 시험은 Windows에서 돌지 않는 WSL staging 시험이고, 빠지는 시험은 봉인된 옛 트리나 막아 둔 옛 실행기를 전제로 하는 `historical` 표지 시험이다. staging 시험은 `wsl -d Ubuntu -- python3 -I -B tests/test_gen33_build_staging.py`로 따로 돌린다. `tools/final_check.py`도 같은 명령으로 돌리고 두 시험이 모두 실행돼 OK여야 통과로 본다.

시험은 이 저장소나 그 사본에서만 돌린다. 동결 세대 폴더(pq_afec, pq_afec_gen3, pq_afec_gen31, pq_afec_gen32)에서 시험을 돌리면 보호 폴더 안에 파일을 쓰게 된다(DC-05).

`tests/test_v33_policy_worker.py`는 2026-11-02부터 저장소 밖 임시 폴더를 쓰고 끝나면 지운다. 그 전에 쌓인 experiments/state/v33_worker_test_artifacts 아래 source-* 폴더는 gitignore 대상으로 남아 있다(로컬 보존, `docs/S5_test_hygiene.md`). Go 시험은 `QAMP_PRESERVE_TEST_ARTIFACTS=1`일 때만 WSL 홈의 quicbed_gen33/test_artifacts에 결과를 남기고, 아니면 Go 임시 폴더를 쓴다(`experiments/quicbed/qamp_preserved_test.go`).

## 3. Go 빌드와 시험

`experiments/quicbed/build_gen33.sh`는 WSL에서 돈다. 실행할 때마다 `$HOME/quicbed_gen33/stage.XXXXXX`에 새 stage를 만들고 Go 소스와 시험 파일을 복사한 뒤 vet, 전체 Go 시험, `--race`를 주면 race 시험, `-trimpath -buildvcs=false` 빌드를 차례로 한다. 시험 기록은 stage의 build_record 폴더에 go_test.txt와 go_race.txt로 남는다(로컬 보존). 빌드 뒤 qamp, qamp.sha256, qamp.srcsha, qamp.buildinfo를 `$HOME/quicbed_gen33/bin/`과 `QAMP_GEN33_OUT`(기본값은 WSL의 /tmp 아래 qamp_gen33)에 복사한다. 시험이나 race가 실패하면 rc 4, 사용법이 틀리거나 빌드 목록에 없는 Go 파일이 있으면 rc 2다.

실제 HOME으로 돌리면 설치본 `~/quicbed_gen33/bin/qamp`가 새 빌드로 바뀐다(로컬 보존). gate_v3_parity의 기본 `--bin`이 [genconfig.json](../genconfig.json)에 적힌 이 설치본이다. 설치본을 그대로 두려면 `tools/final_check.py`를 `--install` 없이 쓴다. 이 도구는 임시 HOME, GOPATH, GOCACHE, QAMP_GEN33_OUT을 만들고, GOROOT와 GOMODCACHE만 이 PC 사용자 홈의 기존 goroot와 gopath/pkg/mod를 가리키게 한다. 다른 PC에서는 이 두 값을 그 PC의 설치에 맞춘다. 설치본 교체는 `--install`을 줄 때만 한다.

`GEN33_KEEP_STAGES`가 기본값 0이면 옛 stage를 지우지 않는다. 양수 N이면 새 stage를 포함해 최근 N개만 남기고 나머지 stage 폴더를 지운 뒤 WSL의 quicbed_gen33/pruned_stages.log에 적는다(로컬 보존). `tools/final_check.py`는 이 변수를 지운 환경에서 빌드한다.

기본 Go 시험에서 건너뛰는 시험은 `TestHoldPythonReadFromReference`와 `TestUDPHoldPythonReadBatchReference`다. 두 시험은 `M1_REFERENCE_GZIP`에 M1 wire 기준 파일을 줘야 돈다. `tools/final_check.py`는 기준 파일 `g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz`가 있으면 build stage에서 두 시험만 따로 돌려 둘 다 PASS이고 skip이 없어야 통과로 본다(로컬 보존). 이어서 `experiments/quicbed/cli_tests/run_cli_tests.sh`로 CLI 배선 시험을 임시 stage에서 돈다. CLI 시험의 PASS 수는 통합 관문 값으로 채움, FAIL은 0이어야 한다.

stage 안에서 특정 시험만 돌릴 때는 빌더와 같은 환경을 맞춘다.

```bash
cd ~/quicbed_gen33/stage.XXXXXX
export PATH="$HOME/goroot/bin:$PATH" GOPATH="${GOPATH:-$HOME/gopath}"
export CGO_ENABLED=0 GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
go test -count=1 -run 'TestPolicyCreditMatchesDecoder|TestParityWireSize' -v ./cmd/qamp
```

`TestHoldQUICReferencePathUnusedParityBeforeFirstCrypto`는 부하가 있을 때 간헐로 `count=2 want=3`으로 실패했다. 시험이 실제 타이머와 실제 UDP로 경로를 흉내 내서, 스케줄링 지터가 hold margin 1 ms를 넘으면 deadline이 마지막 original보다 먼저 터졌기 때문이다. FLK-01(커밋 `948dafe85`)은 첫 flight 동안 시험의 hold 시계를 도착 datagram의 serialization 시간으로만 진행시켜 이 원인을 고쳤다. FLK-02(커밋 `5e870f1b7`)는 같은 시험 묶음에서 첫 flight가 1 ms flush 타이머 때문에 k=1로 나가던 경합을 고쳤다. 두 커밋은 시험 파일만 바꿨다.

재시도 규칙은 `tools/final_check.py`에 그대로 남아 있다. 첫 빌드가 rc 4이고, 실패한 시험이 이 시험 하나뿐이고, 출력에 `count=2 want=3`이 있고, race, panic, fatal error, 빌드 실패, timeout, 공간 부족, kill, undefined 같은 다른 오류가 없을 때만 Go 빌드 전체를 한 번 다시 돈다. 두 번째도 실패하면 검증 실패다. FLK-01 뒤 2026-11-07에 돌린 `tools/final_check.py` 전체 실행 세 번(HEAD `086ee5e32` 한 번, `ed71b1780` 두 번)에서는 재시도가 없었다. 세 번의 통과는 간헐 실패가 사라졌다는 확증이 아니므로 재시도 규칙을 지우지 않았다.

## 4. Python과 Go 관문

두 관문은 네트워크 측정이 아니다. Python 정책(`padfec3/learn3.py`, `padfec3/decide3.py`, `padfec3/layout.py`)과 Go 거울(`experiments/quicbed/policy3.go`, `experiments/quicbed/policy3_l1.go`)이 같은 입력에서 같은 결정과 상태를 내는지 본다.

`experiments/gate_v3_parity.py`는 Windows에서 부르면 스스로 `wsl -d Ubuntu`로 다시 돈다. 기본 `--ref`는 `g3/policy3_reference.json`이다. 기본 `--out`은 저장소 안 experiments/results 아래 파일이므로 항상 `--out`에 저장소 밖 새 파일을 준다. 폴더를 주면 시작 전에 거부한다. 같은 폴더에 gate_v3_fresh로 시작하는 fresh 입력 파일도 남는다.

`experiments/gate_l1_go.py`는 WSL에서 직접 부른다. `--ref`, `--bin`, `--out`을 모두 줘야 하고 `--out`이 이미 있으면 거부한다. 참조는 CX1 커밋 뒤 다시 만든 `g3/v33/V33FIX_policy_reference_v3.json`(SHA-256 `fba752a6d5ba07d5e6e994b9b5e210da0c98a0b7e21a0bdf64ce56177be08ba6`)을 쓴다. v1과 v2 참조, receipt는 이력으로 남겨 두었고 관문에는 쓰지 않는다.

`g3/policy3_reference_gen.py --check`는 v3 참조를 메모리에서 다시 만들어 `g3/policy3_reference.json`과 비교만 한다. `--check` 없이 부르면 커밋된 참조 파일을 덮어쓴다.

설치본은 아래 명령으로 확인한다. 기대 출력은 `qamp: OK`와 srcsha 한 줄이다.

```powershell
wsl -d Ubuntu -- bash -c 'cd ~/quicbed_gen33/bin && sha256sum -c qamp.sha256 && cat qamp.srcsha'
```

2026-11-07 설치본과 동결본(로컬 보존 ~/frozen/gen33_b44f3681/qamp)은 sha256 `b44f36811da480571c30c3312fdf12294b2e37942fac26c89649882cd1dac9da`, srcsha `2f08eb7e9b531597f45a93227fd0405dec7599e61f6a1f43f2cbcd3d1e040325`, 소스 커밋 `ed71b1780`이다. 이 문서를 쓸 때 위 명령의 출력도 `qamp: OK`와 이 srcsha였다. 측정 계획 v1의 gen33 팔은 앞선 동결본(sha256 앞 8자리 63854e33, srcsha 앞 8자리 8e3c0960)을 썼다. 관문 결과 JSON의 binary 칸에도 검사한 바이너리의 sha256과 srcsha가 남는다.

## 5. 시뮬레이션 재판정

여기 도구는 W0 세계 개발 시뮬레이션과 기록 재생이다. 실제 네트워크 측정 결과가 아니다. 원자료는 저장소에 넣지 않았고 루프 기록 폴더에 있다(로컬 보존).

결정 재생은 `python -I -B experiments/v33/v33fix_replay.py --out <새 출력 파일>`이다. `--runs` 기본값이 이 PC의 루프 기록 폴더라 다른 PC에서는 원자료 위치를 준다. 2026-11-07 재생 결과는 none 411000/411000 일치, c1 410997/411000 일치였고 c1의 불일치 3개는 모두 첫 C1 회신 전 연결이었다. 직전 재생 결과와 같았고 그 결과 파일은 로컬 보존이다. 저장소 기록은 `g3/v33/V33FIX_replay_v1.json`이다.

V33FIX 폐루프 비교와 B6 반복은 `experiments/v33/v33fix_rejudge.py`의 snapshot, collect, compare, repeat, repeat-judge, evaluate 순서로 만든다. 명령 전체는 `docs/V33FIX_evaluation.md` 11절에 있다. 원자료(폐루프 158 MB, 반복 208 MB)는 로컬 보존이다. evaluate의 `--out`에 저장소 안 `g3/v33/V33FIX_benchmark_v1.json`을 주면 기록을 덮으므로 저장소 밖 새 파일을 준다. snapshot은 실행할 때의 정책 코드를 복사하므로 지금 HEAD로 다시 돌린 값이 V33FIX 기록과 같은지는 확인하지 않았다.

J6 재판정은 `python -I -B experiments/v33/v33fix_j6_rejudge.py --out <새 출력 파일>`이다. 원자료 위치는 스크립트 안에 고정돼 있고(로컬 보존), `--out`이 이미 있으면 거부한다. 실행 전에 `docs/V33FIX_bench_rules.md` 1절 본문의 SHA-256을 `experiments/v33/zero_variance.py`의 등록값과 대조하므로 그 문서를 고치면 돌지 않는다(9절 표). 저장소 기록은 `g3/v33/V33FIX_J6_rejudge_v1.json`이고, 당시 저장된 14개 대조를 14/14 재현한 뒤 Z1을 적용했다(`docs/V33FIX_world.md`).

## 6. 봉인 대조

봉인 대조는 R-E 저장소 루트에서 돈다. gen33 저장소에는 이 도구가 없다.

```powershell
python -I -B tools/verify_seals.py
```

기대 출력은 `"status": "PASS"`, files 107, matches 107, sha256_section_files 71이다. 봉인별로는 gen31 SEAL_stage3 45/45, gen3 SEAL_stage2 38/38, SEAL_stage0 9/9, SEAL_m1confirm 15/15다. F60(2026-11-07)과 이 문서를 쓸 때 R-E final 작업 트리에서 이 값을 얻었고, F60은 `core.autocrlf=true` 기본 설정의 새 clone에서도 같은 값을 얻었다. R-E 루트의 .gitattributes가 줄바꿈을 LF로 고정하기 때문이다. 공개 사본에서의 실행 확인은 F66이 한다.

gen33의 `report_repro/recompute_v3_verdicts.py`는 보존 저널과 봉인 모듈로 v3.0, v3.1 판정을 읽기 전용으로 다시 계산하고 봉인 71개 파일을 다시 해시한다. 입력은 `REPORT_DATA_ROOT`(기본값은 저장소의 부모 폴더) 아래 동결 세대 폴더와 padfec_archive 보존본에서 찾는다(로컬 보존). `--out`은 아직 없는 폴더여야 하고 봉인 폴더나 보존본 안이면 거부한다. 판정이 모두 같고 최대 차이가 1e-6 ms 미만이며 봉인 파일 71개가 모두 맞을 때만 rc 0이다.

## 7. 측정 조건

측정은 재현 명령 표에 넣지 않는다. 다시 재려면 측정 잠금과 launcher 절차(`docs/FINAL_launcher.md`, `docs/FINAL_devbed.md`)를 따른다. 표의 devbed 행은 `--dry-run`이라 계획을 읽고 요약만 출력한다.

조건은 `docs/T7_conditions_v31.md`와 계획 파일 `g3/v33/plans/final_bundle_v1.json`(M0, M1, X1, X9, X6), `g3/v33/plans/final_bundle_v2.json`(M0, X6 탐색 재측정)과 각 `.md` 설명을 따른다. 두 계획의 공통 조건은 다음과 같다. D50대로 W는 1280 B이고 `-ips`를 주지 않는다. parity datagram 상한은 1452 B, timeout은 10 s, quic-go v0.61.0 서버의 initial congestion window는 32 packet이다. 손실은 Bernoulli이고 X9만 양방향, 나머지는 c2s만이다. netem 지연은 방향마다 RTT/2, 정책 uplink 입력은 netem 대역과 같은 값이며 token과 session resumption은 끈다. 모든 측정은 label development이고 확증 측정이 아니다.

결과 문서는 `docs/M0_result.md`, `docs/M1_result.md`, `docs/X1_result.md`, `docs/X9_result.md`, `docs/X6_result.md`, `docs/M0S_result.md`다. 계획 v2의 X6 재측정 결과 문서는 측정이 끝난 뒤 더한다.

## 8. R-E에 없는 것

R-E의 pq_afec_gen33 사본에서 빠진 것과 그 영향은 다음과 같다.

`g3/v33/validation`은 J1, J6, L1_precision, L2, L3, L5 최종 분석 묶음의 `.py` 파일과 M1_stage2_validation만 들어간다(로컬 보존). 그래서 M1 wire 기준 파일이 없고, `tools/final_check.py`는 M1 단계를 skip으로 적으며 두 M1 시험은 기본 Go 시험에서처럼 건너뛴다.

.github 폴더는 내보내지 않는다. gen33의 CI 초안은 R-E에 없다.

gen33의 git 이력은 내보내지 않는다. 그래서 R-E 사본에서 `tools/check_docs.py`는 기준 커밋 `feb0b1850` 비교를 건너뛰고 "기준 커밋 없음"을 출력한다(9절).

WSL 설치본과 동결 바이너리, build stage, padfec_archive 보존본, 루프 기록 폴더의 원자료, 측정 원자료는 이 PC에만 있다(로컬 보존). 그래서 R-E 사본만으로는 바이너리를 먼저 빌드해야 관문을 돌릴 수 있고, 봉인 판정 재계산, 결정 재생, V33FIX와 J6 재판정은 돌릴 수 없다. `tools/final_check.py`의 측정 잠금 경로와 Go 환경 경로도 이 PC 기준으로 코드에 고정돼 있다.

## 9. 고정된 문서와 봉인 목록

아래 파일에는 용어 치환이나 머리말 추가를 하지 않는다. 저장소 안의 문서는 기준 커밋 `feb0b1850` 이후 차이가 있으면 문서 검사가 실패한다. 기준 커밋이 없는 배포 사본에서는 그 비교를 생략하고 이유를 출력한다. 바깥 세대의 봉인 목록은 로컬 보존 대상이며 보호 경로 검사와 별도 봉인 재해시로 확인한다.

| 파일 | 누가 읽나 | 무엇이 깨지나 | 고쳐도 되는가 |
|---|---|---|---|
| `docs/V33FIX_bench_rules.md` | `experiments/v33/zero_variance.py` | Z1 절의 등록된 해시가 달라져 영분산 재판정이 거부된다. | 고치지 않는다. Z1 절을 포함해 현재 파일을 보존한다. |
| `docs/J6_preflight_budget.md` | `experiments/v33/v33fix_j6_rejudge.py` | 판정 결과에 기록하는 규칙 출처와 줄 번호가 맞지 않게 된다. | 고치지 않는다. |
| `docs/M1_mc_contract.md` | `experiments/v33/bench_m1_family.py` | family 계획의 입력 해시와 보존한 계약이 달라진다. | 고치지 않는다. |
| `docs/J5_ge_contract.md` | `experiments/v33/ge_reference_report.py` | 참조 계산의 출처 해시가 달라진다. | 고치지 않는다. |
| `docs/J5_world_diagnostic_plan.md` | `experiments/v33/ge_world_diagnostic.py`, `g3/v33/plans/J5_world_v1.json` | 고정된 세계 진단 계획의 문서 해시와 달라진다. 현재도 옛 계획의 해시와 일치하지 않는다. | 고치지 않는다. 정책 코드 변경 뒤의 옛 계획이라 다시 돌리지 않는다. |
| `docs/O2_uplink_contract.md` | `experiments/v33/uplink_reference_report.py` | 참조 계산의 출처 해시가 달라진다. | 고치지 않는다. |
| `docs/O2_world_diagnostic_plan.md` | `experiments/v33/uplink_world_diagnostic.py`, `g3/v33/plans/O2_world_v1.json` | 고정된 세계 진단 계획의 문서 해시와 달라진다. | 고치지 않는다. |
| `../pq_afec_gen3/g3/SEAL_stage0.json` | 당시 봉인 검사와 `report_repro/recompute_v3_verdicts.py` | 기준 해시 목록 자체가 달라져 당시 자료와의 대조 기준을 잃는다. | 고치지 않는다. 로컬 보존. |
| `../pq_afec_gen3/g3/SEAL_m1confirm.json` | 당시 봉인 검사와 `report_repro/recompute_v3_verdicts.py` | 기준 해시 목록 자체가 달라진다. | 고치지 않는다. 로컬 보존. |
| `../pq_afec_gen3/g3/SEAL_stage2.json` | 당시 봉인 검사와 `report_repro/recompute_v3_verdicts.py` | 기준 해시 목록 자체가 달라진다. | 고치지 않는다. 로컬 보존. |
| `../pq_afec_gen31/g3/SEAL_stage0.json` | 이전 단계의 보존 사본과 당시 봉인 검사 | 이전 단계의 기준 목록을 바꾸게 된다. | 고치지 않는다. 로컬 보존. |
| `../pq_afec_gen31/g3/SEAL_m1confirm.json` | 이전 단계의 보존 사본과 당시 봉인 검사 | 이전 단계의 기준 목록을 바꾸게 된다. | 고치지 않는다. 로컬 보존. |
| `../pq_afec_gen31/g3/SEAL_stage2.json` | 이전 단계의 보존 사본과 당시 봉인 검사 | 이전 단계의 기준 목록을 바꾸게 된다. | 고치지 않는다. 로컬 보존. |
| `../pq_afec_gen31/g3/SEAL_stage3.json` | 당시 봉인 검사와 `report_repro/recompute_v3_verdicts.py` | 기준 해시 목록 자체가 달라진다. | 고치지 않는다. 로컬 보존. |

J5 문서에는 과거 재전송 기본값을 설명하는 정정 줄이 들어 있다. 그 문서와 옛 계획의 해시 차이는 새 계획을 만들거나 기준을 바꿔 덮지 않는다. 당시 진단의 출처와 재실행 제한으로 남긴다.

봉인 재계산은 보존 저널을 읽고 새 출력 폴더에만 결과를 만든다. 재계산 도구와 출처 경로는 `report_repro/recompute_v3_verdicts.py`와 `report_repro/source_paths.json`에서 확인할 수 있다. 이 목록은 봉인된 모든 입력 파일을 열거한 표가 아니라, 입력 해시를 정한 문서와 봉인 목록 파일을 보호하는 표다.
