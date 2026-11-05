import gzip
import json
import math
import statistics


def recent_mode(values):
    if not values:
        return None
    counts = {value: values.count(value) for value in values}
    return max(reversed(values), key=lambda value: counts[value])


def estimate(history, k, u):
    selected = [value[2] for value in history if value[0] == k and value[1] == u][-16:]
    if not selected:
        return {"a_pre": 0 if u <= 0 else 41 * (k - 1), "a_pre_n": 0,
                "a_pre_median": None, "a_pre_source": "legacy_estimate"}
    value = statistics.median(selected)
    return {"a_pre": int(value) if int(value) == value else int(value) + 1,
            "a_pre_n": len(selected), "a_pre_median": value,
            "a_pre_source": "received_initial_median"}


def seed(audit, run, scenario, margin):
    history, ks, sizes, scope = [], [], [], "legacy_unclassified"
    totals = {"connections": 0, "observed_positive": 0, "missing_or_no_large": 0,
              "median_decisions": 0, "fallback_decisions": 0, "received_preflight_bytes": 0}
    u = scenario["context"]["uplink_mbps"]
    with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if scenario["reset_each_connection"]:
                history, ks, sizes, scope = [], [], [], "legacy_unclassified"
            k, s = recent_mode(ks), statistics.median(sizes) if sizes else None
            decision, info, request = row["decision"], row["observation_info"], row["policy_observe_input"]
            audit.equal("preflight_S_before", row["S_hat_pre"], s)
            if decision.get("k") is not None:
                audit.equal("preflight_k_before", decision["k"], k)
                budget = estimate(history, k, u)
                for field, expected in budget.items():
                    audit.equal("preflight_decision_" + field, decision[field], expected)
                audit.equal("preflight_margin", decision["margin_server_bytes"], margin)
                audit.equal("preflight_decision_S_scope", decision["S_scope"], scope)
                audit.equal("preflight_decision_prefix", decision["prefix"], 1280 * (decision["n_need"] - 1))
                totals["median_decisions" if budget["a_pre_n"] else "fallback_decisions"] += 1
            if info["ctx"] is not None:
                audit.equal("preflight_observe_k_before", info["ctx"]["k"], k)
                audit.equal("preflight_observe_S_before", info["ctx"]["S"], s)
                for field, expected in estimate(history, k, u).items():
                    audit.equal("preflight_observe_" + field, info["ctx"][field], expected)
                audit.equal("preflight_observe_scope", info["ctx"]["S_scope"], scope)
            received, first_large, observed, last_time = 0, None, [], -1.0
            for time, kind, size in row["preflight_received"]:
                audit.check("preflight_arrival_order", type(time) in (int, float) and math.isfinite(time) and time >= 0 and time >= last_time)
                audit.check("preflight_arrival_size", type(size) is int and size > 0)
                last_time = time
                received += size
                if first_large is None:
                    if size >= 1200:
                        first_large = time
                    elif kind == "ack":
                        observed.append(size)
            total = sum(observed)
            evidence = {"source": "world_arrival_proxy", "small_initial_sizes": observed,
                        "first_large_seen": first_large is not None, "srv_bytes_scope": "includes_observed_preflight"}
            audit.equal("preflight_observer_input", request["optional"]["preflight"], evidence)
            audit.equal("preflight_received_scope", request["srv_bytes"], received)
            diagnostic = {"first_large_ms": first_large, "observed_preflight_bytes": total,
                          "received_server_bytes": received, "response_received_bytes": received - total,
                          "unreceived_server_bytes_used": False, "actual_quic_initial_classifier_validated": False}
            audit.equal("preflight_diagnostics", row["preflight_diagnostics"], diagnostic)
            updated = first_large is not None and total > 0 and type(request["k_obs"]) is int and 1 <= request["k_obs"] <= 4
            audit.equal("preflight_update_eligibility", info["preflight_updated"], updated)
            audit.equal("preflight_observed_total", info["preflight_observed_bytes"], total)
            audit.equal("preflight_response", info["S_response_bytes"], received - total)
            audit.equal("preflight_observation_scope", info["S_observation_scope"], "response_excludes_observed_preflight")
            if updated:
                history.append((request["k_obs"], float(u), total))
                history = history[-64:]
            if request["ok"]:
                if type(request["k_obs"]) is int and request["k_obs"] >= 1:
                    ks = (ks + [request["k_obs"]])[-16:]
                if info["legacy_y"] != 1 and received > total:
                    if scope != "response_excludes_observed_preflight":
                        sizes = []
                    scope = "response_excludes_observed_preflight"
                    sizes = (sizes + [float(received - total)])[-16:]
            audit.equal("preflight_S_after", row["S_hat_post"], statistics.median(sizes) if sizes else None)
            totals["connections"] += 1
            totals["observed_positive" if updated else "missing_or_no_large"] += 1
            totals["received_preflight_bytes"] += total
    audit.equal("preflight_run_count", totals["connections"], run["n"])
    audit.equal("preflight_final_history_size", run["final_state"]["apre_history_count"], len(history))
    audit.equal("preflight_final_S_scope", run["final_state"]["S_scope"], scope)
    return totals


def check_runs(audit, groups, protocol):
    scenarios = {scenario["id"]: scenario for scenario in protocol["scenarios"]}
    totals = {}
    for runs in groups.values():
        for run in runs:
            if run["analysis_role"] not in ("j6", "zero"):
                continue
            values = seed(audit, run, scenarios[run["scenario"]], 30 if run["analysis_role"] == "j6" else 0)
            for key, value in values.items():
                totals[key] = totals.get(key, 0) + value
    return totals
