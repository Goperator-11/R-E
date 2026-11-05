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
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not DEST.exists()
for name in ("J1_check_02", "J1_collector_check_03"):
    check = read(RUNS / (name + ".json"))
    assert check["exit_code"] == 0 and check["unchanged"]
    assert all(sha(path) == expected for path, expected in check["source_sha256"].items())
    assert sha(check["log_path"]) == check["log_sha256"]
assert read(RUNS / "J1_validate_smoke_v1.json")["status"] == "pass"
assert read(RUNS / "J1_historical_reference_v1.json")["status"] == "pass"
selected = {Path(__file__), RUNS / "launch_j1_collection_v1.ps1"}
for pattern in ("J1_*", "j1_*", "iter020_*"):
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
with manifest.open("x", encoding="utf-8") as stream:
    json.dump({"entries": entries, "script_sha256": sha(__file__),
        "scope": "J1 full collection preparation; core, collector, five dry/smoke jobs, historical twenty groups, 480 algebraic normalizations; failed initial checks preserved."}, stream, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
paths = ["experiments/adaptation_benchmark.py", "padfec3/layout.py", "padfec3/learn3.py",
    "tests/test_padfec3_arrivals.py", "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_layout.py",
    "tests/test_padfec3_learn.py", "tests/test_v33_l3_candidate.py", "tests/test_v33_policy_worker.py",
    "docs/J1_tail_design.md", "experiments/v33/bench_learning_j1.py", "tests/test_padfec3_second_flight.py", "tests/test_v33_learning_j1.py",
    "g3/v33/ablation_sources/J1_cost_only_v1", "g3/v33/policy_snapshots/J1_v1", "g3/v33/policy_snapshots/J1_cost_only_v1"]
paths += [p.relative_to(ROOT).as_posix() for p in (ROOT / "g3/v33/bench_overlays").glob("J1_*.json")]
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
    assert hashlib.sha256(data[end+1:end+1+size]).hexdigest() == expected, str(path)
    position = end + 2 + size
assert position == len(data)
message = RUNS / "J1_collection_commit_message.txt"
with message.open("x", encoding="utf-8") as stream:
    stream.write("WIP(J1): 둘째 왕복 손실 꼬리와 등급 우도를 같은 확률로 계산\n\n핵심256개·하위464개, 수집기63개·하위17개 통과.\n5개 dry-run과 smoke60연결, 과거20그룹·확률합480조건 검산 통과.\n원래15시나리오와seed31~50의1500실행·2055000연결 계획과 후보를 동결했다.\n전체W1평가와 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
status = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not status, status
receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "git_status": "clean",
    "bundle_files": len(entries), "verified_index_blobs": len(files), "manifest_sha256": sha(manifest), "script_sha256": sha(__file__)}
with (RUNS / "J1_collection_commit_receipt.json").open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
