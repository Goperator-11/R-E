import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import collections
from contextlib import contextmanager
import datetime as dt
from fractions import Fraction
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import statistics
import time


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
FAMILY = RUNS / "J1_joint_action_family_v1.json"
FAMILY_SHA = None
POOL = RUNS / "J1_joint_action_pool_v1"
REPORT = ROOT / "g3/v33/J1_benchmark_v1.json"
MARKDOWN = RUNS / "J1_bench_v1.md"
REPORTER = ROOT / "experiments/v33/bench_learning_j1_report.py"
REPORTER_SHA = '2eeac81d27e9161b07545b9aa6b6bd8e5207fe4e0e13d67b3fcd74e43bed2d6a'
DRIVER = RUNS / "j1_joint_driver_v1.py"
DRIVER_SHA = '967281984c9621f6393cb54f7fcab9dcd78cdd9e5d392e5a25b3e840450a23f2'
BASE = RUNS / "l1_precision_artifact_check_v4.py"
BASE_SHA = "a7504e1a2c94e54721077bbdaff068241da4e4274e17883eb5a7bab8f94aefd6"
N = 131072
STAMP = r"[0-9]{20}_[0-9a-f]{32}"
KST = dt.timezone(dt.timedelta(hours=9))
file_hash = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert file_hash(BASE) == BASE_SHA
spec = importlib.util.spec_from_file_location("verified_independent_arithmetic", BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
canonical, digest = base.canonical, base.digest
weights, bound = base.weights, base.bound
check_seed_summary, check_gate = base.check_seed_summary, base.check_gate
SELF_SHA = file_hash(__file__)
GRADE_PATH = RUNS / "j1_grade_audit_v1.py"
GRADE_SHA = 'c4eb58166e2ae6baf655cdb6a15ea4a689886baf70a1d90668a062df0b202750'
assert file_hash(GRADE_PATH) == GRADE_SHA
grade_spec = importlib.util.spec_from_file_location("independent_j1_grade", GRADE_PATH)
grade = importlib.util.module_from_spec(grade_spec)
grade_spec.loader.exec_module(grade)



class Audit(base.Audit):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.last_check = None

    def check(self, name, condition):
        self.count += 1
        self.last_check = name
        if not condition:
            raise ValueError(name)


@contextmanager
def completed_pool_lock():
    with (POOL / "pool.lock").open("r+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def driver_receipts(audit):
    audit.file(REPORTER, REPORTER_SHA)
    audit.file(DRIVER, DRIVER_SHA)
    values = {}
    for phase in ("plan", "run", "report"):
        prefix = "J1_joint_" + phase + "_v1"
        start_path, end_path = RUNS / (prefix + ".started.json"), RUNS / (prefix + ".finished.json")
        start, end = audit.read(start_path), audit.read(end_path)
        audit.equal("phase_complete:" + phase, end["status"], "complete")
        audit.equal("phase_exit:" + phase, end["exit_code"], 0)
        audit.equal("phase_error:" + phase, end["launch_error"], None)
        audit.equal("phase_start_binding:" + phase, end["started_receipt_sha256"], audit.file(start_path))
        for key in ("command", "wrapper_sha256", "driver_sha256", "inputs_sha256", "plan_identity", "preceding_run"):
            audit.equal("phase_pair:" + phase + key, start[key], end[key])
        for key, expected in (("wrapper_sha256", REPORTER_SHA), ("driver_sha256", DRIVER_SHA)):
            audit.equal("phase_source:" + phase + key, end[key], expected)
            audit.equal("phase_source_after:" + phase + key, end[key + "_after"], expected)
        audit.inventory(end["inputs_sha256"])
        for kind in ("stdout", "stderr"):
            audit.file(end[kind + "_path"], end[kind + "_sha256"])
        if end["published_outputs_sha256"]:
            audit.inventory(end["published_outputs_sha256"])
        audit.equal("phase_python_options:" + phase, start["command"][1:3], ["-I", "-B"])
        audit.equal("phase_wrapper_command:" + phase, start["command"][3], str(REPORTER))
        audit.equal("phase_name_command:" + phase, start["command"][4], "freeze-family" if phase == "plan" else phase)
        values[phase] = start, end
    plan_path = RUNS / "J1_joint_plan_v1.finished.json"
    identity = {"path": str(plan_path), "sha256": audit.file(plan_path), "outputs_sha256": {str(FAMILY): FAMILY_SHA}}
    audit.equal("plan_output", values["plan"][1]["published_outputs_sha256"], identity["outputs_sha256"])
    for phase in ("run", "report"):
        audit.equal("plan_lineage:" + phase, values[phase][1]["plan_identity"], identity)
    run_path = RUNS / "J1_joint_run_v1.finished.json"
    audit.equal("report_run_lineage", values["report"][1]["preceding_run"], {"path": str(run_path), "sha256": audit.file(run_path), "outputs_sha256": {}})
    audit.equal("report_output_inventory", sorted(values["report"][1]["published_outputs_sha256"]), sorted(map(str, (REPORT, MARKDOWN, Path(str(REPORT) + ".published.json")))))
    return values


def load_inputs(audit, family, protocol):
    old_family = audit.read(family["previous_family_path"], family["previous_family_sha256"])
    old_overlay = audit.read(old_family["overlay_path"], old_family["overlay_sha256"])
    imported = audit.read(old_overlay["import_receipt_path"], old_overlay["import_receipt_sha256"])
    refs, runs = {}, []
    for item in imported["provenance"]["result_files"]:
        value = audit.read(item["path"], item["sha256"])
        cid = value["context_id"]
        audit.check("unique_reference:" + cid, cid not in refs)
        audit.equal("reference_status:" + cid, value["status"], "complete")
        audit.equal("reference_digest:" + cid, digest(value), family["manifest"]["oracle_digests"][cid])
        refs[cid] = value
    for item in imported["provenance"]["raw_summary_files"]:
        value = audit.read(item["path"], item["sha256"])
        if value["generation"] in ("v31", "v32") and value["variant"] == "full":
            runs.append({**value, "analysis_role": "baseline"})
    audit.equal("baseline_count", len(runs), 600)
    collection = audit.read(family["collection_plan_path"], family["collection_plan_sha256"])
    folders = [(Path(path), "l1") for path in old_family["raw_dirs"]]
    folders += [(Path(job["out"]), "j1" if job["policy"] == "J1_v1" else "cost") for job in collection["jobs"]]
    for folder, role in folders:
        shard = audit.read(folder / "manifest.json")
        audit.equal("shard_mode:" + str(folder), shard["mode"], "full")
        for mode in shard["observation_modes"]:
            for sid in shard["scenarios"]:
                for seed in shard["seeds"]:
                    path = folder / mode / sid / f"seed{seed:05d}.json"
                    value = audit.read(path, family["inputs_sha256"][str(path)])
                    for key, expected in (("generation", "current"), ("mode", "full"), ("status", "complete"), ("scenario", sid), ("seed", seed), ("observation_mode", mode)):
                        audit.equal("raw_binding:" + str(path) + key, value[key], expected)
                    runs.append({**value, "generation": role + "_" + mode, "analysis_role": role})
    names = ["v31", "v32", "l1_none", "l1_c1", "l1_ideal", "j1_none", "j1_c1", "j1_ideal", "cost_none", "cost_c1"]
    expected = sorted((name, "full", scenario["id"], seed) for name in names for scenario in protocol["scenarios"] for seed in protocol["seeds"])
    actual = [(row["generation"], row["variant"], row["scenario"], row["seed"]) for row in runs]
    audit.equal("joint_raw_exact_inventory", sorted(actual), expected)
    audit.equal("joint_raw_unique_count", len(actual), len(set(actual)))
    audit.equal("family_raw_exact_inventory", family["manifest"]["raw_run_identities"], [list(row) for row in expected])
    scenarios = {row["id"]: row for row in protocol["scenarios"]}
    groups, union = collections.defaultdict(list), set()
    for row in runs:
        label = row["generation"] + row["scenario"] + str(row["seed"])
        audit.equal("raw_length:" + label, row["n"], sum(phase["length"] for phase in scenarios[row["scenario"]]["phases"]))
        audit.file(row["trace_path"], row["trace_sha256"])
        coefficients = weights(row)
        union.update(key for key, value in coefficients.items() if value)
        groups[row["generation"], row["scenario"]].append(row)
    for values in groups.values():
        values.sort(key=lambda row: row["seed"])
    audit.equal("joint_action_union", sorted(union), sorted((row["context_id"], tuple(row["action"])) for row in family["manifest"]["jobs"]))
    audit.equal("joint_counts", {key: sum(row["analysis_role"] == key for row in runs) for key in ("baseline", "l1", "j1", "cost")}, family["role_run_counts"])
    return refs, groups


def verify(audit):
    receipts = driver_receipts(audit)
    family = audit.read(FAMILY, FAMILY_SHA)
    protocol = audit.read(family["protocol_path"], family["protocol_sha256"])
    audit.equal("cost_N", protocol["oracle"]["validation_samples"], N)
    audit.equal("cost_seed", protocol["oracle"]["validation_seed"], 850001)
    audit.equal("cost_seed_inventory", protocol["seeds"], list(range(31, 51)))
    audit.inventory(family["inputs_sha256"])
    report = audit.read(REPORT)
    marker = audit.read(Path(str(REPORT) + ".published.json"))
    audit.equal("report_status", report["status"], "complete")
    audit.equal("report_missing", report["missing"], [])
    audit.equal("marker_status", marker["status"], "complete")
    audit.equal("marker_family", marker["family_plan_sha256"], FAMILY_SHA)
    audit.equal("marker_reporter", marker["reporter_sha256"], REPORTER_SHA)
    audit.equal("marker_outputs", marker["artifacts_sha256"], {str(REPORT): audit.file(REPORT), str(MARKDOWN): audit.file(MARKDOWN)})
    manifest, metadata = audit.read(POOL / "manifest.json"), audit.read(POOL / "execution.json")
    audit.equal("saved_manifest", manifest, family["manifest"])
    audit.equal("execution_inputs", metadata["inputs_sha256"], family["inputs_sha256"])
    audit.equal("execution_family", metadata["family_plan_sha256"], FAMILY_SHA)
    audit.equal("marker_execution", marker["execution_content_sha256"], digest(metadata))
    audit.equal("marker_input_inventory", marker["input_inventory_sha256"], digest(metadata["inputs_sha256"]))
    audit.equal("marker_pool_attestation", marker["pool_attestation_sha256"], digest(report["provenance"]["action_pool"]))
    refs, groups = load_inputs(audit, family, protocol)
    contexts = base.contexts_from(protocol)
    tables, latest, pool_counts = check_pool(audit, {"_effective": protocol}, metadata, manifest, report, refs, contexts, receipts)
    old = audit.read(ROOT / "g3/v33/L1_benchmark.json", base.ORIGINAL_REPORT_SHA)
    check_aggregates(audit, report, old, groups, tables, refs, protocol)
    audit.file(GRADE_PATH, GRADE_SHA)
    grade_counts = grade.check_runs(audit, groups)
    audit.final()
    audit.file(__file__, SELF_SHA)
    return {"groups": len(groups), "comparisons": len(report["comparisons"]), "raw_runs": sum(map(len, groups.values())),
            "contexts": len(refs), "pool": pool_counts, "grade_audit": grade_counts,
            "scope": "Independent receipt, source, seed-statistic, shared-MC, gate, fixed-EPS, observation-grade and update-population checks. No independent event-world simulation or physical network validation."}


def main(argv=None):
    global FAMILY_SHA
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--family-sha256", required=True)
    args = parser.parse_args(argv)
    if re.fullmatch(r"[0-9a-f]{64}", args.family_sha256) is None:
        raise ValueError("invalid family hash")
    FAMILY_SHA = args.family_sha256
    if args.out.exists():
        raise ValueError("checker output must be new")
    audit, error, summary = Audit(), None, None
    started, timer = dt.datetime.now(KST).isoformat(), time.monotonic()
    try:
        with completed_pool_lock():
            summary = verify(audit)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "last_check": audit.last_check}
    result = {"schema": "padfec.v33.j1_joint_artifact_check/1", "status": "pass" if error is None else "fail",
              "started_kst": started, "ended_kst": dt.datetime.now(KST).isoformat(), "elapsed_seconds": time.monotonic() - timer,
              "checks": audit.count, "summary": summary, "error": error, "files_sha256": audit.files,
              "script_sha256": SELF_SHA, "helper_sha256": BASE_SHA}
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: result[key] for key in ("status", "checks", "elapsed_seconds", "summary", "error")}, ensure_ascii=False))
    return 0 if error is None else 1


def check_pool(audit, plan, metadata, manifest, report, refs, contexts, receipts):
    attestation = report["provenance"]["action_pool"]
    execution_sha = digest(metadata)
    jobs = {job["job_id"]: job for job in manifest["jobs"]}
    family_size = manifest["evaluation_family_size"]
    audit.equal("job_count", len(jobs), family_size)
    audit.equal("pool_no_failure_files", list((POOL / "failures").glob("*.json")), [])
    audit.equal("result_inventory", sorted(path.stem for path in (POOL / "results").glob("*.json")), sorted(jobs))
    run_starts = {path.name.removesuffix(".started.json"): path for path in (POOL / "runs").glob("*.started.json")}
    run_ends = {path.name.removesuffix(".finished.json"): path for path in (POOL / "runs").glob("*.finished.json")}
    audit.equal("run_pair_inventory", sorted(run_starts), sorted(run_ends))
    audit.check("run_receipts_present", bool(run_starts))
    audit.equal("run_receipt_file_inventory", len(list((POOL / "runs").glob("*.json"))), 2 * len(run_starts))
    run_values = {}
    for run_id in sorted(run_starts):
        audit.check("run_filename:" + run_id, re.fullmatch(STAMP, run_id) is not None)
        start, end = audit.read(run_starts[run_id]), audit.read(run_ends[run_id])
        for phase, value in (("start", start), ("end", end)):
            for key, expected in (("schema", "padfec.v33.action_pool/1"), ("run_id", run_id), ("execution_sha256", execution_sha)):
                audit.equal("run:" + run_id + phase + key, value[key], expected)
        audit.equal("run_adapter:" + run_id, start["adapter_sha256"], metadata["adapter_sha256"])
        audit.equal("run_workers:" + run_id, start["workers"], 8)
        audit.equal("run_loop:" + run_id, start["loop"], True)
        audit.equal("restart_from_zero:" + run_id, start["resume"], False)
        audit.equal("cost_chunk_budget:" + run_id, start["time_budget_seconds"], 300.0)
        audit.equal("run_full_family:" + run_id, end["evaluation_family_size"], family_size)
        audit.equal("run_failed_jobs:" + run_id, end["failed_jobs"], [])
        audit.equal("run_partition:" + run_id, sorted(end["complete_jobs"] + end["pending_jobs"]), sorted(jobs))
        audit.equal("run_status:" + run_id, end["status"], "partial" if end["pending_jobs"] else "complete")
        audit.check("run_time:" + run_id, start["started_ns"] < end["finished_ns"])
        driver_start, driver_end = receipts["run"]
        audit.check("run_within_driver:" + run_id,
                    int(dt.datetime.fromisoformat(driver_start["started_kst"]).timestamp() * 1e9) <= start["started_ns"]
                    <= end["finished_ns"] <= int(dt.datetime.fromisoformat(driver_end["ended_kst"]).timestamp() * 1e9))
        run_values[run_id] = start, end
    latest = run_values[max(run_values)][1]
    audit.equal("latest_run_complete", latest["status"], "complete")
    audit.equal("latest_no_pending", latest["pending_jobs"], [])
    audit.equal("attested_run_ids", attestation["validated_run_ids"], sorted(run_values))
    defaults = audit.read(ROOT / "experiments/v33/worldparams.json")
    sources = {name: metadata["source_sha256"][name] for name in ("oracle.py", "worldsim.py", "worldparams.json")}
    tables, attempts, checkpoints = {}, set(), set()
    partition = {"mc": [], "structural": []}
    z = statistics.NormalDist().inv_cdf(1 - (1 - .99) / (2 * family_size))
    for job_id, job in jobs.items():
        starts = sorted((POOL / "attempts").glob(job_id + ".*.started.json"))
        ends = sorted((POOL / "attempts").glob(job_id + ".*.finished.json"))
        audit.equal("attempt_pair_inventory:" + job_id, [p.name.removesuffix(".started.json") for p in starts], [p.name.removesuffix(".finished.json") for p in ends])
        audit.check("attempt_present:" + job_id, bool(starts))
        previous, completed = None, False
        for start_path, end_path in zip(starts, ends):
            attempts.update((str(start_path), str(end_path)))
            audit.check("attempt_filename:" + start_path.name, re.fullmatch(re.escape(job_id) + r"\." + STAMP + r"\.started\.json", start_path.name) is not None)
            start, end = audit.read(start_path), audit.read(end_path)
            audit.check("no_attempt_after_complete:" + end_path.name, not completed)
            audit.equal("attempt_start_sha:" + end_path.name, end["started_sha256"], audit.file(start_path))
            audit.equal("checkpoint_chain:" + end_path.name, start["input_checkpoint_sha256"], previous)
            for phase, value in (("start", start), ("end", end)):
                for key, expected in (("schema", "padfec.v33.action_pool/1"), ("job", job), ("execution_sha256", execution_sha)):
                    audit.equal("attempt:" + end_path.name + phase + key, value[key], expected)
            for field in ("run_id", "pid", "started_ns"):
                audit.equal("attempt_pair:" + end_path.name + field, start[field], end[field])
            parent_start, parent_end = run_values[start["run_id"]]
            audit.check("attempt_time:" + end_path.name, parent_start["started_ns"] <= start["started_ns"] <= end["finished_ns"] <= parent_end["finished_ns"])
            audit.check("attempt_attested_success:" + end_path.name, end["status"] in ("partial", "complete") and not end.get("unattested", False))
            if end["status"] == "partial":
                audit.equal("partial_has_no_result:" + end_path.name, end["result_sha256"], None)
            previous, completed = end["checkpoint_sha256"], end["status"] == "complete"
        audit.check("completed_job:" + job_id, completed)
        path = POOL / "results" / (job_id + ".json")
        value = audit.read(path, end["result_sha256"])
        context, ref = contexts[job["context_id"]], refs[job["context_id"]]
        for key, expected in (("schema", "padfec.world_oracle/v1"), ("status", "complete"), ("context_id", job["context_id"]),
                              ("job_id", job_id), ("action", job["action"]), ("reference_action", job["reference_action"]),
                              ("evaluation_family_size", family_size), ("protocol_sha256", metadata["protocol_sha256"]),
                              ("validation_seed", 850001), ("source_hashes", sources), ("context", context["context"]),
                              ("mixture", ref["mixture"]), ("universe_count", ref["universe_count"]),
                              ("universe_sha256", ref["universe_sha256"]), ("world_params_sha256", digest(defaults))):
            audit.equal("result:" + job_id + key, value[key], expected)
        audit.equal("original_reference_action:" + job_id, job["reference_action"], ref["chosen_action"])
        audit.equal("default_world_override:" + job_id, context["world_params"], {})
        spec = {**plan["_effective"]["oracle"], "structural_certificates": True, "mixture": context["mixture"], "evaluation_family_size": family_size}
        spec["max_parity"] = spec.pop("m_max")
        audit.equal("result_spec:" + job_id, value["spec"], spec)
        structural = value["method"] == "structural_zero_loss_pair"
        audit.check("known_method:" + job_id, structural or value["method"] == "independent_paired_validation")
        partition["structural" if structural else "mc"].append(job_id)
        audit.equal("actual_n:" + job_id, value["n"], 0 if structural else N)
        audit.equal("declared_n:" + job_id, value["validation_samples"], 0 if structural else N)
        audit.equal("approximate:" + job_id, value["approximate"], not structural)
        if structural:
            audit.equal("structural_reference_method:" + job_id, ref["method"], "structural_zero_loss_certificate")
            audit.equal("structural_certificate:" + job_id, value["certificate"], ref["certificate"])
            audit.equal("structural_resolved:" + job_id, value["uncertainty_resolved"], True)
            audit.near("structural_gap_subtraction:" + job_id, value["mean_gap_ms"], value["mean_hct_ms"] - value["reference_mean_hct_ms"])
            audit.near("structural_width_zero:" + job_id, value["gap_half_width_ms"], 0)
        else:
            audit.equal("MC_confidence:" + job_id, value["confidence"], .99)
            audit.equal("evaluation_not_selection:" + job_id, value["evaluation_seed_must_not_have_selected_either_action"], True)
            se = math.sqrt(value["gap_variance_ms2"] / N)
            audit.near("MC_se:" + job_id, value["gap_se_ms"], se)
            zero = value["gap_variance_ms2"] <= 1e-20
            same = job["action"] == job["reference_action"]
            audit.equal("zero_variance_flag:" + job_id, value["zero_observed_variance"], zero)
            audit.equal("identity_flag:" + job_id, value["zero_variance_is_identity"], same)
            audit.equal("resolved_flag:" + job_id, value["uncertainty_resolved"], not (zero and not same))
            audit.near("MC_half_width:" + job_id, value["gap_half_width_ms"], None if zero and not same else z * se)
            if zero and not same:
                audit.equal("zero_distinct_null_ci:" + job_id, value["gap_ci_ms"], None)
            else:
                audit.near("MC_interval_lower:" + job_id, value["gap_ci_ms"][0], value["mean_gap_ms"] - z * se)
                audit.near("MC_interval_upper:" + job_id, value["gap_ci_ms"][1], value["mean_gap_ms"] + z * se)
        checkpoint_path = POOL / "checkpoints" / (job_id + ".json")
        if checkpoint_path.exists():
            checkpoints.add(job_id)
            checkpoint = audit.read(checkpoint_path, previous)
            audit.equal("checkpoint_schema:" + job_id, checkpoint["schema"], "padfec.world_oracle/v1")
            audit.equal("checkpoint_complete:" + job_id, checkpoint["status"], "complete")
            audit.equal("checkpoint_identity:" + job_id, checkpoint["identity"], digest({"kind": "evaluate_action", "context": context["context"],
                        "action": job["action"], "reference": job["reference_action"], "params": defaults, "spec": spec, "sources": sources}))
            audit.equal("checkpoint_connection_N:" + job_id, checkpoint["completed_connections"], N)
            for key, expected in checkpoint["report"].items():
                audit.equal("checkpoint_report:" + job_id + key, value[key], expected)
        else:
            audit.equal("missing_checkpoint_hash:" + job_id, previous, None)
            audit.check("missing_checkpoint_structural:" + job_id, structural)
        tables[job["context_id"], tuple(job["action"])] = value
    partition = {key: sorted(value) for key, value in partition.items()}
    audit.equal("complete_job_partition", sorted(partition["mc"] + partition["structural"]), sorted(jobs))
    audit.equal("structural_partition", partition["structural"], sorted(job_id for job_id, job in jobs.items() if refs[job["context_id"]]["method"] == "structural_zero_loss_certificate"))
    audit.equal("attempt_file_inventory", sorted(str(path) for path in (POOL / "attempts").glob("*.json")), sorted(attempts))
    audit.equal("checkpoint_file_inventory", sorted(path.stem for path in (POOL / "checkpoints").glob("*.json")), sorted(checkpoints))
    expected_attested = {str(POOL / name) for name in ("manifest.json", "execution.json")}
    expected_attested.update(str(path) for folder in ("runs", "attempts", "results", "checkpoints") for path in (POOL / folder).glob("*.json"))
    audit.equal("attested_file_inventory", sorted(attestation["files_sha256"]), sorted(expected_attested))
    audit.inventory(attestation["files_sha256"])
    return tables, latest, {"pool_runs": len(run_values), "attempt_pairs": len(attempts) // 2, "checkpoints": len(checkpoints),
                            "MC_jobs": len(partition["mc"]), "structural_jobs": len(partition["structural"])}


def check_observed_summary(audit, label, summary, values):
    present = [value for value in values if value is not None]
    complete = len(present) == len(values)
    audit.equal(label + ":expected_seed_count", summary["expected_seed_count"], len(values))
    audit.equal(label + ":observed_seed_count", summary["observed_seed_count"], len(present))
    audit.equal(label + ":complete", summary["complete"], complete)
    audit.equal(label + ":method", summary["method"], "two-sided Student t on independent seed means")
    if complete:
        check_seed_summary(audit, label, summary, present)
    else:
        audit.equal(label + ":n", summary["n"], 0)
        audit.equal(label + ":df", summary["df"], None)
        audit.equal(label + ":available", summary["interval_available"], False)
        audit.equal(label + ":confidence", summary["confidence"], .95)
        for field in ("mean", "sd", "se", "lower", "upper", "half_width"):
            audit.equal(label + ":" + field, summary[field], None)
        audit.check(label + ":critical_absent", "critical" not in summary)


def check_aggregates(audit, report, old_report, groups, tables, refs, protocol):
    old_groups = {(group["generation"].replace("current_", "l1_"), group["scenario"]): group for group in old_report["groups"]}
    actual = [(group["generation"], group["scenario"]) for group in report["groups"]]
    audit.equal("groups_inventory", sorted(actual), sorted(groups))
    audit.equal("group_count", len(actual), 150)
    for group in report["groups"]:
        key = group["generation"], group["scenario"]
        label = ":".join(key)
        runs = groups[key]
        expected = group["expected_regret"]
        audit.equal("group_seed_inventory:" + label, group["seeds"], protocol["seeds"])
        estimates, average = [], collections.defaultdict(Fraction)
        for run in runs:
            coefficients = weights(run)
            estimates.append(math.fsum(float(weight) * tables[action]["mean_gap_ms"] for action, weight in coefficients.items()))
            for action, weight in coefficients.items():
                average[action] += weight / len(runs)
        audit.equal("regret_seed_order:" + label, [item["seed"] for item in expected["seed_estimates"]], [run["seed"] for run in runs])
        for index, value in enumerate(estimates):
            audit.near("regret_seed:" + label + str(index), expected["seed_estimates"][index]["mean_gap_ms"], value)
        check_seed_summary(audit, "regret_summary:" + label, expected["seed_summary"], estimates)
        mc = bound(average, tables)
        context_weights = collections.defaultdict(Fraction)
        for (cid, _), weight in average.items():
            context_weights[cid] += weight
        selection = 0.0
        for cid, weight in context_weights.items():
            ref = refs[cid]
            if ref.get("uncertainty_resolved") is False or ref.get("selection_gap_upper_ms") is None:
                selection = None
                break
            selection += float(weight) * ref["selection_gap_upper_ms"]
        audit.near("regret_MC:" + label, expected["shared_mc_bound_ms"], mc)
        audit.near("regret_selection:" + label, expected["selection_gap_bound_ms"], selection)
        audit.near("regret_lower:" + label, expected["lower_bound_ms"], None if mc is None else expected["seed_summary"]["lower"] - mc)
        audit.near("regret_upper:" + label, expected["upper_bound_ms"], None if mc is None or selection is None else expected["seed_summary"]["upper"] + mc + selection)
        if group["family"] in ("B1", "B2"):
            check_gate(audit, "regret_gate:" + label, group["gates"]["regret"], expected["seed_summary"], mc, selection,
                       protocol["thresholds"][group["family"] + "_regret_ms"], False)
        for field, summary in group["observed"].items():
            check_observed_summary(audit, "observed_summary:" + label + field, summary, [run["summary"].get(field) for run in runs])
        if key in old_groups:
            for field in ("observed", "observation_diagnostics", "p_convergence"):
                audit.equal("unchanged_observation:" + label + field, group[field], old_groups[key][field])
        if group["family"] == "B4":
            check_gate(audit, "bytes_gate:" + label, group["gates"]["server_extra_bytes"], group["observed"]["mean_extra_server_bytes"], 0, 0, protocol["thresholds"]["B4_extra_bytes"], False)
    pairs = [("j1_" + mode, generation) for mode in ("none", "c1", "ideal") for generation in ("v32", "v31")]
    pairs += [("j1_c1", "j1_none")]
    pairs += [("j1_" + mode, "l1_" + mode) for mode in ("none", "c1", "ideal")]
    pairs += [("j1_" + mode, "cost_" + mode) for mode in ("none", "c1")]
    pairs += [("cost_" + mode, "l1_" + mode) for mode in ("none", "c1")]
    primary = {("j1_none", "l1_none"), ("j1_c1", "l1_c1")}
    expected_ids = sorted((a, b, scenario["id"]) for a, b in pairs for scenario in protocol["scenarios"])
    audit.equal("comparison_count", len(report["comparisons"]), 210)
    audit.equal("comparison_inventory", sorted((row["candidate"]["generation"], row["baseline"]["generation"], row["scenario"]) for row in report["comparisons"]), expected_ids)
    for row in report["comparisons"]:
        candidate, baseline, sid = row["candidate"]["generation"], row["baseline"]["generation"], row["scenario"]
        label = candidate + ":" + baseline + ":" + sid
        audit.equal("comparison_primary:" + label, row["primary"], (candidate, baseline) in primary)
        expected_kind = "tail_likelihood_contrast" if baseline.startswith("cost_") else "tail_cost_contrast" if candidate.startswith("cost_") else "direct_previous_policy" if baseline.startswith("l1_") else "legacy_or_mode_contrast"
        audit.equal("comparison_kind:" + label, row["kind"], expected_kind)
        audit.equal("comparison_privileged:" + label, row["ideal_is_privileged_diagnostic"], candidate.endswith("ideal") or baseline.endswith("ideal"))
        ca, ba = groups[candidate, sid], groups[baseline, sid]
        estimates, average = [], collections.defaultdict(Fraction)
        for c_run, b_run in zip(ca, ba):
            audit.equal("paired_seed:" + label + str(c_run["seed"]), c_run["seed"], b_run["seed"])
            cw, bw = weights(c_run), weights(b_run)
            context_c, context_b = collections.defaultdict(Fraction), collections.defaultdict(Fraction)
            for (cid, _), value in cw.items():
                context_c[cid] += value
            for (cid, _), value in bw.items():
                context_b[cid] += value
            audit.check("paired_context_weights:" + label + str(c_run["seed"]), context_c == context_b)
            difference = {key: cw.get(key, Fraction()) - bw.get(key, Fraction()) for key in set(cw) | set(bw)}
            estimates.append(math.fsum(float(weight) * tables[key]["mean_gap_ms"] for key, weight in difference.items() if weight))
            for key, weight in difference.items():
                average[key] += weight / len(ca)
        audit.equal("comparison_seed_order:" + label, [item["seed"] for item in row["seed_estimates"]], protocol["seeds"])
        for index, value in enumerate(estimates):
            audit.near("comparison_seed:" + label + str(index), row["seed_estimates"][index]["mean_delta_ms"], value)
        check_seed_summary(audit, "comparison_summary:" + label, row["seed_summary"], estimates)
        mc = bound(average, tables)
        audit.near("comparison_MC:" + label, row["shared_mc_bound_ms"], mc)
        audit.equal("oracle_cancels:" + label, row["oracle_cancels"], True)
        audit.near("comparison_selection:" + label, row["selection_gap_bound_ms"], 0)
        audit.near("comparison_lower:" + label, row["lower_bound_ms"], None if mc is None else row["seed_summary"]["lower"] - mc)
        audit.near("comparison_upper:" + label, row["upper_bound_ms"], None if mc is None else row["seed_summary"]["upper"] + mc)
        check_gate(audit, "comparison_gate:" + label, row["regression_gate"], row["seed_summary"], mc, 0,
                   protocol["thresholds"]["max_regression_vs_v31_ms"], True)
        realized = [c["summary"]["mean_hct_ms"] - b["summary"]["mean_hct_ms"] for c, b in zip(ca, ba)]
        check_seed_summary(audit, "realized_diagnostic:" + label, row["realized_hct_diagnostic"], realized)
    for candidate, baseline in pairs:
        cells = [row for row in report["comparisons"] if row["candidate"]["generation"] == candidate and row["baseline"]["generation"] == baseline]
        statuses = [row["regression_gate"]["status"] for row in cells]
        status = "fail" if "fail" in statuses else "pass" if statuses and all(value == "pass" for value in statuses) else "inconclusive"
        name = candidate + "_vs_" + baseline
        value = report["noninferiority"][name]
        audit.equal("noninferiority_status:" + name, value["status"], status)
        audit.equal("noninferiority_count:" + name, value["cell_count"], 15)
        audit.equal("noninferiority_expected_count:" + name, value["required_cell_count"], 15)
        audit.equal("noninferiority_all_cells:" + name, value["all_cells_present"], True)
        audit.equal("noninferiority_primary:" + name, value["primary"], (candidate, baseline) in primary)



if __name__ == "__main__":
    raise SystemExit(main())
