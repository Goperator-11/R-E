# X9 PTO 결과 검산과 해석

quic-go v0.61.0 테스트베드 한 곳, initial congestion window 32 packet의 development 측정이다. 두 클라이언트 모두 FEC off이며 같은 gen33 서버에 연결했다. 이 비교는 group별 PTO 관측을 다루며 PAD-FEC의 성능 비교가 아니다.

실행은 `final_x9_iter031_20261107`다. [자동 결과](X9_result.md)와 [결과 JSON](../g3/v33/results/v33_dev_X9_final_x9_iter031_20261107.json), [고정 계획](../g3/v33/plans/final_bundle_v1.json), [실행 준비 기록](FINAL_X9_run.md)을 함께 읽는다.

## 조건과 분석 분모

RTT 50 ms, uplink 제한 없음, W 1280 B, certsize 512 B, gap 8 ms, timeout 10 s다. 공통 서버에는 FEC on, sealed31, udp-path basic과 cert-file을 지정했다. 각 클라이언트의 tracer를 켰고 expect-k는 x25519가 1, X25519MLKEM768이 2다. c2s 셀은 c2s만 Bernoulli 손실 5%, both 셀은 양방향 각각 5%다.

완료 저널은 244단위·25,620연결이다. 각 방향·그룹에서 블록마다 앞 5연결을 제외했다. 분석 HCT는 실패 연결에 계획의 timeout을 적용하고 성공만의 평균과 구분한다. p99는 nearest rank다.

| 방향 | 팔 | 전체 연결 | 제외한 warmup | 주 PTO 유효 분모 | 주 PTO 누락 | HCT 평균(ms) | HCT p99(ms) | 실패 연결 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| c2s | x25519_off | 6405 | 305 | 6100 | 0 | 62.503787 | 254.315 | 0 |
| c2s | mlkem_off | 6405 | 305 | 6100 | 0 | 63.444644 | 208.367 | 0 |
| both | x25519_off | 6405 | 305 | 6100 | 0 | 77.015748 | 305.35 | 0 |
| both | mlkem_off | 6405 | 305 | 6100 | 0 | 82.157683 | 305.608 | 0 |

주 PTO 유효 분모 기준은 방향별 그룹당 6,095 이상이며 계획 분석 수 6,100과 구분한다. 원 측정은 qhct.go genCert의 자체 서명 P-256으로 보이며 DER 길이는 재지 않았고 qamp 하한 512 B를 썼다. 옛 표는 손실 0.5~5% 균일·버스트를 합친 값이라 이 5% 조건과 같은 양이 아니다.

## 두 PTO 정의

주 정의는 `observation.pto_count >= 1`이다. `memory_qlog` tracer의 `qlog_loss_timer_expired_lower_bound` 범위에 해당하며 기록된 loss timer 만료 횟수의 하한이다. 관측 누락이 없다는 검사만으로 모든 PTO를 빠짐없이 계측했다고 주장하지 않는다. 보조 정의는 `initial_datagrams > first_flight_datagrams + 1`이다.

| 방향 | 정의 | x25519 사건/분모 | MLKEM 사건/분모 | MLKEM-x25519(%p) | 95% 구간(%p) | 짝 블록 | 자유도 |
|---|---|---|---|---:|---|---:|---:|
| c2s | 주 | 310/6100 | 314/6100 | 0.065574 | [-0.790097, 0.921244] | 61 | 60 |
| c2s | 보조 | 310/6100 | 588/6100 | 4.557377 | [3.574845, 5.539909] | 61 | 60 |
| both | 주 | 634/6100 | 629/6100 | -0.081967 | [-1.124708, 0.960773] | 61 | 60 |
| both | 보조 | 634/6100 | 1022/6100 | 6.360656 | [5.117319, 7.603993] | 61 | 60 |

| 방향 | 팔 | 두 정의 비교 가능 연결 | 불일치 연결 |
|---|---|---:|---:|
| c2s | x25519_off | 6100 | 0 |
| c2s | mlkem_off | 6100 | 274 |
| both | x25519_off | 6100 | 0 |
| both | mlkem_off | 6100 | 393 |

주 정의의 두 구간은 0을 포함한다. 이 조건에서 group 간 주 PTO 사건 비율 차이를 확인하지 못했으며 동등성이나 효과 부재를 입증한 결과로 쓰지 않는다. 보조 정의의 차이는 추가 Initial 전송에 관한 진단이다. 이를 정확한 PTO 타이머 발생 차이나 그 인과효과로 바꾸어 쓰지 않는다.

## 실제 수집 확인

수집 검산 17,972항목을 통과했다. 완료된 각 attempt의 netem event와 tc_before·tc_after에서 c2s는 편도 delay 25 ms·손실 5%, s2c는 편도 delay 25 ms·손실 0%(c2s 셀) 또는 5%(both 셀), 양방향 rate 제한 없음을 확인했다. 이는 설정 확인이며 실현 drop률이 정확히 5%였다는 뜻이 아니다.

서버 conn-log와 클라이언트 SCID는 25,620/25,620 대응했고 fec_parse_fail은 0이다. not_accepted 1,262는 서버의 별도 진단값이며 클라이언트 실패 수로 바꾸지 않는다. 모든 실행 명령은 고정 계획과 일치했고 중복 group 인자도 같은 값이었다. 두 셀의 실제 인증서 DER는 각각 512 B이며 P-256이다. 개인키는 실행 폴더 밖으로 복사하지 않았다.

행별 ips_eff는 모두 1280 B, 계측 parity datagram은 0개다. FEC off의 이 결과에는 양수 parity의 wire 크기 표본이 없다. packet capture는 수행하지 않았다.

## 결과 키와 재현

결과의 `x9_by_direction.c2s`와 `x9_by_direction.both`는 카드가 요구한 필드 이름을 제공한다. `pto_rate_x25519`와 `pto_rate_mlkem`은 주 정의의 rate, `diff_ci95`는 주 정의의 짝 블록 ci95다. 셋 모두 비율 단위이며 문서의 %·%p 표시는 100을 곱한 값이다. `units`에 단위를 기록하고 `effect_sign`은 MLKEM-x25519다.

`n_measured`, `warmup_excluded`, `pto_definition_mismatch`는 x25519_off·mlkem_off별 사전이다. 각각 주 정의의 n_valid, arm의 warmup_excluded, 두 정의의 definition_mismatch에 대응한다. 별도 추정이나 분모 선택을 하지 않으며, 원래 statistics.cells의 값과 명시 null을 그대로 복사한다. 세부 누락·불일치·보조 정의는 원래 중첩 필드에서 확인한다.

검산 스크립트와 실행 기록은 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/`의 `F29_iter034_statistics_verify.py`, `F29_iter034_collection_verify.py`, `F29_iter034_roundtrip.py`, `F29_iter034_alias_roundtrip.py`, `F29_iter034_documents.py`, `F29_accept.txt`에 있다. 숫자 전사값은 `F29_iter034_numbers.json`에 보존한다. 원자료와 PEM은 WSL 실행 폴더에 보존한다.

## 검정력과 남은 범위

계획의 검정력은 Bernoulli 분산 상한 0.25를 쓴 독립 비율 정규근사다. 양측 0.05, 목표 0.8에서 차이 1.5 %p의 필요 표본은 그룹당 17,442, 차이 3 %p는 4,361이다. 계획 6,100연결에서 근사 검정력은 각각 0.381033과 0.912075다. 실제 블록 상관과 탈락을 반영한 검정력 보장은 아니며 결과를 보고 블록 수를 늘리지 않았다.

M1 입력 SHA는 결과 JSON의 m1_result_sha256에 기록돼 있다. X9에는 다른 조건에서 얻은 A/A HCT 자를 적용하지 않는다. 실제 idle은 절대 연결 시각이 없어 D79의 null·미확인으로 유지한다. 완료 status의 completed_units 표시는 242/244이며, 완료 저널의 244단위와 구분한다. 재개나 재측정은 하지 않았다.

변경보고와 덱은 D12 기본값대로 수정하지 않는다. 보고서 정오표의 결과 선택은 F32에서 수행한다. 분모가 확인되지 않은 옛 PTO 비율과 z값은 근거로 인용하지 않는다.

## 사후 짝 대조(탐색)

결과 JSON의 `statistics.cells[].contrasts`가 비어 있어 [자동 결과](X9_result.md)의 팔 간 비교 절에는 HCT, 1-RTT, 서버 수신량의 차이가 없다. `report_repro/x9_paired.py`가 로컬 보존 WSL 실행 폴더의 X9 저널 `units_final_x9_iter031_20261107.jsonl`(sha256 29869e31267c3750859ba1137b2bd886903a2b4901e9601c833dd5925a51c140)과 계획(sha256 74f58fbb6b0db5c30ef9abf0698ae13dd6bede861bef3215646e5ca3232154b6)에서 block 61개의 짝 차이를 다시 계산했고, 결과 JSON(sha256 364a49f6d8273ac50f6e351a1b0723c020b2e7b0734f89c9cccc7b4d00f3ff7e)과 묶어 `g3/v33/results/v33_dev_X9_final_x9_iter031_20261107.paired.json`에 남겼다. WSL에서 원자료를 읽기만 하는 단일 프로세스로 돌렸다.

차이는 mlkem_off − x25519_off다. block마다 앞 5연결을 빼고, 실패 행의 HCT는 10,000 ms로 둔다. 1-RTT는 ok이고 HCT가 1.5 × RTT(75 ms) 미만인 행이며, netem uplink 제한이 없어 직렬화 항은 0이다. 서버 수신량은 측정 행과 SCID로 대응한 conn-log rx_bytes의 합을 측정 행 수로 나눈 값이다. 구간은 block 평균 차이의 Student t 95% 구간(df 60)이다.

| 방향 | HCT 차이 (ms) | 1-RTT 비율 차이 (%p) | 서버 수신량 차이 (B/연결) | 짝 block |
|---|---|---|---|---|
| c2s | 0.94 [-0.64, 2.53] | -4.56 [-5.54, -3.57] | 1,280.19 [1,267.48, 1,292.90] | 61 |
| both | 5.14 [2.66, 7.62] | -8.11 [-9.37, -6.86] | 1,319.18 [1,297.69, 1,340.67] | 61 |

같은 코드로 다시 낸 주 PTO 대조와 보조(추가 Initial) 대조는 결과 JSON의 `pto_contrast.primary`, `pto_contrast.auxiliary`와 평균이 같았고 구간 끝 차이는 1e-16보다 작았다.

이 값은 계획의 primary(PTO)가 아니고 결과를 본 뒤 계산한 탐색값이다. 보고서 본문에는 넣지 않는다. c2s에서 추가 Initial 비율 차이는 +4.56 %p [3.57, 5.54]로 비1-RTT 비율 차이와 크기가 같다. 같은 연결 사건을 두 번 센 것이라 서로 독립 근거가 아니다. 서버 수신량 차이에는 두 group의 first flight 크기 차이가 들어 있어 손실 비용만 따로 읽지 않는다.
