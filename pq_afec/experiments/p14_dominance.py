# -*- coding: utf-8 -*-
"""P14 - 두 지렛대의 신용은 같은 물건이 아니다 (보조정리 1 정정판 실측).

무엇이 바뀌었나
---------------
명세 §2 보조정리 1 은 원래 이렇게 적혀 있었다.

    "같은 Δ 바이트면 패리티가 δ-패딩을 **지배**한다 - 신용은 같고 복구가
     추가로 붙으므로 어떤 손실률에서도 손해가 아니다."

**2026-08-21 에 이 문장이 반증됐다.** 신용은 "보낸 바이트"가 아니라 **서버
QUIC 스택이 실제로 센 바이트**로 생기는데(§2.6, p13), 두 지렛대는 그 바이트의
도착 상관이 다르다.

    δ 패딩   여분 바이트가 데이터 데이터그램과 **한 몸**이다.
             원본이 도착하면 신용도 반드시 함께 도착한다.
    패리티   여분 바이트가 **별도 데이터그램**이다. 원본이 와도 패리티만
             따로 사라질 수 있고, 그러면 신용이 k·W 로 떨어져 칸이 내려간다.
             게다가 **복구에 성공해도** 서버는 패리티를 버리고 복구본(원본
             크기)을 스택에 넘기므로 신용이 그만큼 줄어든다.

그래서 k=1·m=1 에서 2-RTT 로 떨어지는 경우가 **두 가지**다.
    (1) 패리티가 유실된다                 확률 p
    (2) 원본이 유실되고 패리티로 복구된다  확률 p   <- 옛 모형이 놓친 쪽
합쳐서 약 2p. 옛 모형은 (1) 만 세어 p 로 봤다.

이 단계가 재는 것
-----------------
cert 4,032 (x25519, k=1, 맨몸은 2-RTT) 에서 네 팔을 나란히 돌린다.

    base        δ=0, m=0    아무것도 안 함
    pad         δ=1, m=0    1 바이트로 칸을 산다 (신용은 원자적, 복구 없음)
    parity      δ=0, m=1    패리티로 칸을 산다 (복구 있음, 신용이 유실 가능)
    combo       δ=1, m=1    **둘 다** - 2026-08-21 에 후보 집합에 추가된 가족

`combo` 가 이 단계의 핵심이다. δ=1 이 살아남은 데이터그램의 신용 바닥을
1,281 로 올려 **패리티를 잃어도, 복구를 해도** 칸 4 를 지킨다. 그래서 pad 의
약점(복구 없음 -> PTO)과 parity 의 약점(신용 유실 -> 2-RTT)을 동시에 없앤다.

모형 예측 (RTT 50 ms, 손실 5%, uplink 무제한):

    팔        2-RTT 확률   복구실패     J
    base        95.0%      5.00%    107.54 ms
    pad          0.0%      5.00%     60.04 ms
    parity       9.5%      0.25%     55.25 ms
    combo        0.0%      0.25%     50.50 ms   <- 가장 좋다

⚠️ 옛 검사 `2c`("패리티만 꼬리를 없앤다")는 **삭제했다.** 두 팔의 Δ 가
   1 B 대 1,325 B 로 전혀 다른데 "같은 Δ" 보조정리를 시험한다고 적혀 있었고,
   그 전제는 이 테스트베드에서 **도달 불가능**하다(아래 검사 5 가 그것을
   수로 보인다). 통과할 수 없게 설계된 검사를 남겨 두면 실패의 뜻이 흐려진다.

Output: experiments/results/p14_dominance.json
실행:   unshare -Urnm python3 -u experiments/p14_dominance.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from padfec import policy as POL                 # noqa: E402
from padfec import quantum as Q                  # noqa: E402

RTT_MS = 50.0
GROUP = "x25519"
K = 1
W = 1280
CERT = 4032          # 맨몸 임계(3,340)와 pad 임계(4,58x) 사이
N = 400
LOSSES = (0.0, 5.0)
# netem 에 rate 를 안 거므로 정책에도 '무제한'을 알려 준다 (p16 실측).
UPLINK_MBPS = 0.0

# (이름, δ, m)  - ips = W + δ (δ=0 이면 0 을 줘서 quic-go 기본값을 쓴다)
ARMS = [("base", 0, 0), ("pad", 1, 0), ("parity", 0, 1), ("combo", 1, 1)]


def mean(v):
    return (sum(v) / len(v)) if v else None


def model(delta, m, p):
    """이 팔의 모형 예측. 실측과 나란히 놓으려고 같은 코드에서 뽑는다."""
    # 🩸 2026-08-25 - C 가 `1146` 리터럴이었다. 이 파일이 재는 그룹은
    #    x25519 이고 실측 C 는 270 이다. **확인 결과 여기서는 결과가
    #    한 조합도 안 바뀐다**(k_floor 를 따로 주고 natural_k 가 양쪽 다
    #    1 이라서) - 결과 오류가 아니라 표류 위생 문제다. 그래도 지운다:
    #    p17·p18 에서 같은 리터럴이 실제로 결과를 틀리게 만들었다.
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


def run_arm(name, delta, m, loss):
    fec = "on" if m > 0 else "off"
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    p_, sp = B.start_server(CERT, fec=fec)
    rows, cs, err = B.run_client(GROUP, N, fec=fec, m=max(m, 1),
                                 ips=(W + delta) if delta else 0,
                                 gap_ms=8, timeout_s=10, expect_k=K,
                                 uplink_mbps=UPLINK_MBPS)
    B.stop_server(p_)
    ss = B.read_server_stats(sp)
    ok = [r["ms"] for r in rows if r.get("ok")]
    ff = [(r.get("first_flight_bytes") or 0)
          + (r.get("first_flight_parity_bytes") or 0) for r in rows]
    return {"arm": name, "delta": delta, "m": m, "loss": loss,
            "n": len(rows), "ok": len(ok), "mean": mean(ok),
            "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
            # 2-RTT: 1 왕복은 샀지만 두 배 가까이 걸린 판.
            "two_rtt_rate": (sum(1 for t in ok if 1.5 * RTT_MS < t
                                 <= 3.0 * RTT_MS) / float(len(ok)))
            if ok else None,
            # PTO 가지: 전멸해서 타이머를 문 판 (복구 없는 팔의 꼬리).
            "pto_rate": (sum(1 for t in ok if t > 3.0 * RTT_MS)
                         / float(len(ok))) if ok else None,
            "ff_bytes_med": sorted(ff)[len(ff) // 2] if ff else 0,
            "srv_recovered": ss.get("recovered"),
            "srv_crc_fail": ss.get("recover_crc_fail"),
            "srv_bytes_in": ss.get("bytes_in"),
            "srv_bytes_to_stack": ss.get("bytes_to_stack"),
            # 🩸 2026-08-21 - RFC 9000 §8.1 은 **연결별** 제약이다.
            # 전체 합만 보면 한 연결이 넘고 다른 연결이 덜 쓸 때
            # 상쇄돼 안 보인다. 서버가 이미 연결별로 세고 있다.
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

    # 1. 무손실: base 만 2-RTT, 나머지 셋은 전부 1 왕복을 산다.
    b0 = get("base", 0.0)
    others0 = [get(nm, 0.0) for nm in ("pad", "parity", "combo")]
    ok1 = (b0 and b0["p50"] and all(o and o["p50"] for o in others0)
           and all(b0["p50"] - o["p50"] >= 0.8 * RTT_MS for o in others0))
    add("1. 무손실: 세 팔 전부 맨몸보다 1 왕복 빠르다",
        ok1, "맨몸 %.1f | pad %.1f / parity %.1f / combo %.1f ms"
        % (b0["p50"] if b0 else -1,
           *[o["p50"] if o else -1 for o in others0]))

    # 2. 무손실: 신용은 셋이 같다(p50 차 2 ms 미만). 여기까지는 옛 보조정리도 참이다.
    p50s = [o["p50"] for o in others0 if o and o["p50"]]
    add("2. 무손실: 세 팔의 p50 차가 2 ms 미만 (신용 동등)",
        len(p50s) == 3 and (max(p50s) - min(p50s)) < 2.0,
        "폭 %.2f ms (%s)" % ((max(p50s) - min(p50s)) if len(p50s) == 3 else -1,
                             ["%.2f" % v for v in p50s]))

    # 3. 손실: **정정된 신용 회계**가 맞는가. parity 의 2-RTT 는 p 가 아니라 2p 다.
    #    (1) 패리티 유실  (2) 원본 유실 -> 복구본이 패리티보다 작아 칸 하락
    par5 = get("parity", 5.0)
    mo_par = out["model"]["parity@0.05"]
    ok3 = (par5 and par5["two_rtt_rate"] is not None
           and abs(par5["two_rtt_rate"] - mo_par["p_two_rtt"]) < 0.04)
    add("3. 손실 5%: parity 의 2-RTT 율이 정정 모형(약 2p)과 맞는다",
        ok3, "실측 %.1f%% vs 모형 %.1f%% (옛 회계는 %.1f%% 였다)"
        % (100 * (par5["two_rtt_rate"] or 0) if par5 else -1,
           100 * mo_par["p_two_rtt"], 100 * 0.05))

    # 4. 손실: pad 는 신용을 안 잃지만(2-RTT ~ 0) 복구가 없어 PTO 꼬리를 문다.
    pad5 = get("pad", 5.0)
    ok4 = (pad5 and (pad5["two_rtt_rate"] or 0) < 0.02
           and (pad5["srv_recovered"] or 0) == 0)
    add("4. 손실 5%: pad 는 신용을 안 잃는다(2-RTT<2%) - 대신 복구 0",
        ok4, "2-RTT %.1f%% / PTO %.1f%% / 복구 %s"
        % (100 * (pad5["two_rtt_rate"] or 0) if pad5 else -1,
           100 * (pad5["pto_rate"] or 0) if pad5 else -1,
           pad5["srv_recovered"] if pad5 else "-"))

    # 5. [핵심] combo 는 둘 다 가진다: 신용도 안 잃고(2-RTT ~ 0) 복구도 한다.
    com5 = get("combo", 5.0)
    ok5 = (com5 and (com5["two_rtt_rate"] or 0) < 0.02
           and (com5["srv_recovered"] or 0) > 0)
    add("5. [핵심] 손실 5%: combo(δ=1·m=1) 는 2-RTT<2% 이면서 복구도 한다",
        ok5, "2-RTT %.1f%% / 복구 %s (parity 는 2-RTT %.1f%%, "
             "pad 는 복구 0)"
        % (100 * (com5["two_rtt_rate"] or 0) if com5 else -1,
           com5["srv_recovered"] if com5 else "-",
           100 * (par5["two_rtt_rate"] or 0) if par5 else -1))

    # 6. combo 가 네 팔 중 평균이 가장 낮다 - 결합 후보를 넣은 이유 그 자체다.
    m5 = {nm: (get(nm, 5.0)["mean"] if get(nm, 5.0) else None)
          for nm, _, _ in ARMS}
    have = {k_: v for k_, v in m5.items() if v is not None}
    ok6 = have and min(have, key=lambda a: have[a]) == "combo"
    add("6. 손실 5%: combo 의 평균 HCT 가 네 팔 중 최저",
        ok6, " / ".join("%s %.2f" % (k_, v) for k_, v in have.items()))

    # 7. [부정] 옛 보조정리의 전제("같은 Δ")는 이 테스트베드에서 도달 불가능하다.
    #    k=1 에서 pad 로 낼 수 있는 최대 Δ 와 패리티 최소 Δ 가 겹치지 않는다.
    max_pad = K * (POL.QUICGO_MAX_IPS - W)
    min_par = POL.parity_datagram_bytes(W, K)
    add("7. [부정] 옛 보조정리의 전제 '같은 Δ' 는 도달 불가능하다",
        max_pad < min_par,
        "pad 최대 Δ %d B (ips 상한 %d) < 패리티 최소 Δ %d B"
        % (max_pad, POL.QUICGO_MAX_IPS, min_par))

    # 8. 부호기 건전성 + 회계 불변식.
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

    # 11. **연결별** 회계 불변식 (검사 9 의 전체 합은 상쇄를 못 본다).
    #     비어 있으면 통과하는 검사가 되지 않도록 연결 수도 함께 본다.
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

    # 12. 무손실에서 FEC/패딩 팔은 2-RTT 를 내지 않아야 한다.
    #
    # 🩸 2026-08-21 - 이 검사가 없어서 **모형과 실측이 어긋난 자리가
    #    각주로만 남아 있었다.** 무손실이면 소거가 없으므로 모형은
    #    세 팔 전부 2-RTT 0 을 예측한다. 그런데 실측은
    #        pad 0/400 · combo 0/400 · **parity 2/400 (0.50%)**
    #    이다. 패리티만 어긋난다 - 패리티 신용이 서버 결정 시점에
    #    안 잡히는 경우가 드물게 있다는 뜻일 수 있다(p13 검사 5).
    #    맨몸(base)은 설계상 2-RTT 이므로 뺀다.
    #    설명될 때까지 **실패로 둔다** - 기준을 완화하지 않는다.
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
