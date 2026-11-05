import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L5_v1"

def test_preserved_l5_candidate_in_isolated_process():
    expected = {'padfec/amplif.py': 'f517ba3c49b952f4714f837d18dd0a2b9200418450d35f5c287cba933d8c4341', 'padfec/capacity.py': 'ab4d79c456a2cb23d00ce54c06b194b61efc78bbc4ee1903f46df581d0de0dbe', 'padfec/codec.py': '9982d94be5c7fabc2a6de37502ff79e30f378c195d925f27dab9af16b181bdc9', 'padfec/policy.py': '4cb840be18ec19b5625b924660d56dd17b7025b19872c6397d5671108450cc6c', 'padfec/quantum.py': '6d6bcf0b5f81e4a6f7515bc7306346419d96f3ded7cb2978836841bf20ba2339', 'padfec/table.py': '96acbb1717a82cedef228d49e22fae4517997bb6e01226485873059b6306adcb', 'padfec/__init__.py': '8af008c57ff0ff6918c8fbe712d04466df56ab9526fe138f53068d8ffb248d79', 'padfec3/decide3.py': 'f511cea301a79be666243ae18b87fd9b9282a3e45f7b54615e6550c3616e3d6b', 'padfec3/layout.py': '3b748b15c98817a3b74d3109ac193dea436edc3d2d1dfacaaa7bd9dcb1780201', 'padfec3/learn3.py': '058d8fc4ea3dcbc43028121ea1dfc2eb361413b6cb27804e2a45e5b213a61c6b', 'padfec3/server_size.py': 'b8369e826b35a09e3ed382d6ecbe57d1bc24b85fbc825a1ff8411415510b2a7d', 'padfec3/__init__.py': 'c5501eeab8d48b3a4911cee273cfd586277b9ab374032913061830fed1b8bae3'}
    for name, value in expected.items():
        assert hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest() == value
    code = "import sys; sys.dont_write_bytecode=True; sys.path[:0]=" + repr([str(SNAPSHOT), str(ROOT)])
    code += "; from pathlib import Path; import padfec3; assert Path(padfec3.__file__).resolve().is_relative_to(Path(" + repr(str(SNAPSHOT)) + "))"
    code += "; import pytest; raise SystemExit(pytest.main(['experiments/v33/candidate_tests/l5_test_padfec3_server_size.py','experiments/v33/candidate_tests/l5_test_v33_server_response_observer.py','-q','-p','no:cacheprovider','-o','pythonpath=']))"
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
