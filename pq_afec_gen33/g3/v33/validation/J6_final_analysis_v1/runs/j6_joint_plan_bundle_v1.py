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
DEST = ROOT / "g3/v33/validation/J6_joint_plan_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not DEST.exists()
family_path = RUNS / "J6_joint_action_family_v1.json"
family = read(family_path)
receipt = read(RUNS / "J6_joint_plan_v1.finished.json")
assert receipt["status"] == "complete" and receipt["exit_code"] == 0
assert receipt["published_outputs_sha256"][str(family_path)] == sha(family_path)
assert family["manifest"]["evaluation_family_size"] == len(family["manifest"]["jobs"])
assert len(family["manifest"]["raw_run_identities"]) == 3000
check = read(RUNS / "J6_checker_fixture_check_v2.json")
assert check["status"] == "pass" and check["checker_sha256"] == sha(RUNS / "j6_joint_artifact_check_v2.py")
assert len(check["mutations_rejected"]) == 12
names = ["J6_joint_action_family_v1.json", "J6_joint_plan_v1.started.json", "J6_joint_plan_v1.finished.json", "J6_joint_plan_v1.stdout.txt", "J6_joint_plan_v1.stderr.txt", "J6_joint_plan_launch_v1.json", "J6_joint_plan_launcher_v1.stdout.txt", "J6_joint_plan_launcher_v1.stderr.txt", "launch_j6_joint_run_v1.ps1", "launch_j6_joint_report_v1.ps1", "launch_j6_validation_v1.ps1", "j6_prepare_phase_launchers_v1.py", "J6_phase_launcher_preparation_v1.json", "J6_phase_launcher_parse_v1.json", "j6_joint_progress_v1.py", "iter021_checkpoint_02.json", "J6_analysis_commit_receipt.json", "j6_joint_plan_bundle_v1.py", "j6_historical_preflight_v1.py", "J6_historical_preflight_v1.json", "J6_historical_preflight_v1.md", "j6_historical_k_anomalies_v1.py", "J6_historical_k_anomalies_v1.json"]
assert read(RUNS / "J6_phase_launcher_parse_v1.json")["status"] == "pass"
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
    json.dump({"entries": entries, "family_sha256": sha(family_path), "scope": "Whole joint development action plan before MC results; raw3000 validated; historical accounting reproduced with k counter exceptions; adoption pending"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "J6_joint_plan_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(f"WIP(J6): 전체 행동 평가 계획과 과거 바이트 재검산 보존\n\n원자료3000실행 검증 완료. 전체{family['manifest']['evaluation_family_size']}행동에 N131072와 seed850001을 적용한다.\n과거25저널124800행의 서버 바이트·경계492/16000을 재현하고 ML-KEM 첫 비행 계수1인7행을 별도 보존했다.\n후보 성능과 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
out = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(entries) + 1}
with (RUNS / "J6_joint_plan_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(out, stream, indent=2)
    stream.write("\n")
print(json.dumps(out))
