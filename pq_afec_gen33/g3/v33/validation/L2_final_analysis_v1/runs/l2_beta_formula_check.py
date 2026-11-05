import sys
sys.dont_write_bytecode = True
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path


def moment(a, b, order):
    value = F(1)
    for index in range(order):
        value *= (a + index) / (a + b + index)
    return value


def check(a, b, q):
    s = a + b
    e = a / s
    other = (1 - q) / 2
    d = (1 - e) * q + e * other
    rho = e * other / d
    mean = (a + rho) / (s + 1)
    second = (a + 1) * (a + 2 * rho) / ((s + 1) * (s + 2))
    direct_mean = (q * moment(a, b, 1) + (other - q) * moment(a, b, 2)) / d
    direct_second = (q * moment(a, b, 2) + (other - q) * moment(a, b, 3)) / d
    assert mean == direct_mean and second == direct_second
    variance = second - mean * mean
    strength = mean * (1 - mean) / variance - 1
    projected_a, projected_b = mean * strength, (1 - mean) * strength
    assert projected_a > 0 and projected_b > 0
    assert moment(projected_a, projected_b, 1) == mean
    assert moment(projected_a, projected_b, 2) == second
    naive_variance = moment(a + rho, b + 1 - rho, 2) - mean * mean
    assert variance - naive_variance == rho * (1 - rho) / ((s + 1) * (s + 2))
    for epsilon in (F(1, 7), F(1, 3), F(2, 3)):
        density_ratio = (1 - rho) * s / b * (1 - epsilon) + rho * s / a * epsilon
        assert density_ratio == (q * (1 - epsilon) + other * epsilon) / d
    if q == F(1, 3):
        assert d == q and rho == e
        assert projected_a == a and projected_b == b
    if q == 1:
        assert rho == 0 and projected_a == a and projected_b == b + 1
    if q == 0:
        assert rho == 1 and projected_a == a + 1 and projected_b == b
    assert (1 - F(2, 3)) * q + F(2, 3) * other == F(1, 3)
    return {"a": str(a), "b": str(b), "q_observed_class": str(q), "rho": str(rho),
            "posterior_mean": str(mean), "posterior_variance": str(variance),
            "projected_a": str(projected_a), "projected_b": str(projected_b),
            "projected_strength_change": str(strength - s),
            "naive_variance_deficit": str(variance - naive_variance)}


def main():
    roots = (F(1, 10), F(1), F(2), F(10))
    bs = (F(1, 10), F(1), F(9), F(999))
    qs = (F(0), F(1, 10), F(1, 3), F(1, 2), F(9, 10), F(1))
    checked = [check(a, b, q) for a in roots for b in bs for q in qs]
    boundaries = [check(F(1), F(999), q) for q in (F(0), F(1, 3), F(1))]
    decrease = next((row for row in checked if F(row["projected_strength_change"]) < 0), None)
    result = {"schema": "padfec.v33.l2_beta_formula_check/1", "kind": "exact_fraction_algebra_no_policy_or_world_execution",
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "cases": len(checked), "all_exact_identities_pass": True,
              "checks": ["linear-likelihood posterior moments", "Beta-mixture density identity",
                         "two-moment projection", "naive update variance deficit", "q=1/3 no information",
                         "q=0 and q=1 conjugate limits", "epsilon=2/3 uniform observed channel"],
              "boundaries_beta_1_999": boundaries, "example_projection_strength_decrease": decrease}
    output = Path(__file__).with_name("L2_beta_formula_check.json")
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
