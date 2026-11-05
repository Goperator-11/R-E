# 공개·push 전 절차

2026-11-02 KST, V33FIX 묶음 D. 이 문서는 gen33 저장소를 공개하거나 원격에 올리기 전에 밟을 절차다. 실행 허가가 아니다. 결정 D1(push 안 함), D11(비공개 전제), D40(시험용 개인키가 남은 이력의 처리)은 그대로이고, 공개 여부와 대상은 도현님이 정한다. 공개 시에는 서버명과 인계 문서도 빼야 한다(D11, Q-21).

## 이력은 다시 쓰지 않는다

gen33 이력은 `filter-repo` 같은 도구로 다시 쓰지 않는다. 커밋을 다시 쓰면 해시가 모두 바뀌는데, 이 해시들이 루프 기록의 근거로 박혀 있다. 2026-11-02 06:45에 HEAD `d67717d9b`의 커밋 122개를 대조했다. 경계가 있는 7~40자 16진 토큰이 어떤 커밋 해시의 접두사이면 그 커밋을 센다(`C:\dev\codex_handoff\v33\runs\v33fix\P\scripts\hashrefs.py`, 출력 `hashrefs.json`). 그 시각의 `C:\dev\codex_handoff\v33\state\LOOP_STATE.json`과 `JOURNAL.md`에 각각 122개 전부, `runs\MORNING_REPORT.md`에 108개, HEAD의 `g3` 추적 파일에 121개(검증 묶음 `g3/v33/validation` 밖만 보면 3개), HEAD의 `docs/*.md`에 9개, 작업 트리의 `docs/*.md`(추적 안 된 문서 포함)에 14개가 적혀 있었다. 처음 이 문서에 적은 "g3 73개"는 `git grep -I -o`로 센 값이라 검증 묶음(`.gitattributes`가 `* -text -diff`)을 binary로 보고 건너뛴 수였고, "docs 11개"는 02:05 무렵 작업 트리 기준이었다. 공개가 필요하면 아래처럼 이력 없는 새 저장소로 내보낸다. 이력 정리를 꼭 원하면 gen33 원본이 아니라 별도 사본에서만 하고, 해시를 인용한 문서를 새 해시로 다시 이어야 한다.

## 이력에 남은 것

검사 명령은 다음과 같다. 아무것도 지우거나 고치지 않고 JSON만 출력한다.

```powershell
Set-Location C:\dev\pq_afec_gen33
python -I -B tools/scrub_for_publish.py --check --history
```

2026-11-02 실행 결과다(ref는 `refs/heads/v33` 하나, 도달 가능한 객체 91,936개 가운데 blob 87,266개, 내용 3,557,316,810 B를 읽음, 약 30~40초). 같은 날 06:53에 묶음 P가 다시 돌려(HEAD `d67717d9b`, 30초, 출력 `C:\dev\codex_handoff\v33\runs\v33fix\P\scripts\scrub_history.json`) 아래 개인키·큰 blob 수치까지 모두 같은 값을 얻었다.

완전한 PEM 개인키 블록이 든 blob은 28개, 합계 1,880,048 B다. 모두 `g3/v33/validation/T1_v1/runs/T1_smoke_v1/` 아래 파일이다.

certificate_512_0.pem, certificate_513_0.pem, certificate_600_0.pem, certificate_1023_0.pem, certificate_1024_0.pem, certificate_1025_0.pem, certificate_2047_0.pem, certificate_2048_0.pem, certificate_2049_0.pem, certificate_2955_0.pem, certificate_4032_0.pem, certificate_5299_0.pem, certificate_6000_0.pem, certificate_6200_0.pem, certificate_7000_0.pem, certificate_7700_0.pem, certificate_8000_0.pem, certificate_9000_0.pem, certificate_10000_0.pem, certificate_12000_0.pem, certificate_14000_0.pem, certificate_16000_0.pem, certificate_18000_0.pem, certificate_32767_0.pem, certificate_32768_0.pem, certificate_65535_0.pem, certificate_65536_0.pem, certificate_1048576_0.pem

이 파일들은 커밋 `60a2f18f93445e3801452323b4923ed9691c8c7d`(T1, 2026-11-01 01:21:44 KST)에서 들어왔고 `3eef6a7373c9b449df77353cfe0322ca6a9b61fc`(S5, 08:35:10)에서 추적이 끊겼다. HEAD에는 없다. 고정 seed로 만든 자가서명 시험 키이고(D22) 키 사본은 `C:\dev\codex_handoff\v33\private\S5_T1_keys_v1`에 해시와 함께 있다. 그래도 공개본에는 넣지 않는다. 그 사이 커밋을 공개하면 키가 같이 나간다.

20,000,000 B를 넘는 blob은 3개이고 HEAD 경로로는 5개다. 이 파일들은 20 MB 거부 훅이 생기기 전(11-01 08:21)에 커밋됐다.

| 크기 (B) | HEAD 경로 |
|---:|---|
| 27,206,885 | `g3/v33/validation/M1_stage1/runs/M1_wire_reference_01.tsv.gz`, `M1_wire_reference_02.tsv.gz`(같은 내용) |
| 23,942,349 | `g3/v33/validation/M1_complete_inputs/handoff/runs/M1_validated_runs_v1.json`, `g3/v33/validation/M1_stage2_family/M1_validated_runs_v1.json`(같은 내용) |
| 21,038,432 | `g3/v33/validation/J7_v2/runs/J7_validated_runs_v1.json` |

## 현재 추적 파일의 개인 정보

```powershell
python -I -B tools/scrub_for_publish.py --check
```

2026-11-02 실행(약 3분 20초, 작업 트리 내용 기준, 다른 수정 묶음이 같은 시각에 파일을 고치던 중이었다)에서 텍스트 파일 102,832개를 읽었다. 사용자 경로가 든 파일 19,841개, 메일 주소가 든 파일 2개, 개인키 머리 문자열이 든 파일 3개가 나왔다. 개인키 머리 3개는 시험 문자열(`tests/test_v33_repro_tools.py`), 검사 스크립트의 정규식, 감사 기록 문장이고 실제 키가 아니다. 사용자 경로는 거의 전부 `g3/v33/validation` 아래에 있다. 처음에 "그 밖은 `git grep` 기준 22개 파일"이라고 적었으나 재현되지 않아, 같은 날 06:54에 묶음 P가 기준을 나눠 다시 쟀다(`C:\dev\codex_handoff\v33\runs\v33fix\P\scripts\userpath_counts.py`, 출력 `userpath_counts.json`). `tools/scrub_for_publish.py`의 `user_path` 정규식을 `check()`처럼 줄 단위로 적용하고 `BINARY` 확장자는 건너뛰었다. 검증 묶음 밖에서 사용자 경로가 든 파일은 HEAD `d67717d9b` 기준 20개, 작업 트리의 추적 파일 기준 20개, 추적 안 된 파일 1개(`docs/V33FIX_testbed.md`)였다. `git grep -l -I -P <같은 정규식> HEAD -- . ":(exclude)g3/v33/validation"`도 20개를 냈다. 같은 시각(06:54~06:57, 183초) 다시 돌린 `--check`는 텍스트 파일 102,832개, 사용자 경로가 든 파일 19,839개, 메일 주소 2개, 개인키 머리 3개였다(작업 트리 내용 기준, 출력 `scripts\scrub_check.json`). 같은 날 07:42에 묶음 D가 `docs/V33FIX_testbed.md`의 WSL 사용자 홈 경로를 `~`와 `<WSL 홈>`으로 바꾼 뒤 같은 스크립트로 다시 쟀다. 검증 묶음 밖에서 사용자 경로가 든 파일은 HEAD 20개, 작업 트리의 추적 파일 20개(06:54와 같은 목록), 추적 안 된 파일 0개다. 07:42~07:45(185초)에 다시 돌린 `--check`도 텍스트 파일 102,832개, 사용자 경로가 든 파일 19,839개, 메일 주소 2개, 개인키 머리 3개로 06:54 실행과 같았다(출력 `C:\dev\codex_handoff\v33\runs\v33fix\D3\userpath_counts.json`, `scrub_check.json`). `docs/S5_test_hygiene.md`는 추적 파일 20개 안에 그대로 있다. 19행의 WSL 사용자 홈 경로가 HEAD부터 있던 본문이기 때문이다. 커밋 작성자 이름과 메일도 이력에 들어 있으므로 공개본의 작성자 정보는 따로 정한다(E37).

## 새 저장소로 내보내기

전제: 묶음 D의 위생 변경(`.gitattributes`, `.gitignore`, `g3/v33/validation` 아래 로그 24개, `tools/hooks/pre-commit`, `tools/scrub_for_publish.py`)을 먼저 커밋한다. 2026-11-02 현재 HEAD `d67717d9b`에는 `tools/hooks`와 `--history` 모드가 없고 새 `.gitattributes`·`.gitignore`도 없어서, 그대로 HEAD를 내보내면 4·5단계의 `git add --chmod=+x tools/hooks/pre-commit`과 `--history` 검사가 실패한다. 커밋 여부와 시점은 도현님이 정한다. 커밋 방법은 `docs/V33FIX_docs_hygiene.md`와 `docs/S5_test_hygiene.md` 끝 절에 있다.

1. 공개할 커밋을 정한다. 커밋하지 않은 작업 트리 변경은 내보내지 않는다. 아래 예시는 `HEAD`다.

2. 코드·문서·요약 결과를 내보낸다. 검증 묶음 `g3/v33/validation`(추적 파일 112,541개, HEAD 기준 4,148,949,700 B)은 빼고, 각 묶음의 `manifest.json`과 `.gitattributes`만 따로 내보낸다. 2026-11-02에 이 두 명령을 스크래치 폴더로 돌려 보니 첫 묶음은 파일 1,205개(약 209 MB, 가장 큰 파일 17,138,231 B), 둘째 묶음은 파일 1,195개(manifest 1,150개)였다.

   ```powershell
   $out = "C:\dev\pq_afec_public_export"
   New-Item -ItemType Directory $out
   git -C C:\dev\pq_afec_gen33 archive --format=tar -o "$out\core.tar" HEAD -- . ":(exclude)g3/v33/validation"
   git -C C:\dev\pq_afec_gen33 archive --format=tar -o "$out\manifests.tar" HEAD -- ":(glob)g3/v33/validation/**/manifest.json" ":(glob)g3/v33/validation/**/.gitattributes"
   ```

3. 검증 묶음의 원자료는 공개 저장소에 넣지 않고 `C:\dev\padfec_archive`처럼 저장소 밖 보관소에 둔다. 보관소는 S1과 같은 방식(`INDEX.json`, `MANIFEST.sha256`, `tools/verify_archive.py`)으로 원본 sha256과 크기를 남긴다. 공개 저장소에는 manifest와 해시만 남아, 보관소 사본으로 묶음을 다시 검증할 수 있다. qamp 바이너리(추적 24개)도 같은 방식으로 다룬다.

4. 새 폴더에 풀고 새 저장소를 만든다. 크기·개인키 훅을 먼저 켠다.

   ```powershell
   $pub = "C:\dev\pq_afec_public"
   New-Item -ItemType Directory $pub
   tar -xf "$out\core.tar" -C $pub
   tar -xf "$out\manifests.tar" -C $pub
   git -C $pub init -b main
   git -C $pub config core.autocrlf false
   git -C $pub config core.longpaths true
   git -C $pub config core.hooksPath tools/hooks
   ```

   커밋 전에 작성자 이름·메일을 도현님이 정한 값으로 `git -C $pub config user.name`, `user.email`에 넣는다. 그 뒤 `git -C $pub add --chmod=+x tools/hooks/pre-commit`, `git -C $pub add -A`, 커밋 순서로 진행한다. 훅이 20,000,000 B를 넘는 파일이나 완전한 PEM 개인키를 막는다.

5. 새 저장소에서 다시 검사한다. `--history` 결과의 `private_key_blob_count`와 `oversize_blob_count`가 모두 0이어야 한다. `--check`가 찾은 사용자 경로·메일은 파일마다 지우거나 일반 경로로 바꿀지 정한다. 서버명과 인계 문서도 이때 뺀다(Q-21).

   ```powershell
   python -I -B "$pub\tools\scrub_for_publish.py" --check --history --root $pub
   python -I -B "$pub\tools\scrub_for_publish.py" --check --root $pub
   ```

6. 새 저장소에서 기본 시험을 돌린다. 검증 묶음을 빼면 그 묶음을 읽는 시험 파일 10개(`tests/test_v33_j1_findings.py`, `test_v33_j1_joint_driver.py`, `test_v33_j6_findings.py`, `test_v33_j6_joint_driver.py`, `test_v33_l2_joint_driver.py`, `test_v33_l3_findings.py`, `test_v33_l3_joint_driver.py`, `test_v33_l5_findings.py`, `test_v33_l5_joint_driver.py`, `test_v33_m1_fixed_report.py`)는 실패할 수 있다. 필요한 묶음만 함께 넣거나, 실패하는 시험과 이유를 공개 문서에 적는다. 이 단계는 2026-11-02에 실행해 보지 않았다.

7. push는 D1 결정이 바뀐 뒤에만 한다. 원격 이름과 대상 저장소(R-E 저장소의 새 폴더인지 새 저장소인지)도 도현님이 정한다.

## 경로 길이

gen33의 가장 긴 추적 경로는 218자이고, 200자를 넘는 경로가 18,368개다. 모두 `g3/v33/validation` 아래에 있다. 검증 묶음을 뺀 나머지의 가장 긴 경로는 79자다. Windows에서 gen33 전체를 clone하려면 `git -c core.longpaths=true clone ...`을 쓴다. 이 설정 없이 95자 경로 아래로 clone하면 'Filename too long'이 1,370건 나며 실패했다(감사 A-E3).

## 줄 끝

공개본에도 gen33의 루트 `.gitattributes`를 그대로 넣는다. 2026-11-02에 `*.log`, `*.saved`, `*.buildinfo`, `*.sha256`, `*.srcsha`, `*.jsonl`, `*.patch`, `*.diff`, `*.js`, `*.yml`, `*.csv`, `*.ini`를 `text eol=lf`로 고정했다. 그 전에는 `core.autocrlf=true`(이 PC의 시스템 기본값)로 clone하면 LF 파일 115개가 CRLF로 바뀌었고, 그중 manifest가 sha256으로 가리키는 108개의 해시가 맞지 않았다. 새 `.gitattributes`를 넣은 clone에서는 115개 모두 LF로 나오고 108개 해시가 모두 맞았다(`docs/V33FIX_docs_hygiene.md`).
