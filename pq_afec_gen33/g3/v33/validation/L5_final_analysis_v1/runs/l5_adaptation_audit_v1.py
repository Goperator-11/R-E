import collections
import gzip
import json


def load_trace(run):
    with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def classify(row, refs, tables, epsilon, width):
    item = tables.get((row["context_id"], tuple(row["action"])))
    uncertainty = None if item is None else width(item)
    if uncertainty is None:
        return None
    if item["mean_gap_ms"] - uncertainty > epsilon:
        return False
    reference = refs.get(row["context_id"])
    selection = None if reference is None or reference.get("uncertainty_resolved") is False else reference.get("selection_gap_upper_ms")
    if selection is not None and item["mean_gap_ms"] + uncertainty + selection <= epsilon:
        return True
    return None


def event(flags, begin, end, consecutive, limit):
    start = confirmed = None
    unknown = streak = 0
    for position in range(begin, end):
        value = flags[position]
        unknown += value is None
        streak = streak + 1 if value is True else 0
        if streak == consecutive:
            start, confirmed = position - consecutive + 1, position
            break
    blocks = []
    for position in range(begin, begin + limit + 1):
        if position + consecutive > end:
            blocks.append(None)
            continue
        block = flags[position:position + consecutive]
        blocks.append(True if all(x is True for x in block) else False if any(x is False for x in block) else None)
    status = "pass" if True in blocks else "fail" if all(x is False for x in blocks) else "inconclusive"
    return {"change_index": begin, "end_index_exclusive": end, "start_index": start, "confirmed_index": confirmed,
            "start_new_observations": None if start is None else start - begin,
            "confirmed_new_observations": None if confirmed is None else confirmed - begin,
            "censored": start is None, "followup_decisions": end - begin,
            "unknown_predicate_rows_before_confirmation": unknown, "consecutive": consecutive,
            "status": "adapted" if start is not None else "unresolved" if unknown else "right_censored",
            "threshold_status": status, "start_limit_new_observations": limit}


def longest(values):
    result = streak = 0
    for value in values:
        streak = streak + 1 if value else 0
        result = max(result, streak)
    return result


def check_group(audit, group, runs, scenario, protocol, refs, tables, width, trace_loader=load_trace):
    epsilon = protocol["metrics"]["adaptation_near_optimal_ms"]
    consecutive = protocol["metrics"]["adaptation_consecutive"]
    limit = protocol["thresholds"]["B5_adaptation_connections"]
    changes, position, previous = [], 0, scenario["context"].get("cert_bytes")
    for phase in scenario["phases"]:
        current = phase.get("cert_bytes", scenario["context"].get("cert_bytes"))
        if position and current != previous:
            changes.append(position)
        position += phase["length"]
        previous = current
    label = group["generation"] + ":" + group["scenario"]
    trace_results = group["trace_metrics_by_seed"]
    audit.equal("B5_trace_seeds:" + label, [item["seed"] for item in trace_results], [run["seed"] for run in runs])
    cases = []
    for run, reported in zip(runs, trace_results):
        tag = label + ":" + str(run["seed"])
        rows = trace_loader(run)
        audit.equal("B5_trace_n:" + tag, len(rows), run["n"])
        audit.equal("B5_trace_indices:" + tag, [row["index"] for row in rows], list(range(run["n"])))
        actual = collections.Counter((row["context_id"], tuple(row["action"])) for row in rows)
        expected = collections.Counter()
        for cell in run["action_counts"]:
            expected[cell["context_id"], tuple(cell["action"])] += cell["n"]
        audit.equal("B5_trace_action_counts:" + tag, actual, expected)
        flags = [classify(row, refs, tables, epsilon, width) for row in rows]
        events = [event(flags, begin, changes[i + 1] if i + 1 < len(changes) else len(rows), consecutive, limit)
                  for i, begin in enumerate(changes)]
        audit.equal("B5_events:" + tag, reported["adaptation"], events)
        audit.equal("B5_unknown:" + tag, reported["unknown_cost_rows"], sum(value is None for value in flags))
        audit.equal("B5_confirmed_episode:" + tag, reported["longest_confirmed_suboptimal_episode"], longest(value is False for value in flags))
        audit.equal("B5_possible_episode:" + tag, reported["longest_possible_suboptimal_episode"], longest(value is not True for value in flags))
        audit.equal("B5_epsilon:" + tag, reported["epsilon_ms"], epsilon)
        cases.extend({"seed": run["seed"], **item} for item in events)
    statuses = [item["threshold_status"] for item in cases]
    status = "inconclusive"
    if len(cases) == len(runs):
        status = "fail" if "fail" in statuses else "pass" if statuses and all(x == "pass" for x in statuses) else "inconclusive"
    gate = {"status": status, "rule": "all protocol seeds must start within the limit and confirm consecutive near-optimal decisions",
            "threshold": limit, "expected_seed_count": len(runs), "observed_cases": len(cases),
            "censored_count": sum(item["censored"] for item in cases),
            "confirmed_start_distribution": [item["start_new_observations"] for item in cases], "cases": cases}
    audit.equal("B5_gate:" + label, group["gates"]["adaptation"], gate)
    return len(cases)
