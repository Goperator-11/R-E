from collections import defaultdict
from datetime import datetime
import math

from . import arms


IDLE_UNAVAILABLE = "클라이언트 행에 절대 연결 시작 시각이 없어 실제 유휴를 계산할 수 없다"


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _mean(values):
    return math.fsum(values) / len(values) if values else None


def _check(values):
    if any(value is None for value in values):
        return "missing"
    return "pass" if values and all(values) else "fail"


def _feedback(rows, enabled, rule):
    total = len(rows)
    received = sum(row["feedback_received"] is True for row in rows)
    missing = sum(row["feedback_received"] is None for row in rows) if enabled else total
    rate = received / total if total and not missing else None
    enough = total >= rule["min_rows"]
    if not enabled:
        status = "해당 없음"
    elif missing:
        status = "미확인"
    elif not enough:
        status = "표본 부족"
    else:
        status = "pass" if rate >= rule["received_rate_min"] else "fail"
    return {"n": total, "received": received, "missing": missing, "rate": rate,
            "minimum_rows_met": enough, "status": status}


def _summary(plan, rows, enabled):
    rule = plan["collection"]["c1_by_class"]
    classes = {}
    for name, value in (("one_rtt", True), ("not_one_rtt", False)):
        classes[name] = _feedback([row for row in rows if row["one_rtt"] is value], enabled, rule)
    missing_rtt = sum(row["path_rtt_valid"] is None for row in rows)
    valid = sum(row["path_rtt_valid"] is True for row in rows)
    valid_rate = valid / len(rows) if rows and not missing_rtt else None
    wait_values = [row["feedback_wait_ms"] for row in rows if row["feedback_wait_ms"] is not None]
    wait_limits = sorted({row["feedback_wait_limit_ms"] for row in rows
                          if row["feedback_wait_limit_ms"] is not None})
    gaps = [row["wait_plus_gap_ms"] for row in rows if row["wait_plus_gap_ms"] is not None]
    excluded_classes = [name for name, item in classes.items()
                        if enabled and item["status"] in ("fail", "미확인")]
    feedback = _feedback(rows, enabled, rule)
    return {"n_rows": len(rows), "feedback_received_rate": feedback["rate"],
            "feedback_received": feedback,
            "feedback_received_rate_by_class": classes,
            "c1_path_excluded": bool(excluded_classes),
            "c1_path_exclusion_classes": excluded_classes,
            "c1_path_exclusion_reason": rule["failure_action"] if excluded_classes else None,
            "valid_rtt": {"valid": valid, "total": len(rows), "missing": missing_rtt,
                          "valid_rtt_rate": valid_rate,
                          "warning": valid_rate is not None
                          and valid_rate < plan["collection"]["valid_rtt_warning_below"]},
            "mean_idle_ms": None, "idle_valid_samples": 0,
            "idle_missing_samples": sum(row["has_next_in_unit"] for row in rows),
            "idle_status": "미확인", "idle_reason": IDLE_UNAVAILABLE,
            "mean_feedback_wait_ms": _mean(wait_values),
            "feedback_wait_samples": len(wait_values),
            "feedback_wait_limit_ms": wait_limits[0] if len(wait_limits) == 1 else None,
            "feedback_wait_limit_ms_values": wait_limits,
            "mean_wait_plus_gap_ms": _mean(gaps), "wait_plus_gap_samples": len(gaps),
            "wait_plus_gap_kind": "실제 feedback 대기와 설정 gap의 합, 실제 유휴 아님"}


def unit_observations(plan, unit, payload):
    arm = plan["arms"][unit["arm"]]
    gen33 = arms.client_family(plan, arm) == "gen33"
    enabled = arm.get("server_feedback", False)
    rows = payload["rows"]
    indices = [row.get("i") for row in rows]
    if (len(rows) != unit["rows_expected"] or any(type(index) is not int for index in indices)
            or set(indices) != set(range(unit["rows_expected"]))):
        raise ValueError("관측 행 수 또는 연결 순번이 계획과 다르다")
    profile = unit["profile"]
    samples = []
    flight_checks = []
    wait_checks = []
    receipt_checks = []
    for row in sorted(rows, key=lambda value: value["i"]):
        if type(row.get("ok")) is not bool or not _number(row.get("ms")):
            raise ValueError("관측 행의 성공 여부 또는 HCT가 유효하지 않다")
        if gen33:
            expectation = row.get("flight_expectation")
            flight_checks.append(None if not isinstance(expectation, dict)
                                 else expectation.get("source") == "explicit"
                                 and type(expectation.get("k")) is int
                                 and expectation["k"] == profile["expect_k"])
        received = row.get("feedback_wait_received")
        received = received if type(received) is bool else None
        limit = row.get("feedback_wait_limit_ms")
        limit = limit if _number(limit) else None
        if enabled:
            wait_checks.append(None if limit is None else limit == profile["feedback_wait_ms"])
            receipt_checks.append(None if received is None else True)
        wait_ns = row.get("feedback_wait_ns")
        wait_ms = wait_ns / 1_000_000 if type(wait_ns) is int and wait_ns >= 0 else None
        rtt_valid = row.get("path_rtt_valid")
        rtt_valid = rtt_valid if type(rtt_valid) is bool else None
        index = row["i"]
        has_next = index + 1 < unit["rows_expected"]
        samples.append({"i": index, "connection_index": unit["connection_offset"] + index,
                        "one_rtt": arms.one_rtt(row, profile), "feedback_received": received,
                        "feedback_wait_ms": wait_ms, "feedback_wait_limit_ms": limit,
                        "path_rtt_valid": rtt_valid,
                        "loss_c2s_pct": unit["loss_c2s_pct"], "loss_s2c_pct": unit["loss_s2c_pct"],
                        "burnin": index < unit["burnin_connections"],
                        "warmup": index < unit["warmup_connections"],
                        "measured": index >= unit["burnin_connections"] + unit["warmup_connections"],
                        "has_next_in_unit": has_next, "idle_ms": None,
                        "wait_plus_gap_ms": wait_ms + profile["gap_ms"]
                        if has_next and wait_ms is not None else None})
    checks = {}
    if gen33:
        checks["explicit_flight"] = _check(flight_checks)
    if enabled:
        checks["feedback_wait_limit"] = _check(wait_checks)
        checks["feedback_received_field"] = _check(receipt_checks)
    identity = {name: unit[name] for name in ("key", "task", "cell", "trajectory", "phase",
                                             "block", "block_across_phases", "arm", "profile_id")}
    return {"unit": identity, "checks": checks, "row_observations": samples,
            "summary": _summary(plan, samples, enabled), "feedback_enabled": enabled,
            "started_at": payload.get("started_at"), "ended_at": payload.get("ended_at")}


def _partition(plan, rows, enabled, field, values):
    return {name: _summary(plan, [row for row in rows if row[field] == value], enabled)
            for name, value in values}


def _loss_groups(plan, rows, enabled):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["loss_c2s_pct"], row["loss_s2c_pct"])].append(row)
    return [{"loss_c2s_pct": key[0], "loss_s2c_pct": key[1],
             **_summary(plan, groups[key], enabled)} for key in sorted(groups)]


def _boundaries(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item["unit"]["trajectory"]].append(item)
    result = []
    for trajectory, entries in sorted(grouped.items()):
        entries.sort(key=lambda item: (item["unit"]["phase"], item["unit"]["block"]))
        for before, after in zip(entries, entries[1:]):
            elapsed = None
            try:
                end = datetime.fromisoformat(before["ended_at"])
                start = datetime.fromisoformat(after["started_at"])
                if start.tzinfo is not None and end.tzinfo is not None:
                    difference = (start - end).total_seconds() * 1000
                    elapsed = difference if difference >= 0 else None
            except (ValueError, TypeError):
                pass
            result.append({"trajectory": trajectory, "previous_unit": before["unit"]["key"],
                           "next_unit": after["unit"]["key"], "elapsed_ms": elapsed})
    return {"samples": result, "mean_elapsed_ms": _mean([item["elapsed_ms"] for item in result
                                                         if item["elapsed_ms"] is not None]),
            "kind": "앞 단위 종료부터 다음 단위 시작까지, 다른 팔 실행과 재시작 포함"}


def summarize_observations(plan, unit_results):
    groups = defaultdict(list)
    seen = set()
    for result in unit_results:
        unit = result["unit"]
        if unit["key"] in seen:
            raise ValueError("중복 단위 관측")
        seen.add(unit["key"])
        groups[(unit["task"], unit["cell"], unit["arm"])].append(result)
    summaries = []
    for key, items in sorted(groups.items()):
        items.sort(key=lambda item: (item["unit"]["trajectory"], item["unit"]["phase"], item["unit"]["block"]))
        enabled = plan["arms"][key[2]].get("server_feedback", False)
        if any(item["feedback_enabled"] != enabled for item in items):
            raise ValueError("단위 관측의 C1 설정이 계획과 다르다")
        rows = [row for item in items for row in item["row_observations"]]
        summary = {"task": key[0], "cell": key[1], "arm": key[2],
                   **_summary(plan, rows, enabled), "by_loss": _loss_groups(plan, rows, enabled),
                   "by_one_rtt": _partition(plan, rows, enabled, "one_rtt",
                                            (("one_rtt", True), ("not_one_rtt", False))),
                   "by_trajectory": [], "unit_boundaries": _boundaries(items)}
        for trajectory in sorted({item["unit"]["trajectory"] for item in items}):
            selected = [row for item in items if item["unit"]["trajectory"] == trajectory
                        for row in item["row_observations"]]
            summary["by_trajectory"].append({"trajectory": trajectory,
                                              **_summary(plan, selected, enabled)})
        measured = [row for row in rows if row["measured"]]
        summary["post_burnin"] = _summary(plan, measured, enabled)
        summary["post_burnin"]["by_loss"] = _loss_groups(plan, measured, enabled)
        summary["post_burnin"]["reweighted_1_1_mean_idle_ms"] = None
        summary["burnin"] = _summary(plan, [row for row in rows if row["burnin"]], enabled)
        summaries.append(summary)
    return summaries
