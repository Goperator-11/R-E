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

const holdQUICReferenceUplinkKbps = 2000

type holdQUICTrace struct {
	mu           sync.Mutex
	dropped      int
	droppedBytes int
	firstCrypto  bool
	prefixDrops  int
	prefixBytes  int
	events       []string
}

type holdQUICFirstFlightConn struct {
	*fecConn
	trace      *holdQUICTrace
	mu         sync.Mutex
	initials   int
	suppressed int
	isolate    bool
}

func (c *holdQUICFirstFlightConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	h := parseLongHdr(b)
	if h.ok && h.typ == 0 {
		c.initials++
		c.trace.mu.Lock()
		ready := c.trace.firstCrypto
		c.trace.mu.Unlock()
		if c.isolate && c.initials > 2 && !ready {
			c.suppressed++
			return len(b), nil
		}
		if c.initials > 2 {
			c.fecConn.mu.Lock()
			c.fecConn.parityDelay = time.Millisecond
			c.fecConn.mu.Unlock()
		}
	}
	return c.fecConn.WriteTo(b, addr)
}

func holdQUICFrames(frames []qlog.Frame) []string {
	result := make([]string, 0, len(frames))
	for _, frame := range frames {
		switch f := frame.Frame.(type) {
		case *qlog.CryptoFrame:
			result = append(result, fmt.Sprintf("crypto:%d:%d", f.Offset, f.Length))
		case qlog.CryptoFrame:
			result = append(result, fmt.Sprintf("crypto:%d:%d", f.Offset, f.Length))
		default:
			result = append(result, fmt.Sprintf("%T", f))
		}
	}
	return result
}

func (t *holdQUICTrace) AddProducer() qlogwriter.Recorder { return t }
func (t *holdQUICTrace) SupportsSchemas(string) bool      { return true }
func (t *holdQUICTrace) Close() error                     { return nil }
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
		if t.firstCrypto {
			return
		}
		t.events = append(t.events, fmt.Sprintf("sent:%s:%d:%v", e.Header.PacketType, e.Header.PacketNumber, holdQUICFrames(e.Frames)))
		for _, frame := range e.Frames {
			switch frame.Frame.(type) {
			case qlog.CryptoFrame, *qlog.CryptoFrame:
				t.firstCrypto = true
				t.prefixDrops, t.prefixBytes = t.dropped, t.droppedBytes
			}
		}
	case qlog.PacketReceived:
		if !t.firstCrypto {
			t.events = append(t.events, fmt.Sprintf("received:%s:%d:%v", e.Header.PacketType, e.Header.PacketNumber, holdQUICFrames(e.Frames)))
		}
	}
}

func TestHoldQUICTraceCountsOnlySentCrypto(t *testing.T) {
	trace := &holdQUICTrace{}
	frames := []qlog.Frame{{Frame: &qlog.CryptoFrame{Offset: 0, Length: 100}}}
	trace.RecordEvent(qlog.PacketReceived{Frames: frames})
	trace.RecordEvent(qlog.PacketSent{})
	if trace.firstCrypto {
		t.Fatal("received CRYPTO or empty sent packet counted as sent CRYPTO")
	}
	trace.RecordEvent(qlog.PacketSent{Frames: frames})
	if !trace.firstCrypto {
		t.Fatal("sent CRYPTO missing")
	}
}

func TestHoldQUICUnusedParityProcessedBeforeFirstCrypto(t *testing.T) {
	holdQUICRun(t, true, false)
}

func TestHoldQUICLiveRetransmissionsPreserveAccounting(t *testing.T) {
	holdQUICRun(t, false, false)
}

func TestHoldQUICReferencePathUnusedParityBeforeFirstCrypto(t *testing.T) {
	holdQUICRun(t, false, true)
}

func holdQUICRun(t *testing.T, isolate, referencePath bool) {
	gfInit()
	for _, lost := range []int{-1, 0, 1} {
		t.Run(map[int]string{-1: "none", 0: "first_original", 1: "last_original"}[lost], func(t *testing.T) {
			serverUDP, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
			if err != nil {
				t.Fatal(err)
			}
			var serverWire net.PacketConn = serverUDP
			if referencePath {
				link := newHoldQUICPathConn(serverUDP, 25*time.Millisecond, 0)
				serverWire = link
				defer link.Close()
			}
			hold := newHoldState(defaultHoldConfig())
			if isolate || referencePath {
				clock := &holdQUICArrivalClock{expected: 5}
				if lost >= 0 {
					clock.expected = 4
				}
				if referencePath {
					clock.rateKbps = holdQUICReferenceUplinkKbps
				}
				hold.now = clock.now
				serverWire = &holdQUICArrivalConn{PacketConn: serverWire, clock: clock}
			}
			server := &decodeConn{countConn: countConn{PacketConn: serverWire}, mode: "fec",
				flights: map[string]*flightRec{}, hold: hold}
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
			var clientWire net.PacketConn = clientUDP
			if referencePath {
				link := newHoldQUICPathConn(clientUDP, 25*time.Millisecond, holdQUICReferenceUplinkKbps)
				clientWire = link
				defer link.Close()
			}
			client := &fecConn{countConn: countConn{PacketConn: clientWire}, mode: "fec", m: 3,
				expectK: 2, parityDelay: 8 * time.Second, layout: "v3", lead: 3,
				dropInitial: drops, dropParity: -1, corruptParity: -1}
			gate := &holdQUICFirstFlightConn{fecConn: client, trace: trace, isolate: isolate}
			clientTransport := &quic.Transport{Conn: gate}
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
			gate.mu.Lock()
			suppressed := gate.suppressed
			gate.mu.Unlock()
			server.mu.Lock()
			recovered, premature, expiries := server.stats.Recovered, server.stats.PrematureRecover, server.stats.DecoderExpiryEvents
			physical, stack, pending := server.stats.BytesIn, server.stats.BytesToStack, server.pendingBytes
			server.mu.Unlock()
			t.Logf("events=%v flights=%d dropped_original=%d suppressed_later_initial=%d recovered=%d premature=%d expiries=%d", events, stats.Flights, stats.DroppedOrig, suppressed, recovered, premature, expiries)
			if !seen || ((isolate || referencePath) && count != want) {
				t.Fatalf("unused parity before first CRYPTO: observed=%v count=%d want=%d bytes=%d", seen, count, want, size)
			}
			wantRecovered := 0
			if lost >= 0 {
				wantRecovered = 1
			}
			if (isolate || referencePath) && recovered != wantRecovered {
				t.Fatalf("loss=%d recovered=%d", lost, recovered)
			}
			if stack+pending > physical || (!isolate && suppressed != 0) {
				t.Fatalf("accounting physical=%d stack=%d pending=%d suppressed=%d", physical, stack, pending, suppressed)
			}
			t.Logf("loss=%d first_crypto_unused_parities=%d bytes=%d recovered=%d", lost, count, size, recovered)
		})
	}
}
