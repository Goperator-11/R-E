import collections
import gzip
import json


def check_row(audit, row, label):
    info = row["observation_info"]
    ctx = info["ctx"]
    request = row["policy_observe_input"]
    evidence = request["optional"]["first_flight_evidence"]
    audit.equal("fixed_epsilon_before:" + label, info["epsilon_before"], .001)
    audit.equal("fixed_epsilon_after:" + label, info["epsilon_after"], .001)
    audit.equal("fixed_epsilon_no_update:" + label, info["epsilon_update_eligible"], False)
    audit.equal("grade_valid:" + label, info["grade_valid"], ctx is not None)
    if ctx is None:
        expected = None if row["ok"] else 2
        audit.equal("cold_cut1:" + label, info["cut1_ms"], None)
        audit.equal("cold_cut2:" + label, info["cut2_ms"], None)
    else:
        delta, lead, trail = row["action"]
        width = ctx["W"] + delta
        serial = (ctx["k"] * width + lead * (width + 39 + 6 * ctx["k"])) * 8.0 / (ctx["u"] * 1000) if ctx["u"] > 0 else 0.0
        response = width * 8.0 / (ctx["u"] * 1000) if ctx["u"] > 0 else 0.0
        first = 1.5 * ctx["rtt"] + serial + 3.0
        second = first + ctx["rtt"] + response
        audit.near("grade_cut1:" + label, info["cut1_ms"], first)
        audit.near("grade_cut2:" + label, info["cut2_ms"], second)
        audit.equal("observed_rtt_context:" + label, ctx["rtt"], request["rtt_ms"])
        expected = 2 if not row["ok"] else 0 if row["hct_ms"] < first else 1 if row["hct_ms"] < second else 2
    audit.equal("grade_value:" + label, info["grade"], expected)
    reason = "source_none" if evidence["src"] == "none" else "truncated" if evidence["trunc"] else "empty" if evidence["sent"] == 0 else None
    kind = "datagram" if reason is None else "categorical" if ctx is not None else "predict_only"
    audit.equal("arrival_usable:" + label, info["arrival_usable"], reason is None)
    audit.equal("arrival_reason:" + label, info["arrival_reject_reason"], reason)
    audit.equal("loss_kind:" + label, info["loss_update_kind"], kind)
    audit.equal("loss_updated:" + label, info["updated"], kind != "predict_only")
    return kind


def check_runs(audit, groups):
    totals = collections.Counter()
    for runs in groups.values():
        for run in runs:
            if run["analysis_role"] not in ("j1", "cost"):
                continue
            label = run["generation"] + ":" + run["scenario"] + ":" + str(run["seed"])
            count = 0
            with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
                for count, line in enumerate(stream, 1):
                    row = json.loads(line)
                    kind = check_row(audit, row, label + ":" + str(count))
                    totals[kind] += 1
                    totals["connections"] += 1
                    totals["failed"] += int(not row["ok"])
            audit.equal("grade_trace_count:" + label, count, run["n"])
            totals["runs"] += 1
    return dict(totals)
