import sys
sys.dont_write_bytecode = True
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
text = (ROOT / "experiments/v33/bench_learning_j1.py").read_text(encoding="utf-8")
text = text.replace("bench_learning_j1.py", "bench_learning_j6.py").replace("/j1-1", "/j6-1")
text = text.replace("tail_variant", "budget_variant").replace("cost_only", "margin_zero").replace("J1 snapshot", "J6 snapshot")
text = text.replace('), 7, "J6 snapshot state version")', '), 8, "J6 snapshot state version")').replace('"state_version": 7', '"state_version": 8')
text = text.replace('"policy_worker.py", "worldsim.py"', '"policy_worker_j6.py", "policy_bridge_j6.py", "preflight_observer.py", "worldsim.py"')
text = text.replace('from experiments.v33.policy_worker import first_flight_evidence', 'from experiments.v33.policy_worker_j6 import first_flight_evidence\nfrom experiments.v33.policy_bridge_j6 import PolicyWorker\nfrom experiments.v33.preflight_observer import make_world_preflight')
text = text.replace('"feedback_grace_ms": 200, "crc_list_limit": 64, "passive": True}', '"feedback_grace_ms": 200, "crc_list_limit": 64, "passive": True,\n            "preflight": "all_modes_received_ack_before_first_large_world_proxy",\n            "preflight_margin_server_bytes": 30, "preflight_zero_is_missing": True}')
text = text.replace('    if "first_flight_evidence" not in initial.get("capabilities", {}).get("observe_extra", []):\n        raise ValueError("policy must explicitly support first-flight evidence")', '    if set(initial.get("capabilities", {}).get("observe_extra", [])) != {"first_flight_evidence", "preflight"}:\n        raise ValueError("policy must explicitly support first-flight and preflight evidence")')
text = text.replace('trace=observation_mode != "none"', 'trace=True')
text = text.replace('                    observed_rtt.observe(observation)', '                    preflight_projection = make_world_preflight(observation)\n                    observed_rtt.observe(observation)')
text = text.replace('observe_input["optional"] = {"first_flight_evidence": projection["evidence"]}', 'observe_input["optional"] = {"first_flight_evidence": projection["evidence"],\n                                                 "preflight": preflight_projection["evidence"]}')
text = text.replace('"observation_mode": observation_mode, "observer_diagnostics": projection["diagnostics"]}', '"observation_mode": observation_mode, "observer_diagnostics": projection["diagnostics"],\n                        "preflight_diagnostics": preflight_projection["diagnostics"],\n                        "preflight_received": [[r["time_ms"], r["kind"], r["size"]] for r in observation["trace"] if r["event"] == "client_receive"]}')
text = text.replace('{"first_flight_evidence"}, "optional evidence boundary")', '{"first_flight_evidence", "preflight"}, "optional evidence boundary")')
needle = '            evidence = request["optional"]["first_flight_evidence"]'
addition = '''            preflight_replayed = make_world_preflight({"model_kind": "independent_event_world",
                "srv_bytes": request["srv_bytes"], "trace": [{"event": "client_receive", "time_ms": time,
                "kind": kind, "size": size} for time, kind, size in row["preflight_received"]]})
            equal(preflight_replayed["evidence"], request["optional"]["preflight"], "received preflight evidence")
            equal(preflight_replayed["diagnostics"], row["preflight_diagnostics"], "received preflight diagnostics")
'''
assert text.count(needle) == 1
text = text.replace(needle, addition + needle)
text = text.replace('worker = bench.PolicyWorker(', 'worker = PolicyWorker(')
with (ROOT / "experiments/v33/bench_learning_j6.py").open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
assert '"state_version": 7' not in text and "bench.PolicyWorker(" not in text
print("created J6 collector")
