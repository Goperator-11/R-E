import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from afec import FecConfig, PathStatsCache, profile, shield
from afec.channel import GilbertElliott
from afec.controller import choose_redundancy, pto_ms
from afec.estimator import LossEstimator
from afec.sim import expected_handshake_ms

RESULTS = []


def verdict(tag, confirmed, detail):
    RESULTS.append((tag, confirmed))
    print("  [%s] %-46s %s" % ("CONFIRMED" if confirmed else "refuted ",
                               tag, detail))


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def h2_shield_rmax():
    print("")
    print("[H2] 핸드셰이크 r*을 J가 정하는가, 빌려온 임계값이 정하는가")
    cfg = FecConfig(rate_bps=10e6)
    prof = profile(768)
    bound_common = []
    unreported = []
    for p, L in ((0.02, 1.0), (0.05, 1.0), (0.02, 3.0), (0.05, 3.0),
                 (0.05, 6.0), (0.05, 8.0)):
        d = shield(prof, p, L, cfg)
        cap = getattr(d, "cap_bound", None)
        common = L <= 3.0
        if common and cap:
            bound_common.append((p, L))
        if cap is None:
            unreported.append((p, L))
        print("       p=%.0f%% L=%.0f : r*=%2d  상한걸림=%-5s  %s"
              % (p * 100, L, d.r, cap,
                 "흔한 구간" if common else "고버스트(모델 한계 구간)"))
    verdict("H2 흔한 구간에서 임계값이 r을 정함",
            bool(bound_common) or bool(unreported),
            "흔한 구간 절단 %d건, 미보고 %d건 (고버스트 절단은 문서화된 한계)"
            % (len(bound_common), len(unreported)))


def h10_burst_one_kills_pto():
    print("")
    print("[H10] 버스트 정보가 없을 때 PTO 항이 살아 있는가")
    from afec.channel import GilbertElliott as GE
    prof = profile(768)
    zero = []
    for p in (0.01, 0.05, 0.10):
        used = GE.for_prior(p, 1.0)
        ft = used.erasure_pmf(prof.k_client)[prof.k_client]
        d = shield(prof, p, 1.0, FecConfig(rate_bps=10e6))
        if ft <= 0.0:
            zero.append(p)
        print("       p=%.0f%% : 사전 채널 ft=%.3e  ->  shield r*=%d"
              % (p * 100, ft, d.r))
    verdict("H10 사전 경로에서 전멸확률이 0", bool(zero),
            "%d/3 조건에서 ft=0" % len(zero))


def h7_srtt_inverts_ordering():
    print("")
    print("[H7] 캐시 srtt에서 부분손실이 전멸보다 비싸지는가")
    prof = profile(768)
    bad = []
    for srtt in (10.0, 20.0, 30.0, 50.0, 66.0, 100.0, 200.0):
        d = shield(prof, 0.05, 3.0, srtt_ms=srtt)
        base = pto_ms(srtt)
        inverted = d.t_recover_ms > base + 1e-9
        if inverted:
            bad.append(srtt)
        print("       srtt=%5.0fms : PTO기저=%7.1f  유효 회복대가=%7.1f  %s"
              % (srtt, base, d.t_recover_ms, "역전!" if inverted else "정상"))
    verdict("H7 회복 대가가 PTO를 넘음", bool(bad),
            "%d/7 설정에서 역전" % len(bad))


def h1_server_two_spaces():
    print("")
    print("[H1] 서버 PTO 기준이 Initial 공간인가, 플라이트 전체인가")
    prof = profile(768)
    d = shield(prof, 0.05, 3.0, side="server")
    uses_initial = (d.k == prof.k_server_initial)
    print("       shield(side='server').k = %d  (k_server_initial=%d, "
          "k_server=%d)" % (d.k, prof.k_server_initial, prof.k_server))
    same = []
    for p, L in ((0.02, 2.0), (0.05, 3.0)):
        a = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0, p, L, 30.0)
        b = expected_handshake_ms(prof.k_client, prof.k_server, 0, 0, p, L, 30.0,
                                  server_critical=prof.k_server_initial)
        print("       p=%.0f%% L=%.0f : 플라이트전체 %.1fms  Initial공간 %.1fms  "
              "%+.0f%%" % (p * 100, L, a.mean_ms, b.mean_ms,
                           100 * (b.mean_ms - a.mean_ms) / a.mean_ms))
        if abs(b.mean_ms - a.mean_ms) < 1e-9:
            same.append((p, L))
    verdict("H1 서버 PTO 기준이 여전히 플라이트 전체",
            (not uses_initial) or bool(same),
            "shield k=%d, 해석해 무변화 %d건" % (d.k, len(same)))


def e2_prior_weight_touches_ewma():
    print("\n[E2] prior_weight가 EWMA 질량을 건드리는가 (문서화된 불변식 위반)")
    rows = []
    for w in (100.0, 80.0, 48.0, 25.0):
        e = LossEstimator(p_init=0.01, burst_init=4.0, prior_weight=w)
        rows.append((w, e._sent))
        print("       prior_weight=%6.1f -> EWMA 질량 _sent=%6.1f" % (w, e._sent))
    differs = len(set(round(s, 6) for _, s in rows)) > 1
    traj = {}
    for w in (100.0, 30.0):
        e = LossEstimator(p_init=0.01, burst_init=4.0, prior_weight=w)
        seq = []
        for _ in range(4):
            e.observe_mask([True] * 6 + [False] * 58)
            seq.append(e.p)
        traj[w] = seq
    rel = abs(traj[30.0][1] - traj[100.0][1]) / traj[100.0][1]
    print("       같은 관측 4블록 후 p_hat: w=100 -> %.4f,  w=30 -> %.4f  "
          "(블록2에서 %+.0f%% 차이)"
          % (traj[100.0][-1], traj[30.0][-1], 100 * rel))
    verdict("E2 prior_weight가 추적 속도를 바꿈", differs and rel > 0.05,
            "질량 %s, 블록2 상대차 %.0f%%"
            % ("다름" if differs else "같음", 100 * rel))


def e1_cached_burst_never_moves():
    print("\n[E1] 캐시된 버스트가 무손실 관측으로 갱신되는가")
    e = LossEstimator(p_init=0.20, burst_init=6.0, prior_weight=100.0)
    b0 = e.burst
    for _ in range(300):
        e.observe_mask([False] * 64)
    b1 = e.burst
    print("       무손실 300블록(19,200심볼) 관측 후: burst %.3f -> %.3f, "
          "p_hat %.5f" % (b0, b1, e.p))
    e2 = LossEstimator(p_init=0.20, burst_init=6.0, prior_weight=100.0)
    for _ in range(60):
        e2.observe_mask([False] * 64)
    print("       jumped=%s 인데 burst=%.3f (사전값 그대로면 리셋이 안 건드림)"
          % (e2.jumped, e2.burst))
    cfg = FecConfig(rate_bps=50e6, delay_budget_ms=20.0)
    e_stale = LossEstimator(p_init=0.0004, burst_init=6.0, prior_weight=100.0)
    e_true = LossEstimator(p_init=0.0004, burst_init=1.0, prior_weight=100.0)
    r_stale = choose_redundancy(64, e_stale.p_safe, e_stale.burst_safe,
                                40.0, 0.0, cfg).r
    r_true = choose_redundancy(64, e_true.p_safe, e_true.burst_safe,
                               40.0, 0.0, cfg).r
    print("       깨끗한 링크(p=0.04%%)에서: 낡은 burst=6 -> r=%d,  "
          "참값 burst=1 -> r=%d" % (r_stale, r_true))
    verdict("E1 캐시 버스트가 관측으로 안 지워짐",
            abs(b1 - b0) < 1e-9 and r_stale > r_true,
            "300블록 무손실에도 burst 불변, r %d vs %d" % (r_stale, r_true))


def e4_up_surprise_drops_cusum():
    print("")
    print("[E4] 상단 검정이 걸린 블록에서 하단 CUSUM이 갱신되는가")
    e = LossEstimator(p_init=0.02, burst_init=1.0, prior_weight=100.0)
    e._down_llr = 2.0
    before = e._down_llr
    fired = e._is_surprising(64, 12)
    after = e._down_llr
    print("       상단 검정 발화=%s :  S %.4f -> %.4f" % (fired, before, after))
    verdict("E4 상단 걸린 블록에서 하단 갱신 생략",
            fired and after >= before - 1e-12,
            "S가 %s" % ("그대로" if after >= before - 1e-12 else "내려감"))


def c5_default_prior_bypasses_cap():
    print("\n[C5] 캐시 미스 경로가 반출 상한을 우회하는가")
    c = PathStatsCache(prior_out_cap=50.0)
    miss = c.lookup("wifi:home", "203.0.113.10", now=0.0)
    c.store("wifi:home", "203.0.113.10", 0.05, 4.0, 1536.0, now=0.0)
    hit = c.lookup("wifi:home", "203.0.113.10", now=0.0)
    print("       prior_out_cap=50 : 미스 weight=%.1f,  히트 weight=%.1f"
          % (miss.weight, hit.weight))
    verdict("C5 기본 사전이 반출 상한을 무시", miss.weight > 50.0,
            "미스 %.0f > 상한 50" % miss.weight)


def main():
    _harden()
    print("=" * 78)
    print("E17 - 감사 주장 자체 검증 (반증 단계가 죽어 미검증 상태였음)")
    print("=" * 78)
    for fn in (h2_shield_rmax, h10_burst_one_kills_pto, h7_srtt_inverts_ordering,
               h1_server_two_spaces, e2_prior_weight_touches_ewma,
               e1_cached_burst_never_moves, e4_up_surprise_drops_cusum,
               c5_default_prior_bypasses_cap):
        try:
            fn()
        except Exception as e:
            print("   ERROR in %s: %s" % (fn.__name__, e))
            RESULTS.append((fn.__name__, None))
    conf = [t for t, ok in RESULTS if ok]
    ref = [t for t, ok in RESULTS if ok is False]
    print("")
    print("=" * 78)
    print("확인된 결함 %d개 / 반증 %d개" % (len(conf), len(ref)))
    for t in conf:
        print("   CONFIRMED: %s" % t)
    for t in ref:
        print("   refuted  : %s" % t)
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
