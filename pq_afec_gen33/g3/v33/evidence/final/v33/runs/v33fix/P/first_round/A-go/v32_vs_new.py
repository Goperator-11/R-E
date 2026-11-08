import sys; sys.dont_write_bytecode = True; sys.stdout.reconfigure(encoding="utf-8")
import json
from pathlib import Path

base = Path(sys.argv[1])
NEW_ONLY_STATE = {"c1_seen", "arrival_streak"}
STATE_SKIP = {"v"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compare(old, new):
    out = {"trajectories": 0, "steps": 0, "step_mismatch": 0, "snapshots": 0, "snap_mismatch": 0,
           "state_fields": 0, "state_mismatch": 0, "decisions": 0, "decision_mismatch": 0,
           "stats_keys_new_only": set(), "first": []}
    for a, b in zip(old["decisions"], new["decisions"]):
        out["decisions"] += 1
        if a != b:
            out["decision_mismatch"] += 1
            if len(out["first"]) < 5:
                out["first"].append(("decision", a.get("id")))
    assert len(old["decisions"]) == len(new["decisions"])
    assert len(old["trajectories"]) == len(new["trajectories"])
    for ta, tb in zip(old["trajectories"], new["trajectories"]):
        out["trajectories"] += 1
        assert ta["id"] == tb["id"] and not ta.get("err") and not tb.get("err"), (ta.get("err"), tb.get("err"))
        sa, sb = ta["steps"], tb["steps"]
        assert set(sa) == set(sb)
        n = len(sa["a"])
        for i in range(n):
            out["steps"] += 1
            if any(sa[k][i] != sb[k][i] for k in sa):
                out["step_mismatch"] += 1
                if len(out["first"]) < 5:
                    out["first"].append((ta["id"], i, [k for k in sa if sa[k][i] != sb[k][i]]))
        for xa, xb in zip(ta["snapshots"], tb["snapshots"]):
            out["snapshots"] += 1
            if any(xa[k] != xb[k] for k in xa if k != "state"):
                out["snap_mismatch"] += 1
            ja, jb = xa["state"], xb["state"]
            assert set(jb) - set(ja) == NEW_ONLY_STATE, set(jb) ^ set(ja)
            for k in ja:
                if k in STATE_SKIP:
                    continue
                if k == "stats":
                    out["stats_keys_new_only"] |= set(jb["stats"]) - set(ja["stats"])
                    for sk in ja["stats"]:
                        out["state_fields"] += 1
                        if ja["stats"][sk] != jb["stats"][sk]:
                            out["state_mismatch"] += 1
                    continue
                out["state_fields"] += 1
                if ja[k] != jb[k]:
                    out["state_mismatch"] += 1
                    if len(out["first"]) < 5:
                        out["first"].append((ta["id"], xa["after_step"], k))
            if jb["c1_seen"] is not False or jb["arrival_streak"] != 0:
                out["state_mismatch"] += 1
            if jb["stats"]["binary"] != jb["stats"]["upd"] or jb["stats"]["arr_none"] != jb["stats"]["obs"]:
                out["state_mismatch"] += 1
    out["stats_keys_new_only"] = sorted(out["stats_keys_new_only"])
    return out


result = {}
for name in sys.argv[2:]:
    old = load(base / ("%s.v32.json" % name))
    new = load(base / ("%s.new.json" % name))
    result[name] = compare(old, new)
print(json.dumps(result, indent=1))
