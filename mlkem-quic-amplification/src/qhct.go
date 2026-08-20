// qhct — QUIC 핸드셰이크 완료 시간(HCT) 측정 도구
//
// 서버·클라이언트 모드를 하나의 바이너리로 제공한다.
// qlog를 켜면 Initial 패킷 수·증폭 예산 동작을 패킷 단위로 관찰할 수 있다.
//
// 빌드:  go build -o qhct qhct.go
// 서버:  ./qhct -mode server -addr 10.9.0.2:44433 -group X25519MLKEM768
// 측정:  ./qhct -mode client -addr 10.9.0.2:44433 -group X25519MLKEM768 \
//              -iters 500 -warmup 20 -csv out.csv -timeout 5000
// qlog:  -qlog ./qlogdir  (클라이언트/서버 어느 쪽이든)
package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/csv"
	"flag"
	"fmt"
	"log"
	"math"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"time"

	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/logging"
	"github.com/quic-go/quic-go/qlog"
)

const alpn = "rne-hct"

// 자체 서명 인증서 생성 (측정 대상은 키 교환이므로 검증은 생략)
func genCert() tls.Certificate {
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
	der, err := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &key.PublicKey, key)
	if err != nil {
		log.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
}

// 그룹 이름 → CurveID
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
	default:
		return 0, fmt.Errorf("지원하지 않는 그룹: %s (X25519 | P256 | P384 | X25519MLKEM768)", name)
	}
}

func pct(sorted []float64, p float64) float64 {
	n := len(sorted)
	if n == 0 {
		return 0
	}
	if n == 1 {
		return sorted[0]
	}
	idx := (p / 100.0) * float64(n-1)
	lo := int(idx)
	hi := lo + 1
	if hi >= n {
		hi = n - 1
	}
	fr := idx - float64(lo)
	return sorted[lo]*(1-fr) + sorted[hi]*fr
}

func qlogTracer(dir, tag string) func(context.Context, logging.Perspective, quic.ConnectionID) *logging.ConnectionTracer {
	if dir == "" {
		return nil
	}
	os.MkdirAll(dir, 0755)
	return func(_ context.Context, p logging.Perspective, cid quic.ConnectionID) *logging.ConnectionTracer {
		role := "client"
		if p == logging.PerspectiveServer {
			role = "server"
		}
		fn := filepath.Join(dir, fmt.Sprintf("%s_%s_%x.qlog", tag, role, cid.Bytes()))
		fh, err := os.Create(fn)
		if err != nil {
			return nil
		}
		return qlog.NewConnectionTracer(fh, p, cid)
	}
}

func runServer(addr, group, qlogDir string) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	tlsConf := &tls.Config{
		Certificates:     []tls.Certificate{genCert()},
		NextProtos:       []string{alpn},
		MinVersion:       tls.VersionTLS13,
		CurvePreferences: []tls.CurveID{cid},
		SessionTicketsDisabled: true, // 세션 재개 차단 — 전체 핸드셰이크만 측정
	}
	qConf := &quic.Config{
		Tracer:               qlogTracer(qlogDir, "srv"),
		MaxIdleTimeout:       30 * time.Second,
		Allow0RTT:            false,
		DisablePathMTUDiscovery: true,
	}
	ln, err := quic.ListenAddr(addr, tlsConf, qConf)
	if err != nil {
		log.Fatal("리스닝 실패: ", err)
	}
	fmt.Printf("QUIC 서버 기동: %s  group=%s\n", addr, group)
	for {
		conn, err := ln.Accept(context.Background())
		if err != nil {
			continue
		}
		go func(c *quic.Conn) {
			// 핸드셰이크만 필요하므로 즉시 종료
			time.Sleep(5 * time.Millisecond)
			c.CloseWithError(0, "done")
		}(conn)
	}
}

func runClient(addr, group string, iters, warmup, timeoutMs int, csvPath, qlogDir string) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	tlsConf := &tls.Config{
		InsecureSkipVerify: true, // 자체 서명. 측정 대상은 키 교환
		NextProtos:         []string{alpn},
		MinVersion:         tls.VersionTLS13,
		CurvePreferences:   []tls.CurveID{cid},
		ClientSessionCache: nil, // 세션 재개 차단
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
		w.Write([]string{"group", "iter", "hct_ms", "status", "negotiated_group", "err"})
	}

	total := warmup + iters
	var samples []float64
	okN, failN, tmoN := 0, 0, 0
	negName := "?"

	for i := 0; i < total; i++ {
		isWarm := i < warmup
		ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutMs)*time.Millisecond)

		qConf := &quic.Config{
			Tracer:                  qlogTracer(qlogDir, fmt.Sprintf("cli%d", i)),
			HandshakeIdleTimeout:    time.Duration(timeoutMs) * time.Millisecond,
			MaxIdleTimeout:          30 * time.Second,
			DisablePathMTUDiscovery: true,
		}

		t0 := time.Now()
		conn, err := quic.DialAddr(ctx, addr, tlsConf, qConf)
		el := float64(time.Since(t0).Microseconds()) / 1000.0
		cancel()

		if err != nil {
			failN++
			status := "fail"
			if ctx.Err() == context.DeadlineExceeded || err == context.DeadlineExceeded {
				tmoN++
				status = "timeout"
			}
			if w != nil && !isWarm {
				w.Write([]string{group, strconv.Itoa(i - warmup), "", status, "", err.Error()})
			}
			continue
		}

		st := conn.ConnectionState()
		if n := st.TLS.CurveID; n != 0 {
			negName = curveName(n)
		}
		conn.CloseWithError(0, "bye")

		okN++
		if !isWarm {
			samples = append(samples, el)
			if w != nil {
				w.Write([]string{group, strconv.Itoa(i - warmup),
					fmt.Sprintf("%.4f", el), "ok", negName, ""})
			}
		}
	}

	sort.Float64s(samples)
	n := len(samples)
	mean, sd := 0.0, 0.0
	for _, v := range samples {
		mean += v
	}
	if n > 0 {
		mean /= float64(n)
		for _, v := range samples {
			sd += (v - mean) * (v - mean)
		}
		if n > 1 {
			sd = math.Sqrt(sd / float64(n-1))
		}
	}
	frate := 0.0
	if okN+failN > 0 {
		frate = 100.0 * float64(failN) / float64(okN+failN)
	}
	fmt.Printf("group=%-18s negotiated=%-18s n=%d  fail=%d  tmo=%d  failrate=%.2f%%\n",
		group, negName, n, failN, tmoN, frate)
	if n > 0 {
		fmt.Printf("  HCT(ms)  mean=%.3f  sd=%.3f  p50=%.3f  p95=%.3f  p99=%.3f  min=%.3f  max=%.3f\n",
			mean, sd, pct(samples, 50), pct(samples, 95), pct(samples, 99),
			samples[0], samples[n-1])
	}
}

func curveName(c tls.CurveID) string {
	switch c {
	case tls.X25519:
		return "X25519"
	case tls.CurveP256:
		return "P256"
	case tls.CurveP384:
		return "P384"
	case tls.X25519MLKEM768:
		return "X25519MLKEM768"
	}
	return fmt.Sprintf("id_%d", uint16(c))
}


// countingConn — UDP 데이터그램의 개수와 크기를 기록하는 래퍼.
// tcpdump 없이, 권한 없이 패킷 수준 관찰이 가능하다.
type countingConn struct {
	net.PacketConn
	sent []int // 송신 데이터그램 크기 (바이트)
	rcvd []int // 수신 데이터그램 크기
}

func (c *countingConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.sent = append(c.sent, len(b))
	return c.PacketConn.WriteTo(b, addr)
}

func (c *countingConn) ReadFrom(b []byte) (int, net.Addr, error) {
	n, addr, err := c.PacketConn.ReadFrom(b)
	if err == nil {
		c.rcvd = append(c.rcvd, n)
	}
	return n, addr, err
}

func sum(xs []int) int {
	t := 0
	for _, x := range xs {
		t += x
	}
	return t
}

// 단일 핸드셰이크를 수행하며 데이터그램 크기를 보고한다
func runProbe(addr, group string, timeoutMs int) {
	cid, err := curveOf(group)
	if err != nil {
		log.Fatal(err)
	}
	udpAddr, err := net.ResolveUDPAddr("udp", addr)
	if err != nil {
		log.Fatal(err)
	}
	pc, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4zero, Port: 0})
	if err != nil {
		log.Fatal(err)
	}
	cc := &countingConn{PacketConn: pc}
	tr := &quic.Transport{Conn: cc}
	defer tr.Close()

	tlsConf := &tls.Config{
		InsecureSkipVerify: true,
		NextProtos:         []string{alpn},
		MinVersion:         tls.VersionTLS13,
		CurvePreferences:   []tls.CurveID{cid},
	}
	qConf := &quic.Config{
		HandshakeIdleTimeout:    time.Duration(timeoutMs) * time.Millisecond,
		MaxIdleTimeout:          10 * time.Second,
		DisablePathMTUDiscovery: true,
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutMs)*time.Millisecond)
	defer cancel()

	t0 := time.Now()
	conn, err := tr.Dial(ctx, udpAddr, tlsConf, qConf)
	el := float64(time.Since(t0).Microseconds()) / 1000.0
	if err != nil {
		fmt.Printf("group=%s  핸드셰이크 실패: %v\n", group, err)
		fmt.Printf("  송신 %d개 %v\n", len(cc.sent), cc.sent)
		return
	}
	neg := curveName(conn.ConnectionState().TLS.CurveID)
	conn.CloseWithError(0, "bye")
	time.Sleep(50 * time.Millisecond)

	fmt.Printf("group=%-18s negotiated=%-18s HCT=%.3fms\n", group, neg, el)
	fmt.Printf("  클라이언트 송신: %d개 데이터그램, 총 %d B  %v\n", len(cc.sent), sum(cc.sent), cc.sent)
	fmt.Printf("  클라이언트 수신: %d개 데이터그램, 총 %d B  %v\n", len(cc.rcvd), sum(cc.rcvd), cc.rcvd)
	if len(cc.sent) > 0 && len(cc.rcvd) > 0 {
		fmt.Printf("  증폭비(수신/송신): %.2f  (RFC 9000 §8.1 한도 3.0)\n",
			float64(sum(cc.rcvd))/float64(sum(cc.sent)))
	}
}

func main() {
	mode := flag.String("mode", "client", "server | client | probe")
	addr := flag.String("addr", "127.0.0.1:44433", "주소:포트")
	group := flag.String("group", "X25519MLKEM768", "키 교환 그룹")
	iters := flag.Int("iters", 100, "측정 반복 횟수")
	warmup := flag.Int("warmup", 10, "워밍업 횟수 (통계 제외)")
	timeout := flag.Int("timeout", 5000, "핸드셰이크 타임아웃 (ms)")
	csvPath := flag.String("csv", "", "원자료 CSV 경로")
	qlogDir := flag.String("qlog", "", "qlog 출력 디렉터리 (비우면 비활성)")
	flag.Parse()

	switch *mode {
	case "server":
		runServer(*addr, *group, *qlogDir)
	case "client":
		runClient(*addr, *group, *iters, *warmup, *timeout, *csvPath, *qlogDir)
	case "probe":
		runProbe(*addr, *group, *timeout)
	default:
		log.Fatal("mode는 server | client | probe")
	}
}
