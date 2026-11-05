package main

import (
	"bytes"
	"hash/crc32"
	"net"
	"testing"
	"time"
)

func decoderFixture(m int) ([][]byte, [][]byte) {
	src := [][]byte{auditInitial(21), auditInitial(22)}
	crcs := []uint32{crc32.ChecksumIEEE(src[0]), crc32.ChecksumIEEE(src[1])}
	lens := []uint16{uint16(len(src[0])), uint16(len(src[1]))}
	syms := rsEncode(src, m, len(src[0]))
	parities := make([][]byte, m)
	for i := range syms {
		parities[i] = buildParity([]byte{9}, []byte{8}, fecBlock{
			flight: 1, k: len(src), m: m, index: i,
			symLen: len(src[0]), crcs: crcs, lens: lens, sym: syms[i],
		})
	}
	return src, parities
}

func TestDecoderExpiryReleasesHeldBytes(t *testing.T) {
	now := time.Now()
	expired := &flightRec{created: now.Add(-2 * flightTTL), heldBytes: 17}
	active := &flightRec{created: now, heldBytes: 23}
	s := &decodeConn{flights: map[string]*flightRec{"expired": expired, "active": active}, heldBytes: 40}
	s.expireLocked(now)
	if len(s.flights) != 1 || s.flights["active"] != active || s.heldBytes != 23 || expired.heldBytes != 0 {
		t.Fatalf("expired flight retained held bytes: flights=%d held=%d expired=%d", len(s.flights), s.heldBytes, expired.heldBytes)
	}
	s.expireLocked(now)
	if s.heldBytes != 23 {
		t.Fatal("repeated expiry released active held bytes")
	}
}

func TestDecoderParityTrafficExpiresFlights(t *testing.T) {
	gfInit()
	_, parity := decoderFixture(3)
	for _, path := range []string{"ReadFrom", "feedOne"} {
		t.Run(path, func(t *testing.T) {
			s := &decodeConn{mode: "fec", heldBytes: 17, flights: map[string]*flightRec{
				"expired": {created: time.Now().Add(-2 * flightTTL), heldBytes: 17},
			}}
			if path == "feedOne" {
				s.feedOne(parity[0])
			} else {
				s.PacketConn = &scriptConn{dgs: [][]byte{parity[0]}, addr: &net.UDPAddr{Port: 5555}}
				if _, _, err := s.ReadFrom(make([]byte, 2000)); err != nil {
					t.Fatal(err)
				}
			}
			if len(s.flights) != 0 || s.heldBytes != 0 {
				t.Fatalf("parity arrival did not expire old state: flights=%d held=%d", len(s.flights), s.heldBytes)
			}
		})
	}
}

func TestDecoderPendingTruncationMatchesReturnedBytes(t *testing.T) {
	ca := &connAcct{}
	s := &decodeConn{pending: []pendingPkt{{data: []byte{1, 2, 3, 4}, acct: ca}}, pendingBytes: 4}
	n, _, err := s.ReadFrom(make([]byte, 2))
	if err != nil {
		t.Fatal(err)
	}
	if n != 2 || s.stats.BytesToStack != int64(n) || ca.Stack != int64(n) || s.pendingBytes != 0 {
		t.Fatalf("truncated delivery disagrees with accounting: n=%d stack=%d connection=%d pending=%d", n, s.stats.BytesToStack, ca.Stack, s.pendingBytes)
	}
}

func TestDecoderRejectsConflictingFlightMetadata(t *testing.T) {
	gfInit()
	src, parity := decoderFixture(3)
	for _, field := range []string{"k", "m", "symbol_length", "crc", "source_length"} {
		t.Run(field, func(t *testing.T) {
			conflict := *parseFecBlock(parity[2])
			switch field {
			case "k":
				conflict.k++
				conflict.crcs = append(conflict.crcs, 1234)
				conflict.lens = append(conflict.lens, uint16(len(src[0])))
			case "m":
				conflict.m++
			case "symbol_length":
				conflict.symLen++
				conflict.sym = append(conflict.sym, 0)
			case "crc":
				conflict.crcs[0] ^= 1
			case "source_length":
				conflict.lens[0]--
			}
			bad := buildParity([]byte{9}, []byte{8}, conflict)
			if parseFecBlock(bad) == nil {
				t.Fatal("conflicting fixture must be individually well formed")
			}
			wire := &scriptConn{dgs: [][]byte{parity[1], bad, parity[2]}, addr: &net.UDPAddr{Port: 5555}}
			s := &decodeConn{mode: "fec"}
			s.PacketConn = wire
			var received [][]byte
			for {
				buf := make([]byte, 2000)
				n, _, err := s.ReadFrom(buf)
				if err != nil {
					break
				}
				received = append(received, append([]byte(nil), buf[:n]...))
			}
			if s.stats.Recovered != 2 || s.stats.RecoverFail != 0 || len(received) != 3 || !bytes.Equal(received[0], bad) || !bytes.Equal(received[1], src[0]) || !bytes.Equal(received[2], src[1]) {
				t.Fatalf("conflicting metadata damaged a valid flight: recovered=%d failures=%d delivered=%d", s.stats.Recovered, s.stats.RecoverFail, len(received))
			}
			var handed int64
			for _, packet := range received {
				handed += int64(len(packet))
			}
			if handed != s.stats.BytesToStack || handed > s.stats.BytesIn {
				t.Fatalf("recovery accounting mismatch: handed=%d stack=%d physical=%d", handed, s.stats.BytesToStack, s.stats.BytesIn)
			}
		})
	}
}
