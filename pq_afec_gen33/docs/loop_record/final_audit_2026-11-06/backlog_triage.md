# 지금까지 쌓인 할 일 전부의 최종 분류

2026-11-06, gen33 `feb0b1850`, R-E main `70e7e08` 기준. 생성 스크립트와 빠짐없음 검사는 같은 세션 스크래치 `finalaudit\backlog\`의 `build_triage.py`, `check_triage.py`, 출력 `check_triage.out.txt`.

분류: FINAL-MUST는 최종 코드·문서에 꼭, FINAL-SHOULD는 시간 되면, DROP은 하지 않음(이유 필수), USER는 도현님 결정. BL-nn은 `backlog.json`의 항목이다. 반영은 추적 장부 값이고, 직접 확인이 필요한 것은 직접 확인한 뒤 분류를 바꿨다(1·2절의 S2, A1, A6-01, Q-20 등).

## 0. 집계

| 분류 | 행 수 |
|---|---:|
| FINAL-MUST | 85 |
| FINAL-SHOULD | 47 |
| DROP | 416 |
| USER | 49 |
| 합계 | 597 |

## 1. 루프 과제 94개

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| S0 | 기준선과 gen33 git 저장소 (30~45분) | done | DROP | done. 기준선 커밋이 있고 남은 일 없음 | prompt/TASKS.md:32 |
| S1 | 원자료와 봉인 바이너리 보존 (30~60분) | done | DROP | done. 보존본 검증 끝. 보존 위치 결정은 BL-35 | prompt/TASKS.md:44 |
| S3 | gen33의 세대 경로 정리 (45~60분) | done | DROP | done. genconfig 경로 정리 끝 | prompt/TASKS.md:55 |
| A0 | 근거 재현 묶음 (45~60분) | done | DROP | done. 근거 재현 스크립트 있음 | prompt/TASKS.md:100 |
| W0 | 세계 모형 분리 (90~120분) | done | DROP | done. 세계 시뮬레이터 동결 | prompt/TASKS.md:126 |
| W1 | 회귀 벤치와 문턱 (60~90분) | done | DROP | done. 기준값 저장됨 | prompt/TASKS.md:151 |
| L1 | 데이터그램 단위 손실 증거 (90~120분) | done | DROP | done. v3.3.1-dev의 c1 경로로 대체됨(D41) | prompt/TASKS.md:189 |
| L2 | 3등급 라벨과 기준선 (45~60분) | done | DROP | done. EPS 적응 버림. 부정 결과 문단은 BL-03 | prompt/TASKS.md:203 |
| L3 | 건너뛰기·재평가·감시층 정리 (60~90분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:208 |
| J1 | 2-RTT 둘째 왕복 꼬리 (45~60분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:245 |
| J6 | δ 후보에 A_pre와 여유 (30분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:274 |
| L5 | S 추정과 n_need (60~90분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:225 |
| E12 | 활성 L1의 Go 거울 선행 단계 | done | DROP | done. v3.3.1 관문 gate_l1_go로 대체됨 | state/EXTRA_TASKS.md:144 |
| J7 | 패리티 크기 고정과 상한 (45분, Go 포함) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 상한 1452 B만 활성에 들어감. 부정 결과는 BL-03 | prompt/TASKS.md:279 |
| M1 | 선행 패리티 보류 복호 (120~180분, Python 모형 + Go 서버 + 와이어 시험) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:295 |
| G1 | 채택된 활성 정책의 Go 거울과 정책 관문 (90~150분, 여러 번 나눠도 됨) | done | DROP | done(통합 결정). coverage 파일 없음은 BL-23 | prompt/TASKS.md:351 |
| G2 | 와이어 관문 (60분) | todo | FINAL-MUST | 최종 Go 와이어와 Python 모형 대조가 없다. BL-06 | prompt/TASKS.md:359 |
| S4 | 10-07 gen-2 수정 이식 (60~90분) | done | DROP | done. 10-07 수정 이식 끝 | prompt/TASKS.md:65 |
| T1 | 결정적 인증서 (30~45분) | done | DROP | done. 결정적 인증서 끝 | prompt/TASKS.md:368 |
| T4 | 관측 장치 (60~90분) | done | DROP | done. 넘겨받은 항목 미기록은 BL-23 | prompt/TASKS.md:380 |
| T5 | 복호기·클라이언트 견고성 (60분) | done | DROP | done. 복호기·UDP 경로 끝 | prompt/TASKS.md:385 |
| T6 | 재전송 비행 모양 (45분) | done | DROP | done. 기본값은 D43으로 repeat_first | prompt/TASKS.md:390 |
| T7 | v3.3 개발 측정 러너 (120~180분) | todo | FINAL-MUST | 측정 러너가 없다(devbed.py 없음). BL-07 | prompt/TASKS.md:394 |
| X6 | v3.3 대 v3.1 대 gen-2 (스모크 → 본측정 약 2~3시간) | todo | FINAL-SHOULD | v3.3.1-dev 실측 0건을 끝낼 측정. BL-16 | prompt/TASKS.md:417 |
| T3 | 같은 바이트 비교 팔 (45~60분) | done | DROP | done. 비교 팔 플래그 있음. X1이 쓴다 | prompt/TASKS.md:376 |
| X1 | 같은 바이트 패딩 대 패리티 (약 1시간) | todo | FINAL-MUST | 핵심 주장을 직접 잰 적이 없다. BL-08 | prompt/TASKS.md:422 |
| T2 | 토큰·resumption 팔 (60분) | done | DROP | done. 토큰·resumption 플래그 있음. X4가 쓴다 | prompt/TASKS.md:372 |
| X4 | 토큰·resumption 기준선 (약 1.7시간) | todo | FINAL-SHOULD | 토큰·resumption 기준선. 시간 남으면. BL-20 | prompt/TASKS.md:427 |
| X3 | A_pre 탐침 (약 15분) | todo | FINAL-SHOULD | A_pre·PTO 배수·뒤 패리티 신용 탐침. BL-18 | prompt/TASKS.md:436 |
| X9 | PTO 비율 재측정: 방향 전환 근거 (약 1~1.5시간) | todo | FINAL-SHOULD | 방향 전환 근거 재측정. 안 재도 보고서는 판정 보류로 맞다. BL-17 | prompt/TASKS.md:443 |
| X2 | 업링크 오입력 (약 15~30분) | todo | FINAL-SHOULD | 업링크 오입력 강건성. 15~30분. BL-19 | prompt/TASKS.md:431 |
| E10 | 서로 다른 행동의 수치상 영분산과 J6 채택 재검토 | done | DROP | done(통합 결정). J6 Z1 재판정 끝 | state/EXTRA_TASKS.md:114 |
| E14 | M1 세계의 수신 신용과 송신 재개 분리 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 M1 재진입 | state/EXTRA_TASKS.md:166 |
| E15 | M1 실제 ACK·PTO·CID 재전송 경로 대조 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 M1 재진입 | state/EXTRA_TASKS.md:176 |
| E25 | RTT 표본 귀속과 실제 송신 관측 (T4 후속) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 O3 재진입용 관측 | state/EXTRA_TASKS.md:301 |
| E27 | 후보별 natural_k와 현재 k 정책의 채택 평가 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 O4 재진입 | state/EXTRA_TASKS.md:318 |
| E28 | 송신 전 ClientHello 입력과 첫 비행 expectK 연결 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 O4 재진입용 quic-go 훅 | state/EXTRA_TASKS.md:325 |
| E1 | 봉인 판정의 독립 재계산 | todo | FINAL-MUST | 봉인 판정 독립 재계산. E36과 한 항목. BL-12 | state/EXTRA_TASKS.md:13 |
| E39 | none B8 seed 46 쌍안정 진단 | todo | DROP | 후보 판정용 진단이다. 후보 평가를 끝내므로 쓸 곳 없다. 단서는 BL-03 | state/EXTRA_TASKS.md:405 |
| E38 | J7 남은 와이어 계약: 패리티 크기 고정과 파싱 실패 계수 | todo | FINAL-SHOULD | fec_parse_fail 계수와 경계 시험만 한다. 크기 고정은 하지 않는다. BL-21 | state/EXTRA_TASKS.md:397 |
| E40 | done 과제가 확인하지 않은 넘김 항목과 남은 교착 항목 보충 | todo | DROP | 대체됨: 이 표가 194항목 전부를 최종 분류한다. 장부 마감은 BL-23 | state/EXTRA_TASKS.md:413 |
| E41 | J6 margin30을 활성 정책의 c1_seen 참 경로에 넣을지 판정 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 granular 계수에서만 이득이고 exact에서는 +120 ms(J6_disposition.md) | state/EXTRA_TASKS.md:421 |
| O2 | 업링크 u (45~60분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:334 |
| J5 | Gilbert-Elliott 버스트 (60~90분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:268 |
| O3 | RTT 신호 (45분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:339 |
| O4 | k를 로컬에서 계산 (30분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:343 |
| J3 | 실패 가지와 재전송 비행 (60분, 우선순위 낮음) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:256 |
| M4 | Retry·토큰 인식 (45분) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:319 |
| J8 | 서버 프로파일 매개변수 (60분, 모형만) | blocked | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 부정 결과는 BL-03 | prompt/TASKS.md:285 |
| L4 | 재주입 사전과 hazard (45분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:218 |
| J2 | 처리 상수 (30~45분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:250 |
| J4 | RTT ≥ 200 탐침 체제 (45분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:262 |
| O1 | 바이트 예산 (45~60분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:327 |
| L6 | 첫 방문과 상태 키 (60분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:235 |
| M2 | 송신 순서 옵션 (45분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:309 |
| M3 | lead와 T 상한 분리 (45분) | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 결함은 BL-05 한계에 한 줄로 남긴다 | prompt/TASKS.md:314 |
| X5 | s2c 손실 (약 30~60분) | todo | DROP | 측정 생략: 보고서 한계에 c2s 한정이 이미 적혔다(content.py:210). BL-05 | prompt/TASKS.md:453 |
| X7 | RFC 정확 스택 (선택, 2시간 상한) | todo | DROP | 측정 불가: 이 PC에 quiche·ngtcp2·cargo가 없고 D7이 내려받기를 막는다 | prompt/TASKS.md:460 |
| X8 | 서버 설정 변형: IW10, InitialPacketSize (선택, 1시간 상한) | todo | DROP | 측정 생략: 보고서 후속 연구에 IW 10이 이미 있다(content.py:216) | prompt/TASKS.md:465 |
| S2 | R-E 위생 (30분) | done | FINAL-MUST | done이지만 결과가 R-E main에 안 들어갔다. main clone 봉인 6/92. BL-01 | prompt/TASKS.md:71 |
| S5 | 시험 위생과 CI 초안 (45~60분) | done | FINAL-SHOULD | done이나 CI가 어디서도 안 돈다. BL-22 | prompt/TASKS.md:82 |
| A1 | 보고서 주장 목록 (30~45분) | done | FINAL-MUST | done이지만 정정표만 만들고 문서에 반영 안 함. BL-02 | prompt/TASKS.md:113 |
| R3 | 알고리즘 지도 문서 (45분) | todo | FINAL-SHOULD | 알고리즘 지도. BL-15. 낡은 수치 정리는 BL-13 | prompt/TASKS.md:487 |
| R2 | v3.3 확증 프로토콜 초안 (60분, 봉인하지 않음) | todo | DROP | 봉인 측정을 안 하고 끝내므로 초안이 쓸 곳 없다(D3). 해석 단서만 BL-05 | prompt/TASKS.md:481 |
| E2 | W1 기준 행동 계산과 결과 검사 | done | DROP | done. W1 참조 완료 | state/EXTRA_TASKS.md:25 |
| E3 | W1 정책 행동의 독립 기대값 계산 | done | DROP | done. W1 전체 평가 완료 | state/EXTRA_TASKS.md:35 |
| E4 | W1 기준값 표와 감사 대조 확정 | done | DROP | done. W1 최종표 완료 | state/EXTRA_TASKS.md:43 |
| E5 | L1 고정 정밀화 계산 완료 | done | DROP | done. L1 행동 계산 완료 | state/EXTRA_TASKS.md:53 |
| E6 | L1 정밀화 보고와 채택 판정 | done | DROP | done. L1 판정 완료 | state/EXTRA_TASKS.md:61 |
| E7 | L2 EPS 적응의 식별과 채택 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 L2 재진입 | state/EXTRA_TASKS.md:70 |
| E8 | 비용 모형 보정 뒤 감시와 변화 감지 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 L3 재진입 | state/EXTRA_TASKS.md:79 |
| E9 | 둘째 비행 꼬리 후보의 관측 모형과 채택 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J1 재진입 | state/EXTRA_TASKS.md:92 |
| E11 | 완료 서버 응답의 관측 입력·수신 한도와 L5 채택 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 L5 재진입 | state/EXTRA_TASKS.md:125 |
| E13 | J7 와이어 정정의 효과 분리와 채택 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J7 성능 재판정 | state/EXTRA_TASKS.md:155 |
| E16 | M1 정책 채택 재검토와 Go 비용 거울 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 M1 재진입 | state/EXTRA_TASKS.md:182 |
| E17 | T5 목적지 k 추정과 flush 입력 | done | DROP | done. cached_k 검증 완료 | state/EXTRA_TASKS.md:219 |
| E18 | T5 실제 flush 대기와 비행 분할 관측 | done | DROP | done. 묶음 시각 관측 완료 | state/EXTRA_TASKS.md:227 |
| E19 | 연결 전체 패리티 묶음 상한 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 연결 전체 패리티 상한은 새 정책 | state/EXTRA_TASKS.md:242 |
| E20 | 중복 행동군과 서버 복호 지원 입력 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 dup 행동군 추가는 새 정책 | state/EXTRA_TASKS.md:253 |
| E21 | 토큰·TLS 재개에 맞춘 정책 분기 | skipped | DROP | 대체됨: M4로 통합되어 skipped | state/EXTRA_TASKS.md:262 |
| E22 | 미확인 업링크의 관측·와이어 정합과 채택 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 O2 재진입 | state/EXTRA_TASKS.md:277 |
| E23 | GE 공동 학습과 후속 비용의 채택 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J5 재진입 | state/EXTRA_TASKS.md:287 |
| E24 | 시간 기반 버스트 손실의 개발 측정 | todo | DROP | 측정 생략: J5 재진입용이고 시간 슬롯 손실 도구도 없다 | state/EXTRA_TASKS.md:295 |
| E26 | RTT 정책과 HCT 불확실성 재검토 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 O3 재진입 | state/EXTRA_TASKS.md:309 |
| E29 | J3 실패 경로의 CRYPTO·ACK·타이머 관측 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J3 재진입용 관측 | state/EXTRA_TASKS.md:333 |
| E30 | J3 실패 비용과 재시도 세계의 채택 검증 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J3 재진입 | state/EXTRA_TASKS.md:340 |
| E31 | M4 실제 재방문 입력·캐시·토큰 거절 어댑터 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 M4 재진입 | state/EXTRA_TASKS.md:347 |
| E32 | M4 토큰·Retry·지원 상태의 HCT 비용과 채택 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 M4 재진입 | state/EXTRA_TASKS.md:354 |
| E33 | 서버 프로파일의 실제 관측 입력 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J8 재진입 | state/EXTRA_TASKS.md:360 |
| E34 | 하향 손실의 타이머·재전송 독립 세계 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J8 재진입 | state/EXTRA_TASKS.md:367 |
| E35 | 서버 프로파일·하향 손실 비용의 정책 채택 | todo | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 J8 재진입 | state/EXTRA_TASKS.md:376 |
| E36 | 과거 판정의 읽기 전용 재계산 | todo | FINAL-MUST | E1과 같은 원인. BL-12 | state/EXTRA_TASKS.md:384 |
| E37 | 공개용 사본과 남은 저장소 위생 | todo | FINAL-SHOULD | 공개용 위생 점검. BL-22 | state/EXTRA_TASKS.md:391 |
| R1 | 아침 보고서 (매 반복 갱신, 마감 45분 전 최종) | todo | DROP | 대체됨: 새 최종 루프의 마감 보고로 대체 | prompt/TASKS.md:474 |

## 2. 감사 항목 194개 (FINDINGS_INDEX 171, EXTRA_SOURCES 23)

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| A1-01 | 2-RTT 결과의 두 번째 왕복 손실 항(q2·PTO)이 J3에 없다 | 재현만 / open E9,J1,J5 | DROP | 새 후보 탐색: 남은 곳 E9,J1,J5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:10 |
| A1-02 | 독립 손실 가정 때문에 측정된 버스트 조건(p18)에서 실패 확률을 100배 낮게 본다 | 재현만 / open E23,J5 | DROP | 새 후보 탐색: 남은 곳 E23,J5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:11 |
| A1-03 | 업링크 u가 오라클 입력이라 값이 틀리면 후회가 12~198 ms다 | 넘김-진행가능 / open E22,O2 | DROP | 새 후보 탐색: 남은 곳 E22,O2 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:12 |
| A1-04 | 후보 생성이 A_pre를 빼고 δ를 계산해서 1-RTT를 사는 최소 패딩이 후보에서 빠진다 | 넘김-교착 / open J6,L5 | DROP | 새 후보 탐색: 남은 곳 J6,L5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:13 |
| A1-05 | m≤4 상한이 lead와 T를 묶어 고손실에서 최적 행동을 막는다 | 기록 없음 / open M3 | DROP | 새 후보 탐색: 남은 곳 M3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:14 |
| A1-06 | 송신 순서 LLLOOP 대신 첫 원본을 먼저 보내는 OLLLOP가 같은 바이트로 낫다 | 기록 없음 / open M2 | DROP | 새 후보 탐색: 남은 곳 M2 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:15 |
| A1-07 | u=0에서 목적함수가 바이트를 공짜로 봐서, 사후분포가 p>0에 질량을 두면 늘 최대 패리티를 고른다 | 넘김-진행가능 / open O1 | DROP | 새 후보 탐색: 남은 곳 O1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:16 |
| A1-08 | 실패 가지 비용의 구조 오류가 우연히 상쇄되어 합계만 맞는다 | 재현만 / open E29,E30,J3 | DROP | 새 후보 탐색: 남은 곳 E29,E30,J3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:17 |
| A1-09 | RTT 200 ms 이상에서는 모든 연결이 가짜 PTO 탐침을 보내는데 모형은 이를 모른다 | 재현만 / open J4 | DROP | 새 후보 탐색: 남은 곳 J4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:18 |
| A1-10 | RTT 입력에 업링크 직렬화가 섞여 t_dec와 이중으로 계산되고, 처리 시간 상수가 없다 | 넘김-진행가능 / open E25,E26,J2,O3 | DROP | 새 후보 탐색: 남은 곳 E25,E26,J2,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:19 |
| A1-11 | 신용 전용 선행 데이터그램의 크기가 패리티 크기(W+39+6k)로 고정되어 있다 | 처리 안 함 / open M1 | DROP | 하지 않음: 검증자 doubtful. 패딩과 같아진다 | findings/FINDINGS_INDEX.md:20 |
| A1-12 | S와 k의 추정 오류에 결정이 칼날처럼 민감하다 | 넘김-진행가능 / open E11,E27,E28,L5,L6,O4 | DROP | 새 후보 탐색: 남은 곳 E11,E27,E28,L5,L6,O4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:21 |
| A1-13 | 서버 예산 규칙이 quic-go overshoot와 1280 B 패킷에 고정되어 있다 | 넘김-진행가능 / open E35,J8 | DROP | 새 후보 탐색: 남은 곳 E35,J8 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:22 |
| A1-14 | 모형 세계 적응 벤치는 결과를 정책과 같은 비용 모형으로 만들어서 비용 모형 오류를 원리상 잡지 못한다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(W0) | findings/FINDINGS_INDEX.md:23 |
| A1-15 | 하향 손실과 서버 재전송이 J3에 없다 | 재현만 / open E34,E35,J8 | DROP | 새 후보 탐색: 남은 곳 E34,E35,J8 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:24 |
| A1-16 | 선택에 영향이 작은 가정 두 개: 경주 q 표 보정, 잃은 데이터그램의 업링크 사용 | 넘김-진행가능 / open O2,X3 | FINAL-SHOULD | X3 경주표만. O2는 DROP. BL-18 | findings/FINDINGS_INDEX.md:25 |
| A2-01 | 1비트 사건 관측은 보호 행동에서 정보가 0이 되어 손실 사후분포가 멈춘다 (uninformative-action trap) | 반영 | DROP | 반영: 맡은 과제가 모두 done(L1) | findings/FINDINGS_INDEX.md:26 |
| A2-02 | 고착은 model-world 폐루프에서 재현되고, per-datagram 우도 + 재평가 제거 + 무조건 잔차 감시 제거가 regret을 96%… | 재현만 / open E8,L3 | DROP | 새 후보 탐색: 남은 곳 E8,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:27 |
| A2-03 | 균등 격자 재주입 사전(P(p≥0.15)=0.50)이 사건 3~4번에 사후 평균을 교차점 위로 밀어 올린다 | 기록 없음 / open L4 | DROP | 새 후보 탐색: 남은 곳 L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:28 |
| A2-04 | 무조건 잔차(HCT − j3_pred_pre)의 창 간 차이 감시는 두 봉우리 분포와 사후 지연에 반응하고, 계급 조건부 잔차 감시는 같은 자료… | 넘김-진행가능 / open E8,J1,J2,L3 | DROP | 새 후보 탐색: 남은 곳 E8,J1,J2,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:29 |
| A2-05 | 경보 대응(가산 비용 + 학습 차단)이 정보를 주는 유일한 행동을 64결정 동안 묶어 후회의 대부분을 만든다 | 넘김-진행가능 / open E8,L3 | DROP | 새 후보 탐색: 남은 곳 E8,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:30 |
| A2-06 | 사건 기준선(같은 행동 HCT 32개의 중앙값)이 2-RTT 수준으로 올라가면 2-RTT 결과가 사건에서 빠지고 사후가 낮은 손실로 무너진다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(L2) | findings/FINDINGS_INDEX.md:31 |
| A2-07 | EPS=0.01은 측정된 거짓 사건률 0.069%의 약 15배이고 저손실 정보의 15~51%를 버린다. 반대로 지터가 큰 경로에서는 부족하다 | 넘김-진행가능 / open E7,J2,O3 | DROP | 새 후보 탐색: 남은 곳 E7,J2,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:32 |
| A2-08 | 0% 손실 과보호는 비용 비대칭의 합리적 귀결이 아니라 정보 함정과 바이트를 무시한 목적함수의 결과다 | 넘김-진행가능 / open O1 | DROP | 새 후보 탐색: 남은 곳 O1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:33 |
| A2-09 | v3.2-dev의 '건너뛴 관측에서도 위험률 전이' 변경은 고착을 푸는 대신 25% 손실에서 진동을 만든다 (model-world 순손실) | 재현만 / open L4 | DROP | 새 후보 탐색: 남은 곳 L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:34 |
| A2-10 | 16번마다 재평가는 정보 가치와 무관한 고정 탐색이고, 1비트 정보에서는 Thompson sampling도 실패한다 | 넘김-진행가능 / open E8,L3 | DROP | 새 후보 탐색: 남은 곳 E8,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:35 |
| A2-11 | S_hist가 사건 연결을 빼기 때문에 인증서 교체와 load balancer 혼합에서 S가 작은 쪽으로 치우치고 2-RTT가 손실로 둔갑한다 | 넘김-진행가능 / open E11,L5 | DROP | 새 후보 탐색: 남은 곳 E11,L5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:36 |
| A2-12 | 서버→클라이언트 손실은 클라이언트→서버 손실로 계산된다 (가설, model-world 수치) | 반영 | DROP | 반영: 맡은 과제가 모두 done(L1,W0) | findings/FINDINGS_INDEX.md:37 |
| A2-13 | 정책 RTT는 전 기간 최솟값이라 내려가기만 하고, 사건 문턱 0.5·RTT는 HCT 지터를 보지 않는다 | 넘김-진행가능 / open E26,O3 | DROP | 새 후보 탐색: 남은 곳 E26,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:38 |
| A2-14 | 첫 방문은 언제나 b0이고 k도 이력에서 추정한다. S 사전을 쓰면 큰 인증서 첫 방문의 1 RTT를 살릴 수 있다 | 재현만 / open E27,E28,L6,O4 | DROP | 새 후보 탐색: 남은 곳 E27,E28,L6,O4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:39 |
| A2-15 | S_bigcert 2↔15% 일정은 두 층의 최적 행동이 같아 적응의 가치를 원리적으로 보일 수 없다 | 재현만 / open R2 | DROP | 봉인 측정을 안 한다(D3). H4 해석 단서 BL-05 | findings/FINDINGS_INDEX.md:40 |
| A2-16 | 학습 시험과 적응 벤치가 폐루프 고착과 감시 비용을 볼 수 없다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(W1) | findings/FINDINGS_INDEX.md:41 |
| A2-17 | 15% 층 J3 과소예측(+7~8 ms)을 계급 조건부로 나누면 실패 계급 비용과 사후 지연으로 설명된다 | 넘김-진행가능 / open E8,E9,J1,J2,J3,J4 | DROP | 새 후보 탐색: 남은 곳 E8,E9,J1,J2,J3,J4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:42 |
| A2r1-01 | 사건 라벨의 기준선 오염: 손실이 높을수록 2-RTT를 사건으로 세지 못한다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(L2) | findings/FINDINGS_INDEX.md:43 |
| A2r1-02 | 연결 하나가 사후분포에 주는 정보: 1비트 사건은 보호 행동에서 사실상 0이고 C1 데이터그램 계수가 그 공백을 메운다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(L1) | findings/FINDINGS_INDEX.md:44 |
| A2r1-03 | 고착 기제를 model-world에서 재현하고 원인을 나눴다: 절반은 감시층, 나머지는 정보 부족과 사전분포 | 재현만 / open E8,L3,L4 | DROP | 새 후보 탐색: 남은 곳 E8,L3,L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:45 |
| A2r1-04 | 잔차 중앙값(평균) 차이 감시는 통계량이 틀렸다: 두 봉우리에서 오경보, 한 행동만 쓰면 눈이 멀고, 실패를 못 본다 | 넘김-진행가능 / open E8,L3 | DROP | 새 후보 탐색: 남은 곳 E8,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:46 |
| A2r1-05 | 측정 안 된 v3.2-dev의 학습층 변경 두 가지: predict_step은 도움이 되고 감시층 변경은 model-world에서 오히려 나쁘다 | 넘김-진행가능 / open E8,L3,L4 | DROP | 새 후보 탐색: 남은 곳 E8,L3,L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:47 |
| A2r1-06 | 0% 손실 과보호는 비용 비대칭의 합리적 결과가 아니라 흡수 상태다: 정보 없는 관측과 균등 재주입이 사후를 사전 근처에 묶는다 | 넘김-진행가능 / open L4,O1 | DROP | 새 후보 탐색: 남은 곳 L4,O1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:48 |
| A2r1-07 | 균등 재주입 사전과 빠른 hazard가 높은 손실 쪽 꼬리를 늘 남겨, 교차점 근처의 결정을 꼬리가 정한다 | 기록 없음 / open L4 | DROP | 새 후보 탐색: 남은 곳 L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:49 |
| A2r1-08 | 16번째마다 재평가는 고정 비율 탐색이고, Thompson sampling은 대부분의 조건에서 더 나쁘다 | 넘김-진행가능 / open E8,L3 | DROP | 새 후보 탐색: 남은 곳 E8,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:50 |
| A2r1-09 | 목적식에 바이트 값이 없다: J_TIE 0.01 ms 동률창 안에서만 바이트를 따져 1 ms 미만 이득에 1.3 KB를 산다 | 기록 없음 / open O1 | DROP | 새 후보 탐색: 남은 곳 O1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:51 |
| A2r1-10 | 서버 바이트 추정이 사건 연결을 버려서, 인증서가 커지면 교착되고 로드밸런서 혼합에서는 손실로 오인한다 | 넘김-진행가능 / open E11,L5 | DROP | 새 후보 탐색: 남은 곳 E11,L5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:52 |
| A2r1-11 | 손실이 아닌 지연도 c2s 손실로 배운다: 서버→클라이언트 손실, RTT 흔들림, 만료되지 않는 min RTT | 넘김-진행가능 / open E26,O3 | DROP | 새 후보 탐색: 남은 곳 E26,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:53 |
| A2r1-12 | 콜드 첫 방문: big-cert는 첫 연결마다 39 ms를 잃고, 둘째 연결부터는 균등 손실 사전 때문에 작은 인증서에도 5.3 KB를 보낸다 | 넘김-진행가능 / open L6 | DROP | 새 후보 탐색: 남은 곳 L6 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:54 |
| A2r1-13 | H4는 고른 조건에서 원리상 통과할 수 없다: 적응의 최대 이득이 하네스 편향 상한보다 작다 | 기록 없음 / open R2 | DROP | 봉인 측정을 안 한다(D3). H4 해석 단서 BL-05 | findings/FINDINGS_INDEX.md:55 |
| A2r1-14 | 적응 벤치와 단위시험이 실제로 깨진 체계를 시험하지 않는다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(W1) | findings/FINDINGS_INDEX.md:56 |
| A2r1-15 | 고정 EPS=0.01은 관측된 오탐보다 훨씬 크고, 정보가 적은 행동에서 남은 정보까지 지운다 | 넘김-진행가능 / open E7 | DROP | 새 후보 탐색: 남은 곳 E7 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:57 |
| A3-01 | RTT 200 셀에서 모든 연결이 기본 PTO(200 ms)로 첫 비행을 재전송하고, RTT 표본이 사라지며, v3 는 패리티를 한 벌 더 보낸… | 넘김-진행가능 / open J4 | DROP | 새 후보 탐색: 남은 곳 J4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:58 |
| A3-02 | 학습은 연결당 1비트만 쓰고, 이미 손에 있는 데이터그램 단위 도착 증거를 버린다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(L1,T4) | findings/FINDINGS_INDEX.md:59 |
| A3-03 | decodeConn 은 데이터그램마다 모든 비행 기록 x recent x k 를 전역 잠금 아래에서 훑는다(배포 시 DoS 와 확장성 문제) | 반영 | DROP | 반영: 맡은 과제가 모두 done(T5) | findings/FINDINGS_INDEX.md:60 |
| A3-04 | v3.2/v3.3 Go 는 10-07 수정이 빠진 gen-2 복호기와 정책을 품고 있고, H1 기준 바이너리의 소스는 고정돼 있지 않다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S4) | findings/FINDINGS_INDEX.md:61 |
| A3-05 | 패리티 크기가 무작위 DCID 길이에 따라 34~46 B 흔들리는데, 모형은 39 B 상수로 절벽을 가른다 | 넘김-진행가능 / open E13,J7 | FINAL-SHOULD | E38 범위만. BL-21 | findings/FINDINGS_INDEX.md:62 |
| A3-06 | 재전송 비행과 이후 비행의 패리티가 비용 모형과 바이트 집계에서 빠져 있다 | 재현만 / open E19,E29,E30,J3,J4 | DROP | 새 후보 탐색: 남은 곳 E19,E29,E30,J3,J4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:63 |
| A3-07 | 무제한 업링크 셀의 1-RTT 는 이 호스트에서 잰 경주표에 걸려 있다 | 넘김-진행가능 / open E22,E35,J8,O2,X3 | FINAL-SHOULD | X3 경주표 oob 대 basic. 나머지는 DROP. BL-18 | findings/FINDINGS_INDEX.md:64 |
| A3-08 | connAcctCap=4096 에 축출이 없어, 서버 프로세스가 연결 4096개를 넘기면 연결별 회계와 C1 회신이 조용히 멈춘다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T5) | findings/FINDINGS_INDEX.md:65 |
| A3-09 | 가짜 Initial 부채널은 인증이 없고, 클라이언트는 출발지와 DCID 를 확인하지 않는다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T5) | findings/FINDINGS_INDEX.md:66 |
| A3-10 | 테스트베드에서 오라클인 입력과, 실제 클라이언트가 그것을 추정하는 방법 | 넘김-진행가능 / open E22,E27,E28,E33,E35,J8,O2,O4,X2 | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 X2로 오입력 효과만 잰다. BL-19 | findings/FINDINGS_INDEX.md:67 |
| A3-11 | 신용은 서버 변경이 필요 없지만 '복호 전 상태 생성'에 기대고, 복구는 shim 이 필요하며, Retry 와 혼잡 제어에서 어긋난다 | 넘김-진행가능 / open E31,E32,M4,X7 | DROP | 새 후보 탐색: 남은 곳 E31,E32,M4,X7 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:68 |
| A3-12 | parity gate 는 정책 핵심만 덮고, 캐시층, 와이어 실현, 복호 의미는 덮지 않는다. gen33 지문은 늘 실패하고, 비트 일치는 am… | 넘김-진행가능 / open G2 | FINAL-MUST | G2로 답한다. BL-06 | findings/FINDINGS_INDEX.md:69 |
| A3-13 | RTT 신호: v3 는 역사적 최솟값을 쓰고, 연결별 표본에는 클라이언트 자신의 선행 패리티 대기열이 섞인다 | 넘김-진행가능 / open E25,E26,O3 | DROP | 새 후보 탐색: 남은 곳 E25,E26,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:70 |
| A3-14 | 비행 경계가 300 us 타이머나 외부에서 준 expect-k 에 달려 있고, 그 대기는 v3 모형에 없다 | 넘김-진행가능 / open T7,X3 | DROP | 효과 분리 안 함. 300 us 타이머는 BL-05 한계. T7 표에 대기 시간만 기록 | findings/FINDINGS_INDEX.md:71 |
| A3-15 | C1 구현에 남은 구멍: 복원된 Handshake 는 회신을 만들지 못하고, 원시 계수는 여전히 재전송을 센다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T4) | findings/FINDINGS_INDEX.md:72 |
| A4-01 | 관측 server_bytes 를 유효 s0·c 식에 넣는 n_need 산출이 1-RTT 문턱을 81~395 B 낮게 잡는다 (gen-2 Go b… | 재현만 / open E11,L5,R3 | FINAL-SHOULD | L5 DROP. n_need 오차는 지도와 BL-05에. BL-15 | findings/FINDINGS_INDEX.md:73 |
| A4-02 | 패리티 크기 모형 W+39+6k 가 CID 길이 변동과 서버 1452 B 수신 버퍼 잘림을 무시하고, 경계 후보는 여유 0 B 로 만들어진다 | 넘김-진행가능 / open E13,J7 | FINAL-SHOULD | E38 범위만. BL-21 | findings/FINDINGS_INDEX.md:74 |
| A4-03 | v3.1 의 A_pre(41(k-1) B)가 상속한 경계 생성기 delta_min·_combo_deltas 에 빠져 k=2·대역 제한에서 pad… | 넘김-교착 / open J6 | DROP | 새 후보 탐색: 남은 곳 J6 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:75 |
| A4-04 | 양자 모형 A(B)=ceil(3B/P)·P 는 quic-go 의 규격 위반 게이트와 P=1280 에서만 맞는다: 서버 회계 모드와 P 를 매개변… | 넘김-진행가능 / open E33,E35,J8 | DROP | 새 후보 탐색: 남은 곳 E33,E35,J8 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:76 |
| A4-05 | 실패 가지 상수(T_PTO 200.86, T_ACK 1.125·RTT+1.424, PTO_S 3·RTT)는 대역 무제한·작은 cert 에서만 쟀… | 넘김-진행가능 / open E30,J2,J3 | DROP | 새 후보 탐색: 남은 곳 E30,J2,J3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:77 |
| A4-06 | J 에 바이트 가격이 없어 J_TIE_MS=0.01 ms 가 사실상의 교환비가 된다: pad 문턱 p* 는 J_TIE 에 정확히 비례하고 명세의… | 기록 없음 / open O1 | DROP | 새 후보 탐색: 남은 곳 O1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:78 |
| A4-07 | gen-2 추정기(Jeffreys, 감쇠 0.99, 비용에 따라 늘어나는 탐색 주기)는 lossless 에서 1,600 연결 뒤에도 p̂ 0.0… | 기록 없음 / open L4 | DROP | 새 후보 탐색: 남은 곳 L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:79 |
| A4-08 | 버스트 모형은 실측 결정에 쓰인 적이 없다: gen-2 Go 는 burst=1.0(=Bernoulli), v3 는 i.i.d. 전용이라 버스트 … | 넘김-진행가능 / open E23,J3,J5 | DROP | 새 후보 탐색: 남은 곳 E23,J3,J5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:80 |
| A4-09 | race_win_prob 표는 한 기계, cert 9000, 부하 없음에서 잰 서버 결정 지연 분포다 | 넘김-진행가능 / open O2,X3 | FINAL-SHOULD | A1-16과 같다. BL-18 | findings/FINDINGS_INDEX.md:81 |
| A4-10 | codec 수학은 맞지만 Python 형식은 테스트베드와 다르고, 신용 전용 lead 패리티는 쓰이지 않는 RS 행을 계산한다 | 넘김-진행가능 / open R3 | FINAL-SHOULD | codec 형식 차이를 지도에 적는다. BL-15 | findings/FINDINGS_INDEX.md:82 |
| A4-11 | 최종 보고서에 인용될 수 있는 gen-2 수치 여러 개가 현재 코드·결과 파일과 어긋난다 | 반영 | FINAL-MUST | A1이 목록만 만들었다. BL-02 | findings/FINDINGS_INDEX.md:83 |
| A5-01 | NEW_TOKEN·Retry 기준선이 없어 재방문 조건에서 얻은 이득의 범위가 정해지지 않았다 | 넘김-진행가능 / open X4 | FINAL-SHOULD | X4. BL-20 | findings/FINDINGS_INDEX.md:84 |
| A5-02 | 핵심 주장(같은 바이트를 패딩 대신 패리티로)을 같은 바이트·같은 위치에서 직접 잰 측정이 없다 | 넘김-진행가능 / open X1 | FINAL-MUST | X1으로 답한다. BL-08 | findings/FINDINGS_INDEX.md:85 |
| A5-03 | 확증 조건 대부분이 v3.1 설계에 쓴 조건이고, 보류 셀 4개는 RTT 120 한 갈래이자 사실상 두 체제뿐이다 | 기록 없음 / open R2 | DROP | 봉인 측정을 안 한다(D3). 해석 단서만 BL-05 | findings/FINDINGS_INDEX.md:86 |
| A5-04 | H2는 단위 수, 비열등 한계, 하네스 한계가 서로 맞지 않아 잡음이 큰 셀에서 구조적으로 통과할 수 없다 | 기록 없음 / open R2 | DROP | 봉인 측정을 안 한다(D3). H2 해석 단서 BL-05 | findings/FINDINGS_INDEX.md:87 |
| A5-05 | H3 예측은 gen-2가 정확한 손실률에서 J3 최적을 고른다고 가정해, 실패가 무엇을 뜻하는지 읽을 수 없다 | 기록 없음 / open R2 | DROP | 봉인 측정을 안 한다(D3). H3 해석 단서 BL-05 | findings/FINDINGS_INDEX.md:88 |
| A5-06 | H4 기준이 조건을 아는 고정 팔이고 v3.1은 사실상 m=4 고정 정책이어서, 설계상 '적응 기여'를 물을 수 없었다 | 재현만 / open R2,X6 | FINAL-SHOULD | X6 전역 고정 팔. BL-16 | findings/FINDINGS_INDEX.md:89 |
| A5-07 | 동결 gen-2 클라이언트의 패리티·바이트 계수가 서버보다 크게 적어, 클라이언트 계수로 낸 바이트 비교는 쓸 수 없다 | 재현만 / open T7 | FINAL-MUST | T7이 서버 계수로 집계. BL-07 | findings/FINDINGS_INDEX.md:90 |
| A5-08 | 정책에 실제 업링크 대역을 알려 주는 오라클 입력에 v3.1의 핵심 수정이 기대고 있다 | 넘김-진행가능 / open E22,O2,X2 | FINAL-SHOULD | X2. O2는 DROP. BL-19 | findings/FINDINGS_INDEX.md:91 |
| A5-09 | netem의 손실·대역 의미와 손실 모형이 여러 데이터그램으로 된 첫 비행에 유리한 쪽으로 단순하다 | 재현만 / open X5 | DROP | 측정 생략: X5 사유. BL-05 | findings/FINDINGS_INDEX.md:92 |
| A5-10 | auto 팔의 단위는 독립 반복이 아니다: 한 조건의 구간들이 캐시 궤적 하나에 묶여 있다 | 기록 없음 / open R2,T7 | FINAL-MUST | T7 독립 궤적 4개. BL-07 | findings/FINDINGS_INDEX.md:93 |
| A5-11 | 같은 블록 안 짝짓기는 시간 표류를 지우지만, gen-2 p3는 아직 순차 팔이라 표류가 팔 차이로 들어간다 | 재현만 / open T7 | FINAL-MUST | T7 교대 측정. BL-07 | findings/FINDINGS_INDEX.md:94 |
| A5-12 | 볼트 정본 콜아웃과 옛 문서에 지금 자료와 어긋나는 주장이 남아 있다 (안전한 주장과 위험한 주장 목록) | 반영 | FINAL-MUST | A1이 목록만 만들었다. BL-02 | findings/FINDINGS_INDEX.md:95 |
| A5-13 | RFC를 정확히 지키는 다른 스택에서 '패리티가 신용을 산다'를 잰 적이 없다 | 기록 없음 / open X7 | DROP | 측정 불가: X7 사유. RFC 정확 스택 미측정은 BL-05 | findings/FINDINGS_INDEX.md:96 |
| A5-14 | 합성 인증서, Go ClientHello, quic-go 한 판, 인증서 압축 없음이라 바이트 크기를 외삽할 근거가 약하다 | 재현만 / open R2 | DROP | 봉인 측정을 안 한다(D3). 크기 표는 REPORT_CLAIMS에 있다 | findings/FINDINGS_INDEX.md:97 |
| A5-15 | HCT와 1-RTT 분류 자체는 견고하다 (확인한 것) | 기록 없음 / open T7 | FINAL-MUST | T7 판정 분류 유지. BL-07 | findings/FINDINGS_INDEX.md:98 |
| A5-16 | v3.2-dev는 네트워크에서 한 번도 재지 않았고, A_pre 41 B의 일반화도 측정되지 않았다 | 기록 없음 / open X3,X6 | FINAL-SHOULD | X6·X3. BL-16과 BL-18 | findings/FINDINGS_INDEX.md:99 |
| A5-17 | 남은 기간 측정 계획: 정보량/시간 순위와 표본 크기 | 기록 없음 / open X6 | FINAL-SHOULD | 측정 순서 근거. BL-16 | findings/FINDINGS_INDEX.md:100 |
| A6-01 | 새 Windows clone 에서 v3 봉인 해시 42/45개가 줄 끝 변환으로 깨진다 | 반영 | FINAL-MUST | 반영으로 집계되지만 hygiene 브랜치에만 있다. main clone 봉인 6/92(직접). BL-01 | findings/FINDINGS_INDEX.md:101 |
| A6-02 | 확증 측정의 원자료, 봉인 바이너리, 사전등록 문서가 노트북 한 대에만 있다 | 반영 | USER | 원자료가 노트북 한 대에만 있다. BL-35 | findings/FINDINGS_INDEX.md:102 |
| A6-03 | 10-07 gen-2 검토 수정 10건이 v3 세대 어디에도 없다(gen-2 가 세 판으로 갈림) | 반영 | DROP | 반영: 맡은 과제가 모두 done(S4) | findings/FINDINGS_INDEX.md:103 |
| A6-04 | WSL 빌드 출력 경로가 세대끼리 겹쳐 봉인 바이너리가 덮어써질 수 있고, 다시 빌드해도 같은 바이너리가 안 나온다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S1) | findings/FINDINGS_INDEX.md:104 |
| A6-05 | 폴더를 복사하고 이름만 바꾼 자리에서 실제 오작동이 난다(gen33 대조 실패, 다른 세대를 가리키는 스크립트) | 반영 | DROP | 반영: 맡은 과제가 모두 done(S3) | findings/FINDINGS_INDEX.md:105 |
| A6-06 | 새 기계에서 결과를 한 번에 재현하거나 확인하는 명령이 없다 | 넘김-진행가능 / open E36 | FINAL-MUST | BL-12와 BL-10 | findings/FINDINGS_INDEX.md:106 |
| A6-07 | 세대를 폴더 사본으로 관리해 같은 코드가 6벌이고 git 은 사후 덤프가 됐다(통합 계획) | 반영 | FINAL-SHOULD | 태그 4개가 로컬에만 있다. BL-01 | findings/FINDINGS_INDEX.md:107 |
| A6-08 | gen-2 파이프라인 지문이 지나치게 엄격하고, 원인과 상관없이 '코드가 바뀜'으로만 보고한다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:108 |
| A6-09 | 테스트: 기본 명령이 빨갛고, gen-2 Go 테스트는 어디서도 안 돌며, CI 가 없다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:109 |
| A6-10 | 테스트베드 인증서를 서버마다 무작위로 만들어 팔 사이에 고정된 1~3 B 차이가 생긴다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T1) | findings/FINDINGS_INDEX.md:110 |
| A6-11 | README 와 명세가 커밋된 자료·코드보다 뒤처져 있다 | 반영 | FINAL-MUST | main README 낡음. BL-01과 BL-02 | findings/FINDINGS_INDEX.md:111 |
| A6-12 | 큰 단일 파일, 러너마다 다시 쓴 테스트베드 제어 코드, 설명이 거의 없는 v3 핵심 코드 | 넘김-진행가능 / open R3,T7 | FINAL-MUST | T7 lib 분리는 필요한 만큼만. 지도는 BL-15. BL-07 | findings/FINDINGS_INDEX.md:112 |
| A6-13 | 최신 세대 폴더의 약 90% 가 물려받은 코드이고, v3.2 를 잴 러너는 없다 | 기록 없음 / open T7 | FINAL-MUST | v3.3 러너 부재. BL-07 | findings/FINDINGS_INDEX.md:113 |
| A6-14 | Go 의존성 고정: 지금 바이너리는 v0.61.0 이지만, 고정을 우회하는 빌드 경로가 6주 동안 main 에 있었다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:114 |
| A6-15 | Windows·WSL·사용자 경로에 묶인 코드와 봉인 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:115 |
| A6-16 | 위생: 시험용 개인키 30개, 캐시 폴더, 개인 이메일, .gitignore 에 안 적힌 제외 규칙 | 넘김-진행가능 / open E37 | FINAL-SHOULD | E37. BL-22 | findings/FINDINGS_INDEX.md:116 |
| A6r1-01 | 봉인된 v3.1 실측의 원자료와 기준 바이너리가 노트북 한 대에만 있다 | 반영 | USER | A6-02와 같다. BL-35 | findings/FINDINGS_INDEX.md:117 |
| A6r1-02 | 동결 gen-2 기준 바이너리는 gen-2 빌드 한 번에 덮이고, 다른 계정에서는 같은 해시로 다시 만들 수 없다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S1) | findings/FINDINGS_INDEX.md:118 |
| A6r1-03 | Windows 기본 Git 설정으로 새로 clone하면 봉인 해시 42/45와 소스 지문이 깨진다 | 반영 | FINAL-MUST | A6-01과 같은 원인. BL-01 | findings/FINDINGS_INDEX.md:119 |
| A6r1-04 | 10월 7일 gen-2 수정 10건이 v3.0~v3.3에 없고, v3 비교의 gen-2 팔은 수정 전 코드다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S4) | findings/FINDINGS_INDEX.md:120 |
| A6r1-05 | 세대 사본이 이전 세대의 경로와 이름을 박고 있어 엉뚱한 세대를 검사하거나 실행한다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S3) | findings/FINDINGS_INDEX.md:121 |
| A6r1-06 | Python 기준 구현과 Go 실행 구현을 매번 두 번 고친다: 알고리즘 개선의 가장 큰 비용 | 넘김-진행가능 / open T7 | DROP | 하지 않음: 검증자 doubtful. Python 제어기 팔 없이 auto3 경로를 잰다 | findings/FINDINGS_INDEX.md:122 |
| A6r1-07 | 검사가 실행 경로와 CI에 연결되지 않았다: gen-2 Go 검사 41개 미호출, gen32 전체 pytest 29개 실패, CI 없음 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:123 |
| A6r1-08 | 세대별 전체 복사 폴더를 태그 기반 단일 저장소로 통합하는 계획 | 반영 | FINAL-SHOULD | A6-07과 같다. 통합 자체는 안 한다. BL-01 | findings/FINDINGS_INDEX.md:124 |
| A6r1-09 | 지문이 지나치게 엄격하다: 환경 변화가 '코드가 바뀜'으로 보고된다(09-15 지적, 아직 안 고침) | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:125 |
| A6r1-10 | 서버 인증서 크기가 팔(arm)마다 다르다: makeCert가 비결정적이다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T1) | findings/FINDINGS_INDEX.md:126 |
| A6r1-11 | README와 인계 문서가 실제 상태와 다르다 | 반영 | FINAL-MUST | A6-11과 같다. BL-01과 BL-02 | findings/FINDINGS_INDEX.md:127 |
| A6r1-12 | 큰 결과 파일 때문에 HEAD가 무겁고 GitHub 100 MB 한도까지 여유가 적다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S5) | findings/FINDINGS_INDEX.md:128 |
| A6r1-13 | 새 기계에서 한 명령으로 재현하는 길이 없고, Windows·WSL 설정에 묶여 있다 | 넘김-진행가능 / open E36 | FINAL-MUST | BL-12와 BL-10 | findings/FINDINGS_INDEX.md:129 |
| A6r1-14 | pq_afec_next의 고유 작업이 어떤 저장소에도 없다 | 반영 | FINAL-SHOULD | A6-M05와 같다. BL-01 | findings/FINDINGS_INDEX.md:130 |
| A6r1-15 | v3 실행기들이 같은 함수를 복사해 쓰고, 단일 함수와 파일이 지나치게 크다 | 기록 없음 / open T7 | FINAL-MUST | T7 공용 함수. BL-07 | findings/FINDINGS_INDEX.md:131 |
| A6r1-16 | v3 핵심 코드와 수식 문서를 잇는 추적 경로가 없다 | 기록 없음 / open R3 | FINAL-SHOULD | BL-15 | findings/FINDINGS_INDEX.md:132 |
| A6r1-17 | 위생: 개인키는 안전하지만 사용자 경로, 잔재 스크립트, 이름 충돌이 남아 있다 | 넘김-진행가능 / open E37 | FINAL-SHOULD | E37. BL-22 | findings/FINDINGS_INDEX.md:133 |
| A7-01 | 재방문은 TLS resumption과 NEW_TOKEN이 이미 덮는다: 테스트베드가 둘 다 끄고 잰 이득의 모집단을 다시 정의해야 한다 | 넘김-진행가능 / open X4 | FINAL-SHOULD | X4. BL-20 | findings/FINDINGS_INDEX.md:134 |
| A7-02 | 첫 방문 공백: 손실 상태는 접속망 키로, k는 로컬 설정에서, S는 모집단 prior로 분리한다 | 넘김-진행가능 / open L6 | DROP | 새 후보 탐색: 남은 곳 L6 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:135 |
| A7-03 | 목적지 캐시는 첫 비행 모양으로 드러나는 교차 연결 상태다: token, ticket과 같은 linkability 규칙이 필요하다 | 재현만 / open L6 | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 linkability 문단만 BL-05 | findings/FINDINGS_INDEX.md:136 |
| A7-04 | initial congestion window가 경쟁 병목이다: 헤드라인 셀은 32-packet 창을 쓰는 서버에서만 성립한다 | 넘김-진행가능 / open E35,J8,X8 | DROP | 측정 생략: X8 사유. IW 단서는 보고서에 있다 | findings/FINDINGS_INDEX.md:137 |
| A7-05 | 2025~2026 PQ 인증서는 MTC로 간다: S 격자를 예산 바로 위 띠로 다시 짜야 한다 | 넘김-진행가능 / open X1 | FINAL-MUST | X1 추가 셀. BL-08 | findings/FINDINGS_INDEX.md:138 |
| A7-06 | Certificate compression은 고전 체인에만 듣는다: 테스트베드의 고전 크기 셀을 실제 고전 체인으로 읽으면 과장이다 | 반영 | FINAL-MUST | REPORT_CLAIMS에 표가 있고 팀 문서 쪽 미반영. BL-02 | findings/FINDINGS_INDEX.md:139 |
| A7-07 | 중복 전송(Proactive) 기준선이 빠져 있다: 서버를 고치지 않아도 같은 신용과 복구를 준다 | 넘김-진행가능 / open X1 | FINAL-MUST | X1 dup 팔. BL-08 | findings/FINDINGS_INDEX.md:140 |
| A7-08 | Google quiche CHP1/CHP2: 산업계 스택에 '첫 비행을 패킷 단위로 부풀리는' 실험 옵션이 이미 있다 | 넘김-진행가능 / open X1 | FINAL-MUST | X1 k-inflate 팔. BL-08 | findings/FINDINGS_INDEX.md:141 |
| A7-09 | 서버마다 증폭 회계와 준수율이 다르다: A(B)를 서버 구현의 파라미터로 둬야 한다 | 넘김-진행가능 / open E33,J8 | DROP | 새 후보 탐색: 남은 곳 E33,J8 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:142 |
| A7-10 | 실패 비용 상수가 클라이언트 스택과 서버 ACK 정책을 따라간다: PTO 1 s면 최적 행동이 바뀐다 | 넘김-진행가능 / open E35,J8 | DROP | 새 후보 탐색: 남은 곳 E35,J8 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:143 |
| A7-11 | HCT 한 비트 학습이 보호 행동에 가려진다: partial monitoring 구조이고, C1 도착 수를 우도에 넣어야 한다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(L1) | findings/FINDINGS_INDEX.md:144 |
| A7-12 | 재설정 prior가 비관적이다: BOCPD의 변화 후 prior를 모집단 정보로 바꿔야 한다 | 기록 없음 / open L4 | DROP | 새 후보 탐색: 남은 곳 L4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:145 |
| A7-13 | 자기 창 median 기준선은 두 봉우리 HCT에서 편향된다: 1-RTT 봉우리를 추정하는 robust 기준선이 필요하다 | 넘김-진행가능 / open E7,J2,O3 | DROP | 새 후보 탐색: 남은 곳 E7,J2,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:146 |
| A7-14 | 감시층을 categorical CUSUM으로: 지금 규칙은 0.5·RTT 칼날 위에 있다 | 넘김-진행가능 / open E8,J1,J2,L3 | DROP | 새 후보 탐색: 남은 곳 E8,J1,J2,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:147 |
| A7-15 | burst 손실: iid 모형은 실패를 과소예측하고, netem gemodel은 시간 상관을 못 만든다 | 재현만 / open E23,E24,J5 | DROP | 새 후보 탐색: 남은 곳 E23,E24,J5 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:148 |
| A7-16 | 1/16 강제 재평가 대신 Thompson sampling이나 IDS | 넘김-진행가능 / open E8,L3 | DROP | 새 후보 탐색: 남은 곳 E8,L3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:149 |
| A7-17 | lead 패리티를 decoding deadline으로 복구에도 쓴다: MDS의 아무 k개 성질을 살린다 | 넘김-진행가능 / open E14,E15,E16,M1 | DROP | 새 후보 탐색: 남은 곳 E14,E15,E16,M1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:150 |
| A7-18 | 첫 비행 FEC는 협상 전이라 서버 지원을 미리 알 수단이 필요하다 | 넘김-교착 / open M4 | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 server_support_signal.md 메모로 충분. 넘김-교착은 이 표로 닫는다 | findings/FINDINGS_INDEX.md:151 |
| A7-19 | 하향 손실과 서버 재전송 예산이 측정 밖에 있다 | 넘김-진행가능 / open E34,E35,X5 | DROP | 측정 생략: X5 사유. BL-05 | findings/FINDINGS_INDEX.md:152 |
| A7-20 | Retry 서버에서는 신용 레버가 쓸모없다: 패리티 전략을 Retry에 맞춰 조정해야 한다 | 넘김-진행가능 / open E31,E32,M4 | DROP | 새 후보 탐색: 남은 곳 E31,E32,M4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:153 |
| A7-21 | 패리티 신용의 규범적 근거는 RFC 9000 8.1절이다: 다만 서버 쪽 steering 뒤에서는 깨질 수 있다 | 재현만 / open X7 | DROP | 측정 불가: X7 사유. 조건 문장은 REPORT_CLAIMS에 있다 | findings/FINDINGS_INDEX.md:154 |
| A7-22 | TTLB 반론에 답하려면 이득을 중앙값 연결 시간 대비 비율로도 제시해야 한다 | 재현만 / open T7,X6 | FINAL-MUST | T7 TTLB 보조 지표. BL-07 | findings/FINDINGS_INDEX.md:155 |
| A8-01 | NEW_TOKEN 토큰 하나로 증폭 한도가 통째로 꺼지는데, 테스트베드와 비교군에 토큰 경로가 없다 | 넘김-진행가능 / open E31,E32,M4,X4 | FINAL-SHOULD | X4. M4 쪽은 DROP. BL-20 | findings/FINDINGS_INDEX.md:156 |
| A8-02 | '신용과 복구는 한 패리티로 동시에 못 얻는다'는 전제가 quic-go 처리 순서와 맞지 않다: 선행 패리티를 보류했다가 쓰면 같은 바이트로 둘… | 넘김-진행가능 / open E15,M1 | DROP | 새 후보 탐색: 남은 곳 E15,M1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:157 |
| A8-03 | 증폭 회계의 정확한 규칙: 1-RTT 판정식은 quic-go와 정확히 맞지만, 그 일치가 quic-go 고유 동작에 기대고 있다 | 재현만 / open E34,E35,J3,J8 | DROP | 새 후보 탐색: 남은 곳 E34,E35,J3,J8 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:158 |
| A8-04 | 키가 아직 없는 Handshake형 패킷은 큐에 들어갔다가 재처리되며 바이트가 두 번 세진다: 신용 지렛대로 쓰면 안 되는 quic-go 결함 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T5) | findings/FINDINGS_INDEX.md:159 |
| A8-05 | 패리티 상한을 MTU 기준 1472 B로 걸었지만 quic-go 서버는 1452 B까지만 읽는다: 1453~1472 B 패리티는 잘려 복구 능력… | 넘김-진행가능 / open E13,J7 | DROP | 대체됨: 1452 B 상한은 v3.3.1-dev에 들어갔다. 경계 시험은 BL-21 | findings/FINDINGS_INDEX.md:160 |
| A8-06 | 41 B 사전 ACK(A_pre)는 소스와 실측 모두 맞다. 다만 s_hat에 같은 41 B가 들어 있어 두 번 청구되고, 클라이언트가 피할 길… | 넘김-진행가능 / open E11,J6,L5,O4,R3 | FINAL-SHOULD | A_pre 이중 청구는 X3로 재고 지도에 적는다. BL-18과 BL-15 | findings/FINDINGS_INDEX.md:161 |
| A8-07 | 정책 RTT는 클라이언트 자신의 업링크 직렬화로 부푼 quic-go MinRTT다: RTT 200 조건에서 +11.3 ms이고, 그 부풂의 기울… | 재현만 / open E22,E25,E26,O2,O3 | DROP | 새 후보 탐색: 남은 곳 E22,E25,E26,O2,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:162 |
| A8-08 | 15% big-cert에서 J3가 6.84 ms 낮게 예측한 원인 후보 셋: 상수 처리 지연, 부푼 RTT로 도는 quic-go 타이머, 모형에… | 재현만 / open E25,E26,E9,J1,J2,J3,J4,O3 | DROP | 새 후보 탐색: 남은 곳 E25,E26,E9,J1,J2,J3,J4,O3 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:163 |
| A8-09 | quic-go Tracer가 주는 패킷 단위 ACK·RTT·손실 이벤트로, 명목 2-RTT 행동을 고른 동안에도 손실률을 계속 배울 수 있다(H… | 넘김-진행가능 / open O3,T7 | FINAL-MUST | T7 tracer 기록 사용. O3 쪽은 DROP. BL-07 | findings/FINDINGS_INDEX.md:164 |
| A8-10 | RTT 200 조건의 모든 연결에서 클라이언트가 200 ms PTO로 ClientHello를 헛재전송한다(탐침 2장, 각 W 바이트) | 넘김-진행가능 / open J4 | DROP | 새 후보 탐색: 남은 곳 J4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:165 |
| A8-11 | 1280(P_SERVER)과 k는 서버 설정, 난수 CID, KEM에 묶인 값이다: P는 클라이언트가 첫 서버 데이터그램 길이로 바로 잴 수 있… | 넘김-진행가능 / open E27,E28,E33,J8,O4 | DROP | 새 후보 탐색: 남은 곳 E27,E28,E33,J8,O4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:166 |
| A8-12 | Retry 경로는 테스트베드에서 한 번도 안 열렸다: Retry가 걸리면 첫 비행 패리티는 전부 낭비되고 연결 전 도착한 패리티마다 Retry가… | 넘김-진행가능 / open E31,E32,M4 | DROP | 새 후보 탐색: 남은 곳 E31,E32,M4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:167 |
| A1-M01 | 측정한 u>0 셀에서는 한 패리티가 신용과 복구를 동시에 하지 않는다. 선행 몫은 패딩과 같다 | 재현만 / open X1 | FINAL-MUST | X1으로 답한다. BL-08 | findings/FINDINGS_INDEX.md:173 |
| A1-M02 | 선행 패리티를 복구에도 쓰는 지연 신용 방식이 빠져 있다 | 넘김-진행가능 / open E14,E16,M1 | DROP | 새 후보 탐색: 남은 곳 E14,E16,M1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:174 |
| A1-M03 | J3 탐욕 선택이 정보 없는 행동을 골라 무손실에서도 사후분포가 내려오지 않는다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(L1) | findings/FINDINGS_INDEX.md:175 |
| A6-M01 | --report-only 는 순수 재계산이 아니라 현재 환경을 다시 검증하고 커밋된 판정 파일을 덮어쓴다 | 재현만 / open E1,E36 | FINAL-MUST | BL-12 | findings/FINDINGS_INDEX.md:176 |
| A6-M02 | RTT 200 셀에서만 연결별 경로 RTT 측정이 99% 실패한다 | 넘김-진행가능 / open J4 | DROP | 새 후보 탐색: 남은 곳 J4 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:177 |
| A6-M03 | 팔마다 서버 바이너리가 달라 서버 쪽 코드 차이가 팔 비교에 섞일 수 있는데 이를 막는 검사가 없다 | 기록 없음 / open T7 | FINAL-MUST | T7 서버 바이너리 경고. BL-07 | findings/FINDINGS_INDEX.md:178 |
| A6-M04 | 봉인 세대 폴더가 쓰기 가능한 작업 폴더라 일상 작업과 감사 제안이 봉인 또는 기록 파일을 바꾼다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S1) | findings/FINDINGS_INDEX.md:179 |
| A6-M05 | 최신 작업본 gen33 과 pq_afec_next 는 git 에 전혀 없다 | 반영 | FINAL-SHOULD | next가 로컬 브랜치에만 있다. BL-01 | findings/FINDINGS_INDEX.md:180 |
| A6-M06 | 비교 기준 gen-2 바이너리의 출처 증거가 다음 빌드 한 번에 사라진다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(S1) | findings/FINDINGS_INDEX.md:181 |
| A7-M01 | J3에 바이트 가격이 없다: 손실을 정확히 알아도 과보호한다 | 기록 없음 / open O1 | DROP | 새 후보 탐색: 남은 곳 O1 전부 DROP. 결함은 BL-05 | findings/FINDINGS_INDEX.md:182 |
| A7-M02 | lead 패리티 신용은 '복호 못 하는 첫 Initial로도 연결을 만드는' quic-go 동작에 기댄다 | 넘김-진행가능 / open E33,E35,J8,X7 | DROP | 측정 불가: X7 사유. BL-05 | findings/FINDINGS_INDEX.md:183 |
| A7-M03 | p̄는 손실 추정치가 아니다: 저널에서 2%와 15%를 구별하지 못하고 burst에서는 격자 끝에 붙는다 | 재현만 / open R1 | FINAL-MUST | 볼트·문서의 p̄ 서술 정정이 남았다. BL-02와 BL-24 | findings/FINDINGS_INDEX.md:184 |
| A7-M04 | 손실된 데이터그램이 업링크 시간을 쓰지 않는다: 테스트베드와 모형이 같은 낙관을 공유한다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(W0) | findings/FINDINGS_INDEX.md:185 |
| Q-01 | 뒤따르는 패리티 신용 항이 검증도 반증도 안 됐다(gen-2 p17·p18 부호 반대, 판정에 팔당 8,544~12,404판 필요) | 기록 없음 / open X3 | FINAL-SHOULD | X3 뒤 패리티 신용. 표본 부족이면 판정 불능으로. BL-18 | findings/EXTRA_SOURCES.md:7 |
| Q-02 | gen-2 p18 검사 4의 자가 거꾸로 되어 있다 | 반영 | FINAL-MUST | 상태 주석 미반영. BL-02 | findings/EXTRA_SOURCES.md:8 |
| Q-03 | 판정 자(허용 오차)가 하네스 자기 표류보다 곱다: p16 자 0.25 ms 대 표류 0.694 ms | 기록 없음 / open R2,T7 | FINAL-MUST | T7 판정 자 경고. BL-07 | findings/EXTRA_SOURCES.md:9 |
| Q-04 | 허용집합 자 1 ms가 오차막대보다 곱다: p11 신뢰반폭 2.42 ms, p17 자리 효과 6.12 ms. 원인은 표본이 아니라 팔을 순차로 잰 것 | 기록 없음 / open R2,T7 | FINAL-MUST | T7 교대 측정. BL-07 | findings/EXTRA_SOURCES.md:10 |
| Q-05 | 원리적 한계를 보고서에 적어야 한다: 폐루프가 실제로는 닫혀 있지 않음, k(비행 데이터그램 수) 제어 불가, 서버→클라이언트 방향 미보호 | 반영 | FINAL-MUST | 상태 주석 미반영. BL-02 | findings/EXTRA_SOURCES.md:11 |
| Q-06 | 측정 러너가 "판정은 붉지만 자료는 멀쩡"과 "아예 안 나옴"을 못 가르고, note 필드가 지문 밖이라 낡아도 무효화되지 않으며, 보고서 단계가 자동으로 안 돈다 | 기록 없음 / open T7 | FINAL-MUST | T7 상태 3값. BL-07 | findings/EXTRA_SOURCES.md:12 |
| Q-07 | 결과 파일을 덮어쓰기 전에 이전 판을 남기지 않는다 | 기록 없음 / open T7 | FINAL-MUST | T7 덮어쓰기 금지. BL-07 | findings/EXTRA_SOURCES.md:13 |
| Q-08 | 팀 문서가 낡았다: 다음 세션 인계.md(09-08 상태), "먼저 읽을 것"이 세 곳에서 다름, 보고서·파이프라인이 둘, 선행연구 대조.md·알고리즘 명세 v0.1·v0.2가 옛 방향, 변경보고 HTML 소스 없음 | 반영 | FINAL-MUST | 낡은 팀 문서 그대로. BL-02 | findings/EXTRA_SOURCES.md:14 |
| Q-09 | 보고서 「한계」에 아직 안 들어간 항목 | 반영 | FINAL-MUST | 상태 주석 미반영. BL-02 | findings/EXTRA_SOURCES.md:15 |
| Q-10 | PTO_SAMPLED_RTT_MULT = 3.0은 RFC 유도값이고 실측이 아니다. 재는 법: _probe_trecover.py에 -drop-initial k-1을 여러 RTT로 | 넘김-진행가능 / open J3,T7,X3 | FINAL-SHOULD | X3 PTO 배수. 못 재면 RFC 유도값으로 표시. BL-18 | findings/EXTRA_SOURCES.md:16 |
| Q-11 | 자체시험이 모두 자기 자신을 기준으로 잰다. DP 실패확률을 외부 문헌 닫힌형(Bolot Table 1, Boutremans 식 11)과 맞춰 본 적이 없다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(W0) | findings/EXTRA_SOURCES.md:17 |
| Q-12 | expected_rounds 독스트링의 모형/실측 비가 두 곳에서 다른 수(1.02~1.07 대 1.01~1.02), 212%는 산술도 틀림 | 기록 없음 / open R3 | FINAL-MUST | policy.py:1789에 212%가 남아 있다(직접). BL-13 | findings/EXTRA_SOURCES.md:18 |
| Q-13 | 명세는 Go 1.26.5인데 08-20 이후 실측은 모두 1.26.6 | 반영 | FINAL-MUST | 실제 정정 미반영. BL-02 | findings/EXTRA_SOURCES.md:19 |
| Q-14 | 팀 스크립트 run_v3.sh는 netem을 클라이언트 송신 쪽에만 건다(명세와 다름). 종합기술문서는 gemodel 5% 50%를 손실 5%로 적었는데 정상상태는 9.09% | 반영 | FINAL-MUST | 상태 주석 미반영. BL-02 | findings/EXTRA_SOURCES.md:20 |
| Q-15 | 서버 통계 unrecoverable_seen이 나중에 복구되는 비행까지 센다(m3 팔: 복구 30사건인데 unrecoverable 30). 이름이 오해를 부른다 | 반영 | DROP | 반영: 맡은 과제가 모두 done(T4) | findings/EXTRA_SOURCES.md:21 |
| Q-16 | 선행연구 대조.md의 틀린 문장 셋: A7 "클라이언트만 고쳐서 배포"(복구는 서버 decodeConn 필요), §4 #3 "연결 간 손실 캐시는 v2 결정 경로에 없다"(Go destCache가 있음), afec/rs.py 머리말의 MDS 설명(코드는 맞고 설명만 틀림) | 반영 | FINAL-MUST | 선행연구 대조.md:105 그대로(직접). BL-02 | findings/EXTRA_SOURCES.md:22 |
| Q-17 | 방향 전환 근거 "② 기각, PTO x25519 12.0% 대 ML-KEM 10.4%, z=0.79"는 워밍업이 분모에 섞인 팀 수집기 값이고 고친 수집기로 다시 잰 적이 없다. z는 어느 분모로도 재현 안 됨(그룹당 약 485연결일 때만). 유의차 없음은 기각이 아니다 | 재현만 / open X9 | FINAL-SHOULD | X9. BL-17 | findings/EXTRA_SOURCES.md:23 |
| Q-18 | C1 서버 피드백 설계.md의 "알려진 결함"(RxOrigN 재전송 계수) 상태 문장이 현재 코드와 다르다(클라이언트 CRC 대조가 바로잡음) | 반영 | FINAL-MUST | gen-2 C1 문서 문장 그대로. BL-02 | findings/EXTRA_SOURCES.md:24 |
| Q-19 | 봉인된 PROTOCOL_stage3.md 3행 상태 문장이 "초안"으로 남은 채 봉인됨. gen31이 물려받은 SEAL_stage0·2의 해시 불일치(v3.0에서 상속) | 반영 | FINAL-MUST | 봉인 문서는 못 고치므로 정오표로. BL-02 | findings/EXTRA_SOURCES.md:25 |
| Q-20 | R-E README 24행 "17단계 통과, 7단계 실패"는 최종 상태 18/6과 다르다 | 반영 | FINAL-MUST | main README 25행이 아직 17/7이다. BL-01 | findings/EXTRA_SOURCES.md:26 |
| Q-21 | 미결: 과제명(원제목 대 09-03 재작성본, 승인 기록 없음), 저장소 공개 여부(공개 시 서버명·인계 문서 제거 필요) | 기록 없음 / open R1 | USER | 과제명과 공개 여부. BL-33, BL-32 | findings/EXTRA_SOURCES.md:27 |
| Q-22 | gen-2 p15 검사 "평상시 선택이 pad(δ=1)"가 ips만 보고 통과한다(실제로는 m=1 패리티도 보냄). 검사 이름과 판정을 m_used 기준으로 | 재현만 / open O1 | FINAL-MUST | gen-2 동결이라 정오표로. O1은 DROP. BL-02 | findings/EXTRA_SOURCES.md:28 |
| Q-23 | v3.1 RESULT_stage3 「다음」 4항: 감시 통계, 명목 2-RTT 고착, 15% J3 과소예측, H 예측 정의 | 넘김-진행가능 / open E8,E9,J1,J2,L3,R2 | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 H 예측 정의는 BL-05 | findings/EXTRA_SOURCES.md:29 |

## 3. 11-01 감사 항목 (v33audit, VERIFY 절 판정 포함)

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| A-E1 | CI 초안의 Go 빌드 단계가 GitHub runner에서 실패할 구조 | medium / confirmed | FINAL-SHOULD | GOPATH는 고쳤지만 CI가 어디서도 안 돈다(R-E 루트에 .github 없음). BL-22 | findings/v33audit_2026-11-01/A-integrity.md |
| A-E2 | T1이 시험용 개인키 PEM 28개를 커밋했고 이력에 남아 있음 | medium / confirmed | DROP | 대체됨: D42. R-E archive에는 키가 없다. 공개 판단은 BL-32 | findings/v33audit_2026-11-01/A-integrity.md |
| A-E3 | gen33 저장소 비대: 파생 자료·바이너리·복사본 대량 커밋 | medium / confirmed | DROP | 대체됨: D42. R-E에 안 올렸다. 보존 판단은 BL-35 | findings/v33audit_2026-11-01/A-integrity.md |
| A-E4 | 검증 묶음 manifest가 가리키는 .log 24개가 git에 없음 | low / confirmed | DROP | 반영: ignore된 g3 파일 0개(직접) | findings/v33audit_2026-11-01/A-integrity.md |
| A-E5 | 기본 pytest가 실행마다 저장소 안에 파일을 남김 | low / partly | DROP | 반영: fixture가 임시 폴더로 갔다. 남은 61개 삭제는 BL-41 | findings/v33audit_2026-11-01/A-integrity.md |
| A-E6 | S2 clone 검사 사본을 스크래치가 아닌 C:\dev\R-E-wt에 남김, 기존 .sh 규칙 행 삭제 | low / confirmed | FINAL-MUST | R-E-wt/hygiene에 .gitattributes 미커밋(직접). BL-01 | findings/v33audit_2026-11-01/A-integrity.md |
| A-E7 | WSL ~/quicbed_gen33/bin의 go_race.txt가 현재 바이너리보다 오래됨, stage 누적 3.9 GB | low / partly | DROP | 반영: build_gen33.sh가 옛 race 기록을 지운다 | findings/v33audit_2026-11-01/A-integrity.md |
| A-E8 | 'Go 시험 231개 통과' 보고에서 기본 SKIP 2건 누락 | low / confirmed | DROP | 반영: 문서에 SKIP 2 표기 | findings/v33audit_2026-11-01/A-integrity.md |
| A-M1 | gen33 .gitattributes가 검증 묶음의 .log 등을 보호하지 않아 기본 Windows clone에서 manifest 해시 108개가 깨짐 | low / missed | DROP | 반영: .gitattributes에 *.log 등 있음(직접) | findings/v33audit_2026-11-01/A-integrity.md |
| A-M2 | 20 MB 거부 pre-commit 훅이 .git/hooks에만 있어 clone하면 사라짐 | low / missed | DROP | 반영: core.hooksPath=tools/hooks(직접) | findings/v33audit_2026-11-01/A-integrity.md |
| B-E1 | 활성 정책의 기본 경로(none, C1 없음)가 v3.2-dev보다 나빠졌다 | high / confirmed | DROP | 반영: none 경로가 v3.2와 같다(411,000 재생) | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-E2 | L1 채택 판정이 과제 규칙을 우회했고 이후 후보와 비대칭 기준을 썼다 | high / partly | DROP | 반영: D47 대칭 기준 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-E3 | C1 B6 비열등 통과가 결과를 본 뒤 정한 정밀화 재실행에 기대고 있다 | medium / partly | DROP | 반영: seed 51~250 반복. 단서는 평가 문서 8절 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-E4 | C1 경로는 버스트 손실에서 p를 낮게 추정하고 비용이 조금 늘어난다 | low / confirmed | DROP | 효과 작음(+0.164 ms). 고치면 새 후보. BL-05 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-E5 | S4 뒤 E12 L1 보충 관문을 다시 돌리지 않아, 지금 그대로 돌리면 출처 검사에서 실패한다 | low / confirmed | USER | 옛 생성기는 안 돈다. 삭제 여부 D52. BL-38 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-E6 | Go 시험이 보호 대상 작업 폴더 ~/quicbed_gen33에 부산물을 남긴다 | low / partly | DROP | 반영: 새 시험은 test_artifacts에 안 쓴다 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-E7 | 상태 판본이 3에서 4로 바뀌었는데 cache3 schema 표지는 그대로라 옛 캐시가 있으면 qamp가 종료한다 | low / confirmed | DROP | 반영: padfec3.cache3/11(직접) | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-M1 | none 경로에서는 10-29 감사의 '보호 행동 정보 0' 결함이 전혀 고쳐지지 않았다 | medium / missed | DROP | 설계로 남김(D41). 무손실 고착은 BL-05 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-M2 | none 경로가 v3.2가 건너뛰던 연결(명목 2-RTT, guard 경보)에도 categorical 갱신을 한다 | low / missed | DROP | 대체됨: none이 v3.2로 돌아갔다 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| B-M3 | c1 이득은 회신 비용 0을 가정한 수동 관측 모형의 값이고, 회신은 인증되지 않은 비표준 서버 확장이다 | low / missed | DROP | REPORT_CLAIMS에 단서 있음. 최종 한계는 BL-05 | findings/v33audit_2026-11-01/B-active-algorithm.md |
| C-E1 | CRN 영분산 규칙이 구조적 상수 차이를 '경계 미정의'로 만들어 J6를 부당하게 기각 | high / partly | DROP | 반영: Z1 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E2 | L1 채택을 가른 셀이 결과를 본 뒤 늘린 표본(같은 seed 앞부분 포함)으로 통과 | medium / confirmed | DROP | 반영: 평가 문서에 사후 분석 명시 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E3 | 세계가 정책의 바이트 상수를 그대로 써서 신용 경계 차원은 자기 채점 | medium / confirmed | DROP | 못 고침(세계가 정책 상수 공유). BL-05 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E4 | 세계 보정의 범위와 허용차가 판정 해상도보다 거칠다 | medium / partly | DROP | 실측 보정이 필요해 생략. BL-05 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E5 | bigcert15 자동(0,0,4) 불일치는 Initial 계수 정의 차이이고, 2라운드 손실 가지는 검증되지 않았다 | low / confirmed | DROP | 반영: Initial 계수 진단(V33FIX_world.md 4절) | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E6 | M1 세계 사본(worldsim_m1.py)이 hold 경로에서만 패리티 수신 뒤 서버 송신을 재개 | high / confirmed | DROP | 반영: worldsim_m1 수정. M1은 DROP | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E7 | L1 채택이 C1 없는 경로의 v31·v32 대비 악화와 카드 완료 기준 미달을 주 비교 지정으로 비켜감 | medium / confirmed | DROP | 반영: D47 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E8 | 셀 간 다중 비교와 영분산 처리의 비대칭 | low / confirmed | DROP | 반영: bench_rules 2.3에 규칙 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E9 | 20 seed 설계에 검정력 계산이 없어 고분산 셀에서 비열등 판정이 사실상 불가능 | low / partly | USER | seed 수 D51. 후보 평가 종료로 무의미. BL-37 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-E10 | 벤치가 정책에 참 업링크를 준다(감사 처방 6 '업링크 오라클 제거'를 평가할 수 없음) | low / partly | DROP | 후보 평가 종료로 생략. 오라클 입력은 BL-05, X2가 일부 답한다 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| C-M1 | 영분산 규칙과 41 B 고정 ACK가 겹쳐 견고한 후보는 막고 칼날 후보는 통과시킨다 | medium / missed | DROP | 후보 평가 종료로 생략. 단서는 BL-05 | findings/v33audit_2026-11-01/C-world-and-stats.md |
| D-E1 | J6 기각은 zero-variance null 경계 규칙에서 생긴 판정 도구의 결함이다 | high / partly | DROP | 반영: Z1 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E2 | seed 몇 개만 다를 때 대칭 t 구간이 개선을 '비열등 미확정'으로 바꾼다 (L2, J1) | high / partly | DROP | 반영: bench_rules 2.4에 기록 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E3 | 10-29 처방 (1)의 감시층 가산 벌점과 16번째 재평가가 여전히 활성이다 | high / confirmed | DROP | 반영: c1 경로에서 벌점 제거. none 잔존은 BL-05 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E4 | 활성 정책이 1452 B를 넘는 패리티 후보를 계속 만든다 (J7 기각의 결과) | high / partly | USER | 상한은 반영. 실측 W는 D50. BL-36 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E5 | L1과 후속 후보에 적용한 채택 기준이 서로 다르다 | medium / confirmed | DROP | 반영: D47 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E6 | 기각과 blocked 처리가 G1 교착으로 이어져 측정 과제 전부가 실행되지 않았다 | high / partly | DROP | 반영: D46, --deps 잠김 0(직접) | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E7 | L2와 J7은 카드의 완료 기준을 충족하고도 blocked로 처리됐다 | medium / partly | DROP | 반영: D49 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-E8 | L5의 역사 관문은 지금 있는 자료로는 영원히 충족할 수 없다 | low / confirmed | DROP | L5 DROP으로 무의미(D48) | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-M1 | seed 46 none B8는 작은 정책 변화에도 양방향으로 뒤집히는 분기점이라 L2·J1의 'B8 개선'은 개선 증거로 약하다 | medium / missed | DROP | E39 DROP. seed 46 단서는 BL-03 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-M2 | G1만 재정의해도 측정은 풀리지 않는다: T7은 G2→M1(blocked)에도 막혀 있다 | medium / missed | DROP | 반영: G2 의존 분리 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-M3 | W1 벤치는 모든 셀이 W1280이라 1452 B 결함을 원리상 거의 볼 수 없고, 실측 W1406에서는 활성 정책의 모든 k2 패리티가 잘린다 | medium / missed | USER | W 결정 D50. BL-36 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| D-M4 | L3가 기각된 뒤에도 L1은 done으로 남아 있지만, L1 카드의 절대 목표는 활성 정책에서 충족되지 않았다 | medium / missed | DROP | REPORT_CLAIMS에 B1 미달 명시. BL-05 | findings/v33audit_2026-11-01/D-rejected-learning.md |
| E-M1-1 | M1 실패 원인을 세계 결함으로만 돌렸다. 후보 비용 모형도 고손실 순수 선행 행동을 크게 과소평가한다 | high / confirmed | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 BL-03 M1 문단에 적는다 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-M1-2 | lead=0이면 hold와 off가 같아야 한다는 불변식을 시험하지 않고 2864초 MC와 120셀 평가를 돌렸다 | medium / confirmed | DROP | M1 DROP. 불변식 시험은 test_v33_m1_world에 있다 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-M1-3 | M1 세계의 보류 수신기에 문맥별 참 업링크를 넣었다(서버 쪽 업링크 오라클) | medium / confirmed | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 BL-03 M1 문단 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-M1-4 | 2% 손해 0.80 ms의 원인을 진단하지 않았고, 비교 상한을 카드보다 6배 느슨하게 잡았다 | low / confirmed | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 BL-03 M1 문단 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-M1-5 | 복구할 수 없는 비행의 보관 선행 패리티는 TTL에 폐기돼 신용으로도 쓰이지 않는데, 비용 모형에 반영되지 않았다 | low / confirmed | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 BL-03 M1 문단 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-J8-1 | J8이 찾은 W0 서버 PTO 재무장 오류가 기존 W1 판정(B7 등)에 미치는 영향을 재지 않았다 | medium / partly | DROP | 반영: 15 대조 판정 변화 0(V33FIX_world.md 4절) | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-J5-1 | J5의 B10 개선 기준은 m≤4 안에서 구조적으로 달성할 수 없는데, 후속 E23이 같은 기준을 다시 걸었다 | low / confirmed | DROP | 반영: J5 부정 결과로 기록 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-J3-1 | J3의 2% 고정 팔 ±10 ms '미통과'는 실패 표본 5건에 근거한다 | low / refuted | DROP | 검증자 반박(refuted). 처방 안 씀 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-J8-2 | J8 카드는 '모형만'이었는데 하향 손실 p_d 항을 J=None으로 남긴 채 blocked 처리했다 | low / partly | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 BL-03 J8 문단 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-M1 | M1의 B7 none 실패 4셀은 세계 결함과 무관한 후보 선택 문제다 | medium / missed | DROP | 새 후보 탐색이다. 활성 정책에 넣지 않고 BL-03 M1 문단 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| E-M2 | Codex의 한 줄 진단 수정 뒤에도 lead=0 off==hold 불변식이 드물게 깨진다 | low / missed | DROP | M1 DROP. 단서는 BL-03 | findings/v33audit_2026-11-01/E-rejected-mechanism.md |
| F-M1 | F1 영향은 옛 클라이언트의 -feedback 설정과 무관하다 | low / missed | DROP | 반영: -feedback-version 문서 | findings/v33audit_2026-11-01/F-go-testbed.md |
| F-M2 | hold 팔은 복구에 성공한 비행에서도 선행 패리티 신용을 포기한다(설계상 교환, X1·X6 해석 주의) | low / missed | DROP | M1 DROP. X1에서 hold 팔을 뺀다. BL-08 | findings/v33audit_2026-11-01/F-go-testbed.md |
| G-E1 | 주장 문서가 볼트의 '쓰면 안 되는 말' 일부와 핵심 단서를 빠뜨림 | medium / confirmed | DROP | 반영: REPORT_CLAIMS 12·49·51·52행(직접) | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E2 | 측정 사슬 전체가 막힌 사실을 결정 항목으로 올리지 않음 | medium / confirmed | DROP | 반영: D46 | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E3 | README가 코드와 모순된다 (정책·상태 버전, 활성 학습층) | medium / confirmed | DROP | 반영: README가 v3.3.1-dev(직접) | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E4 | '정정 35행' 가운데 실제 정정은 18행이다 | low / partly | DROP | 반영: 정정 행의 성격 절(직접) | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E5 | 팀(고1 3명)이 읽기 어려운 문서 품질 | low / confirmed | FINAL-MUST | docs/README.md 없음(직접). BL-10 | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E6 | H1 표의 '기존 95% 구간'이 판정에 쓰인 Holm 하한이 아니다 | low / confirmed | DROP | 반영: Holm 열 있음(REPORT_CLAIMS 17행) | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E7 | A1이 틀렸다고 한 MDS 설명이 gen33 자기 저장소에는 그대로 남음 | low / confirmed | DROP | 반영: afec/rs.py 설명 고침(직접) | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-E8 | T1이 시험용 개인키 PEM을 git 이력에 커밋했다 (D11 공개 시 위험) | low / confirmed | DROP | 대체됨: D42. BL-32 | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-M1 | H1 허용 문장에 봉인 결과의 '대가'(첫 비행 업링크 약 7.9 KB 대 gen-2 4.1~6.5 KB)가 빠짐 | low / missed | DROP | 반영: REPORT_CLAIMS 15행(직접) | findings/v33audit_2026-11-01/G-claims-frame.md |
| G-M2 | 덱 슬라이드 번호를 '확인하지 못했다'고 했지만 Codex가 읽은 볼트 노트에 답이 있었음 | low / missed | DROP | 효과 없음: 슬라이드 번호 확인은 최종 코드와 무관 | findings/v33audit_2026-11-01/G-claims-frame.md |
| H-01 | "처리함 104"는 수정 완료 수가 아니다. 추적 집계가 부풀려 있다 | high / partly | DROP | 반영: coverage_snapshot 6분류 | findings/v33audit_2026-11-01/H-coverage.md |
| H-02 | 의존 교착 때문에 G1, G2, T7, X1~X9가 영구 대기다. 측정은 0건이다 | high / confirmed | DROP | 반영: --deps 잠김 0(직접) | findings/v33audit_2026-11-01/H-coverage.md |
| H-03 | 바로 할 수 있던 해제 과제를 순서 맨 뒤에 둬서 한 번도 실행하지 않았다 | medium / confirmed | DROP | 대체됨: 후보 해제 과제를 전부 DROP | findings/v33audit_2026-11-01/H-coverage.md |
| H-04 | 막힌 과제의 후속 과제가 또 막힌 과제에 의존한다 | medium / confirmed | DROP | 반영: 의존 정리 | findings/v33audit_2026-11-01/H-coverage.md |
| H-05 | 채택 관문이 L1과 이후 후보에 다르게 적용됐다 | medium / confirmed | DROP | 반영: D47 | findings/v33audit_2026-11-01/H-coverage.md |
| H-06 | A6r1-12(저장소 무게)를 처리함으로 적었지만, 실제로는 루프가 문제를 크게 키웠다 | medium / confirmed | DROP | 대체됨: D42. BL-35 | findings/v33audit_2026-11-01/H-coverage.md |
| H-07 | 막힘 3연속 정지 장치가 partial에 리셋돼서, 성과 없는 18반복이 그대로 진행됐다 | medium / partly | DROP | 반영: run_loop.ps1 done 없이 6반복 정지 | findings/v33audit_2026-11-01/H-coverage.md |
| H-08 | MORNING_REPORT 마감 내용이 LOOP_PROMPT 4절 요구를 다 채우지 못했다 | low / confirmed | DROP | 대체됨: 새 루프 마감 보고 | findings/v33audit_2026-11-01/H-coverage.md |
| H-09 | 루프 종료 상태가 정리되지 않았다 | low / confirmed | DROP | 반영: status stopped | findings/v33audit_2026-11-01/H-coverage.md |
| H-10 | 추적 집계가 백업 스냅숏도 입력으로 읽고, 넘김 대상 카드 일부에서 추적이 끊긴다 | low / confirmed | DROP | 반영: 집계기 수정. 장부 마감은 BL-23 | findings/v33audit_2026-11-01/H-coverage.md |
| H-11 | L1 판정은 표본을 사후에 늘려서 문턱을 아슬아슬하게 통과한 것이다 | low / partly | DROP | 반영: 평가 문서에 사후 분석 명시 | findings/v33audit_2026-11-01/H-coverage.md |
| H-12 | 시험용 개인키 28개가 git 이력에 남아 있다 | low / confirmed | DROP | 대체됨: D42. BL-32 | findings/v33audit_2026-11-01/H-coverage.md |
| H-M1 | 넘김을 받은 과제가 done이 될 때 넘겨받은 항목을 확인하지 않는다(T4에서 8개 넘김 항목이 조용히 빠짐) | medium / missed | FINAL-SHOULD | G1·E10 coverage 파일 없음(직접). BL-23 | findings/v33audit_2026-11-01/H-coverage.md |
| H-M2 | v33 기본 바이너리의 와이어 동작이 L1 외에도 바뀌었고 비용 모형은 따라가지 않았다 | medium / missed | DROP | 반영: D43, -profile sealed31 | findings/v33audit_2026-11-01/H-coverage.md |
| H-M3 | 루프가 run_loop.ps1 없이 돈 정황이 있어 실행기의 안전장치와 기록이 적용되지 않았을 수 있다 | low / missed | DROP | 대체됨: 새 루프는 실행기나 KICK 규칙으로 돈다 | findings/v33audit_2026-11-01/H-coverage.md |
| F1 | C1 회신 판본3이 동결 v3.1·gen-2 클라이언트와 호환되지 않음 | high / partly | DROP | 반영: -feedback-version | findings/v33audit_2026-11-01/F-go-testbed.md |
| F2 | 서버 연결별 기록(conns)을 측정 하네스가 더는 얻을 수 없음 | medium / confirmed | FINAL-MUST | 서버 기록은 나왔지만 읽는 러너가 없다. BL-07 | findings/v33audit_2026-11-01/F-go-testbed.md |
| F3 | lead-hold에서 복구 불가 비행의 선행 패리티 신용이 TTL에 폐기됨 | medium / partly | DROP | M1 DROP. BL-03 | findings/v33audit_2026-11-01/F-go-testbed.md |
| F4 | 측정 조건을 바꾸는 기본값 5종이 T7 전에 바뀌었고, v3.1 봉인 조건 대응표가 없음 | medium / confirmed | FINAL-MUST | 대응표는 있고 sealed31 대 동결 v3.1 A/A가 남았다. BL-07 | findings/v33audit_2026-11-01/F-go-testbed.md |
| F5 | pad/dup 비교 팔에서 drop-parity 주입의 C1 장부가 어긋남 | low / confirmed | DROP | 반영 | findings/v33audit_2026-11-01/F-go-testbed.md |
| F6 | cached_k 과소 추정에 의한 첫 묶음 분할을 표시하지 못함 | low / partly | DROP | 효과 작음. 문서 반영됨(V33FIX_testbed.md) | findings/v33audit_2026-11-01/F-go-testbed.md |
| F7 | build_gen33.sh가 stage를 지우지 않아 디스크가 계속 늘어남 | low / partly | DROP | 반영: 기본 전부 보존. 정리 여부 BL-41 | findings/v33audit_2026-11-01/F-go-testbed.md |
| F8 | 보고된 Go 시험 수에서 M1 와이어 관문 2개가 SKIP이라는 사실이 빠짐 | low / confirmed | DROP | 반영: 시험 수 표기 | findings/v33audit_2026-11-01/F-go-testbed.md |

## 4. 팀 문서 할 일 목록과 수정 대기 목록

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| TD:1-1 | 깃허브 커밋 : 무엇을, 몇 개로 | 팀 문서(08-26~09-08) | USER | 커밋 묶음은 11-05에 끝. 남은 push는 BL-32 | R-E/pq_afec/docs/할 일 목록.md:162 |
| TD:1-2 | 정밀도 실행 : 밤새 돌릴지 | 팀 문서(08-26~09-08) | DROP | gen-2 정밀 실행은 10-01~02에 돌았다. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:176 |
| TD:1-3 | 「임계사이·버스트3」 자리를 조사할지 : 오늘 새로 나온 것 | 팀 문서(08-26~09-08) | USER | 버스트3 불일치. 기본값 한계로 적기. BL-45 | R-E/pq_afec/docs/할 일 목록.md:190 |
| TD:1-4 | p18 검사 4의 자 : 세 번째 자를 어떻게 | 팀 문서(08-26~09-08) | USER | p18 검사 4의 자. 기본값 한계로 적기. BL-45 | R-E/pq_afec/docs/할 일 목록.md:208 |
| TD:1-5 | 정정·진행 보고를 선생님께 낼지 · 언제 | 팀 문서(08-26~09-08) | USER | 정정 보고 제출 여부. BL-43 | R-E/pq_afec/docs/할 일 목록.md:217 |
| TD:1-6 | 예산 정합성 : 데이터센터 vs IoT (제출 전 필수) | 팀 문서(08-26~09-08) | USER | 예산 데이터센터 대 IoT. BL-43 | R-E/pq_afec/docs/할 일 목록.md:224 |
| TD:1-7 | 발표 슬라이드 : 리디자인본으로 원본을 대체할지 | 팀 문서(08-26~09-08) | USER | 발표 슬라이드 선택. BL-43 | R-E/pq_afec/docs/할 일 목록.md:232 |
| TD:2-1 | 루프 한 바퀴 (p17·p6·lint) | 팀 문서(08-26~09-08) | DROP | gen-2 실행 끝. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:243 |
| TD:2-2 | 진행 보기 | 팀 문서(08-26~09-08) | DROP | 상태 보기 명령일 뿐. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:244 |
| TD:2-3 | 보고서만 다시 만들기 | 팀 문서(08-26~09-08) | DROP | gen-2 p6 수동. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:245 |
| TD:2-4 | 알고리즘 자체시험 | 팀 문서(08-26~09-08) | DROP | 자체시험 명령일 뿐. 최종 안내는 BL-10 | R-E/pq_afec/docs/할 일 목록.md:246 |
| TD:2-5 | 감독자 자체시험 | 팀 문서(08-26~09-08) | DROP | 자체시험 명령일 뿐. 최종 안내는 BL-10 | R-E/pq_afec/docs/할 일 목록.md:247 |
| TD:2-6 | Go↔Python 격자 대조 | 팀 문서(08-26~09-08) | DROP | 관문 명령일 뿐. 최종 안내는 BL-10 | R-E/pq_afec/docs/할 일 목록.md:248 |
| TD:2-7 | 정밀도 (1-2 결정 후) | 팀 문서(08-26~09-08) | DROP | gen-2 정밀 실행 끝. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:249 |
| TD:3-1 | 「임계사이·버스트3」 불일치 규명 : 가장 새롭고 값이 큼 | 팀 문서(08-26~09-08) | USER | 1-3과 같다. BL-45 | R-E/pq_afec/docs/할 일 목록.md:260 |
| TD:3-2 | p16의 자를 「판정 불능 + 필요 표본 N」 관례로 | 팀 문서(08-26~09-08) | DROP | gen-2 p16 동결. 같은 관례는 T7에 넣는다(BL-07) | R-E/pq_afec/docs/할 일 목록.md:265 |
| TD:3-3 | p13의 0.5 B 차이 확인 | 팀 문서(08-26~09-08) | DROP | 할 일 목록 2026-09-08 절: 결함 아님 확인 | R-E/pq_afec/docs/할 일 목록.md:272 |
| TD:3-4 | A-1 「뒤따르는 패리티 항」 : 검증하거나, 검증 못 했다고 적기 | 팀 문서(08-26~09-08) | FINAL-SHOULD | 검증 못 했다고 적거나 X3로 잰다. BL-18 | R-E/pq_afec/docs/할 일 목록.md:277 |
| TD:3-5 | A-4 허용집합 자 : 이미 처리됨. 추가 작업 없음 | 팀 문서(08-26~09-08) | DROP | 이미 처리됨(문서 자체 표기) | R-E/pq_afec/docs/할 일 목록.md:284 |
| TD:4-1 | 보고서(p6)가 자동으로 안 돈다 | 팀 문서(08-26~09-08) | DROP | gen-2 러너 동결. 같은 관례는 T7(BL-07) | R-E/pq_afec/docs/할 일 목록.md:292 |
| TD:4-2 | 루프가 「판정은 붉지만 자료는 멀쩡」과 「아예 안 나옴」을 못 가른다 | 팀 문서(08-26~09-08) | DROP | gen-2 러너 동결. T7 Q-06(BL-07) | R-E/pq_afec/docs/할 일 목록.md:300 |
| TD:4-3 | note가 지문 밖이라 낡아도 아무도 무효화 안 함 | 팀 문서(08-26~09-08) | DROP | gen-2 러너 동결. T7 Q-06(BL-07) | R-E/pq_afec/docs/할 일 목록.md:305 |
| TD:4-4 | 결과 파일을 덮어쓰기 전 이전 판 남기기 | 팀 문서(08-26~09-08) | DROP | gen-2 러너 동결. T7 Q-07(BL-07) | R-E/pq_afec/docs/할 일 목록.md:310 |
| TD:5-1 | docs/다음 세션 인계.md 갱신 : 제일 값싸고 효과가 큼 | 팀 문서(08-26~09-08) | FINAL-MUST | 인계 문서 낡음. BL-02 | R-E/pq_afec/docs/할 일 목록.md:318 |
| TD:5-2 | 「먼저 읽을 것」을 하나로 못 박기 | 팀 문서(08-26~09-08) | FINAL-MUST | 읽는 순서 하나로. BL-10 | R-E/pq_afec/docs/할 일 목록.md:324 |
| TD:5-3 | 파이프라인·보고서 이중화 정리 | 팀 문서(08-26~09-08) | FINAL-MUST | 상태 주석. BL-02 | R-E/pq_afec/docs/할 일 목록.md:332 |
| TD:5-4 | docs/선행연구 대조.md를 새 방향 기준으로 | 팀 문서(08-26~09-08) | FINAL-MUST | 선행연구 대조 정정. BL-02 | R-E/pq_afec/docs/할 일 목록.md:340 |
| TD:5-5 | 알고리즘 명세 v0.1·v0.2 머리에 안내 붙이기 | 팀 문서(08-26~09-08) | FINAL-MUST | 명세 v0.1·v0.2 안내. BL-02 | R-E/pq_afec/docs/할 일 목록.md:346 |
| TD:5-6 | 보고서 「한계」에 3개 추가 | 팀 문서(08-26~09-08) | FINAL-MUST | 한계 3개. BL-05 | R-E/pq_afec/docs/할 일 목록.md:350 |
| TD:5-7 | 볼트 프로젝트 노트 자기모순 정리 | 팀 문서(08-26~09-08) | FINAL-SHOULD | 볼트 자기모순. Claude 몫. BL-24 | R-E/pq_afec/docs/할 일 목록.md:357 |
| TD:6-1 | 정정·진행 보고 제출 (1쪽 PDF) | 팀 문서(08-26~09-08) | USER | BL-43 | R-E/pq_afec/docs/할 일 목록.md:367 |
| TD:6-2 | 예산 정합성 데이터센터 vs IoT | 팀 문서(08-26~09-08) | USER | BL-43 | R-E/pq_afec/docs/할 일 목록.md:368 |
| TD:6-3 | 발표 슬라이드 원본 vs 리디자인본 | 팀 문서(08-26~09-08) | USER | BL-43 | R-E/pq_afec/docs/할 일 목록.md:369 |
| TD:6-4 | HWP 신청서 본문 업데이트 | 팀 문서(08-26~09-08) | USER | HWP 신청서 본문. BL-43 | R-E/pq_afec/docs/할 일 목록.md:370 |
| TD:6-5 | 영문 초록 | 팀 문서(08-26~09-08) | USER | 영문 초록. BL-43 | R-E/pq_afec/docs/할 일 목록.md:371 |
| TD:6-6 | R&E 과제별 보고서(별도 hwp, 지도 이현미) | 팀 문서(08-26~09-08) | USER | R&E 보고서는 양식.hwp 초안 있음. 남은 칸은 BL-42 | R-E/pq_afec/docs/할 일 목록.md:372 |
| TD:6-7 | 논문 초고 | 팀 문서(08-26~09-08) | USER | 논문 초고. BL-43 | R-E/pq_afec/docs/할 일 목록.md:373 |
| TD:7-1 | p11 후회 신뢰반폭 | 팀 문서(08-26~09-08) | DROP | gen-2 측정 끝난 뒤 판정 유지. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:381 |
| TD:7-2 | p15 후회 신뢰반폭 | 팀 문서(08-26~09-08) | DROP | gen-2 측정 끝난 뒤 판정 유지. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:382 |
| TD:7-3 | p18 m 미세 순서 | 팀 문서(08-26~09-08) | DROP | 측정 불가: 팔당 8,544~12,404판. BL-05에 표본 부족으로 | R-E/pq_afec/docs/할 일 목록.md:383 |
| TD:7-4 | p17 시간 이득 | 팀 문서(08-26~09-08) | DROP | 측정 불가: 팔당 약 46,000판. BL-05 | R-E/pq_afec/docs/할 일 목록.md:384 |
| TD:7-5 | p16 직렬화 판정 | 팀 문서(08-26~09-08) | DROP | gen-2 동결. 필요 N 관례는 T7 | R-E/pq_afec/docs/할 일 목록.md:385 |
| TD:7-6 | 「버스트3」 불일치 | 팀 문서(08-26~09-08) | USER | 1-3과 같다. BL-45 | R-E/pq_afec/docs/할 일 목록.md:386 |
| TD:7-7 | p13 0.5 B | 팀 문서(08-26~09-08) | DROP | 결함 아님 확인(3-3) | R-E/pq_afec/docs/할 일 목록.md:387 |
| TD:0-1 | 루프 한 바퀴 더 돌리기 : p17이 이제 실제로 돈다 | 팀 문서(08-26~09-08) | DROP | gen-2 루프 끝. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:137 |
| TD:0-2 | 지문이 p6·p17 말고 다른 데서 움직였는지 확인 | 팀 문서(08-26~09-08) | DROP | gen-2 지문 확인 끝. 대체됨 | R-E/pq_afec/docs/할 일 목록.md:150 |
| TD:결정-0908-1 | Go 툴체인 1.26.5 대 1.26.6 | 팀 문서(08-26~09-08) | USER | Go 1.26.5 대 1.26.6. 기본값 그대로 적기. BL-45 | R-E/pq_afec/docs/할 일 목록.md:53 |
| TD:결정-0908-2 | 팀 스크립트 run_v3.sh netem 방향 | 팀 문서(08-26~09-08) | USER | run_v3.sh netem 방향. 기본값 보고서 한계. BL-45 | R-E/pq_afec/docs/할 일 목록.md:54 |
| TD:결정-0908-3 | p17 검사 7·8이 큰cert에서 붉을 것 | 팀 문서(08-26~09-08) | DROP | p17 판정 유지. 보고서 Table 5에 있음 | R-E/pq_afec/docs/할 일 목록.md:55 |
| TD:수리-0908-C1 | C1 RxOrigN이 PTO 재전송을 센다 | 팀 문서(08-26~09-08) | DROP | 반영: T4, c1_status.md | R-E/pq_afec/docs/할 일 목록.md:59 |
| TD:수리-0908-combo | _combo_deltas 회계 차이 | 팀 문서(08-26~09-08) | DROP | 결정 영향 0(문서 자체 표기). 효과 없음 | R-E/pq_afec/docs/할 일 목록.md:60 |
| TD:수리-0908-backup | 결과 파일 덮어쓰기 전 백업 | 팀 문서(08-26~09-08) | DROP | gen-2 러너 동결. T7 Q-07 | R-E/pq_afec/docs/할 일 목록.md:61 |
| TD:결정-0830-p17 | p17을 어떻게 할 것인가 | 팀 문서(08-26~09-08) | DROP | 09-01 결정 (다)로 설치됨 | R-E/pq_afec/docs/할 일 목록.md:102 |
| TD:수리-0830-pto | PTO_SAMPLED_RTT_MULT가 RFC 유도값 | 팀 문서(08-26~09-08) | FINAL-SHOULD | Q-10과 같다. BL-18 | R-E/pq_afec/docs/할 일 목록.md:126 |
| TD:수리-0830-주석 | 코드 주석 둘이 다른 수 | 팀 문서(08-26~09-08) | FINAL-MUST | Q-12와 같다. BL-13 | R-E/pq_afec/docs/할 일 목록.md:129 |
| TD:수리-0830-bolot | Bolot·Boutremans 닫힌형 대조 | 팀 문서(08-26~09-08) | DROP | 반영: W0 검증(Q-11) | R-E/pq_afec/docs/할 일 목록.md:131 |
| SW:A-1 | 뒤따르는 패리티 항이 검증되지도 반증되지도 않았다 | 팀 문서(08-26) | FINAL-SHOULD | Q-01과 같다. BL-18 | R-E/pq_afec/docs/수정 대기 목록.md:29 |
| SW:A-2 | p18 검사 4의 자가 거꾸로 되어 있다 | 팀 문서(08-26) | FINAL-MUST | Q-02. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:49 |
| SW:A-3 | p16의 자(0.25 ms)가 자기 표류(0.694 ms)보다 곱다 : 오늘 처음 드러남 | 팀 문서(08-26) | DROP | gen-2 동결. T7 Q-03(BL-07). 한계는 BL-05 | R-E/pq_afec/docs/수정 대기 목록.md:66 |
| SW:A-4 | 허용집합의 자(1 ms)가 오차막대보다 곱다 : p11 · p17 | 팀 문서(08-26) | DROP | 보고서 한계로 처리 끝(할 일 3-5) | R-E/pq_afec/docs/수정 대기 목록.md:91 |
| SW:A-5 | 폐루프가 실제로는 닫혀 있지 않다 : 설계상 알려진 것 | 팀 문서(08-26) | FINAL-MUST | Q-05 상태 주석. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:108 |
| SW:A-6 | k(비행 데이터그램 수) 제어 불가 | 팀 문서(08-26) | FINAL-MUST | Q-05. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:118 |
| SW:A-7 | m ≥ 3 : 부호는 되는데 정책이 안 고른다 | 팀 문서(08-26) | DROP | 설계상 알려진 것. BL-05 | R-E/pq_afec/docs/수정 대기 목록.md:124 |
| SW:A-8 | 서버 → 클라이언트 방향 미보호 : 원리적 제외 | 팀 문서(08-26) | FINAL-MUST | Q-05. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:129 |
| SW:A-9 | 제자리(패딩 자리) 배치 불가 : 결과이지 미구현이 아니다 | 팀 문서(08-26) | DROP | 결과이지 미구현 아님(문서 자체 표기). 보고서에 있음 | R-E/pq_afec/docs/수정 대기 목록.md:134 |
| SW:B-1 | 오늘 고친 것(기록용) | 팀 문서(08-26) | DROP | 오늘 고친 것(기록용) | R-E/pq_afec/docs/수정 대기 목록.md:146 |
| SW:B-2 | 오늘 고친 것(기록용) | 팀 문서(08-26) | DROP | 오늘 고친 것(기록용) | R-E/pq_afec/docs/수정 대기 목록.md:146 |
| SW:B-3 | 오늘 고친 것(기록용) | 팀 문서(08-26) | DROP | 오늘 고친 것(기록용) | R-E/pq_afec/docs/수정 대기 목록.md:146 |
| SW:B-4 | 오늘 고친 것(기록용) | 팀 문서(08-26) | DROP | 오늘 고친 것(기록용) | R-E/pq_afec/docs/수정 대기 목록.md:146 |
| SW:B-5 | →구조 보고서(p6)가 자동으로 안 돈다 | 팀 문서(08-26) | DROP | gen-2 러너 동결. T7 Q-06 | R-E/pq_afec/docs/수정 대기 목록.md:155 |
| SW:B-6 | · B-5의 뿌리 : 루프가 「판정은 붉지만 자료는 멀쩡」과 「아예 안 나옴」을 못 가른다 | 팀 문서(08-26) | DROP | gen-2 러너 동결. T7 Q-06 | R-E/pq_afec/docs/수정 대기 목록.md:167 |
| SW:B-7 | · note가 지문 밖이라 낡아도 아무도 무효화하지 않는다 | 팀 문서(08-26) | DROP | gen-2 러너 동결. T7 Q-06 | R-E/pq_afec/docs/수정 대기 목록.md:180 |
| SW:B-8 | · 결과 파일을 덮어쓰기 전 이전 판을 안 남긴다 | 팀 문서(08-26) | DROP | gen-2 러너 동결. T7 Q-07 | R-E/pq_afec/docs/수정 대기 목록.md:188 |
| SW:C-1 | docs/다음 세션 인계.md가 12일 낡았고 새 세션을 틀린 방향으로 보낸다 | 팀 문서(08-26) | FINAL-MUST | Q-08. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:197 |
| SW:C-2 | 「먼저 읽을 것」이 세 곳에서 서로 다르다 | 팀 문서(08-26) | FINAL-MUST | 읽는 순서. BL-10 | R-E/pq_afec/docs/수정 대기 목록.md:204 |
| SW:C-3 | 보고서가 둘, 파이프라인이 둘 | 팀 문서(08-26) | FINAL-MUST | Q-08 상태 주석. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:215 |
| SW:C-4 | docs/선행연구 대조.md(08-14)가 옛 방향 기준이다 | 팀 문서(08-26) | FINAL-MUST | Q-16. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:226 |
| SW:C-5 | docs/알고리즘 명세 v0.1.md(08-13) · v0.2.md(08-14)가 옛 방향 | 팀 문서(08-26) | FINAL-MUST | Q-08. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:234 |
| SW:C-6 | 볼트 수치 오류 : 오늘 정정 | 팀 문서(08-26) | DROP | 오늘 정정(문서 자체 표기) | R-E/pq_afec/docs/수정 대기 목록.md:240 |
| SW:C-7 | 「연구방향_변경보고」 §5 · §8 : 오늘 1쪽 정정보고로 처리 | 팀 문서(08-26) | DROP | 1쪽 정정보고로 처리. 제출은 BL-43 | R-E/pq_afec/docs/수정 대기 목록.md:245 |
| SW:C-8 | 원본 변경보고의 HTML 소스가 없다 | 팀 문서(08-26) | FINAL-MUST | 상태 주석. BL-02 | R-E/pq_afec/docs/수정 대기 목록.md:250 |
| SW:C-9 | · 보고서에 추가로 들어가야 할 한계 (아직 안 들어감) | 팀 문서(08-26) | FINAL-MUST | Q-09. BL-02와 BL-05 | R-E/pq_afec/docs/수정 대기 목록.md:257 |
| SW:D-1 | p11 후회 신뢰반폭 | 팀 문서(08-26) | DROP | gen-2 측정 끝. 대체됨 | R-E/pq_afec/docs/수정 대기 목록.md:270 |
| SW:D-2 | p15 후회 신뢰반폭 | 팀 문서(08-26) | DROP | gen-2 측정 끝. 대체됨 | R-E/pq_afec/docs/수정 대기 목록.md:271 |
| SW:D-3 | p18 m 미세 순서 | 팀 문서(08-26) | DROP | 측정 불가: 표본. BL-05 | R-E/pq_afec/docs/수정 대기 목록.md:272 |
| SW:D-4 | p17 시간 이득 | 팀 문서(08-26) | DROP | 측정 불가: 표본. BL-05 | R-E/pq_afec/docs/수정 대기 목록.md:273 |
| SW:D-5 | p16 직렬화 판정 | 팀 문서(08-26) | DROP | gen-2 동결. 필요 N 관례는 T7 | R-E/pq_afec/docs/수정 대기 목록.md:274 |
| SW:D-6 | p12c (칸 5·6) | 팀 문서(08-26) | DROP | 물리적 상한(문서 자체 표기) | R-E/pq_afec/docs/수정 대기 목록.md:275 |
| SW:E-1 | 작업 폴더에 이력이 없다 ( 2026-08-26 23:0x 정정) | 팀 문서(08-26) | DROP | 대체됨: gen33 git과 R-E main이 있다 | R-E/pq_afec/docs/수정 대기 목록.md:285 |
| SW:E-2 | · p13의 0.5 B 차이 : 미확인 | 팀 문서(08-26) | DROP | 결함 아님 확인(할 일 09-08 절) | R-E/pq_afec/docs/수정 대기 목록.md:316 |
| SW:F-1 | 무엇이 바뀌었나 (구조) | 팀 문서(08-26) | DROP | 분석 기록. 할 일 없음 | R-E/pq_afec/docs/수정 대기 목록.md:387 |
| SW:F-2 | 새로 생긴 능력 (옛 판에는 개념 자체가 없음) | 팀 문서(08-26) | DROP | 분석 기록. 할 일 없음 | R-E/pq_afec/docs/수정 대기 목록.md:402 |
| SW:F-3 | 값이 바뀐 상수 : 전부 추정 → 실측 교체 | 팀 문서(08-26) | DROP | 분석 기록. 할 일 없음 | R-E/pq_afec/docs/수정 대기 목록.md:415 |
| SW:F-4 | 결정이 얼마나 달라지나 : 격자 1,440점 대조 | 팀 문서(08-26) | DROP | 분석 기록. 할 일 없음 | R-E/pq_afec/docs/수정 대기 목록.md:427 |
| SW:F-5 | ⭐ 어느 쪽이 실측에 맞나 : p18 다섯 조건과 대조 | 팀 문서(08-26) | USER | 버스트3 불일치 원자료. BL-45 | R-E/pq_afec/docs/수정 대기 목록.md:443 |
| SW:F-6 | 한 줄 요약 | 팀 문서(08-26) | DROP | 분석 기록. 할 일 없음 | R-E/pq_afec/docs/수정 대기 목록.md:470 |

## 5. 볼트 2026-10-29 우선순위

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| V10-1 | 손실 학습을 데이터그램 증거로, 벌점·재평가 제거 | 볼트 10-29 우선순위 | DROP | 반영: v3.3.1-dev c1 경로. none 경로 유지는 D41. BL-05 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-2 | 선행 패리티 보류 복호 | 볼트 10-29 우선순위 | DROP | M1 평가 뒤 미채택. BL-03 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-3 | J3 보정(꼬리, 처리 상수, A_pre, n_need, GE) | 볼트 10-29 우선순위 | DROP | J1·J2·J6·L5·J5 전부 미채택 또는 DROP. BL-03 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-4 | 첫 방문 행동 | 볼트 10-29 우선순위 | DROP | L6 DROP. BL-05 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-5 | 바이트 가격 | 볼트 10-29 우선순위 | DROP | O1 DROP. BL-05 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-6 | 업링크 오라클 제거 | 볼트 10-29 우선순위 | DROP | O2 미채택. X2로 오입력만 잰다. BL-19 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-측정 | 같은 바이트, 토큰, 업링크 오입력, A_pre, RFC 스택, 전역 고정 팔 | 볼트 10-29 우선순위 | FINAL-SHOULD | X1 must, 나머지 should, RFC 스택 DROP. BL-08, BL-16~20 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |
| V10-코드 | 원자료·바이너리 보관, .gitattributes, 10-07 이식, 태그, CI | 볼트 10-29 우선순위 | FINAL-MUST | .gitattributes·태그가 main에 없다. CI 미실행. BL-01, BL-22 | 06 세션 로그/2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md:40 |

## 6. V33FIX 문서의 남은 일

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| VF-HYG-1 | docs/README.md 읽는 순서·ID 용어집과 다른 docs 100여 개의 띄어쓰기(G-E5 FIX의 나머지)는 이 묶음 파일 목록 밖 | V33FIX 남은 일 | FINAL-MUST | docs/README.md 없음. BL-10 | gen33/docs\V33FIX_docs_hygiene.md:107 |
| VF-HYG-2 | G-E2(측정 사슬 봉쇄를 결정 항목으로 올리기)는 이 묶음 몫이 아니다. | V33FIX 남은 일 | DROP | 반영: D46 | gen33/docs\V33FIX_docs_hygiene.md:108 |
| VF-HYG-3 | tests/test_v33_policy_worker.py 48행의 state_version 4 기대는 이 묶음 범위(임시 폴더 fixtu | V33FIX 남은 일 | DROP | 반영: test_v33_policy_worker.py:49 값 11(직접) | gen33/docs\V33FIX_docs_hygiene.md:109 |
| VF-HYG-4 | 새 공개 저장소 만들기와 그 안의 검사·시험, push, 이력 재작성은 D1·D11·D40에 따라 하지 않았다. | V33FIX 남은 일 | USER | BL-32 | gen33/docs\V33FIX_docs_hygiene.md:110 |
| VF-HYG-5 | 저장소 안에 이미 쌓인 experiments/state/v33_worker_test_artifacts/source-* 61개는 지우지 않았다 | V33FIX 남은 일 | USER | 삭제 여부 BL-41 | gen33/docs\V33FIX_docs_hygiene.md:111 |
| VF-HYG-6 | .git/hooks/pre-commit 옛 파일은 지우지 않았다. core.hooksPath가 있으므로 쓰이지 않는다. | V33FIX 남은 일 | DROP | 효과 없음: hooksPath로 안 쓰인다 | gen33/docs\V33FIX_docs_hygiene.md:112 |
| VF-HYG-7 | --history 모드의 단위 시험은 시험 파일(tests/test_v33_repro_tools.py)이 이 묶음 목록 밖이라 넣지 않았 | V33FIX 남은 일 | FINAL-SHOULD | scrub 시험. BL-11에 같이 넣는다 | gen33/docs\V33FIX_docs_hygiene.md:113 |
| VF-EVA-1 | c1 B6 외의 셀은 seed 31~50 한 번뿐이다. 설계를 고른 seed라서 다른 셀의 통과도 확증이 아니다. 전 셀 독립 반복은 하지 않았 | V33FIX 남은 일 | DROP | 후보 평가 종료. 문서에 단서 있음 | gen33/docs\V33FIX_evaluation.md:166 |
| VF-EVA-2 | B1 후회 미확정을 새 seed로 해소하려 하지 않았다. 채택 바닥 조건이 아니라 절대 목표라서 계획에 넣지 않았다. | V33FIX 남은 일 | DROP | 절대 목표 미확정 그대로 보고 | gen33/docs\V33FIX_evaluation.md:167 |
| VF-EVA-3 | 1452 B 패리티 상한은 W1 15셀이 모두 W=1280이라 이 벤치에서 시험되지 않는다(A-py 재생에서 후보 수 변화 0). | V33FIX 남은 일 | FINAL-SHOULD | 벤치 밖 경계. BL-21 | gen33/docs\V33FIX_evaluation.md:168 |
| VF-EVA-4 | c1 모드의 B11 seed 42·50처럼 첫 C1 회신이 늦은 목적지는 그 전까지 v3.2 규칙으로 배운다. 이 세계에서는 비용 차이가 +0. | V33FIX 남은 일 | DROP | 효과 없음: +0.000889 ms/연결 | gen33/docs\V33FIX_evaluation.md:169 |
| VF-EVA-5 | Go 거울(policy3.go, qamp)은 평가하지 않았다. 이 결과는 Python 정책의 시뮬레이션 결과다. | V33FIX 남은 일 | FINAL-MUST | Go 쪽은 G2와 X6가 답한다. BL-06 | gen33/docs\V33FIX_evaluation.md:170 |
| VF-EVA-6 | 실측(T7 등)이 없다. | V33FIX 남은 일 | FINAL-MUST | BL-07, BL-08 | gen33/docs\V33FIX_evaluation.md:171 |
| VF-EVA-7 | 이 문서와 JSON은 seed 95% 구간과 MC 99% 폭을 더한 경계를 쓰며, 전체 동시 95% 보장을 주장하지 않는다. | V33FIX 남은 일 | DROP | 문서에 이미 적힘 | gen33/docs\V33FIX_evaluation.md:172 |
| VF-POL5-1 | c1 경로의 이득은 비표준이고 인증되지 않은 C1 회신에 기댄다. W1 원자료의 c1 관측 모형은 회신 비용을 HCT, 증폭 예산, 다음 연결 | V33FIX 남은 일 | DROP | REPORT_CLAIMS에 있음. BL-05 | gen33/docs\V33FIX_policy.md:106 |
| VF-POL5-2 | B10 버스트 손실에서 c1의 p 과소추정(B-E4, 꼬리 p 편향 −0.0204, v32 대비 +0.170 [0.136, 0.204] ms, | V33FIX 남은 일 | DROP | BL-05 | gen33/docs\V33FIX_policy.md:107 |
| VF-POL5-3 | B1 절대 목표 0.1 ms는 record_c1 0.093952 [0.060876, 0.127028]로 미확정이라 달성했다고 말할 수 없다. B | V33FIX 남은 일 | DROP | BL-05 | gen33/docs\V33FIX_policy.md:108 |
| VF-POL5-4 | none 경로는 v3.2와 같으므로 v3.2의 결함(무손실 B3_u0·B4에서 보호 행동 고착, 감사 B 놓친 점 1)도 그대로다. W1 15셀 | V33FIX 남은 일 | DROP | BL-05 | gen33/docs\V33FIX_policy.md:109 |
| VF-POL5-5 | 1452 B 상한 때문에 W와 k가 크면 패리티 후보가 하나도 남지 않는다. 패리티 데이터그램은 W+39+6k B(padfec/policy.p | V33FIX 남은 일 | USER | D50. BL-36 | gen33/docs\V33FIX_policy.md:110 |
| VF-POL5-6 | 명시 행동 경로(decide3의 actions= 인자, explicit_candidates)는 1452 B 상한도 max_ips도 | V33FIX 남은 일 | USER | replay_g3 표시 여부. 기본값 문서만. BL-46 | gen33/docs\V33FIX_policy.md:111 |
| VF-POL5-7 | 첫 C1 회신이 늦게 오는 목적지(B11 seed 42·50)는 그 전까지 v3.2 규칙으로 배운 사후분포를 안고 c1 규칙으로 넘어간다. | V33FIX 남은 일 | DROP | 효과 없음(VF-EVA-4) | gen33/docs\V33FIX_policy.md:112 |
| VF-POL5-8 | 이번 재생은 결정 일치를 센 것이고 성능을 다시 잰 것이 아니다. W1 15셀에서 새 정책의 none 성능은 v3.2와, c1 성능은 L3 re | V33FIX 남은 일 | DROP | 문서에 이미 적힘 | gen33/docs\V33FIX_policy.md:113 |
| VF-POLH-1 | 실측(T7)에서 W를 패리티 상한(k=2면 1401) 아래로 잡을지, W 1406·k=2에서 패리티 없이 잴지. | V33FIX 남은 일 | USER | D50. BL-36 | gen33/docs\V33FIX_policy.md:197 |
| VF-POLH-2 | g3/l1_go_reference_gen.py와 g3/v33/E12_l1_reference_v1.json을 지울지. | V33FIX 남은 일 | USER | D52. BL-38 | gen33/docs\V33FIX_policy.md:198 |
| VF-POLH-3 | 오프라인 분석(replay_g3.py)에서 1452 B를 넘는 명시 행동을 표시하거나 거를지. | V33FIX 남은 일 | USER | BL-46 | gen33/docs\V33FIX_policy.md:199 |
| VF-POLH-4 | experiments/v33/v33fix_rejudge.py 774행의 'pre-registered' 문구(목록 밖 파일). | V33FIX 남은 일 | DROP | 반영: 통합 담당이 고침 | gen33/docs\V33FIX_policy.md:200 |
| VF-POLH-5 | ~/quicbed_gen33에 새 바이너리를 설치하는 일(이 작업에서 금지). | V33FIX 남은 일 | FINAL-MUST | 설치본이 v3.3-dev(직접). BL-14 | gen33/docs\V33FIX_policy.md:201 |
| VF-GO6-1 | experiments/gate_v3_parity.py:27의 POLICY_VERSION이 아직 "v3.3-dev"다. 맡은 파일 밖이라 | V33FIX 남은 일 | DROP | 반영: gate_v3_parity.py:27 v3.3.1-dev(직접) | gen33/docs\V33FIX_policy_go.md:117 |
| VF-GO6-2 | genconfig.json의 gen_id가 "v3.3-dev"다. 맡은 파일 밖이다. 묶음 P는 이 값을 바꾸지 않기로 했다. expe | V33FIX 남은 일 | DROP | 의도된 값: pipeline.py가 gen_id로 옛 러너를 막는다 | gen33/docs\V33FIX_policy_go.md:118 |
| VF-GO6-3 | g3/l1_go_reference_gen.py(E12 L1 생성기)는 none 경로 info에 c1 전용 키를 요구해서 지금 정책으로는 실행 | V33FIX 남은 일 | USER | D52. BL-38 | gen33/docs\V33FIX_policy_go.md:119 |
| VF-GO6-4 | 새 참조의 출처 지문에 든 파일(4절)을 다른 묶음이 이후에 바꾸면 관문이 출처 문제로 실패한다. 그때는 --generate로 다시 만들고 | V33FIX 남은 일 | FINAL-MUST | 최종 코드 뒤 참조 재생성. BL-14 | gen33/docs\V33FIX_policy_go.md:120 |
| VF-GO6-5 | WSL ~/quicbed_gen33에 설치하지 않았고 build_gen33.sh도 돌리지 않았다(이 작업의 금지 사항). 실제 배포 바이 | V33FIX 남은 일 | FINAL-MUST | BL-14 | gen33/docs\V33FIX_policy_go.md:121 |
| VF-GO6-6 | Python from_json은 모르는 최상위 키와 모르는 stats 키를 받아들이지만 Go는 거부한다. 캐시 로더가 원래 그랬던 것을 | V33FIX 남은 일 | DROP | 캐시 로더 원래 동작. 참조에 고정됨 | gen33/docs\V33FIX_policy_go.md:122 |
| VF-GO6-7 | 실제 QUIC 측정(T7 등)은 하지 않았다. 이번 검증은 두 언어 구현의 일치와 v3.2 Go와의 일치를 본 것이고 성능을 잰 것이 아니다. | V33FIX 남은 일 | FINAL-MUST | BL-07, BL-08 | gen33/docs\V33FIX_policy_go.md:123 |
| VF-TB1-1 | flight_shape.go의 retransLayout()은 retransMode가 빈 문자열이면 original_first를 돌 | V33FIX 남은 일 | DROP | 반영: 통합 정리 1절 | gen33/docs\V33FIX_testbed.md:160 |
| VF-TB1-2 | docs/T6_retrans_contract.md, docs/T6_result.md, codex_handoff의 DECISIONS_NE | V33FIX 남은 일 | DROP | 반영: 통합 정리 6절 | gen33/docs\V33FIX_testbed.md:161 |
| VF-TB1-3 | T7 러너(Python)와 g3bed의 conn-log 읽기는 만들지 않았다. | V33FIX 남은 일 | FINAL-MUST | BL-07 | gen33/docs\V33FIX_testbed.md:162 |
| VF-TB1-4 | 클라이언트 tracer와 conn-log의 비용, udp-path 두 경로의 HCT 차이, sealed31 gen33과 동결 v3.1의 A/A | V33FIX 남은 일 | FINAL-MUST | BL-07 스모크에서 잰다 | gen33/docs\V33FIX_testbed.md:163 |
| VF-TB1-5 | GitHub runner에서 CI를 실제로 돌리지 않았다. | V33FIX 남은 일 | FINAL-SHOULD | BL-22 | gen33/docs\V33FIX_testbed.md:164 |
| VF-TB1-6 | build_gen33.sh는 Go 소스 목록을 명시적으로 적는다(47행). 다른 묶음이 experiments/quicbed에 새 비시험 | V33FIX 남은 일 | DROP | 의도된 동작: 종료 2로 멈춘다 | gen33/docs\V33FIX_testbed.md:165 |
| VF-TB1-7 | 새 시험 일부는 정책 쪽 타입(p3Arrivals, auto3Plan, p3Decision)과 chooseFlightExpectat | V33FIX 남은 일 | DROP | 정책 이름 안 바꾼다. 효과 없음 | gen33/docs\V33FIX_testbed.md:166 |
| VF-TB2-1 | qamp_comparison_test.go의 fixture 한 줄은 맡은 목록 밖이라 고치지 않았다. 통합 때 위 patch를 적용하면 Go | V33FIX 남은 일 | DROP | 반영: 통합 담당 patch(19행) | gen33/docs\V33FIX_testbed.md:388 |
| VF-TB2-2 | G3h는 결과가 같은 돌연변이라 행동 시험으로 잡을 수 없다(3절). | V33FIX 남은 일 | USER | 등가 돌연변이 수용. BL-46 | gen33/docs\V33FIX_testbed.md:389 |
| VF-TB2-3 | .github/workflows/ci.yml은 바꾸지 않았다. 새 시험은 build_gen33.sh의 go test에 그대로 들어가고 소 | V33FIX 남은 일 | FINAL-SHOULD | BL-22 | gen33/docs\V33FIX_testbed.md:390 |
| VF-TB2-4 | 루프 폴더의 MORNING_REPORT.md의 "Go 231" 문구와 DECISIONS_NEEDED.md D28 본문은 루프 묶음의 파일 | V33FIX 남은 일 | DROP | 반영: 2차 통합 정리 | gen33/docs\V33FIX_testbed.md:391 |
| VF-TB2-5 | 1차에서 넘긴 T7 러너와 g3bed의 conn-log 읽기, tracer·conn-log 비용, udp-path 두 경로의 HCT, sea | V33FIX 남은 일 | FINAL-MUST | BL-07 | gen33/docs\V33FIX_testbed.md:392 |
| VF-TB2-6 | 보호 경로 ~/quicbed_gen33의 stage 53개와 test_artifacts 4,005개는 읽기 전용으로 세기만 했다. bi | V33FIX 남은 일 | USER | BL-41 | gen33/docs\V33FIX_testbed.md:393 |
| VF-LP4-1 | hygiene-clone-check는 영구 삭제하지 않고 스크래치로 옮겼다. 고유 작업이 없음을 확인했지만 영구 삭제는 되돌릴 수 없어서다. | V33FIX 남은 일 | USER | BL-41 | handoff/V33FIX_loop.md:178 |
| VF-LP4-2 | .gitattributes 복원은 커밋하지 않았다(커밋 금지). hygiene 브랜치에 넣으려면 git -C C:\dev\R-E-wt\hy | V33FIX 남은 일 | FINAL-MUST | R-E-wt/hygiene 미커밋(직접). BL-01 | handoff/V33FIX_loop.md:179 |
| VF-LP4-3 | gen33 docs\S2_hygiene.md 11·40행과 루프 runs\S2_hygiene.md 11·40행이 옮긴 C:\dev\R- | V33FIX 남은 일 | FINAL-SHOULD | docs/S2_hygiene.md에 옛 경로 2줄(직접). BL-01에 같이 | handoff/V33FIX_loop.md:180 |
| VF-LP4-4 | 활성 정책 v3.3.1-dev, D43의 repeat_first 기본값과 -profile sealed31은 다른 묶음이 gen33에 넣는 | V33FIX 남은 일 | DROP | 반영: 통합 때 확인 | handoff/V33FIX_loop.md:181 |
| VF-LP4-5 | G1, E10, L1의 최종 상태는 정하지 않았다(지시대로 통합 때). | V33FIX 남은 일 | DROP | 반영: 통합 결정 | handoff/V33FIX_loop.md:182 |
| VF-LP4-6 | done 과제가 넘겨받고 기록하지 않은 16줄과 넘김-교착 A7-18은 각 항목의 처리 여부를 T4·T5·L2·E17·M4 결과와 대조해야 해서 | V33FIX 남은 일 | DROP | 대체됨: 이 표. 장부 마감은 BL-23 | handoff/V33FIX_loop.md:183 |
| VF-LP4-7 | 감사 원문은 세션 스크래치에 있어 사라질 수 있다. LOOP_PROMPT 2-3은 그 폴더가 없으면 이 파일을 읽으라고 적었다. 통합 때 v3 | V33FIX 남은 일 | DROP | 반영: findings/v33audit_2026-11-01 | handoff/V33FIX_loop.md:184 |
| VF-LP4-8 | KICK.md(손으로 돌릴 때 문구)는 반복 번호를 없는 runs\runs.log에서 읽으라고 하고 정지 규칙이 없다. 이 묶음의 파일이 | V33FIX 남은 일 | DROP | 반영: KICK.md 고침 | handoff/V33FIX_loop.md:185 |
| VF-LP4-9 | 실제 Codex 호출은 하지 않았다. | V33FIX 남은 일 | DROP | 기록 문장. 할 일 없음 | handoff/V33FIX_loop.md:186 |
| VF-LPI-1 | G1·E10을 done으로 정했지만 두 과제의 coverage(runs\G1_coverage.md, runs\E10_coverage.md | V33FIX 남은 일 | FINAL-SHOULD | BL-23 | handoff/V33FIX_loop.md:252 |
| VF-LPI-2 | 기존 v3 관문 기본 참조의 PASS 확인은 2차 정책 묶음 결과를 보고 통합 때 Claude가 한다. 그 전에는 루프 문서 어디에도 PASS로 | V33FIX 남은 일 | DROP | 반영: G1 카드 07:40 확인 | handoff/V33FIX_loop.md:253 |
| VF-LPI-3 | R-E-wt hygiene .gitattributes 커밋과 옮긴 clone의 영구 삭제는 1차와 같이 도현님 몫이다(커밋 금지, 영구 삭제 | V33FIX 남은 일 | FINAL-MUST | 커밋은 BL-01, 삭제는 BL-41 | handoff/V33FIX_loop.md:254 |
| VF-LPI-4 | 실제 Codex 호출, Go, pytest, 관문, 벤치는 이 묶음 범위가 아니라 돌리지 않았다. 이 묶음은 gen33에 쓰지 않았다. gen3 | V33FIX 남은 일 | DROP | 기록 문장. 할 일 없음 | handoff/V33FIX_loop.md:255 |
| Z1-W1-B10 | W1 B10 GE 기준 121행동 Z1 적용 대기 | bench_rules 3절 적용 대기 | DROP | 후보 판정용. 후보 평가 종료로 무의미 | gen33/docs/V33FIX_bench_rules.md:76 |
| Z1-W1-c6000 | W1 c6000 고손실 기준 114행동 Z1 적용 대기 | bench_rules 3절 적용 대기 | DROP | 후보 판정용. 후보 평가 종료로 무의미 | gen33/docs/V33FIX_bench_rules.md:76 |
| Z1-M1 | M1 hold/m1 대 hold/l1 4셀 Z1 적용 대기 | bench_rules 3절 적용 대기 | DROP | M1 DROP | gen33/docs/V33FIX_bench_rules.md:76 |
| Z1-O2 | O2 세계 진단 4대조 Z1 적용 대기 | bench_rules 3절 적용 대기 | DROP | O2 DROP | gen33/docs/V33FIX_bench_rules.md:76 |

## 7. 결정 D1~D52

| ID | 제목 | 현재 상태 | 분류 | 이유 | 근거 위치 |
|---|---|---|---|---|---|
| D1 | GitHub에 push할지 | 아직 기본값 | USER | 하지 않음(gen33). R-E main push만 11-05에 함. BL-32 | state/DECISIONS_NEEDED.md:9 |
| D2 | 봉인 원자료·바이너리를 GitHub Release에 올릴지 | 아직 기본값 | USER | Release 안 올림, padfec_archive 로컬 보존. BL-35 | state/DECISIONS_NEEDED.md:10 |
| D3 | v3.3 확증 측정(봉인, 보류 추첨, 실행) | 아직 기본값 | USER | 확증 측정 안 함. BL-40 | state/DECISIONS_NEEDED.md:11 |
| D4 | 최종 보고서에 어느 알고리즘 판을 쓸지(v3.1 / v3.3) | 아직 기본값 | USER | 보고서는 v3.1 봉인 수치, v3.3.1-dev는 시뮬레이션으로만. BL-31 | state/DECISIONS_NEEDED.md:12 |
| D5 | 비교 실험의 gen-2 기준 | 기본값 유지로 닫음 | DROP | 동결 바이너리 d98b05d7 | state/DECISIONS_NEEDED.md:13 |
| D6 | pq_afec_next의 p3 교대 측정을 정본에 넣을지 | 아직 기본값 | USER | next 정본에 안 넣음, 보관 브랜치만. BL-39 | state/DECISIONS_NEEDED.md:14 |
| D7 | 외부 소스 내려받기(quiche 등) | 기본값 유지로 닫음 | DROP | 내려받기 안 함. X7 DROP 사유 | state/DECISIONS_NEEDED.md:15 |
| D8 | 팀원 공유 | 아직 기본값 | USER | 팀원 공유 안 함. BL-44 | state/DECISIONS_NEEDED.md:16 |
| D9 | 볼트(C:\dev\claude_brain) 기록 | 기본값 유지로 닫음 | DROP | 볼트는 Claude만. BL-24 | state/DECISIONS_NEEDED.md:17 |
| D10 | 과제명(원제목 대 09-03 재작성본, 승인 기록 없음) | 아직 기본값 | USER | 루프 문서는 PAD-FEC v3.3으로만. BL-33 | state/DECISIONS_NEEDED.md:18 |
| D11 | 저장소 공개 여부 | 아직 기본값 | USER | 비공개. BL-32 | state/DECISIONS_NEEDED.md:19 |
| D12 | X9(PTO 비율 재측정) 결과를 변경보고·덱에 반영할지 | 아직 기본값 | USER | X9 결과를 덱·변경보고에 반영 안 함. BL-44 | state/DECISIONS_NEEDED.md:20 |
| D13 | 회신 없음과 PTO를 첫 비행 전멸로 처리할지 | 기본값 유지로 닫음 | DROP | L1 전멸 처리. 활성 c1 경로가 쓰는 값이라 유지 | state/DECISIONS_NEEDED.md:26 |
| D14 | W0에 없는 C1 회신을 L1에서 어떻게 평가할지 | 기본값 유지로 닫음 | DROP | 수동 C1 관측 모형. 평가 문서 단서로 유지(판정 쪽은 D47로 대체) | state/DECISIONS_NEEDED.md:27 |
| D15 | L2 목적지 EPS의 사전 강도와 관측 방식 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:29 |
| D16 | L3 CUSUM 반응·관측 준비·감지 지연 집계 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:33 |
| D17 | J6 margin·A_pre 관측 창·범위 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:37 |
| D18 | L5 응답 관측·혼합·불완전 역사 자료 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:41 |
| D19 | J7 전체 관문과 G1 선행 관계의 순환 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:45 |
| D20 | M1 수신 기한과 보관 한도 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:47 |
| D21 | S4 gen-2 캐시 판본과 이전 상태 | 기본값 유지로 닫음 | DROP | S4 캐시 판본. 활성 코드가 쓰므로 유지 | state/DECISIONS_NEEDED.md:53 |
| D22 | T1 고정 인증서의 서명 방식 | 기본값 유지로 닫음 | DROP | T1 인증서. 활성 테스트베드가 쓰므로 유지 | state/DECISIONS_NEEDED.md:55 |
| D23 | T4의 HCT 이후 C1 수집 대기 | 기본값 유지로 닫음 | DROP | feedback-wait 1 s. T7 계획에 적어야 하므로 유지 | state/DECISIONS_NEEDED.md:57 |
| D24 | T5 복호기 색인과 보관 상한 | 기본값 유지로 닫음 | DROP | T5 복호기 상한. 활성 테스트베드가 쓰므로 유지 | state/DECISIONS_NEEDED.md:59 |
| D25 | T5의 서버 UDP 경로 선택 | 기본값 유지로 닫음 | DROP | UDP 경로 oob. X3 비교 때 명시 | state/DECISIONS_NEEDED.md:61 |
| D26 | T5의 k 추정에 따른 첫 묶음 해제 | 기본값 유지로 닫음 | DROP | cached_k 첫 묶음. 활성 테스트베드가 쓰므로 유지 | state/DECISIONS_NEEDED.md:63 |
| D27 | E18의 묶음 관측 범위 | 기본값 유지로 닫음 | DROP | E18 관측 범위. 유지 | state/DECISIONS_NEEDED.md:65 |
| D28 | T6의 응답 전 후속 묶음 보호 (2026-11-02 D43으로 대체됨: qamp -retrans-layout 기본값은 다 | 기본값 유지로 닫음 | DROP | D43으로 대체됨 | state/DECISIONS_NEEDED.md:67 |
| D29 | T3 pad·dup의 바이트와 계수 | 기본값 유지로 닫음 | DROP | T3 pad·dup. X1이 쓰므로 유지 | state/DECISIONS_NEEDED.md:69 |
| D30 | T3 ClientHello padding 입력과 Initial 크기 | 기본값 유지로 닫음 | DROP | T3 k-inflate. X1이 쓰므로 유지 | state/DECISIONS_NEEDED.md:71 |
| D31 | T2 토큰·티켓 공유와 수집 대기 | 기본값 유지로 닫음 | DROP | T2 토큰. X4가 쓰므로 유지 | state/DECISIONS_NEEDED.md:73 |
| D32 | O2 미확인 업링크·경주 구간과 추정기 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:77 |
| D33 | J5의 iid 경계·추정 사전·상태 이월 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:81 |
| D34 | O3 RTT 표본과 변동 여유 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:85 |
| D35 | O4 현재 ClientHello의 k | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:91 |
| D36 | J3 두 단계 실패 비용과 종료 근사 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:101 |
| D37 | M4 토큰·Retry와 연결당 추가 묶음 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:109 |
| D38 | M4 관측 캐시와 실행 전 TLS 분기 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:111 |
| D39 | J8 서버 프로파일·하향 손실 | 후보 기본값. 후보 평가 종료로 닫음 | DROP | 해당 계약 문서 그대로 | state/DECISIONS_NEEDED.md:113 |
| D40 | T1 시험용 개인키가 남은 git 이력의 공개 전 처리 | 아직 기본값 | USER | 이력 재작성 안 함. BL-32 | state/DECISIONS_NEEDED.md:119 |
| D41 | 활성 정책 v3.3.1-dev 설계 | Claude가 정함. 되돌릴 근거 없음 | DROP | v3.3.1-dev 설계 | state/DECISIONS_NEEDED.md:127 |
| D42 | git 이력 | Claude가 정함. 되돌릴 근거 없음 | DROP | gen33 이력 유지 | state/DECISIONS_NEEDED.md:128 |
| D43 | 재전송 모양 기본값 | Claude가 정함. 되돌릴 근거 없음 | DROP | repeat_first 기본, sealed31 | state/DECISIONS_NEEDED.md:129 |
| D44 | 서로 다른 두 행동의 영분산 해소 | Claude가 정함. 되돌릴 근거 없음 | DROP | Z1 | state/DECISIONS_NEEDED.md:130 |
| D45 | J6 재판정의 범위 | Claude가 정함. 되돌릴 근거 없음 | DROP | J6 재판정만 | state/DECISIONS_NEEDED.md:131 |
| D46 | G1·G2 재정의와 의존 교착 해소 | Claude가 정함. 되돌릴 근거 없음 | DROP | G1·G2 재정의 | state/DECISIONS_NEEDED.md:132 |
| D47 | 대칭 채택 기준 | Claude가 정함. 되돌릴 근거 없음 | DROP | 대칭 채택 기준 | state/DECISIONS_NEEDED.md:133 |
| D48 | L5 역사 관문 | Claude가 정함. 되돌릴 근거 없음 | DROP | L5 역사 관문 대체 | state/DECISIONS_NEEDED.md:134 |
| D49 | 후보 상태 정리 | Claude가 정함. 되돌릴 근거 없음 | DROP | 후보 상태 정리 | state/DECISIONS_NEEDED.md:135 |
| D50 | T7 실측(그 뒤 X 측정 포함)에서 클라이언트 Initial 크기 W를 v3.3.1-dev 패리티 상한 아래로 잡을지 | 아직 기본값 | USER | W 1280 명시. 상한 위 W는 패리티 없음 셀로 따로. BL-36 | state/DECISIONS_NEEDED.md:143 |
| D51 | B6(고분산 c1 셀)의 seed 수를 60개(seed 31~90)로 늘리자는 제안을 확정할지 | 아직 기본값 | USER | seed 31~50 유지. 후보 평가 종료로 실질 무의미. BL-37 | state/DECISIONS_NEEDED.md:144 |
| D52 | 쓸모없어진 gen33 g3/l1_go_reference_gen.py와 g3/v33/E12_l1_reference_v1.j | 아직 기본값 | USER | 지우지 않음. BL-38 | state/DECISIONS_NEEDED.md:145 |

## 8. 기각되거나 blocked인 후보 14개: 코드 흔적과 최종 문서

공통 처리(BL-04). 활성 `padfec/`, `padfec3/`에는 후보 흔적이 없다(`grep -E "cusum|eps_alpha|eps_beta|beta_a|lead_hold|natural_k|minimax|gilbert" padfec3/*.py` 출력 0줄). 나머지는 검증 묶음 manifest와 시험이 경로로 묶여 있어 옮기거나 지우지 않는다. `g3/v33/CANDIDATE_ARCHIVE.json`에 후보마다 파일 목록과 상태를 적고, 시험 하나가 그 파일의 존재와 활성 코드의 비참조, 후보 플래그의 기본 off를 고정한다. 부정 결과 문단은 전부 `docs/FINAL_rejected_candidates.md`(BL-03)에 쓰고, 보고서 `content.py:202` 뒤에는 묶어서 두세 문장만 넣는다(BL-09). 수치는 아래 근거 위치의 원자료에서 다시 읽었다(`recheck_candidate_numbers.py`).

| 후보 | 상태 | 남은 흔적(gen33 안, 모두 활성 경로 밖) | 시도한 것 | 왜 안 넣었나 | 근거 |
|---|---|---|---|---|---|
| L2 | done(EPS 버림) | snapshots L2_v1·L2_fixed_epsilon_v1, ablation_sources/L2_fixed_epsilon_v1, bench_learning_l2*.py, candidate_tests/l2_*, tests/test_v33_l2_*·test_v33_learning_l2_report, docs/L2_*(5개), validation L2_* 9개 | 목적지별 EPS Beta(1,999) | none B8_j10 -1.568806 ms, 보정 상한 1.721694로 비열등 미확정. 이득은 seed 46 하나(-31.376 ms)에서 왔다 | L2_benchmark_v1.json comparisons/113 |
| L3 | blocked | snapshots L3_v1·beta_only·guard_only·record_only, ablation_sources 3개, bench_learning_l3*.py, candidate_tests/l3_*, tests/test_v33_l3_*, docs/L3_*, validation L3_* 9개 | CUSUM 감시와 β 반응 | c1 B8_j20 비열등 실패, B1 절대 후회 미확정. record_only 팔만 v3.3.1-dev c1 경로로 들어갔다(0.093952, 상한 0.127028) | L3_benchmark_v1.json groups/0, V33FIX_benchmark_v1.json |
| L5 | blocked | snapshots L5_v1·L5_single_v1, ablation_sources/L5_single_v1, bench_learning_l5*.py, policy_bridge_l5.py, policy_worker_l5.py, server_response_observer.py, tests/test_v33_l5_*·test_v33_learning_l5*, docs/L5_*, validation L5_* 8개 | 서버 응답 S 추정과 혼합 | c12000 none +24.911063 [23.775437, 26.046689], c1 +24.893233 ms. 1461 B 패리티가 1452 B 수신 한도에서 잘렸다. 역사 입력 없음 | L5_benchmark_v1.json comparisons/119·134 |
| J1 | blocked | snapshots J1_v1·J1_cost_only_v1, ablation_sources/J1_cost_only_v1, bench_learning_j1*.py, tests/test_v33_j1_*·test_v33_learning_j1*, docs/J1_*, validation J1_* 5개 | 2-RTT 둘째 왕복 꼬리 | none 3셀(B7, B8_j10, B8_j20) 미확정, c1 감소 조건 없음. seed 46이 -36.421 ms로 뒤집힘 | J1_benchmark_v1.json comparisons/113 |
| J6 | blocked | snapshots J6_v1·J6_margin_zero_v1, ablation_sources/J6_margin_zero_v1, bench_learning_j6*.py, policy_bridge_j6.py, policy_worker_j6.py, v33fix_j6_rejudge.py, tests/test_v33_j6_*·test_v33_learning_j6*, docs/J6_*, validation J6_* 5개 | δ 후보에 A_pre와 margin 30 B | c6000 -2.47348·-2.50647 ms. Z1 뒤 원래 규칙은 만족[-2.549763, -2.397198]. 규칙 2.1에서 none B6 [5.121544, 7.606734] 실패. exact 계수면 약 +120 ms | J6_benchmark_v1.json comparisons/13·133, V33FIX_J6_rejudge_v1.json |
| J7 | blocked | g3/v33/candidates/J7_wire_v1·J7_wire_on_L1_v2, snapshot J7_v1, bench_j7*.py, validate_j7*.py, tests/test_v33_j7_*, docs/J7_*, validation J7_* 2개 | 패리티 크기 W+46+6k 고정 | 60셀 중 58 통과. 39 B none/B6 [-0.546, 0.505854], 46 B none/B8_j20 +2.354217 [-2.585862, 7.294295]. seed 46 +47.084. 1452 B 상한만 활성에 넣음 | runs/J7_factorial_report_v1.json comparisons/6·54 |
| M1 | blocked | candidate_sources/M1_v1, snapshot M1_v1, bench_m1*.py, bench_action_pool_m1.py, bench_oracles_m1.py, oracle_m1.py, worldsim_m1.py, worldparams_m1.json, world_receiver_m1.py, hold_*.py, validate_m1*.py, m1_*.py, render_m1_fixed.py, candidate_tests/m1_candidate.py, tests/test_v33_m1_*·test_v33_hold_*, Go hold.go·qamp_hold_*_test.go·-lead-hold 플래그 3개(기본 off), docs/M1_*, validation M1_* 11개 | 선행 패리티 보류 복호 | 주 120셀 82 통과·15 실패·23 미확정. hold 세계만 패리티 수신 뒤 송신을 재개한 결함과 (0,4,0) 비용 과소평가가 겹쳤다. 복구 불가 비행의 신용은 TTL로 사라진다 | runs/M1_disposition_v2.json performance_decision |
| O2 | blocked | uplink_reference*.py, uplink_world_diagnostic.py, tests/test_v33_uplink_*, docs/O2_*, plans/O2_world_v1.json, validation O2_* 2개 | 미확인 업링크 minimax | 모형 최대 6.503042445 ms. 세계 240대조 중 16개가 6.5 ms 하한 초과 | docs/O2_reference_result.md:7, O2_world_result.md:9 |
| J5 | blocked | ge_reference*.py, ge_world_diagnostic.py, tests/test_v33_ge_*, docs/J5_*, plans/J5_world_v1.json, validation J5_* 2개 | GE 버스트 비용 | B10에서 iid·known_burst·forced_burst3가 같은 행동이라 HCT 변화 0. 세계 64.562675 대 모형 58.464599, 잔차 6.098075 ms | runs/J5_world_disposition_v1.json |
| O3 | blocked | rtt_reference*.py, rtt_trace_audit.py, tests/test_v33_rtt_*, docs/O3_*, validation O3_* 2개 | 부풂 뺀 RTT 신호 | 198연결 453 갱신 중 보정 입력을 채운 표본 0. 변동 4배 여유가 합성 2-RTT의 69.83~84.11%를 1-RTT로 분류 | docs/O3_trace_result.md:10,28 |
| O4 | blocked | natural_k_*.py, current_k_candidate.py, current_k_replay.py, tests/test_v33_natural_k_*·test_v33_current_k_candidate, docs/O4_*, validation O4_* 3개 | 현재 ClientHello로 k 계산 | W1 900실행·1,233,000연결 재생에서 결정이 같아 차이가 구조적으로 0. 후보별 k 변화와 송신 전 훅 없음 | docs/O4_current_result.md |
| J3 | blocked | recovery_*.py, tests/test_v33_recovery_*, docs/J3_*, validation J3_* 3개 | 실패 가지 두 단계 비용 | 참조 2% -49.257467 ms(표본 5건)로 ±10 ms 미통과, 15% +1.545667 ms. 72문맥 선택 변화 0. 세계와 -29.084599 ms | docs/J3_reference_result.md:13,23 |
| M4 | blocked | revisit_*.py, tests/test_v33_revisit_*, Go revisit.go·revisit_guard.go·qamp_revisit_*_test.go·-revisit-guard·-decoder-support(기본 off), docs/M4_*, plans/M4_guard_v1, docs/server_support_signal.md, validation M4_* 3개 | 토큰·Retry 인식 | 168연결 중 156개만 재생(12개 첫 원본 소거). 고정 팔 전송 검증까지이고 실제 입력 훅·W1·Go 채택 없음 | docs/M4_cache_result.md:9,11, M4_guard_result.md:15 |
| J8 | blocked | server_profile.py, server_cost_reference.py, server_world_trace.py, j8_pto_impact.py, tests/test_v33_server_*, docs/J8_*, validation J8_* 3개 | 서버 프로파일과 하향 손실 | 120조건 중 24조건에서 PTO 만료 이동 44건, 최대 192.184 ms. p_d>0은 J=None. W1 B7 판정은 안 바뀜 | docs/J8_downlink_result.md, V33FIX_world.md 4절 |

## 9. 도현님이 정할 결정과 기본값

모든 결정은 기본값으로 루프를 계속할 수 있다. 다만 push, 제출, 인적 사항 입력은 루프가 하지 않는다. D13~D40의 후보 계약값은 후보 평가를 끝내므로 물을 필요가 없어 7절에서 닫았다.

| 항목 | 결정 | 기본값 | 기본값으로 루프 진행 |
|---|---|---|---|
| BL-31 | 최종 보고서 알고리즘 판 (D4) | 보고서는 v3.1 봉인 수치, v3.3.1-dev는 시뮬레이션으로만 | 가능 |
| BL-32 | push, 공개 여부, 이력 처리 (D1,D11,D40) | 하지 않음(gen33). R-E main push만 11-05에 함; 비공개; 이력 재작성 안 함 | 가능 |
| BL-33 | 과제명 (D10) | 루프 문서는 PAD-FEC v3.3으로만 | 가능 |
| BL-35 | 원자료 보존 위치 (D2) | Release 안 올림, padfec_archive 로컬 보존 | 가능 |
| BL-36 | 실측 W (D50) | W 1280 명시. 상한 위 W는 패리티 없음 셀로 따로 | 가능 |
| BL-37 | B6 seed 수 (D51) | seed 31~50 유지. 후보 평가 종료로 실질 무의미 | 가능 |
| BL-38 | 옛 E12 생성기 삭제 (D52) | 지우지 않음 | 가능 |
| BL-39 | pq_afec_next 합류 (D6) | next 정본에 안 넣음, 보관 브랜치만 | 가능 |
| BL-40 | v3.3 확증 측정 (D3) | 확증 측정 안 함 | 가능 |
| BL-44 | 팀원 공유, X9 결과의 덱 반영 (D8,D12) | 팀원 공유 안 함; X9 결과를 덱·변경보고에 반영 안 함 | 가능 |
| BL-30 | T7 뒤 X 측정을 이번 루프에서 돌릴지 | G2·T7 뒤 X1 → X6 스모크 → X3 → X2 → X9 → X6 본측정 → X4 순서로 합계 8시간 안에서 돌린다 | 가능. 안 돌리면 BL-09의 문장만 그대로 |
| BL-34 | 황요한 역할(ROLE3) | 【입력 필요】 칸 그대로. 지어 쓰지 않는다 | 가능. 제출 전 도현님 필수 |
| BL-41 | WSL stage 53개·test_artifacts 4,005개·source-* 61개·hygiene-clone-check_moved 삭제 | 지우지 않는다 | 가능 |
| BL-42 | 보고서 칸: AI 활용(Fig. 1·2 PaperBanana 문구), 인적 사항, 지도교사 체크리스트, 질문동기 | 손대지 않는다. AI 활용 칸은 도현님 지시로 유지 | 가능. 제출 전 도현님 필수 |
| BL-43 | 예산 정합성, 정정 보고 제출, 발표 슬라이드, 신청서 본문, 영문 초록, 논문 초고, 중간발표 덱 부재 | 루프 범위 밖 | 가능 |
| BL-45 | gen-2 미결: 버스트3 불일치, p18 검사 4의 자, Go 1.26.5/1.26.6, run_v3.sh netem | 새로 재지 않고 한계와 정오표에 적는다 | 가능 |
| BL-46 | exact 계수 팔 등록, G3h 등가 돌연변이, replay_g3 1452 B 표시 | 등록 안 함, 수용, 문서에만 적음 | 가능 |
