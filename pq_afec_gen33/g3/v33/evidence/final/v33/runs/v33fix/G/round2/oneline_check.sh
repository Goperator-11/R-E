#!/bin/bash
set -uo pipefail
B=/home/scien/v33fix_tmp/G/oneline
rm -rf "$B"; mkdir -p "$B/tests" "$B/experiments"
cp /mnt/c/dev/pq_afec_gen33/tests/test_gen32_build_staging.py "$B/tests/"
cp -r /mnt/c/dev/pq_afec_gen33/experiments/quicbed "$B/experiments/"
python3 -B - "$B/experiments/quicbed/build_gen33.sh" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
t = p.read_text()
old = 'OUT=/tmp/qamp_gen33\nOUT="${QAMP_GEN33_OUT:-$OUT}"\n'
assert t.count(old) == 1
p.write_text(t.replace(old, 'OUT="${QAMP_GEN33_OUT:-/tmp/qamp_gen33}"\n'))
PY
grep -n "^OUT" "$B/experiments/quicbed/build_gen33.sh"
cd /tmp && QAMP_GEN33_OUT="$B/out" PYTHONDONTWRITEBYTECODE=1 python3 -B "$B/tests/test_gen32_build_staging.py" 2>&1 | grep -E "^(FAIL|ERROR|OK|Ran)|Error:" | head -5
ls -d /tmp/qamp_gen33 2>&1
rm -rf "$B"
