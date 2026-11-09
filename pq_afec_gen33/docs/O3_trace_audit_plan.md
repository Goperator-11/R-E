# O3 기존 RTT trace 진단 계획

반복48의 집계 전에 범위를 고정한다. 대상은 반복42의 T2 관측 basic·oob, 재방문 basic·oob, 재방문 음성 대조 basic v2·oob v1의 stdout66개다. 실패한 basic v1 대신 기존 T2가 검증한 v2를 쓴다. 별도 측정이나 활성 정책 변경은 없다.

qlog RTT 갱신과 같은 패킷 번호 공간의 ACK가 가리키는 최대 패킷 번호를 대조한다. 송신 기록이 하나이고 수신보다 앞서야 후보가 된다. RTT callback과 수신 callback의 차이, `수신 callback - 송신 callback`과 LatestRTT의 차이가 모두1 ms 이하인 쌍을 수치상 후보로 센다. 이1 ms는 탐색하거나 맞추지 않는다. 후보가 여러 개면 모호함을 유지한다.

이 후보는 소유권의 증명이 아니다. callback 시각은 quic-go가 `SentPacket`에 저장한 monotime과 다르고, LatestRTT에는 적용 가능한 ACK delay가 이미 빠질 수 있다. 현재 trace에는 그 ACK delay와 실제 UDP 송신 datagram별 시각·크기·대기량이 없다. 해당 정보가 없는 기존 행은 O3의 보정 표본으로 승격하지 않는다.

qlog는 바뀐 metric 필드만 내보낸다. 같은 LatestRTT가 반복되면 trace의 rtt_updates가 늘지 않을 수 있다. 따라서 rtt_updates 수는 실제 RTT 표본 수가 아니다. Retry가 RTT를 초기화하는 경로도 ACK 표본과 구분한다. RTT callback이 수신 packet callback보다 먼저 찍힌 후보를 따로 센다.

주 집계는 연결 수, 유효 path RTT, RTT metric 갱신 수, 수치상 ACK 후보 수와 모호함, HCT 뒤 후보, Retry 근처 갱신, 정보 부족 이유다. 시간 차이는 기능 진단 값이며 네트워크 성능이나 보정 정확도 추정으로 쓰지 않는다. 버전·입력 구조·패킷 번호 재사용·다중 ACK·잘림·Retry·시각 순서의 시험을 두고, 집계 숫자를 독립 검산한다.
