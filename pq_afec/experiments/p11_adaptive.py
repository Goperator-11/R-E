# -*- coding: utf-8 -*-
"""P11 - 폐루프가 정말 최선을 고르는가. 후회(regret)로 잰다.

폐루프를 닫았다는 말은 두 가지를 뜻해야 한다.

  1. 사람이 m 을 안 줘도 돈다              (배선)
  2. 사람이 골랐을 최선과 비슷한 결과를 낸다  (성능)

1 은 돌려 보면 안다. 2 는 **고정 m 을 전부 돌려 보고 그 중 최선과 비교**해야
안다. 그 차이가 후회다. 1 차 연구에서 쓰던 지표를 그대로 가져왔다.

    후회 = auto 의 평균 HCT - min(고정 m=0, m=1, m=2 의 평균 HCT)

후회가 작으면 폐루프가 제 몫을 한 것이고, 크면 정책이 틀렸거나 관측이
모자란 것이다. 어느 쪽인지는 auto 가 실제로 고른 m 과 최선 m 을 대조하면
드러난다.

콜드스타트 비용도 따로 본다. 처음 몇 연결은 아직 아무것도 모르므로 손해를
볼 수밖에 없다. 전체 구간과 **수렴 후 구간(후반 절반)** 을 나눠 재면 그
비용이 얼마인지 보인다.

Output: experiments/results/p11_adaptive.json
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
N = 200
CACHE = "/tmp/padfec_p11_cache.json"

# (이름, 인증서 크기, c2s 손실%)
CONDS = [
    ("임계아래/무손실", 2955, 0.0),
    ("임계아래/손실2%", 2955, 2.0),
    ("임계아래/손실5%", 2955, 5.0),
    ("임계위/무손실", 9000, 0.0),
    ("임계위/손실2%", 9000, 2.0),
    ("임계위/손실5%", 9000, 5.0),
]


def mean(v):
    return (sum(v) / len(v)) if v else None


def tail_rate(v, thresh):
    return (sum(1 for x in v if x > thresh) / float(len(v))) if v else None


def run_arm(cert, loss, arm, jr):
    """arm: 'm0' | 'm1' | 'm2' | 'auto'"""
    key = "%d|%.1f|%s|n%d" % (cert, loss, arm, N)
    if jr.has(key):
        return jr.get(key)

    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    extra = []
    if arm == "auto":
        # 조건마다 캐시를 비운다 - 콜드스타트부터 정직하게 잰다
        try:
            os.unlink(CACHE)
        except OSError:
            pass
        fec, m = "auto", 1
        extra = ["-cache", CACHE]
    else:
        m = int(arm[1:])
        fec = "off" if m == 0 else "on"

    p, sp = B.start_server(cert, fec=("on" if fec != "off" else "off"))
    rows, cs, err = B.run_client(GROUP, N, fec=fec, m=max(m, 1), gap_ms=8,
                                 timeout_s=10, expect_k=K, extra=extra)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    ok = [r["ms"] for r in rows if r.get("ok")]
    half = len(ok) // 2
    rec = {"arm": arm, "cert": cert, "loss": loss,
           "n": len(rows), "ok": len(ok),
           "mean": mean(ok), "mean_late": mean(ok[half:]),
           "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
           "tail": tail_rate(ok, 1.5 * RTT_MS),
           "tail_late": tail_rate(ok[half:], 1.5 * RTT_MS),
           "m_used": [r.get("m_used") for r in rows],
           "srv_recovered": ss.get("recovered"),
           "srv_crc_fail": ss.get("recover_crc_fail"),
           "err": err}
    if len(rows) == N and (ss.get("recover_crc_fail") or 0) == 0:
        jr.record(key, rec)
    return rec


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    fp = code_fingerprint(["experiments/p11_adaptive.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/quicbed/policy.go",
                           "experiments/quicbed/pfail_table.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p11_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "n": N, "group": GROUP, "rows": [],
           "regret": [], "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-52s %s" % ("통과" if ok else "실패", name, detail[:76]))
        sys.stdout.flush()

    print("=" * 104)
    print("폐루프(auto) 대 고정 m - 조건마다 n=%d" % N)
    print("=" * 104)
    print("%-18s %-6s %-9s %-9s %-9s %-9s %s"
          % ("조건", "팔", "평균", "수렴후평균", "꼬리", "복구", "고른 m"))

    for name, cert, loss in CONDS:
        arms = {}
        for arm in ("m0", "m1", "m2", "auto"):
            r = run_arm(cert, loss, arm, jr)
            arms[arm] = r
            out["rows"].append(r)
            ms = r["m_used"]
            if arm == "auto":
                from collections import Counter
                mtxt = str(dict(sorted(Counter(ms).items())))
            else:
                mtxt = arm[1:]
            print("%-18s %-6s %-9.2f %-9.2f %-9s %-9s %s"
                  % (name, arm, r["mean"] or -1, r["mean_late"] or -1,
                     ("%.1f%%" % (100 * (r["tail"] or 0))),
                     r["srv_recovered"], mtxt))
            sys.stdout.flush()

        fixed = {a: arms[a]["mean"] for a in ("m0", "m1", "m2")
                 if arms[a]["mean"] is not None}
        if not fixed or arms["auto"]["mean"] is None:
            continue
        best_arm = min(fixed, key=lambda a: fixed[a])
        reg = arms["auto"]["mean"] - fixed[best_arm]
        fixed_late = {a: arms[a]["mean_late"] for a in ("m0", "m1", "m2")
                      if arms[a]["mean_late"] is not None}
        best_late = min(fixed_late, key=lambda a: fixed_late[a])
        reg_late = arms["auto"]["mean_late"] - fixed_late[best_late]
        out["regret"].append({
            "cond": name, "cert": cert, "loss": loss,
            "best_fixed": best_arm, "best_fixed_mean": fixed[best_arm],
            "auto_mean": arms["auto"]["mean"], "regret_ms": reg,
            "best_fixed_late": best_late,
            "auto_mean_late": arms["auto"]["mean_late"],
            "regret_late_ms": reg_late,
            "fixed_means": fixed})
        print("    -> 최선 고정팔 %s (%.2f ms), auto %.2f ms, "
              "후회 %+.2f ms (수렴후 %+.2f ms)"
              % (best_arm, fixed[best_arm], arms["auto"]["mean"], reg,
                 reg_late))
        sys.stdout.flush()

    # ------------------------------------------------------------- 판정
    print()
    print("=" * 104)
    regs = [r["regret_ms"] for r in out["regret"]]
    regs_late = [r["regret_late_ms"] for r in out["regret"]]
    if regs:
        worst = max(regs)
        worst_late = max(regs_late)
        out["worst_regret_ms"] = worst
        out["worst_regret_late_ms"] = worst_late
        add("최악 후회가 5 ms 미만 (전 구간, 콜드스타트 포함)",
            worst < 5.0,
            "최악 %+.2f ms | 조건별 %s"
            % (worst, ["%+.1f" % v for v in regs]))
        add("최악 후회가 2 ms 미만 (수렴 후 구간)",
            worst_late < 2.0,
            "최악 %+.2f ms | 조건별 %s"
            % (worst_late, ["%+.1f" % v for v in regs_late]))

    # auto 가 고른 m 이 최선 고정팔과 일치하는가 (수렴 후)
    agree = 0
    tot = 0
    detail = []
    for r in out["regret"]:
        row = next((x for x in out["rows"]
                    if x["arm"] == "auto" and x["cert"] == r["cert"]
                    and x["loss"] == r["loss"]), None)
        if not row:
            continue
        late = row["m_used"][len(row["m_used"]) // 2:]
        if not late:
            continue
        from collections import Counter
        mode_m = Counter(late).most_common(1)[0][0]
        want = int(r["best_fixed_late"][1:])
        # 🩸 고정팔들의 평균이 사실상 같은 조건에서는 "어느 m 이 최선인가"
        # 자체가 잡음이다. 최선과 차선의 차이가 1 ms 미만이면 일치 여부를
        # 따지지 않는다 - 안 그러면 잡음을 불일치로 세게 된다.
        vals = sorted(r["fixed_means"].values())
        if len(vals) >= 2 and (vals[1] - vals[0]) < 1.0:
            detail.append("%s: 고정팔 차이 %.2fms 라 판정 제외"
                          % (r["cond"], vals[1] - vals[0]))
            continue
        tot += 1
        if mode_m == want:
            agree += 1
        detail.append("%s: auto m=%s / 최선 m=%d" % (r["cond"], mode_m, want))
    if tot:
        add("수렴 후 auto 가 고른 m 이 최선 고정팔과 일치",
            agree == tot, "%d/%d | %s" % (agree, tot, "; ".join(detail)))
        out["agreement"] = [agree, tot]

    crc = sum(r["srv_crc_fail"] or 0 for r in out["rows"])
    add("모든 팔에서 복구 CRC 실패 0", crc == 0, "총 %d 건" % crc)

    npass = sum(1 for c in out["checks"] if c["ok"])
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print("saved:", B.save("p11_adaptive.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
