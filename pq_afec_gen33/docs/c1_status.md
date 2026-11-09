# C1의 현재 상태

보호된 gen-2 팀 문서 `C1 서버 피드백 설계.md`는 수정하지 않았다. 그 문서의 "알려진 결함"과 gen33 구현을 아래처럼 구분한다.

서버의 RxOrigN과 RxParityN은 첫 Handshake를 보기 전 원시 계수다. 중복·재전송이 포함될 수 있다. 이 사실은 여전히 맞지만, 클라이언트의 matchFirstFlight는 T4 이전부터 first flight CRC 목록과 서버의 실제 수신 CRC를 대조하고 있었다. 따라서 "CRC 처방 미적용"이라는 문장은 현재 gen33 클라이언트에 맞지 않는다. m=0도 클라이언트가 보낸 원본 CRC 목록을 갖고 있어 동일하게 대조한다.

T4는 피드백 판본을3으로 바꿨다. 실제 수신 CRC와 복원 CRC를 각각 보낸다. 복원된 원본을 물리 도착으로 세지 않으며, first flight 원본·parity·다른 CRC 수와 복원된 first flight 원본 수를 행마다 기록한다. 기존 recov 원시 계수는 first flight 외 복구를 포함할 수 있으므로 별도 대조 수와 구분한다. 판본2는 읽을 수 있지만 복원 CRC 목록은 없다. 동결된 판본2 클라이언트(gen-2·v3.1·v3.2)는 판본3 회신을 이해하지 못한다. 그래서 2026-11-02에 서버 플래그 `-feedback-version 2|3`(기본 3, 서버 전용)을 넣었다. 판본 2 회신은 동결 클라이언트가 읽고, gen33 클라이언트의 arrivals는 판본 3과 같으며 진단 행 `c1.recovered_original`만 0이 된다. 동결 클라이언트가 붙는 서버에서 `-feedback`을 켤 때는 `-feedback-version 2`나 `-profile sealed31`을 준다. 세대를 섞는 서버의 규칙은 `docs/T7_conditions_v31.md`, 수정과 시험은 `docs/V33FIX_testbed.md` F1 절에 있다.

복원 Handshake가 ReadFrom의 즉시 반환, pending 대기열, 늦은 복구, hold 수신기를 거칠 때도 같은 회신 함수를 호출한다. 연결당 한 번만 보낸다. 실제 도착 목록은 첫 Handshake를 관측한 시점에서 잠긴다. 이후 늦게 도착한 first flight datagram은 목록에 없을 수 있다. truncated=false는 그 시점의 목록이 저장 상한에 걸리지 않았다는 뜻이며, 무한 시간까지의 최종 도착을 보증하지 않는다.

유효한 arrivals는 활성 L1의 기존 관측 함수로 들어간다. C1이 없거나 꺼져 있으면 none 경로다. 잘린 목록이나 중복 송신 CRC, 소켓 쓰기 실패는 검열한다. 회신 없음·PTO·실패만으로 모든 원본을 잃었다고 적립하던 gen33의 gen-2 C2 호출을 제거했다(D13). gen-2 정책 산술과 동결 비교 바이너리는 바꾸지 않았다.

이 피드백은 인증되지 않은 평문 부채널이다. Handshake 헤더 식별은 AEAD 검증 완료를 뜻하지 않는다. T5 첫 단계는 peer와 자체 발급 CID를 검사하며 정상 CID 회전도 추적한다. 인증 위협 모형은 docs/c1_threat_model.md에 있다. CRC는 datagram 식별을 위한 개발 계측이며 공격자의 조작을 막지 않는다. 과거 설계 문서의 "회신이 증폭 예산에 영향을 주지 않는다"는 문장을 이 구현 검증만으로 일반화할 수 없다.

unrecoverable_seen은 중간에 parity가 부족했던 관측 수다. 새 unrecoverable_final은 알려진 FEC 비행이 수신기 TTL에 도달했을 때 원본과 복원본이 모두 없는 경우를 한 번 센다. flights_finalized와 flights_pending을 같이 보고, 비행 기록이 없는 전멸은 이 분모에 들어가지 않는다. 성공적인 복구 전의 일시적인 부족을 최종 실패라고 해석하지 않는다.

시험과 와이어 형식은 `docs/T4_observation_contract.md`, 실행 결과는 `docs/T4_observation_result.md`에서 확인한다. 기능 시험은 HCT 성능 효과나 배포 안전성을 입증하지 않는다.

X6 개발 측정(S_rtt200, cert 9000 B, RTT 200 ms, uplink 2 Mbps)에서 C1 경로는 none보다 primary HCT가 10.71 ms 길었다(95% 구간 [6.73, 14.69], [X6 결과](X6_result.md)). 같은 cert·RTT·uplink의 W0 셀 B11에서 v3.3.1-dev c1과 none의 차이는 -0.017 ms였다(`g3/v33/V33FIX_benchmark_v1.json`의 n131072 주 표). C1 대기창에 받은 비회신 datagram이 정책 S 추정에 들어간 것이 원인으로 보인다. C1W-1, C1W-2에서 정책 S와 RTT 입력을 대기 전 값으로 바꿨고, 수정 뒤 값은 재측정 X6S 결과가 나오면 따로 적는다. 그 전에는 B11 비열등을 실측 근거로 쓰지 않는다.
