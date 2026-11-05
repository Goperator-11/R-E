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
DEST = ROOT / "g3/v33/validation/L5_collection_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not DEST.exists()
checked = {}
for name in ("L5_core_01", "L5_collector_02"):
    check = read(RUNS / (name + ".json"))
    assert check["exit_code"] == 0 and check["unchanged"]
    assert sha(check["log_path"]) == check["log_sha256"]
    checked.update(check["source_sha256"])
assert all(sha(path) == expected for path, expected in checked.items())
assert read(RUNS / "L5_validate_smoke_v1.json")["status"] == "pass"
assert read(RUNS / "L5_independent_smoke_v1.json")["status"] == "pass"
selected = {Path(__file__), RUNS / "launch_l5_collection_v1.ps1"}
for pattern in ("L5_*", "l5_*", "iter023_*"):
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
        "scope": "L5 collection preparation; 329 core tests, 524 subtests; 52 collector/response tests; ten dry/smoke jobs, 120 connections, 2270 independent checks. Initial hct_ms/hct adapter failure preserved. Historical new-method gate remains unavailable."}, stream, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
paths = ["padfec/quantum.py", "padfec3/layout.py", "padfec3/learn3.py", "padfec3/decide3.py", "padfec3/server_size.py",
    "tests/test_padfec3_arrivals.py", "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_learn.py",
    "tests/test_v33_l3_candidate.py", "tests/test_v33_policy_worker.py", "tests/test_padfec3_server_size.py", "tests/test_padfec3_followup.py",
    "tests/test_v33_learning_l5.py", "tests/test_v33_server_response_observer.py", "docs/L5_server_response.md",
    "experiments/v33/bench_learning_l5.py", "experiments/v33/server_response_observer.py", "experiments/v33/policy_bridge_l5.py",
    "experiments/v33/policy_worker_l5.py", "g3/v33/ablation_sources/L5_single_v1",
    "g3/v33/policy_snapshots/L5_v1", "g3/v33/policy_snapshots/L5_single_v1"]
paths += [p.relative_to(ROOT).as_posix() for p in (ROOT / "g3/v33/bench_overlays").glob("L5_*.json")]
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
message = RUNS / "L5_collection_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L5): 완료 응답의 물리 바이트와 크기 혼합 후보 보존\n\n핵심329개·하위524개, 수집·관측52개 시험 통과.\n10개 dry-run과 smoke120연결, 독립2270검사 통과.\n상태9 full과 single 진단의1500실행·2055000연결을 원래 W1 세계와 seed로 동결했다.\n기존 유효 모형 앵커6/6과 c12000의11을 재현했다. 새 산출법은 과거 N·tail·목록 부재로 검증 미완료다.\n전체W1과 활성 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
status = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not status, status
receipt = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "git_status": "clean",
    "bundle_files": len(entries), "verified_index_blobs": len(files), "manifest_sha256": sha(manifest), "script_sha256": sha(__file__)}
with (RUNS / "L5_collection_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
