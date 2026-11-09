# 최종 루프 구현 검증

## F13: G2 credit와 decoder 전달 바이트

2026-11-06, CP-12가 MS-26과 BL-06을 흡수했다. 이 검증은 송신 순서를 유지한 합성 datagram의 도착 부분집합을 다룬다. 네트워크 측정이나 HCT 검증은 포함하지 않는다.

`experiments/quicbed/qamp_policy_credit_test.go`의 `TestPolicyCreditMatchesDecoder`는 k=1~4, m=1~4, lead=0~m에서 도착 mask를 전수 검사한다. `leadBuildFlight`가 만든 datagram을 `decodeConn.ReadFrom`에 넣고, 실제 반환 바이트를 복사해 각 원본의 전달 여부와 총길이를 확인한다. 도착한 원본 수를 a, lead 수를 la, trail 수를 ta라고 하면 miss=k-a다.

- miss≤ta이면 모든 원본이 반환되고, 반환 바이트 합은 `원본 길이 합 + (la+ta-miss)*pz`다. pz는 생성한 parity datagram의 실제 길이다.
- miss>ta이면 원본 전부가 반환되지 않는다. 복구 대기 parity가 남을 수 있으므로 이 경우 반환 바이트와 물리 수신 바이트가 같다고 단언하지 않는다.

총 3840행 중 원본 전달 완료는 1573행, 미완료는 2267행이었다. 성공 행의 바이트 식 불일치는 없었다. Go 입력은 k≥2일 때 마지막 원본이 1150 B이고 나머지는 1200 B이므로 원본의 실제 길이를 합산한다.

`tests/test_padfec3_layout.py`의 `test_policy_credit_matches_decoder_contract`는 같은 조합 범위에서 각 도착 pattern을 한 번씩 검사한다. W=1200 B, p=0.1, uplink=0 조건에서 pattern으로 도착 수를 계산하고, 성공 조건과 `base_credit=la*pz+k*W`, `len(after_delays)=ta-miss`를 확인한다. 여기서 pz는 모형의 parity 크기다. kind별 행 수는 ok 1573, pto 401, ptoS 1018, ack 848이다. 두 시험은 같은 credit 식을 각각 고정한다. Python과 Go의 원시 바이트를 JSON으로 직접 교환하는 대조는 수행하지 않았다.

`experiments/quicbed/qamp_lead_test.go`의 `TestLeadClientV3RepeatLayout`은 k=4까지 검사한다. W=1280의 parity 크기와 wire 상한 검사는 F12의 `TestParityWireSize`가 맡는다. G2 닫힘 행은 카드 조정에 따라 F45에서 기록한다.

## 결함 주입과 복원

임시 build stage의 `decodeConn.readFrom`에서 복구 성공 분기의 `return m, addr, nil`을 `goto again`으로 바꿨다. 장부 갱신은 남기고 첫 복구 원본의 실제 반환만 막았다. 새 시험은 k=1, m=1, lead=0, mask=2에서 `originals complete false, miss 1 trail arrived 1`로 실패했고 종료 코드는 1이었다. 컴파일은 성공했다.

변형 뒤 원본 파일을 바이트 단위로 복원하고 SHA-256 일치를 확인했다. 복원한 stage에서 새 시험을 다시 실행해 3840행이 통과했다. 변형은 저장소나 설치본에 적용하지 않았다.

## 실행 결과와 재현

| 검사 | 결과 |
|---|---|
| 지정 Go 시험 두 개 | PASS, rows 3840 |
| layout Python 시험 | 24 passed |
| 전체 pytest | 1920 passed, 2 skipped, 32 deselected, 17656 subtests passed |
| 전체 Go 시험 | PASS 272, SKIP 2, FAIL 0 |
| Go vet, race, build | PASS, race 보고 0 |
| 기존 설치 바이너리 해시 | 실행 전후 일치 |

Python 시험과 Go 시험이 각각 하나 늘었다. 처음 Go vet은 새 시험이 embedded 필드를 구조체 literal에 지정해 컴파일 오류로 끝났다. 기존 시험과 같은 별도 대입으로 고친 뒤 위 검사를 통과했다. 정책 산술 파일은 변경하지 않아 정책 전용 관문과 replay 재실행 조건에는 해당하지 않는다.

빌드 바이너리 SHA-256은 `49785ea372101cfaa95312d63dfa5f94af9299472b6a08e1da912eca121068b0`으로 F12와 같고, 시험 파일을 포함한 소스 SHA-256은 `a21e476f218f7bceac87559ec3055033e38bdd80eda7c016e7ad6b5f282004b2`다. F16은 그 시점의 소스 지문을 다시 산출한다.

임시 HOME에서 `experiments/quicbed/build_gen33.sh --race`를 실행한 같은 WSL 호출 안에서 지정 시험, 변형, 복원 시험을 수행했다. 지정 Go 명령은 아래와 같다.

```sh
go test -count=1 -run 'TestPolicyCreditMatchesDecoder|TestLeadClientV3RepeatLayout' -v ./cmd/qamp
```

Python 명령은 `python -I -B -m pytest -p no:cacheprovider tests/test_padfec3_layout.py`와 `python -I -B -m pytest -q -p no:cacheprovider`다.

로컬 보존: 실행 스크립트와 수치 집계는 `C:/dev/codex_handoff/final/runs/F13_go.sh`, `F13_mutation.py`, `F13_collect.py`다. 결과는 같은 폴더의 `F13_summary.json`, `F13_targeted_go.log`, `F13_mutation.log`, `F13_restored_go.log`, `F13_pytest.log`, `F13_go_test.txt`, `F13_go_race.txt`에 있다. 최초 컴파일 실패는 `F13_go_fixture_failed.log`에 보존했다.

## F14: 클라이언트 행과 conn-log의 SCID

MS-29에 따라 공통 trial 행에 `client_scid`를 넣었다. 값은 `fecConn.WriteTo`가 관측한 최초 Initial의 SCID를 소문자 hex로 나타낸 것이다. `clientCIDGenerator`가 생성한 CID 중 실제 Initial에 쓰인 값을 `ownCID`에서 읽는다. 추가 CID 생성이나 후속 flight가 이 값을 바꾸지 않는다.

`snapshot`은 기존 mutex 안에서 SCID를 복사하고, `recordFinalSendStats`는 최종 snapshot의 값을 plain 행과 auto3 행에 전달한다. Initial을 관측하지 못한 실패 행에는 `client_scid`가 빈 문자열로 남는다. CID 생성만으로는 행 값을 채우지 않는다. 여러 연결의 aggregate에는 이 필드를 출력하지 않는다. SCID가 있다는 사실은 socket 송신 성공이나 서버 도착을 보증하지 않는다.

`experiments/quicbed/qamp_flight_trace_test.go`의 새 시험은 실제 CID 생성기를 사용한 off·fec 입력의 행과 합성 conn-log JSON을 대조한다. 회전 뒤 초기 SCID 유지, 다른 연결의 행 값 분리, plain·auto3 JSON 보존과 Initial 없는 실패 행도 검사한다. 이 결과는 단위시험이다. 실제 smoke에서 행과 conn-log의 `client_scid` 일치 100% 기준은 F26에서 확인한다. 연결을 합칠 때는 누락과 중복 식별자를 확인하고 모호한 대응을 행 순서로 채우지 않는다.

| 검사 | 결과 |
|---|---|
| flight trace·최종 통계·CID 회전·JSON 행 계약 대상 시험 | 19 PASS |
| 전체 Go 시험 | PASS 275, SKIP 2, FAIL 0 |
| Go vet, race, build | PASS, race 보고 0 |
| 전체 pytest | 1920 passed, 2 skipped, 32 deselected, 17656 subtests passed |
| 기존 설치 바이너리 해시 | 실행 전후 일치 |
| 실제 smoke 일치 | 미실행, F26에서 확인 |

첫 전체 Go 실행에서 JSON 키 목록 시험이 새 필드를 몰라 실패했다. 기대 목록에 `client_scid`를 추가하고 전체 키 일치 검사는 유지했다. 같은 실행에서 알려진 hold 타이밍 시험의 `count=2 want=3` 실패도 났다. 수정 뒤 전체 재실행과 race는 통과했다. 최초 실패 로그의 로컬 보존 위치는 `C:/dev/codex_handoff/final/runs/F14_go_first_failed.txt`다. 정책 산술 파일은 바꾸지 않았고, `experiments/quicbed/policy3_test.go`는 JSON 키 목록만 바꿨다. 정책 전용 관문과 replay는 재실행 조건에 해당하지 않는다.

임시 HOME에서 `experiments/quicbed/build_gen33.sh --race`와 아래 지정 시험을 같은 WSL 호출 안에서 실행했다.

```sh
go test -count=1 -run 'TestFlightTrace|TestClientCIDRotationIsTrackedAndBounded|TestFinalSendStats|TestAuto3RowAddsFieldsAndLeavesTrialAlone' -v ./cmd/qamp
```

빌드 바이너리 SHA-256은 `942df28cc16335d3973c40e1b09c1d57e5703c625e49f1eb1620ad6948e01a8d`, 시험 파일을 포함한 소스 SHA-256은 `4cbfbe584f47e138c4a910bf65d16335e303b8646a63cad6bffdcbb5bf4ebbfa`다. F16은 그 시점의 소스 지문을 다시 산출한다.

로컬 보존: `C:/dev/codex_handoff/final/runs/F14_go.sh`, `F14_collect.py`, `F14_summary.json`, `F14_targeted_go.log`, `F14_go_test.txt`, `F14_go_race.txt`, `F14_pytest.log`.

## F15: 정책 설명 정리와 참조 갱신

BL-13의 `padfec/policy.py` 변경은 기존 주석과 docstring에 한정했다. 오래된 이득 수치와 CID 오차가 보수적이라는 단정을 결과 파일 안내로 줄였다. docstring을 뺀 AST는 변경 전과 같다. gen-2 원본과 R-E의 동결 사본은 유지하고, 해당 설명의 정오표는 F50에서 기록한다.

CP-16은 호출하지 않는 Python 함수와 Python의 `decide_core`, Go의 `p3DecideCore`에서 선택 인자 `reeval` 및 그 인자에만 의존하는 분기를 제거했다. 실제 주기별 재평가와 c1 경로의 억제, 상태 카운터는 유지한다. 활성 Go의 `p3GuardPenalties`도 유지했다. 상수 이름은 서버 패킷 크기와 Initial 기본 크기를 구분하며, 기존 값과 자료형, 산술 순서를 보존한다.

직접 `shielded` 호출을 제거한 시험은 기존 none의 `info["shielded"]`·`skip`과 c1의 `legacy_shielded`·`legacy_skip_reason`·실제 `skip`을 확인한다. arm1 경로에는 `skip_reason`이 None이라는 단언을 남겼다. 시험 메서드는 줄지 않았다.

코드 정리 뒤 `g3/policy3_reference_gen.py`와 `experiments/gate_l1_go.py --generate g3/v33/V33FIX_policy_reference_v2.json`을 순서대로 한 번씩 실행했다. v3 참조는 소스 지문과 생성 소요 시간만 달라졌고, L1 v2는 v1과 소스 지문만 다르다. 계산값은 모두 같다. v1과 v1 receipt를 보존했으며 v2 receipt와 현재 소스 해시도 일치한다. 이후 L1 관문은 v2를 사용한다. F15 이후 `experiments/gate_l1_go.py`, `experiments/replay_g3.py`, `padfec`, `padfec3`는 변경하지 않는다.

이 원칙은 2026-11-07 CX1 opt-in 커밋(f33040d8b)까지의 범위다. 그 커밋이 `padfec3/learn3.py`와 `padfec3/decide3.py`를 바꿔 두 참조에 박힌 소스 지문이 낡았으므로, 같은 순서로 두 참조를 다시 만들었다(086ee5e32). `g3/policy3_reference.json`은 소스 지문(`sources_sha256`)과 생성 소요 시간(`timing_s`)만 달라졌고, 새 `g3/v33/V33FIX_policy_reference_v3.json`은 v2와 소스 지문(`sources`)만 다르다. v2와 v2 receipt는 보존했다. 이후 L1 관문은 v3를 쓰고, `tools/final_check.py`의 gate_l1 단계도 v3를 가리킨다. 그 뒤 설치 검사에서 gate_l1은 738,663/738,663 leaves가 v3 참조와 비트 단위로 같았다.

| 검사 | 결과 |
|---|---|
| BL-13 docstring 제외 AST | 동일 |
| CP-16 지정 삭제·상수 치환 정규화 AST | Python 정책 모듈 3개 동일 |
| 전체 pytest | 1920 passed, 2 skipped, 32 deselected, 17656 subtests passed |
| 전체 Go 시험 | PASS 275, SKIP 2, FAIL 0 |
| Go vet, race, build | PASS, race 보고 0 |
| gate_v3_parity | PASS |
| gate_l1_go, v2 참조 | 738663값 비트 일치 |
| none 재생 | 411000/411000 결정 일치, mismatch 0, 최종 상태 300/300 |
| c1 재생 | 410997/411000 결정 일치, mismatch 3 |
| 기존 설치 바이너리 해시 | 실행 전후 일치 |

임시 HOME에서 빌드와 두 관문, 참조 `--check`를 같은 WSL 호출 안에서 실행했다. 재생은 기존 v3.2 기록과 비교했으며 `experiments/v33/v33fix_replay.py --out`으로 별도 파일에 썼다. 원래 재생 결과는 덮지 않았다. 위 값은 구현 검사와 기록 재생 결과다. 실제 네트워크 측정은 수행하지 않았다. 설치본 교체와 동결본 검증은 F16에서 한다.

빌드 바이너리 SHA-256은 `63854e33ac2a33531f3463c72d31899a5f7df5642910497e8ac94ccec308c63a`, 소스 SHA-256은 `8e3c09609184de9062072019736c90fd174d91092568e4532c94e1a3e236033d`다. L1 v2 참조 SHA-256은 `1096c3a727a8702905b1ec1b4d95e6b50662c66da353f1ce68ff92d03e87eaa9`다.

로컬 보존: `C:/dev/codex_handoff/final/runs/F15_static.py`, `F15_python_static.py`, `F15_go_static.py`, `F15_reference_compare.py`, `F15_go.sh`, `F15_collect.py`와 `F15_summary.json`. 재생 결과는 `C:/dev/codex_handoff/final/scratch/replay_F15.json`이다.

## F16: 전체 검증과 설치·동결

2026-11-06, CP-01·MS-05·RP-08과 BL-14의 설치 검증을 완료했다. 정책과 Go 소스·시험은 F15 커밋 `13e2f4c94` 그대로다. 검증 도구와 Python 시험을 추가한 커밋은 `27da062aa`이며, 설치 검증 JSON의 HEAD도 이 커밋이다. 이 결과는 구현 검증이다. 새 네트워크 개발 측정은 시작하지 않았다.

`tools/final_check.py`는 Windows에서 전체 pytest를 실행하고, 한 번의 Ubuntu WSL 호출 안에서 Go vet·전체 시험·race·빌드, M1 참조 시험, 두 정책 관문, 참조 `--check`, staging unittest를 순서대로 확인한다. 기본 실행은 임시 HOME·GOPATH·GOCACHE·출력 폴더를 사용한다. 실제 설치는 `--install`을 명시했을 때만 수행한다. 실행마다 새 `--out` 경로를 주며 결과 JSON과 단계별 로그를 함께 보존한다.

측정 잠금이 있으면 자식 프로세스를 시작하기 전에 종료 코드 2로 거부한다. 검증 실패는 종료 코드 1이다. 상속된 `GEN33_KEEP_STAGES`는 제거해 기존 stage를 보존한다. 알려진 hold 타이밍 시험의 `count=2 want=3` 실패만 전체 Go 빌드를 한 번 재시도하며, 다른 시험 실패나 컴파일 오류·race 보고가 동반되면 재시도하지 않는다. 이번 임시 빌드와 설치 빌드에는 재시도가 없었다.

V3 관문은 두 실행 모두 `--bin` 없이 기본 경로를 확인했다. L1 관문은 `g3/v33/V33FIX_policy_reference_v2.json`과 현재 빌드의 바이너리, 새 출력 경로를 명시했다. M1 참조가 존재하므로 `TestHoldPythonReadFromReference`와 `TestUDPHoldPythonReadBatchReference`를 별도로 실행했고, 두 시험 모두 skip 없이 통과했다.

| 검사 | 임시 환경 | 실제 설치 |
|---|---|---|
| 전체 pytest | 1946 passed, 2 skipped, 32 deselected, 17656 subtests passed | 동일 |
| 전체 Go 시험 | 275 PASS, 2 SKIP, 0 FAIL | 동일 |
| Go vet·race·build | PASS, race 보고 0 | 동일 |
| 별도 M1 참조 시험 | 2 PASS, 0 SKIP, 각 700116 사례 | 동일 |
| 기본 경로 gate_v3_parity | PASS, problems 비어 있음 | 동일 |
| L1 v2 관문 | 738663/738663값 비트 일치 | 동일 |
| v3 참조 `--check` | PASS | 동일 |
| WSL staging unittest | 2 PASS | 동일 |

새 Python 시험 26개는 잠금의 조기 거부, 환경 격리, M1 무실행·skip 거부, 재시도 한계, 실패 JSON과 로그를 확인한다. Windows에서 skip되는 staging 시험 두 개는 WSL에서 실제 실행했다.

임시 검증 전후로 기존 설치본과 기본 출력 경로, 보존 stage가 같았다. 옛 설치본 5파일을 보관한 뒤 설치했고, 새 stage를 더해 53개에서 54개가 됐다. 기존 stage는 모두 남아 있다. 새 동결본에는 qamp와 SHA-256·소스 지문·buildinfo 파일을 복사하고 파일과 디렉터리의 쓰기 권한을 제거했다. 설치본과 동결본의 네 파일 해시가 일치한다. 기존 동결 바이너리 5개의 해시와 archive의 INDEX·MANIFEST·도구 파일도 불변이다.

| 최종 바이너리 식별 | 값 |
|---|---|
| SHA-256 | `63854e33ac2a33531f3463c72d31899a5f7df5642910497e8ac94ccec308c63a` |
| srcsha | `8e3c09609184de9062072019736c90fd174d91092568e4532c94e1a3e236033d` |
| Go | go1.26.6 |
| quic-go | v0.61.0 |
| cache schema 문자열 | padfec3.cache3/11, 1행 |
| conn-log 도움말 | 1행 |
| 동결본 V3·L1 v2 관문 | 모두 PASS, problems 비어 있음, L1 738663값 비트 일치 |

로컬 보존: 설치본은 `~/quicbed_gen33/bin/qamp`, 새 동결본은 `~/frozen/gen33_63854e33/`다. 옛 설치본의 qamp, qamp.sha256, qamp.srcsha, qamp.buildinfo, go_test.txt는 `C:/dev/padfec_archive/binaries/gen33_41424293/`에 보관했다.

로컬 보존: 실행 결과는 `C:/dev/codex_handoff/final/runs/F16_temporary.json`, `F16_install.json`, `F16_freeze.json`, `F16_frozen_v3.json`, `F16_frozen_l1.json`, `F16_summary.json`이다. 수치 집계와 보존 검사는 같은 폴더의 `F16_collect.py`, `F16_environment.py`, `F16_assets.py`, `F16_verify.sh`로 재현한다. 최초 실행은 WSL의 중복 Git 상태 조회가 지연돼 중단했고 `F16_temp.json`과 로그에 남겼다. 현재 도구는 Windows에서 상태를 기록하고 WSL에서는 HEAD만 확인한다.

계획 JSON은 아직 없으므로 바이너리 SHA-256·srcsha 입력은 F20이 맡는다. 세대 표 반영은 F62, 최종 archive 사본은 F67에서 한다. F16 뒤에는 Go 소스와 Go 시험을 변경하지 않으며, 변경이 필요하면 루프 결정 목록에 기록한다.
