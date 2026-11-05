import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/J6_analysis_preparation_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
check = read(RUNS / "J6_final_checks_01.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(p) == h for p, h in check["source_sha256"].items())
for name in ("J6_checker_fixture_check_v2", "J6_preflight_fixture_check_v2"):
    fixture = read(RUNS / (name + ".json"))
    assert fixture["status"] == "pass" and fixture["checker_sha256"] == sha(RUNS / "j6_joint_artifact_check_v2.py")
assert not DEST.exists()
selected = set(RUNS.glob("j6_*.py"))
selected.update(RUNS / name for name in ("launch_j6_joint_plan_v1.ps1", "J6_analysis_check_01.json", "J6_analysis_check_01.log",
    "J6_final_checks_01.json", "J6_final_checks_01.log", "J6_checker_fixture_check_v1.json", "J6_checker_fixture_check_v2.json",
    "J6_preflight_fixture_check_v2.json", "J6_preflight_checker_revision.md", "J6_collection_commit_receipt.json",
    "J6_collection_launch_v1.json", "J6_collection_progress_01.json", "J6_collection_progress_02.json", "iter021_checkpoint_01.json"))
selected.update(path for path in (RUNS / "J6_preflight_mutations_v2").rglob("*") if path.is_file())
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
    json.dump({"entries": entries, "script_sha256": sha(__file__), "scope": "J6 analysis and independent arithmetic, grade and preflight checker preparation during collection; no full performance read"}, stream, indent=2)
    stream.write("\n")
paths = ["experiments/v33/bench_learning_j6_report.py", "tests/test_v33_learning_j6_report.py", "tests/test_v33_j6_joint_driver.py", "tests/test_v33_j6_findings.py"]
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
message = RUNS / "J6_analysis_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(J6): 고정 전체 짝비교와 관측 예산 독립 검사를 준비\n\n분석·판정45개·하위47개 통과. 합성150그룹·210대조55289검사와 오류주입12건 거부.\n사전 ACK 재생5650검사와 별도12오류주입도 통과했다.\n검사기41과41.0 표현 차이를 정정하고 최초 실패를 보존했다.\n전체수집이 진행 중이며 성능 판정과 채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
receipt = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
    "files": len(entries), "verified_index_blobs": len(files), "manifest_sha256": sha(manifest), "git_status": "clean"}
with (RUNS / "J6_analysis_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
state_path = RUNS.parent / "state/LOOP_STATE.json"
state = read(state_path)
assert state["current"] == "J6"
state["tasks"]["J6"]["commits"].append(receipt["commit"])
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(receipt))
