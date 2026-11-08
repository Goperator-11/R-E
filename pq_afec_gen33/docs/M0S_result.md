# M0 개발 측정 결과

quic-go v0.61.0 테스트베드 한 곳, 합성 인증서, W 1280, 손실은 c2s만, initial congestion window 32 packet, 정책 입력 uplink는 netem 대역과 같음. development 측정이며 확증이 아니다. 이전 결과를 본 뒤 선커밋한 탐색 계획 final_bundle_v2의 측정이다.

실행 ID는 final_m0s_20261107, 정책 판본은 v3.3.1-dev다.
결과 근거: `g3/v33/results/v33_dev_M0_final_m0s_20261107.json`.

## 실행과 판정

| 항목 | 상태 |
|---|---|
| c1_arrivals | pass |
| c1_feedback_received | pass |
| c1_feedback_version | pass |
| c1_path | pass |
| client_rows | pass |
| connection_collection | pass |
| explicit_flight | pass |
| fec_parse_fail | pass |
| feedback_received_field | pass |
| feedback_wait_limit | pass |
| fixed_extra_byte_range | pass |
| fixed_first_flight_bytes | pass |
| hct_mean_range | pass |
| ips | pass |
| netem_config | pass |
| no_feedback | pass |
| none_path | pass |
| policy_uplink | pass |
| process_rc | pass |
| realized_loss | pass |
| recover_crc_fail | pass |
| recovered_positive | pass |
| server_process | pass |
| server_stats | pass |
| server_uniform | pass |
| success_rate | pass |
| w_bound | pass |

실행 상태: 판정 통과. 통계 판정: 기술통계.

## HCT와 연결 비율

| 셀 | 팔 | 범위 | 행 수 | HCT 평균(ms) | HCT 95% 구간(ms) | 성공 HCT 평균(ms) | 실패 비율 | 1-RTT 비율 |
|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | v33s_none | 주 분석 | 20 | 83.391 | 미확인 | 83.391 | 0 | 0.9 |
| bigcert_l2 | v33s_none | 번인 포함 전체 | 20 | 83.391 | 미확인 | 83.391 | 0 | 0.9 |
| bigcert_l2 | v33s_none | 층 전체 c2s=2% s2c=0% | 20 | 83.391 | 미확인 | 83.391 | 0 | 0.9 |
| bigcert_l2 | v33s_none | 층 주 분석 c2s=2% s2c=0% | 20 | 83.391 | 미확인 | 83.391 | 0 | 0.9 |
| bigcert_l2 | v33s_c1 | 주 분석 | 20 | 83.458 | 미확인 | 83.458 | 0 | 0.9 |
| bigcert_l2 | v33s_c1 | 번인 포함 전체 | 20 | 83.458 | 미확인 | 83.458 | 0 | 0.9 |
| bigcert_l2 | v33s_c1 | 층 전체 c2s=2% s2c=0% | 20 | 83.458 | 미확인 | 83.458 | 0 | 0.9 |
| bigcert_l2 | v33s_c1 | 층 주 분석 c2s=2% s2c=0% | 20 | 83.458 | 미확인 | 83.458 | 0 | 0.9 |
| bigcert_l2 | v33pre_c1 | 주 분석 | 20 | 80.8797 | 미확인 | 80.8797 | 0 | 0.95 |
| bigcert_l2 | v33pre_c1 | 번인 포함 전체 | 20 | 80.8797 | 미확인 | 80.8797 | 0 | 0.95 |
| bigcert_l2 | v33pre_c1 | 층 전체 c2s=2% s2c=0% | 20 | 80.8797 | 미확인 | 80.8797 | 0 | 0.95 |
| bigcert_l2 | v33pre_c1 | 층 주 분석 c2s=2% s2c=0% | 20 | 80.8797 | 미확인 | 80.8797 | 0 | 0.95 |
| bigcert_l2 | m4L3 | 주 분석 | 20 | 78.99855 | 미확인 | 78.99855 | 0 | 1 |
| bigcert_l2 | m4L3 | 번인 포함 전체 | 20 | 78.99855 | 미확인 | 78.99855 | 0 | 1 |
| bigcert_l2 | m4L3 | 층 전체 c2s=2% s2c=0% | 20 | 78.99855 | 미확인 | 78.99855 | 0 | 1 |
| bigcert_l2 | m4L3 | 층 주 분석 c2s=2% s2c=0% | 20 | 78.99855 | 미확인 | 78.99855 | 0 | 1 |
| bigcert_l15 | v33s_none | 주 분석 | 20 | 104.8478 | 미확인 | 104.8478 | 0 | 0.45 |
| bigcert_l15 | v33s_none | 번인 포함 전체 | 20 | 104.8478 | 미확인 | 104.8478 | 0 | 0.45 |
| bigcert_l15 | v33s_none | 층 전체 c2s=15% s2c=0% | 20 | 104.8478 | 미확인 | 104.8478 | 0 | 0.45 |
| bigcert_l15 | v33s_none | 층 주 분석 c2s=15% s2c=0% | 20 | 104.8478 | 미확인 | 104.8478 | 0 | 0.45 |
| bigcert_l15 | v33s_c1 | 주 분석 | 20 | 130.85135 | 미확인 | 130.85135 | 0 | 0.4 |
| bigcert_l15 | v33s_c1 | 번인 포함 전체 | 20 | 130.85135 | 미확인 | 130.85135 | 0 | 0.4 |
| bigcert_l15 | v33s_c1 | 층 전체 c2s=15% s2c=0% | 20 | 130.85135 | 미확인 | 130.85135 | 0 | 0.4 |
| bigcert_l15 | v33s_c1 | 층 주 분석 c2s=15% s2c=0% | 20 | 130.85135 | 미확인 | 130.85135 | 0 | 0.4 |
| bigcert_l15 | v33pre_c1 | 주 분석 | 20 | 120.5971 | 미확인 | 120.5971 | 0 | 0.5 |
| bigcert_l15 | v33pre_c1 | 번인 포함 전체 | 20 | 120.5971 | 미확인 | 120.5971 | 0 | 0.5 |
| bigcert_l15 | v33pre_c1 | 층 전체 c2s=15% s2c=0% | 20 | 120.5971 | 미확인 | 120.5971 | 0 | 0.5 |
| bigcert_l15 | v33pre_c1 | 층 주 분석 c2s=15% s2c=0% | 20 | 120.5971 | 미확인 | 120.5971 | 0 | 0.5 |
| bigcert_l15 | m4L3 | 주 분석 | 20 | 98.18245 | 미확인 | 98.18245 | 0 | 0.65 |
| bigcert_l15 | m4L3 | 번인 포함 전체 | 20 | 98.18245 | 미확인 | 98.18245 | 0 | 0.65 |
| bigcert_l15 | m4L3 | 층 전체 c2s=15% s2c=0% | 20 | 98.18245 | 미확인 | 98.18245 | 0 | 0.65 |
| bigcert_l15 | m4L3 | 층 주 분석 c2s=15% s2c=0% | 20 | 98.18245 | 미확인 | 98.18245 | 0 | 0.65 |
| rtt200_l15 | v33s_none | 주 분석 | 20 | 241.88685 | 미확인 | 241.88685 | 0 | 0.9 |
| rtt200_l15 | v33s_none | 번인 포함 전체 | 20 | 241.88685 | 미확인 | 241.88685 | 0 | 0.9 |
| rtt200_l15 | v33s_none | 층 전체 c2s=15% s2c=0% | 20 | 241.88685 | 미확인 | 241.88685 | 0 | 0.9 |
| rtt200_l15 | v33s_none | 층 주 분석 c2s=15% s2c=0% | 20 | 241.88685 | 미확인 | 241.88685 | 0 | 0.9 |
| rtt200_l15 | v33s_c1 | 주 분석 | 20 | 242.75555 | 미확인 | 242.75555 | 0 | 0.95 |
| rtt200_l15 | v33s_c1 | 번인 포함 전체 | 20 | 242.75555 | 미확인 | 242.75555 | 0 | 0.95 |
| rtt200_l15 | v33s_c1 | 층 전체 c2s=15% s2c=0% | 20 | 242.75555 | 미확인 | 242.75555 | 0 | 0.95 |
| rtt200_l15 | v33s_c1 | 층 주 분석 c2s=15% s2c=0% | 20 | 242.75555 | 미확인 | 242.75555 | 0 | 0.95 |
| rtt200_l15 | v33pre_c1 | 주 분석 | 20 | 246.8283 | 미확인 | 246.8283 | 0 | 0.9 |
| rtt200_l15 | v33pre_c1 | 번인 포함 전체 | 20 | 246.8283 | 미확인 | 246.8283 | 0 | 0.9 |
| rtt200_l15 | v33pre_c1 | 층 전체 c2s=15% s2c=0% | 20 | 246.8283 | 미확인 | 246.8283 | 0 | 0.9 |
| rtt200_l15 | v33pre_c1 | 층 주 분석 c2s=15% s2c=0% | 20 | 246.8283 | 미확인 | 246.8283 | 0 | 0.9 |
| rtt200_l15 | m4L2 | 주 분석 | 20 | 222.69095 | 미확인 | 222.69095 | 0 | 1 |
| rtt200_l15 | m4L2 | 번인 포함 전체 | 20 | 222.69095 | 미확인 | 222.69095 | 0 | 1 |
| rtt200_l15 | m4L2 | 층 전체 c2s=15% s2c=0% | 20 | 222.69095 | 미확인 | 222.69095 | 0 | 1 |
| rtt200_l15 | m4L2 | 층 주 분석 c2s=15% s2c=0% | 20 | 222.69095 | 미확인 | 222.69095 | 0 | 1 |
| p11_l0 | v33s_none | 주 분석 | 20 | 51.9211 | 미확인 | 51.9211 | 0 | 1 |
| p11_l0 | v33s_none | 번인 포함 전체 | 20 | 51.9211 | 미확인 | 51.9211 | 0 | 1 |
| p11_l0 | v33s_none | 층 전체 c2s=0% s2c=0% | 20 | 51.9211 | 미확인 | 51.9211 | 0 | 1 |
| p11_l0 | v33s_none | 층 주 분석 c2s=0% s2c=0% | 20 | 51.9211 | 미확인 | 51.9211 | 0 | 1 |
| p11_l0 | v33s_c1 | 주 분석 | 20 | 51.90395 | 미확인 | 51.90395 | 0 | 1 |
| p11_l0 | v33s_c1 | 번인 포함 전체 | 20 | 51.90395 | 미확인 | 51.90395 | 0 | 1 |
| p11_l0 | v33s_c1 | 층 전체 c2s=0% s2c=0% | 20 | 51.90395 | 미확인 | 51.90395 | 0 | 1 |
| p11_l0 | v33s_c1 | 층 주 분석 c2s=0% s2c=0% | 20 | 51.90395 | 미확인 | 51.90395 | 0 | 1 |
| p11_l0 | v33pre_c1 | 주 분석 | 20 | 51.9296 | 미확인 | 51.9296 | 0 | 1 |
| p11_l0 | v33pre_c1 | 번인 포함 전체 | 20 | 51.9296 | 미확인 | 51.9296 | 0 | 1 |
| p11_l0 | v33pre_c1 | 층 전체 c2s=0% s2c=0% | 20 | 51.9296 | 미확인 | 51.9296 | 0 | 1 |
| p11_l0 | v33pre_c1 | 층 주 분석 c2s=0% s2c=0% | 20 | 51.9296 | 미확인 | 51.9296 | 0 | 1 |
| p11_l0 | m4L3 | 주 분석 | 20 | 52.03535 | 미확인 | 52.03535 | 0 | 1 |
| p11_l0 | m4L3 | 번인 포함 전체 | 20 | 52.03535 | 미확인 | 52.03535 | 0 | 1 |
| p11_l0 | m4L3 | 층 전체 c2s=0% s2c=0% | 20 | 52.03535 | 미확인 | 52.03535 | 0 | 1 |
| p11_l0 | m4L3 | 층 주 분석 c2s=0% s2c=0% | 20 | 52.03535 | 미확인 | 52.03535 | 0 | 1 |

## 서버 계수 비용

서버 수신량은 연결 전체의 bytes_in을 같은 범위의 클라이언트 행 수로 나눈다. 손실 조건에서도 이 값은 서버 수신량이다. first flight 바이트는 별도 클라이언트 진단이다.

| 셀 | 팔 | 범위 | 서버 계수 bytes_in(B) | 분모 행 수 | 서버 수신량(B/연결) | 원천 | 상태 | first flight 원본 평균(B) | first flight parity 평균(B) | first flight extra 평균(B) |
|---|---|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | v33s_none | 주 분석 | 202049 | 20 | 10102.45 | server_delta.bytes_in | 확인 | 2560 | 5055.6 | 5055.6 |
| bigcert_l2 | v33s_none | 번인 포함 전체 | 202049 | 20 | 10102.45 | server_delta.bytes_in | 확인 | 2560 | 5055.6 | 5055.6 |
| bigcert_l2 | v33s_c1 | 주 분석 | 201042 | 20 | 10052.1 | server_delta.bytes_in | 확인 | 2560 | 5062 | 5062 |
| bigcert_l2 | v33s_c1 | 번인 포함 전체 | 201042 | 20 | 10052.1 | server_delta.bytes_in | 확인 | 2560 | 5062 | 5062 |
| bigcert_l2 | v33pre_c1 | 주 분석 | 203336 | 20 | 10166.8 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| bigcert_l2 | v33pre_c1 | 번인 포함 전체 | 203336 | 20 | 10166.8 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| bigcert_l2 | m4L3 | 주 분석 | 207364 | 20 | 10368.2 | server_delta.bytes_in | 확인 | 2560 | 5331.4 | 5331.4 |
| bigcert_l2 | m4L3 | 번인 포함 전체 | 207364 | 20 | 10368.2 | server_delta.bytes_in | 확인 | 2560 | 5331.4 | 5331.4 |
| bigcert_l15 | v33s_none | 주 분석 | 182280 | 20 | 9114 | server_delta.bytes_in | 확인 | 2560 | 5061.2 | 5061.2 |
| bigcert_l15 | v33s_none | 번인 포함 전체 | 182280 | 20 | 9114 | server_delta.bytes_in | 확인 | 2560 | 5061.2 | 5061.2 |
| bigcert_l15 | v33s_c1 | 주 분석 | 180833 | 20 | 9041.65 | server_delta.bytes_in | 확인 | 2560 | 5061.2 | 5061.2 |
| bigcert_l15 | v33s_c1 | 번인 포함 전체 | 180833 | 20 | 9041.65 | server_delta.bytes_in | 확인 | 2560 | 5061.2 | 5061.2 |
| bigcert_l15 | v33pre_c1 | 주 분석 | 178743 | 20 | 8937.15 | server_delta.bytes_in | 확인 | 2560 | 5062 | 5062 |
| bigcert_l15 | v33pre_c1 | 번인 포함 전체 | 178743 | 20 | 8937.15 | server_delta.bytes_in | 확인 | 2560 | 5062 | 5062 |
| bigcert_l15 | m4L3 | 주 분석 | 189558 | 20 | 9477.9 | server_delta.bytes_in | 확인 | 2560 | 5332.8 | 5332.8 |
| bigcert_l15 | m4L3 | 번인 포함 전체 | 189558 | 20 | 9477.9 | server_delta.bytes_in | 확인 | 2560 | 5332.8 | 5332.8 |
| rtt200_l15 | v33s_none | 주 분석 | 300244 | 20 | 15012.2 | server_delta.bytes_in | 확인 | 2560 | 5066.6 | 5066.6 |
| rtt200_l15 | v33s_none | 번인 포함 전체 | 300244 | 20 | 15012.2 | server_delta.bytes_in | 확인 | 2560 | 5066.6 | 5066.6 |
| rtt200_l15 | v33s_c1 | 주 분석 | 299849 | 20 | 14992.45 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| rtt200_l15 | v33s_c1 | 번인 포함 전체 | 299849 | 20 | 14992.45 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| rtt200_l15 | v33pre_c1 | 주 분석 | 310610 | 20 | 15530.5 | server_delta.bytes_in | 확인 | 2560 | 5066.6 | 5066.6 |
| rtt200_l15 | v33pre_c1 | 번인 포함 전체 | 310610 | 20 | 15530.5 | server_delta.bytes_in | 확인 | 2560 | 5066.6 | 5066.6 |
| rtt200_l15 | m4L2 | 주 분석 | 319969 | 20 | 15998.45 | server_delta.bytes_in | 확인 | 2560 | 5329 | 5329 |
| rtt200_l15 | m4L2 | 번인 포함 전체 | 319969 | 20 | 15998.45 | server_delta.bytes_in | 확인 | 2560 | 5329 | 5329 |
| p11_l0 | v33s_none | 주 분석 | 204404 | 20 | 10220.2 | server_delta.bytes_in | 확인 | 2560 | 5061 | 5061 |
| p11_l0 | v33s_none | 번인 포함 전체 | 204404 | 20 | 10220.2 | server_delta.bytes_in | 확인 | 2560 | 5061 | 5061 |
| p11_l0 | v33s_c1 | 주 분석 | 185372 | 20 | 9268.6 | server_delta.bytes_in | 확인 | 2560 | 4125.9 | 4125.9 |
| p11_l0 | v33s_c1 | 번인 포함 전체 | 185372 | 20 | 9268.6 | server_delta.bytes_in | 확인 | 2560 | 4125.9 | 4125.9 |
| p11_l0 | v33pre_c1 | 주 분석 | 185697 | 20 | 9284.85 | server_delta.bytes_in | 확인 | 2560 | 4128.35 | 4128.35 |
| p11_l0 | v33pre_c1 | 번인 포함 전체 | 185697 | 20 | 9284.85 | server_delta.bytes_in | 확인 | 2560 | 4128.35 | 4128.35 |
| p11_l0 | m4L3 | 주 분석 | 210996 | 20 | 10549.8 | server_delta.bytes_in | 확인 | 2560 | 5324.8 | 5324.8 |
| p11_l0 | m4L3 | 번인 포함 전체 | 210996 | 20 | 10549.8 | server_delta.bytes_in | 확인 | 2560 | 5324.8 | 5324.8 |

g2auto의 클라이언트 parity 계수에는 client_parity_count_unreliable 표지를 둔다. 클라이언트 bytes_parity와 parity_sent는 비용에 더하지 않는다.

## 팔 간 비교

차이는 x 팔에서 y 팔을 뺀 값이다.

## 관측 범위

| 셀 | 팔 | 범위 | 유효 RTT 비율 | 실제 mean_idle_ms | idle 상태 | wait_plus_gap 진단(ms) | C1 경로 제외 |
|---|---|---|---|---|---|---|---|
| bigcert_l15 | m4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | m4L3 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | m4L3 | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33pre_c1 | 전체 | 1 | 미확인 | 미확인 | 29.66807 | false |
| bigcert_l15 | v33pre_c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 29.66807 | false |
| bigcert_l15 | v33pre_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v33pre_c1 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 29.66807 | false |
| bigcert_l15 | v33pre_c1 | one_rtt | 1 | 미확인 | 미확인 | 55.468506 | false |
| bigcert_l15 | v33pre_c1 | not_one_rtt | 1 | 미확인 | 미확인 | 1.00092 | false |
| bigcert_l15 | v33s_c1 | 전체 | 1 | 미확인 | 미확인 | 24.13606 | false |
| bigcert_l15 | v33s_c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 24.13606 | false |
| bigcert_l15 | v33s_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v33s_c1 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 24.13606 | false |
| bigcert_l15 | v33s_c1 | one_rtt | 1 | 미확인 | 미확인 | 56.0057 | false |
| bigcert_l15 | v33s_c1 | not_one_rtt | 1 | 미확인 | 미확인 | 5.545436 | false |
| bigcert_l15 | v33s_none | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33s_none | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33s_none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v33s_none | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33s_none | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33s_none | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | m4L3 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | m4L3 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33pre_c1 | 전체 | 1 | 미확인 | 미확인 | 52.607682 | false |
| bigcert_l2 | v33pre_c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 52.607682 | false |
| bigcert_l2 | v33pre_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33pre_c1 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 52.607682 | false |
| bigcert_l2 | v33pre_c1 | one_rtt | 1 | 미확인 | 미확인 | 55.474726 | false |
| bigcert_l2 | v33pre_c1 | not_one_rtt | 1 | 미확인 | 미확인 | 1.000898 | false |
| bigcert_l2 | v33s_c1 | 전체 | 1 | 미확인 | 미확인 | 50.070434 | false |
| bigcert_l2 | v33s_c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 50.070434 | false |
| bigcert_l2 | v33s_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33s_c1 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50.070434 | false |
| bigcert_l2 | v33s_c1 | one_rtt | 1 | 미확인 | 미확인 | 55.843355 | false |
| bigcert_l2 | v33s_c1 | not_one_rtt | 1 | 미확인 | 미확인 | 1.000609 | false |
| bigcert_l2 | v33s_none | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33s_none | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33s_none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33s_none | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33s_none | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33s_none | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| p11_l0 | m4L3 | 전체 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | m4L3 | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33pre_c1 | 전체 | 1 | 미확인 | 미확인 | 57.515615 | false |
| p11_l0 | v33pre_c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 57.515615 | false |
| p11_l0 | v33pre_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33pre_c1 | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 57.515615 | false |
| p11_l0 | v33pre_c1 | one_rtt | 1 | 미확인 | 미확인 | 57.515615 | false |
| p11_l0 | v33pre_c1 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33s_c1 | 전체 | 1 | 미확인 | 미확인 | 57.668991 | false |
| p11_l0 | v33s_c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 57.668991 | false |
| p11_l0 | v33s_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33s_c1 | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 57.668991 | false |
| p11_l0 | v33s_c1 | one_rtt | 1 | 미확인 | 미확인 | 57.668991 | false |
| p11_l0 | v33s_c1 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33s_none | 전체 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33s_none | 번인 뒤 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33s_none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33s_none | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33s_none | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33s_none | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | m4L2 | 전체 | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 번인 뒤 | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | m4L2 | c2s=15% s2c=0% | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33pre_c1 | 전체 | 0.55 | 미확인 | 미확인 | 256.665783 | false |
| rtt200_l15 | v33pre_c1 | 번인 뒤 | 0.55 | 미확인 | 미확인 | 256.665783 | false |
| rtt200_l15 | v33pre_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33pre_c1 | c2s=15% s2c=0% | 0.55 | 미확인 | 미확인 | 256.665783 | false |
| rtt200_l15 | v33pre_c1 | one_rtt | 0.555556 | 미확인 | 미확인 | 268.381087 | false |
| rtt200_l15 | v33pre_c1 | not_one_rtt | 0.5 | 미확인 | 미확인 | 157.085698 | false |
| rtt200_l15 | v33s_c1 | 전체 | 0.05 | 미확인 | 미확인 | 261.178922 | false |
| rtt200_l15 | v33s_c1 | 번인 뒤 | 0.05 | 미확인 | 미확인 | 261.178922 | false |
| rtt200_l15 | v33s_c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33s_c1 | c2s=15% s2c=0% | 0.05 | 미확인 | 미확인 | 261.178922 | false |
| rtt200_l15 | v33s_c1 | one_rtt | 0 | 미확인 | 미확인 | 261.551117 | false |
| rtt200_l15 | v33s_c1 | not_one_rtt | 1 | 미확인 | 미확인 | 254.479414 | false |
| rtt200_l15 | v33s_none | 전체 | 0.05 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33s_none | 번인 뒤 | 0.05 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33s_none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33s_none | c2s=15% s2c=0% | 0.05 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33s_none | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33s_none | not_one_rtt | 0.5 | 미확인 | 미확인 | 50 | false |

| 셀 | 팔 | one_rtt 분류 | 전체 행 수 | 수신 | 누락 | C1 수신률 | 분류 판정 | C1 경로 제외 |
|---|---|---|---|---|---|---|---|---|
| bigcert_l15 | v33pre_c1 | one_rtt | 10 | 10 | 0 | 1 | 표본 부족 | false |
| bigcert_l15 | v33pre_c1 | not_one_rtt | 10 | 10 | 0 | 1 | 표본 부족 | false |
| bigcert_l15 | v33s_c1 | one_rtt | 8 | 8 | 0 | 1 | 표본 부족 | false |
| bigcert_l15 | v33s_c1 | not_one_rtt | 12 | 12 | 0 | 1 | 표본 부족 | false |
| bigcert_l2 | v33pre_c1 | one_rtt | 19 | 19 | 0 | 1 | 표본 부족 | false |
| bigcert_l2 | v33pre_c1 | not_one_rtt | 1 | 1 | 0 | 1 | 표본 부족 | false |
| bigcert_l2 | v33s_c1 | one_rtt | 18 | 18 | 0 | 1 | 표본 부족 | false |
| bigcert_l2 | v33s_c1 | not_one_rtt | 2 | 2 | 0 | 1 | 표본 부족 | false |
| p11_l0 | v33pre_c1 | one_rtt | 20 | 20 | 0 | 1 | pass | false |
| p11_l0 | v33pre_c1 | not_one_rtt | 0 | 0 | 0 | 미확인 | 표본 부족 | false |
| p11_l0 | v33s_c1 | one_rtt | 20 | 20 | 0 | 1 | pass | false |
| p11_l0 | v33s_c1 | not_one_rtt | 0 | 0 | 0 | 미확인 | 표본 부족 | false |
| rtt200_l15 | v33pre_c1 | one_rtt | 18 | 18 | 0 | 1 | 표본 부족 | false |
| rtt200_l15 | v33pre_c1 | not_one_rtt | 2 | 2 | 0 | 1 | 표본 부족 | false |
| rtt200_l15 | v33s_c1 | one_rtt | 19 | 19 | 0 | 1 | 표본 부족 | false |
| rtt200_l15 | v33s_c1 | not_one_rtt | 1 | 1 | 0 | 1 | 표본 부족 | false |

연결의 절대 시작·완료 시각이 없어 실제 mean_idle_ms는 null·미확인이다. feedback 대기와 설정 gap의 합은 wait_plus_gap 진단이며 실제 idle의 대체값이 아니다. X6의 실제 idle 차이 기준은 미확인으로 남긴다. C1은 표준 QUIC에 없는 서버 datagram 회신이다.

## 한계

토큰·resumption 기준선(X4), 업링크 오입력(X2), A_pre와 PTO 배수 탐침(X3), s2c 손실(X5), 다른 QUIC 스택(X7), initial congestion window 10(X8), 시간 상관 손실(E24), 중복 전송 기준선(dup), first flight 부풀리기(k-inflate), 서버 first flight 7.7~9.0 KB 띠와 Initial 확대 팔, H c6000, D_p15_4032, 7.8 kB 응답 TTLB는 재지 않았다.
