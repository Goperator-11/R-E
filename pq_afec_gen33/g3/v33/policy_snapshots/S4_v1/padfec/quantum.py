from __future__ import annotations

try:
    from . import capacity
except ImportError:
    import os as _os
    import sys as _sys

    _sys.path.insert(
        0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from padfec import capacity

P_SERVER = 1280

AMP = 3

TYPICAL_MTU = 1500


def _ceil_div(a, b):
    if b <= 0:
        raise ValueError("나눗수는 양수여야 한다: %r" % (b,))
    return -((-a) // b)


def _require_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("%s 는 정수여야 한다: %r" % (name, value))
    return value


def allowed(client_bytes, pkt=P_SERVER):
    if client_bytes <= 0:
        return 0
    if pkt <= 0:
        return AMP * client_bytes
    return _ceil_div(AMP * client_bytes, pkt) * pkt


def bin_index(client_bytes, pkt=P_SERVER):
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 칸이 정의되지 않는다")
    if client_bytes <= 0:
        return 0
    return _ceil_div(AMP * client_bytes, pkt)


def delta_min(client_bytes, steps=1, pkt=P_SERVER):
    _require_int("client_bytes", client_bytes)
    _require_int("steps", steps)
    _require_int("pkt", pkt)
    if steps <= 0:
        return 0
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 칸이 정의되지 않는다")
    b = client_bytes if client_bytes > 0 else 0
    target = (bin_index(b, pkt) + steps - 1) * pkt
    return (target - AMP * b) // AMP + 1


def boundary_W(k, W, steps=1, pkt=P_SERVER):
    if k <= 0:
        raise ValueError("k 는 1 이상이어야 한다: %r" % (k,))
    if steps <= 0:
        return W
    return W + _ceil_div(delta_min(k * W, steps, pkt), k)


def on_boundary(client_bytes, pkt=P_SERVER):
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 경계가 정의되지 않는다")
    if client_bytes <= 0:
        return False
    return (AMP * client_bytes) % pkt == 0


def s0_at(bin_n, s0_base, c_pkt):
    if bin_n < 0:
        raise ValueError("칸 번호는 음수일 수 없다: %r" % (bin_n,))
    return float(s0_base) + bin_n * float(c_pkt)


def threshold(client_bytes, s0_base, c_pkt, pkt=P_SERVER):
    a = allowed(client_bytes, pkt)
    n_pkt = (a // pkt) if pkt > 0 else 0
    return a - s0_at(n_pkt, s0_base, c_pkt)


def _candidate(mode, m, delta, C, W, h, f, cert_bytes, s0,
               base_bytes, base_bin, pkt, k_floor=1,
               s0_base=None, c_pkt=0.0, parity_bytes=None):
    w_eff = W + delta
    k = max(k_floor, capacity.natural_k(C, w_eff, h))
    pbytes = (w_eff if parity_bytes is None else int(parity_bytes(w_eff, k)))
    client_bytes = k * w_eff + m * pbytes
    a = allowed(client_bytes, pkt)
    if s0_base is None:
        s0_eff = float(s0)
    else:
        s0_eff = s0_at((a // pkt) if pkt > 0 else 0, s0_base, c_pkt)
    flight = cert_bytes + s0_eff
    return {
        "mode": mode,
        "steps": bin_index(client_bytes, pkt) - base_bin,
        "m": m,
        "delta_per_dgram": delta,
        "parity_bytes": pbytes,
        "W_eff": w_eff,
        "k": k,
        "client_bytes": client_bytes,
        "credit_bytes": client_bytes,
        "added_bytes": client_bytes - base_bytes,
        "allowed": a,
        "s0_eff": s0_eff,
        "s0_eff_basis": "A/P",
        "server_flight": flight,
        "n_need": bin_needed(cert_bytes, s0, s0_base, c_pkt, pkt),
        "n_rtt": 1 if flight <= a else 2,
        "over_mtu": w_eff > TYPICAL_MTU,
        "late_parity_risk": False,
        "inplace_feasible": capacity.inplace_feasible(C, k + m, w_eff, h, f),
    }


def bin_needed(cert_bytes, s0, s0_base=None, c_pkt=0.0, pkt=P_SERVER):
    if pkt <= 0:
        raise ValueError("pkt <= 0 이면 칸이 정의되지 않는다")
    if s0_base is None:
        if s0 is None:
            raise ValueError("s0 또는 s0_base 중 하나는 있어야 한다")
        S = float(cert_bytes) + float(s0)
        return max(1, _ceil_div(int(S) if float(S).is_integer()
                                else int(S) + 1, pkt))
    if float(c_pkt) >= float(pkt):
        raise ValueError("c_pkt 가 pkt 이상이면 칸을 올려도 못 따라잡는다")
    n = int((float(cert_bytes) + float(s0_base)) / (float(pkt) - float(c_pkt)))
    while n * pkt < float(cert_bytes) + float(s0_base) + n * float(c_pkt):
        n += 1
    return max(1, n)


def _combo_deltas(k, m, W, ovh, n_need, pkt=P_SERVER, max_delta=None):
    need = ((n_need - 1) * pkt) // AMP + 1
    out = set()
    g = 0 if m <= 0 else (1 if m == 1 else m - 1)
    for a in range(k + 1):
        for b in range(m + 1):
            if a + b == 0:
                continue
            used = k - a
            if used > min(b, g):
                continue
            lack = need - (a + b) * W - (b - used) * ovh
            if lack <= 0:
                continue
            d = _ceil_div(lack, a + b)
            if d < 1:
                continue
            if max_delta is not None and d > max_delta:
                continue
            out.add(d)
    return sorted(out)


def levers(C, cert_bytes, s0, W=P_SERVER, h=51, f=16, max_steps=2, m_max=3,
           s0_base=None, c_pkt=0.0, parity_bytes=None, max_delta=None):
    _require_int("C", C)
    _require_int("W", W)
    _require_int("h", h)
    _require_int("f", f)
    _require_int("max_steps", max_steps)
    _require_int("m_max", m_max)
    if C <= 0:
        raise ValueError("C 는 양수여야 한다: %r" % (C,))
    if W < capacity.MIN_INITIAL_DATAGRAM:
        raise ValueError("W 는 %d 이상이어야 한다(RFC 9000 §14.1): %r"
                         % (capacity.MIN_INITIAL_DATAGRAM, W))
    if m_max < 0 or max_steps < 0:
        raise ValueError("max_steps, m_max 는 음수일 수 없다")
    if s0 is None and s0_base is None:
        raise ValueError("s0(상수) 또는 s0_base(명세 §2.5 패킷항) 중 하나는 "
                         "있어야 한다")
    if s0_base is None and c_pkt != 0:
        raise ValueError("c_pkt=%r 를 줬는데 s0_base 가 없다 - 패킷항이 조용히 "
                         "무시되고 상수 s0 모형으로 되돌아간다. s0_base 를 함께 "
                         "주거나 c_pkt 를 빼라" % (c_pkt,))

    pkt = P_SERVER
    k0 = capacity.natural_k(C, W, h)
    base_bytes = k0 * W
    base_bin = bin_index(base_bytes, pkt)

    def mk(mode, m, delta, k_floor=k0):
        return _candidate(mode, m, delta, C, W, h, f, cert_bytes, s0,
                          base_bytes, base_bin, pkt, k_floor=k_floor,
                          s0_base=s0_base, c_pkt=c_pkt,
                          parity_bytes=parity_bytes)

    out = [mk("none", 0, 0)]

    for j in range(1, max_steps + 1):
        d_pad = _ceil_div(delta_min(base_bytes, j, pkt), k0)
        out.append(mk("pad", 0, d_pad))
        if capacity.natural_k(C, W + d_pad, h) < k0:
            out.append(mk("pad_repack", 0, d_pad, k_floor=1))

    for m in range(1, m_max + 1):
        out.append(mk("parity", m, 0))

    for j in range(1, max_steps + 1):
        d_j = delta_min(base_bytes, j, pkt)
        if d_j >= W:
            per = W if parity_bytes is None else int(parity_bytes(W, k0))
            out.append(mk("parity", _ceil_div(d_j, per), 0))

    seen = set()
    uniq = []
    for c in out:
        key = (c["mode"], c["client_bytes"], c["m"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    n_need = bin_needed(cert_bytes, s0, s0_base, c_pkt, pkt)
    ovh = 0 if parity_bytes is None else int(parity_bytes(W, k0)) - W
    byte_seen = set((c["client_bytes"], c["m"]) for c in uniq)
    for m in range(0, m_max + 1):
        for d in _combo_deltas(k0, m, W, ovh, n_need, pkt, max_delta):
            c = mk("combo", m, d)
            key = (c["client_bytes"], c["m"])
            if key in byte_seen:
                continue
            byte_seen.add(key)
            uniq.append(c)
    return uniq


def dominates(a, b):
    ge = (a["added_bytes"] <= b["added_bytes"]
          and a["allowed"] >= b["allowed"]
          and a["m"] >= b["m"]
          and a["W_eff"] >= b["W_eff"])
    if not ge:
        return False
    return (a["added_bytes"] < b["added_bytes"]
            or a["allowed"] > b["allowed"]
            or a["m"] > b["m"]
            or a["W_eff"] > b["W_eff"])


if __name__ == "__main__":
    import sys

    try:
        from padfec import amplif
    except ImportError:
        from . import amplif

    _results = []

    def check(name, cond, detail=""):
        _results.append((bool(cond), name, detail))
        print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                             ("  | " + detail) if detail else ""))

    def info(msg):
        print("[INFO] " + msg)

    print("=" * 72)
    print("padfec/quantum.py self-test   "
          "(spec: PAD-FEC v2, sections 1-3 / 2.5 / 2.6)")
    print("=" * 72)

    bad = [k for k in range(1, 9) if delta_min(k * 1280) != 1]
    check("1. corollary delta_min(k*1280)==1 for k=1..8", not bad,
          "k=1..8 all 1 B" if not bad else "violations at k=%s" % bad)
    notb = [k for k in range(1, 9) if not on_boundary(k * 1280)]
    check("1b. on_boundary(k*1280) true for k=1..8", not notb,
          "3B is always a multiple of P" if not notb else "off at k=%s" % notb)

    d1200 = delta_min(1200)
    bw1200 = boundary_W(1, 1200)
    check("2. delta_min(1200)==81 and boundary_W(1,1200)==1281",
          d1200 == 81 and bw1200 == 1281,
          "delta_min=%d  boundary_W=%d  A(1200)=%d" % (d1200, bw1200,
                                                       allowed(1200)))

    cliff_bad = []
    for kk in (1, 2):
        lo = set(bin_index(kk * i) for i in (1279, 1280))
        hi = set(bin_index(kk * i) for i in (1281, 1282, 1350))
        if not (len(lo) == 1 and len(hi) == 1 and min(hi) == min(lo) + 1):
            cliff_bad.append((kk, sorted(lo), sorted(hi)))
    check("2b. bins: 1279==1280 (negative control), 1281==1282==1350, +1 step",
          not cliff_bad,
          "k=1 bins 3->4, k=2 bins 6->7" if not cliff_bad
          else "%r" % (cliff_bad,))

    b1, b2 = boundary_W(1, 1280), boundary_W(2, 1280)
    check("3. boundary_W(1,1280)==boundary_W(2,1280)==1281",
          b1 == 1281 and b2 == 1281,
          "k=1 -> %d, k=2 -> %d (k does not move the boundary)" % (b1, b2))
    check("3b. the two computations agree with the W=1200 route",
          bw1200 == b1 == b2, "1200-route=%d  1280-route=%d" % (bw1200, b1))

    want = [(1280, 3840), (1281, 5120), (2560, 7680), (2562, 8960)]
    got = [(b, allowed(b)) for b, _ in want]
    check("4. allowed() spot values", got == want,
          " ".join("A(%d)=%d" % (b, a) for b, a in got))

    t1 = allowed(1280) - 500.0
    t2 = allowed(2560) - 1734.5
    in1 = 3312 <= t1 <= 3368
    in2 = 5917 <= t2 <= 5974
    check("5. cert threshold prediction inside measured band",
          t1 == 3340.0 and t2 == 5945.5 and in1 and in2,
          "x25519 %.1f in [3312,3368]=%s ; MLKEM %.1f in [5917,5974]=%s"
          % (t1, in1, t2, in2))

    S0_ANCHOR = [(3, 380.0, 40.0, 500.0), (6, 1494.5, 40.0, 1734.5)]
    s0_bad = [(n, s0_at(n, b, c), w) for n, b, c, w in S0_ANCHOR
              if s0_at(n, b, c) != w]
    S0_PRED = [(4, 380.0, 40.0, 506.0, 563.0),
               (7, 1494.5, 40.0, 1741.0, 1797.0)]
    s0_bad += [(n, s0_at(n, b, c), lo_, hi_) for n, b, c, lo_, hi_ in S0_PRED
               if not (lo_ <= s0_at(n, b, c) <= hi_)]
    check("5b. s0_at() hits both anchors and predicts the other bin in band",
          not s0_bad,
          "anchors s0(3)=%.1f s0(6)=%.1f ; preds s0(4)=%.1f s0(7)=%.1f"
          % (s0_at(3, 380.0, 40.0), s0_at(6, 1494.5, 40.0),
             s0_at(4, 380.0, 40.0), s0_at(7, 1494.5, 40.0))
          if not s0_bad else "%r" % (s0_bad,))

    BANDS = [
        ("x25519 ips=1280", 1280, 380.0, 3312, 3368, 3340.0),
        ("x25519 ips=1350", 1350, 380.0, 4557, 4614, 4580.0),
        ("MLKEM  ips=1280", 2560, 1494.5, 5917, 5974, 5945.5),
        ("MLKEM  ips=1350", 2700, 1494.5, 7163, 7219, 7185.5),
    ]
    band_bad, band_txt = [], []
    for lbl, B, sb, lo_b, hi_b, want_t in BANDS:
        t = threshold(B, sb, 40.0)
        band_txt.append("%s %.1f" % (lbl.split()[0], t))
        if not (t == want_t and lo_b <= t <= hi_b):
            band_bad.append((lbl, t, lo_b, hi_b, want_t))
    check("5c. threshold() inside every measured band (4/4)", not band_bad,
          " ".join(band_txt) if not band_bad else "%r" % (band_bad,))

    CONST_S0 = {380.0: 500.0, 1494.5: 1734.5}
    const_out, pkt_in = 0, 0
    const_txt = []
    for lbl, B, sb, lo_b, hi_b, _ in BANDS:
        t_const = amplif.threshold_cert(B, CONST_S0[sb])
        t_pkt = threshold(B, sb, 40.0)
        if not (lo_b <= t_const <= hi_b):
            const_out += 1
        if lo_b <= t_pkt <= hi_b:
            pkt_in += 1
        const_txt.append("%s const=%.1f pkt=%.1f d=%+.1f"
                         % (lbl.split()[0], t_const, t_pkt, t_const - t_pkt))
    check("5c2. constant-s0 leaves the band at the higher bin, packet term "
          "stays in", const_out == 2 and pkt_in == 4,
          "%d/4 const outside, %d/4 packet-term inside | %s"
          % (const_out, pkt_in, " ; ".join(const_txt)))

    NEWPRED = [("x25519 ips=1707 bin5", 1707, 380.0, 5820.0),
               ("x25519 ips=2134 bin6", 2134, 380.0, 7060.0),
               ("MLKEM  ips=1281 bin7", 2562, 1494.5, 7185.5)]
    np_bad = [(l, threshold(B, sb, 40.0), w) for l, B, sb, w in NEWPRED
              if threshold(B, sb, 40.0) != w]
    check("5d. threshold() reproduces the p12c predictions", not np_bad,
          " ".join("%s=%.1f" % (l.split()[-1], threshold(B, sb, 40.0))
                   for l, B, sb, _ in NEWPRED) if not np_bad
          else "%r" % (np_bad,))

    CLIFF = [
        ("x25519 1279", 1, 1279, 4000, 380.0, 2),
        ("x25519 1280", 1, 1280, 4000, 380.0, 2),
        ("x25519 1281", 1, 1281, 4000, 380.0, 1),
        ("x25519 1282", 1, 1282, 4000, 380.0, 1),
        ("x25519 1350", 1, 1350, 4000, 380.0, 1),
        ("MLKEM  1279", 2, 1279, 6500, 1494.5, 2),
        ("MLKEM  1280", 2, 1280, 6500, 1494.5, 2),
        ("MLKEM  1281", 2, 1281, 6500, 1494.5, 1),
        ("MLKEM  1282", 2, 1282, 6500, 1494.5, 1),
        ("MLKEM  1350", 2, 1350, 6500, 1494.5, 1),
    ]
    cl_bad = [lbl for lbl, kk, ips, cert, sb, obs in CLIFF
              if (1 if cert <= threshold(kk * ips, sb, 40.0) else 2) != obs]
    check("5e. predicted n_rtt == observed n_rtt on all 10 probe_cliff points",
          not cl_bad, "10/10 (x25519 cert=4000, MLKEM cert=6500)"
          if not cl_bad else "misses: %r" % (cl_bad,))

    LO, HI = 1200, 20000
    v_a = v_b = v_c = v_d = v_x = 0
    first_bad = None
    only_dmin1 = 0
    for B in range(LO, HI + 1):
        A = allowed(B)
        dm = delta_min(B)
        if A < AMP * B:
            v_a += 1
            first_bad = first_bad or ("a", B)
        if A - AMP * B >= 1280:
            v_b += 1
            first_bad = first_bad or ("b", B)
        if bin_index(B + dm) != bin_index(B) + 1:
            v_c += 1
            first_bad = first_bad or ("c", B)
        if dm < 1:
            v_d += 1
            first_bad = first_bad or ("d", B)
        if A != amplif.allowed_bytes(B):
            v_x += 1
            first_bad = first_bad or ("x", B)
        if dm == 1 and not on_boundary(B):
            only_dmin1 += 1
    n = HI - LO + 1
    check("6a. allowed(B) >= 3B          (B=%d..%d, n=%d)" % (LO, HI, n),
          v_a == 0, "%d violations" % v_a)
    check("6b. allowed(B) - 3B < 1280", v_b == 0, "%d violations" % v_b)
    check("6c. bin_index(B+delta_min(B)) == bin_index(B)+1", v_c == 0,
          "%d violations" % v_c)
    check("6d. delta_min(B) >= 1", v_d == 0, "%d violations" % v_d)
    check("6e. allowed() == amplif.allowed_bytes() (no drift)", v_x == 0,
          "%d disagreements" % v_x)
    if first_bad:
        info("first violation: %r" % (first_bad,))
    info("delta_min==1 but NOT on_boundary: %d of %d  "
         "(3B mod P in {P-1,P-2}; B = 426 or 853 mod 1280) "
         "-- on_boundary implies delta_min==1, not the converse"
         % (only_dmin1, n))

    SCEN = [
        ("x25519  ips=1280", 259, 4000, 500.0, 1280),
        ("MLKEM   ips=1280", 1450, 6000, 1734.5, 1280),
        ("MLKEM   ips=1200", 1451, 6000, 1734.5, 1200),
        ("MLKEM   big-cert", 1457, 9000, 1769.0, 1350),
    ]
    from padfec import policy as _pol

    _bb = 1 * 1280
    _pk = _pol.parity_datagram_bytes
    _args = (259, 1280, 51, 16, 4000, 500.0, _bb, bin_index(_bb), P_SERVER)
    _kw = {"parity_bytes": _pk}
    _par_sz = _pk(1280, 1)
    lem_pad = _candidate("pad", 0, _par_sz, *_args, **_kw)
    lem_par = _candidate("parity", 1, 0, *_args, **_kw)
    same_delta = (lem_pad["client_bytes"] == lem_par["client_bytes"]
                  and lem_pad["allowed"] == lem_par["allowed"]
                  and lem_pad["added_bytes"] == lem_par["added_bytes"])
    old_lemma = (lem_par["added_bytes"] <= lem_pad["added_bytes"]
                 and lem_par["allowed"] >= lem_pad["allowed"]
                 and lem_par["m"] >= lem_pad["m"])
    _J = lambda c, r, up: _pol.cost_of_v2(c, 1280, r, 0.05, 1.0, k0=1,
                                          uplink_mbps=up)["j_ms"]
    j_pad = [_J(lem_pad, r, 0.0) for r in (50.0, 100.0, 250.0)]
    j_par = [_J(lem_par, r, 0.0) for r in (50.0, 100.0, 250.0)]
    crossover = (j_par[0] < j_pad[0] and j_par[2] > j_pad[2])
    check("7-0. Lemma 1 is FALSE at equal delta, uplink 0: "
          "parity does not dominate pad",
          same_delta and old_lemma and not dominates(lem_par, lem_pad)
          and crossover,
          "same-delta=%s old-rule=%s new-rule=%s | J(parity)-J(pad) @rtt "
          "50/100/250 = %+.2f/%+.2f/%+.2f ms (부호가 뒤집힌다)"
          % (same_delta, old_lemma, dominates(lem_par, lem_pad),
             j_par[0] - j_pad[0], j_par[1] - j_pad[1], j_par[2] - j_pad[2]))

    _jp10 = [_J(lem_pad, r, 10.0) for r in (50.0, 100.0, 250.0)]
    _jr10 = [_J(lem_par, r, 10.0) for r in (50.0, 100.0, 250.0)]
    check("7-0b. under a rate limit pad beats an equal-delta m=1 parity "
          "at EVERY rtt (the trailing parity loses the credit race)",
          all(a > b for a, b in zip(_jr10, _jp10)),
          "J(parity)-J(pad) @rtt 50/100/250 = %+.2f/%+.2f/%+.2f ms (10 Mbps)"
          % (_jr10[0] - _jp10[0], _jr10[1] - _jp10[1], _jr10[2] - _jp10[2]))

    _edges_real = 0
    _pairs_real = 0
    for _C, _s0b in ((1146, 380.0), (2308, 1494.5)):
        for _cert in (1000, 2308, 3000, 4032, 5609, 6500, 8000, 9000, 12000):
            _cs = levers(_C, _cert, None, W=1280, s0_base=_s0b, c_pkt=40.0,
                         parity_bytes=_pk, max_delta=172)
            for _a in _cs:
                for _b in _cs:
                    if _a is _b:
                        continue
                    _pairs_real += 1
                    if dominates(_a, _b):
                        _edges_real += 1
    check("7-1. dominance prunes NOTHING on the reachable candidate set",
          _edges_real == 0,
          "%d edges over %d ordered pairs (levers 는 반사슬이다 - 후보가 "
          "5~6 개뿐이라 전수 평가가 어차피 싸다)" % (_edges_real, _pairs_real))

    LEMMA = [{"added_bytes": _ad, "allowed": _al, "m": _m, "W_eff": _we,
              "mode": "synthetic", "client_bytes": _al // 3, "k": 1,
              "delta_per_dgram": _we - 1280}
             for _ad in (0, 100) for _al in (1280, 2560)
             for _m in (0, 1) for _we in (1280, 1380)]

    total_edges = 0
    n_irr = n_anti = n_trans = n_cyc = n_chain2 = 0
    distinct_edges = set()
    for nm, C, cert, s0v, Wv in SCEN:
        cs = levers(C, cert, s0v, W=Wv)
        if Wv == 1280 and C == 259:
            cs = cs + LEMMA
        idx = range(len(cs))
        edges = {i: [j for j in idx if i != j and dominates(cs[i], cs[j])]
                 for i in idx}
        total_edges += sum(len(v) for v in edges.values())

        def sig(c):
            return (c["mode"], c["m"], c["client_bytes"], c["added_bytes"],
                    c["allowed"])

        for i in idx:
            for j in edges[i]:
                distinct_edges.add((sig(cs[i]), sig(cs[j])))
        for i in idx:
            if dominates(cs[i], cs[i]):
                n_irr += 1
            for j in idx:
                if dominates(cs[i], cs[j]) and dominates(cs[j], cs[i]):
                    n_anti += 1
                for kk in idx:
                    if dominates(cs[i], cs[j]) and dominates(cs[j], cs[kk]):
                        n_chain2 += 1
                        if not dominates(cs[i], cs[kk]):
                            n_trans += 1
        colour = {i: 0 for i in idx}

        def visit(u):
            colour[u] = 1
            hit = False
            for w in edges[u]:
                if colour[w] == 1:
                    hit = True
                elif colour[w] == 0 and visit(w):
                    hit = True
            colour[u] = 2
            return hit

        for i in idx:
            if colour[i] == 0 and visit(i):
                n_cyc += 1
    check("7. dominance is irreflexive", n_irr == 0, "%d self-loops" % n_irr)
    check("7b. dominance is antisymmetric", n_anti == 0,
          "%d mutual pairs" % n_anti)
    check("7c. dominance is transitive", n_trans == 0,
          "%d broken triples out of %d i->j->k chains" % (n_trans, n_chain2))
    check("7d. dominance digraph is ACYCLIC (DFS)", n_cyc == 0,
          "%d cycles over %d scenarios, %d edges"
          % (n_cyc, len(SCEN), total_edges))
    check("7e. the test is NOT vacuous: >=2 distinct edges AND >=1 2-chain",
          len(distinct_edges) >= 2 and n_chain2 >= 1,
          "%d distinct edges (%d total), %d 2-chains to check transitivity on"
          % (len(distinct_edges), total_edges, n_chain2))
    _anti = levers(259, 4000, 500.0, W=1280)
    _pairs = sum(1 for a in _anti for b in _anti
                 if a is not b and dominates(a, b))
    info("levers() candidate set is a Pareto ANTICHAIN: %d dominated pairs "
         "among %d candidates -- Lemma 1 prunes nothing here, so J must be "
         "evaluated at every boundary point" % (_pairs, len(_anti)))

    for nm, C, cert, s0v, Wv, want_add in (
            ("x25519 C=259  cert=4000 s0=500.0", 259, 4000, 500.0, 1280, 1),
            ("MLKEM  C=1450 cert=6000 s0=1734.5", 1450, 6000, 1734.5, 1280, 2)):
        cs = levers(C, cert, s0v, W=Wv)
        base = cs[0]
        win = [c for c in cs if c["mode"] == "pad" and c["n_rtt"] == 1]
        ok = (base["n_rtt"] == 2 and win
              and min(c["added_bytes"] for c in win) == want_add)
        check("8. %s -> pad of %d B removes one RTT" % (nm, want_add), ok,
              "base n_rtt=%d allowed=%d S=%.1f ; cheapest 1-RTT pad = %s B"
              % (base["n_rtt"], base["allowed"], base["server_flight"],
                 (min(c["added_bytes"] for c in win) if win else "none")))

    trap = levers(1150, 6000, 1734.5, W=1200)
    tbase = trap[0]
    tpad = [c for c in trap if c["mode"] == "pad"]
    trep = [c for c in trap if c["mode"] == "pad_repack"]
    cheap = [c for c in tpad if c["n_rtt"] == 1]
    check("9. pad keeps k0: C=1150 W=1200 buys 1-RTT for 162 B (not 1200 B)",
          tbase["k"] == 2 and tbase["n_rtt"] == 2
          and all(c["k"] == 2 for c in tpad)
          and cheap and min(c["added_bytes"] for c in cheap) == 162,
          "base k=2 A=%d S=%.1f n_rtt=2 -> pad W_eff=%d k=%d B=%d A=%d "
          "added=%d n_rtt=%d"
          % (tbase["allowed"], tbase["server_flight"], tpad[0]["W_eff"],
             tpad[0]["k"], tpad[0]["client_bytes"], tpad[0]["allowed"],
             tpad[0]["added_bytes"], tpad[0]["n_rtt"]))
    check("9b. the collapsed variant is KEPT, but as a separate 'pad_repack'",
          len(trep) == 2
          and all(c["k"] == 1 and c["added_bytes"] < 0 and c["steps"] < 0
                  and c["n_rtt"] == 2 for c in trep),
          "pad_repack k=1 added=%s steps=%s A=%s (still 2-RTT)"
          % ([c["added_bytes"] for c in trep], [c["steps"] for c in trep],
             [c["allowed"] for c in trep]))
    info("repacking is NOT a bug to filter: one 1281 B datagram instead of two "
         "1200 B ones saves 1119 B. It is a real option whose n_rtt is simply "
         "worse here, so it is offered alongside -- never instead of -- pad.")

    SW_W = (1200, 1250, 1280, 1300, 1350, 1400)
    SW_C = range(200, 3000)
    n_collapse = 0
    collapse_cfg = set()
    hist = {}
    fixed_better = repack_better = credit_lost = 0
    for Wv in SW_W:
        for Cv in SW_C:
            cs = levers(Cv, 6000, 1734.5, W=Wv, m_max=0)
            reps = [c for c in cs if c["mode"] == "pad_repack"]
            if not reps:
                continue
            pads = dict((c["delta_per_dgram"], c) for c in cs
                        if c["mode"] == "pad")
            collapse_cfg.add((Cv, Wv))
            n_collapse += len(reps)
            for r in reps:
                hist[r["steps"]] = hist.get(r["steps"], 0) + 1
                p = pads[r["delta_per_dgram"]]
                if p["allowed"] > r["allowed"]:
                    credit_lost += 1
                if p["n_rtt"] < r["n_rtt"]:
                    fixed_better += 1
                elif r["n_rtt"] < p["n_rtt"]:
                    repack_better += 1
    check("9c. repacking NEVER beats the k-fixed pad on n_rtt (0 counterex.)",
          repack_better == 0 and credit_lost == n_collapse and n_collapse > 0,
          "%d collapsing candidates over %d distinct (C,W); credit lost in "
          "%d/%d; k-fixed strictly better on n_rtt in %d (%.1f%%), repack "
          "better in %d"
          % (n_collapse, len(collapse_cfg), credit_lost, n_collapse,
             fixed_better, 100.0 * fixed_better / n_collapse, repack_better))
    info("collapse sweep: C=%d..%d x W in %s (cert=6000 s0=1734.5 m_max=0); "
         "steps histogram %s -- the candidate that k-fixing rescues always "
         "dropped 2 or more bins"
         % (SW_C[0], SW_C[-1], list(SW_W),
            sorted(hist.items())))

    import math as _math

    def _dm_float(B, pkt=P_SERVER):
        A = _math.ceil(AMP * B / pkt) * pkt
        return _math.floor(A / AMP - B) + 1

    mism = [B for B in range(1200, 300001) if _dm_float(B) != delta_min(B)]
    check("10. float and int agree on B=1200..300000 (rationale is honest)",
          not mism, "%d mismatches over %d values" % (len(mism), 300001 - 1200))
    BIG = [10 ** 9, 10 ** 12, 10 ** 15,
           10 ** 9 + 427, 10 ** 12 + 853, 10 ** 15 + 427, 10 ** 15 + 853]
    nondeg = [B for B in BIG if (AMP * B) % P_SERVER != 0]
    big_bad = [(B, _dm_float(B), delta_min(B)) for B in BIG
               if _dm_float(B) != delta_min(B)]
    check("10a. float and int also agree at B ~ 1e9/1e12/1e15, %d of %d points "
          "non-degenerate (3B mod P != 0)" % (len(nondeg), len(BIG)),
          not big_bad and len(nondeg) >= 4,
          " ".join("3B%%P=%d:dm=%d" % ((AMP * B) % P_SERVER, delta_min(B))
                   for B in BIG) if not big_bad else "%r" % (big_bad,))
    _brk = 2 ** 53
    check("10b. at B = 2**53 float and int disagree (a single spot check -- "
          "NOT a claim that 2**53 is the first or only such B; it is neither)",
          _dm_float(_brk) != delta_min(_brk),
          "B=2**53: float=%d int=%d" % (_dm_float(_brk), delta_min(_brk)))
    info("integer arithmetic is used to remove the question, NOT because "
         "float demonstrably breaks in range -- it does not.")

    val_bad = []
    for fn, args in ((delta_min, (1280.0,)), (delta_min, (1280, 1.0)),
                     (delta_min, (1280, 1, 1280.0)), (delta_min, (True,)),
                     (levers, (259.0, 4000, 500.0)),
                     (levers, (259, 4000, 500.0, 1280.5))):
        try:
            fn(*args)
        except TypeError:
            continue
        except Exception as exc:
            val_bad.append((fn.__name__, args, type(exc).__name__))
            continue
        val_bad.append((fn.__name__, args, "NO RAISE"))
    check("11. non-int byte/step counts raise TypeError (6/6)", not val_bad,
          "delta_min and levers both reject float and bool"
          if not val_bad else "%r" % (val_bad,))
    try:
        levers(259, 4000, None)
        _both = "NO RAISE"
    except ValueError:
        _both = "ValueError"
    except Exception as exc:
        _both = type(exc).__name__
    check("11b. levers(s0=None) without s0_base is refused up front",
          _both == "ValueError", "raised %s" % _both)

    v_const = levers(1450, 6000, 1734.5, W=1280)
    v_pkt = levers(1450, 6000, None, W=1280, s0_base=1494.5, c_pkt=40.0)
    bc = all(c["s0_eff"] == 1734.5 for c in v_const)
    pk = all(c["s0_eff"] == s0_at(c["allowed"] // P_SERVER, 1494.5, 40.0)
             for c in v_pkt)
    n_s0 = len(set(c["s0_eff"] for c in v_pkt))
    check("12. s0_base=None keeps the old constant s0; s0_base set makes "
          "s0_eff bin-dependent", bc and pk and n_s0 > 1,
          "constant path all %.1f ; packet path %d distinct s0_eff over "
          "%d candidates: %s"
          % (1734.5, n_s0, len(v_pkt),
             sorted(set(c["s0_eff"] for c in v_pkt))))
    all_c = v_const + v_pkt + levers(259, 4000, 500.0, W=1280)
    check("12b. credit_bytes == client_bytes (verified by p13)",
          all(c["credit_bytes"] == c["client_bytes"] for c in all_c),
          "%d candidates" % len(all_c))
    lp = [c for c in all_c if c["late_parity_risk"]]
    check("12c. late_parity_risk is False everywhere "
          "(rests on p13 check 5: n=600, CP lower bound >= 0.99)",
          not lp, "flagged %d of %d (must be 0)" % (len(lp), len(all_c)))
    _mtu = levers(4200, 4000, 500.0, W=1450, max_steps=2, m_max=1)
    over = [c for c in _mtu if c["over_mtu"]]
    check("12d. over_mtu flags exactly W_eff > %d" % TYPICAL_MTU,
          all((c["W_eff"] > TYPICAL_MTU) == c["over_mtu"] for c in all_c + _mtu)
          and over,
          "W_eff seen: %s ; flagged %d"
          % (sorted(set(c["W_eff"] for c in _mtu)), len(over)))

    _MAXD = 172
    _suff_bad = []
    _n_combo_better = 0
    _gain_max = 0.0
    for _C, _s0b in ((1146, 380.0), (2308, 1494.5)):
        _k0 = capacity.natural_k(_C, 1280, 51)
        for _cert in (2308, 4032, 6500, 9000, 12000):
            for _rtt in (50.0, 250.0):
                for _p in (0.0, 0.02, 0.10):
                    _cs = levers(_C, _cert, None, W=1280, s0_base=_s0b,
                                 c_pkt=40.0, parity_bytes=_pk,
                                 max_delta=_MAXD)
                    _old = [c for c in _cs if c["mode"] != "combo"]

                    def _bestj(cands, rtt=_rtt, p=_p, k0=_k0):
                        b = None
                        for c in cands:
                            if (c["W_eff"] > 1452
                                    or c["mode"] == "pad_repack"):
                                continue
                            j = _pol.cost_of_v2(c, 1280, rtt, p, 1.0,
                                                k0=k0)["j_ms"]
                            if b is None or j < b:
                                b = j
                        return b

                    _bnew, _bold = _bestj(_cs), _bestj(_old)
                    _bf = None
                    for _d in range(0, _MAXD + 1):
                        for _m in (0, 1, 2):
                            _c = _candidate("bf", _m, _d, _C, 1280, 51, 16,
                                            _cert, None, _k0 * 1280,
                                            bin_index(_k0 * 1280), P_SERVER,
                                            k_floor=_k0, s0_base=_s0b,
                                            c_pkt=40.0, parity_bytes=_pk)
                            if _c["W_eff"] > 1452:
                                continue
                            _j = _pol.cost_of_v2(_c, 1280, _rtt, _p, 1.0,
                                                 k0=_k0)["j_ms"]
                            if _bf is None or _j < _bf:
                                _bf = _j
                    if _bnew is None or _bf is None or _bnew > _bf + 1e-9:
                        _suff_bad.append((_C, _cert, _rtt, _p, _bnew, _bf))
                    if _bold is not None and _bnew < _bold - 1e-9:
                        _n_combo_better += 1
                        _gain_max = max(_gain_max, _bold - _bnew)
    check("13. combo boundary points == exhaustive sweep over delta 0..%d"
          % _MAXD, not _suff_bad,
          "%d mismatches; combo improved %d conditions, max gain %.3f ms"
          % (len(_suff_bad), _n_combo_better, _gain_max))
    check("13a. the sufficiency test is NOT vacuous (combo actually wins "
          "somewhere)", _n_combo_better > 0,
          "combo 가 더 나은 조건 %d 개 (0 이면 이 시험이 아무것도 안 지킨다)"
          % _n_combo_better)

    HDR = ("mode", "st", "m", "dlt", "W_eff", "k", "cbytes", "added",
           "allowed", "s0_eff", "rtt", "inpl", "lateP", "mtu!")
    FMT = "%-10s %3d %2d %4d %6d %2d %7d %7d %8d %7.1f %3d %5s %5s %4s"

    def table(title, cands):
        print("-" * 78)
        print(title)
        print("%-10s %3s %2s %4s %6s %2s %7s %7s %8s %7s %3s %5s %5s %4s" % HDR)
        for c in cands:
            print(FMT % (c["mode"], c["steps"], c["m"], c["delta_per_dgram"],
                         c["W_eff"], c["k"], c["client_bytes"],
                         c["added_bytes"], c["allowed"], c["s0_eff"],
                         c["n_rtt"], c["inplace_feasible"],
                         c["late_parity_risk"], c["over_mtu"]))

    table("levers(C=1450, cert=6000, s0=1734.5, W=1280)   [MLKEM, k=2, "
          "constant s0]", levers(1450, 6000, 1734.5, W=1280))
    table("levers(C=1450, cert=6000, s0=None, W=1280, s0_base=1527.5, "
          "c_pkt=34.5)   [MLKEM, spec 2.5 packet term]",
          levers(1450, 6000, None, W=1280, s0_base=1527.5, c_pkt=34.5))
    table("levers(C=1150, cert=6000, s0=1734.5, W=1200)   [k-collapse case: "
          "pad keeps k0=2, pad_repack does not]",
          levers(1150, 6000, 1734.5, W=1200))
    print("-" * 78)

    failed = [r for r in _results if not r[0]]
    print("%d checks, %d failed" % (len(_results), len(failed)))
    for _, nm, det in failed:
        print("  FAILED: %s | %s" % (nm, det))
    sys.exit(1 if failed else 0)
