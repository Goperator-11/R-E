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
DEST = ROOT / "g3/v33/validation/J6_followup_preparation_v1"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
assert not DEST.exists()
names = ["j6_revert_candidate_v1.py", "j6_revert_check_v1.py", "j6_prepare_finish_tools_v1.py", "J6_finish_tool_parse_v1.json",
    "j6_prepare_final_bundle_v1.py", "j6_final_bundle_v1.py", "j6_final_commit_v1.py", "L5_reading_during_J6_v1.md",
    "l5_reading_sources_during_j6_v1.py", "L5_reading_sources_during_J6_v1.json", "j6_quic_source_read_v1.py",
    "J6_quic_source_read_v1.json", "J6_quic_source_read_v1.md", "iter021_checkpoint_03.json", "J6_joint_plan_commit_receipt.json",
    "J6_joint_run_launch_v1.json", "J6_joint_progress_01.json", "J6_joint_progress_02.json", "J6_joint_progress_03.json", "j6_followup_bundle_v1.py"]
entries = []
for name in names:
    source, target = RUNS / name, DEST / name
    stored = source.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    if source.suffix == ".py":
        ast.parse(stored)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(source), "stored": name, "source_sha256": sha(source), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "Guarded disposition tooling and source reading during fixed J6 MC; no performance read, no adoption or L5 implementation."}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "J6_followup_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(J6): 판정 뒤 보존 절차와 실제 소스의 관측 한계 기록\n\n단계 도구의 Python 구문과 Git index21개 지문을 검사했다.\nGo1.26.6·quic-go0.61.0 소스8개에서1216 B key_share와 ACK 패딩 조건을 확인했다.\nL5 수신 index의 중복 제거 가능성과 과거 p13 집계의 목록 부재를 기록했다.\n전체116행동 계산 중이며 성능·채택은 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
receipt = {"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest), "files": len(entries), "index_blobs_verified": len(entries) + 1}
with (RUNS / "J6_followup_commit_receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
state_path = RUNS.parent / "state/LOOP_STATE.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
assert state["current"] == "J6"
state["tasks"]["J6"]["commits"].append(receipt["commit"])
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(receipt))
