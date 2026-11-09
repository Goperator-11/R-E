# O4 현재 k 후보의 검증 결과

비활성 Python 후보는 현재 ClientHello로 계산한 k를 결정과 해당 관측 분류에 함께 사용한다. 과거 k_hist에는 실제 관측만 남긴다. 첫 연결에 S나 RTT가 없어도 expected_k를 계산하며, 후보 W에서 k가 바뀌면 결정을 거부한다. 상태 판본 4와 활성 L1은 그대로다.

새 후보 시험 24개와 자연 패킷화 시험 59개, 합계 83개가 통과했다. 기존 핵심 351개·하위 548개는 O3_python_01.json의 통과 기록과 전체 관련 소스 해시를 재확인했다. 현재 k와 과거 최빈값의 불일치, cold·no_rtt·k_range, 실패·미확인 k, C1·none, pending·중복 관측·외부 상태 변경·원자적 거부를 검사했다.

동결 W1의 15시나리오·3관측 모드·seed31~50,900실행·1233000연결에서 후보를 재생했다. 결정의 기존 필드 전체와 관측 분류, 마지막 정책 요약은 원자료와 정확히 일치했다. 연결을 생략하지 않았으며 결과 900개·원자료 900개의 SHA와 45그룹 HCT·바이트·행동 계수를 다시 집계했다. 이 세계의 k는 B4에서 1, 나머지에서 2로 고정되어 있어 과거 최빈값과 현재 값이 같다. 합성 로컬 CH 입력은 실제 TLS 훅을 대신하지 않는다.

모든 행동이 같으므로 같은 동결 세계의 seed별 HCT·바이트 차이는 구조적으로 0이다. 새 세계 시뮬레이션이나 실제 전송 측정을 실행한 결과가 아니다. 기존 0.5 ms 비열등 범위에서 차이가 없음을 확인했으며, 개선 또는 타이머 제거 효과를 주장하지 않는다. 전후 수치는 runs/O4_bench.md에 있다.

dry-run과 45실행·180연결 smoke가 통과했다. 첫 smoke의 실행기는 집합을 JSON으로 비교하다 첫 결정 전에 실패했다. 실패 소스·계획·로그를 보존하고 입력 키 목록 비교만 고쳤다. 후보·세계·seed·기준은 바꾸지 않았다. 행동·관측 등급·관측 k를 각각 변조한 3개 자료는 검사기가 거부했다.

O4는 실제 qamp 입력 훅·expectK 종료가 연결되지 않았고, 후보별 k가 바뀌는 입력을 처리하지 못해 blocked로 남긴다. E27은 후보별 natural_k 비용·관측과 별도 k 변화 세계 평가, E28은 고정 로컬 quic-go 사본의 송신 전 훅·Go 거울·first flight 종료를 맡는다. 두 과제는 O4 완료를 의존하지 않는다. 활성 정책 채택, 첫 연결 300 us 제거, scrambling·Retry 뒤 패킷화와 실제 성능은 미확인이다.

근거: O4_current_k_contract.md, O4_current_replay_plan.md, runs/O4_current_replay_v2.plan.json, O4_current_verify_v1.json, O4_current_tests_01.json, O4_current_negative_v1/result.json. 앞선 T3·T2의 실제 패킷 검증은 O4_reference_result.md와 O4_token_result.md에 있다.
