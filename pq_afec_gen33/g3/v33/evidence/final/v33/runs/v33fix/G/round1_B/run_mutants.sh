#!/bin/bash
set -uo pipefail
source /mnt/c/Users/scien/AppData/Local/Temp/claude/C--Users-scien/98dad099-940c-4208-8359-61078035dc93/scratchpad/v33fix/B/goenv.sh
OUTD="$S/out"
mkdir -p "$OUTD"
declare -A RUNS=(
    [F1]='^(TestFeedbackVersionTwoIsReadableByFrozenClients|TestFeedbackVersionTwoTruncationForFrozenClients|TestFeedbackVersionKeepsGen33Arrivals)$'
    [F2]='^TestConnLog'
    [F4]='^TestRunDefaultsMatchCostModelLayout$'
    [F5]='^TestComparisonDropParityLedger$'
    [BE6]='^TestPreservedTempDirIsRemovedUnlessRequested$'
)
for m in F1 F2 F4 F5 BE6; do
    OVER="$T/overlay_$m"
    rm -rf "$OVER"
    mkdir -p "$OVER"
    cp "$S"/src_mine/* "$OVER/"
    cp "$S/mut_$m"/* "$OVER/"
    STAGE="$T/stage_mut_$m"
    bash "$S/stage.sh" "$S/src_head" "$OVER" "$STAGE" > /dev/null
    cd "$STAGE"
    CGO_ENABLED=0 go test -count=1 -v -run "${RUNS[$m]}" ./cmd/qamp > "$OUTD/mut_$m.txt" 2>&1
    rc=$?
    echo "== $m rc=$rc pass=$(grep -c -- '--- PASS' "$OUTD/mut_$m.txt") fail=$(grep -c -- '--- FAIL' "$OUTD/mut_$m.txt")"
    grep -E -- '--- FAIL|_test.go:[0-9]+:' "$OUTD/mut_$m.txt" | head -8
    cd /
    rm -rf "$STAGE" "$OVER"
done
