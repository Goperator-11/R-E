from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
import p2_threshold as P2
from padfec import amplif
from _journal import Journal, code_fingerprint

RTT_MS = P2.RTT_MS
LO, HI = P2.LO, P2.HI
RESOLUTION = P2.RESOLUTION
N_PROBE = P2.N_PROBE
N_CONFIRM = P2.N_CONFIRM

P = amplif.SERVER_PACKET_SIZE

JUMP_MODEL = 1245.5
JUMP_LO, JUMP_HI = 1100.0, 1400.0

MAIN_GROUP, MAIN_K = "x25519", 1
MAIN_IPS = [1279, 1280, 1281, 1282, 1300, 1350, 1450]
CROSS_GROUP, CROSS_K = "X25519MLKEM768", 2
CROSS_IPS = [1280, 1281, 1350]

PRED = {
    ("x25519", 1279): (3312, 3368),
    ("x25519", 1280): (3312, 3368),
    ("x25519", 1281): (4557, 4614),
    ("x25519", 1282): (4557, 4614),
    ("x25519", 1300): (4557, 4614),
    ("x25519", 1350): (4557, 4614),
    ("x25519", 1450): (4557, 4614),
    ("X25519MLKEM768", 1280): (5917, 5974),
    ("X25519MLKEM768", 1281): (7163, 7219),
    ("X25519MLKEM768", 1350): (7163, 7219),
}

P12C_GROUP, P12C_K = "x25519", 1
P12C_IPS = [1707, 2134]
P12C_PRED = {
    1707: (5, 5831.0, 5865.5),
    2134: (6, 7076.5, 7145.5),
}
P12C_FEAS_CERT = 2000
P12C_FEAS_N = 6
MTU = 1500
UDP_PAYLOAD_MAX = MTU - 20 - 8
QUICGO_MAX_PACKET_BUFFER = 1452

SMOKE_IPS = [1280, 1281]
SMOKE_CERTS = [2000, 8000]
SMOKE_N = 6


def log(msg=""):
    print(msg)
    sys.stdout.flush()


def add(results, name, ok, detail):
    results.append({"check": name, "ok": bool(ok), "detail": detail,
                    "gating": True})
    log("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail))


def add_info(results, name, ok, detail, **extra):
    rec = {"check": name, "ok": bool(ok), "detail": detail, "gating": False}
    rec.update(extra)
    results.append(rec)
    log("[%s] %-58s %s" % ("정보 O" if ok else "정보 X", name, detail))


def probe(group, ips, cert, k, n, jr):
    key = "%s|ips%d|c%d|n%d" % (group, ips, cert, n)
    if jr.has(key):
        return jr.get(key)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    p, _sp = B.start_server(cert, fec="off")
    rows, cs, _err = B.run_client(group, n, fec="off",
                                  ips=(0 if ips == 1280 else ips),
                                  gap_ms=15, expect_k=k)
    B.stop_server(p)
    ss = B.read_server_stats(_sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"group": group, "ips": ips, "cert": cert, "n": s["n"],
           "ok": s["ok"], "p50": s["p50"],
           "two_rtt_rate": s["two_rtt_rate"],
           "first_flight_bytes": cs.get("first_flight_bytes"),
           "first_flight_datagrams": cs.get("first_flight_datagrams"),
           "n_req": n, "n_failed": s["n"] - s["ok"],
           "n_missing": max(0, n - s["n"]),
           "client_rows": rows, "client_stats": cs, "server_stats": ss,
           "collection_provenance": {"run_id": jr.run_id, "journal_key": key,
                                     "fingerprint": jr.fingerprint,
                                     "started_at": started,
                                     "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                     "expected_k_flush_hint": k,
                                     "time_scope": "collection interval, not individual connection timestamps"},
           "error": _err, "valid": not _err and n > 0 and s["ok"] == s["n"] == n}
    if rec["valid"]:
        jr.record(key, rec)
    else:
        if not hasattr(jr, "_p12_failed_probe_units"):
            jr._p12_failed_probe_units = []
        jr._p12_failed_probe_units.append({"key": key, "result": rec,
                                           "journaled": False, "reused": False})
    return rec


def consumed_units(jr):
    provenance = jr.provenance()
    return {"journal_provenance": provenance,
            "probe_units": [{"key": unit["key"], "result": jr.get(unit["key"])}
                            for unit in provenance["units"]],
            "failed_probe_units": list(getattr(jr, "_p12_failed_probe_units", [])),
            "probe_unit_scope": "completed journal units and separate failed attempts; reused units are prior measurements; recording times are not measurement start times"}


def bisect_threshold(group, ips, k, jr):
    lo, hi = LO, HI
    r_lo = probe(group, ips, lo, k, N_PROBE, jr)
    r_hi = probe(group, ips, hi, k, N_PROBE, jr)
    log("  경계 확인: cert %d -> ok %d/%d 2RTT %.0f%% / cert %d -> ok %d/%d "
        "2RTT %.0f%%"
        % (lo, r_lo["ok"], r_lo["n"], 100 * (r_lo["two_rtt_rate"] or 0),
           hi, r_hi["ok"], r_hi["n"], 100 * (r_hi["two_rtt_rate"] or 0)))
    a, b = P2.is_two_rtt(r_lo), P2.is_two_rtt(r_hi)
    if a is None or b is None:
        return {"lo": None, "hi": None, "ref": r_lo,
                "note": "경계에서 핸드셰이크 실패 - 판정 불가"}
    if a:
        return {"lo": None, "hi": lo, "ref": r_lo,
                "note": "하한(%d B)에서 이미 2-RTT" % lo}
    if not b:
        return {"lo": hi, "hi": None, "ref": r_lo,
                "note": "상한(%d B)에서도 1-RTT" % hi}
    while hi - lo > RESOLUTION:
        mid = (lo + hi) // 2
        r = probe(group, ips, mid, k, N_PROBE, jr)
        if P2.is_two_rtt(r) is None:
            return {"lo": None, "hi": None, "ref": r_lo,
                    "note": "cert %d 에서 핸드셰이크 실패 - 판정 불가" % mid}
        rate = r["two_rtt_rate"] or 0.0
        if 0.2 < rate < 0.8:
            r = probe(group, ips, mid, k, N_CONFIRM, jr)
            if P2.is_two_rtt(r) is None:
                return {"lo": None, "hi": None, "ref": r_lo,
                        "note": "cert %d 재확인 실패 - 판정 불가" % mid}
            rate = r["two_rtt_rate"] or 0.0
        if rate >= 0.5:
            hi = mid
        else:
            lo = mid
        log("    cert %-6d 2RTT %5.0f%%  ->  구간 [%d, %d]"
            % (mid, 100 * rate, lo, hi))
    return {"lo": lo, "hi": hi, "ref": r_lo, "note": ""}


def usable(rec):
    if not rec:
        return False
    if rec.get("threshold_lo") is None or rec.get("threshold_hi") is None:
        return False
    if rec.get("note"):
        return False
    return True


def mid_of(rec):
    if not usable(rec):
        return None
    return 0.5 * (rec["threshold_lo"] + rec["threshold_hi"])


def same_bin(a, b):
    if not usable(a) or not usable(b):
        return False
    return (a["threshold_lo"] == b["threshold_lo"]
            and a["threshold_hi"] == b["threshold_hi"])


def distinct_bin(a, b):
    if not usable(a) or not usable(b):
        return False
    return not same_bin(a, b)


def measure(group, ips, k, jr):
    log("")
    log("[%s / ips %d] 임계 이분탐색" % (group, ips))
    th = bisect_threshold(group, ips, k, jr)
    ref = th["ref"]
    ffb = ref.get("first_flight_bytes")
    ffd = ref.get("first_flight_datagrams")

    b_pred = k * ips
    premise = (ffb == b_pred and ffd == k)

    b_use = ffb if ffb else None
    k_use = ffd or k
    if b_use:
        allowed = amplif.allowed_bytes(b_use)
        dmin = allowed // 3 - b_use + 1
        bin_no = allowed // P
        amp = float(allowed) / b_use
        bnd = ips + -(-dmin // max(1, k_use))
    else:
        allowed = dmin = bin_no = amp = bnd = None
    rec = {"group": group, "ips": ips, "k": ffd, "k_expected": k,
           "k_use": k_use,
           "first_flight_bytes": ffb, "first_flight_bytes_pred": b_pred,
           "premise_B_eq_k_ips": premise,
           "allowed_pred": allowed, "bin": bin_no,
           "amp_ratio": amp,
           "delta_min": dmin,
           "boundary_ips": bnd,
           "threshold_lo": th["lo"], "threshold_hi": th["hi"],
           "note": th["note"], "usable": None,
           "jump_from_prev": None, "jump_from_ips": None}
    rec["usable"] = usable(rec)
    rec["threshold_mid"] = mid_of(rec)
    if usable(rec) and b_use:
        rec["s0_est"] = amplif.fit_s0(th["lo"], th["hi"], b_use)
        rec["s0_mid"] = rec["s0_est"]["s0_mid"]
    else:
        rec["s0_est"], rec["s0_mid"] = None, None
    pr = PRED.get((group, ips))
    rec["pred_lo"], rec["pred_hi"] = (pr if pr else (None, None))
    rec["pred_hit"] = bool(pr and usable(rec)
                           and th["lo"] == pr[0] and th["hi"] == pr[1])
    rec["in_sample"] = True if pr else None
    rec["pred_gating"] = False
    log("  => B %s B (예측 %d), 허용 %s B (칸 %s), 임계 %s ~ %s B, "
        "s0 %s, Δ_min %s -> 경계 ips %s"
        % (ffb, b_pred, allowed, rec["bin"], th["lo"], th["hi"],
           ("%.1f" % rec["s0_mid"]) if rec["s0_mid"] is not None else "-",
           dmin, rec["boundary_ips"]))
    return rec


def judge(configs, results, info):
    by = {}
    for c in configs:
        by[(c["group"], c["ips"])] = c

    for c in configs:
        add(results, "전제 B=k·ips [%s/%d]" % (c["group"], c["ips"]),
            c["premise_B_eq_k_ips"],
            "실측 B=%s k=%s, 예측 B=%d k=%d"
            % (c["first_flight_bytes"], c["k"],
               c["first_flight_bytes_pred"], c["k_expected"]))

    a, b = by.get((MAIN_GROUP, 1279)), by.get((MAIN_GROUP, 1280))
    ok = same_bin(a, b) and (a or {}).get("allowed_pred") == (b or {}).get(
        "allowed_pred")
    add(results, "부정시험: ips 1279 와 1280 은 같은 칸", ok,
        "1279 임계 %s~%s (허용 %s) / 1280 임계 %s~%s (허용 %s)"
        % ((a or {}).get("threshold_lo"), (a or {}).get("threshold_hi"),
           (a or {}).get("allowed_pred"), (b or {}).get("threshold_lo"),
           (b or {}).get("threshold_hi"), (b or {}).get("allowed_pred")))

    c1281 = by.get((MAIN_GROUP, 1281))
    j = c1281.get("jump_from_prev") if c1281 else None
    jfrom = c1281.get("jump_from_ips") if c1281 else None
    add(results, "절벽: ips 1280 -> 1281 에서 임계가 한 칸 도약",
        j is not None and JUMP_LO <= j <= JUMP_HI and jfrom == 1280,
        "도약 %s B (실제 비교 대상 ips %s, 모형 %.1f, 허용창 %.0f~%.0f)"
        % (("%.1f" % j) if j is not None else "판정 불가",
           jfrom if jfrom is not None else "-",
           JUMP_MODEL, JUMP_LO, JUMP_HI))

    pl_ips = (1281, 1282, 1300, 1350, 1450)
    plateau = [by.get((MAIN_GROUP, i)) for i in pl_ips]
    ok = (usable(plateau[0])
          and all(same_bin(plateau[0], x) for x in plateau[1:]))
    add(results, "고원: ips 1281·1282·1300·1350·1450 은 같은 칸", ok,
        " / ".join("%d:%s~%s" % (x["ips"], x["threshold_lo"],
                                 x["threshold_hi"])
                   for x in plateau if x) or "자료 없음")

    for c in configs:
        if c["pred_lo"] is None:
            continue
        add_info(info, "예측 대조 [%s/%d]" % (c["group"], c["ips"]),
                 c["pred_hit"],
                 "예측 [%d,%d] vs 실측 [%s,%s] (p2 관측 칸을 옮겨 적은 값 - "
                 "out-of-sample 아님)"
                 % (c["pred_lo"], c["pred_hi"], c["threshold_lo"],
                    c["threshold_hi"]),
                 group=c["group"], ips=c["ips"], in_sample=True)

    add(results, "따름정리: W=1280 에서 Δ_min=1, 경계 ips=1281",
        bool(b) and b.get("delta_min") == 1
        and b.get("boundary_ips") == 1281 and distinct_bin(b, c1281),
        ("Δ_min %s, 경계 ips %s, 1280 과 1281 이 다른 칸: %s"
         % (b.get("delta_min"), b.get("boundary_ips"),
            "예" if distinct_bin(b, c1281) else "아니오"))
        if b else "ips 1280 레코드 없음 - 판정 불가")

    prem_a = bool(a) and usable(a) and bool(a.get("premise_B_eq_k_ips"))
    add(results, "보조정리2: ips 1279 의 Δ_min=2 도 경계 1281 을 가리킨다",
        prem_a and a.get("delta_min") == 2
        and a.get("boundary_ips") == 1281,
        ("Δ_min %s -> 경계 ips %s" % (a.get("delta_min"),
                                      a.get("boundary_ips")))
        if prem_a else
        ("전제 미확인(실측 B=%s, k=%s / 예측 B=%s, 임계 %s~%s, note %r) - "
         "판정 불가"
         % (a.get("first_flight_bytes"), a.get("k"),
            a.get("first_flight_bytes_pred"), a.get("threshold_lo"),
            a.get("threshold_hi"), a.get("note"))
         if a else "ips 1279 레코드 없음 - 판정 불가"))

    for g in (MAIN_GROUP, CROSS_GROUP):
        seq = [c for c in configs if c["group"] == g
               and c["threshold_mid"] is not None]
        seq.sort(key=lambda c: c["ips"])
        mono = all(seq[i]["threshold_mid"] >= seq[i - 1]["threshold_mid"]
                   for i in range(1, len(seq)))
        add(results, "단조성: %s 임계가 ips 에 대해 비감소" % g,
            mono and len(seq) >= 2,
            " -> ".join("%.1f" % c["threshold_mid"] for c in seq) or "자료 없음")

    x = by.get((CROSS_GROUP, 1281))
    jx = x.get("jump_from_prev") if x else None
    jxfrom = x.get("jump_from_ips") if x else None
    add(results, "교차: ML-KEM(k=2) 1280 -> 1281 도 한 칸 도약",
        jx is not None and JUMP_LO <= jx <= JUMP_HI and jxfrom == 1280,
        "도약 %s B (실제 비교 대상 ips %s, k=2 이므로 B 는 +2 B 늘었다)"
        % (("%.1f" % jx) if jx is not None else "판정 불가",
           jxfrom if jxfrom is not None else "-"))

    cpl = [by.get((CROSS_GROUP, i)) for i in (1281, 1350)]
    add(results, "교차 고원: ML-KEM ips 1281·1350 은 같은 칸",
        usable(cpl[0]) and same_bin(cpl[0], cpl[1]),
        " / ".join("%d:%s~%s" % (y["ips"], y["threshold_lo"],
                                 y["threshold_hi"])
                   for y in cpl if y) or "자료 없음")


def fill_jumps(configs):
    for g in (MAIN_GROUP, CROSS_GROUP):
        seq = [c for c in configs if c["group"] == g]
        seq.sort(key=lambda c: c["ips"])
        prev, prev_ips = None, None
        for c in seq:
            m = c["threshold_mid"]
            if prev is not None and m is not None:
                c["jump_from_prev"] = m - prev
                c["jump_from_ips"] = prev_ips
            if m is not None:
                prev, prev_ips = m, c["ips"]


def feasible_ips(group, ips, k, jr):
    r = probe(group, ips, P12C_FEAS_CERT, k, P12C_FEAS_N, jr)
    ffb, ffd = r.get("first_flight_bytes"), r.get("first_flight_datagrams")
    if not (r["n"] > 0 and r["ok"] == r["n"]):
        return False, ("핸드셰이크 %s/%s - 이 크기로는 연결이 안 선다"
                       % (r["ok"], r["n"])), r
    if ffb != k * ips or ffd != k:
        return False, ("실측 B=%s (데이터그램 %s) != k·ips=%d - 스택이 ips 를 "
                       "깎았다(quic-go MaxPacketBufferSize=%d, UDP 페이로드 "
                       "상한 %d)"
                       % (ffb, ffd, k * ips, QUICGO_MAX_PACKET_BUFFER,
                          UDP_PAYLOAD_MAX)), r
    return True, "", r


def run_p12c(jr, checks):
    recs = []
    for ips in P12C_IPS:
        n_bin, pred_pkt, pred_const = P12C_PRED[ips]
        rec = {"group": P12C_GROUP, "ips": ips, "k_expected": P12C_K,
               "bin_expected": n_bin, "in_sample": False, "gating": False,
               "pred_threshold_packet_term": pred_pkt,
               "pred_threshold_const_s0": pred_const,
               "models_diverge_by": round(pred_const - pred_pkt, 1),
               "mtu": MTU, "udp_payload_max": UDP_PAYLOAD_MAX,
               "quicgo_max_packet_buffer": QUICGO_MAX_PACKET_BUFFER,
               "exceeds_mtu": ips > UDP_PAYLOAD_MAX,
               "threshold_lo": None, "threshold_hi": None,
               "threshold_mid": None, "model_supported": None}
        log("")
        log("[p12c %s / ips %d] 먼저 실현 가능성 (MTU %d, UDP 페이로드 상한 "
            "%d, quic-go 상한 %d)"
            % (P12C_GROUP, ips, MTU, UDP_PAYLOAD_MAX,
               QUICGO_MAX_PACKET_BUFFER))
        ok, why, fr = feasible_ips(P12C_GROUP, ips, P12C_K, jr)
        rec["feasibility"] = {
            "cert": P12C_FEAS_CERT, "n": fr["n"], "ok": fr["ok"],
            "first_flight_bytes": fr.get("first_flight_bytes"),
            "first_flight_datagrams": fr.get("first_flight_datagrams"),
            "expected_first_flight_bytes": P12C_K * ips}
        add_info(checks, "p12c: ips %d 를 그 크기로 보낼 수 있는가" % ips, ok,
                 why or ("실측 B=%s = k·ips" % fr.get("first_flight_bytes")),
                 group=P12C_GROUP, ips=ips, in_sample=False)
        if not ok:
            rec["status"] = "skipped"
            rec["skip_reason"] = why
            log("  => skipped: %s" % why)
            log("     (예측은 그대로 남긴다: 패킷항 %.1f vs 상수 s0 %.1f, "
                "차 %.1f B)" % (pred_pkt, pred_const,
                                pred_const - pred_pkt))
            recs.append(rec)
            continue

        m = measure(P12C_GROUP, ips, P12C_K, jr)
        merged = dict(m)
        merged.update(rec)
        merged["threshold_lo"] = m["threshold_lo"]
        merged["threshold_hi"] = m["threshold_hi"]
        merged["threshold_mid"] = m["threshold_mid"]
        merged["status"] = "measured" if usable(m) else "unusable"
        mid = merged["threshold_mid"]
        if mid is not None:
            d_pkt, d_const = abs(mid - pred_pkt), abs(mid - pred_const)
            width = merged["threshold_hi"] - merged["threshold_lo"]
            merged["dist_packet_term"] = round(mid - pred_pkt, 1)
            merged["dist_const_s0"] = round(mid - pred_const, 1)
            merged["grid_width"] = width
            merged["models_separable_by_grid"] = bool(
                abs(pred_const - pred_pkt) > width)
            merged["model_supported"] = (
                "packet_term" if d_pkt < d_const
                else ("const_s0" if d_const < d_pkt else "tie"))
            add_info(checks,
                     "p12c: ips %d 임계가 어느 모형에 가까운가" % ips,
                     merged["model_supported"] == "packet_term",
                     "실측 중점 %.1f | 패킷항 %.1f (차 %+.1f) vs 상수 s0 "
                     "%.1f (차 %+.1f) | 격자 폭 %d B, 두 모형 간격 %.1f B "
                     "-> %s"
                     % (mid, pred_pkt, merged["dist_packet_term"],
                        pred_const, merged["dist_const_s0"], width,
                        abs(pred_const - pred_pkt),
                        "가를 수 있다" if merged["models_separable_by_grid"]
                        else "**격자보다 좁아 못 가른다**"),
                     group=P12C_GROUP, ips=ips, in_sample=False)
        else:
            merged["skip_reason"] = m["note"] or "임계 판정 불가"
            add_info(checks, "p12c: ips %d 임계 판정" % ips, False,
                     merged["skip_reason"], group=P12C_GROUP, ips=ips,
                     in_sample=False)
        recs.append(merged)
    return recs


def smoke(jr):
    results, runs = [], []
    for ips in SMOKE_IPS:
        for cert in SMOKE_CERTS:
            r = probe(MAIN_GROUP, ips, cert, MAIN_K, SMOKE_N, jr)
            runs.append(r)
            log("  ips %-5d cert %-5d  ok %d/%d  p50 %s ms  2RTT %.0f%%  "
                "B %s"
                % (ips, cert, r["ok"], r["n"], r["p50"],
                   100 * (r["two_rtt_rate"] or 0.0),
                   r["first_flight_bytes"]))
    log("")
    for r in runs:
        add(results, "건식: 핸드셰이크 성공 [ips %d/cert %d]"
            % (r["ips"], r["cert"]), r["ok"] == r["n"] and r["n"] > 0,
            "%d/%d 성공" % (r["ok"], r["n"]))
    for r in runs:
        add(results, "건식: B=k·ips [ips %d/cert %d]" % (r["ips"], r["cert"]),
            r["first_flight_bytes"] == MAIN_K * r["ips"]
            and r["first_flight_datagrams"] == MAIN_K,
            "B %s (예측 %d), k %s"
            % (r["first_flight_bytes"], MAIN_K * r["ips"],
               r["first_flight_datagrams"]))
    for r in runs:
        want2 = r["cert"] >= 8000
        got = P2.is_two_rtt(r)
        add(results, "건식: cert %d 는 %s [ips %d]"
            % (r["cert"], "2-RTT" if want2 else "1-RTT", r["ips"]),
            got is not None and got == want2,
            "2RTT 비율 %.0f%%" % (100 * (r["two_rtt_rate"] or 0.0)))
    return results, runs


def main():
    is_smoke = "--smoke" in sys.argv
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()
    B.set_netem(RTT_MS / 2.0)

    fp = code_fingerprint(["experiments/p12_quantum.py",
                           "experiments/p2_threshold.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jname = "p12_smoke_units.jsonl" if is_smoke else "p12_units.jsonl"
    jr = Journal(os.path.join(B.STATE, jname), fp)

    log("=" * 100)
    log("P12 양자 경계 절벽%s   RTT %.0f ms, 격자 [%d,%d] 해상도 %d (폭 ≈56 B), "
        "n %d/%d" % ("  [건식]" if is_smoke else "", RTT_MS, LO, HI,
                     RESOLUTION, N_PROBE, N_CONFIRM))
    log("=" * 100)

    if is_smoke:
        results, runs = smoke(jr)
        npass = sum(1 for r in results if r["ok"])
        out = {"smoke": True, "rtt_ms": RTT_MS, "n": SMOKE_N,
               **consumed_units(jr),
               "runs": runs,
               "checks": results, "passed": npass, "total": len(results)}
        log("")
        log("건식 %d / %d 통과 - 측정 경로 %s"
            % (npass, len(results),
               "살아 있다" if npass == len(results) else "어딘가 죽었다"))
        log("saved: %s" % B.save("p12_quantum_smoke.json", out))
        return 0 if npass == len(results) else 1

    configs = []
    for ips in MAIN_IPS:
        configs.append(measure(MAIN_GROUP, ips, MAIN_K, jr))
    for ips in CROSS_IPS:
        configs.append(measure(CROSS_GROUP, ips, CROSS_K, jr))
    fill_jumps(configs)

    p12c_checks = []
    p12c = run_p12c(jr, p12c_checks)

    log("")
    log("=" * 100)
    log("%-16s %-6s %-3s %-7s %-8s %-4s %-15s %-9s %-9s %s"
        % ("그룹", "ips", "k", "B", "허용", "칸", "임계", "s0", "Δ_min",
           "직전 대비 (무엇과)"))
    log("-" * 100)
    for c in configs:
        log("%-16s %-6d %-3s %-7s %-8s %-4s %-15s %-9s %-9s %s"
            % (c["group"], c["ips"], c["k"], c["first_flight_bytes"],
               c["allowed_pred"], c["bin"],
               "%s~%s" % (c["threshold_lo"], c["threshold_hi"]),
               ("%.1f" % c["s0_mid"]) if c["s0_mid"] is not None else "-",
               c["delta_min"],
               ("%+.1f B (ips %s)" % (c["jump_from_prev"],
                                      c["jump_from_ips"]))
               if c["jump_from_prev"] is not None else "-"))

    log("")
    log("=" * 100)
    log("p12c (칸 5·6, 두 모형이 갈리는 지점) - 게이팅 아님")
    log("-" * 100)
    for c in p12c:
        log("%-16s %-6d %-9s %-15s 패킷항 %-9.1f 상수s0 %-9.1f  %s"
            % (c["group"], c["ips"], c["status"],
               "%s~%s" % (c["threshold_lo"], c["threshold_hi"]),
               c["pred_threshold_packet_term"],
               c["pred_threshold_const_s0"],
               c.get("model_supported") or c.get("skip_reason", "")))

    log("")
    log("=" * 100)
    log("판정")
    log("=" * 100)
    results, preds = [], []
    judge(configs, results, preds)

    npass = sum(1 for r in results if r["ok"])
    log("")
    log("-" * 100)
    log("게이팅 %d / %d 통과   (정보: 예측 대조 %d/%d, p12c %d/%d - 종료코드 "
        "무관)"
        % (npass, len(results),
           sum(1 for r in preds if r["ok"]), len(preds),
           sum(1 for r in p12c_checks if r["ok"]), len(p12c_checks)))
    if npass != len(results):
        log("실패 항목(게이팅):")
        for r in results:
            if not r["ok"]:
                log("  - %s | %s" % (r["check"], r["detail"]))

    out = {"smoke": False, "rtt_ms": RTT_MS, "resolution": RESOLUTION,
           **consumed_units(jr),
           "n_probe": N_PROBE, "n_confirm": N_CONFIRM,
           "server_packet_size": P, "jump_model": JUMP_MODEL,
           "jump_window": [JUMP_LO, JUMP_HI],
           "predictions": [{"group": g, "ips": i, "pred_lo": lo,
                            "pred_hi": hi, "gating": False,
                            "in_sample": True}
                           for (g, i), (lo, hi) in sorted(PRED.items())],
           "predictions_out_of_sample": [
               {"group": P12C_GROUP, "ips": i, "bin": n,
                "pred_threshold_packet_term": pk,
                "pred_threshold_const_s0": cs,
                "gating": False, "in_sample": False}
               for i, (n, pk, cs) in sorted(P12C_PRED.items())],
           "configs": configs,
           "p12c": p12c, "p12c_checks": p12c_checks,
           "checks": results, "prediction_checks": preds,
           "passed": npass, "total": len(results),
           "gating_changed_at": "2026-08-20",
           "gating_note": ("passed/total 은 게이팅 검사만 센다. "
                           "prediction_checks 와 p12c_checks 는 gating=false "
                           "정보이며 종료코드에 들어가지 않는다. "
                           "2026-08-20 게이팅 집합 교체: 예측 대조 8건을 "
                           "정보로 내리고(p2 관측 칸을 옮겨 적은 값이라 "
                           "out-of-sample 이 아님), 레코드가 없으면 조용히 "
                           "사라지던 따름정리·보조정리2 2건을 항상 기록하도록 "
                           "바꿔 게이팅 19건이 됐다. 보조정리2 는 전제 "
                           "B=k·ips 가 실측으로 확인된 레코드에서만 판정한다.")}
    log("saved: %s" % B.save("p12_quantum.json", out))
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
