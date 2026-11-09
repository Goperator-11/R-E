import argparse
import ast
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPORT_ROOT, source_path

REPO = REPORT_ROOT.parent
FORBIDDEN = (
    "v3.3이 v3.2보다 낫다",
    "실측으로 개선 확인",
    "같은 바이트가 credit과 복구를 함께 산다",
    "추가 비용 없는 FEC",
    "어디서나 나쁘지 않다",
    "예측이 맞는다",
    "적응이 이득을 냈다",
    "PQ handshake의 증폭 병목을 우리가 밝혔다",
    "PTO 12.0% 대 10.4%, z=0.79",
)
NUMBER = re.compile(r"(?<![0-9_.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![0-9]|\.\d)")
IDENTIFIER = re.compile(r"(?<![A-Za-z0-9_])(?:v\d+(?:\.\d+)+(?:-dev)?|X25519(?:MLKEM768)?|ML-(?:KEM|DSA)(?:-\d+)?|(?:RT|RFC|FIPS)[ -]\d+|H[1-5]|C1|L[1-6]|X(?:10|[1-9])|F\d{2}|gen-?[23]|p\d+)(?![A-Za-z0-9_])")
FIGURE = re.compile(r"(?:Fig\.|Table|그림|표)\s*\d+(?:\s*[~∼]\s*\d+)?")
TEXT_COLUMNS = ("new", "측정 뒤 문구", "측정 못 한 경우 문구", "러너 구현 뒤 미측정 문구")
SELECTED_COLUMNS = {"측정 뒤 문구": "측정 뒤 문구", "measured": "측정 뒤 문구", "측정 못 한 경우 문구": "측정 못 한 경우 문구",
                    "측정 못 함": "측정 못 한 경우 문구", "러너 구현 뒤 미측정 문구": "러너 구현 뒤 미측정 문구", "구현하였으나": "러너 구현 뒤 미측정 문구"}


def normalize(value):
    number = Decimal(str(value).replace(",", "").strip())
    if not number.is_finite():
        raise ValueError("non-finite number")
    return format(number.normalize(), "f") if number else "0"


def cells(line):
    result = re.split(r"(?<!\\)\|", line.strip().strip("|"))
    return [cell.strip().replace(r"\|", "|") for cell in result]


def decode(cell):
    value = cell.strip()
    if value.startswith("`") and value.endswith("`"):
        value = value[1:-1]
    if value.startswith('"'):
        result = json.loads(value)
        if not isinstance(result, str):
            raise ValueError("table cell must contain a string")
        return result
    return value.replace("<br>", "\n")


def read_rows(path):
    header = None
    known_header = None
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.lstrip().startswith("|"):
            header = None
            continue
        values = cells(line)
        if values and values[0] == "id":
            header = values if "old" in values else None
            known_header = header or known_header
            continue
        if header is None or all(re.fullmatch(r":?-+:?", value) for value in values):
            continue
        if len(values) != len(header):
            raise ValueError(f"{path.name}:{number}: column count mismatch")
        row = {name: decode(value) for name, value in zip(header, values)}
        row["_line"] = number
        rows.append(row)
    required = {"id", "구역", "절", "content.py 줄", "old", "new", "근거 키", "상태", "분량 증감(줄)"}
    if not known_header or not required.issubset(known_header) or not rows:
        raise ValueError("errata table is missing required columns or rows")
    return rows


def forbidden_from_claims(path, required=False):
    if not path.exists():
        if required:
            raise ValueError("CLAIMS.md is required: " + str(path))
        print("CLAIMS 미확인:", path.name, "없음, 내장 금지어", len(FORBIDDEN), "개로 검사")
        return list(FORBIDDEN)
    column = None
    phrases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            column = None
            continue
        values = cells(line)
        matches = [index for index, value in enumerate(values) if value in {"금지", "금지 표현", "금지 문자열", "쓰면 안 되는 말", "금지 문구"}]
        if matches:
            column = matches[0]
            continue
        if column is None or column >= len(values) or re.fullmatch(r":?-+:?", values[column]):
            continue
        cell = values[column]
        quoted = re.findall(r'"([^"\n]+)"|`([^`\n]+)`', cell)
        parts = [first or second for first, second in quoted] if quoted else cell.split("<br>")
        phrases.extend(part.strip() for part in parts if part.strip())
    if not phrases:
        raise ValueError("CLAIMS.md has no recognized forbidden-expression table")
    return phrases


def forbidden_hits(text, phrases):
    hits = [phrase for phrase in phrases if phrase in text]
    if "재방문 이득" in text and not ("NEW_TOKEN" in text and "session ticket" in text):
        hits.append("조건 없는 재방문 이득")
    if "99.1% 적중" in text and not ("1 ms" in text and ("oracle" in text or "최적" in text)):
        hits.append("정의 없는 99.1% 적중")
    if "무손실을 배워 parity를 끈다" in text and "C1" not in text and "c1" not in text:
        hits.append("C1 조건 없는 parity 중지")
    if "기각" in text and ("유의" in text or "차이" in text):
        hits.append("유의차 미확인을 기각으로 표현")
    if re.search(r"큰\s*cert|큰\s*인증서", text) and "H1" in text and not ("initial cwnd" in text or re.search(r"\bIW\s*32\b", text)):
        hits.append("initial cwnd 조건 없는 큰 cert H1")
    return hits


def checked_numbers(text):
    text = text.replace("−", "-")
    superscripts = str.maketrans("⁺⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "+-0123456789")
    scientific = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*[×x·]\s*10\s*(?:\^\{?([-+]?\d+)\}?|([⁺⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+))")
    text = scientific.sub(lambda match: match[1] + "e" + (match[2] or match[3].translate(superscripts)), text)
    text = re.sub(r"(?<![0-9])10([⁺⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda match: "1e" + match[1].translate(superscripts), text)
    return [normalize(value) for value in NUMBER.findall(FIGURE.sub(" ", IDENTIFIER.sub(" ", text)))]


def load_pins(path):
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "errata_numbers/1" or not isinstance(document.get("rows"), dict):
        raise ValueError("errata_numbers schema mismatch")
    return document["rows"]


def key_numbers(items):
    return {normalize(item["text"].replace("−", "-").replace(",", "").lstrip("+")) for item in items}


def row_number_errors(row, pins, entries):
    identity = row["id"]
    baseline = set(checked_numbers(row["old"]))
    used = set()
    errors = []
    for column in TEXT_COLUMNS:
        text = row.get(column, "해당 없음")
        if text == "해당 없음":
            continue
        for value in sorted(set(checked_numbers(text)) - baseline):
            used.add(value)
            pin = pins.get(value)
            if pin is None:
                errors.append(f"{identity}: {column} number {value} has no row evidence")
            elif pin.startswith("literal:"):
                continue
            elif pin not in entries or entries[pin]["status"] != "verified":
                errors.append(f"{identity}: {column} number {value} cites unverified entry {pin}")
            elif value not in entries[pin]["numbers"]:
                errors.append(f"{identity}: {column} number {value} differs from entry {pin}")
    for value in sorted(set(pins) - used):
        errors.append(f"{identity}: stale row evidence for {value}")
    return errors


def applied_text(row):
    selected = row.get("selected", "해당 없음")
    if selected == "원문 유지":
        return row["old"]
    column = SELECTED_COLUMNS.get(selected)
    return row[column] if column else row["new"]


def planned_text(row):
    measured = row.get("측정 뒤 문구", "해당 없음")
    if row.get("selected", "해당 없음").startswith("pending:") and measured != "해당 없음":
        return measured
    return applied_text(row)


def selection_errors(row, final):
    identity = row["id"]
    applied = applied_text(row)
    errors = []
    if applied == "해당 없음":
        errors.append(f"{identity}: selected column is empty")
    if final and (row.get("selected", "해당 없음").startswith("pending:") or "측정 대기" in applied):
        errors.append(f"{identity}: pending text cannot be final")
    return errors


def report_baseline():
    try:
        baseline = json.loads(source_path("report_baseline").read_text(encoding="utf-8"))
    except (FileNotFoundError, KeyError):
        print("HWP baseline 미확인: 로컬 baseline 파일 없음")
        return
    path = Path(baseline["path"])
    if not path.is_file():
        print("HWP baseline 미확인: 원본 파일 없음")
        return
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != baseline["sha256"] or not actual.startswith(baseline["historical_sha256_prefix"]):
        print("경고: HWP 해시가 기준과 다르다. 사람 수정 여부를 확인하고 old를 HWP 본문과 다시 대조해야 한다.")
    else:
        print("HWP baseline unchanged", actual)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--errata", type=Path, default=REPO / "docs/보고서 정오표.md")
    parser.add_argument("--content", type=Path, default=REPORT_ROOT / "content.py")
    parser.add_argument("--numbers", type=Path, default=REPORT_ROOT / "report_numbers.json")
    parser.add_argument("--claims", type=Path, default=REPO / "docs/CLAIMS.md")
    parser.add_argument("--row-numbers", type=Path, default=REPORT_ROOT / "errata_numbers.json")
    parser.add_argument("--keys", type=Path, default=REPORT_ROOT / "measure_keys.json")
    parser.add_argument("--require-claims", action="store_true")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args(argv)
    rows = read_rows(args.errata)
    source = args.content.read_text(encoding="utf-8")
    strings = [node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    numbers = json.loads(args.numbers.read_text(encoding="utf-8"))
    allowed = {normalize(value) for value in numbers["numbers"]}
    entries = {entry["key"]: entry for entry in numbers["entries"]}
    pins = load_pins(args.row_numbers)
    keyed_rows = json.loads(args.keys.read_text(encoding="utf-8"))["rows"] if args.keys.exists() else {}
    phrases = forbidden_from_claims(args.claims, required=args.require_claims or args.final)
    errors = []
    ids = set()
    deltas = Counter({"요약문": 0, "과정": 0, "결과물": 0})
    characters = Counter({"요약문": 0, "과정": 0, "결과물": 0})
    pending = 0
    applied_pending = 0
    delegated = 0
    for unknown in sorted(set(pins) - {row["id"] for row in rows}):
        errors.append(f"{unknown}: row evidence without errata row")
    for row in rows:
        identity = row["id"]
        if identity in ids:
            errors.append(f"{identity}: duplicate id")
        ids.add(identity)
        old = row["old"]
        occurrences = sum(value.count(old) for value in strings) if old else 0
        if occurrences != 1:
            errors.append(f"{identity}: old occurrences {occurrences}, expected 1")
        if row["구역"] not in deltas:
            errors.append(f"{identity}: unknown section")
        else:
            deltas[row["구역"]] += int(row["분량 증감(줄)"])
            if row.get("적용", "apply") == "apply":
                characters[row["구역"]] += len(planned_text(row)) - len(old)
        if row["상태"] not in {"must", "should", "could", "결정 대기", "결정 대기, 도현님 지시로 문구 유지", "사람 확인"}:
            errors.append(f"{identity}: unknown status")
        if not row["근거 키"].strip():
            errors.append(f"{identity}: missing evidence key")
        new = row["new"]
        for column in TEXT_COLUMNS:
            if row.get(column, "해당 없음") == "해당 없음":
                continue
            for phrase in forbidden_hits(row[column], phrases):
                errors.append(f"{identity}: forbidden {column} expression {phrase}")
        applied = row.get("적용", "apply") == "apply"
        keyed = key_numbers(keyed_rows.get(identity, []))
        if applied:
            errors.extend(selection_errors(row, args.final))
        if "g3/v33/results/" in row["근거 키"]:
            delegated += 1
        elif applied and identity not in keyed_rows:
            errors.extend(row_number_errors(row, pins.get(identity, {}), entries))
        if "측정 대기" in new:
            pending += 1
            if applied and "적용" in row:
                applied_pending += 1
                errors.append(f"{identity}: placeholder in applied row")
        elif applied:
            body = re.sub(r"95%\s*CI|95%\s*구간", " ", new)
            for value in sorted(set(checked_numbers(body)) - allowed - set(checked_numbers(old)) - keyed):
                errors.append(f"{identity}: unsupported new number {value}")
    for section, change in deltas.items():
        print(section, "분량 증감(줄)", f"{change:+d}", "글자 증감(selected, 대기 행은 측정 뒤 문구)", f"{characters[section]:+d}")
    print("rows", len(rows), "must", sum(row["상태"] == "must" for row in rows), "measurement_pending", pending, "applied_pending", applied_pending)
    print("row_numbers_pinned", sum(len(value) for value in pins.values()), "delegated_to_check_doc", delegated)
    for error in errors:
        print("ERROR", error)
    report_baseline()
    print("PASS" if not errors else "FAIL", "errors", len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, InvalidOperation) as error:
        print("FAIL", str(error))
        raise SystemExit(1)
