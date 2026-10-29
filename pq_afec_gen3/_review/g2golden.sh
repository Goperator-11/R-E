#!/bin/bash
export GOROOT="$HOME/goroot"; export PATH="$GOROOT/bin:$PATH"; export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"; export CGO_ENABLED=0; export GOFLAGS=-mod=readonly
B="$HOME/quicbed_g3/_review/g2"
rm -f "$B/cmd/qamp/rv_race_test.go"
sed 's/\r$//' /mnt/c/dev/pq_afec_gen3/_review/rv_g2golden_test.go > "$B/cmd/qamp/rv_g2golden_test.go"
cd "$B" && go test -count=1 -run TestRvBuilderGoldenOnG2 -v ./cmd/qamp 2>&1 | grep -E 'RVDIGEST|^ok|FAIL'
