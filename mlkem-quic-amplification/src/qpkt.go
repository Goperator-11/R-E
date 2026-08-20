// qpkt — QUIC 핸드셰이크 중 송신 데이터그램을 직접 계측한다.
//
// quic.Transport 에 래핑한 PacketConn 을 넘겨, WriteTo/ReadFrom 을 가로채
// 방향별 데이터그램 개수·크기를 기록한다. tcpdump 나 특별 권한이 필요 없다.
//
// 빌드: CGO_ENABLED=0 go build -o qpkt qpkt.go
// 서버: ./qpkt -mode server -addr 127.0.0.1:44433 -group X25519MLKEM768
// 측정: ./qpkt -mode client -addr 127.0.0.1:44433 -group X25519MLKEM768 -n 5
package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"flag"
	"fmt"
	"log"
	"math/big"
	"net"
	"sync"
	"time"

	"github.com/quic-go/quic-go"
)

const alpn = "rne-pkt"

// ---- 계측용 PacketConn 래퍼 ----
type countConn struct {
	net.PacketConn
	mu       sync.Mutex
	sent     []int // 송신 데이터그램 크기 (bytes)
	recv     []int // 수신 데이터그램 크기
	counting bool
}

func (c *countConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.mu.Lock()
	if c.counting {
		c.sent = append(c.sent, len(b))
	}
	c.mu.Unlock()
	return c.PacketConn.WriteTo(b, addr)
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
	c.sent = nil
	c.recv = nil
	c.counting = true
	c.mu.Unlock()
}

func (c *countConn) stop() ([]int, []int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.counting = false
	s := append([]int(nil), c.sent...)
	r := append([]int(nil), c.recv...)
	return s, r
}

func sum(a []int) int {
	t := 0
	for _, v := range a {
		t += v
	}
	return t
}

func genCert() tls.Certificate {
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "localhost"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(24 * 365 * time.Hour),
		DNSNames:     []string{"localhost"},
	}
	der, _ := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &key.PublicKey, key)
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
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

func runServer(addr, group string) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	udpAddr, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		log.Fatal(err)
	}
	pc, err := net.ListenUDP("udp", udpAddr)
	if err != nil {
		log.Fatal(err)
	}
	tr := &quic.Transport{Conn: pc}
	tlsConf := &tls.Config{
		Certificates:           []tls.Certificate{genCert()},
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
	fmt.Printf("서버 기동: %s  group=%s\n", addr, group)
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

func runClient(addr, group string, n int) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	raddr, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		log.Fatal(err)
	}
	pc, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	if err != nil {
		log.Fatal(err)
	}
	cc := &countConn{PacketConn: pc}
	tr := &quic.Transport{Conn: cc}
	tlsConf := &tls.Config{
		InsecureSkipVerify: true,
		NextProtos:         []string{alpn},
		MinVersion:         tls.VersionTLS13,
		CurvePreferences:   []tls.CurveID{cid},
	}

	fmt.Printf("=== %s ===\n", group)
	var totSent, totRecv, cntS, cntR int
	for i := 0; i < n; i++ {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		cc.start()
		t0 := time.Now()
		conn, err := tr.Dial(ctx, raddr, tlsConf, &quic.Config{
			HandshakeIdleTimeout:    5 * time.Second,
			MaxIdleTimeout:          30 * time.Second,
			DisablePathMTUDiscovery: true,
		})
		el := float64(time.Since(t0).Microseconds()) / 1000.0
		s, r := cc.stop()
		cancel()
		if err != nil {
			fmt.Printf("  [%d] 실패: %v\n", i, err)
			continue
		}
		conn.CloseWithError(0, "bye")

		if i == 0 {
			fmt.Printf("  송신 데이터그램: %v  (합계 %dB)\n", s, sum(s))
			fmt.Printf("  수신 데이터그램: %v  (합계 %dB)\n", r, sum(r))
		}
		fmt.Printf("  [%d] HCT=%.3fms  송신 %d개/%dB  수신 %d개/%dB\n",
			i, el, len(s), sum(s), len(r), sum(r))
		totSent += sum(s)
		totRecv += sum(r)
		cntS += len(s)
		cntR += len(r)
	}
	if n > 0 {
		fmt.Printf("  평균: 송신 %.1f개 %.0fB · 수신 %.1f개 %.0fB\n",
			float64(cntS)/float64(n), float64(totSent)/float64(n),
			float64(cntR)/float64(n), float64(totRecv)/float64(n))
		fmt.Printf("  증폭비(수신/송신): %.2f  ← RFC 9000 §8.1 서버 한도 3배\n",
			float64(totRecv)/float64(totSent))
	}
}

func main() {
	mode := flag.String("mode", "client", "server 또는 client")
	addr := flag.String("addr", "127.0.0.1:44433", "주소:포트")
	group := flag.String("group", "X25519MLKEM768", "키 교환 그룹")
	n := flag.Int("n", 5, "반복 횟수")
	flag.Parse()

	switch *mode {
	case "server":
		runServer(*addr, *group)
	case "client":
		runClient(*addr, *group, *n)
	default:
		log.Fatal("mode는 server 또는 client")
	}
}
