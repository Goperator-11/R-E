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
DEST = ROOT / "g3/v33/validation/L5_joint_plan_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not DEST.exists()
family_path = RUNS / "L5_joint_action_family_v1.json"
family = read(family_path)
receipt = read(RUNS / "L5_joint_plan_v1.finished.json")
assert receipt["status"] == "complete" and receipt["exit_code"] == 0
assert receipt["published_outputs_sha256"][str(family_path)] == sha(family_path)
assert family["manifest"]["evaluation_family_size"] == len(family["manifest"]["jobs"])
assert len(family["manifest"]["raw_run_identities"]) == 3000
check = read(RUNS / "L5_checker_fixture_check_v3.json")
assert check["status"] == "pass" and check["checker_sha256"] == sha(RUNS / "l5_joint_artifact_check_v3.py")
assert len(check["mutations_rejected"]) == 12
names = ['L5_joint_action_family_v1.json', 'L5_joint_plan_v1.started.json', 'L5_joint_plan_v1.finished.json', 'L5_joint_plan_v1.stdout.txt', 'L5_joint_plan_v1.stderr.txt', 'L5_joint_plan_launch_v1.json', 'L5_joint_plan_launcher_v1.stdout.txt', 'L5_joint_plan_launcher_v1.stderr.txt', 'launch_l5_joint_run_v1.ps1', 'launch_l5_joint_report_v1.ps1', 'launch_l5_validation_v2.ps1', 'l5_prepare_phase_launchers_v1.py', 'L5_phase_launcher_preparation_v1.json', 'L5_phase_launcher_parse_v1.json', 'l5_joint_progress_v1.py', 'iter023_checkpoint_02.json', 'L5_analysis_commit_receipt.json', 'L5_finish_preparation_commit_receipt.json', 'l5_joint_plan_bundle_v1.py', 'l5_prepare_joint_plan_bundle_v1.py', 'L5_full_v1.finished.json', 'L5_collection_progress_10.json', 'L5_checker_reset_commit_receipt.json']
names.extend(["J7_reading_during_L5_v1.json", "J7_reading_during_L5_v1.md", "j7_reading_during_l5_v1.py",
              "L5_reset_dispatch_fixture_v1.json", "l5_reset_dispatch_fixture_v1.py"])
assert read(RUNS / "L5_phase_launcher_parse_v1.json")["status"] == "pass"
entries = []
for name in names:
    source, target = RUNS / name, DEST / name
    stored = source.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if source.suffix == ".py":
        ast.parse(stored, filename=str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "family_sha256": sha(family_path), "scope": "Whole joint development action plan before MC results; raw3000 validated; historical new-method inputs explicitly missing; adoption pending"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "L5_joint_plan_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(f"WIP(L5): 전체 행동 평가 목록과 단계별 실행 근거 고정\n\n원자료3000실행 검증 완료. 전체{family['manifest']['evaluation_family_size']}행동에 N131072와 seed850001을 적용한다.\n완료 응답·B5·B6 독립 검사는 준비됐고 역사 관문은 입력 부족이다.\n후보 성능과 채택은 아직 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(entries) + 1}
with (RUNS / "L5_joint_plan_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
