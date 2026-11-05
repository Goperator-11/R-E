# S2 통합 계획

2026-11-01 현재 새 개발은 C:/dev/pq_afec_gen33의 v33 브랜치에서 이력을 남긴다. R-E main은6bbd11f에 유지했고 hygiene/2026-10-30과 archive/next-2026-09-08만 따로 만들었다. S1의 C:/dev/padfec_archive와 동결 바이너리가 기존 비교 기준이다. 이 계획은 구조 이동을 실행하지 않는다.

| 단계 | 산출물·검증 | 작업량 추정 | 주요 위험과 통과 조건 |
|---|---|---|---|
| Phase0 보존·식별 | 로컬 태그4개, 원본next290파일, LF 새clone 봉인92개, S1 원자료·바이너리 manifest | S1·S2에서 수행한 범위 완료 | 원격 보존은 D1·D2에 따라 미실행. PC 밖 백업은 아직 확보되지 않음 |
| Phase0 입력 목록 고정 | gen33 소스·상태·실행기·판정·원자료·외부 바이너리의 소유 경로와 해시 표 | 반나절 추정 | 같은 이름의 다른 세대 결과나 R-E에만 있는 gen32 development_validation20파일을 누락하지 않음 |
| Phase1 개발 구조 분리 | 새 로컬 브랜치에서 core/(afec,padfec,padfec3), testbed/quicbed, experiments/v33, configs/<gen>.json, results/<run-id> | 3~5일 추정, 감사 A6r1-08의 범위 | 경로·import·상대자료·지문 변경. 활성 v33만 이동하고 과거 세대는 원래 위치와 git 기록에 보존 |
| Phase1 동치 검증 | 경로 이동 전후 Python 전체시험, Go vet/test/race, 정책 관문, 고정 벡터·실행 manifest | 위3~5일에 포함한 추정 | 코드 이동과 정책 변경을 같은 커밋에 섞지 않음. 출력 바이트·선택·지문 입력 차이를 항목별 설명 |
| Phase1 실행기 전환 | 공용 testbed 제어와 세대별 config로 개발 실행 한 경로 정리 | 위3~5일에 포함한 추정 | 기존 봉인 실행·report-only 재실행 금지. 개발 smoke와 읽기 전용 검산으로 먼저 확인 |

기간은 실행 보장이 아닌 계획 추정이다. 여러 사람의 병렬 작업은 현재 요청 범위가 아니며, 팀이 역할을 정하기 전에는 별도 배정하지 않는다. v3.3의 남은 비용·관측 관문과 측정 준비 중에는 Phase1 구조 이동을 시작하지 않는다.

과거 태그를 별도 worktree로 꺼내는 작업과 과거 빌더 실행은 구분한다. 현재 build.sh·build_g3c.sh는 고정 설치 경로를 쓰므로 태그 worktree라고 안전해지지 않는다. 향후 재빌드 도구는 소스와 설치 위치를 별도 임시 개발 경로로 지정하고 기존 동결 경로의 쓰기를 차단해야 한다. 우선 소스 지문을 재현하고, Go 버전·GOAMD64·의존성·경로·trimpath·buildvcs 차이를 기록한다. 같은 source SHA가 바이너리 SHA의 재현을 보장하지 않으므로 검증 전에는 새 빌드로 S1의 기준 바이너리를 교체하지 않는다.

현재 genconfig와 stage 빌드의 경로 분리를 재사용한다. 결과 manifest에는 커밋·dirty 상태·소스 및 바이너리 SHA·계획 SHA·seed·관측 방식·실행 시작/종료·실패·재개를 남긴다. 경로 이동으로 과거 manifest를 다시 쓰지 않는다. 봉인의 상대경로는 세대 루트 기준으로 확인하고 development_data_sha256의 절대 C:/dev 경로는 원래 위치·S1 manifest 대응표를 유지한다. 보호 폴더의 속성 변경·삭제·이동도 이번 계획에서 실행하지 않는다.

next의 p3 교대 측정을 합칠지는 D6에 따라 미정이다. 보관만 완료했으며 통합을 선택하면 gen-2 p3을 새 개발 계획으로 다시 측정해야 한다. R-E의 gen32 development_validation은 로컬gen32에 없는20파일의 정본으로 남긴다. main으로의 merge, push, Release 업로드, 확증 봉인, 최종 보고서 알고리즘 선택은 각각 D1~D4의 기본값을 유지한다.
