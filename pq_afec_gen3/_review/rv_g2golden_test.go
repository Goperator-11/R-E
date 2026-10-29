package main

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"net"
	"testing"
	"time"
)

func leadTestInitial(dcid, scid []byte, size int, seed byte) []byte {
	d := make([]byte, size)
	x := uint32(seed)*2654435761 + 12345
	for i := range d {
		x = x*1103515245 + 12345
		d[i] = byte(x >> 16)
	}
	d[0] = 0xc3
	d[1], d[2], d[3], d[4] = 0, 0, 0, 1
	d[5] = byte(len(dcid))
	copy(d[6:], dcid)
	d[6+len(dcid)] = byte(len(scid))
	copy(d[7+len(dcid):], scid)
	return d
}

var leadTestDCID = []byte{0xd1, 0xd2, 0xd3, 0xd4, 0xd5, 0xd6, 0xd7, 0xd8}
var leadTestSCID = []byte{0x51, 0x52, 0x53, 0x54}

func leadTranscript(fc *fecConn, k int) []byte {
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	srv := leadTestInitial(leadTestSCID, leadTestDCID, 1300, 200)
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{srv}, addr: addr}}
	fc.PacketConn = wire
	var out []byte
	put := func(n int, err error) {
		out = binary.BigEndian.AppendUint16(out, uint16(n))
		if err != nil {
			out = append(out, err.Error()...)
		}
	}
	for round := 0; round < 2; round++ {
		for i := 0; i < k; i++ {
			size := 1200
			if i == k-1 {
				size = 1100 - 37*round
			}
			put(fc.WriteTo(leadTestInitial(leadTestDCID, leadTestSCID, size, byte(16*round+i)), addr))
		}
	}
	buf := make([]byte, 2000)
	n, _, err := fc.ReadFrom(buf)
	put(n, err)
	put(fc.WriteTo(leadTestInitial(leadTestDCID, leadTestSCID, 1200, 99), addr))
	put(fc.WriteTo([]byte{0x40, 1, 2, 3, 4, 5, 6, 7}, addr))
	for _, w := range wire.written {
		out = binary.BigEndian.AppendUint16(out, uint16(len(w)))
		out = append(out, w...)
	}
	return out
}

func leadV2Conn(mode string, m, k int, inject bool) *fecConn {
	fc := &fecConn{mode: mode, m: m, expectK: k, dropParity: -1, corruptParity: -1,
		parityDelay: time.Hour}
	if inject {
		fc.dropInitial = map[int]bool{1: true}
		fc.dropParity = 0
		fc.corruptParity = 1
	}
	return fc
}

func leadV2Digest(mode string, mk func(mode string, m, k int, inject bool) *fecConn) string {
	h := sha256.New()
	for m := 1; m <= 4; m++ {
		for k := 1; k <= 3; k++ {
			for _, inject := range []bool{false, true} {
				fmt.Fprintf(h, "%s|%d|%d|%v|", mode, m, k, inject)
				h.Write(leadTranscript(mk(mode, m, k, inject), k))
			}
		}
	}
	return fmt.Sprintf("%x", h.Sum(nil))
}

var leadV2Golden = map[string]string{
	"off": "ae4b292f44316c12deed63a33d0b52959c8cc0b07aed81dbdaba6ec0938bac3c",
	"buf": "c148d149c90b87c4e386ffa0505c477c35b9622d0316e6eb80d4f6f69360cff5",
	"fec": "514ad428971dd3607b5cbe05da25d0e8e1510f3ad4ef2c10a7fb4bb024475487",
}

func TestRvBuilderGoldenOnG2(t *testing.T) {
	gfInit()
	for mode, want := range leadV2Golden {
		got := leadV2Digest(mode, leadV2Conn)
		t.Logf("RVDIGEST builder-golden %s match=%v %s", mode, got == want, got)
	}
}
