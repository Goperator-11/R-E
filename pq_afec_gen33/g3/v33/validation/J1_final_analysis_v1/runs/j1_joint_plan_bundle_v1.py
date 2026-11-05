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
DEST = ROOT / "g3/v33/validation/J1_joint_plan_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
family_path = RUNS / "J1_joint_action_family_v1.json"
family = read(family_path)
receipt = read(RUNS / "J1_joint_plan_v1.finished.json")
assert receipt["status"] == "complete" and receipt["exit_code"] == 0
assert receipt["published_outputs_sha256"][str(family_path)] == sha(family_path)
assert family["manifest"]["evaluation_family_size"] == len(family["manifest"]["jobs"])
assert len(family["manifest"]["raw_run_identities"]) == 3000
check = read(RUNS / "J1_checker_fixture_check_v1.json")
assert check["status"] == "pass" and check["checker_sha256"] == sha(RUNS / "j1_joint_artifact_check_v1.py")
assert len(check["mutations_rejected"]) == 12
assert not DEST.exists()
names = ["J1_joint_action_family_v1.json", "J1_joint_plan_v1.started.json", "J1_joint_plan_v1.finished.json", "J1_joint_plan_v1.stdout.txt", "J1_joint_plan_v1.stderr.txt", "J1_joint_plan_launch_v1.json", "J1_joint_plan_launcher_v1.stdout.txt", "J1_joint_plan_launcher_v1.stderr.txt", "launch_j1_joint_run_v1.ps1", "launch_j1_joint_report_v1.ps1", "launch_j1_validation_v1.ps1", "j1_prepare_phase_launchers_v1.py", "J1_phase_launcher_preparation_v1.json", "j1_joint_progress_v1.py", "j1_prepare_final_bundle_v1.py", "j1_final_bundle_v1.py", "iter020_checkpoint_02.json", "J1_execution_commit_receipt.json", "j1_joint_plan_bundle_v1.py", "j1_revert_candidate_v1.py", "j1_revert_check_v1.py", "J1_audit_scope_preparation_v1.md"]
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
    json.dump({"entries": entries, "family_sha256": sha(family_path), "scope": "Whole joint action development plan before MC results; raw3000 validated, adoption pending"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "J1_joint_plan_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(f"WIP(J1): 전체 행동 평가 계획과 단계별 출처 검증 고정\n\n원자료3000실행 검증 완료. 전체{family['manifest']['evaluation_family_size']}행동에 N131072와 seed850001을 적용한다.\n보고 및 독립 검사와 보존 절차를 준비했다. 후보 성능과 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(entries) + 1}
with (RUNS / "J1_joint_plan_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
