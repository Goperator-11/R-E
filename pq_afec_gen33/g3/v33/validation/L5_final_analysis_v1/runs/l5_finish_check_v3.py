import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(r"C:\dev\pq_afec_gen33")
RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
files = [RUNS / name for name in ("l5_findings_extract_v3.py", "l5_revert_candidate_v2.py", "l5_revert_check_v1.py", "preserve_test_files_v1.py")]
files.append(ROOT / "tests/test_v33_l5_findings.py")
before = {str(path): sha(path) for path in files}
code = "import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0," + repr(str(ROOT)) + ")"
code += "; import runpy; runpy.run_path(" + repr(str(RUNS / "preserve_test_files_v1.py")) + ")"
code += "; import tempfile; from pathlib import Path; f=tempfile.TemporaryDirectory(); p=Path(f.name)/'preserve.bin'; p.write_bytes(b'preserve'); p.unlink(); assert not p.exists(); f.cleanup(); assert Path(f.name).exists()"
code += "; import pytest; raise SystemExit(pytest.main(['tests/test_v33_l5_findings.py','-q','-p','no:cacheprovider']))"
out, log = RUNS / "L5_finish_check_v3.json", RUNS / "L5_finish_check_v3.log"
assert not out.exists() and not log.exists()
timer = time.monotonic()
with log.open("x", encoding="utf-8", newline="\n") as stream:
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
after = {path: sha(path) for path in before}
value = {"exit_code": result.returncode, "unchanged": before == after, "elapsed_seconds": time.monotonic() - timer,
         "source_sha256": before, "source_sha256_after": after, "log_sha256": sha(log), "script_sha256": sha(__file__)}
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
print(log.read_text(encoding="utf-8"))
print(json.dumps(value))
raise SystemExit(result.returncode if before == after else 2)
