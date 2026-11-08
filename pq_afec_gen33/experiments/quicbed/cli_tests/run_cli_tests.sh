#!/bin/bash
set -euo pipefail
if [ -d "$HOME/goroot" ]; then
    export GOROOT="$HOME/goroot"
    export PATH="$GOROOT/bin:$PATH"
fi
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0 GOFLAGS=-mod=readonly GOAMD64=v1 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(dirname "$HERE")"
STAGE="$(mktemp -d)"
trap 'chmod -R u+w "$STAGE" 2>/dev/null; rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/cmd/qamp" "$STAGE/padfechook"
cp "$SRC/go.mod" "$SRC/go.sum" "$STAGE/"
cp "$SRC/padfechook/"*.go "$SRC/padfechook/go.mod" "$STAGE/padfechook/"
sed 's/\r$//' "$SRC/qamp.go" > "$STAGE/cmd/qamp/main.go"
GO_SOURCES="$(grep '^GO_SOURCES=' "$SRC/build_gen33.sh" | sed 's/^GO_SOURCES="//; s/"$//; s/\r$//')"
for f in $GO_SOURCES; do
    sed 's/\r$//' "$SRC/$f" > "$STAGE/cmd/qamp/$f"
done
for t in "$SRC"/qamp_*_test.go "$SRC"/policy_*_test.go "$SRC"/policy3*_test.go "$HERE"/*_test.go; do
    sed 's/\r$//' "$t" > "$STAGE/cmd/qamp/$(basename "$t")"
done
cd "$STAGE"
go test -count=1 -v -run '^(TestCLIAuto3|TestFecMagicAtBodyNeedsInitialWithEmptyToken$|TestP3GradeCutoffsMatchHandCalculation$)' ./cmd/qamp
