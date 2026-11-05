package main

import (
	"fmt"
	padfechook "github.com/quic-go/quic-go/padfec-local-hook"
)

type inflationInfo struct {
	Bytes        int    `json:"bytes"`
	ParameterID  uint64 `json:"parameter_id"`
	EncodedBytes int    `json:"encoded_bytes"`
	Source       string `json:"source"`
}

func inflationFor(n int) inflationInfo {
	if n == 0 {
		return inflationInfo{Source: "disabled"}
	}
	return inflationInfo{Bytes: n, ParameterID: padfechook.ParameterID, EncodedBytes: padfechook.EncodedBytes(n), Source: "quic_go_v061_development_tp_hook"}
}

func checkInflationFlags(n int, mode, fec string) error {
	if err := padfechook.Validate(n); err != nil {
		return err
	}
	if n > 0 && (mode != "client" || (fec != "off" && fec != "buf")) {
		return fmt.Errorf("positive k-inflate requires client with fixed fec off or buf")
	}
	return nil
}

func checkInitialSize(n int) error {
	if n < 0 || n > 65535 {
		return fmt.Errorf("ips must be between 0 and 65535")
	}
	return nil
}

func effectiveInitialSize(n int) int {
	if n == 0 {
		return 1280
	}
	return min(quicgoMaxIPS, max(1200, n))
}
