import argparse
import collections
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33.bench_metrics import adaptation, evaluate_threshold, paired_summary


RULES = ROOT / "g3/v33/bench_reporting_rules.json"
RAW_SOURCES = {"bench.py", "bench_metrics.py", "policy_worker.py", "worldsim.py", "worldparams.json"}
ORACLE_SOURCES = {"oracle.py", "worldsim.py", "worldparams.json"}
JOB_SOURCES = ORACLE_SOURCES | {"bench.py", "bench_oracles.py"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    result = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"expected JSON object: {path}")
    return result


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def action_key(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(type(x) is not int or x < 0 for x in value):
        raise ValueError("invalid action")
    return tuple(value)


def source_check(values, required):
    if set(values) != required:
        raise ValueError("producer source inventory differs")
    for name, expected in values.items():
        if Path(name).name != name or file_hash(Path(__file__).with_name(name)) != expected:
            raise ValueError(f"producer source differs: {name}")


def load_inputs(protocol_path, raw_dirs, oracle_dirs, action_dirs, rules_path=RULES):
    rules = read_json(rules_path)
    if rules.get("schema") != "padfec.v33.benchmark_reporting_rules/1" or not rules.get("frozen_before_reading_numerical_raw_results"):
        raise ValueError("frozen reporting rules are required")
    rules_hash = file_hash(rules_path)
    from experiments.v33 import bench, bench_oracles
    protocol = bench.load_protocol(Path(protocol_path))
    protocol_hash = file_hash(protocol_path)
    provenance = {"protocol_path": str(Path(protocol_path).resolve()), "protocol_sha256": protocol_hash,
                  "reporting_rules_path": str(Path(rules_path).resolve()), "reporting_rules_sha256": rules_hash,
                  "reporting_source_sha256": {name: file_hash(Path(__file__).with_name(name)) for name in ("bench_report.py", "bench_metrics.py")},
                  "raw_manifests": [], "raw_summary_files": [], "oracle_manifests": [], "action_manifests": [], "result_files": []}
    fingerprints = {}
    for folder in map(Path, raw_dirs):
        path = folder / "manifest.json"
        manifest = read_json(path)
        if manifest.get("schema") != "padfec.v33.benchmark_raw_manifest/1" or manifest.get("protocol_sha256") != protocol_hash:
            raise ValueError("raw manifest protocol differs")
        if digest(manifest["protocol"]) != digest(protocol) or manifest["seeds"] != protocol["seeds"]:
            raise ValueError("raw manifest must contain the entire frozen seed list and protocol")
        source_check(manifest["source_sha256"], RAW_SOURCES)
        current = bench.policy_source_fingerprints(protocol, manifest["generations"])
        if current != manifest["policy_source_fingerprints"]:
            raise ValueError("policy source fingerprint differs from raw manifest")
        for generation, fingerprint in current.items():
            if generation in fingerprints and fingerprints[generation] != fingerprint:
                raise ValueError("mixed policy fingerprints")
            fingerprints[generation] = fingerprint
        provenance["raw_manifests"].append({"path": str(path.resolve()), "sha256": file_hash(path), "source_sha256": manifest["source_sha256"], "policy_source_fingerprints": current})
        provenance["raw_summary_files"].extend({"path": str(item.resolve()), "sha256": file_hash(item)} for item in sorted(folder.glob("*/*/*/seed*.json")))
    raw = bench_oracles.raw_summaries(list(map(Path, raw_dirs)), protocol_hash)
    refs = bench_oracles.references(list(map(Path, oracle_dirs)), protocol_hash, protocol)
    contexts = bench.all_contexts(protocol)
    scenario_map = {scenario["id"]: scenario for scenario in protocol["scenarios"]}
    for run in raw:
        expected_weights = collections.defaultdict(Fraction)
        scenario = scenario_map[run["scenario"]]
        for phase in scenario["phases"]:
            expected_weights[bench.context_id(bench.context_spec(scenario, phase))] += Fraction(phase["length"], run["n"])
        if context_weights(weights(run)) != dict(expected_weights):
            raise ValueError("raw context weights differ from frozen phases")
    tables = {}
    jobs_pending = []
    table_references = {}
    for mode, folders, destination in (("build", oracle_dirs, "oracle_manifests"), ("actions", action_dirs, "action_manifests")):
        for folder in map(Path, folders):
            path = folder / "manifest.json"
            manifest = read_json(path)
            bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode=mode)
            jobs = {job["job_id"]: job for job in manifest["jobs"]}
            if len(jobs) != len(manifest["jobs"]):
                raise ValueError("duplicate oracle job")
            found = set()
            provenance[destination].append({"path": str(path.resolve()), "sha256": file_hash(path), "source_sha256": manifest["source_sha256"],
                                            "evaluation_family_size": manifest.get("evaluation_family_size"), "job_count": len(jobs)})
            for result_path in sorted((folder / "results").glob("*.json")):
                item = read_json(result_path)
                job_id = item.get("job_id")
                if job_id not in jobs or result_path.stem != job_id or item.get("status") != "complete" or item.get("protocol_sha256") != protocol_hash:
                    raise ValueError("oracle result identity differs")
                job = jobs[job_id]
                cid = item["context_id"]
                if cid != job["context_id"] or cid not in contexts:
                    raise ValueError("oracle context differs")
                bench_oracles.validate_oracle_result(item, protocol=protocol, context_spec=contexts[cid], job=job,
                                                     mode=mode, evaluation_family_size=manifest.get("evaluation_family_size"))
                if mode == "build":
                    if cid not in refs or digest(refs[cid]) != digest(item):
                        raise ValueError("reference loader disagrees")
                else:
                    action = action_key(item["action"])
                    reference = action_key(item["reference_action"])
                    if list(action) != job["action"] or list(reference) != job["reference_action"]:
                        raise ValueError("action job differs")
                    if cid in table_references and table_references[cid] != reference:
                        raise ValueError("action tables use different references")
                    table_references[cid] = reference
                    if cid in refs:
                        if reference != action_key(refs[cid]["chosen_action"]) or manifest["oracle_digests"].get(cid) != digest(refs[cid]):
                            raise ValueError("action reference provenance differs")
                    finite(item["mean_gap_ms"], "mean_gap_ms")
                    key = (cid, action)
                    if key in tables and digest(tables[key]) != digest(item):
                        raise ValueError("duplicate action with different values")
                    tables[key] = item
                found.add(job_id)
                provenance["result_files"].append({"path": str(result_path.resolve()), "sha256": file_hash(result_path)})
            jobs_pending.extend(f"{mode}:{job}" for job in sorted(set(jobs) - found))
    provenance["raw_run_identities"] = [[r["generation"], r["variant"], r["scenario"], r["seed"]] for r in raw]
    provenance["raw_trace_files"] = [{"path": r["trace_path"], "sha256": r["trace_sha256"]} for r in raw]
    provenance["rules"] = rules
    if file_hash(rules_path) != rules_hash or file_hash(protocol_path) != protocol_hash:
        raise ValueError("reporting rules or protocol changed during input loading")
    return protocol, raw, refs, tables, provenance, jobs_pending


def weights(run):
    n = run["n"]
    if type(n) is not int or n < 1:
        raise ValueError("run n must be positive")
    result = collections.defaultdict(Fraction)
    for item in run["action_counts"]:
        count = item["n"]
        if type(count) is not int or count < 0:
            raise ValueError("action count must be nonnegative")
        if count:
            result[(item["context_id"], action_key(item["action"]))] += Fraction(count, n)
    if sum(result.values(), Fraction()) != 1:
        raise ValueError("action counts do not sum to run n")
    return dict(result)


def average_weights(runs):
    result = collections.defaultdict(Fraction)
    for run in runs:
        for key, value in weights(run).items():
            result[key] += value / len(runs)
    return dict(result)


def context_weights(action_weights):
    result = collections.defaultdict(Fraction)
    for (cid, _), value in action_weights.items():
        result[cid] += value
    return dict(result)


def gap_width(table):
    if table.get("uncertainty_resolved") is False:
        return None
    distinct = action_key(table["action"]) != action_key(table["reference_action"])
    if table.get("zero_observed_variance") and distinct and table.get("approximate", True):
        return None
    value = table.get("gap_half_width_ms")
    if value is None:
        return None
    value = finite(value, "gap_half_width_ms")
    if value < 0:
        raise ValueError("negative gap width")
    return value


def selection_gap(reference):
    if reference.get("uncertainty_resolved") is False:
        return None
    value = reference.get("selection_gap_upper_ms")
    if value is None:
        return None
    value = finite(value, "selection gap")
    if value < 0:
        raise ValueError("negative selection gap")
    return value


def weighted_bound(coefficients, tables):
    terms = []
    for key, value in coefficients.items():
        if value == 0:
            continue
        if key not in tables or gap_width(tables[key]) is None:
            return None
        terms.append(abs(float(value)) * gap_width(tables[key]))
    return math.fsum(terms)


def expected_regret(runs, references, tables, confidence=.95):
    missing = set()
    estimates = []
    for run in runs:
        coefficients = weights(run)
        absent = [(cid, action) for cid, action in coefficients if cid not in references or (cid, action) not in tables]
        missing.update(f"reference:{cid}" for cid, _ in absent if cid not in references)
        missing.update(f"action:{cid}:{','.join(map(str, action))}" for cid, action in absent if (cid, action) not in tables)
        estimates.append({"seed": run["seed"], "mean_gap_ms": None if absent else math.fsum(float(weight) * finite(tables[key]["mean_gap_ms"], "gap") for key, weight in coefficients.items())})
    summary = paired_summary([row["mean_gap_ms"] for row in estimates], confidence) if not missing else paired_summary([], confidence)
    average = average_weights(runs)
    mc = weighted_bound(average, tables)
    selection = 0.0
    for cid, weight in context_weights(average).items():
        if cid not in references or selection_gap(references[cid]) is None:
            selection = None
            break
        selection += float(weight) * selection_gap(references[cid])
    lower = summary["lower"] - mc if summary["lower"] is not None and mc is not None else None
    upper = summary["upper"] + mc + selection if summary["upper"] is not None and mc is not None and selection is not None else None
    return {"status": "pending" if missing else "available", "estimate_kind": "gap to frozen selected reference; not an exact true-optimum regret",
            "seed_summary": summary, "seed_estimates": estimates, "shared_mc_bound_ms": mc,
            "selection_gap_bound_ms": selection, "lower_bound_ms": lower, "upper_bound_ms": upper,
            "missing": sorted(missing)}


def direct_comparison(candidate, baseline, tables, confidence=.95):
    ca = {r["seed"]: r for r in candidate}
    ba = {r["seed"]: r for r in baseline}
    if set(ca) != set(ba):
        raise ValueError("paired comparison seed sets differ")
    coefficients = collections.defaultdict(Fraction)
    estimates = []
    missing = set()
    for seed in sorted(ca):
        cw, bw = weights(ca[seed]), weights(ba[seed])
        if context_weights(cw) != context_weights(bw):
            raise ValueError("oracle does not cancel with unequal context weights")
        difference = {key: cw.get(key, Fraction()) - bw.get(key, Fraction()) for key in cw.keys() | bw.keys()}
        absent = [key for key, value in difference.items() if value and key not in tables]
        missing.update(f"action:{cid}:{','.join(map(str, action))}" for cid, action in absent)
        estimates.append({"seed": seed, "mean_delta_ms": None if absent else math.fsum(float(value) * finite(tables[key]["mean_gap_ms"], "gap") for key, value in difference.items() if value)})
        for key, value in difference.items():
            coefficients[key] += value / len(ca)
    summary = paired_summary([r["mean_delta_ms"] for r in estimates], confidence) if not missing else paired_summary([], confidence)
    mc = weighted_bound(coefficients, tables)
    realized = paired_summary([finite(ca[s]["summary"]["mean_hct_ms"], "HCT") - finite(ba[s]["summary"]["mean_hct_ms"], "HCT") for s in sorted(ca)], confidence)
    return {"status": "pending" if missing else "available", "sign": "candidate minus baseline; negative is faster",
            "seed_summary": summary, "seed_estimates": estimates, "shared_mc_bound_ms": mc,
            "selection_gap_bound_ms": 0.0, "oracle_cancels": True,
            "lower_bound_ms": summary["lower"] - mc if summary["lower"] is not None and mc is not None else None,
            "upper_bound_ms": summary["upper"] + mc if summary["upper"] is not None and mc is not None else None,
            "realized_hct_diagnostic": realized, "missing": sorted(missing)}


def near_optimal(row, references, tables, epsilon):
    key = (row["context_id"], action_key(row["action"]))
    table = tables.get(key)
    if table is None or gap_width(table) is None:
        return None
    mean, width = finite(table["mean_gap_ms"], "gap"), gap_width(table)
    if mean - width > epsilon:
        return False
    reference = references.get(key[0])
    bound = selection_gap(reference) if reference is not None else None
    return True if bound is not None and mean + width + bound <= epsilon else None


def load_trace(run):
    if run.get("trace_sha256") is not None and file_hash(run["trace_path"]) != run["trace_sha256"]:
        raise ValueError("trace hash differs")
    rows = []
    with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("index") != len(rows):
                raise ValueError("trace index differs")
            rows.append(row)
    if len(rows) != run["n"]:
        raise ValueError("trace length differs")
    actual = collections.Counter((r["context_id"], action_key(r["action"])) for r in rows)
    expected = {key: value * run["n"] for key, value in weights(run).items()}
    if actual != expected:
        raise ValueError("trace action counts differ")
    return rows


def _longest(flags):
    longest = current = 0
    for value in flags:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def trace_metrics(run, scenario, protocol, references, tables, trace_loader=load_trace):
    rows = trace_loader(run)
    settings = protocol["metrics"]
    epsilon = settings["adaptation_near_optimal_ms"]
    flags = [near_optimal(row, references, tables, epsilon) for row in rows]
    result = {"seed": run["seed"], "longest_confirmed_suboptimal_episode": _longest(value is False for value in flags),
              "longest_possible_suboptimal_episode": _longest(value is not True for value in flags),
              "unknown_cost_rows": sum(value is None for value in flags), "epsilon_ms": epsilon,
              "adaptation": [], "fixed_comparators": {}}
    for name, field, byte_field in (("b0", "b0_hct_ms", "b0_server_bytes"), ("global_fixed_031", "global_fixed_hct_ms", "global_fixed_server_bytes")):
        if all(row.get(field) is not None for row in rows):
            costs = [finite(row[field], field) for row in rows]
            result["fixed_comparators"][name] = {"mean_hct_ms": statistics.mean(costs),
                                               "candidate_minus_fixed_ms": statistics.mean(finite(row["hct_ms"], "hct") - cost for row, cost in zip(rows, costs))}
        else:
            result["fixed_comparators"][name] = {"mean_hct_ms": None, "candidate_minus_fixed_ms": None}
        if all(row.get(byte_field) is not None and row.get("server_bytes") is not None for row in rows):
            byte_values = [finite(row[byte_field], byte_field) for row in rows]
            result["fixed_comparators"][name].update(mean_server_bytes=statistics.mean(byte_values),
                                                    candidate_minus_fixed_server_bytes=statistics.mean(finite(row["server_bytes"], "server_bytes") - value for row, value in zip(rows, byte_values)))
        else:
            result["fixed_comparators"][name].update(mean_server_bytes=None, candidate_minus_fixed_server_bytes=None)
    if scenario["family"] == "B5":
        changes = []
        index = 0
        previous = scenario["context"].get("cert_bytes")
        for phase in scenario["phases"]:
            cert = phase.get("cert_bytes", scenario["context"].get("cert_bytes"))
            if index and cert != previous:
                changes.append(index)
            previous = cert
            index += phase["length"]
        consecutive = settings["adaptation_consecutive"]
        result["adaptation"] = adaptation(rows, lambda row: flags[row["index"]], changes, consecutive)
        limit = protocol["thresholds"]["B5_adaptation_connections"]
        for item in result["adaptation"]:
            change, end = item["change_index"], item["end_index_exclusive"]
            statuses = []
            for lag in range(limit + 1):
                block = flags[change + lag:change + lag + consecutive]
                if change + lag + consecutive > end or len(block) < consecutive:
                    statuses.append(None)
                elif all(value is True for value in block):
                    statuses.append(True)
                elif any(value is False for value in block):
                    statuses.append(False)
                else:
                    statuses.append(None)
            item["threshold_status"] = "pass" if any(value is True for value in statuses) else "fail" if all(value is False for value in statuses) else "inconclusive"
            item["start_limit_new_observations"] = limit
    return result


def observed_summary(runs, field, confidence):
    values = [r["summary"].get(field) for r in runs]
    present = [finite(value, field) for value in values if value is not None]
    result = paired_summary(present, confidence) if len(present) == len(values) else paired_summary([], confidence)
    result.update(expected_seed_count=len(runs), observed_seed_count=len(present), complete=len(present) == len(values))
    result["method"] = "two-sided Student t on independent seed means"
    return result


def transition_summary(runs):
    grouped = collections.defaultdict(list)
    for run in runs:
        for item in run["summary"].get("transitions", []):
            grouped[(item["from_phase"], item["to_phase"])].append(item)
    results = []
    for phases, items in sorted(grouped.items()):
        detected = [item for item in items if item.get("detection_status") == "detected"]
        tracking = [item["tracking_delay"] for item in items if item.get("tracking_delay") is not None]
        results.append({"from_phase": phases[0], "to_phase": phases[1], "n": len(items),
                        "old_p": items[0]["old_p"], "new_p": items[0]["new_p"],
                        "detected_n": len(detected),
                        "mean_detection_start_among_detected": statistics.mean(item["detection_delay"] for item in detected) if detected else None,
                        "mean_detection_confirmation_among_detected": statistics.mean(item["detection_confirmed_delay"] for item in detected) if detected else None,
                        "mean_tracking_start_among_reached": statistics.mean(tracking) if tracking else None,
                        "detection_right_censored_n": sum(bool(item.get("detection_censored")) for item in items),
                        "prechange_unqualified_n": sum(item.get("detection_status") in {"already_on_new_side", "prechange_unsettled"} for item in items),
                        "tracking_censored_n": sum(bool(item.get("tracking_censored")) for item in items),
                        "scope": "means are conditional on detected/reached; censored and prechange-unqualified counts remain separate"})
    return results


def threshold_from_summary(summary, limit, **kwargs):
    return evaluate_threshold(summary["mean"], summary["lower"], summary["upper"], limit, **kwargs)


def _all_status(values):
    if any(value == "fail" for value in values):
        return "fail"
    return "pass" if values and all(value == "pass" for value in values) else "inconclusive"


def aggregate(raw, references, tables, protocol, trace_loader=load_trace):
    confidence = protocol["metrics"]["paired_confidence"]
    scenarios = {s["id"]: s for s in protocol["scenarios"]}
    groups = collections.defaultdict(list)
    identities = set()
    for run in raw:
        key = (run["generation"], run["variant"], run["scenario"])
        identity = key + (run["seed"],)
        if identity in identities or run["scenario"] not in scenarios:
            raise ValueError("duplicate or unknown raw run")
        identities.add(identity)
        groups[key].append(run)
    missing = set()
    outputs = []
    for key, runs in sorted(groups.items()):
        runs.sort(key=lambda row: row["seed"])
        if [r["seed"] for r in runs] != sorted(protocol["seeds"]):
            raise ValueError("every present group requires all protocol seeds")
        scenario = scenarios[key[2]]
        expected_n = sum(phase["length"] for phase in scenario["phases"])
        if any(run["n"] != expected_n for run in runs):
            raise ValueError("raw connection count differs from scenario")
        expected = expected_regret(runs, references, tables, confidence)
        missing.update(expected["missing"])
        observed = {field: observed_summary(runs, field, confidence) for field in (
            "mean_hct_ms", "failure_rate", "mean_extra_server_bytes", "mean_extra_first_flight_bytes",
            "mean_extra_client_first_flight_bytes", "p_bias_high_phase", "p_mae_high_phase",
            "alarm_rate_per_1000", "guard_alarm_fraction", "longest_unchanged_action_run")}
        traces = [trace_metrics(run, scenario, protocol, references, tables, trace_loader) for run in runs]
        fixed = {}
        for name in ("b0", "global_fixed_031"):
            valid = all(t["fixed_comparators"][name]["candidate_minus_fixed_ms"] is not None for t in traces)
            fixed[name] = {"status": "available" if valid else "missing_trace_fields",
                           "mean_hct": paired_summary([t["fixed_comparators"][name]["mean_hct_ms"] for t in traces], confidence) if valid else paired_summary([], confidence),
                           "candidate_minus_fixed": paired_summary([t["fixed_comparators"][name]["candidate_minus_fixed_ms"] for t in traces], confidence) if valid else paired_summary([], confidence),
                           "kind": "realized paired counterfactual diagnostic, not expected oracle regret"}
            byte_valid = all(t["fixed_comparators"][name]["candidate_minus_fixed_server_bytes"] is not None for t in traces)
            fixed[name]["mean_server_bytes"] = paired_summary([t["fixed_comparators"][name]["mean_server_bytes"] for t in traces], confidence) if byte_valid else paired_summary([], confidence)
            fixed[name]["candidate_minus_fixed_server_bytes"] = paired_summary([t["fixed_comparators"][name]["candidate_minus_fixed_server_bytes"] for t in traces], confidence) if byte_valid else paired_summary([], confidence)
            fixed[name]["mean_hct"]["method"] = "two-sided Student t on independent seed means"
            fixed[name]["mean_server_bytes"]["method"] = "two-sided Student t on independent seed means"
            if not byte_valid:
                missing.add(f"trace_fixed_byte_fields:{':'.join(key)}:{name}")
            if not valid:
                missing.add(f"trace_fixed_fields:{':'.join(key)}:{name}")
        gates = {}
        family = scenario["family"]
        if family in {"B1", "B2"}:
            gates["regret"] = threshold_from_summary(expected["seed_summary"], protocol["thresholds"][family + "_regret_ms"], mc_bound=expected["shared_mc_bound_ms"], selection_gap=expected["selection_gap_bound_ms"])
        if family == "B1":
            required = protocol["metrics"]["p_bias_high_phase_last_n"]
            bias = observed["p_bias_high_phase"]
            if any(run["summary"].get("p_bias_high_phase_n", 0) < required for run in runs):
                bias = paired_summary([], confidence)
            gates["p_bias"] = threshold_from_summary(bias, protocol["thresholds"]["B1_abs_p_bias"], absolute=True)
        if family == "B4":
            gates["server_extra_bytes"] = threshold_from_summary(observed["mean_extra_server_bytes"], protocol["thresholds"]["B4_extra_bytes"])
        if family == "B5":
            cases = [{"seed": item["seed"], **event} for item in traces for event in item["adaptation"]]
            status = _all_status([item["threshold_status"] for item in cases]) if len(cases) == len(runs) else "inconclusive"
            gates["adaptation"] = {"status": status, "rule": "all protocol seeds must start within the limit and confirm consecutive near-optimal decisions",
                                   "threshold": protocol["thresholds"]["B5_adaptation_connections"], "expected_seed_count": len(runs),
                                   "observed_cases": len(cases), "censored_count": sum(item["censored"] for item in cases),
                                   "confirmed_start_distribution": [item["start_new_observations"] for item in cases], "cases": cases}
        outputs.append({"generation": key[0], "variant": key[1], "scenario": key[2], "family": family,
                        "seeds": [r["seed"] for r in runs], "connections_per_seed": expected_n,
                        "expected_regret": expected, "observed": observed, "gates": gates,
                        "fixed_comparators": fixed, "trace_metrics_by_seed": traces,
                        "transition_summary": transition_summary(runs),
                        "transition_metrics_by_seed": [{"seed": r["seed"], "transitions": r["summary"].get("transitions", [])} for r in runs]})
    comparisons = []
    for key, runs in sorted(groups.items()):
        generation, variant, scenario = key
        baseline_key = ("v31", "full", scenario) if variant == "full" and generation != "v31" else (generation, "full", scenario) if variant != "full" else None
        if baseline_key is None or baseline_key not in groups:
            continue
        result = direct_comparison(runs, groups[baseline_key], tables, confidence)
        missing.update(result["missing"])
        result.update(candidate={"generation": generation, "variant": variant}, baseline={"generation": baseline_key[0], "variant": baseline_key[1]}, scenario=scenario,
                      kind="generation_regression" if variant == "full" else "diagnostic_variant_contrast")
        result["regression_gate"] = threshold_from_summary(result["seed_summary"], protocol["thresholds"]["max_regression_vs_v31_ms"], mc_bound=result["shared_mc_bound_ms"], inclusive=True)
        comparisons.append(result)
    absent_groups = []
    for generation in protocol.get("baseline_generations", ["v31", "v32"]):
        for scenario in scenarios:
            if (generation, "full", scenario) not in groups:
                absent_groups.append([generation, "full", scenario])
                missing.add(f"raw_group:{generation}:full:{scenario}")
    noninferiority = {}
    for generation in sorted({key[0] for key in groups if key[0] != "v31" and key[1] == "full"}):
        values = [item for item in comparisons if item["kind"] == "generation_regression" and item["candidate"]["generation"] == generation]
        complete = {item["scenario"] for item in values} == set(scenarios)
        status = _all_status([item["regression_gate"]["status"] for item in values])
        noninferiority[generation] = {"status": status if complete or status == "fail" else "inconclusive",
                                     "all_cells_present": complete, "cell_count": len(values), "required_cell_count": len(scenarios),
                                     "rule": "every scenario subcell must pass; no pooled cancellation"}
    return {"schema": "padfec.v33.benchmark_report/1", "status": "partial" if missing else "complete",
            "data_kind": "development_independent_world_simulation", "groups": outputs, "comparisons": comparisons,
            "noninferiority": noninferiority, "missing": sorted(missing), "missing_raw_groups": absent_groups,
            "inference_scope": {"seed_interval_confidence": confidence, "mc_context_or_job_family_confidence": protocol.get("oracle", {}).get("confidence"),
                                "combined_bounds_are_simultaneous_95_percent": False,
                                "note": "Seed Student t 95% intervals and MC normal-approximation 99% bounds are separately scoped to contexts/job families. Their combination is not a simultaneous overall 95% guarantee."},
            "scope": "MC intervals are heuristic; frozen-reference point estimates are not exact oracle regret; full and diagnostic variants are separate"}


def _number(value, digits=4):
    return "미확정" if value is None else f"{value:.{digits}f}"


def markdown(report):
    lines = ["# W1 벤치 보고서", "", f"상태: {report['status']}. complete는 필요한 입력 수집이 끝났다는 뜻이며 문턱 통과 여부는 각 판정 열에 있다. 개발용 독립 사건 세계 결과다. 원형 정책과 진단 변형을 합치지 않았다.", "",
             "기대 차이 점추정은 고정된 선택 기준 행동에 대한 값이다. 참 최적 행동 대비 후회에는 선택 오차가 남는다. 구간에는 seed 변동과 공통 MC 오차를 구분해 반영한다. MC 구간은 정규근사이며 실제 네트워크 정확도나 확증 결과를 뜻하지 않는다.", "",
             "seed 구간은 95%, MC 구간은 문맥 또는 action 작업 묶음별 99% 근사다. 이를 더한 보고 경계가 전체 동시 95%를 보장하지는 않는다.", ""]
    for variant in sorted({group["variant"] for group in report["groups"]}):
        lines.extend([f"## 변형 {variant}", "", "| 세대 | 셀 | 선택 기준 대비 ms | seed 95% 구간 | 공통 MC 폭 | 선택 오차 상한 | regret 판정 | 서버 추가 B |", "|---|---|---:|---|---:|---:|---|---:|"])
        for group in report["groups"]:
            if group["variant"] != variant:
                continue
            expected = group["expected_regret"]
            summary = expected["seed_summary"]
            interval = f"[{_number(summary['lower'])}, {_number(summary['upper'])}]"
            lines.append(f"| {group['generation']} | {group['scenario']} | {_number(summary['mean'])} | {interval} | {_number(expected['shared_mc_bound_ms'])} | {_number(expected['selection_gap_bound_ms'])} | {group['gates'].get('regret', {}).get('status', '해당 없음')} | {_number(group['observed']['mean_extra_server_bytes']['mean'], 1)} |")
        lines.append("")
    lines.extend(["## 관측 지표", "", "p 편향은 결정 전 추정치의 높은 손실 phase 마지막 구간 평균이다. 오경보 열은 변화 제외 구간의 새 행동 alarm 수/1000연결이며, s2c·지터에서의 원인별 손실 오탐률을 뜻하지 않는다.", "",
                  "| 세대/변형/셀 | p 편향 | p MAE | alarm/1000 | guard 점유 비율 | 최장 동일 행동 길이(seed 평균) |", "|---|---:|---:|---:|---:|---:|"])
    for group in report["groups"]:
        observed = group["observed"]
        lines.append(f"| {group['generation']}/{group['variant']}/{group['scenario']} | {_number(observed['p_bias_high_phase']['mean'], 6)} | {_number(observed['p_mae_high_phase']['mean'], 6)} | {_number(observed['alarm_rate_per_1000']['mean'], 2)} | {_number(observed['guard_alarm_fraction']['mean'])} | {_number(observed['longest_unchanged_action_run']['mean'], 1)} |")
    lines.extend(["", "## 변화 감지", "", "지연 평균의 분모는 실제 감지된 seed다. 변화 전부터 높은 추정치를 냈던 seed와 우측 검열을 별도 열에 남겼다.", "",
                  "| 세대/변형/셀 | p 변화 | 감지 seed | 시작 지연 | 확인 지연 | 우측 검열 | 변화 전 미자격 |", "|---|---|---:|---:|---:|---:|---:|"])
    for group in report["groups"]:
        for transition in group["transition_summary"]:
            lines.append(f"| {group['generation']}/{group['variant']}/{group['scenario']} | {transition['old_p']}→{transition['new_p']} | {transition['detected_n']}/{transition['n']} | {_number(transition['mean_detection_start_among_detected'], 1)} | {_number(transition['mean_detection_confirmation_among_detected'], 1)} | {transition['detection_right_censored_n']} | {transition['prechange_unqualified_n']} |")
    lines.extend(["## 직접 짝비교", "", "후보에서 기준을 뺀 값이다. 음수면 후보의 비용이 낮다. 기대비용 비교에서는 같은 oracle 항이 상쇄된다.", "",
                  "| 대조 | 셀 | 기대 차이 ms | 공통 MC 폭 | 악화 문턱 | 실현 HCT 차이(진단) |", "|---|---|---:|---:|---|---:|"])
    for item in report["comparisons"]:
        label = f"{item['candidate']['generation']}/{item['candidate']['variant']} vs {item['baseline']['generation']}/{item['baseline']['variant']}"
        lines.append(f"| {label} | {item['scenario']} | {_number(item['seed_summary']['mean'])} | {_number(item['shared_mc_bound_ms'])} | {item['regression_gate']['status']} | {_number(item['realized_hct_diagnostic']['mean'])} |")
    lines.extend(["", "## 개별 문턱과 적응", ""])
    for group in report["groups"]:
        gates = group["gates"]
        if gates:
            text = ", ".join(f"{name}={gate['status']}" for name, gate in gates.items())
            lines.append(f"- {group['generation']}/{group['variant']}/{group['scenario']}: {text}.")
        if "adaptation" in gates:
            gate = gates["adaptation"]
            lines.append(f"  전체 {gate['expected_seed_count']} seed가 2개 새 체인 관측 이내에 근접 최적 행동의 연속 구간을 시작해야 한다. 검열 {gate['censored_count']}개. 시작 관측 수 분포: {gate['confirmed_start_distribution']}.")
    lines.extend(["", "## 고정 팔 대조와 고착", "", "고정 팔 대조는 저장된 같은 난수 연결의 실현 HCT 진단이다. 단순히 행동이 같다는 이유로 고착이라고 부르지 않는다. 비용이 0.5 ms 초과로 열등한 것으로 확인된 연속 구간과 불확실 구간을 JSON에 seed별로 보존했다.", "",
                  "| 세대/변형/셀 | 정책−b0 ms | 정책−고정(0,3,1) ms | 정책−b0 서버 B | 정책−고정 서버 B | 확인된 최장 열등 구간(최대) | 비용 미확정 연결 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for group in report["groups"]:
        fixed = group["fixed_comparators"]
        traces = group["trace_metrics_by_seed"]
        lines.append(f"| {group['generation']}/{group['variant']}/{group['scenario']} | {_number(fixed['b0']['candidate_minus_fixed']['mean'])} | {_number(fixed['global_fixed_031']['candidate_minus_fixed']['mean'])} | {_number(fixed['b0']['candidate_minus_fixed_server_bytes']['mean'], 1)} | {_number(fixed['global_fixed_031']['candidate_minus_fixed_server_bytes']['mean'], 1)} | {max((r['longest_confirmed_suboptimal_episode'] for r in traces), default=0)} | {sum(r['unknown_cost_rows'] for r in traces)} |")
    if report["missing"]:
        lines.extend(["", "## 아직 없는 자료", "", "아래 항목 때문에 보고서는 partial이다. 기대 후회를 실현 HCT로 대체하지 않았다.", ""])
        lines.extend(f"- {value}" for value in report["missing"])
    provenance = report.get("provenance", {})
    lines.extend(["", "## 자료 식별", "", f"프로토콜 SHA-256: `{provenance.get('protocol_sha256', '합성자료')}`.",
                  f"보고 규칙 SHA-256: `{provenance.get('reporting_rules_sha256', '합성자료')}`.",
                  "W0의 bigcert 15% 자동 행동 꼬리·Initial 재전송 보정 한계는 그대로 남는다. 과거 model-world의 1.871, 2.284/3.012와 수치를 같게 만들려고 세계 조건을 바꾸지 않는다.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=ROOT / "g3/v33/bench_protocol.json")
    parser.add_argument("--rules", type=Path, default=RULES)
    parser.add_argument("--raw-dirs", type=Path, nargs="+", required=True)
    parser.add_argument("--oracle-dirs", type=Path, nargs="*", default=[])
    parser.add_argument("--action-dirs", type=Path, nargs="*", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args(argv)
    protocol, raw, refs, tables, provenance, pending = load_inputs(args.protocol, args.raw_dirs, args.oracle_dirs, args.action_dirs, args.rules)
    report = aggregate(raw, refs, tables, protocol)
    report["provenance"] = provenance
    report["missing"] = sorted(set(report["missing"]) | set(pending))
    report["status"] = "partial" if report["missing"] else "complete"
    if report["status"] != "complete" and not args.allow_pending:
        raise ValueError("report has pending inputs; use --allow-pending for an explicitly partial report")
    if args.out.resolve() == args.markdown.resolve() or args.out.exists() or args.markdown.exists():
        raise ValueError("output paths must be distinct new files")
    content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    prose = markdown(report)
    for path, value in ((args.out, content), (args.markdown, prose)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
    print(json.dumps({"status": report["status"], "groups": len(report["groups"]), "missing": len(report["missing"]), "out": str(args.out), "markdown": str(args.markdown)}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
