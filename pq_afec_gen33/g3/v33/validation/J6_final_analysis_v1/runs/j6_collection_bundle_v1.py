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
DEST = ROOT / "g3/v33/validation/J6_collection_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not DEST.exists()
for name in ("J6_core_check_02", "J6_collector_check_01"):
    check = read(RUNS / (name + ".json"))
    assert check["exit_code"] == 0 and check["unchanged"]
    assert all(sha(path) == expected for path, expected in check["source_sha256"].items())
    assert sha(check["log_path"]) == check["log_sha256"]
assert read(RUNS / "J6_validate_smoke_v1.json")["status"] == "pass"
assert read(RUNS / "J6_independent_smoke_v1.json")["status"] == "pass"
selected = {Path(__file__), RUNS / "launch_j6_collection_v1.ps1"}
for pattern in ("J6_*", "j6_*", "iter021_*"):
    for path in RUNS.glob(pattern):
        selected.update([path] if path.is_file() else (p for p in path.rglob("*") if p.is_file()))
entries = []
for path in sorted(selected):
    raw = path.read_bytes()
    stored = raw if path.suffix == ".gz" else raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    target = DEST / "runs" / path.relative_to(RUNS)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": target.relative_to(DEST).as_posix(),
        "source_sha256": hashlib.sha256(raw).hexdigest(), "stored_sha256": sha(target), "stored_bytes": len(stored)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "script_sha256": sha(__file__),
        "scope": "J6 collection preparation; 276 core tests, 494 subtests; 47 collector and preflight tests; ten dry/smoke jobs, 120 connections, 5640 independent checks. Initial state/candidate fixture failures preserved."}, stream, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
paths = ["padfec/quantum.py", "padfec3/layout.py", "padfec3/learn3.py", "padfec3/decide3.py", "padfec3/preflight.py",
    "tests/test_padfec3_arrivals.py", "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_learn.py",
    "tests/test_v33_l3_candidate.py", "tests/test_v33_policy_worker.py", "tests/test_padfec3_preflight.py",
    "tests/test_v33_learning_j6.py", "tests/test_v33_preflight_observer.py", "docs/J6_preflight_budget.md",
    "experiments/v33/bench_learning_j6.py", "experiments/v33/preflight_observer.py", "experiments/v33/policy_bridge_j6.py",
    "experiments/v33/policy_worker_j6.py", "g3/v33/ablation_sources/J6_margin_zero_v1",
    "g3/v33/policy_snapshots/J6_v1", "g3/v33/policy_snapshots/J6_margin_zero_v1"]
paths += [p.relative_to(ROOT).as_posix() for p in (ROOT / "g3/v33/bench_overlays").glob("J6_*.json")]
subprocess.run(git + ["add", "--"] + paths, capture_output=True, check=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], capture_output=True, check=True)
files = [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]
files += [(p, sha(p)) for name in paths for p in ([ROOT / name] if (ROOT / name).is_file() else (ROOT / name).rglob("*")) if p.is_file()]
request = "".join(":" + p.relative_to(ROOT).as_posix() + "\n" for p, _ in files).encode("utf-8")
data = subprocess.run(git + ["cat-file", "--batch"], input=request, capture_output=True, check=True).stdout
position = 0
for path, expected in files:
    end = data.index(b"\n", position)
    fields = data[position:end].split()
    assert len(fields) == 3 and fields[1] == b"blob", (path, fields)
    size = int(fields[2])
    assert hashlib.sha256(data[end + 1:end + 1 + size]).hexdigest() == expected, str(path)
    position = end + 2 + size
assert position == len(data)
message = RUNS / "J6_collection_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(J6): 관측 사전 ACK를 후보와 비용의 같은 예산에 반영\n\n핵심276개·하위494개, 새 수집·관측47개 시험 통과.\n10개 dry-run과 smoke120연결, 독립5640검사 통과.\nmargin30과 진단0의1500실행·2055000연결을 원래 W1 세계와 seed로 동결했다.\n전체W1평가와 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
status = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not status, status
receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "git_status": "clean",
    "bundle_files": len(entries), "verified_index_blobs": len(files), "manifest_sha256": sha(manifest), "script_sha256": sha(__file__)}
with (RUNS / "J6_collection_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
