# E12 L1 Go 구현과 비교 계약

2026-11-02 정정: 활성 정책은 이제 v3.3.1-dev(상태 11)이고 Go에도 그 판이 옮겨졌다. C1 회신이 확인되기 전 목적지는 v3.2-dev와 같은 1비트 이진 우도·결정을 쓰고, 아래의 datagram 우도와 HCT 3등급 우도는 C1 회신을 본 목적지(c1 경로)에서만 쓴다. 이 계약의 E12 L1 참조(`g3/v33/E12_l1_reference_v1.json`)와 생성기(`g3/l1_go_reference_gen.py`)는 새 정책에 맞지 않고, 지금 관문 참조는 `g3/v33/V33FIX_policy_reference_v1.json`이다. 근거 `docs/V33FIX_policy.md`, `docs/V33FIX_policy_go.md`.

활성 Python L1의 상태 4와 정책 v3.3-dev를 Go에 옮긴다. J7의 46 B 후보는 보존 사본에 두고 이번 비교는 현재 39 B 기하를 쓴다. 도착 자료가 완전하면 datagram 우도를 쓰고, 그렇지 않으면 관측 전 문맥의 HCT 3등급 우도를 쓴다. 문맥도 없으면 hazard 예측만 한다. 기존 shield·nominal2·guard 분류는 진단 계수로 남긴다.

Python 입력과 기대값을 Go 구현 실행 전에 생성해 SHA-256으로 고정한다. 보충 자료는 sent 1..8의 모든 lost 값, k 1·2·4, W 1280, u 0·2 Mbps, RTT 50·200 ms, 필요 패킷 1·7·20, delta 0·16, m 0..4의 모든 lead를 포함한다. 등급 경계는 두 cutoff 각각의 바로 아래·동일·바로 위 IEEE 754 값을 검사한다. 관측 자료는 완전·잘림·빈 도착·출처 none·실패·문맥 없음·기존 guard를 포함한다. 잘못된 자료는 예외와 상태 불변을 검사한다.

캐시 기대값은 기존 Python RttTrack의 순서대로 MinRTT와 MinHCT를 갱신한 뒤 learn3.observe3을 호출해 만든다. 결정은 관측 전 RTT로, 관측은 갱신 후 RTT로 계산한다. 실제 Go destCache3.plan과 observePred를 호출하고 MinRTT·RTTObs·MinHCT·Conns 및 상태 JSON을 비교한다. 이는 실제 C1 와이어 연결을 뜻하지 않는다. 해당 연결은 T4에 남긴다.

원래 전체 관문의 seed, 표본 수, 허용 오차는 유지한다. 현재 Python에서 새 이름의 전체 참조를 만들고 원래 참조 파일은 보존한다. 보충 비교는 이산값과 구조를 정확히 비교하고, 우도·posterior는 상대 오차 1e-12, 시간은 기존 관문의 절대 오차 1e-9 ms를 넘지 않아야 한다. 구버전 상태 거부, JSON 왕복, 실패의 원자성, Go vet·test·race와 핵심 Python 시험도 통과해야 한다.

G1 카드의 이중 구현 근거 A6-06은 run1 문서의 A6-06, 정규 ID A6r1-06에 해당한다. 본문 A6-06의 새 기계 재현은 S5, 선택적 Python 와이어 실행기는 T7이다. E12가 G1 전체나 이 두 과제를 완료한 것으로 세지 않는다.
