#!/bin/bash
# 문서 6절 함정: CGO_ENABLED=0 은 필수다(conda 가 CC 를 미설치 컴파일러로
# 지정해 두면 빌드가 실패한다). 우리 환경에도 그대로 적용해 둔다.
set -e
export GOROOT="$HOME/goroot"
export GOPATH="$HOME/gopath"
export GOCACHE="$HOME/.cache/go-build"
export PATH="$GOROOT/bin:$PATH"

SRC=/mnt/c/dev/pq_afec/experiments/quicbed
WORK="$HOME/quicbed"
mkdir -p "$WORK/cmd/server" "$WORK/cmd/client" "$WORK/cmd/dataapp" "$WORK/cmd/qamp" "$WORK/cmd/mlkemcheck"

# strip CRLF - the sources live on a Windows filesystem
sed 's/\r$//' "$SRC/server.go" > "$WORK/cmd/server/main.go"
sed 's/\r$//' "$SRC/client.go" > "$WORK/cmd/client/main.go"
sed 's/\r$//' "$SRC/dataapp.go" > "$WORK/cmd/dataapp/main.go"
sed 's/\r$//' "$SRC/qamp.go" > "$WORK/cmd/qamp/main.go"
sed 's/\r$//' "$SRC/policy.go" > "$WORK/cmd/qamp/policy.go"
sed 's/\r$//' "$SRC/pfail_table.go" > "$WORK/cmd/qamp/pfail_table.go"
sed 's/\r$//' "$SRC/mlkemcheck.go" > "$WORK/cmd/mlkemcheck/main.go"

cd "$WORK"
go mod tidy >/dev/null 2>&1 || true
go build -o "$WORK/bin/qserver" ./cmd/server
go build -o "$WORK/bin/qclient" ./cmd/client
go build -o "$WORK/bin/qdata" ./cmd/dataapp
CGO_ENABLED=0 go build -o "$WORK/bin/qamp" ./cmd/qamp
# 문서 5절: 경로 공백 회피를 위해 /tmp 로 복사해 실행한다.
CGO_ENABLED=0 go build -o "$WORK/bin/mlkemcheck" ./cmd/mlkemcheck
# 문서 5절: 경로 공백 회피를 위해 /tmp 로 복사해 실행한다.
cp "$WORK/bin/qamp" /tmp/qamp
cp "$WORK/bin/mlkemcheck" /tmp/mlkemcheck
echo "built:"
ls -la "$WORK/bin"
