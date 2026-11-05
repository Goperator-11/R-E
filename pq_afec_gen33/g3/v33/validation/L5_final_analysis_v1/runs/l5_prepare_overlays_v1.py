import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
from experiments.v33 import bench_learning_l5 as learning

read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
timer = time.monotonic()
old = read(ROOT / "g3/v33/bench_overlays/L1_v1_import.json")
outputs = []
for name in ("L5_v1", "L5_single_v1"):
    receipt_path = RUNS / (name + "_snapshot_receipt.json")
    receipt = read(receipt_path)
    overlay_path = ROOT / "g3/v33/bench_overlays" / (name + ".json")
    import_path = ROOT / "g3/v33/bench_overlays" / (name + "_import.json")
    overlay = learning.freeze_overlay(old["protocol_path"], old["raw_dirs"], old["oracle_dirs"],
        receipt["snapshot_root"], receipt_path, overlay_path, import_path, old["rules_path"],
        original_source_root=receipt["source_root"])
    outputs.append({"overlay_path": str(overlay_path), "overlay_sha256": sha(overlay_path),
        "import_path": str(import_path), "import_sha256": sha(import_path), "size_variant": overlay["policy"]["size_variant"]})
result = {"started_kst": started, "elapsed_seconds": time.monotonic() - timer, "status": "complete",
    "script_sha256": sha(__file__), "source_sha256": learning.sources(), "outputs": outputs}
with (RUNS / "L5_prepare_overlays_v1.json").open("x", encoding="utf-8") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
