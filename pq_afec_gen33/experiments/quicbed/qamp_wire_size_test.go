package main

import (
	"encoding/json"
	"fmt"
	"net"
	"testing"
)

func wireSizeParity(dcidLen, k, symLen, ver int) []byte {
	fb := fecBlock{ver: ver, flight: 1, k: k, m: 2, lead: 1, index: 0,
		symLen: symLen, crcs: make([]uint32, k), lens: make([]uint16, k), sym: make([]byte, symLen)}
	for i := range fb.lens {
		fb.lens[i] = uint16(symLen)
	}
	return buildParity(make([]byte, dcidLen), make([]byte, 4), fb)
}

func TestParityWireSize(t *testing.T) {
	for _, ver := range []int{fecVer, fecVerLead} {
		for dcidLen := 0; dcidLen <= 20; dcidLen++ {
			for k := 1; k <= 4; k++ {
				for _, symLen := range []int{1280, 1452 - 46 - 6*k, 1452 - 39 - 6*k} {
					t.Run(fmt.Sprintf("v%d/dcid%d/k%d/sym%d", ver, dcidLen, k, symLen), func(t *testing.T) {
						packet := wireSizeParity(dcidLen, k, symLen, ver)
						want := symLen + 22 + dcidLen + 4 + 6*k
						if len(packet) != want {
							t.Fatalf("wire size %d, want %d", len(packet), want)
						}
						if fb := parseFecBlock(packet); fb == nil || fb.symLen != symLen || fb.k != k {
							t.Fatalf("round trip failed: %+v", fb)
						}
					})
				}
			}
		}
	}
}

func TestFecParseFail(t *testing.T) {
	valid := wireSizeParity(20, 2, 1394, fecVerLead)
	oversized := wireSizeParity(20, 2, 1395, fecVerLead)
	if len(valid) != 1452 || len(oversized) != 1453 {
		t.Fatal("invalid boundary fixtures")
	}
	badVersion := append([]byte(nil), valid...)
	badVersion[parseLongHdr(badVersion).bodyOff+3+fecMagicLen] = 0xff
	magicCut := valid[:parseLongHdr(valid).bodyOff+3+fecMagicLen-1]
	for _, path := range []string{"feedOne", "ReadFrom"} {
		for _, mode := range []string{"fec", "off"} {
			for _, tc := range []struct {
				name   string
				packet []byte
				fail   bool
			}{
				{"normal", valid, false},
				{"truncated", oversized, true},
				{"malformed_version", badVersion, true},
				{"magic_cut", magicCut, false},
				{"initial", auditInitial(21), false},
			} {
				t.Run(path+"/"+mode+"/"+tc.name, func(t *testing.T) {
					s := &decodeConn{mode: mode}
					for repeat := 1; repeat <= 2; repeat++ {
						if path == "feedOne" {
							packet := tc.packet
							if len(packet) > 1452 {
								packet = packet[:1452]
							}
							s.feedOne(packet)
						} else {
							s.PacketConn = &scriptConn{dgs: [][]byte{tc.packet}, addr: &net.UDPAddr{Port: 5555}}
							if _, _, err := s.ReadFrom(make([]byte, 1452)); err != nil {
								t.Fatal(err)
							}
						}
						want := 0
						if tc.fail && mode != "off" {
							want = repeat
						}
						if s.stats.FecParseFail != want {
							t.Fatalf("fec_parse_fail %d, want %d", s.stats.FecParseFail, want)
						}
						data, err := json.Marshal(s.stats)
						if err != nil {
							t.Fatal(err)
						}
						var stats map[string]any
						if err := json.Unmarshal(data, &stats); err != nil || stats["fec_parse_fail"] != float64(want) {
							t.Fatalf("counter missing from JSON: %s, %v", data, err)
						}
					}
				})
			}
		}
	}
}
