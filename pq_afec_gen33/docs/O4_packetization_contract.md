# O4 현재 ClientHello의 패킷 수

이 단계는 활성 정책과 분리된 Python 기준 구현이다. 입력은 이번 연결의 완성된 ClientHello CRYPTO 길이, 적용할 Initial datagram 크기 W, 실제 DCID·SCID 길이, 실제 토큰 길이다. 과거 k 최빈값과 고정 오버헤드51 B로 대체하지 않는다. 정수 산술만 쓴다.

범위는 고정 quic-go v0.61.0의 QUIC v1, 응답 전, ACK·재전송·0-RTT 없이 연속으로 패킹하는 첫 ClientHello다. 모든 CRYPTO 바이트가 준비되어 있어야 한다. SNI·ECH scrambling이 켜졌거나, 이미 응답을 받았거나, 불완전한 ClientHello이면 이 참조는 계산을 거부한다. 길이만으로 SNI 위치·순서나 이후 ACK 크기를 알 수 없기 때문이다. NEW_TOKEN은 응답 전 Initial에 실리는 토큰 길이로 계산할 수 있지만 Retry 뒤의 비행을 같은 first flight로 취급하지 않는다.

W의 허용 범위는1200~1452 B다. 플래그0은1280 B,1~1199는1200 B,1453~65535는1452 B로 별도 정규화한다. 헤더는 type·version·CID 길이 필드7 B에 두 CID, 토큰 길이 varint와 토큰, 고정2 B Length, 패킷 번호를 더한다. AEAD 태그는16 B다. first flight의 패킷 번호 길이는 고정 소스의 미확인 패킷 수 규칙을 따른다. CRYPTO offset과 length의 varint 길이를 패킷마다 계산한다. MaxDataLen은 고정 소스처럼 길이1 B로 가정한 뒤 필요하면1 B를 뺀다. W 범위에서 이 규칙을 별도 완전 탐색과 비교한다.

개발 참조의 입력 상한은 ClientHello65536 B, 토큰4096 B, 패킷 수64다. 이는 자원 상한이며 QUIC 프로토콜의 일반 한도가 아니다. 정책이 지원하는 k≤4와 별개다. T3 확대 검사에서 나오는 k>4도 정확히 기록하고 정책 지원으로 표시하지 않는다.

검증은 합성 경계와 기존 T3 basic·oob 원시 패킷을 쓴다. Initial을 인증 복호해 전체 ClientHello와 각 CRYPTO offset·길이를 재구성한다. 실제 CID·토큰·패킷 번호 길이와 W를 추출해 참조의 모든 패킷 경계와 대조한다. T3 이후 토큰·재개 자료는 같은 전제 충족 여부를 따로 검사한다. 원시 자료의 해시와 소스 사본을 보존한다. 새 네트워크 측정이나 HCT 성능 주장으로 읽지 않는다.

정책 연결 전에 각 후보의 W_eff에서 k를 다시 계산해야 한다. 기존 quantum의 k_floor 설명은 qamp가 실제로 그 패킷 수를 강제한다는 증거가 아니다. 이번 단계는 k가 바뀌는 폭을 표로 남기며 활성 decide3·policy3·fecConn·상태 판본4를 바꾸지 않는다. 현재 qamp는 정책 계획 뒤에 tr.Dial을 호출해 ClientHello를 만든다. 실제 ClientHello와 CID·토큰이 결정된 시점의 훅, 후보별 k, first flight 종료 신호가 이어질 과제다. Go 거울은 작업 계약에 따라 G1에서 맞춘다.
