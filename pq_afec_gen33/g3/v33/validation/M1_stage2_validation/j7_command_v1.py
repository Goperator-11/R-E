import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ROOT = Path(r"C:\dev\pq_afec_gen33")
label, command = sys.argv[1], sys.argv[2:]
assert label.replace("_", "").isalnum() and command
assert not (RUNS.parent / "state/MEASURE_LOCK.json").exists()
out, log, start = (RUNS / (label + suffix) for suffix in (".json", ".log", ".started.json"))
assert not any(p.exists() for p in (out, log, start))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sources = sorted((ROOT / "experiments/quicbed").glob("*.go"))
sources += [ROOT / name for name in ("experiments/quicbed/build_gen33.sh", "experiments/quicbed/go.mod", "experiments/quicbed/go.sum", "experiments/gate_v3_parity.py", "g3/policy3_reference_gen.py")]
sources += [p for name in ("afec", "padfec", "padfec3") for p in (ROOT / name).glob("*.py")]
before = {str(p): sha(p) for p in sources}
value = {"command": command, "started_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), "source_sha256": before, "script_sha256": sha(Path(__file__))}
timer = time.monotonic()
with log.open("x", encoding="utf-8", newline="\n") as stream:
    process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    with start.open("x", encoding="utf-8", newline="\n") as started:
        json.dump({**value, "pid": process.pid}, started, ensure_ascii=False, indent=2)
        started.write("\n")
    code = process.wait()
after = {str(p): sha(p) for p in sources}
value.update(exit_code=code, elapsed_seconds=time.monotonic() - timer, ended_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), unchanged=before == after, source_sha256_after=after, log_sha256=sha(log))
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(log.read_text(encoding="utf-8", errors="replace")[-5000:])
print(json.dumps({k: value[k] for k in ("exit_code", "elapsed_seconds", "unchanged", "log_sha256")}))
raise SystemExit(code if before == after else 2)
