import math
from copy import deepcopy


SCHEMA_VERSION = 1
Q_MIN = 1e-6
THRESHOLD = 5.0
WINDOW = 32
READY_COUNT = 8
RIDGE = 4.0
BETA_MAX = math.log(4.0)
SOLVE_STEPS = 40
ENABLED = False
APPLY_BETA = False
APPLY_SHARED = False
C1_REEVAL = True


def number(value, *, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("monitor value must be numeric")
    try:
        value = float(value)
    except OverflowError:
        raise ValueError("monitor value must be finite") from None
    if not math.isfinite(value) or (low is not None and value < low) or (high is not None and value > high):
        raise ValueError("monitor value out of range")
    return value


def integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("monitor counter must be a nonnegative integer")
    return value


def bounded_q(q):
    return min(1.0 - Q_MIN, max(Q_MIN, number(q, low=0.0, high=1.0)))


def shifted(q, beta):
    q = number(q, low=0.0, high=1.0)
    beta = number(beta, low=-BETA_MAX, high=BETA_MAX)
    if beta == 0.0 or q in (0.0, 1.0):
        return q
    odds = math.exp(beta)
    return q * odds / (1.0 - q + q * odds)


def increment(z, q, ratio):
    if type(z) is not int or z not in (0, 1):
        raise ValueError("monitor outcome must be integer zero or one")
    if ratio not in (2.0, 0.5):
        raise ValueError("monitor ratio must be two or one half")
    return z * math.log(ratio) - math.log1p((ratio - 1.0) * bounded_q(q))


def step(up, down, z, q):
    up = max(0.0, number(up, low=0.0) + increment(z, q, 2.0))
    down = max(0.0, number(down, low=0.0) + increment(z, q, 0.5))
    direction = 1 if up >= THRESHOLD else -1 if down >= THRESHOLD else 0
    return (0.0, 0.0, direction) if direction else (up, down, 0)


def fit_beta(window):
    if not window:
        return 0.0
    values = [(bounded_q(q), z) for q, z in window]
    if any(type(z) is not int or z not in (0, 1) for _, z in values):
        raise ValueError("invalid monitor window outcome")

    def score(beta):
        total = -RIDGE * beta
        for q, z in values:
            total += z - shifted(q, beta)
        return total

    low, high = -BETA_MAX, BETA_MAX
    if score(low) <= 0.0:
        return low
    if score(high) >= 0.0:
        return high
    if score(0.0) == 0.0:
        return 0.0
    for _ in range(SOLVE_STEPS):
        middle = (low + high) / 2.0
        if score(middle) > 0.0:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def new_state():
    return {"v": SCHEMA_VERSION, "arms": {}, "shared_at": 0, "shared_count": 0}


def new_arm():
    return {"up": 0.0, "down": 0.0, "beta": 0.0, "n": 0, "last_seen": 0,
            "window": [], "alarm_at": 0, "alarm_dir": 0, "beta_before": 0.0,
            "reactive_alarm": False}


def validate(state, max_seen, check_key):
    if not isinstance(state, dict) or set(state) != {"v", "arms", "shared_at", "shared_count"}:
        raise ValueError("invalid monitor state fields")
    if type(state["v"]) is not int or state["v"] != SCHEMA_VERSION or not isinstance(state["arms"], dict):
        raise ValueError("invalid monitor state schema")
    result = deepcopy(state)
    if integer(state["shared_at"]) > max_seen:
        raise ValueError("monitor shared event is in the future")
    integer(state["shared_count"])
    for key, row in state["arms"].items():
        if not isinstance(key, str):
            raise ValueError("monitor action key must be a string")
        check_key(key)
        if not isinstance(row, dict) or set(row) != set(new_arm()):
            raise ValueError("invalid monitor action fields")
        for name in ("up", "down"):
            if number(row[name], low=0.0) >= THRESHOLD:
                raise ValueError("unconsumed monitor alarm")
        for name in ("beta", "beta_before"):
            number(row[name], low=-BETA_MAX, high=BETA_MAX)
        integer(row["n"])
        if not integer(row["alarm_at"]) <= integer(row["last_seen"]) <= max_seen:
            raise ValueError("monitor action time out of order")
        if type(row["alarm_dir"]) is not int or row["alarm_dir"] not in (-1, 0, 1) or type(row["reactive_alarm"]) is not bool:
            raise ValueError("invalid monitor alarm direction")
        if not isinstance(row["window"], list) or len(row["window"]) > WINDOW or len(row["window"]) != min(WINDOW, row["n"]):
            raise ValueError("invalid monitor window size")
        for pair in row["window"]:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("invalid monitor window pair")
            number(pair[0], low=0.0, high=1.0)
            if type(pair[1]) is not int or pair[1] not in (0, 1):
                raise ValueError("invalid monitor window outcome")
    return result


def observe(state, key, q_raw, q_used, z, at, reactive):
    integer(at, minimum=1)
    if type(reactive) is not bool:
        raise ValueError("monitor readiness must be boolean")
    q_raw = number(q_raw, low=0.0, high=1.0)
    q_used = number(q_used, low=0.0, high=1.0)
    row = state["arms"].setdefault(key, new_arm())
    if at <= row["last_seen"]:
        raise ValueError("monitor observation must advance")
    before = row["beta"]
    row["up"], row["down"], direction = step(row["up"], row["down"], z, q_used)
    row["n"] += 1
    row["last_seen"] = at
    row["window"] = (row["window"] + [[q_raw, z]])[-WINDOW:]
    action = "record"
    if direction:
        row.update(alarm_at=at, alarm_dir=direction, beta_before=before, reactive_alarm=reactive)
        if reactive and APPLY_BETA:
            row["beta"] = fit_beta(row["window"])
            action = "action_model"
    elif reactive and APPLY_BETA and ((row["beta"] > 0.0 and row["up"] == 0.0) or (row["beta"] < 0.0 and row["down"] == 0.0)):
        fitted = fit_beta(row["window"])
        target = max(0.0, min(row["beta"], fitted)) if row["beta"] > 0.0 else min(0.0, max(row["beta"], fitted))
        if target != row["beta"]:
            row["beta"] = target
            action = "recovery"
    active = {key2: value for key2, value in state["arms"].items() if at - value["last_seen"] < WINDOW}
    shared = bool(direction and reactive and APPLY_SHARED and len(active) >= 2 and all(
        value["reactive_alarm"] and value["alarm_dir"] == direction
        and state["shared_at"] < value["alarm_at"] and at - value["alarm_at"] < WINDOW
        for value in active.values()))
    if shared:
        for value in active.values():
            value.update(beta=value["beta_before"], up=0.0, down=0.0, reactive_alarm=False)
        state["shared_at"] = at
        state["shared_count"] += 1
        action = "shared_change"
    return {"direction": direction, "q_raw": q_raw, "q_used": q_used, "q_clamped": bounded_q(q_used),
            "z": z, "up": row["up"], "down": row["down"], "beta_before": before,
            "beta_after": row["beta"], "reactive": reactive, "action": action, "shared": shared,
            "shared_actions": sorted(active) if shared else [], "observations": row["n"]}


def boost_fast(weights):
    weights = [number(value, low=0.0, high=1.0) for value in weights]
    if len(weights) < 3 or abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("invalid hazard weights")
    fast = weights[0] + weights[1]
    if fast <= 0.0 or fast >= 0.8:
        return weights
    target = min(0.8, 2.0 * fast / (1.0 + fast))
    out = [value * (target / fast if index < 2 else (1.0 - target) / (1.0 - fast))
           for index, value in enumerate(weights)]
    total = sum(out)
    return [value / total for value in out]
