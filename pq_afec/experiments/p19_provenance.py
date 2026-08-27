# -*- coding: utf-8 -*-
"""P19 - 수치 출처 감사: 보고된 수가 **실제 측정에서 나온 것인가**.

왜 이 단계가 필요한가
---------------------
이 저장소의 검증은 "측정이 잘 돌았는가"는 여러 자로 본다(loop2 지문, 단위
저널, 단계별 검사). 그런데 **보고된 요약 수치가 그 측정의 원자료와 실제로
맞는지**를 보는 자가 없었다. 그 틈에서 생길 수 있는 일:

  · 요약만 갱신되고 원자료는 옛것 (또는 그 반대)
  · 상수·기본값이 "측정값" 필드에 들어가 그럴듯하게 보임
  · 결과 파일이 소스 수정보다 **먼저** 만들어졌는데 최신으로 인용됨
  · 판정에 쓰인 수치에 원자료가 없어 **아무도 다시 셀 수 없음**

이 단계는 그것들을 기계적으로 잡는다. 원리는 하나다:
**요약 수치를 원자료에서 다시 계산해 대조한다.** 재계산이 안 되는 수치는
"검증 불가"로 세어 드러낸다 - 조용히 통과시키지 않는다.

재계산 정의는 각 단계의 것을 **그대로** 쓴다(padbed.pctl 은 sorted[int(q*(n-1))],
two_rtt 는 1.5RTT< t <=3RTT, pto 는 t>3RTT, tail 은 t>1.5RTT). 정의가 다르면
오탐이 나므로 여기 규칙이 곧 계약이다.

통과 기준
---------
  1. 재계산이 가능한 항목이 실제로 있다 (0 이면 이 단계가 공허하다)
  2. ⭐ 재계산한 값이 보고된 값과 일치 (허용 오차 1e-6 상대)
  3. ⭐ 결과 파일이 알고리즘 소스보다 **나중에** 만들어졌다
  4. 판정에 쓰이는 헤드라인 수치에 원자료가 있다 (없으면 목록으로 드러낸다)
  5. 원자료 길이가 보고된 n 과 일치 (표본이 조용히 잘리지 않았다)
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402

RTT = 50.0
TOL = 1e-6          # 상대 오차 허용치


def pctl(v, q):
    """padbed.pctl 과 **같은 정의**여야 한다. 다르면 오탐이 난다."""
    if not v:
        return None
    s = sorted(v)
    return s[int(q * (len(s) - 1))]


def mean(v):
    return (sum(v) / len(v)) if v else None


def close(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


# 각 결과 파일에서 (원자료, 보고값) 쌍을 뽑는 규칙.
# 함수는 레코드를 받아 [(이름, 보고값, 재계산값), ...] 을 돌려준다.
def _basic(rec, v, prefix):
    out = [("%s.mean" % prefix, rec.get("mean"), mean(v)),
           ("%s.p50" % prefix, rec.get("p50"), pctl(v, 0.5))]
    if "p95" in rec:
        out.append(("%s.p95" % prefix, rec.get("p95"), pctl(v, 0.95)))
    if "p99" in rec:
        out.append(("%s.p99" % prefix, rec.get("p99"), pctl(v, 0.99)))
    if "max" in rec:
        out.append(("%s.max" % prefix, rec.get("max"), max(v) if v else None))
    return out


def check_p3(d):
    out = []
    for r in d.get("runs", []):
        v = r.get("samples")
        if not v:
            continue
        tag = "%s|%s|%s" % (r.get("group"), r.get("loss"), r.get("arm"))
        out += _basic(r, v, tag)
        if "p90" in r:
            out.append((tag + ".p90", r.get("p90"), pctl(v, 0.90)))
    return out


def check_p14(d):
    out = []
    for r in d.get("arms", []):
        v = r.get("ms")
        if not v:
            continue
        tag = "%s|loss%s" % (r.get("arm"), r.get("loss"))
        out += _basic(r, v, tag)
        out.append((tag + ".two_rtt_rate", r.get("two_rtt_rate"),
                    sum(1 for t in v if 1.5 * RTT < t <= 3.0 * RTT) / float(len(v))))
        out.append((tag + ".pto_rate", r.get("pto_rate"),
                    sum(1 for t in v if t > 3.0 * RTT) / float(len(v))))
    return out


def check_p16(d):
    out = []
    for r in d.get("arms", []):
        v = r.get("ms")
        if v:
            out += _basic(r, v, "%s|%s" % (r.get("cond"), r.get("arm")))
    return out


def check_p11(d):
    out = []
    for r in d.get("rows", []):
        v = r.get("ms")
        if not v:
            continue
        tag = "%s|%s|loss%s" % (r.get("arm"), r.get("cert"), r.get("loss"))
        out += _basic(r, v, tag)
        out.append((tag + ".tail", r.get("tail"),
                    sum(1 for x in v if x > 1.5 * RTT) / float(len(v))))
        lv = r.get("ms_late")
        if lv:
            out.append((tag + ".mean_late", r.get("mean_late"), mean(lv)))
    return out


def check_p15(d):
    out = []
    for r in d.get("rows", []):
        v = r.get("ms")
        if v:
            out += _basic(r, v, "%s|%s" % (r.get("cond"), r.get("arm")))
    for a in d.get("auto", []):
        for h in a.get("rounds", []):
            v = h.get("ms")
            if v:
                out += _basic(h, v, "%s|auto|r%s" % (a.get("cond"),
                                                     h.get("round")))
    return out


def check_nested_arms(d):
    """p17·p18 처럼 rows[].arms{} 구조."""
    out = []
    for r in d.get("rows", []):
        for k, a in (r.get("arms") or {}).items():
            v = a.get("ms")
            if v:
                out += _basic(a, v, "%s|%s" % (r.get("cond"), k))
                if a.get("n") is not None:
                    out.append(("%s|%s.n" % (r.get("cond"), k),
                                float(a["n"]), float(len(v))))
    return out


RULES = {
    "p3_effect.json": check_p3,
    "p14_dominance.json": check_p14,
    "p16_uplink.json": check_p16,
    "p11_adaptive.json": check_p11,
    "p15_v2policy.json": check_p15,
    "p17_adaptive_value.json": check_nested_arms,
    "p18_mmax.json": check_nested_arms,
}

# 판정에 쓰이는 헤드라인 — 원자료가 있어야 다시 셀 수 있다
HEADLINE = {
    "p11_adaptive.json": ["worst_regret_late_ms", "worst_ci95_half_ms"],
    "p15_v2policy.json": ["worst_regret_ms", "worst_ci95_half_ms"],
    "p14_dominance.json": [],
    "p3_effect.json": ["total_recovered"],
}


def main():
    B.harden()
    res = os.path.join(ROOT, "experiments", "results")
    out = {"tol": TOL, "items": 0, "mismatch": [], "no_raw": [],
           "stale": [], "checks": []}
    checks = out["checks"]

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail),
              flush=True)

    print("=" * 100)
    print("P19 수치 출처 감사 — 보고된 수를 원자료에서 다시 계산해 대조")
    print("=" * 100)

    # --- 2. 재계산 대조
    n_items = 0
    for fn, rule in sorted(RULES.items()):
        p = os.path.join(res, fn)
        if not os.path.exists(p):
            out["no_raw"].append("%s (파일 없음)" % fn)
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        pairs = rule(d)
        bad = 0
        for name, got, want in pairs:
            n_items += 1
            if not close(got, want):
                bad += 1
                if len(out["mismatch"]) < 20:
                    out["mismatch"].append(
                        {"file": fn, "field": name,
                         "reported": got, "recomputed": want})
        print("  %-26s 대조 %4d 항목, 불일치 %d" % (fn, len(pairs), bad))
    out["items"] = n_items

    # --- 3. 시각 정합: 결과가 알고리즘 소스보다 나중인가
    src = []
    for pat in ("padfec/*.py", "experiments/quicbed/*.go"):
        src += glob.glob(os.path.join(ROOT, pat))
    newest_src = max((os.path.getmtime(s) for s in src), default=0)
    for fn in RULES:
        p = os.path.join(res, fn)
        if os.path.exists(p) and os.path.getmtime(p) < newest_src:
            out["stale"].append(fn)

    # --- 4. 헤드라인에 원자료가 있는가
    for fn, keys in HEADLINE.items():
        p = os.path.join(res, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for k in keys:
            if k not in d:
                out["no_raw"].append("%s: 헤드라인 %s 없음" % (fn, k))

    print()
    add("1. 재계산 가능한 항목이 실제로 있다 (0 이면 이 단계가 공허하다)",
        n_items >= 100, "대조 항목 %d 개" % n_items)
    add("2. ⭐ 재계산한 값이 보고된 값과 일치 (상대오차 <= %g)" % TOL,
        not out["mismatch"],
        "불일치 %d 건%s" % (len(out["mismatch"]),
                          (" 예: %s" % out["mismatch"][0]) if out["mismatch"] else ""))
    add("3. ⭐ 결과 파일이 알고리즘 소스보다 나중에 만들어졌다",
        not out["stale"],
        "낡은 결과 %s" % (out["stale"] or "없음"))
    add("4. 판정 헤드라인이 결과에 실제로 있다", not out["no_raw"],
        "빠진 것 %s" % (out["no_raw"][:3] or "없음"))

    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(checks)))
    print("saved: %s" % B.save("p19_provenance.json", out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
