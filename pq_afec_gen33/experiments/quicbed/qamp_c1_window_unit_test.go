package main

import (
	"bytes"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
)

func TestFeedbackWindowSnapshotsBeforeWait(t *testing.T) {
	m := newMemoryTrace(time.Now())
	big := bytes.Repeat([]byte{0}, 1280)
	m.datagram(big, false)
	before := m.serverBytes()
	pre := quic.ConnectionStats{MinRTT: 217 * time.Millisecond, LatestRTT: 217 * time.Millisecond, MeanDeviation: time.Millisecond}
	post := quic.ConnectionStats{MinRTT: 205 * time.Millisecond, LatestRTT: 205 * time.Millisecond, MeanDeviation: time.Millisecond}
	current := pre
	w := collectFeedbackWindow(m.serverBytes, func() quic.ConnectionStats { return current }, func() bool {
		m.datagram(big, false)
		m.datagram(big, false)
		m.datagram(big[:78], true)
		current = post
		return true
	})
	total := m.snapshot().ServerBytes
	if !w.Waited || !w.Received || w.PreWaitServerBytes != before || total != before+2*1280 {
		t.Fatalf("window %+v before %d total %d", w, before, total)
	}
	if got := w.policyServerBytes(total); got != before {
		t.Fatalf("policy server bytes %d want %d", got, before)
	}
	if got := w.policyStats(current); got.MinRTT != pre.MinRTT {
		t.Fatalf("policy stats %v want %v", got.MinRTT, pre.MinRTT)
	}
	w.AfterWaitRTTMS, w.AfterWaitRTTValid = measuredPathRTT(current)
	var row trial3
	w.annotate(&row)
	if row.SrvBytesPreWait == nil || *row.SrvBytesPreWait != before || row.PathRTTAfterWaitMS == nil || *row.PathRTTAfterWaitMS != 205 || row.PathRTTAfterWaitValid == nil || !*row.PathRTTAfterWaitValid {
		t.Fatalf("row %+v", row)
	}
}

func TestFeedbackWindowZeroValueKeepsNonePath(t *testing.T) {
	var w feedbackWindow
	if got := w.policyServerBytes(13633); got != 13633 {
		t.Fatalf("none policy bytes %d", got)
	}
	current := quic.ConnectionStats{MinRTT: 217 * time.Millisecond}
	if got := w.policyStats(current); got != current {
		t.Fatalf("none policy stats %+v", got)
	}
	var row trial3
	w.annotate(&row)
	if row.SrvBytesPreWait != nil || row.PathRTTAfterWaitMS != nil || row.PathRTTAfterWaitValid != nil {
		t.Fatalf("none row %+v", row)
	}
}
