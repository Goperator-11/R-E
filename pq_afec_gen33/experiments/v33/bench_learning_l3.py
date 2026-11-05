import sys
sys.dont_write_bytecode = True
import argparse
import collections
import gzip
import io
import json
import math
from pathlib import Path
import time
import traceback


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_action_pool as pool, bench_oracles, bench_report
from experiments.v33.bench_metrics import summarize_run
from experiments.v33.first_flight_observer import make_world_evidence
from experiments.v33.policy_worker import first_flight_evidence


SCHEMA = "padfec.v33.learning_benchmark/3"
RAW_SCHEMA = "padfec.v33.learning_raw/3"
IMPORT_SCHEMA = "padfec.v33.learning_import/3"
MODES = ("none", "c1", "ideal")
PACKAGES = ("afec", "padfec", "padfec3")
SOURCE_NAMES = ("bench_learning_l3.py", "first_flight_observer.py", "bench.py", "bench_metrics.py",
                "policy_worker.py", "worldsim.py", "worldparams.json", "oracle.py",
                "bench_oracles.py", "bench_action_pool.py", "bench_report.py")
OBSERVER = {"feedback_loss": "context.s2c_loss_when_world_feature_enabled",
            "receiver_limit": "world.params.server.decoder_max_datagram_bytes",
            "feedback_grace_ms": 200, "crc_list_limit": 64, "passive": True}
COMPARISONS = [[mode, generation] for mode in MODES for generation in ("v32", "v31")] + [["c1", "none"]]
IMPORTED_SOURCES = {name: bench.file_hash(Path(__file__).with_name(name)) for name in SOURCE_NAMES}


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def equal(actual, expected, name):
    if actual != expected:
        raise ValueError(f"{name} differs")


def sources():
    return {name: bench.file_hash(Path(__file__).with_name(name)) for name in SOURCE_NAMES}


def inventory(root):
    root = Path(root).resolve(strict=True)
    files = {}
    for package in PACKAGES:
        if not (root / package / "__init__.py").is_file():
            raise ValueError("incomplete policy snapshot")
        for path in sorted((root / package).rglob("*.py")):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("policy source escapes snapshot")
            files[path.relative_to(root).as_posix()] = bench.file_hash(path)
    return {"source_root": str(root), "files": files}


def snapshot_identity(root, receipt_path, original_root=None):
    root, receipt_path = Path(root).resolve(), Path(receipt_path).resolve()
    receipt = read_json(receipt_path)
    equal(receipt.get("schema"), "padfec.v33.policy_snapshot/1", "snapshot schema")
    equal(receipt.get("source_and_snapshot_byte_identical"), True, "snapshot byte identity")
    equal(Path(receipt["snapshot_root"]).resolve(), root, "snapshot root")
    variants = {
        "full": {"enabled": True, "beta": True, "shared": True, "c1_reeval": False},
        "guard_only": {"enabled": False, "beta": False, "shared": False, "c1_reeval": True},
        "record_only": {"enabled": True, "beta": False, "shared": False, "c1_reeval": False},
        "beta_only": {"enabled": True, "beta": True, "shared": False, "c1_reeval": False}}
    if receipt.get("monitor_variant") not in variants:
        raise ValueError("L3 snapshot must declare monitor variant")
    equal(receipt.get("monitor_config"), variants[receipt["monitor_variant"]], "monitor variant configuration")
    fingerprint = inventory(root)
    equal(fingerprint["files"], receipt["files"], "snapshot complete source inventory")
    if original_root is not None:
        equal(Path(receipt["source_root"]).resolve(), Path(original_root).resolve(), "snapshot origin")
        equal(inventory(original_root)["files"], fingerprint["files"], "snapshot original bytes")
        if Path(original_root).resolve() == root:
            raise ValueError("snapshot must have a separate immutable source root")
    return {"fingerprint": fingerprint, "receipt_path": str(receipt_path),
            "receipt_sha256": bench.file_hash(receipt_path), "policy_version": "v3.3-dev", "state_version": 6,
            "monitor_variant": receipt["monitor_variant"], "monitor_config": receipt["monitor_config"]}


def expected_baseline_ids(protocol):
    return {(generation, "full", scenario["id"], seed) for generation in ("v31", "v32")
            for scenario in protocol["scenarios"] for seed in protocol["seeds"]}


def run_identity(run):
    return run["generation"], run["variant"], run["scenario"], run["seed"]


def import_w1(protocol_path, raw_dirs, oracle_dirs, rules_path):
    protocol, raw, refs, tables, provenance, pending = bench_report.load_inputs(
        protocol_path, raw_dirs, oracle_dirs, [], rules_path)
    if pending or tables:
        raise ValueError("all original oracle references must be complete")
    identities = [run_identity(run) for run in raw]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate imported baseline run")
    equal(set(identities), expected_baseline_ids(protocol), "entire v31/v32 full baseline")
    equal(set(refs), set(bench.all_contexts(protocol)), "entire reference universe")
    reference_ids = [job["context_id"] for folder in oracle_dirs
                     for job in read_json(Path(folder) / "manifest.json")["jobs"]]
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError("reference directories overlap")
    files = {}
    for key in ("raw_manifests", "raw_summary_files", "raw_trace_files", "oracle_manifests", "result_files"):
        for item in provenance[key]:
            path = str(Path(item["path"]).resolve())
            if path in files and files[path] != item["sha256"]:
                raise ValueError("conflicting imported file hash")
            files[path] = item["sha256"]
    receipt = {"schema": IMPORT_SCHEMA, "protocol_path": str(Path(protocol_path).resolve()),
               "protocol_sha256": bench.file_hash(protocol_path),
               "rules_path": str(Path(rules_path).resolve()), "rules_sha256": bench.file_hash(rules_path),
               "raw_dirs": [str(Path(path).resolve()) for path in raw_dirs],
               "oracle_dirs": [str(Path(path).resolve()) for path in oracle_dirs],
               "contexts_sha256": bench.digest(bench.all_contexts(protocol)),
               "baseline_identities": [list(item) for item in sorted(identities)],
               "reference_digests": {cid: bench.digest(value) for cid, value in refs.items()},
               "files_sha256": files, "provenance": provenance,
               "validator_source_sha256": sources()}
    return protocol, raw, refs, receipt


def freeze_overlay(protocol_path, raw_dirs, oracle_dirs, policy_root, snapshot_receipt,
                   out, import_receipt_path, rules_path=bench_report.RULES, original_source_root=None):
    protocol, raw, refs, receipt = import_w1(protocol_path, raw_dirs, oracle_dirs, rules_path)
    policy = snapshot_identity(policy_root, snapshot_receipt, original_source_root or protocol["generations"]["current"]["source_root"])
    equal(sources(), IMPORTED_SOURCES, "imported producer sources")
    bench.write_new(Path(import_receipt_path), receipt)
    overlay = {"schema": SCHEMA, "base_protocol_path": str(Path(protocol_path).resolve()),
               "base_protocol_sha256": bench.file_hash(protocol_path), "source_sha256": sources(),
               "policy": policy, "modes": list(MODES), "observer": OBSERVER,
               "comparisons": COMPARISONS, "primary_mode": "c1", "ideal_is_privileged_diagnostic": True,
               "import_receipt_path": str(Path(import_receipt_path).resolve()),
               "import_receipt_sha256": bench.file_hash(import_receipt_path),
               "seeds": protocol["seeds"], "scenarios": [s["id"] for s in protocol["scenarios"]],
               "contexts_sha256": bench.digest(bench.all_contexts(protocol)),
               "smoke_connections": "first_four_per_phase_using_original_full_connection_index",
               "counterfactuals": "import_validated_same_seed_v32_b0_and_031_traces",
               "data_kind": "development", "observation_has_no_world_cost": True}
    bench.write_new(Path(out), overlay)
    load_overlay(out)
    return overlay


def load_overlay(path):
    overlay = read_json(path)
    equal(overlay.get("schema"), SCHEMA, "learning overlay schema")
    equal(overlay.get("modes"), list(MODES), "learning modes")
    equal(overlay.get("observer"), OBSERVER, "observation contract")
    equal(overlay.get("comparisons"), COMPARISONS, "paired comparisons")
    for name, value in {"primary_mode": "c1", "ideal_is_privileged_diagnostic": True,
                        "smoke_connections": "first_four_per_phase_using_original_full_connection_index",
                        "counterfactuals": "import_validated_same_seed_v32_b0_and_031_traces",
                        "data_kind": "development", "observation_has_no_world_cost": True}.items():
        equal(overlay.get(name), value, "overlay " + name)
    equal(overlay.get("source_sha256"), sources(), "current producer sources")
    equal(overlay["source_sha256"], IMPORTED_SOURCES, "imported producer sources")
    equal(bench.file_hash(overlay["base_protocol_path"]), overlay["base_protocol_sha256"], "base protocol hash")
    protocol = bench.load_protocol(Path(overlay["base_protocol_path"]))
    equal(overlay.get("seeds"), protocol["seeds"], "overlay seeds")
    equal(overlay.get("scenarios"), [s["id"] for s in protocol["scenarios"]], "overlay scenarios")
    equal(overlay.get("contexts_sha256"), bench.digest(bench.all_contexts(protocol)), "overlay contexts")
    policy = overlay["policy"]
    equal(bench.file_hash(policy["receipt_path"]), policy["receipt_sha256"], "snapshot receipt hash")
    equal(snapshot_identity(policy["fingerprint"]["source_root"], policy["receipt_path"]), policy, "snapshot identity")
    equal(bench.file_hash(overlay["import_receipt_path"]), overlay["import_receipt_sha256"], "import receipt hash")
    receipt = read_json(overlay["import_receipt_path"])
    equal(receipt.get("schema"), IMPORT_SCHEMA, "import receipt schema")
    equal(receipt.get("protocol_sha256"), overlay["base_protocol_sha256"], "import protocol")
    equal(receipt.get("contexts_sha256"), overlay["contexts_sha256"], "import contexts")
    equal(receipt.get("validator_source_sha256"), overlay["source_sha256"], "import validators")
    equal(bench.file_hash(receipt["rules_path"]), receipt["rules_sha256"], "reporting rules")
    return overlay, protocol


def imported_runs(overlay, protocol, deep=False):
    receipt = read_json(overlay["import_receipt_path"])
    for kind in ("raw_manifests", "oracle_manifests", "result_files", "raw_summary_files"):
        for item in receipt["provenance"][kind]:
            equal(bench.file_hash(item["path"]), item["sha256"], "imported file")
    raw = [read_json(item["path"]) for item in receipt["provenance"]["raw_summary_files"]]
    ids = [run_identity(run) for run in raw]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate imported baseline")
    equal(set(ids), expected_baseline_ids(protocol), "imported baseline inventory")
    refs = {}
    for item in receipt["provenance"]["result_files"]:
        value = read_json(item["path"])
        refs[value["context_id"]] = value
    equal({cid: bench.digest(value) for cid, value in refs.items()}, receipt["reference_digests"], "imported reference digests")
    equal(set(refs), set(bench.all_contexts(protocol)), "imported reference contexts")
    if deep:
        fresh_protocol, fresh_raw, fresh_refs, fresh_receipt = import_w1(
            receipt["protocol_path"], receipt["raw_dirs"], receipt["oracle_dirs"], receipt["rules_path"])
        equal(fresh_receipt, receipt, "original import validation replay")
    return raw, refs, receipt


def assert_sources(overlay, overlay_path, overlay_hash):
    equal(bench.file_hash(overlay_path), overlay_hash, "overlay changed during run")
    equal(sources(), overlay["source_sha256"], "producer changed during run")
    equal(sources(), IMPORTED_SOURCES, "compiled source identity")
    equal(inventory(overlay["policy"]["fingerprint"]["source_root"]), overlay["policy"]["fingerprint"], "snapshot changed during run")
    equal(bench.file_hash(overlay["base_protocol_path"]), overlay["base_protocol_sha256"], "base protocol changed")
    equal(bench.file_hash(overlay["import_receipt_path"]), overlay["import_receipt_sha256"], "import receipt changed")
    equal(bench.file_hash(overlay["policy"]["receipt_path"]), overlay["policy"]["receipt_sha256"], "snapshot receipt changed")


def validate_initial(initial, policy):
    equal(initial.get("policy_version"), policy["policy_version"], "policy version")
    equal(initial.get("state_version"), policy["state_version"], "state version")
    equal(initial.get("variant"), "full", "policy variant")
    equal(initial.get("runtime_overrides"), {}, "policy runtime overrides")
    if "first_flight_evidence" not in initial.get("capabilities", {}).get("observe_extra", []):
        raise ValueError("policy must explicitly support first-flight evidence")
    validate_audit(initial["audit"], policy["fingerprint"])


def validate_audit(audit, fingerprint):
    bench.validate_policy_audit(audit, fingerprint)
    for name in ("isolated", "dont_write_bytecode", "source_unchanged", "read_only_audit"):
        equal(audit.get(name), True, "worker audit " + name)
    if not audit.get("source_sha256") or not audit.get("actual_module_paths"):
        raise ValueError("worker audit has no actual policy modules")


def schedule(scenario, smoke=False):
    offset = 0
    for phase_number, phase in enumerate(scenario["phases"]):
        for phase_index in range(min(phase["length"], 4) if smoke else phase["length"]):
            yield phase_number, phase_index, offset + phase_index, phase
        offset += phase["length"]


def counterfactual_row(rows, index, phase_number, phase_index, cid, context):
    row = rows[index]
    for key, value in {"index": index, "phase": phase_number, "phase_index": phase_index, "context_id": cid}.items():
        equal(row.get(key), value, "counterfactual " + key)
    equal(row["phase_p"], context.p, "counterfactual loss context")
    return row


def run_seed(worker, scenario, protocol, seed, trace_path, observation_mode, baseline_run, smoke=False):
    baseline_rows = bench_report.load_trace(baseline_run)
    worker.request({"op": "reset", "destination": "d"})
    observed_rtt = bench.ObservedRTT()
    world = bench.World(params=scenario["world_params"], seed=seed)
    rows = []
    with Path(trace_path).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for phase_number, phase_index, world_index, phase in schedule(scenario, smoke):
                    spec = bench.context_spec(scenario, phase)
                    cid = bench.context_id(spec)
                    if scenario["reset_each_connection"]:
                        worker.request({"op": "reset", "destination": "d"})
                        observed_rtt = bench.ObservedRTT()
                    decide_input = {"op": "decide", "destination": "d", "rtt_ms": observed_rtt.value()}
                    result = worker.request(decide_input)
                    decision = result["decision"]
                    context = bench.mixture_context(spec, seed, world_index)
                    fixed = counterfactual_row(baseline_rows, world_index, phase_number, phase_index, cid, context)
                    observation = world.sample(context, bench.Action(*decision["action"]), connection=world_index,
                                               trace=observation_mode != "none")
                    equal(observation["selected_cert_bytes"], fixed["selected_cert_bytes"], "common certificate draw")
                    equal(observation["true_rtt_ms"], fixed["true_rtt_ms"], "common RTT draw")
                    projection = make_world_evidence(observation, mode=observation_mode, seed=seed, connection=world_index,
                        feedback_loss_probability=context.s2c_loss if world.params["features"]["s2c_loss"] else 0.0,
                        receiver_max_datagram_bytes=world.params["server"]["decoder_max_datagram_bytes"],
                        feedback_grace_ms=OBSERVER["feedback_grace_ms"], crc_list_limit=OBSERVER["crc_list_limit"])
                    observed_rtt.observe(observation)
                    observe_input = bench.observation_request(decision, observation, observed_rtt.value())
                    observe_input["optional"] = {"first_flight_evidence": projection["evidence"]}
                    feedback = worker.request(observe_input)
                    info = feedback["observation"]
                    first_received = sum(packet["read_size"] for packet in observation["arrivals"]
                                         if packet["flight"] == 0 and packet["arrived"])
                    row = {"index": len(rows), "world_connection_index": world_index, "phase": phase_number,
                        "phase_index": phase_index, "phase_p": context.p, "p_mean_pre": decision["p_mean"],
                        "S_hat_pre": result["before"]["S_hat"], "action": list(decision["action"]), "context_id": cid,
                        "hct_ms": observation["hct"], "ok": observation["ok"],
                        "extra_server_bytes": observation["server_counted_uplink_bytes"] - fixed["b0_server_bytes"],
                        "extra_first_flight_bytes": first_received-context.k*context.w,
                        "extra_client_first_flight_bytes": observation["client_first_flight_bytes"]-context.k*context.w,
                        "server_bytes": observation["server_counted_uplink_bytes"], "b0_server_bytes": fixed["b0_server_bytes"],
                        "alarm_raised": info.get("raised", []), "guard_alarm": decision.get("guard_alarm", False),
                        "reeval": decision.get("reeval", False), "updated": info.get("updated", False),
                        "decision_why": decision.get("why"), "observation_skip": info.get("skip"),
                        "policy_rtt_ms": observed_rtt.value(), "raw_observed_rtt_ms": observation["rtt"],
                        "S_hat_post": feedback["state"]["S_hat"], "selected_cert_bytes": observation["selected_cert_bytes"],
                        "true_rtt_ms": observation["true_rtt_ms"], "initial_datagrams": observation["initial_datagrams"],
                        "stop_reason": observation["stop_reason"], "b0_hct_ms": fixed["b0_hct_ms"],
                        "global_fixed_hct_ms": fixed["global_fixed_hct_ms"],
                        "global_fixed_server_bytes": fixed["global_fixed_server_bytes"],
                        "policy_decide_input": decide_input, "policy_observe_input": observe_input,
                        "decision": decision, "observation_info": info,
                        "observation_mode": observation_mode, "observer_diagnostics": projection["diagnostics"]}
                    rows.append(row)
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    snapshot = worker.request({"op": "snapshot", "destination": "d"})
    counts = collections.Counter((row["context_id"], tuple(row["action"])) for row in rows)
    return {"seed": seed, "n": len(rows), "summary": summarize_run(rows, scenario, protocol),
            "action_counts": [{"context_id": key[0], "action": list(key[1]), "n": n} for key, n in sorted(counts.items())],
            "final_state": snapshot["state"], "final_serialized_state": snapshot["serialized"], "policy_audit": snapshot["audit"],
            "trace_path": str(Path(trace_path).resolve()), "trace_sha256": bench.file_hash(trace_path),
            "counterfactual_trace_path": baseline_run["trace_path"], "counterfactual_trace_sha256": baseline_run["trace_sha256"]}


def make_manifest(overlay_path, overlay, protocol, modes=None, scenarios=None, smoke=False):
    modes = list(MODES) if modes is None else list(modes)
    selected = [s["id"] for s in protocol["scenarios"]] if scenarios is None else list(scenarios)
    if not modes or len(set(modes)) != len(modes) or not set(modes) <= set(MODES):
        raise ValueError("unknown or duplicate observation mode")
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= set(overlay["scenarios"]):
        raise ValueError("unknown or duplicate scenario")
    return {"schema": RAW_SCHEMA, "overlay_path": str(Path(overlay_path).resolve()),
            "overlay_sha256": bench.file_hash(overlay_path), "protocol_sha256": overlay["base_protocol_sha256"],
            "mode": "smoke" if smoke else "full", "observation_modes": modes, "scenarios": selected,
            "seeds": protocol["seeds"][:1] if smoke else protocol["seeds"],
            "source_sha256": overlay["source_sha256"], "policy": overlay["policy"],
            "import_receipt_sha256": overlay["import_receipt_sha256"]}


def close_value(actual, expected, name):
    if isinstance(expected, float):
        if isinstance(actual, bool) or not isinstance(actual, (float, int)) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-12):
            raise ValueError(name + " differs")
    elif isinstance(expected, dict):
        equal(set(actual), set(expected), name + " fields")
        for key, value in expected.items():
            close_value(actual[key], value, name + ":" + key)
    elif isinstance(expected, list):
        equal(len(actual), len(expected), name + " length")
        for index, value in enumerate(expected):
            close_value(actual[index], value, name + ":" + str(index))
    else:
        equal(actual, expected, name)


def monitor_fit_score(window, beta):
    total = -4.0 * beta
    for raw, outcome in window:
        q = min(1 - 1e-6, max(1e-6, raw))
        odds = math.exp(beta)
        total += outcome - q * odds / (1 - q + q * odds)
    return total


def validate_beta_fit(window, value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not -math.log(4) <= value <= math.log(4):
        raise ValueError("invalid monitor beta")
    score = monitor_fit_score(window, value)
    if value == -math.log(4):
        valid = score <= 1e-7
    elif value == math.log(4):
        valid = score >= -1e-7
    else:
        valid = abs(score) <= 1e-7
    if not valid:
        raise ValueError("monitor fit does not satisfy constrained score equation")


def validate_monitor_row(row, previous, config, obs_index):
    state = {"arrival_streak": 0, "monitor": {"v": 1, "arms": {}, "shared_at": 0, "shared_count": 0}} if previous is None else previous
    snapshot = row["decision"]["monitor_prediction"]
    info = row["observation_info"]
    equal(info["monitor_prediction"], snapshot, "consumed monitor snapshot")
    equal(snapshot["v"], 1, "monitor snapshot version")
    for field in ("v", "dec_index", "obs_index"):
        if type(snapshot[field]) is not int:
            raise ValueError("monitor indices must be integers")
    equal(snapshot["dec_index"], obs_index + 1, "monitor decision sequence")
    equal(snapshot["dec_index"], row["decision"]["dec_index"], "monitor decision counter")
    equal(snapshot["obs_index"], obs_index, "monitor observation counter")
    equal(snapshot["action"], row["action"], "monitor final action")
    equal(snapshot["ready"], state["arrival_streak"] >= 8, "monitor prior readiness")
    equal(row["decision"]["monitor_mode"], {key: config[key] for key in ("enabled", "beta", "shared")}, "monitor runtime mode")
    equal(row["decision"]["reeval_feedback_suppressed"], state["arrival_streak"] > 0 and not config["c1_reeval"], "feedback exploration mode")
    evidence = row["policy_observe_input"]["optional"]["first_flight_evidence"]
    usable = evidence["src"] != "none" and not evidence["trunc"] and evidence["sent"] > 0
    equal(info["arrival_usable"], usable, "complete first-flight evidence")
    state["arrival_streak"] = min(8, state["arrival_streak"] + 1) if usable else 0
    equal(info["arrival_streak_after"], state["arrival_streak"], "feedback history")
    equal(info["epsilon_before"], .001, "fixed L1 epsilon")
    equal(info["epsilon_after"], .001, "fixed L1 epsilon after")
    equal(info["epsilon_update_eligible"], False, "L2 EPS is not enabled")
    equal(info["cutoff_rtt_source"], "observation_rtt_current_policy", "L1 loss label timing")
    key = ",".join(str(value) for value in row["action"])
    old = state["monitor"]["arms"].get(key)
    beta = 0.0 if old is None else old["beta"]
    close_value(snapshot["beta"], beta, "monitor beta before observation")
    ctx = snapshot["ctx"]
    if ctx is not None:
        equal(ctx["rtt"], row["policy_decide_input"]["rtt_ms"], "monitor decision RTT")
        q = snapshot["q_raw"]
        if len(q) != 3 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for value in q):
            raise ValueError("invalid predictive class mass")
        close_value(sum(q), 1.0, "predictive mass sum")
        event = min(1.0, sum(q[1:]))
        adjusted = list(q)
        if beta != 0 and event not in (0, 1):
            tilted = event * math.exp(beta) / (1 - event + event * math.exp(beta))
            adjusted = [1 - tilted, q[1] * tilted / event, q[2] * tilted / event]
        close_value(snapshot["q_used"], adjusted, "monitor corrected probabilities")
    else:
        equal([snapshot[k] for k in ("q_raw", "q_used", "cutoffs")], [None, None, None], "cold snapshot")
    expected_reason = "disabled" if not config["enabled"] else "no_ctx" if ctx is None else None
    equal(info["monitor_reason"], expected_reason, "monitor eligibility reason")
    if expected_reason is not None:
        equal(info["monitor"], None, "no monitor update")
        equal(info["raised"], [], "no monitor alarm")
        return state
    grade = 2 if not row["ok"] else 0 if row["hct_ms"] < snapshot["cutoffs"][0] else 1 if row["hct_ms"] < snapshot["cutoffs"][1] else 2
    equal(info["monitor_grade"], grade, "monitor grade from decision boundary")
    z = int(grade != 0)
    result = info["monitor"]
    raw, used = min(1.0, sum(snapshot["q_raw"][1:])), min(1.0, sum(snapshot["q_used"][1:]))
    q = min(1 - 1e-6, max(1e-6, used))
    close_value([result[k] for k in ("q_raw", "q_used", "q_clamped")], [raw, used, q], "monitor used probabilities")
    equal(result["z"], z, "monitor event")
    reactive = snapshot["ready"] and usable
    equal(result["reactive"], reactive, "monitor reaction readiness")
    old = {"up": 0.0, "down": 0.0, "beta": 0.0, "n": 0, "last_seen": 0, "window": [],
           "alarm_at": 0, "alarm_dir": 0, "beta_before": 0.0, "reactive_alarm": False} if old is None else old
    before = old["beta"]
    close_value(result["beta_before"], before, "monitor previous beta")
    up = max(0.0, old["up"] + z * math.log(2) - math.log(1 + q))
    down = max(0.0, old["down"] + z * math.log(.5) - math.log(1 - .5 * q))
    direction = 1 if up >= 5 else -1 if down >= 5 else 0
    equal(result["direction"], direction, "monitor likelihood-ratio alarm")
    old.update(up=0.0 if direction else up, down=0.0 if direction else down, n=old["n"] + 1, last_seen=obs_index + 1,
               window=(old["window"] + [[raw, z]])[-32:])
    expected_action = "record"
    if direction:
        old.update(alarm_at=obs_index + 1, alarm_dir=direction, beta_before=before, reactive_alarm=reactive)
        if reactive and config["beta"]:
            expected_action = "action_model"
    state["monitor"]["arms"][key] = old
    active = {name: value for name, value in state["monitor"]["arms"].items() if obs_index + 1 - value["last_seen"] < 32}
    shared = bool(direction and reactive and config["shared"] and len(active) >= 2 and all(
        value["reactive_alarm"] and value["alarm_dir"] == direction and state["monitor"]["shared_at"] < value["alarm_at"]
        and obs_index + 1 - value["alarm_at"] < 32 for value in active.values()))
    equal(result["shared"], shared, "monitor common change eligibility")
    equal(result["shared_actions"], sorted(active) if shared else [], "monitor common action set")
    if shared:
        for value in active.values():
            value.update(beta=value["beta_before"], up=0.0, down=0.0, reactive_alarm=False)
        state["monitor"]["shared_at"] = obs_index + 1
        state["monitor"]["shared_count"] += 1
        expected_action = "shared_change"
        close_value(result["beta_after"], old["beta"], "common change cancels action correction")
    elif expected_action == "action_model":
        validate_beta_fit(old["window"], result["beta_after"])
        old["beta"] = result["beta_after"]
    elif not direction and reactive and config["beta"] and ((before > 0 and old["up"] == 0) or (before < 0 and old["down"] == 0)):
        after = result["beta_after"]
        if not min(0, before) <= after <= max(0, before):
            raise ValueError("recovery increased or reversed beta")
        if after == 0:
            if monitor_fit_score(old["window"], 0.0) * before > 1e-7:
                raise ValueError("unjustified beta recovery to zero")
        elif after == before:
            if monitor_fit_score(old["window"], before) * before < -1e-7:
                raise ValueError("missing beta recovery")
        else:
            validate_beta_fit(old["window"], after)
        if after != before:
            old["beta"] = after
            expected_action = "recovery"
    else:
        close_value(result["beta_after"], before, "beta unchanged without reaction")
    equal(result["action"], expected_action, "monitor response kind")
    close_value([result["up"], result["down"]], [old["up"], old["down"]], "monitor cumulative state")
    equal(result["observations"], old["n"], "monitor action observation count")
    equal(info["raised"], [key] if direction else [], "new episode list")
    return state


def validate_run(run, manifest, overlay, scenario, observation_mode, seed, baseline_run, deep=True):
    expected = {"schema": RAW_SCHEMA, "generation": "current", "variant": "full", "scenario": scenario["id"],
                "observation_mode": observation_mode, "seed": seed, "mode": manifest["mode"],
                "n": len(list(schedule(scenario, manifest["mode"] == "smoke"))),
                "overlay_sha256": manifest["overlay_sha256"], "protocol_sha256": overlay["base_protocol_sha256"],
                "source_sha256": overlay["source_sha256"], "snapshot_receipt_sha256": overlay["policy"]["receipt_sha256"],
                "counterfactual_trace_path": baseline_run["trace_path"],
                "counterfactual_trace_sha256": baseline_run["trace_sha256"], "status": "complete"}
    for name, value in expected.items():
        equal(run.get(name), value, "learning run " + name)
    validate_initial(run["policy_initial"], overlay["policy"])
    validate_audit(run["policy_audit"], overlay["policy"]["fingerprint"])
    equal(run.get("source_sha256_before"), overlay["source_sha256"], "pre-run sources")
    equal(run.get("source_sha256_after"), overlay["source_sha256"], "post-run sources")
    if deep:
        rows = bench_report.load_trace(run)
        observed_rtt = bench.ObservedRTT()
        monitor_previous = None
        for row, (phase_number, phase_index, world_index, phase) in zip(rows, schedule(scenario, manifest["mode"] == "smoke")):
            for name, value in {"phase": phase_number, "phase_index": phase_index, "world_connection_index": world_index,
                                "observation_mode": observation_mode,
                                "context_id": bench.context_id(bench.context_spec(scenario, phase))}.items():
                equal(row.get(name), value, "learning trace " + name)
            if scenario["reset_each_connection"]:
                observed_rtt = bench.ObservedRTT()
            equal(row["policy_decide_input"], {"op": "decide", "destination": "d", "rtt_ms": observed_rtt.value()}, "decision input history")
            observed_rtt.observe({"rtt": row["raw_observed_rtt_ms"], "hct": row["hct_ms"], "ok": row["ok"]})
            request = row["policy_observe_input"]
            equal(set(request), {"op", "destination", "action", "hct_ms", "ok", "k_obs", "srv_bytes", "rtt_ms", "j_pred", "optional"}, "observation input boundary")
            equal(set(request["optional"]), {"first_flight_evidence"}, "optional evidence boundary")
            evidence = request["optional"]["first_flight_evidence"]
            first_flight_evidence(evidence)
            if evidence["src"] not in ("none", "c1"):
                raise ValueError("unexpected evidence source for this observer")
            if observation_mode == "none":
                equal(evidence["src"], "none", "disabled evidence")
            for name, value in {"op": "observe", "destination": "d", "ok": row["ok"],
                                "hct_ms": row["hct_ms"] if row["ok"] else None,
                                "rtt_ms": observed_rtt.value(),
                                "j_pred": row["decision"].get("j3_pred_pre_ms", row["decision"].get("ej"))}.items():
                equal(request.get(name), value, "observation input " + name)
            equal(request["action"], row["action"], "observation action pairing")
            equal(row["decision"]["action"], row["action"], "decision action pairing")
            equal(row["policy_rtt_ms"], observed_rtt.value(), "recorded policy RTT")
            equal(row["observer_diagnostics"]["mode"], observation_mode, "observer diagnostic mode")
            if scenario["reset_each_connection"]:
                monitor_previous = None
            monitor_previous = validate_monitor_row(row, monitor_previous, overlay["policy"]["monitor_config"],
                                                    0 if scenario["reset_each_connection"] else row["index"])
        final = run["final_serialized_state"]
        equal(final["v"], 6, "L3 final state version")
        equal(final["monitor_pending"], None, "L3 final snapshot consumed")
        if monitor_previous is not None:
            equal(final["arrival_streak"], monitor_previous["arrival_streak"], "L3 final feedback readiness")
            close_value(final["monitor"], monitor_previous["monitor"], "L3 final monitor state")
        return rows


def validate_receipt(run, result_path):
    result_path = Path(result_path).resolve()
    attempt = run["attempt_id"]
    if Path(attempt).name != attempt or not attempt.startswith(f'seed{run["seed"]:05d}.'):
        raise ValueError("invalid collector attempt identity")
    folder = result_path.parent
    equal(Path(run["trace_path"]).resolve(), folder / (attempt + ".jsonl.gz"), "attempt trace path")
    started_path = folder / (attempt + ".started.json")
    finished_path = folder / (attempt + ".finished.json")
    equal(bench.file_hash(started_path), run["started_receipt_sha256"], "started receipt hash")
    binding = {"schema": RAW_SCHEMA, "observation_mode": run["observation_mode"], "scenario": run["scenario"],
               "seed": run["seed"], "overlay_sha256": run["overlay_sha256"], "source_sha256": run["source_sha256"]}
    equal(read_json(started_path), binding, "started receipt binding")
    equal(read_json(finished_path), {**binding, "status": "complete", "result_digest": bench.digest(run)}, "finished receipt binding")
    if (folder / (attempt + ".failed.json")).exists():
        raise ValueError("published attempt also has failure receipt")
    return {str(started_path): bench.file_hash(started_path), str(finished_path): bench.file_hash(finished_path)}


def collect(overlay_path, out, modes=None, scenarios=None, smoke=False, resume=False, dry_run=False):
    overlay, protocol = load_overlay(overlay_path)
    manifest = make_manifest(overlay_path, overlay, protocol, modes, scenarios, smoke)
    if dry_run:
        return manifest
    raw, refs, receipt = imported_runs(overlay, protocol)
    baseline = {(run["scenario"], run["seed"]): run for run in raw if run["generation"] == "v32"}
    scenario_map = {s["id"]: s for s in protocol["scenarios"]}
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with pool.exclusive_lock(out / "collector.lock"):
        manifest_path = out / "manifest.json"
        if manifest_path.exists():
            if not resume:
                raise ValueError("--resume is required")
            equal(read_json(manifest_path), manifest, "resume manifest")
        else:
            if any(path.name != "collector.lock" for path in out.iterdir()):
                raise ValueError("new collector directory is not empty")
            bench.write_new(manifest_path, manifest)
        for mode in manifest["observation_modes"]:
            for sid in manifest["scenarios"]:
                scenario = scenario_map[sid]
                folder = out / mode / sid
                folder.mkdir(parents=True, exist_ok=True)
                for seed in manifest["seeds"]:
                    baseline_run = baseline[sid, seed]
                    result_path = folder / f"seed{seed:05d}.json"
                    if result_path.exists():
                        old = read_json(result_path)
                        rows = validate_run(old, manifest, overlay, scenario, mode, seed, baseline_run)
                        equal(old["summary"], summarize_run(rows, scenario, protocol), "resume summary recomputation")
                        validate_receipt(old, result_path)
                        continue
                    assert_sources(overlay, overlay_path, manifest["overlay_sha256"])
                    attempt = f"seed{seed:05d}.{time.time_ns()}"
                    binding = {"schema": RAW_SCHEMA, "observation_mode": mode, "scenario": sid, "seed": seed,
                               "overlay_sha256": manifest["overlay_sha256"], "source_sha256": sources()}
                    bench.write_new(folder / (attempt + ".started.json"), binding)
                    worker = None
                    start = time.monotonic()
                    try:
                        worker = bench.PolicyWorker(overlay["policy"]["fingerprint"]["source_root"], scenario, protocol,
                                                    "full", folder / (attempt + ".stderr.txt"))
                        initial = worker.initial
                        validate_initial(initial, overlay["policy"])
                        result = run_seed(worker, scenario, protocol, seed, folder / (attempt + ".jsonl.gz"),
                                          mode, baseline_run, smoke)
                        worker.close()
                        worker = None
                        assert_sources(overlay, overlay_path, manifest["overlay_sha256"])
                        result.update(schema=RAW_SCHEMA, generation="current", variant="full", scenario=sid,
                            observation_mode=mode, mode=manifest["mode"], protocol_sha256=overlay["base_protocol_sha256"],
                            overlay_sha256=manifest["overlay_sha256"], source_sha256=overlay["source_sha256"],
                            source_sha256_before=binding["source_sha256"], source_sha256_after=sources(),
                            snapshot_receipt_sha256=overlay["policy"]["receipt_sha256"], policy_initial=initial,
                            status="complete", elapsed_seconds=time.monotonic()-start)
                        result.update(attempt_id=attempt, started_receipt_sha256=bench.file_hash(folder / (attempt + ".started.json")))
                        validate_run(result, manifest, overlay, scenario, mode, seed, baseline_run)
                        bench.write_new(folder / (attempt + ".finished.json"), {**binding, "status": "complete", "result_digest": bench.digest(result)})
                        bench.write_new(result_path, result)
                        print(json.dumps({"status": "complete", "mode": mode, "scenario": sid, "seed": seed,
                                          "n": result["n"], "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
                    except BaseException as exc:
                        failure = {**binding, "status": "failed", "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()}
                        bench.write_new(folder / (attempt + ".failed.json"), failure)
                        raise
                    finally:
                        if worker is not None:
                            worker.close()
        assert_sources(overlay, overlay_path, manifest["overlay_sha256"])
    return {"status": "complete", "out": str(out), "mode": manifest["mode"]}


def load_learning_runs(overlay_path, raw_dirs, require_complete=True):
    overlay, protocol = load_overlay(overlay_path)
    baseline, refs, receipt = imported_runs(overlay, protocol, deep=True)
    baseline_map = {(run["scenario"], run["seed"]): run for run in baseline if run["generation"] == "v32"}
    scenarios = {s["id"]: s for s in protocol["scenarios"]}
    actual = {}
    files = {**receipt["files_sha256"], str(Path(overlay_path).resolve()): bench.file_hash(overlay_path),
             overlay["import_receipt_path"]: overlay["import_receipt_sha256"]}
    files[overlay["base_protocol_path"]] = overlay["base_protocol_sha256"]
    files[receipt["rules_path"]] = receipt["rules_sha256"]
    files[overlay["policy"]["receipt_path"]] = overlay["policy"]["receipt_sha256"]
    files.update({str(Path(__file__).with_name(name)): value for name, value in overlay["source_sha256"].items()})
    policy = overlay["policy"]["fingerprint"]
    files.update({str(Path(policy["source_root"]) / name): value for name, value in policy["files"].items()})
    for item in receipt["provenance"]["raw_manifests"]:
        for fingerprint in item["policy_source_fingerprints"].values():
            files.update({str(Path(fingerprint["source_root"]) / name): value for name, value in fingerprint["files"].items()})
    for folder in map(Path, raw_dirs):
        with pool.exclusive_lock(folder / "collector.lock"):
            manifest_path = folder / "manifest.json"
            manifest = read_json(manifest_path)
            equal(manifest.get("mode"), "full", "only full learning results may be analyzed")
            expected = make_manifest(overlay_path, overlay, protocol, manifest["observation_modes"], manifest["scenarios"])
            equal(manifest, expected, "learning shard manifest")
            files[str(manifest_path.resolve())] = bench.file_hash(manifest_path)
            expected_paths = set()
            for mode in manifest["observation_modes"]:
                for sid in manifest["scenarios"]:
                    for seed in manifest["seeds"]:
                        path = folder / mode / sid / f"seed{seed:05d}.json"
                        expected_paths.add(path.resolve())
                        if not path.is_file():
                            raise ValueError("learning shard is incomplete")
                        key = mode, sid, seed
                        if key in actual:
                            raise ValueError("duplicate learning run across shards")
                        run = read_json(path)
                        rows = validate_run(run, manifest, overlay, scenarios[sid], mode, seed, baseline_map[sid, seed])
                        files.update(validate_receipt(run, path))
                        equal(run["summary"], summarize_run(rows, scenarios[sid], protocol), "learning summary recomputation")
                        actual[key] = run
                        files[str(path.resolve())] = bench.file_hash(path)
                        files[str(Path(run["trace_path"]).resolve())] = run["trace_sha256"]
            found = {path.resolve() for path in folder.glob("*/*/seed*.json")
                     if path.name.count(".") == 1}
            equal(found, expected_paths, "unexpected learning summary inventory")
    expected_ids = {(mode, s["id"], seed) for mode in MODES for s in protocol["scenarios"] for seed in protocol["seeds"]}
    if require_complete:
        equal(set(actual), expected_ids, "full three-mode seed inventory")
    elif not set(actual) <= expected_ids:
        raise ValueError("learning run is outside the overlay")
    assert_sources(overlay, overlay_path, files[str(Path(overlay_path).resolve())])
    provenance = {"schema": RAW_SCHEMA, "overlay": overlay, "overlay_sha256": bench.file_hash(overlay_path),
                  "import_receipt": receipt, "inputs_sha256": files, "complete": set(actual) == expected_ids,
                  "baseline_runs": len(baseline), "current_runs": len(actual),
                  "analysis_aliases": {mode: "current_" + mode for mode in MODES}}
    return protocol, baseline, [actual[key] for key in sorted(actual)], refs, provenance


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--protocol", type=Path, required=True)
    freeze.add_argument("--raw-dirs", type=Path, nargs="+", required=True)
    freeze.add_argument("--oracle-dirs", type=Path, nargs="+", required=True)
    freeze.add_argument("--policy-source-root", type=Path, required=True)
    freeze.add_argument("--policy-snapshot-receipt", type=Path, required=True)
    freeze.add_argument("--original-source-root", type=Path)
    freeze.add_argument("--out", type=Path, required=True)
    freeze.add_argument("--import-receipt", type=Path, required=True)
    run = commands.add_parser("collect")
    run.add_argument("--overlay", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--modes", nargs="+", choices=MODES)
    run.add_argument("--scenarios", nargs="+")
    run.add_argument("--smoke", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    verify = commands.add_parser("validate")
    verify.add_argument("--overlay", type=Path, required=True)
    verify.add_argument("--raw-dirs", type=Path, nargs="+", required=True)
    args = parser.parse_args(argv)
    if args.command == "freeze":
        result = freeze_overlay(args.protocol, args.raw_dirs, args.oracle_dirs, args.policy_source_root,
                                args.policy_snapshot_receipt, args.out, args.import_receipt, original_source_root=args.original_source_root)
    elif args.command == "collect":
        result = collect(args.overlay, args.out, args.modes, args.scenarios, args.smoke, args.resume, args.dry_run)
    else:
        protocol, baseline, current, refs, provenance = load_learning_runs(args.overlay, args.raw_dirs)
        result = {"status": "complete", "baseline_runs": len(baseline), "current_runs": len(current),
                  "reference_count": len(refs), "input_digest": bench.digest(provenance["inputs_sha256"])}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
