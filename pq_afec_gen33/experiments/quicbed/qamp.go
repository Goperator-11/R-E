package main

import (
	"container/list"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	padfechook "github.com/quic-go/quic-go/padfec-local-hook"
	"hash/crc32"
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
	if s.mode != "off" && fb == nil && fecMagicAtBody(b[:n]) {
		s.stats.FecParseFail++
	}
	ca := s.acctLocked(addr, b[:n], false)
	s.mu.Unlock()
	if fb == nil {
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		s.noteOriginal(b[:n], addr, ca)
		return
	}
	s.mu.Lock()
	if s.creditLocked(ca, fb, n) {
		s.mu.Unlock()
		return
	}
	dc := dcidOf(b[:n])
	key := fmt.Sprintf("%x|%d", dc, fb.flight)
	fr := s.legacyFlightLocked(key, dc, ca, addr, fb, time.Now())
	if fr == nil {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return
	}
	if fr.done || fr.poisoned || !s.addLegacySymbolLocked(fr, fb) {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return
	}
	outs := s.tryRecoverLocked(fr, true)
	if rec := s.settleRecovery(fr, outs); rec != nil {
		s.stackLocked(fr.acct, len(rec))
		s.mu.Unlock()
		return
	}
	if !fr.done && !fr.poisoned && len(outs) == 0 && s.pendingErasures(fr) >= 2 {
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
		found := s.lookupOriginalLocked(&s.recent, decoderGroup{fr.dcid, fr.acct}, fb.crcs[i], int(fb.lens[i])) != nil
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
	if s.stats.BytesToStack+s.pendingBytes+tot > s.stats.BytesIn || s.indexLocked().memory-fr.memory+s.pendingBytes+tot+decoderInputReserve > decoderPayloadCap {
		s.stats.RecoverRefused++
		return nil
	}
	fr.done = true
	s.recordRecoveredLocked(fr.acct, outs)
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
		s.queuePendingLocked(pendingPkt{data: extra, addr: fr.addr, acct: fr.acct, meta: fr.meta})
	}
	s.releaseFlightLocked(fr)
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

func fecMagicAtBody(d []byte) bool {
	h := parseLongHdr(d)
	i := h.bodyOff + 3
	return h.ok && h.typ == 0 && h.bodyOff < len(d) && d[h.bodyOff] == 0 &&
		i+fecMagicLen <= len(d) && string(d[i:i+fecMagicLen]) == string(fecMagic)
}

const fecVer = 1

const fecVerLead = 3

const serverFlightMin = 1200

type fecBlock struct {
	flight uint16
	k      int
	m      int
	index  int
	symLen int
	crcs   []uint32
	lens   []uint16
	sym    []byte
	ver    int
	lead   int
}

func isCreditParity(fb *fecBlock) bool {
	if fb.ver == fecVerLead {
		return fb.index < fb.lead
	}
	return fb.m >= 2 && fb.index == 0
}

func sameFecFlight(a, b *fecBlock) bool {
	if a == nil || b == nil || a.flight != b.flight || a.k != b.k || a.m != b.m || a.symLen != b.symLen ||
		a.ver != b.ver || a.lead != b.lead || len(a.crcs) != len(b.crcs) || len(a.lens) != len(b.lens) {
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
	ver, mb := byte(fecVer), byte(fb.m)
	if fb.ver == fecVerLead {
		ver, mb = byte(fecVerLead), byte(fb.lead<<4|fb.m)
	}
	body := make([]byte, 0, len(fb.sym)+64)
	body = append(body, fecMagic...)
	body = append(body, ver)
	body = binary.BigEndian.AppendUint16(body, fb.flight)
	body = append(body, byte(fb.k), mb, byte(fb.index))
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

const fbVer = 3
const fbCRCCap = 64

type fbRec struct {
	version            int
	recovered          []uint32
	recoveredTruncated bool
	flight             uint16
	k                  uint8
	rxOrig             uint8
	rxPar              uint8
	recov              uint8
	crcs               []uint32
	truncated          bool
}

const fbVerFrozen = 2

func checkFeedbackVersion(v int) error {
	if v != fbVerFrozen && v != fbVer {
		return fmt.Errorf("feedback-version must be %d or %d, got %d", fbVerFrozen, fbVer, v)
	}
	return nil
}

func buildFeedback(dcid, scid []byte, r fbRec) []byte {
	version := fbVer
	if r.version == fbVerFrozen {
		version = fbVerFrozen
	}
	body := make([]byte, 0, 16)
	body = append(body, fbMagic...)
	body = append(body, byte(version))
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

	if version == fbVer {
		recovered := r.recovered
		if len(recovered) > fbCRCCap {
			recovered = recovered[:fbCRCCap]
		}
		nrec := byte(len(recovered))
		if r.recoveredTruncated || len(r.recovered) > fbCRCCap {
			nrec |= 0x80
		}
		body = append(body, nrec)
		for _, cr := range recovered {
			body = binary.BigEndian.AppendUint32(body, cr)
		}
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
			if adv == 0 || tl > uint64(len(d)-i-j-adv) {
				return false
			}
			j += adv + int(tl)
		}
		if i+j >= len(d) {
			return false
		}
		plen, adv := readVarint(d[i+j:])
		if adv == 0 || plen == 0 || plen > uint64(len(d)-i-j-adv) {
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
	if i+blen != len(d) || blen < fecMagicLen+8 {
		return nil
	}
	b := d[i : i+blen]
	if string(b[:fecMagicLen]) != string(fbMagic) || (b[4] != 2 && b[4] != fbVer) {
		return nil
	}
	nc := int(b[11] & 0x7f)
	if nc > fbCRCCap || blen < 12+4*nc || (b[4] == 2 && blen != 12+4*nc) {
		return nil
	}
	r := &fbRec{
		version: int(b[4]),
		flight:  binary.BigEndian.Uint16(b[5:7]),
		k:       b[7], rxOrig: b[8], rxPar: b[9], recov: b[10],
		truncated: b[11]&0x80 != 0,
	}
	for x := 0; x < nc; x++ {
		j := 12 + 4*x
		r.crcs = append(r.crcs, binary.BigEndian.Uint32(b[j:j+4]))
	}
	if b[4] == fbVer {
		pos := 12 + 4*nc
		if pos >= blen {
			return nil
		}
		nr := int(b[pos] & 0x7f)
		if nr > fbCRCCap || blen != pos+1+4*nr {
			return nil
		}
		r.recoveredTruncated = b[pos]&0x80 != 0
		for x := 0; x < nr; x++ {
			j := pos + 1 + 4*x
			r.recovered = append(r.recovered, binary.BigEndian.Uint32(b[j:j+4]))
		}
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
	if string(b[:fecMagicLen]) != string(fecMagic) || (b[4] != fecVer && b[4] != fecVerLead) {
		return nil
	}
	j := 5
	fb := &fecBlock{ver: int(b[4])}
	fb.flight = binary.BigEndian.Uint16(b[j : j+2])
	j += 2
	fb.k = int(b[j])
	fb.m = int(b[j+1])
	fb.index = int(b[j+2])
	j += 3
	fb.symLen = int(binary.BigEndian.Uint16(b[j : j+2]))
	j += 2
	mMax := 8
	if fb.ver == fecVerLead {
		fb.lead = fb.m >> 4
		fb.m &= 0x0f
		mMax = 15
	} else if fb.m >= 2 {
		fb.lead = 1
	}
	if fb.k < 1 || fb.k > 32 || fb.m < 1 || fb.m > mMax || fb.lead > fb.m || fb.index >= fb.m || fb.symLen == 0 {
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
	ClientSCID                string            `json:"client_scid,omitempty"`
	ExtraSent                 extraSent         `json:"extra_sent"`
	RetransLayout             string            `json:"retrans_layout"`
	FlightTrace               flightTrace       `json:"flight_trace"`
	FlightExpectation         flightExpectation `json:"flight_expectation"`
	RxRejectedPeer            int               `json:"rx_rejected_peer"`
	RxRejectedCID             int               `json:"rx_rejected_cid"`
	FirstFlightNonInitialLong int               `json:"first_flight_non_initial_long"`
	Flights                   int               `json:"flights"`
	FlightSizes               map[string]int    `json:"flight_sizes"`
	ParitySent                int               `json:"parity_sent"`
	ParityFail                int               `json:"parity_fail"`
	DroppedOrig               int               `json:"dropped_originals"`
	DroppedPar                int               `json:"dropped_parities"`
	CorruptPar                int               `json:"corrupted_parities"`
	BytesOrig                 int64             `json:"bytes_orig"`
	BytesParity               int64             `json:"bytes_parity"`
	InitialDgram              int               `json:"initial_datagrams"`
	FbRecv                    int               `json:"fb_recv"`
	FbMagicSeen               int               `json:"fb_magic_seen"`
	RxCalls                   int               `json:"rx_calls"`
	FbWaits                   int               `json:"fb_waits"`
	FbRxOrig                  int               `json:"fb_rx_orig"`
	FbRxPar                   int               `json:"fb_rx_parity"`
	FbRxRetx                  int               `json:"fb_rx_retx"`
	FbRawOrig                 int               `json:"fb_raw_orig"`
	FbRawPar                  int               `json:"fb_raw_parity"`
	FbTruncated               bool              `json:"fb_truncated"`
	FbRecov                   int               `json:"fb_recovered"`
	FirstFlightDgrams         int               `json:"first_flight_datagrams"`
	FirstFlightBytes          int64             `json:"first_flight_bytes"`
	FirstFlightParity         int               `json:"first_flight_parity_dgrams"`
	FirstFlightParityBytes    int64             `json:"first_flight_parity_bytes"`
	Layout                    string            `json:"layout"`
	Lead                      int               `json:"lead"`
	FirstFlightLeadDgrams     int               `json:"first_flight_lead_dgrams"`
	LaterParitySent           int               `json:"later_parity_sent"`
}

type fecConn struct {
	revisitGuard    *revisitGuardObservation
	padJunk         bool
	dup             bool
	retransMode     string
	curShape        flightShape
	writeMu         sync.Mutex
	timerGeneration uint64
	traceEpoch      time.Time
	traceSequence   int
	flightFirst     time.Time
	flightLast      time.Time
	expectation     flightExpectation
	identityPeer    net.Addr
	ownCID          []byte
	ownCIDs         map[string]bool
	serverSeen      bool
	countConn
	observer      *memoryTrace
	mode          string
	m             int
	parityDelay   time.Duration
	expectK       int
	dropInitial   map[int]bool
	dropParity    int
	corruptParity int

	dumpPath string

	onFeedback   func(fbRec)
	fbLast       *fbRec
	fbCount      int
	ffOrigCRC    []uint32
	ffParCRC     []uint32
	ffSendFailed bool

	mu       sync.Mutex
	txWG     sync.WaitGroup
	txFinal  bool
	flight   [][]byte
	flightID uint16
	dcid     []byte
	scid     []byte
	peer     net.Addr
	timer    *time.Timer
	stats    clientStats

	layout   string
	lead     int
	srvBig   bool
	curLater bool
}

func (c *fecConn) v3() bool {
	return c.mode == "fec" && c.layout == "v3"
}

func (c *fecConn) layoutName() string {
	if c.layout == "" {
		return "v2"
	}
	return c.layout
}

func (c *fecConn) firstLead() int {
	if c.mode != "fec" {
		return 0
	}
	if c.layout == "v3" && c.lead >= 0 {
		return min(c.lead, c.m)
	}
	if c.m >= 2 {
		return 1
	}
	return 0
}

func (c *fecConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.writeMu.Lock()
	defer c.writeMu.Unlock()
	received := time.Now()
	h := parseLongHdr(b)
	c.mu.Lock()
	boundaryErr := c.checkFirstFlightLocked(b, addr, h)
	if boundaryErr == nil {
		boundaryErr = c.observeRevisitInitialLocked(b, h)
	}
	c.mu.Unlock()
	if boundaryErr != nil {
		return 0, boundaryErr
	}
	isInitial := h.ok && h.typ == 0
	if isInitial {
		c.mu.Lock()
		if c.txFinal {
			c.mu.Unlock()
			return 0, net.ErrClosed
		}
		c.txWG.Add(1)
		if c.traceEpoch.IsZero() {
			c.traceEpoch = received
		}
		c.stats.InitialDgram++
		c.stats.BytesOrig += int64(len(b))
		c.mu.Unlock()
		defer c.txWG.Done()
	}
	if !isInitial {
		c.flushFlightFor("non_initial", 0)
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
		c.flightFirst = received
		c.dcid = append([]byte(nil), h.dcid...)
		c.scid = append([]byte(nil), h.scid...)
		c.peer = addr
		c.curLater = c.v3() && c.srvBig
		c.curShape = c.flightShapeLocked()
	}
	if c.curLater {
		if c.stats.Flights == 0 && c.dropInitial[len(c.flight)] {
			c.stats.DroppedOrig++
		} else if _, err := c.PacketConn.WriteTo(b, addr); err != nil {
			c.mu.Unlock()
			return 0, err
		} else {
			c.countTx(len(b))
		}
	}
	c.flight = append(c.flight, cp)
	c.flightLast = received
	ready := c.expectationReadyLocked()
	if c.timer != nil {
		c.timer.Stop()
	}
	c.timerGeneration++
	generation := c.timerGeneration
	if !ready {
		c.timer = time.AfterFunc(c.parityDelay, func() { c.flushFlightFor("timer", generation) })
	} else {
		c.timer = nil
	}
	c.mu.Unlock()
	if ready {
		c.flushFlightFor("expected_k", generation)
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
		c.mu.Lock()
		accepted := c.acceptServerLocked(b[:n], addr)
		if accepted && parseFeedback(b[:n]) == nil {
			c.serverSeen = true
		}
		c.mu.Unlock()
		if !accepted {
			continue
		}
		c.observer.datagram(b[:n], parseFeedback(b[:n]) != nil)
		if parseFeedback(b[:n]) == nil {
			c.countRx(n)
			if n >= serverFlightMin {
				c.mu.Lock()
				c.srvBig = true
				c.mu.Unlock()
			}
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

func (c *fecConn) flushFlight() { c.flushFlightFor("manual", 0) }

func (c *fecConn) flushFlightFor(reason string, generation uint64) {
	c.mu.Lock()
	if c.txFinal {
		c.mu.Unlock()
		return
	}
	if generation != 0 && generation != c.timerGeneration {
		c.stats.FlightTrace.StaleTriggers++
		c.mu.Unlock()
		return
	}
	c.timerGeneration++
	fl := c.flight
	dcid := c.dcid
	scid := c.scid
	peer := c.peer
	fid := c.flightID
	later := c.curLater
	shape := c.curShape
	c.flight = nil
	if c.timer != nil {
		c.timer.Stop()
		c.timer = nil
	}
	if len(fl) == 0 || peer == nil {
		c.mu.Unlock()
		return
	}
	c.txWG.Add(1)
	defer c.txWG.Done()
	traceIndex := c.traceFlightLocked(reason, fl, time.Now(), true)
	sent, failures := 0, 0
	var sentBytes int64
	paritySent := 0
	extras := extraSent{Kind: c.extraKind()}
	var parityBytes int64
	defer func() { c.finishFlightTrace(traceIndex, sent, failures, sentBytes, paritySent, parityBytes, extras) }()

	k := len(fl)
	size := 0
	for _, d := range fl {
		if len(d) > size {
			size = len(d)
		}
	}

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
			sent++
			sentBytes += int64(len(d))
			c.countTx(len(d))
		} else {
			failures++
		}
		if err != nil && isFirstFlight {
			c.mu.Lock()
			c.ffSendFailed = true
			c.mu.Unlock()
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
	full := c.firstLead()
	lead := full
	if later {
		lead = 0
	}
	flightM := c.m
	if c.v3() {
		lead = shape.Lead
		flightM = shape.Lead + shape.Trail
	}

	mk := func(j int, par []byte) []byte {
		return buildParity(dcid, scid, fecBlock{
			flight: fid, k: k, m: c.m, index: j,
			symLen: size, crcs: crcs, lens: lens, sym: par,
		})
	}
	emit := func(j int, pkt []byte) {
		budget := len(pkt)
		pkt = comparisonPacket(extras.Kind, j, pkt, fl)
		if isFirstFlight && c.dropParity == j {
			c.mu.Lock()
			if extras.Kind == "parity" {
				c.ffParCRC = append(c.ffParCRC, crc32.ChecksumIEEE(pkt))
			}
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
		extra := extraSent{Kind: extras.Kind}
		if err == nil {
			extra.Sent = 1
			extra.Bytes = int64(len(pkt))
			extra.ParityBudgetBytes = int64(budget)
			if isFirstFlight {
				extra.FirstSent = 1
				extra.FirstBytes = extra.Bytes
				extra.FirstParityBudgetBytes = extra.ParityBudgetBytes
				if j < lead {
					extra.FirstLead = 1
				}
			}
		} else {
			extra.Errors = 1
		}
		extras.add(extra)
		c.mu.Lock()
		c.stats.ExtraSent.add(extra)
		if extras.Kind != "parity" {
			c.mu.Unlock()
			return
		}
		if isFirstFlight {
			c.ffParCRC = append(c.ffParCRC, crc32.ChecksumIEEE(pkt))
		}
		if err == nil {
			paritySent++
			parityBytes += int64(len(pkt))
			c.stats.ParitySent++
			c.stats.BytesParity += int64(len(pkt))
			if isFirstFlight {
				c.stats.FirstFlightParity++
				c.stats.FirstFlightParityBytes += int64(len(pkt))
				if j < lead {
					c.stats.FirstFlightLeadDgrams++
				}
			} else {
				c.stats.LaterParitySent++
			}
		} else {
			c.stats.ParityFail++
		}
		c.mu.Unlock()
	}

	if c.v3() {
		mk3 := func(j, m, ld int, par []byte) []byte {
			return buildParity(dcid, scid, fecBlock{ver: fecVerLead,
				flight: fid, k: k, m: m, lead: ld, index: j,
				symLen: size, crcs: crcs, lens: lens, sym: par})
		}
		if later {
			if flightM >= 1 {
				emit(0, mk3(0, 1, 0, rsEncode(padded, 1, size)[0]))
			}
			return
		}
		pars := rsEncode(padded, flightM, size)
		for j := 0; j < lead; j++ {
			emit(j, mk3(j, flightM, lead, pars[j]))
		}
		for i := 0; i < k; i++ {
			sendOrig(i, fl[i])
		}
		for j := lead; j < flightM; j++ {
			emit(j, mk3(j, flightM, lead, pars[j]))
		}
		return
	}
	pars := rsEncode(padded, c.m, size)

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

func (c *fecConn) finalSendStats() clientStats {
	c.mu.Lock()
	c.txFinal = true
	c.mu.Unlock()

	c.txWG.Wait()

	c.mu.Lock()
	if c.timer != nil {
		c.timer.Stop()
		c.timer = nil
	}
	if len(c.flight) > 0 {
		c.traceFlightLocked("final_discard", c.flight, time.Now(), false)
	}
	c.flight = nil
	c.timerGeneration++
	c.mu.Unlock()

	return c.snapshot()
}

func (c *fecConn) snapshot() clientStats {
	c.mu.Lock()
	defer c.mu.Unlock()
	s := c.stats
	s.ClientSCID = fmt.Sprintf("%x", c.ownCID)
	s.FlightTrace = s.FlightTrace.clone()
	fs := map[string]int{}
	for k, v := range s.FlightSizes {
		fs[k] = v
	}
	s.FlightSizes = fs
	s.ExtraSent.Kind = c.extraKind()
	s.FlightExpectation = c.expectation
	s.RetransLayout = c.retransLayout()
	s.Layout = c.layoutName()
	s.Lead = c.firstLead()
	return s
}

type serverStats struct {
	TokenContexts             int   `json:"token_contexts"`
	AddressVerifiedContexts   int   `json:"address_verified_contexts"`
	SourceVerifyCalls         int   `json:"source_verify_calls"`
	SourceVerifyEnabled       bool  `json:"source_verify_enabled"`
	SessionTicketsEnabled     bool  `json:"session_tickets_enabled"`
	TLSAccepted               int   `json:"tls_accepted"`
	TLSResumed                int   `json:"tls_resumed"`
	UDPReadMsg                int   `json:"udp_read_msg"`
	UDPReadBatch              int   `json:"udp_read_batch"`
	UDPWriteMsg               int   `json:"udp_write_msg"`
	UDPWriteErrors            int   `json:"udp_write_errors"`
	UDPGSOCalls               int   `json:"udp_gso_calls"`
	UDPGSOSegments            int   `json:"udp_gso_segments"`
	DecoderEvictedSource      int   `json:"decoder_evicted_source"`
	DecoderFlightCap          int   `json:"decoder_flight_cap"`
	DecoderPayloadCap         int   `json:"decoder_payload_cap"`
	DecoderDuplicate          int   `json:"decoder_duplicate"`
	DecoderOriginalIgnored    int   `json:"decoder_original_ignored"`
	DecoderRecentEvicted      int   `json:"decoder_recent_evicted"`
	DecoderRecentLookups      int64 `json:"decoder_recent_lookups"`
	DecoderFlightVisits       int64 `json:"decoder_flight_visits"`
	DecoderExpiryEvents       int64 `json:"decoder_expiry_events"`
	ConnAcctCompleted         int   `json:"conn_acct_completed"`
	ConnAcctTraceUnmapped     int   `json:"conn_acct_trace_unmapped"`
	ConnAcctExpired           int   `json:"conn_acct_expired"`
	ConnAcctEvictedLRU        int   `json:"conn_acct_evicted_lru"`
	FirstFlightNonInitialLong int   `json:"first_flight_non_initial_long"`
	Originals                 int   `json:"originals"`
	Parities                  int   `json:"parities"`
	FecParseFail              int   `json:"fec_parse_fail"`
	FecOversizeRead           int   `json:"fec_oversize_read,omitempty"`
	Recovered                 int   `json:"recovered"`
	RecoverEvents             int   `json:"recover_events"`
	PrematureRecover          int   `json:"premature_recovered"`
	RecoverFail               int   `json:"recover_crc_fail"`
	LateRecover               int   `json:"late_recovered"`
	RecoverRefused            int   `json:"recover_refused_by_accounting"`
	CreditParities            int   `json:"credit_parities"`
	CreditParitiesV3          int   `json:"credit_parities_v3"`
	Unrecover                 int   `json:"unrecoverable_seen"`
	UnrecoverFinal            int   `json:"unrecoverable_final"`
	FlightsFinalized          int   `json:"flights_finalized"`
	FlightsPending            int   `json:"flights_pending"`
	BytesIn                   int64 `json:"bytes_in"`
	BytesToStack              int64 `json:"bytes_to_stack"`
	HoldDiscardBytes          int64 `json:"hold_discard_bytes"`
	HoldExpiredBytes          int64 `json:"hold_expired_bytes"`
	HoldCapBytes              int64 `json:"hold_cap_bytes"`
	HoldMetadataBytes         int64 `json:"hold_metadata_bytes"`
	HoldDuplicateBytes        int64 `json:"hold_duplicate_bytes"`
	HoldTruncatedBytes        int64 `json:"hold_truncated_bytes"`
	HoldUnsupported           int   `json:"hold_unsupported"`
	ConnAcctDropped           int   `json:"conn_acct_dropped"`
	ConnAcctUnmappedRX        int   `json:"conn_acct_unmapped_rx"`
	ConnAcctUnmappedTX        int   `json:"conn_acct_unmapped_tx"`
	ConnAcctUnmappedStack     int64 `json:"conn_acct_unmapped_stack_bytes"`
	ConnAcctAliasConflicts    int   `json:"conn_acct_alias_conflicts"`
	ConnAcctAliasDropped      int   `json:"conn_acct_alias_dropped"`
	HdrInitial                int   `json:"hdr_initial"`
	HdrHandshake              int   `json:"hdr_handshake"`
	HdrShort                  int   `json:"hdr_short"`
	FbSentN                   int   `json:"fb_sent"`
	FbWriteErr                int   `json:"fb_write_err"`
	HdrCoalescedHS            int   `json:"hdr_coalesced_hs"`
}

type flightRec struct {
	meta      packetMeta
	key       string
	age       *list.Element
	memory    int64
	seenCRC   map[uint32]bool
	finalized bool
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
	meta      packetMeta
	data      []byte
	addr      net.Addr
	acct      *connAcct
	creditVer int
}

type connAcct struct {
	AddressValidationObserved bool `json:"address_validation_observed"`
	AddressVerifiedAtStart    bool `json:"address_verified_at_start"`
	TLSObserved               bool `json:"tls_observed"`
	TLSDidResume              bool `json:"tls_did_resume"`
	life                      *accountLife
	logged                    bool
	HandshakeCompleteNS       int64  `json:"handshake_complete_ns"`
	ClosedNS                  int64  `json:"closed_ns"`
	InitialDCID               string `json:"initial_dcid"`
	ClientSCID                string `json:"client_scid"`
	FirstPeer                 string `json:"first_peer"`
	LastPeer                  string `json:"last_peer"`
	PeerChanges               int    `json:"peer_changes"`
	aliasCount                int
	FirstRxNs                 int64    `json:"first_rx_ns"`
	FirstTxNs                 int64    `json:"first_tx_ns"`
	RxDgrams                  int      `json:"rx_dgrams"`
	RxBytes                   int64    `json:"rx_bytes"`
	RxOrig                    int64    `json:"rx_orig_bytes"`
	RxParity                  int64    `json:"rx_parity_bytes"`
	RxOrigN                   int      `json:"rx_orig_n"`
	RxParityN                 int      `json:"rx_parity_n"`
	RxCRC                     []uint32 `json:"rx_crc"`
	RxCRCTruncated            bool     `json:"rx_crc_truncated"`
	RecoveredCRC              []uint32 `json:"recovered_crc"`
	RecoveredCRCTruncated     bool     `json:"recovered_crc_truncated"`
	RecovN                    int      `json:"recov_n"`
	CreditN                   int      `json:"credit_n"`
	FbSent                    bool     `json:"fb_sent"`
	Stack                     int64    `json:"stack_bytes"`
	TxDgrams                  int      `json:"tx_dgrams"`
	TxBytes                   int64    `json:"tx_bytes"`
	BeffStack                 int64    `json:"beff_stack"`
	BeffPhys                  int64    `json:"beff_phys"`
	BeffOrig                  int64    `json:"beff_orig"`
	BeffParity                int64    `json:"beff_parity"`
	BeffCredit                int      `json:"beff_credit"`
	TxRxTimeline              []int64  `json:"tx_rx_timeline"`
	TxSizes                   []int    `json:"tx_sizes"`
	TxNs                      []int64  `json:"tx_ns"`
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
	readMu   sync.Mutex
	writeMu  sync.Mutex
	udp      udpMessageConn
	readMeta packetMeta
	wideRead bool
	wideBuf  []byte
	closed   bool
	accounts *accountBook
	countConn
	certMeta *certificateMetadata
	hold     *holdState
	mode     string
	feedback bool

	feedbackVersion int
	profile         string
	connLog         *connLogger

	mu            sync.Mutex
	recent        originalIndex
	decoder       *legacyIndex
	pendingByAcct map[*connAcct]int64
	flights       map[string]*flightRec
	pending       []pendingPkt
	pendingBytes  int64
	heldBytes     int64
	conns         map[string]*connAcct
	clientCIDs    map[string]*connAcct
	serverCIDs    map[string]*connAcct
	stats         serverStats

	connLogPending []connLogEntry
}

const connAliasCap = 16

const serverConnIDLength = 4

func (s *decodeConn) bindCIDLocked(client bool, cid []byte, ca *connAcct) {
	if len(cid) == 0 || len(cid) > 20 || ca == nil || ca.life == nil || ca.life.evicted {
		return
	}
	index := s.serverCIDs
	if client {
		index = s.clientCIDs
	}
	key := string(cid)
	alias := accountAlias{client, key}
	for _, known := range ca.life.aliases {
		if known == alias {
			return
		}
	}
	if ca.aliasCount >= connAliasCap {
		s.stats.ConnAcctAliasDropped++
		return
	}
	ca.life.aliases = append(ca.life.aliases, alias)
	s.accountBookLocked().refs[alias]++
	ca.aliasCount++
	if old, exists := index[key]; exists {
		if old != ca && old != nil {
			index[key] = nil
			s.stats.ConnAcctAliasConflicts++
		}
		return
	}
	index[key] = ca
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
	if s.closed {
		return nil
	}
	s.expireAccountsLocked(time.Now())
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
				s.bindCIDLocked(false, h.scid, ca)
			}
		} else {
			if h.typ == 0 && len(h.scid) > 0 && len(h.dcid) > 0 && len(h.dcid) != serverConnIDLength {
				key := fmt.Sprintf("initial:%x/%x", h.dcid, h.scid)
				ca = s.conns[key]
				if ca == nil {
					if len(s.conns) >= connAcctCap {
						oldest := s.accountBookLocked().lru.Front()
						if oldest == nil {
							s.stats.ConnAcctDropped++
							return nil
						}
						s.evictAccountLocked(oldest.Value.(*connAcct), true)
					}
					if s.conns == nil {
						s.conns = map[string]*connAcct{}
					}
					ca = &connAcct{InitialDCID: fmt.Sprintf("%x", h.dcid), ClientSCID: fmt.Sprintf("%x", h.scid)}
					s.conns[key] = ca
					s.registerAccountLocked(key, ca)
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
				s.bindCIDLocked(true, h.scid, ca)
				s.bindCIDLocked(false, h.dcid, ca)
			}
		}
	}
	if ca != nil && ca.life != nil && ca.life.lru != nil {
		s.accountBookLocked().lru.MoveToBack(ca.life.lru)
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

func (s *decodeConn) creditLocked(ca *connAcct, fb *fecBlock, n int) bool {
	if !isCreditParity(fb) {
		return false
	}
	s.stats.CreditParities++
	if fb.ver == fecVerLead {
		s.stats.CreditParitiesV3++
	}
	if ca != nil {
		ca.CreditN++
	}
	s.stackLocked(ca, n)
	return true
}

func (s *decodeConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	return s.serverWrite(b, addr, 0, func() (int, error) { return s.PacketConn.WriteTo(b, addr) })
}

func dcidOf(d []byte) string {
	h := parseLongHdr(d)
	if !h.ok {
		return ""
	}
	return string(h.dcid)
}

func (s *decodeConn) expireLocked(now time.Time) {
	s.expireIndexLocked(now)
}

func (s *decodeConn) noteOriginal(data []byte, addr net.Addr, accounts ...*connAcct) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stats.Originals++
	if s.closed {
		return
	}
	if !decoderOriginal(data) {
		s.stats.DecoderOriginalIgnored++
		return
	}
	now := time.Now()
	s.expireLocked(now)
	var ca *connAcct
	if len(accounts) > 0 {
		ca = accounts[0]
	}
	dc := dcidOf(data)
	group := decoderGroup{dc, ca}
	cr := crc32.ChecksumIEEE(data)
	s.stats.DecoderRecentEvicted += s.recent.add(group, data, now)
	premature := false
	for _, fr := range s.indexLocked().groups[group] {
		s.stats.DecoderFlightVisits++
		if fr.fb != nil && inCRC(fr.fb.crcs, cr) {
			if fr.seenCRC == nil {
				fr.seenCRC = map[uint32]bool{}
			}
			fr.seenCRC[cr] = true
		}
		if fr.recCRC[cr] {
			premature = true
		}
	}
	if premature {
		s.stats.PrematureRecover++
	}
	s.tryLateLocked(group)
}

func (s *decodeConn) tryRecoverLocked(fr *flightRec, count bool) [][]byte {
	fb := fr.fb
	have := map[int][]byte{}
	for i, c := range fb.crcs {
		data := s.lookupOriginalLocked(&s.recent, decoderGroup{fr.dcid, fr.acct}, c, int(fb.lens[i]))
		if data != nil {
			q := make([]byte, fb.symLen)
			copy(q, data)
			have[i] = q
			if fr.seenCRC == nil {
				fr.seenCRC = map[uint32]bool{}
			}
			fr.seenCRC[c] = true
		} else if fr.seenCRC[c] {
			s.stats.DecoderEvictedSource++
			fr.poisoned = true
			s.releaseFlightLocked(fr)
			return nil
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
		s.releaseFlightLocked(fr)
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
			s.releaseFlightLocked(fr)
			return nil
		}
		outs = append(outs, r)
	}
	return outs
}

func (s *decodeConn) tryLateLocked(group decoderGroup) {
	for _, fr := range s.indexLocked().groups[group] {
		s.stats.DecoderFlightVisits++
		if fr.done || fr.poisoned || fr.fb == nil {
			continue
		}
		outs := s.tryRecoverLocked(fr, false)
		rec := s.settleRecovery(fr, outs)
		if rec == nil {
			continue
		}
		s.queuePendingLocked(pendingPkt{data: rec, addr: fr.addr, acct: fr.acct, meta: fr.meta})
		s.stats.LateRecover++
	}
}

func (s *decodeConn) ReadFrom(b []byte) (int, net.Addr, error) {
	s.readMu.Lock()
	defer s.readMu.Unlock()
	return s.readFrom(b)
}

func (s *decodeConn) readFrom(b []byte) (int, net.Addr, error) {
	s.readMeta = packetMeta{}
again:
	s.mu.Lock()
	if s.closed {
		s.mu.Unlock()
		return 0, nil, net.ErrClosed
	}
	if s.hold != nil {
		now := s.hold.now()
		s.holdTickLocked(now)
		if s.hold.closed {
			s.mu.Unlock()
			return 0, nil, net.ErrClosed
		}
		if !s.hold.externalDeadline.IsZero() && !now.Before(s.hold.externalDeadline) {
			s.mu.Unlock()
			return 0, nil, os.ErrDeadlineExceeded
		}
	}
	if len(s.pending) > 0 {
		p := s.pending[0]
		s.pending[0] = pendingPkt{}
		s.pending = s.pending[1:]
		if len(s.pending) == 0 {
			s.pending = nil
		}
		s.pendingBytes -= int64(len(p.data))
		if s.pendingByAcct != nil {
			s.pendingByAcct[p.acct] -= int64(len(p.data))
			if s.pendingByAcct[p.acct] <= 0 {
				delete(s.pendingByAcct, p.acct)
			}
		}
		n := copy(b, p.data)
		s.readMeta = p.meta.truncated(n < len(p.data))
		s.stackLocked(p.acct, n)
		if p.creditVer != 0 {
			s.stats.CreditParities++
			if p.creditVer == fecVerLead {
				s.stats.CreditParitiesV3++
			}
			if p.acct != nil {
				p.acct.CreditN++
			}
		}
		if s.hold != nil {
			s.stats.HoldTruncatedBytes += int64(len(p.data) - n)
		}
		fbOut := s.feedbackLocked(b[:n], p.acct)
		s.mu.Unlock()
		s.writeFeedback(fbOut, p.addr, s.readMeta)
		return n, p.addr, nil
	}
	if s.hold != nil {
		if err := s.holdReadDeadlineLocked(); err != nil {
			s.mu.Unlock()
			return 0, nil, err
		}
	}
	s.mu.Unlock()

	wire := b
	wide := s.wideRead && s.mode != "off" && len(b) < udpMaxPayload
	if wide {
		if s.wideBuf == nil {
			s.wideBuf = make([]byte, udpMaxPayload)
		}
		wire = s.wideBuf
	}
	wireN, addr, err := s.readWire(wire)
	if err != nil {
		if ne, ok := err.(net.Error); s.hold != nil && ok && ne.Timeout() {
			s.mu.Lock()
			now := s.hold.now()
			s.holdTickLocked(now)
			external := !s.hold.externalDeadline.IsZero() && !now.Before(s.hold.externalDeadline)
			s.mu.Unlock()
			if !external {
				goto again
			}
		}
		if wide && wireN > 0 {
			wireN = copy(b, wire[:min(wireN, len(wire))])
		}
		return wireN, addr, err
	}
	n := copy(b, wire[:wireN])
	if wireN > n {
		s.readMeta = s.readMeta.truncated(true)
	}
	s.countRx(n)
	s.mu.Lock()
	if s.closed {
		s.stats.BytesIn += int64(n)
		if s.hold != nil {
			s.stats.HoldDiscardBytes += int64(n)
		}
		s.mu.Unlock()
		return 0, nil, net.ErrClosed
	}
	s.mu.Unlock()
	var fb *fecBlock
	if s.mode != "off" {
		fb = parseFecBlock(wire[:wireN])
	}
	hs := parseLongHdr(b[:n])
	isHandshake := hasHandshake(b[:n])
	var fbOut []byte
	s.mu.Lock()
	s.expireLocked(time.Now())
	s.stats.BytesIn += int64(n)
	if s.mode != "off" && fb == nil && fecMagicAtBody(wire[:wireN]) {
		s.stats.FecParseFail++
	}
	if wireN > n {
		s.stats.FecOversizeRead++
	}
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
	if hs.ok && (hs.typ != 0 || isHandshake) && (ca == nil || ca.FirstTxNs == 0) {
		s.stats.FirstFlightNonInitialLong++
	}
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
			crc := crc32.ChecksumIEEE(wire[:wireN])
			if !inCRC(ca.RxCRC, crc) {
				if len(ca.RxCRC) < fbCRCCap {
					ca.RxCRC = append(ca.RxCRC, crc)
				} else {
					ca.RxCRCTruncated = true
				}
			}
		}
		fbOut = s.feedbackLocked(b[:n], ca)
	} else {
		s.stats.ConnAcctUnmappedRX++
	}
	s.mu.Unlock()
	s.writeFeedback(fbOut, addr, s.readMeta)
	if s.mode == "off" {
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	if s.hold != nil {
		s.mu.Lock()
		s.holdReceiveLocked(b[:n], wireN, fb, addr, ca, s.hold.now(), s.readMeta)
		s.mu.Unlock()
		goto again
	}
	if fb == nil {
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		s.noteOriginal(b[:n], addr, ca)
		return n, addr, nil
	}

	dc := dcidOf(b[:n])
	s.mu.Lock()
	s.stats.Parities++
	if s.creditLocked(ca, fb, n) {
		s.mu.Unlock()
		return n, addr, nil
	}
	key := fmt.Sprintf("%x|%d", dc, fb.flight)
	fr := s.legacyFlightLocked(key, dc, ca, addr, fb, time.Now(), s.readMeta)
	if fr == nil {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	if fr.done || fr.poisoned || !s.addLegacySymbolLocked(fr, fb) {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	outs := s.tryRecoverLocked(fr, true)
	if rec := s.settleRecovery(fr, outs); rec != nil {
		m := copy(b, rec)
		s.readMeta = fr.meta.truncated(m < len(rec))
		s.stackLocked(fr.acct, m)
		fbOut := s.feedbackLocked(b[:m], fr.acct)
		s.mu.Unlock()
		s.writeFeedback(fbOut, addr, s.readMeta)
		return m, addr, nil
	}
	if !fr.done && !fr.poisoned && len(outs) == 0 && s.pendingErasures(fr) >= 2 {
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
	return s.observationStatsLocked(time.Now())
}

func (s *decodeConn) report(includeConns ...bool) interface{} {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.expireAccountsLocked(time.Now())
	conns := make(map[string]*connAcct)
	if len(includeConns) == 0 || includeConns[0] {
		for k, v := range s.conns {
			conns[k] = v.clone()
		}
	}
	warnings := []string{}
	if s.stats.ConnAcctDropped > 0 {
		warnings = append(warnings, "conn_acct_dropped")
	}
	feedbackVersion := fbVer
	if s.feedbackVersion == fbVerFrozen {
		feedbackVersion = fbVerFrozen
	}
	return struct {
		serverStats
		UDPPath         string               `json:"udp_path"`
		Profile         string               `json:"profile"`
		FeedbackVersion int                  `json:"feedback_version"`
		Warnings        []string             `json:"warnings"`
		ConnAcctLive    int                  `json:"conn_acct_live"`
		ConnAcctScope   string               `json:"conn_acct_scope"`
		Conns           map[string]*connAcct `json:"conns"`
		ConnLog         map[string]any       `json:"conn_log,omitempty"`
		LeadHold        map[string]any       `json:"lead_hold"`
		Certificate     *certificateMetadata `json:"certificate,omitempty"`
	}{s.observationStatsLocked(time.Now()), s.udpPath(), profileName(s.profile), feedbackVersion, warnings, len(s.conns), "visible_handshake_cids_server_cid4_v2_lru", conns, s.connLogReportLocked(), s.holdReportLocked(), s.certMeta}
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

func runServer(addr string, certSize int, certFile string, mode string, statsPath string,
	feedback bool, hold *holdConfig, udpPath string, resume, verifySource bool, feedbackVersion int, connLogPath, profile string) {
	cert, certMeta, err := serverCertificate(certSize, certFile)
	if err != nil {
		fmt.Fprintln(os.Stderr, "certificate:", err)
		os.Exit(2)
	}
	encodedMeta, _ := json.Marshal(certMeta)
	fmt.Fprintln(os.Stderr, "cert DER =", certMeta.DERBytes, "bytes")
	fmt.Fprintln(os.Stderr, "CERT_META", string(encodedMeta))
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
		feedback:        feedback,
		feedbackVersion: feedbackVersion,
		profile:         profile,
		wideRead:        wideReadFor(profile),
		certMeta:        &certMeta,
		flights:         map[string]*flightRec{}}
	if hold != nil {
		fc.hold = newHoldState(*hold)
	}
	if connLogPath != "" {
		connLog, err := openConnLog(connLogPath)
		if err != nil {
			fmt.Fprintln(os.Stderr, "conn-log:", err)
			os.Exit(2)
		}
		fc.connLog = connLog
	}
	var serverConn net.PacketConn = fc
	if udpPath == "oob" {
		serverConn = newUDPDecodeConn(fc, udp)
	}
	tr := &quic.Transport{Conn: serverConn, ConnectionIDLength: serverConnIDLength, ConnContext: fc.accountContext}
	fc.stats.SourceVerifyEnabled, fc.stats.SessionTicketsEnabled = verifySource, resume
	if verifySource {
		tr.VerifySourceAddress = fc.verifySource
	}
	tlsConf := &tls.Config{
		Certificates: []tls.Certificate{cert},
		NextProtos:   []string{"padfec"},
		MinVersion:   tls.VersionTLS13,
		CurvePreferences: []tls.CurveID{
			tls.X25519MLKEM768, tls.X25519, tls.CurveP256,
		},
		SessionTicketsDisabled: !resume,
	}
	ln, err := tr.Listen(tlsConf, &quic.Config{
		Tracer:                  fc.accountTracer,
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
	writeStats := func(includeConns bool) {
		if statsPath == "" {
			return
		}
		statsMu.Lock()
		defer statsMu.Unlock()
		b, err := json.Marshal(fc.report(includeConns))
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
				writeStats(false)
			}
		}()
	}
	if fc.connLog != nil {
		go func() {
			for {
				time.Sleep(100 * time.Millisecond)
				fc.flushConnLog(time.Now())
			}
		}()
	}
	if statsPath != "" || fc.connLog != nil {
		sig := make(chan os.Signal, 2)
		signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT)
		go func() {
			<-sig
			if err := fc.finishConnLog(time.Now()); err != nil {
				fmt.Fprintln(os.Stderr, "conn-log:", err)
			}
			writeStats(true)
			os.Exit(0)
		}()
	}
	for {
		conn, err := ln.Accept(context.Background())
		if err != nil {
			continue
		}
		fc.accountAccepted(conn.Context())
		fc.recordTLSResume(conn.Context(), conn.ConnectionState().TLS.DidResume)
		go func(c *quic.Conn) { <-c.Context().Done() }(conn)
	}
}

type trial struct {
	ClientSCID                string                   `json:"client_scid"`
	Profile                   string                   `json:"profile,omitempty"`
	RevisitGuard              *revisitGuardObservation `json:"revisit_guard,omitempty"`
	Revisit                   revisitObservation       `json:"revisit"`
	ClientHelloPadding        inflationInfo            `json:"client_hello_padding"`
	ExtraSent                 extraSent                `json:"extra_sent"`
	RetransLayout             string                   `json:"retrans_layout"`
	BytesParity               int64                    `json:"bytes_parity"`
	FlightTrace               flightTrace              `json:"flight_trace"`
	FlightExpectation         flightExpectation        `json:"flight_expectation"`
	RxRejectedPeer            int                      `json:"rx_rejected_peer"`
	RxRejectedCID             int                      `json:"rx_rejected_cid"`
	FirstFlightNonInitialLong int                      `json:"first_flight_non_initial_long"`
	Arrivals                  p3Arrivals               `json:"arrivals"`
	C1                        c1Observation            `json:"c1"`
	Observation               wireObservation          `json:"observation"`
	HandshakeEndNS            int64                    `json:"handshake_end_ns"`
	FeedbackWaitLimitMS       float64                  `json:"feedback_wait_limit_ms"`
	FeedbackWaitNS            int64                    `json:"feedback_wait_ns"`
	FeedbackWaitReceived      bool                     `json:"feedback_wait_received"`
	I                         int                      `json:"i"`
	Ms                        float64                  `json:"ms"`
	OK                        bool                     `json:"ok"`
	Group                     string                   `json:"group"`
	Err                       string                   `json:"err,omitempty"`
	KEM                       uint16                   `json:"kem_id"`
	CipherID                  uint16                   `json:"cipher_id"`
	Dgrams                    int                      `json:"initial_datagrams"`
	Parity                    int                      `json:"parity_sent"`
	FFDgrams                  int                      `json:"first_flight_datagrams"`
	FFBytes                   int64                    `json:"first_flight_bytes"`
	FFParity                  int                      `json:"first_flight_parity_dgrams"`
	FFParityBytes             int64                    `json:"first_flight_parity_bytes"`
	MUsed                     int                      `json:"m_used"`
	IPSUsed                   int                      `json:"ips_used"`
	IPSEff                    int                      `json:"ips_eff"`
	MWhy                      string                   `json:"m_why,omitempty"`
	SrvBytes                  int64                    `json:"server_bytes"`
	LossEvt                   bool                     `json:"loss_event"`
	PathRTTMS                 float64                  `json:"path_rtt_ms"`
	PathRTTValid              bool                     `json:"path_rtt_valid"`
	PathRTTSource             string                   `json:"path_rtt_source"`
	Layout                    string                   `json:"layout"`
	Lead                      int                      `json:"lead"`
	FFLead                    int                      `json:"first_flight_lead_dgrams"`
	LaterParity               int                      `json:"later_parity_sent"`
}

func measuredPathRTT(stats quic.ConnectionStats) (float64, bool) {
	if stats.MinRTT <= 0 || stats.LatestRTT <= 0 || stats.MeanDeviation <= 0 {
		return 0, false
	}
	return float64(stats.MinRTT) / float64(time.Millisecond), true
}

func recordFinalSendStats(t *trial, agg *clientStats, fin clientStats) {
	t.ClientSCID = fin.ClientSCID
	if t.Arrivals.Src == "" {
		t.Arrivals = p3Arrivals{Src: "none"}
	}
	t.ExtraSent = fin.ExtraSent
	agg.ExtraSent.add(fin.ExtraSent)
	t.FlightTrace = fin.FlightTrace.clone()
	t.RetransLayout = fin.RetransLayout
	agg.RetransLayout = fin.RetransLayout
	t.BytesParity = fin.BytesParity
	agg.FlightTrace.addTotals(fin.FlightTrace)
	t.FlightExpectation = fin.FlightExpectation
	agg.FlightExpectation = fin.FlightExpectation
	t.Dgrams, t.Parity = fin.InitialDgram, fin.ParitySent
	t.FFDgrams, t.FFBytes = fin.FirstFlightDgrams, fin.FirstFlightBytes
	t.FFParity, t.FFParityBytes = fin.FirstFlightParity, fin.FirstFlightParityBytes
	t.FFLead, t.LaterParity = fin.FirstFlightLeadDgrams, fin.LaterParitySent

	agg.Flights += fin.Flights
	agg.ParitySent += fin.ParitySent
	agg.ParityFail += fin.ParityFail
	agg.DroppedOrig += fin.DroppedOrig
	agg.DroppedPar += fin.DroppedPar
	agg.CorruptPar += fin.CorruptPar
	agg.BytesOrig += fin.BytesOrig
	agg.BytesParity += fin.BytesParity
	agg.InitialDgram += fin.InitialDgram
	agg.FirstFlightDgrams = fin.FirstFlightDgrams
	agg.FirstFlightBytes = fin.FirstFlightBytes
	agg.FirstFlightParity = fin.FirstFlightParity
	agg.FirstFlightParityBytes = fin.FirstFlightParityBytes
	agg.Layout = fin.Layout
	agg.Lead = fin.Lead
	agg.FirstFlightLeadDgrams += fin.FirstFlightLeadDgrams
	agg.LaterParitySent += fin.LaterParitySent
	t.RxRejectedPeer = fin.RxRejectedPeer
	t.RxRejectedCID = fin.RxRejectedCID
	t.FirstFlightNonInitialLong = fin.FirstFlightNonInitialLong
	agg.RxRejectedPeer += fin.RxRejectedPeer
	agg.RxRejectedCID += fin.RxRejectedCID
	agg.FirstFlightNonInitialLong += fin.FirstFlightNonInitialLong
	if agg.FlightSizes == nil {
		agg.FlightSizes = map[string]int{}
	}
	for k, v := range fin.FlightSizes {
		agg.FlightSizes[k] += v
	}
}

func runClient(addr, group string, n int, timeout, gap time.Duration,
	mode string, m int, ips int, parityDelayUs int,
	statsPath string, dumpPath string,
	dropInitial map[int]bool, dropParity, corruptParity int,
	cachePath string, mMax, coldM, probeEvery int, uplinkMbps float64,
	feedback bool, layout string, lead int, cache3Path string, padJunk, dup bool, kInflate int, tokenStore, resume bool, revisitWait time.Duration, guardConfig revisitGuardConfig, wiring clientWiring) {
	expectK, expectKSet, feedbackWait, retransMode, profile := wiring.ExpectK, wiring.ExpectKSet, wiring.FeedbackWait, wiring.RetransLayout, wiring.Profile
	if err := padfechook.Configure(kInflate); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
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
	var c3 *destCache3
	if mode == "auto3" {
		var err3 error
		if c3, err3 = loadDestCache3(cache3Path); err3 != nil {
			fmt.Fprintln(os.Stderr, "cache3:", err3)
			os.Exit(2)
		}
	}

	var tokens *trackedTokenStore
	var sessions *trackedSessionCache
	if tokenStore {
		tokens = &trackedTokenStore{store: quic.NewLRUTokenStore(16, 4)}
	}
	if resume {
		sessions = &trackedSessionCache{cache: tls.NewLRUClientSessionCache(16)}
	}
	for i := 0; i < n; i++ {
		tokenBefore, sessionBefore := tokens.snapshot(), sessions.snapshot()
		revisit := revisitObservation{TokenStore: tokenStore, Resume: resume, FirstConnection: i == 0, CacheScope: "process", WaitRequestedNS: int64(revisitWait), WaitRTTSource: "disabled"}
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
		trialLayout, trialLead := layout, lead
		var plan3 auto3Plan
		if mode == "auto3" {
			var err3 error
			if plan3, err3 = c3.plan(addr, wSize, uplinkMbps, cPktDefault); err3 != nil {
				fmt.Fprintln(os.Stderr, "auto3:", err3)
				os.Exit(2)
			}
			trialIPS, trialM, why = plan3.IPS, plan3.M, plan3.Why
			fmode = plan3.FecMode
			trialLayout, trialLead = "v3", plan3.Lead
		}
		udp, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
		if err != nil {
			fmt.Fprintln(os.Stderr, "socket:", err)
			os.Exit(1)
		}
		expectation := chooseFlightExpectation(expectK, expectKSet, mode, plan3)
		fc := &fecConn{countConn: countConn{PacketConn: udp}, mode: fmode,
			expectation: expectation,
			retransMode: retransMode,
			padJunk:     padJunk, dup: dup,
			revisitGuard: newRevisitGuard(guardConfig),
			m:            maxInt(trialM, 1),
			expectK:      expectation.K,
			dropInitial:  dropInitial, dropParity: dropParity,
			corruptParity: corruptParity,
			dumpPath:      dumpPath,
			parityDelay:   time.Duration(parityDelayUs) * time.Microsecond,
			layout:        trialLayout, lead: trialLead}
		tr := &quic.Transport{Conn: fc, ConnectionIDGenerator: clientCIDGenerator{client: fc}}

		tlsConf := &tls.Config{
			InsecureSkipVerify:     true,
			NextProtos:             []string{"padfec"},
			MinVersion:             tls.VersionTLS13,
			CurvePreferences:       []tls.CurveID{curveFor(group)},
			SessionTicketsDisabled: !resume,
		}
		qconf := &quic.Config{
			MaxIdleTimeout:          timeout,
			KeepAlivePeriod:         0,
			Allow0RTT:               false,
			DisablePathMTUDiscovery: true,
		}
		if tokens != nil {
			qconf.TokenStore = tokens
		}
		if sessions != nil {
			tlsConf.ClientSessionCache = sessions
		}
		ipsEff := effectiveInitialSize(trialIPS)
		if trialIPS > 0 {
			qconf.InitialPacketSize = uint16(trialIPS)
		}
		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		start := time.Now()
		observer := newMemoryTrace(start)
		fc.traceEpoch = start
		fc.observer = observer
		if guardConfig.Enabled {
			observer.onRetry = fc.acceptedRevisitRetry
		}
		wiring.installTracer(qconf, observer)
		conn, err := tr.Dial(ctx, ra, tlsConf, qconf)
		el := time.Since(start)
		cancel()
		if err == nil {
			cs := conn.ConnectionState()
			revisit.TLSObserved, revisit.TLSDidResume, revisit.Used0RTT = true, cs.TLS.DidResume, cs.Used0RTT
			if tokenStore || resume {
				target, rtt, source := revisitWaitTarget(revisitWait, el, conn.ConnectionStats())
				revisit.WaitTargetNS, revisit.WaitRTTNS, revisit.WaitRTTSource = int64(target), int64(rtt), source
				elapsed, complete := waitRevisit(conn.Context(), target)
				revisit.WaitElapsedNS, revisit.WaitCompleted = int64(elapsed), complete
			}
		}

		time.Sleep(3 * time.Duration(parityDelayUs) * time.Microsecond)
		var window feedbackWindow
		if feedback && err == nil {
			window = collectFeedbackWindow(observer.serverBytes, conn.ConnectionStats, func() bool { return fc.waitFeedback(feedbackWait) })
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
		t := trial{Profile: profile, Revisit: revisit, ClientHelloPadding: inflationFor(kInflate), I: i, Ms: hct,
			OK: err == nil, Group: group,
			Dgrams: st.InitialDgram, Parity: st.ParitySent,
			FFDgrams: st.FirstFlightDgrams, FFBytes: st.FirstFlightBytes,
			FFParity:      st.FirstFlightParity,
			FFParityBytes: st.FirstFlightParityBytes,
			MUsed:         trialM, IPSUsed: trialIPS, IPSEff: ipsEff,
			MWhy: why, SrvBytes: srvBytes, LossEvt: lossEvt,
			PathRTTSource: "unavailable",
			Layout:        st.Layout, Lead: st.Lead,
			FFLead: st.FirstFlightLeadDgrams, LaterParity: st.LaterParitySent}
		t.Arrivals, t.C1 = fc.arrivalEvidence(feedback)
		t.Observation = observer.snapshot()
		srvBytes = t.Observation.ServerBytes
		t.SrvBytes = srvBytes
		t.HandshakeEndNS = int64(el)
		t.FeedbackWaitLimitMS = float64(feedbackWait) / float64(time.Millisecond)
		t.FeedbackWaitNS = int64(window.Elapsed)
		t.FeedbackWaitReceived = window.Received
		if err != nil {
			t.Err = err.Error()
		} else {
			cs := conn.ConnectionState().TLS
			t.CipherID = cs.CipherSuite
			t.KEM = uint16(cs.CurveID)
			currentStats := conn.ConnectionStats()
			t.PathRTTMS, t.PathRTTValid = measuredPathRTT(window.policyStats(currentStats))
			window.AfterWaitRTTMS, window.AfterWaitRTTValid = measuredPathRTT(currentStats)
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
		if t.Arrivals.Src == "c1" && !t.Arrivals.Trunc && t.Arrivals.Sent > 0 {
			cache.observeSymbols(addr, t.Arrivals.Sent, t.Arrivals.Lost, hct)
		}
		var obs3Info p3ObsInfo
		var obs3After float64
		var obs3Err error
		if mode == "auto3" {
			obs3Info, obs3After, obs3Err = c3.observePred(addr, plan3.Action, plan3.jPred(), hct, err == nil,
				st.FirstFlightDgrams, float64(window.policyServerBytes(srvBytes)), t.PathRTTMS, t.PathRTTValid,
				wSize, uplinkMbps, cPktDefault, &t.Arrivals)
			if obs3Err != nil {
				fmt.Fprintln(os.Stderr, "auto3 observe:", obs3Err)
			}
		}
		tr.Close()
		udp.Close()
		t.Revisit.Token = tokens.snapshot().since(tokenBefore)
		t.Revisit.Session = sessions.snapshot().since(sessionBefore)
		for _, p := range t.Observation.Packets {
			if p.Direction == "received" && p.Space == "retry" {
				t.Revisit.RetryReceived++
			}
		}
		fin := fc.finalSendStats()
		recordFinalSendStats(&t, &agg, fin)
		t.RevisitGuard = fc.revisitGuardSnapshot()
		if mode == "auto3" {
			row := auto3Row(t, plan3, obs3Info, obs3Err, obs3After)
			row.PolicyUplinkMbps = uplinkMbps
			window.annotate(&row)
			enc.Encode(&row)
		} else {
			enc.Encode(&t)
		}
		os.Stdout.Sync()

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
		if gap > 0 {
			time.Sleep(gap)
		}
	}
	if c3 != nil {
		if err := c3.save(); err != nil {
			fmt.Fprintln(os.Stderr, "cache3:", err)
			os.Exit(1)
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

func checkLayoutFlags(layout string, lead int, fmode string, m int) error {
	switch layout {
	case "v2":
		if lead != -1 {
			return fmt.Errorf("-lead %d needs -layout v3", lead)
		}
		return nil
	case "v3":
	default:
		return fmt.Errorf("unknown -layout %q (v2 | v3)", layout)
	}
	if fmode != "fec" && fmode != "auto" {
		return fmt.Errorf("-layout v3 needs -fec fec or -fec auto, got %q", fmode)
	}
	if lead < -1 || lead > 15 {
		return fmt.Errorf("-lead %d outside -1..15", lead)
	}
	if fmode == "fec" {
		if eff := maxInt(m, 1); eff > 15 || lead > eff {
			return fmt.Errorf("-layout v3 needs lead <= m <= 15, got lead %d m %d", lead, eff)
		}
	}
	return nil
}

const profileSealed31 = "sealed31"

type runSettings struct {
	UDPPath         string
	RetransLayout   string
	FeedbackWait    time.Duration
	FeedbackVersion int
	ClientTracer    bool
	ExpectK         int
	ExpectKSet      bool
}

func defaultRunSettings() runSettings {
	return runSettings{UDPPath: "oob", RetransLayout: "repeat_first", FeedbackWait: time.Second, FeedbackVersion: fbVer, ClientTracer: true}
}

func sealed31Settings() runSettings {
	return runSettings{UDPPath: "basic", RetransLayout: "repeat_first", FeedbackWait: 200 * time.Millisecond, FeedbackVersion: fbVerFrozen, ClientTracer: false, ExpectKSet: true}
}

func profileName(profile string) string {
	if profile == "" {
		return "default"
	}
	return profile
}

func wideReadFor(profile string) bool {
	return profile != profileSealed31
}

func applyRunProfile(profile string, explicit map[string]bool, s *runSettings) error {
	switch profile {
	case "":
		return nil
	case profileSealed31:
	default:
		return fmt.Errorf("unknown -profile %q (default | %s)", profile, profileSealed31)
	}
	want := sealed31Settings()
	var conflicts []string
	for _, c := range []struct {
		name string
		same bool
	}{
		{"udp-path", s.UDPPath == want.UDPPath},
		{"retrans-layout", s.RetransLayout == want.RetransLayout},
		{"feedback-wait", s.FeedbackWait == want.FeedbackWait},
		{"feedback-version", s.FeedbackVersion == want.FeedbackVersion},
		{"client-tracer", s.ClientTracer == want.ClientTracer},
	} {
		if explicit[c.name] && !c.same {
			conflicts = append(conflicts, c.name)
		}
	}
	if len(conflicts) > 0 {
		return fmt.Errorf("-profile %s fixes %s", profileSealed31, strings.Join(conflicts, ", "))
	}
	s.UDPPath, s.RetransLayout, s.FeedbackWait = want.UDPPath, want.RetransLayout, want.FeedbackWait
	s.FeedbackVersion, s.ClientTracer = want.FeedbackVersion, want.ClientTracer
	if !explicit["expect-k"] {
		s.ExpectK, s.ExpectKSet = 0, true
	}
	return nil
}

func checkRunSettings(mode string, explicit map[string]bool, s runSettings, revisitGuard bool) error {
	if s.UDPPath != "basic" && s.UDPPath != "oob" {
		return fmt.Errorf("udp-path must be basic or oob")
	}
	if err := checkRetransLayout(s.RetransLayout); err != nil {
		return err
	}
	if s.FeedbackWait < 0 {
		return fmt.Errorf("feedback-wait must be nonnegative")
	}
	if err := checkFeedbackVersion(s.FeedbackVersion); err != nil {
		return err
	}
	if s.ExpectK < 0 || s.ExpectK > 32 {
		return fmt.Errorf("expect-k must be between 0 and 32")
	}
	if mode != "server" && (explicit["feedback-version"] || explicit["conn-log"]) {
		return fmt.Errorf("feedback-version and conn-log are server options")
	}
	if mode != "client" && explicit["client-tracer"] {
		return fmt.Errorf("client-tracer is a client option")
	}
	if revisitGuard && !s.ClientTracer {
		return fmt.Errorf("revisit-guard needs the client tracer to observe Retry")
	}
	return nil
}

type clientWiring struct {
	ExpectK       int
	ExpectKSet    bool
	FeedbackWait  time.Duration
	RetransLayout string
	ClientTracer  bool
	Profile       string
}

type runWiring struct {
	Profile  string
	Settings runSettings
	Client   clientWiring
}

func wireRun(mode, profile string, explicit map[string]bool, flags runSettings, revisitGuard bool) (runWiring, error) {
	if profile == "default" {
		profile = ""
	}
	s := flags
	s.ExpectKSet = explicit["expect-k"]
	if err := applyRunProfile(profile, explicit, &s); err != nil {
		return runWiring{}, err
	}
	if err := checkRunSettings(mode, explicit, s, revisitGuard); err != nil {
		return runWiring{}, err
	}
	client := clientWiring{ExpectK: s.ExpectK, ExpectKSet: s.ExpectKSet, FeedbackWait: s.FeedbackWait,
		RetransLayout: s.RetransLayout, ClientTracer: s.ClientTracer, Profile: profile}
	return runWiring{Profile: profile, Settings: s, Client: client}, nil
}

func (w clientWiring) installTracer(qconf *quic.Config, observer *memoryTrace) {
	if w.ClientTracer {
		qconf.Tracer = observer.tracer
	} else {
		observer.disableTracer()
	}
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
		"client | server | certgen | selftest | policygrid | policy3ref")
	addr := flag.String("addr", "127.0.0.1:44433", "address")
	group := flag.String("group", "X25519MLKEM768", "key exchange group")
	certSize := flag.Int("certsize", 2955, "target certificate DER size")
	certFile := flag.String("cert-file", "", "shared testbed certificate and PKCS#8 key PEM")
	dryRun := flag.Bool("dry-run", false, "certgen metadata without writing a file")
	n := flag.Int("n", 20, "handshakes")
	timeout := flag.Duration("timeout", 12*time.Second, "per-handshake timeout")
	gap := flag.Duration("gap", 25*time.Millisecond, "gap between handshakes")
	fec := flag.String("fec", "off",
		"off | buf | on | auto | auto3  (auto = 목적지 캐시로 m 을 스스로 고름, "+
			"auto3 = v3 학습층이 (δ, ℓ, T) 를 고르고 -layout v3 로 보냄)")
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
	revisitGuard := flag.Bool("revisit-guard", false, "development fixed-flight token/Retry and one-bundle rule")
	decoderSupport := flag.String("decoder-support", "unknown", "revisit-guard decoder capability: unknown | supported | unsupported")
	tokenStore := flag.Bool("token-store", false, "share address tokens across client connections")
	resume := flag.Bool("resume", false, "enable client TLS session cache or server tickets")
	verifySource := flag.Bool("verify-source", false, "server requires Retry for unvalidated addresses")
	revisitWait := flag.Duration("revisit-wait", 200*time.Millisecond, "minimum post-handshake token/ticket collection time")
	kInflate := flag.Int("k-inflate", 0, "ClientHello extra transport parameter value bytes (0..8192, fixed off/buf)")
	ips := flag.Int("ips", 0, "InitialPacketSize (0 = quic-go default)")
	pdelay := flag.Int("parity-delay-us", 300, "delay before emitting parity")
	expectK := flag.Int("expect-k", 0, "명시한 묶음 데이터그램 수 (0 = 타이머 강제, 생략 = auto3의 첫 묶음 k 추정)")
	dump := flag.String("dump-flight", "", "첫 비행 원본 데이터그램을 이 파일에 기록")
	dropI := flag.String("drop-initial", "",
		"검증용: 첫 비행의 이 인덱스들(쉼표 구분) 원본을 보내지 않는다")
	dropP := flag.Int("drop-parity", -1,
		"검증용: N 번째 패리티를 보내지 않는다 (-1 = 안 함)")
	corrP := flag.Int("corrupt-parity", -1,
		"검증용: N 번째 패리티의 한 바이트를 뒤집는다 (-1 = 안 함)")
	padJunk := flag.Bool("pad-junk", false, "replace every parity slot with equal-size non-FEC Initial junk")
	dup := flag.Bool("dup", false, "replace parity slot j with byte-identical original j mod k")
	defaults := defaultRunSettings()
	udpPath := flag.String("udp-path", defaults.UDPPath, "server UDP path: basic | oob")
	profile := flag.String("profile", "", "default | sealed31 (v3.1 봉인 조건: udp-path basic, retrans-layout repeat_first, feedback-wait 200ms, feedback-version 2, client-tracer off, expect-k 생략 시 0)")
	feedbackVersion := flag.Int("feedback-version", defaults.FeedbackVersion, "서버 C1 회신 판본: 3 | 2 (2는 gen-2·v3.1·v3.2 클라이언트도 읽는다)")
	clientTracer := flag.Bool("client-tracer", defaults.ClientTracer, "클라이언트 메모리 qlog tracer (ACK·CRYPTO·RTT·PTO 관측)")
	connLogPath := flag.String("conn-log", "", "서버 연결별 JSONL: 계정 만료·LRU 축출·종료 직전에 연결마다 한 줄 (새 파일만)")
	stats := flag.String("stats", "", "write stats JSON here")
	feedback := flag.Bool("feedback", false,
		"C1: 서버가 첫 비행 수신 심볼 수를 회신한다(클라는 그것으로 손실 관측)")
	feedbackWait := flag.Duration("feedback-wait", defaults.FeedbackWait, "HCT 이후 C1 수집 대기 한도")
	retransMode := flag.String("retrans-layout", defaults.RetransLayout, "v3 응답 전 후속 묶음: repeat_first | original_first (original_first는 정책 비용 모형에 아직 없다)")
	layout := flag.String("layout", "v2",
		"v2 | v3 (v3 첫 묶음 [L,O,T], 응답 전 후속은 retrans-layout, 응답 뒤 원본 즉시 + 뒤 패리티 <=1)")
	lead := flag.Int("lead", -1,
		"-layout v3 의 선행 신용 패리티 수 (-1 = 레거시 [m>=2])")
	cache3 := flag.String("cache3", "",
		"-fec auto3 의 목적지별 학습 상태 파일 (gen-2 -cache 와 따로 둔다)")
	exploreRate := flag.Float64("p3-explore-rate-ms", 0, "-fec auto3 none 경로의 탐색 원장 적립 ms/연결 (0 = 끔)")
	leadHold := flag.Bool("lead-hold", false, "서버의 v3 선행 패리티 보류 복호")
	holdRate := flag.Int64("lead-hold-uplink-kbps", 2000, "보류 기한의 명시 업링크 kbps, 0은 무제한")
	holdMargin := flag.Duration("lead-hold-margin", time.Millisecond, "보류 기한의 여유 시간")
	flag.Parse()
	explicit := map[string]bool{}
	flag.Visit(func(f *flag.Flag) { explicit[f.Name] = true })
	wiring, err := wireRun(*mode, *profile, explicit, runSettings{UDPPath: *udpPath, RetransLayout: *retransMode, FeedbackWait: *feedbackWait,
		FeedbackVersion: *feedbackVersion, ClientTracer: *clientTracer, ExpectK: *expectK}, *revisitGuard)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	settings, runProfile := wiring.Settings, wiring.Profile
	layoutSet := explicit["layout"]

	fmode := "off"
	switch *fec {
	case "on", "fec":
		fmode = "fec"
	case "buf":
		fmode = "buf"
	case "auto":
		fmode = "auto"
	case "auto3":
		fmode = "auto3"
	}
	guardConfig := revisitGuardConfig{Enabled: *revisitGuard, DecoderSupport: *decoderSupport}
	if err := checkRevisitGuard(guardConfig, *mode, fmode, *layout, *ips, *m, *padJunk, *dup); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := checkRevisitFlags(*mode, fmode, *tokenStore, *resume, *verifySource, *revisitWait); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := checkComparisonFlags(*padJunk, *dup, *mode, fmode, *layout, *corrP); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := checkInflationFlags(*kInflate, *mode, fmode); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if err := checkInitialSize(*ips); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if *dryRun && *mode != "certgen" {
		fmt.Fprintln(os.Stderr, "dry-run requires certgen mode")
		os.Exit(2)
	}
	if *certFile != "" && *mode != "server" && *mode != "certgen" {
		fmt.Fprintln(os.Stderr, "cert-file requires server or certgen mode")
		os.Exit(2)
	}
	switch *mode {
	case "certgen":
		meta, err := generateCertificateFile(*certSize, *certFile, *dryRun)
		if err != nil {
			fmt.Fprintln(os.Stderr, "certificate:", err)
			os.Exit(2)
		}
		if err := json.NewEncoder(os.Stdout).Encode(meta); err != nil {
			fmt.Fprintln(os.Stderr, "certificate metadata:", err)
			os.Exit(1)
		}
		return
	case "selftest":
		os.Exit(selfTest())
	case "policygrid":
		policyGrid()
		return
	case "policy3ref":
		os.Exit(policy3RefMain(os.Stdin, os.Stdout))
	case "server":
		if fmode == "auto3" || *cache3 != "" {
			fmt.Fprintln(os.Stderr, "auto3: -fec auto3 and -cache3 are client options")
			os.Exit(2)
		}
		var hc *holdConfig
		if *leadHold {
			config := defaultHoldConfig()
			config.uplinkKbps, config.margin = *holdRate, *holdMargin
			if fmode != "fec" || config.uplinkKbps < 0 || config.margin < 0 || config.margin >= config.ttl {
				fmt.Fprintln(os.Stderr, "lead-hold: fec 서버, 음수가 아닌 속도, 0 이상 1초 미만 margin이 필요합니다")
				os.Exit(2)
			}
			hc = &config
		}
		runServer(*addr, *certSize, *certFile, fmode, *stats, *feedback, hc, settings.UDPPath, *resume, *verifySource, settings.FeedbackVersion, *connLogPath, runProfile)
	default:
		if *leadHold {
			fmt.Fprintln(os.Stderr, "lead-hold는 서버 옵션입니다")
			os.Exit(2)
		}
		if fmode == "auto3" {
			if err := checkAuto3Uplink(explicit); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(2)
			}
			if err := checkAuto3Flags(layoutSet, *layout, *lead, *ips); err != nil {
				fmt.Fprintln(os.Stderr, "auto3:", err)
				os.Exit(2)
			}
			if !p3Finite(*exploreRate) || *exploreRate < 0 {
				fmt.Fprintln(os.Stderr, "auto3: -p3-explore-rate-ms must be finite and >= 0")
				os.Exit(2)
			}
			p3ExploreRateMs = *exploreRate
			if warning := auto3ParityWarning(*ips, *expectK); warning != "" {
				fmt.Fprintln(os.Stderr, warning)
			}
		} else if *cache3 != "" || *exploreRate != 0 {
			fmt.Fprintln(os.Stderr, "auto3: -cache3 and -p3-explore-rate-ms need -fec auto3")
			os.Exit(2)
		} else if err := checkLayoutFlags(*layout, *lead, fmode, *m); err != nil {
			fmt.Fprintln(os.Stderr, "layout:", err)
			os.Exit(2)
		}
		runClient(*addr, *group, *n, *timeout, *gap, fmode, *m, *ips,
			*pdelay, *stats, *dump, parseIdx(*dropI),
			*dropP, *corrP, *cache, *mMax, *coldM, *probeEvery, *uplink,
			*feedback, *layout, *lead, *cache3, *padJunk, *dup, *kInflate, *tokenStore, *resume, *revisitWait, guardConfig, wiring.Client)
	}
}
