# W1 행동 평가 병렬 실행기

`experiments/v33/bench_action_pool.py`는 이미 선택된 oracle 행동을 기준으로 행동별 기대 HCT를 계산하는 실행기다. 계산은 기존 `oracle.evaluate_action`에 맡기고, 완료 판정은 기존 `bench_oracles.validate_oracle_result`를 호출한다. seed, 표본 수, 후보 집합, 구간 산술과 선택 oracle은 바꾸지 않는다. 새 oracle을 선택하는 기능은 없다.

W1 생산 실행의 전체 집합은 `C:\dev\codex_handoff\v33\runs\W1_action_family_plan.json`에 기록되어 있다. 이 계획은 raw 네 폴더의 680개 seed 실행에서 나온 19문맥, 81개 `(context, action)` 작업을 담는다. 전달받은 계획 SHA256은 `792e7935a57f512baf5cf052bb4973f0ba40e1e282507ed367a04be1dae629ca`다. 이 값과 파일 내용이 다르면 실행하지 않는다. 모든 19문맥의 기준 oracle이 완료된 뒤 사용한다.

## 같은 통계 집합을 유지하는 방법

실행기는 계획 파일에 적힌 raw 폴더를 전부 읽는다. 원본 `raw_summaries`로 실행 ID, trace SHA, 정책 audit를 검증하고, raw manifest의 embedded protocol, producer SHA, 현재 정책 fingerprint도 대조한다. 계산한 전체 action 목록, 실행 ID 목록, 문맥별 작업 수를 계획 파일과 비교한다. `--contexts`나 작업 subset 인자는 없다.

기준 oracle 폴더마다 build manifest의 모든 결과가 있어야 한다. 같은 문맥을 두 폴더에 중복 제공하거나 일부 결과가 없으면 거부한다. 기준 결과에는 원래 validator를 적용한다. 전체 프로토콜 문맥과 기준 결과 문맥이 같아야 한다. `chosen_action`을 평가 결과로 다시 선택하지 않는다.

`manifest.json`은 원래 순차 실행기의 actions manifest와 같은 형식이다. jobs는 전체 action 목록으로 만들고, `evaluation_family_size`는 항상 전체81이다. 모든 job의 평가 spec, checkpoint identity, 완료 result validator에 이 값을 전달한다. worker가2개이든3개이든, 이미80개를 완료했든 이 값은 줄지 않는다. 이 manifest와 `results/*.json`은 기존 보고서 입력으로 읽을 수 있다.

## 실행과 재개

항상 독립 CLI로 실행한다. Windows spawn은 main 모듈을 다시 불러오므로, 보호 조건 없이 top-level에서 `pytest.main`을 호출하는 보조 실행기 안에서 직접 `run_pool`을 호출하지 않는다. 실제 spawn 시험도 `python -I -B bench_action_pool.py`를 별도 subprocess로 실행한다.

필수 인자는 `--family-plan`, `--family-plan-sha256`, `--oracle-dirs`, `--out`이다. `--protocol` 기본값은 현재 저장소의 `g3/v33/bench_protocol.json`이다. `--oracle-dirs`에는 서로 겹치지 않는 완료 build 출력 폴더를 모두 전달한다. 입력 경로와 출력 경로는 분리한다. worker 수 기본값은2다.

```text
python -I -B C:\dev\pq_afec_gen33\experiments\v33\bench_action_pool.py
  --protocol C:\dev\pq_afec_gen33\g3\v33\bench_protocol.json
  --family-plan C:\dev\codex_handoff\v33\runs\W1_action_family_plan.json
  --family-plan-sha256 792e7935a57f512baf5cf052bb4973f0ba40e1e282507ed367a04be1dae629ca
  --oracle-dirs <완료된 build 출력 폴더 전부>
  --out <새 action 평가 출력 폴더>
  --workers 2 --time-budget-seconds 300 --loop
```

위 코드는 인자 배치를 보여준다. 실제 PowerShell에서는 한 줄로 입력하거나 인자를 배열로 전달한다. 이미 시작한 출력 폴더에는 같은 입력으로 `--resume`를 붙인다. `--loop`는 partial 작업을 다음 batch에서 다시 시작한다. 한 작업의 시간 예산은 연결 chunk 경계에서 확인하므로 정확한 벽시계 상한은 아니다. worker 수와 시간 예산은 다음 재개에서 바꿀 수 있고, 각 실행의 runtime 기록에 남는다. 원래 oracle의 chunk_size는 유지한다.

종료 코드는 전체완료0, failed2, partial3이다. 오류 예외는 traceback과 함께 비정상 종료한다. 전체완료는 계산 작업이 끝났다는 뜻이다. 성능 문턱 PASS나 근접최적 판정을 뜻하지 않는다. 통계적 미확정 상태는 원래 result 필드 그대로 남는다.

## 출력과 잠금

| 경로 | 내용 |
|---|---|
| `manifest.json` | 전체 jobs, family81, 원래 producer5파일 SHA, protocol SHA, 기준 oracle digests |
| `execution.json` | adapter SHA, manifest digest, 입력 파일 SHA 목록, family plan SHA, 문맥 digest |
| `runs/*.started.json` | worker 수, spawn 방식, Python 버전, 시간 예산, 실행 ID |
| `runs/*.finished.json` | complete/partial/failed, 완료·미완료 목록 또는 오류 |
| `attempts/*.started.json` | job, 실행 메타 digest, 이전 checkpoint hash, PID |
| `attempts/*.finished.json` | 상태, 새 checkpoint hash, 완료 result hash 또는 오류/traceback |
| `checkpoints/<job>.json` | 기존 oracle이 저장하는 독립 job별 재개 상태 |
| `results/<job>.json` | 기존 validator를 통과한 완료 결과 |
| `published/*.json` | 결과를 완성해 fsync한 뒤 공개할 때 쓴 원본 파일 |
| `progress/*.json` | 첫 chunk, 최종 chunk, 그 사이5초 간격의 보조 진행률 |
| `failures/*.json` | worker 프로세스 예외 등 future 실패 기록 |

pool 전체와 각 job에 OS 파일 잠금을 건다. 잠금 파일은 남겨 두고 프로세스가 가진 lock만 해제한다. 프로세스 종료 시 OS lock이 풀리므로 파일의 존재만으로 실행 중이라고 판단하지 않는다. 같은 job의 동시 실행은 거부한다. 검증된 완료 job은 재사용하고 새 attempt를 만들지 않는다.

완료 결과는 별도 파일에 배타적으로 생성하고 fsync한 뒤 같은 출력 볼륨에서 hard link로 `results/<job>.json`에 공개한다. 기존 파일을 덮지 않는다. hard link를 지원하지 않는 파일시스템이면 실패를 남기고 멈춘다. 부분 JSON을 정상 결과로 취급하는 fallback은 없다. 이 실행기는 기록을 정리하거나 삭제하지 않는다.

## 재개 거부와 실패 보존

재개할 때 입력 전체로 manifest를 다시 구성하여 기존 manifest 및 execution metadata와 정확히 비교한다. 원래 producer5파일, 프로토콜, family plan, adapter의 현재 SHA를 확인한다. 프로세스가 불러온 시점의 producer와 adapter SHA도 확인한다. 작업 전후에 같은 검사를 반복한다. pool batch 뒤에는 summary와 reference 입력 파일 해시를 다시 확인한다. 원본 raw trace는 준비 시 원래 raw validator가 기록된 SHA로 검사한다.

각 job은 started/finished 쌍, 이전 checkpoint부터 이어지는 해시, 현재 checkpoint 내용 해시와 oracle identity, 완료 result 내용 해시를 검증한다. 완료 결과는 다시 원래 validator로 검사한다. 알려지지 않은 result/checkpoint, 중복 완료, 미완료 attempt 기록을 발견하면 건너뛰지 않고 거부한다. checkpoint나 result의 수치만 바뀌어도 내용 해시가 달라져 거부된다.

일반 계산 예외는 traceback을 보존한다. 사후 소스와 checkpoint 계약을 다시 확인할 수 있으면 후속 `--resume`에서 그 job을 재시도할 수 있다. 소스 확인 자체가 실패했거나, 사후 검사 중 소스 파일을 읽지 못했거나, checkpoint 계약을 확인하지 못하면 해당 receipt에 `unattested=true`를 남긴다. 소스를 원래대로 돌려도 그 checkpoint를 자동 재사용하지 않는다. 아직 finished receipt가 없는 attempt도 조사 없이 재사용하지 않는다. 이런 경우 원본 오류와 자료를 남긴 채 별도 새 출력으로 재실행하는 것이 기본 복구 방법이다.

입력 변경을 batch 종료 검사에서 발견하면 전체 run은 failed지만, 먼저 끝난 result 파일은 보존된다. 기존 보고서 CLI는 이 실행기의 receipt를 검사하지 않는다. 따라서 failed pool의 결과를 곧바로 집계하지 않는다. 원입력을 복구하고 입력·출처·결과 전체를 다시 검증한 성공적 재개를 거친 뒤 집계한다. 원입력의 정당성을 회복할 수 없으면 별도 새 출력에서 시작한다.

기존 순차 실행기의 출력에는 이 adapter의 execution/receipt 계약이 없다. 해당 폴더를 이 실행기의 재개 대상으로 그대로 사용하지 않는다. adapter 소스가 바뀌면 SHA가 달라지므로 같은 출력에서 재개하지 않는다.

## 검증 범위

`tests/test_v33_bench_action_pool.py`는 합성 raw manifest와 기준 oracle을 만든다. 생산 raw나 진행 중 oracle을 실행하지 않는다. 같은 전체81 family에서 일부만 완료해도 family가 줄지 않는 경우, 중복 lock, 기준 결과 중복·미완료, 내용/출처 오염, 실패 기록 보존, partial 재개, 사후 소스 검증 실패, 진행률 간격을 검사한다. 별도 CLI subprocess에서 structural zero-loss 두 작업을 실제 spawn으로 실행하고 재개한다. 일반 MC 검사는 두 행동과8개 검증 표본의 합성 문맥만 사용한다.

시간 기반 진행률 제한은 기록 횟수만 줄인다. callback은 중단 신호를 반환하지 않고 원래 oracle의 누적 모멘트, checkpoint 주기, 연결 순서, seed와 표본 수를 바꾸지 않는다.
