#!/bin/bash
echo "Historical builder disabled in gen33; use build_gen33.sh" >&2
exit 2
set -euo pipefail
MODE="${1:-build}"
case "$MODE" in
build | --install-only) ;;
*)
	echo "usage: build_g3.sh [--install-only]" >&2
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

G2_SHA=d98b05d73f44774ad622ab1c4993526cac58957b22310fc61122d7bd44964213
G2_SRC="$HOME/quicbed/bin/qamp"
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$HOME/quicbed_g3"
OUT=/tmp/qamp_g3

case "$WORK" in
"$HOME/quicbed" | "$HOME/quicbed/"*)
	echo "refusing to build inside the gen-2 tree" >&2
	exit 2
	;;
esac

got="$(sha256sum "$G2_SRC" | cut -d' ' -f1)"
if [ "$got" != "$G2_SHA" ]; then
	echo "frozen gen-2 binary $G2_SRC has sha $got, expected $G2_SHA" >&2
	exit 3
fi

if [ "$MODE" = build ]; then
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

	rm -rf "$WORK/cmd/qamp"
	mkdir -p "$WORK/cmd/qamp" "$WORK/bin"
	rm -f "$WORK/bin/qamp" "$WORK/bin/qamp.sha256" "$WORK/bin/qamp.srcsha"
	cp "$SRC/go.mod" "$SRC/go.sum" "$WORK/"
	sed 's/\r$//' "$SRC/qamp.go" > "$WORK/cmd/qamp/main.go"
	sed 's/\r$//' "$SRC/policy.go" > "$WORK/cmd/qamp/policy.go"
	sed 's/\r$//' "$SRC/pfail_table.go" > "$WORK/cmd/qamp/pfail_table.go"
	for t in "$SRC"/qamp_*_test.go "$SRC"/policy_*_test.go; do
		sed 's/\r$//' "$t" > "$WORK/cmd/qamp/$(basename "$t")"
	done

	cd "$WORK"
	echo "== go vet"
	go vet ./cmd/qamp
	echo "== go test"
	go test -count=1 -v ./cmd/qamp > "$WORK/bin/go_test.txt" 2>&1 || {
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
	} | sha256sum | cut -d' ' -f1 > "$WORK/bin/qamp.srcsha"
	(cd "$WORK/bin" && sha256sum qamp > qamp.sha256)
fi

(cd "$WORK/bin" && sha256sum -c --quiet qamp.sha256) || {
	echo "$WORK/bin/qamp does not match its recorded sha256; rebuild" >&2
	exit 3
}

mkdir -p "$OUT/g2" "$OUT/g3"
cp "$WORK/bin/qamp" "$OUT/g3/qamp.tmp"
mv -f "$OUT/g3/qamp.tmp" "$OUT/g3/qamp"
cp "$WORK/bin/qamp.srcsha" "$WORK/bin/qamp.sha256" "$OUT/g3/"
(cd "$OUT/g3" && sha256sum -c --quiet qamp.sha256)

cp "$G2_SRC" "$OUT/g2/qamp.tmp"
mv -f "$OUT/g2/qamp.tmp" "$OUT/g2/qamp"
(cd "$OUT/g2" && sha256sum qamp > qamp.sha256)
got="$(cut -d' ' -f1 "$OUT/g2/qamp.sha256")"
if [ "$got" != "$G2_SHA" ]; then
	echo "copied gen-2 binary has sha $got, expected $G2_SHA" >&2
	exit 3
fi

echo "g3 $(cat "$OUT/g3/qamp.sha256")"
echo "g3 src $(cat "$OUT/g3/qamp.srcsha")"
echo "g2 $(cat "$OUT/g2/qamp.sha256")"
