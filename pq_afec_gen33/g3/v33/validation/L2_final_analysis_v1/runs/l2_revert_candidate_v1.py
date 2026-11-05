import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(r"C:\dev\pq_afec_gen33").resolve()
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
BASE = "d845395c7e26637c853c76377139ed46b73907e0"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
findings = read(RUNS / "L2_findings_v3.json")
assert findings["candidate_eligible_for_adoption"] is False
assert read(RUNS / "L2_joint_artifact_check_v3.json")["status"] == "pass"
assert sha(ROOT / "padfec3/learn3.py") == "b0410c9c429c23e7956181f4fdb2e82cf552d858b3393e3647c8fa11dd289d04"
assert sha(ROOT / "padfec3/decide3.py") == "5fb9cc1e5fc095865bd2cf4dc8269acdf65c046efc9c58f9c64f3a3ec6d022e5"
files = ["padfec3/learn3.py", "padfec3/decide3.py", "tests/test_padfec3_arrivals.py",
         "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_learn.py", "tests/test_v33_policy_worker.py"]
receipt = {"started_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "base_commit": BASE,
           "reason": "Original30-cell adoption gate incomplete: none B8_j10 is inconclusive. No post-hoc refinement or diagnostic replacement.",
           "findings_sha256": sha(RUNS / "L2_findings_v3.json"), "restored": [], "moved_tests": []}
for relative in files:
    path = (ROOT / relative).resolve(strict=True)
    assert path.is_relative_to(ROOT)
    old = sha(path)
    raw = subprocess.check_output(["git", "-C", str(ROOT), "show", BASE + ":" + relative])
    path.write_bytes(raw)
    receipt["restored"].append({"path": relative, "before_sha256": old, "after_sha256": sha(path), "base_blob_sha256": hashlib.sha256(raw).hexdigest()})
destination = (ROOT / "experiments/v33/candidate_tests").resolve()
assert destination.is_relative_to(ROOT) and not destination.exists()
destination.mkdir()
for name in ("test_padfec3_epsilon.py", "test_v33_learning_l2.py"):
    source = (ROOT / "tests" / name).resolve(strict=True)
    target = destination / ("l2_" + name)
    assert source.is_relative_to(ROOT) and target.resolve().is_relative_to(ROOT)
    before = sha(source)
    subprocess.run(["git", "-C", str(ROOT), "mv", str(source), str(target)], check=True)
    if name == "test_v33_learning_l2.py":
        text = target.read_text(encoding="utf-8")
        assert 'ROOT = Path(__file__).resolve().parents[1]' in text
        assert 'bench.PolicyWorker(ROOT, scenario' in text
        text = text.replace('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path(__file__).resolve().parents[3]\nSNAPSHOT = ROOT / "g3/v33/policy_snapshots/L2_v1"')
        text = text.replace('bench.PolicyWorker(ROOT, scenario', 'bench.PolicyWorker(SNAPSHOT, scenario')
        target.write_text(text, encoding="utf-8", newline="\n")
    receipt["moved_tests"].append({"source": str(source), "target": str(target), "before_sha256": before, "after_sha256": sha(target)})
for directory in ("padfec", "padfec3"):
    for path in (ROOT / directory).glob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        assert path.read_bytes() == subprocess.check_output(["git", "-C", str(ROOT), "show", BASE + ":" + relative]), relative
receipt["active_policy_exactly_matches_l1"] = True
receipt["ended_kst"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
with (RUNS / "L2_revert_candidate_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(receipt, ensure_ascii=False))
