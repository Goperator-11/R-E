from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics as pystat
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scipy.stats import binom

from experiments.v33 import devbed
from experiments.v33.lib import arms, report_checks
from experiments.v33.lib.report_docs import _interval, _table
from experiments.v33.lib.statistics import interval

SERIES_SCHEMA = "padfec3.x6.p-mean-series/1"
DIAGNOSTICS_SCHEMA = "padfec3.x6.diagnostics/1"
CLOCK_MARGIN_MS = 1000.0
IDLE_KIND = "근사: 서버 first_rx_ns 간격에서 클라이언트 HCT를 뺀 값. 공식 mean_idle_ms가 아니다"
IDLE_LIMITS = ["first datagram이 유실되면 first_rx_ns가 밀려 앞뒤 간격이 함께 흔들린다",
               "first_rx_ns는 서버 wall clock이라 시각 보정이 간격에 들어간다",
               "단위 마지막 연결은 다음 연결이 없어 표본에서 빠진다"]
CLOCK_REASON = "간격이 계획 gap과 C1 대기 한도에 1000 ms를 더한 값을 넘는다. 서버 wall clock 보정으로 판단해 근사 집계에서 뺀다"
CONTEXT_FIELDS = ("ok", "ms", "p_mean_after", "policy_path", "arrivals_src", "action", "s_hat", "n_need")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def mean(values):
    return math.fsum(values) / len(values) if values else None


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def pretty(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1,
                       allow_nan=False) + "\n").encode("utf-8")


def artifact_hashes(path):
    hashes = {}
    base = Path(path).resolve().parent
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match is None:
            raise ValueError("SHA 목록 형식 오류")
        hashes[(base / match.group(2)).resolve()] = match.group(1)
    return hashes


def journal_units(path):
    result = {}
    with Path(path).open("rb") as stream:
        for line in stream:
            record = json.loads(line)
            if record.get("kind") != "block":
                continue
            for entry in record["data"]["units"]:
                payload = entry["payload"]
                if entry["key"] in result:
                    raise ValueError("저널 단위 중복: " + entry["key"])
                result[entry["key"]] = {name: payload[name] for name in
                                        ("attempt", "raw_sha256", "started_at", "ended_at", "server_delta")}
    return result


class RawUnit:
    def __init__(self, raw_dir, unit, meta):
        self.raw_dir = raw_dir
        self.unit = unit
        self.meta = meta
        self.prefix = f"units/{unit['key']}/attempt_{meta['attempt']}/"

    def read(self, name):
        relative = self.prefix + name
        expected = self.meta["raw_sha256"].get(relative)
        if expected is None:
            raise ValueError("저널에 없는 원자료: " + relative)
        data = (self.raw_dir / relative).read_bytes()
        if sha256_bytes(data) != expected:
            raise ValueError("원자료 SHA 불일치: " + relative)
        return data

    def rows(self):
        rows = [json.loads(line) for line in self.read("client.jsonl").splitlines() if line.strip()]
        if sorted(row["i"] for row in rows) != list(range(self.unit["rows_expected"])):
            raise ValueError("연결 순번이 계획과 다르다: " + self.unit["key"])
        return sorted(rows, key=lambda row: row["i"])

    def conns(self):
        return [json.loads(line) for line in self.read("server.conns.jsonl").splitlines() if line.strip()]

    def tc(self, name):
        return json.loads(self.read(name))

    def stats(self):
        return json.loads(self.read("server.stats.json"))


def context_row(row):
    arrivals = row.get("arrivals")
    action = row.get("action")
    return {"ok": row["ok"], "ms": row["ms"], "p_mean_after": row.get("p_mean_after"),
            "policy_path": row.get("policy_path"),
            "arrivals_src": arrivals.get("src") if isinstance(arrivals, dict) else None,
            "action": ",".join(map(str, action)) if isinstance(action, list) else None,
            "s_hat": row.get("s_hat"), "n_need": row.get("n_need")}


def point_row(unit, row):
    value = row.get("p_mean")
    return {"unit_key": unit["key"], "phase": unit["phase"], "block": unit["block"], "i": row["i"],
            "connection_offset": unit["connection_offset"],
            "connection_index": unit["connection_offset"] + row["i"],
            "p_mean_present": "p_mean" in row, "p_mean": value if numeric(value) else None}


def idle_samples(unit, rows, conns):
    if len(conns) != len(rows) or any(not row["ok"] for row in rows):
        return [], {"unit": unit["key"], "reason": "행 수 불일치 또는 실패 행으로 순서 대응을 하지 않는다"}, 0
    if any(type(conn.get("first_rx_ns")) is not int for conn in conns):
        return [], {"unit": unit["key"], "reason": "first_rx_ns 없음"}, 0
    ordered = sorted(conns, key=lambda conn: conn["first_rx_ns"])
    mismatch = sum(isinstance(row.get("client_scid"), str) and row["client_scid"]
                   and row["client_scid"] != conn["client_scid"]
                   for row, conn in zip(rows, ordered))
    samples = []
    for index in range(len(rows) - 1):
        spacing = (ordered[index + 1]["first_rx_ns"] - ordered[index]["first_rx_ns"]) / 1e6
        samples.append({"i": index, "spacing_ms": spacing, "hct_ms": rows[index]["ms"],
                        "idle_ms": spacing - rows[index]["ms"],
                        "first_rx_ns": ordered[index]["first_rx_ns"],
                        "next_first_rx_ns": ordered[index + 1]["first_rx_ns"]})
    return samples, None, mismatch


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).isoformat()


def cell_specs(plan, task):
    return plan["tasks"][task]["cells"] + plan["tasks"][task].get("additional_cells", [])


def by_trajectory(values):
    grouped = defaultdict(list)
    for trajectory, value in values:
        grouped[trajectory].append(value)
    return {trajectory: mean(items) for trajectory, items in sorted(grouped.items())}


def scope_interval(samples, selector):
    means = by_trajectory((item["trajectory"], item["idle_ms"]) for item in samples if selector(item))
    result = interval(list(means.values()))
    result["by_trajectory"] = {str(key): value for key, value in means.items()}
    result["rows"] = sum(1 for item in samples if selector(item))
    return result


def reweighted(samples, losses):
    per_loss = [by_trajectory((item["trajectory"], item["idle_ms"]) for item in samples
                              if item["measured"] and item["loss"] == loss) for loss in losses]
    keys = sorted(set().union(*per_loss)) if per_loss else []
    if not per_loss or any(set(mapping) != set(keys) for mapping in per_loss):
        return None
    return {key: mean([mapping[key] for mapping in per_loss]) for key in keys}


def idle_scope_table(samples):
    losses = sorted({item["loss"] for item in samples})
    table = {"whole_trajectory_including_burnin": scope_interval(samples, lambda item: True),
             "by_loss": {f"{loss:g}": scope_interval(samples, lambda item, value=loss: item["loss"] == value)
                         for loss in losses},
             "by_one_rtt": {name: scope_interval(samples, lambda item, value=flag: item["one_rtt"] is value)
                            for name, flag in (("one_rtt", True), ("not_one_rtt", False))}}
    if len(losses) == 2:
        values = reweighted(samples, losses)
        if values is not None:
            table["post_burnin_reweighted_1_1"] = {**interval(list(values.values())),
                                                   "by_trajectory": {str(key): value for key, value in values.items()}}
    table["median_ms"] = pystat.median(item["idle_ms"] for item in samples) if samples else None
    return table


def difference(left, right):
    x, y = left["by_trajectory"], right["by_trajectory"]
    if set(x) != set(y) or not x:
        return None
    return interval([x[key] - y[key] for key in sorted(x)])


def idle_contrasts(plan, task, idle, cells):
    result = []
    for cell in cells:
        for contrast in plan["tasks"][task]["contrasts"]:
            left = idle.get((cell["id"], contrast["x"]))
            right = idle.get((cell["id"], contrast["y"]))
            if left is None or right is None:
                continue
            row = {"cell": cell["id"], "id": contrast["id"], "x": contrast["x"], "y": contrast["y"],
                   "whole_trajectory_including_burnin": difference(left["whole_trajectory_including_burnin"],
                                                                   right["whole_trajectory_including_burnin"])}
            for loss, value in left["by_loss"].items():
                row["loss_" + loss] = difference(value, right["by_loss"][loss])
            result.append(row)
    return result


def idle_judgments(plan, task, contrasts, cells):
    profiles = {cell["id"]: cell["profile"] for cell in cells}
    results = []
    for row in contrasts:
        x, y = plan["arms"][row["x"]], plan["arms"][row["y"]]
        if profiles[row["cell"]] != "bigcert" or not x.get("server_feedback") or y.get("server_feedback"):
            continue
        if y.get("kind") != "auto3" or y.get("binary") not in ("gen33",):
            continue
        whole = row["whole_trajectory_including_burnin"]
        results.append({"cell": row["cell"], "contrast": row["id"], "scope": "whole_trajectory_including_burnin",
                        "difference_ms": whole["mean"], "ci95": whole["ci95"], "threshold_ms": 5,
                        "within_threshold_approx": abs(whole["mean"]) <= 5,
                        "official_status": "미확인", "official_decision": "D79",
                        "note": "근사 값으로 본 참고 판정이다. 공식 판정을 대신하지 않는다"})
    return results


def idle_additional(plan, task, samples_by_group):
    result = []
    for cell in plan["tasks"][task].get("additional_cells", []):
        for name in ("comparator", "additional_comparator"):
            target = cell.get(name)
            if target is None:
                continue
            for arm_id in cell["arms"]:
                left = defaultdict(list)
                for item in samples_by_group[(cell["id"], arm_id)]:
                    left[(item["phase"], item["block"])].append(item["idle_ms"])
                right = defaultdict(list)
                for item in samples_by_group[(target["cell"], target["arm"])]:
                    if item["trajectory"] == target["trajectory"]:
                        right[(item["phase"], item["block"])].append(item["idle_ms"])
                keys = sorted(set(left) & set(right))
                result.append({"cell": cell["id"], "x": arm_id, "y": target["arm"],
                               "y_cell": target["cell"], "y_trajectory": target["trajectory"],
                               "inference_unit": "paired_block_within_one_trajectory",
                               "independent_trajectory_claim": False,
                               **interval([mean(left[key]) - mean(right[key]) for key in keys])})
    return result


def loss_row(sent, dropped, nominal, confidence):
    attempts = sent + dropped
    tail = (1 - confidence) / 2
    low, high = ([int(binom.ppf(tail, attempts, nominal / 100)), int(binom.ppf(1 - tail, attempts, nominal / 100))]
                 if attempts else [None, None])
    return {"sent": sent, "dropped": dropped, "attempts": attempts,
            "realized_rate": dropped / attempts if attempts else None, "nominal_pct": nominal,
            "prediction_interval_dropped": [low, high], "confidence": confidence,
            "inside_prediction_interval": low <= dropped <= high if attempts else None}


def tc_delta(before, after, direction):
    first = report_checks._tc_counts(before[direction])
    last = report_checks._tc_counts(after[direction])
    if any(end < start for start, end in zip(first, last)):
        raise ValueError("tc 계수가 단위 안에서 감소했다")
    return last[0] - first[0], last[1] - first[1]


def build(args):
    plan, plan_sha = devbed.read_plan(args.plan)
    result_bytes = Path(args.result).read_bytes()
    result = json.loads(result_bytes)
    task, run_id = result["task"], result["run_id"]
    if result["plan_sha256"] != plan_sha or result["label"] != "development" or result["confirmatory"] is not False:
        raise ValueError("결과의 계획 SHA 또는 표지가 입력과 다르다")
    raw_dir = Path(args.raw_dir).expanduser().resolve()
    journal_path = raw_dir / f"units_{run_id}.jsonl"
    manifest_path = raw_dir / f"manifest_{run_id}.json"
    hashes = artifact_hashes(args.artifacts)
    journal_sha = sha256_file(journal_path)
    if hashes.get(journal_path) != journal_sha:
        raise ValueError("저널 SHA가 결과 SHA 목록과 다르다")
    units = arms.iter_units(plan, [task])
    metas = journal_units(journal_path)
    if [unit["key"] for unit in units] != list(metas):
        raise ValueError("저널 단위가 계획 순서와 다르다")
    cells = cell_specs(plan, task)
    points = defaultdict(list)
    contexts = defaultdict(list)
    samples = defaultdict(list)
    excluded = []
    unusable = []
    rank_mismatch = 0
    last_samples = 0
    loss_cells = defaultdict(lambda: [0, 0])
    loss_groups = defaultdict(lambda: [0, 0])
    s2c_dropped = 0
    parse_events = []
    parse_sums = Counter()
    ips_counts = Counter()
    timing = defaultdict(list)
    hct_rows = defaultdict(list)
    state = defaultdict(lambda: {"actions": Counter(), "s_hat": [], "n_need": Counter()})
    confidence = plan["smoke_checks"]["realized_loss"]["confidence"]
    wall = []
    for unit in units:
        meta = metas[unit["key"]]
        raw = RawUnit(raw_dir, unit, meta)
        rows = raw.rows()
        arm = plan["arms"][unit["arm"]]
        identity = (unit["cell"], unit["arm"], unit["trajectory"])
        for row in rows:
            points[identity].append(point_row(unit, row))
            contexts[identity].append(context_row(row))
            burnin = row["i"] < unit["burnin_connections"]
            hct_rows[identity].append({"phase": unit["phase"], "block": unit["block"], "i": row["i"],
                                       "measured": not burnin, "ms": row["ms"] if row["ok"] else plan["statistics"]["failure_hct_ms"]})
            bucket = state[(unit["cell"], unit["arm"], "burnin" if burnin else "primary", unit["loss_c2s_pct"])]
            if isinstance(row.get("action"), list):
                bucket["actions"][",".join(map(str, row["action"]))] += 1
            if numeric(row.get("s_hat")):
                bucket["s_hat"].append(row["s_hat"])
            if numeric(row.get("n_need")):
                bucket["n_need"][str(row["n_need"])] += 1
            if numeric(row.get("ips_used")) and row["ips_used"] >= 1395:
                ips_counts[(unit["cell"], unit["arm"])] += 1
        conns = raw.conns()
        limit = (unit["profile"]["gap_ms"] + (unit["profile"]["feedback_wait_ms"] if arm.get("server_feedback") else 0)
                 + CLOCK_MARGIN_MS)
        unit_samples, problem, mismatch = idle_samples(unit, rows, conns)
        rank_mismatch += mismatch
        if problem is not None:
            unusable.append(problem)
        last_samples += 1
        for item in unit_samples:
            row = rows[item["i"]]
            if abs(item["idle_ms"]) > limit:
                excluded.append({"unit": unit["key"], "i": item["i"], "connection_index": unit["connection_offset"] + item["i"],
                                 "idle_ms": item["idle_ms"], "spacing_ms": item["spacing_ms"], "hct_ms": item["hct_ms"],
                                 "limit_ms": limit, "first_rx_utc": utc(item["first_rx_ns"]),
                                 "next_first_rx_utc": utc(item["next_first_rx_ns"]),
                                 "feedback_wait_ms": row.get("feedback_wait_ns", 0) / 1e6 if type(row.get("feedback_wait_ns")) is int else None,
                                 "reason": CLOCK_REASON})
                continue
            samples[(unit["cell"], unit["arm"])].append({
                "trajectory": unit["trajectory"], "phase": unit["phase"], "block": unit["block"],
                "loss": unit["loss_c2s_pct"], "measured": item["i"] >= unit["burnin_connections"],
                "one_rtt": arms.one_rtt(row, unit["profile"]), "idle_ms": item["idle_ms"]})
        before, after = raw.tc("tc_before.json"), raw.tc("tc_after.json")
        sent, dropped = tc_delta(before, after, "c2s")
        s2c_dropped += tc_delta(before, after, "s2c")[1]
        for store, key in ((loss_cells, (unit["cell"], unit["arm"], unit["trajectory"], unit["phase"], unit["loss_c2s_pct"])),
                           (loss_groups, (unit["cell"], unit["arm"], unit["loss_c2s_pct"]))):
            store[key][0] += sent
            store[key][1] += dropped
        stats = raw.stats()
        count = stats.get("fec_parse_fail")
        if type(count) is int:
            parse_sums[(unit["cell"], unit["arm"])] += count
            if count > 0:
                flagged = [{"i": row["i"], "ips_used": row["ips_used"], "m_used": row.get("m_used"), "ms": row["ms"],
                            "parity_sent": row.get("parity_sent"), "first_flight_parity_bytes": row.get("first_flight_parity_bytes")}
                           for row in rows if numeric(row.get("ips_used")) and row["ips_used"] >= 1395]
                parse_events.append({"unit": unit["key"], "arm": unit["arm"], "fec_parse_fail": count,
                                     "bytes_in": stats["bytes_in"], "conn_log_rx_bytes": sum(conn["rx_bytes"] for conn in conns),
                                     "rows_ips_used_ge_1395": flagged})
        begin = datetime.fromisoformat(meta["started_at"])
        end = datetime.fromisoformat(meta["ended_at"])
        wall.append((begin, end, unit["cell"], unit["key"]))
        timing[(unit["cell"], unit["arm"])].append((end - begin).total_seconds())
    series_trajectories = []
    identities = []
    for cell in cells:
        for arm_id in cell["arms"]:
            for trajectory in range(cell["trajectories"]):
                identity = (cell["id"], arm_id, trajectory)
                identities.append(identity)
                values = points[identity]
                if [item["connection_index"] for item in values] != list(range(len(values))):
                    raise ValueError("연결 번호가 끊겼다: " + str(identity))
                series_trajectories.append({"cell": cell["id"], "arm": arm_id, "trajectory": trajectory, "points": values,
                                            "context": {name: [row[name] for row in contexts[identity]] for name in CONTEXT_FIELDS}})
    result_sha = sha256_bytes(result_bytes)
    series = {"schema": SERIES_SCHEMA, "task": task, "run_id": run_id, "result_sha256": result_sha,
              "plan_sha256": plan_sha, "journal_sha256": journal_sha, "label": "development", "confirmatory": False,
              "context_fields": list(CONTEXT_FIELDS), "trajectories": series_trajectories}
    series_bytes = canonical(series)
    crosscheck = {"compared": 0, "mismatches": []}
    for cell_result in result["statistics"]["cells"]:
        for arm_result in cell_result["arms"]:
            items = [(identity, values) for identity, values in points.items()
                     if identity[0] == cell_result["cell"] and identity[1] == arm_result["arm"]]
            scopes = {"all": lambda point, burn: True,
                      "primary": lambda point, burn: point["connection_index"] >= burn,
                      "burnin": lambda point, burn: point["connection_index"] < burn}
            spec = next(cell for cell in cells if cell["id"] == cell_result["cell"])
            burn = spec["burnin_per_arm_trajectory"]
            for name, selector in scopes.items():
                chosen = [point["p_mean"] for identity, values in items for point in values
                          if selector(point, burn) and point["p_mean"] is not None]
                expected = arm_result[name]
                crosscheck["compared"] += 1
                same = (len(chosen) == expected["p_mean_samples"]
                        and (expected["p_mean"] is None and not chosen
                             or math.isclose(mean(chosen), expected["p_mean"], rel_tol=1e-12, abs_tol=1e-9)))
                if not same:
                    crosscheck["mismatches"].append({"cell": cell_result["cell"], "arm": arm_result["arm"], "scope": name})
    if crosscheck["mismatches"]:
        raise ValueError("시계열 평균이 결과 JSON과 다르다: " + json.dumps(crosscheck["mismatches"], ensure_ascii=False))
    p_summary = []
    for identity in identities:
        values = points[identity]
        present = sum(item["p_mean_present"] for item in values)
        valid = [item["p_mean"] for item in values if item["p_mean"] is not None]
        phases = {}
        for phase in sorted({item["phase"] for item in values}):
            selected = [item["p_mean"] for item in values if item["phase"] == phase and item["p_mean"] is not None]
            phases[str(phase)] = {"valid": len(selected), "mean": mean(selected), "last_30_mean": mean(selected[-30:])}
        p_summary.append({"cell": identity[0], "arm": identity[1], "trajectory": identity[2], "points": len(values),
                          "key_absent": len(values) - present, "present_null": present - len(valid),
                          "numeric": len(valid), "by_phase": phases,
                          "points_sha256": sha256_bytes(canonical(values))})
    identical = []
    for cell in cells:
        for arm_id in cell["arms"]:
            hashes_arm = [sha256_bytes(canonical([item["p_mean"] for item in points[(cell["id"], arm_id, trajectory)]]))
                          for trajectory in range(cell["trajectories"])]
            identical.append({"cell": cell["id"], "arm": arm_id, "p_mean_sequence_sha256": hashes_arm,
                              "all_trajectories_identical": len(set(hashes_arm)) == 1})
    idle_tables = {key: idle_scope_table(values) for key, values in samples.items()}
    contrasts = idle_contrasts(plan, task, idle_tables, cells)
    idle_section = {"kind": IDLE_KIND, "official": result["idle_check"], "limits": IDLE_LIMITS,
                    "exclusion_rule": {"margin_ms": CLOCK_MARGIN_MS, "reason": CLOCK_REASON},
                    "excluded_rows": excluded, "unusable_units": unusable, "scid_rank_mismatches": rank_mismatch,
                    "unit_last_connections_without_next": last_samples,
                    "arms": [{"cell": key[0], "arm": key[1], **value} for key, value in sorted(idle_tables.items())],
                    "contrasts": contrasts, "judgment_approx": idle_judgments(plan, task, contrasts, cells),
                    "additional": idle_additional(plan, task, samples)}
    realized = {"direction": "c2s", "source": "tc -s qdisc의 단위 전후 Sent와 dropped 증분",
                "confidence": confidence, "s2c_dropped_total": s2c_dropped,
                "note": "참고 표다. 예측구간 밖이어도 X6 검사가 아니다",
                "by_cell_arm_loss": [{"cell": key[0], "arm": key[1], **loss_row(value[0], value[1], key[2], confidence)}
                                     for key, value in sorted(loss_groups.items())],
                "by_trajectory_phase": [{"cell": key[0], "arm": key[1], "trajectory": key[2], "phase": key[3],
                                         **loss_row(value[0], value[1], key[4], confidence)}
                                        for key, value in sorted(loss_cells.items())]}
    summaries = {(row["cell"], row["arm"]): row for row in result["server_summary"]}
    parse_section = {"sum_by_cell_arm": [], "events": parse_events, "effects": []}
    for key, row in sorted(summaries.items()):
        value = parse_sums[key]
        if row.get("fec_parse_fail") is not None and row["fec_parse_fail"] != value:
            raise ValueError("fec_parse_fail 합이 결과 JSON과 다르다: " + str(key))
        parse_section["sum_by_cell_arm"].append({"cell": key[0], "arm": key[1], "fec_parse_fail": value,
                                                 "rows_ips_used_ge_1395": ips_counts[key]})
    for event in parse_events:
        parts = event["unit"].split(".")
        identity = (parts[1], parts[-1], int(parts[2][1:]))
        phase, block = int(parts[3][1:]), int(parts[4][1:])
        flagged = {row["i"] for row in event["rows_ips_used_ge_1395"]}
        measured = [row for row in hct_rows[identity] if row["measured"]]
        kept = [row for row in measured if not (row["phase"] == phase and row["block"] == block and row["i"] in flagged)]
        parse_section["effects"].append({"unit": event["unit"], "trajectory_primary_hct_ms": mean([row["ms"] for row in measured]),
                                         "without_flagged_rows_ms": mean([row["ms"] for row in kept]),
                                         "rows_removed": len(measured) - len(kept)})
    state_section = []
    for key, bucket in sorted(state.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3])):
        state_section.append({"cell": key[0], "arm": key[1], "scope": key[2], "loss_c2s_pct": key[3],
                              "action_hist": dict(sorted(bucket["actions"].items())),
                              "n_need_hist": dict(sorted(bucket["n_need"].items())),
                              "s_hat_median": pystat.median(bucket["s_hat"]) if bucket["s_hat"] else None,
                              "s_hat_samples": len(bucket["s_hat"])})
    wall.sort(key=lambda row: row[0])
    gaps = sorted((after[0] - before[1]).total_seconds() for before, after in zip(wall, wall[1:]))
    cell_runs = []
    for cell in cells:
        selected = [row for row in wall if row[2] == cell["id"]]
        cell_runs.append({"cell": cell["id"], "first_start": selected[0][0].isoformat(),
                          "last_end": max(row[1] for row in selected).isoformat(), "units": len(selected),
                          "wall_minutes": (max(row[1] for row in selected) - selected[0][0]).total_seconds() / 60})
    timing_section = {"source": "저널 payload started_at, ended_at",
                      "total_wall_minutes": (max(row[1] for row in wall) - wall[0][0]).total_seconds() / 60,
                      "between_units_seconds": {"median": pystat.median(gaps), "maximum": gaps[-1]},
                      "cells": cell_runs,
                      "arms": [{"cell": key[0], "arm": key[1], "units": len(values),
                                "unit_seconds_median": pystat.median(values), "unit_seconds_maximum": max(values),
                                "sum_minutes": math.fsum(values) / 60} for key, values in sorted(timing.items())]}
    diagnostics = {"schema": DIAGNOSTICS_SCHEMA, "task": task, "run_id": run_id, "label": "development", "confirmatory": False,
                   "provenance": {"result_sha256": result_sha, "plan_sha256": plan_sha, "journal_sha256": journal_sha,
                                  "manifest_sha256": sha256_file(manifest_path),
                                  "artifacts_manifest_sha256": sha256_file(args.artifacts),
                                  "series_sha256": sha256_bytes(series_bytes),
                                  "tool_sha256": sha256_file(__file__), "units": len(units),
                                  "client_rows": sum(len(values) for values in points.values())},
                   "p_mean": {"crosscheck_with_result": crosscheck, "summary": p_summary, "sequence_identity": identical},
                   "idle_approx": idle_section, "realized_loss": realized, "fec_parse_fail": parse_section,
                   "policy_state": state_section, "timing": timing_section}
    names = plan["result_contract"].get("document_names", {})
    return run_id, task, series_bytes, pretty(diagnostics), names.get(task, f"{task}_result.md").removesuffix("_result.md")


def render_document(diagnostics, series_name):
    source = diagnostics["provenance"]
    lines = [f"# {diagnostics['task']} 진단: p_mean 시계열, 유휴 근사, 실현 손실", "",
             f"실행 ID는 {diagnostics['run_id']}다. development 측정의 사후 진단이며 확증이 아니다. "
             "결과 JSON과 자동 결과 문서를 바꾸지 않는다.",
             f"결과 JSON SHA256 `{source['result_sha256']}`, 저널 SHA256 `{source['journal_sha256']}`, "
             f"시계열 SHA256 `{source['series_sha256']}`.", "",
             "## p_mean 시계열", "",
             f"연결별 값은 `g3/v33/results/{series_name}`에 있다. 원자료의 셀, 팔, 궤적, phase, 블록, 연결 순서를 그대로 두었다. "
             "키가 없으면 p_mean_present false, p_mean null이다. 0으로 채우지 않았다.", ""]
    grouped = defaultdict(lambda: [0, 0, 0, 0])
    for row in diagnostics["p_mean"]["summary"]:
        item = grouped[(row["cell"], row["arm"])]
        for index, name in enumerate(("points", "numeric", "key_absent", "present_null")):
            item[index] += row[name]
    _table(lines, ["셀", "팔", "행 수", "숫자", "키 부재", "null"],
           [(*key, *value) for key, value in sorted(grouped.items())])
    check = diagnostics["p_mean"]["crosscheck_with_result"]
    idle = diagnostics["idle_approx"]
    lines.extend([f"결과 JSON의 p_mean 평균·샘플 수와 {check['compared']}곳을 대조했고 불일치는 {len(check['mismatches'])}곳이다.", "",
                  "## 유휴 근사", "", idle["kind"] + ". "
                  f"공식 값은 상태 {idle['official']['status']}, 결정 {idle['official']['decision']}로 그대로 둔다. "
                  + " ".join(text + "." for text in idle["limits"]), ""])
    _table(lines, ["셀", "팔", "표본 행", "전체 평균(ms)", "95% 구간(ms)", "중앙값(ms)"],
           [(row["cell"], row["arm"], row["whole_trajectory_including_burnin"]["rows"],
             row["whole_trajectory_including_burnin"]["mean"], _interval(row["whole_trajectory_including_burnin"]["ci95"]),
             row["median_ms"]) for row in idle["arms"]])
    _table(lines, ["셀", "대조", "전체 차이(ms)", "95% 구간(ms)"],
           [(row["cell"], row["id"], row["whole_trajectory_including_burnin"]["mean"],
             _interval(row["whole_trajectory_including_burnin"]["ci95"])) for row in idle["contrasts"]])
    _table(lines, ["셀", "대조", "차이(ms)", "95% 구간(ms)", "5 ms 안(근사)", "공식 상태"],
           [(row["cell"], row["contrast"], row["difference_ms"], _interval(row["ci95"]), row["within_threshold_approx"],
             row["official_status"]) for row in idle["judgment_approx"]])
    lines.extend([f"근사 집계에서 뺀 행은 {len(idle['excluded_rows'])}개다. " + idle["exclusion_rule"]["reason"] + ".", ""])
    _table(lines, ["단위", "연결", "근사(ms)", "간격(ms)", "HCT(ms)", "first_rx UTC"],
           [(row["unit"], row["i"], row["idle_ms"], row["spacing_ms"], row["hct_ms"], row["first_rx_utc"])
            for row in idle["excluded_rows"]])
    realized = diagnostics["realized_loss"]
    lines.extend(["## 실현 손실", "", realized["source"] + ". " + realized["note"] + ".", ""])
    _table(lines, ["셀", "팔", "명목(%)", "시도 패킷", "드롭", "실현 비율", "예측구간 드롭", "구간 안"],
           [(row["cell"], row["arm"], row["nominal_pct"], row["attempts"], row["dropped"], row["realized_rate"],
             _interval(row["prediction_interval_dropped"]) if row["attempts"] else None, row["inside_prediction_interval"])
            for row in realized["by_cell_arm_loss"]])
    parse = diagnostics["fec_parse_fail"]
    lines.extend(["## fec_parse_fail", ""])
    _table(lines, ["셀", "팔", "서버 fec_parse_fail 합", "ips_used 1395 이상 행"],
           [(row["cell"], row["arm"], row["fec_parse_fail"], row["rows_ips_used_ge_1395"])
            for row in parse["sum_by_cell_arm"]])
    effects = {row["unit"]: row for row in parse["effects"]}
    _table(lines, ["단위", "계수", "bytes_in", "conn-log rx_bytes 합", "해당 행", "궤적 주 HCT(ms)", "해당 행 뺀 값(ms)"],
           [(row["unit"], row["fec_parse_fail"], row["bytes_in"], row["conn_log_rx_bytes"],
             ", ".join(f"i={item['i']} ips_used={item['ips_used']} HCT={item['ms']}" for item in row["rows_ips_used_ge_1395"]),
             effects[row["unit"]]["trajectory_primary_hct_ms"], effects[row["unit"]]["without_flagged_rows_ms"])
            for row in parse["events"]])
    lines.extend(["## 정책 상태", ""])
    _table(lines, ["셀", "팔", "범위", "손실(%)", "행동 분포", "n_need 분포", "s_hat 중앙값"],
           [(row["cell"], row["arm"], row["scope"], row["loss_c2s_pct"], json.dumps(row["action_hist"], sort_keys=True),
             json.dumps(row["n_need_hist"], sort_keys=True), row["s_hat_median"]) for row in diagnostics["policy_state"]])
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="X6 계열 결과의 p_mean 시계열과 진단 산출")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_id, task, series, diagnostics, document_stem = build(args)
        series_name = f"v33_dev_{task}_{run_id}.p_mean_series.json"
        document = render_document(json.loads(diagnostics), series_name).encode("utf-8")
        outputs = {args.out_dir / series_name: series,
                   args.out_dir / f"v33_dev_{task}_{run_id}.diagnostics.json": diagnostics,
                   args.docs_dir / f"{document_stem}_diagnostics.md": document}
        if args.check:
            for path, content in outputs.items():
                if path.read_bytes() != content:
                    raise ValueError("기존 산출물과 바이트가 다르다: " + str(path))
        else:
            for path, content in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(content)
        print(json.dumps({"status": "pass", "check": args.check,
                          "outputs": {str(path): sha256_bytes(content) for path, content in outputs.items()}},
                         ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
