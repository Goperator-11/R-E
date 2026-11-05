from dataclasses import dataclass


def _integer(name, value, lower=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < lower:
        raise ValueError(name)
    return value


@dataclass(frozen=True)
class HoldConfig:
    uplink_kbps: int = 2000
    margin_ns: int = 1_000_000
    ttl_ns: int = 1_000_000_000
    recent_ns: int = 3_000_000_000
    flight_memory_cap: int = 32768

    def __post_init__(self):
        for name in ("uplink_kbps", "margin_ns"):
            _integer(name, getattr(self, name))
        for name in ("ttl_ns", "recent_ns", "flight_memory_cap"):
            _integer(name, getattr(self, name), 1)

    def serialization_ns(self, nbytes):
        _integer("nbytes", nbytes)
        if not self.uplink_kbps:
            return 0
        return (nbytes * 8_000_000 + self.uplink_kbps - 1) // self.uplink_kbps


@dataclass(frozen=True)
class FlightSpec:
    lengths: tuple
    m: int
    lead: int
    parity_size: int
    symbol_size: int | None = None

    def __post_init__(self):
        if not isinstance(self.lengths, tuple) or not 1 <= len(self.lengths) <= 4:
            raise ValueError("lengths")
        for size in self.lengths:
            _integer("original length", size, 1)
        _integer("m", self.m)
        _integer("lead", self.lead)
        _integer("parity_size", self.parity_size, max(self.lengths))
        if self.symbol_size is None:
            object.__setattr__(self, "symbol_size", max(self.lengths))
        _integer("symbol_size", self.symbol_size, max(self.lengths))
        if self.symbol_size > self.parity_size:
            raise ValueError("symbol exceeds wire size")
        if not 0 <= self.lead <= self.m <= 4:
            raise ValueError("parity counts")

    @property
    def k(self):
        return len(self.lengths)

    @property
    def symbols(self):
        return tuple(("o", i) for i in range(self.k)) + tuple(("p", i) for i in range(self.m))

    @property
    def send_order(self):
        return tuple(("p", i) for i in range(self.lead)) + tuple(("o", i) for i in range(self.k)) + tuple(("p", i) for i in range(self.lead, self.m))

    def size(self, kind, index):
        _integer("index", index)
        if kind == "o" and index < self.k:
            return self.lengths[index]
        if kind == "p" and index < self.m:
            return self.parity_size
        raise ValueError("packet identifier")

    def bytes_after_parity(self, index):
        self.size("p", index)
        if index < self.lead:
            return (self.m - index - 1) * self.parity_size + sum(self.lengths)
        return (self.m - index - 1) * self.parity_size


@dataclass(frozen=True)
class Delivery:
    kind: str
    index: int
    size: int
    recovered: bool
    at_ns: int


class HoldDecoder:
    def __init__(self, spec, config=None):
        self.spec = spec
        self.config = config or HoldConfig()
        self.now_ns = 0
        self.created_ns = None
        self.deadline_ns = None
        self.decision_open = False
        self.open_reason = None
        self.terminal = None
        self.originals = {}
        self.held = {}
        self.used = []
        self.recovered = []
        self.pending = []
        self.delivered = []
        self.bytes_in = 0
        self.bytes_to_stack = 0
        self.pending_bytes = 0
        self.held_bytes = 0
        self.held_memory = 0
        self.discard_bytes = 0
        self.consumed_overhead = 0
        self.discards = {}
        self.events = []

    def _record(self, event):
        self.check()
        self.events.append({"event": event, "at_ns": self.now_ns,
            "bytes_in": self.bytes_in, "bytes_to_stack": self.bytes_to_stack,
            "pending_bytes": self.pending_bytes, "held_bytes": self.held_bytes,
            "held_memory": self.held_memory, "discard_bytes": self.discard_bytes,
            "consumed_overhead": self.consumed_overhead, "open": self.decision_open,
            "terminal": self.terminal})

    def check(self):
        if self.pending_bytes != sum(p.size for p in self.pending):
            raise AssertionError("pending accounting")
        if self.held_bytes != len(self.held) * self.spec.parity_size:
            raise AssertionError("held accounting")
        if self.held_memory != len(self.held) * (self.spec.parity_size + self.spec.symbol_size):
            raise AssertionError("held memory")
        values = (self.bytes_in, self.bytes_to_stack, self.pending_bytes, self.held_bytes,
                  self.discard_bytes, self.consumed_overhead)
        if min(values) < 0 or self.bytes_to_stack + self.pending_bytes > self.bytes_in:
            raise AssertionError("physical credit bound")
        if self.bytes_in != sum(values[1:]):
            raise AssertionError("byte conservation")
        if self.held_memory > self.config.flight_memory_cap:
            raise AssertionError("flight cap")

    def _queue(self, kind, index, recovered=False):
        size = self.spec.size(kind, index)
        self.pending.append(Delivery(kind, index, size, recovered, self.now_ns))
        self.pending_bytes += size

    def _discard(self, reason, nbytes):
        self.discard_bytes += nbytes
        self.discards[reason] = self.discards.get(reason, 0) + nbytes

    def _close_discard(self, reason):
        self._discard(reason, self.held_bytes)
        self.held.clear()
        self.held_bytes = 0
        self.held_memory = 0
        self.terminal = reason

    def _open(self, reason):
        if not self.decision_open:
            self.decision_open = True
            self.open_reason = reason

    def _settle(self, current_original=None):
        if self.terminal is not None or not self.decision_open:
            if current_original is not None:
                self._queue("o", current_original)
            return
        have = {i for i, t in self.originals.items() if self.now_ns - t < self.config.recent_ns}
        missing = [i for i in range(self.spec.k) if i not in have]
        if len(missing) > len(self.held):
            if current_original is not None:
                self._queue("o", current_original)
            return
        priority = sorted(self.held, key=lambda i: (i < self.spec.lead, i))
        used = priority[:len(missing)]
        if any(not self.held[i] for i in used):
            self._close_discard("crc")
            if current_original is not None:
                self._queue("o", current_original)
            return
        for i in self.held:
            if i not in used:
                self._queue("p", i)
        if current_original is not None:
            self._queue("o", current_original)
        for i in missing:
            self._queue("o", i, recovered=True)
        self.consumed_overhead += len(used) * self.spec.parity_size - sum(self.spec.lengths[i] for i in missing)
        self.used.extend(used)
        self.recovered.extend(missing)
        self.held.clear()
        self.held_bytes = 0
        self.held_memory = 0
        self.terminal = "complete"

    def advance(self, at_ns):
        _integer("at_ns", at_ns)
        if at_ns < self.now_ns:
            raise ValueError("time reversal")
        if self.created_ns is not None and self.terminal is None:
            expiry = self.created_ns + self.config.ttl_ns
            if not self.decision_open and self.deadline_ns < expiry and self.deadline_ns <= at_ns:
                self.now_ns = self.deadline_ns
                self._open("deadline")
                self._settle()
                self._record("deadline")
            if self.terminal is None and expiry <= at_ns:
                self.now_ns = expiry
                self._close_discard("expired")
                self._record("expiry")
        self.now_ns = at_ns
        self.check()

    def receive(self, kind, index, at_ns, *, metadata_ok=True, symbol_ok=True):
        size = self.spec.size(kind, index)
        if not isinstance(metadata_ok, bool) or not isinstance(symbol_ok, bool):
            raise ValueError("validation status")
        self.advance(at_ns)
        self.bytes_in += size
        if kind == "o":
            self.originals[index] = at_ns
            if self.created_ns is not None and self.terminal is None:
                if index == self.spec.k - 1:
                    self._open("last_original")
                self._settle(current_original=index)
            else:
                self._queue(kind, index)
        elif not metadata_ok:
            self._discard("metadata", size)
        elif self.terminal is not None:
            self._queue(kind, index)
        else:
            if self.created_ns is None:
                self.created_ns = at_ns
                self.deadline_ns = at_ns + self.config.serialization_ns(self.spec.bytes_after_parity(index)) + self.config.margin_ns
                if self.deadline_ns >= at_ns + self.config.ttl_ns:
                    self.terminal = "unsupported_deadline"
                    self._queue(kind, index)
                    self._record("parity")
                    return
                t_last = self.originals.get(self.spec.k - 1)
                if t_last is not None and at_ns - t_last < self.config.recent_ns:
                    self._open("cached_last_original")
            if index in self.held:
                self._discard("duplicate", size)
            elif self.held_memory + size + self.spec.symbol_size > self.config.flight_memory_cap:
                self._close_discard("cap")
                self._queue(kind, index)
            else:
                self.held[index] = symbol_ok
                self.held_bytes += size
                self.held_memory += size + self.spec.symbol_size
                if index >= self.spec.lead:
                    self._open("trailing")
                self._settle()
        self._record("original" if kind == "o" else "parity")

    def read(self, buffer_size=None):
        if buffer_size is not None:
            _integer("buffer_size", buffer_size)
        if not self.pending:
            return None
        packet = self.pending.pop(0)
        self.pending_bytes -= packet.size
        n = packet.size if buffer_size is None else min(packet.size, buffer_size)
        self.bytes_to_stack += n
        self._discard("truncated", packet.size - n)
        delivered = Delivery(packet.kind, packet.index, n, packet.recovered, self.now_ns)
        self.delivered.append(delivered)
        self._record("read")
        return delivered

    def drain(self, buffer_size=None):
        out = []
        while self.pending:
            out.append(self.read(buffer_size))
        return out

    def receive_and_drain(self, kind, index, at_ns, **kwargs):
        self.spec.size(kind, index)
        _integer("at_ns", at_ns)
        if at_ns < self.now_ns:
            raise ValueError("time reversal")
        out = self.drain()
        if self.created_ns is not None and self.terminal is None:
            expiry = self.created_ns + self.config.ttl_ns
            if not self.decision_open and self.deadline_ns < expiry and self.deadline_ns <= at_ns:
                self.advance(self.deadline_ns)
                out.extend(self.drain())
            if self.terminal is None and expiry <= at_ns:
                self.advance(expiry)
                out.extend(self.drain())
        self.receive(kind, index, at_ns, **kwargs)
        out.extend(self.drain())
        return out

    def result(self):
        complete_originals = {p.index for p in self.delivered if p.kind == "o" and p.size == self.spec.lengths[p.index]}
        return {"complete": len(complete_originals) == self.spec.k,
            "used": list(self.used), "recovered": list(self.recovered),
            "delivered": [[p.kind, p.index, p.size, p.recovered, p.at_ns] for p in self.delivered],
            "bytes_in": self.bytes_in, "bytes_to_stack": self.bytes_to_stack,
            "held_bytes": self.held_bytes, "pending_bytes": self.pending_bytes,
            "discard_bytes": self.discard_bytes, "consumed_overhead": self.consumed_overhead,
            "discards": dict(self.discards), "decision_open": self.decision_open,
            "open_reason": self.open_reason, "terminal": self.terminal,
            "created_ns": self.created_ns, "deadline_ns": self.deadline_ns}
