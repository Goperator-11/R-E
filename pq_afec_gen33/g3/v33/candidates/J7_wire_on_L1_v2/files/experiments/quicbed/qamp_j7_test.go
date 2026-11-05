package main

import (
	"bytes"
	"fmt"
	"net"
	"reflect"
	"testing"
	"time"
)

func j7Block(k, m, lead, size, version int) fecBlock {
	fb := fecBlock{flight: 7, k: k, m: m, lead: lead, index: 0, symLen: size, ver: version,
		crcs: make([]uint32, k), lens: make([]uint16, k), sym: bytes.Repeat([]byte{71}, size)}
	for i := range fb.crcs {
		fb.crcs[i] = uint32(i + 100)
		fb.lens[i] = uint16(size - i)
	}
	return fb
}

func TestJ7WireLengthAndPayloadAcrossCIDs(t *testing.T) {
	cases := 0
	for k := 1; k <= 4; k++ {
		for m := 1; m <= 4; m++ {
			for _, version := range []int{fecVer, fecVerLead} {
				for _, size := range []int{1280, 1452 - 46 - 6*k} {
					for dc := 0; dc <= 20; dc++ {
						for sc := 0; sc <= 20; sc++ {
							if dc+sc > 24 {
								continue
							}
							fb := j7Block(k, m, m, size, version)
							dcid, scid := bytes.Repeat([]byte{1}, dc), bytes.Repeat([]byte{2}, sc)
							packet := buildParity(dcid, scid, fb)
							if len(packet) != size+46+6*k || len(packet) > 1452 {
								t.Fatalf("k%d m%d dc%d sc%d size%d: length %d", k, m, dc, sc, size, len(packet))
							}
							h := parseLongHdr(packet)
							if !h.ok || !bytes.Equal(h.dcid, dcid) || !bytes.Equal(h.scid, scid) {
								t.Fatal("connection IDs changed")
							}
							declared := int(packet[h.bodyOff+1]&0x3f)<<8 | int(packet[h.bodyOff+2])
							if declared != len(packet)-h.bodyOff-3 {
								t.Fatal("padding outside declared body")
							}
							pad := 24 - dc - sc
							if !bytes.Equal(packet[len(packet)-pad:], make([]byte, pad)) {
								t.Fatal("nonzero padding")
							}
							got := parseFecBlock(packet)
							if got == nil || got.k != k || got.m != m || got.symLen != size ||
								!bytes.Equal(got.sym, fb.sym) || !reflect.DeepEqual(got.crcs, fb.crcs) || !reflect.DeepEqual(got.lens, fb.lens) {
								t.Fatal("PFEC payload changed")
							}
							cases++
						}
					}
				}
			}
		}
	}
	t.Logf("checked %d wire cases", cases)
}

func TestJ7RejectedParityKeepsOriginals(t *testing.T) {
	gfInit()
	for _, layout := range []string{"v2", "v3"} {
		for _, c := range []struct{ dc, sc, size int }{{20, 20, 1280}, {21, 0, 1280}, {0, 21, 1280}, {8, 4, 1395}} {
			t.Run(fmt.Sprintf("%s_%d_%d_%d", layout, c.dc, c.sc, c.size), func(t *testing.T) {
				addr := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 12345}
				wire := &auditConn{scriptConn: scriptConn{addr: addr}}
				fc := &fecConn{mode: "fec", m: 2, expectK: 2, layout: layout, lead: 1, dropParity: -1, corruptParity: -1, parityDelay: time.Hour}
				fc.PacketConn = wire
				originals := [][]byte{}
				for i := 0; i < 2; i++ {
					packet := leadTestInitial(make([]byte, c.dc), make([]byte, c.sc), c.size, byte(i+3))
					originals = append(originals, packet)
					if n, err := fc.WriteTo(packet, addr); err != nil || n != len(packet) {
						t.Fatalf("original: n=%d err=%v", n, err)
					}
				}
				stats := fc.finalSendStats()
				if !reflect.DeepEqual(wire.written, originals) || stats.ParitySent != 0 || stats.ParityFail != 2 || stats.ParityBuildRejected != 2 || stats.BytesParity != 0 {
					t.Fatalf("rejected parity changed transmission: %+v writes=%d", stats, len(wire.written))
				}
			})
		}
	}
}

func TestJ7FecParseFailureCounter(t *testing.T) {
	base := buildParity(leadTestDCID, leadTestSCID, j7Block(2, 2, 1, 1280, fecVerLead))
	off := parseLongHdr(base).bodyOff
	badVersion := append([]byte(nil), base...)
	badVersion[off+7] = 99
	badLength := append([]byte(nil), base...)
	badLength[off+1] = 0
	falseMagic := leadTestInitial(leadTestDCID, leadTestSCID, 1280, 19)
	copy(falseMagic[off+20:], fecMagic)
	for _, c := range []struct {
		name   string
		packet []byte
		want   int
	}{
		{"valid", base, 0}, {"truncated", base[:len(base)-1], 1}, {"version", badVersion, 1},
		{"length", badLength, 1}, {"unrelated", falseMagic, 0}, {"short", []byte("PFEC"), 0},
	} {
		for _, mode := range []string{"off", "fec"} {
			t.Run(c.name+"_"+mode, func(t *testing.T) {
				wire := &scriptConn{dgs: [][]byte{c.packet}, addr: &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 12345}}
				sv := &decodeConn{mode: mode}
				sv.PacketConn = wire
				buf := make([]byte, 1452)
				sv.ReadFrom(buf)
				want := c.want
				if mode == "off" {
					want = 0
				}
				if sv.stats.FecParseFail != want {
					t.Fatalf("parse failures %d want %d", sv.stats.FecParseFail, want)
				}
			})
		}
	}
}

func TestJ7CandidateReceiveLimit(t *testing.T) {
	checked := 0
	for k := 1; k <= 4; k++ {
		for _, w := range []int{1200, 1280, 1350, 1382, 1388, 1394, 1400, 1452} {
			for _, cert := range []int{1000, 4032, 9000, 11000, 12000, 16000, 30000} {
				s := float64(cert) + 1472 + float64(binIndex(k*w))*cPktDefault
				for _, c := range p3Candidates(k, w, s, cPktDefault) {
					if c.M > 0 && c.WEff+46+6*k > 1452 {
						t.Fatalf("oversize candidate %+v", c)
					}
					checked++
				}
				for _, c := range evalCands(levers(k, w, maxStepsDefault, mMaxDefault, s, cPktDefault, quicgoMaxIPS), k, w, s, 50, .05, 1, cPktDefault, quicgoMaxIPS, 2) {
					if c.c.m > 0 && c.c.wEff+46+6*k > 1452 {
						t.Fatalf("oversize gen2 candidate %+v", c)
					}
					checked++
				}
			}
		}
	}
	t.Logf("checked %d candidates", checked)
}
