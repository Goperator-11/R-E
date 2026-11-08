# PAD-FEC 문서 전수 판정과 최종 문서 구조 제안

기준 시점: gen33 `feb0b1850`, R-E `70e7e08`, 2026-11-06. 판정 뜻: keep은 그대로 두거나 안내만 고친다. fix는 살아 있는 문서라 본문을 고친다. merge는 내용을 정본으로 옮기고 원본은 기록으로 둔다. archive는 작성 시점 기록으로 두고 고치지 않는다. 크기는 B다.

합계 165개: archive 80, fix 11, keep 26, merge 48. 아래 표 밖 묶음: `g3/v33/validation`의 md 442개(추적 기준)는 전부 archive이고, R-E의 `pq_afec_gen3/docs`, `pq_afec_gen31/docs` 15개씩은 `pq_afec/docs`와 같은 파일이라(크기 일치, 다음 세션 인계 sha256 앞자리 3bb52413 세 벌 일치) archive다. `pq_afec_gen33/docs` 111개와 README는 gen33과 바이트가 같아(cmp 불일치 0) gen33 판정을 따른다.

## 1. 문서별 판정

| 경로 | 크기 | 무엇을 말하나 | 판정 | 이유 |
|---|---:|---|---|---|
| gen33 README.md | 15289 | PAD-FEC v3.3 development: 이 폴더는 gen32 개발 사본에서 만든 v3.3 작업 저장소다. 세대 설정은 genconfig.json에 있다. 활성 정책 버전은 v3.3.1-dev, 저장 상태 버전은 | fix | 시험 수, 저장소 밖 경로, 설치본 상태, 내부 호칭(DC-09) |
| gen33 docs/E12_l1_go_contract.md | 2741 | E12 L1 Go 구현과 비교 계약: 활성 Python L1의 상태4와 정책 v3.3-dev를 Go에 옮긴다. J7의 46 B 후보는 보존 사본에 두고 이번 비교는 현재 39 B 기하를 쓴다. 도착 자료가 완 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J1_disposition.md | 6537 | J1 판정과 활성 정책: 2026-10-31 반복20. J1은 전체 평가와 독립 검증을 마쳤지만 채택 조건을 충족하지 못해 blocked로 남긴다. 후보 상태7은 보존하고 활성 정책은 직전 L1  | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J1_tail_design.md | 3941 | J1 둘째 비행 손실 꼬리: v3의 first flight이 성공했지만 증폭 예산 때문에 둘째 왕복이 필요한 가지에 q2·T2를 더한다. 뒤 parity T가 하나 이상이면 later 원본과 XOR  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J3_diagnostic_plan.md | 2477 | J3 실패 비용 진단 계획: 기존 고정 팔 저널 p31_run1_S_bigcert_units.jsonl과 p31_run2_S_bigcert_units.jsonl을 읽어 run·손실률별 g3fixL3를 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J3_recovery_contract.md | 4201 | J3 실패 뒤 두 단계 참조 계약: 이 참조는 first flight의 성공 가지와 기존 L1을 유지하고, 실패 뒤 재전송을 명시적으로 열거한다. 활성 정책에 연결하기 전에 수학·과거 고정 팔·독립 세계의  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J3_recovery_trace_contract.md | 2105 | J3 재전송 구간 관측 계약: 기존 T4_smoke_v4·T6_basic_v1·T6_oob_v1의123연결과 T2 재방문84연결·T3 패킷화114연결을 읽는다. 새 네트워크 실행은 하지 않는다. 출처  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J3_reference_result.md | 5625 | J3 두 단계 실패 비용 참조 결과: 반복52에서 비활성 Python 참조46시험과 과거 고정 팔4,500행의 재집계가 통과했다. 실패 확률·재전송 바이트는 별도 조합 열거102조건으로 검산했다. 기존 핵심3 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J3_trace_result.md | 4369 | J3 기존 재전송 관측 대조, 반복54: 기존 개발 자료 321연결 중 301연결을 검산했다. Retry 20연결은 키와 CRYPTO epoch 재구성이 필요해 계획에 따라 제외했다. 새 네트워크 측정은 하지 않 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J3_transport_result.md | 11700 | J3 재전송 전송 세계 진단: 별도 recovery_world.py의37시험이 통과했다. 기존 모드360대조에서 모든 기존 반환 필드와 사건 trace가 동결 worldsim.py와 같았다. T6의 p | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J3_transport_world_contract.md | 3309 | J3 재전송 전송 세계 계약: 동결 worldsim.py와 worldparams.json은 유지한다. recovery_world.py는 동결 사건 처리기를 별도 판으로 보존하고 재전송 원본 범위, T6 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J5_ge_contract.md | 4437 | J5 버스트 참조 구현과 관측 계약: 2026-11-01 반복45의 성능 계산 전에 고정한다. 이번 단계는 비활성 Python 참조다. 활성 L1, 상태 판본4, Go 정책, W0 세계와 W1 일정은 유지한다 | archive | ge_reference_report.py:136가 경로와 해시로 읽는다. 옮기거나 고치지 않는다 |
| gen33 docs/J5_reference_result.md | 5154 | J5 first flight GE 참조와 조건부 추정 결과: 반복45의 비활성 참조 단계다. 활성 L1·상태4·Go와 동결 세계는 유지했다. J5는 partial이며 전체 W1과 실제 피드백에서의 공동 학습을 아직 검증하지 않았다. | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J5_world_diagnostic_plan.md | 2863 | J5의 알려진 손실률 조건 세계 진단: 2026-11-01 반복46, 결과 계산 전에 고정한다. first flight 모형의 GE 확률 변경이 행동 선택과 독립 사건 세계에 미치는 범위를 확인한다. 활성 L1 | archive | ge_world_diagnostic.py:47가 경로와 해시로 읽는다. 옮기거나 고치지 않는다 |
| gen33 docs/J5_world_result.md | 5272 | J5 세계 진단과 보류 판정: J5는 blocked로 남긴다. first flight GE 참조는 검증했지만 B10 행동 개선이 없고, p·L 공동 학습과 상태를 이월하는 후속 HCT 비용이 남아 있다 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J6_disposition.md | 12135 | J6 판정과 활성 정책: 2026-10-31 반복22. J6는 전체 평가와 독립 검증을 마쳤으나 채택 조건 미충족으로 blocked다. 상태8·margin30 후보와 margin0 진단을 보존하고 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J6_preflight_budget.md | 4811 | J6 사전 ACK와 후보 경계: 이 문서는 반복21에서 성능 실행 전에 정한 개발 계약이다. 기준 정책은 J1 후보를 제거한 L1 상태4다. J6는 상태8을 쓰며 미채택 후보 L2·L3·J1의 상태5·6 | archive | v33fix_j6_rejudge.py:190이 25행을 규칙 출처로 적는다. 옮기지 않는다 |
| gen33 docs/J7_evaluation_plan.md | 3560 | J7 개발 평가 계획: 결과를 보기 전에 비교 범위를 고정한다. 기준 정책은739e6d3의 L1 상태4이며, 기존 L1_v1 사본과 패키지 전체의 바이트가 같은지 확인했다. 후보는 J7의46 B | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J7_family_and_report.md | 4222 | J7 전체 행동 평가와 보고: 기존 J7_evaluation_plan.md와 수집 계획은 그대로 둔다. 이 문서는 전체 수집을 마친 뒤 그 계획을 실행하는 분석기의 범위를 설명한다. 후보 성능을 판정하 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J7_wire_contract.md | 3760 | J7 parity 길이와 수신 상한: 활성 Python 기준은 L1 상태4다. L5 상태9 후보는 보존돼 있으며 J7에 합치지 않는다. J7은 parity 본문 padding, 수신 가능한 후보, 파싱 실패  | merge | 활성 정책의 설명 조각. SPEC_v3.3.1.md로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J8_downlink_result.md | 12345 | J8 하향 손실과 서버 타이머 진단: 반복60에서 동결 W0의 120조건을 추적했다. 세 회계 모드, u0·2 Mbps, S5000·18231 B, 행동(0,0,0)·(0,3,1), 첫 서버 비행의 무손실·첫 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J8_profiles.md | 17323 | J8 서버 프로파일 참조 결과: 반복58, 모형 계산이다. 실제 서버 성능이나 활성 정책 개선을 뜻하지 않는다. J8은 partial이며 전체 J3 비용과 하향 재전송 시간 연결이 남았다. | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/J8_server_cost_contract.md | 2774 | J8 프로파일별 복구 비용 계약: recovery_reference.evaluate의 새 선택 입력 server는 ServerCost다. 서버 프로파일과 실제 데이터그램 크기 목록을 받으며 n_need와  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/J8_server_profile_contract.md | 3352 | J8 서버 프로파일 참조 계약: 이 참조는 실제 서버의 UDP 데이터그램 크기 목록과 이미 보낸 바이트를 입력받는다. 인증서 바이트나 연결 전체 수신 바이트를 first flight 크기로 대신 쓰지 않 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/L1_benchmark_execution.md | 3565 | L1 벤치 실행 범위: 2026-10-30 KST에 L1의 Python 학습기와 독립 관측기를 구현했다. 이 문서는 전체 성능 판정 전의 실행 계약이다. 구현 시험과 짧은 실행이 통과해도 L1  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/L1_benchmark_reporting.md | 11397 | L1 학습 벤치의 행동 평가와 보고: experiments/v33/bench_learning_report.py는 새 관측 모드의 원자료를 검증하고, 하나의 행동 평가 집합과 보고서를 만든다. 수집은 bench | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L1_learning.md | 10955 | L1 도착 증거와 손실 학습: padfec3.learn3.observe3는 연결마다 데이터그램 우도, HCT 3등급 우도, 예측 전용 중 하나를 적용한다. 도착 증거가 완전하면 HCT와 관계없이 데이터 | merge | 활성 정책의 설명 조각. SPEC_v3.3.1.md로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L1_observation_contract.md | 6172 | L1 first flight 관측 계약: L1은 학습 수식, 관측 가능성, 전송 세계를 나눠 검증한다. experiments/v33/first_flight_observer.py는 W0의 전송 소스를 수정하지 않고 | merge | 활성 정책의 설명 조각. SPEC_v3.3.1.md로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L1_precision.md | 6745 | L1 고정 N 정밀화: bench_learning_precision.py는 발행된 L1 개발 결과의 행동 비용 계산을 한 차례 더 정밀하게 계산한다. 원래 N=131072 보고서를 본 뒤 정한  | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L2_artifact_validation.md | 2191 | L2 출처와 산술 검증: l2_joint_artifact_check_v2.py는 전체 계산과 보고의 완료 기록이 있는 자료만 검증한다. 3000실행과 150그룹, 210대조를 각각 대조하고, 행동 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/L2_benchmark_plan.md | 2736 | L2 개발 벤치 계획: 2026-10-31 반복 17, 새 정책 성능 실행 전 고정한다. 전송 세계, W1의 20개 seed와 15개 하위 셀, 19개 동결 참조, 판정 문턱은 유지한다. 기본  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/L2_disposition.md | 1093 | L2 후보 보류: L2의 EPS 적응 후보는 활성 정책에 채택하지 않았다. 사전 계획의 none·c1 전후30셀 중 none B8_j10이 미확정이었다. 차이는-1.568806 ms/연결, | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L2_joint_report.md | 2541 | L2 공동 행동 평가: bench_learning_l2_report.py는 완료된 L1 원자료와 L2 수집 자료를 같은 W1 프로토콜에 연결한다. L1 900실행, L2 900실행, 고정 EPS | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/L2_learning.md | 5492 | L2 목적지별 등급 잡음 추정: 2026-10-31 반복 17에서 성능 실행 전에 정한 설계다. L1의 세 등급과 경계 여유 3 ms를 유지하고, 고정 EPS를 목적지별 Beta 근사로 바꾼다. 사전은  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/L3_disposition.md | 5403 | L3 판정과 활성 정책: 2026-10-31 반복19. L3 후보는 채택하지 않고 과제를 blocked로 남긴다. 전체 평가와 독립 검증은 완료했지만 사전에 정한 채택 조건을 충족하지 못했다. 활 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L3_monitor_design.md | 8405 | L3 감시 설계와 개발 평가 계획: 2026-10-31 반복18. 활성 기준은 L1 상태4다. L2 EPS 후보는 미채택 상태로 보존한다. L1의3등급 fallback·고정 EPS0.001·현재 관측 RTT | merge | 활성 정책의 설명 조각. SPEC_v3.3.1.md로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L5_disposition.md | 5079 | L5 판정과 활성 정책: c12000에서 none은 L1 0.121485→L5 25.032549 ms, 차이+24.911063, 조정 구간23.775437,26.046689다. C1은0.13931 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/L5_server_response.md | 7578 | L5 서버 응답 관측과 혼합: 2026-10-31 KST, 반복23. 성능 실행 전 고정한 개발 후보 설계다. 활성 기준은 L1 상태4, 커밋91432c35다. J6 상태8 후보는 채택되지 않았다. L | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M1_evaluation_plan.md | 5039 | M1 개발 평가 계획: M1의 정책 후보와 수신기 변경을 분리해 평가한다. 이 계획은 성능 결과를 열람하기 전에 작성한다. 활성 정책은 L1 상태 4이고, 별도 M1 후보는 상태 10이다. 후보 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M1_fixed_independent_check.md | 1217 | M1 고정 행동 표의 독립 검사: validate_m1_fixed.py는 고정 행동 보고기의 계산 함수를 import하지 않는다. 가족 계획에 묶인 MC 결과를 읽고 SciPy의 정규분포 역생존함수로 공동 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M1_hold_contract.md | 8157 | M1 보류 복호 계약: 이 문서는 M1 후보의 구현 계약이다. 활성 L1과 동결 W0·W1은 별도로 유지한다. 보류 모드는 기본 꺼짐이며 구현 대조와 성능 채택을 구분한다. 단계별 실행 결과는  | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/M1_mc_contract.md | 3612 | M1의 세계 간 MC 오차: 평가 계획은 기대 비용을 주 결과로 두고 수신기 변경의 끝점 비교를 포함한다. 이때 서로 다른 세계의 공통 참조 비용은 상쇄되지 않는다. 기존 J7의 세계 간 표는 점추정 | archive | bench_m1_family.py:242가 경로와 해시로 읽는다. 옮기거나 고치지 않는다 |
| gen33 docs/M1_quic_queue_check.md | 5188 | M1의 실제 QUIC 처리 순서 검증: qamp_hold_quic_test.go는 로컬 UDP 소켓과 고정 quic-go v0.61.0으로 실제 TLS 연결을 만든다. 클라이언트 first flight은 X25 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M1_quic_reference_path_plan.md | 1839 | M1 실제 QUIC의 기준 경로 시험 계획: 지연 없는 로컬 연결에서는 첫 원본에 대한 ACK 뒤에 클라이언트가 새 Initial을 보내 보류 기한보다 먼저 CH를 완성하는 경로가 있었다. 기존 실패와 무조건 첫 송 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M1_world_validity.md | 7550 | M1 세계 비교의 유효 범위: M1 상태10 후보는 채택하지 않았다. 동결 평가의 주120셀은82통과·15실패·23미확정이며, 뒤 parity 수신 뒤 서버 송신을 재개하는 의미가 off·hold에서  | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/M4_cache_result.md | 4058 | M4 재방문 관측 캐시와 잔여 과제, 반복57: 관측 캐시를 활성 정책과 분리해 구현했다. 클라이언트의 실제 토큰 전달과 수락 Retry, 연결 뒤 TLS full/resumed/unknown을 구분한다. 실행 전에는  | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/M4_guard_result.md | 3521 | M4 고정 팔 전송 검증, 반복56: 기본 off인 revisit-guard를 Go 고정 팔에 연결했다. 실제 첫 Initial의 토큰 길이와 스택이 수락한 Retry를 입력으로 사용한다. 첫 토큰은 서버 수 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M4_observation_cache_contract.md | 3544 | M4 재방문 관측 캐시 계약: revisit_cache.py는 활성 L1과 분리한 Python 관측 참조다. HCT 비용을 계산하거나 행동을 고르지 않는다. 주소 토큰의 원문과 TLS 티켓은 저장하지  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M4_reference_result.md | 4115 | M4 토큰·Retry 참조와 기존 자료 검산, 반복55: 비활성 Python 참조의 44시험과 기존 T2 개발 108연결을 검산했다. 토큰 전달·초기 서버 주소 검증·Retry·실제 TLS 재개를 분리했고, 원래 Initial  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M4_revisit_guard_contract.md | 2821 | M4 고정 팔 전송 규칙: revisit-guard는 기본 off인 개발 옵션이다. fixed client fec·layout v3·m1~4·ips0 또는1280만 허용한다. Initial 크기는  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/M4_revisit_policy_contract.md | 4773 | M4 토큰·Retry·복호 지원의 Python 참조 계약: M4는 비활성 참조로 시작한다. 활성 L1 상태4, T2의 auto·auto3 토큰/재개 거부, T6 original_first 기본값은 전체 관문 전까지 유지한다. 이  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O2_reference_result.md | 5665 | O2 참조와 추정기 진단 결과: 비활성 Python 참조의 결정 산술과 입력 검증을 완료했다. 활성 L1·상태4·Go·독립 세계는 바꾸지 않았다. O2는 partial이다. 독립 세계의 숨긴 업링크 평가 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O2_uplink_contract.md | 4171 | O2 업링크 불확실성 참조 계약: None과 -1은 미확인 업링크다.0은 무제한이라는 기존 의미를 유지하고, 다른 음수·NaN·무한대·bool은 거부한다. 미확인 입력의 기본 시나리오는 U={0,2,5,1 | archive | uplink_reference_report.py:137가 경로와 해시로 읽는다. 옮기거나 고치지 않는다 |
| gen33 docs/O2_world_diagnostic_plan.md | 3340 | O2 숨긴 업링크 세계 진단 계획: 이 단계는 정책 비용 모형의 minimax 선택을 동결 독립 사건 세계로 옮기는 개발 진단이다. 활성 L1의 학습 성능이나 채택 관문을 대신하지 않는다. 참조는 각 손실  | archive | uplink_world_diagnostic.py:51가 경로와 해시로 읽는다. 옮기거나 고치지 않는다 |
| gen33 docs/O2_world_result.md | 5429 | O2 세계 진단 결과: O2의 비활성 minimax 참조를 채택하지 않는다. 고정한 독립 세계 진단에서6.5 ms를 넘는 후회의 하한을 확인했다. O2는 blocked이며, E22에서 와이어 후 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/O3_reference_result.md | 5315 | O3 RTT 참조 검증 결과: 반복47에서 Python 참조를 검증했다. 새 시험70개, 기존 시험351개와 하위 검사548개가 통과했다. 활성 L1 상태4와 Go·세계 코드는 바꾸지 않았다. O3는  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O3_rtt_contract.md | 4172 | O3 RTT 참조 계약: 2026-11-01 반복47에서 성능 실행 전에 고정한다. 이번 단계는 Python 참조와 관측 계약이다. 활성 L1 상태4, Go, 세계의 시간 생성과 W1 기준은 유지 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O3_trace_audit_plan.md | 1946 | O3 기존 RTT trace 진단 계획: 반복48의 집계 전에 범위를 고정한다. 대상은 반복42의 T2 관측 basic·oob, 재방문 basic·oob, 재방문 음성 대조 basic v2·oob v1의 stdo | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O3_trace_result.md | 3766 | O3 RTT trace 진단과 보류 판정: 기존 T2 기능 진단66개 stdout,198연결을 재집계했다. 새 시험15개와 독립 검산이 통과했다. 활성 L1 상태4·Go·세계는 유지했고, 반복47의 기존351개·5 | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/O4_current_k_contract.md | 2702 | O4 현재 연결 k의 정책 후보 계약: 이 후보는 활성 L1을 바꾸지 않는 Python 어댑터다. D35의 완성된 FirstHello로 현재 k를 계산하고 결정과 그 연결의 관측 분류에 같은 k를 쓴다. S·R | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O4_current_replay_plan.md | 2731 | O4 현재 k 후보의 W1 재생 계획: 현재 k 후보는 기존 L1의 W1 원자료 900실행을 같은 seed31~50, 15시나리오, none·c1·ideal로 재생한다. 각 연결의 현재 ClientHello는  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O4_current_result.md | 2833 | O4 현재 k 후보의 검증 결과: 비활성 Python 후보는 현재 ClientHello로 계산한 k를 결정과 해당 관측 분류에 함께 사용한다. 과거 k_hist에는 실제 관측만 남긴다. 첫 연결에 S나 R | merge | 후보 판정 근거. RESULTS_by_generation.md 7절 후보 표에 한 줄로 합치고 원본은 기록으로 둔다 |
| gen33 docs/O4_packetization_contract.md | 2929 | O4 현재 ClientHello의 패킷 수: 이 단계는 활성 정책과 분리된 Python 기준 구현이다. 입력은 이번 연결의 완성된 ClientHello CRYPTO 길이, 적용할 Initial 데이터그램 크기 W,  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O4_reference_result.md | 3337 | O4 첫 ClientHello 패킷화 참조 결과: 반복49의 Python 참조는 기존 T3 개발 자료114연결의 첫 CRYPTO 패킷312개와 일치했다. 활성 정책은 아직 연결하지 않았다. O4는 partial이며 다음  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O4_revisit_plan.md | 1844 | O4 토큰·TLS 재개 자료의 k 검증 계획: T2_revisit_basic_v1·T2_revisit_oob_v1의28개 조건 파일을 모두 사용한다. 조건당3연결인 기존 개발 자료이며 새 네트워크 측정을 시작하지 않는 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/O4_token_result.md | 3151 | O4 토큰·TLS 재개 패킷화 결과: 기존 T2 개발84연결의 첫 ClientHello 패킷168개가 D35 참조와 일치했다. 토큰을 실은32연결의 실제 토큰 길이는90~91 B였다. TLS 재개20연결, R | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/PUBLISH_PROCEDURE.md | 11785 | 공개·push 전 절차: gen33 이력은 filter-repo 같은 도구로 다시 쓰지 않는다. 커밋을 다시 쓰면 해시가 모두 바뀌는데, 이 해시들이 루프 기록의 근거로 박혀 있다. 2026-11 | fix | 3·44·48·81·83행이 11-05 실제 내보내기(feb0b1850, R-E 70e7e08, 1,620개)와 어긋난다. R-E 동기화 절차로 고친다 |
| gen33 docs/R3_codec_format.md | 2177 | Python 부호기와 테스트베드 형식: S5에서 확인한 구현 사실을 R3 문서 작업의 입력으로 남긴다. 모든 길이는 B다. | merge | 활성 정책의 설명 조각. SPEC_v3.3.1.md로 합치고 원본은 기록으로 둔다 |
| gen33 docs/REPORT_CLAIMS_v33.md | 61059 | PAD-FEC v3.3 보고서 주장과 정정 목록: 2026-11-01 KST, A1. 이 문서는 봉인된 gen-2·v3.1 자료의 재분석, v3.3 개발 상태, 인증서 파일의 바이트 측정, 명시한 가정에 따른 계산을 구분 | fix | CLAIMS.md와 ERRATA_frozen_generations.md로 나눈다. 볼트 행 번호, C:/ 절대 링크 48개, 금지 행 4개 누락(어디서나, 예측, 99.1%, 유의차 기각). 원본은 기록으로 두고 맨 위에 안내 한 줄만 넣는다 |
| gen33 docs/S2_consolidation_plan.md | 3806 | S2 통합 계획: 2026-11-01 현재 새 개발은 C:/dev/pq_afec_gen33의 v33 브랜치에서 이력을 남긴다. R-E main은6bbd11f에 유지했고 hygiene/202 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/S2_hygiene.md | 4922 | S2 R-E 위생 결과: R-E main의 HEAD는 6bbd11f8e7ebd7911a4f2e33fba7a8e6e9383937이며 작업 트리는 깨끗하다. 변경은 C:/dev/R-E-wt/hygie | merge | 시험·봉인 대조 절차를 REPRODUCE.md로 합친다. 시험 수는 당시 값이라 그대로 둔다 |
| gen33 docs/S4_port_contract.md | 2879 | S4 이식과 캐시 계약: R-E 커밋73aa4203c52eebac1eb1ce073b0b32f149768a44의 gen-2 수정9파일을 gen33에 의미대로 옮긴다. 원본·수정 전 소스는 hando | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/S4_port_result.md | 4083 | S4 이식 결과: R-E의73aa420 수정9파일을 gen33에 옮겼다. qamp.go의 v3와 M1 경로를 유지하며 parity만 받는 경로의 만료, heldBytes 해제, 상충 met | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/S5_test_hygiene.md | 12574 | S5 시험 정리와 재현 도구: 2026-11-01, 반복 62. 로컬 개발 검증이다. GitHub에서 CI를 실행하거나 원격 저장소에 올리지 않았다. | merge | 시험·봉인 대조 절차를 REPRODUCE.md로 합친다. 시험 수는 당시 값이라 그대로 둔다 |
| gen33 docs/T1_certificate_contract.md | 2632 | T1 고정 인증서 계약: gen33 qamp의 합성 인증서는 ECDSA P-256을 유지한다. 고정 개발용 seed로 키를 만들고 인증서 자체는 RFC 6979로 서명한다. 날짜·일련번호·subj | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T1_certificate_result.md | 3472 | T1 고정 인증서 결과: gen33 qamp는 certsize에 맞춘 결정적 ECDSA P-256 인증서를 만들고 -cert-file로 같은 PEM을 읽는다. 파일에는 단일 인증서와 PKCS8 키 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T2_followup_mapping.md | 897 | T2 후속 과제 연결 정정: TASKS.md의 M4는 이미 Retry·토큰 입력, lead·delta 축소, 뒤 parity와 서버 복호 지원 입력을 맡는다. 반복42에서 추가한 E21의 토큰 정책  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T2_result.md | 4366 | T2 토큰·TLS 재개 구현 검증: 고정 클라이언트의 token-store·resume와 서버 verify-source·resume를 구현했다. 기본값은 모두 off다. 클라이언트 LRU는 시행 루프 밖에서 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T2_revisit_contract.md | 2765 | T2 토큰과 TLS 재개 계약: client의 token-store는 프로세스 안에서 LRU(16 origins, origin당4개)를 공유한다. 매 시행의 UDP 소켓과 Transport는 따로 만들고 | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T3_compare_result.md | 3145 | T3 pad·dup 결과: 반복40의 개발 기능 검증이다. T3는 partial이며 k-inflate와 Initial 크기 확대 검증을 이어간다. 고정 v3 FEC에 pad-junk·dup를 추가하 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T3_comparison_contract.md | 3292 | T3 고정 비교 팔 계약: pad-junk와 dup는 client의 고정 fec on·layout v3 팔에서만 쓴다. 두 옵션을 함께 쓰거나 auto·auto3·buf·off·server에서 쓰면 | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T3_inflate_result.md | 4033 | T3 ClientHello·Initial 확대 결과: 반복41의 개발 기능 검증으로 T3 구현 범위를 완료했다. 반복40의 pad·dup에 이어 k-inflate를 추가하고 ips_used 요청값과 ips_eff 실제 기본· | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T3_inflation_contract.md | 2392 | T3 ClientHello와 Initial 확대 계약: k-inflate는 추가 transport parameter의 값 길이(B)다. 기본0은 추가하지 않는다. 범위0~8192 B, 양수는 client의 고정 fec off· | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T4_observation_contract.md | 5052 | T4 관측 계약: 이 문서는 기능 시험 전에 고정한 개발 계약이다. 활성 정책은 L1 상태4, lead-hold는 기본 off다. 정책의 비용식이나 세계 시뮬레이터를 바꾸지 않는다. | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T4_observation_result.md | 4853 | T4 관측 장치 결과: T4의 와이어 관측 구현을 완료했다. Go 159개·vet·race, 핵심 Python351개·하위548개, 실제 ReadFrom700116사례와 전체 v3 산술 관문이  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T5_boundary_result.md | 2817 | T5 첫 단계 결과: 출처는 구현·기능 검증이며 development다. 클라이언트의 peer·자체 발급 CID 검사와 최초 송신 경계, 계정 LRU·완료 후10초 수명을 구현했다. T5 전체 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T5_decoder_contract.md | 3318 | T5 복호기 색인과 보관 한도: 원본은 Initial이며 길이1472 B 이하인 데이터그램만 보관한다. 색인 키는 DCID, 연결 계정, CRC32, 원본 길이다. 전역512개, 같은 DCID와 계정에서 | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T5_decoder_result.md | 3551 | T5 복호기 색인 단계 결과: DCID와 연결 계정별 색인, 원본·비행·payload 상한을 구현했다. Go 180개와 vet·race, 핵심 Python351개·하위548개가 통과했다. ReadFro | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T5_flush_contract.md | 1574 | T5 비행 묶음 입력 계약: E17은 auto3 결정의 k를 첫 송신 묶음의 예상 데이터그램 수로 연결한다. 정책 비용·행동·상태 직렬화는 바꾸지 않는다. k는 목적지 관측에서 계산한 기존 최빈값이며 | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T5_flush_result.md | 2420 | T5 E17 k 입력 검증: E17은 auto3 결정의 k를 첫 송신 묶음의 expectK로 연결했다. 명시 옵션이 없을 때만 사용한다. 명시0은 캐시 추정 대신 타이머를 강제하고, 명시 양수는 기존 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T5_hardening_contract.md | 2492 | T5 수신 경계와 자원 수명: 클라이언트는 첫 Initial을 소켓에 쓰기 전에 peer와 자신의 SCID를 저장한다. 직접 생성하는 CID도 최대64개 등록하므로 정상 CID 회전을 따라간다. 같은  | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T5_timing_contract.md | 2276 | T5 E18 묶음 대기 관측 계약: flight_trace의 시간은 연결 시작 기준 ms이며 단조 시계로 계산한다. 첫·마지막 입력은 fecConn이 Initial을 받은 시각이다. flush_ms는 잠금  | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T5_timing_result.md | 3741 | T5 E18 대기·분할 관측 검증: flight_trace는 묶음별 첫·마지막 입력, 해제·송신 처리 완료 시각, 해제 이유, 적용 예상 k와 실제 k, 원본 바이트와 flush 송신량을 보존한다. 연결당  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T5_udp_contract.md | 2149 | T5 UDP 경로 계약: gen33의 Linux 서버는 udp-path=oob를 기본으로 쓴다. udp-path=basic으로 이전 수신 경로를 선택할 수 있다. 클라이언트 경로와 정책 산술은 유 | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T5_udp_result.md | 3288 | T5 UDP 연결 결과: 반복36의 구현 검증이다. 서버 기본 경로를 udp-path=oob로 연결했고 basic도 명시 선택할 수 있다. 실제 quic-go가 ReadBatch를 통해 복호기를  | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T6_result.md | 4579 | T6 후속 Initial 모양 검증: v3 FEC의 응답 전 후속 묶음은 기본 original_first에서 원본 우선·뒤 XOR1개를 쓴다. 첫 묶음, v2, 서버 큰 응답 뒤의 원본 즉시 송신은 유지한다. | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/T6_retrans_contract.md | 3815 | T6 후속 Initial 묶음 계약: v3 FEC의 첫 묶음은 기존 (L,O,T)를 유지한다. 큰 서버 응답을 아직 받지 않은 후속 묶음은 원본을 먼저 보내고 XOR parity1개를 뒤에 둔다. parity | merge | 테스트베드 계약. 현재 동작만 SPEC_v3.3.1.md 8절에 합치고 원본은 기록으로 둔다 |
| gen33 docs/T7_conditions_v31.md | 13045 | T7 비교 조건: v3.1 봉인 조건과 gen33 기본값: 2026-11-02, V33FIX 묶음 B. 같은 날 통합 정리(묶음 G)에서 -feedback 행, 예시 두 갈래, 규칙 3의 조건을 더했다. 이 문서는 gen33 qa | fix | 측정 조건 정본으로 남긴다. 묶음 이름과 D 번호에 풀이를 붙이고 용어만 고친다 |
| gen33 docs/V33FIX_bench_rules.md | 14835 | V33FIX 판정 규칙: 1절은 2026-11-02 01:47 KST에 썼다(문서 수정 시각 01:47:37 KST, g3/v33/V33FIX_J6_rejudge_v1.json의 rule_docu | keep | experiments/v33/zero_variance.py:21이 실행 중 읽고 Z1 절 해시가 고정돼 있다(23행). 본문을 고치지 않는다 |
| gen33 docs/V33FIX_docs_hygiene.md | 23036 | V33FIX 묶음 D: 문서와 저장소 위생: 숫자 옆의 "직접 확인"은 이 묶음이 스크립트나 명령으로 다시 구한 값이고, "문서에서 읽음"은 원 문서의 값을 옮긴 것이다. | archive | 11-02 문서 작업 기록. 107행이 docs/README.md와 ID 용어집을 못 했다고 적는다(DC-01, DC-06이 처리) |
| gen33 docs/V33FIX_evaluation.md | 23394 | V33FIX W1 재판정: v3.3.1-dev (개발 시뮬레이션): 이 문서는 결과를 일부 본 뒤에 한 사후 개발 분석이다. v3.3.1-dev의 설계(c1을 본 적 없는 목적지는 v3.2-dev, 본 목적지는 L3 record_only  | merge | v3.3.1 시뮬레이션 판정의 원문. RESULTS_by_generation.md 6절과 CLAIMS.md로 합친다 |
| gen33 docs/V33FIX_policy.md | 35130 | V33FIX 활성 정책 수정 (v3.3.1-dev, 상태 판본 11): 작성 2026-11-02. 묶음 A-py. 바꾼 파일은 padfec3/learn3.py, padfec3/decide3.py, tests/test_padfec3_arriva | merge | 활성 정책의 설명 조각. SPEC_v3.3.1.md로 합치고 원본은 기록으로 둔다 |
| gen33 docs/V33FIX_policy_go.md | 24308 | V33FIX 활성 정책 Go 거울과 Python-Go 관문 (v3.3.1-dev, 상태 판본 11): 작성 2026-11-02. 묶음 A-go. 앞 묶음 A-py가 Python 활성 정책을 v3.3.1-dev로 바꿨고(docs/V33FIX_policy.md), 이 묶음은  | merge | Go 거울과 관문 기록. SPEC_v3.3.1.md 9절과 REPRODUCE.md로 합친다 |
| gen33 docs/V33FIX_testbed.md | 56589 | V33FIX 묶음 B: Go 테스트베드 수정 기록: 2026-11-02. 시작점은 브랜치 v33의 HEAD d67717d9b(작업 트리 깨끗)다. 커밋하지 않았고 작업 트리에서만 고쳤다. 감사 원문은 F-go-testbed | merge | 테스트베드 수정 기록 56 KB, 묶음 호칭 19회. 플래그와 동작만 SPEC_v3.3.1.md 8절로 합친다 |
| gen33 docs/V33FIX_world.md | 38402 | V33FIX 묶음 C: 세계 시뮬레이터와 판정 통계 도구: 이 문서에서 "a ± b"의 b는 짝 차이(같은 seed와 연결 번호로 두 쪽을 평가한 연결별 차이)의 표준오차 1 SE, 곧 표본표준편차/√n이다. 신뢰구간이 아니다.  | merge | 세계 수정 기록. 남은 근사만 RESULTS_by_generation.md 6절로 합친다 |
| gen33 docs/bench_v33.md | 7440 | v3.3 독립 세계 회귀 벤치: g3/v33/bench_protocol.json이 시나리오, seed, 관측 경계와 판정 기준의 정본이다. 12개 가족을 15개 조건으로 나눠 seed 31부터 50까지  | fix | W1 벤치 설명은 지금도 맞다. 15·16행 명령이 저장소 밖으로 쓴다 |
| gen33 docs/c1_status.md | 3833 | C1의 현재 상태: 보호된 gen-2 팀 문서 C1 서버 피드백 설계.md는 수정하지 않았다. 그 문서의 "알려진 결함"과 gen33 구현을 아래처럼 구분한다. | fix | 11행 '활성 L1'이 낡았다. 내용은 SPEC_v3.3.1.md 7절로 합친다 |
| gen33 docs/c1_threat_model.md | 3361 | C1의 신뢰 경계: C1 판본3은 UDP 데이터그램 안의 평문 회신이다. CRC32는 도착한 원본과 복원본을 대조하는 식별값이고 메시지 인증 수단이 아니다. peer 주소와 클라이언트 자신의 | keep | C1 위협 모형. 지금도 맞고 SPEC_v3.3.1.md 7절이 링크한다 |
| gen33 docs/generation_paths.md | 3855 | 세대 경로와 역사 자료: genconfig.json은 작업 세대의 이름, 빌더 파일명, 지속 저장 바이너리, 설치 바이너리와 WSL 저장소 루트를 정한다. experiments/generation | fix | 33행 명령이 저장소 밖으로 쓴다. 검증 명령은 REPRODUCE.md로 옮긴다 |
| gen33 docs/server_support_signal.md | 2579 | 서버 복호 지원 신호 설계 메모: 이 문서의 initial-credit은 가칭이다. 번호를 배정하거나 DNS·QUIC 확장을 구현하지 않는다. M4 참조는 테스트베드가 명시한 supported만 복호 지원 | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/v33_action_pool.md | 9321 | W1 행동 평가 병렬 실행기: experiments/v33/bench_action_pool.py는 이미 선택된 oracle 행동을 기준으로 행동별 기대 HCT를 계산하는 실행기다. 계산은 기존 orac | archive | 작성 시점 기록. 현재형 문장('활성 L1' 등)은 색인 규칙으로 처리하고 본문은 고치지 않는다 |
| gen33 docs/worldsim.md | 20620 | 독립 세계 시뮬레이터: experiments/v33/worldsim.py는 행동을 입력받아 패킷 송신, 손실, 도착, 복호, 서버 응답, ACK와 PTO 사건으로 관측을 생성한다. 정책을 선택하 | fix | W0 API 설명은 지금도 맞다. 용어만 고친다(first flight 3곳, credit 8곳) |
| gen33 g3/v33/archive/S1_archive.md | 2785 | S1 원자료와 바이너리 보존: 2026-10-30 KST. 구현 검증 결과이며 새 네트워크 측정은 없다. | archive | 루프 초기 기록. 로컬 경로가 많지만 기록으로 둔다 |
| gen33 g3/v33/baseline/S0_baseline.md | 2658 | S0 기준선: 2026-10-30 KST. 자료 종류는 구현 검증이다. 네트워크 성능 측정은 하지 않았다. | archive | 루프 초기 기록. 로컬 경로가 많지만 기록으로 둔다 |
| gen33 g3/v33/evidence/A0_coverage.md | 2708 | A0 감사 추적: coverage_check 연결 2개와 A0 카드 근거의 합집합 10개를 처리했다. 아래 '처리함'은 원자료 재현 범위이며, 정책·계측 수정은 표시한 후속 카드에 남아 있 | archive | 루프 초기 기록. 로컬 경로가 많지만 기록으로 둔다 |
| gen33 g3/v33/evidence/EVIDENCE.md | 8593 | A0 근거 재현: 2026-10-30 KST. 봉인 v3.1 원자료를 읽어 재계산했다. 새 네트워크 측정은 하지 않았다. 관측값과 정책 비용 모형값을 구분한다. | archive | 루프 초기 기록. 로컬 경로가 많지만 기록으로 둔다 |
| R-E/README.md | 6067 | R&E: ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구: 2026 R&E, 강원과학고등학교, 신레오·정도현·황요한, 지도 이현미. | fix | 25·26·27·60행과 정본 연결(DC-08) |
| R-E/docs/audit-2026-09-14/README.md | 4490 | 2026-09-14 추가 연구 검토 기록: 이 폴더는 2026년 9월 14일 16:38 KST 이전에 작성한 오프라인 검토 자료 11개와 이 안내 파일을 담는다. 해당 시점에는 정밀 측정이 진행 중이었으며, 추가  | keep | 폴더 안내. 문서가 작성 시점 기록임을 이미 적었다 |
| R-E/docs/audit-2026-09-14/추가검토_연구주장_근거표.md | 21878 | 연구 질문과 주장별 근거 대응표: 검토일: 2026-09-14. 이 문서는 연구 목적과 현재 검증을 연결하는 보완 자료다. 실행 중인 정밀 측정, 코드, 환경과 Git 사본은 변경하지 않았다. 아래 최신  | merge | 주장과 근거 대응 틀을 CLAIMS.md가 물려받는다. 수치는 09-14 시점 |
| R-E/docs/audit-2026-09-14/추가검토_정책비교_검증설계.md | 23837 | 정책 비교의 추가 검토와 독립 확증 실험 설계 | archive | 09-14 설계 검토. 저장소 밖 경로 3곳 |
| R-E/docs/audit-2026-09-14/추가검토_표본충분성.md | 9457 | 추가 검토: p3·p4 표본충분성 | archive | p3·p4 표본 충분성 기록. 저장소 밖 경로 5곳 |
| R-E/docs/audit-2026-09-14/추가보완_작업기록.md | 6778 | 연구 목적에 맞춘 추가 보완 기록: 2026년 9월 14일 추가 검토. 정밀 측정은 계속 진행 중이다. 이 문서는 측정 중 수행한 오프라인 분석과 측정 종료 뒤 반영할 수정 항목을 구분한다. | archive | 09-14 작업 기록 |
| R-E/mlkem-quic-amplification/CHANGELOG.md | 1402 | 변경 이력: - 전 과정 기록 50쪽 (docs/종합기술문서.pdf) | fix | 8·22행 '실측 기각', 12·17행 '발견', '미보고'가 README와 어긋난다(DC-10) |
| R-E/mlkem-quic-amplification/README.md | 8367 | ML-KEM과 QUIC handshake 측정: 2026 R&E, 강원과학고등학교. 신레오, 정도현, 황요한. 지도 이현미. | keep | 해석 절이 이미 정정돼 있다(7·13행) |
| R-E/mlkem-quic-amplification/UPLOAD_GUIDE.md | 2151 | 깃허브 업로드 방법: Private으로 만드세요. 미발표 연구입니다. | archive | 별도 리포 업로드 안내. R-E 안에서는 쓰이지 않는다 |
| R-E/mlkem-quic-amplification/data/README.md | 1001 | 데이터 안내: 0 개요 / 1 개괄 / 2 임계정밀 / 3 RTT / 4 재현성 / 5 이론대조 / 6 한계 / 7 선행연구9편 / 8 padding인과 | keep | 자료 설명 |
| R-E/mlkem-quic-amplification/docs/2026-09-14_연구문서_정정안.md | 27437 | 학술 동아리 연구문서 정정안: 검토일: 2026-09-14. 대상: ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구. | keep | 팀 문서 정정의 근거. ERRATA_frozen_generations.md가 링크한다 |
| R-E/mlkem-quic-amplification/docs/README.md | 1098 | 문서 안내: - 0부 개요·핵심 결과 | fix | 18행 'H1 기각'은 원본 PDF 목차라 옆에 정정 표시만 더한다 |
| R-E/pq_afec/README.md | 33007 | pq_afec: QUIC handshake Initial 비행 FEC (정도현): R&E 「ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC 연구」의 | keep | 동결. em dash 45개, emoji 16개, ** 391개로 문체가 가장 어긋나지만 고치지 않는다(DC-22). 154·164·371행 오류는 ERRATA_frozen_generations.md에 |
| R-E/pq_afec/docs/C1 서버 피드백 설계.md | 6276 | C1 : 서버 수신 피드백 (탐색 없는 손실 관측): 2026-08-23 설계. 구현 전. 근거는 (a) 외부 알고리즘 조사 5영역, | merge | 구현 전 설계. SPEC_v3.3.1.md 7절이 현재 상태(c1_status.md)와 함께 대체한다 |
| R-E/pq_afec/docs/PADFEC v2 명세.md | 54851 | PAD-FEC v2 명세 : 양자 인식 first flight 설계: v1(고정 m parity)에서 v2(δ·m 두 지렛대)로. 2026-08-20. | merge | gen-2 정본. 비용식과 기호를 SPEC_v3.3.1.md 1·4절의 출발점으로 쓴다. 동결이라 본문은 고치지 않고 오류는 ERRATA_frozen_generations.md에 적는다(7절 '새로 만든 것', 508·522·765행) |
| R-E/pq_afec/docs/PADFEC 실측 보고서.md | 44914 | PAD-FEC 실측 보고서: QUIC handshake Initial 비행을 위한 소거정정 부호 : 설계·구현·측정 | merge | p6가 2026-08-21 뒤로 안 돌아 10-01 결과(p1 69.0 B)를 반영하지 못했다. 수치는 시점과 함께 RESULTS_by_generation.md 2절로, 어긋남은 ERRATA_frozen_generations.md로 |
| R-E/pq_afec/docs/다음 세션 인계.md | 40534 | 다음 세션 인계 : PAD-FEC: 이 문서 하나만 읽으면 이어서 작업할 수 있게 쓴 것이다. | archive | 2026-09-08 작업 메모. 15·16행 '복구까지 덤으로', 1절 읽는 순서가 낡았다. ERRATA_frozen_generations.md에 표시 |
| R-E/pq_afec/docs/선행연구 대조.md | 28780 | 선행연구 대조 : 무엇이 있었고, 우리는 무엇이 새로운가: 2026-08-28 전면 개정. 2026-08-19 의 방향 전환(증폭 credit → parity 전환)에 | merge | A 부는 CLAIMS.md 선행연구 절의 원고다. B 부 323~327행 '같은 credit을 사면서 복구까지'는 금지 표현이라 ERRATA_frozen_generations.md에 적는다 |
| R-E/pq_afec/docs/수정 대기 목록.md | 30548 | 수정 대기 목록 : 알고리즘 · 계기 · 문서: 작성 2026-08-26 22:5x · 작성 배경: 도현님 지시 "알고리즘 전체 부분에서 어떤 점을 수정해야 하고 | archive | 2026-08~09 작업 메모. 미해결처럼 읽히지만 대부분 처리됐다. 현재 목록으로 인용하지 않는다 |
| R-E/pq_afec/docs/실측 결과표.md | 9289 | 실측 결과표 (자동 생성): 이 파일은 experiments/e14_report.py가 experiments/results/.json에서 생성한다. 직접 고치지 말 것 : 고쳐야 하면 실험을 다시 돌 | archive | 방향 전환 전 v1 실측 기록. 동결 |
| R-E/pq_afec/docs/실측 보고서.md | 35685 | ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC : 실측 보고서: R&E 과제 계획서 「연구 내용 1~4」의 실행 결과. | archive | 방향 전환 전 v1 실측 기록. 동결 |
| R-E/pq_afec/docs/실측대조_스윕1.md | 5986 | 실측 대조 : 1차 스윕(sweep1) vs 우리 모델: 원자료: sweep1_results.xlsx (팀 실측, 2026-08-13, TLS 1.3 over TCP, | archive | 방향 전환 전 v1 실측 기록. 동결 |
| R-E/pq_afec/docs/실험 연결 계획.md | 6874 | 실험 연결 계획 : 수집할 데이터와 연결할 것들: 계획서 「연구 내용 1(ML-KEM 성능 분석)·2(실험 환경 구축)·4(성능 평가)」의 | archive | 방향 전환 전 v1 실측 기록. 동결 |
| R-E/pq_afec/docs/실험환경 대조.md | 5663 | 실험 환경 대조: title: 실험 환경 대조 : 명세서 vs 이 기계 | merge | 환경 표를 REPRODUCE.md로 합친다. 65행 Kali 표기는 ERRATA_frozen_generations.md에 적는다 |
| R-E/pq_afec/docs/알고리즘 명세 v0.1.md | 33746 | PQ-AFEC 알고리즘 명세 v0.1: 정본은 docs\PADFEC v2 명세.md 다. 2026-08-19 에 연구 질문이 바뀌었고 | archive | 머리에 '정본 아님' 경고가 이미 있다. v0.2 260행 '어떻게 틀려도'는 ERRATA_frozen_generations.md에 적는다 |
| R-E/pq_afec/docs/알고리즘 명세 v0.2.md | 22831 | PQ-AFEC 알고리즘 명세 v0.2 : 목적지별 통계 캐시: 정본은 docs\PADFEC v2 명세.md 다. 2026-08-19 에 연구 질문이 바뀌었고 | archive | 머리에 '정본 아님' 경고가 이미 있다. v0.2 260행 '어떻게 틀려도'는 ERRATA_frozen_generations.md에 적는다 |
| R-E/pq_afec/docs/이어서 작업 프롬프트.md | 3795 | 이어서 작업 프롬프트: 새 세션 첫 메시지에 아래 블록을 그대로 붙여넣으면 된다. | archive | v0.2 시점 세션 프롬프트('지금부터 v0.2다', 검증 40개). 독자용이 아니다 |
| R-E/pq_afec/docs/할 일 목록.md | 27921 | 할 일 목록 : 도현님이 해야 하는 작업 전부: 작성 2026-08-26 23:2x · 지시: "이런 것들 전부 다 자세하고 세세하게 하나하나 전부 다 기록해. | archive | 2026-08~09 작업 메모. 미해결처럼 읽히지만 대부분 처리됐다. 현재 목록으로 인용하지 않는다 |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md | 12829 | PAD-FEC v3 M1 재확증 프로토콜 (큰cert 2%, v2-m1 대 m4L3): 작성 2026-10-02. g3/RESULT_stage0.md의 "다음" 1번 항목을 실행하는 측정이다. 봉인 파일은 g3/SEAL_m1confirm.json이다. | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage0.md | 13839 | PAD-FEC v3 0단계 프로토콜: 기제 확인 (고정 팔): 작성 2026-10-02. 근거 문서는 C:/dev/codex_handoff/state/evo/verdict_v3.md이고, 이 파일의 조건, 팔, 표본 수, 1-RTT  | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md | 48107 | PAD-FEC v3 2단계 프로토콜: gen-2 auto 대 gen-3 auto 본 비교: 상태: 봉인본이다. 15절의 H 추첨 결과와 H 예측표는 게이트 통과 뒤 2026-10-02 12:26 KST에 채웠고, 그 뒤 --seal로 봉인했다. 측정은 봉인 뒤에 | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen3/g3/RESULT_m1confirm.md | 2482 | M1 재확증 결과 (다중 선행 credit, ℓ=3): 측정 2026-10-02 11:00 KST 전후, 약 2분 12초. 봉인 g3/SEAL_m1confirm.json sealed_utc 2026-10-02T01:52:58Z | keep | 봉인 목록에 든 파일. 고치지 않는다 |
| R-E/pq_afec_gen3/g3/RESULT_stage0.md | 6221 | PAD-FEC v3 0단계 결과 (기제 확인, 고정 팔): 측정 2026-10-02 09:46~10:32 KST, WSL Ubuntu, 같은 netns 안에 gen-2 서버(동결 바이너리 d98b05d7…, :44433)와 g3  | keep | 봉인 목록에 든 파일. 고치지 않는다 |
| R-E/pq_afec_gen3/g3/RESULT_stage2.md | 5486 | PAD-FEC v3 2단계 결과: gen-2 auto 대 v3 auto: 봉인 g3/SEAL_stage2.json(sealed_utc 2026-10-02T03:27:08Z, 파일 29개). 1회차 12:31~16:24 KST(22조건, 380블 | keep | 봉인 목록에 든 파일. 고치지 않는다 |
| R-E/pq_afec_gen3/g3/policy3_reference.md | 15643 | policy3 기준 벡터: Go 이식 대조 자료: g3/policy3_reference.json은 padfec3/learn3.py와 padfec3/decide3.py가 내는 답을 고정해 둔 파일이다. Go 쪽 experi | merge | J3와 학습층의 기준 설명. SPEC_v3.3.1.md 4·5절의 출발점. 원본은 동결 |
| R-E/pq_afec_gen31/g3/GEN31_CHANGES.md | 9380 | gen3.1 변경 기록 (X4, 2026-10-02) | keep | 봉인 목록에 든 파일. 고치지 않는다. 절대 링크 18개(GEN31_CHANGES)도 그대로 둔다 |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md | 12829 | PAD-FEC v3 M1 재확증 프로토콜 (큰cert 2%, v2-m1 대 m4L3): 작성 2026-10-02. g3/RESULT_stage0.md의 "다음" 1번 항목을 실행하는 측정이다. 봉인 파일은 g3/SEAL_m1confirm.json이다. | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage0.md | 13839 | PAD-FEC v3 0단계 프로토콜: 기제 확인 (고정 팔): 작성 2026-10-02. 근거 문서는 C:/dev/codex_handoff/state/evo/verdict_v3.md이고, 이 파일의 조건, 팔, 표본 수, 1-RTT  | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md | 48107 | PAD-FEC v3 2단계 프로토콜: gen-2 auto 대 gen-3 auto 본 비교: 상태: 봉인본이다. 15절의 H 추첨 결과와 H 예측표는 게이트 통과 뒤 2026-10-02 12:26 KST에 채웠고, 그 뒤 --seal로 봉인했다. 측정은 봉인 뒤에 | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md | 50890 | PAD-FEC v3.1 3단계 프로토콜: gen-2 auto 대 v3.1 auto 확증 비교: 상태: 초안이다. 봉인 전이고 3단계 측정은 없다. 15절의 H 추첨 결과와 H 예측표는 빈칸 표식(러너의 TODO_MARK, 단계 번호가 붙은 TODO 괄호)으로 비워  | keep | 봉인 파일(SEAL_*.json 목록). 한 바이트도 고치지 않는다 |
| R-E/pq_afec_gen31/g3/RESULT_m1confirm.md | 2482 | M1 재확증 결과 (다중 선행 credit, ℓ=3): 측정 2026-10-02 11:00 KST 전후, 약 2분 12초. 봉인 g3/SEAL_m1confirm.json sealed_utc 2026-10-02T01:52:58Z | keep | 봉인 목록에 든 파일. 고치지 않는다 |
| R-E/pq_afec_gen31/g3/RESULT_stage0.md | 6221 | PAD-FEC v3 0단계 결과 (기제 확인, 고정 팔): 측정 2026-10-02 09:46~10:32 KST, WSL Ubuntu, 같은 netns 안에 gen-2 서버(동결 바이너리 d98b05d7…, :44433)와 g3  | keep | 봉인 목록에 든 파일. 고치지 않는다 |
| R-E/pq_afec_gen31/g3/RESULT_stage3.md | 15462 | PAD-FEC v3.1 3단계 결과: gen-2 auto 대 v3.1 auto: 봉인 g3/SEAL_stage3.json(sealed_utc 2026-10-02T10:35:43Z, 파일 31개, 봉인 파일 sha256 6b452790…). 1회차 20 | keep | H1 원문. 동결. initial cwnd 단서는 ERRATA_frozen_generations.md와 CLAIMS.md가 붙인다 |
| R-E/pq_afec_gen31/g3/policy3_reference.md | 21857 | policy3 기준 벡터: Go 이식 대조 자료 (v3.1): g3/policy3_reference.json은 padfec3/layout.py, padfec3/learn3.py, padfec3/decide3.py가 내는 답을 고정해  | merge | J3와 학습층의 기준 설명. SPEC_v3.3.1.md 4·5절의 출발점. 원본은 동결 |
| R-E/pq_afec_gen32/README.md | 9765 | PAD-FEC v3.2 development: 이 폴더는 C:\dev\pq_afec_gen31의 v3.1 소스에서 만든 개발 사본이다. 정책 버전은 v3.2-dev, 저장 상태 버전은 3이다. v3.1의 측정 자료와  | keep | v3.2 기록. 동결. RESULTS_by_generation.md 5절이 링크한다 |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/README.md | 2070 | v3.2 followup validation: 2026년 10월 3일의 후속 검증이다. 자동 후보의 parity 예산, 실패 시 학습·목적지 캐시 상태 보존, 캐시 입력 검사와 빌드 소스 격리를 수정했다. 합성 적응  | keep | v3.2 기록. 동결. RESULTS_by_generation.md 5절이 링크한다 |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md | 7107 | 학술 동아리 알고리즘 추가 개선 기록: 2026년 10월 3일, PAD-FEC v3.2-dev의 후속 수정이다. 첫 개발 커밋 d3a9764f75ac6b7e2a1891f4154ed806bc8017ec 이후 후보 | keep | v3.2 기록. 동결. RESULTS_by_generation.md 5절이 링크한다 |
| R-E/pq_afec_gen32/g3/development_validation/README.md | 1007 | v3.2 development validation: 최신 검증은 2026년 10월 3일 후속 수정(2026-10-03-followup/README.md)에 있다. Python 109개와 하위 검사 367개, Go 101개, | keep | v3.2 기록. 동결. RESULTS_by_generation.md 5절이 링크한다 |
| R-E/pq_afec_gen32/g3/development_validation/initial-validation.md | 1839 | v3.2 development validation: 2026년 10월 3일에 검사한 v3.2-dev 개발본이다. 학습을 생략한 관측의 위험률 전이, 중앙값 잔차 감시, 입력·캐시 검증과 과거 실행기의 격리를 수정했다. 새  | keep | v3.2 기록. 동결. RESULTS_by_generation.md 5절이 링크한다 |

## 2. 최종 문서 구조 제안

원칙. `docs/` 아래 111개는 옮기지 않는다(DC-21 기본값). 코드 6곳이 경로로 읽고(`zero_variance.py:21`, `bench_m1_family.py:242`, `ge_reference_report.py:136`, `ge_world_diagnostic.py:47`, `uplink_reference_report.py:137`, `uplink_world_diagnostic.py:51`), 검증 JSON 약 800개가 `docs/*.md` 경로를 적고 있어서다. 정본 7개를 새로 써서 `docs/` 맨 위에 두고, 기존 조각은 색인이 "작성 시점 기록"으로 분류한다. 정본은 gen33에서 쓰고 R-E로 내보낸다. 정본은 저장소 안에 있는 파일만 인용하며, R-E 사본에 없는 `g3/v33/validation` 원자료는 "로컬 보존"이라고 적는다.

새 파일 일곱 개: `docs/README.md`, `docs/SPEC_v3.3.1.md`, `docs/RESULTS_by_generation.md`, `docs/CLAIMS.md`, `docs/REPRODUCE.md`, `docs/GLOSSARY.md`, `docs/ERRATA_frozen_generations.md`. 그리고 루트 `README.md`(gen33)와 `R-E/README.md`를 이 일곱 개로 연결한다.

### docs/README.md (색인, 약 150줄)

1. 이 저장소가 무엇인가: 세 문장. 2. 읽는 순서: README, SPEC, RESULTS, CLAIMS, REPRODUCE. 3. 정본 표. 4. 세대 표(gen-2, v3.0, v3.1, v3.2-dev, v3.3.1-dev, 폴더, 측정 여부). 5. 기록 문서 읽는 규칙: `docs/` 조각은 작성 시점 기록이고 "활성 L1", "상태 4", "커밋하지 않았다", "HEAD d67717d9b"는 그때 사실이다. 6. 전체 문서 표: 이 파일 1절을 줄인 것(이름, 한 줄, 분류). 7. 저장소 밖 자료 위치: `C:\dev\padfec_archive`, `C:\dev\codex_handoff\v33`, `g3/v33/validation` 원자료, 그리고 이 자료들은 정도현 노트북에만 있다는 사실.

가져오는 곳: 이 파일 1절, `README.md` 3행, `R-E/README.md` 세대 표, `V33FIX_docs_hygiene.md` 107행(못 한 일 G-E5).

### docs/SPEC_v3.3.1.md (알고리즘 명세)

| 절 | 내용 | 가져오는 곳 |
|---|---|---|
| 0 범위 | POLICY_VERSION v3.3.1-dev, STATE_VERSION 11, Go `padfec3.cache3/11`, gen_id `v3.3-dev`가 세대 이름인 이유. 측정 0건 표시 | `padfec3/learn3.py:25-26`, `genconfig.json`, `generation_paths.md` 3행 |
| 1 문제와 기호 | amplification limit, B, S, P, W, k, δ, L, T, m, n_need, u, RTT. 모든 기호 한 표 | `PADFEC v2 명세.md` 1절, gen31 `policy3_reference.md` |
| 2 행동과 first flight 배치 | (δ, L, T), 송신 순서, 후보 생성, 1452 B 상한과 W 한계 표(k1·2·3·4에서 1407·1401·1395·1389) | `padfec3/layout.py` send_order·datagram_sizes, `padfec3/decide3.py` levers_s·candidates3, `V33FIX_policy.md` 1·5절, `J7_wire_contract.md` |
| 3 와이어 형식 | parity datagram 구조, 모형 W+39+6k와 실제 W+22+6k+CID의 차이(34~46 B), XOR(m=1)과 Cauchy RS | `R3_codec_format.md`, `J7_wire_contract.md`, `padfec/codec.py`, `qamp.go` buildParity |
| 4 비용 모형 J3 | evaluate, outcomes, response_term, race_branches, n_need, preflight_bytes(A_pre 41 B), 동점 규칙. 비용 모형의 알려진 오차 | `padfec3/layout.py`, gen31 `policy3_reference.md`, `GEN31_CHANGES.md`, `PADFEC v2 명세.md` 3절, `J1_tail_design.md`, `J3_reference_result.md` |
| 5 learning layer | 격자 posterior, hazard, c1_seen 표지, none 경로(이진 likelihood, EPS 0.01, 건너뛰는 관측), c1 경로(datagram likelihood, 3등급, CLASS_EPS 1e-3) | `V33FIX_policy.md` 1절, `L1_learning.md`, `L1_observation_contract.md`, gen32 `README.md`, `README.md` 35~41행 |
| 6 결정 규칙 | decide3 순서, guard 벌점, 16번째 재평가, b0, cold, 입력 검증 | `V33FIX_policy.md` "상태와 결정 규칙의 순서", `L3_monitor_design.md`, `padfec3/decide3.py` |
| 7 C1 회신 | 판본 3 내용, 비표준·비인증 평문, 비용 0 가정, 위협 모형 | `c1_status.md`, `c1_threat_model.md`, gen-2 `C1 서버 피드백 설계.md`, `T4_observation_contract.md` |
| 8 서버와 테스트베드 | decodeConn, hold 기본 off, 복호기 상한, oob, 재전송 모양, profile sealed31, 토큰·resumption 팔 | `T1`~`T6` 계약, `M1_hold_contract.md`, `V33FIX_testbed.md`, `T7_conditions_v31.md` |
| 9 Go 거울과 관문 | policy3.go, policy3_l1.go, gate_v3_parity, gate_l1_go가 무엇을 비교하나 | `V33FIX_policy_go.md` |
| 10 상태 직렬화 | v11 필드와 거부 규칙 | `V33FIX_policy.md` 19행 |
| 11 한계 | W 1406·k≥2에서 parity 없음, 세계가 정책 상수를 공유, C1 비표준, quic-go 단일 스택, IW 32 | `V33FIX_policy.md` 5절, `V33FIX_evaluation.md` 7·8절, `worldsim.md` 지원 범위, `REPORT_CLAIMS_v33.md` 12행 |
| 12 세대 변경 표 | gen-2에서 v3.3.1까지 무엇이 왜 바뀌었나 | `GEN31_CHANGES.md`, gen32 `README.md`, `RESULT_stage0.md`, `V33FIX_policy.md` |

### docs/RESULTS_by_generation.md (세대별 결과)

| 절 | 내용 | 가져오는 곳 |
|---|---|---|
| 0 읽는 법 | 근거 등급 네 칸: 봉인 실측, 개발 실측, 시뮬레이션, 구현 검증 | `V33FIX_evaluation.md` 머리말 |
| 1 2026-08 팀 측정 | 경계 관측, 12.0%·10.4%는 분모 문제로 재현 안 됨 | `mlkem-quic-amplification/README.md`, `2026-09-14_연구문서_정정안.md` |
| 2 gen-2 | 최종 triage 18 통과, p8 p10 p15 p17 p18 p20 미통과, p6 안 돔. 주요 수치와 시점(p18 51.82 ms, 용량 부등식 60.0 B와 69.0 B) | `experiments/state/fixloop_triage.json`(로컬), `REPORT_CLAIMS_v33.md` 28·30·51행, `PADFEC 실측 보고서.md` |
| 3 v3.0 | 0단계, m1confirm, 2단계 | gen3 `RESULT_stage0.md`, `RESULT_m1confirm.md`, `RESULT_stage2.md` |
| 4 v3.1 | 3단계 H1~H4, 두 회차 값, 업링크 대가, 다섯 단서 | gen31 `RESULT_stage3.md`, `REPORT_CLAIMS_v33.md` 9~26행 |
| 5 v3.2-dev | 측정 없음, 구현 검사만 | gen32 `README.md`, `development_validation/` |
| 6 v3.3과 v3.3.1 | L1 판정, none 회귀 B6 +6.37 ms, v3.3.1 재판정, 절대 목표 미달, 세계의 남은 근사. 측정 과제가 돌면 여기 추가 | `V33FIX_evaluation.md`, `L1_precision.md`, `V33FIX_world.md`, `g3/v33/V33FIX_benchmark_v1.json` |
| 7 시험한 후보 표 | L2 L3 L5 J1 J3 J5 J6 J7 J8 M1 M4 O2 O3 O4: 무엇을 시험했나, 상태(LOOP_STATE), 왜 채택 안 했나, 근거 문서. "기각" 대신 "미채택", "보류"를 구분 | 각 `*_disposition.md`, `*_result.md` |
| 8 재지 않은 것 | X1, X9, X6 등 미측정 목록 | `state/LOOP_STATE.json`, `REPORT_CLAIMS_v33.md` 표 |
| 9 수치 출처 표 | 문서에 쓴 숫자마다 파일과 필드 | DC-12가 복사한 증거 |

### docs/CLAIMS.md (주장 범위)

1. 쓸 수 있는 말: H1 문장과 다섯 단서, 조건 표(`REPORT_CLAIMS_v33.md` 9~24행), 26행 H2·H3·H4, v3.3.1 문장(178~184·207~215행). 2. 쓰면 안 되는 말: 표 하나로 합친다(36~53행, 186~195행, 217~228행)에 빠진 네 행을 더한다: 어디서나 나쁘지 않다, 예측이 맞는다, 99.1% 적중, 유의차 없음을 기각으로. 3. 선행연구 위치: `선행연구 대조.md` A 부, 50행. 4. 바이트 계수 규범: 55~59행. 5. 인증서 크기 대응: 61~95행. 6. p3 표류와 TTLB: 97~112행. 7. 표현 규칙: 미채택과 기각 구분, 측정 종류 표시, 시점 표시. 볼트 행 번호와 `CONTEXT.md` 인용은 문장으로 풀거나 저장소 안 근거로 바꾼다.

### docs/REPRODUCE.md (재현 절차)

1. 환경: Windows Python 3.14, `wsl -d Ubuntu`, Go 1.26.6, quic-go v0.61.0, 함정(Kali 기본 배포판, `MSYS_NO_PATHCONV`). 가져오는 곳: `실험환경 대조.md`, `README.md` 43~58행. 2. Python 시험: 명령, 현재 수, 출력이 저장소 안에 쓰는 경로 경고. `S5_test_hygiene.md`. 3. Go 빌드와 시험: `build_gen33.sh`, HOME 분리, 현재 수, SKIP 2개 조건. `V33FIX_policy_go.md` 8절, `S5_test_hygiene.md` 57·61행. 4. Python·Go 관문: `gate_v3_parity.py`, `gate_l1_go.py`, 설치본 확인 방법. `README.md` 72~77행. 5. 시뮬레이션 재판정: `v33fix_rejudge.py`, `v33fix_j6_rejudge.py`, 원자료 위치. `V33FIX_evaluation.md` 176·189행. 6. 봉인 대조: `verify_seals`, autocrlf 경고. `S2_hygiene.md`. 7. 측정 조건: `T7_conditions_v31.md` 링크, D50의 W 1280. 8. R-E에 없는 것과 그 영향. `R-E/README.md` 55·57행. 9. 건드리면 깨지는 문서 표(DC-18).

### docs/GLOSSARY.md (용어와 ID)

1. 전문 용어 표: 원어, 뜻, 금지 번역어. 이 파일 3-6절. 2. 측정 이름: W0, W1, B1~B12, S_bigcert, S_rtt200, H_c6000, D_p11_2955, none, c1, ideal. `bench_v33.md`, `g3/v33/bench_protocol.json`. 3. 과제 ID: S, A, W, L, J, M, G, O, T, X, E, R 접두어의 뜻과 ID별 한 줄, 상태. `TASKS.md`, `EXTRA_TASKS.md`, `LOOP_STATE.json`. 4. 감사 ID: A1~A8-nn, A-E1~H-E, H-nn, Q-nn. `findings/FINDINGS_INDEX.md`, `findings/v33audit_2026-11-01`. 5. 결정 ID: D1~D52. `DECISIONS_NEEDED.md`. 6. 작업 이름: 반복 NN, 카드, 묶음 A-py, A-go, B, C, D, E, P, G, W, L, V33FIX.

### docs/ERRATA_frozen_generations.md (동결 문서 정정표)

동결 폴더는 고치지 않고 여기에 적는다. 1. 왜 고치지 않나: 봉인 해시, 바이트 일치 기록. 2. 정정 표: `REPORT_CLAIMS_v33.md` 118~172행의 35행을 옮기고 이 감사가 찾은 행을 더한다(DC-07 fix 칸). 3. 작업 메모 표시: 다음 세션 인계, 이어서 작업 프롬프트, 할 일 목록, 수정 대기 목록은 2026-08~09 메모. 4. 봉인 문서의 알려진 문구 결함: `PROTOCOL_stage3.md` 3행 '초안', gen31이 상속한 stage0·stage2 봉인 범위.


## 3. 부록: 전수 위치

### 3-1. 시험 수가 적힌 곳

직접 잰 현재 값은 R-E 사본에서 pytest 1862 passed, 2 skipped, 32 deselected, 하위 17656, Go PASS 266, SKIP 2, FAIL 0이다(이 감사가 스크래치 사본에서 실행). 아래에서 '현재'로 읽히는 줄만 고치고, 나머지는 당시 값이라 둔다.

| 위치 | 값 | 처리 |
|---|---|---|
| gen33 README.md:54 | 1792 passed | 고침 |
| gen33 docs/REPORT_CLAIMS_v33.md:149 | 1792개 | 고침 |
| gen33 docs/REPORT_CLAIMS_v33.md:241 | 1792개 | 고침 |
| gen33 docs/V33FIX_docs_hygiene.md:37 | 1792통과 | 당시 값으로 둠 |
| gen33 docs/V33FIX_docs_hygiene.md:52 | 1792 passed | 당시 값으로 둠 |
| gen33 docs/V33FIX_docs_hygiene.md:101 | 1792 passed | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy.md:121 | 1792 passed | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy.md:123 | 1855 passed | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy_go.md:111 | pytest(다른 묶음 변경이 섞인 작업 트리) / 1855 | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy_go.md:157 | pytest(Windows) / 1862 | 당시 값으로 둠 |
| gen33 docs/V33FIX_world.md:125 | 1855 통과 | 당시 값으로 둠 |
| R-E/README.md:55 | 1862개 | 고침 |
| gen33 README.md:54 | Go는 PASS 231 | 고침 |
| gen33 README.md:54 | PASS 231 | 고침 |
| gen33 docs/M4_cache_result.md:26 | Go 시험(PASS 231 | 당시 값으로 둠 |
| gen33 docs/S5_test_hygiene.md:19 | Go 시험(PASS 231 | 당시 값으로 둠 |
| gen33 docs/S5_test_hygiene.md:57 | Go 시험 수(PASS 231 | 당시 값으로 둠 |
| gen33 docs/S5_test_hygiene.md:57 | Go 231 | 당시 값으로 둠 |
| gen33 docs/S5_test_hygiene.md:59 | go_test.txt(PASS 231 | 당시 값으로 둠 |
| gen33 docs/S5_test_hygiene.md:61 | PASS 265 | 당시 값으로 둠 |
| gen33 docs/S5_test_hygiene.md:61 | PASS 266 | 당시 값으로 둠 |
| gen33 docs/V33FIX_docs_hygiene.md:52 | Go "PASS 231 | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy_go.md:107 | PASS 260 | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy_go.md:134 | PASS 265 | 당시 값으로 둠 |
| gen33 docs/V33FIX_policy_go.md:150 | PASS 266 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:112 | PASS 249 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:128 | Go 시험은 PASS 231 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:128 | Go 231 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:128 | PASS 249 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:149 | PASS 249 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:268 | pass 266 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:292 | PASS 266 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:314 | Go231시험"을 "PASS 231 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:314 | go_test.txt는 PASS 231 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:326 | PASS 265 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:326 | PASS 266 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:388 | Go 시험이 PASS 266 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:391 | Go 231 | 당시 값으로 둠 |
| gen33 docs/V33FIX_testbed.md:409 | Go 시험(PASS 231 | 당시 값으로 둠 |
| gen33 g3/v33/baseline/S0_baseline.md:9 | Go / vet 통과, 시험 101 | 당시 값으로 둠 |

### 3-2. 저장소 밖 자료를 가리키는 인용 수 (gen33)

`codex_handoff`, `LOOP_STATE`, `DECISIONS_NEEDED`, `MORNING_REPORT`, `JOURNAL.md`, `EXTRA_TASKS`, `TASKS.md`, `CONTEXT.md`, 볼트 단어 수와 절대 경로 수다.

| 문서 | handoff·볼트 | 절대 경로 |
|---|---:|---:|
| docs/REPORT_CLAIMS_v33.md | 51 | 3 |
| docs/V33FIX_testbed.md | 16 | 34 |
| docs/V33FIX_docs_hygiene.md | 23 | 15 |
| docs/V33FIX_world.md | 18 | 15 |
| docs/PUBLISH_PROCEDURE.md | 9 | 12 |
| docs/V33FIX_policy.md | 10 | 10 |
| docs/V33FIX_bench_rules.md | 9 | 8 |
| README.md | 2 | 13 |
| docs/V33FIX_policy_go.md | 4 | 11 |
| g3/v33/baseline/S0_baseline.md | 4 | 7 |
| docs/S5_test_hygiene.md | 2 | 6 |
| docs/bench_v33.md | 2 | 5 |
| g3/v33/archive/S1_archive.md | 2 | 5 |
| docs/S2_hygiene.md | 1 | 6 |
| docs/generation_paths.md | 1 | 5 |
| g3/v33/evidence/EVIDENCE.md | 2 | 4 |
| docs/v33_action_pool.md | 2 | 4 |
| docs/V33FIX_evaluation.md | 3 | 2 |
| docs/J6_disposition.md | 3 | 1 |
| docs/T6_result.md | 2 | 1 |
| docs/J3_diagnostic_plan.md | 2 | 1 |
| docs/O2_world_result.md | 2 | 1 |
| docs/T6_retrans_contract.md | 2 | 1 |
| docs/T3_comparison_contract.md | 2 | 1 |
| docs/M4_revisit_policy_contract.md | 2 | 1 |
| docs/J5_world_diagnostic_plan.md | 2 | 1 |
| docs/J3_reference_result.md | 2 | 1 |
| docs/T5_decoder_result.md | 2 | 0 |
| docs/L1_learning.md | 1 | 1 |
| docs/L1_precision.md | 1 | 1 |
| docs/M1_world_validity.md | 1 | 1 |
| docs/T2_followup_mapping.md | 1 | 0 |
| docs/J1_disposition.md | 1 | 0 |
| docs/J3_trace_result.md | 1 | 0 |
| docs/O4_reference_result.md | 0 | 1 |
| g3/v33/evidence/A0_coverage.md | 1 | 0 |
| docs/T7_conditions_v31.md | 0 | 1 |
| docs/L1_observation_contract.md | 1 | 0 |
| docs/T5_udp_result.md | 1 | 0 |

### 3-3. 저장소 어디에도, 루프 자료에도 없는 인용

백틱 경로를 저장소 경로, 파일 기준 상대 경로, 파일 이름으로 찾고, 그래도 없으면 `C:\dev\codex_handoff`까지 찾은 결과다. 경로로 못 찾은 인용 합계 340건 중 파일 이름으로는 저장소에 있는 것 160건, 루프 자료에만 있는 것 122건, 어디에도 없는 것 58건이다. 58건에는 봉인 문서의 산출물 이름과 설명용 예시가 섞여 있다.

| 위치 | 인용 |
|---|---|
| gen33 docs/REPORT_CLAIMS_v33.md:99 | R_E_중간.pptx |
| gen33 docs/V33FIX_evaluation.md:17 | runs\L3_joint_action_pool_v1 |
| gen33 docs/V33FIX_evaluation.md:17 | runs\L1_action_pool_precision_v2 |
| gen33 docs/V33FIX_policy.md:159 | runs\v33fix\P\first_round\ |
| gen33 docs/V33FIX_policy.md:171 | findings\v33audit_2026-11-01 |
| gen33 docs/V33FIX_policy_go.md:15 | .receipt.json |
| gen33 docs/V33FIX_policy_go.md:94 | v3gate\v3ref.json |
| gen33 docs/V33FIX_policy_go.md:117 | v3gate\v3ref.json |
| gen33 docs/V33FIX_policy_go.md:127 | v3gate\v3ref.json |
| gen33 docs/V33FIX_testbed.md:264 | extra_unlisted.go |
| gen33 docs/V33FIX_testbed.md:403 | wsl_staging_head_out.txt |
| gen33 docs/V33FIX_world.md:157 | exact_diff.py |
| gen33 docs/V33FIX_world.md:157 | exact_diff_out.txt |
| gen33 docs/V33FIX_world.md:157 | diag_sha.py |
| gen33 docs/V33FIX_world.md:157 | diag_sha_out.txt |
| gen33 docs/c1_status.md:3 | C1 서버 피드백 설계.md |
| R-E/README.md:19 | afec/ |
| R-E/README.md:19 | padfec/ |
| R-E/README.md:55 | g3/v33/validation |
| R-E/README.md:57 | experiments/state/ |
| R-E/docs/audit-2026-09-14/추가검토_정책비교_검증설계.md:7 | p17_holdout_audit.json |
| R-E/docs/audit-2026-09-14/추가검토_정책비교_검증설계.md:16 | design_evidence.json |
| R-E/mlkem-quic-amplification/docs/2026-09-14_연구문서_정정안.md:17 | 연구문서_검토목록.csv |
| R-E/mlkem-quic-amplification/docs/2026-09-14_연구문서_정정안.md:52 | ML-KEM_1단계_측정수치_v2.xlsx |
| R-E/pq_afec/docs/C1 서버 피드백 설계.md:4 | scratchpad/sim_feedback.py |
| R-E/pq_afec/docs/C1 서버 피드백 설계.md:4 | sim_adaptive_value.py |
| R-E/pq_afec/docs/다음 세션 인계.md:38 | 알고리즘 명세 v0.1/v0.2.md |
| R-E/pq_afec/docs/다음 세션 인계.md:92 | p15_units.오염_겹쳐돌아_20260826_1655.jsonl |
| R-E/pq_afec/docs/다음 세션 인계.md:598 | 06 세션 로그\2026-08-28 신레오 보고 검증과 버스트 한계.md |
| R-E/pq_afec/docs/수정 대기 목록.md:202 | v0.2.md |
| R-E/pq_afec/docs/수정 대기 목록.md:234 | v0.2.md |
| R-E/pq_afec/docs/이어서 작업 프롬프트.md:49 | 02 작업 규칙\작업하며 기록하고 스스로 피드백하기.md |
| R-E/pq_afec/docs/할 일 목록.md:30 | 06 세션 로그\2026-09-07 PAD-FEC 전량 재현과 코드 감사.md |
| R-E/pq_afec/docs/할 일 목록.md:166 | experiments/p13 |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md:43 | experiments/state/ |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_meta.json |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_status.json |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_incidents.jsonl |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md:179 | _units.jsonl |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md:253 | _status.json |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md:253 | _incidents.jsonl |
| R-E/pq_afec_gen31/g3/GEN31_CHANGES.md:30 | C:/dev/pq_afec_gen31/g3/verify_gen31.sh |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md:43 | experiments/state/ |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_meta.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_status.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_incidents.jsonl |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md:179 | _units.jsonl |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md:253 | _status.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md:253 | _incidents.jsonl |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md:227 | _units.jsonl |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md:298 | _status.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md:298 | _incidents.jsonl |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md:47 | gen32_followup_verification.json |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md:47 | gen32_followup_go_python_parity.json |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md:47 | gen32_followup_adaptation_summary.json |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md:47 | gen32_followup_adaptation_multiseed.json |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md:47 | gen32_followup_saved_journal_replay.json |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md:49 | 학술_알고리즘_v3_2_추가개선.zip |

### 3-4. 루프 자료에만 있는 인용

| 위치 | 인용 | 실제 위치(C:\dev\codex_handoff 아래) |
|---|---|---|
| gen33 docs/M1_world_validity.md:17 | W\round2\r3_lead0_scan_out.txt | v33/runs/v33fix/W/round2/r3_lead0_scan_out.txt |
| gen33 docs/M1_world_validity.md:17 | W\round2\r3_lead0_verify_N1000.txt | v33/runs/v33fix/W/round2/r3_lead0_verify_N1000.txt |
| gen33 docs/PUBLISH_PROCEDURE.md:7 | hashrefs.json | v33/runs/v33fix/P/scripts/hashrefs.json |
| gen33 docs/PUBLISH_PROCEDURE.md:7 | JOURNAL.md | v33/state/JOURNAL.md |
| gen33 docs/PUBLISH_PROCEDURE.md:7 | runs\MORNING_REPORT.md | v33/runs/MORNING_REPORT.md |
| gen33 docs/PUBLISH_PROCEDURE.md:40 | userpath_counts.json | v33/runs/v33fix/P/scripts/userpath_counts.json |
| gen33 docs/PUBLISH_PROCEDURE.md:40 | scripts\scrub_check.json | v33/runs/v33fix/P/scripts/scrub_check.json |
| gen33 docs/PUBLISH_PROCEDURE.md:40 | scrub_check.json | v33/runs/v33fix/P/scripts/scrub_check.json |
| gen33 docs/REPORT_CLAIMS_v33.md:5 | codex_handoff_v33_meta.tar | v33/runs/v33fix/L/first_round_E/codex_handoff_v33_meta.tar |
| gen33 docs/REPORT_CLAIMS_v33.md:174 | G-claims-frame.md | v33/findings/v33audit_2026-11-01/G-claims-frame.md |
| gen33 docs/V33FIX_bench_rules.md:45 | power_out.jsonl | v33/runs/v33fix/W/C_round1/power_out.jsonl |
| gen33 docs/V33FIX_bench_rules.md:45 | power_verify_out.txt | v33/runs/v33fix/W/C_verify/power_verify_out.txt |
| gen33 docs/V33FIX_docs_hygiene.md:3 | A-integrity.md | v33/findings/v33audit_2026-11-01/A-integrity.md |
| gen33 docs/V33FIX_docs_hygiene.md:3 | G-claims-frame.md | v33/findings/v33audit_2026-11-01/G-claims-frame.md |
| gen33 docs/V33FIX_docs_hygiene.md:3 | H-coverage.md | v33/findings/v33audit_2026-11-01/H-coverage.md |
| gen33 docs/V33FIX_docs_hygiene.md:27 | codex_handoff_v33_meta.tar | v33/runs/v33fix/L/first_round_E/codex_handoff_v33_meta.tar |
| gen33 docs/V33FIX_docs_hygiene.md:29 | p1cap.py | v33/runs/v33fix/P/first_round/D/p1cap.py |
| gen33 docs/V33FIX_docs_hygiene.md:33 | h1holm.py | v33/runs/v33fix/P/first_round/D/h1holm.py |
| gen33 docs/V33FIX_docs_hygiene.md:37 | spacing_fix.py | v33/runs/v33fix/P/first_round/D/spacing_fix.py |
| gen33 docs/V33FIX_docs_hygiene.md:37 | token_check.py | v33/runs/v33fix/P/first_round/D/token_check.py |
| gen33 docs/V33FIX_docs_hygiene.md:88 | JOURNAL.md | v33/state/JOURNAL.md |
| gen33 docs/V33FIX_docs_hygiene.md:88 | MORNING_REPORT.md | v33/runs/MORNING_REPORT.md |
| gen33 docs/V33FIX_docs_hygiene.md:88 | hashref2.py | v33/runs/v33fix/P/first_round/D/hashref2.py |
| gen33 docs/V33FIX_docs_hygiene.md:88 | hashrefs.json | v33/runs/v33fix/P/scripts/hashrefs.json |
| gen33 docs/V33FIX_docs_hygiene.md:88 | JOURNAL.md | v33/state/JOURNAL.md |
| gen33 docs/V33FIX_docs_hygiene.md:88 | MORNING_REPORT.md | v33/runs/MORNING_REPORT.md |
| gen33 docs/V33FIX_docs_hygiene.md:88 | hashref2.py | v33/runs/v33fix/P/first_round/D/hashref2.py |
| gen33 docs/V33FIX_docs_hygiene.md:121 | cr_count.json | v33/runs/v33fix/P/scripts/cr_count.json |
| gen33 docs/V33FIX_evaluation.md:7 | compare_all.json | v33/runs/v33fix/A-eval/compare_all.json |
| gen33 docs/V33FIX_evaluation.md:7 | b6_repetition_plan_v1.json | v33/runs/v33fix/A-eval/b6_repetition_plan_v1.json |
| gen33 docs/V33FIX_evaluation.md:7 | b6_repetition_v2.json | v33/runs/v33fix/A-eval/b6_repetition_v2.json |
| gen33 docs/V33FIX_evaluation.md:9 | b6_repetition_v2.json | v33/runs/v33fix/A-eval/b6_repetition_v2.json |
| gen33 docs/V33FIX_evaluation.md:31 | compare_seeds31_34.json | v33/runs/v33fix/A-eval/compare_seeds31_34.json |
| gen33 docs/V33FIX_evaluation.md:189 | compare_all.json | v33/runs/v33fix/A-eval/compare_all.json |
| gen33 docs/V33FIX_evaluation.md:189 | compare_seeds31_34.json | v33/runs/v33fix/A-eval/compare_seeds31_34.json |
| gen33 docs/V33FIX_evaluation.md:189 | b6_repetition_v2.json | v33/runs/v33fix/A-eval/b6_repetition_v2.json |
| gen33 docs/V33FIX_evaluation.md:189 | b6_repetition_v1.json | v33/runs/v33fix/A-eval/b6_repetition_v1.json |
| gen33 docs/V33FIX_policy.md:72 | runs\v33fix\P\SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_policy.md:110 | parity_w_limit_v2.json | v33/runs/v33fix/P/scripts/parity_w_limit_v2.json |
| gen33 docs/V33FIX_policy.md:110 | parity_w_limit_old.py | v33/runs/v33fix/P/scripts/parity_w_limit_old.py |
| gen33 docs/V33FIX_policy.md:110 | parity_w_limit_old.json | v33/runs/v33fix/P/scripts/parity_w_limit_old.json |
| gen33 docs/V33FIX_policy.md:136 | NOTDONE_ALL.md | v33/runs/v33fix/workflow_reports/NOTDONE_ALL.md |
| gen33 docs/V33FIX_policy.md:136 | SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_policy.md:145 | scripts\run_old.py | v33/runs/v33fix/P/scripts/run_old.py |
| gen33 docs/V33FIX_policy.md:145 | run_old_out2.txt | v33/runs/v33fix/P/scripts/run_old_out2.txt |
| gen33 docs/V33FIX_policy.md:157 | compare_all.json | v33/runs/v33fix/A-eval/compare_all.json |
| gen33 docs/V33FIX_policy.md:157 | b6_repetition_plan_v1.json | v33/runs/v33fix/A-eval/b6_repetition_plan_v1.json |
| gen33 docs/V33FIX_policy.md:157 | b6_repetition_v2.json | v33/runs/v33fix/A-eval/b6_repetition_v2.json |
| gen33 docs/V33FIX_policy.md:175 | scripts\run_old_scrub.py | v33/runs/v33fix/P/scripts/run_old_scrub.py |
| gen33 docs/V33FIX_policy_go.md:50 | D-rejected-learning.md | v33/findings/v33audit_2026-11-01/D-rejected-learning.md |
| gen33 docs/V33FIX_policy_go.md:94 | runs\v33fix\P\SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_policy_go.md:100 | final2\gate_l1_main.json | v33/runs/v33fix/P/first_round/A-go/final2/gate_l1_main.json |
| gen33 docs/V33FIX_policy_go.md:101 | final2\gate_l1_fresh.json | v33/runs/v33fix/P/first_round/A-go/final2/gate_l1_fresh.json |
| gen33 docs/V33FIX_policy_go.md:104 | final2\gate_v3.json | v33/runs/v33fix/P/first_round/A-go/final2/gate_v3.json |
| gen33 docs/V33FIX_policy_go.md:105 | v32_vs_new.py | v33/runs/v33fix/P/first_round/A-go/v32_vs_new.py |
| gen33 docs/V33FIX_policy_go.md:106 | final2\vet.txt | v33/runs/v33fix/G/round2/attempt1/out/after1/vet.txt |
| gen33 docs/V33FIX_policy_go.md:138 | vet.txt | v33/runs/v33fix/G/round2/attempt1/out/after1/vet.txt |
| gen33 docs/V33FIX_policy_go.md:160 | SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_testbed.md:5 | F-go-testbed.md | v33/findings/v33audit_2026-11-01/F-go-testbed.md |
| gen33 docs/V33FIX_testbed.md:5 | A-integrity.md | v33/findings/v33audit_2026-11-01/A-integrity.md |
| gen33 docs/V33FIX_testbed.md:5 | B-active-algorithm.md | v33/findings/v33audit_2026-11-01/B-active-algorithm.md |
| gen33 docs/V33FIX_testbed.md:5 | H-coverage.md | v33/findings/v33audit_2026-11-01/H-coverage.md |
| gen33 docs/V33FIX_testbed.md:170 | e2e.sh | v33/runs/v33fix/G/round1_B/e2e.sh |
| gen33 docs/V33FIX_testbed.md:170 | binaries.txt | v33/runs/v33fix/G/round1_B/out/e2e/binaries.txt |
| gen33 docs/V33FIX_testbed.md:170 | sealed.server.json | v33/runs/v33fix/G/round1_B/out/e2e/sealed.server.json |
| gen33 docs/V33FIX_testbed.md:227 | make_mutants.py | v33/runs/v33fix/G/round1_B/make_mutants.py |
| gen33 docs/V33FIX_testbed.md:227 | run_mutants.sh | v33/runs/v33fix/G/round1_B/run_mutants.sh |
| gen33 docs/V33FIX_testbed.md:239 | NOTDONE_ALL.md | v33/runs/v33fix/workflow_reports/NOTDONE_ALL.md |
| gen33 docs/V33FIX_testbed.md:255 | round2\oneline_check.sh | v33/runs/v33fix/G/round2/oneline_check.sh |
| gen33 docs/V33FIX_testbed.md:257 | round2\build_script_check.sh | v33/runs/v33fix/G/round2/build_script_check.sh |
| gen33 docs/V33FIX_testbed.md:276 | round2\make_mutants.py | v33/runs/v33fix/G/round1_B/make_mutants.py |
| gen33 docs/V33FIX_testbed.md:276 | round2\run_mutants.sh | v33/runs/v33fix/G/round1_B/run_mutants.sh |
| gen33 docs/V33FIX_testbed.md:276 | round2\out\mutants_summary.txt | v33/runs/v33fix/G/round2/attempt1/out/mutants_summary.txt |
| gen33 docs/V33FIX_testbed.md:294 | round2\attempt1\out\mutants_summary.txt | v33/runs/v33fix/G/round2/attempt1/out/mutants_summary.txt |
| gen33 docs/V33FIX_testbed.md:318 | workflow_reports\E-loop.md | v33/runs/v33fix/workflow_reports/E-loop.md |
| gen33 docs/V33FIX_testbed.md:318 | round2\reclone_verify_seals.json | v33/runs/v33fix/G/round2/reclone_verify_seals.json |
| gen33 docs/V33FIX_testbed.md:337 | round2\e2e_g.sh | v33/runs/v33fix/G/round2/e2e_g.sh |
| gen33 docs/V33FIX_testbed.md:377 | SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_testbed.md:391 | MORNING_REPORT.md | v33/runs/MORNING_REPORT.md |
| gen33 docs/V33FIX_testbed.md:401 | runs\v33fix\G\comparison_fixture_original_first.patch | v33/runs/v33fix/G/comparison_fixture_original_first.patch |
| gen33 docs/V33FIX_testbed.md:411 | SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_world.md:35 | W\round2\r3_lead0_scan_out.txt | v33/runs/v33fix/W/round2/r3_lead0_scan_out.txt |
| gen33 docs/V33FIX_world.md:35 | W\round2\r3_lead0_scan_nobypass_out.txt | v33/runs/v33fix/W/round2/r3_lead0_scan_nobypass_out.txt |
| gen33 docs/V33FIX_world.md:35 | r3_count_nobypass_out.txt | v33/runs/v33fix/W/round2/r3_count_nobypass_out.txt |
| gen33 docs/V33FIX_world.md:75 | pkt_probe_exact_l1_out.txt | v33/runs/v33fix/W/round2/pkt_probe_exact_l1_out.txt |
| gen33 docs/V33FIX_world.md:84 | round2\n4096_check_out.txt | v33/runs/v33fix/W/round2/n4096_check_out.txt |
| gen33 docs/V33FIX_world.md:113 | W\round2\m1_cost_diag.py | v33/runs/v33fix/W/C_round1/m1_cost_diag.py |
| gen33 docs/V33FIX_world.md:129 | W\SHA256SUMS.txt | v33/runs/v33fix/G/SHA256SUMS.txt |
| gen33 docs/V33FIX_world.md:137 | round2\prefix_tests_summary.txt | v33/runs/v33fix/W/round2/prefix_tests_summary.txt |
| gen33 docs/V33FIX_world.md:137 | round2\r3_prefix_new_tests.txt | v33/runs/v33fix/W/round2/r3_prefix_new_tests.txt |
| gen33 docs/V33FIX_world.md:137 | r3_fixed_new_tests.txt | v33/runs/v33fix/W/round2/r3_fixed_new_tests.txt |
| gen33 docs/V33FIX_world.md:137 | round2\lead0_verify_after_N1000.txt | v33/runs/v33fix/W/round2/lead0_verify_after_N1000.txt |
| gen33 docs/V33FIX_world.md:137 | r3_lead0_verify_N1000.txt | v33/runs/v33fix/W/round2/r3_lead0_verify_N1000.txt |
| gen33 docs/V33FIX_world.md:137 | r3_retry_check_out.txt | v33/runs/v33fix/W/round2/r3_retry_check_out.txt |
| gen33 docs/V33FIX_world.md:137 | r3_retry_check_prefix_out.txt | v33/runs/v33fix/W/round2/r3_retry_check_prefix_out.txt |
| gen33 docs/V33FIX_world.md:139 | r3_lead0_scan_out.txt | v33/runs/v33fix/W/round2/r3_lead0_scan_out.txt |
| gen33 docs/V33FIX_world.md:139 | r3_lead0_scan_nobypass_out.txt | v33/runs/v33fix/W/round2/r3_lead0_scan_nobypass_out.txt |
| gen33 docs/V33FIX_world.md:139 | r3_count_nobypass_out.txt | v33/runs/v33fix/W/round2/r3_count_nobypass_out.txt |
| gen33 docs/V33FIX_world.md:141 | round2\compare_diag_out.txt | v33/runs/v33fix/W/round2/compare_diag_out.txt |
| gen33 docs/V33FIX_world.md:141 | r3_diag_compare_out.txt | v33/runs/v33fix/W/round2/r3_diag_compare_out.txt |
| gen33 docs/V33FIX_world.md:141 | r3_diag\diag_rerun.json | v33/runs/v33fix/W/round2/r3_diag/diag_rerun.json |
| gen33 docs/V33FIX_world.md:141 | round2\V33FIX_world_diag_v1.round1.json | v33/runs/v33fix/W/round2/V33FIX_world_diag_v1.round1.json |
| gen33 docs/V33FIX_world.md:143 | r3_pkt_probe_out.txt | v33/runs/v33fix/W/round2/r3_pkt_probe_out.txt |
| gen33 docs/V33FIX_world.md:143 | r3_pkt_probe_exact_l1_out.txt | v33/runs/v33fix/W/round2/r3_pkt_probe_exact_l1_out.txt |
| gen33 docs/V33FIX_world.md:143 | r3_n4096_check_out.txt | v33/runs/v33fix/W/round2/r3_n4096_check_out.txt |
| gen33 docs/V33FIX_world.md:153 | round2\r3_related_tests.txt | v33/runs/v33fix/W/round2/r3_related_tests.txt |
| gen33 docs/V33FIX_world.md:153 | related_tests.txt | v33/runs/v33fix/W/round2/related_tests.txt |
| gen33 docs/V33FIX_world.md:153 | round2\r3_frozen_check_out.txt | v33/runs/v33fix/W/round2/r3_frozen_check_out.txt |
| gen33 docs/V33FIX_world.md:153 | frozen_check_out.txt | v33/runs/v33fix/W/round2/frozen_check_out.txt |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_units.jsonl | v33/runs/s1_verify/check-qkjquw1x/dev_data/C/dev/pq_afec_gen3/experiments/state/g3_m1confirm_units.jsonl |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md:182 | g3/replay_g3_dev.json | v33/runs/preserved_test_files_v1/removed/10fb4744f4b94ef99a7e9c2b2170baf9/g3/replay_g3_dev.json |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md:258 | design_learning.md | state/evo/design_learning.md |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md:379 | g3/replay_g3_dev.json | v33/runs/preserved_test_files_v1/removed/10fb4744f4b94ef99a7e9c2b2170baf9/g3/replay_g3_dev.json |
| R-E/pq_afec_gen3/g3/RESULT_stage0.md:3 | experiments/state/g3_stage0_units.jsonl | v33/runs/s1_verify/check-qkjquw1x/dev_data/C/dev/pq_afec_gen3/experiments/state/g3_stage0_units.jsonl |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md:43 | g3_m1confirm_units.jsonl | v33/runs/s1_verify/check-qkjquw1x/dev_data/C/dev/pq_afec_gen3/experiments/state/g3_m1confirm_units.jsonl |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md:182 | g3/replay_g3_dev.json | v33/runs/preserved_test_files_v1/removed/10fb4744f4b94ef99a7e9c2b2170baf9/g3/replay_g3_dev.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md:258 | design_learning.md | state/evo/design_learning.md |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md:379 | g3/replay_g3_dev.json | v33/runs/preserved_test_files_v1/removed/10fb4744f4b94ef99a7e9c2b2170baf9/g3/replay_g3_dev.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md:37 | experiments/results/g31_probe.json | v33/runs/preserved_test_files_v1/removed/020e15bb8c44465a819f6e71f7e35444/experiments/results/g31_probe.json |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md:37 | experiments/state/g31_probe_console.log | v33/runs/preserved_test_files_v1/removed/020e15bb8c44465a819f6e71f7e35444/experiments/state/g31_probe_console.log |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md:232 | X7.md | codex_out/X7.md |
| R-E/pq_afec_gen31/g3/RESULT_stage0.md:3 | experiments/state/g3_stage0_units.jsonl | v33/runs/s1_verify/check-qkjquw1x/dev_data/C/dev/pq_afec_gen3/experiments/state/g3_stage0_units.jsonl |

### 3-5. '첫 비행' 파일별 수

정규식 `첫\s*비행` 231건. 보고서 원고 `C:\hwp_work\rne_final\tools\content.py`는 0건, `first flight` 15건이다.

| 문서 | 수 |
|---|---:|
| R-E/pq_afec/docs/PADFEC v2 명세.md | 19 |
| R-E/pq_afec/docs/PADFEC 실측 보고서.md | 16 |
| R-E/mlkem-quic-amplification/docs/2026-09-14_연구문서_정정안.md | 12 |
| gen33 docs/REPORT_CLAIMS_v33.md | 9 |
| gen33 docs/V33FIX_world.md | 9 |
| R-E/pq_afec/docs/C1 서버 피드백 설계.md | 7 |
| gen33 docs/L1_learning.md | 6 |
| gen33 docs/J1_tail_design.md | 5 |
| gen33 docs/J5_ge_contract.md | 5 |
| gen33 docs/J8_profiles.md | 5 |
| gen33 docs/L1_observation_contract.md | 5 |
| gen33 docs/M1_quic_queue_check.md | 5 |
| gen33 docs/c1_status.md | 5 |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage0.md | 5 |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage0.md | 5 |
| gen33 docs/J5_world_result.md | 4 |
| gen33 docs/M1_world_validity.md | 4 |
| R-E/pq_afec/README.md | 4 |
| R-E/pq_afec_gen3/g3/PROTOCOL_stage2.md | 4 |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage2.md | 4 |
| gen33 docs/J5_reference_result.md | 3 |
| gen33 docs/J5_world_diagnostic_plan.md | 3 |
| gen33 docs/J8_server_profile_contract.md | 3 |
| gen33 docs/O2_world_result.md | 3 |
| gen33 docs/O4_packetization_contract.md | 3 |
| gen33 docs/O4_reference_result.md | 3 |
| gen33 docs/T1_certificate_result.md | 3 |
| gen33 docs/T4_observation_contract.md | 3 |
| gen33 docs/worldsim.md | 3 |
| R-E/mlkem-quic-amplification/README.md | 3 |
| R-E/pq_afec_gen3/g3/PROTOCOL_m1confirm.md | 3 |
| R-E/pq_afec_gen3/g3/RESULT_stage0.md | 3 |
| R-E/pq_afec_gen31/g3/PROTOCOL_m1confirm.md | 3 |
| R-E/pq_afec_gen31/g3/PROTOCOL_stage3.md | 3 |
| R-E/pq_afec_gen31/g3/RESULT_stage0.md | 3 |
| R-E/pq_afec_gen31/g3/RESULT_stage3.md | 3 |
| gen33 docs/J6_disposition.md | 2 |
| gen33 docs/J8_downlink_result.md | 2 |
| gen33 docs/V33FIX_docs_hygiene.md | 2 |
| gen33 docs/V33FIX_testbed.md | 2 |
| gen33 docs/bench_v33.md | 2 |
| gen33 docs/server_support_signal.md | 2 |
| R-E/README.md | 2 |
| R-E/pq_afec_gen3/g3/RESULT_stage2.md | 2 |
| gen33 README.md | 1 |
| gen33 docs/J1_disposition.md | 1 |
| gen33 docs/J3_recovery_contract.md | 1 |
| gen33 docs/L5_disposition.md | 1 |
| gen33 docs/L5_server_response.md | 1 |
| gen33 docs/M1_evaluation_plan.md | 1 |
| gen33 docs/M1_hold_contract.md | 1 |
| gen33 docs/M1_mc_contract.md | 1 |
| gen33 docs/O3_reference_result.md | 1 |
| gen33 docs/O3_rtt_contract.md | 1 |
| gen33 docs/O4_current_k_contract.md | 1 |
| gen33 docs/O4_current_result.md | 1 |
| gen33 docs/O4_revisit_plan.md | 1 |
| gen33 docs/O4_token_result.md | 1 |
| gen33 docs/T1_certificate_contract.md | 1 |
| gen33 docs/T5_decoder_contract.md | 1 |
| gen33 docs/T7_conditions_v31.md | 1 |
| gen33 docs/V33FIX_evaluation.md | 1 |
| gen33 docs/V33FIX_policy_go.md | 1 |
| R-E/docs/audit-2026-09-14/추가검토_연구주장_근거표.md | 1 |
| R-E/docs/audit-2026-09-14/추가보완_작업기록.md | 1 |
| R-E/pq_afec/docs/선행연구 대조.md | 1 |
| R-E/pq_afec/docs/수정 대기 목록.md | 1 |
| R-E/pq_afec/docs/할 일 목록.md | 1 |
| R-E/pq_afec_gen3/g3/RESULT_m1confirm.md | 1 |
| R-E/pq_afec_gen31/g3/GEN31_CHANGES.md | 1 |
| R-E/pq_afec_gen31/g3/RESULT_m1confirm.md | 1 |
| R-E/pq_afec_gen32/README.md | 1 |
| R-E/pq_afec_gen32/g3/development_validation/2026-10-03-followup/report.md | 1 |

### 3-6. 같은 뜻의 여러 이름과 번역어 수

| 개념 | 표기별 수 | 대표어 제안 |
|---|---|---|
| first flight | 첫 비행 231, 둘째 비행 4, 서버 비행 36, first flight 1 | first flight, 둘째 flight, server first flight |
| parity | 패리티 524, parity 65 | parity |
| padding | 패딩 103, padding 8 | padding |
| credit | 신용 255, credit 11 | credit |
| handshake | 핸드셰이크 98, handshake 36 | handshake |
| amplification limit | 증폭 제한 24, 증폭 한도 3, 증폭 예산 23, 3배 한도 4, amplification 21 | amplification limit, 남은 양은 amplification budget |
| 원본 앞 parity | 선행 패리티 16, 선행 신용 21, lead 94, ℓ 125 | lead parity, 개수는 L |
| 원본 뒤 parity | 뒤 패리티 30, 뒤따르는 20, 복구 패리티 10, trail 20 | trailing parity, 개수는 T |
| big cert 조건 | 큰cert 141, 큰 인증서 9, S_bigcert 24, big-cert 70 | big-cert(S_bigcert: cert 16000 B, 2 Mbps, RTT 50 ms) |
| 감시 장치 | 감시층 25, 감시 벌점 2, guard 46, monitor 1 | guard |
| 학습 | 학습층 23, 손실 학습 9, 사후분포 40, 우도 138, 위험률 12, hazard 26 | learning layer, posterior, likelihood, hazard |
| 시뮬레이터 | 독립 세계 19, 독립 사건 세계 12, 세계 시뮬레이터 5, W0 28, W1 98 | W0 세계 시뮬레이터, W1 벤치 |
| C1 | C1 회신 58, 서버 피드백 4, shim 8 | C1 회신 |
| 경로 | none 경로 41, 기본 경로 5, c1 경로 31 | none 경로, c1 경로 |
| 세대 | gen-2 200, gen2 12, v2 98 | gen-2 |
| 왕복 | 왕복 81, 라운드 68 | round trip은 RTT로, 재시도는 재전송 round로 구분 |

### 3-7. 쓰면 안 되는 말 전수 판정

정규식과 넓힌 동의어로 찾은 뒤 문맥을 읽었다. G2는 R-E/pq_afec이다. '금지 문맥'은 금지 표나 부정문 안이라 문제없다는 뜻이다.

| 금지 말 | 금지 문맥 위치 | 문제 위치 | 처리 |
|---|---|---|---|
| v3.3이 v3.2보다 낫다 | REPORT_CLAIMS:188·189 | 없음 | 없음 |
| 실측으로 개선 확인 | REPORT_CLAIMS:188·219, V33FIX_evaluation:143, O4_current_replay_plan:9 | 없음 | 없음 |
| 같은 바이트가 credit과 복구를 함께 산다 | REPORT_CLAIMS:40·42, V33FIX_testbed:120, G2 README:116, PADFEC 실측 보고서:14 | G2 다음 세션 인계:15·16, G2 선행연구 대조:326·327 | 동결이라 ERRATA(DC-07) |
| 추가 비용 없는 FEC | REPORT_CLAIMS:51, 정정안:23·38·39·150, PADFEC 실측 보고서:13·48, 수정 대기:247 | 없음 | 없음 |
| 어디서나 나쁘지 않다 | gen3 RESULT_stage2:50, gen31 RESULT_stage3:93 | G2 알고리즘 명세 v0.2:260('어떻게 틀려도', 머리 경고 있음). REPORT_CLAIMS 금지 표에 행 없음 | ERRATA + CLAIMS 행 추가 |
| 예측이 맞는다 | gen31 RESULT_stage3:93 | REPORT_CLAIMS 금지 표에 행 없음 | CLAIMS 행 추가 |
| 적응이 이득을 냈다 | REPORT_CLAIMS:30·192, gen31 RESULT_stage3:93 | 없음 | 없음 |
| PQ handshake 증폭 병목을 우리가 밝혔다 | REPORT_CLAIMS:50, G2 선행연구 대조:26·106·145 | mlkem CHANGELOG:12·17('증폭 임계 발견', '미보고'), PADFEC v2 명세:881~886('새로 만든 것') | CHANGELOG 수정, 명세는 ERRATA |
| 단서 없는 재방문 이득 | REPORT_CLAIMS:38 | 없음(재방문 단어는 전부 T2·M4 기능 문맥) | 없음 |
| initial cwnd 단서 없는 큰 cert H1 | REPORT_CLAIMS:12·49 | R-E README:26·27, gen31 RESULT_stage3:12·36, gen3 RESULT_stage2 | README 수정, RESULT는 ERRATA |
| 99.1% 적중 | G2 다음 세션 인계:547, G2 할 일 목록:121(둘 다 단서 요구) | REPORT_CLAIMS 금지 표에 행 없음 | CLAIMS 행 추가 |
| 유의차 없음을 기각으로 | R-E README:41, mlkem README:13, 정정안:25·33, REPORT_CLAIMS:159(볼트 정정 표 안) | mlkem CHANGELOG:8·22, mlkem docs/README:18. REPORT_CLAIMS 금지 표에 행 없음 | DC-10 + CLAIMS 행 추가 |

`실측 보고서.md:24·237`의 '손실 독립성 기각'(58배), `PADFEC v2 명세.md:244·268·420`의 '상수 모형 기각', 봉인 프로토콜의 Holm '기각'은 실제 검정 결과라 문제가 아니다.
