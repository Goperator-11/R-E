import sys
sys.dont_write_bytecode = True
import argparse
import concurrent.futures
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import statistics


META = {"candidate_version", "k_source", "natural_k", "expected_k", "expected_scope"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def equal(actual, expected, label):
    if canonical(actual) != canonical(expected):
        raise ValueError(label + " differs")


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def checked_plan(path):
    p = read(path)
    equal(p["schema"], "padfec.v33.current_k_replay/1", "plan schema")
    for filename, digest in p["sources"].items():
        equal(sha(filename), digest, "source " + filename)
    equal(sha(p["protocol_path"]), p["protocol_sha256"], "protocol")
    equal(sha(p["contract_path"]), p["contract_sha256"], "contract")
    return p


def imported_candidate(plan):
    snapshot = Path(plan["snapshot_root"]).resolve()
    sys.path.insert(0, str(snapshot))
    from experiments.v33.current_k_candidate import CurrentKPolicy
    from experiments.v33.natural_k_reference import FirstHello, natural_k
    from padfec3 import learn3
    for name, module in sys.modules.items():
        if name.split(".")[0] in {"afec", "padfec", "padfec3", "experiments"}:
            filename = getattr(module, "__file__", None)
            if filename is not None:
                filename = str(Path(filename).resolve())
                if not Path(filename).is_relative_to(snapshot) or filename not in plan["sources"]:
                    raise ValueError("module outside selected snapshot: " + name)
                equal(sha(filename), plan["sources"][filename], "loaded module")
    return CurrentKPolicy, FirstHello, natural_k, learn3


def check_inputs(plan, job):
    for item in job["runs"]:
        equal(sha(item["result_path"]), item["result_sha256"], "result hash")
        run = read(item["result_path"])
        equal(sha(run["trace_path"]), run["trace_sha256"], "trace hash")
        for key, value in {"scenario": job["scenario"]["id"], "observation_mode": job["mode"],
                           "seed": item["seed"], "status": "complete", "mode": "full",
                           "protocol_sha256": plan["protocol_sha256"]}.items():
            equal(run[key], value, "run " + key)
        attempt = Path(item["result_path"]).parent / run["attempt_id"]
        started = Path(str(attempt) + ".started.json")
        equal(sha(started), run["started_receipt_sha256"], "started receipt")
        finished = read(Path(str(attempt) + ".finished.json"))
        equal(finished["result_digest"], hashlib.sha256(canonical(run).encode()).hexdigest(), "finished digest")
    equal([r["seed"] for r in job["runs"]], plan["seeds"], "seed inventory")


def replay_job(plan_path, job_id, out, smoke):
    plan = checked_plan(plan_path)
    job = plan["jobs"][job_id]
    check_inputs(plan, job)
    Policy, Hello, natural_k, learn = imported_candidate(plan)
    hello = Hello(**job["hello"])
    k = job["scenario"]["context"]["k"]
    equal({natural_k(hello, w) for w in range(1200, 1453)} == {k}, True, "width invariance")
    scenario = job["scenario"]
    width, u = scenario["context"]["w"], scenario["context"]["uplink_mbps"]
    results = []
    for item in job["runs"][:1] if smoke else job["runs"]:
        run = read(item["result_path"])
        policy = Policy()
        n = 0
        hct = []
        with gzip.open(run["trace_path"], "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if smoke and n == 4:
                    break
                if scenario["reset_each_connection"]:
                    policy = Policy()
                equal(row["index"], n, "connection index")
                equal(sorted(row["policy_decide_input"]), ["destination", "op", "rtt_ms"], "decision input boundary")
                got = policy.decide(hello, width, u, row["policy_decide_input"]["rtt_ms"], plan["c_pkt"])
                equal({a:b for a,b in got.items() if a not in META}, row["decision"], f"decision {n}")
                equal(got["expected_k"], k, "expected k")
                obs = row["policy_observe_input"]
                equal(got["action"], obs["action"], "observed action")
                equal(got["j3_pred_pre_ms"], obs["j_pred"], "predicted J")
                info = policy.observe(obs["hct_ms"], obs["ok"], obs["k_obs"], obs["srv_bytes"], obs["rtt_ms"],
                                      arrivals=obs["optional"]["first_flight_evidence"])
                equal({a:b for a,b in info.items() if a not in META}, row["observation_info"], f"observation {n}")
                n += 1
                hct.append(row["hct_ms"])
        if not smoke:
            equal(n, run["n"], "complete trace length")
            st = policy.state
            actual = {**learn.post_summary(learn.combined(st)), "S_hat": learn.s_hat(st), "k_hat": learn.k_hat(st),
                      "stats": st.stats, "guard_alarms": st.g_alarm, "n_dec": st.n_dec, "n_reeval": st.n_reeval}
            equal(actual, {a:run["final_state"][a] for a in actual}, "final policy state")
            equal(statistics.mean(hct), run["summary"]["mean_hct_ms"], "mean HCT recomputation")
        results.append({"seed": item["seed"], "n": n, "mean_hct_ms": statistics.mean(hct), "paired_hct_delta_ms": 0.0,
                        "decision_mismatches": 0, "observation_mismatches": 0,
                        "result_path": item["result_path"], "result_sha256": item["result_sha256"],
                        "trace_path": run["trace_path"], "trace_sha256": run["trace_sha256"]})
    checked_plan(plan_path)
    result = {"job": job_id, "scenario": scenario["id"], "mode": job["mode"], "smoke": smoke,
              "status": "pass", "runs": results, "plan_sha256": sha(plan_path)}
    write(out, result)
    return result


def launch_job(script, plan, index, folder, smoke):
    target = folder / f"job{index:03d}.json"
    args = [sys.executable, "-I", "-B", str(script), "--plan", str(plan), "--job", str(index), "--out", str(target)]
    if smoke:
        args.append("--smoke")
    with (folder / f"job{index:03d}.log").open("x", encoding="utf-8", newline="\n") as stream:
        proc = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    return {"job": index, "exit_code": proc.returncode, "result_path": str(target)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--job", type=int)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = checked_plan(args.plan)
    if args.job is not None:
        replay_job(args.plan, args.job, args.out, args.smoke)
        return
    if args.dry_run:
        Policy, Hello, natural_k, learn = imported_candidate(plan)
        for job in plan["jobs"]:
            check_inputs(plan, job)
            k = job["scenario"]["context"]["k"]
            equal(all(natural_k(Hello(**job["hello"]), w) == k for w in range(1200,1453)), True, "local k")
            for phase in job["scenario"]["phases"]:
                equal(phase.get("k", k), k, "phase k")
            for component in job["scenario"].get("mixture") or []:
                equal(component["context"].get("k", k), k, "mixture k")
        write(args.out, {"status": "pass", "jobs": len(plan["jobs"]), "runs": sum(len(j["runs"]) for j in plan["jobs"]), "plan_sha256": sha(args.plan)})
        return
    args.out.mkdir()
    started = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
    write(args.out / "started.json", {"started_kst": started, "plan_sha256": sha(args.plan), "smoke": args.smoke})
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=plan["workers"]) as executor:
        futures = [executor.submit(launch_job, Path(__file__), args.plan, i, args.out, args.smoke) for i in range(len(plan["jobs"]))]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    checked_plan(args.plan)
    write(args.out / "finished.json", {"started_kst": started, "ended_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
          "plan_sha256": sha(args.plan), "status": "pass" if all(r["exit_code"] == 0 for r in results) else "failed",
          "jobs": sorted(results, key=lambda x:x["job"])})
    if any(r["exit_code"] != 0 for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
