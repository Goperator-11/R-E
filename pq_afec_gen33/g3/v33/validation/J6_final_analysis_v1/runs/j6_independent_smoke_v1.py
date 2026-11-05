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
spec = importlib.util.spec_from_file_location("independent_preflight", RUNS / "j6_preflight_audit_v1.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

class Audit:
    def __init__(self):
        self.checks = 0

    def check(self, name, condition):
        self.checks += 1
        if not condition:
            raise ValueError(name)

    def equal(self, name, actual, expected):
        self.check(name, actual == expected)

audit = Audit()
finish = read(RUNS / "J6_smoke_v1.finished.json")
assert finish["status"] == "complete" and finish["jobs"] == 10
protocol = read(ROOT / "g3/v33/bench_protocol.json")
scenarios = {value["id"]: value for value in protocol["scenarios"]}
values, files = [], {}
for receipt in finish["results"]:
    command = receipt["command"]
    overlay = read(command[command.index("--overlay") + 1])
    folder = Path(command[command.index("--out") + 1])
    margin = 30 if overlay["policy"]["budget_variant"] == "full" else 0
    for path in folder.glob("*/*/seed*.json"):
        if path.name.count(".") != 1:
            continue
        run = read(path)
        assert sha(run["trace_path"]) == run["trace_sha256"]
        files[str(path)] = sha(path)
        files[run["trace_path"]] = run["trace_sha256"]
        values.append(helper.seed(audit, run, scenarios[run["scenario"]], margin))
result = {"status": "pass", "runs": len(values), "connections": sum(v["connections"] for v in values),
          "checks": audit.checks, "details": values, "files_sha256": files,
          "script_sha256": sha(__file__), "helper_sha256": sha(RUNS / "j6_preflight_audit_v1.py"),
          "scope": "Independent received preflight, median, causal context and response-scope replay; S eligibility uses preserved legacy_y. No performance claim."}
with (RUNS / "J6_independent_smoke_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({k: v for k, v in result.items() if k not in ("details", "files_sha256")}))
