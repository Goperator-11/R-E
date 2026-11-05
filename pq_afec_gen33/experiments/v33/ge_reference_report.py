import sys
sys.dont_write_bytecode = True
import argparse
from collections import defaultdict, deque
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
from statistics import mean, pstdev
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from experiments.v33 import ge_reference as ge, worldsim
from padfec import policy, quantum
from padfec3 import layout, learn3


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")


def historical(journal):
    groups = defaultdict(list)
    server = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        for segment in json.loads(line)["val"]["segments"]:
            for row in segment["rows"]:
                if row["server_bytes"]:
                    server.append(row["server_bytes"])
                if segment["arm"] == "g3auto" and "action" in row:
                    groups[tuple(row["action"])].append(row)
    server.sort()
    S = server[len(server)//2]
    need = learn3.bin_needed_s(float(S),quantum.bin_index(2560),policy.C_PKT_POLICY_DEFAULT)
    models = {"iid":ge.GEReference(1),"ge":ge.GEReference(3)}
    result = []
    for action,rows in sorted(groups.items()):
        if len(rows)<50:
            continue
        delta,lead,trail = action
        observed = mean(row["ms"] for row in rows)
        values = {name:model.evaluate(2,1280+delta,lead+trail,lead,.15,50,0,need)
                  for name,model in models.items()}
        result.append(dict(action=action,n=len(rows),observed_mean_hct_ms=observed,
                           retx_proxy=sum(not row["ok"] or row["initial_datagrams"]>=4 for row in rows)/len(rows),
                           prediction=values,residual_ms={name:observed-v["J"] for name,v in values.items()}))
    return dict(source=str(journal),sha256=digest(journal),median_server_bytes=S,n_need=need,
                rows=result,proxy_definition="not ok or initial_datagrams >= 4; not a direct first-flight failure label")


def regression(verifier_path):
    spec = importlib.util.spec_from_file_location("_j5_verifier",verifier_path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    count = 0
    max_iid = max_ge = 0.0
    rounds = []
    for k,w,u,rtt,need in ((2,1280,2,50.7,15),(2,1280,0,50,4),
                           (2,1280,10,120,7),(1,1280,0,50,6)):
        for m in range(5):
            for lead in range(m+1):
                for p in (0,.02,.15,.3):
                    args = (k,w,m,lead,p,rtt,u,need)
                    old = layout.evaluate(*args)
                    iid = ge.GEReference(1).evaluate(*args)
                    burst = ge.GEReference(3).evaluate(*args)
                    direct = verifier.evaluate_gen(verifier.std_order(k,lead,m-lead),k,w,p,rtt,u,need,
                                                   probf=verifier.make_ge(p,3))
                    max_iid = max(max_iid,max(abs(iid[key]-old[key]) for key in old if isinstance(old[key],(int,float))))
                    max_ge = max(max_ge,abs(burst["J"]-direct["J"]),abs(burst["p_fail"]-direct["pf"]))
                    count += 1
    for m in range(1,5):
        lead = layout.legacy_lead(m)
        first = ge.GEReference(3).evaluate(2,1280,m,lead,.15,50,0,5)
        exact = ge.expected_attempts(2,m,lead,.15,3)
        retry = ge.expected_attempts(2,m,lead,.15,3,retry=(2,1,0))
        rounds.append(dict(m=m,lead=lead,stationary_reset_multiplier=first["round_mult"],
                           same_action=exact,original_first=retry,
                           gen2_truncated_rounds=policy.expected_rounds(2,m,.15,3)))
    assert max_iid<=1e-12 and max_ge<=1e-12
    return dict(context_action_probability_cases=count,max_iid_absolute_error=max_iid,
                max_verifier_absolute_error=max_ge,rounds=rounds,verifier_sha256=digest(verifier_path))


def synthetic(out):
    summaries = []
    for p,model,seed in itertools.product((.02,.15,.25),("iid","ge"),range(31,51)):
        target = 1/(1-p) if model=="iid" else 3.0
        histories = {"complete":deque(maxlen=64),"success_only":deque(maxlen=64)}
        estimates = {key:[] for key in histories}
        raw_path = out / f"synthetic_p{p}_{model}_seed{seed}.jsonl"
        with raw_path.open("x",encoding="utf-8",newline="\n") as stream:
            for connection in range(1350):
                pattern = [int(x) for x in worldsim.sample_loss_pattern(6,p,loss_model=model,
                            burst_length=3,seed=seed,connection=connection)]
                success = sum(pattern)>=2
                arrival = {"src":"c1","sent":6,"lost":pattern.count(0),"bitmap":pattern,"trunc":False}
                values = {}
                for mode,history in histories.items():
                    history.append(ge.BurstObservation("synthetic",arrival if mode=="complete" or success else None,True,True))
                    value = ge.estimate_burst(history,"synthetic",p)
                    estimates[mode].append(value["mean_burst"])
                    values[mode] = value
                stream.write(json.dumps(dict(connection=connection,pattern=pattern,success=success,estimates=values),
                                        separators=(",",":"),allow_nan=False)+"\n")
        for mode,values in estimates.items():
            tail = values[-450:]
            summaries.append(dict(p=p,loss_model=model,seed=seed,observation=mode,target_mean_burst=target,
                final_mean_burst=values[-1],last450_mean=mean(tail),last450_sd=pstdev(tail),
                last450_mean_absolute_error=mean(abs(x-target) for x in tail),
                source=raw_path.name,sha256=digest(raw_path)))
        print(json.dumps(dict(p=p,loss_model=model,seed=seed,complete_final=estimates["complete"][-1],
                              success_only_final=estimates["success_only"][-1])),flush=True)
    return summaries


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--verifier",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    files = [Path(__file__),Path(ge.__file__),Path(worldsim.__file__),Path(policy.__file__),
             Path(layout.__file__),Path(learn3.__file__),ROOT/"afec/channel.py",ROOT/"docs/J5_ge_contract.md"]
    before = {str(p.relative_to(ROOT)):digest(p) for p in files}
    timer = time.monotonic()
    results = dict(data_kind="development_reference_and_synthetic_diagnostic",
                   historical=historical(args.journal),regression=regression(args.verifier),
                   synthetic=synthetic(args.output))
    after = {str(p.relative_to(ROOT)):digest(p) for p in files}
    results.update(seconds=time.monotonic()-timer,source_sha256=before,source_sha256_after=after,unchanged=before==after)
    write(args.output/"result.json",results)
    assert before==after
    print(json.dumps(dict(result=str(args.output/"result.json"),sha256=digest(args.output/"result.json"),
                          seconds=results["seconds"],unchanged=results["unchanged"])),flush=True)


if __name__ == "__main__":
    main()
