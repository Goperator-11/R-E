# policy3 기준 벡터: Go 이식 대조 자료

`g3/policy3_reference.json`은 `padfec3/learn3.py`와 `padfec3/decide3.py`가 내는 답을 고정해 둔 파일이다. Go 쪽 `experiments/quicbed/policy3.go`가 같은 입력에서 같은 결정과 같은 사후분포를 내는지 대조할 때 쓴다(판정 v3 3절 C단계). 측정 자료는 하나도 들어 있지 않다. 궤적의 관측값도 생성기가 모형에서 뽑은 합성값이다.

## 1. 재생성과 확인

```
python -B g3/policy3_reference_gen.py            # 다시 쓴다
python -B g3/policy3_reference_gen.py --check    # 메모리에서 다시 만들어 파일과 비교만 한다
```

- 현재 파일: 6,778,343 B, sha256 `34d90dfb665ca7b12f7e7ce97857def3a9e8c2d21a11f258df4ae254d9a945f1`. `--check` 결과 "identical"(같은 코드로 두 번 생성해 같음을 확인했다).
- 생성 시간은 이 PC에서 약 80초다(결정점 62초, 궤적 18초).
- `sources_sha256`에 생성에 쓴 소스 7개의 해시가 있다. 이 중 하나라도 바뀌면 파일을 다시 만들어야 하고, Go 대조 결과도 다시 내야 한다.
- 시드: 결정점 20261002, J3 원시점 20261003, 궤적 31~34.
- 파일은 줄 단위 JSON이다. 머리 키는 한 줄에 하나, `primitives`와 `decisions`는 한 줄에 레코드 하나, `trajectories`는 한 줄에 궤적 하나다. 실수는 Python `repr`(최단 왕복 표기)로 적었으므로 Go `encoding/json`으로 읽으면 비트가 같다.

## 2. 대조 기준 (판정 3C)

| 묶음 | 수 | 맞춰야 하는 것 |
|---|---:|---|
| `primitives` | 2,000 | `J`, `e`, `p_two_rtt`, `p_fail`, `p_one_rtt` 각각 절대오차 ≤ 1e-9 |
| `decisions` | 6,720 | `action` 정확히 일치, `n_need`, `n_cands`, `cand_hash` 일치, `ej` 절대오차 ≤ 1e-9 |
| `decisions[*].cands` (672개 레코드) | | 후보 순서와 후보별 `ej` (진단용) |
| `trajectories` | 4 × 10,000 걸음 | 걸음마다 결정 `a` 일치, `ej` 절대오차 ≤ 1e-9(콜드는 null), 1,000걸음마다 `post_h`, `w`, `combined`의 상대오차 ≤ 1e-12 |

결정이 갈리면 그 걸음에서도 관측은 기록된 `a`로 넣는다. 그래야 한 번 갈린 것이 뒤의 사후분포 비교까지 오염시키지 않는다.

동점 규칙에는 EJ의 정확한 비교가 들어 있다(4절 7). 수학적으로 같은 EJ를 두 언어가 같은 비트로 내야 결정이 일치하므로, Go 쪽은 Python과 같은 연산 순서를 지키고 곱셈-덧셈 융합(FMA)을 피해야 한다. Go 규격은 명시적 float64 변환이 융합을 막는다고 정하고 있다(https://go.dev/ref/spec#Floating_point_operators).

## 3. 레코드 형식

`decisions[i]`: `k`, `W`, `cert`, `s0_base`, `S`, `rtt`, `u`, `post_kind`(point, mix2, mix4, full), `g`(G 격자 번호 목록), `q`(같은 길이의 가중치), `n_need`, `n_need_cert`, `n_cands`, `cand_hash`, `action`([δ, ℓ, T]), `mode`, `ej`, `jmin`, `n_tied`, 그리고 `id % 10 == 0`이면 `cands`([δ, ℓ, T, ej] 목록, 후보 생성 순서).

- 사후분포는 길이 26 벡터로 펴서 쓴다. `g`에 없는 칸은 0이다. `q`는 정규화했지만 합이 정확히 1이라는 가정은 하지 말고 주어진 값을 그대로 쓴다.
- `S`는 `cert + s0_base + bin_index(k·W)·c_pkt`로 합성한 값이다(gen-2 관문 policy.go L1438-1443과 같은 규약). Go는 `S`에서 `binNeeded`로 n_need를 구한다. `n_need_cert`는 cert에서 직접 낸 값이고 6,720점 모두 `n_need`와 같다.
- `cand_hash`는 후보 생성 순서대로 `"δ,ℓ,T"`를 `;`로 이은 ASCII 문자열의 sha256이다.

`primitives[i]`: `k`, `W_eff`, `m`, `lead`, `p`, `rtt`, `u`, `n_need`와 `layout.evaluate(..., later="v3")`의 결과다. p의 절반은 격자 밖 값이다.

`trajectories[j]`:
- 머리: `id`, `seed`, `cert`, `s0_base`, `k_true`, `W`, `u`, `c_pkt`, `rtt_true`, `schedule`, `action_counts`, `final_stats`.
- `steps`: 길이 10,000인 병렬 배열 `a`, `why`, `ej`, `p_mean`, `rtt`, `hct`(실패면 null), `ok`, `k`, `srv`, `y`, `upd`.
- `snapshots`: 1,000걸음마다 `after_step`, `post_h`(5×26), `w`(5), `combined`(26), `p_mean`, `k_hat`, `S_hat`, `n_need`, `state`(아래 6절의 JSON 상태 전체).

궤적 재생 절차는 다음과 같다. 상태를 새로 만든 뒤 t = 0..9999마다:
1. `d = decide3(state, W, u, steps.rtt[t], c_pkt)`. `d.action == steps.a[t]`, `d.ej ≈ steps.ej[t]`, `d.p_mean ≈ steps.p_mean[t]`를 확인한다.
2. `observe3(state, steps.a[t], steps.hct[t], steps.ok[t], steps.k[t], steps.srv[t], steps.rtt[t])`. 반환한 y와 갱신 여부가 `steps.y[t]`, `steps.upd[t]`와 같아야 한다.
3. (t+1)이 1,000의 배수면 스냅숏과 비교한다.

## 4. 결정 규칙 (decide3.decide_core)

입력: 결합 사후 post(26), k, W, S, u, RTT, c_pkt. 고정값: max_steps 2, m_max 4, max_ips 1452, UDP 상한 1472, J_TIE 0.01 ms, later "v3".

1. `n_need = binNeeded(S, bin_index(k·W), c_pkt)`. gen-2 Go `binNeeded`와 같은 식이다(`learn3.bin_needed_s`).
2. 후보 바탕은 gen-2 Go `levers(k, W, 2, 4, S, c_pkt, 1452)`를 그대로 따른다(`decide3.levers_s`). 순서와 중복 제거 규칙까지 같다. m_max만 3에서 4로 바뀌었다. 이 포팅이 Python `quantum.levers`와 같은지는 시험 `test_levers_port_matches_quantum`이 288개 조합에서 확인한다.
3. 거르기: W_eff > 1452이면 버리고, m > 0이면서 parity(W_eff, k) = W_eff + 39 + 6k > 1472이면 버린다.
4. 선행 수 펼치기: 남은 levers 후보 (mode, m, δ)마다 m = 0이면 (δ, 0, 0) 하나, m ≥ 1이면 ℓ = 0, 1, ..., m 순서로 (δ, ℓ, m-ℓ)를 만든다. 같은 (δ, ℓ, T)가 다시 나오면 처음 것만 남긴다. mode는 levers의 것을 물려받는다.
5. 기대 비용: `EJ(a) = Σ_g post[g]·J3(a | G[g])`. g는 0부터 차례로 더하고 시작값은 0.0이다. post[g] == 0인 칸은 건너뛴다(더해도 비트가 같다).
6. J3는 `layout.evaluate(k, W_eff, m, ℓ, p, RTT, u, n_need, "v3")["J"]`다. 응답 직렬화 항은 τ(W_eff)다.
7. 고르기: jmin = min EJ. EJ ≤ jmin + 0.01인 후보를 동점으로 모으고, 아래 키가 가장 작은 것을 고른다.
   `(added, m>0이면 0 아니면 1, mode 문자열, ℓ == legacy(m)이면 0 아니면 1, EJ, ℓ, m, δ)`
   - added = max(0, k·W_eff + m·parity(W_eff,k) − k·W).
   - legacy(m) = 1 (m ≥ 2), 0 (m ≤ 1).
   - 앞의 세 성분이 gen-2 `_tie_key`다(late_parity, over_mtu는 거르기 뒤에 항상 같은 값이라 뺐다). 그 뒤 성분은 v3에서 새로 정한 것이다(8절 6).

## 5. 학습 규칙 (learn3.observe3)

상수: G = table.py P_VALS 26점, H = (1/30, 1/100, 1/300, 1/1000, 1/3000), ε = 0.01, 가중치 하한 1e-6, k 창 16, S 창 16, 팔별 HCT 창 32, 기준선 최소 관측 8, 사건 문턱 0.5·RTT, 차폐 RTT 200 ms, 명목 2-RTT 문턱 e(a,0) ≥ 0.5.

`observe3(state, a, hct, ok, k_obs, srv, rtt; W, u, c_pkt)`:
1. 문맥: k̂ = 최근 16개 k의 최빈값(동률이면 가장 최근에 나온 값), Ŝ = 최근 16개 S의 중앙값(짝수 개면 가운데 둘의 평균). 둘 중 하나가 없거나, k̂가 1..4 밖이거나, rtt ≤ 0이면 문맥이 없다. 문맥이 있으면 n_need = binNeeded(Ŝ, bin_index(k̂·W), c_pkt).
2. 기준선 b:
   - 팔 a의 창에 8개 이상 있으면 b = 그 창의 중앙값.
   - 아니면(문맥이 있을 때만) 창에 8개 이상 있는 팔 가운데 관측이 가장 많은 팔 r을 고른다. 동률이면 가장 최근에 관측을 넣은 팔이다. b = median(r의 창) + J3_a(p=0) − J3_r(p=0). 계산 순서는 (median + J3_a) − J3_r이다.
   - 둘 다 안 되면 b는 없다.
3. y: b가 있고 rtt > 0이면 `y = 1 if (not ok) or (hct − b ≥ 0.5·rtt) else 0`. 그렇지 않으면 y는 없다.
4. 사후 갱신은 y와 문맥이 모두 있고 차폐가 아닐 때만 한다. 차폐는 rtt ≥ 200이면서 e(a, p=0) ≥ 0.5인 경우다. 차폐 관측은 사후와 가중치를 전혀 바꾸지 않는다(hazard 혼합도 하지 않는다).
5. 사건 확률: e(a,0) ≥ 0.5인 팔(명목 2-RTT)은 e_learn = p_fail, 나머지는 e_learn = layout의 e = p_two_rtt + p_fail. 우도는 L1 = (1−ε)·e_learn + ε·(1−e_learn), L0 = 1 − L1.
6. 필터(`learn3.filter_step`), H 순서대로:
   ```
   prior[i] = (1 - h)*post_h[i] + h*(1.0/26)
   z_h      = Σ_i prior[i]*L[i]            (i 순서, 시작 0.0)
   post_h[i]= prior[i]*L[i]/z_h
   raw_h    = w_h*z_h
   s = Σ raw ; w_h = raw_h/s ; w_h = max(w_h, 1e-6) ; s2 = Σ w ; w_h = w_h/s2
   ```
   결합 사후는 `combined[i] = Σ_h w_h·post_h[i]`(h 순서, 시작 0.0), 사후평균은 `Σ_i combined[i]·G[i]`다.
7. 넣기: ok일 때만 넣는다. k_obs ≥ 1이면 k 창에, hct는 팔 a의 창에 넣고, 그 팔의 최근 순번을 갱신한다. y ≠ 1이고 srv > 0이면 S 창에도 넣는다. y가 없을 때(분류 전)도 S를 넣는다. 그래야 첫 연결 뒤에 콜드를 벗어난다. 실패 연결(ok 거짓)은 y = 1로 갱신에는 쓰지만 어느 창에도 넣지 않는다.

## 6. decide3와 상태

`decide3(state, W, u, rtt, c_pkt)`:
- S 창이나 k 창이 비어 있으면 b0 = (0, 0, 0)을 돌려준다. `why = "cold"`, `ej = null`. 첫 연결만 해당한다.
- k̂가 1..4 밖이면 b0(`why = "k_range"`), rtt ≤ 0이면 b0(`why = "no_rtt"`).
- 나머지는 `decide_core(combined(state), k̂, W, Ŝ, u, rtt, c_pkt)`. 결과에 `p_mean`, `p_map`, `p_ge_010`(p ≥ 0.10 질량)을 붙인다. 클라이언트 행에는 action, ej, p_mean을 남기면 된다.
- rtt는 learn3 밖에서 정한다. 재생기(`experiments/replay_g3.py` RttTrack)는 gen-2 policyRTT와 같은 규칙을 쓴다: 유효 ACK RTT 표본이 하나라도 있으면 그 최소값, 없으면 성공 연결 HCT의 최소값.
- JSON 상태(`DestState3.to_json`): `v`(1), `k_hist`, `S_hist`, `hct`({"δ,ℓ,T": [...]}), `hct_seq`({"δ,ℓ,T": 순번}), `seq`, `post`(5×26), `w`(5), `stats`. `-cache3` 파일은 목적지 주소를 키로 이 객체를 담으면 된다.

## 7. 생성기가 만드는 것

결정점 6,720개는 판정 3C 격자의 문맥을 빠짐없이 한 번씩 쓴다: k 1..4 × W {1200, 1280, 1350} × cert 14개 {1000, 2308, 3000, 3200, 4032, 5609, 5800, 6500, 8000, 9000, 10800, 12000, 14000, 16000} × s0_base {382.45, 1472.0} × RTT {10, 50, 100, 200} × u {0, 2, 5, 10, 100}. 순서는 시드로 섞었다. 문맥마다 사후분포 종류를 70/15/10/5% 확률로 뽑았다.
- point(4,713개): 26점 중 하나에 질량 1.
- mix2(1,015개), mix4(654개): 무작위 2점, 4점에 무작위 가중치.
- full(338개): 26점 전부에 무작위 가중치.

결과: 고른 행동이 159종류다. 동점 후보가 둘 이상인 결정이 1,293개라 동점 규칙이 많이 쓰인다. 그중 933개는 p ≤ 0.03에 질량이 몰린 점 사후분포다. gen-2 배치와 다른 선행 수를 고른 결정이 5,849개다. mode는 parity 5,605, combo 987, none 108, pad 20이다.

궤적 4개는 합성 관측으로 만든 것이다. 걸음마다 그 걸음의 참 손실률 p에서 `layout.evaluate`가 주는 1-RTT, 2-RTT, 실패 확률로 결과를 뽑는다. HCT는 그 결과에 맞는 왕복 수에 결정 전 직렬화 시간과 흔들림(성공 0~2 ms, ACK 실패 0~5 ms)을 더한 값이다. 실패는 30%를 PTO(RTT + 200.86), 나머지를 ACK 경로(1.125·RTT + 1.424 추가)로 둔다. 0.1%는 HCT를 0.6배로 줄인 낮은 이상값, 0.05%는 연결 실패(hct null)다. k는 1%의 확률로 하나 다른 값이 된다(k = 1이면 위쪽으로만 바뀌어 0.5%). 정책 RTT는 rtt_true + 0.5~8 ms 표본의 누적 최소다.

| 궤적 | 조건 | 손실 일정 | 고른 행동(횟수) | 갱신 / 차폐 / 사건 |
|---|---|---|---|---|
| T1_bigcert | cert 16000, ML-KEM, k 2, u 2, RTT 50 | 2% 450 ↔ 15% 450 | (0,3,1) 8,617, (0,0,4) 1,382, b0 1 | 9,991 / 0 / 1,626 |
| T2_rtt200 | cert 9000, k 2, u 2, RTT 200 | 같음 | (0,2,2) 9,069, (0,1,3) 930, b0 1 | 9,991 / 0 / 202 |
| T3_x25519_unlimited | cert 4032, x25519, k 1, u 0, RTT 50 | 0% 700, 5% 300, 1% 500 | (1,0,4) 9,999, b0 1 | 9,991 / 0 / 3 |
| T4_shielded_rtt200 | cert 30000, k 2, u 5, RTT 200 | 2% ↔ 15% | (0,0,4) 9,999, b0 1 | 0 / 9,991 / 0 |

- T3는 판정 2.6의 약점 7(무손실 과잉 보호)을 그대로 보여 준다. 업링크 0에서는 바이트가 공짜라 (1,0,4)를 고르고, 이 팔의 사건 확률은 p 격자 전체에서 최대 0.00243(p = 0.30)이라 관측이 정보를 거의 주지 않는다. 사후평균이 10,000걸음 동안 0.123에서 0.101로만 내려간다.
- T4는 cert 30000이라 1-RTT가 되는 행동이 없다. RTT 200에서 모든 관측이 차폐되므로 사후가 사전(평균 0.1378)에 그대로 머문다. 차폐 경로를 Go에서 대조하려고 넣었다.

## 8. 판정 문구와 다르게, 또는 판정에 없던 것을 내가 정한 곳

1. 사건 확률. 판정 2.4의 의사코드는 우도에 2.3의 e = p_two_rtt + p_fail을 쓴다. 그런데 관측 y는 그 팔 자신의 중앙값 기준선에서 0.5 RTT를 넘었는지라서, 명목 2-RTT 팔에서는 "실패"만 사건이 된다. e를 그대로 쓰면 그런 팔의 우도가 p와 무관해진다. 큰cert 2 Mbps의 m1은 1-RTT가 될 수 없어 모든 p에서 e = 1이고, 실패 확률은 2%에서 0.0012, 15%에서 0.061로 갈린다. learning 안 3절(약점 1)은 큰cert 재생 이득의 기제를 바로 이 사건률 차이로 설명한다. 그래서 learning 안 2.2절(재생 근거를 만든 정의)대로 명목 2-RTT 팔은 p_fail, 나머지는 e를 쓴다. 명목 판정은 판정 2.4 차폐 조건과 같은 e(a,0) ≥ 0.5다.
2. 차폐. 판정 의사코드는 "L = 1"이지만 그렇게 하면 hazard 혼합 한 걸음이 사후를 움직인다. 판정 B단계 시험 목록의 "차폐 팔이 사후를 바꾸지 않음"과 시제품(replay.py)을 따라 차폐 관측은 갱신을 아예 건너뛴다.
3. 응답 직렬화 항은 τ(W_eff)다. 판정 2.3 문구는 τ(W)이지만, 봉인된 `layout.py`가 τ(W_eff)를 쓰고 이번 과제가 J3를 그 파일에서 가져오고 메모 키를 W_eff로 두라고 했다. δ = 0이면 둘이 같다.
4. decide3는 s0_base를 받지 않는다. gen-2 Go decide처럼 n_need를 Ŝ에서 binNeeded로 구하므로 쓸 곳이 없다. 받기만 하고 안 쓰는 인자를 두면 c_pkt = 0.0 함정과 같은 종류의 조용한 오답 통로가 된다고 봤다. s0_base는 기준 벡터 생성기가 cert에서 S를 합성할 때만 쓴다.
5. 실패 연결과 S 창. 판정 2.4 의사코드는 y == 0일 때만 S를 넣는다. 그대로 두면 b0 팔의 HCT가 8개 쌓여 자기 기준선이 생기는 9번째 연결에서야 첫 y = 0이 나오므로, 콜드 b0가 9연결 이어진다(시뮬레이션으로 확인). 판정 2.5와 2.6은 "첫 연결만 b0"라고 정했으므로 그 의도를 따라 y ≠ 1이면(분류 전 포함) 넣는다.
6. 동점 키 뒷부분. gen-2 동점 규칙은 선행 수를 모른다. 바이트, m>0, mode가 같은 후보끼리는 gen-2 배치(ℓ = legacy)를 먼저, 그다음 EJ, ℓ, m, δ 순으로 정했다. 0.01 ms 안의 차이로 gen-2 배치에서 벗어나지 않게 하려는 것이다.
7. 중앙값은 짝수 개일 때 가운데 둘의 평균이다. 시제품은 위쪽 중앙값을 썼다.
8. 기준선을 옮겨 올 팔이 여럿이면 관측 수, 다음으로 최근성으로 고른다. 시제품은 사전 삽입 순서였다.
9. 가중치 하한은 정규화 → 하한 적용 → 다시 정규화 순서다. 그래서 하한에 걸린 가중치는 1e-6보다 아주 조금 작을 수 있다. 시제품에는 하한이 없었다.
10. k̂가 1..4 밖이거나 rtt ≤ 0이면 b0를 고른다. gen-2 Go는 k ≥ 5에서 panic한다.
