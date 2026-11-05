package main

import (
	"bytes"
	"crypto"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/pem"
	"fmt"
	"io"
	"math/big"
	"os"
	"time"
)

const certificateRecipe = "padfec-testbed-p256-rfc6979-v1"
const maxCertificateDER = 1 << 20

type certificateSigner struct {
	*ecdsa.PrivateKey
}

func (s certificateSigner) Sign(_ io.Reader, digest []byte, opts crypto.SignerOpts) ([]byte, error) {
	return s.PrivateKey.Sign(nil, digest, opts)
}

type certificateMetadata struct {
	Label      string `json:"label"`
	Recipe     string `json:"recipe"`
	Source     string `json:"source"`
	Path       string `json:"path,omitempty"`
	DERBytes   int    `json:"der_bytes"`
	DERSHA256  string `json:"der_sha256"`
	FileSHA256 string `json:"file_sha256"`
	KeyType    string `json:"key_type"`
}

func deterministicCertificate(size int) (tls.Certificate, error) {
	if size < 512 || size > maxCertificateDER {
		return tls.Certificate{}, fmt.Errorf("certificate DER target must be 512..%d bytes", maxCertificateDER)
	}
	var key *ecdsa.PrivateKey
	for counter := 0; counter < 256; counter++ {
		seed := sha256.Sum256([]byte(fmt.Sprintf("%s/key/%d/%d", certificateRecipe, size, counter)))
		candidate, err := ecdsa.ParseRawPrivateKey(elliptic.P256(), seed[:])
		if err == nil {
			key = candidate
			break
		}
	}
	if key == nil {
		return tls.Certificate{}, fmt.Errorf("certificate seed did not produce a P-256 key")
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "padfec-testbed"},
		NotBefore: time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC),
		NotAfter:  time.Date(2040, 1, 1, 0, 0, 0, 0, time.UTC),
		KeyUsage:  x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		DNSNames: []string{"padfec.test"}, BasicConstraintsValid: true,
		SignatureAlgorithm: x509.ECDSAWithSHA256,
	}
	for trial := 0; trial < 64; trial++ {
		fillSize := size - 450
		for adjustment := 0; adjustment < 12; adjustment++ {
			if fillSize < 0 || fillSize > maxCertificateDER {
				break
			}
			filler := make([]byte, fillSize)
			for offset := 0; offset < len(filler); offset += sha256.Size {
				block := sha256.Sum256([]byte(fmt.Sprintf("%s/filler/%d/%d/%d", certificateRecipe, size, trial, offset)))
				copy(filler[offset:], block[:])
			}
			template.ExtraExtensions = []pkix.Extension{{Id: asn1.ObjectIdentifier{1, 3, 6, 1, 4, 1, 99999, 1}, Value: filler}}
			der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, certificateSigner{key})
			if err != nil {
				return tls.Certificate{}, err
			}
			if len(der) == size {
				leaf, err := x509.ParseCertificate(der)
				if err != nil {
					return tls.Certificate{}, err
				}
				return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key, Leaf: leaf}, nil
			}
			fillSize += size - len(der)
		}
	}
	return tls.Certificate{}, fmt.Errorf("cannot construct exact certificate DER size %d", size)
}

func makeCert(size int) tls.Certificate {
	cert, err := deterministicCertificate(size)
	if err != nil {
		panic(err)
	}
	return cert
}

func certificatePEM(cert tls.Certificate) ([]byte, error) {
	key, err := x509.MarshalPKCS8PrivateKey(cert.PrivateKey)
	if err != nil {
		return nil, err
	}
	data := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Certificate[0]})
	return append(data, pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: key})...), nil
}

func certificateInfo(cert tls.Certificate, data []byte, source, path string) certificateMetadata {
	return certificateMetadata{Label: "development", Recipe: certificateRecipe, Source: source, Path: path,
		DERBytes: len(cert.Certificate[0]), DERSHA256: fmt.Sprintf("%x", sha256.Sum256(cert.Certificate[0])),
		FileSHA256: fmt.Sprintf("%x", sha256.Sum256(data)), KeyType: "ECDSA_P256"}
}

func readCertificateFile(size int, path string) (tls.Certificate, certificateMetadata, error) {
	var empty tls.Certificate
	var meta certificateMetadata
	if size < 512 || size > maxCertificateDER {
		return empty, meta, fmt.Errorf("invalid certificate DER target")
	}
	file, err := os.Open(path)
	if err != nil {
		return empty, meta, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 2*maxCertificateDER+1))
	if err != nil || len(data) > 2*maxCertificateDER {
		return empty, meta, fmt.Errorf("cannot read bounded certificate bundle: %v", err)
	}
	rest := data
	for _, kind := range []string{"CERTIFICATE", "PRIVATE KEY"} {
		block, remaining := pem.Decode(rest)
		if block == nil || block.Type != kind || len(block.Headers) != 0 {
			return empty, meta, fmt.Errorf("certificate bundle must contain one certificate and one PKCS#8 key")
		}
		rest = remaining
	}
	if len(bytes.TrimSpace(rest)) != 0 {
		return empty, meta, fmt.Errorf("unexpected trailing certificate bundle content")
	}
	cert, err := tls.X509KeyPair(data, data)
	if err != nil {
		return empty, meta, err
	}
	if len(cert.Certificate) != 1 || len(cert.Certificate[0]) != size {
		return empty, meta, fmt.Errorf("certificate DER does not match target %d", size)
	}
	key, ok := cert.PrivateKey.(*ecdsa.PrivateKey)
	if !ok || key.Curve != elliptic.P256() {
		return empty, meta, fmt.Errorf("testbed certificate must use ECDSA P-256")
	}
	leaf, err := x509.ParseCertificate(cert.Certificate[0])
	if err != nil {
		return empty, meta, err
	}
	if err := leaf.CheckSignature(leaf.SignatureAlgorithm, leaf.RawTBSCertificate, leaf.Signature); err != nil {
		return empty, meta, err
	}
	cert.Leaf = leaf
	meta = certificateInfo(cert, data, "file", path)
	meta.Recipe = "external_file"
	return cert, meta, nil
}

func serverCertificate(size int, path string) (tls.Certificate, certificateMetadata, error) {
	if path != "" {
		return readCertificateFile(size, path)
	}
	cert, err := deterministicCertificate(size)
	if err != nil {
		return tls.Certificate{}, certificateMetadata{}, err
	}
	data, err := certificatePEM(cert)
	return cert, certificateInfo(cert, data, "deterministic_in_memory", ""), err
}

func generateCertificateFile(size int, path string, dryRun bool) (certificateMetadata, error) {
	cert, err := deterministicCertificate(size)
	if err != nil {
		return certificateMetadata{}, err
	}
	data, err := certificatePEM(cert)
	if err != nil {
		return certificateMetadata{}, err
	}
	meta := certificateInfo(cert, data, "generated_file", path)
	if dryRun {
		meta.Source = "dry_run"
		return meta, nil
	}
	if path == "" {
		return certificateMetadata{}, fmt.Errorf("certgen requires -cert-file")
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return certificateMetadata{}, err
	}
	_, writeErr := file.Write(data)
	closeErr := file.Close()
	if writeErr != nil {
		return certificateMetadata{}, writeErr
	}
	return meta, closeErr
}
