# S5 시험 정리와 재현 도구

2026-11-01, 반복 62. 로컬 개발 검증이다. GitHub에서 CI를 실행하거나 원격 저장소에 올리지 않았다.

기본 pytest는 Windows에서 1,792개 통과와 2개 건너뜀, Ubuntu에서 1,794개 통과를 기록했다. 두 환경 모두 하위 검사 4,513개가 통과했고 historical 32개는 선택하지 않았다. Windows에서 건너뛴 두 빌드 스테이징 검사는 Ubuntu에서 실행됐다. 결과 정본은 `S5_pytest_current_v5.results.json`, `S5_pytest_linux_v5.results.json`이다.

기준선은 1,818개를 수집해 33개가 실패했다. 그중 32개는 gen33에 없는 과거 봉인 자료 또는 의도적으로 막은 옛 실행기를 전제로 했다. 감사 당시 29개와 현재 수가 다르다. 각 함수의 이유는 `S5_historical_inventory_v2.json`에 남겼다. 삭제하지 않고 `historical` 마커를 붙였다. gen31 소스 줄 위치 검사는 별도 함수로 옮겨 현재 플래그 검사를 계속 실행한다. 옛 CLI가 파일·프로세스·네트워크 작업을 하기 전에 거부하는 검사도 기본 시험에 남아 있다.

나머지 기준선 실패는 보존한 실패 스크립트까지 현재 소스로 해석한 경로 검사였다. `tests/test_no_foreign_paths.py`와 `tools/lint_ast.py`는 현재 소스와 보존 자료를 구분한다. AST 검사는 현재 Python 311개를 통과했고 compileall을 호출하지 않는다. `experiments/loop2.py`의 gen33 사본만 이 검사를 사용한다. 옛 실행기를 다시 활성화하지 않았다.

테스트의 절대 경로를 저장소 상대 경로로 바꿨다. 기존 검증 묶음의 분석 스크립트는 원본과 SHA가 같은 사본을 읽는다. 별도 입력 묶음 `g3/v33/fixtures/S5_test_inputs_v1`에는 입력 44개, 1,203,485 B와 manifest·속성 파일이 있다. gen31·gen32 정책 사본 38개, 실제 Initial 패킷 발췌 2개, J7 seed 31의 원자료 4개다. 원본 경로·SHA와 발췌 행·상대편 연결 선택은 manifest에 적었다. 이 사본은 단위 시험 입력이며 동결 벤치 계획의 원자료를 대체하지 않는다.

후보 검사 5개는 자식 pytest의 pythonpath를 비우고 실제 import 경로가 후보 사본 안인지 확인한다. `pytest.ini`를 처음 추가했을 때 활성 정책이 후보보다 먼저 import된 회귀를 이 검사로 고쳤다. J7 보고서 검사는 실제 1,350연결 추적을 임시 단일 seed 묶음에 배치한다. 정상 입력의 성공을 먼저 확인한 뒤 여섯 필드 변조를 거부한다. 계획 로더와 계획 해시만 단위 시험 경계에서 바꾼다.

시험 중 임시 파일 삭제는 보존 어댑터로 옮겨 저장했다. 초기 Windows 심벌릭 링크 처리와 Linux DrvFs capture 핸들 충돌은 수정 전 로그를 남기고 해결했다. Ubuntu에서 옛 전체 트리 순회가 오래 걸린 진단 실행 한 번은 중단했다. 현재 소스만 순회한 최종 실행은 153.56초, Windows는 125.75초였다. 성능 벤치 결과로 쓰지 않는다.

`afec/rs.py`의 단일 parity 계수를 XOR과 같게 했다. 독립 바이트 XOR과 k=1,2,3,16,255에서 복구 25경우를 확인했다. 비용·선택 정책, 활성 L1 상태 형식 4, Go 소스, W0 세계와 매개변수는 바꾸지 않았다. 따라서 W1 정책 벤치와 Python/Go 정책 일치 관문은 다시 실행하지 않았다. 형식 차이는 `docs/R3_codec_format.md`에 기록했다.

Go 1.26.6과 quic-go v0.61.0으로 실제 빌더의 vet, Go 시험(PASS 231, SKIP 2, 감사 시점. SKIP 2개는 `M1_REFERENCE_GZIP`이 있어야 도는 M1 와이어 관문이다), 별도 hook 시험과 빌드를 통과했다. 바이너리 SHA-256은 `41424293588fde08d02a8821b4945ac07f4d0016c61480e0ee2db78936323dae`, 소스 지문은 `9798aa226a1a1246f425bfbe407e173e7d0b5b4324e22b92146bfdd8682b009a`다. 보존 stage는 `/home/scien/quicbed_gen33/stage.mBIfxw`다. `/tmp` 경로의 다음 호출에서는 파일이 없어 영속 경로 `/home/scien/quicbed_gen33/bin/qamp`로 지문을 확인했다. 빌더 검사는 GOFLAGS=-mod=readonly, GOTOOLCHAIN=local, GOPROXY=off와 go.mod/go.sum 불변도 확인한다. `build_server.sh`는 이미 즉시 거부하므로 유지했다.

CI 초안은 Ubuntu, Python 3.14.4와 고정 requirements를 쓰며 AST 검사, 기본 pytest, 고정 Go 1.26.6 빌드를 연결한다. Windows 로컬 Python은 3.14.2였다. actions 태그를 공식 저장소에서 확인한 뒤 커밋으로 고정했다. checkout v7은 `3d3c42e5aac5ba805825da76410c181273ba90b1`, setup-python v7은 `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`, setup-go v7은 `b7ad1dad31e06c5925ef5d2fc7ad053ef454303e`다. 사용법 출처는 https://github.com/actions/setup-python 과 https://github.com/actions/setup-go 이다. 로컬 Ubuntu 결과를 GitHub 실행 결과로 간주하지 않는다.

`tools/doctor.py`는 Python·패키지·Go·경로·autocrlf·PADFEC 설정과 선택한 WSL 배포판을 기록한다. 기본 배포판은 Ubuntu이며 Windows에서는 명시적으로 선택한다. `tools/bootstrap_wsl.sh --check`는 설치된 Go 1.26.6, ip·tc·unshare와 분리된 네임스페이스의 netem 1 ms 설정을 통과했다. 호스트 qdisc는 바꾸지 않았다. 이 PC에서는 설치나 Go 다운로드를 하지 않았다. 새 설치 모드는 공식 https://go.dev/dl/?mode=json&include=all 에서 확인한 Linux amd64 아카이브 SHA `708effb774be8237570d0add163225abbdfaf4fca28b2611df167beba4feef89`를 검사하고 기존 설치를 덮어쓰지 않는다.

`tools/runtime_fingerprint.py`는 상대 경로별 내용 해시인 code_fp와 환경을 기록하는 env_fp를 나눈다. 이번 비교에 지정한 파일은 rs.py, learn3.py, worldsim.py, 도구 자체의 네 개다. Windows/Ubuntu 사이에서 코드 같음, 환경 다름, 재사용 불가, 환경에 따른 재측정 권고를 구분했다. 이것은 전체 연구 입력 지문이 아니다. 새 실행기는 실제 입력 전체를 명시해야 한다. Linux 비교 당시 PATH에 Go가 없어 Go 실행 파일은 null로 기록됐고 별도 doctor·빌드 기록에서 도구체인을 확인했다. 기존 동결 실행기의 지문·재개 판단은 바꾸지 않았다.

`tools/raw_io.py`는 새 결과의 .json.gz/.jsonl.gz 쓰기와 읽기를 제공한다. gzip 시각과 파일명은 고정하고 기존 경로 덮어쓰기를 거부한다. 기존 원자료는 변환하지 않았다. gen33의 로컬 pre-commit은 작업 파일 대신 index blob을 검사해 20,000,000 B 초과 파일과 완전한 PEM 개인키 블록을 거부한다. 원래 다른 훅이나 hooksPath는 없었다. 크기·키·압축·지문 관련 여섯 시험이 전체 시험에 포함됐다.

공개 전 읽기 전용 검사는 추적 텍스트 102,641개를 읽었다. 사용자 경로가 든 파일 19,815개, 이메일 파일 2개와 개인키 헤더 1개를 찾았다. 마지막 헤더는 시험 문자열이며 실제 PEM 파일이 아니다. 이 수치는 증거 묶음을 추가하기 전 스냅숏이고 공개 가능 판정이 아니다. 최초 검사에서 찾은 T1 시험용 개인키 PEM 28개, 1,880,048 B는 `C:\dev\codex_handoff\v33\private\S5_T1_keys_v1`에 해시를 검증해 보존하고 git rm으로 현재 추적을 제거했다. T1 원래 manifest를 고치지 않고 `private_key_exclusion_v1.json`을 덧붙여 차이를 설명했다. 기존 커밋에는 사본이 남아 있다. D40 기본값에 따라 이력을 다시 쓰거나 공개하지 않는다.

봉인 보고서의 안전한 별도 출력 재계산은 E36, 공개 사본의 경로·이메일·이력과 잔재 정리는 E37로 등록했다. R3/T7의 구조 분할도 미완료다. 보호 경로 검사는 통과했고 앞선 볼트 경고 여섯 개는 그대로다.

## 커밋 전 훅 설치 (2026-11-02 덧붙임)

위에서 말한 20,000,000 B·개인키 거부 훅은 원래 버전 관리 밖의 `.git/hooks/pre-commit`에만 있어서 clone하면 따라가지 않았다(감사 A 검증자 missed 2, H-06). 같은 내용을 `tools/hooks/pre-commit`으로 옮겨 저장소에 넣었다. 두 파일은 `cmp`로 바이트가 같음을 확인했다. 훅은 `tools/precommit_size.py`를 부르고, 그 도구가 index blob 기준으로 크기와 완전한 PEM 개인키 블록을 검사한다.

새로 clone한 사본이나 다른 PC에서는 저장소 루트에서 한 번 실행한다. 이 설정은 `.git/config`에 들어가므로 clone에 따라가지 않는다.

```powershell
git config core.hooksPath tools/hooks
git config --show-origin --get core.hooksPath
git hook run pre-commit
```

gen33 작업 트리에는 2026-11-02에 이 설정을 저장소 로컬로 넣었다. 둘째 줄은 `file:.git/config	tools/hooks`를, 셋째 줄은 올린 파일이 없을 때 `{"status": "PASS", ... "checked": 0, ...}`를 출력했다. 이제 git은 `.git/hooks/pre-commit` 대신 `tools/hooks/pre-commit`을 쓴다. 옛 파일은 지우지 않았다.

스크래치 저장소에서 같은 설정으로 20,000,001 B 파일과 PEM 개인키 블록을 각각 커밋하려 하자 훅이 둘 다 거부했다(종료 코드 1, 커밋 수 변화 없음). 20,000,000 B 이하 파일 두 개의 첫 커밋은 통과했다.

`.gitattributes`의 `tools/hooks/* text eol=lf` 때문에 `core.autocrlf=true` clone에서도 셔뱅 줄이 CRLF로 바뀌지 않는다. Linux·WSL에서 실행 권한이 필요하므로 이 파일을 처음 커밋할 때 `git add --chmod=+x tools/hooks/pre-commit`으로 실행 비트를 기록한다. Windows용 Git은 셔뱅을 보고 실행한다.

훅은 새로 올리는 파일만 본다. 이미 이력에 있는 20 MB 초과 blob 3개와 시험용 개인키 blob 28개는 남아 있고, `git commit --no-verify`로 훅을 건너뛸 수도 있다. 공개 전에는 `python -I -B tools/scrub_for_publish.py --check --history`로 이력 전체를 따로 검사한다.

같은 날 `tests/test_v33_policy_worker.py`의 읽기 전용 감사 시험도 고쳤다. 전에는 실행할 때마다 저장소 안 `experiments/state/v33_worker_test_artifacts/source-*`에 꾸러미 세 개를 만들고 지우지 않았다(감사 A-E5). 이제 저장소 밖 임시 폴더(`tempfile.TemporaryDirectory`)를 쓰고 시험이 끝나면 지운다. 이미 쌓인 `source-*` 폴더 61개는 gitignore 대상이며 지우지 않고 두었다.

## Go 시험 수와 M1 와이어 관문 (2026-11-02 덧붙임)

위 Go 시험 수(PASS 231, SKIP 2)는 HEAD `d67717d9b`의 값이다. SKIP 2개는 `TestHoldPythonReadFromReference`와 `TestUDPHoldPythonReadBatchReference`이고, 환경변수 `M1_REFERENCE_GZIP`으로 기준 파일을 줘야 돈다. 그래서 "Go 231 통과"는 이 두 관문이 빠진 수다.

인용한 보존 stage `~/quicbed_gen33/stage.mBIfxw`는 2026-11-02에 읽기 전용으로 확인했을 때 남아 있었다. 그 안의 `build_record/qamp.sha256`, `qamp.srcsha`, `go_test.txt`(PASS 231, SKIP 2)가 위 값과 같았다. `build_gen33.sh`는 이제 기본으로 stage를 지우지 않는다(`GEN33_KEEP_STAGES` 기본 0, `docs/V33FIX_testbed.md` 통합 정리 절).

2026-11-02 통합 정리 시점의 작업 트리(V33FIX 수정과 정책 묶음 변경 포함)에서 직접 돌린 기본 Go 시험은 PASS 265, SKIP 2, FAIL 1이었다. 실패 1개는 `TestComparisonSameSlotsAndAccounting`이다. 그 시험의 fixture가 빈 retrans-layout 값에 기대고 있어서, fixture에 `original_first`를 명시하는 한 줄 patch를 얹은 사본에서는 PASS 266, SKIP 2, FAIL 0이었다. 세부와 patch 위치는 `docs/V33FIX_testbed.md` 통합 정리 절에 있다. 이 수는 그 시각 작업 트리의 값이다.

M1 와이어 관문 두 시험은 `build_gen33.sh`가 만든 stage 안에서 기준 파일을 주고 돌린다. 기준 파일은 저장소의 `g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz`(sha256 `59b3434763af6af9b776194b6d21b2f421301eeaa357b38eed1c062312c0dbcf`)다. 2026-11-02 작업 트리에서 두 시험 모두 PASS였고, 각각 "700116 actual decoder cases, 60 configurations"를 출력했다(40.27 s, 42.66 s).

```
cd ~/quicbed_gen33/stage.XXXXXX
export PATH="$HOME/goroot/bin:$PATH" GOPATH="${GOPATH:-$HOME/gopath}"
export CGO_ENABLED=0 GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
M1_REFERENCE_GZIP=/mnt/c/dev/pq_afec_gen33/g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz \
go test -count=1 -v -run '^(TestHoldPythonReadFromReference|TestUDPHoldPythonReadBatchReference)$' ./cmd/qamp
```
