#!/bin/bash
set -euo pipefail
RACE=0
if [ "$#" -gt 0 ]; then
    if [ "$#" -ne 1 ] || [ "$1" != "--race" ]; then
        echo "usage: build_gen33.sh [--race]" >&2
        exit 2
    fi
    RACE=1
fi
if [ -d "$HOME/goroot" ]; then
    export GOROOT="$HOME/goroot"
    export PATH="$GOROOT/bin:$PATH"
fi
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0 GOFLAGS=-mod=readonly GOAMD64=v1 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$HOME/quicbed_gen33"
OUT=/tmp/qamp_gen33
OUT="${QAMP_GEN33_OUT:-$OUT}"
KEEP_STAGES="${GEN33_KEEP_STAGES:-0}"
case "$KEEP_STAGES" in
    ''|*[!0-9]*)
        echo "GEN33_KEEP_STAGES must be a nonnegative integer" >&2
        exit 2
        ;;
esac
GO_SOURCES="policy.go policy3.go policy3_l1.go pfail_table.go hold.go certificate.go observation.go boundary.go decoder_index.go udp_linux.go flight_input.go flight_trace.go flight_shape.go comparison.go inflation.go revisit.go revisit_guard.go"
SEPARATE_PROGRAMS="client.go dataapp.go mlkemcheck.go server.go"
UNSTAGED=""
for f in "$SRC"/*.go; do
    name="$(basename "$f")"
    case " qamp.go $GO_SOURCES $SEPARATE_PROGRAMS " in
        *" $name "*) continue ;;
    esac
    case "$name" in
        qamp_*_test.go|policy_*_test.go|policy3*_test.go) continue ;;
    esac
    UNSTAGED="$UNSTAGED $name"
done
if [ -n "$UNSTAGED" ]; then
    echo "build_gen33.sh does not stage:$UNSTAGED (add to GO_SOURCES or SEPARATE_PROGRAMS; test files must match qamp_*_test.go, policy_*_test.go or policy3*_test.go)" >&2
    exit 2
fi
mkdir -p "$WORK/bin" "$OUT"
WORK_ABS="$(realpath "$WORK")"
STAGE="$(mktemp -d "$WORK_ABS/stage.XXXXXX")"
RECORD="$STAGE/build_record"
export GOTMPDIR="$STAGE/go-work"
mkdir -p "$STAGE/cmd/qamp" "$STAGE/padfechook" "$RECORD" "$GOTMPDIR"
echo "preserved build stage $STAGE"
cp "$SRC/go.mod" "$SRC/go.sum" "$STAGE/"
cp "$SRC/padfechook/"*.go "$SRC/padfechook/go.mod" "$STAGE/padfechook/"
sed 's/\r$//' "$SRC/qamp.go" > "$STAGE/cmd/qamp/main.go"
for f in $GO_SOURCES; do
    sed 's/\r$//' "$SRC/$f" > "$STAGE/cmd/qamp/$f"
done
for t in "$SRC"/qamp_*_test.go "$SRC"/policy_*_test.go "$SRC"/policy3*_test.go; do
    sed 's/\r$//' "$t" > "$STAGE/cmd/qamp/$(basename "$t")"
done
cd "$STAGE"
go vet -work ./cmd/qamp github.com/quic-go/quic-go/padfec-local-hook
echo "gen33 vet passed"
go test -work -count=1 -v ./cmd/qamp github.com/quic-go/quic-go/padfec-local-hook > "$RECORD/go_test.txt" 2>&1 || {
    tail -50 "$RECORD/go_test.txt" >&2
    exit 4
}
if [ "$RACE" -eq 1 ]; then
    CGO_ENABLED=1 go test -work -race -count=1 ./cmd/qamp github.com/quic-go/quic-go/padfec-local-hook > "$RECORD/go_race.txt" 2>&1 || {
        tail -50 "$RECORD/go_race.txt" >&2
        exit 4
    }
    echo "gen33 race passed"
fi
go build -work -trimpath -buildvcs=false -o "$RECORD/qamp" ./cmd/qamp
go version -m "$RECORD/qamp" > "$RECORD/qamp.buildinfo"
echo "gen33 build passed"
{
    cd "$SRC"
    for f in $(ls *.go build.sh build_gen33.sh go.mod go.sum padfechook/*.go padfechook/go.mod | LC_ALL=C sort); do
        printf '%s %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
    done
} | sha256sum | cut -d' ' -f1 > "$RECORD/qamp.srcsha"
(cd "$RECORD" && sha256sum qamp > qamp.sha256)
rm -f "$WORK/bin/go_race.txt"
cp "$RECORD/qamp" "$RECORD/qamp.srcsha" "$RECORD/qamp.sha256" "$RECORD/qamp.buildinfo" "$RECORD/go_test.txt" "$WORK/bin/"
if [ -f "$RECORD/go_race.txt" ]; then
    cp "$RECORD/go_race.txt" "$WORK/bin/"
fi
cp "$WORK/bin/qamp" "$WORK/bin/qamp.srcsha" "$WORK/bin/qamp.sha256" "$WORK/bin/qamp.buildinfo" "$OUT/"
(cd "$OUT" && sha256sum -c --quiet qamp.sha256)
echo "gen33 tests pass $(grep -c '^--- PASS' "$WORK/bin/go_test.txt" || true) skip $(grep -c '^--- SKIP' "$WORK/bin/go_test.txt" || true)"
tail -1 "$WORK/bin/go_test.txt"
echo "development binary $OUT/qamp"
if [ "$KEEP_STAGES" -gt 0 ]; then
    find "$WORK_ABS" -mindepth 1 -maxdepth 1 -type d -name 'stage.??????' ! -path "$STAGE" -printf '%T@ %p\n' \
        | sort -rn | tail -n +"$KEEP_STAGES" | cut -d' ' -f2- \
        | while IFS= read -r old; do
            case "$old" in
                "$WORK_ABS"/stage.??????)
                    rm -rf -- "$old"
                    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) keep=$KEEP_STAGES new=$STAGE pruned=$old" >> "$WORK_ABS/pruned_stages.log"
                    echo "pruned build stage $old"
                    ;;
            esac
        done
fi
