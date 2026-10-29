// qamp - 증폭 제한 실험 도구 + 핸드셰이크 FEC.
//
// 인수인계 문서(2026-08-18) 3-2/3-3 이 말하는 그 qamp.go 다. 문서가 지정한
// 구조를 그대로 따른다.
//
//	countConn  net.PacketConn 을 감싸서 송수신 데이터그램의 개수와 크기를
//	           기록한다. WriteTo 와 ReadFrom 을 가로챈다.
//	           "FEC 인코딩을 끼워 넣을 지점이 바로 여기입니다."
//	makeCert   인증서에 더미 확장을 넣어 목표 바이트 수로 부풀린다.
//	runClient / runServer   quic.Transport 를 직접 만들어 쓴다.
//
// 문서 3-4 가 못박은 전제: quic.DialAddr() 은 라이브러리가 소켓을 내부에서
// 만들어 버려 손댈 수 없다. quic.Transport{Conn: 우리소켓} 이라야 WriteTo 를
// 가로챌 수 있다.
//
// 문서 단계 1~3 을 구현한 부분
//
//	fecConn    (클라이언트) 문서 단계 1 의 구조 - window/parity/k/enabled.
//	           비행을 모아 XOR 복구 심볼을 만들어 함께 내보낸다.
//	decodeConn (서버)  문서 단계 3 - ReadFrom 을 가로채 빠진 데이터그램을
//	           복원하고 "방금 수신한 것처럼" 스택에 넘긴다.
//
// 문서 단계 2 의 세 방식 중 **A(별도 데이터그램)** 로 간다. B(패딩 자리
// 교체)는 용량 부등식 C <= (k-1)(W-h-f) 때문에 실측한 모든 설정에서 성립하지
// 않는다(padfec/capacity.py). 그 판단 근거는 보고서 2장에 적었다.
//
// 설계 요점
//
//  1. 패리티 심볼은 **데이터그램 와이어 바이트 전체**다. 복구 결과가 원본과
//     비트 단위로 같아서 수신측이 QUIC Initial 키를 몰라도 되고, 복구본을
//     그대로 스택에 밀어 넣으면 끝난다.
//
//  2. 패리티는 올바른 DCID 를 가진 롱헤더 Initial 모양으로 보낸다. quic-go 는
//     이것을 연결에 귀속시켜 **바이트를 센 뒤**(connection.go handleOnePacket
//     첫 줄의 ReceivedBytes) 복호에 실패해 폐기한다. 그래서 RFC 9000 8.1 의
//     3배 예산이 그만큼 늘어난다 - 이 설계의 두 번째 이득이다.
//
//  3. 복구를 실제로 수행한 경우에는 패리티를 스택에 넘기지 않고 복구본을
//     대신 넘긴다. 그러지 않으면 도착하지도 않은 바이트가 증폭 예산에
//     계상돼 3배 한도가 4.5배가 된다. 우리 쪽에 유리한 반올림을 하지 않기
//     위한 규칙이며, 런타임에 불변식으로 강제한다.
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

// ------------------------------------------------------------------ GF(256)
// afec/rs.py 와 같은 다항식(0x11d)과 같은 Cauchy 생성행렬을 쓴다. 두 구현이
// 같은 시험 벡터에서 같은 패리티를 내는지 실험 단계에서 대조한다.

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

// cauchyRow 는 패리티 p 행의 계수 k 개를 돌려준다.
//
// 🩸 명세는 afec/rs.py 와 같아야 한다. 처음에는 x_p = k+p, y_o = o 로 잡았는데
// Python 은 x_p = p, y_o = m+o 를 쓴다. 둘 다 유효한 Cauchy 행렬이라 각자는
// 정상 복구되지만 **서로 호환되지 않는다.** k=2,m=2 에서만 XOR 대칭 때문에
// 우연히 같은 값이 나와 그 조합만 통과했고, p5 교차검증이 k>=3 에서 잡았다.
// "아무거나 골라도 되는" 자유도가 있는 곳이 정확히 어긋난다.
func cauchyRow(m, p, k int) []byte {
	row := make([]byte, k)
	for o := 0; o < k; o++ {
		row[o] = gfInv(byte(p) ^ byte(m+o))
	}
	return row
}

// rsEncode 는 k 개 원본에서 m 개 패리티를 만든다. m == 1 이면 순수 XOR 이다
// (인수인계 문서 2-3 이 지정한 형태이고, 1-소거에는 XOR 도 MDS 다).
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

// recoverOne 은 소거 하나를 복원한다.
//
// 🩸 패리티 **인덱스**를 반드시 받아야 한다. m >= 2 에서는 패리티마다 Cauchy
// 생성행렬의 다른 행을 쓰므로, 인덱스 1 의 패리티를 행 0 의 계수로 풀면
// 엉뚱한 값이 나온다. 처음에 이 인자를 빼먹어서 m=2 의 복구가 전부 CRC 에서
// 탈락했다(복구 0건). m == 1 은 순수 XOR 이라 행 개념이 없다.
// parityRow 는 패리티 p 행의 계수 k 개를 준다. m==1 은 순수 XOR 이므로
// 계수가 전부 1 이고, 그 외에는 Cauchy 행이다. rsEncode 의 두 분기와 **정확히
// 같은 계수**를 써야 한다 - 부호기와 복호기가 다른 행렬을 쓰면 조용히 틀린다.
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

// gfMatInv 는 GF(256) 정사각행렬을 가우스 소거로 뒤집는다. 특이하면 nil.
// Cauchy 부분행렬은 구성상 항상 가역이므로 nil 은 인자가 잘못됐다는 뜻이다.
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

// recoverMany 는 소거 e 개를 한꺼번에 복원한다. recoverOne 을 대신한다.
//
//	missing   복원할 원본 인덱스 (0..k-1)
//	origs     살아남은 원본. missing 에 든 것은 들어 있으면 안 된다.
//	parities  쓸 수 있는 **복구용** 패리티 {패리티인덱스: 심볼}.
//	          ⚠️ 증폭 신용으로 이미 스택에 넘긴 패리티는 넣으면 안 된다 -
//	          그 바이트가 예산과 복구에 이중 계상돼 RFC 9000 8.1 의 3 배
//	          한도를 우회하게 된다(decodeConn.ReadFrom 의 불변식 주석).
//
// 🩸 2026-08-27 신레오 보고로 신설. 옛 recoverOne 은 소거를 **정수 하나**로
//
//	받았고, 두 분기가 **비대칭으로 실패**했다:
//	  m >= 2 : 다른 원본이 하나라도 없으면 nil (닫히며 실패 - 안전)
//	  m == 1 : 있는 것만 XOR 하고 **nil 을 안 돌려준다** (열리며 실패 -
//	           파리티 심볼을 그대로 원본이라고 내놓는다. 실측으로 1,200 B
//	           중 1,197 B 가 다르다)
//	두 분기가 다르게 실패하는 것이 함정이었다. 여기서는 **분기 자체를
//	없앤다** - 살아남은 원본이 다 있는지 한 곳에서 검사하므로 규칙이
//	갈라질 자리가 없다.
//
//	옛 코드가 실제로 잘못된 값을 내보낸 적은 없다. 유일한 제품 호출부
//	(tryRecoverLocked)가 len(missing) > 1 에서 먼저 빠져나가기 때문이다.
//	그래서 이것은 **잠재된 덫**이었지 살아 있는 결함은 아니었다 -
//	다만 그 덫을 막고 있던 것이 호출부 가드 하나뿐이었다.
func recoverMany(k, m int, missing []int, origs map[int][]byte,
	parities map[int][]byte, size int) map[int][]byte {
	e := len(missing)
	if e == 0 || e > k {
		return nil
	}
	// 살아남은 원본이 전부 있어야 한다. 없으면 **닫히며** 실패한다.
	for i := 0; i < k; i++ {
		if inIntSlice(missing, i) {
			continue
		}
		if _, ok := origs[i]; !ok {
			return nil
		}
	}
	// 쓸 패리티 e 개를 인덱스 순으로 고른다. Cauchy 는 어느 정방 부분행렬도
	// 가역이므로 어떤 조합을 골라도 성립한다 - 그것이 Cauchy 를 쓰는 이유다.
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

	// 신드롬: 살아남은 원본의 기여를 각 패리티에서 걷어낸다.
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
	// e x e 부분행렬 (행 = 고른 패리티, 열 = 소거된 원본) 을 뒤집는다.
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

// combinations 는 0..n-1 에서 r 개를 고르는 모든 조합을 준다 (사전순).
// permutations 는 0..n-1 의 모든 순열을 준다. 도착 순서 전수 시험용.
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

// feedOne 은 데이터그램 하나를 ReadFrom 경로에 그대로 통과시킨다.
// 회계 불변식 시험용 - 네트워크 없이 decodeConn 의 회계만 돌린다.
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
	// ⚠️ 아래는 ReadFrom 의 패리티 경로와 **같은 규칙**이어야 한다.
	//    어긋나면 이 시험이 실제 경로가 아닌 것을 재게 된다.
	if s.creditLocked(ca, fb, n) {
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
	}
	fr.fb = fb
	// 🩸 2026-08-28 (2 단계 감사) - ReadFrom 과 **같은 가드**다. 근거는 거기
	//    주석에 적었다(결론이 난 비행을 다시 풀면 같은 원본을 또 복원한다).
	//    두 경로가 갈라지면 자체시험이 재는 것과 실제로 도는 것이 달라진다.
	if fr.done || fr.poisoned {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return
	}
	fr.syms[fb.index] = fb.sym
	outs := s.tryRecoverLocked(fr, true)
	if rec := s.settleRecovery(fr, outs); rec != nil {
		// 2026-09-07 감사 - 복원본은 스택에 올라가는 바이트다. 장부에 적는다
		// (ReadFrom 과 같은 수리. 근거는 거기 주석).
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

// pendingErasures 는 이 비행에서 아직 안 온 원본 수다. mu 를 쥔 채로 부른다.
// 뒤따르는 패리티는 원본보다 **뒤에** 오므로, 그 도착 시점의 이 수는
// 「앞으로 몇 개를 복구해야 하는가」와 같다.
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

// settleRecovery 는 복원본 묶음을 회계와 함께 정산한다. mu 를 쥔 채로 부른다.
//
// 🩸 2026-08-28 - 판정과 기록을 **한 곳에** 모은다. 그전에는 복구 함수가
//
//	pending 에 넣고 Recovered 를 올린 뒤 호출부가 따로 판정해서, 거절된
//	복구까지 예약 바이트로 세어져 불변식이 깨졌다.
//
// 돌려주는 것: 스택에 넘길 첫 복원본 (없으면 nil).
// 나머지는 pending 에 예약한다. 회계가 안 되면 아무것도 안 하고 nil 이다.
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
	// 쓰인 뒤따르는 패리티는 **보류 중이므로 아직 스택에 없다.** 그래서
	// 왼쪽에 더할 것은 복원본뿐이다. 복원본(W)은 패리티(W+오버헤드)보다
	// 작으므로 여유가 남는다 - 그 차이가 이 설계가 신용에서 치르는 값이다.
	if s.stats.BytesToStack+s.pendingBytes+tot > s.stats.BytesIn {
		s.stats.RecoverRefused++
		return nil
	}
	fr.done = true
	s.stats.Recovered += len(outs)
	if fr.acct != nil && !fr.acct.FbSent {
		fr.acct.RecovN += len(outs)
	}
	// 사건 수는 **비행당 한 번**이어야 한다. fr.done 가드가 죽으면 여기가
	// 두 번 이상 돌고, 그것을 자체시험이 [중복] 로 잡는다.
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
	// 보류했던 바이트는 이제 역할이 정해졌다. 회계에서 놓아 준다.
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

// ------------------------------------------------------- QUIC 롱헤더 파싱
type longHdr struct {
	ok      bool
	typ     byte // 0=Initial 1=0-RTT 2=Handshake 3=Retry
	version uint32
	dcid    []byte
	scid    []byte
	bodyOff int // 토큰/길이 필드 앞 위치 (SCID 다음)
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
	// 2바이트 고정 인코딩 (0 <= v < 16384). 우리 패리티 길이는 항상 여기 든다.
	return append(b, byte(0x40|(v>>8)), byte(v))
}

// ------------------------------------------------------------- FEC 블록
const fecMagicLen = 4

var fecMagic = []byte{'P', 'F', 'E', 'C'}

const fecVer = 1

const fecVerLead = 3

const serverFlightMin = 1200

type fecBlock struct {
	flight uint16
	k      int
	m      int
	index  int // 이 패리티의 번호 (0..m-1)
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

// buildParity 는 패리티 하나를 담은 데이터그램을 만든다. 겉모양은 정상적인
// 롱헤더 Initial 이라 서버가 연결에 귀속시켜 바이트를 세지만, 페이로드가
// AEAD 를 통과하지 못하므로 QUIC 스택은 조용히 폐기한다.
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
	out = append(out, 0xC3) // 롱헤더 + fixed bit + Initial + pn len 4
	out = binary.BigEndian.AppendUint32(out, 1)
	out = append(out, byte(len(dcid)))
	out = append(out, dcid...)
	out = append(out, byte(len(scid)))
	out = append(out, scid...)
	out = append(out, 0x00) // token length = 0
	out = appendVarint2(out, uint64(len(body)))
	out = append(out, body...)
	return out
}

// ------------------------------------------------------- C1 수신 피드백
//
// 서버가 첫 비행에서 **실제로 받은 심볼 수**를 클라이언트에게 알려 준다.
// 그러면 클라이언트는 일부러 m=0 으로 가는 탐색 라운드 없이도 손실을 관측한다.
//
// 왜 필요한가 (p17 실측, 2026-08-23):
//
//	손실  2% -> 목표 m=1  적중 96.3%
//	손실 15% -> 목표 m=2  적중 ** 0.0%**   <- 상승을 전혀 못 따라간다
//
// 원인은 캐시 관성이다. 관측이 탐색 라운드에서만(연결의 5%), 단위가 연결,
// decay 0.99 의 유효 메모리 100 — 구간당 관측 7~8 개로는 100 을 못 갈아치운다
// (모형 재현: m=2 로 바뀌는 데 1,500 연결). 피드백이면 연결마다 k+m 심볼이
// 들어와 한 구간에 갈아치운다.
//
// ⚠️ **증폭 예산을 건드리면 안 된다.** 서버가 첫 비행 중에 이 회신을 보내면
// 그 바이트가 예산을 먹어, 최적화 대상을 피드백이 갉아먹는 자기모순이 된다.
// 그래서 **클라이언트의 Handshake 패킷을 받은 뒤**에 보낸다 — 그 시점에는
// 주소 검증이 끝나 증폭 한도가 해제돼 있다.
//
// 겉모양은 패리티와 같은 방식이다: 롱헤더 Initial 이라 상대가 연결에
// 귀속시키지만 AEAD 를 통과하지 못해 QUIC 스택은 조용히 폐기하고, 우리
// 계층이 가로채 읽는다.
// fbEarly - **진단 전용**. 첫 데이터그램에도 회신해서 "도달 자체가 되는가"를
// 가른다. 증폭 예산을 쓰므로 측정에 쓰면 안 된다(환경변수로만 켠다).
var fbEarly = os.Getenv("PADFEC_FB_EARLY") == "1"

var fbMagic = []byte{'P', 'F', 'B', 'K'}

// bytesIndex - 진단용 부분열 검색. 표준 bytes 를 새로 import 하지 않으려고
// 직접 쓴다(이 파일의 import 목록을 건드리면 다른 곳이 흔들린다).
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

// Version 2 identifies received datagrams by CRC. Raw counts also include PTO
// retransmissions, so they cannot measure loss in the original flight.
const fbVer = 2
const fbCRCCap = 64

type fbRec struct {
	flight    uint16
	k         uint8 // 서버가 이 비행에서 기대한 원본 수 (참고)
	rxOrig    uint8 // 실제로 받은 원본 데이터그램 수
	rxPar     uint8 // 실제로 받은 패리티 데이터그램 수
	recov     uint8 // 복구한 원본 수
	crcs      []uint32
	truncated bool // CRC storage filled; do not infer loss from this report
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
	out = append(out, 0xC3) // 롱헤더 + fixed + Initial + pn len 4
	out = binary.BigEndian.AppendUint32(out, 1)
	out = append(out, byte(len(dcid)))
	out = append(out, dcid...)
	out = append(out, byte(len(scid)))
	out = append(out, scid...)
	out = append(out, 0x00) // token length = 0
	out = appendVarint2(out, uint64(len(body)))
	out = append(out, body...)
	return out
}

// readVarint 는 QUIC 가변길이 정수를 읽는다(RFC 9000 §16).
// 앞 2 비트가 길이를 정한다: 00=1, 01=2, 10=4, 11=8 바이트.
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

// hasHandshake 는 데이터그램 안에 Handshake 패킷이 있는지 본다.
//
// 🩸 2026-08-23 - 첫 판은 parseLongHdr 로 **첫 패킷만** 봤는데, 클라이언트는
//
//	두 번째 비행에서 Initial(ACK)과 Handshake 를 **한 데이터그램에
//	코얼레스**해 보낸다. 그래서 전부 typ 0 으로 분류돼 회신이 한 번도
//	나가지 않았다(실측: hdr_initial 100, hdr_handshake **0**).
//	코얼레스된 패킷을 길이 필드로 따라가며 전부 훑는다.
func hasHandshake(d []byte) bool {
	i := 0
	for i < len(d) {
		h := parseLongHdr(d[i:])
		if !h.ok {
			return false // 짧은 헤더 = 1-RTT. 그 뒤로는 롱헤더가 없다.
		}
		if h.typ == 2 {
			return true
		}
		j := h.bodyOff
		if h.typ == 0 { // Initial 만 토큰 길이 필드를 갖는다
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

// parseFeedback 은 데이터그램이 서버의 수신 회신인지 보고 내용을 돌려준다.
// 형식은 parseFecBlock 과 같은 규칙을 따른다(토큰 0, 2 바이트 varint 길이).
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

// matchFirstFlight counts unique first-flight datagrams. Retransmitted QUIC
// packets have new packet numbers and do not replace missing original CRCs.
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

// parseFecBlock 은 데이터그램이 우리 패리티인지 보고, 맞으면 내용을 돌려준다.
func parseFecBlock(d []byte) *fecBlock {
	h := parseLongHdr(d)
	if !h.ok || h.typ != 0 {
		return nil
	}
	i := h.bodyOff
	if i >= len(d) || d[i] != 0x00 {
		return nil // 우리 패리티는 토큰 길이를 항상 0 으로 쓴다
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
	// 🩸 2026-08-28 **별칭 수리 (차단 결함).**
	//    옛 코드는 `fb.sym = b[j : j+fb.symLen]` 로 **호출자 버퍼를 그대로
	//    가리켰다.** 바로 위의 crcs·lens 는 make 로 복사하는데 sym 만
	//    아니었다. flightRec 은 이 fb 를 뒤의 ReadFrom 호출 너머까지 들고
	//    있고, quic-go v0.61.0 은 sync.Pool 버퍼로 읽어 재사용한다
	//    (sys_conn.go:117 getPacketBuffer / :121 ReadFrom(buffer.Data)).
	//    그래서 보관한 심볼이 비결정적으로 덮인다 - 늦은 복구가
	//    "되기도 하고 안 되기도" 한다.
	//
	//    ⚠️ 이 복사만 단독으로 넣으면 **더 나빠진다.** 별칭이 지금은
	//       우연한 안전망이라(덮인 심볼은 CRC 가 걸러 낸다) 위의 회계
	//       순서 결함을 가리고 있다. 둘은 **같이** 가야 한다.
	fb.sym = append([]byte(nil), b[j:j+fb.symLen]...)
	return fb
}

// ------------------------------------------------------------- countConn
// 문서 3-3 의 countConn. 송수신 데이터그램의 개수와 크기를 기록한다.
// fecConn(클라이언트)과 decodeConn(서버)이 이것을 품고, 그 위에 FEC 를 얹는다.
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

// ------------------------------------------------------- 클라이언트 쪽 FEC
type clientStats struct {
	Flights      int            `json:"flights"`
	FlightSizes  map[string]int `json:"flight_sizes"`
	ParitySent   int            `json:"parity_sent"`
	ParityFail   int            `json:"parity_fail"`
	DroppedOrig  int            `json:"dropped_originals"`
	DroppedPar   int            `json:"dropped_parities"`
	CorruptPar   int            `json:"corrupted_parities"`
	BytesOrig    int64          `json:"bytes_orig"`
	BytesParity  int64          `json:"bytes_parity"`
	InitialDgram int            `json:"initial_datagrams"`
	// C1 배선 확인용: 서버 회신을 몇 번 받았고 마지막 내용이 무엇인가.
	FbRecv      int  `json:"fb_recv"`
	FbMagicSeen int  `json:"fb_magic_seen"`
	RxCalls     int  `json:"rx_calls"` // fecConn.ReadFrom 이 실제로 불린 횟수
	FbWaits     int  `json:"fb_waits"` // waitFeedback 을 부른 횟수
	FbRxOrig    int  `json:"fb_rx_orig"`
	FbRxPar     int  `json:"fb_rx_parity"`
	FbRxRetx    int  `json:"fb_rx_retx"`
	FbRawOrig   int  `json:"fb_raw_orig"`
	FbRawPar    int  `json:"fb_raw_parity"`
	FbTruncated bool `json:"fb_truncated"`
	FbRecov     int  `json:"fb_recovered"`
	// 첫 비행만 따로. 이것이 증폭 예산을 정하는 양이고, 용량 정리의 k 다.
	// 연결 전체의 Initial 을 세면 뒤따르는 ACK 용 Initial 이 섞여 k 가 흐려진다.
	FirstFlightDgrams int   `json:"first_flight_datagrams"`
	FirstFlightBytes  int64 `json:"first_flight_bytes"`
	// 🩸 p13 (2026-08-20). 패리티도 첫 비행 몫만 따로 센다. BytesParity 는
	// 연결 전체의 합이라 **뒤따르는 ACK 비행의 패리티까지 섞인다** - 그 몫은
	// 서버의 첫 응답보다 한 왕복 늦게 도착하므로 증폭 예산과 무관한데,
	// p2 가 이 합계를 client_bytes_total 로 써서 FEC 팔 임계 예측이
	// 4,000~8,000 B 씩 빗나갔다(첫 비행 패리티만 세면 §2.6 의 B_eff 구간에
	// 정확히 든다). 예산 회계에는 이 두 필드를 써야 한다.
	FirstFlightParity      int    `json:"first_flight_parity_dgrams"`
	FirstFlightParityBytes int64  `json:"first_flight_parity_bytes"`
	Layout                 string `json:"layout"`
	Lead                   int    `json:"lead"`
	FirstFlightLeadDgrams  int    `json:"first_flight_lead_dgrams"`
	LaterParitySent        int    `json:"later_parity_sent"`
}

type fecConn struct {
	countConn
	mode        string // off | buf | fec
	m           int
	parityDelay time.Duration
	// expectK: 비행이 데이터그램 몇 개인지 미리 알면 타이머를 기다릴 필요가
	// 없다. 그만큼 모이는 즉시 내보낸다. 0 이면 타이머만 쓴다.
	// 이 값은 s1 단계에서 실측한 자연 k 를 그대로 넣어 준다 - 추정이 아니다.
	expectK int
	// 결정적 소거 주입 (검증 전용). -1 이면 아무것도 안 한다.
	// 첫 비행에만 적용한다 - 뒤따르는 ACK 비행까지 건드리면 무엇 때문에
	// 무엇이 벌어졌는지 알 수 없게 된다.
	dropInitial   map[int]bool
	dropParity    int
	corruptParity int

	// dumpPath: 첫 비행의 원본 데이터그램을 그대로 떨궈 둔다. 나중에
	// Initial 키로 복호해서 CRYPTO 바이트와 PADDING 바이트를 **실측**한다.
	// 용량 정리의 C 와 h 를 추정이 아니라 측정으로 넣기 위한 것이다.
	dumpPath string

	// C1: 서버 수신 회신. onFeedback 이 있으면 받는 즉시 부른다.
	onFeedback func(fbRec)
	fbLast     *fbRec
	fbCount    int
	ffOrigCRC  []uint32
	ffParCRC   []uint32

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
	h := parseLongHdr(b)
	isInitial := h.ok && h.typ == 0
	if isInitial {
		c.mu.Lock()
		if c.txFinal {
			c.mu.Unlock()
			return 0, net.ErrClosed
		}
		c.txWG.Add(1)
		c.stats.InitialDgram++
		c.stats.BytesOrig += int64(len(b))
		c.mu.Unlock()
		defer c.txWG.Done()
	}
	if !isInitial {
		c.flushFlight() // Initial 이 아닌 것이 나오면 비행이 끝난 것이다
		return c.PacketConn.WriteTo(b, addr)
	}
	// off 모드도 **비행 구조는 기록한다.** 자연 k 와 패딩은 FEC 와 무관하게
	// 재야 하는 값이고, 기준선 팔에서도 같은 계측이 나와야 두 팔을 비교할 수
	// 있다. 다만 전송은 손대지 않고 즉시 내보낸다.
	var immediate int
	var ierr error
	if c.mode == "off" {
		// off 모드도 결정적 소거를 받는다. 기준선이 실제로 아프다는 것을
		// 보여야 FEC 팔의 개선이 의미를 갖는다.
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

	// 🩸 여기서 원본을 **버퍼에 담는다.** 1차 설계에서는 원본을 즉시 내보내고
	// 패리티만 늦게 붙였는데, 그러면 패리티가 마지막 원본보다 늦게 도착한다.
	// quic-go 의 run loop 는 복호에 실패한 패킷에 대해
	//     if !wasProcessed { continue }
	// 로 빠져나가므로(connection.go 669행), 우리 패리티가 증폭 예산을 올려도
	// **송신이 깨어나지 않는다.** 실제로 그래서 cert 6000/9500 에서 70% 가
	// 2-RTT 로 남았다. 순서를 [원본 0..k-2, 패리티, 원본 k-1] 로 바꿔서
	// 마지막에 복호 가능한 패킷이 오게 하면 그 패킷이 송신을 깨우고, 그때는
	// 예산에 패리티 몫이 이미 들어 있다.
	cp := append([]byte(nil), b...)
	c.mu.Lock()
	if len(c.flight) == 0 {
		c.flightID++
		c.dcid = append([]byte(nil), h.dcid...)
		c.scid = append([]byte(nil), h.scid...)
		c.peer = addr
		c.curLater = c.v3() && c.srvBig
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

// ReadFrom 은 받은 바이트를 센다. 이 수가 곧 **서버 비행 크기 관측값**이고,
// 폐루프 정책이 n_rtt 를 예측하는 데 쓰는 유일한 입력이다.
// 🩸 이걸 안 감싸서 처음에는 S=0 이 나왔고, 정책이 아무 근거 없이 골랐다.
func (c *fecConn) ReadFrom(b []byte) (int, net.Addr, error) {
	for {
		n, addr, err := c.PacketConn.ReadFrom(b)
		if err != nil || n <= 0 {
			return n, addr, err
		}
		// 🩸 2026-09-07 감사 - 서버 회신(C1 피드백, ~31 B)은 서버 비행 바이트가
		//    아니다. 세면 -feedback 팔의 srv_bytes 만 +31 B 라 S 관측이 갈린다.
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
		// C1: 서버의 수신 회신이면 여기서 걷어낸다. QUIC 스택에 넘기면
		// AEAD 실패로 조용히 버려지긴 하지만, 넘기지 않는 편이 명확하고
		// 스택의 통계도 안 흐린다.
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
			continue // 다음 데이터그램을 읽는다
		}
		return n, addr, err
	}
}

// waitFeedback 은 서버 수신 회신이 올 때까지 최대 d 만큼 기다린다.
//
// 왜 기다려야 하나: 이 테스트베드는 연결마다 UDP 소켓을 새로 만들고
// 핸드셰이크 직후 닫는다. 그런데 회신은 서버가 클라이언트의 Handshake 를
// 받은 뒤에 보내므로(증폭 예산을 안 쓰려고) 약 1 RTT 늦게 도착한다 —
// 소켓이 이미 닫혀 있으면 못 받는다(실측: 서버가 30/30 보냈는데 클라 수신 0).
//
// **실제 클라이언트는 핸드셰이크 후에도 연결을 유지하므로 이 문제가 없다.**
// 즉시 닫는 우리 쪽이 인위적이다. HCT 는 이 대기 전에 이미 찍히므로
// 측정값에는 영향이 없다(c1_smoke 의 음성 대조가 그것을 확인한다).
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

// lastFeedback 은 이 연결에서 받은 마지막 서버 회신을 준다(없으면 nil).
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

// flushFlight 는 모아 둔 비행을 순서까지 정해 내보낸다.
func (c *fecConn) flushFlight() {
	c.mu.Lock()
	if c.txFinal {
		c.mu.Unlock()
		return
	}
	fl := c.flight
	dcid := c.dcid
	scid := c.scid
	peer := c.peer
	fid := c.flightID
	later := c.curLater
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
	c.mu.Unlock()
	defer c.txWG.Done()

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
	sendMode := c.mode // off = 이미 보냈다, buf = 원본만, fec = 패리티까지
	c.mu.Unlock()

	send := func(d []byte) error {
		_, err := c.PacketConn.WriteTo(d, peer)
		if err == nil {
			c.countTx(len(d))
		}
		return err
	}

	if sendMode == "off" {
		return // 원본은 WriteTo 에서 이미 나갔다. 여기서는 기록만 했다.
	}
	// 결정적 소거: 이 원본을 보내지 않는다. 패리티 계산에는 이미 들어갔다.
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
		// 대조군 'buf': 패리티 없이 버퍼링만 한다. 버퍼링 자체의 비용을
		// FEC 의 효과에서 떼어내기 위한 팔이다.
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
			// 심볼 한가운데 한 바이트를 뒤집는다. CRC 가 걸러 내야 한다.
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
			if c.m-full >= 1 {
				emit(0, mk3(0, 1, 0, rsEncode(padded, 1, size)[0]))
			}
			return
		}
		pars := rsEncode(padded, c.m, size)
		for j := 0; j < lead; j++ {
			emit(j, mk3(j, c.m, lead, pars[j]))
		}
		for i := 0; i < k; i++ {
			sendOrig(i, fl[i])
		}
		for j := lead; j < c.m; j++ {
			emit(j, mk3(j, c.m, lead, pars[j]))
		}
		return
	}
	pars := rsEncode(padded, c.m, size)

	// 🩸 패리티를 어디에 끼울지가 **두 이득 중 무엇을 받을지**를 정한다.
	// 두 이득은 하나의 패리티로 동시에 가질 수 없다.
	//
	//  (1) 증폭 신용 - 패리티 바이트가 예산에 계상되려면 **복호 가능한
	//      마지막 패킷보다 먼저** 도착해야 한다. quic-go 의 run loop 가
	//      `if !wasProcessed { continue }` 로 빠지기 때문에(connection.go
	//      669행), 늦게 온 복호 불가 패킷은 예산만 올리고 송신을 못 깨운다.
	//
	//  (2) 손실 복구 - 복구본을 스택에 넣으려면 **패리티를 대신 버려야**
	//      한다. 안 그러면 도착하지도 않은 바이트가 예산에 들어가 RFC 9000
	//      8.1 의 3배가 4.5배가 된다. 버릴지 말지는 패리티가 도착한 시점에
	//      정해야 하고, 그러려면 패리티가 **원본들보다 뒤에** 와야 한다.
	//
	// 그래서 m 으로 갈라 쓴다.
	//   m = 1 : [원본..., 패리티]           복구만
	//   m >= 2: [패리티0, 원본..., 패리티1..] 앞의 것이 신용, 뒤의 것이 복구
	//           수신 바이트가 두 몫이므로 뒤의 것을 버려도 회계가 맞는다.
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
	c.flight = nil
	c.mu.Unlock()

	return c.snapshot()
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
	s.Layout = c.layoutName()
	s.Lead = c.firstLead()
	return s
}

// ------------------------------------------------------------ 서버 쪽 FEC
type serverStats struct {
	Originals int `json:"originals"`
	Parities  int `json:"parities"`
	Recovered int `json:"recovered"`
	// 🩸 2026-08-28 (2 단계 감사) - **비행당 복구가 한 번뿐인지 보는 계수.**
	//    Recovered 는 복원한 **원본 개수**라 한 번에 여럿을 세므로,
	//    "같은 비행을 두 번 풀었다"를 못 가른다. 그 결함이 실제로 있었다
	//    (뒤따르는 패리티가 m-1 개로 늘면서 재진입이 열렸다). 사건 수를
	//    따로 세면 fr.done 가드가 살아 있는지 시험 하나로 확인된다.
	RecoverEvents int `json:"recover_events"`
	// 🩸 2026-08-28 (2 단계 감사) - **아직 안 온 원본을 소거로 오해한 복구.**
	//    뒤따르는 패리티는 원본보다 뒤에 보내지만 망이 재정렬하면 먼저 닿을
	//    수 있고, 그때 서버는 "안 왔다"와 "잃었다"를 구분할 수단이 없다.
	//    복원본이 원본과 비트 단위로 같아 안전에는 문제가 없지만
	//    (회계 불변식도 안 깨진다) **Recovered 지표는 부푼다** - p3·p13 이
	//    그 값을 읽으므로 따로 세어 두지 않으면 조용히 섞인다.
	//    netem 에 재정렬을 안 걸므로 지금 실측에서는 0 이어야 한다.
	PrematureRecover       int   `json:"premature_recovered"`
	RecoverFail            int   `json:"recover_crc_fail"`
	LateRecover            int   `json:"late_recovered"`
	RecoverRefused         int   `json:"recover_refused_by_accounting"`
	CreditParities         int   `json:"credit_parities"`
	CreditParitiesV3       int   `json:"credit_parities_v3"`
	Unrecover              int   `json:"unrecoverable_seen"`
	BytesIn                int64 `json:"bytes_in"`
	BytesToStack           int64 `json:"bytes_to_stack"`
	ConnAcctDropped        int   `json:"conn_acct_dropped"` // connAcctCap 초과로 못 센 연결
	ConnAcctUnmappedRX     int   `json:"conn_acct_unmapped_rx"`
	ConnAcctUnmappedTX     int   `json:"conn_acct_unmapped_tx"`
	ConnAcctUnmappedStack  int64 `json:"conn_acct_unmapped_stack_bytes"`
	ConnAcctAliasConflicts int   `json:"conn_acct_alias_conflicts"`
	ConnAcctAliasDropped   int   `json:"conn_acct_alias_dropped"`
	// C1 진단: 롱헤더 타입별 수신 수와 회신 송신 수. 배선이 어디서 끊겼는지
	// 추측하지 않고 자료로 보려고 둔다.
	HdrInitial     int `json:"hdr_initial"`
	HdrHandshake   int `json:"hdr_handshake"`
	HdrShort       int `json:"hdr_short"`
	FbSentN        int `json:"fb_sent"`
	FbWriteErr     int `json:"fb_write_err"`
	HdrCoalescedHS int `json:"hdr_coalesced_hs"`
}

type recvItem struct {
	dcid string
	crc  uint32
	data []byte
	addr net.Addr
	t    time.Time
}

type flightRec struct {
	fb      *fecBlock
	dcid    string
	addr    net.Addr
	acct    *connAcct
	created time.Time
	done    bool
	// 🩸 2026-08-28 (2 단계 감사) - 이 비행에서 **복원해 낸** 원본의 CRC.
	//    나중에 진짜 원본이 도착하면(= 잃은 게 아니라 늦게 온 것이었다)
	//    여기 걸려서 PrematureRecover 로 센다. flightTTL 에 같이 만료된다.
	recCRC map[uint32]bool
	// 🩸 2026-08-28 (2 단계) - **뒤따르는 패리티 심볼을 모은다.**
	//    옛 구조는 마지막 패리티 하나만 들고 있어 복구 능력이 소거 1 개로
	//    묶여 있었다(신레오 2026-08-27 보고). 뒤따르는 패리티는 원본보다
	//    **뒤에** 오므로 도착 시점에 소거 개수를 이미 알 수 있고, 그래서
	//    다음처럼 즉시 판정한다:
	//      소거 0 개  -> 신용으로 스택 (지금과 같다)
	//      소거 1 개  -> 이 패리티로 복구하고 복원본을 스택
	//      소거 2 개+ -> **보류**하고 다음 뒤따르는 패리티를 기다린다
	//    보류는 소거가 이미 2 개 이상일 때만 일어난다 - 확률 ~p^2 이라
	//    무손실 대량(약 96%)에서는 아무것도 안 바뀐다. 그래서 증폭 신용을
	//    내주지 않는다.
	//
	//    ⚠️ 선행 패리티(m>=2 의 index 0)는 **여기 넣지 않는다.** 원본보다
	//       먼저 오므로 그것으로 복구를 시도하면 아직 안 온 원본을
	//       "소거됐다"로 오해한다 - 실제로 그렇게 오작동한 적이 있다.
	syms      map[int][]byte
	heldBytes int64
	// CRC 로 한 번 걸러진 비행은 다시 시도하지 않는다. 매 원본 도착마다
	// 같은 실패를 반복하면 카운터만 부풀고 얻는 것이 없다.
	poisoned bool
}

type pendingPkt struct {
	data []byte
	addr net.Addr
	acct *connAcct
}

// ------------------------------------------------- 연결별 회계 (p13, 2026-08-20)
//
// 명세 §2.6 의 B_eff("서버가 응답 비행을 만들기로 결정한 시점까지 도착한
// 클라이언트 바이트")를 **직접** 재기 위한 계측이다. 그전까지 countConn 은
// 프로세스 전체 합계만 세서 (1) 연결끼리 섞이고 (2) 송신을 아예 안 가로채
// "첫 송신 시점"이라는 것 자체가 없었다 - B_eff 재해석이 사후 가설에
// 머문 이유다.
//
// UDP source ports can be reused while older packets are still in flight. Identify
// an Initial by its (DCID, SCID) pair, then follow visible client/server CIDs.
// Unknown or ambiguous CIDs remain explicitly unaccounted; never guess by address.
// Encrypted NEW_CONNECTION_ID frames cannot be observed at this PacketConn layer.
//
// 두 종류의 바이트를 다 센다.
//
//	phys  물리적으로 도착한 바이트 (원본/패리티 분리)
//	stack QUIC 스택에 넘긴 바이트 - quic-go 의 증폭 예산이 실제로 세는 양.
//	      복구가 일어나면 패리티 대신 복구본이 넘어가므로 phys 와 갈린다.
//	      무손실 시행에서는 둘이 같다.
type connAcct struct {
	InitialDCID string `json:"initial_dcid"`
	ClientSCID  string `json:"client_scid"`
	FirstPeer   string `json:"first_peer"`
	LastPeer    string `json:"last_peer"`
	PeerChanges int    `json:"peer_changes"`
	aliasCount  int
	FirstRxNs   int64 `json:"first_rx_ns"`
	FirstTxNs   int64 `json:"first_tx_ns"`
	RxDgrams    int   `json:"rx_dgrams"`
	RxBytes     int64 `json:"rx_bytes"`
	RxOrig      int64 `json:"rx_orig_bytes"`
	RxParity    int64 `json:"rx_parity_bytes"`
	// 🩸 2026-08-23 (C1) - 위 둘은 **바이트**다. 피드백은 심볼 **개수**를
	//    보내야 하므로 따로 센다. 첫 비행 몫만 세려고 Handshake 를 본
	//    시점에 잠근다(FbSent).
	RxOrigN        int      `json:"rx_orig_n"`
	RxParityN      int      `json:"rx_parity_n"`
	RxCRC          []uint32 `json:"rx_crc"`
	RxCRCTruncated bool     `json:"rx_crc_truncated"`
	RecovN         int      `json:"recov_n"`
	CreditN        int      `json:"credit_n"`
	FbSent         bool     `json:"fb_sent"`
	Stack          int64    `json:"stack_bytes"`
	TxDgrams       int      `json:"tx_dgrams"`
	TxBytes        int64    `json:"tx_bytes"`
	// 서버가 첫 데이터그램을 내보내는 순간의 스냅숏. 이것이 B_eff 다.
	BeffStack  int64 `json:"beff_stack"`
	BeffPhys   int64 `json:"beff_phys"`
	BeffOrig   int64 `json:"beff_orig"`
	BeffParity int64 `json:"beff_parity"`
	BeffCredit int   `json:"beff_credit"`
	// 송신 타임라인: n 번째 송신 직전의 stack 누적 바이트, 그 송신의 크기,
	// 그리고 송신 시각(ns). 첫 비행 버스트가 몇 데이터그램인지(= 명세 §2.5 의
	// c 를 확정할 n)와, 버스트 도중에 패리티가 도착해 예산이 자랐는지가 여기서
	// 그대로 보인다. 시각이 있어야 첫 비행과 꼬리(Finished 이후 응답)를 가를 수
	// 있다 - 1-RTT 조건에서 비행은 첫 송신 후 1 ms 안에 끝나고 꼬리는 RTT 뒤에
	// 온다. 바이트 성장만으로 가르면 패리티 도착과 ACK 도착이 둘 다 ~1.3 KB 라
	// 구별되지 않는다.
	TxRxTimeline []int64 `json:"tx_rx_timeline"`
	TxSizes      []int   `json:"tx_sizes"`
	TxNs         []int64 `json:"tx_ns"`
}

const connAcctCap = 4096   // 폭주 방지. 넘으면 새 연결은 세지 않고 개수만 남긴다.
const connTimelineCap = 40 // 서버 첫 비행(<=13 패킷) + 꼬리를 담고도 남는다.

// 🩸 연결마다 flight id 가 1 부터 다시 시작한다. 처음에는 비행 기록을
// flight id 만으로 키잉했는데, 그러면 **서로 다른 연결의 비행이 같은 칸에
// 겹치고** 오래된 k=1 비행이 영원히 남아 새 원본이 올 때마다 "복구"로
// 세어졌다. 60 연결에서 복구가 109 건으로 부풀었다.
// 그래서 (DCID, flight, index) 로 키잉하고, CRC 대조도 같은 DCID 안에서만
// 하고, 오래된 것은 시간으로 버린다. 1차 연구의 1바이트 flight id
// 랩어라운드 사고와 같은 종류의 실수다.
// 🩸 두 수명이 어긋나면 유령 복구가 생긴다.
//
// 비행 기록이 원본보다 오래 살면, 원본이 recent 에서 밀려난 뒤에도
// tryLate 가 그 비행을 다시 들여다보고 "원본이 하나 없다" 고 오판한다.
// 그러면 손실이 0 인데도 복구를 시도해서, 운 좋으면 유령 복구(중복
// 데이터그램을 스택에 주입)를, 운 나쁘면 CRC 실패를 만든다.
//
// 실제로 그랬다. n<=60(4 초)이면 아무것도 만료되지 않아 깨끗했는데,
// n=200(13 초)에서 손실 0 인데 복구 352 건 / CRC 실패 266 건이 나왔다.
// 규모를 키우기 전까지 안 보이는 종류의 결함이다.
//
// 그래서 **원본이 비행 기록보다 확실히 오래 살게** 잡는다.
const flightTTL = 1 * time.Second
const recentTTL = 3 * time.Second
const recentCap = 512

// min8 은 uint8 로 넣기 전에 255 로 자른다. k<=3, m<=2 라 실제로는 안 걸리지만
// 조용한 오버플로가 나면 손실률 추정이 통째로 틀어지므로 못박아 둔다.
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
	feedback bool // C1: 수신 회신을 보낼지 (음성 대조용으로 끌 수 있다)

	mu           sync.Mutex
	recent       []recvItem
	flights      map[string]*flightRec
	pending      []pendingPkt
	pendingBytes int64 // 아직 안 넘긴 복구본의 바이트 (회계 예약분)
	// 🩸 2026-08-28 (2 단계) - 소거가 2 개 이상이라 **보류한** 뒤따르는
	//    패리티의 바이트. 아직 스택에 안 넘겼으므로 불변식의 왼쪽에
	//    들어가지 않는다. 복구가 끝나면 쓰인 만큼은 복원본으로 대체되고
	//    남은 것은 신용으로 풀린다.
	heldBytes  int64
	conns      map[string]*connAcct
	clientCIDs map[string]*connAcct // server destination CIDs; nil means ambiguous
	serverCIDs map[string]*connAcct // client destination CIDs; nil means ambiguous
	stats      serverStats
}

const connAliasCap = 16

// Explicitly matches quic-go v0.61.0's existing default. A fresh client Initial
// DCID is at least 8 bytes; server-issued CIDs here are always 4 bytes.
const serverConnIDLength = 4

// Both CID namespaces are bounded by connAcctCap * connAliasCap. Collisions are
// marked ambiguous instead of silently assigning another connection's packets.
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

// acctLocked follows visible CIDs for this testbed's 4-byte server CID policy.
// The Initial (DCID, SCID) pair separates even repeated client SCIDs. Later
// long headers can reveal new server CIDs while keeping the client SCID.
// Zero-length, ambiguous and unseen short-header CIDs remain unmapped.
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
			// A known server source CID also disambiguates a reused client CID.
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

// stackLocked 는 "스택에 넘긴 바이트"를 전역과 연결 양쪽에 계상한다.
// quic-go 의 증폭 예산이 실제로 세는 것이 이 양이므로, B_eff 의 정본도 이쪽이다.
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

// WriteTo 가 서버 송신을 가로챈다. 이 연결로 나가는 **첫** 데이터그램 직전의
// 수신 누적이 곧 B_eff 다(명세 §2.6). quic-go 는 예산 검사를 패킷을 만들기
// 전에 하므로, 첫 송신 시점의 수신 누적이 첫 응답 비행의 예산을 정한 값이다.
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
			ca.BeffCredit = ca.CreditN
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
	// 🩸 2026-08-28 (2 단계 감사) - **잃은 게 아니라 늦게 온 것이었나.**
	//    뒤따르는 패리티는 원본보다 뒤에 보내지만 망이 재정렬하면 먼저
	//    닿을 수 있다. 그 순간 서버는 "안 왔다"와 "잃었다"를 구분할 수단이
	//    없어 소거로 보고 복구해 버린다. 복원본이 원본과 비트 단위로 같아
	//    안전에는 문제가 없고 회계 불변식도 안 깨지지만, **Recovered 가
	//    부푼다.** p3·p13 이 그 값을 읽으므로 따로 센다.
	//    (netem 에 재정렬을 안 거는 지금 실측에서는 0 이어야 한다 - 0 이
	//     아니면 그 회차의 복구 계수를 그대로 믿으면 안 된다는 신호다.)
	for _, fr := range s.flights {
		if fr.dcid == dc && fr.recCRC[cr] {
			s.stats.PrematureRecover++
			break
		}
	}
	s.mu.Unlock()
	s.tryLate()
}

// tryRecoverLocked 는 이 비행에서 소거 하나를 복구할 수 있으면 복구한다.
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
		// 전부 도착했다. **다시 볼 필요가 없으므로 여기서 닫는다.**
		// 닫지 않으면 나중에 원본이 recent 에서 밀려났을 때 같은 비행을
		// 다시 보고 "하나 없다" 고 오판한다.
		fr.done = true
		return nil
	}
	// 🩸 2026-08-28 (2 단계) - **소거 e 개를 모은 패리티 e 개로 푼다.**
	//    옛 코드는 여기서 `len(missing) > 1` 이면 무조건 포기했다. 그래서
	//    복구 능력이 m 과 무관하게 **1 개로 고정**돼 있었고, m 을 늘려도
	//    "패리티가 살아남을 확률"만 올랐다(신레오 2026-08-27 보고).
	//    이제 모아 둔 뒤따르는 패리티 수만큼 풀 수 있다.
	if len(missing) > len(fr.syms) {
		if count {
			s.stats.Unrecover++
		}
		return nil // 패리티가 모자란다. **닫히며** 실패한다.
	}
	recs := recoverMany(fb.k, fb.m, missing, have, fr.syms, fb.symLen)
	if recs == nil {
		return nil
	}
	// 복원본을 CRC 로 자가 확인한 뒤 하나로 이어 돌려준다. 호출부는 지금
	// 한 번에 하나만 스택에 넘기므로, 여러 개면 나머지는 pending 에 쌓는다.
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
	// ⚠️ **부작용을 두지 않는다.** 회계가 허락할지는 호출부가 정하므로,
	//    여기서 Recovered 를 올리거나 pending 에 넣으면 거절된 복구까지
	//    세어져 예약 바이트가 부풀고 불변식이 깨진다. 실제로 그렇게
	//    깨졌다(2026-08-28). 판정과 기록을 한 곳에 모은다.
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
		s.pendingBytes += int64(len(rec)) // 예약: 넘길 때까지 잡아 둔다
		s.stats.LateRecover++
	}
}

func (s *decodeConn) ReadFrom(b []byte) (int, net.Addr, error) {
	// 🩸 2026-08-28 (2 단계 감사) - **보류한 패리티는 삼킨다.** 자세한 근거는
	//    아래 보류 분기 주석에 있다. 여기로 되돌아와 다음 데이터그램을 읽는다.
again:
	s.mu.Lock()
	if len(s.pending) > 0 {
		p := s.pending[0]
		s.pending = s.pending[1:]
		s.pendingBytes -= int64(len(p.data))
		s.stackLocked(p.acct, len(p.data))
		s.mu.Unlock()
		n := copy(b, p.data)
		return n, p.addr, nil
	}
	s.mu.Unlock()

	n, addr, err := s.PacketConn.ReadFrom(b)
	if err != nil {
		return n, addr, err
	}
	s.countRx(n)
	// 분류를 회계보다 먼저 한다 - 연결별 회계가 원본/패리티를 나눠 세야
	// B_eff 의 "패리티 몫"이 직접 보인다(p13). off 모드는 패리티가 존재하지
	// 않는 팔이므로 파싱을 건너뛰고 전부 원본으로 센다.
	var fb *fecBlock
	if s.mode != "off" {
		fb = parseFecBlock(b[:n])
	}
	// C1: 클라이언트의 두 번째 비행(Handshake) 이 오면 첫 비행 회계를 잠그고
	// 회신한다. 이 시점에는 주소 검증이 끝나 증폭 한도가 해제돼 있으므로
	// 회신 바이트가 예산을 먹지 않는다.
	hs := parseLongHdr(b[:n])
	isHandshake := hasHandshake(b[:n])
	var fbOut []byte
	s.mu.Lock()
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
			// Initial(typ 0) 만 첫 비행 원본으로 센다. Handshake 이후의
			// 데이터그램까지 세면 k 가 흐려진다.
			// 🩸 두 번째 비행(Initial ACK + Handshake 코얼레스)도 첫
			//    패킷이 Initial 이라 그냥 세면 k 가 부풀었다(k=2 인데 3).
			//    Handshake 가 섞인 데이터그램은 첫 비행이 아니다.
			if !ca.FbSent && hs.ok && hs.typ == 0 && !isHandshake {
				ca.RxOrigN++
			}
		}
		// Record physical arrivals before the decoder can replace a parity with
		// a reconstructed original. Initial retransmissions remain identifiable.
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
		// countConn 을 거치지 않는다 - 이 바이트는 첫 비행 회계 밖이고,
		// 섞으면 B_eff·s0 측정이 오염된다.
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
		// 🩸 2026-08-28 **회계 순서 수리 (차단 결함).**
		//    옛 순서는 `noteOriginal` -> `stackLocked` 였다. noteOriginal 은
		//    tryLate 를 부르고, tryLate 는 불변식
		//        BytesToStack + pendingBytes + len(rec) <= BytesIn
		//    을 본다. 그런데 이 데이터그램의 n 바이트는 위(:1501)에서
		//    **BytesIn 에 이미 더해졌고 BytesToStack 에는 아직 안 들어갔다.**
		//    그래서 가드가 **방금 도착한 원본의 바이트를 두 번 내준다** -
		//    늦은 복구 한 번마다 정확히 W(=1280 B) 만큼 신용이 부풀고,
		//    RFC 9000 8.1 의 3 배 규칙에 따라 서버 비행이 3,840 B 늘어난다.
		//    클라이언트가 보낸 적 없는 바이트다.
		//
		//    최소 재현: k=2 · m=1 · **손실 0** · 도착 순서 [P, O0, O1].
		//    독립 하네스 487 개 순열에서 178 건(36.6%) 위반, 초과분은
		//    전부 정확히 1280 B.
		//
		//    ⚠️ 이 수리는 아래 parseFecBlock 의 심볼 복사보다 **먼저**
		//       와야 한다. 지금은 심볼이 호출자 버퍼를 가리키는 별칭이라
		//       내용이 덮여 CRC 가 걸러 주는데, 그 별칭이 **우연한
		//       안전망**으로 이 결함을 가리고 있다. 복사만 먼저 넣으면
		//       확률적 CRC 실패가 **결정적 불변식 위반**으로 바뀐다.
		s.mu.Lock()
		s.stackLocked(ca, n)
		s.mu.Unlock()
		s.noteOriginal(b[:n], addr)
		return n, addr, nil
	}

	dc := dcidOf(b[:n])
	s.mu.Lock()
	s.stats.Parities++
	// 역할 분리를 코드에 못박는다. 마지막 index 만 복구용이고, 그 앞의 것들은
	// 순전히 증폭 신용용이라 복구에 쓰지 않는다. 신용 패리티는 원본보다 먼저
	// 도착하므로, 그것으로 복구를 시도하면 손실이 없는데도 "마지막 원본이
	// 아직 안 왔다"를 소거로 오해한다 - 실제로 그렇게 오작동했다.
	// 🩸 2026-08-28 (2 단계) - **선행 패리티만 신용 전용이다.**
	//    m>=2 의 index 0 은 원본보다 **먼저** 나가므로(flushFlight) 그것으로
	//    복구를 시도하면 아직 안 온 원본을 소거로 오해한다. 그건 그대로 둔다.
	//    나머지(뒤따르는 패리티)는 원본보다 뒤에 오므로 도착 시점에 소거
	//    개수를 이미 알 수 있고, 그래서 아래에서 즉시 판정한다.
	if s.creditLocked(ca, fb, n) {
		s.mu.Unlock()
		return n, addr, nil
	}
	// 🩸 비행 하나에 기록 하나. 옛 열쇠는 `index` 를 포함해 뒤따르는 패리티
	//    마다 따로 기록이 생겼고, 그러면 같은 비행을 여러 번 복구해 복원본이
	//    **중복 주입**될 수 있다. 심볼은 한 기록에 모은다.
	key := fmt.Sprintf("%x|%d", dc, fb.flight)
	if s.flights == nil {
		s.flights = map[string]*flightRec{}
	}
	fr := s.flights[key]
	if fr == nil {
		fr = &flightRec{fb: fb, dcid: dc, addr: addr, acct: ca, created: time.Now(),
			syms: map[int][]byte{}}
		s.flights[key] = fr
	}
	fr.fb = fb
	// 🩸 2026-08-28 (2 단계 감사) - **결론이 난 비행은 다시 풀지 않는다.**
	//    tryLate 는 진작부터 `fr.done || fr.poisoned` 를 걸렀는데(위 tryLate)
	//    이 경로만 안 걸렀다. 복원본은 noteOriginal 을 안 거치므로 s.recent 에
	//    안 들어가고, tryRecoverLocked 는 missing 을 s.recent 로만 계산한다.
	//    그래서 **이미 복원한 원본이 계속 「없다」고 보인다.**
	//      k=2 m=3, O0 하나만 유실, 도착 [P0, O1, P1, P2]
	//        P1 -> O0 복원, fr.done=true, Recovered=1
	//        P2 -> missing 이 여전히 [0] -> **O0 을 또 복원** -> Recovered=2
	//      소거 1 개에 복구 2 건, 같은 Initial 이 QUIC 스택에 두 번 올라간다.
	//    2 단계 전에는 복구 경로에 오는 패리티가 마지막 하나뿐이라 재진입이
	//    불가능했다. 뒤따르는 패리티를 m-1 개로 늘리면서 열린 길이다.
	//    결론이 난 비행에 늦게 온 패리티는 그냥 **평범한 신용**이다.
	if fr.done || fr.poisoned {
		s.stackLocked(ca, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	fr.syms[fb.index] = fb.sym
	outs := s.tryRecoverLocked(fr, true)
	// ⚖️ 불변식: 스택에 넘긴 누적 바이트는 **물리적으로 도착한 누적 바이트를
	// 절대 넘지 않는다.** 어기면 RFC 9000 8.1 의 3 배 한도를 우회하는 셈이다.
	if rec := s.settleRecovery(fr, outs); rec != nil {
		// 🩸 2026-09-07 감사 - **복원본을 장부에 안 적고 있었다.** settleRecovery
		//    의 가드는 `BytesToStack + pendingBytes + len(rec) <= BytesIn` 으로
		//    복원본(outs[0])이 곧 적힐 것으로 치는데, 여기서 quic-go 에 넘기면서
		//    아무도 적지 않았다(뒤따르는 복원본 outs[1:] 은 pending 을 거치며
		//    적힌다). 복구가 한 번 날 때마다 BytesToStack·ca.Stack·BeffStack 이
		//    W 만큼 실제로 넘긴 바이트보다 작았고, 회계 자체시험은 `인계 <= 도착`
		//    만 봐서 W 만큼 관대했다(스크래치 시험: k=2·m=1 에서 인계 2400 vs
		//    장부 1200). 넘기는 바이트를 넘기기 전에 적는다.
		s.stackLocked(fr.acct, len(rec))
		s.mu.Unlock()
		m := copy(b, rec)
		return m, addr, nil
	}
	// 🩸 2026-08-28 (2 단계) - **소거가 아직 여럿이면 이 패리티를 보류한다.**
	//    스택에 넣어 버리면 그 바이트가 신용으로 잡혀, 나중에 이 심볼로
	//    복구할 때 복원본까지 넣으면 이중 계상이 된다.
	//
	// 🩸 2026-08-28 (2 단계 감사) - **보류하면 데이터그램도 삼켜야 한다.**
	//    옛 코드는 `return n, addr, nil` 로 패리티를 quic-go 에 그대로
	//    올려보내면서 stackLocked 만 건너뛰었다. 그런데 설계요점 2 가 못박은
	//    대로 **올려보낸 패리티는 quic-go 가 ReceivedBytes 로 세어 3 배 예산을
	//    늘린다.** 즉 저쪽 예산은 커지는데 우리 회계(BytesToStack)는 0 으로
	//    남고, 나중에 settleRecovery 가 그 심볼로 만든 복원본까지 스택에
	//    넣으므로 **같은 수신 바이트가 두 번 신용이 된다.**
	//      k=2 m=1, 손실 0, 도착 [P, O0, O1] (패리티 재정렬)
	//        -> 실제 인계 4,846 B vs BytesIn 3,646 B = 1,200 B 초과
	//        -> RFC 9000 8.1 로 서버 비행이 3,600 B 더 나간다
	//      계기는 BytesToStack 3,600 <= 3,646 만 보므로 「정상」이라 보고한다.
	//    의도는 "이 바이트에 신용을 안 준다"이므로, 맞는 것은 스택을 건너뛰는
	//    게 아니라 **quic-go 에 아예 안 보여 주는 것**이다.
	//
	//    feedOne 은 데이터그램을 돌려주지 않으므로 처음부터 옳았다 - 그래서
	//    자체시험의 도착순서 전수 검사가 이 차이를 **원리적으로 못 봤다.**
	//    아래 [회계-ReadFrom] 검사를 새로 넣은 이유다.
	if len(outs) == 0 && s.pendingErasures(fr) >= 2 {
		fr.heldBytes += int64(n)
		s.heldBytes += int64(n)
		s.mu.Unlock()
		goto again // 삼킨다 - quic-go 는 이 바이트를 보지 못한다
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

// report 는 전역 합계에 연결별 회계를 붙인 스냅숏이다. -stats JSON 의 최상위
// 키는 예전과 같아서(임베드 구조체는 평탄화된다) p2 등 기존 독자는 그대로
// 읽고, p13 만 "conns" 를 본다. 깊은 복사를 해야 한다 - 타임라인 슬라이스를
// 그대로 내보내면 json.Marshal 이 도는 동안 WriteTo 가 append 해서 경합한다.
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

// ------------------------------------------------------------------ 인증서
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

// ------------------------------------------------------------------ 서버
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
		// 실험환경 명세서 5절: 세션 재개 차단.
		// 재개하면 키 교환을 건너뛰어 측정이 무효화된다. 그리고 티켓을
		// 발급하면 NewSessionTicket 이 서버 비행 뒤에 붙어 server_bytes 를
		// 부풀린다 - s0 추정에 직접 섞이는 잡음이다.
		SessionTicketsDisabled: true,
	}
	ln, err := tr.Listen(tlsConf, &quic.Config{
		MaxIdleTimeout:  30 * time.Second,
		KeepAlivePeriod: 0,
		// 명세 5절: Path MTU Discovery 비활성 - 측정 중 패킷 크기 변동 방지.
		DisablePathMTUDiscovery: true,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "quic listen:", err)
		os.Exit(1)
	}
	fmt.Fprintln(os.Stderr, "READY", addr)
	os.Stderr.Sync()

	// 🩸 통계는 주기 기록만으로는 모자란다. 조건 하나가 1 초도 안 걸리는데
	// 500 ms 주기로 쓰면 마지막 갱신이 유실되어 **복구 건수가 실제보다 적게**
	// 보고된다. 실제로 12 회 전부 복구된 조건이 8 회로 보고됐다.
	// 주기를 줄이고, SIGTERM/SIGINT 를 받으면 마지막으로 한 번 더 쓴다.
	// 2026-08-21 - `os.WriteFile` 은 **자르고 나서 쓴다**(비원자적).
	// 100 ms 주기 고루틴과 SIGTERM 핸들러가 뮤텍스 없이 같은 파일을 쓰고,
	// 핸들러가 쓰기 도중 os.Exit(0) 으로 프로세스를 죽일 수 있다. 그러면
	// **잘린 JSON** 이 남고 read_server_stats 가 2 초 내내 파싱에 실패해
	// {} 를 돌려준다 -> `None or 0 == 0` 이라 CRC 검사가 공허하게 통과한다.
	// 2026-08-21 p11 에서 24 팔 중 1 팔이 실제로 그랬다.
	// 임시 파일에 쓰고 rename 한다(같은 디렉터리 -> 원자적). 두 호출도
	// 뮤텍스로 직렬화한다. 저장소의 atomic_write_json 과 같은 규약이다.
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

// ------------------------------------------------------------------ 클라이언트
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
	// 2026-09-07 - quic-go 가 실제로 쓰는 값. -ips 가 1452 를 넘으면 조용히
	// 1452 로 깎이는데 ips_used 는 요청값을 적어 와이어에 없던 W 가 남았다.
	IPSEff        int     `json:"ips_eff"`
	MWhy          string  `json:"m_why,omitempty"`
	SrvBytes      int64   `json:"server_bytes"`
	LossEvt       bool    `json:"loss_event"`
	PathRTTMS     float64 `json:"path_rtt_ms"`
	PathRTTValid  bool    `json:"path_rtt_valid"`
	PathRTTSource string  `json:"path_rtt_source"`
	Layout        string  `json:"layout"`
	Lead          int     `json:"lead"`
	FFLead        int     `json:"first_flight_lead_dgrams"`
	LaterParity   int     `json:"later_parity_sent"`
}

// quic-go v0.61 starts MinRTT/LatestRTT/SmoothedRTT at 100 ms before
// receiving any RTT sample. MeanDeviation starts at zero and the first
// valid sample initializes it to sample/2. Require that evidence rather
// than treating the positive 100 ms default as a measurement. A valid
// sample whose deviation rounds to zero is conservatively omitted.
func measuredPathRTT(stats quic.ConnectionStats) (float64, bool) {
	if stats.MinRTT <= 0 || stats.LatestRTT <= 0 || stats.MeanDeviation <= 0 {
		return 0, false
	}
	return float64(stats.MinRTT) / float64(time.Millisecond), true
}

func recordFinalSendStats(t *trial, agg *clientStats, fin clientStats) {
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
	if agg.FlightSizes == nil {
		agg.FlightSizes = map[string]int{}
	}
	for k, v := range fin.FlightSizes {
		agg.FlightSizes[k] += v
	}
}

func runClient(addr, group string, n int, timeout, gap time.Duration,
	mode string, m int, ips int, parityDelayUs int, expectK int,
	statsPath string, dumpPath string,
	dropInitial map[int]bool, dropParity, corruptParity int,
	cachePath string, mMax, coldM, probeEvery int, uplinkMbps float64,
	feedback bool, layout string, lead int, cache3Path string) {
	gfInit()
	ra, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, "resolve:", err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	var agg clientStats
	agg.FlightSizes = map[string]int{}

	// 폐루프: mode == "auto" 면 목적지 캐시가 m 을 고른다.
	cache := newDestCache(cachePath)
	wSize := ips
	if wSize <= 0 {
		wSize = 1280 // quic-go 기본 InitialPacketSize
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

	for i := 0; i < n; i++ {
		trialM, why := m, ""
		// 이 판에서 실제로 쓸 InitialPacketSize. auto 가 아니면 플래그 그대로.
		trialIPS := ips
		unbiased := true
		fmode := mode
		if mode == "off" {
			// The CLI's default m is irrelevant when no parity is transmitted.
			// Keep m_used faithful to the actual fixed policy in trial records.
			trialM = 0
		}
		if mode == "auto" {
			// 🩸 2026-08-20 v2 이식. 그전에는 m 만 받아서 δ 지렛대를 쓸 수
			// 없었다. 이제 정책이 고른 ips 를 그대로 이 판에 적용한다 -
			// 헤드라인("1 바이트로 왕복 하나")이 정책의 손에서 실현된다.
			trialIPS, trialM, why, unbiased = cache.decide(addr, wSize,
				mMax, coldM, probeEvery, defaultAssumedBurst, cPktDefault,
				maxStepsDefault, quicgoMaxIPS, uplinkMbps)
			if trialM <= 0 {
				fmode = "off" // 정책이 0 을 골랐으면 패리티를 안 보낸다
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
		fc := &fecConn{countConn: countConn{PacketConn: udp}, mode: fmode,
			m:           maxInt(trialM, 1),
			expectK:     expectK,
			dropInitial: dropInitial, dropParity: dropParity,
			corruptParity: corruptParity,
			dumpPath:      dumpPath,
			parityDelay:   time.Duration(parityDelayUs) * time.Microsecond,
			layout:        trialLayout, lead: trialLead}
		tr := &quic.Transport{Conn: fc}

		tlsConf := &tls.Config{
			InsecureSkipVerify: true,
			NextProtos:         []string{"padfec"},
			MinVersion:         tls.VersionTLS13,
			CurvePreferences:   []tls.CurveID{curveFor(group)},
			// 명세 5절: 세션 재개 차단. ClientSessionCache 가 nil 이면 Go 는
			// 재개하지 않지만, **기본값에 기대지 않고** 명시한다.
			ClientSessionCache:     nil,
			SessionTicketsDisabled: true,
		}
		qconf := &quic.Config{
			MaxIdleTimeout:  timeout,
			KeepAlivePeriod: 0,
			Allow0RTT:       false,
			// 명세 5절: Path MTU Discovery 비활성. 켜 두면 연결 도중 quic-go 가
			// MTU 탐침을 보내 데이터그램 크기가 변한다 - countConn 이 세는
			// 바이트가 흔들려 증폭 회계가 오염된다.
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

		// 패리티는 타이머(기본 300 us)로 나가므로, 통계를 찍기 전에 그
		// 타이머가 확실히 돌게 잠깐 기다린다. 이걸 안 하면 마지막 비행의
		// 패리티가 표본에서 들쭉날쭉 빠져 "보낸 개수 < 비행 수"로 보인다.
		// HCT 측정 구간(Dial)은 이미 끝났으므로 측정에는 영향이 없다.
		time.Sleep(3 * time.Duration(parityDelayUs) * time.Microsecond)
		// C1: 회신을 기다린 **뒤** 스냅숏을 찍는다. 순서를 반대로 하면
		// 대기 중에 받은 회신이 통계에 안 잡힌다 - 2026-08-23 에 실제로
		// 그래서 "회신 0 건"으로 오진했다(서버는 20/20 보냈고 파싱도
		// 정상이었다). HCT(el)는 이미 위에서 찍혔으므로 측정에는 영향 없다.
		if feedback && err == nil {
			fc.waitFeedback(200 * time.Millisecond)
		}
		st := fc.snapshot()
		_, _, _, srvBytes := fc.counts()
		hct := float64(el.Microseconds()) / 1000.0
		// 손실 사건 신호.
		//
		// 🩸 처음에는 `InitialDgram > FirstFlightDgrams` 로 봤는데 **항상
		// 참이었다.** 핸드셰이크가 끝난 뒤 클라이언트가 ACK 용 Initial 을
		// 한 번 더 보내기 때문이다. 그래서 손실률 추정이 1.0 에 붙어
		// 정책이 늘 최대 m 을 골랐다.
		//
		// 옳은 신호는 **첫 비행과 같은 크기의 비행이 두 번 이상** 나가는
		// 것이다. ACK 비행은 데이터그램 하나짜리라 섞이지 않는다.
		lossEvt := false
		if k0 := st.FirstFlightDgrams; k0 > 1 {
			if st.FlightSizes[fmt.Sprint(k0)] > 1 {
				lossEvt = true
			}
		} else if st.FirstFlightDgrams == 1 {
			// k=1 이면 비행 크기로는 구별이 안 되므로 총 Initial 수로 본다.
			// 정상은 CH 1 + ACK 1 = 2 개다.
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
			PathRTTSource: "unavailable",
			Layout:        st.Layout, Lead: st.Lead,
			FFLead: st.FirstFlightLeadDgrams, LaterParity: st.LaterParitySent}
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
		// 🆕 C1/C2 - 심볼 단위 관측. auto 가 아니어도 캐시는 갱신한다
		// (고정팔로 도는 동안 배운 것도 다음 auto 연결에 쓸 수 있다).
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
				// C2: 회신이 없다. 이유가 둘이라 구분해야 한다.
				//   (a) 첫 비행 전멸 -> 서버가 아무것도 못 받았다
				//   (b) 회신 자체가 유실 -> 연결은 정상
				// (b) 를 손실로 세면 캐시가 비관 쪽으로 틀어진다. 그래서
				// **연결이 실패했거나 HCT 가 PTO 수준일 때만** 전멸로 본다.
				// 그 조건이 아니면 아무것도 적립하지 않는다 - 생존 편향이
				// 조금 남지만, 없는 손실을 지어내는 것보다 낫다.
				cache.observeSymbolsWhy(addr, nSent, nSent, hct, true)
			}
		}
		var obs3Info p3ObsInfo
		var obs3After float64
		var obs3Err error
		if mode == "auto3" {
			obs3Info, obs3After, obs3Err = c3.observePred(addr, plan3.Action, plan3.jPred(), hct, err == nil,
				st.FirstFlightDgrams, float64(srvBytes), t.PathRTTMS, t.PathRTTValid,
				wSize, uplinkMbps, cPktDefault)
			if obs3Err != nil {
				fmt.Fprintln(os.Stderr, "auto3 observe:", obs3Err)
			}
		}
		tr.Close()
		udp.Close()
		fin := fc.finalSendStats()
		recordFinalSendStats(&t, &agg, fin)
		if mode == "auto3" {
			row := auto3Row(t, plan3, obs3Info, obs3Err, obs3After)
			enc.Encode(&row)
		} else {
			enc.Encode(&t)
		}
		os.Stdout.Sync()

		// C1 - 새 필드를 여기 안 더하면 최종 통계에 0 으로 남는다.
		// 2026-08-23 에 실제로 그래서 "회신 0 건"으로 오진했다.
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

// ------------------------------------------------------------------- 자체시험
// 부호기·복호기가 맞는지 프로세스 안에서 먼저 확인한다. 네트워크를 붙이기
// 전에 통과해야 하는 관문이다(인수인계 문서 6절: 새 코드는 작게 먼저).
// scriptConn 은 미리 적어 둔 데이터그램을 차례로 내주는 가짜 PacketConn 이다.
//
// 🩸 2026-08-28 (2 단계 감사) - 이것이 없어서 **회계 시험이 전부 feedOne 으로만
//
//	돌고 있었다.** feedOne 은 데이터그램을 돌려주지 않으므로 "quic-go 에 무엇을
//	올려보냈는가"라는 축이 아예 없고, 그 축에서만 보이는 결함(보류한 패리티를
//	올려보내면서 스택에는 안 넣기)을 **원리적으로 못 봤다.** 실제로 그 결함이
//	거기 숨어 있었다. 계기가 못 보는 축은 결함이 사는 곳이다.
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
	// 문서 2-3 의 손계산 예제
	a := []byte{0x69} // 01101001
	b := []byte{0xd6} // 11010110
	p := rsEncode([][]byte{a, b}, 1, 1)[0]
	check("XOR 패리티가 문서 손계산(10111111)과 일치", p[0] == 0xbf)
	rec := recoverOne(2, 1, 0, 0, map[int][]byte{1: b}, p, 1)
	check("A 유실 복원", rec[0] == a[0])

	// 실제 크기 데이터그램. 🩸 2026-08-27 - m=3 을 더했다. 그전에는
	// {1, 2} 뿐이라 **m=3 이 한 번도 시험된 적이 없었다**(신레오 보고).
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
				// 패리티 **아무 하나**로 풀어도 같은 답이 나와야 한다.
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
	// --- 다중 소거 (2026-08-27 신설, 신레오 보고서 6쪽의 요청) --------------
	//
	// 🩸 그전 고리는 `for miss := 0; miss < k; miss++` 로 **언제나 하나만**
	//    지웠다. 그래서 소거가 둘 이상인 경로를 한 번도 안 밟았고, 옛
	//    recoverOne 의 m==1 분기가 잘못된 값을 내놓는다는 사실이 코드에
	//    들어간 채로 남아 있었다. 시험 범위의 문제였지 결함이 아니었으므로,
	//    범위를 넓히는 것이 처방이다.
	//
	// 두 가지를 함께 못 박는다.
	//   양성 : 복구용 패리티가 e 개 있으면 소거 e 개가 **정확히** 복원된다.
	//   음성 : 패리티가 모자라면 **nil** 이어야 한다. 잘못된 값을 내놓으면
	//          안 된다 - 옛 코드가 정확히 그것을 했다.
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
					// (가) 패리티 e 개를 준다 -> 전부 복원돼야 한다.
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

					// (나) [음성] 패리티를 하나 덜 준다 -> nil 이어야 한다.
					//     잘못된 값을 내놓으면 여기서 붉어진다.
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

					// (다) [음성] 살아남은 원본을 하나 감추면 nil 이어야 한다.
					//     옛 recoverOne 의 m==1 분기는 여기서 **잘못된 값**을
					//     내놨다(실측 1,200 B 중 1,197 B 가 달랐다).
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

	// --- 회계 불변식: **도착 순서 전수** (2026-08-28 신설) --------------------
	//
	// 🩸 이 부류의 결함은 옛 시험이 **원리적으로 못 봤다.** 위 검사들은
	//    부호기·복호기만 보고 회계를 안 보며, 실측 하네스의 netem 은
	//    지터도 재정렬도 안 걸어(padbed.py) 패리티가 언제나 마지막에 온다.
	//    그래서 「먼저 온 패리티」 경로가 한 번도 안 밟혔고, 거기에
	//    +1280 B 짜리 신용 부풀림이 숨어 있었다.
	//
	// 지키는 것은 하나다. **스택에 넘긴 누적 바이트는 물리적으로 받은
	// 누적 바이트를 절대 넘지 않는다.** 이걸 어기면 우리가 RFC 9000 8.1 의
	// 3 배 한도를 우회하는 셈이고, 이 연구의 전제가 무너진다.
	//
	// 도착 순서를 **전부** 돌린다 - 잃은 것 없는 판까지 포함해서.
	for _, kk := range []int{1, 2, 3} {
		for _, mm := range []int{1, 2} {
			// 🩸 원본은 **롱헤더 Initial 꼴**이어야 한다. 무작위 바이트로
			//    만들면 dcidOf 가 빈 문자열을 주고, tryRecoverLocked 의
			//    `r.dcid == fr.dcid` 가 영영 안 맞아 **복구가 시도조차 안 된다**
			//    - 시험이 통째로 공허해진다. 실제로 처음 판이 그랬고,
			//    돌연변이를 넣어도 안 붉어져서 드러났다.
			dd := []byte{7, 7, 7, 7, 7, 7, 7, 7}
			sc := []byte{8, 8, 8, 8}
			src := make([][]byte, kk)
			for i := range src {
				d := make([]byte, 1200)
				rand.Read(d)
				// 롱헤더 Initial: 첫 바이트 최상위 비트 + 고정 버전 + CID
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
			// 보낼 데이터그램: 원본 kk 개 + 패리티 mm 개
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
				// 호출자 버퍼를 **재사용**한다 - quic-go 가 sync.Pool 로
				// 하는 것과 같다. 별칭이 남아 있으면 여기서 드러난다.
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

	// --- [회계-ReadFrom] 실제로 올려보낸 바이트 <= 도착한 바이트 -----------
	//
	// 🩸 2026-08-28 (2 단계 감사). 위 시험은 feedOne 으로 돌아서
	//    **BytesToStack 이라는 우리 장부**만 본다. 진짜 물리 불변식은
	//    「quic-go 에 인계한 누적 바이트 <= 도착한 누적 바이트」다 - 설계요점 2
	//    대로 올려보낸 데이터그램은 저쪽에서 ReceivedBytes 로 세어져 3 배
	//    예산을 늘리기 때문이다. 두 값이 갈라질 수 있고, 실제로 갈라져 있었다.
	//    m=3 까지 돈다(2 단계가 새로 연 능력이고 결함도 거기서 열렸다).
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
				// 원본을 하나씩 빼 본다(-1 은 전부 도착). 소거 1 개는 m>=1
				// 이면 풀리고, 그 뒤에 오는 뒤따르는 패리티가 재진입한다.
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
					// 2026-09-07 - 장부(BytesToStack)가 실제로 넘긴 바이트와 같아야
					// 한다. 위 검사는 `인계 <= 도착` 만 봐서 장부가 W 만큼 모자라도
					// 초록이었다(복원본 미기록 결함이 여기서 새어 나갔다).
					if handed != stk && badLedger == "" {
						badLedger = fmt.Sprint("순서", ord, " 소거", drop,
							" 인계 ", handed, " != 장부 ", stk)
					}
					// 🩸 두 현상을 **갈라서** 본다. 처음 판은 둘을 뭉쳐
					//    `Recovered <= 실제 소거` 로 봤는데, 재정렬로 생기는
					//    **미리 복구**(안 온 원본을 소거로 오해)까지 실패로
					//    찍혀 멀쩡한 코드가 붉어졌다. 미리 복구는 안전 문제가
					//    아니라 지표 문제이고, 아래 [미리복구] 로 따로 센다.
					//
					//    여기서 보는 것은 **같은 비행을 두 번 푸는 것**이다.
					//    비행이 하나뿐인 시험이므로 사건 수는 0 또는 1 이어야
					//    한다. fr.done 가드를 빼면 여기가 2 가 된다.
					if ev > 1 && badDup == "" {
						badDup = fmt.Sprint("순서", ord, " 소거", drop,
							" 복구사건 ", ev, " (비행 하나에 두 번 이상)")
					}
					// 미리 복구는 **재정렬이 있을 때만** 생겨야 한다.
					// 순서가 그대로면(=오름차순) 0 이어야 한다.
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

	// --- 다중 소거 통합 시험 (2026-08-28, 신레오 보고의 그 조건) ----------
	//
	// 신레오님이 잰 조건 그대로다: k=2, 원본 **둘 다** 소거.
	//   m=1,2 -> 복구용(뒤따르는) 패리티가 1 개뿐이라 **여전히 못 고친다.**
	//           선행 패리티를 신용으로 쓰는 대가이고, 결함이 아니다.
	//   m=3   -> 뒤따르는 패리티가 2 개이므로 **복구된다.** 이것이 이
	//           수정으로 새로 생긴 능력이고, 실험으로 확인할 지점이다.
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
		// 원본은 **둘 다 버린다**. 패리티만 보낸다.
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
			want = 2 // 뒤따르는 패리티 2 개 -> 소거 2 개 복구
		}
		check(fmt.Sprint("[통합] k=2 원본 둘 다 소거, m=", mm,
			" -> 복구 ", got, " (기대 ", want, ")"), got == want && !over)
	}

	// 패리티 데이터그램 왕복
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
	// 정상 Initial 은 FEC 블록으로 오인되지 않아야 한다
	fakeInitial := append([]byte{0xC3, 0, 0, 0, 1, 8}, dcid...)
	fakeInitial = append(fakeInitial, 0)
	fakeInitial = append(fakeInitial, 0x00, 0x44, 0x00)
	fakeInitial = append(fakeInitial, make([]byte, 1200)...)
	check("정상 Initial 을 패리티로 오인하지 않는다", parseFecBlock(fakeInitial) == nil)
	return fail
}

// parseIdx 는 "0" 또는 "0,1" 같은 문자열을 인덱스 집합으로 바꾼다.
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
		"client | server | selftest | policygrid | policy3ref")
	addr := flag.String("addr", "127.0.0.1:44433", "address")
	group := flag.String("group", "X25519MLKEM768", "key exchange group")
	certSize := flag.Int("certsize", 2955, "target certificate DER size")
	n := flag.Int("n", 20, "handshakes")
	timeout := flag.Duration("timeout", 12*time.Second, "per-handshake timeout")
	gap := flag.Duration("gap", 25*time.Millisecond, "gap between handshakes")
	fec := flag.String("fec", "off",
		"off | buf | on | auto | auto3  (auto = 목적지 캐시로 m 을 스스로 고름, "+
			"auto3 = v3 학습층이 (δ, ℓ, T) 를 고르고 -layout v3 로 보냄)")
	cache := flag.String("cache", "",
		"폐루프 목적지 캐시 파일 (auto 모드에서 씀)")
	// 🩸 2026-08-25 - 2 -> 3. 실측: cert 14,601~16,125 에서 m=2 는
	//    2-RTT, m=3 은 1-RTT 다(한 왕복 50 ms). 근거 전문은
	//    padfec/policy.py 의 M_MAX_DEFAULT 주석.
	mMax := flag.Int("m-max", mMaxDefault,
		"auto 모드에서 고를 수 있는 최대 m (기본값은 확률표가 심는다)")
	coldM := flag.Int("cold-m", 0,
		"auto 모드 콜드스타트(기록 없는 목적지)에서 쓸 m")
	probeEvery := flag.Int("probe-every", 20,
		"auto 모드에서 몇 연결마다 무방비(m=0)로 가서 손실률을 재측정할지")
	// 🩸 2026-08-21. 그전에는 policy.go 안에 10 Mbps 가 리터럴로 박혀 있었다.
	// 어디서도 측정된 적 없는 수인데 결정의 43% 를 좌우했고, 정작 이 테스트베드
	// 는 netem 이 대역을 안 걸어 실측과 25 배 어긋났다. 기본값을 생성 표의
	// uplinkMbpsDefault(= padfec/policy.py 한 곳에서 정의)에서 읽고, 실제로
	// 도는 링크를 아는 호출부(padbed)가 덮어쓴다. 0 = 대역 무제한.
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
	// C1: 서버 수신 회신. 기본은 꺼 둔다 - 켜고 끈 결과를 나란히 재야
	// (p16 식 음성 대조) 회신이 임계·HCT 를 안 건드린다고 말할 수 있다.
	feedback := flag.Bool("feedback", false,
		"C1: 서버가 첫 비행 수신 심볼 수를 회신한다(클라는 그것으로 손실 관측)")
	layout := flag.String("layout", "v2",
		"v2 | v3  (v3: 검증 전 비행 [L.., O.., P..] fecVer 3, 이후 비행 원본 즉시 + 뒤 패리티 <=1)")
	lead := flag.Int("lead", -1,
		"-layout v3 의 선행 신용 패리티 수 (-1 = 레거시 [m>=2])")
	cache3 := flag.String("cache3", "",
		"-fec auto3 의 목적지별 학습 상태 파일 (gen-2 -cache 와 따로 둔다)")
	flag.Parse()
	layoutSet := false
	flag.Visit(func(f *flag.Flag) {
		if f.Name == "layout" {
			layoutSet = true
		}
	})

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
	switch *mode {
	case "selftest":
		os.Exit(selfTest())
	case "policygrid":
		// 정책 결정을 격자 전체에서 찍는다. experiments/gate_go_parity.py 가
		// 이걸 읽어 Python decide_v2 와 대조한다 - 왜 제품 바이너리에
		// 들어 있는지는 policy.go 의 policyGrid 머리말에 적었다.
		policyGrid()
		return
	case "policy3ref":
		os.Exit(policy3RefMain(os.Stdin, os.Stdout))
	case "server":
		if fmode == "auto3" || *cache3 != "" {
			fmt.Fprintln(os.Stderr, "auto3: -fec auto3 and -cache3 are client options")
			os.Exit(2)
		}
		runServer(*addr, *certSize, fmode, *stats, *feedback)
	default:
		if fmode == "auto3" {
			if err := checkAuto3Flags(layoutSet, *layout, *lead, *ips); err != nil {
				fmt.Fprintln(os.Stderr, "auto3:", err)
				os.Exit(2)
			}
		} else if *cache3 != "" {
			fmt.Fprintln(os.Stderr, "auto3: -cache3 needs -fec auto3")
			os.Exit(2)
		} else if err := checkLayoutFlags(*layout, *lead, fmode, *m); err != nil {
			fmt.Fprintln(os.Stderr, "layout:", err)
			os.Exit(2)
		}
		runClient(*addr, *group, *n, *timeout, *gap, fmode, *m, *ips,
			*pdelay, *expectK, *stats, *dump, parseIdx(*dropI),
			*dropP, *corrP, *cache, *mMax, *coldM, *probeEvery, *uplink,
			*feedback, *layout, *lead, *cache3)
	}
}
