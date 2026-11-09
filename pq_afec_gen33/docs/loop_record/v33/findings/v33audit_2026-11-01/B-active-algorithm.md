# B-active-algorithm

## summary
활성 정책은 L1(상태 4, v3.3-dev) 하나다. L2·L3·J1·J6·L5·J7·M1 후보는 모두 미채택(blocked)이라 v3.2-dev 대비 실제로 바뀐 알고리즘은 padfec3/learn3.py의 관측 갱신(observe3)뿐이고, decide3.py는 기준선과 같다. 그래서 guard 벌점과 16번째 재평가는 그대로 남아 있다.

직접 확인한 것: (1) 105개 대조의 seed t구간과 조정 경계를 seed 추정값에서 다시 계산했고 L1_benchmark.json과 정밀화 JSON 모두 일치했다. (2) 원자료 trace(jsonl.gz)와 action pool MC 표로 C1-v32 B1·B6·B7과 none-v32 B6의 seed별 기대 비용 차이를 처음부터 다시 계산했고 최대 오차는 2.6e-13 ms다. (3) HEAD 소스로 WSL 임시 복사본에서 qamp를 빌드해 E12 보충 참조 415,654값이 bit 단위로 모두 일치함을 재현했다. 다른 seed(31415)로 새로 만든 primitive 500개, 결정 1500개, 궤적 4개도 모두 통과했다. (4) HEAD Python으로 E12 참조를 다시 생성하면 저장본과 내용이 같다(padfec/policy.py 지문만 다름). (5) pytest 57개 통과, go vet 무결, Go 정책 시험 통과.

핵심 결론: C1 피드백이 있을 때(c1) W0 개발 시뮬레이션에서 B1 −0.656, B2 −2.118, B5 −0.658, B7 −3.670 ms/연결로 v3.2보다 나아졌고, p 추정 편향이 거의 0이 됐으며, 무손실 B3/B4의 추가 업링크 바이트가 약 53~55% 줄었다. 그러나 활성 정책의 기본 입력은 none이다(Python arrivals=None, Go -feedback 기본 false, 표준 QUIC 서버는 C1을 보내지 않는다). 이 none 경로는 v3.2보다 B6 +6.37 ms(확정 실패)로 나쁘고, B5·B7·B8_j20에서도 증가 근거가 있다. Codex는 이 실패를 숨기지 않았다. 다만 루프가 스스로 정한 D14로 none을 '진단'으로 분류해 L 공통 되돌림 규칙을 피했고, 이후 후보에는 none을 채택 관문으로 쓰는 비대칭 판정을 했다. 실제 QUIC 성능 측정(T7, X6, X1)은 하나도 없다.

절차 사고 고지: Go 시험을 돌릴 때 저장소 시험 도우미(preservedTempDir)가 ~/quicbed_gen33/test_artifacts에 디렉터리 51개를 만들었다. 시각(2026-11-02 00:04:40.98~00:04:41.02)으로 내 실행분만 골라 지웠다. 23:57·23:58·00:07:57에 생긴 다른 디렉터리는 다른 프로세스가 만든 것이라 손대지 않았다. 저장소(git status 0줄)·__pycache__·.pytest_cache 변화는 없고, WSL 임시 디렉터리는 지웠다. 스크립트와 출력은 C:\Users\scien\AppData\Local\Temp\claude\C--Users-scien\98dad099-940c-4208-8359-61078035dc93\scratchpad\v33audit\B-active-algorithm\ 에 있다.

## verdict_improved
(a) 시뮬레이션 세계(W0, 개발용): 조건부로만 발전했다. C1 피드백이 있으면 v3.2-dev보다 B1·B2·B5·B7 기대 비용이 줄고 나머지 셀은 비열등이며(B6은 사후 정밀화 뒤 경계선 통과), 손실률 추정과 무손실 바이트가 크게 좋아졌다. 그러나 활성 정책의 기본 입력은 none이고(Python arrivals=None, Go -feedback 기본 false, 표준 서버는 C1 없음), none 경로는 v3.2보다 B6 +6.37 ms로 확정 악화했다. B5 +0.36, B7 +0.26, B8_j20 +9.45 ms도 증가 근거가 있고, 줄어든 곳은 B2·B12_c12000뿐이다. 절대 목표도 미달이다(C1 B1 후회 1.226 대 목표 0.1, B2 0.513 미확정, B4 추가 바이트 2936 대 1855 B). 10-29 감사가 기대한 1.871→0.053은 'datagram 우도 + guard 끔'의 값이다. 감사가 같은 표에 낸 'datagram 우도 + guard 켬' 1.122가 L1의 1.226과 맞고, W1의 v32 1.882도 감사의 1.871과 맞는다. 차이는 guard 벌점과 16번째 재평가가 활성 decide3.py에 남아 있기 때문이다. L3 후보(0.094)와 guard-only 진단(0.093)은 기대 수준을 재현했지만, L3는 C1 B8_j20 +0.868 실패, guard-only는 진단 팔이라 채택되지 않았다(L3 수치는 g3/v33/L3_benchmark_v1.json에서 직접 확인). (b) 실제 QUIC 측정: 판정할 근거가 없다. T7·X6·X1 등 측정 과제가 전부 todo이고 LOOP_STATE의 measurement는 null이다. T4/T5의 33연결은 C1 배선·복호 기능 시험이지 HCT 성능 비교가 아니다. 따라서 'v3.3-dev가 v3.2-dev보다 낫다'는 실측으로는 말할 수 없고, 시뮬레이션에서도 'C1이 있을 때'라는 단서 없이는 말할 수 없다.

## frame_fit
부분적으로 맞는다. L1은 패리티와 패딩을 얼마나 보낼지 고르는 정책층의 학습 수정이라, '패딩 대신 패리티로 증폭 예산을 산다'는 신규성 주장 자체는 건드리지 않는다. 무손실에서 낭비 패리티를 절반 넘게 줄인 결과(B3/B4)는 '예산을 사는 바이트의 값'이라는 틀과 잘 맞는다. 다만 이득이 C1에 달려 있다. C1은 서버가 평문 UDP로 보내는 비표준 부채널이고, 인증되지 않으며 증폭 회계·HCT·연결 간격 비용에 들어가지 않았다(docs/c1_threat_model.md, D14). PAD-FEC가 이미 서버 쪽 복호를 요구하니 배포 범위는 같지만, 프로토콜 요구가 하나 더 늘어난다. C1 없는 서버에서는 오히려 v3.2보다 나빠진다. 볼트의 '쓰면 안 되는 말'(v3가 어디서나 낫다, 적응이 이득을 냈다)에 비추면, 보고서에 쓸 수 있는 문장은 '개발 시뮬레이션(W0)에서 서버 C1 회신이 있을 때 v3.3-dev 학습층이 손실률을 정확히 추정하고 B1/B2/B5/B7 기대 비용이 v3.2-dev보다 줄었다, C1이 없으면 B6에서 약 6.4 ms 나빠졌다' 정도다. '실측 개선', 'C1 없이도 개선', 'L1이 10-29 감사의 기대 개선을 달성했다'는 쓰면 안 된다.

## errors

### B-E1 [high] 활성 정책의 기본 경로(none, C1 없음)가 v3.2-dev보다 나빠졌다 (repro=True)
L1은 C1이 없으면 HCT 3등급 categorical 우도(EPS 1e-3 고정, 모형 절대 경계)로 갱신한다(learn3.py:748). 이 경로가 v3.2의 1비트 이진 우도보다 모형 오차에 훨씬 민감하다. none 대 v32(정밀화 JSON): B6 +6.372 [5.166, 7.579] 실패, B5 +0.360 [0.047, 0.672], B7 +0.260 [0.114, 0.406], B8_j20 +9.452 [0.263, 18.640]은 하한이 0보다 커서 증가 근거가 있다. 감소는 B2 −1.082, B12_c12000 −0.053 두 셀뿐이다. v31 대비로는 B6 +5.80, B7 +1.37이 실패다. 기전은 원자료로 확인했다. B6(로드밸런서 9000/16000)에서 16000 쪽 연결이 2-RTT 등급으로 관측될 때마다 categorical 우도가 p=0.30 쪽을 p=0.02보다 12~14배 지지한다(내 계산, lik_demo.py). 그 결과 꼬리 p 편향이 +0.271(v32 +0.145, 참값 0.02), 최종 p_mean이 0.29(격자 상한 0.3)까지 오른다. 실현 HCT 평균은 101.76 대 95.20 ms다. B8_j20 지터에서도 p 편향 +0.088 대 +0.030이다. Python observe3의 arrivals 기본값은 None이고, qamp는 서버와 클라이언트 모두 -feedback 기본값이 false다(qamp.go:3095, 3830, 3851). 따라서 C1을 구현하지 않은 서버에 대한 배포 기본 동작이 이 none 경로다.

EVIDENCE: g3/v33/L1_benchmark_precision_v1.json comparisons(pre_post_vs_v32, current_none). 직접 재계산: recompute_seed.py로 none-v32 B6 seed 평균 6.372402(보고값과 2.6e-13 이내). 원자료 요약: L1_raw_v1_38/none/B6 HCT 101.761, p_bias 0.2711 / W1_raw_v32 B6 95.199, 0.1452. qamp.go:3095 flag.Bool("feedback", false, ...), observation.go:199-203 disabled이면 src none.

FIX: none 경로는 v3.2의 이진 우도(또는 기준선 상대 판정)로 되돌리고 categorical은 C1이 확인된 목적지에만 쓰거나, EPS를 크게 잡아 S 혼합·지터에 견디게 한 뒤 none 15셀을 v32 대비 관문으로 다시 평가한다. 보고서에는 'C1 없는 서버에서는 B6에서 약 6.4 ms 나빠진다'를 함께 적는다.

### B-E2 [high] L1 채택 판정이 과제 규칙을 우회했고 이후 후보와 비대칭 기준을 썼다 (repro=True)
TASKS.md:180의 L 공통 규칙은 '다른 시나리오가 0.5 ms/연결 넘게 나빠지면 그 변경을 되돌린다'이고, L1 완료 기준(TASKS.md:193)에는 '다른 시나리오 악화 없음'과 B1<0.1(L3와 공동 허용)이 있다. 루프는 스스로 정한 D14(DECISIONS_NEEDED.md:27)로 c1만 주 비교, none은 진단으로 두어 확정 실패(none-v32 B6 +6.37, none-v31 B6/B7)를 채택 판정에서 뺐다. 공동 목표를 맡을 L3는 미채택이라 활성 정책의 B1 후회는 1.226으로 목표 0.1에 실패한 채 L1이 done으로 기록됐다. 그 뒤 L2·J1·L5는 'none과 c1 각각 L1 대비 15셀'(L2_disposition.md:5)을 채택 관문으로 썼다. 그래서 이미 v3.2보다 나빠진 L1-none이 새 기준선이 됐다. 예를 들어 J1은 none B6를 L1 대비 −5.75 ms 줄였는데도 none 3셀 미확정으로 미채택됐다(J1_disposition.md:12, 이 J1 수치는 Codex 문서에서 읽은 값). 사전 고정한 판정 문서(L1_precision_acceptance_scope.md)대로 진행한 점은 투명하지만, 같은 정책 경로를 L1에서는 진단으로, 후속에서는 관문으로 다룬 것은 일관되지 않다.

EVIDENCE: prompt/TASKS.md:180, 193; state/DECISIONS_NEEDED.md:27(D14); runs/L1_precision_acceptance_scope.md; runs/L1_precision_disposition.md; runs/L2_disposition.md:5; runs/J1_disposition.md:12,16; LOOP_STATE L1 status done.

FIX: L1 상태를 'C1 경로 Python 구현 완료, none 경로 회귀로 정책 채택 보류'로 고치거나, v3.2 대비 none 15셀을 L1 자신에게도 관문으로 적용해 다시 판정한다. 후속 후보의 none 비교 기준선은 L1-none이 아니라 v32로 둔다.

### B-E3 [medium] C1 B6 비열등 통과가 결과를 본 뒤 정한 정밀화 재실행에 기대고 있다 (repro=True)
원래 N=131072 보고서에서 C1-v32 B6는 조정 상한 0.5733으로 미확정이었다. 이를 본 뒤(L1_precision.md:3 '원래 N=131072 보고서를 본 뒤 정한 작업') 같은 seed prefix로 MC N을 1,048,576으로 올려 다시 계산했고, 상한 0.4795로 통과해 L1이 채택됐다. 재실행의 N은 미리 고정했고 1회로 제한했으며 Codex가 사후 정밀화라고 밝혔다. 그래도 미확정 결과를 보고 한 번 더 보는 구조라 통과 확률이 부풀려지고, 여유는 0.02 ms뿐이다. seed 구간 자체 [−0.4717, 0.4339]는 거의 그대로다.

EVIDENCE: g3/v33/L1_benchmark.json C1-v32 B6 adj=[−0.592357, 0.573320] inconclusive / g3/v33/L1_benchmark_precision_v1.json adj=[−0.517390, 0.479549] pass(table.py로 재계산 일치). docs/L1_precision.md:3.

FIX: B6는 '0.5 ms 비열등 경계선'으로만 쓰고, 독립 seed(예: 51~70)로 한 번 더 확인하기 전에는 채택 근거로 쓰지 않는다.

### B-E4 [low] C1 경로는 버스트 손실에서 p를 낮게 추정하고 비용이 조금 늘어난다 (repro=True)
데이터그램 우도는 한 비행의 최대 8개 데이터그램을 iid Bernoulli로 곱한다. 버스트 세계 B10에서 c1의 꼬리 p 편향은 −0.0204(v32 +0.140)이고, 기대 비용은 v32보다 +0.170 [0.136, 0.204]로 증가 근거가 있다(0.5 제한 이내). D13 때문에 회신 없는 전멸 비행은 데이터그램 증거에서 빠지는데, 이것이 생존 편향을 남긴 것으로 보인다(원인 분해는 하지 않았다). 코드 버그가 아니라 모형 한계이고 Codex도 일부 기록했다.

EVIDENCE: 원자료 요약: B10 c1 p_bias −0.0204, v32 +0.1396. 정밀화 JSON C1-v32 B10 +0.169566 [0.135617, 0.203515].

FIX: J5(GE 우도)나 연결 단위 전멸 표지(인증된 C1의 lost=sent)를 넣고 B10을 관문 셀로 다시 본다.

### B-E5 [low] S4 뒤 E12 L1 보충 관문을 다시 돌리지 않아, 지금 그대로 돌리면 출처 검사에서 실패한다 (repro=True)
E12_l1_reference_v1.json의 sources에 기록된 padfec/policy.py 지문이 S4의 lru_cache 추가로 HEAD와 다르다. gate_l1_go.py는 이를 problems로 올려 passed=false가 된다. S4는 v3 관문과 W1만 다시 돌렸다. 계산 내용은 변하지 않았다(내가 HEAD로 다시 생성한 참조가 저장본과 내용 동일, HEAD Go 415,654값 bit 일치).

EVIDENCE: HEAD 지문 비교: padfec/policy.py DIFF, 나머지 7개 MATCH. regen/E12_l1_ref_head.json 비교 결과 schema·arrivals·classes·observations·caches·invalid_arrivals 모두 True.

FIX: S4 이후 참조를 다시 생성해 receipt를 갱신하고 gate_l1_go.py를 다시 돌려 기록한다.

### B-E6 [low] Go 시험이 보호 대상 작업 폴더 ~/quicbed_gen33에 부산물을 남긴다 (repro=True)
qamp_preserved_test.go의 preservedTempDir가 ~/quicbed_gen33/test_artifacts 아래에 test-* 디렉터리를 만들고 지우지 않는다. 이미 4,000개가 넘게 쌓여 있다. 내 검증 실행도 51개를 만들어 시각 기준으로 정확히 그만큼 지웠다. 정책 정확성과는 무관하고 S5 시험 위생 범위다.

EVIDENCE: qamp_preserved_test.go:9-24 (filepath.Join(home, "quicbed_gen33", "test_artifacts")). find 결과 기존 4,005개 + 다른 프로세스 114개.

FIX: t.TempDir()를 기본으로 쓰고 보존이 필요할 때만 환경변수로 켠다.

### B-E7 [low] 상태 판본이 3에서 4로 바뀌었는데 cache3 schema 표지는 그대로라 옛 캐시가 있으면 qamp가 종료한다 (repro=False)
p3StateVersion=4지만 p3CacheSchema는 'padfec3.cache3/3' 그대로다. v3.2 시절 cache3 파일이 있으면 validate 오류로 loadDestCache3가 실패하고 qamp가 exit 2로 끝난다(qamp.go:2407-2407). 이전 상태 거부는 L1_learning.md에 의도로 적혀 있어 안전한 실패 방향이지만, 표지만 보고는 호환 여부를 알 수 없다.

EVIDENCE: policy3.go:50, 618-619, 1620-1662; qamp.go:2407-2407.

FIX: schema를 cache3/4로 올리거나, 판본 불일치 항목은 버리고 콜드스타트하는 명시 경로를 둔다.

## changes
- padfec3/learn3.py: STATE_VERSION 3→4, POLICY_VERSION v3.2-dev→v3.3-dev. observe3에 arrivals 선택 인자 추가(src c1/ack/none, sent, lost, bitmap, trunc; normalize_arrivals로 엄격 검증, 사본에서 갱신 후 성공 시 반영).
- learn3.py 갱신 규칙(668~771행): 완전한 도착 증거가 있으면 격자마다 p^lost·(1−p)^(sent−lost) 데이터그램 우도(이항계수 없음, 반복 곱). 없거나 잘렸으면 문맥이 있을 때 HCT 3등급 categorical 우도((1−EPS)q+EPS(1−q)/2, EPS=1e-3; 경계 1.5·RTT+τ(결정 전 바이트)+3 ms, 그 위 +RTT+τ(W)). 문맥도 없으면 predict_step만 한다.
- 1비트 y, nominal2·shield·guard 건너뛰기는 legacy 진단값으로만 남고 학습 갱신을 막지 않는다(learn3.py:726). 옛 이진 likelihood 함수는 남아 있지만 호출되지 않는다. 진단 카운터 13개 추가, _model_result가 등급 확률을 같은 캐시에 보관.
- padfec3/decide3.py는 기준선과 같다. guard 가산 벌점(248행)과 16번째 재평가(267행)가 그대로 활성이다. layout.py도 바뀌지 않았다.
- Go 거울(E12): policy3.go 상태 4·v3.3-dev, p3Observe 가변 인자 arrivals, policy3_l1.go(도착·등급 우도, 경계, JSON 엄격 해석, 참조 실행기). qamp.go는 fc.arrivalEvidence(feedback)의 CRC 대조 결과를 &t.Arrivals로 넘긴다(T4 배선). -feedback 기본값은 false.
- S4: gen-2 policy.go에 캐시 state_version 1과 이전 map 변환(D21, 새 필드 0), ACK RTT EWMA, C1 신선도, 보호 콜드스타트 뒤 초기 무보호 관측, 심볼 손실 닫힌식 감쇠를 이식했다. afec/channel.py cached가 for_prior를 쓰고, padfec/policy.py expected_rounds에 lru_cache가 붙었다. 활성 v3 결정은 바뀌지 않았다(S4 W1 재실행 동일, 내 참조 재생성 동일).
- S5: afec/rs.py r=1 패리티 계수를 XOR(전부 1)로 바꿨다(코덱, 정책 비용과 무관).
- 채택 상태: 활성은 L1 상태 4. L2(EPS Beta), L3(CUSUM 감시), J1, J6, L5, J7, M1 후보는 평가 뒤 모두 미채택으로 보존됐다. G1·G2·T7·X 측정은 todo다.

## improvements
- [strong] C1 피드백이 있을 때 W0 개발 시뮬레이션에서 v3.2-dev보다 기대 비용 감소 :: 정밀화 JSON C1-v32: B1 −0.656 [−1.119, −0.193], B2 −2.118 [−2.694, −1.543], B5 −0.658 [−1.002, −0.313], B7 −3.670 [−3.980, −3.359] ms/연결. 15셀 모두 0.5 비열등 통과(B6 상한 0.4795로 경계선). seed별 값은 원자료에서 내가 다시 계산해 일치. 시뮬레이션 결과이며 실측이 아니다.
- [strong] C1 경로의 손실률 추정 정확도가 크게 좋아졌다 :: 원자료 꼬리 p 편향(참값 대비): B6 c1 +0.0006 대 v32 +0.145, B7 +0.0003 대 +0.168, B2 +0.002 대 −0.115, B8_j20 +0.0004 대 +0.030. B7(s2c 손실)에서 하향 손실을 상향 손실로 착각하던 문제가 사라졌다.
- [strong] 보호 행동에서도 정보가 들어와 무손실 조건의 낭비 바이트가 줄었다(C1 경로) :: B3_u0 최종 p 0.000126 대 v32 0.0848, B4 0.000205 대 0.1197. 서버 계수 추가 업링크 B3_u0 6644.8→3110.6 B(−53%), B4 6586.9→2935.6 B(−55%). v32는 (0,0,4)/(1,0,4)에 31,980회 고착했다. 다만 B4 문턱 1855 B에는 실패했다.
- [moderate] Python과 Go 활성 L1 구현의 결정·상태 일치 :: HEAD 소스로 빌드한 qamp가 E12 보충 참조 415,654값을 bit 단위로 모두 일치시켰다. 독립 seed 31415의 primitive 500, 결정 1500, 궤적 4도 통과했다. HEAD Python으로 다시 생성한 참조도 저장본과 내용이 같다. 성능이 아니라 구현 일관성 근거다.
- [weak] 관측 입력 검증과 원자성 :: 두 언어 모두 잘못된 arrivals 31종을 거부하고 상태를 바꾸지 않는다(참조 invalid_arrivals 31개 Go 전부 거부). pytest tests/test_padfec3_arrivals.py 57개 통과, go vet 무결, Go 정책 시험 통과.

## checked_but_ok
- C1 데이터그램 우도 수식: 이항계수를 뺀 p^lost(1−p)^(sent−lost)는 격자 사이 상수 배 차이만 없애므로 사후분포에 영향이 없고 iid 모형(layout.outcomes)과 일관된다. Go도 같은 곱셈 순서다(policy3_l1.go p3ArrivalLikelihood).
- 0 나누기·NaN: hazard 재주입으로 모든 격자에 사전 질량이 남아 z>0이 보장된다. 기본 EPS 1e-3에서 categorical 우도는 항상 양수이고 세 등급 합이 1이다. z=0은 EPS=1이고 q=1인 비현실 경계에서만 가능하다. gen-2 심볼 닫힌식은 nSym≤0을 미리 거른다(policy.go:749).
- 105개 대조 전부: seed 추정값에서 Student t 구간과 MC·selection gap을 더한 조정 경계를 다시 계산했고 L1_benchmark.json과 정밀화 JSON 모두 일치했다(table.py).
- 원자료 재계산: W1_raw_v32·L1_raw_v1_* trace와 L1_action_pool_precision_v2 MC 표로 C1-v32 B1(−0.656267), B6(−0.018921), B7(−3.669562), none-v32 B6(+6.372402)의 seed별 값을 오차 2.6e-13 이내로 재현했다. 원자료는 git이 아니라 codex_handoff\runs에 있고, git에는 SHA 목록만 있다.
- 과제가 제시한 수치(B1 −0.6558, B2 −2.1187, B5 −0.6581, B7 −3.6422, B1 후회 1.226, none B6 +6.37, B4 2935 B)는 원래 보고서와 정밀화 보고서에서 그대로 나온다.
- E12 재현: HEAD Go 415,654값 bit 일치, 독립 seed fresh 표본 통과, HEAD Python 참조 재생성 동일. '90,000결정'은 독립 결정 11,720개가 아니라 궤적 9개 단계 수(50,000+40,000)를 뜻한다.
- HEAD 정책 파일은 L1 벤치 스냅숏과 afec/channel.py, afec/rs.py, padfec/policy.py만 다르다. S4가 W1 900실행을 다시 돌려 trace가 같았다고 기록했고(Codex 문서), 내 참조 재생성도 동일해 활성 결정이 바뀌지 않았음과 맞는다.
- qamp C1 증거: matchFirstFlight·inCRC로 첫 비행 CRC와 대조하므로 PTO 재전송(새 CRC)은 도착으로 세지 않는다. 중복 CRC·잘림·송신 실패는 trunc로 검열한다(observation.go:196-249).
- S4 D21 변환: 판본 없는 옛 map은 엄격 해석 뒤 새 필드를 0으로 두고, 잘못된 파일은 전체 거부 후 빈 캐시로 시작한다(다음 저장 때 덮어쓰는 점은 S4_port_contract.md에 적혀 있다). gen-2 경로라 활성 v3 정책과는 무관하다.
- Python 관측의 원자성: deepcopy 사본에서 갱신하고 성공 시 반영한다. Go도 p3CloneState 뒤 성공 시 반영한다.
- Codex 문서는 none 실패, B1/B2 미달, B4 바이트 실패, 사후 정밀화 성격, C1 평문 한계를 모두 밝혔다. 숫자를 숨기거나 부풀린 곳은 찾지 못했다.

## VERIFY

- B-E1 (error): **confirmed** sev= :: none 경로 회귀를 원자료에서 독립 재계산으로 그대로 재현했다. 기전(16000 인증서 연결이 2-RTT 등급으로 관측될 때 categorical 우도가 p=0.30을 p=0.02보다 약 14배 지지)도 실제 행으로 확인했다. 기본 입력이 none이라는 점도 HEAD 바이너리 실행으로 확인했다. 단서: none에 3등급 우도를 쓰라는 것은 TASKS.md:190(L1 5항)이 지시한 설계이고 Codex가 MORNING_REPORT:115와 L1_precision_acceptance_scope.md에 실패를 공개했다. 그래서 감사자의 처방 'v3.2 이진 우도로 되돌리기'는 카드 5항과 충돌하므로 사람이 결정할 사항이다. 그래도 활성 정책의 기본 경로가 v3.2보다 나쁘다는 사실은 '발전했나'의 핵심이라 high를 유지한다. || 직접 계산(recalc.py, seed 31~50, L1_raw_v1_*/none/B6 대 W1_raw_v32): none-v32 B6 평균 차이 6.372402 ms, c1-v32 -0.018921. 마지막 25% 행 p 편향 none 0.2716 / v32 0.1454 / c1 0.0005, 실현 HCT 101.761 / 95.199 / 95.088 ms, 최종 p 0.2917 / 0.1457 / 0.0206. B8_j20 none-v32 +9.451571, p 편향 0.0875 대 0.0302. B7 +0.260174. 정밀화 JSON(tab.py): none-v32 B5 +0.3598 adj[0.0471,0.6724], B6 +6.3724 adj[5.1659,7.5789] fail, B7 +0.2602 adj[0.1142,0.4062], B8_j20 +9.4516 adj[0.2630,18.6402], 감소는 B2 -1.0824, B12_c12000 -0.0526뿐(B11 -0.0253은 구간이 0 포함). v31 대비 B6 +5.8020, B7 +1.3719 fail. lik_rows.py(none B6 seed 31~33): cert 16000·grade 1 행 1,915개의 L(p=.30)/L(p=.02) 중앙값 14.208. 코드: learn3.py:11 CLASS_EPS=1e-3, :658 arrivals=None, :748 categorical. qamp.go:3095 feedback 기본 false. HEAD qamp를 WSL 임시 폴더에서 빌드해 실행한 출력에 "arrivals":{"src":"none"}, "c1":{..."reason":"disabled"}. Go policy3.go:1225-1243이 Python과 같은 none→categorical 분기.

- B-E2 (error): **partly** sev=medium :: 비대칭 관문은 확인된다. L1 자신은 none을 진단으로만 두었는데 L2·J1은 none 대 L1을 채택 관문으로 썼고, J1은 none B6를 크게 줄이고도 none 3셀 미확정으로 미채택됐다. 그러나 '과제 규칙 우회'는 과장이다. TASKS.md L1 7항이 'W0 세계가 arrivals를 C1 방식으로 만들어 주게 한다'고 해 W1 판정을 C1 입력으로 하라는 카드 의도가 있고, L2 카드는 none 변형을 '결과 기록, 통과를 기대하지 않는다'로 다룬다. D14는 L1 수집 전에 고정됐다(L1_precision_acceptance_scope.md 1문단). B1<0.1도 카드가 L3와 공동 달성을 허용했다. 남는 결함은 '공동 목표를 맡은 L3가 미채택인데 L1을 done으로 둔 것'과 '후속 후보에만 none 관문을 건 비일관성'이다. B-E1과 같은 회귀를 절차 쪽에서 다시 센 것이라 high는 과하다. || TASKS.md:180(L 공통 0.5 ms 되돌림), :190(none은 3등급 우도), :193(완료 기준, L3와 공동 허용), L1 카드 7항, L2 카드 완료 기준. DECISIONS_NEEDED.md D14 행. runs/L1_precision_acceptance_scope.md('이 구분은 원래 L1 수집과 정밀화 계획에 이미 들어 있다'). runs/L2_disposition.md:5('채택 비교는 none과 c1 각각의 L1 대비 15셀'). runs/J1_disposition.md 표(J1 none 대 L1 none 통과12·미확정3), none B6 -5.753805(Codex 문서 수치). LOOP_STATE.json: L1 done, L2·L3·J1·L5 blocked. MORNING_REPORT.md:17('none 실패·공동 절대 목표는 L2/L3로 이관').

- B-E3 (error): **partly** sev=low :: 인용 숫자는 모두 맞다. 하지만 '미확정을 보고 다시 봐서 통과 확률이 부풀려진다'는 비판은 약하다. 정밀화는 세계 seed와 원자료를 그대로 두고 행동 비용표의 MC 계산 오차 항만 줄였다(공유 MC 폭 0.129→0.046). seed 구간 상한은 0.444→0.434로 사실상 같다. 새 데이터를 다시 뽑은 것이 아니라 근사 계산을 더 정밀하게 한 것이고, Codex가 N을 미리 고정하고 1회로 제한했으며 '독립 확증이 아님'을 문서에 적었다. 남는 단서는 여유가 0.0205 ms뿐이라 독립 seed 확인 전에는 경계선 통과로만 써야 한다는 점이다. || tab.py 출력: L1_benchmark.json C1-v32 B6 mean -0.0095 seed[-0.4630,0.4439] adj[-0.5924,0.5733] inconclusive. L1_benchmark_precision_v1.json mean -0.0189 seed[-0.4717,0.4339] adj[-0.5174,0.4795] pass. MORNING_REPORT.md:107(MC 폭 0.129375383), :115(공유MC 0.045684, '원형 보고서와 같은 seed prefix의 사후 개발 정밀화이며 독립 확증이 아니다'). docs/L1_precision.md:3-5(N=1048576 고정, '중간 gate를 보고 멈추거나 N을 다시 탐색하는 인자는 없다'). recalc.py로 c1-v32 B6 -0.018921 재현.

- B-E4 (error): **confirmed** sev= :: B10 버스트 세계에서 c1 경로가 p를 낮게 잡고 비용이 조금 늘어나는 것을 원자료로 재현했다. 원인 분해를 하지 않았다는 감사자 단서도 정확하다. 0.5 제한 안이라 low가 맞다. || recalc.py B10(seed 31~50): c1-v32 평균 차이 +0.169566(정밀화 JSON +0.1696 adj[0.1356,0.2035]과 일치). 마지막 25% p 편향 c1 -0.0196 / v32 +0.1379(감사자 -0.0204/+0.1396은 창 정의 차이), 최종 p c1 0.1309 / v32 0.2913. learn3.py arrival_likelihood는 G^lost·(1-G)^(sent-lost) iid 곱. DECISIONS_NEEDED.md D13(회신 없음은 전멸로 넣지 않음).

- B-E5 (error): **confirmed** sev= :: S4가 padfec/policy.py에 lru_cache를 넣은 뒤 E12 L1 참조를 다시 만들지 않아 출처 지문이 어긋난다. gate_l1_go.py는 이를 problems에 넣어 passed=false로 만든다. 계산 내용은 그대로다. || sha256: HEAD padfec/policy.py abfb04a8019e0a44… 대 참조 sources 4cb840be18ec19b5…, 나머지 7개 일치. git diff 90859b973 HEAD -- padfec/policy.py는 import lru_cache와 @lru_cache(maxsize=512) 두 줄뿐. E12 참조 마지막 커밋 ffd9f45ec(10-31 21:06)가 S4 557494b0f(11-01 01:04)보다 앞섬. experiments/gate_l1_go.py:72-75, :95. 내가 HEAD 소스로 빌드한 qamp에 저장된 E12 참조를 넣고 gate_l1_go.compare로 비교: leaves 415,654, bit_exact 415,654, failures 0, invalid_arrivals 31/31 거부.

- B-E6 (error): **partly** sev=low :: 사실은 맞지만 Codex의 실수라기보다 루프 규칙의 의도된 부작용이다. LOOP_PROMPT 7항이 저장소 밖의 추적되지 않는 파일 삭제를 금지했고, Codex는 시험 임시 폴더를 보존하도록 바꿨다고 보고했다. 알고리즘 정확성과 무관하다. 덧붙여 감사자 자신이 보호 대상 ~/quicbed_gen33 안에 51개를 만들고 지웠다고 적었는데, 이는 이번 감사의 'WSL ~/quicbed*에 쓰지 않는다' 규칙 위반이다. 지금 11-02 날짜 폴더 57개가 남아 있어 다른 감사 실행도 이 폴더를 건드린 것으로 보인다. || experiments/quicbed/qamp_preserved_test.go:9-24(filepath.Join(home, "quicbed_gen33", "test_artifacts"), os.MkdirTemp, 삭제 없음). WSL 읽기 전용 확인: test-* 4,176개(10-31 1,010, 11-01 3,109, 11-02 57), 142M. LOOP_PROMPT.md:31('그 밖은 지우지 말고 runs\trash_list.md에 적는다'). MORNING_REPORT.md:375('신규 시험 임시 폴더를 보존하도록 바꿨고').

- B-E7 (error): **confirmed** sev= :: 감사자는 재현하지 않았지만 내가 재현했다. schema 표지는 cache3/3 그대로인데 상태 판본 4가 아니면 qamp가 exit 2로 끝난다. docs/L1_learning.md:53이 구판 거부를 의도로 적었으므로 안전한 실패 방향이고 low가 맞다. || policy3.go:50 p3StateVersion=4, :53 p3CacheSchema="padfec3.cache3/3"(기준선 90859b973은 3과 cache3/3), :618-619, :1600 e.State.validate(). WSL 임시 폴더에서 HEAD qamp 실행: v=3 상태 cache3 → 'cache3: ./c_v3.json: destination 127.0.0.1:1: state version 3, want 4', exit=2. 같은 파일 v=4 → 정상 진행, exit=0.

- C1 피드백이 있을 때 W0 개발 시뮬레이션에서 v3.2-dev보다 기대 비용 감소 (improvement): **confirmed** sev= :: 원자료 재계산과 보고 JSON이 일치한다. 다만 D14의 수동 관측 모형이라 회신 비용이 0으로 들어간 시뮬레이션 결과라는 단서를 붙여야 한다(missed 3 참고). || recalc.py(seed 31~50): c1-v32 B2 -2.118498, B7 -3.669562, B6 -0.018921, B10 +0.169566. 정밀화 JSON: B1 -0.6563 adj[-1.1192,-0.1933], B2 -2.1185 adj[-2.6944,-1.5426], B5 -0.6576 adj[-1.0019,-0.3132], B7 -3.6696 adj[-3.9804,-3.3587], c1-v32 15셀 모두 gate=pass. 과제 문구의 B7 -3.6422는 원래 N=131072 보고서 값(L1_benchmark.json).

- C1 경로의 손실률 추정 정확도가 크게 좋아졌다 (improvement): **confirmed** sev= :: 모든 수치를 재현했다. B2의 v32 -0.115는 감사자가 창을 밝히지 않았지만 '1구간(p=0.25) 마지막 200행' 창에서 -0.1147로 나온다. || recalc.py 마지막 25% 창: B6 c1 0.0005 / v32 0.1454, B7 0.0002 / 0.1672, B8_j20 0.0004 / 0.0302. b2win.py B2 1구간: c1 last200 +0.0022, v32 last200 -0.1147(마지막 25%면 -0.1359).

- 보호 행동에서도 정보가 들어와 무손실 조건의 낭비 바이트가 줄었다(C1 경로) (improvement): **confirmed** sev= :: 모든 수치가 원자료에서 정확히 나온다. 서버 계수 추가 업링크는 행의 extra_server_bytes 평균이다. || bytes.py(seed 31~50): B4 extra_server_bytes c1 2935.6 / v32 6586.9, B3_u0 3110.6 / 6644.8. v32의 (0,0,4)+(1,0,4) 선택 31,980/32,000(B4는 (1,0,4), B3_u0는 (0,0,4)). 마지막 200행 p c1 B4 0.0002122292, B3_u0 0.0001294771(Codex 보고값과 소수 10자리 일치), v32 0.1201/0.0861. B4 1855 B 문턱 실패도 맞다.

- Python과 Go 활성 L1 구현의 결정·상태 일치 (improvement): **confirmed** sev= :: 저장된 참조 재현에 더해, E12 생성기와 다른 무작위 입력(관측 4계열×150, 캐시 결정 3계열×150, c1/ack/none/잘림 도착 혼합)을 내 스크립트로 만들어 HEAD Go와 비교했다. 두 seed 모두 완전 일치해 강도를 strong으로 올려도 된다. 구현 일관성 근거이지 성능 근거는 아니다. || WSL /home/scien/v33audit_tmp/verify-B에 gen33 소스를 복사해 go build(go1.26.6), qamp -mode policy3ref. mkref.py seed 7771: leaves 405,333 전부 exact, 캐시 결정 450개 action·why 일치(datagram 268·categorical 330 갱신 포함). seed 424242: 406,668 전부 exact, 결정 450 일치. 저장 E12 참조: 415,654 bit_exact, invalid 31/31. 임시 폴더는 끝난 뒤 삭제.

- 관측 입력 검증과 원자성 (improvement): **confirmed** sev= :: pytest와 Go 거부 수를 재현했다. 저장소에 캐시가 생기지 않았다. || PYTHONDONTWRITEBYTECODE=1 python -B -m pytest -p no:cacheprovider -q tests/test_padfec3_arrivals.py → 57 passed in 2.02s. 실행 뒤 find로 __pycache__/.pytest_cache 없음, git status 깨끗. Go invalid_arrivals 31/31 거부. learn3.py:657-664 observe3는 deepcopy 사본에서 갱신 뒤 성공 시에만 반영.

- verdict_improved (verdict): **confirmed** sev= :: 판정의 수치와 논리를 모두 확인했다. 10-29 감사 표의 'datagram+guard 켬 1.122'가 L1 c1 1.226과, v32 1.882가 감사의 1.871과 맞고, 기대값 0.053은 guard를 끈 변형이라는 설명이 원문과 일치한다. 실측 없음도 맞다. 보강할 점: none 경로는 B3_u0·B4에서 v32와 행동·바이트가 완전히 같아 10-29의 '보호 행동 정보 0' 결함이 C1 없이는 그대로이고(missed 1), c1 이득은 회신 비용 0을 가정한 수동 관측 모형 값이다(missed 3). || L1_benchmark_precision_v1.json B1 expected_regret: current_c1 1.2262, current_none 2.3864, v32 1.8825, v31 2.5983. L3_benchmark_v1.json: l3_c1 0.094, guard_c1 0.093, l3_c1-l1_c1 B8_j20 +0.8679 adj[0.5696,1.1661] fail. findings/audit-learning.run1.json:55,79('데이터그램 우도(감시 켬) 1.122. 데이터그램·감시 끔 0.053'). LOOP_STATE.json measurement None, T7·X1·X4·X6·X9·G1 todo. docs/T4_observation_result.md:3('33연결 중 … 30개가 성공 … 성능 효과는 측정하지 않았다').

### missed

- [medium] none 경로에서는 10-29 감사의 '보호 행동 정보 0' 결함이 전혀 고쳐지지 않았다 :: 무손실 B3_u0·B4에서 none 경로는 v3.2와 행동·바이트·p가 사실상 같다. 보호 행동에 32,000번 중 31,980번 고착하고, 마지막 200행 p가 0.086/0.12로 남으며, 추가 서버 바이트도 v32와 똑같다. L1 완료 기준 'B3·B4 p_mean 0.01 아래 수렴'(TASKS.md:193)은 c1에서만 충족된다. 감사자의 개선 항목은 '(C1 경로)'로 한정해 틀리지는 않았지만, 판정은 none 경로의 비용 회귀만 다루고 이 미개선은 적지 않았다. 기본 배포 입력이 none이므로 '정보 0' 처방이 실효를 가지려면 서버 C1이 필수라는 점을 판정에 넣어야 한다. || bytes.py(seed 31~50): B3_u0 none 선택 (0,0,4) 31,980/32,000, 마지막 200행 p 0.0857, extra_server_bytes 6644.8(v32 6644.8, 0.0861). B4 none (1,0,4) 31,980/32,000, p 0.1199, 6586.9(v32 6586.9, 0.1201). 정밀화 JSON none-v32 B3_u0·B4 차이 정확히 0.

- [low] none 경로가 v3.2가 건너뛰던 연결(명목 2-RTT, guard 경보)에도 categorical 갱신을 한다 :: L1은 skip 사유를 legacy 진단으로만 남기고, none 경로에서도 모든 문맥 있는 연결을 categorical 우도로 갱신한다. L3 카드 1항은 명목 2-RTT·shield 건너뛰기 제거를 'arrivals가 있을 때'로 한정했으므로 카드 범위와 어긋날 소지가 있다. 반면 L1 카드 2항의 '건너뛰기 사유와 상관없이 모든 연결'을 none 대체 우도에도 적용한 것으로 읽을 수도 있어 카드 자체가 모호하다. Codex는 이 변경을 문서에 적었다. B6·B8_j20 회귀에 얼마나 기여했는지는 분해 실험이 없어 모른다. || learn3.py:722-750(skip은 legacy_skip_reason에만 쓰이고 categorical L 적용은 skip과 무관). skipfrac.py(none, seed 31~40): B6 categorical 갱신 13,490개 중 nominal2 2,427 + guard 889 = 3,316(24.6%). B8_j20는 nominal2 2,271(16.8%), 그중 grade 2가 917. TASKS.md L3 카드 1항. docs/L1_learning.md:61('명목 2-RTT가 무조건 갱신을 막는다는 옛 시험 기대'를 고침).

- [low] c1 이득은 회신 비용 0을 가정한 수동 관측 모형의 값이고, 회신은 인증되지 않은 비표준 서버 확장이다 :: 주 비교(c1)의 기대 비용 감소는 D14가 정한 대로 회신의 비용을 HCT, 증폭 예산, 다음 연결 간격에 넣지 않은 W0 위 수동 관측 모형에서 나왔다. C1은 수정한 서버만 보내는 평문 부채널이고 인증 위협 모형이 따로 있다. 실제 와이어에서 회신 비용과 효과를 재는 T7은 todo다. 감사자의 판정은 'C1이 있을 때'라는 단서는 달았지만 '공짜 회신 가정'은 적지 않았다. || DECISIONS_NEEDED.md D14('회신 비용은 HCT·증폭 예산·다음 연결 간격에 포함하지 않는다. 실제 와이어 C1 효과는 G1/T4 이후 개발 측정으로 남긴다'). docs/c1_status.md('인증되지 않은 평문 부채널', '회신이 증폭 예산에 영향을 주지 않는다는 문장을 이 구현 검증만으로 일반화할 수 없다'). L1_benchmark_precision_v1.json observation_scope('passive observer changes available evidence only'). LOOP_STATE T7 todo.
