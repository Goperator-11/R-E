import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics


class EvidenceError(Exception):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def default_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "padfec3/layout.py").is_file():
            return parent
    return Path(r"C:\dev\pq_afec_gen33")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def average(values):
    values = list(values)
    return statistics.mean(values) if values else None


def numeric(values):
    values = list(values)
    present = [x for x in values if isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)]
    return {"count": len(values), "numeric_count": len(present), "missing_count": len(values) - len(present), "min": min(present) if present else None, "max": max(present) if present else None, "mean": average(present), "median": statistics.median(present) if present else None}


def histogram(values):
    counts = {}
    for value in values:
        key = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def comparison(actual, expected, definition):
    delta = actual - expected if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual is not None else None
    return {"actual": actual, "expected_from_source": expected, "difference": delta, "exact_match": actual == expected, "definition": definition}


def segments(units):
    for unit in units:
        value = unit["val"]
        for segment in value["segments"]:
            yield unit, value, segment


def rows(units, arm=None):
    for unit, value, segment in segments(units):
        if arm is not None and segment["arm"] != arm:
            continue
        for row in segment["rows"]:
            yield unit, value, segment, row


class EvidenceContext:
    def __init__(self, args):
        self.root = Path(args.root).resolve()
        self.journals = Path(args.journals).resolve()
        self.out = Path(args.out).resolve()
        self.inputs = []
        if not (self.root / "padfec3/layout.py").is_file():
            raise EvidenceError("gen33 root에서 padfec3/layout.py를 찾지 못했다", {"root": str(self.root)})
        if self.root.name != "pq_afec_gen33":
            raise EvidenceError("이 초안의 정책 import는 pq_afec_gen33에 한정한다", {"root": str(self.root)})
        sys.path.insert(0, str(self.root))

    def load(self, name):
        path = (self.journals / name).resolve()
        if not path.is_relative_to(self.journals):
            raise EvidenceError("저널 경로가 입력 폴더를 벗어났다", {"path": str(path)})
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        diagnostic = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "fingerprints": [], "duplicate_records": [], "ignored_torn_last_line": None, "schema_errors": []}
        self.inputs.append(diagnostic)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise EvidenceError("읽는 동안 원자료가 바뀌었다", diagnostic)
        lines = [(number, line) for number, line in enumerate(raw.splitlines(), 1) if line.strip()]
        fingerprints = set()
        by_key = {}
        line_by_key = {}
        for position, (number, line) in enumerate(lines):
            try:
                unit = json.loads(line)
            except (ValueError, UnicodeDecodeError) as exc:
                if position == len(lines) - 1:
                    diagnostic["ignored_torn_last_line"] = {"line": number, "reason": str(exc)}
                    continue
                raise EvidenceError("마지막 줄이 아닌 위치의 JSON 손상", {**diagnostic, "line": number, "error": str(exc)}) from exc
            valid = isinstance(unit, dict) and isinstance(unit.get("key"), str) and isinstance(unit.get("fp"), str) and isinstance(unit.get("val"), dict)
            value = unit.get("val") if isinstance(unit, dict) else None
            valid = valid and isinstance(value.get("segments"), list) and isinstance(value.get("block"), int)
            if not valid:
                diagnostic["schema_errors"].append(number)
                continue
            for segment in value["segments"]:
                if not isinstance(segment, dict) or not isinstance(segment.get("arm"), str) or not isinstance(segment.get("rows"), list) or any(not isinstance(row, dict) for row in segment.get("rows", [])):
                    diagnostic["schema_errors"].append(number)
                    valid = False
                    break
            if not valid:
                continue
            fingerprint = unit["fp"]
            fingerprints.add(fingerprint)
            key = (fingerprint, unit["key"])
            if key in by_key:
                diagnostic["duplicate_records"].append({"key": unit["key"], "fingerprint": fingerprint, "discarded_line": line_by_key[key], "kept_line": number})
            by_key[key] = unit
            line_by_key[key] = number
        diagnostic["fingerprints"] = sorted(fingerprints)
        diagnostic["nonempty_lines"] = len(lines)
        diagnostic["selected_units"] = len(by_key)
        if diagnostic["schema_errors"]:
            raise EvidenceError("원자료 unit 형식 오류", diagnostic)
        if len(fingerprints) != 1:
            raise EvidenceError("원자료 fingerprint가 한 개가 아니다. 혼합 자료를 합산하지 않는다", diagnostic)
        return sorted(by_key.values(), key=lambda unit: (unit["val"]["block"], unit["key"]))

    def provenance(self):
        source_paths = list(Path(__file__).resolve().parent.glob("*.py"))
        source_paths += [self.root / p for p in ("padfec3/layout.py", "padfec3/learn3.py", "padfec3/decide3.py", "padfec/policy.py", "padfec/quantum.py", "padfec/table.py")]
        return {str(p): sha256(p) for p in sorted(set(source_paths)) if p.is_file()}

    def write(self, report):
        allowed = [self.root]
        if sys.platform == "win32":
            allowed.append(Path(r"C:\dev\codex_handoff\v33").resolve())
        else:
            allowed.append(Path("/mnt/c/dev/codex_handoff/v33").resolve())
        if not any(self.out.is_relative_to(root) for root in allowed):
            raise EvidenceError("출력은 gen33 또는 v33 루프 폴더 안이어야 한다", {"out": str(self.out)})
        if self.out.suffix.lower() != ".json" or self.out.is_relative_to(self.journals):
            raise EvidenceError("출력은 원자료 밖의 JSON 파일이어야 한다", {"out": str(self.out)})
        envelope = {"schema": "padfec.v33.a0/1", "generated_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"), "root": str(self.root), "inputs": self.inputs, "source_sha256": self.provenance(), **report}
        self.out.parent.mkdir(parents=True, exist_ok=True)
        with self.out.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(envelope, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"out": str(self.out), "status": envelope.get("status"), "sources": len(self.inputs)}, ensure_ascii=False))


def run(analyze):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--journal-root", "--journals", dest="journals", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    context = EvidenceContext(args)
    try:
        result = analyze(context)
        result.setdefault("status", "calculated")
        context.write(result)
    except EvidenceError as exc:
        context.write({"status": "error", "error": str(exc), "diagnostics": exc.diagnostics})
        raise SystemExit(2) from exc
