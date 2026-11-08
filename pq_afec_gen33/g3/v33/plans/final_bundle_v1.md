# 최종 개발 측정 계획 v1

2026-11-06, F20. 이 계획은 아직 실행하지 않은 development 측정의 입력이다. 활성 정책은 v3.3.1-dev, STATE_VERSION 11, Go cache schema padfec3.cache3/11이다. confirmatory는 false다. 질문은 같은 자리와 크기의 padding 대비 parity의 차이, 공통 서버에서 세대별 클라이언트의 차이, 두 key exchange group의 PTO 사건 비율 차이다.

러너 입력은 `g3/v33/plans/final_bundle_v1.json`이다. F20 및 F26~F31의 조정 문장을 원천 항목보다 우선한다. 조건 출처는 로컬 보존 `C:/dev/codex_handoff/final/runs/card_F20.md`와 같은 폴더의 card_F26.md부터 card_F31.md까지다. 옛 TASKS의 X1·X6·T7 내용은 사용하지 않았다. 구현 조건은 `docs/T7_conditions_v31.md`, 주장 범위는 `docs/REPORT_CLAIMS_v33.md`를 따른다.

## 실행 전 고정할 것

계획 JSON과 이 문서를 측정 전에 함께 커밋한다. 러너는 계획 경로에 대한 마지막 변경 커밋을 읽으며 저장소의 현재 HEAD로 대신하지 않는다. 추적되지 않았거나 변경 중인 계획은 종료 코드 2로 거부한다. 결과의 plan_commit과 plan_sha256은 JSON의 실제 커밋과 UTF-8 파일 바이트의 SHA256이다. 문서 커밋과 SHA도 함께 남긴다. 첫 단위의 실제 started_at은 계획 커밋 시각보다 뒤여야 한다. 바이너리 sha 또는 srcsha가 null이면 run과 smoke를 거부한다.

결과를 본 뒤 조건을 보완하거나 바꿀 때는 v1을 덮지 않고 v2 등 별도 계획을 먼저 커밋하며 탐색으로 표시한다. 미정 optional 항목은 보충 계획 없이 실행하지 않는다. plan_commit의 실제 결과 확인은 F26~F30에서 한다.

동결 경로는 모두 로컬 보존 WSL 경로다. F16 완료 뒤 아래 실제 바이너리 SHA와 srcsha 파일을 읽어 고정했다. gen33은 qamp.sha256 내용과도 일치한다.

| 바이너리 | 경로 | SHA256 | srcsha |
|---|---|---|---|
| gen33 | 로컬 보존 `~/frozen/gen33_63854e33/qamp` | `63854e33ac2a33531f3463c72d31899a5f7df5642910497e8ac94ccec308c63a` | `8e3c09609184de9062072019736c90fd174d91092568e4532c94e1a3e236033d` |
| g3c | 로컬 보존 `~/frozen/g3c_6baf2b52/qamp` | `6baf2b5235d9906062d524af708ee28f06b2c20fa11c64fbc8bb51bc7f274d9b` | `6284fdcf2d324bae4aee6aef56d7f339aa01c3b267e3aa3225277e7c87b3ade4` |
| g2 | 로컬 보존 `~/frozen/g2_d98b05d7/qamp` | `d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213` | `b181677970b7dd4338099f37c6837b8bc4aacff3caa1a186b9a2c6c442f2be19` |

## 공통 실행 조건

quic-go v0.61.0 테스트베드, 합성 인증서, 기본 W 1280 B, initial congestion window 32 packet이다. 필수 팔은 -ips 없이 실행하며 정책의 확대 결정 뒤 ips_eff와 실제 parity 크기는 별도로 기록한다. parity datagram 상한은 1452 B다. optional 띠 셀의 FEC off Initial 확대 팔에만 -ips 1400 또는 1452를 명시한다. 모든 팔의 timeout은 10 s다. 정책 uplink는 netem 대역의 참값을 입력하며 무제한은 0이다. X2의 오입력 팔만 이 입력을 바꾼다.

손실은 Bernoulli이고 X9 양방향 셀을 제외하면 c2s에만 건다. 양방향 지연은 각각 RTT/2, rate는 uplink에만 건다. 카드가 seed를 지정하지 않았으므로 새 seed를 선별하지 않고 실제 tc 설정을 기록한다. token-store와 session resumption은 끄며 X4만 별도 계획으로 다룬다.

gen33 공통 서버는 sealed31, FEC on, basic 경로다. 셀마다 certgen으로 PEM을 한 번 만들고 팔별 서버에 같은 PEM과 -certsize를 함께 준다. PEM은 로컬 보존 WSL 측정 경로 ~/v33_runs/<id>/certs/에만 둔다. 결과에는 DER 크기와 SHA를 남긴다. 팔마다 서버·포트를 나누고 블록마다 서버를 새로 시작한다. 연결 로그 수집 전에는 0.3+2×RTT/1000 s를 기다리고 SIGTERM으로 끝낸다. M1의 a·e와 X10만 동결 서버를 쓰며, M1 optional g는 conn-log를 끈다.

| 팔 | 클라이언트 조건 | 서버 회신 |
|---|---|---|
| v33none | gen33 sealed31, fec auto3, cache3, feedback 끔 | 끔 |
| v33c1 | gen33, fec auto3, cache3, feedback, repeat_first, client-tracer=false, profile 없음 | sealed31 feedback, 판본 2 |
| v31auto | 동결 g3c, fec auto3, cache3 | 끔 |
| g2auto | 동결 g2, fec auto, cache, probe-every 20 | 끔 |
| m4L3 / m4L2 | gen33 sealed31, fec on, layout v3, m4, lead3 / lead2 | 끔 |
| pad4L3 / pad4L2 | 해당 고정 팔에 pad-junk 추가 | 끔 |
| trailing_junk4L3 | m4L3에 corrupt-parity 3 추가 | 끔 |

각 클라이언트에는 group별 expect-k와 uplink-mbps를 명시한다. v33c1 대기 한도는 max(200 ms, 2.5×RTT)로 고정해 bigcert·p11은 200 ms, RTT200은 500 ms다. 이 C1은 표준 QUIC에 없는 서버 회신이다. 동결 클라이언트 팔의 서버 fb_sent는 0이어야 한다. v33none은 C1 이력이 없는 새 캐시로 시작하며 종료 캐시도 c1_seen=false여야 한다.

Williams 순서는 짝수 n팔이면 n행, 홀수면 2n행이다. 첫 행은 0,1,n-1,2,n-2 순서로 만들고 행마다 mod n 이동한다. 홀수는 역순 행도 붙인다. 팔 표의 순서를 기준으로 행 번호는 (궤적 내 누적 블록 번호+궤적 번호) mod 행 수다. 두 번호는 0부터 시작한다. 조건, 궤적, phase, 블록 순서로 실행하며 한 블록 안의 팔 순서만 Williams로 회전한다.

auto 팔의 캐시는 셀·궤적·팔마다 새로 만들고 같은 궤적의 phase와 블록 사이에는 유지한다. 재개할 때는 연속 완료 단위의 검증된 cache_after에서 복원한다. 재개 횟수를 독립 궤적 수에 더하지 않는다. X6에서 300연결 phase를 10블록×30으로, 400연결을 20블록×20으로 나누는 것은 F20의 실행 설계 선택이다. 총연결 수와 손실 일정, 번인은 카드 그대로다. 궤적 시작행을 회전해 네 궤적을 합쳤을 때 각 phase의 팔 자리 수를 맞춘다.

## 필수 묶음과 예상 시간

| 과제 | 카드 | 계획 연결 수 | 예상 분 |
|---|---|---:|---:|
| M0 | F26 | 480 | 2 |
| M1 | F27 | 7,200 | 20 |
| X1 | F28 | 8,680 | 30 |
| X9 | F29 | 25,620 | 40 |
| X6 | F30 | 35,200 | 126 |
| RTT200 유휴 대조 | F20/MS-28, F30 | 900 | 6 |

합계는 78,080연결, 약 224분이다. M1 optional g와 F31은 제외했다. 시간은 카드의 추정 합이며 이번 기계의 실측 시간이 아니다. M0는 약 2분, M1은 연결당 약 0.162 s, X1은 bigcert 약 0.162 s·RTT200 약 0.285 s, X9는 약 0.09 s를 쓴 카드 추정이다. X6는 카드의 약 2.1시간을 사용했다. 서버 재시작과 C1 실제 대기로 실행 시간이 달라질 수 있다.

### M0: smoke

bigcert는 cert 16000, RTT 50 ms, uplink 2 Mbps, k2, 손실 2%·15%다. RTT200은 cert 9000, uplink 2 Mbps, k2, 손실 15%다. p11은 cert 2955, RTT 50 ms, uplink 무제한, k2, 손실 0%다. 각 셀에서 자동 네 팔과 고정 두 팔을 20연결씩 실행한다. bigcert·p11의 고정 팔은 m4L3·pad4L3, RTT200은 m4L2·pad4L2다.

성공률은 셀·팔별 0.95 이상, 프로세스 반환 코드는 0이어야 한다. tc의 delay·rate·loss를 확인한다. 실현 손실은 팔별 판정 없이 셀 전체의 v0 Sent·dropped 증분을 합쳐 명목 손실률 이항분포의 중앙 99.9% 예측구간으로 판정한다. 시도 수는 Sent packets와 dropped의 합이다. 고정 팔 first_flight_bytes는 2560, parity 바이트 폭은 각 셀·팔 안에서 48 B 이하다. pad의 0과 parity 팔을 합쳐 폭을 계산하지 않는다. gen33 parity는 1452 B 이하여야 하고 pad 서버 recovered는 0이다. 동결 팔 서버 parities는 양수, recover_crc_fail은 0이다. recovered 양수 기준은 손실 15% 셀의 동결 팔에만 적용한다. 2%·0%에서는 값만 보고한다.

gen33 행은 flight_expectation.source=explicit이고 k가 계획과 같아야 한다. v33c1의 arrivals.src=c1 비율과 feedback_wait_received 비율은 셀 전체에서 0.85 이상이어야 한다. RTT200 대기 한도는 500 ms다. v33none은 모든 행의 arrivals.src와 policy_path가 none이고, v33c1은 첫 회신 뒤 policy_path가 c1이어야 한다.

20연결 평균 HCT 범위는 bigcert 2% m4L3 60~130 ms, bigcert 15% m4L3 60~170 ms, RTT200 m4L2 200~300 ms, p11 m4L3 45~60 ms다. 범위 밖이면 범위를 바꾸지 않고 실패 처리한다. mean_idle_ms와 유효 RTT 비율 경고는 M0 checks에 넣지 않는다. M0는 성능 근거로 쓰지 않는다.

### M1: 서버 교체와 A/A

bigcert 2%에서 각 팔 40연결×30블록이다. a는 동결 g3c m4L3와 동결 g3c 서버, b는 같은 클라이언트와 gen33 서버, c·d는 gen33 sealed31 m4L3와 서로 다른 gen33 서버 포트다. e는 동결 g2 m3와 동결 g2 서버, f는 같은 클라이언트와 gen33 서버다. 동결 클라이언트 플래그는 봉인 p21 ARMS의 fec·m·layout·lead를 따른다. a·e는 conn-log가 없고 최종 stats.conns를 읽는다. 인증서 DER은 목표 N+5~N+8 B일 수 있어 실제 값을 보고한다.

주 결과는 a-b, e-f, c-d, b-c의 짝 블록 평균 차이와 95% 구간이다. c-d 구간이 [-5,5] ms 밖으로 나가면 status는 판정불능이다. 실행 중단 실패는 반환 코드 비정상, 자료 없음, n_blocks<30뿐이다. 판정불능이어도 X1·X6는 같은 자를 쓰고 계속한다. optional g는 c에서 conn-log만 뺀 팔이며 측정 시작 전에 포함 여부를 고정한다. c-g로 비용을 보고하고 추가 예상 시간은 3.2분이다.

탐색 항목 a_vs_sealed는 a의 평균에서 봉인 g3fixL3 bigcert 2% 층별 재계산 값 83.1 ms를 뺀다. 출처는 MS-33의 p31_run1_S_bigcert다. 봉인 커널은 6.18.35.2-microsoft-standard-WSL2이며 현재 커널은 실행 때 수집한다. 절댓값이 5 ms를 넘으면 X1·X6·X9 문서에 "봉인 환경과 표류가 있다"를 적는다. 이내여도 같은 환경이라고 쓰지 않는다. a-b 또는 e-f 구간이 [-5,5] ms를 벗어나면 X6에 "봉인 측정과 직접 비교 불가"를 적고 팔 간 비교만 낸다.

### X1: padding과 parity

bigcert의 m4L3, trailing_junk4L3, pad4L3를 손실 2%에서 39블록×40연결, 15%에서 28블록×40연결로 비교한다. RTT200 15%는 m4L2와 pad4L2를 16블록×20연결로 비교한다. 양쪽 sealed31, 공통 서버와 인증서, gap 50 ms, timeout 10 s, expect-k 2, uplink-mbps 2다.

주 차이는 padding 팔 HCT에서 parity 팔 HCT를 뺀 짝 블록 평균과 95% 구간이다. 1-RTT 비율 차이와 서버 수신 바이트 차이도 보고한다. first flight의 추가 바이트는 parity 팔의 first_flight_parity_bytes, pad 팔의 extra_sent.first_bytes를 쓴다. pad의 first_flight_parity_bytes는 0이다. CID 길이 차이가 있으므로 1 B 단위 동일을 요구하지 않고 실제 차이를 보고한다. pad 서버 recovered=0과 m4L3 recovered>0을 확인한다.

### X9: PTO 사건 비율

cert 512, RTT 50 ms, uplink 무제한, 손실 5%에서 c2s만인 조건과 양방향 각 5%인 조건을 분리한다. x25519와 X25519MLKEM768의 FEC off 팔을 같은 gen33 basic 서버에 붙이며 두 클라이언트 tracer를 모두 켠다. gap은 8 ms다. group별 expect-k는 1과 2다.

방향마다 그룹별 105연결×61블록, 6405연결을 실행한다. 매 블록 앞 5연결을 워밍업으로 분리해 분석 분모는 그룹당 6100이고 허용 최소는 6095다. 주 PTO 사건은 observation.pto_count>=1, 보조 사건은 initial_datagrams>first_flight_datagrams+1이며 두 정의의 불일치 수를 보고한다. 비율 차이 방향은 MLKEM-x25519다. 짝 블록 비율 차이의 95% 구간, HCT 평균·p99, 실패율을 함께 낸다. 사건 필드 누락은 조용히 분모에서 빼지 않는다.

원 측정은 qhct.go genCert의 자체 서명 P-256으로 보이며 DER 길이는 재지 않았고 qamp 하한 512 B를 썼다. 옛 표는 손실 0.5~5% 균일·버스트를 합친 값이라 이 5% 조건과 같은 양이 아니다. 분모가 확인되지 않은 옛 PTO 비율과 z값은 인용하지 않는다. 구간이 0을 포함하면 차이를 확인하지 못했다고 쓴다.

검정력 계산은 기저율 미확인 상태에서 Bernoulli 분산 상한 0.25를 쓰는 독립 비율 정규근사다. 양측 alpha=0.05, 목표 검정력 0.8이고, 그룹당 필요 수는 ceil(2×0.25×(z0.975+z0.8)^2/delta^2)다.

| 차이 (%p) | 근사 필요 수/그룹 | 계획 분석 수/그룹 | 계획 수의 근사 검정력 |
|---|---:|---:|---:|
| 1.5 | 17,442 | 6,100 | 0.381033 |
| 3 | 4,361 | 6,100 | 0.912075 |

계산은 로컬 보존 `C:/dev/codex_handoff/final/runs/F20_generate_plan.py`와 F20_plan_numbers.json에 남겼다. 실제 블록 상관과 탈락을 반영한 검정력은 미확인이다. 이 계산을 근거로 고정한 61블록을 바꾸지 않는다.

### X6: 공통 서버에서 자동 네 팔

각 셀·팔에 독립 궤적 네 개를 둔다. S_bigcert와 S_rtt200은 손실 2→15→2%에서 phase마다 300연결, 궤적당 900연결이다. D_p11_2955_l0는 무손실 400연결이다. 각 궤적 첫 300연결을 번인으로 분리한다. 주 HCT 비교는 번인 뒤 자료의 v33none-g2auto와 v33none-v31auto 차이다. 독립 표본은 블록이나 연결이 아닌 네 궤적이고 Student t 구간의 자유도는 3이다. C1 대 none의 서버 수신 바이트, 1-RTT 비율, 행동 분포, p_mean 궤적도 보고한다.

계획 예상 반폭은 bigcert 4~5 ms, RTT200 2~5 ms다(MS-21 정정). 실제 반폭보다 작은 차이는 판정불능으로 쓴다. 손실 2%·15% 층별 값과 번인 뒤 두 층을 1:1로 가중한 값을 함께 낸다. W1 B1의 450×3 일정과 직접 대조하지 않는다.

v33c1의 feedback_received_rate_by_class를 one_rtt 분류별로 낸다. 부류에 행이 20개 이상인데 수신률이 0.95 미만이면 해당 셀을 C1 경로 측정에서 제외했다고 표시한다. 셀·팔별 valid_rtt_rate<0.90은 경고다. RTT200 봉인에서 0.000~0.013도 관측됐으므로 이 경고만으로 자료 없음으로 처리하지 않는다. 서버 fec_parse_fail 합과 g2auto의 ips_used>=1395 행 수를 함께 낸다. gen33 auto의 fec_parse_fail이 양수이면 checks 실패다.

## A/A 자와 연결 간격

X1·X6의 bigcert 2% 셀에만 M1 c_d의 abs(mean)+(ci95 상한-ci95 하한)/2를 자로 쓴다. 러너와 결과 생성기는 같은 M1 JSON을 읽는다. 차이의 절댓값이 자보다 작으면 판정불능이다. M1 c_d가 [-5,5] ms를 벗어났으면 "자 표류 큼"을 덧붙인다. 다른 셀과 혼합 전체·1:1 재계산에는 "A/A 없음"을 쓰고 95% 구간의 0 포함 여부를 본다. 이 규칙은 M1 결과를 보고 고치지 않는다.

| 셀 | 비-C1 gap | v33c1 gap | 추가 대조와 판정 |
|---|---:|---:|---|
| bigcert | 50 ms | 1 ms | max(1,gap-RTT). X6 전체 궤적 유휴 차이만 5 ms 이내 판정 |
| RTT200 | 50 ms | 50 ms | v33none gap 250 ms 궤적 하나 추가. 평균 유휴와 차이·구간만 보고 |
| p11 | 8 ms | 8 ms | 대역 제한이 없어 맞추지 않고 실제 유휴만 보고 |

mean_idle_ms는 같은 클라이언트 단위의 연속 연결에서 다음 연결 시작 시각과 현재 HCT 완료 시각의 차이다. 실제 feedback_wait_ns를 포함하며 대기 한도를 실측값으로 대입하지 않는다. 블록 경계 서버 재시작 간격은 따로 보고한다. 전체, 손실 층별, one_rtt 분류별 값을 남긴다.

5 ms 판정은 S_bigcert의 번인을 포함한 궤적 전체, 2%:15%가 2:1인 평균에만 적용한다. M0, 손실 층별, one_rtt 분류별, 번인 뒤 1:1 값에는 적용하지 않는다. F20의 예상은 C1-none 차이가 2% 약 -3 ms, 15% 약 +14 ms, 전체 약 +2.5 ms이며 측정값이 아니다.

RTT200 gap250 대조는 300/300/300 일정의 새 캐시 궤적 하나다. 기존 X6 RTT200의 궤적 0, v33none gap50과 v33c1을 각각 대조로 삼고 같은 phase·블록의 idle·HCT 차이와 구간을 낸다. 이것은 궤적 하나 안의 진단이며 네 독립 궤적 결과로 세지 않는다.

## 수집과 분석 계약

모든 결과는 env의 uname_r, python3_V, tc_V, ip_V, cpu_list, cpu_count와 실제 실행 바이너리 SHA·srcsha를 보존한다. 요약은 g3/v33/results에, 원자료는 로컬 보존 WSL 측정 폴더에 둔다. 결과와 문서는 같은 저널에서 다시 만들 때 같은 바이트여야 하며 devreport와 SHA 기록이 모두 성공한 뒤 잠금을 해제한다.

gen33 conn-log는 실제 줄 수와 stats의 lines를 맞추고 errors=0, pending=0, conn_acct_evicted_lru=0을 확인한다. lines>=tls_accepted여야 하고 실패 행 없는 단위는 lines=클라이언트 행 수여야 한다. lines-tls_accepted는 not_accepted로 값만 남기며 이를 단위 실패로 바꾸지 않는다. gen33 client_scid로 연결을 대응하고 빈 값·중복·미대응을 기록한다. 로그 순서로 대응을 채우지 않는다.

비용은 서버 계수 bytes_in과 conn-log를 사용한다. 둘을 중복 합산하지 않고 손실 조건의 표에는 서버 수신량이라고 적는다. 클라이언트 parity 계수는 진단이며 g2auto에는 client_parity_count_unreliable을 붙인다. first flight 바이트와 연결 전체 비용을 구분한다.

고정 팔 차이는 짝 블록 평균의 Student t 95% 구간, X6는 궤적 평균 차이의 구간을 쓴다. 계획된 실패 연결 HCT는 p21과 같이 timeout 10000 ms로 집계하고 성공만의 HCT와 실패율도 별도로 낸다. 누락되거나 깨진 단위는 보간하지 않고 자료 없음으로 표시한다. 실행·자료 상태와 통계 판정 상태는 따로 둔다.

1-RTT는 p21의 ms<1.5×RTT+선행 바이트 직렬화 시간이며 ok 행에만 적용한다. 선행 바이트는 first_flight_bytes에 선행 추가 datagram 수×slot 크기를 더한다. parity는 first_flight_parity_bytes와 first_flight_parity_dgrams, first_flight_lead_dgrams를 쓴다. 동결 gen-2처럼 lead 필드가 없는 행은 p21.row_lead와 같이 m_used>=2이면 min(1, first_flight_parity_dgrams), 아니면 0으로 둔다. m_used나 datagram 수가 정수가 아니어도 0이다. pad는 extra_sent.first_bytes와 first_sent, first_lead를 쓴다. 분모가 0이면 추가 바이트는 0이다.

## F31 optional

필수 X1·X9·X6 결과 파일이 먼저 있어야 한다. F31 하위 과제를 시작할 때마다 예상 종료가 report_cutoff보다 6시간 앞서는지 확인한다. report_cutoff는 2026-11-12 23:59 KST, 측정 시작 마감은 같은 날 16:00 KST다. 이 조건을 못 맞추면 남은 항목을 시간 부족으로 닫는다. 모든 항목은 tier optional, enabled_by_default=false, hold_out_excluded=true다.

| 순서 | 항목 | 고정한 내용 | 예상 시간과 미정 범위 |
|---:|---|---|---|
| 1 | X10 | 동결 g2 양쪽, cert4032, RTT10·50·100·200, 두 group FEC off, 무손실, gap8 ms, 5블록×40연결/팔 | 셀별 RTT·gap·서버 재시작으로 실행 전에 예상 시간을 기록. 값만 보고 |
| 2 | D_p15_4032_l0 | x25519, k1, RTT50, rate0, 손실0, 자동 네 팔×네 궤적×400연결 | 약7분 |
| 3 | X2 | bigcert 2%·15%, H c6000 1%·8%, netem 고정, 입력 참값·0·u/2·2u·10, 설정마다300연결 | 15~30분. 기준 팔은 v33none으로 계획. 번인·분석 구간 보충 계획 필요 |
| 4 | H c6000 | cert6000, RTT120, rate10, k2, 손실1→8→1%, phase300씩, 자동 네 팔×네 궤적 | 약53분 |
| 5 | 띠 셀 | cert8000, RTT50, rate2, 손실2%, m4L3와 FEC off ips1400·1452, 20블록×40연결 | 약7분. cert8000과 실제 서버 first flight 크기를 구분 |
| 6 | X3 | (1,0,4)·(0,0,4), 무손실, RTT120×uplink1·5·10, 200연결. PTO는 drop-initial k-1, RTT50·120·200×lead0·3×uplink0·2 | 약35분. cert·group·k·PTO m·표본·블록과 뒤 parity credit 필요 표본을 먼저 고정 |
| 7 | X4 | v33auto, token+b0, token+뒤 parity(0,0,2), Retry+b0, resumption+b0, 첫 연결 분리 | 약102분. 셀·블록·연결 수·C1·수집 대기 보충 계획 필요 |
| 8 | 전역 고정 팔 | (0,3,1), m4L3 | 셀·블록·연결 수·예상 시간 보충 계획 필요 |

X2의 모름 팔은 O2 미채택으로 제외한다. X3의 (1,0,4)에서 delta=1을 실행하는 방법과 D50의 ips 예외 범위는 미확인이다. D50을 바꾸거나 행동을 delta=0으로 대체하지 않는다. 미정 값은 JSON에 requires_subplan으로 남겼으며 실행 가능한 값으로 간주하지 않는다. F31에서 별도 계획을 먼저 커밋하고 필수 결과 이후 확정한 설계는 탐색으로 표시한다.

hold 팔은 같은 credit 전제가 깨져 제외했다. dup와 k-inflate, 7.8 kB 응답 TTLB, X5·X7·X8·E24는 이번 묶음에 없다. Initial 확대는 optional 띠 셀만 등록했다. 실제 성능과 C1 간격, 서버 계수 비용은 F26~F31 실행 전까지 미확인이다.
