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
DEST = ROOT / "g3/v33/validation/L5_checker_reset_preparation_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
git = ["git", "-C", str(ROOT)]
assert not DEST.exists()
check = read(RUNS / "L5_finish_check_v2.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(p) == expected for p, expected in check["source_sha256"].items())
state_path = RUNS.parent / "state/LOOP_STATE.json"
state = read(state_path)
assert state["iterations"] == 22 and state["current"] == "L5"
names = ['l5_prepare_checker_reset_v1.py', 'l5_response_audit_v3.py', 'l5_joint_artifact_check_v3.py', 'l5_validation_driver_v2.py', 'launch_l5_validation_v2.ps1', 'l5_response_fixture_check_v4.py', 'l5_response_fixture_check_v4_initial.py', 'L5_response_fixture_check_v4.json', 'l5_checker_fixture_check_v3.py', 'L5_checker_fixture_check_v3.json', 'l5_adaptation_fixture_check_v4.py', 'L5_adaptation_fixture_check_v4.json', 'l5_findings_extract_v2.py', 'l5_revert_candidate_v2.py', 'l5_finish_check_v2.py', 'L5_finish_check_v2.json', 'L5_finish_check_v2.log', 'L5_checker_reset_revision_v1.md', 'l5_checker_reset_bundle_prepare_v1.py', 'l5_checker_reset_bundle_v1.py', 'L5_collection_progress_10.json', 'L5_full_v1.finished.json', 'l5_prepare_phase_launchers_v1.py', 'l5_prepare_joint_plan_bundle_v1.py']
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
message = RUNS / "L5_checker_reset_commit_message.txt"
message.write_text("WIP(L5): 독립 검사에 연결별 초기화 계약 반영\n\nB9의 목적지 초기화를 검사 helper에 연결했다. 후보·수집 코드는 그대로다.\n응답120연결과 오류15건, 합성 cold 초기화, 전체 대조와 B5·B6 시험을 통과했다.\n판정20시험 통과. 전체1500수집이 오류 없이 끝났고 성능은 아직 읽지 않았다.\n", encoding="utf-8", newline="\n")
subprocess.run(git + ["commit", "-F", str(message)], check=True, capture_output=True)
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
commit = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
state["tasks"]["L5"]["commits"].append(commit)
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
value = {"commit": commit, "files": len(entries), "verified_index_blobs": len(verify), "manifest_sha256": sha(manifest)}
with (RUNS / "L5_checker_reset_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value))
