import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L5_analysis_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
check = read(RUNS / "L5_analysis_02.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(p) == h for p, h in check["source_sha256"].items())
for name in ("L5_checker_fixture_check_v2", "L5_response_fixture_check_v3", "L5_adaptation_fixture_check_v3"):
    fixture = read(RUNS / (name + ".json"))
    assert fixture["status"] == "pass" and fixture["checker_sha256"] == sha(RUNS / "l5_joint_artifact_check_v2.py")
assert not DEST.exists()
selected = set(RUNS.glob("l5_*.py"))
selected.update(RUNS / name for name in ("launch_l5_joint_plan_v1.ps1", "launch_l5_validation_v1.ps1",
    "L5_analysis_01.json", "L5_analysis_01.log", "L5_analysis_02.json", "L5_analysis_02.log",
    "L5_checker_fixture_check_v1.json", "L5_checker_fixture_check_v2.json", "L5_response_fixture_check_v2.json",
    "L5_response_fixture_check_v3.json", "L5_adaptation_fixture_check_v3.json", "L5_adaptation_fixture_initial_failure.json",
    "L5_adaptation_fixture_second_failure.json", "L5_analysis_preparation_v1.md", "L5_collection_commit_receipt.json",
    "L5_collection_launch_v1.json", "L5_collection_progress_03.json", "L5_collection_progress_04.json", "L5_collection_progress_05.json", "iter023_checkpoint_01.json"))
selected.update(path for path in (RUNS / "L5_test_fixtures").rglob("*") if path.is_file())
entries = []
for path in sorted(selected):
    raw = path.read_bytes()
    stored = raw if path.suffix == ".gz" else raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    dest = DEST / "runs" / path.relative_to(RUNS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": dest.relative_to(DEST).as_posix(),
        "source_sha256": sha(path), "stored_sha256": sha(dest), "stored_bytes": len(stored)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "script_sha256": sha(__file__), "scope": "L5 analysis and independent arithmetic, grade, complete response and adaptation checker preparation during collection; no full performance read"}, stream, indent=2)
    stream.write("\n")
paths = ["experiments/v33/bench_learning_l5_report.py", "tests/test_v33_learning_l5_report.py", "tests/test_v33_l5_joint_driver.py"]
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
    assert hashlib.sha256(data[end + 1:end + 1 + size]).hexdigest() == expected, path
    pos = end + size + 2
assert pos == len(data)
message = RUNS / "L5_analysis_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L5): 전체 짝비교와 완료 응답 독립 검사를 준비\n\n분석37시험·하위47개 통과. 합성150그룹·210대조와 오류12건 거부.\n응답120연결2340검사·오류15건, B5·B6 검사와 오류11건 거부.\n최초 검사기 두 가정 오류를 정정하고 실패 자료를 보존했다.\n전체 수집과 성능 관문은 진행 중이며 역사 관문은 입력 부족이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
receipt = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
    "files": len(entries), "verified_index_blobs": len(files), "manifest_sha256": sha(manifest), "git_status": "clean"}
with (RUNS / "L5_analysis_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
state_path = RUNS.parent / "state/LOOP_STATE.json"
state = read(state_path)
assert state["current"] == "L5"
state["tasks"]["L5"]["commits"].append(receipt["commit"])
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(receipt))
