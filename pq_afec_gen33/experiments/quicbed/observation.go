package main

import (
	"context"
	"hash/crc32"
	"net"
	"sync"
	"time"

	quic "github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/qlog"
	"github.com/quic-go/quic-go/qlogwriter"
)

const observationCap = 4096
const observationFrameCap = 128

type datagramObservation struct {
	AtNS      int64  `json:"at_ns"`
	Bytes     int    `json:"bytes"`
	CRC32C    uint32 `json:"crc32c"`
	Feedback  bool   `json:"feedback"`
	BeforeBig bool   `json:"before_big"`
	Initial   bool   `json:"initial"`
}

type packetObservation struct {
	AtNS      int64      `json:"at_ns"`
	Direction string     `json:"direction"`
	Space     string     `json:"space"`
	PN        int64      `json:"pn"`
	Bytes     int        `json:"bytes"`
	CRC32C    uint32     `json:"crc32c"`
	Coalesced bool       `json:"coalesced"`
	ACKRanges [][2]int64 `json:"ack_ranges"`
	Crypto    [][2]int64 `json:"crypto"`
}

type rttObservation struct {
	AtNS     int64 `json:"at_ns"`
	LatestNS int64 `json:"latest_ns"`
	MinNS    int64 `json:"min_ns"`
}

type wireObservation struct {
	Version     int                   `json:"version"`
	Tracer      string                `json:"tracer"`
	EndNS       int64                 `json:"end_ns"`
	Datagrams   []datagramObservation `json:"server_datagrams"`
	Packets     []packetObservation   `json:"packets"`
	RTT         []rttObservation      `json:"rtt_updates"`
	PTO         []int64               `json:"pto_at_ns"`
	PTOCount    int                   `json:"pto_count"`
	PTOScope    string                `json:"pto_count_scope"`
	ServerBytes int64                 `json:"server_bytes"`
	Truncated   bool                  `json:"truncated"`
}

type memoryTrace struct {
	onRetry func()
	mu      sync.Mutex
	start   time.Time
	now     func() time.Time
	data    wireObservation
	minRTT  time.Duration
	big     bool
}

func newMemoryTrace(start time.Time) *memoryTrace {
	return &memoryTrace{start: start, now: time.Now, data: wireObservation{Version: 1, Tracer: "memory_qlog", PTOScope: "qlog_loss_timer_expired_lower_bound",
		Datagrams: []datagramObservation{}, Packets: []packetObservation{}, RTT: []rttObservation{}, PTO: []int64{}}}
}

func (m *memoryTrace) disableTracer() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.data.Tracer = "disabled"
	m.data.PTOScope = "tracer_disabled"
}

func (m *memoryTrace) tracer(context.Context, bool, quic.ConnectionID) qlogwriter.Trace { return m }
func (m *memoryTrace) AddProducer() qlogwriter.Recorder                                 { return m }
func (m *memoryTrace) SupportsSchemas(schema string) bool                               { return schema == qlog.EventSchema }
func (m *memoryTrace) Close() error                                                     { return nil }

func (m *memoryTrace) packetLocked(direction string, h qlog.PacketHeader, raw qlog.RawInfo, crc qlog.DatagramPayloadChecksum, coalesced bool, frames []qlog.Frame, at int64) {
	if len(m.data.Packets) >= observationCap {
		m.data.Truncated = true
		return
	}
	p := packetObservation{AtNS: at, Direction: direction, Space: string(h.PacketType), PN: int64(h.PacketNumber), Bytes: raw.Length, CRC32C: uint32(crc), Coalesced: coalesced, ACKRanges: [][2]int64{}, Crypto: [][2]int64{}}
	for i, f := range frames {
		if i >= observationFrameCap {
			m.data.Truncated = true
			break
		}
		switch v := f.Frame.(type) {
		case *qlog.AckFrame:
			for _, r := range v.AckRanges {
				if len(p.ACKRanges) >= observationFrameCap {
					m.data.Truncated = true
					break
				}
				p.ACKRanges = append(p.ACKRanges, [2]int64{int64(r.Smallest), int64(r.Largest)})
			}
		case *qlog.CryptoFrame:
			p.Crypto = append(p.Crypto, [2]int64{v.Offset, v.Length})
		}
	}
	m.data.Packets = append(m.data.Packets, p)
}

func (m *memoryTrace) RecordEvent(event qlogwriter.Event) {
	m.mu.Lock()
	var notify func()
	defer func() {
		m.mu.Unlock()
		if notify != nil {
			notify()
		}
	}()
	at := m.now().Sub(m.start).Nanoseconds()
	switch e := event.(type) {
	case qlog.PacketReceived:
		m.packetLocked("received", e.Header, e.Raw, e.DatagramPayloadChecksum, e.IsCoalesced, e.Frames, at)
		if e.Header.PacketType == qlog.PacketTypeRetry {
			notify = m.onRetry
		}
	case qlog.PacketSent:
		m.packetLocked("sent", e.Header, e.Raw, e.DatagramPayloadChecksum, e.IsCoalesced, e.Frames, at)
	case qlog.MetricsUpdated:
		if e.MinRTT > 0 {
			m.minRTT = e.MinRTT
		}
		if e.LatestRTT > 0 {
			if len(m.data.RTT) < observationCap {
				m.data.RTT = append(m.data.RTT, rttObservation{at, int64(e.LatestRTT), int64(m.minRTT)})
			} else {
				m.data.Truncated = true
			}
		}
	case qlog.LossTimerUpdated:
		if e.Type == qlog.LossTimerUpdateTypeExpired && e.TimerType == qlog.TimerTypePTO {
			m.data.PTOCount++
			if len(m.data.PTO) < observationCap {
				m.data.PTO = append(m.data.PTO, at)
			} else {
				m.data.Truncated = true
			}
		}
	}
}

func (m *memoryTrace) datagram(data []byte, feedback bool) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if !feedback {
		m.data.ServerBytes += int64(len(data))
	}
	if len(m.data.Datagrams) < observationCap {
		h := parseLongHdr(data)
		m.data.Datagrams = append(m.data.Datagrams, datagramObservation{m.now().Sub(m.start).Nanoseconds(), len(data), uint32(qlog.CalculateDatagramPayloadChecksum(data)), feedback, !m.big && len(data) < serverFlightMin, h.ok && h.typ == 0})
	} else {
		m.data.Truncated = true
	}
	if !feedback && len(data) >= serverFlightMin {
		m.big = true
	}
}

func (m *memoryTrace) snapshot() wireObservation {
	m.mu.Lock()
	defer m.mu.Unlock()
	d := m.data
	d.EndNS = m.now().Sub(m.start).Nanoseconds()
	d.Datagrams = append([]datagramObservation{}, d.Datagrams...)
	d.Packets = append([]packetObservation{}, d.Packets...)
	for i := range d.Packets {
		d.Packets[i].ACKRanges = append([][2]int64{}, d.Packets[i].ACKRanges...)
		d.Packets[i].Crypto = append([][2]int64{}, d.Packets[i].Crypto...)
	}
	d.RTT = append([]rttObservation{}, d.RTT...)
	d.PTO = append([]int64{}, d.PTO...)
	return d
}

type c1Observation struct {
	Version           int    `json:"version"`
	Received          int    `json:"received"`
	PhysicalOriginal  int    `json:"physical_original"`
	PhysicalParity    int    `json:"physical_parity"`
	OtherCRC          int    `json:"other_crc"`
	RecoveredOriginal int    `json:"recovered_original"`
	OtherRecoveredCRC int    `json:"other_recovered_crc"`
	RawOriginal       int    `json:"raw_original"`
	RawParity         int    `json:"raw_parity"`
	RawRecovered      int    `json:"raw_recovered"`
	Reason            string `json:"reason"`
}

func (c *fecConn) arrivalEvidence(enabled bool) (p3Arrivals, c1Observation) {
	c.mu.Lock()
	defer c.mu.Unlock()
	a := p3Arrivals{Src: "none"}
	d := c1Observation{Received: c.fbCount, Reason: "no_feedback"}
	if !enabled {
		d.Reason = "disabled"
		return a, d
	}
	r := c.fbLast
	if r == nil {
		return a, d
	}
	d.Version = r.version
	d.RawOriginal, d.RawParity, d.RawRecovered = int(r.rxOrig), int(r.rxPar), int(r.recov)
	d.PhysicalOriginal, d.PhysicalParity, d.OtherCRC = matchFirstFlight(r, c.ffOrigCRC, c.ffParCRC)
	seen := map[uint32]bool{}
	for _, cr := range r.recovered {
		if seen[cr] {
			continue
		}
		seen[cr] = true
		if inCRC(c.ffOrigCRC, cr) {
			d.RecoveredOriginal++
		} else {
			d.OtherRecoveredCRC++
		}
	}
	all := append(append([]uint32{}, c.ffOrigCRC...), c.ffParCRC...)
	if len(all) == 0 || len(all) > p3KMax+p3MMax {
		d.Reason = "invalid_sent_count"
		return a, d
	}
	a = p3Arrivals{Src: "c1", Sent: len(all), Bitmap: []int{}, Trunc: r.truncated || r.recoveredTruncated || c.ffSendFailed}
	seen = map[uint32]bool{}
	for _, cr := range all {
		if seen[cr] {
			a.Trunc = true
		}
		seen[cr] = true
		bit := 0
		if inCRC(r.crcs, cr) {
			bit = 1
		} else {
			a.Lost++
		}
		a.Bitmap = append(a.Bitmap, bit)
	}
	d.Reason = "complete_crc_lists"
	if a.Trunc {
		d.Reason = "truncated_or_ambiguous_crc"
	}
	return a, d
}

func (s *decodeConn) recordRecoveredLocked(ca *connAcct, outs [][]byte) {
	if ca == nil || ca.FbSent {
		return
	}
	for _, o := range outs {
		cr := crc32.ChecksumIEEE(o)
		if inCRC(ca.RecoveredCRC, cr) {
			continue
		}
		if len(ca.RecoveredCRC) < fbCRCCap {
			ca.RecoveredCRC = append(ca.RecoveredCRC, cr)
		} else {
			ca.RecoveredCRCTruncated = true
		}
	}
}

func (s *decodeConn) feedbackLocked(data []byte, ca *connAcct) []byte {
	if !s.feedback || ca == nil || ca.FbSent || (!hasHandshake(data) && !fbEarly) {
		return nil
	}
	h := parseLongHdr(data)
	if !h.ok {
		return nil
	}
	ca.FbSent = true
	s.stats.FbSentN++
	return buildFeedback(h.scid, h.dcid, fbRec{version: s.feedbackVersion, flight: 0, k: uint8(min8(ca.RxOrigN + ca.RecovN)), rxOrig: uint8(min8(ca.RxOrigN)), rxPar: uint8(min8(ca.RxParityN)), recov: uint8(min8(ca.RecovN)), crcs: ca.RxCRC, truncated: ca.RxCRCTruncated, recovered: ca.RecoveredCRC, recoveredTruncated: ca.RecoveredCRCTruncated})
}

func (s *decodeConn) writeFeedback(data []byte, addr net.Addr, metas ...packetMeta) {
	if data == nil {
		return
	}
	var err error
	if ua, ok := addr.(*net.UDPAddr); s.udp != nil && ok {
		_, _, err = s.udp.WriteMsgUDP(data, firstPacketMeta(metas).reply(), ua)
	} else {
		_, err = s.PacketConn.WriteTo(data, addr)
	}
	if err != nil {
		s.mu.Lock()
		s.stats.FbWriteErr++
		s.mu.Unlock()
	}
}

func (s *decodeConn) finalizeFlightLocked(fr *flightRec) {
	if fr == nil || fr.fb == nil || fr.finalized {
		return
	}
	fr.finalized = true
	s.stats.FlightsFinalized++
	missing := false
	for _, cr := range fr.fb.crcs {
		if !fr.seenCRC[cr] && !fr.recCRC[cr] {
			missing = true
		}
	}
	if missing {
		s.stats.UnrecoverFinal++
	}
}

func (s *decodeConn) observationStatsLocked(now time.Time) serverStats {
	for _, fr := range s.flights {
		if now.Sub(fr.created) > flightTTL {
			s.finalizeFlightLocked(fr)
		}
	}
	if s.hold != nil {
		for _, fr := range s.hold.flights {
			if s.hold.now().Sub(fr.created) >= s.hold.config.ttl {
				s.finalizeHoldFlightLocked(fr)
			}
		}
	}
	out := s.stats
	for _, fr := range s.flights {
		if !fr.finalized {
			out.FlightsPending++
		}
	}
	if s.hold != nil {
		for _, fr := range s.hold.flights {
			if !fr.finalized {
				out.FlightsPending++
			}
		}
	}
	return out
}

func (s *decodeConn) finalizeHoldFlightLocked(fr *holdFlight) {
	if fr.finalized {
		return
	}
	fr.finalized = true
	s.stats.FlightsFinalized++
	for i, cr := range fr.fb.crcs {
		if !fr.seenCRC[cr] && !inIntSlice(fr.recovered, i) {
			s.stats.UnrecoverFinal++
			break
		}
	}
}

func (m *memoryTrace) serverBytes() int64 {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.data.ServerBytes
}

type feedbackWindow struct {
	Waited             bool
	Received           bool
	Elapsed            time.Duration
	PreWaitServerBytes int64
	PreWaitStats       quic.ConnectionStats
	AfterWaitRTTMS     float64
	AfterWaitRTTValid  bool
}

func collectFeedbackWindow(serverBytes func() int64, stats func() quic.ConnectionStats, wait func() bool) feedbackWindow {
	w := feedbackWindow{Waited: true, PreWaitServerBytes: serverBytes(), PreWaitStats: stats()}
	start := time.Now()
	w.Received = wait()
	w.Elapsed = time.Since(start)
	return w
}

func (w feedbackWindow) policyServerBytes(total int64) int64 {
	if w.Waited {
		return w.PreWaitServerBytes
	}
	return total
}

func (w feedbackWindow) policyStats(current quic.ConnectionStats) quic.ConnectionStats {
	if w.Waited {
		return w.PreWaitStats
	}
	return current
}

func (w feedbackWindow) annotate(r *trial3) {
	if !w.Waited {
		return
	}
	bytes, rtt, valid := w.PreWaitServerBytes, w.AfterWaitRTTMS, w.AfterWaitRTTValid
	r.SrvBytesPreWait, r.PathRTTAfterWaitMS, r.PathRTTAfterWaitValid = &bytes, &rtt, &valid
}
