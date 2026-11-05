import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L2_joint_plan"
assert not DEST.exists()
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location("l2_joint_driver", RUNS / "l2_joint_driver_v1.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
identity = module.phase_identity("plan")
family = module.read(module.FAMILY)
assert sha(module.FAMILY) == "b793aa7df0a831195c2ba54d4f97fb0013c1792edf81946e58b3c00ae1249853"
assert family["role_run_counts"] == {"baseline": 600, "l1": 900, "l2": 900, "fixed": 600}
assert len(family["manifest"]["jobs"]) == family["manifest"]["evaluation_family_size"] == 100
assert len(family["manifest"]["raw_run_identities"]) == 3000
assert len(family["comparisons"]) == 14 and len(family["primary_comparisons"]) == 4
protocol = module.read(family["protocol_path"])
assert protocol["oracle"]["validation_samples"] == 131072 and protocol["oracle"]["validation_seed"] == 850001
names = ["L2_joint_action_family_v1.json", "L2_joint_plan_v1.started.json", "L2_joint_plan_v1.finished.json",
         "L2_joint_plan_v1.stdout.txt", "L2_joint_plan_v1.stderr.txt", "launch_l2_joint_run_v1.ps1", "l2_joint_plan_bundle.py",
         "iter017_checkpoint_02.py", "iter017_checkpoint_02.json"]
DEST.mkdir(parents=True)
entries = []
for name in names:
    src, dst = RUNS / name, DEST / name
    content = src.read_bytes()
    with dst.open("xb") as stream:
        stream.write(content)
    entries.append({"source": str(src), "stored": name, "sha256": sha(dst), "bytes": len(content)})
result = {"schema": "padfec.v33.l2_joint_plan_bundle/1", "entries": entries, "plan_identity": identity,
          "evaluation_family_size": 100, "raw_runs": 3000, "comparison_count": 210,
          "N": 131072, "seed": 850001, "status": "prepared_pending_execution"}
out = DEST / "manifest.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"files": len(entries), "manifest_sha256": sha(out), "family_sha256": sha(module.FAMILY)}))
