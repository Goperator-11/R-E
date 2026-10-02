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

# 🩸 2026-09-03 - 여기 있던 `go mod init` + `go get quic-go@latest` 를 뺐다.
#    @latest 는 **부동 버전**이다. 오늘 돌리면 v0.61.0 이 아니라 v0.62.0
#    (2026-08-30 릴리스)이 받아진다. 지금은 그래도 헤드라인이 안 흔들리지만
#    (T_pto 203.60 -> 203.47 ms, P=1280 그대로 - 2026-09-03 확인) 그것은
#    운이지 보장이 아니다. 이 저장소의 실측은 전부 **quic-go v0.61.0** 의
#    것이고, 그 사실이 이 노트북의 ~/quicbed/go.mod 안에만 있었다.
#    이제 저장소에 있다. 여기서는 그것을 복사만 한다.
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
