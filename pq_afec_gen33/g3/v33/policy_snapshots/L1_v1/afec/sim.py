"""시뮬레이터 - 알고리즘이 실제로 이기는지 숫자로 확인한다.

두 개의 실험이 있다.
  A. 핸드셰이크: ML-KEM 플라이트가 완료되기까지 걸리는 시간
  B. 데이터 구간: 같은 양의 데이터를 보내는 데 걸리는 총 시간

B의 지표를 '총 시간'으로 잡은 이유: 이중화를 너무 많이 넣으면 전송할 심볼이
늘어 시간이 늘고, 너무 적게 넣으면 복구 실패로 재전송 지연이 붙어 또 늘어난다.
양쪽 실패가 같은 저울에 올라가므로 한 숫자로 공정하게 비교된다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .channel import GilbertElliott
from .controller import (AdaptiveFecController, FecConfig, choose_block_size,
                         choose_redundancy, pto_ms)
from .estimator import CongestionDetector, LossEstimator


class ChannelSampler:
    """GE 채널을 시간축으로 이어서 굴린다(블록 경계에서 상태가 초기화되지 않음)."""

    def __init__(self, channel: GilbertElliott, rng: random.Random):
        self.ch = channel
        self.rng = rng
        self.reset_state()

    def reset_state(self) -> None:
        """채널 상태를 정상분포에서 다시 뽑는다.

        PTO로 1초 가까이 쉬었다가 재전송할 때 이걸 안 하면 **직전 실패를
        만든 Bad 상태를 그대로 물려받아** 재시도가 거의 확실히 또 실패한다.
        실제로는 버스트가 수 ms~수십 ms 규모라 1초 뒤엔 상관이 사라진다.
        이 처리를 빼먹었을 때 몬테카를로 평균이 해석해의 2.5배로 부풀었다.
        """
        self.state = 1 if self.rng.random() < self.ch.stationary[1] else 0

    def send(self, n: int) -> list[bool]:
        """n개 심볼을 보내고 손실 여부 목록을 반환(True=손실)."""
        out = []
        for _ in range(n):
            pl = self.ch.p_bad if self.state == 1 else self.ch.p_good
            out.append(self.rng.random() < pl)
            q = self.ch.q_gb if self.state == 0 else self.ch.q_bg
            if self.rng.random() < q:
                self.state ^= 1
        return out


class LossTrace:
    """실측 손실 마스크. netem 위로 쏜 순번 UDP 프로브의 도착 기록이다.

    ⚠️ 이 클래스는 **파일을 열지 않는다.** afec/ 라이브러리는 파일·네트워크·
    프로세스에 손대지 않는 게 규칙이고(verify.py의 발자국 테스트가 강제),
    마스크 읽기는 experiments/ 하네스가 한다. 여기는 바이트만 받는다.
    """

    __slots__ = ("bitmap", "n", "label")

    def __init__(self, bitmap: bytes, n: int, label: str = "trace"):
        if n > len(bitmap) * 8:
            raise ValueError("bitmap too short for n=%d" % n)
        self.bitmap = bitmap
        self.n = n
        self.label = label

    @classmethod
    def from_bits(cls, lost_flags, label: str = "trace") -> "LossTrace":
        """lost_flags[i] = True면 i번 패킷이 손실. (비트맵은 '도착=1' 규약)"""
        flags = list(lost_flags)
        bm = bytearray((len(flags) + 7) // 8)
        for i, lost in enumerate(flags):
            if not lost:
                bm[i >> 3] |= 1 << (i & 7)
        return cls(bytes(bm), len(flags), label)

    def lost(self, i: int) -> bool:
        i %= self.n
        return not (self.bitmap[i >> 3] >> (i & 7)) & 1

    @property
    def loss_rate(self) -> float:
        return sum(1 for i in range(self.n) if self.lost(i)) / self.n


class TraceSampler:
    """ChannelSampler와 같은 인터페이스로 **실측 트레이스**를 흘린다.

    정책 비교의 공정성 문제가 하나 있다: 정책마다 블록당 심볼 수(k+r)가
    달라서, 트레이스를 그냥 순서대로 소비하면 정책들이 **서로 다른 구간**을
    보게 되고 비교가 오염된다(이중화를 많이 넣은 정책이 트레이스를 빨리
    소진해 뒷부분의 다른 손실 국면을 만난다).

    그래서 기본 모드는 `positional`이다: 블록 i는 트레이스의 고정 창
    [i*stride, i*stride + k + r)만 쓴다. stride는 어떤 정책도 창을 넘지
    않도록 k + r_max로 잡는다. **모든 정책이 블록 i에서 같은 채널 구간을
    본다**는 뜻이고, 차이는 오직 "그 구간에서 몇 개를 쓰느냐"가 된다.

    mode='sequential'은 옛 방식(순서대로 소비). 단일 정책의 현실성 확인용.
    """

    def __init__(self, trace: LossTrace, rng: random.Random,
                 stride: int = 0, mode: str = "positional",
                 offset: int = 0):
        self.trace = trace
        self.rng = rng
        self.stride = max(1, stride)
        self.mode = mode
        self.offset = offset % trace.n
        self.pos = self.offset
        self.block = 0

    def reset_state(self) -> None:
        """재시도 전 상관을 끊는 자리. 트레이스에서는 임의 지점으로 점프한다."""
        self.pos = self.rng.randrange(self.trace.n)

    def start_block(self, index: int) -> None:
        if self.mode == "positional":
            self.pos = (self.offset + index * self.stride) % self.trace.n
        self.block = index

    def send(self, n: int) -> list[bool]:
        out = [self.trace.lost(self.pos + i) for i in range(n)]
        self.pos = (self.pos + n) % self.trace.n
        return out


def runs_of_losses(mask: list[bool]) -> list[int]:
    """연속 손실 구간 길이 목록. 버스트 길이 추정에 쓴다."""
    runs, cur = [], 0
    for lost in mask:
        if lost:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return runs


# ---------------------------------------------------------------- A. 핸드셰이크

@dataclass
class HandshakeAnalytic:
    mean_ms: float
    stall_prob: float
    f_client: float
    f_server: float
    bytes_sent: int


def expected_handshake_ms(k_client: int, k_server: int, r_client: int, r_server: int,
                          p: float, burst: float, rtt_ms: float,
                          max_attempts: int = 6, interleave: int = 1,
                          symbol_bytes: int = 1200, ack_partial: bool = True,
                          srtt_ms: float | None = None,
                          server_critical: int | None = None) -> HandshakeAnalytic:
    """핸드셰이크 완료 시간의 기댓값을 닫힌 형태로 계산한다.

    몬테카를로로 재면 평균이 **꼬리에 먹힌다.** PTO가 999 -> 1998 -> 3996 ms로
    배로 늘기 때문에, 확률 1%짜리 3연속 실패가 평균을 통째로 흔든다.
    2만 회를 돌려도 x25519가 ML-KEM보다 느리게 나오는 역전이 실제로 생겼다.
    그래서 평균은 해석적으로 구하고, 시뮬레이션은 교차검증과 분위수 확인에만 쓴다.

    ⚠️ 실패의 대가는 한 가지가 아니다 (2026-08-14 선행연구 대조에서 정밀화).
    v0.1은 "조각 1개만 잃어도 PTO ~999ms"로 모델링했는데, 이는 과장이다:
    Initial 키는 클라이언트 DCID에서 유도되므로 서버는 ClientHello 조각
    하나만 받아도 복호·ACK할 수 있고(quicly #639에서 구현 확인), 그 ACK으로
    클라이언트가 RTT 표본과 시간 임계 손실 검출을 얻어 **부분 손실의 회복은
    약 2*RTT**다. ~999ms 정지가 맞는 경우는 **플라이트 전멸**(버스트가 인접
    데이터그램을 같이 삼킬 때 - GE 모델이 이 확률을 정확히 준다), 돌아오는
    ACK 손실, 부분 CH를 ACK하지 않는 서버 구현(ack_partial=False)이다.

        f  = P[손실 > r]        (복구 실패)
        ft = P[전 심볼 손실]     (전멸 - PTO 경로, 백오프 배증)
        fp = f - ft             (부분 실패 - 시간임계 재전송, ~2*RTT)
        E[지연] = sum_{a=1..A} f^a * [ (fp/f)*2*RTT + (ft/f)*base*2^(a-1) ]

    ack_partial=False면 fp가 ft로 합쳐져 v0.1 공식으로 정확히 환원된다.
    srtt_ms: 캐시가 이전 연결의 srtt를 물려주면(RFC 9002 6.2.2 재개 연결
    조항) PTO 기저가 999ms보다 훨씬 작아진다 - 캐시의 또 다른 배당.
    """
    ch = GilbertElliott.cached(p, burst)
    base = pto_ms(srtt_ms)
    t_fast = 2.0 * rtt_ms          # 시간임계 검출 + 재전송 왕복 근사
    total = rtt_ms
    fails = []
    # 🩸 H1 (2026-08-18 감사): 서버 플라이트에서 "ACK 이 아예 없다(=PTO)"는
    # 사건은 플라이트 전체 손실이 아니라 **Initial 공간(ServerHello) 전체 손실**
    # 이다. 클라이언트는 ServerHello 없이 Handshake 키를 못 만들어 그 공간의
    # 패킷을 복호도 ACK 도 못 하기 때문이다. 전자로 계산하면 전멸 확률을
    # 3.4~8배 과소평가한다(profile(768), p=2~5%).
    # server_critical 을 주면 그 개수의 전멸 확률을 ft 로 쓴다.
    for idx, (k, r) in enumerate(((k_client, r_client), (k_server, r_server))):
        n = k + r
        pmf = ch.erasure_pmf(n, interleave)
        f = sum(pmf[r + 1:])
        if not ack_partial:
            ft = f
        elif idx == 1 and server_critical:
            m = min(server_critical + r, n)
            ft = min(ch.erasure_pmf(m, interleave)[m], f)
        else:
            ft = pmf[n]
        fp = f - ft
        if f > 0.0:
            total += sum((f ** a) * ((fp / f) * t_fast
                                     + (ft / f) * base * (2 ** (a - 1)))
                         for a in range(1, max_attempts + 1))
        fails.append(f)

    stall = 1.0 - (1.0 - fails[0]) * (1.0 - fails[1])
    nbytes = (k_client + r_client + k_server + r_server) * symbol_bytes
    return HandshakeAnalytic(mean_ms=total, stall_prob=stall,
                             f_client=fails[0], f_server=fails[1],
                             bytes_sent=nbytes)


@dataclass
class HandshakeResult:
    mean_ms: float
    p95_ms: float
    stall_rate: float       # PTO를 한 번이라도 맞은 연결 비율
    bytes_sent: int


def simulate_handshake(k_client: int, k_server: int, r_client: int, r_server: int,
                       p: float, burst: float, rtt_ms: float,
                       trials: int = 20000, seed: int = 1,
                       symbol_bytes: int = 1200,
                       ack_partial: bool = True,
                       retry_decorrelate: bool = True,
                       trace: "LossTrace | None" = None) -> HandshakeResult:
    """retry_decorrelate: 재시도 시점에 버스트 상관이 끊겼다고 볼 것인가.

    v0.1은 True 고정("1초 뒤엔 상관이 사라진다")이었는데, **1차 실측 스윕
    (sweep1, 2026-08-13)이 이 가정을 흔들었다**: netem 버스트 조건에서 같은
    평균 손실률인데 평균 완료시간이 균일 대비 1.8~6.0배, p99가 7~10초
    (RTO 백오프 3~4연쇄 = 재시도가 반복해서 죽음). 버스트 에피소드가
    타임아웃 간격보다 길면 재시도도 같은 버스트에 삼켜진다.
    False면 재시도가 채널 상태를 물려받는 비관 경계를 잰다. 실측 대응은
    netem 버스트 파라미터 확인 후 (docs/실측대조_스윕1.md 참고).
    """
    rng = random.Random(seed)
    ch = None if trace is not None else GilbertElliott.from_burst(p, burst)
    times, stalls, total_bytes = [], 0, 0

    for _ in range(trials):
        if trace is not None:
            # 매 시행마다 트레이스의 임의 지점에서 시작 = 실제 채널의
            # 임의 시점에 핸드셰이크를 시도하는 것과 같다
            sampler = TraceSampler(trace, rng, mode="sequential",
                                   offset=rng.randrange(trace.n))
        else:
            sampler = ChannelSampler(ch, rng)
        t = rtt_ms          # 손실이 없을 때의 기준 시간(1-RTT 핸드셰이크)
        stalled = False
        sent = 0

        for k, r in ((k_client, r_client), (k_server, r_server)):
            attempt = 0
            while True:
                mask = sampler.send(k + r)
                sent += (k + r) * symbol_bytes
                n_lost = sum(mask)
                if n_lost <= r:
                    break
                if ack_partial and n_lost < k + r:
                    # 일부 도착 -> 생존 조각의 ACK으로 RTT 표본 + 시간임계
                    # 검출 -> 약 2*RTT 뒤 재전송 (해석해와 같은 근사)
                    t += 2.0 * rtt_ms
                else:
                    # 전멸(또는 부분 ACK 없는 서버) -> PTO 만료까지 대기
                    t += pto_ms(backoff=attempt)
                if retry_decorrelate:
                    sampler.reset_state()  # 쉬는 동안 버스트 상관이 끊긴다
                stalled = True
                attempt += 1
                if attempt > 6:          # 현실적으로는 연결 포기
                    break

        times.append(t)
        stalls += 1 if stalled else 0
        total_bytes += sent

    times.sort()
    return HandshakeResult(
        mean_ms=sum(times) / len(times),
        p95_ms=times[int(0.95 * (len(times) - 1))],
        stall_rate=stalls / trials,
        bytes_sent=total_bytes // trials,
    )


# ---------------------------------------------------------------- B. 데이터 구간

@dataclass
class DataResult:
    label: str
    total_ms: float
    goodput_mbps: float
    overhead: float
    block_fail_rate: float
    mean_r: float
    # 연결이 끝난 시점의 추정기 스냅샷 (p, burst, 관측 증거량).
    # 캐시에 store() 할 값이다. 적응형 계열 정책에서만 채워진다.
    snapshot: tuple | None = None


def simulate_data(policy: str, p: float, burst: float, rtt_ms: float,
                  cfg: FecConfig, n_blocks: int = 400, seed: int = 7,
                  static_ratio: float = 0.25, prior=None,
                  trace: "LossTrace | None" = None) -> DataResult:
    """policy: 'none'|'static'|'adaptive'|'warm'|'cached'|'oracle'|'rquic'

    'rquic' = rQUIC(Garrido et al., GLOBECOM 2019)의 임계값 휴리스틱 근사.
    선행연구 비교 기준선이다: 잔여손실(복구 실패율)을 창 평균해 임계 gamma와
    비교, 이중화율을 곱셈 증감(delta)한다. 원 논문 값 gamma=1%, delta=0.33,
    창 T=3*RTT(약 9블록)를 따른다. "임계값 휴리스틱 vs 비용 최소화"의
    후회 비교가 이 정책의 존재 이유다.

    'warm' = 'adaptive'와 같은데 **참값 사전값으로 시작**한다(가중치는 기본 100).
    캐시가 완벽할 때의 기준선이다. 짧은 연결에서 적응형이 왜 손해인지,
    그리고 그 손해가 캐시로 얼마나 회수되는지를 재기 위한 정책이다.

    'cached' = **현실적인 캐시**. prior=(p, burst, weight) 또는
    afec.cache.Prior를 받아 그대로 워밍 스타트한다. warm과 달리
    사전값이 오래됐거나 아예 틀렸을 수 있고, 증거 가중치가 클 수도 있다.
    캐시가 틀렸을 때의 회복 속도를 재는 것이 이 정책의 존재 이유다.

    trace: 주면 **GE 모델 대신 실측 손실 마스크**를 흘린다(TraceSampler).
    p/burst 인자는 그때도 'oracle' 정책의 참값 입력으로 계속 쓰이므로,
    트레이스에서 잰 실측 (손실률, 버스트)를 넣어야 공정한 상한이 된다.
    """
    rng = random.Random(seed)
    symbol_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
    t_recover = 2.0 * rtt_ms
    k = choose_block_size(cfg)

    if trace is not None:
        r_max = min(max(int(round(k * cfg.rho_max)), 1), max(255 - k, 1))
        sampler = TraceSampler(trace, rng, stride=k + r_max,
                               offset=rng.randrange(trace.n))
    else:
        ch = GilbertElliott.from_burst(p, burst)
        sampler = ChannelSampler(ch, rng)

    ctrl = None
    if policy in ("adaptive", "warm", "cached"):
        if policy == "cached":
            if prior is None:
                raise ValueError("policy='cached' needs prior=(p, burst, weight)")
            pp = getattr(prior, "p", None)
            if pp is None:
                pp, pb, pw = prior
            else:
                pb, pw = prior.burst, prior.weight
            est = LossEstimator(p_init=pp, burst_init=pb, prior_weight=pw,
                                z=cfg.risk_z)
        else:
            p_init = p if policy == "warm" else 0.005
            est = LossEstimator(p_init=p_init, z=cfg.risk_z)
            if policy == "warm":
                est.burst = burst
        ctrl = AdaptiveFecController(cfg, est, CongestionDetector())
        ctrl.cong.observe_rtt(rtt_ms)

    total_ms = 0.0
    sent_symbols = source_symbols = 0
    fails = 0
    r_sum = 0

    # rquic 기준선의 상태 (원 논문: gamma=1%, delta=0.33, 창 T=3*RTT)
    rq_ratio = 0.1
    rq_window: list[bool] = []
    rq_win_blocks = max(3, int(round(3.0 * rtt_ms
                                     / max(k * symbol_ms, 1e-6))))

    # 피드백은 1 RTT 뒤에 온다. 블록 하나 전송시간으로 환산해 지연을 준다.
    block_ms = k * symbol_ms
    lag = max(1, int(round(rtt_ms / max(block_ms, 1e-6))))
    pending: list[tuple[int, list[bool]]] = []

    for block_index in range(n_blocks):
        if trace is not None:
            # 모든 정책이 블록 i에서 같은 트레이스 구간을 보게 고정한다
            sampler.start_block(block_index)
        if policy == "none":
            r = 0
        elif policy == "static":
            r = max(1, int(round(k * static_ratio)))
        elif policy == "oracle":
            r = choose_redundancy(k, p, burst, t_recover, 0.0, cfg).r
        elif policy == "rquic":
            if len(rq_window) >= rq_win_blocks:
                residual = sum(rq_window) / len(rq_window)
                rq_ratio *= (1.0 + 0.33) if residual > 0.01 else (1.0 - 0.33)
                rq_ratio = min(max(rq_ratio, 1.0 / k), cfg.rho_max)
                rq_window.clear()
            r = max(1, int(round(k * rq_ratio)))
        else:
            r = ctrl.next_block().r

        mask = sampler.send(k + r)
        n_lost = sum(mask)
        failed = n_lost > r

        sent_symbols += k + r
        source_symbols += k
        r_sum += r
        total_ms += (k + r) * symbol_ms
        if failed:
            fails += 1
            total_ms += t_recover
        if policy == "rquic":
            rq_window.append(failed)

        if ctrl is not None:
            pending.append((k + r, mask))
            if len(pending) > lag:
                _, old = pending.pop(0)
                # 혼잡 여부: 이 시뮬레이터의 손실은 링크 오류로 둔다(RTT 팽창 없음).
                ctrl.on_feedback(old, rtt_ms=rtt_ms)

    source_bits = source_symbols * cfg.symbol_bytes * 8.0
    return DataResult(
        label=policy,
        total_ms=total_ms,
        goodput_mbps=source_bits / (total_ms / 1000.0) / 1e6,
        overhead=(sent_symbols - source_symbols) / source_symbols,
        block_fail_rate=fails / n_blocks,
        mean_r=r_sum / n_blocks,
        snapshot=ctrl.loss.snapshot() if ctrl is not None else None,
    )
