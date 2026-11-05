import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('m4_gate_fingerprint', Path(__file__).resolve().parents[1] / 'experiments/gate_v3_parity.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize('name', ['padding.go', 'padding_test.go', 'go.mod'])
def test_local_module_changes_invalidate_binary_fingerprint(name):
    target = Path(gate.QUICBED) / 'padfechook' / name
    assert target.is_file()
    original = gate.sha256_file
    baseline = gate.quicbed_fingerprint()
    with patch.object(gate, 'sha256_file', side_effect=lambda path: '0' * 64 if Path(path) == target else original(path)):
        assert gate.quicbed_fingerprint() != baseline
