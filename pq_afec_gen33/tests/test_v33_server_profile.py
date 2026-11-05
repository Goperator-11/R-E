from dataclasses import replace
import math

import pytest

from experiments.v33.server_profile import ServerProfile, first_flight_delivery, mode_evidence, packet_size_evidence, retransmission_budget


@pytest.mark.parametrize("changes", [
    {"mode": "guess"}, {"P": 1199}, {"P": 1453}, {"P": True}, {"iw_pkts": 0},
    {"iw_pkts": 1.5}, {"iw_pkts": 4097}, {"pto_initial_ms": 0}, {"pto_initial_ms": math.inf},
    {"pto_initial_ms": math.nan}, {"pto_initial_ms": True}, {"lead_credited": 1}, {"trailing_race": "always"},
])
def test_profile_rejects_invalid_inputs(changes):
    with pytest.raises(ValueError):
        ServerProfile(**changes)


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_profile_rejects_old_or_malformed_version(version):
    record = ServerProfile().to_dict()
    record["version"] = version
    with pytest.raises(ValueError):
        ServerProfile.from_dict(record)


def test_profile_roundtrip_is_separate_and_strict():
    for profile in (ServerProfile(), ServerProfile.unknown(), ServerProfile("unlimited", 1452, 10, 999, False, "none")):
        record = profile.to_dict()
        assert ServerProfile.from_dict(record) == profile
        record["lead_credited"] = not record["lead_credited"]
        assert ServerProfile.from_dict(record) != profile
        record["extra"] = None
        with pytest.raises(ValueError):
            ServerProfile.from_dict(record)


def test_unknown_profile_does_not_grant_unverified_credit():
    profile = ServerProfile.unknown()
    assert profile.mode == "exact" and profile.iw_pkts == 10
    assert profile.decision_credit(2560, [1338, 1338]) == 2560
    assert profile.credit_branches(2560, [0, 0], [1338, 1338]) == ((1.0, 2560),)


def test_exact_equality_and_granular_strict_boundary():
    exact, granular = ServerProfile("exact"), ServerProfile()
    assert exact.send_prefix(1280, (1280,) * 3)["complete"]
    assert granular.send_prefix(1280, (1280,) * 4)["sent_packets"] == 3
    assert granular.send_prefix(1281, (1280,) * 4)["complete"]
    assert exact.send_prefix(1281, (1280,) * 4)["sent_packets"] == 3


def test_short_final_packet_changes_exact_required_credit():
    sizes = (1280, 1280, 1)
    assert ServerProfile("exact").required_credit(sizes) == 854
    assert ServerProfile().required_credit(sizes) == 854
    assert ServerProfile("exact").required_credit((1280,) * 3) == 1280


def test_prior_ack_is_debited_before_data_and_retry():
    profile = ServerProfile("exact")
    assert profile.send_prefix(1280, (1280,) * 3, sent_bytes=41)["sent_packets"] == 2
    assert profile.required_credit((1280,) * 3, sent_bytes=41) == 1294
    assert profile.send_prefix(1294, (1280,) * 3, sent_bytes=41)["complete"]
    assert profile.send_prefix(1293, (1280,) * 3, sent_bytes=41)["sent_packets"] == 2


def test_unlimited_keeps_congestion_window():
    profile = ServerProfile("unlimited", iw_pkts=10)
    assert profile.send_prefix(0, (1280,) * 11)["sent_packets"] == 10
    assert profile.required_credit((1280,) * 11) is None
    assert profile.required_credit((1280,) * 10) == 0
    assert profile.send_prefix(0, (1280,), available_slots=0)["blocked_by"] == "congestion_window"


@pytest.mark.parametrize("sizes", [(), (0,), (1281,), (True,), (1.1,)])
def test_invalid_server_packet_list_is_rejected(sizes):
    with pytest.raises(ValueError):
        ServerProfile().send_prefix(1280, sizes)


@pytest.mark.parametrize("credit", [-1, True, 1.5, math.inf])
def test_invalid_credit_is_rejected(credit):
    with pytest.raises(ValueError):
        ServerProfile().send_prefix(credit, (1280,))


def test_minimum_credit_and_exact_dominance_exhaustive_boundaries():
    for P in (1200, 1252, 1280, 1350, 1452):
        for count in (1, 2, 3, 10, 15, 32):
            for last in (1, P // 2, P):
                sizes = (P,) * (count - 1) + (last,)
                for previous in (0, 41, 123):
                    granular = ServerProfile(P=P)
                    exact = replace(granular, mode="exact")
                    for profile in (granular, exact):
                        need = profile.required_credit(sizes, sent_bytes=previous)
                        assert profile.send_prefix(need, sizes, sent_bytes=previous)["complete"]
                        assert not profile.send_prefix(need - 1, sizes, sent_bytes=previous)["complete"]
                    assert granular.required_credit(sizes, sent_bytes=previous) <= exact.required_credit(sizes, sent_bytes=previous)
                    assert granular.send_prefix(exact.required_credit(sizes, sent_bytes=previous), sizes, sent_bytes=previous)["complete"]


def test_granular_overshoot_is_less_than_one_packet():
    profile = ServerProfile()
    for credit in range(1, 5000):
        sent = profile.send_prefix(credit, (1280,) * 32)["sent_bytes"]
        assert 3 * credit <= sent < 3 * credit + 1280


def test_lead_credit_flag_and_race_mass():
    profile = ServerProfile()
    assert profile.decision_credit(2560, (1338,) * 3) == 6574
    branches = profile.credit_branches(2560, (0.133, 0.355, 1.066), (1338,) * 3)
    assert sum(weight for weight, _ in branches) == pytest.approx(1)
    assert [credit for _, credit in branches] == [2560, 3898, 5236]
    assert [weight for weight, _ in branches] == pytest.approx([0.004, 0.356, 0.64])


@pytest.mark.parametrize("delays,sizes", [((1, 0), (1280, 1280)), ((math.nan,), (1280,)), ((0,), ()), ((0,), (1199,))])
def test_malformed_race_inputs_are_rejected(delays, sizes):
    with pytest.raises(ValueError):
        ServerProfile().credit_branches(1280, delays, sizes)


@pytest.mark.parametrize("p", [0, 0.01, 0.02, 0.05, 1])
def test_downlink_loss_probability_is_not_hct_scaling(p):
    row = first_flight_delivery(ServerProfile("unlimited"), 0, (1280,) * 15, p)
    assert row["p_first_flight_complete"] == pytest.approx((1-p) ** 15)
    assert row["hct_ms"] is None
    blocked = first_flight_delivery(ServerProfile(), 1280, (1280,) * 15, p)
    assert blocked["p_first_flight_complete"] == 0
    assert blocked["p_no_loss_in_sent_prefix"] == pytest.approx((1-p) ** 3)


def test_server_retransmission_spends_existing_budget_without_reset():
    exact = retransmission_budget(ServerProfile("exact"), 1600, (1280,) * 3, (False, True, False))
    granular = retransmission_budget(ServerProfile(), 1600, (1280,) * 3, (False, True, False))
    assert exact["retransmission_bytes"] == 0
    assert granular["retransmission_bytes"] == 1280
    assert granular["cumulative_sent_bytes"] == 5120
    assert not granular["complete"] and granular["blocked_by"] == "amplification"
    assert not granular["timing_modeled"]


def test_server_retransmission_zero_available_slots():
    row = retransmission_budget(ServerProfile("unlimited"), 0, (1280,), (False,), available_slots=0)
    assert row["retransmission_bytes"] == 0 and row["blocked_by"] == "congestion_window"
    row = retransmission_budget(ServerProfile(), 1280, (1280,), (True,))
    assert row["complete"] and row["missing_sizes"] == ()


def test_retransmission_rejects_unsent_first_packet_and_integer_mask():
    with pytest.raises(ValueError):
        retransmission_budget(ServerProfile(), 1280, (1280,) * 4, (True,) * 4)
    with pytest.raises(ValueError):
        retransmission_budget(ServerProfile(), 1280, (1280,), (1,))


@pytest.mark.parametrize("size", [None, 41, 100, 1199, 1453, 65527])
def test_first_data_size_does_not_promote_invalid_packet_size(size):
    row = packet_size_evidence(size)
    assert row["P"] is None and not row["confirmed"]


@pytest.mark.parametrize("size", [1200, 1280, 1350, 1452])
def test_first_data_packet_size_is_only_an_observation(size):
    row = packet_size_evidence(size)
    assert row["P"] == size and not row["confirmed"]


QUALIFIERS = dict(amplification_limited=True, no_downlink_loss=True, demand_exceeds_observed=True,
                  no_window_limit=True, stable_credit=True, address_unvalidated=True)


@pytest.mark.parametrize("missing", list(QUALIFIERS))
def test_any_missing_mode_evidence_qualifier_prevents_inference(missing):
    qualifiers = {**QUALIFIERS, missing: False}
    row = mode_evidence(credit=1281, first_rtt_server_bytes=5120, P=1280, **qualifiers)
    assert row["planning_mode"] == "exact" and row["candidate_mode"] is None
    assert row["missing_qualifiers"] == (missing,)


def test_overshoot_is_provisional_and_low_ratio_is_ambiguous():
    row = mode_evidence(credit=1281, first_rtt_server_bytes=5120, P=1280, **QUALIFIERS)
    assert row["candidate_mode"] == "granular" and not row["confirmed"]
    assert row["planning_mode"] == "exact"
    row = mode_evidence(credit=1280, first_rtt_server_bytes=3840, P=1280, **QUALIFIERS)
    assert row["candidate_mode"] is None and row["reason"] == "exact_and_granular_not_distinguished"
    row = mode_evidence(credit=1280, first_rtt_server_bytes=5120, P=1280, **QUALIFIERS)
    assert row["candidate_mode"] is None and row["reason"] == "inconsistent_with_amplification_limited_evidence"
