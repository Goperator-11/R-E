# S2 R-E 위생 결과

2026-11-02 정정: 아래 본문의 clone 폴더 `C:/dev/R-E-wt/hygiene-clone-check`는 지금 없다. 카드 S2.2는 clone을 스크래치에 만들라고 했는데 이 폴더를 R-E-wt에 남긴 것이 감사 A-E6이었고, 2026-11-02 V33FIX 루프 묶음이 고유 작업이 없음을 확인한 뒤 세션 스크래치로 옮겼다(`C:\dev\codex_handoff\v33\runs\v33fix\workflow_reports\E-loop.md`). 맨 아래 확인 명령은 새 clone을 임시 폴더에 만들어 확인하는 절차로 바꿨다. 같은 날 이 절차로 hygiene 브랜치(85b00b6)를 다시 확인했고 `status` PASS, 92파일 중 92개 일치였다(묶음 G 기록, `docs/V33FIX_testbed.md` 통합 정리 절).

R-E main의 HEAD는 6bbd11f8e7ebd7911a4f2e33fba7a8e6e9383937이며 작업 트리는 깨끗하다. 변경은 C:/dev/R-E-wt/hygiene와 C:/dev/R-E-wt/next에만 커밋했다. 공유 git 메타데이터에는 요청된 worktree·브랜치·태그가 추가됐다. 보호 main 파일, 원격, 과거 세대 원본은 바꾸지 않았다.

| 작업 | 커밋 | 검증 |
|---|---|---|
| 루트 LF·바이너리 속성 | 59d28339980b82927c398568ed2f75134d072991 | renormalize 기존 내용 변경0파일, 속성 파일만 변경 |
| README 최종 판정·봉인 확인 도구 | 85b00b605ed9a3f445028570047ca2a27bcc55a3 | 원자료18통과·6실패·p6 stale·p16 재실행 이력 확인 |
| next 원본 보관 | 2d5938b3405b7add1f1ccd7cb766865847bb8c6c | 290파일·25111699 B 원본·사본·git blob SHA 모두 일치 |

core.autocrlf=true로 C:/dev/R-E-wt/hygiene-clone-check에 새 clone을 만들었다. 원본 바이트 대조는 stage3의31+14=45개, stage2의29+9=38개, stage0의3+6=9개로 합92개가 일치했다. gen31 빌더의18소스 지문도 6284fdcf2d324bae4aee6aef56d7f339aa01c3b267e3aa3225277e7c87b3ade4로 보존값과 같았다. 빌더는 실행하지 않았다. 절대경로 개발 자료와 외부 바이너리는 이 clone 검사의 범위 밖이며 S1 보존 manifest를 사용한다.

README는 최종18통과·6실패(p8 p10 p15 p17 p18 p20), p6 미실행으로 바꿨다. loop2의 p6.status만 보면 과거 done이지만, 최종 fixloop_triage는 stale로 분류한다. p16은2026-10-01 17:51 실패 뒤2026-10-02 03:36 재실행에서 통과했다. fixloop의 마지막 바퀴2026-10-02 04:36:15도 통과18이다. 봉인 세대 README는 고치지 않았다. 새 tools/verify_seals.py는 상대경로 봉인 파일을 읽어 JSON으로 결과를 출력한다.

next는 원본의 캐시·실험 파일까지 그대로 보관했다. archive 브랜치의 해당 경로만 -text로 지정해 CRLF도 보존했다. _combo_states를 찾는 git log -S가 보관 커밋을 반환한다. 정본에 merge하지 않았고 원본 폴더는 유지했다.

로컬 주석 태그4개를 만들었다.

| 태그 | 대상 커밋 | 범위 |
|---|---|---|
| gen2-frozen-4bab4a5 | 4bab4a59725ed5946c7173060115e89259edd747 | gen-2 동결 비교 기준, 폴더 pq_afec. |
| gen2-fix-73aa420 | 73aa4203c52eebac1eb1ce073b0b32f149768a44 | 10월 7일 gen-2 검토 수정, 폴더 pq_afec. 봉인 비교 기준 바이너리와 구분한다. |
| v3.1-stage3 | 6bbd11f8e7ebd7911a4f2e33fba7a8e6e9383937 | v3.1 3단계 봉인 자료의 폴더 pq_afec_gen31. |
| v3.2-dev | 6bbd11f8e7ebd7911a4f2e33fba7a8e6e9383937 | 실측 없는 v3.2 개발 폴더 pq_afec_gen32. |

gen33의 핵심351시험·548하위 검사 영수증은 모든 소스·로그 SHA가 같아 재사용했다. 정책·Go·측정 코드는 바꾸지 않았다. S2 검증 도구는 실제 새 clone의92파일로 실행했다.

다음 명령은 검토 뒤 사용할 수 있도록 적은 것이며 실행하지 않았다. D1에 따라 이번 반복은 로컬 커밋과 태그만 만들었다.

```powershell
git -C C:\dev\R-E push origin hygiene/2026-10-30 archive/next-2026-09-08
git -C C:\dev\R-E push origin refs/tags/gen2-frozen-4bab4a5 refs/tags/gen2-fix-73aa420 refs/tags/v3.1-stage3 refs/tags/v3.2-dev
```

확인 명령(봉인 확인은 2026-11-02에 새 clone을 임시 폴더에 만들어 확인하는 절차로 바꿨다):

```powershell
git --no-optional-locks -C C:\dev\R-E status --short
git -C C:\dev\R-E worktree list
$clone = Join-Path ([IO.Path]::GetTempPath()) ("R-E-clone-check-" + [guid]::NewGuid().ToString("N").Substring(0,8))
git -c core.autocrlf=true clone --no-hardlinks --single-branch --branch hygiene/2026-10-30 C:\dev\R-E $clone
python -I -B (Join-Path $clone "tools\verify_seals.py")
Remove-Item -LiteralPath $clone -Recurse -Force
```

`verify_seals.py`는 출력 JSON의 `status`가 PASS일 때 종료 0이다. clone은 R-E를 읽기만 하고, `--no-hardlinks`로 원본 객체 파일과 링크를 만들지 않는다.

근거 스크립트: s2_hygiene_v1.py, s2_archive_next_v1.py, s2_verify_and_tag_v1.py. 원자료와 경로·해시는 S2_hygiene_commits_v1.json, S2_next_archive_v1.json, S2_verify_v1.json에 있다.
