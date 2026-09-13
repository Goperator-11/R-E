# -*- coding: utf-8 -*-
"""P15 - v2 정책(δ·m 결합)의 후회. p11 과 같은 자로 잰다 (loop2 단계 p15).

왜 따로 재나
------------
p11 은 m 만 쓰던 시절의 자다 - 고정팔이 {m0, m1, m2} 뿐이라 δ 지렛대가
들어간 뒤의 정책이 **무엇을 상대로 얼마나 잃는지** 재는 자가 없었다.
여기서는 δ 가 실제로 값을 내는 자리(x25519, 임계 사이 인증서)에서
고정팔에 **pad(δ=1) 팔을 반드시 포함**해 잰다 - m 고정팔만 두면 "패리티
2,636 B 로도 같은 왕복을 산다"에 가려 v2 의 값(1 바이트)이 안 보인다.

설계
----
x25519(k=1) · RTT 50 ms. 인증서 두 자리 x 손실 세 조건:
    2955  임계(3340) 아래 - δ 는 쓸모없고 복구만 값을 낸다
    4032  임계 사이(3340 < 4032 < 4580) - δ=1 이 왕복 하나를 산다 (헤드라인)

고정팔: m0(맨몸) / m1 / m2 / pad(ips 1281, m=0).  각 N 연결.
auto:   빈 캐시에서 라운드(400연결)를 캐시를 이어받으며 반복 - 무손실
        조건은 손실률 추정이 pad 문턱(≈0.007)까지 내려오는 데 ~7 라운드가
        걸린다(`_probe_v2converge.py` 실측). 후회는 **마지막 라운드**(수렴
        후)의 평균으로 잰다 - p11 의 "수렴 후 절반"과 같은 취지다.

통과 기준 (loop2 에 적힌 것): 수렴 후 최악 후회 < 2 ms. p11 과 같은 자이며
여기서 완화하지 않는다.

Output: experiments/results/p15_v2policy.json
실행:   unshare -Urnm python3 -u experiments/p15_v2policy.py
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
import blockstat as BST                          # noqa: E402
from padfec import policy as POL                 # noqa: E402

RTT_MS = 50.0
GROUP = "x25519"
K = 1
# 🩸 2026-08-21 - p11 과 같은 처방(--precise). 고정팔 표본은 auto 한
#    라운드와 같은 크기여야 짝이 맞으므로 라운드 크기와 함께 움직인다.
N_DEFAULT = 400               # 고정팔 표본 = auto 한 라운드와 같은 크기
N_PRECISE = 1600
N = int(os.environ.get("PADFEC_P15_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
CACHE = "/tmp/padfec_p15_cache.json"

# (이름, cert, 손실%) - cert 4032 는 명세 4-4 의 Tranco p50 이고
# _probe_v2policy / _probe_v2converge 와 같은 자리다.
CONDS = [
    ("임계아래/무손실", 2955, 0.0),
    ("임계아래/손실2%", 2955, 2.0),
    ("임계아래/손실5%", 2955, 5.0),
    ("임계사이/무손실", 4032, 0.0),
    ("임계사이/손실2%", 4032, 2.0),
    ("임계사이/손실5%", 4032, 5.0),
]

# 🩸 2026-08-21 - 이 실행의 실제 업링크. netem 에 rate 를 안 걸므로 0 이 사실이다.
UPLINK_MBPS = 0.0

# 무손실 조건은 추정기가 하한(0.005)까지 내려와야 pad 로 넘어간다 - 7~8 라운드.
#
# 🩸 2026-08-21 - 손실 조건은 3 라운드였다. **수렴을 시험한 게 아니라 선언한
#    것이었다.** 2026-08-20 실행의 임계사이/손실2% 를 보면 p 추정이
#    0.0377 -> 0.0171 -> 0.0118 로 **여전히 움직이는 중**에 3 라운드에서 끊고
#    그 값을 "수렴 후 후회"라고 불렀다. 그 조건이 곧 헤드라인 실패(+3.08 ms)였다.
#    라운드를 무손실과 같게 8 로 맞추고, **수렴했는지를 검사로 확인한다**
#    (아래 "수렴 판정"). 안 했으면 실패로 드러난다.
# 🩸 2026-09-07 - 8 -> 10. 고정팔 넷과 auto 를 교대로 도는 라틴 회전이 닫히려면
#    라운드 수가 팔 수(5)의 배수여야 각 팔이 각 자리를 같은 횟수로 겪는다.
#    수렴 검사(마지막 세 라운드의 최빈 선택)는 그대로다.
ROUNDS_CLEAN = 10
ROUNDS_LOSSY = 10

# 고정팔: (이름, fec, m, ips)
FIXED = [("m0", "off", 0, 0), ("m1", "on", 1, 0), ("m2", "on", 2, 0),
         ("pad", "off", 0, 1281)]


def mean(v):
    return (sum(v) / len(v)) if v else None


def _delta_only_crossover(cert=4032, rtt_ms=RTT_MS):
    """pad(δ=1) **단독**이 이기는 손실률의 상한. 이분탐색.

    이 수가 추정기의 하한(Jeffreys, ObsCount 고정점 100 -> 4.95e-3)보다
    작으면 **폐루프는 δ 단독을 영영 고를 수 없다** - 그건 결함이 아니라
    인식론적 한계다. 어떤 적응 추정기도 100 표본으로 'p < 5e-5' 를
    증명할 수 없다."""
    lo, hi = 0.0, 0.05
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        d = POL.decide_v2(C=267, cert_bytes=cert, rtt_ms=rtt_ms, p=mid,
                          burst=1.0, s0=None,
                          s0_base=POL.S0_BASE_X25519,
                          c_pkt=POL.C_PKT_POLICY_DEFAULT,
                          uplink_mbps=UPLINK_MBPS)
        if d["choice"]["mode"] == "pad":
            lo = mid
        else:
            hi = mid
    return lo


def added_bytes(row):
    """이 시행이 기준선(k*1280) 대비 실제로 더 보낸 첫 비행 바이트."""
    ff = (row.get("first_flight_bytes") or 0) + (
        row.get("first_flight_parity_bytes") or 0)
    return max(0, ff - K * 1280)


# 🩸 2026-09-07 - **고정팔과 auto 라운드를 교대로 잰다.** 그전에는 조건마다
#    m0 -> m1 -> m2 -> pad 를 팔당 N 판씩 통째로 돌린 뒤 auto 를 8 라운드
#    돌렸다. p11 과 같은 병이다 - 기계의 단조 표류가 팔 이름에 얹혀 후회로
#    계상된다(인계 §4b-4b 가 p15 의 보고 반폭을 1.25 배 과소평가로 판정했다).
#    설계: 조건마다 서버 하나(fec=on), 라운드 r 마다 [auto 라운드 r(N 판),
#    m0·m1·m2·pad 각 N/ROUNDS 판] 을 r 만큼 회전한 순서로. ROUNDS=10 이면
#    다섯 팔이 각 자리를 정확히 두 번 겪는다(균형). auto 의 캐시는 조건 시작에
#    한 번만 비우고 라운드를 넘어 이어진다(수렴을 잰다). 고정팔 표본은 그대로
#    N 이고 auto 는 10N 이다(옛 8N). 표준오차는 배치평균(blockstat.batch_se).
#    저널 단위는 조건이다.
ROUNDS_ORDER = ["auto"] + [f[0] for f in FIXED]


def run_condition(cert, loss, rounds, jr):
    """조건 하나 - 고정팔 넷과 auto 라운드를 교대로. ({팔: rec}, auto rec)."""
    key = "latin|%d|%.1f|r%d|n%d" % (cert, loss, rounds, N)
    if jr.has(key):
        v = jr.get(key)
        return v["fixed"], v["auto"]
    n_blk = N // rounds
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    try:
        os.unlink(CACHE)
    except OSError:
        pass
    fx_rows = {f[0]: [] for f in FIXED}
    fx_blocks = {f[0]: [] for f in FIXED}
    fx_err = {f[0]: "" for f in FIXED}
    fixed_by = {f[0]: f for f in FIXED}
    hist = []
    p, sp = B.start_server(cert, fec="on")
    try:
        for rnd in range(1, rounds + 1):
            r = (rnd - 1) % len(ROUNDS_ORDER)
            order = ROUNDS_ORDER[r:] + ROUNDS_ORDER[:r]
            for pos, aname in enumerate(order):
                if aname == "auto":
                    rows, cs, err = B.run_client(
                        GROUP, N, fec="auto", m=1, gap_ms=8, timeout_s=10,
                        expect_k=K,
                        extra=["-cache", CACHE, "-probe-every", "20"],
                        uplink_mbps=UPLINK_MBPS)
                    ok = [x["ms"] for x in rows if x.get("ok")]
                    # 2026-08-21 - 마지막 행만 보면 안 된다. 그 판이 **탐색**
                    # 이면 m_why 에 p= 가 없다. 뒤에서부터 p= 를 담은 행을 찾는다.
                    why = ""
                    mp = None
                    for _r in reversed(rows):
                        _w = _r.get("m_why", "") or ""
                        _m = re.search(r"p=([0-9.]+)", _w)
                        if _m:
                            why, mp = _w, _m
                            break
                    if not why and rows:
                        why = rows[-1].get("m_why", "") or ""
                    hist.append({
                        "round": rnd, "pos": pos, "n": len(rows),
                        "mean": mean(ok),
                        "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
                        "tail": (sum(1 for x in ok if x > 1.5 * RTT_MS)
                                 / float(len(ok)) if ok else None),
                        "ips_used": dict(Counter(x.get("ips_used")
                                                 for x in rows)),
                        "m_used": dict(Counter(x.get("m_used") for x in rows)),
                        "added_bytes_mean": mean([added_bytes(x)
                                                  for x in rows]),
                        "p_est": float(mp.group(1)) if mp else None,
                        "ms": ok,
                        "ms_rows": [x["ms"] if x.get("ok") else None
                                    for x in rows],
                        "probe_rows": [(x.get("m_why") or "")
                                       .startswith("탐색") for x in rows],
                        "why_last": why, "err": err})
                    continue
                _n, fec, m, ips = fixed_by[aname]
                rows, cs, err = B.run_client(
                    GROUP, n_blk, fec=fec, m=max(m, 1), ips=ips,
                    gap_ms=8, timeout_s=10, expect_k=K,
                    uplink_mbps=UPLINK_MBPS)
                if err:
                    fx_err[aname] = err
                fx_rows[aname].extend(rows)
                ok = [x["ms"] for x in rows if x.get("ok")]
                fx_blocks[aname].append({"round": rnd, "pos": pos,
                                         "n": len(rows), "ok": len(ok),
                                         "mean": mean(ok), "ms": ok})
            print("   라운드 %2d/%d  auto %.2f  %s"
                  % (rnd, rounds, hist[-1]["mean"] or -1,
                     "  ".join("%s(자리%d) %.2f"
                               % (a, fx_blocks[a][-1]["pos"],
                                  fx_blocks[a][-1]["mean"] or -1)
                               for a in order if a != "auto")), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    fixed = {}
    for aname, fec, m, ips in FIXED:
        rows = fx_rows[aname]
        ok = [x["ms"] for x in rows if x.get("ok")]
        fixed[aname] = {
            "arm": aname, "cert": cert, "loss": loss, "n": len(rows),
            "ok": len(ok), "mean": mean(ok), "p50": B.pctl(ok, 0.5),
            "p95": B.pctl(ok, 0.95),
            "tail": (sum(1 for x in ok if x > 1.5 * RTT_MS) / float(len(ok))
                     if ok else None),
            "added_bytes_mean": mean([added_bytes(x) for x in rows]),
            "blocks": fx_blocks[aname],
            # 서버가 조건당 하나 - 조건 합이다.
            "srv_recovered": ss.get("recovered"),
            "srv_crc_fail": ss.get("recover_crc_fail"),
            "ms": ok,
            "srv_stats_present": bool(ss),
            "err": fx_err[aname]}
    au = {"cert": cert, "loss": loss, "rounds": hist,
          "final": hist[-1] if hist else None,
          "srv_stats_present": bool(ss),
          "srv_crc_fail": ss.get("recover_crc_fail")}
    complete = (all(len(fx_rows[f[0]]) == n_blk * rounds for f in FIXED)
                and hist and all(h["n"] == N for h in hist))
    if complete and bool(ss) and (ss.get("recover_crc_fail") or 0) == 0:
        jr.record(key, {"fixed": fixed, "auto": au})
    return fixed, au


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup(mtu=1500)

    from _journal import Journal, code_fingerprint
    fp = code_fingerprint(["experiments/p15_v2policy.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/quicbed/policy.go",
                           "experiments/quicbed/pfail_table.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p15_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "n": N, "group": GROUP,
           "interleaved": True,
           "rows": [], "auto": [], "regret": [], "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail[:86]),
              flush=True)

    print("=" * 104)
    print("v2 정책(auto) 대 고정 {m0, m1, m2, pad(δ=1)} - 조건마다 고정팔 n=%d, "
          "auto 라운드 n=%d (교대 측정)" % (N, N))
    print("=" * 104)

    for name, cert, loss in CONDS:
        rounds = ROUNDS_CLEAN if loss == 0.0 else ROUNDS_LOSSY
        print("### %s (cert %d, 손실 %g%%) - %d 라운드 교대"
              % (name, cert, loss, rounds), flush=True)
        arms, au = run_condition(cert, loss, rounds, jr)
        for aname, fec, m, ips in FIXED:
            r = arms[aname]
            out["rows"].append(r)
            print("%-16s %-5s 평균 %-8.2f p95 %-8.2f 꼬리 %5.1f%% 복구 %-5s "
                  "추가B %s"
                  % (name, aname, r["mean"] or -1, r["p95"] or -1,
                     100 * (r["tail"] or 0), r["srv_recovered"],
                     round(r["added_bytes_mean"] or 0, 1)), flush=True)
        au["cond"] = name
        out["auto"].append(au)
        fin = au["final"]
        for h in au["rounds"]:
            print("%-16s auto r%d 평균 %-8.2f p추정 %-8s ips %s m %s"
                  % (name, h["round"], h["mean"] or -1, h["p_est"],
                     h["ips_used"], h["m_used"]), flush=True)

        fixed_means = {a: arms[a]["mean"] for a in arms
                       if arms[a]["mean"] is not None}
        if not fixed_means or not fin or fin["mean"] is None:
            # 🩸 2026-08-21 - 조용히 빠지면 헤드라인(max)이 저절로 좋아진다.
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss, "why": "측정 실패"})
            print("    -> !! 측정 실패로 이 조건이 빠졌다: %s" % name,
                  flush=True)
            continue
        # 🩸 2026-09-07 감사 - 헤드라인의 창을 맞춘다. auto 의 마지막 라운드는
        #    조건의 **끝**에 있는데 고정팔 평균을 조건 전체(라운드 1~10)로 잡으면
        #    단조 표류의 절반이 여전히 후회로 들어온다 - 교대 측정으로 고치려던
        #    바로 그것이다. 고정팔도 **뒤 절반 라운드**의 블록만 쓴다(p11 의
        #    rows[half:] 와 같은 뜻). 전 구간 값은 regret_full_ms 로 남긴다.
        def _late_ms(a):
            return [t for b_ in (arms[a].get("blocks") or [])
                    if b_["round"] > rounds // 2 for t in (b_.get("ms") or [])]
        fixed_means_late = {a: mean(_late_ms(a)) for a in fixed_means
                            if _late_ms(a)}
        if not fixed_means_late:
            fixed_means_late = dict(fixed_means)
        best = min(fixed_means_late, key=lambda a: fixed_means_late[a])
        best_full = min(fixed_means, key=lambda a: fixed_means[a])
        reg = fin["mean"] - fixed_means_late[best]
        reg_full = fin["mean"] - fixed_means[best_full]

        # 🩸 2026-08-21 (0-c) - 탐색세 분리 (p11 과 같은 항등식).
        #    마지막 라운드는 전부 수렴 후이므로 라운드 전체로 나눈다.
        _mr = fin.get("ms_rows") or []
        _pr = fin.get("probe_rows") or []
        probe_tax = reg_sel = n_probe_fin = None
        if _mr and len(_mr) == len(_pr):
            _lp = [t for t, f_ in zip(_mr, _pr)
                   if f_ and t is not None]
            _ls = [t for t, f_ in zip(_mr, _pr)
                   if not f_ and t is not None]
            n_probe_fin = len(_lp)
            if _lp and _ls:
                _f = len(_lp) / float(len(_lp) + len(_ls))
                probe_tax = _f * (mean(_lp) - mean(_ls))
                reg_sel = reg - probe_tax

        # 🩸 2026-08-21 승자의 저주 보정 + 신뢰구간. p11 과 같은 처방이다.
        sel, ev = {}, {}
        for a in arms:
            v = arms[a].get("ms") or []
            h = len(v) // 2
            if h >= 5:
                sel[a] = mean(v[:h])
                ev[a] = mean(v[h:])
        reg_hold = None
        if sel and ev:
            bh = min(sel, key=lambda a: sel[a])
            reg_hold = fin["mean"] - ev[bh]

        # 🩸 2026-09-07 - 배치평균 SE (p11·p16 과 같은 자). 인계 §4b-4b 가 이
        #    단계의 보고 반폭을 1.25 배 과소평가로 판정했다.
        _se_methods = []

        def _se(v):
            se, method, kb = BST.batch_se_info(v)
            _se_methods.append((method, kb))
            return se

        # 짝지은 후회 (정보). 교대 측정이라 라운드 r 의 auto 와 같은 라운드의
        # 최선 고정팔 블록을 짝지을 수 있다 - 라운드 간 표류가 상쇄된다.
        # 수렴 후 = 뒤쪽 절반 라운드. 헤드라인(regret_ms)의 정의는 그대로 둔다.
        _late_r = [h for h in au["rounds"] if h["round"] > rounds // 2]
        _bb = {b["round"]: b["mean"] for b in arms[best].get("blocks") or []}
        _pd = [h["mean"] - _bb[h["round"]] for h in _late_r
               if h["mean"] is not None and _bb.get(h["round"]) is not None]
        reg_paired = mean(_pd)
        reg_paired_half = None
        if len(_pd) >= 2:
            _mu = sum(_pd) / len(_pd)
            _var = sum((x - _mu) ** 2 for x in _pd) / (len(_pd) - 1)
            reg_paired_half = BST.t_crit(len(_pd) - 1) * (_var / len(_pd)) ** 0.5

        sa = _se(fin.get("ms") or [])
        sf = _se(_late_ms(best) or arms[best].get("ms") or [])
        _methods = sorted(set(m for m, _k in _se_methods if m))
        se_reg = ((sa ** 2 + sf ** 2) ** 0.5
                  if sa is not None and sf is not None else None)

        # 🆕 수렴 판정. "몇 라운드 돌았으니 수렴했다"가 아니라 **직접 본다**:
        #    마지막 세 라운드의 p 추정이 상대 5% 안에서 안정적이고, 선택
        #    분포(ips·m)가 마지막 두 라운드에 같아야 한다.
        rr = au["rounds"] if au else []
        # 2026-08-21 정정. 처음에는 "p 추정의 표류 < 5% **그리고** 선택
        # 분포가 마지막 두 라운드에 동일" 을 요구했다. **자가 틀렸다.**
        #   - 선택 분포를 글자 그대로 비교하면 **탐색 배치의 지터**만으로도
        #     달라진다(예: {2:387,0:13} vs {2:385,0:15}).
        #   - p 추정은 Jeffreys 사전값 쪽으로 **점근적으로 기어가므로**
        #     행동이 이미 굳은 뒤에도 계속 움직인다. 실측: 임계사이/무손실
        #     은 r7·r8 이 ips 1281·m=1 로 같은데 p 는 0.0067 -> 0.0063.
        # 재는 대상은 **행동의 수렴**이다: 마지막 세 라운드의 **최빈 선택**
        # (ips, m)이 같은가. 실측 6/6 조건이 이 기준을 만족한다.
        # p 표류는 판정이 아니라 **정보**로 남긴다 - 추정기의 정밀도가
        # 낮다는 사실(관측 100 회에 상대오차 ~45%)은 따로 보고할 값이다.
        def _modal(dd):
            return (max(dd.items(), key=lambda kv: kv[1])[0]
                    if dd else None)

        conv_ok, conv_why = False, "라운드가 3 개 미만"
        if len(rr) >= 3:
            _ms = [_modal(r_["m_used"]) for r_ in rr[-3:]]
            _is = [_modal(r_["ips_used"]) for r_ in rr[-3:]]
            conv_ok = len(set(_ms)) == 1 and len(set(_is)) == 1
            ps = [r_["p_est"] for r_ in rr[-3:]
                  if r_["p_est"] is not None]
            _dr = ((max(ps) - min(ps)) / max(ps)
                   if len(ps) == 3 and max(ps) > 0 else None)
            conv_why = ("최빈 선택 ips%s m%s | p 표류 %s"
                        % (_is, _ms,
                           ("%.1f%%" % (100 * _dr))
                           if _dr is not None else "읽지 못함"))

        out["regret"].append({
            "cond": name, "cert": cert, "loss": loss,
            "best_fixed": best, "best_fixed_mean": fixed_means_late[best],
            "best_fixed_full": best_full,
            "best_fixed_mean_full": fixed_means[best_full],
            "fixed_means_late": fixed_means_late,
            "auto_final_mean": fin["mean"], "regret_ms": reg,
            "regret_full_ms": reg_full,
            "se_method": ("batch" if _methods == ["batch"]
                          else "+".join(_methods) or None),
            "regret_holdout_ms": reg_hold,
            "probe_rounds_final": n_probe_fin,
            "probe_tax_ms": probe_tax,
            "regret_sel_ms": reg_sel,
            "se_regret_ms": se_reg,
            "ci95_half_ms": (1.96 * se_reg) if se_reg is not None else None,
            "regret_paired_late_ms": reg_paired,
            "regret_paired_late_ci95_half_ms": reg_paired_half,
            "paired_rounds": len(_pd),
            "converged": conv_ok, "converge_why": conv_why,
            "fixed_means": fixed_means,
            "auto_added_bytes": fin["added_bytes_mean"],
            "best_added_bytes": arms[best]["added_bytes_mean"]})
        print("    -> 최선 고정팔 %s (수렴후창 %.2f ms), auto 수렴후 %.2f ms, "
              "후회 %+.2f ms (전구간창 %+.2f, 홀드아웃 %s, ±%s ms) | 수렴 %s (%s)"
              % (best, fixed_means_late[best], fin["mean"], reg, reg_full,
                 ("%+.2f" % reg_hold) if reg_hold is not None else "-",
                 ("%.2f" % (1.96 * se_reg)) if se_reg is not None else "-",
                 "예" if conv_ok else "**아니오**", conv_why),
              flush=True)

    # ------------------------------------------------------------- 판정
    print()
    print("=" * 104)
    # 🩸 2026-08-21 - 판정을 `if regs:` 안에 두면 **데이터가 없을 때 검사가
    #    통째로 사라지고** 남은 것만으로 만점이 되어 종료코드 0 이 난다.
    #    조건 수부터 검사하고 헤드라인은 항상 등록한다.
    add("6 조건이 전부 측정됐다 (빠진 조건이 헤드라인을 좋게 만들 수 없다)",
        len(out["regret"]) == len(CONDS),
        "%d/%d | 빠짐 %s" % (len(out["regret"]), len(CONDS),
                            [d["cond"] for d in out.get("dropped", [])]
                            or "없음"))
    add("모든 고정팔에서 서버 통계가 실제로 있었다",
        all(r.get("srv_stats_present") for r in out["rows"]) and out["rows"],
        "%d/%d 팔" % (sum(1 for r in out["rows"]
                         if r.get("srv_stats_present")), len(out["rows"])))

    regs = [r["regret_ms"] for r in out["regret"]]
    regs_h = [r["regret_holdout_ms"] for r in out["regret"]
              if r["regret_holdout_ms"] is not None]
    cis = [r["ci95_half_ms"] for r in out["regret"]
           if r["ci95_half_ms"] is not None]
    worst = max(regs) if regs else None
    out["worst_regret_ms"] = worst
    out["worst_regret_holdout_ms"] = max(regs_h) if regs_h else None
    out["worst_ci95_half_ms"] = max(cis) if cis else None
    add("수렴 후 최악 후회 < 2 ms (p11 과 같은 자)",
        worst is not None and worst < 2.0,
        "최악 %s ms | 조건별 %s"
        % (("%+.2f" % worst) if worst is not None else "데이터 없음",
           ["%+.2f" % v for v in regs]))
    add("수렴 후 최악 후회 < 2 ms (승자의 저주 보정)",
        regs_h and max(regs_h) < 2.0,
        "최악 %s ms | 조건별 %s"
        % (("%+.2f" % max(regs_h)) if regs_h else "데이터 없음",
           ["%+.2f" % v for v in regs_h]))
    add("후회 추정의 95% 신뢰반폭이 1 ms 미만 (기준 2 ms 를 판정할 정밀도)",
        cis and max(cis) < 1.0,
        "최대 반폭 %s ms | 조건별 %s"
        % (("%.2f" % max(cis)) if cis else "-",
           ["%.2f" % v for v in cis]))
    # 🆕 "수렴 후" 라고 부르려면 실제로 수렴했어야 한다.
    nconv = sum(1 for r in out["regret"] if r.get("converged"))
    add("모든 조건이 실제로 수렴했다 (선언이 아니라 시험)",
        nconv == len(out["regret"]) and out["regret"],
        "%d/%d | %s" % (nconv, len(out["regret"]),
                        "; ".join("%s:%s" % (r["cond"], r["converge_why"])
                                  for r in out["regret"]
                                  if not r.get("converged")) or "전부 수렴"))

    # v2 의 고유 가치: 임계사이/무손실에서 정책이 스스로 δ=1 로 간다.
    conv = next((a for a in out["auto"] if a["cert"] == 4032
                 and a["loss"] == 0.0), None)
    if conv and conv["final"]:
        fin = conv["final"]
        n1281 = fin["ips_used"].get(1281, fin["ips_used"].get("1281", 0))
        add("임계사이/무손실: 수렴 후 평상시 선택이 pad(δ=1) (ips 1281 과반)",
            n1281 > N // 2, "ips 분포 %s | p추정 %s" % (fin["ips_used"],
                                                       fin["p_est"]))
        # 2026-08-21 정정. 예전 검사는 "auto 추가 바이트 < m1 의 10%",
        # 즉 **같은 왕복을 1 바이트로 산다**는 주장이었다. 2026-08-21 에
        # 모형을 고치고 나니 **정책이 그 선택을 하지 않는다** - 그리고
        # 하지 않는 것이 옳다:
        #   pad(δ=1) 단독이 이기는 구간은 p < 5e-5 뿐인데,
        #   추정기의 하한은 (0+0.5)/(100+1) = 4.95e-3 이다 (감쇠 0.99 로
        #   ObsCount 고정점이 100). **99 배 위**라 도달할 수 없다.
        #   도달 가능한 손실률에서는 패리티가 막아 주는 PTO(200.86 ms)가
        #   그 바이트값보다 크다. 실측도 그렇다 - auto 의 후회가 음수다
        #   (고정 pad 팔보다 빠르다).
        # 그래서 **거짓이 된 주장 대신 참인 것을 잰다**:
        #   (a) δ 지렛대를 실제로 쓴다 (위 ips 1281 검사)
        #   (b) 최대치로 도배하지 않는다 (m2 팔보다 확실히 적게 쓴다)
        #   (c) δ 단독 구간이 도달 불가능하다는 사실 자체를 못박는다
        ab = fin["added_bytes_mean"]
        m2b = next((r["added_bytes_mean"] for r in out["rows"]
                    if r["arm"] == "m2" and r["cert"] == 4032
                    and r["loss"] == 0.0), None)
        add("임계사이/무손실: auto 가 최대치로 도배하지 않는다 "
            "(m2 고정팔의 70% 미만)",
            ab is not None and m2b and ab < 0.7 * m2b,
            "auto 평균 추가 %.1f B vs m2 %.1f B" % (ab or -1, m2b or -1))
        _pcrit = _delta_only_crossover()
        _pfloor = 0.5 / 101.0
        add("δ 단독 구간은 추정기가 도달할 수 없다 "
            "(그래서 결합을 고르는 것이 옳다)",
            _pcrit < _pfloor,
            "pad 단독이 이기는 p < %.2e vs 추정기 하한 %.2e (%.0f 배)"
            % (_pcrit, _pfloor, _pfloor / max(_pcrit, 1e-12)))

    # pad 고정팔의 실측 확인 - δ=1 이 실제로 왕복 하나를 산다 (헤드라인 재현)
    pad4032 = next((r for r in out["rows"] if r["arm"] == "pad"
                    and r["cert"] == 4032 and r["loss"] == 0.0), None)
    m04032 = next((r for r in out["rows"] if r["arm"] == "m0"
                   and r["cert"] == 4032 and r["loss"] == 0.0), None)
    if pad4032 and m04032 and pad4032["p50"] and m04032["p50"]:
        d = m04032["p50"] - pad4032["p50"]
        add("pad(δ=1) 고정팔이 맨몸보다 1 왕복 빠르다 (임계사이/무손실)",
            d >= 0.8 * RTT_MS, "%.2f ms = %.3f RTT" % (d, d / RTT_MS))

    # 서버가 조건당 하나라 고정팔·auto 에 같은 수가 복사돼 있다 - 조건별 한 번.
    crc = sum(a.get("srv_crc_fail") or 0 for a in out["auto"])
    add("모든 팔에서 복구 CRC 실패 0", crc == 0, "총 %d 건 (조건별 합)" % crc)
    _bad_se = [r["cond"] for r in out["regret"] if r.get("se_method") != "batch"]
    add("모든 조건의 반폭이 배치평균(독립 가정 아님)으로 나왔다",
        out["regret"] and not _bad_se,
        "iid 로 되돌아간 조건: %s" % (_bad_se or "없음"))

    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    _fname = ("smoke_" if N < N_DEFAULT else "") + "p15_v2policy.json"
    print("saved:", B.save(_fname, out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
