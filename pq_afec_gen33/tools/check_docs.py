import argparse
import glob
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "feb0b1850"
CANONICAL = tuple("docs/" + name for name in (
    "README.md", "SPEC_v3.3.1.md", "RESULTS_by_generation.md", "CLAIMS.md",
    "REPRODUCE.md", "GLOSSARY.md", "ERRATA_frozen_generations.md"))
TRANSLATIONS = ("첫 비행", "패리티", "패딩", "신용", "핸드셰이크", "증폭 제한", "데이터그램")
NEGATIONS = ("인용하지 않는다", "재현 안 됨", "쓰지 않는다", "근거로 쓰지 않는다")
EXTERNAL = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[/\\]|/mnt/c(?:/|\b)|codex_handoff|claude_brain|AppData|볼트", re.I)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA\uFE0F\u20E3]")
OLD_NUMBERS = re.compile(r"(?<![\d.])1792(?!\d|\.\d)|\bPASS\s+231\b", re.I)
ID_PATTERN = re.compile(
    r"(?<![\w])(?:SW:[A-Z]-\d+|TD:결정-\d{4}-p\d+|"
    r"(?:CP|MS|RT|DC|RP|BL|VF-EVA)-\d+(?:-\d+)?|"
    r"A[1-8](?:r\d+)?-(?:[EM])?\d+|[A-H]-(?:[EM])?\d+|Q-\d+|"
    r"[SCAWLJMGOTXERDFBQH]\d+)(?![\w])")
RANGE_PATTERN = re.compile(r"\b([SCAWLJMGOTXERDFBQH])(\d+)\s*[~～]\s*\1?(\d+)\b")
PATH_SUFFIXES = {".md", ".py", ".go", ".sh", ".ps1", ".json", ".jsonl", ".txt",
                 ".csv", ".toml", ".yaml", ".yml", ".mod", ".sum", ".log", ".tex",
                 ".pdf", ".hwp", ".hwpx", ".png", ".svg", ".sha256", ".srcsha"}
REPO_DIRS = {"docs", "tools", "tests", "experiments", "g3", "padfec", "padfec3", "report_repro", ".github"}
FIXED_HEADER = ("파일", "누가 읽나", "무엇이 깨지나", "고쳐도 되는가")
CLAIM_RULES = (
    ("generation_superiority", r"v3\.3(?:\.\d+)?(?:-dev)?(?:이|은|는)?\s*v3\.2(?:-dev)?보다\s*낫다", None),
    ("measured_improvement", r"실측으로\s*개선\s*확인", None),
    ("same_bytes", r"같은\s*(?:parity\s*)?바이트가?\s*(?:항상\s*)?(?:credit|신용)(?:과|와)\s*복구를\s*함께\s*산다", None),
    ("free_fec", r"추가\s*비용\s*없는\s*FEC", None),
    ("universal_noninferiority", r"어디서나\s*나쁘지\s*않다", None),
    ("prediction", r"예측이\s*맞는다", None),
    ("adaptation_gain", r"적응이\s*이득을\s*냈다", None),
    ("novel_bottleneck", r"PQ\s*(?:handshake|핸드셰이크)의\s*증폭\s*병목을\s*우리가\s*밝혔다", None),
    ("revisit", r"재방문\s*이득", r"(?=.*(?:NEW_TOKEN|token))(?=.*(?:session\s*ticket|ticket))(?=.*(?:껐|끈|끄고|비활성|disabled|off))"),
    ("large_cert_h1", r"(?:큰\s*cert|큰\s*인증서|big[-_ ]?cert).*?H1|H1.*?(?:큰\s*cert|큰\s*인증서|big[-_ ]?cert)", r"(?:initial\s*cwnd|congestion\s*window|IW)\s*(?:는|이|=|:)?\s*32"),
    ("hit_rate", r"99\.1\s*%\s*적중", r"고정\s*(?:일정|arm)|m\s*=\s*3"),
    ("nonsignificance", r"유의차(?:가|는)?\s*없[^.\n]*기각|기각[^.\n]*유의차(?:가|는)?\s*없", None),
    ("learn_no_loss", r"무손실을\s*배워\s*(?:parity|패리티)를\s*끈다", r"c1\s*경로에서만"),
    ("old_pto", r"12\.0\s*%.*10\.4\s*%.*z\s*=\s*0\.79", None),
)


def git(root, *args):
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    except OSError:
        return subprocess.CompletedProcess(args, 127, "", "git unavailable")


def code_ranges(line):
    spans, opening = [], None
    for match in re.finditer(r"(?<!\\)`+", line):
        if opening is None:
            opening = (len(match.group()), match.start())
        elif len(match.group()) == opening[0]:
            spans.append((opening[1], match.end()))
            opening = None
    return spans, opening is None


def cells(line):
    if not line.lstrip().startswith("|"):
        return None
    line = line.strip()[1:]
    if line.endswith("|"):
        line = line[:-1]
    spans, _balanced = code_ranges(line)
    result, current, escaped = [], [], False
    for index, char in enumerate(line):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == "|" and not any(start <= index < end for start, end in spans):
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    result.append("".join(current).strip())
    return result


def separator(row):
    return bool(row) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in row)


def rows(text):
    lines = text.splitlines()
    header, fence = None, None
    for index, line in enumerate(lines):
        match = re.match(r"\s*(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token[0]
            elif token[0] == fence:
                fence = None
            header = None
            yield index + 1, line, None, None, True
            continue
        if fence:
            yield index + 1, line, None, None, True
            continue
        row = cells(line)
        if row is None:
            header = None
        elif index + 1 < len(lines) and separator(cells(lines[index + 1])):
            header = row
        yield index + 1, line, header, row, False


def claim_violations(line, contextual=True):
    if contextual and any(text in line for text in NEGATIONS):
        return []
    found = []
    for name, pattern, qualifier in CLAIM_RULES:
        if re.search(pattern, line, re.I) and not (contextual and qualifier and re.search(qualifier, line, re.I)):
            found.append(name)
    return found


def clean_target(target):
    target = target.strip().strip("<>")
    if re.match(r"(?:https?|mailto|doi):", target, re.I):
        target = urlsplit(target).path
    else:
        target = re.split(r"[?#]", target, maxsplit=1)[0]
    target = unquote(target).replace("\\", "/")
    return re.sub(r":\d+(?:[-:]\d+)?$", "", target)


def looks_like_path(value):
    value = clean_target(value.strip().strip("'\""))
    if not value or value.startswith(("http:", "https:", "mailto:")):
        return False
    return (value.startswith(("./", "../", "/", "~", "docs/", "tools/", "experiments/", "tests/", "g3/"))
            or value.split("/", 1)[0] in REPO_DIRS
            or Path(value).suffix.lower() in PATH_SUFFIXES
            or re.match(r"[A-Za-z]:/", value) is not None)


def references(line):
    found = []
    for match in re.finditer(r"!?\[[^\]]*\]\((<[^>]*>|[^)]*)\)", line):
        value = match.group(1).strip()
        if not value.startswith("<"):
            value = re.split(r"\s+[\"']", value, maxsplit=1)[0]
        found.append((value.strip("<>"), False))
    definition = re.match(r"\s*\[[^\]]+\]:\s*(<[^>]*>|\S+)", line)
    if definition:
        found.append((definition.group(1).strip("<>"), False))
    for match in re.finditer(r"(?<!`)`([^`\n]+)`(?!`)", line):
        value = match.group(1).strip()
        if "://" in value or value.startswith("mailto:"):
            continue
        command = re.match(r"(?:python\d*(?:\.\d+)?|git|bash|pwsh|pytest|go)\s", value)
        if looks_like_path(value) and not command and not re.search(r"\s+(?:--?\w|[|&])", value):
            found.append((value, True))
        else:
            try:
                parts = shlex.split(value, posix=False)
            except ValueError:
                parts = value.split()
            found.extend((part.strip("'\"(),;"), True) for part in parts if looks_like_path(part.strip("'\"(),;")))
    return list(dict.fromkeys(found))


def reference_path(root, document, target, inline):
    clean = clean_target(target)
    if inline and clean.split("/", 1)[0] in REPO_DIRS:
        return root / clean
    return document.parent / clean


def reference_errors(root, document, line):
    if "로컬 보존" in line:
        return []
    errors = []
    for target, inline in references(line):
        if target.startswith("#") or re.match(r"(?:https?|mailto|doi):", target, re.I):
            continue
        clean = clean_target(target)
        if not clean:
            continue
        path = reference_path(root, document, target, inline).resolve()
        if EXTERNAL.search(target) or not path.is_relative_to(root):
            errors.append("outside path requires 로컬 보존: " + target)
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(("g3/v33/validation/", ".github/")):
            errors.append("export-excluded path requires 로컬 보존: " + target)
            continue
        matches = glob.glob(str(path)) if glob.has_magic(str(path)) else [str(path)]
        if not matches or not any(Path(value).exists() for value in matches):
            errors.append("missing path: " + target)
    return errors


def check_file(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    label = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    if not path.is_file():
        return [label + ": missing document"]
    errors = []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return [label + ": " + str(exc)]
    for number, line, header, row, fenced in rows(text):
        styled = line
        valid_table = bool(header and row and len(header) == len(row) and code_ranges(line)[1])
        if header and row and not valid_table:
            errors.append(f"{label}:{number}: malformed table row")
        if path.name == "ERRATA_frozen_generations.md" and valid_table and not separator(row):
            if "틀린 문장(원문 인용)" in header:
                quoted = header.index("틀린 문장(원문 인용)")
                styled = " | ".join(value for index, value in enumerate(row) if index != quoted)
        if "로컬 보존" not in line and EXTERNAL.search(line):
            errors.append(f"{label}:{number}: external location requires 로컬 보존")
        if not (valid_table and (path.name == "CLAIMS.md" or "ERRATA" in path.name)):
            errors.extend(f"{label}:{number}: forbidden claim: {name}" for name in claim_violations(line))
        errors.extend(f"{label}:{number}: translated term: {word}" for word in TRANSLATIONS if word in styled)
        if "\u2014" in styled or "\u2013" in styled:
            errors.append(f"{label}:{number}: em/en dash")
        if EMOJI.search(styled):
            errors.append(f"{label}:{number}: emoji")
        if OLD_NUMBERS.search(styled):
            errors.append(f"{label}:{number}: obsolete test count")
        if not fenced:
            errors.extend(f"{label}:{number}: {error}" for error in reference_errors(root, path, line))
    return errors


def fixed_documents(root):
    path = root / "docs/REPRODUCE.md"
    if not path.is_file():
        return [], [], ["docs/REPRODUCE.md: missing fixed-document table"]
    internal, external, errors = [], [], []
    active, found = False, False
    for number, line, header, row, fenced in rows(path.read_text(encoding="utf-8-sig")):
        heading = re.match(r"^(#{1,2})\s+(.+)", line)
        if heading:
            active = bool(re.match(r"9(?:[.)\s]|$)", heading.group(2)))
        if not active or fenced or not row or not header or tuple(header) != FIXED_HEADER or separator(row) or row == header:
            continue
        found = True
        targets = re.findall(r"`([^`]+)`", row[0])
        if not targets or len(row) != len(FIXED_HEADER):
            errors.append(f"docs/REPRODUCE.md:{number}: malformed fixed-document row")
        for target in targets:
            resolved = (root / target).resolve()
            if not resolved.is_relative_to(root):
                if "로컬 보존" not in line:
                    errors.append(f"docs/REPRODUCE.md:{number}: external fixed path requires 로컬 보존")
                external.append(target)
            elif not resolved.is_file():
                errors.append(f"docs/REPRODUCE.md:{number}: missing fixed document: {target}")
            else:
                internal.append(resolved.relative_to(root).as_posix())
    if not found or not internal:
        errors.append("docs/REPRODUCE.md: section 9 has no internal fixed-document table")
    if len(set(internal + external)) != len(internal + external):
        errors.append("docs/REPRODUCE.md: duplicate fixed document")
    return internal, external, errors


def check_fixed(root):
    internal, external, errors = fixed_documents(root)
    notes = [f"fixed documents {len(internal)}, protected external paths {len(external)} (보호 경로 검사 대상)"]
    if git(root, "cat-file", "-e", BASELINE).returncode:
        notes.append("기준 커밋 없음: " + BASELINE)
        return errors, notes
    if internal:
        result = git(root, "diff", "--name-only", BASELINE, "--", *internal)
        if result.returncode:
            errors.append("fixed-document diff failed: " + result.stderr.strip())
        else:
            errors.extend("fixed document differs from baseline: " + name for name in result.stdout.splitlines() if name)
    return errors, notes


def document_files(root):
    result = git(root, "ls-files", "-z", "--", "docs")
    if result.returncode == 0:
        names = [name for name in result.stdout.split("\0") if name]
    else:
        names = [path.relative_to(root).as_posix() for path in (root / "docs").rglob("*") if path.is_file()]
    return sorted(name for name in names if not name.startswith("docs/loop_record/"))


def check_index(root):
    index = root / "docs/README.md"
    if not index.is_file():
        return ["docs/README.md: missing index"], []
    text = index.read_text(encoding="utf-8-sig")
    listed = set()
    for _number, line, _header, _row, fenced in rows(text):
        if fenced:
            continue
        for target, inline in references(line):
            if re.match(r"(?:https?|mailto):", target, re.I):
                continue
            path = reference_path(root, index, target, inline).resolve()
            if path.is_relative_to(root):
                listed.add(path.relative_to(root).as_posix())
    expected = document_files(root)
    errors = ["unlisted document: " + name for name in expected if name not in listed]
    if (root / "docs/loop_record").exists() and "docs/loop_record" not in listed:
        errors.append("docs/loop_record: missing grouped index entry")
    return errors, [f"docs {len(set(expected) & listed)}/{len(expected)} listed", "docs/loop_record: grouped, excluded from per-file index"]


def extract_ids(text):
    found = set(ID_PATTERN.findall(text))
    for match in RANGE_PATTERN.finditer(text):
        prefix, low, high = match.groups()
        low, high = int(low), int(high)
        if low <= high <= low + 1000:
            found.update(prefix + str(number) for number in range(low, high + 1))
    return found


def check_ids(root):
    glossary = root / "docs/GLOSSARY.md"
    if not glossary.is_file():
        return ["docs/GLOSSARY.md: missing ID glossary"], []
    known = extract_ids(glossary.read_text(encoding="utf-8-sig"))
    used, errors = set(), []
    paths = [root / "README.md"] + sorted((root / "docs").rglob("*.md"))
    for path in paths:
        if not path.is_file() or path == glossary or path.is_relative_to(root / "docs/loop_record"):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            names = extract_ids(line)
            used.update(names)
            errors.extend(f"{path.relative_to(root).as_posix()}:{number}: undefined ID: {name}" for name in sorted(names - known))
    return errors, [f"ids {len(used & known)}/{len(used)} defined", "docs/loop_record: grouped, excluded from ID checks"]


def check_claims(root):
    path = root / "docs/CLAIMS.md"
    if not path.is_file():
        return ["docs/CLAIMS.md: missing claims table"], []
    found = set()
    for _number, line, header, row, fenced in rows(path.read_text(encoding="utf-8-sig")):
        if header and row and len(header) == len(row) and code_ranges(line)[1] and not fenced and not separator(row) and row != header:
            found.update(claim_violations(" | ".join(row), contextual=False))
    expected = {name for name, _pattern, _qualifier in CLAIM_RULES}
    return ["CLAIMS table missing forbidden type: " + name for name in sorted(expected - found)], [f"claims {len(found)}/{len(expected)} covered"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--canonical", action="store_true")
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--file", type=Path, action="append", default=[])
    parser.add_argument("--index", action="store_true")
    parser.add_argument("--ids", action="store_true")
    parser.add_argument("--claims", action="store_true")
    args = parser.parse_args(argv)
    if args.final and not args.canonical:
        parser.error("--final requires --canonical")
    if not any((args.canonical, args.file, args.index, args.ids, args.claims)):
        parser.error("select --canonical, --file, --index, --ids or --claims")
    root = args.root.resolve()
    paths = [(root / path).resolve() for path in args.file]
    notes, errors = [], []
    if args.canonical:
        for relative in (("README.md",) + CANONICAL if args.final else CANONICAL):
            path = root / relative
            if args.final or path.exists():
                paths.append(path)
            else:
                notes.append("pending canonical: " + relative)
    for path in dict.fromkeys(paths):
        errors.extend(check_file(root, path))
    notes.insert(0, f"checked files {len(dict.fromkeys(paths))}")
    if (root / "docs/REPRODUCE.md").is_file():
        fixed_errors, fixed_notes = check_fixed(root)
        errors.extend(fixed_errors)
        notes.extend(fixed_notes)
    for enabled, check in ((args.index, check_index), (args.ids, check_ids), (args.claims, check_claims)):
        if enabled:
            found, information = check(root)
            errors.extend(found)
            notes.extend(information)
    for message in notes + errors:
        print(message)
    print("FAIL" if errors else "PASS")
    return int(bool(errors))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
