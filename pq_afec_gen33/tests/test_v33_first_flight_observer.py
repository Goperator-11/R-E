from copy import deepcopy

import pytest

from experiments.v33.first_flight_observer import make_world_evidence, observe_first_flight
from experiments.v33.worldsim import Action, World, WorldContext


def sender(ids=("0:L:0", "0:O:0", "0:P:0"), sizes=None):
    sizes = sizes or [1280] * len(ids)
    return [{"id": identity, "size": size, "sent_ms": float(index)}
            for index, (identity, size) in enumerate(zip(ids, sizes))]


def received(identity, time=25.0, size=1280, read=None):
    return {"id": identity, "read_size": size if read is None else read,
            "wire_size": size, "time_ms": time}


def feedback(records, freeze=50.0, delivered=75.0, trunc=False):
    return {"freeze_ms": freeze, "received_ms": delivered,
            "identities": [packet["id"] for packet in records if packet["time_ms"] <= freeze],
            "truncated": trunc}


def observe(sent, records, delivery, mode="c1", deadline=100.0, closed=30.0):
    return observe_first_flight(sent, records, delivery, mode=mode,
                                deadline_ms=deadline, closed_at_ms=closed)


def test_matches_only_physical_first_flight_not_retransmission_or_recovery():
    manifest = sender()
    records = [received("0:L:0"), received("0:P:0"), received("1:O:0"), received("1:P:0")]
    result = observe(manifest, records, feedback(records))
    assert result["evidence"] == {"src": "c1", "sent": 3, "lost": 1,
                                  "bitmap": [1, 0, 1], "trunc": False}
    assert result["diagnostics"]["unmatched"] == 2


def test_duplicate_receiver_records_count_once():
    records = [received("0:O:0"), received("0:O:0", time=28)]
    result = observe(sender(), records, feedback(records))
    assert result["evidence"]["bitmap"] == [0, 1, 0]
    assert result["diagnostics"]["duplicates"] == 1


def test_no_parity_still_identifies_original():
    records = [received("0:O:0")]
    result = observe(sender(("0:O:0",)), records, feedback(records))
    assert result["evidence"]["sent"] == 1
    assert result["evidence"]["lost"] == 0


def test_delivered_empty_snapshot_includes_all_lost():
    result = observe(sender(), [], feedback([]))
    assert result["evidence"]["lost"] == 3
    assert result["diagnostics"]["all_lost_basis"] == "delivered_complete_snapshot"


def test_missing_feedback_does_not_assert_all_lost():
    result = observe(sender(), [], None)
    assert result["evidence"]["src"] == "none"
    assert result["evidence"]["lost"] == 0
    assert result["diagnostics"]["reason"] == "feedback_missing"
    assert not result["diagnostics"]["all_lost"]


@pytest.mark.parametrize("delivered,reason", [(None, "feedback_lost"), (101.0, "feedback_after_deadline")])
def test_feedback_delivery_censoring(delivered, reason):
    records = [received("0:O:0")]
    result = observe(sender(), records, feedback(records, delivered=delivered))
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["reason"] == reason


def test_feedback_truncation_is_censored_not_missing_arrivals():
    records = [received("0:O:0"), received("0:P:0")]
    delivery = feedback(records, trunc=True)
    delivery["identities"] = delivery["identities"][:1]
    result = observe(sender(), records, delivery)
    assert result["evidence"]["src"] == "none"
    assert result["evidence"]["trunc"]
    assert result["diagnostics"]["reason"] == "feedback_list_truncated"


def test_future_arrival_not_included_or_declared_lost():
    records = [received("0:O:0"), received("0:P:0", time=90.0)]
    result = observe(sender(), records, feedback(records), closed=95.0)
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["reason"] == "snapshot_before_first_flight_closed"


def test_ideal_receiver_tape_must_be_closed():
    result = observe(sender(), [], None, mode="ideal", deadline=20, closed=30)
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["reason"] == "snapshot_before_first_flight_closed"


def test_c1_censors_oversize_emissions_even_when_no_receiver_record():
    manifest = sender(sizes=[1280, 1280, 1457])
    records = [received("0:O:0")]
    result = observe(manifest, records, feedback(records))
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["receiver_datagram_truncated"]


def test_ideal_observes_physical_truncated_datagram():
    manifest = sender(sizes=[1280, 1280, 1457])
    records = [received("0:O:0"), received("0:P:0", size=1457, read=1452)]
    result = observe(manifest, records, None, mode="ideal")
    assert result["evidence"]["bitmap"] == [0, 1, 1]
    assert result["evidence"]["lost"] == 1


def test_c1_censors_partial_read_below_nominal_capacity():
    records = [received("0:O:0", size=1280, read=1000)]
    result = observe(sender(), records, feedback(records))
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["reason"] == "receiver_capacity_censoring"


@pytest.mark.parametrize("mutation", ["future", "omission", "duplicate_sender", "bool_size", "negative_time", "too_many", "wire_size_mismatch", "receive_before_send"])
def test_malformed_tape_is_rejected_without_mutation(mutation):
    manifest, records = sender(), [received("0:O:0")]
    delivery = feedback(records)
    if mutation == "future":
        delivery["identities"].append("0:P:0")
    elif mutation == "omission":
        delivery["identities"] = []
    elif mutation == "duplicate_sender":
        manifest[2]["id"] = manifest[0]["id"]
    elif mutation == "bool_size":
        manifest[0]["size"] = True
    elif mutation == "negative_time":
        records[0]["time_ms"] = -1
    elif mutation == "too_many":
        manifest = sender(tuple(f"0:O:{i}" for i in range(9)))
    elif mutation == "wire_size_mismatch":
        records[0]["wire_size"] += 1
    else:
        records[0]["time_ms"] = 0.5
    before = deepcopy((manifest, records, delivery))
    with pytest.raises(ValueError):
        observe(manifest, records, delivery)
    assert (manifest, records, delivery) == before


def world_result(context=None, action=Action(0, 3, 1), seed=31, connection=0, overrides=None):
    context = context or WorldContext(k=2, w=1280, p=0.02, rtt_ms=50, uplink_mbps=2, cert_bytes=16000)
    return World(seed=seed).sample(context, action, connection=connection, trace=True, overrides=overrides)


@pytest.mark.parametrize("action", [Action(), Action(0, 3, 1), Action(0, 0, 4)])
def test_trace_projection_preserves_world_cost_and_random_streams(action):
    context = WorldContext(k=2, w=1280, p=0.15, rtt_ms=50, uplink_mbps=2, cert_bytes=16000, s2c_loss=0.01)
    plain = World(seed=31)
    traced = World(seed=31)
    for connection in range(6):
        left = plain.sample(context, action, connection=connection)
        right = traced.sample(context, action, connection=connection, trace=True)
        frozen = deepcopy(right)
        for mode in ("none", "c1", "ideal"):
            make_world_evidence(right, mode=mode, seed=31, connection=connection,
                                feedback_loss_probability=0.01)
        assert right == frozen
        assert {key: value for key, value in right.items() if key != "trace"} == {key: value for key, value in left.items() if key != "trace"}


def test_world_projection_does_not_read_future_arrived_or_class_labels():
    row = world_result()
    before = make_world_evidence(row, mode="c1", seed=31, connection=0)
    changed = deepcopy(row)
    changed["world_class"] = "fabricated"
    changed["initial_failure"] = not changed["initial_failure"]
    changed["selected_cert_bytes"] = -999
    for packet in changed["arrivals"]:
        packet["arrived"] = not packet["arrived"]
        packet["arrival_ms"] = -999
        packet["read_size"] = -999
        packet["usable"] = False
    after = make_world_evidence(changed, mode="c1", seed=31, connection=0)
    assert after == before


def test_world_feedback_loss_uses_none_and_retains_ideal_evidence():
    row = world_result()
    result = make_world_evidence(row, mode="c1", seed=31, connection=0, feedback_loss_probability=1)
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["reason"] == "feedback_lost"
    ideal = make_world_evidence(row, mode="ideal", seed=31, connection=0, feedback_loss_probability=1)
    assert ideal["evidence"]["src"] == "c1"


def test_world_ideal_counts_first_flight_all_lost_after_retransmission():
    row = world_result(overrides={"c2s": [0] * 6})
    result = make_world_evidence(row, mode="ideal", seed=31, connection=0)
    assert result["evidence"]["sent"] == 6
    assert result["evidence"]["lost"] == 6
    assert result["diagnostics"]["all_lost"]


def test_world_rtt200_pto_is_not_all_lost():
    context = WorldContext(k=2, w=1280, p=0, rtt_ms=200, uplink_mbps=2, cert_bytes=8000)
    row = world_result(context=context)
    assert row["pto_count"] > 0
    result = make_world_evidence(row, mode="c1", seed=31, connection=0)
    assert result["evidence"]["lost"] == 0
    assert not result["diagnostics"]["all_lost"]


def test_no_response_pto_can_have_a_received_first_flight_original():
    row = world_result(overrides={"c2s": [0, 0, 0, 1, 0, 0], "s2c": [0] * 200})
    result = make_world_evidence(row, mode="c1", seed=31, connection=0)
    assert result["evidence"]["src"] == "none"
    assert result["diagnostics"]["reason"] == "feedback_missing"
    assert result["diagnostics"]["evaluation_only_no_response_pto"]
    assert result["diagnostics"]["evaluation_only_c2_false_all_lost"]
    assert not result["diagnostics"]["evaluation_only_all_lost"]


def test_world_requires_event_trace():
    row = world_result()
    row["trace"] = []
    with pytest.raises(ValueError, match="trace=True"):
        make_world_evidence(row, mode="c1", seed=31, connection=0)


def test_evaluation_does_not_declare_future_unprocessed_arrivals_lost():
    row = world_result()
    row["trace"] = [event for event in row["trace"] if event["time_ms"] <= 1.0]
    result = make_world_evidence(row, mode="ideal", seed=31, connection=0)
    assert result["evidence"]["src"] == "none"
    assert not result["diagnostics"]["evaluation_only_closed"]
    assert result["diagnostics"]["evaluation_only_all_lost"] is None
