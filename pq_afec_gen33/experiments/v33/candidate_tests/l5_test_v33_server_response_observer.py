from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from experiments.v33.server_response_observer import make_world_server_response
from experiments.v33.worldsim import Action, World, WorldContext
from padfec3 import server_size


def received(time, kind, size, index=None):
    return {"event": "client_receive", "time_ms": time, "kind": kind, "size": size, "index": index}


def data(rows, ok=True, hct=5):
    return {"model_kind": "independent_event_world", "trace": rows, "ok": ok, "hct": hct,
            "srv_bytes": sum(row["size"] for row in rows if row["event"] == "client_receive")}


def sample_rows():
    return [received(0, "ack", 41), received(1, "data", 100, 2), received(2, "data", 1280, 0),
            received(3, "data", 1280, 0), received(4, "data", 1100, 1),
            {"event": "handshake_complete", "time_ms": 5}, received(6, "data", 1100, 1)]


def test_reordering_duplicate_and_post_completion_accounting_without_truth():
    original = data(sample_rows())
    result = make_world_server_response(original)
    value = result["evidence"]
    assert value["packets"] == [[0, 1280], [1, 1100], [2, 100]]
    assert value["duplicate_data_bytes"] == 1280
    assert value["other_received_bytes"] == 41 and value["post_complete_bytes"] == 1100
    assert server_size.normalize(value, original["srv_bytes"], True)["sample"]["prefix"] == 2380
    changed = deepcopy(original)
    changed.update(server_first_flight_sizes=[9999], server_retransmission_bytes=50000, selected_cert_bytes=1)
    changed["trace"].insert(0, {"event": "server_send", "time_ms": -100, "size": 999999})
    assert make_world_server_response(changed) == result
    assert not result["diagnostics"]["actual_quic_response_identity_validated"]


def test_incomplete_prefix_is_never_complete_even_when_contiguous():
    value = data([received(1, "data", 1280, i) for i in range(3)], ok=False, hct=None)
    result = make_world_server_response(value)["evidence"]
    assert not result["complete"]
    assert server_size.normalize(result, value["srv_bytes"], False)["sample"] is None


@pytest.mark.parametrize("mutation", ["duplicate_size", "time", "no_complete", "gap", "total", "hct", "bool_index", "duplicate_complete"])
def test_inconsistent_receive_evidence_is_rejected(mutation):
    value = data(sample_rows())
    if mutation == "duplicate_size":
        value["trace"][3]["size"] = 1000
    elif mutation == "time":
        value["trace"][3]["time_ms"] = -1
    elif mutation == "no_complete":
        value["trace"] = [row for row in value["trace"] if row["event"] != "handshake_complete"]
    elif mutation == "gap":
        value["trace"][1]["index"] = 4
    elif mutation == "total":
        value["srv_bytes"] += 1
    elif mutation == "hct":
        value["hct"] += 1
    elif mutation == "bool_index":
        value["trace"][1]["index"] = True
    else:
        value["trace"].append({"event": "handshake_complete", "time_ms": 7})
    with pytest.raises(ValueError):
        make_world_server_response(value)


def test_frozen_world_received_identity_matches_truth_only_after_completion():
    checks = duplicates = 0
    for k, cert, p, down, u, retry in ((2, 9000, 0.02, 0, 2, False), (2, 16000, 0.25, 0.05, 2, False),
                                     (1, 4032, 0, 0.1, 0, False), (2, 6000, 0.08, 0, 10, True)):
        ctx = WorldContext(k=k, cert_bytes=cert, p=p, s2c_loss=down, uplink_mbps=u, retry=retry)
        plain_world, traced_world = World(seed=31), World(seed=31)
        for i in range(20):
            action = Action(0, 3, 1) if i % 2 else Action()
            plain = plain_world.sample(ctx, action, connection=i, trace=False)
            observed = traced_world.sample(ctx, action, connection=i, trace=True)
            assert {k: v for k, v in plain.items() if k != "trace"} == {k: v for k, v in observed.items() if k != "trace"}
            value = make_world_server_response(observed)["evidence"]
            normalized = server_size.normalize(value, observed["srv_bytes"], observed["ok"])
            if observed["ok"]:
                assert [size for _, size in value["packets"]] == observed["server_first_flight_sizes"]
                assert normalized["sample"]["bytes"] == sum(observed["server_first_flight_sizes"])
            duplicates += value["duplicate_data_bytes"]
            checks += 1
    assert checks == 80 and duplicates > 0


def worker_requests():
    root = Path(__file__).resolve().parents[3]
    value = data(sample_rows())
    evidence = make_world_server_response(value)["evidence"]
    return root, [{"op": "init", "source_root": str(root / "g3/v33/policy_snapshots/L5_v1"), "W": 1280, "u_mbps": 2, "c_pkt": 41.983, "variant": "full"},
                  {"op": "decide", "rtt_ms": None},
                  {"op": "observe", "action": [0, 0, 0], "hct_ms": 5, "ok": True, "k_obs": 2,
                   "srv_bytes": value["srv_bytes"], "rtt_ms": 50, "j_pred": None,
                   "optional": {"server_response": evidence}},
                  {"op": "decide", "rtt_ms": 50}, {"op": "snapshot"}]


def run_worker(root, requests):
    process = subprocess.run([sys.executable, "-I", "-B", str(root / "experiments/v33/policy_worker_l5.py")],
                             input="".join(json.dumps(value) + "\n" for value in requests), cwd=root,
                             capture_output=True, text=True, encoding="utf-8", timeout=30)
    return process, [json.loads(line) for line in process.stdout.splitlines()]


def test_worker_declares_response_capability_and_exact_clean_scope():
    root, requests = worker_requests()
    process, rows = run_worker(root, requests)
    assert process.returncode == 0, process.stdout + process.stderr
    assert rows[0]["result"]["state_version"] == 9
    assert rows[0]["result"]["capabilities"]["observe_extra"] == ["first_flight_evidence", "server_response"]
    assert rows[2]["result"]["state"]["S_hat"] == 2480
    assert rows[2]["result"]["state"]["S_scope"] == "complete_response"
    assert rows[3]["result"]["decision"]["size_distribution"][0]["prefix"] == 2380
    audit = rows[-1]["result"]["audit"]
    assert audit["source_unchanged"] and audit["read_only_audit"] and audit["isolated"]
    assert rows[-1]["result"]["serialized"]["size_history"]["seq"] == 1


@pytest.mark.parametrize("mutation", ["hidden", "source", "counts", "failure"])
def test_worker_rejects_unsupported_or_inconsistent_response(mutation):
    root, requests = worker_requests()
    response = requests[2]["optional"]["server_response"]
    if mutation == "hidden":
        response["actual_server_sizes"] = [5000]
    elif mutation == "source":
        response["source"] = "server_sent"
    elif mutation == "counts":
        response["duplicate_data_bytes"] += 1
    else:
        requests[2]["ok"] = False
        requests[2]["hct_ms"] = None
    process, rows = run_worker(root, requests)
    assert process.returncode == 2 and not rows[-1]["ok"]
