import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

BASE = Path(r"C:\dev\codex_handoff\v33\runs\preserved_test_files_v1").resolve()
BASE.mkdir(parents=True, exist_ok=True)
ROOTS = (Path(r"C:\dev\codex_handoff\v33\runs").resolve(), Path(r"C:\dev\pq_afec_gen33").resolve())
BOOTSTRAP = r"C:\dev\codex_handoff\v33\runs\preserve_test_files_v1.py"
tempfile.tempdir = str(BASE)


class PreservedTemporaryDirectory:
    def __init__(self, suffix=None, prefix=None, dir=None, **kwargs):
        parent = BASE if dir is None else Path(dir).resolve()
        if not any(parent.is_relative_to(root) for root in ROOTS):
            raise ValueError("test fixture directory outside authorized roots")
        self.name = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=parent)

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        return False

    def cleanup(self):
        pass


def preserve(path, *args, **kwargs):
    if kwargs.get("dir_fd") is not None:
        raise ValueError("relative descriptor deletion is not supported by preservation adapter")
    source = Path(path).resolve(strict=True)
    if not any(source.is_relative_to(root) for root in ROOTS) or source in ROOTS or source == BASE:
        raise ValueError("refusing test removal outside a fixture")
    archive = (BASE / "removed" / uuid.uuid4().hex).resolve()
    if not archive.is_relative_to(BASE):
        raise ValueError("invalid archive target")
    archive.parent.mkdir(parents=True, exist_ok=True)
    source.rename(archive)
    with (BASE / ("archive_" + str(os.getpid()) + ".jsonl")).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"source": str(source), "preserved": str(archive)}) + "\n")


original_popen = subprocess.Popen


class PreservedPopen(original_popen):
    def __init__(self, args, *other, **kwargs):
        if isinstance(args, (list, tuple)) and "-c" in args:
            index = args.index("-c") + 1
            if index < len(args) and "pytest" in args[index] and BOOTSTRAP not in args[index]:
                args = list(args)
                args[index] = "import runpy; runpy.run_path(" + repr(BOOTSTRAP) + "); " + args[index]
        super().__init__(args, *other, **kwargs)


tempfile.TemporaryDirectory = PreservedTemporaryDirectory
os.unlink = preserve
os.remove = preserve
shutil.rmtree = preserve
subprocess.Popen = PreservedPopen
