import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
path = RUNS / "l5_joint_artifact_check_v3.py"
spec = importlib.util.spec_from_file_location("reset_dispatch_checker", path)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
source = Path(read(RUNS / "L5_independent_smoke_v1.json")["results"][0]["path"])
run = read(source)
with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
    first = json.loads(next(stream))
rows = [copy.deepcopy(first) for _ in range(3)]
for index, row in enumerate(rows):
    row["index"] = index
folder = RUNS / "L5_reset_dispatch_fixture_v1"
folder.mkdir()
trace = folder / "cold.trace.jsonl.gz"
raw = "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows).encode("utf-8")
with trace.open("xb") as stream:
    stream.write(gzip.compress(raw, mtime=0))
run.update(n=3, generation="l5_none", analysis_role="l5", scenario="B9", trace_path=str(trace), trace_sha256=sha(trace),
           final_state={"size_window_count": 1, "size_catalog_count": 1, "size_reset_count": 0, "S_hat": first["S_hat_post"]})
groups = {("l5_none", "B9"): [run]}
audit = checker.Audit()
counts = checker.response_audit.check_runs(audit, groups, {"scenarios": [{"id": "B9", "reset_each_connection": True}]})
try:
    checker.response_audit.check_runs(checker.Audit(), groups, {"scenarios": [{"id": "B9", "reset_each_connection": False}]})
except (ValueError, KeyError) as exc:
    rejected = {"type": type(exc).__name__, "message": str(exc)}
else:
    raise AssertionError("incorrect reset dispatch accepted")
result = {"status": "pass", "checks": audit.count, "counts": counts, "disabled_reset_rejected": rejected,
          "trace_path": str(trace), "trace_sha256": sha(trace), "source_smoke_path": str(source), "source_smoke_sha256": sha(source),
          "script_sha256": sha(__file__), "checker_sha256": sha(path), "scope": "synthetic repeated cold observations dispatched through complete run checker"}
with (RUNS / "L5_reset_dispatch_fixture_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
