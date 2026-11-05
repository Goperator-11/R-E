import bisect
import copy
import hashlib
import heapq
import itertools
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorldContext:
    k: int = 2
    w: int = 1280
    p: float = 0.02
    rtt_ms: float = 50.0
    uplink_mbps: float = 2.0
    server_bytes: float = 0.0
    n_need: int | None = None
    loss_model: str = "iid"
    burst_length: float = 1.0
    s2c_loss: float = 0.0
    cert_bytes: float | None = None
    token: bool = False
    retry: bool = False
    condition: str = ""
    server_dgram_sizes: tuple = ()
    cert_schedule: tuple = ()
    cert_mix: tuple = ()
    jitter_mean_ms: float | None = None
    c_proc_ms: float | None = None


@dataclass(frozen=True)
class Action:
    delta: int = 0
    lead: int = 0
    trailing: int = 0
    order: tuple | None = None


def _integer(name, value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _probability(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite in [0,1]")


def ge_parameters(p, burst_length):
    _probability("p", p)
    if not math.isfinite(burst_length) or burst_length < 1:
        raise ValueError("burst_length must be finite and >= 1")
    if p == 0:
        return 0.0, 1.0
    if p == 1:
        return 1.0, 0.0
    b = 1.0 / burst_length
    a = p * b / (1.0 - p)
    if a > 1.0 + 1e-15:
        raise ValueError("p and burst_length imply a transition probability above one")
    return min(a, 1.0), b


def pattern_probability(pattern, p, loss_model="iid", burst_length=1.0):
    _probability("p", p)
    pattern = tuple(pattern)
    if any(x not in (False, True, 0, 1) for x in pattern):
        raise ValueError("pattern entries must be arrival bits")
    if loss_model not in ("iid", "ge"):
        raise ValueError("loss_model must be iid or ge")
    if loss_model == "iid":
        return math.prod((1.0 - p) if x else p for x in pattern)
    a, b = ge_parameters(p, burst_length)
    if not pattern:
        return 1.0
    value = (1.0 - p) if pattern[0] else p
    for previous, current in zip(pattern, pattern[1:]):
        value *= ((1.0 - a) if current else a) if previous else (b if current else (1.0 - b))
    return value


def _seed(seed, connection, label):
    raw = f"{seed}:{connection}:{label}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(raw, digest_size=16).digest(), "big")


def sample_loss_pattern(n, p, loss_model="iid", burst_length=1.0, seed=0, connection=0):
    _integer("n", n)
    _probability("p", p)
    rng = random.Random(_seed(seed, connection, "loss"))
    if loss_model == "iid":
        return tuple(rng.random() >= p for _ in range(n))
    if loss_model != "ge":
        raise ValueError("loss_model must be iid or ge")
    a, b = ge_parameters(p, burst_length)
    bad = rng.random() < p
    result = []
    for _ in range(n):
        result.append(not bad)
        bad = rng.random() >= b if bad else rng.random() < a
    return tuple(result)


def first_flight_outcome(pattern, k, lead, trailing, lead_mode="credit_only"):
    _integer("k", k, 1)
    _integer("lead", lead)
    _integer("trailing", trailing)
    pattern = tuple(pattern)
    if len(pattern) != lead + k + trailing or any(x not in (False, True, 0, 1) for x in pattern):
        raise ValueError("pattern must contain lead+k+trailing arrival bits")
    if lead_mode not in ("credit_only", "buffered"):
        raise ValueError("lead_mode must be credit_only or buffered")
    la = sum(pattern[:lead])
    oa = sum(pattern[lead:lead + k])
    ta = sum(pattern[lead + k:])
    missing = k - oa
    used_trailing = min(missing, ta)
    used_lead = min(missing - used_trailing, la) if lead_mode == "buffered" else 0
    return {"success": used_trailing + used_lead == missing,
            "missing_originals": missing, "arrived_originals": oa,
            "arrived_lead": la, "arrived_trailing": ta,
            "used_lead": used_lead, "used_trailing": used_trailing,
            "arrivals": pattern, "timing_included": False}


def _merge(base, change):
    for name, value in change.items():
        if isinstance(value, dict) and isinstance(base.get(name), dict):
            _merge(base[name], value)
        else:
            base[name] = copy.deepcopy(value)
    return base


def _tau(size, uplink):
    return 8.0 * size / (1000.0 * uplink) if uplink > 0 else 0.0


def load_params(overrides=None):
    source = Path(__file__).with_name("worldparams.json")
    result = json.loads(source.read_text(encoding="utf-8"))
    if overrides is None:
        return result
    if isinstance(overrides, (str, Path)):
        overrides = json.loads(Path(overrides).read_text(encoding="utf-8"))
    aliases = {"lost_consumes_uplink": ("channel", "lost_consumes_uplink"),
               "preserve_ge_across_connections": ("channel", "preserve_ge_across_connections"),
               "lead_mode": ("fec", "lead_mode"), "hold_margin_ms": ("fec", "hold_margin_ms"),
               "retransmission_shape": ("fec", "retransmission_shape"),
               "server_mode": ("server", "mode"), "P": ("server", "packet_bytes"),
               "iw_packets": ("server", "iw_packets"), "c_proc_ms": ("processing", "default_ms"),
               "decoder_max_datagram_bytes": ("server", "decoder_max_datagram_bytes"),
               "initial_pto_ms": ("timers", "initial_pto_ms"),
               "jitter_mean_ms": ("channel", "jitter_mean_ms")}
    expanded = copy.deepcopy(overrides)
    for alias, (section, name) in aliases.items():
        if alias in expanded:
            expanded.setdefault(section, {})[name] = expanded.pop(alias)
    return _merge(result, expanded)


class World:
    def __init__(self, params=None, profile="default", seed=0):
        self.params = load_params(params)
        if profile not in ("default", "policy_equivalent"):
            raise ValueError("profile must be default or policy_equivalent")
        self.profile = profile
        self.seed = seed
        self.params_sha256 = hashlib.sha256(json.dumps(self.params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self._tables = {}
        self._expectations = {}
        self._ge_states = {}
        self._validate_params()

    def _validate_params(self):
        p = self.params
        if p["server"]["mode"] not in ("granular", "exact", "unlimited"):
            raise ValueError("invalid server mode")
        if p["fec"]["lead_mode"] not in ("credit_only", "buffered"):
            raise ValueError("invalid lead mode")
        if p["fec"]["retransmission_shape"] not in ("full", "originals_first"):
            raise ValueError("invalid retransmission shape")
        for key in ("packet_bytes", "iw_packets", "preflight_ack_bytes"):
            _integer(key, p["server"][key], 1)
        if not 0 <= p["server"]["packet_overhead_bytes"] < p["server"]["packet_bytes"]:
            raise ValueError("invalid server packet overhead")
        times = p["race"]["delay_ms"]
        probabilities = p["race"]["survival_probability"]
        if len(times) != len(probabilities) or len(times) < 2 or times[0] != 0:
            raise ValueError("invalid race table")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("race times must increase")
        if any(not 0 <= q <= 1 for q in probabilities) or any(b > a for a, b in zip(probabilities, probabilities[1:])):
            raise ValueError("race survival must decrease within [0,1]")
        if p["race"]["jitter_factor"] < 0 or p["fec"]["hold_margin_ms"] < 0:
            raise ValueError("race jitter and hold margin must be nonnegative")

    def _check(self, context, action):
        if not isinstance(context, WorldContext) or not isinstance(action, Action):
            raise TypeError("context and action must be WorldContext and Action")
        for name in ("k", "w"):
            _integer(name, getattr(context, name), 1)
        for name in ("delta", "lead", "trailing"):
            _integer(name, getattr(action, name))
        for name in ("p", "s2c_loss"):
            _probability(name, getattr(context, name))
        if context.loss_model not in ("iid", "ge"):
            raise ValueError("invalid loss model")
        if context.loss_model == "ge":
            ge_parameters(context.p, context.burst_length)
        for name in ("rtt_ms", "uplink_mbps", "server_bytes"):
            value = getattr(context, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid {name}")
        if context.rtt_ms <= 0:
            raise ValueError("rtt_ms must be positive")
        if context.n_need is not None:
            _integer("n_need", context.n_need, 1)
        for name in ("cert_bytes", "jitter_mean_ms", "c_proc_ms"):
            value = getattr(context, name)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"invalid {name}")
        order = self._order(context, action)
        if order.count("O") != context.k or order.count("L") != action.lead or order.count("P") != action.trailing:
            raise ValueError("order does not match action counts")
        if self.profile == "default":
            maximum = self.params["server"]["decoder_max_datagram_bytes"]
            w = context.w + action.delta
            if w > maximum:
                raise ValueError("original exceeds quic-go Initial size clamp; automatic repacking is unsupported")
            if (action.lead + action.trailing) and self._parity_size(w, context.k) > self.params["server"]["max_wire_datagram_bytes"]:
                raise ValueError("parity exceeds the configured wire datagram limit")

    def _order(self, context, action):
        if action.order is None:
            return ("L",) * action.lead + ("O",) * context.k + ("P",) * action.trailing
        if any(x not in ("O", "L", "P") for x in action.order):
            raise ValueError("invalid packet kind in order")
        return tuple(action.order)

    def _parity_size(self, w, k):
        return w + self.params["fec"]["parity_overhead_base"] + self.params["fec"]["parity_overhead_per_k"] * k

    def _packetization(self, context, connection, rng):
        cfg = self.params["server"]
        packet = cfg["packet_bytes"]
        cert = context.cert_bytes
        if self.params["features"]["destination_changes"]:
            for start, value in sorted(context.cert_schedule):
                if connection >= start:
                    cert = float(value)
            if context.cert_mix:
                cert = float(context.cert_mix[rng.randrange(len(context.cert_mix))])
        if context.server_dgram_sizes:
            sizes = tuple(context.server_dgram_sizes)
            if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in sizes):
                raise ValueError("server_dgram_sizes must be positive integers")
            return sizes, cert
        total = context.server_bytes
        if total <= 0 and cert is not None:
            base = cfg["s0_mlkem_bytes"] if context.k >= 2 else cfg["s0_classical_bytes"]
            count = max(1, math.ceil((cert + base) / (packet - cfg["packet_overhead_bytes"])))
            total = cert + base + count * cfg["packet_overhead_bytes"]
        if total <= 0 and context.n_need is not None:
            total = context.n_need * packet
        if total <= 0:
            raise ValueError("server_bytes, cert_bytes, server_dgram_sizes or n_need is required")
        total = math.ceil(total)
        count, remainder = divmod(total, packet)
        sizes = (packet,) * count + ((remainder,) if remainder else ())
        return sizes, cert

    def _race_survival(self, delay):
        cfg = self.params["race"]
        times, probs = cfg["delay_ms"], cfg["survival_probability"]
        if delay <= times[0]:
            return probs[0]
        if delay >= times[-1]:
            return 0.0 if cfg["zero_at_last_knot"] else probs[-1]
        pos = bisect.bisect_left(times, delay)
        fraction = (delay - times[pos - 1]) / (times[pos] - times[pos - 1])
        return probs[pos - 1] + fraction * (probs[pos] - probs[pos - 1])

    def _race_delay(self, rng):
        cfg = self.params["race"]
        times, probs = cfg["delay_ms"], cfg["survival_probability"]
        value = rng.random()
        if value >= probs[0]:
            return times[0]
        for i in range(1, len(times)):
            if value >= probs[i] and probs[i - 1] > probs[i]:
                fraction = (probs[i - 1] - value) / (probs[i - 1] - probs[i])
                return (times[i - 1] + fraction * (times[i] - times[i - 1])) * cfg["jitter_factor"]
        return times[-1] * cfg["jitter_factor"]

    def _compat_table(self, context, action):
        key = (context, action)
        if key in self._tables:
            return self._tables[key]
        self._check(context, action)
        if context.loss_model != "iid" or action.order is not None:
            raise ValueError("policy_equivalent requires iid and the standard order")
        order = self._order(context, action)
        w = context.w + action.delta
        parity = self._parity_size(w, context.k)
        sizes = tuple(w if kind == "O" else parity for kind in order)
        server_sizes, _ = self._packetization(context, 0, random.Random(0))
        need = context.n_need if context.n_need is not None else len(server_sizes)
        packet = self.params["server"]["packet_bytes"]
        preack = self.params["server"]["preflight_ack_bytes"] * (context.k - 1) if context.uplink_mbps > 0 else 0
        last_original = action.lead + context.k - 1
        response = _tau(w, context.uplink_mbps)
        atoms, failures = [], []
        for pattern in itertools.product((False, True), repeat=len(order)):
            probability = pattern_probability(pattern, context.p)
            if probability == 0:
                continue
            arrived_at, elapsed = [], 0.0
            for bit, size in zip(pattern, sizes):
                if bit:
                    elapsed += _tau(size, context.uplink_mbps)
                    arrived_at.append(elapsed)
                else:
                    arrived_at.append(None)
            result = first_flight_outcome(pattern, context.k, action.lead, action.trailing)
            trailing = [i for i in range(last_original + 1, len(order)) if pattern[i]]
            if not result["success"]:
                originals = [arrived_at[i] for i in range(action.lead, last_original + 1) if pattern[i]]
                kind = "pto" if not originals else ("ptoS" if not pattern[last_original] else "ack")
                failures.append({"probability": probability, "pattern": pattern, "kind": kind,
                                 "last_original_ms": max(originals, default=0.0)})
                continue
            missing = result["missing_originals"]
            decision_index = trailing[missing - 1] if missing else last_original
            after = trailing[missing:] if missing else trailing
            decision = arrived_at[decision_index]
            base_credit = result["arrived_lead"] * parity + context.k * w
            previous = 1.0
            branches = []
            for count, index in enumerate(after):
                q = self._race_survival(arrived_at[index] - decision)
                if previous - q > 0:
                    branches.append((previous - q, base_credit + count * parity))
                previous = q
            if previous > 0:
                branches.append((previous, base_credit + len(after) * parity))
            for weight, credit in branches:
                rounds = 1 if 3 * credit - preack > packet * (need - 1) else 2
                hct = decision + rounds * context.rtt_ms + (response if rounds == 2 else 0.0)
                atoms.append({"probability": probability * weight, "pattern": pattern,
                              "hct": hct, "rounds": rounds, "initial_failure": False, "kind": "one" if rounds == 1 else "two"})
        failure_probability = sum(row["probability"] for row in failures)
        success = sum(row["probability"] for row in atoms)
        conditional_rounds = sum(row["probability"] * row["rounds"] for row in atoms) / success if success > 1e-15 else 2.0
        multiplier = 1 / (1 - failure_probability) if failure_probability < 1 else 1.0
        cfg = self.params["compatibility"]
        for row in failures:
            if row["kind"] == "pto":
                cost = context.rtt_ms + cfg["initial_pto_ms"] + _tau(context.k * w, context.uplink_mbps)
            elif row["kind"] == "ptoS":
                cost = row["last_original_ms"] + conditional_rounds * context.rtt_ms + cfg["sampled_pto_multiplier"] * context.rtt_ms
            else:
                cost = row["last_original_ms"] + conditional_rounds * context.rtt_ms + cfg["ack_slope"] * context.rtt_ms + cfg["ack_base_ms"]
            atoms.append({"probability": row["probability"], "pattern": row["pattern"], "hct": multiplier * cost,
                          "rounds": None, "initial_failure": True, "kind": row["kind"]})
        cumulative, total = [], 0.0
        for atom in atoms:
            total += atom["probability"]
            cumulative.append(total)
        mean = sum(row["probability"] * row["hct"] for row in atoms)
        variance = sum(row["probability"] * (row["hct"] - mean) ** 2 for row in atoms)
        result = {"atoms": atoms, "cdf": cumulative, "sizes": sizes, "server_sizes": server_sizes,
                  "mean_hct_ms": mean, "variance_hct_ms": variance,
                  "p_one_rtt": sum(row["probability"] for row in atoms if row["rounds"] == 1),
                  "p_two_rtt": sum(row["probability"] for row in atoms if row["rounds"] == 2),
                  "p_fail": failure_probability, "probability_sum": total}
        self._tables[key] = result
        return result

    def exact_expectation(self, context, action):
        if self.profile != "policy_equivalent":
            raise ValueError("exact expectation is only available for policy_equivalent")
        table = self._compat_table(context, action)
        return {key: table[key] for key in ("mean_hct_ms", "variance_hct_ms", "p_one_rtt", "p_two_rtt", "p_fail", "probability_sum")} | {
            "model_kind": "policy_equivalent", "approximate": False, "n": None,
            "stderr_hct_ms": 0.0, "params_sha256": self.params_sha256}

    def expectation(self, context, action, connections=4096, seed=None, use_cache=True):
        _integer("connections", connections, 1)
        if self.profile == "policy_equivalent":
            return self.exact_expectation(context, action)
        effective_seed = self.seed if seed is None else seed
        key = (context, action, connections, effective_seed)
        if use_cache and key in self._expectations:
            return copy.deepcopy(self._expectations[key])
        worker = World(self.params, self.profile, effective_seed)
        mean = m2 = failures = one = two = ok = 0.0
        for index in range(connections):
            row = worker.sample(context, action, connection=index)
            difference = row["hct"] - mean
            mean += difference / (index + 1)
            m2 += difference * (row["hct"] - mean)
            failures += row["initial_failure"]
            one += row["world_class"] == "one"
            two += row["world_class"] == "two"
            ok += row["ok"]
        variance = m2 / (connections - 1) if connections > 1 else 0.0
        result = {"mean_hct_ms": mean, "variance_hct_ms": variance,
                  "stderr_hct_ms": math.sqrt(variance / connections), "n": connections,
                  "p_fail": failures / connections, "p_one_rtt": one / connections,
                  "p_two_rtt": two / connections, "p_ok": ok / connections,
                  "approximate": True, "model_kind": "independent_event_world",
                  "seed": effective_seed, "params_sha256": self.params_sha256,
                  "stderr_assumes_independent_connections": not self.params["channel"]["preserve_ge_across_connections"]}
        if use_cache:
            self._expectations[key] = copy.deepcopy(result)
        return result

    def sample(self, context, action, connection=0, trace=False, overrides=None):
        _integer("connection", connection)
        self._check(context, action)
        if self.profile == "policy_equivalent":
            if overrides:
                raise ValueError("overrides are supported only in the event world")
            table = self._compat_table(context, action)
            value = random.Random(_seed(self.seed, connection, "compat")).random()
            atom = table["atoms"][min(bisect.bisect_left(table["cdf"], value), len(table["atoms"]) - 1)]
            physical = sum(size for size, bit in zip(table["sizes"], atom["pattern"]) if bit)
            result = {"hct": atom["hct"], "ok": context.p < 1, "k_obs": context.k,
                      "srv_bytes": sum(table["server_sizes"]), "rtt": context.rtt_ms,
                      "initial_datagrams": context.k + 1 + (context.k if atom["initial_failure"] else 0),
                      "initial_failure": atom["initial_failure"],
                      "arrivals": [{"flight": 0, "index": i, "kind": kind, "arrived": bool(bit)} for i, (kind, bit) in enumerate(zip(self._order(context, action), atom["pattern"]))],
                      "ack_seen": [i for i, bit in enumerate(atom["pattern"][action.lead:action.lead + context.k]) if bit],
                      "server_dgram_sizes": list(table["server_sizes"]),
                      "server_counted_uplink_bytes": physical, "server_stack_credit_bytes": None,
                      "client_first_flight_bytes": sum(table["sizes"]), "client_total_uplink_bytes": None,
                      "server_retransmission_bytes": None, "pto_count": None,
                      "world_class": "failure" if atom["initial_failure"] else atom["kind"],
                      "model_kind": "policy_equivalent", "trace": [],
                      "compatibility_note": "legacy expected failure cost; transport counters beyond the first flight are synthetic or unavailable"}
            return result
        return self._sample_events(context, action, connection, trace, overrides or {})

    def _sample_events(self, context, action, connection, keep_trace, overrides):
        params = self.params
        features, channel, fec, timers = params["features"], params["channel"], params["fec"], params["timers"]
        server = params["server"]
        world_rng = random.Random(_seed(self.seed, connection, "environment"))
        c2s_rng = random.Random(_seed(self.seed, connection, "c2s"))
        s2c_rng = random.Random(_seed(self.seed, connection, "s2c"))
        sizes, selected_cert = self._packetization(context, connection, world_rng)
        p = context.p if features["c2s_loss"] else 0.0
        q = context.s2c_loss if features["s2c_loss"] else 0.0
        a, b = ge_parameters(p, context.burst_length) if context.loss_model == "ge" else (0.0, 0.0)
        state_key = (context.p, context.burst_length, context.condition)
        prior = self._ge_states.get(state_key)
        ge_bad = prior[1] if channel["preserve_ge_across_connections"] and prior is not None and prior[0] + 1 == connection else c2s_rng.random() < p
        c2s_mask, s2c_mask = tuple(overrides.get("c2s", ())), tuple(overrides.get("s2c", ()))
        for mask in (c2s_mask, s2c_mask):
            if any(bit not in (0, 1, False, True) for bit in mask):
                raise ValueError("override masks must contain arrival bits")
        mask_positions = {"c2s": 0, "s2c": 0}
        jitter_mean = context.jitter_mean_ms if context.jitter_mean_ms is not None else channel["jitter_mean_ms"]
        jitter = overrides.get("jitter_ms", world_rng.expovariate(1.0 / jitter_mean) if jitter_mean > 0 and features["destination_changes"] else 0.0)
        if not math.isfinite(jitter) or jitter < 0:
            raise ValueError("jitter must be finite and nonnegative")
        true_rtt = context.rtt_ms + jitter
        half_rtt = true_rtt / 2.0
        uplink = context.uplink_mbps if features["uplink_serialization"] else 0.0
        w = context.w + action.delta
        parity_size = self._parity_size(w, context.k)
        processing = context.c_proc_ms if context.c_proc_ms is not None else params["processing"]["conditions"].get(context.condition, params["processing"]["default_ms"])
        processing = processing if features["processing_delay"] else 0.0
        decision_delay = overrides.get("decision_delay_ms", self._race_delay(world_rng) if features["trailing_race"] else 0.0)
        if decision_delay < 0 or not math.isfinite(decision_delay):
            raise ValueError("decision delay must be finite and nonnegative")
        initial_pto = timers["rfc_initial_pto_ms"] if timers["use_rfc_initial_pto"] else timers["initial_pto_ms"]
        queue, trace_rows, arrival_rows = [], [], []
        serial = itertools.count()
        original_arrivals, original_stack, ack_seen = set(), set(), set()
        decoders = {}
        received_server, server_acked, outstanding = set(), set(), {}
        server_tx_sizes = []
        counters = {"client_bytes": 0, "first_bytes": 0, "physical_received": 0, "stack_credit": 0,
                    "server_sent": 0, "server_retransmission": 0, "initial": 0, "parity": 0, "pto": 0,
                    "client_server_received": 0, "wire_received": 0}
        state = {"uplink_free": 0.0, "ready": False, "ready_scheduled": False, "validated": bool(context.token and features["token_retry"]),
                 "retry_done": False, "retry_sent": False, "server_next": 0, "server_epoch": 0,
                 "client_epoch": 0, "sample_rtt": None, "srtt": None, "rttvar": None,
                 "min_rtt": None, "server_latest_rtt": None, "server_srtt": None, "server_rttvar": None,
                 "flight": 0, "last_flight": 0.0, "first_failure": None, "first_pattern": (),
                 "first_prefix": None, "srv_big": False, "reply_generation": 0,
                 "reply_delivered": False, "reply_active": False, "reply_retry": 0,
                 "max_orig_ack": -1, "preack_scheduled": False, "pending_ack": set(),
                 "pending_ack_reference": None, "reference_flight": 0.0, "post_ack_scheduled": False,
                 "retry_accepted_flight": 0, "probe_delivered": set(),
                 "last_retry_flight": -1,
                 "complete": False, "hct": timers["max_time_ms"], "second_round": False,
                 "tail": False, "client_retry": 0, "server_retry": 0, "stop_reason": "event_queue_empty"}

        def emit(name, time, **details):
            if keep_trace:
                trace_rows.append({"event": name, "time_ms": time, **details})

        def schedule(time, kind, data=None):
            if time <= timers["max_time_ms"]:
                heapq.heappush(queue, (time, next(serial), kind, data))

        def channel_bit(direction, later=False):
            nonlocal ge_bad
            mask = c2s_mask if direction == "c2s" else s2c_mask
            position = mask_positions[direction]
            mask_positions[direction] += 1
            if direction == "c2s":
                natural = not ge_bad if context.loss_model == "ge" else c2s_rng.random() >= p
                if context.loss_model == "ge":
                    ge_bad = c2s_rng.random() >= b if ge_bad else c2s_rng.random() < a
                if later and not features["second_round_loss"]:
                    natural = True
            else:
                natural = s2c_rng.random() >= q
            if position < len(mask):
                return bool(mask[position])
            if direction in overrides and overrides.get("mask_exhaustion") == "error":
                raise ValueError(f"{direction} override mask exhausted at {position}")
            return natural

        def transmit_client(time, kind, size, index, flight, later=False, server_ack=()):
            bit = channel_bit("c2s", later)
            start = max(time, state["uplink_free"])
            finish = start + (_tau(size, uplink) if bit or channel["lost_consumes_uplink"] else 0.0)
            state["uplink_free"] = finish
            counters["client_bytes"] += size
            if kind in ("O", "R", "B"):
                counters["initial"] += 1
            elif kind in ("L", "P", "Q", "V"):
                counters["parity"] += 1
            if flight == 0:
                counters["first_bytes"] += size
            arrival_rows.append({"flight": flight, "index": index, "kind": kind, "arrived": bit,
                                 "size": size, "sent_ms": time, "wire_finish_ms": finish,
                                 "read_size": min(size, server["decoder_max_datagram_bytes"]) if bit else 0,
                                 "usable": bit and size <= server["decoder_max_datagram_bytes"],
                                 "arrival_ms": finish + half_rtt if bit else None})
            emit("client_send", time, kind=kind, size=size, index=index, flight=flight, arrived=bit)
            if kind == "O" and state["first_prefix"] is None:
                state["first_prefix"] = max(0.0, start - time)
            if bit:
                schedule(finish + half_rtt, "client_arrival", (kind, size, index, flight, time, finish, server_ack))
            return bit, finish

        def sampled_pto():
            if state["sample_rtt"] is None:
                return initial_pto
            if state["srtt"] is None:
                return timers["sampled_pto_multiplier"] * state["sample_rtt"]
            return state["srtt"] + max(4.0 * state["rttvar"], 1.0)

        def server_pto():
            if state["server_latest_rtt"] is None:
                return initial_pto
            return state["server_srtt"] + max(4.0 * state["server_rttvar"], 1.0)

        def arm_client_pto(time):
            state["client_epoch"] += 1
            if not features["retransmissions"] or (state["sample_rtt"] is None and not features["presample_pto"]):
                return
            timeout = sampled_pto() * 2 ** state["client_retry"]
            schedule(max(time, state["last_flight"] + timeout), "client_pto", state["client_epoch"])

        def send_flight(time, retry=False):
            flight = state["flight"]
            standard = self._order(context, action)
            order = standard
            if retry and fec["retransmission_shape"] == "originals_first":
                order = ("O",) * context.k + (("P",) if action.trailing else ())
            original_index = parity_index = 0
            bits, canonical = [], {"L": [], "O": [], "P": []}
            for kind in order:
                index = original_index if kind == "O" else parity_index
                bit, _ = transmit_client(time, kind, w if kind == "O" else parity_size, index, flight)
                bits.append(bit)
                packet_size = w if kind == "O" else parity_size
                canonical[kind].append(bit and packet_size <= server["decoder_max_datagram_bytes"])
                original_index += kind == "O"
                parity_index += kind != "O"
            if flight == 0:
                state["first_pattern"] = tuple(bits)
                outcome = first_flight_outcome(canonical["L"] + canonical["O"] + canonical["P"], context.k, action.lead, action.trailing, fec["lead_mode"])
                state["first_failure"] = not outcome["success"]
            if fec["lead_mode"] == "buffered":
                nominal = time + sum(_tau(w if kind == "O" else parity_size, uplink) for kind in order)
                schedule(nominal + half_rtt + fec["hold_margin_ms"], "hold_deadline", flight)
            state["last_flight"] = time
            state["flight"] += 1
            arm_client_pto(time)

        def can_send(size):
            if not features["amplification_limit"] or state["validated"] or server["mode"] == "unlimited":
                return True
            budget = 3 * counters["stack_credit"]
            return counters["server_sent"] < budget if server["mode"] == "granular" else counters["server_sent"] + size <= budget

        def send_server(time, kind, size, data, retransmission=False):
            if not can_send(size):
                emit("server_amp_blocked", time, kind=kind, size=size, sent=counters["server_sent"], credit=counters["stack_credit"])
                return False
            counters["server_sent"] += size
            server_tx_sizes.append(size)
            if retransmission:
                counters["server_retransmission"] += size
            bit = channel_bit("s2c")
            emit("server_send", time, kind=kind, size=size, arrived=bit, retransmission=retransmission)
            if bit:
                schedule(time + half_rtt, "server_arrival", (kind, size, data, time, retransmission))
            return True

        def arm_server_pto(time):
            state["server_epoch"] += 1
            if not outstanding or not features["retransmissions"] or not can_send(1):
                return
            base = server_pto()
            schedule(time + base * 2 ** state["server_retry"], "server_pto", state["server_epoch"])

        def flush_server(time):
            if not state["ready"]:
                return
            if context.retry and features["token_retry"] and not state["retry_done"]:
                if not state["retry_sent"]:
                    state["retry_sent"] = send_server(time, "retry", server["retry_bytes"], None)
                return
            while state["server_next"] < len(sizes) and len(outstanding) < server["iw_packets"]:
                index = state["server_next"]
                if not send_server(time, "data", sizes[index], index):
                    break
                outstanding[index] = time
                state["server_next"] += 1
            arm_server_pto(time)

        def credit(time, amount):
            blocked = not can_send(1)
            counters["stack_credit"] += amount
            emit("server_credit", time, amount=amount, total=counters["stack_credit"])
            if blocked and can_send(1) and outstanding:
                arm_server_pto(time)

        def decoder(flight):
            return decoders.setdefault(flight, {"originals": set(), "lead": {}, "trailing": {}})

        def request_ready(time):
            if len(original_arrivals) == context.k and not state["ready"] and not state["ready_scheduled"]:
                state["ready_scheduled"] = True
                schedule(time + decision_delay, "server_ready")

        def try_decode(time, flight, force=False):
            record = decoder(flight)
            held_lead, held_trailing = record["lead"], record["trailing"]
            missing = context.k - len(record["originals"])
            usable_trailing = list(held_trailing)
            usable_lead = list(held_lead) if fec["lead_mode"] == "buffered" else []
            if missing > len(usable_trailing) + len(usable_lead):
                request_ready(time)
                return
            if fec["lead_mode"] == "buffered" and missing and not force:
                request_ready(time)
                return
            for symbol in usable_trailing[:missing]:
                held_trailing.pop(symbol)
            used_lead = max(0, missing - len(usable_trailing))
            for symbol in usable_lead[:used_lead]:
                held_lead.pop(symbol)
            for index in range(context.k):
                if index not in record["originals"]:
                    record["originals"].add(index)
                    original_arrivals.add(index)
                    original_stack.add(index)
                    credit(time, w)
                    emit("fec_recover", time, index=index, flight=flight)
            if fec["lead_mode"] == "buffered":
                for value in held_lead.values():
                    credit(time, value)
                held_lead.clear()
            for value in held_trailing.values():
                credit(time, value)
            held_trailing.clear()
            request_ready(time)

        def preack(time, index, sent_time):
            if not features["preflight_ack"] or uplink <= 0 or state["ready"]:
                return
            state["pending_ack"].add(index)
            reference = state["pending_ack_reference"]
            state["pending_ack_reference"] = sent_time if reference is None else min(reference, sent_time)
            if not state["preack_scheduled"]:
                state["preack_scheduled"] = True
                schedule(time + server["preflight_ack_coalesce_ms"], "send_preack")

        def record_rtt(value):
            value = value if features["rtt_inflation"] else true_rtt
            state["min_rtt"] = value if state["min_rtt"] is None else min(state["min_rtt"], value)
            if state["sample_rtt"] is None:
                state["sample_rtt"] = value
                state["srtt"] = value
                state["rttvar"] = value / 2.0
            else:
                state["sample_rtt"] = value
                state["rttvar"] = 0.75 * state["rttvar"] + 0.25 * abs(state["srtt"] - value)
                state["srtt"] = 0.875 * state["srtt"] + 0.125 * value

        def send_reply(time, retry=False):
            generation = state["reply_generation"]
            if not retry:
                state["reply_generation"] += 1
                generation = state["reply_generation"]
                state["reply_active"] = True
            flight = 1000000 + generation
            acknowledged = tuple(sorted(received_server))
            transmit_client(time, "R", w, generation, flight, True, acknowledged)
            if action.trailing and fec["response_xor"]:
                transmit_client(time, "Q", self._parity_size(w, 1), generation, flight, True, acknowledged)
            schedule(time + sampled_pto() * 2 ** state["reply_retry"], "reply_pto", generation)

        def handle_server_ack(time, acknowledged):
            acknowledged = set(acknowledged)
            newly_acked = acknowledged.intersection(outstanding)
            if newly_acked:
                newest = max(newly_acked)
                sample = time - outstanding[newest]
                state["server_latest_rtt"] = sample
                if state["server_srtt"] is None:
                    state["server_srtt"] = sample
                    state["server_rttvar"] = sample / 2.0
                else:
                    state["server_rttvar"] = 0.75 * state["server_rttvar"] + 0.25 * abs(state["server_srtt"] - sample)
                    state["server_srtt"] = 0.875 * state["server_srtt"] + 0.125 * sample
            server_acked.update(acknowledged)
            for packet_index in acknowledged:
                outstanding.pop(packet_index, None)
            if acknowledged:
                largest = max(acknowledged)
                for packet_index, packet_sent in tuple(outstanding.items()):
                    if packet_index < largest:
                        threshold = timers["loss_time_multiplier"] * max(state["server_latest_rtt"] or true_rtt, state["server_srtt"] or true_rtt)
                        schedule(max(time, packet_sent + threshold), "server_loss", packet_index)
            if state["server_next"] < len(sizes):
                state["second_round"] = True
            if not state["complete"]:
                flush_server(time)

        def send_post_big_probes(time):
            for probe in range(timers["initial_probe_packets"]):
                identifier = state["flight"] * timers["initial_probe_packets"] + probe
                transmit_client(time, "B", w, identifier, state["flight"])
                if action.trailing and fec["response_xor"]:
                    transmit_client(time, "V", self._parity_size(w, 1), identifier, state["flight"])
            state["flight"] += 1
            state["last_flight"] = time
            arm_client_pto(time)

        send_flight(0.0)
        events = 0
        while queue and events < timers["max_events"]:
            time, _, kind, data = heapq.heappop(queue)
            events += 1
            if state["complete"] and kind not in ("client_arrival", "server_arrival"):
                continue
            if kind == "client_arrival":
                token, size, index, flight, sent_time, finish, server_ack = data
                wire_size = size
                size = min(wire_size, server["decoder_max_datagram_bytes"])
                counters["wire_received"] += wire_size
                counters["physical_received"] += size
                usable = size == wire_size
                emit("server_receive", time, kind=token, size=size, wire_size=wire_size, usable=usable, index=index, flight=flight)
                if context.retry and features["token_retry"]:
                    if not state["retry_done"]:
                        if flight != state["last_retry_flight"]:
                            credit(time, size)
                            state["retry_sent"] = send_server(time, "retry", server["retry_bytes"], None)
                            state["last_retry_flight"] = flight
                        continue
                    if flight < state["retry_accepted_flight"]:
                        continue
                    if token == "O":
                        state["validated"] = True
                if not usable and token in ("L", "P", "Q", "V"):
                    credit(time, size)
                    emit("parity_truncated", time, kind=token, wire_size=wire_size, read_size=size)
                    continue
                if token in ("B", "V"):
                    if index not in state["probe_delivered"]:
                        state["probe_delivered"].add(index)
                        credit(time, w)
                        if not state["complete"]:
                            flush_server(time)
                    else:
                        credit(time, size)
                    continue
                if token == "A":
                    credit(time, size)
                    handle_server_ack(time, server_ack)
                    continue
                if token in ("R", "Q"):
                    if not state["reply_delivered"]:
                        state["reply_delivered"] = True
                        credit(time, w)
                        state["validated"] = True
                        state["server_retry"] = 0
                        handle_server_ack(time, server_ack)
                    else:
                        credit(time, size)
                    continue
                if token == "O":
                    state["reference_flight"] = max(state["reference_flight"], sent_time)
                    decoder(flight)["originals"].add(index)
                    original_arrivals.add(index)
                    original_stack.add(index)
                    credit(time, size)
                    if len(original_arrivals) < context.k:
                        preack(time, index, sent_time)
                    try_decode(time, flight, force=index == context.k - 1)
                    if state["ready"] and not state["complete"]:
                        flush_server(time)
                elif token == "L":
                    if fec["lead_mode"] == "credit_only" or state["ready"]:
                        credit(time, size)
                    else:
                        decoder(flight)["lead"][index] = size
                else:
                    if state["ready"] or state["ready_scheduled"]:
                        credit(time, size)
                    else:
                        decoder(flight)["trailing"][index] = size
                        try_decode(time, flight, force=True)
            elif kind == "hold_deadline":
                try_decode(time, data, force=True)
            elif kind == "send_preack":
                state["preack_scheduled"] = False
                acknowledged = tuple(sorted(state["pending_ack"]))
                reference = state["pending_ack_reference"]
                state["pending_ack"].clear()
                state["pending_ack_reference"] = None
                if acknowledged:
                    send_server(time, "ack", server["preflight_ack_bytes"], (acknowledged, reference))
            elif kind == "server_ready":
                state["ready"] = True
                state["ready_scheduled"] = False
                emit("server_ready", time)
                flush_server(time)
            elif kind == "server_arrival":
                token, size, index, packet_sent, retransmission = data
                counters["client_server_received"] += size
                emit("client_receive", time, kind=token, size=size, index=index)
                if state["complete"]:
                    continue
                if token == "retry":
                    state["retry_done"] = True
                    state["retry_accepted_flight"] = state["flight"]
                    state["ready"] = False
                    state["ready_scheduled"] = False
                    original_arrivals.clear()
                    original_stack.clear()
                    decoders.clear()
                    state["client_retry"] = 0
                    send_flight(time, retry=True)
                    continue
                if token == "ack":
                    indices, reference = index
                    ack_seen.update(indices)
                    record_rtt(time - reference)
                    highest = max(indices)
                    if highest > state["max_orig_ack"]:
                        state["max_orig_ack"] = highest
                        if any(i not in ack_seen for i in range(highest)) and features["retransmissions"]:
                            schedule(max(time, state["last_flight"] + timers["loss_time_multiplier"] * state["sample_rtt"] + timers["loss_timer_extra_ms"]), "client_loss")
                    arm_client_pto(time)
                    continue
                received_server.add(index)
                if 0 in received_server and state["sample_rtt"] is None:
                    record_rtt(time - state["reference_flight"])
                if size >= 1200:
                    state["srv_big"] = True
                if 0 in received_server and not state["reply_active"]:
                    schedule(time, "send_reply")
                    state["reply_active"] = True
                elif 0 in received_server and state["reply_delivered"] and not state["post_ack_scheduled"]:
                    schedule(time, "send_post_ack")
                    state["post_ack_scheduled"] = True
                if len(received_server) == len(sizes):
                    schedule(time + processing, "complete")
                elif retransmission:
                    state["tail"] = True
            elif kind == "send_reply":
                send_reply(time)
            elif kind == "send_post_ack":
                state["post_ack_scheduled"] = False
                transmit_client(time, "A", server["preflight_ack_bytes"], 0, 2000000, True, tuple(sorted(received_server)))
            elif kind == "client_loss":
                if not state["srv_big"] and state["client_retry"] < timers["max_pto_backoff"]:
                    state["client_retry"] += 1
                    send_flight(time, retry=True)
            elif kind == "client_pto":
                if data != state["client_epoch"] or (state["srv_big"] and 0 in received_server and state["reply_active"]):
                    continue
                if state["client_retry"] >= timers["max_pto_backoff"]:
                    state["stop_reason"] = "client_pto_limit"
                    continue
                counters["pto"] += 1
                emit("client_pto", time, retry=state["client_retry"])
                state["client_retry"] += 1
                if state["srv_big"]:
                    send_post_big_probes(time)
                else:
                    send_flight(time, retry=True)
            elif kind == "reply_pto":
                if data != state["reply_generation"] or state["reply_delivered"]:
                    continue
                if state["reply_retry"] >= timers["max_pto_backoff"] or not features["retransmissions"]:
                    continue
                counters["pto"] += 1
                state["tail"] = True
                state["reply_retry"] += 1
                send_reply(time, retry=True)
            elif kind == "server_loss":
                if data not in outstanding or data in server_acked:
                    continue
                if send_server(time, "data", sizes[data], data, True):
                    outstanding[data] = time
                    state["tail"] = True
                arm_server_pto(time)
            elif kind == "server_pto":
                if data != state["server_epoch"] or not outstanding or not can_send(1):
                    continue
                if state["server_retry"] >= timers["max_pto_backoff"]:
                    continue
                counters["pto"] += 1
                state["server_retry"] += 1
                for packet_index in sorted(outstanding)[:2]:
                    if send_server(time, "data", sizes[packet_index], packet_index, True):
                        outstanding[packet_index] = time
                state["tail"] = True
                arm_server_pto(time)
            elif kind == "complete":
                state["complete"] = True
                state["hct"] = time
                state["stop_reason"] = "handshake_complete"
                emit("handshake_complete", time)
        if events >= timers["max_events"]:
            state["stop_reason"] = "event_limit"
        if channel["preserve_ge_across_connections"]:
            self._ge_states[state_key] = (connection, ge_bad)
        category = "failure" if state["first_failure"] or not state["complete"] else ("tail" if state["tail"] else ("two" if state["second_round"] else "one"))
        return {"hct": state["hct"], "ok": state["complete"], "k_obs": context.k,
                "srv_bytes": counters["client_server_received"],
                "rtt": state["min_rtt"], "initial_datagrams": counters["initial"],
                "initial_failure": bool(state["first_failure"]), "arrivals": arrival_rows,
                "ack_seen": sorted(ack_seen), "server_dgram_sizes": server_tx_sizes,
                "server_counted_uplink_bytes": counters["physical_received"],
                "server_wire_received_bytes": counters["wire_received"],
                "server_stack_credit_bytes": counters["stack_credit"],
                "client_first_flight_bytes": counters["first_bytes"],
                "client_total_uplink_bytes": counters["client_bytes"],
                "server_retransmission_bytes": counters["server_retransmission"],
                "server_total_sent_bytes": counters["server_sent"],
                "parity_datagrams": counters["parity"], "pto_count": counters["pto"],
                "world_class": category, "model_kind": "independent_event_world",
                "true_rtt_ms": true_rtt, "sample_rtt_ms": state["sample_rtt"],
                "min_rtt_ms": state["min_rtt"], "server_sample_rtt_ms": state["server_latest_rtt"],
                "selected_cert_bytes": selected_cert, "server_first_flight_bytes": sum(sizes),
                "server_first_flight_sizes": list(sizes), "initial_arrival_pattern": state["first_pattern"],
                "stop_reason": state["stop_reason"], "event_count": events,
                "params_sha256": self.params_sha256, "trace": trace_rows}
