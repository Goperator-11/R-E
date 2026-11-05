import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def moment(a, b, order):
    result = F(1)
    for index in range(order):
        result *= (a + index) / (a + b + index)
    return result


def variance_check(a, b, rho):
    s, total = a + b, a + b + 1
    mean = (a + rho) / total
    second = (a + 1) * (a + 2 * rho) / (total * (total + 1))
    within = ((1 - rho) * (a / total) * ((b + 1) / total)
              + rho * ((a + 1) / total) * (b / total)) / (total + 1)
    between = rho * (1 - rho) / total / total
    variance = within + between
    assert variance == second - mean * mean and variance > 0
    naive = (a + rho) * (b + 1 - rho) / total / total / (total + 1)
    assert variance - naive == rho * (1 - rho) / total / (total + 1)
    other_mean = (b + (1 - rho)) / total
    assert mean + other_mean == 1
    strength = mean * other_mean / variance - 1
    assert strength > 0 and mean * strength > 0 and other_mean * strength > 0
    return variance


def marginal_check(a, b, prior, qs):
    grid = (F(1, 100), F(1, 10), F(1, 2))
    assert len(prior) == len(qs) == len(grid) and sum(prior) == 1
    e, e2, e3 = (moment(a, b, order) for order in (1, 2, 3))
    likelihood = [(1 - e) * q + e * (1 - q) / 2 for q in qs]
    z = sum(weight * value for weight, value in zip(prior, likelihood))
    p_post = [weight * value / z for weight, value in zip(prior, likelihood)]
    qbar = sum(weight * q for weight, q in zip(prior, qs))
    rbar = (1 - qbar) / 2
    rho = e * rbar / z
    assert z == (1 - e) * qbar + e * rbar
    mean = (a + rho) / (a + b + 1)
    second = (a + 1) * (a + 2 * rho) / ((a + b + 1) * (a + b + 2))
    exact_mean = sum(weight * (q * e + ((1 - q) / 2 - q) * e2) for weight, q in zip(prior, qs)) / z
    exact_second = sum(weight * (q * e2 + ((1 - q) / 2 - q) * e3) for weight, q in zip(prior, qs)) / z
    assert mean == exact_mean and second == exact_second and sum(p_post) == 1
    exact_cross = sum(g * weight * (q * e + ((1 - q) / 2 - q) * e2) for g, weight, q in zip(grid, prior, qs)) / z
    product_cross = sum(g * weight for g, weight in zip(grid, p_post)) * mean
    return {"a": str(a), "b": str(b), "prior": list(map(str, prior)), "observed_class_probabilities": list(map(str, qs)),
            "epsilon_mean": str(mean), "loss_epsilon_covariance": str(exact_cross - product_cross)}


def main():
    output = Path(__file__).with_name("L2_beta_marginal_precheck.json")
    if output.exists():
        raise FileExistsError(output)
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    shapes = ((F(1), F(999)), (F(1, 10), F(1, 10)), (F(20), F(3)), (F(1, 10**9), F(10**12)))
    rhos = (F(0), F(1, 10**12), F(1, 3), F(1, 2), F(999999999999, 10**12), F(1))
    for a, b in shapes:
        for rho in rhos:
            variance_check(a, b, rho)
    priors = ((F(1, 3), F(1, 3), F(1, 3)), (F(1, 2), F(1, 3), F(1, 6)))
    qsets = ((F(9, 10), F(1, 2), F(1, 20)), (F(1, 3),) * 3, (F(0), F(0), F(1)))
    rows = [marginal_check(a, b, prior, qs) for a, b in shapes for prior in priors for qs in qsets]
    correlated = next(row for row in rows if F(row["loss_epsilon_covariance"]) != 0)
    result = {"schema": "padfec.v33.l2_beta_marginal_precheck/1", "status": "pass",
              "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
              "script_sha256": script_sha, "data_kind": "exact_fraction_algebra_no_policy_or_world_execution",
              "variance_cases": len(shapes) * len(rhos), "joint_marginal_cases": len(rows),
              "scope": "One-observation marginals from an independent discrete loss and Beta epsilon prior, before weight floor; repeated product projection is approximate",
              "checks": ["positive within-plus-between variance equals exact second-minus-square",
                         "fractional-count variance deficit", "separate complementary mean",
                         "epsilon marginal from prior-averaged q", "loss marginal from prior epsilon mean"],
              "nonzero_posterior_correlation_example": correlated, "cases": rows}
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == script_sha
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
