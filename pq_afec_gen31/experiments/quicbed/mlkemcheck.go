package main

import (
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"time"
)

func groupName(id tls.CurveID) string {
	switch id {
	case tls.X25519MLKEM768:
		return "X25519MLKEM768"
	case tls.X25519:
		return "x25519"
	case tls.CurveP256:
		return "secp256r1"
	}
	return fmt.Sprint("unknown(", uint16(id), ")")
}

type result struct {
	OK         bool   `json:"ok"`
	Addr       string `json:"addr"`
	Group      string `json:"group"`
	GroupID    uint16 `json:"group_id"`
	Version    uint16 `json:"tls_version"`
	Cipher     uint16 `json:"cipher"`
	Err        string `json:"err,omitempty"`
	PeerCerts  int    `json:"peer_certs"`
	ElapsedMs  float64 `json:"elapsed_ms"`
}

func main() {
	addr := flag.String("addr", "127.0.0.1:44443", "TLS server address")
	group := flag.String("group", "X25519MLKEM768", "key exchange group")
	timeout := flag.Duration("timeout", 15*time.Second, "dial timeout")
	flag.Parse()

	var cid tls.CurveID
	switch *group {
	case "x25519":
		cid = tls.X25519
	case "secp256r1":
		cid = tls.CurveP256
	default:
		cid = tls.X25519MLKEM768
	}

	r := result{Addr: *addr, Group: *group}
	d := &net.Dialer{Timeout: *timeout}
	start := time.Now()
	conn, err := tls.DialWithDialer(d, "tcp", *addr, &tls.Config{
		InsecureSkipVerify: true,
		MinVersion:         tls.VersionTLS13,
		MaxVersion:         tls.VersionTLS13,
		CurvePreferences:   []tls.CurveID{cid},
	})
	r.ElapsedMs = float64(time.Since(start).Microseconds()) / 1000.0
	if err != nil {
		r.Err = err.Error()
	} else {
		st := conn.ConnectionState()
		r.OK = true
		r.Version = st.Version
		r.Cipher = st.CipherSuite
		r.GroupID = uint16(st.CurveID)
		r.Group = groupName(st.CurveID)
		r.PeerCerts = len(st.PeerCertificates)
		conn.Close()
	}
	b, _ := json.Marshal(&r)
	fmt.Println(string(b))
	if !r.OK {
		os.Exit(1)
	}
}
