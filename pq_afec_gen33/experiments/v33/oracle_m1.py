import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random
from statistics import NormalDist
import tempfile
import time

from .worldsim_m1 import Action, World, WorldContext, load_params


SCHEMA = "padfec.world_oracle/v1"
CERTIFIED_WORLD_SHA256 = "8f86bb520af2d18d03f9188f14104bc988af680665f705dbe0121b83d391e374"
CERTIFIED_PARAMS_SHA256 = "f46153ee09566cd2a0e4b56781edb5734cdbfe98db541d7d6bfec8236dad0f55"
DEFAULT_SPEC = {
    "stage_sizes": [64, 256, 1024, 4096, 16384],
    "selection_seed": 840001,
    "validation_seed": 850001,
    "validation_samples": 131072,
    "indifference_ms": 0.025,
    "confidence": 0.99,
    "min_elimination_samples": 1024,
    "max_parity": 4,
    "chunk_size": 32,
    "structural_certificates": True,
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes():
    directory = Path(__file__).resolve().parent
    return {name: _file_hash(directory / name) for name in ("oracle_m1.py", "worldsim_m1.py", "worldparams_m1.json", "world_receiver_m1.py")}


def _derive_seed(seed, label):
    return int.from_bytes(hashlib.blake2b(f"{seed}:{label}".encode(), digest_size=16).digest(), "big")


def _action(value):
    if isinstance(value, Action):
        if value.order is not None:
            raise ValueError("oracle universe supports the standard packet order only")
        value = (value.delta, value.lead, value.trailing)
    elif isinstance(value, dict):
        value = (value.get("delta", 0), value.get("lead", 0), value.get("trailing", value.get("T", 0)))
    value = tuple(value)
    if len(value) != 3 or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in value):
        raise ValueError("action must contain three nonnegative integers")
    return value


def _key(action):
    return ",".join(str(x) for x in action)


def _context(value):
    value = copy.deepcopy(value)
    for name in ("server_dgram_sizes", "cert_mix"):
        if name in value:
            value[name] = tuple(value[name])
    if "cert_schedule" in value:
        value["cert_schedule"] = tuple(tuple(row) for row in value["cert_schedule"])
    context = WorldContext(**value)
    if context.cert_schedule:
        raise ValueError("oracle context must be stationary; split deterministic schedule phases")
    return context


def _spec(value):
    value = copy.deepcopy(value or {})
    if "m_max" in value:
        if "max_parity" in value and value["max_parity"] != value["m_max"]:
            raise ValueError("m_max and max_parity disagree")
        value["max_parity"] = value.pop("m_max")
    result = copy.deepcopy(DEFAULT_SPEC)
    result.update(value)
    if "time_budget_seconds" in result:
        result["time_limit_seconds"] = result.pop("time_budget_seconds")
    stages = result["stage_sizes"]
    if not isinstance(stages, list) or not stages or any(isinstance(n, bool) or not isinstance(n, int) or n < 2 for n in stages):
        raise ValueError("stage_sizes must contain integers >= 2")
    if any(a >= b for a, b in zip(stages, stages[1:])):
        raise ValueError("stage_sizes must increase")
    for name in ("validation_samples", "min_elimination_samples", "chunk_size"):
        n = result[name]
        if isinstance(n, bool) or not isinstance(n, int) or n < 2:
            raise ValueError(f"{name} must be an integer >= 2")
    if isinstance(result["max_parity"], bool) or not isinstance(result["max_parity"], int) or result["max_parity"] < 0:
        raise ValueError("max_parity must be a nonnegative integer")
    for name in ("original_max_bytes", "wire_max_bytes"):
        if name in result and (isinstance(result[name], bool) or not isinstance(result[name], int) or result[name] < 1):
            raise ValueError(f"{name} must be a positive integer")
    if not 0 < result["confidence"] < 1 or result["indifference_ms"] < 0:
        raise ValueError("invalid confidence or indifference")
    if result["selection_seed"] == result["validation_seed"]:
        raise ValueError("selection and validation seeds must differ")
    return result


class _Mixture:
    def __init__(self, context, spec):
        source = spec.get("mixture") or [{"weight": 1.0, "context": {}}]
        total = sum(row["weight"] for row in source)
        if not math.isfinite(total) or total <= 0 or any(not math.isfinite(row["weight"]) or row["weight"] <= 0 for row in source):
            raise ValueError("mixture weights must be finite and positive")
        self.entries = []
        for row in source:
            value = copy.deepcopy(context)
            value.update(row.get("context", {}))
            self.entries.append((row["weight"] / total, _context(value)))
        self.description = [{"weight": weight, "context": vars(ctx)} for weight, ctx in self.entries]

    def at(self, seed, connection):
        if len(self.entries) == 1:
            return self.entries[0][1]
        value = random.Random(_derive_seed(seed, f"mixture:{connection}")).random()
        cumulative = 0.0
        for weight, context in self.entries:
            cumulative += weight
            if value < cumulative:
                return context
        return self.entries[-1][1]


def action_universe(context, world_params=None, spec=None):
    spec = _spec(spec)
    params = load_params(world_params)
    mixture = _Mixture(context, spec)
    original_max = min(params["server"]["decoder_max_datagram_bytes"], spec.get("original_max_bytes", params["server"]["decoder_max_datagram_bytes"]))
    wire_max = min(params["server"]["max_wire_datagram_bytes"], spec.get("wire_max_bytes", params["server"]["max_wire_datagram_bytes"]))
    original_max = min(original_max, wire_max)
    maximum = min(original_max - ctx.w for _, ctx in mixture.entries)
    if maximum < 0:
        raise ValueError("base original exceeds the world decoder clamp")
    actions = []
    for delta in range(maximum + 1):
        for m in range(spec["max_parity"] + 1):
            valid = all(m == 0 or ctx.w + delta + params["fec"]["parity_overhead_base"] + params["fec"]["parity_overhead_per_k"] * ctx.k <= wire_max for _, ctx in mixture.entries)
            if valid:
                actions.extend((delta, lead, m - lead) for lead in range(m + 1))
    if not actions:
        raise ValueError("empty action universe")
    return actions


def _wire_key(action, mixture, params):
    delta, lead, trailing = action
    size = sum(weight * (ctx.k * (ctx.w + delta) + (lead + trailing) * (ctx.w + delta + params["fec"]["parity_overhead_base"] + params["fec"]["parity_overhead_per_k"] * ctx.k)) for weight, ctx in mixture.entries)
    return size, lead, delta, trailing


def _new_moments():
    return {"n": 0, "mean_gap": 0.0, "m2_gap": 0.0, "mean_hct": 0.0,
            "m2_hct": 0.0, "mean_reference_hct": 0.0, "m2_reference_hct": 0.0,
            "co_hct": 0.0, "mean_server_bytes": 0.0, "mean_reference_server_bytes": 0.0,
            "mean_client_bytes": 0.0, "mean_reference_client_bytes": 0.0,
            "failed": 0, "reference_failed": 0, "min_gap": None, "max_gap": None}


def _update(stats, row, reference):
    a, b = row["hct"], reference["hct"]
    gap = a - b
    stats["n"] += 1
    n = stats["n"]
    da, db, dg = a - stats["mean_hct"], b - stats["mean_reference_hct"], gap - stats["mean_gap"]
    stats["mean_hct"] += da / n
    stats["mean_reference_hct"] += db / n
    stats["mean_gap"] += dg / n
    stats["m2_hct"] += da * (a - stats["mean_hct"])
    stats["m2_reference_hct"] += db * (b - stats["mean_reference_hct"])
    stats["m2_gap"] += dg * (gap - stats["mean_gap"])
    stats["co_hct"] += da * (b - stats["mean_reference_hct"])
    for key, value in (("mean_server_bytes", row["server_counted_uplink_bytes"]),
                       ("mean_reference_server_bytes", reference["server_counted_uplink_bytes"]),
                       ("mean_client_bytes", row["client_total_uplink_bytes"]),
                       ("mean_reference_client_bytes", reference["client_total_uplink_bytes"])):
        stats[key] += (value - stats[key]) / n
    stats["failed"] += not row["ok"]
    stats["reference_failed"] += not reference["ok"]
    stats["min_gap"] = gap if stats["min_gap"] is None else min(stats["min_gap"], gap)
    stats["max_gap"] = gap if stats["max_gap"] is None else max(stats["max_gap"], gap)


def _summary(stats, z):
    n = stats["n"]
    variance = max(0.0, stats["m2_gap"] / (n - 1)) if n > 1 else 0.0
    se = math.sqrt(variance / n) if n else None
    width = z * se if se is not None else None
    return {"n": n, "mean_gap_ms": stats["mean_gap"], "gap_variance_ms2": variance,
            "gap_se_ms": se, "gap_half_width_ms": width,
            "gap_ci_ms": [stats["mean_gap"] - width, stats["mean_gap"] + width] if width is not None else None,
            "gap_sum_ms": stats["mean_gap"] * n,
            "mean_hct_ms": stats["mean_hct"], "reference_mean_hct_ms": stats["mean_reference_hct"],
            "variance_hct_ms2": stats["m2_hct"] / (n - 1) if n > 1 else 0.0,
            "reference_variance_hct_ms2": stats["m2_reference_hct"] / (n - 1) if n > 1 else 0.0,
            "covariance_hct_ms2": stats["co_hct"] / (n - 1) if n > 1 else 0.0,
            "mean_server_counted_uplink_bytes": stats["mean_server_bytes"],
            "reference_mean_server_counted_uplink_bytes": stats["mean_reference_server_bytes"],
            "mean_client_total_uplink_bytes": stats["mean_client_bytes"],
            "reference_mean_client_total_uplink_bytes": stats["mean_reference_client_bytes"],
            "failed": stats["failed"], "reference_failed": stats["reference_failed"],
            "min_gap_ms": stats["min_gap"], "max_gap_ms": stats["max_gap"],
            "zero_observed_variance": variance <= 1e-20,
            "confidence_method": "normal approximation for paired differences; not a distribution-free bound"}


def _semantic_spec(spec):
    excluded = {"cache_dir", "checkpoint_path", "time_limit_seconds", "max_evaluations", "chunk_size"}
    return {key: value for key, value in spec.items() if key not in excluded}


class _Run:
    def __init__(self, identity, spec, progress):
        self.identity = identity
        self.spec = spec
        self.progress = progress
        self.started = time.monotonic()
        self.evaluations = 0
        self.cancelled = False
        self.path = None
        if spec.get("checkpoint_path"):
            self.path = Path(spec["checkpoint_path"]).resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif spec.get("cache_dir"):
            directory = Path(spec["cache_dir"]).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"{identity}.json"

    def load(self):
        if self.path is None or not self.path.exists():
            return None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema") != SCHEMA or value.get("identity") != self.identity:
            raise ValueError("checkpoint identity mismatch")
        return value

    def save(self, state):
        state["schema"] = SCHEMA
        state["identity"] = self.identity
        if self.path is not None:
            data = _canonical(state)
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.path.parent, prefix=self.identity + ".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)

    def notify(self, value):
        value = dict(value)
        elapsed = time.monotonic() - self.started
        value.update({"identity": self.identity, "elapsed_seconds_this_call": elapsed,
                      "world_evaluations_this_call": self.evaluations,
                      "world_evaluations_per_second": self.evaluations / elapsed if elapsed > 0 else None})
        if self.progress is not None and self.progress(value) is False:
            self.cancelled = True

    def should_stop(self):
        if self.cancelled:
            return "caller_cancelled"
        if self.spec.get("time_limit_seconds") is not None and time.monotonic() - self.started >= self.spec["time_limit_seconds"]:
            return "time_limit"
        if self.spec.get("max_evaluations") is not None and self.evaluations >= self.spec["max_evaluations"]:
            return "evaluation_budget"
        return None


def _stream(state, actions, reference, count, seed, mixture, params, run, phase):
    world = World(params, seed=seed)
    converted = {action: Action(*action) for action in actions}
    reference_value = Action(*reference)
    records = state.setdefault("records", {})
    for action in actions:
        records.setdefault(_key(action), _new_moments())
    completed = state.get("completed_connections", 0)
    while completed < count:
        reason = run.should_stop()
        if reason:
            state["pause_reason"] = reason
            run.save(state)
            return False
        end = min(count, completed + run.spec["chunk_size"])
        for connection in range(completed, end):
            context = mixture.at(seed, connection)
            ref = world.sample(context, reference_value, connection=connection)
            run.evaluations += 1
            for action in actions:
                row = ref if action == reference else world.sample(context, converted[action], connection=connection)
                run.evaluations += action != reference
                _update(records[_key(action)], row, ref)
        completed = end
        state["completed_connections"] = completed
        state["total_world_evaluations"] = state.get("total_world_evaluations", 0) + (end - state.get("last_checkpoint_connections", 0)) * (len(actions) + (reference not in actions))
        state["last_checkpoint_connections"] = completed
        run.save(state)
        remaining = (count - completed) * (len(actions) + (reference not in actions))
        run.notify({"phase": phase, "stage_index": state.get("stage_index"), "connections": completed,
                    "target_connections": count, "candidate_count": len(actions),
                    "remaining_world_evaluations_in_phase": remaining})
    return True


def _race_moments(params):
    if not params["features"]["trailing_race"]:
        return 0.0, 0.0
    cfg = params["race"]
    mean = second = 0.0
    for lo, hi, qlo, qhi in zip(cfg["delay_ms"], cfg["delay_ms"][1:], cfg["survival_probability"], cfg["survival_probability"][1:]):
        slope = (qhi - qlo) / (hi - lo)
        mean += (hi - lo) * (qlo + qhi) / 2.0
        second += 2.0 * (qlo * (hi * hi - lo * lo) / 2.0 + slope * ((hi ** 3 - lo ** 3) / 3.0 - lo * (hi * hi - lo * lo) / 2.0))
    factor = cfg["jitter_factor"]
    return mean * factor, max(0.0, second - mean * mean) * factor * factor


def _certificate(mixture, params, sources, spec):
    if not spec["structural_certificates"] or len(mixture.entries) != 1 or spec["max_parity"] > 4:
        return None
    if sources["worldsim_m1.py"] != CERTIFIED_WORLD_SHA256 or World(params).params_sha256 != CERTIFIED_PARAMS_SHA256:
        return None
    context = mixture.entries[0][1]
    if context.p != 0 or context.s2c_loss != 0 or context.w != 1280 or context.rtt_ms != 50:
        return None
    if context.retry or context.token or context.server_bytes or context.server_dgram_sizes or context.n_need is not None or context.cert_mix or context.cert_schedule:
        return None
    if context.jitter_mean_ms not in (None, 0) or context.c_proc_ms not in (None, 2.6):
        return None
    if context.k == 2 and context.cert_bytes == 2955 and context.uplink_mbps in (0, 2):
        return {"id": "B3_no_loss_originals_already_fund_first_flight", "action": (0, 0, 0),
                "server_first_flight_bytes": 4595,
                "proof": "All originals arrive, 4595 server bytes fit the 3*2560 credit even after the 41-byte ACK. Lead or padding cannot advance ClientHello completion. b0 minimizes serialization and wire bytes. All permitted actions finish before the 200ms PTO."}
    if context.k == 1 and context.cert_bytes == 4032 and context.uplink_mbps == 0:
        return {"id": "B4_no_loss_one_byte_crosses_granular_boundary", "action": (1, 0, 0),
                "server_first_flight_bytes": 4583,
                "proof": "Four server datagrams require credit>1280 under the granular presend test. delta=1 crosses this bound, all zero-rate packets arrive before server_ready, and 1281 original bytes cost less than every parity action. b0 needs a second RTT; all supported actions finish before PTO."}
    return None


def _base_report(context, params, spec, sources, universe, mixture):
    return {"schema": SCHEMA, "context": context, "mixture": mixture.description,
            "universe_count": len(universe), "universe_sha256": _digest(universe),
            "universe_definition": "all integer deltas through the original clamp, every lead+trailing<=max_parity, wire-valid parity; truncated parity retained",
            "max_parity": spec["max_parity"], "source_hashes": sources,
            "world_params_sha256": World(params).params_sha256,
            "spec": _semantic_spec(spec), "model_kind": "independent_event_world"}


def build_oracle(context, world_params=None, spec=None, progress=None):
    spec = _spec(spec)
    params = load_params(world_params)
    if params["channel"]["preserve_ge_across_connections"]:
        raise ValueError("stationary action oracle does not support action-dependent persistent GE state")
    mixture = _Mixture(context, spec)
    universe = action_universe(context, params, spec)
    sources = _source_hashes()
    base = _base_report(context, params, spec, sources, universe, mixture)
    certificate = _certificate(mixture, params, sources, spec)
    if certificate is not None and tuple(certificate["action"]) in universe:
        certificate["action"] = list(certificate["action"])
        mean_delay, variance_delay = _race_moments(params)
        ctx = mixture.entries[0][1]
        action = Action(*certificate["action"])
        row = World(params, seed=spec["validation_seed"]).sample(ctx, action, overrides={"decision_delay_ms": 0.0, "jitter_ms": 0.0})
        return base | {"status": "complete", "method": "structural_zero_loss_certificate",
                       "approximate": False, "chosen_action": certificate["action"],
                       "chosen_mean_hct_ms": row["hct"] + mean_delay,
                       "chosen_variance_hct_ms2": variance_delay,
                       "oracle_gap_upper_ms": 0.0, "selection_gap_upper_ms": 0.0,
                       "confidence": None, "stage_results": [], "uncertainty_resolved": True,
                       "certificate": certificate, "validation_samples": 0,
                       "note": "Exact only within the pinned event-world source and the narrowly specified zero-loss context."}
    identity = _digest({"kind": "build_oracle", "base": base})
    run = _Run(identity, spec, progress)
    state = run.load()
    if state is not None and state.get("status") == "complete":
        return state["report"]
    if state is None:
        reference = min(universe, key=lambda action: _wire_key(action, mixture, params))
        state = {"status": "selection", "stage_index": 0, "active_actions": [list(a) for a in universe],
                 "reference_action": list(reference), "history": [], "total_world_evaluations": 0}
    alpha = 1.0 - spec["confidence"]
    selection_z = NormalDist().inv_cdf(1.0 - alpha / (4.0 * len(universe) * len(spec["stage_sizes"])))
    while state["status"] == "selection":
        stage = state["stage_index"]
        actions = [tuple(a) for a in state["active_actions"]]
        reference = tuple(state["reference_action"])
        n = spec["stage_sizes"][stage]
        seed = _derive_seed(spec["selection_seed"], f"selection_stage:{stage}")
        if not _stream(state, actions, reference, n, seed, mixture, params, run, "selection"):
            return base | {"status": "partial", "phase": "selection", "stage_index": stage,
                           "active_candidate_count": len(actions), "pause_reason": state["pause_reason"],
                           "checkpoint": str(run.path) if run.path else None, "resume_requires_cache_dir": run.path is None,
                           "history": state["history"], "stage_results": state["history"],
                           "chosen_action": None, "approximate": True, "selection_gap_upper_ms": None,
                           "confidence": spec["confidence"], "method": "paired_stage_screening_then_independent_validation",
                           "projected_validation_evaluations": len(actions) * spec["validation_samples"]}
        summaries = {action: _summary(state["records"][_key(action)], selection_z) for action in actions}
        minimum = min(value["mean_hct_ms"] for value in summaries.values())
        tied = [action for action in actions if summaries[action]["mean_hct_ms"] <= minimum + 1e-12]
        chosen = min(tied, key=lambda action: _wire_key(action, mixture, params))
        upper_bounds = [value["gap_ci_ms"][1] for action, value in summaries.items()
                        if action == reference or not value["zero_observed_variance"]]
        best_upper = min(upper_bounds)
        kept, eliminated = [], []
        for action in actions:
            value = summaries[action]
            zero_unknown = value["zero_observed_variance"] and action != reference
            remove = n >= spec["min_elimination_samples"] and not zero_unknown and value["gap_ci_ms"][0] > best_upper + spec["indifference_ms"]
            if remove:
                eliminated.append({"action": list(action), "gap_ci_ms": value["gap_ci_ms"],
                                   "reference_action": list(reference), "best_upper_ms": best_upper})
            else:
                kept.append(action)
        if chosen not in kept:
            raise AssertionError("selected empirical minimum was eliminated")
        state["history"].append({"stage_index": stage, "new_independent_connections": n, "seed": seed,
                                  "reference_action": list(reference), "empirical_choice": list(chosen),
                                  "chosen_mean_hct_ms": summaries[chosen]["mean_hct_ms"],
                                  "before": len(actions), "after": len(kept), "eliminated": eliminated,
                                  "normal_critical_value": selection_z,
                                  "upper_bound_candidate_count": len(upper_bounds),
                                  "zero_variance_upper_bounds_ignored": len(actions) - len(upper_bounds),
                                  "zero_variance_retained": sum(summaries[a]["zero_observed_variance"] and a != reference for a in kept)})
        state["active_actions"] = [list(a) for a in kept]
        state["reference_action"] = list(chosen)
        state["stage_index"] += 1
        state["records"] = {}
        state["completed_connections"] = 0
        state["last_checkpoint_connections"] = 0
        if state["stage_index"] == len(spec["stage_sizes"]):
            state["status"] = "validation"
            state["chosen_action"] = list(chosen)
        run.save(state)
        run.notify({"phase": "selection_stage_complete", "stage_index": stage, "candidate_count": len(kept),
                    "projected_validation_evaluations": len(kept) * spec["validation_samples"],
                    "chosen_action_selection_only": list(chosen)})
    chosen = tuple(state["chosen_action"])
    actions = [tuple(a) for a in state["active_actions"]]
    if not _stream(state, actions, chosen, spec["validation_samples"], spec["validation_seed"], mixture, params, run, "validation"):
        return base | {"status": "partial", "phase": "validation", "chosen_action": list(chosen),
                       "active_candidate_count": len(actions), "pause_reason": state["pause_reason"],
                       "checkpoint": str(run.path) if run.path else None, "resume_requires_cache_dir": run.path is None,
                       "history": state["history"], "stage_results": state["history"], "approximate": True,
                       "selection_gap_upper_ms": None, "confidence": spec["confidence"],
                       "method": "paired_stage_screening_then_independent_validation",
                       "validation_connections_completed": state["completed_connections"],
                       "projected_validation_evaluations": len(actions) * (spec["validation_samples"] - state["completed_connections"])}
    z = NormalDist().inv_cdf(1.0 - alpha / (4.0 * max(1, len(actions))))
    validations, unknown = [], []
    gap_upper = 0.0
    for action in actions:
        summary = _summary(state["records"][_key(action)], z)
        validations.append({"action": list(action), **summary})
        if action != chosen:
            if summary["zero_observed_variance"]:
                unknown.append(list(action))
            gap_upper = max(gap_upper, -summary["mean_gap_ms"] + summary["gap_half_width_ms"])
    report = base | {"status": "complete", "method": "paired_stage_screening_then_independent_validation",
                     "approximate": True, "chosen_action": list(chosen), "history": state["history"],
                     "stage_results": state["history"],
                     "selection_stage_samples_are_fresh_blocks": True,
                     "validation_seed": spec["validation_seed"], "validation_samples": spec["validation_samples"],
                     "validation_candidate_count": len(actions), "validation": validations,
                     "oracle_gap_upper_ms": None if unknown else gap_upper,
                     "selection_gap_upper_ms": None if unknown else gap_upper,
                     "heuristic_gap_upper_ignoring_zero_variance_ms": gap_upper,
                     "zero_variance_unresolved_actions": unknown, "uncertainty_resolved": not unknown,
                     "validation_changed_choice": False, "confidence": spec["confidence"],
                     "confidence_scope": "Bonferroni allocation across all selection stages/original candidates and surviving validation candidates; normal approximation, not a finite-sample guarantee",
                     "total_world_evaluations": state["total_world_evaluations"],
                     "no_forced_survivor_cap": True,
                     "note": "HCT tails are bounded at the world timeout but these normal intervals are heuristic. A distinct-action sample-zero difference supplies no screening upper bound and is not a proof of equivalence. A surviving distinct action with zero observed validation variance leaves the overall gap unresolved even when the actions may be equivalent. Validation never selects a new action."}
    state["status"] = "complete"
    state["report"] = report
    run.save(state)
    return report


def evaluate_action(context, action, reference_action, world_params=None, spec=None, progress=None):
    spec = _spec(spec)
    params = load_params(world_params)
    if params["channel"]["preserve_ge_across_connections"]:
        raise ValueError("stationary action evaluation does not support persistent GE state")
    action, reference = _action(action), _action(reference_action)
    mixture = _Mixture(context, spec)
    world = World(params)
    for _, ctx in mixture.entries:
        world._check(ctx, Action(*action))
        world._check(ctx, Action(*reference))
    sources = _source_hashes()
    identity = _digest({"kind": "evaluate_action", "context": context, "action": action,
                        "reference": reference, "params": params, "spec": _semantic_spec(spec), "sources": sources})
    base = {"schema": SCHEMA, "context": context, "mixture": mixture.description,
            "action": list(action), "reference_action": list(reference), "source_hashes": sources,
            "world_params_sha256": world.params_sha256, "validation_seed": spec["validation_seed"]}
    certificate = _certificate(mixture, params, sources, spec)
    if certificate is not None and action in action_universe(context, params, spec) and reference in action_universe(context, params, spec):
        ctx = mixture.entries[0][1]
        worker = World(params, seed=spec["validation_seed"])
        a = worker.sample(ctx, Action(*action), overrides={"decision_delay_ms": 0.0, "jitter_ms": 0.0})
        b = worker.sample(ctx, Action(*reference), overrides={"decision_delay_ms": 0.0, "jitter_ms": 0.0})
        stats = _new_moments()
        _update(stats, a, b)
        result = _summary(stats, 0.0)
        delay, variance = _race_moments(params)
        result.update({"n": 0, "mean_hct_ms": a["hct"] + delay, "reference_mean_hct_ms": b["hct"] + delay,
                       "variance_hct_ms2": variance, "reference_variance_hct_ms2": variance,
                       "covariance_hct_ms2": variance, "gap_sum_ms": None,
                       "confidence_method": "structural constant difference within pinned zero-loss event world"})
        return base | result | {"status": "complete", "method": "structural_zero_loss_pair",
                                "approximate": False, "uncertainty_resolved": True,
                                "certificate": certificate}
    run = _Run(identity, spec, progress)
    state = run.load() or {"status": "evaluation", "total_world_evaluations": 0}
    if state.get("status") == "complete":
        return state["report"]
    if not _stream(state, [action], reference, spec["validation_samples"], spec["validation_seed"], mixture, params, run, "action_evaluation"):
        return base | {"status": "partial", "approximate": True, "pause_reason": state["pause_reason"],
                       "n": state.get("completed_connections", 0), "checkpoint": str(run.path) if run.path else None,
                       "resume_requires_cache_dir": run.path is None}
    family = spec.get("evaluation_family_size", 1)
    if isinstance(family, bool) or not isinstance(family, int) or family < 1:
        raise ValueError("evaluation_family_size must be a positive integer")
    z = NormalDist().inv_cdf(1.0 - (1.0 - spec["confidence"]) / (2.0 * family))
    result = _summary(state["records"][_key(action)], z)
    unresolved = result["zero_observed_variance"] and action != reference
    if unresolved:
        result["heuristic_gap_half_width_ms"] = result["gap_half_width_ms"]
        result["heuristic_gap_ci_ms"] = result["gap_ci_ms"]
        result["gap_half_width_ms"] = None
        result["gap_ci_ms"] = None
    report = base | result | {"status": "complete", "method": "independent_paired_validation",
                             "approximate": True, "confidence": spec["confidence"],
                             "evaluation_family_size": family,
                             "n": spec["validation_samples"],
                             "zero_variance_is_identity": action == reference,
                             "uncertainty_resolved": not unresolved,
                             "gap_exact_by_identity": action == reference,
                             "evaluation_seed_must_not_have_selected_either_action": True}
    state["status"] = "complete"
    state["report"] = report
    run.save(state)
    return report
