import argparse
import json
from pathlib import Path
import re
import sys

TOKEN = re.compile(r"([^.\[\]]+)(\[[^\]]*\])?")
REPO = Path(__file__).resolve().parent.parent


def pointer(document, key):
    current = document
    parts = []
    for name, selector in TOKEN.findall(key):
        current = current[name]
        parts.append(name)
        if not selector:
            continue
        inner = selector[1:-1]
        if re.fullmatch(r"\d+", inner):
            index = int(inner)
        else:
            wanted = dict(part.split("=", 1) for part in inner.split(","))
            hits = [index for index, item in enumerate(current) if all(str(item.get(k)) == v for k, v in wanted.items())]
            if len(hits) != 1:
                raise KeyError(f"{key}: selector {inner} matched {len(hits)}")
            index = hits[0]
        current = current[index]
        parts.append(str(index))
    return "/" + "/".join(parts), current


def table(root, keys_path):
    spec = json.loads(keys_path.read_text(encoding="utf-8"))
    paths = {name: path for name, path in spec["sources"].items() if path.startswith("g3/v33/results/")}
    documents = {name: json.loads((root / path).read_text(encoding="utf-8")) for name, path in paths.items()}
    lines = ["| id | new | 근거 키 |", "|---|---|---|"]
    for identity, items in spec["rows"].items():
        groups = {}
        for item in items:
            if item["source"] in documents:
                location, value = pointer(documents[item["source"]], item["key"])
                groups.setdefault(item["source"], []).append((item, location, value))
        for source, entries in groups.items():
            shown = []
            evidence = []
            for item, location, value in entries:
                scale = item.get("scale", 1)
                text = f"{value * scale:.{item['decimals']}f}"
                shown.append(text + "%" if scale == 100 else text)
                evidence.append(f"{paths[source]}#{location}")
            lines.append(f"| {identity} | {' , '.join(shown)} | {'; '.join(evidence)} |")
    return "\n".join(lines)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=REPO)
    parser.add_argument("--keys", type=Path)
    args = parser.parse_args(argv)
    print(table(args.root, args.keys or args.root / "report_repro/measure_keys.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
