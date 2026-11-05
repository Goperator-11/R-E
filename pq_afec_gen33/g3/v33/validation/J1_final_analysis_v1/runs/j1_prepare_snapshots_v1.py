import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p) for package in ("afec", "padfec", "padfec3")
            for p in sorted((root / package).rglob("*.py"))}

def copy(source, destination):
    assert not destination.exists()
    expected = inventory(source)
    for name, checksum in expected.items():
        path = source / name
        assert not path.is_symlink() and sha(path) == checksum
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(path.read_bytes())
    assert expected == inventory(source) == inventory(destination)

def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

def snapshot(source, name, variant):
    dest = ROOT / "g3/v33/policy_snapshots" / name
    copy(source, dest)
    value = {"schema": "padfec.v33.policy_snapshot/1", "source_root": str(source), "snapshot_root": str(dest),
        "files": inventory(dest), "source_and_snapshot_byte_identical": True, "tail_variant": variant,
        "created_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "state_version": 7,
        "script_path": str(Path(__file__).resolve()), "script_sha256": sha(__file__)}
    save(dest / "snapshot_manifest.json", value)
    save(RUNS / (name + "_snapshot_receipt.json"), value)

check = json.loads((RUNS / "J1_check_02.json").read_text(encoding="utf-8"))
assert check["exit_code"] == 0 and check["unchanged"]
for path, expected in check["source_sha256"].items():
    assert sha(path) == expected
before = inventory(ROOT)
snapshot(ROOT, "J1_v1", "full")
ablation = ROOT / "g3/v33/ablation_sources/J1_cost_only_v1"
copy(ROOT, ablation)
path = ablation / "padfec3/learn3.py"
text = path.read_text(encoding="utf-8")
assert text.count('             ev["class_probabilities"])') == 1
assert text.count('        return class_probabilities(ctx, action, g, later)[2]') == 1
text = text.replace('             ev["class_probabilities"])', '             (ev["p_one_rtt"], ev["p_two_rtt"], ev["p_fail"]))')
text = text.replace('        return class_probabilities(ctx, action, g, later)[2]', '        return pf')
compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8", newline="\n")
assert [name for name in before if before[name] != inventory(ablation)[name]] == ["padfec3/learn3.py"]
save(ablation / "ablation_manifest.json", {"original_files": before, "ablation_files": inventory(ablation),
    "scope": "Cost correction retained; learning class partition and nominal-two event probability restored to L1; state7 retained for isolated diagnostic."})
snapshot(ablation, "J1_cost_only_v1", "cost_only")
assert inventory(ROOT) == before
print(json.dumps({"status": "pass", "files_per_snapshot": len(before), "snapshots": ["J1_v1", "J1_cost_only_v1"]}))
