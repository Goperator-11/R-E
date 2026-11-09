# L1 학습 벤치의 행동 평가와 보고

`experiments/v33/bench_learning_report.py`는 새 관측 모드의 원자료를 검증하고, 하나의 행동 평가 집합과 보고서를 만든다. 수집은 `bench_learning.py`가 맡는다. 기존 `bench.py`, `bench_action_pool.py`, `bench_oracles.py`, `bench_metrics.py`, `bench_report.py`, `oracle.py`, `worldsim.py`, `worldparams.json`은 바꾸지 않았다. 보고 모듈은 이 파일들의 고정 SHA를 검사한다.

이 작업은 W1 기준 결과를 읽은 뒤 진행한 L1 개발 분석이다. 새 관측 비교와 보고 보완이 기준 결과를 보기 전에 등록됐다고 주장하지 않는다. 새 생산 실행과 전체 Monte Carlo 계산은 실행 담당자가 별도로 시작한다.

## 입력과 정책 구분

`prepare_plan(overlay_path, raw_dirs)`는 수집기의 `load_overlay`와 `load_learning_runs(require_complete=True)`를 호출한다. 기본 프로토콜, 원형 v31/full 300개와 v32/full 300개, current의 none/c1/ideal 각 300개, 참조 19개를 검증한 뒤 계획과 검증된 입력을 돌려준다. 기본 프로토콜의 15개 하위 셀과 seed 31부터 50까지를 모두 요구한다. 누락, 중복, smoke, 알려지지 않은 모드는 최종 분석에 들어갈 수 없다.

원자료에서 current의 generation과 variant는 각각 `current`, `full`이다. 보고할 때만 사본의 generation을 `current_none`, `current_c1`, `current_ideal`로 바꾼다. 원자료 파일은 수정하지 않는다. C1은 주 결과이며 ideal은 특권적인 수신 정보를 쓰는 관측 상한 진단이다. none도 현재 L1 정책을 쓰므로 역사 v32와 같다고 가정하지 않는다.

원형 세계와 참조 선택 결과는 기본 프로토콜 아래 유지한다. 관측기는 정책에 도착 증거를 전달하며, 이번 overlay에서는 물리 세계의 전송 비용을 바꾸지 않는다. 이런 전제가 바뀌면 기존 참조와 원형 반사실을 재사용할 수 있는지 다시 정해야 한다.

## 전체 행동 집합

`freeze_family(overlay_path, raw_dirs, out)`은 검증된 1500개 seed 실행에서 `(context_id, action)`의 합집합을 만든다. 모든 문맥을 포함해야 한다. 같은 행동이 여러 세대나 관측 모드에 나와도 하나의 평가 작업이다. 계획에는 정렬한 작업 목록, 참조 행동, 참조 결과 digest, 전체 실행 식별자, 전체 집합 크기와 입력 SHA 목록을 기록한다. 파일은 배타적으로 새로 만든다.

집합 크기는 실제 전체 입력에서 정한다. 모드별 또는 프로세스별 작업 수, 남은 작업 수로 줄이지 않는다. 기존 W1의 81개 행동 평가 구간을 새 집합의 구간으로 바꿔 쓰지 않는다. 모든 행동을 새 전체 집합의 보정 아래 다시 평가한다. 참조 19개는 재선택하지 않는다.

`execution_plan(family_path, family_sha256)`은 저장한 계획의 파일 SHA를 확인하고 전체 입력에서 계획을 재구성해 완전히 일치하는지 검사한다. `run_family`는 이 계획을 frozen `bench_action_pool.run_pool`에 직접 전달한다. worker 수와 시간 예산은 실행 기록에 남고 후보, seed, 표본 수, 구간 계산을 바꾸지 않는다.

실행 metadata의 `adapter_sha256`은 실제 실행하는 frozen pool의 SHA이다. `planner_sha256`은 새 보고 모듈의 SHA이며, 새 원자료 schema를 엄격한 수집기 loader로 검증했다는 사실을 별도로 기록한다. 원형 pool의 구형 원자료 parser가 새 입력을 검증했다고 표시하지 않는다.

`inputs_sha256`에는 overlay, 기본 프로토콜, 원형 import receipt, 정책 snapshot receipt와 모든 정책 사본, 역사 정책 파일, 원형과 새 manifest/summary/trace, 19개 참조, 새 seed별 시작·완료 receipt, 관측기, 수집기, 고정 생산자, 보고 규칙, 새 보고 모듈이 들어간다. 수집기가 제공한 전체 목록에 보고 모듈의 자체 SHA를 추가한다. 필수 출처가 빠져 있거나 파일 내용이 바뀌면 거부한다.

## 통계와 판정

보고서는 5개 정책/관측 구분과 15개 하위 셀의 75개 그룹을 만든다. 그룹의 기대 차이, 관측 지표, B5 적응 사례와 고정 팔 진단은 frozen `aggregate`를 그대로 사용한다. 비교는 각 current 모드 대 v32, 각 모드 대 v31, c1 대 none의 7쌍을 셀마다 계산하므로 총 105개다.

기대 차이는 독립적으로 평가한 행동 비용을 각 seed의 실제 선택 빈도로 가중한 값이다. 고정 선택 참조에 대한 차이이며 참 최적값 대비 후회를 정확히 아는 것은 아니다. seed별 기대 차이의 Student t 구간, 여러 seed에 공유되는 행동 평가 MC 폭, 참조 선택 오차를 각각 보존한다. 공통 MC 폭을 seed 수의 제곱근으로 나누지 않는다.

직접 짝비교는 동일 seed와 동일 문맥 비중을 요구한다. 후보와 기준의 행동 빈도 차이를 사용하므로 참조 항은 상쇄된다. 평균 빈도 차이가 정확히 0인 행동의 MC 항도 상쇄된다. 서로 다른 행동에서 관측된 분산이 0이라는 이유로 정확한 비용으로 처리하지 않는다. frozen 검사기가 미확정으로 둔 폭과 선택 경계는 null을 유지한다.

`noninferiority.pre_post_vs_v32`와 `noninferiority.w1_noninferiority_vs_v31`는 분리한다. 각 모드에서 모든 하위 셀이 기존 0.5ms 회귀 한도를 통과해야 해당 비교를 통과로 기록한다. 한 셀의 확정 실패를 다른 셀의 개선으로 상쇄하지 않는다. C1 대 v32와 C1 대 v31이 주 비교다. 0.5ms 비열등 통과는 개선 입증을 뜻하지 않는다. 음수 차이는 더 빠른 쪽이며, seed 구간과 공통 MC 폭을 합친 경계가 0을 포함하는지도 표에서 볼 수 있다. 실현 HCT 짝차는 별도 진단이고 기대 비용 판정을 대체하지 않는다.

B1의 기대 차이와 p 편향, B2의 기대 차이, B4의 서버 추가 바이트, B5의 2관측 이내 적응 규칙은 원형 그대로다. B5는 연속 결정 확인, 우측 검열과 미확정 사례도 모두 보존한다. 집합별 99% MC 근사 경계와 95% seed 구간을 결합했다고 전체 동시 95% 보장이 되는 것은 아니다.

B3/B4의 p 수렴은 기존 high-phase 후미의 `p_bias_high_phase`를 사용한다. 이 두 셀은 참 c2s 손실이 0이므로 해당 값이 결정 전 `p_mean`과 같다. 기존 후미 관측 개수를 그대로 요구하고, 그 평균의 구간으로 `p_mean < 0.01`을 판정한다. 마지막 관측 뒤 `final_state.p_mean`은 별도 진단으로 남긴다. 이를 결정 전 수렴값 대신 쓰지 않는다.

## 관측 진단의 분모

current의 각 그룹은 성공과 실패를 모두 포함한 전체 연결을 분모로 사용한다. 도착 우도, 등급 우도, 예측만 수행한 경로, 증거 출처, 사용 가능 여부, fallback 이유, truncation, 회신 생성·수신, 관측 전멸과 평가 전용 전멸 진단을 집계한다. 없는 필드와 명시적인 null을 구분해 빈도를 기록한다.

우도에 실제 사용된 sent/lost 합계는 usable 도착 증거에 한한다. src=none에 남아 있는 진단용 카운트나 censored 증거를 도착 우도 표본으로 세지 않는다. 실패 연결에서 완전한 전멸 증거가 실제 학습에 쓰인 경우는 별도 연결 수로 남긴다. 관측기의 `all_lost=False`는 관측 부재에서도 쓰는 기본값이다. 전멸 또는 비전멸을 확인했다고 세려면 `observer.usable=True`와 boolean all_lost가 함께 있어야 한다. 회신 부재·유실·잘림·none의 False는 전멸 미확인에 넣고, 원래 all_lost 값 분포도 별도로 보존한다. 평가 전용 `evaluation_only_*` 값은 특권적 진단이며 정책 입력으로 간주하지 않는다. 역사 정책 그룹의 새 관측 진단은 null로 두고 0으로 만들지 않는다.

## 완료 결과 검증과 발행

`final_report(family_path, family_sha256, pool_dir, out, markdown_path=None)`는 pool의 배타적 잠금을 잡은 채 계획과 원자료를 다시 검증한다. 원형 pool의 manifest와 execution metadata가 재구성한 계획과 같아야 한다. 전체 run과 attempt의 시작·완료 쌍, 실행 digest, job 식별자, 시간 범위, 전체 작업 분할과 마지막 run 완료를 확인한다. 실패 기록, 미완료 쌍, 알려지지 않은 작업은 묵살하지 않는다.

각 작업의 검사에는 frozen `inspect_job`을 사용한다. 이 검사가 시작 receipt SHA, checkpoint 연결 순서와 semantic identity, 완료 result SHA, 전체 family와 결과 validator를 연결한다. 원자료, 결과, checkpoint, manifest, execution, 모든 실행 receipt의 해시는 보고 전후에 다시 확인한다. 수치 검증만 끝난 JSON을 읽고 실패 실행을 건너뛰는 경로는 제공하지 않는다.

최종 JSON과 선택적인 Markdown은 pool 밖의 새로운 파일이어야 한다. 모두 작성한 뒤 입력과 출처를 다시 확인하고 `<JSON 경로>.published.json`을 배타적으로 만든다. 이 마지막 발행 기록은 JSON/Markdown 파일 SHA, family 계획 SHA, 입력 목록 digest, pool attestation digest, execution digest와 보고 모듈 SHA를 묶는다. 발행 기록이 없는 파일은 발행 완료 산출물로 취급하지 않는다. Markdown 쓰기나 마지막 검증이 실패하면 이미 쓴 파일은 보존되며 기존 경로를 덮어쓰지 않는다. 조사 뒤 새로운 출력 경로로 다시 발행한다.

보고서의 `status=complete`는 필요한 입력이 모두 검증되어 있다는 뜻이다. 문턱 통과를 뜻하지 않는다. fail과 inconclusive를 각 판정에 그대로 남긴다.

## 실행 형태

모든 명령은 `python -I -B`로 새 보고 모듈을 실행한다. `plan`에는 `--overlay`, 전체 `--raw-dirs`, 새 `--out`을 준다. 완료 출력에는 family 파일 SHA와 전체 평가 작업 수가 나온다.

`run`에는 `--family-plan`, `--family-plan-sha256`, pool `--out`, `--workers`, `--time-budget-seconds`를 준다. 필요하면 `--loop`로 이어 돌리고, 기존 실행은 `--resume`으로 재개한다. `report`에는 같은 family 경로와 SHA, `--pool`, 새 JSON `--out`, 선택적인 `--markdown`을 준다. CLI 종료 코드는 complete 0, failed 2, partial 3이다. 검증 예외는 성공 코드로 처리하지 않는다.

전용 합성 시험은 실제 세계 표본이나 MC를 만들지 않는다. 전체 1500 입력의 75그룹·105대조, 누락·중복, 단일 family 합집합, 공유 MC와 선택 오차, 참조 상쇄, null, B5 원형 동일성, 결정 전 p 수렴, 실패 포함 관측 분모, source 변경, receipt와 결과·checkpoint 변조, 발행 잠금과 산출물 일부 작성 실패를 검사한다. 전용 첫 로그는 19개 시험과 14개 하위 사례 통과를, 두 번째 로그는 발행 기록과 전체 규모 합성 검사를 더한 22개 시험과 14개 하위 사례 통과를 기록한다. 전멸 False 기본값의 해석을 바로잡고 none·회신 부재·유실·잘림 회귀를 더한 세 번째 로그 `runs/L1_learning_report_units_03.txt`에는 23개 시험과 18개 하위 사례가 2.95초에 통과했다고 기록돼 있다. 이 숫자는 합성 시험 결과이며 실제 정책 성능 결과가 아니다.
