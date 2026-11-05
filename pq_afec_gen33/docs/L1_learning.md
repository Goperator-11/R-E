# L1 도착 증거와 손실 학습

2026-11-02 정정: 이 문서는 L1(상태 4, v3.3-dev)의 설명이다. 지금 활성 정책 v3.3.1-dev(상태 11)는 C1 회신이 확인되기 전 목적지에 v3.2-dev와 같은 1비트 이진 우도와 결정(shield·nominal2·guard 건너뛰기, guard 벌점, 16번째 재평가)을 쓰고, 아래의 데이터그램 우도와 HCT 3등급(범주) 우도는 C1 회신을 본 목적지에서만 쓴다. 그 목적지의 결정에는 guard 벌점이 없고 `arrival_streak`가 0보다 크면 16번째 재평가를 미룬다. 근거 `docs/V33FIX_policy.md`.

`padfec3.learn3.observe3`는 연결마다 데이터그램 우도, HCT 3등급 우도, 예측 전용 중 하나를 적용한다. 도착 증거가 완전하면 HCT와 관계없이 데이터그램 우도를 쓴다. 상태 버전은 4, 정책 버전은 `v3.3-dev`다. 결정 점수의 guard 벌점과 16번째 재평가 규칙은 유지한다.

이 구현은 L1의 도착 우도와 최소 categorical fallback을 포함한다. 목적지별 EPS Beta 추정과 역사 자료의 등급 재생은 L2, 감시·벌점·재평가 변경은 L3, Go 이식은 G1의 범위다. Python 단위시험 통과를 W1 전체 성능이나 실측 검증 완료로 해석하지 않는다.

## 입력 계약

기존 호출에 선택 키워드 `arrivals=None`을 추가했다. `None`은 `{"src":"none","sent":0,"lost":0,"bitmap":null,"trunc":false}`로 정규화한다. 객체를 넘길 때는 아래 다섯 필드가 모두 있어야 하며 추가 필드를 허용하지 않는다.

| 필드 | 의미와 검증 |
|---|---|
| `src` | `c1`, `ack`, `none` 중 하나다. |
| `sent` | 첫 비행에서 전송한 원본과 패리티의 데이터그램 수다. bool을 제외한 정수 0..8이다. 상한은 현재 k≤4, m≤4 지원 범위다. |
| `lost` | 그 첫 비행에서 서버에 도착하지 않은 수다. bool을 제외한 정수이며 0≤lost≤sent다. |
| `bitmap` | null 또는 정수 0/1 목록이다. 1은 물리 도착, 0은 확인된 미도착이며 복구 성공 표식이 아니다. 완전 자료는 길이가 sent이고 0의 수가 lost여야 한다. |
| `trunc` | bool이다. true인 자료는 censored로 처리한다. 부분 bitmap은 길이≤sent만 검사하고 그 계수나 빠진 위치를 손실 학습에 쓰지 않는다. |

`src=none`에 남아 있는 0이 아닌 계수도 진단에 보존하지만 데이터그램 우도에 넣지 않는다. `sent=0`, `trunc=true` 역시 유효한 완전 증거가 아니다. 잘못된 필드나 범위는 ValueError로 거부한다. `observe3`는 사본에서 검증·갱신한 뒤 성공한 경우에만 원래 상태에 반영하므로 오류가 나면 원래 상태 전체가 유지된다.

count-only의 `bitmap=null`도 c1 또는 ack가 전체 첫 비행의 완전한 계수를 보증하면 사용할 수 있다. API는 ACK가 실제 물리 도착을 보증하는지 판정하지 않는다. 호출자는 복구 원본의 ACK, ACK 유실, 미확인 패리티, 늦은 도착을 포함한 불완전 자료를 none 또는 censored로 내려야 한다. C1과 ACK를 같은 연결에 두 번 호출해 합치면 안 된다.

실제 C1 입력은 첫 비행 CRC 목록과 맞춘 계수여야 한다. 원시 `RxOrigN`에는 재전송이 섞일 수 있다. `FbRxRetx`는 클라이언트→서버의 첫 비행 목록 밖 CRC 개수이며 서버 응답의 재전송 바이트가 아니다. 전멸 증거는 lost=sent로 받을 수 있지만 학습기는 PTO, 실패, 회신 부재만 보고 그 값을 만들지 않는다. C2와 회신 관측의 자격 판정은 별도 관측 어댑터의 책임이다.

## 우도와 연결 시계

유효 도착 증거의 각 격자 우도는 `p**lost * (1-p)**(sent-lost)`다. 구현은 1.0에서 시작해 lost번 p를 곱한 뒤 sent-lost번 1-p를 곱한다. 이항계수와 EPS 평활화를 추가하지 않는다. 계수만 같은 bitmap은 같은 우도를 만든다. 순서는 향후 Go 이식에서도 유지해야 한다.

도착 증거는 cold, 기준선 부재, k/S/RTT 문맥 부재, 명목 2-RTT, RTT 차폐, guard 경보, 실패 연결에서도 사용한다. HCT 우도를 추가로 곱하지 않는다. `filter_step` 자체가 hazard 전이를 포함하므로 그 앞에 `predict_step`을 호출하지 않는다. 우도가 없는 경로만 `predict_step`을 한 번 호출한다.

도착 증거가 없거나 censored일 때는 관측 전 k/S 이력과 제공된 정책 RTT로 만든 문맥이 있어야 범주 우도를 쓴다. 현재 연결의 k나 서버 바이트를 이력에 미리 넣어 문맥을 만들지 않는다. 문맥이 없으면 예측 전용이며, 성공 관측의 이력은 그 뒤에 갱신한다.

## 최소 3등급 경로

등급 번호는 0=`one_rtt`, 1=`two_rtt`, 2=`late_or_failure`다. 성공 HCT가 첫 경계보다 작으면 0, 첫 경계 이상이고 둘째 경계보다 작으면 1, 둘째 경계 이상이면 2다. 실패는 HCT가 없어도 2다. 실패 등급을 붙일 수 있어도 문맥이 없으면 범주 우도를 계산하지 않는다.

첫 경계는 `layout.one_rtt_cutoff_ms(rtt,k,m,lead,W+delta,u)+3.0`이다. 둘째 경계는 첫 경계에 RTT와 `layout.response_term(m,W+delta,u,later)`를 더한 값이다. 추가 margin1·margin2는 0이다. 3.0ms는 A0 고정 팔의 HCT와 모형 차이 약 3.003ms를 참고해 미리 정한 등급 여유다. 독립적으로 식별한 처리 시간 추정값이 아니며, 처리 시간 공급 계약은 J2에서 다시 다룬다. RTT는 현재 정책에 제공된 관측값을 쓰며 O3 보정이나 세계의 참 RTT를 대신 넣지 않는다.

각 격자의 등급 확률은 `layout.evaluate`의 p_one_rtt, p_two_rtt, p_fail이다. `model_point`의 기존 4원소 반환값은 유지하고 같은 캐시 항목에 등급 확률을 함께 보관한다. EPS는 0.001로 고정하고, 확률 q에 `(1-EPS)*q + EPS*(1-q)/2`를 적용한다. EPS는 다른 두 등급으로 잘못 라벨될 총확률이다. 세 등급 전체의 균등 오염식과 구별한다. 목적지별 EPS 갱신은 아직 없다.

현재 p_fail은 첫 비행 복구 실패 질량이다. 시간 경계보다 늦은 모든 HCT의 확률과 같지는 않다. 역방향 손실, 지터, RTT200 탐침, 둘째 왕복 꼬리는 등급 모형 오차를 만들 수 있다. J1 이후 꼬리 질량, J2 처리 시간, O3 RTT 보정과 연결해야 한다. 감사의 내부 정답 등급을 이용한 model-world 성능 수치와 동일한 분류기라고 주장하지 않는다.

## 진단과 상태

반환값의 `loss_update_kind`는 `datagram`, `categorical`, `predict_only`이며 `updated`는 실제 우도 적용 여부다. `skip`은 실제 예측 전용일 때 `no_ctx`이고, 나머지 두 경로에서는 null이다. `arrival_usable`, `arrival_reject_reason`, src·sent·lost·trunc·bitmap은 선택 근거를 남긴다. grade와 이름, 경계, RTT 출처, 처리 여유, EPS도 반환한다.

`legacy_y`, `legacy_skip_reason`, `legacy_shielded`는 이전 1비트 라벨과 skip 조건을 진단용으로 보존한다. 1비트 y는 손실 우도에 사용하지 않는다. 기존 `likelihood` 함수와 EPS=0.01은 역사적 이진 모형 검산용으로 남아 있지만 `observe3`가 호출하지 않는다. HCT/S 창과 guard 잔차는 기존 규칙을 유지한다. 특히 S_hist의 y 기반 표본 선택은 L5 전까지 남으므로 도착 우도를 넣었다고 S 추정까지 교정된 것은 아니다.

상태 카운터 `predict`는 모든 연결의 hazard 전이 횟수라는 기존 의미다. `datagram`, `categorical`, `predict_only`는 실제 경로별 연결 수이고 앞의 두 수의 합이 `upd`다. `arr_c1`, `arr_ack`, `arr_none`은 받은 증거원별 연결 수, `arr_trunc`와 `arr_empty`는 불완전·빈 계수 표식 수다. `arr_sent`, `arr_lost`에는 실제 도착 우도에 사용한 데이터그램만 합산한다. `grade_*`는 판정 가능한 시간 등급 수이며 문맥 없는 실패의 2등급도 포함한다.

`no_base`, `no_ctx`, `nominal2`, `shield`, `guard`는 legacy 라우팅의 진단 수다. 이전 우선순위를 유지하므로 baseline이 없으면 no_ctx보다 no_base가 먼저 잡힌다. 실제 학습 누락 수는 `predict_only`와 반환 진단을 봐야 한다. `events`는 실제 우도 경로와 무관하게 y=1인 연결 수다.

버전 1·2·3 상태를 명시적으로 거부한다. 새 상태를 생성해야 하며 과거 이진 우도로 형성된 사후분포를 도착 우도 상태로 승계하지 않는다. EPS Beta 상태 등 직렬화 의미가 다시 바뀌면 후속 과제에서 버전을 재검토한다.

## 확인한 시험

새 도착 시험은 우도 곱셈 순서, 독립 hazard 계산, 연결당 한 번의 갱신, malformed 입력의 상태 보존, C1 계수가 같을 때 HCT·실패·guard와 무관한 posterior, censored fallback, cold 문맥 누출 방지, 등급 경계와 확률 질량, 구상태 거부를 다룬다. 보호 행동 `(0,0,4)`, `(1,0,4)`, `(0,3,1)`을 고정하고 손실률 0/2/5/15%의 도착열을 각 1600연결 넣어 마지막 400개 추정 평균을 확인한다. 이는 합성 IID 증거의 학습 시험이며 netem 측정이나 GE 불확실성 검증은 아니다.

`runs/L1_learning_units_01.txt`의 첫 실행은 53개 통과, 4개 실패다. 독립 식의 `h/n`과 구현의 `h*(1/n)` 사이 반올림 차이를 exact equality로 비교한 시험 오류였다. 상대 1e-14, 절대 1e-15 허용오차로 바꾼 뒤 기존 학습·상태 시험을 함께 실행한 `runs/L1_learning_units_02.txt`에서 91개와 하위 시험 11개가 통과했다. 최초 실패 로그는 보존했다.

기존 핵심 관문의 첫 실행 `runs/L1_learning_core_01.txt`에서는 167개와 하위 시험 376개가 통과하고 2개가 실패했다. 하나는 오류 주입 대상이 더 이상 호출하지 않는 이진 likelihood였으므로 실제 categorical 경로로 옮겼다. 다른 하나는 명목 2-RTT가 무조건 갱신을 막는다는 옛 시험 기대였다. categorical 갱신과 legacy 진단을 구분하고, 문맥 없는 예측 전용 사례도 추가해 full/frozen_loss/skip_hazard_ablation의 사후·hazard 보존 검사를 유지했다.

수정 후 `python -I -B C:\dev\codex_handoff\v33\runs\w1_pytest.py`로 README 핵심 시험 목록과 `tests/test_padfec3_arrivals.py`를 함께 실행했다. `runs/L1_learning_core_02.txt`에 169개, 하위 시험 376개 통과와 실행 시간 19.74초를 기록했다. `git diff --check`도 통과했다.

`experiments/adaptation_benchmark.py`는 정책의 layout 모형으로 합성 비용을 만드는 기존 진단 도구다. L1의 none 경로를 호출해도 독립 세계나 C1 관측을 구현한 도구가 되지는 않는다. 해당 시험은 재현성·후보 비용·ablation 상태 보존을 확인하며 L1의 독립 W1 성능을 판정하지 않는다. 이번 학습 변경에서 그 생산 코드는 수정하지 않았다.
