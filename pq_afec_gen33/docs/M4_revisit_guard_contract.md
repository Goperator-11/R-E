# M4 고정 팔 전송 규칙

revisit-guard는 기본 off인 개발 옵션이다. fixed client fec·layout v3·m1~4·ips0 또는1280만 허용한다. Initial 크기는 기존 기본값으로 고정하므로 delta=0이다. 적응 정책과 후보별 크기 변경을 아직 연결하지 않았다. 기존 토큰·TLS 재개의 auto·auto3 거부와 T6 기본값을 유지한다.

첫 WriteTo의 유효한 QUIC v1 Initial 헤더에서 실제 토큰 길이를 읽는다. 첫 패킷의 토큰은 서버 수락을 뜻하지 않으며 server_acceptance는 unknown으로 기록한다. 토큰을 보냈으면 고정 설정의 lead를0으로 만들고 원래 trail만 남긴다. pad-junk는 추가가0이다. lead를 trail로 옮기거나 새 최적 T를 고르지 않는다. 지원하지 않는 입력은 송신 전에 거부한다.

decoder-support는 unknown·supported·unsupported다. 이 개발 옵션에서 parity를 쓰려면 supported를 명시해야 한다. unknown·unsupported는 명시한 dup·pad-junk 고정 팔에서만 실행한다. 지원 입력 없이 parity를 그대로 내보내지 않는다. DNS나 서버 협상 신호를 구현하지 않는다.

qlog.PacketReceived의 Retry만 받아 다음 묶음을 retry_bundle로 기록한다. 고정 quic-go에서는 무결성·CID·중복 검사를 통과한 뒤 이 사건이 발생한다. callback은 memoryTrace 잠금을 푼 뒤 fecConn 잠금을 얻으므로 기존 묶음 기록의 잠금 순서와 충돌하지 않는다. raw Retry 수신·PacketDropped·PacketSent는 이 상태를 바꾸지 않는다.

묶음 모양은 첫 입력 때 고정하고 추가가 있으면 예산을 예약한다. 송신 실패와 Retry는 예약을 되돌리지 않는다. 후속 묶음·PTO·응답 뒤에는 추가가 없다. 아직 예약하지 않았고 수락 Retry 뒤의 첫 묶음이라면 원래 trail만 허용한다. 이 규칙은 shim 묶음에 적용되므로 자연 ClientHello k와 다를 수 있다. 타이머 분할의 영향은 flight_trace의 actual_k·reason과 함께 기록한다.

revisit_guard JSON은 옵션을 켠 행에만 추가한다. 첫 토큰 길이·입력 출처·Retry 수락·Retry 묶음 소비·예약 수를 기록한다. 기존 송신 완료 관문 뒤 스냅숏을 찍으며 첫 묶음 및 연결 전체 바이트는 기존 원장과 대조한다. 기존 정책 상태 JSON은 바꾸지 않는다.

기능 검증은 모든 m·lead·k1~3·토큰0/91·parity/dup/pad 조합, Retry·PTO·응답 뒤, 쓰기 실패·결측·잘못된 헤더·동시성·기존 T6 시험을 포함한다. 실제 네트워크 기능 smoke는 계획·실행 지문·잠금을 별도로 보존한다. 토큰 거절 뒤 새 연결 계획, full/resumed 정책 캐시, 토큰 pacing 및 dup/pad 공동 목적함수와 전체 W1 채택 관문은 후속 단계다.
