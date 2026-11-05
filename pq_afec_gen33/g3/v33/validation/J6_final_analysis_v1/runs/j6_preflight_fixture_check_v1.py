import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("j6_independent_checker", RUNS / "j6_joint_artifact_check_v1.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
audit = checker.Audit()
finish = read(RUNS / "J6_smoke_v1.finished.json")
protocol = read(ROOT / "g3/v33/bench_protocol.json")
scenarios = {value["id"]: value for value in protocol["scenarios"]}
totals, original, chosen_scenario = [], None, None
for receipt in finish["results"]:
    command = receipt["command"]
    overlay = read(command[command.index("--overlay") + 1])
    folder = Path(command[command.index("--out") + 1])
    margin = 30 if overlay["policy"]["budget_variant"] == "full" else 0
    for path in folder.glob("*/*/seed*.json"):
        if path.name.count(".") != 1:
            continue
        run = read(path)
        audit.file(run["trace_path"], run["trace_sha256"])
        totals.append(checker.preflight_audit.seed(audit, run, scenarios[run["scenario"]], margin))
        if margin == 30 and run["observation_mode"] == "none":
            original, chosen_scenario = run, scenarios[run["scenario"]]
assert original is not None
with gzip.open(original["trace_path"], "rt", encoding="utf-8") as stream:
    rows = [json.loads(line) for line in stream]
target_index = next(index for index, row in enumerate(rows) if row["decision"].get("a_pre") is not None and row["observation_info"]["ctx"] is not None)
folder = RUNS / "J6_preflight_mutations_v1"
assert not folder.exists()
folder.mkdir()
mutations = []
timer = time.monotonic()
for name in ("decision_budget", "observation_budget", "margin", "source", "prefix", "S_scope", "S_after", "preflight_list", "preflight_update", "received_sum", "infinite_time", "final_history"):
    changed = copy.deepcopy(rows)
    row = changed[target_index]
    result = copy.deepcopy(original)
    if name == "decision_budget":
        row["decision"]["a_pre"] += 1
    elif name == "observation_budget":
        row["observation_info"]["ctx"]["a_pre"] += 1
    elif name == "margin":
        row["decision"]["margin_server_bytes"] = 0
    elif name == "source":
        row["decision"]["a_pre_source"] = "server_sent"
    elif name == "prefix":
        row["decision"]["prefix"] += 41
    elif name == "S_scope":
        row["decision"]["S_scope"] = "legacy_unclassified"
    elif name == "S_after":
        row["S_hat_post"] += 1
    elif name == "preflight_list":
        row["policy_observe_input"]["optional"]["preflight"]["small_initial_sizes"].append(13)
    elif name == "preflight_update":
        row["observation_info"]["preflight_updated"] = not row["observation_info"]["preflight_updated"]
    elif name == "received_sum":
        row["preflight_received"][0][2] += 1
    elif name == "infinite_time":
        row["preflight_received"][0][0] = float("inf")
    else:
        result["final_state"]["apre_history_count"] += 1
    path = folder / (name + ".jsonl.gz")
    with gzip.open(path, "xt", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(json.dumps(row) for row in changed) + "\n")
    result["trace_path"] = str(path)
    result["trace_sha256"] = sha(path)
    try:
        checker.preflight_audit.seed(checker.Audit(), result, chosen_scenario, 30)
    except ValueError as exc:
        mutations.append({"name": name, "rejected_at": str(exc), "path": str(path), "sha256": sha(path)})
    else:
        raise AssertionError("accepted preflight mutation: " + name)
output = {"status": "pass", "smoke_runs": len(totals), "connections": sum(v["connections"] for v in totals),
          "checks": audit.count, "mutations": mutations, "elapsed_seconds": time.monotonic() - timer,
          "helper_sha256": sha(checker.PREFLIGHT_PATH), "checker_sha256": sha(RUNS / "j6_joint_artifact_check_v1.py"),
          "script_sha256": sha(__file__), "scope": "Independent causal-budget replay and twelve invalid-input mutations; no full performance read."}
with (RUNS / "J6_preflight_fixture_check_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(output, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({k: v for k, v in output.items() if k != "mutations"}))
