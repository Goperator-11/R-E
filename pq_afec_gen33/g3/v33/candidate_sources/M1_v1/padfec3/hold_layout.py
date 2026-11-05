import itertools
import math

from padfec3 import layout as baseline
from padfec3.hold_decoder import FlightSpec, HoldConfig, HoldDecoder


def _config(uplink_mbps, config):
    if isinstance(uplink_mbps, bool) or not isinstance(uplink_mbps, (int, float)) or not math.isfinite(uplink_mbps) or uplink_mbps < 0:
        raise ValueError("uplink_mbps")
    rate = round(uplink_mbps * 1000)
    if abs(rate - uplink_mbps * 1000) > 1e-9:
        raise ValueError("uplink needs integer kbps")
    config = config or HoldConfig(uplink_kbps=rate)
    if config.uplink_kbps != rate:
        raise ValueError("receiver and model rate differ")
    return config


def _race(base, delays, sizes):
    branches = []
    previous = 1.0
    credit = base
    for delay, size in zip(delays, sizes, strict=True):
        q = baseline.policy.race_win_prob(delay)
        if previous - q > 0:
            branches.append((previous - q, credit))
        previous = q
        credit += size
    if previous > 0:
        branches.append((previous, credit))
    return branches


def outcomes(k, m, lead, w, p, uplink_mbps, *, config=None, loss_placement="before_link"):
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("p")
    if loss_placement not in ("before_link", "after_link"):
        raise ValueError("loss_placement")
    lead = baseline.resolve_lead(m, lead)
    baseline.check_action(k, m, lead)
    config = _config(uplink_mbps, config)
    spec = FlightSpec((w,) * k, m, lead, baseline.parity_bytes(w, k))
    order = spec.send_order
    sizes = [spec.size(*symbol) for symbol in order]
    for pattern in itertools.product((0, 1), repeat=len(order)):
        probability = 1.0
        for arrived in pattern:
            probability *= (1 - p) if arrived else p
        if probability == 0:
            continue
        decoder = HoldDecoder(spec, config)
        at_ns = 0
        arrival = [None] * len(order)
        for position, (kind, index) in enumerate(order):
            if pattern[position] or loss_placement == "after_link":
                at_ns += config.serialization_ns(sizes[position])
            if pattern[position]:
                arrival[position] = at_ns / 1_000_000
                decoder.receive_and_drain(kind, index, at_ns)
        if decoder.created_ns is not None and decoder.terminal is None:
            decoder.advance(max(decoder.now_ns, decoder.deadline_ns))
            decoder.drain()
        observed = decoder.result()
        rec = {"pattern": pattern, "pr": probability, "arrival_ms": arrival, "sizes": sizes,
               "lead_arrived": sum(pattern[:lead]), "orig_arrived": sum(pattern[lead:lead+k]),
               "miss": k - sum(pattern[lead:lead+k]), "trail_arrived": sum(pattern[lead+k:]),
               "phys_bytes": decoder.bytes_in, "decoder": observed,
               "model_kind": "M1_event_model", "loss_placement": loss_placement}
        seen, credit, complete_at = set(), 0, None
        for j, packet in enumerate(decoder.delivered):
            credit += packet.size
            if packet.kind == "o" and packet.size == w:
                seen.add(packet.index)
            if len(seen) == k:
                complete_at = j
                break
        if complete_at is None:
            last_original = pattern[lead + k - 1]
            rec["kind"] = "pto" if rec["orig_arrived"] == 0 else ("ptoS" if not last_original else "ack")
            rec["t_last_o"] = max([t for t in arrival[lead:lead+k] if t is not None] or [0.0])
        else:
            t_dec = decoder.delivered[complete_at].at_ns / 1_000_000
            after = decoder.delivered[complete_at + 1:]
            delays = [packet.at_ns / 1_000_000 - t_dec for packet in after]
            after_sizes = [packet.size for packet in after]
            rec.update(kind="ok", t_dec=t_dec, base_credit=credit, after_delays=delays, after_sizes=after_sizes,
                       phys_at_dec=sum(size for size, t in zip(sizes, arrival, strict=True) if t is not None and t <= t_dec),
                       branches=_race(credit, delays, after_sizes))
        yield rec


def evaluate(k, w, m, lead, p, rtt_ms, uplink_mbps, n_need, later="v3", *, config=None, loss_placement="before_link"):
    lead = baseline.resolve_lead(m, lead)
    baseline.check_action(k, m, lead)
    resp = baseline.response_term(m, w, uplink_mbps, later)
    a_pre = baseline.preflight_bytes(k, uplink_mbps)
    J = p1 = p2 = n_sum = succ = t_dec_sum = 0.0
    fails = []
    for rec in outcomes(k, m, lead, w, p, uplink_mbps, config=config, loss_placement=loss_placement):
        pr = rec["pr"]
        if rec["kind"] != "ok":
            fails.append(rec)
            continue
        for weight, credit in rec["branches"]:
            nr = baseline.rtt_count(credit, n_need, a_pre)
            hct = rec["t_dec"] + rtt_ms * nr + (resp if nr == 2 else 0.0)
            J += pr * weight * hct
            if nr == 1:
                p1 += pr * weight
            else:
                p2 += pr * weight
            n_sum += pr * weight * nr
            succ += pr * weight
            t_dec_sum += pr * weight * rec["t_dec"]
    pf = sum(f["pr"] for f in fails)
    n_ok = n_sum / succ if succ > 1e-15 else 2.0
    multiplier = 1.0 / (1.0 - pf) if pf < 1 else 1.0
    split = {kind: 0.0 for kind in baseline.FAIL_KINDS}
    for f in fails:
        kind = f["kind"]
        if kind == "pto":
            cost = rtt_ms + baseline.T_PTO_MS + baseline.tau(k * w, uplink_mbps)
        elif kind == "ptoS":
            cost = f["t_last_o"] + n_ok * rtt_ms + baseline.PTO_SAMPLED_MULT * rtt_ms
        else:
            cost = f["t_last_o"] + n_ok * rtt_ms + (baseline.T_ACK_SLOPE * rtt_ms + baseline.T_ACK_BASE_MS)
        J += f["pr"] * multiplier * cost
        split[kind] += f["pr"]
    return {"J": J, "p_one_rtt": p1, "p_two_rtt": p2, "p_success": succ, "p_fail": pf,
            "p_fail_pto": split["pto"], "p_fail_pto_sampled": split["ptoS"], "p_fail_ack": split["ack"],
            "n_rtt_expected": n_sum, "n_rtt_given_ok": n_ok, "round_mult": multiplier,
            "e": p2 + pf, "t_dec_given_ok": t_dec_sum / succ if succ > 1e-15 else 0.0,
            "response_term_ms": resp, "a_pre": a_pre, "client_bytes": baseline.client_bytes(k, m, w),
            "pre_decision_bytes": baseline.pre_decision_bytes(k, m, lead, w),
            "k": k, "m": m, "lead": lead, "trail": m - lead, "w": w, "later": later,
            "model_kind": "M1_event_model", "loss_placement": loss_placement,
            "hold_config": _config(uplink_mbps, config).__dict__}
