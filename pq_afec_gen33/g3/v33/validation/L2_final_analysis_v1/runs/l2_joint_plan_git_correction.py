import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
DEST = ROOT / "g3/v33/validation/L2_joint_plan"
path = DEST / "manifest.json"
old = path.read_bytes()
original = DEST / "manifest_before_git_normalization.json"
assert not original.exists()
with original.open("xb") as stream:
    stream.write(old)
manifest = json.loads(old)
corrected = []
for item in manifest["entries"]:
    source = Path(item["source"]).read_bytes()
    assert hashlib.sha256(source).hexdigest() == item["sha256"]
    target = DEST / item["stored"]
    stored = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:" + target.relative_to(ROOT).as_posix()])
    assert stored == source or stored == source.replace(b"\r\n", b"\n")
    if stored != source:
        corrected.append(item["stored"])
    item.update(source_sha256=item.pop("sha256"), source_bytes=item.pop("bytes"),
                stored_sha256=hashlib.sha256(stored).hexdigest(), stored_bytes=len(stored))
manifest.update(text_storage="Git UTF-8 LF; original source bytes and stored bytes recorded separately",
                normalized_files=corrected, original_manifest_sha256=hashlib.sha256(old).hexdigest(),
                correction_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"normalized_files": corrected, "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
