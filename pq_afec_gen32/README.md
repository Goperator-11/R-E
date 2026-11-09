# PAD-FEC v3.2 development

이 폴더는 `C:\dev\pq_afec_gen31`의 v3.1 소스에서 만든 개발 사본이다. 정책 버전은 `v3.2-dev`, 저장 상태 버전은 3이다. v3.1의 측정 자료와 봉인 파일은 원본 폴더에 있다. 이 사본에는 실측 원자료를 복사하지 않았다.

학습에 쓰지 못하는 관측에서도 목적지 손실 사후분포의 위험률 전이를 한 번 진행한다. 우도 갱신을 생략한 관측은 손실이 없었다는 증거로 쓰지 않으며, 위험률 혼합 가중치를 유지한다. 정보가 있는 관측은 기존처럼 전이와 우도를 한 번씩 적용한다. `stats.predict`가 진행 횟수를 기록한다.

감시층은 행동 잔차 창의 중앙값에서 공통 잔차 창의 중앙값을 뺀 값으로 경보와 가산 비용을 계산한다. 경보 중인 행동의 성공 잔차도 공통 창에 넣는다. 문턱, 창 크기, 해제 주기, 재평가 주기는 v3.1과 같다. 중앙값은 평균 지연이나 꼬리 위험의 검증을 대신하지 않는다.

전송 입력과 복원 캐시도 검사한다. `c_pkt`는 유한한 0 이상 1280 미만 값이어야 한다. 잘못된 확률 질량, 음수·비유한 입력, 창 크기를 넘긴 이력과 음수 카운터는 거부한다. 지정한 잘못된 입력은 관측·결정 상태를 바꾸기 전에 거부한다.

유한한 값이라도 내부 산술을 표현할 수 없으면 거부한다. 필요한 칸 수의 바이트 곱과 비행 바이트는 `2^53-1` 이하의 정확한 정수 표현 범위를 검사하고, 파생 전송 시간과 지연 비용도 유한해야 한다. 칸 수 계산은 최대 한 번 보정하며 무제한 증분 반복을 사용하지 않는다. 결정 계산 오류는 카운터 증가와 경보 해제를 남기지 않는다.

## 검사와 빌드

PowerShell에서 Python 회귀검사를 실행한다. 아래 명령은 모두 이 폴더에서 실행한다.

```powershell
Set-Location pq_afec_gen32
python -B -m pytest tests/test_core_regressions.py tests/test_padfec3_learn.py tests/test_padfec3_layout.py tests/test_padfec3_dev_regressions.py tests/test_padfec3_input_validation.py tests/test_padfec3_followup.py tests/test_replay_g3_dev.py tests/test_gen32_runner_isolation.py tests/test_adaptation_benchmark.py -q -p no:cacheprovider
python -B g3/policy3_reference_gen.py
wsl -d Ubuntu -- bash experiments/quicbed/build_gen32.sh --race
```

빌드 스크립트는 WSL의 `~/quicbed_gen32` 아래에 매번 새 작업 폴더를 만들고 vet, Go 검사와 빌드를 실행한다. 소스에서 삭제한 예전 검사 파일이 빌드에 남지 않도록 한 조치다. `--race`를 주면 같은 소스에서 race 검사도 실행한다. 지속 저장 바이너리는 `~/quicbed_gen32/bin/qamp`다. `/tmp/qamp_gen32/qamp`에도 설치하지만 WSL이 종료된 뒤에는 임시 파일이 사라질 수 있으므로 대조 검사에는 지속 저장 경로를 쓴다.

빌더 격리 검사는 임시 컴파일러를 사용해 과거 파일 혼입과 작업 폴더 정리를 확인한다. WSL에서 `python3 -B -m unittest discover -s tests -p test_gen32_build_staging.py -v`로 실행한다.

`m_max`는 자동 후보 생성의 패리티 예산이며 0 이상 4 이하 정수다. `max_steps`는 음수가 아닌 정수다. `max_ips`는 `None`이나 0이면 분석용 무제한, 양수이면 1200 이상 정수로 지정한다. 명시적인 `actions` 목록은 분석·재생용 후보 집합을 직접 지정하며 이 생성 옵션을 적용하지 않는다. 관측의 `later` 값은 `v3`, `g2`, `off` 중 하나여야 한다.

양수 `max_ips`의 자동 후보 생성은 패딩 크기와 패리티 개수의 상한까지 계산한다. 이 경로에서는 큰 `max_steps`를 주어도 상한을 넘는 단계를 반복하지 않는다. `max_ips=None/0`의 무제한 분석 모드와 raw `levers_s`는 여전히 `max_steps`에 비례해 계산한다. Python 비용 모형 캐시는 100,000개 계산 점까지 보관하며, FIFO로 제거한 값은 필요할 때 다시 계산한다. 이 상한은 Go의 100,000개 행 캐시와 단위가 다르다.

관측 처리에 실패하면 Python 학습 상태와 Go 목적지 캐시를 호출 전 상태로 유지한다. Go 캐시는 목적지 메타데이터도 검사하고 JSON 문서 뒤에 공백 이외의 데이터가 있으면 읽기를 거부한다. 유한한 두 잔차의 차이나 전이 기준값이 표현 범위를 넘는 경우도 상태를 바꾸기 전에 거부한다.

캐시는 한 프로세스에서 사용하고 빌더는 한 번씩 실행한다. 캐시 저장 임시 파일과 최종 빌드 출력에는 실행 간 잠금이 없으므로 같은 저장 경로를 여러 실행에서 동시에 쓰는 방식은 지원하지 않는다.

WSL에서 Go와 Python을 대조한다. 기준 벡터와 추가 난수 표본, 합성 학습 궤적을 검사하며 실제 네트워크 성능을 측정하지 않는다.

```bash
python3 -B experiments/gate_v3_parity.py --bin "$HOME/quicbed_gen32/bin/qamp" --out g3/gen32_parity.json
```

## 과거 관측 재생

`replay_g3.py`는 결정 전 예측을 관측 함수에 전달해 감시층을 실행한다. 과거 v3.1 저널을 읽는 모드에서는 실제 기록 행동과 새 코드의 결정을 따로 출력한다. 새 결정으로 연결을 실행한 결과가 아니므로 성능 차이나 새 정책의 실제 학습 궤적으로 해석할 수 없다.

```powershell
python -B experiments/replay_g3.py --recorded-v31 --journal C:\dev\pq_afec_gen31\experiments\state\p31_run1_S_bigcert_units.jsonl --out C:\dev\pq_afec_gen32\g3\development_replay.json --limit 1000
```

입력 저널을 출력으로 지정하면 거부한다. 새 관측 진단, 사후분포 요약과 예측 횟수를 함께 저장한다.

## 다음 측정

이 버전의 실제 성능은 아직 측정하지 않았다. v3.1의 H1 통과, H2·H3 실패, H4 기여 미확인 판정은 원래 자료의 판정으로 남는다. 새 확증에는 새 프로토콜, 이미 개발에 쓴 셀을 제외한 보류 조건, 새 봉인과 격리된 측정 경로가 필요하다.

과거 빌더와 `p21_gencompare.py`, `g31_probe.py`, `loop2.py`, `fixloop.py`, `forever.py`, `live_demo.sh`의 CLI는 이 사본에서 실행을 차단한다. 과거 자동 루프의 상태 조회도 차단한다. `padbed`를 불러올 때 결과·상태 폴더를 만들지 않으며, 바이너리 복사와 네트워크 설정·실행 진입점에서도 과거 실측을 거부한다. 기존 바이너리가 있어도 `--only-exact`로 과거 빌더를 건너뛰어 측정할 수 없다.

이 사본은 위에 적힌 회귀검사, 격리된 빌드, Python·Go 대조와 개발 재생을 지원한다. 전체 과거 파이프라인을 v3.2 측정기로 사용할 수는 없다. 차단 여부는 `python -B -m pytest tests/test_gen32_runner_isolation.py -q -p no:cacheprovider`로 검사한다. 이 검사는 네트워크 측정과 빌드를 실행하지 않는다.

GitHub 사본의 경로가 다르면 PowerShell의 `Set-Location`과 WSL의 `cd`를 체크아웃한 폴더로 바꾼다. 과거 저널은 저장소에 포함하지 않았으므로 재생 명령의 `--journal`에 보존한 외부 저널 경로를 지정한다. 테스트용 PKI 파일도 게시본과 배포 ZIP에서 제외한다.

## 합성 적응 벤치

`experiments/adaptation_benchmark.py`는 정책의 비용 모형으로 연결 결과를 만드는 개발용 장난감 벤치다. 기본 프로토콜은 조건 3개에서 공통 준비 32단계 후 같은 상태를 복제하고, 각 비교군을 480단계씩 실행한다. 손실률의 상승과 회복, 일정한 손실률을 다룬다. `full`, 손실 사후분포를 고정한 `frozen_loss`, 관측을 건너뛴 단계의 hazard 전이만 막은 `skip_hazard_ablation`을 비교한다. 관측 이력과 감시층, 결정 횟수는 모든 비교군에서 계속 진행한다.

```powershell
python -B experiments/adaptation_benchmark.py --out C:\temp\gen32_adaptation_benchmark.json
python -B -m pytest tests/test_adaptation_benchmark.py -q -p no:cacheprovider
```

원본·패리티 패킷마다 공통 균등 난수를 쓰고 경주 난수도 공유한다. 출력은 참 손실률에서 선택 행동의 기대 비용과 공통 후보 집합의 최소 기대 비용 차이인 `expected_regret_ms`를, 한 번 뽑은 `synthetic_cost_ms`와 구분한다. 이 모형의 회복 비용을 포함하므로 관측에는 `ok=True`를 전달한다. 준비 단계 비용은 비교에서 제외한다. 조건별·구간별 비용 차이는 모형 안의 기술 통계이며 검정과 신뢰구간을 계산하지 않는다. 네트워크 측정, 실제 HCT, v3.2의 실측 성능이나 H4 확증을 뜻하지 않는다.

조건 안에서 `k`, 서버 바이트와 RTT는 고정하고 패킷 손실은 독립이라고 가정한다. 첫 비행의 실패에는 실제 재시도 궤적 대신 모형의 평균 회복 비용을 쓴다. `frozen_loss`는 손실 분포만 고정하며 전체 적응을 끈 비교군은 아니다. 최소 비용도 공통 후보 집합 안의 값이다.

출력 JSON에 합성 자료 표시, `confirmatory=false`, 네트워크 측정 0회, seed, 입력·적용 프로토콜 해시, 소스 해시와 잡음 테이프 해시를 남긴다. `--protocol`로 별도 프로토콜을 읽고 `--seed`를 반복해 seed 목록을 바꿀 수 있다. `--out`은 필수이며 입력 프로토콜이나 계산에 쓰는 소스를 덮어쓰려는 경로는 거부한다. 결과는 임시 파일 작성 후 교체한다. 기본값은 비용 모형 안에서 구현과 ablation을 점검하는 작은 개발 사례이므로, 비교군 간 차이가 없어도 그대로 출력한다.
