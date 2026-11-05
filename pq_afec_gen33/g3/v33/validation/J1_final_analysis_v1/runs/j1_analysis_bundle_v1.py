import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/J1_analysis_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
check = read(RUNS / "J1_analysis_check_01.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(p) == h for p, h in check["source_sha256"].items())
fixture = read(RUNS / "J1_checker_fixture_check_v1.json")
assert fixture["status"] == "pass" and fixture["checker_sha256"] == sha(RUNS / "j1_joint_artifact_check_v1.py")
assert not DEST.exists()
names = ["j1_prepare_analysis_v1.py", "j1_joint_driver_v1.py", "j1_collection_status.py", "j1_analysis_check_v1.py",
    "j1_grade_audit_v1.py", "j1_prepare_artifact_checker_v1.py", "j1_joint_artifact_check_v1.py",
    "j1_checker_fixture_check_v1.py", "j1_w0_error_table_v1.py", "j1_prepare_plan_launcher_v1.py",
    "launch_j1_joint_plan_v1.ps1", "j1_analysis_bundle_v1.py", "J1_analysis_check_01.json", "J1_analysis_check_01.log",
    "J1_checker_fixture_check_v1.json", "J1_w0_error_table_v1.json", "J1_w0_error_table_v1.md",
    "J1_collection_commit_receipt.json", "J1_collection_launch_v1.json", "J1_collection_progress_01.json", "J1_collection_progress_02.json",
    "j1_collection_checkpoint_v1.py", "iter020_checkpoint_01.json", "j1_finish_collection_bundle_v2.py",
    "J1_collection_manifest_before_lf_v1.json", "J1_collection_manifest_lf_correction.json"]
entries = []
for name in names:
    path = RUNS / name
    raw = path.read_bytes()
    stored = raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    dest = DEST / "runs" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": dest.relative_to(DEST).as_posix(),
        "source_sha256": sha(path), "stored_sha256": sha(dest), "stored_bytes": len(stored)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "script_sha256": sha(__file__), "scope": "J1 analysis and independent arithmetic/grade checker preparation during collection; no full performance read"}, stream, indent=2)
    stream.write("\n")
paths = ["experiments/v33/bench_learning_j1_report.py", "tests/test_v33_learning_j1_report.py", "tests/test_v33_j1_joint_driver.py"]
git = ["git", "-C", str(ROOT)]
subprocess.run(git + ["add", "--"] + paths, capture_output=True, check=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], capture_output=True, check=True)
files = [(DEST / r["stored"], r["stored_sha256"]) for r in entries] + [(manifest, sha(manifest))] + [(ROOT / p, sha(ROOT / p)) for p in paths]
request = "".join(":" + p.relative_to(ROOT).as_posix() + "\n" for p, _ in files).encode("utf-8")
data = subprocess.run(git + ["cat-file", "--batch"], input=request, capture_output=True, check=True).stdout
pos = 0
for path, expected in files:
    end = data.index(b"\n", pos)
    parts = data[pos:end].split()
    assert len(parts) == 3 and parts[1] == b"blob", path
    size = int(parts[2])
    assert hashlib.sha256(data[end+1:end+1+size]).hexdigest() == expected, path
    pos = end + size + 2
assert pos == len(data)
message = RUNS / "J1_analysis_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(J1): 전체 짝비교와 독립 검사 및 W0 오차표 준비\n\n분석37개·하위47개 통과. 합성150그룹·210대조54569검사와 오류주입12건 거부.\n고정W0 7조건의 전후오차를 저장했다. GE·RTT200 한계도 남겼다.\n전체수집은 진행 중이며 성능 판정과 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
receipt = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
    "files": len(entries), "verified_index_blobs": len(files), "manifest_sha256": sha(manifest), "git_status": "clean"}
with (RUNS / "J1_analysis_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps(receipt))
