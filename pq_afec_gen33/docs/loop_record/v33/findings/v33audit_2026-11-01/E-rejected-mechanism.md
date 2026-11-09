# E-rejected-mechanism

## summary
이 갈래의 8개 과제는 활성 정책을 바꾸지 않았다. 활성 정책은 L1 상태4 그대로이고 -lead-hold 기본값은 off다(qamp.go:3722). 그래서 배포 동작 기준으로는 v3.2-dev보다 나아진 것이 없다. 남은 것은 비활성 참조 구현, 기본 off인 Go 보류 수신기, 평가 도구의 결함 두 가지를 찾아낸 기록이다.

M1의 "82통과·15실패·23미확정, hold 세계의 패리티 직접 송신 재개 차이 결함"은 이런 뜻이다. 동결 worldsim_m1.py의 m1_outputs는 패리티 token이 스택에 들어가도 서버 송신을 다시 시작시켰고, off 경로는 신용만 더했다. quic-go v0.61.0은 처리된 패킷이 없는 수신에서는 송신하지 않으므로(connection.go 663~671행, 직접 확인) off 쪽이 맞다. 이 결함은 세계 쪽에 있고 Codex의 판단이 옳다. 다만 원인이 세계 하나만은 아니다. Codex 원자료(B2, p=0.25 구간)를 다시 세어 보니 M1 후보가 (0,4,0)을 56.7% 골랐고 평균 HCT는 154.92 ms였다. 같은 구간에서 (0,3,1)은 108.11 ms였다. 후보 비용 모형은 (0,4,0)을 102.61 ms로 보지만, 결함을 한 줄 고친 세계에서는 148.66 ms가 나왔다. trailing이 0인 행동은 둘째 왕복 응답에 XOR 보호가 없어 PTO 꼬리(329/3000, 평균 521.7 ms)를 맞는데, 비용 모형이 이를 반영하지 않는다. 그러니 실패는 세계 결함과 후보 결함이 겹친 결과다.

같은 한 줄 수정으로 세계를 고쳐 다시 돌렸다(scratch 사본, seed31, 큰cert 문맥). 보류의 이득은 남았다. p=0.15에서 off 최선 109.78 ms가 hold 최선 101.91 ms로, p=0.25에서 130.32 ms가 122.17 ms로 줄었다. p=0.02에서는 82.45 ms가 83.09 ms로 늘었다. lead=0 행동은 off와 정확히 같았다.

Go hold.go는 계약대로 구현돼 있고, WSL 임시 사본에서 hold 관련 Go 시험 25개가 통과했다. 설계 쪽 쟁점은 셋이다. 기한에 쓰는 업링크를 세계에서는 문맥별 참값으로 넣는다. 결정이 마지막 원본 시점에 열려 선행 패리티를 먼저 써 버린다. 복구 불가 비행의 보관 패리티는 TTL에 폐기돼 신용으로도 쓰이지 않는다.

O2·J5·O3·O4·J3·M4·J8의 blocked는 대부분 실제 장애(송신 전 훅 부재, RTT 소유권 관측 부재, J3 실패 비용·J7 크기 상한 미해결)에서 나왔다. 그래도 일부는 작업 분해 문제다. 루프 규칙(2-2)은 partial이 3번이면 blocked로 돌리고, EXTRA 과제는 실행 순서에 없어 선택되지 않는다. 그 결과 의존이 W1뿐이고 75분짜리인 E14(M1 세계 수정)가 루프가 끝날 때까지 todo로 남았다. J5의 B10 개선 기준은 m≤4 안에서 구조적으로 달성할 수 없다.

직접 확인한 결과 스크립트·출력은 C:\Users\scien\AppData\Local\Temp\claude\C--Users-scien\98dad099-940c-4208-8359-61078035dc93\scratchpad\v33audit\E-rejected-mechanism\ 아래에 있다(m1_model_check.py, m1_pattern_diff.py, m1_wait_rule.py, run_world.py, p15_compare.txt, p02_p25_b7_compare.txt, m1_actions.py, m1_class.py, j5_ge_check.py, b10_actions.py, pkg_orig·pkg_fix 세계 사본). 저장소는 손대지 않았다.

## verdict_improved
배포 동작 기준으로는 발전하지 않았다. 이 갈래에서 채택된 후보가 없고 활성 정책은 L1 상태4, -lead-hold는 off다. 연구 역량 기준으로는 일부 발전했다. 핵심 후보인 M1은 Go 구현과 와이어 대조가 단단하고, 세계 결함을 고친 내 scratch 재계산에서도 p=0.15·0.25에서 약 8 ms 이득이 남았다. 다만 이 값은 감사 기대치(약 10 ms)와 모형값(12.88 ms)보다 작고, p=0.02에서는 약 0.6 ms 손해다.

blocked의 정당성은 과제마다 다르다. O3·O4·M4는 송신 전 훅과 RTT 소유권 관측이 없어서 막혔으니 정당하다. O2와 J3는 다른 과제의 결함(J3 실패 비용, J7 크기 상한)과 표본 부족에 걸린 부정·의존 결과다. J5는 B10 기준이 구조적으로 달성 불가능하므로 blocked보다 부정 결과로 닫는 것이 맞다. J8은 카드가 '모형만'이었는데 p_d 항을 비워 두었으니 범위를 부풀린 쪽이다. M1은 blocked 자체는 맞지만, 원인을 세계 쪽으로만 돌렸고 후보 비용 모형의 결함(순수 선행 행동의 둘째 왕복 꼬리)을 놓쳤다.

작업 분해에도 문제가 있었다. 루프 규칙상 partial이 3번이면 blocked가 되고 EXTRA 과제는 선택되지 않아, 가장 가치 있는 다음 단계인 E14(의존 W1만, 75분)가 끝까지 실행되지 않았다. 과제 8개에서 후속 E 과제 22개가 생겼고 대부분 Go 거울과 전체 W1 관문을 완료 조건으로 달고 있어, 같은 구조로는 다음 밤에도 done이 나오기 어렵다.

## frame_fit
대체로 연구 틀(증폭 예산을 패리티로 산다)에 맞는 방향이다. M1은 볼트의 '쓰면 안 되는 말'인 '같은 바이트가 신용과 복구를 함께 산다'를 성립시키려는 기제로, 이번 신규성 주장의 중심에 직접 닿는다. Go 참조 경로에서 미사용 패리티는 신용으로, 쓴 패리티는 원본 크기의 신용과 복구로 작동하는 것을 보였다. 그래도 측정 셀 결과가 아니므로 그 문장은 여전히 쓸 수 없다.

M4(토큰·Retry로 주소가 검증되면 신용 가치 0)와 J8(서버가 신용을 세는 방식, granular/exact, 선행 신용 여부)은 '패리티가 언제 예산을 사는가'를 정하는 조건이라 틀에 정확히 맞는다. O2(u는 선행 바이트의 직렬화 비용)와 O4(k는 신용 계산의 바탕)도 틀 안에 있다. J5·J3·O3는 복구와 학습 쪽 보조 과제라 틀과의 거리가 더 멀다.

틀에 대한 위험은 둘이다. 첫째, M1은 PAD-FEC를 이해하는 서버(보류 복호기)가 있어야 하고, 변경 없는 서버에서는 신용 쪽만 남는다. 둘째, 보류 기한을 계산하려면 서버가 클라이언트 업링크 값을 알아야 하는데(D20 고정 2000 kbps), 배포에서는 새 가정이 된다. 보고서에는 이 두 단서를 붙여야 한다.

## errors

### E-M1-1 [high] M1 실패 원인을 세계 결함으로만 돌렸다. 후보 비용 모형도 고손실 순수 선행 행동을 크게 과소평가한다 (repro=True)
M1_stage3_result.md와 M1_world_validity.md는 120셀 실패의 원인을 hold 세계의 패리티 직접 flush로만 설명한다. Codex 원자료를 다시 세면 B2의 p=0.25 구간에서 M1 후보는 (0,4,0)을 56.7% 골랐고, 그 행동의 평균 HCT가 154.92 ms로 (0,3,1)의 108.11 ms보다 나빴다. (0,4,0)에는 trailing 패리티가 없어 flush 결함의 덕을 보지 않는다. 결함을 고친 세계에서도 (0,4,0)은 148.66 ms로 (0,3,1) 122.17 ms보다 나쁘다. 그런데 후보 모형(hold_layout, baseline response_term·실패 비용 상속)은 (0,4,0)을 102.61 ms로 본다. 원인은 둘째 왕복이다. 세계는 trailing>0일 때만 응답 XOR('V')을 붙이므로 순수 선행 행동은 응답 손실에 노출되는데, 비용 모형에는 이 차이가 없다. 따라서 E14(세계 수정)만 해서는 M1 후보가 통과하지 못한다.

EVIDENCE: 직접 확인: m1_actions.py로 runs\M1_factorial_raw_v1\hold_m1_c1_B2 phase1 집계 결과 (0,4,0) 5099/9000, 평균 154.92 ms, (0,3,1) 3526, 108.11 ms. hold_l1_c1_B2는 (0,0,4) 68.3%, 103.88 ms. m1_model_vs_world.py: 스냅숏 M1_v1 layout.evaluate(lead_hold=True)의 p=0.25 값이 (0,4,0) 102.61, (0,3,1) 110.92 ms. m1_class.py(수정 세계, 3000연결): (0,4,0) p25 평균 148.66 ms, tail 329건 평균 521.7 ms. response_xor=False로 바꾸면 (0,3,1)도 170.88 ms로 나빠진다. worldsim_m1.py send_post_big_probes의 'V'는 action.trailing일 때만 보낸다.

FIX: E16 전에 비용 모형에 trailing=0 행동의 응답 비보호와 둘째 왕복 손실 꼬리를 넣고(J1 범위와 연결), M1 처분 문서에 실패 원인을 세계 결함과 후보 모형 결함으로 나눠 적는다.

### E-M1-2 [medium] lead=0이면 hold와 off가 같아야 한다는 불변식을 시험하지 않고 2864초 MC와 120셀 평가를 돌렸다 (repro=True)
선행 패리티가 없으면 보류할 것이 없으므로 hold 세계와 off 세계의 HCT는 같아야 한다. 동결 세계는 이 불변식을 크게 어긴다. Codex의 사전 검사는 'off 경로가 W0의 56 trace를 재현'하는지만 봤고, 이 불변식은 120셀 평가가 끝난 뒤에야 최소 재현으로 발견했다. 사전에 한 줄짜리 회귀 시험만 있었어도 2864초 MC와 4200실행 평가가 결함 있는 세계에서 돌지 않았을 것이다. 세계 파일(worldsim_m1.py)은 같은 M1 과제에서 Codex가 직접 쓴 것이다.

EVIDENCE: 직접 확인: run_world.py, 큰cert, p=0.15, seed31, 3000연결에서 (0,0,4)는 off 122.554 ms, 동결 hold 88.259 ms, 수정 hold(m1_outputs의 flush 조건에 token == "o" 추가) 122.554 ms였다. p=0.02와 p=0.25, B7 문맥의 (0,0,4)도 off와 수정 hold가 소수점까지 같았다. 손실0·trailing3/4 최소 재현은 117.96 / 78.812 / 117.96 ms로 Codex 값과 같다. 근거 코드는 worldsim_m1.py 718~734행(모든 token 뒤 flush_server)과 off 경로의 'P' 처리(준비 뒤 credit만).

FIX: E14의 회귀 시험에 '모든 lead=0 행동에서 off·hold의 HCT와 서버 송신 목록이 같다'를 넣고, 앞으로 세계 판본을 바꿀 때마다 성능 계산 전에 돌린다.

### E-M1-3 [medium] M1 세계의 보류 수신기에 문맥별 참 업링크를 넣었다(서버 쪽 업링크 오라클) (repro=False)
실제 서버는 클라이언트 업링크를 모른다. Go 서버는 D20에 따라 고정 2000 kbps를 쓴다. 그런데 worldsim_m1은 수신기 기한에 각 문맥의 참 uplink_mbps를 넣는다. W1에서 u≠2인 손실 셀은 B10(u=0, p=0.15 GE), B12_c6000(u=10), B12_c12000(u=5)이고, 이 셀들의 hold 평가는 배포 설정과 다른, 유리한 기한으로 계산됐다. 평가 계획은 이를 '명시 입력'이라고만 적었고 오라클이라는 점이나 오지정 민감도는 다루지 않았다. 10-29 감사 처방 (6)은 정책 쪽 업링크 오라클 제거였는데, M1이 서버 쪽에 새 오라클을 들여왔다.

EVIDENCE: 코드 확인: worldsim_m1.py 708~711행 Receiver(..., round(context.uplink_mbps * 1000), ...), qamp.go 3723행 -lead-hold-uplink-kbps 기본 2000, DECISIONS_NEEDED.md D20, g3\v33\bench_protocol.json의 B10·B12 uplink 값. 영향 크기는 재지 않았다.

FIX: 세계 수신기에 D20 고정값을 넣은 팔과 실제 업링크를 2배·1/2배로 틀리게 준 팔을 E14 계획에 넣는다.

### E-M1-4 [low] 2% 손해 0.80 ms의 원인을 진단하지 않았고, 비교 상한을 카드보다 6배 느슨하게 잡았다 (repro=True)
m1_fixed_checks.py의 nominal_deadline_bound는 첫 비행 전체 직렬화 + 1 ms = 32.536 ms다. 카드의 검증자 단서는 데이터그램 하나(2 Mbps에서 5.324 ms)였다. 0.80 ms는 두 상한을 모두 지키므로 결론은 같다. 다만 손해의 거의 전부(+0.900 ms)는 한 가지 패턴에서 나온다. 선행 3개·원본1만 도착하고 원본0이 손실, 뒤 패리티 도착인 경우다. 마지막 원본이 오는 순간 결정이 열려, 5.3 ms 뒤에 올 뒤 패리티를 기다리지 않고 선행 패리티를 복구에 써 버린다. 그러면 신용이 6553 B에서 5222 B로 줄어 2-RTT가 된다. 이것은 카드가 정한 결정 규칙의 비용이며 deadline 비용과는 다르다.

EVIDENCE: 직접 확인: m1_pattern_diff.py, 패턴 (1,1,1,0,1,1)에서 off t_dec 26.416 ms·신용 6553 B·HCT 76.416 ms, hold t_dec 21.092 ms·신용 5222 B·HCT 126.212 ms. m1_wait_rule.py의 근사('뒤 패리티가 예정돼 있으면 첫 뒤 패리티나 기한까지 선행 사용을 미룸'): p=0.02에서 80.096→79.207 ms(off 79.292보다 낮음), p=0.15에서 100.308→97.460 ms. 16행동의 p=0.02 최대 손해는 (0,3,1)의 0.804 ms다.

FIX: 결정 규칙 변형(뒤 패리티를 기다리는 대기)을 후보로 미리 고정하고 E16에서 원래 규칙과 비교한다. 2% 손해 표에는 데이터그램 하나 기준도 함께 적는다.

### E-M1-5 [low] 복구할 수 없는 비행의 보관 선행 패리티는 TTL에 폐기돼 신용으로도 쓰이지 않는데, 비용 모형에 반영되지 않았다 (repro=False)
결정이 열렸는데 심볼이 모자라면 보관을 계속하고, 1초 TTL에 폐기한다. 클라이언트가 재전송하는 원본은 CRC가 달라 이 비행에 붙지 않는다. 그래서 off에서라면 도착 즉시 계상됐을 선행 바이트가 hold에서는 끝내 신용이 되지 않는다. hold_layout의 실패 비용 식은 신용과 무관하게 계산하므로 이 손실이 빠져 있다. 보류에서 복구 불가 확률은 아주 작아(예: (0,3,1) p15에서 0.0004) 수치 영향은 작다고 본다.

EVIDENCE: 코드 확인: decoder_index.go 338~342행(TTL 사건에서 holdDiscardLocked "expired"), hold.go 152~155행(missing > symbols이면 계속 보관), hold_layout.py 120~128행.

FIX: 재전송 원본으로 CH가 완성되는 등 복구 불가가 확정되면 보관 패리티를 스택에 넘기는 규칙을 검토하거나, 실패 가지 비용에 신용 손실을 넣는다.

### E-J8-1 [medium] J8이 찾은 W0 서버 PTO 재무장 오류가 기존 W1 판정(B7 등)에 미치는 영향을 재지 않았다 (repro=True)
J8은 W0의 arm_server_pto가 '재무장 시각 + PTO'를 쓰고, flush나 신용 해제 때마다 다시 호출된다는 점을 정확히 찾았다. quic-go는 마지막 ack-eliciting 송신 시각을 기준으로 한다. 이 오류는 하향 손실이 있는 W1 셀(B7, s2c 1%)과 M1 hold 세계(flush가 더 잦다)의 서버 재전송 시각을 늦춘다. M1의 B7은 off 기준선 세 개 모두에 대해 4.2~5.6 ms로 실패했고, L1·J1의 B7 판정도 같은 세계에서 나왔다. J8은 E34로 넘기기만 했고 기존 판정의 영향 범위는 표시하지 않았다. all_sent·(0,3,1)·S18231의 HCT 10167~12204 ms도 원인을 밝히지 않은 채 남았다.

EVIDENCE: 코드 확인: worldsim.py 624~629행과 644·651·936·948행의 arm_server_pto(time), quic-go@v0.61.0 internal/ackhandler/sent_packet_handler.go getPTOTimeAndSpace(lastAckElicitingPacketTime + PTO). J8_downlink_result.md의 44건, 최대 192.184 ms. 직접 측정(수정 세계, B7 문맥, 6000연결): hold−off는 (0,1,3) +1.05 ms, (0,1,1) +0.88 ms로, flush 결함만으로는 설명되지 않는 B7 손해가 남는다.

FIX: E34 이전에, 기존 W1 판정 가운데 서버 PTO 사건이 있는 연결의 비율과 B7 판정이 바뀌는지를 별도 진단으로 표시한다.

### E-J5-1 [low] J5의 B10 개선 기준은 m≤4 안에서 구조적으로 달성할 수 없는데, 후속 E23이 같은 기준을 다시 걸었다 (repro=True)
B10에서는 폐루프 L1이 이미 (0,0,4)를 97.8%(c1), 99.9%(none) 고른다. (0,0,4)는 k=2, m≤4에서 보호가 가장 큰 행동이다. GE를 알면 결정은 더 보호적인 쪽으로만 움직이므로 B10 HCT를 줄일 행동이 남아 있지 않다. Codex는 '구조적으로0'이라고 썼지만 E23의 완료 기준에 'B10 감소'를 그대로 넣었다. J5는 'GE 모형은 비용 예측을 맞추지만 W1 결정 가치는 0'이라는 부정 결과로 닫는 편이 맞다.

EVIDENCE: 직접 확인: b10_actions.py로 runs\M1_factorial_raw_v1\off_l1_c1_B10 (0,0,4) 0.978, off_l1_none_B10 (0,0,4) 0.999. J5_world_result.md에서 iid·known_burst·forced_burst3 모두 B10 (0,0,4). EXTRA_TASKS.md E23 완료 기준에 'B10 감소'가 있다.

FIX: E23의 B10 기준을 M2(송신 순서)나 M3(m>4)와 묶거나, J5를 부정 결과로 기록한다.

### E-J3-1 [low] J3의 2% 고정 팔 ±10 ms '미통과'는 실패 표본 5건에 근거한다 (repro=False)
2% 층의 실패 대용은 2,250연결 중 5건이다. 5건 평균(288.3458 ms)으로 ±10 ms 기준을 판정하는 것은 통계적으로 의미가 없으므로 '판정 불능'이 맞다. Codex는 표본 수를 함께 적었지만 표에는 '미통과'로 남겼다. 15% 층(130건)의 +1.55 ms 통과와 같은 무게로 읽히면 안 된다.

EVIDENCE: Codex 문서: docs\J3_reference_result.md 표와 본문의 '2%에서5/2,250, 15%에서130/2,250'.

FIX: 표의 판정 열에 표본 수 기준(예: 실패 30건 미만이면 판정 불능)을 미리 정해 적용한다.

### E-J8-2 [low] J8 카드는 '모형만'이었는데 하향 손실 p_d 항을 J=None으로 남긴 채 blocked 처리했다 (repro=False)
카드가 요구한 것은 서버 프로파일, 하향 손실 p_d 항을 넣은 J3, 결정 표였다. Codex는 W0의 타이머가 틀렸다는 이유로 p_d>0이면 J=None을 반환하게 했다. W0의 결함은 실제로 있지만, 모형 항 자체는 W0 대조와 분리해서 구현하고 '세계 대조 미완'으로 표시할 수 있었다. 그 결과 카드의 모형 산출물이 비어 있다.

EVIDENCE: Codex 문서: docs\J8_server_cost_contract.md의 '하향 손실 p_d가 양수면 현재 단계는 J=None, cost_complete=false'. TASKS.md J8 카드의 '(60분, 모형만)'.

FIX: p_d 항을 RFC 9002 기준 타이머로 구현해 비활성 참조로 두고, W0·E34 대조는 별도 관문으로 남긴다.

## changes
- M1: experiments\quicbed\hold.go(451행) 새 파일. decoder_index.go에 hold 타이머 heap, qamp.go에 -lead-hold(기본 false), -lead-hold-uplink-kbps(기본 2000), -lead-hold-margin(1 ms) 플래그를 추가했다. 와이어 형식은 바뀌지 않았다.
- M1 Go 시험 파일 qamp_hold_test.go(670행), qamp_hold_path_test.go, qamp_hold_quic_test.go를 추가했다.
- M1 Python 파일: hold_decoder.py, hold_layout.py, hold_reference.py, hold_wire_reference.py, worldsim_m1.py(1045행), world_receiver_m1.py, worldparams_m1.json, bench_m1*.py, validate_m1*.py, m1_fixed_checks.py, oracle_m1.py를 추가했다. 정책 스냅숏 g3\v33\policy_snapshots\M1_v1(상태10 후보, 비활성)도 만들었다.
- O2: uplink_reference.py(U={0,2,5,10,20,50} minimax-regret, MinRTT 회귀 추정기), uplink_reference_report.py, uplink_world_diagnostic.py를 추가했다.
- J5: ge_reference.py(2상태 forward 재귀, Beta 사전 L 추정), ge_reference_report.py, ge_world_diagnostic.py를 추가했다.
- O3: rtt_reference.py(RTT_ALPHA=VAR_ALPHA=0.25, 변동 4배 여유), rtt_reference_report.py, rtt_trace_audit.py를 추가했다.
- O4: natural_k_reference.py, natural_k_report.py, natural_k_revisit.py, current_k_candidate.py, current_k_replay.py를 추가했다.
- J3: recovery_reference.py(두 단계 실패 비용), recovery_world.py(별도 전송 세계), recovery_trace.py를 추가했다.
- M4: revisit_reference.py, revisit_cache.py, revisit_capture.py와 smoke 파일들, Go revisit_guard.go를 추가하고 revisit.go와 qamp.go를 수정했다(commit 1003e14ff, 기본 off 고정 팔). docs\server_support_signal.md 설계 메모를 썼다.
- J8: server_profile.py(granular/exact/unlimited, required_credit, 재전송 예산), server_cost_reference.py, server_world_trace.py, server_response_observer.py를 추가했다.
- 문서: docs 아래 M1_* 7개, O2_* 4개, J5_* 4개, O3_* 4개, O4_* 7개, J3_* 7개, M4_* 6개, J8_* 4개.
- 이 갈래의 커밋은 padfec3·padfec·afec의 활성 Python 정책을 건드리지 않았다(git log로 확인). 활성 정책은 L1 상태4 그대로다.
- 후속 과제 E14~E16(M1), E22(O2), E23·E24(J5), E25·E26(O3), E27·E28(O4), E29·E30(J3), E31·E32(M4), E33~E35(J8)를 EXTRA_TASKS에 등록했고, 모두 todo 상태다. 결정 D20(M1 기한·한도)을 비롯해 이후 루프가 정한 결정들도 기록했다.

## improvements
- [strong] Go 서버 보류 복호기 구현과 검증 :: 직접 확인: WSL 임시 사본(go1.26.6, GOPROXY=off)에서 hold 관련 시험 25개 PASS, 0.392 s. Python 대조 2개는 입력 파일이 필요해 SKIP. Codex 문서 기준: 60설정 700116사례가 실제 Go ReadFrom과 일치했고, 참조 FIFO 경로(RTT 50 ms, 2000 kbps) 75연결에서 첫 송신 CRYPTO 전 미사용 패리티 3/2/2개, 복원 0/1/1개를 확인했다(M1_quic_queue_check.md). 코드 검토: 기한 식, 뒤 패리티 우선 선택, 미사용 패리티→현재 원본→복원 원본 반환 순서, BytesToStack+pending≤BytesIn 검사가 계약과 일치한다.
- [moderate] 보류 기제의 이득은 세계 결함을 고친 뒤에도 남는다 :: 직접 확인(scratch 사본, 한 줄 수정, seed31, 큰cert·RTT50·2 Mbps, 4행동 중 최선): p=0.15에서 off 109.78 ms → hold 101.91 ms(−7.87), p=0.25에서 130.32 → 122.17 ms(−8.15), p=0.02에서 82.45 → 83.09 ms(+0.64). lead=0 행동은 off와 소수점까지 같았다. 문맥 하나, seed 하나의 개발 진단이며 W1 전체 재평가는 아니다.
- [moderate] 카드의 모형 수준 완료 기준 재현 :: 직접 확인: P_fail = 0.15^6 + 6·0.85·0.15^5 = 0.000398671875, p=0.02에서 1.888e-08. 스냅숏 layout.evaluate로 off 103.420077 → hold 90.540241 ms(p15, 개선 12.88 ms), p2 79.292127 → 80.096219 ms를 소수 6자리까지 재현했다. 다만 model과 world의 차이는 크다(수정 세계의 개선은 약 7.9 ms).
- [strong] 평가 도구의 전송 의미 결함 두 가지를 찾아냈다 :: 직접 확인: quic-go v0.61.0 connection.go 663~671행(wasProcessed가 거짓이면 continue, 송신 생략)과 ReceivedBytes(복호 전 계상, 제한 해제 시 setLossDetectionTimer). 그리고 sent_packet_handler.go getPTOTimeAndSpace(lastAckElicitingPacketTime 기준)와 W0 arm_server_pto(재무장 시각 기준)의 차이. 두 가지 모두 이후 모든 세계 평가의 정확도와 연결된다.
- [moderate] J5 GE 첫 비행 수학 검증과 부정 결과 :: 직접 확인: 정확 분수 계산으로 p=0.15, L=3에서 (0,0,4) GE P_fail 0.0429920116, (0,0,3) 0.0631808279(Codex 값과 일치). Codex 세계 진단: B10에서 iid와 GE가 같은 행동을 골라 HCT 변화 0. GE 모형의 결정 가치가 W1에서 0이라는 사실이 드러났다.
- [moderate] O2 미확인 업링크의 실제 위험 크기 :: Codex 문서·원자료: 모형 최대 후회 6.503042445 ms(감사 재현). 세계 240대조 중 16개에서 후회 하한이 6.5 ms를 넘었다(B1 u0 p15 10.543249 ms). 직접 확인: B1 (0,3,1)의 첫 비행 실패 547/9000은 off P_fail 0.06075와 맞고, (126,3,1)의 패리티 1406+39+12 = 1457 B가 세계 상한 1452 B를 넘는다(decide3.UDP_MAX = TYPICAL_MTU−28).
- [weak] O4·O3·M4·J8의 관측·입력 사실 :: Codex 문서: 실제 T3 114연결 중 24연결은 후보 W에 따라 k가 바뀐다(첫 CRYPTO 312패킷, Go 직렬화 6674패킷 일치). RTTVAR 4배 여유는 합성 2-RTT의 69.83~84.11%를 1-RTT로 가린다. 직접 확인: M4 전달 확률 0.98801875 / 0.7225 / 0.95550625를 닫힌식으로 재현했다. server_profile.required_credit(S=18231에서 granular 5974, exact 6077)도 맞다. O3 EWMA α=0.25로 94.994 / 139.989 ms가 나온다.

## checked_but_ok
- Codex의 최소 재현(손실0, k2, lead0, trailing0~4)을 scratch 사본에서 그대로 재현했다: off 117.96, 동결 hold 78.812, 진단 117.96 ms(trailing 3·4).
- quic-go v0.61.0 소스에 대한 Codex의 읽기가 맞다: handleOnePacket이 복호 전에 ReceivedBytes를 부르고, 처리된 패킷이 없으면 run 루프가 송신 단계를 건너뛴다.
- hold.go의 기한 식 remaining = (m−i−1)·len + Σlens(선행 index i일 때)는 hold_decoder.FlightSpec.bytes_after_parity와 계약 문장과 같다. 정렬 비교자는 뒤 패리티를 먼저, index 오름차순으로 고른다. 반환 순서는 미사용 패리티(도착순) → 현재 원본 → 복원 원본(index순)이다.
- lead-hold 기본값 false(qamp.go:3722). 이 갈래의 커밋은 padfec3·padfec·afec 활성 정책을 수정하지 않았다.
- M1 처분 JSON의 82/15/23과 C1 B2 +10.255815 [8.849427, 11.662204] ms는 문서와 일치하고, Codex는 C1 감소 8셀을 보류 효과로 쓰지 않았다.
- J5 GE P_fail 0.042992011619과 0.063180827887을 독립 정확 계산으로 재현했다.
- M4 첫 묶음 전달 확률 0.98801875, 0.7225, 0.95550625와 송신 바이트 5236·5120 B가 맞다.
- O2 추정기의 u = 0.008/slope(ms/B → Mbps)와 절편 대수가 맞다. minimax 정렬 키는 (최악 후회, 후회 합, tie_key)다.
- O2 세계 비교를 '세계 최적 대비 후회의 하한'으로 해석한 것은 맞다. 비교 행동의 비용이 세계 최적 이상이기 때문이다.
- server_profile.required_credit: exact는 ceil((sent+Σ)/3), granular는 floor((sent+Σ[:-1])/3)+1로 맞다. credit_branches의 경주 가중치 분해도 맞다.
- O3 EWMA α=0.25에서 50→100 ms 계단 8표본은 94.994 ms, 150 ms는 139.989 ms다.
- J8이 지적한 W0 arm_server_pto와 quic-go getPTOTimeAndSpace의 기준 차이를 코드로 확인했다.
- O2 문서의 '6.5 ms'는 모형값(6.503 ms) 재현이다. 세계에서의 후회 하한은 더 크다(B1 u0 p15 10.54 ms). 작업 지시의 '업링크 오라클 제거 시 최대 6.5 ms 후회'는 모형값으로만 맞다.
- O4의 900실행 재생은 세계 k가 고정이라 차이 0이 예정된 계산이었지만, 후보 코드의 비회귀 확인으로는 의미가 있다.
- 읽기 전용 규칙 준수: gen33 git status 깨끗, __pycache__·.pytest_cache 새로 생기지 않음, ~/quicbed_gen33/bin/qamp 수정 시각 2026-11-01 08:19:50 그대로. WSL 임시 디렉터리 /home/scien/v33audit_tmp/E는 삭제했다.

## VERIFY

- E-M1-1 (error): **confirmed** sev= :: 원자료 집계, 후보 모형 값, 수정 세계 값이 모두 감사자 숫자와 맞는다. 응답 XOR 비대칭이 순위를 뒤집는 원인이라는 점도 확인했다. response_xor=False로 두면 (0,3,1)이 (0,4,0)보다 나빠진다. 다만 응답 XOR은 send_reply의 'Q'(776행)와 탐침의 'V'(811~812행) 두 곳에 있고 둘 다 action.trailing 조건이다. 감사자는 'V'만 적었다. 후보 모형의 둘째 왕복 무손실 가정은 L1 기준 layout.response_term(later=v3면 tau(w)만 반환)에서 물려받은 기존 한계이고, M1이 그것을 드러낸 것이다. 세계 결함과 무관한 후보 실패가 B2 말고도 하나 더 있어(missed 1, B7 none) 이 항목의 결론을 더 받쳐 준다. || 직접 확인. (1) count_actions.py로 runs\M1_factorial_raw_v1\hold_m1_c1_B2 20seed의 phase1 집계: (0,4,0) 5099/9000=0.5666, 평균 154.92 ms. (0,3,1) 3526, 108.11 ms. hold_l1_c1_B2: (0,0,4) 0.6829, 103.88 ms. (2) 스냅숏 layout.evaluate(k2,W1280,RTT50,u2,n_need15, 결정 기록의 n_need=15): p=0.25 hold (0,4,0) 102.607, (0,3,1) 110.921. RTT 55.12에서도 110.109 < 119.640으로 순위가 같다. (3) scratch 수정 세계(m1_outputs flush 조건에 token=="o" 추가, Codex 진단 사본과 diff 동일), 큰cert p=0.25 seed31: 3000연결 (0,4,0) 148.659, (0,3,1) 122.165. 6000연결 154.767 / 123.130. response_xor=False 6000연결: (0,3,1) 180.423, (0,4,0) 154.767(trailing이 없어 값이 그대로). (0,4,0) hold의 tail 등급은 691/6000이고 평균 555.1 ms다. (4) M1_stage3_result.md와 M1_world_validity.md에는 후보 모형 원인이 언급되지 않는다.

- E-M1-2 (error): **confirmed** sev= :: 성능 실행 전 시험에 lead=0 off==hold 불변식이 없었다. 동결 세계에서 이 불변식은 크게 깨진다. MC도 세계 위에서 돌았으므로(M1_mc_contract.md) 결함의 영향을 받았다. 다만 '56 trace 재현만 봤다'는 표현은 좁다. 경계 차분 240사례, 첫 비행 패턴 전수, FIFO 신용 시험도 있었다. 그중 어느 것도 이 불변식을 보지 않았다. 감사자가 낸 회귀 시험은 한 줄 수정 뒤에도 남는 위반까지 잡아내므로 처방이 타당하다(missed 2). || 코드 확인: tests\test_v33_m1_world.py 시험 7개. test_credit_only_replays_frozen_world는 seed 2개 × 경우 7개 × 행동 4개 = 56으로 'W0의 56 trace'와 맞는다. off와 hold의 lead0 비교 시험은 없다. 첫 커밋은 46c80bb9e(10-31 22:54)다. 직접 확인(seed31, 3000연결): p=0.15 (0,0,4)는 off 122.554, 동결 hold 88.259, 수정 hold 122.554. p=0.02의 (0,0,3)/(0,0,4)는 동결 82.498/79.034, off와 수정 hold 118.658/118.602. 손실0·trailing3/4 최소 재현값 117.960/78.812는 M1_stage3_result.md 표와 같다.

- E-M1-3 (error): **confirmed** sev= :: 코드와 계획 문서 모두 감사자 설명과 같다. 영향 크기도 직접 재 보니 0.5 ms 문턱과 비슷한 수준이어서 medium이 맞다. || 코드 확인: worldsim_m1.py 708~711행 Receiver(..., round(context.uplink_mbps*1000), ...). qamp.go 3723행 -lead-hold-uplink-kbps 기본 2000. M1_evaluation_plan.md 5행은 '각 문맥에 명시된 Mbps'를 '자동 추정값이 아니다'라고만 적었다. bench_protocol.json에서 손실이 있고 u≠2인 셀은 B10(u0, GE p0.15), B12_c6000(u10), B12_c12000(u5)뿐이다. B3_u0과 B4는 p=0이다. 직접 측정(수정 세계, 6000연결, 711행을 2000으로 바꾼 scratch 변형): B12_c12000 p0.08 (0,4,0) 136.102→137.307 ms(+1.21). 이 행동은 hold_m1_c1의 p0.08 구간에서 95.6% 선택됐다. B10 (0,1,3) 64.073→64.502(+0.43), M1 선택률 97.8%. B12_c6000 (0,3,1) 128.181→128.292(+0.11). (0,0,4)는 변화 0.

- E-M1-4 (error): **confirmed** sev= :: 패턴 하나가 손해 전부를 설명한다는 분해와 두 상한 값이 모두 재현된다. Codex 문서에는 이 진단이 없고 32.536 ms 상한과 비교한 표만 있다. 카드 단서(데이터그램 하나 5.3 ms)는 원래 '모형에 넣을 것'이라는 지시였다. 결론이 바뀌지 않으므로 low가 맞다. || 직접 확인(pattern_contrib.py, 스냅숏 hold_layout.outcomes): 패턴 (1,1,1,0,1,1)의 off t_dec 26.416, 신용 6553, HCT 76.416. hold는 21.092, 5222, 126.212. 기여 +0.9002 ms. ok 패턴 기여 합 0.8942, 전체 J 차이 0.804092. m1_fixed_checks.py 44행 deadline=tau(client_bytes)+1.0 = 32.536 ms, 패리티 데이터그램 하나 5.324 ms. Codex 쪽: M1_fixed_action_table_v1.md 39행 '(0,3,1) | 0.804092 | 32.536000'. TASKS.md M1 카드 '검증자 단서: deadline 비용(2 Mbps에서 데이터그램 하나 5.3 ms)을 모형에 넣을 것'.

- E-M1-5 (error): **confirmed** sev= :: 코드 동작은 감사자 설명대로다. 다만 TTL 폐기는 계약(M1_hold_contract.md 31행 'TTL 시각에는 보관분을 정확히 한 번 폐기')에 명시된 설계다. 결함은 hold_layout 비용 모형이 이 신용 손실을 반영하지 않는 데 있다. 발생 확률이 매우 작아 low가 맞다. || 코드 확인: decoder_index.go 339~342행(finalizeHoldFlightLocked 뒤 terminal이 비어 있으면 holdDiscardLocked(fr, "expired")). hold.go 81~97행 holdDiscardLocked는 HoldDiscardBytes와 HoldExpiredBytes만 늘리고 스택으로 넘기지 않는다. hold.go 152~155행(missing > len(symbols)이면 passCurrent 후 return). hold_layout.py 120~128행의 실패 비용은 신용과 무관하다. P_fail(0,3,1) p0.15 = 0.000398671875를 정확 분수로 재계산했다.

- E-J8-1 (error): **partly** sev= :: W0의 PTO 재무장 결함이 있다는 점, J8이 기존 W1 판정에 미치는 영향을 표시하지 않고 E34로 넘긴 점은 맞다. E34 카드에도 기존 판정 재검토 항목은 없다. 그러나 근거로 든 B7 hold−off 손해(+1.05/+0.88)는 PTO와 관련이 없다. 하향 손실을 0으로 둬도, PTO 기준을 마지막 송신 시각으로 바꿔도 손해가 그대로 남는다. 원인은 E-M1-4와 같은 결정 규칙 비용이다. M1의 B7 실패(none 모드, 4.2~5.6 ms)도 후보가 (0,3,1)을 고른 탓이다(missed 1). 그래도 영향 범위를 재야 한다는 지적 자체는 더 강해졌다. 내 근사 수정에서 B7 절대 HCT가 행동마다 0.68~3.14 ms씩 다르게 움직였기 때문이다. 서로 다른 행동을 고르는 정책 비교라면 0.5 ms 문턱을 넘을 수 있다. || 코드 확인: worldsim.py 624~629행, 644·651·936·948행. WSL quic-go@v0.61.0 sent_packet_handler.go sha256 7b7a772f…924d는 J8_downlink_timer_source.json과 같다. 직접 측정(수정 세계, B7 문맥, 6000연결): s2c 0.01에서 (0,1,3) off 81.106/hold 82.159(+1.053), (0,1,1) +0.884로 감사자 값을 재현했다. seed32는 +0.882/+0.732. s2c_loss=0이면 +1.071/+0.953이다. PTO를 '마지막 data 송신+PTO, 이미 지났으면 즉시'로 바꾼 scratch 근사에서도 +1.084/+0.915였다. 이 근사에서 절대값 변화는 (0,1,3) 81.106→78.229, (0,3,1) 90.992→87.850, (0,0,4) 126.779→126.095였고, off와 hold가 같은 폭으로 움직였다. 이 근사는 번호 공간을 하나로 본 나의 진단이며 RFC 전체 구현이 아니다.

- E-J5-1 (error): **confirmed** sev= :: B10에서 L1이 이미 (0,0,4)를 고르고 있고, 동결 W1 세계에서도 (0,0,4)가 큰 차이로 최선이다. E23은 'B10 감소'를 판정 기준으로 다시 걸었다. 다만 '구조적으로 불가능'은 약간 과장이다. c1 모드에서는 (0,0,3)으로 간 2.1%를 (0,0,4)로 옮기면 약 0.13 ms 여지가 있다. none 모드는 cold 20연결만 남아 사실상 0이다. Codex도 'GE 정책이 어떤 학습기에서도 이득을 낼 수 없다는 판정이 아니다'라고 적었다. || 직접 확인: off_l1_c1_B10 (0,0,4) 26413/27000=0.9783(64.57 ms), (0,0,3) 567(70.74 ms), (0,0,0) 20. off_l1_none_B10 (0,0,4) 0.9993. scratch에 복사한 동결 worldsim.py로 B10 문맥(GE p0.15 L3, u0, cert4032, 4000연결) 16행동의 순위를 매겼다: (0,0,4) 63.17±0.92, (0,1,3) 69.42, (0,0,3) 71.57, 나머지는 더 나쁘다. EXTRA_TASKS.md E23 완료 기준에 'B10 감소 및0.5 ms 비열등을 판정한다'가 있다. J5_world_result.md 9행.

- E-J3-1 (error): **refuted** sev= :: 실패 대용 5건은 값이 좁게 모여 있다. −49.26 ms 차이는 표본 오차의 약 16배라서 '통계적으로 의미 없음'이 아니다. 오히려 15% 층의 통과(+1.55 ms)가 SE 10.1 ms로 더 불확실하다. 남는 우려는 5건이 모두 run1에서 나왔고 Initial 수가 5개인 한 유형뿐이라는 대표성 문제다. 이것은 Codex가 이미 적었고, 감사자 논지(표본 수 때문에 판정 불능)와는 다르다. || 직접 확인: runs\J3_diagnostic_full_v1\historical_rows.jsonl. loss 2.0은 2250행 중 failure_proxy 5건으로 값 280.5, 281.5, 292.1, 293.8, 293.9, 평균 288.3458, sd 6.77, se 3.03이다(t(4) 95% 반폭 약 8.4 ms). loss 15.0은 130건, 평균 266.3926, sd 115.18, se 10.10이다. J3_reference_result.md는 '낮은 손실률의 표본 수와 직접 실패 라벨 부재를 기록'한다.

- E-J8-2 (error): **partly** sev= :: p_d>0에서 J=None인 것과 카드가 '모형만'인 것은 사실이다. 그런데 카드는 p_d 항을 'W0 세계와 맞춘다'까지 요구했다. W0 타이머 결함을 찾은 이상 그 대조 부분이 막힌 것은 정당하다. p_d 항을 비활성 참조로 먼저 구현할 수 있었다는 지적은 판단의 문제이고, '범위를 부풀렸다'고 단정할 근거는 약하다. || TASKS.md J8 카드: '하향 손실 p_d 항(…)을 J3에 넣고 W0 세계와 맞춘다(A1-15, A7-19)'. docs\J8_server_cost_contract.md: 'p_d가 양수면 현재 단계는 J=None, cost_complete=false', 무손실 반사실 값과 손실 확률은 별도 필드로 보존한다.

- Go 서버 보류 복호기 구현과 검증 (improvement): **partly** sev= :: 구현과 검증이 단단하다는 판단에는 동의한다. 다만 시험 수를 잘못 셌다. 매칭된 상위 시험 25개는 23 PASS와 2 SKIP이다. '25개 PASS에 2개 SKIP'이 아니다. || 직접 실행: build_gen33.sh와 같은 배치로 WSL 임시 stage(/home/scien/v33audit_tmp/verifyE, 끝난 뒤 삭제)를 만들고 go1.26.6, GOPROXY=off, -run "Hold|hold"로 돌렸다. 결과는 ok 0.395s, --- PASS 23, --- SKIP 2(TestHoldPythonReadFromReference, TestUDPHoldPythonReadBatchReference). 코드 확인: hold.go 158~163행 정렬은 뒤 패리티 우선, 182행에서 BytesToStack+pendingBytes+planned > BytesIn이면 거부. 700116사례와 75연결 3/2/2는 Codex 문서 값이다.

- 보류 기제의 이득은 세계 결함을 고친 뒤에도 남는다 (improvement): **partly** sev= :: p=0.15와 0.25 숫자는 정확히 재현된다. p=0.02는 내 값이 82.577→83.201(+0.624)로 감사자 값(82.45→83.09)과 조금 다르다. 'lead=0 행동은 off와 소수점까지 같았다'는 감사자가 본 행동에서만 성립하고, (0,0,1) p=0.25에서 깨진다. 또 이 이득은 행동마다 세계 최선을 골랐을 때(oracle)의 값이다. 실제 M1 후보는 p=0.25에서 (0,4,0)을 주로 골라 수정 세계에서 148.66 ms가 되고, off 최선 130.32보다 나쁘다. || 직접 확인(scratch 수정 세계, seed31, 3000연결, m≤4 행동 15개): p=0.15 off 최선 (0,3,1) 109.780, hold 최선 (0,4,0) 101.906(−7.874). p=0.25 off 최선 (0,0,4) 130.317, hold 최선 (0,3,1) 122.165(−8.152). p=0.02는 82.577 대 83.201. (0,0,1) p=0.25: 수정 hold 157.705, off 157.722. 연결 2041 하나에서 off 1023.068, hold 972.524 ms.

- 카드의 모형 수준 완료 기준 재현 (improvement): **confirmed** sev= :: 정확 분수 계산과 스냅숏 평가값이 모두 맞는다. 다만 카드 기준은 'W1 세계(보류 모드)'에서 약 10 ms였고, 수정 세계의 값은 7.87 ms다. || 직접 확인: P_fail p15 = 0.000398671875, p2 = 1.888e-08. layout.evaluate p15 off (0,3,1) 103.420 → hold (0,4,0) 90.540, p2 79.292 → 80.096.

- 평가 도구의 전송 의미 결함 두 가지를 찾아냈다 (improvement): **confirmed** sev= :: 두 가지 모두 로컬 quic-go 소스로 확인된다. 단서가 하나 있다. ReceivedBytes가 증폭 제한을 풀면 setLossDetectionTimer를 부르고, 기한이 이미 지났으면 다음 루프에서 탐침이 나갈 수 있다. 그래서 '송신 없음'이 절대적이지는 않다. Codex도 pacer 등은 별도 검증이 필요하다고 적었다. || WSL /home/scien/gopath/pkg/mod/github.com/quic-go/quic-go@v0.61.0: connection.go 669~671행 'if !wasProcessed { continue }'. sent_packet_handler.go 224~231행 ReceivedBytes(증폭 제한이 풀리면 setLossDetectionTimer). getPTOTimeAndSpace는 lastAckElicitingPacketTime 기준이다.

- J5 GE 첫 비행 수학 검증과 부정 결과 (improvement): **confirmed** sev= :: 정확 분수로 같은 값을 얻었다. || 직접 확인(ge_check.py, Fraction, a=p·b/(1−p), b=1/3, 정상 시작): 6패킷 0.0429920116194626, 5패킷 0.06318082788671024.

- O2 미확인 업링크의 실제 위험 크기 (improvement): **confirmed** sev= :: 수치와 근거 파일이 맞다. 다만 가장 큰 반례(B12_c12000, 45~55 ms)는 1457 B 패리티가 1452 B 상한에서 잘리는 문제(J7)와 섞여 있다. 업링크를 모르는 데서 오는 위험 자체는 B1 u0 10.54 ms 쪽이 더 정확히 보여 준다. || docs\O2_world_result.md 표와 E22 카드. 직접 확인: iid (0,3,1) off P_fail = 0.15³+3·0.85·0.15² = 0.06075. decide3.py 9행 UDP_MAX = quantum.TYPICAL_MTU − 28. worldparams decoder_max_datagram_bytes 1452.

- O4·O3·M4·J8의 관측·입력 사실 (improvement): **confirmed** sev= :: M4와 J8 값은 직접 재현했다. O3·O4 숫자는 Codex 문서 값이며 따로 재계산하지 않았다. || 직접 확인: M4는 1−(q⁴+4(1−q)q³) = 0.98801875, (1−q)² = 0.7225, (1−q²)² = 0.95550625. server_profile.ServerProfile(mode).required_credit([1280]*14+[311])는 granular 5974, exact 6077이다.

- verdict_improved (verdict): **partly** sev= :: '배포 동작은 발전하지 않았고 연구 역량은 일부 발전했다'는 큰 판정에는 동의한다. 다음 세부는 틀렸거나 부정확하다. (1) 루프 기제 설명. EXTRA 과제는 선택되지 않는 것이 아니라 order 맨 뒤에 들어가 있다. 실제로 E12, E2~E6, E17, E18은 done이다. E14는 의존(W1)이 풀렸지만 순서상 R2(doing) 뒤라서 차례가 오지 않았다. (2) 8개 과제에서 나온 후속 E 과제는 22개가 아니라 17개다(E14~16, E22~35). E17~E21은 T5·T6·T3·X4에서 나왔다. (3) J3를 '표본 부족'으로 분류한 것은 E-J3-1에서 반박된다. (4) J8 '범위 부풀림'은 카드가 W0 대조까지 요구했으므로 부분적으로만 맞다. (5) '약 8 ms 이득'은 행동별 최선을 고른 oracle 값이다. M1 후보의 실제 선택으로는 B2 p0.25와 B7 none에서 수정 세계에서도 손해다. || LOOP_STATE.json: order 90개, E14는 'E13' 다음, 'current': R2, E14 iterations 0, depends ['W1'], W1 done. LOOP_PROMPT.md 43~44행. EXTRA_TASKS.md 147~165행(E14~16), 248행 이후(E22~E35), 192~234행(E17~E21은 T5/T6/T3/X4 후속).

### missed

- [medium] M1의 B7 none 실패 4셀은 세계 결함과 무관한 후보 선택 문제다 :: 주 120셀의 실패 15개 중 4개가 B7 none(대 hold/l1 +4.675, off/l1 +4.229, off/v31 +5.590, off/v32 +4.487 ms)이다. 원인은 M1 후보가 (0,3,1)을 75.4% 고른 데 있다. none 모드 학습층의 p 사후가 0.14 근처에 머물고, hold 모형은 고손실에서 선행이 많은 행동을 선호한다. (0,3,1)은 동결 세계와 수정 세계 모두에서 (0,2,2)보다 약 5.3 ms 느리므로 E14 세계 수정과 무관하게 실패가 남는다. Codex는 실패 전체를 송신 재개 결함 쪽으로 해석했다. 이 셀은 E-M1-1과 함께 후보 쪽 결함의 두 번째 사례이고, E-J8-1이 이 실패를 PTO와 연결한 것도 맞지 않는다. || 직접 확인: M1_benchmark_v1.json comparisons의 primary 실패 목록. count_actions.py: hold_m1_none_B7 (0,3,1) 20352/27000(90.21 ms), (0,2,2) 0.24(84.82). hold_l1_none_B7 (0,2,2) 0.8556(84.91), (0,1,3) 0.1437(79.63). 결정 기록: p_mean 0.1378, n_need 9. scratch 세계 B7 6000연결: 동결 hold (0,3,1) 90.682/(0,2,2) 85.322, 수정 hold 90.682/85.372. 스냅숏 모형 p0.02에서는 (0,1,3) 72.867 < (0,2,2) 75.768 < (0,3,1) 80.919로 최선을 맞힌다. 따라서 문제는 none 모드의 p 추정과 hold 모형의 결합이다.

- [low] Codex의 한 줄 진단 수정 뒤에도 lead=0 off==hold 불변식이 드물게 깨진다 :: 수정 세계에서도 (0,0,1) p=0.25에서 3000연결 중 1연결의 HCT가 다르고(−50.5 ms), 2연결의 서버 송신 목록이 다르다. off 경로는 서버가 ready가 된 뒤 도착한 패리티를 복구에 쓰지 않고 신용으로만 넘긴다(worldsim_m1.py 896~901행 'if state["ready"] or state["ready_scheduled"]: credit'). hold 수신기는 늦은 비행에서도 복구해 'o' 토큰을 만들고 flush를 일으킨다. Codex가 '다섯 trailing 조건의 off·진단 서버 송신 목록 일치'로 확인한 것은 손실0 사례뿐이다. 감사자도 (0,0,4) 몇 경우만 봤다. E14는 이 늦은 비행 복구의 의미도 정해야 한다. || 직접 확인(lead0_diff2.py, scratch 수정 세계, seed31, k2 W1280 RTT50 u2 cert16000 p0.25, 3000연결): conn 2041, off 1023.068 failure, hold 972.524 failure, hold에서 fec_recover(flight 3, 944.924 ms) 뒤 즉시 server_send가 이어진다. 'hct differing 1 … server list differing 2 of 3000'. p=0.02와 0.15의 lead0 행동 5개는 모두 일치했다.
