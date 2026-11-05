import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path


ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
PACKAGES = ("afec", "padfec", "padfec3")
KST = dt.timezone(dt.timedelta(hours=9))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(root):
    found = {}
    for package in PACKAGES:
        assert (root / package / "__init__.py").is_file()
        for path in sorted((root / package).rglob("*.py")):
            assert not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
            found[path.relative_to(root).as_posix()] = sha(path)
    return found


def copy_tree(source, destination):
    assert not destination.exists()
    expected = inventory(source)
    for name, checksum in expected.items():
        path = source / name
        assert sha(path) == checksum
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(path.read_bytes())
    assert inventory(source) == inventory(destination) == expected
    return expected


def save(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def snapshot(source, name, mode):
    destination = ROOT / "g3/v33/policy_snapshots" / name
    files = copy_tree(source, destination)
    receipt = {"schema": "padfec.v33.policy_snapshot/1", "source_root": str(source),
               "snapshot_root": str(destination), "files": files,
               "source_and_snapshot_byte_identical": True, "epsilon_calibration": mode,
               "created_kst": dt.datetime.now(KST).isoformat(), "script_path": str(Path(__file__).resolve()),
               "script_sha256": sha(__file__), "state_version": 5,
               "inventory_scope": "all .py files in afec, padfec, padfec3; source bytes only"}
    save(destination / "snapshot_manifest.json", receipt)
    save(RUNS / (name + "_snapshot_receipt.json"), receipt)
    return receipt


def main():
    before = inventory(ROOT)
    text = (ROOT / "padfec3/learn3.py").read_text(encoding="utf-8")
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(text).body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in ("STATE_VERSION", "CLASS_EPS_A", "CLASS_EPS_B")}
    assert constants == {"STATE_VERSION": 5, "CLASS_EPS_A": 1.0, "CLASS_EPS_B": 999.0}
    main_receipt = snapshot(ROOT, "L2_v1", "adaptive")
    ablation = ROOT / "g3/v33/ablation_sources/L2_fixed_epsilon_v1"
    copy_tree(ROOT, ablation)
    old = "def epsilon_posterior(a, b, q):"
    assert text.count(old) == 1
    changed = text.replace(old, "def epsilon_posterior_adaptive(a, b, q):")
    anchor = "def check_epsilon_state(value):"
    assert changed.count(anchor) == 1
    wrapper = 'def epsilon_posterior(a, b, q):\n    _, _, rho, _ = epsilon_posterior_adaptive(a, b, q)\n    return float(a), float(b), rho, "fixed_epsilon_ablation"\n\n\n'
    changed = changed.replace(anchor, wrapper + anchor)
    compile(changed, str(ablation / "padfec3/learn3.py"), "exec")
    (ablation / "padfec3/learn3.py").write_text(changed, encoding="utf-8", newline="\n")
    fixed_inventory = inventory(ablation)
    assert [name for name in before if before[name] != fixed_inventory[name]] == ["padfec3/learn3.py"]
    receipt = {"schema": "padfec.v33.l2_fixed_epsilon_ablation/1", "original_files": before,
               "ablation_files": fixed_inventory, "only_changed_file": "padfec3/learn3.py",
               "method": "Rename the validated adaptive helper and wrap its result, preserving input a/b and rho; all other policy code and decision timing are unchanged.",
               "original_learning_sha256": before["padfec3/learn3.py"],
               "fixed_learning_sha256": fixed_inventory["padfec3/learn3.py"], "script_sha256": sha(__file__)}
    save(ablation / "ablation_manifest.json", receipt)
    save(RUNS / "L2_fixed_epsilon_v1_ablation.json", receipt)
    fixed_receipt = snapshot(ablation, "L2_fixed_epsilon_v1", "fixed_ablation")
    assert inventory(ROOT) == before
    print(json.dumps({"source_files": len(before), "snapshots": [main_receipt["snapshot_root"], fixed_receipt["snapshot_root"]],
                      "source_unchanged": True, "ablation_changes": [receipt["only_changed_file"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
