import sys
sys.dont_write_bytecode = True
import argparse
import collections
import json
from pathlib import Path
import re
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_action_pool as pool, bench_oracles, bench_report
from experiments.v33.bench_metrics import paired_summary


PATH = Path(__file__).resolve()
IMPORTED_SHA256 = bench.file_hash(PATH)
PLAN_SCHEMA = "padfec.v33.learning_action_family/1"
REPORT_SCHEMA = "padfec.v33.learning_report/1"
PUBLICATION_SCHEMA = "padfec.v33.learning_publication/1"
MODES = ("none", "c1", "ideal")
ALIASES = {mode: "current_" + mode for mode in MODES}
PAIRS = [(ALIASES[mode], baseline) for mode in MODES for baseline in ("v32", "v31")]
PAIRS.append((ALIASES["c1"], ALIASES["none"]))
STAMP = r"[0-9]{20}_[0-9a-f]{32}"
FROZEN_SOURCES = {
    "bench.py": "58db05857c0e6b230e0e0290ca4328c3ebdba289d3837c4f4957a3702f43c396",
    "bench_action_pool.py": "b3601f7887265c7769ea655cfa15ccce072eada0375a28264f9c2bd1af7463d5",
    "bench_report.py": "7c53c630bb33df9f697fd8dac9c0d3447f0b315d7c5c31fb0769086ed59fcfaa",
    "bench_oracles.py": "ecaa601217c9a6df74c903d0e1cc0572ea4f565cf44deec73eb2a039f43bfba9",
    "bench_metrics.py": "1316c407308656affee6a45c7b5985eada7496a0c3274b4f677c96b78e94d06e",
    "oracle.py": "84e9feb6d880e176dc82af8f6e33d42f7a6d3b97dadcd17b21ccd7f1e198592c",
    "worldsim.py": "8f86bb520af2d18d03f9188f14104bc988af680665f705dbe0121b83d391e374",
    "worldparams.json": "57e9352c5ff778fd278772e496fbbfe74a685ef7ba49b3849b40df45648db6ed",
}


def equal(actual, expected, label):
    if bench.canonical(actual) != bench.canonical(expected):
        raise ValueError(f"learning report {label} differs")


def check_reporter():
    equal(bench.file_hash(PATH), IMPORTED_SHA256, "loaded reporter source")
    for name, expected in FROZEN_SOURCES.items():
        equal(bench.file_hash(PATH.with_name(name)), expected, f"frozen source {name}")


def check_files(files):
    if not isinstance(files, dict) or not files:
        raise ValueError("complete input hash inventory is required")
    for path, expected in files.items():
        if not isinstance(path, str) or str(Path(path).resolve()) != path:
            raise ValueError("input hash paths must be absolute and normalized")
        equal(bench.file_hash(path), expected, f"input {path}")


def analysis_runs(protocol, baseline, current):
    expected = {(name, "full", scenario["id"], seed)
                for name in ("v31", "v32", *ALIASES.values())
                for scenario in protocol["scenarios"] for seed in protocol["seeds"]}
    seen = set()
    result = []
    for raw, imported in [(run, True) for run in baseline] + [(run, False) for run in current]:
        item = dict(raw)
        if imported:
            if raw["generation"] not in ("v31", "v32") or "observation_mode" in raw:
                raise ValueError("baseline generation or observation mode differs")
        else:
            if raw["generation"] != "current" or raw.get("observation_mode") not in MODES:
                raise ValueError("current generation or observation mode differs")
            item["generation"] = ALIASES[raw["observation_mode"]]
        identity = (item["generation"], item["variant"], item["scenario"], item["seed"])
        if identity not in expected or identity in seen or raw.get("mode") != "full":
            raise ValueError("missing, duplicate or unexpected full learning run")
        seen.add(identity)
        result.append(item)
    equal(sorted(seen), sorted(expected), "complete baseline/mode/scenario/seed inventory")
    return sorted(result, key=lambda run: (run["generation"], run["variant"], run["scenario"], run["seed"]))


def family_manifest(protocol, protocol_hash, runs, references):
    contexts = bench.all_contexts(protocol)
    equal(sorted(references), sorted(contexts), "full reference contexts")
    keys = set()
    for run in runs:
        for key in bench_report.weights(run):
            if key[0] not in contexts:
                raise ValueError("action is outside the protocol contexts")
            keys.add(key)
    if {cid for cid, _ in keys} != set(contexts):
        raise ValueError("full action family must cover every context")
    jobs = [{"context_id": cid, "action": list(action),
             "reference_action": references[cid]["chosen_action"],
             "job_id": cid + "_" + "_".join(map(str, action))} for cid, action in sorted(keys)]
    manifest = {"schema": "padfec.v33.oracle_jobs/1", "mode": "actions", "protocol_sha256": protocol_hash,
                "source_sha256": pool._sources(), "jobs": jobs, "evaluation_family_size": len(jobs),
                "raw_run_identities": [[run["generation"], run["variant"], run["scenario"], run["seed"]] for run in runs],
                "oracle_digests": {cid: bench.digest(value) for cid, value in sorted(references.items())}}
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="actions")
    return manifest


def prepare_plan(overlay_path, raw_dirs):
    check_reporter()
    from experiments.v33 import bench_learning as loader
    overlay_path = Path(overlay_path).resolve(strict=True)
    folders = [Path(path).resolve(strict=True) for path in raw_dirs]
    if not folders or len(folders) != len(set(folders)):
        raise ValueError("learning raw directories must be unique and nonempty")
    overlay, expected_protocol = loader.load_overlay(overlay_path)
    protocol, baseline, current, references, provenance = loader.load_learning_runs(overlay_path, folders, require_complete=True)
    equal(protocol, expected_protocol, "loaded base protocol")
    equal(provenance.get("complete"), True, "complete loader result")
    runs = analysis_runs(protocol, baseline, current)
    manifest = family_manifest(protocol, overlay["base_protocol_sha256"], runs, references)
    inputs = dict(provenance["inputs_sha256"])
    required = {str(overlay_path): bench.file_hash(overlay_path), str(PATH): IMPORTED_SHA256,
                str(Path(loader.__file__).resolve()): bench.file_hash(loader.__file__)}
    for name in FROZEN_SOURCES:
        required[str(PATH.with_name(name))] = bench.file_hash(PATH.with_name(name))
    required[str(Path(overlay["base_protocol_path"]).resolve())] = overlay["base_protocol_sha256"]
    required[str(Path(overlay["import_receipt_path"]).resolve())] = overlay["import_receipt_sha256"]
    required[str(Path(overlay["policy"]["receipt_path"]).resolve())] = overlay["policy"]["receipt_sha256"]
    for run in baseline + current:
        required[str(Path(run["trace_path"]).resolve())] = run["trace_sha256"]
    for path, expected in required.items():
        if path != str(PATH) and path not in inputs:
            raise ValueError(f"loader input inventory omits {path}")
        if path in inputs:
            equal(inputs[path], expected, "loader input source binding")
        inputs[path] = expected
    check_files(inputs)
    plan = {"schema": PLAN_SCHEMA, "overlay_path": str(overlay_path), "overlay_sha256": bench.file_hash(overlay_path),
            "raw_dirs": sorted(map(str, folders)), "protocol_path": overlay["base_protocol_path"],
            "protocol_sha256": overlay["base_protocol_sha256"], "contexts_sha256": bench.digest(bench.all_contexts(protocol)),
            "manifest": manifest, "inputs_sha256": dict(sorted(inputs.items())), "planner_sha256": IMPORTED_SHA256,
            "loader_sha256": bench.file_hash(loader.__file__), "raw_schema": loader.RAW_SCHEMA,
            "baseline_run_count": len(baseline), "current_run_count": len(current),
            "analysis_aliases": ALIASES, "comparisons": [list(pair) for pair in PAIRS],
            "interval_reuse": "none; all actions are evaluated again under this entire family",
            "validation": "bench_learning.load_learning_runs(require_complete=True); new-schema inputs checked before frozen pool execution"}
    check_reporter()
    return plan, (protocol, baseline, current, references, provenance)


def freeze_family(overlay_path, raw_dirs, out):
    plan, _ = prepare_plan(overlay_path, raw_dirs)
    bench.write_new(Path(out), plan)
    return plan


def execution_plan(family_path, family_sha256):
    family_path = Path(family_path).resolve(strict=True)
    equal(bench.file_hash(family_path), family_sha256, "family file SHA")
    saved = pool.read_json(family_path)
    equal(saved.get("schema"), PLAN_SCHEMA, "family schema")
    rebuilt, loaded = prepare_plan(saved["overlay_path"], saved["raw_dirs"])
    equal(saved, rebuilt, "reconstructed full family")
    manifest = saved["manifest"]
    metadata = {"schema": pool.SCHEMA, "adapter_sha256": FROZEN_SOURCES["bench_action_pool.py"],
                "manifest_sha256": bench.digest(manifest), "protocol_path": saved["protocol_path"],
                "protocol_sha256": saved["protocol_sha256"], "family_plan_path": str(family_path),
                "family_plan_sha256": family_sha256, "source_sha256": manifest["source_sha256"],
                "inputs_sha256": saved["inputs_sha256"], "contexts_sha256": saved["contexts_sha256"],
                "planner_sha256": saved["planner_sha256"], "loader_sha256": saved["loader_sha256"],
                "input_validation_schema": saved["raw_schema"], "input_validation": saved["validation"],
                "overlay_sha256": saved["overlay_sha256"], "analysis_aliases": saved["analysis_aliases"]}
    pool._check_sources(metadata)
    pool._check_inputs(metadata)
    return manifest, metadata, loaded


def run_family(family_path, family_sha256, out, **runtime):
    manifest, metadata, _ = execution_plan(family_path, family_sha256)
    return pool.run_pool(out, manifest, metadata, **runtime)


def job_set(value, known, label):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"invalid {label}")
    if len(set(value)) != len(value) or not set(value) <= known:
        raise ValueError(f"duplicate or unknown {label}")
    return set(value)


def receipt_pairs(folder, pattern, metadata, manifest, runs=None):
    jobs = {job["job_id"]: job for job in manifest["jobs"]}
    pairs, hashes = {}, {}
    for path in sorted(Path(folder).glob("*.json")):
        match = re.fullmatch(pattern, path.name)
        if match is None:
            raise ValueError(f"unrecognized execution receipt: {path}")
        parts = match.groups()
        key, phase = tuple(parts[:-1]), parts[-1]
        entry = pool.read_json(path)
        equal(entry.get("schema"), pool.SCHEMA, "receipt schema")
        equal(entry.get("execution_sha256"), bench.digest(metadata), "receipt execution")
        if runs is None:
            equal(entry.get("run_id"), key[0], "run receipt identity")
        else:
            if key[0] not in jobs or entry.get("run_id") not in runs:
                raise ValueError("attempt has unknown job or run")
            equal(entry.get("job"), jobs[key[0]], "attempt job identity")
        pair = pairs.setdefault(key, {})
        if phase in pair:
            raise ValueError("duplicate receipt phase")
        pair[phase] = entry
        hashes[str(path.resolve())] = bench.file_hash(path)
    if not pairs:
        raise ValueError("execution receipts are missing")
    for key, pair in pairs.items():
        if set(pair) != {"started", "finished"}:
            raise ValueError("unfinished or unmatched execution receipt")
        start, finish = pair["started"], pair["finished"]
        equal(start["run_id"], finish["run_id"], "paired receipt run")
        if finish.get("status") not in ("complete", "partial"):
            raise ValueError("failed or unknown execution status requires investigation")
        if type(start.get("started_ns")) is not int or type(finish.get("finished_ns")) is not int:
            raise ValueError("receipt timestamps must be integers")
        if start["started_ns"] <= 0 or finish["finished_ns"] < start["started_ns"]:
            raise ValueError("invalid receipt timestamp order")
        if runs is None:
            equal(start.get("adapter_sha256"), metadata["adapter_sha256"], "run adapter")
            equal(finish.get("evaluation_family_size"), len(jobs), "run family")
            complete = job_set(finish.get("complete_jobs"), set(jobs), "complete jobs")
            pending = job_set(finish.get("pending_jobs"), set(jobs), "pending jobs")
            if complete & pending or complete | pending != set(jobs):
                raise ValueError("run does not partition the whole family")
            equal(finish.get("failed_jobs"), [], "failed jobs")
            equal(finish["status"], "partial" if pending else "complete", "run status")
        else:
            parent = runs[start["run_id"]]
            if start["started_ns"] < parent["started"]["started_ns"] or finish["finished_ns"] > parent["finished"]["finished_ns"]:
                raise ValueError("attempt timestamps are outside the run")
            equal(start.get("started_ns"), finish.get("started_ns"), "attempt start binding")
            equal(start.get("pid"), finish.get("pid"), "attempt worker identity")
    return pairs, hashes


def validate_pool_locked(out, manifest, metadata):
    out = Path(out).resolve()
    actual, saved, protocol, contexts = pool._load_execution(out)
    equal(actual, manifest, "pool full manifest")
    equal(saved, metadata, "pool execution metadata")
    pool._check_inputs(metadata)
    pool._check_output_inventory(out, manifest)
    if any((out / "failures").glob("*.json")):
        raise ValueError("pool failure files require investigation")
    run_pairs, receipt_hashes = receipt_pairs(out / "runs", rf"({STAMP})\.(started|finished)\.json", metadata, manifest)
    runs = {key[0]: pair for key, pair in run_pairs.items()}
    if runs[max(runs)]["finished"]["status"] != "complete":
        raise ValueError("latest pool run is incomplete")
    _, attempts = receipt_pairs(out / "attempts", rf"([^.]+)\.({STAMP})\.(started|finished)\.json", metadata, manifest, runs)
    receipt_hashes.update(attempts)
    tables = {}
    for job in manifest["jobs"]:
        status = pool.inspect_job(out, manifest, metadata, protocol, contexts, job)
        if status["status"] != "complete":
            raise ValueError("action job is incomplete")
        result_path, checkpoint_path = pool._job_paths(out, job["job_id"])
        item = pool.read_json(result_path)
        tables[(job["context_id"], tuple(job["action"]))] = item
        receipt_hashes[str(result_path.resolve())] = bench.file_hash(result_path)
        if checkpoint_path.exists():
            receipt_hashes[str(checkpoint_path.resolve())] = bench.file_hash(checkpoint_path)
    for name in ("manifest.json", "execution.json"):
        receipt_hashes[str(out / name)] = bench.file_hash(out / name)
    pool._check_sources(metadata)
    check_files(receipt_hashes)
    return tables, {"pool_path": str(out), "evaluation_family_size": len(manifest["jobs"]),
                    "validated_run_ids": sorted(runs), "files_sha256": receipt_hashes,
                    "execution_content_sha256": bench.digest(metadata),
                    "manifest_content_sha256": bench.digest(manifest)}


DIAGNOSTIC_FIELDS = (
    ("loss_update_kind", "observation_info", "loss_update_kind"),
    ("evidence_source", "observation_info", "loss_evidence_src"),
    ("arrival_usable", "observation_info", "arrival_usable"),
    ("arrival_reject_reason", "observation_info", "arrival_reject_reason"),
    ("arrival_trunc", "observation_info", "arrival_trunc"),
    ("observer_reason", "observer_diagnostics", "reason"),
    ("observer_usable", "observer_diagnostics", "usable"),
    ("feedback_generated", "observer_diagnostics", "feedback_generated"),
    ("feedback_received", "observer_diagnostics", "feedback_received"),
    ("crc_list_truncated", "observer_diagnostics", "crc_list_truncated"),
    ("receiver_datagram_truncated", "observer_diagnostics", "receiver_datagram_truncated"),
    ("all_lost", "observer_diagnostics", "all_lost"),
    ("all_lost_basis", "observer_diagnostics", "all_lost_basis"),
    ("evaluation_only_all_lost", "observer_diagnostics", "evaluation_only_all_lost"),
    ("evaluation_only_no_response_pto", "observer_diagnostics", "evaluation_only_no_response_pto"),
    ("evaluation_only_c2_false_all_lost", "observer_diagnostics", "evaluation_only_c2_false_all_lost"),
)


def observation_diagnostics(rows, mode):
    counts = {name: collections.Counter() for name, _, _ in DIAGNOSTIC_FIELDS}
    successes = learned_all_lost = used_sent = used_lost = 0
    confirmed_all_lost = confirmed_not_all_lost = unknown_all_lost = 0
    for row in rows:
        equal(row.get("observation_mode"), mode, "trace observation mode")
        info, diagnostic = row["observation_info"], row["observer_diagnostics"]
        equal(diagnostic.get("mode"), mode, "observer diagnostic mode")
        kind = info.get("loss_update_kind")
        if kind not in ("datagram", "categorical", "predict_only"):
            raise ValueError("unknown loss update kind")
        evidence = row["policy_observe_input"]["optional"]["first_flight_evidence"]
        usable = evidence["src"] != "none" and evidence["sent"] > 0 and not evidence["trunc"]
        equal(info["arrival_usable"], usable, "arrival usability")
        equal(kind == "datagram", usable, "datagram routing")
        equal(info["loss_evidence_src"], evidence["src"], "evidence source")
        equal(info["arrival_sent"], evidence["sent"], "evidence sent")
        equal(info["arrival_lost"], evidence["lost"], "evidence lost")
        equal(info["arrival_trunc"], evidence["trunc"], "evidence censoring")
        if type(row["ok"]) is not bool:
            raise ValueError("observation success flag must be boolean")
        successes += int(row["ok"])
        if diagnostic.get("usable") is True and type(diagnostic.get("all_lost")) is bool:
            confirmed_all_lost += int(diagnostic["all_lost"])
            confirmed_not_all_lost += int(not diagnostic["all_lost"])
        else:
            unknown_all_lost += 1
        if usable:
            used_sent += evidence["sent"]
            used_lost += evidence["lost"]
            learned_all_lost += int(evidence["sent"] == evidence["lost"])
        for name, source, field in DIAGNOSTIC_FIELDS:
            value = row[source]
            key = bench.canonical({"present": field in value, "value": value.get(field)}).decode("utf-8")
            counts[name][key] += 1
    return {"connections": len(rows), "successes": successes, "failures": len(rows) - successes,
            "learned_all_lost_connections": learned_all_lost,
            "confirmed_all_lost_connections": confirmed_all_lost,
            "confirmed_not_all_lost_connections": confirmed_not_all_lost,
            "unknown_all_lost_connections": unknown_all_lost,
            "datagram_likelihood_sent": used_sent, "datagram_likelihood_lost": used_lost,
            "counts": {name: dict(counter) for name, counter in counts.items()}}


def merge_diagnostics(values):
    totals = {key: sum(item[key] for item in values) for key in
              ("connections", "successes", "failures", "learned_all_lost_connections", "datagram_likelihood_sent", "datagram_likelihood_lost",
               "confirmed_all_lost_connections", "confirmed_not_all_lost_connections", "unknown_all_lost_connections")}
    equal(totals["confirmed_all_lost_connections"] + totals["confirmed_not_all_lost_connections"] + totals["unknown_all_lost_connections"],
          totals["connections"], "all-lost diagnostic denominator")
    totals["distributions"] = {}
    for name, _, _ in DIAGNOSTIC_FIELDS:
        counts = collections.Counter()
        for item in values:
            counts.update(item["counts"][name])
        equal(sum(counts.values()), totals["connections"], "all-connection diagnostic denominator")
        totals["distributions"][name] = [{**json.loads(key), "n": n, "fraction_all_connections": n / totals["connections"]}
                                         for key, n in sorted(counts.items())]
    totals["denominator_scope"] = "all connections, including failures, missing feedback and all-lost; absent and null are distinct"
    totals["evaluation_only_fields_are_privileged_diagnostics"] = True
    totals["all_lost_interpretation"] = "observer.usable must be true and all_lost boolean to confirm all-lost or not-all-lost; unusable false sentinels remain unknown"
    return totals


def convergence(group, runs, scenario, protocol):
    if group["family"] not in ("B3", "B4"):
        return None
    if any(float(phase.get("p", scenario["context"].get("p", 0))) != 0 for phase in scenario["phases"]):
        raise ValueError("B3/B4 p-bias equivalence requires zero true c2s loss")
    tail = group["observed"]["p_bias_high_phase"]
    required = protocol["metrics"]["p_bias_high_phase_last_n"]
    eligible = all(run["summary"].get("p_bias_high_phase_n", 0) >= required for run in runs)
    gate = bench_report.threshold_from_summary(tail if eligible else paired_summary([]), 0.01)
    final = [{"seed": run["seed"], "p_mean_after_last_observation": run["final_state"].get("p_mean")} for run in runs]
    available = all(item["p_mean_after_last_observation"] is not None for item in final)
    final_summary = paired_summary([item["p_mean_after_last_observation"] for item in final], protocol["metrics"]["paired_confidence"]) if available else paired_summary([])
    return {"predecision_tail_p_mean": tail, "predecision_tail_gate": gate,
            "tail_definition": "existing high-phase p_bias; at p=0 this equals predecision p_mean; existing tail count is unchanged",
            "required_tail_observations_per_seed": required, "tail_complete": eligible,
            "final_post_observation_p_mean": final_summary, "final_by_seed": final,
            "final_state_scope": "after the final observation; diagnostic only, not a replacement for predecision convergence"}


def aggregate_learning(protocol, baseline, current, references, tables, trace_loader=bench_report.load_trace):
    runs = analysis_runs(protocol, baseline, current)
    by_group = collections.defaultdict(list)
    for run in runs:
        by_group[run["generation"], run["scenario"]].append(run)
    diagnostics = collections.defaultdict(list)
    def load(run):
        rows = trace_loader(run)
        if run["generation"] in ALIASES.values():
            diagnostics[run["generation"], run["scenario"]].append(observation_diagnostics(rows, run["observation_mode"]))
        return rows
    report = bench_report.aggregate(runs, references, tables, protocol, trace_loader=load)
    report["schema"] = REPORT_SCHEMA
    scenarios = {scenario["id"]: scenario for scenario in protocol["scenarios"]}
    for group in report["groups"]:
        key = group["generation"], group["scenario"]
        group["policy_generation"] = "current" if key[0] in ALIASES.values() else key[0]
        group["observation_mode"] = next((mode for mode, alias in ALIASES.items() if alias == key[0]), "legacy_none")
        group["observation_diagnostics"] = merge_diagnostics(diagnostics[key]) if key in diagnostics else None
        group["p_convergence"] = convergence(group, by_group[key], scenarios[key[1]], protocol)
    comparisons = []
    for candidate, baseline_name in PAIRS:
        for sid in scenarios:
            item = bench_report.direct_comparison(by_group[candidate, sid], by_group[baseline_name, sid], tables,
                                                   protocol["metrics"]["paired_confidence"])
            item.update(candidate={"generation": candidate, "variant": "full"}, baseline={"generation": baseline_name, "variant": "full"},
                        scenario=sid, kind="observation_mode_contrast" if baseline_name == ALIASES["none"] else
                        "pre_post_vs_v32" if baseline_name == "v32" else "w1_noninferiority_vs_v31")
            item["regression_gate"] = bench_report.threshold_from_summary(item["seed_summary"], protocol["thresholds"]["max_regression_vs_v31_ms"],
                                                                           mc_bound=item["shared_mc_bound_ms"], inclusive=True)
            item["primary"] = candidate == ALIASES["c1"] and baseline_name in ("v32", "v31")
            item["ideal_is_privileged_diagnostic"] = candidate == ALIASES["ideal"]
            comparisons.append(item)
    report["comparisons"] = comparisons
    report["noninferiority"] = {}
    for baseline_name, key in (("v32", "pre_post_vs_v32"), ("v31", "w1_noninferiority_vs_v31")):
        report["noninferiority"][key] = {}
        for mode, alias in ALIASES.items():
            cells = [item for item in comparisons if item["candidate"]["generation"] == alias and item["baseline"]["generation"] == baseline_name]
            report["noninferiority"][key][mode] = {
                "status": bench_report._all_status([item["regression_gate"]["status"] for item in cells]),
                "cell_count": len(cells), "required_cell_count": len(scenarios), "all_cells_present": len(cells) == len(scenarios),
                "primary": mode == "c1", "ideal_is_privileged_diagnostic": mode == "ideal",
                "rule": "every scenario subcell must pass; no pooled cancellation"}
    report["analysis_aliases"] = ALIASES
    report["comparison_plan"] = [list(pair) for pair in PAIRS]
    report["primary_mode"] = "c1"
    report["development_scope"] = "L1 development analysis after reading the W1 baseline; no claim that these added reporting rules predate baseline results"
    report["observation_scope"] = "passive observer changes available evidence only; ideal uses privileged receiver information; original world/oracle remain fixed"
    return report


def markdown(report):
    lines = ["# L1 학습 벤치 보고", "", "개발 자료다. C1을 주 결과로, ideal을 특권적 수신 정보의 상한 진단으로 구분한다.", "",
             "입력 수집 완료와 각 문턱 통과는 별개다. 선택 기준 대비 기대 차이, seed 구간, 공통 MC 폭, 선택 오차를 분리한다.", "",
             "| 세대/관측 | 셀 | 기대 차이 ms | seed 구간 | 공통 MC 폭 | 선택 오차 | regret 판정 |", "|---|---|---:|---|---:|---:|---|"]
    number = bench_report._number
    for group in report["groups"]:
        expected = group["expected_regret"]
        summary = expected["seed_summary"]
        lines.append(f"| {group['generation']} | {group['scenario']} | {number(summary['mean'])} | [{number(summary['lower'])}, {number(summary['upper'])}] | {number(expected['shared_mc_bound_ms'])} | {number(expected['selection_gap_bound_ms'])} | {group['gates'].get('regret', {}).get('status', '해당 없음')} |")
    lines.extend(["", "| 직접 대조 | 셀 | 기대 차이 ms | seed 구간 | 공통 MC 폭 | 합성 경계 | 실현 HCT 차이 ms | 비열등 판정 |", "|---|---|---:|---|---:|---|---:|---|"])
    for item in report["comparisons"]:
        seed = item["seed_summary"]
        lines.append(f"| {item['candidate']['generation']} - {item['baseline']['generation']} | {item['scenario']} | {number(seed['mean'])} | [{number(seed['lower'])}, {number(seed['upper'])}] | {number(item['shared_mc_bound_ms'])} | [{number(item['lower_bound_ms'])}, {number(item['upper_bound_ms'])}] | {number(item['realized_hct_diagnostic']['mean'])} | {item['regression_gate']['status']} |")
    lines.extend(["", "차이는 후보에서 기준을 뺀 값이다. 음수가 더 빠르다. 0.5ms 비열등 통과는 개선 입증을 뜻하지 않는다. 실현 HCT 차이는 진단이며 기대 차이 판정에 대신 쓰지 않는다.", "",
                  "| 세대/관측 | 셀 | HCT ms | 서버 추가 B | p 편향 | p 수렴 | 마지막 관측 뒤 p | B5 적응 |", "|---|---|---:|---:|---:|---|---:|---|"])
    for group in report["groups"]:
        observed, convergence_value = group["observed"], group["p_convergence"]
        convergence_status = "해당 없음" if convergence_value is None else convergence_value["predecision_tail_gate"]["status"]
        final_p = "해당 없음" if convergence_value is None else number(convergence_value["final_post_observation_p_mean"]["mean"])
        adaptation = group["gates"].get("adaptation", {}).get("status", "해당 없음")
        lines.append(f"| {group['generation']} | {group['scenario']} | {number(observed['mean_hct_ms']['mean'])} | {number(observed['mean_extra_server_bytes']['mean'])} | {number(observed['p_bias_high_phase']['mean'])} | {convergence_status} | {final_p} | {adaptation} |")
    lines.extend(["", "| 관측 모드 | 셀 | 전체 연결 | 실패 | 도착 우도 | 등급 우도 | 예측만 | 관측 전멸 | 전멸 미확인 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
    for group in report["groups"]:
        diagnostic = group["observation_diagnostics"]
        if diagnostic is None:
            continue
        def count(field, value):
            return sum(item["n"] for item in diagnostic["distributions"][field] if item["present"] and item["value"] == value)
        lines.append(f"| {group['observation_mode']} | {group['scenario']} | {diagnostic['connections']} | {diagnostic['failures']} | {count('loss_update_kind', 'datagram')} | {count('loss_update_kind', 'categorical')} | {count('loss_update_kind', 'predict_only')} | {diagnostic['confirmed_all_lost_connections']} | {diagnostic['unknown_all_lost_connections']} |")
    lines.extend(["", "C1 대 v32 전후 회귀와 C1 대 v31 W1 비열등은 JSON의 noninferiority에서 별도로 판정한다.",
                  "관측 coverage·fallback·전멸·누락 분모는 실패를 포함한 전체 연결이다. null과 미확정은 통과로 바꾸지 않는다.",
                  "B3/B4 수렴은 기존 무손실 phase의 결정 전 p 평균으로 판정한다. 마지막 관측 뒤 상태는 별도 진단이다.",
                  "seed 95% 구간과 문맥/행동 family의 99% MC 근사 경계를 합해도 전체 동시 95% 보장이 되지는 않는다.", ""])
    return "\n".join(lines)


def final_report(family_path, family_sha256, pool_dir, out, markdown_path=None):
    pool_dir = Path(pool_dir).resolve(strict=True)
    with pool.exclusive_lock(pool_dir / "pool.lock"):
        manifest, metadata, loaded = execution_plan(family_path, family_sha256)
        protocol, baseline, current, references, provenance = loaded
        tables, attestation = validate_pool_locked(pool_dir, manifest, metadata)
        report = aggregate_learning(protocol, baseline, current, references, tables)
        report["provenance"] = {"learning_inputs": provenance, "action_pool": attestation,
                                "family_plan_path": str(Path(family_path).resolve()), "family_plan_sha256": family_sha256,
                                "reporter_sha256": IMPORTED_SHA256, "frozen_sources": FROZEN_SOURCES}
        report["evaluation_family_size"] = manifest["evaluation_family_size"]
        if report["missing"] or report["missing_raw_groups"] or report["status"] != "complete":
            raise ValueError("final learning report still has missing data")
        destinations = [Path(out).resolve()] + ([Path(markdown_path).resolve()] if markdown_path is not None else [])
        publication_path = Path(str(destinations[0]) + ".published.json")
        destinations_with_receipt = destinations + [publication_path]
        if len(set(destinations_with_receipt)) != len(destinations_with_receipt) or any(path.exists() or path.is_relative_to(pool_dir) for path in destinations_with_receipt):
            raise ValueError("report destinations must be distinct new files outside the pool")
        check_reporter()
        pool._check_sources(metadata)
        pool._check_inputs(metadata)
        check_files(attestation["files_sha256"])
        bench.write_new(destinations[0], report)
        if markdown_path is not None:
            destinations[1].parent.mkdir(parents=True, exist_ok=True)
            with destinations[1].open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(markdown(report))
        check_reporter()
        pool._check_sources(metadata)
        pool._check_inputs(metadata)
        check_files(attestation["files_sha256"])
        bench.write_new(publication_path, {"schema": PUBLICATION_SCHEMA, "status": "complete", "published_ns": time.time_ns(),
                        "artifacts_sha256": {str(path): bench.file_hash(path) for path in destinations},
                        "family_plan_path": str(Path(family_path).resolve()), "family_plan_sha256": family_sha256,
                        "input_inventory_sha256": bench.digest(metadata["inputs_sha256"]),
                        "pool_attestation_sha256": bench.digest(attestation), "execution_content_sha256": bench.digest(metadata),
                        "reporter_sha256": IMPORTED_SHA256})
        return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("plan")
    freeze.add_argument("--overlay", type=Path, required=True)
    freeze.add_argument("--raw-dirs", type=Path, nargs="+", required=True)
    freeze.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run")
    report = commands.add_parser("report")
    for command in (run, report):
        command.add_argument("--family-plan", type=Path, required=True)
        command.add_argument("--family-plan-sha256", dest="family_sha256", required=True)
        command.add_argument("--out", type=Path, required=True)
    run.add_argument("--workers", type=int, default=2)
    run.add_argument("--time-budget-seconds", type=float, default=300.0)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--loop", action="store_true")
    report.add_argument("--pool", type=Path, required=True)
    report.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = freeze_family(args.overlay, args.raw_dirs, args.out)
        summary = {"status": "complete", "out": str(args.out.resolve()), "sha256": bench.file_hash(args.out),
                   "evaluation_family_size": result["manifest"]["evaluation_family_size"]}
    elif args.command == "run":
        summary = run_family(args.family_plan, args.family_sha256, args.out, workers=args.workers,
                             time_budget_seconds=args.time_budget_seconds, resume=args.resume, loop=args.loop)
    else:
        result = final_report(args.family_plan, args.family_sha256, args.pool, args.out, args.markdown)
        summary = {"status": result["status"], "out": str(args.out.resolve()), "sha256": bench.file_hash(args.out),
                   "publication_receipt": str(Path(str(args.out.resolve()) + ".published.json")),
                   "evaluation_family_size": result["evaluation_family_size"], "noninferiority": result["noninferiority"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
    return 0 if summary["status"] == "complete" else 2 if summary["status"] == "failed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
