import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAL = ROOT / "g3" / "SEAL_stage0.json"
SEALED = ["g3/stage0_predictions.json", "g3/PROTOCOL_stage0.md", "padfec3/layout.py"]
RECORDED = ["g3/stage0_predict.py", "tests/test_padfec3_layout.py", "padfec3/__init__.py",
            "padfec/policy.py", "padfec/quantum.py", "afec/channel.py"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(names):
    return {name: sha256(ROOT / name) for name in names}


def write():
    pred = json.load(open(ROOT / "g3" / "stage0_predictions.json", encoding="utf-8"))
    if pred["model"]["sha256"] != sha256(ROOT / "padfec3" / "layout.py"):
        raise SystemExit("stage0_predictions.json was not generated from the current padfec3/layout.py")
    data = {
        "schema": "padfec3.stage0_seal.v1",
        "sealed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stage": "PAD-FEC v3 stage 0 (verdict_v3.md section 4.2)",
        "sha256": digest(SEALED),
        "also_recorded_sha256": digest(RECORDED),
        "predictions_generated_utc": pred["generated_utc"],
        "check": "python -B g3/seal_stage0.py --check",
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
