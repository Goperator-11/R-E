import argparse
import ast
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "코드 지도.md"
SECTION = "수량별 알고리즘 지도"
ROWS = ("A_pre", "1-RTT 조건", "J3와 실패 가지", "arrivals 우도", "3등급 경계", "guard",
        "사전과 hazard", "S 추정과 n_need 오차", "J_TIE", "1452 B 상한", "codec 형식 차이")
LABEL = "수량"
COLUMNS = {"Python 함수": "python", "Go 함수": "go", "시험 이름": "test"}
TOKEN = re.compile(r"`([^`]+)`")
SEPARATOR = re.compile(r":?-{3,}:?")
GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*[\[(]", re.M)
GO_SINGLE = re.compile(r"^(?:const|var)\s+([A-Za-z_]\w*)\b", re.M)
GO_BLOCK = re.compile(r"^(?:const|var)\s*\(\s*$")
GO_BLOCK_NAME = re.compile(r"^\s+([A-Za-z_]\w*)\b")
GO_TEST = re.compile(r"^func\s+(Test\w+)\s*\(\s*\w+\s+\*testing\.T\s*\)", re.M)


def cells(line):
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def section_table(text):
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.startswith("## ") and SECTION in line]
    if len(starts) != 1:
        raise ValueError("section '%s' must appear once, found %d" % (SECTION, len(starts)))
    header, rows, seen_table = None, [], False
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        if not line.lstrip().startswith("|"):
            if seen_table:
                break
            continue
        seen_table = True
        row = cells(line)
        if header is None:
            header = row
        elif all(SEPARATOR.fullmatch(cell.replace(" ", "")) for cell in row):
            continue
        else:
            rows.append(row)
    if header is None:
        raise ValueError("no table under '%s'" % SECTION)
    return header, rows


def python_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    names = {}
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [target for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        for target in targets:
            names.setdefault(target.id, node.lineno)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.setdefault(node.name, node.lineno)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.setdefault(node.name + "." + child.name, child.lineno)
    return names


def go_names(path):
    text = path.read_text(encoding="utf-8")
    names = {}

    def line_of(offset):
        return text.count("\n", 0, offset) + 1

    for pattern in (GO_FUNC, GO_SINGLE):
        for match in pattern.finditer(text):
            names.setdefault(match.group(1), line_of(match.start()))
    block = False
    for number, line in enumerate(text.splitlines(), 1):
        if block:
            if line.strip() == ")":
                block = False
                continue
            match = GO_BLOCK_NAME.match(line)
            if match and not line.lstrip().startswith("//"):
                names.setdefault(match.group(1), number)
        elif GO_BLOCK.match(line):
            block = True
    return names


def test_names(path):
    if path.suffix == ".go":
        text = path.read_text(encoding="utf-8")
        return {match.group(1): text.count("\n", 0, match.start()) + 1 for match in GO_TEST.finditer(text)}
    return {name: line for name, line in python_names(path).items()
            if name.rsplit(".", 1)[-1].startswith("test_")}


def resolve(kind, relative, cache):
    path = ROOT / relative
    if not path.is_file():
        raise ValueError("missing file: " + relative)
    if kind == "python" and path.suffix != ".py":
        raise ValueError("Python column needs a .py file: " + relative)
    if kind == "go" and path.suffix != ".go":
        raise ValueError("Go column needs a .go file: " + relative)
    if kind == "test" and not (path.name.endswith("_test.go")
                               or (path.suffix == ".py" and path.name.startswith("test_"))):
        raise ValueError("test column needs a test file: " + relative)
    key = (kind, relative)
    if key not in cache:
        if kind == "test":
            cache[key] = test_names(path)
        elif kind == "python":
            cache[key] = python_names(path)
        else:
            cache[key] = go_names(path)
    return cache[key]


def check(doc=DOC):
    header, rows = section_table(Path(doc).read_text(encoding="utf-8-sig"))
    problems, found = [], []
    if LABEL not in header or any(column not in header for column in COLUMNS):
        return ["table header must include %s and %s" % (LABEL, ", ".join(COLUMNS))], found
    labels = [row[header.index(LABEL)] if len(row) == len(header) else None for row in rows]
    if any(len(row) != len(header) for row in rows):
        problems.append("malformed row in '%s'" % SECTION)
    if sorted(label for label in labels if label) != sorted(ROWS) or len(labels) != len(ROWS):
        problems.append("rows must be exactly: " + ", ".join(ROWS))
    cache = {}
    for row in rows:
        if len(row) != len(header):
            continue
        label = row[header.index(LABEL)]
        for column, kind in COLUMNS.items():
            current, count = None, 0
            for token in TOKEN.findall(row[header.index(column)]):
                if token.endswith((".py", ".go")):
                    current = token
                    continue
                if current is None:
                    problems.append("%s / %s: name %s has no file before it" % (label, column, token))
                    continue
                try:
                    names = resolve(kind, current, cache)
                except (OSError, SyntaxError, ValueError) as error:
                    problems.append("%s / %s: %s" % (label, column, error))
                    continue
                if token not in names:
                    problems.append("%s / %s: %s not found in %s" % (label, column, token, current))
                    continue
                count += 1
                found.append("%s | %s | %s:%d %s" % (label, column, current, names[token], token))
            if count == 0:
                problems.append("%s / %s: no resolved name" % (label, column))
    return problems, found


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", type=Path, default=DOC)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        problems, found = check(args.doc)
    except (OSError, UnicodeError, ValueError) as error:
        problems, found = [str(error)], []
    if not args.quiet:
        for line in found:
            print(line)
    for line in problems:
        print("PROBLEM", line)
    print("%s rows %d names %d" % ("FAIL" if problems else "PASS", len(ROWS), len(found)))
    return int(bool(problems))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
