from copy import deepcopy
from unittest import mock

import pytest

from experiments.v33 import bench_learning_l3 as collector
from padfec import policy
from padfec3 import decide3, learn3, monitor3


C_PKT = policy.C_PKT_POLICY_DEFAULT
CONFIGS = {
    "full": {"enabled": True, "beta": True, "shared": True, "c1_reeval": False},
    "guard_only": {"enabled": False, "beta": False, "shared": False, "c1_reeval": True},
    "record_only": {"enabled": True, "beta": False, "shared": False, "c1_reeval": False},
    "beta_only": {"enabled": True, "beta": True, "shared": False, "c1_reeval": False}}


def sequence(config, count=45):
    state = learn3.new_state()
    rows = []
    with mock.patch.multiple(monitor3, ENABLED=config["enabled"], APPLY_BETA=config["beta"],
                             APPLY_SHARED=config["shared"], C1_REEVAL=config["c1_reeval"]), \
            mock.patch.object(learn3, "class_probabilities", return_value=[.97, .02, .01]):
        for index in range(count):
            action = (0, 3, 1) if index % 2 else (0, 2, 2)
            decision = decide3.decide3(state, 1280, 2.0, 50.0, C_PKT, actions=[action])
            evidence = {"src": "c1", "sent": 6, "lost": 0, "bitmap": None, "trunc": False}
            hct = 300.0 if index < 30 else 50.0
            info = learn3.observe3(state, decision["action"], hct, True, 2, 18232, 45.0,
                                   W=1280, u_mbps=2, c_pkt=C_PKT, arrivals=evidence)
            rows.append({"decision": decision, "observation_info": info, "action": list(decision["action"]),
                         "policy_decide_input": {"rtt_ms": 50.0}, "hct_ms": hct, "ok": True,
                         "policy_observe_input": {"optional": {"first_flight_evidence": evidence}}})
    return rows, state


@pytest.mark.parametrize("variant", list(CONFIGS))
def test_trace_reconstruction_matches_all_final_monitor_fields(variant):
    config = CONFIGS[variant]
    rows, state = sequence(config)
    chain = None
    for index, row in enumerate(rows):
        chain = collector.validate_monitor_row(row, chain, config, index)
    collector.close_value(state.monitor, chain["monitor"], "full monitor reconstruction")
    assert state.arrival_streak == chain["arrival_streak"]
    if variant == "full":
        assert state.monitor["shared_count"] > 0
    if not config["beta"]:
        assert all(row["beta"] == 0 for row in state.monitor["arms"].values())


@pytest.mark.parametrize("path,value", [
    (("decision", "monitor_mode", "beta"), False),
    (("decision", "reeval_feedback_suppressed"), True),
    (("observation_info", "monitor_prediction", "ready"), True),
    (("observation_info", "arrival_streak_after"), 8),
    (("observation_info", "epsilon_after"), .01),
    (("observation_info", "monitor_reason"), None),
])
def test_cold_trace_tampering_is_rejected(path, value):
    rows, _ = sequence(CONFIGS["full"], 1)
    row = deepcopy(rows[0])
    target = row
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises((ValueError, TypeError, KeyError)):
        collector.validate_monitor_row(row, None, CONFIGS["full"], 0)


@pytest.mark.parametrize("field,value", [("q_raw", .5), ("q_used", .5), ("direction", 1),
    ("beta_after", .1), ("up", 3.0), ("shared", True), ("z", 0), ("reactive", True)])
def test_warm_monitor_arithmetic_tampering_is_rejected(field, value):
    rows, _ = sequence(CONFIGS["full"], 2)
    chain = collector.validate_monitor_row(rows[0], None, CONFIGS["full"], 0)
    row = deepcopy(rows[1])
    row["observation_info"]["monitor"][field] = value
    with pytest.raises((ValueError, TypeError, KeyError)):
        collector.validate_monitor_row(row, chain, CONFIGS["full"], 1)


def test_beta_fit_checks_optimality_instead_of_accepting_any_bounded_value():
    with pytest.raises(ValueError, match="score"):
        collector.validate_beta_fit([[.01, 1]] * 32, .1)
    collector.validate_beta_fit([[.01, 1]] * 32, monitor3.BETA_MAX)
