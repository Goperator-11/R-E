import random
import sys


def _harden_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


_harden_console()

from afec import (AdaptiveFecController, FecConfig, GilbertElliott,
                  PathStatsCache, choose_block_size, profile, shield)
from afec.controller import choose_redundancy, pto_ms
from afec.estimator import LossEstimator, CongestionDetector
from afec.sim import ChannelSampler, expected_handshake_ms, simulate_data

cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)

print("#" * 74)
print("# 장면 1. 블록 하나의 해부 - 결정이 나오기까지")
print("#" * 74)

rng = random.Random(7)
sampler = ChannelSampler(GilbertElliott.from_burst(0.05, 4.0), rng)
est = LossEstimator(p_init=0.01, z=cfg.risk_z)
for _ in range(40):
    est.observe_mask(sampler.send(64))

k = choose_block_size(cfg)
print(f"[1a] 블록 크기 K = {k}")
print(f"     링크 50Mbps x 지연예산 20ms / 심볼 1200B*8bit = "
      f"{50e6*0.02/9600:.0f}개 들어가지만 k_max=64로 상한")

print(f"[1b] 추정기 상태 (참채널: p=5%, L=4를 40블록 관측한 뒤)")
print(f"     p_hat   = {est.p:.4f}   (EWMA 손실수/전송수)")
print(f"     L_hat   = {est.burst:.2f}     (손실 구간 평균 길이)")
print(f"     n_eff   = {est.n_eff:.0f}     (쌓인 증거량, 심볼)")
infl = max(2.0 * est.burst_safe * (1.0 - est.p) - 1.0, 1.0)
print(f"     se팽창  = x{infl**0.5:.2f}    (버스트 상관 보정 sqrt(2L(1-p)-1))")
print(f"     se      = {est.se:.4f}")
print(f"     p_safe  = {est.p_safe:.4f}   (= p_hat + z({cfg.risk_z}) * se)")

rtt = 40.0
t_rec = 2.0 * rtt
d = choose_redundancy(k, est.p_safe, est.burst_safe, t_rec, 0.0, cfg)
sym_ms = cfg.symbol_bytes * 8.0 / cfg.rate_bps * 1000.0
print(f"[1c] 비용표 J(r) = r*{sym_ms:.3f}ms + P_fail(K,r)*{t_rec:.0f}ms")
print(f"     {'r':>4} {'전송비용':>10} {'P_fail':>10} {'실패비용':>10} {'J(r)':>10}")
for r, J, pf in d.table:
    if r <= 6 or abs(r - d.r) <= 3 or r == len(d.table) - 1:
        mark = "  <-- argmin" if r == d.r else ""
        print(f"     {r:>4} {r*sym_ms:>9.2f}m {pf:>10.5f} {pf*t_rec:>9.2f}m "
              f"{J:>9.2f}m{mark}")
print(f"[1d] 결정: r* = {d.r}  (이중화 {d.r}/{k} = {d.r/k:.0%}, "
      f"이 블록의 실패확률 {d.p_fail:.5f})")

print()
print("#" * 74)
print("# 장면 2. 콜드 스타트 30블록 여정 (참채널 p=5%, L=4, RTT 40ms)")
print("#" * 74)
rng = random.Random(11)
sampler = ChannelSampler(GilbertElliott.from_burst(0.05, 4.0), rng)
ctrl = AdaptiveFecController(cfg)
ctrl.cong.observe_rtt(rtt)
pending = []
LAG = 3
print(f"{'blk':>4} {'p_hat':>7} {'p_safe':>7} {'L_hat':>6} {'r':>3} "
      f"{'손실':>4} {'결과':>8} {'비고'}")
fails = saves = 0
for i in range(30):
    d = ctrl.next_block()
    mask = sampler.send(d.k + d.r)
    lost = sum(mask)
    if lost == 0:
        res = "무손실"
    elif lost <= d.r:
        res = "FEC복구"; saves += 1
    else:
        res = "실패!"; fails += 1
    note = ""
    pending.append(mask)
    if len(pending) > LAG:
        ctrl.on_feedback(pending.pop(0), rtt_ms=rtt)
        if ctrl.loss.jumped:
            note = "<< 급변 판정"
    else:
        note = "(피드백 아직)"
    print(f"{i:>4} {ctrl.loss.p:>7.4f} {ctrl.loss.p_safe:>7.4f} "
          f"{ctrl.loss.burst:>6.2f} {d.r:>3} {lost:>4} {res:>8} {note}")
print(f"  => 30블록: FEC 복구 {saves}회, 복구실패(재전송) {fails}회")

print()
print("#" * 74)
print("# 장면 3. 핸드셰이크 - 같은 식, T_recover만 다르다")
print("#" * 74)
prof = profile(768)
print(f"[3a] ML-KEM-768 하이브리드 크기 계산")
print(f"     클라 키공유 {prof.client_share}B (ML-KEM ek 1184 + X25519 32)")
print(f"     ClientHello 전체 = 350 + {prof.client_share} = {prof.client_flight}B")
print(f"     QUIC Initial 1패킷에 CRYPTO {1150}B까지 -> "
      f"{prof.k_client}패킷으로 분할  <-- 연구의 출발점")
print(f"     서버 플라이트 {prof.server_flight}B -> {prof.k_server}패킷")
print(f"[3b] 손실 검출이 왜 1초인가: RTT 표본이 없어서")
print(f"     PTO = 333 + 4*166.5 = {pto_ms():.0f}ms (RFC 9002 kInitialRtt)")
d_hs = shield(prof, p_prior=0.02, burst_prior=3.0, cfg=cfg)
d_data = choose_redundancy(prof.k_client, 0.02, 3.0, 80.0, 0.0, cfg)
print(f"[3c] 같은 비용식에 T_recover만 바꿔 넣으면 (p_prior=2%, K={prof.k_client}):")
print(f"     T_recover = 999ms (핸드셰이크) -> r* = {d_hs.r}")
print(f"     T_recover =  80ms (데이터구간) -> r* = {d_data.r}")
base = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0, 0.02, 3.0, 30.0)
fec = expected_handshake_ms(prof.k_client, prof.k_server, d_hs.r, d_hs.r,
                            0.02, 3.0, 30.0)
print(f"[3d] 효과 (해석해, 손실 2%): 평균 {base.mean_ms:.0f}ms -> {fec.mean_ms:.0f}ms"
      f" ({1-fec.mean_ms/base.mean_ms:.0%} 단축, 비용은 플라이트당 {d_hs.r*1200}B)")

print()
print("#" * 74)
print("# 장면 4. 캐시 - 두 번째 연결은 배운 채로 시작한다")
print("#" * 74)
cache = PathStatsCache()
pr1 = cache.lookup("wifi:home", "203.0.113.10", now=0.0)
print(f"[4a] 첫 방문 lookup -> source={pr1.source}, p_prior={pr1.p}, w={pr1.weight:.0f}")
r1 = simulate_data("cached", 0.05, 4.0, rtt, cfg, n_blocks=30, seed=42,
                   prior=(pr1.p, pr1.burst, pr1.weight))
p_s, b_s, ev = r1.snapshot
print(f"     30블록 후 스냅샷: p={p_s:.4f}, L={b_s:.2f}, 증거 {ev:.0f}심볼")
cache.store("wifi:home", "203.0.113.10", p_s, b_s, ev, now=30.0)
pr2 = cache.lookup("wifi:home", "203.0.113.10", now=60.0)
print(f"[4b] 재방문 lookup -> source={pr2.source}, p_prior={pr2.p:.4f}, "
      f"w={pr2.weight:.0f} (반출상한 100)")
e_cold = LossEstimator(p_init=pr1.p, burst_init=pr1.burst,
                       prior_weight=pr1.weight, z=cfg.risk_z)
e_warm = LossEstimator(p_init=pr2.p, burst_init=pr2.burst,
                       prior_weight=pr2.weight, z=cfg.risk_z)
d_cold = choose_redundancy(k, e_cold.p_safe, e_cold.burst_safe, t_rec, 0.0, cfg)
d_warm = choose_redundancy(k, e_warm.p_safe, e_warm.burst_safe, t_rec, 0.0, cfg)
print(f"[4c] 첫 블록의 결정이 달라진다:")
print(f"     콜드: p_safe={e_cold.p_safe:.4f} -> r={d_cold.r} (참값 5%에 저보호)")
print(f"     웜  : p_safe={e_warm.p_safe:.4f} -> r={d_warm.r} (첫 블록부터 근접)")
pr3 = cache.lookup("cell:450-08", "203.0.113.10", now=90.0)
print(f"[4d] 셀룰러로 이동 -> lookup source={pr3.source} "
      f"(키의 절반이 접속망이라 옛 통계를 안 읽음)")

print()
print("#" * 74)
print("# 장면 5. 급변 - 손실 0.5%에서 10%로 뛰는 순간")
print("#" * 74)
rng = random.Random(3)
ctrl = AdaptiveFecController(cfg)
ctrl.cong.observe_rtt(rtt)
s1 = ChannelSampler(GilbertElliott.from_burst(0.005, 4.0), rng)
for _ in range(60):
    d = ctrl.next_block()
    ctrl.on_feedback(s1.send(d.k + d.r), rtt_ms=rtt)
print(f"[5a] 안정 구간 60블록 학습 후: p_hat={ctrl.loss.p:.4f}, "
      f"r={ctrl.next_block().r}")
s2 = ChannelSampler(GilbertElliott.from_burst(0.10, 4.0), rng)
print(f"{'blk':>4} {'손실':>4} {'streak':>6} {'jumped':>6} {'boost':>5} "
      f"{'p_hat':>7} {'p_safe':>7} {'r':>3}")
for i in range(10):
    d = ctrl.next_block()
    mask = s2.send(d.k + d.r)
    ctrl.on_feedback(mask, rtt_ms=rtt)
    print(f"{i:>4} {sum(mask):>4} {ctrl.loss._streak:>6} "
          f"{str(ctrl.loss.jumped):>6} {ctrl.loss._boost_left:>5} "
          f"{ctrl.loss.p:>7.4f} {ctrl.loss.p_safe:>7.4f} {d.r:>3}")
print("  => 놀라움 2연속 -> 급변 확정 -> 증거 리셋 + 다음 4블록 5배 가중")
