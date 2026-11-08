from __future__ import annotations

import math
from dataclasses import dataclass

from .channel import GilbertElliott
from .controller import Decision, FecConfig, pto_ms

ML_KEM_SIZES = {
    512: (800, 768),
    768: (1184, 1088),
    1024: (1568, 1568),
}
X25519_BYTES = 32


INITIAL_CRYPTO_CAPACITY = 1150

CH_BASE_MINIMAL_QUIC = 232
CH_BASE_BROWSER_QUIC = 508
CH_BASE_CLASSICAL_MIN = 240

SH_BASE = 90

CERT_FLIGHT_CLOUDFLARE = 2955
CERT_FLIGHT_GOOGLE = 5299
CERT_FLIGHT_DEFAULT = CERT_FLIGHT_CLOUDFLARE


@dataclass
class HandshakeProfile:
    kem: str
    client_share: int
    server_share: int
    client_flight: int
    server_flight: int
    k_client: int
    k_server: int
    server_initial_flight: int = 0
    server_handshake_flight: int = 0
    k_server_initial: int = 0
    k_server_handshake: int = 0

    @property
    def amplification_budget(self) -> int:
        return 3 * self.k_client * 1200


def profile(level: int | None = 768, hybrid: bool = True,
            ch_base: int = CH_BASE_BROWSER_QUIC,
            cert_chain: int = CERT_FLIGHT_DEFAULT) -> HandshakeProfile:
    if level is None:
        name = "x25519"
        ck = sk = X25519_BYTES
    else:
        ek, ct = ML_KEM_SIZES[level]
        name = f"{'x25519+' if hybrid else ''}mlkem{level}"
        extra = X25519_BYTES if hybrid else 0
        ck, sk = ek + extra, ct + extra

    def npkt(nbytes):
        return max(1, -(-nbytes // INITIAL_CRYPTO_CAPACITY))

    client_flight = ch_base + ck
    server_initial = SH_BASE + sk
    server_hs = cert_chain
    k_si = npkt(server_initial)
    k_sh = npkt(server_hs)

    return HandshakeProfile(
        kem=name, client_share=ck, server_share=sk,
        client_flight=client_flight,
        server_flight=server_initial + server_hs,
        k_client=npkt(client_flight),
        k_server=k_si + k_sh,
        server_initial_flight=server_initial,
        server_handshake_flight=server_hs,
        k_server_initial=k_si,
        k_server_handshake=k_sh,
    )


def shield(prof: HandshakeProfile, p_prior: float, burst_prior: float = 1.0,
           cfg: FecConfig | None = None, side: str = "client",
           ack_partial: bool = True, srtt_ms: float | None = None,
           rtt_prior_ms: float = 100.0) -> Decision:
    cfg = cfg or FecConfig()

    if side == "client":
        k = prof.k_client
    elif side == "server":
        k = prof.k_server_initial or prof.k_server
    elif side == "server_certs":
        k = prof.k_server_handshake or prof.k_server
    else:
        raise ValueError("side must be client | server | server_certs")

    ch = GilbertElliott.for_prior(p_prior, burst_prior)

    base = pto_ms(srtt_ms)
    rtt_for_fast = srtt_ms if srtt_ms is not None else rtt_prior_ms
    t_fast = 2.0 * rtt_for_fast
    t_fast = min(t_fast, base)

    if side == "server_certs":
        base = t_fast

    byte_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
    rho = getattr(cfg, "handshake_rho_max", cfg.rho_max)
    r_max = min(max(int(math.ceil(k * rho)), 1), max(255 - k, 0))

    best = None
    table = []
    for r in range(r_max + 1):
        n = k + r
        pmf = ch.erasure_pmf(n)
        f = sum(pmf[r + 1:])
        ft = pmf[n] if ack_partial else f
        fp = f - ft
        cost = r * byte_ms + fp * t_fast + ft * base
        table.append((r, cost, f))
        if best is None or cost < best[1] - 1e-12:
            best = (r, cost, f, ft)

    r_star, cost, f, ft = best
    _cap_bound = (r_star == r_max and r_max > 0)
    t_eff = ((f - ft) * t_fast + ft * base) / f if f > 0 else base
    d = Decision(k=k, r=r_star, p_used=p_prior, burst_used=burst_prior,
                 g=0.0, t_recover_ms=t_eff, p_fail=f, cost=cost, table=table)
    d.cap_bound = _cap_bound
    return d
