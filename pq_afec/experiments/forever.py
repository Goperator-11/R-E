from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE = os.path.join(HERE, "state")
RESULTS = os.path.join(HERE, "results")
HISTORY = os.path.join(STATE, "history.jsonl")

sys.path.insert(0, HERE)
import loop2

MEASURE = ["p1", "p2", "p3", "p7", "p8", "p9", "p10", "p11", "p12",
           "p4", "p5", "p13", "p14", "p16", "p17", "p15", "p18",
           "p20", "p6", "p19"]


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def load(name):
    p = os.path.join(RESULTS, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _newest_mtime(outputs):
    newest = None
    for o in outputs or []:
        p = os.path.join(ROOT, *o.split("/"))
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return newest


def passcount(d):
    if not d:
        return None
    passed, total = d.get("passed"), d.get("total")
    if passed is None or total is None:
        return None
    return [passed, total]


def _checks_of(d):
    if not d:
        return None
    checks = d.get("checks")
    if checks is None:
        return None
    return checks


def checknames(d):
    checks = _checks_of(d)
    if checks is None:
        return None
    return [str(c.get("check", ""))[:40] for c in checks]


def failednames(d):
    checks = _checks_of(d)
    if checks is None:
        return None
    return [str(c.get("check", ""))[:40] for c in checks if not c.get("ok")]


def jump_bytes(p12, group):
    if not p12:
        return None
    top = p12.get("jump_bytes")
    if isinstance(top, (int, float)) and not isinstance(top, bool):
        return top
    for c in p12.get("configs", []):
        if c.get("group") == group and c.get("ips") == 1281:
            v = c.get("jump_from_prev")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
            return None
    return None


def snapshot(rnd):
    p1, p2, p3 = load("p1_flight.json"), load("p2_threshold.json"), \
        load("p3_effect.json")
    p4, p5 = load("p4_model.json"), load("p5_audit.json")
    p7, p8 = load("p7_verify.json"), load("p8_stability.json")
    p11, p12 = load("p11_adaptive.json"), load("p12_quantum.json")

    def thr(group, arm):
        for r in (p2 or {}).get("thresholds", []):
            if r["group"] == group and r["arm"] == arm and r.get("threshold_lo"):
                return [r["threshold_lo"], r["threshold_hi"]]
        return None

    def eff(group, loss, arm, field):
        for r in (p3 or {}).get("runs", []):
            if (r["group"] == group and r["loss"] == loss
                    and r["burst"] == 1.0 and r["dir"] == "c2s"
                    and r["arm"] == arm and r.get("valid")):
                return r.get(field)
        return None

    return {
        "round": rnd,
        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "k_mlkem": next((c["k"] for c in (p1 or {}).get("capacity_checks", [])
                         if c["group"] == "X25519MLKEM768" and c["ips"] == 0),
                        None),
        "C_mlkem": next((c["C"] for c in (p1 or {}).get("capacity_checks", [])
                         if c["group"] == "X25519MLKEM768" and c["ips"] == 0),
                        None),
        "any_inplace": (p1 or {}).get("any_inplace_feasible"),
        "thr_off_mlkem": thr("X25519MLKEM768", "off"),
        "thr_on1_mlkem": thr("X25519MLKEM768", "on1"),
        "thr_off_x25519": thr("x25519", "off"),
        "p95_off": eff("X25519MLKEM768", 2.0, "off", "p95"),
        "p95_on1": eff("X25519MLKEM768", 2.0, "on1", "p95"),
        "p99_off": eff("X25519MLKEM768", 2.0, "off", "p99"),
        "p99_on1": eff("X25519MLKEM768", 2.0, "on1", "p99"),
        "p4_threshold_hits": (p4 or {}).get("threshold_hits"),
        "p4_hct_mae": (p4 or {}).get("hct_mae_ms"),
        "p5_pass": passcount(p5),
        "p7_pass": passcount(p7),
        "p8_pass": passcount(p8),
        "p8_checks": checknames(p8),
        "p11_pass": passcount(p11),
        "p11_checks": checknames(p11),
        "p11_failed_checks": failednames(p11),
        "p11_worst_regret_ms": (p11 or {}).get("worst_regret_ms"),
        "p11_worst_regret_late_ms": (p11 or {}).get("worst_regret_late_ms"),
        "p11_worst_regret_ci95_half_ms":
            (p11 or {}).get("worst_regret_ci95_half_ms"),
        "p11_worst_regret_late_ci95_half_ms":
            (p11 or {}).get("worst_regret_late_ci95_half_ms"),
        "p11_worst_ci95_half_ms": (p11 or {}).get("worst_ci95_half_ms"),
        "p12_pass": passcount(p12),
        "p12_checks": checknames(p12),
        "p12_failed_checks": failednames(p12),
        "p12_jump_bytes": jump_bytes(p12, "x25519"),
        "p12_jump_bytes_mlkem": jump_bytes(p12, "X25519MLKEM768"),
        "p9_agree": (load("p9_crossenv.json") or {}).get("all_agree"),
        "p9_A_mlkem": ((load("p9_crossenv.json") or {}).get("A", {})
                       .get("X25519MLKEM768", {}).get("threshold")),
        "p9_B_mlkem": ((load("p9_crossenv.json") or {}).get("B", {})
                       .get("X25519MLKEM768", {}).get("threshold")),
    }


def read_history():
    out = []
    if not os.path.exists(HISTORY):
        return out
    with open(HISTORY, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def algo_fingerprint():
    import glob as _g
    h = hashlib.sha256()
    files = []
    for pat in ("padfec/*.py", "experiments/quicbed/*.go"):
        files += _g.glob(os.path.join(ROOT, *pat.split("/")))
    for f in sorted(files):
        h.update(os.path.relpath(f, ROOT).replace("\\", "/").encode())
        with open(f, "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()[:12]


def append_history(rec):
    rec.setdefault("algo_fp", algo_fingerprint())
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


SNAPSHOT_STAGES = ("p1", "p2", "p3", "p4", "p5", "p7", "p8", "p9", "p11", "p12")


def invalid_reasons(h):
    bad = []

    _fp = h.get("algo_fp")
    if not _fp:
        bad.append("알고리즘 지문 없음(어느 코드로 돌았는지 알 수 없다)")
    elif _fp != algo_fingerprint():
        bad.append("알고리즘이 다르다(지문 %s != 현재 %s)"
                   % (_fp, algo_fingerprint()))
    if h.get("measured") is False:
        bad.append("아무것도 안 쟀다(상류 복구 실패)")
    if h.get("loop_skipped"):
        _POST = {"p6", "p19"}
        _raw = h.get("stage_raw") or {}
        _skipped = [sid for sid in MEASURE
                    if _raw.get(sid) not in ("done", "failed")]
        _meas_skipped = [sid for sid in _skipped if sid not in _POST]
        if _meas_skipped:
            bad.append("loop2 가 **측정** 단계를 건너뜀(exit 3): %s"
                       % ", ".join(_meas_skipped))

    rc = h.get("loop_exit")
    if rc is not None and rc not in (0, 3):
        bad.append("loop2 가 완주하지 못했다(exit %s - 실패해서 멈췄거나 "
                   "인자 오류)" % rc)

    raw = h.get("stage_raw")
    state = h.get("stage_state") or {}
    started = h.get("started_epoch")
    mtimes = h.get("out_mtime")
    for sid in SNAPSHOT_STAGES:
        if raw is not None and sid in raw:
            if raw.get(sid) not in ("done", "failed"):
                bad.append("%s(안 돎:%s)" % (sid, raw.get(sid)))
                continue
        if started is not None and mtimes is not None:
            m = mtimes.get(sid)
            if not isinstance(m, (int, float)) or isinstance(m, bool):
                bad.append("%s(결과 파일이 없다)" % sid)
                continue
            if m < started:
                bad.append("%s(결과 파일이 이번 라운드에 안 쓰였다)" % sid)
                continue
        v = state.get(sid)
        if v and v[0] == "stale":
            bad.append("%s(코드가 바뀐 뒤 안 돎)" % sid)

    if raw is None and not state:
        for item in (h.get("not_done") or []):
            if item.split("(")[0] in SNAPSHOT_STAGES:
                bad.append(item)

    for item in (h.get("not_done") or []):
        if item.startswith("<"):
            bad.append(item)
    return bad


def judgeable(h):
    return (h.get("stage_raw") is not None
            or bool(h.get("stage_state"))
            or ("measured" in h)
            or h.get("started_epoch") is not None)


def split_rounds(hist):
    good, dropped = [], []
    for h in hist:
        why = invalid_reasons(h)
        if why:
            dropped.append((h.get("round"), why))
        else:
            good.append(h)
    return good, dropped, [h for h in good if judgeable(h)]


def verdict(n, same):
    if n < 2:
        return "판정 보류"
    return "안정" if same else "흔들림"


def grouped_pass(hist, pass_field, checks_field, label):
    seq = sorted([h for h in hist if h.get(pass_field)],
                 key=lambda h: h.get("round", -1))
    if not seq:
        return None

    groups = {}
    for h in seq:
        key = tuple(h.get(checks_field) or [])
        g = groups.setdefault(key, {"vals": [], "rounds": []})
        g["vals"].append(h[pass_field])
        g["rounds"].append(h.get("round"))

    changes, prev = [], None
    for h in seq:
        key = tuple(h.get(checks_field) or [])
        if prev is not None and key != prev:
            changes.append({
                "round": h.get("round"),
                "added": [c for c in key if c not in prev],
                "removed": [c for c in prev if c not in key]})
        prev = key

    cur_key = max(groups,
                  key=lambda k: max([r for r in groups[k]["rounds"]
                                     if r is not None] or [-1]))
    cur = groups[cur_key]
    vals = cur["vals"]

    if changes:
        note = "검사 기준이 %d 번 바뀌었다 - " % len(changes) + " / ".join(
            "라운드 %s: +[%s] -[%s]"
            % (c["round"], ", ".join(c["added"]) or "없음",
               ", ".join(c["removed"]) or "없음") for c in changes)
        note += " / 아래 값은 최신 기준(라운드 %s)만 모은 것이다" % (
            ", ".join(str(r) for r in cur["rounds"]))
    else:
        note = "검사 기준이 한 번도 안 바뀌었다 (전 라운드 비교 가능)"

    same = all(v == vals[0] for v in vals)
    vd = verdict(len(vals), same)
    return {"field": pass_field, "label": label + " (최신 검사 기준)",
            "verdict": vd, "n": len(vals),
            "stable": None if vd == "판정 보류" else same, "values": vals,
            "rounds": cur["rounds"], "n_bases": len(groups),
            "basis_changes": changes, "checks": list(cur_key),
            "note": note}


def analyse(hist_all):
    findings = []
    hist, dropped, verified = split_rounds(hist_all)
    n_unjudged = len(hist) - len(verified)

    findings.append({
        "field": "valid_rounds",
        "label": "표본 라운드 (검증됨 + 판정 근거 없음)",
        "verdict": "정보", "stable": None, "n": len(hist),
        "n_verified": len(verified), "n_unjudged": n_unjudged,
        "verified_rounds": [h.get("round") for h in verified][-8:],
        "values": [h.get("round") for h in hist][-8:],
        "dropped": [{"round": r, "why": w} for r, w in dropped],
        "note": "전체 %d 라운드 중 표본 %d 개 = **실제로 쟀음이 검증된 %d 개** "
                "+ 판정 근거 없음 %d 개(stage_raw/measured/out_mtime 이 아예 "
                "없던 옛 줄 - '통과'가 아니라 '모름'이다). 제외 %d 개%s"
                % (len(hist_all), len(hist), len(verified), n_unjudged,
                   len(dropped),
                   (": " + " / ".join("라운드 %s(%s)" % (r, "; ".join(w))
                                      for r, w in dropped[-6:]))
                   if dropped else "")})

    def const(field, label, exact=True):
        vals = [h.get(field) for h in hist if h.get(field) is not None]
        if not vals:
            return
        same = all(v == vals[0] for v in vals)
        vd = verdict(len(vals), same)
        findings.append({"field": field, "label": label, "verdict": vd,
                         "n": len(vals),
                         "stable": None if vd == "판정 보류" else same,
                         "values": vals[-6:]})

    const("k_mlkem", "ML-KEM 첫 비행 데이터그램 수")
    const("any_inplace", "제자리(무비용) 배치 가능 여부")
    const("thr_off_mlkem", "ML-KEM 기준선 임계 구간")
    const("thr_on1_mlkem", "ML-KEM FEC(m=1) 임계 구간")
    const("thr_off_x25519", "x25519 기준선 임계 구간")
    const("p5_pass", "독립 감사 통과 수")
    const("p7_pass", "결정적 검증 통과 수")
    for f in (grouped_pass(hist, "p8_pass", "p8_checks", "반복/음성대조 통과 수"),
              grouped_pass(hist, "p11_pass", "p11_checks", "폐루프 후회 통과 수"),
              grouped_pass(hist, "p12_pass", "p12_checks", "양자 경계 절벽 통과 수")):
        if f:
            findings.append(f)

    const("p11_failed_checks", "폐루프에서 실패 중인 검사 이름")
    const("p9_agree", "두 환경 + 팀 자료가 같은 칸")
    const("p9_A_mlkem", "환경 A(문서) ML-KEM 임계")
    const("p9_B_mlkem", "환경 B(1차) ML-KEM 임계")

    cs = [h["C_mlkem"] for h in hist if h.get("C_mlkem")]
    if cs:
        vd = verdict(len(cs), (max(cs) - min(cs)) <= 24)
        findings.append({"field": "C_mlkem", "label": "ML-KEM ClientHello C",
                         "verdict": vd, "n": len(cs),
                         "stable": (None if vd == "판정 보류"
                                    else (max(cs) - min(cs)) <= 24),
                         "values": cs[-6:],
                         "note": "최대-최소 %d B" % (max(cs) - min(cs))})

    def band(field, label, tol, unit, tol_field=None, tol_mult=2.0):
        vals = [h.get(field) for h in hist
                if isinstance(h.get(field), (int, float))
                and not isinstance(h.get(field), bool)]
        if not vals:
            return
        basis, hw, tol_fixed = "고정", None, tol
        if tol_field:
            hs = [h.get(tol_field) for h in hist
                  if isinstance(h.get(tol_field), (int, float))
                  and not isinstance(h.get(tol_field), bool)
                  and h.get(tol_field) > 0]
            if hs:
                hw = max(hs)
                tol, basis = tol_mult * hw, "정밀도"
        spread = max(vals) - min(vals)
        inband = spread <= tol
        vd = verdict(len(vals), inband)
        if vd == "안정" and basis == "정밀도":
            vd = "정밀도 안"
        findings.append({"field": field, "label": label,
                         "verdict": vd, "n": len(vals),
                         "stable": None if vd == "판정 보류" else inband,
                         "values": [round(v, 3) for v in vals[-6:]],
                         "band_basis": basis, "band_tol": tol,
                         "band_halfwidth": hw, "band_fixed": tol_fixed,
                         "spread": spread,
                         "note": ("최대-최소 %.3f %s (감시 띠 %.3f %s = %s, "
                                  "판정 아님)"
                                  % (spread, unit, tol, unit,
                                     ("신고 반폭 %.3f x%g" % (hw, tol_mult))
                                     if basis == "정밀도"
                                     else "손으로 고른 고정값 - 이 수의 "
                                          "정밀도가 기록에 없다"))})

    band("p11_worst_regret_ms", "폐루프 최악 후회 (전 구간)", 1.0, "ms",
         tol_field="p11_worst_regret_ci95_half_ms")
    band("p11_worst_regret_late_ms", "폐루프 최악 후회 (수렴 후)", 1.0, "ms",
         tol_field="p11_worst_regret_late_ci95_half_ms")
    band("p12_jump_bytes", "양자 경계 도약폭 x25519 (1280->1281)", 128, "B")
    band("p12_jump_bytes_mlkem", "같은 도약폭 ML-KEM (k=2 교차)", 128, "B")
    const("p12_failed_checks", "양자 경계에서 실패 중인 검사 이름")

    for field, label in (("p99", "c2s 2% 손실에서 FEC 가 p99 를 줄인다"),
                         ("p95", "참고: 같은 조건의 p95 방향 (불안정)")):
        dirs = []
        for h in hist:
            a, b = h.get(field + "_off"), h.get(field + "_on1")
            if a is not None and b is not None:
                dirs.append(b < a)
        if dirs:
            if field == "p99":
                ok = all(dirs)
                vd = verdict(len(dirs), ok)
                st = None if vd == "판정 보류" else ok
                note = ""
            else:
                vd, ok, st = "정보", None, None
                note = ("불연속면에 걸린 통계라 흔들리는 것이 정상. "
                        "%d 라운드 중 %d 회 감소 (판정 아님)"
                        % (len(dirs), sum(1 for d in dirs if d)))
            findings.append({
                "field": field + "_direction", "label": label,
                "verdict": vd, "n": len(dirs), "stable": st,
                "values": dirs[-8:], "note": note})
    return findings


def run_loop2(ids, keep_going, log_path):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [sys.executable, os.path.join(HERE, "loop2.py"), "--only"] + list(ids)
    if keep_going:
        cmd.append("--keep-going")
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                       text=True, errors="replace")
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        f.write((r.stdout or "") + (r.stderr or ""))
    return r.returncode


def stale_prereqs():
    stages = loop2.build_stages()
    by = {s.id: s for s in stages}
    st = loop2.load_state()
    pre = [sid for sid in loop2.dep_closure(stages, MEASURE)
           if sid not in MEASURE]
    return [sid for sid in pre
            if loop2.stage_status(by[sid], st)[0] != "done"]


def main():
    harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--stop-on-fail", action="store_true",
                    help="단계가 실패하면 멈춘다 (기본은 기록하고 계속)")
    a = ap.parse_args()

    hist = read_history()
    start = (max(h["round"] for h in hist) + 1) if hist else 0
    print("이미 끝난 라운드 %d 개. %d 번부터 %d 라운드 더 돈다."
          % (len(hist), start, a.rounds))
    sys.stdout.flush()

    for rnd in range(start, start + a.rounds):
        print()
        print("#" * 100)
        print("# 라운드 %d 시작  (%s)"
              % (rnd, datetime.datetime.now().strftime("%H:%M:%S")))
        print("#" * 100)
        sys.stdout.flush()

        prereq = stale_prereqs()
        rebuilt = []
        if prereq:
            print("  ⚠ 무효한 상류: %s - 측정 전에 먼저 돌린다"
                  % ", ".join(prereq))
            sys.stdout.flush()
            plog = os.path.join(STATE, "forever_round%d_prereq.txt" % rnd)
            run_loop2(prereq, keep_going=False, log_path=plog)
            rebuilt = prereq
            still = stale_prereqs()
            if still:
                print("  ✗ 상류를 되돌리지 못했다: %s" % ", ".join(still))
                print("    이 라운드를 거부한다 (로그 %s). 상류를 고친 뒤 "
                      "같은 명령을 다시 실행하면 이어서 간다." % plog)
                snap = snapshot(rnd)
                snap["prereq_failed"] = still
                snap["prereq_rebuilt"] = rebuilt
                snap["measured"] = False
                append_history(snap)
                break

        for f in glob.glob(os.path.join(STATE, "p*_units.jsonl")):
            try:
                os.unlink(f)
            except OSError:
                pass

        log = os.path.join(STATE, "forever_round%d.txt" % rnd)
        t_round_start = time.time()
        rc = run_loop2(MEASURE, keep_going=not a.stop_on_fail, log_path=log)

        snap = snapshot(rnd)
        snap["loop_exit"] = rc
        snap["started_epoch"] = t_round_start
        snap["prereq_rebuilt"] = rebuilt
        snap["measured"] = True
        snap["loop_skipped"] = (rc == 3)
        try:
            _stages = loop2.build_stages()
            _st = loop2.load_state()
            snap["stage_state"] = {
                s.id: [loop2.stage_status(s, _st)[0],
                       (_st["stages"].get(s.id) or {}).get("finished")]
                for s in _stages}
            snap["not_done"] = ["%s(%s)" % (sid, v[0])
                                for sid, v in snap["stage_state"].items()
                                if v[0] != "done"]
            snap["stage_raw"] = {
                s.id: (_st["stages"].get(s.id) or {}).get("status")
                for s in _stages}
            snap["out_mtime"] = {s.id: _newest_mtime(s.outputs)
                                 for s in _stages}
        except Exception as e:
            snap["stage_state"] = {}
            snap["stage_raw"] = None
            snap["out_mtime"] = None
            snap["not_done"] = ["<상태를 못 읽음: %s>" % e]
        append_history(snap)
        print("라운드 %d 끝 (exit %d). 로그 %s" % (rnd, rc, log))
        print("  ML-KEM 임계 기준선 %s / FEC %s | p95 %s -> %s | "
              "검증 p5 %s p7 %s p8 %s"
              % (snap["thr_off_mlkem"], snap["thr_on1_mlkem"],
                 snap["p95_off"], snap["p95_on1"], snap["p5_pass"],
                 snap["p7_pass"], snap["p8_pass"]))
        print("  폐루프 p11 %s | 최악 후회 전구간 %s ms / 수렴후 %s ms%s"
              % (snap["p11_pass"], snap["p11_worst_regret_ms"],
                 snap["p11_worst_regret_late_ms"],
                 (" | 실패: " + "; ".join(snap["p11_failed_checks"]))
                 if snap["p11_failed_checks"] else ""))
        print("  양자경계 p12 %s | 도약폭 x25519 %s B / ML-KEM %s B%s"
              % (snap["p12_pass"], snap["p12_jump_bytes"],
                 snap["p12_jump_bytes_mlkem"],
                 (" | 실패: " + "; ".join(snap["p12_failed_checks"]))
                 if snap["p12_failed_checks"] else ""))
        if snap["not_done"]:
            print("  ⚠ done 아닌 단계: %s" % ", ".join(snap["not_done"]))
        sys.stdout.flush()

        hist = read_history()
        findings = analyse(hist)
        unstable = [f for f in findings if f.get("verdict") == "흔들림"]
        held = [f for f in findings if f.get("verdict") == "판정 보류"]
        stable = [f for f in findings if f.get("verdict") == "안정"]
        within = [f for f in findings if f.get("verdict") == "정밀도 안"]
        info = [f for f in findings if f.get("verdict") == "정보"]
        rest = (len(findings) - len(stable) - len(unstable)
                - len(held) - len(info) - len(within))
        valid = next((f for f in findings
                      if f["field"] == "valid_rounds"), None)
        if findings:
            print("  라운드 간 안정성: 안정 %d / 정밀도 안(구별불가) %d / "
                  "흔들림 %d / 판정 보류 %d / "
                  "정보 %d%s = 총 %d 항목  (표본 %s 라운드 = 검증 %s + "
                  "판정근거없음 %s, 전체 %d 중)"
                  % (len(stable), len(within), len(unstable),
                     len(held), len(info),
                     (" / 분류 안 됨 %d" % rest) if rest else "",
                     len(findings),
                     (valid or {}).get("n", "?"),
                     (valid or {}).get("n_verified", "?"),
                     (valid or {}).get("n_unjudged", "?"), len(hist)))
            for f in unstable:
                print("  ⚠ 흔들림: %s -> %s  (%s)"
                      % (f["label"], f["values"], f.get("note", "")))
            for f in within:
                print("  · 정밀도 안(구별 불가): %s -> %s  (%s)"
                      % (f["label"], f["values"], f.get("note", "")))
            for d in (valid or {}).get("dropped", [])[-4:]:
                print("  ⚠ 표본에서 뺀 라운드 %s: %s"
                      % (d["round"], "; ".join(d["why"])))
        loop2.atomic_write_json(
            os.path.join(RESULTS, "stability_report.json"),
            {"history": hist, "findings": findings})
        sys.stdout.flush()

    print()
    print("=" * 100)
    hist = read_history()
    findings = analyse(hist)
    _valid = next((f for f in findings if f["field"] == "valid_rounds"), None)
    print("총 %d 라운드 (표본 %s 개 = 실제로 쟀음이 검증된 %s 개 + "
          "판정 근거 없는 %s 개). 안정성 요약"
          % (len(hist), (_valid or {}).get("n", "?"),
             (_valid or {}).get("n_verified", "?"),
             (_valid or {}).get("n_unjudged", "?")))
    if _valid and _valid.get("dropped"):
        for d in _valid["dropped"]:
            print("        제외 @라운드 %s  %s" % (d["round"], "; ".join(d["why"])))
    for f in findings:
        print("  [%s] n=%-3s %-34s %s"
              % (f.get("verdict", "?"), f.get("n", "?"), f["label"],
                 f["values"]))
        for c in f.get("basis_changes", []):
            print("        기준 변경 @라운드 %s  +[%s]  -[%s]"
                  % (c["round"], ", ".join(c["added"]) or "없음",
                     ", ".join(c["removed"]) or "없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
