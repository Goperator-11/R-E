from pathlib import Path
import subprocess
import sys
import time


def test_directory_output_is_rejected_before_starting_gate(tmp_path):
    script = Path(__file__).resolve().parents[1] / "experiments/gate_v3_parity.py"
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(script), "--bin", "x", "--out", "."],
        cwd=tmp_path, capture_output=True, text=True, timeout=2,
    )
    assert time.monotonic() - started < 2
    assert result.returncode == 2
    assert "--out must be a file path, not a directory" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []
