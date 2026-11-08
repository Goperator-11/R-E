# 루프 결정과 감사 기록의 사본

원천 카드의 "2026-11-02 시점 사본, 원본은 수정하지 않는다"는 옛 루프 기록의 안내다. 실제 복사는 2026-11-07 KST에 했고, 원본은 수정하지 않았다. 2026-11-02 당시 바이트로 되돌린 사본이라는 뜻은 아니다. 파일별 출처와 복사 시점 SHA256은 [source map](SOURCE_MAP.json)에 있다.

[v33 결정](v33/state/DECISIONS_NEEDED.md), [과제](v33/prompt/TASKS.md), [추가 과제](v33/state/EXTRA_TASKS.md), [상태](v33/state/LOOP_STATE.json)는 옛 내부 ID의 근거다. [CONTEXT](v33/prompt/CONTEXT.md)와 [기존 감사](v33/findings/v33audit_2026-11-01), [감사 색인](v33/findings/FINDINGS_INDEX.md)을 함께 보존했다. [현재 결정 목록](final/state/DECISIONS_NEEDED.md)과 [결정값](final/state/DECISIONS.json)은 이번 복사 시점의 기본값이며 이후 상태와 다를 수 있다. [2026-11-06 감사](final_audit_2026-11-06)에는 이번 루프의 findings 원본을 모두 복사했다.

기존 기록 문서의 경로와 표현은 바꾸지 않았다. source map의 source와 destination으로 과거 경로를 현재 사본에 연결한다. 기록에 적힌 현재형 문장·시험 수·후보 상태는 작성 시점에만 해당한다. 활성 정책이나 최신 측정 결과는 후속 정본을 따른다.

사용자 경로는 원문에 남아 있다. D62의 비공개 유지·LICENSE 없음·gen33 이력 비배포 기본값을 따른다. 공개 전에는 이 기록을 제외할지와 사용자 경로를 검토해야 한다. 완전한 개인키·주요 token 형식·PEM 파일은 복사 전 검사에서 발견되지 않았다.

새로 쓴 이 안내문은 문서 검사 대상으로 삼고, 바이트 동일 원문 사본은 SHA256으로 대조한다. 원문의 용어·과거 경로를 문서 검사에 맞춰 고치지 않는다. 증거 파일은 [증거 사본 안내](../../g3/v33/evidence/final/README.md)에 있다.

```sh
cd docs/loop_record
sha256sum -c SHA256SUMS.txt
```
