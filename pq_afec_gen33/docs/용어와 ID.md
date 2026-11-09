# 용어와 ID

이 저장소의 문서에서 쓰는 이름을 원문과 연결한다. 과제 완료, 후보 채택, 측정 완료는 각각 구분한다. 기록 문서의 상태와 수치는 작성 시점 기준이며, 아래 F 카드 상태는 반복 36에서 F46을 시작한 뒤의 [상태 사본](../g3/v33/evidence/final/F46_loop_state_iter036.json)이다. F46의 `doing`은 그 시점을 보존한 값이다.

같은 글자와 숫자라도 출처가 다르면 뜻이 다를 수 있다. M1은 옛 hold 후보와 이번 A/A 측정에 모두 쓰인다. D1은 루프 결정과 봉인 전 편차에 각각 쓰인다. B는 세계 평가 조건, 작업 묶음, 모형 기호에서 따로 읽는다. 아래 표의 출처를 함께 확인한다.

3~6절의 출처 가운데 과제 카드(TASKS, EXTRA_TASKS), 결정 장부(DECISIONS_NEEDED), 루프 상태·일지, backlog 정리, 문서 정리용 목록은 2026-11-08에 저장소에서 뺐다. 이 이름에는 링크가 없고, 원문은 커밋 `4f26a51`에 있다.

## 1. 전문 용어

first flight, parity, padding, credit, handshake, amplification limit, datagram은 한국어 번역이나 음역으로 바꾸지 않고 이 표의 원어로 쓴다. 금지 번역어를 본문에 다시 나열하는 대신 표기 규칙을 적었다. 원문 사본은 그대로 보존한다.

| 원어·기호 | 이 저장소에서의 뜻 | 표기 규칙·근거 |
|---|---|---|
| first flight | client가 처음 보내는 원본 Initial과 그 주변의 추가 datagram 묶음. server first flight는 별도 방향의 응답 묶음이다. | 원어 유지. [배치와 관측](L1%20first%20flight%20관측%20계약.md) |
| parity | 원본을 복구하는 FEC 부호화 자료. 별도 datagram을 보내면 실제 송신 바이트가 늘어난다. | 원어 유지. [부호 형식](R3%20부호기와%20테스트베드%20형식.md) |
| padding | 바이트 수를 늘리는 채움 자료. 같은 바이트 조건에서 parity와 비교하는 팔은 계획의 전송 배치를 따른다. | 원어 유지. [같은 바이트 비교](X1%20측정%20조건과%20검산.md) |
| credit | 주소 검증 전에 서버가 수신 바이트로 얻는 송신 허용량. 복원한 원본 바이트와 물리 수신 바이트의 계수를 구분한다. | 원어 유지. [서버 회계 검증](최종%20구현%20검증.md) |
| amplification limit·amplification budget | 주소 검증 전 수신 바이트의 3배로 제한되는 서버 송신과 그 남은 허용량. | 원어 유지. [계수 규범](보고서%20주장과%20정정%20목록.md#바이트-계수-규범과-구현-범위) |
| handshake | QUIC 연결을 수립하는 과정. | 원어 유지. [관측 계약](T4%20관측%20계약.md) |
| datagram·packet | UDP 송수신 단위와 그 안의 QUIC packet을 구분한다. FEC 도착·손실과 wire 크기를 셀 때 단위를 명시한다. | datagram은 원어 유지. [wire 계약](J7%20parity%20길이와%20수신%20상한.md) |
| lead parity·L·lead | 원본보다 앞에 보내는 parity와 그 개수. 코드의 `lead`와 문서의 L은 같은 행동 성분이다. | [행동 배치](v3.3.1%20활성%20정책%20수정.md), [세계 입력](독립%20세계%20시뮬레이터.md) |
| trailing parity·T | 원본 뒤에 보내는 parity와 그 개수. | [세계 입력](독립%20세계%20시뮬레이터.md) |
| δ·delta, W, k, m | δ는 원본 크기 증가분, W는 증가 전 원본 UDP 바이트, k는 원본 개수, m=L+T는 parity 개수다. 행동은 (δ,L,T)다. | [세계 입력](독립%20세계%20시뮬레이터.md), [활성 후보](v3.3.1%20활성%20정책%20수정.md) |
| W_eff·wire | W_eff=W+δ는 부호 symbol 길이다. wire 크기는 실제 직렬화된 datagram 바이트이며 모형의 고정 오버헤드와 다를 수 있다. | [모형과 wire 한계](활성%20정책의%20알려진%20한계.md) |
| S·certsize·DER | 비용식의 서버 바이트 문맥, 인증서 목표 길이, 인코딩된 인증서 파일 바이트를 구분한다. DER 크기를 server first flight 총량으로 바꾸어 읽지 않는다. | [인증서 계측](T1%20고정%20인증서%20결과.md), [세계 입력](독립%20세계%20시뮬레이터.md) |
| RTT·round | RTT는 왕복 지연이다. 재전송 round는 다시 보낸 묶음의 차수다. | [세계 사건](독립%20세계%20시뮬레이터.md) |
| HCT | handshake 완료까지의 시간. 실패 연결을 포함하는 평균과 성공 연결만의 평균은 결과 필드로 구분한다. | [개발 통계 계약](../g3/v33/plans/final_bundle_v1.json), [X9 검산](X9%20결과%20검산과%20해석.md) |
| TTLB | 연결 시작부터 응답의 마지막 바이트까지 걸린 시간. HCT 차이를 이 값으로 복사하지 않는다. | [보고 틀](보고서%20주장과%20정정%20목록.md#p3-표류와-ttlb-서술-틀) |
| PTO | QUIC의 Probe Timeout. X9의 qlog 타이머 관측 하한과 Initial 전송 개수 보조 지표는 서로 다른 정의다. | [X9 정의와 분모](X9%20결과%20검산과%20해석.md) |
| initial cwnd·IW | 연결 시작 때의 congestion window. 이 연구의 quic-go 측정 조건은 IW 32 packet이며 다른 구현 전체의 값으로 일반화하지 않는다. | [측정 조건](X1%20측정%20조건과%20검산.md) |
| uplink·u | client에서 server로 가는 링크. 정책에 주는 uplink는 추정값이 아닌 명시한 설정값이며 0은 직렬화 제한 없음이다. | [T7 비교 조건](T7%20비교%20조건.md) |
| c2s·s2c | client→server와 server→client 방향이다. 손실률은 방향을 붙여 읽는다. | [측정 계획](../g3/v33/plans/final_bundle_v1.json) |
| learning layer·posterior·likelihood·hazard | 관측으로 손실률 분포를 갱신하는 층, 갱신된 분포, 관측의 우도, 분포 변화에 쓰는 hazard를 가리킨다. | [학습식](L1%20도착%20증거와%20손실%20학습.md), [현재 분기](v3.3.1%20활성%20정책%20수정.md) |
| guard·record_only | guard는 잔차와 경보를 관리한다. 현행 c1 경로의 record_only는 잔차를 기록하되 guard 가산 벌점이나 경보를 세우지 않는 결정을 가리킨다. | [활성 정책](v3.3.1%20활성%20정책%20수정.md) |
| C1 | 표준 QUIC에 없는 서버 수신 회신이다. CRC는 식별값이며 인증 수단이 아니다. | [위협 모형](C1%20신뢰%20경계.md), [관측 계약](T4%20관측%20계약.md) |
| c1_seen | 목적지에서 C1 또는 ACK 도착 관측을 한 번 받으면 켜지는 지속 표지다. feedback 플래그를 끄는 것만으로 지워지지 않는다. | [상태 전이](v3.3.1%20활성%20정책%20수정.md), [분리 cache](T7%20비교%20조건.md) |
| cold·b0 | 목적지의 결정 문맥이 부족한 시작 상태와 추가 행동이 없는 (0,0,0) 기준 행동이다. | [결정 순서](v3.3.1%20활성%20정책%20수정.md), [벤치 기준선](../g3/v33/bench_protocol.json) |
| sealed31 | gen33에서 v3.1 비교용 플래그를 묶은 프로필. gen33 바이너리·서버가 동결 v3.1과 같다는 뜻은 아니다. | [프로필과 예외](T7%20비교%20조건.md) |
| development·confirmatory·봉인 | 개발 자료, 미리 고정한 확증 절차, 입력과 판정 규칙을 고정·보존한 기록을 구분한다. 이번 M0·M1·X 측정은 development다. | [개발 계획](../g3/v33/plans/final_bundle_v1.json), [주장 범위](보고서%20주장과%20정정%20목록.md) |
| 세계·모형·구현 검증 | 세계는 사건 시뮬레이터의 결과, 모형은 비용식이나 가정에 따른 계산, 구현 검증은 코드·출력·회계 대조다. 각각 실제 네트워크 측정과 구분한다. | [W0 범위](독립%20세계%20시뮬레이터.md), [평가 범위](v3.3.1%20W1%20재판정.md) |
| gen-2·v3.0·v3.1·v3.2-dev·v3.3.1-dev | 연구의 세대·정책 판 이름이다. `gen_id=v3.3-dev`는 세대 식별자이고 활성 `POLICY_VERSION=v3.3.1-dev`와 구분한다. | [세대 경로](세대%20경로와%20역사%20자료.md), [상태 판본](v3.3.1%20활성%20정책%20수정.md) |

## 2. 측정·평가 이름

### 세계 평가

W0는 사건 세계를 구현·검증한 과제이고 W1은 그 세계에서 정책을 비교하는 회귀 벤치다. B 이름은 W1의 조건 가족이다. 아래 값은 [커밋된 벤치 계획](../g3/v33/bench_protocol.json)의 입력이며 새 측정값이 아니다. 구체 실행·집계 범위는 [벤치 설명](v3.3%20독립%20세계%20회귀%20벤치.md)을 따른다.

| 이름 | 계획에서 뜻하는 조건 |
|---|---|
| B1 | cert 16000 B, RTT 50 ms, uplink 2 Mbps에서 c2s 손실 2%→15%→2% |
| B2 | B1의 손실 일정만 2%→25%→2%로 바꾼 조건 |
| B3 | 무손실·cert 2955 B·RTT 50 ms. B3_u0는 uplink 제한 없음, B3_u2는 2 Mbps |
| B4 | 무손실·k=1·cert 4032 B·RTT 50 ms·uplink 제한 없음 |
| B5 | c2s 2%에서 cert 9000 B→16000 B로 바뀌는 조건 |
| B6 | c2s 2%에서 cert 9000 B와 16000 B를 같은 확률로 섞는 조건 |
| B7 | cert 9000 B, c2s 2%에 s2c 1% 손실을 더한 조건 |
| B8 | cert 16000 B, c2s 2%. B8_j10·B8_j20은 각각 평균 10·20 ms 지터 조건 |
| B9 | 연결마다 상태를 비우며 cert 2955 B·16000 B를 확률 0.65·0.35로 섞는 조건 |
| B10 | cert 4032 B·RTT 50 ms·uplink 제한 없음에서 손실률 15%, 평균 버스트 길이 3의 GE 조건 |
| B11 | cert 9000 B·RTT 200 ms·uplink 2 Mbps에서 손실 2%→15%→2% |
| B12 | 과거 보류 셀이 개발에 노출된 가족. B12_c6000은 cert 6000 B·uplink 10 Mbps, B12_c12000은 cert 12000 B·5 Mbps이며 모두 RTT 120 ms·손실 1%→8%→1%. 새 확증 holdout이 아니다. |

### 네트워크 조건과 관측 경로

조건 이름을 재사용해도 실행 일정·서버·팔·표본 수가 같다는 뜻은 아니다. 아래 네트워크 값은 [이번 개발 계획](../g3/v33/plans/final_bundle_v1.json)의 `profiles`와 각 셀에서 읽는다. 과거 봉인 결과의 해석은 [주장 문서](보고서%20주장과%20정정%20목록.md)와 해당 프로토콜을 따른다.

| 이름 | 뜻과 구분 |
|---|---|
| S_bigcert | cert 16000 B·RTT 50 ms·uplink 2 Mbps·k=2 조건. 이번 X6은 c2s 2%→15%→2%, 공통 gen33 서버의 개발 측정이다. |
| S_rtt200 | cert 9000 B·RTT 200 ms·uplink 2 Mbps·k=2 조건. 이번 X6의 주 손실 일정은 S_bigcert와 같다. |
| H_c6000 | cert 6000 B·RTT 120 ms·uplink 10 Mbps·k=2, 손실 1%→8%→1%. 이번 계획에서는 F31의 선택 조건이며 필수 X6 결과에 포함된 것으로 세지 않는다. |
| D_p11_2955_l0·D_p11_2955_l2·D_p11_2955_l5 | 옛 p11 계열 cert 2955 B 조건의 손실 0·2·5% 셀 이름. 이번 필수 X6에는 l0만 있다. |
| D_p15_4032_l0·D_p15_4032_l2·D_p15_4032_l5 | 옛 p15 계열 cert 4032 B 조건의 손실 0·2·5% 셀. 이번 l0는 F31의 선택 조건이다. |
| D_p17_mbps2·D_p17_unlimited | p17 계열의 uplink 2 Mbps·제한 없음 조건 이름. 이 D 접두어는 결정 번호가 아니다. [봉인 조건표](../../pq_afec_gen31/g3/PROTOCOL_stage3.md)는 로컬 보존이다. |
| none | 관측 모드의 회신 없음과 목적지의 기본 정책 경로를 문맥별로 구분한다. 현행 c1_seen=False는 v3.2-dev의 이진 우도 규칙을 따른다. 결정 동치의 비교 범위와 parity 상한 1452/1472 B의 차이는 [기존 회귀 검증 설명](보고서%20주장과%20정정%20목록.md#v32-dev와-같다는-시험의-범위)을 따른다. 옛 L1 문서의 none 3등급 설명은 당시 후보의 뜻이다. |
| c1 | 전달된 C1 관측 모드 또는 c1_seen=True인 정책 경로. 표지가 켜진 뒤 회신이 없거나 잘린 연결의 fallback도 c1 경로 안에서 처리한다. |
| ideal | 세계의 완전한 도착 기록을 쓰는 정보 상한 진단. 실제 client에서 회신 없이 얻을 수 있는 관측이라고 읽지 않는다. |
| v33none·v33c1 | 이번 개발 측정의 auto3 팔. 전자는 C1 이력이 없는 별도 cache, 후자는 양쪽 feedback을 사용한다. [플래그·대기 예외](T7%20비교%20조건.md)를 함께 읽는다. |
| M0·M1 | M0는 실행·수집을 확인하는 smoke, M1은 서버 변경·클라이언트 세대 대조와 같은 설정 A/A·과거 환경 표류를 구분하는 개발 측정이다. M1 후보 과제와 별개다. [계획](../g3/v33/plans/final_bundle_v1.json), [M1 결과](M1_result.md) |
| X1·X6·X9 | 이번 루프에서는 각각 같은 바이트의 padding 대 parity, 세대·C1 경로, PTO 관측 정의 비교를 실행하는 개발 측정이다. 원래 X 과제 명세와 이번 최소 계획의 범위는 구분한다. |
| H1·H2·H3·H4 | 봉인 판정의 가설 이름. 각각 두 S 조건 개선, 조건별 비열등, 모형이 예측한 개선과 관측 개선의 대응, 고정 팔 대비 적응 기여를 평가한다. 결과와 판정 불능의 범위는 [봉인 결과 해석](보고서%20주장과%20정정%20목록.md)을 따른다. |

봉인 프로토콜의 D1~D6은 루프 결정과 다른 번호다. D1은 하네스 대조 팔·A/A 사이클, D2는 하네스 판정 규칙, D3은 H1 문턱, D4는 H2 보고 범주, D5는 H 예측 정의, D6은 S 1회차 서버 부하에 대한 편차다. [2단계 프로토콜의 14.1절](../../pq_afec_gen3/g3/PROTOCOL_stage2.md)은 로컬 보존이며 아래 결정 표의 D1~D6으로 대체하지 않는다.

none·c1·ideal 정의의 근거는 [L1 관측 계약](L1%20first%20flight%20관측%20계약.md)과 [활성 정책의 상태 전이](v3.3.1%20활성%20정책%20수정.md)다. 용어를 풀이하는 이 표는 후보 재진입이나 미실행 측정의 실행 지시가 아니다.
## 3. 과제 ID

옛 과제의 상태는 보존 LOOP_STATE의 기록이다. `done`은 그 카드의 구현·검증 완료를 뜻하며 후보 채택이나 현재 활성화를 뜻하지 않는다. `blocked`는 당시 장부의 막힘 표지이고 원인·미채택 판단은 후보 기록에서 읽는다. `todo`는 당시 미실행, `skipped`는 당시 건너뜀이다. 현재 정책의 채택 범위는 [활성 정책](v3.3.1%20활성%20정책%20수정.md)과 [후보 기록](미채택%20후보%20평가%20기록.md), 최종 루프의 종료 범위는 [닫은 과제](닫은%20과제%20목록.md)를 따른다.

| 접두어 | 과제 범위 |
|---|---|
| S | 준비와 안전 |
| A | 오프라인 재분석 |
| W | 독립 세계 모형과 회귀 벤치 |
| L | 학습층 |
| J | 비용 모형 |
| M | 기제 후보 |
| O | 목적함수와 입력 |
| G | Go 거울과 관문 |
| T | 테스트베드 기능 |
| X | 개발 측정 |
| E | 기존 과제의 후속 범위와 재검토 |
| R | 문서와 보고 |
| F | 최종 마무리 카드 |

### 3.1 옛 과제

정의는 TASKS와 EXTRA_TASKS에서 읽는다. 아래 상태는 보존 당시 값이며 이번 F 카드 상태와 구분한다. 같은 표기의 M1은 이 표에서는 hold 후보, 측정 표와 F27에서는 서버 등가·A/A 개발 측정이다. C1은 과제 접두어가 아니라 서버 회신 표기다.

| ID | 뜻 | 옛 LOOP_STATE 상태 | 정의 출처 |
|---|---|---|---|
| A0 | 근거 재현 묶음 | done | TASKS |
| A1 | 보고서 주장 목록 | done | TASKS |
| E1 | 봉인 판정의 독립 재계산 | todo | EXTRA_TASKS |
| E2 | W1 기준 행동 계산과 결과 검사 | done | EXTRA_TASKS |
| E3 | W1 정책 행동의 독립 기대값 계산 | done | EXTRA_TASKS |
| E4 | W1 기준값 표와 감사 대조 확정 | done | EXTRA_TASKS |
| E5 | L1 고정 정밀화 계산 완료 | done | EXTRA_TASKS |
| E6 | L1 정밀화 보고와 채택 판정 | done | EXTRA_TASKS |
| E7 | L2 EPS 적응의 식별과 채택 재검토 | todo | EXTRA_TASKS |
| E8 | 비용 모형 보정 뒤 감시와 변화 감지 재검토 | todo | EXTRA_TASKS |
| E9 | 둘째 비행 꼬리 후보의 관측 모형과 채택 재검토 | todo | EXTRA_TASKS |
| E10 | 서로 다른 행동의 수치상 영분산과 J6 채택 재검토 | done | EXTRA_TASKS |
| E11 | 완료 서버 응답의 관측 입력·수신 한도와 L5 채택 재검토 | todo | EXTRA_TASKS |
| E12 | 활성 L1의 Go 거울 선행 단계 | done | EXTRA_TASKS |
| E13 | J7 와이어 정정의 효과 분리와 채택 재검토 | todo | EXTRA_TASKS |
| E14 | M1 세계의 수신 credit과 송신 재개 분리 | todo | EXTRA_TASKS |
| E15 | M1 실제 ACK·PTO·CID 재전송 경로 대조 | todo | EXTRA_TASKS |
| E16 | M1 정책 채택 재검토와 Go 비용 거울 | todo | EXTRA_TASKS |
| E17 | T5 목적지 k 추정과 flush 입력 | done | EXTRA_TASKS |
| E18 | T5 실제 flush 대기와 비행 분할 관측 | done | EXTRA_TASKS |
| E19 | 연결 전체 parity 묶음 상한 | todo | EXTRA_TASKS |
| E20 | 중복 행동군과 서버 복호 지원 입력 | todo | EXTRA_TASKS |
| E21 | 토큰·TLS 재개에 맞춘 정책 분기 | skipped | EXTRA_TASKS |
| E22 | 미확인 업링크의 관측·와이어 정합과 채택 재검토 | todo | EXTRA_TASKS |
| E23 | GE 공동 학습과 후속 비용의 채택 재검토 | todo | EXTRA_TASKS |
| E24 | 시간 기반 버스트 손실의 개발 측정 | todo | EXTRA_TASKS |
| E25 | RTT 표본 귀속과 실제 송신 관측 (T4 후속) | todo | EXTRA_TASKS |
| E26 | RTT 정책과 HCT 불확실성 재검토 | todo | EXTRA_TASKS |
| E27 | 후보별 natural_k와 현재 k 정책의 채택 평가 | todo | EXTRA_TASKS |
| E28 | 송신 전 ClientHello 입력과 first flight expectK 연결 | todo | EXTRA_TASKS |
| E29 | J3 실패 경로의 CRYPTO·ACK·타이머 관측 | todo | EXTRA_TASKS |
| E30 | J3 실패 비용과 재시도 세계의 채택 검증 | todo | EXTRA_TASKS |
| E31 | M4 실제 재방문 입력·캐시·토큰 거절 어댑터 | todo | EXTRA_TASKS |
| E32 | M4 토큰·Retry·지원 상태의 HCT 비용과 채택 | todo | EXTRA_TASKS |
| E33 | 서버 프로필의 실제 관측 입력 | todo | EXTRA_TASKS |
| E34 | 하향 손실의 타이머·재전송 독립 세계 | todo | EXTRA_TASKS |
| E35 | 서버 프로필·하향 손실 비용의 정책 채택 | todo | EXTRA_TASKS |
| E36 | 과거 판정의 읽기 전용 재계산 | todo | EXTRA_TASKS |
| E37 | 공개용 사본과 남은 저장소 위생 | todo | EXTRA_TASKS |
| E38 | J7 남은 와이어 계약: parity 크기 고정과 파싱 실패 계수; F12에서 진단 계수·크기 검사 범위 완료 | todo | EXTRA_TASKS |
| E39 | none B8 seed 46 쌍안정 진단 | todo | EXTRA_TASKS |
| E40 | done 과제가 확인하지 않은 넘김 항목과 남은 교착 항목 보충 | todo | EXTRA_TASKS |
| E41 | J6 margin30을 활성 정책의 `c1_seen` 참 경로에 넣을지 판정 | todo | EXTRA_TASKS |
| G1 | 채택된 활성 정책의 Go 거울과 정책 관문 | done | TASKS |
| G2 | 와이어 관문; F13에서 조정된 구현 검증 완료 | todo | TASKS |
| J1 | 2-RTT 둘째 왕복 꼬리 | blocked | TASKS |
| J2 | 처리 상수 | todo | TASKS |
| J3 | 실패 가지와 재전송 비행 | blocked | TASKS |
| J4 | RTT ≥ 200 탐침 체제 | todo | TASKS |
| J5 | Gilbert-Elliott 버스트 | blocked | TASKS |
| J6 | δ 후보에 A_pre와 여유 | blocked | TASKS |
| J7 | parity 크기 고정과 상한 | blocked | TASKS |
| J8 | 서버 프로필 매개변수 | blocked | TASKS |
| L1 | datagram 단위 손실 증거 | done | TASKS |
| L2 | 3등급 라벨과 기준선 | done | TASKS |
| L3 | 건너뛰기·재평가·감시층 정리 | blocked | TASKS |
| L4 | 재주입 사전과 hazard | todo | TASKS |
| L5 | S 추정과 n_need | blocked | TASKS |
| L6 | 첫 방문과 상태 키 | todo | TASKS |
| M1 | 선행 parity 보류 복호 | blocked | TASKS |
| M2 | 송신 순서 옵션 | todo | TASKS |
| M3 | lead와 T 상한 분리 | todo | TASKS |
| M4 | Retry·토큰 인식 | blocked | TASKS |
| O1 | 바이트 예산 | todo | TASKS |
| O2 | 업링크 u | blocked | TASKS |
| O3 | RTT 신호 | blocked | TASKS |
| O4 | k를 로컬에서 계산 | blocked | TASKS |
| R1 | 아침 보고서 | todo | TASKS |
| R2 | v3.3 확증 프로토콜 초안; D67에 따라 확증 측정 안 함 | todo | TASKS |
| R3 | 알고리즘 지도 문서 | todo | TASKS |
| S0 | 기준선과 gen33 git 저장소 | done | TASKS |
| S1 | 원자료와 봉인 바이너리 보존 | done | TASKS |
| S2 | R-E 위생 | done | TASKS |
| S3 | gen33의 세대 경로 정리 | done | TASKS |
| S4 | 10-07 gen-2 수정 이식 | done | TASKS |
| S5 | 시험 위생과 CI 초안 | done | TASKS |
| T1 | 결정적 인증서 | done | TASKS |
| T2 | 토큰·resumption 팔 | done | TASKS |
| T3 | 같은 바이트 비교 팔 | done | TASKS |
| T4 | 관측 장치 | done | TASKS |
| T5 | 복호기·클라이언트 견고성 | done | TASKS |
| T6 | 재전송 비행 모양 | done | TASKS |
| T7 | v3.3 개발 측정 러너; F22~F26의 러너·smoke와 연결 | todo | TASKS |
| W0 | 세계 모형 분리 | done | TASKS |
| W1 | 회귀 벤치와 문턱 | done | TASKS |
| X1 | 같은 바이트 padding 대 parity; F28 완료 | todo | TASKS |
| X2 | 업링크 오입력; F31 선택 측정 | todo | TASKS |
| X3 | A_pre 탐침; F31 선택 측정 | todo | TASKS |
| X4 | 토큰·resumption 기준선; F31 선택 측정 | todo | TASKS |
| X5 | s2c 손실 | todo | TASKS |
| X6 | v3.3 대 v3.1 대 gen-2; F30 측정 중 | todo | TASKS |
| X7 | RFC 정확 스택 | todo | TASKS |
| X8 | 서버 설정 변형: IW10, InitialPacketSize | todo | TASKS |
| X9 | PTO 비율 재측정: 방향 전환 근거; F29 완료 | todo | TASKS |

### 3.2 이번 F 카드

다음은 반복 36 작업 중의 [상태 사본](../g3/v33/evidence/final/F46_loop_state_iter036.json)이다. 제목은 계획한 작업 범위이고 완료 증거는 상태·커밋과 따로 읽는다. `doing`은 진행 중, `todo`는 미실행이다. F46의 `doing`도 이 사본의 시점 값이다. 이후 진행은 이 사본에 소급하지 않는다.

| ID | 작업 범위 | 기록 당시 상태 | 원천·흡수 ID |
|---|---|---|---|
| F01 | R-E final worktree를 만들고 hygiene을 합치고 세대 태그를 단다 | done | RP-01, RP-06, BL-01, DC-19 |
| F02 | 보고서 그림, 표, 수치 재현 묶음을 gen33에 넣는다 | done | RT-06 |
| F03 | 보고서 정오표, 검사기, 수치 대조표를 만든다 | done | RT-09 |
| F04 | 정오표 행을 채운다(1판) | done | RT-28, RT-14, RT-15, RT-16, RT-17, RT-18, RT-19, RT-20, RT-13, RT-29, RT-25, RT-26, RT-30, BL-09 |
| F05 | 봉인 판정을 보존 저널에서 읽기 전용으로 재계산한다 | done | RT-05, BL-12 |
| F06 | 측정 상태에 따라 낡는 보고서 진술 15줄의 문구를 준비한다 | done | RT-04 |
| F40 | 문서 점검 도구와 고정 문서 표를 만든다 | done | DC-13, DC-18 |
| F10 | 관문 도구의 작은 결함과 gen32 이름을 정리한다 | done | CP-14, CP-15, CP-17 |
| F11 | auto3의 uplink 입력을 명시로 강제하고 행에 남긴다 | done | CP-02 |
| F12 | wire 최악 크기를 계수와 시험과 문서 표로 드러낸다 | done | CP-05, CP-06, BL-21 |
| F13 | G2를 시험 하나로 끝낸다 | done | CP-12, MS-26, BL-06 |
| F14 | 클라이언트 행에 client_scid를 넣는다 | done | MS-29 |
| F15 | 활성 정책의 틀린 수치, 죽은 함수, 이름 없는 숫자를 지우고 참조를 다시 만든다 | done | BL-13, CP-16 |
| F16 | 최종 소스로 빌드, 설치, 동결하고 한 명령 확인 도구를 만든다 | done | CP-01, MS-05, RP-08, BL-14 |
| F17 | T7 조건 문서를 지금 코드와 맞춘다 | done | CP-11, MS-07 |
| F20 | 측정 계획 파일을 gen33 안에 쓰고 커밋한다 | done | MS-14, MS-02, MS-28, MS-24 |
| F21 | netem, netns 경로를 울타리 밖에 새로 만든다 | done | MS-04 |
| F22 | 측정 러너 devbed.py 본체를 만든다 | done | MS-03, MS-27, MS-30, BL-07 |
| F23 | 서버 연결별 기록, C1 회신 확인을 러너에 넣는다 | done | MS-09, MS-11, MS-06 |
| F24 | 결과 요약, 서버 계수 비용, sha 기록, 결과 문서 생성기를 만든다 | done | MS-13, MS-10, MS-32 |
| F25 | WSL 수명을 붙잡는 launcher를 만든다 | done | MS-15 |
| F26 | 측정 M0: smoke와 기대 범위 | done | MS-17, MS-08 |
| F27 | 측정 M1: 서버 등가와 A/A | done | MS-18, MS-33 |
| F28 | 측정 X1 최소판: 같은 바이트 padding 대 parity | done | MS-19, BL-08 |
| F29 | 측정 X9 최소판: PTO 비율 재측정 | done | MS-20, BL-17 |
| F30 | 측정 X6 최소판: v3.3.1-dev 대 v3.1 대 gen-2 | doing | MS-21, BL-16 |
| F32 | 측정 결과를 문서와 정오표에 반영한다 | todo | MS-22, DC-25, RT-03 |
| F33 | 측정 없이 끝내는 경우의 문장을 넣는다 | skipped | MS-23 |
| F31 | 시간이 남을 때 더 재는 셀 | todo | RT-23, MS-31, BL-19, BL-18, BL-20 |
| F07 | 저장소 문서와 보고서의 수치 대조표, 원자료 위치표를 만든다 | done | RT-07, RT-22 |
| F41 | 정본이 인용할 증거와 루프 기록을 저장소로 복사한다 | done | DC-12, DC-17 |
| F42 | 후보 14개의 부정 결과 문서를 쓴다 | done | BL-03 |
| F43 | 후보 코드 흔적 색인과 활성 경로 분리 시험을 만든다 | todo | BL-04 |
| F44 | 고치지 않고 끝내는 한계를 한 문서로 모으고 W 1406 문장을 바로잡는다 | done | BL-05, CP-03, CP-04, CP-08, CP-09, CP-10, CP-22, MS-12 |
| F45 | 최종 코드에 필요 없는 과제를 근거와 함께 닫는다 | done | CP-13 |
| F46 | 용어와 ID 풀이(`용어와 ID.md`)를 쓴다 | doing | DC-06 |
| F47 | 알고리즘 명세(`PAD-FEC v3.3.1 명세.md`)를 쓴다 | todo | DC-02 |
| F48 | 세대별 결과 RESULTS_by_generation을 쓴다 | todo | DC-03 |
| F49 | 주장 범위 CLAIMS를 분리하고 금지 행을 더한다 | todo | DC-04 |
| F50 | 동결 문서 정정표를 쓴다 | todo | DC-07, BL-02 |
| F51 | 재현 절차(`재현 절차.md`)를 쓴다 | todo | DC-05, BL-10 |
| F52 | 코드 지도와 알고리즘 지도를 쓴다 | todo | CP-18, BL-15 |
| F64 | gen33 내보내기 도구와 규칙을 만든다 | todo | RP-04, RP-14 |
| F53 | 내보내기 절차 문서를 다시 쓰고 scrub 결함을 고친다 | todo | RP-11, DC-11, BL-11, BL-22 |
| F54 | 살아 있는 문서의 경로, 번역어, 대표어, 숫자 붙여쓰기를 고친다 | todo | DC-14, DC-15, DC-16, DC-20, DC-27 |
| F08 | 선행 조사 검색 기록을 남긴다 | todo | RT-21 |
| F09 | 참고문헌 내용 대조 기록을 남긴다 | todo | RT-27 |
| F55 | docs 색인과 gen33 README를 최종 상태로 쓴다 | todo | DC-01, DC-09, RP-12 |
| F60 | 봉인 대조를 4개 봉인으로 넓힌다 | todo | RP-02 |
| F61 | 팀 측정 폴더 문서의 표현을 바로잡는다 | todo | DC-10, DC-26, RP-18 |
| F62 | R-E 첫 화면 README와 GENERATIONS, DATA_AVAILABILITY를 쓴다 | todo | RP-03, DC-08, RP-10, RP-15, RP-16, RP-20, RP-21, RP-26, RP-22 |
| F63 | R-E용 pre-commit 훅을 넣는다 | todo | RP-13 |
| F65 | gen33을 마감한다: 장부 정리와 최종 수 재기 | todo | BL-23 |
| F66 | 최종본을 R-E final 브랜치에 올리고 배포 검사를 통과시킨다 | todo | RP-05, DC-28 |
| F67 | gen33 원자료와 루프 근거를 보존 폴더에 추가한다 | todo | RP-07 |

### 3.3 최종 감사 원천

CP는 코드, MS는 측정, RT는 보고서, DC는 문서, RP는 배포 저장소, BL은 미결 항목 정리의 원천 ID다. 아래 제목은 감사 당시의 문제·제안 이름이며 현재도 미수정이라는 뜻으로 읽지 않는다. F 카드의 범위 조정과 상태를 함께 본다. 한 원천을 여러 카드가 나누어 처리할 수 있다.

| ID | 감사 당시 항목의 뜻 | 받는 카드와 기록 당시 상태 | 원문 |
|---|---|---|---|
| BL-01 | R-E main에 hygiene 브랜치를 합쳐 clone 봉인 해시와 README 판정을 바로잡는다 | F01:done | backlog.json |
| BL-02 | A1 정정표의 실제 정정 18행과 상태 주석 14행을 문서와 정오표에 반영한다 | F50:todo | backlog.json |
| BL-03 | 후보 14개의 부정 결과를 한 문서에 후보당 한 문단으로 남긴다 | F42:done | backlog.json |
| BL-04 | 후보 코드 흔적의 색인을 만들고 활성 경로와 분리됐음을 시험으로 고정한다 | F43:todo | backlog.json |
| BL-05 | 고치지 않고 끝내는 결함을 활성 정책의 알려진 한계 문서로 남긴다 | F44:done | backlog.json |
| BL-06 | G2 와이어 관문: layout.outcomes의 도착 패턴을 decodeConn에 넣어 Python과 대조한다 | F13:done | backlog.json |
| BL-07 | T7 개발 측정 러너 experiments/v33/devbed.py를 만든다 | F22:done | backlog.json |
| BL-08 | X1: 같은 바이트·같은 자리에서 padding과 parity를 직접 잰다 | F28:done | backlog.json |
| BL-09 | 러너와 측정 결과에 맞춰 보고서 문장과 주장 문서를 동기화한다 | F04: 1판 후보 문장, F32: 2판 skip(내부 용어 L1·L3·record_only, 분량). 주장 문서 동기화는 REPORT_CLAIMS X1·X6 절 | backlog.json |
| BL-10 | 읽는 순서, ID 용어집, 검증된 재현 명령을 담은 입구 문서를 만든다 | F51:todo | backlog.json |
| BL-11 | 최종 gen33을 R-E에 다시 내보내고 scrub --root 결함을 고친다 | F53:todo | backlog.json |
| BL-12 | 봉인 H1~H4 판정을 보존 저널에서 읽기 전용으로 재계산하는 스크립트를 만든다 | F05:done | backlog.json |
| BL-13 | gen33 padfec/policy.py에 남은 틀린 수치를 지운다 | F15:done | backlog.json |
| BL-14 | 최종 코드로 참조를 다시 만들고 바이너리를 설치해 관문 기본 실행을 통과시킨다 | F16:done | backlog.json |
| BL-15 | R3 알고리즘 지도: 수량마다 Python, Go, 시험 위치를 잇는다 | F52:todo | backlog.json |
| BL-16 | X6: v3.3.1-dev와 v3.1, gen-2를 같은 블록에서 잰다 | F30:doing | backlog.json |
| BL-17 | X9: 방향 전환 근거인 PTO 비율을 고친 수집기로 다시 잰다 | F29:done | backlog.json |
| BL-18 | X3: A_pre, PTO 배수, 뒤 parity credit을 짧게 잰다 | F31:todo | backlog.json |
| BL-19 | X2: 정책에 틀린 업링크를 줄 때 이득이 남는지 잰다 | F31:todo | backlog.json |
| BL-20 | X4: 토큰과 resumption 기준선을 잰다 | F31:todo | backlog.json |
| BL-21 | E38 축소판: fec_parse_fail 계수와 W 경계 시험을 넣고 parity 크기는 고정하지 않는다 | F12:done | backlog.json |
| BL-22 | CI를 실제로 돌 자리로 옮기고 E37 잔여 위생을 끝낸다 | F53:todo | backlog.json |
| BL-23 | v33 루프 장부를 마감하고 분류표를 저장소에 남긴다 | F65:todo | backlog.json |
| BL-24 | 볼트의 낡은 문장 5행을 Claude가 고친다 (로컬 보존) | source/absorbed 등록 없음, 카드 조정·결정 참조 | backlog.json |
| BL-45 | gen-2 쪽 묵은 측정 미결을 한계로 닫는다 | source/absorbed 등록 없음, 카드 조정·결정 참조 | backlog.json |
| CP-01 | 설치본 qamp가 옛 정책이라 기본 관문이 실패한다. 코드 과제가 끝난 뒤 교체하고 한 명령으로 전체를 확인한다 | F16:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-02 | auto3의 uplink 입력이 묵시적으로 10 Mbps이고 행에 기록되지 않는다 | F11:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-03 | 정책 한계를 수치와 함께 한 문서로 모은다 | F44:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-04 | none 경로의 무손실 보호 행동 고착은 코드를 고치지 않고 한계로 밝힌다 | F44:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-05 | wire 최악 크기(W+46+6k)가 문서와 계수에 없다. fec_parse_fail, 크기 시험, 두 상한 표로 끝내고 정책 필터는 바꾸지 않는다 | F12:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-06 | W가 상한 위면 auto3이 조용히 parity 없는 정책이 된다. 경고와 행 표지를 넣는다 | F12:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-08 | 관측 S로 잰 n_need가 한 칸 높은 구간은 고치지 않고 한계로 적는다 | F44:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-09 | gen-2 decide_v2의 1457 B 후보는 동결 기준이라 그대로 두고 비교 조건만 적는다 | F44:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-10 | 명시 행동 경로의 상한 미적용은 실제 도달 경로가 없으니 코드를 고치지 않고 열린 질문을 닫는다 | F44:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-11 | Go 기본값과 비용 모형이 가정한 조건의 차이를 표로 밝히고 기본값은 바꾸지 않는다 | F17:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-12 | G2를 시험 하나로 끝낸다: layout.outcomes의 credit과 decoder가 스택에 넘긴 바이트 대조 | F13:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-13 | L4, J2, E14(E15·E16 포함), E39, E41 카드는 최종 코드에 필요 없으니 근거를 남기고 닫는다 | F45:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-14 | gate_v3_parity가 --out 폴더나 경로 없는 파일 이름을 받으면 2분 반을 돈 뒤 죽고, 문서도 폴더로 적혀 있다 | F10:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-15 | gen-2 관문 gate_go_parity.py가 gen33에서 --help에도 traceback으로 죽는다 | F10:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-16 | 활성 정책의 죽은 함수와 이름 없는 숫자를 참조 재생성 때 같이 정리한다 | F15:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-17 | gen32 이름이 남은 시험 파일과 메시지를 gen33으로 바꾼다. L1 이름은 그대로 둔다 | F10:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-18 | 활성 경로와 미채택 후보 보존물을 가르는 코드 지도가 없다 | F52:todo | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| CP-22 | c1_seen이 회신 한 번으로 영구히 켜진다는 점이 위협 문서에 없다 | F44:done | [code.final.json](loop_record/final_audit_2026-11-06/code.final.json) |
| DC-01 | docs/README.md 색인을 새로 쓴다 | F55:todo | docs.json |
| DC-02 | 알고리즘 명세 docs/PAD-FEC v3.3.1 명세.md를 새로 쓴다 | F47:todo | docs.json |
| DC-03 | 세대별 결과 정리 docs/RESULTS_by_generation.md를 새로 쓴다 | F48:todo | docs.json |
| DC-04 | 주장 범위 docs/CLAIMS.md를 REPORT_CLAIMS에서 분리하고 금지 행 4개를 더한다 | F49:todo | docs.json |
| DC-05 | 재현 절차 docs/재현 절차.md를 새로 쓰고 다시 잰 수를 넣는다 | F51:todo | docs.json |
| DC-06 | 용어와 ID 풀이 docs/용어와 ID.md를 새로 쓴다 | F46:doing | docs.json |
| DC-07 | 동결 문서 정정표 docs/동결 세대 문서 정정표.md를 쓴다 | F50:todo | docs.json |
| DC-08 | R-E/README.md의 낡은 판정, 단서 없는 수치, 오해를 부르는 명령을 고친다 | F62:todo | docs.json |
| DC-09 | gen33 README.md를 최종 상태로 다시 쓴다 | F55:todo | docs.json |
| DC-10 | mlkem CHANGELOG의 측정 판정과 발견을 주장하는 표현을 바로잡는다 | F61:todo | docs.json |
| DC-11 | PUBLISH_PROCEDURE.md를 실제 내보내기와 R-E 동기화 절차로 고친다 | F53:todo | docs.json |
| DC-12 | 정본이 인용할 저장소 밖 증거를 g3/v33/evidence/final로 복사한다 | F41:done | docs.json |
| DC-13 | 문서 점검 도구 tools/check_docs.py와 tests/test_docs_final.py를 만든다 | F40:done | docs.json |
| DC-14 | 살아 있는 조각 문서에서 저장소 밖 경로와 풀이 없는 호칭을 없앤다 | F54:todo | docs.json |
| DC-15 | 살아 있는 문서의 번역어를 영어 원어로 바꾼다 | F54:todo | docs.json |
| DC-16 | 한 개념을 여러 말로 부르는 곳을 대표어로 맞춘다 | F54:todo | docs.json |
| DC-17 | 루프 결정·과제·감사 기록을 저장소에 사본으로 둔다 | F41:done | docs.json |
| DC-18 | 옮기거나 고치면 깨지는 문서를 표로 고정하고 일괄 수정에서 뺀다 | F40:done | docs.json |
| DC-19 | R-E main에 봉인 대조 도구와 줄바꿈 규칙을 옮기고 README에 안내한다 | F01:done | docs.json |
| DC-20 | 어디에도 없는 인용을 색인에 '저장소 밖' 또는 '보존 안 됨'으로 표시한다 | F54:todo | docs.json |
| DC-25 | 측정이 돌면 문서의 '미측정' 문장을 같은 커밋에서 고친다 | F32:todo | docs.json |
| DC-26 | mlkem UPLOAD_GUIDE.md를 기록으로 표시한다 | F61:todo | docs.json |
| DC-27 | 살아 있는 문서의 숫자 붙여쓰기를 고친다 | F54:todo | docs.json |
| DC-28 | 최종 커밋을 R-E로 동기화하고 README 커밋·시험 수를 맞춘다 | F66:todo | docs.json |
| MS-02 | D50 확정: T7·X의 Initial 크기 W를 1280 B로 고정 | F20:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-03 | T7 측정 러너 experiments/v33/devbed.py 작성 | F22:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-04 | netem·netns 경로가 gen33에서 전부 차단되어 있고 g3bed는 gen33 바이너리와 안 맞는다 | F21:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-05 | 설치된 gen33 qamp가 v33fix 이전 판이다. 설치, 동결, 관문 재실행 | F16:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-06 | sealed31의 feedback-wait 200 ms 때문에 RTT200에서 1-RTT 연결의 C1 회신만 사라진다 | F23:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-07 | T7 문서의 v33auto 예시만 -expect-k가 빠져 비교 팔과 first flight 해제 방식이 다르다 | F17:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-08 | 동결 서버는 -cert-file이 없고 인증서가 흔들린다. 모든 팔을 같은 gen33 서버와 같은 인증서에 붙인다 | F26:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-09 | 서버 연결별 기록: Go에는 -conn-log가 있으나 읽는 Python이 없고 옛 reader는 조용히 빈 값을 낸다 | F23:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-10 | 클라이언트 parity 과소 계수는 동결 gen-2에 그대로다. 바이트 비용은 서버 계수만 쓴다 | F24:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-11 | C1 판본 3 회신을 옛 클라이언트가 서버 바이트로 세는 문제를 러너가 막는다 | F23:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-12 | '실측 문맥 W 1406'과 '실측 조건에서 PAD-FEC가 꺼진다'는 저널과 다르다 | F44:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-13 | 측정 뒤 요약 JSON, sha 기록, 결과 문서 자동 생성 경로가 없다 | F24:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-14 | '계획 파일 선커밋' 규칙의 위치가 git 밖이다 | F20:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-15 | WSL 수명: /tmp가 호출 사이에 사라지고 setsid 분리 실행은 검증되지 않았다 | F25:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-17 | 측정 M0: smoke와 기대 범위 고정 | F26:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-18 | 측정 M1: 서버 등가와 A/A(gen33 sealed31 대 동결 v3.1) | F27:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-19 | 측정 X1 최소판: 같은 바이트 padding 대 parity(신규성 방어) | F28:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-20 | 측정 X9 최소판: PTO 비율 재측정(방향 전환 근거) | F29:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-21 | 측정 X6 최소판: v3.3.1-dev(none, c1) 대 v3.1 대 gen-2 | F30:doing | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-22 | 측정을 돌린 경우 바꿔야 할 문서 문장 | F32:todo | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-23 | 측정 없이 끝내는 경우 문서에 적을 정확한 문장 | F33:skipped | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-24 | 측정 카드에 남은 낡은 내용을 새 과제 카드에서 뺀다 | F20:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-26 | G2 와이어 관문을 W 1280 크기 검사와 Python outcomes 대조로 줄여 끝낸다 | F13:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-27 | 러너 저널 지문이 환경변수와 experiments/*.py 전체에 묶이지 않게 한다 | F22:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-28 | C1 대기로 달라지는 연결 간격을 계획에 적고 잰다 | F20:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-29 | 클라이언트 행에 client_scid를 넣어 conn-log와 일대일로 잇는다 | F14:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-30 | genconfig.json gen_id가 아직 v3.3-dev다 | F22:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-31 | 시간이 남을 때 더할 셀: H c6000, D_p15_4032, 서버 first flight 7.7~9.0 kB 띠 | F31:todo | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-32 | 결과 문서에 고정할 단서: c2s 손실만, IW 32, 1 byte 절벽, uplink 오라클 | F24:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| MS-33 | 봉인 측정과 지금의 WSL 커널이 다르다. 결과에 환경을 남기고 동결 팔로 표류를 본다 | F27:done | [measure.final.json](loop_record/final_audit_2026-11-06/measure.final.json) |
| RP-01 | hygiene 브랜치가 main에 없어 Windows 기본 clone에서 봉인과 소스 지문이 깨진다 | F01:done | repo.json |
| RP-02 | verify_seals가 봉인 4개 중 3개만 보고 보고서의 71개와 숫자가 안 맞는다 | F60:todo | repo.json |
| RP-03 | README의 gen-2 판정 줄이 state와 다르고 유일한 예시 명령은 25단계 전부 무효를 보여준다 | F62:todo | repo.json |
| RP-04 | gen33을 R-E로 내보내는 포함 목록이 손작업이라 다음 export에서 시험이 또 깨진다 | F64:todo | repo.json |
| RP-05 | 최종 산출물을 R-E final 브랜치에 올리고 도현님 승인 뒤 한 번에 push하는 절차와 대조 스크립트를 만든다 | F66:todo | repo.json |
| RP-06 | 세대 태그가 로컬에만 있고 v3.0, v3.3.1, 최종 태그는 없으며 gen33에는 태그가 하나도 없다 | F01:done | repo.json |
| RP-07 | gen33 원자료와 루프 근거가 archive에 없고 git 원격도 없다 | F67:todo | repo.json |
| RP-08 | 최종 코드의 바이너리가 설치도 동결도 안 돼 있고 WSL 설치본은 옛 판이다 | F16:done | repo.json |
| RP-10 | 첫 화면에서 최종 세대와 결과를 찾을 수 없고 gen3·gen31 README는 gen-2 사본이다 | F62:todo | repo.json |
| RP-11 | PUBLISH_PROCEDURE가 11-02 시점에 멈춰 있고 scrub 도구는 내보낸 폴더에서 죽는다 | F53:todo | repo.json |
| RP-12 | gen33 README의 시험 수와 설치본 설명이 옛 값이고 명령이 로컬 전용 경로를 쓴다 | F55:todo | repo.json |
| RP-13 | R-E에는 pre-commit 훅이 없고 gen33 훅은 R-E 구조에서 커밋을 막아 버린다 | F63:todo | repo.json |
| RP-14 | CI 파일은 R-E 하위 폴더라 절대 안 돈다. 켜지 않고 배포본에서 뺀다 | F64:todo | repo.json |
| RP-15 | 보고서 수치와 원자료 위치를 잇는 표가 없다 | F62:todo | repo.json |
| RP-16 | pq_afec_next의 p21과 p3 교대판은 로컬 브랜치에만 있다. 합치지 않고 보존만 원격에 올린다 | F62:todo | repo.json |
| RP-18 | 팀 측정 README가 현재 정책 위치를 gen-2로 안내한다 | F61:todo | repo.json |
| RP-20 | 20 MB 초과 파일 4개는 그대로 두고 목록만 문서에 남긴다 | F62:todo | repo.json |
| RP-21 | gen-2 README의 자체시험 개수가 옛 값이다 | F62:todo | repo.json |
| RP-22 | 자동 push 스크립트 battery_guard.ps1이 배포본에 남아 있다 | F62:todo | repo.json |
| RP-26 | 로컬 동결 폴더와 배포 사본의 바이트 차이를 기록해 둔다 | F62:todo | repo.json |
| RT-01 | AI 활용 칸이 지금 없는 PaperBanana 그림을 적고 있다 | source/absorbed 등록 없음, 카드 조정·결정 참조 | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-03 | 첫 측정 결과 X9, X1, X6를 넣을 절과 문장 규칙을 정오표에 고정한다 | F32:todo | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-04 | 루프 결과에 따라 낡는 진술 15줄을 측정 상태별 문구로 준비한다 | F06:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-05 | v3 판정 재계산 '223항목, 4.4×10⁻¹² ms'의 산출물이 어디에도 없다 | F05:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-06 | 보고서 그림·표·수치 재현 묶음을 저장소에 넣는다 | F02:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-07 | 저장소 문서와 보고서가 다른 수치를 말하는 곳을 대조표 하나로 정리한다 | F07:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-08 | V4 3_RTT비례 RTT 50 행의 출처를 팀원에게 확인하고 Fig. 3 캡션을 고친다 | source/absorbed 등록 없음, 카드 조정·결정 참조 | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-09 | 보고서 정오표와 검사기를 만든다(hwp는 고치지 않는다) | F03:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-10 | 【입력 필요】 칸, 체크리스트 8행과 서명, 인적 사항, 팀원 번호를 도현님이 채운다 | source/absorbed 등록 없음, 카드 조정·결정 참조 | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-12 | 제출 기준본과 과제명을 하나로 정한다(팀 서명본과 내용이 다르다) | source/absorbed 등록 없음, 카드 조정·결정 참조 | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-13 | 반올림 1건: padding 반폭 3.97 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-14 | 요약의 '세대 비교 259,600연결'을 246,000연결과 구분한다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-15 | Table 5 p17의 '중앙값 194.5'는 5구간 중 3구간 미적응을 가린다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-16 | Table 5 p10 '11/12 완주'는 시험 통과 수다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-17 | Table 5 p8의 0.024 ms 분모를 밝히고 자료 날짜를 바로잡는다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-18 | Table 5 p16 'block 표류 0.39~0.75 ms'의 0.75를 찾지 못했다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-19 | Ⅳ-6 시뮬레이션 문장에 비교 대상, 비표준 서버 단서, B6 미확정을 넣는다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-20 | 한계 일곱째의 1,452 B 제한에 세대를 밝힌다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-21 | '2026년 11월 5일까지의 검색 범위'를 뒷받침할 검색 기록을 남긴다 | F08:todo | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-22 | 보고서가 쓰는 원자료 중 배포본에 없는 것의 위치를 적고 probe 결과를 올린다 | F07:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-23 | 초록의 RTT 비례 수치를 동결 gen-2로 노트북에서 재측정한다 | F31:todo | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-24 | quiche 대조 원자료를 팀원에게 받을지 정한다 | source/absorbed 등록 없음, 카드 조정·결정 참조 | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-25 | '판정불능에 필요 표본을 함께 적었다'를 실제와 맞춘다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-26 | Table 2 v3 봉인 '조건 23개'를 세대별로 적는다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-27 | 참고문헌 내용 대조 기록을 남긴다 | F09:todo | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-28 | 한계 셋째 '첫 접속만 다루었다'가 재방문 조건부 결과를 첫 접속 결과로 읽게 한다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-29 | 정책에 참 uplink를 입력한 사실이 한계 절에 없다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |
| RT-30 | 요약문의 큰 인증서 수치에 initial cwnd 단서를 붙인다 | F04:done | [report.final.json](loop_record/final_audit_2026-11-06/report.final.json) |

### 3.4 보고서 정오표 하위 ID

RT 번호 뒤에 붙은 번호는 [보고서 정오표](보고서%20정오표.md)의 개별 행이다. 같은 원천의 적용 위치와 선택 문구를 나눈 것이며 별도 과제 상태를 만들지 않는다. 상태·selected는 정오표에서 읽는다.

| ID | 적용 위치 | 출처 |
|---|---|---|
| RT-01-1 | 과정: 생성형 AI 활용 | [보고서 정오표](보고서%20정오표.md) |
| RT-01-2 | 과정: 생성형 AI 활용 | [보고서 정오표](보고서%20정오표.md) |
| RT-01-3 | 과정: 생성형 AI 활용 | [보고서 정오표](보고서%20정오표.md) |
| RT-03-1 | 결과물: Ⅳ-1 손실 비교 | [보고서 정오표](보고서%20정오표.md) |
| RT-03-2 | 결과물: Ⅳ-3 같은 바이트 비교 | [보고서 정오표](보고서%20정오표.md) |
| RT-03-3 | 결과물: Ⅳ-6 개발본 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-01 | 결과물: 초록 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-02 | 요약문: 연구 결과 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-03 | 요약문: 향후 계획 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-04 | 요약문: 향후 계획 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-05 | 요약문: 향후 계획 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-06 | 과정: 수행 중 문제 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-07 | 과정: 자체 평가 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-08 | 결과물: Ⅰ-1 연구 배경 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-09 | 결과물: Ⅱ-5 Table 1 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-10 | 결과물: Ⅳ-1 손실 비교 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-11 | 결과물: Ⅳ-6 제목 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-12 | 결과물: Ⅳ-6 개발본 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-13 | 결과물: Ⅴ-1 해석 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-14 | 결과물: Ⅴ-1 학습층 해석 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-15 | 결과물: Ⅴ-3 연구 의의 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-16 | 결과물: Ⅵ 결론 RQ1 | [보고서 정오표](보고서%20정오표.md) |
| RT-04-17 | 결과물: Ⅵ 후속 연구 | [보고서 정오표](보고서%20정오표.md) |
| RT-17-1 | 결과물: Ⅳ-4 Table 5 p8 | [보고서 정오표](보고서%20정오표.md) |
| RT-17-2 | 결과물: Ⅳ-4 Table 5 캡션 | [보고서 정오표](보고서%20정오표.md) |
| RT-21-1 | 요약문: 연구 필요성 | [보고서 정오표](보고서%20정오표.md) |
| RT-21-2 | 결과물: Ⅰ-3 연구 범위 | [보고서 정오표](보고서%20정오표.md) |
## 4. 감사와 옛 메모 ID

감사 ID는 발견 당시의 문제와 제안을 가리킨다. 아래 판정은 당시 검증·이관 기록이며 현재 결함 유무나 후보 채택 상태를 뜻하지 않는다. 현재 처리 상태는 이 문서의 과제 표, [정책 한계](활성%20정책의%20알려진%20한계.md), [후보 기록](미채택%20후보%20평가%20기록.md)에서 확인한다.

[감사 색인](loop_record/v33/findings/FINDINGS_INDEX.md)은 CONFIRMED(확인), PARTLY(부분 확인), REFUTED(반박됨), UNVERIFIABLE(검증 불가), 미검증을 구분한다. A1~A8의 PARTLY 항목은 검증문의 CORRECTED를, 11월 1일 감사는 각 파일의 VERIFY 정정을 우선한다. 제안의 sound·doubtful·harmful 판정은 문제의 사실 여부와 별개이며, 확인된 문제도 제안을 바로 구현하라는 뜻은 아니다. 원문 audit·verify 파일 중 저장소에 복사되지 않은 파일은 로컬 보존이다. 이 표는 확인된 사본과 색인에서 뜻을 찾는 안내이며 이번 반복의 감사 재실행 결과가 아니다.

| 표기 | 이름 공간과 읽는 법 | 근거 |
|---|---|---|
| A1-nn, A2-nn, A3-nn, A4-nn | 각각 비용 모형, 학습, Go·wire, gen-2 기반 감사의 번호 | [감사 색인](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-nn, A6-nn, A7-nn, A8-nn | 각각 측정 설계, 코드·재현 환경, 선행연구, quic-go 소스 감사의 번호 | [감사 색인](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-nn, A6r1-nn | 같은 갈래의 첫 실행 보조 기록. 두 번째 실행을 정본으로 읽음 | [감사 색인](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-Mnn 등 | 해당 감사 검증자가 보탠 missed 항목 | [감사 색인](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A-En, B-En, C-En, D-En | 11월 1일 감사의 무결성, 활성 정책, 세계·통계, 미채택 학습·비용 후보 갈래 | [기록 사본](loop_record/README.md) |
| E-M1-n, F1~F8, G-En, H-nn | 같은 감사의 보류 복호 후보, Go·testbed, 주장, 과제 coverage 갈래. F1~F8은 최종 루프 F01~F08과 다름 | [기록 사본](loop_record/README.md), [testbed 처리 기록](v3.3.1%20Go%20테스트베드%20수정.md) |
| B-Mn, C-Mn, D-Mn | 11월 1일 각 갈래 VERIFY의 missed 목록 순서. A1-Mnn 계열과 시점이 다름 | [B 감사](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md), [C 감사](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md), [D 감사](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| Q-nn | 옛 수정 대기·할 일·연구 노트를 EXTRA_SOURCES로 모은 번호 | 이관표 |
| A-n, C-n, SW:문자-n | gen-2 수정 대기 목록의 절 번호. SW는 그 문서를 출처로 붙인 표기이며 A1-nn 감사와 다름 | 이관표 |
| TD:번호, TD:결정-날짜-주제, TD:수리-날짜-주제 | gen-2 할 일 목록의 절·결정·수리거리 식별자 | 이관표 |
| VF-POL5-n, VF-EVA-n | V33FIX 정책 한계 5절·평가의 남은 일을 이관표에서 식별하는 이름 | 이관표 |

이관표의 FINAL-MUST·FINAL-SHOULD·DROP·USER는 최종 루프에 남길 필수·권장 항목, 범위에서 뺀 항목, 사람 결정 항목을 뜻한다. 현재 카드의 done·todo와는 다른 분류다.

| ID | 검토 주제 또는 정정 요지 | 당시 판정·분류 | 출처 |
|---|---|---|---|
| A-1 | gen-2 뒤따르는 parity 항의 미확정 | 이관 분류 FINAL-SHOULD | 원문 469행 |
| A-2 | gen-2 p18 검사 판정 방향 | 이관 분류 FINAL-MUST | 원문 470행 |
| A-3 | gen-2 p16 판정 자와 하네스 표류 | 이관 분류 DROP | 원문 471행 |
| A-4 | gen-2 허용집합 자와 오차 구간 | 이관 분류 DROP | 원문 472행 |
| A-5 | 옛 gen-2 폐루프의 수동 m | 이관 분류 FINAL-MUST | 원문 473행 |
| A-6 | 클라이언트 flight의 k 제어 범위 | 이관 분류 FINAL-MUST | 원문 474행 |
| A-8 | 서버에서 클라이언트로 가는 방향의 미보호 | 이관 분류 FINAL-MUST | 원문 476행 |
| A-9 | 원래 padding 자리에 parity를 넣는 용량 한계 | 이관 분류 DROP | 원문 477행 |
| A-E1 | CI Go 빌드의 runner 경로 의존성 | CONFIRMED | 원문 14행, 검증 110행 |
| A-E2 | 시험용 PEM의 git 이력 보존 | CONFIRMED | 원문 21행, 검증 112행 |
| A-E3 | 파생 자료·바이너리·사본으로 늘어난 저장소 | CONFIRMED | 원문 28행, 검증 114행 |
| A-E4 | manifest가 가리키는 미추적 로그 | CONFIRMED | 원문 35행, 검증 116행 |
| A-E5 | pytest의 저장소 안 산출물 | PARTLY | 원문 42행, 검증 118행 |
| A-E7 | race 기록·설치 바이너리 시점 차이와 stage 누적 | PARTLY | 원문 56행, 검증 122행 |
| A-E8 | Go 통과 수를 보고할 때 SKIP 누락 | CONFIRMED | 원문 63행, 검증 124행 |
| A1-01 | J3의 두 번째 왕복 손실 꼬리 누락. 꼬리 초과 지연과 처리 상수를 구분 | PARTLY | [원문 10행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-02 | 독립 손실 가정의 burst 실패 확률 오차 | CONFIRMED | [원문 11행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-03 | 참 uplink 입력에 의존하는 결정과 입력 오차 | CONFIRMED | [원문 12행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-04 | A_pre를 빼고 만든 최소 padding 후보 | CONFIRMED | [원문 13행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-05 | lead와 T를 묶는 m 상한의 영향 | CONFIRMED | [원문 14행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-06 | 원본을 먼저 보내는 송신 순서 후보 | CONFIRMED | [원문 15행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-07 | u=0에서 바이트 가격이 없는 목적함수 | CONFIRMED | [원문 16행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-08 | 실패당 비용 과소평가. 고정 팔의 빈도 일치와 혼합 팔의 겉보기 상쇄를 구분 | PARTLY | [원문 17행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-09 | RTT200의 초기 PTO 탐침과 모형 누락 | CONFIRMED | [원문 18행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-10 | RTT에 섞인 uplink 직렬화와 처리 지연 | CONFIRMED | [원문 19행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-12 | S·k 추정 오차와 행동 경계 | CONFIRMED | [원문 21행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-13 | quic-go overshoot와 서버 packet 크기에 묶인 예산 규칙 | CONFIRMED | [원문 22행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-15 | 하향 손실·서버 재전송의 모형 범위 | CONFIRMED | [원문 24행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-M01 | 측정한 uplink 조건에서 lead credit와 trailing 복구의 역할 분리 | 검증자 추가 항목 | [원문 173행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A1-M02 | lead parity 보류 복호 후보 | 검증자 추가 항목 | [원문 174행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-01 | 보호 행동에서 정보가 적은 이진 관측과 posterior 고착 | 미검증 | [원문 26행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-02 | 세계 폐루프의 고착과 관측·감시층 분해 | 미검증 | [원문 27행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-03 | 균등 격자 재주입 prior의 영향 | 미검증 | [원문 28행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-04 | 잔차 창 감시와 등급별 감시의 차이 | 미검증 | [원문 29행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-05 | 경보의 비용 가산·학습 차단 | 미검증 | [원문 30행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-07 | 고정 EPS와 거짓 사건·지터의 관계 | 미검증 | [원문 32행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-08 | 무손실 과보호의 정보와 바이트 비용 문제 | 미검증 | [원문 33행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-09 | 건너뛴 관측의 hazard 전이와 고손실 진동 | 미검증 | [원문 34행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-10 | 주기적 재평가와 정보 기반 탐색 | 미검증 | [원문 35행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-11 | 사건 연결 제외에 따른 S_hist 편향 | 미검증 | [원문 36행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-13 | 역사적 최소 RTT와 지터를 반영하지 않는 사건 문턱 | 미검증 | [원문 38행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-14 | 첫 방문 b0와 S·k 사전 정보 | 미검증 | [원문 39행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-15 | 손실 층 사이 최적 행동이 같은 적응 평가 일정 | 미검증 | [원문 40행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2-17 | 등급별 J3 과소예측 원인 | 미검증 | [원문 42행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-03 | 세계 고착을 감시·정보·prior로 분해한 보조 실행 | 미검증 | [원문 45행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-04 | 잔차 창 감시의 두 봉우리·실패 관측 문제 | 미검증 | [원문 46행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-05 | predict_step·감시층 변경의 세계 비교 | 미검증 | [원문 47행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-06 | 정보 없는 관측과 재주입이 만드는 무손실 고착 | 미검증 | [원문 48행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-07 | prior·hazard가 posterior 꼬리에 주는 영향 | 미검증 | [원문 49행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-08 | 주기적 재평가와 Thompson sampling 진단 | 미검증 | [원문 50행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-09 | 바이트 가격과 동률창 | 미검증 | [원문 51행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-10 | 사건 연결을 제외한 서버 바이트 추정 | 미검증 | [원문 52행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-11 | 하향 손실·RTT 변화와 c2s 손실의 혼동 | 미검증 | [원문 53행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-12 | cold 연결 비용과 다음 연결의 과보호 | 미검증 | [원문 54행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-13 | H4 적응 신호와 하네스 편향의 크기 비교 | 미검증 | [원문 55행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A2r1-15 | 고정 EPS와 저정보 관측 | 미검증 | [원문 57행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A3-01 | RTT200의 PTO 재전송·RTT 표본·추가 parity | 미검증 | [원문 58행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A3-06 | 재전송·후속 flight의 parity 비용 집계 | 미검증 | [원문 63행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A3-11 | 복호 전 연결 생성·서버 shim·Retry의 적용 범위 | 미검증 | [원문 68행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A3-13 | 최소 RTT에 섞이는 클라이언트 대기열 | 미검증 | [원문 70행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A3-14 | flight 경계 타이머와 expect-k 외부 입력 | 미검증 | [원문 71행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-01 | server_bytes를 넣은 n_need 추정 경계 | 미검증 | [원문 73행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-02 | CID 가변 길이와 수신 상한 밖 parity | 미검증 | [원문 74행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-03 | padding 경계 생성기의 A_pre 누락 | 미검증 | [원문 75행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-04 | quic-go 예산 회계에 맞춘 양자 모형 | 미검증 | [원문 76행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-05 | 실패 비용 상수의 측정 조건과 일반화 범위 | 미검증 | [원문 77행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-06 | 바이트 가격 부재와 동률창의 교환비 | 미검증 | [원문 78행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-07 | gen-2 추정기의 무손실 수렴 | 미검증 | [원문 79행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-08 | 실제 정책 결정에서 burst 모형 사용 여부 | 미검증 | [원문 80행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A4-11 | gen-2 수치와 코드·결과의 불일치 | 미검증 | [원문 83행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-03 | 설계 조건과 보류 조건의 독립성 | 미검증 | [원문 86행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-04 | H2 표본·비열등 한계·하네스 한계 | 미검증 | [원문 87행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-05 | H3 예측의 gen-2 참 손실·최적 행동 가정 | 미검증 | [원문 88행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-09 | netem 손실·대역 모형의 적용 범위 | 미검증 | [원문 92행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-11 | 짝 블록 설계와 gen-2 p3의 순차 팔 표류 | 미검증 | [원문 94행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-12 | 옛 보고 문구의 주장·단서 점검 | 미검증 | [원문 95행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-13 | 정확한 RFC 회계를 쓰는 다른 스택의 미측정 | 미검증 | [원문 96행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A5-16 | v3.2 개발판의 미측정과 A_pre 일반화 범위 | 미검증 | [원문 99행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A6-06 | 재현에 필요한 로컬 자료·바이너리. 실행 명령 자체는 봉인 프로토콜에 있음 | PARTLY | [원문 106행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A6-11 | README·명세와 실제 자료의 상태 차이 | CONFIRMED | [원문 111행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A6-M02 | RTT200에서 연결별 경로 RTT 관측 부재 | 검증자 추가 항목 | [원문 177행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A6-M03 | 팔별 서버 바이너리 차이의 교란 | 검증자 추가 항목 | [원문 178행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A6r1-11 | README·인계 문서 상태 차이의 보조 실행 | 미검증 | [원문 127행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-01 | NEW_TOKEN·session ticket을 끈 측정의 적용 범위 | CONFIRMED | [원문 134행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-02 | 첫 방문의 손실·k·S 사전 정보 분리 | CONFIRMED | [원문 135행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-03 | 목적지 캐시와 연결 간 식별 가능성 | CONFIRMED | [원문 136행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-07 | 같은 바이트의 중복 Initial 대조 팔 | CONFIRMED | [원문 140행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-09 | 서버별 amplification 회계 차이 | CONFIRMED | [원문 142행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-10 | 실패 비용의 클라이언트 PTO·서버 ACK 의존성 | CONFIRMED | [원문 143행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-12 | prior만 바꿔서는 고착이 풀리지 않는 정정. 관측 정보와 바이트 가격을 함께 봄 | PARTLY | [원문 145행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-13 | 자기 창 median 사건 기준선의 오염 | CONFIRMED | [원문 146행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-14 | 감시 문턱과 categorical CUSUM 제안 | CONFIRMED | [원문 147행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-15 | iid 손실 가정과 netem burst의 시간 상관 범위 | CONFIRMED | [원문 148행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-16 | 강제 재평가 대신 정보 기반 탐색 제안 | CONFIRMED | [원문 149행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-17 | lead 보류 복호 모형. 손실된 마지막 도착을 미리 아는 가정을 제거한 deadline 정정 | PARTLY | [원문 150행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-18 | 협상 전 first flight 보호 방식. 중복 Initial도 가능하다는 정정 | PARTLY | [원문 151행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-19 | 하향 손실과 서버 재전송 예산의 측정 범위 | CONFIRMED | [원문 152행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-20 | Retry 서버에서의 parity·credit 전략 | CONFIRMED | [원문 153행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-21 | 수신 datagram 계수의 규범 근거와 서버 routing 조건 | CONFIRMED | [원문 154행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-M01 | 참 손실을 알아도 남는 바이트 비용 부재 | 검증자 추가 항목 | [원문 182행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-M02 | 복호 전 연결을 만드는 서버 동작에 의존하는 lead credit | 검증자 추가 항목 | [원문 183행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A7-M03 | 고정 일정의 posterior 평균과 실제 손실 구별 여부 | 검증자 추가 항목 | [원문 184행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-02 | quic-go 처리 순서와 lead 보류 복호 가능성 | 미검증 | [원문 157행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-03 | quic-go 특유의 amplification 회계와 1-RTT 판정식 | 미검증 | [원문 158행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-06 | A_pre의 소스·측정 근거와 s_hat 중복 계상 | 미검증 | [원문 161행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-07 | 자기 uplink 직렬화가 포함된 정책 RTT | 미검증 | [원문 162행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-08 | 큰 인증서 조건 J3 과소예측의 원인 후보 | 미검증 | [원문 163행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-10 | RTT200의 ClientHello PTO 탐침 | 미검증 | [원문 165행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-11 | 서버 설정·CID·KEM에 묶인 P·k | 미검증 | [원문 166행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| A8-12 | Retry 경로의 시험 부재와 parity 낭비 가능성 | 미검증 | [원문 167행](loop_record/v33/findings/FINDINGS_INDEX.md) |
| B-E1 | 당시 none 경로의 v3.2 대비 세계 회귀 | CONFIRMED | [원문 20행, 검증 101행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-E2 | 후속 후보와 L1의 비대칭 관문. 규칙 우회 단정은 정정됨 | PARTLY | [원문 27행, 검증 103행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-E3 | 같은 seed의 MC 정밀화와 경계선 통과. 독립 확증으로 읽지 않음 | PARTLY | [원문 34행, 검증 105행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-E4 | C1 burst 조건의 추정 편향·비용 차이 | CONFIRMED | [원문 41행, 검증 107행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-E5 | 보충 관문 참조의 소스 지문 불일치 | CONFIRMED | [원문 48행, 검증 109행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-E6 | Go 시험 산출물 보존. 당시 삭제 금지 규칙의 영향 구분 | PARTLY | [원문 55행, 검증 111행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-E7 | 상태 판본과 cache schema 표지 불일치 | CONFIRMED | [원문 62행, 검증 113행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-M1 | none 보호 행동의 관측 정보 부족과 고착 | 검증자 추가 항목 | [원문 129행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| B-M3 | C1 비용을 넣지 않은 세계 관측 가정 | 검증자 추가 항목 | [원문 133행](loop_record/v33/findings/v33audit_2026-11-01/B-active-algorithm.md) |
| C-1 | 낡은 다음 세션 인계 문서 | 이관 분류 FINAL-MUST | 원문 486행 |
| C-3 | 두 보고서·파이프라인의 병존 | 이관 분류 FINAL-MUST | 원문 488행 |
| C-8 | 변경보고 원본 HTML 소스 부재 | 이관 분류 FINAL-MUST | 원문 493행 |
| C-9 | 보고서에 남길 한계 | 이관 분류 FINAL-MUST | 원문 494행 |
| C-E1 | 영분산 경계 규칙과 후보 판정 | PARTLY | [원문 14행, 검증 118행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E10 | 학습 벤치의 참 uplink 입력. 별도 O2 숨긴 uplink 진단은 있음 | PARTLY | [원문 77행, 검증 136행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E2 | L1 같은 seed MC 정밀화의 해석 | CONFIRMED | [원문 21행, 검증 120행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E3 | 세계와 정책이 공유하는 바이트 상수 | CONFIRMED | [원문 28행, 검증 122행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E4 | 세계 보정의 허용차와 작은 행동 차이의 해상도 | PARTLY | [원문 35행, 검증 124행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E5 | 세계·실측의 Initial 계수 정의와 둘째 왕복 손실 가지 | CONFIRMED | [원문 42행, 검증 126행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E6 | hold 세계의 parity 도착 뒤 서버 송신 재개 비대칭 | CONFIRMED | [원문 49행, 검증 128행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E7 | none 회귀·공동 절대 목표와 L1 완료 상태 | CONFIRMED | [원문 56행, 검증 130행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E8 | 셀 간 다중 비교와 영분산 처리의 비대칭 | CONFIRMED | [원문 63행, 검증 132행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-E9 | 표본 설계·검정력과 미확정 결과 해석 | PARTLY | [원문 70행, 검증 134행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| C-M1 | 고정 ACK 경계와 영분산 규칙이 후보 비교에 주는 영향 | 검증자 추가 항목 | [원문 154행](loop_record/v33/findings/v33audit_2026-11-01/C-world-and-stats.md) |
| D-E1 | J6 영분산 판정. 임의 시간 상한으로 채택을 단정할 수 없다는 정정 | PARTLY | [원문 14행, 검증 102행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| D-E2 | 소수 seed 차이에 의존하는 구간과 후보 해석 | PARTLY | [원문 21행, 검증 104행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| D-E3 | 당시 감시 벌점·재평가 활성 상태와 절대 목표 | CONFIRMED | [원문 28행, 검증 106행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| D-E4 | 상한 밖 parity 후보. 특정 악화 전체를 잘림 원인으로 단정하지 않음 | PARTLY | [원문 35행, 검증 108행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| D-E5 | L1과 후속 후보의 채택 기준 차이 | CONFIRMED | [원문 42행, 검증 110행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| D-E7 | 기능 완료와 성능 채택·blocked 상태의 구분 | PARTLY | [원문 56행, 검증 114행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| D-M4 | L1·L3 공동 절대 목표와 완료 상태의 차이 | 검증자 추가 항목 | [원문 142행](loop_record/v33/findings/v33audit_2026-11-01/D-rejected-learning.md) |
| E-M1 | 보류 복호 후보 감사의 E-M1-1~E-M1-5 묶음 | 묶음 이름 | [원문 32행](loop_record/v33/findings/v33audit_2026-11-01/E-rejected-mechanism.md) |
| E-M1-1 | hold 후보 비용 모형의 순수 lead 둘째 왕복 손실 누락 | CONFIRMED | [원문 32행, 검증 138행](loop_record/v33/findings/v33audit_2026-11-01/E-rejected-mechanism.md) |
| E-M1-2 | hold와 off의 lead=0 불변식 시험 누락 | CONFIRMED | [원문 39행, 검증 140행](loop_record/v33/findings/v33audit_2026-11-01/E-rejected-mechanism.md) |
| E-M1-3 | hold 수신기의 참 uplink 입력 | CONFIRMED | [원문 46행, 검증 142행](loop_record/v33/findings/v33audit_2026-11-01/E-rejected-mechanism.md) |
| E-M1-4 | 저손실 손해의 원인과 비교 상한 정의 | CONFIRMED | [원문 53행, 검증 144행](loop_record/v33/findings/v33audit_2026-11-01/E-rejected-mechanism.md) |
| E-M1-5 | 복구 불가 hold parity의 TTL 폐기와 credit 계상 | CONFIRMED | [원문 60행, 검증 146행](loop_record/v33/findings/v33audit_2026-11-01/E-rejected-mechanism.md) |
| F1 | 동결 클라이언트와 C1 회신 판본의 호환성·서버 바이트 계수. 호환 문제 자체는 당시에도 문서화됨 | PARTLY | [원문 14행, 검증 115행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F2 | 연결별 서버 기록 내보내기 부재 | CONFIRMED | [원문 21행, 검증 117행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F3 | 복구 불가 hold parity TTL 폐기. 보류 복호 계약상 동작 | PARTLY | [원문 28행, 검증 119행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F4 | gen33 기본값과 v3.1 봉인 조건의 대응 | CONFIRMED | [원문 35행, 검증 121행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F5 | pad·dup 비교 팔의 drop-parity C1 장부 | CONFIRMED | [원문 42행, 검증 123행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F6 | cached_k 과소 추정에 따른 flight 분할 표시의 한계 | PARTLY | [원문 49행, 검증 125행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F7 | 빌드 stage 누적. 당시 산출물 보존 규칙의 영향 구분 | PARTLY | [원문 56행, 검증 127행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| F8 | Go 시험 보고에서 M1 wire 관문 SKIP 누락 | CONFIRMED | [원문 63행, 검증 129행](loop_record/v33/findings/v33audit_2026-11-01/F-go-testbed.md) |
| G-E1 | 주장 문서의 금지 문구·단서 누락 | CONFIRMED | [원문 14행, 검증 106행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E2 | 막힌 측정 사슬의 결정 기록 누락 | CONFIRMED | [원문 21행, 검증 108행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E3 | README와 정책·상태 판본의 차이 | CONFIRMED | [원문 28행, 검증 110행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E4 | 정정표의 정정·확인 행 구분 | PARTLY | [원문 35행, 검증 112행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E5 | 내부 호칭과 독자를 위한 문서 풀이 | CONFIRMED | [원문 42행, 검증 114행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E6 | H1 기존 구간과 Holm 판정 하한의 구분 | CONFIRMED | [원문 49행, 검증 116행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E7 | 저장소에 남은 MDS 설명 오류 | CONFIRMED | [원문 56행, 검증 118행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| G-E8 | 시험용 PEM 이력과 공개 범위 | CONFIRMED | [원문 63행, 검증 120행](loop_record/v33/findings/v33audit_2026-11-01/G-claims-frame.md) |
| H-05 | L1과 이후 후보의 채택 관문 차이 | CONFIRMED | 원문 181행, 검증 374행 |
| H-06 | 처리 기록과 저장소 크기 변화의 차이 | CONFIRMED | 원문 202행, 검증 376행 |
| H-11 | 같은 seed MC 정밀화를 새 표본 확증과 구분 | PARTLY | 원문 259행, 검증 386행 |
| H-12 | 시험용 PEM의 이력 잔존 | CONFIRMED | 원문 273행, 검증 388행 |
| Q-01 | gen-2 뒤따르는 parity 항의 표본 부족 | 이관 분류 FINAL-SHOULD | 원문 291행 |
| Q-02 | p18 검사 판정 방향 | 이관 분류 FINAL-MUST | 원문 292행 |
| Q-03 | p16 판정 자와 하네스 표류 | 이관 분류 FINAL-MUST | 원문 293행 |
| Q-04 | 허용집합 자와 순차 팔의 시간 효과 | 이관 분류 FINAL-MUST | 원문 294행 |
| Q-05 | gen-2 수동 m·k 제어·하향 보호 범위 | 이관 분류 FINAL-MUST | 원문 295행 |
| Q-08 | 옛 팀 문서·보고 경로·변경보고 소스 상태 | 이관 분류 FINAL-MUST | 원문 298행 |
| Q-09 | 보고서에 반영할 한계 | 이관 분류 FINAL-MUST | 원문 299행 |
| Q-10 | PTO 배수의 RFC 유도와 측정 범위 | 이관 분류 FINAL-SHOULD | 원문 300행 |
| Q-13 | 명세와 측정 Go 판본의 차이 | 이관 분류 FINAL-MUST | 원문 303행 |
| Q-14 | 단방향 netem과 gemodel 손실 해석 | 이관 분류 FINAL-MUST | 원문 304행 |
| Q-16 | 선행연구 문서의 서버 수정·캐시·MDS 설명 | 이관 분류 FINAL-MUST | 원문 306행 |
| Q-17 | 옛 PTO 비율의 분모·z 재현 문제 | 이관 분류 FINAL-SHOULD | 원문 307행 |
| Q-19 | 봉인 프로토콜의 초안 표기와 상속 해시 | 이관 분류 FINAL-MUST | 원문 309행 |
| Q-21 | 과제명·저장소 공개 여부의 사람 결정 | 이관 분류 USER | 원문 311행 |
| Q-22 | gen-2 p15의 ips 기반 검사와 실제 m_used | 이관 분류 FINAL-MUST | 원문 312행 |
| Q-23 | v3.1 후속 제안의 감시·고착·비용·예측 정의 | 이관 분류 DROP | 원문 313행 |
| SW:A-3 | gen-2 p16 판정 자와 하네스 표류 | 이관 분류 DROP | 원문 471행 |
| SW:A-5 | 옛 gen-2 폐루프의 수동 m | 이관 분류 FINAL-MUST | 원문 473행 |
| SW:A-7 | 옛 gen-2 부호·복호 지원과 m 선택의 구분 | 이관 분류 DROP | 원문 475행 |
| SW:C-9 | 보고서에 남길 한계 | 이관 분류 FINAL-MUST | 원문 494행 |
| SW:D-3 | gen-2 p18의 m 순서 판정 표본 | 이관 분류 DROP | 원문 497행 |
| SW:D-4 | gen-2 p17 시간 이득 판정 표본 | 이관 분류 DROP | 원문 498행 |
| TD:5-6 | 보고서 한계 추가 | 이관 분류 FINAL-MUST | 원문 441행 |
| TD:7-3 | gen-2 p18의 m 미세 순서 판정 표본 | 이관 분류 DROP | 원문 452행 |
| TD:7-4 | gen-2 p17 시간 이득 판정 표본 | 이관 분류 DROP | 원문 453행 |
| TD:결정-0830-p17 | 옛 p17 진행 결정. 당시 행동 공간·cert 조건의 설명 | 이관 분류 DROP | 원문 465행 |
| TD:수리-0830-pto | PTO 배수의 측정으로 남겨 둔 수리 항목 | 이관 분류 FINAL-SHOULD | 원문 466행 |
| VF-POL5-1 | C1 회신 비용을 세계 비용에 넣지 않은 한계 | 이관 분류 DROP | 원문 541행 |
| VF-POL5-2 | C1 burst 조건의 p 과소추정과 비용 차이 | 이관 분류 DROP | 원문 542행 |
| VF-POL5-3 | 공동 절대 목표 미확정 | 이관 분류 DROP | 원문 543행 |
| VF-POL5-4 | none 경로의 고착·추가 바이트 | 이관 분류 DROP | 원문 544행 |
## 5. 결정 ID

D 번호는 결정의 식별자다. D1~D49는 v33 결정 기록, D50~D79는 최종 루프 결정 기록을 기준으로 읽는다. 이 표의 "당시"는 원문을 쓴 시점이며, 후보의 기본값을 정했다는 사실이 활성 정책 채택을 뜻하지 않는다. 후속 결정이 있는 행은 그 번호를 함께 적었다. 사본의 출처와 복사 시점은 source map에 있다.

옛 v33 기록에도 D50~D52가 있다. 현재 D50은 모든 팔에서 `-ips` 없이 W=1280을 쓰며 F31 Initial 확대 팔만 예외다. 옛 D50의 `-ips` 명시 제안이나 과거 W 해석은 현재 실행 지시로 쓰지 않는다. 현재 D51은 seed 증원 제안을 폐기했고, D52는 옛 E12 산출물을 비활성 기록으로 보존한다.

| ID | 결정의 뜻 | 기본값과 후속 관계 | 출처 |
|---|---|---|---|
| D1 | GitHub push 여부 | 로컬 커밋만. 현재 비공개·push 경계는 D62. | v33 결정 |
| D2 | 봉인 원자료·바이너리의 GitHub Release 업로드 | 업로드하지 않고 로컬 보존. 노트북 밖 사본은 D63. | v33 결정 |
| D3 | v3.3 확증 측정 | 당시 프로토콜 초안까지만. 이번 루프에서는 D67에 따라 실행하지 않음. | v33 결정 |
| D4 | 최종 보고서가 인용할 알고리즘 판 | 당시 미정. 현재 인용 범위는 D65. | v33 결정 |
| D5 | 비교 실험의 gen-2 기준 | 동결 바이너리 d98b05d7을 기준으로 유지. | v33 결정 |
| D6 | pq_afec_next의 p3 교대 측정 포함 여부 | 정본에 넣지 않고 보관 브랜치로 유지. D66에서 재확인. | v33 결정 |
| D7 | 외부 구현 소스 다운로드 | 당시 PC에 있는 것만 사용하고 없으면 X7을 건너뜀. 이번 X7 범위는 D56. | v33 결정 |
| D8 | 팀원 공유 시점 | 루프 중 공유하지 않음. D69에서 재확인. | v33 결정 |
| D9 | 볼트 기록 주체 | 루프는 쓰지 않고 후속 Claude 정리로 남김. 로컬 보존. | v33 결정 |
| D10 | 과제명 선택 | 당시 미정. 이번 제출 기준본·공식 과제명은 D59. | v33 결정 |
| D11 | 저장소 공개 여부 | 비공개 전제로 진행. 현재 공개·이력 범위는 D62. | v33 결정 |
| D12 | X9 결과의 변경보고·덱 반영 | 정정 문장 틀만 만들고 제출 문서는 팀이 수정. D69에서 덱 미수정을 유지. | v33 결정 |
| D13 | 회신 부재·PTO의 all-lost 처리 | 전멸이 확인된 수신 증거에만 all-lost 적용. 당시 none 관측 설명과 현행 D41 경로를 구분. | v33 결정 |
| D14 | W0에 없는 C1 회신의 평가 | 당시 수동 관측 모형에서 c1 주 비교, none·ideal 진단. 채택 판정은 D47이 대체. | v33 결정 |
| D15 | L2 EPS 후보의 사전·관측 | 결과 전에 고정한 EPS 적응 후보. 후보는 미채택이며 상태 정리는 D49. | v33 결정 |
| D16 | L3 CUSUM 후보의 반응·관측 준비 | 후보 수치와 감지 지연 집계를 사전 고정. 전체 후보는 미채택이며 D41의 record_only와 구분. | v33 결정 |
| D17 | J6 margin·A_pre 관측 창 | 후보의 margin과 관측 통계를 사전 고정. 영분산 재판정은 D44·D45. | v33 결정 |
| D18 | L5 응답 관측·혼합·역사 자료 | 출처 없는 N·tail을 만들지 않음. 역사 관문의 대체 절차는 D48. | v33 결정 |
| D19 | J7과 G1의 선행 관계 | 당시 활성 L1 Go 거울을 E12로 분리. 이후 G1·G2 정의는 D46. | v33 결정 |
| D20 | 옛 M1 hold 후보의 수신 기한·보관 한도 | 수신 관측 기반 기한과 메모리 한도, lead-hold 기본 off. 새 M1 A/A 측정과 별개. | v33 결정 |
| D21 | S4 gen-2 캐시 변환 | 암묵 판본 map을 명시 판본으로 옮기고 과거 관측을 보존. 새 필드는 과거 증거로 꾸미지 않음. | v33 결정 |
| D22 | T1 고정 인증서 서명 방식 | ECDSA P-256과 CertificateVerify 방식을 유지하고 인증서 파일의 차이만 제거. | v33 결정 |
| D23 | T4 HCT 이후 C1 수집 대기 | 명시 feedback-wait와 실제 대기를 기록하고 HCT는 대기 전에 고정. 측정별 값은 계획을 따름. | v33 결정 |
| D24 | T5 복호기 색인·보관 상한 | 원본·비행·payload의 상한과 초과 시 fallback을 사전 고정. | v33 결정 |
| D25 | T5 서버 UDP 경로 | oob 기본값과 basic 비교 경로. X3 비교 전 경주·HCT 효과를 주장하지 않음. | v33 결정 |
| D26 | T5 첫 묶음 해제의 k 입력 | 명시 expect-k 우선, 미지정 시 첫 묶음에 cached_k 사용. natural_k와 구분. | v33 결정 |
| D27 | E18 묶음 시각 관측 범위 | 첫 입력 대기와 송신 완료를 구분하고 예상 k 미달만 분할 의심으로 표시. | v33 결정 |
| D28 | T6 응답 전 후속 묶음 보호 | 당시 original_first 기본값. D43이 repeat_first로 대체했으며 옛 본문은 이력. | v33 결정 |
| D29 | T3 pad·dup의 바이트 계수 | pad의 헤더 보존·본문 치환과 dup의 원본 복제 규칙. 실제 수신 바이트와 parity 계수를 구분. | v33 결정 |
| D30 | T3 ClientHello padding·Initial 크기 | 고정 client 모드의 k-inflate 입력과 실제 ips_eff 기록 계약. | v33 결정 |
| D31 | T2 토큰·티켓 공유와 수집 | 기본 off, 고정 모드만 허용. 수신·주소 검증·TLS 재개를 분리하고 E21은 M4에 통합. | v33 결정 |
| D32 | O2 업링크·경주 입력과 추정기 | 미확인과 무제한을 구분한 비활성 참조. 평가 뒤에도 활성 정책에 채택하지 않음. | v33 결정 |
| D33 | J5 iid·GE 경계와 상태 이월 | 물리적 손실 길이·완전 비트맵 계약. 전체 HCT나 공동 학습 채택으로 넓히지 않음. | v33 결정 |
| D34 | O3 RTT 표본과 변동 여유 | 귀속이 확인된 ACK에서 대기·자기 바이트 등을 보정. 실제 입력 계약 미충족으로 활성 연결 보류. | v33 결정 |
| D35 | O4 현재 ClientHello의 k | 실제 CH·CID·토큰·W로 계산하는 비활성 후보. 송신 전 훅과 후보별 k 연결은 별도. | v33 결정 |
| D36 | J3 복구 비용과 종료 근사 | 원본·선행 credit·보관 parity를 구분한 유한 근사. 비용 참조와 전송 세계를 분리. | v33 결정 |
| D37 | M4 토큰·Retry와 추가 묶음 | 토큰 전달과 수락을 구분하고 연결당 추가 묶음 예약을 한 번으로 제한한 비활성 후보. | v33 결정 |
| D38 | M4 관측 캐시와 TLS 분기 | 실제 관측으로 full·resumed·unknown을 구분하고 티켓 제안만으로 결과를 정하지 않음. | v33 결정 |
| D39 | J8 서버 프로필·하향 손실 | 알려진 설정과 미확인 서버를 구분. 하향 손실 비용 미지원과 활성 미채택을 유지. | v33 결정 |
| D40 | T1 시험용 키가 남은 git 이력 | 현재 추적에서 제거한 키의 이력 공개는 별도 문제. D42·D62에 따라 이력 재작성·배포를 하지 않음. | v33 결정 |
| D41 | 활성 v3.3.1-dev와 c1_seen 분기 | none은 v3.2-dev와 비트 일치, c1_seen 이후 L1 관측·L3 record_only 결정. 상태 판본 11. | v33 결정 |
| D42 | gen33 git 이력 처리 | 이력을 다시 쓰지 않고 이력 없는 사본의 내보내기 절차를 사용. 현재 배포 경계는 D62. | v33 결정 |
| D43 | 재전송 기본값과 sealed31 | repeat_first 기본값을 복원하고 sealed31 profile 제공. original_first는 명시 비교 팔. | v33 결정 |
| D44 | 서로 다른 행동의 영분산 MC 경계 | Z1 비짝 구간으로 MC 반폭을 보충하는 재판정 규칙. 기존 N·seed·문턱은 유지. | v33 결정 |
| D45 | J6 재판정 범위 | Z1로 재판정만 하며 활성 편입은 별도 관문. 이번 루프의 후보 재진입은 [닫힌 과제](닫은%20과제%20목록.md) 참조. | v33 결정 |
| D46 | G1·G2 정의와 의존 교착 | 활성 정책 Go 거울을 G1에, 해당 전송 검증을 G2에 두고 미채택 후보의 의존을 분리. | v33 결정 |
| D47 | 후보의 대칭 채택 기준 | none 포함 배포 경로 전체를 같은 기준으로 판정. D14의 채택 판정 기본값을 대체. | v33 결정 |
| D48 | L5 역사 관문의 대체 조건 | 입력이 없으면 계획을 선커밋한 새 개발 측정으로 대체할 수 있다는 당시 절차. 새 실행을 승인한 기록은 아님. | v33 결정 |
| D49 | L2·J5·J7 상태와 후속 정리 | L2 EPS 후보와 등급 라벨을 구분하고 J7 wire·성능 후속을 분리. 현행 닫힘 범위는 [닫힌 과제](닫은%20과제%20목록.md). | v33 결정 |
| D50 | 측정 Initial 크기 W | W=1280, `-ips` 미지정. F31 Initial 확대 팔만 예외. 기본값으로 진행. | 최종 결정 |
| D51 | B6 seed 증원 제안 | 20 seed 유지, 60 seed 제안 폐기. 기본값으로 진행. | 최종 결정 |
| D52 | 옛 E12 생성기·참조 보존 | 지우지 않고 비활성 기록으로 분류. 기본값으로 진행. | 최종 결정 |
| D53 | 필수 개발 측정 묶음 포함 | 포함으로 정해짐. 실행 결정값은 yes이며 M0·M1·X1·X9·X6 최소판을 포함. | 결정값 |
| D54 | gen33 설치 바이너리 교체 | 옛 설치본 보관 뒤 교체. 결정 기록에 F16 완료가 적혀 있음. | 최종 결정 |
| D55 | 기존 코드 주석 | 기존 주석 유지, 새 코드 줄에는 주석 금지. 기본값으로 진행. | 최종 결정 |
| D56 | 측정 사슬 밖 E·X 과제 | 지정 과제는 실행하지 않고 X2·X3·X4는 F31의 시간 조건에 따름. | 최종 결정 |
| D57 | AI 활용 칸의 PaperBanana 문구 | 문구 유지, TikZ와의 불일치는 정오표의 결정 대기. 제출 전 도현님 답 필요. | 최종 결정 |
| D58 | 보고서 반영 마감 | 2026-11-12 23:59 KST 이후 측정은 보고서에서 제외. 학교 취합일은 미확인. | 최종 결정 |
| D59 | 제출 기준본·공식 과제명 | 바탕화면의 제출 양식과 공식 과제명을 유지. R-E 제목 아래 범위 문장 추가. | 최종 결정 |
| D60 | 기존 docs 문서 이동 | 이동하지 않고 새 정본·색인에서 작성 시점 기록으로 분류. | 최종 결정 |
| D61 | 동결 세대 문서 수정 | 동결 폴더 문서의 틀린 문장은 R-E에서도 고치지 않고 정정표에만 기록. 2026-11-08 정리의 주석 제거와 표기·문체 정리는 이와 별개다. | 최종 결정 |
| D62 | 공개·라이선스·이력 배포 | 비공개, LICENSE 없음, gen33 이력 미배포. push는 도현님 몫. | 최종 결정 |
| D63 | 노트북 밖 사본 | 루프는 보관본과 복사 명령을 만들며 외부 복사는 도현님 선택. | 최종 결정 |
| D64 | 최종 보고서의 R-E 포함 | 포함하지 않음. 기본값으로 진행. | 최종 결정 |
| D65 | 보고서가 인용할 판과 근거 범위 | v3.1 봉인 수치가 주 결과. v3.3.1-dev는 시뮬레이션·개발 측정으로 한정. | 최종 결정 |
| D66 | pq_afec_next 정본 포함 | 포함하지 않고 보관 브랜치만 push 명령에 명시. | 최종 결정 |
| D67 | v3.3 확증 측정 | 실행하지 않고 R2를 닫음. | 최종 결정 |
| D68 | WSL·스크래치 산출물 삭제 | 삭제하지 않음. 기본값으로 진행. | 최종 결정 |
| D69 | 팀원 공유·덱 수정 | 루프 중 공유와 덱 수정을 하지 않음. | 최종 결정 |
| D70 | gen-2의 남은 측정 쟁점 | 다시 재지 않고 한계·정정표에 기록. | 최종 결정 |
| D71 | replay_g3·G3h·exact 팔 처리 | replay_g3는 문서 기록, G3h 수용, exact 팔 미등록. | 최종 결정 |
| D72 | GitHub 저장소 설명 수정 | 현재 문구 유지. 수정은 소유자 몫. | 최종 결정 |
| D73 | quiche 대조 원자료 | 현재 문장 유지, 원자료 수신 후 보고서 보충은 도현님 몫. | 최종 결정 |
| D74 | V4 RTT 50 행의 출처 | 값 유지, Fig. 3 캡션 정정안을 기록하고 도현님이 출처 확인. | 최종 결정 |
| D75 | 다른 기관·대회 미제출 체크 | 체크하지 않은 채 두고 도현님이 지도교사와 확인. | 최종 결정 |
| D76 | 제출물의 기존 미결 사항 | 정정 보고·예산·슬라이드·초록 등은 루프 범위 밖, 도현님 몫. | 최종 결정 |
| D77 | 보고서 사람 입력 칸·서명 | 루프가 채우지 않고 도현님과 팀원이 작성. | 최종 결정 |
| D78 | 볼트의 낡은 문장 정리 | 루프 뒤 Claude가 처리. 로컬 보존이며 이 문서 작성은 수정 완료를 뜻하지 않음. | 최종 결정 |
| D79 | 실제 연결 간 idle 관측 부재 | mean_idle_ms는 null·미확인. feedback_wait와 계획 gap의 합은 별도 진단이며 5 ms 기준을 통과로 표시하지 않음. | 최종 결정 |

봉인 프로토콜의 D1~D6은 위 루프 결정과 다른 번호 체계다. v3.0 2단계 프로토콜 14.1절의 봉인 전 편차를 가리키며 v3.1 프로토콜도 이를 이어받는다. 이때 D1은 하네스 대조 팔·A/A 사이클 수의 편차다. 원문은 동결 세대의 프로토콜에 로컬 보존돼 있다. D_p11_2955처럼 밑줄이 있는 표기는 측정 조건 이름이다.

## 6. 작업 이름

묶음은 2026-11-02 수정 작업의 분담 이름이다. 같은 글자를 쓰는 과제 접두어·감사 ID·측정 조건과 구분한다. 아래 문서의 완료·미완료 표현은 해당 작업 시점 기록이다.

| 이름 | 뜻과 읽는 범위 | 출처 |
|---|---|---|
| 반복 NN | 실행기의 한 호출 번호. 같은 과제를 여러 반복에 걸쳐 수행할 수 있으며 옛 v33 루프와 최종 루프의 번호는 별도. | 옛 JOURNAL |
| 카드 | 과제의 조건·의존·할 일·완료 기준을 묶은 작업 단위. 후보 채택 여부와 카드 완료 상태는 구분. | 옛 과제 카드, 추가 카드 |
| 묶음 A-py | v3.3.1-dev 활성 Python 정책과 c1_seen 분기 수정. | [정책 수정 기록](v3.3.1%20활성%20정책%20수정.md) |
| 묶음 A-go | 활성 정책의 Go 거울과 Python-Go 일치 관문. | [Go 수정 기록](v3.3.1%20Go%20정책과%20관문.md) |
| 묶음 A-eval | v3.3.1-dev의 W1 사후 재판정과 개발 시뮬레이션 기록. | [평가 기록](v3.3.1%20W1%20재판정.md) |
| 묶음 B | Go testbed 수정. | [testbed 수정 기록](v3.3.1%20Go%20테스트베드%20수정.md) |
| 묶음 C | 세계 시뮬레이터와 판정 통계 도구 수정. | [세계 수정 기록](v3.3.1%20세계%20시뮬레이터와%20판정%20통계.md) |
| 묶음 D | 문서·저장소 위생 수정과 뒤 통합 정정. | 문서 수정 기록 |
| 묶음 E | 옛 루프 카드·상태·실행기·R-E 작업 위치의 수정. 추가 과제 E 번호와 별개. | E-loop 보고 사본 |
| 묶음 P | 1차 검증 뒤 정책 시험·관문·주장 문서의 남은 항목 정리. | [정책 기록의 통합 정리](v3.3.1%20활성%20정책%20수정.md) |
| 묶음 G | 1차 testbed 검증 뒤 Go 측 남은 항목 통합. | [testbed 기록의 통합 정리](v3.3.1%20Go%20테스트베드%20수정.md) |
| 묶음 W | 1차 세계 검증 뒤 세계·통계 도구의 남은 항목 통합. 과제 W0·W1과 별개. | [세계 기록의 통합 정리](v3.3.1%20세계%20시뮬레이터와%20판정%20통계.md) |
| 묶음 L | 묶음 E 이후 루프 자료·의존·결정·증거 보존의 후속 통합. learning layer 과제 L 번호와 별개. | 옛 MORNING_REPORT의 2차 통합 정리 |
| V33FIX | 2026-11-02 감사 후 v3.3.1-dev 정책과 주변 도구를 수정·검증한 작업 이름. 단일 알고리즘 후보나 새 측정의 이름이 아님. | [정책](v3.3.1%20활성%20정책%20수정.md), [testbed](v3.3.1%20Go%20테스트베드%20수정.md), [세계](v3.3.1%20세계%20시뮬레이터와%20판정%20통계.md), 문서 |
### 6.1 과제 번호와 닮은 표기

ID 자동 수집기는 숫자가 붙은 기호와 보고서 행 번호도 찾는다. 이 표는 그 표기를 과제와 구분한다. W 범위의 중간 정수는 원문 구간의 값이며 별도 과제가 아니다.

| 표기 | 뜻·원문 |
|---|---|
| B0 | 추가 행동이 없는 (0,0,0) 기준 행동. 소문자 b0와 같은 문맥이며 [현재 결정 순서](v3.3.1%20활성%20정책%20수정.md)에서 쓴다. |
| C2 | 회신 부재·PTO만으로 전멸을 적립하던 휴리스틱 이름. gen33의 gen-2 경로에서는 해당 호출을 제거했고 동결 비교 바이너리와 구분한다. [관측 계약](L1%20first%20flight%20관측%20계약.md), T4 제거 기록, D13 |
| C5 | [정오표](보고서%20정오표.md)의 workbook 범위 B5:C5에서 열 C·행 5인 셀 주소다. 이 문맥의 B5도 세계 평가 조건이 아니다. |
| G4 | [testbed 수정 기록](v3.3.1%20Go%20테스트베드%20수정.md)의 conn-log 중복 방지 표시를 제거한 변형 시험 표기다. Go 과제 번호가 아니다. |
| G2·G33 | [보고서 trace](보고서%20출처%20대조표.md)의 경로 별칭에서는 gen-2 자료와 gen33 저장소를 뜻한다. 과제 G2의 wire 검증과 구분한다. |
| H5 | 봉인 결과에서 cold 첫 방문의 HCT·first flight uplink를 보고하는 항목이다. H1~H4의 판정과 구분한다. [v3.1 결과](../../pq_afec_gen31/g3/RESULT_stage3.md)는 로컬 보존이다. |
| J50·J58·J104 | [정책 한계](활성%20정책의%20알려진%20한계.md)의 J50.07·J58.46·J104.45 ms에서 비용 J와 값이 붙은 표기다. 비용 모형 과제 번호가 아니다. |
| L0 | [J5 참조](J5%20GE%20참조와%20조건부%20추정%20결과.md)의 후속 L0·T1은 lead 0·trailing 1개를 뜻한다. [hold 설명](v3.3.1%20Go%20테스트베드%20수정.md)의 L0+O0에서는 첫 lead parity와 첫 원본의 인덱스다. |
| S4000·S5000·S7910·S18231·S18232 | S 뒤에 바이트 수를 붙인 모형 입력. [정책 한계](활성%20정책의%20알려진%20한계.md), [하향 손실 진단](J8%20하향%20손실과%20서버%20타이머%20진단.md), [프로필](J8%20서버%20프로필%20참조%20결과.md), [J3 계획](J3%20실패%20비용%20진단%20계획.md)에 정의돼 있다. S4000~20000처럼 쓴 범위도 모형 입력 범위다. |
| W1200~W1452 | W 뒤에 원본 바이트 크기를 붙인 범위. [O4 참조](O4%20ClientHello%20패킷화%20참조%20결과.md)의 W1200~1416과 1417~1452는 ClientHello 재배치에 따른 k 경계이며 세계 과제 W0·W1과 구분한다. |
| X10 | F31의 RTT 비례 개발 측정 선택 과제. [이번 계획](../g3/v33/plans/final_bundle_v1.json)의 optional 항목이며 완료를 뜻하지 않는다. |
| X25519 | [보고서 수치 대조표](보고서%20수치%20대조표.md)에서 사용하는 키 교환 그룹 이름이다. 개발 측정 X 과제의 번호가 아니다. |

### 6.2 보고서 trace 번호

T 뒤에 세 자리 숫자를 붙인 다음 번호는 [보고서 출처 대조표](보고서%20출처%20대조표.md)의 행 식별자다. 같은 번호 행의 content.py 줄, 주장, 출처, 감사 판정과 수치 키를 함께 읽는다. 과제 T1~T7의 상태와 연결하지 않는다. 표기의 존재가 그 행의 문장 전체를 검증했다는 뜻은 아니다.

| ID | 뜻·출처 |
|---|---|
| T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T025, T026, T027, T028, T029, T030, T031, T032, T033, T034, T035, T036 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T037, T038, T039, T040, T041, T042, T043, T044, T045, T046, T047, T048 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T049, T050, T051, T052, T053, T054, T055, T056, T057, T058, T059, T060 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T061, T062, T063, T064, T065, T066, T067, T068, T069, T070, T071, T072 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T073, T074, T075, T076, T077, T078, T079, T080, T081, T082, T083, T084 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T085, T086, T087, T088, T089, T090, T091, T092, T093, T094, T095, T096 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T097, T098, T099, T100, T101, T102, T103, T104, T105, T106, T107, T108 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T109, T110, T111, T112, T113, T114, T115, T116, T117, T118, T119, T120 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T121, T122, T123, T124, T125, T126, T127, T128, T129, T130, T131, T132 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T133, T134, T135, T136, T137, T138, T139, T140, T141, T142, T143, T144 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
| T145, T146, T147, T148, T149, T150, T151, T152, T153 | [보고서 출처 대조표](보고서%20출처%20대조표.md)의 같은 번호 행 |
