# 개발 측정의 서버 수집과 C1 검사

[devbed.py](../experiments/v33/devbed.py)는 단위마다 서버 자료를 검사한 뒤 완료 블록을 기록한다. 결과는 development이며 confirmatory가 아니다. 아래 검증은 fixture에 관한 것이다. 실제 QUIC smoke와 C1 수신률은 F26, X6 결과는 F30에서 확인한다.

## 연결 로그와 자료 상태

[transport.py](../experiments/v33/lib/transport.py)는 팔·블록마다 새 attempt 디렉터리와 conn-log 경로를 사용한다. 기존 경로가 있으면 실행을 거부한다. 클라이언트가 끝난 뒤 계획의 `0.3+2×RTT/1000`초를 기다리고 서버에 SIGTERM을 보낸다. 비정상 종료, 강제 종료, 종료 요청 전 서버 이탈은 자료 없음으로 남긴다.

[report.py](../experiments/v33/lib/report.py)의 `read_conn_log(path)`는 UTF-8 JSONL의 원형을 읽는다. 잘린 마지막 줄, 빈 줄, 중복 JSON 키, 중복 연결 key, 빠진 계수와 잘못된 숫자를 거부한다. 최종 stats의 `conn_log.path`도 실제 읽는 경로와 같아야 한다.

`validate_server_unit(plan, unit, payload)`는 실제 로그 줄 수와 `conn_log.lines`를 대조한다. `errors`, `pending`, `conn_acct_evicted_lru`는 모두 0이어야 한다. `lines >= tls_accepted`를 확인하고, 클라이언트 실패 행이 없으면 `lines == client_rows`를 확인한다. `not_accepted = lines-tls_accepted`가 양수여도 이 값만으로 실패하지 않는다. client Finished datagram의 손실로 서버 Accept 수가 작아질 수 있다.

동결 클라이언트가 gen33 서버에 붙는 팔도 conn-log를 쓴다. 실제 동결 서버를 쓰는 M1 a/e만 최종 `stats.conns`를 읽는다. 그 서버가 제공하지 않는 `tls_accepted`, `feedback_version`, `fec_parse_fail` 등은 null로 둔다. 계획의 M1 g는 conn-log 생략 대조이며 다른 gen33 팔의 로그 누락에 이 예외를 적용하지 않는다. optional 실행 지원은 F31의 범위다.

연결 귀속에는 task, cell, trajectory, arm, phase, block, `block_across_phases`, unit key를 남긴다. phase마다 다시 시작하는 local block만으로 합치지 않는다. gen33의 `client_scid`는 로그의 SCID와 연결한다. 빈 값, 중복, 미대응은 진단에 남기며 줄 순서로 채우지 않는다.

서버는 단위마다 새로 시작하므로 `server_delta.bytes_in`, `parities`, `recovered`, `credit_parities`는 최종 서버 계수다. conn-log의 연결별 수신량과 이 총량을 더하지 않는다. 비용 분모는 같은 분석 범위의 클라이언트 행 수이며 `tls_accepted`로 바꾸지 않는다. F24가 비용과 분석 구간을 연결한다.

## 회신 설정과 분류

동결 클라이언트 팔은 서버 `fb_sent == 0`, C1 팔은 `feedback_version == 2`를 확인한다. 회신을 끈 gen33 팔도 `fb_sent == 0`이어야 한다. 위반하면 `unit_rejected` 사건에 검사 결과와 블록 key 목록을 기록하고 그 블록을 완료 저널에 넣지 않는다. 파손·누락은 자료 없음, 값이 있는 설정 위반은 판정 실패다. `fec_parse_fail`이 양수인 gen33 auto 팔은 자료를 남기되 checks 실패로 표시한다.

[observations.py](../experiments/v33/lib/observations.py)의 `unit_observations(plan, unit, payload)`는 gen33 행의 `flight_expectation.source == explicit`과 셀 또는 group의 명시 k를 검사한다. C1 행의 `feedback_wait_limit_ms`는 계획값과 같아야 한다. RTT200은 500 ms다. 실제 플래그는 [arms.py](../experiments/v33/lib/arms.py)가 [계획](../g3/v33/plans/final_bundle_v1.json)에서 만들며, C1 클라이언트는 개별 플래그와 셀의 `-uplink-mbps`를 사용한다.

one_rtt는 성공 행에 strict 비교식 `ms < 1.5×RTT + 8×pre_decision_bytes/(1000×uplink_mbps)`를 적용한다. rate가 0이면 직렬화 항도 0이다. 선행 padding은 `extra_sent` 계수로 읽는다. 분류별 C1 수신률은 해당 부류의 모든 행을 분모로 하고 `feedback_wait_received`를 센다. 행이 20개 이상이고 비율이 0.95 미만이면 해당 셀의 `c1_path_excluded`를 켠다. 표본이 부족하면 표본 부족으로 표시한다. smoke 셀 전체의 0.85 기준은 이 분류별 기준과 별개다.

F24는 완료 payload의 `collection.observations`들을 `summarize_observations(plan, unit_results)`에 전달한다. 이 함수가 셀·팔 전체 행으로 비율을 다시 계산한다. 단위별 제외 여부를 OR 하면 블록별 표본 부족 때문에 잘못 판단할 수 있다. 반환에는 전체, 손실 층별, one_rtt 분류별, 궤적별, 번인·번인 뒤 결과가 있다. 유효 RTT 비율은 경고이며 M0 checks에 넣지 않는다.

## 실제 유휴시간의 관측 한계

계획의 `mean_idle_ms`는 다음 연결 시작에서 현재 HCT 완료 시각을 뺀 값이다. 동결 qamp의 `handshake_end_ns`는 Dial 경과시간이고, 연결의 절대 시작·완료 시각은 행에 없다. `feedback_wait_ns`는 실제 feedback 대기만 기록한다. parity 대기, 정리·학습·출력과 다음 연결 준비 시간까지 복원할 근거가 없다.

따라서 전체·층별·one_rtt별 `mean_idle_ms`는 null, `idle_status`는 미확인, `idle_valid_samples`는 0이다. 실제 feedback 대기와 설정 gap의 합은 `mean_wait_plus_gap_ms`라는 별도 진단으로 낸다. 마지막 연결에는 같은 단위 안의 다음 연결이 없으므로 이 진단에서 제외한다. 실제 대기 대신 `feedback_wait_limit_ms`를 넣지 않는다. 단위 종료와 다음 같은 팔 단위 시작의 간격은 다른 팔 실행과 서버 재시작을 포함하는 별도 진단이다.

이 한계는 D79의 기본값이다. Go·동결 바이너리·계획 정의는 유지하며, X6의 실제 idle 차이 5 ms 기준을 통과로 표시하지 않는다. F24·F30이 미확인을 결과에 남기고 F44가 관측 한계를 기록한다. idle과 RTT 경고는 M0 checks가 아니다.

## 저장과 재개

완료 payload의 `collection`에는 서버 검사와 관측 분류를 함께 저장한다. 최상위 `server_delta`, `checks`, `execution_status`도 저장된 검사와 대조한다. 재개와 report-only는 원자료 SHA를 확인한 뒤 로그와 행으로 같은 검사를 다시 계산한다. 저장된 검사와 다르면 완료 자료로 인정하지 않는다.

자료가 없거나 블록을 버려야 하는 경우에는 원자료와 사건을 보존하고 실행을 중단한다. 같은 블록에서 앞서 끝난 팔도 완료 블록에 넣지 않으므로 재개 시 블록 전체를 다시 실행한다. C1 분류별 수신률로 인한 셀 제외는 이 실행 실패와 구분하며 F24 결과 생성기가 표시한다.

지정 완료 기준 시험은 `tests/test_v33_devbed.py::test_conn_log_roundtrip`과 `tests/test_v33_devbed.py::test_frozen_arm_block_rejected_on_feedback`이다. transport 반환값을 실제 수집 검사와 재개 validator에 연결하는 fixture도 있다. 검증 로그와 수치 생성 스크립트는 로컬 보존 폴더 `C:/dev/codex_handoff/final/runs/`의 `F23_verify.py`, `F23_summary.json`, `F23_accept.txt`에 둔다.
