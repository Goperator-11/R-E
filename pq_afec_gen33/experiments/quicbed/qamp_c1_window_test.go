package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"io"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
)

const c1WindowProbes = 2

type c1WindowServerConn struct {
	net.PacketConn
	mu      sync.Mutex
	big     []byte
	delay   time.Duration
	wg      sync.WaitGroup
	holding bool
	flushed bool
	held    [][]byte
	window  int
}

func (c *c1WindowServerConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	if parseFeedback(b) != nil {
		fb := append([]byte(nil), b...)
		c.mu.Lock()
		big := c.big
		c.holding = true
		c.window += c1WindowProbes * len(big)
		c.mu.Unlock()
		c.wg.Add(1)
		go func() {
			defer c.wg.Done()
			time.Sleep(c.delay)
			for range c1WindowProbes {
				c.PacketConn.WriteTo(big, addr)
			}
			c.mu.Lock()
			held := c.held
			c.held = nil
			c.flushed = true
			c.mu.Unlock()
			for _, h := range held {
				c.PacketConn.WriteTo(h, addr)
			}
			c.PacketConn.WriteTo(fb, addr)
		}()
		return len(b), nil
	}
	c.mu.Lock()
	if c.flushed {
		c.mu.Unlock()
		return len(b), nil
	}
	if c.holding {
		c.held = append(c.held, append([]byte(nil), b...))
		c.window += len(b)
		c.mu.Unlock()
		return len(b), nil
	}
	if len(b) >= serverFlightMin && c.big == nil {
		c.big = append([]byte(nil), b...)
	}
	c.mu.Unlock()
	return c.PacketConn.WriteTo(b, addr)
}

type c1RTTDatagram struct {
	b    []byte
	addr net.Addr
	due  time.Time
}

type c1RTTServerConn struct {
	net.PacketConn
	mu     sync.Mutex
	pre    time.Duration
	post   time.Duration
	after  bool
	closed bool
	early  chan c1RTTDatagram
	late   chan c1RTTDatagram
	wg     sync.WaitGroup
}

func newC1RTTServerConn(udp net.PacketConn, pre, post time.Duration) *c1RTTServerConn {
	c := &c1RTTServerConn{PacketConn: udp, pre: pre, post: post,
		early: make(chan c1RTTDatagram, 4096), late: make(chan c1RTTDatagram, 4096)}
	for _, lane := range []chan c1RTTDatagram{c.early, c.late} {
		c.wg.Add(1)
		go func() {
			defer c.wg.Done()
			for d := range lane {
				time.Sleep(time.Until(d.due))
				c.PacketConn.WriteTo(d.b, d.addr)
			}
		}()
	}
	return c
}

func (c *c1RTTServerConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	d := c1RTTDatagram{b: append([]byte(nil), b...), addr: addr}
	c.mu.Lock()
	defer c.mu.Unlock()
	switch {
	case c.closed:
	case parseFeedback(b) != nil:
		c.after = true
		c.wg.Add(1)
		time.AfterFunc(2*c.post, func() {
			defer c.wg.Done()
			c.PacketConn.WriteTo(d.b, d.addr)
		})
	case c.after:
		d.due = time.Now().Add(c.post)
		c.late <- d
	default:
		d.due = time.Now().Add(c.pre)
		c.early <- d
	}
	return len(b), nil
}

func (c *c1RTTServerConn) drain() {
	c.mu.Lock()
	if !c.closed {
		c.closed = true
		close(c.early)
		close(c.late)
	}
	c.mu.Unlock()
	c.wg.Wait()
}

func c1WindowRun(t *testing.T, feedback bool) (map[string]any, []float64, int) {
	t.Helper()
	var wire *c1WindowServerConn
	row, sHist := c1WindowClientRow(t, feedback, func(udp net.PacketConn) (net.PacketConn, func()) {
		wire = &c1WindowServerConn{PacketConn: udp, delay: 50 * time.Millisecond}
		return wire, wire.wg.Wait
	})
	wire.mu.Lock()
	defer wire.mu.Unlock()
	return row, sHist, wire.window
}

func c1WindowClientRow(t *testing.T, feedback bool, wrap func(net.PacketConn) (net.PacketConn, func())) (map[string]any, []float64) {
	t.Helper()
	gfInit()
	udp, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	wire, drain := wrap(udp)
	server := &decodeConn{countConn: countConn{PacketConn: wire}, mode: "fec", feedback: feedback,
		feedbackVersion: fbVerFrozen, flights: map[string]*flightRec{}}
	transport := &quic.Transport{Conn: server, ConnectionIDLength: serverConnIDLength, ConnContext: server.accountContext}
	listener, err := transport.Listen(&tls.Config{Certificates: []tls.Certificate{makeCert(4000)}, NextProtos: []string{"padfec"},
		MinVersion: tls.VersionTLS13, SessionTicketsDisabled: true},
		&quic.Config{Tracer: server.accountTracer, DisablePathMTUDiscovery: true, MaxIdleTimeout: 8 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		drain()
		listener.Close()
		transport.Close()
		server.Close()
	}()
	go func() {
		for {
			conn, err := listener.Accept(context.Background())
			if err != nil {
				return
			}
			server.accountAccepted(conn.Context())
		}
	}()
	cache := filepath.Join(t.TempDir(), "cache3.json")
	read, write, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	output := make(chan []byte, 1)
	go func() {
		raw, _ := io.ReadAll(read)
		output <- raw
	}()
	stdout := os.Stdout
	os.Stdout = write
	addr := udp.LocalAddr().String()
	runClient(addr, "X25519MLKEM768", 1, 5*time.Second, 0, "auto3", 1, 0, 300, "", "", nil, -1, -1, "", 0, 0, 0, 2,
		feedback, "v3", -1, cache, false, false, 0, false, false, 0, revisitGuardConfig{},
		clientWiring{ExpectK: 2, ExpectKSet: true, FeedbackWait: 2 * time.Second, RetransLayout: "repeat_first"})
	os.Stdout = stdout
	write.Close()
	var row map[string]any
	if err := json.Unmarshal(<-output, &row); err != nil {
		t.Fatal(err)
	}
	loaded, err := loadDestCache3(cache)
	if err != nil {
		t.Fatal(err)
	}
	entry := loaded.Dests[addr]
	if entry == nil {
		t.Fatalf("cache has no destination %s", addr)
	}
	return row, entry.State.SHist
}

func TestC1WindowDatagramsStayOutOfPolicyServerBytes(t *testing.T) {
	row, sHist, window := c1WindowRun(t, true)
	if row["feedback_wait_received"] != true {
		t.Fatalf("feedback not received: %v", row["feedback_wait_received"])
	}
	if arrivals, _ := row["arrivals"].(map[string]any); arrivals["src"] != "c1" {
		t.Fatalf("arrivals %v", row["arrivals"])
	}
	total := row["server_bytes"].(float64)
	if len(sHist) != 1 {
		t.Fatalf("S_hist %v", sHist)
	}
	if want := total - float64(window); sHist[0] != want {
		t.Fatalf("S_hist[0]=%v server_bytes=%v want %v: wait-window datagrams reached the policy", sHist[0], total, want)
	}
	if pre, ok := row["server_bytes_pre_wait"].(float64); !ok || pre != sHist[0] {
		t.Fatalf("server_bytes_pre_wait=%v S_hist[0]=%v", row["server_bytes_pre_wait"], sHist[0])
	}
}

func TestC1WindowRTTSampleStaysOutOfPolicyRTT(t *testing.T) {
	const pre, post = 150 * time.Millisecond, 40 * time.Millisecond
	row, _ := c1WindowClientRow(t, true, func(udp net.PacketConn) (net.PacketConn, func()) {
		wire := newC1RTTServerConn(udp, pre, post)
		return wire, wire.drain
	})
	if row["feedback_wait_received"] != true {
		t.Fatalf("feedback not received: %v", row["feedback_wait_received"])
	}
	if row["path_rtt_valid"] != true || row["path_rtt_after_wait_valid"] != true {
		t.Fatalf("path_rtt_valid %v path_rtt_after_wait_valid %v", row["path_rtt_valid"], row["path_rtt_after_wait_valid"])
	}
	policy, _ := row["path_rtt_ms"].(float64)
	after, _ := row["path_rtt_after_wait_ms"].(float64)
	floor := float64(pre) / float64(time.Millisecond)
	if after >= floor {
		t.Fatalf("path_rtt_after_wait_ms=%v: no wait-window RTT sample below the %v ms handshake delay", after, floor)
	}
	if policy < floor {
		t.Fatalf("path_rtt_ms=%v path_rtt_after_wait_ms=%v: wait-window RTT sample reached the policy", policy, after)
	}
}

func TestNonePathPolicyServerBytesIsWholeObservation(t *testing.T) {
	row, sHist, _ := c1WindowRun(t, false)
	if len(sHist) != 1 || sHist[0] != row["server_bytes"].(float64) {
		t.Fatalf("S_hist %v server_bytes %v", sHist, row["server_bytes"])
	}
	for _, key := range []string{"server_bytes_pre_wait", "path_rtt_after_wait_ms", "path_rtt_after_wait_valid"} {
		if _, present := row[key]; present {
			t.Fatalf("none row has %s", key)
		}
	}
	if row["feedback_wait_ns"].(float64) != 0 {
		t.Fatalf("none row waited %v", row["feedback_wait_ns"])
	}
}
