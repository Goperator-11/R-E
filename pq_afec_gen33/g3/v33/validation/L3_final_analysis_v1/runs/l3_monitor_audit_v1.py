import collections
import gzip
import json
import math


COUNT_FIELDS = ("connections", "monitored", "skipped", "ready", "alarms", "up", "down", "action_model", "recovery", "shared_change", "failed_monitored", "reeval_suppressed", "nonzero_beta_decisions")
CONFIGS = {"l3": (True, True, True, False), "guard": (False, False, False, True),
           "record": (True, False, False, False), "beta": (True, True, False, False)}


def close(audit, label, actual, expected):
    if type(expected) is dict:
        audit.equal(label + ":keys", sorted(actual), sorted(expected))
        for key in expected:
            close(audit, label + ":" + key, actual[key], expected[key])
    elif type(expected) is list:
        audit.equal(label + ":length", len(actual), len(expected))
        for index, value in enumerate(expected):
            close(audit, label + ":" + str(index), actual[index], value)
    elif type(expected) is float:
        audit.check(label, type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-11))
    else:
        audit.equal(label, actual, expected)


def score(window, beta):
    odds = math.exp(beta)
    return -4 * beta + math.fsum(z - min(1 - 1e-6, max(1e-6, q)) * odds /
        (1 - min(1 - 1e-6, max(1e-6, q)) + min(1 - 1e-6, max(1e-6, q)) * odds) for q, z in window)


def fitted(audit, label, window, beta):
    edge = math.log(4)
    audit.check(label + ":bounded", math.isfinite(beta) and -edge <= beta <= edge)
    gradient = score(window, beta)
    good = gradient >= -1e-7 if beta == edge else gradient <= 1e-7 if beta == -edge else abs(gradient) <= 1e-7
    audit.check(label + ":optimal", good)


def initial():
    return {"arrival_streak": 0, "monitor": {"v": 1, "arms": {}, "shared_at": 0, "shared_count": 0}}


def advance(audit, row, index, role, state):
    enabled, apply_beta, apply_shared, reeval = CONFIGS[role]
    tag = str(index)
    info, decision = row["observation_info"], row["decision"]
    prediction = decision["monitor_prediction"]
    audit.equal(tag + ":snapshot", info["monitor_prediction"], prediction)
    audit.equal(tag + ":identity", [prediction["v"], prediction["dec_index"], prediction["obs_index"], prediction["action"], prediction["ready"]],
                [1, index + 1, index, row["action"], state["arrival_streak"] >= 8])
    audit.equal(tag + ":mode", decision["monitor_mode"], {"enabled": enabled, "beta": apply_beta, "shared": apply_shared})
    audit.equal(tag + ":reeval", decision["reeval_feedback_suppressed"], state["arrival_streak"] > 0 and not reeval)
    evidence = row["policy_observe_input"]["optional"]["first_flight_evidence"]
    complete = evidence["src"] != "none" and evidence["sent"] > 0 and not evidence["trunc"]
    state["arrival_streak"] = min(8, state["arrival_streak"] + 1) if complete else 0
    audit.equal(tag + ":arrival", [info["arrival_usable"], info["arrival_streak_after"]], [complete, state["arrival_streak"]])
    audit.equal(tag + ":fixed_loss", [info["epsilon_before"], info["epsilon_after"], info["epsilon_update_eligible"], info["cutoff_rtt_source"]],
                [.001, .001, False, "observation_rtt_current_policy"])
    monitor = state["monitor"]
    key = ",".join(map(str, row["action"]))
    previous = monitor["arms"].get(key)
    beta = 0.0 if previous is None else previous["beta"]
    close(audit, tag + ":beta_before", prediction["beta"], beta)
    raw, used = prediction["q_raw"], prediction["q_used"]
    if prediction["ctx"] is not None:
        audit.equal(tag + ":decision_rtt", prediction["ctx"]["rtt"], row["policy_decide_input"]["rtt_ms"])
        audit.check(tag + ":probabilities", len(raw) == 3 and all(type(q) in (int, float) and math.isfinite(q) and 0 <= q <= 1 for q in raw))
        close(audit, tag + ":probability_sum", sum(raw), 1.0)
        event = min(1.0, sum(raw[1:]))
        changed = list(raw)
        if beta and event not in (0, 1):
            target = event * math.exp(beta) / (1 - event + event * math.exp(beta))
            changed = [1 - target, raw[1] * target / event, raw[2] * target / event]
        close(audit, tag + ":probability_tilt", used, changed)
    else:
        audit.equal(tag + ":cold", [raw, used, prediction["cutoffs"]], [None, None, None])
    reason = "disabled" if not enabled else "no_ctx" if prediction["ctx"] is None else None
    audit.equal(tag + ":reason", info["monitor_reason"], reason)
    if reason is not None:
        audit.equal(tag + ":inactive", [info["monitor"], info["raised"]], [None, []])
        return
    current = previous if previous is not None else {"up": 0.0, "down": 0.0, "beta": 0.0, "n": 0, "last_seen": 0,
        "window": [], "alarm_at": 0, "alarm_dir": 0, "beta_before": 0.0, "reactive_alarm": False}
    grade = 2 if not row["ok"] else 0 if row["hct_ms"] < prediction["cutoffs"][0] else 1 if row["hct_ms"] < prediction["cutoffs"][1] else 2
    z = int(grade != 0)
    result = info["monitor"]
    q = min(1 - 1e-6, max(1e-6, min(1.0, sum(used[1:]))))
    base_q = min(1.0, sum(raw[1:]))
    up = max(0, current["up"] + math.log((2 if z else 1) / (1 + q)))
    down = max(0, current["down"] + math.log((.5 if z else 1) / (1 - .5 * q)))
    direction = 1 if up >= 5 else -1 if down >= 5 else 0
    reactive = prediction["ready"] and complete
    audit.equal(tag + ":event", [info["monitor_grade"], result["z"], result["direction"], result["reactive"], info["raised"]],
                [grade, z, direction, reactive, [key] if direction else []])
    close(audit, tag + ":predictive_input", [result[k] for k in ("q_raw", "q_used", "q_clamped", "beta_before")],
          [base_q, min(1.0, sum(used[1:])), q, beta])
    current.update(up=0.0 if direction else float(up), down=0.0 if direction else float(down), last_seen=index + 1,
                   n=current["n"] + 1, window=(current["window"] + [[base_q, z]])[-32:])
    expected_action = "record"
    if direction:
        current.update(alarm_at=index + 1, alarm_dir=direction, beta_before=beta, reactive_alarm=reactive)
        if reactive and apply_beta:
            expected_action = "action_model"
    monitor["arms"][key] = current
    active = {arm: value for arm, value in monitor["arms"].items() if index + 1 - value["last_seen"] < 32}
    shared = bool(direction and reactive and apply_shared and len(active) >= 2 and all(
        value["reactive_alarm"] and value["alarm_dir"] == direction and monitor["shared_at"] < value["alarm_at"]
        and index + 1 - value["alarm_at"] < 32 for value in active.values()))
    audit.equal(tag + ":shared", [result["shared"], result["shared_actions"]], [shared, sorted(active) if shared else []])
    if shared:
        for value in active.values():
            value.update(beta=value["beta_before"], up=0.0, down=0.0, reactive_alarm=False)
        monitor.update(shared_at=index + 1, shared_count=monitor["shared_count"] + 1)
        expected_action = "shared_change"
    elif expected_action == "action_model":
        fitted(audit, tag, current["window"], result["beta_after"])
        current["beta"] = result["beta_after"]
    elif not direction and reactive and apply_beta and ((beta > 0 and up == 0) or (beta < 0 and down == 0)):
        after = result["beta_after"]
        audit.check(tag + ":recovery_bound", min(0, beta) <= after <= max(0, beta))
        if after == 0:
            audit.check(tag + ":recovery_zero", score(current["window"], 0) * beta <= 1e-7)
        elif after == beta:
            audit.check(tag + ":recovery_fixed", score(current["window"], beta) * beta >= -1e-7)
        else:
            fitted(audit, tag, current["window"], after)
        current["beta"] = after
        expected_action = "recovery" if after != beta else "record"
    close(audit, tag + ":result", [result[k] for k in ("beta_after", "up", "down")], [current[k] for k in ("beta", "up", "down")])
    audit.equal(tag + ":count_action", [result["observations"], result["action"]], [current["n"], expected_action])


def monitor_seed(audit, run):
    counts = dict.fromkeys(COUNT_FIELDS, 0)
    reasons, actions = collections.Counter(), collections.Counter()
    beta = []
    state = initial()
    with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            row = json.loads(line)
            if run["scenario"] == "B9":
                state = initial()
            advance(audit, row, 0 if run["scenario"] == "B9" else index, run["analysis_role"], state)
            counts["connections"] += 1
            info, decision = row["observation_info"], row["decision"]
            value = decision["monitor_prediction"]["beta"]
            beta.append(value)
            counts["nonzero_beta_decisions"] += int(value != 0)
            counts["reeval_suppressed"] += int(decision["reeval_feedback_suppressed"])
            result = info["monitor"]
            if result is None:
                counts["skipped"] += 1
                reasons[info["monitor_reason"]] += 1
            else:
                counts["monitored"] += 1
                counts["failed_monitored"] += int(not row["ok"])
                counts["ready"] += int(result["reactive"])
                counts["alarms"] += int(result["direction"] != 0)
                counts["up"] += int(result["direction"] > 0)
                counts["down"] += int(result["direction"] < 0)
                actions[result["action"]] += 1
                if result["action"] in ("action_model", "recovery", "shared_change"):
                    counts[result["action"]] += 1
    audit.equal("trace_count", counts["connections"], run["n"])
    final = run["final_serialized_state"]
    audit.equal("final_monitor_version", [final["v"], final["arrival_streak"], final["monitor_pending"]], [6, state["arrival_streak"], None])
    close(audit, "final_monitor_state", final["monitor"], state["monitor"])
    return {"seed": run["seed"], **counts, "reasons": dict(sorted(reasons.items())), "actions": dict(sorted(actions.items())),
            "alarm_per_1000_all_decisions": counts["alarms"] * 1000 / counts["connections"],
            "alarm_per_1000_monitored": counts["alarms"] * 1000 / counts["monitored"] if counts["monitored"] else None,
            "mean_abs_beta_decision": sum(map(abs, beta)) / len(beta), "maximum_abs_beta_decision": max(map(abs, beta))}


def check_monitors(audit, report, groups, check_seed_summary, check_gate):
    totals = collections.Counter()
    for group in report["groups"]:
        label = group["generation"] + ":" + group["scenario"]
        value = group["monitor_diagnostics"]
        if group["analysis_role"] not in CONFIGS:
            audit.equal(label + ":no_monitor_report", value, None)
            continue
        rows = [monitor_seed(audit, run) for run in groups[group["generation"], group["scenario"]]]
        audit.equal(label + ":monitor_seeds", value["by_seed"], rows)
        for field in COUNT_FIELDS:
            expected = sum(row[field] for row in rows)
            audit.equal(label + ":" + field, value[field], expected)
            totals[field] += expected
        for field in ("reasons", "actions"):
            merged = collections.Counter()
            for row in rows:
                merged.update(row[field])
            audit.equal(label + ":" + field, value[field], dict(sorted(merged.items())))
        for actual, source in (("all_decision_alarm_seed_summary", "alarm_per_1000_all_decisions"),
                               ("monitored_alarm_seed_summary", "alarm_per_1000_monitored"), ("mean_abs_beta_seed_summary", "mean_abs_beta_decision")):
            check_population_summary(audit, label + ":" + actual, value[actual], [row[source] for row in rows if row[source] is not None], check_seed_summary)
        if group["family"] == "B1":
            check_gate(audit, label + ":alarm_gate", group["gates"]["monitor_alarm"], value["all_decision_alarm_seed_summary"], 0, 0, 1.0, False)
    return dict(totals)


def check_population_summary(audit, label, summary, values, full_check):
    if values:
        audit.equal(label + ":full_population", len(values), 20)
        full_check(audit, label, summary, values)
    else:
        audit.equal(label + ":empty", {key: summary[key] for key in ("n", "df", "confidence", "interval_available")},
                    {"n": 0, "df": None, "confidence": .95, "interval_available": False})
        for field in ("mean", "sd", "se", "lower", "upper", "half_width"):
            audit.equal(label + ":" + field, summary[field], None)
        audit.check(label + ":critical_absent", "critical" not in summary)
