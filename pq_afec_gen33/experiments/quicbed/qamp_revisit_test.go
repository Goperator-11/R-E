package main

import (
	"context"
	"crypto/tls"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	quic "github.com/quic-go/quic-go"
)

func TestRevisitCaches(t *testing.T) {
	var absentTokens *trackedTokenStore
	var absentSessions *trackedSessionCache
	if absentTokens.snapshot() != (cacheCounts{}) || absentSessions.snapshot() != (cacheCounts{}) {
		t.Fatal("disabled counts")
	}
	tokens := &trackedTokenStore{store: quic.NewLRUTokenStore(2, 2)}
	before := tokens.snapshot()
	a, b := &quic.ClientToken{}, &quic.ClientToken{}
	if tokens.Pop("server") != nil {
		t.Fatal("cold token")
	}
	tokens.Put("server", a)
	tokens.Put("server", b)
	if tokens.Pop("other") != nil || tokens.Pop("server") != b || tokens.Pop("server") != a || tokens.Pop("server") != nil {
		t.Fatal("token key or one-use")
	}
	if got := tokens.snapshot().since(before); got != (cacheCounts{Gets: 5, Hits: 2, Puts: 2}) {
		t.Fatal(got)
	}
	sessions := &trackedSessionCache{cache: tls.NewLRUClientSessionCache(2)}
	if _, ok := sessions.Get("server"); ok {
		t.Fatal("cold session")
	}
	state := &tls.ClientSessionState{}
	sessions.Put("server", state)
	for i := 0; i < 2; i++ {
		if got, ok := sessions.Get("server"); !ok || got != state {
			t.Fatal("session reuse")
		}
	}
	sessions.Put("server", nil)
	if _, ok := sessions.Get("server"); ok {
		t.Fatal("session invalidation")
	}
	if got := sessions.snapshot(); got != (cacheCounts{Gets: 4, Hits: 2, Puts: 1}) {
		t.Fatal(got)
	}
}

func TestRevisitCacheConcurrent(t *testing.T) {
	tokens := &trackedTokenStore{store: quic.NewLRUTokenStore(16, 4)}
	sessions := &trackedSessionCache{cache: tls.NewLRUClientSessionCache(16)}
	var wg sync.WaitGroup
	for i := 0; i < 16; i++ {
		wg.Go(func() {
			for j := 0; j < 20; j++ {
				tokens.Put("s", &quic.ClientToken{})
				tokens.Pop("s")
				sessions.Put("s", &tls.ClientSessionState{})
				sessions.Get("s")
				tokens.snapshot()
				sessions.snapshot()
			}
		})
	}
	wg.Wait()
	if got := tokens.snapshot(); got.Gets != 320 || got.Puts != 320 || got.Hits > 320 {
		t.Fatal(got)
	}
	if got := sessions.snapshot(); got != (cacheCounts{Gets: 320, Hits: 320, Puts: 320}) {
		t.Fatal(got)
	}
}

func TestRevisitCollection(t *testing.T) {
	target, rtt, source := revisitWaitTarget(200*time.Millisecond, 50*time.Millisecond, quic.ConnectionStats{LatestRTT: time.Second})
	if target != 200*time.Millisecond || rtt != 50*time.Millisecond || source != "handshake_elapsed_fallback" {
		t.Fatal(target, rtt, source)
	}
	target, rtt, source = revisitWaitTarget(200*time.Millisecond, 300*time.Millisecond, quic.ConnectionStats{LatestRTT: 400 * time.Millisecond, MeanDeviation: time.Millisecond})
	if target != 400*time.Millisecond || rtt != target || source != "quic_ack_latest_rtt" {
		t.Fatal(target, rtt, source)
	}
	synctest.Test(t, func(t *testing.T) {
		elapsed, ok := waitRevisit(context.Background(), 200*time.Millisecond)
		if !ok || elapsed != 200*time.Millisecond {
			t.Fatal(elapsed, ok)
		}
		ctx, cancel := context.WithCancel(context.Background())
		time.AfterFunc(10*time.Millisecond, cancel)
		elapsed, ok = waitRevisit(ctx, 200*time.Millisecond)
		if ok || elapsed != 10*time.Millisecond {
			t.Fatal(elapsed, ok)
		}
	})
}

func TestRevisitServerEvidence(t *testing.T) {
	s := &decodeConn{}
	id := quic.ConnectionIDFromBytes([]byte{1, 2, 3, 4})
	ca := &connAcct{}
	s.serverCIDs = map[string]*connAcct{string(id.Bytes()): ca}
	ctx, _ := s.accountContext(context.Background(), &quic.ClientInfo{AddrVerified: true})
	s.accountTracer(ctx, false, id)
	s.recordTLSResume(ctx, true)
	if !ca.AddressValidationObserved || !ca.AddressVerifiedAtStart || !ca.TLSObserved || !ca.TLSDidResume {
		t.Fatal(ca)
	}
	if !s.verifySource(nil) || s.stats.TokenContexts != 1 || s.stats.AddressVerifiedContexts != 1 || s.stats.TLSAccepted != 1 || s.stats.TLSResumed != 1 || s.stats.SourceVerifyCalls != 1 {
		t.Fatal(s.stats)
	}
	ctx, _ = s.accountContext(context.Background(), &quic.ClientInfo{})
	s.recordTLSResume(ctx, false)
	if s.stats.TokenContexts != 2 || s.stats.AddressVerifiedContexts != 1 || s.stats.TLSAccepted != 2 || s.stats.TLSResumed != 1 {
		t.Fatal(s.stats)
	}
}

func TestRevisitFlagBoundaries(t *testing.T) {
	for _, fec := range []string{"off", "buf", "fec"} {
		if err := checkRevisitFlags("client", fec, true, true, false, 0); err != nil {
			t.Fatal(err)
		}
	}
	if err := checkRevisitFlags("server", "fec", false, true, true, 10*time.Second); err != nil {
		t.Fatal(err)
	}
	for _, c := range []struct {
		mode, fec             string
		token, resume, verify bool
		wait                  time.Duration
	}{
		{"server", "off", true, false, false, 0}, {"certgen", "off", false, true, false, 0}, {"client", "off", false, false, true, 0},
		{"client", "auto", true, false, false, 0}, {"client", "auto3", false, true, false, 0},
		{"client", "off", false, false, false, -1}, {"client", "off", false, false, false, 10*time.Second + 1},
	} {
		if checkRevisitFlags(c.mode, c.fec, c.token, c.resume, c.verify, c.wait) == nil {
			t.Fatal(c)
		}
	}
}
