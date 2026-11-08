import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "report_repro/recompute_v3_verdicts.py"
SPEC = importlib.util.spec_from_file_location("report_recompute_v3", SCRIPT)
RECOMPUTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOMPUTE)


def write_units(path, keys):
    path.write_text("".join(json.dumps({"fp": "sealed", "key": key, "val": {"block": index}}) + "\n" for index, key in enumerate(keys)), encoding="utf-8")


def test_recompute_rejects_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        RECOMPUTE.read_units(tmp_path / "absent.jsonl", "sealed", {"a"})


def test_recompute_rejects_duplicate_unit(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    write_units(path, ["a", "a"])
    with pytest.raises(ValueError, match="duplicate unit"):
        RECOMPUTE.read_units(path, "sealed", {"a"})


@pytest.mark.parametrize("torn", [False, True])
def test_recompute_rejects_partial_journal(tmp_path, torn):
    path = tmp_path / "partial.jsonl"
    write_units(path, ["a"])
    if torn:
        with path.open("a", encoding="utf-8") as stream:
            stream.write('{"fp":')
    with pytest.raises(ValueError, match="partial journal"):
        RECOMPUTE.read_units(path, "sealed", {"a", "b"})


def test_recompute_refuses_output_overwrite(tmp_path):
    out = tmp_path / "previous"
    out.mkdir()
    marker = out / "preserved.txt"
    marker.write_bytes(b"original")
    result = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), "--out", str(out)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "refusing to overwrite" in result.stderr
    assert marker.read_bytes() == b"original"
    assert list(out.iterdir()) == [marker]


def test_recompute_comparison_rejects_missing_verdict():
    items, errors = [], []
    RECOMPUTE.compare({"reject": True, "est": 1.0}, {"est": 1.0}, "H1", items, errors)
    assert errors == ["H1.reject: missing recomputed value"]


@pytest.mark.parametrize("field", ["est", "n_requested", "planned", "returned", "ub_holm", "family_size", "holm_m", "mean_planned_imputed_ms"])
def test_recompute_comparison_checks_numeric_values_and_presence(field):
    items, errors = [], []
    RECOMPUTE.compare({field: 2.0}, {}, "saved", items, errors)
    assert errors == ["saved." + field + ": missing recomputed value"]
    items, errors = [], []
    RECOMPUTE.compare({field: 2.0}, {field: 1.0}, "saved", items, errors)
    assert len(items) == 1 and not items[0]["match"]
    assert errors == ["saved." + field + ": value differs"]


@pytest.mark.parametrize("field", ["H4", "arms"])
@pytest.mark.parametrize("actual", [{}, None])
def test_recompute_rejects_missing_or_null_container(field, actual):
    items, errors = [], []
    value = {} if actual == {} else {field: actual}
    RECOMPUTE.compare({field: {"est": 1.0}}, value, "saved", items, errors)
    assert errors
