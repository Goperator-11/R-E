import sys
sys.dont_write_bytecode = True
import argparse
import collections
from concurrent.futures import ProcessPoolExecutor, as_completed
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scipy
from scipy.stats import norm, t
from experiments.v33 import bench, worldsim_m1 as world
from experiments.v33.first_flight_observer import make_world_evidence

PATH = Path(__file__).resolve()
PLAN = ROOT / "g3/v33/bench_overlays/M1_evaluation_v1.json"
PLAN_SHA = "5be8bd6cb35a9d309c7c762a0ee0a2ff62e068c0f689875b4e0942fe2decf591"
SCHEMA = "padfec.v33.m1_independent_validation/1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def same(actual, expected, label):
    if canonical(actual) != canonical(expected):
        raise ValueError("independent M1 check: " + label)


def close(actual, expected, label):
    if actual is None or expected is None:
        same(actual, expected, label)
    elif isinstance(actual, bool) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-10):
        raise ValueError(f"independent M1 numeric check {label}: {actual!r} != {expected!r}")


def same_counts(actual,expected,label):
    key=lambda row:(row["context_id"],row["action"])
    same(sorted(actual,key=key),sorted(expected,key=key),label)


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def spec_for(scenario, phase):
    return {"context": {**scenario["context"], **{k: v for k, v in phase.items() if k != "length"}},
            "world_params": scenario["world_params"], "mixture": scenario.get("mixture", [])}


def raw_job(job):
    plan = read(PLAN)
    profile, role, mode, sid = job
    protocol = plan["protocols"][profile]
    scenario = next(s for s in protocol["scenarios"] if s["id"] == sid)
    folder = Path(plan["raw_root"]) / "_".join(job)
    completed = read(folder / "finished.json")
    same(completed["status"], "complete", "shard completion")
    same(completed["seeds"], protocol["seeds"], "shard seeds")
    schedule = []
    for phase_number, phase in enumerate(scenario["phases"]):
        spec = spec_for(scenario, phase)
        cid = hashlib.sha256(canonical(spec)).hexdigest()[:20]
        for phase_index in range(phase["length"]):
            schedule.append((phase_number, phase_index, cid, spec, phase_index in (0, phase["length"] - 1)))
    results = []
    for seed in protocol["seeds"]:
        path = folder / f"seed{seed:05d}.json"
        same(sha(path), completed["results_sha256"][str(path)], "raw completion hash")
        raw = read(path)
        trace = Path(raw["trace_path"])
        same(sha(trace), raw["trace_sha256"], "raw trace hash")
        same([raw[k] for k in ("profile", "role", "observation_mode", "scenario", "seed", "n")],
             [*job, seed, len(schedule)], "raw identity and length")
        fixed = read(raw["baseline_path"])
        same(sha(raw["baseline_path"]), raw["baseline_sha256"], "fixed source hash")
        same(sha(fixed["trace_path"]), fixed["trace_sha256"], "fixed trace hash")
        with gzip.open(fixed["trace_path"], "rt", encoding="utf-8") as stream:
            fixed_rows = [json.loads(line) for line in stream]
        counts, observations = collections.Counter(), collections.Counter()
        values = {name: [] for name in ("hct_ms", "extra_server_bytes", "extra_first_flight_bytes", "extra_client_first_flight_bytes")}
        minimum_rtt = minimum_hct = None
        checked = replayed = failed = 0
        high_errors = []
        highest = max(spec_for(scenario, p)["context"]["p"] for p in scenario["phases"])
        tail = protocol["metrics"]["p_bias_high_phase_last_n"]
        cold, transition = protocol["metrics"]["cold_alarm_exclusion"], protocol["metrics"]["transition_alarm_exclusion"]
        eligible = alarms = 0
        engine = world.World(params=scenario["world_params"], seed=seed)
        with gzip.open(trace, "rt", encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                row = json.loads(line)
                phase, phase_index, cid, spec, replay = schedule[index]
                same([row[k] for k in ("index", "world_connection_index", "phase", "phase_index", "context_id", "observation_mode")],
                     [index, index, phase, phase_index, cid, mode], "row schedule")
                if scenario["reset_each_connection"]:
                    minimum_rtt = minimum_hct = None
                previous_rtt = minimum_rtt if minimum_rtt is not None else minimum_hct
                same(row["policy_decide_input"], {"op": "decide", "destination": "d", "rtt_ms": previous_rtt}, "causal decision RTT")
                value = row["raw_observed_rtt_ms"]
                if value is not None and math.isfinite(value) and value > 0:
                    minimum_rtt = value if minimum_rtt is None else min(minimum_rtt, value)
                if row["ok"]:
                    minimum_hct = row["hct_ms"] if minimum_hct is None else min(minimum_hct, row["hct_ms"])
                observed_rtt = minimum_rtt if minimum_rtt is not None else minimum_hct
                same(row["policy_rtt_ms"], observed_rtt, "causal observation RTT")
                request = row["policy_observe_input"]
                same(sorted(request), sorted(["op", "destination", "action", "hct_ms", "ok", "k_obs", "srv_bytes", "rtt_ms", "j_pred", "optional"]), "request boundary")
                same(sorted(request["optional"]), ["first_flight_evidence"], "optional boundary")
                expected = {"op": "observe", "destination": "d", "action": row["action"], "ok": row["ok"],
                            "hct_ms": row["hct_ms"] if row["ok"] else None, "rtt_ms": observed_rtt,
                            "j_pred": row["decision"].get("j3_pred_pre_ms", row["decision"].get("ej"))}
                same({k: request[k] for k in expected}, expected, "observation values")
                same(row["decision"]["action"], row["action"], "decision action")
                evidence, info = request["optional"]["first_flight_evidence"], row["observation_info"]
                same(sorted(evidence), sorted(["src", "sent", "lost", "bitmap", "trunc"]), "evidence boundary")
                if evidence["src"] not in ("none", "c1") or mode == "none" and evidence["src"] != "none":
                    raise ValueError("unexpected evidence source")
                usable = evidence["src"] != "none" and evidence["sent"] > 0 and not evidence["trunc"]
                same(info["arrival_usable"], usable, "evidence usability")
                same(info["loss_update_kind"] == "datagram", usable, "likelihood routing")
                for name, source in (("arrival_sent", "sent"), ("arrival_lost", "lost"), ("arrival_trunc", "trunc"), ("loss_evidence_src", "src")):
                    same(info[name], evidence[source], "evidence mapping")
                observations[info["loss_update_kind"]] += 1
                base = fixed_rows[index]
                for name in ("b0_hct_ms", "b0_server_bytes", "global_fixed_hct_ms", "global_fixed_server_bytes", "selected_cert_bytes", "true_rtt_ms"):
                    same(row[name], base[name], "fixed CRN row")
                close(row["extra_server_bytes"], row["server_bytes"] - row["b0_server_bytes"], "server byte delta")
                if replay:
                    context = world.WorldContext(**asdict(bench.mixture_context(spec, seed, index)))
                    simulation = engine.sample(context, world.Action(*row["action"]), connection=index, trace=mode != "none")
                    for target, source in (("hct_ms", "hct"), ("ok", "ok"), ("server_bytes", "server_counted_uplink_bytes"),
                                           ("selected_cert_bytes", "selected_cert_bytes"), ("true_rtt_ms", "true_rtt_ms")):
                        same(row[target], simulation[source], "fixed endpoint world replay")
                    projection = make_world_evidence(simulation, mode=mode, seed=seed, connection=index,
                        feedback_loss_probability=context.s2c_loss if engine.params["features"]["s2c_loss"] else 0.0,
                        receiver_max_datagram_bytes=engine.params["server"]["decoder_max_datagram_bytes"],
                        feedback_grace_ms=200, crc_list_limit=64)
                    same(evidence, projection["evidence"], "endpoint evidence replay")
                    same(row["observer_diagnostics"], projection["diagnostics"], "endpoint observer replay")
                    replayed += 1
                counts[cid, tuple(row["action"])] += 1
                if row["phase_p"] == highest and phase_index >= scenario["phases"][phase]["length"] - tail and row["p_mean_pre"] is not None:
                    high_errors.append(row["p_mean_pre"] - row["phase_p"])
                if not (scenario["reset_each_connection"] and cold > 0) and index >= cold and (phase == 0 or phase_index >= transition):
                    eligible += 1
                    alarms += len(set(row["alarm_raised"]))
                for name in values:
                    values[name].append(row[name])
                failed += not row["ok"]
                checked += 1
        same(checked, len(schedule), "complete trace")
        actual_counts = [{"context_id": cid, "action": list(action), "n": n} for (cid, action), n in sorted(counts.items())]
        same(actual_counts, raw["action_counts"], "action frequency reconstruction")
        means = {"mean_" + name: math.fsum(numbers) / checked for name, numbers in values.items()}
        means.update(failure_rate=failed / checked,
                     p_bias_high_phase=statistics.mean(high_errors) if high_errors else None,
                     p_mae_high_phase=statistics.mean(map(abs, high_errors)) if high_errors else None,
                     alarm_rate_per_1000=1000 * alarms / eligible if eligible else None)
        for name, value in means.items():
            close(raw["summary"][name], value, "raw summary " + name)
        same(raw["summary"]["failure_count"], failed, "failure count")
        results.append({"profile": profile, "role": role, "mode": mode, "scenario": sid, "seed": seed,
                        "n": checked, "action_counts": actual_counts, "means": means,
                        "failures": failed, "likelihood_counts": dict(observations), "world_endpoint_replays": replayed,
                        "raw_path": str(path), "raw_sha256": sha(path), "trace_sha256": sha(trace)})
    return results


def historical_job(run):
    plan=read(PLAN)
    original=read(plan["original_protocol"])
    before=next(s for s in original["scenarios"] if s["id"]==run["scenario"])
    after=next(s for s in plan["protocols"]["off"]["scenarios"] if s["id"]==run["scenario"])
    schedule=[]
    for phase,(old,new) in enumerate(zip(before["phases"],after["phases"],strict=True)):
        oldspec,spec=spec_for(before,old),spec_for(after,new)
        oldcid=hashlib.sha256(canonical(oldspec)).hexdigest()[:20]
        cid=hashlib.sha256(canonical(spec)).hexdigest()[:20]
        for index in range(old["length"]):
            schedule.append((phase,index,oldcid,cid,spec,index in (0,old["length"]-1)))
    same(sha(run["trace_path"]),run["trace_sha256"],"historical trace hash")
    counts,oldcounts=collections.Counter(),collections.Counter()
    hct=[]
    replayed=failed=0
    engine=world.World(params=after["world_params"],seed=run["seed"])
    with gzip.open(run["trace_path"],"rt",encoding="utf-8") as f:
        for index,line in enumerate(f):
            row=json.loads(line)
            phase,position,oldcid,cid,spec,replay=schedule[index]
            same([row[k] for k in ("index","phase","phase_index","context_id")],
                 [index,phase,position,oldcid],"historical schedule")
            counts[cid,tuple(row["action"])]+=1
            oldcounts[oldcid,tuple(row["action"])]+=1
            hct.append(row["hct_ms"])
            failed+=not row["ok"]
            if replay:
                context=world.WorldContext(**asdict(bench.mixture_context(spec,run["seed"],index)))
                sample=engine.sample(context,world.Action(*row["action"]),connection=index)
                same(sample["hct"],row["hct_ms"],"historical off-world endpoint")
                same(sample["ok"],row["ok"],"historical endpoint success")
                replayed+=1
    same(len(hct),len(schedule),"historical complete trace")
    same(len(hct),run["n"],"historical run count")
    format_counts=lambda values:[dict(context_id=cid,action=list(action),n=n) for (cid,action),n in sorted(values.items())]
    same(format_counts(oldcounts),run["original_action_counts"],"historical original counts")
    same_counts(format_counts(counts),run["action_counts"],"historical mapped counts")
    mean=math.fsum(hct)/len(hct)
    close(mean,run["summary"]["mean_hct_ms"],"historical HCT")
    return {"profile":"off","role":run["role"],"mode":"legacy","scenario":run["scenario"],"seed":run["seed"],
            "n":len(hct),"action_counts":format_counts(counts),"means":{"mean_hct_ms":mean},
            "failures":failed,"world_endpoint_replays":replayed,"trace_path":run["trace_path"],"trace_sha256":run["trace_sha256"]}


def validate_raw(validated_path,out):
    same(sha(PLAN),PLAN_SHA,"collection plan")
    producer=read(validated_path)
    plan=read(PLAN)
    jobs=[(p,role,mode,s["id"]) for p,protocol in plan["protocols"].items()
          for role in plan["policies"] for mode in plan["modes"] for s in protocol["scenarios"]]
    history=[r for r in producer["runs"] if r["role"] in ("v31","v32")]
    same(len(history),600,"historical inventory count")
    rows=[]
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures=[executor.submit(raw_job,job) for job in jobs]
        for future in as_completed(futures):
            rows.extend(future.result())
            print(json.dumps({"independent_runs":len(rows)}),flush=True)
        for future in as_completed([executor.submit(historical_job,run) for run in history]):
            rows.append(future.result())
    rows.sort(key=lambda r:(r["profile"],r["role"],r["mode"],r["scenario"],r["seed"]))
    same(len(rows),4200,"whole independent run count")
    result={"schema":SCHEMA,"status":"pass","script_sha256":sha(PATH),"plan_sha256":PLAN_SHA,
            "validated_sha256":sha(validated_path),"runs":rows,"run_count":len(rows),
            "connections":sum(r["n"] for r in rows),"world_endpoint_replays":sum(r["world_endpoint_replays"] for r in rows),
            "scope":"raw counts and sums independently rebuilt; producer world and observer replayed at phase endpoints"}
    write(out,result)
    return {k:result[k] for k in ("status","run_count","connections","world_endpoint_replays")}


def weights(run):
    return {(r["context_id"],tuple(r["action"])):Fraction(r["n"],run["n"]) for r in run["action_counts"]}


def paired(values):
    mean=statistics.mean(values)
    width=float(t.ppf(.975,len(values)-1))*statistics.stdev(values)/math.sqrt(len(values))
    return mean,mean-width,mean+width


def difference(candidate,baseline,tables,same_world):
    same([r["seed"] for r in candidate],[r["seed"] for r in baseline],"paired seeds")
    z=float(norm.ppf(1-.01/(4*len(tables))))
    coefficients=collections.defaultdict(Fraction)
    estimates=[]
    for ca,ba in zip(candidate,baseline,strict=True):
        cw,bw=weights(ca),weights(ba)
        if same_world:
            contexts=[]
            for terms in (cw,bw):
                total=collections.defaultdict(Fraction)
                for (cid,_),weight in terms.items():total[cid]+=weight
                contexts.append(dict(total))
            if contexts[0] != contexts[1]:
                raise ValueError("same-world cancellation")
        terms={key:cw.get(key,0)-bw.get(key,0) for key in cw.keys()|bw.keys()}
        column="mean_gap_ms" if same_world else "mean_hct_ms"
        estimates.append(math.fsum(float(value)*tables[key][column] for key,value in terms.items() if value))
        for key,value in terms.items():coefficients[key]+=value/len(candidate)
    bounds=[]
    unresolved=[]
    for key,weight in coefficients.items():
        if not weight:continue
        table=tables[key]
        if same_world and table["action"]==table["reference_action"]:
            half=0.
        else:
            variance=table["gap_variance_ms2" if same_world else "variance_hct_ms2"]
            if variance<=1e-20 or table["n"]<2:
                unresolved.append(key)
                continue
            half=z*math.sqrt(variance/table["n"])
        bounds.append(abs(float(weight))*half)
    mc=None if unresolved else math.fsum(bounds)
    mean,lower,upper=paired(estimates)
    lo,hi=(lower-mc,upper+mc) if mc is not None else (None,None)
    status="pass" if hi is not None and hi<=.5 else "fail" if lo is not None and lo>.5 else "inconclusive"
    return dict(mean=mean,lower=lower,upper=upper,mc=mc,adjusted_lower=lo,adjusted_upper=hi,status=status,
                estimates=estimates,realized=paired([c["means"]["mean_hct_ms"]-b["means"]["mean_hct_ms"] for c,b in zip(candidate,baseline)]))


def check_row(row,result):
    for key in ("mean","lower","upper"):close(row["seed_summary"][key],result[key],"seed "+key)
    for actual,wanted in zip(("shared_mc_bound_ms","lower_bound_ms","upper_bound_ms"),("mc","adjusted_lower","adjusted_upper")):
        close(row[actual],result[wanted],actual)
    same(row["regression_gate"]["status"],result["status"],"threshold")
    for value,wanted in zip(row["seed_estimates"],result["estimates"]):close(value["mean_delta_ms"],wanted,"seed delta")
    for key,wanted in zip(("mean","lower","upper"),result["realized"]):close(row["realized_hct_diagnostic"][key],wanted,"realized "+key)


def validate_report(family_path,raw_path,report_path,pool_path,out):
    saved,independent,result=map(read,(family_path,raw_path,report_path))
    same(independent["status"],"pass","raw checker status")
    same(independent["script_sha256"],sha(PATH),"raw checker source")
    same(independent["validated_sha256"],saved["validated_sha256"],"raw checker input")
    same(result["family_plan_sha256"],sha(family_path),"report family")
    for path,digest in saved["inputs_sha256"].items():same(sha(path),digest,"frozen input")
    for path,digest in result["pool_validation"]["files_sha256"].items():same(sha(path),digest,"pool provenance")
    jobs=saved["manifest"]["jobs"]
    same(sorted(p.stem for p in pool_path.glob("results/*.json")),sorted(j["job_id"] for j in jobs),"MC inventory")
    tables={}
    for job in jobs:
        table=read(pool_path/"results"/(job["job_id"]+".json"))
        for key,wanted in (("action",job["action"]),("reference_action",job["reference_action"]),
                           ("n",131072),("validation_seed",850001),("evaluation_family_size",len(jobs)),
                           ("method","independent_paired_validation")):
            same(table[key],wanted,"MC "+key)
        state=read(pool_path/"checkpoints"/(job["job_id"]+".json"))
        moments=state["records"][",".join(map(str,job["action"]))]
        same(moments["n"],table["n"],"MC moment count")
        for field,moment in (("mean_hct_ms","mean_hct"),("mean_gap_ms","mean_gap")):
            close(table[field],moments[moment],"MC mean")
        for field,moment in (("variance_hct_ms2","m2_hct"),("gap_variance_ms2","m2_gap")):
            close(table[field],max(0.,moments[moment]/(table["n"]-1)),"MC variance")
        tables[job["context_id"],tuple(job["action"])]=table
    observed={(r["context_id"],tuple(r["action"])) for run in independent["runs"] for r in run["action_counts"]}
    fixed={(cid,tuple(action)) for cid,action in saved["manifest"]["additional_fixed_design_keys"]}
    same(sorted(observed|fixed),sorted(tables),"full observed and fixed action union")
    groups=collections.defaultdict(list)
    for run in independent["runs"]:
        groups[run["profile"],run["role"],run["mode"],run["scenario"]].append(run)
    for values in groups.values():values.sort(key=lambda r:r["seed"])
    plan=read(PLAN)
    expected={(ca,ba,mode,s["id"]) for ca,ba in plan["report_rules"]["primary_contrasts"]
              for mode in plan["modes"] for s in plan["protocols"]["off"]["scenarios"]}
    seen=set();statuses=[];improvements=[]
    for row in result["comparisons"]:
        key=row["candidate"],row["baseline"],row["mode"],row["scenario"]
        if key in seen or key not in expected:raise ValueError("comparison inventory")
        seen.add(key)
        cp,cr=key[0].split("/");bp,br=key[1].split("/");mode,sid=key[2:]
        bm="legacy" if br in ("v31","v32") else mode
        calculated=difference(groups[cp,cr,mode,sid],groups[bp,br,bm,sid],tables,cp==bp)
        check_row(row,calculated)
        primary=mode in ("none","c1")
        same(row["primary"],primary,"primary membership")
        if primary:statuses.append(calculated["status"])
        if key[:3]==("hold/m1","off/l1","c1") and calculated["adjusted_upper"] is not None and calculated["adjusted_upper"]<0:
            improvements.append(sid)
    same(sorted(seen),sorted(expected),"complete comparisons")
    contributions={(kind,mode,s["id"]) for kind in ("policy_off","receiver_l1","receiver_m1")
                   for mode in plan["modes"] for s in plan["protocols"]["off"]["scenarios"]}
    seen=set()
    for row in result["factorial_contributions"]:
        key=row["kind"],row["mode"],row["scenario"]
        if key in seen or key not in contributions:raise ValueError("contribution inventory")
        seen.add(key);kind,mode,sid=key
        cp,cr,bp,br={"policy_off":("off","m1","off","l1"),"receiver_l1":("hold","l1","off","l1"),
                     "receiver_m1":("hold","m1","off","m1")}[kind]
        check_row(row,difference(groups[cp,cr,mode,sid],groups[bp,br,mode,sid],tables,cp==bp))
    same(sorted(seen),sorted(contributions),"complete contributions")
    overall="fail" if "fail" in statuses else "pass" if all(s=="pass" for s in statuses) and improvements else "inconclusive"
    same(result["performance_decision"]["status"],overall,"adoption status")
    same(result["performance_decision"]["counts"],dict(collections.Counter(statuses)),"primary statuses")
    same(result["performance_decision"]["c1_endpoint_improved_cells"],improvements,"C1 improvement list")
    output={"schema":SCHEMA,"status":"pass","script_sha256":sha(PATH),"scipy_version":scipy.__version__,
            "family_sha256":sha(family_path),"raw_sha256":sha(raw_path),"report_sha256":sha(report_path),
            "action_family":len(jobs),"comparisons":len(expected),"contributions":len(contributions),
            "primary_cells":len(statuses),"performance_decision":overall,
            "run_count":independent["run_count"],"connections":independent["connections"],
            "world_endpoint_replays":independent["world_endpoint_replays"]}
    write(out,output)
    return output


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("raw")
    p.add_argument("--validated",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("report")
    for name in ("family","raw","report","pool","out"):p.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    initial=sha(PATH)
    value=validate_raw(args.validated,args.out) if args.command=="raw" else validate_report(args.family,args.raw,args.report,args.pool,args.out)
    same(sha(PATH),initial,"checker unchanged")
    print(json.dumps(value,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()


