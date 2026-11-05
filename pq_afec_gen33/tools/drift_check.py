import argparse
import hashlib
import json
from pathlib import Path
import sys

PATTERNS = ("afec/*.py", "padfec/*.py", "experiments/quicbed/policy.go", "experiments/quicbed/qamp.go")


def normalized_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check(manifest, repository):
    if manifest.get("schema") != "padfec-shared-drift/1" or not manifest.get("roots") or not manifest.get("files"):
        raise ValueError("invalid drift manifest")
    if manifest.get("patterns") != list(PATTERNS):
        raise ValueError("unexpected inventory scope")
    problems, observations = [], []
    roots = manifest["roots"]
    expected = manifest["files"]
    for name, entry in expected.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
            raise ValueError("invalid relative file path")
        if set(entry["sha256_by_root"]) != set(roots):
            raise ValueError("incomplete generation declaration")
        hashes = list(entry["sha256_by_root"].values())
        if any(len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) for digest in hashes):
            raise ValueError("invalid declared hash")
        if len(set(hashes)) > 1 and not entry.get("reason", "").strip():
            raise ValueError("generation difference has no declared reason")
    for generation, raw_root in roots.items():
        base = Path(raw_root)
        if not base.is_absolute():
            base = repository / base
        base = base.resolve()
        observed = {path.relative_to(base).as_posix():path for pattern in PATTERNS for path in base.glob(pattern) if path.is_file()}
        for name in sorted(set(expected) - set(observed)):
            problems.append(dict(generation=generation, file=name, kind="missing"))
        for name in sorted(set(observed) - set(expected)):
            problems.append(dict(generation=generation, file=name, kind="undeclared_file"))
        for name in sorted(set(expected) & set(observed)):
            digest = normalized_hash(observed[name])
            target = expected[name]["sha256_by_root"][generation]
            observations.append(dict(generation=generation, file=name, sha256=digest))
            if digest != target:
                problems.append(dict(generation=generation, file=name, kind="undeclared_content", expected=target, actual=digest))
    return dict(schema="padfec-shared-drift-result/1", status="PASS" if not problems else "FAIL", normalization="CRLF to LF only", checked_files=len(observations), declared_different_paths=sum(len(set(e["sha256_by_root"].values())) > 1 for e in expected.values()), problems=problems, observations=observations)


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=repository / "g3/v33/shared_drift_v1.json")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.manifest.read_text(encoding="utf-8")), repository)
        result["manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = dict(status="ERROR", error=str(error))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    else:
        print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
