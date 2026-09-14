// qamp — QUIC 증폭 제한(RFC 9000 §8.1) 실험 도구
//
// 서버 인증서 크기를 조절해 증폭 예산 초과 여부에 따른 핸드셰이크 비용을 측정한다.
// 송수신 데이터그램을 직접 계측하므로 tcpdump·특별 권한이 필요 없다.
//
// 빌드: CGO_ENABLED=0 go build -o qamp qamp.go
// 서버: ./qamp -mode server -addr 10.9.0.2:44433 -group X25519MLKEM768 -certsize 16000
// 측정: ./qamp -mode client -addr 10.9.0.2:44433 -group X25519MLKEM768 -n 500 -summary
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
	"encoding/csv"
	"errors"
	"flag"
	"fmt"
	"log"
	"math"
	"math/big"
	"net"
	"os"
	"sort"
	"strconv"
	"sync"
	"time"

	"github.com/quic-go/quic-go"
)

const alpn = "rne-amp"

// ---------- 데이터그램 계측 래퍼 ----------
type countConn struct {
	net.PacketConn
	mu       sync.Mutex
	sent     []int
	recv     []int
	counting bool
}

func (c *countConn) WriteTo(b []byte, a net.Addr) (int, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	n, err := c.PacketConn.WriteTo(b, a)
	if c.counting && n > 0 {
		c.sent = append(c.sent, n)
	}
	return n, err
}

func (c *countConn) ReadFrom(b []byte) (int, net.Addr, error) {
	n, a, err := c.PacketConn.ReadFrom(b)
	if err == nil {
		c.mu.Lock()
		if c.counting {
			c.recv = append(c.recv, n)
		}
		c.mu.Unlock()
	}
	return n, a, err
}

func (c *countConn) start() {
	c.mu.Lock()
	c.sent, c.recv, c.counting = nil, nil, true
	c.mu.Unlock()
}

func (c *countConn) stop() ([]int, []int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.counting = false
	return append([]int(nil), c.sent...), append([]int(nil), c.recv...)
}

func sum(a []int) int {
	t := 0
	for _, v := range a {
		t += v
	}
	return t
}

// ---------- 인증서 생성 (크기 조절) ----------
// 더미 확장에 패딩을 넣어 목표 바이트 수에 맞춘다.
// 실제 ML-DSA 서명을 쓰지 않고 전송 바이트만 재현하는 방식으로,
// Kempf 외(NIST 5th PQC Conf, 2024)의 "inflated certificate chain"과 동일한 접근.
func makeCert(target int) (tls.Certificate, int) {
	build := func(pad int) ([]byte, *ecdsa.PrivateKey) {
		key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			log.Fatal(err)
		}
		tmpl := x509.Certificate{
			SerialNumber: big.NewInt(1),
			Subject:      pkix.Name{CommonName: "localhost"},
			NotBefore:    time.Now().Add(-time.Hour),
			NotAfter:     time.Now().Add(24 * 365 * time.Hour),
			DNSNames:     []string{"localhost"},
		}
		if pad > 0 {
			blob := make([]byte, pad)
			if _, err := rand.Read(blob); err != nil {
				log.Fatal(err)
			}
			tmpl.ExtraExtensions = []pkix.Extension{{
				Id:       asn1.ObjectIdentifier{1, 3, 6, 1, 4, 1, 99999, 1},
				Critical: false,
				Value:    blob,
			}}
		}
		der, err := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &key.PublicKey, key)
		if err != nil {
			log.Fatal(err)
		}
		return der, key
	}

	// 1차: 패딩 없이 기준 크기 측정
	base, _ := build(0)
	pad := 0
	if target > len(base) {
		pad = target - len(base)
	}
	der, key := build(pad)

	// 2차 보정 (ASN.1 길이 인코딩 오차)
	if diff := target - len(der); pad > 0 && diff != 0 && pad+diff > 0 {
		der, key = build(pad + diff)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}, len(der)
}

func curveOf(name string) (tls.CurveID, error) {
	switch name {
	case "X25519":
		return tls.X25519, nil
	case "P256":
		return tls.CurveP256, nil
	case "P384":
		return tls.CurveP384, nil
	case "X25519MLKEM768":
		return tls.X25519MLKEM768, nil
	}
	return 0, fmt.Errorf("지원하지 않는 그룹: %s", name)
}

func pct(s []float64, p float64) float64 {
	n := len(s)
	if n == 0 {
		return 0
	}
	if n == 1 {
		return s[0]
	}
	idx := (p / 100.0) * float64(n-1)
	lo := int(idx)
	hi := lo + 1
	if hi >= n {
		hi = n - 1
	}
	fr := idx - float64(lo)
	return s[lo]*(1-fr) + s[hi]*fr
}

func runServer(addr, group string, certSize int) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	cert, actual := makeCert(certSize)
	ua, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		log.Fatal(err)
	}
	pc, err := net.ListenUDP("udp", ua)
	if err != nil {
		log.Fatal(err)
	}
	tr := &quic.Transport{Conn: pc}
	tlsConf := &tls.Config{
		Certificates:           []tls.Certificate{cert},
		NextProtos:             []string{alpn},
		MinVersion:             tls.VersionTLS13,
		CurvePreferences:       []tls.CurveID{cid},
		SessionTicketsDisabled: true,
	}
	ln, err := tr.Listen(tlsConf, &quic.Config{
		MaxIdleTimeout:          30 * time.Second,
		DisablePathMTUDiscovery: true,
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("서버 기동: %s  group=%s  인증서=%dB (목표 %dB)\n", addr, group, actual, certSize)
	for {
		conn, err := ln.Accept(context.Background())
		if err != nil {
			continue
		}
		go func(c *quic.Conn) {
			time.Sleep(5 * time.Millisecond)
			c.CloseWithError(0, "done")
		}(conn)
	}
}

func runClient(addr, group string, n, warmup, timeoutMs, initialSize int, csvPath string, summary bool) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	raddr, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		log.Fatal(err)
	}
	tlsConf := &tls.Config{
		InsecureSkipVerify: true,
		NextProtos:         []string{alpn},
		MinVersion:         tls.VersionTLS13,
		CurvePreferences:   []tls.CurveID{cid},
	}

	var w *csv.Writer
	if csvPath != "" {
		fh, err := os.Create(csvPath)
		if err != nil {
			log.Fatal(err)
		}
		defer fh.Close()
		w = csv.NewWriter(fh)
		defer w.Flush()
		w.Write([]string{"iter", "hct_ms", "sent_pkts", "sent_bytes", "recv_pkts", "recv_bytes", "status", "negotiated_group", "initial_size"})
	}

	var hcts []float64
	var sPk, sBy, rPk, rBy []float64
	failN, tmoN := 0, 0

	for attempt := 0; attempt < n+warmup; attempt++ {
		i := attempt - warmup
		// Separate sockets prevent delayed packets from the preceding connection
		// entering this connection's byte counters.
		pc, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
		if err != nil {
			log.Fatal(err)
		}
		cc := &countConn{PacketConn: pc}
		tr := &quic.Transport{Conn: cc}
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutMs)*time.Millisecond)
		cc.start()
		t0 := time.Now()
		conn, err := tr.Dial(ctx, raddr, tlsConf, &quic.Config{
			InitialPacketSize:       uint16(initialSize),
			HandshakeIdleTimeout:    time.Duration(timeoutMs) * time.Millisecond,
			MaxIdleTimeout:          30 * time.Second,
			DisablePathMTUDiscovery: true,
		})
		el := float64(time.Since(t0).Microseconds()) / 1000.0
		s, r := cc.stop()
		contextErr := ctx.Err()
		cancel()
		negotiated := ""
		if conn != nil {
			negotiated = conn.ConnectionState().TLS.CurveID.String()
			if conn.ConnectionState().TLS.CurveID != cid {
				err = fmt.Errorf("negotiated group %s differs from requested %s", negotiated, group)
			}
			conn.CloseWithError(0, "bye")
		}
		tr.Close()
		pc.Close()
		if i < 0 {
			continue
		}

		if err != nil {
			failN++
			st := "fail"
			var timeoutError net.Error
			if contextErr == context.DeadlineExceeded || errors.Is(err, context.DeadlineExceeded) || (errors.As(err, &timeoutError) && timeoutError.Timeout()) {
				tmoN++
				st = "timeout"
			}
			if w != nil {
				w.Write([]string{strconv.Itoa(i), "", strconv.Itoa(len(s)), strconv.Itoa(sum(s)),
					strconv.Itoa(len(r)), strconv.Itoa(sum(r)), st, negotiated, strconv.Itoa(initialSize)})
			}
			continue
		}
		hcts = append(hcts, el)
		sPk = append(sPk, float64(len(s)))
		sBy = append(sBy, float64(sum(s)))
		rPk = append(rPk, float64(len(r)))
		rBy = append(rBy, float64(sum(r)))

		if w != nil {
			w.Write([]string{strconv.Itoa(i), fmt.Sprintf("%.4f", el),
				strconv.Itoa(len(s)), strconv.Itoa(sum(s)),
				strconv.Itoa(len(r)), strconv.Itoa(sum(r)), "ok", negotiated, strconv.Itoa(initialSize)})
		}
		if !summary {
			fmt.Printf("  [%d] HCT=%.3fms  송신 %d개/%dB  수신 %d개/%dB\n",
				i, el, len(s), sum(s), len(r), sum(r))
		}
	}

	avg := func(a []float64) float64 {
		if len(a) == 0 {
			return 0
		}
		t := 0.0
		for _, v := range a {
			t += v
		}
		return t / float64(len(a))
	}
	sorted := append([]float64(nil), hcts...)
	sort.Float64s(sorted)
	m := avg(hcts)
	sd := 0.0
	for _, v := range hcts {
		sd += (v - m) * (v - m)
	}
	if len(hcts) > 1 {
		sd = math.Sqrt(sd / float64(len(hcts)-1))
	}
	frate := 0.0
	if len(hcts)+failN > 0 {
		frate = 100.0 * float64(failN) / float64(len(hcts)+failN)
	}
	sentB := avg(sBy)
	recvB := avg(rBy)
	amp := 0.0
	if sentB > 0 {
		amp = recvB / sentB
	}
	fmt.Printf("group=%-16s n=%d fail=%d tmo=%d failrate=%.2f%%\n",
		group, len(hcts), failN, tmoN, frate)
	fmt.Printf("  HCT(ms) mean=%.3f sd=%.3f p50=%.3f p95=%.3f p99=%.3f\n",
		m, sd, pct(sorted, 50), pct(sorted, 95), pct(sorted, 99))
	fmt.Printf("  송신 %.2f개/%.0fB  수신 %.2f개/%.0fB  핸드셰이크 전체 수신/송신=%.2f\n",
		avg(sPk), sentB, avg(rPk), recvB, amp)
	fmt.Println("  주소 검증 전 바이트를 분리하지 않았으므로 이 비율로 RFC 증폭 한도를 판정할 수 없습니다.")
	if w != nil {
		w.Flush()
		if err := w.Error(); err != nil {
			log.Fatal("CSV write failed: ", err)
		}
	}
}

func main() {
	mode := flag.String("mode", "client", "server 또는 client")
	addr := flag.String("addr", "127.0.0.1:44433", "주소:포트")
	group := flag.String("group", "X25519MLKEM768", "키 교환 그룹")
	certSize := flag.Int("certsize", 0, "서버 인증서 목표 크기(B). 0이면 기본(약 500B)")
	n := flag.Int("n", 100, "반복 횟수")
	warmup := flag.Int("warmup", 0, "워밍업 횟수 (통계 및 CSV 제외)")
	initialSize := flag.Int("initpkt", 1280, "클라이언트 Initial UDP 페이로드 크기(B, IPv4 MTU 1500에서 1200~1472)")
	timeout := flag.Int("timeout", 5000, "타임아웃(ms)")
	csvPath := flag.String("csv", "", "원자료 CSV 경로")
	summary := flag.Bool("summary", false, "요약만 출력")
	flag.Parse()
	if *n <= 0 || *warmup < 0 || *timeout <= 0 || *certSize < 0 || *initialSize < 1200 || *initialSize > 1472 {
		log.Fatal("n과 timeout은 양수, warmup과 certsize는 음이 아닌 수, initpkt는 1200~1472여야 합니다")
	}

	switch *mode {
	case "server":
		runServer(*addr, *group, *certSize)
	case "client":
		runClient(*addr, *group, *n, *warmup, *timeout, *initialSize, *csvPath, *summary)
	default:
		log.Fatal("mode는 server 또는 client")
	}
}
