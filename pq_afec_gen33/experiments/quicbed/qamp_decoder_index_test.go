package main

import (
	"bytes"
	"errors"
	"fmt"
	"hash/crc32"
	"net"
	"testing"
	"time"
)

func TestDecoderOriginalIndexBoundsAndExpiry(t *testing.T) {
	var x originalIndex
	now := time.Now()
	g := decoderGroup{"one", &connAcct{}}
	for i := 0; i < 100; i++ {
		x.add(g, []byte{byte(i)}, now.Add(time.Duration(i)))
	}
	if x.age.Len() != 64 || x.find(g, crc32.ChecksumIEEE([]byte{0}), 1) != nil || x.groups[g].Len() != 64 {
		t.Fatal("group bound", x.age.Len())
	}
	for i := 0; i < 1000; i++ {
		x.add(decoderGroup{fmt.Sprint(i), nil}, []byte{9}, now.Add(1000+time.Duration(i)))
	}
	if x.age.Len() != recentCap || len(x.groups) != recentCap || len(x.keys) != recentCap {
		t.Fatal("global bound", x.age.Len(), len(x.groups), len(x.keys))
	}
	x.expire(now.Add(recentTTL+time.Second), recentTTL)
	if x.age.Len() != 0 || len(x.groups) != 0 || len(x.keys) != 0 {
		t.Fatal("expiry leaked indexes")
	}
}

func TestDecoderOriginalIndexDuplicatesAndAccountIsolation(t *testing.T) {
	var x originalIndex
	now := time.Now()
	a, b := decoderGroup{"same", &connAcct{}}, decoderGroup{"same", &connAcct{}}
	data := []byte{1, 2, 3}
	cr := crc32.ChecksumIEEE(data)
	x.add(a, data, now)
	x.add(a, data, now.Add(time.Second))
	data[0] = 9
	if !bytes.Equal(x.find(a, cr, 3), []byte{1, 2, 3}) || x.find(b, cr, 3) != nil || x.find(a, cr, 2) != nil {
		t.Fatal("lookup mixed payloads or identities")
	}
	x.expire(now.Add(recentTTL), recentTTL)
	if x.age.Len() != 1 || x.find(a, cr, 3) == nil {
		t.Fatal("expired duplicate erased newer source")
	}
	x.expire(now.Add(recentTTL+time.Second), recentTTL)
	if x.find(a, cr, 3) != nil || len(x.keys) != 0 {
		t.Fatal("last duplicate retained")
	}
}

func TestDecoderSkipsNonInitialAndOversizeOriginals(t *testing.T) {
	s := &decodeConn{}
	initial := auditInitial(1)
	handshake := append([]byte(nil), initial...)
	handshake[0] = 0xe3
	for _, data := range [][]byte{{0x40, 1}, handshake, append(initial, make([]byte, 1473)...)} {
		s.noteOriginal(data, nil)
	}
	if s.recent.age.Len() != 0 || s.stats.DecoderOriginalIgnored != 3 || s.stats.DecoderRecentLookups != 0 {
		t.Fatal(s.stats)
	}
	s.noteOriginal(initial, nil)
	if s.recent.age.Len() != 1 || s.stats.Originals != 4 {
		t.Fatal(s.stats)
	}
}

func TestDecoderBoundedFlightsAndConnectionLocalWork(t *testing.T) {
	now := time.Now()
	s := &decodeConn{}
	base := &fecBlock{k: 2, m: 1, symLen: 1200, crcs: []uint32{1, 2}, lens: []uint16{1200, 1200}}
	for i := 0; i < decoderFlightCap; i++ {
		fb := *base
		fb.flight = uint16(i)
		dc := fmt.Sprint(i)
		if s.legacyFlightLocked(dc, dc, nil, nil, &fb, now) == nil {
			t.Fatal("early global bound", i)
		}
	}
	if s.legacyFlightLocked("extra", "extra", nil, nil, base, now) != nil || s.stats.DecoderFlightCap != 1 {
		t.Fatal("unbounded global flights")
	}
	s.noteOriginal(auditInitial(1), nil)
	if s.stats.DecoderFlightVisits != 0 || s.stats.DecoderRecentLookups != 0 {
		t.Fatal("unrelated flights scanned", s.stats)
	}
	s.expireLocked(now.Add(2 * flightTTL))
	if len(s.flights) != 0 || s.decoder.age.Len() != 0 || len(s.decoder.groups) != 0 {
		t.Fatal("flight expiry leaked indexes")
	}
	for i := 0; i < decoderGroupFlightCap; i++ {
		fb := *base
		fb.flight = uint16(i)
		if s.legacyFlightLocked(fmt.Sprint(i), dcidOf(auditInitial(1)), nil, nil, &fb, time.Now()) == nil {
			t.Fatal("early group bound")
		}
	}
	if s.legacyFlightLocked("next", dcidOf(auditInitial(1)), nil, nil, base, time.Now()) != nil {
		t.Fatal("unbounded group")
	}
	s.stats.DecoderFlightVisits, s.stats.DecoderRecentLookups = 0, 0
	s.noteOriginal(auditInitial(1), nil)
	if s.stats.DecoderFlightVisits != 2*decoderGroupFlightCap || s.stats.DecoderRecentLookups != 2*decoderGroupFlightCap {
		t.Fatal("unexpected group work", s.stats)
	}
}

func TestDecoderDuplicateParityAndPayloadRelease(t *testing.T) {
	gfInit()
	_, parity := decoderFixture(3)
	s := &decodeConn{mode: "fec"}
	for range 100 {
		s.feedOne(parity[1])
	}
	if len(s.flights) != 1 || s.stats.DecoderDuplicate != 99 || s.heldBytes != int64(len(parity[1])) {
		t.Fatal("duplicate accumulated", s.stats, s.heldBytes)
	}
	if s.decoder.memory != int64(parseFecBlock(parity[1]).symLen) {
		t.Fatal("symbol memory", s.decoder.memory)
	}
	s.feedOne(parity[2])
	if s.stats.Recovered != 2 || s.decoder.memory != 0 || s.heldBytes != 0 {
		t.Fatal("settlement retained payload", s.stats, s.decoder.memory, s.heldBytes)
	}
	for _, fr := range s.flights {
		if fr.fb.sym != nil || len(fr.syms) != 0 {
			t.Fatal("payload alias retained")
		}
	}
}

func TestDecoderPayloadCapDoesNotRemoveExistingFlights(t *testing.T) {
	s := &decodeConn{}
	fb := &fecBlock{k: 32, m: 32, symLen: 1472, crcs: make([]uint32, 32), lens: make([]uint16, 32)}
	for i := range fb.lens {
		fb.lens[i] = 1472
	}
	fr := s.legacyFlightLocked("one", "one", nil, nil, fb, time.Now())
	for i := 0; i < 32; i++ {
		p := *fb
		p.index, p.sym = i, make([]byte, 1472)
		if !s.addLegacySymbolLocked(fr, &p) {
			break
		}
	}
	if !fr.poisoned || s.stats.DecoderPayloadCap != 1 || s.decoder.memory != 0 || len(s.flights) != 1 {
		t.Fatal("per flight bound", s.stats, s.decoder.memory)
	}
	fr2 := s.legacyFlightLocked("two", "two", nil, nil, fb, time.Now())
	s.pendingBytes = decoderPayloadCap - decoderInputReserve
	fb.sym = make([]byte, 1472)
	if s.addLegacySymbolLocked(fr2, fb) || !fr2.poisoned || s.decoder.memory != 0 {
		t.Fatal("global pending reserve ignored")
	}
}

func TestDecoderAllLostUnknownDCIDStillRecovers(t *testing.T) {
	gfInit()
	o := [][]byte{auditInitial(9)}
	p := observationParities(o, 1, fecVerLead)[0]
	s := &decodeConn{mode: "fec"}
	s.PacketConn = &scriptConn{dgs: [][]byte{p}, addr: &net.UDPAddr{Port: 1234}}
	b := make([]byte, 2000)
	n, _, err := s.ReadFrom(b)
	if err != nil || !bytes.Equal(b[:n], o[0]) || s.stats.Recovered != 1 || s.recent.age.Len() != 0 {
		t.Fatal("parity-only recovery", err, s.stats)
	}
	if s.stats.BytesToStack != int64(n) || s.stats.BytesToStack > s.stats.BytesIn {
		t.Fatal("parity-only accounting")
	}
}

func TestDecoderHoldIndexBoundsAndDelayedExpiry(t *testing.T) {
	gfInit()
	o := [][]byte{auditInitial(1), auditInitial(2)}
	pars := observationParities(o, 2, fecVerLead)
	s, c := holdTestConn(nil, defaultHoldConfig())
	ca := &connAcct{RxBytes: 1 << 20}
	s.stats.BytesIn = 1 << 20
	now := c.now
	for i := 0; i < decoderGroupFlightCap+1; i++ {
		fb := *parseFecBlock(pars[0])
		fb.flight = uint16(i)
		s.holdReceiveLocked(pars[0], len(pars[0]), &fb, &net.UDPAddr{Port: 5555}, ca, now)
	}
	if len(s.hold.flights) != decoderGroupFlightCap || len(s.hold.events) != 3*decoderGroupFlightCap || s.stats.DecoderFlightCap != 1 {
		t.Fatal("hold flight bound", s.stats, len(s.hold.events))
	}
	s.hold.recent.add(decoderGroup{dcidOf(o[0]), ca}, o[0], now)
	s.hold.recent.add(decoderGroup{dcidOf(o[1]), ca}, o[1], now)
	s.holdTickLocked(now.Add(2 * time.Second))
	if s.stats.Recovered != 0 || s.heldBytes != 0 || s.hold.memory != 0 {
		t.Fatal("late timer recovered expired flight", s.stats)
	}
	s.holdTickLocked(now.Add(4 * time.Second))
	if len(s.hold.flights) != 0 || len(s.hold.events) != 0 || len(s.hold.groups) != 0 || s.hold.recent.age.Len() != 0 {
		t.Fatal("hold expiry leaked indexes")
	}
}

func TestDecoderCloseReleasesBothIndexes(t *testing.T) {
	gfInit()
	_, pars := decoderFixture(3)
	s := &decodeConn{mode: "fec"}
	s.PacketConn = &holdScriptConn{}
	s.feedOne(pars[1])
	s.noteOriginal(auditInitial(99), nil)
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	if s.decoder != nil || len(s.flights) != 0 || s.recent.age.Len() != 0 || s.heldBytes != 0 || s.pendingBytes != 0 {
		t.Fatal("close retained legacy state")
	}
	s.feedOne(pars[1])
	s.noteOriginal(auditInitial(99), nil)
	if s.decoder != nil || len(s.flights) != 0 || s.recent.age.Len() != 0 || s.heldBytes != 0 {
		t.Fatal("post-close work recreated payloads")
	}
}

func TestDecoderCloseDuringLegacyRead(t *testing.T) {
	gfInit()
	_, pars := decoderFixture(3)
	c := &holdScriptConn{frames: []holdFrame{{time.Now(), pars[1]}}}
	s := &decodeConn{mode: "fec"}
	s.PacketConn = c
	c.afterRead = func() {
		if err := s.Close(); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := s.ReadFrom(make([]byte, 2000)); !errors.Is(err, net.ErrClosed) {
		t.Fatal(err)
	}
	if s.decoder != nil || len(s.flights) != 0 || s.recent.age.Len() != 0 || s.heldBytes != 0 {
		t.Fatal("closed receiver recreated state")
	}
}

func TestDecoderForeignFlightsPreserveRealRecovery(t *testing.T) {
	gfInit()
	src, parity := decoderFixture(3)
	s := &decodeConn{mode: "fec"}
	for i := 0; i < 1000; i++ {
		fb := *parseFecBlock(parity[1])
		fb.flight = uint16(i)
		dc := fmt.Sprint(i)
		fr := s.legacyFlightLocked(dc, dc, nil, nil, &fb, time.Now())
		if fr == nil || !s.addLegacySymbolLocked(fr, &fb) {
			t.Fatal("flood fixture")
		}
	}
	s.PacketConn = &scriptConn{dgs: [][]byte{src[0], parity[1]}, addr: &net.UDPAddr{Port: 5555}}
	b := make([]byte, 2000)
	if n, _, err := s.ReadFrom(b); err != nil || !bytes.Equal(b[:n], src[0]) {
		t.Fatal(err)
	}
	if n, _, err := s.ReadFrom(b); err != nil || !bytes.Equal(b[:n], src[1]) {
		t.Fatal(err)
	}
	if s.stats.Recovered != 1 || s.stats.DecoderFlightVisits != 0 || s.stats.DecoderRecentLookups != 2 {
		t.Fatal(s.stats)
	}
}

func TestDecoderEvictedKnownOriginalCannotBeReinjected(t *testing.T) {
	gfInit()
	src := [][]byte{auditInitial(1), auditInitial(2), auditInitial(3)}
	par := observationParities(src, 1, fecVerLead)[0]
	for _, hold := range []bool{false, true} {
		s := &decodeConn{mode: "fec"}
		if hold {
			s.hold = newHoldState(defaultHoldConfig())
		}
		now := time.Now()
		ca := &connAcct{RxBytes: 1 << 20}
		s.stats.BytesIn = 1 << 20
		group := decoderGroup{dcidOf(src[0]), ca}
		fb := parseFecBlock(par)
		if hold {
			s.hold.recent.add(group, src[0], now)
			s.holdReceiveLocked(par, len(par), fb, nil, ca, now)
			for i := 0; i < 64; i++ {
				s.hold.recent.add(group, auditInitial(byte(100+i)), now)
			}
			for _, fr := range s.hold.flights {
				s.holdSettleLocked(fr, now, nil, nil)
				if fr.terminal != "source_evicted" {
					t.Fatal(fr.terminal)
				}
			}
		} else {
			s.recent.add(group, src[0], now)
			fr := s.legacyFlightLocked("target", group.dcid, ca, nil, fb, now)
			s.addLegacySymbolLocked(fr, fb)
			s.tryRecoverLocked(fr, false)
			for i := 0; i < 64; i++ {
				s.recent.add(group, auditInitial(byte(100+i)), now)
			}
			if outs := s.tryRecoverLocked(fr, false); len(outs) != 0 || !fr.poisoned {
				t.Fatal("evicted original reconstructed")
			}
		}
		if s.stats.Recovered != 0 || s.stats.DecoderEvictedSource != 1 || s.heldBytes != 0 {
			t.Fatal(hold, s.stats, s.heldBytes)
		}
	}
}
