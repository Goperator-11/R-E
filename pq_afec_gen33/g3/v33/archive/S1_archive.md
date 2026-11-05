# S1 원자료와 바이너리 보존

2026-10-30 KST. 구현 검증 결과이며 새 네트워크 측정은 없다.

`C:\dev\padfec_archive`에 원자료와 출처 자료를 복사했다. 원본은 이동하거나 고치지 않았다. 보존 폴더는 이후 추가만 허용한다.

| 검증 | 결과 |
|---|---|
| 보존 항목 | 378개, 모두 원본 해시·크기 일치 |
| 항목별 원본 크기 합계 | 782,982,028 B |
| 보존 항목 저장 크기 합계 | 307,939,606 B |
| stage3 고정·기록 파일 | 31/31, 14/14 일치 |
| stage3 개발자료 | 89/89 일치 |
| stage2 고정·기록 파일 | 29/29, 9/9 일치 |
| stage2 개발자료 | 23/23 일치 |
| 동결 qamp | g2, g3, g3b, g3c, gen32 5개 SHA 및 srcsha 일치 |
| gen2 출처 | 4bab4a5의 14파일 srcsha가 보존값 b1816779와 일치, staged 소스 5파일 CRLF 정규화 후 일치 |
| 핵심 pytest | 109개 및 하위 367개 통과, 17.29초 |

개발자료와 세대 자료가 겹치는 경로도 각각 보존했으므로 원본 크기 합계는 고유 자료 크기가 아니다. INDEX.json과 MANIFEST.sha256 자체의 크기는 위 항목 합계에 포함하지 않았다.

gen31/gen3의 state(backup 포함), results, g3 전체와 봉인에서 가리킨 소스 파일, 개발자료, verdict_v3.md, run_p31 래퍼 4개를 보존했다. jsonl만 gzip으로 압축했다. 원본 해시는 압축 전 바이트를 기준으로 한다.

WSL 사본은 `/home/scien/frozen/`의 SHA 이름별 폴더에 있다. 각 qamp는 실행 권한을 유지하고 쓰기 권한을 제거했다. 기존 바이너리와 원본 봉인 폴더의 권한은 바꾸지 않았다. gen-2의 당시 staged 소스, go.mod, go.sum도 `gen2_build_origin`에 복사했다. 바이너리를 다시 빌드하지 않았다.

검증기는 압축본을 `C:\dev\codex_handoff\v33\runs\s1_verify\check-qkjquw1x`에 풀어 원본 SHA-256과 크기를 대조했다. 검증 해제본은 지우지 않고 남겼다. `--report-only`는 실행하지 않았다.

## 범위와 남은 일

이번 보존은 같은 PC의 Windows 폴더와 WSL 안에 있다. 디스크 고장에 대비한 외부 백업은 아직 없다. 업로드는 D2 기본값에 따라 하지 않았다. 빌드 재현성 수정은 S3, 태그 생성은 S2에서 진행한다.

Go 모듈·컴파일 캐시, qamp 외 gen2 실행 파일, 전체 운영체제 백업은 범위 밖이다. 기존 파일과 충돌하면 도구가 덮어쓰지 않고 실패한다.

## 확인 명령

```powershell
python -I -B C:\dev\padfec_archive\tools\verify_archive.py
python -I -B C:\dev\codex_handoff\v33\runs\s1_origin.py
```

검증 원문은 runs/S1_verify.log, S1_gen2_origin.json, S1_pytest.log에 있다. 전체 매핑과 원본 해시는 archive의 INDEX.json, MANIFEST.sha256에 있다.
