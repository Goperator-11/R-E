import sys
sys.dont_write_bytecode = True
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
source = (ROOT / "experiments/v33/bench_learning_l2_report.py").read_text(encoding="utf-8")
source = source.replace("L2", "L3").replace("l2", "l3")


def replace(old, new):
    global source
    assert old in source, old
    source = source.replace(old, new)


def section(start, end, text):
    global source
    first, last = source.index(start), source.index(end)
    source = source[:first] + text + "\n\n" + source[last:]


replace('"fixed": ("none", "c1")', '"guard": ("c1",), "record": ("c1",), "beta": ("c1",)')
section('PAIRS += [("l3_" + mode, "fixed_"', 'FROZEN =', '''PAIRS += [("guard_c1", "l1_c1"), ("record_c1", "guard_c1"), ("beta_c1", "record_c1"), ("l3_c1", "beta_c1")]
PRIMARY = {("l3_c1", "l1_c1"), ("l3_none", "l1_none"), ("l3_c1", "v31")}''')
replace("42dbff55bc984c3d34d2e159c3d162b79376104bd73a9751db66a915a47dcf3e", "309c6cd7fb7959c667e6ea6c88c7db06c8e01dc33aef60c1bfbd179ec7c26ad4")
replace("14712a6836c2069cc8e695635ff90f4cc64f9aee829b5360d6ec54c46697fce0", "4e48e8d951fe1b9b6ce24babb1119775eb49d4e45bf2964be1d6152da31fb9c5")
replace("def analysis_runs(protocol, baseline, previous, candidate, fixed):", "def analysis_runs(protocol, baseline, previous, candidate, guard, record, beta):")
replace('"l3": candidate, "fixed": fixed', '"l3": candidate, "guard": guard, "record": record, "beta": beta')
replace('(("L3_v1", "l3", True), ("L3_fixed_epsilon_v1", "fixed", False))', '(("L3_v1", "l3", True), ("L3_guard_only_v1", "guard", False), ("L3_record_only_v1", "record", False), ("L3_beta_only_v1", "beta", False))')
replace('expected_mode = "adaptive" if role == "l3" else "fixed_ablation"\n        equal(provenance["overlay"]["policy"]["epsilon_calibration"], expected_mode, "calibration role")',
        'expected_mode = "full" if role == "l3" else role + "_only"\n        equal(provenance["overlay"]["policy"]["monitor_variant"], expected_mode, "monitor role")')
replace('loaded["l3"], loaded["fixed"]', 'loaded["l3"], loaded["guard"], loaded["record"], loaded["beta"]')
replace('"l3": len(loaded["l3"]), "fixed": len(loaded["fixed"])', '**{role: len(values) for role, values in loaded.items()}')
replace("Strict complete L1 and L3 loader validation plus exact fixed-control subset and all collection completion receipts", "Strict complete L1 and L3 loader validation plus exact C1 ablation inventories and all collection completion receipts")
section("def epsilon_diagnostics(rows):", "def aggregate(", '''def monitor_diagnostics(rows):
    counts = dict.fromkeys(("connections", "monitored", "skipped", "ready", "alarms", "up", "down", "action_model", "recovery", "shared_change", "failed_monitored", "reeval_suppressed", "nonzero_beta_decisions"), 0)
    reasons, actions = collections.Counter(), collections.Counter()
    beta = []
    for row in rows:
        info, decision = row["observation_info"], row["decision"]
        result = info["monitor"]
        counts["connections"] += 1
        counts["reeval_suppressed"] += int(decision["reeval_feedback_suppressed"])
        value = decision["monitor_prediction"]["beta"]
        beta.append(value)
        counts["nonzero_beta_decisions"] += int(value != 0)
        if result is None:
            counts["skipped"] += 1
            reasons[info["monitor_reason"]] += 1
            continue
        counts["monitored"] += 1
        counts["failed_monitored"] += int(not row["ok"])
        counts["ready"] += int(result["reactive"])
        counts["alarms"] += int(result["direction"] != 0)
        counts["up"] += int(result["direction"] == 1)
        counts["down"] += int(result["direction"] == -1)
        actions[result["action"]] += 1
        if result["action"] in ("action_model", "recovery", "shared_change"):
            counts[result["action"]] += 1
    return {**counts, "reasons": dict(sorted(reasons.items())), "actions": dict(sorted(actions.items())),
            "alarm_per_1000_all_decisions": 1000 * counts["alarms"] / counts["connections"],
            "alarm_per_1000_monitored": 1000 * counts["alarms"] / counts["monitored"] if counts["monitored"] else None,
            "mean_abs_beta_decision": sum(abs(value) for value in beta) / len(beta), "maximum_abs_beta_decision": max(map(abs, beta))}''')
replace('by_group, diagnostics, eps =', 'by_group, diagnostics, monitors =')
replace('if run["analysis_role"] in ("l3", "fixed"):\n            eps[key].append({"seed": run["seed"], **epsilon_diagnostics(rows)})',
        'if run["analysis_role"] in ("l3", "guard", "record", "beta"):\n            monitors[key].append({"seed": run["seed"], **monitor_diagnostics(rows)})')
section('        group["epsilon_diagnostics"] = None', '    comparisons, missing =', '''        group["monitor_diagnostics"] = None
        if key in monitors:
            values = monitors[key]
            count_fields = ("connections", "monitored", "skipped", "ready", "alarms", "up", "down", "action_model", "recovery", "shared_change", "failed_monitored", "reeval_suppressed", "nonzero_beta_decisions")
            counts = {field: sum(row[field] for row in values) for field in count_fields}
            merged = {}
            for field in ("reasons", "actions"):
                tally = collections.Counter()
                for row in values:
                    tally.update(row[field])
                merged[field] = dict(sorted(tally.items()))
            group["monitor_diagnostics"] = {**counts, **merged,
                "all_decision_alarm_seed_summary": paired_summary([row["alarm_per_1000_all_decisions"] for row in values], confidence),
                "monitored_alarm_seed_summary": paired_summary([row["alarm_per_1000_monitored"] for row in values if row["alarm_per_1000_monitored"] is not None], confidence),
                "mean_abs_beta_seed_summary": paired_summary([row["mean_abs_beta_decision"] for row in values], confidence),
                "by_seed": values, "meaning": "Predecision risk-adjusted episodes, with all decisions as the declared gate denominator; monitored denominator shown separately"}
            if group["family"] == "B1":
                group["gates"]["monitor_alarm"] = bench_report.threshold_from_summary(group["monitor_diagnostics"]["all_decision_alarm_seed_summary"], 1.0)''')
replace('kind = "epsilon_adaptation_contrast" if baseline.startswith("fixed_") else "boundary_timing_contrast" if candidate.startswith("fixed_") else "direct_previous_policy" if baseline.startswith("l1_") else "legacy_or_mode_contrast"',
        'kind = "ablation_step_contrast" if (candidate, baseline) in PAIRS[-4:] else "direct_previous_policy" if baseline.startswith("l1_") else "legacy_or_mode_contrast"')
replace("Predeclared L3 development comparison after L1 results; fixed epsilon is a diagnostic control, not another candidate selected from outcomes.",
        "Predeclared L3 development comparison after L1; three diagnostic C1 arms isolate penalty removal, reevaluation removal, action correction and common-change response. Diagnostic arms are not replacement candidates.")
section("def markdown(report):", "def final_report(", '''def markdown(report):
    text = bench_report.markdown(report).replace("# W1 벤치 보고서", "# L3 공동 행동 평가 보고서", 1)
    lines = [text, "", "## 감시 진단", "", "경보는 결정 전에 저장한 예측에서 계산한다. 관문 분모는 모든 결정이며 감시 대상만의 비율도 별도 보존한다.", "",
             "| 정책 | 셀 | 연결 | 감시 | 건너뜀 | 경보 | 행동 보정 | 회복 | 공통 변화 | 1000결정당 경보 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for group in report["groups"]:
        value = group["monitor_diagnostics"]
        if value is not None:
            lines.append(f"| {group['generation']} | {group['scenario']} | {value['connections']} | {value['monitored']} | {value['skipped']} | {value['alarms']} | {value['action_model']} | {value['recovery']} | {value['shared_change']} | {value['all_decision_alarm_seed_summary']['mean']:.6f} |")
    lines.extend(["", "guard 대 L1, record 대 guard, beta 대 record, 전체 L3 대 beta의 단계별 짝차이를 보존한다.",
                  "none·C1의 L1 대비와 C1의 v31 대비 전 셀 비열등을 요구한다. C1 B1·B2 절대 후회와 B1 경보 관문도 별도 요구한다.",
                  "ideal과 진단 팔은 후보로 사후 교체하지 않는다. 고정q 오류 주입은 이 폐루프 경보율과 별도 시험이다.", ""])
    return "\\n".join(lines)''')
with (ROOT / "experiments/v33/bench_learning_l3_report.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(source)
