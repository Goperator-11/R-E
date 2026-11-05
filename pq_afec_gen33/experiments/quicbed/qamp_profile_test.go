package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func TestRunDefaultsMatchCostModelLayout(t *testing.T) {
	d := defaultRunSettings()
	if d.RetransLayout != "repeat_first" {
		t.Fatalf("CLI retrans-layout default %q is not the shape priced by layout.evaluate and p3Evaluate", d.RetransLayout)
	}
	if d.UDPPath != "oob" || d.FeedbackWait != time.Second || d.FeedbackVersion != fbVer || !d.ClientTracer || d.ExpectKSet {
		t.Fatalf("other v33 defaults changed: %+v", d)
	}
	if err := checkRunSettings("client", nil, d, false); err != nil {
		t.Fatal(err)
	}
}

func TestRunProfileSealed31AppliesV31Conditions(t *testing.T) {
	s := defaultRunSettings()
	s.ExpectK = 3
	if err := applyRunProfile(profileSealed31, map[string]bool{}, &s); err != nil {
		t.Fatal(err)
	}
	want := runSettings{UDPPath: "basic", RetransLayout: "repeat_first", FeedbackWait: 200 * time.Millisecond, FeedbackVersion: fbVerFrozen, ClientTracer: false, ExpectK: 0, ExpectKSet: true}
	if s != want {
		t.Fatalf("sealed31 %+v, want %+v", s, want)
	}
	if err := checkRunSettings("server", nil, s, false); err != nil {
		t.Fatal(err)
	}
	if got := chooseFlightExpectation(s.ExpectK, s.ExpectKSet, "auto3", auto3Plan{Decision: p3Decision{HasEJ: true, K: 2}}); got.Source != "explicit_timer" || got.K != 0 {
		t.Fatalf("sealed31 auto3 used cached_k: %+v", got)
	}
	explicitK := defaultRunSettings()
	explicitK.ExpectK, explicitK.ExpectKSet = 2, true
	if err := applyRunProfile(profileSealed31, map[string]bool{"expect-k": true}, &explicitK); err != nil || explicitK.ExpectK != 2 || !explicitK.ExpectKSet {
		t.Fatalf("explicit expect-k was replaced: %+v %v", explicitK, err)
	}
	same := defaultRunSettings()
	same.UDPPath, same.RetransLayout, same.FeedbackWait, same.FeedbackVersion, same.ClientTracer = "basic", "repeat_first", 200*time.Millisecond, fbVerFrozen, false
	all := map[string]bool{"udp-path": true, "retrans-layout": true, "feedback-wait": true, "feedback-version": true, "client-tracer": true}
	if err := applyRunProfile(profileSealed31, all, &same); err != nil {
		t.Fatal("explicit values equal to the profile were refused", err)
	}
}

func TestRunProfileRejectsConflictsAndUnknownNames(t *testing.T) {
	for _, c := range []struct {
		flag string
		set  func(*runSettings)
	}{
		{"udp-path", func(s *runSettings) { s.UDPPath = "oob" }},
		{"retrans-layout", func(s *runSettings) { s.RetransLayout = "original_first" }},
		{"feedback-wait", func(s *runSettings) { s.FeedbackWait = time.Second }},
		{"feedback-version", func(s *runSettings) { s.FeedbackVersion = fbVer }},
		{"client-tracer", func(s *runSettings) { s.ClientTracer = true }},
	} {
		s := defaultRunSettings()
		c.set(&s)
		before := s
		err := applyRunProfile(profileSealed31, map[string]bool{c.flag: true}, &s)
		if err == nil || !strings.Contains(err.Error(), c.flag) || s != before {
			t.Fatalf("%s conflict: %v %+v", c.flag, err, s)
		}
	}
	s := defaultRunSettings()
	before := s
	if err := applyRunProfile("", map[string]bool{}, &s); err != nil || s != before {
		t.Fatal("default profile changed settings", err)
	}
	if applyRunProfile("sealed30", map[string]bool{}, &s) == nil {
		t.Fatal("unknown profile accepted")
	}
}

func TestRunSettingsOptionScope(t *testing.T) {
	d := defaultRunSettings()
	for _, c := range []struct {
		mode     string
		explicit map[string]bool
		mutate   func(*runSettings)
		guard    bool
		ok       bool
	}{
		{"server", map[string]bool{"feedback-version": true, "conn-log": true}, nil, false, true},
		{"client", map[string]bool{"feedback-version": true}, nil, false, false},
		{"client", map[string]bool{"conn-log": true}, nil, false, false},
		{"server", map[string]bool{"client-tracer": true}, nil, false, false},
		{"client", map[string]bool{"client-tracer": true}, func(s *runSettings) { s.ClientTracer = false }, false, true},
		{"client", nil, func(s *runSettings) { s.ClientTracer = false }, true, false},
		{"client", nil, func(s *runSettings) { s.FeedbackVersion = 4 }, false, false},
		{"client", nil, func(s *runSettings) { s.UDPPath = "mmsg" }, false, false},
		{"client", nil, func(s *runSettings) { s.RetransLayout = "repeat" }, false, false},
		{"client", nil, func(s *runSettings) { s.FeedbackWait = -time.Millisecond }, false, false},
		{"client", nil, func(s *runSettings) { s.ExpectK = 33 }, false, false},
	} {
		s := d
		if c.mutate != nil {
			c.mutate(&s)
		}
		if err := checkRunSettings(c.mode, c.explicit, s, c.guard); (err == nil) != c.ok {
			t.Fatalf("%+v: %v", c, err)
		}
	}
}

func TestClientTracerDisabledKeepsServerBytes(t *testing.T) {
	m := newMemoryTrace(time.Now())
	m.disableTracer()
	big := auditInitial(1)
	big = append(big, make([]byte, serverFlightMin)...)
	reply := buildFeedback([]byte{1}, []byte{2}, fbRec{crcs: []uint32{1}})
	m.datagram(big, false)
	m.datagram(reply, true)
	x := m.snapshot()
	if x.Tracer != "disabled" || x.PTOScope != "tracer_disabled" || x.ServerBytes != int64(len(big)) || len(x.Datagrams) != 2 || len(x.Packets) != 0 {
		t.Fatalf("observation without tracer %+v", x)
	}
	c := &fecConn{mode: "fec", m: 1, layout: "v3", lead: 0, observer: m}
	if shape := c.flightShapeLocked(); shape.PTOScope != "tracer_disabled" || shape.PTOCountAtStart != 0 {
		t.Fatalf("flight shape hides the disabled tracer: %+v", shape)
	}
	on := newMemoryTrace(time.Now()).snapshot()
	if on.Tracer != "memory_qlog" || on.PTOScope != "qlog_loss_timer_expired_lower_bound" {
		t.Fatalf("default tracer %+v", on)
	}
}

func TestProfileRecordedOnRowsAndServerStats(t *testing.T) {
	raw, _ := json.Marshal(&trial{})
	var row map[string]any
	json.Unmarshal(raw, &row)
	if _, ok := row["profile"]; ok {
		t.Fatalf("default rows gained a profile key: %s", raw)
	}
	raw, _ = json.Marshal(&trial{Profile: profileSealed31})
	row = map[string]any{}
	json.Unmarshal(raw, &row)
	if row["profile"] != profileSealed31 {
		t.Fatalf("row %s", raw)
	}
	raw, _ = json.Marshal((&decodeConn{profile: profileSealed31, feedbackVersion: fbVerFrozen}).report(false))
	var st map[string]any
	json.Unmarshal(raw, &st)
	if st["profile"] != profileSealed31 || st["feedback_version"] != float64(fbVerFrozen) || st["udp_path"] != "basic" {
		t.Fatalf("server stats %s", raw)
	}
}
