#!/bin/bash
set -e
if [ -d "$HOME/goroot" ]; then
	export GOROOT="$HOME/goroot"
	export PATH="$GOROOT/bin:$PATH"
fi
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export CGO_ENABLED=0
command -v go >/dev/null || {
	echo "go 를 못 찾겠다. Go 1.26.6 이상을 깔고 PATH 에 넣어라" >&2
	echo "(이 기계는 setup.sh 가 \$HOME/goroot 에 풀어 둔 것을 쓴다)" >&2
	exit 2
}

SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$HOME/quicbed"
mkdir -p "$WORK/cmd/server" "$WORK/cmd/client" "$WORK/cmd/dataapp" \
         "$WORK/cmd/qamp" "$WORK/cmd/mlkemcheck" "$WORK/bin"

for m in go.mod go.sum; do
	if [ ! -f "$SRC/$m" ]; then
		echo "$SRC/$m 이 없다. 저장소에서 빠졌다 - 이 파일 없이는" >&2
		echo "quic-go 버전이 고정되지 않아 실측을 재현할 수 없다." >&2
		exit 2
	fi
	cp "$SRC/$m" "$WORK/$m"
done

sed 's/\r$//' "$SRC/server.go" > "$WORK/cmd/server/main.go"
sed 's/\r$//' "$SRC/client.go" > "$WORK/cmd/client/main.go"
sed 's/\r$//' "$SRC/dataapp.go" > "$WORK/cmd/dataapp/main.go"
sed 's/\r$//' "$SRC/qamp.go" > "$WORK/cmd/qamp/main.go"
sed 's/\r$//' "$SRC/policy.go" > "$WORK/cmd/qamp/policy.go"
sed 's/\r$//' "$SRC/pfail_table.go" > "$WORK/cmd/qamp/pfail_table.go"
sed 's/\r$//' "$SRC/mlkemcheck.go" > "$WORK/cmd/mlkemcheck/main.go"

cd "$WORK"
export GOFLAGS=-mod=readonly
go build -o "$WORK/bin/qserver" ./cmd/server
go build -o "$WORK/bin/qclient" ./cmd/client
go build -o "$WORK/bin/qdata" ./cmd/dataapp
CGO_ENABLED=0 go build -o "$WORK/bin/qamp" ./cmd/qamp
CGO_ENABLED=0 go build -o "$WORK/bin/mlkemcheck" ./cmd/mlkemcheck

{
	cd "$SRC"
	for f in $(ls *.go build.sh go.mod go.sum 2>/dev/null | LC_ALL=C sort); do
		printf '%s %s\n' "$f" "$(sha256sum "$f" | cut -d' ' -f1)"
	done
} | sha256sum | cut -d' ' -f1 > "$WORK/bin/qamp.srcsha"
cd "$WORK"

cp "$WORK/bin/qamp" /tmp/qamp
cp "$WORK/bin/mlkemcheck" /tmp/mlkemcheck
cp "$WORK/bin/qamp.srcsha" /tmp/qamp.srcsha
echo "built:"
ls -la "$WORK/bin"
echo "소스 지문: $(cat "$WORK/bin/qamp.srcsha")"
