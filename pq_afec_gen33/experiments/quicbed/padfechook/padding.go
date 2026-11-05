package padfechook

import (
	"fmt"
	"github.com/quic-go/quic-go/internal/wire"
	"github.com/quic-go/quic-go/quicvarint"
	"sync"
)

const ParameterID uint64 = 9730
const MaxPadding = 8192

var configMu sync.Mutex
var configured bool
var configuredBytes int

func Validate(n int) error {
	if n < 0 || n > MaxPadding {
		return fmt.Errorf("k-inflate must be between 0 and %d bytes", MaxPadding)
	}
	return nil
}

func EncodedBytes(n int) int {
	if n == 0 {
		return 0
	}
	return quicvarint.Len(ParameterID) + quicvarint.Len(uint64(n)) + n
}

func Configure(n int) error {
	if err := Validate(n); err != nil {
		return err
	}
	configMu.Lock()
	defer configMu.Unlock()
	if configured {
		if n != configuredBytes {
			return fmt.Errorf("ClientHello padding is already fixed at %d bytes", configuredBytes)
		}
		return nil
	}
	if len(wire.AdditionalTransportParametersClient) != 0 {
		return fmt.Errorf("additional transport parameters already configured")
	}
	if n > 0 {
		wire.AdditionalTransportParametersClient = map[uint64][]byte{ParameterID: make([]byte, n)}
	}
	configured = true
	configuredBytes = n
	return nil
}
