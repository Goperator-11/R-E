import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAL = ROOT / "g3" / "SEAL_m1confirm.json"
SEALED = ["g3/PROTOCOL_m1confirm.md", "g3/m1confirm_predictions.json",
          "experiments/g3_m1confirm.py", "experiments/g3_stage0.py",
          "experiments/g3bed.py", "experiments/padbed.py",
          "experiments/_journal.py", "experiments/blockstat.py"]
RECORDED = ["g3/seal_m1confirm.py", "tests/test_g3_m1confirm.py", "tests/test_g3_stage0.py",
            "g3/RESULT_stage0.md", "g3/stage0_predictions.json", "g3/SEAL_stage0.json",
            "g3/PROTOCOL_stage0.md"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(names):
    return {name: sha256(ROOT / name) for name in names}


def write():
    pred = json.load(open(ROOT / "g3" / "m1confirm_predictions.json", encoding="utf-8"))
    src = pred["copied_from"]
    if src["sha256"] != sha256(ROOT / src["path"]):
        raise SystemExit("m1confirm_predictions.json was not copied from the current %s"
                         % src["path"])
    data = {
        "schema": "padfec3.m1confirm_seal.v1",
        "sealed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": "PAD-FEC v3 M1 re-confirmation (g3/PROTOCOL_m1confirm.md)",
        "sha256": digest(SEALED),
        "also_recorded_sha256": digest(RECORDED),
        "predictions_copied_from": src,
        "check": "python -B g3/seal_m1confirm.py --check",
    }
    with open(SEAL, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps(data, indent=1))


def check():
    data = json.load(open(SEAL, encoding="utf-8"))
    bad = [name for name, h in data["sha256"].items() if sha256(ROOT / name) != h]
    drift = [name for name, h in data["also_recorded_sha256"].items() if sha256(ROOT / name) != h]
    print("sealed files changed:", bad or "none")
    print("recorded files changed:", drift or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(check())
    write()
