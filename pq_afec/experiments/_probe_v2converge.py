# -*- coding: utf-8 -*-
"""손실률 추정이 수렴하면 정책이 pad(δ) 로 넘어가는가.

`_probe_v2policy.py` 가 5/6 으로 끝났다. 정책은 왕복 하나를 스스로 벌었지만
그 방법이 **δ=1 바이트가 아니라 패리티 2 개(2,636 B)** 였다. 값이 2,600 배
다른데 왕복 수만 보면 구별이 안 된다.

정책을 탓하기 전에 입력을 봐야 한다. p=0.038 이면 **패리티가 실제로 옳다** -
pad 는 복구를 주지 않으므로 손실 한 번에 PTO 201 ms 를 문다. 문제는 결정
규칙이 아니라 **추정이 아직 참값(0)에서 멀다**는 것이다.

Jeffreys 사후평균 (손실+0.5)/(관측+1) 은 무손실이면 관측 수에 반비례해
내려간다. 감쇠 0.99 때문에 유효기억이 ~100 이라 하한은 0.5/101 ≈ 0.005 다.
그 근처에 닿으면 pad 가 이겨야 한다. 이 시험이 그것을 확인한다.

🩸 여기서 관측이 쌓이는 속도가 곧 **탐색 정책**의 성질이다. 손실은 m=0 인
   연결에서만 편향 없이 보이는데, m 만 있던 시절엔 m=0 후보가 맨몸 하나뿐이라
   임계 위에서 탐색 한 번이 곧 2-RTT 였다. 그 비용 때문에 주기가 늘어나
   400 연결에 무편향 관측이 3 회뿐이었고 p 가 사전값(0.126)에 정체했다.
   지금은 **가장 싼 m=0 후보**(보통 pad)로 탐색하므로 주기가 훨씬 짧다.

실행 (캐시를 비우고 처음부터)
    unshare -Urnm python3 experiments/_probe_v2converge.py
실행 (앞 실행이 배운 것을 이어받아 더 돌린다)
    unshare -Urnm python3 experiments/_probe_v2converge.py --keep-cache --rounds 8
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import padbed                       # noqa: E402
from padfec import policy, capacity  # noqa: E402

RTT_MS = 50.0
CERT = 4032
IPS = 1280
N = 400
CACHE = "/tmp/padfec/v2conv.json"
HERE = os.path.dirname(os.path.abspath(__file__))
C_HELLO = 259        # x25519 ClientHello 바이트
H = 51
# policy.go destCache.observe 의 감쇠. 두 계수를 매 관측마다 이만큼 줄이므로
# 관측 수의 고정점이 1/(1-decay) 다. **여기 값을 바꾸면 policy.go 도 바꿔야
# 한다** - 지금은 Go 쪽이 정본이고 여기서는 읽기만 한다.
OBS_DECAY = 0.99


def flip_threshold(s0_base):
    """pad(δ) 가 parity 를 이기기 시작하는 손실률 상한을 이분탐색으로 찾는다."""
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
    """Jeffreys 사후평균 + 감쇠가 무손실 경로에서 도달하는 하한 p.

    관측 수는 `obs = decay*obs + 1` 의 고정점 1/(1-decay) 로 수렴하고,
    p_conn = (손실 0 + 0.5)/(obs + 1) 이 그때 가장 작아진다.
    연결당 확률을 데이터그램당으로 되돌리는 변환은 policy.go decide 와 같다.
    """
    obs = 1.0 / (1.0 - OBS_DECAY)
    p_conn = 0.5 / (obs + 1.0)
    return 1.0 - (1.0 - p_conn) ** (1.0 / max(1, k))


def main(argv):
    rounds = 6
    if "--rounds" in argv:
        rounds = int(argv[argv.index("--rounds") + 1])
    keep = "--keep-cache" in argv
    # 이어 돌린 결과를 처음부터 돌린 결과 위에 덮어쓰면 안 된다 - 둘은
    # 다른 실험이다(전자는 캐시가 이미 배운 상태에서 출발한다).
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
    # 탐색이 20 연결마다 한 번이므로 pad 판이 그 정도면 "탐색만" 이다.
    # 넘어갔다고 말하려면 **평상시 선택**이 pad 여야 한다 - 과반으로 본다.
    flipped = last["ips_used"].get(1281, 0) > N // 2
    print("  p 추정: %s -> %s" % (first["p_est"], last["p_est"]))
    print("  마지막 라운드에서 ips=1281 을 쓴 비율: %.1f%%"
          % (100.0 * last["ips_used"].get(1281, 0) / N))
    print("  p50: %s -> %s ms" % (first["p50"], last["p50"]))
    print("  마지막 판단: %s" % last["why_last"])
    print("  [%s] 정책이 pad(δ=1) 로 넘어갔다" % ("OK " if flipped else "아직"))
    out["flipped"] = flipped

    # 🩸 "아직" 과 "영영" 을 구별한다. 측정만 보면 둘이 똑같이 생겼는데
    # 처방이 정반대다 - 전자는 더 돌리면 되고, 후자는 추정기나 탐색 주기를
    # 고쳐야 한다. 그래서 문턱(모형)과 하한(추정기)을 같이 찍는다.
    k = capacity.natural_k(C_HELLO, IPS, H)
    s0b = policy.S0_BASE_X25519   # p13 갱신: 380.0 (c=40 앵커 유도)
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
