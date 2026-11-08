import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import json
d = json.load(open(r"C:\dev\pq_afec\experiments\results\p1_flight.json", encoding="utf-8"))
def find(o, key, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key: yield path + "/" + k, v
            yield from find(v, key, path + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from find(v, key, f"{path}[{i}]")
for p, v in find(d, "capacity_checks"):
    print(p, type(v).__name__, len(v))
    rows = v if isinstance(v, list) else list(v.values())
    print(json.dumps(rows[0], ensure_ascii=False)[:600])
    ex = []
    for r in rows:
        print({k: r.get(k) for k in r if not isinstance(r.get(k), (list, dict))})
for p, v in find(d, "any_inplace_feasible"):
    print(p, v)
