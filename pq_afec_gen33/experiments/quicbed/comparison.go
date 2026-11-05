package main

import "fmt"

type extraSent struct {
	Kind                   string `json:"kind"`
	Sent                   int    `json:"sent"`
	Bytes                  int64  `json:"bytes"`
	Errors                 int    `json:"errors"`
	ParityBudgetBytes      int64  `json:"parity_budget_bytes"`
	FirstSent              int    `json:"first_sent"`
	FirstBytes             int64  `json:"first_bytes"`
	FirstLead              int    `json:"first_lead"`
	FirstParityBudgetBytes int64  `json:"first_parity_budget_bytes"`
}

func (s *extraSent) add(other extraSent) {
	s.Kind = other.Kind
	s.Sent += other.Sent
	s.Bytes += other.Bytes
	s.Errors += other.Errors
	s.ParityBudgetBytes += other.ParityBudgetBytes
	s.FirstSent += other.FirstSent
	s.FirstBytes += other.FirstBytes
	s.FirstLead += other.FirstLead
	s.FirstParityBudgetBytes += other.FirstParityBudgetBytes
}

func (c *fecConn) extraKind() string {
	if c.padJunk {
		return "pad_junk"
	}
	if c.dup {
		return "dup"
	}
	if c.mode == "fec" {
		return "parity"
	}
	return "none"
}

func checkComparisonFlags(pad, dup bool, mode, fec, layout string, corrupt int) error {
	if !pad && !dup {
		return nil
	}
	if pad && dup {
		return fmt.Errorf("pad-junk and dup are mutually exclusive")
	}
	if mode != "client" || fec != "fec" || layout != "v3" || corrupt >= 0 {
		return fmt.Errorf("pad-junk/dup require client, fixed fec on, layout v3, and corrupt-parity -1")
	}
	return nil
}

func comparisonPacket(kind string, j int, pkt []byte, fl [][]byte) []byte {
	if kind == "dup" {
		return append([]byte(nil), fl[j%len(fl)]...)
	}
	if kind == "pad_junk" {
		out := append([]byte(nil), pkt...)
		h := parseLongHdr(out)
		at := h.bodyOff + 3
		copy(out[at:at+4], []byte("JUNK"))
		clear(out[at+12:])
		return out
	}
	return pkt
}
