# X9 개발 측정 결과

quic-go v0.61.0 테스트베드 한 곳, 합성 인증서, W 1280, 손실은 c2s 및 양방향을 구분, initial congestion window 32 packet, 정책 입력 uplink는 netem 대역과 같음. development 측정이며 확증이 아니다.

실행 ID는 final_x9_iter031_20261107, 정책 판본은 v3.3.1-dev다.
결과 근거: `g3/v33/results/v33_dev_X9_final_x9_iter031_20261107.json`.

## 실행과 판정

| 항목 | 상태 |
|---|---|
| both:mlkem_off:pto_auxiliary_fields | pass |
| both:mlkem_off:pto_denominator | pass |
| both:mlkem_off:pto_primary_fields | pass |
| both:x25519_off:pto_auxiliary_fields | pass |
| both:x25519_off:pto_denominator | pass |
| both:x25519_off:pto_primary_fields | pass |
| c2s:mlkem_off:pto_auxiliary_fields | pass |
| c2s:mlkem_off:pto_denominator | pass |
| c2s:mlkem_off:pto_primary_fields | pass |
| c2s:x25519_off:pto_auxiliary_fields | pass |
| c2s:x25519_off:pto_denominator | pass |
| c2s:x25519_off:pto_primary_fields | pass |
| client_rows | pass |
| connection_collection | pass |
| explicit_flight | pass |
| ips | pass |
| no_feedback | pass |
| process_rc | pass |
| server_process | pass |
| server_stats | pass |
| server_uniform | pass |
| w_bound | pass |

실행 상태: 판정 통과. 통계 판정: 기술통계.

## HCT와 연결 비율

| 셀 | 팔 | 범위 | 행 수 | HCT 평균(ms) | HCT 95% 구간(ms) | 성공 HCT 평균(ms) | 실패 비율 | 1-RTT 비율 |
|---|---|---|---|---|---|---|---|---|
| c2s | x25519_off | 주 분석 | 6100 | 62.503787 | [61.304479, 63.703095] | 62.503787 | 0 | 0.94918 |
| c2s | x25519_off | 번인 포함 전체 | 6405 | 62.539711 | [61.349949, 63.729473] | 62.539711 | 0 | 0.949102 |
| c2s | x25519_off | 층 전체 c2s=5% s2c=0% | 6405 | 62.539711 | [61.349949, 63.729473] | 62.539711 | 0 | 0.949102 |
| c2s | x25519_off | 층 주 분석 c2s=5% s2c=0% | 6100 | 62.503787 | [61.304479, 63.703095] | 62.503787 | 0 | 0.94918 |
| c2s | mlkem_off | 주 분석 | 6100 | 63.444644 | [62.346097, 64.543192] | 63.444644 | 0 | 0.903607 |
| c2s | mlkem_off | 번인 포함 전체 | 6405 | 63.520974 | [62.503147, 64.5388] | 63.520974 | 0 | 0.903981 |
| c2s | mlkem_off | 층 전체 c2s=5% s2c=0% | 6405 | 63.520974 | [62.503147, 64.5388] | 63.520974 | 0 | 0.903981 |
| c2s | mlkem_off | 층 주 분석 c2s=5% s2c=0% | 6100 | 63.444644 | [62.346097, 64.543192] | 63.444644 | 0 | 0.903607 |
| both | x25519_off | 주 분석 | 6100 | 77.015748 | [75.285775, 78.745721] | 77.015748 | 0 | 0.896066 |
| both | x25519_off | 번인 포함 전체 | 6405 | 77.261104 | [75.456004, 79.066204] | 77.261104 | 0 | 0.895238 |
| both | x25519_off | 층 전체 c2s=5% s2c=5% | 6405 | 77.261104 | [75.456004, 79.066204] | 77.261104 | 0 | 0.895238 |
| both | x25519_off | 층 주 분석 c2s=5% s2c=5% | 6100 | 77.015748 | [75.285775, 78.745721] | 77.015748 | 0 | 0.896066 |
| both | mlkem_off | 주 분석 | 6100 | 82.157683 | [80.164691, 84.150675] | 82.157683 | 0 | 0.814918 |
| both | mlkem_off | 번인 포함 전체 | 6405 | 82.171703 | [80.253317, 84.090089] | 82.171703 | 0 | 0.813739 |
| both | mlkem_off | 층 전체 c2s=5% s2c=5% | 6405 | 82.171703 | [80.253317, 84.090089] | 82.171703 | 0 | 0.813739 |
| both | mlkem_off | 층 주 분석 c2s=5% s2c=5% | 6100 | 82.157683 | [80.164691, 84.150675] | 82.157683 | 0 | 0.814918 |

## 서버 계수 비용

서버 수신량은 연결 전체의 bytes_in을 같은 범위의 클라이언트 행 수로 나눈다. 손실 조건에서도 이 값은 서버 수신량이다. first flight 바이트는 별도 클라이언트 진단이다.

| 셀 | 팔 | 범위 | 서버 계수 bytes_in(B) | 분모 행 수 | 서버 수신량(B/연결) | 원천 | 상태 | first flight 원본 평균(B) | first flight parity 평균(B) | first flight extra 평균(B) |
|---|---|---|---|---|---|---|---|---|---|---|
| c2s | x25519_off | 주 분석 | 15993788 | 6100 | 2621.932459 | conn_log.rx_bytes | 확인 | 1280 | 0 | 0 |
| c2s | x25519_off | 번인 포함 전체 | 16789340 | 6405 | 2621.286495 | server_delta.bytes_in | 확인 | 1280 | 0 | 0 |
| c2s | mlkem_off | 주 분석 | 23802936 | 6100 | 3902.120656 | conn_log.rx_bytes | 확인 | 2560 | 0 | 0 |
| c2s | mlkem_off | 번인 포함 전체 | 25000684 | 6405 | 3903.307416 | server_delta.bytes_in | 확인 | 2560 | 0 | 0 |
| both | x25519_off | 주 분석 | 16809529 | 6100 | 2755.660492 | conn_log.rx_bytes | 확인 | 1280 | 0 | 0 |
| both | x25519_off | 번인 포함 전체 | 17653393 | 6405 | 2756.189383 | server_delta.bytes_in | 확인 | 1280 | 0 | 0 |
| both | mlkem_off | 주 분석 | 24856514 | 6100 | 4074.838361 | conn_log.rx_bytes | 확인 | 2559.790164 | 0 | 0 |
| both | mlkem_off | 번인 포함 전체 | 26099003 | 6405 | 4074.785792 | server_delta.bytes_in | 확인 | 2559.800156 | 0 | 0 |

g2auto의 클라이언트 parity 계수에는 client_parity_count_unreliable 표지를 둔다. 클라이언트 bytes_parity와 parity_sent는 비용에 더하지 않는다.

## 팔 간 비교

차이는 x 팔에서 y 팔을 뺀 값이다.

## PTO 사건

주 정의는 observation.pto_count가 양수인 연결이다. count_scope=qlog_loss_timer_expired_lower_bound는 메모리 qlog에 기록된 timer 만료 횟수의 하한이다. tracer가 비활성이거나 관측 범위가 맞지 않으면 누락으로 처리한다. 보조 정의는 initial_datagrams가 first_flight_datagrams보다 둘 이상 많은 연결이다. 두 정의의 누락과 불일치를 따로 남겼다.

| 방향 셀 | 팔 | 정의 | 사건 수 | 분석 행 수 | 유효 분모 | 누락 | 관측 범위 불일치 | 비율(%) | 정의 불일치 | 정의 비교 가능 수 |
|---|---|---|---|---|---|---|---|---|---|---|
| c2s | x25519_off | 주 정의 | 310 | 6100 | 6100 | 0 | 0 | 5.081967 | 0 | 6100 |
| c2s | x25519_off | 보조 정의 | 310 | 6100 | 6100 | 0 | 미확인 | 5.081967 | 0 | 6100 |
| c2s | mlkem_off | 주 정의 | 314 | 6100 | 6100 | 0 | 0 | 5.147541 | 274 | 6100 |
| c2s | mlkem_off | 보조 정의 | 588 | 6100 | 6100 | 0 | 미확인 | 9.639344 | 274 | 6100 |
| both | x25519_off | 주 정의 | 634 | 6100 | 6100 | 0 | 0 | 10.393443 | 0 | 6100 |
| both | x25519_off | 보조 정의 | 634 | 6100 | 6100 | 0 | 미확인 | 10.393443 | 0 | 6100 |
| both | mlkem_off | 주 정의 | 629 | 6100 | 6100 | 0 | 0 | 10.311475 | 393 | 6100 |
| both | mlkem_off | 보조 정의 | 1022 | 6100 | 6100 | 0 | 미확인 | 16.754098 | 393 | 6100 |

| 방향 셀 | 정의 | MLKEM-x25519 차이(%p) | 95% 구간(%p) | 짝 블록 수 | 누락 블록 | 자유도 |
|---|---|---|---|---|---|---|
| c2s | 주 정의 | 0.065574 | [-0.790097, 0.921244] | 61 | 0 | 60 |
| c2s | 보조 정의 | 4.557377 | [3.574845, 5.539909] | 61 | 0 | 60 |
| both | 주 정의 | -0.081967 | [-1.124708, 0.960773] | 61 | 0 | 60 |
| both | 보조 정의 | 6.360656 | [5.117319, 7.603993] | 61 | 0 | 60 |

PTO 비율 차이의 구간은 짝 블록에서 계산했다. 구간이 영을 포함하면 차이를 확인하지 못한 것으로 읽는다. 계획용 검정력 근사는 실제 검정력이 아니며 블록 상관과 탈락을 반영하지 않았다.

## 관측 범위

| 셀 | 팔 | 범위 | 유효 RTT 비율 | 실제 mean_idle_ms | idle 상태 | wait_plus_gap 진단(ms) | C1 경로 제외 |
|---|---|---|---|---|---|---|---|
| both | mlkem_off | 전체 | 0.995941 | 미확인 | 미확인 | 8 | false |
| both | mlkem_off | 번인 뒤 | 0.995902 | 미확인 | 미확인 | 8 | false |
| both | mlkem_off | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| both | mlkem_off | c2s=5% s2c=5% | 0.995941 | 미확인 | 미확인 | 8 | false |
| both | mlkem_off | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| both | mlkem_off | not_one_rtt | 0.978206 | 미확인 | 미확인 | 8 | false |
| both | x25519_off | 전체 | 0.989852 | 미확인 | 미확인 | 8 | false |
| both | x25519_off | 번인 뒤 | 0.989836 | 미확인 | 미확인 | 8 | false |
| both | x25519_off | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| both | x25519_off | c2s=5% s2c=5% | 0.989852 | 미확인 | 미확인 | 8 | false |
| both | x25519_off | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| both | x25519_off | not_one_rtt | 0.90313 | 미확인 | 미확인 | 8 | false |
| c2s | mlkem_off | 전체 | 1 | 미확인 | 미확인 | 8 | false |
| c2s | mlkem_off | 번인 뒤 | 1 | 미확인 | 미확인 | 8 | false |
| c2s | mlkem_off | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| c2s | mlkem_off | c2s=5% s2c=0% | 1 | 미확인 | 미확인 | 8 | false |
| c2s | mlkem_off | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| c2s | mlkem_off | not_one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| c2s | x25519_off | 전체 | 0.997346 | 미확인 | 미확인 | 8 | false |
| c2s | x25519_off | 번인 뒤 | 0.997377 | 미확인 | 미확인 | 8 | false |
| c2s | x25519_off | 번인 | 미확인 | 미확인 | 미확인 | 미확인 | false |
| c2s | x25519_off | c2s=5% s2c=0% | 0.997346 | 미확인 | 미확인 | 8 | false |
| c2s | x25519_off | one_rtt | 1 | 미확인 | 미확인 | 8 | false |
| c2s | x25519_off | not_one_rtt | 0.947853 | 미확인 | 미확인 | 8 | false |

연결의 절대 시작·완료 시각이 없어 실제 mean_idle_ms는 null·미확인이다. feedback 대기와 설정 gap의 합은 wait_plus_gap 진단이며 실제 idle의 대체값이 아니다. X6의 실제 idle 차이 기준은 미확인으로 남긴다. C1은 표준 QUIC에 없는 서버 datagram 회신이다.

## 한계

토큰·resumption 기준선(X4), 업링크 오입력(X2), A_pre와 PTO 배수 탐침(X3), s2c 손실(X5), 다른 QUIC 스택(X7), initial congestion window 10(X8), 시간 상관 손실(E24), 중복 전송 기준선(dup), first flight 부풀리기(k-inflate), 서버 first flight 7.7~9.0 KB 띠와 Initial 확대 팔, H c6000, D_p15_4032, 7.8 kB 응답 TTLB는 재지 않았다.
