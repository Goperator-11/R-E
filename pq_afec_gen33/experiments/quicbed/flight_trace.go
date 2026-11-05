package main

import "time"

const flightTraceCap = 128

type flightTraceRecord struct {
	ExtraSent           extraSent   `json:"extra_sent"`
	Shape               flightShape `json:"shape"`
	ParitySent          int         `json:"parity_sent"`
	ParityBytes         int64       `json:"parity_bytes"`
	Sequence            int         `json:"sequence"`
	ID                  uint16      `json:"id"`
	FirstInputMS        float64     `json:"first_input_ms"`
	LastInputMS         float64     `json:"last_input_ms"`
	FlushMS             float64     `json:"flush_ms"`
	EndMS               float64     `json:"end_ms"`
	Reason              string      `json:"reason"`
	ExpectedK           int         `json:"expected_k"`
	ActualK             int         `json:"actual_k"`
	OriginalBytes       int64       `json:"original_bytes"`
	OriginalImmediate   bool        `json:"original_immediate"`
	BufferedFirstWaitMS float64     `json:"buffered_first_wait_ms"`
	BufferedLastWaitMS  float64     `json:"buffered_last_wait_ms"`
	KMismatch           bool        `json:"k_mismatch"`
	SplitSuspected      bool        `json:"split_suspected"`
	Flushed             bool        `json:"flushed"`
	Complete            bool        `json:"complete"`
	FlushTxDgrams       int         `json:"flush_tx_dgrams"`
	FlushTxBytes        int64       `json:"flush_tx_bytes"`
	FlushTxErrors       int         `json:"flush_tx_errors"`
}

type flightTrace struct {
	Records            []flightTraceRecord `json:"records"`
	Omitted            int                 `json:"omitted"`
	StaleTriggers      int                 `json:"stale_triggers"`
	FlushedOriginals   int                 `json:"flushed_originals"`
	FlushedBytes       int64               `json:"flushed_bytes"`
	DiscardedOriginals int                 `json:"discarded_originals"`
	DiscardedBytes     int64               `json:"discarded_bytes"`
}

func (s flightTrace) clone() flightTrace {
	s.Records = append([]flightTraceRecord{}, s.Records...)
	return s
}

func (s *flightTrace) addTotals(other flightTrace) {
	s.Omitted += other.Omitted
	s.StaleTriggers += other.StaleTriggers
	s.FlushedOriginals += other.FlushedOriginals
	s.FlushedBytes += other.FlushedBytes
	s.DiscardedOriginals += other.DiscardedOriginals
	s.DiscardedBytes += other.DiscardedBytes
}

func (c *fecConn) traceFlightLocked(reason string, fl [][]byte, now time.Time, flushed bool) int {
	c.traceSequence++
	expected := c.expectedKLocked()
	var n int64
	for _, b := range fl {
		n += int64(len(b))
	}
	tr := &c.stats.FlightTrace
	if flushed {
		tr.FlushedOriginals += len(fl)
		tr.FlushedBytes += n
	} else {
		tr.DiscardedOriginals += len(fl)
		tr.DiscardedBytes += n
	}
	if len(tr.Records) >= flightTraceCap {
		tr.Omitted++
		return -1
	}
	rec := flightTraceRecord{Shape: c.curShape, Sequence: c.traceSequence, ID: c.flightID,
		FirstInputMS: float64(c.flightFirst.Sub(c.traceEpoch)) / float64(time.Millisecond),
		LastInputMS:  float64(c.flightLast.Sub(c.traceEpoch)) / float64(time.Millisecond),
		FlushMS:      float64(now.Sub(c.traceEpoch)) / float64(time.Millisecond),
		Reason:       reason, ExpectedK: expected, ActualK: len(fl), OriginalBytes: n,
		OriginalImmediate: c.mode == "off" || c.curLater, Flushed: flushed,
		KMismatch: expected > 0 && len(fl) != expected, SplitSuspected: expected > 0 && len(fl) < expected}
	if !rec.OriginalImmediate && flushed {
		rec.BufferedFirstWaitMS = float64(now.Sub(c.flightFirst)) / float64(time.Millisecond)
		rec.BufferedLastWaitMS = float64(now.Sub(c.flightLast)) / float64(time.Millisecond)
	}
	if !flushed {
		rec.Complete = true
		rec.EndMS = rec.FlushMS
	}
	tr.Records = append(tr.Records, rec)
	return len(tr.Records) - 1
}

func (c *fecConn) finishFlightTrace(index, sent, failures int, bytes int64, parities int, parityBytes int64, extras extraSent) {
	if index < 0 {
		return
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	rec := &c.stats.FlightTrace.Records[index]
	rec.EndMS = float64(time.Since(c.traceEpoch)) / float64(time.Millisecond)
	rec.Complete = true
	rec.FlushTxDgrams = sent
	rec.FlushTxBytes = bytes
	rec.FlushTxErrors = failures
	rec.ExtraSent = extras
	rec.ParitySent = parities
	rec.ParityBytes = parityBytes
}
