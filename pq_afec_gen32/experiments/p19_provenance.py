import glob
import argparse
import json
import hashlib
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from _journal import save_result

RESULTS = os.path.join(HERE, "results")

RTT = 50.0
TOL = 1e-6


def pctl(v, q):
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
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(x) for x in (a, b)):
        return False
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def _basic(rec, v, prefix):
    out = [("%s.mean" % prefix, rec.get("mean"), mean(v)),
           ("%s.p50" % prefix, rec.get("p50"), pctl(v, 0.5))]
    expected = rec.get("ok", rec.get("n"))
    if expected is not None:
        out.append(("%s.raw_success_count" % prefix, expected, len(v)))
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
    rtt = float(d.get("rtt_ms", RTT))
    for r in d.get("rows", []):
        v = r.get("ms")
        if not v:
            continue
        tag = "%s|%s|loss%s" % (r.get("arm"), r.get("cert"), r.get("loss"))
        out += _basic(r, v, tag)
        out.append((tag + ".tail", r.get("tail"),
                    sum(1 for x in v if x > 1.5 * rtt) / float(len(v))))
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


def p17_trial_problems(d):
    problems = []
    for rec in d.get("rows", []):
        if rec.get("protocol", {}).get("version", 0) < 2:
            continue
        protocol = rec["protocol"]
        try:
            cycles = protocol["cycles"]
            schedule = protocol["schedule"]
            arms = protocol["arms"]
            if type(cycles) is not int or cycles <= 0 or not schedule or not arms:
                raise ValueError("empty protocol")
            if any(type(n) is not int or n <= 0 for _, n in schedule):
                raise ValueError("invalid expected trials")
            if len({loss for loss, _ in schedule}) != len(schedule):
                raise ValueError("duplicate scheduled loss")
            if len({a[0] for a in arms}) != len(arms):
                raise ValueError("duplicate planned arm")
            expected = {(c, loss, a[0]): n for c in range(cycles)
                        for loss, n in schedule for a in arms}
        except (KeyError, TypeError, ValueError, IndexError):
            problems.append("p17: protocol v2 계획된 구간 정보 불완전")
            continue
        segments = rec.get("segments")
        if not isinstance(segments, list) or not segments:
            problems.append("p17: protocol v2 구간 원자료 없음")
            continue
        seen = set()
        for j, segment in enumerate(segments):
            key = (segment.get("cycle"), segment.get("loss"), segment.get("arm"))
            if key in seen or key not in expected or segment.get("n_expected") != expected[key]:
                problems.append("p17: 계획과 다른 구간 또는 구간 중복 %s" % (key,))
            seen.add(key)
            rows = segment.get("trial_records")
            n = segment.get("n_expected")
            valid = (type(n) is int and n > 0 and isinstance(rows, list)
                     and len(rows) == n and all(isinstance(r, dict) for r in rows))
            if valid:
                ids = [r.get("i") for r in rows]
                valid = (all(type(i) is int for i in ids) and sorted(ids) == list(range(n))
                         and all(type(r.get("ok")) is bool
                                 and type(r.get("ms")) in (int, float)
                                 and math.isfinite(r["ms"]) and r["ms"] >= 0
                                 and type(r.get("m_used")) is int and r["m_used"] >= 0
                                 for r in rows))
            if not valid:
                problems.append("p17: %s 구간 %d 시행 ID·상태·원자료 불완전" % (rec.get("cond"), j))
        if seen != set(expected):
            problems.append("p17: 계획된 전체 구간 중 누락 또는 추가 구간")
    return problems


def check_p17(d):
    out = check_nested_arms(d)
    if p17_trial_problems(d):
        return out
    for rec in d.get("rows", []):
        if rec.get("protocol", {}).get("version", 0) < 2:
            continue
        collected = {}
        for j, segment in enumerate(rec["segments"]):
            raw = segment["trial_records"]
            success = [r["ms"] for r in raw if r["ok"]]
            tag = "%s|segment%d" % (rec.get("cond"), j)
            out.extend([(tag + ".n", segment.get("n"), len(raw)),
                        (tag + ".ok", segment.get("ok"), len(success)),
                        (tag + ".failed", segment.get("failed"), len(raw) - len(success)),
                        (tag + ".mean", segment.get("mean"), mean(success))])
            collected.setdefault(segment.get("arm"), []).extend(success)
        for arm in set(collected) | set(rec.get("arms", {})):
            actual = collected.get(arm, [])
            reported = rec.get("arms", {}).get(arm, {}).get("ms", [])
            differing = abs(len(actual) - len(reported)) + sum(
                not close(a, b) for a, b in zip(actual, reported))
            out.append(("%s|%s.trial_sample_mismatches" % (rec.get("cond"), arm),
                        0, differing))
    return out


def p18_has_trial_records(d):
    return ("trial_coverage" in d or any(
        "trial_coverage" in r or any("trial_records" in s for s in r.get("segments", []))
        for r in d.get("rows", [])))


def p18_trial_problems(d):
    if not p18_has_trial_records(d):
        return []
    problems = []
    arms = d.get("arms")
    if (not isinstance(arms, list) or not arms
            or not all(type(m) is int and m > 0 for m in arms) or len(set(arms)) != len(arms)):
        return ["p18: 계획된 팔 정보 불완전"]
    expected = {(block, m) for block in range(len(arms)) for m in arms}
    for rec in d.get("rows", []):
        n = rec.get("n_per_block")
        segments = rec.get("segments")
        if type(n) is not int or n <= 0 or not isinstance(segments, list):
            problems.append("p18: 조건별 계획 또는 구간 원자료 없음")
            continue
        seen = set()
        for j, segment in enumerate(segments):
            if not isinstance(segment, dict):
                problems.append("p18: 구간 원자료 형식 오류")
                continue
            key = (segment.get("block"), segment.get("m"))
            if (not all(type(v) is int for v in key) or key in seen or key not in expected
                    or segment.get("planned_n") != n):
                problems.append("p18: 계획과 다른 구간 또는 구간 중복 %s" % (key,))
            if all(type(v) is int for v in key):
                seen.add(key)
            raw = segment.get("trial_records")
            valid = isinstance(raw, list) and len(raw) == n and all(isinstance(t, dict) for t in raw)
            if valid:
                ids = [t.get("i") for t in raw]
                valid = (all(type(i) is int for i in ids) and sorted(ids) == list(range(n))
                         and all(type(t.get("ok")) is bool and type(t.get("ms")) in (int, float)
                                 and math.isfinite(t["ms"]) and t["ms"] >= 0 for t in raw))
            if not valid:
                problems.append("p18: %s 구간 %d 시행 ID·상태·원자료 불완전" % (rec.get("cond"), j))
        if seen != expected:
            problems.append("p18: 계획된 전체 구간 중 누락 또는 추가 구간")
    return problems


def check_p18(d):
    out = check_nested_arms(d)
    if not p18_has_trial_records(d) or p18_trial_problems(d):
        return out
    total = {key: 0 for key in ("planned_n", "recorded_n", "ok_n", "failed_n",
                               "missing_n", "planned_segments", "recorded_segments")}
    all_complete = True
    for rec in d.get("rows", []):
        collected = {}
        counts = dict.fromkeys(total, 0)
        counts["planned_segments"] = len(d["arms"]) ** 2
        counts["recorded_segments"] = len(rec["segments"])
        counts["planned_n"] = rec["n_per_block"] * counts["planned_segments"]
        for j, segment in enumerate(rec["segments"]):
            raw = segment["trial_records"]
            success = [t["ms"] for t in raw if t["ok"]]
            fail = len(raw) - len(success)
            missing = max(0, segment["planned_n"] - len(raw))
            tag = "%s|segment%d" % (rec.get("cond"), j)
            out.extend((tag + "." + field, segment.get(field), value) for field, value in
                       (("n", len(raw)), ("ok", len(success)), ("fail", fail),
                        ("missing", missing), ("mean", mean(success))))
            collected.setdefault(str(segment["m"]), []).extend(success)
            counts["recorded_n"] += len(raw)
            counts["ok_n"] += len(success)
            counts["failed_n"] += fail
            counts["missing_n"] += missing
        complete = not (rec.get("err") or counts["failed_n"] or counts["missing_n"]
                        or any(s.get("err") for s in rec["segments"]))
        all_complete = all_complete and complete
        coverage = rec.get("trial_coverage", {})
        for key, value in counts.items():
            out.append(("%s|coverage.%s" % (rec.get("cond"), key), coverage.get(key), value))
            total[key] += value
        for label, reported in (("complete", rec.get("complete")),
                                ("coverage.complete", coverage.get("complete"))):
            out.append(("%s|%s" % (rec.get("cond"), label),
                        int(reported) if type(reported) is bool else None, int(complete)))
        for arm in set(collected) | set(rec.get("arms", {})):
            actual = collected.get(arm, [])
            reported = rec.get("arms", {}).get(arm, {}).get("ms", [])
            differing = abs(len(actual) - len(reported)) + sum(
                not close(a, b) for a, b in zip(actual, reported))
            out.append(("%s|%s.trial_sample_mismatches" % (rec.get("cond"), arm), 0, differing))
    coverage = d.get("trial_coverage", {})
    out.extend(("coverage." + key, coverage.get(key), value) for key, value in total.items())
    reported = coverage.get("complete")
    out.append(("coverage.complete", int(reported) if type(reported) is bool else None,
                int(bool(d.get("rows")) and all_complete)))
    return out


def trial_record_limits(d, filename):
    if filename == "p18_mmax.json" and not p18_has_trial_records(d):
        return ["p18: 과거 자료에는 시행별 ID·성공/실패 원형이 없어 성공 ms 집계만 대조함"]
    return []


def missing_raw(d, filename):
    if filename == "p3_effect.json":
        records = [(r, "samples") for r in d.get("runs", [])]
    elif filename in ("p17_adaptive_value.json", "p18_mmax.json"):
        records = [(a, "ms") for r in d.get("rows", [])
                   for a in (r.get("arms") or {}).values()]
    elif filename in ("p14_dominance.json", "p16_uplink.json"):
        records = [(r, "ms") for r in d.get("arms", [])]
    else:
        records = [(r, "ms") for r in d.get("rows", [])]
        records += [(h, "ms") for a in d.get("auto", []) for h in a.get("rounds", [])]
    problems = []
    if not records:
        problems.append("%s: 측정 팔 없음" % filename)
    for index, (record, key) in enumerate(records):
        values = record.get(key)
        if not isinstance(values, list) or not values:
            problems.append("%s: 팔 %d 원자료 없음" % (filename, index))
        elif not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                     and math.isfinite(v) for v in values):
            problems.append("%s: 팔 %d 유한하지 않은 원자료" % (filename, index))
    if filename == "p17_adaptive_value.json":
        problems.extend(p17_trial_problems(d))
    if filename == "p18_mmax.json":
        problems.extend(p18_trial_problems(d))
    return problems


RULES = {
    "p3_effect.json": check_p3,
    "p14_dominance.json": check_p14,
    "p16_uplink.json": check_p16,
    "p11_adaptive.json": check_p11,
    "p15_v2policy.json": check_p15,
    "p17_adaptive_value.json": check_p17,
    "p18_mmax.json": check_p18,
}

HEADLINE = {
    "p11_adaptive.json": ["worst_regret_late_ms", "worst_ci95_half_ms"],
    "p15_v2policy.json": ["worst_regret_ms", "worst_ci95_half_ms"],
    "p14_dominance.json": [],
    "p3_effect.json": ["total_recovered"],
}


RESULT_STAGES = {name: name.split("_")[0] for name in RULES}
RESULT_STAGES["p7_verify.json"] = "p7"


def verify_recorded_result(stage, record, result_path):
    answer = {"stage": stage.id, "status": "unverifiable", "reason": "",
              "measurement_status": record.get("status") if isinstance(record, dict) else None}

    def fail(reason, mismatch=False):
        answer.update(status="mismatch" if mismatch else "unverifiable", reason=reason)
        return answer

    if not isinstance(record, dict) or record.get("status") not in ("done", "failed"):
        return fail("완료 또는 실패 실행 기록이 없다")
    provenance = record.get("provenance")
    published = record.get("result_provenance")
    if not isinstance(provenance, dict) or provenance.get("schema_version") != 1:
        return fail("당시 소스·환경 기록이 없다 (소급 보충하지 않음)")
    if not isinstance(published, dict) or published.get("schema_version") != 1:
        return fail("당시 산출물 생성 관측 기록이 없다")
    try:
        from loop2 import fingerprint_from_provenance
        current = stage.provenance()
        if provenance.get("runtime_context") != current["runtime_context"]:
            return fail("기록된 launcher 환경 또는 PADFEC 설정이 현재와 다름", True)
        if provenance != current:
            return fail("기록된 소스·명령·의존관계가 현재 단계와 다름", True)
        if any(value is None for value in provenance["source_hashes"].values()):
            return fail("지문에 필요한 소스 파일이 없다")
        if fingerprint_from_provenance(provenance) != record.get("fingerprint"):
            return fail("당시 출처 기록과 실행 지문이 서로 다름", True)
        if stage.fingerprint() != record["fingerprint"]:
            return fail("현재 단계 지문이 실행 당시와 다름", True)
        if published.get("source_consistent") is not True:
            return fail("실행 시작·종료 소스 또는 환경 일치가 확인되지 않음")
        rel = "experiments/results/" + os.path.basename(result_path)
        if rel not in stage.outputs:
            return fail("이 단계가 선언한 산출물이 아님", True)
        evidence = published["outputs"][rel]
        before, after = evidence.get("before"), evidence.get("after")
        started, finished = published["started_at_ns"], published["finished_at_ns"]
        if (not isinstance(started, int) or isinstance(started, bool)
                or not isinstance(finished, int) or isinstance(finished, bool)
                or not 0 < started <= finished):
            return fail("실행 시각 기록이 불완전함")
        if (evidence.get("written_during_run") is not True or not isinstance(after, dict)
                or before == after or published.get("observation_scope") !=
                "exclusive_writer_before_after_file_observation"):
            return fail("이 실행이 새 결과를 썼다는 근거가 없다")
        with open(result_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        if digest != after.get("sha256"):
            return fail("현재 원자료 SHA256이 실행 산출물과 다름", True)
        if record["status"] == "done" and record.get("output_hashes", {}).get(rel) != digest:
            return fail("완료 단계의 output_hashes와 산출물 관측이 서로 다름", True)
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        return fail("출처 기록을 검증할 수 없음: %s" % type(exc).__name__)
    answer.update(status="verified", reason="당시 기록과 현재 소스·launcher 환경·산출물 내용 일치",
                  sha256=digest, fingerprint=record["fingerprint"],
                  runtime_scope=provenance["runtime_scope"])
    return answer


def audit_content_provenance(results_dir, state_path):
    from loop2 import build_stages
    stages = {stage.id: stage for stage in build_stages()}
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
        records = state["stages"]
        if not isinstance(records, dict):
            raise ValueError("stages is not a mapping")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [{"file": name, "stage": sid, "status": "unverifiable",
                 "reason": "단계 상태 파일을 읽을 수 없음: %s" % type(exc).__name__}
                for name, sid in RESULT_STAGES.items()]
    return [dict(verify_recorded_result(stages[sid], records.get(sid),
                                       os.path.join(results_dir, name)), file=name)
            for name, sid in RESULT_STAGES.items()]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=RESULTS)
    parser.add_argument("--state-file", help="당시 loop2 상태 기록 (기본: 결과 폴더의 형제 state/loop2.json)")
    parser.add_argument("--output", help="감사 JSON을 별도 경로에 저장")
    args = parser.parse_args(argv)
    res = os.path.abspath(args.results_dir)
    out = {"tol": TOL, "items": 0, "mismatch": [], "no_raw": [],
           "stale": [], "mtime_warnings": [], "checks": [], "mismatch_count": 0,
           "trial_record_limits": [],
           "provenance_limit": "수치 재계산과 당시 실행 기록 대조. launcher 환경·PADFEC 설정 범위이며 WSL 내부 전체 환경이나 외부 오염을 인증하지 않는다"}
    checks = out["checks"]

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print("[%s] %-58s %s" % ("통과" if ok else "실패", name, detail),
              flush=True)

    print("=" * 100)
    print("P19 수치 출처 감사 — 보고된 수를 원자료에서 다시 계산해 대조")
    print("=" * 100)

    n_items = 0
    for fn, rule in sorted(RULES.items()):
        p = os.path.join(res, fn)
        if not os.path.exists(p):
            out["no_raw"].append("%s (파일 없음)" % fn)
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        out["trial_record_limits"].extend(trial_record_limits(d, fn))
        raw_problems = missing_raw(d, fn)
        out["no_raw"].extend(raw_problems)
        if any("유한하지 않은" in problem for problem in raw_problems):
            continue
        pairs = rule(d)
        bad = 0
        for name, got, want in pairs:
            n_items += 1
            if not close(got, want):
                bad += 1
                out["mismatch_count"] += 1
                if len(out["mismatch"]) < 20:
                    out["mismatch"].append(
                        {"file": fn, "field": name,
                         "reported": got, "recomputed": want})
        print("  %-26s 대조 %4d 항목, 불일치 %d" % (fn, len(pairs), bad))
    out["items"] = n_items

    src = []
    for pat in ("padfec/*.py", "afec/*.py", "experiments/*.py", "experiments/quicbed/*.go"):
        src += glob.glob(os.path.join(ROOT, pat))
    newest_src = max((os.path.getmtime(s) for s in src), default=0)
    for fn in RULES:
        p = os.path.join(res, fn)
        if os.path.exists(p) and os.path.getmtime(p) < newest_src:
            out["mtime_warnings"].append(fn)
    state_path = os.path.abspath(args.state_file or os.path.join(
        os.path.dirname(res), "state", "loop2.json"))
    out["state_file"] = state_path
    out["content_provenance"] = audit_content_provenance(res, state_path)
    out["stale"] = [r["file"] for r in out["content_provenance"] if r["status"] != "verified"]

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
        "불일치 %d 건%s" % (out["mismatch_count"],
                          (" 예: %s" % out["mismatch"][0]) if out["mismatch"] else ""))
    add("3. 당시 소스·launcher 환경·산출물 내용 출처를 확인했다",
        not out["stale"],
        "출처 불일치 또는 확인불가 %s" % (out["stale"] or "없음"))
    add("4. 판정 헤드라인과 각 측정 팔의 원자료가 실제로 있다", not out["no_raw"],
        "빠진 것 %s" % (out["no_raw"][:3] or "없음"))

    try:
        from padfec import policy as POL
        p7p = os.path.join(res, "p7_verify.json")
        with open(p7p, encoding="utf-8") as f:
            d7 = json.load(f)
        byname = {(c.get("case") or "").split(" ")[0]: c for c in d7["cases"]}
        base = byname["V1"]["p50"]
        rtt7 = float(d7.get("rtt_ms") or 50.0)
        meas = {"V2": byname["V2"]["p50"] - base,
                "V3": byname["V3"]["p50"] - base,
                "V9": byname["V9"]["p50"] - base}
        model = {"V2": POL.default_t_recover(rtt7, True),
                 "V3": POL.pto_with_rtt_sample_ms(rtt7),
                 "V9": POL.default_t_recover(rtt7, False)}
        worst = max(abs(model[k] - meas[k]) for k in meas)
        add("5. 모형 T_recover 상수가 p7 원자료(이름으로 찾음)를 10 ms 안에서 재현",
            worst < 10.0,
            " | ".join("%s 모형 %.1f vs 실측 %.1f" % (k, model[k], meas[k])
                       for k in ("V2", "V3", "V9")) + " (최대 %.2f ms)" % worst)
        out["t_recover_vs_p7"] = {"measured": meas, "model": model,
                                  "worst_abs_ms": worst, "rtt_ms": rtt7}
    except (OSError, KeyError, ValueError) as e:
        add("5. 모형 T_recover 상수가 p7 원자료(이름으로 찾음)를 10 ms 안에서 재현",
            False, "p7_verify.json 을 못 읽었다: %r" % (e,))

    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(checks)))
    if args.output:
        saved = save_result(os.path.abspath(args.output), out)
    else:
        saved = save_result(os.path.join(RESULTS, "p19_provenance.json"), out)
    print("saved: %s" % saved)
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
