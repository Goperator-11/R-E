// QUIC server for the PQ-AFEC testbed.
//
// Go's crypto/tls speaks X25519MLKEM768 natively, so this is a REAL ML-KEM
// QUIC handshake - not an emulation.  The certificate chain is padded to a
// configurable DER size so the server flight matches what a real web server
// sends (measured in E3: Cloudflare 2,955 B, Google 5,299 B).
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
	"flag"
	"fmt"
	"math/big"
	"os"
	"time"

	"github.com/quic-go/quic-go"
)

func makeCert(padTo int) tls.Certificate {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		panic(err)
	}
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "pqafec-testbed"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(24 * time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames:     []string{"pqafec.test"},
		IsCA:         false,
		BasicConstraintsValid: true,
	}
	// Pad with a dummy non-critical extension until the DER hits the target
	// size, so the server's Handshake flight is realistically large.
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
	fmt.Fprintf(os.Stderr, "cert DER = %d bytes\n", len(der))
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
}

func main() {
	addr := flag.String("addr", "0.0.0.0:4433", "listen address")
	certSize := flag.Int("certsize", 2955, "target certificate DER size")
	flag.Parse()

	tlsConf := &tls.Config{
		Certificates: []tls.Certificate{makeCert(*certSize)},
		NextProtos:   []string{"pqafec"},
		MinVersion:   tls.VersionTLS13,
		CurvePreferences: []tls.CurveID{
			tls.X25519MLKEM768, tls.X25519, tls.CurveP256,
		},
	}
	ln, err := quic.ListenAddr(*addr, tlsConf, &quic.Config{
		MaxIdleTimeout:  30 * time.Second,
		KeepAlivePeriod: 0,
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "listen:", err)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "READY %s\n", *addr)
	os.Stderr.Sync()

	for {
		conn, err := ln.Accept(context.Background())
		if err != nil {
			continue
		}
		go func(c *quic.Conn) {
			<-c.Context().Done()
		}(conn)
	}
}
