from __future__ import annotations

from dataclasses import dataclass, field


_CHANNEL_CACHE: dict = {}


def _mat_mul(a, b):
    return [
        [a[i][0] * b[0][j] + a[i][1] * b[1][j] for j in range(2)]
        for i in range(2)
    ]


def _mat_pow(m, n):
    result = [[1.0, 0.0], [0.0, 1.0]]
    base = [row[:] for row in m]
    while n > 0:
        if n & 1:
            result = _mat_mul(result, base)
        base = _mat_mul(base, base)
        n >>= 1
    return result


@dataclass
class GilbertElliott:
    q_gb: float
    q_bg: float
    p_good: float = 0.0
    p_bad: float = 1.0
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_burst(cls, p: float, mean_burst: float = 1.0) -> "GilbertElliott":
        p = min(max(p, 0.0), 0.999)
        if p <= 0.0:
            return cls(q_gb=0.0, q_bg=1.0)
        L = max(mean_burst, 1.0)

        l_min = p / (1.0 - p)
        if L < l_min:
            L = l_min
        q_bg = 1.0 / L
        q_gb = min(p * q_bg / (1.0 - p), 1.0)
        return cls(q_gb=q_gb, q_bg=q_bg)

    @classmethod
    def for_prior(cls, p: float, mean_burst: float = 1.0) -> "GilbertElliott":
        pc = min(max(p, 0.0), 0.999)
        if mean_burst <= 1.0 / (1.0 - pc):
            return cls.bernoulli(pc)
        return cls.from_burst(p, mean_burst)

    @classmethod
    def bernoulli(cls, p: float) -> "GilbertElliott":
        return cls(q_gb=0.5, q_bg=0.5, p_good=p, p_bad=p)

    @classmethod
    def cached(cls, p: float, mean_burst: float = 1.0) -> "GilbertElliott":
        key = (round(p * 1e4), round(mean_burst * 1e2))
        ch = _CHANNEL_CACHE.get(key)
        if ch is None:
            if len(_CHANNEL_CACHE) > 512:
                _CHANNEL_CACHE.clear()
            ch = cls.for_prior(key[0] / 1e4, key[1] / 1e2)
            _CHANNEL_CACHE[key] = ch
        return ch

    @property
    def transition(self):
        return [[1.0 - self.q_gb, self.q_gb], [self.q_bg, 1.0 - self.q_bg]]

    @property
    def stationary(self):
        total = self.q_gb + self.q_bg
        if total <= 0:
            return [1.0, 0.0]
        pi_bad = self.q_gb / total
        return [1.0 - pi_bad, pi_bad]

    @property
    def loss_rate(self) -> float:
        pi = self.stationary
        return pi[0] * self.p_good + pi[1] * self.p_bad

    @property
    def mean_burst(self) -> float:
        return 1.0 / self.q_bg if self.q_bg > 0 else float("inf")

    def pmf_table(self, n_max: int, interleave: int = 1):
        for name, v in (("q_gb", self.q_gb), ("q_bg", self.q_bg),
                        ("p_good", self.p_good), ("p_bad", self.p_bad)):
            if not (0.0 <= v <= 1.0):
                raise ValueError(
                    "GilbertElliott: %s=%r is not a probability - this chain "
                    "would make the DP produce negative/divergent values" 
                    % (name, v))

        key = (n_max, interleave)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        step = _mat_pow(self.transition, max(1, interleave))
        p00, p01 = step[0][0], step[0][1]
        p10, p11 = step[1][0], step[1][1]
        lg, lb = self.p_good, self.p_bad

        pi = self.stationary
        good = [pi[0]] + [0.0] * n_max
        bad = [pi[1]] + [0.0] * n_max
        table = [[1.0]]

        for n in range(1, n_max + 1):
            ng = [0.0] * (n + 1)
            nb = [0.0] * (n + 1)
            for c in range(n):
                wg, wb = good[c], bad[c]
                if wg:
                    keep, lose = wg * (1.0 - lg), wg * lg
                    ng[c] += keep * p00
                    nb[c] += keep * p01
                    ng[c + 1] += lose * p00
                    nb[c + 1] += lose * p01
                if wb:
                    keep, lose = wb * (1.0 - lb), wb * lb
                    ng[c] += keep * p10
                    nb[c] += keep * p11
                    ng[c + 1] += lose * p10
                    nb[c + 1] += lose * p11
            good, bad = ng, nb
            table.append([good[c] + bad[c] for c in range(n + 1)])

        self._cache[key] = table
        return table

    def joint_pmf_from(self, n_symbols: int, init=None, interleave: int = 1):
        for name, v in (("q_gb", self.q_gb), ("q_bg", self.q_bg),
                        ("p_good", self.p_good), ("p_bad", self.p_bad)):
            if not (0.0 <= v <= 1.0):
                raise ValueError(
                    "GilbertElliott: %s=%r is not a probability" % (name, v))
        step = _mat_pow(self.transition, max(1, interleave))
        p00, p01 = step[0][0], step[0][1]
        p10, p11 = step[1][0], step[1][1]
        lg, lb = self.p_good, self.p_bad
        pi = self.stationary if init is None else list(init)
        n = int(n_symbols)
        good = [pi[0]] + [0.0] * n
        bad = [pi[1]] + [0.0] * n
        for _ in range(n):
            ng = [0.0] * (n + 1)
            nb = [0.0] * (n + 1)
            for c in range(n):
                wg, wb = good[c], bad[c]
                if wg:
                    keep, lose = wg * (1.0 - lg), wg * lg
                    ng[c] += keep * p00
                    nb[c] += keep * p01
                    ng[c + 1] += lose * p00
                    nb[c + 1] += lose * p01
                if wb:
                    keep, lose = wb * (1.0 - lb), wb * lb
                    ng[c] += keep * p10
                    nb[c] += keep * p11
                    ng[c + 1] += lose * p10
                    nb[c + 1] += lose * p11
            good, bad = ng, nb
        return good, bad

    def erasure_pmf(self, n_symbols: int, interleave: int = 1):
        return self.pmf_table(n_symbols, interleave)[n_symbols]

    @staticmethod
    def _as_prob(x: float) -> float:
        return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

    def p_fail(self, k: int, r: int, interleave: int = 1) -> float:
        pmf = self.pmf_table(k + r, interleave)[k + r]
        return self._as_prob(sum(pmf[r + 1:]))

    def fail_curve(self, k: int, r_max: int, interleave: int = 1):
        table = self.pmf_table(k + r_max, interleave)
        return [self._as_prob(sum(table[k + r][r + 1:]))
                for r in range(r_max + 1)]
