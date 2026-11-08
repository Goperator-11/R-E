import json
from pathlib import Path
import re
import sys

import numpy as np
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import DATA_DIR, source_path, source_reference


def load_source(key):
    return json.loads(source_path(key).read_text(encoding="utf-8"))


def dump(name, value):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / (name + ".json")).open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    print(name, "ok")


def export_fig3():
    workbook = openpyxl.load_workbook(source_path("v4_workbook"), data_only=True)
    try:
        rows = [row[:8] for row in workbook["2_임계정밀"].iter_rows(min_row=5, values_only=True) if isinstance(row[0], (int, float))]
        header2 = list(next(workbook["2_임계정밀"].iter_rows(min_row=4, max_row=4, values_only=True)))[:8]
        overview = [row[:3] for row in workbook["1_개괄스윕"].iter_rows(min_row=4, values_only=True) if isinstance(row[0], (int, float))]
        header1 = list(next(workbook["1_개괄스윕"].iter_rows(min_row=3, max_row=3, values_only=True)))[:3]
        rtt = [row[:3] for row in workbook["3_RTT비례"].iter_rows(min_row=4, max_row=7, values_only=True)]
        header3 = list(next(workbook["3_RTT비례"].iter_rows(min_row=3, max_row=3, values_only=True)))[:3]
    finally:
        workbook.close()
    dump("fig3", {
        "source": source_reference("v4_workbook"),
        "sweep_header": header2,
        "sweep": [list(row) for row in rows],
        "overview_header": header1,
        "overview": [list(row) for row in overview],
        "rtt_header": header3,
        "rtt": [list(row) for row in rtt],
        "threshold_bisect_laptop": {"X25519": [3312, 3368], "X25519MLKEM768": [5917, 5974]},
    })


def export_fig4():
    quantum = load_source("p12_quantum")
    threshold = load_source("p2_threshold")
    padding = [dict(group=config["group"], B=config["first_flight_bytes"], lo=config["threshold_lo"], hi=config["threshold_hi"], W=config.get("ips") or config.get("initial_size")) for config in quantum["configs"]]
    parity = [dict(group=config["group"], arm=config["arm"], B=config["client_bytes_total"], lo=config["threshold_lo"], hi=config["threshold_hi"]) for config in threshold["thresholds"] if config["arm"] in ("on1", "on2")]
    with source_path("p12_units").open(encoding="utf-8") as stream:
        units = [json.loads(line) for line in stream if line.strip()]
    fingerprint = units[-1]["fp"]
    certificate_sizes = {"x25519": 4218, "X25519MLKEM768": 6937}
    cliff = []
    for entry in units:
        match = re.fullmatch(r"(\w+)\|ips(\d+)\|c(\d+)\|n15", entry["key"])
        if match and entry["fp"] == fingerprint and int(match[3]) == certificate_sizes[match[1]]:
            cliff.append(dict(group=match[1], W=int(match[2]), p50=entry["val"]["p50"], two_rtt_rate=entry["val"]["two_rtt_rate"]))
    dump("fig4", {
        "source": [source_reference(key) for key in ("p12_quantum", "p2_threshold", "p12_units")],
        "P": 1280,
        "c": 41.983,
        "s0": {"x25519": 382.45, "X25519MLKEM768": 1472.0},
        "padding_arms": padding,
        "parity_arms": parity,
        "cliff": cliff,
    })


def export_fig5():
    dominance = load_source("p14_dominance")
    arms = [arm for arm in dominance["arms"] if abs(arm["loss"] - 5) < 1e-9]
    output = []
    for arm in arms:
        values = np.array(arm["ms"], dtype=float)
        count = len(values)
        rest = {key: value for key, value in arm.items() if key != "ms"}
        output.append(dict(
            arm=arm["arm"],
            n=count,
            ms=sorted(float(value) for value in values),
            mean=float(values.mean()),
            share_le_75=float((values <= 75).sum() / count * 100),
            share_75_150=float(((values > 75) & (values <= 150)).sum() / count * 100),
            share_gt_150=float((values > 150).sum() / count * 100),
            meta=rest,
        ))
    top = {key: value for key, value in dominance.items() if key != "arms"}
    dump("fig5", {"source": source_reference("p14_dominance"), "top": top, "arms": output})


def export_fig6():
    older = load_source("v30_decisions")
    newer = load_source("v31_decisions")
    dump("fig6", {
        "source": [source_reference(key) for key in ("v30_decisions", "v31_decisions")],
        "v30_run1": {test["cond"]: test for test in older["H2"]["run1"]["tests"]},
        "v31_run1": {test["cond"]: test for test in newer["H2"]["run1"]["tests"]},
    })


def main():
    if len(sys.argv) != 1:
        print("This export accepts no arguments.", file=sys.stderr)
        return 2
    for export in (export_fig3, export_fig4, export_fig5, export_fig6):
        export()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
