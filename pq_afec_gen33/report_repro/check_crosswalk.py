import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA_ROOT, REPORT_ROOT, SOURCE_PATHS, source_path


class Sources:
    def __init__(self, repo):
        self.repo = repo
        self.evidence = []

    def read(self, alias, kind="json"):
        path = source_path(alias)
        raw = path.read_bytes()
        self.evidence.append({"alias": alias, "file": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        text = raw.decode("utf-8-sig")
        return json.loads(text) if kind == "json" else text

    def history(self, revision, filename, root_file=False):
        relative = filename if root_file else str(Path(SOURCE_PATHS["p1_flight"][0]).with_name(filename)).replace("\\", "/")
        raw = subprocess.run(["git", "-C", str(self.repo), "show", revision + ":" + relative], capture_output=True, check=True).stdout
        commit = subprocess.run(["git", "-C", str(self.repo), "show", "-s", "--format=%H%n%aI", revision], capture_output=True, check=True, text=True, encoding="utf-8").stdout.splitlines()
        self.evidence.append({"revision": commit[0], "author_date": commit[1], "file": relative, "sha256": hashlib.sha256(raw).hexdigest()})
        return (json.loads(raw) if filename.endswith(".json") else raw.decode("utf-8-sig")), commit


def select(rows, **conditions):
    matches = [row for row in rows if all(row.get(key) == value for key, value in conditions.items())]
    if len(matches) != 1:
        raise ValueError("Expected one source row: " + repr(conditions))
    return matches[0]


def capture(text, pattern):
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError("Expected one text match: " + pattern)
    return matches[0]


def table_rows(text, prefix):
    found = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and re.match(prefix, cells[0]):
            key = cells[0].split()[0]
            if key in found:
                raise ValueError("Duplicate table row: " + key)
            found[key] = cells
    return found


def derive(sources):
    p1 = sources.read("p1_flight")
    capacity = select(p1["capacity_checks"], group="X25519MLKEM768", ips=1450)
    classical = select(p1["runs"], group="x25519", ips=0)
    hybrid = select(p1["runs"], group="X25519MLKEM768", ips=0)
    p18 = sources.read("p18_mmax")
    p18_row = select(p18["rows"], cert=16000, loss=0.0, uplink=0.0)
    p18_verdict = select(p18["verdict"], cond=p18_row["cond"])
    regret_a, _ = sources.history("5ebc151", "p11_adaptive.json")
    regret_b, _ = sources.history("6182128", "p11_adaptive.json")
    below_a = select(regret_a["regret"], cert=2955, loss=0.0)
    below_b = select(regret_b["regret"], cert=2955, loss=0.0)
    above_a = select(regret_a["regret"], cert=9000, loss=5.0)
    if (regret_a["rtt_ms"], regret_a["n"], regret_a["group"]) != (regret_b["rtt_ms"], regret_b["n"], regret_b["group"]):
        raise ValueError("Historical regret settings differ")
    e6 = sources.read("e6_netem")["configs"]["ge_p5_L4"]
    content_raw = (REPORT_ROOT / "content.py").read_bytes()
    content = content_raw.decode("utf-8-sig")
    sources.evidence.append({"file": str(REPORT_ROOT / "content.py"), "sha256": hashlib.sha256(content_raw).hexdigest(), "source_key": "hybrid shared secret sentence; p1 execution date sentence; Table 5 title", "kind": "report_text"})
    secret = capture(content, r"결합된 shared secret은 (\d+) B")
    report_p1_date = capture(content, r"69\.0 B.*?\((\d+월 \d+일) 실행")
    table5_date = capture(content, r"Table 5\. Steps that failed the first verdict of the gen-2 run \(([^)]+)\)")
    expected = {
        "CW01": "%.1f B (C=%d B, capacity=%.1f B)" % (capacity["C"] - capacity["capacity"], capacity["C"], capacity["capacity"]),
        "CW02": "m2 %.3f ms; m2→m4 %.2f ± %.2f ms" % (p18_row["arms"]["2"]["mean"], p18_verdict["obs_gain_m2_to_m4"], p18_verdict["ci_half_used"]),
        "CW03": "%.3f ± %.3f ms / %.3f ± %.3f ms" % (below_a["regret_late_ms"], below_a["ci95_half_ms"], below_b["regret_late_ms"], below_b["ci95_half_ms"]),
        "CW04": "손실 %.2f%%, 평균 burst %.2f" % (100 * e6["loss_rate"], e6["mean_burst"]),
        "CW05": "X25519 %d개·%d B; hybrid %d개·%d B" % (classical["first_flight_datagrams"], classical["first_flight_bytes"], hybrid["first_flight_datagrams"], hybrid["first_flight_bytes"]),
        "CW06": secret + " B",
        "CW07": "p1 " + report_p1_date + "; Table 5 " + table5_date,
    }
    journals = {}
    for alias in ("p1_units", "p2_units", "p3_units", "p8_units", "p9_units", "p18_units"):
        rows = [json.loads(line) for line in sources.read(alias, "text").splitlines() if line.strip()]
        dates = sorted({row["recorded_at"].split("T")[0] for row in rows if "recorded_at" in row})
        if not dates:
            raise ValueError("Missing recorded_at dates: " + alias)
        journals[alias] = dates
    import openpyxl
    workbook_values = {}
    for alias, sheet, cells in (("v4_workbook", "5_이론대조", ("B6", "C6", "B7", "C7")), ("stage1_workbook", "1_크기", ("E5", "E7"))):
        path = source_path(alias)
        raw = path.read_bytes()
        sources.evidence.append({"alias": alias, "file": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            workbook_values[alias] = {cell: workbook[sheet][cell].value for cell in cells}
        finally:
            workbook.close()
    legacy_measured = sources.read("legacy_measured_report", "text")
    legacy_pending = sources.read("legacy_pending", "text")
    legacy = {
        "capacity": capture(legacy_measured, r"\| X25519MLKEM768 \| 1450 \| 2 \| (\d+) \| ([\d.]+) \| \*\*\+([\d.]+)\*\*"),
        "m2": capture(legacy_pending, r"m=2 는 2-RTT\(실측 ([\d.]+) / 모형"),
        "netem": capture(sources.read("legacy_full_report", "text"), r"\| P=5%, L=4 \| ([\d.]+) % \| ([\d.]+) \|"),
        "regret": [format(above_a["regret_late_ms"], ".3f"), format(above_a["ci95_half_ms"], ".3f")],
    }
    history = {}
    for revision in ("6dbf9e8", "7420d16", "f3dcd4a", "d96a56b", "4bab4a5"):
        data, commit = sources.history(revision, "p1_flight.json")
        row = min(data["capacity_checks"], key=lambda value: value["C"] - value["capacity"])
        history[revision] = [revision, commit[1], row["group"], str(row["W"]), str(row["C"]), "%.1f" % row["capacity"], "%.1f" % (row["C"] - row["capacity"])]
    loop_state = sources.read("legacy_loop_state")
    p6 = loop_state["stages"]["p6"]["finished"]
    p6_history_latest = max(row["at"] for row in loop_state["history"] if row.get("stage") == "p6")
    legacy_readme = sources.read("legacy_readme", "text")
    readme_regret = re.findall(r"\|\s*(2026-08-(?:29|30))\s*\([^)]*\)\s*\|\s*\*\*([\d.]+) ms\*\*\s*\|\s*±([\d.]+)\s*\|\s*([^|]+)\|", legacy_readme)
    if len(readme_regret) != 2:
        raise ValueError("Expected two dated README regret rows")
    deployment_readme, deployment_commit = sources.history("70e7e08", "README.md", root_file=True)
    deployment_date = capture(deployment_readme, r"\| gen-2 \([^|]+\| (2026-10-01~10-02) 실행 \|")
    detail = {
        "journal_dates": journals,
        "legacy_values": legacy,
        "workbook_cells": workbook_values,
        "p6_finished": p6,
        "p6_latest_history": p6_history_latest,
        "readme_regret": readme_regret,
        "deployment_date": deployment_date,
        "deployment_revision": deployment_commit[0],
        "regret_settings": {key: regret_a[key] for key in ("rtt_ms", "n", "group")},
        "p1_settings": {key: p1[key] for key in ("rtt_ms", "n")},
        "p1_capacity": capacity,
        "p1_inferred_f": capacity["W"] - capacity["h"] - capacity["capacity"] / (capacity["k"] - 1),
        "legacy_capacity_f0": capture(legacy_measured, r"\| X25519MLKEM768 \| 1450 \| 2 \| 1449 \| 1389\.0 \| \*\*\+60\.0\*\* \| ([\d.]+) \| \+([\d.]+)"),
        "legacy_m2_model": capture(legacy_pending, r"m=2 는 2-RTT\(실측 [\d.]+ / 모형 ([\d.]+)"),
        "p18_selected_arm": {key: p18_row["arms"]["2"][key] for key in ("n", "mean", "hct_scope")},
        "p18_selected_comparison": {key: p18_verdict[key] for key in ("obs_gain_m2_to_m4", "ci_half_used", "n_per_arm")},
        "e6_selected": {key: e6[key] for key in ("n", "loss_rate", "mean_burst", "p_target", "burst_target")},
        "e6_loss_pct": 100 * e6["loss_rate"],
    }
    return expected, history, detail


def find_repo(explicit):
    if explicit:
        return explicit.resolve()
    candidates = (DATA_ROOT / "R-E-wt" / "final", DATA_ROOT / "R-E", DATA_ROOT)
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate
    raise FileNotFoundError("R-E history unavailable; pass --repo")


def source_token_present(cell, token):
    pattern = re.escape(token)
    if re.fullmatch(r"p\d+_units", token):
        pattern += r"(?:\.jsonl)?"
    return re.search(r"(?<![A-Za-z0-9_./\\-])" + pattern + r"(?![A-Za-z0-9_/\\\[\]-]|\.[A-Za-z0-9_])", cell) is not None


def check_source_cells(rows, metadata):
    p11_path = str(Path(SOURCE_PATHS["p1_flight"][0]).with_name("p11_adaptive.json")).replace("\\", "/")
    journal_parent = str(Path(SOURCE_PATHS["p1_units"][0]).parent).replace("\\", "/")
    source_tokens = {
        "CW01": [SOURCE_PATHS["p1_flight"][0], "p1_flight:", "capacity_checks[group=X25519MLKEM768,ips=1450].C-capacity", "p1_units", *metadata["journal_dates"]["p1_units"]],
        "CW02": [SOURCE_PATHS["p18_mmax"][0], "p18_mmax:", "rows[cert=16000,loss=0,uplink=0].arms[2].mean", "verdict[동일 cond].obs_gain_m2_to_m4", "ci_half_used", "p18_units", *metadata["journal_dates"]["p18_units"]],
        "CW03": [p11_path, "5ebc151", "6182128", "regret[cert=2955,loss=0].regret_late_ms", "ci95_half_ms"],
        "CW04": [SOURCE_PATHS["e6_netem"][0], "e6_netem:", "configs.ge_p5_L4.loss_rate×100", "mean_burst"],
        "CW05": ["p1_flight:", "runs[group=x25519,ips=0]", "runs[group=X25519MLKEM768,ips=0]", "first_flight_datagrams", "first_flight_bytes"],
        "CW06": ["report_repro/content.py", "결합된 shared secret", "stage1_workbook:", Path(SOURCE_PATHS["stage1_workbook"][0]).name, "1_크기!E5,E7"],
        "CW07": ["report_repro/content.py", "Table 5", journal_parent, "p1_units", "p2_units", "p3_units", "p8_units", "p9_units", "recorded_at"],
    }
    legacy = metadata["legacy_values"]
    workbook = metadata["workbook_cells"]
    other_tokens = {
        "CW01": ["용량 표는 %s B(C=%s, capacity=%s)" % (legacy["capacity"][2], legacy["capacity"][0], legacy["capacity"][1]), metadata["legacy_capacity_f0"][1] + " B"],
        "CW02": ["m2 실측 " + legacy["m2"] + " ms", "모형 " + metadata["legacy_m2_model"] + " ms"],
        "CW03": ["%s ± %s ms" % tuple(legacy["regret"]), "%s ± %s ms" % tuple(metadata["readme_regret"][1][1:3]), "regret[cert=9000,loss=5]"],
        "CW04": [legacy["netem"][0] + "%", legacy["netem"][1]],
        "CW05": [workbook["v4_workbook"]["B6"] + "·" + workbook["v4_workbook"]["C6"], workbook["v4_workbook"]["B7"].replace(",", ""), workbook["v4_workbook"]["C7"].replace(",", "")],
        "CW06": [str(workbook["stage1_workbook"]["E7"]) + " B"],
        "CW07": [metadata["deployment_revision"][:7], metadata["deployment_date"] + " 실행"],
    }
    failures = []
    for key in source_tokens:
        cells = rows.get(key, [])
        if len(cells) != 6:
            continue
        for index, tokens in ((2, source_tokens[key]), (3, other_tokens[key])):
            if index == 2:
                missing = [token for token in tokens if not source_token_present(cells[index], token)]
            else:
                missing = [token for token in tokens if token not in cells[index]]
            if missing:
                failures.append(key + (" source" if index == 2 else " other value") + " cell missing: " + repr(missing))
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, default=REPORT_ROOT.parent / "docs" / "REPORT_NUMBERS_CROSSWALK.md")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    sources = Sources(find_repo(args.repo))
    expected, history, metadata = derive(sources)
    text = args.file.read_text(encoding="utf-8")
    actual = table_rows(text, r"CW\d+\b")
    failures = []
    if set(actual) != set(expected):
        failures.append("Crosswalk row IDs differ")
    for key, value in expected.items():
        cells = actual.get(key, [])
        if len(cells) != 6 or cells[1] != value:
            failures.append(key + " report cell mismatch: " + value)
    failures.extend(check_source_cells(actual, metadata))
    actual_history = table_rows(text, r"(?:6dbf9e8|7420d16|f3dcd4a|d96a56b|4bab4a5)\b")
    if actual_history != history:
        failures.append("Capacity history table mismatch")
    required = [metadata["p6_finished"], "60.0", "0.629", "106.71", "4.97", "4.04"]
    if any(value not in text for value in required):
        failures.append("Missing legacy value or p6 timestamp")
    if metadata["legacy_values"] != {"capacity": ("1449", "1389.0", "60.0"), "m2": "106.71", "netem": ("4.97", "4.04"), "regret": ["0.629", "0.429"]}:
        failures.append("Legacy source values differ")
    if metadata["workbook_cells"] != {"v4_workbook": {"B6": "2개", "C6": "3개", "B7": "2,560 B", "C7": "3,840 B"}, "stage1_workbook": {"E5": 32, "E7": 32}}:
        failures.append("Workbook source values differ")
    if metadata["p6_finished"] != metadata["p6_latest_history"] or len(metadata["readme_regret"]) != 2:
        failures.append("Legacy history or regret table coverage differs")
    if any(dates != ["2026-09-29"] for alias, dates in metadata["journal_dates"].items() if alias != "p18_units") or metadata["journal_dates"]["p18_units"] != ["2026-10-01"]:
        failures.append("Journal date coverage differs")
    result = {"schema": "report_crosswalk_check/1", "status": "fail" if failures else "pass", "report_rows": len(expected), "capacity_history_rows": len(history), "report_values": expected, "capacity_history_values": history, "metadata": metadata, "sources": sources.evidence, "failures": failures}
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    return int(bool(failures))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        raise SystemExit(1)
