import itertools

import pytest

from experiments.v33.worldsim import World, WorldContext, Action
from experiments.v33.recovery_world import RecoveryWorld


def world(scope="all",credit="flight",**overrides):
    params={"fec":{"retransmission_shape":"t6_originals_first","retransmission_scope":scope,"credit_scope":credit}}
    params.update(overrides)
    return RecoveryWorld(params,seed=31)


@pytest.mark.parametrize("shape",["full","originals_first"])
@pytest.mark.parametrize("k",[1,2,3,4])
def test_legacy_modes_match_every_frozen_world_field(shape,k):
    params={"retransmission_shape":shape}
    frozen=World(params,seed=31)
    candidate=RecoveryWorld(params,seed=31)
    for m in range(5):
        for lead in range(m+1):
            ctx=WorldContext(k=k,p=.15,rtt_ms=50,uplink_mbps=2,n_need=15)
            action=Action(lead=lead,trailing=m-lead)
            for connection in (0,17,99):
                old=frozen.sample(ctx,action,connection=connection,trace=True)
                new=candidate.sample(ctx,action,connection=connection,trace=True)
                assert {key:new[key] for key in old}==old


@pytest.mark.parametrize("k",[1,2,3,4])
@pytest.mark.parametrize("m",[1,2,3,4])
def test_pure_lead_always_gets_one_retry_xor(k,m):
    ctx=WorldContext(k=k,p=0,n_need=1,uplink_mbps=2)
    row=world().sample(ctx,Action(lead=m),trace=True,overrides={"c2s":(1,)*m+(0,)*k+(1,)*128})
    follow=[x for x in row["arrivals"] if x["flight"]==1]
    assert [x["kind"] for x in follow]==["O"]*k+["P"]
    assert all(x["size"]==1280+39+6*k for x in follow if x["kind"]=="P")
    assert row["ok"] and row["initial_failure"]


def test_no_fec_does_not_gain_retry_parity():
    row=world().sample(WorldContext(p=0,n_need=1),Action(),overrides={"c2s":(0,0)+(1,)*128})
    assert [x["kind"] for x in row["arrivals"] if x["flight"]==1]==["O","O"]
    assert row["parity_datagrams"]==0


def test_acknowledged_original_is_excluded_and_header_uses_retry_k():
    ctx=WorldContext(p=0,n_need=15,uplink_mbps=2)
    row=world("unacked").sample(ctx,Action(trailing=1),trace=True,overrides={"c2s":(1,0,0)+(1,)*128})
    retry=[x for x in row["arrivals"] if x["flight"]==1]
    assert [(x["kind"],x["index"]) for x in retry]==[("O",1),("P",0)]
    assert retry[-1]["size"]==1325
    assert row["flight_originals"]["1"]==[1]
    assert row["ok"]


@pytest.mark.parametrize("k,first,retry,expected",[(2,(1,0,0),(0,1,1),51),(3,(1,1,0,0),(0,0,1,1),1337)])
def test_current_flight_ledger_controls_trailing_credit(k,first,retry,expected):
    ctx=WorldContext(k=k,p=0,n_need=1,uplink_mbps=2)
    args=dict(trace=True,overrides={"c2s":first+retry+(1,)*128,"decision_delay_ms":0})
    old=world(credit="connection").sample(ctx,Action(trailing=1),**args)
    new=world(credit="flight").sample(ctx,Action(trailing=1),**args)
    assert new["ok"] and old["ok"]
    assert old["server_counted_uplink_bytes"]==new["server_counted_uplink_bytes"]
    assert old["server_stack_credit_bytes"]-new["server_stack_credit_bytes"]==expected
    assert new["server_stack_credit_bytes"]<=new["server_counted_uplink_bytes"]


def test_second_all_lost_flight_waits_for_doubled_pto():
    row=world().sample(WorldContext(k=1,p=0,n_need=1,uplink_mbps=0),Action(),trace=True,overrides={"c2s":(0,0)+(1,)*128})
    retries=[x for x in row["trace"] if x["event"]=="client_pto"]
    assert [x["time_ms"] for x in retries]==[200,600]
    assert row["ok"]


def test_total_loss_stops_without_forced_success():
    row=world().sample(WorldContext(p=1,n_need=15),Action(lead=3,trailing=1),trace=True)
    assert not row["ok"] and row["stop_reason"]=="client_pto_limit"
    assert row["server_stack_credit_bytes"]==0
    assert row["pto_count"]==8


@pytest.mark.parametrize("scope",["all","unacked"])
def test_first_patterns_preserve_global_and_per_flight_credit(scope):
    ctx=WorldContext(k=3,p=0,n_need=15,uplink_mbps=2)
    for lead,trail in ((0,0),(0,1),(3,0),(1,2)):
        for bits in itertools.product((0,1),repeat=3+lead+trail):
            row=world(scope).sample(ctx,Action(lead=lead,trailing=trail),overrides={"c2s":bits+(1,)*128})
            assert row["ok"]
            assert 0<=row["server_stack_credit_bytes"]<=row["server_counted_uplink_bytes"]<=row["client_total_uplink_bytes"]


@pytest.mark.parametrize("params",[{"fec":{"retransmission_scope":"missing"}},{"fec":{"credit_scope":"bad"}},
    {"fec":{"retransmission_scope":"unacked","retransmission_shape":"full"}},
    {"fec":{"retransmission_shape":"t6_originals_first","lead_mode":"buffered"}}])
def test_unsupported_shapes_are_explicit(params):
    with pytest.raises(ValueError):RecoveryWorld(params)


def test_inherited_expectation_cannot_silently_use_frozen_world():
    with pytest.raises(ValueError,match="diagnostic"):
        world().expectation(WorldContext(n_need=1),Action())
