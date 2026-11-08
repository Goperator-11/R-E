import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ERRATA = ROOT / "docs/REPORT_ERRATA.md"
CHECKER = ROOT / "report_repro/check_errata.py"
KEYS_CHECKER = ROOT / "report_repro/check_measure_keys.py"
TABLE_BUILDER = ROOT / "report_repro/build_measure_table.py"
RT_04_12_MEASURED = '개발 측정이며 봉인 판정이 아니다."` | `"v3.2-dev와 v3.3.1-dev의 네트워크 측정은 수행하지 못하였다."`'
RT_04_12_SELECTED = '"v3.2-dev와 v3.3.1-dev의 네트워크 측정은 수행하지 못하였다."` | 해당 없음 | 측정 뒤 문구 |'
RT_03_2_VALUE = "손실 2% 4.80 ms(95% CI 2.91~6.69"


def load(path=CHECKER, name="check_errata_rows"):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mutated(tmp_path, old=None, new=None, count=1):
    text = ERRATA.read_text(encoding="utf-8")
    if old is not None:
        assert text.count(old) == count
        text = text.replace(old, new)
    path = tmp_path / "errata.md"
    path.write_text(text, encoding="utf-8")
    return path


def run(tmp_path, capsys, old=None, new=None, extra=(), count=1):
    path = mutated(tmp_path, old, new, count)
    code = load().main(["--errata", str(path), "--claims", str(tmp_path / "missing.md"), *extra])
    return code, capsys.readouterr().out


def run_keys(tmp_path, capsys, old=None, new=None, count=1):
    path = mutated(tmp_path, old, new, count)
    code = load(KEYS_CHECKER, "check_measure_keys_rows").main(
        ["--errata", str(path), "--claims", str(tmp_path / "missing.md")])
    return code, capsys.readouterr().out


def test_baseline_table_passes(tmp_path, capsys):
    code, output = run(tmp_path, capsys)
    assert code == 0
    assert "CLAIMS 미확인" in output
    assert "row_numbers_pinned" in output
    assert "applied_pending 0" in output


def test_measurement_table_is_not_read_as_errata_rows():
    text = ERRATA.read_text(encoding="utf-8")
    assert "| id | new | 근거 키 |" in text
    rows = load().read_rows(ERRATA)
    assert len(rows) == 53
    assert all("old" in row and "적용" in row for row in rows)


@pytest.mark.parametrize("old,new,needle,count", [
    ("나머지 76, 313/450연결", "나머지 76, 400/450연결", "RT-15: new number 400", 1),
    ("60.27 ± 3.97(+1 B)", "60.27 ± 1.62(+1 B)", "RT-13: new number 1.62", 1),
    (RT_04_12_MEASURED, RT_04_12_MEASURED.replace('아니다."`', '아니다. 99.9 ms를 얻었다."`', 1),
     "RT-04-12: 측정 뒤 문구 number 99.9", 1),
    (RT_03_2_VALUE, RT_03_2_VALUE.replace("4.80", "4.90"), "RT-03-2: unsupported new number 4.9", 2),
])
def test_row_numbers_reject_mutants(tmp_path, capsys, old, new, needle, count):
    code, output = run(tmp_path, capsys, old, new, count=count)
    assert code == 1
    assert needle in output


def test_alternative_column_forbidden_expression(tmp_path, capsys):
    code, output = run(tmp_path, capsys, RT_04_12_MEASURED,
                       RT_04_12_MEASURED.replace('아니다."`', '아니다. 실측으로 개선 확인."`', 1))
    assert code == 1
    assert "RT-04-12: forbidden 측정 뒤 문구 expression 실측으로 개선 확인" in output


def test_applied_placeholder_is_an_error(tmp_path, capsys):
    code, output = run(tmp_path, capsys, "| skip:F31 미실행, X10 측정 없음 |", "| apply |")
    assert code == 1
    assert "RT-23: placeholder in applied row" in output
    assert "applied_pending 1" in output


def test_pin_must_match_entry(tmp_path, capsys):
    pins = json.loads((ROOT / "report_repro/errata_numbers.json").read_text(encoding="utf-8"))
    pins["rows"]["RT-13"] = {"3.97": "p17.design"}
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(pins, ensure_ascii=False), encoding="utf-8")
    code, output = run(tmp_path, capsys, extra=("--row-numbers", str(path)))
    assert code == 1
    assert "RT-13: new number 3.97 differs from entry p17.design" in output


def test_stale_pin_is_reported(tmp_path, capsys):
    pins = json.loads((ROOT / "report_repro/errata_numbers.json").read_text(encoding="utf-8"))
    pins["rows"]["RT-13"]["1.11"] = "p14.pad.loss5"
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(pins, ensure_ascii=False), encoding="utf-8")
    code, output = run(tmp_path, capsys, extra=("--row-numbers", str(path)))
    assert code == 1
    assert "RT-13: stale row evidence for 1.11" in output


def test_require_claims_fails_when_missing(tmp_path, capsys):
    with pytest.raises(ValueError):
        run(tmp_path, capsys, extra=("--require-claims",))


def final_run(tmp_path, capsys, old=None, new=None):
    (tmp_path / "claims.md").write_text("| 금지 표현 |\n|---|\n| 추가 비용 없는 FEC |\n", encoding="utf-8")
    path = mutated(tmp_path, old, new)
    code = load().main(["--errata", str(path), "--claims", str(tmp_path / "claims.md"), "--final"])
    return code, capsys.readouterr().out


def test_final_accepts_second_edition(tmp_path, capsys):
    code, output = final_run(tmp_path, capsys)
    assert code == 0
    assert "applied_pending 0" in output


def test_final_rejects_pending(tmp_path, capsys):
    code, output = final_run(tmp_path, capsys, RT_04_12_SELECTED,
                             RT_04_12_SELECTED.replace("| 측정 뒤 문구 |", "| pending:F32/F33 |"))
    assert code == 1
    assert "RT-04-12: pending text cannot be final" in output


def test_selected_values_choose_applied_text():
    module = load()
    row = {"id": "X", "old": "원문", "new": "측정 대기", "측정 뒤 문구": "문구", "측정 못 한 경우 문구": "못 잼", "러너 구현 뒤 미측정 문구": "해당 없음"}
    for selected, text in (("측정 뒤 문구", "문구"), ("measured", "문구"), ("측정 못 함", "못 잼"), ("원문 유지", "원문"), ("pending:F32/F33", "측정 대기")):
        row["selected"] = selected
        assert module.applied_text(row) == text
    row["selected"] = "측정 뒤 문구"
    assert module.selection_errors(row, True) == []
    row["selected"] = "구현하였으나"
    assert "selected column is empty" in module.selection_errors(row, False)[0]
    row["selected"] = "pending:F32/F33"
    assert "pending text cannot be final" in module.selection_errors(row, True)[0]


def test_measure_keys_baseline_passes(tmp_path, capsys):
    code, output = run_keys(tmp_path, capsys)
    assert code == 0
    assert "PASS errors 0" in output


def test_measure_keys_reject_changed_value(tmp_path, capsys):
    code, output = run_keys(tmp_path, capsys, RT_03_2_VALUE, RT_03_2_VALUE.replace("4.80", "4.90"), count=2)
    assert code == 1
    assert "RT-03-2: text 4.80 not in new" in output


def test_measure_keys_reject_forbidden_expression(tmp_path, capsys):
    code, output = run_keys(tmp_path, capsys, "로 차이를 확인하지 못하였고 동등성도 입증하지 않았다.",
                            "로 차이를 확인하지 못하여 가설을 기각하였다.", count=2)
    assert code == 1
    assert "RT-03-1: forbidden new expression 유의차 미확인을 기각으로 표현" in output


def test_measurement_table_matches_keys():
    module = load(TABLE_BUILDER, "build_measure_table_rows")
    table = module.table(ROOT, ROOT / "report_repro/measure_keys.json")
    assert table in ERRATA.read_text(encoding="utf-8")
