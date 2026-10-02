#!/bin/bash
set -euo pipefail
if [ -d "$HOME/goroot" ]; then
    export GOROOT="$HOME/goroot"
    export PATH="$GOROOT/bin:$PATH"
fi
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0 GOFLAGS=-mod=readonly GOAMD64=v1 GOTOOLCHAIN=local
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$HOME/quicbed_gen32"
OUT=/tmp/qamp_gen32
mkdir -p "$WORK/cmd/qamp" "$WORK/bin" "$OUT"
cp "$SRC/go.mod" "$SRC/go.sum" "$WORK/"
sed 's/\r$//' "$SRC/qamp.go" > "$WORK/cmd/qamp/main.go"
for f in policy.go policy3.go pfail_table.go; do
    sed 's/\r$//' "$SRC/$f" > "$WORK/cmd/qamp/$f"
done
for t in "$SRC"/qamp_*_test.go "$SRC"/policy_*_test.go "$SRC"/policy3*_test.go; do
    sed 's/\r$//' "$t" > "$WORK/cmd/qamp/$(basename "$t")"
done
cd "$WORK"
go vet ./cmd/qamp
echo "gen32 vet passed"
go test -count=1 -v ./cmd/qamp > "$WORK/bin/go_test.txt" 2>&1 || {
    tail -50 "$WORK/bin/go_test.txt" >&2
    exit 4
}
go build -o "$WORK/bin/qamp" ./cmd/qamp
echo "gen32 build passed"
{
    cd "$SRC"
    for f in $(ls *.go build.sh build_gen32.sh go.mod go.sum | LC_ALL=C sort); do
        printf '%s %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
    done
} | sha256sum | cut -d' ' -f1 > "$WORK/bin/qamp.srcsha"
(cd "$WORK/bin" && sha256sum qamp > qamp.sha256)
cp "$WORK/bin/qamp" "$WORK/bin/qamp.srcsha" "$WORK/bin/qamp.sha256" "$OUT/"
(cd "$OUT" && sha256sum -c --quiet qamp.sha256)
echo "gen32 tests $(grep -c '^--- PASS' "$WORK/bin/go_test.txt")"
tail -1 "$WORK/bin/go_test.txt"
echo "development binary $OUT/qamp"
