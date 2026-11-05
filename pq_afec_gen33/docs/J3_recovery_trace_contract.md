# J3 재전송 구간 관측 계약

기존 T4_smoke_v4·T6_basic_v1·T6_oob_v1의123연결과 T2 재방문84연결·T3 패킷화114연결을 읽는다. 새 네트워크 실행은 하지 않는다. 출처 파일·분석 소스를 계획에 해시로 묶고 모든 입력 연결을 결과 또는 미지원 사유에 남긴다. Retry 뒤 키·CRYPTO epoch 분리는 이 분석에서 지원하지 않아 Retry 연결은 별도 계수한다.

qlog의 송신 Initial CRYPTO 구간을 시간순으로 읽고 이미 보낸 구간과 새 구간을 나눈다. 수신 Initial ACK의 패킷 번호를 같은 Initial 공간의 이전 송신에만 대응시킨다. ACK가 확인한 CRYPTO와 겹치는 재송신 바이트도 따로 센다. first_flight_datagrams는 shim의 첫 묶음 크기이므로 자연 ClientHello k의 증명으로 쓰지 않는다.

T4·T6 relay에는 암호문이 없어 qlog 구간과 CRC·길이만 대조한다. T2·T3의 wire_hex가 있으면 client Initial을 인증 복호해 PN·CRYPTO 구간을 qlog와 대조한다. 서버 ACK는 여기서 암호문 인증을 하지 않으며 qlog 메타데이터라는 한계를 남긴다. CRC 일치는 암호학적 인증이 아니다. relay에 없는 패킷은 주입 소거 또는 관측 누락일 수 있어 원인을 자동 확정하지 않는다.

PTO 만료 callback이 송신보다 앞섰는지와 첫 수신·ACK·RTT metric보다 앞섰는지를 기록한다. 앞선 callback이 있다고 그 패킷의 재전송 원인을 확정하지 않는다. metric 갱신은 RTT 표본의 ACK 소유권과 구분한다. 타이머 기준 시각, 실제 socket 송신·큐, 손실 선언, ACK delay가 없는 자료로 표본 PTO 배수나 빠른 손실 시간을 적합하지 않는다.

검사는 구간 합집합·부분 겹침·공간별 PN·미래 ACK 거부, 재전송과 새 CRYPTO 분리, 같은 크기의 다른 구간, Relay CRC 충돌·결측, 인증 오류, 잘못된 qlog 구간과 시간 입력을 포함한다. 원자료에 맞추려고 입력을 보정하지 않는다. 활성 L1·상태4·세계·Go와 D36의 계수는 유지한다.
