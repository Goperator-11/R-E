import sys
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding="utf-8")
import hashlib
import json
from pathlib import Path
import subprocess
import time

root=Path(r"C:\dev\pq_afec_gen33")
runs=Path(r"C:\dev\codex_handoff\v33\runs")
paths=[root/"experiments/v33"/n for n in ("oracle_m1.py","bench_oracles_m1.py","bench_action_pool_m1.py",
        "bench_m1_family.py","bench_m1_report.py","m1_pool_validation.py","worldsim_m1.py","world_receiver_m1.py")]
paths += [root/"tests/test_v33_m1_mc.py",root/"docs/M1_mc_contract.md"]
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
start=time.monotonic()
log=runs/"M1_mc_tests_02.log"
command=[sys.executable,"-I","-B","-c","import sys;sys.dont_write_bytecode=True;sys.path.insert(0,sys.argv[1]);import pytest;raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','tests/test_v33_m1_mc.py']))",str(root)]
with log.open("xb") as f:
    result=subprocess.run(command,cwd=root,stdout=f,stderr=subprocess.STDOUT)
record={"exit_code":result.returncode,"source_sha256":before,"command":command,"elapsed_seconds":time.monotonic()-start,
        "log_sha256":hashlib.sha256(log.read_bytes()).hexdigest(),"unchanged":before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
with (runs/"M1_mc_tests_02.json").open("x",encoding="utf-8",newline="\n") as f:
    json.dump(record,f,ensure_ascii=False,indent=2);f.write("\n")
print(log.read_text(encoding="utf-8"))
assert record["exit_code"]==0 and record["unchanged"]
