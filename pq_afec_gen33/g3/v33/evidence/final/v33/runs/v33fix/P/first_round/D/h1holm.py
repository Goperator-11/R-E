import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import json
d = json.load(open(r"C:\dev\pq_afec_gen31\experiments\results\p31_gencompare_decisions.json", encoding="utf-8"))
h1 = d["H1"]
for run in ("run1", "run2"):
    r = h1[run]
    print(run, {k: v for k, v in r.items() if not isinstance(v, (list, dict))})
    for t in r["tests"]:
        print("  ", {k: t[k] for k in t if not isinstance(t[k], (list, dict))})
