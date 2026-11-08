import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from padfec3 import decide3, learn3

TARGET = ROOT / "experiments" / "quicbed" / "policy3_explore_vectors_test.go"
C_PKT = 41.983
W = 1280
RTT = 50.0
EVENT_HCT = 313.0
BASE_HCT = 53.0

SCENARIOS = (
    {"name": "u0_c2955_loss_free", "k": 2, "u": 0.0, "s": 3840.0, "rate_ms": 0.05, "cap_ms": 100.0,
     "steps": 400},
    {"name": "u2_c2955_event", "k": 2, "u": 2.0, "s": 3840.0, "rate_ms": 0.05, "cap_ms": 100.0,
     "steps": 500, "events": (120, 121, 300)},
    {"name": "k1_c4032_loss_free", "k": 1, "u": 0.0, "s": 5000.0, "rate_ms": 0.05, "cap_ms": 100.0,
     "steps": 400},
    {"name": "bigcert_gate_closed", "k": 2, "u": 2.0, "s": 20000.0, "rate_ms": 0.05, "cap_ms": 100.0,
     "steps": 200, "events": (50,)},
    {"name": "cap_and_failure_debit", "k": 2, "u": 2.0, "s": 3840.0, "rate_ms": 7.5, "cap_ms": 30.0,
     "steps": 120, "failures": (40, 90)},
    {"name": "excess_below_event", "k": 2, "u": 0.0, "s": 3840.0, "rate_ms": 5.0, "cap_ms": 100.0,
     "steps": 120, "slow_every": 7, "slow_ms": 10.0},
    {"name": "guard_alarm_on_explored_arm", "k": 2, "u": 0.0, "s": 3840.0, "rate_ms": 10.0, "cap_ms": 100.0,
     "steps": 160, "failures": (1,), "explore_slow_ms": 40.0},
    {"name": "c1_entry_clears_pending", "k": 2, "u": 0.0, "s": 3840.0, "rate_ms": 5.0, "cap_ms": 100.0,
     "steps": 80, "c1_from": 50},
)


def _hct(scenario, index, why):
    if index in scenario.get("events", ()):
        return EVENT_HCT
    hct = BASE_HCT
    every = scenario.get("slow_every", 0)
    if every and index % every == every - 1:
        hct += scenario["slow_ms"]
    if why == "explore":
        hct += scenario.get("explore_slow_ms", 0.0)
    return hct


def vector_case(scenario):
    k, u, s = scenario["k"], scenario["u"], scenario["s"]
    explore = {"rate_ms": scenario["rate_ms"], "cap_ms": scenario["cap_ms"]}
    failures = set(scenario.get("failures", ()))
    c1_from = scenario.get("c1_from", scenario["steps"])
    st = learn3.new_state()
    runs = []
    for index in range(scenario["steps"]):
        dec = decide3.decide3(st, W, u, RTT, C_PKT, explore=explore)
        action = tuple(dec["action"])
        ok = index not in failures
        c1 = index >= c1_from
        hct = _hct(scenario, index, dec["why"]) if ok else None
        extra = {}
        if c1:
            extra["arrivals"] = {"src": "c1", "sent": k, "lost": 0, "bitmap": [1] * k, "trunc": False}
        learn3.observe3(st, action, hct, ok, k, s, RTT, W=W, u_mbps=u, c_pkt=C_PKT,
                        j_pred=dec.get("j3_pred_pre_ms"), **extra)
        head = {"a": list(action), "why": dec["why"], "hct": hct, "ok": ok, "c1": c1}
        if runs and all(runs[-1][key] == value for key, value in head.items()):
            runs[-1]["n"] += 1
        else:
            runs.append({**head, "n": 1})
        runs[-1]["ledger"] = st.x_ledger
        runs[-1]["pending"] = None if st.x_ledger is None else st.x_pending
        runs[-1]["alarms"] = sorted(st.g_alarm)
    return {"name": scenario["name"], "k": k, "w": W, "u": u, "rtt": RTT, "s": s, "c_pkt": C_PKT,
            "rate_ms": scenario["rate_ms"], "cap_ms": scenario["cap_ms"], "runs": runs}


def _step(st, explore, hct=BASE_HCT):
    dec = decide3.decide3(st, W, 0.0, RTT, C_PKT, explore=explore)
    action = tuple(dec["action"])
    learn3.observe3(st, action, hct, True, 2, 3840.0, RTT, W=W, u_mbps=0.0, c_pkt=C_PKT,
                    j_pred=dec.get("j3_pred_pre_ms"))
    return dec


def python_states():
    explore = {"rate_ms": 0.05, "cap_ms": 100.0}
    st = learn3.new_state()
    for _ in range(30):
        _step(st, explore)
    if st.x_pending is not False or st.x_ledger is None:
        raise RuntimeError("state after observations must carry x_ledger with x_pending false")
    states = {"pending_false": st.to_json()}
    dec = decide3.decide3(st, W, 0.0, RTT, C_PKT, explore=explore)
    if dec["why"] != "explore" or st.x_pending is not True:
        raise RuntimeError("explore decision must leave x_pending true")
    states["pending_true"] = st.to_json()
    return states


def _compact(value):
    text = json.dumps(value, separators=(",", ":"), allow_nan=False)
    if "`" in text:
        raise ValueError("vector JSON must not contain a backtick")
    return text


def _check_coverage(cases):
    runs = [run for case in cases for run in case["runs"]]
    needed = {
        "cap": any(run["ledger"] == case["cap_ms"] for case in cases for run in case["runs"]),
        "failure": any(not run["ok"] and run["ledger"] is not None for run in runs),
        "alarm": any(run["alarms"] for run in runs),
        "c1": any(run["c1"] for run in runs),
        "explore": any(run["why"] == "explore" for run in runs),
    }
    missing = sorted(key for key, value in needed.items() if not value)
    if missing:
        raise RuntimeError("vectors do not cover: " + ", ".join(missing))


def render():
    cases = [vector_case(scenario) for scenario in SCENARIOS]
    _check_coverage(cases)
    vectors = "[\n" + ",\n".join(_compact(case) for case in cases) + "\n]"
    return ("package main\n\n"
            "const cx1VectorJSON = `" + vectors + "`\n\n"
            "const cx1PythonStatesJSON = `" + _compact(python_states()) + "`\n")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else None
        if current != text:
            print("stale: " + TARGET.relative_to(ROOT).as_posix())
            return 1
        print("current: " + TARGET.relative_to(ROOT).as_posix())
        return 0
    TARGET.write_bytes(text.encode("utf-8"))
    print("wrote " + TARGET.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
