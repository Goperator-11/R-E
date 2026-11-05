package main

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"sync"
	"time"

	quic "github.com/quic-go/quic-go"
)

type cacheCounts struct {
	Gets int `json:"gets"`
	Hits int `json:"hits"`
	Puts int `json:"puts"`
}

func (c cacheCounts) since(before cacheCounts) cacheCounts {
	return cacheCounts{c.Gets - before.Gets, c.Hits - before.Hits, c.Puts - before.Puts}
}

type trackedTokenStore struct {
	mu     sync.Mutex
	store  quic.TokenStore
	counts cacheCounts
}

func (s *trackedTokenStore) Pop(key string) *quic.ClientToken {
	s.mu.Lock()
	defer s.mu.Unlock()
	token := s.store.Pop(key)
	s.counts.Gets++
	if token != nil {
		s.counts.Hits++
	}
	return token
}

func (s *trackedTokenStore) Put(key string, token *quic.ClientToken) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.store.Put(key, token)
	s.counts.Puts++
}

func (s *trackedTokenStore) snapshot() cacheCounts {
	if s == nil {
		return cacheCounts{}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.counts
}

type trackedSessionCache struct {
	mu     sync.Mutex
	cache  tls.ClientSessionCache
	counts cacheCounts
}

func (s *trackedSessionCache) Get(key string) (*tls.ClientSessionState, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	state, ok := s.cache.Get(key)
	s.counts.Gets++
	if ok {
		s.counts.Hits++
	}
	return state, ok
}

func (s *trackedSessionCache) Put(key string, state *tls.ClientSessionState) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cache.Put(key, state)
	if state != nil {
		s.counts.Puts++
	}
}

func (s *trackedSessionCache) snapshot() cacheCounts {
	if s == nil {
		return cacheCounts{}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.counts
}

type revisitObservation struct {
	TokenStore      bool        `json:"token_store"`
	Resume          bool        `json:"resume"`
	FirstConnection bool        `json:"first_connection"`
	CacheScope      string      `json:"cache_scope"`
	Token           cacheCounts `json:"token"`
	Session         cacheCounts `json:"session"`
	TLSObserved     bool        `json:"tls_observed"`
	TLSDidResume    bool        `json:"tls_did_resume"`
	Used0RTT        bool        `json:"used_0rtt"`
	RetryReceived   int         `json:"retry_received"`
	WaitRequestedNS int64       `json:"wait_requested_ns"`
	WaitTargetNS    int64       `json:"wait_target_ns"`
	WaitElapsedNS   int64       `json:"wait_elapsed_ns"`
	WaitRTTNS       int64       `json:"wait_rtt_ns"`
	WaitRTTSource   string      `json:"wait_rtt_source"`
	WaitCompleted   bool        `json:"wait_completed"`
}

func revisitWaitTarget(requested, handshake time.Duration, stats quic.ConnectionStats) (time.Duration, time.Duration, string) {
	rtt, source := handshake, "handshake_elapsed_fallback"
	if stats.MeanDeviation > 0 && stats.LatestRTT > 0 {
		rtt, source = stats.LatestRTT, "quic_ack_latest_rtt"
	}
	return max(requested, handshake, rtt), rtt, source
}

func waitRevisit(ctx context.Context, target time.Duration) (time.Duration, bool) {
	start := time.Now()
	timer := time.NewTimer(target)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return time.Since(start), false
	case <-timer.C:
		return time.Since(start), ctx.Err() == nil
	}
}

func checkRevisitFlags(mode, fec string, token, resume, verify bool, wait time.Duration) error {
	if wait < 0 || wait > 10*time.Second {
		return errors.New("revisit-wait must be between 0 and 10s")
	}
	if verify && mode != "server" {
		return errors.New("verify-source requires server mode")
	}
	if token && mode != "client" {
		return errors.New("token-store requires client mode")
	}
	if resume && mode != "client" && mode != "server" {
		return errors.New("resume requires client or server mode")
	}
	if mode == "client" && (token || resume) && (fec == "auto" || fec == "auto3") {
		return errors.New("token-store and resume require fixed fec mode")
	}
	return nil
}

func (s *decodeConn) verifySource(net.Addr) bool {
	s.mu.Lock()
	s.stats.SourceVerifyCalls++
	s.mu.Unlock()
	return true
}

func (s *decodeConn) recordTLSResume(ctx context.Context, resumed bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stats.TLSAccepted++
	if resumed {
		s.stats.TLSResumed++
	}
	if trace, ok := ctx.Value(accountContextKey{}).(*accountTrace); ok && trace.account != nil {
		trace.account.TLSObserved = true
		trace.account.TLSDidResume = resumed
	}
}
