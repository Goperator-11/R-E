// mlkemcheck - 우리가 쓰는 ML-KEM 이 표준의 그것과 같은지 확인한다.
//
// 인수인계 문서의 환경에는 OpenSSL 3.5 가 있고, 표 1-1 은 X25519MLKEM768 을
// 쓴다. "ML-KEM 도 똑같이 구현" 을 말로 주장하지 않고 두 가지로 보인다.
//
//   1) 크기 - X25519MLKEM768 의 키셰어는 1,216 B 여야 한다.
//      = X25519 공개키 32 B + ML-KEM-768 캡슐화키 1,184 B (FIPS 203)
//      서버 키셰어는 1,120 B = 32 + ML-KEM-768 암호문 1,088 B
//
//   2) 상호운용 - Go 의 crypto/tls 클라이언트가 **OpenSSL 3.5.5 서버**와
//      X25519MLKEM768 로 TLS 1.3 핸드셰이크를 끝내는가. 서로 다른 두
//      구현이 같은 비밀에 도달해야만 핸드셰이크가 끝나므로, 이것이
//      "같은 ML-KEM 인가" 에 대한 가장 강한 증거다.
//
// 크기만 맞고 상호운용이 안 되면 구현이 다른 것이고, 상호운용이 되면
// FIPS 203 의 같은 알고리즘이다.
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
