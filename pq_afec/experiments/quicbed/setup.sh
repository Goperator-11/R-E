#!/bin/bash
# Set up a real local QUIC testbed: Go toolchain + quic-go.
# No sudo. Everything lives under $HOME.
set -e

# The tarball extracts to ~/go, which collides with Go's default GOPATH.
# Move it to ~/goroot once, then always use that.
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

if [ ! -f go.mod ]; then
  go mod init pqafec/quicbed
fi

echo "== fetching quic-go =="
go get github.com/quic-go/quic-go@latest
go mod tidy

echo "== module =="
cat go.mod
echo "OK"
