#!/bin/bash
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="/tmp/quicbed_build"
rm -rf "$WORK"
mkdir -p "$WORK/cmd/server" "$WORK/cmd/client" "$WORK/cmd/dataapp" "$WORK/cmd/qamp" "$WORK/cmd/mlkemcheck"
sed 's/\r$//' "$SRC/server.go"      > "$WORK/cmd/server/main.go"
sed 's/\r$//' "$SRC/client.go"      > "$WORK/cmd/client/main.go"
sed 's/\r$//' "$SRC/dataapp.go"     > "$WORK/cmd/dataapp/main.go"
sed 's/\r$//' "$SRC/qamp.go"        > "$WORK/cmd/qamp/main.go"
sed 's/\r$//' "$SRC/policy.go"      > "$WORK/cmd/qamp/policy.go"
sed 's/\r$//' "$SRC/pfail_table.go" > "$WORK/cmd/qamp/pfail_table.go"
sed 's/\r$//' "$SRC/mlkemcheck.go"  > "$WORK/cmd/mlkemcheck/main.go"
cd "$WORK"
go mod init quicbed >/dev/null 2>&1 || true
go mod tidy 2>&1 | tail -2
CGO_ENABLED=0 go build -o "$WORK/bin/qamp"       ./cmd/qamp
CGO_ENABLED=0 go build -o "$WORK/bin/mlkemcheck" ./cmd/mlkemcheck
cp "$WORK/bin/qamp" /tmp/qamp
cp "$WORK/bin/mlkemcheck" /tmp/mlkemcheck
echo "built:"; ls -la "$WORK/bin"
