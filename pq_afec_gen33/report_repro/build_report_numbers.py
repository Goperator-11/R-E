import argparse
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPORT_ROOT, source_path, source_reference


def normalize(value):
    number = Decimal(str(value).replace(",", "").replace("−", "-"))
    if not number.is_finite():
        raise ValueError("Non-finite numeric value")
    return "0" if number == 0 else format(number.normalize(), "f")


class Builder:
    def __init__(self):
        self.entries = []
        self.loaded = {}
        self.groups = {}

    def read(self, alias, kind="json"):
        if (alias, kind) not in self.loaded:
            path = source_path(alias)
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig") if kind != "binary" else None
            value = json.loads(text) if kind == "json" else text
            self.loaded[alias, kind] = value, hashlib.sha256(raw).hexdigest()
        return self.loaded[alias, kind][0]

    def add(self, key, alias, source_key, values, trace_ids=(), formats=(), source_kind="measurement", group=None, kind="json", calculation=None):
        self.read(alias, kind)
        values = [value for value in values if value is not None and not isinstance(value, bool)]
        numbers = {normalize(value) for value in values}
        for value in values:
            for spec in formats:
                numbers.add(normalize(format(float(value), spec)))
        entry = {
            "key": key,
            "source": source_reference(alias),
            "source_alias": alias,
            "source_key": source_key,
            "source_sha256": self.loaded[alias, kind][1],
            "source_kind": source_kind,
            "trace_ids": list(trace_ids),
            "status": "verified",
            "values": values,
            "numbers": sorted(numbers, key=Decimal),
            "formats": list(formats),
        }
        if calculation:
            entry["calculation"] = calculation
        self.entries.append(entry)
        if group:
            for name in group if isinstance(group, tuple) else (group,):
                self.groups.setdefault(name, []).append(entry)

    def attempt(self, name, callback):
        try:
            callback()
        except (OSError, ValueError, KeyError, IndexError, TypeError, statistics.StatisticsError) as error:
            self.entries.append({"key": name, "source": "", "source_key": "", "source_kind": "unverified", "trace_ids": [], "status": "unverified", "values": [], "numbers": [], "reason": "미확인: " + str(error)})

    def aggregate(self):
        for key, entries in self.groups.items():
            self.entries.append({
                "key": key,
                "source": sorted({source for entry in entries for source in (entry["source"] if isinstance(entry["source"], list) else [entry["source"]])}),
                "source_key": [entry["key"] for entry in entries],
                "source_kind": "aggregate",
                "trace_ids": sorted({tid for entry in entries for tid in entry["trace_ids"]}),
                "status": "verified",
                "values": [value for entry in entries for value in entry["values"]],
                "numbers": sorted({number for entry in entries for number in entry["numbers"]}, key=Decimal),
            })


def p14_numbers(builder):
    data = builder.read("p14_dominance")
    by_loss = {}
    for index, arm in enumerate(data["arms"]):
        samples = arm["ms"]
        mean = statistics.mean(samples)
        half = 1.96 * statistics.stdev(samples) / math.sqrt(len(samples))
        by_loss.setdefault(arm["loss"], {})[arm["arm"]] = (index, samples, mean, half)
        key = "p14.%s.loss%s" % (arm["arm"], normalize(arm["loss"]))
        builder.add(key, "p14_dominance", "arms[%d].ms" % index, [len(samples), mean, half], [4, 11, 13, 100], [".2f", ".3f"], group="RT-13", calculation="n=len(ms); mean=mean(ms); half_width=1.96*stdev(ms,ddof=1)/sqrt(n)")
        builder.add(key + ".metadata", "p14_dominance", "arms[%d]" % index, [arm["loss"], arm["m"], arm["delta"], arm["n"], arm["p50"], arm["ff_bytes_med"]], [4, 11, 13, 54], [".1f", ".2f"], group="RT-13")
        tail_counts = [sum(value > bound for value in samples) for bound in (75, 150)]
        builder.add(key + ".tail", "p14_dominance", "arms[%d].ms" % index, tail_counts + [100 * count / len(samples) for count in tail_counts], [101, 104], [".2f"], group="RT-13", calculation="count(ms>75),count(ms>150); percentage=100*count/n")
    for loss, arms in by_loss.items():
        for left, right in (("base", "pad"), ("parity", "combo"), ("pad", "combo"), ("pad", "parity")):
            a, b = arms[left], arms[right]
            difference = a[2] - b[2]
            half = math.hypot(a[3], b[3])
            builder.add("p14.loss%s.%s_minus_%s" % (normalize(loss), left, right), "p14_dominance", "arms[%d].ms; arms[%d].ms" % (a[0], b[0]), [difference, half], [11, 102, 141], [".2f", ".3f"], group="RT-13", calculation="mean(left)-mean(right); independent half_width=sqrt(half_left^2+half_right^2)")


def p17_numbers(builder):
    data = builder.read("p17_adaptive_value")
    builder.add("p17.design", "p17_adaptive_value", "cycles;n_per_seg;rtt_ms", [data["cycles"], data["n_per_seg"], data["rtt_ms"]], [120, 121, 122], group="RT-15")
    for index, gain in enumerate(data["gain"]):
        for loss, adaptation in gain["adapt"].items():
            lags = adaptation["lags"]
            values = [100 * adaptation["hit_rate"], adaptation["n"], len(lags), adaptation["never_adapted"], adaptation["lag_med"]] + [value for value in lags if value is not None]
            builder.add("p17.%s.loss%s.adaptation" % (gain["cond"], loss), "p17_adaptive_value", "gain[%d].adapt[%s]" % (index, json.dumps(loss)), values, [120, 121, 122, 144], [".1f", ".2f"], group="RT-15", calculation="hit percentage=100*hit_rate; lags omit null only from numeric values; lag count and never_adapted remain separate")
        builder.add("p17.%s.gain" % gain["cond"], "p17_adaptive_value", "gain[%d]" % index, [gain[key] for key in ("gain_ms", "oracle_gain_ms", "oracle_gain_ci95_half_ms", "cert", "rtt_ms", "n_auto")], [108, 109, 121], [".2f", ".3f"], group="RT-15")


def text_numbers(builder, key, alias, pattern, trace_ids, group, formats=(), source_kind="metadata", json_key=None):
    kind = "json" if json_key else "text"
    data = builder.read(alias, kind)
    text = data[json_key] if json_key else data
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if not matches:
        raise ValueError("No source match for " + key)
    values = [match.group(index) for match in matches for index in range(1, len(match.groups()) + 1)]
    builder.add(key, alias, (json_key + ":" if json_key else "") + "regex:" + pattern, values, trace_ids, formats, source_kind, group, kind)


def seal_numbers(builder):
    counts = []
    for alias in ("seal_stage0", "seal_m1confirm", "seal_stage2", "seal_stage3"):
        count = len(builder.read(alias)["sha256"])
        counts.append(count)
        builder.add(alias + ".file_count", alias, "len(sha256)", [count], [69], group="RT-05", source_kind="metadata")
    entries = builder.groups["RT-05"]
    builder.entries.append({"key": "sealed.file_count", "source": [entry["source"] for entry in entries], "source_key": [entry["key"] for entry in entries], "source_kind": "metadata", "trace_ids": [69], "status": "verified", "values": [sum(counts)], "numbers": [normalize(sum(counts))], "calculation": "sum of the four manifest sha256 mapping lengths"})
    builder.groups["RT-05"].append(builder.entries[-1])


def connection_numbers(builder):
    totals = []
    for alias, field in (("v30_stage0", "cells"), ("v30_m1confirm", "cells"), ("v30_run1", "conds"), ("v30_run2", "conds"), ("v31_run1", "conds"), ("v31_run2", "conds")):
        data = builder.read(alias)
        count = sum(arm["n_requested"] for cell in data[field] for arm in cell["arms"].values())
        returned = sum(arm["n_returned"] for cell in data[field] for arm in cell["arms"].values())
        if count != returned:
            raise ValueError("Requested and returned counts differ: " + alias)
        totals.append(count)
        builder.add(alias + ".connections", alias, field + "[*].arms[*].n_requested; n_returned", [count], [8, 42], group="RT-14", calculation="sum over all conditions and arms; requested==returned checked")
        builder.add(alias + ".condition_count", alias, "len(" + field + ")", [len(data[field])], [42], group="RT-26", source_kind="metadata")
    entries = builder.groups["RT-14"]
    for key, value, selected in (("sealed.total_connections", sum(totals), entries), ("generation_comparison.connections", sum(totals[2:]), entries[2:])):
        entry = {"key": key, "source": [item["source"] for item in selected], "source_key": [item["key"] for item in selected], "source_kind": "measurement", "trace_ids": [8], "status": "verified", "values": [value], "numbers": [normalize(value)], "calculation": "sum of source connection totals"}
        builder.entries.append(entry)
        builder.groups["RT-14"].append(entry)


def workbook_numbers(builder):
    builder.read("v4_workbook", "binary")
    workbook = openpyxl.load_workbook(source_path("v4_workbook"), data_only=True)
    try:
        sheet = workbook["3_RTT비례"]
        for row in range(4, 8):
            values = [sheet.cell(row, col).value for col in range(1, 6)]
            builder.add("v4.rtt.row%d" % row, "v4_workbook", "3_RTT비례!A%d:E%d" % (row, row), values, [3, 83], [".1f"], group="RT-08", kind="binary")
        cells = []
        for row in workbook["2_임계정밀"].iter_rows(values_only=True):
            if row[0] == 3500:
                cells.extend(value for value in row[:8] if isinstance(value, (int, float)))
        builder.add("v4.threshold.c3500", "v4_workbook", "2_임계정밀 rows where column A=3500, numeric columns A:H", cells, [83], [".1f"], group="RT-08", kind="binary")
        for row_number, row in enumerate(workbook["1_개괄스윕"].iter_rows(values_only=True), 1):
            if row[0] == 4032:
                builder.add("v4.overview.c4032", "v4_workbook", "1_개괄스윕!A%d:F%d" % (row_number, row_number), list(row[:6]), [83], [".1f"], group="RT-08", kind="binary")
    finally:
        workbook.close()


def benchmark_numbers(builder):
    data = builder.read("current_benchmark")
    for label, result in data["results"].items():
        floor = result["noninferiority"]["v331_none_vs_v32"]
        builder.add("benchmark.%s.none_floor" % label, "current_benchmark", "results.%s.noninferiority.v331_none_vs_v32" % label, [floor[key] for key in ("cell_count", "pass", "fail", "inconclusive")], [139], group="RT-19", source_kind="world")
        for index, comparison in enumerate(result["comparisons"]):
            if comparison["candidate"] not in ("v331_none", "v331_c1") or comparison["baseline"] != "v32":
                continue
            values = [comparison[key] for key in ("mean_ms", "seed_lower_ms", "seed_upper_ms", "adjusted_lower_ms", "adjusted_upper_ms")]
            values.append(abs(comparison["mean_ms"]))
            builder.add("benchmark.%s.%s.%s" % (label, comparison["candidate"], comparison["scenario"]), "current_benchmark", "results.%s.comparisons[%d]" % (label, index), values, [139], [".2f", ".3f"], group="RT-19", source_kind="world", calculation="raw mean and bounds; absolute mean is included for sentences phrased as a decrease")
    seeds = data["b6_independent_repetition"]["plan"]["seeds"]
    builder.add("benchmark.b6.seed_count", "current_benchmark", "b6_independent_repetition.plan.seeds", [len(seeds), min(seeds), max(seeds)], [139], group="RT-19", source_kind="world", calculation="len,min,max of the independently repeated seed list")
    fields = ("mean_ms", "seed_lower_ms", "seed_upper_ms", "shared_mc_bound_ms", "adjusted_lower_ms", "adjusted_upper_ms")
    for label, comparisons in data["b6_independent_repetition"]["results"].items():
        for index, comparison in enumerate(comparisons):
            values = [comparison[field] for field in fields]
            values.append(len(comparison["seed_estimates"]))
            builder.add(
                "benchmark.b6.%s.%s_vs_%s.%s" % (label, comparison["candidate"], comparison["baseline"], comparison["scenario"]),
                "current_benchmark",
                "b6_independent_repetition.results.%s[%d]" % (label, index),
                values,
                [139],
                [".2f", ".3f"],
                group="RT-19",
                source_kind="world",
                calculation="fields=" + ",".join(fields) + "; final value=len(seed_estimates); independent repetition only",
            )


def policy_numbers(builder):
    text = builder.read("current_policy", "text")
    constants = {}
    for name in ("QUICGO_MAX_IPS", "PARITY_OVERHEAD_BASE", "PARITY_OVERHEAD_PER_K"):
        match = re.search(r"^" + name + r"\s*=\s*(\d+)", text, re.MULTILINE)
        if not match:
            raise ValueError("Missing policy constant " + name)
        constants[name] = int(match.group(1))
    maximum = constants["QUICGO_MAX_IPS"]
    base = constants["PARITY_OVERHEAD_BASE"]
    per_k = constants["PARITY_OVERHEAD_PER_K"]
    builder.add("policy.parity_constants", "current_policy", "QUICGO_MAX_IPS;PARITY_OVERHEAD_BASE;PARITY_OVERHEAD_PER_K", list(constants.values()), [55, 147], source_kind="model", group="RT-20", kind="text")
    builder.add("policy.parity_limit", "current_policy", "QUICGO_MAX_IPS", [maximum], source_kind="model", group="BL-09", kind="text")
    for k in range(1, 5):
        bound = maximum - base - per_k * k
        builder.add("policy.parity_bound.k%d" % k, "current_policy", "QUICGO_MAX_IPS-PARITY_OVERHEAD_BASE-PARITY_OVERHEAD_PER_K*k", [k, bound, bound + 1], [147], source_kind="model", group="RT-20", kind="text", calculation="largest integer W satisfying W+base+per_k*k<=maximum; next integer is the first excluded W")
    protocol = builder.read("current_protocol")
    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("W", "w", "base_w", "base_ips") and isinstance(child, (int, float)):
                    yield path + "." + key, child
                yield from walk(child, path + "." + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from walk(child, path + "[%d]" % index)
    found = list(walk(protocol, "$"))
    if not found:
        raise ValueError("No W field in benchmark protocol")
    for path, value in found:
        builder.add("protocol." + path, "current_protocol", path, [value, value + base + per_k * 2], [55, 147], source_kind="model", group="RT-20", calculation="source W and parity_bytes(W,k=2)")


def decision_numbers(builder):
    for alias in ("v30_decisions", "v31_decisions"):
        data = builder.read(alias)
        for run in ("run1", "run2"):
            for index, test in enumerate(data["H1"][run]["tests"]):
                builder.add("%s.H1.%s.%s" % (alias, run, test["cond"]), alias, "H1.%s.tests[%d]" % (run, index), [test[key] for key in ("est", "lo95", "hi95", "lb_holm")], [5, 129, 153], [".2f", ".3f"], group="RT-30")
    data = builder.read("v31_decisions")
    for index, condition in enumerate(data["H5"]["conds"]):
        for arm, value in condition["arms"].items():
            builder.add("v31.cold.%s.%s" % (condition["cond"], arm), "v31_decisions", "H5.conds[%d].arms[%s].first_visit_ff_uplink_bytes_mean" % (index, json.dumps(arm)), [value["first_visit_ff_uplink_bytes_mean"]], [151], group="RT-28")


def p10_numbers(builder):
    data = builder.read("p10_completeness")
    builder.add("p10.test_counts", "p10_completeness", "tests_passed;tests_total", [data["tests_passed"], data["tests_total"]], [116], source_kind="metadata", group="RT-16")
    for index, result in enumerate(data["results"]):
        match = re.search(r"C2 RTT (\d+) ms", result["check"])
        if match:
            builder.add("p10.rtt.%d" % index, "p10_completeness", "results[%d].check" % index, [int(match.group(1))], [115, 116], source_kind="metadata", group="RT-16")


def p8_dates(builder):
    text = builder.read("p8_units", "text")
    dates = sorted({json.loads(line)["recorded_at"].split("T")[0] for line in text.splitlines() if line.strip() and "recorded_at" in json.loads(line)})
    if not dates:
        raise ValueError("No recorded_at in p8 journal")
    values = [int(part) for date in dates for part in date.split("-")]
    builder.add("p8.recorded_dates", "p8_units", "unique recorded_at UTC calendar dates", values, [114], source_kind="metadata", group="RT-17", kind="text", calculation="year,month,day parsed from recorded_at; dates=" + ",".join(dates))


def p8_projection(builder):
    data = builder.read("p8_stability")
    checks = [(index, re.search(r"차이 ([\d.]+) ms \(첫 (\d+)회", entry["detail"])) for index, entry in enumerate(data["checks"])]
    index, match = next((index, match) for index, match in checks if match is not None)
    length = builder.read("p17_adaptive_value")["n_per_seg"]
    effect = float(match.group(1)) * int(match.group(2)) / length
    builder.add("p8.projected_segment_effect", "p8_stability", "checks[%d].detail" % index, [effect], [113], [".3f", ".4f"], source_kind="model", group="RT-17", calculation="recorded order effect * initial count / p17.n_per_seg; denominator=%s; denominator_source=%s; denominator_sha256=%s" % (length, source_reference("p17_adaptive_value"), builder.loaded["p17_adaptive_value", "json"][1]))
    builder.add("p8.projection_segment_length", "p17_adaptive_value", "n_per_seg", [length], [113], source_kind="model", group="RT-17")
    data = builder.read("legacy_loop_state")
    for stage in ("p8", "p10", "p15", "p16", "p17", "p18", "p20"):
        candidates = [(index, row) for index, row in enumerate(data["history"]) if row.get("stage") == stage and row.get("status") == "failed"]
        index, row = candidates[-1]
        date = row["at"].split()[0]
        builder.add("loop.%s.last_failure_date" % stage, "legacy_loop_state", "history[%d].at" % index, [int(part) for part in date.split("-")], [114], source_kind="metadata", group="RT-17", calculation="year,month,day of saved timestamp=" + row["at"])


def replay_numbers(builder):
    data = builder.read("current_replay")
    total = data["summary"]["none"]["total"]
    builder.add("replay.none.total", "current_replay", "summary.none.total.n;decision_match;decision_mismatch", [total[key] for key in ("n", "decision_match", "decision_mismatch")], [138], source_kind="replay", group="BL-09")


def candidate_numbers(builder):
    text = builder.read("current_candidate_dispositions", "text")
    headings = re.findall(r"^## ([^\r\n]+)\r?$", text, re.MULTILINE)
    expected = ["L2", "L3", "L5", "J1", "J6", "J7", "M1", "O2", "J5", "O3", "O4", "J3", "M4", "J8"]
    trailing = headings[len(expected):]
    if headings[:len(expected)] != expected or trailing not in ([], ["루프 뒤 개발 평가"]):
        raise ValueError("Candidate headings must match the final card order: " + ", ".join(expected))
    builder.add("candidates.final.count", "current_candidate_dispositions", "level-2 candidate headings before the post-loop section", [len(expected)], source_kind="metadata", group="BL-09", kind="text", calculation="exact ordered ID comparison of the first level-2 headings: " + ",".join(expected) + "; an optional trailing '루프 뒤 개발 평가' section is not counted")


def sealed_recomputation_numbers(builder):
    data = builder.read("current_verdict_recompute")
    builder.add("sealed.recompute.current", "current_verdict_recompute", "item_count;max_abs_diff_ms", [data["item_count"], data["max_abs_diff_ms"]], [70], source_kind="implementation_audit", group="RT-05", calculation="preserved functions reused; comparisons include verdicts, statistics, denominators and order; not independent")
    seals = builder.read("current_seal_rehash")
    values = [seals["file_count"], seals["mismatch_count"]]
    values.extend(int(part) for part in seals["checked_at"].split("T")[0].split("-"))
    builder.add("sealed.rehash.current", "current_seal_rehash", "file_count;mismatch_count;checked_at", values, [69], source_kind="implementation_audit", group="RT-05", calculation="seal entry count, mismatches and UTC year/month/day; repeated paths count once per seal entry")


def write_trace(trace, entries):
    lines = ["# 보고서 출처 대조표", "", "이 표는 보존한 감사 trace의 행 순서와 여섯 열을 그대로 옮겼다. 감사 판정 열은 당시 기록이며 이번 실행의 검증 결과가 아니다. 실제 파일을 다시 읽은 수치는 `report_repro/report_numbers.json`의 verified 항목에 있다. 수치 항목이 연결돼 있어도 그 행의 문장 전체를 검증했다는 뜻은 아니다.", "", "원본 trace와 SHA256은 `report_repro/trace_sources.json`에 보존한다. 외부 원문, 날짜의 의미, 서술형 주장처럼 자동 대조하지 않은 부분은 미확인으로 남는다.", "", "| trace | content.py 줄 | 주장 | 보고서 값 | 출처 | 감사 값 | 감사 판정 | 이번 수치 대조 키 |", "|---|---|---|---|---|---|---|---|"]
    for index, row in enumerate(trace, 1):
        keys = [entry["key"] for entry in entries if index in entry["trace_ids"] and entry["status"] == "verified" and entry["source_kind"] != "aggregate"]
        cells = ["T%03d" % index] + row + [", ".join(keys) if keys else "미확인: 자동 수치 대조 없음"]
        lines.append("| " + " | ".join(str(cell).replace("|", "&#124;").replace("\n", "<br>") for cell in cells) + " |")
    path = REPORT_ROOT.parent / "docs" / "보고서 출처 대조표.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=REPORT_ROOT / "report_numbers.json")
    args = parser.parse_args()
    manifest = json.loads((REPORT_ROOT / "trace_sources.json").read_text(encoding="utf-8"))
    builder = Builder()
    for name, callback in (("p14", p14_numbers), ("p17", p17_numbers), ("seals", seal_numbers), ("connections", connection_numbers), ("v4", workbook_numbers), ("benchmark", benchmark_numbers), ("policy", policy_numbers), ("decisions", decision_numbers), ("p8_dates", p8_dates), ("p8_projection", p8_projection), ("p10", p10_numbers), ("replay", replay_numbers), ("candidates", candidate_numbers), ("sealed_recomputation", sealed_recomputation_numbers)):
        builder.attempt(name, lambda callback=callback: callback(builder))
    text_specs = [
        ("v31.recompute.items", "v31_recompute", r"compare\.py checked (\d+) items", [70], "RT-05", (), "audit_record", "method_summary"),
        ("v31.recompute.max_error", "v31_recompute", r"largest is ([\d.e+-]+) at R lo95", [70], "RT-05", (".2g",), "audit_record", "method_summary"),
        ("p16.block_drift", "p16_uplink", r"최대 \|블록 차이\| ([\d.]+) ms, 신호 ([\d.]+) ms", [119], "RT-18", (".2f",), "measurement", None),
        ("legacy.p17.hit", "legacy_fixloop", r"최악 적중률 (40\.3)%", [120], "RT-15", (), "audit_record", None),
        ("legacy.p17.date", "legacy_fixloop", r"\[p17\][^\n]*\(기록 (2026)-(09)-(27) 01:42\)", [120], "RT-15", (), "metadata", None),
        ("p8.order_effect", "p8_stability", r"차이 ([\d.]+) ms \(첫 (\d+)회", [112, 113], "RT-17", (), "measurement", None),
        ("claims.initial_cwnd", "current_claims", r"initial cwnd[^\n]{0,100}?IW는 (\d+)패킷", [145, 153], "RT-30", (), "documentation", None),
    ]
    for spec in text_specs:
        builder.attempt(spec[0], lambda spec=spec: text_numbers(builder, *spec))
    builder.aggregate()
    known_keys = {entry["key"] for entry in builder.entries}
    for key in manifest["item_ids"]:
        if key not in known_keys:
            builder.entries.append({"key": key, "source": manifest["origin"], "source_key": "items[id=" + key + "]", "source_sha256": manifest["origin_sha256"], "source_kind": "audit_reference", "trace_ids": [], "status": "unverified", "values": [], "numbers": [], "reason": "수치 검증 대상이 아닌 서술형 정정 또는 후속 카드 확인 대기. 이 항목은 숫자를 허용하지 않는다."})
    covered = {tid for entry in builder.entries if entry["status"] == "verified" for tid in entry["trace_ids"]}
    for index, row in enumerate(manifest["trace"], 1):
        if index not in covered:
            builder.entries.append({"key": "trace.T%03d" % index, "source": row[3], "source_key": "trace[%d]" % (index - 1), "source_kind": "audit_reference", "trace_ids": [index], "status": "unverified", "values": [], "numbers": [], "reason": "미확인: 서술형 출처 키 또는 이번 실행에서 자동 검증하지 않은 항목. 감사 설명의 숫자는 허용값에 넣지 않았다."})
    numbers = sorted({number for entry in builder.entries if entry["status"] == "verified" for number in entry["numbers"]}, key=Decimal)
    result = {"schema": "report_numbers/1", "trace_origin_sha256": manifest["origin_sha256"], "trace_row_count": len(manifest["trace"]), "trace_with_numeric_entries": len(covered), "normalization": "Decimal; remove thousands separators; Unicode minus converted; finite values only; explicit display formats only", "numbers": numbers, "entries": builder.entries}
    failures = [entry["key"] for entry in builder.entries if entry["source_kind"] == "unverified"]
    print(json.dumps({"trace_rows": len(manifest["trace"]), "trace_with_numeric_entries": len(covered), "verified_entries": sum(entry["status"] == "verified" for entry in builder.entries), "unverified_entries": sum(entry["status"] == "unverified" for entry in builder.entries), "numeric_values": len(numbers), "extraction_failures": failures}, ensure_ascii=False))
    if failures:
        return 1
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_trace(manifest["trace"], builder.entries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
