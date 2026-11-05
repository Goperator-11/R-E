import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
DEST = ROOT / "g3/v33/validation/L3_unit_v1"
sha = lambda b: hashlib.sha256(b).hexdigest()
check = json.loads((RUNS / "L3_core_check_03.json").read_text(encoding="utf-8"))
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(Path(path).read_bytes()) == expected for path, expected in check["source_sha256"].items())
assert not DEST.exists()
selected = {Path(__file__), RUNS / "l3_core_check_v1.py", RUNS / "l3_monitor_operating_v1.py", RUNS / "L3_monitor_operating_v1.json",
            RUNS / "iter017_last.json", RUNS / "iter017_payload.json", RUNS / "iter017_finish.py", RUNS / "iter017_guard_end.txt",
            RUNS / "l2_final_commit_v1.py", RUNS / "L2_final_commit_receipt.json", RUNS / "coverage_iter017_final.json"}
for pattern in ("L3_core_check_*", "iter018_*"):
    selected.update(path for path in RUNS.glob(pattern) if path.is_file())
entries = []
for path in sorted(selected):
    raw = path.read_bytes()
    stored = raw.decode("utf-8-sig").replace("\r\n", "\n").encode("utf-8")
    target = DEST / "runs" / path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(stored)
    entries.append({"source": str(path), "stored": target.relative_to(DEST).as_posix(),
                    "source_sha256": sha(raw), "stored_sha256": sha(stored), "stored_bytes": len(stored)})
with (DEST / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"files": entries, "scope": "L3 implementation and unit/fixed-q development checks; full W1 not run, no adoption", "script_sha256": sha(Path(__file__).read_bytes())}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
git = ["git", "-C", str(ROOT)]
subprocess.run(git + ["add", "--", "padfec3", "tests/test_padfec3_monitor.py", "tests/test_padfec3_learn.py",
    "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_arrivals.py", "tests/test_v33_policy_worker.py", "docs/L3_monitor_design.md"], check=True, capture_output=True)
subprocess.run(git + ["add", "-f", "--", DEST.relative_to(ROOT).as_posix()], check=True, capture_output=True)
message = RUNS / "L3_unit_commit_message.txt"
with message.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write("WIP(L3): 결정 전 예측으로 감시하고 등급 비용 보정을 분리\n\n상태6, 단일 snapshot 소비, C1 준비 조건과 가산 벌점 제거를 구현했다.\n핵심252개·하위424개 통과. 고정q 감지250회 중앙10결정, 양방향 경보율0.065/0.165/0.56회 매1000결정.\n전체 W1과 실제 폐루프 경보율은 미검증이며 후보를 채택하지 않는다.\n")
completed = subprocess.run(git + ["commit", "-F", str(message)], capture_output=True, text=True, encoding="utf-8")
assert completed.returncode == 0, completed.stdout + completed.stderr
print(json.dumps({"commit": subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip(),
                  "files": len(entries), "manifest_sha256": sha((DEST / "manifest.json").read_bytes())}))
