import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
import re
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
parts, hashes = [], {}
for name, key in (("audit-cost-model.md", "A1-04"), ("verify-A1.md", "A1-04"), ("audit-gen2-foundation.md", "A4-03"), ("audit-quicgo-source.md", "A8-06")):
    path = BASE / "findings" / name
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    selected = [section for section in re.split(r"(?=^## )", path.read_text(encoding="utf-8"), flags=re.M) if re.match(r"## " + re.escape(key) + r"\b", section)]
    assert len(selected) == 1
    parts.append(name + "\n" + selected[0])
with (BASE / "runs/iter022_sources.txt").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("\n".join(parts))
with (BASE / "runs/iter022_sources_sha256.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(hashes, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print("\n".join(parts))
