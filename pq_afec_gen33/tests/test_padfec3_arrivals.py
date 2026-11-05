from copy import deepcopy
import json
import math
import random
from unittest import mock

import pytest

from padfec import policy
from padfec3 import layout, learn3


C_PKT = policy.C_PKT_POLICY_DEFAULT


def evidence(sent=6, lost=1, src="c1", bitmap=None, trunc=False):
    return {"src": src, "sent": sent, "lost": lost, "bitmap": bitmap, "trunc": trunc}


def state_with_context(action=(0, 3, 1), baseline=True, k=2, size=18232):
    state = learn3.new_state()
    state.k_hist = [k]
    state.S_hist = [size]
    if baseline:
        state.hct[learn3.arm_key(action)] = [75.0] * learn3.BASE_MIN
    return state


def observe(state, arrivals=None, *, action=(0, 3, 1), hct=75.0, ok=True, rtt=50.0,
            j_pred=None, k=2, size=18232, u=2.0):
    return learn3.observe3(state, action, hct, ok, k, size, rtt, W=1280,
                           u_mbps=u, c_pkt=C_PKT, j_pred=j_pred, arrivals=arrivals)


def independent_filter(state, values):
    prior = [[(1 - hazard) * value + hazard / len(learn3.G) for value in post]
             for hazard, post in zip(learn3.H, state.post)]
    z = [sum(q * value for q, value in zip(row, values)) for row in prior]
    post = [[q * value / normalizer for q, value in zip(row, values)] for row, normalizer in zip(prior, z)]
    raw = [weight * normalizer for weight, normalizer in zip(state.w, z)]
    weights = [max(value / sum(raw), learn3.W_FLOOR) for value in raw]
    return post, [value / sum(weights) for value in weights]


@pytest.mark.parametrize("sent,lost", [(1, 0), (1, 1), (6, 0), (6, 1), (6, 6), (8, 4)])
def test_datagram_likelihood_matches_independent_product(sent, lost):
    actual = learn3.arrival_likelihood(sent, lost)
    expected = [p ** lost * (1 - p) ** (sent - lost) for p in learn3.G]
    assert actual == pytest.approx(expected, rel=1e-14, abs=1e-18)
    assert actual[0] == (0.0 if lost else 1.0)


def test_lost_multiplications_precede_received_multiplications():
    class Number:
        def __init__(self, kind, events):
            self.kind = kind
            self.events = events

        def __rsub__(self, value):
            assert value == 1.0
            return Number("received", self.events)

        def __rmul__(self, value):
            self.events.append(self.kind)
            return 1.0

    events = []
    with mock.patch.object(learn3, "G", (Number("lost", events),)):
        assert learn3.arrival_likelihood(6, 2) == [1.0]
    assert events == ["lost", "lost", "received", "received", "received", "received"]


@pytest.mark.parametrize("mode", ["cold", "no_base", "nominal2", "shield", "guard", "failed"])
def test_complete_arrivals_update_once_despite_legacy_skip(mode):
    action = (0, 0, 4) if mode in ("nominal2", "shield") else (0, 3, 1)
    state = learn3.new_state() if mode == "cold" else state_with_context(action, baseline=mode != "no_base")
    if mode == "guard":
        state.g_alarm[learn3.arm_key(action)] = 0
    before = deepcopy(state)
    values = [p * (1 - p) ** 5 for p in learn3.G]
    expected_post, expected_weights = independent_filter(before, values)
    with mock.patch.object(learn3, "filter_step", wraps=learn3.filter_step) as update, \
            mock.patch.object(learn3, "predict_step", wraps=learn3.predict_step) as predict:
        info = observe(state, evidence(), action=action, ok=mode != "failed",
                       hct=None if mode == "failed" else 75.0, rtt=200.0 if mode == "shield" else 50.0)
    assert update.call_count == 1
    assert predict.call_count == 0
    for actual, expected in zip(state.post, expected_post):
        assert actual == pytest.approx(expected, rel=1e-14, abs=1e-15)
    assert state.w == pytest.approx(expected_weights, rel=1e-14, abs=1e-15)
    assert info["updated"] and info["loss_update_kind"] == "datagram"
    assert info["skip"] is None
    expected_skip = {"cold": "no_base", "no_base": "no_base", "nominal2": "nominal2",
                     "shield": "shield", "guard": None, "failed": None}[mode]
    assert info["legacy_skip_reason"] == expected_skip
    assert info["policy_path"] == "c1" and state.c1_seen and state.g_alarm == {}
    assert state.stats["alarm_cleared"] == int(mode == "guard")
    assert state.arrival_streak == 1
    assert state.stats["predict"] == state.stats["datagram"] == state.stats["upd"] == 1
    assert (state.stats["arr_sent"], state.stats["arr_lost"]) == (6, 1)


def test_same_c1_counts_are_invariant_to_hct_failure_guard_and_bitmap():
    states = [state_with_context() for _ in range(4)]
    infos = []
    for state, hct, ok, bitmap, j_pred in zip(states, (75.0, 175.0, None, 500.0),
                                            (True, True, False, True),
                                            (None, [1, 1, 1, 1, 1, 0], [0, 1, 1, 1, 1, 1], None),
                                            (None, 1.0, None, 0.0)):
        infos.append(observe(state, evidence(bitmap=bitmap), hct=hct, ok=ok, j_pred=j_pred))
    assert [info["y"] for info in infos] == [0, 1, 1, 1]
    assert all(state.post == states[0].post and state.w == states[0].w for state in states)
    assert all(info["loss_update_kind"] == "datagram" for info in infos)


@pytest.mark.parametrize("arrivals,reason", [
    (None, "source_none"),
    (evidence(src="none", lost=6), "source_none"),
    (evidence(trunc=True, bitmap=[0, 1]), "truncated"),
    (evidence(sent=0, lost=0), "empty"),
])
def test_missing_or_censored_arrivals_use_one_categorical_likelihood(arrivals, reason):
    state = state_with_context(action=(0, 0, 4), baseline=False)
    state.c1_seen = True
    before = deepcopy(state)
    ctx = learn3.context(state, 1280, 2.0, 50.0, C_PKT)
    first, second = learn3.grade_cutoffs(ctx, (0, 0, 4))
    hct = (first + second) / 2
    values = learn3.class_likelihood(ctx, (0, 0, 4), 1)
    expected, weights = independent_filter(before, values)
    with mock.patch.object(learn3, "filter_step", wraps=learn3.filter_step) as update, \
            mock.patch.object(learn3, "predict_step", wraps=learn3.predict_step) as predict:
        info = observe(state, arrivals, action=(0, 0, 4), hct=hct)
    assert update.call_count == 1 and predict.call_count == 0
    assert info["y"] is None and info["grade"] == 1
    assert info["loss_update_kind"] == "categorical"
    assert info["arrival_reject_reason"] == reason
    assert not info["arrival_usable"] and info["skip"] is None
    for actual, row in zip(state.post, expected):
        assert actual == pytest.approx(row, rel=1e-14, abs=1e-15)
    assert state.w == pytest.approx(weights, rel=1e-14, abs=1e-15)
    assert state.stats["arr_sent"] == state.stats["arr_lost"] == 0
    assert info["policy_path"] == "c1" and state.arrival_streak == 0


@pytest.mark.parametrize("arrivals", [None, evidence(src="none", lost=6),
                                      evidence(src="none", sent=0, lost=0)])
@pytest.mark.parametrize("hct,event", [(75.0, 0), (175.0, 1)])
def test_missing_arrivals_before_any_c1_use_v32_binary_likelihood(arrivals, hct, event):
    state = state_with_context(action=(0, 3, 1))
    before = deepcopy(state)
    ctx = learn3.context(state, 1280, 2.0, 50.0, C_PKT)
    expected, weights = independent_filter(before, learn3.likelihood(ctx, (0, 3, 1), event))
    with mock.patch.object(learn3, "class_likelihood", wraps=learn3.class_likelihood) as categorical:
        info = observe(state, arrivals, hct=hct)
    assert categorical.call_count == 0
    assert info["policy_path"] == "none" and not state.c1_seen and state.arrival_streak == 0
    assert info["y"] == event and info["updated"] and info["loss_update_kind"] == "binary"
    for actual, row in zip(state.post, expected):
        assert actual == pytest.approx(row, rel=1e-14, abs=1e-15)
    assert state.w == pytest.approx(weights, rel=1e-14, abs=1e-15)


@pytest.mark.parametrize("action,rtt,reason", [((0, 0, 4), 50.0, "nominal2"),
                                               ((0, 0, 4), 200.0, "shield")])
def test_missing_arrivals_before_any_c1_keep_v32_skips(action, rtt, reason):
    state = state_with_context(action=action)
    before = deepcopy(state)
    info = observe(state, None, action=action, rtt=rtt)
    assert info["skip"] == reason and not info["updated"]
    assert info["loss_update_kind"] == "predict_only"
    assert state.post == learn3.predict_step(before.post, before.w)[0]
    assert state.w == before.w


def test_context_is_not_filled_with_current_observation_before_learning():
    state = learn3.new_state()
    state.post = [[1.0] + [0.0] * (len(learn3.G) - 1) for _ in learn3.H]
    before = deepcopy(state)
    with mock.patch.object(learn3, "filter_step", wraps=learn3.filter_step) as update, \
            mock.patch.object(learn3, "predict_step", wraps=learn3.predict_step) as predict:
        info = observe(state, evidence(trunc=True))
    assert update.call_count == 0 and predict.call_count == 1
    assert state.post == learn3.predict_step(before.post, before.w)[0]
    assert state.w == before.w
    assert info["ctx"] is None and info["loss_update_kind"] == "predict_only"
    assert info["skip"] == "no_ctx" and state.stats["predict_only"] == 1
    assert state.k_hist == [2] and state.S_hist == [18232.0]


def test_ack_complete_counts_and_all_lost_are_accepted_without_hct_inference():
    state = learn3.new_state()
    info = observe(state, evidence(sent=6, lost=6, src="ack"), ok=False, hct=None, rtt=None)
    assert info["loss_update_kind"] == "datagram"
    assert state.stats["arr_ack"] == 1 and state.stats["arr_lost"] == 6
    assert learn3.combined(state)[0] == 0.0
    missing = learn3.new_state()
    missing_info = observe(missing, None, ok=False, hct=None, rtt=None)
    assert missing_info["loss_update_kind"] == "predict_only"
    assert missing.stats["arr_lost"] == 0


MALFORMED = [
    {}, [], evidence(sent=True), evidence(lost=False), evidence(sent=6.0), evidence(lost=1.0),
    evidence(sent=-1), evidence(lost=-1), evidence(sent=9), evidence(sent=2, lost=3),
    evidence(src="c2"), evidence(src=True), evidence(trunc=0), evidence(bitmap=[True] * 6),
    evidence(bitmap=[1.0] * 6), evidence(bitmap=[1] * 6), evidence(bitmap=[0, 1]),
    evidence(bitmap=[1] * 7, trunc=True), evidence(bitmap="111110"), evidence(bitmap=(1, 1, 1, 1, 1, 0)),
    dict(evidence(), extra=True), {key: value for key, value in evidence().items() if key != "bitmap"},
]


@pytest.mark.parametrize("arrivals", MALFORMED)
def test_malformed_arrivals_leave_entire_state_unchanged(arrivals):
    state = state_with_context()
    snapshot = state.to_json()
    with pytest.raises(ValueError):
        observe(state, arrivals, j_pred=1.0)
    assert state.to_json() == snapshot


def test_grade_boundaries_use_predecision_action_bytes_and_current_rtt():
    state = state_with_context()
    ctx = learn3.context(state, 1280, 2.0, 50.0, C_PKT)
    action = (10, 3, 1)
    first, second = learn3.grade_cutoffs(ctx, action)
    assert first == layout.one_rtt_cutoff_ms(50.0, 2, 4, 3, 1290, 2.0) + 3.0
    assert second == first + 50.0 + layout.response_term(4, 1290, 2.0, "v3")
    assert learn3.classify_hct(ctx, action, math.nextafter(first, -math.inf), True) == 0
    assert learn3.classify_hct(ctx, action, first, True) == 1
    assert learn3.classify_hct(ctx, action, math.nextafter(second, -math.inf), True) == 1
    assert learn3.classify_hct(ctx, action, second, True) == 2
    assert learn3.classify_hct(ctx, action, None, False) == 2


def test_class_likelihood_preserves_model_partition_and_total_error_definition():
    state = state_with_context()
    ctx = learn3.context(state, 1280, 2.0, 50.0, C_PKT)
    for action in ((0, 0, 4), (0, 3, 1)):
        likelihoods = [learn3.class_likelihood(ctx, action, grade) for grade in range(3)]
        exact = [learn3.class_likelihood(ctx, action, grade, epsilon=0) for grade in range(3)]
        for g, p in enumerate(learn3.G):
            ev = layout.evaluate(2, 1280, 4, action[1], p, 50.0, 2.0, ctx["n_need"], "v3")
            q = [ev["p_one_rtt"], ev["p_two_rtt"], ev["p_fail"]]
            assert [row[g] for row in exact] == q
            assert sum(row[g] for row in likelihoods) == pytest.approx(1, abs=1e-12)
            for grade in range(3):
                assert likelihoods[grade][g] == (1 - 0.001) * q[grade] + 0.001 * (1 - q[grade]) / 2


@pytest.mark.parametrize("action,k,size,u", [((0, 0, 4), 2, 4514, 0.0),
                                             ((1, 0, 4), 1, 4676, 0.0),
                                             ((0, 3, 1), 2, 18232, 2.0)])
@pytest.mark.parametrize("true_p", [0.0, 0.02, 0.05, 0.15])
def test_fixed_protection_arms_learn_loss_from_arrivals(action, k, size, u, true_p):
    state = state_with_context(action, k=k, size=size)
    rng = random.Random(317)
    n = k + action[1] + action[2]
    estimates = []
    for i in range(1600):
        bitmap = [int(rng.random() >= true_p) for _ in range(n)]
        info = observe(state, evidence(n, bitmap.count(0), bitmap=bitmap), action=action,
                       hct=75.0, k=k, size=size, u=u)
        assert info["loss_update_kind"] == "datagram"
        if i >= 1200:
            estimates.append(learn3.post_mean(learn3.combined(state)))
    assert abs(sum(estimates) / len(estimates) - true_p) < (0.01 if true_p == 0 else 0.02)
    assert state.stats["datagram"] == 1600 and state.stats["arr_sent"] == 1600 * n
    assert state.stats["categorical"] == state.stats["predict_only"] == 0


def test_version_eleven_roundtrip_rejects_every_prior_state():
    state = state_with_context()
    observe(state, evidence())
    observe(state, None)
    data = json.loads(json.dumps(state.to_json()))
    assert data["v"] == 11 and learn3.POLICY_VERSION == "v3.3.1-dev"
    assert (data["c1_seen"], data["arrival_streak"]) == (True, 0)
    assert learn3.DestState3.from_json(data).to_json() == data
    for version in range(1, 11):
        old = dict(data, v=version)
        with pytest.raises(ValueError, match="version mismatch"):
            learn3.DestState3.from_json(old)
