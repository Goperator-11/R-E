import copy
from dataclasses import replace
import json
import math

import pytest

from experiments.v33 import rtt_reference as ref
from padfec3 import learn3


def sample(value=50.0, **changes):
    return replace(ref.RttSample(0, "initial_ack", value, 1280, 0, 0.0, 0.0,
                                 0.0, True, True, True), **changes)


@pytest.mark.parametrize("lead", range(5))
@pytest.mark.parametrize("uplink", [0.0, 2.0, 5.0, 10.0, 50.0])
def test_physical_byte_correction(lead, uplink):
    amount = lead * 1331 + 1280
    serialized = 0 if uplink == 0 else amount * 8 / (uplink * 1000)
    result = ref.correct_sample(sample(50 + serialized + 0.3,
        queued_bytes=lead * 1331, shim_wait_ms=0.3, uplink_mbps=uplink))
    assert result["accepted"]
    assert result["corrected_ms"] == pytest.approx(50.0, abs=1e-12)


def test_initial_ack_delay_ignored_by_transport_cannot_be_subtracted():
    assert ref.correct_sample(sample(52, ack_delay_ms=2))["reason"] == "initial_ack_delay_not_applicable"
    later = sample(57.12, source="later_1rtt_ack", uplink_mbps=2, ack_delay_ms=2)
    assert ref.correct_sample(later)["corrected_ms"] == pytest.approx(50, abs=1e-12)


@pytest.mark.parametrize("field", ["datagram_bytes", "queued_bytes", "shim_wait_ms", "uplink_mbps", "ack_delay_ms"])
def test_unknown_components_are_not_zero(field):
    result = ref.correct_sample(sample(**{field: None}))
    assert result == {"accepted": False, "reason": field + "_missing"}


@pytest.mark.parametrize("field", ["ack_verified", "packet_attributed", "queue_accounted"])
def test_unverified_components_rejected(field):
    assert ref.correct_sample(sample(**{field: False}))["reason"] == field + "_missing"


def test_legacy_minimum_has_no_packet_owner():
    assert not ref.correct_sample(sample(source="legacy_min_rtt"))["accepted"]


def test_later_queue_free_sample_preferred_over_minimum_and_initial():
    track = ref.RttTrack()
    rows = [sample(20), sample(60, sample_id=1, source="later_1rtt_ack"),
            sample(65, sample_id=2, source="later_1rtt_ack"), sample(30, sample_id=3)]
    result = track.observe_connection(0, rows)
    assert result["selected"]["sample_id"] == 2
    assert track.ewma_ms == 65
    assert track.min_ms == 65
    assert track.observations == 1


@pytest.mark.parametrize("changes", [{"queued_bytes": 1}, {"shim_wait_ms": 0.001}])
def test_queued_later_sample_does_not_claim_queue_free(changes):
    track = ref.RttTrack()
    result = track.observe_connection(0, [sample(55), sample(50, sample_id=1,
        source="later_1rtt_ack", **changes)])
    assert result["samples"][1]["reason"] == "later_sample_queued"
    assert track.ewma_ms == 55


@pytest.mark.parametrize("higher", [100.0, 150.0])
def test_gen2_eight_connection_adaptation_and_separate_minimum(higher):
    track = ref.RttTrack()
    track.observe_connection(0, [sample(50)])
    for i in range(1, 9):
        track.observe_connection(i, [sample(higher)])
    expected = higher - (higher - 50) * 0.75 ** 8
    assert track.ewma_ms == pytest.approx(expected, abs=1e-12)
    assert track.ewma_ms >= (90 if higher == 100 else 130)
    assert track.min_ms == 50
    start = track.ewma_ms
    for i in range(9, 17):
        track.observe_connection(i, [sample(25)])
    assert track.ewma_ms == pytest.approx(25 + (start - 25) * 0.75 ** 8, abs=1e-12)
    assert track.min_ms == 25


def test_variation_uses_previous_mean_and_preserves_missing_observations():
    track = ref.RttTrack()
    track.observe_connection(0, [sample(50)])
    assert track.variation_ms == 25
    track.observe_connection(1, [sample(100)])
    assert track.ewma_ms == 62.5
    assert track.variation_ms == 31.25
    before = track.to_dict()
    track.observe_connection(2, [])
    assert track.age_connections() == 1
    assert track.to_dict() == dict(before, connection_seq=2)
    assert ref.RttTrack().age_connections() is None


def test_roundtrip_and_resume_identical():
    a = ref.RttTrack()
    a.observe_connection(0, [sample(50)])
    a.observe_connection(1, [])
    b = ref.RttTrack.from_dict(json.loads(json.dumps(a.to_dict(), allow_nan=False)))
    for i, x in enumerate([100, 150, 25, 25], 2):
        assert a.observe_connection(i, [sample(x)]) == b.observe_connection(i, [sample(x)])


@pytest.mark.parametrize("mutation", [
    {"state_version": 0}, {"state_version": 2}, {"state_version": True},
    {"observations": -1}, {"observations": 2}, {"last_valid_seq": 3},
    {"min_ms": 60}, {"ewma_ms": float("nan")}, {"variation_ms": -1},
    {"source": "legacy_min_rtt"}, {"sample_id": True}, {"extra": 0},
    {"variation_ms": 1}, {"connection_seq": -1}])
def test_invalid_serialized_state_rejected(mutation):
    track = ref.RttTrack()
    track.observe_connection(0, [sample(50)])
    with pytest.raises((TypeError, ValueError)):
        ref.RttTrack.from_dict(dict(track.to_dict(), **mutation))


def test_missing_field_and_fake_unobserved_state_rejected():
    value = ref.RttTrack().to_dict()
    del value["source"]
    with pytest.raises(ValueError):
        ref.RttTrack.from_dict(value)
    with pytest.raises(ValueError):
        ref.RttTrack.from_dict(dict(ref.RttTrack().to_dict(), ewma_ms=100))


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "50"])
def test_invalid_sample_is_atomic(bad):
    track = ref.RttTrack()
    track.observe_connection(0, [sample(50)])
    before = copy.deepcopy(track.to_dict())
    with pytest.raises((TypeError, ValueError)):
        track.observe_connection(1, [sample(60), sample(bad, sample_id=1)])
    assert track.to_dict() == before


@pytest.mark.parametrize("rows", [[sample(), sample()], [sample(sample_id=2), sample(sample_id=1)]])
def test_duplicate_or_unordered_sample_is_atomic(rows):
    track = ref.RttTrack()
    before = track.to_dict()
    with pytest.raises(ValueError):
        track.observe_connection(0, rows)
    assert track.to_dict() == before


def test_connection_cannot_be_replayed_or_reordered():
    track = ref.RttTrack()
    track.observe_connection(4, [])
    for i in [4, 3]:
        with pytest.raises(ValueError):
            track.observe_connection(i, [sample()])
    assert track.observations == 0


def test_overcorrection_is_missing_not_floored():
    result = ref.correct_sample(sample(1, uplink_mbps=2))
    assert result["reason"] == "nonpositive_corrected_rtt"


def test_cutoff_direction_and_zero_variance_regression():
    ctx = {"k": 2, "W": 1280, "u": 2, "rtt": 50, "n_need": 5}
    action = (0, 3, 1)
    first, second = learn3.grade_cutoffs(ctx, action)
    assert ref.grade_cutoffs(ctx, action, 0) == (first, second)
    assert ref.grade_cutoffs(ctx, action, 5) == (first + 20, second + 20)
    for x in [math.nextafter(first, -math.inf), first, math.nextafter(second, -math.inf), second]:
        assert ref.classify_hct(ctx, action, x, True, 0) == learn3.classify_hct(ctx, action, x, True)
    assert ref.classify_hct(ctx, action, None, False, 5) == 2
    assert ref.classify_hct(None, action, 50, True, 5) is None


def test_event_and_guard_share_variation_threshold():
    assert ref.delay_threshold(50, 0) == 25
    assert ref.delay_threshold(20, 5) == 20
    assert ref.delay_threshold(20, 2.5) == 10


def test_pto_boundary_includes_own_packet_and_explicit_processing():
    amount = 3 * 1331 + 1280
    boundary = 200 - amount * 8 / 2000 - 3
    assert ref.first_ack_time(boundary, amount, 2, 3) == 200
    assert ref.pto_risk(boundary, amount, 2, 3)
    assert not ref.pto_risk(boundary - 1e-6, amount, 2, 3)
    assert not ref.pto_risk(boundary, amount, 2, 0)
    with pytest.raises(TypeError):
        ref.pto_risk(180, amount, None, 3)
