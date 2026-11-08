from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .channel import GilbertElliott

K_INITIAL_RTT_MS = 333.0
GF256_MAX_SYMBOLS = 255


@dataclass
class FecConfig:
    symbol_bytes: int = 1200
    rate_bps: float = 10e6
    beta: float = 4.0
    rho_max: float = 0.50
    handshake_rho_max: float = 4.0
    k_min: int = 4
    k_max: int = 64
    delay_budget_ms: float = 30.0
    interleave: int = 1
    dwell_blocks: int = 4
    decay_fraction: float = 0.30
    risk_z: float = 1.5
    cpu_cost_ms_per_symbol: float = 0.0


@dataclass
class Decision:
    k: int
    r: int
    p_used: float
    burst_used: float
    g: float
    t_recover_ms: float
    p_fail: float
    cost: float
    table: list = field(default_factory=list)

    @property
    def overhead(self) -> float:
        return self.r / self.k if self.k else 0.0


def pto_ms(srtt_ms: float | None = None, rttvar_ms: float | None = None,
           backoff: int = 0, max_ack_delay_ms: float = 0.0) -> float:
    if srtt_ms is None:
        srtt_ms = K_INITIAL_RTT_MS
        rttvar_ms = K_INITIAL_RTT_MS / 2.0
    if rttvar_ms is None:
        rttvar_ms = srtt_ms / 2.0
    base = srtt_ms + max(4.0 * rttvar_ms, 1.0) + max_ack_delay_ms
    return base * (2 ** backoff)


def choose_redundancy(k: int, p: float, burst: float, t_recover_ms: float,
                      g: float = 0.0, cfg: FecConfig | None = None,
                      r_floor: int = 0) -> Decision:
    cfg = cfg or FecConfig()
    channel = GilbertElliott.cached(p, burst)

    hard_cap = max(GF256_MAX_SYMBOLS - k, 0)
    r_floor = min(max(r_floor, 0), hard_cap)
    r_max = min(max(int(math.ceil(k * cfg.rho_max)), r_floor), hard_cap)

    byte_cost_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
    weight = 1.0 + cfg.beta * g

    curve = channel.fail_curve(k, r_max, cfg.interleave)

    best = None
    table = []
    for r, pf in enumerate(curve):
        tx = r * (byte_cost_ms + cfg.cpu_cost_ms_per_symbol)
        cost = weight * tx + pf * t_recover_ms
        table.append((r, cost, pf))
        if r < r_floor:
            continue
        if best is None or cost < best[1] - 1e-12:
            best = (r, cost, pf)

    r_star, cost, pf = best
    return Decision(k=k, r=r_star, p_used=p, burst_used=burst, g=g,
                    t_recover_ms=t_recover_ms, p_fail=pf, cost=cost, table=table)


def choose_block_size(cfg: FecConfig, rate_bps: float | None = None) -> int:
    rate = rate_bps or cfg.rate_bps
    fit = rate * (cfg.delay_budget_ms / 1000.0) / (cfg.symbol_bytes * 8.0)
    return int(min(max(int(fit), cfg.k_min), cfg.k_max))


class AdaptiveFecController:
    def __init__(self, cfg: FecConfig | None = None, estimator=None, congestion=None):
        from .estimator import CongestionDetector, LossEstimator
        self.cfg = cfg or FecConfig()
        self.loss = estimator or LossEstimator(z=self.cfg.risk_z)
        self.cong = congestion or CongestionDetector()
        self._last_r = 0
        self._pending_down = 0
        self.last_decision: Decision | None = None

    def next_block(self, rate_bps: float | None = None) -> Decision:
        rate = self.cfg.rate_bps if rate_bps is None else rate_bps
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("rate_bps must be finite and positive")
        cfg = replace(self.cfg, rate_bps=rate)
        k = choose_block_size(cfg, rate)

        srtt = self.cong.srtt
        t_recover = 2.0 * srtt if srtt else pto_ms()

        d = choose_redundancy(
            k=k,
            p=self.loss.p_safe,
            burst=self.loss.burst_safe,
            t_recover_ms=t_recover,
            g=self.cong.g,
            cfg=cfg,
        )

        ridge = d.table[-1][2] > 0.25 if d.table else False
        if ridge and self.loss.p_safe > self.loss.p:
            d_mean = choose_redundancy(
                k=k, p=self.loss.p, burst=self.loss.burst_safe,
                t_recover_ms=t_recover, g=self.cong.g, cfg=cfg)
            if d_mean.r > d.r:
                d = d_mean

        r_cap = min(int(math.ceil(k * cfg.rho_max)), max(GF256_MAX_SYMBOLS - k, 0))
        d.r = min(self._apply_hysteresis(d.r), r_cap)
        self._last_r = d.r

        d.p_fail = GilbertElliott.cached(d.p_used, d.burst_used).p_fail(
            d.k, d.r, cfg.interleave)
        byte_ms = cfg.symbol_bytes * 8.0 / rate * 1000.0
        d.cost = ((1.0 + cfg.beta * d.g)
                  * d.r * (byte_ms + cfg.cpu_cost_ms_per_symbol)
                  + d.p_fail * d.t_recover_ms)
        self.last_decision = d
        return d

    def _apply_hysteresis(self, r_target: int) -> int:
        if r_target >= self._last_r:
            self._pending_down = 0
            self._last_r = r_target
            return r_target

        self._pending_down += 1
        if self._pending_down >= self.cfg.dwell_blocks:
            self._pending_down = 0
            gap = self._last_r - r_target
            self._last_r -= max(1, int(gap * self.cfg.decay_fraction))
        return self._last_r

    def on_feedback(self, mask: list[bool], rtt_ms: float | None = None,
                    ce_marked: bool = False) -> None:
        self.loss.observe_mask(mask)
        if rtt_ms is not None:
            self.cong.observe_rtt(rtt_ms)
        self.cong.observe_ecn(ce_marked)
