import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L5_finish_preparation_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
git = ["git", "-C", str(ROOT)]
assert not DEST.exists()
check = read(RUNS / "L5_finish_check_v1.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(p) == expected for p, expected in check["source_sha256"].items())
state_path = RUNS.parent / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 22 and state["current"] == "L5"
resume = {"recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "iteration": 23,
          "task": "L5", "guard_check": "GUARD_OK 2026-10-31T18:49:43+09:00", "guard_external_warnings": 6,
          "measurement_lock": False, "state_reloaded": True, "journal_recent_three_read": True,
          "continued_driver_pid": 14020, "no_restart": True,
          "latest_progress_path": str(RUNS / "L5_collection_progress_07.json"),
          "notes": ["initial JOURNAL path was corrected from root/JOURNAL.md to state/JOURNAL.md", "same iteration23 continued; no completed iteration overwritten"]}
with (RUNS / "iter023_resume_check.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(resume, stream, indent=2)
    stream.write("\n")
names = ["l5_prepare_finish_tools_v1.py", "l5_findings_extract_v1.py", "l5_revert_candidate_v1.py", "l5_revert_check_v1.py",
         "preserve_test_files_v1.py", "l5_finish_check_v1.py", "L5_finish_check_v1.json", "L5_finish_check_v1.log",
         "l5_finish_preparation_bundle_v1.py", "iter023_resume_check.json", "L5_collection_progress_06.json", "L5_collection_progress_07.json"]
sources = [RUNS / name for name in names]
sources.extend(path for path in (RUNS / "preserved_test_files_v1").rglob("*") if path.is_file())
entries = []
for path in sources:
    stored = path.read_bytes()
    if path.suffix in (".py", ".json", ".jsonl", ".log"):
        stored = stored.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if path.suffix == ".py":
        ast.parse(stored)
    target = DEST / path.relative_to(RUNS)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": target.relative_to(DEST).as_posix(), "source_sha256": sha(path), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
manifest.write_text(json.dumps({"entries": entries, "scope": "predeclared L5 disposition and reversible restoration preparation; no full performance read"}, indent=2) + "\n", encoding="utf-8", newline="\n")
subprocess.run(git + ["add", "--", "tests/test_v33_l5_findings.py"], check=True, capture_output=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
verify = [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest)), (ROOT / "tests/test_v33_l5_findings.py", sha(ROOT / "tests/test_v33_l5_findings.py"))]
for path, expected in verify:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "L5_finish_preparation_commit_message.txt"
message.write_text("WIP(L5): 역사 자료와 변화·혼합 관문을 최종 판정에 연결\n\n판정20시험 통과. 미확정·누락·중복과 역사 입력 부재는 채택을 막는다.\n후보 보존·L1 복구 절차를 준비했고 시험 임시 파일의 보존 어댑터를 점검했다.\n전체 수집은 같은 프로세스로 계속하며 성능은 아직 읽지 않았다.\n", encoding="utf-8", newline="\n")
subprocess.run(git + ["commit", "-F", str(message)], check=True, capture_output=True)
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
commit = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
state["tasks"]["L5"]["commits"].append(commit)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
value = {"commit": commit, "files": len(entries), "verified_index_blobs": len(verify), "manifest_sha256": sha(manifest)}
with (RUNS / "L5_finish_preparation_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value))
