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
DEST = ROOT / "g3/v33/validation/L3_joint_plan_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
family_path = RUNS / "L3_joint_action_family_v1.json"
family = read(family_path)
receipt = read(RUNS / "L3_joint_plan_v1.finished.json")
assert receipt["status"] == "complete" and receipt["exit_code"] == 0
assert receipt["published_outputs_sha256"][str(family_path)] == sha(family_path)
assert family["manifest"]["evaluation_family_size"] == 101
assert len(family["manifest"]["raw_run_identities"]) == 3300
check = read(RUNS / "L3_checker_fixture_check_v1.json")
assert check["status"] == "pass" and check["checker_sha256"] == sha(RUNS / "l3_joint_artifact_check_v1.py")
assert len(check["mutations_rejected"]) == 7
assert not DEST.exists()
names = ["L3_joint_action_family_v1.json", "L3_joint_plan_v1.started.json", "L3_joint_plan_v1.finished.json",
    "L3_joint_plan_v1.stdout.txt", "L3_joint_plan_v1.stderr.txt", "L3_joint_plan_launch_v1.json",
    "L3_joint_plan_launcher_v1.stdout.txt", "L3_joint_plan_launcher_v1.stderr.txt", "L3_full_v1.finished.json",
    "L3_collection_progress_11.json", "l3_joint_artifact_check_v1.py", "launch_l3_joint_run_v1.ps1",
    "launch_l3_joint_report_v1.ps1", "l3_validation_driver_v1.py", "launch_l3_validation_v1.ps1",
    "l3_joint_progress_v1.py", "l3_final_bundle_v1.py", "l3_operating_integrity_v1.py", "L3_operating_integrity_v1.json",
    "l3_checkpoint_phase_v1.py", "iter018_checkpoint_03.json", "l3_checker_fixture_check_v1.py",
    "L3_checker_fixture_check_v1.json", "J1_preparation_during_L3_v1.md", "l3_joint_plan_bundle_v1.py"]
entries = []
for name in names:
    source, target = RUNS / name, DEST / name
    raw = source.read_bytes()
    stored = raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if source.suffix == ".py":
        ast.parse(stored, filename=str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "family_sha256": sha(family_path), "scope": "Whole101-action development plan before MC results; raw3300 validated, adoption pending"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "L3_joint_plan_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 전체101행동 평가 계획과 독립 검사 고정\n\n원자료3300실행 검증397.51초 정상 종료. 같은 N131072와 seed850001을 유지한다.\n합성165그룹·210대조의 독립 집계56999검사와 오류 주입7건 거부를 확인했다.\n전체 후보 성능과 채택은 아직 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(entries) + 1}
with (RUNS / "L3_joint_plan_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
