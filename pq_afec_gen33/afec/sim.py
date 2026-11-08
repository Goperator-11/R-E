from __future__ import annotations

import random
from dataclasses import dataclass

from .channel import GilbertElliott
from .controller import (AdaptiveFecController, FecConfig, choose_block_size,
                         choose_redundancy, pto_ms)
from .estimator import CongestionDetector, LossEstimator


class ChannelSampler:
    def __init__(self, channel: GilbertElliott, rng: random.Random):
        self.ch = channel
        self.rng = rng
        self.reset_state()

    def reset_state(self) -> None:
        self.state = 1 if self.rng.random() < self.ch.stationary[1] else 0

    def send(self, n: int) -> list[bool]:
        out = []
        for _ in range(n):
            pl = self.ch.p_bad if self.state == 1 else self.ch.p_good
            out.append(self.rng.random() < pl)
            q = self.ch.q_gb if self.state == 0 else self.ch.q_bg
            if self.rng.random() < q:
                self.state ^= 1
        return out


class LossTrace:
    __slots__ = ("bitmap", "n", "label")

    def __init__(self, bitmap: bytes, n: int, label: str = "trace"):
        if n > len(bitmap) * 8:
            raise ValueError("bitmap too short for n=%d" % n)
        self.bitmap = bitmap
        self.n = n
        self.label = label

    @classmethod
    def from_bits(cls, lost_flags, label: str = "trace") -> "LossTrace":
        flags = list(lost_flags)
        bm = bytearray((len(flags) + 7) // 8)
        for i, lost in enumerate(flags):
            if not lost:
                bm[i >> 3] |= 1 << (i & 7)
        return cls(bytes(bm), len(flags), label)

    def lost(self, i: int) -> bool:
        i %= self.n
        return not (self.bitmap[i >> 3] >> (i & 7)) & 1

    @property
    def loss_rate(self) -> float:
        return sum(1 for i in range(self.n) if self.lost(i)) / self.n


class TraceSampler:
    def __init__(self, trace: LossTrace, rng: random.Random,
                 stride: int = 0, mode: str = "positional",
                 offset: int = 0):
        self.trace = trace
        self.rng = rng
        self.stride = max(1, stride)
        self.mode = mode
        self.offset = offset % trace.n
        self.pos = self.offset
        self.block = 0

    def reset_state(self) -> None:
        self.pos = self.rng.randrange(self.trace.n)

    def start_block(self, index: int) -> None:
        if self.mode == "positional":
            self.pos = (self.offset + index * self.stride) % self.trace.n
        self.block = index

    def send(self, n: int) -> list[bool]:
        out = [self.trace.lost(self.pos + i) for i in range(n)]
        self.pos = (self.pos + n) % self.trace.n
        return out


def runs_of_losses(mask: list[bool]) -> list[int]:
    runs, cur = [], 0
    for lost in mask:
        if lost:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return runs


@dataclass
class HandshakeAnalytic:
    mean_ms: float
    stall_prob: float
    f_client: float
    f_server: float
    bytes_sent: int


def expected_handshake_ms(k_client: int, k_server: int, r_client: int, r_server: int,
                          p: float, burst: float, rtt_ms: float,
                          max_attempts: int = 6, interleave: int = 1,
                          symbol_bytes: int = 1200, ack_partial: bool = True,
                          srtt_ms: float | None = None,
                          server_critical: int | None = None) -> HandshakeAnalytic:
    ch = GilbertElliott.cached(p, burst)
    base = pto_ms(srtt_ms)
    t_fast = 2.0 * rtt_ms
    total = rtt_ms
    fails = []
    for idx, (k, r) in enumerate(((k_client, r_client), (k_server, r_server))):
        n = k + r
        pmf = ch.erasure_pmf(n, interleave)
        f = sum(pmf[r + 1:])
        if not ack_partial:
            ft = f
        elif idx == 1 and server_critical:
            m = min(server_critical + r, n)
            ft = min(ch.erasure_pmf(m, interleave)[m], f)
        else:
            ft = pmf[n]
        fp = f - ft
        if f > 0.0:
            total += sum((f ** a) * ((fp / f) * t_fast
                                     + (ft / f) * base * (2 ** (a - 1)))
                         for a in range(1, max_attempts + 1))
        fails.append(f)

    stall = 1.0 - (1.0 - fails[0]) * (1.0 - fails[1])
    nbytes = (k_client + r_client + k_server + r_server) * symbol_bytes
    return HandshakeAnalytic(mean_ms=total, stall_prob=stall,
                             f_client=fails[0], f_server=fails[1],
                             bytes_sent=nbytes)


@dataclass
class HandshakeResult:
    mean_ms: float
    p95_ms: float
    stall_rate: float
    bytes_sent: int


def simulate_handshake(k_client: int, k_server: int, r_client: int, r_server: int,
                       p: float, burst: float, rtt_ms: float,
                       trials: int = 20000, seed: int = 1,
                       symbol_bytes: int = 1200,
                       ack_partial: bool = True,
                       retry_decorrelate: bool = True,
                       trace: "LossTrace | None" = None) -> HandshakeResult:
    rng = random.Random(seed)
    ch = None if trace is not None else GilbertElliott.from_burst(p, burst)
    times, stalls, total_bytes = [], 0, 0

    for _ in range(trials):
        if trace is not None:
            sampler = TraceSampler(trace, rng, mode="sequential",
                                   offset=rng.randrange(trace.n))
        else:
            sampler = ChannelSampler(ch, rng)
        t = rtt_ms
        stalled = False
        sent = 0

        for k, r in ((k_client, r_client), (k_server, r_server)):
            attempt = 0
            while True:
                mask = sampler.send(k + r)
                sent += (k + r) * symbol_bytes
                n_lost = sum(mask)
                if n_lost <= r:
                    break
                if ack_partial and n_lost < k + r:
                    t += 2.0 * rtt_ms
                else:
                    t += pto_ms(backoff=attempt)
                if retry_decorrelate:
                    sampler.reset_state()
                stalled = True
                attempt += 1
                if attempt > 6:
                    break

        times.append(t)
        stalls += 1 if stalled else 0
        total_bytes += sent

    times.sort()
    return HandshakeResult(
        mean_ms=sum(times) / len(times),
        p95_ms=times[int(0.95 * (len(times) - 1))],
        stall_rate=stalls / trials,
        bytes_sent=total_bytes // trials,
    )


@dataclass
class DataResult:
    label: str
    total_ms: float
    goodput_mbps: float
    overhead: float
    block_fail_rate: float
    mean_r: float
    snapshot: tuple | None = None


def simulate_data(policy: str, p: float, burst: float, rtt_ms: float,
                  cfg: FecConfig, n_blocks: int = 400, seed: int = 7,
                  static_ratio: float = 0.25, prior=None,
                  trace: "LossTrace | None" = None) -> DataResult:
    rng = random.Random(seed)
    symbol_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
    t_recover = 2.0 * rtt_ms
    k = choose_block_size(cfg)

    if trace is not None:
        r_max = min(max(int(round(k * cfg.rho_max)), 1), max(255 - k, 1))
        sampler = TraceSampler(trace, rng, stride=k + r_max,
                               offset=rng.randrange(trace.n))
    else:
        ch = GilbertElliott.from_burst(p, burst)
        sampler = ChannelSampler(ch, rng)

    ctrl = None
    if policy in ("adaptive", "warm", "cached"):
        if policy == "cached":
            if prior is None:
                raise ValueError("policy='cached' needs prior=(p, burst, weight)")
            pp = getattr(prior, "p", None)
            if pp is None:
                pp, pb, pw = prior
            else:
                pb, pw = prior.burst, prior.weight
            est = LossEstimator(p_init=pp, burst_init=pb, prior_weight=pw,
                                z=cfg.risk_z)
        else:
            p_init = p if policy == "warm" else 0.005
            est = LossEstimator(p_init=p_init, z=cfg.risk_z)
            if policy == "warm":
                est.burst = burst
        ctrl = AdaptiveFecController(cfg, est, CongestionDetector())
        ctrl.cong.observe_rtt(rtt_ms)

    total_ms = 0.0
    sent_symbols = source_symbols = 0
    fails = 0
    r_sum = 0

    rq_ratio = 0.1
    rq_window: list[bool] = []
    rq_win_blocks = max(3, int(round(3.0 * rtt_ms
                                     / max(k * symbol_ms, 1e-6))))

    block_ms = k * symbol_ms
    lag = max(1, int(round(rtt_ms / max(block_ms, 1e-6))))
    pending: list[tuple[int, list[bool]]] = []

    for block_index in range(n_blocks):
        if trace is not None:
            sampler.start_block(block_index)
        if policy == "none":
            r = 0
        elif policy == "static":
            r = max(1, int(round(k * static_ratio)))
        elif policy == "oracle":
            r = choose_redundancy(k, p, burst, t_recover, 0.0, cfg).r
        elif policy == "rquic":
            if len(rq_window) >= rq_win_blocks:
                residual = sum(rq_window) / len(rq_window)
                rq_ratio *= (1.0 + 0.33) if residual > 0.01 else (1.0 - 0.33)
                rq_ratio = min(max(rq_ratio, 1.0 / k), cfg.rho_max)
                rq_window.clear()
            r = max(1, int(round(k * rq_ratio)))
        else:
            r = ctrl.next_block().r

        mask = sampler.send(k + r)
        n_lost = sum(mask)
        failed = n_lost > r

        sent_symbols += k + r
        source_symbols += k
        r_sum += r
        total_ms += (k + r) * symbol_ms
        if failed:
            fails += 1
            total_ms += t_recover
        if policy == "rquic":
            rq_window.append(failed)

        if ctrl is not None:
            pending.append((k + r, mask))
            if len(pending) > lag:
                _, old = pending.pop(0)
                ctrl.on_feedback(old, rtt_ms=rtt_ms)

    source_bits = source_symbols * cfg.symbol_bytes * 8.0
    return DataResult(
        label=policy,
        total_ms=total_ms,
        goodput_mbps=source_bits / (total_ms / 1000.0) / 1e6,
        overhead=(sent_symbols - source_symbols) / source_symbols,
        block_fail_rate=fails / n_blocks,
        mean_r=r_sum / n_blocks,
        snapshot=ctrl.loss.snapshot() if ctrl is not None else None,
    )
