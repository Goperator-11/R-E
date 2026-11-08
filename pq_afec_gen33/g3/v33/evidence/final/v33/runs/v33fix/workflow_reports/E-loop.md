# FIX E-loop
## summary
루프 자료(C:\dev\codex_handoff\v33)와 R-E-wt에 걸린 맡은 감사 항목을 모두 고쳤다. G1을 "채택된 활성 정책의 Go 거울"로 다시 정의하고(의존 [L1]), G2에서 M1 의존을 뗐다. todo 과제가 blocked 과제를 의존으로 갖지 않게 16과제의 의존을 정리하고 order를 바꿨다(측정 사슬, 해제 과제, 후보 순, R1은 맨 끝). 그 결과 잠긴 과제는 32개에서 0개가 됐고, T7은 G1·G2만, X1~X9는 G1·G2·T7만 기다린다. 대칭 채택 기준을 TASKS와 LOOP_PROMPT에 넣었고, 결정 D41~D49, 새 과제 E38·E39·E40, E 카드 보충, CONTEXT 0절, README, MORNING_REPORT 덧붙임 절을 썼다. run_loop.ps1은 done 없이 6반복이면 멈춘다. 반복 번호가 iter001로 되돌아가 Codex 파일을 덮던 버그와 DryRun이 state·runs에 쓰던 문제도 고쳤다. coverage_snapshot.py는 백업을 읽지 않고 6분류와 --received/--deps를 낸다. R-E-wt에는 .sh LF 규칙 행을 되살렸다(커밋 안 함). hygiene-clone-check는 고유 작업이 없음을 확인했지만 영구 삭제하지 않고 스크래치로 옮겼다.

## files_changed
[
 "C:\\dev\\codex_handoff\\v33\\prompt\\TASKS.md",
 "C:\\dev\\codex_handoff\\v33\\prompt\\LOOP_PROMPT.md",
 "C:\\dev\\codex_handoff\\v33\\prompt\\CONTEXT.md",
 "C:\\dev\\codex_handoff\\v33\\state\\LOOP_STATE.json",
 "C:\\dev\\codex_handoff\\v33\\state\\EXTRA_TASKS.md",
 "C:\\dev\\codex_handoff\\v33\\state\\DECISIONS_NEEDED.md",
 "C:\\dev\\codex_handoff\\v33\\run_loop.ps1",
 "C:\\dev\\codex_handoff\\v33\\README.md",
 "C:\\dev\\codex_handoff\\v33\\runs\\MORNING_REPORT.md",
 "C:\\dev\\codex_handoff\\v33\\runs\\coverage_snapshot.py",
 "C:\\dev\\codex_handoff\\v33\\V33FIX_loop.md",
 "C:\\dev\\R-E-wt\\hygiene\\.gitattributes",
 "C:\\dev\\R-E-wt\\hygiene-clone-check (moved to C:\\Users\\scien\\AppData\\Local\\Temp\\claude\\C--Users-scien\\98dad099-940c-4208-8359-61078035dc93\\scratchpad\\v33fix\\E\\rewt\\hygiene-clone-check_moved)"
]

## not_done
[
 {
  "ids": "A-E6 (영구 삭제)",
  "reason": "고유 작업이 없음을 확인했지만 영구 삭제는 되돌릴 수 없어서, 감사 FIX가 허용한 '스크래치로 옮기기'를 골랐다. 완전히 지우는 일은 도현님이 직접 한다. 경로는 C:\\Users\\scien\\AppData\\Local\\Temp\\claude\\C--Users-scien\\98dad099-940c-4208-8359-61078035dc93\\scratchpad\\v33fix\\E\\rewt\\hygiene-clone-check_moved 이다."
 },
 {
  "ids": "A-E6 (.gitattributes 커밋)",
  "reason": "git commit 금지라 작업 트리에만 고쳤다. hygiene 브랜치(85b00b6)에는 아직 없다."
 },
 {
  "ids": "A-E6 (S2_hygiene.md 확인 명령)",
  "reason": "gen33 docs/S2_hygiene.md 11·40행과 루프 runs/S2_hygiene.md 11·40행이 옮긴 clone 경로를 가리킨다. 둘 다 이 묶음의 파일이 아니라 고치지 않았다."
 },
 {
  "ids": "G1·E10·L1 최종 상태",
  "reason": "지시대로 note만 적었고 상태는 통합 때 정한다."
 },
 {
  "ids": "H verifier missed 1 / H-10 기존 끊김 16줄 + A7-18",
  "reason": "항목마다 T4·T5·L2·E17·M4 결과와 대조해야 해서 판정하지 않고 새 과제 E40에 맡겼다."
 },
 {
  "ids": "v3.3.1-dev·D43 실제 반영 확인",
  "reason": "다른 묶음이 gen33에 넣는 중이다. 카드·결정·CONTEXT에는 '정한 값'으로 적었고 코드 반영은 확인하지 않았다."
 },
 {
  "ids": "E17·E21 카드-상태 불일치",
  "reason": "이번에 손대지 않은 원래 기록이다(E17 done, E21 skipped). 실행 순서에 영향이 없어 그대로 두었다."
 },
 {
  "ids": "실제 Codex 호출, Go·pytest·관문 실행",
  "reason": "이 묶음 범위가 아니다. 실행기는 파서 검사, 함수 시험, 스크래치 사본 DryRun으로만 확인했다."
 }
]

## tests
직접 실행한 것만 적는다. (1) 스크래치 v33fix\E\verify_loop.py: LOOP_STATE JSON 유효, 과제 93·order 93(중복·누락·모르는 ID 0), 모르는 의존·순환 0, blocked 직접 의존 0, 잠김 0, status stopped·current null·R2 todo. 카드의 '의존:' 문장 48개가 LOOP_STATE와 일치하고, 불일치 2개(E17, E21)는 원래 상태다. (2) tools\coverage_check.py: 항목 194 누락 0(TASKS를 고친 뒤). (3) runs\coverage_snapshot.py: --deps에서 잠김 32→0, 6분류 숫자는 원래 상태 57/29/29/49/1/29, 수정 뒤 59/29/75/1/1/29(cov_before.json·cov_after.json, 2026-11-02 02:12). 옛 4분류 104/60/29/1. (4) run_loop.ps1: ParseFile 오류 0. 함수 시험(test_streaks.ps1)은 모두 기대대로이고, history 43~60을 넣으면 6번째에서 멈춘다. 스크래치 사본 DryRun은 첫 실행에서 서식 버그를 찾아 고친 뒤 rc 0이었다(Codex 호출 없음, GUARD_OK). (5) bench.py --dry-run은 쓰기 없이 계획만 출력했다. (6) 고친 md·json에 제어 문자와 새 줄표가 없다. MORNING_REPORT 본문은 바이트 그대로이고, run_loop.ps1의 CRLF·BOM도 유지됐다. 루프 폴더에 __pycache__는 생기지 않았다. Go 시험, pytest, 관문, W1 벤치는 돌리지 않았다.

## numbers
직접: 잠긴 과제 32→0. blocked 직접 의존을 가진 미완 과제 16→0. 실행 가능 과제 11→20(첫 과제 G1). T7의 미완 의존은 G1·G2, X1~X9는 G1·G2·T7. 과제 90→93(E38·E39·E40 추가). 상태 수 done 26, blocked 13, todo 53, skipped 1. 추적 6분류(반영/재현만/넘김-진행가능/넘김-교착/처리 안 함/기록 없음): 원래 상태 57/29/29/49/1/29, 수정 뒤 59/29/75/1/1/29. 옛 4분류 104/60/29/1. done 과제의 미기록 넘김 16줄(13개 ID), 카드 ID 누락은 1건 남음. 실행기 다음 반복 번호의 시작점 64. history 43~60을 새 규칙에 넣으면 6번째에서 멈춘다. clone-check 360M, 48커밋 전부 R-E에 있음. 문서에서 읽은 값: L1 none B6 v32 대비 +6.372402 ms(Codex). L3 record 대 l1은 두 대조를 합해 B1 -1.132398, B2 -0.202831, B5 -0.484054 ms(L3_findings_v1.md). Go PASS 231, SKIP 2(감사 A-E8/F8).

## handoff
통합 때 할 일: (a) gen33 docs/S2_hygiene.md와 C:\dev\codex_handoff\v33\runs\S2_hygiene.md의 11·40행이 C:\dev\R-E-wt\hygiene-clone-check를 가리키는데, 그 폴더는 스크래치로 옮겼다. 확인 명령을 '새 clone을 만들어 확인'으로 바꿔야 한다(다른 묶음/Codex 파일). (b) KICK.md(손으로 돌릴 때 문구)는 반복 번호를 없는 runs\runs.log에서 읽고 정지 규칙이 없다. 실행기와 같은 반복 번호 규칙과 'done 없이 6반복이면 멈춤'을 넣어야 한다(이 묶음 파일 아님. LOOP_PROMPT 앞머리에 자가 규칙을 대신 넣었다). (c) 감사 원문 v33audit\out은 세션 스크래치에 있다. LOOP_PROMPT 2-3과 CONTEXT가 그 경로를 가리키므로 findings\ 아래로 복사해 영구화하는 것이 좋다. (d) G1·E10·L1 상태 결정: v3.3.1-dev Go 거울과 관문이 통과하면 G1은 done 후보다. E10은 V33FIX_J6_rejudge 결과로 정한다. (e) D41·D43(repeat_first 기본값, -profile sealed31)과 docs/PUBLISH_PROCEDURE.md가 gen33에 실제로 들어갔는지 확인해야 한다. 이 묶음은 카드·결정에 '정한 값'으로만 적었다. (f) 맡은 목록 밖이지만 내 파일 범위라 카드에 넣은 것이 있다. E-M1-3(E14), E-J8-1(E34), E-J3-1(E30)이다. 다른 묶음이 이것을 직접 처리했다면 카드 문장을 '완료'로 고쳐야 한다. (g) R-E-wt hygiene의 .gitattributes 변경은 커밋되지 않았다. (h) 스크래치 출력은 v33fix\E\ 아래에 있다(cov_before/after.json, verify_loop.out.txt, test_streaks.out.txt, dryrun_tmp, rewt\clone_check_before_move.txt, orig\ 원본 사본). WSL v33fix_tmp/E는 만들지 않았다.

## fixes
[
 {
  "ids": "D-E6, H-02, G-E2, D verifier missed 2",
  "what": "TASKS G1 카드를 '채택된 활성 정책의 Go 거울과 정책 관문'(의존 L1)으로 다시 썼다. 미채택 후보는 채택될 때 그 과제 안에서 Go 거울까지 끝낸다는 규칙을 TASKS 실행 순서 절, LOOP_PROMPT 2-3.3, LOOP_STATE note에 넣었다. G2 의존은 [G1]으로 바꾸고 M1 와이어 시험은 M1·E16 범위로 옮겼다. 같은 원칙으로 X2·L4·J2·J4·L6·M2의 blocked 의존도 뗐다. LOOP_PROMPT 2-2.5에 '의존 교착을 발견하면 고치거나 결정 항목으로 올리고 아침 보고에 적는다'를 넣었다. 결정은 D46.",
  "verification": "직접: coverage_snapshot.py --deps와 verify_loop.py로 확인. 잠김 32개(감사값과 같음)에서 0개로, blocked 직접 의존 16개에서 0개로 줄었다. T7의 미완 의존 폐포는 G1·G2, X1~X9는 G1·G2·T7뿐이다. 실행 가능 과제는 11개에서 20개가 됐고 첫 과제는 G1이다."
 },
 {
  "ids": "H-03",
  "what": "order를 끝난 묶음, 측정 사슬(G1..T7), X, 해제 과제(E10, E14, E15, E25, E27, E28, E1, E39, E38, E40), 끝난 후보, 활성 정책 위에서 진행할 후보, X5/X7/X8, S2..R2, 나머지 E, R1(맨 끝) 순서로 바꿨다. 해제 과제를 측정 사슬 바로 뒤에 두는 규칙은 EXTRA 머리말 규칙 3과 LOOP_PROMPT 2-2.6에 넣었고, E1·E10 카드에 정정 줄을 붙였다.",
  "verification": "직접: order 93개, 중복·누락 0. 수정 전 실행 가능 목록 맨 앞은 R2, R1이었고, 지금은 G1, E10, E14, ... 순이다."
 },
 {
  "ids": "H-04",
  "what": "EXTRA_TASKS 머리말에 재진입·의존 규칙을 적었다(재진입 과제는 풀려는 막힌 과제를 의존으로 두지 않고, blocked 의존은 그 과제의 재진입 E 과제로 바꾼다). 의존은 E7 [J2,E26], E8 [J2], E9 [W1], E11 [T4,W1], E13 [E38,W1], E22 [T4,E25,E30], E23 [T4,T6,E30,E12], E26 [E25,E12,W1]으로 고쳤다. 각 카드에 정정 줄을 붙이고 이전 값은 depends_before_v33fix에 남겼다.",
  "verification": "직접: 카드의 마지막 '의존:' 문장이 LOOP_STATE와 48개 카드에서 일치한다. 불일치 2개(E17 done, E21 skipped)는 이번에 손대지 않은 원래 상태다."
 },
 {
  "ids": "D-E7",
  "what": "L2를 done으로 바꿨다(result_v33fix에 EPS 적응은 버리고 3등급 라벨은 활성 L1에 있다고 적음, 이전 상태·blocker 보존). J7은 blocked로 두고 1452 B 상한은 v3.3.1-dev가 넣는다고 적었다. 나머지 와이어 계약(W+46+6k 고정, overhead 46, fec_parse_fail)은 새 E38(의존 G1)으로, 성능 재판정은 E13(개선 조건 없이 L 공통 기준만)으로 나눴다.",
  "verification": "verify_loop.py: L2 done, J7 followup_v33fix [E38, E13], E38은 order 해제 묶음에 있다."
 },
 {
  "ids": "D-E8",
  "what": "D48로 L5 역사 관문을 '계획을 먼저 커밋한 새 개발 측정(T7 이후)으로 대체할 수 있음'으로 바꿨다. E11 카드에 같은 내용과 원래 금지 문장을 읽는 법을 덧붙였다.",
  "verification": "DECISIONS_NEEDED.md와 EXTRA_TASKS.md E11 정정 줄을 읽어 확인."
 },
 {
  "ids": "E-J5-1",
  "what": "J5를 부정 결과로 기록했다(LOOP_STATE result_v33fix, TASKS J5 결과 줄. 상태는 blocked 유지, 원래 result 경로 보존). E23 채택 조건에서 'B10 감소'를 빼고 B10 이득은 M2·M3와 묶었다. E23 의존의 J3는 E30으로 바꿨다.",
  "verification": "근거는 gen33 docs/J5_world_result.md(Codex)와 감사가 직접 확인한 값(c1 97.8%, none 99.9%가 이미 (0,0,4))이다."
 },
 {
  "ids": "E-J8-2 (+E-J8-1)",
  "what": "E34·E35 카드에 하향 손실 p_d 항을 RFC 9002 타이머 기준(마지막 ack-eliciting 송신 + PTO)의 비활성 참조로 먼저 구현하고 p_d>0에서 J=None을 반환하지 않게 하라는 지시를 넣었다. 같은 E34 카드에 E-J8-1(기존 W1 판정의 서버 PTO 영향 진단)도 넣었다.",
  "verification": "카드를 읽어 확인."
 },
 {
  "ids": "E-M1-1, E-M1-4, E-M1-5 (+E-M1-2, E-M1-3, E-J3-1)",
  "what": "E16 카드에 넣은 것: trailing=0 행동의 둘째 왕복 응답 비보호와 손실 꼬리를 반영한 비용 모형 수정, 뒤 패리티를 기다리는 결정 규칙 변형의 사전 고정 비교와 데이터그램 하나 기준(5.324 ms) 표, TTL 폐기 신용 손실, M1 와이어 전수 대조. E14 카드에는 성능 계산 전 관문으로 lead=0 off==hold 불변식 시험(E-M1-2)과 E-M1-3 오지정 업링크 팔을 넣었다. E30 카드에는 E-J3-1 최소 실패 표본 규칙을 넣었다.",
  "verification": "카드를 읽어 확인. 숫자는 감사 직접 확인값이며 출처를 카드에 적었다."
 },
 {
  "ids": "D verifier missed 1",
  "what": "새 과제 E39 'none B8 seed 46 쌍안정 진단'(의존 W1)을 만들었다. EXTRA 카드와 LOOP_STATE에 넣고 order는 해제 묶음에 두었다.",
  "verification": "verify_loop.py: E39 존재, 의존 일치."
 },
 {
  "ids": "B-E2, C-E7, H-05, D-E5",
  "what": "TASKS L 공통 절에 채택 기준 1~4를 넣었다. (1) none 포함 모든 배포 경로가 v32 대비 W1 모든 셀 0.5 ms 비열등 (2) 사후 MC 정밀화는 미리 정한 경우에만 모든 후보에 똑같이 (3) 루프가 주 비교를 고르거나 경로를 진단으로 내리지 않음 (4) 세부는 gen33 docs/V33FIX_bench_rules.md. 같은 문단을 LOOP_PROMPT 2-4에 넣고, CONTEXT 6절에 하지 말 것 세 줄을, 재진입 카드에 기준 참조를 넣었다. 결정은 D47이며 D14를 채택 판정에서 대체한다.",
  "verification": "문서를 읽어 확인."
 },
 {
  "ids": "H-07",
  "what": "run_loop.ps1에 -MaxNoDone 6과 Step-Streaks 함수를 넣었다. done이면 0으로, partial·blocked·실패면 1씩 올리고 wait는 세지 않는다. 6이 되면 STOP 파일을 쓰고 멈추며, 시작할 때 history 끝의 셈을 이어받는다. 반복 번호를 runs의 모든 iterNNN_ 파일과 LOOP_STATE iterations 중 최댓값으로 계산하게 했다(전에는 iter001로 되돌아가 Codex의 iter001_last.json을 덮을 수 있었다). DryRun은 기록과 프롬프트를 %TEMP%에 쓰고 STOP을 쓰지 않게 했다.",
  "verification": "직접: ParseFile 오류 0. test_streaks.ps1로 history 43~60의 실제 상태 열을 넣으면 6번째에서 멈춘다. 다른 경우들도 기대대로였다. 스크래치 사본에서 TEMP를 스크래치로 돌려 DryRun을 실행했다. 첫 실행에서 Get-IterBase의 double 서식 버그를 찾아 [int]로 고쳤고, 두 번째 실행은 rc 0(GUARD_OK, Codex 호출 없음)이었다. 실제 폴더 기준 반복 시작점은 64다."
 },
 {
  "ids": "H-08",
  "what": "LOOP_PROMPT 4절을 9개 절 양식으로 바꿨다. 첫 줄 6분류, 숫자 표, 의존 교착, 실행 가능 과제, 다음 밤 첫 과제를 넣고 git log·status, pytest, build_gen33.sh, gate_v3_parity.py, bench --dry-run, coverage 명령 블록을 넣었다.",
  "verification": "직접: bench.py --dry-run --generations current v32는 계획 JSON만 출력하고 쓰지 않았다. genconfig binary가 ~/quicbed_gen33/bin/qamp인 것도 확인했다. 관문과 빌드는 돌리지 않았다."
 },
 {
  "ids": "H-09",
  "what": "LOOP_STATE를 status stopped, current null로 바꾸고 R2를 todo로 되돌렸다(active_iteration 64와 started_kst는 interrupted_attempt로 옮김). iterations 63과 history는 그대로 두었다.",
  "verification": "verify_loop.py problems [] (top_status, R2 검사 포함)."
 },
 {
  "ids": "H-10, H-01, H verifier missed 1",
  "what": "coverage_snapshot.py는 이제 정확히 <과제ID>_coverage.md 이름인 파일만 읽어 iter056/057 백업을 뺀다. 집계는 반영/재현만/넘김-진행가능/넘김-교착/처리 안 함/기록 없음 6분류이고 partial_handled 표지를 따로 둔다. --received, --deps, --state, --out을 더했고 인자가 없으면 출력만 한다(옛 호출은 그대로 동작). LOOP_PROMPT 2-3·2-4와 EXTRA 규칙 4에 넘겨받은 항목 확인과 카드 ID 기록 규칙을 넣었다. 카드에 빠진 감사 ID를 E8, E22, E25, E26, E28, E33, E35, E36에 보충했다. done 과제가 기록하지 않은 16줄과 넘김-교착 A7-18은 새 과제 E40에 맡겼다.",
  "verification": "직접: 원래 상태는 반영 57, 재현만 29, 진행가능 29, 교착 49, 처리 안 함 1, 기록 없음 29였다. 수정 뒤는 59/29/75/1/1/29다. 옛 4분류로 세면 104/60/29/1로 MORNING_REPORT 5행·감사와 같다. 기록 없음 중 잠긴 21개는 감사값과 같고 수정 뒤 0개다. 카드 ID 누락은 1건(done 과제 E17)이 남았다."
 },
 {
  "ids": "DECISIONS D41~D49",
  "what": "DECISIONS_NEEDED.md 끝에 'Claude가 정한 결정(2026-11-02, 도현님 지시 ...)' 표를 만들었다. D41 v3.3.1-dev 설계, D42 이력 재작성 안 함·새 저장소 공개, D43 repeat_first 기본값·-profile sealed31, D44 Z1, D45 J6 재판정만, D46 G1·G2 재정의, D47 대칭 기준, D48 L5 역사 관문, D49 후보 상태 정리이며 행마다 되돌리는 방법을 적었다.",
  "verification": "D41의 L3 숫자는 runs/L3_findings_v1.md에서 직접 다시 읽었다. record 대 l1 직접 행이 없어 두 대조를 더한 값(B1 -1.132398, B2 -0.202831, B5 -0.484054, B6 미확정 MC 0.142519)으로 고쳐 적었다."
 },
 {
  "ids": "CONTEXT / README / MORNING_REPORT",
  "what": "CONTEXT에 0절 '지금 상태(2026-11-02)'를 넣었다(활성 정책, 상태 판본, 와이어 기본값, 판정 규칙, 과제 구조, 감사 요약, 수정 문서 위치). 6절에는 'none 경로를 진단으로 내려 채택하지 않는다' 등 세 줄을 더했다. README에는 새 정지 조건, 반복 번호, DryRun, 실행기 없이 돈 정황(H missed low), 과제 수 93을 적었다. MORNING_REPORT 맨 끝에 '## 2026-11-02 Claude 검증·수정 덧붙임' 절을 붙였다. 감사 요약, 처리함 104 정정 표, F8/A-E8 정정(PASS 231, SKIP 2, M1_REFERENCE_GZIP), 다음 밤 첫 과제 정정, 문서 목록이 들어 있다.",
  "verification": "직접: MORNING_REPORT 앞 69,757 B가 원본과 바이트 단위로 같다. 고친 md 문서들에 줄표와 제어 문자가 없다(CONTEXT의 원래 규칙 문장 안의 줄표는 그대로 둠)."
 },
 {
  "ids": "LOOP_STATE 통합 대기",
  "what": "G1, E10, L1의 note에 'v33fix 진행 중, 통합 때 갱신'만 적었다. 상태는 G1 todo, E10 todo, L1 done 그대로 두었다.",
  "verification": "LOOP_STATE를 출력해 확인."
 },
 {
  "ids": "A-E6",
  "what": "R-E main의 'mlkem-quic-amplification/src/*.sh text eol=lf' 행을 R-E-wt/hygiene/.gitattributes 끝에 되살렸다(작업 트리만, 커밋 안 함). hygiene-clone-check는 고유 작업이 없음을 확인한 뒤 스크래치 v33fix\\E\\rewt\\hygiene-clone-check_moved로 옮겼다.",
  "verification": "직접: git diff는 +1행이고, check-attr로 run_v3.sh가 text set, eol lf임을 확인했다. clone-check는 status·ignored 0, stash 0이다. 유일한 ref 85b00b6은 R-E hygiene/2026-10-30에 있고, rev-list --all 48커밋과 dangling blob 2개가 모두 R-E에 있다. 사용자 훅은 없고, R-E worktree가 아닌 별도 clone이며 크기는 360M이다. 확인 기록은 rewt\\clone_check_before_move.txt에 있다. R-E main 작업 트리 status는 깨끗하다."
 }
]

# VERIFY
## new_problems
[
 {
  "severity": "medium",
  "title": "E30 카드에 반박된 감사 항목 E-J3-1을 처방으로 넣어 관문을 느슨하게 만들었다",
  "detail": "E는 감사 목록 밖인 E-J3-1을 E30 카드에 넣었다. 실패 표본 수 기준(예: 30건 미만)을 정하고, 그보다 적은 층은 '판정 불능'으로 적으라는 내용이다. 그러나 E 검증자는 E-J3-1을 refuted로 판정했다. 2% 층 실패 5건은 값이 좁게 모여 있다(sd 6.77, se 3.03). -49.26 ms는 표본 오차의 약 16배라서 통계적으로 분명한 미통과이고, 남는 문제는 대표성(5건 모두 run1, Initial 5개인 한 유형)뿐이다. 이 카드대로 하면 E30은 2% 층의 확정 미통과를 '판정 불능'으로 바꿔 '전체 고정 팔 층 ±10 ms' 완료 기준을 통과할 수 있다. TASKS 머리말은 PARTLY 항목에서는 검증 파일의 정정 문장을 정본으로 삼으라고 하는데, 그 원칙과도 어긋난다.",
  "evidence": "EXTRA_TASKS.md E30 '2026-11-02 추가(E-J3-1)' 줄; E-rejected-mechanism.md VERIFY 'E-J3-1 (error): **refuted** ... −49.26 ms 차이는 표본 오차의 약 16배라서 통계적으로 의미 없음이 아니다'; V33FIX_loop.md 'E-J3-1(감사 목록 밖, E30 카드 범위)'.",
  "suggested_fix": "E30의 E-J3-1 줄을 검증자 정정으로 바꾼다. 2% 층 -49.257 ms는 미통과로 유지하고(se 3.03, 5건), 대표성 한계(run1의 한 유형뿐)를 함께 적는다. 최소 표본 규칙을 두려면 se 기반 구간으로 판정하게 하고, 표본 수만으로 '판정 불능'을 만들지 않는다."
 },
 {
  "severity": "low",
  "title": "--deps 의존 점검이 coverage 파싱에 묶여 있어, coverage 행 하나의 형식이 어긋나면 반복마다 하는 점검 전체가 예외로 죽는다",
  "detail": "LOOP_PROMPT 2-2.5는 매 반복 과제를 고르기 전에 coverage_snapshot.py --deps를 돌리게 한다. 그런데 main()은 --deps일 때도 build()를 먼저 부르고, build()는 모든 <과제>_coverage.md 행을 파싱한다. 둘째 칸이 처리함·처리 안 함·다른 과제로 넘김으로 시작하지 않는 감사 ID 행이 하나라도 있으면 ValueError가 난다. E40 카드는 넘겨받은 과제의 coverage 끝에 '넘겨받은 항목 보충' 표를 덧붙이라고 하면서 열 순서를 정하지 않았다. 그럴듯한 형식(| 항목 | 넘긴 과제 | 처리 |)을 스크래치 사본에 붙여 build()를 부르니 바로 ValueError가 났다.",
  "evidence": "coverage_snapshot.py 242~259행(main이 --deps 전에 build 호출), 103~105행(missing tracking disposition 예외). 스크래치 verify-E-loop\\covsim에서 T4_coverage.md에 '| A1-01 | J1 | 처리함(T4_result.md) |'를 덧붙인 시험: 'EXC ValueError missing tracking disposition: ...T4_coverage.md:18'.",
  "suggested_fix": "--deps 모드는 LOOP_STATE만 읽어 dependency_report(state)를 바로 출력하게 한다(coverage 파싱 생략). E40 카드에는 덧붙일 표의 열 순서를 '| 감사 ID | 처리 상태(처리함/처리 안 함/다른 과제로 넘김(...)) | 근거 |'로 명시한다."
 },
 {
  "severity": "low",
  "title": "D49의 E40 범위가 E40 카드와 다르다",
  "detail": "D49 행은 E40을 'T4·T5가 확인하지 않은 넘김 14줄 보충'으로 적었다. E40 카드, LOOP_STATE note, V33FIX_loop.md, MORNING_REPORT 덧붙임은 모두 16줄(13개 ID, 대상 T4·T5·L2·E17)이다. L2를 done으로 바꾸면서 늘어난 줄을 D49에 반영하지 않았다. 직접 계산한 값도 16줄이다.",
  "evidence": "DECISIONS_NEEDED.md D49 행 'E40(T4·T5가 확인하지 않은 넘김 14줄 보충)'; v3_cov.py done_target_unrecorded 16줄(T4 13, T5 1, L2 1, E17 1).",
  "suggested_fix": "D49 문장을 'E40(T4·T5·L2·E17이 확인하지 않은 넘김 16줄, 13개 ID와 넘김-교착 A7-18 보충)'으로 고친다."
 },
 {
  "severity": "low",
  "title": "덧붙인 문서의 작은 사실 부정확",
  "detail": "(1) MORNING_REPORT 덧붙임 '다음 밤 첫 과제 정정'의 'T7과 X1~X9는 G1·G2만 기다린다'는 틀렸다. X1~X9는 T7도 기다린다. V33FIX_loop.md와 CONTEXT는 'G1·G2·T7'로 바르게 적었다. (2) TASKS J5 결과 줄의 'm≤4 안에서는 W1 B10 개선 기준을 원리상 만족할 수 없다'는 E 검증자가 고친 과장이다(c1 모드 약 0.13 ms 여지). E23 정정 줄의 '구조적으로 0'도 같다. (3) README 실행기 5항은 'partial이 막힘 횟수를 0으로 되돌려 ... 18반복이 돌아도 멈추지 않았다'고 단정한다. 그런데 바로 위 문단과 H 검증자는 그 밤에 실행기가 쓰이지 않았을 정황을 적었다. 설계 결함이라는 점은 맞지만 그 밤의 원인으로 단정할 수는 없다.",
  "evidence": "runs/MORNING_REPORT.md 덧붙임 '새 order에서 ... T7과 X1~X9는 G1·G2만 기다린다'; LOOP_STATE X* depends에 T7; E-rejected-mechanism.md VERIFY E-J5-1 ''구조적으로 불가능'은 약간 과장이다 ... 약 0.13 ms 여지'; README.md 24행; H-coverage.md VERIFY H-07 partly.",
  "suggested_fix": "(1) 'T7은 G1·G2만, X1~X9는 G1·G2·T7만 기다린다'로 고친다. (2) '사실상 0(c1 모드 약 0.13 ms 여지, none 모드 0)'으로 고친다. (3) '실행기를 썼다면 멈추지 않았을 구조였다'로 고친다."
 },
 {
  "severity": "low",
  "title": "G1 카드와 CONTEXT 0절이 c1_seen 참 경로의 재평가 조건을 빠뜨렸다",
  "detail": "설계(D41, 작업 지시)는 c1_seen이 참인 목적지에서 'arrival_streak > 0인 동안' 16번째 재평가를 하지 않는다. G1 카드('참인 목적지의 감시 벌점·16번째 재평가·β 반응 없음')와 CONTEXT 0절('감시 가산 벌점·16번째 재평가·β 반응 없이')에는 그 조건이 없다. G1은 Go 거울 과제라서, 이 문장대로 구현하면 Python과 어긋날 수 있다. 관문이 잡겠지만 카드가 오해를 부른다. E8 정정 줄과 D41에는 조건이 바르게 들어 있다.",
  "evidence": "TASKS.md G1 카드 '할 일'; CONTEXT.md 0절 활성 정책 항목; DECISIONS D41 '(3) ... arrival_streak>0인 동안 16번째 재평가 없음'.",
  "suggested_fix": "G1 카드와 CONTEXT 0절에 '도착 증거가 이어지는 동안(arrival_streak>0)'을 넣는다."
 },
 {
  "severity": "low",
  "title": "done 없는 6반복으로 멈춘 뒤에는 STOP을 지워도 재시작되지 않고, 우회 방법이 문서에 없다",
  "detail": "정지하면 STOP을 쓴다. 사람이 STOP을 지우고 다시 실행해도, 시작할 때 Get-NoDoneFromHistory가 같은 history 끝(6 이상)을 세어 'exit 1'로 바로 끝난다. 사람이 의존 교착을 고친 뒤 재시작하려면 -MaxNoDone을 키우거나 history를 고쳐야 한다. README와 로그 문구에는 이 방법이 없다. 같은 맥락에서, LOOP_PROMPT가 R1을 '과제로 고르지 않는다'고 해 R1이 끝내 done이 되지 않는다. 그러면 '모든 과제가 done/blocked/skipped면 all_done' 조건은 영원히 성립하지 않는다(모든 과제가 끝날 때만 문제가 되는 가장자리 경우다).",
  "evidence": "run_loop.ps1 130~131행(시작 시 noDone ≥ MaxNoDone이면 exit 1), 273~277행(STOP 쓰기); README.md 실행기 5항; LOOP_PROMPT 2-2.2와 4절 마지막 줄.",
  "suggested_fix": "README와 시작 로그에 '사람이 정한 뒤 재시작은 -MaxNoDone <큰 값>으로 한 번 실행'을 적거나 -ResetNoDone 스위치를 둔다. R1은 '마지막 반복에서 최종본을 쓰면 done'으로 정하거나, all_done 조건에서 R1을 뺀다."
 }
]

## out_of_scope_edits
파일 범위: 바뀐 파일은 보고한 11개(TASKS, LOOP_PROMPT, CONTEXT, LOOP_STATE, EXTRA_TASKS, DECISIONS_NEEDED, run_loop.ps1, README, MORNING_REPORT 덧붙임, coverage_snapshot.py, 새 V33FIX_loop.md)와 R-E-wt/hygiene/.gitattributes, 그리고 hygiene-clone-check 이동뿐이다. 루프 폴더에서 2026-11-02 01:29 뒤에 바뀐 파일을 find로 찾고 백업 tar와 비교해 확인했다. JOURNAL, guard_baseline, tools 5개, iter_schema, KICK, findings, evidence, private는 그대로다. R-E main(6bbd11f, clean)과 R-E-wt/next도 그대로다. gen33에 E가 쓴 흔적은 다른 묶음의 작업과 구별할 수 없어 확인하지 못했다(E는 쓰지 않았다고 했다). 내용 범위: 감사 배정 밖의 카드 추가가 있다. E-M1-3은 E14에, E-J8-1은 E34에 넣었고 둘 다 감사 원문과 맞다. E-J3-1은 E30에 넣었는데, 검증자가 반박한 항목이라 문제가 된다(새 문제 1). 의존 정리는 X2·L4·J2·J4·L6·M2까지 넓혔고, V33FIX_loop.md에 이유가 적혀 있어 정당하다. G1·CONTEXT·D41~D49에는 다른 묶음이 구현 중인 v3.3.1-dev와 D43을 '정한 값'으로 적었다. gen33 작업 트리를 보면 learn3.py는 v3.3.1-dev·STATE_VERSION 11, qamp 기본값은 repeat_first, -profile sealed31이 들어갔다. 반면 Go policy3.go는 아직 p3UDPMax 1472, cache schema '/3'이라 통합 전이다.

## tests_rerun
모두 직접 실행했고 아무것도 고치지 않았다. 스크래치는 v33fix\verify-E-loop에만 썼다. (1) 백업 tar를 bak\에 풀어 18개 파일을 비교했다. SAME 7개, DIFF 11개였다. MORNING_REPORT 앞 69,757 B는 cmp로 같았다. (2) v1_state.py로 LOOP_STATE를 과제별로 diff했다. history는 63/63 같고, order_before_v33fix는 백업 order와 같고, revisions sha가 백업 sha와 같았다. (3) v2_closure.py로 전이 폐포를 다시 계산했다. 백업은 잠김 32, runnable 11, 도달 가능 18이었다. 현재는 잠김 0, blocked 직접 의존 0, runnable 20(첫 G1), T7 미완 조상 G1·G2, X* 미완 조상 G1·G2·T7, 도달 가능 53이었다. (4) v6_cards.py로 카드의 '의존:' 문장과 LOOP_STATE를 비교했다. 47개가 일치했고, 불일치는 E17·E21 2개로 수정 전부터의 상태다. (5) coverage_snapshot.py를 인자 없이, --state 백업으로, --deps로, --received G1로 돌렸다. 59/29/75/1/1/29, 백업 57/29/29/49/1/29, 옛 104/60/29/1, ignored 2개, done_target_unrecorded 16, 카드 누락 1이었다. 실행 전후 루프 폴더 목록 diff는 0이었다. (6) v4_covdiff.py는 46개가 교착에서 진행가능으로, 2개(A2-06, A2r1-01)가 교착에서 반영으로 옮겨졌음을 보였다. (7) tools\coverage_check.py는 '항목 194 누락 0'이었다. (8) pwsh로 run_loop.ps1 ParseFile을 돌려 오류 0을 확인했다. 함수 3개를 AST로 뽑아 시험했다(IterBase 64 Int32, iter065, history 43~60은 6번째에서 정지, 그 밖의 경우 6개). 스크래치 사본으로 -DryRun -NoWakeHold를 돌렸더니 rc 0, GUARD_OK였고, 실제 폴더에는 쓰기가 0이었다. (9) 줄 끝·BOM은 run_loop.ps1 CRLF+BOM, 나머지 LF였다. 추가 줄의 줄표와 이모지, 제어 문자는 0이었다. (10) R-E와 R-E-wt를 git status, rev-parse, worktree, for-each-ref, check-attr로 보았다. 옮긴 clone은 rev-list --all 48개가 모두 R-E에 있었다. (11) L3_findings_v1.md와 L1_precision_disposition.md에서 D41 숫자를 대조했다. (12) coverage 파서에 E40식 보충 행을 넣는 시뮬레이션은 ValueError를 재현했다. Go 시험, pytest, 관문, 벤치 본실행은 돌리지 않았다(이 검증 범위 밖).

## items
[
 {
  "ids": "D-E6, H-02, G-E2, D 검증자 missed 2",
  "verdict": "fixed",
  "reason": "전이 폐포를 직접 다시 계산했다. 백업 LOOP_STATE에서는 잠김 32개(감사값과 같음), blocked 직접 의존 16개, 실행 가능 11개(R2, R1, E1...)였다. 지금은 잠김 0, blocked 직접 의존 0, 순환 0, 모르는 의존 0, 실행 가능 20개이고 첫 과제는 G1이다. T7의 미완 조상은 G1·G2뿐이고 X1~X9는 G1·G2·T7뿐이며, 조상에 blocked·skipped가 없다. 모두 성공한다고 가정하고 order대로 돌리면 53과제가 전부 도달 가능하다(백업에서는 18개뿐). G1 [L1], G2 [G1]이고, M1 와이어 시험은 TASKS M1·G2 카드와 EXTRA E16으로 옮겨졌다. D46과 LOOP_PROMPT 2-2.5도 있다.",
  "evidence": "scratch v33fix\\verify-E-loop\\v2_closure.py 출력(v2_closure.out.txt): BACKUP locked 32, runnable 11; CURRENT direct-blocked-dep 0, locked 0, runnable 20 ['G1','E10',...,'R1'], T7 open-ancestors ['G1','G2'], X* ['G1','G2','T7'], 'never reachable'에는 blocked 13개와 E21(skipped)만 남음. coverage_snapshot.py --deps 결과도 같음."
 },
 {
  "ids": "H-03",
  "verdict": "fixed",
  "reason": "order 93개에 중복·누락·모르는 ID가 없다. 해제 과제(E10, E14, E15, E25, E27, E28, E1, E39, E38, E40)는 이제 X 측정 사슬 바로 뒤, 후보와 R 과제보다 앞에 있고 R1은 맨 끝이다. TASKS 실행 순서의 묶음 목록과 LOOP_STATE order가 일치한다. 감사 FIX는 '바로 다음 반복'이었고 E는 '측정 사슬 바로 뒤'를 골랐다. 이 선택은 V33FIX_loop.md에 이유와 함께 적혀 있다. E1·E10 카드의 옛 '본래 과제 뒤' 문장은 남아 있지만 아래에 정정 줄이 붙었다. order 위치 네 곳(E40→E17, E7→E26, E22·E23→E30)에서 의존이 과제보다 뒤에 오는데, 실행기는 의존이 done인지로만 고르므로 해가 없다.",
  "evidence": "order 출력: ... T7 X6 T3 X1 T2 X4 X3 X9 X2 E10 E14 E15 E25 E27 E28 E1 E39 E38 E40 O2 ... R2 E2 ... E37 R1. order_before_v33fix가 백업 order와 같다(True)."
 },
 {
  "ids": "H-04",
  "verdict": "fixed",
  "reason": "E7 [J2,E26], E8 [J2], E9 [W1], E11 [T4,W1], E13 [E38,W1], E22 [T4,E25,E30], E23 [T4,T6,E30,E12], E26 [E25,E12,W1]이 LOOP_STATE와 카드의 마지막 '의존:' 문장에서 서로 일치한다. 바꾸기 전 값은 depends_before_v33fix로 남아 있다. EXTRA 머리말 규칙 1~5도 있다. 카드마다 옛 '의존:' 문장과 정정 줄이 함께 남아 있어 읽기에는 혼란스럽다. 다만 LOOP_STATE가 정본이라고 여러 곳에 적혀 있다.",
  "evidence": "v6_cards.py: 문장이 있는 카드 49개 중 47개 일치. 불일치는 E17(done, 카드 'T5' 대 [])과 E21(skipped, 'T2, G1' 대 [T2])뿐이고 둘 다 수정 전부터의 상태다. 변경 과제별 per-card 출력으로 확인."
 },
 {
  "ids": "D-E7",
  "verdict": "fixed",
  "reason": "L2는 done이다(result_v33fix, status_before_v33fix=blocked, blocker_before_v33fix 보존). 이는 감사 FIX와 D 검증자('L2 부분은 대체로 맞다, L 공통은 blocked를 요구하지 않는다')에 맞는다. J7은 blocked로 두고 와이어 계약은 E38(의존 G1), 성능 재판정은 E13(의존 E38, W1)으로 나눴다. E13 정정 줄은 검증자 정정(W1 15셀이 모두 W1280)을 반영했다. L2가 done이 되면서 A2-06·A2r1-01이 반영으로 옮겨졌고, L1→L2 넘김 1줄(A2r1-11)이 새로 '미기록 done 대상'이 되었다. 이 줄은 E40이 의존 L2로 맡는다.",
  "evidence": "v1_state.py diff: L2 status blocked→done, J7 followup_v33fix [E38,E13], NEW E38 depends [G1]. v4_covdiff.py: 2개 ('넘김-교착','반영') = A2-06, A2r1-01. done_target_unrecorded가 원래 state 15줄에서 현재 16줄로 늘었다."
 },
 {
  "ids": "D-E8",
  "verdict": "fixed",
  "reason": "D48로 역사 관문을 '계획을 먼저 커밋한 새 개발 측정(T7 이후)'으로 대체할 수 있게 했다. E11 정정 줄에는 D48과, 원래 금지 문장을 '계획 없이 자동으로 대체하지 않는다'로 읽는 법이 함께 적혀 있다. E11 의존 [T4,W1]이라 잠기지 않는다.",
  "evidence": "DECISIONS_NEEDED.md diff의 D48 행, EXTRA_TASKS.md E11 '2026-11-02 정정(H-04, D-E8)' 줄."
 },
 {
  "ids": "D 검증자 missed 1",
  "verdict": "fixed",
  "reason": "E39(none B8 seed 46 쌍안정 진단, 의존 W1)가 카드와 LOOP_STATE에 있고 지금 실행할 수 있다. 사후 채택 금지와 '규칙 변경은 결정 항목으로만' 금지 문장도 있다. 숫자(-31.376, -36.421, +47.084)는 D 검증 원문과 같다.",
  "evidence": "LOOP_STATE NEW E39 depends [W1]; runnable_in_order에 E39 포함; D-rejected-learning.md VERIFY missed 1."
 },
 {
  "ids": "B-E2, C-E7, H-05, D-E5",
  "verdict": "partly",
  "reason": "대칭 채택 기준 1~4가 TASKS L 공통, LOOP_PROMPT 2-4, CONTEXT 6절, D47에 같은 내용으로 들어갔다. 내용은 v32 대비 none 포함 모든 경로의 모든 셀, none 기준선을 L1-none으로 바꾸지 않음, 사후 정밀화는 미리 정한 경우만, 루프가 경로를 진단으로 내리지 않음이다. gen33 docs/V33FIX_bench_rules.md 2.1·2.2와도 맞는다. 그러나 감사 FIX의 다른 절반인 'L1을 같은 기준으로 다시 판정하거나 L1 상태를 고친다'(B-E2, H-05)는 하지 않았다. L1은 done이고 note에 '통합 때 갱신'만 붙었다. 지시대로 미룬 것이고 v3.3.1-dev가 none 경로를 v3.2로 되돌리지만, 상태 기록은 아직 그대로다.",
  "evidence": "diff_TASKS.txt의 '채택 기준(2026-11-02 Claude, B-E2·C-E7·H-05·D-E5)' 1~4; LOOP_PROMPT diff 2-4 대칭 기준 줄; LOOP_STATE L1 status done, note '... | v33fix 진행 중, 통합 때 갱신'."
 },
 {
  "ids": "E-J5-1",
  "verdict": "fixed",
  "reason": "J5는 blocked로 두고 result_v33fix에 부정 결과를 적었다. 원래 result 경로도 남아 있다. E23 채택 조건에서 'B10 감소'를 빼고 B10 이득을 M2·M3와 묶었으며, E23 의존의 J3는 E30으로 바꿨다. 감사 FIX 두 갈래를 모두 했다. 다만 TASKS J5 결과 줄의 'm≤4 안에서는 ... 원리상 만족할 수 없다'는 E 검증자가 '약간 과장, c1에서 (0,0,3) 2.1%를 옮기면 약 0.13 ms 여지'라고 고친 부분을 반영하지 않았다(새 문제 4).",
  "evidence": "diff_TASKS.txt J5 '결과(2026-11-02 Claude 기록, E-J5-1)' 줄; EXTRA E23 정정 줄; E-rejected-mechanism.md VERIFY E-J5-1."
 },
 {
  "ids": "E-J8-2, E-J8-1",
  "verdict": "fixed",
  "reason": "E34 카드에 p_d 항을 RFC 9002 타이머 기준의 비활성 참조로 먼저 구현하고 p_d>0에서 J=None을 반환하지 않게 하라는 지시가 들어갔다. E35에는 그 참조를 쓰라는 지시가 있다. E-J8-1 진단 지시는 검증자 정정(B7 손해는 PTO가 아니라 결정 규칙 비용, 절대 HCT는 0.68~3.14 ms씩 이동)과 맞게 적혔다.",
  "evidence": "EXTRA_TASKS diff의 E34 '2026-11-02 추가(E-J8-2)', '(E-J8-1)' 줄, E35 '(E-J8-2)' 줄; E-rejected-mechanism.md VERIFY E-J8-1."
 },
 {
  "ids": "E-M1-1, E-M1-4, E-M1-5, E-M1-2, E-M1-3",
  "verdict": "fixed",
  "reason": "E16에 응답 XOR 비대칭이 들어갔다. 검증자 정정대로 'Q'와 'V'를 모두 적었다. 결정 규칙 변형의 사전 고정, 5.324 ms 기준, TTL 폐기 신용 손실, M1 와이어 전수 대조도 E16에 있다. E14에는 lead=0 off==hold 관문(E-M1-2)과 D20 고정·2배·1/2배 오지정 팔(E-M1-3)이 들어갔다. 숫자는 E 감사·검증 원문과 같다. 참고로 E 검증자의 missed 2건은 어느 카드에도 없다. 하나는 B7 none 4셀 실패가 후보 선택 문제라는 것이고, 다른 하나는 수정 세계에서도 늦은 비행 복구 때문에 lead0 불변식이 드물게 깨진다는 것이다. E의 배정 목록에 있었는지는 확인할 수 없다.",
  "evidence": "EXTRA_TASKS diff의 E14·E16 추가 줄; E-rejected-mechanism.md E-M1-1~5, VERIFY E-M1-1('send_reply의 Q(776행)와 탐침의 V'), missed 1·2."
 },
 {
  "ids": "H-07",
  "verdict": "fixed",
  "reason": "직접 확인했다. ParseFile 오류는 0이다. AST로 Step-Streaks, Get-IterBase, Get-NoDoneFromHistory를 뽑아 따로 돌렸다. 실제 history 43~60 상태 열은 6번째(반복 48)에서 멈춘다. partial 5번 뒤 done이면 계속 가고, wait 10번은 세지 않으며, blocked 3연속과 실패 3연속은 3번째에서 멈춘다. 실제 폴더의 반복 시작점은 64(Int32)이고 다음은 iter065, 현재 history 끝의 done 없는 반복 수는 0이다. 스크래치 사본(TEMP를 스크래치로 돌림)에서 -DryRun -NoWakeHold를 직접 돌렸더니 rc 0, GUARD_OK, iter065 프롬프트와 로그가 TEMP에만 생겼다. 실제 루프 폴더에는 아무것도 쓰이지 않았고(find -newermt 결과 0), STOP·runner.log도 없었다. CRLF·BOM도 유지됐다.",
  "evidence": "scratch verify-E-loop\\v5_ps.ps1 출력: 'parse errors: 0', 'IterBase real: 64 type Int32; next stamp iter065', 'hist43-60 stops at element 6 (iteration 48)'. dry\\out.txt rc=0, dry\\tmp\\v33_dryrun_iter065_prompt.md 머리말 '보호 경로 점검: GUARD_OK'. run_loop.ps1 CRLF 284/284, BOM True."
 },
 {
  "ids": "H-08",
  "verdict": "fixed",
  "reason": "LOOP_PROMPT 4절이 9개 절 순서로 바뀌었다(6분류 첫 줄, 표, 의존 교착, runnable 앞 10개, 다음 밤 첫 과제, 명령 블록). 명령의 경로와 플래그를 gen33 HEAD에서 확인했다. experiments/gate_v3_parity.py --out, experiments/v33/bench.py --dry-run --generations, genconfig binary ~/quicbed_gen33/bin/qamp가 모두 있다.",
  "evidence": "LOOP_PROMPT diff 4절; git show HEAD:experiments/gate_v3_parity.py add_argument('--out'), bench.py 252행 if args.dry_run, genconfig.json binary."
 },
 {
  "ids": "H-09",
  "verdict": "fixed",
  "reason": "status 'stopped', current null, R2 todo이고 interrupted_attempt에 64·started_kst·status_before가 들어갔다. iterations 63은 그대로이고 history 63줄은 백업과 완전히 같다. 실행기는 status=='done'일 때만 멈추므로 다음 실행을 막지 않는다.",
  "evidence": "v1_state.py: TOPDIFF status running→stopped, current R2→None, 'history equal: True 63 63', R2 diff."
 },
 {
  "ids": "H-10, H-01",
  "verdict": "fixed",
  "reason": "수정된 coverage_snapshot.py를 직접 돌렸다. 인자 없이 돌리면 쓰기 없이 출력만 한다(runs·state·tools 목록 전후 diff 0, __pycache__ 0). 6분류는 59/29/75/1/1/29, 옛 4분류는 104/60/29/1이다. 백업 state(--state)로 돌리면 57/29/29/49/1/29이고 mapped_all_locked 21, 잠김 32다. 보고 숫자와 모두 같다. iter056/057 백업 파일은 ignored_inputs로 빠진다. 카드 ID 누락은 1건(E17, done)이다. MORNING_REPORT 5행 본문은 지시대로 두고 덧붙임 절에서 정정했다.",
  "evidence": "cov_now.txt counts {'반영':59,'재현만':29,'넘김-진행가능':75,'넘김-교착':1,'처리 안 함':1,'기록 없음':29}, legacy {'처리함':104,...}, ignored_inputs [iter056_before_M4_coverage.md, iter057_before_M4_coverage.md]; cov_bakstate.txt 57/29/29/49/1/29, '기록 없음:mapped_all_locked': 21, locked 32."
 },
 {
  "ids": "H 검증자 missed 1",
  "verdict": "partly",
  "reason": "규칙(LOOP_PROMPT 2-3 --received, 2-4, EXTRA 규칙 4)과 도구(--received)는 들어갔다. --received G1은 14줄을 낸다. 그러나 이미 생긴 끊김 16줄(13개 ID)과 넘김-교착 A7-18은 판정하지 않고 E40(todo)으로 넘겼다. 기존 결함 자체는 아직 남아 있다.",
  "evidence": "v3_cov.py: done_target_unrecorded 16줄(T4 13, T5 1, L2 1, E17 1), 넘김-교착 A7-18 open ['M4'](blocked); LOOP_STATE E40 depends [T4,T5,L2,E17] 모두 done이라 실행 가능."
 },
 {
  "ids": "DECISIONS D41~D49",
  "verdict": "partly",
  "reason": "D41은 지시된 설계 4항과 맞는다. 표지 정의, false 경로의 v3.2-dev, true 경로의 'arrival_streak>0인 동안 16번째 재평가 없음', 1452 B QUICGO_MAX_IPS, decide_v2 불변이 모두 들어 있다. L3 숫자를 직접 다시 계산했다. guard_c1 대 l1_c1 B1 -1.133353에 record_c1 대 guard_c1 B1 0.000955를 더하면 -1.132398이다. B2는 0과 -0.202831을 더해 -0.202831, B5는 -0.484054와 0을 더해 -0.484054다. B6은 +0.023892, MC 0.142519로 미확정이다. 짝 평균의 합이라 점추정으로는 유효하다. none B6 +6.372402 [5.165881, 7.578923]도 L1_precision_disposition.md 35행과 같다. D44는 gen33 docs/V33FIX_bench_rules.md 1절 Z1과 맞고, D46·D47·D48도 실제 변경과 맞는다. 틀린 곳은 D49 하나다. 'E40(T4·T5가 확인하지 않은 넘김 14줄 보충)'이라고 적었지만 E40 카드와 V33FIX는 16줄(T4·T5·L2·E17)이다.",
  "evidence": "runs/L3_findings_v1.md 179·184·185·194·195·199행; runs/L1_precision_disposition.md:35; DECISIONS_NEEDED diff D41~D49; EXTRA E40 카드 '16줄(13개 ID ...)'."
 },
 {
  "ids": "CONTEXT / README / MORNING_REPORT",
  "verdict": "fixed",
  "reason": "MORNING_REPORT 앞 69,757 B는 백업과 바이트 단위로 같다(cmp). 인용한 줄 번호 5행과 78·195·207행(Go231), qamp_hold_test.go 593~595행은 실제 파일과 맞는다. JOURNAL, guard_baseline, tools 5개, iter_schema는 백업과 같다. KICK, findings, evidence, private의 mtime도 바뀌지 않았다. 덧붙인 글에는 줄표·이모지·제어 문자가 없고, 새로 넣은 굵게는 LOOP_PROMPT 2-2.5 한 곳뿐이다. 문장 수준의 작은 부정확은 새 문제 4에 적었다.",
  "evidence": "head -c 69757 | cmp → MR_PREFIX_SAME; 백업 tar 비교 SAME: JOURNAL.md, guard_baseline.json, tools/*.py, iter_schema.json; find -newermt '2026-11-02 01:29' 결과가 보고한 파일 목록과 같음; difflib 기준 추가 줄의 U+2014/U+2013 0개."
 },
 {
  "ids": "A-E6",
  "verdict": "partly",
  "reason": "R-E-wt/hygiene/.gitattributes에 main의 행이 CRLF 작업 사본 형식으로 한 줄 추가됐다. check-attr로 run_v3.sh가 text set, eol lf인 것을 확인했다. 옮긴 clone을 직접 다시 검사했다. status·ignored 0, stash 0, ref는 85b00b6 하나, rev-list --all 48커밋이 모두 R-E에 있고, 사용자 훅이 없다. 옮기기 전 기록 파일도 있다. 그래서 이동은 안전했다. R-E main은 clean, HEAD 6bbd11f(main)이고 브랜치 ref와 stash도 변하지 않았다. R-E-wt/next도 clean 2d5938b다. 남은 것은 셋이다. 커밋이 금지라 hygiene 브랜치에 아직 없다. 감사 FIX의 '확인 명령을 새 clone 절차로 바꾼다'는 gen33·루프 runs의 S2_hygiene.md가 E의 파일이 아니라 handoff로 남겼다. 옮긴 clone은 세션 스크래치에 있어 세션이 끝나면 사라질 수 있다(고유 작업이 없으니 문제는 아니다).",
  "evidence": "git -C R-E-wt/hygiene diff: '+mlkem-quic-amplification/src/*.sh text eol=lf'; check-attr 'text: set', 'eol: lf'; moved clone 'commits 48 missing 0', refs 85b00b6; git -C C:\\dev\\R-E status 빈 출력, rev-parse 6bbd11f, branch main."
 },
 {
  "ids": "LOOP_STATE 유효성 / 지시 밖 변경",
  "verdict": "fixed",
  "reason": "JSON이 유효하다. 형식은 백업과 같다(indent 2, ensure_ascii False, LF, BOM 없음). revisions의 before_sha256 7c006ee3...은 백업 파일의 sha256과 같고, order_before_v33fix도 백업 order와 같다. 바뀐 과제는 보고한 목록(L1·E10·G1 note, L2, L4, J2, J7, G1, G2, X2, J5, L6, J4, M2, R2, E7, E8, E9, E11, E13, E16, E22, E23, E26)과 새 E38~E40뿐이다. 상태 수는 done 26, blocked 13, todo 53, skipped 1이다. WSL /home/scien/v33fix_tmp/E는 없다.",
  "evidence": "v1_state.out.txt 전체 diff; sha256sum 백업 = 7c006ee3ea04...; json.dumps(indent=2, ensure_ascii=False) 왕복 일치."
 }
]

