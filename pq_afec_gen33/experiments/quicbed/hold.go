package main

import (
	"fmt"
	"hash/crc32"
	"net"
	"sort"
	"time"
)

type holdConfig struct {
	uplinkKbps  int64
	margin      time.Duration
	ttl         time.Duration
	recentTTL   time.Duration
	flightCap   int64
	globalCap   int64
	flightCount int
}

func defaultHoldConfig() holdConfig {
	return holdConfig{2000, time.Millisecond, time.Second, 3 * time.Second, 32768, 8 << 20, 1024}
}

type heldSymbol struct {
	meta  packetMeta
	index int
	raw   []byte
	sym   []byte
}

type holdFlight struct {
	meta      packetMeta
	events    [3]*holdEvent
	wakes     [2]*holdEvent
	seenCRC   map[uint32]bool
	finalized bool
	fb        *fecBlock
	dcid      string
	acct      *connAcct
	addr      net.Addr
	created   time.Time
	deadline  time.Time
	open      bool
	terminal  string
	symbols   []heldSymbol
	memory    int64
	used      []int
	recovered []int
}

type holdState struct {
	config           holdConfig
	flights          map[string]*holdFlight
	recent           originalIndex
	groups           map[decoderGroup]map[string]*holdFlight
	events           holdEvents
	wakes            holdEvents
	memory           int64
	externalDeadline time.Time
	closed           bool
	now              func() time.Time
}

func newHoldState(config holdConfig) *holdState {
	return &holdState{config: config, flights: map[string]*holdFlight{}, now: time.Now}
}

func sameHoldMetadata(a, b *fecBlock) bool {
	if a.ver != b.ver || a.flight != b.flight || a.k != b.k || a.m != b.m || a.lead != b.lead || a.symLen != b.symLen || len(a.crcs) != len(b.crcs) || len(a.lens) != len(b.lens) {
		return false
	}
	for i := range a.crcs {
		if a.crcs[i] != b.crcs[i] || a.lens[i] != b.lens[i] {
			return false
		}
	}
	return true
}

func (s *decodeConn) holdDiscardLocked(fr *holdFlight, reason string) {
	var raw int64
	for _, p := range fr.symbols {
		raw += int64(len(p.raw))
	}
	s.heldBytes -= raw
	s.hold.memory -= fr.memory
	s.stats.HoldDiscardBytes += raw
	if reason == "expired" {
		s.stats.HoldExpiredBytes += raw
	}
	if reason == "cap" {
		s.stats.HoldCapBytes += raw
	}
	fr.symbols, fr.memory, fr.terminal = nil, 0, reason
	s.hold.updateWake(fr)
}

func (s *decodeConn) holdQueueLocked(data []byte, addr net.Addr, ca *connAcct, meta packetMeta, creditVersion ...int) {
	cp := append([]byte(nil), data...)
	ver := 0
	if len(creditVersion) > 0 {
		ver = creditVersion[0]
	}
	s.queuePendingLocked(pendingPkt{data: cp, addr: addr, acct: ca, creditVer: ver, meta: meta})
}

func (s *decodeConn) holdHaveLocked(fr *holdFlight, now time.Time) map[int][]byte {
	have := map[int][]byte{}
	for i, cr := range fr.fb.crcs {
		data := s.lookupOriginalLocked(&s.hold.recent, decoderGroup{fr.dcid, fr.acct}, cr, int(fr.fb.lens[i]))
		if data != nil {
			q := make([]byte, fr.fb.symLen)
			copy(q, data)
			have[i] = q
			if fr.seenCRC == nil {
				fr.seenCRC = map[uint32]bool{}
			}
			fr.seenCRC[cr] = true
		} else if fr.seenCRC[cr] {
			s.stats.DecoderEvictedSource++
			s.holdDiscardLocked(fr, "source_evicted")
			return nil
		}
	}
	return have
}

func (s *decodeConn) holdSettleLocked(fr *holdFlight, now time.Time, current []byte, addr net.Addr, metas ...packetMeta) {
	meta := firstPacketMeta(metas)
	s.hold.updateWake(fr)
	passCurrent := func() {
		if current != nil {
			s.holdQueueLocked(current, addr, fr.acct, meta)
		}
	}
	if fr.terminal != "" || !fr.open {
		passCurrent()
		return
	}
	have := s.holdHaveLocked(fr, now)
	if fr.terminal != "" {
		passCurrent()
		return
	}
	missing := []int{}
	for i := 0; i < fr.fb.k; i++ {
		if have[i] == nil {
			missing = append(missing, i)
		}
	}
	if len(missing) > len(fr.symbols) {
		passCurrent()
		return
	}
	ordered := append([]heldSymbol(nil), fr.symbols...)
	sort.Slice(ordered, func(i, j int) bool {
		a, b := ordered[i].index, ordered[j].index
		if (a < fr.fb.lead) != (b < fr.fb.lead) {
			return a >= fr.fb.lead
		}
		return a < b
	})
	used := map[int][]byte{}
	for _, p := range ordered[:len(missing)] {
		used[p.index] = p.sym
	}
	var recs map[int][]byte
	if len(missing) > 0 {
		recs = recoverMany(fr.fb.k, fr.fb.m, missing, have, used, fr.fb.symLen)
	}
	outs := [][]byte{}
	for _, i := range missing {
		r := recs[i]
		if len(r) < int(fr.fb.lens[i]) || crc32.ChecksumIEEE(r[:int(fr.fb.lens[i])]) != fr.fb.crcs[i] {
			s.stats.RecoverFail++
			s.holdDiscardLocked(fr, "crc")
			passCurrent()
			return
		}
		outs = append(outs, r[:int(fr.fb.lens[i])])
	}
	planned := int64(len(current))
	for _, p := range fr.symbols {
		if used[p.index] == nil {
			planned += int64(len(p.raw))
		}
	}
	for _, r := range outs {
		planned += int64(len(r))
	}
	accountPending := s.pendingByAcct[fr.acct]
	if s.stats.BytesToStack+s.pendingBytes+planned > s.stats.BytesIn || fr.acct == nil || fr.acct.Stack+accountPending+planned > fr.acct.RxBytes || s.hold.memory-fr.memory+s.pendingBytes+planned > s.hold.config.globalCap {
		s.stats.RecoverRefused++
		s.holdDiscardLocked(fr, "cap")
		passCurrent()
		return
	}
	var raw int64
	for _, p := range fr.symbols {
		raw += int64(len(p.raw))
		if used[p.index] == nil {
			ver := 0
			if p.index < fr.fb.lead {
				ver = fr.fb.ver
			}
			s.holdQueueLocked(p.raw, fr.addr, fr.acct, p.meta, ver)
		}
	}
	passCurrent()
	for _, r := range outs {
		s.holdQueueLocked(r, fr.addr, fr.acct, fr.meta)
	}
	for _, p := range ordered[:len(missing)] {
		fr.used = append(fr.used, p.index)
	}
	fr.recovered = append(fr.recovered, missing...)
	if len(missing) > 0 {
		s.stats.RecoverEvents++
	}
	s.stats.Recovered += len(missing)
	if !fr.acct.FbSent {
		fr.acct.RecovN += len(missing)
	}
	s.recordRecoveredLocked(fr.acct, outs)
	s.heldBytes -= raw
	s.hold.memory -= fr.memory
	fr.symbols, fr.memory, fr.terminal = nil, 0, "complete"
	s.hold.updateWake(fr)
}

func (s *decodeConn) holdTickLocked(now time.Time) {
	s.tickHoldIndexLocked(now)
}

func (s *decodeConn) holdReportLocked() map[string]any {
	if s.hold == nil {
		return map[string]any{"enabled": false}
	}
	c := s.hold.config
	return map[string]any{"enabled": true, "contract": "M1_receiver_deadline_v1", "uplink_kbps": c.uplinkKbps,
		"margin_ns": int64(c.margin), "ttl_ns": int64(c.ttl), "recent_ttl_ns": int64(c.recentTTL),
		"flight_payload_cap": c.flightCap, "global_payload_cap": c.globalCap, "flight_count_cap": c.flightCount,
		"held_payload_memory": s.hold.memory, "held_wire_bytes": s.heldBytes, "pending_bytes": s.pendingBytes,
		"flight_records": len(s.hold.flights), "recent_originals": s.hold.recent.age.Len()}
}

func (s *decodeConn) holdReadDeadlineLocked() error {
	d := s.hold.externalDeadline
	if len(s.hold.wakes) > 0 {
		when := s.hold.wakes[0].when
		if d.IsZero() || when.Before(d) {
			d = when
		}
	}
	return s.PacketConn.SetReadDeadline(d)
}

func (s *decodeConn) SetReadDeadline(t time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.hold == nil {
		return s.PacketConn.SetReadDeadline(t)
	}
	s.hold.externalDeadline = t
	return s.holdReadDeadlineLocked()
}

func (s *decodeConn) SetDeadline(t time.Time) error {
	if err := s.SetReadDeadline(t); err != nil {
		return err
	}
	return s.PacketConn.SetWriteDeadline(t)
}

func (s *decodeConn) Close() error {
	s.mu.Lock()
	s.closed = true
	if s.hold != nil {
		s.hold.closed = true
		for _, fr := range s.hold.flights {
			if fr.terminal == "" {
				s.holdDiscardLocked(fr, "closed")
			}
		}
		s.stats.HoldDiscardBytes += s.pendingBytes
		s.pending, s.pendingBytes = nil, 0
		s.hold.recent = originalIndex{}
		s.hold.groups = nil
		s.hold.events = nil
		s.hold.wakes = nil
		s.hold.flights = map[string]*holdFlight{}
	}
	for _, fr := range s.flights {
		s.releaseFlightLocked(fr)
	}
	s.flights = nil
	s.decoder = nil
	s.recent = originalIndex{}
	s.pending, s.pendingBytes, s.pendingByAcct = nil, 0, nil
	s.mu.Unlock()
	return s.PacketConn.Close()
}

func (s *decodeConn) holdReceiveLocked(data []byte, wireLen int, fb *fecBlock, addr net.Addr, ca *connAcct, now time.Time, metas ...packetMeta) {
	meta := firstPacketMeta(metas)
	h := s.hold
	if h.closed {
		s.stats.HoldDiscardBytes += int64(len(data))
		return
	}
	s.holdTickLocked(now)
	dc := dcidOf(data)
	if fb == nil {
		s.stats.Originals++
		if ca == nil || !decoderOriginal(data) {
			s.stats.DecoderOriginalIgnored++
			s.holdQueueLocked(data, addr, ca, meta)
			return
		}
		cr := crc32.ChecksumIEEE(data)
		group := decoderGroup{dc, ca}
		s.stats.DecoderRecentEvicted += h.recent.add(group, data, now)
		keys := []string{}
		for key := range h.groups[group] {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		consumed := false
		for _, key := range keys {
			fr := h.flights[key]
			s.stats.DecoderFlightVisits++
			if inCRC(fr.fb.crcs, cr) {
				if fr.seenCRC == nil {
					fr.seenCRC = map[uint32]bool{}
				}
				fr.seenCRC[cr] = true
			}
			if fr.terminal != "" {
				for _, i := range fr.recovered {
					if fr.fb.crcs[i] == cr && int(fr.fb.lens[i]) == len(data) {
						s.stats.PrematureRecover++
						break
					}
				}
				continue
			}
			matched := false
			for i, c := range fr.fb.crcs {
				if c == cr && int(fr.fb.lens[i]) == len(data) {
					matched = true
					if i == fr.fb.k-1 {
						fr.open = true
					}
				}
			}
			if matched && !consumed {
				s.holdSettleLocked(fr, now, data, addr, meta)
				consumed = true
			}
		}
		if !consumed {
			s.holdQueueLocked(data, addr, ca, meta)
		}
		return
	}
	s.stats.Parities++
	key := fmt.Sprintf("%x|%d", dc, fb.flight)
	fr := h.flights[key]
	if fr != nil && (fr.acct != ca || !sameHoldMetadata(fr.fb, fb)) {
		s.stats.HoldMetadataBytes += int64(len(data))
		s.stats.HoldDiscardBytes += int64(len(data))
		return
	}
	creditVer := 0
	if isCreditParity(fb) {
		creditVer = fb.ver
	}
	validLengths := true
	for _, n := range fb.lens {
		if n == 0 || n > udpMaxPayload {
			validLengths = false
		}
	}
	if fb.ver != fecVerLead || fb.k > 4 || fb.m > 4 || ca == nil || !validLengths {
		s.stats.HoldUnsupported++
		s.holdQueueLocked(data, addr, ca, meta, creditVer)
		return
	}
	if fr == nil {
		if len(h.flights) >= h.config.flightCount || len(h.groups[decoderGroup{dc, ca}]) >= decoderGroupFlightCap {
			s.stats.DecoderFlightCap++
			s.stats.HoldUnsupported++
			s.holdQueueLocked(data, addr, ca, meta, creditVer)
			return
		}
		remaining := int64((fb.m - fb.index - 1) * wireLen)
		if fb.index < fb.lead {
			for _, n := range fb.lens {
				remaining += int64(n)
			}
		}
		delay := h.config.margin
		if h.config.uplinkKbps > 0 {
			numerator := remaining * 8_000_000
			serial := numerator / h.config.uplinkKbps
			if numerator%h.config.uplinkKbps != 0 {
				serial++
			}
			delay += time.Duration(serial)
		}
		metadata := *fb
		metadata.sym = nil
		fr = &holdFlight{meta: meta.recovery(), fb: &metadata, dcid: dc, acct: ca, addr: addr, created: now, deadline: now.Add(delay)}
		h.flights[key] = fr
		h.register(key, fr)
		if delay >= h.config.ttl {
			fr.terminal = "unsupported_deadline"
			s.stats.HoldUnsupported++
		}
		if s.holdHaveLocked(fr, now)[fb.k-1] != nil {
			fr.open = true
		}
	}
	s.hold.updateWake(fr)
	if fr.terminal != "" {
		s.holdQueueLocked(data, addr, ca, meta, creditVer)
		return
	}
	for _, p := range fr.symbols {
		if p.index == fb.index {
			s.stats.HoldDuplicateBytes += int64(len(data))
			s.stats.HoldDiscardBytes += int64(len(data))
			return
		}
	}
	extra := int64(len(data) + len(fb.sym))
	if fr.memory+extra > h.config.flightCap || h.memory+s.pendingBytes+extra+65535 > h.config.globalCap {
		s.holdDiscardLocked(fr, "cap")
		s.holdQueueLocked(data, addr, ca, meta, creditVer)
		return
	}
	fr.symbols = append(fr.symbols, heldSymbol{meta: meta, index: fb.index, raw: append([]byte(nil), data...), sym: fb.sym})
	fr.memory += extra
	h.memory += extra
	s.heldBytes += int64(len(data))
	if fb.index >= fb.lead {
		fr.open = true
	}
	s.holdSettleLocked(fr, now, nil, nil)
}
