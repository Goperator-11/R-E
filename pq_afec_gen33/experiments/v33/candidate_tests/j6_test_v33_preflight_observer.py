import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33.preflight_observer import make_world_preflight
from experiments.v33.worldsim import Action, World, WorldContext


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/J6_v1"


def row(time, kind, size):
    return {"event": "client_receive", "time_ms": time, "kind": kind, "size": size}


def data(rows):
    return {"model_kind": "independent_event_world", "trace": rows,
            "srv_bytes": sum(r["size"] for r in rows if r.get("event") == "client_receive")}


def test_arrived_ack_prefix_only_and_no_hidden_send_fields():
    rows = [{"event": "server_send", "time_ms": 0, "kind": "ack", "size": 99},
            row(1, "retry", 50), row(2, "ack", 41), row(3, "ack", 42),
            row(4, "data", 1280), row(5, "ack", 43), row(6, "data", 700)]
    result = make_world_preflight(data(rows))
    assert result["evidence"]["small_initial_sizes"] == [41, 42]
    assert result["evidence"]["first_large_seen"] is True
    assert result["diagnostics"]["observed_preflight_bytes"] == 83
    assert result["diagnostics"]["first_large_ms"] == 4
    assert result["diagnostics"]["response_received_bytes"] == 2073
    assert result["diagnostics"]["unreceived_server_bytes_used"] is False
    changed = data(rows)
    changed["server_total_sent_bytes"] = 999999
    changed["server_dgram_sizes"] = [41, 41, 41, 1280]
    changed["arrivals"] = [{"lost": True, "size": 100}]
    assert make_world_preflight(changed) == result


def test_empty_and_small_only_are_not_confirmed_zero_budget():
    for rows, seen in (([], False), ([row(1, "ack", 41)], False), ([row(1, "data", 1280)], True)):
        result = make_world_preflight(data(rows))
        assert result["evidence"]["first_large_seen"] is seen
        assert result["evidence"]["source"] == "world_arrival_proxy"


@pytest.mark.parametrize("mutation", ["missing", "byte_sum", "negative_time", "backward", "nan", "bool_size", "bad_size", "model"])
def test_bad_trace_is_rejected(mutation):
    value = data([row(1, "ack", 41), row(2, "data", 1280)])
    if mutation == "missing":
        value["trace"] = []
    elif mutation == "byte_sum":
        value["srv_bytes"] += 1
    elif mutation == "negative_time":
        value["trace"][0]["time_ms"] = -0.5
    elif mutation == "backward":
        value["trace"][1]["time_ms"] = 0
    elif mutation == "nan":
        value["trace"][0]["time_ms"] = float("nan")
    elif mutation == "bool_size":
        value["trace"][0]["size"] = True
    elif mutation == "bad_size":
        value["trace"][0]["size"] = -1
    elif mutation == "model":
        value["model_kind"] = "policy_equivalent"
    with pytest.raises(ValueError):
        make_world_preflight(value)


def test_trace_collection_does_not_change_world_or_random_schedule():
    path = ROOT / "g3/v33/bench_protocol.json"
    protocol = json.loads(path.read_text(encoding="utf-8"))
    from experiments.v33 import bench
    checks = 0
    for scenario in protocol["scenarios"]:
        for phase in scenario["phases"]:
            context = bench.mixture_context(bench.context_spec(scenario, phase), protocol["seeds"][0], 0)
            for action in (Action(0, 0, 0), Action(7, 0, 3), Action(12, 0, 3), Action(0, 3, 1)):
                first = World(params=scenario["world_params"], seed=protocol["seeds"][0])
                second = World(params=scenario["world_params"], seed=protocol["seeds"][0])
                for index in range(3):
                    plain = first.sample(context, action, connection=index, trace=False)
                    traced = second.sample(context, action, connection=index, trace=True)
                    assert {k: v for k, v in plain.items() if k != "trace"} == {k: v for k, v in traced.items() if k != "trace"}
                    result = make_world_preflight(traced)
                    assert result["diagnostics"]["received_server_bytes"] == traced["srv_bytes"]
                    assert result["diagnostics"]["actual_quic_initial_classifier_validated"] is False
                    checks += 1
    assert checks >= 180


def run_worker(requests):
    process = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "experiments/v33/policy_worker_j6.py")],
                             input="".join(json.dumps(value) + "\n" for value in requests),
                             cwd=ROOT, text=True, encoding="utf-8", capture_output=True, timeout=30)
    return process, [json.loads(line) for line in process.stdout.splitlines()]


def requests():
    return [{"op": "init", "source_root": str(SNAPSHOT), "W": 1280, "u_mbps": 10, "c_pkt": 41.983, "variant": "full"},
            {"op": "decide", "rtt_ms": None},
            {"op": "observe", "action": [0, 0, 0], "hct_ms": 100, "ok": True, "k_obs": 2,
             "srv_bytes": 7951, "rtt_ms": 100, "j_pred": None,
             "optional": {"first_flight_evidence": {"src": "none", "sent": 0, "lost": 0, "bitmap": None, "trunc": False},
                          "preflight": {"source": "world_arrival_proxy", "small_initial_sizes": [41],
                                        "first_large_seen": True, "srv_bytes_scope": "includes_observed_preflight"}}},
            {"op": "decide", "rtt_ms": 100}, {"op": "snapshot"}]


def test_worker_declares_new_input_and_preserves_isolation():
    process, rows = run_worker(requests())
    assert process.returncode == 0, process.stdout + process.stderr
    assert rows[0]["result"]["capabilities"]["observe_extra"] == ["first_flight_evidence", "preflight"]
    assert rows[0]["result"]["state_version"] == 8
    assert rows[2]["result"]["state"]["S_hat"] == 7910
    assert rows[2]["result"]["state"]["apre_history_count"] == 1
    assert rows[3]["result"]["decision"]["a_pre"] == 41
    assert rows[3]["result"]["decision"]["a_pre_source"] == "received_initial_median"
    assert rows[-1]["result"]["audit"]["source_unchanged"] is True
    assert rows[-1]["result"]["audit"]["read_only_audit"] is True


def test_worker_rejects_extra_world_fields_and_invalid_budget():
    for mutation in ("source", "extra", "sum", "scope"):
        value = requests()
        target = value[2]["optional"]["preflight"]
        if mutation == "source":
            target["source"] = "server_sent"
        elif mutation == "extra":
            target["true_ack_loss"] = 0
        elif mutation == "sum":
            value[2]["srv_bytes"] = 40
        else:
            target["srv_bytes_scope"] = "unknown"
        process, rows = run_worker(value)
        assert process.returncode == 2
        assert rows[-1]["ok"] is False
