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

const fbVer = 1

type fbRec struct {
	flight uint16
	k      uint8 // 서버가 이 비행에서 기대한 원본 수 (참고)
	rxOrig uint8 // 실제로 받은 원본 데이터그램 수
	rxPar  uint8 // 실제로 받은 패리티 데이터그램 수
	recov  uint8 // 복구한 원본 수
}

func buildFeedback(dcid, scid []byte, r fbRec) []byte {
	body := make([]byte, 0, 16)
	body = append(body, fbMagic...)
	body = append(body, byte(fbVer))
	body = binary.BigEndian.AppendUint16(body, r.flight)
	body = append(body, r.k, r.rxOrig, r.rxPar, r.recov)

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
//    두 번째 비행에서 Initial(ACK)과 Handshake 를 **한 데이터그램에
//    코얼레스**해 보낸다. 그래서 전부 typ 0 으로 분류돼 회신이 한 번도
//    나가지 않았다(실측: hdr_initial 100, hdr_handshake **0**).
//    코얼레스된 패킷을 길이 필드로 따라가며 전부 훑는다.
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
	if i+blen > len(d) || blen < fecMagicLen+7 {
		return nil
	}
	b := d[i : i+blen]
	if string(b[:fecMagicLen]) != string(fbMagic) || b[4] != fbVer {
		return nil
	}
	return &fbRec{
		flight: binary.BigEndian.Uint16(b[5:7]),
		k:      b[7], rxOrig: b[8], rxPar: b[9], recov: b[10],
	}
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
	// C1 배선 확인용: 서버 회신을 몇 번 받았고 마지막 내용이 무엇인가.
	FbRecv      int `json:"fb_recv"`
	FbMagicSeen int `json:"fb_magic_seen"`
	RxCalls     int `json:"rx_calls"` // fecConn.ReadFrom 이 실제로 불린 횟수
	FbWaits     int `json:"fb_waits"` // waitFeedback 을 부른 횟수
	FbRxOrig  int   `json:"fb_rx_orig"`
	FbRxPar   int   `json:"fb_rx_parity"`
	FbRecov   int   `json:"fb_recovered"`
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
	FirstFlightParity      int   `json:"first_flight_parity_dgrams"`
	FirstFlightParityBytes int64 `json:"first_flight_parity_bytes"`
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
	for {
		n, addr, err := c.PacketConn.ReadFrom(b)
		if err != nil || n <= 0 {
			return n, addr, err
		}
		c.countRx(n)
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
			c.stats.FbRxOrig = int(r.rxOrig)
			c.stats.FbRxPar = int(r.rxPar)
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
			if isFirstFlight {
				c.stats.FirstFlightParity++
				c.stats.FirstFlightParityBytes += int64(len(pkt))
			}
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
	ConnAcctDropped int `json:"conn_acct_dropped"` // connAcctCap 초과로 못 센 연결
	// C1 진단: 롱헤더 타입별 수신 수와 회신 송신 수. 배선이 어디서 끊겼는지
	// 추측하지 않고 자료로 보려고 둔다.
	HdrInitial   int `json:"hdr_initial"`
	HdrHandshake int `json:"hdr_handshake"`
	HdrShort     int `json:"hdr_short"`
	FbSentN      int `json:"fb_sent"`
	FbWriteErr   int `json:"fb_write_err"`
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

// ------------------------------------------------- 연결별 회계 (p13, 2026-08-20)
//
// 명세 §2.6 의 B_eff("서버가 응답 비행을 만들기로 결정한 시점까지 도착한
// 클라이언트 바이트")를 **직접** 재기 위한 계측이다. 그전까지 countConn 은
// 프로세스 전체 합계만 세서 (1) 연결끼리 섞이고 (2) 송신을 아예 안 가로채
// "첫 송신 시점"이라는 것 자체가 없었다 - B_eff 재해석이 사후 가설에
// 머문 이유다.
//
// 연결의 열쇠는 클라이언트 주소다. 시행마다 새 UDP 소켓(새 포트)을 쓰므로
// 주소가 곧 연결이다. DCID 는 서버가 Retry 없이도 바꿔 앉을 수 있어 안 쓴다.
//
// 두 종류의 바이트를 다 센다.
//   phys  물리적으로 도착한 바이트 (원본/패리티 분리)
//   stack QUIC 스택에 넘긴 바이트 - quic-go 의 증폭 예산이 실제로 세는 양.
//         복구가 일어나면 패리티 대신 복구본이 넘어가므로 phys 와 갈린다.
//         무손실 시행에서는 둘이 같다.
type connAcct struct {
	FirstRxNs int64 `json:"first_rx_ns"`
	FirstTxNs int64 `json:"first_tx_ns"`
	RxDgrams  int   `json:"rx_dgrams"`
	RxBytes   int64 `json:"rx_bytes"`
	RxOrig    int64 `json:"rx_orig_bytes"`
	RxParity  int64 `json:"rx_parity_bytes"`
	// 🩸 2026-08-23 (C1) - 위 둘은 **바이트**다. 피드백은 심볼 **개수**를
	//    보내야 하므로 따로 센다. 첫 비행 몫만 세려고 Handshake 를 본
	//    시점에 잠근다(FbSent).
	RxOrigN   int  `json:"rx_orig_n"`
	RxParityN int  `json:"rx_parity_n"`
	RecovN    int  `json:"recov_n"`
	FbSent    bool `json:"fb_sent"`
	Stack     int64 `json:"stack_bytes"`
	TxDgrams  int   `json:"tx_dgrams"`
	TxBytes   int64 `json:"tx_bytes"`
	// 서버가 첫 데이터그램을 내보내는 순간의 스냅숏. 이것이 B_eff 다.
	BeffStack  int64 `json:"beff_stack"`
	BeffPhys   int64 `json:"beff_phys"`
	BeffOrig   int64 `json:"beff_orig"`
	BeffParity int64 `json:"beff_parity"`
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

const connAcctCap = 4096     // 폭주 방지. 넘으면 새 연결은 세지 않고 개수만 남긴다.
const connTimelineCap = 40   // 서버 첫 비행(<=13 패킷) + 꼬리를 담고도 남는다.

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
	conns        map[string]*connAcct
	stats        serverStats
}

// acctLocked 는 이 주소의 연결 회계를 준다. mu 를 쥔 채로만 부른다.
func (s *decodeConn) acctLocked(addr net.Addr) *connAcct {
	if addr == nil {
		return nil
	}
	key := addr.String()
	ca, ok := s.conns[key]
	if ok {
		return ca
	}
	if s.conns == nil {
		s.conns = map[string]*connAcct{}
	}
	if len(s.conns) >= connAcctCap {
		s.stats.ConnAcctDropped++
		return nil
	}
	ca = &connAcct{}
	s.conns[key] = ca
	return ca
}

// stackLocked 는 "스택에 넘긴 바이트"를 전역과 연결 양쪽에 계상한다.
// quic-go 의 증폭 예산이 실제로 세는 것이 이 양이므로, B_eff 의 정본도 이쪽이다.
func (s *decodeConn) stackLocked(addr net.Addr, n int) {
	s.stats.BytesToStack += int64(n)
	if ca := s.acctLocked(addr); ca != nil {
		ca.Stack += int64(n)
	}
}

// WriteTo 가 서버 송신을 가로챈다. 이 연결로 나가는 **첫** 데이터그램 직전의
// 수신 누적이 곧 B_eff 다(명세 §2.6). quic-go 는 예산 검사를 패킷을 만들기
// 전에 하므로, 첫 송신 시점의 수신 누적이 첫 응답 비행의 예산을 정한 값이다.
func (s *decodeConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	s.mu.Lock()
	if ca := s.acctLocked(addr); ca != nil {
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
		s.stackLocked(p.addr, len(p.data))
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
	if ca := s.acctLocked(addr); ca != nil {
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
		if s.feedback && (isHandshake || fbEarly) && !ca.FbSent {
			ca.FbSent = true
			s.stats.FbSentN++
			fbOut = buildFeedback(hs.scid, hs.dcid, fbRec{
				flight: 0,
				k:      uint8(min8(ca.RxOrigN + ca.RecovN)),
				rxOrig: uint8(min8(ca.RxOrigN)),
				rxPar:  uint8(min8(ca.RxParityN)),
				recov:  uint8(min8(ca.RecovN)),
			})
		}
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
		s.stackLocked(addr, n)
		s.mu.Unlock()
		return n, addr, nil
	}
	if fb == nil {
		s.noteOriginal(b[:n], addr)
		s.mu.Lock()
		s.stackLocked(addr, n)
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
		s.stackLocked(addr, n)
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
		s.stackLocked(addr, len(rec))
		s.mu.Unlock()
		m := copy(b, rec)
		return m, addr, nil
	}
	if rec != nil {
		s.stats.RecoverRefused++
	}
	// 복구가 없으면 패리티를 그대로 통과시킨다. quic-go 는 바이트를 센 뒤
	// 복호 실패로 폐기하므로, 증폭 예산만 그만큼 늘어난다.
	s.stackLocked(addr, n)
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
		conns[k] = &cp
	}
	return struct {
		serverStats
		Conns map[string]*connAcct `json:"conns"`
	}{s.stats, conns}
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
	tr := &quic.Transport{Conn: fc}
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
	FFParity      int   `json:"first_flight_parity_dgrams"`
	FFParityBytes int64 `json:"first_flight_parity_bytes"`
	MUsed    int     `json:"m_used"`
	IPSUsed  int     `json:"ips_used"`
	MWhy     string  `json:"m_why,omitempty"`
	SrvBytes int64   `json:"server_bytes"`
	LossEvt  bool    `json:"loss_event"`
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

	// 폐루프: mode == "auto" 면 목적지 캐시가 m 을 고른다.
	cache := newDestCache(cachePath)
	wSize := ips
	if wSize <= 0 {
		wSize = 1280 // quic-go 기본 InitialPacketSize
	}
	defer cache.save()

	for i := 0; i < n; i++ {
		trialM, why := m, ""
		// 이 판에서 실제로 쓸 InitialPacketSize. auto 가 아니면 플래그 그대로.
		trialIPS := ips
		unbiased := true
		fmode := mode
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
			MUsed: trialM, IPSUsed: trialIPS,
			MWhy: why, SrvBytes: srvBytes, LossEvt: lossEvt}
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
		// 🆕 C1/C2 - 심볼 단위 관측. auto 가 아니어도 캐시는 갱신한다
		// (고정팔로 도는 동안 배운 것도 다음 auto 연결에 쓸 수 있다).
		if feedback {
			nSent := st.FirstFlightDgrams + st.FirstFlightParity
			if r := fc.lastFeedback(); r != nil {
				nRecv := int(r.rxOrig) + int(r.rxPar)
				if nSent > 0 && nRecv >= 0 && nRecv <= nSent {
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
		}
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
		// 정책 결정을 격자 전체에서 찍는다. experiments/gate_go_parity.py 가
		// 이걸 읽어 Python decide_v2 와 대조한다 - 왜 제품 바이너리에
		// 들어 있는지는 policy.go 의 policyGrid 머리말에 적었다.
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
