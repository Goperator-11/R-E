import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L3_execution_ready_v1"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding="utf-8"))
check = read(RUNS / "L3_audit_check_02.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(Path(path)) == expected for path, expected in check["source_sha256"].items())
assert not DEST.exists()
names = ["L3_audit_check_02.json", "L3_audit_check_02.log", "l3_prepare_bound_launchers_v1.py",
         "l3_prepare_validation_execution_v1.py", "L3_collection_progress_07.json", "L3_collection_progress_08.json", "l3_execution_ready_bundle_v1.py"]
entries = []
for name in names:
    src, dst = RUNS / name, DEST / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    with dst.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    entries.append({"source": str(src), "stored": name, "source_sha256": sha(src), "stored_sha256": sha(dst)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"entries": entries, "scope": "L3 reset/failure audit cases and finite phase launch preparation; full performance unread"}, stream, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
subprocess.run(git + ["add", "--", "tests/test_v33_l3_monitor_audit.py"], check=True, capture_output=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / row["stored"], row["stored_sha256"]) for row in entries] + [(manifest, sha(manifest))]:
    assert hashlib.sha256(subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])).hexdigest() == expected
message = RUNS / "L3_execution_ready_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 연결 초기화와 실패 관측의 독립 검사 보강\n\n독립 감시 시험15개 통과. B9 초기화가 준비 상태를 이어받지 않고 HCT 없는 실패도F로 분류함을 확인했다.\n전체 수집 뒤 고정할 MC·보고·검사 실행 준비를 보존했다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
print(json.dumps({"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(), "manifest_sha256": sha(manifest)}))
