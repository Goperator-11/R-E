from dataclasses import asdict, dataclass
import math

from padfec import policy


PROFILE_VERSION = 1


def integer(name, value, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or maximum is not None and value > maximum:
        raise ValueError(name + " is outside its integer bounds")
    return value


def number(name, value, minimum=0, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum or maximum is not None and value > maximum:
        raise ValueError(name + " is outside its finite bounds")
    return value


@dataclass(frozen=True)
class ServerProfile:
    mode: str = "granular"
    P: int = 1280
    iw_pkts: int = 32
    pto_initial_ms: float = 200.0
    lead_credited: bool = True
    trailing_race: str = "table"

    def __post_init__(self):
        if self.mode not in ("granular", "exact", "unlimited"):
            raise ValueError("unsupported amplification mode")
        integer("P", self.P, 1200, 1452)
        integer("iw_pkts", self.iw_pkts, 1, 4096)
        number("pto_initial_ms", self.pto_initial_ms)
        if self.pto_initial_ms == 0:
            raise ValueError("pto_initial_ms must be positive")
        if type(self.lead_credited) is not bool or self.trailing_race not in ("table", "none"):
            raise ValueError("invalid credit capabilities")

    @classmethod
    def unknown(cls, *, P=1280, iw_pkts=10, pto_initial_ms=999.0):
        return cls("exact", P, iw_pkts, pto_initial_ms, False, "none")

    def to_dict(self):
        return {"version": PROFILE_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        keys = {"version", "mode", "P", "iw_pkts", "pto_initial_ms", "lead_credited", "trailing_race"}
        if type(value) is not dict or set(value) != keys or type(value["version"]) is not int or value["version"] != PROFILE_VERSION:
            raise ValueError("unsupported server profile record")
        return cls(**{k: v for k, v in value.items() if k != "version"})

    def packets(self, sizes):
        sizes = tuple(sizes)
        if not sizes:
            raise ValueError("server data flight is empty")
        for size in sizes:
            integer("server packet", size, 1, self.P)
        return sizes

    def required_credit(self, sizes, *, sent_bytes=0):
        sizes = self.packets(sizes)
        integer("sent_bytes", sent_bytes)
        if len(sizes) > self.iw_pkts:
            return None
        if self.mode == "unlimited":
            return 0
        if self.mode == "exact":
            return (sent_bytes + sum(sizes) + 2) // 3
        return (sent_bytes + sum(sizes[:-1])) // 3 + 1

    def send_prefix(self, credit, sizes, *, sent_bytes=0, available_slots=None):
        integer("credit", credit)
        integer("sent_bytes", sent_bytes)
        sizes = self.packets(sizes)
        slots = self.iw_pkts if available_slots is None else available_slots
        integer("available_slots", slots, 0, self.iw_pkts)
        sent = []
        cumulative = sent_bytes
        reason = None
        for size in sizes:
            if len(sent) == slots:
                reason = "congestion_window"
                break
            allowed = self.mode == "unlimited" or (cumulative < 3 * credit if self.mode == "granular" else cumulative + size <= 3 * credit)
            if not allowed:
                reason = "amplification"
                break
            sent.append(size)
            cumulative += size
        return dict(sent_sizes=tuple(sent), sent_packets=len(sent), sent_bytes=sum(sent),
                    cumulative_sent_bytes=cumulative, complete=len(sent) == len(sizes), blocked_by=reason)

    def decision_credit(self, original_credit, lead_sizes=()):
        integer("original_credit", original_credit)
        lead_sizes = tuple(lead_sizes)
        for size in lead_sizes:
            integer("lead datagram", size, 1200, 1452)
        return original_credit + (sum(lead_sizes) if self.lead_credited else 0)

    def credit_branches(self, base_credit, trailing_delays=(), trailing_sizes=()):
        integer("base_credit", base_credit)
        delays, sizes = tuple(trailing_delays), tuple(trailing_sizes)
        if len(delays) != len(sizes):
            raise ValueError("trailing time and size counts differ")
        for delay in delays:
            number("trailing delay", delay)
        if any(b < a for a, b in zip(delays, delays[1:])):
            raise ValueError("trailing delays must not decrease")
        for size in sizes:
            integer("trailing datagram", size, 1200, 1452)
        if self.trailing_race == "none":
            return ((1.0, base_credit),)
        result = []
        previous, credit = 1.0, base_credit
        for delay, size in zip(delays, sizes):
            q = policy.race_win_prob(delay)
            if previous > q:
                result.append((previous - q, credit))
            previous = q
            credit += size
        if previous:
            result.append((previous, credit))
        return tuple(result)


def first_flight_delivery(profile, credit, sizes, p_d, *, sent_bytes=0):
    if not isinstance(profile, ServerProfile):
        raise ValueError("invalid server profile")
    number("downlink loss", p_d, 0, 1)
    sizes = profile.packets(sizes)
    burst = profile.send_prefix(credit, sizes, sent_bytes=sent_bytes)
    n = burst["sent_packets"]
    return {**burst, "p_no_loss_in_sent_prefix": (1.0 - p_d) ** n,
            "p_loss_in_sent_prefix": 1.0 - (1.0 - p_d) ** n,
            "p_first_flight_complete": (1.0 - p_d) ** len(sizes) if burst["complete"] else 0.0,
            "hct_ms": None}


def retransmission_budget(profile, credit, first_sizes, received, *, sent_bytes=0, available_slots=None):
    if not isinstance(profile, ServerProfile):
        raise ValueError("invalid server profile")
    first_sizes = profile.packets(first_sizes)
    received = tuple(received)
    if len(received) != len(first_sizes) or any(type(bit) is not bool for bit in received):
        raise ValueError("arrival mask must contain one bool per sent server packet")
    first = profile.send_prefix(credit, first_sizes, sent_bytes=sent_bytes)
    if not first["complete"]:
        raise ValueError("first_sizes includes a packet that could not be sent")
    missing = tuple(size for size, bit in zip(first_sizes, received) if not bit)
    if not missing:
        return dict(missing_sizes=(), retransmitted_sizes=(), retransmission_bytes=0,
                    cumulative_sent_bytes=first["cumulative_sent_bytes"], blocked_by=None,
                    complete=True, timing_modeled=False)
    retry = profile.send_prefix(credit, missing, sent_bytes=first["cumulative_sent_bytes"], available_slots=available_slots)
    return dict(missing_sizes=missing, retransmitted_sizes=retry["sent_sizes"], retransmission_bytes=retry["sent_bytes"],
                cumulative_sent_bytes=retry["cumulative_sent_bytes"], blocked_by=retry["blocked_by"],
                complete=retry["complete"], timing_modeled=False)


def packet_size_evidence(first_data_datagram_bytes):
    if first_data_datagram_bytes is None:
        return dict(P=None, confirmed=False, reason="missing_first_data_datagram")
    integer("first_data_datagram_bytes", first_data_datagram_bytes, 1, 65527)
    if not 1200 <= first_data_datagram_bytes <= 1452:
        return dict(P=None, confirmed=False, reason="outside_supported_first_data_range")
    return dict(P=first_data_datagram_bytes, confirmed=False, reason="observed_first_data_datagram_only")


def mode_evidence(*, credit, first_rtt_server_bytes, P, amplification_limited=False,
                  no_downlink_loss=False, demand_exceeds_observed=False, no_window_limit=False,
                  stable_credit=False, address_unvalidated=False):
    integer("credit", credit, 1)
    integer("first_rtt_server_bytes", first_rtt_server_bytes)
    integer("P", P, 1200, 1452)
    checks = dict(amplification_limited=amplification_limited, no_downlink_loss=no_downlink_loss,
                  demand_exceeds_observed=demand_exceeds_observed, no_window_limit=no_window_limit,
                  stable_credit=stable_credit, address_unvalidated=address_unvalidated)
    if any(type(flag) is not bool for flag in checks.values()):
        raise ValueError("mode evidence qualifiers must be bool")
    missing = tuple(key for key, flag in checks.items() if not flag)
    ratio = first_rtt_server_bytes / credit
    candidate = None
    reason = "missing_qualifiers" if missing else "exact_and_granular_not_distinguished"
    if not missing and first_rtt_server_bytes > 3 * credit:
        if first_rtt_server_bytes < 3 * credit + P:
            candidate, reason = "granular", "overshoot_compatible_with_granular"
        else:
            reason = "inconsistent_with_amplification_limited_evidence"
    return dict(planning_mode="exact", confirmed=False, candidate_mode=candidate, reason=reason,
                missing_qualifiers=missing, observed_ratio=ratio, promotion_requires="independent_stack_validation")
