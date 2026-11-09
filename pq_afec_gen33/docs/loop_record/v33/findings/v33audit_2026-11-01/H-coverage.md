# H-coverage

## summary
결론: 이번 루프는 준비, 재현, 테스트베드 쪽 일은 거의 다 끝냈습니다. 반면 알고리즘에서 실제로 활성 코드에 들어간 변경은 L1 하나이고, 측정은 한 건도 하지 않았습니다. 감사 194항목의 "처리함 104"는 수정을 마친 개수가 아닙니다.

1) 추적 수치
- coverage_check.py는 읽기만 하는 스크립트라 그대로 돌렸습니다. 결과는 "항목 194 누락 0"이고, 이 스크립트는 감사 항목이 과제 카드에 연결됐는지만 봅니다.
- 처리 상태는 Codex의 runs\coverage_snapshot.py와 같은 규칙으로 스크래치에서 다시 계산했습니다. MORNING_REPORT 수치(처리함 104, 넘김 60, 기록 없음 29, 처리 안 함 1)와 정확히 같았습니다.
- 처리함 104개를 나누면 이렇습니다.
  - 매핑된 과제가 모두 done: 60개(코드·인프라 41, A1 문서 정정 13, 세계·벤치 자체 항목 6)
  - 코드가 일부만 처리하고 나머지 과제가 열려 있음: 16개
  - A1 문서만 쓰고 측정·정책 과제가 열려 있음: 10개
  - A0·W0·W1에서 재현이나 세계 모형만 하고 수정 과제가 열려 있음: 18개
- 처리함 표본 20개(층화)를 확인했습니다. 실제 처리 10, 부분 3, 표기와 반대(저장소 무게) 1, 재현만 5, 문서만 1입니다.
- 넘김 60개는 넘겨받은 과제 중 done이 하나도 없습니다. 그중 34개는 넘겨받은 과제가 blocked이거나 blocked 과제에 의존해서 시작할 수 없습니다.
- 기록 없음 29개 중 21개도 같은 교착에 묶여 있습니다.

2) 10-29 처방 매핑
- 알고리즘 (1)~(6)
  - (1) 부분: 도착 증거 학습은 L1(Python)·E12(Go 거울)·T4(Go 관측)로 완료. 2-RTT 건너뛰기·감시층 벌점·재평가 제거(L3)는 시도했으나 기각.
  - (2) M1: 시도했으나 기각.
  - (3) J3 비용 모형: J1·J3·J5·J6·J7·J8은 기각 또는 blocked, J2·J4는 미착수. padfec3/layout.py와 decide3.py는 기준선에서 변경 0입니다.
  - (4) L6, (5) O1: 미착수(교착).
  - (6) O2: 시도했으나 기각.
- 측정 처방: X1·X4·X9 모두 0회. 비교 팔(T3·T2)만 준비됐습니다.
- 코드 처방
  - 완료: 원자료 보관(S1), 10-07 이식(S4), 줄 끝 LF 규칙과 태그(R-E-wt hygiene 브랜치, push 없음)
  - 초안만: CI(실행 0회)

3) 시간
- 벽시계 55.4시간 중 27.9시간이 반복 14의 사용 한도 중단입니다. 실제로 일한 시간은 27.2시간입니다.
- 그중 41.8%(11.4시간)는 결국 기각된 후보 7개의 전체 평가에 썼습니다.
- 12.2%(3.3시간)는 blocked로 끝난 비활성 참조 7개에 썼습니다.
- 측정에 쓴 시간은 0입니다.
- G1·T7이 todo로 남은 이유는 의존 구조입니다.
  - G1은 L2·L3·L4·J1·J2·J6·L5·J7이 모두 done이어야 시작할 수 있고, T7은 G1·G2를, X*는 T7을 기다립니다. 루프 규칙은 의존이 모두 done인 과제만 고릅니다.
  - 그래서 후보들이 blocked가 되자 미완 과제 51개 중 32개가 영구 대기에 들어갔습니다.
  - 이 구조는 Claude가 설계했습니다. Codex는 J7과 G1 사이 순환은 D19로 풀었지만, T7과 G1 교착은 결정 항목에 올리지 않았습니다.
  - 의존이 풀려 바로 할 수 있던 해제 과제(E10, E14, E15, E25, E27, E28, E1)는 순서 맨 뒤에 붙어 한 번도 실행되지 않았습니다.

남은 일 (우선순위 순)
- 코드에서 바로 고칠 것
  1. 의존 그래프 수정: G1을 "E12 + destCache3 궤적 관문"으로 재정의하거나, T7 의존에서 G1·G2를 뺍니다.
  2. T7 러너(experiments/v33/devbed.py, 아직 없음)를 쓰고 dry-run과 smoke까지 돌립니다.
  3. E10을 하고 J6을 다시 판정합니다.
  4. E14·E15를 하고 M1을 다시 판정합니다.
  5. 추적 집계를 "반영 / 재현만 / 넘김-진행 가능 / 넘김-교착"으로 나누고, glob이 백업 스냅숏을 읽지 않게 고칩니다.
  6. 검증 원자료 4.1 GB를 저장소 밖으로 옮기고, 크기 훅을 버전 관리되는 설치 경로로 옮깁니다.
  7. LOOP_STATE의 R2 doing과 status running을 정리합니다.
- 실측으로 확인할 것
  1. X1: 같은 바이트로 패딩과 패리티 비교(핵심 주장)
  2. X9: PTO 비율 재측정(방향 전환 근거)
  3. X4: 토큰·resumption 기준선
  4. X6: L1 대 v3.1 대 gen-2. none 경로 B6 악화가 실제로도 나타나는지 봅니다.
  5. X3: 경주표와 PTO 배수
- 사람이 정할 것
  1. none 경로를 주 비교로 둘지, 진단으로 둘지. L1도 같은 기준으로 다시 판정해야 합니다.
  2. 정확도 수정(J1 등)에도 HCT 개선을 요구할지
  3. G1·T7 의존을 어떻게 다시 정의할지
  4. 증거 보관 정책과 공개용 이력: D40 시험 키, D1, D2, D11
  5. R-E-wt hygiene 브랜치와 태그를 merge·push할지
  6. 루프가 스스로 정한 D13~D39 기본값을 승인할지(특히 D14, D18, D20)

스크래치 산출물은 C:\Users\scien\AppData\Local\Temp\claude\C--Users-scien\98dad099-940c-4208-8359-61078035dc93\scratchpad\v33audit\H-coverage\ 에 있습니다.
- cov_snapshot_ro.py, cov_details.json
- sample20.md
- hist.py, alloc.py
- commits.py, commits.out.txt
- handled_list.txt
- coverage_check.out.txt

## verdict_improved
부분적으로 발전했다. 다만 무게중심이 연구 증거가 아니라 인프라 쪽이다.

- 인프라: 기준선(v3.2-dev 사본 90859b973)보다 분명히 나아졌다. 테스트베드 기능, 보존과 재현 가능성, 시험 위생 모두 근거가 있다.
- 알고리즘: 활성 코드에 들어간 변경은 L1 하나다.
  - 세계 시뮬레이터의 C1 경로에서는 개선을 보였다.
  - none 경로 B6는 +6.37 ms 악화했다.
  - 카드 목표(B1 < 0.1 ms)는 미달이다(1.226 ms).
  - 비용 모형(layout.py, decide3.py)은 그대로다.
- 연구 질문에 대한 새 측정 증거: 0건이다.
- 감사 194항목: 처방이 실제로 반영된 것은 많아야 60개다. 진행 경로가 막힌 미처리가 최소 55개다.
- 10-29 처방 (1)~(6): 완료 0, 부분 1, 시도 후 기각 3, 미착수 2.
- 측정 처방: 모두 미착수다. 비교 팔만 준비됐다.

완수도가 낮은 주원인은 Codex의 작업 품질보다 의존 교착(Claude가 설계)과, 그것을 풀지 않은 Codex의 우선순위다. 해제 과제를 맨 뒤에 둔 것, 교착을 결정 항목에 올리지 않은 것이 여기에 해당한다. L1과 이후 후보에 다른 채택 기준을 쓴 것도 기각이 연쇄된 데 영향을 줬다.

## frame_fit
과제 하나하나는 연구 틀 안에 있지만, 시간 배분은 틀의 중심에서 벗어났다.

연구의 신규성은 "클라이언트가 증폭 예산을 사려고 부풀리는 바이트를 패딩 대신 패리티로 낸다"이다. 이것을 직접 보여주는 X1(같은 바이트, 같은 자리에서 패딩 대 패리티)과, 방향 전환의 근거인 X9(PTO 비율 재측정)는 한 번도 돌지 않았다. T3 팔은 준비됐다.

대신 활성 시간의 약 54%가 학습층과 비용 모형 후보 평가, 비활성 참조에 쓰였고 모두 기각되거나 blocked로 끝났다.

채택된 L1의 이득은 C1 서버 피드백에서 나온다. C1은 비표준 서버 shim이고 인증 없는 평문 부채널이다. 그런데 이 연구의 레버는 서버 변경 없이 클라이언트만으로 성립한다는 점이다. 서버 피드백이 없는 none 경로에서는 L1이 오히려 나빠졌다(B6 +6.37 ms, Codex 문서값). 그래서 L1은 "클라이언트 단독"이라는 틀과 긴장 관계에 있다.

틀에 잘 맞은 부분도 있다.
- A1의 주장 정정은 볼트의 "쓸 수 있는 말 / 쓰면 안 되는 말" 목록과 같은 방향이다. M1이 기각됐으므로 "같은 바이트가 신용과 복구를 함께 산다"는 계속 쓰면 안 되는 말로 남는다.
- T2 토큰 팔은 볼트가 요구한 재방문 단서를 실험할 준비가 돼 있다.

R2 확증 프로토콜 초안(g3/v33/PROTOCOL_stage4_DRAFT.md)은 쓰지 않았다.

## errors

### H-01 [high] "처리함 104"는 수정 완료 수가 아니다. 추적 집계가 부풀려 있다 (repro=True)
coverage_snapshot.py는 추적 파일 하나라도 "처리함"이면 그 항목을 처리함으로 올린다. 그래서 A0(봉인 자료 재현), W0·W1(세계 모형), A1(문서 정정)의 처리함이 그대로 섞인다.

처리함 104개를 나누면 이렇다.
- 매핑 과제가 모두 done: 60개(코드·인프라 41, A1 문서 정정 13, 세계·벤치 자체 항목 6)
- 코드가 일부만 처리하고 남은 과제가 열려 있음: 16개
- A1 문서만 있고 측정·정책 과제가 열려 있음: 10개
- 재현·세계 모형만 있고 수정 과제가 열려 있음: 18개(A1-01, A1-02, A1-08, A1-09, A1-15, A2-02, A2-09, A2-14, A2-15, A2r1-03, A3-06, A4-01, A5-06, A5-07, A5-09, A7-15, A8-07, A8-08)

넘김 60개는 넘겨받은 과제 중 done이 0개이고, 그중 34개는 대상이 교착 상태다. 기록 없음 29개 중 21개도 교착이다. 따라서 194개 가운데 처방이 실제로 반영된 것은 많아야 60개(31%)이고, 진행 경로가 막힌 미처리가 최소 55개다.

MORNING_REPORT 3행은 단서 없이 104를 적었다. JSON의 note와 W1 기록에는 단서가 있다.

EVIDENCE: - C:\dev\codex_handoff\v33\runs\coverage_snapshot.py: disposition 우선순위 ("처리함", "다른 과제로 넘김", "처리 안 함")
- runs\iter063_coverage_status.json: counts {처리함 104, 넘김 60, 기록 없음 29, 처리 안 함 1}, with_open_mapped_tasks 142
- 스크래치 cov_snapshot_ro.py로 다시 계산: 같은 수치
- 분해 근거: 스크래치 cov_details.json, sample20.md

FIX: 집계를 "처방 반영(코드·문서)", "재현·기록만", "넘김: 진행 가능", "넘김: 교착", "기록 없음"으로 나누고, MORNING_REPORT 첫 줄을 그 숫자로 바꾼다.

### H-02 [high] 의존 교착 때문에 G1, G2, T7, X1~X9가 영구 대기다. 측정은 0건이다 (repro=True)
LOOP_STATE의 의존 관계는 이렇다.
- G1은 L1, L2, L3, L4, J1, J2, J6, L5, J7이 모두 done이어야 한다.
- T7은 G1과 G2를 기다린다.
- X 측정은 전부 T7을 기다린다.

LOOP_PROMPT 2-2는 의존이 모두 done인 과제만 고르고 blocked는 건너뛴다. 후보 7개가 blocked가 되자 미완 과제 51개 중 32개가 blocked 조상 때문에 시작할 수 없게 됐다. G1이 실제로 할 일(채택된 Python 변경의 Go 거울)은 채택된 것이 L1뿐이고, 그 거울은 E12에서 이미 끝났다.

의존 그래프는 Claude가 만들었다(LOOP_STATE created_by "Claude 2026-10-30"). Codex는 J7과 G1 사이 순환은 D19로 분해했다. 하지만 T7·G1 교착은 결정 항목으로 올리지 않았고, JOURNAL에 "T7은 G1/G2 의존이 풀리지 않아 건너뛴다"를 되풀이해 적기만 했다. MORNING_REPORT의 "도현님 결정이 필요한 것" 절에도 이 교착이 없다.

EVIDENCE: - LOOP_STATE.json의 tasks.G1.depends, T7.depends [G1, G2, S4, T1, T4], X*.depends [T7, ...]
- JOURNAL.md 518, 531, 546, 747행
- DECISIONS_NEEDED.md 45행(D19, J7 순환만 다룸)
- MORNING_REPORT.md 423~435행
- 스크래치 계산: blocked 조상 때문에 잠긴 과제 32개

FIX: 사람이 정한다. 방법은 두 가지다. G1을 "E12 + destCache3 궤적 관문"으로 재정의해서 닫거나, T7 의존에서 G1과 G2를 빼고 X* 측정은 S4, T7, 관문 PASS만 요구하게 바꾼다.

### H-03 [medium] 바로 할 수 있던 해제 과제를 순서 맨 뒤에 둬서 한 번도 실행하지 않았다 (repro=True)
아래 E 과제는 의존이 모두 done이었는데도 order 목록 맨 끝(R1 뒤)에 붙어 있었다.
- E1: 반복 4부터 실행 가능
- E10(J6 c6000의 distinct-action 영분산 MC 경계): 의존 W1, 반복 22부터 실행 가능
- E14(M1 세계의 신용·송신 재개 분리): 반복 30부터 실행 가능
- E15: 반복 39부터 실행 가능
- E25: 반복 48부터 실행 가능
- E27, E28: 반복 51부터 실행 가능

그동안 루프는 새 주 과제 O2, J5, O3, O4, J3, M4, J8을 2~3반복씩 열었고, 모두 blocked로 끝났다.

J6은 성능이 나빠져서가 아니라 "MC 경계 미정의"라는 분석 도구 문제로 기각됐다. 그런데 그 문제를 푸는 E10은 끝까지 실행하지 않았다. 지금 바로 할 수 있는 과제는 R2, R1, E1, E10, E14, E15, E25, E27, E28, E36, E37이다.

EVIDENCE: - LOOP_STATE.json order: E1~E37이 R2, R1 뒤에 있음
- 의존: tasks.E10 [W1], E14 [W1], E15 [S4, T6], E25 [T4, T5, T6], E27 [W1, T3], E28 [T2, T3, T5, E12]
- JOURNAL.md 반복 22: "c6000 두 주 비교의 MC 경계 미정의로 후보를 채택하지 않았다"

FIX: 기각 사유가 도구 결함이나 세계 모형 결함인 과제는 그것을 푸는 E 과제를 바로 다음 반복에 둔다.

### H-04 [medium] 막힌 과제의 후속 과제가 또 막힌 과제에 의존한다 (repro=True)
다음 과제들은 의존 목록에 blocked 과제가 들어 있어 시작할 수 없다.
- E7(J2, O3)
- E8(J1, J2)
- E9(O3, J5)
- E13(M1, J5, O3)
- E22(J7, O3, J3, T4)
- E23(J3)
- E26(E25, J3, E12, W1)

E26 카드는 "O3·J5·G1 완료를 의존으로 넣지 않는다"고 적었지만 J3를 넣었고, J3는 반복 54에서 blocked가 됐다. 반복 51 이후 만든 E27~E35는 "X 완료를 기다리지 않는다"로 이 문제를 피했다. 앞뒤 기준이 다르다.

이 경로 때문에 E8에 넘긴 A2-04, A2-05, A2-10, A2r1-04, A2r1-08, A7-14, A7-16과, E7에 넘긴 A2-07, A2r1-15, A7-13 등이 묶였다.

EVIDENCE: - LOOP_STATE.json tasks.E7, E8, E9, E13, E22, E23, E26의 depends
- EXTRA_TASKS.md 277~281행

FIX: 후속 과제의 의존에서 blocked 과제를 빼고, 실제로 필요한 관측이나 도구만 의존으로 둔다.

### H-05 [medium] 채택 관문이 L1과 이후 후보에 다르게 적용됐다 (repro=False)
L1의 기준은 이랬다.
- 주 비교는 c1 경로만이었다(D14, docs/L1_benchmark_execution.md:9).
- none 경로의 v32 대비 B6 악화 +6.372402 ms [5.165881, 7.578923]와 v31 대비 B6·B7 실패는 진단으로 분류했고, L1은 done이 됐다.

이후 L2, J1, J6, L5, M1의 기준은 더 엄격했다.
- none과 c1 둘 다 L1 대비 주 비교였다(docs/J6_preflight_budget.md:25, docs/L2_joint_report.md:9, docs/M1_evaluation_plan.md:11).
- 여기에 c1 경로의 유의한 감소 조건까지 요구했다.
- 그 결과 J1은 none 3셀 미확정으로 기각됐다.

같은 기준이면 L1도 none 경로에서 통과하지 못한다. 또 L1 카드의 완료 기준(B1 < 0.1 ms, L3와 함께 달성 허용)은 L3가 기각되면서 충족되지 않았다(L1 단독 B1 1.226227 ms). 그런데도 L1은 done으로 남아 있다.

수치는 Codex 문서값이며 다시 계산하지 않았다.

EVIDENCE: - JOURNAL.md 167행: L1 none 진단 fail, "D14의 C1 주 비교와 구분"
- JOURNAL.md 220, 228행: J1 "none 3셀의 비열등 미확정과 C1 감소 조건 부재로" 기각
- MORNING_REPORT.md L1 반복 16 항목
- TASKS.md L1 완료 기준

FIX: 사람이 정한다. none 경로를 주 비교로 둘지 진단으로 둘지 하나로 정하고, L1을 같은 기준으로 다시 판정한다.

### H-06 [medium] A6r1-12(저장소 무게)를 처리함으로 적었지만, 실제로는 루프가 문제를 크게 키웠다 (repro=True)
- 기준선 90859b973의 트리: 201파일, 21.7 MB
- HEAD의 트리: 113,746파일, 4,358.1 MB(무압축 합). pack은 1.79 GiB다.
- g3/v33/validation 아래만 112,541파일, 4,148.9 MB다.

20 MB를 넘는 파일(M1_wire_reference_01/02.tsv.gz 27.2 MB 등)은 크기 훅을 만들기 전인 반복 28~30에 이미 커밋됐다. S5가 만든 20 MB 거부 훅은 .git/hooks/pre-commit에만 있어서 clone하면 따라가지 않는다. 초안 CI(.github/workflows/ci.yml)는 이 4 GB 저장소를 통째로 checkout해야 한다.

EVIDENCE: - git ls-tree -r -l 크기 합: 기준선 201파일 21.7 MB, HEAD 113,746파일 4,358.1 MB
- git count-objects -vH: size-pack 1.79 GiB
- runs\S5_coverage.md 15행
- .git/hooks/pre-commit

FIX: 검증 원자료는 padfec_archive처럼 저장소 밖에 보관하고, 저장소에는 manifest와 요약만 둔다. 공개 전에는 새 이력으로 복사한다(D40과 함께 처리).

### H-07 [medium] 막힘 3연속 정지 장치가 partial에 리셋돼서, 성과 없는 18반복이 그대로 진행됐다 (repro=True)
run_loop.ps1은 partial이 나오면 blockStreak를 0으로 되돌린다. 그래서 정지 장치가 한 번도 작동하지 않았다.
- 반복 43~60(18회, 3.3시간): O2, J5, O3, O4, J3, M4, J8을 차례로 partial 1~2회 뒤 blocked로 끝냈다. done은 0이고, 새 E 과제만 14개(E22~E35) 생겼다.
- 반복 17~30에서도 done은 E12 하나였다.

Codex가 정지를 피하려 했다는 근거는 없다. 실행기 설계 문제이지만 결과적으로 사람에게 알림 없이 계속 돌았다.

EVIDENCE: - run_loop.ps1 231~236행: partial이면 blockStreak = 0
- LOOP_STATE.json history 43~60의 status

FIX: 정지 조건을 "N반복 동안 done 0" 또는 "blocked 과제 수 증가"로 바꾼다.

### H-08 [low] MORNING_REPORT 마감 내용이 LOOP_PROMPT 4절 요구를 다 채우지 못했다 (repro=True)
- "다음 밤 첫 과제"가 R2(문서 초안)이다. 교착 해소나 지금 실행할 수 있는 E 과제는 언급하지 않는다.
- "아침 확인 명령"은 git log 하나뿐이고 관문 명령과 벤치 명령이 없다.
- 70 KB 보고서 가운데 "숫자" 절은 띄어쓰기 없는 긴 로그 문장이라 팀이 읽기 어렵다. 예: "B1선택기준대비기대격차는v31 2.5982,v32 1.8821ms이고"

EVIDENCE: - MORNING_REPORT.md 433~445행
- 같은 파일 숫자 절의 W1 반복 11 항목
- LOOP_PROMPT.md 4절

FIX: 마감 보고에 교착 목록, 실행 가능한 과제, 관문·벤치 명령을 넣고, 숫자 절은 표로 요약한다.

### H-09 [low] 루프 종료 상태가 정리되지 않았다 (repro=True)
반복 64(R2)는 2026-11-01 08:53:29에 preflight와 state 파일만 남기고 끝 기록이 없다. LOOP_STATE는 status "running", current "R2", R2 "doing"(iterations 0), iterations 63으로 남아 있다.

실행기 로그(state/runner.log, runs/runs.log)가 없어서 끝난 원인이 마감인지 중단인지는 확인하지 못했다.

EVIDENCE: - runs\iter064_preflight.json, iter064_state_before.json, iter064_state_review.json: 모두 08:53:29
- LOOP_STATE.json status, current

FIX: 다음 실행 전에 R2를 todo로 되돌리고 status를 정리한다.

### H-10 [low] 추적 집계가 백업 스냅숏도 입력으로 읽고, 넘김 대상 카드 일부에서 추적이 끊긴다 (repro=True)
- coverage_snapshot.py의 glob "*_coverage.md"가 iter056_before_M4_coverage.md와 iter057_before_M4_coverage.md도 함께 읽는다. 이 두 파일은 진행 중이라는 뜻으로 "처리 안 함"을 써 두었다. 지금 최종 수치는 바뀌지 않지만, 백업이 더 생기면 집계가 흔들린다.
- 넘김 표기에서 E 카드를 가리킨 73건 중 16건은 그 E 카드 본문에 해당 감사 ID가 없다. 예: A8-06→E10, A1-M02→E14, Q-23→E8·E9, A2-17→E8

EVIDENCE: - runs\coverage_snapshot.py의 glob
- 스크래치 cov_details.json에서 A3-11, A7-18, A7-20, A8-01, A8-12의 이벤트
- 스크래치 검사 결과: "E-target mentions with item id in card: 57 missing: 16"

FIX: glob을 과제 ID로 시작하는 정식 파일명으로 좁히고, 넘김을 기록할 때 대상 카드에 감사 ID를 함께 적는다.

### H-11 [low] L1 판정은 표본을 사후에 늘려서 문턱을 아슬아슬하게 통과한 것이다 (repro=False)
- 반복 12에서 C1-v32 B6 비열등이 미확정으로 나왔다(조정 구간 [-0.592357, 0.573320]).
- 그러자 같은 seed prefix로 N을 131,072에서 1,048,576으로 늘려 다시 계산했다.
- 다시 계산한 상한은 0.479549 ms로, 0.5 문턱을 0.02 ms 차이로 통과했다.

Codex는 "사후 개발 정밀화이며 독립 확증이 아니다"라고 공개했다.

이 계산은 반복 14의 사용 한도 중단(27.9시간) 동안 v1 pool이 100개 중 52개에서 죽었고, v2에서 처음부터 다시 돌았다(run 5284 s). 결과적으로 셀 하나를 판정하는 데 반복 13~16과 활성 시간 약 3.1시간이 들었다.

EVIDENCE: - MORNING_REPORT.md L1 반복 12, 13, 14, 16 항목
- JOURNAL.md 122~170행

FIX: 표본 크기는 실행 전에 고정한다. 미확정이 나오면 그대로 미확정으로 보고하거나, 새 seed로 독립 반복한다.

### H-12 [low] 시험용 개인키 28개가 git 이력에 남아 있다 (repro=True)
T1(반복 32)이 검증 묶음에 개인키가 든 PEM 28개를 커밋했고, S5(반복 62)는 현재 추적에서만 지웠다. HEAD에 남은 PEM 12개에는 개인키가 없다. 테스트베드 전용 키라 당장 위험은 낮지만, 저장소를 공개하기 전에는 이력을 정리해야 한다(D40).

EVIDENCE: - 3eef6a737 커밋에서 삭제된 .pem 28개(git log --diff-filter=D)
- git grep "PRIVATE KEY" HEAD -- '*.pem': 결과 없음
- DECISIONS_NEEDED.md 119행

FIX: 공개용 사본은 이력 없이 새로 만든다(E37).

## changes
- 활성 Python 정책에서 바뀐 것은 padfec3/learn3.py 하나다(L1). 들어간 내용은 arrivals 우도(normalize_arrivals, arrival_likelihood), 3등급 우도(class_likelihood), STATE_VERSION 4, POLICY_VERSION v3.3-dev다. padfec3/layout.py와 decide3.py는 기준선 90859b973에서 변경 0이다. padfec/policy.py는 +2줄(S4)이고, afec/rs.py와 channel.py는 몇 줄만 바뀌었다. 감시층(guard_common, guard_excess)과 n_reeval은 HEAD에 그대로 남아 있다.
- Go 쪽 변경은 이렇다. policy3_l1.go(E12의 L1 거울)가 새로 생겼다. 테스트베드 파일 observation.go, decoder_index.go, hold.go, boundary.go, certificate.go, comparison.go, flight_trace.go, flight_shape.go, revisit.go, revisit_guard.go, udp_linux.go가 새로 생겼다. qamp.go는 크게 수정됐다. 새 기능은 대부분 기본 off 플래그다.
- 커밋은 기준선 뒤로 121개이고, 그중 45개는 코드 변경 없이 증거·문서·JSON만 바꿨다. docs/*.md는 102개가 새로 생겼다. tests와 experiments/v33는 171파일이 추가되고 14파일이 수정됐다(대부분 비활성 후보, 참조, 벤치 코드).
- 과제 상태(전체 90개 = 주 53 + E 37): done 25(주 17, E 8), blocked 14(전부 주 과제: L2, L3, J1, J6, L5, J7, M1, O2, J5, O3, O4, J3, M4, J8), todo 49, doing 1(R2), skipped 1(E21).
- 시간: 벽시계 55.4시간(10-30 01:26 ~ 11-01 08:53)이다. 반복 14가 27.9시간(사용 한도 중단 포함)이라 활성 시간은 27.2시간이다.
- 기각된 후보 평가 7개: 11.36 h(41.8%)
- 세계·벤치 W0·W1: 3.89 h(14.3%). 이 중 W1이 6반복에 3.43 h
- 테스트베드 S4·T1~T6: 3.74 h(13.8%)
- blocked로 끝난 비활성 참조 7개: 3.31 h(12.2%)
- L1: 활성 4반복 3.07 h(11.3%), 반복 14 별도
- 준비·위생: 1.04 h
- A0·A1: 0.41 h
- E12: 0.35 h
- 측정: 0 h
- 10-29 처방 (1) 데이터그램 도착 증거 학습과 감시층 정리: 부분.
- 완료: L1(Python), E12(Go 거울), T4(Go 관측 arrivalEvidence → qamp.go:2569)
- 시도했으나 기각: L3. C1 B1 절대 0.093952 [0.060876, 0.127028] 미확정, B8_j20 +0.867859 [0.569639, 1.166079] 악화(Codex 문서값)
- W1에서 L1 단독 B1 후회는 1.226227 ms로, 감사 목표 0.053에 크게 못 미친다.
- 10-29 처방 (2) M1 선행 패리티 보류 복호: 시도했으나 기각.
- Go hold.go와 -lead-hold(기본 off)가 생겼고, 와이어 대조는 700,116 사례가 통과했다(Codex 문서값).
- 전체 평가 120셀 중 15셀 fail, 23셀 미확정이었다.
- 이 과정에서 세계 모형 결함(뒤 패리티가 서버 송신을 재개함)을 찾았다. 후속 E14~E16은 todo다.
- 10-29 처방 (3) J3 비용 모형 보정: 시도했으나 기각되거나 미착수.
- 시도 후 기각 또는 blocked: J1, J5, J6, J7. J3와 J8은 참조만 만들고 blocked다.
- 미착수: J2, J4(교착)
- 활성 layout.py 변경은 0이다.
- 10-29 처방 (4) 첫 방문 행동(L6)과 (5) 바이트 가격(O1): 둘 다 미착수다. L6은 L5 blocked, O1은 L4를 거쳐 L3 blocked 때문에 시작할 수 없다.
- 10-29 처방 (6) 업링크 오라클 제거(O2): 시도했으나 기각. 비활성 참조는 만들었지만, 세계 진단 240대조 중 16개에서 후회가 6.5 ms를 넘었다(Codex 문서값). 후속 E22는 교착이다.
- 10-29 측정 처방: X1(같은 바이트 패딩 대 패리티), X4(토큰·resumption 기준선), X9(PTO 비율 재측정)은 모두 0회다. X2, X3, X5, X6, X7, X8도 0회다. 준비된 것은 T3 비교 팔(pad-junk, dup, k-inflate, Initial 확대)과 T2 토큰·resume 팔뿐이다. T7 러너(experiments/v33/devbed.py)는 없다.
- 10-29 코드 처방은 대부분 끝났다.
- 원자료·봉인 바이너리 보관: 완료(S1). C:\dev\padfec_archive에 INDEX.json, MANIFEST.sha256, binaries가 있다. 다만 같은 PC 안이다.
- 10-07 gen-2 수정 이식: 완료(S4). docs/S4_port_result.md에 9파일 이식이 기록돼 있다.
- .gitattributes: R-E-wt hygiene/2026-10-30 브랜치 59d2833에 LF 규칙을 넣었다. main(6bbd11f)에는 아직 반영되지 않았다.
- 태그: R-E-wt에 4개(gen2-fix-73aa420, gen2-frozen-4bab4a5, v3.1-stage3, v3.2-dev)가 있고 push하지 않았다. gen33 저장소에는 태그가 0개다.
- CI: .github/workflows/ci.yml 초안만 있고 실행된 적은 없다.
- 저장소 크기: 201파일 21.7 MB에서 113,746파일 4,358.1 MB(pack 1.79 GiB)로 커졌다.
- 루프가 스스로 정한 결정은 D13~D40으로 28개다. 사람 결정 D1~D12는 기본값을 유지했다.

## improvements
- [moderate] 데이터그램 단위 도착 증거 학습(L1)이 Python과 Go 양쪽에 들어갔다 :: - HEAD padfec3/learn3.py 226, 249, 294, 743, 748행
- experiments/quicbed/policy3_l1.go, observation.go:196, qamp.go:2569
- Codex 문서값: E12 Go·Python 대조 90,000결정 일치. W1에서 C1-v32 B1 -0.6558, B2 -2.1187, B7 -3.6422 ms/연결. B3·B4 사후 평균이 0.0002 이하로 수렴.
- 한계: 세계 시뮬레이터 결과일 뿐이다. C1은 서버 shim이 필요하고, none 경로 B6는 +6.37 ms 악화했다.
- [strong] X 측정에 필요한 테스트베드 기능이 대부분 갖춰졌다 :: - 결정적 인증서: certificate.go와 시험 3개
- 같은 바이트 비교 팔: comparison.go와 inflation 경로
- 토큰·resumption: revisit.go
- 복호기 색인과 LRU: decoder_index.go, boundary.go, qamp_decoder_index_test.go 시험 12개
- 도착·복원 관측: TestObservationRecoveredHandshakeFeedback, unrecoverable_final
- 재전송 모양: flight_shape.go
- S4의 10-07 이식
- 모두 HEAD에 있고 표본 확인을 통과했다. Go 시험 231개는 Codex 문서값이다. 실제 측정은 아직 0건이다.
- [strong] 보존과 재현 가능성이 나아졌다 :: - S1: padfec_archive 378항목 해시 검증(Codex 문서값). 폴더가 있는 것은 직접 확인했다.
- S3: 세대 경로를 분리하고, 재현 빌드 SHA가 일치한다.
- A0: 감사 수치를 g3/v33/evidence/01~07 스크립트와 JSON으로 고정했다. 45/45 일치(Codex 문서값).
- S2: 새 clone에서 봉인 해시 92/92가 유지된다(Codex 문서값).
- [moderate] 정책을 쓰지 않는 독립 세계 시뮬레이터와 회귀 벤치가 생겼다 :: - 코드: experiments/v33/worldsim.py, bench.py, bench_oracles.py
- 12가족, 15조건, 20 seed 기준값과 원형 정책 실패 범위를 보존했다(W1).
- 후보 7개를 같은 seed와 같은 문턱으로 짝비교해서 기각할 수 있었다.
- [moderate] 정직성 절차를 지켰다 :: - 후보를 기각할 때마다 활성 정책을 L1로 되돌리고 시험을 다시 돌렸다. HEAD learn3.py는 L1 상태다.
- seed, 문턱, 세계 매개변수를 바꾸지 않았다는 기록과 실패 로그를 보존했다(JOURNAL의 "버린 것과 이유").
- 세계값, 모형값, 측정값을 구분해 표시했다.
- [moderate] 시험 위생이 나아졌다 :: - pytest.ini, tools/lint_ast.py, tools/doctor.py, tools/drift_check.py, tools/runtime_fingerprint.py가 생겼다.
- 기본 pytest가 Windows 1792개, Ubuntu 1794개 통과(Codex 문서값).
- CI 초안이 있다. 다만 원격이 없어 실행된 적은 없다.
- [weak] 추적 연결은 끊김 없이 유지됐다 :: - coverage_check.py 실행 결과 "항목 194 누락 0"이다. 모든 감사 항목이 그 ID를 적은 과제 카드에 연결돼 있다.
- 넘김 대상 E1~E37 카드는 모두 EXTRA_TASKS.md에 있다.

## checked_but_ok
- coverage_check.py는 쓰기 없는 스크립트라 그대로 실행했다(python -I -B, 출력은 스크래치). 결과 "항목 194 누락 0". FINDINGS_INDEX 171개와 EXTRA_SOURCES 23개가 모두 카드에 연결돼 있다.
- MORNING_REPORT 첫 줄 수치(처리함 104, 넘김 60, 기록 없음 29, 처리 안 함 1)를 같은 규칙으로 다시 계산했고 정확히 일치했다. iter063_coverage_status.json의 with_open_mapped_tasks 142도 일치한다.
- 처리 안 함 1개(A1-11)는 검증자가 doubtful로 판정한 제안을 하지 않은 것으로, TASKS의 M1 "하지 말 것"과 맞는다.
- LOOP_PROMPT 2-2.1의 "3연속 partial이면 분할" 규칙은 지켰다. W1은 반복 8에서 E2~E4로, L1은 반복 14에서 E5·E6로 나눴다.
- 반복 목표 75분: 반복 14(사용 한도 중단)를 빼면 가장 긴 반복이 71.9분이다.
- 처리함 표본 중 실제 처리 10건은 HEAD에서 코드와 시험 흔적을 확인했다(sample20.md): A2-01, A3-02, A3-03, A3-08, A3-15, Q-15, A6-10, A3-04, A2-06(L1 경유), A4-10.
- S2: R-E-wt hygiene/2026-10-30 브랜치에 .gitattributes 커밋 59d2833과 태그 4개가 있다. main 6bbd11f는 그대로이고 push는 하지 않았다.
- C:\dev\padfec_archive가 있고 INDEX.json, MANIFEST.sha256, binaries, v31_stage3 등이 들어 있다. 해시 재검증은 하지 않았다.
- HEAD에서 추적 중인 PEM 12개에는 개인키가 없다(git grep "PRIVATE KEY" 결과 없음).
- 넘김 대상 E1~E37 카드는 모두 EXTRA_TASKS.md에 있다. 다만 제목 수준이 E1~E24는 ###, E25~E37은 ##로 섞여 있다.
- guard 경고로 뜬 볼트 변경 6건은 10-30·10-31의 다른 주제 세션 노트(AI_TOP_100, mTOR, 헤모글로빈, PowerGuard)다. MEMORY 색인에 있는 다른 세션 작업과 일치해 Codex가 쓴 것으로 보이지 않는다. 변경 주체를 직접 확인하지는 못했다.
- 이번 검증은 읽기 전용으로 했다. 저장소와 handoff 폴더에 __pycache__나 .pyc가 새로 생기지 않았고, git은 log, show, diff, ls-tree, ls-files, grep, cat-file, count-objects만 썼다.

## VERIFY

- H-01 (error): **partly** sev=high :: 핵심 수치는 전부 그대로 재현됐다. 처리함 104 가운데 매핑 과제 모두 done 60, 열린 과제가 남은 44(A1 문서만 10, A0·W0·W1 재현만 18, 나머지 16)이고, 넘김 60 중 넘겨받은 미완 과제가 모두 교착인 것 34, 기록 없음 29 중 21이 교착이다. 18개 ID 목록도 감사자 목록과 정확히 같다. 다만 하위 주장 '넘김 60개는 넘겨받은 과제 중 done이 0개'는 틀렸다. A1-04, A4-03, A8-06(J6), A2r1-11(L1), A1-12, A2-11, A2r1-10(L5), A2-17(J1) 8개는 넘김 대상 목록에 T4가 들어 있다. T4는 반복 33에 done이 됐지만 이 항목들을 기록하지 않았다(missed 1 참고). 결론(실제 반영은 많아야 60개)은 유지되고 오히려 추적이 더 약하다는 근거가 된다. 'MORNING_REPORT 3행'은 실제로 5행이다. || 스크래치 snap.py(coverage_snapshot.py와 같은 논리, 쓰기 없음): {'처리함':104,'다른 과제로 넘김':60,'아직 추적 기록 없음':29,'처리 안 함':1}. split.py: '처리함 all-mapped-done 60 some open 44', Counter A1 10, A0 6, W0 6, W1 6. defer.py: 'all not-done targets locked 34', 'no-record 29 all mapped locked 21'. donetgt.py: 'J6 A1-04 -> T4 done@ 33 target coverage mentions: False' 등. L5_coverage.md 'A1-12 | 다른 과제로 넘김(E11,O4,G1,T4)'. MORNING_REPORT.md:5 '감사194항목 {...104...}'.

- H-02 (error): **confirmed** sev=high :: 직접 계산으로 todo·doing·skipped 51개 중 32개가 blocked 조상 때문에 잠겨 있다. 지금 실행 가능한 과제 11개도 감사자 목록과 같다. G1 depends에 blocked인 L2, L3, J1, J6, L5, J7이 들어 있고 T7은 G1, G2를 기다린다. X 공통 조건도 'G1·G2·S4·T7 완료'다. JOURNAL은 'T7은 G1/G2 ... 의존이 풀리지 않아 건너뛰고'를 되풀이했고 DECISIONS_NEEDED에는 D19(J7·G1 순환)만 있으며 T7·G1 교착 결정 항목은 없다. MORNING_REPORT 결정 절(423~431행)에도 없다. || snap.py 출력 'locked by blocked ancestor (todo/doing/skipped) 32 [L4, J2, G1, G2, T7, X6, X1, X4, X2, X3, X9, ...]', 'runnable now [R2, R1, E1, E10, E14, E15, E25, E27, E28, E36, E37]'. LOOP_STATE tasks.G1.depends ['L1','L2','L3','L4','J1','J2','J6','L5','J7'], T7.depends ['G1','G2','S4','T1','T4']. TASKS.md G1 카드, X절 '공통: 시작 전 G1·G2·S4·T7 완료'. JOURNAL.md 518, 531, 546, 747행. DECISIONS_NEEDED.md 45행 D19.

- H-03 (error): **confirmed** sev=medium :: E 과제는 order 목록에서 R2, R1 뒤에 있고, E1 카드는 'TASKS 본래 52과제를 먼저 진행한 뒤 실행한다', E10 카드는 '본래 TASKS 뒤 E9 다음에 등록'이라고 Codex 스스로 적었다. 같은 루프에서 E12는 J7을 풀려고 order에서 J7 바로 앞에 끼웠으므로, 해제 과제를 앞에 둘 수 있었는데 E10·E14 등에는 그렇게 하지 않은 것이 확인된다. J6 기각 사유가 'MC 경계 미정의'(점추정은 none·C1 각각 -2.47/-2.51 ms)인 것도 맞다. 반복 번호는 의존 완료 반복 기준이라 하나씩 어긋난다(A0 done 반복 4이므로 E1은 반복 5부터). || LOOP_STATE order [..., 'L5','E12','J7', ..., 'R3','R2','R1','E1', ... 'E37']. EXTRA_TASKS.md E1 카드 '예상 시간' 줄, E10 카드 '의존: W1 ... 본래 TASKS 뒤 E9 다음에 등록'. history: A0 done@4, W1 done@11, T6 done@39, T3 done@41. MORNING_REPORT.md:127 'B12 c6000 none -2.473480 ms와C1 -2.506470 ms는공유MC경계null'.

- H-04 (error): **confirmed** sev= :: LOOP_STATE의 depends가 그대로다. E7 [J2,O3], E8 [J1,J2], E9 [O3,J5], E13 [M1,J5,O3], E22 [J7,O3,J3,T4], E23 [T4,T6,J3,E12], E26 [E25,J3,E12,W1]. E26 카드의 '재진입: E25·E26은 O3·J5·G1 완료를 의존으로 넣지 않는다' 문장도 확인했다. 덧붙이면 E26 등록(반복 48) 때 J3는 아직 todo였고 반복 54에 blocked가 된 뒤 E26 의존을 고치지 않은 것이다. || LOOP_STATE.json tasks.*.depends 출력. EXTRA_TASKS.md 277행 '의존: E25, J3, E12, W1', 281행 '재진입 ...'. history: O3 blocked 반복 48, J3 blocked 반복 54.

- H-05 (error): **confirmed** sev=medium :: 인용한 문서 줄을 직접 확인했다. L1은 c1만 주 비교였고(L1_benchmark_execution.md:9 'c1이 주 비교'), J6·L2·M1은 none과 c1 둘 다 L1 대비 주 비교에 C1 감소 조건까지 붙었다(J6_preflight_budget.md:25). L1의 none B6 v32 대비 +6.372402 [5.165881, 7.578923] 실패와 B1 1.226227 [0.951607, 1.500847] 목표 실패는 Codex 문서값과 일치한다. L1 카드 완료 기준 'B1 < 0.1 ... L3와 함께 달성해도 된다', '다른 시나리오 악화 없음'이 L3 기각 뒤에도 다시 판정되지 않았다. 숫자는 다시 계산하지 않았다. || git show HEAD:docs/L1_benchmark_execution.md 9행, docs/J6_preflight_budget.md 25행, docs/L2_joint_report.md 9행, docs/M1_evaluation_plan.md 11행. runs/L1_precision_disposition.md 31, 35행. JOURNAL.md 220, 228행. TASKS.md L1 카드 '완료 기준(W1)'.

- H-06 (error): **confirmed** sev=medium :: 크기 수치를 그대로 재현했다. 20 MB 초과 파일 5개가 HEAD에 있고 훅은 staged 파일만 보므로 이미 들어간 파일은 남는다. 훅 설치 스크립트나 core.hooksPath가 없어 clone에 따라가지 않는다. CI는 actions/checkout으로 전체 트리를 받는다. 한 가지만 고친다. 20 MB 초과 파일 중 J7_validated_runs_v1.json(21.0 MB)은 반복 27(957dbbd4a, 10-31 21:50)에 커밋됐으므로 '반복 28~30'이 아니라 '반복 27~30'이다. || git ls-tree -r -l: 90859b973 '201 files 21.7 MB', HEAD '113746 files 4358.1 MB', g3/v33/validation '112541 files 4148.9 MB'. git count-objects -vH 'size-pack: 1.79 GiB'. 20 MB 초과: 21038432 J7_validated_runs_v1.json, 23942349 x2 M1_validated_runs_v1.json, 27206885 x2 M1_wire_reference_0[12].tsv.gz. 추가 커밋 957dbbd4a, 21cd5334e, 9c6070624, dd630f270. tools/precommit_size.py staged_sizes는 diff --cached만 검사. .git/hooks/pre-commit만 존재, git config core.hooksPath 없음.

- H-07 (error): **partly** sev=low :: 현상은 맞다. 반복 43~60의 18회는 partial과 blocked가 번갈아 나와 done 0, 실제 소요 합 198.5분(3.3시간), 새 E22~E35 14개다. 반복 17~30의 done도 E12 하나다. run_loop.ps1 231~232행이 partial에서 blockStreak를 0으로 되돌리는 것도 맞다. 그러나 이번 루프가 run_loop.ps1로 돌았다는 근거가 없다. 실행기가 시작할 때 무조건 쓰는 state/runner.log, 반복마다 만드는 iterNNN_prompt.md, iterNNN.jsonl, iterNNN_stderr.txt가 하나도 없고, iterNNN_last.json은 Codex의 iterNNN_finish.py가 직접 썼다. 감사자 스스로 H-09에서 실행기 로그가 없다고 적었다. 따라서 '정지 장치가 partial 리셋 때문에 작동하지 않았다'는 원인 서술은 확인할 수 없고, 정황상 정지 장치 자체가 없었을 가능성이 높다. || run_loop.ps1 25~26행 $RunnerLog=state\runner.log, 76행 시작 시 Write-Log. ls runs | grep -cE '^iter[0-9]{3}_prompt\.md$' = 0, '.jsonl' 0, '_stderr.txt' 0. state/ 에 runner.log 없음. runs/iter063_finish.py 69행 save(r / "iter063_last.json", last). runs/empty_stdin.txt 생성 10-30 01:09:04(run_loop.ps1 저장 01:09:03, 건식 실행 시점). history 43~60 소요 합 198.5분.

- H-08 (error): **confirmed** sev= :: LOOP_PROMPT 4절은 아침 확인 명령으로 git log, 관문 명령, 벤치 명령을 요구한다. MORNING_REPORT 437행 이하에는 git log 한 줄만 있다. '다음 밤 첫 과제'는 R2 초안이고 교착 해소나 실행 가능한 E 과제 언급이 없다. 인용한 띄어쓰기 없는 문장도 105행에 그대로 있다. 행 번호 433~445는 파일이 443행이라 433~443이다. || LOOP_PROMPT.md 104행. MORNING_REPORT.md 433행 '## 다음 밤 첫 과제', 437행 '## 아침 확인 명령', 코드 블록에 'git -C C:\dev\pq_afec_gen33 log --oneline'만. 105행 'B1선택기준대비기대격차는v31 2.5982,v32 1.8821ms이고'.

- H-09 (error): **confirmed** sev= :: LOOP_STATE status 'running', current 'R2', R2 'doing' iterations 0, iterations 63을 직접 확인했다. iter064_* 세 파일은 08:53:29에 만들어졌고 그 뒤 기록이 없다. 실행기 로그도 없다. || LOOP_STATE.json 최상위 {'status':'running','current':'R2','iterations':63}, tasks.R2 'doing'. ls --time-style=full-iso runs/iter064_*: 08:53:29.59~.60. state/runner.log, runs/runs.log 없음.

- H-10 (error): **confirmed** sev= :: glob '*_coverage.md'가 iter056_before_M4_coverage.md, iter057_before_M4_coverage.md를 읽고, 거기 A3-11, A7-20, A8-01, A8-12가 '처리 안 함'으로 적혀 있다. 백업을 빼고 다시 세도 수치는 같다. E 카드에 감사 ID가 없는 넘김도 확인했다(A8-06→E10, A1-M02→E14, Q-23→E8·E9, A2-17→E8 모두 False). 다만 내 방식(넘김 줄의 셋째 칸까지 E 번호 전부)으로는 고유 짝 104개 중 21개가 빠져 감사자의 '73건 중 16건'과 다르다. 세는 범위 차이이고 결함 방향은 같다. || snap.py 'backup-ev A3-11 처리함 [(iter056..., 처리 안 함), ...]', 'no-backup {처리함:104, 넘김:60, 기록 없음:29, 처리 안 함:1}'. ecards.py 'unique pairs 104 missing 21', 'A8-06 E10 False', 'A1-M02 E14 False', 'Q-23 E8 False', 'Q-23 E9 False', 'A2-17 E8 False'.

- H-11 (error): **partly** sev=low :: 핵심 사실은 맞다. 반복 12의 C1-v32 B6 조정 구간 [-0.592357, 0.573320] 미확정 뒤 N 131072에서 1048576으로 늘린 같은 seed prefix의 재계산이 상한 0.479549로 통과했고, Codex가 '같은 seed prefix를 쓴 사후 개발 정밀화이며 독립 재현이나 확증이 아니다'라고 적었다. 두 가지는 고친다. 늘린 것은 세계 기준 비용의 MC 표본이고 판정의 seed 표본(20개)은 그대로라서, 실험 자료를 더 모은 optional stopping과는 성격이 다르다(MC 폭 0.129→0.046). 시간도 반복 13~16 실제 작업은 약 2.3시간(17.1+약 11+39.7+70.3분, 반복 14는 07:11 이후 Codex 활동 없음)이고 3.1시간은 반복 12를 넣어야 나온다. || MORNING_REPORT.md:107 '[-0.592357394,0.573320041]로 0.5 비열등 미확정', :115 '조정[-0.517391,0.479549]'. runs/L1_precision_disposition.md 11행, 27행 '공유 MC 경계는 0.045684'. history 반복 13 17.1분, 15 39.7분, 16 70.3분. runs/ 파일 시각: 반복 14 시작 07:02 뒤 마지막 Codex 산출물 07:11(L1_precision_artifact_check.py), 08:05는 계산 stdout뿐.

- H-12 (error): **confirmed** sev= :: 3eef6a737에서 지운 .pem 28개 모두 3eef6a737^ 내용에 'PRIVATE KEY'가 있고, 이 파일들은 60a2f18f9(T1, 11-01 01:21:44, 반복 32)에서 추가됐다. HEAD의 .pem 12개에는 개인키가 없다. HEAD 안 다른 'PRIVATE KEY' 문자열은 코드 상수, 시험 더미, 감사 메모뿐이다. || git show --diff-filter=D --name-only 3eef6a737 | grep -c '\.pem$' = 28. 루프 검사 'with private key: 28'. git ls-tree HEAD .pem 12개, git grep -l 'PRIVATE KEY' HEAD -- '*.pem' 0건. DECISIONS_NEEDED.md 119행 D40.

- 데이터그램 단위 도착 증거 학습(L1)이 Python과 Go 양쪽에 들어갔다 (improvement): **partly** sev= :: 코드는 확인했다. HEAD learn3.py 226행 normalize_arrivals, 249행 arrival_likelihood, 743행 사용, observation.go:196 arrivalEvidence, qamp.go:2569 연결, policy3_l1.go 존재. HEAD learn3.py는 L1 커밋 01c0de308과 diff가 비어 있다. 수치 하나가 틀렸다. 'B3·B4 사후 평균이 0.0002 이하'라고 했지만 B4는 0.0002122292다(B3 두 셀은 0.000129). B1·B2·B7 수치는 W1 자체가 아니라 반복 12 L1 평가(N 131072)의 값이다. || git show HEAD:padfec3/learn3.py 226, 249, 743, 748행. git diff 01c0de308 HEAD -- padfec3/learn3.py 출력 없음. runs/L1_precision_disposition.md 33행 'B3_u0, B3_u2, B4 ... 0.0001294771, 0.0001294694, 0.0002122292'. MORNING_REPORT.md:107.

- X 측정에 필요한 테스트베드 기능이 대부분 갖춰졌다 (improvement): **confirmed** sev= :: 인용한 Go 파일이 HEAD에 모두 있고 qamp_decoder_index_test.go의 Test 함수는 12개, TestObservationRecoveredHandshakeFeedback와 unrecoverable_final 필드도 있다. 다만 측정 러너 T7의 experiments/v33/devbed.py는 없어서 '대부분'이라는 한정이 맞다. Go 시험 통과 수는 다시 돌리지 않았다(Codex 문서값). || git cat-file -e HEAD:experiments/quicbed/{certificate,comparison,revisit,decoder_index,boundary,flight_shape}.go 모두 yes. grep -c '^func Test' qamp_decoder_index_test.go = 12. qamp_observation_test.go:123, qamp.go:1487. HEAD:experiments/v33/devbed.py 없음.

- 보존과 재현 가능성이 나아졌다 (improvement): **confirmed** sev= :: C:\dev\padfec_archive에 INDEX.json, MANIFEST.sha256, binaries, dev_data, gen2_build_origin이 있다. 378항목 해시, 45/45, 92/92는 Codex 문서값이며 다시 검증하지 않았다는 감사자 표기가 맞다. || ls /c/dev/padfec_archive: INDEX.json MANIFEST.sha256 binaries dev_data gen2_build_origin. LOOP_STATE tasks.S1/S3/A0/S2 note.

- 정책을 쓰지 않는 독립 세계 시뮬레이터와 회귀 벤치가 생겼다 (improvement): **confirmed** sev= :: experiments/v33/worldsim.py, bench.py, bench_oracles.py와 후보별 bench_learning_* 파일이 HEAD에 있다. 후보 7개를 같은 seed850001·N131072로 짝비교한 기록이 MORNING_REPORT에 남아 있다. || git ls-tree HEAD experiments/v33/: worldsim.py, bench.py, bench_oracles.py, bench_learning_l2.py ... MORNING_REPORT.md 117~137행 'N131072·seed850001'.

- 정직성 절차를 지켰다 (improvement): **confirmed** sev= :: 기각 뒤마다 'L1 복구' 커밋이 있고 HEAD learn3.py가 L1 커밋과 같다. decide3.py, layout.py는 기준선 대비 순변경이 없다. 사후 정밀화(H-11)와 기준 비대칭(H-05)도 Codex가 문서에 공개했다. || git log -- padfec3/learn3.py: 67aed72df L2, c81bbdf2d L3, e94961a4f J1, 91432c35c J6, 739e6d347 L5 모두 '활성 L1 복구'. git diff --stat 90859b973 HEAD -- padfec3/decide3.py padfec3/layout.py 출력 없음.

- 시험 위생이 나아졌다 (improvement): **confirmed** sev= :: pytest.ini, tools/lint_ast.py, doctor.py, drift_check.py, runtime_fingerprint.py, precommit_size.py가 HEAD에 있고 .github/workflows/ci.yml 초안이 있다. git remote가 없어 CI는 실행된 적이 없다. pytest 1792개는 다시 돌리지 않았다(Codex 문서값). || git ls-files tools: bootstrap_wsl.sh doctor.py drift_check.py lint_ast.py precommit_size.py raw_io.py runtime_fingerprint.py scrub_for_publish.py. git cat-file -e HEAD:pytest.ini yes. git remote -v 출력 없음.

- 추적 연결은 끊김 없이 유지됐다 (improvement): **refuted** sev= :: coverage_check.py가 '항목 194 누락 0'을 내는 것은 맞지만, 이 도구는 FINDINGS_INDEX의 처음 매핑이 과제 카드에 ID로 적혔는지만 본다. 그 매핑은 루프 전에 Claude가 만들고 맞춘 것이라 Codex 작업의 개선이 아니다. 루프 중의 추적은 오히려 끊겼다. 넘김 대상 E 카드 21쌍에 감사 ID가 없고(H-10), 넘김 대상이던 T4가 done이 될 때 넘겨받은 8개 넘김 항목을 기록하지 않았다(missed 1). || python -I -B tools/coverage_check.py: '항목 194 누락 0'. coverage_check.py main()은 index_rows와 TASKS.md cards만 대조. 볼트 2026-10-29 세션 로그 '기계 대조(tools/coverage_check.py ...)에서 171개 중 10개 누락'을 루프 전에 고침. ecards.py 'missing 21', donetgt.py T4 항목들.

- verdict_improved (verdict): **partly** sev= :: 결론 대부분은 확인된다. 처방 (1)~(6) 매핑(부분 1: L1만 done이고 L3 기각, 시도 후 기각 3: M1·J1/J3·O2, 미착수 2: L6·O1), 측정 X 전부 todo, 194항목 중 완전 반영 최대 60·교착 미처리 55, 비용 모형 decide3·layout 무변경은 모두 재현했다. 틀린 곳은 '알고리즘: 활성 코드에 들어간 변경은 L1 하나다'이다. Go 쪽 기본 동작도 바뀌었다. retrans-layout 기본값이 original_first(응답 전 후속 묶음에 T'=1 XOR 패리티 추가)로, 서버 udp-path 기본값이 oob로 바뀌었고, Codex 문서도 정책 비용 모형이 이 새 와이어를 반영하지 않는다고 적었다. 그래서 v33 바이너리는 L1 하나만 다른 것이 아니며, 이후 X6 같은 비교에서 효과가 섞인다. 또 완수도 원인에서 '정지 장치' 부분은 실행기가 쓰였다는 근거가 없다(H-07). || git show HEAD:experiments/quicbed/qamp.go 3715행 flag.String("retrans-layout", "original_first", ...), 3708행 flag.String("udp-path", "oob", ...). docs/T6_retrans_contract.md 3행 'retrans-layout=original_first가 새 v3 기본값', 9행 'layout.evaluate와 Go p3Evaluate는 ... 기존 실패 근사다 ... 원래 모형과 새 와이어가 완전히 같다고 쓰지 않는다'. DECISIONS_NEEDED.md D25, D28. LOOP_STATE: L6 todo, O1 todo, M1·J1·J3·O2 blocked.

### missed

- [medium] 넘김을 받은 과제가 done이 될 때 넘겨받은 항목을 확인하지 않는다(T4에서 8개 넘김 항목이 조용히 빠짐) :: 루프 규칙 2-3은 과제를 시작할 때 coverage_check.py --task <ID>로 감사 항목 목록을 뽑게 한다. 이 목록은 FINDINGS_INDEX의 처음 매핑만 보고, 다른 과제의 coverage 파일에서 넘겨받은 항목은 넣지 않는다. 그래서 J1, J6, L1, L3, L5가 'T4'를 넘김 대상으로 적은 항목들이 T4(반복 33 done)의 점검 목록에 없었고, T4_coverage.md에는 자기 매핑 6개만 있다. 넘김 상태로 남은 항목 중 A1-04, A4-03, A8-06, A2r1-11, A1-12, A2-11, A2r1-10, A2-17 8개가 여기에 해당하고, A2-02는 T5(done)에도 넘겨졌다가 같은 일을 겪었다. 넘김 대상 하나가 끝났는데 그 항목의 처리 기록이 없으므로 '다른 과제로 넘김'은 추적을 보장하지 못한다. 감사자의 '넘겨받은 과제 중 done 0개'도 이 때문에 틀렸다. || 스크래치 donetgt.py 출력: 'J6 A1-04 -> T4 done@ 33 target coverage mentions: False', 'L5 A2-11 -> T4 ...False', 'L1 A2r1-11 -> T4 ...False', 'L3 A2-02 -> T5 done@ 38 ...False' 등 16줄 중 14줄 False. python -I -B tools/coverage_check.py --task T4: 'T4 과제에 연결된 감사 항목 6개: A3-02, A3-15, A8-09, A6-M02, Q-15, Q-18'. runs/T4_coverage.md 표 6행뿐. LOOP_PROMPT.md 49행(2-3.1).

- [medium] v33 기본 바이너리의 와이어 동작이 L1 외에도 바뀌었고 비용 모형은 따라가지 않았다 :: T6(D28)이 v3 응답 전 후속 묶음의 기본 모양을 original_first(원본 먼저, 뒤 XOR 패리티 1개, 첫 행동이 전부 lead여도 T'=1)로 바꿨고, T5(D25)가 서버 UDP 경로 기본값을 oob로 바꿨다. 정책 비용 모형(layout.evaluate, Go p3Evaluate)은 이 새 재전송 보호를 반영하지 않으며, 이를 맞출 J3·J4 중 J3는 blocked, J4는 교착 상태다. 결과적으로 기본 v33 바이너리는 정책 모형과 실제 와이어가 어긋난 채로 남았고, 앞으로 X6(v3.3 대 v3.1 대 gen-2)을 돌리면 L1 효과와 재전송 모양·서버 경로 변경 효과가 섞인다. Codex는 문서에 공개했지만 기본값을 repeat_first로 되돌리거나 비교 계획에 분리 팔을 요구하지는 않았다. || git show HEAD:experiments/quicbed/qamp.go 3715행 '"retrans-layout", "original_first"', 3708행 '"udp-path", "oob"'. git show HEAD:docs/T6_retrans_contract.md 3, 9행. DECISIONS_NEEDED.md 61행 D25, 67행 D28 '정책 비용 변경은 J3·J4가 맡는다'. LOOP_STATE tasks.J3 blocked, J4 todo(J1 blocked 의존).

- [low] 루프가 run_loop.ps1 없이 돈 정황이 있어 실행기의 안전장치와 기록이 적용되지 않았을 수 있다 :: 실행기는 시작할 때 state/runner.log를 무조건 쓰고, 반복마다 runs/iterNNN_prompt.md, iterNNN.jsonl, iterNNN_stderr.txt를 만든다. 이 파일이 하나도 없고, iterNNN_last.json은 Codex의 finish 스크립트가 직접 썼다. 보호 경로 점검은 Codex의 preflight 스크립트가 반복마다 돌렸지만, 반복 시간 상한, 막힘·실패 연속 정지, 사용 한도 처리, 실행기 기록은 이번 루프에 없었을 가능성이 높다. 볼트 10-30 기록에는 프롬프트 파일을 바탕화면에 복사해 달라는 요청이 있다. 어떻게 실행했는지는 도현님에게 확인해야 한다. || run_loop.ps1 25~26, 76, 126~130행. ls runs: iter*_prompt.md 0개, iter*.jsonl 0개, iter*_stderr.txt 0개, state/runner.log 없음. runs/iter063_finish.py 69행 save(r / "iter063_last.json", last). runs/iter062_preflight.py가 guard_check.py --check 직접 실행. C:\dev\claude_brain\06 세션 로그\2026-10-29 PAD-FEC 마지막 종합 검토와 개선 방향.md 69행.
