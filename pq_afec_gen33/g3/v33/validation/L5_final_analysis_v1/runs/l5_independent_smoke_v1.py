import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
helper_path = RUNS / "l5_response_audit_v1.py"
spec = importlib.util.spec_from_file_location("l5_response_audit", helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
finish = read(RUNS / "L5_smoke_v1.finished.json")
assert finish["status"] == "complete"
results = []
for receipt in finish["results"]:
    command = receipt["command"]
    folder = Path(command[command.index("--out") + 1])
    overlay = read(command[command.index("--overlay") + 1])
    for path in folder.glob("*/*/seed*.json"):
        if path.name.count(".") != 1:
            continue
        run = read(path)
        assert run["trace_sha256"] == sha(run["trace_path"])
        with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        result = helper.audit_rows(rows, variant=overlay["policy"]["size_variant"])
        results.append({"path": str(path), "sha256": sha(path), "trace_sha256": run["trace_sha256"], **result})
assert len(results) == 10 and sum(row["rows"] for row in results) == 120
value = {"status": "pass", "checks": sum(row["checks"] for row in results), "rows": 120, "results": results,
         "scope": "independent scalar reconstruction of receive bytes and causal response history; not an independent transport world",
         "script_sha256": sha(__file__), "helper_sha256": sha(helper_path)}
with (RUNS / "L5_independent_smoke_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({key: value[key] for key in ("status", "checks", "rows")}))
