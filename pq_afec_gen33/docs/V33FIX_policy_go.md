# V33FIX 활성 정책 Go 거울과 Python-Go 관문 (v3.3.1-dev, 상태 판본 11)

작성 2026-11-02. 묶음 A-go. 앞 묶음 A-py가 Python 활성 정책을 v3.3.1-dev로 바꿨고(`docs/V33FIX_policy.md`), 이 묶음은 그것을 Go(`qamp -fec auto3`)로 옮기고 두 언어가 비트 단위로 같은지 확인하는 관문을 새로 만들었다.

## 1. 바꾼 파일

| 파일 | 내용 |
|---|---|
| `experiments/quicbed/policy3.go` | 상수, 상태 필드와 검증, 관측을 none/c1 두 경로로 나눔, 결정 규칙, 캐시 로더, auto3 기록 행 |
| `experiments/quicbed/policy3_l1.go` | 참조 실행기(`-mode policy3ref`의 `l1` 입력): 경로별 info 출력, 결정 전체 출력, 결정+관측 열, 잘못된 상태, 캐시 파일 |
| `experiments/quicbed/policy3_test.go`, `policy3_gen32_test.go` | none 경로 시험을 기준선 90859b973의 v3.2 본문으로 되돌리고 상수만 새 값으로 바꿈 |
| `experiments/quicbed/policy3_l1_test.go` | 거부 판본 목록을 1~10, 12로 바꿈 |
| `experiments/quicbed/policy3_v331_test.go` (새 파일) | c1 경로, 전환, streak, 재평가 보류, 상태 표지 검증, 캐시 스키마, 1452 B 상한, 기록 행 시험 12개 |
| `experiments/gate_l1_go.py` | 참조 생성기(`--generate`)를 넣고, 비교 대상에 새 구획을 더함 |
| `g3/v33/V33FIX_policy_reference_v1.json`, `.receipt.json` (새 파일) | 새 참조와 영수증 |
| 이 문서 | |

`qamp.go`는 고치지 않았다. `destCache3.plan`, `observePred`, `auto3Row`의 서명은 그대로이고, qamp는 지금처럼 `&t.Arrivals`를 넘긴다. `-feedback`이 꺼져 있으면 arrivals는 `src none`이라 목적지는 none 경로에 머문다.

## 2. Go에 옮긴 규칙

### 상수와 상태

`p3StateVersion` 11, `p3PolicyVersion` "v3.3.1-dev", `p3CacheSchema` "padfec3.cache3/11", `p3UDPMax`는 `typicalMTU - 28`(1472)에서 `quicgoMaxIPS`(1452)로 바꿨다. `p3UDPMax`를 쓰는 곳은 `p3Candidates`의 m>0 후보 거르기와 참조 상수 출력(`udp_max`) 둘뿐이다. 새 상수 `p3ArrivalStreakCap` 8은 Python `learn3.ARRIVAL_STREAK_CAP`과 같다.

`p3State`에 `C1Seen`(`"c1_seen"`)과 `ArrivalStreak`(`"arrival_streak"`)을 `g_alarm`과 `stats` 사이에 넣었고, `p3Stats`에 `Binary`(`"binary"`)를 넣었다. `validate()`는 Python `from_json`과 같은 조건을 더 본다. streak가 0..8 밖이면, `c1_seen`이 false인데 streak가 0이 아니면, `c1_seen`이 true인데 `g_alarm`이 비어 있지 않으면 거부한다. `p3State.UnmarshalJSON`을 새로 두어 두 필드가 없거나 null이면 거부한다(Go 기본 해석은 빠진 필드를 0으로 두고 null을 무시해서, Python의 KeyError·TypeError와 어긋났다). 이 해석기 안에서도 `DisallowUnknownFields`를 켜서, 캐시 로더가 원래 하던 모르는 키 거부가 상태 안쪽까지 그대로 이어진다.

### 관측 (`p3ObserveCandidate`)

입력 검증과 guard 잔차 미리보기, `p3Context`까지는 이전과 같다. 그다음 순서는 Python `_observe3`과 같다.

1. arrivals의 `src`가 `c1`이나 `ack`이고 `C1Seen`이 false면 `p3EnterC1`: `C1Seen=true`, `AlarmCleared += len(GAlarm)`, `GAlarm`을 비운다. 잘린 회신과 `sent=0` 회신도 여기 들어간다.
2. `C1Seen`이면 `p3ObserveC1`, 아니면 `p3ObserveNone`.
3. 공통 끝: 갱신 종류별 카운터(`binary`, `datagram`, `categorical`, `predict_only`), `Predict`, 성공이면 k·HCT·S 창.

`p3ObserveNone`은 기준선 90859b973의 Go `p3Observe` 본문이다. 1비트 이진 우도(`p3Likelihood`, EPS 0.01), shield·nominal2·guard 건너뛰기, `p3GuardObserve`(기록 뒤 경보 검사), 갱신했을 때만 `Events`를 센다. L1 Go에서는 모든 경로에서 `p3ClassifyHCT`를 먼저 불렀는데, none 경로에서는 부르지 않게 했다(Python `_observe_none`도 부르지 않는다).

`p3ObserveC1`은 L1 Go 관측과 같되 두 곳이 다르다. guard는 `p3GuardRecord`로 잔차만 기록하고 경보를 세우지 않는다(`Raised`는 빈 목록, `Alarmed` false). 끝에서 쓸 수 있는 회신이면 `ArrivalStreak = min(8, streak+1)`, 아니면 0이다. `p3GuardObserve`는 `p3GuardRecord`와 `p3GuardCheck`로 나눴다.

### 결정 (`p3Decide`)

`c1 := st.C1Seen`. c1이면 guard 벌점 맵을 만들지 않는다(nil). 아니면 v3.2처럼 만료되지 않은 경보마다 벌점을 둔다. `reevalOpen := !c1 || ArrivalStreak == 0`. 16번째 재평가 계수(`NReeval`)는 `ReevalCond && reevalOpen`일 때만 오른다. c1이면 `p3GuardRelease`를 부르지 않고 `GuardCleared`는 빈 목록이다. 결정에 `PolicyPath`, `C1Seen`, `ArrivalStreak`, `ReevalHeld`(Python `reeval_feedback_suppressed`)를 더했다. c1 경로의 guard 잔차 유한성 검사는 `validate()`의 `p3ValidateGuardGaps`가 이미 한다.

### 캐시 파일과 기록 행

`loadDestCache3`는 이제 `schema`를 먼저 확인하고 그다음 `dests`를 해석한다. 이전에는 문서 전체를 한 번에 해석해서, 옛 캐시를 넣으면 스키마 대신 상태 필드 오류가 먼저 나왔다(아래 5절 e2e 행). auto3 기록 행에 `policy_path`, `reeval_feedback_suppressed`, `obs_policy_path`, `obs_loss_update_kind`를 더했다. 관측이 없는 행에서는 뒤의 두 키가 null이다. 실측 때 연결마다 어느 경로로 배웠는지 행만 보고 알 수 있게 하려는 것이다.

## 3. 감사 ID별 처리

감사 원문 위치: `C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01\B-active-algorithm.md`, `D-rejected-learning.md`(세션 스크래치의 원본을 옮긴 보존 사본).

- B-E7 ("상태 판본이 3에서 4로 바뀌었는데 cache3 schema 표지는 그대로"): 표지를 `padfec3.cache3/11`로 올렸고, 로더가 스키마를 먼저 본다. 옛 캐시(`cache3/3`)를 넣으면 qamp는 여전히 exit 2로 끝나지만, 메시지가 `schema "padfec3.cache3/3", want "padfec3.cache3/11"`로 바뀌어 표지만 보고 호환 여부를 안다. 콜드스타트로 넘어가는 다른 처방은 택하지 않았다. 옛 사후분포를 조용히 버리면 실측 기록에서 그 사실이 사라지기 때문이다.
- B-E5 ("S4 뒤 E12 L1 보충 관문을 다시 돌리지 않아 출처 검사에서 실패"): 정책 자체가 바뀌어 E12 L1 참조(`g3/v33/E12_l1_reference_v1.json`, 상태 판본 4)는 더는 쓸 수 없다. 같은 방식의 관문을 새 정책으로 다시 만들었고(4절), 현재 소스 지문으로 생성한 참조를 영수증과 함께 두고 관문을 다시 돌렸다(5절). E12 L1 참조는 기록으로 남겨 두었고 고치지 않았다. 지금 Go로 그 참조를 돌리면 입력 상태에 `c1_seen`이 없어 읽는 단계에서 거부될 것이다(코드로 판단한 것이고 실행하지는 않았다).
- D-E4 ("활성 정책이 1452 B를 넘는 패리티 후보를 계속 만든다"): A-py가 Python에 적용한 상한을 Go `p3UDPMax`에 적용했다.
- B-E1, D-E3, C-E7: Python 쪽 처방(none은 v3.2, c1은 L3 record_only 결정)을 Go에 그대로 옮겼다. none 경로가 v3.2 Go와 같다는 것은 기준선 Go 바이너리와 직접 비교해 확인했다(5절).

## 4. 새 참조 관문

### 생성

```
python -I -B experiments/gate_l1_go.py --generate g3/v33/V33FIX_policy_reference_v1.json
```

seed 기본값 20261102, 생성 19.4초(영수증 `python_seconds`). 출력 파일이 이미 있으면 덮어쓰지 않고 멈춘다. 생성기는 Python 결정 사전의 키 집합이 `DECISION_KEYS`와 다르면 멈추고, 아래 커버리지 항목 중 하나라도 0이면 멈춘다(`REQUIRED_COVERAGE`).

| 구획 | 크기 | 내용 |
|---|---:|---|
| arrivals | 44 | sent 1~8 × lost 0~sent 데이터그램 우도 |
| classes | 1,080 | 등급 경계, 경계 바로 옆 HCT 등급, 등급 확률, 범주 우도 |
| observations | 26 열 × 30행 = 780 | 초기 상태 6종(cold, hot, rtt200, nominal, no_rtt, guard) × 증거 4종(none만, 인덱스 1에서 c1 시작, 인덱스 25에서 전환, 잘린 회신으로 시작) + 이미 c1인 상태 2열. 매 행 상태 JSON 왕복 |
| sequences | 13 열, 2,120행 | 결정+관측 열. 무작위 장면 9열(none 3, c1 3, 인덱스 100에서 전환 3, 각 200행, 그중 3열은 W=1406), 재평가 열 2개(64행, none과 c1), guard 열 2개(96행, none과 인덱스 30에서 전환) |
| caches | 6 열 × 48행 = 288 | `destCache3.plan`/`observePred`, RTT 출처 3종 × 증거 2종, 매 행 캐시 항목 JSON 왕복 |
| invalid_arrivals | 31 | Go JSON 해석이 거부해야 하는 arrivals. Python이 `hot`과 `c1hot` 두 상태에서 거부하고 상태를 바꾸지 않는 것을 생성 때 확인 |
| invalid_states | 32 | 판본 1~10·12·11.0·null·"11", `c1_seen`·`arrival_streak` 잘못된 값, 모순된 표지, 음수 `binary`, 필드 누락. 생성 때 Python `from_json`이 모두 거부하는지 확인 |
| cache_files | 17 | 유효 2개(저장 뒤 다시 읽은 내용까지 비교), 거부 15개(옛 스키마, v4 상태, 표지 누락·null·문자열·범위 밖·실수, 모순, 모르는 키, 뒤따르는 문서) |

영수증(`g3/v33/V33FIX_policy_reference_v1.receipt.json`)의 커버리지 중 주요 값: none 결정에서 재평가 5회, 경보가 있는 결정 172회, 경보 해제 2회, 경보 발생 7회, c1 결정에서 재평가 2회와 보류 52회, W=1406(k≥2) 결정 706회, 관측 갱신 종류 none-binary 607·none-predict_only 966·c1-datagram 930·c1-categorical 625·c1-predict_only 60, none→c1 전환 25열, streak 상한 도달 134행.

출처 지문(`sources`)에는 `experiments/gate_l1_go.py`, `experiments/replay_g3.py`, `padfec3/learn3.py`, `padfec3/decide3.py`, `padfec3/layout.py`, `padfec/policy.py`, `padfec/quantum.py`, `padfec/table.py`가 들어간다. 이 중 하나라도 바뀌면 관문이 `problems`에 올리므로, 바꾼 사람이 참조를 다시 만들어야 한다(B-E5와 같은 상황을 바로 드러내려는 것이다).

### 실행과 비교 규칙

WSL Python에서 돌린다(바이너리가 Linux ELF다).

```
python3 -I -B experiments/gate_l1_go.py --ref g3/v33/V33FIX_policy_reference_v1.json --bin <qamp> --out <결과.json>
```

비교 규칙은 E12 L1 관문과 같다. 모든 잎을 먼저 정확히 비교하고, 같지 않을 때만 사후분포·가중치·p_mean·확률·우도는 상대 1e-12, 나머지 실수는 절대 1e-9로 본다. S·HCT 창은 항상 정확히 같아야 한다. 사전은 키 집합까지 같아야 하므로, Go가 none 경로 info에 c1 전용 키(grade, legacy_* 등)를 내면 실패한다. 이번에 더한 것은 바이너리의 `policy_version`·`state_version`·`udp_max` 상수를 참조 값과 대조하는 검사다.

## 5. 검증 (직접 실행한 값)

WSL Ubuntu 임시 복사본 `~/v33fix_tmp/A-go`에서 `build_gen33.sh`의 파일 목록대로 stage를 만들어 Go 1.26.6으로 빌드했다(HOME도 그 아래로 바꿈). 끝난 뒤 그 폴더는 지웠다. 출력은 세션 스크래치에 있던 것을 묶음 P가 sha256 대조 뒤 `C:\dev\codex_handoff\v33\runs\v33fix\P\first_round\A-go`로 옮겼다(아래 표의 경로는 이 폴더 기준, 목록은 `runs\v33fix\P\SHA256SUMS.txt`). 옮긴 것은 `final2`, `fresh`, `mutants_final`, `v32src`와 맨 위 스크립트·기록 파일이다. 중간 시도인 `try1`, `final`, `mutants1`, `e2e`와, 기본 v3 참조를 스크래치에서 다시 만든 `v3gate`는 옮기지 않았다(`v3gate\v3ref.json`은 지금 저장소의 `g3/policy3_reference.json`과 `timing_s`만 다르다, 7절).

최종 바이너리 sha256 `8be4c740b95376fb9dfa865b3bec3e139ae5a8296b8151f87446457200a1a5f4`, srcsha `bf6b75c31c2c818cffee7299b07d59479cf1b6ac1c3efad998b8654b70477324`(실행 시점의 `experiments/quicbed` 지문과 같음).

| 검사 | 결과 | 출처 |
|---|---|---|
| 새 관문, 고정 참조(seed 20261102, sha256 `2adbd0fc…8bf7`) | 잎 738,663개 모두 비트 일치, 실패 0, problems 없음, Go 1.37초 | `final2\gate_l1_main.json` |
| 새 관문, 독립 seed 271828로 새로 만든 표본(sha256 `9e6c44f8…b4d6`) | 잎 743,595개 모두 비트 일치, 실패 0, Go 1.46초 | `final2\gate_l1_fresh.json`, 표본 `fresh\` |
| 관문이 틀린 Go를 잡는지(고정 참조, 정책 코드를 일부러 바꾼 빌드 7개) | 7개 모두 통과 못 함. 1472 상한: 실패 10,117. c1 재평가 보류 제거: 1,160. none 벌점 제거: 294. none guard 건너뛰기 제거: 11,668. 전환 때 경보 유지: 실행기가 거부(exit 2). streak 상한 9: 실행기가 거부(exit 2). 상태 표지 검증 하나 끔: 실패 2 | `mutants_final\*.json`, `*.err` |
| 같은 7개 변형에 대한 Go 단위 시험 | 7개 모두 하나 이상 실패 | 실행 출력(이 문서 작성 직전) |
| 기존 v3 관문(`experiments/gate_v3_parity.py`), 현재 Python으로 스크래치에 다시 만든 참조(`POLICY_VERSION`은 메모리에서만 고침, 저장소 기본 참조로 다시 돌린 결과는 7절) | PASS. 상수, primitive 2,800, 결정 6,720(벌점 있는 것 1,344, ej 비트 일치 6,720/6,720), 궤적 5개 × 10,000단계 모두 일치. fresh seed 20261005: primitive 2,600, 결정 5,000(벌점 1,000), 궤적 4개 × 10,000단계 일치 | `final2\gate_v3.json` |
| none 경로 대 기준선 v3.2 Go(90859b973의 `qamp.go`, `policy.go`, `policy3.go`, `pfail_table.go`를 `p3UDPMax`만 1452로 바꿔 빌드, sha256 `378ffa83…64a3`) | 같은 입력에서 궤적 9개 90,000단계의 모든 단계 필드(행동, why, ej, p_mean, y, upd, n2, reeval, pen, alarm, common, n_alarm, resid, skip), 스냅숏 90개(사후분포, 가중치, 상태 공통 필드 2,340개), 결정 11,720개 모두 일치. 새 상태의 `c1_seen`은 모두 false, streak 0 | `final2\ref.*.json`, `final2\fresh.*.json`, 비교 도구 `v32_vs_new.py` |
| `go vet ./... github.com/quic-go/quic-go/padfec-local-hook` | 출력 없음(rc 0) | `final2\vet.txt` |
| `go test -count=1 -v` 같은 범위 | PASS 260, FAIL 0, SKIP 2(`TestHoldPythonReadFromReference`, `TestUDPHoldPythonReadBatchReference`, `M1_REFERENCE_GZIP` 환경변수가 필요함) | `final2\go_test.txt` |
| `go test -race -count=1` 같은 범위 | 통과, `DATA RACE` 0줄, cmd/qamp 88.2초 | `final2\go_race.txt` |
| qamp e2e: `-fec auto3 -cache3 <파일> -addr 127.0.0.1:1 -n 1` | `cache3/3` 스키마 파일 두 종류: exit 2, `schema "padfec3.cache3/3", want "padfec3.cache3/11"`. 새 스키마에 v4 상태: exit 2, `state field c1_seen is missing or null`. 유효한 v11 캐시: exit 0 | 실행 출력. 입력은 참조의 `cache_files` |
| pytest `tests/test_l1_go_gate.py` | 3 passed, 15 subtests | 실행 출력 |
| 전체 pytest(다른 묶음 변경이 섞인 작업 트리) | 1855 passed, 4 failed, 2 skipped, 32 deselected. 실패 4개는 A-py가 적은 것과 같은 맡은 파일 밖 시험이다 | 실행 출력 |

Go 단위 시험 중 바꾼 것: L1이 none 경로를 범주 우도로 바꾸면서 고쳐 놓은 8개 시험(`TestP3SkippedObservationsAdvanceEachHazardOnce`, `TestP3ObservedEvidenceUsesOnlyOneTransition`, `TestP3AlarmedSuccessesRefreshTheCommonDelay`, `TestP3ShieldedObservationPredictsWithoutLossEvidence`, `TestP3NominalTwoObservationUpdatesWindowsAndPredicts`, `TestP3AlarmNeedsEightResidualsAndHalfRTTExcess`, `TestP3AlarmedActionPenaltySkipAndClear`, 판본 시험)을 90859b973 본문으로 되돌렸다. L1의 범주 우도 기대는 버리지 않고 `policy3_v331_test.go`의 `TestP3V331C1MissingReplyUsesCategoricalEvidence`로 옮겨 c1 목적지에서 회신이 빠진 경우로 남겼다. guard 경우는 c1 목적지에 경보가 있을 수 없어서 `TestP3V331C1DecisionsIgnoreGuardResiduals`(기록만 하고 경보·벌점 없음)로 바꿨다. 그 밖의 바뀐 곳은 판본 문자열, `udp_max` 1452, 상태 키 목록(`c1_seen`, `arrival_streak`, `binary`)이다.

## 6. 못 한 것과 다음 묶음에 넘길 것

- `experiments/gate_v3_parity.py:27`의 `POLICY_VERSION`이 아직 "v3.3-dev"다. 맡은 파일 밖이라 바꾸지 않았고, 위 v3 관문은 메모리에서만 "v3.3.1-dev"로 바꿔 돌렸다. 그 줄을 고친 뒤 `g3/policy3_reference.json`(이 관문의 기본 참조, 판본 4·1472 상한으로 만든 것)을 `python -I -B g3/policy3_reference_gen.py`로 다시 만들어야 기본 실행이 통과한다. 스크래치 `v3gate\v3ref.json`이 같은 생성기로 만든 결과다(2분 6초). 묶음 P가 두 곳을 고치고 저장소 기본 참조로 관문을 다시 돌렸다(7절).
- `genconfig.json`의 `gen_id`가 "v3.3-dev"다. 맡은 파일 밖이다. 묶음 P는 이 값을 바꾸지 않기로 했다. `experiments/pipeline.py` 375행이 `gen_id == "v3.3-dev"`일 때 과거 파이프라인을 막기 때문이다(`docs/V33FIX_policy.md` 통합 정리 절).
- `g3/l1_go_reference_gen.py`(E12 L1 생성기)는 none 경로 info에 c1 전용 키를 요구해서 지금 정책으로는 실행되지 않을 것이다. 새 생성기가 `experiments/gate_l1_go.py --generate`로 대신한다. 옛 생성기와 E12 L1 참조를 지울지는 사람이 정할 일이라 그대로 두었다.
- 새 참조의 출처 지문에 든 파일(4절)을 다른 묶음이 이후에 바꾸면 관문이 출처 문제로 실패한다. 그때는 `--generate`로 다시 만들고 관문을 다시 돌린다.
- WSL `~/quicbed_gen33`에 설치하지 않았고 `build_gen33.sh`도 돌리지 않았다(이 작업의 금지 사항). 실제 배포 바이너리는 다음 설치 때 바뀐다.
- Python `from_json`은 모르는 최상위 키와 모르는 `stats` 키를 받아들이지만 Go는 거부한다. 캐시 로더가 원래 그랬던 것을 유지한 것이고, 참조의 `cache_files`에서 Go 쪽 동작만 고정했다.
- 실제 QUIC 측정(T7 등)은 하지 않았다. 이번 검증은 두 언어 구현의 일치와 v3.2 Go와의 일치를 본 것이고 성능을 잰 것이 아니다.

## 7. 기본 v3 관문 다시 돌림 (묶음 P, 2026-11-02)

6절 첫 항목을 처리했다. `experiments/gate_v3_parity.py`의 `POLICY_VERSION`을 "v3.3.1-dev"로 바꾸고, 결과 JSON의 `label` 문자열이 같은 상수를 읽게 했다. 기본 참조 `g3/policy3_reference.json`은 `python -I -B g3/policy3_reference_gen.py`로 다시 만들었다. 생성기는 `--out` 기본값인 이 파일 하나만 쓰고(임시 파일 `.tmp`를 쓴 뒤 교체), 영수증 파일은 없다(`g3/policy3_reference_gen.py` 39·411~414행). 새 참조의 sha256은 `5f582673497c2c3f4833760796b8f63b7b8fdaf09a04efc3b82e1881d4191de0`(HEAD 판 `ca4cbf38ef6c700a7e04d6f7dd659df4c75b0ab2d4489640b7676ee87df0f542`)이고, 상수는 policy_version v3.3.1-dev, state_version 11, udp_max 1452, max_ips 1452다. 출처 지문 7개는 지금 파일과 모두 같다. 직접 확인한 것은 둘이다. `python -I -B g3/policy3_reference_gen.py --check`가 지금 코드로 다시 만든 결과와 이 파일이 같다고 냈고("check: identical", 3분 36초, 쓰기 없음), 스크래치 `v3gate\v3ref.json`과는 `timing_s`만 달랐다.

빌드는 WSL Ubuntu 임시 폴더 `~/v33fix_tmp/P`에서 했다. `build_gen33.sh`의 `GO_SOURCES`와 시험 파일 목록대로 stage를 만들고 Go 1.26.6, HOME·GOCACHE를 그 폴더 아래로 두었다. 끝난 뒤 폴더는 지웠다.

| 검사 | 결과 |
|---|---|
| `go vet ./cmd/qamp github.com/quic-go/quic-go/padfec-local-hook` | 출력 없음(rc 0) |
| `go test -count=1 -v` 같은 범위 | 최상위 PASS 265, SKIP 2(5절과 같은 두 시험), FAIL 1. 실패는 `TestComparisonSameSlotsAndAccounting`(`qamp_comparison_test.go` 49행)이다. 이 시험이 보는 첫 비행 배치 코드(`flight_shape.go`, `qamp.go`)는 같은 시각 테스트베드 묶음이 고치던 파일이고 `policy3.go`와 관계없다. 통합 때 다시 본다 |
| 바이너리 | sha256 `06520d52c2f5ee50f0329548a9351030e54030e21ef7ec46b85c46d171c2e3fb`, srcsha `efac25fe292d4c9a8a9961b8325a5e39470beac6255496b3dd9e5010c3db1127`(빌드 전후와 관문 시점의 `experiments/quicbed` 지문이 모두 같음) |
| `python3 -I -B experiments/gate_v3_parity.py --bin <위 바이너리> --out <임시 폴더>/gate_v3_parity.json`(기본 `--ref`, fresh 포함) | PASS, problems 없음, 113.9초. 상수 일치. 참조: primitive 2,800, 결정 6,720(행동 122종, 동점 1,317, 벌점 있는 결정 1,344), ej 비트 일치 6,720/6,720, 정확 비교 필드 9종 모두 6,720/6,720, 궤적 5개 각 10,000단계 일치(사후분포와 guard 상태 비트 일치). fresh seed 20261005: primitive 2,600, 결정 5,000(벌점 1,000), 궤적 4개 각 10,000단계 일치 |

출력 사본은 `C:\dev\codex_handoff\v33\runs\v33fix\P\gate_v3_2026-11-02\`(바이너리, `go_test.txt`, `vet.txt`, `qamp.buildinfo`, `qamp.sha256`, `qamp.srcsha`, stage 파일 목록, 관문 JSON·표준 출력, fresh 입력)에 있고 WSL 쪽 sha256과 대조했다.

옵션은 코드로 확인했다. `--no-fresh`는 fresh 표본을 건너뛰지만 그러면 problems에 "fresh seeded sample skipped"가 올라 PASS가 나올 수 없다(`gate_v3_parity.py` 615~617행). 관문은 `--out` 폴더에 fresh 입력 `gate_v3_fresh_<pid>_<ns>.json`을 남기므로(599~602행), 기본값 `experiments/results/`를 쓰면 저장소 안에 파일이 생긴다. 그래서 `--out`을 임시 폴더로 줬다. `--bin`을 주지 않으면 `genconfig.json`의 `~/quicbed_gen33/bin/qamp`를 쓴다. 그 설치본은 2026-11-01 08:19 빌드이고 문자열에 `v3.3-dev`와 `padfec3.cache3/3`이 들어 있으며 srcsha가 `9798aa226a1a1246f425bfbe407e173e7d0b5b4324e22b92146bfdd8682b009a`다(읽기만 함). 그래서 다시 설치하기 전에는 기본 실행이 상수와 srcsha 검사에서 실패할 것이다. 이것은 코드와 파일로 판단한 것이고 실행하지 않았다. 설치(`build_gen33.sh` 실행)는 이 작업에서 하지 않았다.

## 8. 통합 확인 (2026-11-02 07:35~07:45)

2차 네 묶음이 끝나고 통합 수정 두 가지(`qamp_comparison_test.go`의 `comparisonFixture`에 `c.retransMode = "original_first"` 한 줄, `build_gen33.sh` 목록 밖 시험 파일 안내 문구)를 넣은 작업 트리로 다시 돌렸다. 7절의 srcsha `efac25fe…1127`은 그 뒤 `build_gen33.sh`와 시험 파일이 바뀌어 지금 지문과 다르다. 비시험 Go 소스는 같아서 바이너리 sha256은 7절과 같다.

빌드는 실제 `build_gen33.sh --race`를 WSL Ubuntu 임시 HOME(`~/v33fix_tmp/INT/home`)과 임시 `QAMP_GEN33_OUT`으로 돌렸다. 실제 `~/quicbed_gen33`은 건드리지 않았고 임시 폴더는 끝난 뒤 지웠다.

| 검사 | 결과(모두 직접 실행) |
|---|---|
| `build_gen33.sh --race` | rc 0, 133초. vet 통과, `go test -count=1 -v` 최상위 PASS 266, SKIP 2, FAIL 0. race 통과(DATA RACE 0) |
| `gofmt -l` | `pfail_table.go` 하나. 생성 파일이고 HEAD와 바이트가 같다 |
| M1 와이어 관문 2개(`M1_REFERENCE_GZIP`, 기준 sha256 `59b3434763af…0dbcf`) | PASS 2, 각 700,116사례·60설정(40.19 s, 42.94 s) |
| 바이너리 | sha256 `06520d52c2f5ee50f0329548a9351030e54030e21ef7ec46b85c46d171c2e3fb`, srcsha `bb31e5904d2281ed6e4076067904750394a8724ac89fdb084e62bbaea2cc4dae` |
| `gate_v3_parity.py --bin <위 바이너리> --out <임시 폴더>`(기본 `--ref`, fresh 포함) | PASS, problems 없음, 106초. primitive 2,800, 결정 6,720(정확 비교 9종 불일치 0, 실수 필드 6종 비트 일치 6,720), 후보 목록 35,943 비트 일치, 궤적 5개. fresh: primitive 2,600, 결정 5,000, 궤적 4개 |
| `gate_l1_go.py --ref g3/v33/V33FIX_policy_reference_v1.json` | passed, problems 없음, bit_exact 738,663 |
| `python -I -B g3/policy3_reference_gen.py --check` | identical, 165초, 쓰기 없음 |
| 전체 pytest(Windows) | 1862 passed, 2 skipped, 32 deselected, 하위 17,656 passed, 169초. 실행 전후 `git status --short --ignored` 같음 |
| `tests/test_gen32_build_staging.py`(WSL python3) | `QAMP_GEN33_OUT` 없이 2 OK, 임시 값을 준 채로도 2 OK이고 그 경로에는 쓰지 않음 |

출력 사본은 `C:\dev\codex_handoff\v33\runs\v33fix\INT\`(바이너리, 시험·race·M1 기록, stage 파일 sha 목록, 관문 JSON과 fresh 입력, `SHA256SUMS.txt`)에 있다. 설치본 `~/quicbed_gen33/bin/qamp`는 여전히 2026-11-01 08:19 빌드(srcsha `9798aa22…`, v3.3-dev)다. 설치 전에는 `--bin` 없이 기본 관문을 돌리면 실패한다. 설치 시점은 사람이 정한다.
