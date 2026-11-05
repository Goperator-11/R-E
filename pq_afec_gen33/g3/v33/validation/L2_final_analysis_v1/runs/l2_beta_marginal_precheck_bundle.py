import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path


BASE = Path(r"C:\dev\codex_handoff\v33")
ROOT = Path(r"C:\dev\pq_afec_gen33")
OUT = ROOT / "g3/v33/validation/L2_beta_marginal_precheck"
NAMES = ["l2_beta_marginal_precheck_bundle.py", "l2_beta_marginal_precheck.py", "L2_beta_marginal_precheck.json", "L2_beta_marginal_precheck.md"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    paths = [BASE / "runs" / name for name in NAMES]
    before = {str(path): sha(path) for path in paths}
    for path in paths:
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    entries = []
    OUT.mkdir(parents=True, exist_ok=False)
    for path in paths:
        relative = path.resolve(strict=True).relative_to(BASE.resolve())
        destination = OUT / relative
        if not destination.resolve().is_relative_to(OUT.resolve()):
            raise ValueError("destination escapes bundle")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != before[str(path)]:
            raise ValueError("source changed before copy")
        stored = ("\n".join(line.rstrip() for line in raw.decode("utf-8-sig").splitlines()).rstrip("\n") + "\n").encode("utf-8") if raw else b""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(stored)
        if sha(destination) != hashlib.sha256(stored).hexdigest():
            raise ValueError("stored bytes differ")
        entries.append({"source": str(path), "stored_file": relative.as_posix(), "source_sha256": before[str(path)],
                        "stored_sha256": sha(destination), "stored_bytes": len(stored)})
    if any(sha(path) != expected for path, expected in before.items()):
        raise ValueError("source changed during copy")
    manifest = {"schema": "padfec.v33.beta_marginal_precheck_bundle/1", "iteration": 15,
                "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
                "status": "exact_algebra_preparation_only_not_L2_completion", "files": entries,
                "checks": "Python AST parsing and source/copy SHA equality; exact rational algebra output preserved, no new MC",
                "normalization": "UTF-8 LF, trailing line whitespace removed; original SHA retained"}
    with (OUT / "bundle_manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"files": len(entries), "stored_bytes": sum(row["stored_bytes"] for row in entries),
                      "manifest_sha256": sha(OUT / "bundle_manifest.json")}))


if __name__ == "__main__":
    main()
