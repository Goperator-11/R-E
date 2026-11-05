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
DEST = ROOT / "g3/v33/validation/L3_custody_preparation_v1"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
names = ["l3_independent_smoke_v1.py", "L3_independent_smoke_v1.json", "l3_prepare_plan_launcher_v1.py", "launch_l3_joint_plan_v1.ps1",
    "L3_audit_preparation_v1.md", "l3_prepare_final_bundle_v1.py", "l3_prepare_bound_launchers_v1.py", "l3_prepare_validation_execution_v1.py",
    "iter018_checkpoint_02.py", "iter018_checkpoint_02.json", "L3_collection_progress_04.json", "L3_collection_progress_05.json",
    "L3_collection_progress_06.json", "L3_analysis_commit_receipt.json", "l3_custody_preparation_bundle_v1.py"]
assert not DEST.exists()
entries = []
for name in names:
    path = RUNS / name
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    if path.suffix == ".py":
        ast.parse(text, filename=str(path))
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(text.encode("utf-8"))
    entries.append({"source": str(path), "stored": name, "source_sha256": sha(path), "stored_sha256": sha(target)})
manifest = DEST / "manifest.json"
with manifest.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"files": entries, "scope": "L3 custody preparation before full results; bound generators require completed family and were not executed yet"}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
for path, expected in [(DEST / item["stored"], item["stored_sha256"]) for item in entries] + [(manifest, sha(manifest))]:
    blob = subprocess.check_output(git + ["show", ":" + path.relative_to(ROOT).as_posix()])
    assert hashlib.sha256(blob).hexdigest() == expected
message = RUNS / "L3_custody_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 감사 범위와 완료 후 증거 보존 절차 기록\n\n독립 감시 재생6실행·72연결 통과를 보존했다.\n연결11감사의 구현과 미검증 범위를 나누고, 전체 수집 완료 뒤 한 번 실행할 분석 입구를 고정했다.\n전체 비용·경보 결과와 후보 채택은 아직 미확인이다.\n")
result = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert result.returncode == 0, result.stdout + result.stderr
assert not subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
print(json.dumps({"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
    "manifest_sha256": sha(manifest), "files": len(entries)}))
