# 내보내기와 공개 전 절차

gen33 코드는 R-E 저장소의 하위 폴더 pq_afec_gen33로 내보낸다. 이 문서는 gen33 쪽에서 밟을 순서와 검사 도구를 적는다. R-E 쪽 커밋, 태그, 배포 검사의 정본은 R-E 루트의 docs/RELEASE_PROCEDURE.md다. 현재 결정은 D62다. R-E는 비공개로 두고 LICENSE를 넣지 않으며 gen33 이력은 올리지 않는다. push는 도현님이 한다. 이 문서는 실행 허가가 아니다.

## 이력은 다시 쓰지 않는다

gen33 이력은 `filter-repo` 같은 도구로 다시 쓰지 않는다(D42). 커밋을 다시 쓰면 해시가 모두 바뀌는데, 루프 기록이 이 해시를 근거로 인용한다. 2026-11-02 06:45에 그때 HEAD까지의 커밋 122개를 대조했다. 당시 LOOP_STATE.json과 JOURNAL.md에는 122개 전부, MORNING_REPORT.md에는 108개, HEAD의 g3 추적 파일에는 121개(검증 묶음 밖만 보면 3개), HEAD의 docs 아래 Markdown에는 9개, 작업 트리의 docs 아래 Markdown에는 14개가 적혀 있었다. 세는 기준과 처음 잘못 센 값의 원인은 [V33FIX_docs_hygiene](V33FIX_docs_hygiene.md)에 있다.

이력 정리를 꼭 원하면 gen33 원본이 아니라 별도 사본에서만 하고, 해시를 인용한 문서를 새 해시로 다시 이어야 한다. R-E에는 아래 내보내기 도구로 만든 이력 없는 사본만 들어간다.

## 이력에 남은 것

이력 검사는 아무것도 지우거나 고치지 않고 JSON만 출력한다.

```powershell
python -I -B tools/scrub_for_publish.py --check --history
```

2026-11-02 실행에서 완전한 PEM 개인키 블록이 든 blob은 28개, 합계 1,880,048 B였다. 모두 T1 검증 묶음의 T1_smoke_v1 실행 폴더에 있던 certificate_<크기>_0.pem 파일이다. 이 파일들은 커밋 `60a2f18f93445e3801452323b4923ed9691c8c7d`(T1, 2026-11-01 01:21:44 KST)에서 들어왔고 `3eef6a7373c9b449df77353cfe0322ca6a9b61fc`(S5, 같은 날 08:35:10)에서 추적이 끊겼다. 고정 seed로 만든 자가서명 시험 키다(D22). 키 사본은 해시와 함께 C:\dev\codex_handoff\v33\private\S5_T1_keys_v1에 있다(로컬 보존). 그래도 공개본에는 넣지 않는다. 두 커밋 사이의 이력을 공개하면 키가 같이 나간다(D40).

같은 실행에서 20,000,000 B를 넘는 blob은 3개였다. 20 MB 거부 훅이 생기기 전(11-01 08:21)에 커밋된 파일이고, 지금 HEAD에서도 아래 경로 5개로 추적된다. 모두 검증 묶음 안이라 내보내기 규칙에 들지 않고 gen33에만 남는다.

| 크기 (B) | HEAD 경로 |
|---:|---|
| 27,206,885 | g3/v33/validation/M1_stage1/runs/M1_wire_reference_01.tsv.gz, M1_wire_reference_02.tsv.gz(같은 내용) |
| 23,942,349 | g3/v33/validation/M1_complete_inputs/handoff/runs/M1_validated_runs_v1.json, g3/v33/validation/M1_stage2_family/M1_validated_runs_v1.json(같은 내용) |
| 21,038,432 | g3/v33/validation/J7_v2/runs/J7_validated_runs_v1.json |

커밋 작성자 이름과 메일도 이력에 들어 있다. 공개본의 작성자 정보는 따로 정한다(E37).

## 검사 도구

`tools/scrub_for_publish.py`는 파일을 읽기만 하고 고치지 않는다. 출력 JSON은 UTF-8이고, Windows에서 리다이렉트로 파일에 저장해도 UTF-8로 읽힌다.

- `--check --root <폴더>`는 사용자 경로, 메일 주소, 개인키 머리 문자열이 든 파일 수를 센다. 폴더가 git 저장소의 맨 위 폴더면 추적 파일(`git ls-files`)을 읽고, 아니면 `os.walk`로 디스크의 모든 파일을 읽는다. 어느 쪽이든 `.git`은 건너뛴다. R-E 안에 내보낸 pq_afec_gen33 폴더는 git 저장소 맨 위가 아니므로 디스크의 파일을 그대로 읽는다. 출력의 `file_listing`이 어느 방식이었는지 알려 준다. 찾은 것이 있으면 FINDINGS와 rc 1, 없으면 PASS와 rc 0이다.
- `--check --history --root <저장소>`는 모든 ref에서 닿는 blob을 읽어 완전한 PEM 개인키 블록과 20,000,000 B를 넘는 blob을 찾는다. git 저장소 맨 위 폴더만 받는다. 다른 폴더를 주면 이유를 stderr에 쓰고 rc 2로 끝난다.
- `--root`로 준 폴더가 없으면 rc 2다.

## 기본 경로: R-E 하위 폴더로 내보내기

아래 명령의 `<gen33>`, `<R-E>`, `<커밋>`은 자리표시자다. 이 PC에서 `<gen33>`은 C:\dev\pq_afec_gen33이고, `<R-E>`는 R-E를 체크아웃한 폴더다(로컬 보존).

1. 내보낼 gen33 커밋을 정한다. 도구는 그 커밋의 트리만 읽으므로 커밋하지 않은 작업 트리 변경은 나가지 않는다.

2. R-E 쪽 내보내기 도구 tools/export_gen33.py를 돌린다(R-E 쪽 경로, 로컬 보존).

   ```powershell
   python -I -B <R-E>/tools/export_gen33.py --src <gen33> --rev <커밋> --dest <R-E>/pq_afec_gen33 --rule <R-E>/tools/gen33_export_rule.json
   ```

   규칙 파일 tools/gen33_export_rule.json(R-E 쪽, 로컬 보존)은 검증 묶음(g3/v33/validation 아래)을 기본으로 빼고, 시험 수집이 읽는 묶음만 넣는다. J1_final_analysis_v1, J6_final_analysis_v1, L1_precision_final, L2_final_analysis_v1, L3_final_analysis_v1, L5_final_analysis_v1은 .py 파일만, M1_stage2_validation은 전부 넣는다. .github 폴더는 뺀다. GitHub는 저장소 루트의 .github/workflows만 읽으므로 R-E 하위 폴더에서는 CI가 돌지 않는다. 그 밖의 파일은 모두 나간다.

   export_gen33.py는 git ls-tree로 커밋의 파일 목록을 만들고 규칙으로 거른다. 고른 파일에 20,000,000 B를 넘는 파일, 완전한 PEM 개인키 블록(도구 옆 precommit_size.py와 같은 정규식), 규칙에 없는 검증 묶음을 가리키는 tests 바로 아래 .py 파일, text 속성이 unset이 아니고 앞 8,000 B에 NUL이 없는 blob의 CRLF 가운데 하나라도 있으면 아무것도 쓰지 않고 rc 1로 끝난다. dest는 이름이 pq_afec_gen33이고 다른 git 작업 트리 안에 있는 폴더일 때만 지우고 다시 만들며, 조건이 맞지 않으면 rc 2다. 파일 내용은 git cat-file --batch로 받은 blob 바이트를 그대로 쓰므로 줄 끝이 바뀌지 않는다. 끝나면 R-E 루트의 docs/EXPORT_gen33.json에 source rev, 규칙 sha256, 파일 수, 실행 비트 파일, 경로별 blob을 쓴다(R-E 쪽, 로컬 보존).

3. R-E에서 줄 끝 변환 없이 색인에 넣는다.

   ```powershell
   git -C <R-E> -c core.autocrlf=false add -f -A pq_afec_gen33
   ```

   이 PC의 시스템 기본값은 core.autocrlf=true라서, 옵션 없이 add하면 줄 끝 변환 때문에 blob이 gen33과 달라질 수 있다. -f는 R-E의 ignore 규칙에 걸리는 파일도 넣는다. 색인의 blob(git ls-files -s pq_afec_gen33)과 docs/EXPORT_gen33.json의 blob이 하나도 다르지 않아야 한다.

4. 내보낸 폴더에서 시험을 돌린다. 명령과 기대 수는 [REPRODUCE](REPRODUCE.md)를 따른다.

5. 내보낸 폴더와 R-E 이력을 검사한다. `<R-E clone>`은 R-E를 새로 clone한 폴더다.

   ```powershell
   python -I -B <R-E>/pq_afec_gen33/tools/scrub_for_publish.py --check --root <R-E>/pq_afec_gen33
   python -I -B <R-E>/pq_afec_gen33/tools/scrub_for_publish.py --check --history --root <R-E clone>
   ```

   첫 명령은 FINDINGS(rc 1)가 정상이다. 아래 위생 분류 표의 사용자 경로 파일이 기록 원문 그대로 나가기 때문이다. 개인키는 둘째 명령의 `private_key_blob_count`가 0인지로 판단한다.

6. 커밋, 태그, 배포 검사, push 순서는 R-E 루트의 docs/RELEASE_PROCEDURE.md를 따른다. push는 도현님이 한다(D62).

2026-11-05에 커밋 feb0b1850을 R-E로 내보낼 때는 이 도구가 없었다. 검증 묶음을 빼고 넣었다가 시험 수집이 실패해 파일을 손으로 더했고, 줄 끝 때문에 add 옵션도 달랐다. 그 결과인 R-E 커밋 70e7e08의 pq_afec_gen33은 파일 1,620개이고 그중 검증 묶음 파일이 383개다. 같은 커밋 feb0b1850에 지금 규칙을 적용하면 1,619개를 고른다. 차이는 .github/workflows/ci.yml 하나이고, 양쪽에 다 있는 파일의 blob과 mode 차이는 0이다.

## 새 공개 저장소로 내보내기

D62가 바뀌어 공개가 정해질 때만 쓴다. 대상 저장소와 원격 이름도 그때 도현님이 정한다.

1. 이력 없는 새 저장소를 만든다. gen33 이력에는 위의 시험 키와 큰 blob이 남아 있으므로 그대로 올리지 않는다.
2. 내용은 같은 도구와 규칙으로 고른다. 도구는 dest가 git 작업 트리 안의 pq_afec_gen33 폴더여야 하므로 새 저장소 안의 pq_afec_gen33 하위 폴더로 쓴다.
3. 커밋 전에 core.autocrlf를 false, core.longpaths를 true로 두고 작성자 이름과 메일을 도현님이 정한 값으로 넣는다. R-E처럼 루트에 tools/hooks/pre-commit과 tools/precommit_size.py를 두고 core.hooksPath를 tools/hooks로 켜면, 20,000,000 B를 넘는 파일과 완전한 PEM 개인키가 든 커밋을 훅이 막는다.
4. 새 저장소의 `--history` 결과에서 `private_key_blob_count`와 `oversize_blob_count`가 모두 0이어야 한다. `--check`가 찾은 사용자 경로와 메일은 아래 표를 보며 파일마다 지우거나 일반 경로로 바꿀지 정한다. 서버명과 인계 문서도 이때 뺀다(Q-21).
5. 시험은 [REPRODUCE](REPRODUCE.md)를 따른다.

## 내보내는 파일의 위생 분류(E37)

2026-11-07, gen33 커밋 789202f1e에 규칙을 적용해 고른 파일 1,912개를 `--check`와 같은 정규식으로 읽은 결과다(검증 묶음 파일 383개 포함, 20,000,000 B 초과 0개, .pem 0개). 세는 스크립트와 출력은 로컬 보존 폴더 C:/dev/codex_handoff/final/runs/의 F53_counts.py와 F53_counts.json이다. 파일 수는 커밋마다 달라지므로 최종 내보내기의 수는 docs/EXPORT_gen33.json(R-E 쪽, 로컬 보존)을 본다. 공개 계획이 없으므로(D62) 표의 파일은 옮기거나 고치지 않았다. 공개가 정해지면 이 표에서 시작한다.

| 분류 | 지금 상태 | 처리 |
|---|---|---|
| 사용자 경로가 든 파일 | 92개. 이 PC 계정 이름이 든 파일이 89개다. 루프 기록 사본(docs/loop_record) 21개, 실행 증거(g3/v33/evidence) 26개, 내보내는 검증 묶음 21개, 그 밖의 g3에 있는 실행 계획, 기준선, 보관 색인, 시험 입력 17개, 문서 `docs/O4_reference_result.md`와 `docs/S5_test_hygiene.md`, 코드 `tools/final_check.py`와 `tests/test_final_check.py`다. 나머지 3개는 계정 이름이 아닌 시험용 경로만 든 시험 파일이다. | 기록과 실행 당시 경로는 원문을 고치지 않는다. 그래서 내보낸 폴더의 `--check`는 FINDINGS가 정상이다. 공개 때 파일마다 정한다. |
| 메일 주소가 든 파일 | 3개. 감사 기록 docs/loop_record/v33/findings/v33audit_2026-11-01/A-integrity.md에 gmail.com 주소 하나, 시험 파일 2개에 example.invalid 주소. | 감사 기록은 원문을 고치지 않는다. 공개 때 그 기록을 뺄지 정한다. |
| 개인키 머리 문자열이 든 파일 | 1개, `tests/test_v33_repro_tools.py`의 시험 문자열. 완전한 PEM 블록은 아니다. | 그대로 둔다. 내보내기 도구와 훅은 완전한 블록만 막는다. |
| 참조 없는 일회성 스크립트 | experiments/_*.py 14개 가운데 5개(_p7smoke, _probe_cliff, _probe_losstest, _probe_losstest_analyze, _seed_journals)는 내보내기 대상의 다른 파일이 이름으로 가리키지 않고, 실행 증거(g3/v33/evidence) 안 tar의 파일 목록에만 이름이 있다. 다른 6개(_journal, _probe_s0, _probe_trecover, _probe_trecover_rtt, _probe_v2converge, _probe_v2policy)는 다른 코드가 import하거나 이름으로 가리킨다. 나머지 3개(_probe_race, _add_drop_flags, _fix_qfec_cauchy)는 gen33에서 실행을 막았고 `tests/test_gen33_runner_isolation.py`가 rc 2로 막히는지 확인한다. | 그대로 둔다. 옮기거나 지울 때는 import, 진입점, 시험을 함께 확인한다(E37). |
| qamp 이름 충돌 | R-E final/2026-11 브랜치 75d6f9a에 qamp.go라는 파일이 8개 있다. 팀 도구 mlkem-quic-amplification/src/qamp.go, 세대 폴더 pq_afec, pq_afec_gen3, pq_afec_gen31, pq_afec_gen32, pq_afec_gen33의 experiments/quicbed/qamp.go 5개, gen33 후보 보존 폴더(J7_wire_on_L1_v2, J7_wire_v1)의 2개다. gen33 내보내기에는 그중 3개가 들어간다. gen33이 추적하는 qamp 바이너리 24개는 모두 검증 묶음 안이라 내보내지 않는다. | 이름은 바꾸지 않는다. 세대 폴더는 고치지 않고(D61), 팀 폴더 README의 7줄이 qamp를 가리키므로 이름을 바꾸면 팀 문서도 같이 바꿔야 한다. 명령과 문서에는 폴더 경로까지 적어 구분한다. |

## 경로 길이

gen33의 가장 긴 추적 경로는 218자이고, 200자를 넘는 경로가 18,368개다. 모두 검증 묶음 안이다. 내보내기 대상의 가장 긴 경로는 135자이고, R-E 안에서는 pq_afec_gen33/를 붙여 149자다. Windows에서 gen33 전체를 clone하려면 `git -c core.longpaths=true clone ...`을 쓴다. 이 설정 없이 95자 경로 아래로 clone하면 'Filename too long'이 1,370건 나며 실패했다(감사 A-E3).

## 줄 끝

gen33 루트의 .gitattributes는 내보내기 대상에 그대로 들어간다. 2026-11-02에 확장자가 `.log`, `.saved`, `.buildinfo`, `.sha256`, `.srcsha`, `.jsonl`, `.patch`, `.diff`, `.js`, `.yml`, `.csv`, `.ini`인 파일을 `text eol=lf`로 고정했다. 그 전에는 core.autocrlf=true(이 PC의 시스템 기본값)로 clone하면 LF 파일 115개가 CRLF로 바뀌었고, 그중 manifest가 sha256으로 가리키는 108개의 해시가 맞지 않았다. 새 .gitattributes를 넣은 clone에서는 115개 모두 LF로 나오고 108개 해시가 모두 맞았다([V33FIX_docs_hygiene](V33FIX_docs_hygiene.md)).
