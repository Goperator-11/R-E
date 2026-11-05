package main

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"hash/crc32"
	"io"
	"net"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"
)

type holdFrame struct {
	at   time.Time
	data []byte
}

type holdScriptConn struct {
	net.PacketConn
	frames    []holdFrame
	i         int
	now       time.Time
	deadline  time.Time
	closed    bool
	stop      time.Time
	check     func()
	afterRead func()
}

func (c *holdScriptConn) ReadFrom(b []byte) (int, net.Addr, error) {
	if c.check != nil {
		c.check()
	}
	if c.closed {
		return 0, nil, net.ErrClosed
	}
	if c.i == len(c.frames) && !c.stop.IsZero() && (c.deadline.IsZero() || c.deadline.After(c.stop)) {
		return 0, nil, io.EOF
	}
	if !c.deadline.IsZero() && (c.i == len(c.frames) || !c.frames[c.i].at.Before(c.deadline)) {
		c.now = c.deadline
		return 0, nil, os.ErrDeadlineExceeded
	}
	if c.i == len(c.frames) {
		return 0, nil, io.EOF
	}
	f := c.frames[c.i]
	c.i++
	c.now = f.at
	if c.afterRead != nil {
		c.afterRead()
	}
	return copy(b, f.data), &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 32100}, nil
}

func (c *holdScriptConn) SetReadDeadline(t time.Time) error  { c.deadline = t; return nil }
func (c *holdScriptConn) SetWriteDeadline(t time.Time) error { return nil }
func (c *holdScriptConn) Close() error                       { c.closed = true; return nil }

func holdTestConn(dgs [][]byte, config holdConfig) (*decodeConn, *holdScriptConn) {
	c := &holdScriptConn{now: time.Unix(0, 0)}
	for i, d := range dgs {
		c.frames = append(c.frames, holdFrame{time.Unix(0, int64(i+1)*1000), d})
	}
	s := &decodeConn{countConn: countConn{PacketConn: c}, mode: "fec", hold: newHoldState(config)}
	s.hold.now = func() time.Time { return c.now }
	return s, c
}

func holdReadAll(t *testing.T, s *decodeConn) [][]byte {
	t.Helper()
	out := [][]byte{}
	for i := 0; i < 30; i++ {
		b := make([]byte, 2000)
		n, _, err := s.ReadFrom(b)
		if errors.Is(err, io.EOF) {
			return out
		}
		if err != nil {
			t.Fatal(err)
		}
		out = append(out, append([]byte(nil), b[:n]...))
		if s.stats.BytesToStack+s.pendingBytes > s.stats.BytesIn {
			t.Fatal("global credit")
		}
		for _, ca := range s.conns {
			pending := int64(0)
			for _, p := range s.pending {
				if p.acct == ca {
					pending += int64(len(p.data))
				}
			}
			if ca.Stack+pending > ca.RxBytes {
				t.Fatal("connection credit")
			}
		}
	}
	t.Fatal("read did not terminate")
	return nil
}

func TestHoldReadFromFIFO(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVerLead, 3, 4, 2, 31)
	s, _ := holdTestConn([][]byte{dg[0].data, dg[1].data, dg[2].data, src[0], src[1]}, defaultHoldConfig())
	out := holdReadAll(t, s)
	want := [][]byte{src[0], dg[0].data, dg[1].data, dg[2].data, src[1]}
	if len(out) != len(want) {
		t.Fatal(len(out))
	}
	for i := range out {
		if !bytes.Equal(out[i], want[i]) {
			t.Fatalf("FIFO %d", i)
		}
	}
	if s.stats.Recovered != 0 || s.heldBytes != 0 || s.hold.memory != 0 {
		t.Fatal(s.stats)
	}
}

func TestHoldReadFromTimerRecovery(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVerLead, 2, 2, 2, 41)
	s, c := holdTestConn([][]byte{dg[0].data, dg[1].data, src[0]}, defaultHoldConfig())
	out := holdReadAll(t, s)
	if len(out) != 3 || !bytes.Equal(out[0], src[0]) || !bytes.Equal(out[1], dg[1].data) || !bytes.Equal(out[2], src[1]) {
		t.Fatal("timer output")
	}
	want := time.Unix(0, 1000).Add(time.Duration((len(dg[1].data)+len(src[0])+len(src[1]))*4000) + time.Millisecond)
	if !c.now.Equal(want) || s.stats.Recovered != 1 || s.stats.RecoverEvents != 1 {
		t.Fatal(c.now, want, s.stats)
	}
}

func TestHoldReadFromPersistentOpenAndTrailingPriority(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVerLead, 2, 4, 4, 51)
	s, _ := holdTestConn([][]byte{dg[0].data, dg[1].data, dg[6].data, src[0]}, defaultHoldConfig())
	out := holdReadAll(t, s)
	if len(out) != 4 {
		t.Fatal(len(out))
	}
	for i := range out {
		if !bytes.Equal(out[i], src[i]) {
			t.Fatal("recovered bytes", i)
		}
	}
	for _, fr := range s.hold.flights {
		if len(fr.used) != 3 || fr.used[0] != 2 || fr.used[1] != 0 || fr.used[2] != 1 {
			t.Fatal(fr.used)
		}
	}
}

func TestHoldReadFromMetadataAndDuplicate(t *testing.T) {
	gfInit()
	dg, src := leadBuildFlight(fecVerLead, 2, 2, 2, 61)
	fb := parseFecBlock(dg[1].data)
	fb.lead = 1
	conflict := buildParity(leadTestDCID, leadTestSCID, *fb)
	s, _ := holdTestConn([][]byte{dg[0].data, dg[0].data, conflict, src[0]}, defaultHoldConfig())
	out := holdReadAll(t, s)
	if len(out) != 2 || !bytes.Equal(out[1], src[1]) {
		t.Fatal("conflict recovery")
	}
	if s.stats.HoldDuplicateBytes != int64(len(dg[0].data)) || s.stats.HoldMetadataBytes != int64(len(conflict)) {
		t.Fatal(s.stats)
	}
}

func TestHoldReadFromCapExpiryAndSmallBuffer(t *testing.T) {
	gfInit()
	dg, _ := leadBuildFlight(fecVerLead, 2, 2, 2, 71)
	config := defaultHoldConfig()
	config.flightCap = 3000
	s, _ := holdTestConn([][]byte{dg[0].data, dg[1].data}, config)
	out := holdReadAll(t, s)
	if len(out) != 1 || s.stats.HoldCapBytes != int64(len(dg[0].data)) || s.heldBytes != 0 {
		t.Fatal("cap")
	}
	s, _ = holdTestConn([][]byte{dg[0].data}, defaultHoldConfig())
	if out = holdReadAll(t, s); len(out) != 0 || s.stats.HoldExpiredBytes != int64(len(dg[0].data)) || s.heldBytes != 0 {
		t.Fatal("expiry")
	}
	s, _ = holdTestConn([][]byte{dg[0].data, dg[1].data}, defaultHoldConfig())
	if n, _, err := s.ReadFrom(make([]byte, 2000)); err != nil || n != 1200 {
		t.Fatal(n, err)
	}
	before := s.stats.BytesToStack
	if n, _, err := s.ReadFrom(make([]byte, 7)); err != nil || n != 7 {
		t.Fatal(n, err)
	}
	if s.stats.BytesToStack-before != 7 || s.pendingBytes != 0 || s.stats.HoldTruncatedBytes != 1143 {
		t.Fatal("small buffer", s.stats)
	}
}

func TestHoldExternalDeadlineAndClose(t *testing.T) {
	gfInit()
	dg, _ := leadBuildFlight(fecVerLead, 2, 2, 2, 81)
	s, c := holdTestConn([][]byte{dg[0].data}, defaultHoldConfig())
	external := time.Unix(0, 2000)
	if err := s.SetReadDeadline(external); err != nil {
		t.Fatal(err)
	}
	if _, _, err := s.ReadFrom(make([]byte, 2000)); !errors.Is(err, os.ErrDeadlineExceeded) {
		t.Fatal(err)
	}
	if !c.now.Equal(external) || s.heldBytes == 0 {
		t.Fatal("external deadline lost")
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	if s.heldBytes != 0 || s.pendingBytes != 0 {
		t.Fatal("close retained memory")
	}
	if _, _, err := s.ReadFrom(make([]byte, 2000)); !errors.Is(err, net.ErrClosed) {
		t.Fatal(err)
	}
}

func holdReferenceFixture(t *testing.T, k, m, lead int) [][]byte {
	return holdNamedFixture(t, k, m, lead, leadTestDCID, leadTestSCID)
}

func holdNamedFixture(t *testing.T, k, m, lead int, dcid, scid []byte) [][]byte {
	t.Helper()
	size := 1331 - 34 - 6*k
	src := make([][]byte, k)
	padded := make([][]byte, k)
	crcs := make([]uint32, k)
	lens := make([]uint16, k)
	for i := range src {
		src[i] = leadTestInitial(dcid, scid, 1200+17*i, byte(30+i))
		padded[i] = make([]byte, size)
		copy(padded[i], src[i])
		crcs[i], lens[i] = crc32.ChecksumIEEE(src[i]), uint16(len(src[i]))
	}
	packets := append([][]byte(nil), src...)
	if m == 0 {
		return packets
	}
	for i, p := range rsEncode(padded, m, size) {
		packet := buildParity(dcid, scid, fecBlock{ver: fecVerLead, flight: 1, k: k, m: m, lead: lead, index: i, symLen: size, crcs: crcs, lens: lens, sym: p})
		if len(packet) != 1331 {
			t.Fatal("reference packet size", len(packet))
		}
		packets = append(packets, packet)
	}
	return packets
}

func TestHoldCloseDuringPhysicalRead(t *testing.T) {
	gfInit()
	packets := holdReferenceFixture(t, 2, 2, 2)
	s, c := holdTestConn([][]byte{packets[2]}, defaultHoldConfig())
	c.afterRead = func() {
		c.afterRead = nil
		if err := s.Close(); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := s.ReadFrom(make([]byte, 2000)); !errors.Is(err, net.ErrClosed) {
		t.Fatal(err)
	}
	if len(s.hold.flights) != 0 || s.heldBytes != 0 || s.pendingBytes != 0 || s.hold.recent.age.Len() != 0 {
		t.Fatal("state created after Close")
	}
	if s.stats.BytesIn != 1331 || s.stats.HoldDiscardBytes != 1331 {
		t.Fatal(s.stats)
	}
}

func TestHoldTwoConnectionsShareAddressWithoutCreditBorrowing(t *testing.T) {
	gfInit()
	a := holdReferenceFixture(t, 2, 2, 2)
	b := holdNamedFixture(t, 2, 2, 2, []byte{1, 2, 3, 4, 5, 6, 7, 8}, []byte{41, 42, 43, 44})
	s, _ := holdTestConn([][]byte{a[2], b[2], a[3], b[3]}, defaultHoldConfig())
	out := holdReadAll(t, s)
	if len(out) != 4 || len(s.conns) != 2 {
		t.Fatal(len(out), len(s.conns))
	}
	for _, ca := range s.conns {
		if ca.RxBytes != 2662 || ca.Stack != 2417 || ca.RecovN != 2 {
			t.Fatal(ca)
		}
	}
	if s.heldBytes != 0 || s.hold.memory != 0 || s.pendingBytes != 0 {
		t.Fatal("retained memory")
	}
}

func TestHoldGlobalMemoryAndFlightCountCaps(t *testing.T) {
	gfInit()
	a := holdReferenceFixture(t, 2, 2, 2)
	b := holdNamedFixture(t, 2, 2, 2, []byte{1, 2, 3, 4, 5, 6, 7, 8}, []byte{41, 42, 43, 44})
	for _, byCount := range []bool{false, true} {
		config := defaultHoldConfig()
		if byCount {
			config.flightCount = 1
		} else {
			config.globalCap = 65535 + 2662
		}
		s, _ := holdTestConn([][]byte{a[2], b[2]}, config)
		out := holdReadAll(t, s)
		if len(out) != 1 || !bytes.Equal(out[0], b[2]) || s.stats.Recovered != 0 || s.heldBytes != 0 {
			t.Fatal("global fallback", byCount)
		}
		if int64(len(s.hold.flights)) > int64(config.flightCount) || s.hold.memory+s.pendingBytes > config.globalCap {
			t.Fatal("cap exceeded")
		}
	}
}

func TestHoldCreditCountsOnlyReturnedParity(t *testing.T) {
	gfInit()
	packets := holdReferenceFixture(t, 2, 3, 3)
	s, _ := holdTestConn([][]byte{packets[2], packets[3], packets[4], packets[0], packets[1], packets[2]}, defaultHoldConfig())
	buf := make([]byte, 2000)
	if _, _, err := s.ReadFrom(buf); err != nil {
		t.Fatal(err)
	}
	if s.stats.CreditParities != 0 {
		t.Fatal("unreturned credit")
	}
	if _, _, err := s.ReadFrom(buf); err != nil {
		t.Fatal(err)
	}
	if s.stats.CreditParities != 1 || s.stats.CreditParitiesV3 != 1 {
		t.Fatal("pending counted early")
	}
	holdReadAll(t, s)
	if s.stats.CreditParities != 4 || s.stats.CreditParitiesV3 != 4 {
		t.Fatal("late parity missing")
	}
}

func TestHoldMetadataFieldsAreImmutable(t *testing.T) {
	gfInit()
	packets := holdReferenceFixture(t, 2, 2, 2)
	mutations := []func(*fecBlock){
		func(f *fecBlock) { f.ver = fecVer }, func(f *fecBlock) { f.k = 1; f.crcs = f.crcs[:1]; f.lens = f.lens[:1] },
		func(f *fecBlock) { f.m = 3 }, func(f *fecBlock) { f.lead = 1 },
		func(f *fecBlock) { f.symLen++; f.sym = append(f.sym, 0) }, func(f *fecBlock) { f.crcs[0]++ }, func(f *fecBlock) { f.lens[0]-- },
	}
	for i, mutate := range mutations {
		fb := parseFecBlock(packets[3])
		mutate(fb)
		bad := buildParity(leadTestDCID, leadTestSCID, *fb)
		if parseFecBlock(bad) == nil {
			t.Fatal("fixture not parseable", i)
		}
		s, _ := holdTestConn([][]byte{packets[2], bad, packets[0]}, defaultHoldConfig())
		out := holdReadAll(t, s)
		if len(out) != 2 || !bytes.Equal(out[1], packets[1]) || s.stats.HoldMetadataBytes != int64(len(bad)) {
			t.Fatal("metadata mutation", i)
		}
	}
}

func TestHoldRealSocketTimerAndClose(t *testing.T) {
	gfInit()
	udp, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	config := defaultHoldConfig()
	config.uplinkKbps = 0
	s := &decodeConn{countConn: countConn{PacketConn: udp}, mode: "fec", hold: newHoldState(config)}
	defer s.Close()
	sender, err := net.Dial("udp", udp.LocalAddr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer sender.Close()
	packets := holdReferenceFixture(t, 2, 2, 2)
	if err = s.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	for _, p := range packets[2:] {
		if _, err = sender.Write(p); err != nil {
			t.Fatal(err)
		}
	}
	for i := 0; i < 2; i++ {
		buf := make([]byte, 2000)
		n, _, readErr := s.ReadFrom(buf)
		if readErr != nil || !bytes.Equal(buf[:n], packets[i]) {
			t.Fatal("real socket timer", i, readErr)
		}
	}
	if s.stats.Recovered != 2 || s.pendingBytes != 0 || s.heldBytes != 0 {
		t.Fatal(s.stats)
	}
	if err = s.SetReadDeadline(time.Time{}); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { _, _, e := s.ReadFrom(make([]byte, 2000)); done <- e }()
	for i := 0; i < 20; i++ {
		if err = s.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
			t.Fatal(err)
		}
	}
	if err = s.Close(); err != nil {
		t.Fatal(err)
	}
	select {
	case e := <-done:
		if !errors.Is(e, net.ErrClosed) {
			t.Fatal("close did not unblock", e)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("blocked ReadFrom leaked")
	}
}

func TestHoldCRCFailureDoesNotReturnPartialRecovery(t *testing.T) {
	gfInit()
	packets := holdReferenceFixture(t, 2, 2, 2)
	bad := append([]byte(nil), packets[2]...)
	bad[len(bad)-parseFecBlock(bad).symLen+100] ^= 1
	s, _ := holdTestConn([][]byte{bad, packets[3]}, defaultHoldConfig())
	out := holdReadAll(t, s)
	if len(out) != 0 || s.stats.Recovered != 0 || s.stats.RecoverFail != 1 || s.stats.HoldDiscardBytes != 2662 || s.heldBytes != 0 {
		t.Fatal("CRC atomicity", s.stats)
	}
}

func TestHoldDeadlinePacketTiesAndLateSymbols(t *testing.T) {
	gfInit()
	for _, offset := range []int64{-1, 0, 1} {
		packets := holdReferenceFixture(t, 2, 1, 1)
		s, c := holdTestConn([][]byte{packets[2], packets[0], packets[1]}, defaultHoldConfig())
		deadline := int64(1000 + (1200+1217)*4000 + 1_000_000)
		c.frames[2].at = time.Unix(0, deadline+offset)
		buf := make([]byte, 2000)
		if n, _, err := s.ReadFrom(buf); err != nil || !bytes.Equal(buf[:n], packets[0]) {
			t.Fatal(err)
		}
		n, _, err := s.ReadFrom(buf)
		if err != nil {
			t.Fatal(err)
		}
		if offset < 0 {
			if !bytes.Equal(buf[:n], packets[2]) || s.stats.Recovered != 0 {
				t.Fatal("early final original")
			}
		} else {
			if !bytes.Equal(buf[:n], packets[1]) || s.stats.Recovered != 1 || s.stats.BytesIn != 2531 || c.now.UnixNano() != deadline {
				t.Fatal("timer prefix", offset, s.stats, c.now)
			}
		}
		holdReadAll(t, s)
	}
	packets := holdReferenceFixture(t, 4, 4, 4)
	s, c := holdTestConn([][]byte{packets[4], packets[0], packets[5], packets[1]}, defaultHoldConfig())
	remaining := 3*1331 + 1200 + 1217 + 1234 + 1251
	deadline := int64(1000 + remaining*4000 + 1_000_000)
	c.frames[2].at = time.Unix(0, deadline+1000)
	c.frames[3].at = time.Unix(0, deadline+2000)
	out := holdReadAll(t, s)
	if len(out) != 4 || s.stats.Recovered != 2 {
		t.Fatal("decision closed prematurely")
	}
	for i := range out {
		if !bytes.Equal(out[i], packets[i]) {
			t.Fatal("late symbol bytes", i)
		}
	}
}

func holdReferenceOutput(t *testing.T, k, m, lead int, code string, packets [][]byte, useUDP ...bool) []byte {
	t.Helper()
	dgs := [][]byte{}
	if code != "-" {
		for _, c := range code {
			i := int(c - '0')
			if i < 0 || i >= len(packets) {
				t.Fatal("symbol", code)
			}
			dgs = append(dgs, packets[i])
		}
	}
	s, c := holdTestConn(dgs, defaultHoldConfig())
	read := s.ReadFrom
	if len(useUDP) > 0 && useUDP[0] {
		read = udpReferenceReader(s, c)
	}
	for i, d := range dgs {
		fb := parseFecBlock(d)
		if fb == nil {
			continue
		}
		remaining := (m - fb.index - 1) * 1331
		if fb.index < lead {
			for j := 0; j < k; j++ {
				remaining += 1200 + 17*j
			}
		}
		c.stop = time.Unix(0, int64(i+1)*1000+int64(remaining)*4000+1_000_000)
		break
	}
	if c.stop.IsZero() {
		c.stop = time.Unix(0, 1)
	}
	actualReturned := int64(0)
	c.check = func() {
		physical := int64(0)
		for _, frame := range c.frames[:c.i] {
			physical += int64(len(frame.data))
		}
		if s.stats.BytesIn != physical || s.stats.BytesToStack != actualReturned || s.stats.BytesToStack+s.pendingBytes > physical {
			t.Fatalf("reference prefix %d %d %d %s", k, m, lead, code)
		}
	}
	delivered := make([][]any, 0)
	recSeen := map[int]bool{}
	complete := map[int]bool{}
	for attempts := 0; attempts < 30; attempts++ {
		buf := make([]byte, 2000)
		n, _, err := read(buf)
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		actualReturned += int64(n)
		if s.stats.BytesToStack != actualReturned || actualReturned+s.pendingBytes > s.stats.BytesIn {
			t.Fatal("returned accounting")
		}
		id := -1
		for j, p := range packets {
			if bytes.Equal(buf[:n], p) {
				id = j
				break
			}
		}
		if id < 0 {
			t.Fatal("unknown returned bytes")
		}
		kind, index, recovered := "p", id-k, false
		if id < k {
			kind, index = "o", id
			complete[id] = true
			for _, fr := range s.hold.flights {
				for _, r := range fr.recovered {
					if r == id && !recSeen[id] {
						recovered = true
						recSeen[id] = true
					}
				}
			}
		}
		delivered = append(delivered, []any{kind, index, n, recovered, c.now.UnixNano()})
	}
	used, recovered := make([]int, 0), make([]int, 0)
	var created, deadline, terminal any
	for _, fr := range s.hold.flights {
		used = append(used, fr.used...)
		recovered = append(recovered, fr.recovered...)
		created, deadline = fr.created.UnixNano(), fr.deadline.UnixNano()
		if fr.terminal != "" {
			terminal = fr.terminal
		}
	}
	result := map[string]any{"complete": len(complete) == k, "used": used, "recovered": recovered, "delivered": delivered,
		"bytes_in": s.stats.BytesIn, "bytes_to_stack": s.stats.BytesToStack, "held_bytes": s.heldBytes, "pending_bytes": s.pendingBytes,
		"discard_bytes": s.stats.HoldDiscardBytes, "consumed_overhead": s.stats.BytesIn - s.stats.BytesToStack - s.pendingBytes - s.heldBytes - s.stats.HoldDiscardBytes,
		"created_ns": created, "deadline_ns": deadline, "terminal": terminal}
	encoded, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func TestHoldPythonReadFromReference(t *testing.T) { runHoldPythonReference(t, false) }

func TestUDPHoldPythonReadBatchReference(t *testing.T) { runHoldPythonReference(t, true) }

func runHoldPythonReference(t *testing.T, useUDP bool) {
	path := os.Getenv("M1_REFERENCE_GZIP")
	if path == "" {
		t.Skip("M1_REFERENCE_GZIP is required for the full wire gate")
	}
	gfInit()
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	gz, err := gzip.NewReader(f)
	if err != nil {
		t.Fatal(err)
	}
	defer gz.Close()
	scanner := bufio.NewScanner(gz)
	fixtures := map[string][][]byte{}
	counts := map[string]int{}
	group := ""
	seen := map[string]bool{}
	total := 0
	for scanner.Scan() {
		fields := strings.Split(scanner.Text(), "\t")
		if len(fields) != 5 {
			t.Fatal("reference row")
		}
		k, e1 := strconv.Atoi(fields[0])
		m, e2 := strconv.Atoi(fields[1])
		lead, e3 := strconv.Atoi(fields[2])
		if e1 != nil || e2 != nil || e3 != nil || k < 1 || k > 4 || m < 0 || m > 4 || lead < 0 || lead > m {
			t.Fatal("reference config")
		}
		key := strings.Join(fields[:3], "/")
		if group != key {
			if counts[key] != 0 {
				t.Fatal("repeated group")
			}
			group = key
			seen = map[string]bool{}
		}
		code := fields[3]
		if seen[code] {
			t.Fatal("duplicate case", key, code)
		}
		seen[code] = true
		if fixtures[key] == nil {
			fixtures[key] = holdReferenceFixture(t, k, m, lead)
		}
		actual := holdReferenceOutput(t, k, m, lead, code, fixtures[key], useUDP)
		if fmt.Sprintf("%x", sha256.Sum256(actual)) != fields[4] {
			t.Fatalf("case %s %s: actual %s expected sha %s", key, code, actual, fields[4])
		}
		counts[key]++
		total++
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	for k := 1; k <= 4; k++ {
		for m := 0; m <= 4; m++ {
			for lead := 0; lead <= m; lead++ {
				key := fmt.Sprintf("%d/%d/%d", k, m, lead)
				expected, term := 1, 1
				for n := 1; n <= k+m; n++ {
					term *= k + m - n + 1
					expected += term
				}
				if counts[key] != expected {
					t.Fatal("missing cases", key, counts[key], expected)
				}
			}
		}
	}
	if total != 700116 || len(counts) != 60 {
		t.Fatal(total, len(counts))
	}
	t.Logf("700116 actual decoder cases, 60 configurations, byte equality and prefix accounting match Python")
}
