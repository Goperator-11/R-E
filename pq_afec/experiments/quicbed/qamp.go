// qamp - 증폭 제한 실험 도구 + 핸드셰이크 FEC.
//
// 인수인계 문서(2026-08-18) 3-2/3-3 이 말하는 그 qamp.go 다. 문서가 지정한
// 구조를 그대로 따른다.
//
//   countConn  net.PacketConn 을 감싸서 송수신 데이터그램의 개수와 크기를
//              기록한다. WriteTo 와 ReadFrom 을 가로챈다.
//              "FEC 인코딩을 끼워 넣을 지점이 바로 여기입니다."
//   makeCert   인증서에 더미 확장을 넣어 목표 바이트 수로 부풀린다.
//   runClient / runServer   quic.Transport 를 직접 만들어 쓴다.
//
// 문서 3-4 가 못박은 전제: quic.DialAddr() 은 라이브러리가 소켓을 내부에서
// 만들어 버려 손댈 수 없다. quic.Transport{Conn: 우리소켓} 이라야 WriteTo 를
// 가로챌 수 있다.
//
// 문서 단계 1~3 을 구현한 부분
//   fecConn    (클라이언트) 문서 단계 1 의 구조 - window/parity/k/enabled.
//              비행을 모아 XOR 복구 심볼을 만들어 함께 내보낸다.
//   decodeConn (서버)  문서 단계 3 - ReadFrom 을 가로채 빠진 데이터그램을
//              복원하고 "방금 수신한 것처럼" 스택에 넘긴다.
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
//
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

type fecBlock struct {
	flight uint16
	k      int
	m      int
	index  int // 이 패리티의 번호 (0..m-1)
	symLen int
	crcs   []uint32
	lens   []uint16
	sym    []byte
}

// buildParity 는 패리티 하나를 담은 데이터그램을 만든다. 겉모양은 정상적인
// 롱헤더 Initial 이라 서버가 연결에 귀속시켜 바이트를 세지만, 페이로드가
// AEAD 를 통과하지 못하므로 QUIC 스택은 조용히 폐기한다.
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
	if fb.k < 1 || fb.k > 32 || fb.m < 1 || fb.m > 8 {
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
	}
	fb.sym = b[j : j+fb.symLen]
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
	// 첫 비행만 따로. 이것이 증폭 예산을 정하는 양이고, 용량 정리의 k 다.
	// 연결 전체의 Initial 을 세면 뒤따르는 ACK 용 Initial 이 섞여 k 가 흐려진다.
	FirstFlightDgrams int   `json:"first_flight_datagrams"`
	FirstFlightBytes  int64 `json:"first_flight_bytes"`
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
	n, addr, err := c.PacketConn.ReadFrom(b)
	if err == nil && n > 0 {
		c.countRx(n)
	}
	return n, addr, err
}

// flushFlight 는 모아 둔 비행을 순서까지 정해 내보낸다.
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
		} else {
			c.stats.ParityFail++
		}
		c.mu.Unlock()
	}

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

// ------------------------------------------------------------ 서버 쪽 FEC
type serverStats struct {
	Originals    int   `json:"originals"`
	Parities     int   `json:"parities"`
	Recovered    int   `json:"recovered"`
	RecoverFail  int   `json:"recover_crc_fail"`
	LateRecover  int   `json:"late_recovered"`
	RecoverRefused int `json:"recover_refused_by_accounting"`
	CreditParities int `json:"credit_parities"`
	Unrecover    int   `json:"unrecoverable_seen"`
	BytesIn      int64 `json:"bytes_in"`
	BytesToStack int64 `json:"bytes_to_stack"`
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
	created time.Time
	done    bool
	// CRC 로 한 번 걸러진 비행은 다시 시도하지 않는다. 매 원본 도착마다
	// 같은 실패를 반복하면 카운터만 부풀고 얻는 것이 없다.
	poisoned bool
}

type pendingPkt struct {
	data []byte
	addr net.Addr
}

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

type decodeConn struct {
	countConn
	mode string

	mu           sync.Mutex
	recent       []recvItem
	flights      map[string]*flightRec
	pending      []pendingPkt
	pendingBytes int64 // 아직 안 넘긴 복구본의 바이트 (회계 예약분)
	stats        serverStats
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
	s.recent = append(s.recent, recvItem{dcid: dcidOf(cp),
		crc: crc32.ChecksumIEEE(cp), data: cp, addr: addr, t: now})
	s.stats.Originals++
	s.mu.Unlock()
	s.tryLate()
}

// tryRecoverLocked 는 이 비행에서 소거 하나를 복구할 수 있으면 복구한다.
func (s *decodeConn) tryRecoverLocked(fr *flightRec, count bool) []byte {
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
	if len(missing) > 1 {
		if count {
			s.stats.Unrecover++
		}
		return nil // 소거가 둘 이상 - 패리티 1 개로는 복구 불가
	}
	rec := recoverOne(fb.k, fb.m, fb.index, missing[0], have, fb.sym,
		fb.symLen)
	if rec == nil {
		return nil
	}
	want := int(fb.lens[missing[0]])
	if want > len(rec) {
		return nil
	}
	rec = rec[:want]
	// 복구본이 원본과 같은지 부호가 스스로 확인한다.
	if crc32.ChecksumIEEE(rec) != fb.crcs[missing[0]] {
		s.stats.RecoverFail++
		fr.poisoned = true
		return nil
	}
	s.stats.Recovered++
	return rec
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
		rec := s.tryRecoverLocked(fr, false)
		if rec == nil {
			continue
		}
		if s.stats.BytesToStack+s.pendingBytes+int64(len(rec)) >
			s.stats.BytesIn {
			s.stats.RecoverRefused++
			continue
		}
		fr.done = true
		s.pending = append(s.pending,
			pendingPkt{data: rec, addr: fr.addr})
		s.pendingBytes += int64(len(rec)) // 예약: 넘길 때까지 잡아 둔다
		s.stats.LateRecover++
	}
}

func (s *decodeConn) ReadFrom(b []byte) (int, net.Addr, error) {
	s.mu.Lock()
	if len(s.pending) > 0 {
		p := s.pending[0]
		s.pending = s.pending[1:]
		s.pendingBytes -= int64(len(p.data))
		s.stats.BytesToStack += int64(len(p.data))
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
	s.mu.Lock()
	s.stats.BytesIn += int64(n)
	s.mu.Unlock()
	if s.mode == "off" {
		s.mu.Lock()
		s.stats.BytesToStack += int64(n)
		s.mu.Unlock()
		return n, addr, nil
	}
	fb := parseFecBlock(b[:n])
	if fb == nil {
		s.noteOriginal(b[:n], addr)
		s.mu.Lock()
		s.stats.BytesToStack += int64(n)
		s.mu.Unlock()
		return n, addr, nil
	}

	dc := dcidOf(b[:n])
	s.mu.Lock()
	s.stats.Parities++
	// 역할 분리를 코드에 못박는다. 마지막 index 만 복구용이고, 그 앞의 것들은
	// 순전히 증폭 신용용이라 복구에 쓰지 않는다. 신용 패리티는 원본보다 먼저
	// 도착하므로, 그것으로 복구를 시도하면 손실이 없는데도 "마지막 원본이
	// 아직 안 왔다"를 소거로 오해한다 - 실제로 그렇게 오작동했다.
	if fb.index != fb.m-1 {
		s.stats.CreditParities++
		s.stats.BytesToStack += int64(n)
		s.mu.Unlock()
		return n, addr, nil
	}
	fr := &flightRec{fb: fb, dcid: dc, addr: addr, created: time.Now()}
	key := fmt.Sprintf("%x|%d|%d", dc, fb.flight, fb.index)
	if s.flights == nil {
		s.flights = map[string]*flightRec{}
	}
	s.flights[key] = fr
	rec := s.tryRecoverLocked(fr, true)
	// ⚖️ 불변식: 스택에 넘긴 누적 바이트는 **물리적으로 도착한 누적 바이트를
	// 절대 넘지 않는다.** 이걸 어기면 우리가 RFC 9000 8.1 의 3배 한도를
	// 우회하는 셈이 된다. 복구본을 넣을 때는 그 자리에 있던 패리티를 버려
	// 회계를 맞춘다.
	if rec != nil && s.stats.BytesToStack+s.pendingBytes+int64(len(rec)) <=
		s.stats.BytesIn {
		fr.done = true
		s.stats.BytesToStack += int64(len(rec))
		s.mu.Unlock()
		m := copy(b, rec)
		return m, addr, nil
	}
	if rec != nil {
		s.stats.RecoverRefused++
	}
	// 복구가 없으면 패리티를 그대로 통과시킨다. quic-go 는 바이트를 센 뒤
	// 복호 실패로 폐기하므로, 증폭 예산만 그만큼 늘어난다.
	s.stats.BytesToStack += int64(n)
	s.mu.Unlock()
	return n, addr, nil
}

func (s *decodeConn) snapshot() serverStats {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.stats
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
func runServer(addr string, certSize int, mode string, statsPath string) {
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
		flights: map[string]*flightRec{}}
	tr := &quic.Transport{Conn: fc}
	tlsConf := &tls.Config{
		Certificates: []tls.Certificate{makeCert(certSize)},
		NextProtos:   []string{"padfec"},
		MinVersion:   tls.VersionTLS13,
		CurvePreferences: []tls.CurveID{
			tls.X25519MLKEM768, tls.X25519, tls.CurveP256,
		},
	}
	ln, err := tr.Listen(tlsConf, &quic.Config{
		MaxIdleTimeout:  30 * time.Second,
		KeepAlivePeriod: 0,
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
	writeStats := func() {
		if statsPath == "" {
			return
		}
		b, _ := json.Marshal(fc.snapshot())
		os.WriteFile(statsPath, b, 0644)
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
	I        int     `json:"i"`
	Ms       float64 `json:"ms"`
	OK       bool    `json:"ok"`
	Group    string  `json:"group"`
	Err      string  `json:"err,omitempty"`
	KEM      uint16  `json:"kem_id"`
	CipherID uint16  `json:"cipher_id"`
	Dgrams   int     `json:"initial_datagrams"`
	Parity   int     `json:"parity_sent"`
	FFDgrams int     `json:"first_flight_datagrams"`
	FFBytes  int64   `json:"first_flight_bytes"`
	MUsed    int     `json:"m_used"`
	MWhy     string  `json:"m_why,omitempty"`
	SrvBytes int64   `json:"server_bytes"`
	LossEvt  bool    `json:"loss_event"`
}

func runClient(addr, group string, n int, timeout, gap time.Duration,
	mode string, m int, ips int, parityDelayUs int, expectK int,
	statsPath string, dumpPath string,
	dropInitial map[int]bool, dropParity, corruptParity int,
	cachePath string, mMax, coldM, probeEvery int) {
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

	for i := 0; i < n; i++ {
		trialM, why := m, ""
		unbiased := true
		fmode := mode
		if mode == "auto" {
			trialM, why, unbiased = cache.decide(addr, wSize, mMax, coldM,
				probeEvery, defaultAssumedBurst)
			if trialM <= 0 {
				fmode = "off" // 정책이 0 을 골랐으면 패리티를 안 보낸다
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
			m: maxInt(trialM, 1),
			expectK:     expectK,
			dropInitial: dropInitial, dropParity: dropParity,
			corruptParity: corruptParity,
			dumpPath:    dumpPath,
			parityDelay: time.Duration(parityDelayUs) * time.Microsecond}
		tr := &quic.Transport{Conn: fc}

		tlsConf := &tls.Config{
			InsecureSkipVerify: true,
			NextProtos:         []string{"padfec"},
			MinVersion:         tls.VersionTLS13,
			CurvePreferences:   []tls.CurveID{curveFor(group)},
		}
		qconf := &quic.Config{
			MaxIdleTimeout:  timeout,
			KeepAlivePeriod: 0,
			Allow0RTT:       false,
		}
		if ips > 0 {
			qconf.InitialPacketSize = uint16(ips)
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
			MUsed: trialM, MWhy: why, SrvBytes: srvBytes, LossEvt: lossEvt}
		if err != nil {
			t.Err = err.Error()
		} else {
			cs := conn.ConnectionState().TLS
			t.CipherID = cs.CipherSuite
			t.KEM = uint16(cs.CurveID)
			conn.CloseWithError(0, "done")
		}
		if err == nil && mode == "auto" {
			cache.observe(addr, st.FirstFlightDgrams, float64(srvBytes),
				hct, lossEvt, unbiased)
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
		agg.FirstFlightDgrams = st.FirstFlightDgrams
		agg.FirstFlightBytes = st.FirstFlightBytes
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

// ------------------------------------------------------------------- 자체시험
// 부호기·복호기가 맞는지 프로세스 안에서 먼저 확인한다. 네트워크를 붙이기
// 전에 통과해야 하는 관문이다(인수인계 문서 6절: 새 코드는 작게 먼저).
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

	// 실제 크기 데이터그램, m=1 과 m=2
	for _, m := range []int{1, 2} {
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
					got := recoverOne(k, m, j, miss, have, pp, 1200)
					same := got != nil && string(got) == string(src[miss])
					check(fmt.Sprint("복원 m=", m, " k=", k, " miss=", miss,
						" 패리티", j), same)
				}
			}
		}
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
	mode := flag.String("mode", "client", "client | server | selftest")
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
	mMax := flag.Int("m-max", 2, "auto 모드에서 고를 수 있는 최대 m")
	coldM := flag.Int("cold-m", 0,
		"auto 모드 콜드스타트(기록 없는 목적지)에서 쓸 m")
	probeEvery := flag.Int("probe-every", 20,
		"auto 모드에서 몇 연결마다 무방비(m=0)로 가서 손실률을 재측정할지")
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
	case "server":
		runServer(*addr, *certSize, fmode, *stats)
	default:
		runClient(*addr, *group, *n, *timeout, *gap, fmode, *m, *ips,
			*pdelay, *expectK, *stats, *dump, parseIdx(*dropI),
			*dropP, *corrP, *cache, *mMax, *coldM, *probeEvery)
	}
}
