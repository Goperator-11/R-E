package main

import (
	"errors"
	"net"
	"reflect"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/quic-go/quic-go/qlog"
)

func guardInitial(seed byte, token int) []byte {
	d := finalStatsInitial(seed)
	h := parseLongHdr(d)
	pos := h.bodyOff
	v := appendVarint2(nil, uint64(token))
	copy(d[pos:], v)
	pos += len(v)
	for i := 0; i < token; i++ {
		d[pos+i] = byte(i + 1)
	}
	pos += token
	copy(d[pos:], appendVarint2(nil, uint64(len(d)-pos-2)))
	return d
}

func guardWrite(t *testing.T, c *fecConn, addr net.Addr, seed byte, token int) {
	t.Helper()
	d := guardInitial(seed, token)
	if n, err := c.WriteTo(d, addr); n != len(d) || err != nil {
		t.Fatal(n, err)
	}
}

func TestRevisitGuardWireMatrix(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		for _, kind := range []string{"parity", "dup", "pad"} {
			for _, token := range []int{0, 91} {
				for m := 1; m <= 4; m++ {
					for lead := 0; lead <= m; lead++ {
						for k := 1; k <= 3; k++ {
							c, w, addr := flightInputFixture(flightExpectation{k, "explicit", "all_flights"})
							c.mode, c.layout, c.m, c.lead = "fec", "v3", m, lead
							c.dup, c.padJunk = kind == "dup", kind == "pad"
							c.revisitGuard = newRevisitGuard(revisitGuardConfig{true, "supported"})
							c.observer = newMemoryTrace(time.Now())
							c.observer.onRetry = c.acceptedRevisitRetry
							firstExtra, firstLead := m, lead
							if token > 0 {
								firstExtra, firstLead = m-lead, 0
								if kind == "pad" {
									firstExtra = 0
								}
							}
							for round := 0; round < 4; round++ {
								if round == 1 {
									c.observer.RecordEvent(qlog.PacketReceived{Header: qlog.PacketHeader{PacketType: qlog.PacketTypeRetry}})
								}
								if round == 2 {
									c.observer.RecordEvent(qlog.LossTimerUpdated{Type: qlog.LossTimerUpdateTypeExpired, TimerType: qlog.TimerTypePTO})
								}
								if round == 3 {
									c.mu.Lock()
									c.srvBig = true
									c.mu.Unlock()
								}
								for i := 0; i < k; i++ {
									guardWrite(t, c, addr, byte(round*k+i), token)
								}
							}
							st := c.finalSendStats()
							g := c.revisitGuardSnapshot()
							if len(retransWire(w)) != 4*k+firstExtra || st.ExtraSent.Sent != firstExtra || st.ExtraSent.FirstLead != firstLead || g.InitialTokenBytes != token || g.BundlesReserved != min(firstExtra, 1) || !g.RetryAccepted || g.ServerAcceptance != "unknown" {
								t.Fatal(kind, token, m, lead, k, st, g)
							}
							for i, f := range st.FlightTrace.Records {
								if i > 0 && (f.ExtraSent.Sent != 0 || f.Shape.Lead != 0 || f.Shape.Trail != 0) {
									t.Fatal("followup extras", kind, token, m, lead, k, i, f)
								}
							}
							if st.FlightTrace.Records[1].Shape.Phase != "retry_bundle" {
								t.Fatal(st.FlightTrace)
							}
						}
					}
				}
			}
		}
	})
}

func TestRevisitGuardInvalidInputDoesNotStartBundle(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		for _, change := range []func([]byte) []byte{
			func(d []byte) []byte { return d[:parseLongHdr(d).bodyOff] },
			func(d []byte) []byte { d[4] = 2; return d },
			func(d []byte) []byte { copy(d[parseLongHdr(d).bodyOff:], []byte{0x7f, 0xff}); return d },
			func(d []byte) []byte { d[parseLongHdr(d).bodyOff+2] = 0; return d },
		} {
			c, w, addr := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
			c.mode, c.layout = "fec", "v3"
			c.revisitGuard = newRevisitGuard(revisitGuardConfig{true, "supported"})
			d := change(guardInitial(1, 0))
			if _, err := c.WriteTo(d, addr); err == nil {
				t.Fatal("malformed Initial accepted")
			}
			if c.revisitGuardSnapshot().InitialSeen || c.snapshot().Flights != 0 || len(retransWire(w)) != 0 {
				t.Fatal("invalid input changed bundle")
			}
			c.finalSendStats()
		}
	})
}

func TestRevisitGuardRetryNotificationReleasesTraceLock(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, _, addr := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
		c.mode, c.layout, c.lead = "fec", "v3", 0
		c.revisitGuard = newRevisitGuard(revisitGuardConfig{true, "supported"})
		m := newMemoryTrace(time.Now())
		c.observer = m
		m.onRetry = func() { m.snapshot(); c.acceptedRevisitRetry() }
		guardWrite(t, c, addr, 1, 0)
		before := c.revisitGuardSnapshot()
		m.RecordEvent(qlog.PacketDropped{Header: qlog.PacketHeader{PacketType: qlog.PacketTypeRetry}})
		m.RecordEvent(qlog.PacketSent{Header: qlog.PacketHeader{PacketType: qlog.PacketTypeRetry}})
		if !reflect.DeepEqual(before, c.revisitGuardSnapshot()) {
			t.Fatal("unaccepted Retry changed policy")
		}
		m.RecordEvent(qlog.PacketReceived{Header: qlog.PacketHeader{PacketType: qlog.PacketTypeRetry}})
		m.RecordEvent(qlog.PacketReceived{Header: qlog.PacketHeader{PacketType: qlog.PacketTypeRetry}})
		if !c.revisitGuardSnapshot().RetryAccepted || c.revisitGuardSnapshot().BundlesReserved != 1 {
			t.Fatal(c.revisitGuardSnapshot())
		}
		c.finalSendStats()
	})
}

func TestRevisitGuardFailedWritesKeepReservation(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, w, addr := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
		c.mode, c.layout, c.m, c.lead = "fec", "v3", 2, 0
		c.revisitGuard = newRevisitGuard(revisitGuardConfig{true, "supported"})
		w.parityErr = errors.New("write failed")
		guardWrite(t, c, addr, 1, 91)
		c.acceptedRevisitRetry()
		guardWrite(t, c, addr, 2, 91)
		st := c.finalSendStats()
		if st.ParitySent != 0 || st.ParityFail != 2 || st.FlightTrace.Records[1].Shape.Trail != 0 || c.revisitGuardSnapshot().BundlesReserved != 1 {
			t.Fatal(st)
		}
	})
}

func TestRevisitGuardSnapshotConcurrent(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		gfInit()
		c, _, addr := flightInputFixture(flightExpectation{1, "explicit", "all_flights"})
		c.mode, c.layout, c.lead = "fec", "v3", 0
		c.revisitGuard = newRevisitGuard(revisitGuardConfig{true, "supported"})
		guardWrite(t, c, addr, 1, 0)
		var wg sync.WaitGroup
		for i := 0; i < 8; i++ {
			wg.Go(func() {
				for j := 0; j < 20; j++ {
					c.acceptedRevisitRetry()
					c.revisitGuardSnapshot()
				}
			})
		}
		for i := 0; i < 8; i++ {
			guardWrite(t, c, addr, byte(i+2), 0)
		}
		wg.Wait()
		c.finalSendStats()
		if c.revisitGuardSnapshot().BundlesReserved != 1 {
			t.Fatal(c.revisitGuardSnapshot())
		}
	})
}

func TestRevisitGuardFlagBoundaries(t *testing.T) {
	if checkRevisitGuard(revisitGuardConfig{false, "unknown"}, "server", "off", "v2", 1472, 0, false, false) != nil {
		t.Fatal("disabled guard changed existing flags")
	}
	for _, support := range []string{"unknown", "supported", "unsupported"} {
		for _, mode := range []string{"parity", "pad", "dup"} {
			err := checkRevisitGuard(revisitGuardConfig{true, support}, "client", "fec", "v3", 1280, 4, mode == "pad", mode == "dup")
			if (err == nil) != (mode != "parity" || support == "supported") {
				t.Fatal(support, mode, err)
			}
		}
	}
	for _, x := range []struct {
		mode, fec, layout string
		ips, m            int
	}{
		{"server", "fec", "v3", 1280, 1}, {"client", "auto3", "v3", 1280, 1},
		{"client", "fec", "v2", 1280, 1}, {"client", "fec", "v3", 1281, 1},
		{"client", "fec", "v3", 1280, 5}, {"client", "fec", "v3", 1280, 0},
	} {
		if checkRevisitGuard(revisitGuardConfig{true, "supported"}, x.mode, x.fec, x.layout, x.ips, x.m, false, false) == nil {
			t.Fatal(x)
		}
	}
	if checkRevisitGuard(revisitGuardConfig{false, "supported"}, "client", "fec", "v3", 1280, 1, false, false) == nil {
		t.Fatal("silent support flag")
	}
}
