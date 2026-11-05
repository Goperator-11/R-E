from dataclasses import dataclass
import itertools
import math


SUPPORT = ("unknown", "supported", "unsupported")
PHASES = ("first", "retry", "pto", "followup", "response")
REFERENCE_VERSION = "m4-revisit/1"


def integer(name, value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer in {lo}..{hi}")
    return value


def boolean(name, value):
    if type(value) is not bool:
        raise ValueError(f"{name} must be bool")
    return value


@dataclass(frozen=True)
class Action:
    mode: str = "none"
    delta: int = 0
    lead: int = 0
    trail: int = 0

    def __post_init__(self):
        if self.mode not in ("none", "parity", "pad", "dup"):
            raise ValueError("unknown action mode")
        integer("delta", self.delta, 0, 252)
        integer("lead", self.lead, 0, 4)
        integer("trail", self.trail, 0, 4)
        if self.lead + self.trail > 4:
            raise ValueError("at most four extra datagrams")
        if self.mode == "none" and (self.delta or self.lead or self.trail):
            raise ValueError("none has no additional bytes")
        if self.mode in ("parity", "dup") and self.lead + self.trail == 0:
            raise ValueError("parity and dup require extra datagrams")
        if self.mode == "pad" and self.delta + self.lead + self.trail == 0:
            raise ValueError("empty pad is none")


def allowed(action, token_supplied, retry_accepted, decoder_support):
    if not isinstance(action, Action):
        raise ValueError("action must be Action")
    boolean("token_supplied", token_supplied)
    boolean("retry_accepted", retry_accepted)
    if decoder_support not in SUPPORT:
        raise ValueError("unknown decoder support")
    if action.mode == "parity" and decoder_support != "supported":
        return False
    if token_supplied or retry_accepted:
        if action.delta or action.lead or action.mode == "pad":
            return False
    return True


def candidates(templates, *, token_supplied, retry_accepted, decoder_support):
    templates = list(templates)
    result = []
    allowed(Action(), token_supplied, retry_accepted, decoder_support)
    for action in templates:
        if allowed(action, token_supplied, retry_accepted, decoder_support) and action not in result:
            result.append(action)
    if Action() not in result:
        result.insert(0, Action())
    return tuple(result)


class ConnectionPolicy:
    def __init__(self, *, token_supplied=False, decoder_support="unknown"):
        allowed(Action(), token_supplied, False, decoder_support)
        self.token_supplied = token_supplied
        self.decoder_support = decoder_support
        self.retry_accepted = False
        self.peer_processed = False
        self.first_started = False
        self.retry_started = False
        self.extras_reserved = False
        self.closed = False

    def receive_retry(self, *, accepted):
        boolean("accepted", accepted)
        if not accepted or self.closed or self.peer_processed or self.retry_accepted:
            return False
        if not self.first_started:
            raise ValueError("Retry precedes the first flight")
        self.retry_accepted = True
        return True

    def receive_peer_packet(self, *, processed):
        boolean("processed", processed)
        if processed and not self.closed:
            self.peer_processed = True

    def choices(self, phase, templates):
        if phase not in PHASES or self.closed:
            raise ValueError("invalid phase or closed connection")
        if phase == "first" and (self.first_started or self.retry_accepted):
            raise ValueError("first flight already started")
        if phase != "first" and not self.first_started:
            raise ValueError("first flight has not started")
        if phase == "retry" and (not self.retry_accepted or self.retry_started or self.peer_processed):
            raise ValueError("no new accepted Retry")
        if phase in ("pto", "followup", "response") or self.extras_reserved:
            return (Action(),)
        return candidates(templates, token_supplied=self.token_supplied,
                          retry_accepted=self.retry_accepted, decoder_support=self.decoder_support)

    def reserve(self, phase, action):
        if not isinstance(action, Action) or action not in self.choices(phase, (action,)):
            raise ValueError("action is not allowed")
        if phase == "first":
            self.first_started = True
        elif phase == "retry":
            self.retry_started = True
        if action.lead + action.trail:
            self.extras_reserved = True
        return dict(version=REFERENCE_VERSION, phase=phase, action=action,
                    address_validation="assumed" if self.token_supplied or self.retry_accepted else "unvalidated",
                    decoder_support=self.decoder_support, extras_reserved=self.extras_reserved)

    def invalid_token(self):
        if self.closed or not self.first_started or not (self.token_supplied or self.retry_accepted):
            raise ValueError("no active token attempt")
        self.closed = True
        return dict(restart_without_token=True, reused_connection=False)

    def close(self):
        self.closed = True


def observation_key(destination, *, token_supplied, retry_accepted,
                    server_initially_validated, tls_resumed):
    if not isinstance(destination, str) or not destination:
        raise ValueError("destination must be nonempty")
    boolean("token_supplied", token_supplied)
    boolean("retry_accepted", retry_accepted)
    for name, value in (("server_initially_validated", server_initially_validated), ("tls_resumed", tls_resumed)):
        if value is not None:
            boolean(name, value)
    if server_initially_validated is None:
        address = "retry_unknown" if retry_accepted else ("token_unknown" if token_supplied else "no_token_unknown")
    elif retry_accepted:
        address = "retry_validated" if server_initially_validated else "retry_unvalidated"
    elif token_supplied:
        address = "token_validated" if server_initially_validated else "token_unvalidated"
    else:
        address = "other_validated" if server_initially_validated else "no_token_unvalidated"
    tls = "unknown" if tls_resumed is None else ("resumed" if tls_resumed else "full")
    return destination, address, tls


def first_flight(k, action, loss, *, original_sizes, parity_size, decoder_support, hold_lead=False):
    integer("k", k, 1, 4)
    if not isinstance(action, Action):
        raise ValueError("action must be Action")
    if type(loss) not in (int, float) or not math.isfinite(loss) or not 0 <= loss <= 1:
        raise ValueError("loss must be finite in 0..1")
    if decoder_support not in SUPPORT:
        raise ValueError("unknown decoder support")
    boolean("hold_lead", hold_lead)
    sizes = tuple(original_sizes)
    if len(sizes) != k:
        raise ValueError("need k explicit original sizes")
    for size in sizes:
        integer("original size", size, 1, 65527)
    integer("parity_size", parity_size, 1, 65527)
    order = []
    for j in range(action.lead):
        order.append(("dup" if action.mode == "dup" else "lead", j % k))
    order.extend(("original", i) for i in range(k))
    for j in range(action.lead, action.lead + action.trail):
        order.append(("dup" if action.mode == "dup" else "trail", j % k))
    wire_sizes = [sizes[i] if kind in ("dup", "original") else parity_size for kind, i in order]
    success = 0.0
    physical = 0.0
    mass = 0.0
    for pattern in itertools.product((0, 1), repeat=len(order)):
        probability = 1.0
        for bit in pattern:
            probability *= (1 - loss) if bit else loss
        mass += probability
        delivered = set()
        symbols = 0
        for bit, (kind, index) in zip(pattern, order):
            if not bit:
                continue
            if kind in ("original", "dup"):
                delivered.add(index)
            elif action.mode == "parity" and decoder_support == "supported" and (kind == "trail" or hold_lead):
                symbols += 1
        if len(delivered) + symbols >= k:
            success += probability
        physical += probability * sum(size for bit, size in zip(pattern, wire_sizes) if bit)
    return dict(version=REFERENCE_VERSION, p_complete=success, probability_mass=mass,
                sent_bytes=sum(wire_sizes), expected_physical_bytes=physical, order=order,
                sizes=wire_sizes, scope="first_bundle_iid_delivery_only", hct_ms=None)
