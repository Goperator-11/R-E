# T3 고정 비교 팔 계약

2026-11-02 정정: 아래 마지막 문단의 "original_first·L1상태4를 유지한다"는 이 계약을 쓴 2026-11-01 상태다. 지금 qamp `-retrans-layout` 기본값은 다시 `repeat_first`이고 `original_first`는 `-retrans-layout original_first`로 명시할 때만 쓴다(루프 결정 D43이 D28을 대체). pad-junk·dup 팔도 `-retrans-layout`을 따로 주지 않으면 이 기본값을 쓴다. 2026-11-02 작업 트리의 활성 정책은 v3.3.1-dev(상태 판본 11, `docs/V33FIX_policy.md`)다. 근거는 `docs/V33FIX_testbed.md`(F4 절과 통합 정리 절)와 `C:\dev\codex_handoff\v33\state\DECISIONS_NEEDED.md`의 D43이다.

pad-junk와 dup는 client의 고정 fec on·layout v3 팔에서만 쓴다. 두 옵션을 함께 쓰거나 auto·auto3·buf·off·server에서 쓰면 종료 2다. corrupt-parity와도 함께 쓰지 않는다. 학습 후보군은 이 단계에서 바꾸지 않는다.

pad-junk는 원래 parity를 계산한 뒤 같은 datagram의 Initial 외부 헤더·CID·길이를 유지하고 본문을 JUNK 표식과 0으로 대체한다. 모든 첫·후속 parity 자리에 적용한다. 복호기에는 parity로 보이지 않으므로 recovered는 0이며 credit_parities도 0이다. 감사 A5-02의 credit_parities 동일 조건은 파서 분류를 의미하므로 이 팔에는 맞지 않는다. 수신기 구현을 바꾸지 않고 같은 길이·순서, 수신·스택 바이트, 실제 회신 경로를 검증한다. 무손실에서는 parity도 미복구라 모든 바이트를 스택에 전달하는지 확인한다. 손실 시에는 복원본 대체와 스택 바이트가 다를 수 있으므로 같다고 강제하지 않는다. 이 바이트 회계가 실제 QUIC 송신 credit과 항상 같다는 주장은 하지 않는다.

dup는 parity 자리 j에 그 묶음 원본 j mod k를 바이트 그대로 복사한다. 원본 순서와 T6의 첫·응답 전·응답 뒤 배치를 유지한다. 중복을 parity로 세지 않는다. DUP datagram은 원본과 같고 헤더를 덧붙이지 않으므로 parity와 바이트 수가 정확히 같지 않다. 별도 extra_sent 필드에 종류·성공 수·바이트·오류·대조 parity 바이트와 첫 묶음 몫을 기록한다. 정책 m과 L은 추가 송신 자리 수를 뜻한다. parity_sent와 bytes_parity는 실제 parity만 센다. flight_trace도 같은 extra_sent를 보존한다. C1의 CRC 목록은 중복 송신 사건을 구별하지 못하므로 이 팔을 학습 관측에 쓰지 않는다.

corrupt-parity는 기존 첫 묶음 단일 인덱스 의미를 유지한다. m4L3에 3을 지정하면 뒤 parity만 손상된다. pad-junk와 별도 비교 조건이다. 같은 입력의 단위 시험에서 padding의 정확한 크기·위치를 대조하며 실제 연결 사이 CID·암호문·시각 차이를 짝비교 효과로 해석하지 않는다.

현재 단계는 pad·dup만 맡는다. k-inflate의 큰 transport parameter, Initial 요청 크기 1291~1472와 실제 1452상한 검증은 다음 T3 단계다. X1의 성능·서버 복호 on/off·같은 바이트 비교 계획과 E20의 후보군 확장은 해당 과제에 남긴다. 기본 300us·lead-hold off·original_first·L1상태 4를 유지한다.
