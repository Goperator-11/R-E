# T5 UDP 경로 계약

gen33의 Linux 서버는 udp-path=oob를 기본으로 쓴다. udp-path=basic으로 이전 수신 경로를 선택할 수 있다. 클라이언트 경로와 정책 산술은 유지한다. X3의 비교 계획은 서버 경로를 명시해야 하며, 두 경로의 경주 확률과 HCT 효과는 아직 미확인이다.

래퍼는 SyscallConn, SetReadBuffer, SetWriteBuffer, ReadMsgUDP, WriteMsgUDP와 ReadBatch를 노출한다. 고정 quic-go v0.61.0은 ReadBatch가 없으면 fd를 직접 읽으므로 이 메서드도 복호 경로에 연결한다. 한 번의 ReadBatch는 복호 결과1개를 반환한다. native recvmmsg 배치를 재현하는 구현은 아니다. 이 차이는 X3의 서버 경로 대조에 포함한다.

물리 수신은 ReadMsgUDP로 읽는다. 원본과 그대로 전달하는 parity에는 해당 datagram의 OOB와 flags를 붙인다. 보류한 raw parity와 pending 결과는 자신의 메타데이터를 보관한다. 복원본에는 복호 비행 기록을 처음 만든 parity의 로컬 packet-info만 붙이고 ECN·수신 타임스탬프를 복제하지 않는다. 실제로 받지 않은 원본의 ECN 값은 알 수 없다. C1 회신도 수신한 로컬 주소의 packet-info를 사용해 wildcard 서버에서 출발지가 바뀌지 않게 한다.

송신 OOB는 그대로 UDP 소켓에 넘긴다. UDP_SEGMENT가 있으면 payload를 실제 segment 크기로 나눠 연결별 바이트·datagram·타임라인에 기록한다. 송신 직전 수신 credit을 보존하고, 실패한 송신의 연결별 계수는 복구해 GSO 실패 뒤 fallback이 중복 집계되지 않게 한다. C1 회신 바이트는 기존처럼 서버 전송 관측에서 제외한다.

검증은 원본·보류 raw·즉시 복원·pending 복원·타이머 복원의 메타데이터, 다른 연결의 OOB 혼합 방지, IPv4·IPv6 packet-info와 ECN, 짧은 버퍼, GSO segment 회계와 송신 실패를 포함한다. 실제 UDP에서 복호와 wildcard 응답을 확인하고 basic·oob 각각 QUIC smoke를 실행한다. 수신 바이트와 계수의 기존 전수 기준을 유지한다.
