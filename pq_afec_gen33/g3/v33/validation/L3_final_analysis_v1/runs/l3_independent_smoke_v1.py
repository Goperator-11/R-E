import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base_path = RUNS / "l1_precision_artifact_check_v4.py"
assert sha(base_path) == "a7504e1a2c94e54721077bbdaff068241da4e4274e17883eb5a7bab8f94aefd6"
base = load("independent_base", base_path)
helper_path = RUNS / "l3_monitor_audit_v1.py"
helper_sha = sha(helper_path)
helper = load("independent_monitor", helper_path)
audit = base.Audit()
finish = audit.read(RUNS / "L3_smoke_v1.finished.json")
assert finish["status"] == "complete" and finish["jobs"] == 6
roles = {"full": "l3", "guard_only": "guard", "record_only": "record", "beta_only": "beta"}
values = []
for receipt in finish["results"]:
    command = receipt["command"]
    overlay_path = Path(command[command.index("--overlay") + 1])
    overlay = audit.read(overlay_path)
    folder = Path(command[command.index("--out") + 1])
    for path in folder.glob("*/*/seed*.json"):
        if path.name.count(".") != 1:
            continue
        run = audit.read(path)
        audit.file(run["trace_path"], run["trace_sha256"])
        run["analysis_role"] = roles[overlay["policy"]["monitor_variant"]]
        values.append({"role": run["analysis_role"], "mode": run["observation_mode"], **helper.monitor_seed(audit, run)})
audit.final()
assert sha(helper_path) == helper_sha
result = {"status": "pass", "runs": len(values), "connections": sum(value["connections"] for value in values),
    "checks": len(audit.checks), "helper_sha256": helper_sha, "script_sha256": sha(__file__), "sources_sha256": audit.files,
    "scope": "Independent monitor replay on six completed smoke traces; no full W1 performance read"}
with (RUNS / "L3_independent_smoke_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps({k: v for k, v in result.items() if k != "sources_sha256"}))
