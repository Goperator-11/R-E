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
DEST = ROOT / "g3/v33/validation/L5_finalization_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]
assert not DEST.exists() and not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
end = read(RUNS / "L5_joint_run_v1.finished.json")
assert end["status"] == "complete" and end["exit_code"] == 0
assert sha(RUNS / "l5_findings_extract_v3.py") == "53dd0c2b3297b52d2985f8d4de034689f21693093852e487ba982d991840acd4"
assert sha(RUNS / "l5_joint_artifact_check_v3.py") == "c42dab5f81a270a0565ec971e914e6906b8edab077c2d13a6d586ea0e1a82c70"
names = ["l5_finalization_preparation_bundle_v1.py", "l5_prepare_final_bundle_v1.py", "l5_final_bundle_v1.py", "l5_prepare_final_commit_v1.py", "l5_final_commit_v1.py", "l5_finish_records_v1.py", "l5_prepare_uncertainty_diagnosis_v1.py", "l5_uncertainty_diagnosis_v1.py", "L5_joint_progress_14.json", "L5_joint_run_v1.finished.json", "L5_joint_report_launch_v1.json", "iter024_checkpoint_01.json", "L5_disposition_rule_commit_receipt.json", "J7_reading_during_L5_v2.json", "J7_reading_during_L5_v2.md", "J7_reading_during_L5_v3.md", "j7_reading_during_l5_v2.py"]
entries = []
for name in names:
    source, target = RUNS / name, DEST / name
    data = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if source.suffix == ".py":
        ast.parse(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "Whole MC complete; report and independent validation pending; final record, evidence bundle and revert commit preparations plus read-only J7 source review. No adoption decision or policy change."}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path in [DEST / row["stored"] for row in entries] + [manifest]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == sha(path)
message = RUNS / "L5_finalization_preparation_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L5): 전체 계산 완료 근거와 최종 기록 절차 보존\n\n118행동 MC가1120.952초에 complete·exit0으로 끝났다.\n보고·독립 검사 이후 실행할 판정·복구·감사 이관 절차를 보존했다.\n판정기21시험 통과와 소스SHA를 유지하며 채택 결과는 아직 미확인이다.\n")
completed = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert completed.returncode == 0, completed.stdout + completed.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
value = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "files": len(entries), "index_blobs_verified": len(entries)+1, "manifest_sha256": sha(manifest)}
with (RUNS / "L5_finalization_preparation_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value))
