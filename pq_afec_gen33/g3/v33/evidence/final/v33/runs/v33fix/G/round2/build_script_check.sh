#!/bin/bash
set -uo pipefail
S=/mnt/c/Users/scien/AppData/Local/Temp/claude/C--Users-scien/98dad099-940c-4208-8359-61078035dc93/scratchpad/v33fix2/G-testbed/v2
REPO=/mnt/c/dev/pq_afec_gen33
BASE=/home/scien/v33fix_tmp/G/bcheck
OUTD=$S/out/build_script
rm -rf "$BASE" "$OUTD"; mkdir -p "$BASE" "$OUTD"
export PATH=/home/scien/goroot/bin:/usr/local/bin:/usr/bin:/bin
export GOROOT=/home/scien/goroot GOPATH=/home/scien/gopath GOMODCACHE=/home/scien/gopath/pkg/mod GOCACHE=/home/scien/v33fix_tmp/G/gocache
export TMPDIR=/home/scien/v33fix_tmp/G/tmp
mksrc() {
    rm -rf "$BASE/src"; mkdir -p "$BASE/src"
    cp -r "$REPO/experiments/quicbed/." "$BASE/src/"
    for p in "$@"; do (cd "$BASE/src" && patch -p3 --quiet < "$p"); done
}
mkhome() {
    rm -rf "$BASE/home" "$BASE/out"; mkdir -p "$BASE/home/quicbed_gen33/bin"
    for i in 1 2 3 4 5 6 7; do
        d="$BASE/home/quicbed_gen33/stage.fake0$i"
        mkdir -p "$d/build_record"; echo "fake $i" > "$d/build_record/marker"
        touch -d "2026-10-0$i 12:00" "$d"
    done
    mkdir -p "$BASE/home/quicbed_gen33/stage.keepme_not_a_stage"
    touch -d "2026-09-01 12:00" "$BASE/home/quicbed_gen33/stage.keepme_not_a_stage"
    echo "stale race record" > "$BASE/home/quicbed_gen33/bin/go_race.txt"
}
state() {
    local tag="$1" rc="$2"
    {
        echo "== $tag rc=$rc"
        echo "stages: $(cd "$BASE/home/quicbed_gen33" && ls -d stage.* | tr '\n' ' ')"
        echo "stage_count $(cd "$BASE/home/quicbed_gen33" && ls -d stage.* | wc -l)"
        echo "bin: $(ls "$BASE/home/quicbed_gen33/bin" | tr '\n' ' ')"
        if [ -f "$BASE/home/quicbed_gen33/pruned_stages.log" ]; then echo "pruned_log_lines $(wc -l < "$BASE/home/quicbed_gen33/pruned_stages.log")"; sed 's/^[0-9TZ:-]* /<time> /' "$BASE/home/quicbed_gen33/pruned_stages.log"; else echo "pruned_log none"; fi
        grep -E "^(preserved|gen33|pruned|development|build_gen33|GEN33)|^ok|^FAIL" "$OUTD/$tag.log" | sed "s|$BASE|<BASE>|g"
    } | tee -a "$OUTD/summary.txt"
}
run() {
    local tag="$1"; shift
    (cd "$BASE" && env HOME="$BASE/home" QAMP_GEN33_OUT="$BASE/out" "$@" bash "$BASE/src/build_gen33.sh" > "$OUTD/$tag.log" 2>&1); local rc=$?
    state "$tag" "$rc"
}
: > "$OUTD/summary.txt"
FIX=$S/comparison_fixture_original_first.patch
mksrc
mkhome; run A_default_tests_fail
mkhome; run B_keep3_tests_fail GEN33_KEEP_STAGES=3
mkhome; run F_keep_not_number GEN33_KEEP_STAGES=abc
mksrc; echo "package main" > "$BASE/src/extra_unlisted.go"
mkhome; run E_unlisted_source
mksrc "$FIX"
mkhome; run C_default_success
mkhome; run D_keep3_success GEN33_KEEP_STAGES=3
echo "real_home_stage_count $(ls -d /home/scien/quicbed_gen33/stage.* | wc -l)" | tee -a "$OUTD/summary.txt"
echo "tmp_qamp_gen33 $(ls -d /tmp/qamp_gen33 2>&1)" | tee -a "$OUTD/summary.txt"
