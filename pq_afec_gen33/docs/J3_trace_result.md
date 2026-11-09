# J3 기존 재전송 관측 대조, 반복54

기존 개발 자료 321연결 중 301연결을 검산했다. Retry 20연결은 키와 CRYPTO epoch 재구성이 필요해 계획에 따라 제외했다. 새 네트워크 측정은 하지 않았다. Python 23시험과 독립 바이트 집합 검산은 통과했지만, J3의 고정 팔 실패당 비용 오차 ±10 ms 기준은 아직 통과하지 못했다. 활성 정책은 유지한다.

## 관측 범위

입력 214파일은 T4_smoke_v4, T6_basic_v1, T6_oob_v1, T2_revisit_basic_v1, T2_revisit_oob_v1, T3_inflate_inflation_basic_v1, T3_inflate_inflation_oob_v1에서 왔다. 계획 SHA-256은 `4ae30dd9ee4018491b41fea2833611b61e8c0fedc08a93ca46f37547cbccc6e7`이다. 모든 연결을 결과 또는 Retry 미지원 목록에 넣었다.

| 지표 | 기존 개발 자료 재집계 |
|---|---:|
| 암호문이 있는 분석 연결 | 178 |
| 인증한 client Initial 패킷 | 638 |
| 그중 CRYPTO가 있는 패킷 | 460 |
| 반복 CRYPTO 패킷 | 134 |
| 반복 CRYPTO 바이트 | 107024 B |
| 첫 수신·Initial ACK 전 반복 패킷 | 116 |
| Initial ACK 뒤 반복 패킷 | 18 |
| ACK가 이미 확인한 CRYPTO와 겹친 반복 바이트 | 0 B |
| qlog 수신 Initial ACK 패킷 | 656 |
| relay CRC·길이 대응이 없는 CRYPTO 패킷 | 45 |

ACK 뒤 반복 18개는 v2 9개와 v3 9개이며 T4·T6의 fec_one·hold_one 사례에 있다. 모두 앞선 PTO callback이 없다. ACK가 확인한 바이트와 반복된 바이트의 겹침은 없었다. 이를 빠른 손실 선언의 직접 관측으로 분류하지 않는다. 손실 선언 callback과 타이머 재무장 정보가 필요하다.

첫 수신 전에 발생한 PTO callback 58개의 직전 CRYPTO 송신 callback 이후 간격은 최소 200.130050, 중앙값 200.716440, 최대 201.724260 ms다. 실제 socket 송신 시각이나 전송 계층 타이머 기준 시각과 같다고 보장할 수 없다. 이 값으로 sampled PTO 배수나 D36 상수를 맞추지 않는다.

T2·T3에서는 암호문을 인증 복호해 PN·CRYPTO 구간·패킷 길이를 대조했다. T4·T6는 암호문이 없어 qlog와 CRC·길이까지만 대조했다. 서버 ACK는 qlog에서 읽었으며 암호문을 인증하지 않았다. relay 대응이 없는 45개는 Initial 소거를 주입한 사례에 있지만, 대응 결측만으로 소거 원인을 확정하지 않는다.

## 고친 검산 오류와 검증

첫 smoke에서 T2_revisit_basic_v1/retry_token_resume_rtt200의 두 번째 연결이 실패했다. PN4가 실린 UDP 1280 B datagram은 Initial 1099 B와 Handshake 181 B로 구성된다. qlog bytes는 Initial 길이이고 CRC는 UDP 전체 길이에 대응한다. qlog coalesced=false를 근거로 두 길이가 같다고 검사한 분석기를 고쳤다. 기존 Go 기록 코드는 변경하지 않았다. 실패 소스·계획·오류를 J3_trace_failed_v1에 보존하고 실제 입력 회귀 시험을 추가했다.

최종 23시험은 구간 합집합, 부분 반복, ACK 공간과 시각, 중복 PN, CRC 충돌·결측, 인증 변조, 실제 coalesced 패킷을 검사한다. 수정 뒤 smoke와 전체 재생이 통과했다. 독립 검산은 바이트 집합으로 범위를 다시 계산하고 입력 SHA와 연결 목록을 대조했다. 기존 핵심 351시험·548하위 검사는 전체 관련 소스 해시 일치로 재사용했다.

## 남은 조건

반복52의 고정 팔 오차는 기본 참조에서 15% +1.545667 ms, 2% -49.257467 ms다. 반복53의 T6 unacked+flight 세계는 RTT50·u2·p0.15·(0,3,1) 실패당 평균 238.853683 ms로 참조 267.938282 ms와 -29.084599 ms 차이가 남았다. 이번 자료는 그 실패 비용 표본을 새로 측정한 결과가 아니다.

실제 타이머 소유권·손실 선언·ACK로 남은 CRYPTO 범위·두 번째 실패를 확인할 E29와, 전송 계약을 비용 및 세계 검증에 연결할 E30을 EXTRA_TASKS에 등록한다. E29는 기존 E25 관측 훅과 E15 재전송 경로 검증을 재사용한다. E30 완료 전 J3를 blocked로 유지한다. 전체 W1, 같은 seed31~50의 B1/B2와 0.5 ms 비열등, Go 산술 동치, 고정 팔 ±10 ms 기준을 바꾸지 않는다.

근거 파일은 J3_trace_full_v2/result.json, J3_trace_verify_v1.json, J3_trace_tests_02.json, j3_trace_replay_v2.py, j3_trace_verify_v1.py다. 이 문서의 숫자는 j3_trace_report_v1.py로 만든다.
