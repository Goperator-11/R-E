package main

import "fmt"

type revisitGuardConfig struct {
	Enabled        bool
	DecoderSupport string
}

type revisitGuardObservation struct {
	Version           int    `json:"version"`
	DecoderSupport    string `json:"decoder_support"`
	InitialSeen       bool   `json:"initial_seen"`
	InitialTokenBytes int    `json:"initial_token_bytes"`
	TokenInputSource  string `json:"token_input_source"`
	ServerAcceptance  string `json:"server_acceptance"`
	RetryAccepted     bool   `json:"retry_accepted"`
	RetryConsumed     bool   `json:"retry_consumed"`
	BundlesReserved   int    `json:"bundles_reserved"`
}

func newRevisitGuard(config revisitGuardConfig) *revisitGuardObservation {
	if !config.Enabled {
		return nil
	}
	return &revisitGuardObservation{Version: 1, DecoderSupport: config.DecoderSupport, TokenInputSource: "first_initial_header", ServerAcceptance: "unknown"}
}

func checkRevisitGuard(config revisitGuardConfig, mode, fec, layout string, ips, m int, pad, dup bool) error {
	if config.DecoderSupport != "unknown" && config.DecoderSupport != "supported" && config.DecoderSupport != "unsupported" {
		return fmt.Errorf("decoder-support must be unknown, supported, or unsupported")
	}
	if !config.Enabled {
		if config.DecoderSupport != "unknown" {
			return fmt.Errorf("decoder-support requires revisit-guard")
		}
		return nil
	}
	if mode != "client" || fec != "fec" || layout != "v3" || (ips != 0 && ips != 1280) || m < 1 || m > 4 {
		return fmt.Errorf("revisit-guard requires fixed client fec, layout v3, ips 0 or 1280, and m 1..4")
	}
	if !pad && !dup && config.DecoderSupport != "supported" {
		return fmt.Errorf("parity with revisit-guard requires explicit supported decoder")
	}
	return nil
}

func (c *fecConn) observeRevisitInitialLocked(b []byte, h longHdr) error {
	if c.revisitGuard == nil || c.revisitGuard.InitialSeen || !h.ok || h.typ != 0 {
		return nil
	}
	if h.version != 1 || h.bodyOff >= len(b) {
		return fmt.Errorf("revisit-guard requires a complete QUIC v1 Initial")
	}
	n, size := readVarint(b[h.bodyOff:])
	if size == 0 || n >= uint64(len(b)-h.bodyOff-size) {
		return fmt.Errorf("revisit-guard invalid Initial token length")
	}
	pos := h.bodyOff + size + int(n)
	payload, length := readVarint(b[pos:])
	if length == 0 || payload == 0 || payload > uint64(len(b)-pos-length) {
		return fmt.Errorf("revisit-guard invalid Initial packet length")
	}
	c.revisitGuard.InitialSeen = true
	c.revisitGuard.InitialTokenBytes = int(n)
	return nil
}

func (c *fecConn) acceptedRevisitRetry() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.revisitGuard != nil && !c.txFinal && c.revisitGuard.InitialSeen {
		c.revisitGuard.RetryAccepted = true
	}
}

func (c *fecConn) revisitShapeLocked(shape flightShape) flightShape {
	g := c.revisitGuard
	if g == nil {
		return shape
	}
	first := c.stats.Flights == 0
	retry := !first && g.RetryAccepted && !g.RetryConsumed
	if retry {
		shape.Phase = "retry_bundle"
		g.RetryConsumed = true
	}
	shape.Rule = "revisit_first"
	if g.BundlesReserved > 0 || (!first && !retry) || c.srvBig {
		shape.Lead, shape.Trail = 0, 0
		shape.Rule = "revisit_no_extra"
	} else {
		if g.InitialTokenBytes > 0 || g.RetryAccepted {
			shape.Lead = 0
			shape.Rule = "revisit_recovery_only"
			if c.padJunk {
				shape.Trail = 0
			}
		}
		if c.extraKind() == "parity" && g.DecoderSupport != "supported" {
			shape.Lead, shape.Trail = 0, 0
			shape.Rule = "revisit_decoder_unknown"
		}
	}
	if shape.Lead+shape.Trail > 0 {
		g.BundlesReserved++
	}
	shape.OriginalImmediate = c.curLater
	return shape
}

func (c *fecConn) revisitGuardSnapshot() *revisitGuardObservation {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.revisitGuard == nil {
		return nil
	}
	copy := *c.revisitGuard
	return &copy
}
