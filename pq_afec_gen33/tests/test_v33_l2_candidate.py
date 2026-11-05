import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L2_v1"


def test_preserved_l2_candidate_in_isolated_process():
    assert hashlib.sha256((SNAPSHOT / "padfec3/learn3.py").read_bytes()).hexdigest() == "b0410c9c429c23e7956181f4fdb2e82cf552d858b3393e3647c8fa11dd289d04"
    assert hashlib.sha256((SNAPSHOT / "padfec3/decide3.py").read_bytes()).hexdigest() == "5fb9cc1e5fc095865bd2cf4dc8269acdf65c046efc9c58f9c64f3a3ec6d022e5"
    files = ["experiments/v33/candidate_tests/l2_test_padfec3_epsilon.py",
             "experiments/v33/candidate_tests/l2_test_v33_learning_l2.py"]
    code = "import sys; sys.dont_write_bytecode=True; sys.path[:0]=" + repr([str(SNAPSHOT), str(ROOT)])
    code += "; from pathlib import Path; import padfec3; assert Path(padfec3.__file__).resolve().is_relative_to(Path(" + repr(str(SNAPSHOT)) + "))"
    code += "; import pytest; raise SystemExit(pytest.main(" + repr(files + ["-q", "-p", "no:cacheprovider", "-o", "pythonpath="]) + "))"
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
