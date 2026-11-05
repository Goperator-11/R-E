package main

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/qlog"
	"github.com/quic-go/quic-go/qlogwriter"
)

type holdQUICTrace struct {
	mu             sync.Mutex
	dropped        int
	droppedBytes   int
	firstCrypto    bool
	prefixDrops    int
	prefixBytes    int
	events         []string
}

func (t *holdQUICTrace) AddProducer() qlogwriter.Recorder { return t }
func (t *holdQUICTrace) SupportsSchemas(string) bool     { return true }
func (t *holdQUICTrace) Close() error                    { return nil }
func (t *holdQUICTrace) RecordEvent(event qlogwriter.Event) {
	t.mu.Lock()
	defer t.mu.Unlock()
	switch e := event.(type) {
	case qlog.PacketDropped:
		t.events = append(t.events, fmt.Sprintf("drop:%s:%d", e.Trigger, e.Raw.Length))
		if e.Trigger == qlog.PacketDropPayloadDecryptError && e.Raw.Length >= 1200 {
			t.dropped++
			t.droppedBytes += e.Raw.Length
		}
	case qlog.PacketSent:
		t.events = append(t.events, fmt.Sprintf("sent:%+v:%+v", e.Header, e.Frames))
		if t.firstCrypto {
			return
		}
	case qlog.PacketReceived:
		t.events = append(t.events, fmt.Sprintf("received:%+v:%+v", e.Header, e.Frames))
		for _, frame := range e.Frames {
			switch frame.Frame.(type) {
			case qlog.CryptoFrame, *qlog.CryptoFrame:
				t.firstCrypto = true
				t.prefixDrops, t.prefixBytes = t.dropped, t.droppedBytes
			}
		}
	}
}

func TestHoldQUICUnusedParityProcessedBeforeFirstCrypto(t *testing.T) {
	gfInit()
	for _, lost := range []int{-1, 0, 1} {
		t.Run(map[int]string{-1: "none", 0: "first_original", 1: "last_original"}[lost], func(t *testing.T) {
			serverUDP, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
			if err != nil {
				t.Fatal(err)
			}
			server := &decodeConn{countConn: countConn{PacketConn: serverUDP}, mode: "fec",
				flights: map[string]*flightRec{}, hold: newHoldState(defaultHoldConfig())}
			trace := &holdQUICTrace{}
			serverTransport := &quic.Transport{Conn: server, ConnectionIDLength: serverConnIDLength}
			defer serverTransport.Close()
			defer server.Close()
			listener, err := serverTransport.Listen(&tls.Config{Certificates: []tls.Certificate{makeCert(16000)},
				NextProtos: []string{"padfec"}, MinVersion: tls.VersionTLS13, SessionTicketsDisabled: true},
				&quic.Config{DisablePathMTUDiscovery: true, MaxIdleTimeout: 8 * time.Second,
					Tracer: func(context.Context, bool, quic.ConnectionID) qlogwriter.Trace { return trace }})
			if err != nil {
				t.Fatal(err)
			}
			defer listener.Close()
			clientUDP, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
			if err != nil {
				t.Fatal(err)
			}
			drops := map[int]bool{}
			if lost >= 0 {
				drops[lost] = true
			}
			client := &fecConn{countConn: countConn{PacketConn: clientUDP}, mode: "fec", m: 3,
				expectK: 2, parityDelay: time.Millisecond, layout: "v3", lead: 3,
				dropInitial: drops, dropParity: -1, corruptParity: -1}
			clientTransport := &quic.Transport{Conn: client}
			defer clientTransport.Close()
			defer clientUDP.Close()
			defer client.finalSendStats()
			ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
			defer cancel()
			connection, err := clientTransport.Dial(ctx, serverUDP.LocalAddr(), &tls.Config{
				InsecureSkipVerify: true, NextProtos: []string{"padfec"}, MinVersion: tls.VersionTLS13,
				CurvePreferences: []tls.CurveID{tls.X25519MLKEM768}, SessionTicketsDisabled: true},
				&quic.Config{InitialPacketSize: 1280, DisablePathMTUDiscovery: true, MaxIdleTimeout: 8 * time.Second})
			if err != nil {
				t.Fatal(err)
			}
			defer connection.CloseWithError(0, "done")
			stats := client.snapshot()
			if stats.FirstFlightDgrams != 2 {
				t.Fatalf("unexpected TLS first flight k=%d", stats.FirstFlightDgrams)
			}
			want := 3
			if lost >= 0 {
				want = 2
			}
			trace.mu.Lock()
			seen, count, size := trace.firstCrypto, trace.prefixDrops, trace.prefixBytes
			events := append([]string(nil), trace.events...)
			trace.mu.Unlock()
			t.Logf("events=%v client=%+v", events, stats)
			if !seen || count != want {
				t.Fatalf("unused parity before first CRYPTO: observed=%v count=%d want=%d bytes=%d", seen, count, want, size)
			}
			server.mu.Lock()
			recovered := server.stats.Recovered
			server.mu.Unlock()
			if (lost >= 0) != (recovered > 0) {
				t.Fatalf("loss=%d recovered=%d", lost, recovered)
			}
			t.Logf("loss=%d first_crypto_unused_parities=%d bytes=%d recovered=%d", lost, count, size, recovered)
		})
	}
}
