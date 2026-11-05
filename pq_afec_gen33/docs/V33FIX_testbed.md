# V33FIX 묶음 B: Go 테스트베드 수정 기록

2026-11-02 정정: 같은 날 통합 정리(묶음 G)에서 바뀐 사실은 끝의 "통합 정리 (2026-11-02)" 절에, 그 뒤 통합 담당과 묶음 D가 고친 것은 맨 끝 "통합 정리 (2026-11-02, 통합 담당과 묶음 D)" 절에 있다. A-E7 절의 `GEN33_KEEP_STAGES` 기본 5와 "실제 폴더에서 오래된 stage가 지워진다"는 주의는 지금 기본 0(전부 보존)으로 바뀌었고, "못 한 것과 넘기는 것" 절의 `flight_shape.go`·T6 문서·c1_status·`build_gen33.sh` 소스 목록 항목은 그 절에서 처리했다. 시험 수와 바이너리 sha도 그 절의 값이 지금 값이다.

2026-11-02. 시작점은 브랜치 v33의 HEAD `d67717d9b`(작업 트리 깨끗)다. 커밋하지 않았고 작업 트리에서만 고쳤다. 감사 원문은 `F-go-testbed.md`, `A-integrity.md`, `B-active-algorithm.md`, `H-coverage.md`(감사 폴더 `C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01`)이고, 아래 ID는 그 파일들의 것이다. 정책 파일(`policy*.go`)은 다른 묶음 담당이라 손대지 않았다.

바꾼 파일: `experiments/quicbed/qamp.go`, `observation.go`, `boundary.go`, `qamp_comparison_test.go`, `qamp_preserved_test.go`, `build_gen33.sh`, `.github/workflows/ci.yml`. 새 파일: `experiments/quicbed/qamp_feedback_compat_test.go`, `qamp_connlog_test.go`, `qamp_profile_test.go`, `docs/T7_conditions_v31.md`, 이 문서.

숫자의 출처는 두 가지로 나눠 적는다. "직접"은 이번 작업에서 WSL Ubuntu 임시 복사본(`~/v33fix_tmp/B`, 끝난 뒤 삭제)으로 돌려 본 값이다. "문서"는 감사 파일이나 기존 문서에서 읽은 값이다. 직접 돌린 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\G\round1_B`(출력은 그 아래 `out`)에 있다. 핵심 줄은 부록에도 그대로 옮겼다.

## 요약

| ID | 처리 | 바뀐 곳 | 확인 |
|---|---|---|---|
| F1 (+검증자 missed) | 고침 | 서버 `-feedback-version 2\|3`, `buildFeedback` | 시험 5개, 동결 클라이언트 3종 loopback |
| F2 | 고침 | 서버 `-conn-log` JSONL | 시험 5개, loopback |
| F4, H 누락 | 고침 | `-retrans-layout` 기본값 `repeat_first`, `-profile sealed31`, `-client-tracer`, `docs/T7_conditions_v31.md` | 시험 6개, loopback |
| F5 | 고침 | `emit`의 drop-parity 분기 | 시험 1개 |
| B-E6, A-E5(Go 쪽) | 고침 | `preservedTempDir` | 시험 1개 |
| A-E7, F7 | 고침 | `build_gen33.sh` | CI 흉내 실행에서 확인 |
| A-E1 | 고침 | `ci.yml` | setup-go를 흉내 낸 임시 HOME에서 고치기 전후 실행 |
| F3 | 동작 유지, 문서 | 이 문서 | 해당 없음 |
| F6, F8 | 문서 | 이 문서 | 해당 없음 |

새 시험은 18개다. 고친 코드 한 군데씩을 원래대로 되돌린 복사본(돌연변이)에서 각 시험이 실패하는지도 확인했다(부록 B).

## F1: 서버 C1 회신 판본과 동결 클라이언트

문제. gen33 서버는 C1 회신을 판본 3(복원 CRC 목록 포함)으로만 보냈다. 동결 gen-2·v3.1·v3.2 클라이언트의 `parseFeedback`은 판본 2이고 길이가 `12+4*nc`일 때만 받는다. 받지 못한 회신은 클라이언트의 `-feedback` 설정과 상관없이 `countRx`로 들어가 `server_bytes`를 부풀린다(감사 F1과 검증자 missed 항목, 문서). 세 세대의 `parseFeedback`이 바이트 단위로 같다는 것은 직접 diff로 확인했다.

세대 판별을 먼저 검토했다. 서버가 볼 수 있는 FEC 틀 판본은 1(v2 배치)과 3(v3 배치)뿐인데, 판본 1은 gen-2·v3.1·v3.2·gen33이 모두 쓰고 판본 3은 v3.1·v3.2·gen33이 함께 쓴다. FEC를 끈 팔은 틀이 없다. 그래서 틀로는 세대를 가를 수 없고, 서버 플래그로 정했다.

바꾼 것.
- `qamp.go`: `-feedback-version` 플래그(기본 3, 값은 2 또는 3, 서버 전용). `buildFeedback`은 `fbRec.version`이 2이면 판본 바이트를 2로 쓰고 복원 CRC 절을 뺀다. 나머지 필드(k, rxOrig, rxPar, recov, 물리 수신 CRC 목록과 잘림 표시)는 판본 3과 같고, 이는 v3.1 서버가 보내던 내용과도 같다(gen31 qamp.go 2165행 근처의 `fbRec` 구성).
- `observation.go`: `feedbackLocked`가 서버의 판본 설정을 회신에 넘긴다.
- 서버 stats에 `feedback_version`과 `profile`을 남긴다.
- 세대를 섞는 공통 서버의 규칙은 `docs/T7_conditions_v31.md`의 "공통 서버에서 세대를 섞을 때의 규칙" 절에 적었다. 요점은 동결 클라이언트가 붙는 서버에서 `-feedback`을 켜면 `-feedback-version 2`나 `-profile sealed31`을 쓴다는 것이다.

확인(직접).
- `qamp_feedback_compat_test.go`의 `frozenV2ParseFeedback`는 동결 세 세대의 `parseFeedback`을 그대로 옮긴 것이다. 판본 2 서버 회신은 이 파서가 받고, 기본(판본 3) 회신은 받지 못한다. CRC·계수·잘림 표시가 판본 사이에 같고, 판본 2 회신은 판본 3에서 복원 절(1+4n 바이트)만 뺀 길이다. gen33 클라이언트의 `arrivals`는 두 판본에서 같고 `c1.recovered_original`만 0이 된다.
- loopback(부록 A). 동결 클라이언트 n=4로 서버 변형 다섯 가지를 붙였다. HEAD 서버와 수정본 기본 서버(판본 3)에서는 세 동결 클라이언트 모두 `fb_recv 0`, `fb_magic_seen 4`이고 `server_bytes`가 4857~4877이었다. `-feedback-version 2`와 `-profile sealed31` 서버에서는 `fb_recv 4`이고 `server_bytes`가 4809~4834였다. `-feedback`을 끈 서버는 4811~4834였다. 연결 4개짜리 기능 확인이고 효과 크기 추정이 아니다.

## F2: 연결별 서버 기록 내보내기

문제. T5 이후 주기 stats(100 ms)는 `conns`를 빼고 쓰고, 계정은 완료·종료 10 s 뒤 만료된다. 그래서 하네스가 연결별 서버 기록(B_eff, TxSizes, TxRxTimeline 등)을 얻을 수 없었다(감사 F2, 문서).

바꾼 것. `boundary.go`와 `qamp.go`.
- 서버 `-conn-log 경로`. 새 파일만 연다(이미 있으면 종료 2). 계정이 만료·LRU 축출될 때 그 시점의 깊은 복사본을 대기열에 넣고, 100 ms마다 도는 고루틴이 JSON 한 줄씩 쓴다. SIGTERM·SIGINT를 받으면 살아 있는 계정을 `shutdown`으로 모두 넣고 비운 뒤 파일을 닫고, 그다음 최종 stats를 쓴다.
- 줄 형식은 기존 `conns` 값과 같은 필드에 `key`, `reason`(`expired`, `lru`, `shutdown`), `logged_ns`를 더한 것이다. 계정마다 `logged` 표시를 둬서 한 연결이 두 줄이 되지 않는다.
- 파일 쓰기는 `s.mu` 밖에서 한다. 잠금 순서는 `connLogger.mu` 다음 `s.mu`이고, `report`는 원자 계수만 읽는다.
- 서버 stats에 `conn_log`(경로, 줄 수, 오류 수, 대기 수, 계정 수명)를 남긴다. 플래그를 주지 않으면 대기열도 고루틴도 없고 기존 동작과 같다.
- `report`의 깊은 복사는 `connAcct.clone()`으로 옮겨 두 곳이 같은 코드를 쓴다.

확인(직접).
- `TestConnLogRecordsEveryAccountOnceBeforeExpiry`: 5000연결에서 주기 보고의 `conns`는 비어 있고, 수명이 지나면 `s.conns`도 비지만 conn-log에는 5000줄이 남는다. 키가 모두 다르고, `lru` 904줄과 `expired` 4096줄이다(상한 4096).
- 복사 독립성과 연결당 한 줄, 기본 꺼짐, 기존 파일 거부, 동시 실행(-race 포함)을 각각 시험했다.
- loopback: n=4 연결 뒤 11.5 s 기다리니 SIGTERM 전에 `expired` 4줄이 있었고, 그때 주기 stats의 `conns`는 0개였다. SIGTERM 뒤에도 4줄이었다. sealed31 서버를 바로 SIGTERM한 경우는 `shutdown` 4줄이었다.

T7 러너(Python)는 아직 없다. `g3bed.new_conns`류 코드는 이 JSONL을 읽도록 따로 고쳐야 한다.

## F4와 H 누락: 기본값과 v3.1 봉인 조건

문제. `-retrans-layout` 기본값 `original_first`(D28)가 auto3 비용 모형(`layout.evaluate`, `p3Evaluate`)보다 먼저 기본값이 됐다. T6 계약이 이를 기존 실패 근사라고 적었고 J3는 blocked, J4는 todo다. 이 밖에 udp-path oob, feedback-wait 1 s, 클라이언트 tracer 상시 켬, C1 판본 3, cached_k 첫 묶음 적용이 v3.1과 다르지만 한 번에 맞추는 방법이 없었다(감사 F4, H verdict와 missed, 문서).

바꾼 것. `qamp.go`.
- `-retrans-layout` 기본값을 `repeat_first`로 되돌렸다. `original_first`는 명시할 때만 쓴다. 이 결정은 D28을 대체한다. 이유는 비용 모형과 와이어를 맞추는 것이고, J3·J4가 비용 모형에 L'=0·T'=1을 넣은 뒤 다시 정한다.
- 기본값을 `defaultRunSettings()` 한 곳에 모았고 플래그 정의가 이 값을 읽는다.
- `-client-tracer`(기본 켬). 끄면 `quic.Config.Tracer`를 넣지 않고, 관측 기록의 `tracer`를 `disabled`, `pto_count_scope`를 `tracer_disabled`로 남긴다. `server_bytes`는 tracer와 무관한 수신 기록에서 계속 센다. revisit-guard는 Retry를 tracer로 보므로 tracer를 끄면 함께 쓸 수 없다(종료 2).
- `-profile sealed31`. udp-path basic, retrans-layout repeat_first, feedback-wait 200 ms, feedback-version 2, client-tracer 끔, expect-k를 생략하면 0(타이머)을 한꺼번에 설정한다. 같은 플래그에 다른 값을 명시하면 종료 2로 거부한다. 클라이언트 행에는 `profile`이 sealed31일 때만 생기고(기본 행의 키 목록은 그대로다), 서버 stats에는 항상 `profile`이 있다.
- 대응표(플래그, v3.1 값, gen33 기본값, sealed31 값, 바뀐 이유와 결정 ID)는 `docs/T7_conditions_v31.md`에 있다. 인증서 생성기, 서버 주기 stats, 클라이언트 수신 필터처럼 플래그로 되돌릴 수 없는 차이도 그 표에 적었다.
- udp-path 기본값 oob(D25)는 이번에 바꾸지 않았다. X6처럼 L1 효과만 보려는 비교는 sealed31이나 `-udp-path basic`을 명시해야 한다.
- 클라이언트 tracer의 비용은 아직 재지 않았다. 같은 블록의 A/A 비교가 필요하다.

확인(직접). 시험 6개(`qamp_profile_test.go`). loopback에서 sealed31 양쪽 실행의 행은 `profile` sealed31, `feedback_wait_limit_ms` 200, `observation.tracer` disabled, 패킷 기록 0, `c1.version` 2, `flight_expectation` `{"k":0,"source":"explicit_timer","scope":"timer_only"}`였고 서버 stats는 `udp_path` basic, `feedback_version` 2였다. 수정본 기본 클라이언트의 `retrans_layout`은 repeat_first였다. 잘못된 플래그 조합 5종은 모두 종료 2로 거부됐다(부록 A).

## F5: pad/dup 팔의 drop-parity 장부

문제. `emit`의 drop-parity 분기가 슬롯 종류와 상관없이 `ffParCRC`에 CRC를 넣었다. 실제로 보낸 pad·dup 슬롯은 넣지 않으므로, pad_junk는 버린 쓰레기 슬롯만 "보냈으나 잃은 패리티"로 세고 dup은 원본과 CRC가 겹쳐 검열됐다(감사 F5, 문서).

바꾼 것. `qamp.go` `emit`: 슬롯 종류가 parity일 때만 버린 슬롯의 CRC를 장부에 넣는다. `DroppedPar` 계수는 그대로 센다. pad·dup 슬롯은 보냈든 버렸든 C1 장부에 들어가지 않는다.

확인(직접). `TestComparisonDropParityLedger`(m2·lead1·k2, drop-parity 0, 서버가 보낸 것을 모두 받았다고 가정). parity는 sent 4·lost 1, pad_junk와 dup은 sent 2·lost 0·trunc false다. 고치기 전 코드에서는 pad_junk가 sent 3·lost 1로 실패했다. 감사가 재현한 숫자와 같다.

## B-E6, A-E5(Go 쪽): 시험 산출물 폴더

문제. `preservedTempDir`가 `~/quicbed_gen33/test_artifacts` 아래에 지우지 않는 폴더를 만들었다(감사 B-E6, A-E5).

바꾼 것. `qamp_preserved_test.go`: 기본은 `t.TempDir()`(시험이 끝나면 지워진다). 환경변수 `QAMP_PRESERVE_TEST_ARTIFACTS=1`일 때만 예전처럼 보존하고 경로를 로그에 남긴다. 이 도우미를 쓰는 정책 시험 파일들은 고치지 않았고 그대로 이 동작을 따른다.

확인(직접). `TestPreservedTempDirIsRemovedUnlessRequested`는 HOME을 임시 폴더로 바꿔 두 경우를 시험한다. 전체 시험 뒤 임시 HOME에 `quicbed_gen33`가 생기지 않았다. 이미 쌓인 `~/quicbed_gen33/test_artifacts`(감사 B 기준 4,176개, 142M, 문서. 이번 작업 끝에 읽기 전용으로 센 수는 4,005개)는 보호 경로라 지우지 않았다. A-E5의 Python 쪽(`tests/test_v33_policy_worker.py`)은 이 묶음 범위가 아니다.

## A-E7, F7: 빌드 스크립트의 race 기록과 stage 누적

바꾼 것. `build_gen33.sh`.
- 새 바이너리를 `bin`에 복사하기 직전에 이전 `go_race.txt`를 지운다. `--race`로 빌드했을 때만 새 race 기록이 들어간다. 그래서 `bin`의 race 기록은 항상 같은 바이너리의 것이다.
- stage 보존 한도. `GEN33_KEEP_STAGES`(기본 5, 0이면 모두 보존). 새 stage를 만든 직후 이번 stage를 포함해 이 수만큼만 남긴다. 기본값이면 이번 stage 말고 수정 시각이 최근인 4개를 남기고 더 오래된 `stage.??????` 폴더를 지운다. 지우기 전에 경로가 `$WORK/stage.??????` 꼴인지 다시 확인한다.
- 출력 폴더를 `QAMP_GEN33_OUT`으로 바꿀 수 있게 했다(기본 `/tmp/qamp_gen33` 그대로). 시험 실행이 공유 `/tmp` 바이너리를 덮지 않게 하려는 것이다.
- 마지막 보고 줄에 SKIP 수를 함께 쓴다(`gen33 tests pass N skip M`).

주의. 다음에 실제 `~/quicbed_gen33`로 이 스크립트를 돌리면 오래된 stage가 지워진다. 감사 시점에 stage는 53개였고 `~/quicbed_gen33` 전체는 3.9G였다(감사 F7·A-E7, 문서). 남기려면 `GEN33_KEEP_STAGES=0`을 주거나 먼저 옮겨 둔다. 이번 작업에서는 실제 위치로 스크립트를 돌리지 않았다.

확인(직접). 아래 A-E1의 CI 흉내 실행에서 임시 HOME에 가짜 stage 7개(수정 시각 10-01~10-07)와 낡은 `go_race.txt`를 미리 넣었다. 빌드 뒤 남은 것은 10-04~10-07의 4개와 새 stage 1개였고, `bin`에는 `go_race.txt`가 없었다.

## A-E1: CI의 Go 단계

문제. setup-go는 GOPATH를 export하지 않는다. `go mod download`는 `$HOME/go`에 받는데 `build_gen33.sh` 15행은 GOPATH가 비면 `$HOME/gopath`를 쓰고 17행에서 `GOPROXY=off`를 켜서 빌드가 모듈을 찾지 못한다(감사 A-E1, 문서). 이 PC의 모듈 캐시가 `$HOME/gopath`에 있으므로 스크립트 기본값은 그대로 두었다.

바꾼 것. `ci.yml`: setup-go 앞에 `echo "GOPATH=$HOME/gopath" >> "$GITHUB_ENV"`를 넣고, `go mod download` 앞에서 `go env GOPATH`가 그 값인지 확인한다. setup-go 캐시도 `go env`를 읽으므로 같은 경로를 쓴다.

확인(직접). `ci.yml`의 Go 단계를 줄 단위로 읽어 그대로 실행하는 흉내 실행을 WSL 임시 HOME에서 했다. 조건은 GOPATH 미설정, PATH에 Go 1.26.6, job env의 `GOFLAGS=-mod=readonly`·`GOTOOLCHAIN=local`이다. 네트워크 대신 `go mod download`에만 로컬 모듈 캐시를 file 프록시(`GOPROXY=file://…`, `GOSUMDB=off`)로 주었다. 이 점이 GitHub runner와 다르다.
- HEAD의 `ci.yml`: `go mod download`는 `$HOME/go`에 받고 rc 0, `build_gen33.sh`는 rc 1이고 `module lookup disabled by GOPROXY=off`가 났다. 감사 재현과 같다. 이때는 HEAD 스크립트의 출력 경로만 임시로 바꿨다.
- 수정한 `ci.yml`: 세 단계 모두 rc 0, `go_test.txt` PASS 249·SKIP 2·FAIL 0, 바이너리 sha256 `902971fd9485…`(같은 소스를 직접 빌드한 값과 같다).

GitHub에서 실제로 돌린 결과는 아니다. 원격 저장소가 없어서 돌리지 않았다.

## F3: lead-hold의 신용 성질(동작 유지)

hold 경로는 결정이 열린 뒤에도 남은 심볼이 누락 수보다 적으면 선행 패리티를 계속 보류하고(`hold.go` 152~155행), TTL 1 s에 도달하면 `tickHoldIndexLocked`의 case 0에서 `expired`로 버린다(`decoder_index.go` 339~342행). 버린 패리티는 스택에 넘어가지 않으므로 증폭 신용이 되지 않는다. 복구에 쓴 선행 패리티도 스택에 넘어가지 않는다. 이것은 `docs/M1_hold_contract.md` "회계와 수명" 절이 정한 설계이고, Python 참조(`hold_wire_reference.py`)와 700116사례 와이어 관문이 이 동작에 묶여 있다. 그래서 동작은 바꾸지 않았다.

해석 주의. 감사 F3 검증자가 lead1·m2·k2로 잰 값(문서)은 다음과 같다. L0만 도착하고 복구가 불가능한 비행에서 hold는 BytesToStack 2350 B, HoldExpired 1246 B, 신용 패리티 0이고, hold를 끈 경로는 BytesToStack 3596 B, 신용 패리티 1이다. 복구가 되는 L0+O0에서는 legacy가 2446 B·신용 1·복구 0, hold가 2350 B·신용 0·복구 1이다. 따라서 X1의 "m4L3 대 m4L3+보류 복호"와 X6의 "v33auto 보류 복호 켬" 팔에서는 "같은 바이트, 같은 신용"이라는 전제가 성립하지 않는다. hold 팔의 결과로 "같은 바이트가 신용과 복구를 함께 산다"고 쓰면 안 된다. 두 팔의 차이에는 복구 이득과 신용 손실이 함께 들어 있다.

## F6: cached_k 과소 추정에 의한 첫 묶음 분할(문서)

cached_k가 실제 k보다 작으면 첫 묶음이 일찍 끝나고, 남은 원본은 다음 묶음(`pre_response_followup`)으로 나간다. `split_suspected`는 실제 크기가 예상보다 작을 때만 켜지고(`flight_trace.go` 83행), 첫 묶음 뒤에는 예상 k가 0이 된다(`flight_input.go` 22~27행). 그래서 이 분할은 표시되지 않는다. C1 첫 비행 장부도 앞 묶음만 덮으므로, 그 연결의 학습 입력은 실제 첫 비행의 일부만 본 관측이다. `docs/T5_timing_contract.md`와 D26이 이 한계를 이미 적었다. 이번에 코드는 바꾸지 않았다. 분석할 때는 `flight_expectation.source`가 cached_k이고 `flight_trace`에 첫 묶음 직후 parity-delay 안에 시작한 후속 묶음이 있는 연결을 따로 떼어 본다. `-profile sealed31`은 expect-k를 0으로 두므로 이 경로를 타지 않는다.

## F8: Go 시험 수 보고와 와이어 관문

HEAD의 기본 Go 시험은 PASS 231, SKIP 2다(감사 F8·A-E8, 문서). SKIP 2개는 `TestHoldPythonReadFromReference`와 `TestUDPHoldPythonReadBatchReference`이고 `M1_REFERENCE_GZIP`이 있어야 돈다. "Go 231 통과"는 이 두 관문이 빠진 수다. 이 묶음 뒤의 기본 Go 시험은 PASS 249, SKIP 2, FAIL 0이다(직접).

와이어 관문 실행 명령. `build_gen33.sh`가 만든 최근 stage 안에서, 또는 같은 구성의 복사본에서 돌린다.

```
cd ~/quicbed_gen33/stage.XXXXXX
M1_REFERENCE_GZIP=/mnt/c/dev/pq_afec_gen33/g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz \
CGO_ENABLED=0 GOFLAGS=-mod=readonly GOTOOLCHAIN=local GOPROXY=off \
go test -count=1 -v -run '^(TestHoldPythonReadFromReference|TestUDPHoldPythonReadBatchReference)$' ./cmd/qamp
```

기준 파일의 sha256은 `59b3434763af6af9b776194b6d21b2f421301eeaa357b38eed1c062312c0dbcf`다(직접). 이번 실행에서 두 시험 모두 PASS였고 각각 "700116 actual decoder cases, 60 configurations"를 출력했다(39.38 s, 42.65 s).

## 검증 전체(직접)

구성: WSL Ubuntu, Go 1.26.6 linux/amd64, `GOPROXY=off`, `GOTOOLCHAIN=local`, `GOFLAGS=-mod=readonly`, HOME과 GOCACHE는 임시 폴더. stage는 `build_gen33.sh`와 같은 구성이고, 묶음 B 담당 파일은 작업 트리에서, 나머지 파일은 HEAD에서 가져왔다. 같은 방식으로 HEAD만 빌드한 바이너리의 sha256은 `41424293588fde08…`로 `docs/S5_test_hygiene.md`에 적힌 배포 바이너리와 같았다. 즉 stage 구성이 실제 빌더와 같다.

| 검사 | 결과 |
|---|---|
| gofmt (생성 파일 `pfail_table.go` 제외) | 형식 어긋남 0개 |
| go vet `./cmd/qamp`, padfec-local-hook | 출력 0줄, rc 0 |
| go test -count=1 | PASS 249, SKIP 2, FAIL 0 |
| go test -race | rc 0, DATA RACE 0건, 149 s |
| M1 와이어 관문 2개 | PASS 2, 각 700116사례 |
| 돌연변이 5종 | 모두 해당 시험이 실패(부록 B) |
| CI 흉내 실행 | HEAD rc 1, 수정본 rc 0 |
| loopback | 부록 A |

이 sha와 시험 수는 "HEAD + 묶음 B" 상태의 값이다. 다른 묶음이 정책 파일을 고치면 바이너리 sha와 시험 수는 달라진다.

## 못 한 것과 넘기는 것

- `flight_shape.go`의 `retransLayout()`은 `retransMode`가 빈 문자열이면 `original_first`를 돌려준다. CLI는 항상 값을 넘기므로 바이너리에서는 이 분기를 타지 않지만, 구조체를 직접 만드는 시험은 이 값을 쓴다(`qamp_retrans_test.go`). 담당 파일 밖이라 그대로 두었다.
- `docs/T6_retrans_contract.md`, `docs/T6_result.md`, codex_handoff의 `DECISIONS_NEEDED.md` D28은 아직 `original_first`를 기본값으로 적고 있다. `docs/c1_status.md` 셋째 문단의 "T7에서 피드백 호환성을 별도로 다뤄야 한다"는 이제 `-feedback-version`과 T7 문서로 처리됐다. 모두 담당 밖이라 고치지 않았다.
- T7 러너(Python)와 `g3bed`의 conn-log 읽기는 만들지 않았다.
- 클라이언트 tracer와 conn-log의 비용, udp-path 두 경로의 HCT 차이, sealed31 gen33과 동결 v3.1의 A/A 일치는 재지 않았다.
- GitHub runner에서 CI를 실제로 돌리지 않았다.
- `build_gen33.sh`는 Go 소스 목록을 명시적으로 적는다(47행). 다른 묶음이 `experiments/quicbed`에 새 비시험 Go 파일을 더하면 이 목록에 넣어야 빌드된다.
- 새 시험 일부는 정책 쪽 타입(`p3Arrivals`, `auto3Plan`, `p3Decision`)과 `chooseFlightExpectation`을 쓴다. 정책 묶음이 이 이름을 바꾸면 함께 고쳐야 한다.

## 부록 A: loopback 출력

`e2e.sh` 출력에서 `client_rc=0` 줄(모든 실행이 0이었다)만 빼고 그대로 옮겼다. 서버는 `-fec on -feedback`(fixed_nofeedback만 `-feedback` 없음), 동결 클라이언트는 `-n 4 -fec on -m 1 -feedback`, gen33 클라이언트는 `-n 4 -fec on -layout v3 -m 2 -lead 1 -feedback`이다. `qamp_head`는 HEAD 소스, `qamp_fixed`는 HEAD + 묶음 B 소스다. gen33 클라이언트 블록은 판본 3 서버, 판본 2 서버 순서다. 출력 파일은 `C:\dev\codex_handoff\v33\runs\v33fix\G\round1_B\out\e2e`에 있다. 아래 인용에서 WSL 사용자 홈 경로의 앞부분은 `<WSL 홈>`으로 가렸다(2026-11-02 통합 정리). 가리지 않은 원문은 같은 폴더의 `binaries.txt`(첫 두 줄), `sealed.server.json`(`conn_log`의 `path`), `refuse4.err`(기존 conn-log 거부)에 있다.

```
902971fd9485fff35553392949e833daac09fabb534be74203dd8dce89a833be  <WSL 홈>/v33fix_tmp/B/e2e/qamp_fixed
41424293588fde08d02a8821b4945ac07f4d0016c61480e0ee2db78936323dae  <WSL 홈>/v33fix_tmp/B/e2e/qamp_head
== frozen client g3c_6baf2b52, server head_default
rows 4 ok 4 server_bytes [4861, 4867, 4877, 4860] fb_recv 0 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version None srv_udp_path oob_readmsg_batch1 srv_profile None
== frozen client g3c_6baf2b52, server fixed_default
rows 4 ok 4 server_bytes [4866, 4876, 4863, 4877] fb_recv 0 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client g3c_6baf2b52, server fixed_v2
rows 4 ok 4 server_bytes [4819, 4817, 4825, 4821] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client g3c_6baf2b52, server fixed_sealed31
rows 4 ok 4 server_bytes [4823, 4819, 4820, 4834] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path basic srv_profile sealed31
== frozen client g3c_6baf2b52, server fixed_nofeedback
rows 4 ok 4 server_bytes [4825, 4828, 4820, 4821] fb_recv 0 fb_magic_seen 0 srv_fb_sent 0 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client gen32_85f54cf5, server head_default
rows 4 ok 4 server_bytes [4865, 4864, 4866, 4867] fb_recv 0 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version None srv_udp_path oob_readmsg_batch1 srv_profile None
== frozen client gen32_85f54cf5, server fixed_default
rows 4 ok 4 server_bytes [4859, 4869, 4861, 4865] fb_recv 0 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client gen32_85f54cf5, server fixed_v2
rows 4 ok 4 server_bytes [4824, 4823, 4820, 4824] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client gen32_85f54cf5, server fixed_sealed31
rows 4 ok 4 server_bytes [4831, 4831, 4819, 4809] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path basic srv_profile sealed31
== frozen client gen32_85f54cf5, server fixed_nofeedback
rows 4 ok 4 server_bytes [4825, 4822, 4812, 4816] fb_recv 0 fb_magic_seen 0 srv_fb_sent 0 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client g2_d98b05d7, server head_default
rows 4 ok 4 server_bytes [4871, 4857, 4861, 4862] fb_recv 0 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version None srv_udp_path oob_readmsg_batch1 srv_profile None
== frozen client g2_d98b05d7, server fixed_default
rows 4 ok 4 server_bytes [4868, 4862, 4866, 4862] fb_recv 0 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client g2_d98b05d7, server fixed_v2
rows 4 ok 4 server_bytes [4820, 4823, 4832, 4819] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path oob_readmsg_batch1 srv_profile default
== frozen client g2_d98b05d7, server fixed_sealed31
rows 4 ok 4 server_bytes [4824, 4822, 4815, 4816] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path basic srv_profile sealed31
== frozen client g2_d98b05d7, server fixed_nofeedback
rows 4 ok 4 server_bytes [4813, 4813, 4834, 4811] fb_recv 0 fb_magic_seen 0 srv_fb_sent 0 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
== gen33 fixed client on version 2 and version 3 servers
rows 4 ok 4 server_bytes [4823, 4821, 4822, 4828] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 3 srv_udp_path oob_readmsg_batch1 srv_profile default
c1_version [3, 3, 3, 3] arrivals [('c1', 4, 0), ('c1', 4, 0), ('c1', 4, 0), ('c1', 4, 0)] retrans_layout ['repeat_first'] tracer ['memory_qlog']
rows 4 ok 4 server_bytes [4818, 4820, 4816, 4822] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path oob_readmsg_batch1 srv_profile default
c1_version [2, 2, 2, 2] arrivals [('c1', 4, 0), ('c1', 4, 0), ('c1', 4, 0), ('c1', 4, 0)] retrans_layout ['repeat_first'] tracer ['memory_qlog']
== sealed31 on both sides
rows 4 ok 4 server_bytes [4829, 4826, 4821, 4830] fb_recv 4 fb_magic_seen 4 srv_fb_sent 4 srv_feedback_version 2 srv_udp_path basic srv_profile sealed31
profile ['sealed31'] wait_ms [200] tracer ['disabled'] pto_scope ['tracer_disabled'] packets [0] c1_version [2, 2, 2, 2] expect ['{"k": 0, "source": "explicit_timer", "scope": "timer_only"}']
conn_log_lines 4 reasons ['shutdown'] keys_unique 4 tx_sizes_nonempty True server_conn_log {'errors': 0, 'lines': 4, 'path': '<WSL 홈>/v33fix_tmp/B/e2e/sealed.conns.jsonl', 'pending': 0, 'retention_ns': 10000000000}
== conn-log expiry before shutdown
before_sigterm lines 4 reasons ['expired'] periodic conns 0 live 0 expired 4
after_sigterm lines 4 beff_stack [3894, 3895, 3893, 3895] tx_dgrams [4, 4, 4, 4]
== CLI refusals
sealed31+oob rc=2 -profile sealed31 fixes udp-path
client+feedback-version rc=2 feedback-version and conn-log are server options
guard+notracer rc=2 revisit-guard needs the client tracer to observe Retry
existing conn-log rc=2 conn-log: open <WSL 홈>/v33fix_tmp/B/e2e/exists.jsonl: file exists
feedback-version 4 rc=2 feedback-version must be 2 or 3, got 4
```

## 부록 B: 돌연변이 확인

고친 곳 하나씩을 원래 코드로 되돌린 복사본에서 해당 시험만 돌렸다(`make_mutants.py`, `run_mutants.sh`).

| 되돌린 곳 | 실패한 시험 | 실패 메시지 일부 |
|---|---|---|
| F1 `buildFeedback`의 판본 선택 | 3/3 | "frozen gen-2/v3.1/v3.2 parser rejected the version 2 reply" |
| F2 `evictAccountLocked`의 기록 | 3/5 (기본 꺼짐·파일 시험은 축출과 무관해 통과) | "conn-log has 0 lines for 5000 connections" |
| F4 기본 retrans-layout | 1/1 | "CLI retrans-layout default \"original_first\" is not the shape priced by …" |
| F5 drop-parity 분기 | 1/1 | "pad_junk ledger: arrivals {Src:c1 Sent:3 Lost:1 …}" |
| B-E6 `t.TempDir()` 분기 | 1/1 | "default test artifact directory survived the test" |

## 통합 정리 (2026-11-02)

묶음 G가 1차 검증의 새 문제(`C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports\B-testbed.md` VERIFY 절)와 1차 handoff(같은 폴더 `NOTDONE_ALL.md`의 B-testbed)를 마무리했다. 같은 날 03:50에 시작한 첫 시도가 04:11에 끊겼으므로, 그 시도가 작업 트리에 남긴 상태를 다시 읽고 확인한 뒤 이어서 했다. 커밋하지 않았다. 아래 "직접" 값은 WSL Ubuntu 임시 복사본(`~/v33fix_tmp/G`, 끝난 뒤 삭제)에서 돌린 것이다. stage는 지금 작업 트리 전체(정책 묶음 변경 포함)를 `build_gen33.sh`와 같은 구성으로 옮겼고, 소스 목록은 그 스크립트의 `GO_SOURCES`에서 읽었다. 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\G\round2`에 있다.

### 1. 빈 retrans-layout 값 (새 문제 2, handoff 5)

`flight_shape.go`의 `retransLayout()`은 `retransMode`가 빈 문자열이면 `original_first`를 돌려줬다. 이제 `defaultRunSettings().RetransLayout`(repeat_first)을 돌려준다.

바이너리에서는 이 분기를 타지 않는다는 1차 판단을 코드로 다시 확인했다. 비시험 코드에서 `fecConn`을 만드는 곳은 `qamp.go`의 `runClient` 한 곳이고, 거기 넣는 값은 `wireRun`이 `checkRunSettings`를 거쳐 넘긴 것이다. `checkRetransLayout`은 빈 값을 거부한다(`TestWireRunRejectsLikeCLI`의 "empty retrans-layout" 경우). 아래 loopback에서도 수정 전후 바이너리의 행이 같았다.

빈 값에 기대던 시험은 시험하려는 모양을 명시하게 했다. `qamp_retrans_test.go`의 `TestRetransOriginalFirstMatrix`, `TestRetransShapeIsFixedAtBundleStart`, `TestRetransIDWrapKeepsFollowup`은 `original_first`를 넘긴다. 새 시험 `TestRetransEmptyModeFollowsCLIDefault`는 m 1~4, lead 0~m, k 1~3에서 빈 값과 `repeat_first`의 와이어 바이트와 행이 같은지 본다.

`qamp_comparison_test.go`의 `comparisonFixture`도 빈 값에 기댄다. 그 시험의 기대 추가 송신 수 `m+1+min(1,m-lead)`는 original_first 모양의 값이다. 이 파일은 이번 묶음이 맡은 목록 밖이라 고치지 않았고, 한 줄(`c.retransMode = "original_first"`) patch를 `C:\dev\codex_handoff\v33\runs\v33fix\G\comparison_fixture_original_first.patch`로 남겼다. 이 patch가 들어가기 전의 작업 트리에서는 `TestComparisonSameSlotsAndAccounting` 1개가 실패한다(아래 검증 표).

### 2. build_gen33.sh의 stage 정리 (새 문제 3, handoff 1·2)

- `GEN33_KEEP_STAGES` 기본값을 0(전부 보존)으로 바꿨다. 정리는 vet, test, `--race`일 때 race, 빌드, `bin` 설치, 출력 폴더 설치와 sha 확인이 모두 끝난 뒤 맨 마지막에 한다. 스크립트가 `set -euo pipefail`이라 앞 단계가 실패하면 정리 블록에 오지 않는다. 지운 경로는 표준 출력과 `$WORK/pruned_stages.log`(UTC 시각, keep 값, 새 stage, 지운 stage)에 남는다.
- Go 소스 목록을 `GO_SOURCES` 변수로 뺐다. `experiments/quicbed`의 `*.go`가 `qamp.go`, `GO_SOURCES`, 별도 프로그램(`client.go`, `dataapp.go`, `mlkemcheck.go`, `server.go`. 각자 `func main`이 있고 `build.sh`가 따로 빌드한다), 시험 glob 가운데 어디에도 들지 않으면 stage를 만들기 전에 종료 2로 멈춘다. 지금 비시험 Go 파일 22개는 `qamp.go` 1개, `GO_SOURCES` 17개, 별도 프로그램 4개로 빠짐없이 나뉜다.
- `OUT`은 `OUT=/tmp/qamp_gen33` 다음 줄에서 `QAMP_GEN33_OUT`으로 덮는 두 줄 형태로 둔다. `tests/test_gen32_build_staging.py`는 스크립트 사본의 `OUT=/tmp/qamp_gen33` 문자열을 바꿔 설치 경로를 임시 폴더로 돌린다. 1차의 한 줄 형태(`OUT="${QAMP_GEN33_OUT:-/tmp/qamp_gen33}"`)에서는 이 바꿔치기가 일어나지 않아 그 시험이 Linux와 CI에서 실패한다(Windows에서는 건너뛰는 시험이라 1차 pytest 수에는 드러나지 않았다). 첫 시도가 두 줄로 고쳐 놓은 것을 확인하고 유지했다. 한 줄 형태에서 시험이 깨진다는 판단은 코드를 읽어서 한 것이다. 바꿔치기할 `OUT=/tmp/qamp_gen33` 문자열이 없으므로 설치 경로가 시험의 `$HOME/install`로 바뀌지 않고, 시험이 읽는 `install/qamp.buildinfo`가 생기지 않는다. 근거로 함께 든 실험(WSL Ubuntu, Python 3.14.4, `round2\oneline_check.sh`, 한 줄 형태 사본에서 ERROR 1개)은 `QAMP_GEN33_OUT`을 설정한 채 돌린 것이라 근거가 섞였다. 그때의 시험은 이 변수가 있으면 두 줄 형태에서도 같은 ERROR를 냈으므로, 그 ERROR 하나로는 한 줄 형태 탓인지 가를 수 없다(통합 검증자 지적, 2026-11-02 정정). 시험은 이제 env를 만든 뒤 이 변수를 지운다(`env.pop('QAMP_GEN33_OUT', None)`, 아래 "통합 정리 (2026-11-02, 통합 담당과 묶음 D)" 절).

확인(직접, `round2\build_script_check.sh`). 임시 HOME에 가짜 stage 7개(수정 시각 10-01~10-07), 이름만 비슷한 폴더 `stage.keepme_not_a_stage`, 낡은 `bin/go_race.txt`를 넣고 저장소 사본의 `build_gen33.sh`를 그대로 돌렸다. `QAMP_GEN33_OUT`도 임시 폴더로 줬다.

| 경우 | 종료 | 남은 stage | 정리 기록 |
|---|---|---|---|
| 기본값, 시험 실패(지금 트리 그대로) | 4 | 가짜 7개, keepme, 새 stage 모두 | 없음 |
| `GEN33_KEEP_STAGES=3`, 시험 실패 | 4 | 모두 | 없음 |
| `GEN33_KEEP_STAGES=abc` | 2 | 모두(새 stage를 만들지 않음) | 없음 |
| 목록에 없는 `extra_unlisted.go`를 더함 | 2 | 모두(새 stage를 만들지 않음) | 없음 |
| 기본값, 시험 통과(fixture patch를 얹은 사본) | 0 | 모두. `bin/go_race.txt`는 지워짐 | 없음 |
| `GEN33_KEEP_STAGES=3`, 시험 통과 | 0 | 새 stage, fake06, fake07, keepme | 5줄(fake05~fake01) |

시험이 통과한 두 경우의 보고 줄은 `gen33 tests pass 266 skip 2`였다. 실행 전후 실제 `~/quicbed_gen33`의 stage는 53개 그대로였고 `/tmp/qamp_gen33`는 생기지 않았다. 실제 경로로는 스크립트를 돌리지 않았다.

### 3. main과 runClient 연결 (새 문제 1)

`qamp.go`에서 플래그 값으로 runClient 인자를 만드는 부분을 `wireRun(mode, profile, explicit, flags, revisitGuard)`로 뺐다. 프로필 이름 정리(`default`를 빈 값으로), `ExpectKSet`, `applyRunProfile`, `checkRunSettings`의 순서는 그대로다. 결과의 `clientWiring`(ExpectK, ExpectKSet, FeedbackWait, RetransLayout, ClientTracer, Profile)을 `runClient`가 한 덩어리로 받고, tracer 설치는 `clientWiring.installTracer`로 뺐다. 서버는 `wiring.Settings`와 `wiring.Profile`을 그대로 쓴다.

새 시험 파일 `qamp_wiring_test.go`의 최상위 시험은 4개다. `TestWireRunClientCarriesResolvedSettings`(9경우: 기본, 이름으로 준 default, sealed31, 프로필이 명시하지 않은 플래그 값을 덮는 경우, 명시값 4종, sealed31과 같은 명시값), `TestWireRunRejectsLikeCLI`(8경우), `TestClientWiringInstallsTracerOnlyWhenEnabled`, `TestWiringMainLoopbackRows`다. 마지막 시험은 `TestMain`이 환경변수를 보고 시험 바이너리 안의 실제 `main()`을 돌리게 해서, sealed31 서버 하나에 sealed31 클라이언트와 기본 클라이언트를 붙인다. 행의 `retrans_layout`, `feedback_wait_limit_ms`, `observation.tracer`, `flight_expectation.source`, `profile`과 서버 stats의 `profile`, `udp_path`, `feedback_version`을 확인한다. 이 시험은 `build_gen33.sh`와 CI의 go test에 그대로 들어간다. 127.0.0.1 UDP만 쓴다.

돌연변이(직접). fixture patch를 얹은 사본에 하나씩 넣고 전체 go test를 돌렸다(`round2\make_mutants.py`, `round2\run_mutants.sh`, 결과 `round2\out\mutants_summary.txt`).

| 돌연변이 | 결과 | 실패한 시험 |
|---|---|---|
| G1 빈 값이면 original_first(1절을 되돌림) | 잡힘 | TestRetransEmptyModeFollowsCLIDefault |
| G3a wireRun이 프로필 적용 전 retrans 값을 넘김 | 잡힘 | TestWireRunClientCarriesResolvedSettings |
| G3b installTracer가 항상 Tracer를 설치 | 잡힘 | TestClientWiringInstallsTracerOnlyWhenEnabled, TestWiringMainLoopbackRows |
| G3c wireRun이 프로필 적용 전 feedback-wait를 넘김 | 잡힘 | TestWireRunClientCarriesResolvedSettings, TestWiringMainLoopbackRows |
| G3d wireRun이 프로필 적용 전 client-tracer를 넘김 | 잡힘 | 위 세 시험 |
| G3e wireRun이 프로필 적용 전 expect-k를 넘김 | 잡힘 | TestWireRunClientCarriesResolvedSettings, TestWiringMainLoopbackRows |
| G3f main이 wireRun 결과 대신 플래그 값으로 clientWiring을 만듦 | 잡힘 | TestWiringMainLoopbackRows |
| G3g runClient가 installTracer 대신 항상 Tracer를 설치(1차 F4_tracer_always_on에 해당) | 잡힘 | TestWiringMainLoopbackRows |
| G3h main이 RetransLayout만 `*retransMode`로 바꿔 넘김(1차 F4_main_passes_raw_retrans에 해당) | 살아남음 | 없음 |
| G3i main이 ClientTracer만 `*clientTracer`로 바꿔 넘김 | 잡힘 | TestWiringMainLoopbackRows |
| G4 conn-log `logged` 표시 제거(4절) | 잡힘 | TestConnLogShutdownThenExpiryKeepsOneLine |

돌연변이 없는 대조는 PASS 266, SKIP 2, FAIL 0이었다.

G3h는 지금 받아들여지는 모든 플래그 조합에서 결과가 같은 돌연변이다. `-retrans-layout`을 명시하지 않으면 플래그 값은 기본값 repeat_first이고 sealed31도 repeat_first를 고른다. 명시하면 기본 프로필에서는 그 값이 그대로 쓰이고, sealed31에서는 다른 값이 종료 2로 거부된다. 그래서 `*retransMode`와 해석된 값이 다른 실행이 없고, 행동으로 잡는 시험도 만들 수 없다. 기본값이나 sealed31 값 가운데 하나가 바뀌면 `TestWiringMainLoopbackRows`의 sealed31 행 기대(repeat_first)가 이 돌연변이를 잡는다. 같은 연결은 G3a(wireRun 안)와 G3f(main 전체)가 지키고, 둘 다 잡혔다. 첫 시도의 돌연변이 실행(04:06~04:08)은 `TestWiringMainLoopbackRows`를 쓰기 전이라 G3f와 G3g가 살아남았다(`round2\attempt1\out\mutants_summary.txt`).

### 4. conn-log의 logged 표시 (새 문제 5)

표시를 지우지 않고 시험을 더했다. `TestConnLogShutdownThenExpiryKeepsOneLine`은 계정 2개를 끝낸 뒤 두 순서를 본다. 첫째는 `finishConnLog`의 시각이 계정 수명과 같아서, 그 안의 flush가 방금 shutdown으로 넣은 계정을 만료시키는 순서다. 둘째는 finish 뒤 수명이 지난 시각에 flush가 다시 도는 순서다. 두 경우 모두 줄 2개, 키 2개, reason은 모두 shutdown, 오류 0, 대기 0, 닫기 1회, 남은 계정 0이어야 한다. 표시를 지운 돌연변이 G4는 첫째 순서에서 같은 계정의 `expired` 줄이 한 번 더 써져 실패했다. 둘째 순서(표시가 없으면 닫힌 파일에 쓰려는 줄이 오류로 세어진다)는 첫째에서 먼저 실패해 돌연변이로 따로 돌려 보지는 않았다. 실제 서버에서는 SIGTERM 처리기가 `finishConnLog`를 부른 뒤 `os.Exit`까지 100 ms flush 고루틴이 계속 돌 수 있으므로(`qamp.go` `runServer`) 이 표시가 필요하다.

### 5. T7_conditions_v31.md (새 문제 4)

첫 시도가 넣은 `-feedback` 행, 예시 두 갈래, 규칙 3의 조건을 다시 확인하고 출처를 고쳤다. 첫 시도는 봉인 v3.1 러너를 gen31 `g3bed.py`와 0단계 러너 `g3_stage0.py`로 적었다. v3.1 3단계 봉인 러너는 `p21_gencompare.py`다(gen31 `g3/PROTOCOL_stage3.md` 5행). 그 러너의 `start_server`(2264~2280행), `run_client`(2323~2336행), `ARMS`(293~306행)에 `-feedback`이 없음을 읽어서 확인했다. 재현 예시의 근거는 그 러너의 고정 팔 `g3fixL3`(m4L3, 298행), `profile`(274~278행: ML-KEM 조건의 expect-k 2, netem 대역 제한이 있으면 gap 50 ms, 없으면 8 ms), `TIMEOUT_S`(88행, 10 s)로 바꿨다. gen31 `experiments`에서 `-feedback`을 넘기는 곳은 `p17_adaptive_value.py` 367행 하나다. v33auto 예시에는 `-feedback`이 없으면 `c1_seen`이 켜지지 않아 v3.3.1-dev가 v3.2-dev와 같게 돈다는 이유를 더했다. 규칙 4의 근거도 3단계 러너로 바꿨다. 두 예시 명령은 아래 loopback에서 그대로 돌았다.

### 6. retrans-layout 기본값을 적은 문서 (새 문제 2, handoff 4)

`T6_retrans_contract.md`, `T6_result.md`, `M4_revisit_policy_contract.md`, `T3_comparison_contract.md`, `J3_reference_result.md`, `J3_diagnostic_plan.md`, `O2_world_result.md`, `J5_world_diagnostic_plan.md` 맨 위에 "2026-11-02 정정:" 줄을 넣고 본문은 그대로 두었다. 각 줄은 그 문서가 original_first를 기본값으로 적은 자리를 가리키고, 지금 기본값 repeat_first와 명시 옵션 original_first, 근거(이 문서와 루프 결정 D43)를 적는다. M4 계약과 T3 계약에는 "활성 L1 상태4"가 지금은 v3.3.1-dev(상태 판본 11)라는 점, O2 결과에는 1457 B 패리티 후보가 v3 후보의 1452 B 상한(`policy.QUICGO_MAX_IPS`, `docs/V33FIX_policy.md`)으로 빠진다는 점, J3 결과에는 지금 기본 와이어의 후속 묶음이 그 문서의 "과거 repeat_first 와이어"와 같은 규칙이라는 점을 더했다. D28 본문은 루프 묶음의 파일이라 고치지 않았다. `DECISIONS_NEEDED.md` 67행 D28 제목에 "2026-11-02 D43으로 대체됨"이 이미 붙어 있음을 읽어서 확인했다.

### 7. c1_status.md

셋째 문단의 "T7에서 피드백 호환성을 별도로 다뤄야 한다"를 `-feedback-version 2|3`(기본 3, 서버 전용), 판본 2에서 달라지는 진단 필드, 동결 클라이언트가 붙는 서버의 설정, `docs/T7_conditions_v31.md`와 이 문서 F1 절을 가리키는 문장으로 바꿨다. 현재 상태를 적는 문서라 본문을 고쳤다.

### 8. Go 시험 수 (S5_test_hygiene.md, M4_cache_result.md, F8)

두 문서의 "Go 시험 231개"와 "Go231시험"을 "PASS 231, SKIP 2, 감사 시점"으로 고치고, SKIP 2개가 M1 와이어 관문이라는 점을 붙였다. S5 문서 끝에는 지금 수와 관문 실행 명령을 덧붙였다. S5가 인용하는 보존 stage `~/quicbed_gen33/stage.mBIfxw`는 읽기 전용으로 확인했을 때 남아 있었다. 그 안의 `build_record/qamp.sha256`은 `41424293588fde08…`, `qamp.srcsha`는 `9798aa226a1a1246…`, `go_test.txt`는 PASS 231, SKIP 2로 S5 문서와 같았다.

### 9. S2_hygiene.md

`C:\dev\R-E-wt\hygiene-clone-check`는 1차 루프 묶음이 스크래치로 옮겨서 지금 없다(`workflow_reports\E-loop.md`). 맨 위에 정정 줄을 넣고, 확인 명령의 마지막 줄을 새 clone을 임시 폴더에 만들어 `verify_seals.py`를 돌린 뒤 지우는 절차로 바꿨다. 그 PowerShell 절차를 그대로 돌렸고(R-E는 읽기만 했다) hygiene 브랜치 85b00b6에서 `status` PASS, 92파일 중 92개 일치였다. Git Bash로 같은 clone을 만들어 센 분류도 S2 본문과 같았다(stage3 31+14, stage2 29+9, stage0 3+6, `round2\reclone_verify_seals.json`).

### 검증 (직접)

| 검사 | 지금 작업 트리 | fixture patch를 얹은 사본 |
|---|---|---|
| gofmt | 생성 파일 `pfail_table.go` 1개만 걸림(HEAD와 같음) | 같음 |
| go vet `./cmd/qamp`, padfec-local-hook | rc 0, 0줄 | rc 0, 0줄 |
| go test -count=1 | PASS 265, SKIP 2, FAIL 1(`TestComparisonSameSlotsAndAccounting`) | PASS 266, SKIP 2, FAIL 0 |
| go test -race | rc 1, DATA RACE 0건, 실패는 위 1개뿐, 106 s | rc 0, DATA RACE 0건, 95 s |
| M1 와이어 관문 2개(`M1_REFERENCE_GZIP`) | PASS 2, 각 700116사례·60설정(40.27 s, 42.66 s) | 돌리지 않음(시험 파일 한 줄 차이) |
| `-trimpath` 바이너리 sha256 | `06520d52c2f5ee50f0329548a9351030e54030e21ef7ec46b85c46d171c2e3fb` | 같음(바뀐 것은 시험 파일뿐) |
| 돌연변이 11종 | 해당 없음 | 10종 잡힘, G3h 살아남음(3절) |
| `build_gen33.sh` 가짜 HOME 6경우 | 2절 표 | 2절 표 |

M1 기준 gzip은 `g3/v33/validation/M1_stage1/runs/M1_wire_reference_02.tsv.gz`(git 추적, sha256 `59b3434763af6af9b776194b6d21b2f421301eeaa357b38eed1c062312c0dbcf`)다. SKIP 2개는 이 관문이다. 이번 묶음이 더한 최상위 시험은 6개다(`qamp_wiring_test.go` 4개, `TestRetransEmptyModeFollowsCLIDefault`, `TestConnLogShutdownThenExpiryKeepsOneLine`). 시험 수와 sha는 이 시각 작업 트리의 값이라, 다른 묶음이 Go 파일을 고치면 달라진다.

### loopback (직접)

`round2\e2e_g.sh`. 지금 트리의 바이너리(`qamp_cur`, 위 sha)와, 같은 트리에서 `qamp.go`와 `flight_shape.go`만 첫 시도 전 상태(1차 B 결과, `round2\orig`)로 되돌린 바이너리(`qamp_preG`, sha256 `8be4c740b95376fb9dfa865b3bec3e139ae5a8296b8151f87446457200a1a5f4`)를 같은 순서로 돌렸다. 다섯 경우의 출력 줄(행 수, 프로필, 재전송 모양, 대기, tracer, 첫 묶음 기대, arrivals, 패리티 수, 서버 stats, conn-log)이 두 바이너리에서 한 줄도 다르지 않았다. 아래는 `qamp_cur` 쪽 출력에서 `client_rc=0` 줄(10번 모두 0)만 뺀 것이다. 각 경우의 명령은 다음과 같다. 봉인 재현은 서버 `-profile sealed31 -fec on -conn-log`, 클라이언트 `-profile sealed31 -fec on -layout v3 -m 4 -lead 3 -expect-k 2 -gap 50ms -timeout 10s -n 4`다. v33auto는 서버 `-profile sealed31 -fec on -feedback`, 클라이언트 `-profile sealed31 -fec auto3 -cache3 … -feedback -n 4`다. 기본 행은 서버 `-fec on`, 클라이언트 `-fec on -layout v3 -m 2 -lead 1 -n 4`다. 후속 묶음 강제는 서버 `-fec on`, 클라이언트 `-fec on -layout v3 -m 2 -lead 1 -expect-k 2 -drop-initial 0,1 -drop-parity 0 -n 3`이고 둘째 줄만 `-retrans-layout original_first`를 더했다. n=3~4 기능 확인이고 효과 크기가 아니다.

```
== cur sealed31 both sides, no -feedback (sealed v3.1 reproduction, m4L3)
rows 4 ok 4
  profile ['"sealed31"'] retrans_layout ['"repeat_first"'] wait_ms ['200']
  tracer ['"disabled"'] pto_scope ['"tracer_disabled"'] expectation ['{"k": 2, "scope": "all_flights", "source": "explicit"}']
  arrivals_src ['"none"'] c1_version ['0'] parity_sent [5, 5, 5, 5] later_parity_sent [1, 1, 1, 1]
  server profile sealed31 udp_path basic feedback_version 2 fb_sent 0
  conn_log lines 4 reasons ['shutdown'] keys_unique 4
== cur sealed31 both sides with -feedback, auto3 (v33auto learning arm)
rows 4 ok 4
  profile ['"sealed31"'] retrans_layout ['"not_applicable"', '"repeat_first"'] wait_ms ['200']
  tracer ['"disabled"'] pto_scope ['"tracer_disabled"'] expectation ['{"k": 0, "scope": "timer_only", "source": "explicit_timer"}']
  arrivals_src ['"c1"'] c1_version ['2'] parity_sent [0, 5, 5, 5] later_parity_sent [0, 1, 1, 1]
  server profile sealed31 udp_path basic feedback_version 2 fb_sent 4
== cur default server and default client row
rows 4 ok 4
  profile ['"<absent>"'] retrans_layout ['"repeat_first"'] wait_ms ['1000']
  tracer ['"memory_qlog"'] pto_scope ['"qlog_loss_timer_expired_lower_bound"'] expectation ['{"k": 0, "scope": "timer_only", "source": "timer_only"}']
  arrivals_src ['"none"'] c1_version ['0'] parity_sent [3, 3, 3, 3] later_parity_sent [1, 1, 1, 1]
  server profile default udp_path oob_readmsg_batch1 feedback_version 3 fb_sent 0
== cur forced pre-response follow-up, retrans-layout default
rows 3 ok 3
  profile ['"<absent>"'] retrans_layout ['"repeat_first"'] wait_ms ['1000']
  tracer ['"memory_qlog"'] pto_scope ['"qlog_loss_timer_expired_lower_bound"'] expectation ['{"k": 2, "scope": "all_flights", "source": "explicit"}']
  arrivals_src ['"none"'] c1_version ['0'] parity_sent [4, 4, 4] later_parity_sent [3, 3, 3]
  server profile default udp_path oob_readmsg_batch1 feedback_version 3 fb_sent 0
== cur forced pre-response follow-up, retrans-layout original_first
rows 3 ok 3
  profile ['"<absent>"'] retrans_layout ['"original_first"'] wait_ms ['1000']
  tracer ['"memory_qlog"'] pto_scope ['"qlog_loss_timer_expired_lower_bound"'] expectation ['{"k": 2, "scope": "all_flights", "source": "explicit"}']
  arrivals_src ['"none"'] c1_version ['0'] parity_sent [3, 3, 3] later_parity_sent [2, 2, 2]
  server profile default udp_path oob_readmsg_batch1 feedback_version 3 fb_sent 0
```

후속 묶음 강제 두 줄의 `parity_sent`·`later_parity_sent`(repeat_first 4·3, original_first 3·2)는 1차 검증자가 같은 조건에서 잰 값(B-testbed.md VERIFY의 F4 항목)과 같다.

### 증거 보존

`C:\dev\codex_handoff\v33\runs\v33fix\G` 아래에 두었다. 복사한 파일은 원본과 sha256을 대조했고, 전체 목록과 해시는 `SHA256SUMS.txt`에 있다.

- `round1_B`: 1차 묶음 B의 스크립트와 출력(세션 스크래치 `v33fix\B`의 `*.sh`, `*.py`, `*.yml`, `out`). 앞 절들이 가리키는 출력이 여기 있다.
- `round1_B_verify`: 1차 검증자의 스크립트와 출력(`out`, 돌연변이별 로그 포함). 돌연변이별 소스 사본(약 82 MB)은 옮기지 않았다.
- `round2`: 이번 묶음의 스크립트, 출력, 돌연변이 patch, 첫 시도 전 파일 사본(`orig`), 첫 시도의 스크립트와 출력(`attempt1`).
- `comparison_fixture_original_first.patch`: 1절의 한 줄 patch.

이 문서 앞 절의 경로도 바꿨다. 감사 원문은 세션 스크래치 대신 `C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01`(감사 `.md` 8개가 스크래치 원본과 바이트 단위로 같음을 확인했다), 1차 스크립트와 출력은 `round1_B`를 가리킨다.

### 못 한 것과 넘기는 것

- `qamp_comparison_test.go`의 fixture 한 줄은 맡은 목록 밖이라 고치지 않았다. 통합 때 위 patch를 적용하면 Go 시험이 PASS 266, SKIP 2, FAIL 0이 된다(대조 실행으로 확인).
- G3h는 결과가 같은 돌연변이라 행동 시험으로 잡을 수 없다(3절).
- `.github/workflows/ci.yml`은 바꾸지 않았다. 새 시험은 `build_gen33.sh`의 go test에 그대로 들어가고 소스 목록 검사도 같은 스크립트 안에 있어서 바꿀 곳이 없었다. GitHub runner에서는 돌리지 않았다(원격 저장소 없음).
- 루프 폴더의 `MORNING_REPORT.md`의 "Go 231" 문구와 `DECISIONS_NEEDED.md` D28 본문은 루프 묶음의 파일이라 고치지 않았다.
- 1차에서 넘긴 T7 러너와 `g3bed`의 conn-log 읽기, tracer·conn-log 비용, udp-path 두 경로의 HCT, sealed31 gen33 대 동결 v3.1 A/A는 이번에도 하지 않았다.
- 보호 경로 `~/quicbed_gen33`의 stage 53개와 `test_artifacts` 4,005개는 읽기 전용으로 세기만 했다. `bin/go_race.txt`(11-01 07:03)는 `bin/qamp`(11-01 08:19)보다 오래된 race 기록이다. 다음 실제 빌드가 성공하면 `build_gen33.sh`가 지운다.

## 통합 정리 (2026-11-02, 통합 담당과 묶음 D)

묶음 G 뒤의 검증(`C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports2\VERDICTS.md`의 G-testbed new_problems)이 짚은 것을 통합 담당(Claude)과 묶음 D가 나눠 처리했다. 커밋하지 않았다.

통합 담당이 고친 세 가지(07시대). 묶음 D는 고치지 않고 작업 트리에서 결과만 읽어 확인했다.

- 비교 시험 fixture. 검증자 지적 "지금 작업 트리의 Go 시험이 1개 실패해 build_gen33.sh가 바이너리를 만들지 못한다". 위 1절의 patch(`runs\v33fix\G\comparison_fixture_original_first.patch`)를 적용해 `experiments/quicbed/qamp_comparison_test.go`의 `comparisonFixture`에 `c.retransMode = "original_first"`가 들어갔다(지금 19행). 1절과 "못 한 것과 넘기는 것"의 "patch가 들어가기 전" 문장은 이 적용 전의 상태다.
- 소스 목록 검사의 안내 문구. 검증자 지적 "build_gen33.sh 소스 목록 검사가 패턴 밖 시험 파일에 틀린 안내를 낸다". `experiments/quicbed/build_gen33.sh` 43행의 종료 2 메시지 끝에 "; test files must match qamp_*_test.go, policy_*_test.go or policy3*_test.go"가 붙었다. 동작(종료 2로 멈춤)은 같다.
- 스테이징 시험의 환경변수. 검증자 지적 "test_gen32_build_staging.py가 환경의 QAMP_GEN33_OUT에 따라 실패하고, 한 줄 형태 실험 근거가 이 변수로 섞였다". `tests/test_gen32_build_staging.py`가 env를 만든 뒤 `env.pop('QAMP_GEN33_OUT', None)`을 한다. 묶음 D가 WSL Ubuntu(Python 3.14.4)에서 저장소 사본(`~/v33fix_tmp/D3`, 끝난 뒤 삭제, 두 파일 sha256을 작업 트리와 대조)으로 직접 돌렸다. 고친 시험은 `QAMP_GEN33_OUT`을 뺀 채로도, 준 채로도 2개 모두 통과했고 준 경로에는 아무것도 생기지 않았다. 같은 사본에 HEAD 판 시험을 두면 변수를 뺀 채로는 통과, 준 채로는 `install/qamp.buildinfo`가 없어 ERROR 1개였다. 두 실행 모두 `/tmp/qamp_gen33`는 생기지 않았다(`C:\dev\codex_handoff\v33\runs\v33fix\D3\wsl_staging_out.txt`, `wsl_staging_head_out.txt`). 2절의 한 줄 형태 근거 문장은 이 지적에 맞춰 "코드 읽기로 판단했고, 그때 실험은 이 변수가 설정된 상태라 근거가 섞였다"로 고쳤다. 한 줄 형태를 이 변수 없이 다시 돌려 보지는 않았다. 그 형태는 바꿔치기가 일어나지 않아 공유 경로 `/tmp/qamp_gen33`에 시험용 가짜 바이너리를 설치하기 때문이다.

검증자 info 지적 "빈 retransMode에 기대는 다른 시험이 이제 original_first 대신 repeat_first 경로를 탄다". 1절에서 빈 값의 뜻을 repeat_first로 바꿨으므로, `retransMode`를 정하지 않고 `fecConn`을 만들어 후속 묶음까지 가는 시험은 이제 repeat_first 모양을 시험한다. 예는 `experiments/quicbed/qamp_hold_quic_test.go` 168행의 실제 QUIC dial이다(`fecConn` 구성에 `retransMode`가 없고, 201행 로그에 `flights`가 남는다. 검증자 실행에서는 `flights=2`). 바이너리 기본값과 같은 모양이라 결함은 아니다. original_first 후속 모양을 덮는 시험은 이제 값을 명시한 `qamp_retrans_test.go`의 세 시험과 patch 뒤의 비교 시험이다. hold QUIC 시험에 두 모양을 모두 명시하는 경우를 더할지는 다음 시험 정리 때 정한다(지금 고칠 것 없음).

묶음 D가 이 문서에서 바꾼 것. 검증자 지적 "V33FIX_testbed.md와 S5_test_hygiene.md에 WSL 사용자 홈 경로가 남아 있다"에 따라 9행의 임시 폴더를 `~/v33fix_tmp/B`로 적고, 부록 A의 원출력 인용 네 줄(바이너리 sha 두 줄, sealed31 conn-log 경로, 기존 conn-log 거부)은 경로 앞부분을 `<WSL 홈>`으로 가렸다. 가리지 않은 원문은 부록 A 머리에 적은 `round1_B\out\e2e`의 세 파일에 있다. 2절 한 줄 형태 근거 문장은 위처럼 고쳤다. 맨 위 정정 줄은 "맨 끝" 대신 두 통합 정리 절을 가리키게 했다. 고친 뒤 이 문서에 사용자 홈 경로(`tools/scrub_for_publish.py`의 `user_path` 정규식)가 든 줄은 0이다.

`docs/S5_test_hygiene.md`. 묶음 G가 새로 쓴 59행의 보존 stage 경로를 `~/quicbed_gen33/stage.mBIfxw`로 바꿨다. 19행의 WSL 사용자 홈 경로 두 개(보존 stage와 `bin/qamp`)는 S5 커밋 `3eef6a737`부터 있던 본문이라 그대로 두었다. S5는 반복 62 시점의 기록이므로 정정 줄 정책대로라면 본문을 다시 쓰지 않는다. 이 경로는 사실이 틀린 것이 아니라 공개 전 위생 문제이고, 공개본에서는 `docs/PUBLISH_PROCEDURE.md`의 `--check`가 이 파일을 사용자 경로 파일로 잡는다. 같은 19행의 "Go 시험(PASS 231, SKIP 2, 감사 시점 …)"은 묶음 G가 HEAD 문장 "Go 시험 231개"를 본문에서 직접 고친 것이라 엄밀히는 정정 줄 정책에서 벗어난다. 숫자 231은 그대로이고 같은 뜻을 끝의 "Go 시험 수와 M1 와이어 관문" 절이 적으므로 정보가 사라지지는 않았다. 지시대로 19행은 두었고, HEAD 문장으로 되돌리고 맨 위 정정 줄로 옮길지는 사람이 정할 일로 남긴다.

Go 시험 수는 여기 적지 않는다. 위 세 변경 뒤의 Go 전체 시험은 통합 담당이 따로 돌려 기록한다. 묶음 D의 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\D3\`에 있다(목록과 sha256은 그 폴더의 `SHA256SUMS.txt`).
