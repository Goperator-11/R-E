from __future__ import annotations

import math

MIN_INITIAL_DATAGRAM = 1200

DEFAULT_H = 51

DEFAULT_F = 16


def inplace_capacity(k, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    if k < 2:
        return 0
    return (k - 1) * (W - h - f)


def natural_k(C, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H):
    per = W - h
    if per <= 0:
        raise ValueError("W 가 패킷 고정비용보다 작다")
    return max(1, int(math.ceil(float(C) / per)))


def inplace_feasible(C, k, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    return C <= inplace_capacity(k, W, h, f)


def min_k_for_inplace(C, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    per = W - h - f
    if per <= 0:
        return None
    return int(math.ceil(float(C) / per)) + 1


def parity_symbol_bytes(C, k, h=DEFAULT_H):
    return int(math.ceil(float(C) / k)) + h


def describe(C, W=MIN_INITIAL_DATAGRAM, h=DEFAULT_H, f=DEFAULT_F):
    k = natural_k(C, W, h)
    cap = inplace_capacity(k, W, h, f)
    need = min_k_for_inplace(C, W, h, f)
    flight = k * W
    return {
        "C": C, "W": W, "h": h, "f": f,
        "k_natural": k,
        "flight_bytes": flight,
        "fill_ratio": float(C) / (k * (W - h)),
        "inplace_capacity": cap,
        "inplace_feasible": C <= cap,
        "k_needed_for_inplace": need,
        "extra_datagrams": (None if need is None else max(0, need - k)),
        "extra_bytes": (None if need is None else max(0, need - k) * W),
        "protectable_at_all": k >= 2,
    }
