import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
import re
from pathlib import Path

BASE = Path(r"C:\dev\codex_handoff\v33")
parts, hashes = [], {}
for name, key in (("audit-cost-model.md", "A1-12"), ("verify-A1.md", "A1-12"), ("audit-learning.md", "A2-11"), ("audit-learning.run1.md", "A2-10"), ("audit-gen2-foundation.md", "A4-01"), ("audit-quicgo-source.md", "A8-06")):
    path = BASE / "findings" / name
    hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    selected = [section for section in re.split(r"(?=^## )", path.read_text(encoding="utf-8"), flags=re.M) if re.match(r"## " + re.escape(key) + r"\b", section)]
    assert len(selected) == 1
    parts.append(name + "\n" + selected[0])
for name, content in (("iter023_sources.txt", "\n".join(parts)), ("iter023_sources_sha256.json", json.dumps(hashes, ensure_ascii=False, indent=2) + "\n")):
    with (BASE / "runs" / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
print("\n".join(parts))
