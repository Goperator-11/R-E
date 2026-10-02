# PAD-FEC v3.2 development

이 폴더는 `C:\dev\pq_afec_gen31`의 v3.1 소스에서 만든 개발 사본이다. 정책 버전은 `v3.2-dev`, 저장 상태 버전은 3이다. v3.1의 측정 자료와 봉인 파일은 원본 폴더에 있다. 이 사본에는 실측 원자료를 복사하지 않았다.

학습에 쓰지 못하는 관측에서도 목적지 손실 사후분포의 위험률 전이를 한 번 진행한다. 우도 갱신을 생략한 관측은 손실이 없었다는 증거로 쓰지 않으며, 위험률 혼합 가중치를 유지한다. 정보가 있는 관측은 기존처럼 전이와 우도를 한 번씩 적용한다. `stats.predict`가 진행 횟수를 기록한다.

감시층은 행동 잔차 창의 중앙값에서 공통 잔차 창의 중앙값을 뺀 값으로 경보와 가산 비용을 계산한다. 경보 중인 행동의 성공 잔차도 공통 창에 넣는다. 문턱, 창 크기, 해제 주기, 재평가 주기는 v3.1과 같다. 중앙값은 평균 지연이나 꼬리 위험의 검증을 대신하지 않는다.

전송 입력과 복원 캐시도 검사한다. `c_pkt`는 유한한 0 이상 1280 미만 값이어야 한다. 잘못된 확률 질량, 음수·비유한 입력, 창 크기를 넘긴 이력과 음수 카운터는 거부한다. 지정한 잘못된 입력은 관측·결정 상태를 바꾸기 전에 거부한다.

유한한 값이라도 내부 산술을 표현할 수 없으면 거부한다. 필요한 칸 수의 바이트 곱과 비행 바이트는 `2^53-1` 이하의 정확한 정수 표현 범위를 검사하고, 파생 전송 시간과 지연 비용도 유한해야 한다. 칸 수 계산은 최대 한 번 보정하며 무제한 증분 반복을 사용하지 않는다. 결정 계산 오류는 카운터 증가와 경보 해제를 남기지 않는다.

## 검사와 빌드

PowerShell에서 Python 회귀검사를 실행한다.

```powershell
Set-Location C:\dev\pq_afec_gen32
python -B -m pytest tests/test_core_regressions.py tests/test_padfec3_learn.py tests/test_padfec3_layout.py tests/test_padfec3_dev_regressions.py tests/test_padfec3_input_validation.py tests/test_replay_g3_dev.py -q -p no:cacheprovider
python -B g3/policy3_reference_gen.py
wsl -d Ubuntu -- bash /mnt/c/dev/pq_afec_gen32/experiments/quicbed/build_gen32.sh
```

빌드 스크립트는 WSL의 `~/quicbed_gen32`에서 vet, Go 검사와 빌드를 실행한다. 지속 저장 바이너리는 `~/quicbed_gen32/bin/qamp`다. `/tmp/qamp_gen32/qamp`에도 설치하지만 WSL이 종료된 뒤에는 임시 파일이 사라질 수 있으므로 대조 검사에는 지속 저장 경로를 쓴다.

WSL에서 Go와 Python을 대조한다. 기준 벡터와 추가 난수 표본, 합성 학습 궤적을 검사하며 실제 네트워크 성능을 측정하지 않는다.

```bash
cd /mnt/c/dev/pq_afec_gen32
python3 -B experiments/gate_v3_parity.py --bin "$HOME/quicbed_gen32/bin/qamp" --out /mnt/c/dev/pq_afec_gen32/g3/gen32_parity.json
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
