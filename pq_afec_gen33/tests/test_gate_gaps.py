import json
from pathlib import Path
import sys
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT))

import gate_go_parity
import gate_v3_parity


def test_gate_v3_bare_output_filename_writes_into_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "platform", "linux")
    gate_v3_parity.main(["--bin", str(tmp_path / "missing"), "--out", "bare.json", "--no-fresh"])
    value = json.loads((tmp_path / "bare.json").read_text(encoding="utf-8"))
    assert value["pass"] is False
    assert not (tmp_path / "bare.json.tmp").exists()


def test_gen2_go_gate_stays_disabled_in_gen33(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gate_go_parity.py"])
    build = Mock(side_effect=AssertionError("gen-2 gate reached its build check"))
    monkeypatch.setattr(gate_go_parity, "check_build_is_current", build)
    assert gate_go_parity.main() == 2
    assert "gen-2 parity gate is disabled in gen33" in capsys.readouterr().out
    build.assert_not_called()
