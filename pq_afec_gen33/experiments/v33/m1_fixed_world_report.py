import sys
sys.dont_write_bytecode = True
import argparse
import math
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.v33 import bench, bench_m1_family as family, bench_m1_report as report
from experiments.v33 import m1_pool_validation as validation


def minimum(rows):
    chosen = min(rows, key=lambda r: (r["mean_hct_ms"], r["action"]))
    complete = all(row["half_width_ms"] is not None for row in rows)
    return {"action": chosen["action"], "mean_hct_ms": chosen["mean_hct_ms"],
            "lower_ms": min(r["mean_hct_ms"]-r["half_width_ms"] for r in rows) if complete else None,
            "upper_ms": min(r["mean_hct_ms"]+r["half_width_ms"] for r in rows) if complete else None,
            "scope": "minimum over prespecified fixed design only"}


def summarize(tables, plan, fixed):
    actions = fixed["actions"]
    z = NormalDist().inv_cdf(1-(1-plan["report_rules"]["mc_family_confidence"])/(4*len(tables)))
    contexts = {}
    rows = []
    for profile in ("off", "hold"):
        for p in plan["fixed_action_checks"]["p"]:
            wanted = dict(plan["fixed_action_checks"]["context"], p=p)
            selected = [(cid, spec) for cid, spec in bench.all_contexts(plan["protocols"][profile]).items()
                        if spec["context"] == wanted and not spec["mixture"]]
            if len(selected) != 1:
                raise ValueError("fixed exact context inventory")
            cid = selected[0][0]
            contexts[profile, p] = cid
            for action in actions:
                table = tables[cid, tuple(action)]
                rows.append({"profile": profile, "p": p, "context_id": cid, "action": action,
                             "mean_hct_ms": table["mean_hct_ms"], "half_width_ms": report.width(table, True, z),
                             "n": table["n"]})
    differences = []
    minima = []
    for p in plan["fixed_action_checks"]["p"]:
        by_profile = {profile: [r for r in rows if r["profile"] == profile and r["p"] == p]
                      for profile in ("off", "hold")}
        bounds = {profile: minimum(part) for profile, part in by_profile.items()}
        off, hold = bounds["off"], bounds["hold"]
        resolved = off["lower_ms"] is not None and hold["lower_ms"] is not None
        minima.append({"p": p, **bounds, "hold_minus_off_ms": hold["mean_hct_ms"]-off["mean_hct_ms"],
                       "lower_ms": hold["lower_ms"]-off["upper_ms"] if resolved else None,
                       "upper_ms": hold["upper_ms"]-off["lower_ms"] if resolved else None})
        for action in actions:
            parts = [next(r for r in by_profile[profile] if r["action"] == action) for profile in ("off", "hold")]
            delta = parts[1]["mean_hct_ms"]-parts[0]["mean_hct_ms"]
            bound = sum(r["half_width_ms"] for r in parts) if all(r["half_width_ms"] is not None for r in parts) else None
            model = next(r for r in fixed["rows"] if r["p"] == p and r["action"] == action)
            cap = model["nominal_deadline_bound_ms"]
            upper = delta+bound if bound is not None else None
            differences.append({"p": p, "action": action, "hold_minus_off_ms": delta,
                                "lower_ms": delta-bound if bound is not None else None, "upper_ms": upper,
                                "model_nominal_deadline_bound_ms": cap,
                                "independent_world_upper_within_nominal_bound": upper <= cap if upper is not None else None,
                                "model_hold_minus_off_ms": model["hold_minus_off_ms"]})
    return {"schema": "m1-fixed-world-report/1", "data_kind": "independent_event_world_MC",
            "action_count": len(actions), "fixed_rows": rows, "fixed_differences": differences,
            "finite_design_minima": minima, "mc_z": z, "mc_scalar_family_size": 2*len(tables),
            "new_adoption_gate": False, "global_optimum_claim": False,
            "model_first_flight_probability_source": str(family.collector.RUNS/"M1_fixed_checks_01.json"),
            "limitations": ["normal approximation", "finite fixed design, not continuous or global optimum",
                            "zero observed variance unresolved without new structural proof"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source_sha = bench.file_hash(__file__)
    saved, metadata, _ = family.execution_plan(args.family, args.sha256)
    plan = family.collector.load_plan(saved["collection_plan_path"])
    fixed_path = family.collector.RUNS/"M1_fixed_checks_01.json"
    fixed = family.read(fixed_path)
    with family.pool.exclusive_lock(args.pool/".pool.lock"):
        tables, provenance = validation.validate_pool_locked(args.pool, saved["manifest"], metadata)
        result = summarize(tables, plan, fixed)
        result.update(family_plan_sha256=args.sha256, source_sha256=source_sha,
                      model_source_sha256=bench.file_hash(fixed_path), pool_validation=provenance)
        family.equal(bench.file_hash(__file__), source_sha, "fixed summary source unchanged")
        bench.write_new(args.out, result)
    print(result["finite_design_minima"])


if __name__ == "__main__":
    main()
