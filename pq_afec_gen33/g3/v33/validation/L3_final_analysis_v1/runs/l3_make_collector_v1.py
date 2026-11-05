import sys
sys.dont_write_bytecode = True
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
source = ROOT / "experiments/v33/bench_learning_l2.py"
target = ROOT / "experiments/v33/bench_learning_l3.py"
assert not target.exists()
text = source.read_text(encoding="utf-8")
text = text.replace('learning_benchmark/2', 'learning_benchmark/3').replace('learning_raw/2', 'learning_raw/3').replace('learning_import/2', 'learning_import/3')
text = text.replace('bench_learning_l2.py', 'bench_learning_l3.py')
text = text.replace('    if receipt.get("epsilon_calibration") not in ("adaptive", "fixed_ablation"):\n        raise ValueError("L2 snapshot must declare epsilon calibration mode")', '''    variants = {
        "full": {"enabled": True, "beta": True, "shared": True, "c1_reeval": False},
        "guard_only": {"enabled": False, "beta": False, "shared": False, "c1_reeval": True},
        "record_only": {"enabled": True, "beta": False, "shared": False, "c1_reeval": False},
        "beta_only": {"enabled": True, "beta": True, "shared": False, "c1_reeval": False}}
    if receipt.get("monitor_variant") not in variants:
        raise ValueError("L3 snapshot must declare monitor variant")
    equal(receipt.get("monitor_config"), variants[receipt["monitor_variant"]], "monitor variant configuration")''')
text = text.replace('"state_version": 5,\n            "epsilon_calibration": receipt["epsilon_calibration"]}', '"state_version": 6,\n            "monitor_variant": receipt["monitor_variant"], "monitor_config": receipt["monitor_config"]}')
start = text.index('def validate_epsilon_row(')
end = text.index('\ndef validate_run(', start)
replacement = '''def close_value(actual, expected, name):
    if isinstance(expected, float):
        if isinstance(actual, bool) or not isinstance(actual, (float, int)) or not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-12):
            raise ValueError(name + " differs")
    elif isinstance(expected, dict):
        equal(set(actual), set(expected), name + " fields")
        for key, value in expected.items():
            close_value(actual[key], value, name + ":" + key)
    elif isinstance(expected, list):
        equal(len(actual), len(expected), name + " length")
        for index, value in enumerate(expected):
            close_value(actual[index], value, name + ":" + str(index))
    else:
        equal(actual, expected, name)


def monitor_fit_score(window, beta):
    total = -4.0 * beta
    for raw, outcome in window:
        q = min(1 - 1e-6, max(1e-6, raw))
        odds = math.exp(beta)
        total += outcome - q * odds / (1 - q + q * odds)
    return total


def validate_beta_fit(window, value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not -math.log(4) <= value <= math.log(4):
        raise ValueError("invalid monitor beta")
    score = monitor_fit_score(window, value)
    if value == -math.log(4):
        valid = score <= 1e-7
    elif value == math.log(4):
        valid = score >= -1e-7
    else:
        valid = abs(score) <= 1e-7
    if not valid:
        raise ValueError("monitor fit does not satisfy constrained score equation")


def validate_monitor_row(row, previous, config, obs_index):
    state = {"arrival_streak": 0, "monitor": {"v": 1, "arms": {}, "shared_at": 0, "shared_count": 0}} if previous is None else previous
    snapshot = row["decision"]["monitor_prediction"]
    info = row["observation_info"]
    equal(info["monitor_prediction"], snapshot, "consumed monitor snapshot")
    equal(snapshot["v"], 1, "monitor snapshot version")
    for field in ("v", "dec_index", "obs_index"):
        if type(snapshot[field]) is not int:
            raise ValueError("monitor indices must be integers")
    equal(snapshot["dec_index"], obs_index + 1, "monitor decision sequence")
    equal(snapshot["dec_index"], row["decision"]["dec_index"], "monitor decision counter")
    equal(snapshot["obs_index"], obs_index, "monitor observation counter")
    equal(snapshot["action"], row["action"], "monitor final action")
    equal(snapshot["ready"], state["arrival_streak"] >= 8, "monitor prior readiness")
    equal(row["decision"]["monitor_mode"], {key: config[key] for key in ("enabled", "beta", "shared")}, "monitor runtime mode")
    equal(row["decision"]["reeval_feedback_suppressed"], state["arrival_streak"] > 0 and not config["c1_reeval"], "feedback exploration mode")
    evidence = row["policy_observe_input"]["optional"]["first_flight_evidence"]
    usable = evidence["src"] != "none" and not evidence["trunc"] and evidence["sent"] > 0
    equal(info["arrival_usable"], usable, "complete first-flight evidence")
    state["arrival_streak"] = min(8, state["arrival_streak"] + 1) if usable else 0
    equal(info["arrival_streak_after"], state["arrival_streak"], "feedback history")
    equal(info["epsilon_before"], .001, "fixed L1 epsilon")
    equal(info["epsilon_after"], .001, "fixed L1 epsilon after")
    equal(info["epsilon_update_eligible"], False, "L2 EPS is not enabled")
    equal(info["cutoff_rtt_source"], "observation_rtt_current_policy", "L1 loss label timing")
    key = ",".join(str(value) for value in row["action"])
    old = state["monitor"]["arms"].get(key)
    beta = 0.0 if old is None else old["beta"]
    close_value(snapshot["beta"], beta, "monitor beta before observation")
    ctx = snapshot["ctx"]
    if ctx is not None:
        equal(ctx["rtt"], row["policy_decide_input"]["rtt_ms"], "monitor decision RTT")
        q = snapshot["q_raw"]
        if len(q) != 3 or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1 for value in q):
            raise ValueError("invalid predictive class mass")
        close_value(sum(q), 1.0, "predictive mass sum")
        event = min(1.0, sum(q[1:]))
        adjusted = list(q)
        if beta != 0 and event not in (0, 1):
            tilted = event * math.exp(beta) / (1 - event + event * math.exp(beta))
            adjusted = [1 - tilted, q[1] * tilted / event, q[2] * tilted / event]
        close_value(snapshot["q_used"], adjusted, "monitor corrected probabilities")
    else:
        equal([snapshot[k] for k in ("q_raw", "q_used", "cutoffs")], [None, None, None], "cold snapshot")
    expected_reason = "disabled" if not config["enabled"] else "no_ctx" if ctx is None else None
    equal(info["monitor_reason"], expected_reason, "monitor eligibility reason")
    if expected_reason is not None:
        equal(info["monitor"], None, "no monitor update")
        equal(info["raised"], [], "no monitor alarm")
        return state
    grade = 2 if not row["ok"] else 0 if row["hct_ms"] < snapshot["cutoffs"][0] else 1 if row["hct_ms"] < snapshot["cutoffs"][1] else 2
    equal(info["monitor_grade"], grade, "monitor grade from decision boundary")
    z = int(grade != 0)
    result = info["monitor"]
    raw, used = min(1.0, sum(snapshot["q_raw"][1:])), min(1.0, sum(snapshot["q_used"][1:]))
    q = min(1 - 1e-6, max(1e-6, used))
    close_value([result[k] for k in ("q_raw", "q_used", "q_clamped")], [raw, used, q], "monitor used probabilities")
    equal(result["z"], z, "monitor event")
    reactive = snapshot["ready"] and usable
    equal(result["reactive"], reactive, "monitor reaction readiness")
    old = {"up": 0.0, "down": 0.0, "beta": 0.0, "n": 0, "last_seen": 0, "window": [],
           "alarm_at": 0, "alarm_dir": 0, "beta_before": 0.0, "reactive_alarm": False} if old is None else old
    before = old["beta"]
    close_value(result["beta_before"], before, "monitor previous beta")
    up = max(0.0, old["up"] + z * math.log(2) - math.log(1 + q))
    down = max(0.0, old["down"] + z * math.log(.5) - math.log(1 - .5 * q))
    direction = 1 if up >= 5 else -1 if down >= 5 else 0
    equal(result["direction"], direction, "monitor likelihood-ratio alarm")
    old.update(up=0.0 if direction else up, down=0.0 if direction else down, n=old["n"] + 1, last_seen=obs_index + 1,
               window=(old["window"] + [[raw, z]])[-32:])
    expected_action = "record"
    if direction:
        old.update(alarm_at=obs_index + 1, alarm_dir=direction, beta_before=before, reactive_alarm=reactive)
        if reactive and config["beta"]:
            expected_action = "action_model"
    state["monitor"]["arms"][key] = old
    active = {name: value for name, value in state["monitor"]["arms"].items() if obs_index + 1 - value["last_seen"] < 32}
    shared = bool(direction and reactive and config["shared"] and len(active) >= 2 and all(
        value["reactive_alarm"] and value["alarm_dir"] == direction and state["monitor"]["shared_at"] < value["alarm_at"]
        and obs_index + 1 - value["alarm_at"] < 32 for value in active.values()))
    equal(result["shared"], shared, "monitor common change eligibility")
    equal(result["shared_actions"], sorted(active) if shared else [], "monitor common action set")
    if shared:
        for value in active.values():
            value.update(beta=value["beta_before"], up=0.0, down=0.0, reactive_alarm=False)
        state["monitor"]["shared_at"] = obs_index + 1
        state["monitor"]["shared_count"] += 1
        expected_action = "shared_change"
        close_value(result["beta_after"], old["beta"], "common change cancels action correction")
    elif expected_action == "action_model":
        validate_beta_fit(old["window"], result["beta_after"])
        old["beta"] = result["beta_after"]
    elif not direction and reactive and config["beta"] and ((before > 0 and old["up"] == 0) or (before < 0 and old["down"] == 0)):
        after = result["beta_after"]
        if not min(0, before) <= after <= max(0, before):
            raise ValueError("recovery increased or reversed beta")
        if after == 0:
            if monitor_fit_score(old["window"], 0.0) * before > 1e-7:
                raise ValueError("unjustified beta recovery to zero")
        elif after == before:
            if monitor_fit_score(old["window"], before) * before < -1e-7:
                raise ValueError("missing beta recovery")
        else:
            validate_beta_fit(old["window"], after)
        if after != before:
            old["beta"] = after
            expected_action = "recovery"
    else:
        close_value(result["beta_after"], before, "beta unchanged without reaction")
    equal(result["action"], expected_action, "monitor response kind")
    close_value([result["up"], result["down"]], [old["up"], old["down"]], "monitor cumulative state")
    equal(result["observations"], old["n"], "monitor action observation count")
    equal(info["raised"], [key] if direction else [], "new episode list")
    return state

'''
text = text[:start] + replacement + text[end:]
text = text.replace('epsilon_previous', 'monitor_previous')
text = text.replace('validate_epsilon_row(row, monitor_previous, overlay["policy"]["epsilon_calibration"],', 'validate_monitor_row(row, monitor_previous, overlay["policy"]["monitor_config"],')
old_final = '''        equal(final["v"], 5, "L2 final state version")
        equal(final["class_pending"], None, "L2 final snapshot consumed")
        if monitor_previous is not None:
            equal([final["class_epsilon"]["a"], final["class_epsilon"]["b"]], monitor_previous, "L2 final epsilon")'''
assert old_final in text
text = text.replace(old_final, '''        equal(final["v"], 6, "L3 final state version")
        equal(final["monitor_pending"], None, "L3 final snapshot consumed")
        if monitor_previous is not None:
            equal(final["arrival_streak"], monitor_previous["arrival_streak"], "L3 final feedback readiness")
            close_value(final["monitor"], monitor_previous["monitor"], "L3 final monitor state")''')
assert 'epsilon_calibration' not in text and 'validate_epsilon_row' not in text
compile(text, str(target), "exec")
with target.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
print(str(target))
