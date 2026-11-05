import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
OUT = ROOT / "g3/v33/validation/L2_collection_preparation"
original = OUT / "manifest.json"
saved = OUT / "manifest_before_git_normalization.json"
assert not saved.exists()
raw = original.read_bytes()
manifest = json.loads(raw)
commit = "3ea96d67f5f226aac7c34284cbc2c20ae19d4216"
changes = []
for entry in manifest["files"]:
    path = (OUT / entry["stored_path"]).resolve(strict=True)
    assert path.is_relative_to(OUT.resolve())
    before = path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == entry["sha256"]
    relative = path.relative_to(ROOT).as_posix()
    blob = subprocess.check_output(["git", "-C", str(ROOT), "show", commit + ":" + relative])
    if before != blob:
        assert path.suffix == ".txt" and before.replace(b"\r\n", b"\n") == blob
        path.write_bytes(blob)
        changes.append(relative)
    entry["source_sha256"] = entry.pop("sha256")
    entry["source_bytes"] = entry.pop("bytes")
    entry["stored_sha256"] = hashlib.sha256(blob).hexdigest()
    entry["stored_bytes"] = len(blob)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["stored_sha256"]
with saved.open("xb") as stream:
    stream.write(raw)
manifest["normalization"] = "Ten subprocess stdout text files are stored with LF as required by Git attributes; original source SHA and size are retained. Gzip bytes are unchanged."
manifest["original_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
manifest["original_commit"] = commit
manifest["normalized_files"] = changes
manifest["verification_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
assert len(changes) == 10
original.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"verified_files": len(manifest["files"]), "normalized_stdout_files": len(changes),
                  "manifest_sha256": hashlib.sha256(original.read_bytes()).hexdigest()}))
