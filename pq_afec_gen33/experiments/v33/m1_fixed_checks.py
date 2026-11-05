import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import time

ROOT=Path(__file__).resolve().parents[2]
SNAPSHOT=ROOT/"g3/v33/policy_snapshots/M1_v1"
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(SNAPSHOT))
from padfec3 import layout, decide3
from experiments.v33 import worldsim_m1 as world


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text(encoding="utf-8"))
    paths={**plan["source_sha256"],**plan["inputs_sha256"]}
    policy=plan["policies"]["m1"]["fingerprint"]
    paths.update({str(Path(policy["source_root"])/name):digest for name,digest in policy["files"].items()})
    for name,digest in paths.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    assert Path(layout.__file__).resolve().is_relative_to(SNAPSHOT)
    started=time.monotonic()
    spec=plan["fixed_action_checks"]["context"]
    context=world.WorldContext(**spec)
    sizes,_=world.World(seed=31)._packetization(context,0,random.Random(31))
    candidates=decide3.candidates3(context.k,context.w,sum(sizes),41.983)
    actions=sorted({tuple(c["action"]) for c in candidates}|{(0,lead,m-lead) for m in range(5) for lead in range(m+1)})
    rows=[]
    for p,action in itertools.product(plan["fixed_action_checks"]["p"],actions):
        delta,lead,trailing=action
        m,w=lead+trailing,context.w+delta
        off=layout.evaluate(context.k,w,m,lead,p,context.rtt_ms,context.uplink_mbps,len(sizes),lead_hold=False)
        hold=layout.evaluate(context.k,w,m,lead,p,context.rtt_ms,context.uplink_mbps,len(sizes),lead_hold=True)
        deadline=layout.tau(layout.client_bytes(context.k,m,w),context.uplink_mbps)+1.0 if m else 0.
        rows.append({"p":p,"action":list(action),"off":off,"hold":hold,
                     "hold_minus_off_ms":hold["J"]-off["J"],"nominal_deadline_bound_ms":deadline,
                     "damage_within_deadline":hold["J"]-off["J"]<=deadline+1e-10})
    exact=[]
    for p in plan["fixed_action_checks"]["p"]:
        for action in plan["fixed_action_checks"]["special_actions"]:
            delta,lead,trailing=action
            context=world.WorldContext(**dict(spec,p=p))
            engine=world.World(params={"features":{"retransmissions":False}},seed=31)
            failure=mass=0.
            counts={"patterns":0,"failed":0}
            for pattern in itertools.product((0,1),repeat=context.k+lead+trailing):
                probability=1.
                for bit in pattern:probability*=(1-p) if bit else p
                observed=engine.sample(context,world.Action(*action),trace=True,
                    overrides={"c2s":list(pattern)+[1]*256,"decision_delay_ms":0.})
                mass+=probability
                failure+=probability*observed["initial_failure"]
                counts["patterns"]+=1;counts["failed"]+=observed["initial_failure"]
                assert observed["server_stack_credit_bytes"]<=observed["server_counted_uplink_bytes"]
            target=next(r for r in rows if r["p"]==p and r["action"]==action)["hold"]["p_fail"]
            assert abs(failure-target)<1e-14 and abs(mass-1)<1e-13
            exact.append({"p":p,"action":action,"independent_first_flight_p_fail":failure,
                          "model_p_fail":target,"probability_mass":mass,**counts,
                          "scope":"enumerated first flight; retransmissions disabled and subsequent arrivals fixed; not HCT expectation"})
    best=[]
    for p in plan["fixed_action_checks"]["p"]:
        selected=[r for r in rows if r["p"]==p]
        off=min(selected,key=lambda r:r["off"]["J"])
        hold=min(selected,key=lambda r:r["hold"]["J"])
        best.append({"p":p,"off_action":off["action"],"hold_action":hold["action"],
                     "off_J_ms":off["off"]["J"],"hold_J_ms":hold["hold"]["J"],
                     "improvement_ms":off["off"]["J"]-hold["hold"]["J"]})
    result={"schema":"m1-fixed-action-checks/1","data_kind":"model_J_and_independent_first_flight_probability",
            "plan_sha256":hashlib.sha256(args.plan.read_bytes()).hexdigest(),
            "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"source_sha256":paths,
            "actions":actions,"action_count":len(actions),"world_server_sizes":sizes,"n_need":len(sizes),
            "rows":rows,"exact_first_flight":exact,"best":best,
            "low_loss_all_damage_within_deadline":all(r["damage_within_deadline"] for r in rows if r["p"]==.02),
            "elapsed_seconds":time.monotonic()-started,
            "independent_HCT_expectation":"pending full fixed-sample action family"}
    for name,digest in paths.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    with args.output.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write("\n")
    print(json.dumps({k:result[k] for k in ("action_count","best","exact_first_flight","low_loss_all_damage_within_deadline","elapsed_seconds")}),flush=True)


if __name__=="__main__":
    main()
