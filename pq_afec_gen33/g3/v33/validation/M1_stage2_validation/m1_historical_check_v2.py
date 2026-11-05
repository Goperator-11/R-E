import sys
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0,r"C:\dev\pq_afec_gen33")
import time
from experiments.v33 import bench_m1_family as f

start=time.monotonic()
plan=f.collector.load_plan(f.collector.PLAN)
rows,inputs=f.historical_runs(plan)
controls,source=f.frozen_reference_controls(plan)
protocol=f.combined_protocol(plan)
aliases=[{"generation":"design_validation","variant":"full","scenario":"context","seed":0,"n":1,
          "action_counts":[{"context_id":cid,"action":v["chosen_action"],"n":1}]} for cid,v in controls.items()]
manifest=f.manifest_with_fixed(protocol,"validation",aliases,controls)
assert len(manifest["additional_fixed_design_keys"]) == 64
record={"status":"pass","historical_runs":len(rows),"historical_connections":sum(r["n"] for r in rows),
        "inputs_sha256":inputs,"controls":len(controls),"design_test_jobs":len(manifest["jobs"]),
        "fixed_design_keys":len(manifest["additional_fixed_design_keys"]),"family_source_sha256":f.IMPORTED_SHA,
        "elapsed_seconds":time.monotonic()-start}
f.bench.write_new(f.collector.RUNS/"M1_historical_check_02.json",record)
print({k:v for k,v in record.items() if k!="inputs_sha256"})
