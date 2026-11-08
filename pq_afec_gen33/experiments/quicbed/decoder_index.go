package main

import (
	"container/heap"
	"container/list"
	"hash/crc32"
	"net"
	"sort"
	"time"
)

const decoderGroupRecentCap = 64
const decoderGroupFlightCap = 8
const decoderFlightCap = 1024
const decoderFlightPayloadCap = 32768
const decoderPayloadCap = 8 << 20
const decoderInputReserve = 65535
const udpMaxPayload = 1472

type decoderGroup struct {
	dcid string
	acct *connAcct
}

type originalKey struct {
	group decoderGroup
	crc   uint32
	size  int
}

type indexedOriginal struct {
	key                   originalKey
	data                  []byte
	at                    time.Time
	age, group, duplicate *list.Element
}

type originalIndex struct {
	age    list.List
	groups map[decoderGroup]*list.List
	keys   map[originalKey]*list.List
}

func (x *originalIndex) remove(r *indexedOriginal) {
	x.age.Remove(r.age)
	g, d := x.groups[r.key.group], x.keys[r.key]
	g.Remove(r.group)
	d.Remove(r.duplicate)
	if g.Len() == 0 {
		delete(x.groups, r.key.group)
	}
	if d.Len() == 0 {
		delete(x.keys, r.key)
	}
	r.data = nil
}

func (x *originalIndex) expire(now time.Time, ttl time.Duration) {
	for e := x.age.Front(); e != nil; e = x.age.Front() {
		r := e.Value.(*indexedOriginal)
		if now.Sub(r.at) < ttl {
			break
		}
		x.remove(r)
	}
}

func (x *originalIndex) add(group decoderGroup, data []byte, now time.Time) int {
	if x.groups == nil {
		x.groups = map[decoderGroup]*list.List{}
		x.keys = map[originalKey]*list.List{}
	}
	key := originalKey{group, crc32.ChecksumIEEE(data), len(data)}
	if x.groups[group] == nil {
		x.groups[group] = &list.List{}
	}
	if x.keys[key] == nil {
		x.keys[key] = &list.List{}
	}
	r := &indexedOriginal{key: key, data: append([]byte(nil), data...), at: now}
	r.age = x.age.PushBack(r)
	r.group = x.groups[group].PushBack(r)
	r.duplicate = x.keys[key].PushBack(r)
	dropped := 0
	for x.groups[group] != nil && x.groups[group].Len() > decoderGroupRecentCap {
		x.remove(x.groups[group].Front().Value.(*indexedOriginal))
		dropped++
	}
	for x.age.Len() > recentCap {
		x.remove(x.age.Front().Value.(*indexedOriginal))
		dropped++
	}
	return dropped
}

func (x *originalIndex) find(group decoderGroup, crc uint32, size int) []byte {
	if entries := x.keys[originalKey{group, crc, size}]; entries != nil {
		return entries.Front().Value.(*indexedOriginal).data
	}
	return nil
}

func decoderOriginal(data []byte) bool {
	h := parseLongHdr(data)
	return h.ok && h.typ == 0 && len(h.dcid) > 0 && len(data) <= udpMaxPayload
}

type legacyIndex struct {
	age    list.List
	groups map[decoderGroup]map[string]*flightRec
	memory int64
}

func (s *decodeConn) indexLocked() *legacyIndex {
	if s.decoder != nil {
		return s.decoder
	}
	x := &legacyIndex{groups: map[decoderGroup]map[string]*flightRec{}}
	s.decoder = x
	if s.flights == nil {
		s.flights = map[string]*flightRec{}
	}
	keys := make([]string, 0, len(s.flights))
	for key := range s.flights {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i, j int) bool {
		a, b := s.flights[keys[i]], s.flights[keys[j]]
		if a.created.Equal(b.created) {
			return keys[i] < keys[j]
		}
		return a.created.Before(b.created)
	})
	for _, key := range keys {
		s.indexFlightLocked(key, s.flights[key])
	}
	return x
}

func (s *decodeConn) indexFlightLocked(key string, fr *flightRec) {
	x := s.decoder
	g := decoderGroup{fr.dcid, fr.acct}
	if x.groups[g] == nil {
		x.groups[g] = map[string]*flightRec{}
	}
	x.groups[g][key] = fr
	fr.key = key
	fr.age = x.age.PushBack(fr)
	for _, sym := range fr.syms {
		fr.memory += int64(len(sym))
	}
	x.memory += fr.memory
}

func (s *decodeConn) releaseFlightLocked(fr *flightRec) {
	if s.decoder != nil {
		s.decoder.memory -= fr.memory
	}
	fr.memory, fr.syms = 0, nil
	s.heldBytes -= fr.heldBytes
	fr.heldBytes = 0
}

func (s *decodeConn) expireIndexLocked(now time.Time) {
	if s.closed {
		return
	}
	s.recent.expire(now, recentTTL)
	x := s.indexLocked()
	for e := x.age.Front(); e != nil; e = x.age.Front() {
		fr := e.Value.(*flightRec)
		if now.Sub(fr.created) <= flightTTL {
			break
		}
		s.finalizeFlightLocked(fr)
		s.releaseFlightLocked(fr)
		delete(s.flights, fr.key)
		g := decoderGroup{fr.dcid, fr.acct}
		delete(x.groups[g], fr.key)
		if len(x.groups[g]) == 0 {
			delete(x.groups, g)
		}
		x.age.Remove(fr.age)
		fr.age = nil
	}
}

func (s *decodeConn) legacyFlightLocked(key, dc string, ca *connAcct, addr net.Addr, fb *fecBlock, now time.Time, metas ...packetMeta) *flightRec {
	if s.closed {
		return nil
	}
	x := s.indexLocked()
	if fr := s.flights[key]; fr != nil {
		if fr.acct != ca || !sameFecFlight(fr.fb, fb) {
			return nil
		}
		return fr
	}
	if len(s.flights) >= decoderFlightCap || len(x.groups[decoderGroup{dc, ca}]) >= decoderGroupFlightCap {
		s.stats.DecoderFlightCap++
		return nil
	}
	if fb.symLen > udpMaxPayload {
		s.stats.DecoderPayloadCap++
		return nil
	}
	metadata := *fb
	metadata.sym = nil
	fr := &flightRec{meta: firstPacketMeta(metas).recovery(), fb: &metadata, dcid: dc, addr: addr, acct: ca, created: now, syms: map[int][]byte{}}
	s.flights[key] = fr
	s.indexFlightLocked(key, fr)
	return fr
}

func (s *decodeConn) addLegacySymbolLocked(fr *flightRec, fb *fecBlock) bool {
	if fr.syms[fb.index] != nil {
		s.stats.DecoderDuplicate++
		return false
	}
	extra := int64(len(fb.sym))
	if fr.memory+extra > decoderFlightPayloadCap || s.decoder.memory+s.pendingBytes+extra+decoderInputReserve > decoderPayloadCap {
		s.stats.DecoderPayloadCap++
		fr.poisoned = true
		s.releaseFlightLocked(fr)
		return false
	}
	fr.syms[fb.index] = fb.sym
	fr.memory += extra
	s.decoder.memory += extra
	return true
}

func (s *decodeConn) lookupOriginalLocked(index *originalIndex, group decoderGroup, crc uint32, size int) []byte {
	s.stats.DecoderRecentLookups++
	return index.find(group, crc, size)
}

func (s *decodeConn) queuePendingLocked(p pendingPkt) {
	s.pending = append(s.pending, p)
	s.pendingBytes += int64(len(p.data))
	if s.pendingByAcct == nil {
		s.pendingByAcct = map[*connAcct]int64{}
	}
	s.pendingByAcct[p.acct] += int64(len(p.data))
}

type holdEvent struct {
	when  time.Time
	key   string
	kind  int
	fr    *holdFlight
	index int
}

type holdEvents []*holdEvent

func (h holdEvents) Len() int { return len(h) }
func (h holdEvents) Less(i, j int) bool {
	if !h[i].when.Equal(h[j].when) {
		return h[i].when.Before(h[j].when)
	}
	if h[i].key != h[j].key {
		return h[i].key < h[j].key
	}
	return h[i].kind < h[j].kind
}
func (h holdEvents) Swap(i, j int) { h[i], h[j] = h[j], h[i]; h[i].index = i; h[j].index = j }
func (h *holdEvents) Push(v any)   { e := v.(*holdEvent); e.index = len(*h); *h = append(*h, e) }
func (h *holdEvents) Pop() any {
	a := *h
	e := a[len(a)-1]
	a[len(a)-1] = nil
	*h = a[:len(a)-1]
	e.index = -1
	return e
}

func (h *holdState) register(key string, fr *holdFlight) {
	g := decoderGroup{fr.dcid, fr.acct}
	if h.groups == nil {
		h.groups = map[decoderGroup]map[string]*holdFlight{}
	}
	if h.groups[g] == nil {
		h.groups[g] = map[string]*holdFlight{}
	}
	h.groups[g][key] = fr
	times := []time.Time{fr.created.Add(h.config.ttl), fr.deadline, fr.created.Add(h.config.recentTTL)}
	for kind, when := range times {
		e := &holdEvent{when: when, key: key, kind: kind, fr: fr}
		fr.events[kind] = e
		heap.Push(&h.events, e)
		if kind < 2 {
			wake := &holdEvent{when: when, key: key, kind: kind, fr: fr}
			fr.wakes[kind] = wake
			heap.Push(&h.wakes, wake)
		}
	}
}

func (h *holdState) cancelWake(fr *holdFlight, kind int) {
	if e := fr.wakes[kind]; e != nil {
		if e.index >= 0 {
			heap.Remove(&h.wakes, e.index)
		}
		fr.wakes[kind] = nil
	}
}

func (h *holdState) updateWake(fr *holdFlight) {
	if fr.open || fr.terminal != "" {
		h.cancelWake(fr, 1)
	}
	if fr.terminal != "" {
		h.cancelWake(fr, 0)
	}
}

func (h *holdState) cancel(fr *holdFlight, kind int) {
	if e := fr.events[kind]; e != nil {
		if e.index >= 0 {
			heap.Remove(&h.events, e.index)
		}
		fr.events[kind] = nil
	}
}

func (s *decodeConn) tickHoldIndexLocked(now time.Time) {
	h := s.hold
	h.recent.expire(now, h.config.recentTTL)
	for len(h.events) > 0 && !now.Before(h.events[0].when) {
		e := heap.Pop(&h.events).(*holdEvent)
		fr := e.fr
		fr.events[e.kind] = nil
		if e.kind < 2 {
			h.cancelWake(fr, e.kind)
		}
		s.stats.DecoderExpiryEvents++
		switch e.kind {
		case 0:
			s.finalizeHoldFlightLocked(fr)
			if fr.terminal == "" {
				s.holdDiscardLocked(fr, "expired")
			}
		case 1:
			if fr.terminal == "" && !fr.open && now.Before(fr.created.Add(h.config.ttl)) {
				fr.open = true
				s.holdSettleLocked(fr, now, nil, nil)
			}
		case 2:
			s.finalizeHoldFlightLocked(fr)
			if fr.terminal == "" {
				s.holdDiscardLocked(fr, "expired")
			}
			for kind := range fr.events {
				h.cancel(fr, kind)
			}
			for kind := range fr.wakes {
				h.cancelWake(fr, kind)
			}
			delete(h.flights, e.key)
			g := decoderGroup{fr.dcid, fr.acct}
			delete(h.groups[g], e.key)
			if len(h.groups[g]) == 0 {
				delete(h.groups, g)
			}
		}
	}
}
