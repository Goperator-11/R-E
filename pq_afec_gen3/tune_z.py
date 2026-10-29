"""신뢰상한 계수 z 튜닝 - **캐시 없는 콜드 스타트 전용 관점 (v0.1)**.

⚠️ v0.2부터 z의 최종 결정은 `tune_cache.py`의 (w, z) 공동 스윕이 한다.
캐시가 사전값(특히 L=4)을 물려주면 se 팽창 때문에 z의 실효 강도가 달라져서,
z를 캐시와 따로 튜닝하면 v0.1의 n_eff 사건(파라미터가 남의 역할을 떠맡음)을
반복하게 된다. 이 스크립트는 콜드 전용 관점의 기록으로 남겨 둔다.

배경: 추정기의 상승 편향을 없앴더니(검증에서 +47% -> +8%) 최악 후회가
4.3% -> 6.6%로 나빠졌다. 그 편향이 **1 RTT 피드백 지연을 우연히 보상**하고
있었던 것이다. 하지만 그 안전마진의 올바른 자리는 편향된 추정기가 아니라
신뢰상한 z다. z는 "추정 오차만큼 얹는다"는 뜻이 분명하고 튜닝 가능하다.

여기서 z를 훑어 최악 후회가 최소가 되는 값을 찾는다.
콘솔 출력은 ASCII만.
"""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime

from afec import FecConfig
from afec.sim import simulate_data

def _harden_console():
    """로케일이 빈약한 환경(리눅스 LANG=C, Windows cp949)에서 출력 크래시 방지.

    이 프로젝트는 마지막 print의 em-dash 하나로 12분 계산을 날린 적이 있다.
    인코딩이 못 담는 문자는 ?로 강등시켜서, 출력 때문에 계산이 죽는 일은
    구조적으로 없앤다. (표시가 깨질 뿐 계산·파일 기록은 무사하다)
    """
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


_harden_console()

PROBS = (0.0, 0.005, 0.02, 0.05, 0.10)
BURST, RTT = 4.0, 40.0


SEEDS = tuple(range(101, 113))   # 12개 시드 평균
SHORT_SEEDS = tuple(range(201, 233))   # 짧은 연결은 싸니까 시드를 더 쓴다


def _stderr(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return (var / n) ** 0.5


def sweep(label, n_blocks, seeds):
    """⚠️ 시드 하나로 z를 고르면 안 된다.

    처음엔 시드 1개로 훑었더니 z=2.5가 최적으로 나왔는데, 값들이 z에 대해
    단조롭지 않고 위아래로 튀었다(z=0.5가 z=1.0보다 나쁨). 그건 신호가 아니라
    몬테카를로 잡음이다. 시드를 여러 개 돌려 평균과 표준오차를 같이 봐야
    'z 차이'와 '시드 차이'를 구분할 수 있다.
    """
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
    """stdout과 파일에 동시에 쓴다."""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def write(self, s):
        sys.__stdout__.write(s)
        self.f.write(s)
        self.f.flush()   # 버퍼링하면 오래 걸리는 스윕의 중간 진행을 못 본다

    def flush(self):
        sys.__stdout__.flush()
        self.f.flush()


if __name__ == "__main__":
    # 🩸 출력 파일명은 **스크립트가 직접 정한다.**
    #    예전엔 호출 쪽에서 `> docs/z_스윕.txt`로 리다이렉트했는데, 백그라운드로
    #    두 번 돌렸더니 **두 프로세스가 같은 파일에 동시에 써서** 결과가 섞였다.
    #    앞부분은 새 실행, 뒷부분은 옛 실행이 남아 표가 일관돼 보이는데 틀렸다.
    #    타임스탬프를 붙이면 구조적으로 못 겹친다.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = pathlib.Path(__file__).parent / "docs" / f"z_sweep_{stamp}.txt"
    out.parent.mkdir(exist_ok=True)
    sys.stdout = _Tee(out)

    print(f"  출력 파일: {out.name}")

    # 긴 연결에서만 재면 콜드 스타트가 전체의 1%밖에 안 돼서, 정작 z가
    # 존재하는 이유(표본이 없는 연결 초반)를 검증하지 못한다. 짧은 연결을
    # 같이 재야 'z가 필요 없다'와 'z를 잴 구간이 없었다'가 구분된다.
    sweep("짧은 연결 (웹 페이지 로드 수준)", 30, SHORT_SEEDS)
    sweep("긴 연결 (벌크 전송)", 400, SEEDS)
    sys.stdout.flush()
