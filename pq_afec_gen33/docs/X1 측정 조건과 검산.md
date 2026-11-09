# X1 측정 조건과 검산

quic-go v0.61.0 테스트베드, initial congestion window 32 packet에서 수행한 development 측정이다. 확증 결과가 아니다. 고정 padding·parity 팔을 비교했으며 활성 학습 정책의 세대 간 성능 비교는 수행하지 않았다.

실행 `final_x1_iter027_20261107`의 [자동 결과 문서](X1_result.md)와 [결과 JSON](../g3/v33/results/v33_dev_X1_final_x1_iter027_20261107.json)을 검산했다. 조건은 [선커밋 계획](../g3/v33/plans/final_bundle_v1.json)의 `tasks.X1`과 `profiles`를 따른다. 같은 셀의 팔은 공통 gen33 서버와 같은 인증서를 썼다. 봉인 측정은 세대별 서버를 썼으므로 서버 조건이 다르다.

## 조건과 주 비교

모든 팔은 W=1280 B이며 명시 `-ips` 없이 실행했다. 양쪽 `sealed31`, `-fec on`, client `-layout v3`를 사용했다. 손실은 c2s에만 적용했고 token 저장과 session resumption을 껐다. 정책 입력 uplink는 netem 대역과 같다.

| 셀 | 요청 certsize(B) | RTT(ms) | uplink(Mbps) | k | gap(ms) | c2s 손실(%) | 주 비교 | 짝 블록 | 팔당 연결 |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| bigcert_l2 | 16000 | 50 | 2 | 2 | 50 | 2 | pad4L3 - m4L3 | 39 | 1560 |
| bigcert_l15 | 16000 | 50 | 2 | 2 | 50 | 15 | pad4L3 - m4L3 | 28 | 1120 |
| rtt200_l15 | 9000 | 200 | 2 | 2 | 50 | 15 | pad4L2 - m4L2 | 16 | 320 |

bigcert의 m4L3는 m=4·lead=3, RTT200의 m4L2는 m=4·lead=2다. pad 팔은 같은 설정에 `-pad-junk`를 더했다. bigcert의 `-corrupt-parity 3` 팔은 별도 진단이며 주 비교에 합치지 않았다. certsize는 요청 인자이고 같은 셀의 인증서 동일성은 DER SHA로 대조했다.

차이는 padding 팔에서 parity 팔을 뺀 값이다. HCT 구간은 짝 블록 단위의 95% 구간이다. first flight 합계 차이는 client 진단이며 서버 비용과 구분한다.

| 셀 | HCT 차이(ms) | 95% 구간(ms) | 1-RTT 비율 차이 | 서버 수신량 차이(B/연결) | first flight 합계 차이(B) |
|---|---:|---|---:|---:|---:|
| bigcert_l2 | 4.799263 | [2.907010, 6.691517] | -0.025000 | 268.582051 | 0.353846 |
| bigcert_l15 | 35.118315 | [28.625103, 41.611527] | -0.141964 | 1439.701786 | -0.717857 |
| rtt200_l15 | 117.878381 | [77.992021, 157.764742] | -0.293750 | 394.653125 | 5.087500 |

M1 C/D 구간은 [-1.188556, 1.185171] ms이고 A/A 자는 1.188556 ms다. bigcert 2%에만 적용하며 15%와 RTT200에는 A/A가 없다. M1의 봉인 기준 대비 탐색 차이는 -1.099118 ms다. X1과 M1의 저장 환경 지문은 같지만 봉인 kernel `6.18.35.2-microsoft-standard-WSL2`과 현재 `6.18.54.1-microsoft-standard-WSL2`은 다르다. A/A 자의 시간 표류 자체는 미확인이다.

## 수집과 비용

완료 저널은 233단위, 반환된 client 행은 8680개다. 비용은 `server_delta.bytes_in`을 실패 행도 포함한 전체 반환행 수로 나눈다. `conn-log`의 귀속을 별도로 대조했고 client parity 계수는 비용에 더하지 않았다.

| 셀 | 팔 | 반환행 | 실패행 | server recovered | fec_parse_fail | 서버 수신량 합(B) | SCID 대응 |
|---|---|---:|---:|---:|---:|---:|---|
| bigcert_l15 | m4L3 | 1120 | 0 | 392 | 0 | 10551290 | 1120/1120 |
| bigcert_l15 | pad4L3 | 1120 | 0 | 0 | 0 | 12163756 | 1120/1120 |
| bigcert_l15 | trailing_junk4L3 | 1120 | 0 | 152 | 0 | 12141547 | 1120/1120 |
| bigcert_l2 | m4L3 | 1560 | 0 | 92 | 0 | 16124410 | 1560/1560 |
| bigcert_l2 | pad4L3 | 1560 | 0 | 0 | 0 | 16543398 | 1560/1560 |
| bigcert_l2 | trailing_junk4L3 | 1560 | 0 | 35 | 0 | 16571309 | 1560/1560 |
| rtt200_l15 | m4L2 | 320 | 0 | 225 | 0 | 4989242 | 320/320 |
| rtt200_l15 | pad4L2 | 320 | 0 | 0 | 0 | 5115531 | 320/320 |

pad의 first flight 추가 바이트는 `extra_sent.first_bytes`, parity의 추가 바이트는 `first_flight_parity_bytes`를 쓴다. pad의 `first_flight_parity_bytes`는 0이다. CID 길이 등의 실제 차이를 남겼으며 팔 사이 바이트가 1 B 단위로 같다고 주장하지 않는다. `not_accepted`는 서버 진단이고 client 실패 수나 비용 분모로 바꾸지 않았다.

X1에는 g2auto가 없다. `client_parity_count_unreliable`와 `g2auto_ips_used_ge1395`의 해당 팔 검사는 F30에서 확인한다. X1의 g2auto 전용 null을 0으로 채우지 않았다. `fec_parse_fail`은 PFEC 파싱 실패 계수이며 네트워크 잘림 여부를 단독으로 판정하지 않는다.

## 검증 범위와 한계

독립 helper의 통계 1044검사와 이전 앱 검산 대조 121검사가 통과했다. 이전 앱 검산 1613검사는 보존된 실행이며 이번에 재실행하지 않았다. 전체 artifact SHA 2103개를 확인했고 `experiments/v33/devreport.py --report-only` 두 회에서 결과 JSON·자동 문서·SHA 목록의 바이트가 모두 같았다. 실행 스크립트와 출력의 로컬 보존 위치는 `C:/dev/codex_handoff/final/runs/F28_iter030_documents.py`와 같은 폴더다.

RTT200의 유효 RTT 비율은 자동 결과 문서의 관측 범위에 남겼다. 낮은 비율을 새 통과 기준으로 바꾸거나 값을 보정하지 않았다. 실제 idle은 D79에 따라 null·미확인이고 wait_plus_gap은 진단이다. parity 크기 확인은 client 계측값이며 packet capture는 미확인이다. 완료 status의 마지막 블록 표시와 실제 완료 저널 수의 차이는 F44에서 기록한다.

hold·dup·k-inflate·Initial 확대 팔은 이 비교에 없다. 선택 띠 셀은 F31 범위다. X9·X6 및 다른 QUIC 스택의 결과로 일반화하지 않는다. 종합 주장과 보고서 정오표 반영은 F32에서 처리한다.
