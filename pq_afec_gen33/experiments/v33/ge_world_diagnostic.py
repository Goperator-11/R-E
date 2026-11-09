import sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import time

from experiments.v33 import ge_reference as ge
from experiments.v33.bench_metrics import paired_summary
from experiments.v33.worldsim import Action,World,WorldContext
from padfec import policy,quantum
from padfec3 import decide3,learn3


SCENARIOS = ("B1","B2","B3_u0","B3_u2","B4","B10")
ARMS = ("iid","known_burst","forced_burst3","fixed_trailing4")
FAMILY_SIZE = 18


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")


def sources():
    files=[Path(__file__),Path(ge.__file__),Path(__file__).with_name("worldsim.py"),
           Path(__file__).with_name("worldparams.json"),Path(__file__).with_name("bench_metrics.py"),
           ROOT/"g3/v33/bench_protocol.json",ROOT/"docs/J5 세계 진단 계획.md"]
    files+=sorted((ROOT/"padfec").glob("*.py"))+sorted((ROOT/"padfec3").glob("*.py"))
    return {p.relative_to(ROOT).as_posix():sha(p) for p in files}


def make_plan():
    protocol=read(ROOT/"g3/v33/bench_protocol.json")
    assert protocol["seeds"]==list(range(31,51)) and protocol["world"]["profile"]=="default"
    for name,digest in protocol["world"]["source_sha256"].items():
        assert sha(Path(__file__).with_name(name))==digest
    scenarios=[next(s for s in protocol["scenarios"] if s["id"]==name) for name in SCENARIOS]
    assert all(not s.get("mixture") and not s["world_params"] for s in scenarios)
    connections=sum(sum(p["length"] for p in s["phases"]) for s in scenarios)*20
    return dict(schema="j5-known-loss-world-diagnostic/1",data_kind="development_independent_event_world",
                source_sha256=sources(),scenarios=scenarios,seeds=protocol["seeds"],c_pkt=protocol["c_pkt"],
                family_size=FAMILY_SIZE,seed_runs=120,connection_contexts=connections,
                arms=ARMS,noninferiority_ms=.5,active_policy_changed=False,
                learning_connected=False,full_w1_adoption_gate=False)


def validate_plan(plan):
    if json.dumps(plan,sort_keys=True)!=json.dumps(make_plan(),sort_keys=True):
        raise ValueError("plan or source identity changed")


def schedule(scenario,smoke=False):
    offset=0
    for number,phase in enumerate(scenario["phases"]):
        for index in range(min(4,phase["length"]) if smoke else phase["length"]):
            yield number,index,offset+index
        offset+=phase["length"]


def design(scenario,phase,c_pkt):
    context=dict(scenario["context"])
    context.update({key:value for key,value in phase.items() if key!="length"})
    k,w,p=context["k"],context["w"],context["p"]
    S=context["cert_bytes"]+quantum.s0_at(quantum.bin_index(k*w),policy.S0_BASE_MLKEM,c_pkt)
    need=learn3.bin_needed_s(S,quantum.bin_index(k*w),c_pkt)
    candidates=decide3.candidates3(k,w,S,c_pkt)
    arms={"fixed_trailing4":(0,0,4)}
    tables={}
    true_burst=context.get("burst_length",1) if context.get("loss_model","iid")=="ge" else 1
    for name,burst in (("iid",1),("known_burst",true_burst),("forced_burst3",3)):
        model=ge.GEReference(burst)
        table=[]
        for candidate in candidates:
            outcome=model.evaluate(k,candidate["W_eff"],candidate["m"],candidate["lead"],
                                   p,context["rtt_ms"],context["uplink_mbps"],need)
            table.append(dict(candidate,score=outcome["J"],prediction=outcome))
        selected,jmin,ntied=decide3.pick(table)
        arms[name]=selected["action"]
        tables[name]=dict(requested_mean_burst=burst,selected=selected["action"],minimum_cost_ms=jmin,
                         tied_candidates=ntied,candidates=table)
    assert all(tuple(a) in {tuple(c["action"]) for c in candidates} for a in arms.values())
    return dict(context=context,S=S,n_need=need,arms=arms,tables=tables)


def execute(job):
    plan,scenario,seed,output,smoke=job
    validate_plan(plan)
    destination=Path(output)/f"{scenario['id']}_seed{seed}"
    destination.mkdir(parents=True,exist_ok=False)
    designs=[design(scenario,phase,plan["c_pkt"]) for phase in scenario["phases"]]
    world=World(params=scenario["world_params"],profile="default",seed=seed)
    assert not world.params["channel"]["preserve_ge_across_connections"]
    totals={name:dict(hct=0.0,first_failure=0,final_failure=0,client_bytes=0,server_bytes=0,pto=0) for name in ARMS}
    pairs={name:dict(difference_sum=0.0,same_action=True) for name in ARMS[1:]}
    n=samples=0
    raw=destination/"rows.jsonl.gz"
    with raw.open("xb") as binary:
        with gzip.GzipFile(fileobj=binary,mode="wb",mtime=0,filename="") as zipped:
            with io.TextIOWrapper(zipped,encoding="utf-8",newline="\n") as stream:
                for number,index,connection in schedule(scenario,smoke):
                    chosen=designs[number]
                    context=WorldContext(**chosen["context"])
                    outputs={}
                    for action in sorted(set(tuple(a) for a in chosen["arms"].values())):
                        observed=world.sample(context,Action(*action),connection=connection,trace=index==0)
                        key=",".join(map(str,action))
                        outputs[key]=dict(hct=observed["hct"],first_failure=observed["world_class"]=="failure",
                            world_class=observed["world_class"],final_failure=not observed["ok"],
                            client_bytes=observed["client_total_uplink_bytes"],server_bytes=observed["server_counted_uplink_bytes"],
                            pto=observed["pto_count"])
                        if index==0:write(destination/f"phase{number}_{key.replace(',','_')}_trace.json",observed)
                        samples+=1
                    for name,action in chosen["arms"].items():
                        observed=outputs[",".join(map(str,action))]
                        for field in totals[name]:totals[name][field]+=observed[field]
                    baseline=outputs[",".join(map(str,chosen["arms"]["iid"]))]["hct"]
                    for name in pairs:
                        pairs[name]["difference_sum"]+=outputs[",".join(map(str,chosen["arms"][name]))]["hct"]-baseline
                        pairs[name]["same_action"]&=tuple(chosen["arms"][name])==tuple(chosen["arms"]["iid"])
                    stream.write(json.dumps(dict(connection=connection,phase=number,phase_index=index,samples=outputs),separators=(",",":"),allow_nan=False)+"\n")
                    n+=1
    validate_plan(plan)
    result=dict(job_id=destination.name,scenario=scenario["id"],seed=seed,smoke=smoke,n=n,world_samples=samples,
                designs=designs,totals=totals,pairs=pairs,rows_sha256=sha(raw),source_sha256=sources(),
                params_sha256=world.params_sha256)
    write(destination/"result.json",result)
    return result


def inference(values,same):
    ordinary=paired_summary(values)
    adjusted=paired_summary(values,confidence=1-.05/FAMILY_SIZE)
    unresolved=not same and (ordinary["sd"] is None or ordinary["sd"]<=1e-12)
    if same:
        assert all(x==0 for x in values)
    elif unresolved:
        for result in (ordinary,adjusted):
            result.update(lower=None,upper=None,half_width=None,interval_available=False)
    return dict(paired95=ordinary,family95=adjusted,structural_zero=same,zero_variance_unresolved=unresolved,
                decrease=adjusted["upper"] is not None and adjusted["upper"]<0,
                harm_above_0_5=adjusted["lower"] is not None and adjusted["lower"]>.5)


def summarize(results,plan,smoke):
    comparisons=[]
    for scenario in SCENARIOS:
        selected=sorted([r for r in results if r["scenario"]==scenario],key=lambda r:r["seed"])
        assert [r["seed"] for r in selected]==(plan["seeds"][:1] if smoke else plan["seeds"])
        for arm in ARMS[1:]:
            values=[r["pairs"][arm]["difference_sum"]/r["n"] for r in selected]
            same=all(r["pairs"][arm]["same_action"] for r in selected)
            comparisons.append(dict(scenario=scenario,arm=arm,seed_differences=values,
                                    **inference(values,same)))
    return dict(data_kind="development_independent_event_world",smoke=smoke,runs=len(results),
                connection_contexts=sum(r["n"] for r in results),world_samples=sum(r["world_samples"] for r in results),
                comparisons=comparisons,active_policy_changed=False,full_w1_adoption_gate=False)


def collect(plan,output,smoke=False):
    validate_plan(plan)
    output.mkdir(parents=True,exist_ok=False)
    write(output/"plan.json",plan)
    seeds=plan["seeds"][:1] if smoke else plan["seeds"]
    jobs=[(plan,s,seed,str(output/"jobs"),smoke) for s in plan["scenarios"] for seed in seeds]
    results=[]
    timer=time.monotonic()
    def status(state):
        value=dict(status=state,pid=os.getpid(),completed=len(results),total=len(jobs),seconds=time.monotonic()-timer,
                   updated_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat())
        (output/"status.json").write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8",newline="\n")
    status("running")
    try:
        with ProcessPoolExecutor(max_workers=2) as pool:
            for future in as_completed([pool.submit(execute,job) for job in jobs]):
                results.append(future.result())
                status("running")
        result=summarize(results,plan,smoke)
        result.update(source_sha256=sources(),elapsed_seconds=time.monotonic()-timer,
                      input_results=[dict(job_id=r["job_id"],sha256=sha(output/"jobs"/r["job_id"]/"result.json"))
                                     for r in sorted(results,key=lambda r:r["job_id"])])
        write(output/"summary.json",result)
        status("complete")
        (output/"DONE").write_text(sha(output/"summary.json")+"\n",encoding="ascii")
    except BaseException:
        status("failed")
        raise
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.prepare:
        plan=make_plan();write(args.plan,plan)
        print(json.dumps(dict(plan=str(args.plan),sha256=sha(args.plan),connections=plan["connection_contexts"])))
        return
    plan=read(args.plan);validate_plan(plan)
    if args.dry_run:
        print(json.dumps(dict(status="PASS",runs=plan["seed_runs"],connections=plan["connection_contexts"])))
        return
    if args.out is None:parser.error("--out is required")
    result=collect(plan,args.out,args.smoke)
    print(json.dumps({k:result[k] for k in ("runs","connection_contexts","world_samples","elapsed_seconds")}))


if __name__=="__main__":
    main()
