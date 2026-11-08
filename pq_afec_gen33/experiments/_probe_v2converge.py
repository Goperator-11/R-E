import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import padbed
from padfec import policy, capacity

RTT_MS = 50.0
CERT = 4032
IPS = 1280
N = 400
CACHE = "/tmp/padfec/v2conv.json"
HERE = os.path.dirname(os.path.abspath(__file__))
C_HELLO = 259
H = 51
OBS_DECAY = 0.99


def flip_threshold(s0_base):
    lo, hi = 0.0, 0.05
    for _ in range(60):
        mid = (lo + hi) / 2.0
        r = policy.decide_v2(C=C_HELLO, cert_bytes=CERT, rtt_ms=RTT_MS, p=mid,
                             burst=1.0, W=IPS, h=H, s0_base=s0_base,
                             c_pkt=policy.C_PKT_POLICY_DEFAULT,
                             max_steps=policy.MAX_STEPS_DEFAULT, m_max=2,
                             max_ips=policy.QUICGO_MAX_IPS)
        if r["choice"]["mode"] == "pad":
            lo = mid
        else:
            hi = mid
    return lo


def estimator_floor(k):
    obs = 1.0 / (1.0 - OBS_DECAY)
    p_conn = 0.5 / (obs + 1.0)
    return 1.0 - (1.0 - p_conn) ** (1.0 / max(1, k))


def main(argv):
    rounds = 6
    if "--rounds" in argv:
        rounds = int(argv[argv.index("--rounds") + 1])
    keep = "--keep-cache" in argv
    out_path = os.path.join(HERE, "results", "probe_v2converge%s.json"
                            % ("2" if keep else ""))

    padbed.harden()
    padbed.require_root()
    padbed.require_bin()
    padbed.setup(mtu=1500)
    padbed.set_netem(RTT_MS / 2.0, 0.0, 0.0)
    if not keep:
        try:
            os.unlink(CACHE)
        except OSError:
            pass

    out = {"rtt_ms": RTT_MS, "cert": CERT, "n_per_round": N,
           "kept_cache": keep, "rounds": []}
    srv = None
    try:
        srv, _ = padbed.start_server(CERT, fec="fec")
        for rnd in range(1, rounds + 1):
            rows, _st, err = padbed.run_client(
                "x25519", N, fec="auto", ips=IPS, gap_ms=15, timeout_s=12,
                warmup=0, extra=["-cache", CACHE, "-probe-every", "20"])
            s = padbed.summarize(rows, rtt_ms=RTT_MS)
            used = Counter(r.get("ips_used") for r in rows)
            musd = Counter(r.get("m_used") for r in rows)
            why = rows[-1].get("m_why", "") if rows else ""
            mp = re.search(r"p=([0-9.]+)", why)
            p_est = float(mp.group(1)) if mp else None
            mode = why.split()[0] if why else "?"
            rec = {"round": rnd, "p_est": p_est, "mode_last": mode,
                   "why_last": why, "err": err,
                   "p50": s.get("p50"), "two_rtt": s.get("two_rtt_rate"),
                   "ips_used": dict(used), "m_used": dict(musd)}
            out["rounds"].append(rec)
            print("라운드 %d | p추정=%-8s 마지막선택=%-7s p50=%-8s | ips=%s m=%s"
                  % (rnd, p_est, mode, rec["p50"], dict(used), dict(musd)),
                  flush=True)
    finally:
        padbed.stop_server(srv)

    print()
    print("=== 판정 ===")
    first, last = out["rounds"][0], out["rounds"][-1]
    flipped = last["ips_used"].get(1281, 0) > N // 2
    print("  p 추정: %s -> %s" % (first["p_est"], last["p_est"]))
    print("  마지막 라운드에서 ips=1281 을 쓴 비율: %.1f%%"
          % (100.0 * last["ips_used"].get(1281, 0) / N))
    print("  p50: %s -> %s ms" % (first["p50"], last["p50"]))
    print("  마지막 판단: %s" % last["why_last"])
    print("  [%s] 정책이 pad(δ=1) 로 넘어갔다" % ("OK " if flipped else "아직"))
    out["flipped"] = flipped

    k = capacity.natural_k(C_HELLO, IPS, H)
    s0b = policy.S0_BASE_X25519
    thr = flip_threshold(s0b)
    floor = estimator_floor(k)
    out["flip_threshold_p"] = thr
    out["estimator_floor_p"] = floor
    out["margin"] = (thr / floor) if floor > 0 else None
    print()
    print("  === 닿을 수 있는 목표인가 ===")
    print("  pad 가 이기는 손실률 상한 : p < %.5f" % thr)
    print("  추정기가 도달하는 하한    : p = %.5f  (Jeffreys + 감쇠 %.2f)"
          % (floor, OBS_DECAY))
    if floor < thr:
        print("  여유 %.2f 배 - 도달 가능. 안 넘어갔다면 라운드가 모자란 것이다."
              % (thr / floor))
    else:
        print("  **하한이 문턱보다 높다 - 라운드를 늘려도 영영 안 넘어간다.**")
        print("  고칠 곳은 정책이 아니라 추정기(감쇠)나 탐색 주기다.")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
