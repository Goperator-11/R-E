# PAD-FEC v3.3 과제 보드

이 파일은 과제의 **명세**다. 진행 상태는 `state/LOOP_STATE.json`에 적고 이 파일은 고치지 않는다. 일하다 새 과제가 필요하면 `state/EXTRA_TASKS.md`에 같은 양식으로 추가한다(번호 `E1`, `E2`, …).

각 카드의 근거 ID는 `findings/FINDINGS_INDEX.md`에서 찾는다. 원문은 `findings/audit-*.md`, 검증은 `findings/verify-*.md`다. 검증이 PARTLY인 항목은 검증 파일의 정정 문장이 정본이다.

2026-11-02 Claude 수정(v33fix 묶음 E, 도현님 지시 "수정해야하는 모든 수정 사항들을 전부다 꼼꼼하게 수정해줘"): 2026-11-02 감사(`C:\dev\codex_handoff\v33\findings\v33audit_2026-11-01`)에 따라 실행 순서, G1·G2 카드, L 공통 채택 기준, 의존을 바꾼 카드(L4, J2, J4, L6, M2, X2)와 M1·J5·J7 카드에 덧붙였다. 무엇을 왜 바꿨는지는 `C:\dev\codex_handoff\v33\V33FIX_loop.md`에 있다. 루프는 여전히 이 파일을 고치지 않는다. 같은 날 2차 통합 정리(Claude)에서 G1 카드(통합 결정 done, `c1_seen` 참 경로의 재평가 조건), J5 결과 줄과 M2 카드의 "사실상 0" 정정, 실행 순서 10항과 R1 카드의 done 조건을 고치고, 실행 순서 4항(해제 과제)에 E41을 넣었다(V33FIX_loop.md 끝 "통합 정리" 절).

## 실행 순서

`state/LOOP_STATE.json`의 `order`가 정본이다. 의존이 모두 `done`인 과제 가운데 order에서 가장 앞의 것을 고른다. 아래는 그 order를 묶음으로 적은 것이다(2026-11-02 재배치, H-03·G-E2). 측정(X*)은 G1·G2·S4·T7이 끝나기 전에는 시작하지 않는다.

1. 끝난 묶음(done 또는 blocked): S0 → S1 → S3 → A0 → W0 → W1 → L1 → L2 → L3 → J1 → J6 → L5 → E12 → J7 → M1
2. 측정 사슬: G1 → G2 → S4 → T1 → T4 → T5 → T6 → T7
3. 개발 측정: X6(스모크 먼저) → T3 → X1 → T2 → X4 → X3 → X9 → X2
4. 해제 과제(기각 사유가 도구·세계 결함인 것을 푸는 E 과제와 추적 보충): E10 → E14 → E15 → E25 → E27 → E28 → E1 → E39 → E38 → E40 → E41
5. 끝난 후보(blocked): O2 → J5 → O3 → O4 → J3 → M4 → J8
6. 활성 정책 위에서 진행하는 후보: L4 → J2 → J4 → O1 → L6 → M2 → M3
7. X5 → X7(선택) → X8(선택)
8. S2 → S5 → A1 → R3 → R2
9. 나머지 E 과제(재진입 과제 포함)는 order의 순서대로
10. R1은 order 맨 끝에 있다. 과제로 고르지 않고 매 반복 갱신하며, 마감 45분 전에는 무엇을 하든 R1 최종본을 쓴다. 모든 과제가 끝났는지 볼 때 R1은 세지 않는다. R1을 뺀 모든 과제가 done·blocked·skipped이면 그 반복에서 R1 최종본을 쓰고 R1을 done으로 바꾼 뒤 끝낸다(LOOP_PROMPT 4절, 2026-11-02 2차 수정).

blocked는 미채택이나 실제 장애다. todo 과제의 의존에 blocked 과제를 두지 않는다. 미채택 후보에 순서상으로만 걸려 있던 과제(L4, J2, J4, L6, M2)는 당시 활성 정책 위에서 진행한다(2026-11-02). 어떤 후보든 채택하려면 그 과제 안에서 Go 거울, 기준 벡터 재생성, 관문 PASS까지 끝내야 `done`이다. G1은 이미 채택된 활성 정책의 Go 거울만 맡는다. 의존 관계의 정본은 `state/LOOP_STATE.json`의 `depends`다.

예상 시간은 Codex 한 반복 기준 대략값이다. 한 반복에 다 못 하면 하위 단계로 나눠 `partial`로 끝내고 재개 메모를 남긴다.

---

## S. 준비와 안전

### S0 기준선과 gen33 git 저장소 (30~45분)
- 목적: 작업 폴더를 되돌릴 수 있게 만들고 출발점의 시험 수를 고정한다.
- 근거: A6-M05, A6-05, 볼트 10-22 기록(gen33 기준선 관문이 빌드 스크립트 이름 때문에 FAIL).
- 할 일:
  1. `C:\dev\pq_afec_gen33`이 gen32와 빌드 스크립트 이름·`g3/gen33_parity_baseline.json`만 다른지 CRLF 정규화 diff로 확인한다(`__pycache__`, `.pytest_cache`, `experiments/state`, `experiments/results` 제외). 다르면 멈추고 기록한다.
  2. `git -c core.autocrlf=false init`, `git config core.autocrlf false`, 사용자 이름·이메일은 R-E 커밋과 같은 값(`git -C C:\dev\R-E log -1 --format='%an %ae'`). 첫 커밋 "기준선: v3.2-dev 사본(gen33)". 브랜치 이름 `v33`.
  3. README의 핵심 pytest 9개 파일을 gen33 경로로 돌린다(`python -B -m pytest ... -q -p no:cacheprovider`). 기대값 109 통과 + 하위 367(10-22 기록).
  4. WSL에서 `build_gen33.sh`(race 없이)로 vet·go test·빌드. 기대값 vet 통과, Go 시험 101 통과. 바이너리 sha256과 srcsha를 기록한다.
  5. `gate_v3_parity.py --bin ~/quicbed_gen33/bin/qamp --out <작업 폴더 밖 임시 경로>`. 내용 대조가 전부 통과하고 지문만 FAIL이면 정상(S3에서 고친다).
- 완료 기준: 위 수치가 `runs/S0_baseline.md`에 있고 git 첫 커밋이 있다. 기대값과 다르면 차이를 적고 원인을 찾을 때까지 다음 과제로 가지 않는다.
- 하지 말 것: gen32·gen31 안에서 아무것도 실행하지 않는다(읽기만).

### S1 원자료와 봉인 바이너리 보존 (30~60분)
- 목적: H1~H4 판정의 근거가 노트북 한 대에만 있는 상태를 끝낸다.
- 근거: A6-02, A6-04, A6r1-01, A6r1-02, A6-M04, A6-M06, verify-A6.
- 할 일:
  1. `C:\dev\padfec_archive\v31_stage3\`를 만든다. 넣을 것: gen31 `experiments/state/p31_run1_*`, `p31_run2_*`, `p31_draw_*`, `g31_probe_*`의 jsonl을 `.jsonl.gz`로, `*_meta.json`, `*_status.json`, console·install 로그, gen31 `experiments/results/` 전부, gen31 `g3/` 전부 사본. gen3 `experiments/state`의 2단계 저널도 같은 방식으로 `C:\dev\padfec_archive\v30_stage2\`에.
  2. `SEAL_stage3.json`의 `development_data_sha256` 항목 가운데 C:\dev 밖이거나 git 밖에 있는 파일(`C:\dev\codex_handoff\state\evo\` 등)을 `dev_data\` 아래 원래 경로 구조로 복사.
  3. WSL 바이너리 보존: `~/frozen/g2_d98b05d7/`, `~/frozen/g3c_6baf2b52/`, `~/frozen/gen32_85f54cf5/`에 qamp와 `.srcsha`를 복사하고 `chmod a-w`. 같은 파일을 `C:\dev\padfec_archive\binaries\`에도. `go version -m` 출력도 같이.
  4. 원본 바이트 sha256 목록 `MANIFEST.sha256`(압축 전 원본 기준)과 검증 스크립트 `verify_archive.py`(압축을 임시 폴더에 풀어 sha 대조). 실제로 돌려 전부 일치 확인.
- 완료 기준: 검증 스크립트 출력 "전부 일치"와 파일 수·크기가 `runs/S1_archive.md`에 있다.
- 하지 말 것: 원본을 옮기거나 지우지 않는다(복사만). GitHub 업로드는 하지 않는다(도현님 결정, `DECISIONS_NEEDED.md`에 적힘).

### S3 gen33의 세대 경로 정리 (45~60분)
- 근거: A6-05, A3-12, A6r1-05.
- 할 일:
  1. gen33 루트에 `genconfig.json`(gen_id `v3.3-dev`, 빌드 스크립트 `build_gen33.sh`, 바이너리 `~/quicbed_gen33/bin/qamp`, 설치 경로 `/tmp/qamp_gen33/qamp`, WSL 루트 `/mnt/c/dev/pq_afec_gen33`).
  2. `gate_v3_parity.py`의 BIN_DEFAULT와 지문 목록(`build_gen32.sh` 하드코딩)을 genconfig에서 읽게 한다. `experiments/pipeline.py`의 `WSL_ROOT`, `tests/test_gen32_build_staging.py`의 스크립트 이름도.
  3. `tests/test_no_foreign_paths.py`: gen33 코드에 `/mnt/c/dev/pq_afec`(gen33 제외), `pq_afec_gen31`, `pq_afec_gen32`, `quicbed_gen32` 같은 다른 세대 경로가 있으면 실패. 역사 기록 파일(`g3/policy3_reference.json` 등)은 허용 목록.
  4. `POLICY_VERSION`은 아직 바꾸지 않는다(L1에서 `v3.3-dev`로).
  5. 빌드 재현성(A6-04, A6r1-02): `build_gen33.sh`의 `go build`에 `-trimpath -buildvcs=false`를 넣고, 빌드마다 `go version -m` 출력을 바이너리 옆(`qamp.buildinfo`)에 저장한다. 바이너리 sha가 S0 기록과 달라지는 것은 의도된 변화이므로 새 sha를 기록한다.
- 완료 기준: 관문 기본 실행이 gen33 바이너리를 쓰고 PASS. 핵심 pytest 그대로 통과. 새 시험 통과.

### S4 10-07 gen-2 수정 이식 (60~90분)
- 근거: A6-03, A3-04, A6r1-04. R-E 커밋 `73aa420`(9개 파일).
- 할 일: `git -C C:\dev\R-E show 73aa420`의 변경을 gen33에 **의미대로** 옮긴다. gen33 qamp.go는 v3 배치가 들어간 판이라 gen-2 qamp.go와 다르니 hunk를 그대로 적용하지 말고 같은 결함을 같은 방식으로 고친다: 패리티만 오는 트래픽의 만료와 `heldBytes` 차감, 잘린 복원본의 전달량 계상, 상충 패리티 메타데이터(sameFecFlight) 거부, policy.go의 콜드스타트 반복·오래된 C1 회신·최소 RTT 고착(ACK RTT EWMA)·심볼 손실 순서·손상 캐시 JSON, `afec/channel.py`의 `for_prior`, `padfec/policy.py`의 `expected_rounds` 캐시. 시험 3개 파일(`qamp_decoder_lifecycle_test.go`, `test_channel_prior_regressions.py`, `test_policy_cache_regressions.py`)도 옮긴다.
- 완료 기준: Go vet·test 전부 통과(새 시험 포함), pytest 통과, 관문 PASS. policy3 결정은 바뀌지 않아야 한다(관문이 증명). gen-2 결정이 바뀌는 것은 의도된 변화이므로 `runs/S4_port.md`에 적는다.
- 하지 말 것: 비교 실험의 gen-2 팔에는 이 판이 아니라 동결 바이너리(`~/frozen/g2_d98b05d7`)를 쓴다. 이 이식은 gen33 바이너리 안의 gen-2 경로와 복호기 결함 수정용이다.

### S2 R-E 위생 (30분)
- 근거: A6-01·A6r1-03(.gitattributes), A6-07·A6r1-08(태그, 통합 계획), A6r1-14(pq_afec_next 보관).
- 할 일:
  1. `git -C C:\dev\R-E worktree add C:\dev\R-E-wt\hygiene -b hygiene/2026-10-30 main`. 그 worktree에서 루트 `.gitattributes`에 `* text=auto eol=lf`와 바이너리 패턴(`*.png *.xlsx *.docx *.pdf *.pptx *.gz binary`). `git add --renormalize .` 결과 내용 변경이 0인지 확인하고 커밋.
  2. 검증: 스크래치에 `-c core.autocrlf=true`로 이 브랜치를 clone해 gen31 `SEAL_stage3.json`의 45개 해시가 원본 바이트로 전부 일치하는지(`evidence/audit-code-infra/seal_check_clone.py` 참고).
  3. 로컬 주석 태그만(푸시 안 함): `gen2-frozen-4bab4a5`(→`4bab4a5`, 메시지에 qamp sha `d98b05d7…`, srcsha `b1816779…`), `gen2-fix-73aa420`, `v3.1-stage3`·`v3.2-dev`(→`6bbd11f`, 메시지에 폴더 이름).
  4. 두 번째 worktree `C:\dev\R-E-wt\next` 브랜치 `archive/next-2026-09-08`에 `C:\dev\pq_afec_next`를 `pq_afec_next/`로 그대로 복사해 커밋(merge 안 함).
  5. 같은 hygiene 브랜치에서 R-E README 24행의 "17단계 통과, 7단계 실패(p8 p10 p16 p17 p15 p18 p20)"를 최종 상태(18 통과, 6 실패: p8 p10 p15 p17 p18 p20, p6 미실행)로 고친다(Q-20). 근거는 `C:\dev\pq_afec\experiments\state\loop2.json`과 `fixloop.log` 마지막 바퀴. 봉인 세대 폴더(pq_afec_gen3, pq_afec_gen31)의 README는 봉인 범위와 상관없이 이번엔 고치지 않는다.
  6. 통합 계획 문서(실행은 안 함): `runs/S2_consolidation_plan.md`에 A6-07·A6r1-08의 Phase 0/1 안(태그 기반 단일 저장소, core/testbed/experiments 분리, 세대별 config, 과거 세대 바이너리는 태그 worktree에서 빌드)을 이 PC 현황에 맞춰 단계·소요 시간·위험과 함께 적는다.
- 완료 기준: main 작업 트리 `git status` 깨끗, HEAD `6bbd11f` 그대로. 도현님이 아침에 칠 push 명령을 `runs/S2_hygiene.md`에 적는다(실행은 안 함).

### S5 시험 위생과 CI 초안 (45~60분)
- 근거: A6-09, A6-06, A6-08, A6-12, A6-14, A6-15, A6-16, A6r1-07, A6r1-09, A6r1-12, A6r1-13, A6r1-17, A6-M01, A4-10.
- 할 일:
  1. gen33에 `pytest.ini`(testpaths, `historical` marker). 봉인 파일이 없어 실패하는 상속 시험 29개는 이유를 적고 `historical`로 표시해 기본 실행에서 뺀다(지우지 않는다). 전체 pytest가 초록이 되게 한다.
  2. `.github/workflows/ci.yml` 초안(ubuntu-latest, 핵심 pytest, go vet, go test -count=1, 관문은 빼고). `requirements.txt`(pytest, matplotlib 버전).
  3. 재현 도구: `tools/doctor.py`(배포판 이름, Python 버전, autocrlf, PADFEC_* 값, 경로 검사), `tools/bootstrap_wsl.sh`(Go 1.26.6 tarball sha256 확인 뒤 `~/goroot`, iproute2 확인, `unshare -Urnm`에서 netem이 걸리는지 확인. 이 PC에서는 내려받기 없이 확인 모드로만 돌린다), 배포판 이름은 환경변수 `PADFEC_WSL_DISTRO`(기본 Ubuntu)로.
  4. 새 러너용 지문은 code_fp와 env_fp로 나눈다(A6-08, A6r1-09). gen-2 loop2는 건드리지 않는다.
  5. Go 의존성 고정(A6-14): gen33의 `experiments/quicbed/build_server.sh`가 `go mod init`/`tidy`로 quic-go 고정을 푸는지 확인하고, 그렇다면 `build_gen33.sh`에 위임하게 고치거나 막는다. 모든 빌드 경로가 `GOFLAGS=-mod=readonly`와 go.sum을 쓰는지 시험으로 고정.
  6. 큰 파일 정책(A6-12, A6r1-12): 앞으로 생기는 원자료는 `.json.gz`/`.jsonl.gz`로 쓰는 읽기 도우미, 20 MB 넘는 파일을 거부하는 `tools/precommit_size.py`와 git pre-commit 훅(gen33 저장소에만).
  7. lint가 소스 트리에 `__pycache__`를 만드는 compileall 대신 `ast.parse` 검사를 쓰게(A6r1-17, gen33 안의 lint 경로만).
  8. 코덱 함정(A4-10): `afec/rs.py`의 `RSErasureCode(k, 1)`을 m=1에 쓰면 전송 형식(XOR)과 호환되지 않으니, gen33 사본에서 m=1 호출을 막거나 XOR을 강제하는 시험. `codec.py` 16 B 꼬리표 형식이 실제 전송 형식(CRC 4k + 길이 2k)과 다르다는 점은 R3 문서에 적는다.
  9. 위생(A6-16, A6r1-17): 시험용 개인키는 계속 저장소 밖, 공개 전 정리 스크립트(`tools/scrub_for_publish.py`: 사용자 경로·이메일 검사, 실행은 검사 모드만).
- 하지 말 것: 봉인 폴더의 `--report-only`를 실행하지 않는다(커밋된 판정 파일을 덮어쓴다, A6-M01).

---

## A. 오프라인 재분석

### A0 근거 재현 묶음 (45~60분)
- 목적: 이 루프의 모든 판단이 기대는 숫자를 gen33 안의 재현 가능한 스크립트로 고정한다. W0 보정 자료도 여기서 나온다.
- 근거: A7-11, A2-01·A2-06, A1-01(정정), A1-02, A5-07, A4-01, A1-09, A6-M02.
- 할 일: `g3/v33/evidence/`에 스크립트 7개와 `EVIDENCE.md`. 저널은 gen31에서 읽기만 한다(행 구조: 줄마다 `val.segments[].rows[]`, 행에 arm이 없으니 segment의 `arm`을 붙인다, 서버 계수는 `segments[].server_delta`).
  1. D_p11_2955 l0/l2/l5의 g3auto 결정 전 p_mean 궤적 동일성(1,600위치).
  2. S_bigcert 15% (0,3,1) baseline 오염: 비1-RTT 중 y=0 수(기대 85/535, 55/484).
  3. 15% (0,3,1)·(0,0,4) J3 분해: 관측 평균 대 `layout.evaluate`, 처리 상수·둘째 왕복 꼬리·실패 가지 몫(검증자 정정값 기준).
  4. p18 (0,0,4) iid 대 GE 대 실측(P_fail, 평균 HCT).
  5. 서버 계수 바이트: 팔별 parity 수와 연결당 bytes_in(전 조건 표).
  6. H c12000 관측 S → n_need 12 대 유효 모형 11.
  7. RTT200: initial_datagrams 분포, path_rtt_source unavailable 비율.
- 완료 기준: 7개 모두 기대값 재현, 아니면 차이와 원인. 재현 안 된 수치는 이후 과제에서 근거로 쓰지 않는다.

### A1 보고서 주장 목록 (30~45분)
- 근거: A5-12, A4-11, A6-11, A6r1-11, A7-01, A7-03, A7-05, A7-06, A7-18, A7-21, A7-22, A8-03, A5-11, A5-14, A7-M03, A1-M01.
- 할 일:
  1. `docs/REPORT_CLAIMS_v33.md`. 쓸 수 있는 말(조건 단서 포함), 쓰면 안 되는 말(이유와 근거 파일), 낡은 문장 목록(어느 문서 몇 행, 현재 값, 근거 파일). 팀 문서(`C:\dev\pq_afec\docs`), README, 볼트(`C:\dev\claude_brain`)는 고치지 않는다. 목록만 만들고, 볼트 쪽 목록은 아침에 Claude가 반영할 수 있게 따로 절을 둔다.
  2. 인증서 크기의 현실 대응(A5-14, A7-05, A7-06): WSL의 OpenSSL 3.5(`openssl list -signature-algorithms`로 ML-DSA 지원 확인)로 ML-DSA-44·65 체인(루트·중간·리프)과 CertificateVerify 크기를 실제로 만들어 바이트를 재고, 테스트베드 `-certsize`(합성 DER)와 "서버 첫 비행 바이트 = DER + s0" 표로 대응시킨다. 고전 체인은 RFC 8879 압축 뒤 크기로 해석한다는 문장과 MTC 띠(약 7.7~9.0 KB) 위치도 같은 표에. ML-DSA가 없으면 FIPS 204 크기로 계산하고 "계산값"으로 표시.
  3. gen-2 p3 수치(덱 15·16번)는 순차 측정이라 ±0.3 ms 표류를 통제하지 않았다는 한계 문장(A5-11). 다시 재는 것은 D6 결정 대상.
  4. TTLB 반론 대비 문장(A7-22): 이득을 ms와 함께 비재개 연결 중앙 전송량(7.8 kB) 기준 비율로도 적는 틀.
  5. 감사 밖 정정 목록(`findings\EXTRA_SOURCES.md`): Q-02(p18 검사 4 자 방향), Q-05(원리적 한계: 폐루프, k 제어 불가, s2c 미보호), Q-08(낡은 팀 문서 목록과 각각 무엇이 틀렸는지), Q-09(보고서 「한계」에 빠진 항목), Q-13(Go 1.26.5 명세 대 1.26.6 실측), Q-14(`run_v3.sh` 한쪽 netem, `gemodel 5% 50%`의 정상상태 9.09%), Q-16(`선행연구 대조.md` 틀린 문장 셋), Q-17(z=0.79 "기각" 문장, X9 결과로 바꿀 문장 틀), Q-19(봉인 프로토콜 상태 문장, 상속 봉인 불일치 표기), Q-22(p15 "평상시 pad" 검사가 ips만 봄). 항목마다 "어느 파일 몇 행, 지금 문장, 고칠 문장, 근거"를 표로. 팀 문서 자체는 고치지 않는다.

---

## W. 독립 세계 시뮬레이터 (모든 알고리즘 과제의 판정 도구)

### W0 세계 모형 분리 (90~120분)
- 목적: 지금 적응 벤치는 결과를 정책과 같은 J3로 만들어서 비용 모형 오류를 원리상 못 잡는다(A1-14 CONFIRMED). 정책 모형과 분리된 세계 모형을 만든다.
- 근거: A1-14, A1-15, A7-15, A7-M04, A2-12, A2-16, A3-06, A8-07, A8-08.
- 위치: `experiments/v33/worldsim.py`(정책 코드를 import하지 않는다. 상수는 별도 `worldparams.json`).
- 세계가 다루는 것(각각 끄고 켤 수 있게):
  1. c2s 손실: Bernoulli 또는 Gilbert-Elliott(정상 손실 p, 평균 버스트 L), 송신 순서대로 데이터그램마다 전이.
  2. s2c 손실 q: 서버 첫 비행 데이터그램마다. 잃으면 서버 재전송(9/8·RTT 또는 PTO), 서버 재전송도 3배 예산을 쓴다.
  3. 업링크 직렬화 u, 잃은 데이터그램이 업링크 시간을 쓰는지(`lost_consumes_uplink`, 기본 거짓 = netem과 같음).
  4. 서버 회계: quic-go 올림형(P=1280, 보내기 전 `sent >= 3·received` 검사) 또는 정확형. 41 B 사전 ACK(업링크 제한 시 원본마다, ClientHello 완성 전). initial cwnd(기본 32패킷).
  5. 뒤 패리티 경주: 서버 결정 지연 분포(기존 q 표를 기본으로, 흔들림 인자).
  6. 선행 패리티: 신용 전용(현행) 또는 보류 복호(M1 모드, deadline = 마지막 슬롯 예정 도착 + margin).
  7. 2-RTT 결과의 둘째 왕복 데이터그램 손실과 클라이언트 PTO(3·rtt_sample).
  8. 처리 상수 c_proc(기본 2.6 ms, 조건별).
  9. 클라이언트 RTT 표본 부풂(첫 원본 앞 바이트의 직렬화).
  10. 실패 가지: PTO(quic-go 200 ms 기본, RFC 999 ms 선택), 재전송 비행 모양(현행 [L,O,T] 전체 또는 원본 우선), 두 번째 실패는 PTO×2.
  11. RTT ≥ 200 탐침 체제(표본 없는 PTO 200 ms가 먼저 터짐).
  12. 토큰 보유(한도 없음), Retry.
  13. 목적지 상태 변화: 인증서 교체, 로드밸런서 체인 혼합, 지터(지수분포).
- 출력: 연결마다 정책 관측 인터페이스 그대로(hct, ok, k_obs, srv_bytes, rtt) + 새 필드 `arrivals`(보낸 원본·패리티 각각의 도착 비트, C1이 줄 수 있는 것), `ack_seen`(사전 ACK로 확인된 원본), `server_dgram_sizes`, 서버 계수 업링크 바이트.
- 검증(필수):
  0. 외부 기준 대조(Q-11): 지금까지의 자체시험은 모두 자기 자신을 기준으로 쟀다. 세계 모형의 블록 실패확률 계산을 Gilbert-Elliott 손실의 문헌 닫힌형(Bolot 1999 Table 1, Boutremans 2003 식 11)과 몇 점에서 맞춰 본다. 문헌 원문을 이 PC에서 확인할 수 없으면(`evidence\audit-prior-art\dl\`과 팀 `docs\선행연구 대조.md`부터 찾는다) 그 사실을 적고, 대신 2상태 Markov 연쇄의 전수 열거와 몬테카를로 두 독립 방법으로 대조한다.
  1. 세계를 "정책 모형 동치"(iid, 꼬리 없음, c_proc 0, 부풂 없음, 현행 실패 비용)로 두면 행동별 평균이 `layout.evaluate`와 몬테카를로 오차 안에서 같다(10^5 연결, 3σ).
  2. 기본 세계로 v3.1 저널을 재현: S_bigcert 2%·15%의 행동별 1-RTT/2-RTT/꼬리/실패 비율과 평균 HCT, D_p18의 P_fail, S_rtt200의 initial_datagrams. 허용 오차를 미리 적고 결과를 `runs/W0_calibration.md`에. 맞지 않는 항목은 숨기지 말고 "세계 모형 한계"로 적는다.
- 하지 말 것: 세계 매개변수를 정책 수정 결과가 좋아 보이게 고르지 않는다. 보정은 A0의 v3.1 저널에만 맞춘다.

### W1 회귀 벤치와 문턱 (60~90분)
- 근거: A2-16, A2r1-14, A2-02, A2r1-03, A2-09, A2-15, A5-06, A2-14.
- 위치: `experiments/v33/bench.py`, 프로토콜 `g3/v33/bench_protocol.json`(봉인 개념은 아니지만 커밋으로 고정).
- 시나리오(정책 변형마다 같은 seed 목록, 공통 난수로 짝비교):
  - B1 big-cert(S 16000, k=2, 2 Mbps, RTT 50) 2%→15%→2%, 각 450연결, 20 seed 이상
  - B2 같은 문맥 2%↔25% (교차점 위)
  - B3 0% 손실 2955 B(k=2) 업링크 0과 2 Mbps
  - B4 0% 손실 4032 B(k=1, x25519) 업링크 0
  - B5 인증서 교체 9000→16000(p=0.02)
  - B6 로드밸런서 9000/16000 50:50
  - B7 s2c 손실 1%(c2s 2%), c9000
  - B8 지터(지수 평균 10, 20 ms)
  - B9 첫 방문 모집단(큰 체인 35%)
  - B10 p18 버스트 3(15%, cert 4032)
  - B11 RTT200 9000 B 2 Mbps 2↔15%
  - B12 보류형 셀 c6000 RTT120 10 Mbps 1↔8%, c12000 RTT120 5 Mbps 1↔8%
- 지표: 세계 참값 oracle 대비 연결당 후회(ms), 15% 정상 구간 p 편향, 서버 계수 추가 바이트, 최장 고착 길이, 오경보율, 변화 감지 지연, 교체 적응 연결 수. 짝비교 차이는 seed 단위 평균과 95% 구간.
- 문턱(현행 코드는 대부분 실패해야 정상이다. 그것이 벤치가 결함을 본다는 증거다):
  - B1 후회 < 0.1 ms/연결, B2 후회 < 0.5 ms/연결
  - B1 15% 정상 구간 p 편향 |Δ| < 0.005
  - B4 추가 바이트 < 1,855 B(p15 사전등록 기준)
  - B5 교체 적응 ≤ 2연결
  - 어떤 시나리오에서도 v3.1 대비 후회가 0.5 ms/연결 넘게 나빠지지 않음
- 할 일: v3.1(gen31 padfec3를 **읽기 전용 import**, 경로를 sys.path 맨 앞에 두지 말고 별도 프로세스로)과 v3.2-dev(gen32 동일 방식) 기준값을 `g3/v33/bench_baseline.json`으로 커밋.
- 완료 기준: 기준값 표가 `runs/W1_bench.md`에 있고, 감사 수치(1.871, 2.284/3.012 등)와 방향이 같다. 크게 다르면 원인을 찾는다(세계 모형이 다르니 숫자는 같을 필요가 없다).

---

## L. 학습층 (Python 기준 구현 먼저, Go 거울은 채택할 때 그 과제 안에서. 2026-11-02 정정)

모든 L 과제 공통: `padfec3/learn3.py`, `decide3.py`를 고친다. 상태 버전을 올리고 `POLICY_VERSION`을 새 판으로 바꾼다(2026-11-02 현재 활성은 v3.3.1-dev, STATE_VERSION 11). 각 과제 끝에 W1 벤치 전체를 돌려 전후 표를 `runs/<과제>_bench.md`에 남긴다. 개선이 없거나 다른 시나리오가 0.5 ms/연결 넘게 나빠지면 그 변경을 되돌리고 `JOURNAL.md`에 "버린 것과 이유"를 적는다.

채택 기준(2026-11-02 Claude, B-E2·C-E7·H-05·D-E5). L1은 c1 경로만 주 비교로 두고 none 경로의 v32 대비 B6 +6.372402 ms 악화(`runs/L1_precision_disposition.md`, Codex 문서값)를 진단으로 내려 채택됐고, 그 뒤 후보들은 none과 c1 모두 L1 대비 관문을 썼다. 같은 경로를 후보마다 다르게 다룬 이 비대칭을 없앤다. 정책을 바꾸는 모든 과제(L·J·O·M과 그 재진입 E 과제)에 아래를 똑같이 쓴다.
1. 채택하려면 none 경로(C1 회신 없음, 기본 배포 경로)와 c1 경로를 포함한 모든 배포 경로에서 W1 모든 셀이 v32(기준선 90859b973의 v3.2-dev) 대비 0.5 ms/연결 비열등이어야 한다. 이것은 바닥 조건이고, 카드의 개선 기준과 당시 활성 정책 대비 악화 없음은 그대로 둔다. none 비교의 기준선을 이전 후보의 none(예: L1-none)으로 바꾸지 않는다.
2. 사후 MC 정밀화(결과를 본 뒤 N을 늘려 다시 계산)는 계획 파일에 미리 정한 경우에만 하고, 정했다면 모든 후보에 똑같이 적용한다. 미확정은 통과가 아니다. 미확정이 나오면 그대로 보고하거나 새 seed로 독립 반복한다.
3. 루프가 스스로 주 비교를 고르거나 어떤 배포 경로를 진단으로 내리지 않는다. 그런 결정이 필요하면 `DECISIONS_NEEDED.md`에 올리고 기본값은 1을 따른다.
4. 판정 규칙 세부(영분산 처리 Z1, 표본 크기 고정 등)는 gen33 `docs/V33FIX_bench_rules.md`를 따른다.

### L1 데이터그램 단위 손실 증거 (90~120분)
- 목적: 손실 학습을 고른 행동과 분리한다. 보호 행동에서도 정보가 들어오게 한다.
- 근거: A2-01, A2-02, A2-08, A2-12, A2r1-02, A2r1-06, A7-11, A3-02, A8-09, A1-M03, C1 설계 문서(`C:\dev\pq_afec\docs\C1 서버 피드백 설계.md` 3.1·3.4절, 109~121행 결함).
- 할 일:
  1. 관측 함수에 선택 인자 `arrivals`를 추가한다: `{"src": "c1"|"ack"|"none", "sent": int, "lost": int, "bitmap": [0/1,...] 또는 null, "trunc": bool}`. sent는 첫 비행에서 보낸 데이터그램 수(원본 + 패리티), lost는 서버에 도착하지 않은 수.
  2. 우도: 격자마다 b_g = G[g]^lost · (1−G[g])^(sent−lost). 반복 곱셈으로 계산(Go와 같은 순서). 건너뛰기 사유와 상관없이 **모든 연결**에서 곱한다.
  3. 첫 비행 전멸(서버 회신 없음, PTO로 끝남)은 C1 문서 3.4절 C2 규칙대로 sent개 모두 손실로 넣는다(생존 편향 방지).
  4. C1 결함 확인: 원시 `RxOrigN`이 PTO 재전송을 센다(문서 109~121행). 클라이언트 CRC 대조(`matchFirstFlight`)가 이를 바로잡는지 qamp.go에서 확인하고, 우도에는 CRC로 대조된 첫 비행 수만 쓴다. 확인 결과를 `runs/L1_c1_check.md`에.
  5. `src="none"`이면 L2의 3등급 우도로 대신한다.
  6. 1비트 y는 손실 추정에서 빼고 감시(L3)에만 쓴다.
  7. W0 세계가 arrivals를 C1 방식으로 만들어 주게 한다.
- 완료 기준(W1): B1 < 0.1, B2 < 0.5 ms/연결(감시층 정리 L3와 함께 달성해도 된다. L1 단독 결과도 기록), B3·B4 p_mean이 0.01 아래로 수렴, 다른 시나리오 악화 없음. 시험: 보호 행동만 고르는 목적지에서 p가 참값으로 수렴하는 단위 시험.
- 하지 말 것: arrivals가 없는 경로를 지우지 않는다(C1 없는 서버 대비).

### L2 3등급 라벨과 기준선 (45~60분)
- 근거: A2-06, A2-07, A2r1-01, A2r1-15, A7-13(검증: 모형 절대 기준선은 위험, 하위 분위수나 혼합 적합이나 등급 우도가 안전).
- 할 일: HCT를 1-RTT / 2-RTT / 그 이상·실패 3등급으로 나눈다. 경계는 RTT 양자 구조로: 1-RTT 경계 = `layout.one_rtt_cutoff_ms`(1.5·RTT + τ(결정 전 바이트)) + c_proc 여유, 2-RTT 경계 = 그 + RTT + response term + 여유. 경계가 쓰는 RTT는 O3의 보정 RTT(그 전까지는 현행). 등급 우도는 `layout.evaluate`의 p_one_rtt, p_two_rtt, p_fail(J1 이후엔 꼬리 반영값). EPS는 목적지별 Beta 사후로 추정하고 기본 1e-3(측정 오탐 0.069%, A2-07).
- 완료 기준: A0의 2번 스크립트를 새 라벨로 돌리면 놓친 2-RTT가 0, 2% 층 오탐 0. W1에서 arrivals 없는 변형(src=none)의 B1 결과 기록(단독으로 B2를 통과하지 못하는 것이 2차 감사 결과이므로 통과를 기대하지 않는다).

### L3 건너뛰기·재평가·감시층 정리 (60~90분)
- 근거: A2-02, A2-04, A2-05, A2-10, A2r1-03, A2r1-04, A2r1-08, A7-14(proposal doubtful 단서), A7-16(TS 넣지 않음), Q-23(v3.1 「다음」의 감시 통계와 명목 2-RTT 고착).
- 할 일:
  1. 명목 2-RTT 건너뛰기(`skip_reason`의 nominal2)와 RTT≥200 shield 건너뛰기를 arrivals가 있을 때는 없앤다.
  2. 감시층의 가산 벌점과 학습 차단을 없앤다.
  3. 새 감시: 행동별 등급 결과에 대한 위험 보정 CUSUM. 예측 등급 확률 q는 결정 시점 사후 예측. R=2, h=5에서 시작(위쪽), 아래쪽 R=0.5도. 경보가 나면 벌점이 아니라 행동별 보정항 β_a(logit 이동, 상한 있음)를 갱신하고 기록한다. 모든 행동 CUSUM이 함께 울리면 모형 오류가 아니라 손실 변화로 보고 빠른 hazard 가중을 올린다.
  4. 16번째 재평가: arrivals가 있으면 없앤다. 없으면 한 단계 knowledge gradient가 기대 손해보다 클 때만 탐색(선택 구현, 시간 없으면 현행 유지).
- 완료 기준(W1): B1 오경보 1,000결정당 < 1, 모형 오류 주입 시험(행동 하나의 실제 1-RTT 비율을 0.97에서 0.34로) 15결정 안 감지, B1·B2 문턱 통과(L1과 함께), 다른 시나리오 악화 없음.
- 하지 말 것: Thompson sampling.

### L4 재주입 사전과 hazard (45분)
- 의존(2026-11-02, 정본은 LOOP_STATE): L1. L3는 미채택이므로 기다리지 않고 당시 활성 정책 위에서 진행한다.
- 근거: A2-03, A2-09, A2r1-05, A2r1-07, A7-12(proposal doubtful: 단독으로는 효과 없음), A4-07.
- 격자 표현(A4-07): 지금 G(`table.P_VALS`)의 첫 영 아닌 원자가 pad 단독 경계(p < 4.98e-5 근처)보다 40배 커서 "거의 무손실"을 표현할 수 없다. G에 1e-4, 5e-4 원자를 더하는 안과 p=0 점질량(spike-and-slab) 안을 같이 평가한다. G를 바꾸면 Go 거울·기준 벡터·관문도 이 과제 안에서 같이 바꾼다(2026-11-02 정정: G1은 이미 채택된 활성 정책의 거울만 맡는다).
- 할 일: hazard 재주입 목표를 균등 격자 대신 π0로. 후보 π0: (a) 0.9·exp(−p/0.03) + 0.1·균등, (b) 0.7·… + 0.3·균등, (c) 균등(현행). hazard 집합 (현행 5개) 대 (1/300, 1/1000, 1/3000). v3.2-dev의 건너뛴 관측 predict_step은 arrivals가 있으면 필요 없으니 없애고, arrivals가 없을 때만 남길지 B2 진동(A2-09)으로 판정.
- 완료 기준: B1과 B2 **합산** 후회가 가장 작은 조합을 고르고, B2를 망치는 조합(2차 감사의 낮은 사전 단독 6.571)은 버린다. 선택 근거 표를 남긴다.

### L5 S 추정과 n_need (60~90분)
- 근거: A2-11, A2r1-10, A4-01(Claude 확인), A8-06, A1-12.
- 할 일:
  1. 모든 완료 연결의 서버 바이트를 받되 재전송분을 뺀다(C1 `rxRetx` 또는 서버 첫 비행 데이터그램 목록).
  2. 사전 ACK 41 B는 S에서 빼거나 1-RTT 식의 A_pre에서 빼거나 **한쪽만**.
  3. n_need: 관측 바이트를 유효 모형 S로 바꾸는 보정 S_eff = S_obs − tail − (N_obs − base_bin)·c, 또는 근본안(서버 첫 비행 데이터그램 크기 목록으로 "마지막 데이터그램을 뺀 합 < 3·credit − A_pre"를 직접 판정). 두 안을 다 구현해 A4-01 검증(6개 앵커 밴드 재현 6/6, H c12000 → 11)으로 고른다. 앵커 밴드는 `C:\dev\pq_afec\docs\PADFEC v2 명세.md` 358~365행, `evidence/audit-gen2-foundation/s05_anchor.py`.
  4. 변화 감지: 새 값이 s_hat과 크게 다르면(기준은 서버 패킷 크기 절반 같은 물리량으로 정하고 근거를 적는다) 창을 비운다.
  5. S가 여러 값이면(로드밸런서) S 혼합 분포에 대한 E[J]로 결정.
- 완료 기준: W1 B5 적응 ≤ 2연결, B6 후회가 최선 고정 행동 수준, A4-01 검증 통과.

### L6 첫 방문과 상태 키 (60분)
- 의존(2026-11-02, 정본은 LOOP_STATE): O1. L5는 미채택이므로 S는 당시 활성 정책의 추정을 쓰고, L5 재진입(E11)이 채택되면 그 결과를 다시 확인한다.
- 근거: A2-14, A2r1-12, A7-02(단서: 작은 인증서에 패리티를 보내는 비용, 접속망 키 손실이 목적지마다 틀릴 위험), A7-03.
- 할 일: 손실 사후분포의 키를 접속망 키로(테스트베드에서는 설정 문자열), S는 목적지별 + 모집단 사전(큰 체인 35%에서 시작, 다른 목적지 캐시로 갱신), k는 O4. 첫 방문은 S 사전에 대한 E[J] + 바이트 예산(O1)으로 결정.
- 완료 기준: W1 B9에서 첫 방문 이득과 작은 인증서 목적지의 손해를 함께 표로. 프라이버시 한계 문단을 `docs/REPORT_CLAIMS_v33.md`에 추가.

---

## J. 비용 모형 J3 (채택하는 과제는 그 과제 안에서 Go 거울을 맞춘다. 2026-11-02 정정)

### J1 2-RTT 둘째 왕복 꼬리 (45~60분)
- 근거: A1-01(PARTLY, 정정값), A2-17, A8-08, Q-23(v3.1 「다음」의 15% J3 과소예측).
- 할 일: `layout.evaluate`의 nr=2 가지에 q2·T2를 더한다. q2 = p²(T≥1, later XOR 패리티 있음) 또는 p(T=0). T2 = PTO_SAMPLED_MULT·rtt_sample, rtt_sample = rtt + τ(첫 원본 앞 바이트 + W, u). learn3의 등급 확률도 같은 값을 쓴다.
- 완료 기준: A0 3번 스크립트에서 15% (0,0,4) 과소예측이 약 4.3 ms 줄고 (0,3,1)은 약 1.7 ms. 교차점 0.215~0.217. GE·iid 모두에서 확률 합 1. 세계 모형(W0) 대비 오차 표.

### J2 처리 상수 (30~45분)
- 의존(2026-11-02, 정본은 LOOP_STATE): W1. J1은 미채택이므로 당시 활성 비용 모형 위에서 진행한다.
- 근거: A1-10, A8-08, A4-05.
- 할 일: J3에 c_proc 항. 목적지별로 1-RTT 등급 결과에서만 온라인 추정(중앙값, 손실과 섞이지 않게). 기본값은 A0의 2% 층 1-RTT 군집에서.
- 완료 기준: 2% 층 행동별 평균 잔차 |·| < 1 ms(저널 재생).

### J3 실패 가지와 재전송 비행 (60분, 우선순위 낮음)
- 근거: A1-08(PARTLY: 실패당 비용 33~37 ms 과소, 빈도는 맞음), A3-06, A4-05.
- 근거 추가: Q-10(X3이 잰 PTO 배수가 있으면 3.0 대신 그 값을 쓰고, 없으면 3.0을 "RFC 유도값"으로 표시).
- 할 일: M·c를 명시적 2단계 기대값으로. 실패 종류별 탐지 시각(3·rtt_sample, 9/8·rtt_sample + 1.424, T_PTO), 재전송 비행 모양(T6과 같게), 두 번째 실패 PTO×2. 재전송 비행 보호 수준 T′는 기본 1.
- 완료 기준: 고정 팔 실패당 비용 오차 ±10 ms 안(저널). 결정 변화 표.

### J4 RTT ≥ 200 탐침 체제 (45분)
- 의존(2026-11-02, 정본은 LOOP_STATE): W1, T6. J1은 미채택이므로 기다리지 않는다. 실패 비용은 T6의 재전송 계약과 당시 활성 비용 모형을 쓰고, J3 재진입(E30)이 채택되면 다시 맞춘다.
- 근거: A1-09, A3-01, A8-10, A6-M02.
- 할 일: rtt + t_dec(첫 비행) ≥ T_PTO_NO_ACK이면 탐침 체제: 실패 비용, 2-RTT 가지의 탐침 신용, 바이트 회계에 탐침 비행. 탐침 비행 보호는 T′=1(원본만이면 첫 비행 실제 실패 시 기대 손해 약 1.3 ms라 검증자가 T′=1 권장).
- 완료 기준: S_rtt200 저널 재생에서 행동별 J3 편향 감소 표.

### J5 Gilbert-Elliott 버스트 (60~90분)
- 근거: A1-02(CONFIRMED), A4-08, A7-15. 검증자 단서: L 과대추정은 과보호, 관측이 적을 때 출렁임, u=0이면 O1 없이는 바이트가 끝없이 는다.
- 할 일: `layout.outcomes`의 패턴 확률을 송신 순서 위의 2상태 forward 재귀로. L=1이면 지금과 **1e-12 안에서 같아야** 한다(회귀 시험). L은 arrivals bitmap의 연속 손실로 추정하되 사전분포를 두고 갱신(버스트 없음 쪽에 무게).
- 완료 기준: p18 (0,0,4) P_fail 예측 0.04 근처, 평균 HCT 예측 오차가 처리 상수 수준. W1 B10 개선, B1~B4 악화 없음.
- 결과(2026-11-02 Claude 기록, E-J5-1): 부정 결과다. B10에서 활성 정책이 이미 (0,0,4)를 고르고 J5의 알려진 손실률 진단에서 iid·known_burst·forced_burst3가 모두 같은 행동을 골라 B10 HCT 변화는 0 ms였다(gen33 `docs/J5_world_result.md`). 남은 "W1 B10 개선" 여지도 m≤4 안에서는 사실상 0이다(c1 모드는 (0,0,3)으로 간 2.1%를 (0,0,4)로 옮기면 약 0.13 ms, none 모드는 cold 20연결 말고는 0. 2026-11-02 2차 정정, 감사 검증자 E-J5-1 VERIFY가 "구조적으로 불가능"을 약간 과장이라고 고쳤다). B10 이득은 M2(송신 순서)·M3(m>4)와 함께 본다. 남은 p·L 공동 학습은 E23이 맡는다.

### J6 δ 후보에 A_pre와 여유 (30분)
- 근거: A1-04(CONFIRMED), A4-03, A8-06.
- 할 일: `quantum.delta_min`, `_combo_deltas`(gen33 사본)와 `decide3.levers_s`의 need에 A_pre와 여유: need = ((n_need−1)·P + A_pre)//3 + 1 + ceil(margin/3), margin 20~40 B. L5에서 A_pre를 한쪽만 쓰기로 한 것과 맞춘다. A_pre는 상수 41 대신 목적지별 관측 중앙값(서버 첫 큰 데이터그램 앞의 작은 Initial 크기)으로 배운다(A8-06). ML-KEM(k≥2)에서 사전 ACK를 피하려고 k=1을 노리는 행동은 키 공유 크기상 불가능하므로 후보에서 빼고 근거를 R3 문서에 적는다(A8-06).
- 완료 기준: c6000(S 7910, n_need 7)에서 δ=7 근처 후보가 생기고, margin 덕에 A_pre ±13 B 오차에서도 2-RTT로 떨어지지 않음(단위 시험).

### J7 패리티 크기 고정과 상한 (45분, Go 포함)
- 근거: A3-05, A4-02, A8-05.
- 할 일: Go `buildParity`가 본문 끝을 0으로 채워 모든 패리티를 W+46+6k로(`parseFecBlock`은 need 너머 바이트를 무시하는지 확인). 두 언어의 overhead 상수 46. 패리티 상한 1452 B(Python `decide3.UDP_MAX`, Go `p3UDPMax`, gen-2 `policy.go`, 기준 벡터 생성기, 관문). decodeConn에 "PFEC 매직은 있는데 파싱 실패" 계수.
- 완료 기준: Go 시험: 모든 DCID 길이에서 패리티 크기가 같음, 1452 넘는 후보 0. 관문 PASS(기준 벡터 재생성).
- 2026-11-02 Claude 정리(D-E7): 1452 B 패리티 상한은 v3.3.1-dev(정책 수정 방향 4항, `policy.QUICGO_MAX_IPS`)가 활성 정책에 넣는다. gen-2 경로(`padfec/policy.py` `decide_v2`)는 그대로다. 남은 와이어 계약(패리티 크기 W+46+6k 고정, 두 언어 overhead 46, `fec_parse_fail` 계수)은 E38, 그 성능 재판정은 E13이 맡는다. 와이어 계약과 성능 판정을 나눈다.

### J8 서버 프로파일 매개변수 (60분, 모형만)
- 근거: A4-04, A8-03, A8-11, A1-13, A7-04, A7-09, A7-10, A7-M02, A3-07.
- 근거 추가: A1-15(하향 손실), A7-19(서버 재전송 예산).
- 할 일: 서버 프로파일 {mode: granular|exact|unlimited, P, iw_pkts, pto_initial_ms, lead_credited, trailing_race}를 J3 입력으로. 기본값은 quic-go(granular, 1280, 32, 200, 참, 표). P는 첫 서버 데이터그램 크기로 학습. mode는 증폭에 실제로 묶인 연결에서 "첫 RTT 서버 바이트 / 결정 시점 신용" 비로 추정하되, 서버가 보낼 것이 적거나 s2c 손실이 있으면 비가 틀리므로 확정 전에는 exact를 안전 기본값으로(A7-09 검증자 단서). exact로 고른 행동은 quic-go에서도 1-RTT다. 하향 손실 p_d 항(서버 첫 비행 n_need개 중 하나라도 잃으면 서버 재전송, 그 재전송도 3배 예산을 씀)을 J3에 넣고 W0 세계와 맞춘다(A1-15, A7-19). 결정이 갈리는 영역을 표로(`runs/J8_profiles.md`).
- 하지 말 것: 테스트베드 측정 없이 "다른 서버에서도 된다"고 쓰지 않는다.

---

## M. 기제

### M1 선행 패리티 보류 복호 (120~180분, Python 모형 + Go 서버 + 와이어 시험)
- 목적: 같은 바이트로 신용과 복구를 함께 얻는다. 측정 셀에서 지금 성립하지 않는 핵심 주장을 성립시킨다.
- 근거: A8-02, A7-17(PARTLY: 현실적 deadline), A1-M02, A1-M01. 검증자 단서: deadline 비용(2 Mbps에서 데이터그램 하나 5.3 ms)을 모형에 넣을 것, 다른 서버에서는 선행 신용이 0일 수 있음.
- Go(`qamp.go` decodeConn) 할 일:
  1. 비행(DCID|flight) 단위 보류 버퍼: 선행 패리티는 도착 즉시 스택에 넘기지 않고 심볼과 함께 보관(비행당 상한, 전체 상한, TTL).
  2. 결정 시점: 마지막 원본(index k−1) 도착, 첫 뒤 패리티 도착, 또는 deadline(마지막 슬롯 예정 도착 + margin) 중 먼저.
  3. 소거 없음: 보관 선행 패리티를 그 원본 **앞에** pending으로 넣는다(신용). 소거 있음: 뒤 패리티 먼저, 모자라면 선행 심볼로 `recoverMany`. 복원본만 넘기고 쓴 패리티는 삼킨다. 불변식 BytesToStack + pending + len(rec) ≤ BytesIn 유지.
  4. 마지막 원본이 사라진 경우는 첫 뒤 패리티나 deadline으로 확정.
  5. 플래그 `-lead-hold`(기본 꺼짐)로 켠다. 기존 동작과 나란히 잴 수 있게.
- Python 할 일: `layout.outcomes`에 보류 복호 가지(선행도 복구에 쓰고, 쓴 만큼 신용에서 빠짐, 결정 시각은 deadline 반영). 같은 규칙을 W0 세계에.
- 시험: k ≤ 4, m ≤ 4의 모든 도착 순서·소거 집합을 scriptConn으로 decodeConn에 넣어 신용 바이트·복구 여부·불변식을 Python 모형과 대조. 이 M1 와이어 시험은 M1과 그 재진입 E16의 범위다(2026-11-02, G2로 합치지 않는다. G2가 M1 채택을 기다리면 측정 사슬이 잠긴다).
- 완료 기준: 와이어 대조 전부 일치. W1 세계(보류 모드)에서 15% 큰cert (0,3,1) P_fail ≈ 0.0004, 최선 J3 개선 약 10 ms(현실적 deadline). 2% 층 손해가 deadline 비용 이하임을 표로.
- 하지 말 것: 와이어 형식 변경, 선행을 RS가 아닌 데이터로 바꾸기(A1-11 제안은 검증자 doubtful: 이득이 t_dec 1.57 ms와 393 B뿐이고 보류 복호를 막으며 패딩과 같아진다).

### M2 송신 순서 옵션 (45분)
- 근거: A1-06(독립 손실 이득 약 0.3 ms, 버스트 2.6~7.8 ms).
- 할 일: order 매개변수(LLLOOP 현행, OLLLOP 등). W1(B10, B1)에서 평가. 이득이 문턱(버스트 1 ms 이상, 다른 시나리오 악화 없음)을 넘을 때만 기본값을 바꾼다.
- 의존(2026-11-02, 정본은 LOOP_STATE): W1. M1·J5는 미채택이므로 기다리지 않는다. 보류 복호 켬 팔은 M1 재진입(E16)이 채택된 뒤에만 넣는다. J5의 부정 결과(B10 결정 가치 사실상 0, c1 모드 약 0.13 ms 여지, 2026-11-02 2차 정정) 때문에 B10 이득을 보려면 송신 순서나 m>4(M3)가 필요하다.

### M3 lead와 T 상한 분리 (45분)
- 근거: A1-05(CONFIRMED, 헤더는 이미 m≤15). 검증자: 학습층 수정 없이 풀면 해롭다.
- 조건: L1~L4와 O1이 끝난 뒤에만. lead 0..5, T 0..3, m ≤ 8. W1 전체에서 바이트 증가와 이득 표.
- 의존(2026-11-02, 정본은 LOOP_STATE): O1. L2는 done, L3는 미채택으로 끝났으므로 조건의 "L1~L4"는 L1·L4 done과 O1 done을 뜻한다. 평가 계획에 활성 정책의 감시층 상태(c1 경로는 L3 record 팔과 같고 none 경로는 v3.2 그대로, v3.3.1-dev)를 적는다.

### M4 Retry·토큰 인식 (45분)
- 근거: A8-12, A7-20, A8-01, A3-11, A7-18.
- 할 일: fecConn이 Retry(롱헤더 type 3)를 보면 그 연결 다음 비행은 신용용 바이트 0, 복구용 뒤 패리티만. 정책에 토큰 보유 입력: 있으면 lead=0, δ=0, T만 고른다. 패리티 묶음은 연결당 한 번(PTO 탐침에는 넣지 않음, T6과 맞춤). 서버 복호 지원 여부 입력: 지원 신호가 없으면 패리티의 복구 가치를 0으로 보고 dup·pad와 비교(A7-07). 지원 신호 설계(HTTPS RR SvcParam 가칭 initial-credit, 이전 연결 transport parameter 기억)는 구현하지 않고 `docs/server_support_signal.md`에 설계 메모로(A7-18).

---

## O. 목적함수와 입력

### O1 바이트 예산 (45~60분)
- 근거: A2-09·A2r1-09·A2-08, A1-07(proposal doubtful), A4-06, A7-M01, Q-22. 검증자: λ만 넣으면 u>0 보류 셀이 1.4~5.6 ms 느려짐.
- 바이트 지표는 첫 비행 바이트와 연결 전체 업링크(서버 계수)를 둘 다 보고, "pad를 골랐다"는 판정은 ips와 m_used를 함께 본다(Q-22).
- 조건: L1~L4 뒤.
- 의존(2026-11-02, 정본은 LOOP_STATE): L4. L2는 done, L3는 미채택으로 끝났으므로 조건의 "L1~L4"는 L1·L4 done을 뜻한다.
- 할 일: 두 형태를 구현해 W1로 비교한다. (a) 허용치형: 최선 E[J]에서 τ ms 안의 후보 중 바이트 최소(τ 0.1/0.25/0.5). (b) 예산형 Lagrangian: B4·p15형 조건 평균 추가 바이트 ≤ 1,855 B를 만족하는 최소 λ. 최대 후회가 작은 쪽을 기본으로. HCT-바이트 Pareto 곡선을 `runs/O1_pareto.md`와 그림으로.

### O2 업링크 u (45~60분)
- 근거: A1-03, A1-16, A3-07, A3-10, A4-09, A5-08, A8-07.
- 할 일: u를 모를 때(`-uplink-mbps -1` 또는 None) U={0,2,5,10,20,50}에 대한 minimax-regret. 추정기: 같은 목적지의 MinRTT 부풂과 첫 원본 앞 바이트의 회귀, 또는 사전 ACK와 첫 서버 데이터그램 간격. q(d) 경주 표는 구간으로.
- 완료 기준: 세계에서 u를 숨겨도 후회 ≤ 6.5 ms(감사값), 추정기 수렴 연결 수 표.

### O3 RTT 신호 (45분)
- 근거: A2-13, A2r1-11, A3-13, A8-07, A1-10.
- 할 일: 정책 RTT = 부풂을 뺀 표본(표본 − τ(그 패킷 앞에 보낸 바이트))의 EWMA, 최솟값은 따로 보관. gen-2 10-07 EWMA 규칙과 같게. 등급 경계·감시 문턱이 이 RTT를 쓰고, 경계에는 RTTVAR 배수 여유를 더해 HCT 지터가 2-RTT로 잘못 분류되지 않게 한다(A2-13). 표본은 대기열이 없는 패킷에서(Dial 뒤 첫 1-RTT ACK 뒤의 ConnectionStats 또는 Tracer 나중 표본, A3-13). RTT ≥ 200 shield 조건도 보정 RTT + τ(결정 전 바이트) + c_proc 기준으로(A8-10).

### O4 k를 로컬에서 계산 (30분)
- 근거: A1-12, A2-14, A3-10, A8-11.
- 할 일: qamp가 ClientHello CRYPTO 길이와 W로 natural_k를 계산해 정책에 넘긴다(`k_hat` 최빈값 대체). fecConn의 expectK도 이 값(첫 연결 300 µs 타이머 제거, A3-14).

---

## G. Go 거울과 관문

### G1 채택된 활성 정책의 Go 거울과 정책 관문 (90~150분, 여러 번 나눠도 됨)
- 근거: A3-12, A6-06(이중 구현 비용).
- 2026-11-02 재정의(D-E6·H-02·G-E2, D46): 원래 G1은 L1~L5, J1, J2, J5, J6, J7이 모두 done이어야 시작할 수 있었다. 후보 여섯 개가 미채택(blocked)이 되자 G1과 그 뒤의 G2·T7·X 측정 전부가 영구 대기에 들어갔다(감사 H-02 계산, todo·doing·skipped 51개 중 32개 잠김). G1은 이제 채택된 활성 정책만 맡는다. 미채택 후보는 G1을 기다리게 하지 않고, 나중에 채택될 때 그 후보의 과제(또는 재진입 E 과제) 안에서 Go 거울·기준 벡터·관문 PASS까지 끝낸다.
- 의존(정본은 LOOP_STATE): L1.
- 할 일: 활성 정책(2026-11-02 현재 v3.3.1-dev, STATE_VERSION 11, Go cache schema `padfec3.cache3/11`)의 Python 학습·결정 산술을 `policy3.go`에 같은 순서·같은 산술로 옮긴다(반복 곱셈, 합 순서). E12가 이미 끝낸 L1 거울(90000결정 일치, `runs/E12_result.md`)을 출발점으로 쓰고, v3.3.1-dev가 바꾼 부분(목적지별 `c1_seen` 표지, `c1_seen`이 거짓인 목적지의 v3.2-dev 동작, 참인 목적지에서 감시 가산 벌점 없음, 도착 증거가 이어지는 동안(`arrival_streak > 0`) 16번째 재평가 없음(streak가 0이면 재평가는 그대로 돈다), β 반응 없음, v3 패리티 데이터그램 상한 1452 B)을 확인한다. `g3/policy3_reference_gen.py`의 기준 벡터를 활성 정책으로 다시 만든다. `gate_v3_parity.py`에 destCache3 궤적 모드(JSON 왕복 포함)를 더한다. v33fix가 이미 넣은 부분은 다시 만들지 않고 관문으로 확인만 한다(통합 때 Claude가 G1 상태를 정한다). 다른 과제가 G1로 넘긴 감사 항목(`runs\coverage_snapshot.py --received G1`) 가운데 미채택 후보의 Go 거울에 해당하는 것은 G1 coverage에 그 후보의 재진입 E 과제로 다시 넘긴다고 적는다.
- 완료 기준: 관문 PASS(내용 불일치 0, 최대 |dJ| 0 또는 문서화된 부동소수 한계 안). Go vet·test·race 통과. 미채택 후보(L2의 EPS 적응, L3, J1, J5, J6, L5, J7 와이어 후보, M1)는 거울에 넣지 않는다.
- 2026-11-02 통합 결정(Claude): 상태: done. 근거는 gen33 `docs/V33FIX_policy_go.md` 5절이다. 새 관문 `experiments/gate_l1_go.py`가 고정 참조 `g3/v33/V33FIX_policy_reference_v1.json`(seed 20261102)의 잎 738,663개를 모두 비트 일치로 통과했고, 1차 반박 검증자가 따로 만든 seed 4815162 참조도 잎 741,055개가 비트 일치였다(`runs\v33fix\workflow_reports\A-policy.md` VERIFY). Go vet 출력 없음, `go test` PASS 260·SKIP 2·FAIL 0, race 통과(같은 문서). 남은 것: 1차 수정 시점에는 기존 v3 관문 `experiments/gate_v3_parity.py`의 기본 참조 `g3/policy3_reference.json`이 판본 4·1472 B 상한으로 만든 것이라 기본 실행이 실패했다(같은 문서는 스크래치에 다시 만든 참조로만 PASS를 적었다). 이 참조 재생성은 2026-11-02 2차 P 묶음이 맡았고(06:34 KST에 작업 트리의 참조 상수가 policy_version v3.3.1-dev, state_version 11, udp_max 1452로 바뀐 것만 확인했다), Claude가 통합 때 관문 PASS를 다시 확인한다. 그 확인 전에는 v3 관문 기본 실행 결과를 PASS로 적지 않는다. 2026-11-02 07:40 통합 확인(Claude): 다시 만든 기본 참조 `g3/policy3_reference.json`(sha256 `5f582673…1de0`, `policy3_reference_gen.py --check` identical)으로 `gate_v3_parity.py --bin <임시 빌드> --out <임시 폴더>`가 PASS, problems 없음이었다. 같은 작업 트리에서 `build_gen33.sh --race`(임시 HOME) Go 시험 PASS 266·SKIP 2·FAIL 0, race 통과, M1 와이어 관문 2개 PASS, `gate_l1_go.py` 비트 일치 738,663이었다(gen33 `docs/V33FIX_policy_go.md` 8절, 출력 `runs\v33fix\INT`). 설치본 `~/quicbed_gen33/bin/qamp`는 아직 v3.3-dev라서 `--bin` 없이 기본 실행하면 실패한다. 설치 시점은 도현님이 정한다.

### G2 와이어 관문 (60분)
- 근거: A3-12.
- 의존(2026-11-02, 정본은 LOOP_STATE): G1. M1 의존은 뗐다(D 검증자 missed 2: G1만 고쳐도 G2→M1(blocked) 때문에 T7이 잠긴다).
- 할 일: `layout.outcomes`가 나열하는 도착 패턴을 scriptConn으로 decodeConn에 넣고 quic-go에 올라간 신용 바이트·복구 여부를 활성 정책의 Python과 대조. fecConn이 행동별로 실제 내보내는 배치와 크기 검사(v3 패리티 1452 B 상한 포함). 보류 복호(`-lead-hold`, 기본 off)의 와이어 시험은 M1·E16 범위이며 여기서 다시 하지 않는다.

---

## T. 테스트베드 기능 (gen33 qamp, 측정 전 필수)

### T1 결정적 인증서 (30~45분)
- 근거: A6-10, A6r1-10(406블록 중 334블록에서 팔마다 인증서가 최대 3 B 다름).
- 할 일: certsize마다 고정 seed 키와 길이 조정 반복으로 len(der) == 목표인 인증서를 한 번 만들어 파일로. 모든 서버가 `-cert-file`로 같은 파일. 인증서 sha256을 meta에.

### T2 토큰·resumption 팔 (60분)
- 근거: A5-01, A7-01, A8-01. 검증자: 테스트베드는 같은 IP라 토큰이 늘 유효하므로 상한 비교로 해석.
- 할 일: 클라이언트 `-token-store`(프로세스 안 연결들이 LRU TokenStore 공유, 핸드셰이크 뒤 1 RTT 이상 열어 NEW_TOKEN을 받음), `-resume`(ClientSessionCache, 서버 ticket 허용). 첫 연결(토큰 없음)은 따로 표시. Retry 강제 서버 `-verify-source`.

### T3 같은 바이트 비교 팔 (45~60분)
- 근거: A5-02, A7-07, A7-08, A7-05(검증자: Initial 확대 팔 필요).
- 할 일: `-pad-junk`(모든 패리티를 같은 크기·같은 자리의 쓰레기로 = pad4L3), 기존 `-corrupt-parity`(뒤 패리티만 쓰레기), `-dup`(원본과 바이트가 같은 Initial 중복), `-k-inflate`(큰 transport parameter로 ClientHello 부풀리기), Initial 확대 팔(W 1,291~1,472).

### T4 관측 장치 (60~90분)
- 근거: A8-09, A3-02, A3-15, A6-M02, Q-15, Q-18.
- 추가: 서버 통계 `unrecoverable_seen`은 나중에 복구되는 비행까지 센다(Q-15). 이름은 두고 "끝내 복구 못 한 비행" 계수를 따로 만들어 둘을 구분한다. `C1 서버 피드백 설계.md`의 "알려진 결함" 문장이 현재 코드와 맞는지 확인해 gen33 쪽 `docs/c1_status.md`에 현재 상태를 적는다(Q-18, 팀 문서는 안 고침).
- 할 일: quic-go `Config.Tracer` 메모리 기록기(Initial 공간 ACK range와 수신 시각, PTO 횟수, LatestRTT 표본). fecConn.ReadFrom에 서버 데이터그램 (시각, 크기) 목록. C1 fbVer 3: 서버가 "도착"과 "복원"을 구분해 보냄, 복원된 Handshake에도 회신. 행마다 arrivals 필드(L1 형식)와 C1 대조 수.

### T5 복호기·클라이언트 견고성 (60분)
- 근거: A3-03, A3-08, A3-09, A3-14, A8-04.
- 근거 추가: A3-07, A3-11.
- 할 일: decodeConn을 DCID 색인으로(데이터그램당 O(k)), 비행·recent 상한, 모르는 DCID 패리티는 조회 한 번. connAcct 축출(핸드셰이크 뒤 10 s, LRU)과 `ConnAcctDropped` 경고. 클라이언트는 회신·S·srvBig을 peer 주소와 자기 CID인 경우만 받음. "클라이언트 첫 비행에 Initial이 아닌 롱헤더" 불변식 계수(Handshake형 패킷 이중 계상 경로 차단, A8-04). decodeConn 래퍼가 `*net.UDPConn`의 `SyscallConn`·`ReadMsgUDP`를 숨겨 서버가 quic-go basicConn 경로(GSO·ECN·DF 없음)로 떨어지는 문제: 이 메서드를 통과시키는 래퍼로 바꾸고, 바꾸기 전후 경주 표(q)가 달라지는지 X3에서 잰다(A3-07, A3-11). C1을 배포한다면 무인증 평문 부채널 대신 암호화된 연결 안(1-RTT 확장 프레임 등)으로 옮겨야 한다는 위협 모형 메모를 `docs/c1_threat_model.md`에(A3-09, 구현은 안 함).

### T6 재전송 비행 모양 (45분)
- 근거: A3-01, A3-06.
- 할 일: srvBig 전 재전송 비행은 원본 우선(L=0, T′≤1). 모양을 행동의 일부로 기록하고 J3(J3·J4 과제)와 같게. 바이트 보고에 연결 전체 패리티 바이트.

### T7 v3.3 개발 측정 러너 (120~180분)
- 근거: A6-15, A6-12, A6-13, A6r1-06, A6r1-15, A5-10, A5-11, A5-15, A6-M03, A7-22.
- 선택지(A6r1-06, 검증자 doubtful): 연구 단계에서 Python 정책이 결정하고 qamp 고정 플래그로 보내는 "Python 제어기" 팔. 쓰려면 먼저 같은 (δ, ℓ, T)를 auto3 경로와 고정 플래그 경로로 200연결씩 보내 행마다 TxSizes·TxNs가 같은지 A/A로 확인한다. 같지 않으면 쓰지 않는다.
- 위치: `experiments/v33/devbed.py`(얇은 드라이버, 800줄 이하), 공용 함수는 `experiments/v33/lib/`로 뽑되 gen32에서 import하지 않고 gen33 안의 것만.
- 요구:
  1. 팔: `v33auto`(gen33 바이너리), `v31auto`(`~/frozen/g3c_6baf2b52`), `g2auto`(`~/frozen/g2_d98b05d7`), 고정 팔 목록. 바이너리는 실행 시 `/tmp` 아래 run 폴더로 복사해 같은 wsl 호출 안에서 쓴다. 바이너리 sha·srcsha를 행마다.
  2. 블록 안 Williams 회전 교대, A/A 블록 포함, auto 팔은 캐시를 새로 시작하는 독립 궤적 4개 이상, 번인(첫 300연결) 따로 보고.
  3. 서버 쪽 바이트(`server_delta`)로 비용 집계, 서버 바이너리가 팔마다 다르면 경고(A6-M03).
  4. 모든 결과에 `"label": "development"`, `"confirmatory": false`. 결과 `experiments/results/v33_dev_*.json`, 저널 `experiments/state/v33_dev_*`(gitignore 대상이므로 요약 JSON은 `g3/v33/results/`에 복사해 커밋).
  5. 재개: 단위 저널로 중단 지점부터.
  6. 잠금: 시작 시 `C:\dev\codex_handoff\v33\state\MEASURE_LOCK.json`을 쓰고 끝나면 지움(루프 규칙 참고).
  7. 보조 지표: 7.8 kB 응답 TTLB 팔(dataapp.go, A7-22).
  8. 판정 자와 표류(Q-03, Q-04): 실행마다 A/A 블록으로 하네스 표류와 그 신뢰구간을 재고, 계획 파일에 적은 판정 허용 오차가 "표류 + 구간 반폭"보다 작으면 러너가 경고하고 그 판정을 "판정불능(자가 표류보다 곱다)"으로 표시한다.
  9. 상태 구분과 보고(Q-06): 단계마다 "자료 없음(실행 실패)", "자료 있음·판정 실패", "자료 있음·판정 통과"를 다른 값으로 기록하고, 측정이 끝나면 요약 보고 단계가 자동으로 돈다. 사람이 읽는 `note` 같은 문장은 지문 안의 값에서 생성하고 수치를 손으로 박지 않는다.
  10. 덮어쓰기 금지(Q-07): 결과·저널 파일 이름에 실행 ID를 넣고, 같은 이름이 있으면 거부한다.
- 완료 기준: `--dry-run`, `--smoke`(1~2분)가 통과하고 스모크 결과가 기대 범위.

---

## X. 개발 측정 (development 표시, 확증 아님)

공통: 시작 전 G1·G2·S4·T7 완료, 관문 PASS, 바이너리 고정. 측정 계획(셀, 팔, 블록 수, 연결 수, 예상 시간, 이 측정이 답하는 질문)을 `runs/<X>_plan.md`에 먼저 쓰고 커밋한 뒤 시작한다. 측정 중에는 루프 규칙의 "측정 중 허용 작업"만 한다. 결과는 계획에 적은 분석만 "주 결과"로, 나머지는 "탐색"으로 표시한다.

### X6 v3.3 대 v3.1 대 gen-2 (스모크 → 본측정 약 2~3시간)
- 근거: A5-16, A5-06(H4′), A5-17(측정 순서와 정보량/시간), A7-22, A2r1-05(v3.2 감시층 변경의 회귀 위험).
- 셀: S_bigcert 2↔15%, S_rtt200 2↔15%, D_p11_2955 0%, D_p15_4032 0%, H c6000 RTT120 10 Mbps 1↔8%(개발 셀이 된다는 것을 기록). 팔: v33auto(보류 복호 켬과 끔 둘), v31auto, g2auto, 전역 고정 (0,3,1).
- 보고: 평균 HCT 차와 구간, 1-RTT 비율, 서버 계수 바이트, W1 세계 예측과의 차이.

### X1 같은 바이트 패딩 대 패리티 (약 1시간)
- 근거: A5-02(표본 크기: 2% 39블록×40, 15% 28블록, RTT200 15% 8블록), A7-07, A7-08, A7-05, A1-M01.
- 팔: m4L3, m4L3+뒤 쓰레기, pad4L3(전부 쓰레기), dup, Initial 확대, k-inflate(ClientHello 부풀리기), m4L3+보류 복호. 질문: 같은 바이트·같은 자리에서 패리티가 패딩보다 몇 ms 빠른가, 보류 복호가 그 차이를 키우는가.
- 추가 셀(A7-05): 서버 첫 비행 약 7.7~9.0 KB 띠(MTC 이후 예상 띠, ML-KEM k=2) 하나에서 Initial 확대 팔과 패리티 팔을 같은 블록에서 비교한다. 이 띠에서 Initial 확대만으로 1-RTT가 되면 그 사실을 그대로 보고한다.

### X4 토큰·resumption 기준선 (약 1.7시간)
- 근거: A5-01, A7-01, A8-01.
- 팔: v33auto, 토큰 + b0, 토큰 + 뒤 패리티만 (0,0,2), Retry 강제 + b0, resumption + b0. 첫 연결은 분석에서 빼고 따로.

### X2 업링크 오입력 (약 15~30분)
- 근거: A5-08, A1-03.
- netem 대역은 고정하고 정책 입력만 {참값, 0, u/2, 2u, 10, 모름(O2)}. 셀 bigcert 2%·15%, H c6000 1%·8%, 설정마다 300연결.
- 의존(2026-11-02, 정본은 LOOP_STATE): T7. O2 의존은 뗐다. "모름(O2)" 팔은 O2(또는 재진입 E22)가 채택됐을 때만 넣고, 아니면 그 팔을 빼고 이유를 계획 파일에 적는다.

### X3 A_pre 탐침 (약 15분)
- 근거: A5-16, A8-06.
- 고정 팔 (1,0,4)·(0,0,4), 손실 0%, RTT 120 × 업링크 {1, 5, 10}, k=1(x25519) 업링크 셀, 200연결씩, 서버 첫 송신 크기·시각 기록.
- 표본 없는 PTO 배수 실측(Q-10, 약 20분): `PTO_SAMPLED_RTT_MULT = 3.0`은 RFC 유도값이다. 첫 원본 하나를 결정적으로 지우는 `-drop-initial k-1`로 RTT 50·120·200 ms × lead 0·3 × 업링크 0·2 Mbps에서 PTO까지 걸린 시간을 재고, rtt_sample(부푼 표본) 대비 배수를 회귀로 낸다. J3 과제가 이 값을 쓴다.
- 뒤 패리티 신용 항 검증(Q-01): gen-2 p17·p18에서 부호가 갈렸던 뒤 패리티 신용을, 아래 경주 표 측정과 같은 블록에서 (0,0,m)과 (0,m,0)의 1-RTT 비율 차이로 직접 본다. 판정에 필요한 표본 수를 먼저 계산하고, 밤 안에 모자라면 "표본 부족으로 판정 못 함"으로 적는다.
- 경주 표 재측정(A4-09, A3-07, 선택 30분): 뒤 패리티 신용 확률 q(d) = P(서버 결정 지연 > d)를 cert 4032·16000, 업링크 10·20 Mbps에서 다시 잰다(`C:\dev\pq_afec\experiments` 의 `_probe_race.py` 방식을 gen33으로 옮겨서). T5의 UDPConn 통과 래퍼 전후를 같은 블록에서.

### X9 PTO 비율 재측정: 방향 전환 근거 (약 1~1.5시간)
- 근거: Q-17, A5-12.
- 목적: 연구방향 변경보고 ②("패킷이 늘면 손실에 취약 → 기각, x25519 12.0% 대 ML-KEM 10.4%, z=0.79")의 숫자는 워밍업이 분모에 섞인 팀 수집기 값이고 다시 잰 적이 없다. 원래 질문(ML-KEM의 더 많은 Initial 패킷이 손실 노출을 늘리는가)을 고친 측정으로 다시 답한다.
- 할 일:
  1. 원래 팀 조건(손실률, RTT, 인증서, netem 방향)을 `C:\dev\R-E\mlkem-quic-amplification`의 README·`run_v3.sh`·`qhct.go`에서 읽기만 해서 정리한다.
  2. 검정력 계산을 먼저: PTO 발생률 차이 1.5%p와 3%p를 검정력 0.8로 볼 표본 수.
  3. FEC 없는 b0 팔로 x25519 대 X25519MLKEM768을 같은 블록에서 교대, 원래 조건(한쪽 netem)과 양방향 조건 둘 다. PTO 발생은 연결별 Initial 데이터그램 수와 Tracer 기록으로 판정. 분모는 측정 연결만(워밍업 제외).
  4. 결과는 차이와 95% 구간으로 적고, "유의차 없음은 기각이 아니다"라는 해석 규칙을 그대로 지킨다. A1의 정정 문장 틀에 결과를 넣는다.
- 하지 말 것: 팀 저장소 파일 수정, 덱·보고서 직접 수정.

### X5 s2c 손실 (약 30~60분)
- 근거: A7-19, A5-09, A2-12.
- c2s 0%와 2%에 s2c 1%·5%, 팔 b0·pad·m4L3·v33auto. 서버 재전송 시점(qlog)과 학습된 p.
- 대칭 손실 셀(A5-09a): big-cert 2↔15%에서 s2c에도 같은 손실, 고정 팔 b0·m4L3, 헤드라인 이득이 얼마나 줄어드는지.
- 손실 의미 스모크(A5-09b, A7-M04): rate는 클라이언트 쪽 egress, loss는 그 뒤 hop(peer 쪽 ingress, ifb)에 거는 2단 구성으로 "잃은 데이터그램도 업링크 시간을 쓴다" 조건을 스모크 수준으로 만들고 W0의 `lost_consumes_uplink` 예측과 비교.
- 시간 기반 버스트(A5-09c, A7-15): netem gemodel은 패킷마다 상태가 바뀐다. 시간 단위 페이드(수십 ms 동안 전부 손실)를 netem slot이나 tc 스크립트의 on/off로 만들어 패리티 간격·송신 순서(M2)의 효과를 본다. 만들 수 없으면 시도와 이유만 기록.

### X7 RFC 정확 스택 (선택, 2시간 상한)
- 근거: A5-13, A7-21, A7-M02, A3-11.
- WSL에 quiche(또는 ngtcp2) 서버를 오프라인 가능하면 빌드. 안 되면 시도 기록만 남기고 건너뛴다. 팔: b0, 신용 전용 선행 1·2·3, m4L3, (0,0,4), 원본 우선 순서. 서버 쪽 tcpdump로 첫 RTT 송신 바이트.
- 서버 앞단 분배(A7-21): quic-go 서버를 SO_REUSEPORT 다중 worker로 띄웠을 때 선행 패리티 신용이 원래 연결에 잡히는지(QUIC-LB 같은 SNI 기반 분배는 흉내 낼 수 있을 때만). 선행을 원본보다 먼저 보내는 순서를 꼭 포함.

### X8 서버 설정 변형: IW10, InitialPacketSize (선택, 1시간 상한)
- 근거: A7-04(PARTLY), A8-11.
- 모듈 캐시를 건드리지 않는 임시 복사본에서 quic-go `initialCongestionWindow=10`로 바꾼 서버. 큰cert와 c8000에서 b0·v33auto.
- 서버 `Config.InitialPacketSize = 1452`(P가 1280이 아님) 조건에서 같은 팔. J8의 P 학습이 맞는 값을 잡는지, δ와 패리티 개수 판단이 바뀌는지.

---

## R. 문서와 보고

### R1 아침 보고서 (매 반복 갱신, 마감 45분 전 최종)
- order 맨 끝에 둔다(2026-11-02). 의존이 없어 언제나 고를 수 있으므로 앞에 두면 다른 과제를 가린다. 과제로 고르지 않고 매 반복 갱신한다.
- done 조건(2026-11-02 2차): R1을 뺀 모든 과제가 done·blocked·skipped가 된 반복에서 최종본을 쓰면 done이다. 그 전에는 마감마다 최종본을 써도 todo로 둔다(다음 밤에도 갱신한다). 전체 종료 판정(`all_done`)에서는 R1을 세지 않는다.
- 위치: `C:\dev\codex_handoff\v33\runs\MORNING_REPORT.md`.
- 근거: Q-21.
- 내용: 끝낸 과제와 커밋, 숫자(model-world/세계 시뮬레이터/개발 측정을 반드시 구분), 실패한 관문과 이유, 버린 것과 이유, 도현님 결정이 필요한 것(과제명 확정과 저장소 공개 여부 같은 묵은 미결 Q-21 포함), 다음 밤에 할 일 순서, 아침에 칠 확인 명령.

### R2 v3.3 확증 프로토콜 초안 (60분, 봉인하지 않음)
- 근거: A5-03, A5-04, A5-05, A5-06, A5-10, A2-15, A2r1-13, A5-14.
- 근거 추가: A7-05(S 격자를 MTC 이후 띠로), A1-M01(같은 바이트 주장), Q-03·Q-04(판정 자는 측정한 하네스 표류와 구간 반폭보다 커야 하고, 모든 팔은 같은 블록에서 교대), Q-23(v3.1 「다음」 4항 가운데 H 예측 정의).
- 할 일: `g3/v33/PROTOCOL_stage4_DRAFT.md`. S 격자는 A1에서 만든 ML-DSA·MTC 크기 표를 바탕으로 약 6.2, 7.7, 8.0, 9.0 KB 띠를 넣고 큰cert 셀은 "drop-in PQ X.509 최후 수단 시나리오"로 이름을 바꾼다. 같은 바이트 패딩 대 패리티(X1 형식)를 확증 가설 하나로 둔다. H1 유지. H2: 비열등 한계 |c| ≥ B, 번인 사전 등록, 층당 단위 ≥ 5, 독립 궤적 ≥ 4. H3: 구조 가설(고정 팔끼리)과 정책 가설(비교 정책의 실제 행동 분포 시뮬레이션) 분리. H4′: 봉인 전 정한 전역 고정 (0,3,1) 대비 HCT와 서버 계수 바이트, 사전 계산한 적응 상한이 2B를 넘는 셀만. 보류 추첨: RTT {20, 80, 120} × 업링크 {0, >0} 층화, 예측이 같은 셀 쌍 제외, 개발에 쓴 모든 셀(X 측정 셀 포함) 제외. 예상 소요 시간.
- 하지 말 것: 봉인, 추첨 실행, 확증 측정 실행(도현님 결정).

### R3 알고리즘 지도 문서 (45분)
- 근거: A6-12, A6r1-16, A4-10, Q-12.
- 추가: gen33 사본의 `padfec/policy.py` `expected_rounds` 독스트링과 `decide_v2` 주석의 모형/실측 비 수치가 서로 다르고(1.02~1.07 대 1.01~1.02) 212%는 산술도 틀렸다(Q-12). gen33 사본에서 수치를 지우고 결과 파일을 가리키는 문장으로 바꾼다(코드 동작은 바꾸지 않는다, 관문으로 확인).
- 할 일: `docs/v3_algorithm_map.md`. 수량마다 Python 함수:줄, Go 함수:줄, 그 값을 고정하는 시험 이름. 대상: A_pre, 1-RTT 조건, J3와 실패 가지, 꼬리 항, arrivals 우도, 등급 경계, CUSUM, 사전·hazard, S 보정, J_TIE와 예산, 보류 복호 규칙. 이름이 실제로 있는지 검사하는 스크립트.
