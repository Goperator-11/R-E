package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestCertificateExactSizeAndDeterministicBytes(t *testing.T) {
	for _, size := range []int{512, 513, 600, 1023, 1024, 1025, 2047, 2048, 2049, 2955, 4032, 5299, 6000, 6200, 7700, 8000, 9000, 12000, 14000, 16000, 18000, 32767, 32768, 65535, 65536, maxCertificateDER} {
		t.Run(fmt.Sprint(size), func(t *testing.T) {
			a, err := deterministicCertificate(size)
			if err != nil {
				t.Fatal(err)
			}
			b, err := deterministicCertificate(size)
			if err != nil {
				t.Fatal(err)
			}
			x, err := certificatePEM(a)
			if err != nil {
				t.Fatal(err)
			}
			y, err := certificatePEM(b)
			if err != nil || !bytes.Equal(x, y) || len(a.Certificate[0]) != size {
				t.Fatalf("certificate is not exact and deterministic: %d %v", len(a.Certificate[0]), err)
			}
			if _, ok := a.PrivateKey.(*ecdsa.PrivateKey); !ok {
				t.Fatal("TLS CertificateVerify key type changed")
			}
			if err := a.Leaf.CheckSignature(a.Leaf.SignatureAlgorithm, a.Leaf.RawTBSCertificate, a.Leaf.Signature); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestCertificateFileRoundTripAndMetadata(t *testing.T) {
	path := filepath.Join(preservedTempDir(t), "shared.pem")
	preview, err := generateCertificateFile(6000, path, true)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("dry run wrote a file")
	}
	created, err := generateCertificateFile(6000, path, false)
	if err != nil {
		t.Fatal(err)
	}
	if preview.DERSHA256 != created.DERSHA256 || preview.FileSHA256 != created.FileSHA256 {
		t.Fatal("dry run and saved certificate differ")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 3; i++ {
		cert, meta, err := serverCertificate(6000, path)
		if err != nil || meta.DERSHA256 != created.DERSHA256 || meta.FileSHA256 != fmt.Sprintf("%x", sha256.Sum256(data)) || len(cert.Certificate[0]) != 6000 {
			t.Fatalf("server certificate identity changed: %+v %v", meta, err)
		}
		conn := &decodeConn{certMeta: &meta}
		report, err := json.Marshal(conn.report())
		if err != nil {
			t.Fatal(err)
		}
		var parsed struct {
			Certificate certificateMetadata `json:"certificate"`
		}
		if json.Unmarshal(report, &parsed) != nil || parsed.Certificate != meta {
			t.Fatal("stats lost certificate identity")
		}
	}
	if _, err := generateCertificateFile(6000, path, false); err == nil {
		t.Fatal("existing certificate was overwritten")
	}
	after, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(data, after) {
		t.Fatal("failed generation changed saved file")
	}
}

func TestCertificateRejectsInvalidInputs(t *testing.T) {
	for _, size := range []int{-1, 0, 511, maxCertificateDER + 1} {
		if _, err := deterministicCertificate(size); err == nil {
			t.Fatalf("accepted size %d", size)
		}
	}
	folder := preservedTempDir(t)
	cert := makeCert(2955)
	valid, err := certificatePEM(cert)
	if err != nil {
		t.Fatal(err)
	}
	other := makeCert(6000)
	key, err := x509.MarshalPKCS8PrivateKey(other.PrivateKey)
	if err != nil {
		t.Fatal(err)
	}
	mismatch := append(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Certificate[0]}), pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: key})...)
	for name, data := range map[string][]byte{
		"empty": nil, "garbage": []byte("not PEM"), "trailing": append(append([]byte{}, valid...), 'x'),
		"multiple": append(append([]byte{}, valid...), valid...), "mismatched_key": mismatch,
		"oversize": make([]byte, 2*maxCertificateDER+1),
	} {
		t.Run(name, func(t *testing.T) {
			path := filepath.Join(folder, name+".pem")
			if err := os.WriteFile(path, data, 0600); err != nil {
				t.Fatal(err)
			}
			if _, _, err := serverCertificate(2955, path); err == nil {
				t.Fatal("invalid file accepted or silently replaced")
			}
		})
	}
	path := filepath.Join(folder, "valid.pem")
	if err := os.WriteFile(path, valid, 0600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := serverCertificate(2956, path); err == nil {
		t.Fatal("wrong DER target accepted")
	}
	if _, _, err := serverCertificate(2955, filepath.Join(folder, "missing.pem")); err == nil {
		t.Fatal("missing file silently generated")
	}
}
