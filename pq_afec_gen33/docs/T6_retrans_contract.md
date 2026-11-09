# T6 후속 Initial 묶음 계약

2026-11-02 정정: 아래 본문의 "retrans-layout=original_first가 새 v3 기본값"은 이 계약을 고정한 2026-11-01 당시의 결정 D28이다. auto3 비용 모형이 이 재전송 보호를 아직 반영하지 않아(J3 blocked, J4 대기) 지금 qamp `-retrans-layout` 기본값은 다시 `repeat_first`이고 `original_first`는 `-retrans-layout original_first`로 명시할 때만 쓴다(루프 결정 D43이 D28을 대체). 원본 우선·뒤 XOR 1개 모양 자체의 계약은 그대로다. 마지막 문단의 "L1상태4를 유지한다"도 이 계약을 쓴 2026-11-01 상태이고, 2026-11-02 작업 트리의 활성 정책은 v3.3.1-dev(상태 판본 11, `docs/V33FIX_policy.md`)다. 근거는 `docs/V33FIX_testbed.md`(F4 절과 통합 정리 절)와 `C:\dev\codex_handoff\v33\state\DECISIONS_NEEDED.md`의 D43이다.

v3 FEC의 첫 묶음은 기존 (L,O,T)를 유지한다. 큰 서버 응답을 아직 받지 않은 후속 묶음은 원본을 먼저 보내고 XOR parity1개를 뒤에 둔다. parity가 비활성인 off·buf에는 추가하지 않는다. 서버 응답 뒤는 기존처럼 원본 즉시 송신, 첫 행동의 T가 양수일 때만 뒤 XOR1개다. v2 송신은 그대로다.

retrans-layout=original_first가 새 v3 기본값이며 repeat_first는 이전 v3 후속 (L,O,T)를 명시 재현한다. 첫 행동이 전부 lead라도 새 기본값의 응답 전 후속 묶음에는 T'=1을 쓴다. 이는 J3·J4 카드의 기본 보호 수준과 같다. T'를 성능 결과로 고르지 않는다. 사용자 지정 옵션은 두 값만 허용한다.

입력 시각은 WriteTo 직렬화 잠금을 얻은 뒤의 처리 시작이다. 그 잠금을 기다린 시간은 별도 계측하지 않는다. 묶음 시작 때 phase·rule·lead·trail·original_immediate를 고정한다. phase는 first_bundle, pre_response_followup, post_response다. 서버 응답은 기존 srvBig의1200 B 이상 비회신 datagram 조건이다. 이 조건을 암호학적 검증 완료나 서버의 전체 비행 수신으로 부르지 않는다. PTOCountAtStart는 기존 qlog 만료 사건 계수의 하한이며 PTO 인과 증명이 아니다. 후속 묶음은 재전송·ACK·타이머 분할일 수 있으므로 pre_response_followup 자체를 PTO 재전송이라고 쓰지 않는다.

행에는 retrans_layout과 연결 전체 bytes_parity를 첫 묶음 parity bytes와 함께 기록한다. flight_trace에는 묶음마다 실제 적용 모양, 계획한 parity 수, 성공한 parity 수·바이트를 보존한다. 실패·주입 소거는 성공 수에 넣지 않는다. 첫 묶음과 이후 합계는 기존 최종 송신 완료 관문 뒤 갱신한다.

layout.evaluate와 Go p3Evaluate는 현재 재전송 보호 수준을 명시하지 않은 기존 실패 근사다. 이 과제에서 정책 산술·학습 상태를 바꾸지 않는다. J3·J4는 이 계약의 L'=0,T'=1과 전체 바이트를 사용해 실패 종류·두 번째 실패·탐침 credit을 새로 평가해야 한다. 원래 모형과 새 와이어가 완전히 같다고 쓰지 않는다. E15는 실제 ACK·PTO·CID·CRYPTO 중복과 큐 경로의 잔여를 맡는다.

검증은 v3 m1~4·모든lead·k1~3의 첫·응답전후 묶음과 v2 golden, 단일소거 복구·상한·종료 회계, 기존 Go·Python 관문이다. 실제 RTT200의 original_first·repeat_first 두 고정 팔을 기능 smoke에 추가하고 둘의 원본 k와 parity 수를 헤더·행·relay로 대조한다. HCT·Finished 출발 지연·RTT유효99%는 기능 검사로 보장하지 않는다. A3-01의 later_parity_sent≤1 제안은 후속 묶음이 여러 개면 성립하지 않을 수 있어 묶음별 T≤1과 연결 합계를 구분한다. 기본300 us·lead-hold off·L1상태4를 유지한다.
