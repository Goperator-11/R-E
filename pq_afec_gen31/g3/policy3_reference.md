# policy3 기준 벡터: Go 이식 대조 자료 (v3.1)

`g3/policy3_reference.json`은 `padfec3/layout.py`, `padfec3/learn3.py`, `padfec3/decide3.py`가 내는 답을 고정해 둔 파일이다. Go 쪽 `experiments/quicbed/policy3.go`가 같은 입력에서 같은 결정, 같은 사후분포, 같은 감시층 상태를 내는지 대조할 때 쓴다. 정책 버전은 `v3.1`, 스키마는 `padfec3.policy3_reference/2`다. 측정 자료는 들어 있지 않다. 궤적의 관측값도 생성기가 모형에서 뽑은 합성값이다.

v3.1 명세는 사전 등록된 여섯 항목이다. 완료 규칙에 비행 전 서버 ACK 바이트를 넣고(1), 명목 2-RTT 행동의 관측은 손실 사후에 넣지 않고(2), 그런 행동이 최적일 때 16번째마다 명목 1-RTT 행동을 재평가하고(3), 행동별 잔차 감시층을 두고(4), 클라이언트 행에 새 필드를 남긴다(5). 나머지는 v3과 같다(6).

## 1. 재생성과 확인

```
python -B g3/policy3_reference_gen.py            # 다시 쓴다
python -B g3/policy3_reference_gen.py --check    # 메모리에서 다시 만들어 파일과 비교만 한다
```

- 현재 파일: 12,855,493 B, sha256 `8c04033ec9036df50e81703f50cc4fcf50c4744e036213121701061bcce9df3f`. 같은 코드로 한 번 더 만든 `--check` 결과는 "identical"이다.
- 생성 시간은 이 PC(Windows, Python 3.14.2)에서 약 87초다. 원시점 1.4초, 결정점 59.5초, 궤적 25.7초.
- `sources_sha256`에 생성에 쓴 소스 7개의 해시가 있다. 하나라도 바뀌면 파일을 다시 만들고 Go 대조도 다시 낸다.
- 시드: 결정점 20261002, 무작위 원시점 20261003, 절벽 원시점 20261031, 벌점 20261032, 궤적 31~35. 결정점의 문맥과 사후분포는 v3 기준 벡터와 같은 시드로 뽑았으므로 6,720개 문맥이 v3 파일과 하나하나 같다.
- 파일은 줄 단위 JSON이다. 머리 키는 한 줄에 하나, `primitives`와 `decisions`는 한 줄에 레코드 하나, `trajectories`는 한 줄에 궤적 하나다. 실수는 Python `repr`(최단 왕복 표기)로 적었다.

## 2. 대조 기준

| 묶음 | 수 | 정확히 같아야 하는 것 | 절대오차 ≤ 1e-9 |
|---|---:|---|---|
| `primitives` | 2,800 | `a_pre` | `J`, `e`, `p_two_rtt`, `p_fail`, `p_one_rtt` |
| `decisions` | 6,720 | `action`, `mode`, `n_need`, `n_cands`, `cand_hash`, `n_tied`, `n2`, `reeval_cond`, `alt` | `ej`, `jmin`, `score`, `pen_chosen`, `alt_ej`, `alt_score` |
| `decisions[*].cands` | 2,016개 레코드 | 후보 순서, 후보별 `n2` | 후보별 `ej`, `pen` |
| `trajectories` 걸음 | 5 × 10,000 | `a`, `why`, `y`, `upd`, `n2`, `reeval`, `alarm`, `n_alarm`, `skip` | `ej`, `pen`, `common`, `resid` |
| `trajectories` 스냅숏 | 5 × 10 | `k_hat`, `S_hat`, `n_need`, 상태의 `k_hist`, `S_hist`, `hct`, `hct_seq`, `seq`, `n_dec`, `n_reeval`, `g_alarm`, `stats` | 상태의 `g_resid`, `g_common` |

사후분포(`post_h`, `w`, `combined`, 걸음별 `p_mean`)는 v3과 같이 상대오차 1e-12 이하다. `cands`는 `id % 10 == 0`인 672개와 벌점을 준 1,344개에 붙어 있다. 두 묶음은 겹치지 않는다.

결정이 갈리면 그 걸음에서도 관측은 기록된 `a`와 기록된 `ej`(`j_pred`)로 넣는다. 그래야 한 번 갈린 것이 뒤의 사후분포와 감시창 비교를 오염시키지 않는다.

동점 규칙에는 점수의 정확한 비교가 들어 있다(5절 6). Go 쪽은 Python과 같은 연산 순서를 지키고 곱셈-덧셈 융합(FMA)을 피해야 한다. Go 규격은 명시적 float64 변환이 융합을 막는다고 정하고 있다(https://go.dev/ref/spec#Floating_point_operators). 감시층의 평균은 `learn3.mean_seq`처럼 왼쪽부터 차례로 더한 뒤 개수로 나눈다. Python 3.12부터 내장 `sum()`은 보정 합산을 하므로 이 값에는 쓰지 않았다.

`experiments/gate_v3_parity.py`(스키마 `padfec3.gate_v3_parity/2`)는 이 표의 필드를 모두 비교한다. 목록은 `PRIM_EXACT`, `DEC_EXACT`, `DEC_CLOSE`, `STEP_EXACT`, `STEP_CLOSE`, `STATE_EXACT`이고, 상태의 `g_resid`와 `g_common`은 모양이 같은지 본 뒤 값을 절대오차로 비교한다.

## 3. 레코드 형식

`decisions[i]`: `k`, `W`, `cert`, `s0_base`, `S`, `rtt`, `u`, `a_pre`(= `preflight_bytes(k, u)`), `post_kind`, `g`, `q`, `n_need`, `n_need_cert`, `n_cands`, `cand_hash`, `action`, `mode`, `ej`, `pen_chosen`, `score`, `n2`, `jmin`, `n_tied`, `reeval_cond`, `alt`, `alt_ej`, `alt_score`. `id % 5 == 2`인 레코드에는 `pen`([δ, ℓ, T, 벌점 ms] 목록)이 있다. `cands`는 [δ, ℓ, T, ej, n2(0/1), pen] 목록이고 후보 생성 순서다.

- 사후분포는 길이 26 벡터로 펴서 쓴다. `g`에 없는 칸은 0이다.
- `pen`이 있는 레코드는 `decide_core(..., pen=그 벌점)`의 결과다. 첫 항목은 벌점 없이 고른 행동이고, 나머지 0~2개는 후보 가운데 무작위로 고른 행동이다. 벌점은 15% 확률로 0, 나머지는 0~80 ms 균등값(소수 셋째 자리 반올림)이다.
- `alt`는 명목 1-RTT 후보 중 점수 최소인 행동이다(5절 7). 명목 1-RTT 후보가 없으면 null이다. 결정점에서는 재평가 계수기를 쓰지 않으므로 `action`은 언제나 주 선택이다.

`primitives[i]`: `set`("random" 2,000개, "cliff" 800개), `k`, `W_eff`, `m`, `lead`, `p`, `rtt`, `u`, `n_need`, `a_pre`, `margin`(= 3·(k·W_eff + ℓ·parity) − 1280·(n_need−1), 무손실 선행 신용의 여유)과 `layout.evaluate(..., later="v3")` 결과다. 절벽 원시점은 `margin`이 −30 이상 a_max + 30 이하가 되게 W_eff를 골랐다(a_max = 41·(k−1)). 그중 475개가 a_pre > 0이고, 258개는 여유가 (0, a_pre] 안이라 v3과 v3.1의 완료 판정이 갈린다.

`trajectories[j]`:
- 머리: `id`, `seed`, `cert`, `s0_base`, `k_true`, `W`, `u`, `c_pkt`, `rtt_true`, `schedule`, `common_ms`, `bias`, `n_steps`, `action_counts`, `final_stats`.
- `steps`: 길이 10,000인 병렬 배열 `a`, `why`, `ej`, `p_mean`, `rtt`, `hct`(실패면 null), `ok`, `k`, `srv`, `y`, `upd`, `n2`, `reeval`, `pen`, `alarm`, `common`, `n_alarm`, `resid`, `skip`.
- `snapshots`: 1,000걸음마다 `after_step`, `post_h`(5×26), `w`(5), `combined`(26), `p_mean`, `k_hat`, `S_hat`, `n_need`, `state`(7절의 JSON 상태 전체).

궤적 재생 절차는 다음과 같다. 상태를 새로 만든 뒤 t = 0..9999마다:
1. `d = decide3(state, W, u, steps.rtt[t], c_pkt)`. `a`, `why`, `ej`, `p_mean`, `n2`, `reeval`, `pen`, `alarm`(= `guard_alarm`), `common`(= `guard_common_ms`), `n_alarm`(= `guard_alarmed_actions`)을 확인한다.
2. `observe3(state, steps.a[t], steps.hct[t], steps.ok[t], steps.k[t], steps.srv[t], steps.rtt[t], j_pred=steps.ej[t])`. 반환한 `y`, `updated`, `resid`, `skip`이 `steps.y[t]`, `steps.upd[t]`, `steps.resid[t]`, `steps.skip[t]`와 같아야 한다.
3. (t+1)이 1,000의 배수면 스냅숏과 비교한다.

클라이언트 행(qamp `-fec auto3`) 필드와의 대응:

| 행 필드 | Python 값 | 시점 |
|---|---|---|
| `j3_pred_pre_ms` | `decide3(...)["j3_pred_pre_ms"]` = 고른 행동의 벌점 없는 EJ = 궤적의 `ej` | 결정 |
| `guard_alarm` | `["guard_alarm"]`, 고른 행동이 경보 중인가 | 결정(해제 처리 뒤) |
| `guard_common_ms` | `["guard_common_ms"]`, 공통 지연 b | 결정(해제 처리 뒤) |
| `guard_alarmed_actions` | `["guard_alarmed_actions"]`, 경보 중인 행동 수 | 결정(해제 처리 뒤) |
| `reeval` | `["reeval"]`, 이때 `why3` = "reeval" | 결정 |
| `guard_resid_ms` | `observe3(...)["resid"]`, 잔차 h − j3_pred_pre_ms(없으면 null) | 관측 |
| `policy_version` | `["policy_version"]` = "v3.1" | 결정 |

기존 `j3_ms`는 `ej`(벌점 없는 기대 J)로, `j3_min_ms`는 `jmin`(후보 점수의 최소)으로 두면 v3 행과 뜻이 같다. 감시층 경보가 없으면 둘 다 v3 정의와 같은 값이다. 관측 쪽 `obs_shielded`는 `skip == "shield"`일 때만 참이다. 생략 이유 전체(`skip`)는 행에 새로 남기는 편이 분석에 낫지만 명세 5에는 없는 필드다.

## 4. 완료 규칙 (layout)

신용 B 바이트를 가진 가지는 다음일 때만 한 번 왕복으로 끝난다.

```
3·B − A_pre > 1280·(n_need − 1)
A_pre = 41·(k − 1)   (u > 0)
A_pre = 0            (u ≤ 0)
```

`layout.one_rtt_ok`, `layout.rtt_count(credit, need, a_pre)`, `layout.preflight_bytes(k, u)`가 이 식이다. `evaluate`는 A_pre를 k와 u에서 직접 정하므로 호출 형식은 v3과 같고, 결과에 `a_pre`를 붙인다. 이 판정을 쓰는 곳은 성공 가지 하나뿐이고, 경주 신용 가지와 복구 가지가 모두 거기를 지난다. 그래서 J3, e(a,p), 명목 왕복 판정(e(a,0) ≥ 0.5)이 모두 새 규칙을 따른다. 경주 q 표, 응답 직렬화 항, 실패 비용은 그대로다.

A_pre = 0이면 이 식은 v3의 ceil(3B/1280) ≥ n_need와 정수 범위에서 같다. 시험 `test_completion_rule_without_preflight_equals_ceil_rule`이 신용 −3..60,000(12,000 위는 7바이트 간격)과 n_need 0..45 격자에서 확인한다. 기준 벡터에서도 u = 0이거나 k = 1인 결정점은 행동과 EJ가 v3 파일과 비트 단위로 같다.

후보 생성(`levers_s`, `_combo_deltas`)은 명세 6에 따라 v3 그대로다. 그래서 결합 후보의 δ는 A_pre 없는 칸 계산으로 만들어진다.

## 5. 결정 규칙 (decide_core, decide3)

`decide_core(post, k, W, S, u, RTT, c_pkt, pen=None, reeval=False)`:
1. `n_need = binNeeded(S, bin_index(k·W), c_pkt)`.
2. 후보는 v3과 같다(levers 이식, 거르기, 선행 수 펼치기).
3. `ej(a) = Σ_g post[g]·J3(a | G[g])`. g는 0부터 차례로 더하고 시작값은 0.0이다. post[g] == 0인 칸은 건너뛴다.
4. `pen(a)`는 `pen` 사전에서 "δ,ℓ,T" 키로 찾은 값이고 없으면 0.0이다. `score(a) = ej(a) + pen(a)`.
5. `n2(a) = e(a, p=0) ≥ 0.5`. e는 4절 규칙의 `p_two_rtt + p_fail`이다.
6. 주 선택: jmin = min score. score ≤ jmin + 0.01인 후보를 모아 아래 키가 가장 작은 것을 고른다. v3 동점 키에서 EJ 자리를 score로 바꾼 것이다.
   `(added, m>0이면 0 아니면 1, mode 문자열, ℓ == legacy(m)이면 0 아니면 1, score, ℓ, m, δ)`
7. 대안: n2가 거짓인 후보만 놓고 6과 같은 방법(최소 score, 0.01 ms 동점, 같은 키)으로 고른다. 없으면 null.
8. `reeval_cond = n2(주 선택) and 대안 있음`. `reeval=True`이고 조건이 참이면 대안을 고르고 why = "reeval"이다.
9. 결과의 `ej`, `pen`, `score`, `n2`, `j3_pred_pre_ms`(= ej)는 최종 선택의 값이다. `jmin`, `n_tied`는 주 선택 단계의 값이다.

`decide3(state, W, u, rtt, c_pkt)`는 상태를 바꾼다. 연결 하나에 한 번만 불러야 한다.
1. 감시 해제: 경보 중인 행동마다 `n_dec − 경보 시점 ≥ 64`이면 경보를 지우고 그 행동의 잔차 창도 지운다.
2. b = 공통 지연(6절), 벌점 = 경보 중인 행동마다 max(0, mean(그 행동의 창) − b).
3. `n_dec += 1`. 콜드나 b0 결정도 센다.
4. S 창이나 k 창이 비었으면 b0(`why = "cold"`), k̂가 1..4 밖이면 b0(`"k_range"`), rtt ≤ 0이면 b0(`"no_rtt"`). b0의 `ej`와 `j3_pred_pre_ms`는 null이다.
5. 나머지는 `decide_core(combined(state), k̂, W, Ŝ, u, rtt, c_pkt, pen=벌점)`.
6. `reeval_cond`가 참이면 `n_reeval += 1`. 그 뒤 `n_reeval % 16 == 0`이면 대안으로 바꾸고 why = "reeval", `stats.reeval += 1`. 조건을 만족한 결정의 16번째, 32번째, ...가 재평가다.
7. 결과에 `p_mean`, `p_map`, `p_ge_010`, `guard_alarm`, `guard_common_ms`, `guard_alarmed_actions`, `guard_cleared`, `dec_index`, `n_reeval`, `policy_version`을 붙인다.

## 6. 학습 규칙 (observe3)

상수: G = table.py P_VALS 26점, H = (1/30, 1/100, 1/300, 1/1000, 1/3000), ε = 0.01, 가중치 하한 1e-6, k 창 16, S 창 16, 팔별 HCT 창 32, 기준선 최소 관측 8, 사건 문턱 0.5·RTT, 차폐 RTT 200 ms, 명목 2-RTT 문턱 e(a,0) ≥ 0.5, 재평가 주기 16, 공통 잔차 창 64, 행동 잔차 창 32, 경보 최소 잔차 8, 경보 문턱 0.5·RTT, 해제 주기 64결정.

`observe3(state, a, hct, ok, k_obs, srv, rtt; W, u, c_pkt, j_pred)`:
1. 문맥, 기준선 b, y는 v3과 같다. 문맥이 있으면 n_need = binNeeded(Ŝ, bin_index(k̂·W), c_pkt).
2. 잔차: ok이고 j_pred가 있으면 r = hct − j_pred. 이때
   - r을 행동 a의 창(최근 32개)에 넣는다.
   - 관측 전에 a가 경보 중이 아니었으면 r을 공통 창(최근 64개)에도 넣는다.
   - 경보 검사: 경보 중이 아닌 모든 행동(키 순)에 대해 창이 8개 이상이고 mean(창) − b_now > 0.5·rtt이면 경보를 올리고 시점을 현재 `n_dec`로 적는다. b_now는 방금 갱신한 공통 창의 중앙값이다. rtt가 없거나 0 이하면 검사하지 않는다.
   - 실패 연결(ok 거짓)은 잔차를 만들지 않는다. 학습층에는 시간 초과 대입값이 없다.
3. 생략 이유는 다음 순서로 정한다. 명목 2-RTT이고 rtt ≥ 200이면 "shield", 명목 2-RTT면 "nominal2", 2의 처리를 마친 뒤 a가 경보 중이면 "guard". 경보를 올린 관측은 그 자리에서 "guard"가 된다.
4. 사후 갱신은 y와 문맥이 있고 생략 이유가 없을 때만 한다. 생략된 관측은 사후와 가중치를 바꾸지 않는다(hazard 혼합도 하지 않는다). 통계는 `no_base`, `no_ctx`, `shield`, `nominal2`, `guard`, `upd` 가운데 하나만 늘어난다.
5. 사건 확률, 우도, 필터 식은 v3과 같다. 명목 2-RTT 행동은 이제 우도까지 오지 않으므로 `event_prob`의 p_fail 분기는 학습 경로에서 쓰이지 않는다.
6. 넣기: v3과 같다. ok일 때만 k 창, 팔 HCT 창, 최근 순번을 갱신하고, y ≠ 1이고 srv > 0이면 S 창에 넣는다. 생략된 관측도 이 창들은 갱신한다.

공통 지연 b는 공통 창의 중앙값이고(짝수 개면 가운데 둘의 평균) 창이 비면 0이다.

## 7. 상태 JSON (v = 2)

`DestState3.to_json`: `v`(2), `k_hist`, `S_hist`, `hct`, `hct_seq`, `seq`, `post`(5×26), `w`(5), `n_dec`, `n_reeval`, `g_resid`({"δ,ℓ,T": [잔차...]}), `g_common`([잔차...]), `g_alarm`({"δ,ℓ,T": 경보 시점 n_dec}), `stats`. `stats` 키는 `obs`, `upd`, `shield`, `nominal2`, `guard`, `no_base`, `no_ctx`, `events`, `fail`, `resid`, `reeval`, `alarm_raised`, `alarm_cleared`다. `from_json`은 v = 1 상태를 거부한다. v3.1 확증 캐시는 새로 시작한다는 설계(X7 3절)를 따랐다.

rtt는 learn3 밖에서 정한다. 재생기는 gen-2 policyRTT와 같은 규칙을 쓴다: 유효 ACK RTT 표본이 하나라도 있으면 그 최소값, 없으면 성공 연결 HCT의 최소값.

## 8. 생성기가 만드는 것

결정점 6,720개는 k 1..4 × W {1200, 1280, 1350} × cert 14개 × s0_base {382.45, 1472.0} × RTT {10, 50, 100, 200} × u {0, 2, 5, 10, 100} 격자를 한 번씩 쓴다. 사후분포 종류(point, mix2, mix4, full)와 문맥 순서는 v3 파일과 같다.

- 벌점이 없는 5,376개 가운데 375개가 v3 파일과 다른 행동을 고른다. 모두 u > 0이고 k ≥ 2인 문맥이다(k = 2: 199, k = 3: 112, k = 4: 64). EJ가 바뀐 결정도 이 375개뿐이다.
- 벌점을 준 1,344개 가운데 1,264개는 0이 아닌 벌점이 하나 이상 있고, 1,117개는 벌점 때문에 벌점 없는 선택과 다른 행동을 고른다.
- 주 선택이 명목 2-RTT인 결정은 92개이고 모두 대안이 있다(`reeval_cond` 참).
- 동점 후보가 둘 이상인 결정 1,310개, 고른 행동 140종류. mode는 parity 6,024, combo 584, none 98, pad 14다.

궤적 다섯 개는 합성 관측이다. 걸음마다 참 손실률 p에서 `layout.evaluate`(v3.1 완료 규칙)가 주는 1-RTT, 2-RTT, 실패 확률로 결과를 뽑는다. HCT, 실패, 이상값, k 흔들림 규칙은 v3 생성기와 같다. T5에만 `common_ms`(모든 HCT에 더함)와 `bias`(특정 행동에 확률적으로 RTT 배수를 더함)가 있다. 이 둘은 감시층을 시험하려고 넣은 모형 밖 지연이다.

| 궤적 | 조건 | 손실 일정 | 고른 행동(횟수) | 갱신 / 생략(shield, nominal2, guard) / 사건 | 재평가 / 경보 |
|---|---|---|---|---|---|
| T1_bigcert | cert 16000, k 2, u 2, RTT 50 | 2% 450 ↔ 15% 450 | (0,3,1) 8,634, (0,0,4) 1,305, (0,0,3) 37, (0,0,2) 11, (0,1,3) 8, (0,1,2) 4, b0 1 | 7,568 / 0, 1,365, 1,058 / 1,208 | 91 / 32 |
| T2_rtt200 | cert 9000, k 2, u 2, RTT 200 | 같음 | (0,2,2) 9,069, (0,1,3) 930, b0 1 | 9,991 / 0, 0, 0 / 202 | 0 / 0 |
| T3_x25519_unlimited | cert 4032, k 1, u 0, RTT 50 | 0% 700, 5% 300, 1% 500 | (1,0,4) 9,999, b0 1 | 9,991 / 0, 0, 0 / 3 | 0 / 0 |
| T4_shielded_rtt200 | cert 30000, k 2, u 5, RTT 200 | 2% ↔ 15% | (0,0,4) 9,999, b0 1 | 0 / 9,991, 0, 0 / 0 | 0 / 0 |
| T5_guard_c6000_u10 | cert 6000, k 2, u 10, RTT 80, 공통 +3 ms, (0,2,2)에 90% 확률로 +1·RTT | 1% 400 ↔ 8% 400 | (1,2,2) 7,198, (0,2,2) 1,978, (0,1,2) 508, (0,1,3) 315, b0 1 | 9,875 / 0, 0, 116 / 67 | 0 / 117 |

T2, T3, T4는 고른 행동과 횟수가 v3 파일과 같다. T1은 명목 2-RTT 생략과 재평가 때문에 달라졌다(v3: (0,3,1) 8,617, (0,0,4) 1,382).

## 9. 궤적에서 본 감시층의 성질 (합성 자료)

T5에서는 감시층이 설계대로 움직인다. (0,2,2)의 잔차 평균은 +75.1 ms이고 다른 행동은 +3.7~+5.4 ms다. (0,2,2)는 경보를 117번 받았고, 경보 중에는 한 번도 선택되지 않았다. 대신 해제 뒤 다시 8번 관측해야 경보가 서므로, 64결정마다 나쁜 행동을 약 8번 다시 고른다. (0,2,2) 1,978회의 대부분이 이 재무장 비용이다.

T1은 모형에서 그대로 뽑은 세계인데도 경보가 32번 섰고, 32번 모두 15% 블록 안이다. 행동별로는 (0,3,1) 21번, (0,0,4) 6번, (0,0,3) 3번, (0,0,2)와 (0,1,3) 각 1번이다. 15% 블록에서 (0,3,1)의 잔차는 두 봉우리로 갈린다. 걸음 700~729를 보면 1-RTT 연결이 약 −19 ms, 2-RTT 연결이 약 +36 ms다. 공통 창은 대부분 (0,3,1)의 잔차라 중앙값 b가 다수인 1-RTT 봉우리(−19 ~ −26 ms)에 붙는다. 반면 32개 창의 평균은 두 봉우리 사이, 0 근처에 있다. 그래서 모형이 평균으로 맞아도 mean − b가 20 ms 안팎이 되고, 2-RTT가 조금 몰리면 0.5·RTT = 25 ms를 넘는다. 잔차가 한 봉우리이고 0 근처인 명목 2-RTT 행동((0,0,4) 등)도 같은 이유로 b보다 25 ms 넘게 위에 놓여 경보를 받는다. 경보가 서면 그 행동에 벌점이 붙어 선택이 옮겨 가고, (0,0,x) 관측은 명목 2-RTT라 생략되므로 그동안 사후가 거의 멈춘다. T1의 guard 생략 1,058회와 경보 중 선택 1,037회가 이 경로에서 나왔다. 한 행동만 쓰는 목적지에서는 반대로 그 행동의 잔차가 공통 창을 채워 b가 따라오므로 경보가 서기 어렵다. 두 성질 모두 상수를 바꾸지 않고 기록만 해 둔다.

## 10. 명세 문구에 없던 것을 내가 정한 곳

v3 때 정한 것:

1. 사건 확률. 명목 2-RTT 팔은 e_learn = p_fail, 나머지는 e_learn = p_two_rtt + p_fail. v3.1에서는 명목 2-RTT 관측이 우도까지 오지 않으므로 학습 경로에서는 뒤쪽만 쓰인다.
2. 차폐 관측은 갱신을 아예 건너뛴다(hazard 혼합도 하지 않는다). v3.1의 nominal2, guard 생략도 같은 방식이다.
3. 응답 직렬화 항은 τ(W_eff)다.
4. decide3는 s0_base를 받지 않는다. n_need는 Ŝ에서 binNeeded로 구한다.
5. y ≠ 1이면(분류 전 포함) S 창에 넣는다. 그래야 콜드 b0가 첫 연결 한 번으로 끝난다.
6. 동점 키 뒷부분: gen-2 배치(ℓ = legacy)를 먼저, 그다음 점수, ℓ, m, δ 순.
7. 중앙값은 짝수 개일 때 가운데 둘의 평균이다.
8. 기준선을 옮겨 올 팔이 여럿이면 관측 수, 다음으로 최근성으로 고른다.
9. 가중치 하한은 정규화 → 하한 적용 → 다시 정규화 순서다.
10. k̂가 1..4 밖이거나 rtt ≤ 0이면 b0를 고른다.

v3.1에서 정한 것:

11. A_pre는 `evaluate` 안에서 k와 u로 정한다. 함수 인자로 받지 않으므로 v3 호출 형식(게이트의 새 표본 생성 포함)이 그대로 쓰인다.
12. 재평가 계수기는 조건을 만족한 결정에서만 먼저 1을 더하고 16으로 나눈 나머지를 본다. 첫 재평가는 조건을 만족한 16번째 결정이다. "가장 낮은 기대 J"는 벌점을 더한 점수로 비교하고, 0.01 ms 동점은 주 선택과 같은 키로 가린다.
13. `j3_pred_pre_ms`는 벌점 없는 EJ다. 벌점을 더한 값으로 잔차를 내면 경보 중인 행동의 잔차가 벌점만큼 작아져 경보가 스스로 풀리는 고리가 생긴다.
14. 경보는 걸쇠다. 올라간 뒤 64결정 동안은 조건이 다시 거짓이 돼도 유지되고, 그동안 벌점 크기만 현재 창과 b로 다시 계산한다. 명세의 "창을 새로 할 때 다시 검사한다"를 이렇게 읽었다.
15. 경보 검사는 관측마다 경보 중이 아닌 모든 행동에 대해 한다. b가 다른 행동의 관측으로도 움직이기 때문이다(시험 `test_other_actions_can_alarm_when_common_delay_falls`).
16. 해제 시점: 경보를 올린 관측 뒤의 64결정은 경보 상태로 결정하고, 65번째 결정의 맨 앞에서 지운다. 창은 빈 목록이 아니라 키째 지운다.
17. 실패 연결은 잔차를 만들지 않는다. 학습층에는 시간 초과 대입값이 없고, 10,000 ms 대입은 확증 분석의 규칙이다.
18. 생략 이유가 겹치면 shield > nominal2 > guard 순으로 하나만 센다. `shield`의 뜻(RTT ≥ 200의 명목 2-RTT)은 v3과 같게 두고 RTT < 200은 `nominal2`로 따로 센다.
19. `n_dec`는 b0를 포함한 모든 decide3 호출을 센다. 그래서 decide3는 상태를 바꾸고, 연결마다 정확히 한 번 불러야 한다.
20. 상태 JSON은 v = 2만 받는다.
