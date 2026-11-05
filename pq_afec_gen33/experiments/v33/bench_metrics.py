import collections
import math
import statistics


def _finite(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _positive_integer(name, value, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _beta_fraction(a, b, x):
    floor = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < floor:
        d = floor
    d = 1.0 / d
    result = d
    for m in range(1, 501):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + aa / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        result *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + aa / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= 3e-14:
            return result
    raise ArithmeticError("incomplete beta fraction did not converge")


def _regularized_beta(x, a, b):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def student_t_critical(df, confidence=0.95):
    _positive_integer("df", df)
    confidence = _finite("confidence", confidence)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    target = 1.0 - confidence
    low, high = 0.0, 1.0
    while _regularized_beta(df / (df + high * high), df / 2.0, 0.5) > target:
        high *= 2.0
        if not math.isfinite(high):
            raise ArithmeticError("Student t quantile could not be bracketed")
    for _ in range(100):
        mid = (low + high) / 2.0
        if _regularized_beta(df / (df + mid * mid), df / 2.0, 0.5) > target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def paired_summary(values, confidence=0.95):
    confidence = _finite("confidence", confidence)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between zero and one")
    values = [_finite("paired value", value) for value in values]
    n = len(values)
    result = {"n": n, "mean": statistics.mean(values) if n else None,
              "sd": None, "se": None, "lower": None, "upper": None,
              "half_width": None, "confidence": confidence, "df": n - 1 if n else None,
              "method": "two-sided Student t on independent seed differences",
              "interval_available": n >= 2}
    if n < 2:
        return result
    result["sd"] = statistics.stdev(values)
    result["se"] = result["sd"] / math.sqrt(n)
    result["critical"] = student_t_critical(n - 1, confidence)
    result["half_width"] = result["critical"] * result["se"]
    result["lower"] = result["mean"] - result["half_width"]
    result["upper"] = result["mean"] + result["half_width"]
    return result


def evaluate_threshold(estimate, lower, upper, threshold, *, mc_bound=0.0,
                       selection_gap=0.0, inclusive=False, absolute=False):
    estimate = None if estimate is None else _finite("estimate", estimate)
    lower = None if lower is None else _finite("lower", lower)
    upper = None if upper is None else _finite("upper", upper)
    threshold = _finite("threshold", threshold)
    mc_bound = None if mc_bound is None else _finite("mc_bound", mc_bound)
    selection_gap = None if selection_gap is None else _finite("selection_gap", selection_gap)
    if any(value is not None and value < 0 for value in (mc_bound, selection_gap)):
        raise ValueError("uncertainty bounds must be nonnegative")
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("lower exceeds upper")
    if type(inclusive) is not bool or type(absolute) is not bool:
        raise ValueError("inclusive and absolute must be boolean")
    adjusted_lower = lower - mc_bound if lower is not None and mc_bound is not None else None
    adjusted_upper = upper + mc_bound + selection_gap if upper is not None and mc_bound is not None and selection_gap is not None else None
    if absolute:
        if adjusted_lower is None or adjusted_upper is None:
            adjusted_lower, adjusted_upper = None, None
        else:
            a, b = adjusted_lower, adjusted_upper
            adjusted_lower = 0.0 if a <= 0 <= b else min(abs(a), abs(b))
            adjusted_upper = max(abs(a), abs(b))
    point = abs(estimate) if absolute and estimate is not None else estimate
    point_pass = None if point is None else (point <= threshold if inclusive else point < threshold)
    passed = adjusted_upper is not None and (adjusted_upper <= threshold if inclusive else adjusted_upper < threshold)
    failed = adjusted_lower is not None and (adjusted_lower > threshold if inclusive else adjusted_lower >= threshold)
    status = "pass" if passed else "fail" if failed else "inconclusive"
    return {"status": status, "estimate": estimate, "point_pass": point_pass,
            "lower": lower, "upper": upper, "adjusted_lower": adjusted_lower,
            "adjusted_upper": adjusted_upper, "threshold": threshold,
            "inclusive": inclusive, "absolute": absolute,
            "mc_bound": mc_bound, "selection_gap": selection_gap}


def _row_order(rows):
    for position, row in enumerate(rows):
        if row.get("index") != position or type(row.get("index")) is not int:
            raise ValueError("rows must have contiguous zero-based index values")


def _first_consecutive(rows, predicate, consecutive):
    length = 0
    start = None
    unknown = 0
    for row in rows:
        value = predicate(row)
        if value is not None and type(value) is not bool:
            raise ValueError("predicate must return bool or None")
        if value is None:
            unknown += 1
        if value:
            if not length:
                start = row["index"]
            length += 1
            if length == consecutive:
                return start, row["index"], unknown
        else:
            length = 0
            start = None
    return None, None, unknown


def adaptation(rows, near_optimal, changes, consecutive=2):
    rows = list(rows)
    _row_order(rows)
    _positive_integer("consecutive", consecutive)
    changes = list(changes)
    for value in changes:
        _positive_integer("change", value, minimum=0)
        if value >= len(rows):
            raise ValueError("change is outside the observed run")
    if changes != sorted(set(changes)):
        raise ValueError("changes must be unique and increasing")
    result = []
    for position, change in enumerate(changes):
        end = changes[position + 1] if position + 1 < len(changes) else len(rows)
        start, confirmed, unknown = _first_consecutive(rows[change:end], near_optimal, consecutive)
        result.append({"change_index": change, "end_index_exclusive": end,
                       "start_index": start, "confirmed_index": confirmed,
                       "start_new_observations": None if start is None else start - change,
                       "confirmed_new_observations": None if confirmed is None else confirmed - change,
                       "censored": start is None, "followup_decisions": end - change,
                       "unknown_predicate_rows_before_confirmation": unknown,
                       "consecutive": consecutive,
                       "status": "adapted" if start is not None else "unresolved" if unknown else "right_censored"})
    return result


def _phase_groups(rows):
    groups = []
    for row in rows:
        phase = row["phase"]
        _positive_integer("phase", phase, minimum=0)
        _positive_integer("phase_index", row["phase_index"], minimum=0)
        p = _finite("phase_p", row["phase_p"])
        if not 0 <= p <= 1:
            raise ValueError("phase_p must be a probability")
        if not groups or groups[-1][0]["phase"] != phase:
            if groups and phase <= groups[-1][0]["phase"]:
                raise ValueError("phases must increase")
            groups.append([])
        group = groups[-1]
        if row["phase_index"] != len(group):
            raise ValueError("phase_index must be contiguous and zero based")
        if group and group[0]["phase_p"] != p:
            raise ValueError("phase_p changed within a phase")
        group.append(row)
    return groups


def _transitions(groups, consecutive):
    result = []
    for before, after in zip(groups, groups[1:]):
        old_p, new_p = before[0]["phase_p"], after[0]["phase_p"]
        if old_p == new_p:
            continue
        midpoint = (old_p + new_p) / 2.0
        direction = 1 if new_p > old_p else -1

        def new_side(row):
            value = row.get("p_mean_pre")
            return None if value is None else direction * (_finite("p_mean_pre", value) - midpoint) > 0

        prior = before[-consecutive:]
        ready = len(prior) == consecutive and all(row.get("p_mean_pre") is not None and direction * (_finite("p_mean_pre", row["p_mean_pre"]) - midpoint) < 0 for row in prior)
        already = len(prior) == consecutive and all(new_side(row) is True for row in prior)
        start, confirmed, unknown = _first_consecutive(after, new_side, consecutive)
        change = after[0]["index"]
        detection = start if ready else None
        result.append({"from_phase": before[0]["phase"], "to_phase": after[0]["phase"],
                       "change_index": change, "old_p": old_p, "new_p": new_p,
                       "midpoint": midpoint, "direction": "up" if direction == 1 else "down",
                       "consecutive": consecutive, "prechange_old_side_qualified": ready,
                       "already_on_new_side": already,
                       "tracking_start_index": start, "tracking_confirmed_index": confirmed,
                       "tracking_delay": None if start is None else start - change,
                       "tracking_confirmed_delay": None if confirmed is None else confirmed - change,
                       "tracking_censored": start is None,
                       "detection_delay": None if detection is None else detection - change,
                       "detection_confirmed_delay": None if detection is None else confirmed - change,
                       "detection_censored": ready and detection is None,
                       "detection_status": "detected" if detection is not None else "right_censored" if ready else "already_on_new_side" if already else "prechange_unsettled",
                       "followup_decisions": len(after),
                       "unknown_p_rows_before_confirmation": unknown})
    return result


def summarize_run(rows, scenario, protocol):
    rows = list(rows)
    _row_order(rows)
    metrics = protocol.get("metrics", {})
    high_last = _positive_integer("p_bias_high_phase_last_n", metrics.get("p_bias_high_phase_last_n", 200))
    cold = _positive_integer("cold_alarm_exclusion", metrics.get("cold_alarm_exclusion", 100), minimum=0)
    transition = _positive_integer("transition_alarm_exclusion", metrics.get("transition_alarm_exclusion", 100), minimum=0)
    consecutive = _positive_integer("delay_consecutive", metrics.get("delay_consecutive", 5))
    groups = _phase_groups(rows)
    highest = max((row["phase_p"] for row in rows), default=None)
    phase_summaries = []
    high_errors = []
    for group in groups:
        errors = [_finite("p_mean_pre", row["p_mean_pre"]) - row["phase_p"] for row in group[-high_last:] if row.get("p_mean_pre") is not None]
        if group[0]["phase_p"] == highest:
            high_errors.extend(errors)
        phase_summaries.append({"phase": group[0]["phase"], "p": group[0]["phase_p"], "n": len(group),
                                "tail_requested_n": high_last, "tail_observed_n": min(high_last, len(group)),
                                "tail_p_n": len(errors), "tail_p_bias": statistics.mean(errors) if errors else None,
                                "tail_p_mae": statistics.mean(map(abs, errors)) if errors else None})
    eligible = []
    first_phase = groups[0][0]["phase"] if groups else None
    for row in rows:
        if type(row["ok"]) is not bool:
            raise ValueError("ok must be boolean")
        if scenario.get("reset_each_connection", False) and cold > 0:
            continue
        if row["index"] < cold:
            continue
        if row["phase"] != first_phase and row["phase_index"] < transition:
            continue
        eligible.append(row)
    alarms = []
    for row in eligible:
        values = row.get("alarm_raised", [])
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("alarm_raised must be a list of action keys")
        alarms.append(len(set(values)))
    longest = current = 0
    previous = None
    for row in rows:
        action = row["action"]
        if not isinstance(action, (list, tuple)) or len(action) != 3 or any(type(value) is not int or value < 0 for value in action):
            raise ValueError("action must have three nonnegative integers")
        action = tuple(action)
        current = current + 1 if action == previous else 1
        longest = max(longest, current)
        previous = action

    def mean_field(name, optional=False):
        values = [_finite(name, row[name]) for row in rows if name in row and row[name] is not None]
        if not optional and len(values) != len(rows):
            raise ValueError(f"missing {name}")
        return statistics.mean(values) if values else None

    failures = sum(not row["ok"] for row in rows)
    count = len(rows)
    return {"n": count, "mean_hct_ms": mean_field("hct_ms"),
            "failure_count": failures, "failure_rate": failures / count if count else None,
            "mean_extra_server_bytes": mean_field("extra_server_bytes"),
            "mean_extra_first_flight_bytes": mean_field("extra_first_flight_bytes"),
            "mean_extra_client_first_flight_bytes": mean_field("extra_client_first_flight_bytes", optional=True),
            "extra_client_first_flight_observed_n": sum(row.get("extra_client_first_flight_bytes") is not None for row in rows),
            "p_bias_high_phase": statistics.mean(high_errors) if high_errors else None,
            "p_mae_high_phase": statistics.mean(map(abs, high_errors)) if high_errors else None,
            "p_bias_high_phase_n": len(high_errors), "high_phase_p": highest,
            "phase_summaries": phase_summaries,
            "alarm_episode_count": sum(alarms), "alarm_connections": sum(value > 0 for value in alarms),
            "alarm_eligible_connections": len(eligible),
            "alarm_rate_per_1000": 1000 * sum(alarms) / len(eligible) if eligible else None,
            "alarm_interpretation": "new action alarms per eligible 1000 connections without regime change; not causal loss false alarms",
            "guard_alarm_fraction": sum(bool(row.get("guard_alarm")) for row in rows) / count if count else None,
            "longest_unchanged_action_run": longest,
            "transitions": _transitions(groups, consecutive),
            "reeval_count": sum(bool(row.get("reeval")) for row in rows),
            "updated_count": sum(bool(row.get("updated")) for row in rows),
            "decision_why_counts": dict(collections.Counter(str(row.get("decision_why")) for row in rows)),
            "observation_skip_counts": dict(collections.Counter(str(row.get("observation_skip")) for row in rows)),
            "expected_regret_status": "not_evaluated",
            "metric_scope": "observed run; unchanged actions are not an oracle-defined stuck episode"}
