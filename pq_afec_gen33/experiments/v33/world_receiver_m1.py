class Receiver:
    def __init__(self, lengths, parity_count, lead_count, parity_bytes, rate_kbps,
                 margin_ns=1000000, ttl_ns=1000000000, recent_ns=3000000000,
                 memory_limit=32768, symbol_bytes=None):
        self.lengths = tuple(lengths)
        self.m, self.lead, self.parity = parity_count, lead_count, parity_bytes
        self.rate, self.margin, self.ttl, self.recent = rate_kbps, margin_ns, ttl_ns, recent_ns
        self.limit = memory_limit
        self.symbol_bytes = max(self.lengths) if symbol_bytes is None else symbol_bytes
        values = (*self.lengths, self.m, self.lead, self.parity, self.rate, self.margin,
                  self.ttl, self.recent, self.limit, self.symbol_bytes)
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in values):
            raise ValueError("receiver integer inputs")
        if not 1 <= len(self.lengths) <= 4 or min(self.lengths) == 0 or not 0 <= self.lead <= self.m <= 4:
            raise ValueError("receiver scope")
        if not max(self.lengths) <= self.symbol_bytes <= self.parity or min(self.ttl, self.recent, self.limit) <= 0:
            raise ValueError("receiver sizes or lifetime")
        self.now = 0
        self.created = self.deadline = None
        self.opened = False
        self.closed = None
        self.cache = {}
        self.symbols = []
        self.outputs = []
        self.consumed = []
        self.restored = []
        self.physical = self.stack = self.discarded = self.overhead = 0

    @property
    def held_memory(self):
        return len(self.symbols) * (self.parity + self.symbol_bytes)

    @property
    def next_time(self):
        if self.created is None or self.closed is not None:
            return None
        return self.created + self.ttl if self.opened else min(self.deadline, self.created + self.ttl)

    def _output(self, kind, index, recovered=False):
        size = self.lengths[index] if kind == "o" else self.parity
        self.outputs.append([kind, index, size, recovered, self.now])
        self.stack += size

    def _release(self, current=None):
        missing = [i for i in range(len(self.lengths))
                   if i not in self.cache or self.now - self.cache[i] >= self.recent]
        if self.opened and self.closed is None and len(missing) <= len(self.symbols):
            priority = [i for i, _ in self.symbols if i >= self.lead]
            priority.sort()
            priority += sorted(i for i, _ in self.symbols if i < self.lead)
            used = priority[:len(missing)]
            if any(not valid for i, valid in self.symbols if i in used):
                self.discarded += len(self.symbols) * self.parity
                self.symbols.clear()
                self.closed = "crc"
            else:
                for i, _ in self.symbols:
                    if i not in used:
                        self._output("p", i)
                if current is not None:
                    self._output("o", current)
                    current = None
                for i in missing:
                    self._output("o", i, True)
                self.overhead += len(used) * self.parity - sum(self.lengths[i] for i in missing)
                self.consumed.extend(used)
                self.restored.extend(missing)
                self.symbols.clear()
                self.closed = "complete"
        if current is not None:
            self._output("o", current)

    def _check(self):
        if self.physical != self.stack + self.discarded + self.overhead + len(self.symbols) * self.parity:
            raise AssertionError("receiver byte partition")
        if self.held_memory > self.limit or self.stack > self.physical:
            raise AssertionError("receiver bound")

    def advance(self, at_ns):
        if isinstance(at_ns, bool) or not isinstance(at_ns, int) or at_ns < self.now:
            raise ValueError("receiver time")
        offset = len(self.outputs)
        while self.next_time is not None and self.next_time <= at_ns:
            self.now = self.next_time
            if self.now >= self.created + self.ttl:
                self.discarded += len(self.symbols) * self.parity
                self.symbols.clear()
                self.closed = "expired"
            else:
                self.opened = True
                self._release()
            self._check()
        self.now = at_ns
        return self.outputs[offset:]

    def receive(self, kind, index, at_ns, metadata_ok=True, symbol_ok=True):
        if kind not in ("o", "p") or isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < (len(self.lengths) if kind == "o" else self.m):
            raise ValueError("receiver packet")
        if not isinstance(metadata_ok, bool) or not isinstance(symbol_ok, bool):
            raise ValueError("receiver validity")
        offset = len(self.outputs)
        self.advance(at_ns)
        self.physical += self.lengths[index] if kind == "o" else self.parity
        if kind == "o":
            self.cache[index] = self.now
            if self.created is not None and self.closed is None:
                self.opened |= index == len(self.lengths) - 1
                self._release(index)
            else:
                self._output(kind, index)
        elif not metadata_ok:
            self.discarded += self.parity
        elif self.closed is not None:
            self._output(kind, index)
        else:
            if self.created is None:
                self.created = self.now
                tail = (self.m - index - 1) * self.parity
                if index < self.lead:
                    tail += sum(self.lengths)
                duration = (tail * 8000000 + self.rate - 1) // self.rate if self.rate else 0
                self.deadline = self.now + duration + self.margin
                if self.deadline >= self.now + self.ttl:
                    self.closed = "unsupported_deadline"
                    self._output(kind, index)
                    self._check()
                    return self.outputs[offset:]
                last = self.cache.get(len(self.lengths) - 1)
                self.opened = last is not None and self.now - last < self.recent
            if any(i == index for i, _ in self.symbols):
                self.discarded += self.parity
            elif self.held_memory + self.parity + self.symbol_bytes > self.limit:
                self.discarded += len(self.symbols) * self.parity
                self.symbols.clear()
                self.closed = "cap"
                self._output(kind, index)
            else:
                self.symbols.append((index, symbol_ok))
                self.opened |= index >= self.lead
                self._release()
        self._check()
        return self.outputs[offset:]

    def result(self):
        return {"complete": len({p[1] for p in self.outputs if p[0] == "o"}) == len(self.lengths),
                "used": list(self.consumed), "recovered": list(self.restored), "delivered": list(self.outputs),
                "bytes_in": self.physical, "bytes_to_stack": self.stack,
                "held_bytes": len(self.symbols) * self.parity, "pending_bytes": 0,
                "discard_bytes": self.discarded, "consumed_overhead": self.overhead,
                "terminal": self.closed, "created_ns": self.created, "deadline_ns": self.deadline}
