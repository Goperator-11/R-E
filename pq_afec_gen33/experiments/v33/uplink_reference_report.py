import sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import argparse
import datetime as dt
import hashlib
import json
import random
import time
from dataclasses import replace

from experiments.v33.uplink_reference import (
    ModelReference, RACE_SCALES, RttObservation, UPLINK_SCENARIOS,
    estimate_uplink, select_minimax,
)
from padfec import policy, quantum
from padfec3 import decide3, layout, learn3


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contexts():
    result = []
    for name, S, rtt, ps in [
        ("bigcert", 18231, 50, (0.02, 0.15)),
        ("rtt200", 10992, 200, (0.02, 0.15)),
        ("c6000_r120", 7910, 120, (0.01, 0.08)),
        ("c12000_r120", 14072, 120, (0.01, 0.08)),
        ("p11_9000_r50", 10951, 50, (0.02, 0.15)),
    ]:
        need = learn3.bin_needed_s(S, quantum.bin_index(2560), 41.983)
        for p in ps:
            result.append(dict(source="auditor", name=name, S=S, rtt=rtt, p=p, n_need=need))
    for name, cert, rtt, ps in [
        ("bigcert", 16000, 50, (0.02, 0.15)),
        ("rtt200", 9000, 200, (0.02, 0.15)),
        ("c6000_r120", 6000, 120, (0.01, 0.08)),
        ("c12000_r120", 12000, 120, (0.01, 0.08)),
        ("p11_9000_r50", 9000, 50, (0, 0.02)),
    ]:
        S = cert + quantum.s0_at(quantum.bin_index(2560), policy.S0_BASE_MLKEM, 41.983)
        need = layout.n_need(cert, s0_base=policy.S0_BASE_MLKEM, c_pkt=41.983)
        for p in ps:
            result.append(dict(source="verifier", name=name, S=S, rtt=rtt, p=p, n_need=need))
    return result


def model_report():
    reference = ModelReference()
    rows = []
    for ctx in contexts():
        nominal = reference.cost_matrix([(ctx["p"], 1)], 2, 1280, ctx["S"], ctx["rtt"], 41.983)
        assert nominal["n_need"] == ctx["n_need"]
        direct = [[layout.evaluate(2, c["W_eff"], c["m"], c["lead"], ctx["p"],
                   ctx["rtt"], u, ctx["n_need"])["J"] for u in UPLINK_SCENARIOS]
                  for c in nominal["candidates"]]
        assert direct == nominal["cost_ms"]
        candidate = select_minimax(nominal["candidates"], direct)
        joint = reference.cost_matrix([(ctx["p"], 1)], 2, 1280, ctx["S"], ctx["rtt"],
                                      41.983, race_scales=RACE_SCALES)
        joint_choice = select_minimax(joint["candidates"], joint["cost_ms"])
        assert nominal["candidates"] == joint["candidates"]
        oracle = [min(row[j] for row in direct) for j in range(6)]
        audit_oracle = []
        for j in range(6):
            tied = [i for i in range(len(direct)) if direct[i][j] <= oracle[j] + 0.01]
            index = min(tied, key=lambda i: nominal["candidates"][i]["added"])
            audit_oracle.append(direct[index][j])
        verifier_regret = [[cost - audit_oracle[j] for j, cost in enumerate(row)] for row in direct]
        verifier_index = min(range(len(direct)), key=lambda i: max(verifier_regret[i]))
        wrong_u_index = min(range(len(direct)), key=lambda i: direct[i][0])
        audit_index = min(range(len(direct)), key=lambda i: (
            max(direct[i][j] - oracle[j] for j in range(6)),
            sum(direct[i][j] - oracle[j] for j in range(6))))
        rows.append({"context": ctx, "nominal_table": nominal, "nominal_choice": candidate,
                     "joint_table": joint, "joint_choice": joint_choice,
                     "faithful_auditor_action": nominal["candidates"][audit_index]["action"],
                     "faithful_verifier_action": nominal["candidates"][verifier_index]["action"],
                     "faithful_verifier_regret_ms": max(verifier_regret[verifier_index]),
                     "wrong_u0_action": nominal["candidates"][wrong_u_index]["action"],
                     "wrong_u0_worst_regret_ms": max(direct[wrong_u_index][j] - oracle[j] for j in range(6))})
    return rows


def estimator_report():
    result = []
    for rate in (2, 5, 10, 20, 50):
        for noise in (0, 0.25):
            for seed in range(31, 51):
                rng = random.Random(seed)
                observations = []
                trajectory = []
                first = None
                convergence = None
                consecutive = 0
                for i in range(64):
                    prefix = 1280 if i % 2 == 0 else 2611
                    rtt = 50 + 0.008 * prefix / rate + rng.gauss(0, noise)
                    observations.append(RttObservation("synthetic", prefix, rtt, True, True, True, True))
                    estimate = estimate_uplink(observations, "synthetic")
                    value = estimate["uplink_mbps"]
                    error = None if value is None else abs(value / rate - 1)
                    if value is not None and first is None:
                        first = i + 1
                    consecutive = consecutive + 1 if error is not None and error <= 0.1 else 0
                    if consecutive >= 5 and convergence is None:
                        convergence = i + 1
                    trajectory.append({"connection": i + 1, "uplink_mbps": value,
                                       "relative_error": error, "reason": estimate["reason"]})
                result.append({"true_rate_mbps": rate, "noise_sigma_ms": noise, "seed": seed,
                               "first_estimate_connection": first, "convergence_connection": convergence,
                               "observations": [vars(x) for x in observations], "trajectory": trajectory})
    base = [RttObservation("synthetic", 1280 if i % 2 == 0 else 2611,
                          50 + 0.004 * (1280 if i % 2 == 0 else 2611), True, True, True, True)
            for i in range(64)]
    stress = {
        "constant_bytes": estimate_uplink([replace(x, prefix_bytes=1280) for x in base], "synthetic"),
        "missing_evidence": estimate_uplink([replace(x, loss_free=False) for x in base], "synthetic"),
        "confounded_extra_slope": estimate_uplink([replace(x, min_rtt_ms=x.min_rtt_ms + 0.004*x.prefix_bytes)
                                                   for x in base], "synthetic"),
        "unlimited_flat": estimate_uplink([replace(x, min_rtt_ms=50) for x in base], "synthetic"),
    }
    return {"data_kind": "development_synthetic_estimator_diagnostic", "runs": result, "stress": stress}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    source_paths = [Path(__file__), ROOT / "experiments/v33/uplink_reference.py",
                    ROOT / "docs/O2 업링크 불확실성 참조 계약.md"]
    source_paths += sorted((ROOT / "padfec3").glob("*.py")) + sorted((ROOT / "padfec").glob("*.py"))
    before = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    timer = time.monotonic()
    results = {"started_kst": started, "models": model_report(), "estimator": estimator_report()}
    after = {str(p.relative_to(ROOT)): sha(p) for p in source_paths}
    results.update(seconds=time.monotonic()-timer, source_sha256=before,
                   source_sha256_after=after, unchanged=before == after)
    assert before == after
    with (args.out_dir / "result.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"models": len(results["models"]), "estimator_runs": len(results["estimator"]["runs"]),
                      "seconds": results["seconds"], "result_sha256": sha(args.out_dir / "result.json")}))


if __name__ == "__main__":
    main()
