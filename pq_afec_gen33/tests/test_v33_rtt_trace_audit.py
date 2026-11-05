import copy

import pytest

from experiments.v33 import rtt_trace_audit as audit


def packet(at, direction, space="initial", pn=0, ack=None):
    return {"at_ns": at, "direction": direction, "space": space, "pn": pn,
            "bytes": 1280, "crc32c": 7, "ack_ranges": ack or []}


def row(packets=None, updates=None):
    return {"handshake_end_ns": 40_000_000, "observation": {"version": 1,
        "truncated": False, "packets": packets if packets is not None else
            [packet(1_000_000, "sent"), packet(51_000_000, "received", ack=[[0, 0]])],
        "rtt_updates": updates if updates is not None else
            [{"at_ns": 50_990_000, "latest_ns": 50_000_000, "min_ns": 50_000_000}]}}


def test_metric_can_precede_received_callback_without_becoming_proven_sample():
    result = audit.audit_row(row())
    update = result["metric_updates"][0]
    assert len(update["candidates"]) == 1
    assert update["candidates"][0]["callback_event_gap_ns"] == 10_000
    assert update["after_handshake"]
    assert not update["eligible_for_correction"] and result["eligible_samples"] == 0


def test_packet_number_spaces_are_separate():
    packets = [packet(1_000_000, "sent", "handshake"),
               packet(51_000_000, "received", "initial", ack=[[0, 0]])]
    result = audit.audit_row(row(packets))
    assert result["acknowledgments"][0]["sent_candidates"] == 0
    assert result["metric_updates"][0]["candidates"] == []


def test_zero_rtt_and_one_rtt_share_packet_number_space():
    packets = [packet(1_000_000, "sent", "0RTT"),
               packet(51_000_000, "received", "1RTT", ack=[[0, 0]])]
    result = audit.audit_row(row(packets))
    assert result["received_1rtt_ack"] == 1
    assert len(result["metric_updates"][0]["candidates"]) == 1


def test_largest_acknowledged_selects_only_that_packet():
    packets = [packet(1_000_000, "sent", pn=0), packet(2_000_000, "sent", pn=1),
               packet(51_000_000, "received", ack=[[0, 1]])]
    result = audit.audit_row(row(packets))
    assert result["acknowledgments"][0]["sent_index"] == 1
    assert result["metric_updates"][0]["candidates"][0]["rtt_value_gap_ns"] == -1_000_000


def test_packet_number_reuse_is_ambiguous():
    packets = [packet(1_000_000, "sent"), packet(2_000_000, "sent"),
               packet(51_000_000, "received", ack=[[0, 0]])]
    result = audit.audit_row(row(packets))
    assert result["acknowledgments"][0]["sent_candidates"] == 2
    assert result["metric_updates"][0]["candidates"] == []


def test_multiple_numeric_matches_are_retained():
    packets = [packet(1_000_000, "sent"), packet(50_900_000, "received", ack=[[0, 0]]),
               packet(51_000_000, "received", pn=1, ack=[[0, 0]])]
    result = audit.audit_row(row(packets))
    assert len(result["metric_updates"][0]["candidates"]) == 2


def test_retry_metric_is_not_an_ack():
    packets = [packet(1_000_000, "sent"), packet(51_000_000, "received", "retry")]
    result = audit.audit_row(row(packets))
    assert result["metric_updates"][0]["near_retry"]
    assert result["metric_updates"][0]["candidates"] == []


def test_no_metric_does_not_mean_no_ack():
    result = audit.audit_row(row(updates=[]))
    assert len(result["acknowledgments"]) == 1
    assert result["metric_updates"] == []


def test_trace_truncation_cannot_become_complete_evidence():
    value = row()
    value["observation"]["truncated"] = True
    result = audit.audit_row(value)
    assert result["truncated"] and result["eligible_samples"] == 0


@pytest.mark.parametrize("change", ["version", "truncated", "direction", "backwards", "reverse_ack", "boolean_time"])
def test_malformed_input_rejected_without_mutation(change):
    value = row()
    if change == "version":
        value["observation"]["version"] = True
    elif change == "truncated":
        value["observation"]["truncated"] = 0
    elif change == "direction":
        value["observation"]["packets"][0]["direction"] = "unknown"
    elif change == "backwards":
        value["observation"]["packets"].reverse()
    elif change == "reverse_ack":
        value["observation"]["packets"][1]["ack_ranges"] = [[2, 1]]
    elif change == "boolean_time":
        value["handshake_end_ns"] = True
    before = copy.deepcopy(value)
    with pytest.raises(ValueError):
        audit.audit_row(value)
    assert value == before
