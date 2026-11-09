# G-claims-frame

## summary
A1의 REPORT_CLAIMS_v33.md(= runs/A1_report_final_v2.md, 바이트 동일, 커밋 d67717d9b)는 숫자가 정확하다. 원 출처와 직접 대조한 값 약 40개(봉인 저널에서 다시 계산한 H1 평균 8개와 차이 4개, 판정 JSON의 구간 4개, p18·p17·p3·p15 값, 정책 코드로 다시 계산한 pad 문턱 4.9783e-5와 expected_rounds, 봉인 해시 일치 수, 인증서 파일 바이트, Cloudflare 7.8 kB 정의) 가운데 틀린 것은 없었다. 볼트가 정정한 p18 값(103.535228/51.711570/+51.823658 ± 0.113620)과 PTO 12.0% 대 10.4%("재현 안 됨, 유의차 없음은 기각이 아님")는 맞게 다뤘다. 정정 35행이 가리키는 파일·행 35개도 모두 맞았고, 맞던 문장을 틀리게 바꾼 행은 없었다. 다만 35행 가운데 실제 정정은 18행이다. 14행은 과거 기록에 붙이는 상태 주석이고, 3행은 이미 맞는 문장을 다시 쓴 것이다. "v3.3이 낫다"류의 과장은 102개 docs와 MORNING_REPORT 어디에도 없었다. 결함은 세 가지다. (1) 허용 주장과 금지 표가 볼트의 금지 목록 일부를 빠뜨렸다: 큰cert H1의 IW 단서, "증폭 병목을 우리가 밝혔다", "추가 비용 없는 FEC"와 용량 부등식 60.0/69.0 B, "H1 이득은 대부분 신용 바이트 기제". (2) README가 코드와 모순된다(v3.2-dev·상태 3 대 실제 v3.3-dev·상태 4). (3) 문서 가독성이 낮다. 연구 틀에서 가장 큰 문제는 63반복(일시 중단을 뺀 실작업 약 27시간)의 약 81%가 학습층·세계 시뮬레이터에 쓰였고 측정은 0이라는 점이다. Claude가 짠 의존 구조(X*←T7←G1←학습 후보 전부 채택)에서 학습 후보 6개가 미채택(blocked)이 되자, X1(신규성 방어)·X9(방향 전환 근거)·X6이 원리상 시작될 수 없었다. Codex는 규칙을 지켰지만 이 봉쇄를 도현님 결정 항목으로 올리지 않았다. 결정 D1·D3·D6·D8·D9·D12는 지켰다. 루프 기간에 볼트에서 바뀐 6건은 모두 다른 Claude 세션(AlphaFold, mTOR, AI_TOP_100, PowerGuard)이 쓴 것이다.

## verdict_improved
부분적으로 나아졌다. 보고 주장의 위생은 나아졌지만, 연구 주장의 증거는 v3.2-dev 기준선과 같다. 기준선(gen32)에는 주장 목록 문서가 없었고 README의 일반적인 단서뿐이었다. 이제는 원 출처와 자릿수까지 맞는 조건부 주장 문서가 있다. 그 안에 낡은 팀 문서 문장 18건의 정정, 실측한 ML-DSA 인증서 바이트, TTLB 보고 틀이 들어 있고, 직접 대조한 값 약 40개에서 오류는 0건이다. 반면 A1은 과거 봉인 자료를 다시 정리한 것이고, 새 네트워크 측정은 하나도 없다. 그래서 연구 핵심 주장(패딩 대신 패리티, 같은 바이트 비교)의 증거 강도는 그대로다. 볼트의 금지 목록 가운데 IW 단서, 신규성 축소, 추가 비용 없는 FEC(60.0/69.0 B)가 빠졌고, README는 코드보다 낡았다(v3.2-dev 대 v3.3-dev). 그러니 '보고서를 쓸 준비'는 나아졌지만 '보고서에 쓸 새 결과'는 늘지 않았다.

## frame_fit
A1 문서 자체는 연구 틀에 맞는다. 패리티의 값을 '복구'보다 '증폭 신용'으로 보는 관점(선행 몫은 신용 전용, 뒤 몫은 복구)을 따르고, RFC 9000 §8.1 계수 규범과 quic-go 판본 한정을 지키며, H1을 봉인 조건으로 한정하고, H2·H3 실패와 H4 기여 없음을 그대로 적었다. MTC 띠와 dup 대안처럼 우리 주장을 약하게 만드는 사실도 스스로 적었다. 그러나 금지 표가 볼트 목록 일부를 빠뜨려(G-E1) 틀의 경계가 완전하지 않다. 루프 전체를 보면 연구 질문에서 벗어난 비중이 크다. 일시 중단을 뺀 실작업 약 1,630분 가운데 81%(44반복)가 학습층·세계 시뮬레이터 후보에 쓰였고, 그 14개 과제는 모두 미채택(blocked)으로 끝났다. 채택된 것은 L1(C1 회신 학습)뿐이다. 연구의 신규성 방어 실험 X1, 방향 전환 근거 재측정 X9, 세대 비교 X6은 0반복이다. 측정에 필요한 고정 팔(T3 pad·dup·k-inflate, T2 토큰·재개)은 만들어 두었다. 이 공백을 Codex의 이탈로만 보기는 어렵다. Claude가 짠 의존 구조(X*←T7←G1←학습 후보 전부 채택)와 실행 순서(학습 묶음이 측정보다 앞)가 측정을 막았고, Codex는 규칙을 지켰다. 다만 막힌 사실을 결정 항목으로 올리지 않은 것(G-E2)은 Codex의 보고 공백이다. 다음 루프에서는 X1·X9를 G1과 분리한 고정 팔 개발 측정으로 먼저 돌려야 연구 틀에 맞는다.

## errors

### G-E1 [medium] 주장 문서가 볼트의 '쓰면 안 되는 말' 일부와 핵심 단서를 빠뜨림 (repro=True)
REPORT_CLAIMS_v33.md는 이 연구의 '쓸 수 있는 말·쓰면 안 되는 말'을 정리하는 문서다. 그런데 7행의 허용 주장(v3.1 봉인 조건에서 H1 두 조건 충족)에 initial cwnd 단서(quic-go IW 32 대 RFC·quiche·msquic 10)가 없다. 볼트는 이 단서 없이 큰cert H1을 쓰는 것을 금지했다. 금지 표(28~40행)에는 '추가 비용 없는 FEC'(용량 부등식 위반 12/12, 최소 초과 08-27 기준 60.0 B, 10-01 p1_flight 기준 69.0 B)와 'PQ 증폭 병목을 우리가 밝혔다'(신규성은 Nawrocki·McManus를 잇는 한 수로 좁혀졌다)가 없다. RESULT_stage3의 'v3.1의 수정이 이득을 늘렸다고 말하지 않는다'(v3.0과 같은 크기)와 볼트 10-02의 '이득 대부분은 신용 바이트 위치·개수, 패딩에 가까운 기제' 단서도 H1 문장에 붙지 않았다. 그 결과 이 문서만 보고 쓰면 H1이 '패리티의 고유 가치' 증거처럼 읽힐 수 있다. '같은 바이트가 신용과 복구를 함께 산다'는 '항상'을 붙여 약하게 바꿔 실었다(32행). 다만 이 항목들 다수는 A1 카드의 근거 목록에 없었으므로, 과제 설계(Claude)에도 일부 책임이 있다.

EVIDENCE: grep -n -i 'IW|cwnd|Nawrocki|McManus|신규성|추가 비용|비용이 없|69.0|60.0' docs/REPORT_CLAIMS_v33.md → 0건. 볼트 우리 학술 노트 86·127·154·172행(금지 목록), 193~194행(69.0 B 정정). 직접 계산: C:\dev\pq_afec\experiments\results\p1_flight.json capacity_checks 최소 초과 69.0 B(X25519MLKEM768, ips 1450, C=1457, capacity 1388.0), any_inplace_feasible=False. pq_afec_gen31/g3/RESULT_stage3.md:91. FINDINGS_INDEX.md에는 IW 항목이 아예 없다(grep 0건).

FIX: 금지 표에 'IW 단서 없는 큰cert H1', 'PQ 증폭 병목 발견 주장', '추가 비용 없는 FEC(용량 부등식, 60.0 B@08-27·69.0 B@10-01, 설정과 함께 인용)'를 추가한다. 7행 허용 문장에 'token·resumption 끔, quic-go IW 32, 이득 대부분은 신용 바이트 기제이며 패딩 대비 고유 몫은 X1 전 미확인'을 붙인다.

### G-E2 [medium] 측정 사슬 전체가 막힌 사실을 결정 항목으로 올리지 않음 (repro=True)
X1(같은 바이트 패딩 대 패리티, 신규성 방어), X9(PTO 재측정, 방향 전환 근거), X6(v3.3 대 v3.1 대 gen-2), X4가 모두 todo로 남았다. 규칙상 X*는 T7 뒤에, T7은 G1 뒤에 시작한다. G1은 L1·L2·L3·L4·J1·J2·J6·L5·J7이 모두 done이어야 시작할 수 있다. 그런데 L2·L3·J1·J6·L5·J7은 후보 미채택으로 blocked였고, L4·J2는 그 뒤라 시작하지 못했다. 그래서 반복 25 이후로는 측정이 원리상 불가능했다. Codex는 D19에서 J7/G1 순환만 풀었다. MORNING_REPORT 262행에는 'G1 전체와 미채택 학습 후보의 의존은 해제하지 않는다'고 적었지만, '도현님 결정이 필요한 것' 절에는 이 봉쇄를 올리지 않았다. 근본 원인은 Claude가 설계한 과제 의존 구조다.

EVIDENCE: LOOP_STATE.json: G1 depends [L1,L2,L3,L4,J1,J2,J6,L5,J7], T7 depends [G1,G2,S4,T1,T4], X1 [T7,T3], X9 [T7,T4], X6 [T7]. 상태 집계 done 25·blocked 14·todo 49. TASKS.md:9 '측정(X*)은 G1·S4·T7이 끝나기 전에는 시작하지 않는다'. MORNING_REPORT.md:262, 423~431. history 63반복: 학습·세계(W·L·J·M·O·E12) 44반복, 계측 T 11, 준비 S 6, 문서 A 2, 측정 0. 반복 14(1675분)의 대부분은 사용 한도 중단이었다. 이를 빼면 실작업 1630분 중 학습·세계 1318분(81%), T 196분(12%), S 91분, A 24분이다.

FIX: 아침 보고에 'G1 의존 때문에 X1·X9·X6이 원리상 실행 불가'를 결정 항목으로 올린다. G1 의존을 '채택된 L1만'으로 줄이는 안, 또는 X1·X9를 G1과 무관한 고정 팔 개발 측정으로 분리하는 안을 도현님께 제시한다.

### G-E3 [medium] README가 코드와 모순된다 (정책·상태 버전, 활성 학습층) (repro=True)
gen33 README 3행은 '정책 버전은 아직 v3.2-dev, 저장 상태 버전은 3'이라고 적는다. 실제 코드는 POLICY_VERSION = "v3.3-dev"이고 상태 버전은 4다. Go 쪽 p3PolicyVersion도 v3.3-dev다. README 5행 이후의 학습층 설명은 v3.2의 hazard 전이 설명 그대로이고, 활성 정책이 된 L1(C1 도착 증거 학습)은 언급하지 않는다. README는 반복 3(S3)에서만 고쳐졌고 그 뒤 59반복 동안 갱신되지 않았다.

EVIDENCE: README.md:3 대 padfec3/learn3.py:26 POLICY_VERSION = "v3.3-dev", experiments/quicbed/policy3.go:56, docs/L1_learning.md:3('상태 버전은 4, 정책 버전은 v3.3-dev'). git log 90859b973..HEAD -- README.md → 1fb785ec4(10-30 01:45, S3) 하나뿐이다.

FIX: README의 버전·상태 판본을 v3.3-dev·4로 고치고, 활성 학습층(L1, C1 회신 필요)과 미채택 후보 목록을 한 단락으로 적는다.

### G-E4 [low] '정정 35행' 가운데 실제 정정은 18행이다 (repro=True)
35행 인용은 모두 맞는 파일·행을 가리켰고, 맞던 문장을 틀리게 바꾼 행은 없었다. 성격별로 나누면 이렇다. 실제 정정(원문이 틀렸거나 현재 사실로 낡음) 18행: v0.1:12, v0.2:12, 선행연구:105·278, rs.py:1, README:154·164·371, R-E README:24, 명세:508·522·765, policy.py:279·833·1789, PROTOCOL_stage3:3, 볼트 노트 72·97행. 과거 기록·수정 대기 항목에 붙이는 상태 주석 14행: 수정 대기 49·110·118·129·197·215·250·257, 인계:30, 실험환경:65, run_v3.sh:27, SEAL_stage0·2, 10-29 로그:35. 이미 맞는 원문을 다시 쓴 3행: 실험환경 대조.md:31은 이미 정정이 붙어 있고, 볼트 09-07 로그 94행은 이미 9.09%를 적었으며, 09-17 로그 87행은 이미 m=1 1520/1600을 적었다. MORNING_REPORT와 커밋 메시지의 '정정35행'은 정정 건수를 부풀려 보이게 한다.

EVIDENCE: scratchpad v33audit/G-claims-frame/rows.py로 A1_claim_sources_v3.json records 35개를 검사했다. 각 start 행의 원문이 current_text 첫 줄과 35/35 일치했고, source_sha256 19개는 A1 이후 변경 0이다. 원문 대조: 볼트 06 세션 로그/2026-09-07 …:94, 2026-09-17 …:87, pq_afec/docs/실험환경 대조.md:31~42.

FIX: 보고 문서에서 '정정 18행, 상태 주석 14행, 재확인 3행'으로 나눠 표기한다.

### G-E5 [low] 팀(고1 3명)이 읽기 어려운 문서 품질 (repro=True)
REPORT_CLAIMS에는 한글 바로 뒤에 숫자가 붙은 곳이 115곳 있다. 예: '18조건 중17조건', '평균 HCT는103.535228 ms와51.711570 ms', '차이는51.823658 ms'. 일부는 '버스트3'처럼 원래 붙여 쓰는 표기다. docs/*.md 전체로는 1,455곳이다. MORNING_REPORT에는 띄어쓰기가 거의 없는 줄이 있다(105행 'W1 [개발독립세계최종기준값,반복11]:19참조와81행동평가완료,…'). 새 docs 102개(3,103줄)에는 목차나 읽는 순서가 없고, 내부 ID(B1~B12, D13~D40, E1~E37, C1, W1)를 설명 없이 쓴다. S5_test_hygiene.md처럼 읽기 쉬운 문서도 있어 문서마다 편차가 크다.

EVIDENCE: python 정규식 [가-힣][0-9]: REPORT_CLAIMS_v33.md 115건, docs 전체 1,455건. MORNING_REPORT.md:105. ls docs | wc -l = 102이며 index·README 문서는 없다.

FIX: REPORT_CLAIMS의 숫자 앞 띄어쓰기를 고치고, docs/README.md에 읽는 순서와 ID 용어집을 둔다. 팀용 요약은 별도 한 쪽으로 만든다.

### G-E6 [low] H1 표의 '기존 95% 구간'이 판정에 쓰인 Holm 하한이 아니다 (repro=True)
표의 구간은 판정 JSON의 lo95/hi95(보정하지 않은 95%)다. H1 판정 규칙은 Holm(m=2) 하한 lb_holm을 썼다. run1 RTT200은 lo95 11.036674인데 lb_holm은 10.762043이고, run2 bigcert는 lo95 25.579746인데 lb_holm은 24.898871이다. RESULT_stage3:12는 run1을 Holm 하한으로 인용한다. 수치는 맞지만 표기가 판정 근거로 오해될 수 있다.

EVIDENCE: C:\dev\pq_afec_gen31\experiments\results\p31_gencompare_decisions.json /H1/run1/tests[1] lo95=11.036674487 lb_holm=10.762043369, /H1/run2/tests[0] lo95=25.579745808 lb_holm=24.898871044. REPORT_CLAIMS_v33.md:9~16.

FIX: 열 이름을 '보정 안 한 95% 구간'으로 바꾸고 Holm 하한 열을 추가한다.

### G-E7 [low] A1이 틀렸다고 한 MDS 설명이 gen33 자기 저장소에는 그대로 남음 (repro=True)
A1은 gen-2 afec/rs.py:1의 '반데르몬드 행렬을 systematic 형태로 행축약하면 MDS가 깨질 수 있다'를 정정 대상으로 올렸다. 이 정정은 수학적으로 맞다. 가역 행변환은 부호 자체를 바꾸지 않는다. 그런데 보호 대상이 아닌 gen33의 afec/rs.py 13행에는 같은 문장이 남아 있다. S4에서 머리말 1행과 r=1 XOR 행만 바꿨다.

EVIDENCE: grep -n 행축약하면 C:\dev\pq_afec_gen33\afec\rs.py → 13행. git diff 90859b973 HEAD -- afec/rs.py는 1행과 100~101행만 바꿨다.

FIX: gen33 rs.py 머리말의 해당 문장을 A1 정정문으로 바꾼다(코드 동작 변화 없음).

### G-E8 [low] T1이 시험용 개인키 PEM을 git 이력에 커밋했다 (D11 공개 시 위험) (repro=True)
T1 커밋 60a2f18f9가 개인키가 든 PEM 28개를 gen33에 추가했다. S5(3eef6a737)가 추적에서 지우고 D40으로 스스로 보고했지만, 이력에는 그대로 남아 있다. 시험용 키라 실제 위험은 낮다. 그러나 저장소를 공개하면(D11 미정) 이력 정리가 필요하다. A1이 추가한 PEM 12개에는 개인키가 없다.

EVIDENCE: git log --diff-filter=A -- '*.pem' → 60a2f18f9(T1), d67717d9b(A1). T1 PEM 첫 파일 git show에서 'PRIVATE KEY' 2건. 현재 추적 중인 A1 PEM 12개는 PRIVATE KEY 0건. DECISIONS_NEEDED.md D40.

FIX: 공개 결정 전에 공개용 새 사본을 만들거나 이력을 정리한다(D40 그대로 도현님 결정).

## changes
- gen33에 docs/REPORT_CLAIMS_v33.md(159행, 41,125 B)가 생겼다. runs/A1_report_final_v2.md·A1_report_final.md와 바이트 동일하며, 커밋은 d67717d9b(2026-11-01 08:52, 반복 63, A1 소요 17분)이다.
- README.md는 S3(1fb785ec4, 10-30 01:45)에서 한 번만 바뀌었다(제목 v3.3, gen33 경로, python -I -B, 빌드 정보 문장, 14줄 추가·15줄 삭제). '이 버전의 실제 성능은 아직 측정하지 않았다'는 유지됐다.
- gen33 docs에 새 문서 102개(3,103줄)가 추가됐다. 대부분 과제별 contract·result·disposition 문서다.
- A1 근거 자료가 handoff runs에 생겼다. A1_numeric_audit_v1.json(H1 재계산, p18·p17·p3·p15 추출, pad 문턱, q17 z 역산), A1_claim_sources_v3.json(35행, 원문 19개 SHA), A1_certificate_v1(OpenSSL 3.5.5로 만든 ML-DSA-44·65·ECDSA-P256 루트·중간·리프와 CV 서명, 개인키 제외), A1_pytest_v1(1792 통과, 2 건너뜀, 하위 4513), A1_coverage.md(26항목)다.
- REPORT_CLAIMS의 구성: 허용 주장(v3.1 봉인 H1 조건부), 금지 주장 표 12행, RFC 9000 §8.1 계수 규범, quic-go v0.61.0 범위, 인증서 크기와 합성 DER 대응표(C_eq, s0=1724 B 가정), MTC 계산 띠, p3 표류 한계, TTLB 보고 틀, 팀 문서 정정 30행, 볼트 정정 제안 5행이다.
- R-E 저장소: S2가 worktree 두 개(hygiene/2026-10-30, archive/next-2026-09-08)와 주석 태그 4개(gen2-fix-73aa420, gen2-frozen-4bab4a5, v3.1-stage3, v3.2-dev, 11-01 07:54)를 만들었다. main은 6bbd11f 그대로다.
- LOOP_STATE: 반복 63, done 25·blocked 14·todo 49·doing 1(R2)·skipped 1. X1·X4·X6·X9·T7·G1은 0반복이다. R2 초안(PROTOCOL_stage4_DRAFT.md)은 만들어지지 않았다.

## improvements
- [strong] 보고 숫자의 정확성이 원 출처 수준으로 검증됨 :: 직접 재계산 결과다. 봉인 저널 4개에서 H1 평균 8개와 차이 4개(28.009256, 12.382440, 28.919530, 10.330776)를 계층 동일 가중으로 다시 내서 6자리까지 일치했다. 판정 JSON의 lo95/hi95 4쌍 일치. p18 m2 103.535228·m4 51.711570·버스트3 100.163515−66.981337=33.182179 일치, 저장 예측 23.57 일치, 74,000/5 실패 일치. p17 oracle 0.0415±0.1605, 1.1675±1.2745, auto−best −3.751854 일치. p3 on2−off 0.232와 선형 표류 −0.3398~+0.3073(n·기울기 정의로 A1 값 재현) 일치. pad 문턱 4.97828e-05와 expected_rounds(k=2) 1.214766/1.188659/1.114800/1.072777을 gen33 정책 코드로 재현했다(gen-2 policy.py와 CRLF 정규화 후 동일). 봉인 해시 일치 수 gen31 stage0 2/3·5/6, stage2 22/29·7/9, stage3 31/31·14/14, gen3 전부 일치. 인증서 DER 파일 크기 9개와 산술(C_eq, S, 8832 B, 1291~1341 B) 일치. 불일치 0건이다.
- [strong] 볼트가 정정한 값과 방향 전환 근거를 맞게 다룸 :: p18 옛 값 106.7/54.6/+52.13 대신 103.535228/51.711570/+51.823658 ± 0.113620을 썼다(볼트 193행과 일치). PTO 12.0% 대 10.4%와 z=0.79는 '유효 분모로 재현 못 함, 유의차 없음을 기각으로 쓰지 않음, X9 틀만 남김'으로 다뤘다(q17: z=0.79는 그룹당 약 485일 때만, 볼트 212·235행과 일치). gen-2 17/7(첫 실행, 봉인 RESULT_stage3:97)과 최종 18/6(p16 재실행 6/6 통과, results/p16_uplink.json)을 구분했다.
- [moderate] 팀 문서의 실제 오류 18건을 근거와 함께 짚음 :: destCache가 Go에 있음(v0.1·v0.2:12, 선행연구:278), '클라이언트만 고쳐 배포' 불성립(선행연구:105), MDS 설명 오류(rs.py:1, 수학적으로 맞는 정정), 212%는 산술 오류이고 31.01/13.51=229.5%(policy.py:754), pad 문턱 0.00703은 현 코드로 4.98e-5(명세:765), CID 오차가 신용을 과대평가할 수도 있음(명세:508, policy.py:279. 1바이트 절벽이 있으므로 실제 위험이다), Go 1.26.5와 1.26.6 구분(README:164), R-E README 17/7과 18/6 구분. 35행 인용 위치가 모두 정확했다.
- [moderate] ML-DSA 인증서 실바이트 측정과, 과장을 막는 MTC 띠 해석 :: 이전에는 합성 DER(-certsize)만 있었다. 이번에 OpenSSL 3.5.5로 실제 사슬과 CV를 만들어 바이트를 쟀다(ML-DSA-44 전송 DER 8,082 B와 CV 2,420 B, ML-DSA-65 11,140 B와 3,309 B). 7.7~9.0 kB MTC 띠는 'Initial 두 개를 1291~1341 B로 키우는 패딩만으로도 덮인다'고 적어 '이 띠에서 패리티가 최선'이라는 과장을 막았다(REPORT 80행). 바이트가 같은 Initial 중복(dup)도 표준 서버에서 보호 수단이 된다는 점을 금지 표에 넣어 X1의 필요성을 분명히 했다(33행).
- [moderate] TTLB 반론 대비 틀을 바로잡음 :: A1 카드는 'ms 이득을 7.8 kB 기준 비율로' 적으라고 했다. A1은 시간 분모에 바이트를 쓰지 않는 TTLB 중앙값 비율 틀로 바꿨다. Cloudflare 원문을 직접 확인한 결과, 7.8 kB는 HTTP 요청이 적어도 하나 있는 비재개 QUIC 연결의 서버→클라이언트 총 전송량 중앙값이고, 15.8%는 전체 QUIC 연결의 100 kB 초과 비율이며, 3.2 kB는 압축된 사슬 중앙값이다. A1의 서술과 일치한다.
- [moderate] 루프 산출 문서 전체에서 과장 표현이 없음 :: docs 102개와 MORNING_REPORT를 grep했다('어디서나', '더 낫다', '적응이 이득', '추가 비용 없', '증폭 병목을 밝', '신용과 복구를 함께', '신규성'). 단서 없는 사용은 0건이다. 개선 언급은 모두 '주장하지 않는다', '미확인' 꼴이고, 숫자에는 [측정]·[세계]·[모형] 같은 출처 종류가 붙어 있다.

## checked_but_ok
- D1 push 안 함: gen33에는 remote가 없다. R-E origin/main은 6bbd11f 그대로이고 원격 추적 ref도 main뿐이다. JOURNAL 847행에 '원격 백업은 실행하지 않았다'고 적혀 있다. 태그의 원격 존재 여부는 네트워크 없이 확인하지 않았다.
- D3·D12: 확증 측정·봉인·추첨은 없었다. X9는 A1에 정정 문장 틀만 남겼다.
- D6: p3 재측정과 발표 덱 편집은 없었다(REPORT 86행에 명시).
- D8: pq_afec·gen3·gen31·gen32에 루프 기간(10-30 01:20~11-01 09:00) 수정 파일 0개. 팀 공유 흔적은 없다.
- D9 볼트: 루프 시작(01:26:53) 뒤 바뀐 파일 6건은 2026-10-30 AlphaFold·mTOR 세션 로그, 10-31 AI_TOP_100 세션 로그와 프로젝트 노트(진행중에서 보관으로 이동, 추가·삭제 2건), PowerGuard 로그다. 모두 다른 Claude 세션이 쓴 무관한 주제이고 Codex라는 단어가 없다. 우리 학술 노트(01:11)와 10-29 로그(01:22)는 루프 시작과 guard 기준선 이전에 Claude가 썼다. guard_baseline과 현재 파일 목록을 대조해 확인했다. Codex가 이 6건을 '변경 주체 미확인'으로 약 40번 반복 기록한 것은 잡음이지만 위반은 아니다.
- D10: 문서가 'PAD-FEC v3.3'으로만 부른다.
- A1 인증서 PEM 12개에 개인키가 없다(PRIVATE KEY 0건).
- 35행 인용 위치는 35/35 정확했다. 원문 19개 SHA는 A1 이후 변경 0이다.
- rs.py MDS 정정은 수학적으로 맞다(가역 행변환은 생성 부호를 보존하고, 실패하는 것은 [I|V]를 그냥 쌓는 구성이다).
- CID ±수 B 정정이 맞다. base 39가 실측 중앙값이므로 과대평가 쪽 오차도 생긴다.
- 인증서 표 산술: Certificate+CV 메시지 = DER 합+18+서명+8, zlib 본문+12 B, C_eq와 S 모두 파일 바이트에서 재현했다.
- s0=1724 B 가정은 A1이 직접 기록한 관측 오프셋(중앙 약 2225/1985 B)보다 작다. A1이 그 차이를 82행에 공개했고, 관측 중앙값으로 바꿔도 'MTC landmark 띠는 1452 B Initial 두 개(8712 B)로 덮이고 fallback 8972 B는 못 덮는다'는 결론은 바뀌지 않는다(직접 계산).
- Cloudflare 7.8 kB, 15.8%, 3.2 kB의 정의와 인용은 원문(2024-11-07)과 일치한다.
- 확인하지 않은 것: IETF 125 MTC 슬라이드 내용, MTC draft-07의 2026-10-07 날짜, Chrome Root Program 방향 문서 문구.
- 이번 검증으로 저장소에 __pycache__나 .pytest_cache가 생기지 않았고, git status는 깨끗하다. 스크립트는 C:\Users\scien\AppData\Local\Temp\claude\C--Users-scien\98dad099-940c-4208-8359-61078035dc93\scratchpad\v33audit\G-claims-frame\ 아래에만 있다.

## VERIFY

- G-E1 (error): **confirmed** sev=medium :: 직접 확인했다. REPORT_CLAIMS_v33.md에는 IW/cwnd/Nawrocki/McManus/신규성/추가 비용/60.0/69.0이 한 번도 나오지 않는다. 7행 허용 문장에도 initial cwnd 단서와 token·resumption 단서가 없다. 32행은 '항상'을 붙인 꼴로만 금지한다. 감사자가 단 완화 단서('A1 카드 근거 목록에 없었으므로 과제 설계에도 일부 책임')는 실제보다 약하게 봐야 한다. 루프가 매 반복 전부 읽는 CONTEXT.md §7은 'initial cwnd 단서 없는 큰cert 결과'를 쓰면 안 되는 말로 명시했고, §1(11행)은 신규성 축소(Nawrocki·McManus를 잇는 한 수)를 적었다. Codex는 볼트 노트 72·97행을 인용했으니 같은 노트의 86·127·154·172·193~194행도 읽을 수 있었다. J8 문서에서는 IW10 프로파일까지 모형화했다. 문맥 어디에도 없던 것은 용량 부등식(60.0/69.0 B) 하나뿐이다. 따라서 IW와 신규성 누락은 Codex 쪽 책임이 더 크다. 심각도 medium은 적절하다. || grep -n -i -E 'IW|cwnd|Nawrocki|McManus|신규성|추가 비용|비용이 없|69\.0|60\.0' docs/REPORT_CLAIMS_v33.md 결과 0건. FINDINGS_INDEX.md에서 IW grep 0건. 볼트 우리 학술 노트 86행(60.0 B, C=1449 대 1389.0), 127행(병목 발견 주장 금지), 154행(패딩에 가까운 기제, FEC 고유 몫 2% 6.9 ms·15% 41.0 ms), 172행(IW 단서), 193~194행(69.0 B, C=1457, 1388.0). p1_flight.json capacity_checks 직접 계산: 12개 모두 feasible=False, 최소 초과 X25519MLKEM768 ips1450 C=1457−1388.0=69.0 B, any_inplace_feasible=False. RESULT_stage3.md:91 'v3.1의 수정이 이 두 조건에서 이득을 늘렸다고는 말하지 않는다'. CONTEXT.md:11, :88, :125. A1_claim_sources_v3.json에 볼트 노트 72·97행 레코드 있음. docs/J8_profiles.md:83,89(iw10).

- G-E2 (error): **confirmed** sev=medium :: 의존 구조, 상태 집계, 반복 분포가 모두 재현됐다. X 카드는 TASKS.md:393에서 '개발 측정 (development 표시, 확증 아님)'이다. 그러니 D3(확증 측정 안 함)와 무관하게 이번 밤에 돌 수 있도록 설계된 작업이었다. 그런데 G1이 blocked 후보 6개에 묶여 원리상 시작할 수 없었다. DECISIONS_NEEDED의 D13~D40은 모두 '사용자 응답을 기다리지 않는다' 꼴이다. 측정 사슬 봉쇄를 결정 항목으로 올린 줄은 없다. MORNING_REPORT '도현님 결정이 필요한 것' 절(423~431행)에도 없다. || LOOP_STATE.json: G1 depends [L1,L2,L3,L4,J1,J2,J6,L5,J7]. L2·L3·J1·J6·L5·J7은 blocked, L4·J2는 todo. T7 [G1,G2,S4,T1,T4], X1 [T7,T3], X9 [T7,T4], X6 [T7], X4 [T7,T2]. 상태 todo 49, done 25, blocked 14, doing 1, skipped 1. scratchpad hist.py로 history 63행 집계: 학습·세계 44반복(2994분, 반복14의 1675분 제외 시 1319분), T 11반복 196분, S 6반복 91분, A 2반복 24분, X 0. 반복14 제외 총 1630분 중 81%. MORNING_REPORT.md:262 문장 원문 일치. DECISIONS_NEEDED.md:45 D19.

- G-E3 (error): **confirmed** sev=low :: 사실은 그대로다. README 3행은 v3.2-dev와 상태 3을 적는데, 코드는 learn3.py:26 POLICY_VERSION="v3.3-dev", :25 STATE_VERSION=4, policy3.go:56 p3PolicyVersion="v3.3-dev"다. README에는 L1과 C1이 한 번도 나오지 않는다. README의 마지막 수정은 1fb785ec4(S3, 반복 3, 10-30 01:45)이고, 이때는 아직 v3.2-dev가 맞았다. 반복 16에서 L1이 채택된 뒤 낡았다. 다만 연구 주장에는 영향이 없다. README의 '다음 측정' 절은 '이 버전의 실제 성능은 아직 측정하지 않았다'고 옳게 적고 있고, 안내한 시험 파일 10개와 build_gen33.sh도 모두 있다. 저장소는 D11에 따라 비공개다. 그래서 심각도는 low가 맞다. || README.md:3, padfec3/learn3.py:25-26, experiments/quicbed/policy3.go:56, docs/L1_learning.md:3. git log 90859b973..HEAD -- README.md 결과는 1fb785ec4 하나. git diff 90859b973 HEAD -- README.md에서 '정책 버전은 아직 v3.2-dev' 추가 확인. README 안내 파일 존재 검사 11/11 ok.

- G-E4 (error): **partly** sev=low :: 사실 부분은 재현됐다. 35개 레코드의 start 행이 current_text 첫 줄과 35/35 일치했고, source_sha256 19/19가 그대로였다. 원문이 이미 맞았던 3행(09-07 로그 94행 9.09%, 09-17 로그 87행 m=1 1520/1600, 실험환경 대조 31행 기존 정정)도 원문을 열어 확인했다. 그러나 '실제 정정 18행'은 경계가 흐린 판단 분류다. 실험환경 대조.md:65는 '이 기계' OS를 Kali Rolling으로 적었고, A6-11 감사는 측정이 wsl -d Ubuntu로 돌았다고 지적했다. 이 행은 실제 오류에 가깝지만 감사자는 상태 주석으로 셌다. 반대로 PROTOCOL_stage3:3(봉인된 원문 유지, 정오표 제안)은 상태 주석에 가까운데 정정으로 셌다. 또 REPORT 103행은 '원문이 이미 정정된 경우에는 그 사실을 적었다'고 밝히고 절 제목도 '정정 제안'이라 숨긴 것은 아니다. '부풀렸다'는 표기 수준의 문제다. || scratchpad v33audit/verify-G-claims-frame/rows.py 출력: line match 35 35, sha same 19 19. 원문 대조: 2026-09-07 …:94, 2026-09-17 …:87, pq_afec/docs/실험환경 대조.md:31~42, :65. findings/audit-code-infra.md:215(A6-11, Kali 표기 대 Ubuntu 측정). git log -1 d67717d9b 본문 '정정35행'.

- G-E5 (error): **confirmed** sev=low :: 정규식 건수와 예시가 그대로 재현됐다. 115건 가운데 '버스트3'처럼 붙여 쓰는 표기도 섞여 있다. 하지만 바로 앞 글자가 조사 꼴인 경우(는·의·중·은·와 등)만 43건이고, 나머지 대부분도 '약3115', '반폭0.11'처럼 띄어쓰기 오류다. docs 102개는 전부 이번 루프에서 새로 만든 파일(수정 0)이고 3,103줄이며, README나 색인 파일은 없다. MORNING_REPORT 105행도 확인했다. || scratchpad style.py: REPORT 115, docs md 102, docs total 1455, added docs 102 modified 0, added lines 3103, README/index 0. style2.py: 앞 글자 분포 약16·는11·의8·트6, 조사 꼴 43. MORNING_REPORT.md:105 원문.

- G-E6 (error): **confirmed** sev=low :: 수치가 정확히 재현됐다. 덧붙일 점이 있다. Holm 순위 때문에 run1 S_bigcert와 run2 S_rtt200은 holm_level 0.05라 lo95와 lb_holm이 같고, 차이가 나는 것은 4개 중 2개(run1 RTT200, run2 bigcert)다. 표의 열 이름 '기존 95% 구간'도 엄밀히 틀린 말은 아니다. 다만 RESULT_stage3:12가 run1을 Holm 하한으로 인용하므로 두 문서를 나란히 보면 10.76과 11.04가 엇갈린다. low가 맞다. || p31_gencompare_decisions.json /H1: run1 S_bigcert lo95=lb_holm=24.33056450 (holm_level 0.05). run1 S_rtt200 lo95 11.036674487, lb_holm 10.762043369 (0.025). run2 S_bigcert lo95 25.579745808, lb_holm 24.898871044 (0.025). run2 S_rtt200 lo95=lb_holm=7.327190083. RESULT_stage3.md:12. REPORT_CLAIMS_v33.md:9~16.

- G-E7 (error): **confirmed** sev=low :: gen33 afec/rs.py:1에 '행축약하면 이 성질이 깨질 수 있는' 문장이 그대로 남아 있다. A1 정정은 수학적으로 맞다(행공간이 같으면 부호가 같다). 다만 감사자의 출처 표기에 작은 오류가 있다. rs.py를 바꾼 커밋은 S4가 아니라 S5(3eef6a737)다. 결론에는 영향이 없다. || grep -n 행축약하면 C:\dev\pq_afec_gen33\afec\rs.py 결과 13행. git log 90859b973..HEAD -- afec/rs.py 결과 3eef6a737 'S5: 기본 시험과 재현 도구를 정리하고…' 하나뿐. diff는 1행 머리말과 100~101행(r==1이면 [[1]*k])만 바꿨다.

- G-E8 (error): **confirmed** sev=low :: T1 커밋이 추가한 PEM 28개는 모두 'PRIVATE KEY' 줄을 2개(BEGIN/END)씩 가진다. S5가 이 파일들을 삭제했고, 현재 추적 중인 PEM 12개(A1 추가분)에는 개인키가 0개다. 원격도 없다. 하나 덧붙이면, D22에 따라 이 키들은 고정 seed로 만든 시험 키라 코드만으로 다시 만들 수 있다. 그래서 실제 위험은 감사자 평가보다 더 낮다. 공개 전 이력 정리가 필요하다는 점은 그대로다. || git log --diff-filter=A -- '*.pem' 결과 60a2f18f9, d67717d9b. git show 60a2f18f9 PEM 28개 각각 'PRIVATE KEY' 2회. git ls-files '*.pem' 12개 모두 0회. git log --diff-filter=D 결과 3eef6a737. git remote -v 결과 비어 있음. DECISIONS_NEEDED.md:55(D22 고정 seed), :119(D40).

- 보고 숫자의 정확성이 원 출처 수준으로 검증됨 (improvement): **confirmed** sev= :: 표본 약 25개를 독립적으로 다시 확인했고 불일치는 없었다. H1 est 4개, lo95/hi95, p18 값 9개(원 p18_mmax.json 안에 그대로 있음), expected_rounds 4개와 pad 문턱 4.978282525e-05(gen33 정책으로 재계산, gen-2 policy.py와 CRLF 정규화 후 바이트 동일), 31.01/13.51=229.5%, 봉인 해시 일치 수(gen31 stage0 2/3·5/6, stage2 22/29·7/9, stage3 31/31·14/14, gen3 stage0 3/3·6/6, stage2 29/29·9/9), DER 크기 9개와 C_eq 3개가 모두 맞았다. || scratchpad repro.py 출력: policy same after CRLF norm True, expected_rounds [1.2147657311,1.1886586651,1.1148003288,1.0727767511], threshold 4.978282525173353e-05, 2.2953. seal.py 출력은 위 수치와 같다. p18_mmax.json 문자열 검사 9/9 True. A1_certificate_v1 DER 4011/4019/4063, 5540/5548/5592, 416/424/469. p1_flight·decisions JSON 직접 확인. 실행 후 gen33·pq_afec에 __pycache__ 생성 없음.

- 볼트가 정정한 값과 방향 전환 근거를 맞게 다룸 (improvement): **partly** sev= :: p18(103.535228/51.711570/51.823658±0.113620), PTO 12.0% 대 10.4%(z=0.79는 그룹당 약 485일 때만 나옴), gen-2 17/7 대 18/6은 맞게 다뤘다. 그러나 과제가 짚은 볼트 정정 세 가지 가운데 용량 부등식 최소 초과(60.0 B@08-27 대 69.0 B@10-01)는 REPORT_CLAIMS에 아예 나오지 않는다(G-E1). '세 정정값을 맞게 다뤘다'가 아니라 '두 개는 맞게, 하나는 누락'이다. || REPORT_CLAIMS_v33.md:20, :146, :148, :130. A1_numeric_audit_v1.json q17 assumed_equal_n_for_z079=484.93. 60.0/69.0 grep 0건. 볼트 노트 193~194행.

- 팀 문서의 실제 오류 18건을 근거와 함께 짚음 (improvement): **confirmed** sev= :: 내가 확인한 정정 내용은 모두 옳았다. 212%는 산술 오류(실제 229.5%), pad 문턱은 현재 코드로 4.98e-5, MDS 설명 정정은 수학적으로 맞고, CID 오차로 신용을 과대평가할 수도 있다(실제 오버헤드가 39 B보다 작을 때). README:154의 '19 checks'도 A6-11 감사가 실행한 56 checks와 다르므로 실제 오류다. 다만 '18건'이라는 숫자는 G-E4처럼 판단 분류다. || repro.py 31.01/13.51=2.2953. findings/audit-code-infra.md:213(56 checks, 42 checks). CONTEXT.md:87(DCID 8~20 B, overhead 34~46 B, 모형 상수 39). REPORT_CLAIMS_v33.md:120,132,134,135.

- ML-DSA 인증서 실바이트 측정과, 과장을 막는 MTC 띠 해석 (improvement): **confirmed** sev= :: sizes.json의 값과 DER 파일 크기가 맞고, 세 사슬 모두 서명 검증 'Signature Verified Successfully'다. 산술도 맞다. 7746/6=1291, 8045/6=1340.8에서 1341, 6×1472=8832<8972, 3×2×1250=7500, C_eq 10435/14382/898. 80행의 '패딩만으로도 덮인다' 문장과 33행 dup 행이 X1의 필요성을 드러낸다는 평가도 타당하다. || C:\dev\codex_handoff\v33\runs\A1_certificate_v1\sizes.json, 각 폴더 *.der 파일 크기. REPORT_CLAIMS_v33.md:54~58, :66~68, :80, :33.

- TTLB 반론 대비 틀을 바로잡음 (improvement): **confirmed** sev= :: Cloudflare 원문(2024-11-07)을 직접 다시 읽었다. 7.8 kB는 비재개 연결의 서버에서 클라이언트로 가는 전송량 중앙값이고, 15.8%는 전체 QUIC 연결 가운데 100 kB 초과 비율이며, 3.2 kB는 압축된 사슬 중앙값이다. REPORT 88행 서술과 일치한다. 카드 4항('7.8 kB 기준 비율')을 시간 대 시간 비율로 바꾼 것도 단위상 옳다. || WebFetch https://blog.cloudflare.com/another-look-at-pq-signatures/ 결과: 'For non-resumptions the median is 7.8kB', 'only 15.8% of all QUIC connections transfer more than 100kB', 'The median certificate chain today (with compression) is 3.2kB'. TASKS.md A1 카드 4항. REPORT_CLAIMS_v33.md:88~97.

- 루프 산출 문서 전체에서 과장 표현이 없음 (improvement): **confirmed** sev= :: 과장 꼴 문구를 grep한 결과, docs에서는 REPORT 32행의 금지 표 항목과 T5 문서의 부정문만 나왔고 MORNING_REPORT에서는 0건이었다. 다만 이것은 적극적 과장이 없다는 뜻일 뿐이다. 단서 누락(G-E1, 아래 missed)은 grep으로 잡히지 않는다. || grep -E '어디서나|더 낫|보다 낫|적응이 이득|추가 비용 없|비용이 없|증폭 병목을 (우리가 )?밝|신용과 복구를 함께|함께 산다|개선했다|향상|우월' docs/*.md 결과 2행(REPORT_CLAIMS:32 금지 표, T5_hardening_contract:11 부정문). MORNING_REPORT.md 결과 0행.

- verdict_improved (verdict): **confirmed** sev= :: 판정의 골자(보고 위생은 나아졌고 연구 주장의 증거는 기준선과 같다)는 맞다. 새 네트워크 측정이 0회라는 점도 LOOP_STATE history로 확인된다. 한 가지는 다듬어야 한다. '기준선에는 주장 목록 문서가 없었다'는 gen32 저장소에서는 사실이다(기준선 트리에 docs 폴더 없음). 그러나 같은 틀은 이미 gen31 RESULT_stage3.md '말할 수 있는 것과 없는 것' 절, CONTEXT.md §7, 볼트 노트에 있었다. 그래서 REPORT_CLAIMS는 틀을 새로 만든 것이 아니라 모아서 정리한 것이다. 게다가 RESULT_stage3에 있던 단서 일부(이득 크기가 v3.0과 같음, 대가 7.9 KB)를 빠뜨렸다. || git ls-tree --name-only 90859b973 결과 docs 없음. g3에는 adaptation_benchmark_protocol.json, gen33_parity_baseline.json, policy3_reference*.py/json만 있음. pq_afec_gen31/g3/RESULT_stage3.md:89~97. CONTEXT.md:120~125. LOOP_STATE history 63행 중 X 과제 0.

### missed

- [low] H1 허용 문장에 봉인 결과의 '대가'(첫 비행 업링크 약 7.9 KB 대 gen-2 4.1~6.5 KB)가 빠짐 :: RESULT_stage3의 '말할 수 있는 것과 없는 것' 절은 H1 이득을 말할 때 바이트 비용을 함께 적었다. REPORT_CLAIMS_v33 7행의 허용 문장과 9~16행 표에는 이 비용이 없다. 연구 질문 자체가 '바이트를 패딩 대신 패리티로' 내는 것이고 볼트도 '추가 비용 없는 FEC'를 금지한다. 그러니 ms 이득만 싣고 업링크 바이트 증가를 빼면 이득이 공짜처럼 읽힌다. G-E1의 연장선이지만, G-E1이 짚은 볼트 금지 목록과는 별개로 봉인 결과 문서 자신이 붙인 단서다. || C:\dev\pq_afec_gen31\g3\RESULT_stage3.md:95 '- 대가: 첫 비행 업링크가 대부분 조건에서 약 7.9 KB(gen-2 4.1~6.5 KB).' grep -n -E '7\.9|4\.1~6\.5|대가' docs/REPORT_CLAIMS_v33.md 결과 해당 없음(13행의 숫자 일부 일치만). A1_report_final_v2.md에서도 '7.9 KB'와 '첫 비행 업링크' grep 0건.

- [low] 덱 슬라이드 번호를 '확인하지 못했다'고 했지만 Codex가 읽은 볼트 노트에 답이 있었음 :: REPORT_CLAIMS 86행은 'A1에서는 발표 원본의 현재 슬라이드 번호를 확인하지 못했다'고 적는다. 그런데 Codex가 72·97행을 인용한 같은 볼트 노트 199행에는 '덱 15·16번(09-22 판 21·22번) 숫자는 09-14 p14·p3·p7 실행(qamp 경로)에서 나왔다'가 있다. 이 노트는 루프 시작 전(10-30 01:11)에 이미 이 상태였다. 출처 경위를 인용할 수 있었는데 미확인으로 남겼다. || REPORT_CLAIMS_v33.md:86. 볼트 '03 프로젝트/진행중/우리 학술 (연구공모전).md':199, 파일 mtime 2026-10-30 01:11:01(루프 첫 반복 01:26:53보다 앞섬). A1_claim_sources_v3.json에 같은 파일의 72·97행 레코드 있음.
