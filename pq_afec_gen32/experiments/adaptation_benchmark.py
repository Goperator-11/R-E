"""Deterministic development simulation, with no network or measured HCT input."""
import argparse
import copy
import functools
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from padfec import quantum
from padfec3 import decide3, layout, learn3

PROTOCOL_DEFAULT = ROOT / "g3" / "adaptation_benchmark_protocol.json"
VARIANTS = ("full", "frozen_loss", "skip_hazard_ablation")
SOURCES = ("experiments/adaptation_benchmark.py", "padfec3/learn3.py",
           "padfec3/decide3.py", "padfec3/layout.py", "padfec/quantum.py",
           "padfec/policy.py", "padfec/table.py",
           "g3/adaptation_benchmark_protocol.json")
NOTE = ("Development toy simulation under the policy's own cost model. "
        "No network measurements or real HCT observations are used. "
        "Ablation differences describe this model and protocol; they do not "
        "establish real performance or predictive accuracy.")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    return {name: sha256((ROOT / name).read_bytes()) for name in SOURCES}


def integer(name, value, minimum=1, maximum=10000):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError("%s must be an integer in [%d, %d]" % (name, minimum, maximum))
    return value


def number(name, value, minimum=0.0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be finite" % name)
    try:
        value = float(value)
    except OverflowError:
        raise ValueError("%s must be finite" % name) from None
    if not math.isfinite(value):
        raise ValueError("%s must be finite" % name)
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError("%s is outside its allowed range" % name)
    return float(value)


def check_protocol(protocol):
    p = copy.deepcopy(protocol)
    if p.get("schema") != "padfec3.adaptation_benchmark_protocol/toy-v1":
        raise ValueError("unsupported toy protocol schema")
    if p.get("variants") != list(VARIANTS):
        raise ValueError("protocol must specify full, frozen_loss and skip_hazard_ablation")
    integer("warmup_steps", p["warmup_steps"], maximum=1000)
    if not isinstance(p["seeds"], list) or not 1 <= len(p["seeds"]) <= 16:
        raise ValueError("protocol needs 1 to 16 seeds")
    for seed in p["seeds"]:
        integer("seed", seed, minimum=0, maximum=(1 << 63) - 1)
    if len(set(p["seeds"])) != len(p["seeds"]):
        raise ValueError("duplicate seeds")
    if not isinstance(p["conditions"], list) or not 1 <= len(p["conditions"]) <= 8:
        raise ValueError("protocol needs 1 to 8 conditions")
    names = set()
    for spec in p["conditions"]:
        if not isinstance(spec.get("id"), str) or not spec["id"] or spec["id"] in names:
            raise ValueError("condition ids must be unique non-empty strings")
        names.add(spec["id"])
        integer("k", spec["k"], maximum=layout.K_MAX)
        integer("W", spec["W"], minimum=1200, maximum=decide3.MAX_IPS)
        number("cert", spec["cert"])
        number("s0_base", spec["s0_base"], minimum=1.0)
        number("rtt_ms", spec["rtt_ms"], minimum=1.0)
        number("uplink_mbps", spec["uplink_mbps"])
        learn3.check_transport(spec["W"], spec["uplink_mbps"], spec["rtt_ms"], spec["c_pkt"])
        if not isinstance(spec["phases"], list) or not 1 <= len(spec["phases"]) <= 16:
            raise ValueError("condition needs 1 to 16 phases")
        phase_names, total = set(), 0
        for phase in spec["phases"]:
            if not isinstance(phase.get("id"), str) or not phase["id"] or phase["id"] in phase_names:
                raise ValueError("phase ids must be unique non-empty strings")
            phase_names.add(phase["id"])
            total += integer("phase steps", phase["steps"])
            number("p_true", phase["p_true"], maximum=0.30)
        if total > 10000:
            raise ValueError("toy condition exceeds 10000 comparison steps")
    canonical(p)
    return p


def true_context(spec):
    S = (spec["cert"] + spec["s0_base"]
         + quantum.bin_index(spec["k"] * spec["W"]) * spec["c_pkt"])
    need = layout.n_need(spec["cert"], s0_base=spec["s0_base"], c_pkt=spec["c_pkt"])
    return S, need


@functools.lru_cache(maxsize=4096)
def cost_catalogue(k, W, action, p, rtt, up, need):
    """Probability atoms whose expectation is layout.evaluate(...)[J]."""
    d, lead, trail = action
    m, w = lead + trail, W + d
    ev = layout.evaluate(k, w, m, lead, p, rtt, up, need, "v3")
    by_pattern, atoms = {}, []
    for rec in layout.outcomes(k, m, lead, w, p, up):
        options = []
        if rec["kind"] == "ok":
            for weight, credit in rec["branches"]:
                nr = layout.rtt_count(credit, need, ev["a_pre"])
                cost = rec["t_dec"] + rtt * nr + (ev["response_term_ms"] if nr == 2 else 0.0)
                options.append({"weight": weight, "synthetic_cost_ms": cost,
                                "initial_kind": "ok", "n_rtt": nr})
        else:
            kind = rec["kind"]
            if kind == "pto":
                cost = rtt + layout.T_PTO_MS + layout.tau(k * w, up)
            elif kind == "ptoS":
                cost = rec["t_last_o"] + ev["n_rtt_given_ok"] * rtt + layout.PTO_SAMPLED_MULT * rtt
            else:
                cost = (rec["t_last_o"] + ev["n_rtt_given_ok"] * rtt
                        + layout.T_ACK_SLOPE * rtt + layout.T_ACK_BASE_MS)
            options.append({"weight": 1.0, "synthetic_cost_ms": ev["round_mult"] * cost,
                            "initial_kind": kind, "n_rtt": None})
        by_pattern[rec["pattern"]] = options
        for option in options:
            atoms.append(dict(option, pattern=rec["pattern"],
                              probability=rec["pr"] * option["weight"]))
    mass = math.fsum(a["probability"] for a in atoms)
    expected = math.fsum(a["probability"] * a["synthetic_cost_ms"] for a in atoms)
    if not math.isclose(mass, 1.0, abs_tol=1e-12) or not math.isclose(expected, ev["J"], rel_tol=1e-12, abs_tol=1e-9):
        raise AssertionError("synthetic cost catalogue does not match the model")
    return {"by_pattern": by_pattern, "atoms": atoms, "expected_cost_ms": ev["J"]}


def catalogue(spec, action, p):
    _, need = true_context(spec)
    return cost_catalogue(spec["k"], spec["W"], tuple(action), p,
                          spec["rtt_ms"], spec["uplink_mbps"], need)


def noise_tape(seed, condition_id, segment, steps):
    key = sha256(canonical([seed, condition_id, segment]))
    rng = random.Random(int(key, 16))
    tape = [{"original": [rng.random() for _ in range(4)],
             "parity": [rng.random() for _ in range(4)], "race": rng.random()}
            for _ in range(steps)]
    return tape, sha256(canonical(tape))


def sample_cost(spec, action, p, noise):
    _, lead, trail = action
    values = (noise["parity"][:lead] + noise["original"][:spec["k"]]
              + noise["parity"][lead:lead + trail])
    pattern = tuple(int(value >= p) for value in values)
    options = catalogue(spec, action, p)["by_pattern"][pattern]
    cumulative = 0.0
    selected = options[-1]
    for option in options:
        cumulative += option["weight"]
        if noise["race"] < cumulative:
            selected = option
            break
    return dict(selected, pattern=list(pattern))


def observe_variant(st, res, sampled, spec, variant):
    if variant not in VARIANTS:
        raise ValueError("unknown ablation variant")
    old_post, old_w = copy.deepcopy(st.post), list(st.w)
    S, _ = true_context(spec)
    info = learn3.observe3(st, res["action"], sampled["synthetic_cost_ms"], True,
                           spec["k"], S, spec["rtt_ms"], W=spec["W"],
                           u_mbps=spec["uplink_mbps"], c_pkt=spec["c_pkt"],
                           later="v3", j_pred=res["j3_pred_pre_ms"])
    restore = variant == "frozen_loss" or (variant == "skip_hazard_ablation" and not info["updated"])
    if restore:
        st.post, st.w = old_post, old_w
    return info, {"posterior_update_committed": bool(info["updated"] and not restore),
                  "hazard_transition_committed": not restore}


def summary(rows):
    n = len(rows)
    return {"steps": n,
            "mean_expected_cost_ms": statistics.mean(r["true_expected_cost_ms"] for r in rows),
            "mean_synthetic_cost_ms": statistics.mean(r["synthetic_cost_ms"] for r in rows),
            "mean_expected_regret_ms": statistics.mean(r["expected_regret_ms"] for r in rows),
            "sum_expected_regret_ms": math.fsum(r["expected_regret_ms"] for r in rows),
            "posterior_updates_committed": sum(r["posterior_update_committed"] for r in rows),
            "hazard_transitions_committed": sum(r["hazard_transition_committed"] for r in rows),
            "decision_alarm_steps": sum(r["guard_alarm"] for r in rows),
            "observation_alarm_steps": sum(r["observation_alarm"] for r in rows),
            "reeval_steps": sum(r["reeval"] for r in rows)}


def paired_differences(all_rows):
    base = all_rows["full"]
    return {variant: {
        "steps": len(base),
        "mean_expected_cost_difference_ms": statistics.mean(
            row["true_expected_cost_ms"] - ref["true_expected_cost_ms"]
            for row, ref in zip(rows, base)),
        "mean_synthetic_cost_difference_ms": statistics.mean(
            row["synthetic_cost_ms"] - ref["synthetic_cost_ms"]
            for row, ref in zip(rows, base))}
        for variant, rows in all_rows.items() if variant != "full"}


def run_condition(spec, seed, warmup_steps, variant_order=VARIANTS):
    if set(variant_order) != set(VARIANTS) or len(variant_order) != len(VARIANTS):
        raise ValueError("variant order must contain every comparison arm once")
    S, _ = true_context(spec)
    candidates = decide3.candidates3(spec["k"], spec["W"], S, spec["c_pkt"])
    actions = [tuple(c["action"]) for c in candidates]
    warmup, warm_sha = noise_tape(seed, spec["id"], "shared_warmup", warmup_steps)
    st = learn3.new_state()
    st.k_hist, st.S_hist = [spec["k"]], [S]
    for noise in warmup:
        res = decide3.decide3(st, spec["W"], spec["uplink_mbps"], spec["rtt_ms"],
                              spec["c_pkt"], actions=actions, later="v3")
        sample = sample_cost(spec, res["action"], spec["phases"][0]["p_true"], noise)
        observe_variant(st, res, sample, spec, "full")
    initial_sha = sha256(canonical(st.to_json()))
    phases = [phase for phase in spec["phases"] for _ in range(phase["steps"])]
    tape, tape_sha = noise_tape(seed, spec["id"], "comparison", len(phases))
    true_costs = {p: {a: catalogue(spec, a, p)["expected_cost_ms"] for a in actions}
                  for p in {phase["p_true"] for phase in spec["phases"]}}
    oracles = {p: min(costs.values()) for p, costs in true_costs.items()}
    rows_by_variant, outputs = {}, {}
    for variant in variant_order:
        state, rows = copy.deepcopy(st), []
        for step, (phase, noise) in enumerate(zip(phases, tape)):
            res = decide3.decide3(state, spec["W"], spec["uplink_mbps"], spec["rtt_ms"],
                                  spec["c_pkt"], actions=actions, later="v3")
            action = tuple(res["action"])
            expected = true_costs[phase["p_true"]][action]
            oracle = oracles[phase["p_true"]]
            sampled = sample_cost(spec, action, phase["p_true"], noise)
            info, effective = observe_variant(state, res, sampled, spec, variant)
            rows.append({"step": step, "phase": phase["id"], "p_true": phase["p_true"],
                         "action": list(action), "true_expected_cost_ms": expected,
                         "oracle_min_expected_cost_ms": oracle, "expected_regret_ms": expected - oracle,
                         "synthetic_cost_ms": sampled["synthetic_cost_ms"],
                         "initial_kind": sampled["initial_kind"],
                         "decision_expected_j_ms": res["j3_pred_pre_ms"],
                         "p_mean_before": res["p_mean"],
                         "p_mean_after": learn3.post_mean(learn3.combined(state)),
                         "guard_alarm": res["guard_alarm"], "reeval": res["reeval"],
                         "observation_alarm": info["alarmed"], "observation_event": info["y"],
                         "learner_likelihood_evaluated": info["updated"], "obs_skip": info["skip"],
                         **effective})
        rows_by_variant[variant] = rows
        outputs[variant] = {"summary": summary(rows),
                            "by_phase": {p["id"]: summary([r for r in rows if r["phase"] == p["id"]])
                                         for p in spec["phases"]},
                            "learner_stats_after": dict(state.stats), "rows": rows}
    return {"condition": spec["id"], "seed": seed,
            "warmup": {"steps": warmup_steps, "excluded_from_comparison": True,
                       "initial_state_sha256": initial_sha, "noise_tape_sha256": warm_sha},
            "noise_tape_sha256": tape_sha, "candidate_actions": [list(a) for a in actions],
            "oracle_rule": "strict minimum true-p model J over the common candidate set; no J_TIE",
            "variants": {v: outputs[v] for v in VARIANTS},
            "paired_differences": paired_differences(rows_by_variant),
            "paired_differences_by_phase": {p["id"]: paired_differences(
                {v: [r for r in rows_by_variant[v] if r["phase"] == p["id"]] for v in VARIANTS})
                for p in spec["phases"]}}


def run_benchmark(protocol, protocol_path=None):
    resolved = check_protocol(protocol)
    hashes = source_hashes()
    input_sha = sha256(Path(protocol_path).read_bytes()) if protocol_path else None
    cases = [run_condition(spec, seed, resolved["warmup_steps"])
             for spec in resolved["conditions"] for seed in resolved["seeds"]]
    if source_hashes() != hashes:
        raise RuntimeError("benchmark sources changed during the simulation")
    if protocol_path and sha256(Path(protocol_path).read_bytes()) != input_sha:
        raise RuntimeError("protocol input changed during the simulation")
    return {"schema": "padfec3.adaptation_benchmark/synthetic-v1",
            "label": "development synthetic toy comparison", "synthetic": True,
            "confirmatory": False, "network_measurements": 0, "note": NOTE,
            "policy_version": learn3.POLICY_VERSION, "protocol": resolved,
            "protocol_sha256": sha256(canonical(resolved)),
            "protocol_input_sha256": input_sha,
            "source_sha256": hashes, "seeds": resolved["seeds"],
            "noise_coupling": "four semantic original uniforms, four parity uniforms and one race uniform per step",
            "environment": "fixed known k, server bytes and RTT; costs come from the policy model",
            "model_mode": "v3",
            "ablation_rule": "frozen_loss restores only post and w after every observation; skip_hazard_ablation restores them only when no likelihood update occurred; histories, guard and decision counters advance in every arm",
            "observation_rule": "all modeled connections are ok=True; initial failure uses the model recovery cost",
            "paired_difference_rule": "ablation minus full; descriptive model differences without tests or confidence intervals",
            "learner_stats_rule": "learner counters include shared warmup and discarded updates; committed counters cover comparison steps only",
            "cases": cases}


def same_path(left, right):
    if os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve())):
        return True
    return Path(left).exists() and Path(right).exists() and os.path.samefile(left, right)


def atomic_write(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=path.name + ".", suffix=".tmp",
                                         dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            json.dump(doc, f, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=NOTE)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_DEFAULT)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, action="append", help="replace protocol seeds; repeat to add seeds")
    args = parser.parse_args(argv)
    protected = [args.protocol] + [ROOT / name for name in SOURCES]
    if any(same_path(args.out, path) for path in protected):
        parser.error("output must not overwrite protocol input or benchmark sources")
    try:
        protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
        if args.seed is not None:
            protocol["seeds"] = args.seed
        doc = run_benchmark(protocol, args.protocol)
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    atomic_write(args.out, doc)
    print("development synthetic toy comparison: %d cases; no network measurements" % len(doc["cases"]))
    print(NOTE)
    print("wrote %s" % args.out)
    return doc


if __name__ == "__main__":
    main()
