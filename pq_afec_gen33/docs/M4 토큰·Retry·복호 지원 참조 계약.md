# M4 토큰·Retry·복호 지원의 Python 참조 계약

2026-11-02 정정: 아래 첫 문단의 "T6 original_first 기본값"과 "활성 L1 상태4"는 이 계약을 쓴 2026-11-01 상태다. 지금 qamp `-retrans-layout` 기본값은 다시 `repeat_first`이고 `original_first`는 `-retrans-layout original_first`로 명시할 때만 쓴다(루프 결정 D43이 D28을 대체). 2026-11-02 작업 트리의 활성 정책은 v3.3.1-dev(상태 판본 11, `docs/v3.3.1 활성 정책 수정.md`)다. 근거는 `docs/v3.3.1 Go 테스트베드 수정.md`(F4 절과 통합 정리 절)와 `C:\dev\codex_handoff\v33\state\DECISIONS_NEEDED.md`의 D43이다.

M4는 비활성 참조로 시작한다. 활성 L1 상태 4, T2의 auto·auto3 토큰/재개 거부, T6 original_first 기본값은 전체 관문 전까지 유지한다. 이 참조는 행동 허용 조건과 첫 묶음 전달 확률을 검사하며 HCT 비용이나 채택된 정책을 뜻하지 않는다.

token_supplied는 해당 연결의 TokenStore.Pop 결과가 실제 Initial에 실렸다는 로컬 입력이다. 캐시 조회 적중, 서버가 초기 주소를 검증한 사실, TLS 티켓 제안, 실제 TLS 재개는 별개다. 유효성을 예측해 서버 수락으로 기록하지 않는다. 토큰이 실렸으면 lead=0, delta=0으로 후보를 제한하고 복구용 뒤 parity 또는 중복만 비교한다. 서버가 수락하지 않은 토큰도 클라이언트가 미리 알아낼 수 없으므로 같은 분기를 탄다. INVALID_TOKEN으로 연결이 끝나면 다음 시도는 그 토큰 없이 시작하며 같은 연결에 credit용 비행을 삽입하지 않는다. IP 변경·만료·키 교체의 실제 감지는 후속 전송 단계다.

decoder_support는 unknown, supported, unsupported 세 값이다. supported는 명시적 테스트베드 설정 또는 별도로 검증된 지원 신호만 받는다. unknown과 unsupported에는 parity 후보를 넣지 않고 none·pad·dup를 비교한다. 토큰 또는 Retry 뒤 pad와 양수 delta는 credit 전용이므로 제외한다. 지원 신호 설계는 서버 복호 지원 신호 설계.md에만 쓰며 DNS 조회나 새 transport parameter를 구현하지 않는다.

Retry는 QUIC 스택이 수락한 사건만 반영한다. 롱헤더 type3만 보고 바꾸지 않는다. 고정 quic-go connection.go의 Retry 처리는 무결성·CID·기존 수신·중복 검사 뒤 qlog.PacketReceived를 내보낸다. RFC도 무효 Retry를 버리고 연결 시도당 하나만 처리하도록 정한다. 수신된 Retry 토큰을 서버가 수락할지는 아직 미확인이다. [RFC 9000 §17.2.5](https://www.rfc-editor.org/rfc/rfc9000.html#section-17.2.5)

한 연결 시도에서 추가 datagram 묶음은 최대 한 번 예약한다. Retry는 이 예산을 초기화하지 않는다. 첫 묶음이 none이었다면 수락한 Retry 뒤 첫 묶음에 복구 전용 추가를 예약할 수 있다. 이미 예약했다면 Retry 뒤·PTO·후속·응답 뒤에는 추가가 없다. 송신 오류나 취소 뒤에도 예약을 되돌리지 않는다. 이는 재시도 중 중복 예약을 막기 위한 보수적 기본값이다. M4 후보의 규칙이며 기존 T6의 묶음별 T'=1과 결과를 혼합하지 않는다. 중복 Initial도 같은 추가 예산을 사용한다.

첫 묶음 전달 검산은 iid 소거, k1~4, 추가 0~4를 사용한다. dup는 T3와 같이 전체 추가 자리 j에서 원본 j mod k를 복제한다. parity의 뒤 심벌은 복구에 쓰며 lead는 기본 credit 전용이다. lead-hold 복호는 명시 진단 입력으로만 허용한다. pad는 복구하지 않는다. 원본 길이와 parity 길이는 명시 입력이고 서로 다른 실제 바이트를 같은 비용으로 부르지 않는다. 이 확률은 ACK·PTO·서버 pacing·전체 HCT를 포함하지 않는다.

관측 캐시 키는 목적지, 초기 주소 검증 종류, 실제 full/resumed/unknown TLS 결과를 구분한다. 실제 결과가 없는 실패는 unknown에 남긴다. TLS 티켓이 있었다는 이유로 resumed에 넣지 않으며, 성공했다는 이유로 토큰이 수락됐다고 간주하지 않는다. 기존 S·k 이력에 이 참조의 관측을 넣지 않는다. 참조의 연결 상태는 메모리에만 있고 기존 JSON 형식은 바뀌지 않는다.

검증은 토큰 실패·미지원·서버 증거 부재, 첫 묶음/Retry/PTO 중복 예약과 송신 실패, 원자적 입력 거부, k1의 RS=dup 및 k2의 차이, lead-only·hold 경계·정확한 바이트·독립 전수 열거를 포함한다. 실제 토큰 전달 시점은 auto3 정책 계획보다 늦으므로 연결 훅과 캐시 분리는 별도 단계다. 활성 채택에는 전체 W1의 같은 seed31~50·B1/B2·0.5 ms 비열등과 Go 거울·실제 실패 경로가 필요하다.
