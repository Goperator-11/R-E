package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"hash/crc32"
	"math/big"
	"net"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/quic-go/quic-go"
)

var gfExp [512]byte
var gfLog [256]byte

func gfInit() {
	x := 1
	for i := 0; i < 255; i++ {
		gfExp[i] = byte(x)
		gfLog[x] = byte(i)
		x <<= 1
		if x&0x100 != 0 {
			x ^= 0x11d
		}
	}
	for i := 255; i < 512; i++ {
		gfExp[i] = gfExp[i-255]
	}
}

func gfMul(a, b byte) byte {
	if a == 0 || b == 0 {
		return 0
	}
	return gfExp[int(gfLog[a])+int(gfLog[b])]
}

func gfInv(a byte) byte {
	if a == 0 {
		panic("gf inverse of zero")
	}
	return gfExp[255-int(gfLog[a])]
}

func cauchyRow(m, p, k int) []byte {
	row := make([]byte, k)
	for o := 0; o < k; o++ {
		row[o] = gfInv(byte(p) ^ byte(m+o))
	}
	return row
}

func rsEncode(src [][]byte, m int, size int) [][]byte {
	k := len(src)
	out := make([][]byte, m)
	if m == 1 {
		p := make([]byte, size)
		for _, d := range src {
			for i := 0; i < len(d); i++ {
				p[i] ^= d[i]
			}
		}
		out[0] = p
		return out
	}
	for j := 0; j < m; j++ {
		row := cauchyRow(m, j, k)
		p := make([]byte, size)
		for i, d := range src {
			c := row[i]
			if c == 0 {
				continue
			}
			for b := 0; b < len(d); b++ {
				p[b] ^= gfMul(c, d[b])
			}
		}
		out[j] = p
	}
	return out
}

func parityRow(m, p, k int) []byte {
	if m == 1 {
		row := make([]byte, k)
		for o := range row {
			row[o] = 1
		}
		return row
	}
	return cauchyRow(m, p, k)
}

func gfMatInv(a [][]byte) [][]byte {
	n := len(a)
	aug := make([][]byte, n)
	for i := 0; i < n; i++ {
		aug[i] = make([]byte, 2*n)
		copy(aug[i], a[i])
		aug[i][n+i] = 1
	}
	for col := 0; col < n; col++ {
		piv := -1
		for r := col; r < n; r++ {
			if aug[r][col] != 0 {
				piv = r
				break
			}
		}
		if piv < 0 {
			return nil
		}
		aug[col], aug[piv] = aug[piv], aug[col]
		inv := gfInv(aug[col][col])
		for j := 0; j < 2*n; j++ {
			aug[col][j] = gfMul(inv, aug[col][j])
		}
		for r := 0; r < n; r++ {
			if r == col || aug[r][col] == 0 {
				continue
			}
			f := aug[r][col]
			for j := 0; j < 2*n; j++ {
				aug[r][j] ^= gfMul(f, aug[col][j])
			}
		}
	}
	out := make([][]byte, n)
	for i := 0; i < n; i++ {
		out[i] = aug[i][n:]
	}
	return out
}

func recoverMany(k, m int, missing []int, origs map[int][]byte,
	parities map[int][]byte, size int) map[int][]byte {
	e := len(missing)
	if e == 0 || e > k {
		return nil
	}
	for i := 0; i < k; i++ {
		if inIntSlice(missing, i) {
			continue
		}
		if _, ok := origs[i]; !ok {
			return nil
		}
	}
	pidx := make([]int, 0, len(parities))
	for j := range parities {
		pidx = append(pidx, j)
	}
	if len(pidx) < e {
		return nil
	}
	sort.Ints(pidx)
	pidx = pidx[:e]

	miss := append([]int(nil), missing...)
	sort.Ints(miss)

	syn := make([][]byte, e)
	for r, j := range pidx {
		row := parityRow(m, j, k)
		acc := make([]byte, size)
		copy(acc, parities[j])
		for i := 0; i < k; i++ {
			if inIntSlice(miss, i) {
				continue
			}
			d := origs[i]
			c := row[i]
			for b := 0; b < len(d) && b < size; b++ {
				acc[b] ^= gfMul(c, d[b])
			}
		}
		syn[r] = acc
	}
	sub := make([][]byte, e)
	for r, j := range pidx {
		row := parityRow(m, j, k)
		sub[r] = make([]byte, e)
		for c, o := range miss {
			sub[r][c] = row[o]
		}
	}
	inv := gfMatInv(sub)
	if inv == nil {
		return nil
	}
	out := map[int][]byte{}
	for c, o := range miss {
		buf := make([]byte, size)
		for r := 0; r < e; r++ {
			f := inv[c][r]
			if f == 0 {
				continue
			}
			sr := syn[r]
			for b := 0; b < size; b++ {
				buf[b] ^= gfMul(f, sr[b])
			}
		}
		out[o] = buf
	}
	return out
}

func permutations(n int) [][]int {
	idx := make([]int, n)
	for i := range idx {
		idx[i] = i
	}
	var out [][]int
	var rec func(k int)
	rec = func(k int) {
		if k == n {
			out = append(out, append([]int(nil), idx...))
			return
		}
		for i := k; i < n; i++ {
			idx[k], idx[i] = idx[i], idx[k]
			rec(k + 1)
			idx[k], idx[i] = idx[i], idx[k]
		}
	}
	rec(0)
	return out
}

func (s *decodeConn) feedOne(d []byte) {
	b := make([]byte, 2000)
	copy(b, d)
	n := len(d)
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 3), Port: 5555}
	s.countRx(n)
	var fb *fecBlock
	if s.mode != "off" {
		fb = parseFecBlock(b[:n])
	}
	s.mu.Lock()
	s.expireLocked(time.Now())
	s.stats.BytesIn += int64(n)
	ca := s.acctLocked(addr, b[:n], false)
	s.mu.Unlock()
	if fb == nil {
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		s.noteOriginal(b[:n], addr)
		return
	}
	s.mu.Lock()
	if fb.m >= 2 && fb.index == 0 {
		s.stats.CreditParities++
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return
	}
	dc := dcidOf(b[:n])
	key := fmt.Sprintf("%x|%d", dc, fb.flight)
	if s.flights == nil {
		s.flights = map[string]*flightRec{}
	}
	fr := s.flights[key]
	if fr == nil {
		fr = &flightRec{fb: fb, dcid: dc, addr: addr, acct: ca, created: time.Now(),
			syms: map[int][]byte{}}
		s.flights[key] = fr
	} else if !sameFecFlight(fr.fb, fb) {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return
	}
	if fr.done || fr.poisoned {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return
	}
	fr.syms[fb.index] = fb.sym
	outs := s.tryRecoverLocked(fr, true)
	if rec := s.settleRecovery(fr, outs); rec != nil {
		s.stackLocked(fr.acct, len(rec))
		s.mu.Unlock()
		return
	}
	if len(outs) == 0 && s.pendingErasures(fr) >= 2 {
		fr.heldBytes += int64(n)
		s.heldBytes += int64(n)
		s.mu.Unlock()
		return
	}
	s.stackLocked(ca, n)
	s.mu.Unlock()
}

func (s *decodeConn) pendingErasures(fr *flightRec) int {
	fb := fr.fb
	miss := 0
	for i := 0; i < fb.k; i++ {
		found := false
		for _, r := range s.recent {
			if r.crc == fb.crcs[i] && r.dcid == fr.dcid {
				found = true
				break
			}
		}
		if !found {
			miss++
		}
	}
	return miss
}

func (s *decodeConn) settleRecovery(fr *flightRec, outs [][]byte) []byte {
	if fr == nil || fr.done || fr.poisoned || len(outs) == 0 {
		return nil
	}
	var tot int64
	for _, o := range outs {
		if len(o) == 0 {
			return nil
		}
		tot += int64(len(o))
	}
	if s.stats.BytesToStack+s.pendingBytes+tot > s.stats.BytesIn {
		s.stats.RecoverRefused++
		return nil
	}
	fr.done = true
	s.stats.Recovered += len(outs)
	if fr.acct != nil && !fr.acct.FbSent {
		fr.acct.RecovN += len(outs)
	}
	s.stats.RecoverEvents++
	if fr.recCRC == nil {
		fr.recCRC = map[uint32]bool{}
	}
	for _, o := range outs {
		fr.recCRC[crc32.ChecksumIEEE(o)] = true
	}
	for _, extra := range outs[1:] {
		s.pending = append(s.pending, pendingPkt{data: extra, addr: fr.addr, acct: fr.acct})
		s.pendingBytes += int64(len(extra))
	}
	s.heldBytes -= fr.heldBytes
	fr.heldBytes = 0
	return outs[0]
}

func combinations(n, r int) [][]int {
	var out [][]int
	cur := make([]int, r)
	var rec func(start, depth int)
	rec = func(start, depth int) {
		if depth == r {
			out = append(out, append([]int(nil), cur...))
			return
		}
		for i := start; i < n; i++ {
			cur[depth] = i
			rec(i+1, depth+1)
		}
	}
	if r >= 0 && r <= n {
		rec(0, 0)
	}
	return out
}

func inIntSlice(v []int, x int) bool {
	for _, y := range v {
		if y == x {
			return true
		}
	}
	return false
}

func recoverOne(k, m, parityIdx, missing int, origs map[int][]byte,
	parity []byte, size int) []byte {
	acc := make([]byte, size)
	copy(acc, parity)
	if m == 1 {
		for i, d := range origs {
			if i == missing {
				continue
			}
			for b := 0; b < len(d) && b < size; b++ {
				acc[b] ^= d[b]
			}
		}
		return acc
	}
	row := cauchyRow(m, parityIdx, k)
	for i := 0; i < k; i++ {
		if i == missing {
			continue
		}
		d, ok := origs[i]
		if !ok {
			return nil
		}
		c := row[i]
		for b := 0; b < len(d) && b < size; b++ {
			acc[b] ^= gfMul(c, d[b])
		}
	}
	inv := gfInv(row[missing])
	for b := 0; b < size; b++ {
		acc[b] = gfMul(inv, acc[b])
	}
	return acc
}

type longHdr struct {
	ok      bool
	typ     byte
	version uint32
	dcid    []byte
	scid    []byte
	bodyOff int
}

func parseLongHdr(b []byte) longHdr {
	var h longHdr
	if len(b) < 7 || b[0]&0x80 == 0 || b[0]&0x40 == 0 {
		return h
	}
	h.typ = (b[0] & 0x30) >> 4
	h.version = binary.BigEndian.Uint32(b[1:5])
	i := 5
	if i >= len(b) {
		return h
	}
	dcil := int(b[i])
	i++
	if i+dcil > len(b) {
		return h
	}
	h.dcid = b[i : i+dcil]
	i += dcil
	if i >= len(b) {
		return h
	}
	scil := int(b[i])
	i++
	if i+scil > len(b) {
		return h
	}
	h.scid = b[i : i+scil]
	i += scil
	h.bodyOff = i
	h.ok = true
	return h
}

func appendVarint2(b []byte, v uint64) []byte {
	return append(b, byte(0x40|(v>>8)), byte(v))
}

const fecMagicLen = 4

var fecMagic = []byte{'P', 'F', 'E', 'C'}

const fecVer = 1

type fecBlock struct {
	flight uint16
	k      int
	m      int
	index  int
	symLen int
	crcs   []uint32
	lens   []uint16
	sym    []byte
}

func sameFecFlight(a, b *fecBlock) bool {
	if a == nil || b == nil || a.flight != b.flight || a.k != b.k || a.m != b.m || a.symLen != b.symLen ||
		len(a.crcs) != len(b.crcs) || len(a.lens) != len(b.lens) {
		return false
	}
	for i := range a.crcs {
		if a.crcs[i] != b.crcs[i] {
			return false
		}
	}
	for i := range a.lens {
		if a.lens[i] != b.lens[i] {
			return false
		}
	}
	return true
}

func buildParity(dcid, scid []byte, fb fecBlock) []byte {
	body := make([]byte, 0, len(fb.sym)+64)
	body = append(body, fecMagic...)
	body = append(body, byte(fecVer))
	body = binary.BigEndian.AppendUint16(body, fb.flight)
	body = append(body, byte(fb.k), byte(fb.m), byte(fb.index))
	body = binary.BigEndian.AppendUint16(body, uint16(fb.symLen))
	for _, c := range fb.crcs {
		body = binary.BigEndian.AppendUint32(body, c)
	}
	for _, l := range fb.lens {
		body = binary.BigEndian.AppendUint16(body, l)
	}
	body = append(body, fb.sym...)

	out := make([]byte, 0, len(body)+64)
	out = append(out, 0xC3)
	out = binary.BigEndian.AppendUint32(out, 1)
	out = append(out, byte(len(dcid)))
	out = append(out, dcid...)
	out = append(out, byte(len(scid)))
	out = append(out, scid...)
	out = append(out, 0x00)
	out = appendVarint2(out, uint64(len(body)))
	out = append(out, body...)
	return out
}

var fbEarly = os.Getenv("PADFEC_FB_EARLY") == "1"

var fbMagic = []byte{'P', 'F', 'B', 'K'}

func bytesIndex(h, nd []byte) int {
	for i := 0; i+len(nd) <= len(h); i++ {
		ok := true
		for j := range nd {
			if h[i+j] != nd[j] {
				ok = false
				break
			}
		}
		if ok {
			return i
		}
	}
	return -1
}

const fbVer = 2
const fbCRCCap = 64

type fbRec struct {
	flight    uint16
	k         uint8
	rxOrig    uint8
	rxPar     uint8
	recov     uint8
	crcs      []uint32
	truncated bool
}

func buildFeedback(dcid, scid []byte, r fbRec) []byte {
	body := make([]byte, 0, 16)
	body = append(body, fbMagic...)
	body = append(body, byte(fbVer))
	body = binary.BigEndian.AppendUint16(body, r.flight)
	body = append(body, r.k, r.rxOrig, r.rxPar, r.recov)
	crcs := r.crcs
	truncated := r.truncated || len(crcs) > fbCRCCap
	if len(crcs) > fbCRCCap {
		crcs = crcs[:fbCRCCap]
	}
	count := byte(len(crcs))
	if truncated {
		count |= 0x80
	}
	body = append(body, count)
	for _, crc := range crcs {
		body = binary.BigEndian.AppendUint32(body, crc)
	}

	out := make([]byte, 0, len(body)+64)
	out = append(out, 0xC3)
	out = binary.BigEndian.AppendUint32(out, 1)
	out = append(out, byte(len(dcid)))
	out = append(out, dcid...)
	out = append(out, byte(len(scid)))
	out = append(out, scid...)
	out = append(out, 0x00)
	out = appendVarint2(out, uint64(len(body)))
	out = append(out, body...)
	return out
}

func readVarint(b []byte) (uint64, int) {
	if len(b) == 0 {
		return 0, 0
	}
	n := 1 << (b[0] >> 6)
	if len(b) < n {
		return 0, 0
	}
	v := uint64(b[0] & 0x3F)
	for i := 1; i < n; i++ {
		v = v<<8 | uint64(b[i])
	}
	return v, n
}

func hasHandshake(d []byte) bool {
	i := 0
	for i < len(d) {
		h := parseLongHdr(d[i:])
		if !h.ok {
			return false
		}
		if h.typ == 2 {
			return true
		}
		j := h.bodyOff
		if h.typ == 0 {
			tl, adv := readVarint(d[i+j:])
			if adv == 0 {
				return false
			}
			j += adv + int(tl)
		}
		if i+j >= len(d) {
			return false
		}
		plen, adv := readVarint(d[i+j:])
		if adv == 0 || plen == 0 {
			return false
		}
		j += adv + int(plen)
		if j <= 0 || i+j > len(d) {
			return false
		}
		i += j
	}
	return false
}

func parseFeedback(d []byte) *fbRec {
	h := parseLongHdr(d)
	if !h.ok || h.typ != 0 {
		return nil
	}
	i := h.bodyOff
	if i >= len(d) || d[i] != 0x00 {
		return nil
	}
	i++
	if i+2 > len(d) || d[i]&0xC0 != 0x40 {
		return nil
	}
	blen := int(d[i]&0x3F)<<8 | int(d[i+1])
	i += 2
	if i+blen > len(d) || blen < fecMagicLen+8 {
		return nil
	}
	b := d[i : i+blen]
	if string(b[:fecMagicLen]) != string(fbMagic) || b[4] != fbVer {
		return nil
	}
	nc := int(b[11] & 0x7f)
	if nc > fbCRCCap || blen != 12+4*nc {
		return nil
	}
	r := &fbRec{
		flight: binary.BigEndian.Uint16(b[5:7]),
		k:      b[7], rxOrig: b[8], rxPar: b[9], recov: b[10],
		truncated: b[11]&0x80 != 0,
	}
	for x := 0; x < nc; x++ {
		j := 12 + 4*x
		r.crcs = append(r.crcs, binary.BigEndian.Uint32(b[j:j+4]))
	}
	return r
}

func inCRC(values []uint32, crc uint32) bool {
	for _, value := range values {
		if value == crc {
			return true
		}
	}
	return false
}

func matchFirstFlight(r *fbRec, origCRC, parCRC []uint32) (rxOrig, rxPar, retx int) {
	if r == nil {
		return
	}
	seen := map[uint32]bool{}
	for _, crc := range r.crcs {
		if seen[crc] {
			continue
		}
		seen[crc] = true
		if inCRC(origCRC, crc) {
			rxOrig++
		} else if inCRC(parCRC, crc) {
			rxPar++
		} else {
			retx++
		}
	}
	return
}

func parseFecBlock(d []byte) *fecBlock {
	h := parseLongHdr(d)
	if !h.ok || h.typ != 0 {
		return nil
	}
	i := h.bodyOff
	if i >= len(d) || d[i] != 0x00 {
		return nil
	}
	i++
	if i+2 > len(d) {
		return nil
	}
	if d[i]&0xC0 != 0x40 {
		return nil
	}
	blen := int(d[i]&0x3F)<<8 | int(d[i+1])
	i += 2
	if i+blen > len(d) || blen < fecMagicLen+9 {
		return nil
	}
	b := d[i : i+blen]
	if string(b[:fecMagicLen]) != string(fecMagic) || b[4] != fecVer {
		return nil
	}
	j := 5
	fb := &fecBlock{}
	fb.flight = binary.BigEndian.Uint16(b[j : j+2])
	j += 2
	fb.k = int(b[j])
	fb.m = int(b[j+1])
	fb.index = int(b[j+2])
	j += 3
	fb.symLen = int(binary.BigEndian.Uint16(b[j : j+2]))
	j += 2
	if fb.k < 1 || fb.k > 32 || fb.m < 1 || fb.m > 8 || fb.index >= fb.m || fb.symLen == 0 {
		return nil
	}
	need := j + 4*fb.k + 2*fb.k + fb.symLen
	if need > len(b) {
		return nil
	}
	fb.crcs = make([]uint32, fb.k)
	for x := 0; x < fb.k; x++ {
		fb.crcs[x] = binary.BigEndian.Uint32(b[j : j+4])
		j += 4
	}
	fb.lens = make([]uint16, fb.k)
	for x := 0; x < fb.k; x++ {
		fb.lens[x] = binary.BigEndian.Uint16(b[j : j+2])
		j += 2
		if int(fb.lens[x]) > fb.symLen {
			return nil
		}
	}
	fb.sym = append([]byte(nil), b[j:j+fb.symLen]...)
	return fb
}

type countConn struct {
	net.PacketConn
	cmu      sync.Mutex
	TxDgrams int
	TxBytes  int64
	RxDgrams int
	RxBytes  int64
}

func (c *countConn) countTx(n int) {
	c.cmu.Lock()
	c.TxDgrams++
	c.TxBytes += int64(n)
	c.cmu.Unlock()
}

func (c *countConn) countRx(n int) {
	c.cmu.Lock()
	c.RxDgrams++
	c.RxBytes += int64(n)
	c.cmu.Unlock()
}

func (c *countConn) counts() (int, int64, int, int64) {
	c.cmu.Lock()
	defer c.cmu.Unlock()
	return c.TxDgrams, c.TxBytes, c.RxDgrams, c.RxBytes
}

type clientStats struct {
	Flights                int            `json:"flights"`
	FlightSizes            map[string]int `json:"flight_sizes"`
	ParitySent             int            `json:"parity_sent"`
	ParityFail             int            `json:"parity_fail"`
	DroppedOrig            int            `json:"dropped_originals"`
	DroppedPar             int            `json:"dropped_parities"`
	CorruptPar             int            `json:"corrupted_parities"`
	BytesOrig              int64          `json:"bytes_orig"`
	BytesParity            int64          `json:"bytes_parity"`
	InitialDgram           int            `json:"initial_datagrams"`
	FbRecv                 int            `json:"fb_recv"`
	FbMagicSeen            int            `json:"fb_magic_seen"`
	RxCalls                int            `json:"rx_calls"`
	FbWaits                int            `json:"fb_waits"`
	FbRxOrig               int            `json:"fb_rx_orig"`
	FbRxPar                int            `json:"fb_rx_parity"`
	FbRxRetx               int            `json:"fb_rx_retx"`
	FbRawOrig              int            `json:"fb_raw_orig"`
	FbRawPar               int            `json:"fb_raw_parity"`
	FbTruncated            bool           `json:"fb_truncated"`
	FbRecov                int            `json:"fb_recovered"`
	FirstFlightDgrams      int            `json:"first_flight_datagrams"`
	FirstFlightBytes       int64          `json:"first_flight_bytes"`
	FirstFlightParity      int            `json:"first_flight_parity_dgrams"`
	FirstFlightParityBytes int64          `json:"first_flight_parity_bytes"`
}

type fecConn struct {
	countConn
	mode          string
	m             int
	parityDelay   time.Duration
	expectK       int
	dropInitial   map[int]bool
	dropParity    int
	corruptParity int

	dumpPath string

	onFeedback func(fbRec)
	fbLast     *fbRec
	fbCount    int
	ffOrigCRC  []uint32
	ffParCRC   []uint32

	mu       sync.Mutex
	flight   [][]byte
	flightID uint16
	dcid     []byte
	scid     []byte
	peer     net.Addr
	timer    *time.Timer
	stats    clientStats
}

func (c *fecConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	h := parseLongHdr(b)
	isInitial := h.ok && h.typ == 0
	if isInitial {
		c.mu.Lock()
		c.stats.InitialDgram++
		c.stats.BytesOrig += int64(len(b))
		c.mu.Unlock()
	}
	if !isInitial {
		c.flushFlight()
		return c.PacketConn.WriteTo(b, addr)
	}
	var immediate int
	var ierr error
	if c.mode == "off" {
		c.mu.Lock()
		idx := len(c.flight)
		first := c.stats.Flights == 0
		c.mu.Unlock()
		if first && c.dropInitial[idx] {
			c.mu.Lock()
			c.stats.DroppedOrig++
			c.mu.Unlock()
			immediate = len(b)
		} else {
			immediate, ierr = c.PacketConn.WriteTo(b, addr)
			if ierr != nil {
				return immediate, ierr
			}
			c.countTx(len(b))
		}
	}

	cp := append([]byte(nil), b...)
	c.mu.Lock()
	if len(c.flight) == 0 {
		c.flightID++
		c.dcid = append([]byte(nil), h.dcid...)
		c.scid = append([]byte(nil), h.scid...)
		c.peer = addr
	}
	c.flight = append(c.flight, cp)
	ready := c.expectK > 0 && len(c.flight) >= c.expectK
	if c.timer != nil {
		c.timer.Stop()
	}
	if !ready {
		c.timer = time.AfterFunc(c.parityDelay, c.flushFlight)
	}
	c.mu.Unlock()
	if ready {
		c.flushFlight()
	}
	if c.mode == "off" {
		return immediate, nil
	}
	return len(b), nil
}

func (c *fecConn) ReadFrom(b []byte) (int, net.Addr, error) {
	for {
		n, addr, err := c.PacketConn.ReadFrom(b)
		if err != nil || n <= 0 {
			return n, addr, err
		}
		if parseFeedback(b[:n]) == nil {
			c.countRx(n)
		}
		c.mu.Lock()
		c.stats.RxCalls++
		c.mu.Unlock()
		if n > 16 && bytesIndex(b[:n], fbMagic) >= 0 {
			c.mu.Lock()
			c.stats.FbMagicSeen++
			c.mu.Unlock()
		}
		if r := parseFeedback(b[:n]); r != nil {
			c.mu.Lock()
			c.fbLast = r
			c.fbCount++
			c.stats.FbRecv++
			o, p, x := matchFirstFlight(r, c.ffOrigCRC, c.ffParCRC)
			c.stats.FbRxOrig = o
			c.stats.FbRxPar = p
			c.stats.FbRxRetx = x
			c.stats.FbRawOrig = int(r.rxOrig)
			c.stats.FbRawPar = int(r.rxPar)
			c.stats.FbTruncated = r.truncated
			c.stats.FbRecov = int(r.recov)
			cb := c.onFeedback
			c.mu.Unlock()
			if cb != nil {
				cb(*r)
			}
			continue
		}
		return n, addr, err
	}
}

func (c *fecConn) waitFeedback(d time.Duration) bool {
	c.mu.Lock()
	c.stats.FbWaits++
	c.mu.Unlock()
	deadline := time.Now().Add(d)
	for time.Now().Before(deadline) {
		c.mu.Lock()
		got := c.fbCount > 0
		c.mu.Unlock()
		if got {
			return true
		}
		time.Sleep(500 * time.Microsecond)
	}
	return false
}

func (c *fecConn) lastFeedback() *fbRec {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.fbLast
}

func (c *fecConn) matchFeedback(r *fbRec) (int, int, int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return matchFirstFlight(r, c.ffOrigCRC, c.ffParCRC)
}

func (c *fecConn) flushFlight() {
	c.mu.Lock()
	fl := c.flight
	dcid := c.dcid
	scid := c.scid
	peer := c.peer
	fid := c.flightID
	c.flight = nil
	if c.timer != nil {
		c.timer.Stop()
		c.timer = nil
	}
	c.mu.Unlock()

	if len(fl) == 0 || peer == nil {
		return
	}
	k := len(fl)
	size := 0
	for _, d := range fl {
		if len(d) > size {
			size = len(d)
		}
	}

	c.mu.Lock()
	if c.stats.Flights == 0 && c.dumpPath != "" {
		var blob []byte
		for _, d := range fl {
			blob = binary.BigEndian.AppendUint16(blob, uint16(len(d)))
			blob = append(blob, d...)
		}
		os.WriteFile(c.dumpPath, blob, 0644)
	}
	if c.stats.Flights == 0 {
		c.stats.FirstFlightDgrams = k
		var tot int64
		for _, d := range fl {
			tot += int64(len(d))
		}
		c.stats.FirstFlightBytes = tot
	}
	c.stats.Flights++
	isFirstFlight := c.stats.Flights == 1
	if isFirstFlight {
		for _, d := range fl {
			c.ffOrigCRC = append(c.ffOrigCRC, crc32.ChecksumIEEE(d))
		}
	}
	if c.stats.FlightSizes == nil {
		c.stats.FlightSizes = map[string]int{}
	}
	c.stats.FlightSizes[fmt.Sprint(k)]++
	sendMode := c.mode
	c.mu.Unlock()

	send := func(d []byte) error {
		_, err := c.PacketConn.WriteTo(d, peer)
		if err == nil {
			c.countTx(len(d))
		}
		return err
	}

	if sendMode == "off" {
		return
	}
	sendOrig := func(i int, d []byte) {
		if isFirstFlight && c.dropInitial[i] {
			c.mu.Lock()
			c.stats.DroppedOrig++
			c.mu.Unlock()
			return
		}
		send(d)
	}

	if sendMode == "buf" {
		for i, d := range fl {
			sendOrig(i, d)
		}
		return
	}

	crcs := make([]uint32, k)
	lens := make([]uint16, k)
	padded := make([][]byte, k)
	for i, d := range fl {
		crcs[i] = crc32.ChecksumIEEE(d)
		lens[i] = uint16(len(d))
		q := make([]byte, size)
		copy(q, d)
		padded[i] = q
	}
	pars := rsEncode(padded, c.m, size)

	mk := func(j int, par []byte) []byte {
		return buildParity(dcid, scid, fecBlock{
			flight: fid, k: k, m: c.m, index: j,
			symLen: size, crcs: crcs, lens: lens, sym: par,
		})
	}
	emit := func(j int, pkt []byte) {
		if isFirstFlight && c.dropParity == j {
			c.mu.Lock()
			c.stats.DroppedPar++
			c.mu.Unlock()
			return
		}
		if isFirstFlight && c.corruptParity == j && len(pkt) > 8 {
			pkt = append([]byte(nil), pkt...)
			pkt[len(pkt)/2] ^= 0xFF
			c.mu.Lock()
			c.stats.CorruptPar++
			c.mu.Unlock()
		}
		err := send(pkt)
		c.mu.Lock()
		if err == nil {
			c.stats.ParitySent++
			c.stats.BytesParity += int64(len(pkt))
			if isFirstFlight {
				c.stats.FirstFlightParity++
				c.stats.FirstFlightParityBytes += int64(len(pkt))
				c.ffParCRC = append(c.ffParCRC, crc32.ChecksumIEEE(pkt))
			}
		} else {
			c.stats.ParityFail++
		}
		c.mu.Unlock()
	}

	if c.m >= 2 {
		emit(0, mk(0, pars[0]))
	}
	for i := 0; i < k; i++ {
		sendOrig(i, fl[i])
	}
	for j := 0; j < len(pars); j++ {
		if c.m >= 2 && j == 0 {
			continue
		}
		emit(j, mk(j, pars[j]))
	}
}

func (c *fecConn) snapshot() clientStats {
	c.mu.Lock()
	defer c.mu.Unlock()
	s := c.stats
	fs := map[string]int{}
	for k, v := range s.FlightSizes {
		fs[k] = v
	}
	s.FlightSizes = fs
	return s
}

type serverStats struct {
	Originals              int   `json:"originals"`
	Parities               int   `json:"parities"`
	Recovered              int   `json:"recovered"`
	RecoverEvents          int   `json:"recover_events"`
	PrematureRecover       int   `json:"premature_recovered"`
	RecoverFail            int   `json:"recover_crc_fail"`
	LateRecover            int   `json:"late_recovered"`
	RecoverRefused         int   `json:"recover_refused_by_accounting"`
	CreditParities         int   `json:"credit_parities"`
	Unrecover              int   `json:"unrecoverable_seen"`
	BytesIn                int64 `json:"bytes_in"`
	BytesToStack           int64 `json:"bytes_to_stack"`
	ConnAcctDropped        int   `json:"conn_acct_dropped"`
	ConnAcctUnmappedRX     int   `json:"conn_acct_unmapped_rx"`
	ConnAcctUnmappedTX     int   `json:"conn_acct_unmapped_tx"`
	ConnAcctUnmappedStack  int64 `json:"conn_acct_unmapped_stack_bytes"`
	ConnAcctAliasConflicts int   `json:"conn_acct_alias_conflicts"`
	ConnAcctAliasDropped   int   `json:"conn_acct_alias_dropped"`
	HdrInitial             int   `json:"hdr_initial"`
	HdrHandshake           int   `json:"hdr_handshake"`
	HdrShort               int   `json:"hdr_short"`
	FbSentN                int   `json:"fb_sent"`
	FbWriteErr             int   `json:"fb_write_err"`
	HdrCoalescedHS         int   `json:"hdr_coalesced_hs"`
}

type recvItem struct {
	dcid string
	crc  uint32
	data []byte
	addr net.Addr
	t    time.Time
}

type flightRec struct {
	fb        *fecBlock
	dcid      string
	addr      net.Addr
	acct      *connAcct
	created   time.Time
	done      bool
	recCRC    map[uint32]bool
	syms      map[int][]byte
	heldBytes int64
	poisoned  bool
}

type pendingPkt struct {
	data []byte
	addr net.Addr
	acct *connAcct
}

type connAcct struct {
	InitialDCID    string `json:"initial_dcid"`
	ClientSCID     string `json:"client_scid"`
	FirstPeer      string `json:"first_peer"`
	LastPeer       string `json:"last_peer"`
	PeerChanges    int    `json:"peer_changes"`
	aliasCount     int
	FirstRxNs      int64    `json:"first_rx_ns"`
	FirstTxNs      int64    `json:"first_tx_ns"`
	RxDgrams       int      `json:"rx_dgrams"`
	RxBytes        int64    `json:"rx_bytes"`
	RxOrig         int64    `json:"rx_orig_bytes"`
	RxParity       int64    `json:"rx_parity_bytes"`
	RxOrigN        int      `json:"rx_orig_n"`
	RxParityN      int      `json:"rx_parity_n"`
	RxCRC          []uint32 `json:"rx_crc"`
	RxCRCTruncated bool     `json:"rx_crc_truncated"`
	RecovN         int      `json:"recov_n"`
	FbSent         bool     `json:"fb_sent"`
	Stack          int64    `json:"stack_bytes"`
	TxDgrams       int      `json:"tx_dgrams"`
	TxBytes        int64    `json:"tx_bytes"`
	BeffStack      int64    `json:"beff_stack"`
	BeffPhys       int64    `json:"beff_phys"`
	BeffOrig       int64    `json:"beff_orig"`
	BeffParity     int64    `json:"beff_parity"`
	TxRxTimeline   []int64  `json:"tx_rx_timeline"`
	TxSizes        []int    `json:"tx_sizes"`
	TxNs           []int64  `json:"tx_ns"`
}

const connAcctCap = 4096
const connTimelineCap = 40

const flightTTL = 1 * time.Second
const recentTTL = 3 * time.Second
const recentCap = 512

func min8(v int) int {
	if v < 0 {
		return 0
	}
	if v > 255 {
		return 255
	}
	return v
}

type decodeConn struct {
	countConn
	mode     string
	feedback bool

	mu           sync.Mutex
	recent       []recvItem
	flights      map[string]*flightRec
	pending      []pendingPkt
	pendingBytes int64
	heldBytes    int64
	conns        map[string]*connAcct
	clientCIDs   map[string]*connAcct
	serverCIDs   map[string]*connAcct
	stats        serverStats
}

const connAliasCap = 16

const serverConnIDLength = 4

func (s *decodeConn) bindCIDLocked(index map[string]*connAcct, cid []byte, ca *connAcct) {
	if len(cid) == 0 || len(cid) > 20 || ca == nil {
		return
	}
	key := string(cid)
	if old, exists := index[key]; exists {
		if old != ca && old != nil {
			index[key] = nil
			s.stats.ConnAcctAliasConflicts++
		}
		return
	}
	if ca.aliasCount >= connAliasCap {
		s.stats.ConnAcctAliasDropped++
		return
	}
	index[key] = ca
	ca.aliasCount++
}

func shortCIDAccount(b []byte, index map[string]*connAcct) *connAcct {
	if len(b) < 2 || b[0]&0xc0 != 0x40 {
		return nil
	}
	var found *connAcct
	for n := 1; n <= 20 && n < len(b); n++ {
		ca, exists := index[string(b[1:1+n])]
		if !exists {
			continue
		}
		if ca == nil || (found != nil && found != ca) {
			return nil
		}
		found = ca
	}
	return found
}

func (s *decodeConn) acctLocked(addr net.Addr, b []byte, outbound bool) *connAcct {
	if s.clientCIDs == nil {
		s.clientCIDs = map[string]*connAcct{}
	}
	if s.serverCIDs == nil {
		s.serverCIDs = map[string]*connAcct{}
	}
	h := parseLongHdr(b)
	var ca *connAcct
	if !h.ok {
		if outbound {
			ca = shortCIDAccount(b, s.clientCIDs)
		} else {
			ca = shortCIDAccount(b, s.serverCIDs)
		}
	} else if len(h.scid) <= 20 && len(h.dcid) <= 20 {
		if outbound {
			ca = s.serverCIDs[string(h.scid)]
			if dst := s.clientCIDs[string(h.dcid)]; ca != nil && dst != nil && ca != dst {
				s.serverCIDs[string(h.scid)] = nil
				s.stats.ConnAcctAliasConflicts++
				return nil
			}
			if ca == nil {
				ca = s.clientCIDs[string(h.dcid)]
			}
			if ca != nil {
				s.bindCIDLocked(s.serverCIDs, h.scid, ca)
			}
		} else {
			if h.typ == 0 && len(h.scid) > 0 && len(h.dcid) > 0 && len(h.dcid) != serverConnIDLength {
				key := fmt.Sprintf("initial:%x/%x", h.dcid, h.scid)
				ca = s.conns[key]
				if ca == nil {
					if len(s.conns) >= connAcctCap {
						s.stats.ConnAcctDropped++
						return nil
					}
					if s.conns == nil {
						s.conns = map[string]*connAcct{}
					}
					ca = &connAcct{InitialDCID: fmt.Sprintf("%x", h.dcid), ClientSCID: fmt.Sprintf("%x", h.scid)}
					s.conns[key] = ca
				}
			} else {
				ca = s.serverCIDs[string(h.dcid)]
				if src := s.clientCIDs[string(h.scid)]; ca != nil && src != nil && ca != src {
					s.stats.ConnAcctAliasConflicts++
					return nil
				}
				if ca == nil {
					ca = s.clientCIDs[string(h.scid)]
				}
			}
			if ca != nil {
				s.bindCIDLocked(s.clientCIDs, h.scid, ca)
				s.bindCIDLocked(s.serverCIDs, h.dcid, ca)
			}
		}
	}
	if ca != nil && addr != nil {
		peer := addr.String()
		if ca.FirstPeer == "" {
			ca.FirstPeer = peer
		}
		if ca.LastPeer != "" && ca.LastPeer != peer {
			ca.PeerChanges++
		}
		ca.LastPeer = peer
	}
	return ca
}

func (s *decodeConn) stackLocked(ca *connAcct, n int) {
	s.stats.BytesToStack += int64(n)
	if ca != nil {
		ca.Stack += int64(n)
	} else {
		s.stats.ConnAcctUnmappedStack += int64(n)
	}
}

func (s *decodeConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	s.mu.Lock()
	if ca := s.acctLocked(addr, b, true); ca != nil {
		now := time.Now().UnixNano()
		if ca.TxDgrams == 0 {
			ca.FirstTxNs = now
			ca.BeffStack = ca.Stack
			ca.BeffPhys = ca.RxBytes
			ca.BeffOrig = ca.RxOrig
			ca.BeffParity = ca.RxParity
		}
		if len(ca.TxRxTimeline) < connTimelineCap {
			ca.TxRxTimeline = append(ca.TxRxTimeline, ca.Stack)
			ca.TxSizes = append(ca.TxSizes, len(b))
			ca.TxNs = append(ca.TxNs, now)
		}
		ca.TxDgrams++
		ca.TxBytes += int64(len(b))
	} else {
		s.stats.ConnAcctUnmappedTX++
	}
	s.mu.Unlock()
	n, err := s.PacketConn.WriteTo(b, addr)
	if err == nil {
		s.countTx(n)
	}
	return n, err
}

func dcidOf(d []byte) string {
	h := parseLongHdr(d)
	if !h.ok {
		return ""
	}
	return string(h.dcid)
}

func (s *decodeConn) expireLocked(now time.Time) {
	keep := s.recent[:0]
	for _, r := range s.recent {
		if now.Sub(r.t) < recentTTL {
			keep = append(keep, r)
		}
	}
	s.recent = keep
	if len(s.recent) > recentCap {
		s.recent = s.recent[len(s.recent)-recentCap:]
	}
	for k, fr := range s.flights {
		if now.Sub(fr.created) > flightTTL {
			s.heldBytes -= fr.heldBytes
			fr.heldBytes = 0
			delete(s.flights, k)
		}
	}
}

func (s *decodeConn) noteOriginal(data []byte, addr net.Addr) {
	cp := append([]byte(nil), data...)
	now := time.Now()
	s.mu.Lock()
	s.expireLocked(now)
	dc := dcidOf(cp)
	cr := crc32.ChecksumIEEE(cp)
	s.recent = append(s.recent, recvItem{dcid: dc,
		crc: cr, data: cp, addr: addr, t: now})
	s.stats.Originals++
	for _, fr := range s.flights {
		if fr.dcid == dc && fr.recCRC[cr] {
			s.stats.PrematureRecover++
			break
		}
	}
	s.mu.Unlock()
	s.tryLate()
}

func (s *decodeConn) tryRecoverLocked(fr *flightRec, count bool) [][]byte {
	fb := fr.fb
	have := map[int][]byte{}
	for i, c := range fb.crcs {
		for _, r := range s.recent {
			if r.crc == c && r.dcid == fr.dcid {
				q := make([]byte, fb.symLen)
				copy(q, r.data)
				have[i] = q
				break
			}
		}
	}
	missing := []int{}
	for i := 0; i < fb.k; i++ {
		if _, ok := have[i]; !ok {
			missing = append(missing, i)
		}
	}
	if len(missing) == 0 {
		fr.done = true
		return nil
	}
	if len(missing) > len(fr.syms) {
		if count {
			s.stats.Unrecover++
		}
		return nil
	}
	recs := recoverMany(fb.k, fb.m, missing, have, fr.syms, fb.symLen)
	if recs == nil {
		return nil
	}
	outs := make([][]byte, 0, len(missing))
	for _, mi := range missing {
		r := recs[mi]
		if r == nil {
			return nil
		}
		w := int(fb.lens[mi])
		if w > len(r) {
			return nil
		}
		r = r[:w]
		if crc32.ChecksumIEEE(r) != fb.crcs[mi] {
			s.stats.RecoverFail++
			fr.poisoned = true
			return nil
		}
		outs = append(outs, r)
	}
	return outs
}

func (s *decodeConn) tryLate() {
	now := time.Now()
	s.mu.Lock()
	defer s.mu.Unlock()
	s.expireLocked(now)
	for _, fr := range s.flights {
		if fr.done || fr.poisoned {
			continue
		}
		outs := s.tryRecoverLocked(fr, false)
		rec := s.settleRecovery(fr, outs)
		if rec == nil {
			continue
		}
		s.pending = append(s.pending,
			pendingPkt{data: rec, addr: fr.addr, acct: fr.acct})
		s.pendingBytes += int64(len(rec))
		s.stats.LateRecover++
	}
}

func (s *decodeConn) ReadFrom(b []byte) (int, net.Addr, error) {
again:
	s.mu.Lock()
	if len(s.pending) > 0 {
		p := s.pending[0]
		s.pending = s.pending[1:]
		s.pendingBytes -= int64(len(p.data))
		n := copy(b, p.data)
		s.stackLocked(p.acct, n)
		s.mu.Unlock()
		return n, p.addr, nil
	}
	s.mu.Unlock()

	n, addr, err := s.PacketConn.ReadFrom(b)
	if err != nil {
		return n, addr, err
	}
	s.countRx(n)
	var fb *fecBlock
	if s.mode != "off" {
		fb = parseFecBlock(b[:n])
	}
	hs := parseLongHdr(b[:n])
	isHandshake := hasHandshake(b[:n])
	var fbOut []byte
	s.mu.Lock()
	s.expireLocked(time.Now())
	s.stats.BytesIn += int64(n)
	if !hs.ok {
		s.stats.HdrShort++
	} else if hs.typ == 0 {
		s.stats.HdrInitial++
	} else if hs.typ == 2 {
		s.stats.HdrHandshake++
	}
	if isHandshake {
		s.stats.HdrCoalescedHS++
	}
	ca := s.acctLocked(addr, b[:n], false)
	if ca != nil {
		if ca.RxDgrams == 0 {
			ca.FirstRxNs = time.Now().UnixNano()
		}
		ca.RxDgrams++
		ca.RxBytes += int64(n)
		if fb != nil {
			ca.RxParity += int64(n)
			if !ca.FbSent {
				ca.RxParityN++
			}
		} else {
			ca.RxOrig += int64(n)
			if !ca.FbSent && hs.ok && hs.typ == 0 && !isHandshake {
				ca.RxOrigN++
			}
		}
		if !ca.FbSent && hs.ok && hs.typ == 0 && !isHandshake {
			crc := crc32.ChecksumIEEE(b[:n])
			if !inCRC(ca.RxCRC, crc) {
				if len(ca.RxCRC) < fbCRCCap {
					ca.RxCRC = append(ca.RxCRC, crc)
				} else {
					ca.RxCRCTruncated = true
				}
			}
		}
		if s.feedback && (isHandshake || fbEarly) && !ca.FbSent {
			ca.FbSent = true
			s.stats.FbSentN++
			fbOut = buildFeedback(hs.scid, hs.dcid, fbRec{
				flight: 0,
				k:      uint8(min8(ca.RxOrigN + ca.RecovN)),
				rxOrig: uint8(min8(ca.RxOrigN)),
				rxPar:  uint8(min8(ca.RxParityN)),
				recov:  uint8(min8(ca.RecovN)),
				crcs:   ca.RxCRC, truncated: ca.RxCRCTruncated,
			})
		}
	} else {
		s.stats.ConnAcctUnmappedRX++
	}
	s.mu.Unlock()
	if fbOut != nil {
		if _, werr := s.PacketConn.WriteTo(fbOut, addr); werr != nil {
			s.mu.Lock()
			s.stats.FbWriteErr++
			s.mu.Unlock()
		}
	}
	if s.mode == "off" {
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	if fb == nil {
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		s.noteOriginal(b[:n], addr)
		return n, addr, nil
	}

	dc := dcidOf(b[:n])
	s.mu.Lock()
	s.stats.Parities++
	if fb.m >= 2 && fb.index == 0 {
		s.stats.CreditParities++
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	key := fmt.Sprintf("%x|%d", dc, fb.flight)
	if s.flights == nil {
		s.flights = map[string]*flightRec{}
	}
	fr := s.flights[key]
	if fr == nil {
		fr = &flightRec{fb: fb, dcid: dc, addr: addr, acct: ca, created: time.Now(),
			syms: map[int][]byte{}}
		s.flights[key] = fr
	} else if !sameFecFlight(fr.fb, fb) {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	if fr.done || fr.poisoned {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	fr.syms[fb.index] = fb.sym
	outs := s.tryRecoverLocked(fr, true)
	if rec := s.settleRecovery(fr, outs); rec != nil {
		s.stackLocked(fr.acct, len(rec))
		s.mu.Unlock()
		m := copy(b, rec)
		return m, addr, nil
	}
	if len(outs) == 0 && s.pendingErasures(fr) >= 2 {
		fr.heldBytes += int64(n)
		s.heldBytes += int64(n)
		s.mu.Unlock()
		goto again
	}
	s.stackLocked(ca, n)
	s.mu.Unlock()
	return n, addr, nil
}

func (s *decodeConn) snapshot() serverStats {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.stats
}

func (s *decodeConn) report() interface{} {
	s.mu.Lock()
	defer s.mu.Unlock()
	conns := make(map[string]*connAcct, len(s.conns))
	for k, v := range s.conns {
		cp := *v
		cp.TxRxTimeline = append([]int64(nil), v.TxRxTimeline...)
		cp.TxSizes = append([]int(nil), v.TxSizes...)
		cp.TxNs = append([]int64(nil), v.TxNs...)
		cp.RxCRC = append([]uint32(nil), v.RxCRC...)
		conns[k] = &cp
	}
	return struct {
		serverStats
		ConnAcctScope string               `json:"conn_acct_scope"`
		Conns         map[string]*connAcct `json:"conns"`
	}{s.stats, "visible_handshake_cids_server_cid4_v1", conns}
}

func makeCert(padTo int) tls.Certificate {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		panic(err)
	}
	tmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "padfec-testbed"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:              []string{"padfec.test"},
		BasicConstraintsValid: true,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		panic(err)
	}
	if padTo > len(der) {
		need := padTo - len(der) - 16
		if need > 0 {
			filler := make([]byte, need)
			rand.Read(filler)
			tmpl.ExtraExtensions = []pkix.Extension{{
				Id:    asn1.ObjectIdentifier{1, 3, 6, 1, 4, 1, 99999, 1},
				Value: filler,
			}}
			der, err = x509.CreateCertificate(rand.Reader, tmpl, tmpl,
				&key.PublicKey, key)
			if err != nil {
				panic(err)
			}
		}
	}
	fmt.Fprintln(os.Stderr, "cert DER =", len(der), "bytes")
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
}

func curveFor(name string) tls.CurveID {
	switch name {
	case "x25519", "X25519":
		return tls.X25519
	case "secp256r1", "p256", "P256":
		return tls.CurveP256
	}
	return tls.X25519MLKEM768
}

func runServer(addr string, certSize int, mode string, statsPath string,
	feedback bool) {
	gfInit()
	ua, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, "resolve:", err)
		os.Exit(1)
	}
	udp, err := net.ListenUDP("udp", ua)
	if err != nil {
		fmt.Fprintln(os.Stderr, "listen:", err)
		os.Exit(1)
	}
	fc := &decodeConn{countConn: countConn{PacketConn: udp}, mode: mode,
		feedback: feedback,
		flights:  map[string]*flightRec{}}
	tr := &quic.Transport{Conn: fc, ConnectionIDLength: serverConnIDLength}
	tlsConf := &tls.Config{
		Certificates: []tls.Certificate{makeCert(certSize)},
		NextProtos:   []string{"padfec"},
		MinVersion:   tls.VersionTLS13,
		CurvePreferences: []tls.CurveID{
			tls.X25519MLKEM768, tls.X25519, tls.CurveP256,
		},
		SessionTicketsDisabled: true,
	}
	ln, err := tr.Listen(tlsConf, &quic.Config{
		MaxIdleTimeout:          30 * time.Second,
		KeepAlivePeriod:         0,
		DisablePathMTUDiscovery: true,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "quic listen:", err)
		os.Exit(1)
	}
	fmt.Fprintln(os.Stderr, "READY", addr)
	os.Stderr.Sync()

	var statsMu sync.Mutex
	writeStats := func() {
		if statsPath == "" {
			return
		}
		statsMu.Lock()
		defer statsMu.Unlock()
		b, err := json.Marshal(fc.report())
		if err != nil {
			return
		}
		tmp := statsPath + ".tmp"
		if err := os.WriteFile(tmp, b, 0644); err != nil {
			return
		}
		_ = os.Rename(tmp, statsPath)
	}
	if statsPath != "" {
		go func() {
			for {
				time.Sleep(100 * time.Millisecond)
				writeStats()
			}
		}()
		sig := make(chan os.Signal, 2)
		signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT)
		go func() {
			<-sig
			writeStats()
			os.Exit(0)
		}()
	}
	for {
		conn, err := ln.Accept(context.Background())
		if err != nil {
			continue
		}
		go func(c *quic.Conn) { <-c.Context().Done() }(conn)
	}
}

type trial struct {
	I             int     `json:"i"`
	Ms            float64 `json:"ms"`
	OK            bool    `json:"ok"`
	Group         string  `json:"group"`
	Err           string  `json:"err,omitempty"`
	KEM           uint16  `json:"kem_id"`
	CipherID      uint16  `json:"cipher_id"`
	Dgrams        int     `json:"initial_datagrams"`
	Parity        int     `json:"parity_sent"`
	FFDgrams      int     `json:"first_flight_datagrams"`
	FFBytes       int64   `json:"first_flight_bytes"`
	FFParity      int     `json:"first_flight_parity_dgrams"`
	FFParityBytes int64   `json:"first_flight_parity_bytes"`
	MUsed         int     `json:"m_used"`
	IPSUsed       int     `json:"ips_used"`
	IPSEff        int     `json:"ips_eff"`
	MWhy          string  `json:"m_why,omitempty"`
	SrvBytes      int64   `json:"server_bytes"`
	LossEvt       bool    `json:"loss_event"`
	PathRTTMS     float64 `json:"path_rtt_ms"`
	PathRTTValid  bool    `json:"path_rtt_valid"`
	PathRTTSource string  `json:"path_rtt_source"`
}

func measuredPathRTT(stats quic.ConnectionStats) (float64, bool) {
	if stats.MinRTT <= 0 || stats.LatestRTT <= 0 || stats.MeanDeviation <= 0 {
		return 0, false
	}
	return float64(stats.MinRTT) / float64(time.Millisecond), true
}

func runClient(addr, group string, n int, timeout, gap time.Duration,
	mode string, m int, ips int, parityDelayUs int, expectK int,
	statsPath string, dumpPath string,
	dropInitial map[int]bool, dropParity, corruptParity int,
	cachePath string, mMax, coldM, probeEvery int, uplinkMbps float64,
	feedback bool) {
	gfInit()
	ra, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, "resolve:", err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	var agg clientStats
	agg.FlightSizes = map[string]int{}

	cache := newDestCache(cachePath)
	wSize := ips
	if wSize <= 0 {
		wSize = 1280
	}
	defer cache.save()

	for i := 0; i < n; i++ {
		trialM, why := m, ""
		trialIPS := ips
		unbiased := true
		fmode := mode
		if mode == "off" {
			trialM = 0
		}
		if mode == "auto" {
			trialIPS, trialM, why, unbiased = cache.decide(addr, wSize,
				mMax, coldM, probeEvery, defaultAssumedBurst, cPktDefault,
				maxStepsDefault, quicgoMaxIPS, uplinkMbps)
			if trialM <= 0 {
				fmode = "off"
				trialM = 0
			} else {
				fmode = "fec"
			}
		}
		udp, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
		if err != nil {
			fmt.Fprintln(os.Stderr, "socket:", err)
			os.Exit(1)
		}
		fc := &fecConn{countConn: countConn{PacketConn: udp}, mode: fmode,
			m:           maxInt(trialM, 1),
			expectK:     expectK,
			dropInitial: dropInitial, dropParity: dropParity,
			corruptParity: corruptParity,
			dumpPath:      dumpPath,
			parityDelay:   time.Duration(parityDelayUs) * time.Microsecond}
		tr := &quic.Transport{Conn: fc}

		tlsConf := &tls.Config{
			InsecureSkipVerify:     true,
			NextProtos:             []string{"padfec"},
			MinVersion:             tls.VersionTLS13,
			CurvePreferences:       []tls.CurveID{curveFor(group)},
			ClientSessionCache:     nil,
			SessionTicketsDisabled: true,
		}
		qconf := &quic.Config{
			MaxIdleTimeout:          timeout,
			KeepAlivePeriod:         0,
			Allow0RTT:               false,
			DisablePathMTUDiscovery: true,
		}
		ipsEff := trialIPS
		if ipsEff > quicgoMaxIPS {
			ipsEff = quicgoMaxIPS
		}
		if trialIPS > 0 {
			qconf.InitialPacketSize = uint16(trialIPS)
		}
		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		start := time.Now()
		conn, err := tr.Dial(ctx, ra, tlsConf, qconf)
		el := time.Since(start)
		cancel()

		time.Sleep(3 * time.Duration(parityDelayUs) * time.Microsecond)
		if feedback && err == nil {
			fc.waitFeedback(200 * time.Millisecond)
		}
		st := fc.snapshot()
		_, _, _, srvBytes := fc.counts()
		hct := float64(el.Microseconds()) / 1000.0
		lossEvt := false
		if k0 := st.FirstFlightDgrams; k0 > 1 {
			if st.FlightSizes[fmt.Sprint(k0)] > 1 {
				lossEvt = true
			}
		} else if st.FirstFlightDgrams == 1 {
			lossEvt = st.InitialDgram > 2
		}
		t := trial{I: i, Ms: hct,
			OK: err == nil, Group: group,
			Dgrams: st.InitialDgram, Parity: st.ParitySent,
			FFDgrams: st.FirstFlightDgrams, FFBytes: st.FirstFlightBytes,
			FFParity:      st.FirstFlightParity,
			FFParityBytes: st.FirstFlightParityBytes,
			MUsed:         trialM, IPSUsed: trialIPS, IPSEff: ipsEff,
			MWhy: why, SrvBytes: srvBytes, LossEvt: lossEvt,
			PathRTTSource: "unavailable"}
		if err != nil {
			t.Err = err.Error()
		} else {
			cs := conn.ConnectionState().TLS
			t.CipherID = cs.CipherSuite
			t.KEM = uint16(cs.CurveID)
			t.PathRTTMS, t.PathRTTValid = measuredPathRTT(conn.ConnectionStats())
			if t.PathRTTValid {
				t.PathRTTSource = "quic_ack_min_rtt"
				if mode == "auto" {
					cache.observeRTT(addr, t.PathRTTMS)
				}
			}
			conn.CloseWithError(0, "done")
		}
		if err == nil && mode == "auto" {
			cache.observe(addr, st.FirstFlightDgrams, float64(srvBytes),
				hct, lossEvt, unbiased)
		}
		if feedback {
			nSent := st.FirstFlightDgrams + st.FirstFlightParity
			if r := fc.lastFeedback(); r != nil {
				o, p, _ := fc.matchFeedback(r)
				nRecv := o + p
				if !r.truncated && nSent > 0 && nRecv >= 0 && nRecv <= nSent {
					cache.observeSymbols(addr, nSent, nSent-nRecv, hct)
				}
			} else if base := cache.minHCT(addr); nSent > 0 &&
				(err != nil || (base > 0 && hct > 3*base)) {
				cache.observeSymbolsWhy(addr, nSent, nSent, hct, true)
			}
		}
		enc.Encode(&t)
		os.Stdout.Sync()

		agg.Flights += st.Flights
		agg.ParitySent += st.ParitySent
		agg.ParityFail += st.ParityFail
		agg.DroppedOrig += st.DroppedOrig
		agg.DroppedPar += st.DroppedPar
		agg.CorruptPar += st.CorruptPar
		agg.BytesOrig += st.BytesOrig
		agg.BytesParity += st.BytesParity
		agg.InitialDgram += st.InitialDgram
		agg.FbRecv += st.FbRecv
		agg.FbMagicSeen += st.FbMagicSeen
		agg.RxCalls += st.RxCalls
		agg.FbWaits += st.FbWaits
		if st.FbRecv > 0 {
			agg.FbRxOrig = st.FbRxOrig
			agg.FbRxPar = st.FbRxPar
			agg.FbRecov = st.FbRecov
			agg.FbRawOrig = st.FbRawOrig
			agg.FbRawPar = st.FbRawPar
			agg.FbTruncated = st.FbTruncated
		}
		agg.FbRxRetx += st.FbRxRetx
		agg.FirstFlightDgrams = st.FirstFlightDgrams
		agg.FirstFlightBytes = st.FirstFlightBytes
		agg.FirstFlightParity = st.FirstFlightParity
		agg.FirstFlightParityBytes = st.FirstFlightParityBytes
		for k, v := range st.FlightSizes {
			agg.FlightSizes[k] += v
		}
		tr.Close()
		udp.Close()
		if gap > 0 {
			time.Sleep(gap)
		}
	}
	if statsPath != "" {
		b, _ := json.Marshal(&agg)
		os.WriteFile(statsPath, b, 0644)
	}
	keys := make([]string, 0, len(agg.FlightSizes))
	for k := range agg.FlightSizes {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	fmt.Fprintln(os.Stderr, "DONE flights", agg.Flights, "parity", agg.ParitySent,
		"sizes", keys)
}

type scriptConn struct {
	net.PacketConn
	dgs  [][]byte
	i    int
	addr net.Addr
}

func (c *scriptConn) ReadFrom(b []byte) (int, net.Addr, error) {
	if c.i >= len(c.dgs) {
		return 0, nil, fmt.Errorf("대본 끝")
	}
	n := copy(b, c.dgs[c.i])
	c.i++
	return n, c.addr, nil
}

func selfTest() int {
	gfInit()
	fail := 0
	check := func(name string, ok bool) {
		if !ok {
			fail++
			fmt.Fprintln(os.Stderr, "FAIL", name)
		} else {
			fmt.Fprintln(os.Stderr, "ok  ", name)
		}
	}
	a := []byte{0x69}
	b := []byte{0xd6}
	p := rsEncode([][]byte{a, b}, 1, 1)[0]
	check("XOR 패리티가 문서 손계산(10111111)과 일치", p[0] == 0xbf)
	rec := recoverOne(2, 1, 0, 0, map[int][]byte{1: b}, p, 1)
	check("A 유실 복원", rec[0] == a[0])

	for _, m := range []int{1, 2, 3} {
		for k := 2; k <= 4; k++ {
			src := make([][]byte, k)
			for i := range src {
				src[i] = make([]byte, 1200)
				rand.Read(src[i])
			}
			pars := rsEncode(src, m, 1200)
			for miss := 0; miss < k; miss++ {
				have := map[int][]byte{}
				for i := range src {
					if i != miss {
						have[i] = src[i]
					}
				}
				for j, pp := range pars {
					got := recoverMany(k, m, []int{miss}, have,
						map[int][]byte{j: pp}, 1200)
					same := got != nil && got[miss] != nil &&
						string(got[miss]) == string(src[miss])
					check(fmt.Sprint("단일 소거 복원 m=", m, " k=", k,
						" miss=", miss, " 패리티", j), same)
				}
			}
		}
	}
	for _, m := range []int{1, 2, 3} {
		for k := 2; k <= 4; k++ {
			src := make([][]byte, k)
			for i := range src {
				src[i] = make([]byte, 1200)
				rand.Read(src[i])
			}
			pars := rsEncode(src, m, 1200)
			for e := 1; e <= k && e <= m; e++ {
				for _, miss := range combinations(k, e) {
					have := map[int][]byte{}
					for i := range src {
						if !inIntSlice(miss, i) {
							have[i] = src[i]
						}
					}
					give := map[int][]byte{}
					for j := 0; j < e; j++ {
						give[j] = pars[j]
					}
					got := recoverMany(k, m, miss, have, give, 1200)
					ok := got != nil
					for _, o := range miss {
						if ok && (got[o] == nil ||
							string(got[o]) != string(src[o])) {
							ok = false
						}
					}
					check(fmt.Sprint("다중 소거 복원 m=", m, " k=", k,
						" 소거", miss, " 패리티", e, "개"), ok)

					if e >= 2 {
						few := map[int][]byte{}
						for j := 0; j < e-1; j++ {
							few[j] = pars[j]
						}
						bad := recoverMany(k, m, miss, have, few, 1200)
						check(fmt.Sprint("[음성] 패리티 부족이면 nil m=", m,
							" k=", k, " 소거", miss, " 패리티", e-1, "개"),
							bad == nil)
					}

					if len(have) >= 1 {
						hole := map[int][]byte{}
						first := true
						for i, d := range have {
							if first {
								first = false
								continue
							}
							hole[i] = d
						}
						bad2 := recoverMany(k, m, miss, hole, give, 1200)
						check(fmt.Sprint("[음성] 원본이 모자라면 nil m=", m,
							" k=", k, " 소거", miss), bad2 == nil)
					}
				}
			}
		}
	}

	for _, kk := range []int{1, 2, 3} {
		for _, mm := range []int{1, 2} {
			dd := []byte{7, 7, 7, 7, 7, 7, 7, 7}
			sc := []byte{8, 8, 8, 8}
			src := make([][]byte, kk)
			for i := range src {
				d := make([]byte, 1200)
				rand.Read(d)
				d[0] = 0xc0
				d[1], d[2], d[3], d[4] = 0, 0, 0, 1
				d[5] = byte(len(dd))
				copy(d[6:], dd)
				d[6+len(dd)] = byte(len(sc))
				copy(d[7+len(dd):], sc)
				src[i] = d
			}
			crcs := make([]uint32, kk)
			lens := make([]uint16, kk)
			for i, d := range src {
				crcs[i] = crc32.ChecksumIEEE(d)
				lens[i] = uint16(len(d))
			}
			pars := rsEncode(src, mm, 1200)
			dg := make([][]byte, 0, kk+mm)
			dg = append(dg, src...)
			for j := 0; j < mm; j++ {
				dg = append(dg, buildParity(dd, sc, fecBlock{
					flight: 1, k: kk, m: mm, index: j, symLen: 1200,
					crcs: crcs, lens: lens, sym: pars[j]}))
			}
			for _, ord := range permutations(len(dg)) {
				sv := &decodeConn{mode: "fec"}
				bad := false
				buf := make([]byte, 2000)
				for _, ix := range ord {
					copy(buf, dg[ix])
					sv.feedOne(buf[:len(dg[ix])])
					sv.mu.Lock()
					over := sv.stats.BytesToStack+sv.pendingBytes >
						sv.stats.BytesIn
					sv.mu.Unlock()
					if over {
						bad = true
					}
				}
				if bad {
					check(fmt.Sprint("[회계] 스택<=수신 k=", kk, " m=", mm,
						" 순서", ord), false)
				}
			}
			check(fmt.Sprint("[회계] 스택<=수신, 도착순서 전수 k=", kk,
				" m=", mm), true)
		}
	}

	for _, kk := range []int{1, 2} {
		for _, mm := range []int{1, 2, 3} {
			dd := []byte{9, 9, 9, 9, 9, 9, 9, 9}
			sc := []byte{6, 6, 6, 6}
			src := make([][]byte, kk)
			for i := range src {
				d := make([]byte, 1200)
				rand.Read(d)
				d[0] = 0xc0
				d[1], d[2], d[3], d[4] = 0, 0, 0, 1
				d[5] = byte(len(dd))
				copy(d[6:], dd)
				d[6+len(dd)] = byte(len(sc))
				copy(d[7+len(dd):], sc)
				src[i] = d
			}
			crcs := make([]uint32, kk)
			lens := make([]uint16, kk)
			for i, d := range src {
				crcs[i] = crc32.ChecksumIEEE(d)
				lens[i] = uint16(len(d))
			}
			pars := rsEncode(src, mm, 1200)
			dg := make([][]byte, 0, kk+mm)
			dg = append(dg, src...)
			for j := 0; j < mm; j++ {
				dg = append(dg, buildParity(dd, sc, fecBlock{
					flight: 1, k: kk, m: mm, index: j, symLen: 1200,
					crcs: crcs, lens: lens, sym: pars[j]}))
			}
			ua := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 1), Port: 40000}
			badOver, badDup, badPre, badLedger := "", "", "", ""
			for _, ord := range permutations(len(dg)) {
				for drop := -1; drop < kk; drop++ {
					send := make([][]byte, 0, len(dg))
					for _, ix := range ord {
						if drop >= 0 && ix == drop {
							continue
						}
						send = append(send, dg[ix])
					}
					sv := &decodeConn{mode: "fec"}
					sv.PacketConn = &scriptConn{dgs: send, addr: ua}
					var handed int64
					buf := make([]byte, 2000)
					for {
						n, _, err := sv.ReadFrom(buf)
						if err != nil {
							break
						}
						handed += int64(n)
					}
					sv.mu.Lock()
					in := sv.stats.BytesIn
					ev := sv.stats.RecoverEvents
					pre := sv.stats.PrematureRecover
					stk := sv.stats.BytesToStack
					sv.mu.Unlock()
					if handed > in && badOver == "" {
						badOver = fmt.Sprint("순서", ord, " 소거", drop,
							" 인계 ", handed, " > 도착 ", in)
					}
					if handed != stk && badLedger == "" {
						badLedger = fmt.Sprint("순서", ord, " 소거", drop,
							" 인계 ", handed, " != 장부 ", stk)
					}
					if ev > 1 && badDup == "" {
						badDup = fmt.Sprint("순서", ord, " 소거", drop,
							" 복구사건 ", ev, " (비행 하나에 두 번 이상)")
					}
					inOrder := true
					for i := 1; i < len(ord); i++ {
						if ord[i] < ord[i-1] {
							inOrder = false
						}
					}
					if inOrder && pre > 0 && badPre == "" {
						badPre = fmt.Sprint("순서", ord, " 소거", drop,
							" 미리복구 ", pre, " (재정렬이 없는데)")
					}
				}
			}
			check(fmt.Sprint("[회계-ReadFrom] 인계<=도착, 도착순서x소거 전수 k=",
				kk, " m=", mm), badOver == "")
			if badOver != "" {
				fmt.Println("     ", badOver)
			}
			check(fmt.Sprint("[회계-장부] 인계 == BytesToStack k=", kk,
				" m=", mm), badLedger == "")
			if badLedger != "" {
				fmt.Println("     ", badLedger)
			}
			check(fmt.Sprint("[중복] 비행 하나에 복구 사건 <=1 k=", kk,
				" m=", mm), badDup == "")
			if badDup != "" {
				fmt.Println("     ", badDup)
			}
			check(fmt.Sprint("[미리복구] 재정렬 없으면 0 k=", kk,
				" m=", mm), badPre == "")
			if badPre != "" {
				fmt.Println("     ", badPre)
			}
		}
	}

	for _, mm := range []int{1, 2, 3} {
		kk := 2
		dd2 := []byte{7, 7, 7, 7, 7, 7, 7, 7}
		sc2 := []byte{8, 8, 8, 8}
		src := make([][]byte, kk)
		for i := range src {
			d := make([]byte, 1200)
			rand.Read(d)
			d[0] = 0xc0
			d[1], d[2], d[3], d[4] = 0, 0, 0, 1
			d[5] = byte(len(dd2))
			copy(d[6:], dd2)
			d[6+len(dd2)] = byte(len(sc2))
			copy(d[7+len(dd2):], sc2)
			src[i] = d
		}
		crcs := make([]uint32, kk)
		lens := make([]uint16, kk)
		for i, d := range src {
			crcs[i] = crc32.ChecksumIEEE(d)
			lens[i] = uint16(len(d))
		}
		pars := rsEncode(src, mm, 1200)
		sv := &decodeConn{mode: "fec"}
		for j := 0; j < mm; j++ {
			sv.feedOne(buildParity(dd2, sc2, fecBlock{
				flight: 1, k: kk, m: mm, index: j, symLen: 1200,
				crcs: crcs, lens: lens, sym: pars[j]}))
		}
		sv.mu.Lock()
		got := sv.stats.Recovered
		over := sv.stats.BytesToStack+sv.pendingBytes > sv.stats.BytesIn
		sv.mu.Unlock()
		want := 0
		if mm >= 3 {
			want = 2
		}
		check(fmt.Sprint("[통합] k=2 원본 둘 다 소거, m=", mm,
			" -> 복구 ", got, " (기대 ", want, ")"), got == want && !over)
	}

	dcid := []byte{1, 2, 3, 4, 5, 6, 7, 8}
	scid := []byte{9, 9, 9, 9}
	sym := make([]byte, 1200)
	rand.Read(sym)
	pkt := buildParity(dcid, scid, fecBlock{flight: 7, k: 2, m: 1, index: 0,
		symLen: 1200, crcs: []uint32{111, 222}, lens: []uint16{1200, 1200},
		sym: sym})
	fb := parseFecBlock(pkt)
	check("패리티 데이터그램 왕복", fb != nil && fb.k == 2 && fb.flight == 7 &&
		string(fb.sym) == string(sym) && fb.crcs[1] == 222)
	h := parseLongHdr(pkt)
	check("패리티가 롱헤더 Initial 로 파싱된다(서버가 연결에 귀속시킬 수 있음)",
		h.ok && h.typ == 0 && string(h.dcid) == string(dcid))
	check("패리티 데이터그램이 1200 B 이상(RFC 9000 14.1)", len(pkt) >= 1200)
	fakeInitial := append([]byte{0xC3, 0, 0, 0, 1, 8}, dcid...)
	fakeInitial = append(fakeInitial, 0)
	fakeInitial = append(fakeInitial, 0x00, 0x44, 0x00)
	fakeInitial = append(fakeInitial, make([]byte, 1200)...)
	check("정상 Initial 을 패리티로 오인하지 않는다", parseFecBlock(fakeInitial) == nil)
	return fail
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func parseIdx(v string) map[int]bool {
	out := map[int]bool{}
	if v == "" {
		return out
	}
	for _, part := range strings.Split(v, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if i, err := strconv.Atoi(part); err == nil {
			out[i] = true
		}
	}
	return out
}

func main() {
	mode := flag.String("mode", "client",
		"client | server | selftest | policygrid")
	addr := flag.String("addr", "127.0.0.1:44433", "address")
	group := flag.String("group", "X25519MLKEM768", "key exchange group")
	certSize := flag.Int("certsize", 2955, "target certificate DER size")
	n := flag.Int("n", 20, "handshakes")
	timeout := flag.Duration("timeout", 12*time.Second, "per-handshake timeout")
	gap := flag.Duration("gap", 25*time.Millisecond, "gap between handshakes")
	fec := flag.String("fec", "off",
		"off | buf | on | auto  (auto = 목적지 캐시로 m 을 스스로 고름)")
	cache := flag.String("cache", "",
		"폐루프 목적지 캐시 파일 (auto 모드에서 씀)")
	mMax := flag.Int("m-max", mMaxDefault,
		"auto 모드에서 고를 수 있는 최대 m (기본값은 확률표가 심는다)")
	coldM := flag.Int("cold-m", 0,
		"auto 모드 콜드스타트(기록 없는 목적지)에서 쓸 m")
	probeEvery := flag.Int("probe-every", 20,
		"auto 모드에서 몇 연결마다 무방비(m=0)로 가서 손실률을 재측정할지")
	uplink := flag.Float64("uplink-mbps", uplinkMbpsDefault,
		"업링크 대역 Mbps. 추가 바이트의 직렬화 시간을 J 에 청구한다. "+
			"0 이면 대역 제한 없음(직렬화 비용 0) - netem 에 rate 를 안 건 "+
			"이 테스트베드의 실제 조건이다")
	m := flag.Int("m", 1, "parity datagrams per flight")
	ips := flag.Int("ips", 0, "InitialPacketSize (0 = quic-go default)")
	pdelay := flag.Int("parity-delay-us", 300, "delay before emitting parity")
	expectK := flag.Int("expect-k", 0, "첫 비행의 데이터그램 수 (0 = 타이머만)")
	dump := flag.String("dump-flight", "", "첫 비행 원본 데이터그램을 이 파일에 기록")
	dropI := flag.String("drop-initial", "",
		"검증용: 첫 비행의 이 인덱스들(쉼표 구분) 원본을 보내지 않는다")
	dropP := flag.Int("drop-parity", -1,
		"검증용: N 번째 패리티를 보내지 않는다 (-1 = 안 함)")
	corrP := flag.Int("corrupt-parity", -1,
		"검증용: N 번째 패리티의 한 바이트를 뒤집는다 (-1 = 안 함)")
	stats := flag.String("stats", "", "write stats JSON here")
	feedback := flag.Bool("feedback", false,
		"C1: 서버가 첫 비행 수신 심볼 수를 회신한다(클라는 그것으로 손실 관측)")
	flag.Parse()

	fmode := "off"
	switch *fec {
	case "on", "fec":
		fmode = "fec"
	case "buf":
		fmode = "buf"
	case "auto":
		fmode = "auto"
	}
	switch *mode {
	case "selftest":
		os.Exit(selfTest())
	case "policygrid":
		policyGrid()
		return
	case "server":
		runServer(*addr, *certSize, fmode, *stats, *feedback)
	default:
		runClient(*addr, *group, *n, *timeout, *gap, fmode, *m, *ips,
			*pdelay, *expectK, *stats, *dump, parseIdx(*dropI),
			*dropP, *corrP, *cache, *mMax, *coldM, *probeEvery, *uplink,
			*feedback)
	}
}
