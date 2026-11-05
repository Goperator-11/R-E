import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sys.path.insert(0, str(ROOT))
from experiments.v33 import bench_learning_l3 as learning


read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
check = read(RUNS / "L3_core_check_04.json")
assert check["exit_code"] == 0 and check["unchanged"]
assert all(sha(path) == value for path, value in check["source_sha256"].items())
assert read(RUNS / "L3_collector_check_01.json")["exit_code"] == 0
configs = {
    "full": {"enabled": True, "beta": True, "shared": True, "c1_reeval": False},
    "guard_only": {"enabled": False, "beta": False, "shared": False, "c1_reeval": True},
    "record_only": {"enabled": True, "beta": False, "shared": False, "c1_reeval": False},
    "beta_only": {"enabled": True, "beta": True, "shared": False, "c1_reeval": False}}
keys = {"enabled": "ENABLED", "beta": "APPLY_BETA", "shared": "APPLY_SHARED", "c1_reeval": "C1_REEVAL"}
original = learning.inventory(ROOT)["files"]
assert len(original) == 20
outputs = []
for variant, config in configs.items():
    name = "L3_v1" if variant == "full" else "L3_" + variant + "_v1"
    origin = ROOT if variant == "full" else ROOT / "g3/v33/ablation_sources" / name
    if variant != "full":
        origin.mkdir(parents=True, exist_ok=False)
        for relative, value in original.items():
            raw = (ROOT / relative).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == value
            target = origin / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == "padfec3/monitor3.py":
                text = raw.decode("utf-8")
                for key, symbol in keys.items():
                    before = symbol + " = " + str(configs["full"][key]) + "\n"
                    after = symbol + " = " + str(config[key]) + "\n"
                    assert text.count(before) == 1
                    text = text.replace(before, after)
                raw = text.encode("utf-8")
            with target.open("xb") as stream:
                stream.write(raw)
    fingerprint = learning.inventory(origin)["files"]
    changed = [key for key in original if original[key] != fingerprint[key]]
    assert changed == ([] if variant == "full" else ["padfec3/monitor3.py"])
    snapshot = ROOT / "g3/v33/policy_snapshots" / name
    snapshot.mkdir(parents=True, exist_ok=False)
    for relative, value in fingerprint.items():
        raw = (origin / relative).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == value
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    receipt = {"schema": "padfec.v33.policy_snapshot/1", "source_root": str(origin), "snapshot_root": str(snapshot),
        "files": fingerprint, "source_and_snapshot_byte_identical": True, "monitor_variant": variant, "monitor_config": config,
        "created_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "origin_candidate_files": original,
        "changed_files_vs_full": changed, "script_sha256": sha(__file__)}
    path = RUNS / (name + "_snapshot_receipt.json")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    learning.snapshot_identity(snapshot, path, origin)
    outputs.append({"name": name, "snapshot": str(snapshot), "receipt_path": str(path), "receipt_sha256": sha(path), "config": config})
with (RUNS / "L3_snapshots_v1.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"outputs": outputs, "script_sha256": sha(__file__)}, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"snapshots": len(outputs), "files_each": len(original), "outputs": outputs}))
