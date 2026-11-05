import sys
sys.dont_write_bytecode = True
import argparse
import collections
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.v33 import bench, bench_report
from experiments.v33 import bench_learning_l3 as collector
from experiments.v33 import bench_learning_report as legacy
from experiments.v33.bench_metrics import paired_summary


RAW_SCHEMA = "padfec.v33fix.rejudge_raw/1"
SNAPSHOT_SCHEMA = "padfec.v33fix.rejudge_snapshot/1"
COMPARE_SCHEMA = "padfec.v33fix.rejudge_trajectory/1"
REPORT_SCHEMA = "padfec.v33fix.rejudge_report/1"
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
PROTOCOL = ROOT / "g3/v33/bench_protocol.json"
REPLAY = ROOT / "g3/v33/V33FIX_replay_v1.json"
L3_REPORT = ROOT / "g3/v33/L3_benchmark_v1.json"
PRECISION_REPORT = ROOT / "g3/v33/L1_benchmark_precision_v1.json"
L3_FAMILY = RUNS / "L3_joint_action_family_v1.json"
L3_FAMILY_SHA256 = "3e31108f94fe693d60507e213f6a6e4f77876479675a63f65343122f921262ad"
L3_POOL = RUNS / "L3_joint_action_pool_v1"
PRECISION_POOL = RUNS / "L1_action_pool_precision_v2"
L3_RECORD_OVERLAY = "L3_record_only_v1.json"
POLICY_VERSION = "v3.3.1-dev"
STATE_VERSION = 11
PACKAGES = ("afec", "padfec", "padfec3")
MODES = ("none", "c1")
ALIASES = {"none": "v331_none", "c1": "v331_c1"}
PAIRS = [("v331_none", "v32"), ("v331_c1", "v32"), ("v331_none", "v31"), ("v331_c1", "v31"),
         ("v331_none", "l1_none"), ("v331_c1", "l1_c1"), ("v331_c1", "v331_none"), ("v331_c1", "record_c1")]
ADOPTION_PAIRS = [("v331_none", "v32"), ("v331_c1", "v32")]
ROW_FIELDS = ("index", "phase", "phase_index", "phase_p", "context_id", "action", "hct_ms", "ok", "server_bytes",
              "b0_server_bytes", "extra_server_bytes", "extra_first_flight_bytes", "extra_client_first_flight_bytes",
              "selected_cert_bytes", "true_rtt_ms", "initial_datagrams", "stop_reason", "b0_hct_ms",
              "global_fixed_hct_ms", "global_fixed_server_bytes", "policy_rtt_ms", "raw_observed_rtt_ms",
              "p_mean_pre", "S_hat_pre", "S_hat_post", "decision_why", "reeval", "guard_alarm", "alarm_raised",
              "updated", "observation_skip", "policy_decide_input")
TRAJECTORY_FIELDS = ("action", "hct_ms", "ok", "server_bytes", "extra_server_bytes", "selected_cert_bytes",
                     "true_rtt_ms", "policy_rtt_ms", "p_mean_pre", "decision_why")
C1_FIELDS = ("observer_diagnostics", "observation_mode")
DECISION_FIELDS = ("action", "why", "ej", "p_mean", "n_cands", "reeval")
SLIM_FIELDS = ("index", "context_id", "action", "hct_ms", "b0_hct_ms", "global_fixed_hct_ms", "server_bytes",
               "b0_server_bytes", "global_fixed_server_bytes")


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def equal(actual, expected, label):
    if actual != expected:
        raise ValueError(f"{label} differs")


def policy_inventory(root):
    root = Path(root).resolve(strict=True)
    return {path.relative_to(root).as_posix(): bench.file_hash(path)
            for package in PACKAGES for path in sorted((root / package).rglob("*.py"))}


def make_snapshot(out):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("snapshot destination must be new")
    replay = read_json(REPLAY)
    before = policy_inventory(ROOT)
    equal(before, replay["policy_sources_sha256"], "working tree policy against the replayed policy")
    for relative in before:
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    copied = policy_inventory(out)
    equal(copied, before, "snapshot bytes")
    equal(policy_inventory(ROOT), before, "working tree changed while copying")
    receipt = {"schema": SNAPSHOT_SCHEMA, "source_root": str(ROOT), "snapshot_root": str(out), "files": copied,
               "replay_path": str(REPLAY), "replay_sha256": bench.file_hash(REPLAY),
               "replay_policy_sources_match": True, "policy_version": POLICY_VERSION, "state_version": STATE_VERSION,
               "created_ns": time.time_ns()}
    bench.write_new(out.parent / (out.name + ".receipt.json"), receipt)
    return receipt


def load_snapshot(root):
    root = Path(root).resolve(strict=True)
    receipt_path = root.parent / (root.name + ".receipt.json")
    receipt = read_json(receipt_path)
    equal(receipt.get("schema"), SNAPSHOT_SCHEMA, "snapshot schema")
    equal(Path(receipt["snapshot_root"]).resolve(), root, "snapshot root")
    equal(policy_inventory(root), receipt["files"], "snapshot inventory")
    return receipt, receipt_path


def family_inventory():
    equal(bench.file_hash(L3_FAMILY), L3_FAMILY_SHA256, "L3 joint family plan")
    return {str(Path(path).resolve()).lower(): value for path, value in read_json(L3_FAMILY)["inputs_sha256"].items()}


def checked(path, inventory, label):
    key = str(Path(path).resolve()).lower()
    if key not in inventory:
        raise ValueError(f"{label} is outside the frozen L3 joint inventory: {path}")
    equal(bench.file_hash(path), inventory[key], label + " hash")
    return path


def summary_files(folder):
    return sorted(path for path in Path(folder).glob("seed?????.json"))


def baseline_runs(generation, inventory=None):
    folder = RUNS / f"W1_raw_{generation}" / generation / "full"
    result = {}
    for cell in sorted(folder.iterdir()):
        for path in summary_files(cell):
            if inventory is not None:
                checked(path, inventory, f"W1 {generation} summary")
            run = read_json(path)
            equal((run["generation"], run["variant"], run["scenario"]), (generation, "full", cell.name), "W1 run identity")
            if inventory is not None:
                checked(run["trace_path"], inventory, f"W1 {generation} trace")
            result[run["scenario"], run["seed"]] = run
    return result


def learning_runs(pattern, overlay_name, modes, inventory=None):
    result = {}
    for root in sorted(RUNS.glob(pattern)):
        if not root.is_dir() or not (root / "manifest.json").is_file():
            continue
        manifest = read_json(root / "manifest.json")
        if Path(manifest["overlay_path"]).name != overlay_name or manifest.get("mode") != "full":
            continue
        for mode in manifest["observation_modes"]:
            if mode not in modes:
                continue
            for cell in manifest["scenarios"]:
                for path in summary_files(root / mode / cell):
                    if inventory is not None:
                        checked(path, inventory, f"{overlay_name} summary")
                    run = read_json(path)
                    equal((run["observation_mode"], run["scenario"], run["mode"]), (mode, cell, "full"), "learning run identity")
                    if inventory is not None:
                        checked(run["trace_path"], inventory, f"{overlay_name} trace")
                    key = mode, cell, run["seed"]
                    if key in result:
                        raise ValueError(f"duplicate learning run {key}")
                    result[key] = run
    return result


def load_rows(run):
    trace = Path(run["trace_path"])
    equal(bench.file_hash(trace), run["trace_sha256"], f"trace {trace}")
    rows = []
    with gzip.open(trace, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            equal(row.get("index"), len(rows), "trace index")
            rows.append(row)
    equal(len(rows), run["n"], "trace length")
    return rows


def validate_initial(initial, receipt):
    equal(initial.get("policy_version"), POLICY_VERSION, "policy version")
    equal(initial.get("state_version"), STATE_VERSION, "state version")
    equal(initial.get("variant"), "full", "policy variant")
    equal(initial.get("runtime_overrides"), {}, "runtime overrides")
    if "first_flight_evidence" not in initial.get("capabilities", {}).get("observe_extra", []):
        raise ValueError("policy must accept first-flight evidence")
    validate_audit(initial["audit"], receipt)


def validate_audit(audit, receipt):
    bench.validate_policy_audit(audit, {"source_root": receipt["snapshot_root"], "files": receipt["files"]})
    for name in ("isolated", "dont_write_bytecode", "source_unchanged", "read_only_audit"):
        equal(audit.get(name), True, "worker audit " + name)


def collect_one(snapshot, out, mode, sid, seeds):
    if mode not in MODES:
        raise ValueError("unknown mode")
    receipt, receipt_path = load_snapshot(snapshot)
    protocol = bench.load_protocol(PROTOCOL)
    protocol_hash = bench.file_hash(PROTOCOL)
    scenario = {s["id"]: s for s in protocol["scenarios"]}[sid]
    baseline = baseline_runs("v32")
    folder = Path(out).resolve() / mode / sid
    folder.mkdir(parents=True, exist_ok=True)
    for seed in seeds:
        result_path = folder / f"seed{seed:05d}.json"
        if result_path.exists():
            old = read_json(result_path)
            equal(bench.file_hash(old["trace_path"]), old["trace_sha256"], "existing trace")
            continue
        trace_path = folder / f"seed{seed:05d}.jsonl.gz"
        if trace_path.exists():
            raise ValueError(f"orphan trace needs inspection: {trace_path}")
        sources_before = collector.sources()
        start = time.monotonic()
        worker = bench.PolicyWorker(receipt["snapshot_root"], scenario, protocol, "full", folder / f"seed{seed:05d}.worker.txt")
        try:
            initial = worker.initial
            validate_initial(initial, receipt)
            result = collector.run_seed(worker, scenario, protocol, seed, trace_path, mode, baseline[sid, seed])
            worker.close()
            worker = None
        finally:
            if worker is not None:
                worker.close()
        validate_audit(result["policy_audit"], receipt)
        equal(policy_inventory(receipt["snapshot_root"]), receipt["files"], "snapshot after run")
        equal(collector.sources(), sources_before, "producer sources during run")
        result.update(schema=RAW_SCHEMA, generation=ALIASES[mode], variant="full", scenario=sid, observation_mode=mode,
                      mode="full", protocol_sha256=protocol_hash, snapshot_receipt_path=str(receipt_path),
                      snapshot_receipt_sha256=bench.file_hash(receipt_path), policy_initial=initial,
                      producer_sha256=sources_before, elapsed_seconds=time.monotonic() - start)
        bench.write_new(result_path, result)
        print(json.dumps({"status": "complete", "mode": mode, "scenario": sid, "seed": seed, "n": result["n"],
                          "elapsed_seconds": round(result["elapsed_seconds"], 2)}), flush=True)


def collect(snapshot, out, modes, scenarios, seeds, jobs):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    logs.mkdir(exist_ok=True)
    pending = [(mode, sid) for mode in modes for sid in scenarios]
    running = []
    failures = []
    started = time.monotonic()
    while pending or running:
        while pending and len(running) < jobs:
            mode, sid = pending.pop(0)
            stamp = time.time_ns()
            stdout = (logs / f"{mode}_{sid}_{stamp}.out.txt").open("x", encoding="utf-8")
            stderr = (logs / f"{mode}_{sid}_{stamp}.err.txt").open("x", encoding="utf-8")
            command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "collect-one", "--snapshot", str(snapshot),
                       "--out", str(out), "--mode", mode, "--scenario", sid, "--seeds", *map(str, seeds)]
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            running.append((mode, sid, process, stdout, stderr))
        time.sleep(0.5)
        for item in list(running):
            mode, sid, process, stdout, stderr = item
            code = process.poll()
            if code is None:
                continue
            stdout.close()
            stderr.close()
            running.remove(item)
            if code != 0:
                failures.append({"mode": mode, "scenario": sid, "exit": code})
            print(json.dumps({"finished": [mode, sid], "exit": code, "elapsed_seconds": round(time.monotonic() - started, 1)}), flush=True)
    return {"status": "failed" if failures else "complete", "failures": failures, "out": str(out)}


def row_view(row, mode):
    view = {name: row.get(name, "<absent>") for name in ROW_FIELDS}
    view["policy_observe_input"] = {key: value for key, value in row["policy_observe_input"].items() if key != "optional"}
    view["decision"] = {name: row["decision"].get(name, "<absent>") for name in DECISION_FIELDS}
    if mode == "c1":
        for name in C1_FIELDS:
            view[name] = row.get(name, "<absent>")
        view["evidence"] = row["policy_observe_input"].get("optional")
    return view


def compare_run(mode, new_run, reference_run):
    new_rows, old_rows = load_rows(new_run), load_rows(reference_run)
    equal(len(new_rows), len(old_rows), "trajectory length")
    field_mismatch = collections.Counter()
    first = {}
    first_trajectory = None
    for new, old in zip(new_rows, old_rows):
        a, b = row_view(new, mode), row_view(old, mode)
        for name in a:
            if a[name] != b[name]:
                field_mismatch[name] += 1
                first.setdefault(name, new["index"])
        if first_trajectory is None and any(new[name] != old[name] for name in TRAJECTORY_FIELDS):
            first_trajectory = new["index"]
    summary_equal = new_run["summary"] == reference_run["summary"]
    counts_equal = new_run["action_counts"] == reference_run["action_counts"]
    paths = collections.Counter(row["decision"].get("policy_path") for row in new_rows)
    first_c1 = next((row["index"] for row in new_rows if row["decision"].get("c1_seen")), None)
    return {"mode": mode, "scenario": new_run["scenario"], "seed": new_run["seed"], "n": len(new_rows),
            "reference_trace": reference_run["trace_path"], "reference_trace_sha256": reference_run["trace_sha256"],
            "new_trace_sha256": new_run["trace_sha256"],
            "trajectory_identical": first_trajectory is None, "first_trajectory_difference": first_trajectory,
            "all_compared_fields_identical": not field_mismatch, "field_mismatch_rows": dict(sorted(field_mismatch.items())),
            "first_field_mismatch": dict(sorted(first.items())), "summary_identical": summary_equal,
            "action_counts_identical": counts_equal, "policy_path_counts": {str(k): v for k, v in sorted(paths.items(), key=str)},
            "first_decision_with_c1_seen": first_c1}


def compare(raw, out):
    raw = Path(raw).resolve()
    inventory = family_inventory()
    v32 = baseline_runs("v32", inventory)
    record = learning_runs("L3_raw_v1_*", L3_RECORD_OVERLAY, ("c1",), inventory)
    results = []
    for mode in MODES:
        for path in sorted(raw.glob(f"{mode}/*/seed?????.json")):
            run = read_json(path)
            equal(run.get("schema"), RAW_SCHEMA, "rejudge raw schema")
            reference = v32[run["scenario"], run["seed"]] if mode == "none" else record[mode, run["scenario"], run["seed"]]
            results.append(compare_run(mode, run, reference))
    totals = {}
    for mode in MODES:
        items = [item for item in results if item["mode"] == mode]
        totals[mode] = {"runs": len(items), "trajectory_identical": sum(item["trajectory_identical"] for item in items),
                        "all_fields_identical": sum(item["all_compared_fields_identical"] for item in items),
                        "summary_identical": sum(item["summary_identical"] for item in items),
                        "different": [[item["scenario"], item["seed"], item["first_trajectory_difference"]]
                                      for item in items if not item["trajectory_identical"]],
                        "field_mismatch_runs": dict(collections.Counter(name for item in items for name in item["field_mismatch_rows"]))}
    value = {"schema": COMPARE_SCHEMA, "raw": str(raw), "references": {"none": "W1_raw_v32", "c1": "L3 record_only_v1 c1"},
             "trajectory_fields": list(TRAJECTORY_FIELDS), "compared_row_fields": list(ROW_FIELDS) + ["policy_observe_input", "decision"],
             "decision_fields": list(DECISION_FIELDS), "c1_extra_fields": list(C1_FIELDS) + ["evidence"],
             "totals": totals, "runs": results}
    bench.write_new(Path(out), value)
    return totals


def arm_policy(arm, snapshot):
    protocol = read_json(PROTOCOL)
    if arm == "v32":
        root = Path(protocol["generations"]["v32"]["source_root"]).resolve()
        expected = read_json(RUNS / "W1_raw_v32" / "manifest.json")["policy_source_fingerprints"]["v32"]["files"]
        return root, expected, "legacy"
    if arm == "l1_c1":
        root = (ROOT / "g3/v33/policy_snapshots/L1_v1").resolve()
        expected = read_json(ROOT / "g3/v33/bench_overlays/L1_v1.json")["policy"]["fingerprint"]["files"]
        return root, expected, "c1"
    if arm in ("v331_none", "v331_c1"):
        receipt, _ = load_snapshot(snapshot)
        return Path(receipt["snapshot_root"]), receipt["files"], arm.split("_", 1)[1]
    raise ValueError("unknown repetition arm")


def fresh_seed(worker, scenario, protocol, seed, trace_path, observation_mode):
    from experiments.v33.bench_metrics import summarize_run
    from experiments.v33.first_flight_observer import make_world_evidence
    worker.request({"op": "reset", "destination": "d"})
    observed_rtt = bench.ObservedRTT()
    world = bench.World(params=scenario["world_params"], seed=seed)
    baseline = bench.World(params=scenario["world_params"], seed=seed)
    fixed = bench.World(params=scenario["world_params"], seed=seed)
    rows = []
    with Path(trace_path).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for phase_number, phase_index, index, phase in collector.schedule(scenario):
                    spec = bench.context_spec(scenario, phase)
                    cid = bench.context_id(spec)
                    if scenario["reset_each_connection"]:
                        worker.request({"op": "reset", "destination": "d"})
                        observed_rtt = bench.ObservedRTT()
                    decide_input = {"op": "decide", "destination": "d", "rtt_ms": observed_rtt.value()}
                    result = worker.request(decide_input)
                    decision = result["decision"]
                    context = bench.mixture_context(spec, seed, index)
                    observation = world.sample(context, bench.Action(*decision["action"]), connection=index,
                                               trace=observation_mode == "c1")
                    b0 = baseline.sample(context, bench.Action(), connection=index)
                    global_fixed = fixed.sample(context, bench.Action(0, 3, 1), connection=index)
                    observed_rtt.observe(observation)
                    observe_input = bench.observation_request(decision, observation, observed_rtt.value())
                    diagnostics = None
                    if observation_mode != "legacy":
                        projection = make_world_evidence(observation, mode=observation_mode, seed=seed, connection=index,
                            feedback_loss_probability=context.s2c_loss if world.params["features"]["s2c_loss"] else 0.0,
                            receiver_max_datagram_bytes=world.params["server"]["decoder_max_datagram_bytes"],
                            feedback_grace_ms=collector.OBSERVER["feedback_grace_ms"], crc_list_limit=collector.OBSERVER["crc_list_limit"])
                        observe_input["optional"] = {"first_flight_evidence": projection["evidence"]}
                        diagnostics = projection["diagnostics"]
                    feedback = worker.request(observe_input)
                    info = feedback["observation"]
                    first_received = sum(packet["read_size"] for packet in observation["arrivals"]
                                         if packet["flight"] == 0 and packet["arrived"])
                    row = {"index": index, "world_connection_index": index, "phase": phase_number, "phase_index": phase_index,
                        "phase_p": context.p, "p_mean_pre": decision["p_mean"], "S_hat_pre": result["before"]["S_hat"],
                        "action": list(decision["action"]), "context_id": cid, "hct_ms": observation["hct"], "ok": observation["ok"],
                        "extra_server_bytes": observation["server_counted_uplink_bytes"] - b0["server_counted_uplink_bytes"],
                        "extra_first_flight_bytes": first_received - context.k * context.w,
                        "extra_client_first_flight_bytes": observation["client_first_flight_bytes"] - context.k * context.w,
                        "server_bytes": observation["server_counted_uplink_bytes"], "b0_server_bytes": b0["server_counted_uplink_bytes"],
                        "alarm_raised": info.get("raised", []), "guard_alarm": decision.get("guard_alarm", False),
                        "reeval": decision.get("reeval", False), "updated": info.get("updated", False),
                        "decision_why": decision.get("why"), "observation_skip": info.get("skip"),
                        "policy_rtt_ms": observed_rtt.value(), "raw_observed_rtt_ms": observation["rtt"],
                        "S_hat_post": feedback["state"]["S_hat"], "selected_cert_bytes": observation["selected_cert_bytes"],
                        "true_rtt_ms": observation["true_rtt_ms"], "initial_datagrams": observation["initial_datagrams"],
                        "stop_reason": observation["stop_reason"], "b0_hct_ms": b0["hct"],
                        "global_fixed_hct_ms": global_fixed["hct"], "global_fixed_server_bytes": global_fixed["server_counted_uplink_bytes"],
                        "policy_decide_input": decide_input, "policy_observe_input": observe_input,
                        "decision": decision, "observation_info": info, "observation_mode": observation_mode,
                        "observer_diagnostics": diagnostics}
                    rows.append(row)
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    snapshot = worker.request({"op": "snapshot", "destination": "d"})
    counts = collections.Counter((row["context_id"], tuple(row["action"])) for row in rows)
    return {"seed": seed, "n": len(rows), "summary": summarize_run(rows, scenario, protocol),
            "action_counts": [{"context_id": key[0], "action": list(key[1]), "n": n} for key, n in sorted(counts.items())],
            "final_state": snapshot["state"], "policy_audit": snapshot["audit"],
            "trace_path": str(Path(trace_path).resolve()), "trace_sha256": bench.file_hash(trace_path)}


def repeat_one(snapshot, out, arm, sid, seeds, plan):
    root, files, observation_mode = arm_policy(arm, snapshot)
    equal(policy_inventory(root), files, f"{arm} policy inventory")
    protocol = bench.load_protocol(PROTOCOL)
    protocol_hash = bench.file_hash(PROTOCOL)
    scenario = {s["id"]: s for s in protocol["scenarios"]}[sid]
    folder = Path(out).resolve() / arm / sid
    folder.mkdir(parents=True, exist_ok=True)
    fingerprint = {"source_root": str(root), "files": files}
    for seed in seeds:
        result_path = folder / f"seed{seed:05d}.json"
        if result_path.exists():
            continue
        trace_path = folder / f"seed{seed:05d}.jsonl.gz"
        if trace_path.exists():
            raise ValueError(f"orphan trace needs inspection: {trace_path}")
        start = time.monotonic()
        worker = bench.PolicyWorker(root, scenario, protocol, "full", folder / f"seed{seed:05d}.worker.txt")
        try:
            initial = worker.initial
            equal(initial.get("runtime_overrides"), {}, "runtime overrides")
            extras = initial.get("capabilities", {}).get("observe_extra", [])
            equal(extras, [] if observation_mode == "legacy" else ["first_flight_evidence"], f"{arm} observation capability")
            bench.validate_policy_audit(initial["audit"], fingerprint)
            result = fresh_seed(worker, scenario, protocol, seed, trace_path, observation_mode)
            worker.close()
            worker = None
        finally:
            if worker is not None:
                worker.close()
        bench.validate_policy_audit(result["policy_audit"], fingerprint)
        equal(policy_inventory(root), files, f"{arm} policy inventory after run")
        result.update(schema=RAW_SCHEMA, generation=arm, variant="full", scenario=sid, observation_mode=observation_mode,
                      mode="repetition", protocol_sha256=protocol_hash, policy_root=str(root), policy_files=files,
                      policy_initial=initial, plan_path=str(Path(plan).resolve()), plan_sha256=bench.file_hash(plan),
                      elapsed_seconds=time.monotonic() - start)
        bench.write_new(result_path, result)
        print(json.dumps({"status": "complete", "arm": arm, "scenario": sid, "seed": seed, "n": result["n"],
                          "elapsed_seconds": round(result["elapsed_seconds"], 2)}), flush=True)


def repeat(snapshot, out, arms, sid, seeds, plan, jobs, chunk):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    logs.mkdir(exist_ok=True)
    pending = [(arm, seeds[i:i + chunk]) for arm in arms for i in range(0, len(seeds), chunk)]
    running, failures = [], []
    while pending or running:
        while pending and len(running) < jobs:
            arm, part = pending.pop(0)
            stamp = time.time_ns()
            stdout = (logs / f"{arm}_{part[0]}_{stamp}.out.txt").open("x", encoding="utf-8")
            stderr = (logs / f"{arm}_{part[0]}_{stamp}.err.txt").open("x", encoding="utf-8")
            command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "repeat-one", "--snapshot", str(snapshot),
                       "--out", str(out), "--arm", arm, "--scenario", sid, "--plan", str(plan), "--seeds", *map(str, part)]
            running.append((arm, part, subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr), stdout, stderr))
        time.sleep(0.5)
        for item in list(running):
            arm, part, process, stdout, stderr = item
            code = process.poll()
            if code is None:
                continue
            stdout.close()
            stderr.close()
            running.remove(item)
            if code != 0:
                failures.append({"arm": arm, "first_seed": part[0], "exit": code})
    return {"status": "failed" if failures else "complete", "failures": failures, "out": str(out)}


def repeat_judge(out_dir, plan, out):
    plan_value = read_json(plan)
    plan_sha = bench.file_hash(plan)
    protocol = bench.load_protocol(PROTOCOL)
    protocol_hash = bench.file_hash(PROTOCOL)
    confidence = protocol["metrics"]["paired_confidence"]
    seeds = plan_value["seeds"]
    sid = "B6"
    scenario = {s["id"]: s for s in protocol["scenarios"]}[sid]
    inventory = family_inventory()
    refs, _ = load_references(protocol, protocol_hash, inventory)
    runs, files = {}, {}
    for arm in plan_value["arms"]:
        items = []
        for seed in seeds:
            path = Path(out_dir) / arm / sid / f"seed{seed:05d}.json"
            run = read_json(path)
            equal((run["schema"], run["generation"], run["scenario"], run["seed"], run["mode"], run["plan_sha256"], run["protocol_sha256"]),
                  (RAW_SCHEMA, arm, sid, seed, "repetition", plan_sha, protocol_hash), "repetition run identity")
            equal(run["n"], sum(phase["length"] for phase in scenario["phases"]), "repetition length")
            equal(bench.file_hash(run["trace_path"]), run["trace_sha256"], "repetition trace")
            bench.validate_policy_audit(run["policy_audit"], {"source_root": run["policy_root"], "files": run["policy_files"]})
            files[str(path)] = bench.file_hash(path)
            items.append(run)
        runs[arm] = items
    identity = []
    for a, b in zip(runs["v331_none"], runs["v32"]):
        rows_a, rows_b = load_rows(a), load_rows(b)
        first = next((x["index"] for x, y in zip(rows_a, rows_b) if any(x[name] != y[name] for name in TRAJECTORY_FIELDS)), None)
        identity.append({"seed": a["seed"], "first_trajectory_difference": first, "summary_identical": a["summary"] == b["summary"],
                         "action_counts_identical": a["action_counts"] == b["action_counts"]})
    l3_tables, l3_source = load_pool(L3_POOL, L3_REPORT, PROTOCOL, refs, "n131072_l3_joint")
    precision_protocol = ROOT / "g3/v33/bench_overlays/L1_precision_v1_protocol.json"
    p_tables, p_source = load_pool(PRECISION_POOL, PRECISION_REPORT, precision_protocol, refs, "n1048576_l1_precision")
    tables = {"n131072_l3_joint": l3_tables, "n1048576_l1_precision": p_tables}
    results = {}
    for label, table in tables.items():
        results[label] = []
        for candidate, baseline, role in plan_value["comparisons"]:
            item = bench_report.direct_comparison(runs[candidate], runs[baseline], table, confidence)
            item.update(candidate={"generation": candidate}, baseline={"generation": baseline}, scenario=sid)
            item["regression_gate"] = bench_report.threshold_from_summary(item["seed_summary"], protocol["thresholds"]["max_regression_vs_v31_ms"],
                                                                           mc_bound=item["shared_mc_bound_ms"], inclusive=True)
            entry = compact_comparison(item)
            entry["role"] = role
            results[label].append(entry)
    unplanned = {}
    for label, table in tables.items():
        item = bench_report.direct_comparison(runs["l1_c1"], runs["v32"], table, confidence)
        item.update(candidate={"generation": "l1_c1"}, baseline={"generation": "v32"}, scenario=sid)
        item["regression_gate"] = bench_report.threshold_from_summary(item["seed_summary"], protocol["thresholds"]["max_regression_vs_v31_ms"],
                                                                       mc_bound=item["shared_mc_bound_ms"], inclusive=True)
        unplanned[label] = compact_comparison(item)
    value = {"schema": "padfec.v33fix.b6_independent_repetition/1", "plan_path": str(Path(plan).resolve()), "plan_sha256": plan_sha,
             "plan": plan_value, "seeds": len(seeds), "arms": {arm: len(items) for arm, items in runs.items()},
             "connections": sum(run["n"] for items in runs.values() for run in items),
             "none_vs_v32_identity": {"seeds_identical": sum(item["first_trajectory_difference"] is None for item in identity),
                                      "summaries_identical": sum(item["summary_identical"] for item in identity), "by_seed": identity},
             "tables": {"n131072_l3_joint": l3_source, "n1048576_l1_precision": p_source}, "results": results,
             "primary_status": {f'{row["candidate"]}_vs_{row["baseline"]}': row["gate_0_5_ms"] for row in results["n131072_l3_joint"]},
             "unplanned_diagnostic_l1_c1_vs_v32": {"note": "added after the plan was written; audit B-E3 asks for an independent-seed check of the L1 C1 B6 cell; not part of the v3.3.1-dev decision",
                                                   "results": unplanned},
             "files_digest": bench.digest(files)}
    bench.write_new(Path(out), value)
    return {"status": "complete", "primary_status": value["primary_status"],
            "side": {f'{row["candidate"]}_vs_{row["baseline"]}': row["gate_0_5_ms"] for row in results["n1048576_l1_precision"]},
            "identity": value["none_vs_v32_identity"]["seeds_identical"]}


def reference_dirs():
    receipt = read_json(ROOT / "g3/v33/bench_overlays/L1_v1_import.json")
    return [Path(path) for path in receipt["oracle_dirs"]]


def load_references(protocol, protocol_hash, inventory):
    folders = reference_dirs()
    for folder in folders:
        checked(folder / "manifest.json", inventory, "oracle manifest")
        for path in sorted((folder / "results").glob("*.json")):
            checked(path, inventory, "oracle reference")
    from experiments.v33 import bench_oracles
    refs = bench_oracles.references(folders, protocol_hash, protocol)
    equal(set(refs), set(bench.all_contexts(protocol)), "reference contexts")
    return refs, [str(folder) for folder in folders]


def load_pool(pool_dir, report_path, protocol_path, refs, label):
    from experiments.v33 import bench_oracles
    report = read_json(report_path)
    attestation = report["provenance"]["action_pool"]
    equal(Path(attestation["pool_path"]).resolve(), Path(pool_dir).resolve(), label + " pool path")
    protocol = bench.load_protocol(Path(protocol_path))
    protocol_hash = bench.file_hash(protocol_path)
    manifest = read_json(Path(pool_dir) / "manifest.json")
    equal(bench.digest(manifest), attestation["manifest_content_sha256"], label + " manifest content")
    equal(manifest["protocol_sha256"], protocol_hash, label + " protocol")
    bench_oracles.validate_oracle_manifest(manifest, protocol_hash=protocol_hash, mode="actions")
    family = manifest["evaluation_family_size"]
    equal(family, attestation["evaluation_family_size"], label + " family size")
    files = {str(Path(path).resolve()).lower(): value for path, value in attestation["files_sha256"].items()}
    contexts = bench.all_contexts(protocol)
    tables = {}
    for job in manifest["jobs"]:
        path = Path(pool_dir) / "results" / f'{job["job_id"]}.json'
        equal(bench.file_hash(path), files[str(path.resolve()).lower()], label + " result hash")
        item = read_json(path)
        equal(item.get("protocol_sha256"), protocol_hash, label + " result protocol")
        bench_oracles.validate_oracle_result(item, protocol=protocol, context_spec=contexts[job["context_id"]], job=job,
                                            mode="actions", evaluation_family_size=family)
        equal(tuple(item["reference_action"]), tuple(refs[job["context_id"]]["chosen_action"]), label + " reference action")
        equal(manifest["oracle_digests"][job["context_id"]], bench.digest(refs[job["context_id"]]), label + " reference digest")
        tables[job["context_id"], tuple(job["action"])] = item
    samples = sorted({item["n"] for item in tables.values()})
    return tables, {"label": label, "pool_path": str(Path(pool_dir).resolve()), "report_path": str(Path(report_path).resolve()),
                    "report_sha256": bench.file_hash(report_path), "protocol_path": str(Path(protocol_path).resolve()),
                    "protocol_sha256": protocol_hash, "evaluation_family_size": family, "jobs": len(tables),
                    "mc_samples_per_job": samples, "validation_seed": protocol["oracle"]["validation_seed"],
                    "confidence": protocol["oracle"]["confidence"],
                    "result_files_digest": bench.digest({str(Path(pool_dir) / "results" / f'{job["job_id"]}.json'): files[str((Path(pool_dir) / "results" / f'{job["job_id"]}.json').resolve()).lower()] for job in manifest["jobs"]})}


def new_runs(raw, protocol, protocol_hash):
    raw = Path(raw).resolve()
    scenarios = {s["id"]: s for s in protocol["scenarios"]}
    result, files, receipts = {}, {}, set()
    for mode in MODES:
        for sid, scenario in scenarios.items():
            for seed in protocol["seeds"]:
                path = raw / mode / sid / f"seed{seed:05d}.json"
                run = read_json(path)
                equal((run["schema"], run["generation"], run["variant"], run["scenario"], run["observation_mode"], run["seed"], run["mode"]),
                      (RAW_SCHEMA, ALIASES[mode], "full", sid, mode, seed, "full"), "new run identity")
                equal(run["protocol_sha256"], protocol_hash, "new run protocol")
                equal(run["n"], sum(phase["length"] for phase in scenario["phases"]), "new run length")
                receipt = read_json(run["snapshot_receipt_path"])
                equal(bench.file_hash(run["snapshot_receipt_path"]), run["snapshot_receipt_sha256"], "snapshot receipt")
                validate_audit(run["policy_audit"], receipt)
                validate_initial(run["policy_initial"], receipt)
                equal(bench.file_hash(run["trace_path"]), run["trace_sha256"], "new trace")
                receipts.add(run["snapshot_receipt_sha256"])
                files[str(path)] = bench.file_hash(path)
                files[run["trace_path"]] = run["trace_sha256"]
                result[mode, sid, seed] = run
    if len(receipts) != 1:
        raise ValueError("new runs must share one policy snapshot")
    return result, files, receipts.pop()


def relabel(run, generation):
    item = dict(run)
    item["generation"] = generation
    item["variant"] = "full"
    return item


def slim_loader(run):
    rows = []
    with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            equal(row.get("index"), len(rows), "trace index")
            rows.append({name: row.get(name) for name in SLIM_FIELDS})
    equal(len(rows), run["n"], "trace length")
    actual = collections.Counter((row["context_id"], tuple(row["action"])) for row in rows)
    expected = {key: value * run["n"] for key, value in bench_report.weights(run).items()}
    equal(dict(actual), expected, "trace action counts")
    return rows


def short_summary(value):
    return {key: value.get(key) for key in ("n", "mean", "lower", "upper", "half_width")}


def short_gate(value):
    keys = ("status", "estimate", "lower", "upper", "adjusted_lower", "adjusted_upper", "threshold", "mc_bound", "selection_gap", "inclusive", "absolute")
    return {key: value.get(key) for key in keys if key in value}


def compact_group(group):
    expected = group["expected_regret"]
    gates = {}
    for name, gate in group["gates"].items():
        if name == "adaptation":
            gates[name] = {key: gate[key] for key in ("status", "threshold", "expected_seed_count", "observed_cases", "censored_count", "confirmed_start_distribution")}
        else:
            gates[name] = short_gate(gate)
    observed = {name: short_summary(group["observed"][name]) for name in (
        "mean_hct_ms", "failure_rate", "mean_extra_server_bytes", "mean_extra_first_flight_bytes", "p_bias_high_phase",
        "p_mae_high_phase", "alarm_rate_per_1000", "guard_alarm_fraction")}
    convergence = group.get("p_convergence")
    if convergence is not None:
        convergence = {"predecision_tail_p_mean": short_summary(convergence["predecision_tail_p_mean"]),
                       "gate_below_0_01": short_gate(convergence["predecision_tail_gate"]),
                       "final_post_observation_p_mean": short_summary(convergence["final_post_observation_p_mean"])}
    return {"generation": group["generation"], "scenario": group["scenario"],
            "expected_regret": {"status": expected["status"], "seed": short_summary(expected["seed_summary"]),
                                "seed_estimates": [row["mean_gap_ms"] for row in expected["seed_estimates"]],
                                "shared_mc_bound_ms": expected["shared_mc_bound_ms"],
                                "selection_gap_bound_ms": expected["selection_gap_bound_ms"],
                                "lower_bound_ms": expected["lower_bound_ms"], "upper_bound_ms": expected["upper_bound_ms"],
                                "missing": expected["missing"]},
            "gates": gates, "observed": observed, "p_convergence": convergence,
            "unknown_cost_rows": sum(row["unknown_cost_rows"] for row in group["trace_metrics_by_seed"]),
            "longest_confirmed_suboptimal_episode_max": max(row["longest_confirmed_suboptimal_episode"] for row in group["trace_metrics_by_seed"])}


def compact_comparison(item):
    gate = item["regression_gate"]
    return {"candidate": item["candidate"]["generation"], "baseline": item["baseline"]["generation"], "scenario": item["scenario"],
            "status": item["status"], "mean_ms": item["seed_summary"]["mean"], "seed_lower_ms": item["seed_summary"]["lower"],
            "seed_upper_ms": item["seed_summary"]["upper"], "shared_mc_bound_ms": item["shared_mc_bound_ms"],
            "adjusted_lower_ms": gate["adjusted_lower"], "adjusted_upper_ms": gate["adjusted_upper"],
            "gate_0_5_ms": gate["status"], "point_pass": gate["point_pass"],
            "upper_below_zero": gate["adjusted_upper"] is not None and gate["adjusted_upper"] < 0,
            "lower_above_zero": gate["adjusted_lower"] is not None and gate["adjusted_lower"] > 0,
            "seed_estimates": [row["mean_delta_ms"] for row in item["seed_estimates"]],
            "realized_hct_diagnostic": short_summary(item["realized_hct_diagnostic"]), "missing": item["missing"]}


def evaluate_table(label, runs, extra, refs, tables, protocol):
    confidence = protocol["metrics"]["paired_confidence"]
    scenarios = {s["id"]: s for s in protocol["scenarios"]}
    report = bench_report.aggregate(runs, refs, tables, protocol, trace_loader=slim_loader)
    by_group = collections.defaultdict(list)
    for run in runs + extra:
        by_group[run["generation"], run["scenario"]].append(run)
    for key in by_group:
        by_group[key].sort(key=lambda row: row["seed"])
    groups = []
    for group in report["groups"]:
        group["p_convergence"] = legacy.convergence(group, by_group[group["generation"], group["scenario"]], scenarios[group["scenario"]], protocol)
        groups.append(compact_group(group))
    comparisons = []
    for candidate, baseline in PAIRS:
        for sid in scenarios:
            item = bench_report.direct_comparison(by_group[candidate, sid], by_group[baseline, sid], tables, confidence)
            item.update(candidate={"generation": candidate, "variant": "full"}, baseline={"generation": baseline, "variant": "full"}, scenario=sid)
            item["regression_gate"] = bench_report.threshold_from_summary(item["seed_summary"], protocol["thresholds"]["max_regression_vs_v31_ms"],
                                                                           mc_bound=item["shared_mc_bound_ms"], inclusive=True)
            comparisons.append(compact_comparison(item))
    noninferiority = {}
    for candidate, baseline in PAIRS:
        cells = [row for row in comparisons if row["candidate"] == candidate and row["baseline"] == baseline]
        statuses = collections.Counter(row["gate_0_5_ms"] for row in cells)
        noninferiority[candidate + "_vs_" + baseline] = {
            "status": bench_report._all_status([row["gate_0_5_ms"] for row in cells]), "cell_count": len(cells),
            "pass": statuses["pass"], "fail": statuses["fail"], "inconclusive": statuses["inconclusive"],
            "missing_cells": [row["scenario"] for row in cells if row["missing"]],
            "decrease_cells": [row["scenario"] for row in cells if row["upper_below_zero"]],
            "increase_cells": [row["scenario"] for row in cells if row["lower_above_zero"]],
            "rule": "every scenario subcell must pass the 0.5 ms inclusive upper bound; no pooled cancellation"}
    adoption = {"rule": "v331_none and v331_c1 must each pass all 15 cells against v32 at 0.5 ms (TASKS.md L common rule 1)",
                "pairs": {f"{c}_vs_{b}": noninferiority[f"{c}_vs_{b}"]["status"] for c, b in ADOPTION_PAIRS}}
    adoption["status"] = bench_report._all_status(list(adoption["pairs"].values()))
    return {"label": label, "groups": groups, "comparisons": comparisons, "noninferiority": noninferiority, "adoption_floor": adoption,
            "aggregate_status": report["status"], "aggregate_missing": report["missing"]}


def side_by_side(results):
    keys = list(results)
    rows = []
    first = results[keys[0]]["comparisons"]
    for index, item in enumerate(first):
        entry = {"candidate": item["candidate"], "baseline": item["baseline"], "scenario": item["scenario"]}
        for key in keys:
            other = results[key]["comparisons"][index]
            equal((other["candidate"], other["baseline"], other["scenario"]), (item["candidate"], item["baseline"], item["scenario"]), "comparison order")
            entry[key] = {name: other[name] for name in ("mean_ms", "seed_lower_ms", "seed_upper_ms", "shared_mc_bound_ms", "adjusted_lower_ms", "adjusted_upper_ms", "gate_0_5_ms")}
        rows.append(entry)
    return rows


def after_repetition(results, repetition):
    if repetition is None:
        return None
    seeds = repetition["plan"]["seeds"]
    output = {"rule": f"B6 cells are replaced by the status of the independent repetition (seeds {min(seeds)}..{max(seeds)}) on the primary N=131072 table; its plan was written after seeing seeds 31..50 and before running any seed above 50, so it is not a pre-registration; all other cells keep the seeds 31..50 status",
              "repetition_primary_status": repetition["primary_status"]}
    for label, result in results.items():
        pairs = {}
        for candidate, baseline in ADOPTION_PAIRS + [("v331_c1", "l1_c1"), ("v331_none", "l1_none")]:
            cells = {row["scenario"]: row["gate_0_5_ms"] for row in result["comparisons"] if row["candidate"] == candidate and row["baseline"] == baseline}
            key = f"{candidate}_vs_{baseline}"
            if key in repetition["primary_status"]:
                cells["B6"] = repetition["primary_status"][key]
            pairs[key] = {"status": bench_report._all_status(list(cells.values())),
                          "non_pass_cells": {cell: status for cell, status in cells.items() if status != "pass"}}
        floor = bench_report._all_status([pairs[f"{c}_vs_{b}"]["status"] for c, b in ADOPTION_PAIRS])
        output[label] = {"pairs": pairs, "adoption_floor_status": floor}
    return output


def evaluate(raw, compare_path, out, repetition_path=None):
    started = time.monotonic()
    repetition = None
    if repetition_path is not None:
        repetition = read_json(repetition_path)
        equal(repetition.get("schema"), "padfec.v33fix.b6_independent_repetition/1", "repetition schema")
        equal(bench.file_hash(repetition["plan_path"]), repetition["plan_sha256"], "repetition plan")
    rules = read_json(bench_report.RULES)
    equal(bench.file_hash(bench_report.RULES), read_json(L3_REPORT)["provenance"]["reporting_rules_sha256"], "frozen reporting rules")
    protocol = bench.load_protocol(PROTOCOL)
    protocol_hash = bench.file_hash(PROTOCOL)
    inventory = family_inventory()
    refs, oracle_dirs = load_references(protocol, protocol_hash, inventory)
    v31, v32 = baseline_runs("v31", inventory), baseline_runs("v32", inventory)
    l1 = learning_runs("L1_raw_v1_*", "L1_v1.json", MODES, inventory)
    record = learning_runs("L3_raw_v1_*", L3_RECORD_OVERLAY, ("c1",), inventory)
    fresh, fresh_files, snapshot_sha = new_runs(raw, protocol, protocol_hash)
    expected = {(sid, seed) for sid in (s["id"] for s in protocol["scenarios"]) for seed in protocol["seeds"]}
    equal(set(v31), expected, "v31 inventory")
    equal(set(v32), expected, "v32 inventory")
    for mode in MODES:
        equal({(sid, seed) for m, sid, seed in l1 if m == mode}, expected, f"L1 {mode} inventory")
    equal({(sid, seed) for _, sid, seed in record}, expected, "record c1 inventory")
    runs = [relabel(run, "v31") for run in v31.values()] + [relabel(run, "v32") for run in v32.values()]
    runs += [relabel(run, "l1_" + key[0]) for key, run in l1.items()]
    runs += [relabel(run, ALIASES[key[0]]) for key, run in fresh.items()]
    extra = [relabel(run, "record_c1") for run in record.values()]
    trajectory = read_json(compare_path)
    equal(trajectory.get("schema"), COMPARE_SCHEMA, "trajectory comparison schema")
    equal(Path(trajectory["raw"]).resolve(), Path(raw).resolve(), "trajectory comparison raw")
    compared = {(item["mode"], item["scenario"], item["seed"]): item for item in trajectory["runs"]}
    equal(set(compared), set(fresh), "trajectory comparison coverage")
    for key, item in compared.items():
        equal(item["new_trace_sha256"], fresh[key]["trace_sha256"], "trajectory comparison trace")
    l3_tables, l3_source = load_pool(L3_POOL, L3_REPORT, PROTOCOL, refs, "n131072_l3_joint")
    precision_protocol = ROOT / "g3/v33/bench_overlays/L1_precision_v1_protocol.json"
    equal(bench.file_hash(precision_protocol), read_json(PRECISION_REPORT)["provenance"]["evaluation_protocol_sha256"], "precision protocol")
    p_tables, p_source = load_pool(PRECISION_POOL, PRECISION_REPORT, precision_protocol, refs, "n1048576_l1_precision")
    results = {"n131072_l3_joint": evaluate_table("n131072_l3_joint", runs, extra, refs, l3_tables, protocol),
               "n1048576_l1_precision": evaluate_table("n1048576_l1_precision", runs, extra, refs, p_tables, protocol)}
    replay = read_json(REPLAY)
    value = {"schema": REPORT_SCHEMA, "status": "complete", "data_kind": "development_independent_world_simulation",
             "analysis_kind": "post_hoc_development_rejudgement_after_partial_results_were_seen",
             "policy": {"policy_version": POLICY_VERSION, "state_version": STATE_VERSION, "snapshot_receipt_sha256": snapshot_sha,
                        "files": read_json(next(iter(fresh.values()))["snapshot_receipt_path"])["files"]},
             "aliases": {"v331_none": "working-tree v3.3.1-dev, observation mode none (no C1 reply)",
                         "v331_c1": "working-tree v3.3.1-dev, observation mode c1 (passive C1 reply, zero reply cost)",
                         "l1_none": "L1 v3.3-dev none (L1_raw_v1)", "l1_c1": "L1 v3.3-dev c1 (L1_raw_v1)",
                         "record_c1": "L3_record_only_v1 c1 diagnostic arm (L3_raw_v1)", "v31": "W1_raw_v31", "v32": "W1_raw_v32"},
             "comparison_plan": [list(pair) for pair in PAIRS], "adoption_pairs": [list(pair) for pair in ADOPTION_PAIRS],
             "closed_loop": {"raw": str(Path(raw).resolve()), "runs": len(fresh), "connections": sum(run["n"] for run in fresh.values()),
                             "seconds_total": sum(run["elapsed_seconds"] for run in fresh.values()),
                             "trajectory_comparison_path": str(Path(compare_path).resolve()),
                             "trajectory_comparison_sha256": bench.file_hash(compare_path), "trajectory_totals": trajectory["totals"],
                             "trajectory_fields": trajectory["trajectory_fields"],
                             "b11_c1_differences": [compared[key] for key in sorted(compared) if not compared[key]["trajectory_identical"]],
                             "new_files_digest": bench.digest(fresh_files)},
             "replay": {"path": str(REPLAY), "sha256": bench.file_hash(REPLAY), "none": replay["summary"]["none"]["total"],
                        "c1": replay["summary"]["c1"]["total"], "mismatches": replay["mismatches"]},
             "inputs": {"protocol_sha256": protocol_hash, "reporting_rules_sha256": bench.file_hash(bench_report.RULES),
                        "l3_family_plan_sha256": L3_FAMILY_SHA256, "oracle_dirs": oracle_dirs,
                        "reference_digests": {cid: bench.digest(ref) for cid, ref in sorted(refs.items())},
                        "baseline_runs": {"v31": len(v31), "v32": len(v32), "l1": len(l1), "record_c1": len(record)},
                        "historical_files_checked_against_l3_family_inventory": True,
                        "tables": {"n131072_l3_joint": l3_source, "n1048576_l1_precision": p_source}},
             "results": results, "side_by_side": side_by_side(results),
             "b6_independent_repetition": None if repetition is None else {**repetition, "path": str(Path(repetition_path).resolve()),
                                                                           "sha256": bench.file_hash(repetition_path)},
             "adoption_after_repetition": after_repetition(results, repetition),
             "scope": {"seed_interval": "95% Student t over 20 seeds", "mc": "99% normal approximation per action job family; no division by sqrt(seeds)",
                       "combined_bounds_are_simultaneous_95_percent": False,
                       "precision_table": "N=1048576 seed 850001 prefix-overlapping post-hoc development table; applied to every comparison equally",
                       "world": "independent event world W0 shares policy packetization, parity overhead, race table and 41.983 B ACK constants (audit C-E3)",
                       "c1": "passive observer, reply cost not charged to HCT, amplification budget or connection spacing",
                       "measurement": "no real QUIC measurement"},
             "source_sha256": {name: bench.file_hash(Path(__file__).with_name(name)) for name in ("v33fix_rejudge.py", "bench_report.py", "bench_metrics.py", "bench_learning_report.py", "bench_learning_l3.py", "bench.py", "policy_worker.py", "worldsim.py", "worldparams.json", "first_flight_observer.py", "oracle.py", "bench_oracles.py")},
             "rules_schema": rules["schema"], "elapsed_seconds": None}
    value["elapsed_seconds"] = time.monotonic() - started
    bench.write_new(Path(out), value)
    return {"status": "complete", "out": str(Path(out).resolve()),
            "adoption": {key: item["adoption_floor"] for key, item in results.items()},
            "noninferiority": {key: {k: v["status"] for k, v in item["noninferiority"].items()} for key, item in results.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot")
    snap.add_argument("--out", type=Path, required=True)
    for name in ("collect", "collect-one"):
        sub = commands.add_parser(name)
        sub.add_argument("--snapshot", type=Path, required=True)
        sub.add_argument("--out", type=Path, required=True)
        sub.add_argument("--seeds", type=int, nargs="+", required=True)
        if name == "collect":
            sub.add_argument("--modes", nargs="+", choices=MODES, required=True)
            sub.add_argument("--scenarios", nargs="+", required=True)
            sub.add_argument("--jobs", type=int, default=6)
        else:
            sub.add_argument("--mode", choices=MODES, required=True)
            sub.add_argument("--scenario", required=True)
    comp = commands.add_parser("compare")
    comp.add_argument("--raw", type=Path, required=True)
    comp.add_argument("--out", type=Path, required=True)
    judge = commands.add_parser("evaluate")
    judge.add_argument("--raw", type=Path, required=True)
    judge.add_argument("--compare", type=Path, required=True)
    judge.add_argument("--repetition", type=Path)
    judge.add_argument("--out", type=Path, required=True)
    for name in ("repeat", "repeat-one"):
        sub = commands.add_parser(name)
        sub.add_argument("--snapshot", type=Path, required=True)
        sub.add_argument("--out", type=Path, required=True)
        sub.add_argument("--plan", type=Path, required=True)
        sub.add_argument("--scenario", default="B6")
        sub.add_argument("--seeds", type=int, nargs="+", required=True)
        if name == "repeat":
            sub.add_argument("--arms", nargs="+", required=True)
            sub.add_argument("--jobs", type=int, default=10)
            sub.add_argument("--chunk", type=int, default=20)
        else:
            sub.add_argument("--arm", required=True)
    rjudge = commands.add_parser("repeat-judge")
    rjudge.add_argument("--raw", type=Path, required=True)
    rjudge.add_argument("--plan", type=Path, required=True)
    rjudge.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        result = make_snapshot(args.out)
    elif args.command == "collect":
        result = collect(args.snapshot, args.out, args.modes, args.scenarios, args.seeds, args.jobs)
    elif args.command == "collect-one":
        collect_one(args.snapshot, args.out, args.mode, args.scenario, args.seeds)
        result = {"status": "complete"}
    elif args.command == "compare":
        result = compare(args.raw, args.out)
    elif args.command == "repeat":
        result = repeat(args.snapshot, args.out, args.arms, args.scenario, args.seeds, args.plan, args.jobs, args.chunk)
    elif args.command == "repeat-one":
        repeat_one(args.snapshot, args.out, args.arm, args.scenario, args.seeds, args.plan)
        result = {"status": "complete"}
    elif args.command == "repeat-judge":
        result = repeat_judge(args.raw, args.plan, args.out)
    else:
        result = evaluate(args.raw, args.compare, args.out, args.repetition)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)[:4000], flush=True)
    return 0 if not isinstance(result, dict) or result.get("status") != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
