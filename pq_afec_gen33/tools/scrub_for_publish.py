import argparse
import collections
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "user_path": re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"']+|/(?:Users|home)/[^/\s\"']+)"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "private_key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
}
BINARY = {".gz", ".png", ".jpg", ".jpeg", ".zip", ".pdf", ".xlsx", ".docx", ".pptx", ".exe", ".dll", ".pyc"}
HISTORY_LIMIT = 20_000_000
PRIVATE_KEY_BLOCK = re.compile(rb"-----BEGIN (?P<kind>(?:[A-Z0-9]+ )?PRIVATE KEY)-----\s+(?:[A-Za-z][A-Za-z0-9-]*:[^\r\n]*\s+)*(?:[A-Za-z0-9+/=]+\s+)+-----END (?P=kind)-----")


def git_root(root):
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True)
    except OSError as error:
        return False, str(error)
    top = done.stdout.decode("utf-8", "replace").strip()
    if done.returncode or not top:
        return False, done.stderr.decode("utf-8", "replace").strip() or "git rev-parse failed"
    try:
        same = os.path.samefile(top, root)
    except OSError as error:
        return False, str(error)
    return same, "" if same else "inside the git work tree " + top


def walk(root, unavailable):
    def failed(error):
        unavailable.append({"path": str(error.filename), "error": str(error)})

    names = []
    for current, directories, files in os.walk(root, onerror=failed):
        directories[:] = sorted(name for name in directories if name != ".git")
        base = Path(current).relative_to(root)
        names.extend((base / name).as_posix() for name in sorted(files) if name != ".git")
    return names


def listed_files(root, unavailable):
    if git_root(root)[0]:
        return "git ls-files", subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode("utf-8").split("\0")
    return "os.walk", walk(root, unavailable)


def check(root=ROOT):
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"--root is not a folder: {root}")
    counts = collections.Counter()
    examples_by_kind = {kind: [] for kind in PATTERNS}
    scanned, binary, unavailable = 0, 0, []
    listing, names = listed_files(root, unavailable)
    for name in names:
        if not name:
            continue
        path = root / name
        if path.suffix.lower() in BINARY:
            binary += 1
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                found = set()
                for number, line in enumerate(stream, 1):
                    for kind, pattern in PATTERNS.items():
                        if kind not in found and pattern.search(line):
                            counts[kind] += 1
                            found.add(kind)
                            if len(examples_by_kind[kind]) < 200:
                                examples_by_kind[kind].append({"path": name, "line": number, "kind": kind})
                scanned += 1
        except OSError as error:
            unavailable.append({"path": name, "error": str(error)})
    examples = [row for rows in examples_by_kind.values() for row in rows]
    return {"mode": "check_only", "file_listing": listing, "status": "FINDINGS" if counts or unavailable else "PASS",
            "text_files_scanned": scanned, "known_binary_files_not_decoded": binary,
            "affected_file_counts": dict(counts), "examples": examples,
            "examples_truncated": sum(counts.values()) > len(examples), "unavailable": unavailable}


def reachable_blobs(root):
    git = ["git", "-C", str(root)]
    listing = subprocess.check_output(git + ["rev-list", "--objects", "--all"])
    paths = {}
    order = []
    for row in listing.split(b"\n"):
        if not row:
            continue
        sha, _, name = row.partition(b" ")
        sha = sha.decode("ascii")
        if sha not in paths:
            order.append(sha)
            paths[sha] = name.decode("utf-8", "surrogateescape") or None
    request = "".join(sha + "\n" for sha in order).encode("ascii")
    checked = subprocess.check_output(git + ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"], input=request).decode("ascii").splitlines()
    blobs = {}
    for line in checked:
        sha, kind, size = line.split()
        if kind == "blob":
            blobs[sha] = int(size)
    return blobs, paths, len(order)


def scan_blob_contents(root, blobs):
    found = []
    order = list(blobs)
    process = subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def feed():
        try:
            for sha in order:
                process.stdin.write((sha + "\n").encode("ascii"))
        finally:
            process.stdin.close()

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    scanned = 0
    for expected in order:
        header = process.stdout.readline().decode("ascii").split()
        if len(header) != 3 or header[0] != expected or header[1] != "blob":
            raise ValueError(f"unexpected cat-file header for {expected}: {header}")
        raw = process.stdout.read(int(header[2]))
        if process.stdout.read(1) != b"\n":
            raise ValueError(f"incomplete blob {expected}")
        scanned += len(raw)
        if b"PRIVATE KEY" in raw and PRIVATE_KEY_BLOCK.search(raw):
            found.append(expected)
    writer.join()
    if process.wait() != 0:
        raise RuntimeError("git cat-file --batch failed")
    return found, scanned


def commits_touching(root, paths, change):
    if not paths:
        return []
    output = subprocess.check_output(["git", "-C", str(root), "log", "--all", f"--diff-filter={change}", "--format=%H %cI", "--", *sorted(paths)]).decode("utf-8")
    return [{"commit": line.split()[0], "committed": line.split()[1]} for line in output.splitlines() if line.strip()]


def head_blobs(root):
    try:
        listing = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-r", "-z", "HEAD"], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return {}
    result = collections.defaultdict(list)
    for row in listing.split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        result[meta.split()[2].decode("ascii")].append(name.decode("utf-8", "surrogateescape"))
    return result


def history(root=ROOT, limit=HISTORY_LIMIT):
    root = Path(root)
    blobs, paths, objects = reachable_blobs(root)
    keys, scanned = scan_blob_contents(root, blobs)
    in_head = head_blobs(root)

    def describe(sha):
        return {"blob": sha, "bytes": blobs[sha], "path_seen": paths.get(sha), "head_paths": sorted(in_head.get(sha, []))}

    key_rows = sorted((describe(sha) for sha in keys), key=lambda row: (row["path_seen"] or "", row["blob"]))
    key_paths = {row["path_seen"] for row in key_rows if row["path_seen"]}
    oversize = sorted((describe(sha) for sha, size in blobs.items() if size > limit), key=lambda row: (-row["bytes"], row["blob"]))
    refs = subprocess.check_output(["git", "-C", str(root), "for-each-ref", "--format=%(refname)"]).decode("utf-8").split()
    return {"mode": "history_check_only", "status": "FINDINGS" if key_rows or oversize else "PASS",
            "refs": refs, "reachable_objects": objects, "reachable_blobs": len(blobs),
            "blob_bytes_scanned": scanned, "private_key_blob_count": len(key_rows),
            "private_key_blobs": key_rows,
            "private_key_added_in": commits_touching(root, key_paths, "A"),
            "private_key_removed_in": commits_touching(root, key_paths, "D"),
            "oversize_limit_bytes": limit, "oversize_blob_count": len(oversize), "oversize_blobs": oversize}


def main(argv=None):
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"--root is not a folder: {args.root}", file=sys.stderr)
        return 2
    if args.history:
        is_root, reason = git_root(args.root)
        if not is_root:
            print(f"--history reads git history and needs the top folder of a git repository; {args.root} is not one ({reason}). "
                  "Use --check without --history for a plain folder.", file=sys.stderr)
            return 2
    result = history(args.root) if args.history else check(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
