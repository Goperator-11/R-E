import sys
sys.dont_write_bytecode = True
import argparse
import collections
from fractions import Fraction
import math
from pathlib import Path
from statistics import NormalDist

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from experiments.v33 import bench, bench_m1_family as family, bench_report, bench_learning_report as legacy
from experiments.v33 import m1_pool_validation as validation
from experiments.v33.bench_metrics import paired_summary

SCHEMA="padfec.v33.m1_factorial_report/1"
PATH=Path(__file__).resolve()
IMPORTED_SHA=bench.file_hash(PATH)


def width(table, absolute, z):
    if not absolute and table.get("gap_exact_by_identity"):
        return 0.
    if not absolute and bench_report.gap_width(table) is None:
        return None
    n=table["n"]
    variance=bench_report.finite(table["variance_hct_ms2" if absolute else "gap_variance_ms2"],"MC variance")
    if n<2 or variance<=1e-20:
        return None
    return z*math.sqrt(variance/n)


def comparison(candidate, baseline, tables, rules, same_world):
    ca,ba=({r["seed"]:r for r in runs} for runs in (candidate,baseline))
    if set(ca)!=set(ba) or len(ca)!=len(candidate) or len(ba)!=len(baseline):
        raise ValueError("paired seed inventory")
    family_size=len(tables)
    z=NormalDist().inv_cdf(1-(1-rules["mc_family_confidence"])/(4*family_size))
    coefficients=collections.defaultdict(Fraction)
    estimates=[]
    field="mean_gap_ms" if same_world else "mean_hct_ms"
    for seed in sorted(ca):
        cw,bw=bench_report.weights(ca[seed]),bench_report.weights(ba[seed])
        if same_world and bench_report.context_weights(cw)!=bench_report.context_weights(bw):
            raise ValueError("same-world context weights")
        differences={key:cw.get(key,Fraction())-bw.get(key,Fraction()) for key in cw.keys()|bw.keys()}
        for key,weight in differences.items():
            coefficients[key]+=weight/len(ca)
        estimate=math.fsum(float(weight)*bench_report.finite(tables[key][field],field)
                           for key,weight in differences.items() if weight)
        estimates.append({"seed":seed,"mean_delta_ms":estimate})
    terms=[]
    unresolved=[]
    for key,weight in sorted(coefficients.items()):
        if not weight:
            continue
        bound=width(tables[key],not same_world,z)
        if bound is None:
            unresolved.append([key[0],list(key[1])])
        else:
            terms.append(abs(float(weight))*bound)
    mc=None if unresolved else math.fsum(terms)
    summary=paired_summary([r["mean_delta_ms"] for r in estimates],rules["seed_confidence"])
    realized=paired_summary([ca[s]["summary"]["mean_hct_ms"]-ba[s]["summary"]["mean_hct_ms"] for s in sorted(ca)],rules["seed_confidence"])
    gate=bench_report.threshold_from_summary(summary,rules["noninferiority_ms"],mc_bound=mc,inclusive=True)
    return {"seed_summary":summary,"seed_estimates":estimates,"shared_mc_bound_ms":mc,
            "lower_bound_ms":summary["lower"]-mc if mc is not None and summary["lower"] is not None else None,
            "upper_bound_ms":summary["upper"]+mc if mc is not None and summary["upper"] is not None else None,
            "realized_hct_diagnostic":realized,"regression_gate":gate,"unresolved":unresolved,
            "same_world":same_world,"oracle_cancels":same_world,"mc_z":z,"mc_scalar_family_size":2*family_size,
            "sign":"candidate minus baseline; negative is faster"}


def inventory(runs,plan):
    groups=collections.defaultdict(list)
    expected={(p,role,mode,s["id"],seed) for p,protocol in plan["protocols"].items()
              for role in plan["policies"] for mode in plan["modes"] for s in protocol["scenarios"] for seed in protocol["seeds"]}
    expected|={("off",role,"legacy",s["id"],seed) for role in ("v31","v32")
               for s in plan["protocols"]["off"]["scenarios"] for seed in plan["protocols"]["off"]["seeds"]}
    seen=set()
    for run in runs:
        key=run["profile"],run["role"],run["observation_mode"],run["scenario"]
        identity=(*key,run["seed"])
        if identity in seen or identity not in expected:
            raise ValueError("duplicate or unknown report run")
        seen.add(identity);groups[key].append(run)
    family.equal(seen,expected,"complete M1 report inventory")
    return groups


def aggregate(runs,tables,plan):
    groups=inventory(runs,plan)
    rows=[]
    for candidate,baseline in plan["report_rules"]["primary_contrasts"]:
        cp,cr=candidate.split("/");bp,br=baseline.split("/")
        for mode in plan["modes"]:
            for scenario in plan["protocols"][cp]["scenarios"]:
                sid=scenario["id"]
                cm=mode;bm="legacy" if br in ("v31","v32") else mode
                row=comparison(groups[cp,cr,cm,sid],groups[bp,br,bm,sid],tables,plan["report_rules"],cp==bp)
                row.update(candidate=candidate,baseline=baseline,mode=mode,scenario=sid,
                           primary=mode in plan["report_rules"]["primary_modes"])
                rows.append(row)
    primary=[r for r in rows if r["primary"]]
    expected=len(plan["report_rules"]["primary_contrasts"])*len(plan["report_rules"]["primary_modes"])*len(plan["protocols"]["off"]["scenarios"])
    family.equal(len(primary),expected,"primary count")
    statuses=collections.Counter(r["regression_gate"]["status"] for r in primary)
    status=bench_report._all_status([r["regression_gate"]["status"] for r in primary])
    improved=[r["scenario"] for r in primary if r["candidate"]=="hold/m1" and r["baseline"]=="off/l1" and r["mode"]=="c1"
              and r["upper_bound_ms"] is not None and r["upper_bound_ms"]<0]
    verdict={"status":"pass" if status=="pass" and improved else "fail" if status=="fail" else "inconclusive",
             "noninferiority":status,"primary_cells":len(primary),"counts":dict(statuses),"c1_endpoint_improved_cells":improved}
    contribution=[]
    for mode in plan["modes"]:
        for scenario in plan["protocols"]["off"]["scenarios"]:
            sid=scenario["id"]
            for cp,cr,bp,br,kind in (("off","m1","off","l1","policy_off"),
                                    ("hold","l1","off","l1","receiver_l1"),("hold","m1","off","m1","receiver_m1")):
                row=comparison(groups[cp,cr,mode,sid],groups[bp,br,mode,sid],tables,plan["report_rules"],cp==bp)
                row.update(mode=mode,scenario=sid,kind=kind,primary=False)
                contribution.append(row)
    return {"schema":SCHEMA,"status":"complete","data_kind":plan["data_kind"],"comparisons":rows,
            "factorial_contributions":contribution,"performance_decision":verdict,"report_rules":plan["report_rules"],
            "limitations":["normal approximation; no distribution-free guarantee", "single connection valid-metadata event world", 
                           "Go policy mirror and first-send QUIC credit gates remain separate", "no new-profile absolute optimum claim"]}


def markdown(report):
    v=report["performance_decision"]
    lines=["# M1 개발 기대 비용 평가","",f"전체 판정: {v['status']}. 주 비교 {v['primary_cells']}셀. 비열등 상태: {v['counts']}.",
           "", "차이는 후보에서 기준을 뺀 값이며 단위는 ms/연결이다. 구간은 seed 95%와 MC 가족 99% 정규근사 오차를 합쳤다.",
           "", "| 후보 / 기준 | 관측 | 시나리오 | 기대 차이 | 보정 상한 | 판정 |", "|---|---|---|---:|---:|---|"]
    for row in report["comparisons"]:
        if row["primary"]:
            upper="미확정" if row["upper_bound_ms"] is None else f"{row['upper_bound_ms']:.6f}"
            lines.append(f"| {row['candidate']} / {row['baseline']} | {row['mode']} | {row['scenario']} | {row['seed_summary']['mean']:.6f} | {upper} | {row['regression_gate']['status']} |")
    return "\n".join(lines)+"\n"


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--family",type=Path,required=True);parser.add_argument("--sha256",required=True)
    parser.add_argument("--pool",type=Path,required=True);parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--markdown",type=Path,required=True)
    args=parser.parse_args()
    saved,metadata,runs=family.execution_plan(args.family,args.sha256)
    plan=family.collector.load_plan(saved["collection_plan_path"])
    with family.pool.exclusive_lock(args.pool/".pool.lock"):
        tables,provenance=validation.validate_pool_locked(args.pool,saved["manifest"],metadata)
        report=aggregate(runs,tables,plan)
        report.update(family_plan_sha256=args.sha256,producer_sha256=IMPORTED_SHA,pool_validation=provenance)
        family.equal(bench.file_hash(PATH),IMPORTED_SHA,"report source unchanged")
        bench.write_new(args.out,report)
        with args.markdown.open("x",encoding="utf-8",newline="\n") as f:f.write(markdown(report))
    print(report["performance_decision"])


if __name__=="__main__":
    main()
