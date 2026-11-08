from __future__ import annotations

import math


class LossEstimator:
    def __init__(self, alpha=0.08, p_init=0.01, z=1.0,
                 jump_alpha=0.40, surprise_threshold=0.05, jump_min_losses=2,
                 jump_confirm=2, prior_weight=100.0, burst_init=1.0,
                 down_h=3.0):
        self.alpha = alpha
        self.z = z
        self.jump_alpha = jump_alpha
        self.surprise_threshold = surprise_threshold
        self.jump_min_losses = jump_min_losses
        self.jump_confirm = jump_confirm

        self._prior_weight = max(float(prior_weight), 1.0)
        seed_mass = 100.0
        self._sent = seed_mass
        self._lost = p_init * seed_mass
        self._observed = 0.0
        self._run_sum = max(float(burst_init), 1.0)
        self._run_num = 1.0
        self._runs_observed = 0
        self._burst_prior_fade = 2000.0
        self.down_h = down_h
        self.jump_boost_blocks = 4
        self.jumped = False
        self._streak = 0
        self._open_run = 0
        self._down_llr = 0.0
        self._boost_left = 0

    @property
    def p(self) -> float:
        return self._lost / self._sent if self._sent else 0.0

    @property
    def burst(self) -> float:
        raw = self._run_sum / self._run_num if self._run_num else 1.0
        if self._runs_observed == 0 and self._observed > 0.0:
            w = min(self._observed / self._burst_prior_fade, 1.0)
            return raw * (1.0 - w) + 1.0 * w
        return raw

    @burst.setter
    def burst(self, value: float) -> None:
        self._run_sum, self._run_num = float(value), 1.0
        self._runs_observed = 0

    def observe_mask(self, mask: list[bool]) -> None:
        n_symbols = len(mask)
        n_lost = sum(mask)

        if self._is_surprising(n_symbols, n_lost):
            self._streak += 1
        else:
            self._streak = 0
        was_jumped = self.jumped
        self.jumped = self._streak >= self.jump_confirm

        if self._boost_left > 0:
            a = self.jump_alpha
            self._boost_left -= 1
        else:
            a = self.alpha

        self._lost = (1.0 - a) * self._lost + a * n_lost
        self._sent = (1.0 - a) * self._sent + a * n_symbols
        self._observed += n_symbols
        if self.jumped and not was_jumped:
            self._observed = float(n_symbols)
            self._prior_weight = 0.0
            if self._runs_observed == 0:
                self._run_sum, self._run_num = 1.0, 1.0
            self._down_llr = 0.0
            self._boost_left = self.jump_boost_blocks
            if self._sent > n_symbols > 0:
                f = n_symbols / self._sent
                self._sent *= f
                self._lost *= f

        closed: list[int] = []
        run = self._open_run
        for lost in mask:
            if lost:
                run += 1
            elif run:
                closed.append(run)
                run = 0
        self._open_run = run

        if closed:
            b = 0.15
            self._run_sum = (1.0 - b) * self._run_sum + b * sum(closed)
            self._run_num = (1.0 - b) * self._run_num + b * len(closed)
            self._runs_observed += len(closed)

    def _is_surprising(self, n_symbols: int, n_lost: int) -> bool:
        from .channel import GilbertElliott
        pmf = GilbertElliott.cached(self.p, self.burst_safe).erasure_pmf(n_symbols)

        pmf_half = GilbertElliott.cached(self.p / 2.0,
                                         self.burst_safe).erasure_pmf(n_symbols)
        c = min(n_lost, n_symbols)
        llr = math.log(max(pmf_half[c], 1e-300)) - math.log(max(pmf[c], 1e-300))
        self._down_llr = max(0.0, self._down_llr + llr)

        if n_lost >= self.jump_min_losses:
            if sum(pmf[min(n_lost, n_symbols):]) < self.surprise_threshold:
                return True

        return self._down_llr > self.down_h

    @property
    def n_eff(self) -> float:
        window = self._sent * (2.0 - self.alpha) / self.alpha
        return max(min(window, self._observed + self._prior_weight), 1.0)

    def snapshot(self) -> tuple[float, float, float]:
        window = self._sent * (2.0 - self.alpha) / self.alpha
        return self.p, self.burst_safe, min(self._observed, window)

    @property
    def se(self) -> float:
        p = self.p
        L = self.burst_safe
        inflation = max(2.0 * L * (1.0 - p) - 1.0, 1.0)
        return math.sqrt(max(p * (1.0 - p), 1e-9) / self.n_eff * inflation)

    @property
    def p_safe(self) -> float:
        return min(self.p + self.z * self.se, 0.9)

    @property
    def burst_safe(self) -> float:
        return max(self.burst, 1.0)


class CongestionDetector:
    def __init__(self, theta_lo=0.10, theta_hi=0.50, ecn_decay=0.8,
                 rtt_min_window=200):
        self.theta_lo = theta_lo
        self.theta_hi = theta_hi
        self.ecn_decay = ecn_decay
        self.rtt_min_window = rtt_min_window
        self.srtt = None
        self._ecn = 0.0
        self._cur_min = None
        self._prev_min = None
        self._count = 0

    def observe_rtt(self, rtt_ms: float) -> None:
        self.srtt = rtt_ms if self.srtt is None else 0.875 * self.srtt + 0.125 * rtt_ms

        self._cur_min = rtt_ms if self._cur_min is None else min(self._cur_min, rtt_ms)
        self._count += 1
        if self._count >= self.rtt_min_window:
            self._prev_min, self._cur_min, self._count = self._cur_min, None, 0

    @property
    def rtt_min(self):
        mins = [m for m in (self._cur_min, self._prev_min) if m is not None]
        return min(mins) if mins else None

    def observe_ecn(self, ce_marked: bool) -> None:
        self._ecn = self.ecn_decay * self._ecn + (1.0 - self.ecn_decay) * (1.0 if ce_marked else 0.0)

    @property
    def inflation(self) -> float:
        if self.srtt is None or not self.rtt_min:
            return 0.0
        return max(0.0, (self.srtt - self.rtt_min) / self.rtt_min)

    @property
    def g(self) -> float:
        infl = self.inflation
        span = max(self.theta_hi - self.theta_lo, 1e-6)
        from_rtt = min(max((infl - self.theta_lo) / span, 0.0), 1.0)
        return max(from_rtt, min(self._ecn * 2.0, 1.0))
