# J8 서버 프로필 참조 계약

이 참조는 실제 서버의 UDP datagram 크기 목록과 이미 보낸 바이트를 입력받는다. 인증서 바이트나 연결 전체 수신 바이트를 first flight 크기로 대신 쓰지 않는다. 활성 정책과 동결 W0 파일은 그대로 둔다.

`ServerProfile`의 명시적 quic-go 기본값은 granular, P=1280 B, IW=32개, 초기 PTO=200 ms, 선행 credit 허용, 기존 경주표다. `unknown()`은 exact, 선행 credit 없음, 뒤 parity 경주 없음으로 시작한다. IW=10개와 PTO=999 ms는 미확인 서버의 보장이 아니라 비교용 가정이다. 실제 입력은 각각 명시할 수 있다. 프로필 직렬화 판본은 1이며 활성 학습 상태와 별개다.

first flight는 주어진 순서의 datagram 전체를 보낸다. exact는 다음 datagram까지 포함한 송신량이 3B 이하여야 보낸다. granular는 보내기 직전 누적량이 3B보다 작으면 다음 datagram을 보낸다. unlimited도 IW를 유지한다. ACK 등 앞서 보낸 바이트는 `sent_bytes`에 따로 청구한다. IW는 동결 W0와 같은 datagram 개수 근사이며 바이트 단위 혼잡 제어를 재현한 것은 아니다. exact 서버의 패킷 재분할은 모델링하지 않는다. 재분할이 있으면 새 크기 목록이 필요하다.

`required_credit`는 마지막 datagram 직전 합계를 사용한다. 각 datagram이 P 이하인 목록에서 exact로 전체를 보낼 수 있으면 동일한 IW의 granular에서도 보낼 수 있다. IW를 넘는 목록은 credit을 늘려도 first flight 전체를 보낼 수 없어 None을 반환한다.

하향 손실 계산은 첫 송신 목록의 독립 손실 확률만 계산한다. 재전송 예산 함수는 잃은 datagram의 재송신에도 누적 3B 예산을 청구한다. `available_slots`는 호출자가 손실 선언 또는 ACK 이후 이용 가능한 혼잡 창을 명시하는 입력이다. 기본값은 IW 전체가 이용 가능하다는 예산 진단이다. ACK, 주소 검증, 재전송 타이머, 두 번째 송신 손실, HCT는 아직 이 함수의 범위 밖이다. 손실 없는 확률을 HCT 이득에 곱해 성능을 주장하지 않는다.

P 관측 함수는 호출자가 첫 서버 데이터 datagram으로 분류한 크기를 받는다. ACK나 Retry를 식별하는 기능은 없다. 반환한 P도 잠정 관측값이다. 모드 관측은 amplification limit 확인, 하향 무손실, 남은 송신 수요, IW 비제한, 결정 이후 credit 불변, 주소 미검증을 모두 요구한다. 조건이 빠지면 추정하지 않는다. 조건을 채워도 낮은 비율은 exact와 granular를 구분하지 못하고, 한 datagram 미만 초과는 granular 후보로만 남긴다. 계획에는 exact를 유지한다. unlimited를 바이트 비율만으로 채택하지 않는다.

프로토콜 근거: 주소 검증 전 송신량 제한은 [RFC 9000 8.1절](https://www.rfc-editor.org/rfc/rfc9000.html#section-8.1), 초기 혼잡 창은 [RFC 9002 7.2절](https://www.rfc-editor.org/rfc/rfc9002.html#section-7.2)이다. granular는 감사에서 확인한 고정 quic-go 동작을 비교하기 위한 모형이며 RFC의 정확한 3B 한도와 구분한다. 다른 서버의 동작이나 성능은 측정하지 않았다.
