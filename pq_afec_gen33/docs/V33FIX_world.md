# V33FIX 묶음 C: 세계 시뮬레이터와 판정 통계 도구

2026-11-02 KST. 모든 수치는 독립 사건 세계의 개발 시뮬레이션이며 실측이나 확증이 아니다. 숫자마다 결과 파일을 단다. "직접 확인"은 이번에 실행해서 얻은 값이고, "문서에서 읽음"은 기존 보고서나 감사 원문의 값이다.

이 문서에서 "a ± b"의 b는 짝 차이(같은 seed와 연결 번호로 두 쪽을 평가한 연결별 차이)의 표준오차 1 SE, 곧 표본표준편차/√n이다. 신뢰구간이 아니다. 대괄호 [하한, 상한]은 그 자리에 적은 수준(99% MC, 95% seed 등)의 구간이다.

동결 세계(`experiments/v33/worldsim.py`, `worldparams.json`, `oracle.py`, `bench*.py`)는 고치지 않았다. 두 세계 파일의 SHA-256은 `g3/v33/bench_protocol.json`의 world.source_sha256과 지금도 같다(`tests/test_v33fix_world.py`가 검사). 새 규칙과 진단은 새 모듈로 만들었다.

| 감사 ID | 처리 | 결과 위치 |
|---|---|---|
| C-E6, E-M1-2, E14 세계 부분, E 검증자 missed 2 | M1 세계 수정과 lead=0 불변식 시험 | 1절 |
| E-M1-3 | 보류 수신기 기한 업링크를 D20 2000 kbps 기본값으로 | 1절, 5절 |
| C-E1, D-E1, E10 | Z1 규칙 등록 뒤 J6 재판정 | 2절, `docs/V33FIX_bench_rules.md`, `docs/J6_disposition.md` 덧붙임 |
| C-E3, C 검증자 missed | ACK·패킷화 민감도 | 3절 |
| C-E5 | Initial 계수 대안 정의 | 4절 |
| E-J8-1 | 서버 PTO 기준 진단 | 4절 |
| E-M1-1, E-M1-4, E 검증자 missed 1 | 후보 비용 모형 결함 수치화 | 5절, `docs/M1_world_validity.md` 덧붙임 |
| C-E2, C-E8, C-E9, D-E2, D 검증자 missed | 다음 평가 규칙 | `docs/V33FIX_bench_rules.md` 2절 |
| C-E4, C-E10 | 후속 과제로만 기록 | `docs/V33FIX_bench_rules.md` 2.6 |

## 1. M1 세계 수정

`experiments/v33/worldsim_m1.py`와 `worldparams_m1.json`에서 1차 수정 때 네 가지를 바꿨고, 통합 정리에서 한 가지(다섯째)를 더 고쳤다.

첫째, `m1_outputs`가 보류 수신기의 반환 token마다 `flush_server`를 부르던 것을 없앴다. 이제는 도착한 원본 'O'를 수신기에 넣은 뒤에만, 서버가 ready이고 완료 전이면 송신을 재개한다. 동결 기본 세계의 off 경로(`worldsim.py` 819~840행: 원본 도착 때만 flush, 패리티는 신용만)와 같은 의미다. 패리티 도착, 복구된 원본, 수신기 타이머는 송신을 재개하지 않는다.

둘째, 서버가 ready이거나 ready가 예약된 뒤 도착한 패리티(L, P)는 보류 수신기를 거치지 않고 패리티 크기 그대로 신용만 더한다. off 경로의 'P' 처리(ready 또는 ready_scheduled이면 credit)와 같다. 이 규칙이 없으면 늦은 비행의 패리티가 복구에 쓰여 원본 크기(1280 B)로 신용이 들어가고, off는 패리티 크기(1331 B)로 넣는다. 일부러 만든 경우(첫 비행 원본0만 도착, 재전송 비행 원본1과 패리티 도착, 손실 0)에서 수정 전 hold의 서버 신용은 6486 B, off는 6537 B였고 수정 뒤에는 둘 다 6537 B다(직접 확인, `tests/test_v33_m1_world.py`의 test_parity_after_ready_is_credit_not_recovery).

셋째, 수신기는 시각을 정수 ns로 다룬다. 수신 사건과 같은 순간에 나온 출력에 `stamp / 1000000`을 그대로 쓰면 사건 시각이 1e-13 ms 단위로 달라져 off와 hold의 HCT가 부동소수점 끝자리에서 갈렸다(예: c12000 p0.25 seed31 (12,0,0) 연결1에서 384.9322700995772 대 384.9322700995771 ms). 수신 사건 시각과 같은 ns의 출력에는 사건의 float 시각을 쓴다. 타이머 출력의 시각은 바뀌지 않는다.

넷째, E-M1-3에 따라 `worldparams_m1.json`에 `hold_uplink_source`("fixed" 기본, "context")와 `hold_uplink_kbps`(2000)를 넣었다. 기본은 Go 서버의 `-lead-hold-uplink-kbps` 기본값 2000(D20, `experiments/quicbed/qamp.go`, HEAD d67717d9b 기준 3723행, E 감사 인용)이다. 문맥의 참 업링크는 `hold_uplink_source: "context"`로 명시할 때만 쓰는 진단 옵션이다. "fixed"이면 문맥 업링크가 정수 kbps가 아니어도 거부하지 않는다.

다섯째(2026-11-02 통합 정리에서 추가), retry 문맥에서 hold의 initial_failure를 고쳤다. buffered 모드는 결과를 만들 때 first_failure를 첫 비행 원본이 수신기에서 몇 개 나왔는지(`len(first_delivered) < k`)로 다시 쓴다. retry 문맥(`context.retry`이고 `features.token_retry`가 켜짐)에서는 첫 비행 데이터그램이 서버의 Retry 처리에서 버려져 수신기에 들어가지 않는다. 그래서 이 덮어쓰기가 모든 연결을 initial_failure=True, world_class "failure"로 만들었다(1차 검증 retry_check.py, seed 777, 1500연결: hold 1500/1500, off 115/1500). 이제 retry 문맥에서는 덮어쓰지 않고, 첫 비행을 보낼 때 계산한 `first_flight_outcome(..., "buffered")` 값을 그대로 쓴다. off와 동결 기본 세계(`worldsim.py` 596행)도 retry와 상관없이 첫 비행 도착 패턴으로 이 값을 정하므로 정의가 같아진다. Retry 뒤 첫 비행으로 정의를 바꾸는 방법도 있었지만, 그러면 동결 기본 세계와 off의 정의와 달라져 lead=0 불변식이 깨지므로 쓰지 않았다. first_failure는 사건 처리에 쓰이지 않고 결과의 initial_failure와 world_class에만 들어가므로 HCT, 송신, 신용은 이 수정 전후로 같다.

확인은 이렇게 했다. 시험 `test_lead_zero_hold_matches_off_across_loss_seeds_and_contexts`는 큰cert(16000 B)와 B7(s2c 1%) 문맥, p 0·0.02·0.15·0.25, seed 31·50, δ 0·12, trailing 0~4의 160조합 각 40연결에서 HCT, 서버 송신 목록(시각·종류·크기·도착·재전송), event_count를 뺀 모든 결과 필드가 off와 같음을 확인한다. 감사가 찾은 연결(큰cert p0.25 (0,0,1) seed31 연결 2041)과 최소 재현(손실 0, trailing 3·4, 둘 다 117.96 ms)도 시험에 넣었다. 시험보다 넓은 스크래치 검사(문맥 5개: 큰cert, B7, B10, B12 c6000, B12 c12000 × p 4개 × seed 2개 × δ 2개 × trailing 5개 = 400조합, 각 3000연결, 스크립트 `C:\dev\codex_handoff\v33\runs\v33fix\W\C_round1\lead0_scan.py`)에서도 event_count 말고는 차이가 0이었다. 1차 때는 출력이 파일로 남지 않아 통합 정리에서 지금 세계(383034eb…)로 다시 돌렸고 결과는 같았다(`W\round2\r3_lead0_scan_out.txt`). 같은 검사를 둘째 수정만 뺀 보존 사본(`W\C_round1\nobypass\`, worldsim_m1.py f7b1629c…)으로 돌리면 HCT와 송신 목록은 400조합 모두 같지만 서버 신용 바이트가 142조합(B10 46, 나머지 네 문맥 각 24)에서 달랐다. 조합당 최대는 66/3000연결(B10 p0.25 seed31 δ 0·12 trailing 1)이다(`W\round2\r3_lead0_scan_nobypass_out.txt`, 집계 `r3_count_nobypass_out.txt`). 1차 판 이 문장의 "최대 52/3000연결(c12000 p0.25 seed50)"은 틀렸다. 52는 B10을 뺀 네 문맥의 p0.25 seed50 trailing 1 값이다.

위 검사에는 token과 retry 문맥이 없었다. 1차 검증이 문맥 11개(token, retry 포함), 변형 3개, seed 3개로 80만 쌍을 비교했을 때 차이는 retry 문맥의 initial_failure·world_class에서만 나왔다(69432행). 그래서 1차 수정 시점의 "event_count를 뺀 모든 결과 필드가 같다"는 retry 문맥에서는 틀렸고, 다섯째 수정으로 고쳤다. 통합 정리에서 시험 두 개를 더했다. test_lead_zero_hold_matches_off_with_token_and_retry는 큰cert·B7 × token·retry × p 4개 × seed 2개 × δ 2개 × trailing 5개 = 320조합, 각 20연결에서 위와 같은 항목을 비교한다. test_retry_initial_failure_follows_first_flight_pattern은 retry 문맥에서 lead 0~4와 첫 비행 64패턴 전부에 대해 initial_failure가 "도착 2개 미만"과 같은지 본다. 다섯째 수정 전 코드에서 두 시험은 하위 시험 3084개(전부 retry 쪽, token 0개)와 285개가 실패했고, 고친 뒤 모두 통과했다(직접 확인). 1차 검증 스크립트 lead0_verify.py를 고친 세계에 그대로 다시 돌린 결과는 끝의 통합 정리 절에 적었다.

수정 뒤 세계의 SHA-256은 worldsim_m1.py 383034eb7b8cfb2468ae4223682e9dd9ad412d11e3f76b9bae0f56820e7a035d(2026-11-02 통합 정리 판본, 1차 수정 판본 36e619e0…cfbadc와는 다섯째 수정 한 줄만 다르다), worldparams_m1.json b817e32c5934a1191342727668944ddf3cb59896ef3cbcfbd71470ebbcc3538b다. 동결 M1 결과(`g3/v33/M1_benchmark_v1.json`)를 만든 세계는 커밋 46c80bb9e의 HEAD 판본(worldsim_m1.py SHA-256 fc427330…78c7, M1 실행 manifest의 값과 같음)으로 남아 있고, Codex의 한 줄 진단 사본은 `g3/v33/validation/M1_complete_results/handoff/runs/M1_wakeup_diagnostic_v1/`에 있다. 해시가 달라졌으므로 bench_m1이 동결 계획으로 다시 돌지 않는다. M1 전체 120셀 재평가는 하지 않았다(E14~E16 후속).

## 2. 영분산 규칙 Z1과 J6 재판정

규칙은 `docs/V33FIX_bench_rules.md` 1절에 결과 전에 썼다(문서 수정 시각 2026-11-01T16:47:37Z = 01:47:37 KST, 재판정 시작 01:50:32 KST, 둘 다 `g3/v33/V33FIX_J6_rejudge_v1.json`에 기록). 규칙 본문 SHA-256(124952bb…c2e0)은 `experiments/v33/zero_variance.py`에 고정했고, 다르면 재판정이 실행되지 않는다.

`experiments/v33/v33fix_j6_rejudge.py`는 J6 보고서의 원자료(L1·J6·margin0·v31·v32 B12_c6000 원시 실행 200개, 행동 표 18개)를 J6 provenance 해시와 대조해 읽고, 저장된 14개 대조의 seed 요약과 MC 경계를 정확히 재현한 뒤(14/14) Z1을 적용했다(직접 확인).

| Z1 쌍 (B12 c6000) | 행동 seed | 기준 seed | 비짝 차이 (ms) | 99% 구간, F=116 (ms) | 짝 점추정 g (ms) | 채운 반폭 h (ms) |
|---|---|---|---:|---|---:|---:|
| p0.08 (12,0,4) 대 (7,0,4) | 860001 | 860002 | 0.003634 | [-0.012929, 0.020197] | 0.008000 | 0.020929 |
| p0.01 (12,0,2) 대 (7,0,2) | 860003 | 860004 | 0.007462 | [0.003884, 0.011039] | 0.008000 | 0.004116 |

각 N=131072, 실패 연결 0이다. 재판정 결과 J6 주 비교의 c6000 두 셀은 none -2.473480 [-2.549763, -2.397198], C1 -2.506470 [-2.615222, -2.397718] ms로 통과했다. 원래 J6 채택 규칙(전 30셀 조정 상한 0.5 이하, C1 한 셀 상한 0 미만)으로는 채택 조건을 만족한다. 활성 정책에는 넣지 않았다. 새 규칙 2.1(none 포함 v32 대비 비열등)로는 none 대 v32 B6 +6.364139 [5.121544, 7.606734] 실패 때문에 채택되지 않는다. 자세한 표는 `docs/J6_disposition.md` 덧붙임에 있다.

## 3. ACK와 패킷화 민감도 (C-E3)

`experiments/v33/world_ack_profile.py`, 결과 `g3/v33/V33FIX_ack_sensitivity_v1.json`. seed 860101, 점마다 4096연결, 모든 행동·ACK 크기·패킷화에 같은 seed와 연결 번호(공통 난수)를 썼다. 기본 세계는 그대로 두고 `preflight_ack_bytes`와 서버 패킷화만 덮어썼다.

ACK 범위의 출처를 확인했다. 28~54 B는 봉인 실측 범위가 아니다. `C:\dev\codex_handoff\v33\prompt\TASKS.md` 277행 J6 카드의 "A_pre ±13 B 오차" 가정이고, `docs/J6_preflight_budget.md` 9행이 단위 시험 범위로 썼다. 41 B는 CID 4 B 기준 손계산(헤더 20 + ACK 5 + 태그 16, `findings/audit-quicgo-source.md`)이다. 봉인 자료로 확인되는 것은 2 Mbps와 무제한의 서버 수신 바이트 중앙값 차이 42·44 B, 인증서 크기를 빼면 41·42 B다(`C:\dev\codex_handoff\v33\runs\J6_historical_preflight_v1.md`). 봉인 캡처에는 연결별 서버 데이터그램 크기 목록이 없어서(`docs/T1_certificate_result.md` 13행, `docs/J6_disposition.md` L5 자료 검토) 실제 데이터그램 크기는 넣지 못했다. 대신 패킷화 두 가지를 넣었다. 하나는 감사 audit-gen2-foundation (5)의 물리 적합(ML-KEM 1589.92 + 40.05n, X25519 477.98 + 40.21n)이고, 다른 하나는 봉인 H c12000 관측 S 14,058·14,114 B(`g3/v33/evidence/EVIDENCE.md` 15행, 표의 "6. H c12000" 행)에서 사전 ACK 41 B를 뺀 총량이다.

| 문맥 | 행동 (역할) | ACK 28~41 B 평균 HCT (ms) | ACK 42~54 B 평균 HCT (ms) |
|---|---|---:|---:|
| B12 c6000 p0.08 | (7,0,4) W1 기준, J6 margin0 | 125.182 | 246.835 |
| B12 c6000 p0.08 | (12,0,4) J6 margin30 | 125.190 | 125.190 |
| B12 c6000 p0.08 | (0,2,2) L1, v31, v32 | 128.590 | 128.590 |
| B12 c6000 p0.01 | (7,0,2) W1 기준 | 125.176 | 246.206 |
| B12 c6000 p0.01 | (12,0,2), (12,0,4) J6 margin30 | 125.184 | 125.184 |
| B12 c6000 p0.01 | (0,2,2) L1, v31, v32 | 127.275 | 127.275 |

W1 c6000 기준 행동 (7,0,4)·(7,0,2)는 ACK가 41 B에서 42 B로 1 B만 커져도 2-RTT가 된다(+121.65, +121.03 ms). J6 margin30 행동과 L1 행동은 28~54 B 전 구간에서 변하지 않는다. 그래서 ACK가 42 B 이상이면 목록 안 최선 행동이 J6 행동으로 바뀌고, L1 (0,2,2)와 최선의 차이는 p0.08에서 3.408에서 3.400 ms로, p0.01에서 2.099에서 2.091 ms로 거의 그대로다. J6와 L1의 차이(약 2.47 ms)는 이 범위의 ACK 크기에 민감하지 않고, 칼날인 것은 기준 행동과 margin0 진단이다. 물리 적합 패킷화에서도 절벽은 같은 42 B였다(마지막 데이터그램만 86 B에서 191 B로 바뀌고 개수 7개는 같다). 다만 아래에 적은 이유로 이 일치는 패킷화에 대한 견고성 증거가 아니다.

B12 c12000의 (0,3,1)과 (0,2,2)는 ACK 28~54 B와 세 패킷화(세계 기본 마지막 1134 B, 물리 적합 1231 B, 봉인 S 1217·1273 B, 모두 11개)에서 평균 HCT가 같았다(p0.08: 140.402, 149.167 ms; p0.01: 133.691, 133.640 ms). 봉인 c12000의 기록 n_need=12 오류는 세계의 서버 데이터그램 개수(11)로는 재현되지 않는다는 C-E3 지적과 맞는다. B4는 u=0이라 사전 ACK가 없고, (0,0,0) 103.116 대 (1,0,0) 53.116 ms의 1 B 경계는 두 패킷화에서 같다.

패킷화 쪽 일치를 읽는 법(2026-11-02 통합 정리, 1차 검증 지적). 세계의 서버 계수 기본값은 granular다(`experiments/v33/worldparams.json` 25행). granular 증폭 검사는 데이터그램을 보내기 전에 지금까지 보낸 바이트가 3×신용보다 작은지만 보고(`worldsim_m1.py` can_send, 동결 `worldsim.py`도 같다), 보낼 데이터그램의 크기는 검사에 넣지 않는다. 세 패킷화 프로필은 c6000에서 1280 B 6개, c12000에서 1280 B 10개로 꽉 찬 데이터그램 수가 같고 마지막 데이터그램 크기만 다르다(`V33FIX_ack_sensitivity_v1.json`의 server_first_flight_sizes). 그러므로 granular 모드에서 세 패킷화는 어느 경계도 움직일 수 없고, 위의 "세 패킷화에서 같다"는 구조상 정해진 결과다. 이 절이 보여 주는 것은 ACK 크기에 대한 민감도뿐이고, 패킷화에 대해서는 정보가 없다. ACK는 서버 송신 바이트에 직접 더해지므로 granular에서도 경계를 움직인다.

꽉 찬 데이터그램 수가 바뀌는 경우와 exact 계수(보낼 데이터그램까지 더해 3×신용 이하일 때만 보냄)는 따로 확인했다. 동결 `worldsim.py`(SHA-256 8f86bb52…e374), seed 860101, 2000연결, 사전 ACK 41 B, 서버 계수만 바꾼 평균 HCT(ms)다(직접 확인, `C:\dev\codex_handoff\v33\runs\v33fix\W\round2\pkt_probe_out.txt`, `pkt_probe_exact_l1_out.txt`).

| 문맥 | 서버 계수 | W1 기준 (7,0,4) 또는 (7,0,2) | J6 margin30 (12,0,4) 또는 (12,0,2) | L1 (0,2,2) |
|---|---|---:|---:|---:|
| B12 c6000 p0.08 | granular | 125.173 | 125.181 | 128.104 |
| B12 c6000 p0.08 | exact | 248.203 | 248.215 | 128.104 |
| B12 c6000 p0.01 | granular | 125.168 | 125.176 | 127.269 |
| B12 c6000 p0.01 | exact | 246.198 | 246.210 | 127.269 |

p0.08의 (7,0,4)·(12,0,4) 네 값은 1차 검증의 pkt_probe.py(같은 seed와 연결 수) 값과 같고, L1 열과 p0.01 행은 이번에 더했다. p0.08의 두 행동은 세계 기본 패킷화와 물리 적합 패킷화에서 두 계수 모두 같은 값이었다(pkt_probe_out.txt). 표의 granular 행이 위 ACK 표와 다른 것은 연결 수(2000 대 4096)가 달라서다. 같은 세계에서 4096연결로 다시 재면 ACK 표 값(125.182, 125.190, 128.590)이 나오고 앞 2000연결만 평균하면 이 표 값이 나온다(`round2\n4096_check_out.txt`). exact 계수에서는 W1 기준뿐 아니라 J6 margin30 행동도 2-RTT가 되고 L1 (0,2,2)는 그대로다. 같은 seed·연결로 잰 평균 차이로 J6가 L1보다 p0.08에서 +120.110 ms, p0.01에서 +118.942 ms 느리다(반올림 전 평균끼리 뺀 값 120.110404, 118.941588. 연결별 차이의 평균도 같다. 동결 worldsim.py, seed 860101, 2000연결, `C:\dev\codex_handoff\v33\runs\v33fix\D3\exact_diff_out.txt`). 이 자리에 처음 적은 +120.111·+118.941은 위 표의 반올림한 평균끼리 뺀 값이었다. 따라서 c6000에서 J6가 L1보다 약 2.47 ms 빠르다는 결과는 granular 계수 가정 위에서만 성립한다. 어느 계수가 실제 quic-go에 가까운지는 이 문서에서 판정하지 않는다(J8 범위). c12000에서 S를 14114 B(41 B를 빼지 않은 값)로 두어 데이터그램이 12개가 되게 해도 granular에서 (0,3,1) 140.221, (0,2,2) 147.951 ms로 14017·14073 B(11개)와 같았다. 패킷화나 계수에 대한 견고성을 주장하려면 꽉 찬 데이터그램 수가 바뀌는 프로필이나 exact 계수 팔을 결과 전에 등록해야 한다.

## 4. Initial 계수와 서버 PTO

Initial 계수(C-E5). `experiments/v33/initial_count_diag.py`, 결과 `g3/v33/V33FIX_world_diag_v1.json`의 sections.initial_count. W0 프로토콜의 seed 20261030, 사례당 100000연결로 W0 원래 정의의 결과를 7사례 모두 정확히 재현했다(직접 확인). 대안 정의는 quic-go 클라이언트가 첫 Handshake 패킷을 보낼 때 Initial 키를 버린다는 규칙(RFC 9001 4.9.1)을 따른다. 세계에서는 첫 응답 R이 그 시점이고 Initial ACK가 같이 실리므로, 그 전의 O·B와 첫 R은 세고 R 재전송은 세지 않는다. `validate_world.py`는 고치지 않았다.

| 사례 | 정의 | tail | failure_or_initial_retransmission | 관측 tail / f_or_rt |
|---|---|---:|---:|---|
| bigcert 15% 자동 (0,0,4) | W0 | 0.00000 | 0.02379 | 0.02812 / 0.00106 |
| bigcert 15% 자동 (0,0,4) | 키 폐기 | 0.02339 | 0.00040 | 0.02812 / 0.00106 |
| bigcert 15% 고정 (0,3,1) | W0 | 0.00000 | 0.07028 | 0.00756 / 0.05778 |
| bigcert 15% 고정 (0,3,1) | 키 폐기 | 0.00847 | 0.06181 | 0.00756 / 0.05778 |

자동 셀은 W0 정의로는 tail과 f_or_rt 둘 다 W0 허용차 0.02를 넘지만, 키 폐기 정의로는 모든 등급이 허용차 안이다. 옮겨진 2339연결의 HCT 중앙값은 283.88 ms(최소 283.37, 최대 615.30)다. 남는 차이(tail 0.0234 대 0.0281)는 관측 표준오차 범위 밖인지 따로 검정하지 않았다. 평균 HCT는 정의와 무관하다(122.687 ms). p18과 RTT200 사례는 거의 그대로다(rtt200_15의 Initial 5 비율 0.99983에서 0.99985).

서버 PTO 기준(E-J8-1). `experiments/v33/j8_pto_impact.py`, 결과 sections.j8_pto. worldsim.py 파일은 그대로 두고, 실행 중에 소스 문자열 세 곳을 바꾼 사본 모듈을 만들어 서버 PTO 시각을 "재무장 시각 + PTO"에서 "마지막 ack-eliciting 서버 data 송신 + PTO, 이미 지났으면 즉시"로 바꿨다(quic-go v0.61.0 getPTOTimeAndSpace, 번호 공간은 하나로 단순화). B7 문맥(0998e3f951c80c846cc2, 기준 (0,1,2))의 6개 행동을 seed 850001, N=131072로 평가했고, 원래 세계 표는 J6 행동 표를 소수 끝자리까지 재현했다(6/6).

| 행동 | W0 평균 (ms) | 수정 PTO 평균 (ms) | 짝 변화 (ms, ± 1 SE) | 기준과의 차이 W0 → 수정 (ms) |
|---|---:|---:|---:|---|
| (0,1,2) 기준 | 80.068 | 77.721 | -2.347 ± 0.055 | 0 → 0 |
| (0,1,3) | 80.062 | 77.715 | -2.347 | -0.0063 → -0.0059 |
| (0,2,2) | 84.345 | 81.867 | -2.477 | 4.2767 → 4.1465 |
| (0,2,1) | 84.514 | 82.038 | -2.476 | 4.4458 → 4.3171 |
| (0,0,0) | 132.204 | 131.610 | -0.595 | 52.1365 → 53.8888 |

131072연결 중 HCT가 바뀐 연결은 행동마다 약 2530~2566개, W0에서 서버 재전송이 있는 연결은 약 11320개다. 절대 HCT는 2.3~2.5 ms 내려가지만 행동 사이 차이는 0.13 ms 안에서만 움직였다. 이 표로 W1 B7의 15개 대조(J6 보고서의 14쌍과 v32 대 v31)를 다시 계산하면 판정이 하나도 바뀌지 않는다. v32 대 v31은 +1.103 [0.781, 1.425]에서 +1.069 [0.757, 1.382] ms로 그대로 실패, L1(=J6) none 대 v31은 +1.361 [1.038, 1.684]에서 +1.320 [1.006, 1.633] ms로 그대로 실패다. 연결 하나만 보면 차이가 크다. 첫 서버 data 데이터그램이 손실된 손실 0 문맥에서 W0는 449.47 ms, 수정 PTO는 268.16 ms다(`tests/test_v33fix_world.py`). J1 B7과 M1 hold 세계의 PTO 영향은 재지 않았다.

## 5. M1 후보 비용 모형과 보류 업링크

결과 sections.m1_cost_model. 수정한 M1 세계, seed 31, 행동마다 6000연결이다. 저장소 밖 스크립트로 계산했고 스크립트 원문과 SHA-256을 결과 JSON의 script_source에 넣었다. 스크립트 사본은 `C:\dev\codex_handoff\v33\runs\v33fix\W\C_round1\m1_cost_diag.py`이고, 그 원문은 script_source와 같다(통합 정리에서 확인). 다만 보존 파일은 줄바꿈이 CRLF(187줄, 10,427 B)라 파일 바이트의 SHA-256은 bd788a36377184e259b4231ebd30760d92f5b1ef9d7557dd854d63feda3d5bb4이고, CRLF를 LF로 바꾼 텍스트의 SHA-256이 결과 JSON의 script_sha256 d1ed9009d07a04f8e4c7165db162445c1c8c5d04511b95ad64397fc38716729d와 같다(`W\round2\m1_cost_diag.py`도 같은 바이트, 2026-11-02 묶음 D 확인, `C:\dev\codex_handoff\v33\runs\v33fix\D3\diag_sha_out.txt`). 모형 값은 M1 스냅숏(`g3/v33/policy_snapshots/M1_v1`)의 layout.evaluate다.

B2 p0.25(큰cert)에서 후보 모형과 세계의 순서가 뒤집힌다. 모형(hold, n_need 15)은 (0,4,0) 102.607 < (0,3,1) 110.921 ms로 순수 선행 행동을 고르고, 동결 실행의 hold_m1_c1_B2 고손실 구간에서 후보는 (0,4,0)을 56.66% 골랐다(9000연결, 평균 HCT 154.92 ms, 직접 재집계). 수정 세계에서는 (0,4,0) 154.767 ms, (0,3,1) 123.139 ms이고 짝 차이는 +31.63 ± 4.61 ms다. (0,4,0)의 tail은 691/6000연결, tail 평균 555.1 ms다. 세계는 trailing이 있을 때만 응답 XOR(Q, V)을 붙이므로 순수 선행 행동은 둘째 왕복 응답 손실에 그대로 노출된다. response_xor를 끄면 (0,3,1)이 180.431 ms로 (0,4,0)보다 나빠져 이 비대칭이 순서를 정한다는 것이 확인된다. 모형의 response_term은 둘째 왕복 무손실을 가정하므로 이 꼬리가 빠진다.

B7 none에서는 p 추정과 hold 모형이 겹친다. 동결 실행에서 M1 후보는 (0,3,1)을 75.38% 골랐고 결정 전 p_mean 중앙값은 0.2608이다(L1 none은 (0,2,2) 85.56%, p_mean 중앙값 0.2094). 수정 세계에서 (0,3,1) 90.682, (0,2,2) 85.372, (0,1,3) 82.159 ms이며 (0,3,1) - (0,2,2) = +5.310 ± 0.030 ms다. 모형은 p=0.02에서 (0,1,3) 67.544 < (0,2,2) 70.642 < (0,3,1) 75.799로 순서를 맞히지만, p=0.25에서는 (0,3,1) 75.630 < (0,2,2) 76.771로 뒤집는다. 따라서 이 실패는 세계 수정과 무관하게 남는다.

p=0.02의 손해(E-M1-4). 큰cert (0,3,1)에서 수정 세계의 hold - off는 +0.635 ± 0.102 ms다(83.086 대 82.451). 모형 차이는 +0.804 ms이고, 그중 패턴(선행 3개와 원본1 도착, 원본0 손실, 뒤 패리티 도착, 확률 0.01808)의 기여가 +0.900 ms다. 이 패턴에서 hold는 마지막 원본이 오는 21.092 ms에 결정을 열어 선행 패리티를 복구에 쓰고 결정 시 신용이 5222 B, off는 26.416 ms에 6553 B다. 같은 패턴을 세계에 강제하면(손실 0, 결정 지연 0) hold 128.812 ms, off 79.016 ms다. 비교 상한은 m1_fixed_checks의 첫 비행 기준 32.536 ms였고, 카드가 말한 패리티 데이터그램 하나는 2 Mbps에서 5.324 ms다. 손해는 기한이 아니라 결정 규칙의 비용이다.

보류 수신기 업링크(E-M1-3). 수정 세계에서 D20 고정값과 문맥 참값의 짝 차이(고정 - 참값)는 B12 c12000 p0.08 (0,4,0) +1.205 ± 0.054 ms, B10 (0,1,3) +0.428 ± 0.043 ms, B12 c6000 p0.08 (0,3,1) +0.111 ± 0.020 ms였고, 세 문맥의 (0,0,4)는 0이다. 기본값을 D20으로 바꾸면 업링크가 2 Mbps가 아닌 셀에서 보류의 이득이 이만큼 줄어든다.

## 6. 시험

새 시험 `tests/test_v33_zero_variance.py`(10개), `tests/test_v33fix_world.py`(12개), 고친 `tests/test_v33_m1_world.py`(1차 수정 때 11개, 통합 정리에서 token·retry 시험 2개를 더해 지금 13개, 기존 7개 중 test_fifo_credit_precedes_completing_original은 ready 뒤 뒤 패리티가 수신기를 거치지 않으므로 기대 목록에서 ('p',3)을 빼고 신용 1331 B를 따로 확인하도록 바꿨다)와 관련 기존 시험(test_v33_worldsim, test_v33_world_loss, test_v33_m1_mc, test_v33_m1_independent, test_v33_m1_fixed_independent, test_v33_m1_fixed_report, test_v33_oracle, test_v33_bench_report, test_v33_bench_metrics)을 함께 돌려 135개 통과, 하위 9709개 통과였다. 전체 pytest(`python -I -B -m pytest -p no:cacheprovider`, 2026-11-02 03시 무렵)는 1855 통과, 4 실패, 2 건너뜀, historical 32 제외, 하위 10936 통과였다. 실패 4개(test_adaptation_benchmark의 ablation 시험, test_p21_gencompare의 toy cell, test_v33_l3_candidate의 STATE_VERSION 4 기대, test_v33_policy_worker의 state_version 4 기대)는 모두 이 묶음이 건드리지 않은 시험이며, 같은 시간에 다른 묶음이 고치고 있는 padfec3(STATE_VERSION 11, 패리티 1452 B 상한)와 맞물린 기대값이다.

## 7. 스크래치 자료와 남은 일

1차 수정의 스크래치 스크립트와 출력은 저장소 밖 `C:\dev\codex_handoff\v33\runs\v33fix\W\C_round1\`에 복사해 두었다(원본과 SHA-256 대조, 목록은 `W\SHA256SUMS.txt`). lead0_scan.py(400조합 불변식 검사), lead0_scan_nobypass.py와 nobypass\(둘째 수정을 뺀 사본), late_case.py, m1_cost_diag.py(원문은 결과 JSON에도 있음), power_calc.py와 power_out.jsonl(V33FIX_bench_rules.md 2.4 표), j8_check.py, timing.py와 j6_dry64.json(Z1 등록 시각을 따질 때 쓴 자료), 첫 실행 결과(ack_run1.json, diag_run1.json)와 전체 pytest 출력이다. 1차 검증의 재현 스크립트와 출력(pkt_probe.py, lead0_verify.py, retry_check.py, power_verify.py, m1_spot.py 등)은 `W\C_verify\`, 통합 정리의 것은 `W\round2\`에 있다.

하지 않은 일과 이유는 이렇다. M1 120셀 재평가와 E15·E16은 후속 과제다. E-M1-5(복구 불가 비행의 보관 선행 패리티가 TTL에 폐기돼 신용이 되지 않는 점)는 이 묶음에 배정되지 않았고 세계 동작도 바꾸지 않았다. `docs/V33FIX_bench_rules.md` 3절의 Z1 목록(W1 B10 GE 121행동, c6000 114행동, M1 4셀, O2 4대조)은 적용 대기이며 방법만 적었다. 실측 보정 셀(C-E4)과 업링크 숨김 벤치 팔(C-E10)은 실측과 새 계획이 필요하다.

## 통합 정리 (2026-11-02)

1차 수정 뒤 검증(1차 보고 C-world의 VERIFY 절)과 수정자 not_done에서 넘어온 항목 8개를 처리했다. 1차 보고 원문은 `C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports\C-world.md`다. 이 작업은 03:50 무렵 시작해 04:11에 계정 사용 한도로 한 번 끊겼고, 06:27부터 이어서 했다. 이어서 할 때는 끊기기 전에 바꾼 파일과 결과를 하나씩 다시 돌려 확인했고, 그 과정에서 1차 판 문장 하나가 틀린 것을 찾아 고쳤다(아래 lead=0 스캔). 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\W\round2\`에 있고, 이어서 한 부분의 파일 이름은 r3_로 시작한다. 아래 숫자는 따로 적지 않으면 직접 실행해서 얻은 값이다.

retry 문맥의 lead=0 hold(검증 new_problems 1). 1절 다섯째에 적은 대로 `worldsim_m1.py` 결과 조립부 한 줄을 고쳐, retry 문맥에서는 buffered 모드도 첫 비행을 보낼 때 계산한 `first_flight_outcome` 값을 쓰게 했다. `tests/test_v33_m1_world.py`에 token·retry 문맥 시험 두 개를 더했다. 고치기 전 코드에서 새 시험이 실패하는지는 두 번 확인했다. 끊기기 전에는 작업 트리에서 직접 돌렸고(`round2\prefix_tests_summary.txt`), 이어서 할 때는 그 한 줄만 되돌린 사본(SHA-256이 1차 판 36e619e0…cfbadc와 같음, `round2\r3_prefix_pkg\`)에 새 시험을 돌렸다. 두 번 모두 test_lead_zero_hold_matches_off_with_token_and_retry의 하위 시험 6400개 중 3084개(전부 retry, token 0개)와 test_retry_initial_failure_follows_first_flight_pattern의 320개 중 285개가 실패했고, 지금 판에서는 모두 통과했다(`round2\r3_prefix_new_tests.txt`, `r3_fixed_new_tests.txt`). 1차 검증 스크립트 lead0_verify.py(문맥 11개, 변형 3개, seed 7·777·860123, δ 0·5·60, trailing 0~4, 조합마다 1000연결)를 지금 세계에 다시 돌리면 80만 쌍에서 event_count를 뺀 결과 필드, HCT, 서버 송신 목록, 서버 신용 사건, m1_stack을 뺀 사건 순서의 차이가 모두 0이다. 1차 검증 때는 retry 69432행이 달랐다. 끊기기 전 실행과 이어서 한 실행의 결과가 같다(`round2\lead0_verify_after_N1000.txt`, `r3_lead0_verify_N1000.txt`, 뒤 파일에는 실행 전후의 worldsim_m1.py 해시 383034eb…를 함께 적었다). 25조합은 전과 같이 off와 hold가 똑같은 ValueError를 낸다(w1406에 δ60을 더하면 1452 B를 넘음). retry_check.py(seed 777, 1500연결)에서 initial_failure는 지금 판 hold 115, off 115, HCT 차이 0이고, 되돌린 사본에서는 hold 1500, off 115다(`r3_retry_check_out.txt`, `r3_retry_check_prefix_out.txt`).

lead=0 400조합 스캔. 1차 수정의 400조합 × 3000연결 스캔은 출력이 파일로 남지 않았다. 보존 스크립트로 지금 세계에서 다시 돌려 차이 0을 확인했고, 둘째 수정을 뺀 보존 사본으로도 다시 돌렸다. 그 결과 1차 판 1절의 "서버 신용 바이트가 조합당 최대 52/3000연결(c12000 p0.25 seed50)"이 틀렸다는 것을 찾아 "142조합, 최대 66/3000연결(B10 p0.25 seed31)"로 고쳤다(1절, `r3_lead0_scan_out.txt`, `r3_lead0_scan_nobypass_out.txt`, `r3_count_nobypass_out.txt`). 둘째 수정이 없을 때 HCT와 송신 목록에는 차이가 없다는 1차 결론은 그대로다.

진단 결과 파일. 새 세계 해시는 1절에 적었다. 이 해시를 인용하는 `g3/v33/V33FIX_world_diag_v1.json`의 m1_cost_model 절은 끊기기 전에 같은 스크립트(원문 SHA-256 d1ed9009…729d, seed 31, 6000연결)로 다시 만들었다. 다시 만든 절은 시작 시각, 소요 시간, 세계 해시 말고는 1차 판과 같았고, initial_count·j8_pto 두 절은 손대지 않았다(`round2\compare_diag_out.txt`). 이어서 할 때 이 파일이 지금 코드로 끝까지 만들어졌는지 다시 확인했다. 보존 스크립트로 스크래치 사본에 절을 새로 만들고(06:31 실행) 시간 필드 두 개만 저장소 값으로 바꾸면 저장소 파일과 바이트 단위로 같았다(`r3_diag_compare_out.txt`, `r3_diag\diag_rerun.json`). 결과 파일 SHA-256은 fd90e955…0c0f에서 431804d7…a71f로 바뀌었고, 1차 판은 `round2\V33FIX_world_diag_v1.round1.json`으로 남겼다. 다른 결과 JSON(`V33FIX_J6_rejudge_v1.json`, `V33FIX_ack_sensitivity_v1.json`)은 동결 `worldsim.py`만 쓰므로 이 해시와 무관하다.

패킷화 민감도(검증 new_problems 2). 3절에 granular 계수에서는 마지막 데이터그램 크기만 바뀌어 세 패킷화가 경계를 움직일 수 없다는 사실을 적고, "세 패킷화에서 같다"를 견고성 증거로 읽지 않도록 고쳤다. 1차 검증의 pkt_probe.py를 그대로 다시 돌려 exact 계수 c6000 (7,0,4) 248.203, (12,0,4) 248.215 ms와 c12000 14114 B의 값을 재현했고, 같은 조건에서 L1 (0,2,2)와 p0.01 행을 더 쟀다. 이어서 할 때 pkt_probe.py, pkt_probe_exact_l1.py, n4096_check.py를 다시 돌렸고 출력이 끊기기 전 것과 바이트 단위로 같았다(`r3_pkt_probe_out.txt`, `r3_pkt_probe_exact_l1_out.txt`, `r3_n4096_check_out.txt`). exact 계수에서는 J6 margin30이 L1보다 약 120 ms 느리므로 J6의 c6000 이득은 granular 가정에 달려 있다. 이 단서는 `docs/J6_disposition.md` 끝 절에도 넣었다.

판정 규칙 문서(검증 new_problems 3, C-E1 partly). `docs/V33FIX_bench_rules.md` 2.4의 "B6 60 seed(31~90) 고정"을 도현님 확인 전의 제안으로 바꾸고 `g3/v33/bench_protocol.json`의 seeds가 31~50 그대로라고 적었다(직접 확인). 이어서 할 때 루프 묶음이 이 제안을 결정 항목 D51로 올린 것을 보고, 2.4에 D51을 가리키는 문장을 넣었다. 다음 후보 계획은 B6 seed 수의 근거로 2.4가 아니라 D51의 결정이나 기본값을 적는다. Z1 본문의 "예외 없이 적용"과 실제 적용 범위가 어긋나지 않도록 Z1 바로 뒤에 "1절 적용 상태" 절을 두고, 3절 표에 상태 열(네 곳 모두 적용 대기)을 넣었다. 머리 문단에는 등록 시점에 감사의 비짝 구간이 이미 공개돼 있었고 01:45 시간 측정 실행이 있었다는 1차 검증 지적을 출처와 함께 넣었고, 등록 시각을 결과 JSON의 문서 수정 시각과 같은 01:47(01:47:37)로 맞췄다. Z1 본문은 고치지 않았다. 편집 뒤에도 본문 해시 124952bb…c2e0이 `zero_variance.py`의 고정값과 같다(`check_rule` 통과).

`docs/M1_world_validity.md`(검증 new_problems 4·5). 정정 절의 "활성 L1 상태4"를 2026-11-02 작업 트리의 사실(v3.3.1-dev, 상태 판본 11, `padfec3/learn3.py`의 STATE_VERSION 11·POLICY_VERSION "v3.3.1-dev", `docs/V33FIX_policy.md`, 시험대 `-lead-hold` 기본 false)로 고쳤고 시점을 밝혔다. 맨 위에는 정정 줄을 넣었다. 정정 절의 lead=0 불변식 문장에 retry 차이와 이번 수정, 스캔 스크립트의 보존 경로, 80만 쌍 재확인 결과를 덧붙였다. "±"가 짝 차이의 1 SE라는 정의는 이 문서 머리, 4절 표 머리, M1 정정 절 머리에 적었다.

`docs/J6_disposition.md`. 결론 줄이 없어서 맨 위에 "2026-11-02 정정:" 줄로 넣었다. Z1 재판정으로 원래 J6 규칙은 만족(`g3/v33/V33FIX_J6_rejudge_v1.json`), 새 규칙 2.1로는 none 대 v32 B6 실패라 미채택, c1_seen True 경로에 J6 margin30을 넣을지는 후속이다. 이어서 할 때 루프에 이 후속이 과제 E41로 등록된 것을 확인하고(`C:\dev\codex_handoff\v33\state\EXTRA_TASKS.md`), 맨 위 줄과 끝 절의 "D45, 루프의 새 과제로 넘김"을 "E41, 범위 결정 D45"로 바꿨다. 끝 절의 "다른 묶음이 정책을 바꾸는 중"은 지금 사실로 바꾸고 exact 계수 단서를 넷째로 더했다.

증거 보존. 1차 수정 스크래치(`W\C_round1\`, 21개 파일)와 1차 검증 스크래치(`W\C_verify\`, 20개 파일)는 원본 폴더와 파일 목록과 SHA-256이 모두 같다(이어서 할 때 다시 대조). 통합 정리 자료(`W\round2\`)를 더해 전체 목록과 해시를 `C:\dev\codex_handoff\v33\runs\v33fix\W\SHA256SUMS.txt`에 적었다. 이 묶음의 문서와 결과 JSON에는 사용자 홈 아래 경로가 없다(검색 0건).

시험. 1차 묶음 관련 12개 파일(6절 목록, `tests/test_v33_m1_world.py`, `tests/test_v33fix_world.py`, `tests/test_v33_zero_variance.py` 포함)을 이어서 할 때 다시 돌려 137개 통과, 하위 16429개 통과였다(`round2\r3_related_tests.txt`, 끊기기 전 `related_tests.txt`와 같은 수). 1차의 135개, 하위 9709개에 새 시험 2개와 하위 6720개가 더해진 수다. 실행 전후 `git status --short --ignored`의 untracked·ignored 목록이 같았고 `__pycache__`와 `.pytest_cache`는 0개다. 동결 파일 확인: worldsim.py 8f86bb52…e374와 worldparams.json 57e9352c…b6ed는 bench_protocol·bench_baseline 기록과 같고, oracle.py 84e9feb6…592c, bench.py, bench_metrics.py, bench_oracles.py, bench_report.py는 bench_baseline 기록과 같다. 기록이 없는 oracle_m1.py, world_receiver_m1.py와 나머지 bench*.py는 `git diff HEAD`가 비어 있다(`round2\r3_frozen_check_out.txt`, 끊기기 전 `frozen_check_out.txt`와 같음). 전체 pytest는 다른 묶음과 섞이므로 돌리지 않았다.

하지 않은 일. 패킷화·계수 견고성 자체(꽉 찬 데이터그램 수가 바뀌는 프로필과 exact 계수 팔을 결과 전에 등록한 평가)는 하지 않았다. 사전 등록과 계획이 필요하다. Z1 적용 대기 네 곳은 재판정하지 않았다. J6를 v3.3.1-dev의 c1_seen True 경로에 넣는 평가는 루프 과제 E41의 일이라 하지 않았다. B6 seed 수는 도현님이 정할 일이다(D51).

묶음 D 정정(2026-11-02, 묶음 W 뒤 검증 `C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports2\VERDICTS.md`의 W-world new_problems 세 개). 첫째, 검증자 지적 "exact 계수의 J6-L1 차이 +120.111·+118.941은 반올림한 평균끼리 뺀 값이다". 동결 worldsim.py(8f86bb52…e374), seed 860101, 2000연결, 사전 ACK 41 B로 직접 다시 재니 exact 계수의 평균은 p0.08 J6 (12,0,4) 248.214857, L1 (0,2,2) 128.104452 ms, p0.01 J6 (12,0,2) 246.210362, L1 127.268774 ms였다. 반올림 전 평균의 차는 120.110404, 118.941588 ms이고 연결별 차이의 평균도 같다. 3절 문장을 +120.110, +118.942로 고치고 `docs/J6_disposition.md` 넷째 단서도 같이 고쳤다. 같은 값이 옮겨진 루프 과제 E41 카드(`C:\dev\codex_handoff\v33\state\EXTRA_TASKS.md`)는 루프 묶음 파일이라 고치지 않았다. 둘째, 검증자 지적 "보존 m1_cost_diag.py의 바이트 SHA-256이 결과 JSON의 script_sha256과 다르다(CRLF)". 5절에 파일 바이트 해시 bd788a36…5bb4와 LF로 바꾼 텍스트 해시 d1ed9009…729d(= script_sha256)를 함께 적었다. 셋째, 검증자 지적 "'g3/v33/evidence/EVIDENCE.md 6행' 참조가 실제 행과 다르다". 3절을 15행(표의 "6. H c12000" 행)으로 고쳤다. 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\D3\`의 `exact_diff.py`, `exact_diff_out.txt`, `diag_sha.py`, `diag_sha_out.txt`다. 실행 전후 gen33 `git status --short --ignored`가 같았다.
