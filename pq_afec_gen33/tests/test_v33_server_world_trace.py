import sys

import pytest

from experiments.v33.server_world_trace import sample_with_server_trace
from experiments.v33.worldsim import Action, World, WorldContext


@pytest.mark.parametrize("mode",["granular","exact","unlimited"])
@pytest.mark.parametrize("loss",[0,.02,.15])
def test_tracing_preserves_every_world_result_field(mode,loss):
    context=WorldContext(k=2,p=0.15,s2c_loss=loss,server_bytes=18000)
    settings={"server":{"mode":mode}}
    expected=World(settings,seed=31).sample(context,Action(0,3,1),connection=5,trace=True)
    result=sample_with_server_trace(World(settings,seed=31),context,Action(0,3,1),connection=5)
    assert result["outcome"]==expected
    assert result["server_internal_trace"]
    assert sys.getprofile() is None


def test_exact_sender_ledger_is_visible_before_mutation():
    context=WorldContext(k=2,p=0,s2c_loss=0,server_bytes=18000,uplink_mbps=0)
    result=sample_with_server_trace(World({"server":{"mode":"exact"}},seed=31),context,Action())
    records=result["server_internal_trace"]
    assert any(x["function"]=="arm_server_pto" and x["event"]=="return" and not x["armed_deadlines"] for x in records)
    calls={}
    for row in records:
        if row["function"]!="send_server":continue
        if row["event"]=="call":calls[(row["time_ms"],row["kind"],str(row["data"]))]=row
        elif row["sent"]:
            before=calls[(row["time_ms"],row["kind"],str(row["data"]))]
            if not before["state"]["validated"]:
                assert before["counters"]["server_sent"]+before["size"]<=3*before["counters"]["stack_credit"]


def test_exception_restores_profiler():
    with pytest.raises(ValueError):
        sample_with_server_trace(World(),WorldContext(server_bytes=5000),Action(),overrides={"s2c":[2]})
    assert sys.getprofile() is None


def test_record_limit_restores_profiler():
    with pytest.raises(RuntimeError,match="record limit"):
        sample_with_server_trace(World(),WorldContext(server_bytes=5000),Action(),max_records=1)
    assert sys.getprofile() is None


def test_existing_profiler_is_not_replaced():
    callback=lambda *args:None
    sys.setprofile(callback)
    try:
        with pytest.raises(RuntimeError,match="existing profiler"):
            sample_with_server_trace(World(),WorldContext(server_bytes=5000),Action())
        assert sys.getprofile() is callback
    finally:
        sys.setprofile(None)
