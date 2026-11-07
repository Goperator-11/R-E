import argparse
import json
from pathlib import Path
import re
import subprocess

LIMIT = 20_000_000
ROOT = Path(__file__).resolve().parents[1]
PRIVATE_KEY = re.compile(rb"-----BEGIN (?P<kind>(?:[A-Z0-9]+ )?PRIVATE KEY)-----\s+(?:[A-Za-z][A-Za-z0-9-]*:[^\r\n]*\s+)*(?:[A-Za-z0-9+/=]+\s+)+-----END (?P=kind)-----")


def staged_sizes(root):
    command = ["git", "-C", str(root)]
    changed = subprocess.check_output(command + ["diff", "--cached", "--no-renames", "--name-only", "-z", "--diff-filter=ACM"]).split(b"\0")
    wanted = {name for name in changed if name}
    index = subprocess.check_output(command + ["ls-files", "--stage", "-z"]).split(b"\0")
    entries = []
    for row in index:
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, sha, stage = meta.split()
        if name in wanted and stage == b"0" and mode != b"160000":
            entries.append((name.decode("utf-8"), sha.decode("ascii")))
    if not entries:
        return []
    hashes = "\n".join(sha for _, sha in entries) + "\n"
    sizes = subprocess.check_output(command + ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"], input=hashes.encode("ascii")).decode("ascii").splitlines()
    result = []
    for (name, sha), line in zip(entries, sizes, strict=True):
        actual, kind, size = line.split()
        if actual != sha or kind != "blob":
            raise ValueError("staged object is not a verified blob")
        result.append({"path": name, "bytes": int(size), "blob": sha})
    return result


def private_keys(root, files):
    found = []
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        for row in files:
            if row["bytes"] > LIMIT:
                continue
            process.stdin.write((row["blob"] + "\n").encode("ascii"))
            process.stdin.flush()
            sha, kind, size = process.stdout.readline().decode("ascii").split()
            if sha != row["blob"] or kind != "blob" or int(size) != row["bytes"]:
                raise ValueError("staged object identity changed")
            raw = process.stdout.read(int(size))
            if process.stdout.read(1) != b"\n":
                raise ValueError("incomplete staged blob")
            if PRIVATE_KEY.search(raw):
                found.append(row["path"])
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("could not inspect staged blobs")
    return found


def check(root=ROOT):
    files = staged_sizes(root)
    failures = [row for row in files if row["bytes"] > LIMIT]
    keys = private_keys(root, files)
    return {"status": "FAIL" if failures or keys else "PASS", "limit_bytes": LIMIT,
            "checked": len(files), "oversize": failures, "private_key_files": keys}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = check(args.root)
    print(json.dumps(result, ensure_ascii=False))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
