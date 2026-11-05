#!/bin/bash
set -euo pipefail
export GOROOT=/home/scien/goroot
export PATH="$GOROOT/bin:$PATH"
export GOPATH=/home/scien/gopath
export GOCACHE=/home/scien/.cache/go-build
export CGO_ENABLED=0 GOFLAGS=-mod=readonly GOAMD64=v1 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off
cd /home/scien/quicbed_gen33/stage.zJV3Mg
go test -count=25 -v -run '^TestHoldQUIC' ./cmd/qamp
