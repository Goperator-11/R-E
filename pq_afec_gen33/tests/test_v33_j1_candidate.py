import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/J1_v1"


def test_preserved_j1_candidate_in_isolated_process():
    expected = {'learn3.py': '1e132a6bac3ad961a65f454aa8d73c553807353678bc514b567f2d5c56c303e5', 'layout.py': '20d0ade5a6cdca2670b0b5fb7b9bae08de225945e24f90c04f367bd18b55475f'}
    for name, value in expected.items():
        assert hashlib.sha256((SNAPSHOT / "padfec3" / name).read_bytes()).hexdigest() == value
    helper = ROOT / "experiments/v33/candidate_tests/j1_adaptation_benchmark.py"
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == '43349ec3174146d0cd6a767d5a718c882e1181c97b31aed7ab89679f38b5b4ed'
    code = "import sys; sys.dont_write_bytecode=True; sys.path[:0]=" + repr([str(SNAPSHOT), str(ROOT)])
    code += "; import importlib.util, experiments; spec=importlib.util.spec_from_file_location('experiments.adaptation_benchmark'," + repr(str(helper)) + "); module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module); experiments.adaptation_benchmark=module"
    code += "; from pathlib import Path; import padfec3; assert Path(padfec3.__file__).resolve().is_relative_to(Path(" + repr(str(SNAPSHOT)) + "))"
    code += "; import pytest; raise SystemExit(pytest.main(['experiments/v33/candidate_tests/j1_test_padfec3_second_flight.py','-q','-p','no:cacheprovider','-o','pythonpath=']))"
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
