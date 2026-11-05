from dataclasses import replace
import math

import pytest

from experiments.v33.recovery_reference import RecoveryProfile, evaluate, flight_ledger
from experiments.v33.server_cost_reference import ServerCost
from experiments.v33.server_profile import ServerProfile
from padfec3 import layout


def value(*, server=None, p=0, k=2, m=4, lead=3, u=2, need=15, width=1280, **kwargs):
    return evaluate(k,width,m,lead,p,50,u,need,server=server,**kwargs)


@pytest.mark.parametrize("P", [1200,1280,1452])
@pytest.mark.parametrize("mode", ["exact","granular","unlimited"])
def test_lossless_server_window_rounds(P,mode):
    cost=ServerCost(ServerProfile(mode,P,10),(P,)*25)
    assert cost.lossless_completion(20000,50,0,1280,0)==150
    assert cost.lossless_completion(20000,50,2,1280,0)==pytest.approx(150+8*(1280+41)/2000)


def test_amplification_first_prefix_then_address_validation():
    cost=ServerCost(ServerProfile("exact",iw_pkts=10),(1280,)*15)
    assert cost.lossless_completion(1280,50,2,1280,0)==pytest.approx(155.284)
    assert cost.lossless_completion(1280,50,0,1280,0)==150
    cost=ServerCost(ServerProfile("exact",iw_pkts=32),(1280,)*15)
    assert cost.lossless_completion(1280,50,2,1280,0)==pytest.approx(105.12)


@pytest.mark.parametrize("p", [0,0.02,0.15,0.3,1])
def test_initial_pto_comes_from_explicit_server_profile(p):
    for pto in (200,999):
        cost=ServerCost(ServerProfile(pto_initial_ms=pto),(1280,))
        row=value(k=1,m=0,lead=0,p=p,u=0,need=1,server=cost)
        assert row["J"]==pytest.approx(50+pto*(p+2*p*p),abs=1e-10)
        assert row["terminal_probability"]==pytest.approx(p*p)


@pytest.mark.parametrize("k", [1,2,3,4])
@pytest.mark.parametrize("u", [0,2])
def test_explicit_legacy_profile_preserves_recovery_reference_cost(k,u):
    server=ServerCost(ServerProfile(pto_initial_ms=layout.T_PTO_MS),(1280,)*15)
    for m,lead in ((0,0),(1,0),(4,0),(4,3),(4,4)):
        old=value(k=k,m=m,lead=lead,p=.15,u=u)
        new=value(k=k,m=m,lead=lead,p=.15,u=u,server=server)
        assert new["J"]==pytest.approx(old["J"],abs=1e-10)
        for key in ("p_fail","terminal_probability","expected_retry_bytes","expected_retry_parity_bytes"):
            assert new[key]==old[key]


def test_one_byte_padding_crosses_only_granular_full_packet_boundary():
    granular=ServerCost(ServerProfile(),(1280,)*4)
    exact=ServerCost(ServerProfile("exact"),(1280,)*4)
    g=value(k=1,m=0,lead=0,need=4,width=1281,u=0,server=granular)
    e=value(k=1,m=0,lead=0,need=4,width=1281,u=0,server=exact)
    assert g["J"]==50 and e["J"]==100


def test_exact_uses_short_last_packet_and_not_p_times_count():
    short=ServerCost(ServerProfile("exact"),(1280,1280,1280,1))
    full=ServerCost(ServerProfile("exact"),(1280,)*4)
    assert value(k=1,m=0,lead=0,need=4,width=1281,u=0,server=short)["J"]==50
    assert value(k=1,m=0,lead=0,need=4,width=1281,u=0,server=full)["J"]==100


def test_lead_and_trailing_credit_are_independent_server_capabilities():
    known=ServerCost(ServerProfile(),(1280,)*15)
    no_lead=replace(known,profile=replace(known.profile,lead_credited=False))
    assert value(server=no_lead)["J"]-value(server=known)["J"]==pytest.approx(55.12)
    no_race=replace(known,profile=replace(known.profile,trailing_race="none"))
    assert value(server=no_race,lead=0,u=0)["J"]==100
    assert value(server=known,lead=0,u=0)["J"]==50


def test_uncredited_lead_keeps_physical_bytes_and_delay():
    row=flight_ledger((0,),(0,),1,0,1280,2,(1,1),lead_credited=False)
    assert row["credit"]==1280
    assert row["physical"]==1280+layout.parity_bytes(1280,1)
    assert row["complete"][0]==pytest.approx(layout.tau(row["physical"],2))


def test_discarded_lead_is_not_reported_as_buffered_parity():
    server=ServerCost(ServerProfile(lead_credited=False),(1280,)*15)
    result=value(server=server,p=.15,keep_branches=True)
    row=next(x for x in result["branches"] if x["pattern"]==[1,1,1,0,0,1])
    assert row["initial_held_bytes"]==layout.parity_bytes(1280,2)
    assert row["initial_ignored_lead_bytes"]==3*layout.parity_bytes(1280,2)
    assert row["initial_stack_credit"]==0
    assert row["initial_held_bytes"]+row["initial_ignored_lead_bytes"]==row["initial_physical_bytes"]


def test_recovery_all_scope_allows_multi_original_credit_events():
    server=ServerCost(ServerProfile(),(1280,)*15)
    row=value(k=4,m=4,lead=0,p=.15,server=server,profile=RecoveryProfile(scope="all"))
    assert row["cost_complete"] and math.isfinite(row["J"])


@pytest.mark.parametrize("p_d", [.01,.02,.05,1])
def test_unresolved_downlink_timing_never_becomes_complete_cost(p_d):
    server=ServerCost(ServerProfile(),(1280,)*15,p_d)
    row=value(server=server,p=.15,keep_branches=True)
    assert row["J"] is None and not row["cost_complete"]
    assert row["lossless_counterfactual_J"]==value(server=replace(server,p_d=0),p=.15)["J"]
    assert row["downlink_loss_probability"]==pytest.approx(1-(1-p_d)**15)
    assert row["conditional_failure_cost_ms"] is None
    assert all(x["conditional_cost_ms"] is None for x in row["branches"])


@pytest.mark.parametrize("changes", [{"sizes":[]},{"sizes":()},{"sizes":(1281,)},{"p_d":-1},{"p_d":math.nan},{"p_d":True},{"ack_bytes":0},{"ack_bytes":True}])
def test_invalid_server_cost_input_is_rejected(changes):
    args=dict(profile=ServerProfile(),sizes=(1280,))
    args.update(changes)
    with pytest.raises(ValueError):
        ServerCost(**args)


def test_server_packet_count_mismatch_and_no_credit_are_rejected():
    server=ServerCost(ServerProfile(),(1280,))
    with pytest.raises(ValueError):
        value(server=server)
    with pytest.raises(ValueError):
        server.lossless_completion(0,50,0,1280,0)
