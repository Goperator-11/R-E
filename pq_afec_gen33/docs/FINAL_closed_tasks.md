# 최종 루프에서 닫은 과제

F45는 CP-13에 따라 아래 후보 개발·재진입 과제를 최종 루프에서 실행하지 않기로 닫는다. 후보 상태는 미채택으로 남기고, 이미 끝난 구현 검증은 그 범위로 닫는다. 후보 코드·스냅숏·원자료와 옛 과제·상태 파일은 보존한다. 아래 ID를 최종 루프 상태 파일의 새 카드로 등록하지 않는다.

활성 정책은 v3.3.1-dev다. C1은 표준 QUIC에 없는 서버 회신이며, `c1_seen=True` 경로에는 L1 관측과 L3 `record_only` 결정이 남아 있다. `c1_seen=False`의 none 경로와 v3.2-dev 동치 범위는 [활성 정책 명세](V33FIX_policy.md)를 따른다. 아래 성능 수치는 보존된 개발 세계·모형 평가의 인용이며 새 네트워크 측정이나 confirmatory 결과가 아니다. 후보별 비교 기준과 구간은 [미채택 후보 기록](FINAL_rejected_candidates.md), 활성 판의 한계는 [정책 한계](FINAL_policy_limits.md)에 있다.

| 과제 ID | 닫는 이유 | 근거 파일·수치 |
|---|---|---|
| L4 | 격자·prior·hazard를 바꾸는 새 후보라 실행하지 않는다. none 경로를 유지한다는 D41의 범위에서 c1 경로에 새 설계를 넣는 일도 이번 마무리에 포함하지 않는다. | [활성 판 평가 7절](V33FIX_evaluation.md): 개발 세계의 무손실 B3·B4에서 c1의 결정 전 p_mean은 각각 0.000129·0.000212로 수렴했다. 이 두 조건의 결과로 다른 조건의 학습 문제까지 해결됐다고 쓰지 않는다. 옛 L4 카드의 A7-12는 prior 단독 변경의 효과 부재를 지적한다. |
| J2 | 비용 항으로는 결정 불변, c1 등급 경계에 넣는 것은 새 후보라 안 한다. 모든 후보에 같은 처리 상수를 더하는 것과 관측 분류 경계를 바꾸는 것을 구분한다. | `padfec3/decide3.py`의 `decide_core`·`pick`, `padfec3/learn3.py`의 `guard_common`·`guard_excess`·`grade_cutoffs`: none guard는 공통 중앙값을 빼고, c1 등급 경계의 `CLASS_C_PROC_MS`는 3.0 ms다. 목적지별 온라인 추정을 이 경계에 넣으면 우도가 바뀐다. |
| E14·E15·E16 | 미채택 M1 hold 후보의 세계·실제 전송 대조·비용 모형·Go 거울을 다시 평가하는 묶음이다. 이미 남긴 세계 정정과 기능 검증을 보존하고 재진입은 하지 않는다. | [M1 기록](FINAL_rejected_candidates.md#m1)과 [세계 정정](V33FIX_world.md): 원래 개발 세계의 주 비교 120셀은 통과 82, 실패 15, 미확정 23이었다. 세계 결함 외에 trailing=0의 응답 손실 비용 누락도 남아 있어 세계 수정만으로 채택을 주장할 수 없다. `experiments/quicbed/qamp.go`의 `lead-hold` 기본값은 false다. 후보 M1은 F27의 M1 서버 등가·A/A 개발 측정과 별개다. |
| E39 | 옛 L1·L2·J1·J7 none 후보의 B8 쌍안정 진단을 활성 none 경로의 미해결 고착으로 이어 붙이지 않는다. 기존 결과를 보존하고 후보 재판정·seed 제외·새 진단은 하지 않는다. | [최종 감사 CP-13](loop_record/final_audit_2026-11-06/code.final.json)의 W1_raw_v32 읽기 검증: B8_j10·B8_j20의 각 20 seed를 통틀어 p_mean_pre>0.1의 최장 연속 구간은 33연결(seed 47)이었다. [판정 규칙 2.5절](V33FIX_bench_rules.md)의 고착은 100연결 이상 기준과 다른 행동을 고르면서 p_mean_pre>0.1인 경우다. 이 정의에 든 seed는 0이다. 이는 해당 B8 기록의 결과이며 무손실 B3·B4 고착과 구분한다. |
| E41 | J6 margin30을 c1 경로에만 넣어 상태·Go 거울·W1을 다시 평가하는 새 후보라 실행하지 않는다. margin30은 미채택으로 남긴다. | [J6 기록](FINAL_rejected_candidates.md#j6): 개발 세계 c6000에서 J6 c1은 L1 대비 -2.506470 ms였다. 별도 고정 행동 진단에서는 서버 계수를 granular에서 exact로 바꾸자 c6000 p0.08의 J6 행동 (12,0,4)가 L1 행동 (0,2,2)보다 약 +120 ms 느렸다. 후자는 보존 stdout의 반올림 평균 차이며 정밀 차의 원본은 미확인이다. 이 조건 차이를 새 c1 전용 후보의 통과로 해석하지 않는다. |
| E7 | 처리 상수·RTT 보정 뒤 목적지 EPS 적응을 다시 설계하는 선택 과제다. EPS 적응 후보는 미채택으로 남기고 새 설계·W1 재평가를 하지 않는다. | [L2 기록](FINAL_rejected_candidates.md#l2): 개발 세계 none B8_j10의 L1 대비 차이는 -1.568806 ms, 조정 구간 [-4.859306, 1.721694] ms로 비열등 미확정이었다. seed 46 하나의 평균 감소를 일반적인 개선으로 쓰지 않는다. |
| E8 | none 감시와 위험 보정 CUSUM 등을 다시 설계하는 후보 과제라 닫는다. 현재 c1 경로의 `record_only` 결정을 유지한다. | [L3 기록](FINAL_rejected_candidates.md#l3): 개발 세계 c1 B8_j20의 L1 대비 +0.867859 ms, 조정 구간 [0.569639, 1.166079] ms로 비열등에 실패했다. B1 절대 후회 상한 0.127028 ms는 0.1 ms 목표에 미확정이었다. 경보가 없는 c1 경로의 경보 수를 감시 성능으로 해석하지 않는다. |
| E9 | J1의 둘째 왕복 손실 꼬리를 보정하고 다시 평가하는 후보 과제다. J1을 미채택으로 남기고 활성 비용식을 바꾸지 않는다. | [J1 기록](FINAL_rejected_candidates.md#j1): 개발 세계 none B7·B8_j10·B8_j20은 비열등 미확정이고 c1 감소 조건을 충족한 셀이 없었다. B8_j10의 L1 대비 차이는 -1.821025 ms, 조정 구간 [-5.640545, 1.998494] ms였다. |
| E11 | L5의 서버 응답 크기 추정을 새 관측 자료와 wire 계약 위에서 재평가하는 과제라 실행하지 않는다. S 추정·혼합 후보는 미채택으로 남긴다. | [L5 기록](FINAL_rejected_candidates.md#l5): 개발 세계 c12000의 L1 대비 none +24.911063 ms, 조정 구간 [23.775437, 26.046689] ms였다. parity 잘림과 역사 입력 부재가 있었으며, 관측되지 않은 완료 응답을 채워 후보를 재판정하지 않는다. |
| E13 | CP-05 축소 범위에 따라 E38의 진단 계수·크기 시험·상한 표만 F12에서 완료했다. overhead 46 B·wire 크기 고정·정책 필터 변경을 채택하지 않았으므로 J7 성능 재판정도 열지 않는다. | [최종 감사 CP-05](loop_record/final_audit_2026-11-06/code.final.json), [정책의 모형·wire 상한](V33FIX_policy.md), [J7 기록](FINAL_rejected_candidates.md#j7). 39 B 모형과 정책 산술·참조는 F12에서 유지했다. 로컬 보존 `C:/dev/codex_handoff/final/runs/F12_accept.txt`의 CP-05 범위 축소 기록을 따른다. |
| G2 | F13의 조정된 구현 검증 완료로 닫는다. 별도 wire 관문 도구를 만들거나 M1 hold 재진입을 기다리지 않는다. | [F13 검증](FINAL_verification.md): 송신 순서를 유지한 합성 datagram mask 3840행, 복구 원본 반환 누락 변형 검출과 원본 복원 뒤 통과, k=4 배치 검사, F12 wire 크기 검사를 연결했다. Python·Go 원시 JSON 직접 교환, 모든 재정렬, 네트워크 HCT 검증은 이 범위에 포함하지 않는다. 로컬 보존 `C:/dev/codex_handoff/final/runs/F13_accept.txt`. |
| E38 | F12에서 줄인 범위의 완료로 닫는다. `fec_parse_fail`, wire 크기 시험과 모형·wire 안전 상한 표를 반영했다. 원래 W+46+6k 크기 고정 후보는 미채택이며, 정책의 39 B·필터·참조를 유지한다. | [CP-05](loop_record/final_audit_2026-11-06/code.final.json), [크기와 계수 설명](V33FIX_policy.md). `TestParityWireSize`와 `TestFecParseFail`의 F12 검증을 인용한다. `fec_parse_fail`은 PFEC magic 식별 뒤 parse 실패 계수이며 잘림만의 계수가 아니다. 로컬 보존 `C:/dev/codex_handoff/final/runs/F12_accept.txt`. |

옛 과제의 정의와 닫는 범위는 로컬 보존 `C:/dev/codex_handoff/v33/prompt/TASKS.md`의 L4·J2·G2, `C:/dev/codex_handoff/v33/state/EXTRA_TASKS.md`의 해당 E 카드와 대조했다. 수치와 코드 위치의 읽기 검증은 로컬 보존 `C:/dev/codex_handoff/final/runs/F45_verify.py`, `C:/dev/codex_handoff/final/runs/F45_verification.json`에 남긴다. 이번 문서 작업에서 정책 산술·판정 기준·seed·원자료를 바꾸거나 재생·세계 평가를 실행하지 않았다.

## 고정 판정 문서의 범위 정정

DC-18에 따라 [V33FIX 판정 규칙](V33FIX_bench_rules.md) 원문은 수정하지 않는다. 아래 문장은 그 문서 2.4절 끝의 none B8 설명과 2.5절 진단 대상을 한정한다. D51의 기본값인 B6 20 seed 유지와 추가 seed 제안 폐기는 그대로다.

v3.2 none 경로의 B8 20 seed에는 고착이 없다(2026-11-06 재확인). 2.5절 진단은 옛 후보에 대한 것이다.
