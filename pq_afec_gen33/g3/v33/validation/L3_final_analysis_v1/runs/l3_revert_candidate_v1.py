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
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L3_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]


def main():
    findings_path = RUNS / "L3_findings_v1.json"
    findings = read(findings_path)
    checked_path = RUNS / "L3_joint_artifact_check_v1.json"
    checked = read(checked_path)
    assert checked["status"] == "pass" and checked["error"] is None
    assert findings["candidate_eligible_for_adoption"] is False
    assert findings["provenance"]["check_sha256"] == sha(checked_path)
    assert findings["provenance"]["report_sha256"] == sha(ROOT / "g3/v33/L3_benchmark_v1.json")
    assert read(RUNS / "L3_validation_v1.finished.json")["status"] == "complete"
    out = RUNS / "L3_revert_candidate_v1.json"
    assert not out.exists()
    for directory in ("padfec", "padfec3"):
        frozen = sorted(path.name for path in (SNAPSHOT / directory).glob("*.py"))
        current = sorted(path.name for path in (ROOT / directory).glob("*.py"))
        assert current == frozen
        for name in frozen:
            assert sha(ROOT / directory / name) == sha(SNAPSHOT / directory / name), name
    restores = ["padfec3/learn3.py", "padfec3/decide3.py", "padfec3/layout.py", "tests/test_padfec3_arrivals.py",
        "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_learn.py", "tests/test_v33_policy_worker.py"]
    names = ("test_padfec3_monitor.py", "test_v33_learning_l3.py", "test_v33_l3_monitor_audit.py")
    destination = (ROOT / "experiments/v33/candidate_tests").resolve(strict=True)
    assert destination.is_relative_to(ROOT)
    for name in names:
        assert (ROOT / "tests" / name).is_file() and not (destination / ("l3_" + name)).exists()
    removed = (ROOT / "padfec3/monitor3.py").resolve(strict=True)
    assert removed.is_relative_to(ROOT)
    subprocess.run(git + ["ls-files", "--error-unmatch", "--", "padfec3/monitor3.py"], check=True, capture_output=True)
    receipt = {"started_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "base_commit": BASE,
        "reason": "The prespecified whole-candidate adoption conjunction did not pass; no diagnostic replacement or added samples",
        "findings_sha256": sha(findings_path), "check_sha256": sha(checked_path), "restored": [], "moved_tests": [],
        "removed_active_module": {"path": str(removed), "sha256": sha(removed), "frozen_copy": str(SNAPSHOT / "padfec3/monitor3.py")}}
    raw_blobs = {relative: subprocess.check_output(git + ["show", BASE + ":" + relative]) for relative in restores}
    for relative, raw in raw_blobs.items():
        path = (ROOT / relative).resolve(strict=True)
        assert path.is_relative_to(ROOT)
        before = sha(path)
        path.write_bytes(raw)
        receipt["restored"].append({"path": relative, "before_sha256": before, "after_sha256": sha(path), "base_blob_sha256": hashlib.sha256(raw).hexdigest()})
    subprocess.run(git + ["rm", "--", "padfec3/monitor3.py"], check=True, capture_output=True)
    for name in names:
        source, target = (ROOT / "tests" / name).resolve(strict=True), destination / ("l3_" + name)
        assert source.is_relative_to(ROOT) and target.resolve().is_relative_to(ROOT)
        before = sha(source)
        subprocess.run(git + ["mv", str(source), str(target)], check=True, capture_output=True)
        text = target.read_text(encoding="utf-8")
        if name == "test_padfec3_monitor.py":
            assert 'Path(__file__).resolve().parents[1]' in text
            text = text.replace('Path(__file__).resolve().parents[1]', 'Path(__file__).resolve().parents[3]')
        if name == "test_v33_l3_monitor_audit.py":
            assert 'with_name("test_v33_learning_l3.py")' in text
            text = text.replace('with_name("test_v33_learning_l3.py")', 'with_name("l3_test_v33_learning_l3.py")')
        target.write_text(text, encoding="utf-8", newline="\n")
        receipt["moved_tests"].append({"source": str(source), "target": str(target), "before_sha256": before, "after_sha256": sha(target)})
    for directory in ("padfec", "padfec3"):
        expected = subprocess.check_output(git + ["ls-tree", "--name-only", BASE, "--", directory + "/"], text=True).splitlines()
        actual = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).glob("*.py"))
        expected = sorted(path for path in expected if path.endswith(".py") and path.count("/") == 1)
        assert actual == expected, directory
        for relative in actual:
            assert (ROOT / relative).read_bytes() == subprocess.check_output(git + ["show", BASE + ":" + relative]), relative
    receipt["active_policy_exactly_matches_l1"] = True
    receipt["ended_kst"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    receipt["script_sha256"] = sha(__file__)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
