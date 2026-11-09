# V33FIX 활성 정책 수정 (v3.3.1-dev, 상태 판본 11)

작성 2026-11-02. 묶음 A-py. 바꾼 파일은 `padfec3/learn3.py`, `padfec3/decide3.py`, `tests/test_padfec3_arrivals.py`, `tests/test_padfec3_dev_regressions.py`, `tests/test_padfec3_followup.py`, `tests/test_padfec3_learn.py`, 새 파일 `tests/test_v33fix_policy.py`, `experiments/v33/v33fix_replay.py`, `g3/v33/V33FIX_replay_v1.json`, 이 문서다. `padfec3/layout.py`와 `padfec/*`(gen-2 `decide_v2` 포함)는 건드리지 않았다.

## 1. 설계

목적지 상태에 끈끈한 표지 `c1_seen`을 둔다. 그 목적지에서 `arrivals.src`가 `c1` 또는 `ack`인 관측이 한 번이라도 들어오면 True가 되고 다시 False가 되지 않는다. 잘린(`trunc`) 회신이나 `sent=0` 회신도 서버가 C1을 보낸다는 증거라서 표지를 켠다.

`c1_seen`이 False인 목적지(C1 회신이 없는 표준 서버, 기본 배포 경로)는 관측과 결정이 v3.2-dev(기준선 90859b973의 `padfec3`)와 같다. 1비트 이진 우도(`likelihood`, EPS 0.01), 명목 2-RTT·shield·guard 건너뛰기, guard 가산 벌점, 16번째 재평가, 64결정 뒤 경보 해제가 모두 그대로다.

`c1_seen`이 True인 목적지는 관측이 L1과 같다. 완전한 회신은 datagram 우도, 회신이 빠지거나 잘린 연결은 HCT 3등급 우도(CLASS_EPS 1e-3), 문맥이 없으면 예측만 한다. 결정은 L3 record_only 진단 팔(`g3/v33/policy_snapshots/L3_record_only_v1`)과 같다. guard 가산 벌점이 없고, `arrival_streak > 0`인 동안 16번째 재평가를 하지 않으며, β 반응이 없다. guard 잔차 창(`g_resid`, `g_common`)은 기록만 하고 경보는 세우지 않는다.

`c1_seen`이 켜지는 관측에서 그때까지의 guard 경보(`g_alarm`)를 모두 지우고 `stats.alarm_cleared`에 그 수를 더한다. 그 관측 자체는 c1 규칙으로 처리한다. 그래서 c1 목적지에는 경보가 남지 않는다.

v3 후보의 parity datagram 상한을 1452 B(`policy.QUICGO_MAX_IPS`)로 내렸다. `decide3.UDP_MAX`의 값을 `quantum.TYPICAL_MTU - 28`(1472)에서 `policy.QUICGO_MAX_IPS`(1452)로 바꿨다. 이 상수를 쓰는 곳은 `candidates3`의 m>0 후보 거르기, `experiments/v33/uplink_reference.py:114`의 후보 크기 검사, `g3/policy3_reference_gen.py:342`가 Go 참조에 쓰는 `udp_max` 상수 셋이다. 셋 다 "parity datagram이 넘으면 안 되는 크기"라는 뜻이라 새 상수를 따로 만들지 않고 값을 바꿨다. gen-2 경로(`padfec/policy.py decide_v2`)는 그대로라 1457 B parity 후보를 계속 만든다.

### 상태와 결정 규칙의 순서

상태 JSON(v 11)은 v4 필드에 `"c1_seen": bool`, `"arrival_streak": int`가 더해진다(`g_alarm` 다음, `stats` 앞). `stats`에는 none 경로의 1비트 갱신 수 `binary`가 더해진다. `from_json`은 판본이 11이 아니면 `state version mismatch`로 거부하고, `c1_seen`이 bool이 아니거나 `arrival_streak`가 0..8 밖이거나, `c1_seen=False`인데 `arrival_streak>0`이거나, `c1_seen=True`인데 `g_alarm`이 비어 있지 않으면 거부한다. 두 필드가 없으면 다른 필드와 같이 KeyError가 난다.

`observe3` 순서:

1. `normalize_arrivals`로 엄격 검증, 전송값·`srv_bytes`·HCT·`j_pred`·패킷 수 검증(이전과 같음), `ctx = context(...)`.
2. `src`가 c1/ack이고 `c1_seen`이 False면 `enter_c1`: `c1_seen=True`, `alarm_cleared += len(g_alarm)`, `g_alarm={}`.
3. `c1_seen`이면 `_observe_c1`, 아니면 `_observe_none`.
   - `_observe_none`은 v3.2 `_observe3` 본문 그대로다. 기준선과 y, 잔차, `obs`/`fail`, `guard_observe`(기록 뒤 경보 검사), skip(shield/nominal2, 그다음 경보면 guard), y 없음이면 `no_base`, 문맥 없음이면 `no_ctx`, skip이면 그 사유, 아니면 `likelihood(ctx, action, y)`로 갱신하고 `upd`, `events`(y=1일 때)를 센다. 갱신이 없으면 `predict_step`. 종류는 `binary` 또는 `predict_only`, `arr_none`을 센다.
   - `_observe_c1`은 L3 record 팔의 관측과 같다. 등급과 경계, 기준선과 y, 잔차, `obs`/`fail`, `guard_record`(경보 검사 없음), legacy skip 진단, `events`(y=1이면 항상), `arr_<src>`, `arr_trunc`, `arr_empty`, 등급 수, 사유(`source_none`/`truncated`/`empty`/없음)에 따라 datagram, 범주, 예측만. 끝에 `arrival_streak = min(8, arrival_streak+1)`(쓸 수 있는 회신) 또는 0.
4. 공통 끝: `stats[kind] += 1`, `predict += 1`, 성공이면 `k_hist`, `hct`, `hct_seq`, `seq`, (y≠1이면) `S_hist`.

`decide3` 순서:

1. 전송값·`later`·후보 선택지 검증, 그다음 `c1_seen`(bool), `arrival_streak`(0..8, c1 아닐 때 0), c1이면 `g_alarm` 비어 있음을 검사한다.
2. 명시 행동 검증, `b = guard_common`.
3. c1이면 모든 `g_resid` 키의 `guard_excess`를 유한성만 검사하고 벌점은 없다. 아니면 v3.2처럼 만료되지 않은 경보마다 벌점을 만든다.
4. `reeval_open = (not c1) or arrival_streak == 0`.
5. cold/k_range/no_rtt면 B0, 아니면 `decide_core`(후보는 1452 B 상한 적용). `reeval_cond and reeval_open`이고 `(n_reeval+1) % 16 == 0`이면 alt로 바꾼다.
6. c1이면 `cleared=[]`, 아니면 `guard_refresh`.
7. `n_dec += 1`, `reeval_cond and reeval_open`이면 `n_reeval += 1`, 재평가면 `stats.reeval += 1`.
8. 결과에 `policy_path`, `c1_seen`, `arrival_streak`, `reeval_feedback_suppressed`(= not `reeval_open`)를 더한다.

`calibrated_cost(beta=0)`은 L3 스냅숏 `learn3.py`에서 `if beta == 0.0: return base_cost`로 기대 비용 객체를 그대로 돌려준다. `tests/test_v33fix_policy.py::test_calibrated_cost_with_zero_beta_is_the_expected_cost`가 모든 후보에서 `is` 동일성으로 확인한다. 그래서 CUSUM 감시(`monitor3`)는 옮기지 않았다. 그 결과 c1 경로의 `info["raised"]`, `info["alarmed"]`, `stats.alarm_raised`는 L3 record와 다르다(L3는 CUSUM 방향을 여기에 적었다). 셋 다 결정에 쓰이지 않는다.

## 2. 근거 (감사 원문)

감사 원문 위치: `C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01`(세션 스크래치의 원본을 옮긴 보존 사본).

- B-E1(B-active-algorithm.md): "활성 정책의 기본 경로(none, C1 없음)가 v3.2-dev보다 나빠졌다". none 대 v32 B6 +6.372 [5.166, 7.579] ms가 확정 실패이고, FIX는 "none 경로는 v3.2의 이진 우도(또는 기준선 상대 판정)로 되돌리고 categorical은 C1이 확인된 목적지에만 쓰"라는 것이다. 이번 수정이 이 처방 그대로다.
- C-E7(C-world-and-stats.md): FIX의 "L1을 'C1 서버 전용 조건부 채택'으로 표기하고 기본 경로에는 v32 동작을 유지한다"를 구현했다.
- B-E2(B-active-algorithm.md)와 H-05(H-coverage.md): 같은 none 경로를 L1에서는 진단으로, 후속 후보에서는 관문으로 다룬 비대칭이다. none 경로가 v3.2와 비트 단위로 같아졌으므로 none 대 v32 비교는 구성상 차이 0이다(아래 재생 결과). 후속 후보의 none 기준선을 v32로 둘지는 판정 규칙 문제라 이 묶음에서 바꾸지 않았다.
- D-E3(D-rejected-learning.md): "10-29 처방 (1)의 감시층 가산 벌점과 16번째 재평가가 여전히 활성이다". FIX는 "β 반응을 뺀 record 팔(벌점 제거, arrivals가 있을 때 재평가 제거)"이다. c1 목적지에서 이것을 적용했다. none 목적지에는 v3.2와 같게 두라는 설계라 벌점과 재평가가 남는다.
- D-E4(D-rejected-learning.md): "활성 정책이 1452 B를 넘는 parity 후보를 계속 만든다". FIX의 "1452 B 상한(UDP_MAX와 p3UDPMax)을 성능 중립적인 와이어 계약 정정으로 분리해 먼저 적용"을 Python 쪽에 적용했다. Go `p3UDPMax`는 다음 묶음 몫이다.
- B-E3(B-active-algorithm.md): C1 B6 비열등 통과가 사후 정밀화에 기댄다는 지적이다. 이 수정으로 고쳐지지 않는다. c1 경로의 B6는 아래처럼 L1_c1 대비로도 미확정이다.

c1 경로를 L3 record 팔로 고른 근거(문서에서 읽은 값, `C:\dev\codex_handoff\v33\runs\L3_findings_v1.md`): guard_c1 대 l1_c1 B1 −1.133353 [−1.448570, −0.818136], B5 −0.484054 [−0.583110, −0.384998], B6 +0.023892(MC 폭 0.142519, 조정 경계 [−0.493825, 0.541609], 미확정), 나머지 12셀 0. record_c1 대 guard_c1 B1 +0.000955, B2 −0.202831 [−0.252068, −0.153593], 나머지 13셀 0. 두 행의 평균을 더하면 record_c1 대 l1_c1은 B1 −1.132398, B2 −0.202831, B5 −0.484054, B6 +0.023892 ms다(같은 seed의 기대 비용 차이라 평균은 더할 수 있다. 구간은 더할 수 없어 적지 않는다). record_c1의 B1 절대 기대 후회는 0.093952 [0.060876, 0.127028]로 0.1 목표 미확정이다.

## 3. 동등성 검증 (직접 실행한 값)

### (a) none 경로 대 v3.2, (b) c1 경로 대 L3 record_only

참조 정책은 저장소 안의 두 사본이다. v3.2는 `g3/v33/fixtures/S5_test_inputs_v1/policies/v32`(90859b973의 `afec`, `padfec`, `padfec3`와 파일 단위로 같음을 확인했다), L3 record는 `g3/v33/policy_snapshots/L3_record_only_v1`이다. 두 참조 모두 `decide3.UDP_MAX`만 1452로 바꿔 불러온다. 원자료를 만든 정책 소스 지문(W1_raw_v32 manifest의 v32 19파일, L3_raw_v1_41 manifest의 20파일)과도 sha256이 모두 같다.

무작위 열 생성기는 `tests/test_v33fix_policy.py`에 있다. 장면(W 1200/1280/1350/1406, k 1~3, u 0~10 Mbps, RTT 10~250 ms, 인증서 2955~16000 B, 손실 0~0.3)을 고르고, 진행 중에 손실·u·인증서를 바꾸며, 행동별 HCT 편향(0.8 RTT)으로 guard 경보를 유발하고, 실패·RTT 없음·k 이상값·srv_bytes 없음/0을 섞는다. c1 쪽은 회신률(0.95/0.7/0.3)에 따라 완전한 c1·ack 회신, 회신 없음(None, src none), 잘린 회신, sent=0 회신을 섞는다. 매 단계 결정 사전의 모든 키(참조 쪽 키, `policy_version`과 L3 감시 키 제외), 관측 정보, 직렬화 상태를 비트 단위로 비교한다.

| 검사 | 단계 | 불일치 | 실행한 분기 |
|---|---:|---:|---|
| none 대 v3.2, seed 1001 | 10,000 | 0 | reeval 36, no_rtt 421, skip nominal2 1020·shield 311·guard 208, 경보 34, 양의 벌점 116, 실패 492 |
| none 대 v3.2, seed 1002 | 10,000 | 0 | reeval 55, skip nominal2 1707·shield 193·guard 143, 경보 46 |
| c1 대 L3 record, seed 2001 | 10,000 | 0 | reeval 27, 재평가 보류 534, datagram 6029·범주 3810·예측만 161, streak 최대 8 |
| c1 대 L3 record, seed 2002 | 10,000 | 0 | reeval 14, 재평가 보류 471, datagram 6654·범주 3278·예측만 68 |
| none→c1 전환, seed 1~40 | 전환 전 260 + 전환 뒤 300씩 | 0 | 16 seed가 전환 순간 경보 보유(합 28개), 전환 뒤 12,000단계 reeval 9 |

전환 검사는 전환 전에는 v3.2와 비교하고, 전환 관측에서 `c1_seen`, 경보 삭제, `alarm_cleared`, datagram 우도 갱신을 확인한 뒤, 그 순간의 새 상태로 L3 record 상태를 만들어 같이 진행시키며 비교한다. 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\P\first_round\A-py\eq_out\`에 있다(묶음 A-py가 세션 스크래치에 남긴 폴더를 sha256 대조 뒤 옮긴 사본, 목록은 `runs\v33fix\P\SHA256SUMS.txt`). pytest에는 같은 함수의 축약판(none 800단계, c1 800단계, 전환 seed 10)이 들어 있다. 재현 예:

```
python -I -B -c "import sys; sys.dont_write_bytecode=True; sys.path[:0]=['.', 'tests']; import test_v33fix_policy as T; c=T.run_none_equivalence(T.load_reference(T.V32_ROOT), 10000, 1001); print(len(c['mismatch']), c['why'])"
```

### (c) 원자료 재생

도구 `experiments/v33/v33fix_replay.py`, 결과 `g3/v33/V33FIX_replay_v1.json`. 원자료는 `C:\dev\codex_handoff\v33\runs`의 `W1_raw_v32\v32\full`(15셀 × seed 31~50, v3.2 궤적)과, overlay가 `L3_record_only_v1.json`이고 관측 모드가 c1인 L3 원자료 15개 폴더(L3_raw_v1_07, 08, 09, 41~51, 87)다. 궤적 sha256을 seed 요약과 대조한 뒤 연결마다 기록된 `decide` 입력(rtt_ms)으로 결정하고, 기록된 `observe` 입력(행동, HCT, 성공, k_obs, srv_bytes, rtt_ms, j_pred, c1이면 first_flight_evidence)으로 관측한다. 결정은 행동과 why로 비교하고, 상태 동기 확인으로 `ej`와 `p_mean`의 비트 일치도 센다. 불일치가 있는 seed는 `UDP_MAX`를 1472로 넓혀 다시 재생해 1452 상한 탓인지 가린다. 실행 시간 102.5초(10 프로세스).

| 모드 | 연결 | 결정 일치 | 불일치 | ej·p_mean 비트 일치 | 후보 수 변화 | 최종 상태 일치 seed |
|---|---:|---:|---:|---:|---:|---:|
| none (W1_raw_v32 재생) | 411,000 | 411,000 | 0 | 411,000 | 0 | 300/300 |
| c1 (L3 record_c1 재생) | 411,000 | 410,997 | 3 | 408,304 | 0 | 298/300 |

1452 B 상한 때문에 생긴 불일치는 0이고 후보 수가 바뀐 결정도 0이다. 이유는 W=1280 자체가 아니라 재생한 S_hat_pre가 초과 후보 띠 밖이라는 데 있다. 상한이 1472 B인 원래 v3.2-dev는 W=1280(`g3/v33/bench_protocol.json`)에서도 k=1 S 21,175~22,410 B, k=2 S 12,635~13,870 B·21,300~22,535 B, k=4 S 25,265~26,500 B·33,935~35,165 B에서 모형 parity가 1452 B를 넘는 후보를 낸다(S 1,500~60,000 B, 5 B 격자, k=3은 없음). W1 15셀에서 S_hat_pre가 있는 383,720행은 모두 이 띠 밖이고 B9에는 S_hat_pre가 없다. 가장 가까운 값은 B12_c12000의 13,975 B로 k=2 띠 끝 13,870 B보다 105 B 위다. 따라서 none 경로가 원래 v3.2-dev와 같다는 말은 이 15셀 재생의 결과이며 W=1280 전체로 넓힐 수 없다. S 40 B 격자 16,344문맥(p 4값, u 3값, RTT 3값)에서 띠 안 5,580문맥은 모두 후보 수가 달랐고 그중 2,418문맥은 행동도 달랐다. 띠 밖 10,764문맥은 같았고, `UDP_MAX`를 1452로 맞춘 v3.2-dev는 16,344문맥 모두 같았다.

c1 불일치 3건은 모두 B11(RTT 200 ms)이다. seed 42와 50은 첫 c1 회신이 각각 236번째, 205번째 연결에야 왔다(나머지 298 seed는 0번째, B7 32·37·48과 B10 42·50은 1번째). 설계상 그 전까지는 v3.2 규칙(이진 우도와 shield/nominal2 건너뛰기)으로 학습하고 L3 record는 범주 우도로 학습했으므로, 두 seed의 사후분포는 3번째 연결(인덱스 2)부터 갈라진다. 그 결과 인덱스 187에서 두 seed 모두 (0,1,3) 대신 (0,2,2)를 골랐고(기록 ej 226.4798, 재생 ej 226.5099), seed 42는 c1 전환 뒤인 인덱스 1242에서도 같은 쌍으로 한 번 갈렸다. 이 1건도 전환 전에 갈라진 사후분포가 이어진 결과다(그 단계의 p_mean이 비트 단위로 다르다). 최종 상태 차이도 이 두 seed의 `post`, `w`와 갱신 종류 통계뿐이다. 이것은 설계 규칙 2의 의도된 결과라 고치지 않았다. 전환 뒤의 c1 규칙 자체는 위 전환 검사(전환 순간 상태에서 L3 record와 12,000단계 일치)로 확인했다.

## 4. 시험

새 파일 `tests/test_v33fix_policy.py`(27개): none 대 v3.2 축약판, c1 대 L3 record 축약판, `calibrated_cost(beta=0)` 동일성, none→c1 전환, c1 뒤 none 증거가 와도 c1 규칙 유지, `arrival_streak>0`일 때 재평가 보류, c1 결정에서 guard 잔차 무시, 1452 상한(6 문맥, 넓힌 상한과의 집합 차가 정확히 초과 후보), 판본 11 왕복과 판본 1~10 거부, `c1_seen`·`arrival_streak` 잘못된 값 9종과 누락 2종 거부, 살아 있는 상태의 모순된 표지에서 `decide3` 거부.

기존 시험에서 바꾼 곳과 이유:

- `tests/test_padfec3_learn.py`, `tests/test_padfec3_dev_regressions.py`: L1이 "회신 없는 관측 = 범주 우도"로 바꿔 놓은 none 경로 기대를 v3.2 판(90859b973의 같은 시험 본문)으로 되돌렸다. 새 설계에서 회신 없는 목적지는 v3.2와 같아야 하기 때문이다. L1의 범주 우도 기대는 버리지 않고 `C1MissingReplyTests` 클래스로 옮겨 `c1_seen=True` 목적지에서 회신이 빠진 경우의 시험으로 남겼다(learn 3개, dev_regressions 3개, guard 경우는 c1 목적지에 경보가 없으므로 "기록만 하고 경보 없음" 시험으로 바꿨다). 판본 기대는 3/4에서 11로, 거부 판본은 이전 판본 전부로, 정책 이름은 v3.3.1-dev로 바꿨다.
- `tests/test_padfec3_learn.py::test_candidates_contain_gen2_legacy_actions`: gen-2 후보 중 parity가 1452 B를 넘는 (126,1,2) 같은 행동은 v3 후보에 없어야 한다로 바꿨다. 나머지 gen-2 행동은 여전히 v3 후보에 있어야 한다.
- `tests/test_padfec3_arrivals.py`: guard 경보가 있던 목적지에 완전한 c1 회신이 오면 경보가 지워지므로 legacy skip 기대를 None으로 바꾸고 `alarm_cleared`를 확인한다. 회신 없음/잘림 범주 우도 시험은 `c1_seen=True` 목적지로 한정했다. C1을 본 적 없는 목적지는 v3.2 이진 우도와 skip을 쓴다는 시험 8개를 더했다. 판본 시험은 11로 바꿨다.
- `tests/test_padfec3_followup.py`: 늦은 오류 원자성 시험을 none 경로(`likelihood` 실패)와 c1 경로(`class_likelihood` 실패) 둘 다에서 돌리게 했다.

pytest(`PYTHONDONTWRITEBYTECODE=1 python -I -B -m pytest -p no:cacheprovider`, gen33 전체)는 §6에 적었다.

## 5. 남은 한계

- c1 경로의 이득은 비표준이고 인증되지 않은 C1 회신에 기댄다. W1 원자료의 c1 관측 모형은 회신 비용을 HCT, 증폭 예산, 다음 연결 간격에 넣지 않는 수동 관측이다(감사 B 놓친 점 3, D14). 실측(T7)은 없다.
- B10 버스트 손실에서 c1의 p 과소추정(B-E4, 꼬리 p 편향 −0.0204, v32 대비 +0.170 [0.136, 0.204] ms, 감사 B 값)은 그대로다. datagram 우도가 iid라서다.
- B1 절대 목표 0.1 ms는 record_c1 0.093952 [0.060876, 0.127028]로 미확정이라 달성했다고 말할 수 없다. B6는 L1_c1 대비 미확정(조정 상한 0.541609)이다.
- none 경로는 v3.2와 같으므로 v3.2의 결함(무손실 B3_u0·B4에서 보호 행동 고착, 감사 B 놓친 점 1)도 그대로다. W1 15셀 재생에서 none 경로 결정은 v3.2와 모두 같았으므로, C1이 없는 서버에서 v3.3.1-dev는 이 세계에서 v3.2-dev와 같은 결과를 낸다. W1 밖 문맥(W 1406처럼 기본 W가 큰 문맥이나 W=1280의 위 S 띠)에서는 1452 B 상한 때문에 v3.2와 후보가 다르다. 그 차이의 크기는 바로 아래 항목에 적었다.
- 1452 B 상한 때문에 W와 k가 크면 parity 후보가 하나도 남지 않는다. 모형의 parity datagram 크기는 W_eff+39+6k B(`padfec/policy.py`의 `PARITY_OVERHEAD_BASE` 39, `PARITY_OVERHEAD_PER_K` 6)이고 W_eff=W+δ다. `candidates3`는 m>0 후보 중 이 모형 크기가 1452 B를 넘는 것을 버리므로, parity 후보는 W ≤ 1413 − 6k에서만 있다. 실제 wire 크기는 아래 표와 설명으로 구분한다. `decide3.candidates3`로 W 1200~1452(1 B 간격), k 1~4, S 2000·9000·16000·30000 B, `c_pkt` 기본값을 모두 돌려 직접 확인한 상한은 k=1 W ≤ 1407, k=2 W ≤ 1401, k=3 W ≤ 1395, k=4 W ≤ 1389이다. 상한 아래에서 parity 후보가 빠진 W는 없었고, 네 S 값에서 결과가 같았다. 상한 위에서는 m=0 후보만 남는다. W 1406이면 k=2와 k=4에서 후보가 B0 (0,0,0) 하나, k=3에서 B0과 padding 17 B인 (17,0,0) 둘이다. W 1400이면 k=2는 parity 후보 14개가 있지만 k=3은 (0,0,0)·(23,0,0), k=4는 (0,0,0)뿐이다. 그래서 W 1406·k≥2와 W 1400·k≥3에서 v3.3.1-dev는 parity를 쓰지 않는다. 같은 계산을 HEAD(v3.3-dev, 상한 1472 B) 정책으로 돌리면 상한은 1427·1421·1415·1409였다. `docs/J6_preflight_budget.md`는 실측 문맥을 "W1280·1281·1406에서 k2"로 적고 있으므로, W 1406·k=2 실측에서는 이 정책이 PAD-FEC의 parity를 내지 않는다. W1 15셀은 모두 W 1280이라 이 소멸이 벤치에 나타나지 않는다. 계산 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\P\scripts\parity_w_limit.py`, `parity_w_limit_v2.json`(HEAD 정책판은 `parity_w_limit_old.py`, `parity_w_limit_old.json`)이다.

parity의 직렬화 길이는 `W_eff+22+D+S_c+6k` B다. 여기서 `W_eff=W+δ`는 symbol 길이, D와 S_c는 DCID와 SCID 길이다. 실제 first Initial의 D=8~20, S_c=4 조건에서는 `W_eff+(34~46)+6k` B이고, 모형은 고정 오버헤드 39 B를 쓴다. 아래 wire 안전 상한은 이 CID 조건에서 1452 B를 넘지 않는 W_eff의 상한이다. δ=0이면 W의 상한과 같고, combo 행동은 δ도 포함해 비교한다.

| k | 모형 상한 W_eff (B) | wire 안전 상한 W_eff (B) |
|---|---:|---:|
| 1 | 1407 | 1400 |
| 2 | 1401 | 1394 |
| 3 | 1395 | 1388 |
| 4 | 1389 | 1382 |

두 상한 사이의 후보는 DCID 길이에 따라 1452 B를 넘을 수 있다. `W=1280`, `c_pkt=41.983`, `S=1500~60000` B를 5 B 간격으로 계산했을 때 k=1·2에는 wire 최악 크기가 1452 B를 넘는 후보가 없었다. k=3은 S=25140~26375 B(δ=114, W_eff=1394), k=4는 S=16600~17835 B(δ=107, W_eff=1387) 격자에서 초과 후보가 있었다. 이 범위는 5 B 격자 결과이며 정확한 정수 경계나 실제 선택 결과를 뜻하지 않는다. 서버가 1452 B로 읽는 경로(`-profile sealed31`, 동결 서버)에서는 잘린 parity를 복구에 쓸 수 없다. 기본 프로필 서버는 1472 B까지 읽어 parity 전체를 복구에 쓰고 quic-go에는 앞 1452 B만 넘기므로 credit은 같다. 계산 스크립트와 출력은 `C:/dev/codex_handoff/final/runs/F12_numbers.py`, `F12_numbers.json`이다.

`fec_parse_fail`은 PFEC magic을 식별했지만 `parseFecBlock`이 실패한 수신 수다. 정상 parity와 off 모드는 증가시키지 않는다. 이 계수에는 잘림 외의 malformed PFEC도 포함되며, magic까지 잘리면 식별하지 못한다. 네트워크 잘림 원인을 이 계수만으로 판정할 수 없다.

auto3 client는 명시한 `-ips`가 1407을 넘으면 `auto3: no parity candidate above W 1407`을 stderr에 한 번 출력하고 계속 실행한다. W가 1390~1407이면 `auto3: no parity candidate for k>=K above W C`를 stderr에 낸다. K는 parity가 사라지는 가장 작은 k이고 C는 그 k의 모형 상한이다. `-expect-k`가 K보다 작으면 내지 않는다. 각 결정 행의 `policy_parity_possible`은 k를 알 때 기본 W가 해당 모형 상한 이하인지 나타내고, cold 행에서는 null이다. 선택한 행동의 parity 사용 여부와 wire 안전 여부는 이 표지와 별도로 확인한다. D50의 측정 기본값은 모든 팔 W=1280이며 `-ips`를 주지 않는다(F31의 Initial 확대 팔 예외는 유지한다).

- 명시 행동 경로(`decide3`의 `actions=` 인자, `explicit_candidates`)는 1452 B 상한도 `max_ips`도 적용하지 않는다. v3.2부터 같은 동작이고 이번에 코드를 바꾸지 않았다. 지금 이 경로로 상한 밖 행동이 들어갈 수 있는 곳은 `experiments/replay_g3.py`의 오프라인 분석(240행 v3.1 기록 팔 `LEGACY` 네 행동의 재생, 483행 기록 행동의 예측 비용)이다. `experiments/adaptation_benchmark.py`(239·253행)는 `candidates3`가 만든 후보만 넘기므로 상한이 이미 걸려 있고, `experiments/v33/uplink_reference.py`는 `explicit_candidates`를 쓰지만 바로 뒤(113~115행)에서 `MAX_IPS`와 `UDP_MAX`를 따로 검사해 넘는 후보를 거부한다. `experiments/v33/current_k_candidate.py`는 호출자가 준 actions를 그대로 넘긴다(지금 호출하는 `current_k_replay.py`는 actions를 주지 않는다). 오프라인 분석에서 1452 B를 넘는 행동을 표시하거나 거를지는 정하지 않았다.
- 첫 C1 회신이 늦게 오는 목적지(B11 seed 42·50)는 그 전까지 v3.2 규칙으로 배운 사후분포를 안고 c1 규칙으로 넘어간다.
- 이번 재생은 결정 일치를 센 것이고 성능을 다시 잰 것이 아니다. W1 15셀에서 새 정책의 none 성능은 v3.2와, c1 성능은 L3 record_c1과 같다는 결론은 재생 일치(none 411,000/411,000, c1 410,997/411,000)에서 나온다. B11 두 seed의 차이 3결정이 비용에 주는 영향은 계산하지 않았다.

## 6. 전체 pytest와 못 한 것

다른 묶음이 같은 작업 트리를 동시에 고치고 있어서 숫자는 실행 시점(2026-11-02 02:20 무렵)의 작업 트리 기준이다. 아래 실패 4개는 그 뒤 묶음 P가 고쳤다(이 문서 끝 "통합 정리" 절).

| 범위 | 결과 |
|---|---|
| 수정 전 기준(작업 트리 깨끗, HEAD d67717d9b) | 1792 passed, 2 skipped, 32 deselected |
| 맡은 시험 7파일(`test_padfec3_*` 6개 + `test_v33fix_policy.py`) | 180 passed, 실패 0 |
| 전체 | 1855 passed, 4 failed, 2 skipped, 32 deselected |

실패 4개는 모두 맡은 파일 밖의 시험이 옛 정책(판본 4, none 범주 우도, 1472 B 상한)을 단언하는 곳이다.

맡은 파일 밖이라 고치지 못한 실패와 고칠 방법:

- `tests/test_v33_l3_candidate.py::test_active_l1_rejects_l3_candidate_state`: `learn3.STATE_VERSION == 4`를 단언한다. 11로 바꾸면 된다(판본 6 거부 단언은 그대로 성립).
- `tests/test_v33_policy_worker.py::PolicyWorkerTests::test_current_complete_first_flight_updates_cold_loss_state_once`: `state_version` 4를 단언한다. 11로 바꾸면 된다. 같은 시험의 나머지 기대(datagram, legacy_skip_reason no_base, stats)는 c1 경로에서 그대로 성립한다.
- `tests/test_adaptation_benchmark.py::AdaptationBenchmarkTests::test_ablations_restore_only_loss_state_and_keep_observation_history`: L1이 none 경로 범주 우도를 기대하도록 바꾼 시험이다. 90859b973의 같은 메서드 본문으로 되돌리면 통과한다(그 판을 스크래치에 꺼내 현재 코드로 돌려 1 passed를 확인했다).
- `tests/test_p21_gencompare.py::HPredictionTests::test_toy_cell_matches_a_direct_computation`: gen-2 행동 (126,1,3)이 v3 후보에 있어야 한다고 단언한다. 1452 B 상한으로 빠진 행동이다. `parity_datagram_bytes(w+d, k) > decide3.UDP_MAX`인 m>0 행동은 `assertNotIn`으로 바꾸면 된다.

## 통합 정리 (2026-11-02)

묶음 P(정책 마무리와 주장 문서)가 1차 수정 뒤 남은 항목을 처리했다. 근거는 1차 검증 요약 `C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports\VERIFY_ALL.md`의 A-policy new_problems 일곱 개와 D-docs new_problems, `NOTDONE_ALL.md`의 A-py handoff 7·8항, A-go handoff 1·5, A-eval handoff 3~5, D handoff 4·5다. 이 작업은 2026-11-02 03:50에 한 번 시작했다가 계정 사용 한도로 끊겼다. 그때 바뀐 파일(시험 4개, `experiments/gate_v3_parity.py`, `g3/policy3_reference.json`, `g3/v33/V33FIX_benchmark_v1.json`)은 아래처럼 다시 확인하고 이어서 했다. 스크립트와 출력은 `C:\dev\codex_handoff\v33\runs\v33fix\P\`에 있고 목록과 sha256은 그 폴더의 `SHA256SUMS.txt`다.

### 시험 실패 4개 (A-policy new_problem 1, A-py handoff 7)

- `tests/test_v33_l3_candidate.py` 32행: `learn3.STATE_VERSION == 4`를 11로 바꿨다. 판본 6 상태를 거부하는 단언은 그대로다.
- `tests/test_v33_policy_worker.py` 48행: `state_version` 기대를 4에서 11로 바꿨다. 묶음 D가 고친 임시 폴더 fixture(`test_read_only_audit_blocks_import_time_write`)는 건드리지 않았다.
- `tests/test_adaptation_benchmark.py`의 ablation 시험: 90859b973 본문의 두 경우(인증서 30000 B·RTT 200 ms는 shield로 건너뛰고, 4000 B·80 ms는 이진 우도로 갱신)로 되돌렸다. 이 시험이 원래 지키려던 성질은 "ablation 변형은 손실 상태(`post`, `w`)만 되돌리고, 관측 이력(`hct`, `g_resid`, `stats`, `seq`)은 모든 변형에서 진행한다"이다. 되돌린 본문이 이것을 그대로 본다. HEAD 판이 더했던 것 가운데 지금 정책에서도 맞는 것은 남겼다. 문맥이 없는 경우(`k_hist`를 비움, `stats.no_ctx` 1), 관측 정보의 `policy_path` "none"·`loss_update_kind`(binary 또는 predict_only)·`skip`, `full`과 `skip_hazard_ablation`의 hazard·사후분포 반영 표지다.
- `tests/test_p21_gencompare.py` 1102행: gen-2 행동 가운데 m>0이고 `policy.parity_datagram_bytes(W+δ, k) > decide3.UDP_MAX`인 것은 v3 후보에 없어야 한다(`assertNotIn`)로 바꾸고, 나머지 행동은 여전히 `assertIn`이다. 세 toy cell을 통틀어 이렇게 빠진 행동이 하나 이상이어야 한다는 단언도 더해, 상한이 실제로 걸리는지 함께 본다. 나머지 검사(J 값, 행동 수, lead 규칙, n_need)는 그대로다.

확인: HEAD의 `afec`, `padfec`, `padfec3` 19개 파일을 스크래치에 꺼내(sha256이 `git show HEAD:<경로>`와 같음을 확인) `sys.path` 앞에 두고 고친 시험을 돌리면 넷 다 실패했다(l3 단언 실패, worker `4 != 11`, ablation `True != False`, p21 `0 not greater than 0`, `scripts\run_old.py`, `run_old_out2.txt`). 지금 정책에서는 통과한다(아래 시험 표).

### 기본 v3 관문 (A-policy new_problem 2, A-go handoff 1)

`POLICY_VERSION`을 "v3.3.1-dev"로 바꾸고 기본 참조를 다시 만들어 WSL 임시 빌드로 관문을 돌렸다. PASS, problems 없음. 자세한 값과 옵션 뜻은 `docs/V33FIX_policy_go.md` 7절에 있다.

### parity 후보 소멸 (A-policy new_problem 3)

5절에 W·k별 상한(k1·2·3·4에서 W ≤ 1407·1401·1395·1389)과 W 1406·k≥2, W 1400·k≥3에서 parity를 쓰지 않는다는 사실을 적었다. README와 `docs/REPORT_CLAIMS_v33.md`에도 옮겼다. 실측(T7)에서 W를 이 상한 아래로 잡을지는 정하지 않았다.

### 평가 JSON 문구와 증거 경로 (A-policy new_problem 4·7, A-eval handoff 5)

`g3/v33/V33FIX_benchmark_v1.json`의 `adoption_after_repetition.rule`에서 'pre-registered'를 빼고, 계획을 seed 31~50 결과를 본 뒤 seed 51 이상을 돌리기 전에 썼다는 문장으로 바꿨다(`docs/V33FIX_evaluation.md` 8절과 같은 뜻). 같은 파일의 스크래치 경로 4곳(`closed_loop.raw`, `closed_loop.trajectory_comparison_path`, `b6_independent_repetition.plan_path`, `.path`)은 보존 폴더 `C:\dev\codex_handoff\v33\runs\v33fix\A-eval`로 바꾸고 그 내역을 `evidence_relocation` 키에 적었다. 원본 JSON과 키 단위로 비교해 이 다섯 값과 새 키 말고는 같음을 확인했고, 세 파일(`compare_all.json`, `b6_repetition_plan_v1.json`, `b6_repetition_v2.json`)의 보존본 sha256이 JSON에 적힌 값과 같음도 확인했다. 이 JSON의 sha256을 적은 파일은 `docs/V33FIX_evaluation.md` 하나뿐이라(grep) 그 값을 `36f38d70…f7d2`로 고쳤다. `experiments/v33/v33fix_rejudge.py` 774행은 여전히 옛 문구를 쓰므로 evaluate를 다시 돌리면 'pre-registered'가 돌아온다. 이 파일은 묶음 P 목록 밖이다.

이 문서, `docs/V33FIX_policy_go.md`, `docs/V33FIX_evaluation.md`, `docs/V33FIX_docs_hygiene.md`가 세션 스크래치를 가리키던 곳은 보존 폴더로 바꿨다. 1차 묶음 A-py·A-go·D의 스크래치 자료 157개 파일(A-py 전체, A-go의 `final2`·`fresh`·`mutants_final`·`v32src`·맨 위 파일, D의 `eol_*.z` 셋을 뺀 전체)을 `runs\v33fix\P\first_round\`에 복사하고 한 파일씩 sha256을 대조했다(불일치 0). 감사 원문은 이미 `C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01`에 있었다. 묶음 P가 고친 문서에서 `tools/scrub_for_publish.py`의 사용자 경로 정규식에 걸리는 줄은 0이다(WSL 경로도 `~/`로 적었다).

### 명시 행동 경로 (A-policy new_problem 6)

5절에 적었다. 코드는 바꾸지 않았다.

### README와 REPORT_CLAIMS

`experiments/quicbed/policy3.go`의 `p3StateVersion = 11`(50행), `p3UDPMax = quicgoMaxIPS`(51행, `pfail_table.go` 35행의 1452), `p3CacheSchema = "padfec3.cache3/11"`(53행), `p3PolicyVersion = "v3.3.1-dev"`(56행)와 `padfec3/learn3.py` 25·26행을 직접 읽어 README 3행과 REPORT_CLAIMS의 값과 같음을 확인했다. README가 가리키는 V33FIX 문서 9개는 모두 있다. REPORT_CLAIMS의 v3.3.1-dev 절에는 v3.2-dev와 같다는 시험의 범위, `docs/V33FIX_evaluation.md` 8절의 쓸 수 있는/쓰면 안 되는 문장, parity 후보 소멸, c1 경로에 경보 장치가 없다는 점(A-eval handoff 4)을 출처 문서의 숫자 그대로 옮겼다. CONTEXT.md 행 번호 인용은 절 이름으로 바꾸고 기준 판을 밝혔다(D-docs new_problem 1).

### 옛 설명 문서의 정정 줄

`docs/E12_l1_go_contract.md`, `J1_disposition.md`, `J1_tail_design.md`, `J7_wire_contract.md`, `L1_benchmark_execution.md`, `L1_learning.md`, `L1_observation_contract.md`, `L2_learning.md`, `L3_monitor_design.md`, `L5_disposition.md`, `generation_paths.md` 11개 모두 제목 아래에 "2026-11-02 정정:" 문단을 하나 넣었다. 본문은 고치지 않았다. 문서마다 그 문서가 다루는 내용(E12는 참조 파일, J7은 W 상한, L3는 record_only 팔, L5는 1461 B parity, generation_paths는 gen_id)에 맞췄다. 빠진 문서는 없다. 정정 문단 때문에 이 문서들의 행 번호가 2씩 밀렸다. 그래서 REPORT_CLAIMS가 인용하던 `L1_observation_contract.md` 27행과 `L1_benchmark_execution.md` 11행을 29·13행으로 고쳤다. 감사 원문(`findings\v33audit_2026-11-01`)의 행 번호 인용은 HEAD 판 기준의 기록이라 그대로 두었다.

### `--history` 단위 시험 (D handoff 5)

`tests/test_v33_repro_tools.py`에 `test_history_check_finds_removed_private_key_and_oversize_blob`를 넣었다. 저장소 밖 임시 폴더에 합성 git 저장소를 만들고, 완전한 PEM 개인키 파일과 머리 문자열만 있는 텍스트를 커밋한 뒤 키 파일을 지우고 20,000,001 B 파일을 커밋한다. `scrub_for_publish.history()`가 키 blob 1개(머리만 있는 텍스트는 잡지 않음, HEAD 경로 없음), 추가·삭제 커밋, 20 MB 초과 blob 1개(HEAD 경로 `big.dat`)를 찾는지, 상한을 그 크기로 주면 0개인지, `main`이 `--check --history`에 종료 코드 1을, `--history`만 주면 2를 내는지, 실행 전후 HEAD와 `git status`가 같은지, 끝난 뒤 임시 폴더가 지워졌는지 본다. git이 없으면 건너뛰고, git 명령 하나가 120초를 넘으면 건너뛴다. HEAD 판 `scrub_for_publish.py`(history 없음)로 돌리면 이 시험은 AttributeError로 실패한다(`scripts\run_old_scrub.py`).

### `gen_id`와 옛 E12 생성기 (A-go handoff, VERIFY_ALL A-policy new_problem 5)

`genconfig.json`의 `gen_id`는 "v3.3-dev" 그대로 둔다. 이 값을 읽는 곳은 `experiments/generation.py` 8행(필수 키 검사)과 `experiments/pipeline.py` 375행뿐이고, 후자는 `gen_id == "v3.3-dev"`일 때 과거 파이프라인을 막는다. 정책 판본에 맞춰 "v3.3.1-dev"로 바꾸면 이 차단이 풀린다. `gen_id`는 세대 이름이고 정책 판본은 `learn3.POLICY_VERSION`과 `p3PolicyVersion`이 따로 맡는다(`docs/generation_paths.md`에 정정 줄을 넣었다).

`g3/l1_go_reference_gen.py`(E12 L1 생성기)와 `g3/v33/E12_l1_reference_v1.json`(상태 4 입력)은 새 정책에서 쓸모가 없다. 옛 생성기는 none 경로 info에 c1 전용 키를 요구하고, E12 참조의 상태에는 `c1_seen`이 없어 지금 Go가 읽는 단계에서 거부한다(`docs/V33FIX_policy_go.md` 3절의 판단, 실행하지 않음). 대신하는 것은 `python -I -B experiments/gate_l1_go.py --generate`와 `g3/v33/V33FIX_policy_reference_v1.json`이다. 두 파일을 참조하는 곳은 `docs/E12_l1_go_contract.md`, `docs/V33FIX_policy_go.md`, 두 파일 자신과 영수증, `g3/v33/J7_l1_reference_v1*.json`뿐이고 시험·관문 코드는 없다. 지울지는 도현님이 정한다.

### 시험 (묶음 P가 직접 돌림)

| 실행 | 결과 |
|---|---|
| 고친 시험 4개 파일(`test_v33_l3_candidate.py`, `test_v33_policy_worker.py`, `test_adaptation_benchmark.py`, `test_p21_gencompare.py::HPredictionTests`) | 22 passed, 하위 53 passed |
| `tests/test_v33_repro_tools.py` | 7 passed(새 시험 2.5초) |
| 고친 시험 파일 5개 전체 + `tests/test_padfec3_*.py` + `tests/test_v33fix_policy.py` + `tests/test_l1_go_gate.py` | 274 passed, 8 deselected, 하위 430 passed, 61초 |
| `python -I -B g3/policy3_reference_gen.py --check` | check: identical |
| 기본 v3 관문(WSL, 임시 빌드) | PASS(`docs/V33FIX_policy_go.md` 7절) |

pytest는 모두 `PYTHONDONTWRITEBYTECODE=1 python -I -B -m pytest -p no:cacheprovider`로 돌렸고, 실행 전후 `git status --short --ignored`의 추적 안 된·무시된 목록이 같았으며 `__pycache__`가 생기지 않았다. 전체 pytest는 다른 묶음 변경이 섞여 있어 돌리지 않았다(통합 때 한다). 같은 임시 빌드의 Go 시험에서 `TestComparisonSameSlotsAndAccounting` 하나가 실패했는데, 테스트베드 묶음이 고치던 파일의 시험이고 정책 코드와 관계없다.

### 못 한 것과 사람이 정할 것

- 실측(T7)에서 W를 parity 상한(k=2면 1401) 아래로 잡을지, W 1406·k=2에서 parity 없이 잴지.
- `g3/l1_go_reference_gen.py`와 `g3/v33/E12_l1_reference_v1.json`을 지울지.
- 오프라인 분석(`replay_g3.py`)에서 1452 B를 넘는 명시 행동을 표시하거나 거를지.
- `experiments/v33/v33fix_rejudge.py` 774행의 'pre-registered' 문구(목록 밖 파일).
- `~/quicbed_gen33`에 새 바이너리를 설치하는 일(이 작업에서 금지).

### 덧붙임 (2026-11-02, 통합 담당과 묶음 D)

- `experiments/v33/v33fix_rejudge.py`의 rule 문자열(위 "못 한 것" 넷째 항목, 묶음 P not_done 1): 통합 담당이 `after_repetition`의 rule에서 'pre-registered'를 빼고, `g3/v33/V33FIX_benchmark_v1.json`의 `adoption_after_repetition.rule`과 같은 문장을 반복 계획의 seeds(51..250)로 만들게 고쳤다. 묶음 D가 다시 읽었을 때 그 파일에 'pre-registered'는 0곳이고 rule은 지금 775행 f-string이다. 그래서 evaluate를 다시 돌려도 옛 문구가 돌아오지 않는다.
- 1절 11행 "회신이 빠지거나 잘린 연결은 HCT 3등급 우도"의 쓸 수 없는 회신에는 `sent=0`인 빈 회신도 든다. 사유는 `source_none`, `truncated`, `empty` 셋이고(3절 `_observe_c1` 항목, `padfec3/learn3.py` `_observe_c1`의 `reason`), 문맥이 있으면 범주 우도, 없으면 예측만이다. 같은 뜻으로 `docs/L1_observation_contract.md`와 `docs/L2_learning.md` 맨 위 정정 줄을 고쳤다(묶음 D, 검증자 지적 "정정 줄 두 곳이 범주 우도를 '회신이 빠지거나 잘린 연결에만' 쓴다고 적어 빈 회신(sent=0)을 빠뜨렸다").

### 정정 (2026-11-07, F44)

"못 한 것과 사람이 정할 것"의 측정 W 미결은 D50 기본값 W 1280으로 정리됨. 봉인 3단계의 base W도 1280이며 k=2인 그 조건에서 m>0 후보는 14개다. 본문의 W 1406·k=2는 후보가 B0 하나인 모형 입력이고, 봉인 g2auto가 선택한 W_eff 1406은 53,600행 중 6행이었다. 이 드문 선택값을 봉인 측정의 기본 W로 일반화하지 않는다. k=3·W=1400에서는 B0과 δ=23 padding만 남는다. 조건과 출처는 [활성 정책의 알려진 한계](FINAL_policy_limits.md)의 MS-12에 있다.

명시 행동의 상한 밖 여부는 별도로 표시하지 않는다. 현재 `replay_g3.py` 호출처는 W 1280에서 LEGACY 네 행동(δ=0)과 v3.1 기록 행동(δ=0·1)만 넣으므로 1452 B 상한 밖으로 나가지 않는다. Go auto3에는 이 명시 행동 경로가 없다. Python `actions=` 자체가 상한을 거르는 것은 아니므로 임의 행동을 넣는 분석 호출의 안전성을 보장한다는 뜻은 아니다. CP-10의 현재 호출 범위로 미결을 닫으며 코드와 재생 결과는 바꾸지 않았다.
