import sys
sys.dont_write_bytecode = True
import argparse
import collections
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_action_pool as pool, bench_report
from experiments.v33 import bench_learning as previous_loader
from experiments.v33 import bench_learning_l3 as loader
from experiments.v33 import bench_learning_report as legacy
from experiments.v33.bench_metrics import paired_summary


PATH = Path(__file__).resolve()
IMPORTED_SHA256 = bench.file_hash(PATH)
PLAN_SCHEMA = "padfec.v33.l3_joint_action_family/1"
REPORT_SCHEMA = "padfec.v33.l3_joint_report/1"
ROLES = {"l1": ("none", "c1", "ideal"), "l3": ("none", "c1", "ideal"), "guard": ("c1",), "record": ("c1",), "beta": ("c1",)}
ALIASES = {role: {mode: role + "_" + mode for mode in modes} for role, modes in ROLES.items()}
PAIRS = [("l3_" + mode, generation) for mode in ROLES["l3"] for generation in ("v32", "v31")]
PAIRS += [("l3_c1", "l3_none")]
PAIRS += [("l3_" + mode, "l1_" + mode) for mode in ROLES["l3"]]
PAIRS += [("guard_c1", "l1_c1"), ("record_c1", "guard_c1"), ("beta_c1", "record_c1"), ("l3_c1", "beta_c1")]
PRIMARY = {("l3_c1", "l1_c1"), ("l3_none", "l1_none"), ("l3_c1", "v31")}

FROZEN = {"bench_learning.py": "412666987b56f46cdfe6cfa7970c1c6da5ff3eeed207037bae997ec4790d873f",
          "bench_learning_l3.py": "309c6cd7fb7959c667e6ea6c88c7db06c8e01dc33aef60c1bfbd179ec7c26ad4",
          "bench_learning_report.py": "9f480a41f456101e74461d2e8a3509625e3be148dda686eea752c1ce92a39c49"}
PREVIOUS_FAMILY_SHA256 = "e315280cf0199ab36a77f2f8a6d5289bf80dc00553aae4b0599610e2a5ff5e35"
COLLECTION_PLAN_SHA256 = "4e48e8d951fe1b9b6ce24babb1119775eb49d4e45bf2964be1d6152da31fb9c5"


def equal(actual, expected, label):
    legacy.equal(actual, expected, "L3 " + label)


def check_sources():
    equal(bench.file_hash(PATH), IMPORTED_SHA256, "loaded reporter")
    for name, expected in FROZEN.items():
        equal(bench.file_hash(PATH.with_name(name)), expected, "frozen " + name)
    legacy.check_reporter()


def merge_inputs(*inventories):
    output = {}
    for inventory in inventories:
        for path, expected in inventory.items():
            if path in output:
                equal(output[path], expected, "conflicting source")
            output[path] = expected
    return dict(sorted(output.items()))


def analysis_runs(protocol, baseline, previous, candidate, guard, record, beta):
    groups = {"baseline": baseline, "l1": previous, "l3": candidate, "guard": guard, "record": record, "beta": beta}
    names = ("v31", "v32", *(alias for role in ALIASES.values() for alias in role.values()))
    expected = {(name, "full", scenario["id"], seed) for name in names
                for scenario in protocol["scenarios"] for seed in protocol["seeds"]}
    seen, result = set(), []
    for role, raw_runs in groups.items():
        for raw in raw_runs:
            item = dict(raw)
            if role == "baseline":
                if raw["generation"] not in ("v31", "v32") or "observation_mode" in raw:
                    raise ValueError("unexpected historical baseline")
            else:
                mode = raw.get("observation_mode")
                if raw["generation"] != "current" or mode not in ROLES[role]:
                    raise ValueError("unexpected role or observation mode")
                item["generation"] = ALIASES[role][mode]
            identity = (item["generation"], item["variant"], item["scenario"], item["seed"])
            if identity not in expected or identity in seen or raw.get("mode") != "full":
                raise ValueError("duplicate, incomplete, or unplanned joint run")
            seen.add(identity)
            item["analysis_role"] = role
            result.append(item)
    equal(sorted(seen), sorted(expected), "complete joint run inventory")
    return sorted(result, key=lambda row: (row["generation"], row["variant"], row["scenario"], row["seed"]))


def collection_attestation(plan_path):
    plan_path = Path(plan_path).resolve(strict=True)
    equal(bench.file_hash(plan_path), COLLECTION_PLAN_SHA256, "frozen collection plan")
    plan = loader.read_json(plan_path)
    folder = plan_path.parent
    started_path, finished_path = folder / "L3_full_v1.started.json", folder / "L3_full_v1.finished.json"
    if not finished_path.is_file():
        raise ValueError("entire L3 collection must finish before analysis")
    started, finished = loader.read_json(started_path), loader.read_json(finished_path)
    equal(finished.get("status"), "complete", "complete collection")
    equal(finished.get("error"), None, "collection error")
    equal(finished["jobs"], finished["expected_jobs"], "collection job completeness")
    equal(finished["jobs"], len(plan["jobs"]), "collection planned jobs")
    equal(finished["plan_sha256"], bench.file_hash(plan_path), "collection plan binding")
    equal(started["plan_sha256"], bench.file_hash(plan_path), "collection start plan")
    equal(finished["started_receipt_sha256"], bench.file_hash(started_path), "collection start receipt")
    driver_path = folder / "l3_bench_driver_v1.py"
    equal(finished["driver_sha256"], plan["driver_sha256"], "collection driver")
    equal(started["driver_sha256"], plan["driver_sha256"], "collection starting driver")
    equal(bench.file_hash(driver_path), plan["driver_sha256"], "current frozen collection driver")
    inputs = {str(path): bench.file_hash(path) for path in (plan_path, started_path, finished_path, driver_path)}
    inputs = merge_inputs(inputs, plan["inputs_sha256"])
    expected_commands = {tuple(job["command"]): job for job in plan["jobs"]}
    if len(expected_commands) != len(plan["jobs"]):
        raise ValueError("duplicate collection command")
    seen = set()
    for receipt in finished["results"]:
        command = tuple(receipt["command"])
        if command not in expected_commands or command in seen:
            raise ValueError("unexpected collection receipt")
        seen.add(command)
        job = expected_commands[command]
        start_path = folder / (job["id"] + ".started.json")
        finish_path = folder / (job["id"] + ".finished.json")
        equal(loader.read_json(finish_path), receipt, "shard receipt copy")
        equal(receipt["status"], "complete", "complete shard")
        equal(receipt["exit_code"], 0, "shard exit")
        equal(receipt["error"], None, "shard launch error")
        equal(receipt["started_receipt_sha256"], bench.file_hash(start_path), "shard start receipt")
        start = loader.read_json(start_path)
        equal(start["command"], list(command), "shard started command")
        for field in ("driver_sha256", "driver_sha256_after"):
            equal(receipt[field], plan["driver_sha256"], "shard driver")
        equal(start["driver_sha256"], plan["driver_sha256"], "shard starting driver")
        equal(start["collector_sha256"], FROZEN["bench_learning_l3.py"], "shard starting collector")
        equal(receipt["collector_sha256"], FROZEN["bench_learning_l3.py"], "shard collector")
        equal(start["overlay_sha256"], bench.file_hash(job["overlay"]), "shard starting overlay")
        equal(receipt["overlay_sha256"], bench.file_hash(job["overlay"]), "shard overlay")
        for path in (start_path, finish_path):
            inputs[str(path)] = bench.file_hash(path)
        for kind in ("stdout", "stderr"):
            path = str(Path(receipt[kind + "_path"]).resolve(strict=True))
            equal(bench.file_hash(path), receipt[kind + "_sha256"], "shard log")
            inputs[path] = receipt[kind + "_sha256"]
    equal(sorted(seen), sorted(expected_commands), "entire shard receipt inventory")
    legacy.check_files(inputs)
    return plan, inputs


def prepare_plan(collection_plan, previous_family):
    check_sources()
    launch, launch_inputs = collection_attestation(collection_plan)
    previous_family = Path(previous_family).resolve(strict=True)
    equal(bench.file_hash(previous_family), PREVIOUS_FAMILY_SHA256, "frozen L1 family")
    old = loader.read_json(previous_family)
    rebuilt, old_loaded = legacy.prepare_plan(old["overlay_path"], old["raw_dirs"])
    equal(rebuilt, old, "L1 input family reconstruction")
    protocol, baseline, previous, references, old_provenance = old_loaded
    loaded, provenances = {}, {"l1": old_provenance}
    for name, role, complete in (("L3_v1", "l3", True), ("L3_guard_only_v1", "guard", False), ("L3_record_only_v1", "record", False), ("L3_beta_only_v1", "beta", False)):
        jobs = [job for job in launch["jobs"] if job["policy"] == name]
        overlays = {job["overlay"] for job in jobs}
        if len(overlays) != 1:
            raise ValueError("role must bind exactly one overlay")
        parts = loader.load_learning_runs(next(iter(overlays)), [job["out"] for job in jobs], require_complete=complete)
        new_protocol, new_baseline, current, new_references, provenance = parts
        equal(new_protocol, protocol, "same original W1 protocol")
        equal(new_baseline, baseline, "same historical baseline input")
        equal(new_references, references, "same frozen references")
        expected_mode = "full" if role == "l3" else role + "_only"
        equal(provenance["overlay"]["policy"]["monitor_variant"], expected_mode, "monitor role")
        loaded[role], provenances[role] = current, provenance
    runs = analysis_runs(protocol, baseline, previous, loaded["l3"], loaded["guard"], loaded["record"], loaded["beta"])
    protocol_path = Path(old["protocol_path"])
    equal(protocol["oracle"]["validation_samples"], 131072, "predeclared evaluation sample size")
    equal(protocol["oracle"]["validation_seed"], 850001, "predeclared evaluation seed")
    manifest = legacy.family_manifest(protocol, bench.file_hash(protocol_path), runs, references)
    additional = {str(previous_family): PREVIOUS_FAMILY_SHA256, str(PATH): IMPORTED_SHA256}
    additional.update({str(PATH.with_name(name)): expected for name, expected in FROZEN.items()})
    additional.update({str(PATH.with_name(name)): expected for name, expected in legacy.FROZEN_SOURCES.items()})
    inputs = merge_inputs(launch_inputs, additional, *(p["inputs_sha256"] for p in provenances.values()))
    legacy.check_files(inputs)
    plan = {"schema": PLAN_SCHEMA, "collection_plan_path": str(Path(collection_plan).resolve()),
            "collection_plan_sha256": bench.file_hash(collection_plan), "previous_family_path": str(previous_family),
            "previous_family_sha256": PREVIOUS_FAMILY_SHA256, "protocol_path": str(protocol_path),
            "protocol_sha256": bench.file_hash(protocol_path), "manifest": manifest,
            "contexts_sha256": bench.digest(bench.all_contexts(protocol)), "inputs_sha256": inputs,
            "planner_sha256": IMPORTED_SHA256, "loader_sha256": FROZEN["bench_learning_l3.py"],
            "raw_schema": "padfec.v33.l3_joint_raw_validation/1", "analysis_aliases": ALIASES,
            "comparisons": [list(pair) for pair in PAIRS], "primary_comparisons": [list(pair) for pair in sorted(PRIMARY)],
            "role_run_counts": {"baseline": len(baseline), "l1": len(previous), **{role: len(values) for role, values in loaded.items()}},
            "interval_reuse": "none; reevaluate the joint action union under one full family",
            "validation": "Strict complete L1 and L3 loader validation plus exact C1 ablation inventories and all collection completion receipts"}
    check_sources()
    return plan, (protocol, runs, references, provenances)


def execution_plan(family_path, family_sha256):
    family_path = Path(family_path).resolve(strict=True)
    equal(bench.file_hash(family_path), family_sha256, "family SHA")
    saved = loader.read_json(family_path)
    equal(saved.get("schema"), PLAN_SCHEMA, "family schema")
    rebuilt, loaded = prepare_plan(saved["collection_plan_path"], saved["previous_family_path"])
    equal(saved, rebuilt, "reconstructed joint family")
    manifest = saved["manifest"]
    metadata = {"schema": pool.SCHEMA, "adapter_sha256": legacy.FROZEN_SOURCES["bench_action_pool.py"],
                "manifest_sha256": bench.digest(manifest), "protocol_path": saved["protocol_path"],
                "protocol_sha256": saved["protocol_sha256"], "family_plan_path": str(family_path),
                "family_plan_sha256": family_sha256, "source_sha256": manifest["source_sha256"],
                "inputs_sha256": saved["inputs_sha256"], "contexts_sha256": saved["contexts_sha256"],
                "planner_sha256": saved["planner_sha256"], "loader_sha256": saved["loader_sha256"],
                "input_validation_schema": saved["raw_schema"], "input_validation": saved["validation"],
                "analysis_aliases": ALIASES}
    pool._check_sources(metadata)
    pool._check_inputs(metadata)
    return manifest, metadata, loaded


def monitor_diagnostics(rows):
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
            "mean_abs_beta_decision": sum(abs(value) for value in beta) / len(beta), "maximum_abs_beta_decision": max(map(abs, beta))}

def aggregate(protocol, runs, references, tables, trace_loader=bench_report.load_trace):
    by_group, diagnostics, monitors = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for run in runs:
        by_group[run["generation"], run["scenario"]].append(run)
    def load(run):
        rows = trace_loader(run)
        key = run["generation"], run["scenario"]
        if run["analysis_role"] != "baseline":
            diagnostics[key].append(legacy.observation_diagnostics(rows, run["observation_mode"]))
        if run["analysis_role"] in ("l3", "guard", "record", "beta"):
            monitors[key].append({"seed": run["seed"], **monitor_diagnostics(rows)})
        return rows
    report = bench_report.aggregate(runs, references, tables, protocol, trace_loader=load)
    report["schema"] = REPORT_SCHEMA
    scenarios = {scenario["id"]: scenario for scenario in protocol["scenarios"]}
    confidence = protocol["metrics"]["paired_confidence"]
    for group in report["groups"]:
        key = group["generation"], group["scenario"]
        raw = by_group[key][0]
        group["analysis_role"] = raw["analysis_role"]
        group["observation_mode"] = raw.get("observation_mode", "legacy_none")
        group["observation_diagnostics"] = legacy.merge_diagnostics(diagnostics[key]) if key in diagnostics else None
        group["p_convergence"] = legacy.convergence(group, by_group[key], scenarios[key[1]], protocol)
        group["monitor_diagnostics"] = None
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
                group["gates"]["monitor_alarm"] = bench_report.threshold_from_summary(group["monitor_diagnostics"]["all_decision_alarm_seed_summary"], 1.0)

    comparisons, missing = [], set(report["missing"])
    for candidate, baseline in PAIRS:
        for sid in scenarios:
            item = bench_report.direct_comparison(by_group[candidate, sid], by_group[baseline, sid], tables, confidence)
            missing.update(item["missing"])
            kind = "ablation_step_contrast" if (candidate, baseline) in PAIRS[-4:] else "direct_previous_policy" if baseline.startswith("l1_") else "legacy_or_mode_contrast"
            item.update(candidate={"generation": candidate, "variant": "full"}, baseline={"generation": baseline, "variant": "full"},
                        scenario=sid, kind=kind, primary=(candidate, baseline) in PRIMARY,
                        ideal_is_privileged_diagnostic=candidate.endswith("ideal") or baseline.endswith("ideal"))
            item["regression_gate"] = bench_report.threshold_from_summary(item["seed_summary"], protocol["thresholds"]["max_regression_vs_v31_ms"],
                                                                           mc_bound=item["shared_mc_bound_ms"], inclusive=True)
            comparisons.append(item)
    report["comparisons"] = comparisons
    report["missing"] = sorted(missing)
    report["status"] = "partial" if missing or report["missing_raw_groups"] else "complete"
    report["noninferiority"] = {}
    for candidate, baseline in PAIRS:
        cells = [row for row in comparisons if row["candidate"]["generation"] == candidate and row["baseline"]["generation"] == baseline]
        report["noninferiority"][candidate + "_vs_" + baseline] = {
            "status": bench_report._all_status([row["regression_gate"]["status"] for row in cells]),
            "cell_count": len(cells), "required_cell_count": len(scenarios), "all_cells_present": len(cells) == len(scenarios),
            "primary": (candidate, baseline) in PRIMARY, "rule": "every subcell must pass; no pooled cancellation"}
    report["analysis_aliases"] = ALIASES
    report["comparison_plan"] = [list(pair) for pair in PAIRS]
    report["development_scope"] = "Predeclared L3 development comparison after L1; three diagnostic C1 arms isolate penalty removal, reevaluation removal, action correction and common-change response. Diagnostic arms are not replacement candidates."
    return report


def markdown(report):
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
    return "\n".join(lines)

def final_report(family_path, family_sha256, pool_dir, out, markdown_path):
    pool_dir = Path(pool_dir).resolve(strict=True)
    with pool.exclusive_lock(pool_dir / "pool.lock"):
        manifest, metadata, loaded = execution_plan(family_path, family_sha256)
        protocol, runs, references, provenances = loaded
        tables, attestation = legacy.validate_pool_locked(pool_dir, manifest, metadata)
        report = aggregate(protocol, runs, references, tables)
        if report["status"] != "complete":
            raise ValueError("joint report has missing data")
        report["evaluation_family_size"] = manifest["evaluation_family_size"]
        report["provenance"] = {"protocol_sha256": metadata["protocol_sha256"],
                                "reporting_rules_sha256": bench.file_hash(bench_report.RULES),
                                "learning_inputs": provenances, "action_pool": attestation,
                                "family_plan_path": str(Path(family_path).resolve()), "family_plan_sha256": family_sha256,
                                "reporter_sha256": IMPORTED_SHA256, "frozen_sources": {**FROZEN, **legacy.FROZEN_SOURCES}}
        destinations = [Path(out).resolve(), Path(markdown_path).resolve()]
        marker = Path(str(destinations[0]) + ".published.json")
        if len(set(destinations + [marker])) != 3 or any(path.exists() or path.is_relative_to(pool_dir) for path in destinations + [marker]):
            raise ValueError("publication destinations must be distinct new files outside pool")
        check_sources()
        pool._check_inputs(metadata)
        legacy.check_files(attestation["files_sha256"])
        bench.write_new(destinations[0], report)
        destinations[1].parent.mkdir(parents=True, exist_ok=True)
        with destinations[1].open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown(report))
        check_sources()
        pool._check_sources(metadata)
        pool._check_inputs(metadata)
        legacy.check_files(attestation["files_sha256"])
        bench.write_new(marker, {"schema": "padfec.v33.l3_joint_publication/1", "status": "complete", "published_ns": time.time_ns(),
                                "artifacts_sha256": {str(path): bench.file_hash(path) for path in destinations},
                                "family_plan_path": str(Path(family_path).resolve()), "family_plan_sha256": family_sha256,
                                "input_inventory_sha256": bench.digest(metadata["inputs_sha256"]),
                                "pool_attestation_sha256": bench.digest(attestation), "execution_content_sha256": bench.digest(metadata),
                                "reporter_sha256": IMPORTED_SHA256})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-family")
    freeze.add_argument("--collection-plan", type=Path, required=True)
    freeze.add_argument("--previous-family", type=Path, required=True)
    freeze.add_argument("--out", type=Path, required=True)
    for name in ("run", "report"):
        sub = commands.add_parser(name)
        sub.add_argument("--family-plan", type=Path, required=True)
        sub.add_argument("--family-sha256", required=True)
        sub.add_argument("--out", type=Path, required=True)
        if name == "run":
            sub.add_argument("--workers", type=int, default=8)
            sub.add_argument("--time-budget-seconds", type=float, default=300.0)
            sub.add_argument("--loop", action="store_true")
            sub.add_argument("--resume", action="store_true")
        else:
            sub.add_argument("--pool-dir", type=Path, required=True)
            sub.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "freeze-family":
        plan, _ = prepare_plan(args.collection_plan, args.previous_family)
        bench.write_new(args.out, plan)
        result = {"status": "complete", "family": plan["manifest"]["evaluation_family_size"], "role_run_counts": plan["role_run_counts"],
                  "out": str(args.out.resolve()), "sha256": bench.file_hash(args.out)}
    elif args.command == "run":
        manifest, metadata, _ = execution_plan(args.family_plan, args.family_sha256)
        result = pool.run_pool(args.out, manifest, metadata, workers=args.workers, time_budget_seconds=args.time_budget_seconds,
                               loop=args.loop, resume=args.resume)
    else:
        value = final_report(args.family_plan, args.family_sha256, args.pool_dir, args.out, args.markdown)
        result = {"status": value["status"], "out": str(args.out.resolve()), "sha256": bench.file_hash(args.out)}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
