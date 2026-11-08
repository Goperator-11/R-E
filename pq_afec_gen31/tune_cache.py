from __future__ import annotations

import pathlib
import sys
from datetime import datetime

from afec import FecConfig
from afec.sim import simulate_data

def _harden_console():
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


_harden_console()

SEEDS = tuple(range(201, 233))
N_BLOCKS = 30
RTT = 40.0

W_LIST = (100.0, 200.0, 400.0, 800.0, 1536.0)
Z_LIST = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
COLD_PROBS = (0.0, 0.005, 0.02, 0.05, 0.10)

SCENARIOS = (
    ("ok@0.005", 0.005, 4.0, 0.005, 4.0),
    ("ok@0.02", 0.02, 4.0, 0.02, 4.0),
    ("ok@0.05", 0.05, 4.0, 0.05, 4.0),
    ("ok@0.1", 0.10, 4.0, 0.10, 4.0),
    ("lo@0.005", 0.005, 4.0, 0.0025, 4.0),
    ("lo@0.02", 0.02, 4.0, 0.01, 4.0),
    ("hi@0.005", 0.005, 4.0, 0.01, 4.0),
    ("hi@0.02", 0.02, 4.0, 0.04, 4.0),
    ("hi@0.1", 0.10, 4.0, 0.20, 4.0),
    ("wrongLO", 0.10, 4.0, 0.005, 1.0),
    ("wrongHI", 0.005, 4.0, 0.10, 4.0),
    ("wrongB", 0.05, 4.0, 0.05, 1.0),
    ("ghost", 0.0, 1.0, 0.02, 4.0),
)


def _stderr(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return (var / n) ** 0.5


def main(z_list=Z_LIST, do_long=True):
    true_cells = sorted({(p, b) for _, p, b, _, _ in SCENARIOS}
                        | {(p, 4.0) for p in COLD_PROBS if p > 0}
                        | {(0.0, 1.0)})

    print("oracle baseline computing ...")
    base_cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    oracle = {(p, b, s): simulate_data("oracle", p, b, RTT, base_cfg,
                                       n_blocks=N_BLOCKS, seed=s).total_ms
              for p, b in true_cells for s in SEEDS}

    def regrets(policy, p, b, cfg, prior=None):
        return [simulate_data(policy, p, b, RTT, cfg, n_blocks=N_BLOCKS,
                              seed=s, prior=prior).total_ms
                / oracle[(p, b, s)] - 1.0 for s in SEEDS]

    print("\n" + "=" * 90)
    print(f"  콜드 스타트 (캐시 없음, 블록 {N_BLOCKS}, 시드 {len(SEEDS)}개"
          " 평균, 괄호=표준오차)")
    print("=" * 90)
    cold_worst = {}
    print(f"{'z':>5}" + "".join(f"{p:>13.1%}" for p in COLD_PROBS)
          + f"{'WORST':>10}")
    for z in z_list:
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, risk_z=z)
        row, worst = f"{z:>5.1f}", (0.0, 0.0)
        for p in COLD_PROBS:
            b = 4.0 if p > 0 else 1.0
            rs = regrets("adaptive", p, b, cfg)
            m, se = sum(rs) / len(rs), _stderr(rs)
            if m > worst[0]:
                worst = (m, se)
            row += f" {m:>7.1%}({se:.1%})"
        cold_worst[z] = worst
        print(row + f" {worst[0]:>8.1%}")

    summary = []
    for z in z_list:
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, risk_z=z)
        for w in W_LIST:
            cells = {}
            worst = (0.0, 0.0, "")
            for lab, p, b, cp, cb in SCENARIOS:
                rs = regrets("cached", p, b, cfg, prior=(cp, cb, w))
                m, se = sum(rs) / len(rs), _stderr(rs)
                cells[lab] = (m, se)
                if m > worst[0]:
                    worst = (m, se, lab)
            sys_worst = max(worst[0], cold_worst[z][0])
            summary.append((z, w, worst, cold_worst[z][0], sys_worst, cells))
            print(f"\n  z={z:.1f} w={w:g}  cached-worst {worst[0]:.1%}"
                  f"(se {worst[1]:.1%}, {worst[2]})"
                  f"  cold-worst {cold_worst[z][0]:.1%}"
                  f"  SYSTEM {sys_worst:.1%}")
            print("    " + "  ".join(f"{lab}:{m:.1%}" for lab, (m, _) in
                                     cells.items()))

    print("\n" + "=" * 90)
    print("  요약: 시스템 최악 후회 = max(캐시 시나리오 13개, 콜드 5개)")
    print("=" * 90)
    print(f"{'':>7}" + "".join(f"{f'w={w:g}':>12}" for w in W_LIST))
    for z in z_list:
        row = f"z={z:>4.1f}"
        for w in W_LIST:
            s = next(s for s in summary if s[0] == z and s[1] == w)
            row += f"{s[4]:>12.1%}"
        print(row)

    best = min(summary, key=lambda s: s[4])
    z_s, w_s, worst, cold, sysw, cells = best
    print("-" * 90)
    print(f"  최적: z={z_s:.1f}, w={w_s:g}  (시스템 최악 {sysw:.1%};"
          f" 캐시 최악 {worst[0]:.1%} @ {worst[2]}, 콜드 최악 {cold:.1%})")
    near = [s for s in summary if s[4] <= sysw + 0.02]
    print(f"  2%p 이내 동률 {len(near)}개:"
          + "  ".join(f"(z={s[0]:.1f},w={s[1]:g})" for s in near))

    if not do_long:
        return
    print("\n" + "=" * 90)
    print("  최적 z 의 긴 연결(400블록) 검증 (콜드) - v0.1 기준선(z=2.5)과 비교")
    print("=" * 90)
    long_seeds = tuple(range(101, 113))
    oracle_cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    oracle_ms = {}
    for p in COLD_PROBS:
        b = 4.0 if p > 0 else 1.0
        oracle_ms[p] = {s: simulate_data("oracle", p, b, RTT, oracle_cfg,
                                         n_blocks=400, seed=s).total_ms
                        for s in long_seeds}
    for z in sorted({z_s, 2.5}):
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, risk_z=z)
        worst = 0.0
        row = f"  z={z:.1f}: "
        for p in COLD_PROBS:
            b = 4.0 if p > 0 else 1.0
            oc = oracle_ms[p]
            rs = [simulate_data("adaptive", p, b, RTT, cfg, n_blocks=400,
                                seed=s).total_ms / oc[s] - 1.0
                  for s in long_seeds]
            m = sum(rs) / len(rs)
            worst = max(worst, m)
            row += f" {p:.1%}:{m:.1%}"
        print(row + f"  WORST {worst:.1%}")


class _Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def write(self, s):
        sys.__stdout__.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        sys.__stdout__.flush()
        self.f.flush()


if __name__ == "__main__":
    args = [float(a) for a in sys.argv[1:]]
    z_subset = tuple(args) if args else Z_LIST
    partial = bool(args)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"cache_wz_sweep_{stamp}.txt"
    out = pathlib.Path(__file__).parent / "docs" / name
    out.parent.mkdir(exist_ok=True)
    sys.stdout = _Tee(out)
    print(f"  출력 파일: {name}" + (f"  (부분 실행: z={z_subset})" if partial
                                    else ""))
    try:
        main(z_list=z_subset, do_long=not partial)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("SWEEP-CRASHED")
        raise
    print("ALL-DONE")
