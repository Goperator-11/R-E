import argparse
import ast
import json
import os
from pathlib import Path
import sys
import tokenize

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", ".venv", "venv", "__pycache__", "_build", "state", "results", "round1_backup", "node_modules", ".pytest_cache"}
ARCHIVED = {"g3/v33", "tests/fixtures"}


def sources(root=ROOT):
    root = Path(root).resolve()
    found = []
    for directory, dirs, names in os.walk(root):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in IGNORED
                         and (base / d).relative_to(root).as_posix() not in ARCHIVED)
        found.extend((base / name).relative_to(root).as_posix() for name in names if name.endswith(".py"))
    return sorted(found)


def check(paths, root=ROOT):
    errors = []
    for relative in paths:
        path = Path(root) / relative
        try:
            with tokenize.open(path) as stream:
                ast.parse(stream.read(), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append({"path": str(relative), "error": str(error)})
    return {"status": "PASS" if not errors else "FAIL", "files": len(paths), "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    result = check(args.paths or sources())
    print(json.dumps(result, ensure_ascii=False))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
