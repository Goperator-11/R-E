import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
from pathlib import Path
import re

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
launcher = (RUNS / "launch_j6_collection_v1.ps1").read_text(encoding="utf-8-sig").replace("j6", "l5").replace("J6", "L5")
launcher = re.sub(r"if \(\$driverSha -ne '[0-9a-f]+'\)", "if ($driverSha -ne '" + sha(RUNS / "l5_bench_driver_v1.py") + "')", launcher)
launcher = re.sub(r"if \(\$planSha -ne '[0-9a-f]+'\)", "if ($planSha -ne '" + sha(RUNS / "L5_full_v1_plan.json") + "')", launcher)
with (RUNS / "launch_l5_collection_v1.ps1").open("x", encoding="utf-8-sig", newline="\n") as stream:
    stream.write(launcher)
bundle = (RUNS / "j6_collection_bundle_v1.py").read_text(encoding="utf-8").replace("j6", "l5").replace("J6", "L5")
bundle = bundle.replace("J6_collection_preparation_v1", "L5_collection_preparation_v1")
start = bundle.index('for name in ("L5_core_check_02", "L5_collector_check_01"):')
end = bundle.index('assert read(RUNS / "L5_validate_smoke_v1.json")', start)
bundle = bundle[:start] + '''checked = {}
for name in ("L5_core_01", "L5_collector_02"):
    check = read(RUNS / (name + ".json"))
    assert check["exit_code"] == 0 and check["unchanged"]
    assert sha(check["log_path"]) == check["log_sha256"]
    checked.update(check["source_sha256"])
assert all(sha(path) == expected for path, expected in checked.items())
''' + bundle[end:]
bundle = bundle.replace('"iter021_*"', '"iter023_*"')
bundle = bundle.replace('"padfec3/preflight.py"', '"padfec3/server_size.py"')
bundle = bundle.replace('"tests/test_padfec3_preflight.py"', '"tests/test_padfec3_server_size.py", "tests/test_padfec3_followup.py"')
bundle = bundle.replace('"tests/test_v33_preflight_observer.py"', '"tests/test_v33_server_response_observer.py"')
bundle = bundle.replace('"docs/L5_preflight_budget.md"', '"docs/L5_server_response.md"')
bundle = bundle.replace('"experiments/v33/preflight_observer.py"', '"experiments/v33/server_response_observer.py"')
bundle = bundle.replace("margin_zero", "single")
bundle = bundle.replace('"scope": "L5 collection preparation; 276 core tests, 494 subtests; 47 collector and preflight tests; ten dry/smoke jobs, 120 connections, 5640 independent checks. Initial state/candidate fixture failures preserved."', '"scope": "L5 collection preparation; 329 core tests, 524 subtests; 52 collector/response tests; ten dry/smoke jobs, 120 connections, 2270 independent checks. Initial hct_ms/hct adapter failure preserved. Historical new-method gate remains unavailable."')
old = 'stream.write("WIP(L5): 관측 사전 ACK를 후보와 비용의 같은 예산에 반영\\n\\n핵심276개·하위494개, 새 수집·관측47개 시험 통과.\\n10개 dry-run과 smoke120연결, 독립5640검사 통과.\\nmargin30과 진단0의1500실행·2055000연결을 원래 W1 세계와 seed로 동결했다.\\n전체W1평가와 채택은 미확인이다.\\n")'
new = 'stream.write("WIP(L5): 완료 응답의 물리 바이트와 크기 혼합 후보 보존\\n\\n핵심329개·하위524개, 수집·관측52개 시험 통과.\\n10개 dry-run과 smoke120연결, 독립2270검사 통과.\\n상태9 full과 single 진단의1500실행·2055000연결을 원래 W1 세계와 seed로 동결했다.\\n기존 유효 모형 앵커6/6과 c12000의11을 재현했다. 새 산출법은 과거 N·tail·목록 부재로 검증 미완료다.\\n전체W1과 활성 채택은 미확인이다.\\n")'
assert bundle.count(old) == 1
bundle = bundle.replace(old, new)
compile(bundle, "l5_collection_bundle_v1.py", "exec")
with (RUNS / "l5_collection_bundle_v1.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(bundle)
print("prepared L5 bundle, exact Git index check and detached collection launcher")
