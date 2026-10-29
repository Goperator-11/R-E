package main

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"hash/crc32"
	"net"
	"sort"
	"testing"
	"time"
)

func rvInitial(dcid, scid []byte, size int, seed byte) []byte {
	d := make([]byte, size)
	x := uint32(seed)*2246822519 + 777
	for i := range d {
		x = x*1664525 + 1013904223
		d[i] = byte(x >> 24)
	}
	d[0] = 0xc3
	d[1], d[2], d[3], d[4] = 0, 0, 0, 1
	d[5] = byte(len(dcid))
	copy(d[6:], dcid)
	d[6+len(dcid)] = byte(len(scid))
	copy(d[7+len(dcid):], scid)
	return d
}

var rvDCID = []byte{0xa1, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7, 0xa8, 0xa9}
var rvSCID = []byte{0xb1, 0xb2, 0xb3, 0xb4, 0xb5}

func rvClientTranscript(fc *fecConn, k int, flushByShort bool) []byte {
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	srvSmall := rvInitial(rvSCID, rvDCID, 300, 211)
	srvBig := rvInitial(rvSCID, rvDCID, 1252, 212)
	wire := &auditConn{scriptConn: scriptConn{dgs: [][]byte{srvSmall, srvBig}, addr: addr}}
	fc.PacketConn = wire
	var out []byte
	put := func(n int, err error) {
		out = binary.BigEndian.AppendUint16(out, uint16(n))
		if err != nil {
			out = append(out, err.Error()...)
		}
	}
	short := []byte{0x41, 7, 7, 7, 7, 7, 7}
	buf := make([]byte, 2000)
	for round := 0; round < 4; round++ {
		if round == 1 || round == 2 {
			n, _, err := fc.ReadFrom(buf)
			put(n, err)
		}
		kk := k
		if round >= 2 {
			kk = 1 + round%2
		}
		for i := 0; i < kk; i++ {
			size := 1200
			if i == kk-1 {
				size = 1180 - 13*round
			}
			put(fc.WriteTo(rvInitial(rvDCID, rvSCID, size, byte(32*round+i)), addr))
		}
		if flushByShort {
			put(fc.WriteTo(short, addr))
		}
	}
	put(fc.WriteTo(short, addr))
	for _, w := range wire.written {
		out = binary.BigEndian.AppendUint16(out, uint16(len(w)))
		out = append(out, w...)
	}
	return out
}

func rvClientDigest(mode string) string {
	h := sha256.New()
	for m := 1; m <= 4; m++ {
		for k := 1; k <= 4; k++ {
			for _, inject := range []bool{false, true} {
				for _, byShort := range []bool{false, true} {
					fc := &fecConn{mode: mode, m: m, dropParity: -1, corruptParity: -1,
						parityDelay: time.Hour}
					if !byShort {
						fc.expectK = k
					}
					if inject {
						fc.dropInitial = map[int]bool{0: true, 2: true}
						fc.dropParity = 1
						fc.corruptParity = 0
					}
					fmt.Fprintf(h, "%s|%d|%d|%v|%v|", mode, m, k, inject, byShort)
					h.Write(rvClientTranscript(fc, k, byShort))
				}
			}
		}
	}
	return fmt.Sprintf("%x", h.Sum(nil))
}

func TestRvClientV2Digest(t *testing.T) {
	gfInit()
	for _, mode := range []string{"off", "buf", "fec"} {
		t.Logf("RVDIGEST client %s %s", mode, rvClientDigest(mode))
	}
}

type rvDg struct {
	data []byte
	orig int
	par  int
}

func rvLegacyFlight(m, k int, seed byte, flight uint16) []rvDg {
	src := make([][]byte, k)
	size := 0
	for i := range src {
		n := 1200 - 31*i
		src[i] = rvInitial(rvDCID, rvSCID, n, seed+byte(i))
		size = max(size, n)
	}
	crcs := make([]uint32, k)
	lens := make([]uint16, k)
	padded := make([][]byte, k)
	for i, d := range src {
		crcs[i] = crc32.ChecksumIEEE(d)
		lens[i] = uint16(len(d))
		padded[i] = make([]byte, size)
		copy(padded[i], d)
	}
	pars := rsEncode(padded, m, size)
	mk := func(j int) rvDg {
		return rvDg{data: buildParity(rvDCID, rvSCID, fecBlock{flight: flight, k: k, m: m, index: j,
			symLen: size, crcs: crcs, lens: lens, sym: pars[j]}), orig: -1, par: j}
	}
	var dg []rvDg
	if m >= 2 {
		dg = append(dg, mk(0))
	}
	for i := range src {
		dg = append(dg, rvDg{data: src[i], orig: i, par: -1})
	}
	for j := 0; j < m; j++ {
		if m >= 2 && j == 0 {
			continue
		}
		dg = append(dg, mk(j))
	}
	return dg
}

func rvOrders(n int, visit func(ord []int)) {
	used := make([]bool, n)
	ord := make([]int, 0, n)
	var rec func()
	rec = func() {
		visit(ord)
		for i := 0; i < n; i++ {
			if used[i] {
				continue
			}
			used[i] = true
			ord = append(ord, i)
			rec()
			ord = ord[:len(ord)-1]
			used[i] = false
		}
	}
	rec()
}

func rvServerRun(dgs [][]byte, viaReadFrom bool, h interface{ Write([]byte) (int, error) }) string {
	sv := &decodeConn{mode: "fec"}
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 3), Port: 5555}
	strict := func() string {
		if sv.stats.BytesToStack+sv.pendingBytes > sv.stats.BytesIn {
			return fmt.Sprint("invariant ", sv.stats.BytesToStack, "+", sv.pendingBytes, " > ", sv.stats.BytesIn)
		}
		if sv.heldBytes < 0 {
			return "held < 0"
		}
		return ""
	}
	if viaReadFrom {
		sv.PacketConn = &auditConn{scriptConn: scriptConn{dgs: dgs, addr: addr}}
		buf := make([]byte, 2000)
		for {
			n, _, err := sv.ReadFrom(buf)
			if err != nil {
				break
			}
			h.Write(binary.BigEndian.AppendUint32(nil, crc32.ChecksumIEEE(buf[:n])))
			sv.mu.Lock()
			bad := strict()
			sv.mu.Unlock()
			if bad != "" {
				return bad
			}
		}
	} else {
		for _, d := range dgs {
			sv.feedOne(d)
			sv.mu.Lock()
			bad := strict()
			sv.mu.Unlock()
			if bad != "" {
				return bad
			}
		}
	}
	st := sv.stats
	fmt.Fprintf(h, "|%d %d %d %d %d %d %d %d %d %d %d %d %d|",
		st.BytesIn, st.BytesToStack, st.Recovered, st.RecoverEvents, st.RecoverFail,
		st.RecoverRefused, st.CreditParities, st.Unrecover, st.LateRecover,
		st.PrematureRecover, st.Parities, sv.pendingBytes, sv.heldBytes)
	keys := make([]string, 0, len(sv.conns))
	for k := range sv.conns {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		c := sv.conns[k]
		fmt.Fprintf(h, "%s %d %d %d %d %d|", k, c.Stack, c.RxBytes, c.RxParity, c.RecovN, c.RxOrigN)
	}
	return ""
}

func TestRvServerLegacyDigest(t *testing.T) {
	gfInit()
	for _, via := range []bool{false, true} {
		h := sha256.New()
		runs := 0
		for m := 1; m <= 4; m++ {
			for k := 1; k <= 3; k++ {
				dg := rvLegacyFlight(m, k, byte(9*m+k), uint16(3+m))
				bad := ""
				rvOrders(len(dg), func(ord []int) {
					if bad != "" {
						return
					}
					runs++
					var send [][]byte
					for _, ix := range ord {
						send = append(send, dg[ix].data)
					}
					fmt.Fprintf(h, "m%d k%d %v:", m, k, ord)
					bad = rvServerRun(send, via, h)
				})
				if bad != "" {
					t.Fatalf("readfrom=%v m %d k %d: %s", via, m, k, bad)
				}
			}
		}
		t.Logf("RVDIGEST server readfrom=%v runs=%d %x", via, runs, h.Sum(nil))
	}
}
