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
BASE = "91432c35c122dd83bc946b2d53e68c96bd6fa14b"
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L5_v1"
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
git = ["git", "-C", str(ROOT)]

def main():
    findings_path = RUNS / "L5_findings_v1.json"
    findings = read(findings_path)
    check_path = RUNS / "L5_joint_artifact_check_v2.json"
    checked = read(check_path)
    assert checked["status"] == "pass" and checked["error"] is None
    assert findings["candidate_adopted"] is False
    assert findings["checker_sha256"] == sha(check_path)
    assert findings["report_sha256"] == sha(ROOT / "g3/v33/L5_benchmark_v1.json")
    finished = read(RUNS / "L5_validation_v1.finished.json")
    assert finished["status"] == "complete" and finished["exit_code"] == 0
    output = RUNS / "L5_revert_candidate_v1.json"
    assert not output.exists()
    for directory in ("padfec", "padfec3"):
        frozen = sorted(path.name for path in (SNAPSHOT / directory).glob("*.py"))
        current = sorted(path.name for path in (ROOT / directory).glob("*.py"))
        assert current == frozen
        for name in frozen:
            assert sha(ROOT / directory / name) == sha(SNAPSHOT / directory / name), name
    restores = ["padfec/quantum.py", "padfec3/decide3.py", "padfec3/layout.py", "padfec3/learn3.py",
        "tests/test_padfec3_arrivals.py", "tests/test_padfec3_dev_regressions.py", "tests/test_padfec3_learn.py",
        "tests/test_v33_l3_candidate.py", "tests/test_v33_policy_worker.py", "tests/test_padfec3_followup.py"]
    raw_blobs = {name: subprocess.check_output(git + ["show", BASE + ":" + name]) for name in restores}
    destination = (ROOT / "experiments/v33/candidate_tests").resolve(strict=True)
    wrapper = ROOT / "tests/test_v33_l5_candidate.py"
    assert destination.is_relative_to(ROOT) and not wrapper.exists()
    moves = []
    for name in ("test_padfec3_server_size.py", "test_v33_server_response_observer.py"):
        source = ROOT / "tests" / name
        target = destination / ("l5_" + name)
        assert not target.exists()
        text = source.read_text(encoding="utf-8")
        if "observer" in name:
            assert "root = Path(__file__).resolve().parents[1]" in text
            assert '"source_root": str(root)' in text
            text = text.replace("root = Path(__file__).resolve().parents[1]", 'root = Path(__file__).resolve().parents[3]')
            text = text.replace('"source_root": str(root)', '"source_root": str(root / "g3/v33/policy_snapshots/L5_v1")')
        moves.append((source, target, text, sha(source)))
    receipt = {"started_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "base_commit": BASE,
        "reason": findings["reason"], "findings_sha256": sha(findings_path), "check_sha256": sha(check_path), "restored": [], "moved_tests": []}
    for source, target, text, original_sha in moves:
        subprocess.run(git + ["mv", str(source), str(target)], check=True, capture_output=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        receipt["moved_tests"].append({"from": str(source), "to": str(target), "original_sha256": original_sha, "preserved_sha256": sha(target)})
    for relative, raw in raw_blobs.items():
        path = (ROOT / relative).resolve(strict=True)
        assert path.is_relative_to(ROOT)
        before = sha(path)
        path.write_bytes(raw)
        receipt["restored"].append({"path": relative, "before_sha256": before, "after_sha256": sha(path), "base_blob_sha256": hashlib.sha256(raw).hexdigest()})
    deleted = ROOT / "padfec3/server_size.py"
    receipt["removed_active_module"] = {"path": str(deleted), "sha256": sha(deleted), "preserved_at": str(SNAPSHOT / "padfec3/server_size.py")}
    assert deleted.resolve().is_relative_to(ROOT)
    subprocess.run(git + ["rm", "--", "padfec3/server_size.py"], check=True, capture_output=True)
    expected = {path.relative_to(SNAPSHOT).as_posix(): sha(path) for folder in ("padfec", "padfec3") for path in (SNAPSHOT / folder).glob("*.py")}
    wrapper_text = '''import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L5_v1"

def test_preserved_l5_candidate_in_isolated_process():
    expected = EXPECTED
    for name, value in expected.items():
        assert hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest() == value
    code = "import sys; sys.dont_write_bytecode=True; sys.path[:0]=" + repr([str(SNAPSHOT), str(ROOT)])
    code += "; import pytest; raise SystemExit(pytest.main(['experiments/v33/candidate_tests/l5_test_padfec3_server_size.py','experiments/v33/candidate_tests/l5_test_v33_server_response_observer.py','-q','-p','no:cacheprovider']))"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr

def test_active_policy_rejects_l5_candidate_state():
    import pytest
    from padfec3 import learn3
    assert learn3.STATE_VERSION != 9
    value = learn3.new_state().to_json()
    value["v"] = 9
    with pytest.raises(ValueError):
        learn3.DestState3.from_json(value)
'''.replace("EXPECTED", repr(expected))
    with wrapper.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(wrapper_text)
    for directory in ("padfec", "padfec3"):
        expected_paths = subprocess.check_output(git + ["ls-tree", "--name-only", BASE, "--", directory + "/"], text=True).splitlines()
        actual = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).glob("*.py"))
        assert actual == sorted(path for path in expected_paths if path.endswith(".py") and path.count("/") == 1)
        for relative in actual:
            assert (ROOT / relative).read_bytes() == subprocess.check_output(git + ["show", BASE + ":" + relative]), relative
    receipt.update(active_policy_exactly_matches_l1=True, wrapper_sha256=sha(wrapper),
        ended_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), script_sha256=sha(__file__))
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, ensure_ascii=False))

if __name__ == "__main__":
    main()
