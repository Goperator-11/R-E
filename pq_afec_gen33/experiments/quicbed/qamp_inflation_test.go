package main

import "testing"

func TestInflationFlagsAndDescription(t *testing.T) {
	for _, n := range []int{0, 1, 63, 64, 1280, 2560, 8192} {
		for _, mode := range []string{"off", "buf"} {
			if checkInflationFlags(n, "client", mode) != nil {
				t.Fatal(n, mode)
			}
		}
		h := inflationFor(n)
		if h.Bytes != n {
			t.Fatal(h)
		}
		if n == 0 {
			if h.Source != "disabled" || h.ParameterID != 0 || h.EncodedBytes != 0 {
				t.Fatal(h)
			}
		} else if h.ParameterID != 9730 || h.EncodedBytes != n+3+min(1, n/64) || h.Source != "quic_go_v061_development_tp_hook" {
			t.Fatal(h)
		}
	}
	for _, n := range []int{-1, 8193} {
		if checkInflationFlags(n, "client", "off") == nil {
			t.Fatal(n)
		}
	}
	for _, mode := range []string{"on", "fec", "auto", "auto3"} {
		if checkInflationFlags(1280, "client", mode) == nil {
			t.Fatal(mode)
		}
	}
	if checkInflationFlags(1, "server", "off") == nil || checkInflationFlags(0, "server", "off") != nil {
		t.Fatal("server flags")
	}
}

func TestInitialSizeEffectiveAndInput(t *testing.T) {
	for _, v := range [][2]int{{0, 1280}, {1, 1200}, {1199, 1200}, {1200, 1200}, {1291, 1291}, {1341, 1341}, {1350, 1350}, {1452, 1452}, {1472, 1452}, {65535, 1452}} {
		if checkInitialSize(v[0]) != nil || effectiveInitialSize(v[0]) != v[1] {
			t.Fatal(v, effectiveInitialSize(v[0]))
		}
	}
	for _, n := range []int{-1, 65536} {
		if checkInitialSize(n) == nil {
			t.Fatal(n)
		}
	}
}
