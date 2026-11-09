# X1 개발 측정 결과

quic-go v0.61.0 테스트베드 한 곳, 합성 인증서, W 1280, 손실은 c2s만, initial congestion window 32 packet, 정책 입력 uplink는 netem 대역과 같음. development 측정이며 확증이 아니다. 모든 팔을 같은 gen33 서버에 붙였고 봉인 측정의 세대별 서버와 다르다.

실행 ID는 final_x1_iter027_20261107, 정책 판본은 v3.3.1-dev다.
결과 근거: `g3/v33/results/v33_dev_X1_final_x1_iter027_20261107.json`.

## 실행과 판정

| 항목 | 상태 |
|---|---|
| client_rows | pass |
| connection_collection | pass |
| explicit_flight | pass |
| ips | pass |
| m4L3_recovered | pass |
| no_feedback | pass |
| pad_recovered | pass |
| process_rc | pass |
| server_process | pass |
| server_stats | pass |
| server_uniform | pass |
| w_bound | pass |

실행 상태: 판정 통과. 통계 판정: 기술통계.

## HCT와 연결 비율

| 셀 | 팔 | 범위 | 행 수 | HCT 평균(ms) | HCT 95% 구간(ms) | 성공 HCT 평균(ms) | 실패 비율 | 1-RTT 비율 |
|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | m4L3 | 주 분석 | 1560 | 82.285956 | [81.621394, 82.950519] | 82.285956 | 0 | 0.933974 |
| bigcert_l2 | m4L3 | 번인 포함 전체 | 1560 | 82.285956 | [81.621394, 82.950519] | 82.285956 | 0 | 0.933974 |
| bigcert_l2 | m4L3 | 층 전체 c2s=2% s2c=0% | 1560 | 82.285956 | [81.621394, 82.950519] | 82.285956 | 0 | 0.933974 |
| bigcert_l2 | m4L3 | 층 주 분석 c2s=2% s2c=0% | 1560 | 82.285956 | [81.621394, 82.950519] | 82.285956 | 0 | 0.933974 |
| bigcert_l2 | trailing_junk4L3 | 주 분석 | 1560 | 87.037946 | [85.37227, 88.703621] | 87.037946 | 0 | 0.910897 |
| bigcert_l2 | trailing_junk4L3 | 번인 포함 전체 | 1560 | 87.037946 | [85.37227, 88.703621] | 87.037946 | 0 | 0.910897 |
| bigcert_l2 | trailing_junk4L3 | 층 전체 c2s=2% s2c=0% | 1560 | 87.037946 | [85.37227, 88.703621] | 87.037946 | 0 | 0.910897 |
| bigcert_l2 | trailing_junk4L3 | 층 주 분석 c2s=2% s2c=0% | 1560 | 87.037946 | [85.37227, 88.703621] | 87.037946 | 0 | 0.910897 |
| bigcert_l2 | pad4L3 | 주 분석 | 1560 | 87.08522 | [85.340644, 88.829796] | 87.08522 | 0 | 0.908974 |
| bigcert_l2 | pad4L3 | 번인 포함 전체 | 1560 | 87.08522 | [85.340644, 88.829796] | 87.08522 | 0 | 0.908974 |
| bigcert_l2 | pad4L3 | 층 전체 c2s=2% s2c=0% | 1560 | 87.08522 | [85.340644, 88.829796] | 87.08522 | 0 | 0.908974 |
| bigcert_l2 | pad4L3 | 층 주 분석 c2s=2% s2c=0% | 1560 | 87.08522 | [85.340644, 88.829796] | 87.08522 | 0 | 0.908974 |
| bigcert_l15 | m4L3 | 주 분석 | 1120 | 111.483561 | [107.640912, 115.326209] | 111.483561 | 0 | 0.583929 |
| bigcert_l15 | m4L3 | 번인 포함 전체 | 1120 | 111.483561 | [107.640912, 115.326209] | 111.483561 | 0 | 0.583929 |
| bigcert_l15 | m4L3 | 층 전체 c2s=15% s2c=0% | 1120 | 111.483561 | [107.640912, 115.326209] | 111.483561 | 0 | 0.583929 |
| bigcert_l15 | m4L3 | 층 주 분석 c2s=15% s2c=0% | 1120 | 111.483561 | [107.640912, 115.326209] | 111.483561 | 0 | 0.583929 |
| bigcert_l15 | trailing_junk4L3 | 주 분석 | 1120 | 136.362413 | [131.316923, 141.407902] | 136.362413 | 0 | 0.458929 |
| bigcert_l15 | trailing_junk4L3 | 번인 포함 전체 | 1120 | 136.362413 | [131.316923, 141.407902] | 136.362413 | 0 | 0.458929 |
| bigcert_l15 | trailing_junk4L3 | 층 전체 c2s=15% s2c=0% | 1120 | 136.362413 | [131.316923, 141.407902] | 136.362413 | 0 | 0.458929 |
| bigcert_l15 | trailing_junk4L3 | 층 주 분석 c2s=15% s2c=0% | 1120 | 136.362413 | [131.316923, 141.407902] | 136.362413 | 0 | 0.458929 |
| bigcert_l15 | pad4L3 | 주 분석 | 1120 | 146.601876 | [141.274665, 151.929086] | 146.601876 | 0 | 0.441964 |
| bigcert_l15 | pad4L3 | 번인 포함 전체 | 1120 | 146.601876 | [141.274665, 151.929086] | 146.601876 | 0 | 0.441964 |
| bigcert_l15 | pad4L3 | 층 전체 c2s=15% s2c=0% | 1120 | 146.601876 | [141.274665, 151.929086] | 146.601876 | 0 | 0.441964 |
| bigcert_l15 | pad4L3 | 층 주 분석 c2s=15% s2c=0% | 1120 | 146.601876 | [141.274665, 151.929086] | 146.601876 | 0 | 0.441964 |
| rtt200_l15 | m4L2 | 주 분석 | 320 | 229.401147 | [225.81761, 232.984684] | 229.401147 | 0 | 0.965625 |
| rtt200_l15 | m4L2 | 번인 포함 전체 | 320 | 229.401147 | [225.81761, 232.984684] | 229.401147 | 0 | 0.965625 |
| rtt200_l15 | m4L2 | 층 전체 c2s=15% s2c=0% | 320 | 229.401147 | [225.81761, 232.984684] | 229.401147 | 0 | 0.965625 |
| rtt200_l15 | m4L2 | 층 주 분석 c2s=15% s2c=0% | 320 | 229.401147 | [225.81761, 232.984684] | 229.401147 | 0 | 0.965625 |
| rtt200_l15 | pad4L2 | 주 분석 | 320 | 347.279528 | [306.038264, 388.520792] | 347.279528 | 0 | 0.671875 |
| rtt200_l15 | pad4L2 | 번인 포함 전체 | 320 | 347.279528 | [306.038264, 388.520792] | 347.279528 | 0 | 0.671875 |
| rtt200_l15 | pad4L2 | 층 전체 c2s=15% s2c=0% | 320 | 347.279528 | [306.038264, 388.520792] | 347.279528 | 0 | 0.671875 |
| rtt200_l15 | pad4L2 | 층 주 분석 c2s=15% s2c=0% | 320 | 347.279528 | [306.038264, 388.520792] | 347.279528 | 0 | 0.671875 |

## 서버 계수 비용

서버 수신량은 연결 전체의 bytes_in을 같은 범위의 클라이언트 행 수로 나눈다. 손실 조건에서도 이 값은 서버 수신량이다. first flight 바이트는 별도 클라이언트 진단이다.

| 셀 | 팔 | 범위 | 서버 계수 bytes_in(B) | 분모 행 수 | 서버 수신량(B/연결) | 원천 | 상태 | first flight 원본 평균(B) | first flight parity 평균(B) | first flight extra 평균(B) |
|---|---|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | m4L3 | 주 분석 | 16124410 | 1560 | 10336.160256 | server_delta.bytes_in | 확인 | 2560 | 5327.417949 | 5327.417949 |
| bigcert_l2 | m4L3 | 번인 포함 전체 | 16124410 | 1560 | 10336.160256 | server_delta.bytes_in | 확인 | 2560 | 5327.417949 | 5327.417949 |
| bigcert_l2 | trailing_junk4L3 | 주 분석 | 16571309 | 1560 | 10622.633974 | server_delta.bytes_in | 확인 | 2560 | 5327.630769 | 5327.630769 |
| bigcert_l2 | trailing_junk4L3 | 번인 포함 전체 | 16571309 | 1560 | 10622.633974 | server_delta.bytes_in | 확인 | 2560 | 5327.630769 | 5327.630769 |
| bigcert_l2 | pad4L3 | 주 분석 | 16543398 | 1560 | 10604.742308 | server_delta.bytes_in | 확인 | 2560 | 0 | 5327.771795 |
| bigcert_l2 | pad4L3 | 번인 포함 전체 | 16543398 | 1560 | 10604.742308 | server_delta.bytes_in | 확인 | 2560 | 0 | 5327.771795 |
| bigcert_l15 | m4L3 | 주 분석 | 10551290 | 1120 | 9420.794643 | server_delta.bytes_in | 확인 | 2560 | 5327.596429 | 5327.596429 |
| bigcert_l15 | m4L3 | 번인 포함 전체 | 10551290 | 1120 | 9420.794643 | server_delta.bytes_in | 확인 | 2560 | 5327.596429 | 5327.596429 |
| bigcert_l15 | trailing_junk4L3 | 주 분석 | 12141547 | 1120 | 10840.666964 | server_delta.bytes_in | 확인 | 2560 | 5327.167857 | 5327.167857 |
| bigcert_l15 | trailing_junk4L3 | 번인 포함 전체 | 12141547 | 1120 | 10840.666964 | server_delta.bytes_in | 확인 | 2560 | 5327.167857 | 5327.167857 |
| bigcert_l15 | pad4L3 | 주 분석 | 12163756 | 1120 | 10860.496429 | server_delta.bytes_in | 확인 | 2558.857143 | 0 | 5328.021429 |
| bigcert_l15 | pad4L3 | 번인 포함 전체 | 12163756 | 1120 | 10860.496429 | server_delta.bytes_in | 확인 | 2558.857143 | 0 | 5328.021429 |
| rtt200_l15 | m4L2 | 주 분석 | 4989242 | 320 | 15591.38125 | server_delta.bytes_in | 확인 | 2556 | 5326.95 | 5326.95 |
| rtt200_l15 | m4L2 | 번인 포함 전체 | 4989242 | 320 | 15591.38125 | server_delta.bytes_in | 확인 | 2556 | 5326.95 | 5326.95 |
| rtt200_l15 | pad4L2 | 주 분석 | 5115531 | 320 | 15986.034375 | server_delta.bytes_in | 확인 | 2560 | 0 | 5328.0375 |
| rtt200_l15 | pad4L2 | 번인 포함 전체 | 5115531 | 320 | 15986.034375 | server_delta.bytes_in | 확인 | 2560 | 0 | 5328.0375 |

g2auto의 클라이언트 parity 계수에는 client_parity_count_unreliable 표지를 둔다. 클라이언트 bytes_parity와 parity_sent는 비용에 더하지 않는다.

## 팔 간 비교

차이는 x 팔에서 y 팔을 뺀 값이다.

| 셀 | 대조 | x | y | 범위 | HCT 차이(ms) | 95% 구간(ms) | 독립 표본 수 | 자유도 | A/A | 자(ms) | 자 표류 | 판정 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | pad4L3_minus_m4L3 | pad4L3 | m4L3 | primary | 4.799263 | [2.90701, 6.691517] | 39 | 38 | A/A 적용 | 1.188556 | 미확인 | 차이 관측 |
| bigcert_l2 | trailing_junk_minus_parity | trailing_junk4L3 | m4L3 | primary | 4.751989 | [3.189512, 6.314466] | 39 | 38 | A/A 적용 | 1.188556 | 미확인 | 차이 관측 |
| bigcert_l15 | pad4L3_minus_m4L3 | pad4L3 | m4L3 | primary | 35.118315 | [28.625103, 41.611527] | 28 | 27 | A/A 없음 | 미확인 | A/A 없음 | 차이 관측 |
| bigcert_l15 | trailing_junk_minus_parity | trailing_junk4L3 | m4L3 | primary | 24.878852 | [18.129015, 31.628688] | 28 | 27 | A/A 없음 | 미확인 | A/A 없음 | 차이 관측 |
| rtt200_l15 | pad4L3_minus_m4L3 | pad4L2 | m4L2 | primary | 117.878381 | [77.992021, 157.764742] | 16 | 15 | A/A 없음 | 미확인 | A/A 없음 | 차이 관측 |

같은 대조의 1-RTT 비율과 서버 수신량 차이는 다음과 같다. 비율은 백분율로 환산하지 않았다.

| 셀 | 대조 | x | y | 범위 | 1-RTT 비율 차이 | 95% 구간(비율) | 서버 수신량 차이(B/연결) | 95% 구간(B/연결) |
|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | pad4L3_minus_m4L3 | pad4L3 | m4L3 | primary | -0.025 | [-0.044851, -0.005149] | 268.582051 | [193.151246, 344.012856] |
| bigcert_l2 | trailing_junk_minus_parity | trailing_junk4L3 | m4L3 | primary | -0.023077 | [-0.04133, -0.004824] | 286.473718 | [227.725364, 345.222072] |
| bigcert_l15 | pad4L3_minus_m4L3 | pad4L3 | m4L3 | primary | -0.141964 | [-0.182155, -0.101773] | 1439.701786 | [1272.015364, 1607.388208] |
| bigcert_l15 | trailing_junk_minus_parity | trailing_junk4L3 | m4L3 | primary | -0.125 | [-0.167378, -0.082622] | 1419.872321 | [1242.363482, 1597.38116] |
| rtt200_l15 | pad4L3_minus_m4L3 | pad4L2 | m4L2 | primary | -0.29375 | [-0.343237, -0.244263] | 394.653125 | [174.508496, 614.797754] |

first flight의 원본과 추가 바이트 차이는 클라이언트 행의 진단이다. 서버 수신량 비용과 구분하며 값은 x 팔에서 y 팔을 뺀 관측 차이다.

| 셀 | 대조 | x | y | 범위 | 원본 차이(B) | 추가 차이(B) | 합계 차이(B) | x 누락 행 | y 누락 행 |
|---|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | pad4L3_minus_m4L3 | pad4L3 | m4L3 | primary | 0 | 0.353846 | 0.353846 | {} | {} |
| bigcert_l2 | trailing_junk_minus_parity | trailing_junk4L3 | m4L3 | primary | 0 | 0.212821 | 0.212821 | {} | {} |
| bigcert_l15 | pad4L3_minus_m4L3 | pad4L3 | m4L3 | primary | -1.142857 | 0.425 | -0.717857 | {} | {} |
| bigcert_l15 | trailing_junk_minus_parity | trailing_junk4L3 | m4L3 | primary | 0 | -0.428571 | -0.428571 | {} | {} |
| rtt200_l15 | pad4L3_minus_m4L3 | pad4L2 | m4L2 | primary | 4 | 1.0875 | 5.0875 | {} | {} |

## 관측 범위

| 셀 | 팔 | 범위 | 유효 RTT 비율 | 실제 mean_idle_ms | idle 상태 | wait_plus_gap 진단(ms) | C1 경로 제외 |
|---|---|---|---|---|---|---|---|
| bigcert_l15 | m4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | m4L3 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | pad4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | pad4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | pad4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | pad4L3 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | pad4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | pad4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | trailing_junk4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | trailing_junk4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | trailing_junk4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | trailing_junk4L3 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | trailing_junk4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | trailing_junk4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | m4L3 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | pad4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | pad4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | pad4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | pad4L3 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | pad4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | pad4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | trailing_junk4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | trailing_junk4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | trailing_junk4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | trailing_junk4L3 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | trailing_junk4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | trailing_junk4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 전체 | 0.015625 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 번인 뒤 | 0.015625 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | m4L2 | c2s=15% s2c=0% | 0.015625 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | not_one_rtt | 0.454545 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | 전체 | 0.309375 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | 번인 뒤 | 0.309375 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | pad4L2 | c2s=15% s2c=0% | 0.309375 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | not_one_rtt | 0.942857 | 미확인 | 미확인 | 50 | false |

연결의 절대 시작·완료 시각이 없어 실제 mean_idle_ms는 null·미확인이다. feedback 대기와 설정 gap의 합은 wait_plus_gap 진단이며 실제 idle의 대체값이 아니다. X6의 실제 idle 차이 기준은 미확인으로 남긴다. C1은 표준 QUIC에 없는 서버 datagram 회신이다.

## 한계

토큰·resumption 기준선(X4), 업링크 오입력(X2), A_pre와 PTO 배수 탐침(X3), s2c 손실(X5), 다른 QUIC 스택(X7), initial congestion window 10(X8), 시간 상관 손실(E24), 중복 전송 기준선(dup), first flight 부풀리기(k-inflate), 서버 first flight 7.7~9.0 kB 띠와 Initial 확대 팔, H c6000, D_p15_4032, 7.8 kB 응답 TTLB는 재지 않았다.
