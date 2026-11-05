import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
import math
from pathlib import Path

from scipy.stats import norm
import scipy

PATH = Path(__file__).resolve()
FAMILY_SHA = "fabdb4e3b0377c4c192f6c4b0c3c9e57b8f6a7dd3f098baa8cf02570cd949406"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def compare(actual, expected, label="root"):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(label + " keys")
        for key, value in expected.items():
            compare(actual[key], value, label + "." + key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(label + " list")
        for index, value in enumerate(expected):
            compare(actual[index], value, label + f"[{index}]")
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        if isinstance(actual, bool) or not isinstance(actual, (float, int)) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-10):
            raise ValueError(label + " number")
    elif actual != expected or type(actual) is not type(expected):
        raise ValueError(label + " value")


def design_minimum(rows):
    picked = sorted(rows, key=lambda row: (row["mean_hct_ms"], row["action"]))[0]
    lower = upper = None
    if all(row["half_width_ms"] is not None for row in rows):
        lower = min(row["mean_hct_ms"] - row["half_width_ms"] for row in rows)
        upper = min(row["mean_hct_ms"] + row["half_width_ms"] for row in rows)
    return dict(action=picked["action"], mean_hct_ms=picked["mean_hct_ms"], lower_ms=lower, upper_ms=upper,
                scope="minimum over prespecified fixed design only")


def context_for(plan, profile, probability):
    target = dict(plan["fixed_action_checks"]["context"], p=probability)
    found = set()
    for scenario in plan["protocols"][profile]["scenarios"]:
        for phase in scenario["phases"]:
            context = dict(scenario["context"], **{key: value for key, value in phase.items() if key != "length"})
            mixture = scenario.get("mixture", [])
            if context == target and not mixture:
                found.add(digest(dict(context=context, world_params=scenario["world_params"], mixture=mixture))[:20])
    if len(found) != 1:
        raise ValueError("fixed context identity")
    return found.pop()


def expected_values(plan, fixed, tables, family_size):
    z = float(norm.isf(.01 / (4 * family_size)))
    rows = []
    for profile in ("off", "hold"):
        for probability in plan["fixed_action_checks"]["p"]:
            cid = context_for(plan, profile, probability)
            for action in fixed["actions"]:
                table = tables[cid, tuple(action)]
                variance, n = table["variance_hct_ms2"], table["n"]
                half = z * math.sqrt(variance / n) if variance > 1e-20 and n >= 2 else None
                rows.append(dict(profile=profile, p=probability, context_id=cid, action=action,
                                 mean_hct_ms=table["mean_hct_ms"], half_width_ms=half, n=n))
    differences, minima = [], []
    for probability in plan["fixed_action_checks"]["p"]:
        parts = {profile: [r for r in rows if r["profile"] == profile and r["p"] == probability] for profile in ("off", "hold")}
        off, hold = [design_minimum(parts[profile]) for profile in ("off", "hold")]
        known = off["lower_ms"] is not None and hold["lower_ms"] is not None
        minima.append(dict(p=probability, off=off, hold=hold, hold_minus_off_ms=hold["mean_hct_ms"] - off["mean_hct_ms"],
                           lower_ms=hold["lower_ms"] - off["upper_ms"] if known else None,
                           upper_ms=hold["upper_ms"] - off["lower_ms"] if known else None))
        for action in fixed["actions"]:
            off, hold = [next(r for r in parts[profile] if r["action"] == action) for profile in ("off", "hold")]
            delta = hold["mean_hct_ms"] - off["mean_hct_ms"]
            known = off["half_width_ms"] is not None and hold["half_width_ms"] is not None
            width = off["half_width_ms"] + hold["half_width_ms"] if known else None
            model = next(r for r in fixed["rows"] if r["p"] == probability and r["action"] == action)
            upper = delta + width if known else None
            differences.append(dict(p=probability, action=action, hold_minus_off_ms=delta,
                lower_ms=delta - width if known else None, upper_ms=upper,
                model_nominal_deadline_bound_ms=model["nominal_deadline_bound_ms"],
                independent_world_upper_within_nominal_bound=upper <= model["nominal_deadline_bound_ms"] if known else None,
                model_hold_minus_off_ms=model["hold_minus_off_ms"]))
    return dict(fixed_rows=rows, fixed_differences=differences, finite_design_minima=minima, mc_z=z)


def validate(family_path, pool_path, model_path, report_path, independent_path):
    compare(sha(family_path), FAMILY_SHA, "frozen family")
    family, model, result, independent = map(read, (family_path, model_path, report_path, independent_path))
    compare(independent["status"], "pass", "main independent report")
    compare(independent["family_sha256"], FAMILY_SHA, "independent family")
    compare(result["family_plan_sha256"], FAMILY_SHA, "report family")
    compare(result["model_source_sha256"], sha(model_path), "model source")
    plan_path = family["collection_plan_path"]
    compare(sha(plan_path), family["collection_plan_sha256"], "collection plan")
    plan = read(plan_path)
    paths = dict(result["pool_validation"]["files_sha256"])
    paths.update(family["inputs_sha256"])
    for path, expected in paths.items():
        compare(sha(path), expected, "provenance " + path)
    jobs = family["manifest"]["jobs"]
    compare(sorted(p.stem for p in pool_path.glob("results/*.json")), sorted(j["job_id"] for j in jobs), "MC inventory")
    tables = {}
    for job in jobs:
        path = pool_path / "results" / (job["job_id"] + ".json")
        compare(sha(path), paths[str(path.resolve())], "bound MC result")
        table = read(path)
        for field, expected in (("n", 131072), ("validation_seed", 850001), ("action", job["action"]), ("evaluation_family_size", len(jobs))):
            compare(table[field], expected, "MC " + field)
        tables[job["context_id"], tuple(job["action"])] = table
    expected = expected_values(plan, model, tables, len(jobs))
    compare({key: result[key] for key in expected}, expected, "fixed values")
    for field, value in (("action_count", 16), ("mc_scalar_family_size", 2 * len(jobs)), ("new_adoption_gate", False), ("global_optimum_claim", False)):
        compare(result[field], value, field)
    return dict(schema="m1-independent-fixed/1", status="pass", fixed_rows=len(expected["fixed_rows"]),
        fixed_differences=len(expected["fixed_differences"]), finite_minima=len(expected["finite_design_minima"]),
        family_sha256=FAMILY_SHA, report_sha256=sha(report_path), main_independent_sha256=sha(independent_path),
        source_sha256=sha(PATH), scipy_version=scipy.__version__, normal_quantile="scipy.stats.norm.isf",
        performance_or_adoption_reinterpreted=False)


def main():
    parser = argparse.ArgumentParser()
    for name in ("family", "pool", "model", "report", "independent", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    initial = sha(PATH)
    result = validate(args.family, args.pool, args.model, args.report, args.independent)
    compare(sha(PATH), initial, "checker unchanged")
    with args.out.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False); f.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
