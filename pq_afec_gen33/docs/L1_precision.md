# L1 고정 N 정밀화

bench_learning_precision.py는 발행된 L1 개발 결과의 행동 비용 계산을 한 차례 더 정밀하게 계산한다. 원래 N=131072 보고서를 본 뒤 정한 작업이다. 같은 validation seed 850001의 앞부분을 다시 포함하므로 독립 재현이 아니며, 두 번의 구간 확인에 새로운 동시 신뢰 보장을 붙이지 않는다.

목표는 MC 행동당 N=1048576으로 고정했다. 이는 표본 수를 8배로 정한 것이며 정밀도가 8배 개선된다는 뜻은 아니다. 전체 family 100개 중 84개 MC에 적용하고 16개 구조적 결과는 frozen certificate에 따른 n=0 예외를 유지한다. 원래 19개 참조, 600개 원형 raw와 900개 L1 raw, 모든 정책·세계·seed·문턱·confidence·비교 목록은 그대로다. 중간 gate를 보고 멈추거나 N을 다시 탐색하는 인자는 없다.

명령은 plan, run, report로 나뉜다. 다음 명령은 인터페이스 예시이며 이 문서를 작성하면서 생산 계획이나 MC를 실행하지 않았다.

```powershell
python -I -B experiments/v33/bench_learning_precision.py plan --original-family <original-family.json> --original-family-sha256 <sha256> --original-report <L1_benchmark.json> --decision <L1_precision_decision.md> --effective-protocol <new-evaluation-protocol.json> --out <new-precision-plan.json>
python -I -B experiments/v33/bench_learning_precision.py run --precision-plan <new-precision-plan.json> --precision-plan-sha256 <sha256> --out <new-pool-directory> --workers 8 --time-budget-seconds 300 --loop
python -I -B experiments/v33/bench_learning_precision.py report --precision-plan <new-precision-plan.json> --precision-plan-sha256 <sha256> --pool <new-pool-directory> --out <new-report.json> --markdown <new-report.md>
```

plan은 원래 family, JSON 보고서, 그 경로에 .published.json을 붙인 발행 marker, 원래 protocol과 frozen reporter의 SHA를 고정값에 대조한다. 원래 execution_plan을 실제 호출해 전체 raw·참조를 원래 protocol로 검증한다. 원래 pool도 잠금 안에서 다시 검증하고, 실제 receipt·result·checkpoint attestation이 원래 발행본과 같은지 확인한다. 운영 결정 Markdown의 SHA는 계획 입력에 포함된다.

평가 전용 protocol은 원래 객체의 oracle.validation_samples 하나만 바꾼 새 파일이다. 전체 객체를 exact 대조하므로 다른 필드를 몰래 바꿀 수 없다. 원래 protocol이나 raw·참조의 protocol_sha256은 변경하지 않는다. 새 행동 manifest만 새 평가 protocol을 가리키고, 별도의 reference_lineage는 19개 참조가 원래 protocol에서 왔음을 기록한다.

새 precision plan은 원래 전체 입력, 원래 발행물, 운영 결정, 평가 protocol, wrapper와 frozen source 지문을 묶는다. 자기 파일 SHA는 자기 내용에 넣지 않는다. 저장한 뒤 <plan>.published.json을 마지막에 쓰며 run/report는 이 marker를 필수로 확인한다. execution metadata는 plan과 marker의 실제 SHA까지 입력 inventory에 추가한다.

run/report는 저장된 plan 전체를 다시 만든 값과 대조한다. run은 frozen pool.run_pool을 호출하며 worker는 1개부터 8개까지 허용한다. 새 pool은 비어 있어야 하며 원래 pool과 겹칠 수 없다. N은 checkpoint identity에 들어가므로 원래 checkpoint를 복사하거나 identity를 바꿔서 이어 쓰지 않는다. 새 pool은 connection 0부터 고정 seed를 다시 계산한다.

report는 frozen validate_pool_locked와 aggregate_learning을 재사용한다. 결과 검증·집계·발행 동안 새 pool의 잠금을 유지하고, 입력과 source의 SHA를 발행 전후에 대조한다. 100개 결과와 원래 84/16 job 분류가 모두 맞아야 한다. nonstructural 결과의 실제 n은 목표 N이어야 하며 n=0은 실제 구조 certificate로만 인정한다. 서로 다른 행동의 표본분산 0에 따른 null, 동일 행동의 정확한 차이 0, 원래 참조의 selection gap null 규칙을 유지한다.

새 MC 평균으로 각 seed의 기대 차이와 구간을 전부 다시 계산한다. 기존 seed 구간에 새 MC 폭만 끼워 넣지 않는다. 원래 raw의 실현 HCT와 관측 궤적은 변하지 않는다. 직접 대조에서 원래 참조가 소거되는 규칙과 절대 후회에서 원래 선택 오차가 필요한 규칙을 모두 유지한다. 이 정밀화는 원래 선택 오차가 null인 문맥의 절대 최적성 상한을 새로 증명하지 않는다.

JSON·Markdown과 마지막 publication marker는 새 경로에만 쓴다. 입력 누락, 불완전 pool, source 변경, 집계 또는 쓰기 오류가 있으면 성공 marker를 만들지 않는다. 쓰기 도중 실패해 남은 파일은 완료 보고서가 아니며 자동 덮어쓰지 않는다. complete의 CLI 종료 코드는 0, failed는 2, partial은 3이다. 검증 예외는 성공 코드로 바꾸지 않는다.

이번 생산 실행은 root의 runs/l1_precision_driver_v1.py와 함께 사용한다. 이 driver는 최초 plan/run/report 전용이며 기존 pool이나 receipt 재사용을 거부한다. frozen pool이 complete receipt를 쓴 직후 wrapper의 마지막 source/input 검사가 실패할 수 있다. wrapper report 자체가 root driver의 실패 기록을 읽는 것은 아니므로 driver의 직전 run 성공 receipt 연결도 발행 조건이다. 자동 재시도나 기존 receipt 덮어쓰기는 하지 않는다.

정상 --loop은 같은 실행 안에서 partial checkpoint를 이어 목표 N까지 진행한다. 중단 후에는 같은 plan·목표에서 wrapper --resume을 사용할 수 있지만, 새 실행 receipt를 보존하고 report가 그 실행을 연결하도록 별도 root driver가 필요하다. 완료 뒤 미확정을 해소하려고 N을 더 늘리는 운영은 이 계약에 없다. pass/fail/inconclusive를 모두 기록하고, 미확정을 통과로 바꾸지 않는다.

전용 시험은 World.sample을 금지한 합성 자료만 사용한다. N 외 변경, 원형 발행·참조·입력 연결, 1500 raw identity와 100행동 보존, 84/16 분류, plan 재구성·발행 marker, 원래 checkpoint identity 거부, 실제 frozen validator의 n·seed·family·certificate 거부, 선택 오차 null과 직접 상쇄, 새 평균에 따른 seed 구간 재계산, 잠금과 마지막 marker를 검사한다. 로그는 C:\dev\codex_handoff\v33\runs\L1_precision_units_01.txt에 보존한다. 최초 합성 시험에서 plan과 입력 fixture의 가변 partition 공유를 발견해 plan을 독립 복사하도록 고쳤으며 최초 실패 출력도 로그에 남겼다. 시험 통과는 생산 결과나 L1 채택을 뜻하지 않는다.
