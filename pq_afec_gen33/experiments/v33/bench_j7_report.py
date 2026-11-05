import sys
sys.dont_write_bytecode = True
import argparse
import collections
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_j7_family as family, bench_report, bench_learning_report as legacy
from experiments.v33.bench_metrics import paired_summary

PATH = Path(__file__).resolve()
IMPORTED_SHA = bench.file_hash(PATH)
SCHEMA = "padfec.v33.j7_factorial_report/1"


def inventory(runs, plan):
    groups = collections.defaultdict(list)
    expected = {(profile, role, mode, scenario["id"], seed)
                for profile, protocol in plan["protocols"].items() for role in plan["policies"]
                for mode in plan["modes"] for scenario in protocol["scenarios"] for seed in protocol["seeds"]}
    seen = set()
    for run in runs:
        key = run["profile"], run["role"], run["observation_mode"], run["scenario"], run["seed"]
        if key not in expected or key in seen:
            raise ValueError("unplanned or duplicate factorial run")
        seen.add(key)
        bench_report.weights(run)
        groups[key[:-1]].append(run)
    family.equal(seen, expected, "report complete factorial")
    for group in groups.values():
        group.sort(key=lambda r: r["seed"])
    return groups


def cross_profile(candidate, baseline, tables, confidence):
    ca, ba = ({run["seed"]: run for run in runs} for runs in (candidate, baseline))
    if set(ca) != set(ba):
        raise ValueError("cross-profile seed inventory differs")
    estimates, realized = [], []
    for seed in sorted(ca):
        values = []
        for run in (ca[seed], ba[seed]):
            values.append(math.fsum(float(w) * bench_report.finite(tables[key]["mean_hct_ms"], "absolute MC mean")
                                    for key, w in bench_report.weights(run).items()))
        estimates.append({"seed": seed, "mean_delta_ms": values[0] - values[1]})
        realized.append(ca[seed]["summary"]["mean_hct_ms"] - ba[seed]["summary"]["mean_hct_ms"])
    return {"expected_cost_point_ms": paired_summary([r["mean_delta_ms"] for r in estimates], confidence)["mean"],
            "seed_estimates": estimates, "realized_hct_diagnostic": paired_summary(realized, confidence),
            "shared_mc_bound_ms": None, "oracle_cancels": False, "used_for_adoption": False,
            "scope": "different fixed world profiles; expected point decomposition only, no joint MC interval or optimum claim"}


def decision(comparisons, plan):
    rules = plan["report_rules"]
    primary = [r for r in comparisons if r["primary"]]
    expected = {(p, m, s["id"]) for p in rules["primary_profiles"] for m in rules["primary_modes"]
                for s in plan["protocols"][p]["scenarios"]}
    keys = [(r["profile"], r["mode"], r["scenario"]) for r in primary]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("primary cell inventory differs")
    statuses = [r["regression_gate"]["status"] for r in primary]
    noninferiority = bench_report._all_status(statuses)
    improvements = [r for r in primary if r["mode"] == "c1" and r["upper_bound_ms"] is not None and r["upper_bound_ms"] < 0]
    return {"status": "pass" if noninferiority == "pass" and improvements else
                       "fail" if noninferiority == "fail" else "inconclusive",
            "noninferiority": noninferiority, "counts": dict(collections.Counter(statuses)),
            "primary_cells": len(primary), "required_cells": len(expected),
            "c1_improvement_cells": [[r["profile"], r["scenario"]] for r in improvements],
            "improvement_satisfied": bool(improvements), "rules": rules,
            "wire_and_implementation_gates_separate": True}


def aggregate(runs, tables, plan):
    groups = inventory(runs, plan)
    confidence = plan["report_rules"]["seed_confidence"]
    comparisons = []
    for profile, protocol in plan["protocols"].items():
        for mode in plan["modes"]:
            for scenario in protocol["scenarios"]:
                sid = scenario["id"]
                value = bench_report.direct_comparison(groups[profile, "j7", mode, sid], groups[profile, "l1", mode, sid], tables, confidence)
                if value["missing"]:
                    raise ValueError("expected cost comparison has missing actions")
                value.update(profile=profile, mode=mode, scenario=sid,
                             primary=profile in plan["report_rules"]["primary_profiles"] and mode in plan["report_rules"]["primary_modes"])
                value["regression_gate"] = bench_report.threshold_from_summary(value["seed_summary"],
                    plan["report_rules"]["noninferiority_ms"], mc_bound=value["shared_mc_bound_ms"], inclusive=True)
                comparisons.append(value)
    diagnostics = []
    fields = ("mean_hct_ms", "failure_rate", "mean_extra_server_bytes", "mean_extra_first_flight_bytes",
              "mean_extra_client_first_flight_bytes", "p_bias_high_phase", "p_mae_high_phase", "alarm_rate_per_1000")
    for key, group in sorted(groups.items()):
        observed = {}
        for field in fields:
            present = [run["summary"][field] for run in group if run["summary"].get(field) is not None]
            observed[field] = paired_summary(present, confidence)
            observed[field]["expected_seed_count"] = len(group)
        diagnostics.append({"profile": key[0], "role": key[1], "mode": key[2], "scenario": key[3],
                            "observed": observed, "kind": "realized development diagnostics",
                            "observations": legacy.merge_diagnostics([r["observation_diagnostics"] for r in group])})
    contribution = []
    for mode in plan["modes"]:
        for scenario in plan["protocols"]["wire39"]["scenarios"]:
            sid = scenario["id"]
            wire = {role: cross_profile(groups["wire46", role, mode, sid], groups["wire39", role, mode, sid], tables, confidence)
                    for role in plan["policies"]}
            endpoint = cross_profile(groups["wire46", "j7", mode, sid], groups["wire39", "l1", mode, sid], tables, confidence)
            policy = {p: next(r for r in comparisons if (r["profile"], r["mode"], r["scenario"]) == (p, mode, sid))
                      for p in plan["protocols"]}
            p39, p46 = (policy[p]["seed_summary"]["mean"] for p in ("wire39", "wire46"))
            residual = endpoint["expected_cost_point_ms"] - p46 - wire["l1"]["expected_cost_point_ms"]
            residual2 = endpoint["expected_cost_point_ms"] - p39 - wire["j7"]["expected_cost_point_ms"]
            if max(abs(residual), abs(residual2)) > 1e-9:
                raise ValueError("factorial expected cost decomposition differs")
            contribution.append({"mode": mode, "scenario": sid, "wire_effect_by_policy": wire,
                                 "combined_endpoint": endpoint, "policy_effect_wire39_ms": p39,
                                 "policy_effect_wire46_ms": p46, "interaction_point_ms": p46 - p39,
                                 "decomposition_max_residual_ms": max(abs(residual), abs(residual2))})
    return {"schema": SCHEMA, "status": "complete", "data_kind": plan["data_kind"],
            "physical_measurement": False, "comparisons": comparisons, "groups": diagnostics,
            "factorial_contributions": contribution, "performance_decision": decision(comparisons, plan),
            "limitations": ["MC intervals use the frozen normal approximation and are not distribution-free guarantees.",
                            "Cross-profile expected costs are descriptive point decompositions; no joint MC interval is claimed.",
                            "The fixed reference action is not asserted optimal in wire46.",
                            "Ideal observations are privileged diagnostics and do not substitute for C1."]}


def markdown(report):
    verdict = report["performance_decision"]
    lines = ["# J7 개발 기대 비용 평가", "", f"전체 판정: {verdict['status']}. 비열등: {verdict['noninferiority']}. "
             f"주 비교 {verdict['primary_cells']}셀, C1 감소 {len(verdict['c1_improvement_cells'])}셀.", "",
             "같은 세계에서 J7 기대 비용에서 L1을 뺐다. 음수는 J7이 빠르다는 뜻이다. 구간은 seed 단위 95% 구간과 공통 MC 오차를 합쳤다. 단위는 ms/연결이다.", "",
             "| 세계 | 관측 | 시나리오 | 차이 | 보정 하한 | 보정 상한 | 판정 |", "|---|---|---|---:|---:|---:|---|"]
    def num(v):
        return "미확정" if v is None else f"{v:.6f}"
    for row in report["comparisons"]:
        if row["primary"]:
            lines.append(f"| {row['profile']} | {row['mode']} | {row['scenario']} | {num(row['seed_summary']['mean'])} | {num(row['lower_bound_ms'])} | {num(row['upper_bound_ms'])} | {row['regression_gate']['status']} |")
    lines += ["", "두 세계 사이의 와이어 효과와 결합 끝점은 JSON의 factorial_contributions에 별도로 보존했다. 기대 비용 점추정의 분해이며, 그 차이의 공통 MC 구간은 계산하지 않았다. 채택 판정에 쓰지 않는다.",
              "", "실현 HCT·바이트·p 편향과 전체 관측 분모는 groups에 기록했다. 새 세계의 최적 후회나 실제 네트워크 성능을 뜻하지 않는다.",
              "", "전체 Go 관문과 와이어 시험의 통과 여부는 성능 판정과 별도로 확인한다.", ""]
    return "\n".join(lines)


def final_report(family_path, sha, pool_dir, out, markdown_path):
    outputs = [Path(p).resolve() for p in (out, markdown_path)]
    marker = Path(str(outputs[0]) + ".published.json")
    if len(set(outputs + [marker])) != 3 or any(p.exists() for p in outputs + [marker]):
        raise ValueError("report outputs must be distinct new paths")
    saved, metadata, runs = family.execution_plan(family_path, sha)
    plan = family.collector.load_plan(saved["collection_plan_path"])
    with family.pool.exclusive_lock(Path(pool_dir) / "pool.lock"):
        tables, attestation = legacy.validate_pool_locked(pool_dir, saved["manifest"], metadata)
        report = aggregate(runs, tables, plan)
        report["provenance"] = {"family_path": str(Path(family_path).resolve()), "family_sha256": sha,
                                "collection_plan_sha256": family.PLAN_SHA, "reporter_sha256": IMPORTED_SHA,
                                "family_size": saved["manifest"]["evaluation_family_size"],
                                "run_count": saved["run_count"], "connections": saved["connections"],
                                "pool_attestation": attestation, "validated_sha256": saved["validated_sha256"]}
        family.equal(bench.file_hash(PATH), IMPORTED_SHA, "loaded reporter")
        legacy.check_files(saved["inputs_sha256"])
        legacy.check_files(attestation["files_sha256"])
        bench.write_new(outputs[0], report)
        with outputs[1].open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown(report))
        bench.write_new(marker, {"status": "complete", "schema": SCHEMA, "artifacts_sha256": family.hashes(outputs),
                                 "family_sha256": sha, "reporter_sha256": IMPORTED_SHA,
                                 "pool_attestation_sha256": bench.digest(attestation)})
    return {"status": "complete", "performance_decision": report["performance_decision"], "sha256": bench.file_hash(out)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(final_report(args.family, args.sha256, args.pool, args.out, args.markdown), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
