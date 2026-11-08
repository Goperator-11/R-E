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

PROBS = (0.0, 0.005, 0.02, 0.05, 0.10)
BURST, RTT = 4.0, 40.0


SEEDS = tuple(range(101, 113))
SHORT_SEEDS = tuple(range(201, 233))


def _stderr(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return (var / n) ** 0.5


def sweep(label, n_blocks, seeds):
    base = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    oracle = {(p, s): simulate_data("oracle", p, BURST, RTT, base,
                                    n_blocks=n_blocks, seed=s).total_ms
              for p in PROBS for s in seeds}

    print(f"\n{'=' * 88}")
    print(f"  {label}  (블록 {n_blocks}개, 시드 {len(seeds)}개 평균, 괄호=표준오차)")
    print("=" * 88)
    print(f"{'z':>5}" + "".join(f"{p:>12.1%}" for p in PROBS)
          + f"{'WORST':>9}{'MEAN':>9}")
    print("-" * 88)

    rows = []
    for z10 in range(0, 31, 5):
        z = z10 / 10.0
        cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0, risk_z=z)
        cells, means = [], []
        for p in PROBS:
            regs = [simulate_data("adaptive", p, BURST, RTT, cfg,
                                  n_blocks=n_blocks, seed=s).total_ms
                    / oracle[(p, s)] - 1.0 for s in seeds]
            m = sum(regs) / len(regs)
            cells.append(f"{m:>7.1%}({_stderr(regs):.1%})")
            means.append(m)
        worst, mean = max(means), sum(means) / len(means)
        rows.append((z, worst, mean))
        print(f"{z:>5.1f}" + "".join(cells) + f"{worst:>8.1%}{mean:>8.1%}")

    print("-" * 88)
    best_worst = min(rows, key=lambda r: r[1])
    best_mean = min(rows, key=lambda r: r[2])
    print(f"  최악 후회 최소 : z = {best_worst[0]:.1f}  (worst {best_worst[1]:.1%})")
    print(f"  평균 후회 최소 : z = {best_mean[0]:.1f}  (mean  {best_mean[2]:.1%})")
    spread = max(r[1] for r in rows) - min(r[1] for r in rows)
    print(f"  z 전 구간 최악 후회 폭: {spread:.1%}"
          " - 이보다 작은 차이는 고르는 의미가 없다")
    return rows


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
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = pathlib.Path(__file__).parent / "docs" / f"z_sweep_{stamp}.txt"
    out.parent.mkdir(exist_ok=True)
    sys.stdout = _Tee(out)

    print(f"  출력 파일: {out.name}")

    sweep("짧은 연결 (웹 페이지 로드 수준)", 30, SHORT_SEEDS)
    sweep("긴 연결 (벌크 전송)", 400, SEEDS)
    sys.stdout.flush()
