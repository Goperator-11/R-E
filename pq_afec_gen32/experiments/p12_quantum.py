# -*- coding: utf-8 -*-
"""P12 - 양자 경계 절벽. v2 의 헤드라인 주장을 증명하거나 죽인다.

명세 §2 따름정리는 이렇게 말한다.

    W = 1280 = P 이면  B = k·W 이고 3B 는 항상 P 의 배수다.
    그러므로 A(B) = ceil(3B/P)·P = 3B 이고

        Δ_min = floor(A(B)/3 − B) + 1 = 1        (k 와 무관)

    즉 quic-go 기본 클라이언트는 증폭 양자 경계에 **정확히 걸터앉아**
    있고, 1 바이트만 더 보내면 서버 예산이 P = 1,280 B 늘어난다.

이 문장은 반증 가능하다. `ips` 를 1 B 씩 움직이면서 1-RTT → 2-RTT 임계
인증서 크기를 재면, 임계가 **1280 과 1281 사이에서만** 한 칸 뛰어야 한다.
이 실험은 데이터그램별 IPS를 바꾼다. k=1이면 IPS +1 B가 총 +1 B이고,
k=2인 교차 실험에서는 총 +2 B다. 후자는 총 +1 B의 직접 실측이 아니다.
1279 와 1280 은 같은 칸이어야 하고, 1281 위쪽(1282·1300·1350·1450)은 전부
같은 고원이어야 한다.

무엇이 이 주장을 죽이는가 (부정 시험을 먼저 적는다)
  - 1279 와 1280 의 임계가 **다르면** "경계는 1281" 이 죽는다. 그러면
    임계는 양자 계단이 아니라 연속이거나, 계단의 위치가 우리 식과 다르다.
  - 1280 → 1281 도약이 한 칸(≈1,246 B)이 아니면 A(B) = ceil(3B/P)·P 가
    틀린 것이다.
  - 1281 위쪽이 고원이 아니면 계단폭이 P 가 아니다.
  - 어느 설정에서든 B ≠ k·ips 이면 **예측의 전제 자체**가 깨진 것이다.
    이건 실패로 기록하고, 나머지 예측은 근거를 잃는다.

측정 설계 (명세 §8 의 p12 / p12b / p12c)
  주 실험  x25519 (k=1)          ips ∈ {1279, 1280, 1281, 1282, 1300, 1350, 1450}
  교차 확인 X25519MLKEM768 (k=2)  ips ∈ {1280, 1281, 1350}
  p12c    x25519 (k=1)          ips ∈ {1707, 2134}  (칸 5·6)

임계는 p2 와 **같은 격자**에서 찾는다. LO/HI/RESOLUTION 을 p2 에서 그대로
가져오므로 이분탐색이 밟는 중점이 같고, 따라서 여기서 나온 구간을 p2 의
`ips_sweep` 구간(1200/1280 → [3312,3368], 1350/1450 → [4557,4614])과
**글자 그대로** 비교할 수 있다. 상수를 새로 고르면 폭이 달라져 두 실험을
못 겹친다 - 그래서 import 로 묶어 둔다.

무엇이 종료코드를 정하는가 (2026-08-20 감사 반영)
  게이팅  전제(B=k·ips) · 부정시험 · 절벽 · 고원 · 따름정리 · 보조정리2 ·
          단조성 · 교차. 이것만 exit code 를 만든다.
  정보    사전 등록 예측과의 **글자 그대로** 대조. 이 8~10 건은 p2 가 이미
          관측한 칸 안의 값이라 **out-of-sample 이 아니다**(`in_sample: true`).
          s0 기준선이 격자 한 칸(56 B)만 밀려도 전부 어긋나므로, 헤드라인을
          그 위에 얹으면 안 된다. `gating: false` 로 남기기만 한다.
  p12c    1707·2134 만 진짜 out-of-sample(`in_sample: false`). 단 이 둘은
          MTU 1500(UDP 페이로드 1472)을 넘고 quic-go v0.61 은
          InitialPacketSize 를 MaxPacketBufferSize = 1452 로 **조용히 깎는다**
          (`config.go` populateConfig). 그래서 먼저 "정말 그 크기로 나가는가"를
          재고, 안 나가면 `skipped` 로 적는다 - 억지로 통과시키지 않는다.
          여기도 게이팅이 아니다.

    실행:  unshare -Urnm python3 -u experiments/p12_quantum.py
    건식:  unshare -Urnm python3 -u experiments/p12_quantum.py --smoke

Output: experiments/results/p12_quantum.json   (--smoke 는 *_smoke.json)
"""
from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
import p2_threshold as P2                        # noqa: E402
from padfec import amplif                        # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

# ---------------------------------------------------------------- 상수 (p2 상속)
# 🩸 여기 있는 네 값은 **절대 따로 정하지 않는다.** p2 의 이분탐색 격자와
# 같아야 두 실험의 임계 구간을 직접 비교할 수 있다. 폭 약 56 B 는
# (16000-1500)/2^8 에서 나온 것이지 우리가 고른 수가 아니다.
RTT_MS = P2.RTT_MS                 # 50.0
LO, HI = P2.LO, P2.HI              # 1500, 16000
RESOLUTION = P2.RESOLUTION         # 100  -> 최종 폭 ≈ 56 B
N_PROBE = P2.N_PROBE               # 15   임계 판정에 필요한 최소
N_CONFIRM = P2.N_CONFIRM           # 40   경계가 흐릿할 때만

P = amplif.SERVER_PACKET_SIZE      # 1280, quic-go 서버 패킷 크기

# 한 칸 도약의 허용 범위. 모형이 말하는 값은 P = 1280 이 아니라
# **1245.5** 다 - 칸이 하나 올라가면 허용량은 +1280 이지만 s0 추정도
# 34.5 B 올라가기 때문이다(명세 §5 의 "s0 두 단계"). 격자 폭이 ±56 이므로
# 두 값(1245.5, 1280)을 모두 품는 창을 쓴다.
JUMP_MODEL = 1245.5
JUMP_LO, JUMP_HI = 1100.0, 1400.0

MAIN_GROUP, MAIN_K = "x25519", 1
# 명세 §8 p12 의 통과 기준은 "1281 과 1350·**1450** 이 같은 칸"이다.
# 1450 이 빠져 있어서 기준이 요구하는 측정점을 못 채우고 있었다(감사).
MAIN_IPS = [1279, 1280, 1281, 1282, 1300, 1350, 1450]
CROSS_GROUP, CROSS_K = "X25519MLKEM768", 2
# 같은 이유로 교차(p12b)의 "1281 과 1350 이 같은 칸"을 위해 1350 을 넣는다.
CROSS_IPS = [1280, 1281, 1350]

# 사전 등록한 예측. 측정 전에 적어 둔 값이며 **p2 의 관측 구간 그대로**다.
#   x25519  : 1279·1280 -> 칸 3 [3312,3368],  1281 이상 -> 칸 4 [4557,4614]
#   ML-KEM  : 1280 -> 칸 6 [5917,5974],       1281 이상 -> 칸 7 [7163,7219]
#
# 🩸 이 표는 **out-of-sample 예측이 아니다.** p2 는 x25519 1350·1450 에서
# [4557,4614] 를, ML-KEM 1350·1450 에서 [7163,7219] 를 이미 관측했다. 여기
# 적힌 값은 그 관측된 칸을 이웃 ips 로 옮겨 적은 것뿐이다. 그래서 아래
# 판정에서 이 대조는 **정보(gating=False)** 로만 남긴다 - 진짜 시험은
# 1707·2134(P12C_PRED)다.
PRED = {
    ("x25519", 1279): (3312, 3368),
    ("x25519", 1280): (3312, 3368),
    ("x25519", 1281): (4557, 4614),
    ("x25519", 1282): (4557, 4614),
    ("x25519", 1300): (4557, 4614),
    ("x25519", 1350): (4557, 4614),
    ("x25519", 1450): (4557, 4614),
    ("X25519MLKEM768", 1280): (5917, 5974),
    ("X25519MLKEM768", 1281): (7163, 7219),
    ("X25519MLKEM768", 1350): (7163, 7219),
}

# ------------------------------------------------------------------ p12c
# 명세 §8 p12c. 칸 5·6 은 기존 데이터 **밖**이라 두 모형이 서로 다른 값을
# 준다 - 여기서 갈린다.
#
#   패킷항 모형   임계 = A(B) − s0_base − (A(B)/P)·c   (§2.5, c = 34.5)
#   상수 s0 모형  임계 = A(B) − s0                     (v1)
#
# ⚠ 두 ips 는 MTU 1500 을 넘는다(IP 20 + UDP 8 → 페이로드 상한 1472).
#   quic-go v0.61 `populateConfig` 는 InitialPacketSize 를
#   MaxPacketBufferSize = 1452 로 **말없이 깎는다**. 그러면 B = k·ips 라는
#   전제부터 깨지므로 임계를 재도 그건 1707 의 임계가 아니다.
#   그래서 먼저 실현 가능성을 재고, 깎이면 skipped 로 적는다.
P12C_GROUP, P12C_K = "x25519", 1
P12C_IPS = [1707, 2134]
P12C_PRED = {          # ips: (칸 n, 패킷항 모형 임계, 상수 s0 모형 임계)
    1707: (5, 5831.0, 5865.5),
    2134: (6, 7076.5, 7145.5),
}
P12C_FEAS_CERT = 2000  # 실현 가능성만 본다 - 임계 근처일 필요가 없다
P12C_FEAS_N = 6
MTU = 1500
UDP_PAYLOAD_MAX = MTU - 20 - 8      # 1472
QUICGO_MAX_PACKET_BUFFER = 1452     # quic-go internal/protocol/protocol.go

# 건식 실행(경로 점검용). ips 2개 x 인증서 2개 x n=6.
SMOKE_IPS = [1280, 1281]
SMOKE_CERTS = [2000, 8000]
SMOKE_N = 6


def log(msg=""):
    print(msg)
    sys.stdout.flush()


def add(results, name, ok, detail):
    """게이팅 검사. 이것만 종료코드를 만든다."""
    results.append({"check": name, "ok": bool(ok), "detail": detail,
                    "gating": True})
    log("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail))


def add_info(results, name, ok, detail, **extra):
    """정보 검사. 기록만 하고 **종료코드에 넣지 않는다.**

    🩸 왜 분리했나(2026-08-20 감사). 사전 등록 예측과의 글자 그대로 대조가
    exit code 를 정하고 있었다. 그 예측은 p2 관측 칸을 옮겨 적은 것이라
    s0 기준선이 격자 한 칸(56 B)만 밀려도 8건이 통째로 어긋나고, 그러면
    **절벽 자체는 멀쩡한데 헤드라인 단계가 실패로 보인다.** 정보와 시험을
    같은 통에 담은 것이 잘못이었다.
    """
    rec = {"check": name, "ok": bool(ok), "detail": detail, "gating": False}
    rec.update(extra)
    results.append(rec)
    log("[%s] %-58s %s" % ("정보 O" if ok else "정보 X", name, detail))


# ------------------------------------------------------------------- 측정 단위
def probe(group, ips, cert, k, n, jr):
    """이 (그룹, ips, 인증서)에서 2-RTT 비율을 잰다. p2.probe 의 ips 판.

    p2 는 팔(off/buf/on)을 훑고 우리는 ips 를 훑는다. 그래서 서명이 다르지만
    안쪽은 같다 - 서버를 새로 띄우고, 클라이언트를 n 회 돌리고, **먼저 죽인
    뒤** 통계를 읽는다(p2 의 피 흘린 주석: 순서를 바꾸면 마지막 시행이 샌다).
    """
    key = "%s|ips%d|c%d|n%d" % (group, ips, cert, n)
    if jr.has(key):
        return jr.get(key)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    p, _sp = B.start_server(cert, fec="off")
    # p2 의 ips_sweep 과 같게 1280 은 -ips 를 주지 않고 quic-go 기본값으로 둔다.
    rows, cs, _err = B.run_client(group, n, fec="off",
                                  ips=(0 if ips == 1280 else ips),
                                  gap_ms=15, expect_k=k)
    B.stop_server(p)
    ss = B.read_server_stats(_sp)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    rec = {"group": group, "ips": ips, "cert": cert, "n": s["n"],
           "ok": s["ok"], "p50": s["p50"],
           "two_rtt_rate": s["two_rtt_rate"],
           "first_flight_bytes": cs.get("first_flight_bytes"),
           "first_flight_datagrams": cs.get("first_flight_datagrams"),
           "n_req": n, "n_failed": s["n"] - s["ok"],
           "n_missing": max(0, n - s["n"]),
           "client_rows": rows, "client_stats": cs, "server_stats": ss,
           "collection_provenance": {"run_id": jr.run_id, "journal_key": key,
                                     "fingerprint": jr.fingerprint,
                                     "started_at": started,
                                     "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                     "expected_k_flush_hint": k,
                                     "time_scope": "collection interval, not individual connection timestamps"},
           "error": _err, "valid": not _err and n > 0 and s["ok"] == s["n"] == n}
    if rec["valid"]:
        jr.record(key, rec)
    else:
        # Failed search bounds may not be returned as the threshold's ref.
        # Preserve every attempted failed unit outside the completed journal.
        if not hasattr(jr, "_p12_failed_probe_units"):
            jr._p12_failed_probe_units = []
        jr._p12_failed_probe_units.append({"key": key, "result": rec,
                                           "journaled": False, "reused": False})
    return rec


def consumed_units(jr):
    """Keep stored probe p50 and provenance; absent old telemetry stays absent."""
    provenance = jr.provenance()
    return {"journal_provenance": provenance,
            "probe_units": [{"key": unit["key"], "result": jr.get(unit["key"])}
                            for unit in provenance["units"]],
            "failed_probe_units": list(getattr(jr, "_p12_failed_probe_units", [])),
            "probe_unit_scope": "completed journal units and separate failed attempts; reused units are prior measurements; recording times are not measurement start times"}


def bisect_threshold(group, ips, k, jr):
    """1-RTT -> 2-RTT 임계 인증서 크기. p2.bisect_threshold 와 같은 절차.

    경계 두 점을 먼저 확인한다(p2 가 그렇게 한다). 하한에서 이미 2-RTT 이거나
    상한에서도 1-RTT 이면 이 설정은 판정 불가이고, 그걸 임계 없음으로
    조용히 넘기면 안 된다 - p2 의 주석대로 **실패는 1-RTT 가 아니다**.
    """
    lo, hi = LO, HI
    r_lo = probe(group, ips, lo, k, N_PROBE, jr)
    r_hi = probe(group, ips, hi, k, N_PROBE, jr)
    log("  경계 확인: cert %d -> ok %d/%d 2RTT %.0f%% / cert %d -> ok %d/%d "
        "2RTT %.0f%%"
        % (lo, r_lo["ok"], r_lo["n"], 100 * (r_lo["two_rtt_rate"] or 0),
           hi, r_hi["ok"], r_hi["n"], 100 * (r_hi["two_rtt_rate"] or 0)))
    a, b = P2.is_two_rtt(r_lo), P2.is_two_rtt(r_hi)
    if a is None or b is None:
        return {"lo": None, "hi": None, "ref": r_lo,
                "note": "경계에서 핸드셰이크 실패 - 판정 불가"}
    if a:
        return {"lo": None, "hi": lo, "ref": r_lo,
                "note": "하한(%d B)에서 이미 2-RTT" % lo}
    if not b:
        return {"lo": hi, "hi": None, "ref": r_lo,
                "note": "상한(%d B)에서도 1-RTT" % hi}
    while hi - lo > RESOLUTION:
        mid = (lo + hi) // 2
        r = probe(group, ips, mid, k, N_PROBE, jr)
        if P2.is_two_rtt(r) is None:
            return {"lo": None, "hi": None, "ref": r_lo,
                    "note": "cert %d 에서 핸드셰이크 실패 - 판정 불가" % mid}
        rate = r["two_rtt_rate"] or 0.0
        if 0.2 < rate < 0.8:
            r = probe(group, ips, mid, k, N_CONFIRM, jr)
            if P2.is_two_rtt(r) is None:
                return {"lo": None, "hi": None, "ref": r_lo,
                        "note": "cert %d 재확인 실패 - 판정 불가" % mid}
            rate = r["two_rtt_rate"] or 0.0
        if rate >= 0.5:
            hi = mid
        else:
            lo = mid
        log("    cert %-6d 2RTT %5.0f%%  ->  구간 [%d, %d]"
            % (mid, 100 * rate, lo, hi))
    return {"lo": lo, "hi": hi, "ref": r_lo, "note": ""}


def usable(rec):
    """판정에 쓸 수 있는 측정인가.

    🩸 여기가 감사에서 뚫린 자리다(2026-08-20). 예전 가드는 `threshold_lo`
    **하나만** 봤다. 그런데 bisect_threshold 의 실패 반환 중 하나가

        {"lo": hi, "hi": None, "note": "상한(16000 B)에서도 1-RTT"}

    라서 `threshold_lo = 16000` 이 들어 있다 - 가드를 그냥 통과한다.
    netem 이 안 걸려 **모든** 설정이 이 실패를 낸 시나리오를 재현하면
    전 설정의 구간이 [16000, None] 으로 똑같아져서

        '부정시험: 1279 와 1280 은 같은 칸'        -> ok=true
        '고원: 1281·1282·1300·1350 은 같은 칸'      -> ok=true

    둘 다 통과했다. **측정 실패가 절벽의 증거로 둔갑한다.** 그래서
    ① 양쪽 끝을 다 보고 ② note 가 붙은 레코드는 아예 뺀다. note 는
    "판정 불가"를 적어 두는 자리이므로, 값이 있어도 믿을 수 없다.
    """
    if not rec:
        return False
    if rec.get("threshold_lo") is None or rec.get("threshold_hi") is None:
        return False
    if rec.get("note"):
        return False
    return True


def mid_of(rec):
    if not usable(rec):
        return None
    return 0.5 * (rec["threshold_lo"] + rec["threshold_hi"])


def same_bin(a, b):
    """두 설정이 같은 칸인가 - 임계 구간이 글자 그대로 같은가로 본다."""
    if not usable(a) or not usable(b):
        return False
    return (a["threshold_lo"] == b["threshold_lo"]
            and a["threshold_hi"] == b["threshold_hi"])


def distinct_bin(a, b):
    """두 설정이 **확실히** 다른 칸인가.

    same_bin 의 부정으로 쓰면 안 된다. 한쪽 측정이 실패해 임계가 없으면
    same_bin 은 False 를 주고, 그 부정은 "다른 칸"이 되어 **측정 실패가
    절벽의 증거로 둔갑한다.** 그래서 양쪽 다 쓸 수 있을 때만 참이다.
    """
    if not usable(a) or not usable(b):
        return False
    return not same_bin(a, b)


def measure(group, ips, k, jr):
    """한 설정을 재고 모형값과 나란히 담는다."""
    log("")
    log("[%s / ips %d] 임계 이분탐색" % (group, ips))
    th = bisect_threshold(group, ips, k, jr)
    ref = th["ref"]
    ffb = ref.get("first_flight_bytes")
    ffd = ref.get("first_flight_datagrams")

    # 예측의 전제: B = k·W. 실측이 이걸 깨면 아래 예측은 전부 근거를 잃는다.
    b_pred = k * ips
    premise = (ffb == b_pred and ffd == k)

    # 모형은 **실측 B** 로만 계산한다.
    # 🩸 예전에는 `b_use = ffb if ffb else b_pred` 였다(2026-08-20 감사 중대 1).
    # `padbed.run_client` 는 timeout 에서 `[], {}, "timeout"` 을 돌려주므로
    # ffb 가 None 이 되고, 그 자리에 **예측값 k·ips** 가 조용히 들어왔다.
    # 그러면 Δ_min·경계 ips 가 실측 없이도 "맞는" 수로 채워져서, 전제 10건이
    # 전부 실패인 재현에서도 보조정리2 검사만 통과했다. 폴백을 없앤다 -
    # 실측이 없으면 계산하지 않고 None 으로 남겨 판정이 실패가 되게 한다.
    b_use = ffb if ffb else None
    k_use = ffd or k
    if b_use:
        allowed = amplif.allowed_bytes(b_use)
        dmin = allowed // 3 - b_use + 1       # 보조정리 2 (B 가 정수라 floor 생략)
        bin_no = allowed // P
        amp = float(allowed) / b_use
        # ceil(dmin/k_use) - 데이터그램마다 나눠 담아야 하므로
        bnd = ips + -(-dmin // max(1, k_use))
    else:
        allowed = dmin = bin_no = amp = bnd = None
    rec = {"group": group, "ips": ips, "k": ffd, "k_expected": k,
           "k_use": k_use,
           "first_flight_bytes": ffb, "first_flight_bytes_pred": b_pred,
           "premise_B_eq_k_ips": premise,
           "allowed_pred": allowed, "bin": bin_no,
           "amp_ratio": amp,
           "delta_min": dmin,
           "boundary_ips": bnd,
           "threshold_lo": th["lo"], "threshold_hi": th["hi"],
           "note": th["note"], "usable": None,
           "jump_from_prev": None, "jump_from_ips": None}
    rec["usable"] = usable(rec)
    rec["threshold_mid"] = mid_of(rec)
    if usable(rec) and b_use:   # 양쪽 끝 + note 까지 본다(usable 주석)
        rec["s0_est"] = amplif.fit_s0(th["lo"], th["hi"], b_use)
        rec["s0_mid"] = rec["s0_est"]["s0_mid"]
    else:
        rec["s0_est"], rec["s0_mid"] = None, None
    pr = PRED.get((group, ips))
    rec["pred_lo"], rec["pred_hi"] = (pr if pr else (None, None))
    # usable() 을 한 번 더 거는 이유: 실패한 측정이 우연히 예측과 같은 수를
    # 들고 있어도 '적중' 으로 적히면 안 된다.
    rec["pred_hit"] = bool(pr and usable(rec)
                           and th["lo"] == pr[0] and th["hi"] == pr[1])
    # 이 예측은 p2 가 이미 관측한 칸을 옮겨 적은 것이다 - out-of-sample 아님.
    rec["in_sample"] = True if pr else None
    rec["pred_gating"] = False
    log("  => B %s B (예측 %d), 허용 %s B (칸 %s), 임계 %s ~ %s B, "
        "s0 %s, Δ_min %s -> 경계 ips %s"
        % (ffb, b_pred, allowed, rec["bin"], th["lo"], th["hi"],
           ("%.1f" % rec["s0_mid"]) if rec["s0_mid"] is not None else "-",
           dmin, rec["boundary_ips"]))
    return rec


# ------------------------------------------------------------------- 판정
def judge(configs, results, info):
    """게이팅 검사는 results 로, 정보는 info 로 간다.

    게이팅 = 전제 · 부정시험 · 절벽 · 고원 · 따름정리 · 보조정리2 ·
             단조성 · 교차. 사전 등록 예측 대조는 **정보**다(add_info 주석).
    """
    by = {}
    for c in configs:
        by[(c["group"], c["ips"])] = c

    # 0. 전제: B = k·ips 를 설정마다 확인한다.
    for c in configs:
        add(results, "전제 B=k·ips [%s/%d]" % (c["group"], c["ips"]),
            c["premise_B_eq_k_ips"],
            "실측 B=%s k=%s, 예측 B=%d k=%d"
            % (c["first_flight_bytes"], c["k"],
               c["first_flight_bytes_pred"], c["k_expected"]))

    # 1. 부정 시험 - 이게 깨지면 "경계는 1281" 이 죽는다.
    a, b = by.get((MAIN_GROUP, 1279)), by.get((MAIN_GROUP, 1280))
    ok = same_bin(a, b) and (a or {}).get("allowed_pred") == (b or {}).get(
        "allowed_pred")
    add(results, "부정시험: ips 1279 와 1280 은 같은 칸", ok,
        "1279 임계 %s~%s (허용 %s) / 1280 임계 %s~%s (허용 %s)"
        % ((a or {}).get("threshold_lo"), (a or {}).get("threshold_hi"),
           (a or {}).get("allowed_pred"), (b or {}).get("threshold_lo"),
           (b or {}).get("threshold_hi"), (b or {}).get("allowed_pred")))

    # 2. 절벽 - 1280 -> 1281 에서 한 칸 뛴다.
    #    🩸 도약은 "직전 ips" 가 아니라 "임계가 나온 직전 ips" 와의 차다
    #    (fill_jumps 주석). 그 실제 비교 대상을 detail 에 같이 찍는다 -
    #    안 찍으면 '1280 -> 1281' 이라 적어 놓고 속으로는 1279 와 비교한
    #    수를 보고할 수 있다.
    c1281 = by.get((MAIN_GROUP, 1281))
    j = c1281.get("jump_from_prev") if c1281 else None
    jfrom = c1281.get("jump_from_ips") if c1281 else None
    add(results, "절벽: ips 1280 -> 1281 에서 임계가 한 칸 도약",
        j is not None and JUMP_LO <= j <= JUMP_HI and jfrom == 1280,
        "도약 %s B (실제 비교 대상 ips %s, 모형 %.1f, 허용창 %.0f~%.0f)"
        % (("%.1f" % j) if j is not None else "판정 불가",
           jfrom if jfrom is not None else "-",
           JUMP_MODEL, JUMP_LO, JUMP_HI))

    # 3. 고원 - 1281 위쪽은 전부 같은 칸. 명세 §8 은 1450 까지 요구한다.
    pl_ips = (1281, 1282, 1300, 1350, 1450)
    plateau = [by.get((MAIN_GROUP, i)) for i in pl_ips]
    ok = (usable(plateau[0])
          and all(same_bin(plateau[0], x) for x in plateau[1:]))
    add(results, "고원: ips 1281·1282·1300·1350·1450 은 같은 칸", ok,
        " / ".join("%d:%s~%s" % (x["ips"], x["threshold_lo"],
                                 x["threshold_hi"])
                   for x in plateau if x) or "자료 없음")

    # 4. 사전 등록한 예측과의 대조 - **정보만**. 종료코드에 넣지 않는다.
    for c in configs:
        if c["pred_lo"] is None:
            continue
        add_info(info, "예측 대조 [%s/%d]" % (c["group"], c["ips"]),
                 c["pred_hit"],
                 "예측 [%d,%d] vs 실측 [%s,%s] (p2 관측 칸을 옮겨 적은 값 - "
                 "out-of-sample 아님)"
                 % (c["pred_lo"], c["pred_hi"], c["threshold_lo"],
                    c["threshold_hi"]),
                 group=c["group"], ips=c["ips"], in_sample=True)

    # 5. 따름정리 Δ_min = 1 과 그 실측 대응.
    #    🩸 `if b:` 로 감싸면 안 된다(2026-08-20 감사 중대 2). 레코드가 없을 때
    #    검사가 실패가 아니라 **결과 목록에서 증발**해서 total 이 같이 줄고,
    #    passed == total 이 되어 종료코드 0 이 된다. 자료가 없으면 명시적으로
    #    ok=False 로 적는다 - usable() 로 세운 원칙과 같은 원칙이다.
    add(results, "따름정리: W=1280 에서 Δ_min=1, 경계 ips=1281",
        bool(b) and b.get("delta_min") == 1
        and b.get("boundary_ips") == 1281 and distinct_bin(b, c1281),
        ("Δ_min %s, 경계 ips %s, 1280 과 1281 이 다른 칸: %s"
         % (b.get("delta_min"), b.get("boundary_ips"),
            "예" if distinct_bin(b, c1281) else "아니오"))
        if b else "ips 1280 레코드 없음 - 판정 불가")

    # 6. 보조정리 2 는 1279 에서도 같은 점을 가리켜야 한다(Δ_min=2 -> 1281).
    #    🩸 전제 가드가 없어서 뚫렸던 자리다(감사 중대 1). delta_min·
    #    boundary_ips 는 실측 B 에서만 나와야 의미가 있으므로, ① 임계 측정이
    #    쓸 수 있고(usable) ② 전제 B=k·ips 가 실측으로 확인된 레코드에서만
    #    판정한다. 그 밖에는 전부 실패다 - 못 잰 것은 통과가 아니다.
    prem_a = bool(a) and usable(a) and bool(a.get("premise_B_eq_k_ips"))
    add(results, "보조정리2: ips 1279 의 Δ_min=2 도 경계 1281 을 가리킨다",
        prem_a and a.get("delta_min") == 2
        and a.get("boundary_ips") == 1281,
        ("Δ_min %s -> 경계 ips %s" % (a.get("delta_min"),
                                      a.get("boundary_ips")))
        if prem_a else
        ("전제 미확인(실측 B=%s, k=%s / 예측 B=%s, 임계 %s~%s, note %r) - "
         "판정 불가"
         % (a.get("first_flight_bytes"), a.get("k"),
            a.get("first_flight_bytes_pred"), a.get("threshold_lo"),
            a.get("threshold_hi"), a.get("note"))
         if a else "ips 1279 레코드 없음 - 판정 불가"))

    # 7. 단조성 - 클라 바이트가 늘면 임계는 줄지 않아야 한다.
    for g in (MAIN_GROUP, CROSS_GROUP):
        seq = [c for c in configs if c["group"] == g
               and c["threshold_mid"] is not None]
        seq.sort(key=lambda c: c["ips"])
        mono = all(seq[i]["threshold_mid"] >= seq[i - 1]["threshold_mid"]
                   for i in range(1, len(seq)))
        add(results, "단조성: %s 임계가 ips 에 대해 비감소" % g,
            mono and len(seq) >= 2,
            " -> ".join("%.1f" % c["threshold_mid"] for c in seq) or "자료 없음")

    # 8. 교차 확인 - ML-KEM(k=2)에서 같은 위치·같은 크기.
    x = by.get((CROSS_GROUP, 1281))
    jx = x.get("jump_from_prev") if x else None
    jxfrom = x.get("jump_from_ips") if x else None
    add(results, "교차: ML-KEM(k=2) 1280 -> 1281 도 한 칸 도약",
        jx is not None and JUMP_LO <= jx <= JUMP_HI and jxfrom == 1280,
        "도약 %s B (실제 비교 대상 ips %s, k=2 이므로 B 는 +2 B 늘었다)"
        % (("%.1f" % jx) if jx is not None else "판정 불가",
           jxfrom if jxfrom is not None else "-"))

    # 9. 교차 고원 - 명세 §8 p12b 의 "1281 과 1350 이 같은 칸".
    cpl = [by.get((CROSS_GROUP, i)) for i in (1281, 1350)]
    add(results, "교차 고원: ML-KEM ips 1281·1350 은 같은 칸",
        usable(cpl[0]) and same_bin(cpl[0], cpl[1]),
        " / ".join("%d:%s~%s" % (y["ips"], y["threshold_lo"],
                                 y["threshold_hi"])
                   for y in cpl if y) or "자료 없음")


def fill_jumps(configs):
    """직전 설정 대비 임계 도약폭.

    🩸 이름이 거짓말을 하고 있었다(감사). 여기서 말하는 '직전'은 **ips 순서상
    직전**이 아니라 **임계가 나온 마지막 ips** 다. 1280 의 측정이 실패하면
    1281 은 조용히 1279 와 비교되는데, 판정 detail 에는 '1280 -> 1281' 이라
    적힌다. 그래서 실제 비교 대상을 `jump_from_ips` 에 같이 남긴다 - 이제
    detail 이 무엇과 뺀 수인지 스스로 말한다.
    """
    for g in (MAIN_GROUP, CROSS_GROUP):
        seq = [c for c in configs if c["group"] == g]
        seq.sort(key=lambda c: c["ips"])
        prev, prev_ips = None, None
        for c in seq:
            m = c["threshold_mid"]
            if prev is not None and m is not None:
                c["jump_from_prev"] = m - prev
                c["jump_from_ips"] = prev_ips
            if m is not None:
                prev, prev_ips = m, c["ips"]


# -------------------------------------------------------------------- p12c
def feasible_ips(group, ips, k, jr):
    """이 ips 가 **정말 그 크기로 나가는가**를 먼저 짧게 잰다.

    1707·2134 는 MTU 1500 을 넘는다. quic-go 는 InitialPacketSize 를
    MaxPacketBufferSize = 1452 로 말없이 깎으므로, 그냥 이분탐색을 돌리면
    임계는 나오지만 그건 **1452 의 임계**다. 그걸 1707 의 임계라고 적으면
    출처가 조작된 숫자가 된다. 그래서 못 보내면 재지 않고 skipped 다.
    """
    r = probe(group, ips, P12C_FEAS_CERT, k, P12C_FEAS_N, jr)
    ffb, ffd = r.get("first_flight_bytes"), r.get("first_flight_datagrams")
    if not (r["n"] > 0 and r["ok"] == r["n"]):
        return False, ("핸드셰이크 %s/%s - 이 크기로는 연결이 안 선다"
                       % (r["ok"], r["n"])), r
    if ffb != k * ips or ffd != k:
        return False, ("실측 B=%s (데이터그램 %s) != k·ips=%d - 스택이 ips 를 "
                       "깎았다(quic-go MaxPacketBufferSize=%d, UDP 페이로드 "
                       "상한 %d)"
                       % (ffb, ffd, k * ips, QUICGO_MAX_PACKET_BUFFER,
                          UDP_PAYLOAD_MAX)), r
    return True, "", r


def run_p12c(jr, checks):
    """명세 §8 p12c - 칸 5·6. **두 모형이 갈리는 지점**이다.

        패킷항 모형(§2.5)  1707 -> 5,831.0   2134 -> 7,076.5
        상수 s0 모형(v1)   1707 -> 5,865.5   2134 -> 7,145.5

    p12 본체와 달리 이 둘은 p2 가 본 적 없는 칸이라 **진짜 out-of-sample** 다.
    다만 게이팅은 아니다 - 보낼 수 있는지부터가 스택 사정이라, 못 보낸 것을
    실패로 세면 절벽 주장이 애먼 이유로 죽는다.
    """
    recs = []
    for ips in P12C_IPS:
        n_bin, pred_pkt, pred_const = P12C_PRED[ips]
        rec = {"group": P12C_GROUP, "ips": ips, "k_expected": P12C_K,
               "bin_expected": n_bin, "in_sample": False, "gating": False,
               "pred_threshold_packet_term": pred_pkt,
               "pred_threshold_const_s0": pred_const,
               "models_diverge_by": round(pred_const - pred_pkt, 1),
               "mtu": MTU, "udp_payload_max": UDP_PAYLOAD_MAX,
               "quicgo_max_packet_buffer": QUICGO_MAX_PACKET_BUFFER,
               "exceeds_mtu": ips > UDP_PAYLOAD_MAX,
               "threshold_lo": None, "threshold_hi": None,
               "threshold_mid": None, "model_supported": None}
        log("")
        log("[p12c %s / ips %d] 먼저 실현 가능성 (MTU %d, UDP 페이로드 상한 "
            "%d, quic-go 상한 %d)"
            % (P12C_GROUP, ips, MTU, UDP_PAYLOAD_MAX,
               QUICGO_MAX_PACKET_BUFFER))
        ok, why, fr = feasible_ips(P12C_GROUP, ips, P12C_K, jr)
        rec["feasibility"] = {
            "cert": P12C_FEAS_CERT, "n": fr["n"], "ok": fr["ok"],
            "first_flight_bytes": fr.get("first_flight_bytes"),
            "first_flight_datagrams": fr.get("first_flight_datagrams"),
            "expected_first_flight_bytes": P12C_K * ips}
        add_info(checks, "p12c: ips %d 를 그 크기로 보낼 수 있는가" % ips, ok,
                 why or ("실측 B=%s = k·ips" % fr.get("first_flight_bytes")),
                 group=P12C_GROUP, ips=ips, in_sample=False)
        if not ok:
            rec["status"] = "skipped"
            rec["skip_reason"] = why
            log("  => skipped: %s" % why)
            log("     (예측은 그대로 남긴다: 패킷항 %.1f vs 상수 s0 %.1f, "
                "차 %.1f B)" % (pred_pkt, pred_const,
                                pred_const - pred_pkt))
            recs.append(rec)
            continue

        m = measure(P12C_GROUP, ips, P12C_K, jr)
        merged = dict(m)
        merged.update(rec)                       # p12c 쪽 값이 이긴다
        merged["threshold_lo"] = m["threshold_lo"]
        merged["threshold_hi"] = m["threshold_hi"]
        merged["threshold_mid"] = m["threshold_mid"]
        merged["status"] = "measured" if usable(m) else "unusable"
        mid = merged["threshold_mid"]
        if mid is not None:
            d_pkt, d_const = abs(mid - pred_pkt), abs(mid - pred_const)
            width = merged["threshold_hi"] - merged["threshold_lo"]
            merged["dist_packet_term"] = round(mid - pred_pkt, 1)
            merged["dist_const_s0"] = round(mid - pred_const, 1)
            merged["grid_width"] = width
            # 두 모형의 간격이 격자 폭보다 좁으면 이 측정으로는 못 가른다.
            merged["models_separable_by_grid"] = bool(
                abs(pred_const - pred_pkt) > width)
            merged["model_supported"] = (
                "packet_term" if d_pkt < d_const
                else ("const_s0" if d_const < d_pkt else "tie"))
            add_info(checks,
                     "p12c: ips %d 임계가 어느 모형에 가까운가" % ips,
                     merged["model_supported"] == "packet_term",
                     "실측 중점 %.1f | 패킷항 %.1f (차 %+.1f) vs 상수 s0 "
                     "%.1f (차 %+.1f) | 격자 폭 %d B, 두 모형 간격 %.1f B "
                     "-> %s"
                     % (mid, pred_pkt, merged["dist_packet_term"],
                        pred_const, merged["dist_const_s0"], width,
                        abs(pred_const - pred_pkt),
                        "가를 수 있다" if merged["models_separable_by_grid"]
                        else "**격자보다 좁아 못 가른다**"),
                     group=P12C_GROUP, ips=ips, in_sample=False)
        else:
            merged["skip_reason"] = m["note"] or "임계 판정 불가"
            add_info(checks, "p12c: ips %d 임계 판정" % ips, False,
                     merged["skip_reason"], group=P12C_GROUP, ips=ips,
                     in_sample=False)
        recs.append(merged)
    return recs


# -------------------------------------------------------------------- 건식
def smoke(jr):
    """경로가 살아 있는지만 본다. 과학적 주장은 하지 않는다.

    ips 2개 x 인증서 2개 x n=6. 인증서는 임계(≈3,340 / ≈4,585 B)를 사이에
    두고 하나씩 골랐다 - 하네스가 살아 있으면 2000 은 1-RTT, 8000 은 2-RTT 로
    갈라져야 한다. 갈라지지 않으면 측정 경로가 아니라 판정 경로가 죽은 것이다.
    """
    results, runs = [], []
    for ips in SMOKE_IPS:
        for cert in SMOKE_CERTS:
            r = probe(MAIN_GROUP, ips, cert, MAIN_K, SMOKE_N, jr)
            runs.append(r)
            log("  ips %-5d cert %-5d  ok %d/%d  p50 %s ms  2RTT %.0f%%  "
                "B %s"
                % (ips, cert, r["ok"], r["n"], r["p50"],
                   100 * (r["two_rtt_rate"] or 0.0),
                   r["first_flight_bytes"]))
    log("")
    for r in runs:
        add(results, "건식: 핸드셰이크 성공 [ips %d/cert %d]"
            % (r["ips"], r["cert"]), r["ok"] == r["n"] and r["n"] > 0,
            "%d/%d 성공" % (r["ok"], r["n"]))
    for r in runs:
        add(results, "건식: B=k·ips [ips %d/cert %d]" % (r["ips"], r["cert"]),
            r["first_flight_bytes"] == MAIN_K * r["ips"]
            and r["first_flight_datagrams"] == MAIN_K,
            "B %s (예측 %d), k %s"
            % (r["first_flight_bytes"], MAIN_K * r["ips"],
               r["first_flight_datagrams"]))
    for r in runs:
        want2 = r["cert"] >= 8000
        got = P2.is_two_rtt(r)
        add(results, "건식: cert %d 는 %s [ips %d]"
            % (r["cert"], "2-RTT" if want2 else "1-RTT", r["ips"]),
            got is not None and got == want2,
            "2RTT 비율 %.0f%%" % (100 * (r["two_rtt_rate"] or 0.0)))
    return results, runs


# -------------------------------------------------------------------- 본체
def main():
    is_smoke = "--smoke" in sys.argv
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()
    B.set_netem(RTT_MS / 2.0)

    fp = code_fingerprint(["experiments/p12_quantum.py",
                           "experiments/p2_threshold.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jname = "p12_smoke_units.jsonl" if is_smoke else "p12_units.jsonl"
    jr = Journal(os.path.join(B.STATE, jname), fp)

    log("=" * 100)
    log("P12 양자 경계 절벽%s   RTT %.0f ms, 격자 [%d,%d] 해상도 %d (폭 ≈56 B), "
        "n %d/%d" % ("  [건식]" if is_smoke else "", RTT_MS, LO, HI,
                     RESOLUTION, N_PROBE, N_CONFIRM))
    log("=" * 100)

    if is_smoke:
        results, runs = smoke(jr)
        npass = sum(1 for r in results if r["ok"])
        # 🩸 행 목록 키는 p6_report.py 가 찾는 이름이어야 한다. p6 는
        # ("configs", "runs", "ips_sweep", …) 순으로 찾고 **먼저 맞는 것 하나만**
        # 쓴다. 건식은 "runs" 에서 잡히므로 "ips_sweep" 별칭은 순수 중복이었다
        # (같은 목록을 두 번 직렬화). 별칭을 뺀다.
        out = {"smoke": True, "rtt_ms": RTT_MS, "n": SMOKE_N,
               **consumed_units(jr),
               "runs": runs,
               "checks": results, "passed": npass, "total": len(results)}
        log("")
        log("건식 %d / %d 통과 - 측정 경로 %s"
            % (npass, len(results),
               "살아 있다" if npass == len(results) else "어딘가 죽었다"))
        log("saved: %s" % B.save("p12_quantum_smoke.json", out))
        return 0 if npass == len(results) else 1

    configs = []
    for ips in MAIN_IPS:
        configs.append(measure(MAIN_GROUP, ips, MAIN_K, jr))
    for ips in CROSS_IPS:
        configs.append(measure(CROSS_GROUP, ips, CROSS_K, jr))
    fill_jumps(configs)

    # p12c 는 **별도 목록**이다. configs 에 섞으면 (a) 단조성·전제 같은
    # 게이팅 검사가 스택이 깎아 버린 ips 를 실패로 세고 (b) fill_jumps 가
    # 칸 4 -> 칸 5 를 '직전 대비'로 잡아 절벽 도약폭을 오염시킨다.
    p12c_checks = []
    p12c = run_p12c(jr, p12c_checks)

    log("")
    log("=" * 100)
    log("%-16s %-6s %-3s %-7s %-8s %-4s %-15s %-9s %-9s %s"
        % ("그룹", "ips", "k", "B", "허용", "칸", "임계", "s0", "Δ_min",
           "직전 대비 (무엇과)"))
    log("-" * 100)
    for c in configs:
        log("%-16s %-6d %-3s %-7s %-8s %-4s %-15s %-9s %-9s %s"
            % (c["group"], c["ips"], c["k"], c["first_flight_bytes"],
               c["allowed_pred"], c["bin"],
               "%s~%s" % (c["threshold_lo"], c["threshold_hi"]),
               ("%.1f" % c["s0_mid"]) if c["s0_mid"] is not None else "-",
               c["delta_min"],
               ("%+.1f B (ips %s)" % (c["jump_from_prev"],
                                      c["jump_from_ips"]))
               if c["jump_from_prev"] is not None else "-"))

    log("")
    log("=" * 100)
    log("p12c (칸 5·6, 두 모형이 갈리는 지점) - 게이팅 아님")
    log("-" * 100)
    for c in p12c:
        log("%-16s %-6d %-9s %-15s 패킷항 %-9.1f 상수s0 %-9.1f  %s"
            % (c["group"], c["ips"], c["status"],
               "%s~%s" % (c["threshold_lo"], c["threshold_hi"]),
               c["pred_threshold_packet_term"],
               c["pred_threshold_const_s0"],
               c.get("model_supported") or c.get("skip_reason", "")))

    log("")
    log("=" * 100)
    log("판정")
    log("=" * 100)
    results, preds = [], []
    judge(configs, results, preds)

    npass = sum(1 for r in results if r["ok"])
    log("")
    log("-" * 100)
    # 🩸 종료코드는 **게이팅 검사만** 센다. 예측 대조(preds)와 p12c 는
    # 정보다 - 그것들이 exit code 를 정하면 헤드라인(절벽)이 애먼 이유로
    # 죽는다(감사 중대 2).
    log("게이팅 %d / %d 통과   (정보: 예측 대조 %d/%d, p12c %d/%d - 종료코드 "
        "무관)"
        % (npass, len(results),
           sum(1 for r in preds if r["ok"]), len(preds),
           sum(1 for r in p12c_checks if r["ok"]), len(p12c_checks)))
    if npass != len(results):
        log("실패 항목(게이팅):")
        for r in results:
            if not r["ok"]:
                log("  - %s | %s" % (r["check"], r["detail"]))

    out = {"smoke": False, "rtt_ms": RTT_MS, "resolution": RESOLUTION,
           **consumed_units(jr),
           "n_probe": N_PROBE, "n_confirm": N_CONFIRM,
           "server_packet_size": P, "jump_model": JUMP_MODEL,
           "jump_window": [JUMP_LO, JUMP_HI],
           "predictions": [{"group": g, "ips": i, "pred_lo": lo,
                            "pred_hi": hi, "gating": False,
                            "in_sample": True}
                           for (g, i), (lo, hi) in sorted(PRED.items())],
           "predictions_out_of_sample": [
               {"group": P12C_GROUP, "ips": i, "bin": n,
                "pred_threshold_packet_term": pk,
                "pred_threshold_const_s0": cs,
                "gating": False, "in_sample": False}
               for i, (n, pk, cs) in sorted(P12C_PRED.items())],
           # p6_report.py 는 ("configs", "runs", "ips_sweep", …) 순으로 행
           # 목록을 찾고 **먼저 맞는 것 하나만** 쓴다. "configs" 에서 잡히므로
           # 예전의 "ips_sweep" 별칭은 순수 중복이었다 - 뺐다.
           "configs": configs,
           "p12c": p12c, "p12c_checks": p12c_checks,
           "checks": results, "prediction_checks": preds,
           "passed": npass, "total": len(results),
           # 🩸 게이팅 집합이 이번 라운드에 바뀌었다(예측 대조 8건이 게이팅에서
           # 빠지고, 조건부라 증발하던 따름정리·보조정리2 2건이 항상 기록되어
           # 게이팅 19건). forever.py 는 checks 이름 목록으로 basis_changes 를
           # 추적하므로 다음 라운드에 **기준 교체**로 잡힌다. 그게 결과가
           # 흔들린 것이 아니라 의도된 교체임을 이력에 남긴다.
           "gating_changed_at": "2026-08-20",
           "gating_note": ("passed/total 은 게이팅 검사만 센다. "
                           "prediction_checks 와 p12c_checks 는 gating=false "
                           "정보이며 종료코드에 들어가지 않는다. "
                           "2026-08-20 게이팅 집합 교체: 예측 대조 8건을 "
                           "정보로 내리고(p2 관측 칸을 옮겨 적은 값이라 "
                           "out-of-sample 이 아님), 레코드가 없으면 조용히 "
                           "사라지던 따름정리·보조정리2 2건을 항상 기록하도록 "
                           "바꿔 게이팅 19건이 됐다. 보조정리2 는 전제 "
                           "B=k·ips 가 실측으로 확인된 레코드에서만 판정한다.")}
    log("saved: %s" % B.save("p12_quantum.json", out))
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
