import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
old_source = ROOT / "g3/v33/policy_snapshots/L1_v1/padfec3/learn3.py"
current_source = ROOT / "padfec3/learn3.py"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert sha(old_source) == "80f924c67b28b5030de4195fa2856c655a3c5a59fe34780f34d98518a0ae4452"
assert sha(current_source) == "b0410c9c429c23e7956181f4fdb2e82cf552d858b3393e3647c8fa11dd289d04"
nodes = lambda path: {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(Path(path).read_text(encoding="utf-8")).body if isinstance(node, ast.FunctionDef)}
old_nodes, current_nodes = nodes(old_source), nodes(current_source)
names = ("grade_cutoffs", "classify_hct", "check_action", "check_later", "_finite")
assert all(old_nodes[name] == current_nodes[name] for name in names)
original = RUNS / "l2_historical_grade_precheck.py"
text = original.read_text(encoding="utf-8")
text = text.replace('OUT = RUNS / "L2_historical_grade_precheck.json"', 'OUT = RUNS / "L2_historical_current_v1.json"')
text = text.replace(sha(old_source), sha(current_source)).replace("l1_", "l2_").replace("Fixed L1 boundaries", "Fixed L2 boundaries")
target = RUNS / "l2_historical_current_v1.py"
assert not target.exists()
compile(text, str(target), "exec")
with target.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
value = {"status": "pass", "old_source_sha256": sha(old_source), "current_source_sha256": sha(current_source),
         "same_function_AST": list(names), "original_replay_sha256": sha(original), "current_replay_sha256": sha(target),
         "scope": "L2 current code repeats A0 historical labels with unchanged cutoff/classification arithmetic, new source identity and distinct output."}
out = RUNS / "L2_historical_current_prepare.json"
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(value))
