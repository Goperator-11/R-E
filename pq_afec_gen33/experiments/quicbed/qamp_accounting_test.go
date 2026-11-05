package main

import (
	"encoding/binary"
	"hash/crc32"
	"net"
	"testing"
)

func accountingPacket(typ byte, dcid, scid []byte) []byte {
	// Server CIDs have exactly four bytes in the actual transport. Keep
	// markers compact in fixtures while encoding the same server CID shape.
	if len(dcid) == 1 && dcid[0] >= 21 && dcid[0] <= 31 {
		dcid = []byte{dcid[0], 0, 0, 0}
	}
	if len(scid) == 1 && scid[0] >= 21 && scid[0] <= 31 {
		scid = []byte{scid[0], 0, 0, 0}
	}
	b := []byte{0xc3 | typ<<4, 0, 0, 0, 1, byte(len(dcid))}
	b = append(b, dcid...)
	b = append(b, byte(len(scid)))
	b = append(b, scid...)
	return append(b, 0, 0x40, 1, 42)
}

func TestAccountingSeparatesReusedUDPAddress(t *testing.T) {
	a := accountingPacket(0, []byte{1}, []byte{11})
	b := accountingPacket(0, []byte{2}, []byte{12})
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{a, b, a},
		addr: &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 5555}}}
	s := &decodeConn{mode: "off"}
	s.PacketConn = wire
	buf := make([]byte, 2000)
	for i := 0; i < 3; i++ {
		if _, _, err := s.ReadFrom(buf); err != nil {
			t.Fatal(err)
		}
	}
	if len(s.conns) != 2 {
		t.Fatalf("three packets from two connections at one address produced %d accounts", len(s.conns))
	}
	counts := map[int]int{}
	for _, c := range s.conns {
		counts[c.RxDgrams]++
	}
	if counts[1] != 1 || counts[2] != 1 {
		t.Fatalf("retransmission merged into wrong connection: %v", counts)
	}
}

func TestAccountingTracksCIDTransitionAndMigration(t *testing.T) {
	s := &decodeConn{}
	a := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 5555}
	b := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 5556}
	old := s.acctLocked(a, accountingPacket(0, []byte{1}, []byte{11}), false)
	newer := s.acctLocked(a, accountingPacket(0, []byte{2}, []byte{12}), false)
	if old == nil || newer == nil || old == newer {
		t.Fatal("connections not distinguished")
	}
	for _, check := range []struct {
		addr     net.Addr
		packet   []byte
		outbound bool
		want     *connAcct
	}{
		{a, accountingPacket(0, []byte{11}, []byte{21}), true, old},
		{a, accountingPacket(0, []byte{12}, []byte{22}), true, newer},
		{a, accountingPacket(0, []byte{21}, []byte{11}), false, old},
		{a, accountingPacket(2, []byte{22}, []byte{12}), false, newer},
		// quic-go rotates immediately after handshake completion. The new
		// server CID was encrypted in NEW_CONNECTION_ID, but the next client
		// long header still carries the original client SCID.
		{a, accountingPacket(0, []byte{31}, []byte{11}), false, old},
		{a, []byte{0x40, 31, 0, 0, 0, 0}, false, old},
		{b, []byte{0x40, 21, 0, 0, 0, 0}, false, old},
		{b, []byte{0x40, 11, 0}, true, old},
		{a, accountingPacket(0, []byte{1}, []byte{11}), false, old},
	} {
		if got := s.acctLocked(check.addr, check.packet, check.outbound); got != check.want {
			t.Fatal("CID change, delayed packet, or address migration changed account")
		}
	}
	if len(s.conns) != 2 || old.PeerChanges != 2 {
		t.Fatalf("accounts=%d address changes=%d", len(s.conns), old.PeerChanges)
	}
}

func TestAccountingNeverGuessesUnknownOrAmbiguousCID(t *testing.T) {
	s := &decodeConn{}
	a := &net.UDPAddr{Port: 5555}
	x := s.acctLocked(a, accountingPacket(0, []byte{1}, []byte{11}), false)
	y := s.acctLocked(a, accountingPacket(0, []byte{2}, []byte{12}), false)
	if x == nil || y == nil || x == y {
		t.Fatal("different SCIDs must not merge")
	}
	s.bindCIDLocked(true, []byte{11}, y)
	if s.stats.ConnAcctAliasConflicts != 1 {
		t.Fatal("SCID reuse not reported")
	}
	for _, p := range [][]byte{[]byte{0x40, 11, 0}, accountingPacket(0, []byte{11}, []byte{21})} {
		if s.acctLocked(a, p, true) != nil {
			t.Fatal("ambiguous outbound CID was guessed by address")
		}
	}
	if s.acctLocked(a, []byte{0x40, 99, 0}, false) != nil {
		t.Fatal("unknown CID was guessed")
	}
	if s.acctLocked(a, accountingPacket(0, []byte{9}, nil), false) != nil {
		t.Fatal("zero-length CID incorrectly assigned")
	}
}

func TestAccountingCapacityDoesNotReuseLastAddress(t *testing.T) {
	s := &decodeConn{}
	a := &net.UDPAddr{Port: 5555}
	for i := 0; i < connAcctCap; i++ {
		cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
		if s.acctLocked(a, accountingPacket(0, cid, cid), false) == nil {
			t.Fatalf("dropped connection %d before cap", i)
		}
	}
	newer := s.acctLocked(a, accountingPacket(0, []byte{0xff}, []byte{0xff}), false)
	if newer == nil || newer.InitialDCID != "ff" {
		t.Fatal("capacity overflow failed to create a distinct account")
	}
	if len(s.conns) != connAcctCap || s.stats.ConnAcctDropped != 1 || s.stats.ConnAcctEvictedLRU != 1 {
		t.Fatal("capacity overflow not reported")
	}
	if s.acctLocked(a, accountingPacket(0, []byte{0, 0, 0, 0, 0, 0, 0, 2}, []byte{0, 0, 0, 0, 0, 0, 0, 2}), false) == nil {
		t.Fatal("cap blocked an existing connection's retransmission")
	}
}

func TestRepeatedClientSCIDIsNotSilentlyMerged(t *testing.T) {
	s := &decodeConn{}
	a := &net.UDPAddr{Port: 5555}
	p := accountingPacket(0, []byte{1}, []byte{11})
	old := s.acctLocked(a, p, false)
	newer := s.acctLocked(a, accountingPacket(0, []byte{2}, []byte{11}), false)
	if old == nil || newer == nil || old == newer || len(s.conns) != 2 {
		t.Fatal("reused client SCID merged distinct Initial pairs")
	}
	if s.stats.ConnAcctAliasConflicts != 1 {
		t.Fatal("SCID collision not reported")
	}
	if s.acctLocked(a, p, false) != old {
		t.Fatal("retransmitted original Initial lost identity")
	}
	if s.acctLocked(a, accountingPacket(0, []byte{11}, []byte{21}), true) != nil {
		t.Fatal("ambiguous server reply was guessed")
	}
}

func TestPendingRecoveryKeepsOriginalAccount(t *testing.T) {
	s := &decodeConn{mode: "off"}
	a := &net.UDPAddr{Port: 5555}
	p := accountingPacket(0, []byte{1}, []byte{11})
	old := s.acctLocked(a, p, false)
	newer := s.acctLocked(a, accountingPacket(0, []byte{2}, []byte{12}), false)
	s.pending = []pendingPkt{{data: p, addr: a, acct: old}}
	s.pendingBytes = int64(len(p))
	if _, _, err := s.ReadFrom(make([]byte, 2000)); err != nil {
		t.Fatal(err)
	}
	if old.Stack != int64(len(p)) || newer.Stack != 0 {
		t.Fatal("delayed recovery charged to new connection at same address")
	}
}

func TestUnknownAccountingIsReported(t *testing.T) {
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{{0x40, 99, 0}}, addr: &net.UDPAddr{Port: 5555}}}
	s := &decodeConn{mode: "off"}
	s.PacketConn = wire
	if _, _, err := s.ReadFrom(make([]byte, 2000)); err != nil {
		t.Fatal(err)
	}
	if _, err := s.WriteTo([]byte{0x40, 99, 0}, wire.addr); err != nil {
		t.Fatal(err)
	}
	if len(s.conns) != 0 || s.stats.ConnAcctUnmappedRX != 1 || s.stats.ConnAcctUnmappedTX != 1 || s.stats.ConnAcctUnmappedStack != 3 {
		t.Fatalf("missing explicit unknown accounting: %+v", s.stats)
	}
}

func TestRecoveredOriginalIsCountedOnItsConnection(t *testing.T) {
	gfInit()
	original := accountingPacket(0, []byte{1}, []byte{11})
	parity := buildParity([]byte{1}, []byte{11}, fecBlock{flight: 1, k: 1, m: 1,
		symLen: len(original), crcs: []uint32{crc32.ChecksumIEEE(original)},
		lens: []uint16{uint16(len(original))}, sym: original})
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{parity, parity}, addr: &net.UDPAddr{Port: 5555}}}
	s := &decodeConn{mode: "fec"}
	s.PacketConn = wire
	for i := 0; i < 2; i++ {
		if _, _, err := s.ReadFrom(make([]byte, 2000)); err != nil {
			t.Fatal(err)
		}
	}
	if s.stats.Recovered != 1 || len(s.conns) != 1 {
		t.Fatalf("bad fixture: %+v", s.stats)
	}
	for _, c := range s.conns {
		if c.RecovN != 1 {
			t.Fatalf("global recovery=1 but per-connection recov_n=%d", c.RecovN)
		}
	}
}

func TestRecoveryAccountingCommitIsGuardedAndConnectionSpecific(t *testing.T) {
	for _, scenario := range []string{"no_bytes", "empty", "poisoned", "already_done"} {
		s := &decodeConn{}
		ca := &connAcct{}
		fr := &flightRec{acct: ca}
		outs := [][]byte{{1, 2, 3}}
		if scenario != "no_bytes" {
			s.stats.BytesIn = 100
		}
		if scenario == "empty" {
			outs = [][]byte{nil}
		}
		if scenario == "poisoned" {
			fr.poisoned = true
		}
		if scenario == "already_done" {
			fr.done = true
		}
		if s.settleRecovery(fr, outs) != nil || ca.RecovN != 0 || s.stats.Recovered != 0 {
			t.Fatalf("%s committed an invalid recovery", scenario)
		}
	}
	s := &decodeConn{}
	s.stats.BytesIn = 100
	old, newer := &connAcct{}, &connAcct{}
	fr := &flightRec{acct: old}
	outs := [][]byte{{1, 2, 3}, {4, 5, 6}}
	if s.settleRecovery(fr, outs) == nil || old.RecovN != 2 || newer.RecovN != 0 {
		t.Fatal("successful recovery did not credit its original connection")
	}
	if len(s.pending) != 1 || s.pending[0].acct != old {
		t.Fatal("pending recovery lost its account")
	}
	if s.settleRecovery(fr, outs) != nil || old.RecovN != 2 || s.stats.Recovered != 2 {
		t.Fatal("duplicate commit inflated recovery counts")
	}
	old.FbSent = true
	if s.settleRecovery(&flightRec{acct: old}, [][]byte{{7}}) == nil || old.RecovN != 2 {
		t.Fatal("post-feedback recovery modified frozen first-flight count")
	}
}
