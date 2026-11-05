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
REPORT = ROOT / "g3/v33/L2_benchmark_v1.json"
CHECKER = RUNS / "l2_joint_artifact_check_v3.py"
CHECK = RUNS / "L2_joint_artifact_check_v3.json"
OUTPUT = RUNS / "L2_findings_v3.json"
MARKDOWN = RUNS / "L2_findings_v3.md"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))


def extract(report):
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
    pair_summaries = {}
    for name, values in pairs.items():
        counts = collections.Counter(row["gate"] for row in values)
        pair_summaries[name] = {"primary": values[0]["primary"], "cells": len(values),
            "pass": counts["pass"], "fail": counts["fail"], "inconclusive": counts["inconclusive"],
            "known_upper_max_ms": max((row["adjusted_upper_ms"] for row in values if row["adjusted_upper_ms"] is not None), default=None),
            "null_upper_cells": [row["scenario"] for row in values if row["adjusted_upper_ms"] is None],
            "fail_cells": [row["scenario"] for row in values if row["gate"] == "fail"],
            "inconclusive_cells": [row["scenario"] for row in values if row["gate"] == "inconclusive"],
            "cost_reduction_with_adjusted_upper_below_zero": [row["scenario"] for row in values if row["adjusted_upper_ms"] is not None and row["adjusted_upper_ms"] < 0]}
    primary = [row for row in cells if row["primary"]]
    adoption = [row for row in primary if (row["candidate"], row["baseline"]) in (("l2_none", "l1_none"), ("l2_c1", "l1_c1"))]
    improved = [row for row in adoption if row["adjusted_upper_ms"] is not None and row["adjusted_upper_ms"] < 0]
    groups = []
    for row in report["groups"]:
        expected, observed, eps = row["expected_regret"], row["observed"], row["epsilon_diagnostics"]
        groups.append({"generation": row["generation"], "scenario": row["scenario"], "family": row["family"],
            "expected_regret_ms": expected["seed_summary"]["mean"], "regret_adjusted_lower_ms": expected["lower_bound_ms"],
            "regret_adjusted_upper_ms": expected["upper_bound_ms"], "gates": row["gates"],
            "p_bias": observed["p_bias_high_phase"], "p_convergence": row["p_convergence"],
            "extra_server_bytes": observed["mean_extra_server_bytes"], "epsilon": None if eps is None else
                {key: eps[key] for key in ("connections", "eligible", "skipped", "failed_eligible", "above_two_thirds", "reasons", "final_mean_seed_summary", "tail_mean_seed_summary", "meaning")}})
    return {"schema": "padfec.v33.l2_findings/1", "data_kind": report["data_kind"], "group_count": len(groups),
            "comparison_count": len(cells), "primary_cell_count": len(primary), "pair_summaries": dict(sorted(pair_summaries.items())),
            "comparisons": cells, "groups": groups, "primary_all_pass": len(primary) == 60 and all(row["gate"] == "pass" for row in primary),
            "adoption_cell_count": len(adoption), "before_after_all_pass": len(adoption) == 30 and all(row["gate"] == "pass" for row in adoption),
            "before_after_reduction_cells": [{key: row[key] for key in ("candidate", "baseline", "scenario", "mean_ms", "adjusted_upper_ms")} for row in improved],
            "candidate_eligible_for_adoption": len(adoption) == 30 and all(row["gate"] == "pass" for row in adoption) and bool(improved),
            "scope": "Original precollection plan: all30 none/C1 L2-vs-L1 cells must pass, with an adjusted upper<0 cost reduction. C1-v31/v32 primary reporting remains separate and every result is retained. Fixed EPS and ideal remain diagnostic. Physical network and true false-label rate are unverified."}


def prose(result):
    number = lambda value: "미확정" if value is None else f"{value:.6f}"
    lines = ["# L2 개발 평가 수치", "", "독립 사건 세계의 개발 평가다. 기대 차이는 후보 비용에서 기준 비용을 뺀 값이며 단위는 ms/연결이다.",
             "seed 95% 구간과 공통 MC 오차를 함께 적는다. 조정 경계의 전체 동시95% 보장을 주장하지 않는다.", "",
             f"전체 {result['group_count']}그룹, {result['comparison_count']}대조, 주 비교 {result['primary_cell_count']}셀.", "",
             "| 대조 | 주 비교 | pass | fail | 미확정 | 알려진 조정 상한 최대 ms |", "|---|---|---:|---:|---:|---:|"]
    for name, row in result["pair_summaries"].items():
        lines.append(f"| {name} | {row['primary']} | {row['pass']} | {row['fail']} | {row['inconclusive']} | {number(row['known_upper_max_ms'])} |")
    lines += ["", "## 셀별 직접 차이", "", "| 후보 | 기준 | 셀 | 평균 ms | seed 95% 구간 ms | MC 폭 ms | 조정 경계 ms | 판정 |", "|---|---|---|---:|---|---:|---|---|"]
    for row in result["comparisons"]:
        lines.append(f"| {row['candidate']} | {row['baseline']} | {row['scenario']} | {number(row['mean_ms'])} | [{number(row['seed_95_lower_ms'])}, {number(row['seed_95_upper_ms'])}] | {number(row['shared_mc_bound_ms'])} | [{number(row['adjusted_lower_ms'])}, {number(row['adjusted_upper_ms'])}] | {row['gate']} |")
    lines += ["", "## L2의 절대 비용과 EPS", "", "EPS는 근사 모형의 유효 잡음 매개변수이며 실제 잘못된 라벨의 비율을 식별한 값이 아니다.", "",
              "| 정책 | 셀 | 기대 후회 ms | 조정 경계 ms | 후회 판정 | 마지막200 EPS seed 평균 | 갱신 대상/전체 | 실패 갱신 |", "|---|---|---:|---|---|---:|---:|---:|"]
    for row in result["groups"]:
        if not row["generation"].startswith("l2_"):
            continue
        eps = row["epsilon"]
        lines.append(f"| {row['generation']} | {row['scenario']} | {number(row['expected_regret_ms'])} | [{number(row['regret_adjusted_lower_ms'])}, {number(row['regret_adjusted_upper_ms'])}] | {row['gates'].get('regret', {}).get('status', '해당 없음')} | {number(eps['tail_mean_seed_summary']['mean'])} | {eps['eligible']}/{eps['connections']} | {eps['failed_eligible']} |")
    lines += ["", f"보고용 주 비교60셀 통과: {result['primary_all_pass']}. 사전 계획의 L1 대비 채택 비교30셀 통과: {result['before_after_all_pass']}.",
              f"L1 대비 조정 상한<0인 채택 비교 셀: {len(result['before_after_reduction_cells'])}개.",
              f"사전 비교 기준에 따른 채택 가능 상태: {result['candidate_eligible_for_adoption']}. 실제 채택·복원은 별도 작업 기록에 남긴다.", ""]
    return "\n".join(lines)


def main():
    check = read(CHECK)
    assert check["status"] == "pass" and check["script_sha256"] == sha(CHECKER)
    assert check["files_sha256"][str(REPORT)] == sha(REPORT)
    assert check["summary"]["groups"] == 150 and check["summary"]["comparisons"] == 210
    assert check["summary"]["raw_runs"] == 3000
    assert not OUTPUT.exists() and not MARKDOWN.exists()
    report = read(REPORT)
    result = extract(report)
    result.update(recorded_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
        provenance={"report_path": str(REPORT), "report_sha256": sha(REPORT), "check_path": str(CHECK),
                    "check_sha256": sha(CHECK), "extractor_sha256": sha(__file__)})
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with MARKDOWN.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(prose(result))
    assert check["files_sha256"][str(REPORT)] == sha(REPORT)
    print(json.dumps({key: result[key] for key in ("pair_summaries", "primary_all_pass", "before_after_all_pass", "before_after_reduction_cells", "candidate_eligible_for_adoption")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
