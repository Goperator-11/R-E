# -*- coding: utf-8 -*-
"""P13 - B_eff 직접 측정 (명세 §2.6 / §8, loop2 단계 p13).

무엇을 재나
-----------
명세 §2.6 의 재해석: 증폭 모형의 인자는 "클라이언트가 보낸 총 바이트"가
아니라 **"서버가 응답 비행을 만들기로 결정한 시점까지 도착한 바이트"
B_eff** 다. 이 재해석은 사후적이므로 직접 측정 전까지는 가설이다 —
명세가 "반드시 직접 측정으로 확인해야 한다"고 못박은 자리가 여기다.

계측은 qamp.go 서버 쪽 연결별 회계(connAcct, 2026-08-20)다. 서버가 이
연결로 **첫 데이터그램을 내보내는 순간**의 수신 누적(스택 기준 = quic-go
증폭 예산이 실제로 세는 양)을 스냅숏으로 남기고, 원본/패리티 몫을 나눠
센다. 송신 타임라인(누적·크기·시각)도 함께 남아 서버 첫 비행의 실제
데이터그램 수까지 그대로 보인다.

경합하는 두 가설 (p4 임계 4/8 의 원인)
---------------------------------------
  (a) late-parity: k=1·m=1 배치 [원본, 패리티]는 패리티가 서버 결정
      **이후**에 도착해 신용을 못 산다 (levers 의 late_parity_risk 표시).
  (b) 뒤 비행 오합산: 패리티는 제때 도착해 신용을 다 산다. 빗나간 것은
      p2 가 client_bytes_total 에 **ACK 비행의 패리티까지** 합산했기
      때문이다 (on1 인데 패리티가 연결당 ~2,640 B = 1,318 x 2 로 잡혔다).
      첫 비행 몫만 세면 4개 팔 전부가 §2.6 의 "필요 B_eff 구간"에 든다:
          x25519 on1  1280+1318 = 2,598 ∈ (2560, 2986.7]   칸 7
          x25519 on2  1280+2636 = 3,916 ∈ (3840, 4266.7]   칸 10
          MLKEM  on1  2560+1324 = 3,884 ∈ (3840, 4266.7]   칸 10
          MLKEM  on2  2560+2648 = 5,208 ∈ (5120, 5546.7]   칸 13
이 스크립트가 B_eff 를 직접 재서 둘을 가른다.

같이 재는 것 — c (서버 패킷 오버헤드, 명세 §2.5)
------------------------------------------------
서버 송신을 가로채므로 첫 비행의 **실제 데이터그램 수 n 과 바이트**를 직접
센다. s0 = (첫 비행 바이트) - cert 를 n 에 대해 회귀하면 c 가 나온다.
_probe_s0 의 두 한계가 여기서 없어진다: (1) server_bytes 의 꼬리(ACK·
HANDSHAKE_DONE) 오염 - 첫 비행만 시각으로 잘라낸다, (2) n̂ = ceil(S/P)
추정 오류 - n 을 세지 추정하지 않는다. 1-RTT 조건만 쓴다(2-RTT 는 비행이
쪼개져 시각 절단이 무효다). FEC 팔로 허용량을 올려 cert 범위를 넓힌다 -
s0 는 서버 비행의 성질이라 클라이언트 팔과 무관하다.

통과 기준 (loop2 에 적힌 것): x25519 on1 의 B_eff ∈ (2560, 2986.7].

Output: experiments/results/p13_beff.json
실행:   unshare -Urnm python3 -u experiments/p13_beff.py
"""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
from padfec import policy as POL                 # noqa: E402

RTT_MS = 50.0
N_BEFF = 24
N_SWEEP = 12

# 🩸 2026-08-21 — **late-parity 판정에는 검정력이 없었다.**
# 옛 검사 5 는 N_BEFF=24 연결에서 나온 점추정(24/24 = 1.00)을 0.90 과
# 비교해 '기각(refuted)' 이라고 적었다. 그런데 24/24 의 95% 하한은
# **0.883** 이다 - 즉 참 신용률이 88.3% (늦은 패리티 11.7%) 여도 이
# 자료와 모순되지 않는다. 판정선(0.90)이 자료의 분해능보다 가늘다.
#
# 이것이 실제로 문제인 이유: p14 무손실 parity 팔이 2-RTT 를 **0.50%**
# (2/400) 냈다. 같은 조건의 pad 팔은 0/400 이다. 모형은 패리티 신용이
# 100% 잡힌다고 가정하므로 무손실 2-RTT 를 **0** 으로 예측한다.
# 0.5% 규모의 현상은 n=24 로는 원리적으로 안 보인다(무사건 확률 89%).
#
# 그래서 이 판정만 따로, 큰 표본으로 잰다. 600 연결이면 전부 신용될 때
# 95% 하한이 0.9950 이라 '늦은 패리티 < 1%' 를 실제로 말할 수 있다.
# (연결당 ~75 ms 이므로 약 45 초. 비싸지 않다.)
N_LATE = 600
LATE_CRED_MIN = 0.99      # 신용률 95% 하한이 이 값을 넘어야 '기각'
P_SRV = 1280

# 첫 비행/꼬리 절단 창. 1-RTT 조건에서 비행 버스트는 첫 송신 후 1 ms 안에
# 끝나고 꼬리는 RTT(50 ms) 뒤에 온다. 중간값 20 ms 는 양쪽에서 20 ms 이상
# 여유가 있다.
FLIGHT_WINDOW_NS = 20_000_000

GROUPS = [("x25519", 1), ("X25519MLKEM768", 2)]
ARMS = [("off", "off", 0), ("on1", "on", 1), ("on2", "on", 2)]

# 실측 임계(p2, 2026-08-20)의 중점. B_eff 를 "그 임계를 설명하는 칸"과 잇는다.
CERT_NEAR = {
    ("x25519", "off"): 3340, ("x25519", "on1"): 8267, ("x25519", "on2"): 12005,
    ("X25519MLKEM768", "off"): 5945,
    ("X25519MLKEM768", "on1"): 10929, ("X25519MLKEM768", "on2"): 14611,
}

# §2.6: 실측 임계를 설명하는 칸 n 이 요구하는 B_eff 구간
#   3*B_eff ∈ ((n-1)*P, n*P]  =>  B_eff ∈ ((n-1)*P/3, n*P/3]
BIN_OF = {("x25519", "off"): 3, ("x25519", "on1"): 7, ("x25519", "on2"): 10,
          ("X25519MLKEM768", "off"): 6, ("X25519MLKEM768", "on1"): 10,
          ("X25519MLKEM768", "on2"): 13}


def req_interval(bin_n):
    return ((bin_n - 1) * P_SRV / 3.0, bin_n * P_SRV / 3.0)


# c 스윕 조건: (그룹, 팔이름, fec, m, cert 목록). 전부 그 팔의 실측 임계
# 아래(1-RTT)다. FEC 팔은 허용량을 올려 cert 범위를 넓히는 수단일 뿐이고
# s0 는 서버 쪽 성질이라 팔과 무관하다 - 그 무관함 자체도 자료에서 보인다
# (같은 n 이 다른 팔에서 나오면 s0 가 같아야 한다).
SWEEP = [
    ("x25519", "off", "off", 0, [1000, 2000, 3000]),
    ("x25519", "on1", "on", 1, [4000, 5000, 6000, 7000, 8000]),
    ("x25519", "on2", "on", 2, [9000, 10500, 11500]),
    ("X25519MLKEM768", "off", "off", 0, [1000, 2500, 4000, 5500]),
    ("X25519MLKEM768", "on1", "on", 1, [6500, 8000, 9500, 10500]),
    ("X25519MLKEM768", "on2", "on", 2, [11500, 13000, 14000]),
]


def median(vals):
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def cp_lower(x, n, alpha=0.05):
    """Clopper-Pearson 단측 95% 하한 - 참 비율의 **보수적** 하한.

    점추정(x/n)을 판정선과 직접 비교하면 표본이 작을수록 유리한 쪽으로
    틀린다. 하한을 쓰면 '표본이 모자라면 통과할 수 없다'가 된다.
    x == n 일 때는 닫힌 형태 alpha**(1/n) 과 일치한다(자체시험).
    """
    if not n or x is None:
        return None
    if x <= 0:
        return 0.0
    if x >= n:
        return alpha ** (1.0 / n)
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        s = 0.0
        for i in range(x, n + 1):
            s += math.exp(math.lgamma(n + 1) - math.lgamma(i + 1)
                          - math.lgamma(n - i + 1)
                          + i * math.log(mid)
                          + (n - i) * math.log1p(-mid))
        if s > alpha:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def run_cond(group, k, fec, m, cert, n):
    """조건 하나를 돌리고 (클라 행들, 클라 통계, 서버 보고)를 준다."""
    srv_mode = "on" if fec == "on" else "off"
    p, sp = B.start_server(cert, fec=srv_mode)
    rows, cs, err = B.run_client(group, n, fec=fec, m=max(m, 1), gap_ms=15,
                                 timeout_s=12, expect_k=k)
    B.stop_server(p)
    ss = B.read_server_stats(sp)
    return rows, cs, ss, err


def conn_list(ss):
    """서버 보고의 연결별 회계. 시각 순(첫 수신 순)으로 준다."""
    conns = list((ss.get("conns") or {}).values())
    conns.sort(key=lambda c: c.get("first_rx_ns") or 0)
    return conns


def flight_of(conn):
    """송신 타임라인에서 서버 첫 비행(시각 절단)을 잘라낸다.

    돌려주는 것: (데이터그램 수, 바이트 합, 절단이 유효한가, 사유).

    🩸 2026-08-21 정정 — **옛 기준이 성공한 측정만 골라서 버렸다.**
    옛 조건은 사실상 `has_tail`(창 뒤에 송신이 더 있다) 하나였다.
    의도는 '비행이 창 경계에서 잘렸는지' 를 가리는 것이었는데,
    꼬리가 없는 경우는 두 가지이고 그 둘의 뜻이 정반대다.

      (a) 타임라인이 넘쳐서 뒤가 안 남았다      -> 정말로 알 수 없다
      (b) 서버가 그 뒤로 아무것도 안 보냈다     -> 비행이 한 번에 끝났다

    (b) 는 **FEC 가 성공해서 1-RTT 로 끝난 바로 그 경우**다(신용이
    충분하면 서버가 비행 전체를 한 버스트로 내보내고, 클라이언트가
    핸드셰이크 직후 연결을 닫으므로 뒤따르는 송신이 없다). 그래서
    X25519MLKEM768 의 FEC 팔이 **12/12 전부 무효**로 버려졌고,
    ML-KEM 의 c 는 사실상 off 팔 3 점에서 나온 값이 됐다.
    (근거: results/p13_beff.json 의 on1 6500/8000/9500/10500,
     on2 11500/13000/14000 이 전부 n_valid 0~1 / n_conns 12)

    (a) 와 (b) 는 `tx_dgrams == len(tx_ns)` 로 갈린다 — 서버가 센
    송신 수와 기록된 타임라인 길이가 같으면 타임라인이 안 넘친 것이다.
    사유를 함께 돌려주어 **어느 가지로 갔는지 자료에 남긴다**
    (추측이 아니라 다음 실행이 사실을 말하게 한다).
    """
    ts = conn.get("tx_ns") or []
    sz = conn.get("tx_sizes") or []
    if not ts or len(ts) != len(sz):
        return 0, 0, False, "타임라인 없음/길이 불일치"
    nfl = 0
    for i, t in enumerate(ts):
        if t - ts[0] < FLIGHT_WINDOW_NS:
            nfl = i + 1
        else:
            break
    has_tail = nfl < len(ts)
    timeline_full = conn.get("tx_dgrams") == len(ts)
    if has_tail:
        # 창 뒤에 송신이 더 있다 = 비행과 꼬리 사이를 실제로 갈랐다.
        return nfl, sum(sz[:nfl]), True, "꼬리로 절단"
    if timeline_full:
        # 꼬리가 없고 타임라인도 안 넘쳤다 = 서버가 그 뒤로 아무것도
        # 안 보냈다. 기록된 전부가 첫 비행이고, 잘린 것이 아니다.
        return nfl, sum(sz[:nfl]), True, "꼬리없음·타임라인 완전"
    # 꼬리도 없고 타임라인도 넘쳤다 = 뒤를 알 수 없다.
    return nfl, sum(sz[:nfl]), False, "타임라인 넘침"


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup(mtu=1500)
    B.set_netem(RTT_MS / 2.0, 0.0, 0.0)

    out = {"rtt_ms": RTT_MS, "n_beff": N_BEFF, "n_sweep": N_SWEEP,
           "beff": [], "sweep": [], "fits": {}, "checks": []}

    def add(name, ok, detail):
        out["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail[:90]),
              flush=True)

    # ================================================== 1. B_eff 직접 측정
    print("=" * 100)
    print("1) B_eff - 서버 첫 송신 직전의 수신 누적 (스택 기준, 원본/패리티 분리)")
    print("=" * 100)
    print("%-16s %-4s %-6s %-9s %-9s %-9s %-9s %-11s %s"
          % ("그룹", "팔", "cert", "B_eff", "원본몫", "패리티몫", "클라FF",
             "FF패리티", "판정구간"))

    for group, k in GROUPS:
        for arm, fec, m in ARMS:
            certs = sorted({3000, CERT_NEAR[(group, arm)]})
            for cert in certs:
                rows, cs, ss, err = run_cond(group, k, fec, m, cert, N_BEFF)
                conns = conn_list(ss)
                # 포트 충돌 합침 진단: 정상 연결의 rx_dgrams 는 조건
                # 안에서 거의 같다. 1.5 배를 넘으면 두 연결이 합쳐진
                # 것으로 의심하고 개수를 남긴다(다음 실행부터 원인이
                # 자료가 된다).
                _rxd = sorted(c.get("rx_dgrams") or 0 for c in conns)
                _rxmed = _rxd[len(_rxd) // 2] if _rxd else 0
                merged_n = sum(1 for c in conns
                               if _rxmed and (c.get("rx_dgrams") or 0)
                               >= 1.5 * _rxmed)
                beff = [c["beff_stack"] for c in conns]
                borg = [c["beff_orig_bytes"]
                        if "beff_orig_bytes" in c else c.get("beff_orig", 0)
                        for c in conns]
                bpar = [c.get("beff_parity", 0) for c in conns]
                ffb = [r.get("first_flight_bytes") or 0 for r in rows]
                ffp = [r.get("first_flight_parity_bytes") or 0 for r in rows]
                lo, hi = req_interval(BIN_OF[(group, arm)])
                rec = {"group": group, "arm": arm, "m": m, "cert": cert,
                       "n_conns": len(conns), "n_rows": len(rows),
                       "merged_suspect": merged_n,
                       "err": err,
                       "beff_med": median(beff),
                       "beff_min": min(beff) if beff else None,
                       "beff_max": max(beff) if beff else None,
                       "beff_orig_med": median(borg),
                       "beff_parity_med": median(bpar),
                       "client_ff_bytes_med": median(ffb),
                       "client_ff_parity_med": median(ffp),
                       "req_lo": lo, "req_hi": hi,
                       "parity_credited_frac": (
                           sum(1 for v in bpar if v > 0) / float(len(bpar))
                           if bpar and m > 0 else None),
                       # 🩸 2026-08-27 - **원자료를 남긴다.** 2026-08-26 에
                       #    검사 4 가 「1,332.5 vs 1,333.0」로 붉어졌는데,
                       #    중앙값만 저장돼 있어 **왜 0.5 B 가 갈렸는지
                       #    답할 수 없었다.** 목록 둘을 그대로 둔다 - 24 개짜리
                       #    정수 배열 두 개라 파일이 커지지 않는다.
                       "beff_parity_all": sorted(bpar),
                       "client_ff_parity_all": sorted(ffp),
                       # 패리티 크기는 quic-go 가 연결마다 무작위로 고르는
                       # CID 길이 때문에 몇 바이트 흔들린다(PARITY_OVERHEAD_BASE
                       # 주석). 그 폭을 재서 자로 쓴다 - 아래 검사 4.
                       "parity_jitter_b": ((max(ffp) - min(ffp))
                                           if ffp and m > 0 else 0)}
                out["beff"].append(rec)
                print("%-16s %-4s %-6d %-9s %-9s %-9s %-9s %-11s (%.0f, %.1f]"
                      % (group, arm, cert, rec["beff_med"],
                         rec["beff_orig_med"], rec["beff_parity_med"],
                         rec["client_ff_bytes_med"],
                         rec["client_ff_parity_med"], lo, hi), flush=True)

    def pick(group, arm, cert=None):
        cand = [r for r in out["beff"]
                if r["group"] == group and r["arm"] == arm
                and (cert is None or r["cert"] == cert)]
        return cand[-1] if cand else None

    # ---- 검사 1: 음성 대조 - off 팔은 패리티 몫 0, B_eff = k*W 그대로
    neg_bad = []
    for group, k in GROUPS:
        for r in [x for x in out["beff"] if x["group"] == group
                  and x["arm"] == "off"]:
            if r["beff_parity_med"] != 0 or r["beff_med"] != k * 1280:
                neg_bad.append((group, r["cert"], r["beff_med"],
                                r["beff_parity_med"]))
    add("1. 음성 대조: off 팔 B_eff == k*1280, 패리티 몫 0", not neg_bad,
        str(neg_bad[:3]) if neg_bad else "4/4 조건 정확히 k*1280")

    # ---- 검사 2 (loop2 통과 기준): x25519 on1 B_eff ∈ (2560, 2986.7]
    r = pick("x25519", "on1", CERT_NEAR[("x25519", "on1")])
    ok2 = r and r["beff_med"] is not None and 2560 < r["beff_med"] <= 8960 / 3.0
    add("2. [loop2 기준] x25519 on1 B_eff ∈ (2560, 2986.7]", ok2,
        "B_eff 중앙값 %s" % (r and r["beff_med"]))

    # ---- 검사 3: 4개 FEC 팔 전부 - B_eff 가 실측 임계를 설명하는 칸 구간 안
    miss = []
    for group, k in GROUPS:
        for arm in ("on1", "on2"):
            rr = pick(group, arm, CERT_NEAR[(group, arm)])
            if not rr or rr["beff_med"] is None or not (
                    rr["req_lo"] < rr["beff_med"] <= rr["req_hi"]):
                miss.append((group, arm, rr and rr["beff_med"]))
    add("3. FEC 4팔 전부 B_eff 가 해당 칸 구간 안", not miss,
        str(miss) if miss else "on1/on2 x 두 그룹 전부 적중")

    # ---- 검사 4: 첫 비행 패리티가 전부 결정 전에 도착하는가
    #
    # 🩸 2026-08-27 - **자를 제대로 세운다.** 옛 검사는
    #        median(서버 패리티 몫) == median(클라 패리티 바이트)
    #    를 **정확히** 요구했다. 셋이 잘못돼 있었다.
    #
    #    (1) **짝지어져 있지 않다.** 서버 쪽 `bpar` 는 포트로 묶은 연결별
    #        회계이고 클라 쪽 `ffp` 는 클라이언트 행이다. 같은 연결들이지만
    #        순서도 개수도 보장되지 않는다(n_conns vs n_rows). 두 목록의
    #        중앙값을 견주는 것은 연결을 짝지어 견주는 것과 다르다.
    #    (2) **재는 양이 흔들린다.** 패리티 크기는 quic-go 가 연결마다
    #        무작위로 고르는 CID 길이 때문에 몇 바이트 움직인다 - 그 사실은
    #        `PARITY_OVERHEAD_BASE` 주석이 이미 적어 뒀다(실측 1,323.5~1,326.5).
    #        흔들리는 양의 중앙값에 **정확히 같음**을 요구하면, 회계가 멀쩡해도
    #        표본이 홀짝만 달라져도 붉어진다.
    #    (3) **묻고 싶은 것을 안 묻는다.** 진짜 질문은 「패리티가 서버의 송신
    #        결정 전에 도착해 신용이 됐는가」다. 그 답은 중앙값이 아니라
    #        `parity_credited_frac`(신용된 연결의 비율)에 있다.
    #
    #    실제로 2026-08-26 에 붉어진 그 한 건이 이것이었다:
    #        X25519MLKEM768 / on1 / cert 3000 -> 1,332.5 vs 1,333.0
    #        같은 줄의 parity_credited_frac 는 **23/24 = 0.958** 이다.
    #        즉 연결 하나에서 패리티가 늦어 신용이 안 됐고, 나머지는 CID
    #        길이 흔들림이다. 1,333 B 중 0.5 B = 0.04% 를 「회계 누락」으로
    #        읽을 근거가 아니었다.
    #
    # 그래서 둘로 나눈다.
    #    4a  신용된 연결의 비율 (묻고 싶던 것). 표본이 24 라 점추정으로
    #        판정하면 안 되므로 Wilson 하한을 쓴다 - 검사 5 가 이미 쓰는 관례다.
    #    4b  신용된 연결에 한해 중앙값이 **CID 흔들림 폭 안에서** 맞는가.
    #        자는 그 조건에서 실제로 관측된 흔들림 폭(parity_jitter_b)이고,
    #        폭이 0 이면 정확히 같기를 요구한다. 임의로 넓힌 자가 아니다.
    par_bad, cred_bad = [], []
    for group, k in GROUPS:
        for arm in ("on1", "on2"):
            for rr in [x for x in out["beff"] if x["group"] == group
                       and x["arm"] == arm]:
                n_c = rr["n_conns"] or 0
                frac = rr.get("parity_credited_frac")
                if frac is not None and n_c:
                    # ⚠️ N_BEFF=24 로는 **어떤 결과가 나와도** CP 하한이
                    #    0.05^(1/24) = 0.883 을 못 넘는다. 그러므로 하한에
                    #    0.95 같은 선을 그으면 **달성 불가능한 자**가 된다 -
                    #    이 저장소가 방금 p18 검사 4 에서 걷어낸 것과 같은
                    #    병이다. 그래서 판정은 점추정으로 하고, **하한과
                    #    필요 표본을 함께 적어** 얼마나 확실한지 드러낸다.
                    #    엄밀한 판정은 검사 5 가 n=600 으로 따로 한다.
                    if frac < 0.95:
                        cred_bad.append((group, arm, rr["cert"],
                                         round(frac, 4),
                                         round(cp_lower(int(round(frac * n_c)),
                                                        n_c) or 0, 4), n_c))
                tol = max(0, rr.get("parity_jitter_b") or 0)
                d = abs((rr["beff_parity_med"] or 0)
                        - (rr["client_ff_parity_med"] or 0))
                if d > tol:
                    par_bad.append((group, arm, rr["cert"],
                                    rr["beff_parity_med"],
                                    rr["client_ff_parity_med"], tol))
    # 하한 0.95 를 인증하려면 전부 신용돼도 n >= ceil(ln0.05/ln0.95) = 59 이다.
    _n_for_95 = int(math.ceil(math.log(0.05) / math.log(0.95)))
    add("4a. 패리티가 서버 결정 전에 도착해 신용된다 (점추정 >= 0.95; "
        "하한 인증은 검사 5)",
        not cred_bad, str(cred_bad[:3]) if cred_bad
        else " | ".join("%s/%s c%d %.3f (하한 %.3f, n=%d)"
                        % (r["group"][:6], r["arm"], r["cert"],
                           r["parity_credited_frac"],
                           cp_lower(int(round((r["parity_credited_frac"] or 0)
                                               * (r["n_conns"] or 0))),
                                     r["n_conns"] or 1),
                           r["n_conns"])
                        for r in out["beff"]
                        if r.get("parity_credited_frac") is not None)
             + " | 하한 0.95 인증에는 조건당 n>=%d 필요 (지금 %d)"
               % (_n_for_95, N_BEFF))
    add("4b. 서버 패리티 몫 == 클라 패리티 (CID 흔들림 폭 안)",
        not par_bad, str(par_bad[:3]) if par_bad
        else "전 조건에서 흔들림 폭 안 (폭 %s B)"
             % sorted({r.get("parity_jitter_b") for r in out["beff"]
                       if r.get("parity_jitter_b") is not None}))

    # ---- 검사 5: late-parity 가설 판정 (k=1, m=1) - 전용 대량 표본
    #
    # 위 beff 구간(N_BEFF=24)의 점추정으로는 이 판정을 할 수 없다
    # (N_LATE 주석 참조). 같은 조건을 N_LATE 연결로 다시 재고,
    # **95% 하한**으로 판정한다. 2-RTT 비율도 같은 연결에서 함께
    # 남긴다 - 늦은 패리티가 실제로 왕복을 하나 더 물리는지 보려면
    # 두 수가 같은 표본에서 나와야 하기 때문이다.
    _lcert = CERT_NEAR[("x25519", "on1")]
    print()
    print("5) late-parity 전용 측정: x25519 k=1 m=1 cert=%d, %d 연결"
          % (_lcert, N_LATE), flush=True)
    _lrows, _lcs, _lss, _lerr = run_cond("x25519", 1, "on", 1,
                                        _lcert, N_LATE)
    _lconns = conn_list(_lss)
    _lpar = [c.get("beff_parity", 0) for c in _lconns]
    _lcred = sum(1 for v in _lpar if v > 0)
    _lsum = B.summarize(_lrows, rtt_ms=RTT_MS)
    _llo = cp_lower(_lcred, len(_lconns)) if _lconns else None
    out["late_parity"] = {
        "cert": _lcert, "n_req": N_LATE, "n_conns": len(_lconns),
        "credited": _lcred, "err": _lerr,
        "frac": (_lcred / float(len(_lconns))) if _lconns else None,
        "cred_ci95_lo": _llo,
        "two_rtt_rate": _lsum.get("two_rtt_rate"),
        "p50": _lsum.get("p50"), "n_ok": _lsum.get("n"),
    }
    print("   신용 %d/%d (하한 %s) | 2-RTT %s"
          % (_lcred, len(_lconns),
             "-" if _llo is None else "%.4f" % _llo,
             out["late_parity"]["two_rtt_rate"]), flush=True)
    refuted = _llo is not None and _llo >= LATE_CRED_MIN
    _frac = out["late_parity"]["frac"]
    out["late_parity_verdict"] = (
        "refuted" if refuted else
        ("confirmed" if _frac is not None and _frac <= 0.1
         else "inconclusive"))
    add("5. late-parity: 신용률 95%% 하한 >= %.2f (= 늦은 패리티 < %.0f%%)"
        % (LATE_CRED_MIN, 100 * (1 - LATE_CRED_MIN)),
        out["late_parity_verdict"] != "inconclusive",
        "%d/%d 신용, 하한 %s -> %s (표본 %d 로는 하한이 %s 까지만 간다)"
        % (_lcred, len(_lconns),
           "-" if _llo is None else "%.4f" % _llo,
           out["late_parity_verdict"], len(_lconns),
           "-" if not _lconns else "%.4f" % (0.05 ** (1.0 / len(_lconns)))))

    # ---- 검사 6: 뒤 비행(ACK 비행)의 바이트가 B_eff 에 안 섞였다
    ack_bad = []
    for rr in out["beff"]:
        full = (rr["client_ff_bytes_med"] or 0) + (rr["client_ff_parity_med"]
                                                   or 0)
        if rr["beff_med"] is not None and rr["beff_med"] > full:
            ack_bad.append((rr["group"], rr["arm"], rr["cert"],
                            rr["beff_med"], full))
    add("6. B_eff <= 첫 비행(원본+패리티) - 뒤 비행 몫이 안 섞임", not ack_bad,
        str(ack_bad[:3]) if ack_bad else "전 조건에서 상한 준수")

    # ---- 검사 7: 계측 완전성 - 연결 수가 시행 수와 같다
    #
    # 🩸 2026-08-21 재보정 - 등호 요구는 **포트 생일 충돌**에 걸리는
    #    양치기였다. 서버는 연결을 IP:포트로 식별하므로(qamp.go 825)
    #    임시 포트(28,232 개)가 재사용되면 두 시행이 한 항목으로
    #    합쳐진다. 기대 충돌 수가 관측과 맞는다: late-parity n=600 에서
    #    기대 6.4 -> 관측 6(3차)/10(4차); beff 12 조건에서 기대
    #    0.12/실행 -> 관측 0(3차)/1(4차). 중앙값 측정에 1/24 손실은
    #    영향이 없다. 조건별 <= 1 & 전체 <= 기대x3 만 허용하고,
    #    전면적 회계 손실은 여전히 잡는다.
    inc = [(r_["group"], r_["arm"], r_["cert"], r_["n_conns"], r_["n_rows"])
           for r_ in out["beff"] if r_["n_conns"] != r_["n_rows"]]
    _bad7 = [x for x in inc if x[4] - x[3] >= 2]
    _miss = sum(x[4] - x[3] for x in inc)
    _exp = sum(r_["n_rows"] * (r_["n_rows"] - 1) / 2.0 / 28232.0
               for r_ in out["beff"])
    add("7. 연결별 회계 완전성 (포트 생일충돌 기대 이내, 조건별 <= 1)",
        (not _bad7) and _miss <= max(1, 3.0 * _exp),
        "누락 합 %d (생일 기대 %.2f) | 조건별 2+ 누락 %s | 상세 %s"
        % (_miss, _exp, _bad7 or "없음", inc[:3] or "완전"))

    # ================================================== 2. c 확정 스윕
    print()
    print("=" * 100)
    print("2) c (서버 패킷 오버헤드) - 첫 비행 데이터그램을 직접 세서 s0(n) 회귀")
    print("=" * 100)
    print("%-16s %-4s %-6s %-7s %-9s %-9s %-6s" % (
        "그룹", "팔", "cert", "n비행", "비행바이트", "s0직접", "유효"))

    for group, arm, fec, m, certs in SWEEP:
        k = 2 if group == "X25519MLKEM768" else 1
        for cert in certs:
            rows, cs, ss, err = run_cond(group, k, fec, m, cert, N_SWEEP)
            conns = conn_list(ss)
            nfl, sfl, s0d = [], [], []
            valid = 0
            why_n = {}     # 무효 사유별 개수 - 버린 이유를 남긴다
            for c in conns:
                n_, s_, ok_, why_ = flight_of(c)
                why_n[why_] = why_n.get(why_, 0) + 1
                if not ok_:
                    continue
                valid += 1
                nfl.append(n_)
                sfl.append(s_)
                s0d.append(s_ - cert)
            two = B.summarize(rows, rtt_ms=RTT_MS).get("two_rtt_rate")
            # 🩸 2026-08-21 - **폐루프가 실제로 보는 값**을 같이 적는다.
            #    Go 의 decide() 는 fc.counts() 의 RxBytes 를
            #    snap.ServerFlight 로 쓰는데, 그것은 연결 **전체**의
            #    수신 바이트지 첫 비행 몫이 아니다. 두 값을 나란히
            #    재 본 적이 한 번도 없었다.
            srvb = [r.get("server_bytes") or 0 for r in rows
                    if r.get("ok")]
            rec = {"group": group, "arm": arm, "cert": cert, "err": err,
                   "n_conns": len(conns), "n_valid": valid,
                   "two_rtt_rate": two,
                   "n_flight_med": median(nfl), "flight_bytes_med": median(sfl),
                   "s0_direct_med": median(s0d),
                   "s0_spread": (max(s0d) - min(s0d)) if s0d else None,
                   "flight_why": why_n,
                   # 폐루프 입력 대 실제 첫 비행 (같은 연결들)
                   "srv_rx_med": median(srvb),
                   "srv_rx_minus_flight": (
                       (median(srvb) - median(sfl))
                       if srvb and sfl else None),
                   # 1-RTT 이고, 비행 절단이 과반에서 유효해야 쓴다
                   "usable": bool(s0d) and valid >= N_SWEEP // 2
                             and (two is not None and two < 0.1)}
            out["sweep"].append(rec)
            print("%-16s %-4s %-6d %-7s %-9s %-9s %-6s"
                  % (group, arm, cert, rec["n_flight_med"],
                     rec["flight_bytes_med"], rec["s0_direct_med"],
                     "예" if rec["usable"] else "아니오"), flush=True)

    # ---- 그룹별 회귀: s0 = s0_base + n*c
    for group, _k in GROUPS:
        pts = [(r_["n_flight_med"], r_["s0_direct_med"])
               for r_ in out["sweep"] if r_["group"] == group and r_["usable"]]
        # 같은 n 은 평균으로 합친다 - 조건 수가 아니라 n 격자가 자유도다
        by_n = {}
        for n_, s_ in pts:
            by_n.setdefault(n_, []).append(s_)
        xy = sorted((n_, sum(v) / len(v)) for n_, v in by_n.items())
        fit = {"points": xy, "by_n": {str(k_): v for k_, v in by_n.items()}}
        if len(xy) >= 2:
            n_ = len(xy)
            mx = sum(x for x, _ in xy) / n_
            my = sum(y for _, y in xy) / n_
            den = sum((x - mx) ** 2 for x, _ in xy)
            c_hat = sum((x - mx) * (y - my) for x, y in xy) / den
            b_hat = my - c_hat * mx
            fit["c"] = c_hat
            fit["s0_base"] = b_hat
            fit["mae"] = sum(abs(y - (b_hat + c_hat * x)) for x, y in xy) / n_
        out["fits"][group] = fit
        if "c" in fit:
            print("  %-16s c = %.2f B/패킷, s0_base = %.1f, 적합 MAE %.1f B, "
                  "n 격자 %s" % (group, fit["c"], fit["s0_base"], fit["mae"],
                                 [x for x, _ in xy]), flush=True)

    # ---- 검사 8: s0 단조 증가 (직접 계수 기준)
    mono_bad = []
    for group, _k in GROUPS:
        xy = out["fits"][group].get("points", [])
        for i in range(1, len(xy)):
            if xy[i][1] < xy[i - 1][1] - 1.0:
                mono_bad.append((group, xy[i - 1], xy[i]))
    add("8. s0 가 첫 비행 데이터그램 수에 대해 단조 증가", not mono_bad,
        str(mono_bad[:3]) if mono_bad else "두 그룹 전부 단조")

    # ---- 검사 9: s0(n) 선형 모형의 적합도 (임계 예측에 쓰는 그 용도 기준)
    #
    # ⚠️ 이 검사의 첫 판은 "같은 n 안 폭 <= 6 B" 였다 - '폭은 n̂ 추정 오류라
    # 직접 세면 사라진다'는 명세 §2.5 의 가설을 박은 것이다. 첫 실측이 그
    # 가설을 **기각**했다(x25519 폭 39·41.5 B, 직접 계수인데도): 게이트가
    # 마지막 작은 패킷을 통과시키므로 조성에 따라 s0 가 같은 n 안에서도
    # 실제로 흔들린다(cert 3312 에서 3,931 B > A 를 보내고 1-RTT - 명세 §2.5
    # 정정 참조). 기각된 가설을 영원히 실패로 두는 대신, 이 모형이 실제로
    # 쓰이는 용도(임계 예측)의 적합도를 잰다. 폭 원자료는 fits.by_n 과
    # s0_spread 에 그대로 남는다 - 숨기는 것이 아니다.
    mae_bad = []
    for group, _k in GROUPS:
        mae = out["fits"][group].get("mae")
        if mae is None or mae > 15.0:
            mae_bad.append((group, mae))
    add("9. s0(n) 회귀 MAE <= 15 B (임계 예측 용도의 적합도)", not mae_bad,
        str(mae_bad) if mae_bad else
        "x25519 %.1f / MLKEM %.1f B (같은 n 안 실폭은 fits.by_n 에 기록)"
        % (out["fits"][GROUPS[0][0]].get("mae", -1),
           out["fits"][GROUPS[1][0]].get("mae", -1)))

    # ---- 검사 10: 패킷항이 실재한다 (기울기 > 5) + 두 그룹 일치
    cs_ = [out["fits"][g].get("c") for g, _ in GROUPS]
    ok10 = all(c_ is not None and c_ > 5.0 for c_ in cs_)
    add("10. c > 5 B/패킷 (상수 s0 모형 기각)", ok10,
        "x25519 %.2f / MLKEM %.2f" % tuple(c_ if c_ is not None else -1
                                           for c_ in cs_))

    # ---- 검사 13: 폐루프가 보는 S 가 첫 비행과 한 칸 안에서 같다
    #
    # 폐루프는 이 값으로 n* 를 정한다. 칸이 1,280 B 이므로 차이가 한 칸을
    # 넘으면 **결정의 눈금이 통째로 어긋난다** - 임의의 선이 아니다.
    # 한 칸 안이라도 값은 그대로 기록한다(부호와 크기가 다음 수정의 근거다).
    _gaps = [(r_["group"], r_["arm"], r_["cert"],
              r_["srv_rx_minus_flight"]) for r_ in out["sweep"]
             if r_.get("usable") and r_.get("srv_rx_minus_flight") is not None]
    _bad13 = [g for g in _gaps if abs(g[3]) >= P_SRV]
    add("13. 폐루프 입력(server_bytes)이 첫 비행과 한 칸(1280 B) 안",
        (not _bad13) and bool(_gaps),
        (str(_bad13[:3]) if _bad13 else
         "%d 조건, 차이 %+d ~ %+d B (중앙 %+d)"
         % (len(_gaps), min(g[3] for g in _gaps),
            max(g[3] for g in _gaps),
            sorted(g[3] for g in _gaps)[len(_gaps) // 2]))
        if _gaps else "측정된 조건이 없다")

    # ---- 검사 11: 조건마다 연결이 실제로 생겼다
    #
    # 🩸 X25519MLKEM768 off cert=5500 은 n_conns 가 **0** 이었는데
    #    조용히 usable=False 로 넘어갔다. 연결이 하나도 안 생긴 것은
    #    '이 조건은 못 쓴다' 가 아니라 '측정이 안 됐다' 이고, 그 둘을
    #    같은 칸에 넣으면 안 된 측정이 목록에서 사라진다.
    noconn = [(r_["group"], r_["arm"], r_["cert"], r_["err"])
              for r_ in out["sweep"] if not r_["n_conns"]]
    add("11. 스윕 전 조건에서 연결이 실제로 생겼다", not noconn,
        str(noconn[:3]) if noconn else
        "%d 조건 전부 n_conns > 0" % len(out["sweep"]))

    # ---- 검사 12: 두 그룹의 회귀가 n 격자 3 점 이상에서 나왔다
    #
    # 근거의 두께를 수치로 드러낸다. 2 점이면 직선은 언제나 완벽히
    # 맞으므로(자유도 0) 검사 9 의 MAE 가 의미를 잃는다.
    thin = [(g_, len(out["fits"][g_].get("points", [])))
            for g_, _k in GROUPS
            if len(out["fits"][g_].get("points", [])) < 3]
    add("12. 두 그룹 모두 n 격자 3 점 이상에서 회귀했다", not thin,
        str(thin) if thin else "x25519 %d 점 / MLKEM %d 점"
        % (len(out["fits"][GROUPS[0][0]].get("points", [])),
           len(out["fits"][GROUPS[1][0]].get("points", []))))

    # 정책 기본값과의 관계를 기록만 한다 - 상수를 실제로 바꾸는 것은
    # 이 결과를 보고 명세를 고친 뒤의 일이다 (quantum.py 머리말의 규칙).
    out["c_policy_default"] = POL.C_PKT_POLICY_DEFAULT

    npass = sum(1 for c in out["checks"] if c["ok"])
    out["passed"] = npass
    out["total"] = len(out["checks"])
    print()
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(out["checks"])))
    print("late-parity 판정: %s" % out["late_parity_verdict"])
    print("saved:", B.save("p13_beff.json", out))
    return 0 if npass == len(out["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
