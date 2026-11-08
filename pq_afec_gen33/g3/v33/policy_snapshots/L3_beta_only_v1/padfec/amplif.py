from __future__ import annotations

AMPLIFICATION_FACTOR = 3

SERVER_PACKET_SIZE = 1280


def budget(client_bytes):
    return AMPLIFICATION_FACTOR * client_bytes


def server_flight(cert_bytes, s0):
    return cert_bytes + s0


def allowed_bytes(client_bytes, pkt=SERVER_PACKET_SIZE):
    b = budget(client_bytes)
    if pkt <= 0:
        return b
    n = (b - 1) // pkt + 1 if b > 0 else 0
    return n * pkt


def rtt_count(cert_bytes, client_bytes, s0, pkt=SERVER_PACKET_SIZE):
    return 1 if server_flight(cert_bytes, s0) <= allowed_bytes(
        client_bytes, pkt) else 2


def threshold_cert(client_bytes, s0, pkt=SERVER_PACKET_SIZE):
    return allowed_bytes(client_bytes, pkt) - s0


def exchange_ratio():
    return float(AMPLIFICATION_FACTOR)


def credit_rtt(cert_bytes, client_bytes, extra_bytes, s0):
    before = rtt_count(cert_bytes, client_bytes, s0)
    after = rtt_count(cert_bytes, client_bytes + extra_bytes, s0)
    return before - after


def fit_s0(threshold_lo, threshold_hi, client_bytes,
           pkt=SERVER_PACKET_SIZE):
    b = allowed_bytes(client_bytes, pkt)
    return {"allowed": b, "budget": budget(client_bytes),
            "s0_lo": b - threshold_hi, "s0_hi": b - threshold_lo,
            "s0_mid": b - 0.5 * (threshold_lo + threshold_hi)}
