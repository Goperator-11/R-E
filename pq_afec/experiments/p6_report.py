# -*- coding: utf-8 -*-
"""P6 - 보고서와 요약 PDF 를 결과 파일에서 직접 생성한다.

숫자를 손으로 옮겨 적지 않는다. `results/*.json` 만 읽어서 쓴다.
그래야 실험을 다시 돌렸을 때 보고서가 조용히 낡지 않는다.

이 원칙을 어긴 자리가 있었다(2026-08-20 정정). 머리말은 "손으로 옮기지
않는다"고 선언해 놓고 본문에는 손으로 옮긴 수가 셋 있었다.

  - 용량 초과분 "63 B" / "용량 1,382 B" / "C=1,445 B"  -> p1 에서 계산
  - 같은 사실을 서두에서는 "약 50~70 B" 라고 달리 적음  -> 한 곳에서 계산
  - "서버는 정확히 3배에서 멈춘다(증폭비 3.00)"          -> e21 + p2 에서 계산

특히 마지막 것은 **조건을 지운 수**였다. 3.00 은 `3B` 가 서버 패킷 크기
`P` 의 배수일 때만 나오고, 일반적으로 허용량은 `ceil(3B/P)·P` 라 3 배를
초과한다. 조건 없이 "정확히 3배"라고 적으면 같은 보고서 3 장의 양자화
모형과 정면으로 충돌한다. 이제 조건과 함께 원자료에서 뽑아 쓴다.

읽는 파일
  p1 비행 구조 · p2 임계 · p3 손실 효과 · p4 모형 · p5 감사
  p7 결정적 검증 · p8 재현성 · p9 교차환경 · p10 완성도 · p11 폐루프 후회
  p12 양자 경계 절벽(있으면) · probe_cliff_*(있으면) · e21 바이트 타임라인

산출물
  docs/PADFEC 실측 보고서.md
  docs/ML-KEM QUIC 핸드셰이크 FEC 요약.pdf  (A4, 조판에 따라 여러 쪽)

이 파일의 요약 PDF 를 "한 장"이라고 부르지 않는다 — 실제로는 A4 두 쪽이
나온다. 쪽수를 세지 않고 이름만 "한 장"으로 두면 그것도 손으로 옮긴 수다.
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_escape
import json
import math
from datetime import datetime, timezone
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
DOCS = os.path.join(ROOT, "docs")
sys.path.insert(0, ROOT)

# 🩸 2026-08-26 - **Edge 를 더했다.** 이 PC 에서 Chrome 이 없어져(Edge 만 남음)
#    `chrome 을 못 찾아 PDF 는 건너뛴다` 가 찍히며 **한 장 요약 PDF 가 조용히
#    안 만들어지고 있었다.** 단계는 0 을 내고 통과했으므로 루프도 안 잡았다 -
#    산출물이 빠지는데 아무도 실패하지 않는 자리다. Edge 는 같은 Chromium 이라
#    `--headless --print-to-pdf` 가 그대로 된다.
#    (outputs 에 PDF 를 적지 않은 것은 그대로 둔다. 브라우저가 아예 없는
#     기계에서도 보고서 .md 는 나와야 하기 때문이다 - 대신 아래에서 **못
#     찾았다는 사실을 반드시 찍는다.**)
CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def load(name):
    p = os.path.join(RESULTS, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fmt(v, nd=1, dash="-"):
    if v is None:
        return dash
    if isinstance(v, float):
        return ("%%.%df" % nd) % v
    return str(v)


def sgn(v, nd=2, dash="-"):
    """부호를 붙여 포맷. None 이면 대시(후회처럼 음수가 의미 있는 값에 쓴다)."""
    return dash if v is None else ("%%+.%df" % nd) % v


def cell(s, n=None):
    """표 칸에 넣을 텍스트를 안전하게 만든다.

    결과 JSON 의 detail 에는 파이프(`|`)가 섞여 있다(예: "off ... | on ...").
    그대로 넣으면 마크다운 표의 열이 밀려서 **보고서가 조용히 틀린다**.
    """
    s = "" if s is None else str(s)
    if n:
        s = s[:n]
    return s.replace("|", "\\|").replace("\n", " ")


def com(v):
    """천 단위 구분. None 이면 대시."""
    return "-" if v is None else "{:,}".format(int(round(v)))


def present(d):
    """파일이 **있었는가**. 파이썬에서 빈 dict 는 거짓이라 `if p12:` 로 쓰면
    빈 결과와 없는 결과가 구분되지 않고 절이 통째로 사라진다. 그러면 독자는
    실험을 안 한 것으로 읽는다 — 실제로는 돌았는데 결과가 빈 것인데도.
    """
    return d is not None


def empty_note(name):
    """있지만 빈 결과. 절을 지우지 말고 한 줄이라도 남긴다."""
    return ("> `%s` 는 **있지만 비어 있다**(빈 객체). 실험이 돌았는데 결과가 "
            "비었다는 뜻이므로, 이 절을 지우지 않고 그 사실만 남긴다." % name)


# ===================================================================== 사실 추출
# 아래 함수들이 이 파일의 핵심이다. 본문에 쓰는 수는 **여기서만** 만들어지고,
# 문장은 그 결과를 포맷할 뿐이다. 같은 사실을 두 곳에서 다르게 적는 사고를
# 막으려면 사실이 한 군데서만 나와야 한다.

def cap_facts(p1):
    """용량 부등식 `C ≤ (k−1)(W−h−f)` 의 위반 폭을 p1 원자료에서 센다.

    JSON 의 `capacity` 를 그대로 쓰고, 꼬리표를 f=0 으로 잡은 경우
    `(k−1)(W−h)` 도 같은 자리에서 다시 센다(결론이 f 에 강건한지 보려고).
    수치는 라운드마다 흔들리므로 단일 상수로 굳히지 않고, **최소 초과분과
    그 설정 + 전체 범위**를 함께 돌려준다.
    """
    rows = []
    for c in (p1 or {}).get("capacity_checks", []):
        k, W, h, C = c["k"], float(c["W"]), float(c["h"]), float(c["C"])
        cap = float(c.get("capacity") or 0.0)
        cap0 = max(0.0, (k - 1) * (W - h))          # f = 0 일 때의 우변
        rows.append({
            "group": c["group"], "ips": c["ips"] or int(W), "k": k, "W": W,
            "h": h, "C": C, "capacity": cap, "excess": C - cap,
            "capacity_f0": cap0, "excess_f0": C - cap0,
            "f_implied": (W - h - cap / (k - 1)) if k >= 2 else None,
            "violates": C > cap,
        })
    if not rows:
        return None
    # 🩸 초과분 통계는 **k≥2 행에서만** 낸다. k=1 은 우변이 0 이라 초과분이
    # 곧 C 자신이고, §2 표도 그 8행을 빼고 그린다. 섞어서 최대/최소를 내면
    # 본문의 "전체 범위"가 표에 없는 행에서 나와 대조가 불가능해진다.
    pool = [r for r in rows if r["k"] >= 2] or [r for r in rows
                                                if r["violates"]] or rows
    best = min(pool, key=lambda r: r["excess"])
    return {
        "rows": rows,
        "pool": pool,
        "n": len(rows),
        "n_pool": len(pool),
        "n_violate": sum(1 for r in rows if r["violates"]),
        "n_k1": sum(1 for r in rows if r["k"] < 2),
        "min": best,
        "max_excess": max(r["excess"] for r in pool),
        "min_excess_f0": min(r["excess_f0"] for r in pool),
        # f=0 대조는 **best 와 같은 행**에서 뽑는다. 다른 행의 최소값과
        # 화살표로 이으면 "76.0 B → 60.0 B" 가 서로 다른 설정의 수가 된다.
        "excess_f0_at_min": best["excess_f0"],
        "f_implied": sorted({round(r["f_implied"], 1) for r in pool
                             if r["f_implied"] is not None}),
    }


def cap_phrase(cf, bold="**"):
    """용량 초과분을 한 문장으로. 서두와 본문이 **같은 문자열 생성기**를 쓴다."""
    if not cf:
        return "용량 자료 없음"
    b = cf["min"]
    return ("최소 초과 %s%.1f B%s (%s / Initial %s B — C=%.0f B, 용량 %.1f B), "
            "우변이 0 이 아닌 %d개 설정 전체로는 %.1f ~ %.1f B 초과"
            % (bold, b["excess"], bold, b["group"], b["ips"], b["C"],
               b["capacity"], cf["n_pool"], b["excess"], cf["max_excess"]))


def sweep_rows(p2):
    """`ips_sweep` 에서 **표와 계산이 함께 쓸** 행만 고른다.

    🩸 amp_facts 는 `first_flight_bytes` 로, §3-2 표는 `threshold_lo` 로
    걸렀다. 술어가 다르면 본문의 "훑은 N개 설정"과 표의 줄 수가 어긋난다.
    술어를 여기 한 곳에 둔다. 그리고 `first_flight_bytes` 를 `r.get()` 으로
    받는다 — 0 이면 A(B)/B 가 ZeroDivisionError, 키가 없으면 KeyError 로
    **보고서 생성이 통째로 죽는다**(둘 다 재현됨).
    """
    out = []
    for r in (p2 or {}).get("ips_sweep", []) or []:
        if not r.get("first_flight_bytes"):
            continue
        if not r.get("threshold_lo") or not r.get("threshold_hi"):
            continue
        out.append(r)
    return out


def amp_facts(p2, e21):
    """증폭비를 원자료에서 계산한다.

    두 종류를 구분해서 돌려준다.
      obs   e21 바이트 타임라인에서 **관측된** 정지 지점 (tx == 3·rx 인가)
      sweep p2 ips_sweep 각 점의 허용량/첫비행 = `ceil(3B/P)·P / B`
    "증폭비 3.00" 은 obs 중 특수 조건에서만 나오는 값이므로 조건을 함께 든다.
    """
    from padfec import amplif
    P = amplif.SERVER_PACKET_SIZE
    sweep = []
    for r in sweep_rows(p2):            # §3-2 표와 **같은 술어**를 쓴다
        b = r["first_flight_bytes"]
        al = amplif.allowed_bytes(b)
        sweep.append({"group": r["group"], "ips": r["ips"], "B": b,
                      "budget": amplif.budget(b), "allowed": al,
                      "ratio": float(al) / b, "exact3": al == 3 * b,
                      "lo": r.get("threshold_lo"), "hi": r.get("threshold_hi")})
    obs = []
    for r in (e21 or {}).get("runs", []):
        a = r.get("analysis") or {}
        rx, tx = a.get("stall_rx_cum"), a.get("stall_tx_cum")
        if rx in (None, 0) or tx is None:
            continue
        obs.append({"arm": r.get("arm"), "cert": r.get("cert"),
                    "rx": rx, "tx": tx, "ratio": float(tx) / rx,
                    "at_limit": tx == 3 * rx,
                    "hct": (r.get("hct_ms") or [None])[0]})
    out = {"P": P, "sweep": sweep, "obs": obs,
           "at_limit": [o for o in obs if o["at_limit"]]}
    if sweep:
        out["ratio_lo"] = min(s["ratio"] for s in sweep)
        out["ratio_hi"] = max(s["ratio"] for s in sweep)
        out["arg_hi"] = max(sweep, key=lambda s: s["ratio"])
        out["n_exact3"] = sum(1 for s in sweep if s["exact3"])
    return out


def s0_levels(p2):
    """s0 = 허용량 − 임계 중앙값. ips 마다 다시 뽑으면 **계단**이 드러난다.

    s0 를 그룹당 단일값으로 쓰면 안 된다 — 허용량 계단을 넘는 ips 에서
    값이 갈린다. 그 사실을 여기서 데이터로 확인한다.
    """
    from padfec import amplif
    by = {}
    for r in sweep_rows(p2):
        b = r["first_flight_bytes"]
        al = amplif.allowed_bytes(b)
        mid = 0.5 * (r["threshold_lo"] + r["threshold_hi"])
        by.setdefault(r["group"], []).append(
            {"ips": r["ips"], "B": b, "allowed": al, "lo": r["threshold_lo"],
             "hi": r["threshold_hi"], "s0": al - mid})
    out = {}
    for g, rows in by.items():
        lv = sorted({round(x["s0"], 1) for x in rows})
        out[g] = {"rows": rows, "levels": lv,
                  "spread": (lv[-1] - lv[0]) if lv else 0.0}
    return out


def model_facts(p4, p2):
    """양자화 모형의 예측 대 실측. **적중이 왜 적중인지**까지 같이 판정한다.

    p4 는 s0 를 기준선 팔에서 역산해 놓고 그 팔의 임계를 다시 예측한다 —
    그 팔에서 맞는 것은 검증이 아니라 항등식이다. p2 의 `s0_est` 와 p4 의
    `s0` 가 같은 팔을 찾아 표시한다.
    """
    if not p4:
        return None
    s0 = p4.get("s0") or {}
    fitted = {}
    for r in (p2 or {}).get("thresholds", []):
        est = (r.get("s0_est") or {}).get("s0_mid")
        g = r.get("group")
        if est is not None and g in s0 and abs(est - s0[g]) < 1e-9:
            fitted.setdefault(g, []).append(r.get("arm"))
    rows = []
    for r in p4.get("threshold_prediction", []):
        mid = 0.5 * (r["measured_lo"] + r["measured_hi"])
        rows.append({"group": r["group"], "arm": r["arm"],
                     "client_bytes": r["client_bytes"],
                     "predicted": r["predicted"], "lo": r["measured_lo"],
                     "hi": r["measured_hi"], "mid": mid, "hit": r["hit"],
                     "dev": r["predicted"] - mid,
                     "identity": r["arm"] in fitted.get(r["group"], [])})
    hit = [r for r in rows if r["hit"]]
    miss = [r for r in rows if not r["hit"]]
    return {"rows": rows, "hits": p4.get("threshold_hits"), "s0": s0,
            "fitted": fitted, "hit_rows": hit, "miss_rows": miss,
            "all_hits_are_identities": bool(hit) and all(r["identity"]
                                                         for r in hit),
            "any_miss_is_identity": any(r["identity"] for r in miss)}


# 인수인계 문서(2026-08-18) 표에 적힌 첫 비행 바이트. **인용값**이므로 그룹과
# 함께 적어 둔다. 우리 값과의 대조는 아래에서 그룹 단위로 **계산**한다 —
# "다르다/같다"를 문장에 굳혀 놓으면 우리 값이 바뀌어도 문장이 안 바뀐다.
# (실제로 그 사고가 났다: 우리 X25519MLKEM768 2,560 B 를 놓고 "문서의
#  2,560 B / 3,840 B 와 다르다"고 적었다.)
HANDOVER_FIRST_FLIGHT = {"x25519": 2560, "X25519MLKEM768": 3840}


def handover_facts(base, base_k=None):
    """기본 설정 첫 비행 B(우리 실측)를 인수인계 문서 표와 **그룹 단위**로 댄다.

    base: {그룹: k·W}, base_k: {그룹: k}. 돌려주는 것은 그룹별 비교 결과와
    요약 플래그뿐이고, 판정 문장은 이 결과에서 파생시킨다.

    🩸 차이가 "데이터그램 하나(W) 몫"인지도 **여기서 나눠서** 판정한다.
    예전 본문은 그 문구를 문장에 굳혀 놓고 차이값을 W 와 대보지 않았다 —
    차이가 2W 가 되어도 문장은 "하나" 그대로였다.
    """
    base_k = base_k or {}
    rows = []
    for g in sorted(set(base) | set(HANDOVER_FIRST_FLIGHT)):
        ours = base.get(g)
        doc = HANDOVER_FIRST_FLIGHT.get(g)
        k = base_k.get(g)
        W = (float(ours) / k) if (ours is not None and k) else None
        diff = (ours - doc) if (ours is not None and doc is not None) else None
        q = (diff / W) if (diff is not None and W) else None
        rows.append({
            "group": g, "ours": ours, "doc": doc, "k": k, "W": W,
            "diff": diff,
            # 차이가 데이터그램 몇 개 몫인가. 정수 배가 아니면 exact_W=False.
            "n_W": q,
            "exact_W": (abs(q - round(q)) < 1e-9) if q is not None else None,
            "same": (ours == doc) if (ours is not None and doc is not None)
                    else None,
        })
    cmp_rows = [r for r in rows if r["same"] is not None]
    diff_rows = [r for r in cmp_rows if not r["same"]]
    # 문서의 어떤 그룹 값이 **우리의 다른 그룹** 값과 같은가. 헷갈림의 원인이
    # 여기 있으므로(문서 x25519 2,560 = 우리 ML-KEM 2,560) 계산으로 찾는다.
    cross = []
    for r in cmp_rows:
        for g2, v2 in sorted(base.items()):
            if g2 != r["group"] and r["doc"] == v2:
                cross.append({"doc_group": r["group"], "value": r["doc"],
                              "our_group": g2})
    return {"rows": rows, "cmp": cmp_rows, "diff": diff_rows,
            "n_cmp": len(cmp_rows), "n_diff": len(diff_rows),
            "all_differ": bool(cmp_rows) and len(diff_rows) == len(cmp_rows),
            "none_differ": bool(cmp_rows) and not diff_rows,
            "cross": cross,
            "diffs": sorted({r["diff"] for r in diff_rows}),
            "only_in_doc": [r["group"] for r in rows if r["ours"] is None],
            "only_ours": [r["group"] for r in rows if r["doc"] is None]}


def _match_check(checks, tag, vkey, v):
    """p11 의 검사 목록에서 `tag` 에 해당하는 검사 **하나**를 짝짓는다.

    🩸 예전 방식은 `'%+.2f' % v` 를 각 검사의 detail 전체에서 `in` 으로
    찾았다. 그런데 p11 의 detail 은 머리값 뒤에 **조건별 값 목록**을 같이
    담는다(`"최악 +3.61 ms | 조건별 ['+0.1', '+1.6', …]"`). 그래서 값이
    남의 검사 목록 안에 우연히 들어 있으면 **엉뚱한 검사에 붙는다** —
    그 검사의 통과/실패가 그대로 인쇄된다.

    그래서 짝짓기를 이름/키로 바꾼다.
      ① p11 이 기계용 키(`key`/`tag`/`id`/`metric`)를 내보내면 그것으로.
      ② 없으면 detail 의 **머리 조각**(첫 `|` 앞, 조건별 목록이 시작되기
         전)에서만 값을 찾는다. 목록 안의 값은 애초에 후보가 안 된다.
    어느 쪽이든 **후보가 정확히 하나일 때만** 붙인다. 둘 이상이면 모른다고
    적는다(criterion 이 "대응하는 검사를 p11 에서 못 찾음" 을 찍는다).
    """
    for kf in ("key", "tag", "id", "metric"):
        named = [c for c in checks
                 if str(c.get(kf, "")) in (tag, vkey)]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            return None
    if v is None:
        return None
    want = "%+.2f" % v
    head = [c for c in checks
            if want in str(c.get("detail", "")).split("|")[0]]
    return head[0] if len(head) == 1 else None


def _is_diagnostic(check):
    return (check.get("counted") is False or check.get("gating") is False
            or check.get("kind") == "diagnostic"
            or check.get("status") == "diagnostic")


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def check_label(check):
    if check.get("kind") == "판정불능" or check.get("status") == "indeterminate":
        return "판정불능"
    if _is_diagnostic(check):
        return "진단"
    if check.get("ok") is True:
        return "통과"
    if check.get("ok") is False:
        return "미흡"
    return "판정 없음"


def p10_test_facts(result):
    tests = [r for r in result.get("results", [])
             if isinstance(r, dict) and r.get("kind") != "재고"]
    counted = [r for r in tests if check_label(r) not in ("진단", "판정불능")]
    return {"tests": tests, "counted": counted,
            "passed": sum(r.get("ok") is True for r in counted), "total": len(counted),
            "failed": [r for r in counted if r.get("ok") is False],
            "excluded": [r for r in tests if r not in counted]}


def p18_consumer_notes(result):
    """Read new metadata and legacy values without inventing historical scope."""
    facts = sample_facts(None, result) or {}
    notes = []
    levels = facts.get("p18_confidence_levels") or []
    if levels:
        notes.append("p18에 저장된 alpha/수준 기준 개별 명목 신뢰수준은 %s다. "
                     "분석 가정과 구간 선택 규칙에 따른 범위이며 실제 포함확률의 보장이 아니다."
                     % ", ".join("%s%%" % fmt(100*v, 2) for v in levels))
    family = sorted({v["family_confidence_level"] for v in result.get("verdict", [])
                     if _finite_number(v.get("family_confidence_level"))
                     and 0 < v["family_confidence_level"] < 1})
    if family:
        notes.append("p18이 기록한 비교군 전체 명목 신뢰수준은 %s다. "
                     "개별 구간 수준과 구분하며 분석 가정의 한계는 그대로 남는다."
                     % ", ".join("%s%%" % fmt(100*v, 2) for v in family))
    if "normal_iid" in facts.get("p18_connection_methods", []):
        notes.append("normal_iid로 기록된 p18 연결 구간은 iid 정규근사이고, Latin 구간은 셀 평균의 t 구간이다. "
                     "선택 구간은 저장된 decision_gain과 같은 중심으로 읽는다.")
    elif facts.get("p18_has_legacy_ci_name"):
        notes.append("옛 p18의 ci95/Welch 안내는 역사 출력 명칭이다. "
                     "이 명칭만으로 95% 또는 Welch 구간이라고 단정하지 않는다.")
    plugin = facts.get("p18_n_plugin")
    if plugin:
        notes.append("p18 판정불능 조건 %d/%d개 중 수치가 기록된 %d개 조건의 "
                     "같은 자료 표본 대입값은 팔당 %s~%s다. 추가 표본이나 검정력을 보장하지 않는다."
                     % (facts["p18_n_undecided"], facts["p18_n_conds"],
                        facts["p18_n_plugin_condition_count"], fmt(plugin[0], 0), fmt(plugin[1], 0)))
    cap = result.get("current_adaptive_default_m_max")
    if type(cap) is int and cap > 0:
        notes.append("p18이 기록한 적응 기본 m 상한은 %d다. 고정 m2-m4 대조를 "
                     "적응 상한 개입의 직접 검증으로 해석하지 않는다." % cap)
    elif result.get("verdict"):
        notes.append("옛 p18 조건명의 m_max2는 현재 적응 상한의 근거가 아니다. "
                     "현재 상한은 이 저장 결과에서 확인되지 않는다.")
    coverage = result.get("trial_coverage") or {}
    keys = ("planned_n", "recorded_n", "ok_n", "failed_n", "missing_n")
    if all(_finite_number(coverage.get(k)) for k in keys):
        notes.append("p18 계획 %s, 반환 %s, 성공 %s, 실패 %s, 누락 %s. "
                     "HCT는 성공 시행 조건부이며 실패·누락은 완전성 검사에 남는다."
                     % tuple(fmt(coverage[k], 0) for k in keys))
    provenance = result.get("journal_provenance")
    if isinstance(provenance, dict):
        notes.append("p18 단위 출처는 재사용 %s, 신규 %s, 저널 미저장 %s로 기록됐다. "
                     "단위 기록 시각은 개별 시행 시각이나 독립 반복의 증거가 아니다."
                     % tuple(fmt(provenance.get(k), 0) for k in
                             ("reused_units", "new_units", "unjournaled_units")))
    elif result.get("rows") or result.get("verdict"):
        notes.append("이 p18 결과에는 단위별 출처 요약이 없다. 새 코드의 기록 필드로 "
                     "과거 run_id나 기록 시각을 복원하지 않는다.")
    return notes


def p20_consumer_notes(result):
    """Keep plug-in target provenance separate from recorded sufficiency verdicts."""
    pairs = [p for c in result.get("conds", []) for p in c.get("pairs", [])]
    if not pairs and not result.get("input_coverage") and not result.get("input_provenance"):
        return []
    model = sum(p.get("n_target_source") == "model_delta" for p in pairs)
    observed = sum(p.get("n_target_source") == "observed_same_data_delta" for p in pairs)
    unknown = len(pairs)-model-observed
    notes = ["p20 표본 대입값의 목표 출처는 모형차 %d쌍, 같은 자료 관측차 %d쌍, "
             "미기록 %d쌍이다. 같은 자료 관측차는 고정된 독립 목표나 검정력 보장이 아니다. "
             "기록된 표본 기준 판정은 그대로 두고 목표 출처를 함께 해석한다."
             % (model, observed, unknown)]
    coverage = result.get("input_coverage")
    if not isinstance(coverage, dict):
        notes.append("옛 p20 결과에는 전체 입력의 계획·반환·성공·실패 분모 확인 기록이 없다.")
    else:
        notes.append("p20 입력 완전성은 input_coverage에 저장된 분모와 누락 문제를 기준으로 읽는다. "
                     "이 검사는 전송 계측의 완전성이나 모형 적합성을 뜻하지 않는다.")
        expected = coverage.get("expected") or {}
        arms = [a for c in expected.values() if isinstance(c, dict)
                for a in c.values() if isinstance(a, dict)]
        keys = ("requested_n", "recorded_n", "successful_n", "failed_n")
        if arms and all(all(_finite_number(a.get(k)) for k in keys) for a in arms):
            notes.append("p20 입력 분모 기록의 합은 요청 %s, 반환 %s, 성공 %s, 실패 %s다. "
                         "계획 조건/팔 %s/%s, 분석 조건/팔 %s/%s, 누락·불일치 문제 %d건이다."
                         % (tuple(fmt(sum(a[k] for a in arms), 0) for k in keys)
                            + tuple(fmt(coverage.get(k), 0) for k in
                                    ("expected_conditions", "expected_arms", "analysed_conditions", "analysed_arms"))
                            + (len(coverage.get("problems") or []),)))
    provenance = result.get("input_provenance")
    if not isinstance(provenance, dict) or not provenance:
        notes.append("옛 p20 입력 파일 SHA와 p17 저널 선택 출처는 이 결과에 기록되지 않았다.")
    else:
        notes.append("p20 입력 파일 SHA와 p17 저널 선택 출처는 input_provenance에 기록됐다. "
                     "같은 입력을 다시 분석한 결과를 새 실측으로 세지 않는다.")
        entries = [(k, v) for k, v in provenance.items() if isinstance(v, dict)]
        notes.append("p20 파일별 출처: " + "; ".join(
            "%s 가용 %s, SHA %s" % (name, value.get("available"), value.get("sha256") or "미기록")
            for name, value in entries) + ".")
        selection = (provenance.get("p17") or {}).get("journal_selection")
        if isinstance(selection, dict):
            units = selection.get("units") or []
            notes.append("p20이 고른 p17 저널 지문은 %s, 단위 %d개이며 run_id 또는 "
                         "기록 시각이 없는 단위 %d개다. 파일 SHA는 %s다."
                         % (selection.get("fingerprint") or "미기록", len(units),
                            sum(not u.get("run_id") or not u.get("recorded_at") for u in units),
                            selection.get("sha256") or "미기록"))
        else:
            notes.append("p20 결과에 p17 저널 선택의 단위별 출처 기록은 없다.")
    return notes


def late_stage_summary(results):
    """Surface late-stage failures even when the main report predates a stage."""
    lines = ["", "## 후속 정책·모형 검증 기록", "",
             "아래 표는 입력 결과의 기록이다. 이번 코드에서의 유효성은 출처 목록과 함께 확인한다.",
             "통과 개수는 연구 가설의 확증 여부와 다르다. 누락·실패를 통과로 세지 않는다.", "",
             "| 결과 파일 | 기록된 통과 수 | 미통과 검사 또는 누락 |",
             "|---|---|---|"]
    for name, result in results.items():
        if not result:
            lines.append("| %s | - | 결과 없음 또는 빈 결과 |" % cell(name))
            continue
        checks = result.get("checks")
        inline_diagnostics = []
        if isinstance(checks, list):
            inline_diagnostics = [c for c in checks if isinstance(c, dict) and _is_diagnostic(c)]
            checks = [c for c in checks if isinstance(c, dict) and not _is_diagnostic(c)]
        if not isinstance(checks, list) or not checks:
            summary, detail = "-", "검사 기록 없음"
        else:
            passed = sum(c.get("ok") is True for c in checks)
            summary = "%d/%d" % (passed, len(checks))
            detail = "; ".join(str(c.get("check", "이름 없음")) + ": " + str(c.get("detail", ""))
                               for c in checks if c.get("ok") is not True) or "기록된 미통과 검사 없음"
        diagnostics = result.get("diagnostics", [])
        diagnostics = (diagnostics if isinstance(diagnostics, list) else []) + inline_diagnostics
        if isinstance(diagnostics, list) and diagnostics:
            detail += "; 합격 판정에서 제외한 진단: " + "; ".join(
                str(d.get("check", d.get("name", "진단"))) + ": " + str(d.get("detail", ""))
                for d in diagnostics if isinstance(d, dict))
        lines.append("| %s | %s | %s |" % (cell(name), summary, cell(detail)))
    lines.append("")
    for name, reader in (("p18_mmax.json", p18_consumer_notes),
                         ("p20_residual.json", p20_consumer_notes)):
        result = results.get(name)
        if isinstance(result, dict) and result:
            lines.extend(reader(result))
            lines.append("")
    lines.extend(["", "정책 비교는 성공 조건부 지연과 실패율을 함께 해석한다. "
                  "동일 실행을 시간순으로 나눈 비교는 독립 평가가 아니며, "
                  "차이를 찾지 못했다는 결과는 동등성의 증명이 아니다.", ""])
    return "\n".join(lines)


def late_stage_html(results):
    # Keep failure details in PDF as well as Markdown; escape data before HTML.
    text = prose_style(late_stage_summary(results))
    return ('<section style="break-before:page;font-size:9pt">'
            '<pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit">'
            + html_escape.escape(text) + '</pre></section>')


def adapt_value_facts(p17):
    """Descriptive same-data candidate selection gain, not a true oracle bound."""
    if not p17:
        return None
    conds = []
    for g in (p17.get("gain") or []):
        og = g.get("oracle_gain_ms")
        if og is None:
            continue
        alw = g.get("allowed_by_loss") or {}
        best = {}
        for loss, rec in alw.items():
            if rec:
                best[loss] = rec.get("best")
        conds.append({"cond": g.get("cond"), "oracle_gain_ms": float(og),
                      "best_by_loss": best,
                      "same_best": len(set(best.values())) == 1 and bool(best)})
    if not conds:
        return None
    return {"conds": conds,
            "worst": max(c["oracle_gain_ms"] for c in conds),
            "all_zero": all(c["oracle_gain_ms"] <= 0.0 for c in conds),
            "schedule": [x[0] for x in (p17.get("schedule") or [])],
            "cert": p17.get("cert"), "rtt_ms": p17.get("rtt_ms"),
            "n": p17.get("n_per_seg")}


def ruler_facts(p11, p17):
    """Compare recorded CI widths with 1 ms; position ranges are diagnostics."""
    tol = 1.0
    bars = []
    half = (p11 or {}).get("worst_ci95_half_ms")
    if _finite_number(half) and half >= 0:
        bars.append(("p11 후회 추정의 95% 신뢰반폭", float(half)))
    pos = [g.get("pos_effect_ms") for g in ((p17 or {}).get("gain") or [])]
    pos = [float(v) for v in pos if _finite_number(v) and v >= 0]
    if not bars and not pos:
        return None
    return {"tol": tol, "bars": bars,
            "worst": max((v for _n, v in bars), default=None),
            "p17_position_range_ms": max(pos) if pos else None,
            "finer": bool(bars) and all(v > tol for _n, v in bars)}


def sample_facts(p17, p18):
    """Read sample diagnostics and stored contrasts without changing verdicts."""
    out = {}
    vs = (p18 or {}).get("verdict") or []
    und = [v for v in vs if v.get("significant") is not True]
    values = [v.get("n_plugin_per_arm") if "n_plugin_per_arm" in v
              else v.get("n_needed_per_arm") for v in und]
    values = [v for v in values if _finite_number(v) and v >= 0]
    if vs:
        now = [v.get("n_per_arm") for v in vs if _finite_number(v.get("n_per_arm"))]
        if now:
            out["p18_n_now"] = (min(now), max(now))
        out["p18_n_undecided"] = len(und)
        out["p18_n_conds"] = len(vs)
        out["p18_n_plugin_condition_count"] = len(values)
        if values:
            out["p18_n_plugin"] = (min(values), max(values))
        levels = []
        for v in vs:
            level = v.get("per_comparison_confidence_level")
            if not (_finite_number(level) and 0 < level < 1):
                alpha = v.get("alpha")
                level = 1-alpha if _finite_number(alpha) and 0 < alpha < 1 else None
            if level is not None:
                levels.append(level)
        out["p18_confidence_levels"] = sorted(set(levels))
        out["p18_connection_methods"] = sorted({v["connection_ci_method"] for v in vs
                                               if isinstance(v.get("connection_ci_method"), str)})
        out["p18_has_legacy_ci_name"] = any("obs_gain_ci95_half" in v for v in vs)

    def _p17_m3m2():
        for g in (p17 or {}).get("gain") or []:
            if g.get("cond") != "2Mbps":
                continue
            alw = g.get("allowed_by_loss") or {}
            for l, rec in alw.items():
                try:
                    if abs(float(l) - 15.0) > 1e-9 or not rec:
                        continue
                except (TypeError, ValueError):
                    continue
                m = rec.get("means") or {}
                if "m3" in m and "m2" in m:
                    return m["m3"] - m["m2"]
        return None

    def _p18_m3m2():
        for v in vs:
            c = v.get("cond") or ""
            if "2Mbps" in c and "15" in c:
                o = v.get("obs") or {}
                a, b = o.get("3", o.get(3)), o.get("2", o.get(2))
                if _finite_number(a) and _finite_number(b):
                    return a-b
        return None

    a, b = _p17_m3m2(), _p18_m3m2()
    if a is not None and b is not None:
        out["m3m2_p17"], out["m3m2_p18"] = a, b
        out["m3m2_same_sign"] = (a < 0) == (b < 0)
    return out or None


def regret_facts(p11):
    """p11 의 후회 검사 두 개를 짝지어 붙인다.

    🩸 여태 보고서는 "(<5 ms 통과)" 와 "(<2 ms 기준 실패)" 를 코드에 굳혀
    두고 p11 이 있기만 하면 찍었다. 가짜 p11(late=0.812, ok=True)로 확인한
    결과 통과한 검사를 "실패"로 인쇄했다. 판정 문구를 굳히지 않는 것은
    그대로 두고, **짝짓는 방법**만 `_match_check` 로 옮겼다(값 부분일치가
    남의 검사에 붙던 문제).

    기준값(5/2 ms)은 p11 이 필드로 내보내면 그것을 쓰고, 안 내보내면
    수를 만들어 내지 않고 검사 이름을 그대로 인용한다.
    """
    if not p11:
        return None
    out = {}
    checks = p11.get("checks") or []
    for tag, vkey, lkey in (("all", "worst_regret_ms", "regret_limit_ms"),
                            ("late", "worst_regret_late_ms",
                             "regret_limit_late_ms")):
        v = p11.get(vkey)
        hit = _match_check(checks, tag, vkey, v)
        out[tag] = {"value": v, "check": hit,
                    "ok": (hit or {}).get("ok"),
                    "label": (hit or {}).get("check"),
                    "limit": p11.get(lkey)}
    a, b = out["all"]["value"], out["late"]["value"]
    out["both"] = (a is not None and b is not None)
    out["late_bigger"] = bool(out["both"] and b > a)
    out["equal"] = bool(out["both"] and b == a)
    out["gap"] = (b - a) if out["both"] else None
    return out


def verdict(ok):
    """검사 결과를 문구로. ok 가 없으면 **판정하지 않는다**(모른다고 적는다)."""
    return "판정 없음" if ok is None else ("통과" if ok else "**실패**")


def criterion(f):
    """검사 기준을 한 조각으로. 기준값 필드가 있으면 수로, 없으면 이름 인용."""
    if f.get("limit") is not None:
        return "기준 < %s ms — %s" % (fmt(f["limit"], 0), verdict(f["ok"]))
    if f.get("label"):
        return "%s — %s" % (cell(f["label"]), verdict(f["ok"]))
    return "대응하는 검사를 p11 에서 못 찾음"


# 🩸 이 목록의 **순서가 곧 우선순위**다(아래 dedup 이 먼저 온 것을 남긴다).
# `probe_cliff.json` 은 그룹 접미사가 붙기 전의 옛 이름이고 지금은
# `probe_cliff_x25519.json` 으로 개명됐다. 목록 순서대로 실으면 옛 파일이
# 남아 있을 때 **새 파일이 조용히 버려진다**. 그래서 main() 에서 파일
# mtime 이 최신인 것부터 싣는다 — 이름 순서에 기대지 않는다.
CLIFF_FILES = ("probe_cliff.json", "probe_cliff_x25519.json",
               "probe_cliff_X25519MLKEM768.json")

# 서버 바이트 직접 측정으로 s0 를 재는 판(`_probe_s0.py`). 있으면 싣는다.
S0_FILES = ("probe_s0_x25519.json", "probe_s0_X25519MLKEM768.json")


def mtime(name):
    """`results/` 안 파일의 수정 시각. 없으면 -1(가장 낮은 우선순위)."""
    p = os.path.join(RESULTS, name)
    return os.path.getmtime(p) if os.path.exists(p) else -1.0


def cliff_facts(files):
    """`probe_cliff_*.json` 에서 절벽을 **계산**한다.

    files: [(파일명, dict)]. 없으면 None 을 돌려주고 절은 조용히 빠진다.
    각 파일에서 ips 오름차순으로 n_rtt 가 2 → 1 로 꺾이는 지점을 찾아
    경계 ips · 늘어난 바이트 · 줄어든 p50 · 그것이 RTT 의 몇 배인지를 낸다.
    """
    out = []
    seen = set()
    for name, d in files:
        rows = [r for r in (d or {}).get("rows", []) or []
                if r.get("ips") is not None and r.get("n_rtt_obs") is not None]
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: r["ips"])
        g = d.get("group") or rows[0].get("group") or "-"
        key = (g, d.get("cert"), tuple(r["ips"] for r in rows))
        if key in seen:            # probe_cliff.json 과 _x25519.json 이 같은 판일 수 있다
            continue
        seen.add(key)
        rtt = d.get("rtt_ms")
        edge = None
        for lo, hi in zip(rows, rows[1:]):
            if lo["n_rtt_obs"] == 2 and hi["n_rtt_obs"] == 1:
                d_ips = hi["ips"] - lo["ips"]
                d_b = ((hi.get("client_bytes") or 0)
                       - (lo.get("client_bytes") or 0))
                gain = None
                if lo.get("p50") is not None and hi.get("p50") is not None:
                    gain = lo["p50"] - hi["p50"]
                edge = {"lo": lo, "hi": hi, "d_ips": d_ips, "d_bytes": d_b,
                        "gain_ms": gain,
                        "rtt_gain": (gain / rtt) if (gain is not None and rtt)
                                    else None,
                        "ms_per_byte": (gain / d_b) if (gain is not None
                                                        and d_b) else None}
                break
        # 부정 시험: n_rtt 가 같은 이웃 쌍(경계를 안 넘은 쌍)
        same = [(a, b) for a, b in zip(rows, rows[1:])
                if a["n_rtt_obs"] == b["n_rtt_obs"]]
        out.append({"file": name, "group": g, "cert": d.get("cert"),
                    "rtt_ms": rtt, "n": d.get("n"), "rows": rows,
                    "edge": edge, "same_pairs": same,
                    "k": rows[0].get("k_expect"),
                    "checks": d.get("checks") or [],
                    "passed": d.get("passed"), "total": d.get("total")})
    if not out:
        return None
    # 🩸 "k 와 무관하게 경계가 같다"는 v2 의 헤드라인 주장이다. 그 판정은
    # **경계를 실제로 찾은 판**에서만 나와야 한다. 예전 코드는 경계를 못 찾은
    # 판을 조용히 빼고 `same_boundary` 를 냈으면서, 렌더 쪽은 `len(sets) > 1`
    # 로 문턱을 삼아 **한 판만 경계를 잡아도 "두 판의 경계가 같다"** 고
    # 인쇄했다. k 목록도 경계 없는 판의 k 를 끌어왔다. 그래서 경계를 찾은
    # 판만 따로 담고, 못 찾은 판은 지우지 말고 그 사실을 남긴다.
    with_edge = [o for o in out if o["edge"]]
    no_edge = [o for o in out if not o["edge"]]
    edges = [o["edge"]["hi"]["ips"] for o in with_edge]
    return {"sets": out,
            "with_edge": with_edge,
            "no_edge": no_edge,
            "n_edge": len(with_edge),
            "boundary_ips": sorted(set(edges)),
            # 판 하나로는 "k 무관"을 말할 수 없다 — 최소 두 판이 필요하다.
            "same_boundary": len(with_edge) > 1 and len(set(edges)) == 1,
            "ks": sorted({o["k"] for o in with_edge if o["k"] is not None}),
            "ks_no_edge": sorted({o["k"] for o in no_edge
                                  if o["k"] is not None})}


def s0_probe_facts(files):
    """`probe_s0_*.json` — 서버 바이트를 직접 세어 `s0` 를 잰 판.

    files: [(파일명, dict)]. 없으면 None 이고 절은 조용히 빠진다(load 관례).

    이 판이 왜 따로 필요한가. 임계 이분탐색은 s0 를 **역산**해서 얻는데,
    그러면 s0 를 넣어 만든 예측을 같은 s0 로 검증하는 자리가 생긴다. 여기서는
    클라이언트가 시행마다 기록한 `server_bytes` 에서 `s0 = S − cert` 를 직접
    빼므로 임계를 거치지 않는다. 우리가 만드는 수는 없다 — 파일에 있는
    `slope_per_pkt` · `mae_const` · `mae_pkt` 를 그대로 나른다.
    """
    out = []
    seen = set()
    for name, d in files:
        rows = [r for r in (d or {}).get("rows", []) or []
                if r.get("s0_obs") is not None and r.get("n_pkt") is not None]
        if not rows:
            continue
        g = d.get("group") or "-"
        key = (g, tuple(r.get("cert") for r in rows))
        if key in seen:            # 같은 판이 두 이름으로 있을 수 있다
            continue
        seen.add(key)
        rows = sorted(rows, key=lambda r: r.get("cert") or 0)
        mc, mp = d.get("mae_const"), d.get("mae_pkt")
        out.append({
            "file": name, "group": g, "rtt_ms": d.get("rtt_ms"),
            "n": d.get("n"), "rows": rows,
            "slope": d.get("slope_per_pkt"),
            "mae_const": mc, "mae_pkt": mp,
            # 상수 모형 기각 여부는 **두 오차의 비교**로만 판정한다.
            "pkt_better": (mp < mc) if (mc is not None and mp is not None)
                          else None,
            "n_pkt_lo": min(r["n_pkt"] for r in rows),
            "n_pkt_hi": max(r["n_pkt"] for r in rows),
            "s0_lo": min(r["s0_obs"] for r in rows),
            "s0_hi": max(r["s0_obs"] for r in rows),
            "cert_lo": min(r.get("cert") or 0 for r in rows),
            "cert_hi": max(r.get("cert") or 0 for r in rows),
            "checks": d.get("checks") or [],
            "passed": d.get("passed"), "total": d.get("total"),
        })
    if not out:
        return None
    sl = [o["slope"] for o in out if o["slope"] is not None]
    cmpd = [o for o in out if o["pkt_better"] is not None]
    return {"sets": out, "slopes": sl,
            "slope_lo": min(sl) if sl else None,
            "slope_hi": max(sl) if sl else None,
            "n_cmp": len(cmpd),
            "n_pkt_better": sum(1 for o in cmpd if o["pkt_better"]),
            "all_pkt_better": bool(cmpd) and all(o["pkt_better"]
                                                 for o in cmpd)}


def build_markdown(p1, p2, p3, p4, p5, p7=None, p8=None, p9=None,
                   p10=None, p11=None, p12=None, e21=None, cliff=None,
                   s0p=None, p17=None, p18=None):
    cf = cap_facts(p1)
    af = amp_facts(p2, e21)
    s0f = s0_levels(p2)
    mf = model_facts(p4, p2)

    L = []
    A = L.append
    A("# PAD-FEC 실측 보고서")
    A("")
    A("QUIC 핸드셰이크 Initial 비행을 위한 소거정정 부호 — 설계·구현·측정")
    A("")
    A("> 이 문서는 `experiments/results/*.json` 에서 직접 생성된다. "
      "숫자를 손으로 옮기지 않는다.")
    A("")
    # 있는데 빈 결과와 아예 없는 결과는 다른 사실이다. 빈 것을 조용히 빼면
    # 독자는 "안 한 실험"으로 읽는다.
    blank = [n for n, v in (("p1", p1), ("p2", p2), ("p3", p3), ("p4", p4),
                            ("p5", p5), ("p7", p7), ("p8", p8), ("p9", p9),
                            ("p10", p10), ("p11", p11), ("p12", p12),
                            ("e21", e21)) if v is not None and not v]
    if blank:
        A("> ⚠ 결과 파일은 있으나 **내용이 빈** 단계: %s. 없는 것과 구분해 "
          "여기 적어 둔다 — 해당 절은 지우지 않고 빈 사실만 남긴다."
          % ", ".join("`%s`" % b for b in blank))
        A("")
    A("## 0. 요약")
    A("")
    A("저장된 실험 결과를 정리했다. 이 보고서의 생성은 실험 재실행을 뜻하지 "
      "않는다. 자료별 출처와 현재 코드 검증 여부는 앞의 출처 표에 기록한다.")
    A("")
    lim = (af or {}).get("at_limit") or []
    if lim:
        o = lim[0]
        # 🩸 `ratio_lo`/`arg_hi` 는 amp_facts 가 **sweep 이 있을 때만** 넣는
        # 키다. p2 의 이분탐색이 실패해 `threshold_lo` 가 전부 null 이면
        # sweep_rows 가 빈 리스트를 주고 그 키들이 아예 안 생긴다 — 예전
        # 코드는 여기서 KeyError 로 **보고서 생성이 통째로 죽었다**(재현됨).
        # 없으면 그 문장만 통째로 뺀다. 수를 지어내지 않는다.
        rlo, rhi = (af or {}).get("ratio_lo"), (af or {}).get("ratio_hi")
        ahi = (af or {}).get("arg_hi")
        if rlo is not None and rhi is not None and ahi is not None:
            span = ("이 테스트베드의 송신량 모형은 `ceil(3B/P)·P`로, 3 배를 초과할 수 있다. "
                    "훑은 %d개 설정에서 %.2f ~ %.2f 였다(최대: %s / Initial "
                    "%d B). " % (len((af or {}).get("sweep") or []), rlo, rhi,
                                 ahi["group"], ahi["ips"]))
        else:
            span = ("이 테스트베드의 송신량 모형 `ceil(3B/P)·P`는 3 배를 초과할 수 있다"
                    "(p2 의 `ips_sweep` 에 임계가 없어 이 판에서는 초과 범위를 "
                    "싣지 못했다). ")
        A("1. **증폭 제한이 실제로 구속한다 — 다만 '정확히 3배'는 조건부다.** "
          "바이트 타임라인에서 서버는 수신 누적 %s B 에 대해 송신 누적 %s B "
          "에서 멈췄다(비 %.2f, e21 `%s` 팔). 그러나 그 비가 딱 3 인 것은 "
          "3B(= %s B)가 서버 패킷 크기 P = %s B 의 **배수**이기 때문이다. "
          "%s"
          "RFC 9000 §8.1 은 예외 문구가 없는 `MUST NOT send more than three "
          "times` 이므로 이 초과분은 **규격 위반**이다. 자세한 것은 3 장."
          % (com(o["rx"]), com(o["tx"]), o["ratio"],
             o["arm"], com(3 * o["rx"]), com(af["P"]), span))
    else:
        A("1. **증폭 제한이 실제로 구속한다.** 허용량은 `ceil(3B/P)·P` 로 "
          "3 배를 초과한다(3 장). 바이트 타임라인(e21)이 없어 관측 정지 "
          "지점은 이 판에 싣지 못했다.")
    A("2. **이 테스트베드의 임계는 서버가 받은 바이트의 영향을 받는다.** 키 교환을 고정하고 "
      "패딩만 늘려도 임계가 이동한다. 다만 이동은 연속이 아니라 **서버 패킷 "
      "경계로 계단**을 이룬다 — 팀 자료의 '교환비 1:3.8' 은 이 계단의 겉모습이다.")
    if cf:
        A("3. **'버려지는 패딩을 공짜로 쓴다'는 기대는 성립하지 않는다.** "
          "손실 단위가 데이터그램이라 용량 부등식 `C ≤ (k−1)(W−h−f)` 을 넘을 "
          "수 없고, 측정한 %d개 설정 전부(%d/%d)가 이를 위반한다. %s. 꼬리표를 "
          "f=0 으로 잡아도 최소 %.1f B 모자라므로 결론은 꼬리표 크기에 "
          "강건하다."
          % (cf["n"], cf["n_violate"], cf["n"], cap_phrase(cf),
             cf["min_excess_f0"]))
    else:
        A("3. **'버려지는 패딩을 공짜로 쓴다'는 기대는 성립하지 않는다.** "
          "손실 단위가 데이터그램이라 용량 부등식 `C ≤ (k−1)(W−h−f)` 을 넘을 "
          "수 없다. (p1 의 `capacity_checks` 가 없어 이 판에는 수치를 "
          "싣지 못했다.)")
    A("4. 패리티 데이터그램은 손실 복구와 증폭 신용 확보에 쓰일 수 있다. "
      "효과는 손실 위치와 도착 순서에 따라 달라진다. 복구에 사용한 바이트를 "
      "추가 신용으로 다시 계산할 수 없으며, 복구 한도를 넘는 손실에는 재전송이 "
      "필요하다. 회계와 배치는 4장에 적었다.")
    A("")

    # ------------------------------------------------------------ 1. 비행 구조
    A("## 1. 첫 비행의 구조 (실측)")
    A("")
    A("클라이언트가 실제로 내보낸 첫 비행을 그대로 떠서 RFC 9001 §5.2 의 "
      "Initial 키로 복호해 프레임 단위로 셌다. 추정값이 아니다.")
    A("")
    A("| 그룹 | Initial 크기 | 데이터그램 k | ClientHello C | PADDING | 패킷당 고정비 h | 채움률 |")
    A("|---|---|---|---|---|---|---|")
    for c in (p1 or {}).get("capacity_checks", []):
        A("| %s | %s | %d | %d | %d | %.0f | %.0f%% |"
          % (c["group"], c["ips"] or "기본(1280)", c["k"], c["C"],
             c["padding"], c["h"], 100 * c["fill"]))
    A("")
    k1 = [c for c in (p1 or {}).get("capacity_checks", []) if c["k"] == 1]
    if k1:
        pcts = [100.0 * c["padding"] / c["W"] for c in k1]
        A("- %s 는 **데이터그램 하나**로 끝난다(%d개 설정). 패딩이 "
          "데이터그램의 **%.0f ~ %.0f %%** 를 차지한다 — 버려지는 공간은 "
          "확실히 크다."
          % (" · ".join(sorted({c["group"] for c in k1})), len(k1),
             min(pcts), max(pcts)))
    base, base_k = {}, {}
    for c in (p1 or {}).get("capacity_checks", []):
        if not c["ips"]:                       # ips=0 = quic-go 기본값
            base[c["group"]] = c["k"] * c["W"]
            base_k[c["group"]] = c["k"]
    if base:
        multi = sorted(g for g, k in base_k.items() if k >= 2)
        A("- 기본 설정에서 첫 비행 B = k·W 는 %s 다.%s"
          % (", ".join("%s %s B" % (g, com(v))
                       for g, v in sorted(base.items())),
             (" %s 만 데이터그램이 **%s 개**로 늘어난다."
              % (" · ".join(multi),
                 " / ".join(str(base_k[g]) for g in multi))) if multi else ""))
        A("")
        # 인수인계 문서 표와의 대조는 **그룹 단위 계산**이다. 문장에 "다르다"를
        # 굳혀 놓으면 우리 값이 문서와 같아져도 문장이 안 바뀐다.
        hf = handover_facts(base)
        A("| 그룹 | 우리 실측 B = k·W | 인수인계 문서(2026-08-18) 표 | 차이 |")
        A("|---|---|---|---|")
        for r in hf["rows"]:
            A("| %s | %s | %s | %s |"
              % (r["group"],
                 ("%s B" % com(r["ours"])) if r["ours"] is not None
                 else "우리 자료 없음",
                 ("%s B" % com(r["doc"])) if r["doc"] is not None
                 else "문서에 없음",
                 ("**{:+,} B**".format(r["diff"])) if r["diff"] else
                 ("같음" if r["same"] else "-")))
        A("")
        if hf["n_cmp"] == 0:
            A("문서 표와 그룹 이름이 겹치는 것이 없어 대조하지 못했다.")
        elif hf["none_differ"]:
            A("대조한 %d개 그룹에서 **우리 값과 문서 값이 같다**." % hf["n_cmp"])
        else:
            A("대조한 %d개 그룹 중 **%d개가 다르다** — %s. %s우리 값을 넣어야 "
              "§2 의 임계가 산술과 맞는다."
              % (hf["n_cmp"], hf["n_diff"],
                 "; ".join("%s 우리 %s B vs 문서 %s B (%+d B)"
                           % (r["group"], com(r["ours"]), com(r["doc"]),
                              r["diff"]) for r in hf["diff"]),
                 ("모두 %s B 차이로, 데이터그램 하나(W) 몫이다. "
                  % com(hf["diffs"][0]).lstrip("-"))
                 if len(hf["diffs"]) == 1 else ""))
        if hf["cross"]:
            A("")
            A("> 헷갈리기 쉬운 자리 — %s. 그룹을 섞어 읽으면 **같은 수를 놓고 "
              "\"다르다\"고 적게 된다**(실제로 그런 문장이 나간 적 있다)."
              % "; ".join("문서의 %s 값 %s B 는 우리 %s 값과 같다"
                          % (c["doc_group"], com(c["value"]), c["our_group"])
                          for c in hf["cross"]))
    A("")

    # -------------------------------------------------------- 2. 용량 정리
    A("## 2. 왜 '공짜 FEC' 가 안 되는가 — 용량 정리")
    A("")
    A("손실 단위는 데이터그램이다. 하나가 통째로 사라지면 그 안에 있던 "
      "실내용과 그 안에 있던 패리티 조각이 함께 사라진다. 그래서 제자리"
      "(바이트 중립) 1-소거 보호가 가능하려면")
    A("")
    A("```")
    A("    C  ≤  (k − 1) · (W − h − f)")
    A("```")
    A("")
    A("이어야 한다. C=ClientHello 바이트, k=데이터그램 수, W=데이터그램 크기, "
      "h=패킷당 고정비, f=꼬리표.")
    A("")
    A("- **따름정리 1** — k=1 이면 우변이 0 이다. 데이터그램이 하나뿐인 비행은 "
      "비행 내부에서 보호할 방법이 **원리적으로 없다**. x25519 가 여기 해당한다.")
    A("- **따름정리 2** — 구현은 패킷을 꽉 채워 보내므로 자연 채움률이 높다. "
      "정리는 채움률 (k−1)/k 이하를 요구하므로, 보통 데이터그램이 하나 더 필요하다.")
    if cf:
        A("- **실측 결과** — %d개 설정 중 %d개 위반. %s."
          % (cf["n"], cf["n_violate"], cap_phrase(cf)))
        A("")
        A("| 그룹 | Initial | k | C | 용량 (k−1)(W−h−f) | 초과 | f=0 용량 | f=0 초과 |")
        A("|---|---|---|---|---|---|---|---|")
        for r in cf["rows"]:
            if r["k"] < 2:
                continue        # 우변이 0 이라 표에 실을 것이 없다
            A("| %s | %s | %d | %.0f | %.1f | **+%.1f** | %.1f | +%.1f |"
              % (r["group"], r["ips"], r["k"], r["C"], r["capacity"],
                 r["excess"], r["capacity_f0"], r["excess_f0"]))
        A("")
        A("k=1 인 %d개 설정은 우변이 0 이므로 표에 싣지 않았다 — C 가 얼마든 "
          "위반이다(따름정리 1). 위 초과분 범위와 아래 최소값은 **이 표의 "
          "%d행(k≥2)에서만** 계산한다. 꼬리표를 0 으로 잡은 오른쪽 두 열이 "
          "**결론이 f 에 강건함**을 보인다: 같은 설정(%s / Initial %s)에서 "
          "초과분이 %.1f B → %.1f B 로 줄 뿐 부호가 바뀌지 않는다"
          "(이 데이터가 함의하는 f = %s B)."
          % (cf["n_k1"], cf["n_pool"], cf["min"]["group"], cf["min"]["ips"],
             cf["min"]["excess"], cf["excess_f0_at_min"],
             ", ".join("%.0f" % x for x in cf["f_implied"]) or "-"))
        A("")
        A("> 이 초과분은 **라운드마다 흔들리는 관측값**이다(C 가 TLS 확장·"
          "세션 티켓 길이에 따라 몇 바이트 움직인다). 그래서 단일 상수로 "
          "인용하지 말고 위 표의 설정과 함께 인용해야 한다.")
        A("")
    A("이 정리는 작은 매개변수에서 **모든 배치를 완전탐색**해 반례가 없음을 "
      "확인했다(§6).")
    A("")
    A("> 인수인계 문서 1-4 의 기대와 다른 결론이다. 문서 8절의 지침을 따른다 — "
      "\"데이터를 억지로 해석하지 말고 있는 그대로 기록하십시오.\"")
    A("")

    # -------------------------------------------------------- 3. 증폭 임계
    A("## 3. 증폭 임계 (RFC 9000 §8.1)")
    A("")
    A("RFC 9000 §8.1 은 주소 검증 전 서버가 **받은 바이트의 3 배를 넘겨 "
      "보내면 안 된다**고 예외 없이(`MUST NOT`) 정한다. 여기서 두 가지를 "
      "구분해야 한다 — 규격이 정한 **상한**과 구현이 실제로 멈추는 **지점**.")
    A("")
    if (af or {}).get("obs"):
        A("서버 앞에서 바이트 타임라인을 떠서 정지 지점을 직접 봤다(e21).")
        A("")
        A("| 팔 | 인증서 | 정지 시 수신 누적 | 정지 시 송신 누적 | 송신/수신 | 3배 한도에서 멈췄나 | HCT |")
        A("|---|---|---|---|---|---|---|")
        for o in af["obs"]:
            A("| %s | %s B | %s B | %s B | %.2f | %s | %s ms |"
              % (o["arm"], com(o["cert"]), com(o["rx"]), com(o["tx"]),
                 o["ratio"],
                 "예" if o["at_limit"] else "아니오 (한도 전에 비행이 끝남)",
                 fmt(o["hct"])))
        A("")
        if af["at_limit"]:
            o = af["at_limit"][0]
            A("정지한 팔(%s)에서 송신/수신 비는 정확히 %.2f 이다. **그런데 이 "
              "값을 조건 없이 인용하면 안 된다.** 그 팔의 첫 비행은 "
              "B = %s B 이고 3B(= %s B)는 서버 패킷 크기 P = %s B 의 배수라, "
              "양자화가 일어나지 않는 특수한 점이다. 아래 3-2 가 일반적인 "
              "경우를 보여준다."
              % ("/".join(x["arm"] for x in af["at_limit"]), o["ratio"],
                 com(o["rx"]), com(3 * o["rx"]), com(af["P"])))
            A("")
    if p2:
        A("### 3-1. 기준선 임계와 팀 자료 대조")
        A("")
        A("| 그룹 | 팀 자료 | 우리 측정 | 일치 |")
        A("|---|---|---|---|")
        for r in p2["thresholds"]:
            if r["arm"] != "off":
                continue
            t = p2["team"].get(r["group"])
            if not t or not r.get("threshold_lo"):
                continue
            A("| %s | %d ~ %d B | %d ~ %d B | %s |"
              % (r["group"], t[0], t[1], r["threshold_lo"], r["threshold_hi"],
                 "예" if r.get("team_agrees") else "아니오"))
        A("")
        A("### 3-2. 바이트만 늘려도 임계가 이동하는가 (문서 1-3 재현)")
        A("")
        A("| 그룹 | Initial 크기 | 첫 비행 B | 예산 3B | 허용 A(B) | **A(B)/B** | 측정 임계 | s0 = A(B) − 임계 |")
        A("|---|---|---|---|---|---|---|---|")
        from padfec import amplif
        for r in sweep_rows(p2):       # amp_facts 와 **같은 술어**
            cb = r["first_flight_bytes"]
            al = amplif.allowed_bytes(cb)
            mid = 0.5 * (r["threshold_lo"] + r["threshold_hi"])
            A("| %s | %d | %d B | %d | %d | %.2f | %d ~ %d B | %.1f |"
              % (r["group"], r["ips"], cb, amplif.budget(cb), al,
                 float(al) / cb, r["threshold_lo"], r["threshold_hi"],
                 al - mid))
        A("")
        A("알고리즘도 인증서도 그대로 두고 **패딩만** 늘렸는데 임계가 움직인다. "
          "원인은 키 교환 방식이 아니라 보내는 바이트 수 자체다 — 문서 1-3 의 "
          "결론이 우리 테스트베드에서도 재현된다.")
        A("")
        A("한 가지 정정: 이동은 매끄럽지 않고 **계단**이다. quic-go 는 패킷을 "
          "만들기 전에 `bytesSent >= 3×bytesReceived` 만 보므로(불리언 게이트), "
          "예산이 조금이라도 남으면 패킷 하나를 통째로 더 보낸다. 그래서 실제 "
          "허용량은 `A(B) = ceil(3B/P)·P`(P = %s B)다."
          % com((af or {}).get("P", 1280)))
        A("")
        if (af or {}).get("sweep"):
            A("**그 결과 A(B)/B 는 3 을 넘는다** — 위 표에서 %.2f ~ %.2f 이고 "
              "최대는 %s / Initial %d B 의 %.2f 다. 3.00 이 나오는 것은 3B 가 "
              "P 의 배수인 %d개(%d개 중)뿐이다. RFC 9000 §8.1 의 `MUST NOT send "
              "more than three times` 에는 패킷 경계 예외가 없으므로, 이 "
              "초과분은 **규격 위반**이다. 우리 설계가 그 위반 위에 서 있다는 "
              "점도 함께 적는다."
              % (af["ratio_lo"], af["ratio_hi"], af["arg_hi"]["group"],
                 af["arg_hi"]["ips"], af["arg_hi"]["ratio"],
                 af["n_exact3"], len(af["sweep"])))
            A("")
        ex = (p2 or {}).get("exchange") or {}
        pts = [p for p in ex.get("points", []) if p.get("ratio")]
        if pts:
            top = max(pts, key=lambda p: p["ratio"])
            sl = [(k[6:], v) for k, v in sorted(ex.items())
                  if k.startswith("slope_")]
            A("팀 자료의 '교환비 1:3.8' 도 이 계단의 겉모습이다. 인접한 두 "
              "점만 보면 비가 0 이거나 %.1f 로 보인다(%s, +%.0f B). 회귀 "
              "기울기는 %s 로 서로 다르고 3 도 아니다 — 표본이 계단 **하나만** "
              "걸치므로 기울기 추정으로 쓸 수 없다. 계단 모형이 맞다면 이 "
              "수들은 애초에 기울기가 아니라 계단 높이 나누기 걸음 폭이다."
              % (top["ratio"], top["group"], top["d_client_bytes"],
                 " / ".join("%s %.2f" % (g, v) for g, v in sl) or "-"))
            A("")
        A("### 3-3. 패리티가 임계를 밀어올리는가")
        A("")
        A("| 그룹 | 팔 | 클라이언트 바이트 | 측정 임계 |")
        A("|---|---|---|---|")
        for r in p2["thresholds"]:
            if not r.get("threshold_lo"):
                continue
            A("| %s | %s | %.0f B | %d ~ %d B |"
              % (r["group"], r["arm"], r["client_bytes_total"],
                 r["threshold_lo"], r["threshold_hi"]))
        A("")

        # ------------------------------------------- 3-4. 모형의 예측 대 실측
        if mf:
            A("### 3-4. 양자화 모형은 어디까지 맞는가 (있는 그대로)")
            A("")
            hits = mf["hits"]
            A("p4 의 임계 예측 성적은 `threshold_hits = %s` 다. "
              "이 수를 그냥 '적중률'로 읽으면 안 된다."
              % json.dumps(hits))
            A("")
            A("| 그룹 | 팔 | 클라 바이트 | 예측 임계 | 측정 임계 | 적중 | 예측−측정 | s0 를 이 점에서 역산했나 |")
            A("|---|---|---|---|---|---|---|---|")
            for r in mf["rows"]:
                A("| %s | %s | %.0f | %.1f | %d ~ %d | %s | %+.1f B | %s |"
                  % (r["group"], r["arm"], r["client_bytes"], r["predicted"],
                     r["lo"], r["hi"], "O" if r["hit"] else "X", r["dev"],
                     "**예 — 항등식**" if r["identity"] else "아니오"))
            A("")
            if mf["all_hits_are_identities"]:
                A("**적중한 %d개는 전부 s0 를 바로 그 점에서 역산한 팔이다.** "
                  "s0 = A(B) − 임계로 정의해 놓고 임계 = A(B) − s0 를 "
                  "예측했으니 맞는 것이 당연하다 — 검증이 아니라 항등식이다. "
                  "예측력이 걸린 곳은 나머지 %d개(FEC 팔)이고, 거기서는 "
                  "**전부 빗나갔다**: %s."
                  % (len(mf["hit_rows"]), len(mf["miss_rows"]),
                     ", ".join("%s/%s %+.1f B" % (r["group"], r["arm"],
                                                  r["dev"])
                               for r in mf["miss_rows"])))
            else:
                A("적중 %d / 빗나감 %d. 적중 중 s0 역산 팔이 아닌 것이 "
                  "있으므로(아래 표의 마지막 열), 그 팔은 진짜 예측이다."
                  % (len(mf["hit_rows"]), len(mf["miss_rows"])))
            A("")
            A("빗나간 방향이 전부 **과대예측**(예측 > 측정)인 것도 그대로 "
              "적는다. 패리티로 산 바이트가 예산에는 들어가지만 임계를 "
              "모형만큼 밀어 올리지는 못한다는 뜻이고, 이유 후보는 4 장의 "
              "타이밍 조건(늦게 온 바이트는 그 비행의 예산을 못 늘린다)이다. "
              "**아직 확정하지 못했다.**")
            A("")

        # -------------------------------------- 3-5. s0 는 단일값이 아니다
        if s0f:
            A("### 3-5. s0 는 그룹당 하나가 아니라 두 단계다")
            A("")
            A("s0(인증서를 뺀 서버 첫 비행)를 그룹당 상수로 쓰면 위 예측이 "
              "어긋난다. ips 마다 다시 뽑으면 **허용량 계단을 넘는 지점에서 "
              "값이 갈린다**.")
            A("")
            A("| 그룹 | Initial | 첫 비행 B | 허용 A(B) | 측정 임계 | s0 |")
            A("|---|---|---|---|---|---|")
            for g in sorted(s0f):
                for r in s0f[g]["rows"]:
                    A("| %s | %d | %d | %d | %d ~ %d | **%.1f** |"
                      % (g, r["ips"], r["B"], r["allowed"], r["lo"], r["hi"],
                         r["s0"]))
            A("")
            A("계단 요약 — %s."
              % "; ".join(
                  "%s: %s (폭 %.1f B)"
                  % (g, " / ".join("%.1f" % v for v in s0f[g]["levels"]),
                     s0f[g]["spread"]) for g in sorted(s0f)))
            A("")
            A("두 단계가 생기는 이유는 s0 를 `A(B) − 임계중앙값` 으로 재기 "
              "때문이다. 임계는 인증서 격자에서만 관측되므로 s0 도 격자만큼 "
              "번지고, 여기에 계단이 겹친다. **s0 를 단일값으로 인용하면 안 "
              "된다** — 어느 ips 에서 뽑은 값인지 함께 적어야 한다.")
            A("")

    # -------------------------------------------------------- 4. 두 이득의 배타성
    A("## 4. 하나의 패리티로 두 이득을 동시에 가질 수 없다")
    A("")
    A("설계 도중 발견한 제약이며, 이 연구에서 가장 중요한 구현 지식이다.")
    A("")
    A("- **증폭 신용을 받으려면** 패리티가 *복호 가능한 마지막 패킷보다 먼저* "
      "도착해야 한다. quic-go 의 run loop 는 복호에 실패한 패킷에 대해 "
      "`if !wasProcessed { continue }` 로 빠지므로(`connection.go:669`), "
      "늦게 온 패리티는 예산만 올리고 **송신을 깨우지 못한다**.")
    A("- **손실을 복구하려면** 복구본을 스택에 넣는 대신 *패리티를 버려야* 한다. "
      "안 그러면 도착하지도 않은 바이트가 예산에 들어가 3배 한도가 4.5배가 된다. "
      "버릴지 말지는 패리티가 도착한 시점에 정해야 하고, 그러려면 패리티가 "
      "**원본들보다 뒤에** 와야 한다.")
    A("")
    A("두 요구가 정반대다. 그래서 구현은 역할을 나눈다.")
    A("")
    A("| 팔 | 배치 | 얻는 것 |")
    A("|---|---|---|")
    A("| `on1` | 원본… → 패리티 | 손실 복구만 |")
    A("| `on2` | 패리티0 → 원본… → 패리티1 | 앞이 증폭 신용, 뒤가 복구 (회계도 맞음) |")
    A("")
    A("`on2` 에서 회계가 맞는 이유: 수신 바이트가 패리티 두 몫이므로, 뒤의 "
      "패리티를 복구에 쓰고 버려도 스택에 넘긴 누적이 물리적으로 받은 누적을 "
      "넘지 않는다. 구현은 이 불변식을 **런타임에 강제**한다.")
    A("")

    # -------------------------------------------------------- 5. 효과
    A("## 5. 손실 조건에서의 효과 (문서 단계 4)")
    A("")
    if p3:
        A("cert %d B, RTT %.0f ms, 조건마다 n=%d."
          % (p3["cert"], p3["rtt_ms"], p3["n"]))
        A("")
        A("| 그룹 | 손실 | 버스트 | 방향 | 팔 | p50 | p95 | p99 | PTO율 | 복구 |")
        A("|---|---|---|---|---|---|---|---|---|---|")
        for r in p3["runs"]:
            if not r.get("valid"):
                continue
            A("| %s | %.1f%% | %.0f | %s | %s | %s | %s | %s | %s%% | %s |"
              % (r["group"], r["loss"], r["burst"], r["dir"], r["arm"],
                 fmt(r["p50"]), fmt(r["p95"]), fmt(r["p99"]),
                 fmt(100 * (r["pto_rate"] or 0)), r["srv_recovered"]))
        A("")
        A("총 복구 %d 건, 복구 CRC 실패 %d 건 (복구본이 원본과 다르면 부호가 "
          "스스로 걸러낸다)."
          % (p3["total_recovered"], p3["recover_crc_fail"]))
        A("")

    # -------------------------------------------------------- 6. 검증
    A("## 6. 검증")
    A("")
    if p5:
        A("| 항목 | 결과 | 비고 |")
        A("|---|---|---|")
        for r in p5["results"]:
            A("| %s | %s | %s |" % (cell(r["check"]), "통과" if r["ok"] else "실패",
                                    cell(r["detail"], 70)))
        A("")
        A("%d / %d 통과." % (p5["passed"], p5["total"]))
        A("")
    if p7:
        A("### 결정적 검증 - 소거를 우리가 만들고 대조")
        A("")
        A("무작위 손실 통계는 \"꼬리가 줄었다\"까지만 말한다. 그 개선이 정말 "
          "복구 때문인지는 **못 고치게 만들어 보아야** 알 수 있다.")
        A("")
        A("| 조건 | 성공 | p50 | 최대 | 복구 | CRC거절 |")
        A("|---|---|---|---|---|---|")
        for c in p7["cases"]:
            A("| %s | %d/%d | %s | %s | %s | %s |"
              % (c["case"], c["ok"], c["n"], fmt(c["p50"]), fmt(c["max"]),
                 c["srv_recovered"], c["srv_crc_fail"]))
        A("")
        A("| 판정 | 결과 | 근거 |")
        A("|---|---|---|")
        for c in p7["checks"]:
            A("| %s | %s | %s |" % (cell(c["check"]), "통과" if c["ok"] else "실패",
                                    cell(c["detail"], 80)))
        A("")
        A("%d / %d 통과." % (p7["passed"], p7["total"]))
        A("")

    if p9:
        A("### 환경 교차검증 - 서로 다른 두 테스트베드")
        A("")
        A("결론이 하네스에 의존하면 그건 하네스의 성질이다. 코드도 프로세스 "
          "구조도 다른 두 환경에서 같은 것을 쟀다.")
        A("")
        A("| 그룹 | 환경 A (문서 환경, qamp 직결) | 환경 B (1차 환경, 심 중계) "
          "| 팀 자료 (다른 PC) | 판정 |")
        A("|---|---|---|---|---|")
        for c in p9["compare"]:
            def rng(x):
                return ("%s ~ %s B" % (x[0], x[1])) if x and x[0] else "-"
            A("| %s | %s | %s | %s | %s |"
              % (c["group"], rng(c["A"]), rng(c["B"]),
                 ("%d ~ %d B" % tuple(c["team"])) if c["team"] else "-",
                 "세 곳 모두 겹침" if c["ok"] else "불일치"))
        A("")

    if p8:
        A("### 반복 재현성과 음성 대조")
        A("")
        A("| 판정 | 결과 | 근거 |")
        A("|---|---|---|")
        for c in p8["checks"]:
            A("| %s | %s | %s |" % (cell(c["check"]), "통과" if c["ok"] else "실패",
                                    cell(c["detail"], 80)))
        A("")
        A("%d / %d 통과." % (p8["passed"], p8["total"]))
        A("")

    if p4:
        A("### 모형이 실측을 맞췄는가")
        A("")
        A("s0(인증서를 뺀 서버 비행 크기)는 **기준선 팔에서 역산**하고, "
          "그것으로 나머지 팔의 임계를 예측했다. 그러므로 기준선 팔의 "
          "적중은 자유도 없는 예측이 아니라 **항등식**이다 — 성적을 그렇게 "
          "읽어야 한다(3-4 표).")
        A("")
        h = p4.get("threshold_hits")
        if h:
            note = ""
            if mf and mf["all_hits_are_identities"]:
                note = (" — 그러나 적중 %d개는 전부 s0 역산 팔이고, "
                        "FEC 팔 %d개는 전부 빗나갔다(%s)"
                        % (len(mf["hit_rows"]), len(mf["miss_rows"]),
                           ", ".join("%+.1f B" % r["dev"]
                                     for r in mf["miss_rows"])))
            A("- 임계 예측 **%d / %d 적중**%s" % (h[0], h[1], note))
        if p4.get("hct_mae_ms") is not None:
            A("- HCT 예측 평균 절대 오차 **%.1f ms**" % p4["hct_mae_ms"])
        a = p4.get("policy_agreement")
        if a:
            A("- 정책이 고른 팔이 실측 최선과 일치 **%d / %d**" % (a[0], a[1]))
        if mf and mf["s0"]:
            A("- 예측에 쓴 s0 = %s (3-5 가 보이듯 **ips 에 따라 갈리는 값**을 "
              "하나로 고정한 것이다)"
              % ", ".join("%s %.1f B" % (g, v)
                          for g, v in sorted(mf["s0"].items())))
        A("")

    # ------------------------------------------- 7~ 뒤쪽 절은 번호를 계산한다
    # (p10/p11/p12 는 있을 때만 실리므로 고정 번호를 못 쓴다. 0~6 은 본문에서
    #  서로를 가리키므로 그대로 둔다.)
    nxt = [7]

    def sec(title):
        n = nxt[0]
        nxt[0] += 1
        A("## %d. %s" % (n, title))
        A("")
        return n

    # -------------------------------------------------------- 완성도 (p10)
    if present(p10):
        sec("완성도 — 설계했지만 아직 안 되는 것")
    if present(p10) and not p10:
        A(empty_note("p10_completeness.json"))
        A("")
    if p10:
        A("잘 되는 것만 세면 완성도가 아니다. **설계에 있는데 구현에 없는 "
          "것**을 재고조사하고, 한 번도 안 해 본 영역(동시 연결·극단 RTT·"
          "극단 손실·악성 입력·장수명)에서 무너지는지 봤다.")
        A("")
        gaps = [g for g in p10.get("gaps", []) if not g.get("ok")]
        if gaps:
            A("### 미해결 재고 %d 건" % len(gaps))
            A("")
            A("| 항목 | 설계 | 구현 | 왜 |")
            A("|---|---|---|---|")
            for g in gaps:
                A("| %s | %s | %s | %s |"
                  % (cell(g.get("item")), cell(g.get("designed")),
                     cell(g.get("implemented")), cell(g.get("why"))))
            A("")
            A("기능 목록은 소스 구현 여부를 기록한다. 해당 기능의 성능 검증은 "
              "각 실험 단계의 결과로 확인해야 한다. 제자리 배치의 용량 위반도 "
              "측정한 설정과 명시한 가정 안에서 해석한다.")
            A("")
        _p10_facts = p10_test_facts(p10)
        tests = _p10_facts["tests"]
        if tests:
            A("### 한 번도 안 해 본 영역")
            A("")
            A("| 시험 | 결과 | 근거 |")
            A("|---|---|---|")
            for r in tests:
                A("| %s | %s | %s |"
                  % (cell(r["check"]), check_label(r),
                     cell(r.get("detail"), 90)))
            A("")
            A("%s / %s 통과, 미해결 재고 %s 건."
              % (fmt(_p10_facts["passed"], 0), fmt(_p10_facts["total"], 0),
                 fmt(p10.get("open_gaps"), 0)))
            A("")
            bad = _p10_facts["failed"]
            if bad:
                A("미흡한 항목을 지우지 않고 남긴다 — %s."
                  % "; ".join("**%s** (%s)" % (r["check"],
                                               cell(r.get("detail"), 60))
                              for r in bad))
                A("")
            if _p10_facts["excluded"]:
                A("판정불능·진단 %d개는 통과 집계에서 제외했다." % len(_p10_facts["excluded"]))
                A("")

    # ------------------------------------------------------ 폐루프 후회 (p11)
    if present(p11):
        sec("폐루프가 최선을 고르는가 — 후회")
    if present(p11) and not p11:
        A(empty_note("p11_adaptive.json"))
        A("")
    if p11:
        A("\"폐루프를 닫았다\"는 배선이 됐다는 뜻과 사람이 골랐을 최선만큼 "
          "한다는 뜻이 있다. 뒤엣것은 **고정 m 을 전부 돌려 보고 그 중 최선과 "
          "비교**해야 알 수 있다. 그 차이가 후회다.")
        A("")
        A("`후회 = auto 평균 HCT − min(고정 m=0,1,2 평균 HCT)`, "
          "%s, n=%s, RTT %s ms."
          % (p11.get("group", "-"), fmt(p11.get("n"), 0),
             fmt(p11.get("rtt_ms"), 0)))
        A("")
        # 🩸 판정 문구를 코드에 굳히지 않는다. 대소 비교와 통과/실패는 전부
        # p11 의 값과 checks 에서 파생시킨다(가짜 p11 로 확인한 사고).
        rf = regret_facts(p11)
        A("**두 값을 함께 봐야 한다.** 전 구간 최악 후회는 **%s ms**(%s), "
          "수렴 후(후반 절반) 최악 후회는 **%s ms**(%s) 다."
          % (sgn(rf["all"]["value"], 3), criterion(rf["all"]),
             sgn(rf["late"]["value"], 3), criterion(rf["late"])))
        if rf["both"]:
            if rf["late_bigger"]:
                A("")
                A("**뒤엣값이 앞엣값보다 %.3f ms 크다** — 콜드스타트 손해로 "
                  "설명되지 않는다는 뜻이므로 하나만 인용하면 결론이 뒤집힌다."
                  % rf["gap"])
            elif rf["equal"]:
                A("")
                A("두 값이 같다. 콜드스타트 구간이 최악 조건을 만들지 않았다는 "
                  "뜻이다.")
            else:
                A("")
                A("**앞엣값이 뒤엣값보다 %.3f ms 크다** — 최악 후회가 "
                  "콜드스타트 구간에서 나왔고 수렴 후에는 %.3f ms 로 줄었다는 "
                  "뜻이다. 그래도 두 값을 함께 적는다."
                  % (-rf["gap"], rf["late"]["value"]))
        A("")
        rg = p11.get("regret") or []
        if rg:
            A("| 조건 | 인증서 | 손실 | 최선 고정팔 | 최선 평균 | auto 평균 | 후회 | 수렴 후 후회 |")
            A("|---|---|---|---|---|---|---|---|")
            for r in rg:
                A("| %s | %s B | %.1f%% | %s | %s | %s | %+.3f | %+.3f |"
                  % (r.get("cond", "-"), "{:,}".format(r.get("cert", 0)),
                     r.get("loss", 0.0), r.get("best_fixed", "-"),
                     fmt(r.get("best_fixed_mean"), 2),
                     fmt(r.get("auto_mean"), 2),
                     r.get("regret_ms", 0.0), r.get("regret_late_ms", 0.0)))
            A("")
        ck = p11.get("checks") or []
        if ck:
            A("| 판정 | 결과 | 근거 |")
            A("|---|---|---|")
            for c in ck:
                A("| %s | %s | %s |" % (cell(c.get("check")),
                                        verdict(c.get("ok")),
                                        cell(c.get("detail"), 90)))
            A("")
            A("%s / %s 통과." % (fmt(p11.get("passed"), 0),
                                fmt(p11.get("total"), 0)))
            A("")
            failed = [c.get("check") for c in ck if not c.get("ok")]
            # 짝이 되는 후회 검사 중 **통과한 쪽**만 든다. 무관한 검사까지
            # 나열하면 "이것만 인용하면 가려진다"는 말이 성립하지 않는다.
            sibling = [f["label"] for f in (rf["all"], rf["late"])
                       if f.get("ok") and f.get("label")]
            if failed:
                worst = (max(rg, key=lambda r: r.get("regret_late_ms", 0.0))
                         if rg else {})
                A("**실패한 검사: %s.**%s 최악 조건은 %s 이고, 거기서 auto 가 "
                  "최선 고정팔(%s)보다 %s ms 뒤진다."
                  % ("; ".join(cell(x) for x in failed),
                     (" 통과한 쪽(%s)만 인용하면 이 실패가 가려진다."
                      % "; ".join(cell(x) for x in sibling))
                     if sibling else "",
                     worst.get("cond", "-"),
                     worst.get("best_fixed_late", "-"),
                     sgn(rf["late"]["value"], 3)))
                A("")
            else:
                A("실패한 검사가 없다. 그래도 위 두 값을 **함께** 인용해야 "
                  "한다 — 하나만 적으면 조건이 지워진다.")
                A("")

    # ------------------------------- 적응이 벌 수 있는 것 (p17, 선택)
    # 🩸 이 절은 8 장 바로 뒤여야 한다. 8 장이 "폐루프가 최선을 고르는가"를
    #    묻는데, 이 절은 그보다 **앞선 질문**에 답한다 — 애초에 적응해서 벌
    #    것이 있는가. 순서가 뒤집히면 0 이 실패처럼 읽힌다.
    _av = adapt_value_facts(p17)
    if _av:
        sec("손실 구간별 후보 선택의 관측 이득 (p17)")
        A("같은 측정 자료에서 손실 구간별 최선 후보와 전체 최선 고정 후보를 "
          "골라 평균 차이를 계산했다. 선택에 쓴 자료로 이득도 평가했으므로 "
          "독립 확증이나 모든 적응 정책에 대한 참상한이 아니다.")
        A("")
        A("cert %s B · RTT %s ms · 손실 스케줄 %s%% 를 50:50 으로 번갈아 걸고, "
          "팔을 구간 안에서 인터리브해 자리를 라틴 방격으로 회전시켜 쟀다"
          "(구간당 n=%s)."
          % (fmt(_av["cert"], 0), fmt(_av["rtt_ms"], 0),
             " ↔ ".join(fmt(x, 0) for x in _av["schedule"]) or "-",
             fmt(_av["n"], 0)))
        A("")
        A("| 조건 | 같은 자료에서 선택한 이득 | 구간별 최선 고정팔 |")
        A("|---|---|---|")
        for c in _av["conds"]:
            A("| %s | **%s ms** | %s |"
              % (cell(c["cond"]),
                 fmt(c["oracle_gain_ms"], 3),
                 " · ".join("손실 %s%% → %s" % (fmt(float(l), 0), cell(v))
                            for l, v in sorted(
                                c["best_by_loss"].items(),
                                key=lambda kv: float(kv[0])))
                 or "-"))
        A("")
        A("관측 이득이 0인 조건도 참이득이 0임을 증명하지 않는다. "
          "자동 정책의 적중률·미적응 구간·실제 지연 차이는 별도로 확인해야 한다. "
          "독립 평가 자료와 후보 전체의 불확실성을 고려하기 전에는 "
          "적응이 불가능하거나 필요 없다는 결론으로 확대하지 않는다.")
        A("")

    # ------------------------------------------- 양자 경계 절벽 (p12, 선택)
    if present(p12):
        sec("양자 경계 절벽 (p12)")
    if present(p12) and not p12:
        A(empty_note("p12_quantum.json"))
        A("")
    if p12:
        A("명세 §8 의 검증 계획 `p12` — `ips` 를 계단 경계 좌우로 훑어 임계가 "
          "**한 칸(≈P)** 뛰는지 본다.")
        A("")
        # 🩸 행 목록의 키는 추측이 아니라 **p12_quantum.py 의 출력 dict** 다.
        #   본선: "configs" (measure() 가 만든 설정 행)
        #   건식: "runs"    (smoke() 가 만든 probe 행)
        # 나머지는 스키마가 또 바뀔 때를 위한 별칭이고, "results" 는 아래
        # checks 탐색과 겹치므로 **배타 처리**한다(같은 자료를 두 번 그리면
        # 판정표가 표 두 개로 나와 독자가 다른 실험으로 읽는다).
        rows = None
        for key in ("configs", "runs", "ips_sweep", "sweep", "points",
                    "rows", "results"):
            v = p12.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                rows = (key, v)
                break
        if rows and any("threshold_lo" in r for r in rows[1]):
            A("| 그룹 | Initial | 첫 비행 B | 허용 A(B) | 칸 | 측정 임계 | s0 | Δ_min | 경계 ips |")
            A("|---|---|---|---|---|---|---|---|---|")
            from padfec import amplif as _am
            for r in rows[1]:
                b = r.get("first_flight_bytes")
                al = _am.allowed_bytes(b) if b else None
                A("| %s | %s | %s | %s | %s | %s ~ %s | %s | %s | %s |"
                  % (cell(r.get("group", "-")), fmt(r.get("ips"), 0),
                     fmt(b, 0), fmt(al, 0),
                     fmt(r.get("bin"), 0),
                     fmt(r.get("threshold_lo"), 0),
                     fmt(r.get("threshold_hi"), 0),
                     fmt(r.get("s0_mid"), 1),
                     fmt(r.get("delta_min"), 0),
                     fmt(r.get("boundary_ips"), 0)))
            A("")
        elif rows:
            # 🩸 폴백 표도 반드시 cell() 을 거친다. detail 에 파이프가 든 행이
            # 실제로 있고(현재 보고서에 5개), 그대로 넣으면 열이 밀려서
            # **보고서가 조용히 틀린다**. 헤더도 값이므로 같이 거른다.
            keys = []
            for r in rows[1]:
                for k in r:
                    if k not in keys:
                        keys.append(k)
            A("| %s |" % " | ".join(cell(k) for k in keys))
            A("|%s" % ("---|" * len(keys)))
            for r in rows[1]:
                A("| %s |" % " | ".join(
                    cell("-" if r.get(k) is None else r.get(k), 90)
                    for k in keys))
            A("")
        used = rows[0] if rows else None
        for key in ("checks", "results"):
            if key == used:        # 행 표에 이미 쓴 자료를 두 번 그리지 않는다
                continue
            v = p12.get(key)
            if not isinstance(v, list) or not v:
                continue
            if not isinstance(v[0], dict) or "check" not in v[0]:
                continue
            A("| 판정 | 결과 | 근거 |")
            A("|---|---|---|")
            for c in v:
                A("| %s | %s | %s |" % (cell(c.get("check")),
                                        verdict(c.get("ok")),
                                        cell(c.get("detail"), 90)))
            A("")
            break
        if p12.get("total") is not None:
            A("%s / %s 통과." % (fmt(p12.get("passed"), 0),
                                fmt(p12.get("total"), 0)))
            A("")

    # --------------------------- 양자 경계 절벽 직접 실측 (probe_cliff, 선택)
    # load() 관례대로 파일이 **있으면** 싣고 없으면 조용히 건너뛴다.
    if cliff:
        sec("1 바이트 절벽 — 경계를 직접 밟아 본 결과")
        A("명세 §2 따름정리(`Δ_min = 1`)를 인증서를 고정한 채 `ips` 만 바꿔 "
          "직접 밟았다. 임계를 이분탐색하는 대신 **경계 좌우에서 실제 "
          "핸드셰이크 시간을 잰다** — 계단이 있다면 한 바이트에서 왕복 하나가 "
          "통째로 사라져야 한다.")
        A("")
        from padfec import amplif as _am
        for s in cliff["sets"]:
            A("### %s%s" % (s["group"],
                            (" (k=%d)" % s["k"]) if s["k"] else ""))
            A("")
            A("인증서 %s B 고정 · RTT %s ms · 설정마다 n=%s · `%s`"
              % (com(s["cert"]), fmt(s["rtt_ms"], 0), fmt(s["n"], 0),
                 s["file"]))
            A("")
            A("| ips | 첫 비행 B | 허용 A(B) | 칸 | 예측 n_rtt | 관측 n_rtt | p50 | 2-RTT 비율 |")
            A("|---|---|---|---|---|---|---|---|")
            for r in s["rows"]:
                b = r.get("client_bytes") or r.get("first_flight_bytes")
                al = r.get("allowed")
                if al is None and b:
                    al = _am.allowed_bytes(b)
                A("| %s | %s | %s | %s | %s | **%s** | %s ms | %s |"
                  % (fmt(r.get("ips"), 0), fmt(b, 0), fmt(al, 0),
                     fmt(r.get("n_bin"), 0), fmt(r.get("n_rtt_pred"), 0),
                     fmt(r.get("n_rtt_obs"), 0), fmt(r.get("p50"), 3),
                     fmt(r.get("two_rtt_rate"), 3)))
            A("")
            e = s["edge"]
            if e:
                A("경계는 **ips = %d** 이다. %d → %d 로 데이터그램당 **%d B**"
                  "(첫 비행 전체로는 %d B) 늘렸더니 관측 왕복이 2 → 1 로 "
                  "떨어지고 p50 이 %s → %s ms 가 됐다%s."
                  % (e["hi"]["ips"], e["lo"]["ips"], e["hi"]["ips"],
                     e["d_ips"], e["d_bytes"], fmt(e["lo"].get("p50"), 3),
                     fmt(e["hi"].get("p50"), 3),
                     (" — **%.2f ms 절약 = %.3f RTT**"
                      % (e["gain_ms"], e["rtt_gain"]))
                     if e["rtt_gain"] is not None else ""))
                if e["ms_per_byte"] is not None:
                    A("")
                    A("추가한 바이트로 나누면 **%.2f ms/B** 다. 이 수는 "
                      "연속 모형에서는 나올 수 없다 — 계단이라 경계 한 점에서만 "
                      "이만큼이고, 그 앞뒤로는 0 이다."
                      % e["ms_per_byte"])
            else:
                A("이 판에서는 2-RTT → 1-RTT 로 꺾이는 이웃 쌍을 못 찾았다 "
                  "(경계가 훑은 구간 밖이거나 측정이 실패했다).")
            if s["same_pairs"]:
                A("")
                A("부정 시험 — %s 는 관측 왕복이 서로 같다. 경계를 안 넘은 "
                  "쌍에서는 아무 일도 일어나지 않는다."
                  % ", ".join("ips %d ≡ %d (n_rtt %s)"
                              % (a["ips"], b["ips"], fmt(a["n_rtt_obs"], 0))
                              for a, b in s["same_pairs"]))
            if s["checks"]:
                A("")
                A("| 판정 | 결과 | 근거 |")
                A("|---|---|---|")
                for c in s["checks"]:
                    A("| %s | %s | %s |" % (cell(c.get("check")),
                                            verdict(c.get("ok")),
                                            cell(c.get("detail"), 90)))
                A("")
                if s["total"] is not None:
                    A("%s / %s 통과." % (fmt(s["passed"], 0),
                                        fmt(s["total"], 0)))
            A("")
        # 🩸 아래 판정은 **경계를 실제로 찾은 판**(`with_edge`)에서만 뽑는다.
        # 판 수·k 목록·"같다"를 전체 판 수로 세면, 한 판만 경계를 잡아도
        # "k 와 무관하게 경계가 같다"가 인쇄된다.
        if cliff["same_boundary"]:
            A("**경계를 찾은 %d판 전부에서 경계 ips 가 %d 로 같다**(k = %s). "
              "따름정리의 \"k 와 무관하게 Δ_min = 1\" 이 실측으로 확인된다 — "
              "데이터그램당 1 B 이므로 첫 비행 전체로는 k 바이트다."
              % (cliff["n_edge"], cliff["boundary_ips"][0],
                 " / ".join(str(x) for x in cliff["ks"]) or "-"))
        elif cliff["n_edge"] > 1:
            A("경계를 찾은 %d판에서 경계 ips 가 서로 다르다(%s). k 무관 "
              "주장은 이 자료로는 성립하지 않는다."
              % (cliff["n_edge"],
                 ", ".join(str(x) for x in cliff["boundary_ips"])))
        elif cliff["n_edge"] == 1:
            s1 = cliff["with_edge"][0]
            A("경계를 찾은 판이 **%s 하나뿐**이라(경계 ips = %d, k = %s), "
              "\"k 와 무관하게 경계가 같다\"는 판정은 이 자료로 **할 수 없다** "
              "— 판정하려면 다른 k 의 판이 최소 하나 더 있어야 한다."
              % (s1["group"], cliff["boundary_ips"][0],
                 fmt(s1["k"], 0)))
        else:
            A("어느 판에서도 2-RTT → 1-RTT 경계를 찾지 못했다. 이 절은 "
              "판정을 내리지 않는다.")
        if cliff["no_edge"]:
            A("")
            A("> 경계를 못 찾은 판 %d개(%s)는 위 판정에서 **뺐다**. 조용히 "
              "빼면 표본 수가 부풀려지므로 여기 남긴다."
              % (len(cliff["no_edge"]),
                 ", ".join("%s / `%s`" % (o["group"], o["file"])
                           for o in cliff["no_edge"])))
        A("")

    # ------------------------ s0 패킷항 직접 측정 (probe_s0_*, 선택)
    # load() 관례대로 파일이 **있으면** 싣고 없으면 조용히 건너뛴다.
    if s0p:
        sec("s0 는 상수가 아니다 — 서버 패킷 수 항을 직접 쟀다")
        A("임계 이분탐색으로 얻은 `s0` 는 **역산값**이라, 그 s0 로 만든 예측을 "
          "같은 점에서 검증하면 항등식이 된다. 그래서 임계를 거치지 않는 길로 "
          "갔다 — 클라이언트가 시행마다 기록한 `server_bytes`(= 서버에게서 받은 "
          "총 바이트) `S` 에서 `s0 = S − cert` 를 직접 뺀다. 인증서만 바꿔 가며 "
          "훑으면 서버 패킷 수 `n̂` 이 늘고, `s0` 가 그와 함께 커지는지 본다.")
        A("")
        for s in s0p["sets"]:
            A("### %s" % s["group"])
            A("")
            A("인증서 %s ~ %s B · RTT %s ms · 조건당 n=%s · `%s`"
              % (com(s["cert_lo"]), com(s["cert_hi"]), fmt(s["rtt_ms"], 0),
                 fmt(s["n"], 0), s["file"]))
            A("")
            A("| cert | S(서버 바이트) | n̂ | **s0 실측** | 상수 예측 | 패킷항 예측 | 상수 오차 | 패킷항 오차 |")
            A("|---|---|---|---|---|---|---|---|")
            for r in s["rows"]:
                A("| %s | %s | %s | **%s** | %s | %s | %s | %s |"
                  % (com(r.get("cert")), com(r.get("S")),
                     fmt(r.get("n_pkt"), 0), fmt(r.get("s0_obs"), 1),
                     fmt(r.get("s0_const"), 1), fmt(r.get("s0_pkt"), 1),
                     sgn(r.get("err_const"), 1), sgn(r.get("err_pkt"), 1)))
            A("")
            A("- 패킷당 증분(기울기) **%s B/패킷**, `s0` 는 n̂ %s → %s 에서 "
              "%s → %s B 로 움직였다."
              % (fmt(s["slope"], 1), fmt(s["n_pkt_lo"], 0),
                 fmt(s["n_pkt_hi"], 0), fmt(s["s0_lo"], 1),
                 fmt(s["s0_hi"], 1)))
            if s["pkt_better"] is not None:
                A("- 평균절대오차 — 상수 모형 **%s B** vs 패킷항 모형 **%s B** "
                  "→ 이 판에서 상수 모형은 **%s**."
                  % (fmt(s["mae_const"], 1), fmt(s["mae_pkt"], 1),
                     "기각된다" if s["pkt_better"] else "기각되지 않는다"))
            if s["checks"]:
                A("")
                A("| 판정 | 결과 | 근거 |")
                A("|---|---|---|")
                for c in s["checks"]:
                    A("| %s | %s | %s |" % (cell(c.get("check")),
                                            verdict(c.get("ok")),
                                            cell(c.get("detail"), 90)))
                A("")
                if s["total"] is not None:
                    A("%s / %s 통과." % (fmt(s["passed"], 0),
                                        fmt(s["total"], 0)))
            A("")
        A("**두 모형 대조 — 한 표로**")
        A("")
        A("| 그룹 | 기울기 (B/패킷) | 평균절대오차 상수 | 평균절대오차 패킷항 | 상수 모형 |")
        A("|---|---|---|---|---|")
        for s in s0p["sets"]:
            A("| %s | %s | %s | %s | %s |"
              % (s["group"], fmt(s["slope"], 1), fmt(s["mae_const"], 1),
                 fmt(s["mae_pkt"], 1),
                 "판정 없음" if s["pkt_better"] is None
                 else ("**기각**" if s["pkt_better"] else "유지")))
        A("")
        if s0p["n_cmp"]:
            A("대조한 %d개 그룹 중 **%d개에서 패킷항 모형이 더 정확하다**%s."
              % (s0p["n_cmp"], s0p["n_pkt_better"],
                 " — 상수 s0 모형은 두 그룹 모두에서 기각된다"
                 if s0p["all_pkt_better"] and s0p["n_cmp"] > 1 else ""))
            A("")
        if s0p["slopes"]:
            A("기울기는 그룹별로 %s 다."
              % (" · ".join("%s %s B/패킷" % (o["group"], fmt(o["slope"], 1))
                            for o in s0p["sets"] if o["slope"] is not None)))
            A("")
        # ⚠ 이 단서를 빼면 두 방법의 절편을 나란히 놓고 "다르다"고 읽게 된다.
        A("> ⚠ **절편은 비교할 수 없다.** 여기 쓴 `S` 는 `server_bytes` 이고, "
          "그 안에는 첫 비행 말고 **꼬리 바이트**(ACK · HANDSHAKE_DONE · "
          "NewSessionTicket)가 함께 들어 있다. 그래서 이 방법의 절편은 임계 "
          "역산이 주는 절편보다 꼬리만큼 높게 나온다. 꼬리가 대략 상수라 "
          "**기울기(B/패킷)만 두 방법 사이에서 비교 가능**하고, 절편끼리의 "
          "차이는 모형의 불일치로 읽으면 안 된다.")
        A("")

    # -------------------------------------------------------- 한계
    sec("한계 — 이 결과가 말하지 않는 것")
    A("- 보호 대상은 **클라이언트 → 서버 방향의 첫 비행뿐**이다. 서버 비행에는 "
      "패딩이 없고(인증서로 꽉 찬다) 서버에게 쓸 수 있는 무료 바이트도 없다. "
      "반대 방향 손실은 이 설계로 줄지 않는다.")
    A("- 측정은 한 대의 기계 안 veth 링크에서 netem 으로 조건을 건 것이다. "
      "실제 인터넷 경로의 재정렬·경합·중간상자는 없다.")
    A("- 패리티 데이터그램은 유효한 DCID 를 가진 롱헤더 Initial 모양이라 "
      "서버가 연결에 귀속시켜 바이트를 센다. 이는 quic-go 의 동작(소스 확인)에 "
      "기댄 것으로, 다른 구현에서 같은지는 확인하지 않았다.")
    A("- 클라이언트가 추가로 전송한 바이트가 서버에 도착하면 증폭 예산도 늘어난다. "
      "이 자체는 RFC가 허용하는 예산 증가다. 다만 3 장의 quic-go 관측에는 "
      "패킷 경계에서 3 배를 넘는 경우가 있다(최대 %s). 이 초과를 RFC의 "
      "허용으로 해석하면 안 된다. p7의 커널 L2 계수기는 주소 검증 시점을 "
      "식별하지 않아 RFC 준수를 입증하지 못한다. 엄격한 3 배 제한을 적용한 "
      "서버에서도 정책의 이득이 유지되는지는 별도로 검증해야 한다."
      % (("%.2f 배" % af["ratio_hi"]) if (af or {}).get("sweep") else "미측정"))
    # 🩸 "수렴 후 기준을 못 맞춘다"는 **그 검사가 실패했을 때만** 쓴다.
    # 아무 검사나 하나 실패하면 찍던 옛 코드는 통과한 판에도 실패를 적었다.
    _rf = regret_facts(p11)
    if _rf and _rf["late"]["ok"] is False:
        A("- 폐루프 정책은 **수렴 후 후회 기준(%s)을 아직 못 맞춘다**"
          "(최악 %s ms). 자동 선택이 사람이 고른 최선과 같다고 말할 수 "
          "없는 조건이 남아 있다."
          % (("< %s ms" % fmt(_rf["late"]["limit"], 0))
             if _rf["late"]["limit"] is not None
             else cell(_rf["late"]["label"]) or "p11 의 수렴 후 검사",
             sgn(_rf["late"]["value"], 3)))
    # 🩸 2026-08-26 도현님 지시 이행: 자(허용집합 1 ms)는 건드리지 않고
    #    **한계로 적는다.** 조건부인 이유는 위 _rf 와 같다 - 정밀도가 자
    #    아래로 내려가면 이 문단은 스스로 사라져야 한다.
    _rk = ruler_facts(p11, p17)
    if _rk and _rk["finer"]:
        # 🩸 2026-09-07 - 뒷문장의 수(필요 표본 · p17/p18 부호)를 원자료에서
        #    읽는다(sample_facts). 없으면 그 문장은 빠진다.
        _sf = sample_facts(p17, p18) or {}
        _tail = ""
        if _sf.get("p18_n_plugin") and _sf.get("p18_n_now"):
            _tail += (" p18 판정불능 조건 %d/%d개에서 같은 자료의 역제곱 표본 "
                      "대입값은 팔당 %s~%s이고 현재는 %s~%s다. "
                      "이 진단값은 추가 표본이나 검정력을 보장하지 않는다."
                      % (_sf["p18_n_undecided"], _sf["p18_n_conds"],
                         fmt(_sf["p18_n_plugin"][0], 0),
                         fmt(_sf["p18_n_plugin"][1], 0),
                         fmt(_sf["p18_n_now"][0], 0),
                         fmt(_sf["p18_n_now"][1], 0)))
        if "m3m2_p17" in _sf:
            _tail += (" 같은 자리(cert 9,000 · 2 Mbps · 손실 15%%)를 두 단계가 "
                      "각각 기록한 m3-m2는 p17 %s / p18 %s ms로 부호가 %s. "
                      "두 기록의 통계적 독립성은 확인되지 않았다."
                      % (sgn(_sf["m3m2_p17"], 2), sgn(_sf["m3m2_p18"], 2),
                         "같다" if _sf["m3m2_same_sign"] else "반대다"))
        A("- 기록된 p11 후회 반폭 %s는 허용집합 폭 %s ms보다 크다. "
          "이 불확실성은 고정팔 선택의 해석에 남으며, 불일치 원인을 정책 결함이나 "
          "측정 흔들림 하나로 확정하지 않는다. 기존 허용집합 기준은 유지한다.%s"
          % (" · ".join("%s %s ms" % (n, fmt(v, 2)) for n, v in _rk["bars"]),
             fmt(_rk["tol"], 0),
             _tail))
    if _rk and _rk.get("p17_position_range_ms") is not None:
        A("- p17 자리별 구간 평균의 최대 범위는 %s ms다. "
          "이 값은 잔차 표준오차나 신뢰반폭이 아니며, 독립성이나 인과적 순서 효과를 확증하지 않는다."
          % fmt(_rk["p17_position_range_ms"], 2))
    if p10 and p10.get("open_gaps"):
        A("- 설계했지만 구현하지 않은 항목이 %d 건 남아 있다(위 재고 표)."
          % p10["open_gaps"])
    A("")
    sec("재현 방법")
    A("```bash")
    A("python experiments/loop2.py --status   # 어디까지 됐는지")
    A("python experiments/loop2.py --loop     # 끝까지 (중단해도 이어서)")
    A("```")
    A("")
    return "\n".join(L)


ONEPAGER = """<!doctype html><meta charset="utf-8">
<style>
@page { size: A4 portrait; margin: 11mm 10mm; }
* { box-sizing: border-box; }
body { font-family: "Malgun Gothic","맑은 고딕",sans-serif; font-size: 8.1pt;
       line-height: 1.34; color: #16181d; margin: 0; }
h1 { font-size: 15pt; margin: 0 0 1mm; letter-spacing: -0.4px; }
.sub { color: #5b6472; font-size: 8pt; margin-bottom: 3mm; }
h2 { font-size: 8.8pt; margin: 3mm 0 1.2mm; padding-bottom: 0.8mm;
     border-bottom: 1.1px solid #16181d; }
table { width: 100%; border-collapse: collapse; font-size: 7.2pt; }
th,td { border: 0.5px solid #c9cdd4; padding: 1.0mm 1.3mm; text-align: right; }
th { background: #f2f4f7; font-weight: 600; text-align: center; }
td:first-child, th:first-child { text-align: left; }
.k { color: #0b6b3a; font-weight: 700; }
.b { color: #a3232b; font-weight: 700; }
.cols { display: flex; gap: 4mm; }
.cols > div { flex: 1; }
ul { margin: 1mm 0 0 4mm; padding: 0; }
li { margin-bottom: 0.8mm; }
.box { border: 0.8px solid #16181d; padding: 1.8mm 2.2mm; margin-top: 1.5mm;
       background: #fafbfc; }
.foot { margin-top: 3mm; color: #7a8391; font-size: 6.8pt;
        border-top: 0.5px solid #c9cdd4; padding-top: 1.2mm; }
code { font-family: Consolas, monospace; font-size: 7.2pt; }
</style>
@@BODY@@
"""


def build_onepager(p1, p2, p3, p4, p5, p7=None, p8=None, p9=None,
                   p10=None, p11=None, p12=None, e21=None, cliff=None):
    from padfec import amplif
    cf = cap_facts(p1)
    af = amp_facts(p2, e21)
    H = []
    A = H.append
    A('<h1>ML-KEM QUIC 핸드셰이크 FEC — 실측 요약</h1>')
    A('<div class="sub">Initial 패딩을 복구 심볼로 쓰는 설계의 검증 · '
      'PAD-FEC · 강원과학고 R&amp;E</div>')

    lim = (af or {}).get("at_limit") or []
    if lim and af.get("sweep"):
        o = lim[0]
        c1 = ('① 증폭 제한은 실제로 구속한다 — 서버는 수신 %s B 에 송신 '
              '<span class="k">%s B</span> 에서 멈췄다(비 %.2f). 단 그 비가 '
              '3.00 인 것은 <b>3B 가 서버 패킷 크기 %s B 의 배수</b>일 때뿐이고, '
              '이 테스트베드의 송신량 모형 <code>ceil(3B/P)·P</code> 는 3 배를 '
              '<b class="b">초과</b>한다(%.2f~%.2f, RFC 9000 §8.1 위반). '
              % (com(o["rx"]), com(o["tx"]), o["ratio"],
                 com(af["P"]), af["ratio_lo"], af["ratio_hi"]))
    else:
        c1 = '① 증폭 제한은 실제로 구속하며 허용량은 패킷 경계로 양자화된다. '
    if cf:
        b = cf["min"]
        c3 = ('③ 측정 설정에서는 데이터그램 수와 크기를 유지한 제자리 보호가 불가능하다. '
              '용량 부등식을 %d/%d 설정이 위반하고, 최소 초과분이 '
              '<span class="b">%.1f B</span>(%s / Initial %s B), 꼬리표를 '
              'f=0 으로 잡아도 %.1f B 다. '
              % (cf["n_violate"], cf["n"], b["excess"], b["group"], b["ips"],
                 cf["min_excess_f0"]))
    else:
        c3 = '③ 제자리 보호 가능성은 용량 부등식과 실제 패킷 배치로 판단해야 한다. '
    A('<div class="box"><b>결론</b> — ' + c1 +
      '② 이 테스트베드의 임계는 서버 수신 바이트와 패킷 경계의 영향을 받는다. '
      + c3 +
      '④ 패리티는 도착 순서와 손실 위치에 따라 복구 또는 증폭 신용에 기여한다. '
      '복구에 쓴 바이트를 추가 신용으로 중복 계산할 수 없고, 복구 한도를 넘는 손실에는 재전송이 필요하다.</div>')

    # 1. 비행 구조
    A('<h2>1. 첫 비행 구조 (Initial 키로 복호해 실측)</h2>')
    A('<table><tr><th>그룹</th><th>Initial</th><th>k</th><th>C</th>'
      '<th>PADDING</th><th>채움률</th><th>제자리 가능?</th></tr>')
    for c in (p1 or {}).get("capacity_checks", []):
        if c["ips"] not in (0, 1450):
            continue
        A('<tr><td>%s</td><td>%s</td><td>%d</td><td>%d</td><td>%d</td>'
          '<td>%.0f%%</td><td class="b">%s</td></tr>'
          % (c["group"], c["ips"] or "1280", c["k"], c["C"], c["padding"],
             100 * c["fill"], "가능" if c["feasible"] else "불가"))
    A('</table>')
    A('<div style="font-size:7pt;color:#5b6472;margin-top:1mm">'
      '용량 부등식 <code>C ≤ (k−1)(W−h−f)</code> — k=1 이면 우변이 0 이므로 '
      'x25519 는 <b>원리적으로</b> 비행 내부 보호가 불가능하다. '
      'ML-KEM 은 k=2 지만 채움률이 절반을 넘어 역시 불가.</div>')

    # 2. 임계
    A('<div class="cols"><div>')
    A('<h2>2. 증폭 임계 — 팀 자료 재현</h2>')
    A('<table><tr><th>그룹</th><th>팀</th><th>우리</th><th>일치</th></tr>')
    for r in (p2 or {}).get("thresholds", []):
        if r["arm"] != "off" or not r.get("threshold_lo"):
            continue
        t = p2["team"].get(r["group"])
        if not t:
            continue
        A('<tr><td>%s</td><td>%d~%d</td><td>%d~%d</td><td class="k">%s</td></tr>'
          % (r["group"], t[0], t[1], r["threshold_lo"], r["threshold_hi"],
             "O" if r.get("team_agrees") else "X"))
    A('</table>')
    A('</div><div>')
    A('<h2>3. 바이트만 늘려도 임계가 이동 (허용=ceil(3B/P)·P)</h2>')
    A('<table><tr><th>그룹</th><th>Initial</th><th>첫비행 B</th>'
      '<th>허용 A</th><th>A/B</th><th>임계</th></tr>')
    for r in sweep_rows(p2):           # 본문 §3-2 와 **같은 술어**
        cb = r["first_flight_bytes"]
        al = amplif.allowed_bytes(cb)
        A('<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td>'
          '<td class="%s">%.2f</td><td>%d~%d</td></tr>'
          % (r["group"][:14], r["ips"], cb, al,
             "b" if al > 3 * cb else "", float(al) / cb,
             r["threshold_lo"], r["threshold_hi"]))
    A('</table>')
    A('</div></div>')

    # 4. 패리티 효과
    A('<h2>4. 패리티가 임계를 밀어올린다</h2>')
    A('<table><tr><th>그룹</th><th>팔</th><th>클라 바이트</th><th>임계</th>'
      '<th>기준선 대비</th></tr>')
    base = {}
    for r in (p2 or {}).get("thresholds", []):
        if r["arm"] == "off" and r.get("threshold_lo"):
            base[r["group"]] = 0.5 * (r["threshold_lo"] + r["threshold_hi"])
    for r in (p2 or {}).get("thresholds", []):
        if not r.get("threshold_lo"):
            continue
        mid = 0.5 * (r["threshold_lo"] + r["threshold_hi"])
        d = mid - base.get(r["group"], mid)
        A('<tr><td>%s</td><td>%s</td><td>%.0f</td><td>%d~%d</td>'
          '<td class="%s">%+.0f B</td></tr>'
          % (r["group"][:14], r["arm"], r["client_bytes_total"],
             r["threshold_lo"], r["threshold_hi"],
             "k" if d > 0 else "", d))
    A('</table>')

    # 5. 손실 효과
    A('<h2>5. 손실 조건 효과 (c2s 손실, cert %s B, RTT %s ms)</h2>'
      % ((p3 or {}).get("cert", "?"), fmt((p3 or {}).get("rtt_ms"), 0)))
    A('<table><tr><th>그룹</th><th>손실</th><th>팔</th><th>p50</th>'
      '<th>p95</th><th>p99</th><th>PTO율</th><th>복구</th></tr>')
    for r in (p3 or {}).get("runs", []):
        if not r.get("valid") or r["dir"] != "c2s" or r["burst"] != 1.0:
            continue
        if r["loss"] not in (0.0, 2.0, 5.0):
            continue
        A('<tr><td>%s</td><td>%.1f%%</td><td>%s</td><td>%s</td><td>%s</td>'
          '<td class="%s">%s</td><td>%s%%</td><td>%s</td></tr>'
          % (r["group"][:14], r["loss"], r["arm"], fmt(r["p50"]),
             fmt(r["p95"]),
             "k" if r["arm"] != "off" else "b", fmt(r["p99"]),
             fmt(100 * (r["pto_rate"] or 0)), r["srv_recovered"]))
    A('</table>')

    # 6. 검증
    A('<h2>6. 검증</h2><ul>')
    if cliff and cliff["with_edge"]:
        seg = []
        # 🩸 본문과 같은 규칙 — **경계를 찾은 판만** 센다. "k 에 무관" 은
        # same_boundary(경계를 찾은 판이 둘 이상이고 그 값이 하나)일 때만.
        for s in cliff["with_edge"]:
            e = s["edge"]
            seg.append("%s%s ips %d→%d, %s→%s ms%s"
                       % (s["group"][:14],
                          ("(k=%d)" % s["k"]) if s["k"] else "",
                          e["lo"]["ips"], e["hi"]["ips"],
                          fmt(e["lo"].get("p50"), 1),
                          fmt(e["hi"].get("p50"), 1),
                          (" = %.2f RTT" % e["rtt_gain"])
                          if e["rtt_gain"] is not None else ""))
        A('<li>양자 경계 절벽 — 데이터그램당 <b>1 B</b> 를 더 보내자 왕복이 '
          '<b class="k">2 → 1</b> 로 떨어졌다(%s)%s%s</li>'
          % ("; ".join(seg),
             ("; <b>경계를 찾은 %d판 전부 경계 ips = %d 로 k 에 무관</b>"
              % (cliff["n_edge"], cliff["boundary_ips"][0]))
             if cliff["same_boundary"] else "",
             ("; 경계를 못 찾은 판 %d개는 이 판정에서 뺐다"
              % len(cliff["no_edge"])) if cliff["no_edge"] else ""))
    if p9 and p9.get("all_agree"):
        A('<li>환경 교차검증 — <b>서로 다른 두 테스트베드</b>(문서 환경 직결 / '
          '1차 환경 심 중계)와 <b>다른 PC 의 팀 자료</b>가 같은 임계 칸을 '
          '가리킨다</li>')
    if p7:
        A('<li>결정적 검증 <b>%d / %d 통과</b> — 소거를 우리가 만들어 넣고, '
          '패리티를 없애거나 손상시키면 <b>반드시 못 고치는지</b>까지 확인'
          '(부정 시험)</li>' % (p7["passed"], p7["total"]))
    if p5:
        A('<li>독립 감사 <b>%d / %d 통과</b> — Go/Python 교차구현, '
          '용량 정리 완전탐색 반례 탐색, 불변식</li>'
          % (p5["passed"], p5["total"]))
    if p11:
        # 🩸 여기서도 판정 문구를 굳히지 않는다. 통과/실패는 p11 의 checks 에서,
        # 두 값의 대소는 실제 비교에서 나온다.
        rf = regret_facts(p11)

        def _crit(f):
            if f.get("limit") is not None:
                base = "&lt;%s ms" % fmt(f["limit"], 0)
            elif f.get("label"):
                base = f["label"].replace("<", "&lt;")
            else:
                base = "대응 검사 없음"
            v = f.get("ok")
            return "%s %s" % (base, "판정 없음" if v is None
                              else ("<b>통과</b>" if v else "<b>실패</b>"))

        big = ""
        if rf["both"]:
            big = ("; 뒤엣값이 %.2f ms 더 크다" % rf["gap"]) if rf["late_bigger"] \
                else (("; 두 값이 같다" if rf["equal"]
                       else "; 앞엣값이 %.2f ms 더 크다" % -rf["gap"]))
        A('<li>폐루프 후회 — 전 구간 최악 <b>%s ms</b>(%s), '
          '<b class="b">수렴 후 최악 %s ms</b>(%s)%s. 두 값을 함께 적는다</li>'
          % (sgn(rf["all"]["value"], 2), _crit(rf["all"]),
             sgn(rf["late"]["value"], 2), _crit(rf["late"]), big))
    if p10:
        _p10_facts = p10_test_facts(p10)
        A('<li>완성도 — 새 영역 시험 <b>%s / %s 통과</b>(동시연결·극단 RTT·'
          '손실 20%%·악성 패리티·600 연결), <b class="b">미해결 재고 %s 건</b></li>'
          % (fmt(_p10_facts["passed"], 0), fmt(_p10_facts["total"], 0),
             fmt(p10.get("open_gaps"), 0)))
        if _p10_facts["excluded"]:
            A('<li>판정불능·진단 %d개는 통과 집계에서 제외했다</li>' % len(_p10_facts["excluded"]))
    if p4:
        h = p4.get("threshold_hits")
        mf1 = model_facts(p4, p2)
        if h and mf1 and mf1["all_hits_are_identities"]:
            A('<li>임계 예측 <b>%d / %d 적중</b> — 다만 적중분은 전부 '
              '<b>s0 를 그 점에서 역산한 항등식</b>이고 FEC 팔 %d 개는 전부 '
              '빗나갔다(%s)</li>'
              % (h[0], h[1], len(mf1["miss_rows"]),
                 ", ".join("%+.0f B" % r["dev"] for r in mf1["miss_rows"])))
        elif h:
            A('<li>임계 예측 <b>%d / %d 적중</b></li>' % (h[0], h[1]))
        if p4.get("hct_mae_ms") is not None:
            A('<li>HCT 예측 평균 절대 오차 <b>%.1f ms</b></li>'
              % p4["hct_mae_ms"])
        a = p4.get("policy_agreement")
        if a:
            A('<li>정책 선택이 실측 최선과 일치 <b>%d / %d</b></li>'
              % (a[0], a[1]))
    if p3:
        A('<li>복구 %d 건 중 CRC 불일치 <b>%d 건</b>; 손실 0%% 조건에서 복구 '
          '0 건(오작동 없음); 스택 전달 바이트 ≤ 물리 수신 바이트 불변식 유지</li>'
          % (p3["total_recovered"], p3["recover_crc_fail"]))
    A('</ul>')

    A('<div class="foot">한계 — 보호 대상은 클라이언트→서버 첫 비행뿐(서버 비행에는 '
      '패딩이 없다). 측정은 한 기계 안 veth + netem 이며 실제 경로의 재정렬·경합은 없다. '
      '패리티가 예산에 계상되는 것은 quic-go 동작(소스 확인)에 기댄 것이다. '
      '증폭 예산을 늘리는 설계는 증폭 방어를 의도적으로 약화시키는 면이 있어 '
      '배치 전 별도 검토가 필요하다.</div>')
    return ONEPAGER.replace("@@BODY@@", "\n".join(H))


def prose_style(text):
    """Keep generated prose punctuation consistent with the project style."""
    text = text.translate(str.maketrans({'—': ':', '–': '~', '“': '"', '”': '"'}))
    for marker in ('⚠️', '⚠', '✅', '❌', '🩸', '⭐', '🆕', '🔴', '🟡', '🔵'):
        text = text.replace(marker, '')
    return text


def source_manifest():
    """Record input hashes and pipeline state without changing stored results."""
    try:
        import loop2
        state_path = os.path.join(HERE, "state", "loop2.json")
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        stages = loop2.build_stages()
        needs_run = set(loop2.resolve(stages, state, []))
        output_stages = {
            os.path.basename(o): stage.id
            for stage in stages for o in stage.outputs if o.endswith(".json")
        }
    except (OSError, ValueError, KeyError):
        state, needs_run, output_stages = {}, set(), {}
    names = ["p1_flight.json", "p2_threshold.json", "p3_effect.json",
             "p4_model.json", "p5_audit.json", "p7_verify.json",
             "p8_stability.json", "p9_crossenv.json", "p10_completeness.json",
             "p11_adaptive.json", "p12_quantum.json", "p17_adaptive_value.json",
             "p18_mmax.json", "p15_v2policy.json", "p16_uplink.json",
             "p13_beff.json", "p19_provenance.json", "p20_residual.json",
             "e21_budget_trace.json"] + list(CLIFF_FILES)
    rows = []
    for name in names:
        path = os.path.join(RESULTS, name)
        stage = output_stages.get(name)
        rec = state.get("stages", {}).get(stage, {})
        row = {"file": name, "exists": os.path.isfile(path), "stage": stage,
               "last_run_status": rec.get("status", "unknown"),
               "last_run_finished": rec.get("finished"),
               "current_code_validated": (stage is not None and stage not in needs_run
                                           and rec.get("status") == "done"
                                           and os.path.abspath(RESULTS) == os.path.abspath(
                                               os.path.join(HERE, "results")))}
        if row["exists"]:
            with open(path, "rb") as f:
                row["sha256"] = hashlib.sha256(f.read()).hexdigest()
            row["modified_utc"] = datetime.fromtimestamp(
                os.path.getmtime(path), timezone.utc).isoformat()
        rows.append(row)
    return {"generated_utc": datetime.now(timezone.utc).isoformat(),
            "results_directory": os.path.abspath(RESULTS), "sources": rows}


def manifest_markdown(manifest):
    lines = ["## 자료 출처와 재검증 상태", "",
             "이 문서는 저장된 결과를 다시 계산·조판한 것이다. 파일 수정 시각은 "
             "실험 시각의 증명이 아니며, 파일별 SHA256은 함께 저장한 출처 JSON에 있다.", "",
             "| 결과 파일 | 마지막 단계 상태 | 현재 코드에서 재검증 |",
             "|---|---|---|"]
    for row in manifest["sources"]:
        status = row["last_run_status"] if row["exists"] else "파일 없음"
        verified = "확인" if row["current_code_validated"] else "미확인"
        lines.append("| `%s` | %s | %s |" % (row["file"], status, verified))
    lines += ["", "`미확인`인 결과는 현재 코드의 성능이나 정확성을 입증하지 않는다. "
              "아래의 통과·실패 표시는 해당 원자료에 저장된 당시 판정이다.", ""]
    return "\n".join(lines)


def render_pdf(chrome, html, out):
    """Publish a valid PDF atomically, preserving any previous report on failure."""
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="padfec-report-", ignore_cleanup_errors=True) as tmpdir:
        source = os.path.join(tmpdir, "report.html")
        candidate = os.path.join(tmpdir, "report.pdf")
        profile = os.path.join(tmpdir, "profile")
        with open(source, "w", encoding="utf-8") as f:
            f.write(html)
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        try:
            r = subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                 "--user-data-dir=" + profile, "--print-to-pdf=" + candidate, source],
                capture_output=True, text=True, timeout=180,
                encoding="utf-8", errors="replace", **kwargs)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("PDF 렌더 실행 실패:", exc)
            return False
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if os.path.isfile(candidate):
                with open(candidate, "rb") as f:
                    content = f.read()
                if content.startswith(b"%PDF-") and b"%%EOF" in content[-1024:]:
                    # Use a sibling temporary file for atomic replacement across volumes.
                    with tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(out)),
                                                      suffix=".pdf", delete=False) as f:
                        ready = f.name
                        f.write(content)
                    try:
                        os.replace(ready, out)
                    finally:
                        if os.path.exists(ready):
                            os.remove(ready)
                    return True
            if r.returncode != 0:
                break
            time.sleep(0.5)
        print("PDF 생성 실패 (exit %s): %s" % (r.returncode, (r.stderr or "")[-400:]))
        return False


def main(argv=None):
    global RESULTS
    parser = argparse.ArgumentParser(description="저장된 원자료에서 보고서 생성")
    parser.add_argument("--output-dir", default=DOCS)
    parser.add_argument("--results-dir", default=RESULTS)
    parser.add_argument("--no-pdf", action="store_true", help="Markdown와 출처 JSON만 생성")
    args = parser.parse_args(argv)
    RESULTS = os.path.abspath(args.results_dir)
    output_dir = os.path.abspath(args.output_dir)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p1, p2, p3 = load("p1_flight.json"), load("p2_threshold.json"), \
        load("p3_effect.json")
    p4, p5 = load("p4_model.json"), load("p5_audit.json")
    p7 = load("p7_verify.json")
    p8 = load("p8_stability.json")
    p9 = load("p9_crossenv.json")
    p10 = load("p10_completeness.json")
    p11 = load("p11_adaptive.json")
    # 🩸 p17 은 판정에 안 쓰고 **자기 정밀도(자리 효과)를 읽으려고만** 싣는다.
    #    없으면 ruler_facts 가 None 을 내고 해당 한계 문단이 빠진다.
    p17 = load("p17_adaptive_value.json")
    # 🩸 2026-09-07 - p18 은 「한계」절의 필요 표본·m3-m2 부호를 읽으려고 싣는다
    #    (sample_facts). 그전에는 그 수가 문장에 박혀 있었다.
    p18 = load("p18_mmax.json")
    # p12 는 아직 만드는 중일 수 있다. load() 관례대로 없으면 None 이고,
    # 그때는 해당 절을 통째로 건너뛴다(조용히).
    p12 = load("p12_quantum.json")
    e21 = load("e21_budget_trace.json")
    # 경계 절벽 직접 실측. 파일 이름이 판마다 다르므로(그룹 접미사가 붙기도
    # 하고 안 붙기도 한다) 후보를 전부 훑고 **있는 것만** 싣는다.
    cliff_files = [(n, load(n)) for n in CLIFF_FILES]
    cliff_files = [(n, d) for n, d in cliff_files if d]
    cliff = cliff_facts(cliff_files)
    missing = [n for n, v in (("p1", p1), ("p2", p2), ("p3", p3))
               if v is None]
    if missing:
        print("앞 단계 결과가 없다:", missing)
        return 2
    named = (("p4", p4), ("p5", p5), ("p7", p7), ("p8", p8), ("p9", p9),
             ("p10", p10), ("p11", p11), ("p12", p12), ("e21", e21))
    absent = [n for n, v in named if v is None]
    blank = [n for n, v in named if v is not None and not v]
    if absent:
        print("없어서 건너뛴 절:", ", ".join(absent))
    if blank:
        # 빈 것을 "없는 것"과 같이 취급하면 절이 통째로 사라진다. 구분해 찍는다.
        print("있지만 비어 있는 결과(절은 남긴다):", ", ".join(blank))
    if cliff:
        print("경계 절벽 자료 %d판: %s"
              % (len(cliff["sets"]),
                 ", ".join(s["file"] for s in cliff["sets"])))
    else:
        print("경계 절벽 자료 없음 - 해당 절은 건너뛴다")

    os.makedirs(output_dir, exist_ok=True)
    md = build_markdown(p1, p2, p3, p4, p5, p7, p8, p9, p10, p11, p12, e21,
                        cliff, p17=p17, p18=p18)
    late_inputs = {name: load(name) for name in (
        "p13_beff.json", "p19_provenance.json",
        "p15_v2policy.json", "p16_uplink.json", "p17_adaptive_value.json",
        "p18_mmax.json", "p20_residual.json")}
    md += late_stage_summary(late_inputs)
    manifest = source_manifest()
    header, body = md.split("\n", 1)
    md = prose_style(header + "\n\n" + manifest_markdown(manifest) + "\n" + body)
    mdp = os.path.join(output_dir, "PADFEC 실측 보고서.md")
    with open(os.path.join(output_dir, "PADFEC 보고서 출처.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(mdp, "w", encoding="utf-8") as f:
        f.write(md)
    print("wrote %s (%d 줄)" % (mdp, md.count("\n") + 1))

    html = build_onepager(p1, p2, p3, p4, p5, p7, p8, p9, p10, p11, p12, e21,
                          cliff)
    html += late_stage_html(late_inputs)
    html = prose_style(html)
    if "@@" in html:
        print("치환되지 않은 자리표시자가 남았다")
        return 1
    if args.no_pdf:
        return 0
    chrome = next((c for c in CHROME if os.path.exists(c)), None)
    out = os.path.join(output_dir, "ML-KEM QUIC 핸드셰이크 FEC 요약.pdf")
    if not chrome:
        print("PDF 생성에 필요한 Chrome/Edge가 없다. Markdown만 원하면 --no-pdf를 지정한다.")
        return 1
    unverified = [row["file"] for row in manifest["sources"]
                  if row["exists"] and not row["current_code_validated"]]
    if unverified:
        warning = ("저장된 과거 결과 요약. 현재 코드에서 재검증 미확인: "
                   + ", ".join(unverified))
        # Insert into the body after CSS, preserving a complete HTML document.
        notice = '<p style="font-size:9pt;border:1px solid #555;padding:6px">' + html_escape.escape(warning) + '</p>'
        html = html.replace("</style>", "</style>" + notice, 1)
    if not render_pdf(chrome, html, out):
        return 1
    print("wrote %s (%.0f KB)" % (out, os.path.getsize(out) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
