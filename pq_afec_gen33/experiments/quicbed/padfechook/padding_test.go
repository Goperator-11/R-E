package padfechook

import (
	"bytes"
	"github.com/quic-go/quic-go/internal/protocol"
	"github.com/quic-go/quic-go/internal/wire"
	"testing"
)

func readVarint(b []byte) (uint64, int) {
	n := 1 << uint(b[0]>>6)
	v := uint64(b[0] & 63)
	for _, x := range b[1:n] {
		v = v<<8 | uint64(x)
	}
	return v, n
}

func params(b []byte) map[uint64][]byte {
	out := map[uint64][]byte{}
	for len(b) > 0 {
		id, n := readVarint(b)
		b = b[n:]
		size, n := readVarint(b)
		b = b[n:]
		out[id] = b[:size]
		b = b[size:]
	}
	return out
}

func TestPaddingValidationAndWireLength(t *testing.T) {
	for _, n := range []int{0, 1, 63, 64, 1280, 2560, 8192} {
		if Validate(n) != nil {
			t.Fatal(n)
		}
		want := n + 3
		if n >= 64 {
			want = n + 4
		}
		if n == 0 {
			want = 0
		}
		if EncodedBytes(n) != want {
			t.Fatal(n, EncodedBytes(n), want)
		}
	}
	for _, n := range []int{-1, 8193, 65536} {
		if Validate(n) == nil {
			t.Fatal(n)
		}
	}
	if ParameterID != 27+31*313 || ParameterID <= 27+31*255 {
		t.Fatal(ParameterID)
	}
}

func TestPaddingClientOnlyAndFrozen(t *testing.T) {
	p := &wire.TransportParameters{}
	if _, ok := params(p.Marshal(protocol.PerspectiveClient))[ParameterID]; ok {
		t.Fatal("nonzero default")
	}
	if err := Configure(8193); err == nil || configured {
		t.Fatal("invalid config changed state")
	}
	if err := Configure(1280); err != nil {
		t.Fatal(err)
	}
	got := params(p.Marshal(protocol.PerspectiveClient))[ParameterID]
	if !bytes.Equal(got, make([]byte, 1280)) {
		t.Fatal(len(got))
	}
	if _, ok := params(p.Marshal(protocol.PerspectiveServer))[ParameterID]; ok {
		t.Fatal("server inflated")
	}
	if err := Configure(1280); err != nil {
		t.Fatal(err)
	}
	if err := Configure(0); err == nil {
		t.Fatal("runtime mutation accepted")
	}
	if len(wire.AdditionalTransportParametersClient[ParameterID]) != 1280 {
		t.Fatal("changed after rejection")
	}
}
