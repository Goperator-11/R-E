# M0 smoke 검증 기록

2026-11-06, F26. 실행 `final_m0_iter022_20261106`의 480연결과 24단위가 완료됐으며 [결과 JSON](../g3/v33/results/v33_dev_M0_final_m0_iter022_20261106.json)의 checks 29개가 모두 pass다. M0는 실행 경로와 고정 범위를 확인하는 development smoke다. 팔 간 성능 근거나 확증 결과로 쓰지 않는다.

모든 팔은 gen33 서버와 셀별 공통 인증서를 썼다. 동결 v3.1·gen-2 클라이언트도 이 서버에 연결했으므로 봉인 측정과 서버가 다르다. quic-go v0.61.0 테스트베드 한 곳, 합성 인증서, initial congestion window 32 packet, token·resumption 비활성 조건이다. C1은 표준 QUIC에 없는 서버 회신이다. 조건은 [선커밋 계획](../g3/v33/plans/final_bundle_v1.md), 전체 수치는 [생성 결과 문서](M0_result.md)에 있다.

## 고정 범위 확인

아래 HCT는 계획의 셀·고정 팔별 20연결 평균이다. 네 값 모두 실행 전에 정한 범위 안이다. 전체 480연결의 실패 행은 0개다.

| 셀 | 고정 팔 | HCT 평균(ms) | 계획 범위(ms) | 출처 종류 |
|---|---|---:|---|---|
| bigcert_l2 | m4L3 | 84.19155 | 60~130 | 개발 측정 |
| bigcert_l15 | m4L3 | 119.55780 | 60~170 | 개발 측정 |
| rtt200_l15 | m4L2 | 221.86275 | 200~300 | 개발 측정 |
| p11_l0 | m4L3 | 52.04155 | 45~60 | 개발 측정 |

tc 설정과 셀 전체 실현 손실, W·parity 크기, 고정 팔 바이트, none·C1 경로, 복구 계수, 공통 서버·DER 기준을 확인했다. bigcert 2%의 v31auto recovered는 0이며 계획대로 합격 판정 대상이 아니다. 손실 15%의 v31auto·g2auto recovered는 두 셀에서 모두 양수다.

gen33 client_scid는 320/320행이 서버 conn-log와 일치했다. 빈 값, 중복 client·server SCID, 미대응 client·server 행은 모두 0개다. 동결 클라이언트 160행에는 해당 필드가 없으므로 그 세대의 SCID 일치는 미확인이다. 서버 conn-log는 총 480행이며 완전성 검사도 통과했다.

v33c1의 feedback_wait_received는 네 셀 각각 20/20이다. RTT200 대기 한도는 500 ms이고, M0의 셀 전체 수신 기준을 적용했다. 동결 클라이언트 팔의 서버 fb_sent 합은 0이다. 본측정의 분류별 수신 기준은 후속 결과에서 따로 판정한다.

## 생존과 재현

[Windows launcher](FINAL_launcher.md)를 호출한 PowerShell은 측정 시작 전에 종료됐다. 실제 측정 상태를 종료까지 수집했으며 관측한 서로 다른 heartbeat 시각 사이의 최대 간격은 약 5.879초다. 같은 수집 구간의 WSL uptime은 97.63초에서 240.51초로 증가했고 감소한 표본은 없었다. Windows 감독자와 WSL은 정상 완료했고 DONE·결과 생성·SHA 확인 뒤 devbed가 잠금을 해제했다. 전원은 AC, 충전 중 덮개 설정은 0이었으며 설정은 바꾸지 않았다.

최초 SHA 목록의 221파일을 검증한 뒤 결과 JSON·문서·SHA 목록을 로컬 보존 폴더에 복사했다. 같은 저널과 인자로 report-only를 두 번 실행했으며 세 파일 모두 최초 바이트와 같았다. 재생성 뒤에도 SHA 목록의 221파일이 통과했다. 저장소에 추적된 PEM은 기존 12개 그대로다. 이번 측정 PEM과 원자료는 로컬 보존 경로 `~/v33_runs/final_m0_iter022_20261106/`에 둔다.

계획 JSON SHA256은 `74f58fbb6b0db5c30ef9abf0698ae13dd6bede861bef3215646e5ca3232154b6`, 계획 커밋은 `a8e9fdf63d173bcfcf8166f18da4ba57eb21f5c1`이다. 결과 JSON SHA256은 `d61a534375b6e9f24872c593360c2c34a35e28ebc7a8350ec6030f1271d2fb28`이다. 실행 전 동결 바이너리의 SHA·srcsha와 계획을 대조했고 실행 사본과 완료 자료의 식별값도 확인했다.

검증 스크립트와 출력은 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/`의 `F26_launch_monitor.py`, `F26_probe.py`, `F26_smoke_independent.py`, `F26_postcheck.py`, `F26_report_replay.py`, `F26_collect.py`, `F26_summary.json`, `F26_accept.txt`에 있다. 독립 원자료 검사의 2058개 항목과 추가 지문·tc·W·parity 검사의 628개 항목은 통과했다. 미확인 40개는 실제 idle 미관측 24개, 동결 SCID 미제공 8개, 동결 cache C1 검사 제외 8개다. 실행 생존과 SHA 재현은 별도로 확인했다.

## 남은 관측 한계

실제 mean_idle_ms는 절대 연결 시각이 없어 null·미확인이다(D79). feedback 대기와 설정 gap의 합을 실제 idle로 대체하지 않는다.

최종 상태 파일의 completed_units는 18에 머물렀다. 러너가 블록 시작 때 진행 수를 기록하고 마지막 블록 뒤 다시 갱신하지 않기 때문이다. 완료 저널과 결과는 24단위이며 DONE·생성 결과·SHA 검증도 완료됐다. 이 진행 표시 차이는 F44에 넘겼고 원자료와 러너를 수정하지 않았다.

최초 PowerShell 파일 호출은 실행 정책으로 측정 시작 전에 중단됐다. 같은 명령을 PowerShell 명령 인자로 실행한 뒤 smoke를 한 번 완료했다. 실행 정책, 계획, seed, 손실 일정, 판정 범위, Go·정책 코드와 동결 바이너리는 바꾸지 않았다. 측정 재개는 하지 않았다.

추가 문서 검사에서 JSON 저장·로드 뒤 두 one_rtt 분류의 표 순서가 바뀌는 오류를 확인했다. 출력 순서를 고정해 최초 생성 문서와 같은 바이트를 유지했고 저장된 JSON의 문서 대조도 통과했다. 집계 수치, 실제 측정과 원자료는 바꾸지 않았다.
