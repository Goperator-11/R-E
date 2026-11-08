import importlib.util
from pathlib import Path
import runpy
import sys

import pytest


SELECTOR = "rows[cert=16000,loss=0,uplink=0].arms[2].mean"
SOURCE_FILE = "archive/experiments/results/sample.json"


@pytest.fixture
def token_present(monkeypatch):
    report_dir = Path(__file__).resolve().parents[1] / "report_repro"
    spec = importlib.util.spec_from_file_location("crosswalk_paths", report_dir / "paths.py")
    paths = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paths)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setitem(sys.modules, "paths", paths)
    module = runpy.run_path(str(report_dir / "check_crosswalk.py"))
    return module["source_token_present"]


@pytest.mark.parametrize("cell,token,expected", [
    (SELECTOR + ",", SELECTOR, True),
    (SELECTOR + ". 다음 문장", SELECTOR, True),
    (SELECTOR + "_invalid", SELECTOR, False),
    (SELECTOR + ".fake", SELECTOR, False),
    (SELECTOR + "[0]", SELECTOR, False),
    ("fake." + SELECTOR, SELECTOR, False),
    (SOURCE_FILE + "의", SOURCE_FILE, True),
    (SOURCE_FILE + ". 다음 문장", SOURCE_FILE, True),
    (SOURCE_FILE + ".bak의", SOURCE_FILE, False),
    (SOURCE_FILE + "_invalid", SOURCE_FILE, False),
    ("wrong/" + SOURCE_FILE, SOURCE_FILE, False),
    ("p1_units·p2_units", "p1_units", True),
    ("p9_units.jsonl의", "p9_units", True),
    ("p9_units.jsonl.bak", "p9_units", False),
    ("p9_units_invalid", "p9_units", False),
])
def test_source_token_requires_complete_selector_or_path(token_present, cell, token, expected):
    assert token_present(cell, token) is expected
