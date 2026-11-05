import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L5_disposition_rule_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
git = ["git", "-C", str(ROOT)]
assert not DEST.exists()
assert subprocess.check_output(git + ["status", "--porcelain"], text=True).strip() == "M tests/test_v33_l5_findings.py"
check = read(RUNS / "L5_finish_check_v3.json")
assert check["exit_code"] == 0 and check["unchanged"]
for path, expected in check["source_sha256"].items():
    assert sha(path) == expected
assert sha(RUNS / "L5_finish_check_v3.log") == check["log_sha256"]
names = ["l5_disposition_rule_bundle_v1.py", "l5_prepare_disposition_rule_v1.py", "l5_findings_extract_v3.py", "l5_finish_check_v3.py", "L5_finish_check_v3.json", "L5_finish_check_v3.log", "L5_disposition_rule_review_v1.md", "iter024_preflight.json", "L5_joint_progress_03.json"]
entries = []
for name in names:
    source, target = RUNS / name, DEST / name
    stored = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if source.suffix == ".py":
        ast.parse(stored)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "tests": 21, "scope": "Existing no-improvement rejection made explicit before full performance results; frozen candidate, evaluator, seeds and thresholds unchanged"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix(), "tests/test_v33_l5_findings.py"], check=True, capture_output=True)
paths = [DEST / row["stored"] for row in entries] + [manifest, ROOT / "tests/test_v33_l5_findings.py"]
for path in paths:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == sha(path)
message = RUNS / "L5_disposition_rule_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L5): 개선이 없는 후보를 거부하는 기존 판정 규칙 명시\n\n판정 시험21개 통과. 전체 성능 결과를 읽기 전에 원래 공통 개선 조건을 반영했다.\n후보와 고정118행동 평가·seed·표본·문턱은 그대로다. 역사 관문은 입력 부족이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(paths)}
with (RUNS / "L5_disposition_rule_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
