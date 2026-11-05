import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
BASE = Path(r"C:\dev\codex_handoff\v33")
RUNS = BASE / "runs"
sys.path.insert(0, str(ROOT))
from padfec import policy, quantum
from padfec3 import learn3, server_size

read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
source = BASE / "evidence/audit-gen2-foundation/s05_anchor.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
anchors = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ANCH" for target in node.targets)]
assert len(anchors) == 1
rows = []
for group, k, n, low, high in anchors[0]:
    base = policy.S0_BASE_X25519 if group == "x25519" else policy.S0_BASE_MLKEM
    threshold = max(cert for cert in range(500, 20000) if quantum.bin_needed(cert, None, base, policy.C_PKT_POLICY_DEFAULT) <= n)
    rows.append({"group": group, "k": k, "n": n, "band": [low, high],
                 "effective_model_threshold_B": threshold, "effective_fit_inside_band": low <= threshold <= high,
                 "observed_correction": {"status": "unavailable", "missing": ["paired per-connection N_obs", "tail calibration"]},
                 "physical_prefix": {"status": "unavailable", "missing": ["complete per-connection response packet sizes"]}})
historical = read(ROOT / "g3/v33/evidence/06_server_size_bins.json")
for entry in historical["inputs"]:
    assert sha(entry["path"]) == entry["sha256"]
h_rows = []
for result in historical["results"]:
    assert result["input"]["cert_B"] == 12000
    effective = quantum.bin_needed(12000, None, policy.S0_BASE_MLKEM, policy.C_PKT_POLICY_DEFAULT)
    assert effective == result["effective_model_n_need"] == 11
    obs = result["observed_server_bytes"]
    h_rows.append({"arm": result["arm"], "rows": result["rows"], "observed_min_B": obs["min"], "observed_max_B": obs["max"],
                   "legacy_bins_at_endpoints": [learn3.bin_needed_s(obs[key], 6, policy.C_PKT_POLICY_DEFAULT) for key in ("min", "max")],
                   "recorded_n_need": result["recorded_n_need"], "effective_model_n_need": effective,
                   "new_methods_status": "unavailable_without_N_tail_or_response_list"})
examples = []
for cert, sizes in ((3250, [1280, 1280, 1209, 95]), (3300, [1280, 1280, 1257, 95])):
    sample = server_size.physical(sizes)
    examples.append({"cert_B": cert, "complete_sizes_B": sizes, "prefix_B": sample["prefix"], "credit_B": 1280,
                     "one_rtt_under_granular_rule": sample["prefix"] < 3 * 1280})
assert all(row["effective_fit_inside_band"] for row in rows)
assert all(row["one_rtt_under_granular_rule"] for row in examples)
inputs = [source, Path(r"C:\dev\pq_afec\docs\PADFEC v2 명세.md"), ROOT / "g3/v33/evidence/06_server_size_bins.json",
          RUNS / "L5_history_availability_during_J6_v2.json", RUNS / "J6_L5_historical_packet_inventory_v1.json", RUNS / "J6_L5_p13_fit_recheck_v1.json"]
output = {"schema": "padfec.v33.l5_anchor_availability/1", "data_kind": "historical_aggregate_reanalysis_and_model_fit_check",
          "effective_fit": {"inside": sum(row["effective_fit_inside_band"] for row in rows), "total": len(rows), "independent_validation": False},
          "anchors": rows, "H_c12000": h_rows, "complete_documented_examples": examples,
          "excluded_example": {"cert_B": 3340, "sizes_B": [1280, 1280, 1280], "reason": "incomplete first flight in a 2-RTT connection; final response size is unavailable"},
          "two_new_methods_historical_gate": "blocked_missing_inputs", "online_candidate": "physical_prefix_provisional_world_only",
          "calibrated_tail_selected": False, "script_sha256": sha(__file__),
          "input_sha256": {str(path): sha(path) for path in inputs},
          "policy_source_sha256": {str(ROOT / name): sha(ROOT / name) for name in ("padfec/policy.py", "padfec/quantum.py", "padfec3/learn3.py", "padfec3/server_size.py")}}
with (RUNS / "L5_anchor_availability_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(output, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(output, ensure_ascii=False))
