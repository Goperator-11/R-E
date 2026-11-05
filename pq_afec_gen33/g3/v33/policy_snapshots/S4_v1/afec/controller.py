"""PQ-AFEC 제어기 - 적응형 FEC의 핵심.

설계 원칙
---------
"손실률이 높으면 FEC를 늘린다"는 규칙 기반 임계값 방식은 두 가지에서 진다.
(1) 임계값을 몇으로 둘지 근거가 없다. (2) 손실률이 같아도 **손실 한 번의 대가**가
상황마다 다르다는 걸 표현하지 못한다.

그래서 규칙 대신 **비용 최소화**로 간다. 이중화 개수 r을 고를 때

    J(r) = (1 + beta*g) * t_tx(r)  +  P_fail(K, r) * T_recover
           ^^^^^^^^^^^^^^^^^^^^^^     ^^^^^^^^^^^^^^^^^^^^^^^^^
           지금 확실히 내는 비용        복구 실패 시 확률적으로 낼 비용
           (여분 심볼 전송 시간)        (재전송까지 날리는 시간)

    r* = argmin J(r)

t_tx(r) = r * 심볼크기 * 8 / 링크속도  (ms)
g       = 혼잡 확신도. 혼잡일수록 여분 바이트의 실제 대가가 커지므로 가중.
T_recover = 복구 실패 시 물어야 하는 지연.

이 하나의 식이 다음을 전부 자동으로 설명한다.

* 핸드셰이크에 FEC를 몰아주는 이유
  ML-KEM 키 공유가 실린 ClientHello는 RTT 표본도 없고 뒤따르는 패킷도 없어서
  손실 검출이 PTO로 넘어간다. RFC 9002 기준 첫 PTO = 333 + 4*166.5 = 약 999 ms.
  T_recover가 1초짜리면 아주 작은 P_fail도 비싸므로 r이 커진다.

* 안정 구간에서 FEC를 끄는 이유
  데이터 구간의 T_recover는 약 2*RTT(예: 20~100 ms)라 두 자릿수 배 싸다.
  P_fail이 이미 작으면 여분 심볼 값을 못 하므로 r*=0이 자연히 나온다.

* 혼잡일 때 FEC를 늘리지 않는 이유
  g가 1로 가면 t_tx 항이 (1+beta)배로 뛰어 r이 눌린다. 혼잡 손실에
  이중화로 대응해 상황을 악화시키는 사고를 구조적으로 막는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .channel import GilbertElliott

# RFC 9002 상수
K_INITIAL_RTT_MS = 333.0
GF256_MAX_SYMBOLS = 255


@dataclass
class FecConfig:
    symbol_bytes: int = 1200        # 심볼 1개 = QUIC 패킷 1개
    rate_bps: float = 10e6          # 링크 속도 추정치
    beta: float = 4.0               # 혼잡 시 여분 바이트 비용 가중
    rho_max: float = 0.50           # 이중화 비율 상한 (r/K) - 데이터 구간용
    # 🩸 H2 (2026-08-18 감사): 핸드셰이크에 rho_max 를 그대로 쓰면 안 된다.
    # 핸드셰이크 플라이트는 K가 1~5뿐이라 ceil(K*0.5) = 1, 즉 탐색 후보가
    # {0,1} 로 잘린다. 이 연구의 논지는 "임계값 규칙을 버리고 비용 최소화로
    # 간다"인데, 정작 핸드셰이크의 r* 은 J 가 아니라 **데이터 구간에서 빌려온
    # 비율 임계값**이 정하고 있었다 (실측: p=5%,L=3 에서 shield r*=1 J=27.7,
    # 자유 탐색 r*=7 J=9.1 - J 가 67% 낮은 지점이 잘려 있었다).
    # 핸드셰이크는 1.2KB 대 1초라는 비대칭이 존재 이유이므로 비율 상한이
    # 의미가 없다. 넉넉한 절대 상한만 두고 나머지는 J 가 정하게 한다.
    handshake_rho_max: float = 4.0  # 핸드셰이크 이중화 비율 상한 (r/K)
    k_min: int = 4
    k_max: int = 64
    delay_budget_ms: float = 30.0   # 블록을 채우는 데 허용할 시간
    interleave: int = 1             # 인터리빙 깊이 D
    dwell_blocks: int = 4           # r을 내릴 때 요구하는 안정 지속 블록 수
    decay_fraction: float = 0.30    # 한 번에 줄이는 비율(남은 차이 대비)
    # 손실률 신뢰상한 계수. v0.1은 2.5였는데(캐시 없는 콜드 스타트 전제,
    # tune_z.py), v0.2에서 목적지 캐시와 **공동 튜닝**해 1.5로 내렸다
    # (tune_cache.py, 2026-08-14, 시드 32개). 이유:
    #  - 캐시가 L=4를 물려주면 se 팽창 sqrt(2L(1-p)-1) ~ 2.6배가 z에 곱해져
    #    z=2.5는 사실상 z=6.5처럼 동작한다. 링크가 깨끗해졌는데 캐시가 손실을
    #    기억하는 시나리오(ghost)가 만성 과보호로 후회 36.6%를 냈다.
    #  - 채택 기준은 "캐시가 어떻게 틀려도 캐시 없는 콜드보다 나쁘지 않을 것".
    #    이걸 만족하는 (z, w)는 z=1.5 + 반출 가중치 100뿐이었다. z=2.0/2.5는
    #    전 w에서 ghost 또는 wrongLO가 콜드를 초과.
    #  - 대가: 콜드 짧은 연결 최악이 25.5% -> 33.5% (+8%p). 캐시가 맞을 때
    #    최악 7.7%(콜드의 1/4)와 틀린 캐시 안전이 그 값어치를 한다.
    #    긴 연결(400블록)은 z가 낮을수록 좋아(v0.1 실측) 같이 개선된다.
    risk_z: float = 1.5
    # 부호화 CPU 비용. 2026-08-17 실측(experiments/e8_cpu_cost.py, i7-14700HX,
    # gcc -O3 -march=native): C 부호기 RS(40,32)x1200B = **0.011 ms/이중화 심볼**.
    # 파이썬(rs.py) 0.043과의 비는 3.9배 - 명세 v0.1의 "C는 100배 빠르다"는
    # 틀렸다(rs.py가 bytes.translate + big-int XOR로 이미 C 레벨에서 돌기 때문).
    # 기본값을 여전히 0으로 두는 이유: 50 Mbps에서 C 부호기의 CPU 점유가
    # 코어의 1.4%(k=32,r=8)라 전송시간(심볼당 0.192 ms)에 비해 6% 수준이고,
    # 실장 부호기가 정해지면 그 값으로 채우는 게 맞다. 0.011을 넣고 싶으면
    # FecConfig(cpu_cost_ms_per_symbol=0.011)로 명시할 것.
    cpu_cost_ms_per_symbol: float = 0.0


@dataclass
class Decision:
    k: int
    r: int
    p_used: float
    burst_used: float
    g: float
    t_recover_ms: float
    p_fail: float
    cost: float
    table: list = field(default_factory=list)   # [(r, J, P_fail)] 보고서 그래프용

    @property
    def overhead(self) -> float:
        return self.r / self.k if self.k else 0.0


def pto_ms(srtt_ms: float | None = None, rttvar_ms: float | None = None,
           backoff: int = 0, max_ack_delay_ms: float = 0.0) -> float:
    """RFC 9002 6.2.1의 PTO. RTT 표본이 없으면 kInitialRtt를 쓴다."""
    if srtt_ms is None:
        srtt_ms = K_INITIAL_RTT_MS
        rttvar_ms = K_INITIAL_RTT_MS / 2.0
    if rttvar_ms is None:
        rttvar_ms = srtt_ms / 2.0
    base = srtt_ms + max(4.0 * rttvar_ms, 1.0) + max_ack_delay_ms
    return base * (2 ** backoff)


def choose_redundancy(k: int, p: float, burst: float, t_recover_ms: float,
                      g: float = 0.0, cfg: FecConfig | None = None,
                      r_floor: int = 0) -> Decision:
    """블록 크기 K가 주어졌을 때 비용을 최소화하는 이중화 개수 r을 고른다."""
    cfg = cfg or FecConfig()
    channel = GilbertElliott.cached(p, burst)

    # GF(256) 한계는 절대 넘을 수 없다 - r_floor보다 우선한다.
    # 하한도 같이 잘라야 한다. 안 자르면 r_floor > r_max가 되어 후보가 전부
    # 걸러지고 argmin이 비어 크래시한다(K=250, r_floor=50에서 실제로 터졌다).
    hard_cap = max(GF256_MAX_SYMBOLS - k, 0)
    r_floor = min(max(r_floor, 0), hard_cap)
    r_max = min(max(int(math.ceil(k * cfg.rho_max)), r_floor), hard_cap)

    byte_cost_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
    weight = 1.0 + cfg.beta * g

    # r 후보 전체의 P_fail을 DP 한 번으로 구한다
    curve = channel.fail_curve(k, r_max, cfg.interleave)

    best = None
    table = []
    for r, pf in enumerate(curve):
        tx = r * (byte_cost_ms + cfg.cpu_cost_ms_per_symbol)
        cost = weight * tx + pf * t_recover_ms
        table.append((r, cost, pf))
        if r < r_floor:
            continue
        # 동률이면 작은 r을 택한다(여분 바이트를 아끼는 쪽)
        if best is None or cost < best[1] - 1e-12:
            best = (r, cost, pf)

    r_star, cost, pf = best
    return Decision(k=k, r=r_star, p_used=p, burst_used=burst, g=g,
                    t_recover_ms=t_recover_ms, p_fail=pf, cost=cost, table=table)


def choose_block_size(cfg: FecConfig, rate_bps: float | None = None) -> int:
    """지연 예산이 허용하는 최대 블록 크기.

    K가 클수록 부호화 효율이 좋아지지만(같은 보호에 더 적은 이중화 비율),
    블록이 다 차야 복구가 시작되므로 지연이 늘어난다. 지연 예산이 상한을 정한다.
    """
    rate = rate_bps or cfg.rate_bps
    fit = rate * (cfg.delay_budget_ms / 1000.0) / (cfg.symbol_bytes * 8.0)
    return int(min(max(int(fit), cfg.k_min), cfg.k_max))


class AdaptiveFecController:
    """데이터 구간용 제어기. 블록마다 (K, r)을 낸다."""

    def __init__(self, cfg: FecConfig | None = None, estimator=None, congestion=None):
        from .estimator import CongestionDetector, LossEstimator
        self.cfg = cfg or FecConfig()
        self.loss = estimator or LossEstimator(z=self.cfg.risk_z)
        self.cong = congestion or CongestionDetector()
        self._last_r = 0
        self._pending_down = 0
        self.last_decision: Decision | None = None

    def next_block(self, rate_bps: float | None = None) -> Decision:
        rate = self.cfg.rate_bps if rate_bps is None else rate_bps
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("rate_bps must be finite and positive")
        # Use the current link rate for both candidate selection and reporting.
        # Keep the caller's configuration available as the default for later blocks.
        cfg = replace(self.cfg, rate_bps=rate)
        k = choose_block_size(cfg, rate)

        srtt = self.cong.srtt
        t_recover = 2.0 * srtt if srtt else pto_ms()

        d = choose_redundancy(
            k=k,
            p=self.loss.p_safe,
            burst=self.loss.burst_safe,
            t_recover_ms=t_recover,
            g=self.cong.g,
            cfg=cfg,
        )

        # ⚠️ 신뢰상한은 보호를 **늘리는 방향으로만** 작용해야 한다 (v0.2에서 발견).
        #
        # argmin_r J는 p에 대해 단조가 아니다. p가 "가망 없음" 능선을 넘으면
        # (r_max를 다 써도 P_fail ~ 1) 실패항이 상수가 되어 r*=0(포기)로
        # 무너진다. 상한점 p_safe = p + z*se가 se 팽창(표본 부족 + 버스트
        # 상관 보정) 때문에 그 능선을 넘는 일이 실제로 났다: 캐시가 p=0.2를
        # 물려준 채널(참값 10%)에서 p_safe=0.53 -> r=0 -> 블록 6개 연속 실패로
        # 후회 45%. 진짜 채널은 능선 아래에 있는데 **불확실성 헤지가 보호를
        # 꺼버린 것**이다. 상한은 헤지 수단이므로, 상한 결정이 평균 결정보다
        # 보호를 줄이면 평균 결정을 쓴다. 평균 자체가 가망 없다고 하면(둘 다
        # r=0) 포기가 맞다 - 그 판단은 상한이 아니라 평균의 몫이다.
        #
        # 능선 아래에서는 r*(p)가 (근사적으로) p에 단조 증가라 상한 결정이
        # 평균 결정보다 보호를 줄일 수 없다. 그래서 평균 재계산(DP 한 번 더)은
        # **상한 기준으로 r_max조차 가망이 없어 보일 때만** 한다 - 이 판정은
        # 이미 계산된 곡선의 끝값 P_fail(r_max)로 공짜다. 게이트 없이 매 블록
        # 재계산하면 블록당 DP가 두 배가 된다(실측 103 -> 181 ms/시뮬).
        ridge = d.table[-1][2] > 0.25 if d.table else False
        if ridge and self.loss.p_safe > self.loss.p:
            d_mean = choose_redundancy(
                k=k, p=self.loss.p, burst=self.loss.burst_safe,
                t_recover_ms=t_recover, g=self.cong.g, cfg=cfg)
            if d_mean.r > d.r:
                d = d_mean

        # 히스테리시스가 과거의 큰 r을 물고 있을 수 있으므로 현재 상한으로 자른다.
        # K는 링크 속도에 따라 줄어들 수 있어서, 자르지 않으면 rho_max나
        # GF(256) 한계(K+r<=255)를 조용히 넘긴다.
        r_cap = min(int(math.ceil(k * cfg.rho_max)), max(GF256_MAX_SYMBOLS - k, 0))
        d.r = min(self._apply_hysteresis(d.r), r_cap)
        self._last_r = d.r

        # r이 바뀌었으면 P_fail과 비용도 그 r 기준으로 다시 계산해야 한다
        d.p_fail = GilbertElliott.cached(d.p_used, d.burst_used).p_fail(
            d.k, d.r, cfg.interleave)
        byte_ms = cfg.symbol_bytes * 8.0 / rate * 1000.0
        d.cost = ((1.0 + cfg.beta * d.g)
                  * d.r * (byte_ms + cfg.cpu_cost_ms_per_symbol)
                  + d.p_fail * d.t_recover_ms)
        self.last_decision = d
        return d

    def _apply_hysteresis(self, r_target: int) -> int:
        """올릴 땐 즉시, 내릴 땐 안정이 유지될 때만. 진동을 막는다.

        내릴 때 한 칸씩만 내리면 r=32에서 r=8까지 200블록 넘게 걸려
        회복이 사실상 안 된다. 남은 차이의 일정 비율씩 줄여 기하적으로 수렴시킨다.
        """
        if r_target >= self._last_r:
            self._pending_down = 0
            self._last_r = r_target
            return r_target

        self._pending_down += 1
        if self._pending_down >= self.cfg.dwell_blocks:
            self._pending_down = 0
            gap = self._last_r - r_target
            self._last_r -= max(1, int(gap * self.cfg.decay_fraction))
        return self._last_r

    # 피드백 입력 -------------------------------------------------
    def on_feedback(self, mask: list[bool], rtt_ms: float | None = None,
                    ce_marked: bool = False) -> None:
        """ACK로 확인된 블록의 손실 마스크(True=손실)를 반영."""
        self.loss.observe_mask(mask)
        if rtt_ms is not None:
            self.cong.observe_rtt(rtt_ms)
        self.cong.observe_ecn(ce_marked)
