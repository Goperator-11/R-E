import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("check_report_numbers_sources", ROOT / "report_repro/check_report_numbers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(tmp_path, module, monkeypatch, recorded):
    source = tmp_path / "source.md"
    source.write_bytes(b"a\r\nb\r\n")
    (tmp_path / "report_numbers.json").write_text(json.dumps({"entries": [
        {"key": "k", "source_alias": "alias", "source_sha256": recorded}]}), encoding="utf-8")
    monkeypatch.setattr(module, "REPORT_ROOT", tmp_path)
    monkeypatch.setattr(module, "source_path", lambda key: source)


def test_current_source_hash_accepts_either_line_ending(tmp_path, monkeypatch, capsys):
    module = load()
    for raw in (b"a\r\nb\r\n", b"a\nb\n"):
        prepare(tmp_path, module, monkeypatch, hashlib.sha256(raw).hexdigest())
        assert module.check_number_sources() == 0


def test_stale_source_hash_is_counted(tmp_path, monkeypatch, capsys):
    module = load()
    prepare(tmp_path, module, monkeypatch, "0" * 64)
    assert module.check_number_sources() == 1
    assert "report_numbers stale k alias" in capsys.readouterr().out


def test_missing_data_root_is_one_line(monkeypatch, capsys):
    module = load()

    def missing(_):
        raise FileNotFoundError("Missing source v4_workbook")

    monkeypatch.setattr(module, "source_path", missing)
    monkeypatch.setattr(module.sys, "argv", ["check_report_numbers.py"])
    assert module.main() == 2
    assert "Missing source v4_workbook" in capsys.readouterr().err


def test_fig4_segments_match_committed_figure():
    module = load()
    snapshot = json.loads((ROOT / "report_repro/data/fig4.json").read_text(encoding="utf-8"))
    text = (ROOT / "report_repro/fig4_staircase_cliff.tex").read_text(encoding="utf-8")
    for group in snapshot["s0"]:
        for segment in module.fig4_segments(snapshot, group):
            assert "(%.2f,%.2f)(%.2f,%.2f)" % segment in text
