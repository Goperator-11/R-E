import importlib.util
import math
from dataclasses import dataclass
from statistics import median
from types import SimpleNamespace

from padfec import policy, quantum
from padfec3 import decide3, layout, learn3


UPLINK_SCENARIOS = (0.0, 2.0, 5.0, 10.0, 20.0, 50.0)
RACE_SCALES = (0.5, 1.0, 2.0)
RTT_WINDOW = 64
RTT_MIN_SAMPLES = 8
RTT_GROUP_MIN = 4
RTT_MIN_SPAN_BYTES = 1200


def normalize_uplink(value):
    if value is None:
        return None
    value = learn3._finite("uplink_mbps", value)
    if value == -1.0:
        return None
    if value < 0.0:
        raise ValueError("uplink_mbps must be unknown, zero, or positive")
    return value


def race_interval(delay_ms):
    delay = learn3._finite("delay_ms", delay_ms, minimum=0.0)
    return (policy.race_win_prob(delay / RACE_SCALES[0]),
            policy.race_win_prob(delay / RACE_SCALES[-1]))


def select_minimax(candidates, costs):
    if not candidates or len(candidates) != len(costs):
        raise ValueError("cost rows must match a nonempty candidate set")
    actions = [learn3.check_action(tuple(c["action"])) for c in candidates]
    if len(set(actions)) != len(actions):
        raise ValueError("candidate actions must be unique")
    size = len(costs[0])
    if size == 0 or any(len(row) != size for row in costs):
        raise ValueError("cost rows must have the same positive size")
    matrix = [[learn3._finite("scenario cost", x, minimum=0.0) for x in row]
              for row in costs]
    oracle = [min(row[j] for row in matrix) for j in range(size)]
    regrets = [[x - oracle[j] for j, x in enumerate(row)] for row in matrix]
    ranked = []
    for i, (candidate, values) in enumerate(zip(candidates, regrets)):
        worst = max(values)
        total = learn3._finite("regret sum", sum(values), minimum=0.0)
        key = (worst, total, decide3.tie_key(dict(candidate, score=worst)))
        ranked.append((key, i))
    key, index = min(ranked)
    return {"candidate": dict(candidates[index]), "index": index,
            "worst_regret_ms": key[0], "sum_regret_ms": key[1],
            "regret_ms": regrets[index], "cost_ms": matrix[index],
            "oracle_cost_ms": oracle, "all_regret_ms": regrets,
            "data_kind": "development_policy_model_reference"}


class ModelReference:
    def __init__(self):
        self._layouts = {}

    def _model(self, scale):
        scale = learn3._finite("race scale", scale, positive=True)
        if scale not in self._layouts:
            spec = importlib.util.spec_from_file_location(
                "_o2_private_layout", layout.__file__)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            q = policy.race_win_prob
            module.policy = SimpleNamespace(
                parity_datagram_bytes=policy.parity_datagram_bytes,
                race_win_prob=lambda delay: q(delay / scale))
            self._layouts[scale] = module
        return self._layouts[scale]

    def cost_matrix(self, loss_distribution, k, w, S, rtt_ms, c_pkt, *,
                    uplink_mbps=None, race_scales=(1.0,), actions=None,
                    later=learn3.LATER_DEFAULT):
        uplink = normalize_uplink(uplink_mbps)
        rates = UPLINK_SCENARIOS if uplink is None else (uplink,)
        scales = tuple(learn3._finite("race scale", x, positive=True)
                       for x in race_scales)
        if not scales or len(set(scales)) != len(scales):
            raise ValueError("race scales must be nonempty and unique")
        learn3.check_later(later)
        k = learn3._int("k", k)
        layout.check_action(k, 0, 0)
        for rate in rates:
            learn3.check_transport(w, rate, rtt_ms, c_pkt)
        need = learn3.bin_needed_s(S, quantum.bin_index(k * w), c_pkt)
        distribution = []
        for p, weight in loss_distribution:
            p = learn3._finite("loss probability", p, minimum=0.0)
            weight = learn3._finite("posterior weight", weight, minimum=0.0)
            if p > 1:
                raise ValueError("loss probability must be at most one")
            distribution.append((p, weight))
        if not distribution or abs(sum(x[1] for x in distribution) - 1) > learn3.PROB_MASS_TOL:
            raise ValueError("posterior mass must be one")
        candidates = (decide3.candidates3(k, w, S, c_pkt) if actions is None
                      else decide3.explicit_candidates(actions, k, w))
        if not candidates:
            raise ValueError("no candidates")
        if len({c["action"] for c in candidates}) != len(candidates):
            raise ValueError("candidate actions must be unique")
        for candidate in candidates:
            effective = candidate["W_eff"]
            if effective > decide3.MAX_IPS or (candidate["m"] and
                    policy.parity_datagram_bytes(effective, k) > decide3.UDP_MAX):
                raise ValueError("candidate exceeds packet size limit")
            for rate in rates:
                learn3.check_model_arithmetic(effective, rate, rtt_ms)
        scenarios = [{"uplink_mbps": rate, "race_scale": scale}
                     for rate in rates for scale in scales]
        matrix = []
        for candidate in candidates:
            row = []
            for scenario in scenarios:
                model = self._model(scenario["race_scale"])
                cost = 0.0
                for p, weight in distribution:
                    if weight:
                        cost += weight * model.evaluate(
                            k, candidate["W_eff"], candidate["m"],
                            candidate["lead"], p, rtt_ms,
                            scenario["uplink_mbps"], need, later)["J"]
                row.append(learn3._finite("expected model cost", cost, minimum=0.0))
            matrix.append(row)
        return {"candidates": candidates, "cost_ms": matrix,
                "scenarios": scenarios, "n_need": need,
                "data_kind": "development_policy_model_reference"}

    def decide(self, *args, **kwargs):
        table = self.cost_matrix(*args, **kwargs)
        result = select_minimax(table["candidates"], table["cost_ms"])
        result["scenarios"] = table["scenarios"]
        result["n_need"] = table["n_need"]
        return result


@dataclass(frozen=True)
class RttObservation:
    destination: str
    prefix_bytes: int
    min_rtt_ms: float
    full_sent: bool = False
    loss_free: bool = False
    retransmission_free: bool = False
    path_stable: bool = False


def estimate_uplink(observations, destination):
    if not isinstance(destination, str) or not destination:
        raise ValueError("destination must be a nonempty string")
    selected = []
    for observation in observations:
        if not isinstance(observation, RttObservation):
            raise TypeError("expected RttObservation")
        if not isinstance(observation.destination, str) or not observation.destination:
            raise ValueError("observation destination must be nonempty")
        learn3._nonnegative_int("prefix_bytes", observation.prefix_bytes)
        if observation.prefix_bytes > learn3.MAX_EXACT_INT:
            raise ValueError("prefix bytes exceed exact float integer range")
        learn3._finite("min_rtt_ms", observation.min_rtt_ms, positive=True)
        flags = (observation.full_sent, observation.loss_free,
                 observation.retransmission_free, observation.path_stable)
        if any(type(flag) is not bool for flag in flags):
            raise TypeError("eligibility evidence must be boolean")
        if observation.destination == destination:
            selected.append(observation)
    window = selected[-RTT_WINDOW:]
    qualified = [x for x in window if x.full_sent and x.loss_free and
                 x.retransmission_free and x.path_stable]
    buckets = {}
    for point in qualified:
        buckets.setdefault(point.prefix_bytes, []).append(point.min_rtt_ms)
    groups = [{"prefix_bytes": key, "samples": len(values),
               "median_rtt_ms": median(values)}
              for key, values in sorted(buckets.items()) if len(values) >= RTT_GROUP_MIN]
    result = {"destination": destination, "window_samples": len(window),
              "qualified_samples": len(qualified), "groups": groups,
              "status": "unknown", "reason": "insufficient_samples",
              "uplink_mbps": None, "slope_ms_per_byte": None,
              "intercept_ms": None, "span_bytes": 0,
              "data_kind": "development_observational_diagnostic"}
    if len(qualified) < RTT_MIN_SAMPLES:
        return result
    if len(groups) < 2:
        result["reason"] = "insufficient_byte_diversity"
        return result
    span = groups[-1]["prefix_bytes"] - groups[0]["prefix_bytes"]
    result["span_bytes"] = span
    if span < RTT_MIN_SPAN_BYTES:
        result["reason"] = "insufficient_byte_span"
        return result
    origin = groups[0]["prefix_bytes"]
    xs = [x["prefix_bytes"] - origin for x in groups]
    ys = [x["median_rtt_ms"] for x in groups]
    xbar = sum(xs) / len(xs)
    yorigin = ys[0]
    centered_y = [y - yorigin for y in ys]
    ybar = sum(centered_y) / len(ys)
    slope = (sum((x - xbar) * (y - ybar) for x, y in zip(xs, centered_y)) /
             sum((x - xbar) ** 2 for x in xs))
    intercept = yorigin + ybar - slope * (origin + xbar)
    result["slope_ms_per_byte"] = slope
    result["intercept_ms"] = intercept
    if not math.isfinite(slope) or not math.isfinite(intercept) or slope <= 0:
        result["reason"] = "nonpositive_or_nonfinite_slope"
        return result
    rate = 0.008 / slope
    if not math.isfinite(rate) or rate <= 0:
        result["reason"] = "nonfinite_rate"
        return result
    result.update(status="estimated", reason="qualified_group_regression", uplink_mbps=rate)
    return result
