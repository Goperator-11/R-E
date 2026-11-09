# v33 감사 기록

이 폴더에는 2026-11-01 v33 감사의 지적 문서와 2026-11-06 최종 감사의 판정 JSON이 있다. [활성 정책의 알려진 한계](../FINAL_policy_limits.md), [보고서 주장 범위](../REPORT_CLAIMS_v33.md), [코드 지도](../CODE_MAP.md), [닫은 과제](../FINAL_closed_tasks.md)가 이 기록을 근거로 인용한다.

- [감사 색인](v33/findings/FINDINGS_INDEX.md)과 [2026-11-01 감사](v33/findings/v33audit_2026-11-01)의 B~G 여섯 갈래
- [quic-go 소스 감사](v33/findings/audit-quicgo-source.md)
- [2026-11-06 최종 감사](final_audit_2026-11-06)의 code, measure, report 판정 JSON

기록에 적힌 현재형 문장, 시험 수, 후보 상태는 작성 시점 값이다. 활성 정책과 최신 측정 결과는 위 정본 문서를 따른다. 기록 문서는 원문 바이트 그대로 두었고, 아래 명령으로 확인한다.

```sh
cd docs/loop_record
sha256sum -c SHA256SUMS.txt
```

루프 운영 기록(과제 카드, 결정 장부, 프롬프트, 일지, A·H 갈래 감사)은 2026-11-08에 저장소에서 뺐다. 원문은 커밋 `4f26a51`에 있다.
