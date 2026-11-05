from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments.v33 import bench, bench_learning_l2 as collector
from padfec import policy
from padfec3 import decide3, learn3


ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "g3/v33/policy_snapshots/L2_v1"
C_PKT = policy.C_PKT_POLICY_DEFAULT


def synthetic_row():
    state = learn3.new_state()
    state.k_hist = [2]
    state.S_hist = [18232.0]
    decision = decide3.decide3(state, 1280, 2.0, 50, C_PKT, actions=[(0, 3, 1)])
    info = learn3.observe3(state, decision["action"], 140.0, True, 2, 18232, 45,
                           W=1280, u_mbps=2.0, c_pkt=C_PKT)
    return {"decision": decision, "observation_info": info, "action": list(decision["action"]),
            "policy_decide_input": {"rtt_ms": 50}, "hct_ms": 140, "ok": True}


def test_actual_policy_row_has_decision_boundary_and_temporal_binding():
    row = synthetic_row()
    assert collector.validate_epsilon_row(row, None, "adaptive", 0) == [
        row["observation_info"]["epsilon_a_after"], row["observation_info"]["epsilon_b_after"]]
    assert row["observation_info"]["cutoff_rtt_ms"] == 50
    with pytest.raises(ValueError, match="temporal continuity"):
        collector.validate_epsilon_row(row, [2, 999], "adaptive", 0)


@pytest.mark.parametrize("path,value", [
    (("decision", "class_prediction", "action"), [0, 0, 0]),
    (("decision", "class_prediction", "obs_index"), 1),
    (("decision", "class_prediction", "a"), 2),
    (("observation_info", "cutoff_rtt_ms"), 45),
    (("observation_info", "epsilon_update_eligible"), False),
    (("observation_info", "epsilon_update_reason"), "fixed_epsilon_ablation"),
    (("observation_info", "epsilon_after"), .001),
    (("observation_info", "epsilon_a_after"), -1),
    (("observation_info", "grade"), 0),
])
def test_tampered_trace_cannot_pass_l2_validation(path, value):
    row = synthetic_row()
    target = row
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        collector.validate_epsilon_row(row, None, "adaptive", 0)


def test_old_overlay_is_rejected_before_any_collection(tmp_path):
    path = tmp_path / "overlay.json"
    path.write_text(json.dumps({"schema": "padfec.v33.learning_benchmark/1"}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        collector.load_overlay(path)


def test_state_five_survives_actual_isolated_worker_exchange(tmp_path):
    scenario = {"context": {"w": 1280, "uplink_mbps": 2.0}}
    worker = bench.PolicyWorker(SNAPSHOT, scenario, {"c_pkt": C_PKT}, "full", tmp_path / "worker.stderr.txt")
    try:
        assert worker.initial["state_version"] == 5
        previous = None
        for index in range(3):
            decision = worker.request({"op": "decide", "destination": "d", "rtt_ms": 50})["decision"]
            observation = worker.request({"op": "observe", "destination": "d", "rtt_ms": 45,
                "action": decision["action"], "hct_ms": 80, "ok": True, "k_obs": 2,
                "srv_bytes": 18232, "j_pred": decision["j3_pred_pre_ms"],
                "optional": {"first_flight_evidence": {"src": "none", "sent": 0, "lost": 0, "bitmap": None, "trunc": False}}})["observation"]
            row = {"decision": decision, "observation_info": observation, "action": decision["action"],
                   "policy_decide_input": {"rtt_ms": 50}, "hct_ms": 80, "ok": True}
            previous = collector.validate_epsilon_row(row, previous, "adaptive", index)
        snapshot = worker.request({"op": "snapshot", "destination": "d"})
        assert snapshot["serialized"]["v"] == 5
        assert snapshot["serialized"]["class_pending"] is None
        assert snapshot["serialized"]["class_epsilon"]["updates"] == 2
        assert snapshot["audit"]["source_unchanged"]
    finally:
        worker.close()
