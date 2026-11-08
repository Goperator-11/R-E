import argparse
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_errata import checked_numbers, forbidden_from_claims, forbidden_hits, normalize, read_rows

REPO = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"([^.\[\]]+)(\[[^\]]*\])?")
LITERAL_95 = re.compile(r"95%\s*CI|95%\s*구간")


def resolve(doc, key):
    current = doc
    for name, selector in TOKEN.findall(key):
        current = current[name]
        if selector:
            inner = selector[1:-1]
            if inner.lstrip("-").isdigit():
                current = current[int(inner)]
            else:
                conditions = dict(part.split("=") for part in inner.split(","))
                hits = [item for item in current if all(str(item.get(k)) == v for k, v in conditions.items())]
                if len(hits) != 1:
                    raise KeyError(f"{key}: selector {inner} matched {len(hits)}")
                current = hits[0]
    return current


def formatted(value, decimals, scale, sign):
    number = Decimal(repr(float(value) * scale * sign))
    return format(number.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN), "f")


def plain(text):
    return text.replace("−", "-").replace(",", "")


def check(errata, keys_path, numbers_path, claims, root):
    rows = read_rows(errata)
    spec = json.loads(keys_path.read_text(encoding="utf-8"))
    sources = {name: json.loads((root / path).read_text(encoding="utf-8")) for name, path in spec["sources"].items()}
    allowed = {normalize(value) for value in json.loads(numbers_path.read_text(encoding="utf-8"))["numbers"]}
    phrases = forbidden_from_claims(claims)
    errors = []
    checked = 0
    for row in rows:
        identity = row["id"]
        applied = row.get("적용", "apply") == "apply"
        for column in ("측정 못 한 경우 문구", "러너 구현 뒤 미측정 문구"):
            value = row.get(column, "")
            if value and value != "해당 없음":
                for phrase in forbidden_hits(value, phrases):
                    errors.append(f"{identity}: forbidden in {column}: {phrase}")
        if not applied:
            continue
        new = row["new"]
        for phrase in forbidden_hits(new, phrases):
            errors.append(f"{identity}: forbidden new expression {phrase}")
        for marker in ("측정 대기", "pending:", "제출 전 검색 기록을 갱신"):
            if marker in new:
                errors.append(f"{identity}: placeholder {marker}")
        items = spec["rows"].get(identity, [])
        keyed = set()
        for item in items:
            checked += 1
            if item.get("source") == "LITERAL":
                got = plain(item["text"])
            else:
                got = formatted(resolve(sources[item["source"]], item["key"]), item["decimals"], item.get("scale", 1), item.get("sign", 1))
            if normalize(plain(item["text"])) != normalize(got):
                errors.append(f"{identity}: key {item['key']} gives {got}, row says {item['text']}")
            if item["text"] not in new:
                errors.append(f"{identity}: text {item['text']} not in new")
            keyed.add(normalize(plain(item["text"]).lstrip("+")))
        numbers = set(checked_numbers(LITERAL_95.sub(" ", new))) - set(checked_numbers(LITERAL_95.sub(" ", row["old"])))
        pool = keyed | {value.lstrip("+") for value in keyed}
        for value in sorted(numbers - allowed - pool):
            errors.append(f"{identity}: unsupported new number {value}")
    for error in errors:
        print("ERROR", error)
    print("keys checked", checked, "rows", len(rows), "applied", sum(row.get("적용", "apply") == "apply" for row in rows))
    print("PASS" if not errors else "FAIL", "errors", len(errors))
    return 1 if errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--errata", type=Path, default=REPO / "docs/REPORT_ERRATA.md")
    parser.add_argument("--keys", type=Path, default=REPO / "report_repro/measure_keys.json")
    parser.add_argument("--numbers", type=Path, default=REPO / "report_repro/report_numbers.json")
    parser.add_argument("--claims", type=Path, default=REPO / "docs/CLAIMS.md")
    parser.add_argument("--root", type=Path, default=REPO)
    args = parser.parse_args(argv)
    return check(args.errata, args.keys, args.numbers, args.claims, args.root)


if __name__ == "__main__":
    raise SystemExit(main())
