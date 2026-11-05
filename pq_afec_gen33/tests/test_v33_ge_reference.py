import itertools
import math

import pytest

from afec.channel import GilbertElliott
from experiments.v33 import ge_reference as ge
from experiments.v33 import worldsim
from padfec3 import layout, learn3


@pytest.mark.parametrize("p", [0.0, 0.02, 0.15, 0.5, 0.9, 1.0])
@pytest.mark.parametrize("burst", [1.0, 1.001, 3.0, 10.0])
def test_probability_normalization_and_marginals(p, burst):
    for n in (0, 1, 2, 6, 8):
        rows = [(pat, ge.pattern_probability(pat, p, burst))
                for pat in itertools.product((0, 1), repeat=n)]
        assert sum(pr for _, pr in rows) == pytest.approx(1.0, abs=2e-14)
        for i in range(n):
            assert sum(pr for pat, pr in rows if not pat[i]) == pytest.approx(p, abs=2e-14)


@pytest.mark.parametrize("p,burst", [(0.02, 3), (0.15, 3), (0.25, 3), (0.9, 10)])
def test_forward_matches_independent_world_and_channel_dp(p, burst):
    for n in (1, 2, 6, 8):
        counts = [0.0] * (n + 1)
        for pat in itertools.product((0, 1), repeat=n):
            prob = ge.pattern_probability(pat, p, burst)
            assert prob == pytest.approx(worldsim.pattern_probability(
                pat, p, loss_model="ge", burst_length=burst), abs=2e-15)
            counts[pat.count(0)] += prob
        assert counts == pytest.approx(GilbertElliott.from_burst(p, burst).erasure_pmf(n), abs=2e-14)


@pytest.mark.parametrize("context", [(2,1280,2,50.7,15), (2,1280,0,50,4),
                                     (2,1280,10,120,7), (1,1280,0,50,6)])
def test_iid_all_fields_are_unchanged(context):
    k, w, u, rtt, need = context
    before = layout.outcomes
    cache = list(learn3._MODEL.items())
    ref = ge.GEReference()
    for m in range(5):
        for lead in range(m+1):
            for p in (0.0, 0.02, 0.15, 0.3, 1.0):
                args = (k,w,m,lead,p,rtt,u,need)
                assert ref.evaluate(*args) == layout.evaluate(*args)
    assert layout.outcomes is before
    assert list(learn3._MODEL.items()) == cache


def test_iid_boundary_is_continuous_and_physical_one_is_distinct():
    p = 0.15
    iid = 1.0 / (1.0-p)
    for pat in itertools.product((0,1), repeat=6):
        assert ge.pattern_probability(pat,p,iid) == ge.pattern_probability(pat,p,1)
        assert ge.pattern_probability(pat,p,iid+1e-13) == pytest.approx(
            ge.pattern_probability(pat,p,1),abs=1e-12)
    assert worldsim.pattern_probability((0,0),p,loss_model="ge",burst_length=1) == 0
    assert ge.pattern_probability((0,0),p,1) == p*p


def test_p18_failure_is_preserved():
    ref = ge.GEReference(3)
    result = ref.evaluate(2,1280,4,0,0.15,50,0,5)
    p, a, b = .15, .15 / (3*.85), 1/3
    direct = p*(1-b)**5 + (1-p)*a*(1-b)**4 + p*(1-b)**4*b + 4*p*b*a*(1-b)**3
    assert result["p_fail"] == pytest.approx(direct,abs=1e-14)
    assert 58 < result["J"] < 59


@pytest.mark.parametrize("p,burst", [(0.02,1),(0.15,1),(0.15,3),(0.25,3)])
@pytest.mark.parametrize("action", [(2,4,0),(2,4,3),(2,1,0),(1,0,0)])
def test_expected_attempts_against_tail_sum(p,burst,action):
    result = ge.expected_attempts(*action,p,burst)
    matrix = result["retry_failure_transition"]
    mass = [1-p,p]
    tail = 1.0
    for _ in range(500):
        mass = [sum(mass[i]*matrix[i][j] for i in (0,1)) for j in (0,1)]
        tail += sum(mass)
    assert result["attempts"] == pytest.approx(tail,abs=1e-12)
    k,m,lead = action
    failure = ge.GEReference(burst).evaluate(k,1280,m,lead,p,50,0,5)["p_fail"]
    assert sum((1-p)*matrix[0][j]+p*matrix[1][j] for j in (0,1)) == pytest.approx(failure,abs=1e-14)
    if burst == 1:
        assert result["attempts"] == pytest.approx(1/(1-failure),abs=1e-12)


def test_retry_action_and_probability_endpoints():
    result = ge.expected_attempts(2,4,3,0.15,3,retry=(2,1,0))
    mass = [sum([0.85,0.15][i]*result["first_failure_transition"][i][j] for i in (0,1)) for j in (0,1)]
    tail = 1+sum(mass)
    for _ in range(500):
        mass = [sum(mass[i]*result["retry_failure_transition"][i][j] for i in (0,1)) for j in (0,1)]
        tail += sum(mass)
    assert result["attempts"] == pytest.approx(tail,abs=1e-12)
    assert ge.expected_attempts(2,4,0,0,3)["attempts"] == 1
    assert math.isinf(ge.expected_attempts(2,4,0,1,3)["attempts"])


def obs(bits, destination="a", **kwargs):
    return ge.BurstObservation(destination,{"src":"c1","sent":len(bits),
        "lost":bits.count(0),"bitmap":bits,"trunc":False},**dict(full_sent=True,physical=True,**kwargs))


def test_run_edges_are_censored_and_connections_not_joined():
    result = ge.estimate_burst([obs([0,0]),obs([0,1])],"a",0.15)
    assert result["transitions"] == {"gg":0,"gb":0,"bg":1,"bb":1}
    assert result["raw_bad_to_good"] == pytest.approx((1+16*.85)/18)
    assert result["mean_burst"] == pytest.approx(18/(1+16*.85))


def test_all_lost_is_used_only_with_explicit_evidence():
    row = obs([0]*6)
    result = ge.estimate_burst([row],"a",0.15)
    assert result["transitions"]["bb"] == 5
    for bad in (ge.BurstObservation("a",None,True,True),
                ge.BurstObservation("a",row.arrivals,False,True),
                ge.BurstObservation("a",row.arrivals,True,False),
                ge.BurstObservation("a",dict(row.arrivals,src="none"),True,True),
                ge.BurstObservation("a",dict(row.arrivals,trunc=True),True,True),
                ge.BurstObservation("a",dict(row.arrivals,bitmap=None),True,True)):
        value = ge.estimate_burst([bad],"a",0.15)
        assert value["qualified_samples"] == 0 and value["iid"]


def test_window_ages_missing_evidence_and_isolates_destinations():
    old = [obs([0]*6)]*64
    missing = [ge.BurstObservation("a",None)]*64
    result = ge.estimate_burst(old+missing+[obs([0]*6,"b")],"a",0.15)
    assert result["window_samples"] == 64
    assert result["qualified_samples"] == 0
    assert result["iid"]
    assert ge.estimate_burst(old,"a",0.15)["mean_burst"] > 3


@pytest.mark.parametrize("p,burst", [(-.1,1),(1.1,1),(True,1),(.1,True),
                                    (.1,.9),(.1,math.inf),(.1,math.nan),(math.nan,3)])
def test_invalid_channel_is_rejected(p,burst):
    with pytest.raises((ValueError,TypeError)):
        ge.parameters(p,burst)


@pytest.mark.parametrize("bits", [(True,), (2,), (-1,), (0.0,)])
def test_invalid_bits_are_rejected(bits):
    with pytest.raises(ValueError):
        ge.pattern_probability(bits,.15,3)


def test_invalid_evidence_and_initial_state_are_rejected():
    row = obs([1,0])
    with pytest.raises(ValueError):
        ge.estimate_burst([ge.BurstObservation("a",dict(row.arrivals,lost=0),True,True)],"a",.15)
    with pytest.raises(TypeError):
        ge.estimate_burst([ge.BurstObservation("a",row.arrivals,1,True)],"a",.15)
    for initial in ((.2,.2),(1,-.1),(True,False),(1,)):
        with pytest.raises((ValueError,TypeError)):
            ge.forward((1,0),.15,3,initial)
