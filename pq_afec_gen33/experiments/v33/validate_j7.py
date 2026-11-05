import sys
sys.dont_write_bytecode = True
import argparse
import collections
from concurrent.futures import ProcessPoolExecutor, as_completed
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scipy
from scipy.stats import norm, t
from experiments.v33 import bench
from experiments.v33.first_flight_observer import make_world_evidence

PATH = Path(__file__).resolve()
PLAN = ROOT / "g3/v33/bench_overlays/J7_evaluation_v1.json"
PLAN_SHA = "5f417689ea9d677e9153ba88246c20c38da8caf3bae4dabd4e67b088fa039d81"
SCHEMA = "padfec.v33.j7_independent_validation/1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def same(actual, expected, label):
    if canonical(actual) != canonical(expected):
        raise ValueError("independent J7 check: " + label)


def close(actual, expected, label):
    if actual is None or expected is None:
        same(actual, expected, label)
    elif isinstance(actual, bool) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-10):
        raise ValueError(f"independent J7 numeric check {label}: {actual!r} != {expected!r}")


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def spec_for(scenario, phase):
    return {"context": {**scenario["context"], **{k: v for k, v in phase.items() if k != "length"}},
            "world_params": scenario["world_params"], "mixture": scenario.get("mixture", [])}


def raw_job(job):
    plan = read(PLAN)
    profile, role, mode, sid = job
    protocol = plan["protocols"][profile]
    scenario = next(s for s in protocol["scenarios"] if s["id"] == sid)
    folder = Path(plan["raw_root"]) / "_".join(job)
    completed = read(folder / "finished.json")
    same(completed["status"], "complete", "shard completion")
    same(completed["seeds"], protocol["seeds"], "shard seeds")
    schedule = []
    for phase_number, phase in enumerate(scenario["phases"]):
        spec = spec_for(scenario, phase)
        cid = hashlib.sha256(canonical(spec)).hexdigest()[:20]
        for phase_index in range(phase["length"]):
            schedule.append((phase_number, phase_index, cid, spec, phase_index in (0, phase["length"] - 1)))
    results = []
    for seed in protocol["seeds"]:
        path = folder / f"seed{seed:05d}.json"
        same(sha(path), completed["results_sha256"][str(path)], "raw completion hash")
        raw = read(path)
        trace = Path(raw["trace_path"])
        same(sha(trace), raw["trace_sha256"], "raw trace hash")
        same([raw[k] for k in ("profile", "role", "observation_mode", "scenario", "seed", "n")],
             [*job, seed, len(schedule)], "raw identity and length")
        fixed = read(raw["baseline_path"])
        same(sha(raw["baseline_path"]), raw["baseline_sha256"], "fixed source hash")
        same(sha(fixed["trace_path"]), fixed["trace_sha256"], "fixed trace hash")
        with gzip.open(fixed["trace_path"], "rt", encoding="utf-8") as stream:
            fixed_rows = [json.loads(line) for line in stream]
        counts, observations = collections.Counter(), collections.Counter()
        values = {name: [] for name in ("hct_ms", "extra_server_bytes", "extra_first_flight_bytes", "extra_client_first_flight_bytes")}
        minimum_rtt = minimum_hct = None
        checked = replayed = failed = 0
        high_errors = []
        highest = max(spec_for(scenario, p)["context"]["p"] for p in scenario["phases"])
        tail = protocol["metrics"]["p_bias_high_phase_last_n"]
        cold, transition = protocol["metrics"]["cold_alarm_exclusion"], protocol["metrics"]["transition_alarm_exclusion"]
        eligible = alarms = 0
        world = bench.World(params=scenario["world_params"], seed=seed)
        with gzip.open(trace, "rt", encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                row = json.loads(line)
                phase, phase_index, cid, spec, replay = schedule[index]
                same([row[k] for k in ("index", "world_connection_index", "phase", "phase_index", "context_id", "observation_mode")],
                     [index, index, phase, phase_index, cid, mode], "row schedule")
                if scenario["reset_each_connection"]:
                    minimum_rtt = minimum_hct = None
                previous_rtt = minimum_rtt if minimum_rtt is not None else minimum_hct
                same(row["policy_decide_input"], {"op": "decide", "destination": "d", "rtt_ms": previous_rtt}, "causal decision RTT")
                value = row["raw_observed_rtt_ms"]
                if value is not None and math.isfinite(value) and value > 0:
                    minimum_rtt = value if minimum_rtt is None else min(minimum_rtt, value)
                if row["ok"]:
                    minimum_hct = row["hct_ms"] if minimum_hct is None else min(minimum_hct, row["hct_ms"])
                observed_rtt = minimum_rtt if minimum_rtt is not None else minimum_hct
                same(row["policy_rtt_ms"], observed_rtt, "causal observation RTT")
                request = row["policy_observe_input"]
                same(sorted(request), sorted(["op", "destination", "action", "hct_ms", "ok", "k_obs", "srv_bytes", "rtt_ms", "j_pred", "optional"]), "request boundary")
                same(sorted(request["optional"]), ["first_flight_evidence"], "optional boundary")
                expected = {"op": "observe", "destination": "d", "action": row["action"], "ok": row["ok"],
                            "hct_ms": row["hct_ms"] if row["ok"] else None, "rtt_ms": observed_rtt,
                            "j_pred": row["decision"].get("j3_pred_pre_ms", row["decision"].get("ej"))}
                same({k: request[k] for k in expected}, expected, "observation values")
                same(row["decision"]["action"], row["action"], "decision action")
                evidence, info = request["optional"]["first_flight_evidence"], row["observation_info"]
                same(sorted(evidence), sorted(["src", "sent", "lost", "bitmap", "trunc"]), "evidence boundary")
                if evidence["src"] not in ("none", "c1") or mode == "none" and evidence["src"] != "none":
                    raise ValueError("unexpected evidence source")
                usable = evidence["src"] != "none" and evidence["sent"] > 0 and not evidence["trunc"]
                same(info["arrival_usable"], usable, "evidence usability")
                same(info["loss_update_kind"] == "datagram", usable, "likelihood routing")
                for name, source in (("arrival_sent", "sent"), ("arrival_lost", "lost"), ("arrival_trunc", "trunc"), ("loss_evidence_src", "src")):
                    same(info[name], evidence[source], "evidence mapping")
                observations[info["loss_update_kind"]] += 1
                base = fixed_rows[index]
                for name in ("b0_hct_ms", "b0_server_bytes", "global_fixed_hct_ms", "global_fixed_server_bytes", "selected_cert_bytes", "true_rtt_ms"):
                    same(row[name], base[name], "fixed CRN row")
                close(row["extra_server_bytes"], row["server_bytes"] - row["b0_server_bytes"], "server byte delta")
                if replay:
                    context = bench.mixture_context(spec, seed, index)
                    simulation = world.sample(context, bench.Action(*row["action"]), connection=index, trace=mode != "none")
                    for target, source in (("hct_ms", "hct"), ("ok", "ok"), ("server_bytes", "server_counted_uplink_bytes"),
                                           ("selected_cert_bytes", "selected_cert_bytes"), ("true_rtt_ms", "true_rtt_ms")):
                        same(row[target], simulation[source], "fixed endpoint world replay")
                    projection = make_world_evidence(simulation, mode=mode, seed=seed, connection=index,
                        feedback_loss_probability=context.s2c_loss if world.params["features"]["s2c_loss"] else 0.0,
                        receiver_max_datagram_bytes=world.params["server"]["decoder_max_datagram_bytes"],
                        feedback_grace_ms=200, crc_list_limit=64)
                    same(evidence, projection["evidence"], "endpoint evidence replay")
                    same(row["observer_diagnostics"], projection["diagnostics"], "endpoint observer replay")
                    replayed += 1
                counts[cid, tuple(row["action"])] += 1
                if row["phase_p"] == highest and phase_index >= scenario["phases"][phase]["length"] - tail and row["p_mean_pre"] is not None:
                    high_errors.append(row["p_mean_pre"] - row["phase_p"])
                if not (scenario["reset_each_connection"] and cold > 0) and index >= cold and (phase == 0 or phase_index >= transition):
                    eligible += 1
                    alarms += len(set(row["alarm_raised"]))
                for name in values:
                    values[name].append(row[name])
                failed += not row["ok"]
                checked += 1
        same(checked, len(schedule), "complete trace")
        actual_counts = [{"context_id": cid, "action": list(action), "n": n} for (cid, action), n in sorted(counts.items())]
        same(actual_counts, raw["action_counts"], "action frequency reconstruction")
        means = {"mean_" + name: math.fsum(numbers) / checked for name, numbers in values.items()}
        means.update(failure_rate=failed / checked,
                     p_bias_high_phase=statistics.mean(high_errors) if high_errors else None,
                     p_mae_high_phase=statistics.mean(map(abs, high_errors)) if high_errors else None,
                     alarm_rate_per_1000=1000 * alarms / eligible if eligible else None)
        for name, value in means.items():
            close(raw["summary"][name], value, "raw summary " + name)
        same(raw["summary"]["failure_count"], failed, "failure count")
        results.append({"profile": profile, "role": role, "mode": mode, "scenario": sid, "seed": seed,
                        "n": checked, "action_counts": actual_counts, "means": means,
                        "failures": failed, "likelihood_counts": dict(observations), "world_endpoint_replays": replayed,
                        "raw_path": str(path), "raw_sha256": sha(path), "trace_sha256": sha(trace)})
    return results


def validate_raw(out):
    same(sha(PLAN), PLAN_SHA, "collection plan")
    plan = read(PLAN)
    jobs = [(p, role, mode, s["id"]) for p, protocol in plan["protocols"].items()
            for role in plan["policies"] for mode in plan["modes"] for s in protocol["scenarios"]]
    rows = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        for future in as_completed([executor.submit(raw_job, job) for job in jobs]):
            rows.extend(future.result())
            print(json.dumps({"independent_runs": len(rows)}), flush=True)
    rows.sort(key=lambda r: (r["profile"], r["role"], r["mode"], r["scenario"], r["seed"]))
    result = {"schema": SCHEMA, "status": "pass", "script_sha256": sha(PATH), "plan_sha256": PLAN_SHA,
              "runs": rows, "run_count": len(rows), "connections": sum(r["n"] for r in rows),
              "world_endpoint_replays": sum(r["world_endpoint_replays"] for r in rows),
              "scope": "independent raw counts, sums, fixed pairs, causal request boundary; world and evidence replay at every phase endpoint"}
    write(out, result)
    return {k: result[k] for k in ("status", "run_count", "connections", "world_endpoint_replays")}


def weights(run):
    return {(r["context_id"], tuple(r["action"])): Fraction(r["n"], run["n"]) for r in run["action_counts"]}


def paired(values):
    mean = statistics.mean(values)
    width = float(t.ppf(0.975, len(values) - 1)) * statistics.stdev(values) / math.sqrt(len(values))
    return mean, mean - width, mean + width


def check_summary(actual, values, label):
    same(actual["n"], len(values), label + " count")
    if len(values) >= 2:
        mean, lower, upper = paired(values)
    else:
        mean, lower, upper = (values[0] if values else None), None, None
    for name, value in (("mean", mean), ("lower", lower), ("upper", upper)):
        close(actual[name], value, label + " " + name)


def independent_difference(candidate, baseline, tables):
    same([r["seed"] for r in candidate], [r["seed"] for r in baseline], "independent seed pairing")
    coefficients = collections.defaultdict(Fraction)
    estimates = []
    for ca, ba in zip(candidate, baseline):
        cw, bw = weights(ca), weights(ba)
        context_totals = []
        for w in (cw, bw):
            totals = collections.defaultdict(Fraction)
            for (cid, _), n in w.items():
                totals[cid] += n
            context_totals.append(dict(totals))
        if context_totals[0] != context_totals[1]:
            raise ValueError("independent reference cancellation failed")
        delta = {key: cw.get(key, 0) - bw.get(key, 0) for key in cw.keys() | bw.keys()}
        estimates.append(math.fsum(float(value) * tables[key]["mean_gap_ms"] for key, value in delta.items() if value))
        for key, value in delta.items():
            coefficients[key] += value / len(candidate)
    mean, lower, upper = paired(estimates)
    bounds = []
    unresolved = []
    for key, value in coefficients.items():
        if not value:
            continue
        table = tables[key]
        if table["gap_half_width_ms"] is None or not table["uncertainty_resolved"]:
            unresolved.append(key)
        else:
            bounds.append(abs(float(value)) * table["gap_half_width_ms"])
    mc = None if unresolved else math.fsum(bounds)
    lo, hi = (None, None) if mc is None else (lower - mc, upper + mc)
    status = "pass" if hi is not None and hi <= 0.5 else "fail" if lo is not None and lo > 0.5 else "inconclusive"
    return {"mean": mean, "lower": lower, "upper": upper, "mc": mc, "adjusted_lower": lo,
            "adjusted_upper": hi, "status": status, "seed_estimates": estimates, "unresolved_terms": len(unresolved)}


def validate_report(family_path, raw_path, report_path, pool_path, out):
    saved, independent, report = (read(p) for p in (family_path, raw_path, report_path))
    same(independent["status"], "pass", "independent raw completion")
    same(independent["script_sha256"], sha(PATH), "independent raw checker identity")
    published = read(str(report_path) + ".published.json")
    same(published["status"], "complete", "report publication")
    for path, checksum in published["artifacts_sha256"].items():
        same(sha(path), checksum, "published artifact")
    same(published["family_sha256"], sha(family_path), "publication family")
    same(report["provenance"]["family_sha256"], sha(family_path), "report family")
    for path, checksum in saved["inputs_sha256"].items():
        same(sha(path), checksum, "frozen input")
    for path, checksum in report["provenance"]["pool_attestation"]["files_sha256"].items():
        same(sha(path), checksum, "pool attestation")
    jobs = saved["manifest"]["jobs"]
    same(sorted(p.stem for p in Path(pool_path).glob("results/*.json")), sorted(j["job_id"] for j in jobs), "MC inventory")
    tables = {}
    for job in jobs:
        result = read(Path(pool_path) / "results" / (job["job_id"] + ".json"))
        same(result["action"], job["action"], "MC action")
        same(result["reference_action"], job["reference_action"], "MC common control")
        same(result["evaluation_family_size"], len(jobs), "MC whole family")
        same(result["validation_seed"], 850001, "MC fixed seed")
        if result["approximate"]:
            same(result["n"], 131072, "MC fixed sample count")
            state = read(Path(pool_path) / "checkpoints" / (job["job_id"] + ".json"))
            moments = state["records"][",".join(map(str, job["action"]))]
            same(moments["n"], result["n"], "MC checkpoint sample count")
            close(result["mean_gap_ms"], moments["mean_gap"], "MC mean gap")
            close(result["mean_hct_ms"], moments["mean_hct"], "MC absolute mean")
            variance = max(0, moments["m2_gap"] / (result["n"] - 1))
            width = float(norm.ppf(1 - 0.05 / (2 * len(jobs)))) * math.sqrt(variance / result["n"])
            unresolved = variance <= 1e-20 and job["action"] != job["reference_action"]
            same(result["uncertainty_resolved"], not unresolved, "zero variance unresolved")
            close(result["gap_half_width_ms"], None if unresolved else width, "MC family width")
            close(result["gap_variance_ms2"], variance, "MC variance")
        else:
            same(result["method"], "structural_zero_loss_pair", "structural method")
            same(result["n"], 0, "structural sample count")
            same(result["uncertainty_resolved"], True, "structural resolution")
        tables[job["context_id"], tuple(job["action"])] = result
    observed_keys = {(r["context_id"], tuple(r["action"])) for run in independent["runs"] for r in run["action_counts"]}
    if observed_keys != set(tables):
        raise ValueError("independent full action union differs")
    groups = collections.defaultdict(list)
    for run in independent["runs"]:
        same(sha(run["raw_path"]), run["raw_sha256"], "raw input unchanged")
        groups[run["profile"], run["role"], run["mode"], run["scenario"]].append(run)
    for values in groups.values():
        values.sort(key=lambda r: r["seed"])
    plan = read(PLAN)
    expected_cells = {(p, mode, s["id"]) for p, protocol in plan["protocols"].items()
                      for mode in plan["modes"] for s in protocol["scenarios"]}
    seen_cells = set()
    checked, decisions, improvements = [], [], []
    for row in report["comparisons"]:
        p, mode, sid = row["profile"], row["mode"], row["scenario"]
        if (p, mode, sid) not in expected_cells or (p, mode, sid) in seen_cells:
            raise ValueError("independent comparison inventory differs")
        seen_cells.add((p, mode, sid))
        same(row["primary"], mode in ("none", "c1"), "primary membership")
        result = independent_difference(groups[p, "j7", mode, sid], groups[p, "l1", mode, sid], tables)
        for key in ("mean", "lower", "upper"):
            close(row["seed_summary"][key], result[key], "seed " + key)
        for target, source in (("shared_mc_bound_ms", "mc"), ("lower_bound_ms", "adjusted_lower"), ("upper_bound_ms", "adjusted_upper")):
            close(row[target], result[source], target)
        same(row["regression_gate"]["status"], result["status"], "cell verdict")
        for actual, expected in zip(row["seed_estimates"], result["seed_estimates"]):
            close(actual["mean_delta_ms"], expected, "individual seed delta")
        if row["primary"]:
            decisions.append(result["status"])
            if mode == "c1" and result["adjusted_upper"] is not None and result["adjusted_upper"] < 0:
                improvements.append([p, sid])
        checked.append({"profile": p, "mode": mode, "scenario": sid, **result})
        realized = [ca["means"]["mean_hct_ms"] - ba["means"]["mean_hct_ms"] for ca, ba in
                    zip(groups[p, "j7", mode, sid], groups[p, "l1", mode, sid])]
        check_summary(row["realized_hct_diagnostic"], realized, "same-world realized diagnostic")
    if seen_cells != expected_cells:
        raise ValueError("incomplete independent comparisons")
    group_keys = set()
    for group in report["groups"]:
        key = group["profile"], group["role"], group["mode"], group["scenario"]
        if key not in groups or key in group_keys:
            raise ValueError("diagnostic group inventory differs")
        group_keys.add(key)
        raw_runs = groups[key]
        for field, value in group["observed"].items():
            numbers = [r["means"][field] for r in raw_runs if r["means"][field] is not None]
            check_summary(value, numbers, "group diagnostic " + field)
        same(group["observations"]["connections"], sum(r["n"] for r in raw_runs), "diagnostic denominator")
        same(group["observations"]["failures"], sum(r["failures"] for r in raw_runs), "diagnostic failures")
        same(group["observations"]["successes"], sum(r["n"] - r["failures"] for r in raw_runs), "diagnostic successes")
    if group_keys != set(groups):
        raise ValueError("incomplete diagnostic groups")
    contributions = set()
    for cell in report["factorial_contributions"]:
        mode, sid = cell["mode"], cell["scenario"]
        if (mode, sid) in contributions:
            raise ValueError("duplicate factorial contribution")
        contributions.add((mode, sid))
        contrasts = [(cell["combined_endpoint"], ("wire46", "j7", mode, sid), ("wire39", "l1", mode, sid))]
        contrasts += [(cell["wire_effect_by_policy"][role], ("wire46", role, mode, sid), ("wire39", role, mode, sid)) for role in ("l1", "j7")]
        for result, ca_key, ba_key in contrasts:
            estimates, realized = [], []
            for ca, ba in zip(groups[ca_key], groups[ba_key]):
                means = [math.fsum(float(w) * tables[k]["mean_hct_ms"] for k, w in weights(r).items()) for r in (ca, ba)]
                estimates.append(means[0] - means[1])
                realized.append(ca["means"]["mean_hct_ms"] - ba["means"]["mean_hct_ms"])
            close(result["expected_cost_point_ms"], statistics.mean(estimates), "cross-profile point estimate")
            check_summary(result["realized_hct_diagnostic"], realized, "cross-profile realized diagnostic")
            same(result["used_for_adoption"], False, "cross-profile adoption exclusion")
            same(result["oracle_cancels"], False, "cross-profile cancellation exclusion")
        policy = {p: next(r["mean"] for r in checked if (r["profile"], r["mode"], r["scenario"]) == (p, mode, sid)) for p in ("wire39", "wire46")}
        for profile in policy:
            close(cell["policy_effect_" + profile + "_ms"], policy[profile], "policy decomposition")
        close(cell["interaction_point_ms"], policy["wire46"] - policy["wire39"], "interaction decomposition")
    same(len(contributions), 45, "contribution count")
    same(len(checked), 90, "all comparison count")
    same(len(decisions), 60, "primary comparison count")
    overall = "fail" if "fail" in decisions else "pass" if all(d == "pass" for d in decisions) and improvements else "inconclusive"
    same(report["performance_decision"]["status"], overall, "independent adoption decision")
    same(report["performance_decision"]["c1_improvement_cells"], improvements, "independent C1 improvement cells")
    output = {"schema": SCHEMA, "status": "pass", "script_sha256": sha(PATH), "scipy_version": scipy.__version__,
              "family_sha256": sha(family_path), "raw_check_sha256": sha(raw_path), "report_sha256": sha(report_path),
              "action_family": len(jobs), "comparisons": checked, "performance_decision": overall,
              "checks": "raw-derived exact rational action weights; independent SciPy t/normal intervals; checkpoint MC moments; 60-cell adoption decision",
              "run_count": independent["run_count"], "connections": independent["connections"],
              "world_endpoint_replays": independent["world_endpoint_replays"]}
    write(out, output)
    return {k: output[k] for k in ("status", "action_family", "performance_decision", "connections", "world_endpoint_replays")}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("raw")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("report")
    for name in ("family", "raw", "report", "pool", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "raw":
        value = validate_raw(args.out)
    else:
        value = validate_report(args.family, args.raw, args.report, args.pool, args.out)
    print(json.dumps(value, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
