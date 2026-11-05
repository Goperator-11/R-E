import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess

ARCHIVE = Path(r"C:\dev\padfec_archive")
REPO = r"C:\dev\R-E"
PREFIX = "pq_afec/experiments/quicbed/"

def git(*args):
    return subprocess.check_output(["git", "-C", REPO, *args])

names = git("ls-tree", "--name-only", "4bab4a5:" + PREFIX.rstrip("/")).decode().splitlines()
names = sorted(n for n in names if n.endswith(".go") or n in {"build.sh", "go.mod", "go.sum"})
hashes = {n: hashlib.sha256(git("show", "4bab4a5:" + PREFIX + n)).hexdigest() for n in names}
srcsha = hashlib.sha256("".join(f"{n} {hashes[n]}\n" for n in names).encode()).hexdigest()
recorded = (ARCHIVE / "binaries/g2_d98b05d7/qamp.srcsha").read_text().strip()
assert srcsha == recorded, (srcsha, recorded)
source_comparison = []
for staged, original in (("cmd/qamp/main.go", "qamp.go"), ("cmd/qamp/policy.go", "policy.go"), ("cmd/qamp/pfail_table.go", "pfail_table.go"), ("go.mod", "go.mod"), ("go.sum", "go.sum")):
    data = (ARCHIVE / "gen2_build_origin" / staged).read_bytes()
    original_data = git("show", "4bab4a5:" + PREFIX + original)
    same = data.replace(b"\r\n", b"\n") == original_data.replace(b"\r\n", b"\n")
    source_comparison.append({"staged": staged, "git_file": PREFIX + original, "sha256": hashlib.sha256(data).hexdigest(), "crlf_normalized_match": same})
assert all(row["crlf_normalized_match"] for row in source_comparison)
result = {"source_commit": git("rev-parse", "4bab4a5").decode().strip(), "srcsha_files": len(names), "computed_srcsha": srcsha, "recorded_srcsha": recorded, "source_files": source_comparison, "binary_rebuilt": False}
path = Path(r"C:\dev\codex_handoff\v33\runs\S1_gen2_origin.json")
path.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode())
print(json.dumps(result, ensure_ascii=False))
