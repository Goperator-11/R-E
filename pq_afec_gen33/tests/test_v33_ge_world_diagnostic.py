import copy

import pytest

from experiments.v33 import ge_world_diagnostic as driver
from padfec3 import layout


def test_plan_preserves_frozen_scenarios_and_counts():
    plan=driver.make_plan()
    protocol=driver.read(driver.ROOT/"g3/v33/bench_protocol.json")
    assert plan["seed_runs"]==120
    assert plan["connection_contexts"]==177000
    assert plan["seeds"]==list(range(31,51))
    assert all(s in protocol["scenarios"] for s in plan["scenarios"])
    driver.validate_plan(plan)
    for key,value in (("c_pkt",0),("family_size",1),("seeds",[31])):
        tampered=copy.deepcopy(plan);tampered[key]=value
        with pytest.raises(ValueError):driver.validate_plan(tampered)


def test_smoke_preserves_connection_ids():
    scenario=driver.make_plan()["scenarios"][0]
    assert [x[2] for x in driver.schedule(scenario,True)]==[0,1,2,3,450,451,452,453,900,901,902,903]
    assert len(list(driver.schedule(scenario)))==1350


@pytest.mark.parametrize("name",driver.SCENARIOS)
def test_known_iid_and_burst_inputs_are_separate(name):
    plan=driver.make_plan()
    scenario=next(s for s in plan["scenarios"] if s["id"]==name)
    original=layout.outcomes
    for phase in scenario["phases"]:
        design=driver.design(scenario,phase,plan["c_pkt"])
        iid=design["tables"]["iid"]
        known=design["tables"]["known_burst"]
        if name=="B10":
            assert known["requested_mean_burst"]==3
            first=next(c for c in known["candidates"] if c["action"]==(0,0,4))
            assert first["prediction"]["p_fail"]==pytest.approx(.042992011619462624,abs=1e-14)
        else:
            assert known==iid
    assert layout.outcomes is original


def test_inference_distinguishes_structural_zero_from_unresolved():
    same=driver.inference([0.0]*20,True)
    unresolved=driver.inference([0.0]*20,False)
    assert same["structural_zero"] and same["family95"]["lower"]==0
    assert not same["decrease"]
    assert unresolved["zero_variance_unresolved"] and unresolved["family95"]["lower"] is None
    assert driver.inference([1+(i%2)*.01 for i in range(20)],False)["harm_above_0_5"]
    with pytest.raises(AssertionError):driver.inference([1.0]*20,True)
