# M4 토큰·Retry 참조와 기존 자료 검산, 반복55

비활성 Python 참조의 44시험과 기존 T2 개발 108연결을 검산했다. 토큰 전달·초기 서버 주소 검증·Retry·실제 TLS 재개를 분리했고, 원래 Initial 108개를 인증했다. 지원하지 않는 parity 복구 가치를0으로 두며, 연결당 추가 묶음 예산은 수락한 Retry 뒤에도 초기화하지 않는다. 활성 L1·T2 제한·T6는 유지한다.

## 기존 개발 자료

입력 112파일의 계획 SHA-256은 `5eececff0a57be1b192a3536c8bb7a9d87b31d1eb7595eb43b4d3e0660531c9b`다. T2_revisit_basic_v1·T2_revisit_oob_v1·T2_revisit_negative_basic_v2·T2_revisit_negative_oob_v1의36사례를 모두 사용했다. wire 첫 Initial의 토큰 길이와 client SCID를 읽고 인증한 뒤, 실제 서버의 같은 SCID·TLS 관측 계정과 대응했다. 새 네트워크 측정이나 HCT 전후 비교는 하지 않았다.

토큰을 실은 연결은 48개, 수락한 Retry는 26개, TLS 재개는 32개다. IP 변경의 무효 토큰8개 중4개는 Retry 뒤 검증됐고4개는 Retry 없이 미검증 상태로 진행했다. 두 경우 모두 최초 토큰의 유효성을 클라이언트가 결정 전에 안다고 가정할 수 없다.

| 실제 관측 분류 | 연결 수 |
|---|---:|
| no_token_unvalidated/full | 34 |
| no_token_unvalidated/resumed | 4 |
| retry_validated/full | 18 |
| retry_validated/resumed | 8 |
| token_unvalidated/resumed | 4 |
| token_validated/full | 24 |
| token_validated/resumed | 16 |

초기 server AddrVerified가 true라는 사실만으로 NEW_TOKEN 수락이라 분류하지 않는다. Retry가 있었다면 retry_validated에 기록한다. ticket 제안 대신 실제 DidResume를 써 full/resumed 캐시를 나누고, 서버나 TLS 관측이 없으면 unknown으로 유지한다.

## 첫 묶음 전달 확률

320조건을 별도 닫힌식으로 재검산했다. 아래는 iid 손실0.15·k2·추가2·원본1280 B, parity/padding1338 B를 명시한 진단이다. HCT·서버 pacing·PTO 비용을 포함하지 않는다. 바이트가 서로 다르므로 같은 바이트 실험으로 해석하지 않는다.

| 모드 | 복호 지원 | 첫 묶음 완성 확률 | 송신 B |
|---|---|---:|---:|
| parity | supported | 0.98801875 | 5236 |
| parity | unsupported | 0.72250000 | 5236 |
| dup | unknown | 0.95550625 | 5120 |
| pad | unknown | 0.72250000 | 5236 |

unknown·unsupported에는 parity 후보를 넣지 않는다. 강제 parity 진단의 복구 기여는0이며 pad와 같은 원본 도착 확률이 된다. k1의 뒤 parity1개와 원본 복제1개의 전달 확률은 같다. 이 결과는 A7-07·A7-18의 적용 범위를 재현하며 실제 HCT 우위나 새 정책 채택을 입증하지 않는다.

## 오류와 남은 구현

첫 독립 검산기는 무효 IP 토큰8건을 전부 Retry 없는 미검증 연결로 가정해 실패했다. 원자료와 분석 코드는 바꾸지 않고, Retry 뒤 검증된4건을 별도로 확인한 v2 검산기로 고쳤다. m4_verify_v1.py와 M4_verify_v1.failure.json을 보존했다. 기준·표본·계수 변경은 없다.

M4_revisit_policy_contract.md의 D37 기본값과 server_support_signal.md 설계 메모를 고정했다. 지원 신호는 구현하지 않는다. 기존 qamp는 정책 계획 뒤 TokenStore.Pop을 호출하므로 실제 토큰 전달 입력 훅이 필요하다. Go 송신 경로의 Retry 수락·중복 예약·후속 무추가·토큰 거절, full/resumed 캐시 연결을 다음 반복에서 검토한다. 현재 참조에는 HCT 목적함수의 토큰 pacing과 dup·pad 공동 후보 평가가 없다. E20 및 전체 W1·Go 관문을 완료해야 활성 채택을 판단할 수 있다.

핵심351시험·548하위 검사는 관련 전체 소스 해시 일치로 재사용했다. 새44시험·계획·smoke12연결·전체108연결·320확률 조건의 독립 검산이 통과했다. 상태는 partial이며 기존 정책·세계·Go 코드와 직렬화 판본을 바꾸지 않았다. 숫자는 m4_diagnostic_v1.py와 m4_verify_v2.py, 이 문서는 m4_report_v1.py로 만든다.
