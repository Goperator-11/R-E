#!/bin/bash
set -uo pipefail
export GOROOT="$HOME/goroot"
export PATH="$GOROOT/bin:$PATH"
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0
export GOFLAGS=-mod=readonly
G3SRC=/mnt/c/dev/pq_afec_gen3/experiments/quicbed
G2SRC=/mnt/c/dev/pq_afec/experiments/quicbed
RV=/mnt/c/dev/pq_afec_gen3/_review
BASE="$HOME/quicbed_g3/_review"
rm -rf "$BASE"
for tree in g2 g3; do
	mkdir -p "$BASE/$tree/cmd/qamp"
	if [ $tree = g2 ]; then S=$G2SRC; else S=$G3SRC; fi
	cp "$S/go.mod" "$S/go.sum" "$BASE/$tree/"
	sed 's/\r$//' "$S/qamp.go" > "$BASE/$tree/cmd/qamp/main.go"
	sed 's/\r$//' "$S/policy.go" > "$BASE/$tree/cmd/qamp/policy.go"
	sed 's/\r$//' "$S/pfail_table.go" > "$BASE/$tree/cmd/qamp/pfail_table.go"
	for t in "$S"/qamp_*_test.go "$S"/policy_*_test.go; do
		sed 's/\r$//' "$t" > "$BASE/$tree/cmd/qamp/$(basename "$t")"
	done
	sed 's/\r$//' "$RV/rv_common_test.go" > "$BASE/$tree/cmd/qamp/rv_common_test.go"
	if [ $tree = g3 ]; then
		sed 's/\r$//' "$RV/rv_g3_test.go" > "$BASE/$tree/cmd/qamp/rv_g3_test.go"
	fi
done
echo "== sha check"
sha256sum "$G2SRC/qamp.go" "$G3SRC/qamp.go"
echo "== g2 digests"
(cd "$BASE/g2" && go test -count=1 -run 'TestRv' -v ./cmd/qamp 2>&1 | grep -E 'RVDIGEST|^(--- |ok|FAIL|PASS)')
echo "== g3 vet"
(cd "$BASE/g3" && go vet ./cmd/qamp && echo vet ok)
echo "== g3 full test"
(cd "$BASE/g3" && go test -count=1 -v ./cmd/qamp > "$BASE/g3_test.txt" 2>&1; echo "rc $?")
grep -E 'RVDIGEST|loss patterns|runs$|first lead' "$BASE/g3_test.txt"
echo "pass $(grep -c '^--- PASS' "$BASE/g3_test.txt") fail $(grep -c '^--- FAIL' "$BASE/g3_test.txt")"
grep -E '^--- FAIL' -A 5 "$BASE/g3_test.txt" | head -40
tail -2 "$BASE/g3_test.txt"
