# X1 최소판 실행 준비

F28은 [선커밋 계획](../g3/v33/plans/final_bundle_v1.json)의 X1을 실행한다. quic-go v0.61.0, initial congestion window 32, 공통 gen33 서버와 셀별 공통 인증서 조건의 development 측정이다. confirmatory 결과가 아니다. 이 문서는 실행 전 조건과 완료 뒤 확인할 항목을 기록하며 측정 결과를 담지 않는다.

## 실행 범위

모든 팔은 W=1280, k=2, 양쪽 `-profile sealed31`, `-gap 50ms`, `-timeout 10s`, `-expect-k 2`, `-uplink-mbps 2`를 쓴다. `-ips`는 지정하지 않는다. 손실은 c2s에만 적용하고 s2c 손실은 0%다. token과 session resumption은 꺼진 조건이다.

| 셀 | certsize (B) | RTT (ms) | c2s 손실 | 팔 | 블록 × 팔당 연결 |
|---|---:|---:|---:|---|---|
| bigcert_l2 | 16000 | 50 | 2% | m4L3, trailing_junk4L3, pad4L3 | 39 × 40 |
| bigcert_l15 | 16000 | 50 | 15% | m4L3, trailing_junk4L3, pad4L3 | 28 × 40 |
| rtt200_l15 | 9000 | 200 | 15% | m4L2, pad4L2 | 16 × 20 |

계획을 전개한 합계는 233단위, 8680연결이다. 측정한 연결 수와 구분한다. 기본 parity 팔에 trailing junk는 `-corrupt-parity 3`, padding은 `-pad-junk`를 더한다. hold, dup, k-inflate, Initial 확대 팔은 이 최소판에 없다. BL-08의 선택 띠 셀은 F31 범위다.

## 입력과 시작 확인

계획 JSON의 SHA256은 `74f58fbb6b0db5c30ef9abf0698ae13dd6bede861bef3215646e5ca3232154b6`이다. 입력은 [완료 M1 결과](../g3/v33/results/v33_dev_M1_final_m1_iter024_20261107.json)이며 SHA256은 `490b4dc7ecc6869bb83ff7411747ecb218e19195f05e607cb63cd9793b065559`이다. M1의 실행 상태는 판정 통과, A/A 통계 상태는 판정 가능이다. [M1 문서](M1_result.md)의 자는 1.1885561905999296 ms이고 X1 bigcert 2%에만 적용한다. 15%와 RTT200에는 A/A 자를 적용하지 않는다.

실행 ID는 `final_x1_iter027_20261107`로 정했다. [Windows launcher](FINAL_launcher.md)에 X1 과제와 위 M1 결과를 전달한다. 실제 시작은 launcher 접수 뒤 측정 heartbeat의 갱신, devbed 생존, F28 잠금으로 확인한다. 시작 전 전원 상태를 기록하며 전원 설정은 바꾸지 않는다.

계획·M1 입력·전체 단위의 명령 대조는 로컬 보존 도구 `C:/dev/codex_handoff/final/runs/F28_prelaunch_verify.py`와 출력 `F28_prelaunch.json`에 있다. launcher 명령과 상태 관측은 같은 폴더의 `F28_launch.py`, `F28_receipt.json`, `F28_start_samples.json`에 남긴다. 원자료와 PEM은 실행별 WSL 보존 폴더에 둔다.

## 완료 뒤 검증

DONE, 프로세스 종료, 결과 JSON, SHA 목록, 잠금 해제를 함께 확인한다. `runs/measurements/final_x1_iter027_20261107/X1_artifacts.sha256`은 로컬 보존 runs 아래 경로다. 보고서 재생성은 해당 실행의 원자료로만 수행하고 JSON·문서·SHA 목록의 동일 바이트 재현을 확인한다.

padding 팔의 서버 recovered=0, m4L3 팔의 recovered>0을 확인한다. first flight의 추가 바이트는 parity 팔에서 `first_flight_parity_bytes`, padding 팔에서 `extra_sent.first_bytes`를 읽는다. padding 팔의 `first_flight_parity_bytes`는 0이며, 실제 바이트 차이를 보고한다. CID에 따른 차이를 허용하는 계획에 1 B 단위 동일 조건을 덧붙이지 않는다.

세 셀에서 padding 빼기 parity의 짝 블록 HCT 차이와 95% 구간, 1-RTT 비율 차이, 서버 수신 바이트 차이를 대조한다. RTT200의 contrast ID에도 L3가 남아 있으므로 실제 x/y 팔인 pad4L2와 m4L2를 함께 표기한다. 구간이 0을 포함하면 차이를 확인하지 못했다고 쓴다. 비용은 `server_delta.bytes_in`과 conn-log에 근거하며 실패를 포함한 해당 client 행 수를 분모로 쓴다.

MS-14의 계획 커밋·SHA·최초 단위 시각, MS-02의 W·wire 상한, MS-32의 development·공통 서버·IW32 문구와 결과 숫자를 확인한다. 실제 idle은 D79에 따라 미확인으로 유지한다. 자동 결과 문서는 F28에서 검증하고 종합 주장과 보고서 정오표 반영은 F32가 맡는다.
