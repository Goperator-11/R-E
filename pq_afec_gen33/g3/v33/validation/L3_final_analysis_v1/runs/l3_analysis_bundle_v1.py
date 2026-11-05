import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L3_analysis_preparation_v1"
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
check = read(RUNS / "L3_analysis_check_01.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(Path(path)) == expected for path, expected in check["source_sha256"].items())
assert not DEST.exists()
names = ["l3_make_reporter_v1.py", "l3_prepare_joint_execution_v1.py", "l3_joint_driver_v1.py", "l3_collection_status.py",
    "l3_report_check_v1.py", "l3_monitor_audit_v1.py", "l3_audit_check_v1.py", "l3_prepare_artifact_checker_v1.py",
    "l3_findings_extract_v1.py", "l3_prepare_analysis_check_v1.py", "l3_analysis_check_v1.py", "l3_analysis_bundle_v1.py",
    "L3_report_check_01.json", "L3_report_check_01.log", "L3_report_check_02.json", "L3_report_check_02.log",
    "L3_audit_check_01.json", "L3_audit_check_01.log", "L3_analysis_check_01.json", "L3_analysis_check_01.log",
    "L3_collection_commit_receipt.json", "L3_collection_launch_v1.json", "L3_collection_progress_01.json",
    "L3_collection_progress_02.json", "L3_collection_progress_03.json", "iter018_checkpoint_01.py", "iter018_checkpoint_01.json"]
entries = []
for name in names:
    path = RUNS / name
    raw = path.read_bytes()
    stored = raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    target = DEST / "runs" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": target.relative_to(DEST).as_posix(), "source_sha256": sha(path),
                    "stored_sha256": sha(target), "stored_bytes": len(stored)})
manifest_path = DEST / "manifest.json"
with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "L3 analysis and independent check preparation while collection is running; no full performance read", "script_sha256": sha(Path(__file__))}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
paths = ["experiments/v33/bench_learning_l3_report.py", "tests/test_v33_learning_l3_report.py", "tests/test_v33_l3_joint_driver.py",
         "tests/test_v33_l3_monitor_audit.py", "tests/test_v33_l3_findings.py"]
git = ["git", "-C", str(ROOT)]
subprocess.run(git + ["add", "--"] + paths, check=True, capture_output=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
verified = [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest_path, sha(manifest_path))]
verified += [(ROOT / path, sha(ROOT / path)) for path in paths]
request = "".join(":" + path.relative_to(ROOT).as_posix() + "\n" for path, _ in verified).encode("utf-8")
data = subprocess.run(git + ["cat-file", "--batch"], input=request, capture_output=True, check=True).stdout
position = 0
for path, expected in verified:
    end = data.index(b"\n", position)
    fields = data[position:end].split()
    assert len(fields) == 3 and fields[1] == b"blob", (path, fields)
    size = int(fields[2])
    assert hashlib.sha256(data[end + 1:end + 1 + size]).hexdigest() == expected == sha(path), str(path)
    position = end + 2 + size
assert position == len(data)
message_path = RUNS / "L3_analysis_commit_message.txt"
with message_path.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 전체 비교와 감시 진단의 독립 검사 준비\n\n보고·실행·감시 검산·채택 조건61개와 하위57개 시험이 통과했다.\n3300실행의165그룹과210대조를 재평가하도록 구현했다.\n45셀 비열등·B1/B2 절대 후회·경보·고정q 감지·비용 감소를 함께 요구한다.\n전체 수집이 진행 중이며 성능 결과와 최종 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message_path)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
status = subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not status, status
value = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "files": len(entries),
         "verified_index_blobs": len(verified), "manifest_sha256": sha(manifest_path), "git_status": "clean"}
with (RUNS / "L3_analysis_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(json.dumps(value))
