# 최종 문서의 증거 사본

2026-11-07 KST에 F41이 원본 파일을 바이트 그대로 복사했다. 사본의 출처와 SHA256은 [source map](SOURCE_MAP.json), 현재 폴더의 검증 목록은 [SHA256SUMS.txt](SHA256SUMS.txt)에 있다. 각 결과의 관측 시점과 출처 종류는 원문을 따른다. 복사 시각은 측정 시각이 아니다.

스크립트에 적힌 절대 경로는 실행 당시 경로이며, 사본 위치에서 그대로 재실행할 수 있다는 뜻은 아니다. 사용자 경로가 들어 있는 원문도 보존했다. D62의 비공개 유지·LICENSE 없음·gen33 이력 비배포 기본값을 따르며, 공개 전에는 사용자 경로를 별도로 검토해야 한다. 완전한 개인키와 주요 token 형식을 검사했지만 모든 비밀 형식을 검출한다고 보장하지 않는다.

H1 원 판정은 [p31 판정 사본](p31_gencompare_decisions.json)에 있다. 숫자 감사·인증서 크기·가정 계산·L3 결과는 [기존 runs 사본](v33/runs), 독립 세계 평가 요약은 [A-eval 사본](v33/runs/v33fix/A-eval)에 있다. A-eval의 대형 원자료는 이 사본에 포함하지 않았다.

감사 위치표가 가리킨 g31_probe.json·g31_probe_console.log·replay_g3_dev.json 보존본은 각각 2 B이며 실제 측정 원자료로 사용할 수 없다. probe의 지정 필드 근거는 별도의 [F07 발췌](../../../../report_repro/g31_probe_excerpt.json)와 [원자료 위치표](../../../../report_repro/SOURCES.md)를 따른다. source map의 inventory_references는 이 보존본을 가리킨 과거 인용과 현재 사본을 구분한다.

위치표의 일부 P·W SHA256SUMS 인용은 실제 위치 열에서 G의 목록으로 연결됐다. source map은 그 대응을 그대로 기록하고 P 목록도 별도로 보존했다. 하위 폴더의 옛 SHA 목록은 당시 전체 작업을 대상으로 하므로 이 부분 사본에서 검증을 보장하지 않는다. 이 폴더 맨 위 SHA256SUMS만 이번 복사 범위의 목록이다.

기존 문서의 외부 경로는 작성 시점 기록으로 둔다. 새 정본은 이 사본과 [루프 기록](../../../../docs/loop_record/README.md)을 인용한다. 전체 정본의 인용 전환 확인은 F55에서 한다.

```sh
cd g3/v33/evidence/final
sha256sum -c SHA256SUMS.txt
```
