# M0 개발 측정 결과

quic-go v0.61.0 테스트베드 한 곳, 합성 인증서, W 1280, 손실은 c2s만, initial congestion window 32 packet, 정책 입력 uplink는 netem 대역과 같음. development 측정이며 확증이 아니다.

실행 ID는 final_m0_iter022_20261106, 정책 판본은 v3.3.1-dev다.
결과 근거: `g3/v33/results/v33_dev_M0_final_m0_iter022_20261106.json`.

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
| frozen_feedback | pass |
| frozen_parities | pass |
| hct_mean_range | pass |
| ips | pass |
| netem_config | pass |
| no_feedback | pass |
| none_path | pass |
| pad_recovered | pass |
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
| bigcert_l2 | v33none | 주 분석 | 20 | 83.5238 | 미확인 | 83.5238 | 0 | 0.9 |
| bigcert_l2 | v33none | 번인 포함 전체 | 20 | 83.5238 | 미확인 | 83.5238 | 0 | 0.9 |
| bigcert_l2 | v33none | 층 전체 c2s=2% s2c=0% | 20 | 83.5238 | 미확인 | 83.5238 | 0 | 0.9 |
| bigcert_l2 | v33none | 층 주 분석 c2s=2% s2c=0% | 20 | 83.5238 | 미확인 | 83.5238 | 0 | 0.9 |
| bigcert_l2 | v33c1 | 주 분석 | 20 | 88.31165 | 미확인 | 88.31165 | 0 | 0.85 |
| bigcert_l2 | v33c1 | 번인 포함 전체 | 20 | 88.31165 | 미확인 | 88.31165 | 0 | 0.85 |
| bigcert_l2 | v33c1 | 층 전체 c2s=2% s2c=0% | 20 | 88.31165 | 미확인 | 88.31165 | 0 | 0.85 |
| bigcert_l2 | v33c1 | 층 주 분석 c2s=2% s2c=0% | 20 | 88.31165 | 미확인 | 88.31165 | 0 | 0.85 |
| bigcert_l2 | v31auto | 주 분석 | 20 | 80.82645 | 미확인 | 80.82645 | 0 | 0.95 |
| bigcert_l2 | v31auto | 번인 포함 전체 | 20 | 80.82645 | 미확인 | 80.82645 | 0 | 0.95 |
| bigcert_l2 | v31auto | 층 전체 c2s=2% s2c=0% | 20 | 80.82645 | 미확인 | 80.82645 | 0 | 0.95 |
| bigcert_l2 | v31auto | 층 주 분석 c2s=2% s2c=0% | 20 | 80.82645 | 미확인 | 80.82645 | 0 | 0.95 |
| bigcert_l2 | g2auto | 주 분석 | 20 | 129.33745 | 미확인 | 129.33745 | 0 | 0 |
| bigcert_l2 | g2auto | 번인 포함 전체 | 20 | 129.33745 | 미확인 | 129.33745 | 0 | 0 |
| bigcert_l2 | g2auto | 층 전체 c2s=2% s2c=0% | 20 | 129.33745 | 미확인 | 129.33745 | 0 | 0 |
| bigcert_l2 | g2auto | 층 주 분석 c2s=2% s2c=0% | 20 | 129.33745 | 미확인 | 129.33745 | 0 | 0 |
| bigcert_l2 | m4L3 | 주 분석 | 20 | 84.19155 | 미확인 | 84.19155 | 0 | 0.9 |
| bigcert_l2 | m4L3 | 번인 포함 전체 | 20 | 84.19155 | 미확인 | 84.19155 | 0 | 0.9 |
| bigcert_l2 | m4L3 | 층 전체 c2s=2% s2c=0% | 20 | 84.19155 | 미확인 | 84.19155 | 0 | 0.9 |
| bigcert_l2 | m4L3 | 층 주 분석 c2s=2% s2c=0% | 20 | 84.19155 | 미확인 | 84.19155 | 0 | 0.9 |
| bigcert_l2 | pad4L3 | 주 분석 | 20 | 97.2215 | 미확인 | 97.2215 | 0 | 0.85 |
| bigcert_l2 | pad4L3 | 번인 포함 전체 | 20 | 97.2215 | 미확인 | 97.2215 | 0 | 0.85 |
| bigcert_l2 | pad4L3 | 층 전체 c2s=2% s2c=0% | 20 | 97.2215 | 미확인 | 97.2215 | 0 | 0.85 |
| bigcert_l2 | pad4L3 | 층 주 분석 c2s=2% s2c=0% | 20 | 97.2215 | 미확인 | 97.2215 | 0 | 0.85 |
| bigcert_l15 | v33none | 주 분석 | 20 | 104.34505 | 미확인 | 104.34505 | 0 | 0.7 |
| bigcert_l15 | v33none | 번인 포함 전체 | 20 | 104.34505 | 미확인 | 104.34505 | 0 | 0.7 |
| bigcert_l15 | v33none | 층 전체 c2s=15% s2c=0% | 20 | 104.34505 | 미확인 | 104.34505 | 0 | 0.7 |
| bigcert_l15 | v33none | 층 주 분석 c2s=15% s2c=0% | 20 | 104.34505 | 미확인 | 104.34505 | 0 | 0.7 |
| bigcert_l15 | v33c1 | 주 분석 | 20 | 105.96425 | 미확인 | 105.96425 | 0 | 0.6 |
| bigcert_l15 | v33c1 | 번인 포함 전체 | 20 | 105.96425 | 미확인 | 105.96425 | 0 | 0.6 |
| bigcert_l15 | v33c1 | 층 전체 c2s=15% s2c=0% | 20 | 105.96425 | 미확인 | 105.96425 | 0 | 0.6 |
| bigcert_l15 | v33c1 | 층 주 분석 c2s=15% s2c=0% | 20 | 105.96425 | 미확인 | 105.96425 | 0 | 0.6 |
| bigcert_l15 | v31auto | 주 분석 | 20 | 106.1973 | 미확인 | 106.1973 | 0 | 0.65 |
| bigcert_l15 | v31auto | 번인 포함 전체 | 20 | 106.1973 | 미확인 | 106.1973 | 0 | 0.65 |
| bigcert_l15 | v31auto | 층 전체 c2s=15% s2c=0% | 20 | 106.1973 | 미확인 | 106.1973 | 0 | 0.65 |
| bigcert_l15 | v31auto | 층 주 분석 c2s=15% s2c=0% | 20 | 106.1973 | 미확인 | 106.1973 | 0 | 0.65 |
| bigcert_l15 | g2auto | 주 분석 | 20 | 128.8696 | 미확인 | 128.8696 | 0 | 0 |
| bigcert_l15 | g2auto | 번인 포함 전체 | 20 | 128.8696 | 미확인 | 128.8696 | 0 | 0 |
| bigcert_l15 | g2auto | 층 전체 c2s=15% s2c=0% | 20 | 128.8696 | 미확인 | 128.8696 | 0 | 0 |
| bigcert_l15 | g2auto | 층 주 분석 c2s=15% s2c=0% | 20 | 128.8696 | 미확인 | 128.8696 | 0 | 0 |
| bigcert_l15 | m4L3 | 주 분석 | 20 | 119.5578 | 미확인 | 119.5578 | 0 | 0.55 |
| bigcert_l15 | m4L3 | 번인 포함 전체 | 20 | 119.5578 | 미확인 | 119.5578 | 0 | 0.55 |
| bigcert_l15 | m4L3 | 층 전체 c2s=15% s2c=0% | 20 | 119.5578 | 미확인 | 119.5578 | 0 | 0.55 |
| bigcert_l15 | m4L3 | 층 주 분석 c2s=15% s2c=0% | 20 | 119.5578 | 미확인 | 119.5578 | 0 | 0.55 |
| bigcert_l15 | pad4L3 | 주 분석 | 20 | 149.7589 | 미확인 | 149.7589 | 0 | 0.5 |
| bigcert_l15 | pad4L3 | 번인 포함 전체 | 20 | 149.7589 | 미확인 | 149.7589 | 0 | 0.5 |
| bigcert_l15 | pad4L3 | 층 전체 c2s=15% s2c=0% | 20 | 149.7589 | 미확인 | 149.7589 | 0 | 0.5 |
| bigcert_l15 | pad4L3 | 층 주 분석 c2s=15% s2c=0% | 20 | 149.7589 | 미확인 | 149.7589 | 0 | 0.5 |
| rtt200_l15 | v33none | 주 분석 | 20 | 231.85725 | 미확인 | 231.85725 | 0 | 0.95 |
| rtt200_l15 | v33none | 번인 포함 전체 | 20 | 231.85725 | 미확인 | 231.85725 | 0 | 0.95 |
| rtt200_l15 | v33none | 층 전체 c2s=15% s2c=0% | 20 | 231.85725 | 미확인 | 231.85725 | 0 | 0.95 |
| rtt200_l15 | v33none | 층 주 분석 c2s=15% s2c=0% | 20 | 231.85725 | 미확인 | 231.85725 | 0 | 0.95 |
| rtt200_l15 | v33c1 | 주 분석 | 20 | 236.00655 | 미확인 | 236.00655 | 0 | 0.95 |
| rtt200_l15 | v33c1 | 번인 포함 전체 | 20 | 236.00655 | 미확인 | 236.00655 | 0 | 0.95 |
| rtt200_l15 | v33c1 | 층 전체 c2s=15% s2c=0% | 20 | 236.00655 | 미확인 | 236.00655 | 0 | 0.95 |
| rtt200_l15 | v33c1 | 층 주 분석 c2s=15% s2c=0% | 20 | 236.00655 | 미확인 | 236.00655 | 0 | 0.95 |
| rtt200_l15 | v31auto | 주 분석 | 20 | 231.08875 | 미확인 | 231.08875 | 0 | 0.95 |
| rtt200_l15 | v31auto | 번인 포함 전체 | 20 | 231.08875 | 미확인 | 231.08875 | 0 | 0.95 |
| rtt200_l15 | v31auto | 층 전체 c2s=15% s2c=0% | 20 | 231.08875 | 미확인 | 231.08875 | 0 | 0.95 |
| rtt200_l15 | v31auto | 층 주 분석 c2s=15% s2c=0% | 20 | 231.08875 | 미확인 | 231.08875 | 0 | 0.95 |
| rtt200_l15 | g2auto | 주 분석 | 20 | 266.64575 | 미확인 | 266.64575 | 0 | 0.75 |
| rtt200_l15 | g2auto | 번인 포함 전체 | 20 | 266.64575 | 미확인 | 266.64575 | 0 | 0.75 |
| rtt200_l15 | g2auto | 층 전체 c2s=15% s2c=0% | 20 | 266.64575 | 미확인 | 266.64575 | 0 | 0.75 |
| rtt200_l15 | g2auto | 층 주 분석 c2s=15% s2c=0% | 20 | 266.64575 | 미확인 | 266.64575 | 0 | 0.75 |
| rtt200_l15 | m4L2 | 주 분석 | 20 | 221.86275 | 미확인 | 221.86275 | 0 | 1 |
| rtt200_l15 | m4L2 | 번인 포함 전체 | 20 | 221.86275 | 미확인 | 221.86275 | 0 | 1 |
| rtt200_l15 | m4L2 | 층 전체 c2s=15% s2c=0% | 20 | 221.86275 | 미확인 | 221.86275 | 0 | 1 |
| rtt200_l15 | m4L2 | 층 주 분석 c2s=15% s2c=0% | 20 | 221.86275 | 미확인 | 221.86275 | 0 | 1 |
| rtt200_l15 | pad4L2 | 주 분석 | 20 | 284.15465 | 미확인 | 284.15465 | 0 | 0.75 |
| rtt200_l15 | pad4L2 | 번인 포함 전체 | 20 | 284.15465 | 미확인 | 284.15465 | 0 | 0.75 |
| rtt200_l15 | pad4L2 | 층 전체 c2s=15% s2c=0% | 20 | 284.15465 | 미확인 | 284.15465 | 0 | 0.75 |
| rtt200_l15 | pad4L2 | 층 주 분석 c2s=15% s2c=0% | 20 | 284.15465 | 미확인 | 284.15465 | 0 | 0.75 |
| p11_l0 | v33none | 주 분석 | 20 | 52.18875 | 미확인 | 52.18875 | 0 | 1 |
| p11_l0 | v33none | 번인 포함 전체 | 20 | 52.18875 | 미확인 | 52.18875 | 0 | 1 |
| p11_l0 | v33none | 층 전체 c2s=0% s2c=0% | 20 | 52.18875 | 미확인 | 52.18875 | 0 | 1 |
| p11_l0 | v33none | 층 주 분석 c2s=0% s2c=0% | 20 | 52.18875 | 미확인 | 52.18875 | 0 | 1 |
| p11_l0 | v33c1 | 주 분석 | 20 | 52.46295 | 미확인 | 52.46295 | 0 | 1 |
| p11_l0 | v33c1 | 번인 포함 전체 | 20 | 52.46295 | 미확인 | 52.46295 | 0 | 1 |
| p11_l0 | v33c1 | 층 전체 c2s=0% s2c=0% | 20 | 52.46295 | 미확인 | 52.46295 | 0 | 1 |
| p11_l0 | v33c1 | 층 주 분석 c2s=0% s2c=0% | 20 | 52.46295 | 미확인 | 52.46295 | 0 | 1 |
| p11_l0 | v31auto | 주 분석 | 20 | 52.14365 | 미확인 | 52.14365 | 0 | 1 |
| p11_l0 | v31auto | 번인 포함 전체 | 20 | 52.14365 | 미확인 | 52.14365 | 0 | 1 |
| p11_l0 | v31auto | 층 전체 c2s=0% s2c=0% | 20 | 52.14365 | 미확인 | 52.14365 | 0 | 1 |
| p11_l0 | v31auto | 층 주 분석 c2s=0% s2c=0% | 20 | 52.14365 | 미확인 | 52.14365 | 0 | 1 |
| p11_l0 | g2auto | 주 분석 | 20 | 51.84805 | 미확인 | 51.84805 | 0 | 1 |
| p11_l0 | g2auto | 번인 포함 전체 | 20 | 51.84805 | 미확인 | 51.84805 | 0 | 1 |
| p11_l0 | g2auto | 층 전체 c2s=0% s2c=0% | 20 | 51.84805 | 미확인 | 51.84805 | 0 | 1 |
| p11_l0 | g2auto | 층 주 분석 c2s=0% s2c=0% | 20 | 51.84805 | 미확인 | 51.84805 | 0 | 1 |
| p11_l0 | m4L3 | 주 분석 | 20 | 52.04155 | 미확인 | 52.04155 | 0 | 1 |
| p11_l0 | m4L3 | 번인 포함 전체 | 20 | 52.04155 | 미확인 | 52.04155 | 0 | 1 |
| p11_l0 | m4L3 | 층 전체 c2s=0% s2c=0% | 20 | 52.04155 | 미확인 | 52.04155 | 0 | 1 |
| p11_l0 | m4L3 | 층 주 분석 c2s=0% s2c=0% | 20 | 52.04155 | 미확인 | 52.04155 | 0 | 1 |
| p11_l0 | pad4L3 | 주 분석 | 20 | 52.5805 | 미확인 | 52.5805 | 0 | 1 |
| p11_l0 | pad4L3 | 번인 포함 전체 | 20 | 52.5805 | 미확인 | 52.5805 | 0 | 1 |
| p11_l0 | pad4L3 | 층 전체 c2s=0% s2c=0% | 20 | 52.5805 | 미확인 | 52.5805 | 0 | 1 |
| p11_l0 | pad4L3 | 층 주 분석 c2s=0% s2c=0% | 20 | 52.5805 | 미확인 | 52.5805 | 0 | 1 |

## 서버 계수 비용

서버 수신량은 연결 전체의 bytes_in을 같은 범위의 클라이언트 행 수로 나눈다. 손실 조건에서도 이 값은 서버 수신량이다. first flight 바이트는 별도 클라이언트 진단이다.

| 셀 | 팔 | 범위 | 서버 계수 bytes_in(B) | 분모 행 수 | 서버 수신량(B/연결) | 원천 | 상태 | first flight 원본 평균(B) | first flight parity 평균(B) | first flight extra 평균(B) |
|---|---|---|---|---|---|---|---|---|---|---|
| bigcert_l2 | v33none | 주 분석 | 202079 | 20 | 10103.95 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| bigcert_l2 | v33none | 번인 포함 전체 | 202079 | 20 | 10103.95 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| bigcert_l2 | v33c1 | 주 분석 | 203773 | 20 | 10188.65 | server_delta.bytes_in | 확인 | 2560 | 5060.2 | 5060.2 |
| bigcert_l2 | v33c1 | 번인 포함 전체 | 203773 | 20 | 10188.65 | server_delta.bytes_in | 확인 | 2560 | 5060.2 | 5060.2 |
| bigcert_l2 | v31auto | 주 분석 | 204416 | 20 | 10220.8 | server_delta.bytes_in | 확인 | 2560 | 5056 | 미확인 |
| bigcert_l2 | v31auto | 번인 포함 전체 | 204416 | 20 | 10220.8 | server_delta.bytes_in | 확인 | 2560 | 5056 | 미확인 |
| bigcert_l2 | g2auto | 주 분석 | 216976 | 20 | 10848.8 | server_delta.bytes_in | 확인 | 2560 | 3597.6 | 미확인 |
| bigcert_l2 | g2auto | 번인 포함 전체 | 216976 | 20 | 10848.8 | server_delta.bytes_in | 확인 | 2560 | 3597.6 | 미확인 |
| bigcert_l2 | m4L3 | 주 분석 | 207389 | 20 | 10369.45 | server_delta.bytes_in | 확인 | 2560 | 5323.8 | 5323.8 |
| bigcert_l2 | m4L3 | 번인 포함 전체 | 207389 | 20 | 10369.45 | server_delta.bytes_in | 확인 | 2560 | 5323.8 | 5323.8 |
| bigcert_l2 | pad4L3 | 주 분석 | 226800 | 20 | 11340 | server_delta.bytes_in | 확인 | 2560 | 0 | 5326 |
| bigcert_l2 | pad4L3 | 번인 포함 전체 | 226800 | 20 | 11340 | server_delta.bytes_in | 확인 | 2560 | 0 | 5326 |
| bigcert_l15 | v33none | 주 분석 | 189210 | 20 | 9460.5 | server_delta.bytes_in | 확인 | 2560 | 5062 | 5062 |
| bigcert_l15 | v33none | 번인 포함 전체 | 189210 | 20 | 9460.5 | server_delta.bytes_in | 확인 | 2560 | 5062 | 5062 |
| bigcert_l15 | v33c1 | 주 분석 | 184735 | 20 | 9236.75 | server_delta.bytes_in | 확인 | 2560 | 5058.4 | 5058.4 |
| bigcert_l15 | v33c1 | 번인 포함 전체 | 184735 | 20 | 9236.75 | server_delta.bytes_in | 확인 | 2560 | 5058.4 | 5058.4 |
| bigcert_l15 | v31auto | 주 분석 | 180185 | 20 | 9009.25 | server_delta.bytes_in | 확인 | 2560 | 5061.4 | 미확인 |
| bigcert_l15 | v31auto | 번인 포함 전체 | 180185 | 20 | 9009.25 | server_delta.bytes_in | 확인 | 2560 | 5061.4 | 미확인 |
| bigcert_l15 | g2auto | 주 분석 | 188639 | 20 | 9431.95 | server_delta.bytes_in | 확인 | 2560 | 3595.35 | 미확인 |
| bigcert_l15 | g2auto | 번인 포함 전체 | 188639 | 20 | 9431.95 | server_delta.bytes_in | 확인 | 2560 | 3595.35 | 미확인 |
| bigcert_l15 | m4L3 | 주 분석 | 185047 | 20 | 9252.35 | server_delta.bytes_in | 확인 | 2560 | 5331.4 | 5331.4 |
| bigcert_l15 | m4L3 | 번인 포함 전체 | 185047 | 20 | 9252.35 | server_delta.bytes_in | 확인 | 2560 | 5331.4 | 5331.4 |
| bigcert_l15 | pad4L3 | 주 분석 | 222045 | 20 | 11102.25 | server_delta.bytes_in | 확인 | 2560 | 0 | 5323.6 |
| bigcert_l15 | pad4L3 | 번인 포함 전체 | 222045 | 20 | 11102.25 | server_delta.bytes_in | 확인 | 2560 | 0 | 5323.6 |
| rtt200_l15 | v33none | 주 분석 | 309617 | 20 | 15480.85 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| rtt200_l15 | v33none | 번인 포함 전체 | 309617 | 20 | 15480.85 | server_delta.bytes_in | 확인 | 2560 | 5062.4 | 5062.4 |
| rtt200_l15 | v33c1 | 주 분석 | 307616 | 20 | 15380.8 | server_delta.bytes_in | 확인 | 2560 | 5065 | 5065 |
| rtt200_l15 | v33c1 | 번인 포함 전체 | 307616 | 20 | 15380.8 | server_delta.bytes_in | 확인 | 2560 | 5065 | 5065 |
| rtt200_l15 | v31auto | 주 분석 | 292710 | 20 | 14635.5 | server_delta.bytes_in | 확인 | 2560 | 5062 | 미확인 |
| rtt200_l15 | v31auto | 번인 포함 전체 | 292710 | 20 | 14635.5 | server_delta.bytes_in | 확인 | 2560 | 5062 | 미확인 |
| rtt200_l15 | g2auto | 주 분석 | 284867 | 20 | 14243.35 | server_delta.bytes_in | 확인 | 2560 | 3595.95 | 미확인 |
| rtt200_l15 | g2auto | 번인 포함 전체 | 284867 | 20 | 14243.35 | server_delta.bytes_in | 확인 | 2560 | 3595.95 | 미확인 |
| rtt200_l15 | m4L2 | 주 분석 | 321258 | 20 | 16062.9 | server_delta.bytes_in | 확인 | 2560 | 5327.8 | 5327.8 |
| rtt200_l15 | m4L2 | 번인 포함 전체 | 321258 | 20 | 16062.9 | server_delta.bytes_in | 확인 | 2560 | 5327.8 | 5327.8 |
| rtt200_l15 | pad4L2 | 주 분석 | 322623 | 20 | 16131.15 | server_delta.bytes_in | 확인 | 2560 | 0 | 5324.2 |
| rtt200_l15 | pad4L2 | 번인 포함 전체 | 322623 | 20 | 16131.15 | server_delta.bytes_in | 확인 | 2560 | 0 | 5324.2 |
| p11_l0 | v33none | 주 분석 | 204609 | 20 | 10230.45 | server_delta.bytes_in | 확인 | 2560 | 5062.2 | 5062.2 |
| p11_l0 | v33none | 번인 포함 전체 | 204609 | 20 | 10230.45 | server_delta.bytes_in | 확인 | 2560 | 5062.2 | 5062.2 |
| p11_l0 | v33c1 | 주 분석 | 185763 | 20 | 9288.15 | server_delta.bytes_in | 확인 | 2560 | 4131 | 4131 |
| p11_l0 | v33c1 | 번인 포함 전체 | 185763 | 20 | 9288.15 | server_delta.bytes_in | 확인 | 2560 | 4131 | 4131 |
| p11_l0 | v31auto | 주 분석 | 204428 | 20 | 10221.4 | server_delta.bytes_in | 확인 | 2560 | 5062.2 | 미확인 |
| p11_l0 | v31auto | 번인 포함 전체 | 204428 | 20 | 10221.4 | server_delta.bytes_in | 확인 | 2560 | 5062.2 | 미확인 |
| p11_l0 | g2auto | 주 분석 | 221133 | 20 | 11056.65 | server_delta.bytes_in | 확인 | 2560 | 3594.45 | 미확인 |
| p11_l0 | g2auto | 번인 포함 전체 | 221133 | 20 | 11056.65 | server_delta.bytes_in | 확인 | 2560 | 3594.45 | 미확인 |
| p11_l0 | m4L3 | 주 분석 | 211112 | 20 | 10555.6 | server_delta.bytes_in | 확인 | 2560 | 5330.6 | 5330.6 |
| p11_l0 | m4L3 | 번인 포함 전체 | 211112 | 20 | 10555.6 | server_delta.bytes_in | 확인 | 2560 | 5330.6 | 5330.6 |
| p11_l0 | pad4L3 | 주 분석 | 211060 | 20 | 10553 | server_delta.bytes_in | 확인 | 2560 | 0 | 5328 |
| p11_l0 | pad4L3 | 번인 포함 전체 | 211060 | 20 | 10553 | server_delta.bytes_in | 확인 | 2560 | 0 | 5328 |

g2auto의 클라이언트 parity 계수에는 client_parity_count_unreliable 표지를 둔다. 클라이언트 bytes_parity와 parity_sent는 비용에 더하지 않는다.

## 팔 간 비교

차이는 x 팔에서 y 팔을 뺀 값이다.

## 관측 범위

| 셀 | 팔 | 범위 | 유효 RTT 비율 | 실제 mean_idle_ms | idle 상태 | wait_plus_gap 진단(ms) | C1 경로 제외 |
|---|---|---|---|---|---|---|---|
| bigcert_l15 | g2auto | 전체 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | g2auto | 번인 뒤 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | g2auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | g2auto | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | g2auto | one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | g2auto | not_one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
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
| bigcert_l15 | v31auto | 전체 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v31auto | 번인 뒤 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v31auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v31auto | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v31auto | one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v31auto | not_one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v33c1 | 전체 | 1 | 미확인 | 미확인 | 35.659615 | false |
| bigcert_l15 | v33c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 35.659615 | false |
| bigcert_l15 | v33c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v33c1 | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 35.659615 | false |
| bigcert_l15 | v33c1 | one_rtt | 1 | 미확인 | 미확인 | 55.87731 | false |
| bigcert_l15 | v33c1 | not_one_rtt | 1 | 미확인 | 미확인 | 1.000708 | false |
| bigcert_l15 | v33none | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33none | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l15 | v33none | c2s=15% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33none | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l15 | v33none | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | g2auto | 전체 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | g2auto | 번인 뒤 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | g2auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | g2auto | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | g2auto | one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | g2auto | not_one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
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
| bigcert_l2 | v31auto | 전체 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v31auto | 번인 뒤 | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v31auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v31auto | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v31auto | one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v31auto | not_one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33c1 | 전체 | 1 | 미확인 | 미확인 | 47.136788 | false |
| bigcert_l2 | v33c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 47.136788 | false |
| bigcert_l2 | v33c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33c1 | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 47.136788 | false |
| bigcert_l2 | v33c1 | one_rtt | 1 | 미확인 | 미확인 | 55.787337 | false |
| bigcert_l2 | v33c1 | not_one_rtt | 1 | 미확인 | 미확인 | 1.00053 | false |
| bigcert_l2 | v33none | 전체 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33none | 번인 뒤 | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| bigcert_l2 | v33none | c2s=2% s2c=0% | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33none | one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| bigcert_l2 | v33none | not_one_rtt | 1 | 미확인 | 미확인 | 50 | false |
| p11_l0 | g2auto | 전체 | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | g2auto | 번인 뒤 | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | g2auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | g2auto | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | g2auto | one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | g2auto | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | m4L3 | 전체 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | m4L3 | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | m4L3 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | pad4L3 | 전체 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | pad4L3 | 번인 뒤 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | pad4L3 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | pad4L3 | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | pad4L3 | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | pad4L3 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v31auto | 전체 | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v31auto | 번인 뒤 | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v31auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v31auto | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v31auto | one_rtt | 1 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v31auto | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33c1 | 전체 | 1 | 미확인 | 미확인 | 57.604309 | false |
| p11_l0 | v33c1 | 번인 뒤 | 1 | 미확인 | 미확인 | 57.604309 | false |
| p11_l0 | v33c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33c1 | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 57.604309 | false |
| p11_l0 | v33c1 | one_rtt | 1 | 미확인 | 미확인 | 57.604309 | false |
| p11_l0 | v33c1 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33none | 전체 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33none | 번인 뒤 | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| p11_l0 | v33none | c2s=0% s2c=0% | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33none | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| p11_l0 | v33none | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | g2auto | 전체 | 0.05 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | g2auto | 번인 뒤 | 0.05 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | g2auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | g2auto | c2s=15% s2c=0% | 0.05 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | g2auto | one_rtt | 0 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | g2auto | not_one_rtt | 0.2 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | m4L2 | 전체 | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 번인 뒤 | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | m4L2 | c2s=15% s2c=0% | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | m4L2 | not_one_rtt | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | pad4L2 | 전체 | 0.2 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | 번인 뒤 | 0.2 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | pad4L2 | c2s=15% s2c=0% | 0.2 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | pad4L2 | not_one_rtt | 0.8 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v31auto | 전체 | 0 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v31auto | 번인 뒤 | 0 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v31auto | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v31auto | c2s=15% s2c=0% | 0 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v31auto | one_rtt | 0 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v31auto | not_one_rtt | 0 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33c1 | 전체 | 0.4 | 미확인 | 미확인 | 248.457647 | false |
| rtt200_l15 | v33c1 | 번인 뒤 | 0.4 | 미확인 | 미확인 | 248.457647 | false |
| rtt200_l15 | v33c1 | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33c1 | c2s=15% s2c=0% | 0.4 | 미확인 | 미확인 | 248.457647 | false |
| rtt200_l15 | v33c1 | one_rtt | 0.421053 | 미확인 | 미확인 | 258.898276 | false |
| rtt200_l15 | v33c1 | not_one_rtt | 0 | 미확인 | 미확인 | 60.52634 | false |
| rtt200_l15 | v33none | 전체 | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33none | 번인 뒤 | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33none | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| rtt200_l15 | v33none | c2s=15% s2c=0% | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33none | one_rtt | 0 | 미확인 | 미확인 | 50 | false |
| rtt200_l15 | v33none | not_one_rtt | 0 | 미확인 | 미확인 | 50 | false |

| 셀 | 팔 | one_rtt 분류 | 전체 행 수 | 수신 | 누락 | C1 수신률 | 분류 판정 | C1 경로 제외 |
|---|---|---|---|---|---|---|---|---|
| bigcert_l15 | v33c1 | one_rtt | 12 | 12 | 0 | 1 | 표본 부족 | false |
| bigcert_l15 | v33c1 | not_one_rtt | 8 | 8 | 0 | 1 | 표본 부족 | false |
| bigcert_l2 | v33c1 | one_rtt | 17 | 17 | 0 | 1 | 표본 부족 | false |
| bigcert_l2 | v33c1 | not_one_rtt | 3 | 3 | 0 | 1 | 표본 부족 | false |
| p11_l0 | v33c1 | one_rtt | 20 | 20 | 0 | 1 | pass | false |
| p11_l0 | v33c1 | not_one_rtt | 0 | 0 | 0 | 미확인 | 표본 부족 | false |
| rtt200_l15 | v33c1 | one_rtt | 19 | 19 | 0 | 1 | 표본 부족 | false |
| rtt200_l15 | v33c1 | not_one_rtt | 1 | 1 | 0 | 1 | 표본 부족 | false |

연결의 절대 시작·완료 시각이 없어 실제 mean_idle_ms는 null·미확인이다. feedback 대기와 설정 gap의 합은 wait_plus_gap 진단이며 실제 idle의 대체값이 아니다. X6의 실제 idle 차이 기준은 미확인으로 남긴다. C1은 표준 QUIC에 없는 서버 datagram 회신이다.

## 한계

토큰·resumption 기준선(X4), 업링크 오입력(X2), A_pre와 PTO 배수 탐침(X3), s2c 손실(X5), 다른 QUIC 스택(X7), initial congestion window 10(X8), 시간 상관 손실(E24), 중복 전송 기준선(dup), first flight 부풀리기(k-inflate), 서버 first flight 7.7~9.0 KB 띠와 Initial 확대 팔, H c6000, D_p15_4032, 7.8 kB 응답 TTLB는 재지 않았다.
