package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"hash/crc32"
	"net"
	"reflect"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/quic-go/quic-go/qlog"
)

func observationParities(originals [][]byte, m int, version int) [][]byte {
	size := 0
	for _, o := range originals {
		size = max(size, len(o))
	}
	crcs := []uint32{}
	lens := []uint16{}
	padded := [][]byte{}
	for _, o := range originals {
		crcs = append(crcs, crc32.ChecksumIEEE(o))
		lens = append(lens, uint16(len(o)))
		b := make([]byte, size)
		copy(b, o)
		padded = append(padded, b)
	}
	pars := rsEncode(padded, m, size)
	packets := [][]byte{}
	h := parseLongHdr(originals[0])
	for i, p := range pars {
		packets = append(packets, buildParity(h.dcid, h.scid, fecBlock{ver: version, flight: 1, k: len(originals), m: m, index: i, symLen: size, crcs: crcs, lens: lens, sym: p}))
	}
	return packets
}

func drainObservation(s *decodeConn) {
	b := make([]byte, 2000)
	for {
		if _, _, err := s.ReadFrom(b); err != nil {
			return
		}
	}
}

func TestObservationFeedbackVersions(t *testing.T) {
	r := fbRec{crcs: []uint32{1, 2}, recovered: []uint32{3, 4}, recov: 2}
	p := buildFeedback([]byte{9}, []byte{8}, r)
	x := parseFeedback(p)
	if x == nil || x.version != 3 || !reflect.DeepEqual(x.crcs, r.crcs) || !reflect.DeepEqual(x.recovered, r.recovered) {
		t.Fatalf("v3: %+v", x)
	}
	for cut := 0; cut < len(p); cut++ {
		if parseFeedback(p[:cut]) != nil {
			t.Fatalf("truncated %d", cut)
		}
	}
	if parseFeedback(append(append([]byte{}, p...), 0)) != nil {
		t.Fatal("accepted trailing bytes")
	}
	h := parseLongHdr(p)
	start := h.bodyOff + 3
	legacy := append([]byte{}, p[:start+12+4*len(r.crcs)]...)
	legacy[start+4] = 2
	binary.BigEndian.PutUint16(legacy[h.bodyOff+1:h.bodyOff+3], uint16(0x4000+len(legacy)-start))
	x = parseFeedback(legacy)
	if x == nil || x.version != 2 || len(x.recovered) != 0 || !reflect.DeepEqual(x.crcs, r.crcs) {
		t.Fatalf("v2: %+v", x)
	}
	legacy[start+4] = 1
	if parseFeedback(legacy) != nil {
		t.Fatal("accepted unsupported version")
	}
	r.recovered = make([]uint32, fbCRCCap+1)
	x = parseFeedback(buildFeedback([]byte{9}, []byte{8}, r))
	if x == nil || !x.recoveredTruncated || x.truncated || len(x.recovered) != fbCRCCap {
		t.Fatalf("recovery cap: %+v", x)
	}
}

func TestObservationArrivalsSeparateRecovery(t *testing.T) {
	c := &fecConn{ffOrigCRC: []uint32{10, 11}, ffParCRC: []uint32{12}, fbCount: 1, fbLast: &fbRec{version: 3, crcs: []uint32{11, 12, 12, 99}, recovered: []uint32{10, 10, 100}}}
	a, d := c.arrivalEvidence(true)
	if a.Src != "c1" || a.Sent != 3 || a.Lost != 1 || a.Trunc || !reflect.DeepEqual(a.Bitmap, []int{0, 1, 1}) || d.RecoveredOriginal != 1 || d.OtherRecoveredCRC != 1 || d.OtherCRC != 1 {
		t.Fatalf("arrivals=%+v diagnostic=%+v", a, d)
	}
	if _, err := p3NormalizeArrivals([]*p3Arrivals{&a}); err != nil {
		t.Fatal(err)
	}
	c.fbLast.truncated = true
	a, _ = c.arrivalEvidence(true)
	if !a.Trunc {
		t.Fatal("missing truncation")
	}
	c.fbLast.truncated = false
	c.ffOrigCRC = []uint32{10, 10}
	a, _ = c.arrivalEvidence(true)
	if !a.Trunc {
		t.Fatal("ambiguous CRC")
	}
	c.ffOrigCRC = []uint32{10, 11}
	c.ffSendFailed = true
	a, _ = c.arrivalEvidence(true)
	if !a.Trunc {
		t.Fatal("write failure not censored")
	}
	a, _ = c.arrivalEvidence(false)
	if a.Src != "none" || a.Sent != 0 || a.Bitmap != nil {
		t.Fatal(a)
	}
	c.fbLast = nil
	a, _ = c.arrivalEvidence(true)
	if a.Src != "none" || a.Sent != 0 || a.Lost != 0 {
		t.Fatal(a)
	}
}

func TestObservationRecoveredHandshakeFeedback(t *testing.T) {
	gfInit()
	o := auditInitial(42)
	hs := auditInitial(43)
	hs[0] = 0xe3
	for _, kind := range []string{"immediate", "pending", "late"} {
		t.Run(kind, func(t *testing.T) {
			var dgs [][]byte
			wantRecovered := 1
			switch kind {
			case "immediate":
				dgs = observationParities([][]byte{hs}, 1, 0)
			case "pending":
				p := observationParities([][]byte{o, hs}, 3, 0)
				dgs = p
				wantRecovered = 2
			case "late":
				p := observationParities([][]byte{o, hs}, 1, 0)
				dgs = append(p, o)
			}
			wire := &auditConn{scriptConn: scriptConn{dgs: dgs, addr: &net.UDPAddr{Port: 5555}}}
			s := &decodeConn{countConn: countConn{PacketConn: wire}, mode: "fec", feedback: true}
			drainObservation(s)
			if len(wire.written) != 1 {
				t.Fatalf("feedback %d", len(wire.written))
			}
			r := parseFeedback(wire.written[0])
			if r == nil || len(r.recovered) != wantRecovered || !inCRC(r.recovered, crc32.ChecksumIEEE(hs)) || inCRC(r.crcs, crc32.ChecksumIEEE(hs)) {
				t.Fatalf("feedback %+v", r)
			}
			if s.stats.BytesToStack > s.stats.BytesIn {
				t.Fatal("credit inflation")
			}
		})
	}
}

type observationHoldConn struct {
	*holdScriptConn
	written [][]byte
}

func (c *observationHoldConn) WriteTo(b []byte, _ net.Addr) (int, error) {
	c.written = append(c.written, append([]byte{}, b...))
	return len(b), nil
}

func TestObservationHoldRecoveredHandshake(t *testing.T) {
	gfInit()
	hs := auditInitial(43)
	hs[0] = 0xe3
	p := observationParities([][]byte{hs}, 1, fecVerLead)
	s, c := holdTestConn(p, defaultHoldConfig())
	w := &observationHoldConn{holdScriptConn: c}
	s.PacketConn = w
	s.feedback = true
	drainObservation(s)
	if len(w.written) != 1 {
		t.Fatalf("feedback %d", len(w.written))
	}
	r := parseFeedback(w.written[0])
	if r == nil || !inCRC(r.recovered, crc32.ChecksumIEEE(hs)) || inCRC(r.crcs, crc32.ChecksumIEEE(hs)) {
		t.Fatalf("feedback %+v", r)
	}
}

func TestObservationFinalUnrecoverable(t *testing.T) {
	gfInit()
	originals := [][]byte{auditInitial(1), auditInitial(2)}
	pars := observationParities(originals, 3, 0)
	for _, recovered := range []bool{false, true} {
		dgs := [][]byte{pars[1]}
		if recovered {
			dgs = append(dgs, pars[2])
		}
		s := &decodeConn{mode: "fec", countConn: countConn{PacketConn: &auditConn{scriptConn: scriptConn{dgs: dgs, addr: &net.UDPAddr{Port: 5555}}}}}
		drainObservation(s)
		if s.stats.Unrecover != 1 {
			t.Fatalf("seen %d", s.stats.Unrecover)
		}
		before := s.snapshot()
		if before.FlightsPending != 1 || before.FlightsFinalized != 0 {
			t.Fatal(before)
		}
		s.mu.Lock()
		a := s.observationStatsLocked(time.Now().Add(2 * time.Second))
		b := s.observationStatsLocked(time.Now().Add(2 * time.Second))
		s.expireLocked(time.Now().Add(2 * time.Second))
		s.mu.Unlock()
		want := 1
		if recovered {
			want = 0
		}
		if a.UnrecoverFinal != want || a.FlightsFinalized != 1 || b != a || s.stats.FlightsFinalized != 1 {
			t.Fatalf("recovered %v: %+v / %+v", recovered, a, b)
		}
	}
}

func TestObservationHoldFinalUnrecoverable(t *testing.T) {
	gfInit()
	o := [][]byte{auditInitial(1), auditInitial(2)}
	pars := observationParities(o, 2, fecVerLead)
	for _, complete := range []bool{false, true} {
		dgs := [][]byte{pars[0]}
		if complete {
			dgs = append(dgs, pars[1])
		}
		s, c := holdTestConn(dgs, defaultHoldConfig())
		c.stop = c.now.Add(2 * time.Second)
		drainObservation(s)
		c.now = c.now.Add(2 * time.Second)
		x := s.snapshot()
		want := 1
		if complete {
			want = 0
		}
		if x.UnrecoverFinal != want || x.FlightsFinalized != 1 {
			t.Fatalf("complete %v: %+v", complete, x)
		}
	}
}

func TestObservationTraceAndSnapshot(t *testing.T) {
	m := newMemoryTrace(time.Unix(100, 0))
	m.now = func() time.Time { return time.Unix(100, 123) }
	var ack qlog.AckFrame
	if err := json.Unmarshal([]byte(`{"AckRanges":[{"Smallest":2,"Largest":5},{"Smallest":0,"Largest":0}]}`), &ack); err != nil {
		t.Fatal(err)
	}
	m.RecordEvent(qlog.PacketReceived{Header: qlog.PacketHeader{PacketType: qlog.PacketTypeInitial, PacketNumber: 3}, Raw: qlog.RawInfo{Length: 41}, Frames: []qlog.Frame{{Frame: &ack}, {Frame: &qlog.CryptoFrame{Offset: 0, Length: 99}}}})
	m.RecordEvent(qlog.MetricsUpdated{MinRTT: 50 * time.Millisecond, LatestRTT: 60 * time.Millisecond})
	m.RecordEvent(qlog.MetricsUpdated{CongestionWindow: 123})
	m.RecordEvent(qlog.LossTimerUpdated{Type: qlog.LossTimerUpdateTypeExpired, TimerType: qlog.TimerTypePTO})
	m.RecordEvent(qlog.PTOCountUpdated{PTOCount: 0})
	m.RecordEvent(qlog.LossTimerUpdated{Type: qlog.LossTimerUpdateTypeExpired, TimerType: qlog.TimerTypeACK})
	m.datagram(auditInitial(1), false)
	m.datagram(bytes.Repeat([]byte{0}, serverFlightMin), false)
	m.datagram(auditInitial(2), false)
	x := m.snapshot()
	if x.PTOCount != 1 || len(x.PTO) != 1 || len(x.RTT) != 1 || x.RTT[0].MinNS != 50e6 || x.Packets[0].AtNS != 123 || !reflect.DeepEqual(x.Packets[0].ACKRanges, [][2]int64{{2, 5}, {0, 0}}) {
		t.Fatalf("trace %+v", x)
	}
	if !x.Datagrams[0].BeforeBig || x.Datagrams[1].BeforeBig || x.Datagrams[2].BeforeBig {
		t.Fatal(x.Datagrams)
	}
	if x.ServerBytes != int64(2*len(auditInitial(1))+serverFlightMin) || x.PTOScope != "qlog_loss_timer_expired_lower_bound" {
		t.Fatal(x)
	}
	x.Packets[0].ACKRanges[0][0] = 99
	x.Packets[0].Crypto[0][0] = 99
	x.RTT[0].LatestNS = 1
	x.Datagrams[0].Bytes = 1
	y := m.snapshot()
	if y.Packets[0].ACKRanges[0][0] != 2 || y.Packets[0].Crypto[0][0] != 0 || y.RTT[0].LatestNS != 60e6 || y.Datagrams[0].Bytes == 1 {
		t.Fatal("snapshot aliases")
	}
}

func TestObservationBoundedConcurrentTrace(t *testing.T) {
	m := newMemoryTrace(time.Now())
	var wg sync.WaitGroup
	for range 4 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for range observationCap {
				m.RecordEvent(qlog.PacketSent{})
				m.datagram([]byte{1}, false)
			}
		}()
	}
	wg.Wait()
	x := m.snapshot()
	if !x.Truncated || len(x.Packets) != observationCap || len(x.Datagrams) != observationCap {
		t.Fatalf("bounds %d %d %v", len(x.Packets), len(x.Datagrams), x.Truncated)
	}
}

func TestObservationInjectedParityLossIncluded(t *testing.T) {
	gfInit()
	w := &auditConn{}
	c := &fecConn{mode: "fec", m: 1, expectK: 1, dropParity: 0, corruptParity: -1, countConn: countConn{PacketConn: w}}
	o := auditInitial(1)
	if _, err := c.WriteTo(o, &net.UDPAddr{Port: 5555}); err != nil {
		t.Fatal(err)
	}
	c.fbLast = &fbRec{version: 3, crcs: []uint32{crc32.ChecksumIEEE(o)}}
	a, _ := c.arrivalEvidence(true)
	if a.Sent != 2 || a.Lost != 1 || !reflect.DeepEqual(a.Bitmap, []int{1, 0}) {
		t.Fatal(a)
	}
}

func TestObservationFeedbackCollectionDeadline(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		c := &fecConn{}
		start := time.Now()
		time.AfterFunc(250*time.Millisecond, func() { c.mu.Lock(); c.fbCount++; c.mu.Unlock() })
		if c.waitFeedback(200 * time.Millisecond) {
			t.Fatal("accepted a future reply")
		}
		if !c.waitFeedback(time.Second) {
			t.Fatal("missed delayed reply")
		}
		if time.Since(start) < 250*time.Millisecond || time.Since(start) > 251*time.Millisecond {
			t.Fatal(time.Since(start))
		}
	})
}

func TestObservationLateOriginalSettlesEveryKnownFlight(t *testing.T) {
	o := auditInitial(31)
	crc := crc32.ChecksumIEEE(o)
	for range 128 {
		fb := &fecBlock{k: 1, m: 1, crcs: []uint32{crc}, lens: []uint16{uint16(len(o))}, symLen: len(o)}
		first := &flightRec{fb: fb, dcid: dcidOf(o), created: time.Now(), done: true, recCRC: map[uint32]bool{crc: true}}
		second := &flightRec{fb: fb, dcid: dcidOf(o), created: time.Now(), poisoned: true}
		s := &decodeConn{flights: map[string]*flightRec{"recovered": first, "poisoned": second}}
		s.noteOriginal(o, &net.UDPAddr{Port: 5555})
		s.mu.Lock()
		s.expireLocked(time.Now().Add(2 * time.Second))
		s.mu.Unlock()
		if s.stats.FlightsFinalized != 2 || s.stats.UnrecoverFinal != 0 || s.stats.PrematureRecover != 1 {
			t.Fatal(s.stats)
		}
	}
}
