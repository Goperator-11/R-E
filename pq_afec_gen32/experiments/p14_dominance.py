from __future__ import annotations

import datetime as dt
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B
from padfec import policy as POL
from padfec import quantum as Q

RTT_MS = 50.0
GROUP = "x25519"
K = 1
W = 1280
CERT = 4032
N = 400
LOSSES = (0.0, 5.0)
UPLINK_MBPS = 0.0

ARMS = [("base", 0, 0), ("pad", 1, 0), ("parity", 0, 1), ("combo", 1, 1)]


def mean(v):
    return (sum(v) / len(v)) if v else None


def model(delta, m, p):
    cd = Q._candidate("x", m, delta, B.measured_C(GROUP), W, 51, 16,
                      CERT, None,
                      K * W, Q.bin_index(K * W), W, k_floor=K,
                      s0_base=POL.S0_BASE_X25519,
                      c_pkt=POL.C_PKT_POLICY_DEFAULT,
                      parity_bytes=POL.parity_datagram_bytes)
    e = POL.cost_of_v2(cd, W, RTT_MS, p, 1.0, k0=K, uplink_mbps=UPLINK_MBPS)
    return {"p_two_rtt": e["p_two_rtt"], "p_fail": e["p_fail"],
            "j_ms": e["j_ms"], "client_bytes": e["client_bytes_real"],
            "allowed": e["allowed_real"], "server_flight": cd["server_flight"]}


def arm_evidence(rows, cs, ss, err, n_req):
    n_ok = sum(1 for row in rows if row.get("ok"))
    return {"n_req": n_req, "n_rows": len(rows), "n_failed": len(rows) - n_ok,
            "n_missing": max(0, n_req - len(rows)), "client_rows": rows,
            "client_stats": cs, "server_stats": ss,
            "client_coverage_complete": len(rows) == n_req and n_ok == n_req and not err,
            "recording_scope": "available client rows and server connection records; equal counts alone do not establish matching"}


def run_arm(name, delta, m, loss):
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    collection_id = uuid.uuid4().hex
    fec = "on" if m > 0 else "off"
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    p_, sp = B.start_server(CERT, fec=fec)
    rows, cs, err = B.run_client(GROUP, N, fec=fec, m=max(m, 1),
                                 ips=(W + delta) if delta else 0,
                                 gap_ms=8, timeout_s=10, expect_k=K,
                                 uplink_mbps=UPLINK_MBPS)
    B.stop_server(p_)
    ss = B.read_server_stats(sp)
    cs["collection_provenance"] = {
        "collection_id": collection_id, "started_at": started,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "group": GROUP, "expected_k_flush_hint": K, "fec": fec, "m": m,
        "delta": delta, "cert": CERT, "n_req": N, "loss_c2s_percent": loss,
        "requested_rtt_ms": RTT_MS, "requested_uplink_mbps": UPLINK_MBPS,
        "time_scope": "collection interval, not individual connection timestamps"}
    ok = [r["ms"] for r in rows if r.get("ok")]
    ff = [(r.get("first_flight_bytes") or 0)
          + (r.get("first_flight_parity_bytes") or 0) for r in rows]
    return {**arm_evidence(rows, cs, ss, err, N),
            "arm": name, "delta": delta, "m": m, "loss": loss,
            "n": len(rows), "ok": len(ok), "mean": mean(ok),
            "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
            "two_rtt_rate": (sum(1 for t in ok if 1.5 * RTT_MS < t
                                 <= 3.0 * RTT_MS) / float(len(ok)))
            if ok else None,
            "pto_rate": (sum(1 for t in ok if t > 3.0 * RTT_MS)
                         / float(len(ok))) if ok else None,
            "ff_bytes_med": sorted(ff)[len(ff) // 2] if ff else 0,
            "srv_recovered": ss.get("recovered"),
            "srv_crc_fail": ss.get("recover_crc_fail"),
            "srv_bytes_in": ss.get("bytes_in"),
            "srv_bytes_to_stack": ss.get("bytes_to_stack"),
            "srv_conn_n": len(ss.get("conns") or {}),
            "srv_conn_amp_bad": sum(
                1 for c_ in (ss.get("conns") or {}).values()
                if (c_.get("stack_bytes") or 0)
                > (c_.get("rx_bytes") or 0)),
            "srv_conn_amp_worst": max(
                [(c_.get("stack_bytes") or 0) - (c_.get("rx_bytes") or 0)
                 for c_ in (ss.get("conns") or {}).values()] or [None]),
            "srv_stats_present": bool(ss),
            "ms": ok, "err": err}


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup(mtu=1500)

    out = {"rtt_ms": RTT_MS, "group": GROUP, "cert": CERT, "n": N,
           "uplink_mbps": UPLINK_MBPS, "arms": [], "model": {}, "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail[:72]))
        sys.stdout.flush()

    for nm, d, m in ARMS:
        for p in (0.0, 0.05):
            out["model"]["%s@%.2f" % (nm, p)] = model(d, m, p)

    print("=" * 104)
    print("cert %d (맨몸 2-RTT 자리) 에서 네 팔 - base / pad(δ=1) / "
          "parity(m=1) / combo(δ=1·m=1)" % CERT)
    print("=" * 104)
    print("%-8s %-7s %-9s %-9s %-9s %-9s %-7s %s"
          % ("팔", "손실%", "평균", "p50", "2-RTT", "PTO", "복구", "모형 2-RTT"))

    for loss in LOSSES:
        for nm, d, m in ARMS:
            r = run_arm(nm, d, m, loss)
            out["arms"].append(r)
            mo = out["model"]["%s@%.2f" % (nm, loss / 100.0)]
            print("%-8s %-7.1f %-9.2f %-9.2f %-9s %-9s %-7s %.4f"
                  % (nm, loss, r["mean"] or -1, r["p50"] or -1,
                     "%.1f%%" % (100 * (r["two_rtt_rate"] or 0)),
                     "%.1f%%" % (100 * (r["pto_rate"] or 0)),
                     r["srv_recovered"], mo["p_two_rtt"]))
            sys.stdout.flush()

    def get(nm, loss):
        return next((r for r in out["arms"]
                     if r["arm"] == nm and r["loss"] == loss), None)

    print()
    print("=" * 104)

    b0 = get("base", 0.0)
    others0 = [get(nm, 0.0) for nm in ("pad", "parity", "combo")]
    ok1 = (b0 and b0["p50"] and all(o and o["p50"] for o in others0)
           and all(b0["p50"] - o["p50"] >= 0.8 * RTT_MS for o in others0))
    add("1. 무손실: 세 팔 전부 맨몸보다 1 왕복 빠르다",
        ok1, "맨몸 %.1f | pad %.1f / parity %.1f / combo %.1f ms"
        % (b0["p50"] if b0 else -1,
           *[o["p50"] if o else -1 for o in others0]))

    p50s = [o["p50"] for o in others0 if o and o["p50"]]
    add("2. 무손실: 세 팔의 p50 차가 2 ms 미만 (신용 동등)",
        len(p50s) == 3 and (max(p50s) - min(p50s)) < 2.0,
        "폭 %.2f ms (%s)" % ((max(p50s) - min(p50s)) if len(p50s) == 3 else -1,
                             ["%.2f" % v for v in p50s]))

    par5 = get("parity", 5.0)
    mo_par = out["model"]["parity@0.05"]
    ok3 = (par5 and par5["two_rtt_rate"] is not None
           and abs(par5["two_rtt_rate"] - mo_par["p_two_rtt"]) < 0.04)
    add("3. 손실 5%: parity 의 2-RTT 율이 정정 모형(약 2p)과 맞는다",
        ok3, "실측 %.1f%% vs 모형 %.1f%% (옛 회계는 %.1f%% 였다)"
        % (100 * (par5["two_rtt_rate"] or 0) if par5 else -1,
           100 * mo_par["p_two_rtt"], 100 * 0.05))

    pad5 = get("pad", 5.0)
    ok4 = (pad5 and (pad5["two_rtt_rate"] or 0) < 0.02
           and (pad5["srv_recovered"] or 0) == 0)
    add("4. 손실 5%: pad 는 신용을 안 잃는다(2-RTT<2%) - 대신 복구 0",
        ok4, "2-RTT %.1f%% / PTO %.1f%% / 복구 %s"
        % (100 * (pad5["two_rtt_rate"] or 0) if pad5 else -1,
           100 * (pad5["pto_rate"] or 0) if pad5 else -1,
           pad5["srv_recovered"] if pad5 else "-"))

    com5 = get("combo", 5.0)
    ok5 = (com5 and (com5["two_rtt_rate"] or 0) < 0.02
           and (com5["srv_recovered"] or 0) > 0)
    add("5. [핵심] 손실 5%: combo(δ=1·m=1) 는 2-RTT<2% 이면서 복구도 한다",
        ok5, "2-RTT %.1f%% / 복구 %s (parity 는 2-RTT %.1f%%, "
             "pad 는 복구 0)"
        % (100 * (com5["two_rtt_rate"] or 0) if com5 else -1,
           com5["srv_recovered"] if com5 else "-",
           100 * (par5["two_rtt_rate"] or 0) if par5 else -1))

    m5 = {nm: (get(nm, 5.0)["mean"] if get(nm, 5.0) else None)
          for nm, _, _ in ARMS}
    have = {k_: v for k_, v in m5.items() if v is not None}
    ok6 = have and min(have, key=lambda a: have[a]) == "combo"
    add("6. 손실 5%: combo 의 평균 HCT 가 네 팔 중 최저",
        ok6, " / ".join("%s %.2f" % (k_, v) for k_, v in have.items()))

    max_pad = K * (POL.QUICGO_MAX_IPS - W)
    min_par = POL.parity_datagram_bytes(W, K)
    add("7. [부정] 옛 보조정리의 전제 '같은 Δ' 는 도달 불가능하다",
        max_pad < min_par,
        "pad 최대 Δ %d B (ips 상한 %d) < 패리티 최소 Δ %d B"
        % (max_pad, POL.QUICGO_MAX_IPS, min_par))

    crc = sum(r["srv_crc_fail"] or 0 for r in out["arms"])
    add("8. 복구 CRC 실패 0", crc == 0, "총 %d 건" % crc)
    bad_acct = [r["arm"] for r in out["arms"]
                if (r["srv_bytes_to_stack"] or 0) > (r["srv_bytes_in"] or 0)]
    add("9. 회계 불변식: 스택 누적 <= 물리 수신 누적",
        not bad_acct, "위반 %s" % (bad_acct or "없음"))
    add("10. 모든 팔에서 서버 통계가 실제로 있었다",
        all(r["srv_stats_present"] for r in out["arms"]) and out["arms"],
        "%d/%d" % (sum(1 for r in out["arms"] if r["srv_stats_present"]),
                   len(out["arms"])))

    conn_bad = [(r["arm"], r["srv_conn_amp_bad"]) for r in out["arms"]
                if (r["srv_conn_amp_bad"] or 0) > 0]
    n_conn = sum(r["srv_conn_n"] or 0 for r in out["arms"])
    worst = max([r["srv_conn_amp_worst"] for r in out["arms"]
                 if r["srv_conn_amp_worst"] is not None] or [None])
    add("11. [연결별] 스택 <= 물리 수신 (RFC 9000 §8.1 은 연결별이다)",
        (not conn_bad) and n_conn > 0,
        "위반 %s / 연결 %d 개 검사, 최악 여유 %s B"
        % (conn_bad or "없음", n_conn,
           "측정 안 됨" if worst is None else "%+d" % worst))

    l0bad = [(r["arm"], r["two_rtt_rate"]) for r in out["arms"]
             if r["loss"] == 0.0 and r["arm"] != "base"
             and (r["two_rtt_rate"] or 0) > 0]
    l0n = sum(1 for r in out["arms"]
              if r["loss"] == 0.0 and r["arm"] != "base")
    add("12. 무손실에서 pad/parity/combo 가 2-RTT 를 내지 않는다",
        (not l0bad) and l0n > 0,
        "어긋난 팔 %s (검사한 무손실 팔 %d 개)"
        % (l0bad or "없음", l0n))

    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    print("saved:", B.save("p14_dominance.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
