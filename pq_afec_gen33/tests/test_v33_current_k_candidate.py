from copy import deepcopy
from dataclasses import replace

import pytest

from padfec import policy
from padfec3 import decide3, learn3
from experiments.v33.current_k_candidate import CurrentKPolicy, UnsupportedRepacking
from experiments.v33.natural_k_reference import FirstHello


HELLO = FirstHello(1447, 10, 4, 0, True, False, True)
C_PKT = policy.C_PKT_POLICY_DEFAULT
META = {"candidate_version", "k_source", "natural_k", "expected_k", "expected_scope"}


def state(k=2):
    s = learn3.new_state()
    s.k_hist = [k] * 8
    s.S_hist = [18232.0] * 8
    return s


def decide(p, hello=HELLO, **kw):
    return p.decide(hello, 1280, 2.0, 50.0, C_PKT, **kw)


def observe(p, **kw):
    args = dict(hct_ms=75.0, ok=True, k_obs=2, srv_bytes=18232.0, rtt_ms=50.0,
                arrivals={"src":"c1", "sent":6, "lost":1, "bitmap":None, "trunc":False})
    args.update(kw)
    return p.observe(**args)


@pytest.mark.parametrize("old_k", [1, 2, 3, 4])
def test_current_k_controls_decision_without_overwriting_history(old_k):
    s = state(old_k)
    p = CurrentKPolicy(s)
    expected_state = deepcopy(s)
    expected_state.k_hist = [2]
    expected = decide3.decide3(expected_state, 1280, 2.0, 50.0, C_PKT, keep_cands=True)
    got = decide(p, keep_cands=True)
    assert {k:v for k,v in got.items() if k not in META} == expected
    assert got["natural_k"] == got["expected_k"] == got["k"] == 2
    assert s.k_hist == [old_k] * 8
    expected_state.k_hist = [old_k] * 8
    assert s.__dict__ == expected_state.__dict__


def test_current_k_controls_observation_context_and_keeps_real_history():
    p = CurrentKPolicy(state(3))
    d = decide(p)
    oracle = deepcopy(p.state)
    oracle.k_hist = [2]
    args = dict(W=1280, u_mbps=2.0, c_pkt=C_PKT, j_pred=d["j3_pred_pre_ms"],
                arrivals={"src":"c1", "sent":6, "lost":1, "bitmap":None, "trunc":False})
    expected = learn3.observe3(oracle, d["action"], 75.0, True, 2, 18232.0, 50.0, **args)
    got = observe(p)
    assert {k:v for k,v in got.items() if k not in META} == expected
    assert got["ctx"]["k"] == 2 and p.state.k_hist == [3] * 8 + [2]
    oracle.k_hist = p.state.k_hist
    assert oracle.__dict__ == p.state.__dict__
    assert p.pending is None


@pytest.mark.parametrize("evidence", [None, {"src":"c1","sent":6,"lost":1,"bitmap":None,"trunc":False}])
def test_same_k_matches_existing_closed_loop_exactly(evidence):
    baseline = learn3.new_state()
    current = CurrentKPolicy()
    for i in range(40):
        expected = decide3.decide3(baseline, 1280, 2.0, 50.0, C_PKT)
        got = decide(current)
        assert {k:v for k,v in got.items() if k not in META} == expected
        ok = i % 11 != 7
        hct = (75.0 if i % 4 else 175.0) if ok else None
        baseline_info = learn3.observe3(baseline, expected["action"], hct, ok, 2, 18232.0, 50.0,
                                        W=1280, u_mbps=2.0, c_pkt=C_PKT,
                                        j_pred=expected["j3_pred_pre_ms"], arrivals=evidence)
        current_info = observe(current, hct_ms=hct, ok=ok, arrivals=evidence)
        if i > 0:
            assert {k:v for k,v in current_info.items() if k not in META} == baseline_info
        assert current.state.__dict__ == baseline.__dict__


def test_cold_policy_still_knows_expected_first_k():
    p = CurrentKPolicy()
    got = decide(p)
    assert got["why"] == "cold" and got["k"] is None
    assert got["expected_k"] == 2 and got["expected_scope"] == "first_flight"
    assert p.state.k_hist == []


def test_missing_k_history_no_longer_prevents_known_context_decision():
    s = state()
    s.k_hist = []
    got = decide(CurrentKPolicy(s))
    assert got["why"] in ("ej", "reeval") and got["k"] == 2
    assert s.k_hist == []


def test_no_rtt_does_not_hide_expected_k():
    p = CurrentKPolicy(state())
    got = p.decide(HELLO, 1280, 2.0, None, C_PKT)
    assert got["why"] == "no_rtt" and got["expected_k"] == 2


def test_large_k_is_not_silently_clamped_to_policy_range():
    p = CurrentKPolicy(state())
    got = decide(p, replace(HELLO, crypto_bytes=9600))
    assert got["why"] == "k_range" and got["expected_k"] == 8


@pytest.mark.parametrize("actions", [None, [(0, 0, 0), (130, 0, 0)]])
def test_repacking_candidate_is_rejected_atomically(actions):
    p = CurrentKPolicy(state(3))
    before = deepcopy(p.state.__dict__)
    with pytest.raises(UnsupportedRepacking):
        decide(p, replace(HELLO, crypto_bytes=2700), actions=actions)
    assert p.state.__dict__ == before and p.pending is None


def test_explicit_same_k_actions_work_near_other_width_boundary():
    p = CurrentKPolicy(state(3))
    got = decide(p, replace(HELLO, crypto_bytes=2700), actions=[(0, 0, 0)])
    assert got["k"] == got["expected_k"] == 3


@pytest.mark.parametrize("change", [{"k_obs":1}, {"k_obs":True}, {"k_obs":-1},
    {"k_obs":65}, {"hct_ms":-1.0}, {"arrivals":{"src":"c1","sent":1,"lost":2,"bitmap":None,"trunc":False}}])
def test_bad_observation_keeps_state_and_pending(change):
    p = CurrentKPolicy(state())
    decide(p)
    before, pending = deepcopy(p.state.__dict__), deepcopy(p.pending)
    with pytest.raises(ValueError):
        observe(p, **change)
    assert p.state.__dict__ == before and p.pending == pending


def test_failed_or_missing_observed_k_does_not_invent_history():
    for ok, k in ((False, 2), (True, 0)):
        p = CurrentKPolicy(state(3))
        decide(p)
        got = observe(p, ok=ok, k_obs=k, hct_ms=75.0 if ok else None)
        assert got["ctx"]["k"] == 2 and p.state.k_hist == [3] * 8


def test_pending_and_duplicate_observation_are_rejected():
    p = CurrentKPolicy(state())
    with pytest.raises(ValueError, match="no decision"):
        observe(p)
    decide(p)
    before = deepcopy(p.state.__dict__)
    with pytest.raises(ValueError, match="pending"):
        decide(p)
    assert p.state.__dict__ == before
    observe(p)
    with pytest.raises(ValueError, match="no decision"):
        observe(p)


def test_external_context_change_after_decision_is_rejected():
    p = CurrentKPolicy(state())
    decide(p)
    p.state.S_hist.append(4000.0)
    with pytest.raises(ValueError, match="state changed"):
        observe(p)


def test_history_window_and_serialized_schema_are_preserved():
    p = CurrentKPolicy(state(3))
    p.state.k_hist = [3] * learn3.K_WIN
    decide(p)
    observe(p)
    assert p.state.k_hist == [3] * (learn3.K_WIN-1) + [2]
    assert set(p.state.__dict__) == set(learn3.new_state().__dict__)
