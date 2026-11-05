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
BASE = "c81bbdf2dd17348a3a36707b3013ee3451fd97d2"
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/J1_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]


def main():
    findings_path = RUNS / "J1_findings_v1.json"
    findings = read(findings_path)
    checked_path = RUNS / "J1_joint_artifact_check_v1.json"
    checked = read(checked_path)
    assert checked["status"] == "pass" and checked["error"] is None
    assert findings["candidate_adopted"] is False
    assert findings["checker_sha256"] == sha(checked_path)
    assert findings["report_sha256"] == sha(ROOT / "g3/v33/J1_benchmark_v1.json")
    assert read(RUNS / "J1_validation_v1.finished.json")["status"] == "complete"
    out = RUNS / "J1_revert_candidate_v1.json"
    assert not out.exists()
    for directory in ("padfec", "padfec3"):
        frozen = sorted(path.name for path in (SNAPSHOT / directory).glob("*.py"))
        current = sorted(path.name for path in (ROOT / directory).glob("*.py"))
        assert current == frozen
        for name in frozen:
            assert sha(ROOT / directory / name) == sha(SNAPSHOT / directory / name), name
    restores = ["padfec3/learn3.py", "padfec3/layout.py", "experiments/adaptation_benchmark.py",
        "tests/test_padfec3_arrivals.py", "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_layout.py",
        "tests/test_padfec3_learn.py", "tests/test_v33_policy_worker.py", "tests/test_v33_l3_candidate.py"]
    destination = (ROOT / "experiments/v33/candidate_tests").resolve(strict=True)
    source_test = (ROOT / "tests/test_padfec3_second_flight.py").resolve(strict=True)
    target_test = destination / "j1_test_padfec3_second_flight.py"
    target_helper = destination / "j1_adaptation_benchmark.py"
    wrapper = ROOT / "tests/test_v33_j1_candidate.py"
    assert destination.is_relative_to(ROOT) and source_test.is_relative_to(ROOT)
    assert not any(path.exists() for path in (target_test, target_helper, wrapper))
    helper = (ROOT / "experiments/adaptation_benchmark.py").read_text(encoding="utf-8")
    assert "ROOT = Path(__file__).resolve().parents[1]" in helper
    helper = helper.replace("ROOT = Path(__file__).resolve().parents[1]", "ROOT = Path(__file__).resolve().parents[3]")
    raw_blobs = {relative: subprocess.check_output(git + ["show", BASE + ":" + relative]) for relative in restores}
    receipt = {"started_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "base_commit": BASE,
        "reason": findings["reason"], "findings_sha256": sha(findings_path), "check_sha256": sha(checked_path),
        "restored": [], "test_source_sha256": sha(source_test), "helper_source_sha256": sha(ROOT / "experiments/adaptation_benchmark.py")}
    with target_helper.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(helper)
    subprocess.run(git + ["mv", str(source_test), str(target_test)], check=True, capture_output=True)
    for relative, raw in raw_blobs.items():
        path = (ROOT / relative).resolve(strict=True)
        assert path.is_relative_to(ROOT)
        before = sha(path)
        path.write_bytes(raw)
        receipt["restored"].append({"path": relative, "before_sha256": before, "after_sha256": sha(path),
            "base_blob_sha256": hashlib.sha256(raw).hexdigest()})
    expected = {name: sha(SNAPSHOT / "padfec3" / name) for name in ("learn3.py", "layout.py")}
    wrapper_text = '''import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/J1_v1"


def test_preserved_j1_candidate_in_isolated_process():
    expected = EXPECTED
    for name, value in expected.items():
        assert hashlib.sha256((SNAPSHOT / "padfec3" / name).read_bytes()).hexdigest() == value
    helper = ROOT / "experiments/v33/candidate_tests/j1_adaptation_benchmark.py"
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == HELPER_SHA
    code = "import sys; sys.dont_write_bytecode=True; sys.path[:0]=" + repr([str(SNAPSHOT), str(ROOT)])
    code += "; import importlib.util, experiments; spec=importlib.util.spec_from_file_location('experiments.adaptation_benchmark'," + repr(str(helper)) + "); module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module); experiments.adaptation_benchmark=module"
    code += "; import pytest; raise SystemExit(pytest.main(['experiments/v33/candidate_tests/j1_test_padfec3_second_flight.py','-q','-p','no:cacheprovider']))"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_active_policy_rejects_j1_candidate_state():
    import pytest
    from padfec3 import learn3
    assert learn3.STATE_VERSION != 7
    value = learn3.new_state().to_json()
    value["v"] = 7
    with pytest.raises(ValueError):
        learn3.DestState3.from_json(value)
'''.replace("EXPECTED", repr(expected)).replace("HELPER_SHA", repr(sha(target_helper)))
    with wrapper.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(wrapper_text)
    for directory in ("padfec", "padfec3"):
        expected_paths = subprocess.check_output(git + ["ls-tree", "--name-only", BASE, "--", directory + "/"], text=True).splitlines()
        actual = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).glob("*.py"))
        assert actual == sorted(path for path in expected_paths if path.endswith(".py") and path.count("/") == 1)
        for relative in actual:
            assert (ROOT / relative).read_bytes() == subprocess.check_output(git + ["show", BASE + ":" + relative]), relative
    receipt.update(active_policy_exactly_matches_l1=True, moved_test=str(target_test), moved_test_sha256=sha(target_test),
        preserved_helper=str(target_helper), preserved_helper_sha256=sha(target_helper), wrapper_sha256=sha(wrapper),
        ended_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), script_sha256=sha(__file__))
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
