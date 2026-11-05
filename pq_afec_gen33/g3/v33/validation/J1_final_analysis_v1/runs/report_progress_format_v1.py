import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import re


RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
label = sys.argv[1]
assert label.replace("_", "").isalnum()
path = RUNS / "MORNING_REPORT.md"
raw = path.read_bytes()
text = raw.decode("utf-8")
newline = "\r\n" if "\r\n" in text else "\n"
match = re.search(r"(?m)^## 진행\r?\n(?P<body>[\s\S]*?)(?=^## 숫자\r?$)", text)
assert match
body = match.group("body")
rows = [line for line in body.splitlines() if line.strip()]
assert rows and all(line.startswith("|") and line.endswith("|") for line in rows)
replacement = newline + newline.join(rows) + newline + newline
before, after = text[:match.start("body")], text[match.end("body"):]
formatted = (before + replacement + after).encode("utf-8")
assert [line for line in replacement.splitlines() if line.strip()] == rows
backup, receipt = RUNS / (label + "_before.md"), RUNS / (label + ".json")
assert not backup.exists() and not receipt.exists()
with backup.open("xb") as stream:
    stream.write(raw)
path.write_bytes(formatted)
value = {"path": str(path), "backup_path": str(backup), "rows_including_header": len(rows),
    "before_sha256": hashlib.sha256(raw).hexdigest(), "after_sha256": hashlib.sha256(formatted).hexdigest(),
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "scope": "Only blank lines between progress table rows removed; all row text and every other section preserved exactly."}
with receipt.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value))
