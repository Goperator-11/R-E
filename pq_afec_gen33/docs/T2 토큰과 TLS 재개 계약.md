# T2 토큰과 TLS 재개 계약

client의 token-store는 프로세스 안에서 LRU(16 origins, origin당 4개)를 공유한다. 매 시행의 UDP 소켓과 Transport는 따로 만들고 quic.Config.TokenStore에 같은 저장소를 연결한다. resume는 같은 범위의 TLS LRU(16개)를 사용한다. 서버도 resume를 켜야 티켓을 발급한다. 두 옵션 기본값은 false다. Dial과 Allow0RTT=false를 유지한다. 주소 토큰과 TLS 티켓을 구분하며 첫 시행 표시·cache 조회/적중/저장·실제 TLS DidResume를 기록한다. 토큰·티켓 원문은 클라이언트 통계 JSON에 싣지 않는다. 기능 검사의 relay 와이어는 별도 증거로 보존한다.

두 옵션 중 하나를 켠 성공 연결은 HCT를 고정한 뒤 revisit-wait(기본 200 ms), handshake 경과 시간, 유효한 최근 ACK RTT 중 가장 긴 시간 동안 추가로 열어 둔다. 현재 관측 RTT 이상을 확보하기 위한 개발 입력이며 미래 RTT 상한을 뜻하지 않는다. 대기 요청·선택 시간·실제 시간·완료 여부·RTT 출처를 기록한다. 대기 중 연결이 닫히면 완료로 표시하지 않는다. C1 대기는 기존 규약을 유지하고 따로 기록한다. 옵션을 끄면 새 대기를 하지 않는다. 토큰과 티켓 수신은 저장소 Put 수로 검증하며 대기만 했다는 이유로 수신 성공을 가정하지 않는다.

verify-source는 서버 전용이며 VerifySourceAddress가 항상 true를 반환하게 한다. 서버 ConnContext에 전달된 ClientInfo.AddrVerified를 연결별·누적 통계로 남긴다. Accept 뒤의 TLS DidResume도 별도로 남긴다. Retry로 검증된 연결과 NEW_TOKEN으로 처음부터 검증된 연결은 클라이언트 qlog Retry 및 첫 Initial token 길이를 대조해 구분한다. 재전송 때문에 verify 콜백 호출 수가 연결 수보다 클 수 있다.

token-store·resume 클라이언트는 고정 off·buf·fec에서 사용한다. auto·auto3는 토큰과 TLS 재개에 맞춘 정책 관측 의미가 정리되기 전까지 거부한다. credit용 lead·delta를 줄이고 손실 복구용 뒤 parity를 고르는 정책은 E21에서 검증한다. 같은 IP·같은 서버 프로세스의 기능 시험은 토큰 유효성 상한 비교다. 실제 브라우저 재방문률이나 HCT 개선을 뜻하지 않는다. X4는 T7 측정 설계 의존을 유지한다.

검증은 두 서버 UDP 경로에서 cold·token·resume·둘의 조합과 Retry 강제, 서버 티켓 off, 후속 Initial 토큰·서버 주소 검증·양쪽 DidResume·0-RTT 부재를 확인한다. 기존 C1·FEC·padding 기능 관문과 Go race, Python 고정 시험을 유지한다. 정책 산술·상태 판본을 바꾸지 않는다.
