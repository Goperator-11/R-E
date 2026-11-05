import sys
sys.dont_write_bytecode = True
import argparse
import collections
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench_metrics, bench_report, oracle
from experiments.v33.worldsim import Action, World, load_params


RULES_PATH = ROOT / "docs" / "V33FIX_bench_rules.md"
RULE_BEGIN = "<!-- Z1-BEGIN -->"
RULE_END = "<!-- Z1-END -->"
RULE_SECTION_SHA256 = "124952bb4f4f287acafb9cb372d4decb58077e747eb53bbce7d85fe04672c2e0"
ZERO_VARIANCE = 1e-20
SEED_START = 860001
MC_CONFIDENCE = 0.99


def rule_section(path=RULES_PATH):
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    start, end = text.find(RULE_BEGIN), text.find(RULE_END)
    if start < 0 or end <= start or text.count(RULE_BEGIN) != 1 or text.count(RULE_END) != 1:
        raise ValueError("Z1 rule markers are missing or repeated")
    return text[start + len(RULE_BEGIN):end]


def rule_section_sha256(path=RULES_PATH):
    return hashlib.sha256(rule_section(path).encode("utf-8")).hexdigest()


def check_rule(path=RULES_PATH):
    actual = rule_section_sha256(path)
    if actual != RULE_SECTION_SHA256:
        raise ValueError("Z1 rule text differs from the registered section")
    return actual


def critical(family, confidence=MC_CONFIDENCE):
    if isinstance(family, bool) or not isinstance(family, int) or family < 1:
        raise ValueError("family must be a positive integer")
    if isinstance(confidence, bool) or not 0 < confidence < 1:
        raise ValueError("confidence must be inside (0,1)")
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence) / (2.0 * family))


def _action(value):
    value = tuple(value)
    if len(value) != 3 or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in value):
        raise ValueError("action must contain three nonnegative integers")
    return value


def sample_moments(context, action, seed, samples, world_params=None, mixture=None):
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise ValueError("samples must be an integer >= 2")
    action = _action(action)
    value_action = Action(*action)
    mix = oracle._Mixture(context, {"mixture": mixture} if mixture else {})
    world = World(load_params(world_params), seed=seed)
    n = failed = 0
    mean = m2 = 0.0
    low = high = None
    for connection in range(samples):
        row = world.sample(mix.at(seed, connection), value_action, connection=connection)
        value = row["hct"]
        n += 1
        delta = value - mean
        mean += delta / n
        m2 += delta * (value - mean)
        failed += not row["ok"]
        low = value if low is None else min(low, value)
        high = value if high is None else max(high, value)
    return {"action": list(action), "seed": seed, "n": n, "mean_hct_ms": mean,
            "variance_hct_ms2": m2 / (n - 1), "failed": failed,
            "min_hct_ms": low, "max_hct_ms": high,
            "params_sha256": world.params_sha256}


def interval(action_moments, reference_moments, family, confidence=MC_CONFIDENCE, paired_gap=None):
    n_a, n_r = action_moments["n"], reference_moments["n"]
    var_a, var_r = action_moments["variance_hct_ms2"], reference_moments["variance_hct_ms2"]
    difference = action_moments["mean_hct_ms"] - reference_moments["mean_hct_ms"]
    degenerate = var_a <= ZERO_VARIANCE or var_r <= ZERO_VARIANCE
    z = critical(family, confidence)
    se = None if degenerate else math.sqrt(var_a / n_a + var_r / n_r)
    lower = None if degenerate else difference - z * se
    upper = None if degenerate else difference + z * se
    effective = None
    if not degenerate and paired_gap is not None:
        effective = max(upper - paired_gap, paired_gap - lower)
    return {"status": "unresolved" if degenerate else "resolved",
            "unpaired_difference_ms": difference, "unpaired_se_ms": se,
            "critical": z, "confidence": confidence, "evaluation_family_size": family,
            "unpaired_interval_ms": None if degenerate else [lower, upper],
            "paired_gap_ms": paired_gap, "effective_gap_half_width_ms": effective}


def unpaired_difference(context, action, reference, action_seed, reference_seed, samples=131072,
                        family=1, confidence=MC_CONFIDENCE, world_params=None, mixture=None, paired_gap=None):
    action, reference = _action(action), _action(reference)
    if action == reference:
        raise ValueError("Z1 applies only to distinct actions")
    if action_seed == reference_seed:
        raise ValueError("Z1 requires different seeds for the two actions")
    a = sample_moments(context, action, action_seed, samples, world_params, mixture)
    r = sample_moments(context, reference, reference_seed, samples, world_params, mixture)
    result = interval(a, r, family, confidence, paired_gap)
    result.update({"action": a, "reference": r, "method": "Z1 independent-seed unpaired evaluation"})
    return result


def needs_resolution(table):
    distinct = bench_report.action_key(table["action"]) != bench_report.action_key(table["reference_action"])
    return bool(table.get("zero_observed_variance")) and distinct and table.get("gap_half_width_ms") is None


def direct_coefficients(candidate, baseline):
    ca = {r["seed"]: r for r in candidate}
    ba = {r["seed"]: r for r in baseline}
    if set(ca) != set(ba):
        raise ValueError("paired comparison seed sets differ")
    coefficients = collections.defaultdict(Fraction)
    for seed in sorted(ca):
        cw, bw = bench_report.weights(ca[seed]), bench_report.weights(ba[seed])
        if bench_report.context_weights(cw) != bench_report.context_weights(bw):
            raise ValueError("oracle does not cancel with unequal context weights")
        for key in cw.keys() | bw.keys():
            coefficients[key] += (cw.get(key, Fraction()) - bw.get(key, Fraction())) / len(ca)
    return dict(coefficients)


def weighted_bound(coefficients, tables, resolved):
    terms = []
    for key, value in coefficients.items():
        if value == 0:
            continue
        if key in resolved:
            width = resolved[key]
        elif key in tables:
            width = bench_report.gap_width(tables[key])
        else:
            width = None
        if width is None:
            return None
        terms.append(abs(float(value)) * width)
    return math.fsum(terms)


def rejudged_comparison(candidate, baseline, tables, resolved, threshold, confidence=0.95, inclusive=True):
    original = bench_report.direct_comparison(candidate, baseline, tables, confidence)
    coefficients = direct_coefficients(candidate, baseline)
    mc = weighted_bound(coefficients, tables, resolved)
    summary = original["seed_summary"]
    gate = bench_metrics.evaluate_threshold(summary["mean"], summary["lower"], summary["upper"], threshold,
                                            mc_bound=mc, selection_gap=0.0, inclusive=inclusive)
    used = sorted([key[0], list(key[1])] for key, value in coefficients.items() if value and key in resolved)
    return {"seed_summary": summary, "original_shared_mc_bound_ms": original["shared_mc_bound_ms"],
            "shared_mc_bound_ms": mc, "lower_bound_ms": gate["adjusted_lower"],
            "upper_bound_ms": gate["adjusted_upper"], "regression_gate": gate,
            "z1_resolved_terms": used,
            "nonzero_coefficients": sorted([key[0], list(key[1]), float(value)] for key, value in coefficients.items() if value),
            "realized_hct_diagnostic": original["realized_hct_diagnostic"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rule-sha")
    run = sub.add_parser("evaluate")
    run.add_argument("--context", required=True)
    run.add_argument("--action", type=int, nargs=3, required=True)
    run.add_argument("--reference", type=int, nargs=3, required=True)
    run.add_argument("--seeds", type=int, nargs=2, required=True)
    run.add_argument("--samples", type=int, default=131072)
    run.add_argument("--family", type=int, required=True)
    run.add_argument("--paired-gap", type=float)
    args = parser.parse_args(argv)
    if args.command == "rule-sha":
        print(rule_section_sha256())
        return 0
    check_rule()
    result = unpaired_difference(json.loads(args.context), args.action, args.reference, args.seeds[0], args.seeds[1],
                                 args.samples, args.family, paired_gap=args.paired_gap)
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
