# A-integrity

## summary
보존과 무결성 쪽은 Codex 보고가 사실이다. 직접 확인한 결과는 이렇다. 보호 폴더 5개(gen-2, v3.0, v3.1, v3.2, next)는 기준선(10-30 01:24) 대비 차이 0건이다. R-E main은 6bbd11f 그대로이고 작업 트리도 깨끗하다. WSL 봉인 바이너리 5개의 sha도 같다. padfec_archive는 378/378 항목이 해시·크기 일치하고, 원본 쪽도 로컬 348개와 WSL 24개가 전부 일치한다. 봉인 해시는 R-E hygiene 브랜치를 core.autocrlf=true로 새로 clone해도 92/92 일치한다. 같은 조건에서 main을 clone하면 6/92만 맞으므로 A6 결함과 그 수정이 둘 다 실재한다. 다만 이 수정은 아직 push하지 않은 로컬 브랜치에만 있다. pytest는 Windows 작업 트리와 새 clone 양쪽에서 Codex 주장과 똑같이 나왔다(1792 통과, 2 건너뜀, 32 deselected, 하위 4513). Go는 staging 방식으로 vet 통과, 231 PASS, 2 SKIP이고 기준선은 101 PASS였다. gen33 qamp를 다른 디렉터리에서 다시 빌드해도 sha 41424293…가 그대로 나와 재현 빌드가 확인됐다. A0 수치 3묶음(p11 l0 서버 계수, RTT200 unavailable 비율, bigcert 85/535·55/484)은 gen31 코드와 원자료로 독립 재계산해 정확히 일치했다. 결함은 위생 쪽에 있다. (1) CI 마지막 단계는 build_gen33.sh가 GOPATH를 $HOME/gopath로 바꾸고 GOPROXY=off를 켜기 때문에 GitHub runner에서 실패할 가능성이 높다. 메커니즘은 로컬에서 재현했다. (2) T1 커밋이 개인키 PEM 28개를 넣었고, 이력 전체를 스캔해 보니 정확히 28개가 아직 남아 있다. (3) 저장소가 pack 1.79 GiB, HEAD 4.36 GB, 파일 113,746개로 비대하다. 바이너리 24개와 20 MB 넘는 파일 5개가 들어 있다. (4) 검증 묶음 manifest가 가리키는 .log 24개가 gitignore 때문에 빠져 있다. (5) 시험 하나가 실행될 때마다 저장소 안 experiments/state에 파일을 남긴다. 이 시험 때문에 이번 감사의 pytest 실행도 C:\dev\pq_afec_gen33\experiments\state\v33_worker_test_artifacts\source-6f17sdmv\ 에 __init__.py 3개를 만들었다(gitignore 대상이고 git status는 깨끗하다). 지우지 않고 그대로 두었으니 정리할지는 사람이 정한다. __pycache__, .pytest_cache, .git/index 변경은 없었다.

## verdict_improved
무결성·보존·시험 인프라는 v3.2-dev 기준선보다 분명히 나아졌다. 기준선에는 gen33 git 이력이 없었고, 봉인 원자료는 노트북 한 대의 원본에만 있었다. 빌드는 경로에 따라 sha가 달라졌고, R-E를 autocrlf=true로 clone하면 봉인 해시 86/92가 깨졌다. Go 시험은 101개였고 전체 pytest도 기본으로 초록이 아니었다(S5 기준 33 실패). 지금은 보존본 378항목이 원본과 전부 일치하고, 재현 빌드는 비트 단위로 같으며, 기본 pytest는 새 clone에서도 1792/4513으로 초록이고, Go는 231개다. 이 수치는 모두 직접 확인했다. 반면 새 위생 부채도 생겼다. 저장소가 1.79 GiB, 4.36 GB, 11만 파일로 커졌고, 이력에 시험용 개인키 28개가 남았고, CI 마지막 단계는 실패할 구조이고, R-E 수정은 push 전이다. 그래서 '보존과 검증 가능성은 발전했고, 공유·공개 준비도는 오히려 손이 더 가는 상태'라고 판정한다. 이 갈래에서 Codex가 숫자를 잘못 보고한 사례는 찾지 못했다. 다만 Go SKIP 2건을 적지 않은 누락은 있다.

## frame_fit
이 갈래는 인프라 작업이라 연구 주장을 직접 만들지는 않는다. 대신 주장 틀을 지키는 쪽으로 맞게 움직였다. 봉인 v3.1 원자료와 바이너리를 보존해서, 볼트의 '쓸 수 있는 말'(H1 개선 주장의 근거)을 나중에도 재검증할 수 있게 했다. A0는 이 틀의 핵심 양인 서버 수신 바이트와 parity 계수(패리티가 증폭 예산을 사는지)와 학습층 기준선 결함(85/535)을 원자료로 고정했고, 관측값과 model-world를 구분해 표시했다. README의 gen-2 판정 정정도 과장을 줄이는 방향이다. 연구 질문 밖의 새 주장은 만들지 않았고 확증 측정(D3)과 push(D1)는 하지 않았다. 반면 validation 아래 11만 파일 덤프와 복사본은 연구 서사에 보탬이 안 되면서 공유를 어렵게 만든다. 틀이 요구하는 결정적 근거인 X1(같은 바이트 패딩 대 패리티), X4, X9 측정은 이 갈래 범위 밖이라 여기서는 판단하지 않았다.

## errors

### A-E1 [medium] CI 초안의 Go 빌드 단계가 GitHub runner에서 실패할 구조 (repro=True)
ci.yml은 30행에서 go mod download를 기본 GOPATH($HOME/go)로 돌린 뒤 32행에서 build_gen33.sh를 부른다. build_gen33.sh 15행은 GOPATH가 비어 있으면 $HOME/gopath로 바꾸고, 17행은 GOPROXY=off를 켠다. setup-go v7(b7ad1dad)의 src/main.ts는 GOPATH를 export하지 않는다(PATH와 GOTOOLCHAIN만 다루고, GOROOT는 1.9 미만일 때만 export). 그래서 내려받은 모듈은 $HOME/go/pkg/mod에 있고, 빌드는 비어 있는 $HOME/gopath/pkg/mod를 보다가 네트워크 조회가 막혀 실패한다. S5는 CI를 GitHub에서 돌리지 않았다고 정직하게 적었지만, 초안이 돌아간다는 확인은 없다.

EVIDENCE: WSL에서 setup-go 환경을 흉내 냈다(HOME을 임시 디렉터리로, PATH에는 ~/goroot/bin, GOPATH 미설정, 모듈 캐시는 $HOME/go/pkg/mod). 같은 staging 디렉터리에서 기본 GOPATH로 돌린 go vet은 VET_OK였다. GOPATH=$HOME/gopath로 돌리면 'cmd/qamp/udp_linux.go:13:2: module lookup disabled by GOPROXY=off'와 rc=1이 나왔다. setup-go 소스는 raw.githubusercontent.com/actions/setup-go/b7ad1dad…/src/main.ts 57·64·125-141·192행에서 확인했다. GitHub에서 직접 돌린 결과는 아니다.

FIX: ci.yml job env에 GOPATH를 명시하거나(예: GOPATH: /home/runner/gopath를 go mod download 전에 설정), build_gen33.sh 15행을 GOPATH="${GOPATH:-$(go env GOPATH)}"로 바꾼다.

### A-E2 [medium] T1이 시험용 개인키 PEM 28개를 커밋했고 이력에 남아 있음 (repro=True)
A6-16과 카드 S5.9의 원칙은 '시험용 개인키는 저장소 밖'이다. 그런데 T1 커밋 60a2f18f9(11-01 01:21)가 인증서와 개인키를 한 파일에 담은 certificate_*.pem 28개를 g3/v33/validation/T1_v1/runs/T1_smoke_v1/에 넣었다. 파일 이름이 .gitignore의 *.key 규칙을 비껴갔다. S5 커밋 3eef6a737(08:35)이 git rm으로 추적을 끊고 .gitignore에 certificate_*.pem을 추가했지만 60a2f18f9부터 S5 직전까지의 커밋에는 키가 그대로 있다. S5와 D40이 이 사실을 스스로 밝혔으므로 거짓 보고는 아니다. 원격이 없고(remote 0개), D22에 따르면 고정 seed로 만든 시험 키라 당장 노출 위험은 낮다. 다만 push나 공개 전에는 이력을 다시 써야 한다.

EVIDENCE: git rev-list --objects --all로 blob 87,266개를 뽑아 PEM 개인키 정규식으로 검사했다. 완전한 개인키 블록이 든 blob은 28개였고 전부 T1_smoke_v1/certificate_*.pem이었다. A1의 ML-DSA root/intermediate/leaf.pem은 인증서만 들어 있었다. 추가 커밋은 git log --diff-filter=A, 제거 커밋은 --diff-filter=D로 확인했다(60a2f18f9, 3eef6a737).

FIX: push나 공개 전에 git filter-repo로 해당 경로를 이력에서 지우거나, 키가 없는 새 공개용 저장소를 만든다(D40 결정 사항). 키를 별도 파일로 내는 harness는 출력 경로를 저장소 밖으로 고정한다.

### A-E3 [medium] gen33 저장소 비대: 파생 자료·바이너리·복사본 대량 커밋 (repro=True)
추적 파일 113,746개 가운데 112,541개가 g3/v33/validation 아래 있다. HEAD 트리는 4,358,113,526 B이고 pack은 1.79 GiB다. */handoff/* 아래 codex_handoff 실행물 사본이 20,782개(1.15 GB)이고, 같은 blob이 여러 경로에 있는 항목이 26,629개(805 MB)다. qamp 바이너리가 24개(322 MB, 고유 blob 21개) 커밋됐다. 20 MB 넘는 파일 5개(최대 27,206,885 B, M1_wire_reference_01/02.tsv.gz 등)는 S5의 20 MB pre-commit 훅이 생기기(11-01 08:21) 전에 들어갔다. S2 통합 계획과 MORNING_REPORT 어디에도 저장소 크기 문제가 없다. 상대 경로가 최장 218자여서, Windows에서 core.longpaths 없이 짧지 않은 경로(약 41자 초과)로 clone하면 실패한다.

EVIDENCE: git count-objects -vH의 size-pack은 1.79 GiB였다. git ls-tree -r -l HEAD로 디렉터리별·확장자별 합계를 냈다. 첫 clone(스크래치 경로 95자)은 'Filename too long' 1,370건, rc=128로 실패했다. core.longpaths=true로 다시 clone하니 성공했다.

FIX: 검증 묶음과 바이너리는 padfec_archive 같은 외부 보관소로 옮기고 저장소에는 manifest와 해시만 둔다. 공유나 push 전에는 filter-repo로 정리한 공개용 이력을 만든다. 경로 깊이도 줄인다.

### A-E4 [low] 검증 묶음 manifest가 가리키는 .log 24개가 git에 없음 (repro=True)
.gitignore의 *.log 때문에 g3/v33/validation/J7_checkpoint_v1/runs(16개), E12_v1/runs(7개), L2_unit/runs(1개)의 로그가 추적되지 않았다. 그런데 커밋된 manifest.json에는 이 파일들의 stored_path와 sha256이 들어 있다(예: J7_checkpoint_v1/manifest.json 134-137행, runs/J7_build_01.log). 새 clone에서는 이 묶음을 완전하게 검증할 수 없다. 원본은 작업 트리와 C:\dev\codex_handoff\v33\runs에 남아 있다. 같은 validation 아래 다른 .log 590개는 강제로 추가돼 있어 처리가 일관되지 않다.

EVIDENCE: git ls-files --others --ignored --exclude-standard -- g3로 24개 전부 .log임을 확인했다. 각 파일의 sha256을 git grep HEAD -- g3/v33/validation으로 찾았고 24개 모두 manifest에서 2~7회 참조됐다.

FIX: 24개를 git add -f로 추가하거나, manifest에 '저장소 밖 보존' 표시를 단다.

### A-E5 [low] 기본 pytest가 실행마다 저장소 안에 파일을 남김 (repro=True)
tests/test_v33_policy_worker.py 139행 test_read_only_audit_blocks_import_time_write가 ROOT/experiments/state/v33_worker_test_artifacts/source-XXXX/ 아래 afec, padfec, padfec3의 __init__.py를 만들고 지우지 않는다. 감사 전에 이미 이런 디렉터리가 61개 쌓여 있었다. 이번 감사의 Windows 실행도 source-6f17sdmv(파일 3개)를 새로 만들었다. gitignore 대상이라 git status에는 나오지 않는다. 다만 보호·읽기 전용 검증 중에 저장소에 쓰기가 생긴다. S5의 '임시 파일 삭제를 보존 어댑터로 옮김' 방침과 맞물린 결과로 보인다.

EVIDENCE: pytest 전후로 gen33 전체를 snapshot해 비교했다. 새 파일은 정확히 3개였고 모두 experiments\state\v33_worker_test_artifacts\source-6f17sdmv\{afec,padfec,padfec3}\__init__.py였다. 그 밖의 변경과 __pycache__, .pytest_cache 생성은 0이었고 .git/index mtime도 그대로였다. 이 시험은 W1 커밋 cbde906ba에서 들어왔다.

FIX: fixture를 tempfile.mkdtemp()처럼 저장소 밖에 만들고 tearDown에서 지운다.

### A-E6 [low] S2 clone 검사 사본을 스크래치가 아닌 C:\dev\R-E-wt에 남김, 기존 .sh 규칙 행 삭제 (repro=True)
카드 S2.2는 clone을 스크래치에 만들라고 했다. Codex는 C:\dev\R-E-wt\hygiene-clone-check(전체 clone, autocrlf=true)를 만들어 그대로 두었고, S2_hygiene.md의 확인 명령도 그 경로를 가리킨다. 그 결과 R-E-wt에는 카드에 없던 세 번째 폴더가 생겼다. hygiene 브랜치의 .gitattributes는 main에 있던 'mlkem-quic-amplification/src/*.sh text eol=lf' 행을 지우고 '* text=auto eol=lf'로 바꿨다. 텍스트로 판별되는 .sh에서는 동작이 같지만 원래의 명시 규칙은 사라졌다.

EVIDENCE: ls C:/dev/R-E-wt의 결과는 hygiene, hygiene-clone-check(07:53:52), next다. git -C C:/dev/R-E diff --stat main hygiene/2026-10-30의 .gitattributes는 8줄 추가, 1줄 삭제다. git show main:.gitattributes로 원래 행을 확인했다.

FIX: 검사가 끝난 clone은 지우거나 스크래치로 옮기고, 확인 명령은 새 clone을 만드는 절차로 바꾼다. 원래 .sh 규칙 행은 다시 넣는다.

### A-E7 [low] WSL ~/quicbed_gen33/bin의 go_race.txt가 현재 바이너리보다 오래됨, stage 누적 3.9 GB (repro=True)
build_gen33.sh는 --race 없이 실행하면 bin/go_race.txt를 지우지 않는다. 그래서 07:03 빌드의 race 결과가 08:19에 만든 현재 qamp(srcsha 9798aa22…) 옆에 그대로 있어, 현재 소스가 race를 통과했다고 오해할 수 있다. S5 보고서가 race 통과를 주장하지는 않았다. 빌드마다 stage를 보존하는 설계여서 stage 디렉터리 53개, 3.9 GB가 쌓였다.

EVIDENCE: ls --time-style=full-iso /home/scien/quicbed_gen33/bin 결과 go_race.txt는 2026-11-01 07:03:52, qamp·qamp.srcsha는 08:19:50이었다. du -sh /home/scien/quicbed_gen33은 3.9G다.

FIX: 빌드를 시작할 때 bin의 이전 go_race.txt를 지우거나 이름에 srcsha를 붙인다. 오래된 stage에는 보존 한도를 둔다.

### A-E8 [low] 'Go 시험 231개 통과' 보고에서 기본 SKIP 2건 누락 (repro=True)
TestHoldPythonReadFromReference와 TestUDPHoldPythonReadBatchReference는 M1_REFERENCE_GZIP이 없으면 건너뛴다(qamp_hold_test.go 595행 t.Skip, 'full wire gate'). S5와 MORNING_REPORT는 'Go 231'만 적어서, M1 전체 와이어 관문까지 기본 시험으로 돈다고 읽힐 수 있다. Codex 자신의 go_test.txt에도 SKIP 2건이 있다.

EVIDENCE: staging 사본에서 go test -count=1 -v를 돌린 결과는 '--- PASS' 231, '--- SKIP' 2, '--- FAIL' 0이었다. /home/scien/quicbed_gen33/bin/go_test.txt에도 SKIP 2건이 있다.

FIX: 보고에 'PASS 231, SKIP 2(M1_REFERENCE_GZIP 필요)'로 적고, 와이어 관문을 돌리는 별도 명령을 문서화한다.

## changes
- gen33 git 저장소를 새로 만들었다. 브랜치 v33, 기준선 90859b973(10-30 01:28), HEAD d67717d9b(11-01 08:52), 커밋 122개이고 작성자는 전부 jeongdohyun0306 <scientistdo314@gmail.com>(S0 카드 지시), 원격은 없다. 기준선 트리는 gen32와 비교해 199개 파일이 원본 바이트로 같고, 다른 것은 build_gen32.sh가 build_gen33.sh로 바뀐 것과 g3/gen33_parity_baseline.json 추가뿐이다. experiments/pki 키 26개는 처음부터 제외됐다.
- S1: C:\dev\padfec_archive를 만들었다. 378항목(비압축 264, gzip 114), 원본 782,982,028 B, 저장 307,939,606 B, INDEX.json, MANIFEST.sha256, tools/verify_archive.py가 있다. WSL /home/scien/frozen/에 g2_d98b05d7, g3_d519b331, g3b_ad5246f3, g3c_6baf2b52, gen32_85f54cf5 다섯 폴더를 읽기 전용으로 두었다.
- S2: R-E에 로컬 브랜치 hygiene/2026-10-30을 만들었다. 59d2833은 루트 .gitattributes를 '* text=auto eol=lf'와 바이너리 패턴으로 바꾸고, 85b00b6은 README gen-2 판정을 '18 통과, 6 실패, p6 stale'로 고치고 tools/verify_seals.py를 추가했다. archive/next-2026-09-08(2d5938b)에는 pq_afec_next 290파일을 보관했다. 로컬 주석 태그 4개(gen2-frozen-4bab4a5→4bab4a5, gen2-fix-73aa420→73aa420, v3.1-stage3·v3.2-dev→6bbd11f)를 달았고, worktree C:\dev\R-E-wt\hygiene와 \next, clone 폴더 hygiene-clone-check를 만들었다. main과 원격은 그대로다.
- S3: genconfig.json(gen_id v3.3-dev, ~/quicbed_gen33/bin/qamp, /tmp/qamp_gen33/qamp)을 추가하고, build_gen33.sh에 -trimpath -buildvcs=false와 qamp.buildinfo 기록을 넣었다. 관문과 pipeline은 genconfig를 읽고, tests/test_no_foreign_paths.py를 추가했다.
- S5: pytest.ini를 추가했다(testpaths=tests, historical marker, 기본 실행에서 32개 deselected). .github/workflows/ci.yml(ubuntu, Python 3.14.4, Go 1.26.6, actions는 SHA로 고정), requirements.txt(pytest 9.0.3, matplotlib 3.10.8, cryptography 50.0.1, scipy 1.18.1), tools/doctor.py, bootstrap_wsl.sh, precommit_size.py, lint_ast.py, raw_io.py, runtime_fingerprint.py, scrub_for_publish.py를 추가했다. .git/hooks/pre-commit은 11-01 08:21에 설치됐다. afec/rs.py는 r=1일 때 Cauchy 계수 대신 전부 1(XOR)을 쓴다. T1 개인키 PEM 28개는 git rm하고 C:\dev\codex_handoff\v33\private\S5_T1_keys_v1로 옮겼으며, .gitignore에 *.key와 certificate_*.pem을 추가했다.
- 시험: tests 파일이 38개에서 109개로 늘었다. 삭제된 시험 파일은 없다. 원래 있던 Python 시험 14개와 Go 시험 8개 파일이 수정됐는데, 주로 L1 의미 변경(skip/shield 대신 범주 증거)에 맞춘 것이다. Go 시험은 101개에서 231개(+SKIP 2)로 늘었다.
- A0: g3/v33/evidence/에 스크립트 7개, common.py, EVIDENCE.md, JSON 7개, server_accounting.csv(182행), source_precision_checks.json을 추가했다. 출력 경로는 gen33나 v33 루프 폴더로 제한된다.
- 루프 산출물이 C:\dev\codex_handoff\v33\runs에 7.6 GB(파일 6,680개), WSL ~/quicbed_gen33에 3.9 GB(stage 53개) 쌓였다.

## improvements
- [strong] 보호 폴더와 봉인 바이너리가 루프 동안 그대로 유지됨 :: guard_check.py는 실패 시 GUARD_FAIL.txt를 쓰므로 그 로직을 쓰기 없이 다시 돌렸다(스크래치 guard_ro.py). 기준선 대비 차이는 pq_afec 667/667, gen3 396/396, gen31 403/403, gen32 226/226, next 290/290 모두 0이었다. R-E main 6bbd11f와 status 0줄도 같았고, WSL 5개 sha도 SAME이었다. 볼트 경고 7건은 도현님과의 Claude 세션 노트 6개와 이번 감사 노트 1개이며 Codex가 쓴 것이 아니다.
- [strong] 원자료·바이너리 보존본이 완전히 검증 가능해짐 (S1) :: INDEX.json 378항목 전부에 대해 저장 바이트 sha, gzip을 메모리에서 푼 원본 sha와 크기, MANIFEST.sha256 행이 모두 일치했다. 원본 위치에서 다시 해시한 결과도 로컬 348/348, WSL 24/24(sha256sum -c OK) 일치했다. frozen 바이너리 5개의 sha와 srcsha도 INDEX와 같았다.
- [strong] R-E 새 clone에서 봉인 해시가 깨지는 A6 결함을 고침 (로컬 브랜치 한정) :: core.autocrlf=true로 clone했을 때 main은 92개 중 6개만 맞았고 hygiene/2026-10-30은 92/92(stage3 31+14, stage2 29+9, stage0 3+6) 맞았다. 원본 gen31·gen3 폴더 대비로도 45/45, 38/38, 9/9였다. GitHub에는 아직 반영되지 않았다(ls-remote에는 main 6bbd11f만 있음).
- [strong] gen33 Go 바이너리의 비트 단위 재현 빌드 :: WSL 임시 디렉터리에서 같은 소스로 go build -trimpath -buildvcs=false를 실행하니 sha256이 41424293588fde08…로 /home/scien/quicbed_gen33/bin/qamp와 같았다. 소스 지문을 다시 계산한 값도 9798aa22…로 설치본 qamp.srcsha와 같았다.
- [strong] 시험이 초록이고 새 clone에서도 같은 결과 :: Windows 작업 트리와, core.longpaths로 새로 clone한 사본 양쪽에서 '1792 passed, 2 skipped, 32 deselected, 4513 subtests passed'가 나왔다(85.8초, 94.8초). gitignore 대상 파일이 없는 clean checkout에서도 통과한다는 뜻이다. Go는 기준선 101 PASS에서 현재 231 PASS + SKIP 2로 늘었고 vet도 통과한다.
- [strong] A0 감사 근거 수치를 원자료에서 재현할 수 있게 됨 :: gen31 코드와 원자료 저널로 독립 스크립트(a0_recheck.py)를 짜서 다시 계산했다. p11_2955_l0은 g2auto의 클라이언트/서버 parity 4532/8579와 연결당 11000.8575 B, g3auto의 7991/7991과 10545.550625 B가 나왔다. RTT200 run1은 unavailable 비율이 99.3333%, 99.4889%, 99.3556%이고 g3auto의 Initial 5개는 4500행, parity 9개는 4490행이었다. S_bigcert 15% (0,3,1)은 run1 85/535, run2 55/484였다. 모두 EVIDENCE.md와 정확히 같다.
- [moderate] gen33 변경을 되돌릴 수 있는 git 이력과 충실한 기준선 :: 기준선 커밋 90859b973의 199개 파일이 gen32 원본 바이트와 같았고, 허용된 두 차이만 있었다. 이후 변경은 커밋 122개로 추적된다.
- [moderate] R-E README의 gen-2 판정이 원자료에 맞게 정정됨 (로컬 브랜치) :: fixloop.log 마지막 바퀴(2026-10-02 04:36:15)는 '통과 18'이고, loop2.json에서 failed는 p8, p10, p15, p17, p18, p20이다. fixloop_triage.json의 p6은 'stale, 통과로 세면 안 된다'다. 18 통과, 6 실패, p6 미실행 문장이 이와 맞는다.
- [moderate] pq_afec_next 미합류 사본의 바이트 보존 (D6 준수) :: archive/next-2026-09-08 트리와 C:\dev\pq_afec_next를 ls-tree -z로 대조하니 290/290 파일, 25,111,699 B가 원본 바이트로 같았다. main에 merge하지 않았다.
- [moderate] Python RS 코덱의 단일 패리티가 전송 형식(XOR)과 같아짐 :: afec/rs.py diff에서 r==1이면 self.cauchy=[[1]*k]이다. 전부 1인 행은 단일 소실 복구 조건을 만족하고, 관련 시험도 기본 pytest에 들어 있어 통과한다.
- [weak] CI 초안의 의존성 고정은 유효함 :: git ls-remote 결과 checkout v7.0.1은 3d3c42e5…, setup-python v7.1.0은 6d4fd22b…, setup-go v7.0.0은 b7ad1dad…로 커밋 고정값과 같다. requirements의 고정 버전 4개는 S5_linux_dependencies_01.log에서 실제로 내려받아졌다. 다만 A-E1 때문에 마지막 단계는 실패할 가능성이 높다.

## checked_but_ok
- guard_check.py는 --check에서 위반이 있을 때 state\GUARD_FAIL.txt를 쓴다. 그래서 같은 로직을 쓰기 없이(git --no-optional-locks) 스크래치에서 두 번 돌렸고 두 번 다 보호 위반 0이었다. 한계도 있다. guard는 size와 mtime만 보고, .git 내부, padfec_archive, ~/frozen은 대상이 아니다.
- R-E push 흔적은 없다. git ls-remote origin에는 HEAD와 refs/heads/main=6bbd11f만 있다. origin/main reflog의 마지막 'update by push'는 2026-10-29 14:40:53이다. 태그 4개와 브랜치 2개는 로컬에만 있다(D1 준수). 태그 대상 커밋은 카드와 같고, gen2-frozen 메시지의 srcsha b1816779…는 WSL quicbed/bin/qamp.srcsha 내용과 같다.
- S2의 주장(새 clone 92해시, next 290파일·25,111,699 B, README 18/6/p6 stale)은 전부 직접 재확인했다.
- S0 기준선 커밋은 gen32와 충실하게 같다(199파일 원본 바이트 일치, 허용 차이 2개).
- gen33의 줄바꿈 처리: CRLF/mixed 800파일은 -text로 원본 바이트가 보존된다. i/lf w/crlf인 3파일 가운데 L2_joint_plan_v1.stdout.txt는 manifest에 source_sha256과 stored_sha256이 둘 다 적혀 있어 의도된 처리다. 명시 LF 속성이 없는 텍스트 파일은 115개(.log 82, .sha256 5 등)뿐이다.
- 개인키 스캔에서 A1의 ML-DSA PEM(root, intermediate, leaf, leaf_public)은 인증서만 들어 있었다. 헤더 문자열만 든 blob 3개는 시험 코드와 기록 파일이다.
- pre-commit 훅 설치 이후 커밋(S5 3eef6a737, A1 d67717d9b)의 최대 blob은 1.66 MB로 20 MB 정책을 지켰다.
- 기존 시험 파일은 하나도 삭제되지 않았다. historical 32개는 deselected로 남았고 삭제되지 않았다. 수정된 Go 시험의 Fatal 조건 변화는 L1 의미 변경(LegacySkip 진단)에 맞춘 것으로 보이며 단순히 기준을 낮춘 흔적은 아니다. 다만 학습층 판단은 다른 갈래 몫이다.
- experiments/quicbed에서 바로 'go vet ./...'를 돌리면 main 중복 선언으로 실패한다. 이는 기준선부터 있던 구조(build 스크립트 staging 필요)이고 회귀가 아니다. staging 방식으로는 vet이 통과한다.
- pytest 실행 뒤 gen33에 __pycache__와 .pytest_cache는 0개였고 .git/index mtime(11-01 08:52:22)도 바뀌지 않았다. gen31 모듈은 -B와 dont_write_bytecode로 import했고, 재검사에서도 gen31 차이는 0이었다.
- prompt\TASKS.md, CONTEXT.md, LOOP_PROMPT.md, findings\, tools\의 mtime은 모두 루프 시작(10-30 01:28) 전이다. 카드 파일을 고친 흔적은 없다.
- S5 카드의 build_server.sh 고정 문제(A6-14)는 빌더가 GOFLAGS=-mod=readonly, GOTOOLCHAIN=local, GOPROXY=off를 쓰는 것으로 처리돼 있다. 로컬 WSL에서는 이 설정으로 vet, test, build가 통과한다.
- 가장 긴 상대 경로는 218자로, 원래 위치 C:\dev\pq_afec_gen33에서는 260자 제한 안에 든다.

## VERIFY

- A-E1 (error): **confirmed** sev=low :: 재현됐다. setup-go 소스(b7ad1dad)는 GOPATH를 export하지 않고, ubuntu-24.04 runner 이미지 README에도 GOPATH/GOMODCACHE 환경변수가 없다. go mod download는 기본 GOPATH($HOME/go)에 모듈을 받고, build_gen33.sh 15행은 GOPATH를 $HOME/gopath로 바꾸며 17행은 GOPROXY=off라서 빌드가 실패한다. 심각도는 low로 낮춘다. Codex가 S5_test_hygiene.md와 MORNING_REPORT 334행에서 'CI는 미실행 초안'이라고 밝혔고, remote가 0개라 지금 돌 일이 없으며, 고치는 데 한 줄이면 되고, 연구 수치에는 영향이 없다. || WSL 임시 HOME(GOPATH 미설정, PATH=~/goroot/bin, GOFLAGS=-mod=readonly GOTOOLCHAIN=local)에서 go env GOMODCACHE=$HOME/go/pkg/mod를 확인했다. go mod download는 rc=0이었고, 이어서 bash build_gen33.sh(OUT만 임시로 바꿈)는 build_rc=1에 'cmd/qamp/udp_linux.go:13:2: module lookup disabled by GOPROXY=off'를 냈다. 같은 사본을 GOPATH=$HOME/go로 다시 돌리면 build_rc=0이 나와 감사자의 수정안이 맞다는 것도 확인했다. WebFetch: setup-go main.ts의 exportVariable은 GOROOT(1.9 미만일 때만)와 GOTOOLCHAIN뿐이고, addBinToPath는 'go env GOPATH'를 읽어 bin을 PATH에 넣기만 한다. runner-images Ubuntu2404-Readme.md에는 Go 관련 환경변수가 없다.

- A-E2 (error): **confirmed** sev=low :: 사실관계는 모두 맞다. 다만 medium은 과하다. D22에 따르면 고정 seed로 만든 시험용 자가서명 키이고 어떤 신뢰 체인에도 들어가지 않는다. remote는 0개이고, Codex가 D40과 E37로 스스로 밝혀 공개 전 처리를 사람 결정으로 넘겼다. 실제 위험은 공개나 R-E 통합 전에 이력을 정리해야 한다는 위생 부담뿐이다. || git cat-file --batch-all-objects로 blob 87,483개(도달 불가 2개 포함)의 내용을 전부 훑었다. BEGIN...PRIVATE KEY가 든 blob은 36개였고, 그중 실제 키 블록은 T1_smoke_v1/certificate_*.pem 28개뿐이다(예: certificate_512_0.pem은 CERTIFICATE와 PRIVATE KEY 블록을 함께 담음). 나머지는 정규식 문자열, 시험 fixture('YWJjZA=='), A6-16 인용문이었다. 60a2f18f9(11-01 01:21:44)가 28개를 추가했고 3eef6a737(08:35:10)이 삭제했다. 지금 .gitignore 27행은 certificate_*.pem이고, git remote는 0개다. DECISIONS_NEEDED.md 119행 D40에 'PEM28개가 개인키를 포함', '기존 커밋에는 키가 남으므로'라고 적혀 있다.

- A-E3 (error): **confirmed** sev= :: 감사자가 낸 숫자를 모두 같은 값으로 재현했다. 루프 지시(LOOP_PROMPT 70행)는 요약 JSON을 g3/v33/results/에 커밋하라고 했을 뿐 11만 개 파일 커밋을 요구하지 않았으므로, 비대화는 Codex가 선택한 결과다. MORNING_REPORT와 S2_consolidation_plan에도 저장소 크기 언급은 없다(E37은 경로·메일·키 정리만 다룬다). || git count-objects -vH의 size-pack은 1.79 GiB다. git ls-tree -r -l HEAD 집계 결과는 다음과 같다. 파일 113,746개, 합계 4,358,113,526 B, validation 112,541개, /handoff/ 20,782개(1,150,259,705 B), 중복 blob의 추가 경로 31,819-5,190=26,629개(804,570,577 B), qamp 24개(322,411,832 B, 고유 21개), 20 MB 초과 5개(최대 27,206,885 B, M1_wire_reference_01/02.tsv.gz), 최장 경로 218자, 200자 초과 경로 18,368개. 큰 파일 추가 시각은 21cd5334e 10-31 22:36, 957dbbd4a 10-31 21:50, dd630f270 11-01 00:11이고, .git/hooks/pre-commit은 11-01 08:21이다. MORNING_REPORT.md와 S2_consolidation_plan.md를 GiB, 용량, 크기, count-objects로 검색하면 0건이다. 감사자 clone.log의 'Filename too long'은 1,370건이다.

- A-E4 (error): **confirmed** sev= :: ignore된 파일은 정확히 24개이고 전부 .log다. 24개 모두 커밋된 manifest가 sha256으로 참조한다. || git ls-files --others --ignored --exclude-standard -- g3 결과는 24개(E12_v1 7, J7_checkpoint_v1 16, L2_unit 1)다. 각 파일의 sha256을 git grep HEAD -- g3/v33/validation으로 찾으니 2회 7개, 5회 15개, 7회 2개였다. J7_checkpoint_v1/manifest.json 134-137행 stored_path는 runs/J7_build_01.log다. 추적 중인 validation 아래 .log는 590개다.

- A-E5 (error): **partly** sev= :: 결함 자체는 맞다. 시험 fixture가 ROOT/experiments/state/v33_worker_test_artifacts 아래에 mkdtemp로 디렉터리를 만들고 지우지 않는다(def는 138행, 쓰기 경로는 139행). 다만 '감사 전에 이미 61개'라는 숫자는 틀렸다. 지금 source-* 디렉터리가 61개이고 그중 11-02 생성분은 감사자 실행이 만든 source-6f17sdmv 하나뿐이므로, 감사 전에는 60개였다. 또 감사자가 gen33 작업 트리에서 직접 pytest를 돌려 읽기 전용 규칙을 어기고 파일 3개를 남겼다(감사자도 밝혔다). 그 3개는 지금도 남아 있다. || ls -la --time-style=full-iso experiments/state/v33_worker_test_artifacts의 날짜별 개수는 10-30 8, 10-31 28, 11-01 25, 11-02 1(source-6f17sdmv, 00:08:44)이고 source-* 합계는 61이다. find -newermt '2026-11-01 23:00'로 찾은 새 파일은 source-6f17sdmv/{afec,padfec,padfec3}/__init__.py 3개뿐이다. git log -S로 보면 이 시험은 cbde906ba(10-30 02:39 W1)에서 들어왔다. 나는 scratch clone에서 pytest를 돌렸고, 전후 snapshot 결과 gen33, codex_handoff, R-E, padfec_archive 모두 diff 0이었다.

- A-E6 (error): **confirmed** sev= :: 카드 S2.2는 clone을 스크래치에 만들라고 했는데 Codex는 C:\dev\R-E-wt\hygiene-clone-check에 만들어 남겼다. S2_hygiene.md 11행과 40행도 그 경로를 가리킨다. .sh 규칙 행이 빠진 것은 사실이지만 기능 차이는 없다. autocrlf=true로 clone한 hygiene 브랜치에서 4개 .sh가 모두 attr/text=auto eol=lf, w/lf, CR 0바이트였다. 심각도 low는 적절하다. || ls -la C:/dev/R-E-wt 결과는 hygiene(07:53:40), hygiene-clone-check(07:53:52, autocrlf=true, origin=C:\dev\R-E), next다. git show main:.gitattributes는 'mlkem-quic-amplification/src/*.sh text eol=lf' 한 줄이고, hygiene 브랜치 쪽은 '* text=auto eol=lf'와 binary 6줄이다. 스크래치 clone에서 git ls-files --eol 'mlkem-quic-amplification/src/*.sh'를 돌리면 4개 모두 i/lf w/lf였다.

- A-E7 (error): **partly** sev=info :: 스크립트의 잠재 결함은 맞다(61-64행이 이전 go_race.txt를 지우지 않음). stage 53개, 3.9G도 맞다. 그러나 '현재 소스가 race를 통과했다고 오해할 수 있다'는 지금 상태에는 해당하지 않는다. go_race.txt를 만든 07:02 빌드(stage.Pr7HTF)의 srcsha가 현재 qamp와 같은 9798aa226a1a이고, 바이너리 sha256도 41424293…로 같다. 그러므로 bin의 race 결과는 실제로 현재 소스에 대한 결과다. || WSL에서 ls -td stage.*로 각 build_record/qamp.srcsha를 확인했다. stage.mBIfxw(08:19)는 9798aa226a1a에 race=n, stage.Pr7HTF(07:02)는 9798aa226a1a에 race=y였다. 두 stage의 qamp.sha256은 모두 41424293588fde08…다. bin/go_race.txt 내용은 'WORK=.../stage.Pr7HTF/...', cmd/qamp ok 85.706s, padfec-local-hook ok다. du -sh는 3.9G, stage.* 개수는 53이다.

- A-E8 (error): **confirmed** sev= :: S5_test_hygiene.md 19행 'Go 시험 231개'와 MORNING_REPORT 78·207행 'Go231'에는 SKIP 2건이 적혀 있지 않다. 231 PASS 자체는 정확하므로 누락 수준의 low가 맞다. || WSL 임시 사본으로 build_gen33.sh를 돌리니 PASS=231, SKIP=2, FAIL=0이었다(GOPATH만 지정). /home/scien/quicbed_gen33/bin/go_test.txt에도 '--- SKIP: TestHoldPythonReadFromReference', '--- SKIP: TestUDPHoldPythonReadBatchReference'가 있다.

- 보호 폴더와 봉인 바이너리가 루프 동안 그대로 유지됨 (improvement): **confirmed** sev= :: guard_check.py의 쓰기 로직(GUARD_FAIL.txt, --init)을 뺀 사본으로 다시 확인했다. 기준선은 루프 시작 전(10-30 01:24:54)에 찍혔다. 보호 세대 폴더 5개에는 .git이 없으므로 guard가 .git을 빼고 본 것은 빈틈이 아니다. || 스크래치 guard_ro.py 결과 pq_afec 667/667, gen3 396/396, gen31 403/403, gen32 226/226, next 290/290이 모두 diff 0이었다. R-E HEAD는 6bbd11f8e7eb main이고 status도 같았으며, WSL 5개는 SAME이었다. 볼트 경고 7건의 파일 시각은 10-31 10:43, 12:10 등 도현님 세션 노트와 11-01 23:54 감사 노트였다. find로 C:\dev\R-E\.git의 루프 기간 변경을 보면 objects, worktrees, refs, logs뿐이고 config와 packed-refs는 바뀌지 않았다.

- 원자료·바이너리 보존본이 완전히 검증 가능해짐 (S1) (improvement): **confirmed** sev= :: 표본이 아니라 378개 전부를 확인했다. MANIFEST.sha256은 gzip 항목을 logical_path와 원본 sha로 적는 형식이다. || archive_check.py 결과 378개 모두 stored sha와 크기가 일치했고, gzip 114개를 메모리에서 풀어 본 원본 sha와 크기도 일치했다. MANIFEST(logical_path, original_sha256)는 378/378, 원본 위치 재해시는 Windows 348/348이었고, WSL은 sha256sum -c로 24/24 OK, rc 0이었다. /home/scien/frozen 5개의 sha와 srcsha도 INDEX.binaries와 같다.

- R-E 새 clone에서 봉인 해시가 깨지는 A6 결함을 고침 (로컬 브랜치 한정) (improvement): **confirmed** sev= :: 숫자를 그대로 재현했다. push되지 않았다는 점도 확인했다. || core.autocrlf=true로 clone한 뒤 hygiene 브랜치의 tools/verify_seals.py를 돌리면 main은 FAIL 92 중 6, hygiene/2026-10-30은 PASS 92/92(stage3 31+14, stage2 29+9, stage0 3+6)였다. git ls-remote origin에는 HEAD와 refs/heads/main 6bbd11f만 있다. R-E reflog의 마지막 'update by push'는 10-29 14:40:53이다.

- gen33 Go 바이너리의 비트 단위 재현 빌드 (improvement): **confirmed** sev= :: 다른 HOME, 다른 stage 경로, 새 모듈 캐시에서 빌드해도 같은 바이너리가 나왔다. || WSL 임시 HOME에서 GOPATH=$HOME/go로 build_gen33.sh를 돌린 결과물의 sha256은 41424293588fde08d02a8821b4945ac07f4d0016c61480e0ee2db78936323dae로, 설치본 qamp.sha256과 같다. 원본 /mnt/c/dev/pq_afec_gen33/experiments/quicbed에서 스크립트와 같은 방식으로 다시 계산한 srcsha는 9798aa226a1a…로 설치본과 같다.

- 시험이 초록이고 새 clone에서도 같은 결과 (improvement): **confirmed** sev= :: 이 PC의 기본값(시스템 core.autocrlf=true)으로 clone한 사본에서도 같은 결과가 나왔다. 다만 32개 deselect 가운데 3개는 v3.2-dev에서 물려받은 실패가 아니다(verdict_improved 참고). || git -c core.longpaths=true clone --no-hardlinks(autocrlf=true, status 0줄) 뒤 'python -I -B -m pytest -q -p no:cacheprovider'를 돌리니 '1792 passed, 2 skipped, 32 deselected, 4513 subtests passed in 83.18s'였다. 실행 전후 보호 폴더 snapshot diff는 0이다. tools/lint_ast.py는 PASS(311 files)다. Go는 gen32 bin/go_test.txt PASS 101에서 현재 PASS 231과 SKIP 2로 늘었다(Test 함수 수도 101에서 233).

- A0 감사 근거 수치를 원자료에서 재현할 수 있게 됨 (improvement): **confirmed** sev= :: EVIDENCE.md 스크립트를 쓰지 않고 독립 스크립트로 두 묶음을 다시 계산했다. || a0_mine.py로 gen31 p31_run1_D_p11_2955_l0_units.jsonl을 계산하면 g2auto는 서버 parity 8579, 클라이언트 4532, bytes_in/1600=11000.8575이고, g3auto는 7991, 7991, 10545.550625다. p31_run1_S_rtt200_units.jsonl의 path_rtt_source unavailable 비율은 g2auto 4470/4500=99.3333%, g3auto 4477/4500=99.4889%, g3fixL2 4471/4500=99.3556%다. 둘 다 EVIDENCE.md 표와 같다.

- gen33 변경을 되돌릴 수 있는 git 이력과 충실한 기준선 (improvement): **confirmed** sev= :: 카드 S0.1이 허용한 차이만 있다. || base_cmp.py에서 90859b973 트리 201개 가운데 199개가 gen32 바이트와 같았다(git blob 해시 비교). 나머지 2개는 추가된 build_gen33.sh와 g3/gen33_parity_baseline.json이다. gen32 쪽에만 있는 27개는 experiments/pki 26개와 이름이 바뀐 build_gen32.sh다.

- R-E README의 gen-2 판정이 원자료에 맞게 정정됨 (로컬 브랜치) (improvement): **confirmed** sev= :: 원자료와 맞는다. || pq_afec/experiments/state/loop2.json stages는 done 19(p6 stale 포함), failed 6(p8 p10 p15 p17 p18 p20)이다. fixloop.log 58행(2026-10-02 04:36:15)은 '통과 18', '안돌았음 1'이다. hygiene 브랜치 README diff에서 해당 행은 '18단계 통과, 6단계 실패(p8 p10 p15 p17 p18 p20), p6 미실행'이다.

- pq_afec_next 미합류 사본의 바이트 보존 (D6 준수) (improvement): **confirmed** sev= :: 바이트 단위로 같고, merge하지 않았다. || next_cmp.py로 archive/next-2026-09-08의 pq_afec_next/ 트리와 C:\dev\pq_afec_next를 비교하니 290/290이 같았고 합계 25,111,699 B, 폴더 파일 수도 290이다. main은 6bbd11f 그대로다. D6은 '보관 브랜치만'이다.

- Python RS 코덱의 단일 패리티가 전송 형식(XOR)과 같아짐 (improvement): **confirmed** sev= :: diff와 시험이 존재하고, 기본 실행에서 통과한다. || git diff 90859b973 HEAD -- afec/rs.py의 해당 행은 'self.cauchy = [[1] * k] if r == 1 else ...'다. tests/test_core_regressions.py 148행 test_single_parity_matches_wire_xor_and_recovers_erasures와 167행 test_xor_rejects_unknown_parity_index가 있고, clone 전체 실행에서 통과했다.

- CI 초안의 의존성 고정은 유효함 (improvement): **confirmed** sev= :: action 고정 해시와 requirements 고정값을 확인했다. 마지막 단계 실패(A-E1) 때문에 weak가 맞다. 덧붙이면 Codex의 Linux pytest(1794 passed)는 /mnt/c/dev/pq_afec_gen33 작업 트리에서 돈 결과다(s5_pytest_linux_v5.py 11행). clean checkout Linux runner에서 Python 단계가 통과하는지는 아무도 확인하지 않았다. || git ls-remote 결과 actions/checkout v7.0.1은 3d3c42e5aac5, setup-python v7.1.0은 6d4fd22b2046, setup-go v7.0.0은 b7ad1dad31e0으로 ci.yml 18, 19, 26행과 같다. S5_linux_dependencies_01.log 41-46행에서 pytest 9.0.3, matplotlib 3.10.8, cryptography 50.0.1, scipy 1.18.1을 내려받았다.

- verdict_improved (verdict): **partly** sev= :: 큰 결론(보존과 검증 가능성은 나아졌고, 공유·공개 준비는 손이 더 감)은 맞다. 근거 하나는 틀렸다. '기준선 전체 pytest가 초록이 아니었다(S5 기준 33 실패)'의 33은 v3.2-dev 기준선 값이 아니다. 11-01 07:58 S5 직전 gen33 작업 트리(1818개 수집)의 값이다. 기준선 커밋 자체는 29 실패다. 33개 중 4개는 루프가 만든 실패였다. S3(1fb785ec4)가 legacy main을 막아서 깨진 test_cli_requires_explicit_mode 2개, test_layout_rule_mirrors_qamp, test_no_foreign_paths다. S5는 이 중 3개를 historical로 옮겼다(사유를 적었다). 그래서 historical 32개 = 상속 29개 + 루프 변경으로 깨진 3개이고, 카드의 '상속 시험 29개'보다 많다. 판정 문장의 '재현 빌드는 비트 단위로 같다', '378항목 일치', '86/92가 깨졌다'는 직접 확인했다. 보존본(padfec_archive, ~/frozen)도 같은 노트북 디스크에 있으므로 '노트북 한 대에만 있었다'는 약점은 디스크 손실 관점에서 여전하다(외부 사본 여부는 확인하지 못함). 또 gen33 자신의 검증 묶음이 기본 Windows clone에서 manifest 해시가 깨지는 문제(missed 1)가 있어서, 'clone 준비도' 개선은 R-E에 한정된다. || git archive 90859b973을 scratch에 풀고 'python -I -B -m pytest tests -q -p no:cacheprovider'를 돌리니 '29 failed, 552 passed, 2 skipped, 583 subtests passed in 24.02s'였다. S5_pytest_baseline_v1.results.json은 collected 1818, failed 33이고 s5_pytest_baseline_v1.py 11행 root는 C:\dev\pq_afec_gen33(작업 트리), started_kst는 2026-11-01T07:58:25다. historical 32개와 기준선 실패 29개의 차집합은 test_g31_probe::test_historical_source_reference_locations, test_g3_m1confirm::CliTests::test_cli_requires_explicit_mode, test_g3_stage0::Stage0PlanTests::test_cli_requires_explicit_mode 3개다. 이 둘째·셋째 시험은 기준선에서 2 passed, 지금은 'SystemExit not raised'로 실패한다(git diff 90859b973 HEAD -- experiments/g3_stage0.py: main이 'return 2'로 바뀜).

### missed

- [low] gen33 .gitattributes가 검증 묶음의 .log 등을 보호하지 않아 기본 Windows clone에서 manifest 해시 108개가 깨짐 :: Codex는 S2에서 R-E의 A6 결함(autocrlf=true clone에서 봉인 해시가 깨짐)을 고쳤다. 그런데 gen33에서는 같은 결함을 다시 만들었다. gen33 .gitattributes는 *.py, *.go, *.md, *.json, *.txt 등만 eol=lf로 고정하고 *.log, *.saved, *.buildinfo, *.sha256, *.srcsha, *.jsonl, *.patch, *.diff, *.js는 빠져 있다. 이 PC의 시스템 기본값(core.autocrlf=true)으로 clone하면 115개 파일이 LF에서 CRLF로 바뀐다. 그중 108개가 g3/v33/validation과 candidates의 manifest에 sha256으로 적혀 있어 새 PC에서 검증 묶음을 확인하면 불일치가 난다. tools/doctor.py는 autocrlf 값을 기록만 하고(runtime_fingerprint.py 35·54행) 문제로 표시하지 않는다. 연구 수치에는 영향이 없고, 묶음 재검증의 이식성 문제다. || git config --show-origin으로 보면 'C:/Program Files/Git/etc/gitconfig core.autocrlf=true'다. 스크래치 clone에서 git ls-files --eol을 보면 'i/lf w/crlf'가 115개였다. crlf_check.py로 이 115개의 원본(LF) sha256을 HEAD의 manifest, *.sha256 해시 문자열 64,364개와 대조하니 108개가 참조됐다(log 79, saved 10, buildinfo 4, sha256 4, srcsha 4, jsonl 3, patch 2, diff 1, js 1). 예: g3/v33/validation/E12_v1/manifest.json 263-265행 stored_path build/qamp.sha256의 sha256은 a216b18d…인데, clone 파일의 sha256은 5a95827c…다.

- [low] 20 MB 거부 pre-commit 훅이 .git/hooks에만 있어 clone하면 사라짐 :: S5가 만든 훅은 버전 관리되지 않는 .git/hooks/pre-commit에만 있다. core.hooksPath 설정도, 설치 안내 문서도 없다. 새 clone이나 다른 팀원의 PC에서는 큰 파일 방지가 작동하지 않는다. 카드 S5.6이 'gen33 저장소에만'이라고 했으므로 카드 위반은 아니다. 다만 이후 A-E3 같은 비대화를 막는 장치로는 약하다. || .git/hooks/pre-commit(11-01 08:21)의 내용은 'exec python -I -B "$root/tools/precommit_size.py"'다. docs/S5_test_hygiene.md, README.md, tools/*를 pre-commit, hooksPath, .git/hooks로 검색하면 0건이다(27행 raw_io 설명만 나옴).
