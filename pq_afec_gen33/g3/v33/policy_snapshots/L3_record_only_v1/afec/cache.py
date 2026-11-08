from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Prior:
    p: float
    burst: float
    weight: float
    source: str


@dataclass
class _Entry:
    p: float
    burst: float
    weight: float
    t: float


def _dest_key(dest: str) -> str:
    try:
        addr = ipaddress.ip_address(dest)
    except ValueError:
        return dest
    if addr.version == 4:
        return str(ipaddress.ip_network(f"{addr}/24", strict=False))
    return str(ipaddress.ip_network(f"{addr}/48", strict=False))


class PathStatsCache:
    NETWORK_AGG = "*"

    def __init__(self, half_life_s: float = 600.0, max_entries: int = 256,
                 w_cap: float = 1536.0, w_min: float = 25.0,
                 prior_out_cap: float = 100.0,
                 default_p: float = 0.01, default_burst: float = 1.0,
                 default_weight: float = 100.0):
        self.half_life_s = half_life_s
        self.max_entries = max_entries
        self.w_cap = w_cap
        self.w_min = w_min
        self.prior_out_cap = prior_out_cap
        self.default = Prior(default_p, default_burst,
                             min(default_weight, prior_out_cap), "default")
        self._table: dict[tuple[str, str], _Entry] = {}

    def _decayed_weight(self, e: _Entry, now: float) -> float:
        age = max(now - e.t, 0.0)
        return e.weight * 0.5 ** (age / self.half_life_s)

    def _get(self, key: tuple[str, str], now: float) -> Prior | None:
        e = self._table.get(key)
        if e is None:
            return None
        w = self._decayed_weight(e, now)
        if w < self.w_min:
            del self._table[key]
            return None
        return Prior(e.p, e.burst, min(w, self.prior_out_cap),
                     "exact" if key[1] != self.NETWORK_AGG else "network")

    def _merge(self, key: tuple[str, str], p: float, burst: float,
               w_new: float, now: float) -> None:
        old = self._table.get(key)
        if old is not None:
            w_old = self._decayed_weight(old, now)
            w = w_old + w_new
            p = (old.p * w_old + p * w_new) / w
            burst = (old.burst * w_old + burst * w_new) / w
        else:
            w = w_new
        self._table[key] = _Entry(p, burst, min(w, self.w_cap), now)

        if len(self._table) > self.max_entries:
            oldest = min(self._table, key=lambda k: self._table[k].t)
            del self._table[oldest]

    def lookup(self, network_id: str, dest: str,
               now: float | None = None) -> Prior:
        now = time.monotonic() if now is None else now
        hit = self._get((network_id, _dest_key(dest)), now)
        if hit is not None:
            return hit
        hit = self._get((network_id, self.NETWORK_AGG), now)
        if hit is not None:
            return hit
        return self.default

    def store(self, network_id: str, dest: str, p: float, burst: float,
              evidence: float, now: float | None = None) -> None:
        if evidence <= 0.0:
            return
        now = time.monotonic() if now is None else now
        w = min(evidence, self.w_cap)
        self._merge((network_id, _dest_key(dest)), p, burst, w, now)
        self._merge((network_id, self.NETWORK_AGG), p, burst, w, now)

    def __len__(self) -> int:
        return len(self._table)
