package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/binary"
	"encoding/json"
	"flag"
	"fmt"
	"math/big"
	"os"
	"sort"
	"time"

	"github.com/quic-go/quic-go"
)

func selfSigned() tls.Certificate {
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "pqafec-data"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
	}
	der, _ := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
}

func qconf() *quic.Config {
	return &quic.Config{
		EnableDatagrams: true,
		MaxIdleTimeout:  30 * time.Second,
		KeepAlivePeriod: 0,
	}
}

type summary struct {
	Sent      int     `json:"sent"`
	Received  int     `json:"received"`
	Lost      int     `json:"lost"`
	LossRate  float64 `json:"loss_rate"`
	DurMs     float64 `json:"duration_ms"`
	GoodputMb float64 `json:"goodput_mbps"`
	Size      int     `json:"payload_bytes"`
	LatP50Ms  float64 `json:"latency_p50_ms"`
	LatP95Ms  float64 `json:"latency_p95_ms"`
	LatP99Ms  float64 `json:"latency_p99_ms"`
	LatMaxMs  float64 `json:"latency_max_ms"`
	LatMeanMs float64 `json:"latency_mean_ms"`
	LatSamples int `json:"latency_samples"`
	LatSkipped map[string]int `json:"latency_skipped"`
}

func runServer(addr string, n int, size int, out string) {
	tlsConf := &tls.Config{
		Certificates: []tls.Certificate{selfSigned()},
		NextProtos:   []string{"pqafec-data"},
		MinVersion:   tls.VersionTLS13,
		CurvePreferences: []tls.CurveID{
			tls.X25519MLKEM768, tls.X25519,
		},
	}
	ln, err := quic.ListenAddr(addr, tlsConf, qconf())
	if err != nil {
		fmt.Fprintln(os.Stderr, "listen:", err)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "READY %s\n", addr)
	os.Stderr.Sync()

	conn, err := ln.Accept(context.Background())
	if err != nil {
		os.Exit(1)
	}
	seen := make([]bool, n)
	got := 0
	var first, last time.Time
	lat := make([]float64, 0, n)
	latSkipShort, latSkipNeg, latSkipHuge := 0, 0, 0
	deadline := time.Now().Add(120 * time.Second)
	for got < n && time.Now().Before(deadline) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		msg, err := conn.ReceiveDatagram(ctx)
		cancel()
		if err != nil {
			break
		}
		if len(msg) < 12 {
			latSkipShort++
			continue
		}
		seq := int(binary.BigEndian.Uint32(msg[:4]))
		if seq < 0 || seq >= n || seen[seq] {
			continue
		}
		seen[seq] = true
		got++
		now := time.Now()
		sentNs := int64(binary.BigEndian.Uint64(msg[4:12]))
		if sentNs > 0 {
			d := float64(now.UnixNano()-sentNs) / 1e6
			if d < 0 {
				latSkipNeg++
			} else if d >= 60000 {
				latSkipHuge++
			} else {
				lat = append(lat, d)
			}
		}
		if first.IsZero() {
			first = now
		}
		last = now
	}
	dur := last.Sub(first).Seconds()
	s := summary{Sent: n, Received: got, Lost: n - got,
		LossRate: float64(n-got) / float64(n), Size: size,
		DurMs: dur * 1000}
	if dur > 0 {
		s.GoodputMb = float64(got*size*8) / dur / 1e6
	}
	s.LatSamples = len(lat)
	s.LatSkipped = map[string]int{"short": latSkipShort, "negative": latSkipNeg,
		"huge": latSkipHuge}
	if len(lat) > 0 {
		sort.Float64s(lat)
		q := func(f float64) float64 {
			i := int(f * float64(len(lat)-1))
			return lat[i]
		}
		sum := 0.0
		for _, v := range lat {
			sum += v
		}
		s.LatP50Ms, s.LatP95Ms = q(0.50), q(0.95)
		s.LatP99Ms, s.LatMaxMs = q(0.99), lat[len(lat)-1]
		s.LatMeanMs = sum / float64(len(lat))
	}
	b, _ := json.Marshal(&s)
	if out != "" {
		os.WriteFile(out, b, 0644)
	}
	fmt.Println(string(b))
}

func runClient(addr string, n int, size int, pps float64) {
	tlsConf := &tls.Config{
		InsecureSkipVerify: true,
		NextProtos:         []string{"pqafec-data"},
		MinVersion:         tls.VersionTLS13,
		CurvePreferences:   []tls.CurveID{tls.X25519MLKEM768},
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	conn, err := quic.DialAddr(ctx, addr, tlsConf, qconf())
	cancel()
	if err != nil {
		fmt.Fprintln(os.Stderr, "dial:", err)
		os.Exit(1)
	}
	payload := make([]byte, size)
	rand.Read(payload[4:])
	interval := time.Duration(float64(time.Second) / pps)
	start := time.Now()
	skipped := 0
	sentCount := 0
	for i := 0; i < n; i++ {
		binary.BigEndian.PutUint32(payload[:4], uint32(i))
		binary.BigEndian.PutUint64(payload[4:12], uint64(time.Now().UnixNano()))
		if err := conn.SendDatagram(payload); err != nil {
			skipped++
		} else {
			sentCount++
		}
		target := start.Add(time.Duration(i+1) * interval)
		if d := time.Until(target); d > 0 {
			time.Sleep(d)
		}
	}
	fmt.Fprintf(os.Stderr, "SENT %d SKIPPED %d OFFERED %d ELAPSED_MS %.1f\n",
		sentCount, skipped, n,
		float64(time.Since(start).Microseconds())/1000.0)
	time.Sleep(1500 * time.Millisecond)
	conn.CloseWithError(0, "done")
	fmt.Fprintf(os.Stderr, "SENT %d in %.1f ms\n", n,
		float64(time.Since(start).Microseconds())/1000.0)
}

func main() {
	role := flag.String("role", "client", "client|server")
	addr := flag.String("addr", "127.0.0.1:4444", "address")
	n := flag.Int("n", 4000, "datagrams")
	size := flag.Int("size", 1100, "payload bytes")
	pps := flag.Float64("pps", 2000, "datagrams per second")
	out := flag.String("out", "", "server: write summary JSON here")
	flag.Parse()
	if *role == "server" {
		runServer(*addr, *n, *size, *out)
	} else {
		runClient(*addr, *n, *size, *pps)
	}
}
