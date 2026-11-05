import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/J1_collection_preparation_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest = DEST / "manifest.json"
raw = manifest.read_bytes()
assert b"\r\n" in raw
with (RUNS / "J1_collection_manifest_before_lf_v1.json").open("xb") as stream:
    stream.write(raw)
value = json.loads(raw)
entries = value["entries"]
assert all(sha(DEST / item["stored"]) == item["stored_sha256"] for item in entries)
manifest.write_bytes(raw.replace(b"\r\n", b"\n"))
note = {"reason": "Initial bundle manifest used Windows default newline, so Git normalized CRLF. Content and evidence were unchanged; normalize only this new manifest before final index verification.",
    "before_sha256": hashlib.sha256(raw).hexdigest(), "after_sha256": sha(manifest), "script_sha256": sha(__file__)}
with (RUNS / "J1_collection_manifest_lf_correction.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(note, stream, indent=2)
    stream.write("\n")
source = (RUNS / "j1_collection_bundle_v1.py").read_text(encoding="utf-8")
tail = source[source.index('git = ["git", "-C", str(ROOT)]'):]
exec(compile(tail, str(RUNS / "j1_collection_bundle_v1.py"), "exec"))
