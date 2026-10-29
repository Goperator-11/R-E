#!/bin/bash
export GOROOT="$HOME/goroot"
export PATH="$GOROOT/bin:$PATH"
export GOPATH="${GOPATH:-$HOME/gopath}"
export GOCACHE="${GOCACHE:-$HOME/.cache/go-build}"
export GOFLAGS=-mod=readonly
BASE="$HOME/quicbed_g3/_review"
for tree in g2 g3; do
	sed 's/\r$//' /mnt/c/dev/pq_afec_gen3/_review/rv_race_test.go > "$BASE/$tree/cmd/qamp/rv_race_test.go"
	echo "== $tree race"
	(cd "$BASE/$tree" && CGO_ENABLED=1 go test -race -count=1 -run 'TestRvConcurrent|TestLeadClient|TestRvClientServer|TestRvLater' ./cmd/qamp 2>&1 | tail -30)
done
