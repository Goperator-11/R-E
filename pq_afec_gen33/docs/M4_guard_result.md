# M4 고정 팔 전송 검증, 반복56

기본 off인 revisit-guard를 Go 고정 팔에 연결했다. 실제 첫 Initial의 토큰 길이와 스택이 수락한 Retry를 입력으로 사용한다. 첫 토큰은 서버 수락과 구분해 unknown으로 기록한다. 토큰이 있으면 lead=0, delta=0이며 원래 설정의 trail만 허용한다. 연결당 추가 묶음 예약은 한 번이고 Retry·PTO·송신 실패로 되돌리지 않는다. 활성 적응 정책과 상태4·300 us·T6 기본값은 유지한다.

## 검증

| 범위 | 결과 |
|---|---|
| Go | 231개 시험, vet·race·빌드 통과. 새 시험6개, 전송 조합252개. |
| Python 소스 지문 검사 | 로컬 padding 소스·시험·go.mod 변경 감지3개 통과. |
| 옵션 거부 | 잘못된 실행 입력7개가 송신 전에 exit2로 거부됨. |
| 정책 동치 관문 | constants·primitives·decisions·trajectories·fresh 모두 PASS. 참조 결정6720개와 새 결정5000개의 비용 오차0. |
| 새 고정 팔 기능 | basic·oob 각10조건·30연결. 총60연결 성공. |
| 독립 원자료 확인 | 첫 Initial60개 인증, client SCID와 서버 TLS 계정 대응. |
| Python 계약 재생 | 실제156개 송신 묶음의 행동·예약·Retry 전이가 일치함. |
| 기존 기본 옵션 | 90연결, 성공84개와 의도한 전체 손실6개. guard JSON 필드는 없음. 기존 두 재전송 배치와 C1 검사 통과. |
| 핵심 Python | 기존351시험·548하위 검사의 관련 입력 소스 해시가 모두 일치해 재사용함. |
| 빌드 보존 | WSL stage.Pr7HTF의59파일·18,368,191 B, 실제 Go 소스50개와 빌드 입력 SHA가 일치함. |

새 기능 자료에서 토큰을 보낸 연결은32개, Retry 수락은18개, TLS 재개는8개다. 추가 datagram은124개·162,794 B이며 연결의 Initial 송신 전체는376개·485,354 B다. 이 값은 열 가지 다른 고정 조건의 합계다. 대조군 대비 절감이나 HCT 효과로 쓰지 않는다. PTO가 기록된 연결12개에서도 후속 추가가 없었다. 토큰 때문에 추가가0인 연결은12개다.

첫 번째 정책 관문은 산술 다섯 절이 일치했으나 바이너리 소스 지문에서 실패했다. T3 빌더는 padfechook/*.go와 padfechook/go.mod를 포함하고 관문은 상위 파일만 셌다. 관문에도 같은 로컬 모듈 파일을 포함해 다시 실행했다. 바이너리·정책·seed·허용 오차는 바꾸지 않았다. M4_gate_before_fingerprint_fix.py와 M4_gate_report_01.json, 실패 로그를 보존했다. 두 번째 관문은 빌드 지문9798aa226a1a1246f425bfbe407e173e7d0b5b4324e22b92146bfdd8682b009a까지 일치했다.

두 새 기능 계획은 실행 전에943a49ddf1965177441233001925c79c0d421a0c에 고정했다. 드라이버는 revisit_guard_smoke.py, 독립 검산은 m4_guard_verify_v1.py, 기본 옵션 회귀는 observation_smoke.py와 m4_default_verify_v1.py다. 모두 development 기능 검증이며 X4 성능 측정은 실행하지 않았다.

## 남은 일

현재 옵션은 delta0 고정이고 최적 T를 고르지 않는다. 지원 unknown·unsupported에서는 명시한 dup·pad만 허용하며 parity를 거부한다. 후보별 ClientHello 크기 변경·현재 k는 E27·E28과 연결해야 한다. 토큰 거절 뒤 새 연결, 실제 full/resumed 정책 캐시, token pacing·dup/pad 공동 HCT 비용과 전체 W1 비열등 판정이 남았다. M4는 partial로 유지한다. 활성 정책 채택 전에는 기본 옵션을 바꾸지 않는다.
