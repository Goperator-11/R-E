#!/bin/bash
set -e

if [ ! -x "$HOME/goroot/bin/go" ] && [ -x "$HOME/go/bin/go" ]; then
  echo "moving ~/go -> ~/goroot (GOPATH collision)"
  mv "$HOME/go" "$HOME/goroot"
fi

export GOROOT="$HOME/goroot"
export GOPATH="$HOME/gopath"
export GOCACHE="$HOME/.cache/go-build"
export PATH="$GOROOT/bin:$GOPATH/bin:$PATH"

echo "== go =="
go version
go env GOROOT GOPATH | tr '\n' ' '
echo ""

WORK="$HOME/quicbed"
mkdir -p "$WORK"
cd "$WORK"

SRC="$(cd "$(dirname "$0")" && pwd)"
for m in go.mod go.sum; do
  [ -f "$SRC/$m" ] || { echo "$SRC/$m 이 없다 - 저장소에서 빠졌다" >&2; exit 2; }
  cp "$SRC/$m" "$WORK/$m"
done

echo "== fetching pinned deps =="
GOFLAGS=-mod=readonly go mod download

echo "== module =="
cat go.mod
echo "OK"
