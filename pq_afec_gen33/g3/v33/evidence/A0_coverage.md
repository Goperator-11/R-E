# A0 감사 추적

coverage_check 연결 2개와 A0 카드 근거의 합집합 10개를 처리했다. 아래 '처리함'은 원자료 재현 범위이며, 정책·계측 수정은 표시한 후속 카드에 남아 있다. 근거 경로는 g3/v33/evidence 아래다. 7개 스크립트, 25개 입력 저널, 출처 자릿수 비교 45개를 재현했다.

| ID | 처리 |
|---|---|
| A7-11 | 처리함: 01_posterior_trajectories.json, 1,600위치 동일. 새 우도 구현은 다른 과제로 넘김: TASKS L1 및 W0 카드 |
| A2-01 | 처리함: 01_posterior_trajectories.json, 보호 행동의 손실 구별 실패 재현. 학습 변경은 다른 과제로 넘김: TASKS L1 카드 |
| A2-06 | 처리함: 02_baseline_contamination.json, 원자료 85/535 및 55/484. 새 라벨은 다른 과제로 넘김: TASKS L2 카드 |
| A1-01 | 처리함: 03_j3_decomposition.json, 검증 정정대로 꼬리 초과분 1.672236/4.289507 ms. 비용식 수정은 다른 과제로 넘김: TASKS J1 카드 |
| A1-02 | 처리함: 04_burst_model.json, p18 실패 대용 지표 0.040936, iid 0.000399, GE 0.042992 재현. 독립 세계는 W0, 정책 GE는 J5 카드로 넘김 |
| A5-07 | 처리함: 05_server_accounting.json 및 server_accounting.csv, 전 조건 182그룹. p11 l0 서버 parity 8,579/7,991 대 클라이언트 4,532/7,991. 계측 수정은 다른 과제로 넘김: TASKS T7 요구 3 |
| A4-01 | 처리함: 06_server_size_bins.json, n_need=12 1,799행과 유효 모형 11. 추정식 수정은 다른 과제로 넘김: TASKS L5 카드 |
| A1-09 | 처리함: 07_rtt200_probes.json, run1 g3auto 4,500행 모두 Initial 5개. 탐침 비용과 재전송 변경은 다른 과제로 넘김: TASKS J4/T6 카드 |
| A6-M02 | 처리함: 07_rtt200_probes.json, RTT unavailable 99.3333/99.4889/99.3556%. 원인 관측과 경고는 다른 과제로 넘김: TASKS T4/J4 카드 |
| A6-M01 | 처리함: 봉인 report-only를 실행하지 않는 독립 입력·출력 경로와 입력 SHA 기록. 전체 H1~H4 재계산은 다른 과제로 넘김: state/EXTRA_TASKS.md E1에 기록. 7개 통계 재현을 판정 전체 재현으로 부르지 않음 |
| A1-08 (보조 정정) | 처리함: 03_j3_decomposition.json, 고정 L3 실패 130/2,250, 관측 266.392615 ms 대 모형 233.444486 ms, 기여 차이 +1.209821 ms. 자동 팔은 분리. 실패 비용 수정은 다른 과제로 넘김: TASKS J3 카드 |

반올림 비교는 source_precision_checks.json에 있다. 모든 입력은 fingerprint 1개이며 중복·손상·형식 오류가 없다. Python 핵심 109개와 하위 375개, 다른 세대 경로 3개가 통과했다. 7개 분석 스크립트는 종료 코드 0이었다. 정책과 Go 코드는 바꾸지 않았다.
