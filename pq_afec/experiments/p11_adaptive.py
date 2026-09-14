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

🩸 2026-09-07 - **팔을 교대로 잰다** (run_condition 주석). 순차 측정에서는
   기계 표류가 후회로 계상됐다(08-30 정밀 실행 1.17 ms 중 대부분). 저널 단위가
   팔에서 조건으로 바뀌었고, 표준오차는 배치평균(blockstat)으로 잰다.

Output: experiments/results/p11_adaptive.json
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
import blockstat as BST                          # noqa: E402
from padfec import policy as POL                 # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
# 🩸 2026-08-20 p11 계측. N=200(수렴 후 절반 100)의 후반부 평균은 PTO 급
# 꼬리(+150~200 ms) 사건 하나에 ±1.5~2 ms 씩 흔들렸다 - 2 ms 기준을 재는
# 자의 표준오차가 기준과 같은 크기였다. 기준은 그대로 두고 표본을 키운다
# (수렴 후 절반 300, 표준오차 ~1.1 ms). p10 C2 와 같은 처방이다.
# 🩸 2026-08-21 - 표본을 밖에서 키울 수 있게 한다.
#    2 차 실행에서 후회의 95% 신뢰반폭이 **3.31 ms** 로 나왔다 -
#    판정선(2 ms)보다 크고 점추정(+2.37 ms)보다도 크다. 즉 이 표본으로는
#    기준을 통과했는지 실패했는지 **말할 수 없다**. 필요 표본은 조건별
#    반폭에서 역산해 N ≈ 4,000 이다(단독 약 112 분).
#    기준은 그대로 두고 표본만 키운다. 저널 키에 n 이 들어가므로
#    상시 실행분 캐시는 덮이지 않는다 - 두 자료가 같이 남는다.
#        python experiments/p11_adaptive.py --precise
#        PADFEC_P11_N=2000 python experiments/p11_adaptive.py
N_DEFAULT = 600
N_PRECISE = 4000
N = int(os.environ.get("PADFEC_P11_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))
CACHE = "/tmp/padfec_p11_cache.json"

# 🩸 2026-08-21 - 이 실행의 **실제 업링크 대역**. netem 에 rate 를 안 걸므로
#    0(무제한)이 사실이다. 그전에는 정책(Go)이 10 Mbps 를 리터럴로 박고 있어
#    없는 비용을 청구했고, 그 때문에 임계아래/손실5% 에서 m=1 을 골랐다
#    (실측 최선은 m=2). p16 이 이 값을 직접 잰다.
UPLINK_MBPS = 0.0

# 🩸 2026-08-26 - 고정팔을 M_MAX_DEFAULT 에서 **파생**시킨다. 그전에는
#    ("m0","m1","m2") 가 네 곳에 리터럴로 박혀 있었는데, 2026-08-25 에
#    m_max 가 2 -> 3 이 되면서 auto 는 m=3 을 600 판 중 594 판 고르는데
#    **비교할 고정팔이 없어졌다.** 결과:
#      - 일치 검사는 `"m3" in tie` 를 묻게 되어 **구조적으로 통과 불가**.
#        2026-08-25 자료의 불일치 4 건 중 3 건(임계위 전부)이 이것이다.
#      - 후회도 auto 가 실제로 고른 팔을 뺀 집합과 비교하게 된다.
#    p17 은 같은 이유로 2026-08-25 에 m3 팔을 받았는데 p11 은 빠졌다.
#    (실제로 m3 이 최선인 자리가 있다 - p17 실측 cert 9000·무제한·손실 2%
#     에서 m3 52.01 < m2 52.22.)
#    상한이 또 바뀌어도 여기가 따라오도록 리터럴을 없앤다.
FIXED_ARMS = tuple("m%d" % i for i in range(POL.M_MAX_DEFAULT + 1))
ALL_ARMS = FIXED_ARMS + ("auto",)

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


# 🩸 2026-09-07 - **팔을 교대로 잰다.** 그전에는 조건마다 m0 -> m1 -> m2 -> m3 ->
#    auto 순서로 팔당 N 판을 통째로 돌렸다. 그러면 기계의 단조 표류가 팔 이름에
#    그대로 얹힌다. 08-30 정밀 실행(N=4000)에서 같은 조건의 팔 평균이 첫 팔
#    51.34 -> 마지막 팔 52.51 ms 로 흘렀고 그 1.17 ms 가 통째로 「후회」로
#    계상됐다 - 같은 코드·같은 N 의 08-29 실행(0.629 ± 0.429)과 신뢰구간이
#    안 겹쳤다(1.173 ± 0.049). 오차막대는 팔 **안** 표본분산만 담으므로 정의상
#    그것을 못 본다. 처방은 표본을 늘리는 것이 아니라 팔을 교대로 도는 것이다
#    (README 「한계」·인계 §5 가 09-03 에 적어 둔 처방). p17 의 라틴 방격과 같은
#    원리다.
#
#    설계: 조건마다 서버 하나(fec=on - p17·p18 과 같다), BLOCKS 개 블록, 블록마다
#    다섯 팔을 회전한 순서로 N/BLOCKS 판씩. BLOCKS=10 이면 각 팔이 각 자리를
#    정확히 두 번 겪는다(균형). auto 의 캐시는 조건 시작에 한 번만 비우고
#    블록을 넘어 이어진다(콜드스타트 -> 수렴을 그대로 잰다). 「수렴 후」= 각
#    팔의 후반 절반 = 뒤쪽 5 블록이라, auto 와 고정팔의 수렴 후 창이 **같은
#    시간대**를 덮는다. 표준오차는 배치평균(blockstat.batch_se)으로 잰다 -
#    연속한 판은 독립이 아니다(p16 09-01 실측).
#    저널 단위는 팔이 아니라 조건이다 - 교대 측정은 팔 하나만 다시 잴 수 없다.
BLOCKS = 10
# 🩸 2026-09-07 감사 - N 이 BLOCKS 로 안 나뉘면 실제 팔당 판 수는 (N//BLOCKS)*BLOCKS
#    인데 키·out["n"]·필요표본은 N 을 썼다. 한 곳에서 맞춘다.
N_REQ = N
N = (N // BLOCKS) * BLOCKS
if N != N_REQ:
    print("   N=%d 은 블록 %d 로 안 나뉜다 - 팔당 %d 판으로 맞춘다"
          % (N_REQ, BLOCKS, N), flush=True)


def run_condition(cert, loss, jr):
    """조건 하나의 다섯 팔을 교대로 잰다. {팔: rec}."""
    key = "%d|%.1f|latin|n%d|b%d" % (cert, loss, N, BLOCKS)
    if jr.has(key):
        return jr.get(key)
    n_blk = N // BLOCKS
    B.set_netem(RTT_MS / 2.0, loss_c2s=loss)
    try:
        os.unlink(CACHE)          # 조건마다 한 번 - 콜드스타트부터 정직하게
    except OSError:
        pass
    rows_by = {a: [] for a in ALL_ARMS}
    blocks_by = {a: [] for a in ALL_ARMS}
    err_by = {a: "" for a in ALL_ARMS}
    p, sp = B.start_server(cert, fec="on")
    try:
        for b in range(BLOCKS):
            r = b % len(ALL_ARMS)
            order = ALL_ARMS[r:] + ALL_ARMS[:r]
            for pos, arm in enumerate(order):
                if arm == "auto":
                    fec, m, extra = "auto", 1, ["-cache", CACHE]
                else:
                    m = int(arm[1:])
                    fec, extra = ("off" if m == 0 else "on"), []
                rows, cs, e = B.run_client(
                    GROUP, n_blk, fec=fec, m=max(m, 1), gap_ms=8,
                    timeout_s=10, expect_k=K, extra=extra,
                    # 🩸 2026-08-21 - 정책에 **이 실행의 실제 업링크**를 알려
                    #    준다. 그전에는 Go 가 10 Mbps 를 리터럴로 박고 있었다.
                    uplink_mbps=UPLINK_MBPS)
                if e:
                    err_by[arm] = e
                rows_by[arm].extend(rows)
                ok = [x["ms"] for x in rows if x.get("ok")]
                blocks_by[arm].append({"block": b, "pos": pos, "n": len(rows),
                                       "ok": len(ok), "mean": mean(ok)})
            print("   블록 %2d/%d  %s"
                  % (b + 1, BLOCKS,
                     "  ".join("%s(자리%d) %.2f"
                               % (a, blocks_by[a][-1]["pos"],
                                  blocks_by[a][-1]["mean"] or -1)
                               for a in order)), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    out = {}
    for arm in ALL_ARMS:
        rows = rows_by[arm]
        ok = [r["ms"] for r in rows if r.get("ok")]
        # 🩸 두 통계가 서로 다른 창을 쓰면 안 된다. **행 인덱스 기준 한 창**.
        half_rows = len(rows) // 2
        late_rows = rows[half_rows:]
        ok_late = [r["ms"] for r in late_rows if r.get("ok")]
        out[arm] = {
            "arm": arm, "cert": cert, "loss": loss,
            "n": len(rows), "ok": len(ok),
            "mean": mean(ok), "mean_late": mean(ok_late),
            "p50": B.pctl(ok, 0.5), "p95": B.pctl(ok, 0.95),
            "tail": tail_rate(ok, 1.5 * RTT_MS),
            "tail_late": tail_rate(ok_late, 1.5 * RTT_MS),
            "m_used": [r.get("m_used") for r in rows],
            # 행 단위 원자료 - 탐색세 분리(0-c)·신뢰구간·사후 추적에 쓴다.
            "ms_rows": [r["ms"] if r.get("ok") else None for r in rows],
            "probe_rows": [(r.get("m_why") or "").startswith("탐색")
                           for r in rows],
            "ms": ok, "ms_late": ok_late,
            "m_why": [r.get("m_why") for r in rows[:3]],
            "blocks": blocks_by[arm],
            # 서버가 조건당 하나이므로 아래 둘은 **조건 합**이다.
            "srv_recovered": ss.get("recovered"),
            "srv_crc_fail": ss.get("recover_crc_fail"),
            "srv_stats_present": bool(ss),
            "err": err_by[arm]}
    complete = all(len(rows_by[a]) == n_blk * BLOCKS for a in ALL_ARMS)
    if complete and bool(ss) and (ss.get("recover_crc_fail") or 0) == 0:
        jr.record(key, out)
    return out


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

    out = {"rtt_ms": RTT_MS, "n": N, "n_requested": N_REQ, "group": GROUP,
           "blocks": BLOCKS, "interleaved": True,
           "rows": [], "regret": [], "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-52s %s" % ("통과" if ok else "실패", name, detail[:76]))
        sys.stdout.flush()

    print("=" * 104)
    print("폐루프(auto) 대 고정 m - 조건마다 팔당 n=%d, 블록 %d 교대" % (N, BLOCKS))
    print("=" * 104)
    print("%-18s %-6s %-9s %-9s %-9s %-9s %s"
          % ("조건", "팔", "평균", "수렴후평균", "꼬리", "복구(조건합)", "고른 m"))

    for name, cert, loss in CONDS:
        print("### %s (cert %d, 손실 %g%%)" % (name, cert, loss), flush=True)
        arms = run_condition(cert, loss, jr)
        for arm in ALL_ARMS:
            r = arms[arm]
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

        fixed = {a: arms[a]["mean"] for a in FIXED_ARMS
                 if arms[a]["mean"] is not None}
        if not fixed or arms["auto"]["mean"] is None:
            # 🩸 2026-08-21 - 예전에는 여기서 그냥 `continue` 했다. 헤드라인이
            #    max(후회) 라서 **하필 최악 조건이 빠지면 헤드라인이 저절로
            #    좋아진다.** 어디에도 기록이 없었다. 이제 남기고 검사한다.
            out.setdefault("dropped", []).append(
                {"cond": name, "cert": cert, "loss": loss,
                 "why": "측정 실패", "errs": {a: arms[a].get("err")
                                          for a in arms}})
            print("    -> !! 측정 실패로 이 조건이 빠졌다: %s" % name)
            sys.stdout.flush()
            continue
        best_arm = min(fixed, key=lambda a: fixed[a])
        reg = arms["auto"]["mean"] - fixed[best_arm]
        fixed_late = {a: arms[a]["mean_late"] for a in FIXED_ARMS
                      if arms[a]["mean_late"] is not None}
        best_late = min(fixed_late, key=lambda a: fixed_late[a])
        reg_late = arms["auto"]["mean_late"] - fixed_late[best_late]

        # 🩸 2026-08-21 (0-c) - **탐색세 분리.** 항등식
        #        전체평균 = f·탐색평균 + (1-f)·선택평균
        #    에서 후회 = (선택평균-최선) + f·(탐색평균-선택평균)
        #             =  선택 오류분    +  탐색세.
        #    기준(2 ms)은 전체 후회에 그대로 걸려 있다 - 내역만 보인다.
        _mr = arms["auto"].get("ms_rows") or []
        _pr = arms["auto"].get("probe_rows") or []
        probe_tax = reg_sel = n_probe_late = None
        if _mr and len(_mr) == len(_pr):
            _h = len(_mr) // 2
            _lp = [t for t, f_ in zip(_mr[_h:], _pr[_h:])
                   if f_ and t is not None]
            _ls = [t for t, f_ in zip(_mr[_h:], _pr[_h:])
                   if not f_ and t is not None]
            n_probe_late = len(_lp)
            if _lp and _ls:
                _f = len(_lp) / float(len(_lp) + len(_ls))
                probe_tax = _f * (mean(_lp) - mean(_ls))
                reg_sel = reg_late - probe_tax

        # 🩸 2026-08-21 승자의 저주 보정.
        #    `min(고정 3 팔의 평균)` 은 **잡음이 있는 셋의 최소**라 기댓값이
        #    참값보다 작다. 그래서 후회가 체계적으로 과대하게 나온다. 게다가
        #    헤드라인은 6 조건의 **최대**라 상방 편향이 한 번 더 붙는다.
        #    표본을 반으로 갈라 **앞 절반으로 고르고 뒤 절반으로 잰다** -
        #    고르는 데 쓴 잡음과 재는 데 쓴 잡음이 독립이라 편향이 없어진다.
        #    (옛 정의도 그대로 남긴다. 수를 조용히 바꾸지 않기 위해서다.)
        sel = {}
        ev = {}
        for a in FIXED_ARMS:
            v = arms[a].get("ms") or []
            h = len(v) // 2
            if h >= 5:
                sel[a] = mean(v[:h])
                ev[a] = mean(v[h:])
        reg_hold = None
        best_hold = None
        se_hold = None
        if sel and ev and arms["auto"]["mean_late"] is not None:
            best_hold = min(sel, key=lambda a: sel[a])
            reg_hold = arms["auto"]["mean_late"] - ev[best_hold]

        # 후회의 표준오차. auto 와 고정팔은 **서로 다른 손실 실현**을 본
        # 독립 표본이므로 분산이 더해진다.
        # 🩸 2026-09-07 - s/sqrt(n) 이 아니라 배치평균 SE 다. 연속한 판은
        #    독립이 아니라(부하·표류) 옛 식은 반폭을 과소평가했다(인계 §4b-4b:
        #    p15 1.25 배, p16 2.43 배). blockstat.batch_se 는 p16·p15 와 같은 자다.
        _se_methods = []

        def _se(v):
            se, method, kb = BST.batch_se_info(v)
            _se_methods.append((method, kb))
            return se

        se_auto = _se(arms["auto"].get("ms_late") or [])
        se_fix = _se(arms[best_late].get("ms_late") or [])
        se_reg = None
        if se_auto is not None and se_fix is not None:
            se_reg = (se_auto ** 2 + se_fix ** 2) ** 0.5

        # 🩸 2026-08-25 - 위 se_reg 는 **수렴 후 표본(ms_late)** 에서
        #    나온 수라 regret_late_ms 의 정밀도다. 전 구간 후회
        #    (regret_ms) 에 그 정밀도를 갖다 붙이면 안 된다 - 표본이
        #    다르다. 전 구간용은 전 구간 표본으로 따로 낸다.
        se_auto_f = _se(arms["auto"].get("ms") or [])
        se_fix_f = _se(arms[best_arm].get("ms") or [])
        se_reg_f = None
        if se_auto_f is not None and se_fix_f is not None:
            se_reg_f = (se_auto_f ** 2 + se_fix_f ** 2) ** 0.5
        # 🩸 2026-09-07 감사 - 홀드아웃 후회의 반폭은 **그 표본**(auto 수렴 후 +
        #    최선 홀드아웃 팔의 뒤 절반)에서 낸다. 그전에는 수렴 후 후회의 반폭을
        #    빌려 썼다 - 다른 조건·다른 표본 크기의 자였다.
        if best_hold is not None:
            _v = arms[best_hold].get("ms") or []
            _se_h = _se(_v[len(_v) // 2:])
            if se_auto is not None and _se_h is not None:
                se_hold = (se_auto ** 2 + _se_h ** 2) ** 0.5
        _methods = sorted(set(m for m, _k in _se_methods if m))
        half_late = BST.batch_diff_half(arms["auto"].get("ms_late") or [],
                                        arms[best_late].get("ms_late") or [])
        half_full = BST.batch_diff_half(arms["auto"].get("ms") or [],
                                        arms[best_arm].get("ms") or [])
        half_hold = None
        if best_hold is not None:
            hold_values = arms[best_hold].get("ms") or []
            half_hold = BST.batch_diff_half(arms["auto"].get("ms_late") or [],
                                            hold_values[len(hold_values)//2:])

        out["regret"].append({
            "cond": name, "cert": cert, "loss": loss,
            "best_fixed": best_arm, "best_fixed_mean": fixed[best_arm],
            "auto_mean": arms["auto"]["mean"], "regret_ms": reg,
            "best_fixed_late": best_late,
            "auto_mean_late": arms["auto"]["mean_late"],
            "regret_late_ms": reg_late,
            "regret_holdout_ms": reg_hold,
            "probe_rounds_late": n_probe_late,
            "probe_tax_ms": probe_tax,
            "regret_late_sel_ms": reg_sel,
            "best_fixed_holdout": best_hold,
            "se_regret_ms": se_reg,
            "ci95_half_ms": half_late,
            "ci95_half_full_ms": half_full,
            "ci95_half_holdout_ms": half_hold,
            "ci_method": "Welch-t on batch means (iid fallback for short samples)",
            "se_method": ("batch" if _methods == ["batch"]
                          else "+".join(_methods) or None),
            "se_batches_min": min((k for _m, k in _se_methods if k),
                                  default=None),
            "fixed_means": fixed,
            "fixed_means_late": fixed_late})
        print("    -> 최선 고정팔 %s (%.2f ms), auto %.2f ms, "
              "후회 %+.2f ms (수렴후 %+.2f ms, 홀드아웃 %s, ±%s ms)"
              % (best_arm, fixed[best_arm], arms["auto"]["mean"], reg,
                 reg_late,
                 ("%+.2f" % reg_hold) if reg_hold is not None else "-",
                 ("%.2f" % half_late) if half_late is not None else "-"))
        if probe_tax is not None:
            print("       내역: 선택 오류분 %+.2f ms + 탐색세 %+.2f ms "
                  "(수렴후 탐색 %d 라운드)"
                  % (reg_sel, probe_tax, n_probe_late))
        sys.stdout.flush()

    _taxes = [r["probe_tax_ms"] for r in out["regret"]
              if r.get("probe_tax_ms") is not None]
    out["worst_probe_tax_ms"] = max(_taxes) if _taxes else None

    # ------------------------------------------------------------- 판정
    print()
    print("=" * 104)
    # 🩸 2026-08-21 - 헤드라인 판정이 `if regs:` 안에 있으면 **데이터가 없을 때
    #    검사 자체가 사라지고** 남은 것만으로 "N/N 통과"가 되어 종료코드 0 이
    #    난다. 조건 수부터 먼저 검사하고, 헤드라인은 항상 등록한다.
    add("6 조건이 전부 측정됐다 (빠진 조건이 헤드라인을 좋게 만들 수 없다)",
        len(out["regret"]) == len(CONDS),
        "%d/%d 조건 | 빠짐 %s"
        % (len(out["regret"]), len(CONDS),
           [d["cond"] for d in out.get("dropped", [])] or "없음"))
    add("모든 팔에서 서버 통계가 실제로 있었다 (없으면 CRC 검사가 공허해진다)",
        all(r.get("srv_stats_present") for r in out["rows"]) and out["rows"],
        "%d/%d 팔"
        % (sum(1 for r in out["rows"] if r.get("srv_stats_present")),
           len(out["rows"])))

    regs = [r["regret_ms"] for r in out["regret"]]
    regs_late = [r["regret_late_ms"] for r in out["regret"]]
    regs_hold = [r["regret_holdout_ms"] for r in out["regret"]
                 if r["regret_holdout_ms"] is not None]
    cis = [r["ci95_half_ms"] for r in out["regret"]
           if r["ci95_half_ms"] is not None]
    worst = max(regs) if regs else None
    worst_late = max(regs_late) if regs_late else None
    worst_hold = max(regs_hold) if regs_hold else None
    out["worst_regret_ms"] = worst
    out["worst_regret_late_ms"] = worst_late
    out["worst_regret_holdout_ms"] = worst_hold
    out["worst_ci95_half_ms"] = max(cis) if cis else None

    # 🩸 2026-08-25 - worst_ci95_half_ms 는 **조건들의 반폭 중 최대**라
    #    헤드라인 수를 낸 그 조건의 정밀도가 아니다(상한이다). 감시 띠를
    #    거기서 뽑으면 띠가 필요 이상으로 넓어져 '구별 불가'가 남발된다.
    #    헤드라인과 **같은 조건**의 반폭을 따로 적는다.
    def _ci_at(field, value, key):
        if value is None:
            return None
        for _r in out["regret"]:
            if _r.get(field) == value:
                return _r.get(key)
        return None

    out["worst_regret_ci95_half_ms"] = _ci_at(
        "regret_ms", worst, "ci95_half_full_ms")
    out["worst_regret_late_ci95_half_ms"] = _ci_at(
        "regret_late_ms", worst_late, "ci95_half_ms")
    add("최악 후회가 5 ms 미만 (전 구간, 콜드스타트 포함)",
        worst is not None and worst < 5.0,
        "최악 %s ms | 조건별 %s"
        % (("%+.2f" % worst) if worst is not None else "데이터 없음",
           ["%+.1f" % v for v in regs]))
    # 🩸 2026-08-27 - **자를 그대로 두고 판정을 셋으로 가른다.**
    #
    #    옛 판은 점추정 하나를 2 ms 와 견줬다. 그런데 이 추정의 신뢰반폭이
    #    2 ms 와 **같은 크기**라, 같은 코드로 두 번 재면 판정이 뒤집힌다.
    #    2026-08-27 에 그것을 그대로 봤다:
    #        13:59  최악 후회 +0.898  반폭 1.15  -> 통과
    #        19:04  최악 후회 +2.06   반폭 1.99  -> 실패
    #    둘 다 같은 알고리즘·같은 자다. 뒤집힌 것은 **동전**이지 성능이
    #    아니다. 이런 실패는 「고쳐야 할 결함」이 아니라 「못 잰 것」이고,
    #    루프가 둘을 같은 통에 넣으면 없는 결함을 쫓게 된다.
    #
    #    p16 이 같은 날 받은 처방을 그대로 옮긴다 - 자(2 ms)는 **안 넓힌다.**
    #      맞음     추정 + 반폭 <= 2      2 ms 안이라고 **말할 수 있다**
    #      틀림     추정 - 반폭 >  2      2 ms 밖이라고 **말할 수 있다**
    #      판정불능 그 사이               구간이 자를 걸친다 -> 표본을 말한다
    #    실패로 세는 것은 **틀림뿐**이다. 판정불능은 자료가 모자란 것이므로
    #    detail 에 필요 표본과 함께 드러낸다.
    def _verdict(est, half, ruler=2.0):
        if est is None:
            return "데이터없음"
        if half is None:
            return "맞음" if est < ruler else "틀림"
        if est + half <= ruler:
            return "맞음"
        if est - half > ruler:
            return "틀림"
        return "판정불능"

    def _need_n(half, ruler, est, n_now):
        """구간이 자를 안 걸치려면 표본이 몇이어야 하나. 반폭 ∝ 1/sqrt(n)."""
        if half is None or est is None or n_now is None:
            return None
        want = abs(ruler - est)
        if want < 1e-9:
            return None
        return int(math.ceil(n_now * (half / want) ** 2))

    _h_late = out.get("worst_regret_late_ci95_half_ms")
    _v_late = _verdict(worst_late, _h_late)
    add("최악 후회가 2 ms 밖이라고 **말할 수 있는** 조건이 없다 (수렴 후)",
        _v_late != "틀림",
        "최악 %s ms ±%s -> %s%s | 조건별 %s"
        % (("%+.2f" % worst_late) if worst_late is not None else "데이터 없음",
           ("%.2f" % _h_late) if _h_late is not None else "?", _v_late,
           ("  필요 n=%s (지금 %d)"
            % (_need_n(_h_late, 2.0, worst_late, N), N))
           if _v_late == "판정불능" else "",
           ["%+.1f" % v for v in regs_late]))
    # 🆕 승자의 저주를 뺀 판. 고르기와 재기를 다른 표본으로 나눈다.
    _h_hold = _ci_at("regret_holdout_ms", worst_hold, "ci95_half_holdout_ms")
    _v_hold = _verdict(worst_hold, _h_hold)
    add("최악 후회가 2 ms 밖이라고 **말할 수 있는** 조건이 없다 "
        "(수렴 후 · 승자의 저주 보정)",
        _v_hold != "틀림",
        "최악 %s ms ±%s -> %s | 조건별 %s"
        % (("%+.2f" % worst_hold) if worst_hold is not None else "데이터 없음",
           ("%.2f" % _h_hold) if _h_hold is not None else "?", _v_hold,
           ["%+.1f" % v for v in regs_hold]))
    # 🆕 자가 기준을 판정할 만큼 정밀한가. 이게 없으면 "2 ms 미만"이 통과해도
    #    다음 실행에 뒤집힐 수 있다 - 실제로 캠페인마다 +4.92 / +3.08 / +1.19
    #    로 흔들렸다(2026-08-21 저널 대조). **기준을 완화하는 대신 자를 잰다.**
    add("후회 추정의 95% 신뢰반폭이 1 ms 미만 (기준 2 ms 를 판정할 정밀도)",
        cis and max(cis) < 1.0,
        "최대 반폭 %s ms | 조건별 %s"
        % (("%.2f" % max(cis)) if cis else "-",
           ["%.2f" % v for v in cis]))

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
        #
        # 🩸 2026-08-21 - 제외 규칙이 **전 구간 평균**(fixed_means)으로 계산되는데
        #    정답은 **수렴 후 최선**(best_fixed_late)에서 왔다. 두 창이 실제로
        #    다른 답을 내는 조건이 이미 있어서(임계아래/무손실: 전구간 m2 /
        #    수렴후 m1) 게이트와 판정 대상이 어긋나 있었다. 같은 창으로 맞춘다.
        #
        # 🩸 2026-08-21 - **제외 규칙이 조건을 너무 많이 버렸다.**
        #    옛 규칙은 최선과 **차선**의 차이만 봤다. 그래서
        #        임계위/무손실:  m0=102.80  m1=52.30  m2=52.20
        #    이 m1-m2 = 0.10 ms 라는 이유로 빠졌다 - 거기서 m0 을
        #    고르면 **+50.6 ms** 인데도. 6 조건 중 4 개가 그렇게 빠져
        #    검사가 2 조건 위에만 서 있었다.
        #
        #    옳은 판정: auto 가 **최선과 잡음 안에서 같은** 팔을
        #    골랐는가. 허용집합 = {최선과의 차이 < 1 ms 인 팔}.
        #    모든 팔이 허용집합에 들 때만(= 어느 것을 골라도 손해가
        #    없을 때만) 조건을 뺀다. 2 차 자료에서 2/6 -> 5/6 이 된다.
        fm = r["fixed_means_late"]
        best_val = min(fm.values())
        tie = sorted(a for a, v in fm.items() if (v - best_val) < 1.0)
        if len(tie) == len(fm):
            detail.append("%s: 전 팔이 최선과 1 ms 안 -> 판정 제외"
                          % r["cond"])
            continue
        tot += 1
        picked_ok = ("m%d" % mode_m) in tie
        if picked_ok:
            agree += 1
        detail.append("%s: auto m=%s / 최선 m=%d / 허용 %s%s"
                      % (r["cond"], mode_m, want, tie,
                         "" if picked_ok else " <-- 불일치"))
    if tot:
        add("수렴 후 auto 가 최선과 잡음 안에서 같은 m 을 골랐다",
            agree == tot, "%d/%d | %s" % (agree, tot, "; ".join(detail)))
        out["agreement"] = [agree, tot]
        # 🩸 위 검사가 **몇 조건 위에 서 있는지**를 함께 건다.
        #    판별력 있는 조건이 절반도 안 되면 통과해도 통과가 아니다.
        add("판별력 있는 조건이 절반 이상 (없으면 위 검사가 공허하다)",
            tot * 2 >= len(out["regret"]) and tot > 0,
            "%d/%d 조건에서 팔 선택이 실제로 손익을 가른다"
            % (tot, len(out["regret"])))

    # 서버가 조건당 하나라 팔마다 같은 수가 복사돼 있다 - 조건별로 한 번만 센다.
    _seen = set()
    crc = 0
    for r in out["rows"]:
        k_ = (r["cert"], r["loss"])
        if k_ in _seen:
            continue
        _seen.add(k_)
        crc += r["srv_crc_fail"] or 0
    add("모든 팔에서 복구 CRC 실패 0", crc == 0, "총 %d 건 (조건별 합)" % crc)
    # 🩸 2026-09-07 - 반폭이 배치평균으로 나왔는지 검사한다. 짧은 표본에서는
    #    iid 로 되돌아가는데, 그 반폭은 독립 가정이라 09-01 실측 기준 1.7~2.4 배
    #    과소평가다. 그 자로 통과한 정밀도 검사는 통과가 아니다.
    _bad_se = [r["cond"] for r in out["regret"] if r.get("se_method") != "batch"]
    add("모든 조건의 반폭이 배치평균(독립 가정 아님)으로 나왔다",
        out["regret"] and not _bad_se,
        "iid 로 되돌아간 조건: %s" % (_bad_se or "없음"))

    npass = sum(1 for c in out["checks"] if c["ok"])
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    out["passed"] = npass
    out["total"] = len(out["checks"])
    # 🩸 2026-09-07 - 기본 N 보다 작은 실행(스모크)은 정본 파일을 덮지 않는다.
    #    N=20 스모크가 n=4000 실측 결과를 덮어쓴 사고에서 나온 가드다.
    _fname = ("smoke_" if N < N_DEFAULT else "") + "p11_adaptive.json"
    print("saved:", B.save(_fname, out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
