import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
path = RUNS / "l5_joint_artifact_check_v2.py"
spec = importlib.util.spec_from_file_location("l5_response_fixture_checker", path)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
audit = checker.Audit()
groups = collections.defaultdict(list)
samples = None
for receipt in read(RUNS / "L5_smoke_v1.finished.json")["results"]:
    command = receipt["command"]
    folder = Path(command[command.index("--out") + 1])
    overlay = read(command[command.index("--overlay") + 1])
    for source in folder.glob("*/*/seed*.json"):
        if source.name.count(".") != 1:
            continue
        run = read(source)
        run["analysis_role"] = "single" if overlay["policy"]["size_variant"] == "single" else "l5"
        run["generation"] = run["analysis_role"] + "_" + run["observation_mode"]
        groups[run["generation"], run["scenario"]].append(run)
        if samples is None and run["analysis_role"] == "l5":
            with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
                samples = [json.loads(line) for line in stream]
timer = time.monotonic()
counts = checker.response_audit.check_runs(audit, groups, {})
mutations = []
for kind in ("nan", "infinite", "negative_time", "bool_time", "duplicate_completion", "raw_bytes", "prior_distribution", "size_update", "scope", "reset", "loss_context", "S_display", "geometry", "ack_identity", "data_identity"):
    rows = copy.deepcopy(samples)
    warm = rows[1]
    if kind in ("nan", "infinite", "negative_time", "bool_time"):
        rows[0]["server_response_received"][0][0] = {"nan": float("nan"), "infinite": float("inf"), "negative_time": -1, "bool_time": True}[kind]
    elif kind == "duplicate_completion":
        marker = next(x for x in rows[0]["server_response_received"] if x[1] == "complete")
        index = rows[0]["server_response_received"].index(marker)
        rows[0]["server_response_received"].insert(index, list(marker))
    elif kind == "raw_bytes":
        warm["policy_observe_input"]["srv_bytes"] += 1
    elif kind == "prior_distribution":
        warm["decision"]["size_distribution"][0]["weight"] = .5
    elif kind == "size_update":
        warm["observation_info"]["size_updated"] = False
    elif kind == "scope":
        warm["observation_info"]["size_scope_before"] = "legacy_unclassified"
    elif kind == "reset":
        warm["observation_info"]["size_reset"] = not warm["observation_info"]["size_reset"]
    elif kind == "loss_context":
        warm["observation_info"]["loss_context"]["size_distribution"][0]["S"] += 1
    elif kind == "S_display":
        warm["S_hat_post"] += 1
    elif kind == "geometry":
        warm["observation_info"]["size_sample"]["prefix"] += 1
    else:
        packet = next(x for x in warm["server_response_received"] if x[1] == "data")
        if kind == "ack_identity":
            packet[1], packet[3] = "ack", 0
        else:
            packet[3] = True
    try:
        checker.response_audit.audit_rows(rows, variant="full")
    except ValueError as exc:
        mutations.append({"mutation": kind, "rejected_at": str(exc)})
    else:
        raise AssertionError("accepted response mutation: " + kind)
result = {"status": "pass", "positive_checks": audit.count, "counts": counts, "mutations_rejected": mutations,
          "elapsed_seconds": time.monotonic() - timer, "script_sha256": sha(__file__), "checker_sha256": sha(path),
          "scope": "ten preserved smoke runs and invalid-input mutations; no full collection performance read"}
with (RUNS / "L5_response_fixture_check_v3.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps(result))
