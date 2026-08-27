# -*- coding: utf-8 -*-
"""P17 - 적응의 **값어치**: 손실률이 변할 때 auto 가 최선 고정팔을 이기는가.

왜 이 단계가 필요한가
---------------------
p11·p15 는 조건마다 손실률을 **고정**해 두고 auto 와 최선 고정팔을 비교한다.
손실률이 고정이면 최선 고정팔이 언제나 존재하므로 **적응은 그것을 따라잡을
수 있을 뿐 이길 수 없다.** 그래서 두 단계의 후회는 구조적으로 >= 0 이고,
"적응이 필요한가"에는 답하지 못한다. 답하는 것은 "적응이 해를 끼치지 않는가"뿐.

적응이 이기려면 두 가지가 동시에 있어야 한다.
  (a) 손실률이 **변한다** — 아니면 고정팔 하나가 늘 최적이다.
  (b) 패리티가 **공짜가 아니다** — 아니면 최대 m 이 늘 최적이라 (a) 도 무의미.
      이 테스트베드는 기본이 대역 무제한이라 t_tx=0 이고 (b) 가 성립하지 않는다.
      p16 이 잰 그 사실이 여기서 실험 설계로 돌아온다.

🩸 2026-08-26 — 증폭신용 경주를 넣어 모형을 수리한 뒤, 위 (a)(b) 를 수로
   옮겨 **설계 공간을 전수로 훑었다.** 오라클 이득 = (구간마다 최선을 고르는
   정책) 대비 (최선 고정팔 하나) 의 차이, 50:50 스케줄:

       cert 3,000~30,000 (250 B 간격) × 업링크 0.25~10 Mbps 및 무제한
       × RTT 20/50/100/200 × 손실쌍 24 종  = 23,328 조합

   나온 것이 이 단계의 방향을 바꾼다:

   1. **FEC 가 왕복을 사는 영역(1-RTT 가 잡히는 자리)에서는 오라클 이득이
      어느 RTT 에서도 정확히 0.00 ms 다.** 이유가 분명하다 - 패리티가 일단
      왕복을 사면 그 값어치(≈1 RTT)가 패리티 하나의 직렬화(수 ms)를 압도
      하므로 **m 은 클수록 좋고, 손실률이 변해도 그 답이 안 바뀐다.**
      적응할 대상 자체가 없다.
   2. 이득이 나는 자리는 전부 **cert 가 커서 왕복을 못 사는 영역**이다
      (RTT 50 최대 1.77 ms, RTT 200 최대 7.10 ms). 거기서 갈리는 것은
      "왕복" 이 아니라 업링크 직렬화뿐이라 이 프로젝트의 본 현상이 아니다.
   3. 그래서 운용점을 그리로 옮기지 **않았다.** 지금 운용점(cert 9,000 ·
      2 Mbps · RTT 50)은 m>=2 가 1-RTT 를 잡아 J 가 100 -> 56 ms 로 떨어지는
      자리이고, 그것이 이 연구의 헤드라인이다. 1.8 ms 짜리 곁가지를 위해
      44 ms 짜리 본 현상을 버리는 것은 거꾸로 가는 것이다.

   결론: 이 단계는 이제 **"적응이 이긴다"를 보이는 실험이 아니라, 적응이
   벌 수 있는 것이 얼마인지를 재서 보고하는 실험**이다. 검사 6 이 그 값을
   재고, 지금 운용점에서 그 값은 0 이다. 그 0 이 결과다 - 자를 흔들어
   초록으로 만들 일이 아니다.
   (남은 연구 방향: 적응의 값어치는 손실률이 아니라 **버스트성**이나
    **RTT 변동**에 있을 수 있다. 이 단계는 손실률만 흔든다.)

1 차 실행(2026-08-23, n=200)이 실제로 그것을 보였다:

    10Mbps  auto 60.304  최선 고정 m1 60.692   이득 **+0.388 ms**
    무제한   auto 57.902  최선 고정 m1 57.486   이득 **-0.416 ms**  <- 해롭다

두 수가 p11 이 독립적으로 잰 탐색세(+0.48~0.51)와 맞물린다:
  무제한 = 선택개선 0    - 탐색세 0.42 = -0.42   (실측 -0.416)
  10Mbps = 선택개선 +0.8 - 탐색세 0.42 = +0.38   (실측 +0.388)

⚠️ 그러나 1 차 설계는 **판정할 수 없었다** — 팔마다 전체 스케줄을 따로 돌려
   팔 간 간격이 ~54 초였고, 블록 간 표류가 1.67~3.29 ms 로 재려는 이득
   (0.4 ms)보다 컸다. 아래 2 차 설계가 그것을 고친다.

어떻게 재나 (2 차 설계)
-----------------------
**구간 안에서 팔을 인터리브하고, 자리를 라틴 방격으로 회전한다.**

  - 서버를 한 번만 띄우고 구간마다 네 팔을 연속으로 돌린다
    -> 팔 간 간격 54 초 -> ~14 초, 실행 시간도 절반
  - 구간 인덱스마다 순서를 한 칸씩 돌린다(회전). 구간이 팔 수와 같으므로
    **각 팔이 모든 자리를 정확히 한 번씩** 겪는다. 단순 뒤집기로는 안 된다 —
    auto 는 자리 0·3 만, m0 은 1·2 만 겪어 자리 효과가 팔에 균등하지 않다.
  - 자리 효과(순서 표류)를 직접 재서 이득과 나란히 보고한다. 표류가 이득보다
    크면 **판정 불능으로 드러낸다** — 통과시키지 않는다.

auto 의 목적지 캐시는 실행 내내 유지된다(그래야 적응을 잰다).

통과 기준
---------
  1. 모든 팔·구간이 측정됐다        2. 서버 통계가 실제로 있었다
  3. 대역이 실제로 걸렸다 (저손실 구간에서 m2 가 m1 보다 비싸다)
  4. 손실 전환이 실제로 일어났다
  5. 고정팔들이 서로 갈린다 (안 갈리면 아래가 공허하다)
  6. **자리 효과가 이득보다 작다** (아니면 판정 불능)
  7. ⭐ 대역 있는 경로에서 auto 가 최선 고정팔을 이긴다
  8. [부정] 무제한에서는 auto 가 최선 고정팔을 이기지 못한다
     (적응이 값을 못 하는 자리 — 1 차 실측은 오히려 탐색세만큼 해로웠다)
  9. 복구 CRC 실패 0
"""
import os
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
# 🩸 2026-08-25 - 2955 -> 9000. 옛 자리는 **두 구간의 최적 m 이 둘 다 1**
#    이라 따라갈 것이 없었다(검사 6 이 계속 실패로 신고하고 있었다).
#    m_max=3 이 되면서 같은 2% <-> 15% 스케줄로 갈리는 자리가 생겼다:
#        cert 7,200~12,000 · 업링크 1~3 Mbps 에서 m=1 <-> m=3
#    9000 은 그 cert 구간의 가운데다. 손실 전이는 3%~5% 사이라
#    스케줄 2%/15% 가 양쪽에 여유를 두고 걸친다.
CERT = 9000          # 갈리는 구간(7,200~12,000)의 가운데.
CACHE = "/tmp/padfec/p17_cache.json"

N_DEFAULT = 150
N_PRECISE = 450
N = int(os.environ.get("PADFEC_P17_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))

# (이름, fec, m)  auto 는 정책이 고른다
# 🩸 2026-08-25 - m3 을 더했다. 새 운용점의 고손실 구간 목표가 m=3 인데
#    고정팔에 m=3 이 없으면 "auto 가 최선 고정팔만큼 하는가"를 잴 수
#    없다 - 비교 대상이 아예 없으면 후회가 실제보다 좋게 나온다.
ARMS = [("auto", "auto", 1), ("m0", "off", 0), ("m1", "on", 1),
        ("m2", "on", 2), ("m3", "on", 3)]

# 손실 스케줄 한 사이클. 새 운용점(cert 9000 · 2 Mbps)에서 모형이 짚는
# 전이는 손실 3% ~ 5% 사이다(m=1 -> m=3). 2% / 15% 는 양쪽에 여유를 두고
# 걸친다.
#
# 🩸 2026-08-25 - 닫힘 조건을 적어 둔 주석이 **틀렸다.** 실제 코드는
#    `r = rot[loss] % len(ARMS)` 로 손실률마다 사이클당 한 번씩 돌리므로,
#    닫히려면 **CYCLES == len(ARMS)** 여야 한다(구간 수는 관계없다).
#    우연히 4 == 4 였을 뿐이라 아무도 몰랐다. 팔이 5 개가 됐으니 맞춘다.
SCHEDULE = [(2.0, N), (15.0, N)]
CYCLES = len(ARMS)  # 라틴 방격 닫힘: 손실률마다 각 팔이 각 자리 정확히 1 번

# 🩸 2026-08-25 - 10 Mbps -> 2 Mbps. 모형상 두 손실 구간의 최적 m 이
#    갈리는 대역은 **1~3 Mbps 뿐**이다(0.5 이하도, 4 이상도 안 갈린다).
#    10 Mbps 에서는 어떤 cert 에서도 안 갈려서 이 실험이 성립하지
#    않았다. 무제한 조건은 **음성 대조로 그대로 둔다** - 거기서는
#    여전히 안 갈리고, 그것이 "패리티가 공짜면 적응할 것이 없다"를
#    드러낸다(검사 9).
CONDS = [
    ("2Mbps", 2.0, POL.UPLINK_CONSTRAINED_MBPS),
    ("무제한", 0.0, POL.UPLINK_UNSHAPED),
]


def mean(v):
    return (sum(v) / len(v)) if v else None


def run_interleaved(cond_name, rate, up_policy, jr):
    """구간 안에서 팔을 인터리브하고 자리를 회전한다(라틴 방격)."""
    # 🩸 2026-08-26 - **연결 간격을 대역에 맞춘다.** gap 8 ms 로 연결을 붙여
    #    돌리면 앞 연결의 *뒤따르는* 패리티가 다음 연결의 첫 비행 뒤에 줄을
    #    선다. m 이 클수록 꼬리가 길어 더 밀리므로, 대역 제한이 걸린 조건에서
    #    **높은 m 에 불리한 편향**이 생긴다. 2 Mbps 에서 직접 쟀다
    #    (cert 9000, 팔당 120 연결, m3-m2 평균차):
    #
    #        gap  8 ms -> +5.11 ms   <- 패리티 하나 직렬화(5.32)와 같다
    #        gap 50 ms -> -1.04 ms
    #        gap600 ms -> +0.02 ms
    #
    #    즉 이건 악수의 비용이 아니라 **다음 연결에 떠넘긴 큐**다. gap>=50 에서
    #    사라진다. 이 편향 때문에 "auto 가 m=3 을 과선택한다"는 오진을 한 번
    #    했다 - 큐를 비우고 재니 2 Mbps 최선은 m3(71.00) 이었고 m2 는 73.13
    #    이었다. 무제한은 큐가 안 쌓이므로 8 ms 그대로 둔다(실행 시간).
    gap_ms = 50 if rate > 0 else 8
    key = "%s|latin|n%d|c%d|g%d" % (cond_name, N, CYCLES, gap_ms)
    if jr.has(key):
        return jr.get(key)
    try:
        os.unlink(CACHE)
    except OSError:
        pass
    acc = {a: [] for a, _f, _m in ARMS}
    seg, err = [], ""
    # C1: PADFEC_FEEDBACK=1 이면 서버·클라 양쪽에 -feedback 을 준다.
    # 끄고 켠 결과를 나란히 둬야 "피드백이 적응률을 고쳤다"고 말할 수 있다.
    FB = ["-feedback"] if os.environ.get("PADFEC_FEEDBACK") == "1" else []
    p, sp = B.start_server(CERT, fec="on", extra=FB)
    try:
        # 🩸 회전 카운터는 **손실률마다 따로** 센다. 하나로 세면 손실률이
        #    2 개일 때 같은 손실률의 회전이 0,2,0,2 로 건너뛰어 방격이 닫히지
        #    않는다(각 팔이 두 자리만 겪는다 - 고치기 전 실제로 그랬다).
        rot = {}
        for cyc in range(CYCLES):
            for loss, n_conn in SCHEDULE:
                B.set_netem(RTT_MS / 2.0, loss_c2s=loss, rate_up_mbit=rate)
                r = rot.get(loss, 0) % len(ARMS)
                rot[loss] = rot.get(loss, 0) + 1
                order = ARMS[r:] + ARMS[:r]
                for pos, (aname, fec, m) in enumerate(order):
                    extra = (["-cache", CACHE, "-probe-every", "20"]
                             if fec == "auto" else []) + FB
                    rows, cs, e = B.run_client(
                        GROUP, n_conn, fec=fec, m=max(m, 1), gap_ms=gap_ms,
                        timeout_s=10, expect_k=K, extra=extra,
                        uplink_mbps=up_policy)
                    if e:
                        err = e
                    ok = [x["ms"] for x in rows if x.get("ok")]
                    acc[aname].extend(ok)
                    # 🩸 2026-08-23 - **선택을 기록한다.** 시간으로 적응을
                    #    판정하려면 팔당 46,398 연결이 필요하다(부트스트랩
                    #    직접 계산, 현재 1,200 - 39 배). 고손실 구간의 PTO
                    #    분산 때문이다. 그런데 재려는 것은 "정책이 채널 변화를
                    #    따라가는가"이고, 그것은 **선택**을 보면 잡음 없이
                    #    판정된다 - 시간을 거칠 필요가 없다.
                    mu = [x.get("m_used") for x in rows
                          if x.get("ok") and x.get("m_used") is not None]
                    seg.append({"cycle": cyc, "loss": loss, "arm": aname,
                                "pos": pos, "n": len(rows), "ok": len(ok),
                                "mean": mean(ok), "m_used": mu})

                print("   %-8s cyc%d 손실%-5g  %s" % (
                    cond_name, cyc, loss,
                    "  ".join("%s(자리%d) %.2f" % (s["arm"], s["pos"],
                                                 s["mean"] or -1)
                              for s in seg[-len(ARMS):])), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    rec = {"cond": cond_name,
           "arms": {a: {"n": len(v), "mean": mean(v), "p50": B.pctl(v, 0.5),
                        "p95": B.pctl(v, 0.95), "ms": v}
                    for a, v in acc.items()},
           "segments": seg, "srv_recovered": ss.get("recovered"),
           "srv_crc_fail": ss.get("recover_crc_fail"),
           "srv_stats_present": bool(ss), "err": err}
    if not err and bool(ss):
        jr.record(key, rec)
    return rec


def optimal_m(loss_pct, up):
    """모형이 말하는 이 구간의 최적 m. 정책 구현이 따라가야 할 목표값."""
    # 🩸 2026-08-25 - C 가 `1146` 으로 박혀 있었다(실측 1448, 그리고
    #    1146 은 어느 그룹의 값도 아니다). 여기서는 다행히 목표 m 이
    #    양쪽 다 1 이라 결론이 안 바뀌었지만, 모형은 k=1 로 돌고
    #    있었다. 측정 파일에서 읽는다 (padbed.measured_C 주석 참고).
    d = POL.decide_v2(C=B.measured_C(GROUP), cert_bytes=CERT,
                      rtt_ms=RTT_MS,
                      p=loss_pct / 100.0, burst=1.0, s0_base=POL.S0_BASE_MLKEM,
                      c_pkt=POL.C_PKT_POLICY_DEFAULT, W=1280, max_steps=2,
                      m_max=POL.M_MAX_DEFAULT, uplink_mbps=up)
    return d["choice"]["m"]


def allowed_by_loss(rec, tol=1.0):
    """구간별 **실측** 허용집합 = {최선 고정팔과 tol ms 안에 드는 팔}.

    🩸 2026-08-26. 여기가 이 단계의 자를 바꾸는 자리다. 옛 정답지는
       `optimal_m()`, 즉 **모형의 argmin** 이었다. 두 가지가 동시에 잘못됐다.

       (1) 모형이 틀린 자리에서는 폐루프가 맞혀도 실패로 찍힌다. 2026-08-26
           의 모형 수리 전에 이 단계가 정확히 그렇게 실패하고 있었다.
       (2) 더 나쁜 것은 argmin 이 **이산 라벨**이라는 점이다. 수리된 모형을
           설계 공간 전체(cert 3,000~30,000 · 업링크 0.25~10 Mbps · RTT
           20~200 · 손실쌍 24 종)로 훑어 보면, 두 손실 구간의 최적 m 이
           갈리는 자리에서도 **1·2 위의 차이가 0.29 ms** 다. 이 단계의
           측정 분해능은 신뢰반폭 1~2 ms 이므로, 정답지가 잡음에 뒤집힌다.
           즉 어떤 운용점을 골라도 적중률은 **못 재는 자**였다.

       p11 이 2026-08-21 에 같은 문제를 이미 풀었다(허용집합 = 최선과 1 ms
       안). 같은 관례를 쓴다 - 정답지를 모형에서 떼어 **실측**에 붙이고,
       "최선과 잡음 안에서 같은 팔" 을 맞힌 것으로 센다.
    """
    out = {}
    for loss, _n in SCHEDULE:
        fixed = {}
        for a, _f, _m in ARMS:
            if a == "auto":
                continue
            v = [s["mean"] for s in rec["segments"]
                 if s["arm"] == a and s["loss"] == loss
                 and s["mean"] is not None]
            if v:
                fixed[a] = mean(v)
        if not fixed:
            out[loss] = None
            continue
        b = min(fixed.values())
        out[loss] = {"means": {a: round(v, 3) for a, v in fixed.items()},
                     "best": min(fixed, key=lambda a: fixed[a]),
                     "allowed": sorted(a for a, v in fixed.items()
                                       if v - b < tol)}
    return out


def oracle_gain_ms(alw):
    """**적응이 벌 수 있는 것의 상한** — 구간마다 최선을 고르는 오라클이
    하나의 최선 고정팔보다 버는 ms (구간 가중치는 스케줄과 같은 50:50).

    이 단계가 묻는 것("적응이 이기는가")의 분자가 바로 이 값이다. 이것이
    탐색세(p11 실측 0.42~0.51 ms)보다 작으면 **어떤 정책도 못 이긴다** -
    최적 m 라벨이 갈리는지 아닌지와 무관하게. 그래서 검사 6 의 자를
    라벨에서 이 값으로 바꿨다.
    """
    ls = [l for l, _n in SCHEDULE]
    if any(alw.get(l) is None for l in ls):
        return None
    arms = set(alw[ls[0]]["means"])
    for l in ls[1:]:
        arms &= set(alw[l]["means"])
    if not arms:
        return None
    oracle = sum(min(alw[l]["means"][a] for a in arms) for l in ls) / len(ls)
    fixed = min(sum(alw[l]["means"][a] for l in ls) / len(ls) for a in arms)
    return fixed - oracle


def adapt_stats(rec, up, alw):
    """auto 의 선택이 구간별 최선을 따라갔는가 — 시간이 아니라 선택으로 잰다.

    적중 = auto 가 그 구간의 **실측 허용집합** 안의 팔을 골랐다
    적응 지연 = 구간 시작 후 허용집합 안의 선택이 연속 10 회 나올 때까지
    모형의 argmin(`want_m_model`)은 **정보로만** 남긴다 - 모형과 실측이
    갈리는 자리를 나중에 찾을 수 있어야 하기 때문이다.
    """
    out = {}
    for loss, _n in SCHEDULE:
        want = optimal_m(loss, up)
        ok_ms = set()
        if alw.get(loss):
            for a in alw[loss]["allowed"]:
                for nm, _f, mm in ARMS:
                    if nm == a:
                        ok_ms.add(mm)
        hits = tot = 0
        lags = []
        for s in rec["segments"]:
            if s["arm"] != "auto" or s["loss"] != loss:
                continue
            mu = s.get("m_used") or []
            tot += len(mu)
            hits += sum(1 for x in mu if x in ok_ms)
            lag, run = None, 0
            for i, x in enumerate(mu):
                run = run + 1 if x in ok_ms else 0
                if run >= 10:
                    lag = i - 9
                    break
            lags.append(lag)
        out[loss] = {"want_m_model": want,
                     "allowed": (alw.get(loss) or {}).get("allowed"),
                     "best_measured": (alw.get(loss) or {}).get("best"),
                     "hit_rate": (hits / tot) if tot else None,
                     "n": tot, "lags": lags,
                     "lag_med": (sorted([x for x in lags if x is not None])
                                 [len([x for x in lags if x is not None]) // 2]
                                 if any(x is not None for x in lags) else None),
                     "never_adapted": sum(1 for x in lags if x is None)}
    return out


def position_effect(rec):
    """자리(순서) 효과 — 팔에 무관하게 자리별 평균의 산포.

    라틴 방격이라 각 자리에 네 팔이 정확히 한 번씩 오므로, 자리별 평균의
    차이는 팔 효과가 상쇄된 **순수 순서 효과**다. 이것이 재려는 이득보다
    크면 그 이득은 이 표본으로 주장할 수 없다.
    """
    worst = 0.0
    for loss, _n in SCHEDULE:
        by_pos = {}
        for s in rec["segments"]:
            if s["loss"] == loss and s["mean"] is not None:
                by_pos.setdefault(s["pos"], []).append(s["mean"])
        vals = [mean(v) for v in by_pos.values() if v]
        if len(vals) >= 2:
            worst = max(worst, max(vals) - min(vals))
    return worst


def main():
    B.harden()
    B.require_root()
    B.setup()

    fp = code_fingerprint(["experiments/p17_adaptive_value.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/quicbed/policy.go",
                           "experiments/quicbed/pfail_table.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p17_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "group": GROUP, "cert": CERT, "n_per_seg": N,
           "cycles": CYCLES, "schedule": SCHEDULE, "rows": [], "gain": [],
           "checks": []}
    checks = out["checks"]

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-64s %s" % ("통과" if ok else "실패", name, detail),
              flush=True)

    print("=" * 104)
    print("P17 적응의 값어치 - 손실 %s%% 교대 x%d 사이클, 구간당 n=%d "
          "(라틴 방격 인터리브)"
          % (" <-> ".join("%g" % l for l, _ in SCHEDULE), CYCLES, N))
    print("=" * 104)

    for cond_name, rate, up_policy in CONDS:
        print()
        print("### 조건 %s (netem rate %g, 정책 uplink %g)"
              % (cond_name, rate, up_policy))
        out["rows"].append(run_interleaved(cond_name, rate, up_policy, jr))

    for rec in out["rows"]:
        am = rec["arms"]
        if not all(am[a]["mean"] is not None for a in am):
            continue
        means = {a: am[a]["mean"] for a in am}
        # 🩸 2026-08-25 - 여기 팔 이름이 ("m0","m1","m2") 로 박혀 있었다.
        #    29 차에서 m3 을 더했는데 이 목록에 안 들어가서 **최선 고정팔
        #    후보에서 m3 이 빠졌다.** 새 운용점의 고손실 구간 최적이
        #    m=3 이므로, 그대로 뒀으면 후회가 실제보다 **좋게** 나왔다.
        #    후회를 재는 자리에서 최선을 빼는 것은 결과를 좋게 만드는
        #    방향의 오류라 특히 나쁘다. ARMS 에서 유도한다.
        _fixed_names = [a for a, _f, _m in ARMS if a != "auto"]
        fixed = {a: means[a] for a in _fixed_names if a in means}
        best = min(fixed, key=lambda a: fixed[a])
        alw = allowed_by_loss(rec)
        out["gain"].append({
            "cond": rec["cond"], "means": means, "best_fixed": best,
            "best_fixed_mean": fixed[best], "auto_mean": means["auto"],
            "gain_ms": fixed[best] - means["auto"],
            "pos_effect_ms": position_effect(rec),
            "allowed_by_loss": alw,
            "oracle_gain_ms": oracle_gain_ms(alw),
            "adapt": adapt_stats(rec, dict(
                (c[0], c[2]) for c in CONDS)[rec["cond"]], alw),
            "fixed_spread_ms": max(fixed.values()) - min(fixed.values()),
            "n_auto": am["auto"]["n"]})
        g = out["gain"][-1]
        print()
        print("   [%s] 최선 고정 %s %.3f | auto %.3f | **이득 %+.3f ms** "
              "(자리효과 %.3f)"
              % (g["cond"], best, fixed[best], means["auto"],
                 g["gain_ms"], g["pos_effect_ms"]))

    print()
    print("-" * 104)
    g = {x["cond"]: x for x in out["gain"]}
    n_seg = len(CONDS) * CYCLES * len(SCHEDULE) * len(ARMS)
    got = sum(len(r["segments"]) for r in out["rows"])
    add("1. 모든 팔·구간이 측정됐다", got == n_seg
        and all(s["mean"] is not None for r in out["rows"]
                for s in r["segments"]),
        "%d/%d 구간" % (got, n_seg))
    add("2. 모든 조건에서 서버 통계가 실제로 있었다",
        all(r["srv_stats_present"] for r in out["rows"]) and out["rows"],
        "%d/%d" % (sum(1 for r in out["rows"] if r["srv_stats_present"]),
                   len(out["rows"])))

    lo = SCHEDULE[0][0]

    def seg_mean(cond, arm, loss):
        v = [s["mean"] for r in out["rows"] if r["cond"] == cond
             for s in r["segments"]
             if s["arm"] == arm and s["loss"] == loss and s["mean"] is not None]
        return mean(v)

    # 🩸 2026-08-25 - 조건 이름 "10Mbps" 가 박혀 있었다. 29 차에서
    #    "2Mbps" 로 바꾸자 조용히 None 이 되어 "자료 없음"으로 실패했다.
    #    이름이 아니라 **대역이 걸린 조건**(netem rate > 0)을 고른다.
    # 🩸 2026-08-26 - 이 검사는 "m2 가 m1 보다 비싸다"로 적혀 있었다.
    #    **모형의 주장을 자로 쓴 것**이고, 그 주장이 틀렸다. 대역이 걸리면
    #    m=1 의 뒤따르는 패리티가 증폭 신용을 송신 결정 전에 못 올려서
    #    왕복을 하나 더 쓴다(padfec/policy.py '경주' 절). 실측이 정확히
    #    반대다 - 2 Mbps 손실 2% 에서 m1 121.31 / m2 70.36 이다. 즉 이
    #    검사는 **대역이 제대로 걸릴수록 실패**하고 있었다.
    #
    #    재려던 것은 "netem 이 정말 대역을 거는가" 하나다. 그건 모형을
    #    거치지 말고 **같은 팔을 두 조건에서** 비교하면 된다. 패리티가 없는
    #    m0 이 제일 깨끗하다 - 첫 비행이 원본 k 개뿐이라 예상 지연이
    #    k·W/대역 으로 딱 떨어진다.
    _shaped = next((c for c in CONDS if c[1] > 0), None)
    _free = next((c for c in CONDS if c[1] == 0), None)
    sh0 = seg_mean(_shaped[0], "m0", lo) if _shaped else None
    fr0 = seg_mean(_free[0], "m0", lo) if _free else None
    # 원본 k 개를 그 대역으로 밀어내는 데 드는 시간. 관측 차이가 이것의
    # 절반은 돼야 "걸렸다"고 본다(측정 잡음 ~1-2 ms 보다 훨씬 크다).
    _ser = ((K * 1280 * 8.0) / (_shaped[1] * 1e6) * 1e3) if _shaped else 0.0
    add("3. 대역이 실제로 걸렸다 (같은 팔 m0 이 %s 에서 무제한보다 느리다)"
        % (_shaped[0] if _shaped else "대역 조건 없음"),
        (sh0 is not None and fr0 is not None and (sh0 - fr0) > _ser / 2.0),
        ("m0: %s %.2f vs 무제한 %.2f (차이 %+.2f ms, 예상 직렬화 %.2f)"
         % (_shaped[0], sh0, fr0, sh0 - fr0, _ser))
        if (sh0 and fr0) else "자료 없음(대역 조건 %s)"
        % (_shaped[0] if _shaped else None))

    slo = [s["mean"] for r in out["rows"] for s in r["segments"]
           if s["loss"] == lo and s["mean"] is not None]
    shi = [s["mean"] for r in out["rows"] for s in r["segments"]
           if s["loss"] != lo and s["mean"] is not None]
    add("4. 손실 전환이 실제로 일어났다 (고손실 구간이 저손실보다 느리다)",
        slo and shi and mean(shi) > mean(slo),
        "저손실 %.2f vs 고손실 %.2f ms" % (mean(slo) or -1, mean(shi) or -1))

    # 🩸 2026-08-25 - 여기도 조건 **이름**이 박혀 있었다. 이 한 줄이
    #    검사 5·6·7·8·9 를 전부 먹이므로, 이름이 바뀌면 다섯 검사가
    #    통째로 "자료 없음"으로 죽는다. 이름이 아니라 **성질**로 고른다:
    #    대역이 걸린 조건(netem rate > 0) / 안 걸린 조건(rate == 0).
    _shaped_name = next((c[0] for c in CONDS if c[1] > 0), None)
    _free_name = next((c[0] for c in CONDS if c[1] == 0), None)
    g10 = g.get(_shaped_name) if _shaped_name else None
    gu = g.get(_free_name) if _free_name else None
    add("5. 고정팔들이 서로 갈린다 (안 갈리면 아래가 공허하다)",
        g10 and g10["fixed_spread_ms"] > 0.5,
        ("고정팔 산포 %.3f ms" % g10["fixed_spread_ms"]) if g10 else "자료 없음")

    # ================= 선택 기반 판정 (시간 기반은 아래에서 정보로만) =====
    #
    # 🩸 2026-08-23 재설계. 시간(이득 ms)으로 판정하려면 팔당 46,398 연결이
    #    필요하다 - 부트스트랩으로 직접 계산했고 현재의 39 배다. 고손실
    #    구간의 PTO 분산이 원인이라 표본 말고는 방법이 없다.
    #    그런데 이 단계가 묻는 것은 "정책이 채널 변화를 따라가는가"이고,
    #    그것은 **선택**을 보면 잡음 없이 판정된다. 시간은 정보로 남긴다.
    a10 = g10["adapt"] if g10 else {}
    au = gu["adapt"] if gu else {}
    lo_l, hi_l = SCHEDULE[0][0], SCHEDULE[1][0]

    # 🩸 2026-08-26 - 검사 6 의 자를 **라벨에서 ms 로** 바꿨다.
    #    옛 자: "두 구간의 최적 m(모형 argmin)이 다르다".
    #    두 군데가 틀렸다. (a) 정답을 모형에서 가져오므로 모형이 틀리면
    #    자도 같이 틀린다. (b) 라벨이 갈리는 것과 **적응이 벌 것이 있는
    #    것**은 다른 말이다 - 1·2 위가 0.29 ms 차이면 라벨은 갈려도 벌
    #    것은 없다. 이 단계의 머리말이 적어 둔 조건 (a)(b) 를 그대로
    #    수로 옮기면 그것이 곧 오라클 이득이다. 그래서 그걸 잰다.
    #    탐색세는 p11 이 독립적으로 잰 0.42~0.51 ms 다. 그보다 작으면
    #    어떤 정책도 못 이기므로 아래 검사 7·8 은 공허해진다.
    og = g10.get("oracle_gain_ms") if g10 else None
    alw10 = (g10 or {}).get("allowed_by_loss") or {}
    add("6. [부정] 이 운용점에 적응이 벌 것이 있다 (오라클 이득 > 탐색세 0.42 ms)",
        og is not None and og > 0.42,
        ("오라클 이득 %.3f ms | %s"
         % (og if og is not None else float("nan"),
            " | ".join("손실%g%%: 최선 %s 허용 %s"
                       % (l, (alw10.get(l) or {}).get("best"),
                          (alw10.get(l) or {}).get("allowed"))
                       for l, _n in SCHEDULE)))
        if g10 else "자료 없음")

    worst_hit = min([a10[l]["hit_rate"] for l in a10
                     if a10[l]["hit_rate"] is not None] or [0])
    # 🩸 2026-08-27 - 검사 8 이 이미 갖고 있던 공허 표시를 **7 에도** 단다.
    #    두 구간의 허용집합이 같으면 auto 는 **고정 m 하나**로도 두 구간을
    #    다 맞힌다 - 그때 높은 적중률은 「적응한다」가 아니라 「적응할 게
    #    없다」는 뜻이다. 검사 6 이 붉을 때(오라클 이득 <= 탐색세) 이 검사의
    #    통과는 근거가 아니고, 그 사실이 판정 옆에 보여야 한다.
    #    (자를 바꾸지는 않는다 - 그건 연구 설계 판단이라 사람이 정한다.)
    _same7 = (a10 and a10[lo_l].get("allowed") == a10[hi_l].get("allowed"))
    add("7. ⭐ auto 가 각 구간에서 실측 허용집합 안의 m 을 과반 이상 고른다"
        + ("  [공허]" if _same7 else ""),
        a10 and worst_hit > 0.5,
        (("⚠️ 두 구간의 허용집합이 같다 - 고정 m 하나로도 통과한다. "
          "이 통과는 적응의 근거가 아니다. " if _same7 else "")
         + "최악 적중률 %.1f%% | %s"
         % (100 * worst_hit,
            "  ".join("손실%g%%: 허용 %s(최선 %s, 모형 m=%d) 적중 %.1f%% (n=%d)"
                      % (l, a10[l]["allowed"], a10[l]["best_measured"],
                         a10[l]["want_m_model"],
                         100 * (a10[l]["hit_rate"] or 0), a10[l]["n"])
                      for l in sorted(a10))))
        if a10 else "자료 없음")

    lags = [a10[l]["lag_med"] for l in a10 if a10[l]["lag_med"] is not None]
    never = sum(a10[l]["never_adapted"] for l in a10) if a10 else 0
    # 🩸 이 검사는 검사 6 위에 서 있다. 두 구간의 허용집합이 같으면 auto 가
    #    무엇을 고르든 지연이 0 으로 나와 **통과가 아무 말도 안 한다**(헐거움).
    #    자를 완화하지 않는 대신, 공허한지 아닌지를 detail 에 못 박는다.
    _same = (a10 and a10[lo_l].get("allowed") == a10[hi_l].get("allowed"))
    add("8. 적응 지연이 구간 길이의 절반 미만이다 (전환을 실제로 따라간다)",
        a10 and lags and max(lags) < N / 2 and never == 0,
        ("구간별 중앙 지연 %s 연결 (구간 %d) | 끝까지 적응 못 한 구간 %d%s"
         % (lags, N, never,
            "  ⚠️ 두 구간의 허용집합이 같다 - 이 통과는 공허하다"
            if _same else "")) if a10 else "자료 없음")

    # 검사 6 과 **같은 자**로 잰다(라벨이 아니라 ms). 무제한은 패리티가
    # 공짜라 최대 m 이 늘 최적이고, 그래서 적응이 벌 것이 0 이어야 한다.
    ogu = gu.get("oracle_gain_ms") if gu else None
    alwu = (gu or {}).get("allowed_by_loss") or {}
    add("9. [부정] 무제한에서는 적응이 벌 것이 없다 (오라클 이득 <= 탐색세)",
        ogu is not None and ogu <= 0.42,
        ("오라클 이득 %.3f ms | %s"
         % (ogu if ogu is not None else float("nan"),
            " | ".join("손실%g%%: 최선 %s 허용 %s"
                       % (l, (alwu.get(l) or {}).get("best"),
                          (alwu.get(l) or {}).get("allowed"))
                       for l, _n in SCHEDULE)))
        if gu else "자료 없음")

    # --- 시간 이득은 정보로만 (판정 안 함). 왜 판정 못 하는지 함께 적는다.
    for x in out["gain"]:
        print("   [정보] %-8s 시간 이득 %+.3f ms | 자리효과 %.3f ms "
              "-> 이 표본으로는 시간으로 판정 불가 (필요 N 약 4.6만/팔)"
              % (x["cond"], x["gain_ms"], x["pos_effect_ms"]))

    crc = sum(r["srv_crc_fail"] or 0 for r in out["rows"])
    add("10. 복구 CRC 실패 0", crc == 0, "총 %d 건" % crc)

    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(checks)))
    print("saved: %s" % B.save("p17_adaptive_value.json", out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
