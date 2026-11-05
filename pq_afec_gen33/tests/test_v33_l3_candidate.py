import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L3_v1"


def test_preserved_l3_candidate_in_isolated_process():
    expected = {
        "learn3.py": "e4d9e803da1188c21421b8b225fc0648d57214865006630d8c702c94a1f042c0",
        "decide3.py": "f820d93a95cff9319345f226a8e782bc564a3722f249ef431dab8042f83a2adb",
        "monitor3.py": "f1ea1af2085f5b84a7f572f51e6decd51a15a5107972c9ae2904176368d68a57",
        "layout.py": "d31f63d879e414ace81cd4b1c2123543b7ba568612f7408f13bf6e2a128c31e7"}
    for name, value in expected.items():
        assert hashlib.sha256((SNAPSHOT / "padfec3" / name).read_bytes()).hexdigest() == value
    files = ["experiments/v33/candidate_tests/l3_test_padfec3_monitor.py",
             "experiments/v33/candidate_tests/l3_test_v33_learning_l3.py",
             "experiments/v33/candidate_tests/l3_test_v33_l3_monitor_audit.py"]
    code = "import sys; sys.dont_write_bytecode=True; sys.path[:0]=" + repr([str(SNAPSHOT), str(ROOT)])
    code += "; from pathlib import Path; import padfec3; assert Path(padfec3.__file__).resolve().is_relative_to(Path(" + repr(str(SNAPSHOT)) + "))"
    code += "; import pytest; raise SystemExit(pytest.main(" + repr(files + ["-q", "-p", "no:cacheprovider", "-o", "pythonpath="]) + "))"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


def test_active_l1_rejects_l3_candidate_state():
    import pytest
    from padfec3 import learn3
    assert learn3.STATE_VERSION == 11
    value = learn3.new_state().to_json()
    value["v"] = 6
    with pytest.raises(ValueError):
        learn3.DestState3.from_json(value)
