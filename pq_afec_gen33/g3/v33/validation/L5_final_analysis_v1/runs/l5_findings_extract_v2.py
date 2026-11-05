import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))

def assess(report, scenario_ids):
    if report.get("status") != "complete" or report.get("missing") or report.get("missing_raw_groups"):
        raise ValueError("complete report required")
    expected = {(mode, sid) for mode in ("none", "c1") for sid in scenario_ids}
    rows = [row for row in report["comparisons"] if row["candidate"]["generation"] in ("l5_none", "l5_c1")
        and row["baseline"]["generation"] == "l1_" + row["candidate"]["generation"].removeprefix("l5_")]
    identities = [(r["candidate"]["generation"].removeprefix("l5_"), r["scenario"]) for r in rows]
    if len(identities) != len(expected) or set(identities) != expected or not all(row["primary"] for row in rows):
        raise ValueError("all original none/c1 comparisons must appear exactly once")
    counts = dict(collections.Counter(r["regression_gate"]["status"] for r in rows))
    if set(counts) - {"pass", "fail", "inconclusive"}:
        raise ValueError("unknown gate status")
    noninferior = all(r["regression_gate"]["status"] == "pass" for r in rows)
    improved = [r for r in rows if r["candidate"]["generation"] == "l5_c1" and r["upper_bound_ms"] is not None and r["upper_bound_ms"] < 0]
    required_groups = {(mode, family) for mode in ("none", "c1") for family in ("B5", "B6")}
    found = {}
    for group in report.get("groups", []):
        key = group["generation"].removeprefix("l5_"), group["scenario"]
        if key in required_groups:
            if key in found:
                raise ValueError("duplicate B5/B6 group")
            gate = "adaptation" if key[1] == "B5" else "mixture_fixed_regret"
            status = group["gates"][gate]["status"]
            if status not in ("pass", "fail", "inconclusive"):
                raise ValueError("unknown specific gate status")
            found[key] = status
    if set(found) != required_groups:
        raise ValueError("all none/c1 B5/B6 gates required")
    historical = report.get("historical_new_methods_gate")
    if historical not in ("pass", "blocked_missing_inputs", "fail"):
        raise ValueError("historical new-method gate required")
    specific = all(status == "pass" for status in found.values())
    adopt = noninferior and specific and historical == "pass"
    reasons = []
    if not noninferior:
        reasons.append("primary noninferiority failed or inconclusive")
    if not specific:
        reasons.append("B5 adaptation or B6 mixture gate failed or inconclusive")
    if historical != "pass":
        reasons.append("historical new-method validation: " + historical)
    return {"candidate_adopted": adopt, "primary_counts": counts, "primary_comparison_count": len(rows),
        "all_none_c1_pass": noninferior, "c1_improvement_scenarios": [r["scenario"] for r in improved],
        "reason": "; ".join(reasons) if reasons else "all predeclared primary, B5/B6 and historical gates pass",
        "historical_gate": historical, "specific_gates": {mode + ":" + family: status for (mode, family), status in found.items()},
        "primary_rows": [{"mode": r["candidate"]["generation"].removeprefix("l5_"), "scenario": r["scenario"],
            "mean_delta_ms": r["seed_summary"]["mean"], "seed_lower_ms": r["seed_summary"]["lower"], "seed_upper_ms": r["seed_summary"]["upper"],
            "shared_mc_bound_ms": r["shared_mc_bound_ms"], "adjusted_lower_ms": r["lower_bound_ms"], "adjusted_upper_ms": r["upper_bound_ms"],
            "gate": r["regression_gate"]["status"]} for r in rows]}

def main():
    check_path = RUNS / "L5_joint_artifact_check_v3.json"
    check = read(check_path)
    assert check["status"] == "pass"
    report_path = ROOT / "g3/v33/L5_benchmark_v1.json"
    assert sha(report_path) == check["files_sha256"][str(report_path)]
    family = read(RUNS / "L5_joint_action_family_v1.json")
    protocol = read(family["protocol_path"])
    report = read(report_path)
    result = assess(report, [s["id"] for s in protocol["scenarios"]])
    result.update(schema="padfec.v33.l5_findings/1", report_sha256=sha(report_path), checker_sha256=sha(check_path),
        script_sha256=sha(__file__), all_comparison_counts=dict(collections.Counter(r["regression_gate"]["status"] for r in report["comparisons"])),
        absolute_c1={r["scenario"]: {"expected_regret": r["expected_regret"], "gates": r["gates"]} for r in report["groups"]
            if r["generation"] == "l5_c1" and r["scenario"] in ("B1", "B2", "B5", "B6")},
        response_fixture_sha256=sha(RUNS / "L5_response_fixture_check_v4.json"),
        adaptation_fixture_sha256=sha(RUNS / "L5_adaptation_fixture_check_v4.json"),
        scope="Development only. Original 30 noninferiority cells and none/c1 B5/B6 gates plus historical new-method validation. Single is diagnostic only; no substitution or new samples.")
    with (RUNS / "L5_findings_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    groups = {(r["generation"], r["scenario"]):r for r in report["groups"]}
    lines = ["# L5 전체 개발 평가", "", f"채택 판정: {result['candidate_adopted']}. 전체30셀 판정: {result['primary_counts']}.", "",
        "| 모드 | 조건 | L1 평균 후회 ms | L5 평균 후회 ms | 직접 차이 ms | seed95% 구간 ms | 공유 MC ms | 조정 구간 ms | 비열등 |",
        "|---|---|---:|---:|---:|---|---:|---|---|"]
    fmt = lambda v: "미정의" if v is None else f"{v:.6f}"
    for row in result["primary_rows"]:
        mode, sid = row["mode"], row["scenario"]
        old = groups["l1_" + mode, sid]["expected_regret"]["seed_summary"]["mean"]
        new = groups["l5_" + mode, sid]["expected_regret"]["seed_summary"]["mean"]
        lines.append(f"| {mode} | {sid} | {fmt(old)} | {fmt(new)} | {fmt(row['mean_delta_ms'])} | [{fmt(row['seed_lower_ms'])}, {fmt(row['seed_upper_ms'])}] | {fmt(row['shared_mc_bound_ms'])} | [{fmt(row['adjusted_lower_ms'])}, {fmt(row['adjusted_upper_ms'])}] | {row['gate']} |")
    lines += ["", "세부 관문: " + str(result["specific_gates"]) + ". 역사 관문: " + result["historical_gate"] + ".", "비열등은 각 셀의 조정 상한0.5 ms 이하를 요구한다. 채택에는 none·C1의 B5 적응·B6 혼합 관문과 두 새 산출법의 역사 관문도 필요하다. 바이트·B1/B2 절대후회와 과거 세대·진단 판 대조는 전체 원본 보고서에 보존한다.",
        "실제 네트워크 측정이나 확증 결과가 아니다. C1 회신 비용은 D14의 수동 관측 근사에 따라 세계 비용에 포함되지 않는다.", ""]
    with (RUNS / "L5_bench.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    print(json.dumps({k:result[k] for k in ("candidate_adopted", "primary_counts", "c1_improvement_scenarios", "reason", "all_comparison_counts")}))

if __name__ == "__main__":
    main()
