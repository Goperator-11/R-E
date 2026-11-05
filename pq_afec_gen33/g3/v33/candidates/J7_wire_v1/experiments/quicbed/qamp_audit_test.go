package main

import (
	"hash/crc32"
	"math"
	"net"
	"testing"
)

type auditConn struct {
	scriptConn
	written [][]byte
}

func (c *auditConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.written = append(c.written, append([]byte(nil), b...))
	return len(b), nil
}

func auditInitial(marker byte) []byte {
	pkt := []byte{0xc3, 0, 0, 0, 1, 1, 9, 1, 8, 0, 0x40, 1, marker}
	return pkt
}

func TestRejectInvalidParityIndex(t *testing.T) {
	for _, index := range []int{2, 3, 255} {
		packet := buildParity([]byte{1}, []byte{2}, fecBlock{
			flight: 1, k: 1, m: 2, index: index, symLen: 1,
			crcs: []uint32{0}, lens: []uint16{1}, sym: []byte{42},
		})
		if parseFecBlock(packet) != nil {
			t.Errorf("accepted parity index %d outside [0,2)", index)
		}
	}
}

func TestRejectImpossibleSymbolLength(t *testing.T) {
	packet := buildParity([]byte{1}, []byte{2}, fecBlock{
		flight: 1, k: 1, m: 1, index: 0, symLen: 1,
		crcs: []uint32{0}, lens: []uint16{2}, sym: []byte{42},
	})
	if parseFecBlock(packet) != nil {
		t.Fatal("accepted source length larger than parity symbol")
	}
}

func TestFeedbackExcludesRetransmissionsAndDuplicates(t *testing.T) {
	gfInit()
	original := auditInitial(10)
	missing := auditInitial(11)
	retransmission := auditInitial(12)
	retxParity := buildParity([]byte{9}, []byte{8}, fecBlock{
		flight: 2, k: 1, m: 1, index: 0, symLen: len(retransmission),
		crcs: []uint32{crc32.ChecksumIEEE(retransmission)},
		lens: []uint16{uint16(len(retransmission))}, sym: retransmission,
	})
	handshake := auditInitial(13)
	handshake[0] = 0xe3
	wire := &auditConn{scriptConn: scriptConn{
		dgs:  [][]byte{original, original, retransmission, retxParity, handshake},
		addr: &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 5555},
	}}
	sv := &decodeConn{mode: "fec", feedback: true}
	sv.PacketConn = wire
	buf := make([]byte, 2000)
	for {
		if _, _, err := sv.ReadFrom(buf); err != nil {
			break
		}
	}
	if len(wire.written) != 1 {
		t.Fatalf("wanted one feedback datagram, got %d", len(wire.written))
	}
	r := parseFeedback(wire.written[0])
	if r == nil || r.truncated || len(r.crcs) != 3 {
		t.Fatalf("receiver did not report unique physical CRCs: %+v", r)
	}
	o, p, retx := matchFirstFlight(r,
		[]uint32{crc32.ChecksumIEEE(original), crc32.ChecksumIEEE(missing)},
		[]uint32{12345678})
	if o != 1 || p != 0 || retx != 2 {
		t.Fatalf("first flight counts = (%d,%d), retransmissions = %d", o, p, retx)
	}
	if int(r.rxOrig)+int(r.rxPar) <= o+p {
		t.Fatal("test must contain raw-count contamination")
	}
}

func TestClientRecordsFirstFlightForFeedback(t *testing.T) {
	gfInit()
	for _, mode := range []string{"off", "buf", "fec"} {
		wire := &auditConn{}
		fc := &fecConn{mode: mode, m: 1, expectK: 1, dropParity: -1, corruptParity: -1}
		fc.PacketConn = wire
		original := auditInitial(20)
		addr := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 4433}
		if _, err := fc.WriteTo(original, addr); err != nil {
			t.Fatal(err)
		}
		if len(fc.ffOrigCRC) != 1 || fc.ffOrigCRC[0] != crc32.ChecksumIEEE(original) {
			t.Fatalf("%s did not retain original CRC", mode)
		}
		wantParity := 0
		if mode == "fec" {
			wantParity = 1
		}
		if len(fc.ffParCRC) != wantParity {
			t.Fatalf("%s retained %d parity CRCs", mode, len(fc.ffParCRC))
		}
	}
}

func TestFeedbackCapAndTruncation(t *testing.T) {
	crcs := make([]uint32, fbCRCCap+1)
	for i := range crcs {
		crcs[i] = uint32(i)
	}
	r := parseFeedback(buildFeedback([]byte{1}, []byte{2}, fbRec{crcs: crcs}))
	if r == nil || !r.truncated || len(r.crcs) != fbCRCCap {
		t.Fatalf("overflow is not marked as incomplete: %+v", r)
	}
	packet := buildFeedback([]byte{1}, []byte{2}, fbRec{crcs: crcs[:2]})
	for cut := 0; cut < len(packet); cut++ {
		if parseFeedback(packet[:cut]) != nil {
			t.Fatalf("accepted truncated feedback at byte %d", cut)
		}
	}
}

func TestComboCandidatesMatchCreditBoundaries(t *testing.T) {
	for k := 1; k <= 4; k++ {
		for m := 1; m <= 3; m++ {
			for _, w := range []int{1200, 1280} {
				for _, need := range []int{4, 7, 10, 13, 16} {
					candidates := comboDeltas(k, m, w, 46+6*k, need, 172)
					last, _, _, _ := flightOutcome(k, m, w, 0.17, 3, need, 0)
					for delta := 1; delta <= 172; delta++ {
						value, _, _, _ := flightOutcome(k, m, w+delta, 0.17, 3, need, 0)
						changed := math.Abs(value-last) > 1e-12
						if changed != inIntSlice(candidates, delta) {
							t.Fatalf("k=%d m=%d w=%d need=%d delta=%d: changed=%v candidates=%v",
								k, m, w, need, delta, changed, candidates)
						}
						last = value
					}
				}
			}
		}
	}
}
