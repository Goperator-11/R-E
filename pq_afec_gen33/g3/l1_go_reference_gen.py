import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from padfec3 import learn3, decide3
from experiments.replay_g3 import RttTrack


def evidence(i):
    return [None,
            dict(src="c1", sent=4, lost=1, bitmap=[1, 0, 1, 1], trunc=False),
            dict(src="ack", sent=8, lost=3, bitmap=None, trunc=False),
            dict(src="c1", sent=4, lost=1, bitmap=[0, 1], trunc=True),
            dict(src="ack", sent=0, lost=0, bitmap=[], trunc=False),
            dict(src="none", sent=3, lost=1, bitmap=[0, 1, 1], trunc=False),
            dict(src="c1", sent=2, lost=2, bitmap=[0, 0], trunc=False),
            dict(src="ack", sent=3, lost=0, bitmap=[1, 1], trunc=True),
            dict(src="c1", sent=8, lost=0, bitmap=None, trunc=False)][i % 9]


def output_info(info):
    return {key: info[key] for key in (
        "y", "baseline", "ref", "updated", "shielded", "skip", "resid",
        "alarmed", "raised", "common", "n_alarm", "loss_evidence_src",
        "arrival_sent", "arrival_lost", "arrival_trunc", "arrival_bitmap",
        "grade", "grade_name", "grade_valid", "grade_reason", "cut1_ms", "cut2_ms",
        "cutoff_rtt_ms", "cutoff_rtt_source", "c_proc_used_ms", "margin1_ms",
        "margin2_ms", "epsilon_before", "epsilon_after", "epsilon_update_eligible",
        "legacy_y", "legacy_skip_reason", "legacy_shielded", "arrival_usable",
        "arrival_reject_reason", "loss_update_kind")}


def decision(d):
    return {key: d[key] for key in ("action", "why", "ej", "p_mean", "reeval")}


def initial(name):
    st = learn3.new_state()
    if name not in ("cold", "no_rtt"):
        st.k_hist = [2] * 16
        st.S_hist = [30000.0 if name == "nominal" else 8500.0] * 16
        st.hct = {"0,0,0": [100.0] * 32}
        st.hct_seq = {"0,0,0": 0}
        st.seq = 1
    if name == "guard":
        st.g_resid = {"0,2,2": [140.0] * 16}
        st.g_common = [0.0] * 64
        st.g_alarm = {"0,2,2": 0}
    return st


def observations():
    result = []
    actions = [(0, 0, 0), (0, 2, 2), (16, 1, 0), (0, 4, 0), (0, 0, 4)]
    for name in ("cold", "hot", "rtt200", "nominal", "no_rtt", "guard"):
        st = initial(name)
        case = dict(id=name, initial=st.to_json(), rows=[])
        for i in range(72):
            rtt = 0.0 if name == "no_rtt" else 200.0 if name in ("rtt200", "nominal") else 50.0
            a = actions[i % len(actions)]
            ctx = learn3.context(st, 1280, 2.0, rtt, 41.983)
            cuts = learn3.grade_cutoffs(ctx, a) if ctx else (80.0, 150.0)
            hct = [math.nextafter(cuts[0], 0.0), cuts[0], math.nextafter(cuts[0], math.inf),
                   math.nextafter(cuts[1], 0.0), cuts[1], math.nextafter(cuts[1], math.inf)][i % 6]
            row = dict(a=a, hct=None if i % 11 == 0 else hct, ok=i % 11 != 0,
                       k=2 if i % 17 else 5, srv=8500.0, rtt=rtt,
                       w=1280, u=2.0, c_pkt=41.983, j_pred=None if i % 3 else 80.0,
                       arrivals=evidence(i))
            info = learn3.observe3(st, a, row["hct"], row["ok"], row["k"], row["srv"], rtt,
                                  W=1280, u_mbps=2.0, c_pkt=41.983,
                                  j_pred=row["j_pred"], arrivals=row["arrivals"])
            row.update(info=output_info(info), state=st.to_json())
            st = learn3.DestState3.from_json(json.loads(json.dumps(st.to_json())))
            case["rows"].append(row)
        result.append(case)
    return result


def caches():
    cases = []
    for name in ("proxy", "ack_later", "ack_first"):
        st = learn3.new_state()
        rt = RttTrack()
        rows = []
        for i in range(96):
            d = decide3.decide3(st, 1280, 2.0, rt.rtt(), 41.983)
            valid = name == "ack_first" or (name == "ack_later" and i >= 7)
            ok = i % 13 != 0
            hct = 80.0 + (i % 5) * 60.0
            path_rtt = [70.0, 50.0, 60.0, 40.0][i % 4]
            row = dict(a=d["action"], hct=hct if ok else None, ok=ok, k=2,
                       srv=8500.0, path_rtt=path_rtt, path_valid=valid,
                       w=1280, u=2.0, c_pkt=41.983, j_pred=d["ej"], arrivals=evidence(i))
            rt.observe(dict(path_rtt_valid=valid, path_rtt_ms=path_rtt, ok=ok, ms=hct))
            info = learn3.observe3(st, d["action"], row["hct"], ok, 2, 8500.0, rt.rtt(),
                                  W=1280, u_mbps=2.0, c_pkt=41.983,
                                  j_pred=d["ej"], arrivals=row["arrivals"])
            entry = dict(state=st.to_json(), min_rtt_ms=rt.min_rtt,
                         rtt_observations=rt.rtt_obs, min_hct_ms=rt.min_hct, conns=i + 1)
            row.update(decision=decision(d), info=output_info(info), entry=entry,
                       p_after=learn3.post_mean(learn3.combined(st)))
            st = learn3.DestState3.from_json(json.loads(json.dumps(st.to_json())))
            rows.append(row)
        cases.append(dict(id=name, rows=rows))
    return cases


def main():
    dest = Path(sys.argv[1])
    if dest.exists():
        raise FileExistsError(dest)
    arrivals = [dict(sent=s, lost=l, likelihood=learn3.arrival_likelihood(s, l))
                for s in range(1, 9) for l in range(s + 1)]
    classes = []
    actions = [(d, lead, m - lead) for d in (0, 16) for m in range(5) for lead in range(m + 1)]
    for k, u, rtt, n, a in itertools.product((1, 2, 4), (0.0, 2.0), (50.0, 200.0), (1, 7, 20), actions):
        ctx = dict(k=k, W=1280, u=u, rtt=rtt, n_need=n, S=8500.0)
        cuts = learn3.grade_cutoffs(ctx, a)
        hs = [x for cut in cuts for x in (math.nextafter(cut, 0.0), cut, math.nextafter(cut, math.inf))]
        classes.append(dict(ctx=ctx, a=a, cuts=cuts, hct=hs,
                            grades=[learn3.classify_hct(ctx, a, h, True) for h in hs],
                            probabilities=[learn3.class_probabilities(ctx, a, g) for g in range(26)],
                            likelihood=[learn3.class_likelihood(ctx, a, grade) for grade in range(3)]))
    base = dict(src="c1", sent=2, lost=1, bitmap=[1, 0], trunc=False)
    invalid = [[], {}, {**base, "extra": 0}]
    for key, values in {"src": [None, 3, "bad"], "sent": [None, True, 1.5, -1, 9],
                        "lost": [None, False, 1.2, -1, 3], "trunc": [None, 0, 1, "false"],
                        "bitmap": [[True, 0], [2, 0], [1], [1, 1], [1, 0, 1], "10"]}.items():
        invalid.extend({**base, key: value} for value in values)
    for key in base:
        invalid.append({k: v for k, v in base.items() if k != key})
    for value in invalid:
        st = initial("hot")
        before = st.to_json()
        try:
            learn3.observe3(st, (0, 0, 0), 80.0, True, 2, 8500.0, 50.0,
                           W=1280, u_mbps=2.0, c_pkt=41.983, arrivals=value)
        except (ValueError, TypeError):
            assert before == st.to_json()
        else:
            raise AssertionError(value)
    doc = dict(schema="padfec3.l1_go_reference/1", arrivals=arrivals, classes=classes,
               observations=observations(), caches=caches(), invalid_arrivals=invalid)
    sources = ["g3/l1_go_reference_gen.py", "experiments/replay_g3.py",
               "padfec3/learn3.py", "padfec3/decide3.py", "padfec3/layout.py",
               "padfec/policy.py", "padfec/quantum.py", "padfec/table.py"]
    doc["sources"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    receipt = dict(path=str(dest), sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                   arrivals=len(arrivals), classes=len(classes), observations=432, cache_steps=288,
                   invalid_arrivals=len(invalid), sources=doc["sources"])
    dest.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
