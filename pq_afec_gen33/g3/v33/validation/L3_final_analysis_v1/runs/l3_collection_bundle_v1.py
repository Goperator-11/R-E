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
DEST = ROOT / "g3/v33/validation/L3_collection_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not DEST.exists()
for name in ("L3_core_check_04", "L3_collector_check_01"):
    check = read(RUNS / (name + ".json"))
    assert check["exit_code"] == 0 and check["unchanged"]
    assert all(sha(path) == expected for path, expected in check["source_sha256"].items())
    assert sha(check["log_path"]) == check["log_sha256"]
assert read(RUNS / "L3_validate_smoke_v2.json")["status"] == "pass"
operating = read(RUNS / "L3_monitor_operating_v2.json")
assert all(sha(path) == expected for path, expected in operating["sources_sha256"].items())
selected = {Path(__file__), RUNS / "launch_l3_collection_v1.ps1"}
for pattern in ("L3_*", "l3_*"):
    for path in RUNS.glob(pattern):
        selected.update([path] if path.is_file() else (item for item in path.rglob("*") if item.is_file()))
entries = []
for path in sorted(selected):
    raw = path.read_bytes()
    stored = raw if path.suffix == ".gz" else raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    target = DEST / "runs" / path.relative_to(RUNS)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": target.relative_to(DEST).as_posix(),
                    "source_sha256": hashlib.sha256(raw).hexdigest(), "stored_sha256": hashlib.sha256(stored).hexdigest(),
                    "stored_bytes": len(stored)})
manifest_path = DEST / "manifest.json"
with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "L3 full collection preparation, final source checks and six smoke runs; no full W1 performance read", "script_sha256": sha(__file__)}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
paths = ["docs/L3_monitor_design.md", "padfec3/monitor3.py", "tests/test_padfec3_monitor.py",
         "tests/test_v33_learning_l3.py", "experiments/v33/bench_learning_l3.py"]
paths += ["g3/v33/" + directory + "/" + name for directory in ("policy_snapshots", "ablation_sources")
          for name in ("L3_v1", "L3_guard_only_v1", "L3_record_only_v1", "L3_beta_only_v1") if (ROOT / "g3/v33" / directory / name).exists()]
paths += [p.relative_to(ROOT).as_posix() for p in (ROOT / "g3/v33/bench_overlays").glob("L3_*.json")]
subprocess.run(git + ["add", "--"] + paths, check=True, capture_output=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
verified = [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest_path, sha(manifest_path))]
old = ROOT / "g3/v33/validation/L3_unit_v1"
verified += [(old / row["stored"], row["stored_sha256"]) for row in read(old / "manifest.json")["files"]]
verified += [(path, sha(path)) for base in paths for path in ([ROOT / base] if (ROOT / base).is_file() else (ROOT / base).rglob("*.py"))]
request = "".join(":" + path.relative_to(ROOT).as_posix() + "\n" for path, _ in verified).encode("utf-8")
data = subprocess.run(git + ["cat-file", "--batch"], input=request, capture_output=True, check=True).stdout
position = 0
for path, expected in verified:
    end = data.index(b"\n", position)
    fields = data[position:end].split()
    assert len(fields) == 3 and fields[1] == b"blob", (path, fields)
    size = int(fields[2])
    assert hashlib.sha256(data[end + 1:end + 1 + size]).hexdigest() == expected == sha(path), str(path)
    assert data[end + 1 + size:end + 2 + size] == b"\n"
    position = end + 2 + size
assert position == len(data)
message_path = RUNS / "L3_collection_commit_message.txt"
with message_path.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 감시 회복 조건과 고정 후보의 전체 수집 준비\n\n핵심254개·하위424개, 수집기28개·하위17개가 통과했다.\n6개 dry-run과 smoke 72연결의 시점·수식·상태·출처를 검사했다.\n고정q 오류주입250회 중앙10결정을 재현했으며 실제 W1 경보율과 비용은 미확인이다.\n진단 팔3개를 포함한1800실행·2466000연결을 같은 세계와 seed로 고정한다.\n")
completed = subprocess.run(git + ["commit", "-F", str(message_path)], capture_output=True, text=True, encoding="utf-8")
assert completed.returncode == 0, completed.stdout + completed.stderr
status = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not status, status
result = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "git_status": "clean",
          "bundle_files": len(entries), "verified_index_blobs": len(verified), "manifest_sha256": sha(manifest_path), "script_sha256": sha(__file__)}
with (RUNS / "L3_collection_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
