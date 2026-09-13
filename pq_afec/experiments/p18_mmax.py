# -*- coding: utf-8 -*-
"""P18 - m_max 상한이 손해인가: 고정팔 m=1..4 를 직접 재서 모형을 검증한다.

왜 이 단계가 필요한가
---------------------
정책의 상한은 `m_max=2` 이고 확률표(pfail_table.go)도 m<=2 까지만 담는다.
그런데 모형(Python 은 표 없이 직접 계산하므로 m>2 도 낸다)은 상한을 4 로
풀면 **20/24 조건에서 이득, 최대 +17.27 ms** 라고 예측한다:

    cert 9000 · L=1 · p=0.15 :  m=2 -> m=4   +17.27 ms
    cert 4032 · L=3 · p=0.15 :  m=2 -> m=4   +10.82 ms

⚠️ 이것은 **모형 예측이고 실측이 아니다.** 그리고 2026-08-23 에 우리는
   모형이 m 을 과대평가하던 결함을 하나 잡았다(패리티가 ACK 를 만든다고
   본 것 — 그 수정으로 격자 24.5% 의 선택이 바뀌었다). 같은 실수를
   반복하지 않으려면 **표를 늘리기 전에 실측으로 확인**해야 한다.

다행히 표 확장 없이 검증할 수 있다: 표는 정책(auto)만 쓰고, 고정팔은
클라이언트가 m 개 패리티를 만들 뿐이다(parseFecBlock 이 m<=8 을 받는다).

무엇을 재나
-----------
모형이 가장 큰 이득을 예측하는 자리에서 고정팔 m=1..4 를 나란히 돌린다.
순서 효과는 p17 에서 배운 **라틴 방격**으로 통제한다(각 팔이 각 자리를
정확히 한 번씩). 자리 효과가 재려는 이득보다 크면 판정 불능으로 드러낸다.

통과 기준
---------
  1. 모든 팔·블록이 측정됐다
  2. 서버 통계가 실제로 있었다
  3. 팔들이 서로 갈린다 (안 갈리면 아래가 공허하다)
  4. 자리 효과가 모형이 예측한 이득보다 작다 (판정할 수 있다)
  5. ⭐ 모형이 예측한 순서(m=4 가 m=2 보다 빠르다)가 실측에서도 성립
  6. ⭐ 이득 크기가 모형 예측의 절반 이상 (부호만이 아니라 규모도)
  7. 복구 CRC 실패 0
"""
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from padfec import policy as POL                 # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2

N_DEFAULT = 250
# 🩸 2026-08-29 - **N_PRECISE 를 정의한다.** 형제 단계(p3·p11·p15·p17)는 전부
#    `--precise` 로 정밀도 판을 고를 수 있는데 여기만 없어서, 정밀도 실행을
#    걸 때마다 사람이 `PADFEC_P18_N` 을 손으로 줘야 했다. 2026-08-28 에
#    그걸 잊어서 **p18 이 기본값으로 돌 뻔했다** — 하필 m=1~4 를 직접 재는,
#    다중 소거 복구(2 단계) 검증의 핵심 단계다.
#    값 750 = 기본값의 3 배(p17 과 같은 비율). 2026-08-29 실행이 이 값으로
#    돌아 검사 5(m=4 가 m=2 보다 빠른 것이 잡음과 구별된다)를 4/5 조건에서
#    통과시켰다 - 그 아래는 못 판정한다는 뜻이므로 더 줄이면 안 된다.
N_PRECISE = 750
N = int(os.environ.get("PADFEC_P18_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))

ARMS = [1, 2, 3, 4]          # 고정 m

# 🩸 2026-08-25 - 조건마다 **N 을 따로** 준다. 옛 코드는 하나의 N 을
#    모든 조건에 썼는데, 조건마다 필요 표본이 10 배 넘게 다르다
#    (결정적 자리는 100 판이면 끝나고, 손실 기반 자리는 수천 판).
#    같은 N 을 쓰면 한쪽은 낭비하고 다른 쪽은 판정 불능이 된다.
#
#    조건 선택도 바꿨다. 옛 두 자리는 **틀린 C(1146)** 로 고른
#    자리였다(21 차 수정). 바른 C=1448 로 1,152 자리를 다시 훑으면
#    그 둘은 417 위·557 위이고, 이득이 각각 +2.38 / +0.77 ms 라
#    잡음에 묻힌다(필요 표본 팔당 11,343 / 3,014 - 22 차 수정).
#
#    바른 C 에서 이득이 가장 큰 자리는 **무손실 + 큰 cert** 다:
#      **실측** 무손실 1-RTT 한계 cert (이분탐색, n=20/점, 100 B 해상도):
#          m=1 10,855   m=2 14,601   m=3 16,125 이상   m=4 16,125 이상
#      그리고 이 스택의 천장: 클라이언트 CRYPTO 버퍼 16,384 B 라
#      cert 16,125~16,187 위로는 **어떤 m 으로도 악수가 안 된다**
#      (CRYPTO_BUFFER_EXCEEDED). 처음엔 모형이 말한 cert 18,000 을
#      골랐다가 **네 팔 전부 0/60 실패**로 그 천장을 발견했다.
#    -> 자리는 **정책이 실제로 갈리는 곳**으로 잡는다. cert 15,400 은
#       m_max=2 정책도 combo(패딩+m=2)로 1-RTT 를 내므로 m_max 의
#       값어치를 재는 자리가 아니다(처음에 그걸로 골랐다가 고쳤다).
#       m_max=2 는 cert 15,860 까지 버티다 그 위에서 **포기**한다.
#    -> cert 16,000: m_max=2 정책은 none(2-RTT), m_max=3 은 m=3(1-RTT).
#       실측으로도 m=2 106.3 ms / m=3 53.7 ms (각 25/25, 무손실).
#       천장(16,125)까지 125 B 여유 - 좁지만 이 크기는 직접 재서
#       악수가 되는 것을 확인했다.
#       p12 가 검증한 절벽과 같은 기전이라 기전도 알려져 있다.
# (이름, cert, 버스트, 손실%, 업링크, N/팔/블록)
# 🩸 2026-08-26 - **네 번째 조건(대역 2 Mbps)을 더했다.** 위 세 조건은
#    업링크가 전부 0(무제한)이었다. 그런데 모형이 틀린 곳은 **대역이 걸린
#    자리뿐**이었고(무제한 실측은 오차 -1.9~-6.9 ms 로 잘 맞는다), 그래서
#    "고정팔을 직접 재서 모형을 검증한다"는 이 단계가 정작 그 축을 한 번도
#    안 밟았다. m=1 의 증폭 신용 경주(오차 69.2 ms)를 p17 만 신고하고 있었고
#    p18 은 통과하고 있었다 - 통과가 아니라 사각지대였다.
#    자리는 p17 과 같은 운용점(cert 9000 · 2 Mbps · 손실 2%)으로 잡는다.
#    거기서 실측은 m1 121.31 / m2 70.36 이고, 차이 50.95 ms = **정확히 한 왕복**이다.
# 🩸 2026-08-26 (2) - **다섯 번째 조건: 대역 × 고손실.** 네 조건을 표로 놓고
#    보면 모서리 하나가 비어 있었다.
#
#                     무제한          2 Mbps
#        저손실          -          임계위·2Mbps
#        고손실   임계위·무버스트        **없음**
#
#    그런데 지금 남은 결함이 정확히 그 빈칸에 있다. 모형이 m=3 을 고르는데
#    실측 최선은 m=2 이고, 그 벌점이 **손실이 클수록 커진다**:
#        2 Mbps 손실 2%   m2 70.36 / m3 70.50   (0.14 ms)
#        2 Mbps 손실 15%  m2 86.46 / m3 88.25   (1.79 ms)   <- p17
#        임계위/손실5%     m2 51.06 / m3 52.46   (1.40 ms)   <- p11 수렴후
#    p11 과 p17 이 서로 모르는 채 같은 방향을 가리키는데, "고정팔을 직접
#    재서 모형을 검증한다"는 이 단계는 그 모서리를 안 밟고 있다. 네 번째
#    조건을 더할 때와 **같은 이유**다 - 통과가 아니라 사각지대다.
#
#    기전 가설(재서 확인할 것): `critical_path_bytes` 는 m>=2 에서 앞선
#    패리티 하나만 임계경로로 센다(qamp.go flushFlight 로 검증된 식이라
#    맞다). 그런데 **뒤따르는 패리티는 업링크를 실제로 점유한다** - 2 Mbps
#    에서 하나당 5.32 ms. 손실이 커서 복구·재전송이 필요해질수록 그 점유가
#    물리므로 벌점이 손실과 함께 커진다. m=1..4 를 이 자리에서 직접 재면
#    **m 마다 얼마씩 붙는지**가 나오고, 그게 모형에 넣을 상수다.
#    (짐작해서 넣지 않는다 - 2026-08-26 의 q(d) 표가 그 교훈이다.)
CONDS = [
    ("m_max2포기·무손실", 16000, 1.0, 0.0, 0.0, max(40, N // 6)),
    ("임계사이·버스트3", 4032, 3.0, 15.0, 0.0, N * 3),
    ("임계위·무버스트", 9000, 1.0, 15.0, 0.0, N),
    ("임계위·2Mbps", 9000, 1.0, 2.0, 2.0, N),
    ("임계위·2Mbps·손실15", 9000, 1.0, 15.0, 2.0, N),
]


import blockstat as BST  # noqa: E402


def mean(v):
    return (sum(v) / len(v)) if v else None


def se(v):
    """평균의 표준오차."""
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    var = sum((x - mu) ** 2 for x in v) / (len(v) - 1)
    return math.sqrt(var / len(v))


def gain_ci(a, b, alpha):
    """두 팔 평균 차(a-b)와 그 신뢰반폭.

    🩸 2026-08-25 - 이 함수가 없어서 검사 5 가 **부호만 보고** 합격을
       줬다. 원자료로 재 보니 두 조건의 이득이 **둘 다 0 을 포함**한다
       (+1.43 [-2.78,+5.65] / +9.31 [-4.82,+23.44], n=1000/팔).
       즉 통과의 근거가 잡음이었다. 동전을 던져도 절반은 통과한다.
    """
    sa, sb = se(a), se(b)
    if sa is None or sb is None:
        return None, None
    z = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    return (mean(a) - mean(b)), z * math.sqrt(sa * sa + sb * sb)


def model_j(cert, L, p, up, m):
    """이 조건에서 m 을 강제했을 때 모형이 말하는 J.

    🩸 2026-08-25 - C 가 `1146` 으로 박혀 있었다. 우리가 재는 그룹은
       X25519MLKEM768 이고 실측 C 는 1448 이다(1146 은 어느 그룹도
       아니다). natural_k 가 1 vs 2 로 갈려 **모형이 k=1 로** 계산했고,
       그래서 m=2->m=4 예측 이득이 +17.27 ms 로 부풀었다. 바른 C 로는
       +2.38 ms 이고 실측 +1.43 ms 가 그 60% 다 - 검사 6 이 잡은 것은
       알고리즘이 아니라 이 상수였다. padbed.measured_C 로 읽는다.
    """
    d = POL.decide_v2(C=B.measured_C(GROUP), cert_bytes=cert,
                      rtt_ms=RTT_MS, p=p / 100.0,
                      burst=L, s0_base=POL.S0_BASE_MLKEM,
                      c_pkt=POL.C_PKT_POLICY_DEFAULT, W=1280,
                      max_steps=2, m_max=max(m, 1), uplink_mbps=up)
    cs = [c["j_ms"] for c in d["candidates"] if c["m"] == m]
    return min(cs) if cs else None


def run_cond(name, cert, L, loss, up, n_conn, jr):
    key = "%s|c%d|L%g|l%g|u%g|n%d" % (name, cert, L, loss, up, n_conn)
    if jr.has(key):
        return jr.get(key)
    acc = {m: [] for m in ARMS}
    seg, err = [], ""
    p, sp = B.start_server(cert, fec="on")
    try:
        # 라틴 방격: 블록마다 순서를 한 칸씩 돌린다 -> 각 팔이 각 자리 1 번
        for blk in range(len(ARMS)):
            B.set_netem(RTT_MS / 2.0, loss_c2s=loss, burst_len=L,
                        rate_up_mbit=up)
            order = ARMS[blk:] + ARMS[:blk]
            for pos, m in enumerate(order):
                # 🩸 2026-08-26 - 대역이 걸리면 gap 을 벌린다. gap 8 ms 로
                # 붙여 돌리면 앞 연결의 *뒤따르는* 패리티가 다음 연결의 첫
                # 비행 뒤에 줄을 서서, m 이 클수록 불리해진다(2 Mbps 에서
                # m3-m2 가 gap 8 이면 +5.11 ms, gap 600 이면 +0.02 ms).
                # 큐를 다음 연결에 떠넘긴 것이지 악수의 비용이 아니다.
                # p17_adaptive_value.py 의 같은 주석과 같은 근거다.
                rows, cs, e = B.run_client(GROUP, n_conn, fec="on", m=m,
                                           gap_ms=(50 if up > 0 else 8),
                                           timeout_s=10,
                                           expect_k=K, uplink_mbps=up)
                if e:
                    err = e
                ok = [x["ms"] for x in rows if x.get("ok")]
                acc[m].extend(ok)
                seg.append({"block": blk, "m": m, "pos": pos,
                            "n": len(rows), "ok": len(ok), "mean": mean(ok)})
                print("   %-16s blk%d m=%d(자리%d) 평균 %.2f"
                      % (name, blk, m, pos, mean(ok) or -1), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    rec = {"cond": name, "cert": cert, "burst": L, "loss": loss,
           "uplink": up, "n_per_block": n_conn,
           "arms": {str(m): {"n": len(v), "mean": mean(v),
                             "p50": B.pctl(v, 0.5), "ms": v}
                    for m, v in acc.items()},
           "segments": seg, "srv_crc_fail": ss.get("recover_crc_fail"),
           "srv_stats_present": bool(ss), "err": err}
    if not err and bool(ss):
        jr.record(key, rec)
    return rec


def pos_effect(rec):
    """자리 효과 — 라틴 방격이라 자리별 평균의 산포가 순수 순서 효과다."""
    by = {}
    for s in rec["segments"]:
        if s["mean"] is not None:
            by.setdefault(s["pos"], []).append(s["mean"])
    v = [mean(x) for x in by.values() if x]
    return (max(v) - min(v)) if len(v) >= 2 else 0.0


def main():
    B.harden()
    B.require_root()
    B.setup()
    fp = code_fingerprint(["experiments/p18_mmax.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p18_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "group": GROUP, "n": N, "arms": ARMS,
           "rows": [], "verdict": [], "checks": []}
    checks = out["checks"]

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-60s %s" % ("통과" if ok else "실패", name, detail),
              flush=True)

    print("=" * 100)
    print("P18 m_max 상한 검증 — 고정팔 m=1..4 직접 측정 "
          "(조건별 n: %s)" % ", ".join("%s %d" % (c[0], c[5])
                                       for c in CONDS))
    print("=" * 100)
    for name, cert, L, loss, up, n_conn in CONDS:
        print()
        print("### %s (cert %d, 버스트 %g, 손실 %g%%, 업링크 %g, n=%d/팔/블록)"
              % (name, cert, L, loss, up, n_conn))
        out["rows"].append(run_cond(name, cert, L, loss, up, n_conn, jr))

    for rec in out["rows"]:
        am = rec["arms"]
        if not all(am[str(m)]["mean"] is not None for m in ARMS):
            continue
        obs = {m: am[str(m)]["mean"] for m in ARMS}
        mdl = {m: model_j(rec["cert"], rec["burst"], rec["loss"],
                          rec["uplink"], m) for m in ARMS}
        pred_gain = (mdl[2] - mdl[4]) if (mdl[2] and mdl[4]) else None
        # 🩸 2026-08-25 - 이득에 **신뢰구간**을 붙인다. 조건이 K 개이므로
        #    Bonferroni 로 α=0.05/K (p4 와 같은 규칙).
        _alpha = 0.05 / max(1, len(CONDS))
        obs_gain, half = gain_ci(am["2"]["ms"], am["4"]["ms"], _alpha)
        # 구간이 0 을 배제하려면 표본이 몇이어야 하나 (반폭 ∝ 1/sqrt(n))
        n_now = min(len(am["2"]["ms"]), len(am["4"]["ms"]))
        # 2026-08-27 - 필요 표본을 **판정에 실제로 쓴 반폭**으로 센다.
        #    옛 코드는 Welch 반폭(half)으로 셌는데 판정은 아래에서
        #    max(Welch, 방격)으로 한다. 그러면 "이만큼 더 재면 판정된다"가
        #    거짓이 된다 - 그 표본을 채워도 넓은 쪽 자에 걸려 여전히
        #    판정 불능이다. 두 수는 같은 자를 가리켜야 한다.
        #    (_half_use 는 아래에서 정해지므로 여기서는 미룬다.)
        # 🩸 2026-08-27 - **설계대로 분석한다.** 라틴 방격은 자리를 상쇄
        #    하도록 짠 설계인데, 지금까지 대조는 두 표본(Welch)으로만 쟀다.
        #    experiments/blockstat.py 머리말에 근거가 있다. 두 가지를 얻는다.
        #      (가) 설계가 실제로 균형인가 - 이게 깨지면 추정량이 **편향**된다.
        #           자리 효과가 큰 것과는 전혀 다른 문제다.
        #      (나) 자리를 흡수한 대조와 그 신뢰반폭.
        #    두 반폭 중 **넓은 쪽**으로 유의성을 판정한다. 어느 쪽이 옳은지
        #    블록 4 개로는 가릴 수 없기 때문이다(블록 기반 SE 는 자유도 3 이라
        #    그 자체가 흔들린다 - 실제로 조건마다 비가 0.38~3.18 배로 튄다).
        #    **넓은 쪽을 쓰는 것은 자를 넓히는 것이 아니라 두 자 중 관대하지
        #    않은 쪽을 고르는 것이다.**
        _cells = [(sg["m"], sg["pos"]) for sg in rec["segments"]
                  if sg["mean"] is not None]
        _bal_ok, _bal_why = BST.balance(_cells)
        _an = BST.latin_anova([{"arm": sg["m"], "pos": sg["pos"],
                                "block": sg["block"], "value": sg["mean"]}
                               for sg in rec["segments"]
                               if sg["mean"] is not None])
        _bd, _bhalf = BST.contrast(_an, 2, 4, _alpha) if _an.get("ok")             else (None, None)
        _half_use = max(half or 0.0, _bhalf or 0.0)
        n_need = (int(math.ceil(n_now * (_half_use / abs(obs_gain)) ** 2))
                  if (_half_use and obs_gain) else None)
        out["verdict"].append({
            "cond": rec["cond"], "uplink": rec["uplink"],
            "obs": obs, "model": mdl,
            "pred_gain_m2_to_m4": pred_gain, "obs_gain_m2_to_m4": obs_gain,
            "obs_gain_ci95_half": half, "alpha": _alpha,
            "n_per_arm": n_now, "n_needed_per_arm": n_need,
            # 설계 기반 분석 (blockstat)
            "design_balanced": bool(_bal_ok), "design_note": _bal_why,
            "blocked_gain_m2_to_m4": _bd,
            "blocked_ci_half": _bhalf,
            "blocked_mse": _an.get("mse"),
            "blocked_df_resid": _an.get("df_resid"),
            "pos_f": _an.get("pos_f"),
            "pos_ss_share": _an.get("pos_share"),
            "ci_half_used": _half_use,
            "significant": bool(_half_use > 0 and abs(obs_gain) > _half_use),
            "pos_effect_ms": pos_effect(rec)})
        v = out["verdict"][-1]
        print()
        print("   [%s] 실측 %s" % (rec["cond"],
              "  ".join("m%d %.2f" % (m, obs[m]) for m in ARMS)))
        print("   %s 모형 %s" % (" " * len(rec["cond"]),
              "  ".join("m%d %.2f" % (m, mdl[m] or -1) for m in ARMS)))
        # 🩸 2026-09-01/09-07 - 화면의 구간은 **판정에 쓴 반폭**(ci_half_used =
        #    max(Welch, 라틴 방격))으로 찍는다. 옛 코드는 Welch 반폭만 찍어서
        #    08-29 로그의 「+0.03 ± 0.60」이 실제 판정 반폭 0.89 와 달랐고,
        #    그 수가 보고서로 옮겨질 뻔했다. Welch 값은 옆에 따로 적는다.
        print("   m=2 -> m=4 이득:  모형 %+.2f ms  vs  **실측 %+.2f ms**  "
              "(구간 [%+.2f, %+.2f] = ±%.2f 판정반폭, Welch ±%.2f, 자리효과 %.2f)"
              % (pred_gain or 0, obs_gain,
                 obs_gain - (v["ci_half_used"] or 0),
                 obs_gain + (v["ci_half_used"] or 0),
                 v["ci_half_used"] or 0,
                 v["obs_gain_ci95_half"] or 0,
                 v["pos_effect_ms"]))
        if not v["significant"]:
            print("   ⚠ 이 이득은 **0 과 구별되지 않는다**. 판정하려면 "
                  "팔당 약 %s 판이 필요하다 (지금 %d)."
                  % (v["n_needed_per_arm"], v["n_per_arm"]))

    print()
    print("-" * 100)
    nseg = len(CONDS) * len(ARMS) * len(ARMS)
    got = sum(len(r["segments"]) for r in out["rows"])
    add("1. 모든 팔·블록이 측정됐다", got == nseg
        and all(s["mean"] is not None for r in out["rows"]
                for s in r["segments"]), "%d/%d 구간" % (got, nseg))
    add("2. 서버 통계가 실제로 있었다",
        all(r["srv_stats_present"] for r in out["rows"]) and out["rows"],
        "%d/%d" % (sum(1 for r in out["rows"] if r["srv_stats_present"]),
                   len(out["rows"])))
    vs = out["verdict"]
    spread = [max(v["obs"].values()) - min(v["obs"].values()) for v in vs]
    add("3. 팔들이 서로 갈린다", vs and min(spread) > 0.5,
        "팔 산포 %s" % ["%.2f" % s for s in spread] if vs else "자료 없음")
    # 🩸 2026-08-27 - **검사 4 의 자를 세 번째로 바꾼다. 이번에는 자가
    #    아니라 자의 *대상*을 바꾼다.**
    #
    #    옛 자 (25 일 이전): 자리 효과 vs 모형 예측 이득
    #      -> 예측이 0 에 가까운 조건에서 아무것도 말하지 않았다.
    #    그다음 자 (25 일): 자리 효과 vs 측정 신뢰반폭
    #      -> **거꾸로다.** 반폭은 표본이 늘수록 줄어드니 **정밀하게 잴수록
    #         실패한다.** 원자료가 그대로 보여 준다 - 비율로 가장 나쁜
    #         조건(자리/이득 214%)을 통과시키고 무시해도 되는 조건(1.4%)을
    #         실패시켰다.
    #
    #    세 번째로 바꾸는 것이라 근거를 분명히 한다. **자리 효과가 큰 것은
    #    그 자체로 결함이 아니다.** 라틴 방격이 균형이면 팔 효과 추정량은
    #    자리 효과가 아무리 커도 **편향되지 않는다**(표준 실험계획법).
    #    자리 효과가 하는 일은 정밀도를 깎는 것뿐이고 그것은 이미 신뢰구간이
    #    말한다 - 같은 것을 두 번 세면 안 된다.
    #
    #    그러므로 여기서 물어야 할 것은 **"설계가 실제로 균형인가"** 다.
    #    이건 자료가 아니라 설계의 성질이라 결정적으로 판정된다. 깨져 있으면
    #    (예: 한 팔이 어떤 자리를 두 번 겪으면) 그때는 진짜로 편향이 생긴다.
    #    자리 효과의 크기는 **진단으로 남긴다** — F 와 제곱합 몫으로.
    #    상쇄했다고 없던 일로 하지 않는다는 이 저장소의 규칙 그대로다.
    ok4 = bool(vs) and all(v.get("design_balanced") for v in vs)
    add("4. 라틴 방격이 균형이다 (팔 효과 추정이 자리에 편향되지 않는다)",
        ok4,
        " | ".join("%s: %s | 자리 F=%.2f 제곱합몫 %.1f%% (진단)"
                   % (v["cond"], v.get("design_note", "?"),
                      v.get("pos_f") or -1,
                      100.0 * (v.get("pos_ss_share") or 0.0)) for v in vs)
        if vs else "자료 없음")

    # 🩸 2026-08-27 신설 - 두 신뢰반폭이 크게 갈리면 그 자체가 정보다.
    #    갈린다는 것은 **블록 사이의 흔들림이 연결 사이의 흔들림으로
    #    설명되지 않는다**는 뜻이고, 그때는 넓은 쪽(=보수적인 쪽)을 써야 한다.
    #    위 verdict 가 이미 넓은 쪽을 쓴다. 여기서는 그 사실을 드러낸다.
    _rat = [((v.get("blocked_ci_half") or 0) / v["obs_gain_ci95_half"])
            for v in vs if v.get("obs_gain_ci95_half")]
    add("4b. 두 신뢰반폭(연결 기준 vs 블록 기준)을 나란히 보고한다",
        True,
        " | ".join("%s: Welch %.2f vs 방격 %.2f (%.2f배)"
                   % (v["cond"], v["obs_gain_ci95_half"] or -1,
                      v.get("blocked_ci_half") or -1,
                      ((v.get("blocked_ci_half") or 0)
                       / v["obs_gain_ci95_half"])
                      if v.get("obs_gain_ci95_half") else float("nan"))
                   for v in vs) if _rat else "자료 없음")

    # 🩸 2026-08-25 - 옛 검사 5 는 `obs_gain > 0`, 즉 **부호만** 봤다
    #    (29 차에서 유의성 검정으로 바꿈). 그런데 27 차 연습 실행에서
    #    또 다른 문제가 드러났다: **"모형이 틀렸다"와 "우리가 덜 쟀다"를
    #    같은 실패 통에 넣고 있었다.** 손실 기반 조건이 표본 부족으로
    #    판정 불능이면 검사 전체가 실패로 찍혀서, 결정적 자리에서 얻은
    #    유의한 확인(+52.39 ± 0.32, 예측의 105%)이 요약에서 사라진다.
    #    -> 판정 가능한 조건만 판정한다. 다만 (a) 하나도 판정 가능하지
    #       않으면 **실패**(공허 방지), (b) 판정 불능 조건은 필요
    #       표본과 함께 detail 에 그대로 남긴다 - 숨기지 않는다.
    dec = [v for v in vs if v["significant"]]
    und = [v for v in vs if not v["significant"]]
    ok5 = bool(dec) and all(v["obs_gain_m2_to_m4"] > 0 for v in dec)
    add("5. ⭐ m=4 가 m=2 보다 빠른 것이 **잡음과 구별된다** (판정 가능 %d/%d 조건)"
        % (len(dec), len(vs)), ok5,
        # 🩸 2026-09-07 - detail 의 ± 도 **판정에 쓴 반폭**(ci_half_used)이다.
        #    옛 detail 은 Welch 반폭을 찍어 판정과 다른 자를 보여 줬다.
        (" | ".join("%s: %+.2f ± %.2f 유의"
                    % (v["cond"], v["obs_gain_m2_to_m4"],
                       v["ci_half_used"] or 0) for v in dec)
         or "판정 가능한 조건이 하나도 없다 = 이 검사가 공허하다")
        + ("  || 판정 불능: " + "; ".join(
            "%s %+.2f ± %.2f (팔당 %s 판 필요, 지금 %d)"
            % (v["cond"], v["obs_gain_m2_to_m4"],
               v["ci_half_used"] or 0, v["n_needed_per_arm"],
               v["n_per_arm"]) for v in und) if und else ""))

    # 🩸 옛 검사 6 은 `실측 >= 0.5 x 예측` 한쪽만 봤다. 예측이 0 에
    #    가까우면 무엇이든 통과하고, **모형이 과소평가할 때 못 잡는다**
    #    (버스트 자리: 예측 +0.77 vs 실측 +9.31 = 1203%). 양쪽으로 본다.
    #    단 예측이 측정 반폭보다 작으면 비율이 무의미하므로 판정 불능.
    def _ratio_ok(v):
        """비율을 판정할 수 있는가. None 이면 판정 불능.

        두 가지가 다 필요하다: 실측 이득이 잡음과 구별되고(significant),
        모형 예측도 측정 반폭보다 커야 한다. 둘 중 하나라도 아니면
        비율은 잡음/잡음 이라 뜻이 없다.
        """
        pg = v["pred_gain_m2_to_m4"]
        og = v["obs_gain_m2_to_m4"]
        if not v["significant"]:
            return None
        if not pg or abs(pg) < (v["obs_gain_ci95_half"] or 0):
            return None
        return 0.5 <= (og / pg) <= 2.0

    _r = [_ratio_ok(v) for v in vs]
    _judged = [(v, x) for v, x in zip(vs, _r) if x is not None]
    # 판정 가능한 것이 하나도 없으면 실패 - 통과시키면 공허하다.
    ok6 = bool(_judged) and all(x is True for _v, x in _judged)
    add("6. ⭐ 이득 크기가 모형 예측의 0.5~2 배 (판정 가능 %d/%d 조건)"
        % (len(_judged), len(vs)), ok6,
        " | ".join("%s: 실측 %+.2f / 예측 %+.2f (%s)"
                   % (v["cond"], v["obs_gain_m2_to_m4"],
                      v["pred_gain_m2_to_m4"] or 0,
                      ("판정 불능 - " + ("실측이 잡음과 구별 안 됨"
                                       if not v["significant"]
                                       else "예측이 측정 반폭보다 작다"))
                      if x is None else
                      "%.0f%%" % (100 * v["obs_gain_m2_to_m4"]
                                  / (v["pred_gain_m2_to_m4"] or 1)))
                   for v, x in zip(vs, _r)) if vs else "자료 없음")
    # 🩸 2026-08-26 신설. 위 검사 5·6 이 재는 것은 **절벽에서 m_max 를
    #    올리는 값어치**(m=2 -> m=4)다. 대역이 걸린 자리에서는 m 을 올려도
    #    임계경로 바이트가 안 늘어(criticalPathBytes: 앞선 패리티 하나뿐)
    #    그 이득이 원래 0 이라, 그 자리를 같은 통에서 재면 아무 말도 못 한다.
    #    대역 축이 실제로 무는 곳은 **m=1 대 m=2** 다.
    #
    #    주장: m=1 은 패리티가 원본 **뒤**라 증폭 신용이 서버의 송신 결정보다
    #    늦게 닿는다. 그래서 왕복을 하나 통째로 더 쓴다(RTT 50 ms). m>=2 는
    #    앞선 패리티가 결정적으로 신용을 주므로 안 그렇다.
    #    이 검사는 **모형과 실측이 같은 쪽을 같은 크기로** 말하는지 본다.
    #    (고치기 전 모형은 m1 을 53.0 ms 로 봐서 m2 보다 **싸다**고 했다 -
    #     실측은 121.3 vs 70.4 로 정반대였고 오차가 68.3 ms 였다.)
    shaped = [v for v in vs if v.get("uplink", 0) > 0]
    _bad9, _det9 = [], []
    for v in shaped:
        og = v["obs"][1] - v["obs"][2]
        pg = v["model"][1] - v["model"][2] if v["model"][1] else None
        ratio = (og / pg) if (pg and abs(pg) > 1e-9) else None
        _det9.append("%s: 실측 m1-m2 %+.2f / 모형 %+.2f (%s)"
                     % (v["cond"], og, pg or 0,
                        ("%.0f%%" % (100 * ratio)) if ratio else "판정불능"))
        if ratio is None or not (og > 0 and pg > 0 and 0.5 <= ratio <= 2.0):
            _bad9.append(v["cond"])
    add("8. ⭐ 대역 조건에서 m=1 이 잃는 왕복을 모형이 낸다 "
        "(m1-m2 부호·크기, 조건 %d 개)" % len(shaped),
        bool(shaped) and not _bad9,
        " | ".join(_det9) if shaped else "대역이 걸린 조건이 하나도 없다")

    crc = sum(r["srv_crc_fail"] or 0 for r in out["rows"])
    add("7. 복구 CRC 실패 0", crc == 0, "총 %d 건" % crc)

    # 🩸 2026-08-25 - cert 18,000 은 p2 스윕 상한(16,000) 밖이라 이
    #    테스트베드에서 **처음 재는 크기**다. 서버가 그 크기를 실제로
    #    만들었는지, 그리고 무손실 자리가 정말 무손실인지 확인한다.
    #    (이게 없으면 '작아진 cert 를 재고 절벽을 못 봤다'와
    #     '절벽이 없다'를 구별할 수 없다.)
    det = [r for r in out["rows"] if r["loss"] == 0]
    _t = [(r["cond"], r["arms"]["2"]["mean"], r["arms"]["4"]["mean"])
          for r in det if r["arms"]["2"]["mean"] and r["arms"]["4"]["mean"]]
    add("8. 무손실 자리에서 m=2 가 실제로 2-RTT 다 (절벽을 재고 있다)",
        bool(_t) and all(a > 1.5 * RTT_MS for _c, a, _b in _t),
        " | ".join("%s: m2 %.1f ms (1.5RTT=%.0f 초과여야)"
                   % (c, a, 1.5 * RTT_MS) for c, a, _b in _t)
        or "무손실 조건 없음")
    add("9. 그 자리에서 m=4 는 1-RTT 다 (절벽을 넘었다)",
        bool(_t) and all(b <= 1.5 * RTT_MS for _c, _a, b in _t),
        " | ".join("%s: m4 %.1f ms" % (c, b) for c, _a, b in _t)
        or "무손실 조건 없음")

    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(checks)))
    _fname = ("smoke_" if N < N_DEFAULT else "") + "p18_mmax.json"
    print("saved: %s" % B.save(_fname, out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
