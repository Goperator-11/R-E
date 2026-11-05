import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
from experiments.v33 import bench, bench_learning_l2 as learning


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


result_path = RUNS / "L2_snapshot_smoke_check.json"
assert not result_path.exists()
results = []
for name, mode in (("L2_v1", "adaptive"), ("L2_fixed_epsilon_v1", "fixed_ablation")):
    receipt_path = RUNS / (name + "_snapshot_receipt.json")
    receipt = learning.read_json(receipt_path)
    identity = learning.snapshot_identity(receipt["snapshot_root"], receipt_path, receipt["source_root"])
    worker = bench.PolicyWorker(Path(receipt["snapshot_root"]), {"context": {"w": 1280, "uplink_mbps": 2.0}},
                                {"c_pkt": 41.983}, "full", RUNS / (name + "_worker_smoke.stderr.txt"))
    rows = []
    try:
        learning.validate_initial(worker.initial, identity)
        previous = None
        for i, (hct, ok) in enumerate(((80, True), (140, True), (None, False))):
            decision = worker.request({"op": "decide", "rtt_ms": 50})["decision"]
            action = decision["action"]
            sent = 2 + action[1] + action[2]
            info = worker.request({"op": "observe", "action": action, "hct_ms": hct, "ok": ok,
                                   "k_obs": 2, "srv_bytes": 18232, "rtt_ms": 45,
                                   "j_pred": decision["j3_pred_pre_ms"], "optional": {"first_flight_evidence":
                                   {"src": "c1", "sent": sent, "lost": 1, "bitmap": None, "trunc": False}}})["observation"]
            row = {"decision": decision, "action": action, "observation_info": info,
                   "policy_decide_input": {"rtt_ms": 50}, "hct_ms": hct, "ok": ok}
            previous = learning.validate_epsilon_row(row, previous, mode, i)
            rows.append(row)
        snapshot = worker.request({"op": "snapshot"})
        learning.validate_audit(snapshot["audit"], identity["fingerprint"])
        assert snapshot["serialized"]["class_epsilon"]["updates"] == 2
        assert snapshot["serialized"]["class_epsilon"]["skips"] == {"no_ctx": 1}
        assert snapshot["serialized"]["class_pending"] is None
        assert (previous == [1., 999.]) == (mode == "fixed_ablation")
        results.append({"name": name, "identity": identity, "rows": rows, "final": snapshot["serialized"],
                        "audit": snapshot["audit"]})
    finally:
        worker.close()
assert results[0]["final"]["post"] == results[1]["final"]["post"]
assert results[0]["final"]["w"] == results[1]["final"]["w"]
result = {"status": "pass", "scope": "synthetic isolated-worker exchange, not world performance",
          "script_sha256": sha(__file__), "collector_sha256": sha(learning.__file__), "results": results}
with result_path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({"status": "pass", "snapshots": len(results), "observations": 6,
                  "c1_loss_posteriors_identical": True, "result_sha256": sha(result_path)}))
