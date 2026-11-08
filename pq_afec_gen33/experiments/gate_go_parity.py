from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from padfec import capacity, policy

RESULTS = os.path.join(HERE, "results")
OUT = os.path.join(RESULTS, "gate_go_parity.json")

INTERP_TOL_MS = 0.1

J_DIFF_TOL_MS = float(__import__("os").environ.get("PADFEC_GATE_JTOL")
                      or INTERP_TOL_MS)

H = capacity.DEFAULT_H


QUICBED = os.path.join(HERE, "quicbed")


def go_src_fingerprint():
    names = sorted([n for n in os.listdir(QUICBED) if n.endswith(".go")]
                   + ["build.sh", "go.mod", "go.sum"])
    h = hashlib.sha256()
    for n in names:
        with open(os.path.join(QUICBED, n), "rb") as f:
            inner = hashlib.sha256(f.read()).hexdigest()
        h.update(("%s %s\n" % (n, inner)).encode())
    return h.hexdigest()


def built_fingerprint(win):
    if win:
        r = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc",
             'cat "$HOME/quicbed/bin/qamp.srcsha" 2>/dev/null'],
            capture_output=True, text=True, timeout=60)
        got = r.stdout.strip()
        return got or None
    import padbed as B
    p = B.require_bin() + ".srcsha"
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read().strip() or None


def check_build_is_current(win):
    want = go_src_fingerprint()
    got = built_fingerprint(win)
    if got == want:
        return want, got
    print("  FAIL  빌드된 Go 가 저장소 소스와 다르다 (또는 지문이 없다)")
    print("        소스 지문   %s" % want)
    print("        바이너리    %s" % (got or "없음 - 옛 build.sh 로 빌드됐다"))
    print()
    print("        이 상태로 나오는 불일치는 **이식 결함이 아니라 낡은")
    print("        바이너리**다. 모형을 뜯기 전에 먼저 다시 빌드해라:")
    print("            wsl -d Ubuntu -- bash experiments/quicbed/build.sh")
    return want, got


def go_rows(dump=None):
    if dump:
        with open(dump, encoding="utf-8") as f:
            return f.read().splitlines(), "dump:%s" % dump

    if os.name == "nt":
        cmd = ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc",
               '"$HOME/quicbed/bin/qamp" -mode policygrid']
        src = "wsl:~/quicbed/bin/qamp"
    else:
        import padbed as B
        cmd = [B.require_bin(), "-mode", "policygrid"]
        src = cmd[0]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError("qamp -mode policygrid 실패: %s" % r.stderr[-500:])
    return r.stdout.replace("\r", "").splitlines(), src


def c_for_k(k, w):
    per = w - H
    return ((k - 1) * per + 1 + k * per) // 2


def main():
    if "--dump" not in sys.argv:
        from generation import load_config
        if load_config(ROOT)["gen_id"].startswith("v3.3"):
            print("gen-2 parity gate is disabled in gen33; baseline is the frozen binary d98b05d7")
            return 2
    dump = None
    if "--dump" in sys.argv:
        dump = sys.argv[sys.argv.index("--dump") + 1]
    if dump:
        src_sha = built_sha = None
        src_ok = True
        print("(--dump 실행 - 빌드 지문 대조를 건너뛴다)")
    else:
        src_sha, built_sha = check_build_is_current(os.name == "nt")
        src_ok = (src_sha == built_sha)
    lines, src = go_rows(dump)
    lines = [ln for ln in lines if ln.strip()]
    print("Go 격자점 %d 개  (%s)" % (len(lines), src))
    if not lines:
        print("  FAIL  Go 가 아무것도 안 찍었다")
        return 2

    bad, near, picks, deltas = [], [], {}, {}
    jdiff = []
    uplinks = set()
    for ln in lines:
        f = ln.split()
        if len(f) != 13:
            raise RuntimeError(
                "격자 줄의 열이 13 개가 아니다(%d 개): %r\n"
                "  옛 형식(11 열)이면 Go 를 다시 빌드해야 한다 - "
                "up(업링크) 축이 2026-08-21 에 추가됐다." % (len(f), ln))
        k, w, cert = int(f[0]), int(f[1]), int(f[2])
        s0b, rtt, p, l = float(f[3]), float(f[4]), float(f[5]), float(f[6])
        up = float(f[7])
        go = (f[8], int(f[9]), int(f[10]), int(f[11]))
        go_j = float(f[12])
        uplinks.add(up)

        C = c_for_k(k, w)
        assert capacity.natural_k(C, w, H) == k, (C, w, k)
        r = policy.decide_v2(C=C, cert_bytes=cert, rtt_ms=rtt, p=p, burst=l,
                             W=w, h=H, s0_base=s0b,
                             c_pkt=policy.C_PKT_POLICY_DEFAULT,
                             max_steps=policy.MAX_STEPS_DEFAULT,
                             m_max=policy.M_MAX_DEFAULT,
                             max_ips=policy.QUICGO_MAX_IPS,
                             uplink_mbps=up)
        c = r["choice"]
        py = (c["mode"], c["delta_per_dgram"], c["m"], c["W_eff"])
        _jm = {(x["mode"], x["delta_per_dgram"], x["m"], x["W_eff"]):
               x["j_ms"] for x in r["candidates"]}
        if go in _jm:
            jdiff.append((abs(go_j - _jm[go]),
                          {"k": k, "cert": cert, "rtt": rtt, "p": p,
                           "burst": l, "up": up, "go_j": go_j,
                           "py_j": _jm[go]}))
        if py != go:
            jmap = {(x["mode"], x["delta_per_dgram"], x["m"], x["W_eff"]):
                    x["j_ms"] for x in r["candidates"]}
            reg = None
            if go in jmap and py in jmap:
                reg = jmap[go] - jmap[py]
            rec = {"k": k, "w": w, "cert": cert, "s0_base": s0b,
                   "rtt_ms": rtt, "p": p, "burst": l, "uplink_mbps": up,
                   "go": list(go), "py": list(py),
                   "j_regret_ms": reg}
            if reg is not None and abs(reg) <= INTERP_TOL_MS:
                near.append(rec)
            else:
                bad.append(rec)
        picks[go[0]] = picks.get(go[0], 0) + 1
        if go[0] == "pad":
            deltas[go[1]] = deltas.get(go[1], 0) + 1

    worst_interp = max([abs(x["j_regret_ms"] or 0.0) for x in near], default=0.0)
    jdiff.sort(key=lambda t: t[0], reverse=True)
    worst_j = jdiff[0][0] if jdiff else 0.0
    j_over = [x for x in jdiff if x[0] > J_DIFF_TOL_MS]
    ok = (not bad) and (not j_over)
    print()
    print("=== Python decide_v2 vs Go decide - (mode, delta, m, ips) 전부 ===")
    print(("  OK   " if ok else "  FAIL ")
          + "%d 격자점 중 진짜 불일치 %d 건" % (len(lines), len(bad)))
    print("       표 보간 근소차 %d 건 - Python J 기준 최대 대가 %.6f ms "
          "(한도 %.3f ms)" % (len(near), worst_interp, INTERP_TOL_MS))
    print("       결정이 같은 점의 J 어긋남 - 최대 %.6f ms "
          "(한도 %.3f), 한도 초과 %d 건 / %d 점"
          % (worst_j, J_DIFF_TOL_MS, len(j_over), len(jdiff)))
    for _d, _w in j_over[:3]:
        print("         k=%d cert=%d rtt=%g p=%g L=%g up=%g | Go J %.6f "
              "vs Py J %.6f | 차 %.6f ms"
              % (_w["k"], _w["cert"], _w["rtt"], _w["p"], _w["burst"],
                 _w["up"], _w["go_j"], _w["py_j"], _d))
    if near[:3]:
        for x in near[:3]:
            print("         p=%g rtt=%g up=%g | Go %s | Py %s | 대가 %.6f ms"
                  % (x["p"], x["rtt_ms"], x["uplink_mbps"], x["go"], x["py"],
                     x["j_regret_ms"]))
    for x in bad[:8]:
        print("     k=%d w=%d cert=%d s0b=%g rtt=%g p=%g L=%g up=%g | "
              "Go %s | Py %s"
              % (x["k"], x["w"], x["cert"], x["s0_base"], x["rtt_ms"],
                 x["p"], x["burst"], x["uplink_mbps"], x["go"], x["py"]))

    print()
    print("=== 지렛대가 실제로 선택되는가 (v2 이식의 목적) ===")
    for mode, n in sorted(picks.items(), key=lambda t: -t[1]):
        print("   %-8s %5d 건 (%.1f%%)" % (mode, n, 100.0 * n / len(lines)))
    if deltas:
        print("   pad 을 고른 판의 delta: %s"
              % sorted(deltas.items())[:8])
        print("   그중 delta=1 (1 바이트로 칸 올리기): %d 건"
              % deltas.get(1, 0))
    pad_ok = deltas.get(1, 0) > 0
    if not pad_ok:
        print("  FAIL  δ=1 을 고르는 판이 하나도 없다 - 헤드라인이 "
              "정책의 손에서 실현되지 않는다")

    up_ok = len(uplinks) >= 2
    if not up_ok:
        print("  FAIL  업링크 축이 %s 하나뿐이다 - 이 항의 갈라짐을 "
              "대조하지 못한다" % sorted(uplinks))
    combo_ok = picks.get("combo", 0) > 0
    if not combo_ok:
        print("  FAIL  combo(결합 δ·m) 후보가 한 번도 안 뽑혔다 - "
              "2026-08-21 이식이 격자에서 대조되지 않는다")

    if dump:
        print()
        print("(--dump 실행이라 %s 는 안 건드린다)" % os.path.basename(OUT))
    else:
        os.makedirs(RESULTS, exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"grid_points": len(lines), "source": src,
                       "worst_j_diff_ms": worst_j,
                       "j_diff_over_tol": len(j_over),
                       "j_diff_tol_ms": J_DIFF_TOL_MS,
                       "j_diff_points": len(jdiff),
                       "go_src_sha256": src_sha,
                       "go_built_sha256": built_sha,
                       "go_build_current": bool(src_ok),
                       "mismatch": len(bad), "mismatches": bad[:50],
                       "interp_near_misses": len(near),
                       "interp_worst_j_regret_ms": worst_interp,
                       "interp_tol_ms": INTERP_TOL_MS,
                       "picks": picks, "pad_deltas": deltas,
                       "uplinks": sorted(uplinks),
                       "ok": bool(ok and pad_ok and up_ok and combo_ok
                                  and src_ok)}, f,
                      ensure_ascii=False, indent=1)
        print()
        print("wrote %s" % OUT)
    return 0 if (ok and pad_ok and up_ok and combo_ok and src_ok) else 1


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass
    sys.exit(main())
