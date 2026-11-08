import hashlib
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
import blockstat as BST
from padfec import policy as POL
from _journal import Journal, code_fingerprint

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
CERT = 9000
CACHE = "/tmp/padfec/p17_cache.json"

N_DEFAULT = 150
N_PRECISE = 450
N = int(os.environ.get("PADFEC_P17_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))

DRYRUN = os.environ.get("PADFEC_P17_DRYRUN") == "1"
FP_OVERRIDE = os.environ.get("PADFEC_P17_FP") or None

ARMS = [("auto", "auto", 1), ("m0", "off", 0), ("m1", "on", 1),
        ("m2", "on", 2), ("m3", "on", 3)]

SCHEDULE = [(2.0, N), (15.0, N)]
CYCLES = len(ARMS)

CONDS = [
    ("2Mbps",   2.0, POL.UPLINK_CONSTRAINED_MBPS, 9000,  50.0),
    ("무제한",   0.0, POL.UPLINK_UNSHAPED,         9000,  50.0),
    ("큰cert",  2.0, POL.UPLINK_CONSTRAINED_MBPS, 16000, 50.0),
    ("RTT200",  2.0, POL.UPLINK_CONSTRAINED_MBPS, 9000,  200.0),
]

PROBE_TAX_MS = 0.42
TOL_MS = 1.0
BOUGHT_HI = 0.9
BOUGHT_LO = 0.7


def mean(v):
    return (sum(v) / len(v)) if v else None


FEEDBACK = os.environ.get("PADFEC_FEEDBACK") == "1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def cache_snapshot():
    try:
        with open(CACHE, "rb") as stream:
            data = stream.read()
    except FileNotFoundError:
        return {"exists": False, "sha256": None, "state": None}
    except OSError as exc:
        return {"exists": None, "sha256": None, "state": None,
                "error": str(exc)}
    out = {"exists": True, "sha256": hashlib.sha256(data).hexdigest()}
    try:
        out["state"] = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        out["state"] = None
        out["error"] = "invalid cache JSON"
    return out


def trial_timeline(segment):
    n = segment.get("n_expected", segment.get("n"))
    if type(n) is not int or n <= 0:
        return [], "invalid_count"
    rows = segment.get("trial_records")
    if rows is None:
        mu = segment.get("m_used")
        if (segment.get("ok") == n == segment.get("n")
                and isinstance(mu, list) and len(mu) == n
                and all(type(x) is int and 0 <= x <= POL.M_MAX_DEFAULT for x in mu)):
            return list(mu), "legacy_all_success"
        return [None] * n, "legacy_missing_trial_indices"
    if not isinstance(rows, list):
        return [None] * n, "invalid_trial_records"
    choices = [None] * n
    seen, invalid = set(), False
    for row in rows:
        i = row.get("i") if isinstance(row, dict) else None
        if type(i) is not int or not 0 <= i < n:
            invalid = True
            continue
        if i in seen:
            invalid = True
            choices[i] = None
            continue
        seen.add(i)
        m = row.get("m_used")
        if type(m) is int and 0 <= m <= POL.M_MAX_DEFAULT:
            choices[i] = m
        else:
            invalid = True
    complete = not invalid and len(rows) == n and all(x is not None for x in choices)
    return choices, "all_attempts" if complete else "incomplete_trial_records"


def unit_complete(rec):
    if not isinstance(rec, dict) or not isinstance(rec.get("segments"), list):
        return False
    expected = {(c, loss, a): n for c in range(CYCLES)
                for loss, n in SCHEDULE for a, _f, _m in ARMS}
    seen = set()
    for s in rec.get("segments", []):
        if not isinstance(s, dict) or type(s.get("cycle")) is not int:
            return False
        key = (s.get("cycle"), s.get("loss"), s.get("arm"))
        if (key not in expected or key in seen or type(s.get("n")) is not int
                or s["n"] != expected[key] or s.get("err")):
            return False
        seen.add(key)
        if type(s.get("ok")) is not int or not 0 < s["ok"] <= s["n"]:
            return False
        if type(s.get("mean")) not in (int, float) or not math.isfinite(s["mean"]):
            return False
        choices, scope = trial_timeline(s)
        if len(choices) != expected[key] or scope not in ("all_attempts", "legacy_all_success"):
            return False
        if "trial_records" in s:
            rows = s["trial_records"]
            if any(type(x.get("ok")) is not bool
                   or type(x.get("ms")) not in (int, float)
                   or not math.isfinite(x["ms"]) or x["ms"] < 0 for x in rows):
                return False
            if sum(x["ok"] for x in rows) != s["ok"]:
                return False
    return (seen == set(expected) and bool(rec.get("srv_stats_present"))
            and type(rec.get("srv_crc_fail")) is int and rec["srv_crc_fail"] == 0
            and not rec.get("err"))


def unit_key(cond_name, rate, cert, rtt):
    gap_ms = 50 if rate > 0 else 8
    return "%s|latin|n%d|c%d|g%d|cert%d|rtt%g|fb%d" % (
        cond_name, N, CYCLES, gap_ms, cert, rtt, int(FEEDBACK)), gap_ms


def run_interleaved(cond_name, rate, up_policy, cert, rtt, jr):
    key, gap_ms = unit_key(cond_name, rate, cert, rtt)
    if jr.has(key):
        cached = jr.get(key)
        if unit_complete(cached) or DRYRUN:
            return cached
        print("   (저널 단위가 불완전해 다시 측정: %s)" % key)
    if DRYRUN:
        have = sorted(k for k in jr.keys() if k.startswith(cond_name + "|"))
        print("   (드라이런: 키 %s 없음. 이 지문의 %s 단위: %s)"
              % (key, cond_name, have or "없음"))
        return None
    try:
        os.unlink(CACHE)
    except OSError:
        pass
    acc = {a: [] for a, _f, _m in ARMS}
    seg, err = [], ""
    started_at = utc_now()
    FB = ["-feedback"] if FEEDBACK else []
    p, sp = B.start_server(cert, fec="on", extra=FB)
    try:
        rot = {}
        for cyc in range(CYCLES):
            for loss, n_conn in SCHEDULE:
                B.set_netem(rtt / 2.0, loss_c2s=loss, rate_up_mbit=rate)
                r = rot.get(loss, 0) % len(ARMS)
                rot[loss] = rot.get(loss, 0) + 1
                order = ARMS[r:] + ARMS[:r]
                for pos, (aname, fec, m) in enumerate(order):
                    before = cache_snapshot()
                    segment_started_at = utc_now()
                    extra = (["-cache", CACHE, "-probe-every", "20"]
                             if fec == "auto" else []) + FB
                    rows, cs, e = B.run_client(
                        GROUP, n_conn, fec=fec, m=max(m, 1), gap_ms=gap_ms,
                        timeout_s=10, expect_k=K, extra=extra,
                        uplink_mbps=up_policy)
                    if e:
                        err = e
                    ok = [x["ms"] for x in rows if x.get("ok")]
                    acc[aname].extend(ok)
                    mu = [x.get("m_used") for x in rows]
                    seg.append({"cycle": cyc, "loss": loss, "arm": aname,
                                "pos": pos, "n": len(rows), "ok": len(ok),
                                "n_expected": n_conn, "failed": len(rows) - len(ok),
                                "mean": mean(ok), "m_used": mu,
                                "trial_records": rows,
                                "choice_scope": "all_attempts",
                                "started_at": segment_started_at,
                                "finished_at": utc_now(),
                                "cache_before": before, "cache_after": cache_snapshot(),
                                "client_stats": cs, "err": e})

                print("   %-8s cyc%d 손실%-5g  %s" % (
                    cond_name, cyc, loss,
                    "  ".join("%s(자리%d) %.2f" % (s["arm"], s["pos"],
                                                 s["mean"] or -1)
                              for s in seg[-len(ARMS):])), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    rec = {"cond": cond_name, "cert": cert, "rtt_ms": rtt,
           "up_policy": up_policy, "netem_rate_mbit": rate,
           "gap_ms": gap_ms, "feedback": FEEDBACK,
           "started_at": started_at, "finished_at": utc_now(),
           "protocol": {"version": 2, "group": GROUP, "expected_k": K,
                        "n_per_segment": N, "cycles": CYCLES,
                        "schedule": SCHEDULE, "arms": ARMS,
                        "probe_every": 20, "cache_reset_per_condition": True,
                        "choice_scope": "all_attempts",
                        "latency_scope": "successful_attempts",
                        "comparison_scope": "exploratory_same_data_labels"},
           "arms": {a: {"n": len(v), "mean": mean(v), "p50": B.pctl(v, 0.5),
                        "p95": B.pctl(v, 0.95), "ms": v}
                    for a, v in acc.items()},
           "segments": seg, "srv_recovered": ss.get("recovered"),
           "server_stats": ss,
           "server_statistics_scope": "one condition total; presence is not a connection matching check",
           "srv_crc_fail": ss.get("recover_crc_fail"),
           "srv_stats_present": bool(ss), "err": err}
    n_seg = CYCLES * len(SCHEDULE) * len(ARMS)
    complete = unit_complete(rec)
    if complete:
        jr.record(key, rec)
    else:
        print("   (저널에 안 남긴다: err=%r 구간 %d/%d crc실패 %s)"
              % (err, len(seg), n_seg, ss.get("recover_crc_fail")))
    return rec


def optimal_m(loss_pct, up, cert=None, rtt=None):
    d = POL.decide_v2(C=B.measured_C(GROUP),
                      cert_bytes=CERT if cert is None else cert,
                      rtt_ms=RTT_MS if rtt is None else rtt,
                      p=loss_pct / 100.0, burst=1.0, s0_base=POL.S0_BASE_MLKEM,
                      c_pkt=POL.C_PKT_POLICY_DEFAULT, W=1280, max_steps=2,
                      m_max=POL.M_MAX_DEFAULT, uplink_mbps=up)
    return d["choice"]["m"]


def block_means(rec, arm, loss):
    out = {}
    for s in rec["segments"]:
        if s["arm"] == arm and s["loss"] == loss and s["mean"] is not None:
            out[s["cycle"]] = s["mean"]
    return out


def paired_ci(rec, a, b, loss, alpha=0.05):
    ma, mb = block_means(rec, a, loss), block_means(rec, b, loss)
    cyc = sorted(set(ma) & set(mb))
    d = [ma[c] - mb[c] for c in cyc]
    if len(d) < 2:
        return (mean(d), None, len(d))
    mu = sum(d) / len(d)
    var = sum((x - mu) ** 2 for x in d) / (len(d) - 1)
    half = BST.t_crit(len(d) - 1, alpha) * math.sqrt(var / len(d))
    return (mu, half, len(d))


def fixed_arm_names():
    return [a for a, _f, _m in ARMS if a != "auto"]


def allowed_by_loss(rec, tol=TOL_MS, alpha=0.05):
    out = {}
    for loss, _n in SCHEDULE:
        fixed = {}
        for a in fixed_arm_names():
            v = [s["mean"] for s in rec["segments"]
                 if s["arm"] == a and s["loss"] == loss
                 and s["mean"] is not None]
            if v:
                fixed[a] = mean(v)
        if not fixed:
            out[loss] = None
            continue
        best = min(fixed, key=lambda a: fixed[a])
        b = fixed[best]
        margins = {}
        stat = []
        for a in fixed:
            if a == best:
                margins[a] = {"diff": 0.0, "half": 0.0}
                stat.append(a)
                continue
            d, half, nb = paired_ci(rec, a, best, loss, alpha)
            margins[a] = {"diff": d, "half": half, "blocks": nb}
            if d is None:
                continue
            if half is None or (d - half) <= 0:
                stat.append(a)
        out[loss] = {"means": fixed,
                     "means_display_ms": {a: round(v, 3) for a, v in fixed.items()},
                     "best": best,
                     "allowed": sorted(a for a, v in fixed.items()
                                       if v - b < tol),
                     "allowed_stat": sorted(stat),
                     "margins": margins}
    return out


def intersections(alw):
    ls = [l for l, _n in SCHEDULE]
    if any(alw.get(l) is None for l in ls):
        return None, None
    tol = set(alw[ls[0]]["allowed"])
    st = set(alw[ls[0]]["allowed_stat"])
    for l in ls[1:]:
        tol &= set(alw[l]["allowed"])
        st &= set(alw[l]["allowed_stat"])
    return sorted(tol), sorted(st)


def bought_rtt(rec, rtt):
    am = rec["arms"]
    fixed = {a: am[a]["mean"] for a in fixed_arm_names()
             if am.get(a) and am[a]["mean"] is not None}
    if "m0" not in fixed or len(fixed) < 2:
        return {"ratio": None, "label": "자료 없음", "best": None}
    best = min(fixed, key=lambda a: fixed[a])
    ratio = (fixed["m0"] - fixed[best]) / rtt
    if ratio >= BOUGHT_HI:
        lab = "샀다"
    elif ratio <= BOUGHT_LO:
        lab = "못 샀다"
    else:
        lab = "판정 불능"
    return {"ratio": ratio, "label": lab, "best": best}


def oracle_gain(rec, alw, alpha=0.05):
    ls = [l for l, _n in SCHEDULE]
    if any(alw.get(l) is None for l in ls):
        return None, None, None
    arms = set(alw[ls[0]]["means"])
    for l in ls[1:]:
        arms &= set(alw[l]["means"])
    if not arms:
        return None, None, None
    fixed_best = min(arms, key=lambda a: sum(alw[l]["means"][a] for l in ls))
    per_loss_best = {l: min(arms, key=lambda a: alw[l]["means"][a]) for l in ls}
    gain = sum(alw[l]["means"][fixed_best] - alw[l]["means"][per_loss_best[l]]
               for l in ls) / len(ls)
    cyc = None
    bm = {}
    for l in ls:
        for a in (fixed_best, per_loss_best[l]):
            bm[(l, a)] = block_means(rec, a, l)
            cyc = set(bm[(l, a)]) if cyc is None else cyc & set(bm[(l, a)])
    g = []
    for c in sorted(cyc or []):
        g.append(sum(bm[(l, fixed_best)][c] - bm[(l, per_loss_best[l])][c]
                     for l in ls) / len(ls))
    half = None
    if len(g) >= 2:
        mu = sum(g) / len(g)
        var = sum((x - mu) ** 2 for x in g) / (len(g) - 1)
        half = BST.t_crit(len(g) - 1, alpha) * math.sqrt(var / len(g))
    gain = mean(g) if g else None
    return gain, half, {"fixed_best": fixed_best,
                        "point_scope": "unrounded matched cycle contrasts; same-data winner labels are exploratory",
                        "matched_cycles": sorted(cyc or []),
                        "per_loss_best": {("%g" % l): per_loss_best[l]
                                          for l in ls}}


def oracle_verdict(gain, half, tax=PROBE_TAX_MS):
    if gain is None:
        return "자료 없음"
    if half is None:
        return "반폭 없음"
    if gain + half <= tax:
        return "값 없다"
    if gain - half > tax:
        return "값 있다"
    return "판정 불능"


def variance_inflation(rec, loss, a, b, alpha=0.05):
    rows = [{"arm": s["arm"], "pos": s["pos"], "block": s["cycle"],
             "value": s["mean"]}
            for s in rec["segments"] if s["loss"] == loss
            and s["mean"] is not None]
    an = BST.latin_anova(rows)
    _d, half_pool = BST.contrast(an, a, b, alpha) if an.get("ok") \
        else (None, None)
    _d2, half_pair, _nb = paired_ci(rec, a, b, loss, alpha)
    if not half_pool or not half_pair:
        return None
    return half_pool / half_pair


def adapt_stats(rec, up, alw):
    out = {}
    for loss, _n in SCHEDULE:
        want = optimal_m(loss, up, rec.get("cert"), rec.get("rtt_ms"))
        ok_ms = set()
        if alw.get(loss):
            for a in alw[loss]["allowed"]:
                for nm, _f, mm in ARMS:
                    if nm == a:
                        ok_ms.add(mm)
        hits = tot = unknown = 0
        lags = []
        scopes = []
        for s in rec["segments"]:
            if s["arm"] != "auto" or s["loss"] != loss:
                continue
            mu, scope = trial_timeline(s)
            scopes.append(scope)
            tot += len(mu)
            unknown += sum(x is None for x in mu)
            hits += sum(1 for x in mu if x in ok_ms)
            lag, run = None, 0
            for i, x in enumerate(mu):
                run = run + 1 if x in ok_ms else 0
                if run >= 10:
                    lag = i - 9
                    break
            lags.append(lag)
        out[loss] = {"want_m_model": want,
                     "allowed": (alw.get(loss) or {}).get("allowed"),
                     "allowed_stat": (alw.get(loss) or {}).get("allowed_stat"),
                     "best_measured": (alw.get(loss) or {}).get("best"),
                     "hit_rate": (hits / tot) if tot else None,
                     "timeline_complete": bool(scopes) and all(
                         x in ("all_attempts", "legacy_all_success") for x in scopes),
                     "timeline_scopes": scopes, "unknown_choices": unknown,
                     "hit_rate_scope": "all_attempts_unknown_as_misses",
                     "n": tot, "lags": lags,
                     "lag_med": (statistics.median(x for x in lags if x is not None)
                                 if any(x is not None for x in lags) else None),
                     "lag_median_scope": "conditional on segments that adapted; never-adapted segments are not zero-lag observations",
                     "adapted_segments": sum(x is not None for x in lags),
                     "total_segments": len(lags),
                     "never_adapted": sum(1 for x in lags if x is None)}
    return out


def trial_inventory(rec):
    records = [r for segment in rec.get("segments", []) for r in segment.get("trial_records", [])]
    expected = sum(segment.get("n_expected", segment.get("n", 0)) for segment in rec.get("segments", []))
    counts = {}
    valid = 0
    for row in records:
        k = row.get("first_flight_datagrams")
        label = str(k) if type(k) is int and k > 0 else "unknown"
        counts[label] = counts.get(label, 0) + 1
        rtt = row.get("path_rtt_ms")
        valid += int(row.get("path_rtt_valid") is True and
                     type(rtt) in (int, float) and math.isfinite(rtt) and rtt > 0)
    return {"n_expected": expected, "n_records": len(records),
            "n_missing_records": max(0, expected - len(records)),
            "actual_k_counts": counts, "current_ack_rtt_valid": valid,
            "current_ack_rtt_missing_or_invalid": len(records) - valid,
            "expected_k_scope": "flush hint, not a filter on actual observed k",
            "rtt_scope": "current connection ACK observation only; absence does not establish cached RTT absence or connection failure"}


def position_effect(rec):
    worst = 0.0
    for loss, _n in SCHEDULE:
        by_pos = {}
        for s in rec["segments"]:
            if s["loss"] == loss and s["mean"] is not None:
                by_pos.setdefault(s["pos"], []).append(s["mean"])
        vals = [mean(v) for v in by_pos.values() if v]
        if len(vals) >= 2:
            worst = max(worst, max(vals) - min(vals))
    return worst


def main():
    if FP_OVERRIDE and not DRYRUN:
        print("PADFEC_P17_FP is allowed only with PADFEC_P17_DRYRUN=1; "
              "live measurements must use the current source fingerprint.", file=sys.stderr)
        return 2
    if not DRYRUN:
        B.harden()
        B.require_root()
        B.setup()
    else:
        B.harden()
        print("** 드라이런: 측정 안 함, 저널의 조건만 검사, 결과 파일 안 씀 **")

    fp = FP_OVERRIDE or code_fingerprint(
        ["experiments/p17_adaptive_value.py",
         "experiments/quicbed/qamp.go",
         "experiments/quicbed/policy.go",
         "experiments/quicbed/pfail_table.go",
         "experiments/quicbed/go.mod", "experiments/quicbed/go.sum",
         "experiments/quicbed/build.sh", "experiments/_journal.py",
         "experiments/blockstat.py", "experiments/padbed.py",
         "padfec/policy.py", "padfec/quantum.py",
         "experiments/results/p1_flight.json"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p17_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "group": GROUP, "cert": CERT, "n_per_seg": N,
           "cycles": CYCLES, "schedule": SCHEDULE,
           "conds": [{"cond": c[0], "netem_rate_mbit": c[1], "up_policy": c[2],
                      "cert": c[3], "rtt_ms": c[4]} for c in CONDS],
           "probe_tax_ms": PROBE_TAX_MS, "tol_ms": TOL_MS,
           "bought_hi": BOUGHT_HI, "bought_lo": BOUGHT_LO,
           "dryrun": DRYRUN, "journal_fp": fp, "feedback": FEEDBACK,
           "analysis_scope": "exploratory_same_data_labels",
           "confirmatory": False,
           "rows": [], "gain": [], "checks": []}
    checks = out["checks"]

    def add(name, ok, detail, scope="existing_check"):
        checks.append({"check": name, "ok": bool(ok), "detail": detail,
                       "scope": scope, "confirmatory": False})
        print("[%s] %-64s %s" % ("통과" if ok else "실패", name, detail),
              flush=True)

    print("=" * 104)
    print("P17 적응의 값어치 - 손실 %s%% 교대 x%d 사이클, 구간당 n=%d "
          "(라틴 방격 인터리브)"
          % (" <-> ".join("%g" % l for l, _ in SCHEDULE), CYCLES, N))
    print("=" * 104)

    for cond_name, rate, up_policy, cert, rtt in CONDS:
        print()
        print("### 조건 %s (netem rate %g, 정책 uplink %g, cert %d, RTT %g)"
              % (cond_name, rate, up_policy, cert, rtt))
        rec = run_interleaved(cond_name, rate, up_policy, cert, rtt, jr)
        if rec is None:
            print("   (드라이런: 저널에 없음 - 건너뜀)")
            continue
        filled = False
        for k_, v_ in (("up_policy", up_policy), ("netem_rate_mbit", rate),
                       ("cert", cert), ("rtt_ms", rtt)):
            if k_ not in rec:
                rec[k_] = v_
                filled = True
        if filled:
            rec["inputs_filled_from_conds"] = True
        out["rows"].append(rec)

    for rec in out["rows"]:
        am = rec["arms"]
        if not all(am[a]["mean"] is not None for a in am):
            continue
        means = {a: am[a]["mean"] for a in am}
        fixed = {a: means[a] for a in fixed_arm_names() if a in means}
        best = min(fixed, key=lambda a: fixed[a])
        alw = allowed_by_loss(rec)
        tol_int, stat_int = intersections(alw)
        bought = bought_rtt(rec, rec["rtt_ms"])
        og, og_half, og_who = oracle_gain(rec, alw)
        if bought["label"] == "못 샀다" and stat_int is not None:
            if len(stat_int) == 0:
                needed = True
            elif tol_int:
                needed = False
            else:
                needed = None
        elif bought["label"] == "샀다" and tol_int is not None:
            needed = False if tol_int else None
        else:
            needed = None
        hi_l0 = SCHEDULE[-1][0]
        margin_hi = None
        if alw.get(hi_l0):
            _b = alw[hi_l0]["best"]
            _ms = [(a, v["diff"], v["half"]) for a, v in alw[hi_l0]["margins"].items()
                   if a != _b and v.get("half") is not None]
            if _ms:
                margin_hi = min(((d - h), a) for a, d, h in _ms)
        hi_l = SCHEDULE[-1][0]
        lo_l = SCHEDULE[0][0]
        vi = None
        if alw.get(hi_l) and alw.get(lo_l):
            a_hi, a_lo = alw[hi_l]["best"], alw[lo_l]["best"]
            if a_hi != a_lo:
                vi = variance_inflation(rec, hi_l, a_lo, a_hi)
        out["gain"].append({
            "cond": rec["cond"], "cert": rec["cert"], "rtt_ms": rec["rtt_ms"],
            "up_policy": rec.get("up_policy"),
            "netem_rate_mbit": rec.get("netem_rate_mbit"),
            "means": means, "best_fixed": best,
            "best_fixed_mean": fixed[best], "auto_mean": means["auto"],
            "gain_ms": fixed[best] - means["auto"],
            "pos_effect_ms": position_effect(rec),
            "allowed_by_loss": {("%g" % l): v for l, v in alw.items()},
            "intersection_tol": tol_int, "intersection_stat": stat_int,
            "bought_rtt": bought,
            "adapt_needed": needed,
            "deciding_margin_ms": (margin_hi[0] if margin_hi else None),
            "deciding_arm": (margin_hi[1] if margin_hi else None),
            "oracle_gain_ms": og, "oracle_gain_ci95_half_ms": og_half,
            "oracle_arms": og_who,
            "oracle_verdict": oracle_verdict(og, og_half),
            "variance_inflation_pooled_over_paired": vi,
            "adapt": adapt_stats(rec, rec.get("up_policy"), alw),
            "trial_inventory": trial_inventory(rec),
            "fixed_spread_ms": max(fixed.values()) - min(fixed.values()),
            "n_auto": am["auto"]["n"]})
        g = out["gain"][-1]
        print()
        print("   [%s] 최선 고정 %s %.3f | auto %.3f | 시간 이득 %+.3f ms "
              "(자리효과 %.3f, 진단)"
              % (g["cond"], best, fixed[best], means["auto"],
                 g["gain_ms"], g["pos_effect_ms"]))
        print("   %s 왕복 %s (%.2f RTT) | 실질 교집합 %s | 통계 교집합 %s | "
              "적응 %s | 고손실 판별 여유 %s"
              % (" " * len(g["cond"]), bought["label"],
                 bought["ratio"] if bought["ratio"] is not None else -1,
                 tol_int, stat_int,
                 {True: "필요", False: "불필요", None: "판정 불능"}[needed],
                 ("%+.3f ms (%s)" % (g["deciding_margin_ms"], g["deciding_arm"]))
                 if g["deciding_margin_ms"] is not None else "-"))

    print()
    print("-" * 104)
    g = {x["cond"]: x for x in out["gain"]}
    n_seg = len(CONDS) * CYCLES * len(SCHEDULE) * len(ARMS)
    got = sum(len(r["segments"]) for r in out["rows"])
    add("1. 모든 팔·구간이 측정됐다", got == n_seg
        and {r["cond"] for r in out["rows"]} == {c[0] for c in CONDS}
        and len(out["rows"]) == len(CONDS)
        and all(unit_complete(r) for r in out["rows"]),
        "%d/%d 구간" % (got, n_seg))
    add("2. 모든 조건에서 서버 통계가 실제로 있었다",
        all(r["srv_stats_present"] for r in out["rows"]) and out["rows"],
        "%d/%d" % (sum(1 for r in out["rows"] if r["srv_stats_present"]),
                   len(out["rows"])))

    lo = SCHEDULE[0][0]

    def seg_mean(cond, arm, loss):
        v = [s["mean"] for r in out["rows"] if r["cond"] == cond
             for s in r["segments"]
             if s["arm"] == arm and s["loss"] == loss and s["mean"] is not None]
        return mean(v)

    _free = next((c for c in CONDS if c[1] == 0), None)
    _shaped = next((c for c in CONDS if c[1] > 0 and _free
                    and c[3] == _free[3] and c[4] == _free[4]), None)
    sh0 = seg_mean(_shaped[0], "m0", lo) if _shaped else None
    fr0 = seg_mean(_free[0], "m0", lo) if _free else None
    _ser = ((K * 1280 * 8.0) / (_shaped[1] * 1e6) * 1e3) if _shaped else 0.0
    add("3. 대역이 실제로 걸렸다 (같은 팔 m0 이 %s 에서 무제한보다 느리다)"
        % (_shaped[0] if _shaped else "대역 조건 없음"),
        (sh0 is not None and fr0 is not None and (sh0 - fr0) > _ser / 2.0),
        ("m0: %s %.2f vs 무제한 %.2f (차이 %+.2f ms, 예상 직렬화 %.2f)"
         % (_shaped[0], sh0, fr0, sh0 - fr0, _ser))
        if (sh0 and fr0) else "자료 없음(대역 조건 %s)"
        % (_shaped[0] if _shaped else None))

    slo = [s["mean"] for r in out["rows"] for s in r["segments"]
           if s["loss"] == lo and s["mean"] is not None]
    shi = [s["mean"] for r in out["rows"] for s in r["segments"]
           if s["loss"] != lo and s["mean"] is not None]
    add("4. 손실 전환이 실제로 일어났다 (고손실 구간이 저손실보다 느리다)",
        slo and shi and mean(shi) > mean(slo),
        "저손실 %.2f vs 고손실 %.2f ms" % (mean(slo) or -1, mean(shi) or -1))

    add("5. 고정팔들이 서로 갈린다 (안 갈리면 아래가 공허하다)",
        out["gain"] and all(x["fixed_spread_ms"] > 0.5 for x in out["gain"]),
        " | ".join("%s 산포 %.3f ms" % (x["cond"], x["fixed_spread_ms"])
                   for x in out["gain"]) or "자료 없음")

    claim_ok, claim_detail = [], []
    n_bought = n_not = 0
    for x in out["gain"]:
        lab = x["bought_rtt"]["label"]
        if lab == "샀다":
            n_bought += 1
            ok = bool(x["intersection_tol"])
            claim_ok.append(ok)
            claim_detail.append("%s 샀다(%.2f RTT)→실질교집합 %s%s"
                                % (x["cond"], x["bought_rtt"]["ratio"],
                                   x["intersection_tol"],
                                   "" if ok else " <-- 고정 m 으로 부족"))
        elif lab == "못 샀다":
            if x["adapt_needed"] is None:
                claim_detail.append(
                    "%s 못 샀다(%.2f RTT)→통계교집합 %s 실질교집합 %s - 판정 불능"
                    "(고손실 여유 %s)"
                    % (x["cond"], x["bought_rtt"]["ratio"],
                       x["intersection_stat"], x["intersection_tol"],
                       ("%+.3f ms" % x["deciding_margin_ms"])
                       if x["deciding_margin_ms"] is not None else "-"))
                continue
            n_not += 1
            ok = bool(x["adapt_needed"])
            claim_ok.append(ok)
            claim_detail.append("%s 못 샀다(%.2f RTT)→통계교집합 %s(고손실 여유 %s)%s"
                                % (x["cond"], x["bought_rtt"]["ratio"],
                                   x["intersection_stat"],
                                   ("%+.3f ms" % x["deciding_margin_ms"])
                                   if x["deciding_margin_ms"] is not None else "-",
                                   "" if ok else " <-- 고정 m 하나로 충분하다"))
        else:
            claim_detail.append("%s 왕복 %s(%.2f RTT) - 판정 제외"
                                % (x["cond"], lab,
                                   x["bought_rtt"]["ratio"] or -1))
    add("6. 왕복을 산 조건은 고정 m 하나로 충분하고, 못 산 조건은 적응이 필요하다"
        + ("" if (n_bought and n_not) else "  [공허: 한 무리뿐]"),
        bool(claim_ok) and all(claim_ok) and n_bought > 0 and n_not > 0,
        " | ".join(claim_detail) if claim_detail else "자료 없음")

    need = [x for x in out["gain"] if x["adapt_needed"] is True]
    vac = not need
    tgt = need if need else out["gain"]
    fallback_scope = "exploratory_all_conditions_no_required_adaptation" if vac else "required_adaptation_conditions_same_data_labels"
    out["adaptation_check_scope"] = {"checks": [7, 8], "scope": fallback_scope,
                                     "required_condition_count": len(need),
                                     "targets": [x["cond"] for x in tgt], "confirmatory": False}

    def worst_hit_of(x):
        a = x["adapt"]
        hs = [a[l]["hit_rate"] for l in a if a[l]["hit_rate"] is not None]
        return min(hs) if hs else None

    hits = [(x["cond"], worst_hit_of(x)) for x in tgt]
    timelines_complete = all(a["timeline_complete"] for x in tgt
                             for a in x["adapt"].values())
    worst_hit = min([h for _c, h in hits if h is not None] or [0])
    add("7. auto가 실측 허용집합 안의 m을 과반 이상 고른다"
        + ("  [탐색적 전체 조건 대체: 적응 필요 조건 없음]" if vac else " [적응 필요 조건]"),
        tgt and timelines_complete and worst_hit > 0.5,
        ("최악 적중률 %.1f%% | " % (100 * worst_hit)
         + "  ".join("%s: %s" % (x["cond"], "  ".join(
             "손실%g%%: 허용 %s(최선 %s, 모형 m=%d) 적중 %.1f%% (n=%d)"
             % (l, x["adapt"][l]["allowed"], x["adapt"][l]["best_measured"],
                x["adapt"][l]["want_m_model"],
                100 * (x["adapt"][l]["hit_rate"] or 0), x["adapt"][l]["n"])
             for l in sorted(x["adapt"]))) for x in tgt))
        if tgt else "자료 없음", scope=fallback_scope)

    lag_rows = []
    never = 0
    for x in tgt:
        a = x["adapt"]
        lag_rows.append((x["cond"], [a[l]["lag_med"] for l in sorted(a)]))
        never += sum(a[l]["never_adapted"] for l in a)
    lags = [v for _c, vs in lag_rows for v in vs if v is not None]
    add("8. 적응이 필요한 조건에서 적응 지연이 구간 길이의 절반 미만이다"
        + ("  [탐색적 전체 조건 대체: 적응 필요 조건 없음]" if vac else ""),
        tgt and timelines_complete and lags and max(lags) < N / 2 and never == 0,
        ("적응한 구간에 한정한 중앙 지연 %s (구간 %d) | 끝까지 적응 못 한 구간 %d"
         % (lag_rows, N, never)) if tgt else "자료 없음", scope=fallback_scope)

    _free_name = _free[0] if _free else None
    gu = g.get(_free_name) if _free_name else None
    add("9. [부정] 무제한에서는 적응이 벌 것이 없다 (오라클 이득 상한 <= 탐색세 %.2f)"
        % PROBE_TAX_MS,
        gu and gu["oracle_gain_ms"] is not None
        and gu["oracle_gain_ci95_half_ms"] is not None
        and (gu["oracle_gain_ms"] + gu["oracle_gain_ci95_half_ms"])
        <= PROBE_TAX_MS,
        ("오라클 이득 %.3f ± %.3f ms -> %s | %s"
         % (gu["oracle_gain_ms"] if gu["oracle_gain_ms"] is not None
            else float("nan"),
            gu["oracle_gain_ci95_half_ms"]
            if gu["oracle_gain_ci95_half_ms"] is not None else float("nan"),
            gu["oracle_verdict"],
            " | ".join("손실%s: 최선 %s 허용 %s"
                       % (l, v["best"], v["allowed"])
                       for l, v in sorted(gu["allowed_by_loss"].items())
                       if v)))
        if gu else "자료 없음")

    for x in out["gain"]:
        og, oh = x["oracle_gain_ms"], x["oracle_gain_ci95_half_ms"]
        print("   [정보] %-8s 오라클 이득 %s ms -> %s | auto 시간 이득 %+.3f | "
              "분산 부풀림(pooled/짝지은) %s"
              % (x["cond"],
                 ("%.3f ± %.3f" % (og, oh)) if (og is not None and oh is not None)
                 else ("%.3f" % og if og is not None else "-"),
                 x["oracle_verdict"], x["gain_ms"],
                 ("%.1f배" % x["variance_inflation_pooled_over_paired"])
                 if x["variance_inflation_pooled_over_paired"] else "-"))

    crc = sum(r["srv_crc_fail"] or 0 for r in out["rows"])
    add("10. 복구 CRC 실패 0", crc == 0, "총 %d 건" % crc)

    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    out["journal_provenance"] = jr.provenance()
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(checks)))
    if DRYRUN:
        print("(드라이런: 결과 파일을 쓰지 않는다)")
    else:
        _fname = ("smoke_" if N < N_DEFAULT else "") + "p17_adaptive_value.json"
        print("saved: %s" % B.save(_fname, out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
