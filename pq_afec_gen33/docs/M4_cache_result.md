# M4 재방문 관측 캐시와 잔여 과제, 반복57

관측 캐시를 활성 정책과 분리해 구현했다. 클라이언트의 실제 토큰 전달과 수락 Retry, 연결 뒤 TLS full/resumed/unknown을 구분한다. 실행 전에는 티켓 제안이 있어도 full·resumed 이력을 모두 반환한다. 서버 수락이나 미래 TLS 결과를 선택 입력으로 쓰지 않는다. 기본 목적지16개·분류별32관측, 별도 상태1의 직렬화·중복·입력 원자성을 검증했다. 활성 L1 상태4와 Go 기본 옵션은 유지한다.

## 검증 결과

119개 시험이 통과했다. 캐시65개·ClientHello 판독10개·기존 재방문 참조44개다. 실패나 결측을 HCT0으로 넣지 않고, 토큰 거절은 새 연결·토큰 없음 계획을 반환한다. 티켓 제안 뒤 거절, 실측 결과 결측, 잘못된 상태·판본·sequence·LRU·창 상한·복사본 변경을 검사했다. 실제 소켓의 토큰 거절 처리와 자동 재접속을 구현한 것은 아니다.

기존 T2와 M4의56조건·168연결·174입력을 계획에 고정했다. 첫 smoke18연결은 통과했으나 전체 v1은 ClientHello 완성 전에 DCID가 바뀌는 입력에서 중단됐다. 전수 진단에서 원인을 첫 원본을 송신 단계에서 버린12연결로 확인했다. relay에는 그 원본 바이트가 없어 PSK 제안 여부를 완성할 수 없었다. 실패 계획·진단·판독 코드를 보존하고 결측을 명시하는 v2를 만들었다. 결측을 티켓 제안 없음으로 바꾸거나 세션 캐시 적중으로 채우지 않았다.

v2는156연결의 첫 ClientHello를 재조립하는 데 사용한322개 Initial 패킷을 인증했다. 패킷 수에는 복제본도 포함한다. 토큰 전달72개, 수락 Retry44개, 실제 PSK 제안36개와 TLS 재개36개를 확인했다. 156번의 직렬화·복원이 일치했고 독립 검산기의 LRU·보관 창·실행 전 조회와 최종 상태가 같았다. 불완전한12연결은 캐시에 넣지 않았다.

| 클라이언트 관측 분류 | 연결 수 |
|---|---:|
| no_token_unknown/full | 40 |
| no_token_unknown/resumed | 4 |
| retry_unknown/full | 32 |
| retry_unknown/resumed | 12 |
| token_unknown/full | 48 |
| token_unknown/resumed | 20 |

기존 자료에는 실제 티켓을 제안했지만 TLS 재개가 거절된 연결이0개다. 이 분기의 단위 시험은 합성 입력이며 실제 서버 키 교체·만료·terminal INVALID_TOKEN 검증을 대신하지 않는다. PSK 제안은 첫 ClientHello의 확장41로 확인했다. 확장45의 모드 지원과는 구분한다. 형식 근거는 [RFC 8446 PSK 정의](https://www.rfc-editor.org/rfc/rfc8446.html#section-4.2.11)다.

## M4 상태

반복55의 Python 후보 허용·추가 묶음 참조, 반복56의 기본 off Go 고정 팔, 이번 관측 캐시는 검증했다. 현재 구현은 최적 T를 선택하거나 토큰 pacing·Retry 왕복·dup/pad 공동 HCT를 계산하지 않는다. W1 전후 성능 비교를 실행하지 않았고 새 정책을 채택하지 않았다. 기존351시험·548하위 검사와 Go 시험(PASS 231, SKIP 2, 감사 시점. SKIP 2개는 `M1_REFERENCE_GZIP`이 있어야 도는 M1 와이어 관문이다)·race·정책 동치 관문은 관련 소스 해시가 그대로여서 재사용했다.

M4는 blocked로 기록한다. E31은 E28의 송신 전 훅을 재사용해 실제 토큰·PSK·현재 k와 캐시·거절 fallback을 연결한다. E32는 E20·E27·E30과 함께 최적 T·정확 바이트·토큰 pacing·full/resumed·Retry 실패 비용을 검증하고 전체 W1·Go 채택 관문을 맡는다. 기존 auto·auto3 토큰/재개 거부와 활성 L1 상태4·T6 기본값을 유지한다. 다음 의존 완료 과제는 J8이다.

수치 생성은 m4_cache_diagnostic_v2.py, 독립 검산은 m4_cache_verify_v1.py다. 입력 출처와 소스 SHA는 M4_cache_replay_v2.plan.json, 실패 입력 목록은 M4_cache_full_v1.failure.json에 있다. 사후 와이어 판독을 실행 전 입력 훅으로 해석하지 않는다.
