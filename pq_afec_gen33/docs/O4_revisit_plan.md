# O4 토큰·TLS 재개 자료의 k 검증 계획

T2_revisit_basic_v1·T2_revisit_oob_v1의28개 조건 파일을 모두 사용한다. 조건당3연결인 기존 개발 자료이며 새 네트워크 측정을 시작하지 않는다. 토큰 유무, TLS 재개, Retry 설정, RTT200 조건을 그대로 보존한다.

각 연결의 첫 비패리티 Initial에서 키를 유도하고, 인증된 CRYPTO의 첫4 B로 TLS ClientHello 전체 길이를 읽는다. 완성될 때까지 연속 offset의 원본 패킷을 모은다. 뒤에 온 PTO 재전송이나 Retry 뒤의 새 Initial을 첫 비행에 합치지 않는다. 선택한 모든 패킷은 qlog의 PN·CRC32C·CRYPTO 범위와 맞고 첫 수신 callback 전에 나갔어야 한다. 인증 실패, 빠진 범위, 중복·겹침, CID·토큰 변화, scrambling은 적격 표본으로 인정하지 않는다.

실제 토큰 길이·CID·SCID·W를 D35 참조에 넣고 첫 묶음 k뿐 아니라 모든 패킷 경계를 대조한다. 토큰 적중과 TLS 재개는 T2 기록을 그대로 읽는다. Retry를 받은 연결도 Retry 전의 완성된 첫 ClientHello만 이 검증의 대상이다. 이후 비행에 대한 정확성을 주장하지 않는다. 입력 해시와 포함·제외 이유를 모두 기록한다.

이 단계에서는 원시 CH 준비 훅의 위치도 고정 소스로 확인한다. newClientConnection에서 CID·transport parameters·토큰이 정해지고 Conn.run의 StartHandshake와 handleHandshakeEvents가 첫 송신 예약보다 먼저 실행된다. 후보 IPS 변경 시 sentPacketHandler의 최대 데이터그램 크기·cwnd·maxPayloadSizeEstimate도 일치해야 한다. qlog의 PacketSent callback은 이미 패킹이 끝난 시점이므로 정책의 모든 입력을 사전에 얻는 훅으로 쓰지 않는다. 활성 정책·상태4·Go를 유지한다.
