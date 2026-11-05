import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
REPORT = ROOT / "g3/v33/L3_benchmark_v1.json"
CHECKER = RUNS / "l3_joint_artifact_check_v1.py"
CHECK = RUNS / "L3_joint_artifact_check_v1.json"
OPERATING = RUNS / "L3_monitor_operating_v2.json"
OUTPUT = RUNS / "L3_findings_v1.json"
MARKDOWN = RUNS / "L3_findings_v1.md"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))


def extract(report, operating):
    pairs = collections.defaultdict(list)
    cells = []
    for row in report["comparisons"]:
        candidate, baseline = row["candidate"]["generation"], row["baseline"]["generation"]
        cell = {"candidate": candidate, "baseline": baseline, "scenario": row["scenario"], "primary": row["primary"],
                "kind": row["kind"], "mean_ms": row["seed_summary"]["mean"],
                "seed_95_lower_ms": row["seed_summary"]["lower"], "seed_95_upper_ms": row["seed_summary"]["upper"],
                "shared_mc_bound_ms": row["shared_mc_bound_ms"], "adjusted_lower_ms": row["lower_bound_ms"],
                "adjusted_upper_ms": row["upper_bound_ms"], "gate": row["regression_gate"]["status"]}
        cells.append(cell)
        pairs[candidate + "_vs_" + baseline].append(cell)
    summaries = {}
    for name, values in pairs.items():
        counts = collections.Counter(row["gate"] for row in values)
        summaries[name] = {"primary": values[0]["primary"], "cells": len(values),
            "pass": counts["pass"], "fail": counts["fail"], "inconclusive": counts["inconclusive"],
            "known_upper_max_ms": max((row["adjusted_upper_ms"] for row in values if row["adjusted_upper_ms"] is not None), default=None),
            "null_upper_cells": [row["scenario"] for row in values if row["adjusted_upper_ms"] is None],
            "fail_cells": [row["scenario"] for row in values if row["gate"] == "fail"],
            "inconclusive_cells": [row["scenario"] for row in values if row["gate"] == "inconclusive"],
            "cost_reduction_with_adjusted_upper_below_zero": [row["scenario"] for row in values if row["adjusted_upper_ms"] is not None and row["adjusted_upper_ms"] < 0]}
    required_pairs = (("l3_none", "l1_none"), ("l3_c1", "l1_c1"), ("l3_c1", "v31"))
    primary = [row for row in cells if (row["candidate"], row["baseline"]) in required_pairs]
    before_after = [row for row in primary if row["baseline"].startswith("l1_")]
    improved = [row for row in before_after if row["adjusted_upper_ms"] is not None and row["adjusted_upper_ms"] < 0]
    groups = []
    for row in report["groups"]:
        expected, observed, monitor = row["expected_regret"], row["observed"], row["monitor_diagnostics"]
        groups.append({"generation": row["generation"], "scenario": row["scenario"], "family": row["family"],
            "expected_regret_ms": expected["seed_summary"]["mean"], "regret_adjusted_lower_ms": expected["lower_bound_ms"],
            "regret_adjusted_upper_ms": expected["upper_bound_ms"], "gates": row["gates"], "p_bias": observed["p_bias_high_phase"],
            "p_convergence": row["p_convergence"], "extra_server_bytes": observed["mean_extra_server_bytes"],
            "legacy_eligible_alarm_rate": observed["alarm_rate_per_1000"], "monitor": None if monitor is None else
                {key: value for key, value in monitor.items() if key != "by_seed"}})
    gate_details = {}
    for sid, gate in (("B1", "regret"), ("B2", "regret"), ("B1", "monitor_alarm")):
        matching = [row for row in groups if row["generation"] == "l3_c1" and row["scenario"] == sid]
        gate_details[sid + "_" + gate] = matching[0]["gates"].get(gate, {"status": "inconclusive"}) if len(matching) == 1 else {"status": "inconclusive"}
    injection = operating["injection"]
    injection_pass = (injection["replicates"] == 250 and injection["median_including_censor_as_infinity"] is not None
        and injection["median_including_censor_as_infinity"] <= 15 and injection["median_le_15"] is True)
    primary_pass = len(primary) == 45 and all(row["gate"] == "pass" for row in primary)
    gates_pass = all(value["status"] == "pass" for value in gate_details.values())
    return {"schema": "padfec.v33.l3_findings/1", "data_kind": report["data_kind"], "group_count": len(groups),
        "comparison_count": len(cells), "primary_cell_count": len(primary), "pair_summaries": dict(sorted(summaries.items())),
        "comparisons": cells, "groups": groups, "primary_all_pass": primary_pass, "before_after_cell_count": len(before_after),
        "before_after_all_pass": len(before_after) == 30 and all(row["gate"] == "pass" for row in before_after),
        "before_after_reduction_cells": [{key: row[key] for key in ("candidate", "baseline", "scenario", "mean_ms", "adjusted_upper_ms")} for row in improved],
        "absolute_and_alarm_gates": gate_details, "absolute_and_alarm_all_pass": gates_pass,
        "known_q_injection": {key: value for key, value in injection.items() if key != "raw"}, "known_q_injection_pass": injection_pass,
        "candidate_eligible_for_adoption": primary_pass and gates_pass and injection_pass and bool(improved),
        "scope": "Precollection plan: all45 noninferiority cells, C1 B1/B2 regret, B1 all-decision alarm rate, fixed-q injection median and at least one L1 cost reduction must pass. Ablations and ideal remain diagnostic. Physical wire and Go are unverified."}


def prose(result):
    number = lambda value: "미확정" if value is None else f"{value:.6f}"
    lines = ["# L3 개발 평가 수치", "", "독립 사건 세계의 개발 평가다. 기대 차이는 후보 비용에서 기준 비용을 뺀 값이며 단위는 ms/연결이다.",
        "seed 95% 구간과 공유 MC 오차를 함께 적는다. 조정 경계의 전체 동시95% 보장을 주장하지 않는다.", "",
        f"전체 {result['group_count']}그룹, {result['comparison_count']}대조, 채택 비교 {result['primary_cell_count']}셀.", "",
        "| 대조 | 채택 비교 | pass | fail | 미확정 | 알려진 조정 상한 최대 ms |", "|---|---|---:|---:|---:|---:|"]
    for name, row in result["pair_summaries"].items():
        lines.append(f"| {name} | {row['primary']} | {row['pass']} | {row['fail']} | {row['inconclusive']} | {number(row['known_upper_max_ms'])} |")
    lines += ["", "## 셀별 직접 차이", "", "| 후보 | 기준 | 셀 | 평균 ms | seed 95% 구간 ms | MC 폭 ms | 조정 경계 ms | 판정 |", "|---|---|---|---:|---|---:|---|---|"]
    for row in result["comparisons"]:
        lines.append(f"| {row['candidate']} | {row['baseline']} | {row['scenario']} | {number(row['mean_ms'])} | [{number(row['seed_95_lower_ms'])}, {number(row['seed_95_upper_ms'])}] | {number(row['shared_mc_bound_ms'])} | [{number(row['adjusted_lower_ms'])}, {number(row['adjusted_upper_ms'])}] | {row['gate']} |")
    lines += ["", "## 절대 비용과 감시", "", "경보 관문의 분모는 모든 결정이다. 현재 세계에서 정상 B1도 모형 불일치를 포함하므로 알려진 q의 Bernoulli 시험과 구분한다.", "",
        "| 정책 | 셀 | 기대 후회 ms | 조정 경계 ms | 후회 판정 | 1000결정당 경보 | 행동 보정 | 회복 | 공통 변화 |", "|---|---|---:|---|---|---:|---:|---:|---:|"]
    for row in result["groups"]:
        value = row["monitor"]
        if value is None:
            continue
        lines.append(f"| {row['generation']} | {row['scenario']} | {number(row['expected_regret_ms'])} | [{number(row['regret_adjusted_lower_ms'])}, {number(row['regret_adjusted_upper_ms'])}] | {row['gates'].get('regret', {}).get('status', '해당 없음')} | {number(value['all_decision_alarm_seed_summary']['mean'])} | {value['action_model']} | {value['recovery']} | {value['shared_change']} |")
    lines += ["", f"사전 비열등45셀 통과: {result['primary_all_pass']}. 절대 후회·경보 관문 통과: {result['absolute_and_alarm_all_pass']}.",
        f"고정q 오류 주입 중앙 지연: {result['known_q_injection']['median_including_censor_as_infinity']}결정. 해당 기준 통과: {result['known_q_injection_pass']}.",
        f"L1 대비 조정 상한<0인 셀: {len(result['before_after_reduction_cells'])}개. 사전 기준의 채택 가능 상태: {result['candidate_eligible_for_adoption']}.", ""]
    return "\n".join(lines)


def main():
    check = read(CHECK)
    assert check["status"] == "pass" and check["script_sha256"] == sha(CHECKER)
    assert check["files_sha256"][str(REPORT)] == sha(REPORT)
    assert (check["summary"]["groups"], check["summary"]["comparisons"], check["summary"]["raw_runs"]) == (165, 210, 3300)
    operating = read(OPERATING)
    assert operating["sources_unchanged"]
    assert all(sha(path) == expected for path, expected in operating["sources_sha256"].items())
    assert not OUTPUT.exists() and not MARKDOWN.exists()
    result = extract(read(REPORT), operating)
    result.update(recorded_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        provenance={"report_path": str(REPORT), "report_sha256": sha(REPORT), "check_path": str(CHECK),
            "check_sha256": sha(CHECK), "operating_path": str(OPERATING), "operating_sha256": sha(OPERATING), "extractor_sha256": sha(__file__)})
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with MARKDOWN.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(prose(result))
    assert check["files_sha256"][str(REPORT)] == sha(REPORT)
    print(json.dumps({key: result[key] for key in ("pair_summaries", "primary_all_pass", "absolute_and_alarm_gates", "known_q_injection_pass", "before_after_reduction_cells", "candidate_eligible_for_adoption")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
