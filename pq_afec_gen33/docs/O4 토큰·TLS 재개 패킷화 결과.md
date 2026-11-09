# O4 토큰·TLS 재개 패킷화 결과

기존 T2 개발 84연결의 첫 ClientHello 패킷 168개가 D35 참조와 일치했다. 토큰을 실은 32연결의 실제 토큰 길이는 90~91 B였다. TLS 재개 20연결, Retry를 받은 20연결이 포함된다. Retry가 있는 경우에도 여기서 확인한 범위는 Retry 전의 첫 ClientHello다.

| 검증 | 결과 |
|---|---|
| 원시 자료 | basic·oob 합계 28조건·56파일·84연결 |
| 인증된 첫 ClientHello | 84개, 각각 Initial2개 |
| 현재 입력 | 실제 CH·CID·SCID·토큰·W와 qlog PN·CRC32C·CRYPTO 범위 일치 |
| 고정 Go 직렬화 대조 | 기존 검증 바이너리에 새 84입력·168패킷 전달, 모두 일치 |
| 새 부정 검사 | 실제 자료의 누락·중복·순서·CRC·ACK·수신 시각·잘림·W·인증 태그·DCID 변조 거부 |
| Python | 기존 참조 59개와 새 12개, 합계 71개 통과 |
| 기존 핵심 검사 | O3_python_01의 351개·하위 548개 통과 뒤 관련 소스 해시 일치 |

첫 응답 전에 추가로 관측된 Initial24개는 첫 ClientHello가 완성된 뒤의 패킷이다. 이들을 k에 더하지 않았다. 뒤의 재전송·Retry 비행 전체를 복호하거나 그 패킷 수를 예측한 결과는 아니다. 토큰의 주소 검증 효과나 재개의 HCT 효과도 이 재생으로 추정하지 않는다.

입력 전달 순서는 고정 quic-go 소스에서 확인했다. newClientConnection에서 CID와 transport parameters를 만들고 토큰을 Pop해 packer에 넣는다. Conn.run은 TLS StartHandshake와 handleHandshakeEvents를 처리한 뒤 첫 송신을 예약한다. 따라서 완성된 ClientHello를 읽을 지점은 첫 송신 예약 직전이다. 현재 공개 qamp 설정에는 그 시점의 callback이 없고, PacketSent qlog는 이미 패킹한 뒤라 IPS 결정에 늦다.

후속 구현은 현재 연결의 입력과 과거 관측 이력을 구분한다. 먼저 Python 후보에서 현재 k를 결정에 쓰되 k_hist를 덮어쓰지 않고, 첫 방문에도 expectK를 별도로 산출한다. 후보 W_eff에서 k가 달라지는 범위는 별도 판정하며 고정 k 산술로 처리하지 않는다. S 사전·RTT 추정·손실 사후분포 변경을 같은 후보에 섞지 않는다.

Go 연결은 완성된 CH·실제 CID·토큰을 첫 송신 예약 전에 전달하는 훅이 필요하다. IPS를 바꾸면 Config.InitialPacketSize뿐 아니라 sentPacketHandler의 최대 datagram 크기와 maxPayloadSizeEstimate도 맞아야 한다. cached_k와 달리 first flight의 명시 종료를 신뢰하려면 전송 취소·잘림·Retry·PTO·명시 expect-k와의 우선순위를 시험해야 한다. 보호 모듈 캐시는 수정하지 않는다. 필요하면 이미 설치된 고정 소스를 개발용 사본으로 보존하고 사용한다.

O4는 계속 partial이다. 이 반복은 토큰 길이를 포함한 참조 범위를 검증했으며 정책·fecConn 연결, 전체 W1 비열등, Go 정책 거울은 아직 남아 있다. 활성 L1 상태 4와 타이머 300 µs는 유지한다. 근거는 runs/O4_token_replay_v1/result.json과 O4_token_verify_v1.json이다.
