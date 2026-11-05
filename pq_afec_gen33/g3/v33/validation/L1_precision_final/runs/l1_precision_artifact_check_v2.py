import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import collections
from contextlib import contextmanager
import copy
import datetime as dt
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
PLAN = ROOT / "g3/v33/bench_overlays/L1_precision_v1.json"
EFFECTIVE = ROOT / "g3/v33/bench_overlays/L1_precision_v1_protocol.json"
POOL = RUNS / "L1_action_pool_precision_v2"
REPORT = ROOT / "g3/v33/L1_benchmark_precision_v1.json"
MARKDOWN = RUNS / "L1_precision_bench_v1.md"
MARKER = Path(str(REPORT) + ".published.json")
PLAN_MARKER = Path(str(PLAN) + ".published.json")
ORIGINAL_DRIVER = RUNS / "l1_precision_driver_v1.py"
DRIVER = RUNS / "l1_precision_driver_v2.py"
WRAPPER = ROOT / "experiments/v33/bench_learning_precision.py"
WRAPPER_SHA = "7abe1c7a18b4f3db53830f4946359917f7fa1b9997168f6a563f9288401a1446"
ORIGINAL_DRIVER_SHA = "a6d1b412d1f5851b4acb7253686d554259edb6ff258facee70ff05ef9e3b686f"
DRIVER_SHA = "0d8695096914b421835b2339795ec873bc4f2fd76d7f5a4ed224abe0995155ab"
PLAN_SHA = "f71d22fba623fd42a0ae9e906ede79372449e008e9669174888ba2a78975a4ff"
RECOVERY = RUNS / "L1_precision_interruption_v1.json"
RECOVERY_SHA = "dafd24775bd6ec9c00b79498307833b649dea5dfb4861c308a3f9f3493b4c8c5"
REPORTER_SHA = "9f480a41f456101e74461d2e8a3509625e3be148dda686eea752c1ce92a39c49"
ORIGINAL_FAMILY_SHA = "e315280cf0199ab36a77f2f8a6d5289bf80dc00553aae4b0599610e2a5ff5e35"
ORIGINAL_REPORT_SHA = "c89026795ce3e04fb35dfc19d4bf01d0700571fc7fae1330a6caa065dc5616cb"
ORIGINAL_PUBLICATION_SHA = "ae7bdc37e3a20c344799bceb0ee9b7c654ddd9a85335cd0a99fda2925082e37a"
ORIGINAL_PROTOCOL_SHA = "10cf3aa16b460054b533f03170b7c8718a21450eba39359525dbdba098583305"
SCHEMA = "padfec.v33.learning_precision_artifact_check/1"
STAMP = r"[0-9]{20}_[0-9a-f]{32}"
N = 1048576
ABS_TOL = 1e-10
REL_TOL = 1e-12
KST = dt.timezone(dt.timedelta(hours=9))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


INITIAL_SELF_SHA = file_hash(__file__)


class Audit:
    def __init__(self):
        self.checks = {}
        self.files = {}

    def check(self, name, condition):
        self.checks[name] = bool(condition)
        if not condition:
            raise ValueError(name)

    def equal(self, name, actual, expected):
        self.check(name, canonical(actual) == canonical(expected))

    def near(self, name, actual, expected):
        if actual is None or expected is None:
            self.equal(name, actual, expected)
            return
        self.check(name, type(actual) in (int, float) and math.isfinite(actual)
                   and math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL))

    def file(self, path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = file_hash(path)
        if str(path) in self.files:
            self.equal("stable:" + str(path), actual, self.files[str(path)])
        if expected is not None:
            self.equal("sha:" + str(path), actual, expected)
        self.files[str(path)] = actual
        return actual

    def read(self, path, expected=None):
        self.file(path, expected)
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        self.file(path)
        return value

    def inventory(self, values):
        self.check("nonempty_inventory:" + digest(values), isinstance(values, dict) and bool(values))
        for path, expected in values.items():
            self.equal("normalized:" + path, path, str(Path(path).resolve()))
            self.file(path, expected)

    def final(self):
        for path, expected in list(self.files.items()):
            self.file(path, expected)
        self.file(__file__, INITIAL_SELF_SHA)


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


def final_json_in_stream(path):
    text = Path(path).read_text(encoding="utf-8")
    decoder, position, result = json.JSONDecoder(), 0, None
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        result, position = decoder.raw_decode(text, position)
    if not isinstance(result, dict):
        raise ValueError("driver stdout has no final JSON object")
    return result


def preflight(audit):
    audit.file(WRAPPER, WRAPPER_SHA)
    audit.file(DRIVER, DRIVER_SHA)
    audit.file(ORIGINAL_DRIVER, ORIGINAL_DRIVER_SHA)
    receipts = {}
    for phase in ("plan", "run", "report"):
        stem = "L1_precision_" + phase + ("_v1" if phase == "plan" else "_v2")
        start_path, end_path = RUNS / (stem + ".started.json"), RUNS / (stem + ".finished.json")
        start, end = audit.read(start_path), audit.read(end_path)
        audit.equal("driver_complete:" + phase, end.get("status"), "complete")
        audit.equal("driver_exit_zero:" + phase, end.get("exit_code"), 0)
        audit.equal("driver_launch_error:" + phase, end.get("launch_error"), None)
        audit.check("driver_no_post_failure:" + phase, "post_validation_error" not in end)
        audit.equal("driver_start_sha:" + phase, end["started_receipt_sha256"], audit.file(start_path))
        for key in ("started_kst", "command", "inputs_sha256", "plan_identity", "preceding_run"):
            audit.equal("driver_start_end:" + phase + ":" + key, start[key], end[key])
        for key, expected in (("wrapper_sha256", WRAPPER_SHA), ("driver_sha256", ORIGINAL_DRIVER_SHA if phase == "plan" else DRIVER_SHA)):
            audit.equal("driver_start_source:" + phase + key, start[key], expected)
            audit.equal("driver_end_source:" + phase + key, end[key], expected)
            audit.equal("driver_after_source:" + phase + key, end[key + "_after"], expected)
        begin, finish = dt.datetime.fromisoformat(end["started_kst"]), dt.datetime.fromisoformat(end["ended_kst"])
        audit.check("driver_time:" + phase, begin.tzinfo is not None and finish >= begin)
        audit.check("driver_elapsed:" + phase, math.isfinite(end["elapsed_seconds"]) and end["elapsed_seconds"] >= 0)
        audit.inventory(end["inputs_sha256"])
        for channel in ("stdout", "stderr"):
            audit.equal("driver_log_path:" + phase + channel, end[channel + "_path"], str(RUNS / (stem + "." + channel + ".txt")))
            audit.file(end[channel + "_path"], end[channel + "_sha256"])
        receipts[phase] = (start, end)
    for left, right in (("plan", "run"), ("run", "report")):
        audit.check("driver_order:" + left + right,
                    dt.datetime.fromisoformat(receipts[left][1]["ended_kst"]) <= dt.datetime.fromisoformat(receipts[right][0]["started_kst"]))
    audit.check("published_marker_exists", MARKER.is_file() and PLAN_MARKER.is_file())
    return receipts


def driver_binding(audit, receipts, plan, marker, manifest, metadata, latest_run):
    recovery = audit.read(RECOVERY, RECOVERY_SHA)
    audit.equal("interruption_status", recovery["status"], "interrupted_unattested")
    audit.equal("interruption_plan", recovery["plan_sha256"], PLAN_SHA)
    audit.equal("restart_pool", recovery["restart_pool_path"], str(POOL))
    audit.equal("no_intermediate_performance_inspection", recovery["performance_inspected"], False)
    audit.check("original_root_completion_absent", not (RUNS / "L1_precision_run_v1.finished.json").exists())
    audit.inventory(recovery["files_sha256"])
    recovery_identity = {"path": str(RECOVERY), "sha256": RECOVERY_SHA,
                         "original_driver_path": str(ORIGINAL_DRIVER), "original_driver_sha256": ORIGINAL_DRIVER_SHA,
                         "rule": "restart same complete fixed plan from zero in new pool; no imported results or checkpoints"}
    for phase in ("run", "report"):
        for edge, value in zip(("start", "end"), receipts[phase]):
            audit.equal("recovery_link:" + phase + edge, value["recovery_identity"], recovery_identity)
    original = plan["original"]
    fixed_inputs = {original[key]: original[key.replace("path", "sha256")] for key in
                    ("family_path", "report_path", "publication_path", "decision_path")}
    plan_outputs = {str(path): audit.file(path) for path in (PLAN, PLAN_MARKER, EFFECTIVE)}
    identity = {"receipt_path": str(RUNS / "L1_precision_plan_v1.finished.json"),
                "receipt_sha256": audit.file(RUNS / "L1_precision_plan_v1.finished.json"),
                "outputs_sha256": plan_outputs, "wrapper_sha256": WRAPPER_SHA}
    preceding = {"path": str(RUNS / "L1_precision_run_v2.finished.json"),
                 "sha256": audit.file(RUNS / "L1_precision_run_v2.finished.json")}
    first_python = receipts["plan"][0]["command"][0]
    plan_args = ["--original-family", original["family_path"], "--original-family-sha256", ORIGINAL_FAMILY_SHA,
                 "--original-report", original["report_path"], "--decision", original["decision_path"],
                 "--effective-protocol", str(EFFECTIVE), "--out", str(PLAN)]
    common_args = ["--precision-plan", str(PLAN), "--precision-plan-sha256", audit.file(PLAN)]
    args = {"plan": plan_args,
            "run": common_args + ["--out", str(POOL), "--workers", "8", "--time-budget-seconds", "300", "--loop"],
            "report": common_args + ["--pool", str(POOL), "--out", str(REPORT), "--markdown", str(MARKDOWN)]}
    expected_outputs = {"plan": plan_outputs, "run": {}, "report": {str(path): audit.file(path) for path in (REPORT, MARKER, MARKDOWN)}}
    for phase in ("plan", "run", "report"):
        _, end = receipts[phase]
        audit.equal("driver_exact_command:" + phase, end["command"], [first_python, "-I", "-B", str(WRAPPER), phase] + args[phase])
        audit.equal("driver_exact_inputs:" + phase, end["inputs_sha256"], fixed_inputs)
        audit.equal("driver_plan_identity:" + phase, end["plan_identity"], None if phase == "plan" else identity)
        audit.equal("driver_preceding_run:" + phase, end["preceding_run"], preceding if phase == "report" else None)
        audit.equal("driver_outputs:" + phase, end["published_outputs_sha256"], expected_outputs[phase])
        stdout = final_json_in_stream(end["stdout_path"])
        audit.equal("driver_stdout_complete:" + phase, stdout["status"], "complete")
        audit.equal("driver_stdout_family:" + phase, stdout["evaluation_family_size"], 100)
        if phase == "run":
            audit.equal("driver_run_stdout_matches_pool", stdout, latest_run)
        else:
            target = PLAN if phase == "plan" else REPORT
            audit.equal("driver_stdout_target:" + phase, stdout["out"], str(target))
            audit.equal("driver_stdout_sha:" + phase, stdout["sha256"], audit.file(target))
            audit.equal("driver_stdout_marker:" + phase, stdout["publication_receipt"], str(target) + ".published.json")
        if phase == "plan":
            audit.equal("driver_stdout_fixed_contract", stdout["contract"], plan["contract"])
            audit.equal("driver_stdout_effective_sha", stdout["effective_protocol_sha256"], audit.file(EFFECTIVE))
    publication_ns = marker["published_ns"]
    start, end = receipts["report"]
    audit.check("publication_inside_report_process",
                int(dt.datetime.fromisoformat(start["started_kst"]).timestamp() * 1e9) <= publication_ns
                <= int(dt.datetime.fromisoformat(end["ended_kst"]).timestamp() * 1e9))


def contexts_from(protocol):
    result = {}
    for scenario in protocol["scenarios"]:
        for phase in scenario["phases"]:
            value = {"context": {**scenario["context"], **{k: v for k, v in phase.items() if k != "length"}},
                     "world_params": scenario["world_params"], "mixture": scenario.get("mixture", [])}
            key = digest(value)[:20]
            if key in result and result[key] != value:
                raise ValueError("context collision")
            result[key] = value
    return result


def load_raw_and_references(audit, original_family, original_report, protocol, manifest):
    imported = original_report["provenance"]["learning_inputs"]["import_receipt"]
    refs = {}
    for item in imported["provenance"]["result_files"]:
        value = audit.read(item["path"], item["sha256"])
        cid = value["context_id"]
        audit.check("unique_reference:" + cid, cid not in refs)
        refs[cid] = value
        audit.equal("reference_complete:" + cid, value["status"], "complete")
        audit.equal("reference_original_protocol:" + cid, value["protocol_sha256"], ORIGINAL_PROTOCOL_SHA)
        audit.equal("reference_original_spec_N:" + cid, value["spec"]["validation_samples"], 131072)
        structural = value["method"] == "structural_zero_loss_certificate"
        audit.equal("reference_validation_N:" + cid, value["validation_samples"], 0 if structural else 131072)
        audit.equal("reference_digest:" + cid, digest(value), manifest["oracle_digests"][cid])
    audit.equal("original_reference_lineage", imported["reference_digests"], manifest["oracle_digests"])
    raw, current = [], []
    for item in imported["provenance"]["raw_summary_files"]:
        value = audit.read(item["path"], item["sha256"])
        if value["generation"] in ("v31", "v32") and value["variant"] == "full":
            raw.append(value)
    audit.equal("baseline_run_count", len(raw), 600)
    for folder in original_family["raw_dirs"]:
        folder = Path(folder)
        shard = audit.read(folder / "manifest.json")
        audit.equal("current_shard_full:" + str(folder), shard["mode"], "full")
        for mode in shard["observation_modes"]:
            for sid in shard["scenarios"]:
                for seed in shard["seeds"]:
                    path = folder / mode / sid / f"seed{seed:05d}.json"
                    value = audit.read(path)
                    for field, expected in (("observation_mode", mode), ("scenario", sid), ("seed", seed),
                                            ("generation", "current"), ("status", "complete"), ("mode", "full")):
                        audit.equal("current_raw:" + str(path) + field, value[field], expected)
                    current.append({**value, "generation": "current_" + mode})
    audit.equal("current_run_count", len(current), 900)
    raw += current
    expected = sorted((name, "full", scenario["id"], seed) for name in
                      ("v31", "v32", "current_none", "current_c1", "current_ideal")
                      for scenario in protocol["scenarios"] for seed in protocol["seeds"])
    actual = [(run["generation"], run["variant"], run["scenario"], run["seed"]) for run in raw]
    audit.equal("unique_raw_identities", len(actual), len(set(actual)))
    audit.equal("raw_complete_identity_inventory", sorted(actual), expected)
    audit.equal("manifest_raw_identities", manifest["raw_run_identities"], [list(row) for row in expected])
    scenarios = {row["id"]: row for row in protocol["scenarios"]}
    union = set()
    groups = collections.defaultdict(list)
    for run in raw:
        label = f'{run["generation"]}:{run["scenario"]}:{run["seed"]}'
        audit.equal("raw_length:" + label, run["n"], sum(phase["length"] for phase in scenarios[run["scenario"]]["phases"]))
        audit.equal("action_denominator:" + label, sum(row["n"] for row in run["action_counts"]), run["n"])
        audit.file(run["trace_path"], run["trace_sha256"])
        for row in run["action_counts"]:
            if row["n"] > 0:
                union.add((row["context_id"], tuple(row["action"])))
        groups[run["generation"], run["scenario"]].append(run)
    for runs in groups.values():
        runs.sort(key=lambda row: row["seed"])
    audit.equal("full_action_union", sorted(union), sorted((job["context_id"], tuple(job["action"])) for job in manifest["jobs"]))
    audit.equal("action_union_count", len(union), 100)
    return refs, groups


def check_pool(audit, plan, metadata, manifest, report, refs, contexts, receipts):
    attestation = report["provenance"]["action_pool"]
    execution_sha = digest(metadata)
    jobs = {job["job_id"]: job for job in manifest["jobs"]}
    audit.equal("job_count", len(jobs), 100)
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
        audit.equal("fixed_chunk_budget:" + run_id, start["time_budget_seconds"], 300)
        audit.equal("run_full_family:" + run_id, end["evaluation_family_size"], 100)
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
    z = statistics.NormalDist().inv_cdf(1 - (1 - .99) / (2 * 100))
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
        for key, expected in (("schema", "padfec.v33.oracle/1"), ("status", "complete"), ("context_id", job["context_id"]),
                              ("job_id", job_id), ("action", job["action"]), ("reference_action", job["reference_action"]),
                              ("evaluation_family_size", 100), ("protocol_sha256", metadata["protocol_sha256"]),
                              ("validation_seed", 850001), ("source_hashes", sources), ("context", context["context"]),
                              ("mixture", ref["mixture"]), ("universe_count", ref["universe_count"]),
                              ("universe_sha256", ref["universe_sha256"]), ("world_params_sha256", digest(defaults))):
            audit.equal("result:" + job_id + key, value[key], expected)
        audit.equal("original_reference_action:" + job_id, job["reference_action"], ref["chosen_action"])
        audit.equal("default_world_override:" + job_id, context["world_params"], {})
        spec = {**plan["_effective"]["oracle"], "structural_certificates": True, "mixture": context["mixture"], "evaluation_family_size": 100}
        spec["max_parity"] = spec.pop("m_max")
        audit.equal("result_spec:" + job_id, value["spec"], spec)
        structural = value["method"] == "structural_zero_loss_pair"
        audit.check("known_method:" + job_id, structural or value["method"] == "independent_paired_validation")
        partition["structural" if structural else "mc"].append(job_id)
        audit.equal("actual_n:" + job_id, value["n"], 0 if structural else N)
        audit.equal("declared_n:" + job_id, value["validation_samples"], 0 if structural else N)
        audit.equal("approximate:" + job_id, value["approximate"], not structural)
        if structural:
            old_path = Path(plan["original"]["pool_path"]) / "results" / (job_id + ".json")
            old = audit.read(old_path, metadata["inputs_sha256"][str(old_path)])
            audit.equal("same_structural_method:" + job_id, old["method"], value["method"])
            audit.equal("same_structural_certificate:" + job_id, value["certificate"], old["certificate"])
            audit.equal("structural_resolved:" + job_id, value["uncertainty_resolved"], True)
            audit.near("structural_gap_unchanged:" + job_id, value["mean_gap_ms"], old["mean_gap_ms"])
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
    audit.equal("MC_job_count", len(partition["mc"]), 84)
    audit.equal("structural_job_count", len(partition["structural"]), 16)
    audit.equal("fixed_job_partition", partition, plan["result_partition"])
    audit.equal("attempt_file_inventory", sorted(str(path) for path in (POOL / "attempts").glob("*.json")), sorted(attempts))
    audit.equal("checkpoint_file_inventory", sorted(path.stem for path in (POOL / "checkpoints").glob("*.json")), sorted(checkpoints))
    expected_attested = {str(POOL / name) for name in ("manifest.json", "execution.json")}
    expected_attested.update(str(path) for folder in ("runs", "attempts", "results", "checkpoints") for path in (POOL / folder).glob("*.json"))
    audit.equal("attested_file_inventory", sorted(attestation["files_sha256"]), sorted(expected_attested))
    audit.inventory(attestation["files_sha256"])
    return tables, latest, {"pool_runs": len(run_values), "attempt_pairs": len(attempts) // 2, "checkpoints": len(checkpoints),
                            "MC_jobs": 84, "structural_jobs": 16}


def weights(run):
    values = collections.defaultdict(Fraction)
    for row in run["action_counts"]:
        if type(row["n"]) is not int or row["n"] < 0:
            raise ValueError("invalid action frequency")
        if row["n"]:
            values[row["context_id"], tuple(row["action"])] += Fraction(row["n"], run["n"])
    if sum(values.values(), Fraction()) != 1:
        raise ValueError("invalid action denominator")
    return values


def width(value):
    if value.get("uncertainty_resolved") is False or (value.get("zero_observed_variance") and value["action"] != value["reference_action"] and value.get("approximate", True)):
        return None
    return value["gap_half_width_ms"]


def bound(coefficients, tables):
    if any(width(tables[key]) is None for key, value in coefficients.items() if value):
        return None
    return math.fsum(abs(float(value)) * width(tables[key]) for key, value in coefficients.items() if value)


def t_cdf_positive(value, df):
    theta = math.atan(value / math.sqrt(df))
    power = df - 1
    integral = theta if power % 2 == 0 else math.sin(theta)
    for n in range(2 if power % 2 == 0 else 3, power + 1, 2):
        integral = math.sin(theta) * math.cos(theta) ** (n - 1) / n + (n - 1) / n * integral
    constant = math.exp(math.lgamma((df + 1) / 2) - math.lgamma(df / 2)) / math.sqrt(math.pi)
    return .5 + constant * integral


def check_seed_summary(audit, label, summary, values):
    audit.equal(label + ":n", summary["n"], 20)
    audit.equal(label + ":df", summary["df"], 19)
    audit.equal(label + ":confidence", summary["confidence"], .95)
    audit.equal(label + ":available", summary["interval_available"], True)
    mean, sd = statistics.mean(values), statistics.stdev(values)
    se = sd / math.sqrt(20)
    critical = summary["critical"]
    audit.check(label + ":positive_critical", critical > 0 and math.isfinite(critical))
    audit.near(label + ":critical_CDF", t_cdf_positive(critical, 19), .975)
    for key, expected in (("mean", mean), ("sd", sd), ("se", se), ("half_width", critical * se),
                          ("lower", mean - critical * se), ("upper", mean + critical * se)):
        audit.near(label + ":" + key, summary[key], expected)


def check_gate(audit, label, gate, summary, mc, selection, limit, inclusive):
    lower = None if mc is None else summary["lower"] - mc
    upper = None if mc is None or selection is None else summary["upper"] + mc + selection
    passed = upper is not None and (upper <= limit if inclusive else upper < limit)
    failed = lower is not None and (lower > limit if inclusive else lower >= limit)
    audit.equal(label + ":status", gate["status"], "pass" if passed else "fail" if failed else "inconclusive")
    for key, expected in (("estimate", summary["mean"]), ("lower", summary["lower"]), ("upper", summary["upper"]),
                          ("adjusted_lower", lower), ("adjusted_upper", upper), ("threshold", limit),
                          ("mc_bound", mc), ("selection_gap", selection)):
        audit.near(label + ":" + key, gate[key], expected)
    audit.equal(label + ":inclusive", gate["inclusive"], inclusive)
    audit.equal(label + ":absolute", gate["absolute"], False)
    audit.equal(label + ":point_pass", gate["point_pass"], summary["mean"] <= limit if inclusive else summary["mean"] < limit)


def check_aggregates(audit, report, old_report, groups, tables, refs, protocol):
    old_groups = {(group["generation"], group["scenario"]): group for group in old_report["groups"]}
    actual = [(group["generation"], group["scenario"]) for group in report["groups"]]
    audit.equal("groups_inventory", sorted(actual), sorted(groups))
    audit.equal("group_count", len(actual), 75)
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
        for field in ("observed", "observation_diagnostics", "p_convergence"):
            audit.equal("unchanged_observation:" + label + field, group[field], old_groups[key][field])
    pairs = [("current_" + mode, base) for mode in ("none", "c1", "ideal") for base in ("v32", "v31")]
    pairs.append(("current_c1", "current_none"))
    expected_ids = sorted((a, b, scenario["id"]) for a, b in pairs for scenario in protocol["scenarios"])
    audit.equal("comparison_count", len(report["comparisons"]), 105)
    audit.equal("comparison_inventory", sorted((row["candidate"]["generation"], row["baseline"]["generation"], row["scenario"]) for row in report["comparisons"]), expected_ids)
    for row in report["comparisons"]:
        candidate, baseline, sid = row["candidate"]["generation"], row["baseline"]["generation"], row["scenario"]
        label = candidate + ":" + baseline + ":" + sid
        audit.equal("comparison_primary:" + label, row["primary"], candidate == "current_c1" and baseline in ("v31", "v32"))
        audit.equal("comparison_privileged:" + label, row["ideal_is_privileged_diagnostic"], candidate == "current_ideal")
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
    for baseline, name in (("v32", "pre_post_vs_v32"), ("v31", "w1_noninferiority_vs_v31")):
        for mode in ("none", "c1", "ideal"):
            cells = [row for row in report["comparisons"] if row["candidate"]["generation"] == "current_" + mode and row["baseline"]["generation"] == baseline]
            statuses = [row["regression_gate"]["status"] for row in cells]
            status = "fail" if "fail" in statuses else "pass" if statuses and all(value == "pass" for value in statuses) else "inconclusive"
            value = report["noninferiority"][name][mode]
            audit.equal("noninferiority_status:" + name + mode, value["status"], status)
            audit.equal("noninferiority_count:" + name + mode, value["cell_count"], 15)
            audit.equal("noninferiority_expected_count:" + name + mode, value["required_cell_count"], 15)
            audit.equal("noninferiority_all_cells:" + name + mode, value["all_cells_present"], True)
            audit.equal("noninferiority_primary:" + name + mode, value["primary"], mode == "c1")
            audit.equal("noninferiority_privileged:" + name + mode, value["ideal_is_privileged_diagnostic"], mode == "ideal")


def check_markdown(audit, report, text):
    def number(value):
        return "미확정" if value is None else format(value, ".4f")
    expected = []
    for group in report["groups"]:
        regret = group["expected_regret"]
        summary = regret["seed_summary"]
        expected.append([group["generation"], group["scenario"], number(summary["mean"]),
                         "[" + number(summary["lower"]) + ", " + number(summary["upper"]) + "]",
                         number(regret["shared_mc_bound_ms"]), number(regret["selection_gap_bound_ms"]),
                         group["gates"].get("regret", {}).get("status", "해당 없음")])
    for item in report["comparisons"]:
        summary = item["seed_summary"]
        expected.append([item["candidate"]["generation"] + " - " + item["baseline"]["generation"], item["scenario"],
                         number(summary["mean"]), "[" + number(summary["lower"]) + ", " + number(summary["upper"]) + "]",
                         number(item["shared_mc_bound_ms"]), "[" + number(item["lower_bound_ms"]) + ", " + number(item["upper_bound_ms"]) + "]",
                         number(item["realized_hct_diagnostic"]["mean"]), item["regression_gate"]["status"]])
    for group in report["groups"]:
        observed, convergence = group["observed"], group["p_convergence"]
        expected.append([group["generation"], group["scenario"], number(observed["mean_hct_ms"]["mean"]),
                         number(observed["mean_extra_server_bytes"]["mean"]), number(observed["p_bias_high_phase"]["mean"]),
                         "해당 없음" if convergence is None else convergence["predecision_tail_gate"]["status"],
                         "해당 없음" if convergence is None else number(convergence["final_post_observation_p_mean"]["mean"]),
                         group["gates"].get("adaptation", {}).get("status", "해당 없음")])
    for group in report["groups"]:
        diagnostics = group["observation_diagnostics"]
        if diagnostics is None:
            continue
        counts = [sum(row["n"] for row in diagnostics["distributions"]["loss_update_kind"] if row["present"] and row["value"] == kind)
                  for kind in ("datagram", "categorical", "predict_only")]
        expected.append([group["observation_mode"], group["scenario"], str(diagnostics["connections"]), str(diagnostics["failures"]),
                         *map(str, counts), str(diagnostics["confirmed_all_lost_connections"]), str(diagnostics["unknown_all_lost_connections"])])
    actual, table = [], False
    for line in text.splitlines():
        if line.startswith("|---"):
            table = True
        elif table and line.startswith("| "):
            actual.append([cell.strip() for cell in line.strip("|").split("|")])
        else:
            table = False
    audit.equal("markdown_all_displayed_values", actual, expected)


def verify(audit):
    receipts = preflight(audit)
    with completed_pool_lock():
        plan = audit.read(PLAN, PLAN_SHA)
        plan_marker = audit.read(PLAN_MARKER)
        report, marker = audit.read(REPORT), audit.read(MARKER)
        manifest, metadata = audit.read(POOL / "manifest.json"), audit.read(POOL / "execution.json")
        original = plan["original"]
        for key, expected in (("family_sha256", ORIGINAL_FAMILY_SHA), ("report_sha256", ORIGINAL_REPORT_SHA),
                              ("publication_sha256", ORIGINAL_PUBLICATION_SHA)):
            audit.equal("original_pinned:" + key, original[key], expected)
        old_family = audit.read(original["family_path"], ORIGINAL_FAMILY_SHA)
        old_report = audit.read(original["report_path"], ORIGINAL_REPORT_SHA)
        audit.read(original["publication_path"], ORIGINAL_PUBLICATION_SHA)
        audit.file(original["decision_path"], original["decision_sha256"])
        base = audit.read(plan["base_protocol_path"], ORIGINAL_PROTOCOL_SHA)
        effective = audit.read(EFFECTIVE, plan["effective_protocol_sha256"])
        expected_protocol = copy.deepcopy(base)
        expected_protocol["oracle"]["validation_samples"] = N
        audit.equal("only_N_changed", effective, expected_protocol)
        audit.equal("original_N", base["oracle"]["validation_samples"], 131072)
        audit.equal("seed_unchanged", effective["oracle"]["validation_seed"], 850001)
        audit.equal("base_protocol_identity", plan["base_protocol_sha256"], ORIGINAL_PROTOCOL_SHA)
        audit.equal("effective_protocol_path", plan["effective_protocol_path"], str(EFFECTIVE))
        for key, expected in (("schema", "padfec.v33.learning_precision_plan/1"), ("wrapper_sha256", WRAPPER_SHA), ("reporter_sha256", REPORTER_SHA)):
            audit.equal("plan:" + key, plan[key], expected)
        for key, expected in (("validation_samples", N), ("original_validation_samples", 131072), ("validation_seed", 850001),
                              ("confidence", .99), ("evaluation_family_size", 100), ("mc_job_count", 84), ("structural_job_count", 16),
                              ("reference_count", 19), ("baseline_run_count", 600), ("current_run_count", 900),
                              ("allowed_protocol_changes", ["oracle.validation_samples"]), ("recompute_from_connection", 0),
                              ("reuse_original_checkpoints", False), ("additional_simultaneous_coverage_claim", False)):
            audit.equal("fixed_contract:" + key, plan["contract"][key], expected)
        expected_manifest = copy.deepcopy(old_family["manifest"])
        expected_manifest["protocol_sha256"] = audit.file(EFFECTIVE)
        audit.equal("manifest_original_jobs_and_references", manifest, expected_manifest)
        audit.equal("plan_manifest", plan["manifest"], manifest)
        audit.equal("reference_lineage", plan["reference_lineage"], {"protocol_sha256": ORIGINAL_PROTOCOL_SHA,
                    "oracle_digests": old_family["manifest"]["oracle_digests"], "retagged": False, "reevaluated": False})
        expected_plan_marker = {"schema": "padfec.v33.learning_precision_plan_publication/1", "status": "complete",
                                "precision_plan_path": str(PLAN), "precision_plan_sha256": audit.file(PLAN),
                                "wrapper_sha256": WRAPPER_SHA, "artifacts_sha256": {str(PLAN): audit.file(PLAN), str(EFFECTIVE): audit.file(EFFECTIVE)},
                                "input_inventory_sha256": digest(plan["inputs_sha256"]), "original_publication_sha256": ORIGINAL_PUBLICATION_SHA}
        audit.equal("plan_publication", {k: v for k, v in plan_marker.items() if k != "published_ns"}, expected_plan_marker)
        audit.check("plan_publication_time", type(plan_marker["published_ns"]) is int and plan_marker["published_ns"] > 0)
        audit.inventory(plan["inputs_sha256"])
        expected_inputs = {**plan["inputs_sha256"], str(PLAN): audit.file(PLAN), str(PLAN_MARKER): audit.file(PLAN_MARKER)}
        audit.equal("execution_input_inventory", metadata["inputs_sha256"], expected_inputs)
        audit.equal("plan_no_self_reference", str(PLAN) in plan["inputs_sha256"] or str(PLAN_MARKER) in plan["inputs_sha256"], False)
        expected_plan_inputs = {**old_family["inputs_sha256"], **old_report["provenance"]["action_pool"]["files_sha256"],
                               **audit.read(original["publication_path"])["artifacts_sha256"],
                               original["family_path"]: ORIGINAL_FAMILY_SHA, original["publication_path"]: ORIGINAL_PUBLICATION_SHA,
                               original["decision_path"]: original["decision_sha256"], str(WRAPPER): WRAPPER_SHA, str(EFFECTIVE): audit.file(EFFECTIVE)}
        audit.equal("complete_original_input_lineage", plan["inputs_sha256"], expected_plan_inputs)
        audit.equal("report_learning_input_lineage", report["provenance"]["learning_inputs"], old_report["provenance"]["learning_inputs"])
        for key, expected in (("protocol_path", str(EFFECTIVE)), ("protocol_sha256", audit.file(EFFECTIVE)),
                              ("base_protocol_sha256", ORIGINAL_PROTOCOL_SHA), ("family_plan_path", str(PLAN)),
                              ("family_plan_sha256", audit.file(PLAN)), ("manifest_sha256", digest(manifest)),
                              ("precision_schema", plan["schema"]), ("precision_contract", plan["contract"]),
                              ("wrapper_sha256", WRAPPER_SHA), ("reporter_sha256", REPORTER_SHA), ("original", original),
                              ("reference_lineage", plan["reference_lineage"]), ("result_partition", plan["result_partition"])):
            audit.equal("execution:" + key, metadata[key], expected)
        audit.equal("report_scope", report["precision_scope"], plan["contract"])
        audit.equal("report_primary_mode", report["primary_mode"], "c1")
        audit.equal("report_aliases", report["analysis_aliases"], plan["analysis_aliases"])
        audit.equal("report_comparison_plan", report["comparison_plan"], plan["comparisons"])
        audit.equal("report_schema", report["schema"], "padfec.v33.learning_precision_report/1")
        for key, expected in (("status", "complete"), ("missing", []), ("missing_raw_groups", []), ("evaluation_family_size", 100)):
            audit.equal("report:" + key, report[key], expected)
        provenance = report["provenance"]
        for key, expected in (("precision_plan_path", str(PLAN)), ("precision_plan_sha256", audit.file(PLAN)),
                              ("wrapper_sha256", WRAPPER_SHA), ("reporter_sha256", REPORTER_SHA), ("original", original),
                              ("base_protocol_sha256", ORIGINAL_PROTOCOL_SHA), ("evaluation_protocol_path", str(EFFECTIVE)),
                              ("evaluation_protocol_sha256", audit.file(EFFECTIVE)), ("reference_lineage", plan["reference_lineage"]),
                              ("result_partition", plan["result_partition"]), ("frozen_sources", plan["frozen_sources"])):
            audit.equal("report_provenance:" + key, provenance[key], expected)
        attestation = provenance["action_pool"]
        for key, expected in (("pool_path", str(POOL)), ("evaluation_family_size", 100),
                              ("execution_content_sha256", digest(metadata)), ("manifest_content_sha256", digest(manifest))):
            audit.equal("attestation:" + key, attestation[key], expected)
        for key, expected in (("schema", "padfec.v33.learning_precision_publication/1"), ("status", "complete"),
                              ("precision_plan_path", str(PLAN)), ("precision_plan_sha256", audit.file(PLAN)),
                              ("input_inventory_sha256", digest(expected_inputs)), ("pool_attestation_sha256", digest(attestation)),
                              ("execution_content_sha256", digest(metadata)), ("wrapper_sha256", WRAPPER_SHA),
                              ("reporter_sha256", REPORTER_SHA), ("original_publication_sha256", ORIGINAL_PUBLICATION_SHA)):
            audit.equal("publication:" + key, marker[key], expected)
        audit.equal("publication_artifact_inventory", sorted(marker["artifacts_sha256"]), sorted([str(REPORT), str(MARKDOWN)]))
        audit.inventory(marker["artifacts_sha256"])
        for name, sha in plan["frozen_sources"].items():
            audit.file(ROOT / "experiments/v33" / name, sha)
        audit.equal("frozen_sources_original", plan["frozen_sources"], old_report["provenance"]["frozen_sources"])
        audit.file(ROOT / "experiments/v33/bench_learning_report.py", REPORTER_SHA)
        audit.equal("adapter_source", metadata["adapter_sha256"], plan["frozen_sources"]["bench_action_pool.py"])
        audit.equal("producer_sources", metadata["source_sha256"], manifest["source_sha256"])
        contexts = contexts_from(base)
        audit.equal("contexts_unchanged", contexts_from(effective), contexts)
        audit.equal("contexts_count", len(contexts), 19)
        audit.equal("contexts_digest", metadata["contexts_sha256"], digest(contexts))
        audit.equal("plan_contexts_digest", plan["contexts_sha256"], digest(contexts))
        refs, groups = load_raw_and_references(audit, old_family, old_report, base, manifest)
        audit.equal("references_inventory", sorted(refs), sorted(contexts))
        pool_plan = {**plan, "_effective": effective}
        tables, latest_run, counts = check_pool(audit, pool_plan, metadata, manifest, report, refs, contexts, receipts)
        driver_binding(audit, receipts, plan, marker, manifest, metadata, latest_run)
        check_aggregates(audit, report, old_report, groups, tables, refs, base)
        text = MARKDOWN.read_text(encoding="utf-8")
        check_markdown(audit, report, text)
        for required in ("독립 재현", "1048576", "84개 MC", "16개 구조적", "seed별 기대 차이", "비열등 통과는 개선 입증"):
            audit.check("markdown_scope:" + required, required in text)
        row_counts, count = [], 0
        for line in text.splitlines():
            if line.startswith("|---"):
                count = 0
            elif line.startswith("| "):
                count += 1
            elif count:
                row_counts.append(count)
                count = 0
        if count:
            row_counts.append(count)
        audit.equal("markdown_table_rows", row_counts, [75, 105, 75, 45])
        audit.final()
        return {**counts, "raw_seed_runs": 1500, "references": 19, "family": 100, "MC_N": N,
                "groups": 75, "comparisons": 105, "markdown_table_rows": row_counts,
                "regression_status_counts": dict(collections.Counter(row["regression_gate"]["status"] for row in report["comparisons"]))}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=RUNS / "L1_precision_artifact_check.json")
    parser.add_argument("--review", type=Path, default=RUNS / "L1_precision_artifact_review.md")
    args = parser.parse_args(argv)
    if args.out.exists() or args.review.exists() or args.out.resolve() == args.review.resolve():
        raise FileExistsError("artifact verification outputs must be distinct new files")
    audit, counts, error = Audit(), None, None
    try:
        counts = verify(audit)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    stable_script = file_hash(__file__) == INITIAL_SELF_SHA
    result = {"schema": SCHEMA, "status": "pass" if error is None and stable_script else "fail",
              "verified_kst": dt.datetime.now(KST).isoformat(), "script_path": str(Path(__file__).resolve()),
              "script_sha256": INITIAL_SELF_SHA, "script_sha256_after": file_hash(__file__),
              "checks": audit.checks, "error": error, "counts": counts,
              "verified_files_sha256": dict(sorted(audit.files.items())),
              "numeric_tolerances": {"absolute": ABS_TOL, "relative": REL_TOL},
              "scope": "standard-library provenance and independent action-weighted expectation/seed interval/MC-bound checks; no product imports, policy execution, tests or MC",
              "not_recomputed": ["raw per-connection learner updates", "B5 adaptation and near-optimal episodes", "oracle selection proof"],
              "performance_scope": "artifact integrity pass is separate from performance pass/fail/inconclusive; no independent replication claim"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    lines = ["# L1 정밀화 최종 아티팩트 검증", "", f'검증 상태: {result["status"]}. 시각: {result["verified_kst"]}.', "",
             f'검사기 SHA: {INITIAL_SELF_SHA}. 결과 JSON SHA: {file_hash(args.out)}.', "",
             "검사기는 plan/run/report driver receipt와 발행 marker가 모두 성공일 때만 새 pool 잠금 안으로 진행한다. 실패 시 실제 수행 범위는 결과 JSON의 checks에 남는다. "
             "원형 raw·참조, 원래 protocol과 평가 protocol의 N 한 필드 차이, 새 전체 행동 결과와 발행 지문을 대조한다.", "",
             "기대 차이와 seed 통계, 공통 MC 폭·선택 오차·직접 비교 gate는 표준 라이브러리로 독립 계산한다. "
             "Student t 임계값은 정수 자유도의 밀도 적분 재귀식으로 CDF를 확인한다. "
             "연결별 학습 갱신, B5 적응/episode, 참조 선택 증명은 재계산하지 않았다.", "",
             "아티팩트 무결성의 pass는 성능 통과나 L1 완료를 뜻하지 않는다. 같은 seed prefix의 사후 개발 정밀화 범위를 유지한다.", "",
             "```json", json.dumps({"counts": counts, "error": error}, ensure_ascii=False, indent=2), "```", ""]
    args.review.parent.mkdir(parents=True, exist_ok=True)
    with args.review.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    print(json.dumps({"status": result["status"], "checks": len(audit.checks), "error": error,
                      "out": str(args.out.resolve()), "out_sha256": file_hash(args.out),
                      "review": str(args.review.resolve()), "review_sha256": file_hash(args.review)}, ensure_ascii=False, indent=2), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
