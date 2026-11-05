import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")

def save(path, content):
    compile(content, str(path), "exec")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)

worker = (ROOT / "experiments/v33/policy_worker_j6.py").read_text(encoding="utf-8")
worker = worker.replace('"preflight": "preflight_observation"', '"server_response": "server_response"')
worker = worker.replace('"apre_history_count": len(getattr(state, "apre_hist", [])),', '"size_window_count": len(state.size_history["window"]), "size_catalog_count": len(state.size_history["catalog"]), "size_reset_count": state.size_history["resets"],')
worker = worker.replace('self.learn.preflight.normalize(value, request.get("srv_bytes"))', 'self.learn.server_size.normalize(value, request.get("srv_bytes"), request["ok"])')
save(ROOT / "experiments/v33/policy_worker_l5.py", worker)
bridge = (ROOT / "experiments/v33/policy_bridge_j6.py").read_text(encoding="utf-8").replace("policy_worker_j6.py", "policy_worker_l5.py")
save(ROOT / "experiments/v33/policy_bridge_l5.py", bridge)
collector = (ROOT / "experiments/v33/bench_learning_j6.py").read_text(encoding="utf-8")
collector = collector.replace("j6", "l5").replace("J6", "L5").replace("budget_variant", "size_variant").replace("margin_zero", "single")
collector = collector.replace('), 8, "L5 snapshot state version")', '), 9, "L5 snapshot state version")').replace('"state_version": 8', '"state_version": 9')
collector = collector.replace("must declare tail variant", "must declare response size variant")
collector = collector.replace("preflight", "server_response")
old = '            "server_response": "all_modes_received_ack_before_first_large_world_proxy",\n            "server_response_margin_server_bytes": "snapshot_full30_single0", "server_response_zero_is_missing": True}'
new = '            "server_response": "all_modes_completed_received_index_proxy",\n            "response_deduplication": "stable_response_index", "response_order": "index_not_arrival",\n            "response_scope": "complete_before_handshake_event_excluding_ACK_retry_duplicates_and_late_receipts",\n            "a_pre": "legacy41_per_prior_original_once", "candidate_margin_server_bytes": 0}'
assert collector.count(old) == 1
collector = collector.replace(old, new)
old = '"server_response_received": [[r["time_ms"], r["kind"], r["size"]] for r in observation["trace"] if r["event"] == "client_receive"]}'
assert collector.count(old) == 1
collector = collector.replace(old, '"server_response_received": server_response_projection["received"]}')
old = '''            server_response_replayed = make_world_server_response({"model_kind": "independent_event_world",
                "srv_bytes": request["srv_bytes"], "trace": [{"event": "client_receive", "time_ms": time,
                "kind": kind, "size": size} for time, kind, size in row["server_response_received"]]})'''
new = '''            server_response_replayed = make_world_server_response({"model_kind": "independent_event_world",
                "srv_bytes": request["srv_bytes"], "ok": row["ok"], "hct": row["hct_ms"],
                "trace": [{"event": "handshake_complete", "time_ms": time} if kind == "complete" else
                          {"event": "client_receive", "time_ms": time, "kind": kind, "size": size, "index": index}
                          for time, kind, size, index in row["server_response_received"]]})'''
assert collector.count(old) == 1
collector = collector.replace(old, new)
assert "preflight" not in collector and '"state_version": 8' not in collector
save(ROOT / "experiments/v33/bench_learning_l5.py", collector)
tests = (ROOT / "tests/test_v33_learning_j6.py").read_text(encoding="utf-8")
tests = tests.replace("j6", "l5").replace("J6", "L5").replace("budget_variant", "size_variant").replace("preflight", "server_response")
tests = tests.replace('"state_version": 8', '"state_version": 9').replace("state_version=8", "state_version=9")
tests = tests.replace('"kind": "data", "size": 1280}', '"kind": "data", "size": 1280, "index": 0}')
old = '"kind": "data", "size": 1679}]} '
needle = '"kind": "data", "size": 1679}]}'
assert tests.count(needle) == 1
tests = tests.replace(needle, '"kind": "data", "size": 1679, "index": 1}] + ([] if connection == self.failure_index else [{"event": "handshake_complete", "time_ms": 100.0}])}')
save(ROOT / "tests/test_v33_learning_l5.py", tests)
check = (RUNS / "j6_collector_check_v1.py").read_text(encoding="utf-8")
check = check.replace("j6", "l5").replace("test_v33_preflight_observer.py", "test_v33_server_response_observer.py").replace("test_padfec3_preflight.py", "test_padfec3_server_size.py").replace("preflight_observer.py", "server_response_observer.py")
save(RUNS / "l5_collector_check_v1.py", check)
print("L5 collector, worker boundary and preserved fixture tests created")
