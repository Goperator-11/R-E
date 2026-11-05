import math
from dataclasses import dataclass

from padfec3 import learn3


STATE_VERSION = 1
RTT_ALPHA = 0.25
VAR_ALPHA = 0.25
VAR_MULTIPLIER = 4.0
SAMPLE_CAP = 4096
MAX_EXACT_INT = (1 << 53) - 1
SOURCES = ("initial_ack", "later_1rtt_ack")


def _number(name, value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(name + " must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(name + " must be finite and " + ("positive" if positive else "nonnegative"))
    return value


def _integer(name, value, *, minimum=0):
    if type(value) is not int:
        raise TypeError(name + " must be int")
    if not minimum <= value <= MAX_EXACT_INT:
        raise ValueError(name + " outside exact integer range")
    return value


def tau(byte_count, uplink_mbps):
    _integer("byte_count", byte_count)
    uplink_mbps = _number("uplink_mbps", uplink_mbps)
    value = 0.0 if uplink_mbps == 0 else 0.008 * byte_count / uplink_mbps
    return _number("serialization_ms", value)


@dataclass(frozen=True)
class RttSample:
    sample_id: int
    source: str
    raw_ms: float
    datagram_bytes: int | None = None
    queued_bytes: int | None = None
    shim_wait_ms: float | None = None
    uplink_mbps: float | None = None
    ack_delay_ms: float | None = None
    ack_verified: bool = False
    packet_attributed: bool = False
    queue_accounted: bool = False


def correct_sample(sample):
    if not isinstance(sample, RttSample):
        raise TypeError("sample must be RttSample")
    _integer("sample_id", sample.sample_id)
    raw = _number("raw_ms", sample.raw_ms, positive=True)
    if not isinstance(sample.source, str):
        raise TypeError("source must be str")
    for name in ("ack_verified", "packet_attributed", "queue_accounted"):
        if type(getattr(sample, name)) is not bool:
            raise TypeError(name + " must be bool")
    for name in ("datagram_bytes", "queued_bytes"):
        value = getattr(sample, name)
        if value is not None:
            _integer(name, value, minimum=1 if name == "datagram_bytes" else 0)
    for name in ("shim_wait_ms", "uplink_mbps", "ack_delay_ms"):
        value = getattr(sample, name)
        if value is not None:
            _number(name, value)
    if sample.source not in SOURCES:
        return {"accepted": False, "reason": "unattributed_source"}
    for name in ("ack_verified", "packet_attributed", "queue_accounted"):
        if not getattr(sample, name):
            return {"accepted": False, "reason": name + "_missing"}
    for name in ("datagram_bytes", "queued_bytes", "shim_wait_ms", "uplink_mbps", "ack_delay_ms"):
        if getattr(sample, name) is None:
            return {"accepted": False, "reason": name + "_missing"}
    if sample.source == "initial_ack" and sample.ack_delay_ms != 0:
        return {"accepted": False, "reason": "initial_ack_delay_not_applicable"}
    if sample.source == "later_1rtt_ack" and (sample.queued_bytes != 0 or sample.shim_wait_ms != 0):
        return {"accepted": False, "reason": "later_sample_queued"}
    serialized = tau(sample.queued_bytes + sample.datagram_bytes, sample.uplink_mbps)
    corrected = raw - serialized - sample.shim_wait_ms - sample.ack_delay_ms
    if not math.isfinite(corrected) or corrected <= 0:
        return {"accepted": False, "reason": "nonpositive_corrected_rtt"}
    return {"accepted": True, "reason": None, "sample_id": sample.sample_id,
            "source": sample.source, "raw_ms": raw, "corrected_ms": corrected,
            "serialization_ms": serialized, "shim_wait_ms": sample.shim_wait_ms,
            "ack_delay_ms": sample.ack_delay_ms}


class RttTrack:
    def __init__(self):
        self.connection_seq = -1
        self.last_valid_seq = -1
        self.observations = 0
        self.ewma_ms = None
        self.min_ms = None
        self.variation_ms = None
        self.source = None
        self.sample_id = None

    def to_dict(self):
        return {"state_version": STATE_VERSION, "connection_seq": self.connection_seq,
                "last_valid_seq": self.last_valid_seq, "observations": self.observations,
                "ewma_ms": self.ewma_ms, "min_ms": self.min_ms,
                "variation_ms": self.variation_ms, "source": self.source,
                "sample_id": self.sample_id}

    @classmethod
    def from_dict(cls, value):
        out = cls()
        if not isinstance(value, dict) or set(value) != set(out.to_dict()):
            raise ValueError("RTT state fields do not match schema")
        if type(value["state_version"]) is not int or value["state_version"] != STATE_VERSION:
            raise ValueError("unsupported RTT state version")
        for name in ("connection_seq", "last_valid_seq"):
            _integer(name, value[name], minimum=-1)
        count = _integer("observations", value["observations"])
        if not -1 <= value["last_valid_seq"] <= value["connection_seq"] or count > value["last_valid_seq"] + 1:
            raise ValueError("inconsistent RTT observation counters")
        if count == 0:
            if value["last_valid_seq"] != -1 or any(value[n] is not None for n in
                    ("ewma_ms", "min_ms", "variation_ms", "source", "sample_id")):
                raise ValueError("unobserved state contains RTT evidence")
        else:
            mean = _number("ewma_ms", value["ewma_ms"], positive=True)
            minimum = _number("min_ms", value["min_ms"], positive=True)
            variation = _number("variation_ms", value["variation_ms"])
            _integer("sample_id", value["sample_id"])
            if minimum > mean or value["source"] not in SOURCES:
                raise ValueError("inconsistent RTT values or source")
            if count == 1 and (minimum != mean or variation != mean / 2.0):
                raise ValueError("inconsistent first RTT observation")
        for key in out.__dict__:
            setattr(out, key, value[key])
        return out

    def observe_connection(self, connection_seq, samples):
        self.from_dict(self.to_dict())
        _integer("connection_seq", connection_seq)
        if connection_seq <= self.connection_seq:
            raise ValueError("connection sequence must increase")
        if not isinstance(samples, (list, tuple)) or len(samples) > SAMPLE_CAP:
            raise ValueError("samples must be a bounded sequence")
        evaluated = [correct_sample(sample) for sample in samples]
        ids = [sample.sample_id for sample in samples]
        if ids != sorted(set(ids)):
            raise ValueError("sample identifiers must increase within a connection")
        accepted = [row for row in evaluated if row["accepted"]]
        later = [row for row in accepted if row["source"] == "later_1rtt_ack"]
        selected = (later or accepted)[-1] if accepted else None
        candidate = self.from_dict(self.to_dict())
        candidate.connection_seq = connection_seq
        if selected is not None:
            value = selected["corrected_ms"]
            if candidate.observations == 0:
                candidate.ewma_ms = candidate.min_ms = value
                candidate.variation_ms = value / 2.0
            else:
                candidate.variation_ms = (candidate.variation_ms * (1.0 - VAR_ALPHA)
                                          + abs(candidate.ewma_ms - value) * VAR_ALPHA)
                candidate.ewma_ms = candidate.ewma_ms * (1.0 - RTT_ALPHA) + value * RTT_ALPHA
                candidate.min_ms = min(candidate.min_ms, value)
            candidate.observations += 1
            candidate.last_valid_seq = connection_seq
            candidate.source, candidate.sample_id = selected["source"], selected["sample_id"]
        self.from_dict(candidate.to_dict())
        self.__dict__.update(candidate.__dict__)
        return {"selected": selected, "samples": evaluated, "state": self.to_dict()}

    def age_connections(self):
        return None if self.observations == 0 else self.connection_seq - self.last_valid_seq


def delay_threshold(rtt_ms, variation_ms):
    rtt = _number("rtt_ms", rtt_ms, positive=True)
    variation = _number("variation_ms", variation_ms)
    return _number("delay_threshold", max(0.5 * rtt, VAR_MULTIPLIER * variation), positive=True)


def grade_cutoffs(ctx, action, variation_ms, later=learn3.LATER_DEFAULT):
    variation = _number("variation_ms", variation_ms)
    first, second = learn3.grade_cutoffs(ctx, action, later)
    margin = VAR_MULTIPLIER * variation
    return (_number("first_cutoff", first + margin, positive=True),
            _number("second_cutoff", second + margin, positive=True))


def classify_hct(ctx, action, hct_ms, ok, variation_ms, later=learn3.LATER_DEFAULT):
    if type(ok) is not bool:
        raise TypeError("ok must be bool")
    if not ok:
        return 2
    if ctx is None:
        return None
    hct = _number("hct_ms", hct_ms, positive=True)
    first, second = grade_cutoffs(ctx, action, variation_ms, later)
    return 0 if hct < first else 1 if hct < second else 2


def first_ack_time(rtt_ms, pre_decision_bytes, uplink_mbps, c_proc_ms):
    rtt = _number("rtt_ms", rtt_ms, positive=True)
    processing = _number("c_proc_ms", c_proc_ms)
    return _number("first_ack_time", rtt + tau(pre_decision_bytes, uplink_mbps) + processing, positive=True)


def pto_risk(rtt_ms, pre_decision_bytes, uplink_mbps, c_proc_ms):
    return first_ack_time(rtt_ms, pre_decision_bytes, uplink_mbps, c_proc_ms) >= learn3.SHIELD_RTT_MS
