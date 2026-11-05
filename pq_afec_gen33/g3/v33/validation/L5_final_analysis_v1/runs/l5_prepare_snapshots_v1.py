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
        "files": inventory(dest), "source_and_snapshot_byte_identical": True, "size_variant": variant,
        "created_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "state_version": 9,
        "script_path": str(Path(__file__).resolve()), "script_sha256": sha(__file__)}
    save(dest / "snapshot_manifest.json", value)
    save(RUNS / (name + "_snapshot_receipt.json"), value)

assert not (RUNS.parent / "state/MEASURE_LOCK.json").exists()
checked = {}
for label in ("L5_core_01", "L5_collector_02"):
    check = json.loads((RUNS / (label + ".json")).read_text(encoding="utf-8"))
    assert check["exit_code"] == 0 and check["unchanged"]
    checked.update(check["source_sha256"])
for path, expected in checked.items():
    assert sha(path) == expected, path
before = inventory(ROOT)
snapshot(ROOT, "L5_v1", "full")
ablation = ROOT / "g3/v33/ablation_sources/L5_single_v1"
copy(ROOT, ablation)
path = ablation / "padfec3/learn3.py"
content = path.read_text(encoding="utf-8")
assert content.count('SIZE_MODE = "full"\n') == 1
content = content.replace('SIZE_MODE = "full"\n', 'SIZE_MODE = "single"\n')
compile(content, str(path), "exec")
path.write_text(content, encoding="utf-8", newline="\n")
assert [name for name in before if before[name] != inventory(ablation)[name]] == ["padfec3/learn3.py"]
save(ablation / "ablation_manifest.json", {"original_files": before, "ablation_files": inventory(ablation),
    "scope": "Identical completed response observation, physical budget and conditional likelihood. Single median-neighbor sample without change resets or mixture decisions."})
snapshot(ablation, "L5_single_v1", "single")
assert inventory(ROOT) == before
print(json.dumps({"status": "pass", "files_per_snapshot": len(before), "snapshots": ["L5_v1", "L5_single_v1"]}))
