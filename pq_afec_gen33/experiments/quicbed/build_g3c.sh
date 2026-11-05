#!/bin/bash
echo "Historical builder disabled in gen33; use build_gen33.sh" >&2
exit 2
set -euo pipefail
MODE="${1:-build}"
case "$MODE" in
build | --install-only | --race) ;;
*)
	echo "usage: build_g3c.sh [--install-only | --race]" >&2
	exit 2
	;;
esac
if [ -d "$HOME/goroot" ]; then
	export GOROOT="$HOME/goroot"
	export PATH="$GOROOT/bin:$PATH"
fi
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0
export GOFLAGS=-mod=readonly
export GOAMD64=v1
export GOTOOLCHAIN=local

G2_SHA=d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213
G2_SRC="$HOME/quicbed/bin/qamp"
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$HOME/quicbed_g3c"
OUT=/tmp/qamp_g3

case "$WORK" in
"$HOME/quicbed" | "$HOME/quicbed/"* | "$HOME/quicbed_g3" | "$HOME/quicbed_g3/"* | "$HOME/quicbed_g3b" | "$HOME/quicbed_g3b/"*)
	echo "refusing to build inside the gen-2, stage-0 or stage-2 tree" >&2
	exit 2
	;;
esac

stage() {
	local dst="$1"
	rm -rf "$dst/cmd/qamp"
	mkdir -p "$dst/cmd/qamp"
	cp "$SRC/go.mod" "$SRC/go.sum" "$dst/"
	sed 's/\r$//' "$SRC/qamp.go" >"$dst/cmd/qamp/main.go"
	for f in policy.go policy3.go pfail_table.go; do
		sed 's/\r$//' "$SRC/$f" >"$dst/cmd/qamp/$f"
	done
	for t in "$SRC"/qamp_*_test.go "$SRC"/policy_*_test.go "$SRC"/policy3*_test.go; do
		sed 's/\r$//' "$t" >"$dst/cmd/qamp/$(basename "$t")"
	done
}

if [ "$MODE" != "--install-only" ]; then
	command -v go >/dev/null || {
		echo "go not found (expected \$HOME/goroot/bin/go)" >&2
		exit 2
	}
	for m in go.mod go.sum; do
		if [ ! -f "$SRC/$m" ]; then
			echo "$SRC/$m missing" >&2
			exit 2
		fi
	done
fi

if [ "$MODE" = "--race" ]; then
	command -v gcc >/dev/null || {
		echo "gcc not found; go test -race needs cgo" >&2
		exit 2
	}
	stage "$WORK/race"
	mkdir -p "$WORK/bin"
	cd "$WORK/race"
	echo "== go test -race (CGO_ENABLED=1)"
	CGO_ENABLED=1 go test -race -count=1 -v ./cmd/qamp >"$WORK/bin/go_test_race.txt" 2>&1 || {
		tail -40 "$WORK/bin/go_test_race.txt" >&2
		echo "go test -race failed" >&2
		exit 4
	}
	echo "race pass $(grep -c '^--- PASS' "$WORK/bin/go_test_race.txt") fail $(grep -c '^--- FAIL' "$WORK/bin/go_test_race.txt" || true) data races $(grep -c 'WARNING: DATA RACE' "$WORK/bin/go_test_race.txt" || true)"
	tail -1 "$WORK/bin/go_test_race.txt"
	exit 0
fi

got="$(sha256sum "$G2_SRC" | cut -d' ' -f1)"
if [ "$got" != "$G2_SHA" ]; then
	echo "frozen gen-2 binary $G2_SRC has sha $got, expected $G2_SHA" >&2
	exit 3
fi

if [ "$MODE" = build ]; then
	stage "$WORK"
	mkdir -p "$WORK/bin"
	rm -f "$WORK/bin/qamp" "$WORK/bin/qamp.sha256" "$WORK/bin/qamp.srcsha" "$WORK/bin/go_test.txt"

	cd "$WORK"
	echo "== go version $(go version | cut -d' ' -f3-) GOAMD64=$(go env GOAMD64)"
	echo "== go vet"
	go vet ./cmd/qamp
	echo "== go test"
	go test -count=1 -v ./cmd/qamp >"$WORK/bin/go_test.txt" 2>&1 || {
		tail -40 "$WORK/bin/go_test.txt" >&2
		echo "go test failed; nothing installed" >&2
		exit 4
	}
	echo "pass $(grep -c '^--- PASS' "$WORK/bin/go_test.txt") fail $(grep -c '^--- FAIL' "$WORK/bin/go_test.txt" || true)"
	tail -1 "$WORK/bin/go_test.txt"

	go build -o "$WORK/bin/qamp" ./cmd/qamp

	{
		cd "$SRC"
		for f in $(ls *.go build.sh go.mod go.sum 2>/dev/null | LC_ALL=C sort); do
			printf '%s %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
		done
	} | sha256sum | cut -d' ' -f1 >"$WORK/bin/qamp.srcsha"
	(cd "$WORK/bin" && sha256sum qamp >qamp.sha256)
fi

(cd "$WORK/bin" && sha256sum -c --quiet qamp.sha256) || {
	echo "$WORK/bin/qamp does not match its recorded sha256; rebuild" >&2
	exit 3
}
got="$(cut -d' ' -f1 "$WORK/bin/qamp.sha256")"
if [ "$got" = "$G2_SHA" ]; then
	echo "g3c binary is byte-identical to the frozen gen-2 binary" >&2
	exit 3
fi

mkdir -p "$OUT/g2" "$OUT/g3c"
cp "$WORK/bin/qamp" "$OUT/g3c/qamp.tmp"
mv -f "$OUT/g3c/qamp.tmp" "$OUT/g3c/qamp"
cp "$WORK/bin/qamp.srcsha" "$WORK/bin/qamp.sha256" "$OUT/g3c/"
(cd "$OUT/g3c" && sha256sum -c --quiet qamp.sha256)

if [ ! -f "$OUT/g2/qamp" ] || [ "$(sha256sum "$OUT/g2/qamp" | cut -d' ' -f1)" != "$G2_SHA" ]; then
	cp "$G2_SRC" "$OUT/g2/qamp.tmp"
	mv -f "$OUT/g2/qamp.tmp" "$OUT/g2/qamp"
fi
(cd "$OUT/g2" && sha256sum qamp >qamp.sha256)
got="$(cut -d' ' -f1 "$OUT/g2/qamp.sha256")"
if [ "$got" != "$G2_SHA" ]; then
	echo "copied gen-2 binary has sha $got, expected $G2_SHA" >&2
	exit 3
fi

echo "g3c $(cat "$OUT/g3c/qamp.sha256")"
echo "g3c src $(cat "$OUT/g3c/qamp.srcsha")"
echo "g2 $(cat "$OUT/g2/qamp.sha256")"
