import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_errata import read_rows

REPO = Path(__file__).resolve().parent.parent
BASE_SHA = "afc8b777ee171f7b662bef702b8dc4e71ea0b6911cad2be36ab7ed5639d40c80"
TOOL_FILES = ("build_report.py", "cfb.py", "content.py", "engine.py")


def offsets(raw):
    result = [0]
    for index, byte in enumerate(raw):
        if byte == 10:
            result.append(index + 1)
    return result


def patch_rows(raw, rows):
    tree = ast.parse(raw.decode("utf-8"))
    table = offsets(raw)
    parents = {}
    nodes = []
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            nodes.append(node)
    edits = {}
    for row in rows:
        hits = [node for node in nodes if row["old"] in node.value]
        if sum(node.value.count(row["old"]) for node in hits) != 1:
            raise SystemExit(row["id"] + ": old must occur once")
        edits.setdefault(hits[0], []).append(row)
    spans = []
    for node, items in edits.items():
        places = sorted((node.value.index(item["old"]), node.value.index(item["old"]) + len(item["old"]), item["id"]) for item in items)
        for left, right in zip(places, places[1:]):
            if left[1] > right[0]:
                raise SystemExit("overlap " + left[2] + " " + right[2])
        value = node.value
        for item in items:
            value = value.replace(item["old"], item["new"])
        parent = parents[node]
        is_para = isinstance(parent, ast.Tuple) and parent.elts and isinstance(parent.elts[0], ast.Constant) and parent.elts[0].value == "p"
        if "\n" in value and is_para:
            start = table[parent.lineno - 1] + parent.col_offset
            end = table[parent.end_lineno - 1] + parent.end_col_offset
            spans.append((start, end, ",\n    ".join("('p', %r)" % part for part in value.split("\n"))))
        else:
            start = table[node.lineno - 1] + node.col_offset
            end = table[node.end_lineno - 1] + node.end_col_offset
            spans.append((start, end, repr(value)))
    out = raw
    for start, end, replacement in sorted(spans, reverse=True):
        out = out[:start] + replacement.encode("utf-8") + out[end:]
    return out


def body_list(raw):
    tree = ast.parse(raw.decode("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "BODY":
            return node.value
    raise SystemExit("BODY not found")


def move_after(raw, source_prefix, heading_prefix):
    body = body_list(raw)
    table = offsets(raw)
    source = heading = None
    for index, element in enumerate(body.elts):
        if isinstance(element, ast.Tuple) and len(element.elts) >= 2 and isinstance(element.elts[1], ast.Constant) and isinstance(element.elts[1].value, str):
            if element.elts[1].value.startswith(source_prefix):
                source = element
            if element.elts[1].value.startswith(heading_prefix):
                heading = index
    if source is None or heading is None:
        raise SystemExit("move target missing")
    paragraph = body.elts[heading + 1]
    start = table[source.lineno - 1] + source.col_offset
    end = table[source.end_lineno - 1] + source.end_col_offset
    stop = table[paragraph.end_lineno - 1] + paragraph.end_col_offset
    if start > stop:
        raise SystemExit("move must go forward")
    chunk = raw[start:end]
    tail = end
    while raw[tail] in b" ,\r\n":
        tail += 1
    return raw[:start] + raw[tail:stop] + b",\n    " + chunk + raw[stop:]


def set_figure_widths(raw, widths):
    text = raw.decode("utf-8")
    for name, width in widths.items():
        needle = "('fig', '%s', 140," % name
        if text.count(needle) != 1:
            raise SystemExit("figure missing " + name)
        text = text.replace(needle, "('fig', '%s', %d," % (name, width))
    return text.encode("utf-8")


def set_line_spacing(build_report, body_ls, heading_ls):
    text = build_report.read_text(encoding="utf-8")
    pairs = (
        ("PS_H1 = keep(doc.add_parashape(0, prev=700, next=200))", "PS_H1 = keep(doc.add_parashape(0, prev=700, next=200, ls=%d))" % heading_ls),
        ("PS_H2 = keep(doc.add_parashape(0, prev=280, next=60))", "PS_H2 = keep(doc.add_parashape(0, prev=280, next=60, ls=%d))" % heading_ls),
        ("PS_BODY = doc.add_parashape(6, next=80)", "PS_BODY = doc.add_parashape(6, next=80, ls=%d)" % body_ls),
    )
    for old, new in pairs:
        if text.count(old) != 1:
            raise SystemExit("line spacing anchor missing: " + old)
        text = text.replace(old, new)
    build_report.write_text(text, encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--errata", type=Path, default=REPO / "docs/보고서 정오표.md")
    parser.add_argument("--tools", type=Path, default=Path(r"C:\hwp_work\rne_final\tools"))
    parser.add_argument("--current", type=Path, default=Path(r"C:\Users\scien\OneDrive\Desktop\양식.hwp"))
    parser.add_argument("--layout", type=Path, default=REPO / "report_repro/build_layout.json")
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out.resolve() == args.current.resolve():
        raise SystemExit("output must not be the current file")
    if args.out.exists():
        raise SystemExit("output exists")
    actual = hashlib.sha256(args.current.read_bytes()).hexdigest()
    if actual != BASE_SHA:
        raise SystemExit("current report hash changed, compare by hand first: " + actual)
    layout = json.loads(args.layout.read_text(encoding="utf-8"))
    rows = [row for row in read_rows(args.errata) if row.get("적용") == "apply"]
    args.workdir.mkdir(parents=True, exist_ok=True)
    for name in TOOL_FILES:
        shutil.copyfile(args.tools / name, args.workdir / name)
    raw = (args.workdir / "content.py").read_bytes()
    raw = patch_rows(raw, rows)
    for source_prefix, heading_prefix in layout.get("moves", []):
        raw = move_after(raw, source_prefix, heading_prefix)
    raw = set_figure_widths(raw, layout.get("figure_mm", {}))
    ast.parse(raw.decode("utf-8"))
    (args.workdir / "content.py").write_bytes(raw)
    set_line_spacing(args.workdir / "build_report.py", layout["body_ls"], layout["heading_ls"])
    subprocess.run([sys.executable, "-B", "build_report.py", str(args.out)], cwd=args.workdir, check=True)
    print("rows", len(rows), "out", args.out, "sha256", hashlib.sha256(args.out.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
