#!/bin/bash
set -u
cd /mnt/c/dev/pq_afec_gen31
python3 -V
python3 -B -m unittest -q tests.test_p21_gencompare >/tmp/r31_unit.txt 2>&1
echo "unit_rc=$?"
tail -4 /tmp/r31_unit.txt
python3 -B experiments/p21_gencompare.py --dry-run >/tmp/r31_dry.txt 2>&1
echo "dry_rc=$?"
grep -n "schedule run1\|schedule smoke\|total run\|development data\|excluded before\|binary problems\|build processes\|other measurements" /tmp/r31_dry.txt
