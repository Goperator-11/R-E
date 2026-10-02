// QUIC client for the PQ-AFEC testbed.
//
// Times N real handshakes and prints one JSON line per trial.  The measured
// interval is exactly quic.DialAddr, which returns when the handshake has
// completed, so process startup is measured once and never enters a sample.
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/quic-go/quic-go"
)

type trial struct {
	I        int     `json:"i"`
	Ms       float64 `json:"ms"`
	OK       bool    `json:"ok"`
	Group    string  `json:"group"`
	Err      string  `json:"err,omitempty"`
	KEM      uint16  `json:"kem_id"`
	CipherID uint16  `json:"cipher_id"`
}

func curveFor(name string) tls.CurveID {
	switch name {
	case "x25519":
		return tls.X25519
	case "X25519MLKEM768", "mlkem":
		return tls.X25519MLKEM768
	case "secp256r1", "p256":
		return tls.CurveP256
	}
	return tls.X25519MLKEM768
}

func main() {
	addr := flag.String("addr", "10.9.0.2:4433", "server address")
	group := flag.String("group", "X25519MLKEM768", "key exchange group")
	n := flag.Int("n", 100, "number of handshakes")
	timeout := flag.Duration("timeout", 12*time.Second, "per-handshake timeout")
	gap := flag.Duration("gap", 25*time.Millisecond, "gap between handshakes")
	flag.Parse()

	enc := json.NewEncoder(os.Stdout)
	for i := 0; i < *n; i++ {
		tlsConf := &tls.Config{
			InsecureSkipVerify: true,
			NextProtos:         []string{"pqafec"},
			MinVersion:         tls.VersionTLS13,
			CurvePreferences:   []tls.CurveID{curveFor(*group)},
		}
		// A fresh handshake every time: no session resumption, no 0-RTT, and
		// crucially no cached RTT - which is the situation the research is
		// about (first contact, no RTT sample, loss falls through to PTO).
		qconf := &quic.Config{
			MaxIdleTimeout:  *timeout,
			KeepAlivePeriod: 0,
			Allow0RTT:       false,
		}
		ctx, cancel := context.WithTimeout(context.Background(), *timeout)
		start := time.Now()
		conn, err := quic.DialAddr(ctx, *addr, tlsConf, qconf)
		el := time.Since(start)
		cancel()

		t := trial{I: i, Ms: float64(el.Microseconds()) / 1000.0,
			OK: err == nil, Group: *group}
		if err != nil {
			t.Err = err.Error()
		} else {
			cs := conn.ConnectionState().TLS
			t.CipherID = cs.CipherSuite
			t.KEM = uint16(cs.CurveID)
			conn.CloseWithError(0, "done")
		}
		enc.Encode(&t)
		os.Stdout.Sync()
		if *gap > 0 {
			time.Sleep(*gap)
		}
	}
	fmt.Fprintln(os.Stderr, "DONE")
}
