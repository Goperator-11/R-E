# V33FIX 묶음 D: 문서와 저장소 위생

2026-11-02 KST. 도현님 지시 "지금까지 수정해야하는 모든 수정 사항들을 전부다 꼼꼼하게 수정해줘"에 따라 감사가 찾은 문서·저장소 위생 항목을 고쳤다. 작업 트리에서만 고쳤고 커밋·`git add`·이력 재작성은 하지 않았다. 다른 묶음이 같은 시각에 같은 작업 트리의 정책·Go·세계 파일을 고치고 있었으므로, 아래 시험 수치 가운데 작업 트리 전체 실행은 그 묶음들의 중간 상태를 포함한다. 감사 원문은 `C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01`의 `A-integrity.md`, `G-claims-frame.md`, `H-coverage.md`다(세션 스크래치의 원본을 옮긴 보존 사본). 이 묶음의 스크립트와 출력은 세션 스크래치의 `v33fix\D` 폴더에 있었고, 2026-11-02 묶음 P가 그것을 sha256 대조 뒤 `C:\dev\codex_handoff\v33\runs\v33fix\P\first_round\D`로 옮겼다. `git ls-files --eol` 출력을 담은 압축 파일 세 개(`eol_before.z`, `eol_after.z`, `eol_after2.z`, 각 17,986,652 B)는 같은 명령으로 다시 만들 수 있어 옮기지 않았다.

숫자 옆의 "직접 확인"은 이 묶음이 스크립트나 명령으로 다시 구한 값이고, "문서에서 읽음"은 원 문서의 값을 옮긴 것이다.

## 바꾼 파일

| 파일 | 감사 ID | 바꾼 내용 |
|---|---|---|
| `docs/REPORT_CLAIMS_v33.md` | G-E1, G 검증자 missed 2건, G-E4, G-E5, G-E6 | 빠진 단서·금지 문장, H1 Holm 하한 열, 정정 행 분류, v3.3.1-dev 절, 숫자 띄어쓰기 |
| `README.md` | G-E3, A-E8 | 활성 정책 v3.3.1-dev(상태 11)와 시험 안내 |
| `afec/rs.py` | G-E7 | 머리말의 MDS 설명 문장만 |
| `.gitattributes` | A 검증자 missed 1, A-E4 | LF 고정 확장자 12개, 훅 폴더, 로그 묶음 3곳의 `-text` |
| `.gitignore` | A-E4 | manifest가 가리키는 로그 24개의 부정 규칙 |
| `tests/test_v33_policy_worker.py` | A-E5 | 읽기 전용 감사 시험의 임시 폴더만 |
| `tools/hooks/pre-commit`(새 파일), `.git/config`의 `core.hooksPath` | A 검증자 missed 2, H-06 | 버전 관리되는 커밋 전 훅 |
| `tools/scrub_for_publish.py` | A-E2, A-E3, G-E8, H-12, H-06 | 이력 전체 검사 모드 `--history` |
| `docs/PUBLISH_PROCEDURE.md`(새 파일) | A-E2, A-E3, G-E8, H-12, H-06 | 공개·push 전 절차 |
| `docs/S5_test_hygiene.md` | A 검증자 missed 2, A-E5 | 훅 설치 방법 덧붙임 |

## REPORT_CLAIMS_v33.md

G-E1과 G 검증자 missed. 허용 문장(H1)에 다섯 단서를 붙였다. token·resumption을 끈 조건, quic-go initial cwnd 32패킷 대 RFC·quiche·msquic 10패킷, 이득의 대부분이 신용 바이트 기제라는 점(패딩 대비 패리티 고유 몫은 X1 전 미확인), v3.1 수정이 이득을 늘리지 않았다는 점, 첫 비행 업링크 대가다. 금지 표에는 "큰cert H1이 QUIC 서버 일반에서 나온다", "증폭 병목을 우리가 밝혔다", "추가 비용 없는 FEC", "H1 이득은 패리티의 고유 가치", "v3.1 수정이 이득을 늘렸다" 다섯 행을 더했다. 덱 슬라이드 번호는 볼트 노트 207행의 경위를 인용했다. 확인한 출처는 다음과 같다.

- 볼트 `C:\dev\claude_brain\03 프로젝트\진행중\우리 학술 (연구공모전).md`(읽기만, 2026-11-02 00:47 수정판): 86행(60.0 B), 120~127행(신규성 축소, Nawrocki 외 CoNEXT '22, Kampanakis & Lepoint SSR '23, McManus 2020), 154·155행(패딩에 가까운 기제, 대가), 180행(IW, token·resumption, 같은 바이트 문장), 191행(덱 파일 없음), 202행(69.0 B 정정), 207행(덱 15·16번 출처). 감사 당시 인용한 행 번호(172, 193~194, 199)와 다른 것은 감사 뒤에 노트가 고쳐졌기 때문이다.
- `C:\dev\codex_handoff\v33\prompt\CONTEXT.md`의 §1 '선행연구 위치' 항목, §4 '테스트베드 설정' 항목(SessionTicketsDisabled, TokenStore 없음), §5-3 '서버 회계, P, IW, PTO' 항목(IW 10 서버에서 큰cert는 어차피 2-RTT, 감사 문장), §7 '쓰면 안 되는 말' 문단. 처음에는 11·53·88·125행으로 적었는데, 이 번호는 2026-11-02 01:30 1차 백업 tar `codex_handoff_v33_meta.tar`에 든 판(파일 시각 2026-10-30 01:07, sha256 `b07a88b55333c0700e15980857ef772973c3f6519c7b697969bd8f87685c6fa8`, 사본 `C:\dev\codex_handoff\v33\runs\v33fix\P\evidence\CONTEXT_md_from_backup_0130.md`) 기준이었다. CONTEXT.md가 02:04 이후 맨 앞에 0절을 넣어 다시 쓰이면서 번호가 바뀌었으므로, 2026-11-02 묶음 P가 이 문서와 REPORT_CLAIMS의 인용을 절 이름으로 바꿨다. 네 항목은 묶음 P가 확인할 때 지금 판의 같은 절에 그대로 있었다.
- 60.0 B: `C:\dev\pq_afec\docs\PADFEC 실측 보고서.md`(파일 시각 2026-08-27 22:23) 13·60·67·71행, 문서에서 읽음.
- 69.0 B: `C:\dev\pq_afec\experiments\results\p1_flight.json`(파일 시각 2026-10-01 14:39)의 `capacity_checks` 12행을 읽어 직접 계산했다. 12행 모두 `feasible=false`, `any_inplace_feasible=false`이고, k=2인 4행의 C − capacity는 228.5, 322.5, 158.5, 69.0 B다. 최소 69.0 B는 X25519MLKEM768, ips 1450, C=1457, capacity 1388.0이다(스크립트 `p1cap.py`).
- 첫 비행 업링크: `C:\dev\pq_afec_gen31\g3\RESULT_stage3.md` 36·37·91·95행, `C:\dev\pq_afec_gen3\g3\RESULT_stage2.md` 23·24·51행, 문서에서 읽음. 과제 카드는 둘 다 gen31에 있다고 했지만 `RESULT_stage2.md`는 gen31에 없고 gen3에 있다.
- 신용 바이트 기제 수치: `C:\dev\pq_afec_gen31\g3\RESULT_stage0.md` 17·51행(6.89 ms [2.53, 11.26], 41.04 ms [35.08, 47.00], 30.4 ms), 문서에서 읽음.

G-E6. H1 표의 열 이름을 "보정 안 한 95% 구간"으로 바꾸고 Holm(m=2) 하한과 Holm 수준 열을 더했다. 값은 `C:\dev\pq_afec_gen31\experiments\results\p31_gencompare_decisions.json`의 `/H1/run1/tests`, `/H1/run2/tests`에서 직접 읽었다(스크립트 `h1holm.py`). run1 S_bigcert 24.330565(수준 0.05), run1 S_rtt200 10.762043(0.025), run2 S_bigcert 24.898871(0.025), run2 S_rtt200 7.327190(0.05)이고, 하네스 상한 3.101743 ms, 하한 평균 17.546304·16.113031 ms다.

G-E4. "정정 행의 성격" 절에 실제 정정 18행, 상태 주석 14행, 재확인 3행을 행 목록과 함께 표로 적었다. 판단 분류라는 단서와, 검증자가 짚은 경계 행 두 개(`실험환경 대조.md:65`, `PROTOCOL_stage3.md:3`)를 맞바꿔도 수가 같다는 점을 함께 적었다. MORNING_REPORT와 커밋 `d67717d9b` 메시지의 "정정35행"은 고치지 않았다.

G-E5. 한글 바로 뒤의 숫자·±·−·§ 앞에 띄어쓰기를 넣고, `ms,m4=`처럼 쉼표 뒤가 붙은 곳, `CV80 B`처럼 영문 약어에 붙은 숫자, `1792통과·2건너뜀`처럼 단위 없는 숫자를 고쳤다. 인용 열(현재 문장 발췌)과 링크 주소, 조건 이름 `버스트3`은 손대지 않았다. 스크립트(`spacing_fix.py`, `token_check.py`)로 확인한 결과는 다음과 같다(직접 확인).

| 확인 항목 | 고치기 전 | 고친 뒤 |
|---|---:|---:|
| 숫자 토큰 수(`\d+(\.\d+)*`) | 1,153 | 1,153, 목록 동일 |
| 링크 수 | 57 | 57, 모두 동일 |
| 인용·경로 칸이 같은 정정 행 | 35 | 35 |
| 한글 바로 뒤 숫자(문서 전체) | 115 | 6 |

남은 6곳은 모두 `버스트3`이고 그중 2곳은 인용문 안이다. 그 뒤 내용을 더한 최종본에서 인용 열을 뺀 본문에 남은 곳은 `버스트3` 네 곳과 MORNING_REPORT 표기를 그대로 옮긴 "정정35행" 하나다. 띄어쓰기 수정 뒤에 내용을 더했으므로, 최종본의 숫자 토큰 수는 더한 문장만큼 늘었다. 줄표와 이모지는 인용 밖 본문에 0개다.

v3.3.1-dev 절. 과제가 정한 정책 방향(c1_seen, none 경로 v3.2 동일, c1 경로 L3 record_only 결정, 1452 B 상한)을 전제로 쓸 수 있는 말 셋과 쓰면 안 되는 말 여섯을 적었다. 숫자는 두 출처에서 직접 읽었다. `g3/v33/L1_benchmark_precision_v1.json` `comparisons[6]`(B6, `current_none` 대 `v32`)의 평균 6.372401820014076 ms와 조정 경계 [5.1658809, 7.5789227] ms, 그리고 `C:\dev\codex_handoff\v33\runs\L3_findings_v1.md` 179~208행이다. record_c1 − l1_c1은 두 대조 평균의 합으로 계산했다(B1 −1.132398, B2 −0.202831, B5 −0.484054, B6 0.023892 미확정). C1이 비표준·비인증이고 회신 비용 0을 가정했다는 문장은 `docs/c1_threat_model.md` 3·7·9행, `docs/L1_observation_contract.md` 29행, `docs/L1_benchmark_execution.md` 13행에서 확인했다(두 문서 맨 위에 2026-11-02 정정 문단이 들어가기 전에는 27·11행이었다). v3.3.1-dev 자체의 평가 수치와 v3.2 동일성 시험 결과는 다른 묶음 문서(`V33FIX_policy.md`, `V33FIX_policy_go.md`, `V33FIX_evaluation.md`)에 맡기고 이 문서에서는 확인하지 않았다고 적었다.

## README.md

G-E3. 정책 버전·상태 판본을 v3.3.1-dev·11, Go 캐시 형식을 `padfec3.cache3/11`로 적고 `c1_seen` 두 경로, 1452 B 상한(k=2·W=1406 → 1406+39+12 = 1457 B), 실측 0건, C1의 비인증·회신 비용 0 가정을 새 절로 썼다. v3.2-dev에서 물려받은 기제 설명은 "c1_seen이 False인 경로에서 같게 동작한다"는 절로 옮겼다. V33FIX 문서 9개는 다른 묶음이 쓰는 중이라 파일 이름만 가리켰다. 시험 안내는 10개 파일 목록 대신 `pytest.ini` 기본 실행으로 바꾸고, 커밋 `d67717d9b` 기준 수(1792 passed, 2 skipped, 32 deselected, 하위 4513, 문서에서 읽음)와 Go "PASS 231, SKIP 2, FAIL 0"(감사 A-E8, 문서에서 읽음), 건너뛰는 두 Go 시험과 `M1_REFERENCE_GZIP` 조건(`qamp_hold_test.go` 593·595행, 직접 확인)을 적었다. `-feedback` 기본값 false는 `experiments/quicbed/qamp.go`의 `flag.Bool("feedback", false, ...)` 정의(작업 시각 3860행, 테스트베드 묶음의 수정 뒤 행 번호가 바뀜), `C1_SOURCES = ("c1", "ack")`는 `padfec3/learn3.py` 27행에서 확인했다. 작업 시각에 Python 쪽은 이미 `STATE_VERSION = 11`, `POLICY_VERSION = "v3.3.1-dev"`였고, Go 쪽(`policy3.go` 53·56행)은 아직 `padfec3.cache3/3`, `v3.3-dev`였다. 2026-11-02 묶음 P가 다시 읽었을 때 `policy3.go`는 `p3StateVersion = 11`(50행), `p3UDPMax = quicgoMaxIPS`(51행, `pfail_table.go` 35행 1452), `p3CacheSchema = "padfec3.cache3/11"`(53행), `p3PolicyVersion = "v3.3.1-dev"`(56행)로 README와 같았다.

## afec/rs.py

G-E7. "반데르몬드 행렬을 systematic 형태로 행축약하면 이 성질이 깨질 수 있다"를 고쳤다. 새 설명은 이렇다. systematic 생성행렬 [I | A]는 A의 모든 정사각 부분행렬이 가역이어야 MDS다. 반데르몬드 생성행렬을 가역 행변환으로 [I | A] 꼴로 바꾸면 행공간이 같으므로 MDS가 유지된다. 깨질 수 있는 것은 행변환 없이 반데르몬드 행렬을 A 자리에 넣는 구성이다. Cauchy 행렬은 모든 정사각 부분행렬이 다시 Cauchy라 가역이다. 머리말 문자열을 뺀 모듈 AST가 HEAD와 같음을 확인했다(코드 동작 불변, 직접 확인).

## .gitattributes

A 검증자 missed 1. `*.log`, `*.saved`, `*.buildinfo`, `*.sha256`, `*.srcsha`, `*.jsonl`, `*.patch`, `*.diff`, `*.js`를 `text eol=lf`로 넣었다. 같은 위험이 있던 나머지 3개(`*.yml` 1개, `*.csv` 1개, `*.ini` 1개)도 넣어, 속성 없이 LF로 저장된 파일을 115개에서 0개로 줄였다. 새 훅 폴더용 `tools/hooks/* text eol=lf`도 넣었다. 확인은 다음과 같다(모두 직접 확인).

- `git ls-files --eol` 분석: 바꾸기 전 `i/lf`이면서 LF·`-text` 속성이 없는 파일 115개(.log 82, .saved 10, .sha256 5, .buildinfo 4, .srcsha 4, .jsonl 3, .patch 2, .diff 1, .js 1, .yml 1, .csv 1, .ini 1), 바꾼 뒤 0개. 인덱스가 CRLF·mixed(800개)인데 `text` 속성이 붙는 파일은 바꾸기 전후 0개이므로, 하위 `.gitattributes`의 `-text`가 그대로 이긴다.
- `git check-attr text eol`: 115개 모두 `text: set`, `eol: lf`.
- 이 115개의 LF 원본 sha256 가운데 HEAD 추적 파일이 가리키는 것은 108개(log 79, saved 10, buildinfo 4, sha256 4, srcsha 4, jsonl 3, patch 2, diff 1, js 1)로, 감사 수와 같다.
- clone 시험: `core.autocrlf=true`, `core.longpaths=true`, `--no-checkout`과 cone 방식 sparse checkout(45개 폴더)으로 HEAD를 받았다. HEAD 속성으로는 115개가 모두 CRLF였고 manifest 해시 108개가 모두 틀렸다. 새 `.gitattributes`를 clone 인덱스에 올리고 115개를 다시 checkout하자 CRLF 0개, 108개 해시 모두 일치였다. 이때 clone의 `git status`에는 `.gitattributes` 말고 바뀐 파일이 없었다.
- gen33 작업 트리의 `git status`에는 이 묶음이 바꾼 파일과 다른 묶음의 파일 말고 새로 수정으로 뜨는 파일이 없었다(`git --no-optional-locks status`, 인덱스를 쓰지 않음).

작업 트리 변경은 커밋 전이므로 지금 새로 clone하면 아직 옛 속성이 적용된다.

## .gitignore와 로그 24개

A-E4. `git ls-files --others --ignored --exclude-standard -- g3`가 찾은 24개(E12_v1/runs 7개, J7_checkpoint_v1/runs 16개, L2_unit/runs 1개)를 경로별 `!` 규칙으로 다시 넣었다. 24개 모두 sha256이 HEAD의 manifest와 run JSON에 2·5·7번 나온다(직접 확인). 바꾼 뒤 `git status --porcelain --untracked-files=all`에 24개가 `??`로 보이고, 무시된 g3 파일은 0개다. `git add`는 하지 않았다.

24개 가운데 10개는 CR 바이트를 담고 있다(처음에 11개로 적었다가 2026-11-02 묶음 P가 바이트로 다시 셌다. 10개 모두 CRLF이고 단독 CR은 0개다. E12_v1 3개, J7_checkpoint_v1 7개, L2_unit 0개). 이대로 `*.log text eol=lf`를 받으면 `git add` 때 LF로 정규화돼 저장 blob이 manifest 해시와 달라진다. 예를 들어 `J7_reference_01.log`는 정규화하면 blob이 `21eb3580…`, 원본 그대로면 `871f4711…`다. 그래서 세 폴더의 `runs/*.log`에 `-text`를 걸었다. 세 폴더에는 이미 추적 중인 `.log`가 없다. `git hash-object --path=<경로>`(쓰기 없음)로 필터를 거친 blob과 원본 blob이 24개 모두 같음을 확인했고, `core.autocrlf=true`에서도 같았다.

## tests/test_v33_policy_worker.py

A-E5. `test_read_only_audit_blocks_import_time_write`가 저장소 안 `experiments/state/v33_worker_test_artifacts/source-*`에 꾸러미를 만들고 지우지 않던 것을, 저장소 밖 `tempfile.TemporaryDirectory(prefix="v33-worker-source-")`로 바꿨다. 시험은 임시 폴더가 저장소 밖인지, 감사 훅이 import 시 쓰기를 `PermissionError`로 막는지, 표지 파일이 생기지 않았는지, 끝난 뒤 임시 폴더가 지워졌는지를 본다. 원래 목적은 그대로다.

이 시험 하나는 통과했다(1 passed). 실행 전후 `source-*` 폴더 수는 61개로 같았고 임시 폴더 시스템 위치에 `v33-worker-source-*`가 남지 않았다. 이미 쌓인 61개는 gitignore 대상이며 지우지 않았다.

## 커밋 전 훅

A 검증자 missed 2. `.git/hooks/pre-commit`과 바이트가 같은 `tools/hooks/pre-commit`을 만들고(`cmp` 확인, CR 0개), 이 저장소에 `git config --local core.hooksPath tools/hooks`를 넣었다. `git hook run pre-commit`은 올린 파일이 없을 때 PASS를 냈다. 스크래치 저장소에 같은 훅과 `tools/precommit_size.py`를 두고 20,000,001 B 파일과 PEM 개인키 블록을 커밋하려 하자 둘 다 종료 코드 1로 거부됐다. 설치 방법은 `docs/S5_test_hygiene.md` 끝 절에 덧붙였다. 처음 커밋할 때 `git add --chmod=+x tools/hooks/pre-commit`으로 실행 비트를 기록해야 한다.

## 이력 검사와 공개 절차

A-E2, A-E3, G-E8, H-12, H-06. 이력은 다시 쓰지 않았다. 커밋 122개의 해시가 `LOOP_STATE.json`·`JOURNAL.md`에 122개, `MORNING_REPORT.md`에 108개, g3 추적 파일에 73개, `docs/*.md`에 11개 적혀 있음을 7자 이상 접두사 대조로 확인했다(`hashref2.py`, 직접 확인). 2026-11-02 묶음 P가 기준을 밝혀 다시 쟀다(`C:\dev\codex_handoff\v33\runs\v33fix\P\scripts\hashrefs.py`, 출력 `hashrefs.json`, 06:45 측정, HEAD `d67717d9b`). 문서에서 경계가 있는 7~40자 16진 토큰이 어떤 커밋 해시의 접두사이면 그 커밋을 센다. 결과는 `LOOP_STATE.json` 122, `JOURNAL.md` 122, `MORNING_REPORT.md` 108(셋 다 그 시각의 파일), HEAD의 g3 추적 파일 전체 121(검증 묶음 밖만 보면 3), HEAD의 `docs/*.md` 9, 작업 트리의 `docs/*.md`(추적 안 된 V33FIX 문서 포함) 14다. 처음 적은 73은 `git grep -I -o`로 센 값인데, 검증 묶음의 `.gitattributes`가 `* -text -diff`라 git이 그 파일들을 binary로 보고 `-I`가 건너뛴 결과다(같은 방식으로 다시 세도 73). 11은 `hashref2.py`가 작업 트리의 `docs/*.md`를 읽은 02:05 무렵의 값이고, 그 뒤 V33FIX 문서가 늘어 지금은 14다. 대신 `docs/PUBLISH_PROCEDURE.md`에 이력 없는 새 저장소로 내보내는 절차를 적었다. 거기에 개인키 PEM 28개 경로, 추가 커밋 `60a2f18f9`와 추적 해제 커밋 `3eef6a737`, 20 MB 초과 blob 3개(HEAD 경로 5개), 원자료는 저장소 밖 보관소와 manifest만, `core.longpaths`를 넣었다. 문서의 `git archive` 두 명령은 스크래치로 실제 실행해 파일 수(1,205개, 1,195개)를 확인했다. 새 저장소를 만들고 검사·시험하는 4~6단계는 실행하지 않았다.

`tools/scrub_for_publish.py`에 `--check --history` 모드를 더했다. `git rev-list --objects --all`로 도달 가능한 blob을 모으고, `git cat-file --batch`로 내용을 읽어 완전한 PEM 개인키 블록(`tools/precommit_size.py`와 같은 정규식)과 20,000,000 B 초과 blob을 찾는다. 키가 든 경로의 추가·삭제 커밋과 HEAD 경로도 같이 낸다. 아무것도 쓰거나 지우지 않는다. 기존 `--check` 출력과 `check()` 함수는 그대로라 기존 시험 `tests/test_v33_repro_tools.py`는 6개 모두 통과했다. 실제 저장소 결과(직접 확인)는 도달 가능한 blob 87,266개, 읽은 내용 3,557,316,810 B, 개인키 blob 28개(1,880,048 B, 모두 `g3/v33/validation/T1_v1/runs/T1_smoke_v1/`, HEAD에 0개), 추가 커밋 `60a2f18f9`, 삭제 커밋 `3eef6a737`, 20 MB 초과 blob 3개다. 28개와 1,880,048 B는 S5 문서와 감사 수와 같다. 스크래치 합성 저장소에서는 머리 문자열만 있는 텍스트는 잡지 않고, 지운 키 파일과 큰 파일은 잡는 것도 확인했다. `--check` 없이 `--history`만 주면 인자 오류(종료 코드 2)다.

## 시험

| 실행 | 결과 |
|---|---|
| `tests/test_v33_policy_worker.py` 고친 시험 하나 | 1 passed |
| `tests/test_v33_policy_worker.py` 전체(작업 트리) | 8 passed, 1 failed. 실패는 48행 `state_version` 4 기대(정책 묶음이 상태 11로 올림) |
| `tests/test_v33_repro_tools.py` | 6 passed |
| `tools/lint_ast.py` | 종료 코드 0 |
| 기본 pytest 전체, gen33 작업 트리(다른 묶음 수정 포함, 172.86초) | 4 failed, 1833 passed, 2 skipped, 32 deselected, 하위 10931 passed |
| 기본 pytest 전체, HEAD clone에 이 묶음 파일만 얹은 사본(129.95초) | 1792 passed, 2 skipped, 32 deselected, 하위 4513 passed. `d67717d9b` 기준과 같다. 실행 뒤 clone에 `experiments/state/v33_worker_test_artifacts` 폴더가 생기지 않았다 |

작업 트리 전체 실행의 실패 4개는 `test_adaptation_benchmark.py::test_ablations_restore_only_loss_state_and_keep_observation_history`, `test_p21_gencompare.py::test_toy_cell_matches_a_direct_computation`(행동 (126, 1, 3)이 g3 후보 집합에 없음, 1452 B 상한 변경과 관련된 것으로 보임), `test_v33_l3_candidate.py::test_active_l1_rejects_l3_candidate_state`(`STATE_VERSION` 11 대 4), `test_v33_policy_worker.py::test_current_complete_first_flight_updates_cold_loss_state_once`(같은 이유)다. 넷 다 정책 묶음이 바꾸는 중인 파일 때문이고 이 묶음 파일과 무관하다는 것은 바로 아래 줄의 분리 실행으로 확인했다. 실행 전후 `__pycache__`와 `.pytest_cache`는 생기지 않았다.

## 못 한 것

- `docs/README.md` 읽는 순서·ID 용어집과 다른 docs 100여 개의 띄어쓰기(G-E5 FIX의 나머지)는 이 묶음 파일 목록 밖이라 하지 않았다. MORNING_REPORT 105행도 같다.
- G-E2(측정 사슬 봉쇄를 결정 항목으로 올리기)는 이 묶음 몫이 아니다.
- `tests/test_v33_policy_worker.py` 48행의 `state_version` 4 기대는 이 묶음 범위(임시 폴더 fixture) 밖이라 고치지 않았다.
- 새 공개 저장소 만들기와 그 안의 검사·시험, push, 이력 재작성은 D1·D11·D40에 따라 하지 않았다.
- 저장소 안에 이미 쌓인 `experiments/state/v33_worker_test_artifacts/source-*` 61개는 지우지 않았다.
- `.git/hooks/pre-commit` 옛 파일은 지우지 않았다. `core.hooksPath`가 있으므로 쓰이지 않는다.
- `--history` 모드의 단위 시험은 시험 파일(`tests/test_v33_repro_tools.py`)이 이 묶음 목록 밖이라 넣지 않았다. 합성 저장소 실행으로만 확인했다.

## 통합 정정 (2026-11-02, 묶음 P)

1차 검증(`C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports\VERIFY_ALL.md`의 D-docs new_problems)이 짚은 것을 묶음 P가 고쳤다. 위 본문에서 바뀐 곳은 다음과 같다.

- 3행의 사용자 홈 스크래치 경로를 지우고 감사 원문과 이 묶음 자료의 보존 위치로 바꿨다.
- "확인한 출처" 목록의 CONTEXT.md 인용을 행 번호에서 절 이름으로 바꾸고 기준 판을 밝혔다. REPORT_CLAIMS도 같이 고쳤다.
- 로그 24개 가운데 CR을 담은 파일 수를 11에서 10으로 고쳤다. 바이트로 다시 센 값이다(`C:\dev\codex_handoff\v33\runs\v33fix\P\scripts\cr_count.py`, `cr_count.json`). `-text`를 건 결정과 해시 일치 결과는 바뀌지 않는다.
- 커밋 해시 참조 수(73, 11)를 기준을 밝혀 다시 잰 값으로 보탰다. `docs/PUBLISH_PROCEDURE.md`의 같은 숫자와 사용자 경로 파일 수(22)도 다시 재서 고쳤고, 그 문서의 내보내기 절 앞에 "묶음 D의 위생 변경을 먼저 커밋한다"는 전제를 넣었다.
- `-feedback` 기본값의 행 번호 인용을 정의 문장 인용으로 바꾸고, Go 상수가 지금 README와 같음을 적었다.
- README와 REPORT_CLAIMS가 가리키던 `docs/V33FIX_policy_go.md`, `docs/V33FIX_evaluation.md`는 지금 있다. REPORT_CLAIMS의 v3.3.1-dev 절에 v3.2 동일성 시험 범위와 평가 문장을 옮겼다(48행 끝의 "확인하지 않았다"를 대신한다).
- "못 한 것"의 `tests/test_v33_policy_worker.py` 48행 기대(4)는 묶음 P가 11로 고쳤다. 이 묶음이 고친 fixture는 그대로다. `--history` 단위 시험도 묶음 P가 `tests/test_v33_repro_tools.py`에 넣었다(그 파일 7 passed). 자세한 내용은 `docs/V33FIX_policy.md` 끝 "통합 정리" 절에 있다.
