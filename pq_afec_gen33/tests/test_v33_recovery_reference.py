import itertools
import math

import pytest

from padfec3 import layout
from experiments.v33.recovery_reference import RecoveryProfile, evaluate, flight_ledger


def value(k=2,m=4,lead=3,p=.15,u=2,**kwargs):
    return evaluate(k,1280,m,lead,p,50,u,15,**kwargs)


@pytest.mark.parametrize("p", [0,.02,.15,.3,1])
def test_single_original_without_protection_matches_closed_form(p):
    got=evaluate(1,1280,0,0,p,50,0,1)
    assert got["J"]==pytest.approx(50+layout.T_PTO_MS*(p+2*p*p),abs=1e-12)
    assert got["terminal_probability"]==pytest.approx(p*p,abs=1e-15)
    assert got["expected_retry_bytes"]==pytest.approx(1280*(p+p*p),abs=1e-10)


@pytest.mark.parametrize("p", [0,.02,.15,.3,1])
def test_xor_failure_chain_matches_independent_closed_form(p):
    got=evaluate(1,1280,1,0,p,50,0,1)
    assert got["J"]==pytest.approx(50+layout.T_PTO_MS*(p*p+2*p**4),abs=1e-12)
    assert got["terminal_probability"]==pytest.approx(p**4,abs=1e-15)
    assert got["expected_retry_bytes"]==pytest.approx((1280+layout.parity_bytes(1280,1))*(p*p+p**4),abs=1e-10)


@pytest.mark.parametrize("p", [.02,.15,.3,1])
def test_pure_lead_action_still_protects_the_retry(p):
    got=evaluate(1,1280,1,1,p,50,0,1,keep_branches=True)
    assert got["J"]==pytest.approx(50+layout.T_PTO_MS*(p+2*p**3),abs=1e-12)
    assert got["terminal_probability"]==pytest.approx(p**3,abs=1e-15)
    assert all(b["retry_lead"]==0 and b["retry_trailing"]==1 for b in got["branches"])


@pytest.mark.parametrize("k", [1,2,3,4])
@pytest.mark.parametrize("u", [0,2])
def test_no_loss_first_success_is_unchanged(k,u):
    for m in range(5):
        for lead in range(m+1):
            got=value(k,m,lead,0,u)
            old=layout.evaluate(k,1280,m,lead,0,50,u,15)
            assert got["J"]==old["J"]
            assert got["failure_contribution_ms"]==got["terminal_probability"]==got["expected_retry_bytes"]==0


def test_second_failure_uses_doubled_pto_and_is_marked_as_truncated():
    got=value(p=1,keep_branches=True)
    assert got["terminal_probability"]==1
    assert got["J"]==pytest.approx(3*layout.T_PTO_MS+2*50+3*layout.tau(1280,2))
    assert got["terminal_assumption"]=="forced_lossless_completion_after_second_failure"
    assert got["response_and_ACK_bytes_included"] is False


def test_first_failure_keeps_lead_credit_and_excludes_held_trailing():
    branches=value(keep_branches=True)["branches"]
    row=next(x for x in branches if x["pattern"]==[1,1,1,0,0,1])
    assert row["initial_stack_credit"]==3*layout.parity_bytes(1280,2)
    assert row["initial_held_bytes"]==layout.parity_bytes(1280,2)
    assert row["kind"]=="pto" and row["timer_sample_ms"] is None


def test_timer_uses_only_surviving_prefix_in_local_approximation():
    branches=value(keep_branches=True)["branches"]
    row=next(x for x in branches if x["pattern"]==[1,0,1,1,0,0])
    prefix=layout.tau(2*layout.parity_bytes(1280,2)+1280,2)
    assert row["kind"]=="ptoS"
    assert row["timer_sample_ms"]==pytest.approx(50+prefix)
    assert row["detection_ms"]==pytest.approx(prefix+3*(50+prefix))


def test_explicit_sample_and_path_modes_have_visible_different_detection():
    path=value(profile=RecoveryProfile(sample_mode="path"),keep_branches=True)
    explicit=value(profile=RecoveryProfile(sample_mode="explicit",explicit_sample_ms=72),keep_branches=True)
    for a,b in zip(path["branches"],explicit["branches"]):
        if a["kind"]=="pto":assert a["detection_ms"]==b["detection_ms"]
        else:assert b["detection_ms"]>a["detection_ms"]


def test_old_originals_can_complete_crypto_without_decoding_current_flight():
    got=flight_ledger((0,1),(1,),0,1,1280,2,(0,1,0))
    assert got["complete"][0]==layout.tau(1280,2)
    assert got["credit"]==got["physical"]==1280
    assert got["missing"]==()


def test_unusable_current_parity_does_not_become_credit():
    got=flight_ledger((0,1),(0,1),0,1,1280,2,(0,0,1))
    assert got["complete"] is None and got["credit"]==0
    assert got["physical"]==layout.parity_bytes(1280,2)
    assert got["held_symbols"]==1


def test_reconstruction_credit_is_replacement_not_addition():
    got=flight_ledger((0,1),(0,1),0,1,1280,2,(1,0,1))
    assert got["credit"]==2560
    assert got["physical"]==1280+layout.parity_bytes(1280,2)
    assert got["held_symbols"]==0 and got["missing"]==()


def test_packet_ledgers_conserve_credit_for_all_supported_small_flights():
    for k in range(1,5):
        for m in range(5):
            for lead in range(m+1):
                for bits in itertools.product((0,1),repeat=k+m):
                    row=flight_ledger(tuple(range(k)),tuple(range(k)),lead,m-lead,1280,2,bits)
                    assert 0<=row["credit"]<=row["physical"]<=row["sent_bytes"]
                    assert (row["complete"] is not None)==(sum(bits[lead:])>=k)


def test_all_scope_does_not_use_smaller_retransmission_headers():
    a=value(keep_branches=True)
    b=value(profile=RecoveryProfile(scope="all"),keep_branches=True)
    assert any(x["retry_originals"]==1 for x in a["branches"])
    assert all(x["retry_originals"]==2 for x in b["branches"])
    assert b["expected_retry_bytes"]>a["expected_retry_bytes"]


@pytest.mark.parametrize("kwargs", [{"scope":"bad"},{"retransmission":"bad"},{"sample_mode":"bad"},
    {"explicit_sample_ms":5},{"sample_mode":"explicit"},{"initial_pto_ms":0},{"sampled_multiplier":math.inf},{"ack_slope":True},{"ack_base_ms":-1}])
def test_invalid_timer_profiles_are_rejected(kwargs):
    with pytest.raises(ValueError):RecoveryProfile(**kwargs)


@pytest.mark.parametrize("p", [-1,1.01,math.inf,math.nan,True])
def test_invalid_probabilities_are_rejected(p):
    with pytest.raises(ValueError):value(p=p)


def test_rtt200_probe_regime_is_explicitly_marked():
    assert evaluate(2,1280,4,3,.15,200,2,9)["presample_probe_regime"]
    assert not value()["presample_probe_regime"]
