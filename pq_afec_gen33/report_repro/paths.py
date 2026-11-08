import json
import os
from pathlib import Path

REPORT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("REPORT_DATA_ROOT") or REPORT_ROOT.parent.parent).expanduser().resolve()
DATA_DIR = REPORT_ROOT / "data"
SOURCE_PATHS = json.loads((REPORT_ROOT / "source_paths.json").read_text(encoding="utf-8"))


def source_path(key):
    candidates = []
    for relative in SOURCE_PATHS[key]:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Source paths must be relative: " + key)
        candidates.append(DATA_ROOT / path)
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("Missing source " + key + ": " + ", ".join(str(path) for path in candidates)
                            + ". REPORT_DATA_ROOT must point to the folder that holds the sources listed in report_repro/SOURCES.md.")


def source_reference(key):
    return source_path(key).relative_to(DATA_ROOT).as_posix()
