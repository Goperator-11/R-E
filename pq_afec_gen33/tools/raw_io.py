import gzip
import io
import json
from pathlib import Path


def kind(path):
    name = str(path)
    for suffix, value in ((".jsonl.gz", "jsonl"), (".json.gz", "json")):
        if name.endswith(suffix):
            return value
    raise ValueError("new raw data requires .json.gz or .jsonl.gz")


def write(path, value):
    mode = kind(path)
    with Path(path).open("xb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream:
                rows = value if mode == "jsonl" else [value]
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def read(path):
    mode = kind(path)
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        if mode == "json":
            return json.load(stream)
        return [json.loads(line) for line in stream]


def iter_rows(path):
    if kind(path) != "jsonl":
        raise ValueError("streaming rows requires .jsonl.gz")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)
