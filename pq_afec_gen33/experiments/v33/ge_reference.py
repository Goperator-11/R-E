import importlib.util
import itertools
import math
from dataclasses import dataclass

from padfec3 import layout, learn3


BURST_WINDOW = 64
BURST_PRIOR_STRENGTH = 16.0


def parameters(p, mean_burst=1.0):
    p = learn3._finite("loss probability", p, minimum=0.0)
    mean_burst = learn3._finite("mean_burst", mean_burst, minimum=1.0)
    if p > 1.0:
        raise ValueError("loss probability must be at most one")
    iid = p in (0.0, 1.0) or mean_burst <= 1.0 / (1.0 - p)
    if iid:
        a, b = p, 1.0 - p
    else:
        b = 1.0 / mean_burst
        a = p * b / (1.0 - p)
    return {"p": p, "requested_mean_burst": mean_burst,
            "effective_mean_burst": 1.0 / b if b > 0 and p > 0 else None,
            "good_to_bad": a, "bad_to_good": b, "iid": iid}


def _pattern(pattern):
    result = tuple(pattern)
    if any(type(x) is not int or x not in (0, 1) for x in result):
        raise ValueError("pattern must contain integer zero or one")
    return result


def forward(pattern, p, mean_burst=1.0, initial=None):
    pattern = _pattern(pattern)
    params = parameters(p, mean_burst)
    a, b = params["good_to_bad"], params["bad_to_good"]
    p = params["p"]
    if initial is None:
        good, bad = 1.0 - p, p
    else:
        if len(initial) != 2:
            raise ValueError("initial must contain two probabilities")
        good, bad = (learn3._finite("initial probability", x, minimum=0.0)
                     for x in initial)
        if abs(good + bad - 1.0) > 1e-12 or max(good, bad) > 1:
            raise ValueError("initial probabilities must sum to one")
    for arrived in pattern:
        if arrived:
            good, bad = good * (1.0 - a), good * a
        else:
            good, bad = bad * b, bad * (1.0 - b)
    return good, bad


def pattern_probability(pattern, p, mean_burst=1.0):
    pattern = _pattern(pattern)
    params = parameters(p, mean_burst)
    if params["iid"]:
        result = 1.0
        for bit in pattern:
            result *= 1.0 - params["p"] if bit else params["p"]
        return result
    return sum(forward(pattern, params["p"], mean_burst))


class GEReference:
    def __init__(self, mean_burst=1.0):
        self.mean_burst = learn3._finite("mean_burst", mean_burst, minimum=1.0)
        spec = importlib.util.spec_from_file_location("_j5_private_layout", layout.__file__)
        self.model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.model)
        self._iid_outcomes = self.model.outcomes
        self.model.outcomes = self.outcomes

    def outcomes(self, k, m, lead, w, p, uplink_mbps):
        params = parameters(p, self.mean_burst)
        if params["iid"]:
            yield from self._iid_outcomes(k, m, lead, w, p, uplink_mbps)
            return
        for record in self._iid_outcomes(k, m, lead, w, 0.5, uplink_mbps):
            probability = pattern_probability(record["pattern"], p, self.mean_burst)
            if probability:
                record["pr"] = probability
                yield record

    def evaluate(self, k, w, m, lead, p, rtt_ms, uplink_mbps, n_need, later="v3"):
        return self.model.evaluate(k, w, m, lead, p, rtt_ms, uplink_mbps, n_need, later)


def failure_transition(k, m, lead, p, mean_burst=1.0):
    order = layout.send_order(k, m, lead)
    lead = order.count("L")
    parameters(p, mean_burst)
    matrix = [[0.0, 0.0], [0.0, 0.0]]
    for pattern in itertools.product((0, 1), repeat=len(order)):
        missing = k - sum(pattern[lead:lead+k])
        trailing = sum(pattern[lead+k:])
        if missing <= trailing:
            continue
        for start in (0, 1):
            after = forward(pattern, p, mean_burst,
                            (1.0, 0.0) if start == 0 else (0.0, 1.0))
            for end in (0, 1):
                matrix[start][end] += after[end]
    return matrix


def expected_attempts(k, m, lead, p, mean_burst=1.0, retry=None):
    params = parameters(p, mean_burst)
    first = failure_transition(k, m, lead, p, mean_burst)
    if retry is None:
        retry = (k, m, lead)
    if len(retry) != 3:
        raise ValueError("retry must be (k, m, lead)")
    repeated = failure_transition(*retry, p, mean_burst)
    if p == 1.0:
        attempts = math.inf
    elif p == 0.0:
        attempts = 1.0
    else:
        a, b = 1.0 - repeated[0][0], -repeated[0][1]
        c, d = -repeated[1][0], 1.0 - repeated[1][1]
        determinant = a * d - b * c
        if determinant <= 0:
            raise ArithmeticError("nonabsorbing or numerically singular retry matrix")
        remaining = ((d - b) / determinant, (a - c) / determinant)
        failed = [(1.0 - p) * first[0][j] + p * first[1][j] for j in (0, 1)]
        attempts = 1.0 + failed[0] * remaining[0] + failed[1] * remaining[1]
    return {"attempts": attempts, "first_failure_transition": first,
            "retry_failure_transition": repeated, "parameters": params,
            "retry": list(retry), "data_kind": "development_packet_chain_reference"}


@dataclass(frozen=True)
class BurstObservation:
    destination: str
    arrivals: object
    full_sent: bool = False
    physical: bool = False


def estimate_burst(observations, destination, p):
    params = parameters(p)
    p = params["p"]
    if not isinstance(destination, str) or not destination:
        raise ValueError("destination must be a nonempty string")
    selected = []
    for observation in observations:
        if not isinstance(observation, BurstObservation):
            raise TypeError("expected BurstObservation")
        if not isinstance(observation.destination, str) or not observation.destination:
            raise ValueError("observation destination must be nonempty")
        if type(observation.full_sent) is not bool or type(observation.physical) is not bool:
            raise TypeError("evidence flags must be boolean")
        arrivals = learn3.normalize_arrivals(observation.arrivals)
        if observation.destination == destination:
            selected.append((observation, arrivals))
    window = selected[-BURST_WINDOW:]
    counts = {"gg": 0, "gb": 0, "bg": 0, "bb": 0}
    qualified = 0
    datagrams = lost = 0
    for observation, arrivals in window:
        if (not observation.full_sent or not observation.physical or
                arrivals["src"] == "none" or arrivals["trunc"] or
                arrivals["bitmap"] is None or arrivals["sent"] < 2):
            continue
        qualified += 1
        datagrams += arrivals["sent"]
        lost += arrivals["lost"]
        pattern = arrivals["bitmap"]
        for left, right in zip(pattern, pattern[1:]):
            counts[("g" if left else "b") + ("g" if right else "b")] += 1
    alpha = BURST_PRIOR_STRENGTH * (1.0 - p) + counts["bg"]
    beta = BURST_PRIOR_STRENGTH * p + counts["bb"]
    raw_b = alpha / (alpha + beta)
    boundary = p in (0.0, 1.0)
    b = 1.0 - p if boundary else min(1.0 - p, raw_b)
    burst = 1.0 / b if b > 0 and p > 0 else None
    informed = not boundary and counts["bg"] + counts["bb"] > 0
    return {"destination": destination, "p": p, "window_samples": len(window),
            "qualified_samples": qualified, "datagrams": datagrams, "lost": lost,
            "transitions": counts, "prior_strength": BURST_PRIOR_STRENGTH,
            "posterior_alpha": alpha, "posterior_beta": beta,
            "raw_bad_to_good": raw_b, "bad_to_good": b,
            "mean_burst": burst, "status": "estimated" if informed else "prior",
            "iid": boundary or b == 1.0 - p,
            "data_kind": "development_conditional_burst_diagnostic"}
