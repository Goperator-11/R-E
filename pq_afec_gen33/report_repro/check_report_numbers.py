import hashlib
import json
import math
from pathlib import Path
import re
import sys

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPORT_ROOT, source_path


def tex(name):
    return (REPORT_ROOT / (name + ".tex")).read_text(encoding="utf-8")


def load_source(key):
    return json.loads(source_path(key).read_text(encoding="utf-8"))


def pairs(text):
    return [(float(x), float(y)) for x, y in re.findall(r"\((-?[\d.]+),(-?[\d.]+)\)", text)]


def check_fig3():
    workbook = openpyxl.load_workbook(source_path("v4_workbook"), data_only=True)
    try:
        sweep = {(row[0], row[1]): row[2] for row in workbook["2_임계정밀"].iter_rows(min_row=5, values_only=True) if isinstance(row[0], (int, float))}
        overview = {row[0]: row[1:3] for row in workbook["1_개괄스윕"].iter_rows(min_row=4, values_only=True) if isinstance(row[0], (int, float))}
        rtt = [row[:3] for row in workbook["3_RTT비례"].iter_rows(min_row=4, max_row=7, values_only=True)]
    finally:
        workbook.close()
    allowed = {(float(cert), round(float(value), 3)) for (cert, group), value in sweep.items()}
    for cert in (4032,):
        allowed.add((float(cert), round(float(overview[cert][0]), 3)))
        allowed.add((float(cert), round(float(overview[cert][1]), 3)))
    panel_a, panel_b = tex("fig3_threshold").split(r"\begin{axis}[name=B")
    bad = 0
    count = 0
    for match in re.finditer(r"\\addplot\[(x25519|hybrid)[^\]]*\] coordinates \{([^}]*)\}", panel_a):
        for point in pairs(match.group(2)):
            count += 1
            if (point[0], round(point[1], 3)) not in allowed:
                bad += 1
                print("fig3a mismatch", point)
    if count == 0:
        bad += 1
        print("fig3a missing coordinates")
    for rtt_ms, classical, hybrid in rtt:
        if "(%g,%g)" % (rtt_ms, classical - hybrid) not in panel_b:
            bad += 1
            print("fig3b missing", rtt_ms, classical - hybrid)
        if "%.1f\\%%" % (100 * (classical - hybrid) / rtt_ms) not in panel_b:
            bad += 1
            print("fig3b pct", rtt_ms)
    print("fig3 points", count, "bad", bad)
    return bad


def fig4_segments(snapshot, group):
    width, slope, base = snapshot["P"], snapshot["c"], snapshot["s0"][group]
    arms = [row["B"] for row in snapshot["padding_arms"] + snapshot["parity_arms"] if row["group"] == group]
    left, right = min(arms) - 60, max(arms) + 60
    count = math.ceil(3 * left / width)
    model = lambda n: n * width - base - n * slope
    segments = []
    while True:
        edge = count * width / 3
        end = min(edge, right)
        segments.append((left, model(count), end, model(count)))
        if edge >= right:
            return segments
        segments.append((end, model(count), end, model(count + 1)))
        left = edge
        count += 1


def check_fig4():
    quantum = load_source("p12_quantum")
    threshold = load_source("p2_threshold")
    text = tex("fig4_staircase_cliff")
    snapshot = json.loads((REPORT_ROOT / "data/fig4.json").read_text(encoding="utf-8"))
    bad = 0
    count = 0
    for group in snapshot["s0"]:
        for segment in fig4_segments(snapshot, group):
            count += 1
            if "(%.2f,%.2f)(%.2f,%.2f)" % segment not in text:
                bad += 1
                print("fig4 stair missing", group, segment)
    for config in quantum["configs"]:
        count += 1
        if "(%.2f,%.2f)" % (config["first_flight_bytes"], (config["threshold_lo"] + config["threshold_hi"]) / 2) not in text:
            bad += 1
            print("fig4 padding missing", config["group"], config["first_flight_bytes"])
    for config in threshold["thresholds"]:
        if config["arm"] in ("on1", "on2"):
            count += 1
            if "(%.2f,%.2f)" % (config["client_bytes_total"], (config["threshold_lo"] + config["threshold_hi"]) / 2) not in text:
                bad += 1
                print("fig4 parity missing", config["group"], config["client_bytes_total"])
    if count == 0:
        bad += 1
        print("fig4 missing source arms")
    print("fig4 arm points", count, "bad", bad)
    return bad


def transform(value):
    return math.copysign(math.log10(1 + abs(value)), value)


def check_fig6():
    older = {test["cond"]: test for test in load_source("v30_decisions")["H2"]["run1"]["tests"]}
    newer = {test["cond"]: test for test in load_source("v31_decisions")["H2"]["run1"]["tests"]}
    keys30 = ["S_bigcert", "S_rtt200", "D_p17_mbps2", "D_p18_burst3", "D_p11_9000_l5", "D_p15_4032_l5", "H_h_c6000_r80_u10", "H_h_c8000_r120_u5"]
    keys31 = ["S_bigcert", "S_rtt200", "D_p17_mbps2", "D_p18_burst3", "D_p11_9000_l5", "D_p15_4032_l5", "H_h_c6000_r120_u10", "H_h_c8000_r120_u10", "H_h_c12000_r120_u5", "H_h_c14000_r120_u5"]
    text = tex("fig6_forest")
    bad = 0
    count = 0
    for decisions, keys in ((older, keys30), (newer, keys31)):
        for key in keys:
            test = decisions[key]
            for value in (test["est"], test["lo95"], test["hi95"]):
                count += 1
                if "%.4f" % transform(value) not in text:
                    bad += 1
                    print("fig6 coord missing", key, value)
                if "%.1f" % abs(value) not in text:
                    bad += 1
                    print("fig6 text missing", key, value)
    margin_present = "%.4f" % transform(-1.0) in text
    if not margin_present:
        bad += 1
    print("fig6 values", count, "bad", bad)
    print("margin coord present", margin_present)
    print("undrawn min lo95", min(test["lo95"] for key, test in older.items() if key not in keys30), min(test["lo95"] for key, test in newer.items() if key not in keys31))
    print("v3.0 count", len(keys30), "v3.1 count", len(keys31), "of", len(older), len(newer))
    print("carried-over conditions per generation", sum(1 for key in older if key.startswith("D_")), "uplink-limited held-out v3.0", [key for key in older if key.startswith("H_") and not key.endswith("u0")], "v3.1", [key for key in newer if key.startswith("H_") and not key.endswith("u0")])
    return bad


def check_fig5():
    dominance = load_source("p14_dominance")
    arms = {arm["arm"]: arm for arm in dominance["arms"] if abs(arm["loss"] - 5) < 1e-9}
    text = tex("fig5_levers")
    bad = 0
    if not arms:
        bad += 1
        print("fig5 missing source arms")
    for arm, values in arms.items():
        samples = sorted(values["ms"])
        count = len(samples)
        mean = sum(samples) / count
        standard_deviation = (sum((value - mean) ** 2 for value in samples) / (count - 1)) ** 0.5
        half_width = 1.96 * standard_deviation / count ** 0.5
        if "(%.3f," % mean not in text or "+- (%.3f,0)" % half_width not in text:
            bad += 1
            print("fig5b missing", arm)
        for value in (samples[0], samples[count // 2], samples[-1]):
            if "%.3f" % value not in text:
                bad += 1
                print("fig5a missing", arm, value)
    print("fig5 bad", bad, {arm: round(sum(values["ms"]) / len(values["ms"]), 2) for arm, values in arms.items()})
    return bad


def check_number_sources():
    numbers = json.loads((REPORT_ROOT / "report_numbers.json").read_text(encoding="utf-8"))
    bad = 0
    seen = {}
    for entry in numbers["entries"]:
        alias, recorded = entry.get("source_alias"), entry.get("source_sha256")
        if not alias or not recorded:
            continue
        if alias not in seen:
            raw = source_path(alias).read_bytes()
            lf = raw.replace(b"\r\n", b"\n")
            seen[alias] = {hashlib.sha256(value).hexdigest() for value in (raw, lf, lf.replace(b"\n", b"\r\n"))}
        if recorded not in seen[alias]:
            bad += 1
            print("report_numbers stale", entry["key"], alias, recorded[:16])
    print("report_numbers sources", len(seen), "stale", bad)
    return bad


def main():
    if len(sys.argv) != 1:
        print("This check accepts no arguments.", file=sys.stderr)
        return 2
    try:
        total_bad = sum(check() for check in (check_fig3, check_fig4, check_fig6, check_fig5, check_number_sources))
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 2
    print("total bad", total_bad)
    return 1 if total_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
