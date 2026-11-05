package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
)

type boundaryInput struct {
	data []byte
	addr net.Addr
}

type boundaryConn struct {
	auditConn
	input   []boundaryInput
	inspect func([]byte, net.Addr)
}

func (c *boundaryConn) ReadFrom(b []byte) (int, net.Addr, error) {
	if len(c.input) == 0 {
		return 0, nil, net.ErrClosed
	}
	x := c.input[0]
	c.input = c.input[1:]
	return copy(b, x.data), x.addr, nil
}

func (c *boundaryConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	if c.inspect != nil {
		c.inspect(b, addr)
	}
	return c.auditConn.WriteTo(b, addr)
}

func TestClientBoundaryRejectsForeignPeerAndCID(t *testing.T) {
	peer := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4433}
	wrong := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4434}
	own := []byte{1, 2, 3, 4}
	fb := buildFeedback(own, []byte{9}, fbRec{crcs: []uint32{7}})
	wrongCID := buildFeedback([]byte{5, 6, 7, 8}, []byte{9}, fbRec{})
	big := leadTestInitial(own, []byte{9}, 1300, 44)
	badBig := leadTestInitial([]byte{5, 6, 7, 8}, []byte{9}, 1300, 44)
	short := append([]byte{0x40}, own...)
	short = append(short, 99)
	wire := &boundaryConn{input: []boundaryInput{{fb, wrong}, {big, wrong}, {wrongCID, peer}, {badBig, peer}, {[]byte{0x40, 5, 6, 7, 8, 99}, peer}, {fb, peer}, {short, peer}}}
	fc := &fecConn{identityPeer: peer, ownCID: own, observer: newMemoryTrace(time.Now())}
	fc.PacketConn = wire
	buf := make([]byte, 2000)
	n, _, err := fc.ReadFrom(buf)
	if err != nil || !bytes.Equal(buf[:n], short) {
		t.Fatalf("accepted packet %x error %v", buf[:n], err)
	}
	if fc.stats.RxRejectedPeer != 2 || fc.stats.RxRejectedCID != 3 || fc.stats.FbRecv != 1 || fc.srvBig {
		t.Fatalf("foreign input changed state: %+v", fc.stats)
	}
	obs := fc.observer.snapshot()
	if len(obs.Datagrams) != 2 || obs.ServerBytes != int64(len(short)) || fc.RxBytes != int64(len(short)) {
		t.Fatalf("foreign input changed bytes: %+v", obs)
	}
	wire.input = []boundaryInput{{big, peer}}
	if n, _, err := fc.ReadFrom(buf); err != nil || n != len(big) || !fc.srvBig {
		t.Fatal("valid large datagram did not update observation")
	}
}

func TestClientBoundaryIdentityPrecedesSocketWrite(t *testing.T) {
	peer := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4433}
	own := []byte{1, 2, 3, 4}
	fc := &fecConn{mode: "off", expectK: 1, dropParity: -1, corruptParity: -1, parityDelay: time.Hour}
	wire := &boundaryConn{}
	wire.inspect = func(_ []byte, addr net.Addr) {
		fc.mu.Lock()
		defer fc.mu.Unlock()
		if !fc.acceptServerLocked(buildFeedback(own, []byte{9}, fbRec{}), addr) {
			t.Fatal("response can race the first write before identity is registered")
		}
	}
	fc.PacketConn = wire
	if _, err := fc.WriteTo(leadTestInitial(leadTestDCID, own, 1200, 4), peer); err != nil {
		t.Fatal(err)
	}
	fc.finalSendStats()
}

func TestClientFirstFlightRejectsNonInitialLongHeader(t *testing.T) {
	for _, typ := range []byte{1, 2, 3} {
		wire := &auditConn{}
		fc := &fecConn{mode: "off"}
		fc.PacketConn = wire
		if n, err := fc.WriteTo(accountingPacket(typ, []byte{1}, []byte{11}), &net.UDPAddr{Port: 44}); err == nil || n != 0 || len(wire.written) != 0 || fc.stats.FirstFlightNonInitialLong != 1 {
			t.Fatalf("type %d passed the first-flight boundary", typ)
		}
		fc.serverSeen = true
		if _, err := fc.WriteTo(accountingPacket(typ, []byte{1}, []byte{11}), &net.UDPAddr{Port: 44}); err != nil {
			t.Fatal(err)
		}
	}
	fc := &fecConn{mode: "off"}
	wire := &auditConn{}
	fc.PacketConn = wire
	coalesced := append(accountingPacket(0, []byte{1}, []byte{11}), accountingPacket(2, []byte{1}, []byte{11})...)
	if _, err := fc.WriteTo(coalesced, &net.UDPAddr{Port: 44}); err == nil || len(wire.written) != 0 {
		t.Fatal("coalesced Handshake passed the first-flight boundary")
	}
}

func TestLongHeaderLengthOverflowDoesNotPanic(t *testing.T) {
	header := accountingPacket(0, []byte{1}, []byte{11})[:9]
	for _, suffix := range [][]byte{
		{0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff},
		{0, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff},
		{0x40, 127},
		{0, 0x40, 127},
	} {
		if hasHandshake(append(append([]byte(nil), header...), suffix...)) {
			t.Fatal("truncated length accepted as Handshake")
		}
	}
}

func TestClientCIDRotationIsTrackedAndBounded(t *testing.T) {
	peer := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4433}
	fc := &fecConn{identityPeer: peer}
	g := clientCIDGenerator{client: fc}
	for i := 0; i < clientCIDCap; i++ {
		id, err := g.GenerateConnectionID()
		if err != nil || id.Len() != 4 {
			t.Fatalf("generated ID %d: %s %v", i, id, err)
		}
		if i == 0 {
			fc.ownCID = append([]byte(nil), id.Bytes()...)
		}
		short := append([]byte{0x40}, id.Bytes()...)
		short = append(short, 99)
		if !fc.acceptServerLocked(short, peer) || !fc.acceptServerLocked(buildFeedback(id.Bytes(), []byte{9}, fbRec{}), peer) {
			t.Fatal("locally generated rotated CID rejected")
		}
	}
	if _, err := g.GenerateConnectionID(); err == nil || len(fc.ownCIDs) != clientCIDCap {
		t.Fatal("CID storage limit not enforced")
	}
	foreign := []byte{0x40, 1, 2, 3, 4, 99}
	for fc.ownCIDs[string(foreign[1:5])] {
		foreign[1]++
	}
	if fc.acceptServerLocked(foreign, peer) {
		t.Fatal("foreign CID accepted after rotation")
	}
}

func TestAccountRetentionFiveThousandConnections(t *testing.T) {
	s := &decodeConn{feedback: true}
	peer := &net.UDPAddr{Port: 5555}
	start := time.Now()
	for i := 0; i < 5000; i++ {
		cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
		ca := s.acctLocked(peer, accountingPacket(0, cid, cid), false)
		if ca == nil {
			t.Fatalf("account %d missing", i)
		}
		if len(s.feedbackLocked(accountingPacket(2, cid, cid), ca)) == 0 {
			t.Fatalf("feedback %d missing", i)
		}
		s.accountEndedLocked(ca, start, true)
		if len(s.conns) > connAcctCap || len(s.clientCIDs) > connAcctCap*connAliasCap || len(s.serverCIDs) > connAcctCap*connAliasCap {
			t.Fatal("account or alias cap exceeded")
		}
	}
	if s.stats.FbSentN != 5000 || s.stats.ConnAcctDropped != 0 || s.stats.ConnAcctEvictedLRU != 5000-connAcctCap {
		t.Fatalf("long-run accounts %+v", s.stats)
	}
	s.expireAccountsLocked(start.Add(accountRetention - time.Nanosecond))
	if len(s.conns) != connAcctCap {
		t.Fatal("account expired before retention")
	}
	s.expireAccountsLocked(start.Add(accountRetention))
	if len(s.conns) != 0 || len(s.clientCIDs) != 0 || len(s.serverCIDs) != 0 || len(s.accounts.refs) != 0 || s.accounts.lru.Len() != 0 || s.accounts.expiry.Len() != 0 || s.stats.ConnAcctExpired != connAcctCap {
		t.Fatal("account expiry leaked indexes")
	}
}

func TestAccountLRUTouchAndAmbiguousAliasRetention(t *testing.T) {
	s := &decodeConn{}
	peer := &net.UDPAddr{Port: 5555}
	a := s.acctLocked(peer, accountingPacket(0, []byte{1}, []byte{11}), false)
	b := s.acctLocked(peer, accountingPacket(0, []byte{2}, []byte{11}), false)
	if got, exists := s.clientCIDs[string([]byte{11})]; !exists || got != nil {
		t.Fatal("collision not retained")
	}
	s.evictAccountLocked(a, true)
	if got, exists := s.clientCIDs[string([]byte{11})]; !exists || got != nil {
		t.Fatal("collision was reassigned to a surviving account")
	}
	s.evictAccountLocked(b, true)
	if len(s.clientCIDs) != 0 || len(s.serverCIDs) != 0 || len(s.accounts.refs) != 0 {
		t.Fatal("last alias owner did not release tombstone")
	}
	for i := 0; i < connAcctCap; i++ {
		cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
		s.acctLocked(peer, accountingPacket(0, cid, cid), false)
	}
	first := binary.BigEndian.AppendUint64(nil, 1)
	keep := s.acctLocked(peer, accountingPacket(0, first, first), false)
	s.acctLocked(peer, accountingPacket(0, []byte{99}, []byte{99}), false)
	if keep.life.evicted || s.serverCIDs[string(binary.BigEndian.AppendUint64(nil, 2))] != nil {
		t.Fatal("LRU access did not protect the touched account")
	}
}

func TestAccountCompletionUsesAcceptedContext(t *testing.T) {
	s := &decodeConn{}
	peer := &net.UDPAddr{Port: 5555}
	cid := []byte{1, 2, 3, 4, 5, 6, 7, 8}
	ca := s.acctLocked(peer, accountingPacket(0, cid, []byte{11}), false)
	s.feedback = true
	s.feedbackLocked(accountingPacket(2, cid, []byte{11}), ca)
	if ca.HandshakeCompleteNS != 0 || ca.life.expiry != nil {
		t.Fatal("unauthenticated header marked completion")
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	ctx, _ = s.accountContext(ctx, nil)
	s.accountTracer(ctx, false, quic.ConnectionIDFromBytes(cid))
	s.accountAccepted(ctx)
	if ca.HandshakeCompleteNS == 0 || ca.life.expiry == nil {
		t.Fatal("accepted context did not mark completion")
	}
	deadline := ca.life.deadline
	s.accountEndedLocked(ca, time.Now().Add(time.Second), false)
	if ca.life.deadline != deadline {
		t.Fatal("close extended retention")
	}
}

func TestAccountConcurrentReportsAndExpiry(t *testing.T) {
	s := &decodeConn{}
	var wg sync.WaitGroup
	for worker := 0; worker < 4; worker++ {
		wg.Go(func() {
			for i := 0; i < 200; i++ {
				s.mu.Lock()
				cid := binary.BigEndian.AppendUint64(nil, uint64(worker*200+i+1))
				ca := s.acctLocked(&net.UDPAddr{Port: 5555}, accountingPacket(0, cid, cid), false)
				s.accountEndedLocked(ca, time.Now(), true)
				s.mu.Unlock()
				if _, err := json.Marshal(s.report(i%2 == 0)); err != nil {
					t.Error(err)
				}
			}
		})
	}
	wg.Wait()
	if len(s.conns) != 800 {
		t.Fatalf("lost concurrent accounts: %d", len(s.conns))
	}
}
