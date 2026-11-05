package main

import (
	"bytes"
	"net"
	"testing"
)

func TestDecoderV3MetadataConflictsPreserveFlight(t *testing.T) {
	gfInit()
	for _, field := range []string{"version", "lead"} {
		for _, path := range []string{"ReadFrom", "feedOne"} {
			t.Run(field+"/"+path, func(t *testing.T) {
				src, packets := decoderFixture(3)
				for i, packet := range packets {
					fb := *parseFecBlock(packet)
					fb.ver, fb.lead = fecVerLead, 0
					packets[i] = buildParity([]byte{9}, []byte{8}, fb)
				}
				conflict := *parseFecBlock(packets[2])
				if field == "version" {
					conflict.ver = fecVer
				} else {
					conflict.lead = 1
				}
				bad := buildParity([]byte{9}, []byte{8}, conflict)
				if parseFecBlock(bad) == nil {
					t.Fatal("metadata conflict must be well formed")
				}
				s := &decodeConn{mode: "fec"}
				if path == "feedOne" {
					s.feedOne(packets[1])
					s.feedOne(bad)
					s.feedOne(packets[2])
					if len(s.pending) != 1 || !bytes.Equal(s.pending[0].data, src[1]) {
						t.Fatal("feedOne lost second recovery")
					}
				} else {
					s.PacketConn = &scriptConn{dgs: [][]byte{packets[1], bad, packets[2]}, addr: &net.UDPAddr{Port: 5555}}
					for _, expected := range [][]byte{bad, src[0], src[1]} {
						buf := make([]byte, 2000)
						n, _, err := s.ReadFrom(buf)
						if err != nil || !bytes.Equal(buf[:n], expected) {
							t.Fatalf("metadata conflict changed output: n=%d err=%v", n, err)
						}
					}
				}
				if s.stats.Recovered != 2 || s.stats.RecoverFail != 0 || s.heldBytes != 0 || s.stats.BytesToStack+s.pendingBytes > s.stats.BytesIn {
					t.Fatalf("conflicting metadata broke recovery/accounting: %+v", s.stats)
				}
				for _, flight := range s.flights {
					if flight.fb.ver != fecVerLead || flight.fb.lead != 0 {
						t.Fatal("conflicting metadata replaced accepted flight")
					}
				}
			})
		}
	}
}
