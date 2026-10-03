package main

import (
	"bytes"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func p3CacheTransactionSnapshot(t *testing.T, c *destCache3) ([]byte, []byte) {
	t.Helper()
	inMemory, err := json.Marshal(c.Dests)
	if err != nil {
		t.Fatal(err)
	}
	if err := c.save(); err != nil {
		t.Fatal(err)
	}
	onDisk, err := os.ReadFile(c.path)
	if err != nil {
		t.Fatal(err)
	}
	return inMemory, onDisk
}

func TestP3CacheFailedCallsPreserveMemoryAndSavedJSON(t *testing.T) {
	for _, existing := range []bool{false, true} {
		for _, failure := range []string{"plan_inputs", "observe_inputs", "action", "hct", "srv", "j_pred"} {
			t.Run(map[bool]string{false: "new", true: "existing"}[existing]+"/"+failure, func(t *testing.T) {
				c, err := loadDestCache3(filepath.Join(t.TempDir(), "cache.json"))
				if err != nil {
					t.Fatal(err)
				}
				const addr = "127.0.0.1:44434"
				if existing {
					if _, err := c.plan(addr, 1280, 2, cPktDefault); err != nil {
						t.Fatal(err)
					}
					if _, _, err := c.observe(addr, p3Action{}, 60, true, 2, 18000, 50, true, 1280, 2, cPktDefault); err != nil {
						t.Fatal(err)
					}
				}
				entry := c.Dests[addr]
				var state *p3State
				if entry != nil {
					state = entry.State
				}
				beforeMemory, beforeDisk := p3CacheTransactionSnapshot(t, c)
				a, hct, srv, w := p3Action{}, 40.0, 18000.0, 1280
				var pred *float64
				switch failure {
				case "plan_inputs":
					_, err = c.plan(addr, 1199, 2, cPktDefault)
				case "observe_inputs":
					w = 1199
				case "action":
					a.Lead = 5
				case "hct":
					hct = math.Inf(1)
				case "srv":
					srv = -1
				case "j_pred":
					j := math.Inf(1)
					pred = &j
				}
				if failure != "plan_inputs" {
					_, _, err = c.observePred(addr, a, pred, hct, true, 2, srv, 20, true, w, 2, cPktDefault)
				}
				if err == nil {
					t.Fatal("invalid call succeeded")
				}
				afterMemory, afterDisk := p3CacheTransactionSnapshot(t, c)
				if !bytes.Equal(beforeMemory, afterMemory) || !bytes.Equal(beforeDisk, afterDisk) {
					t.Fatal("failed call changed cache memory or saved JSON")
				}
				if c.Dests[addr] != entry || (entry != nil && entry.State != state) {
					t.Fatal("failed call changed entry or learner pointer")
				}
			})
		}
	}
}

func TestP3CacheSuccessfulCommitKeepsEntryAndStatePointers(t *testing.T) {
	c, err := loadDestCache3("")
	if err != nil {
		t.Fatal(err)
	}
	const addr = "127.0.0.1:44434"
	p, err := c.plan(addr, 1280, 2, cPktDefault)
	if err != nil || p.Decision.Why != "cold" || p.Decision.DecIndex != 1 {
		t.Fatalf("cold fallback: %+v, %v", p.Decision, err)
	}
	entry, state := c.Dests[addr], c.Dests[addr].State
	if _, _, err := c.observe(addr, p.Action, 60, true, 5, 18000, 50, true, 1280, 2, cPktDefault); err != nil {
		t.Fatal(err)
	}
	if c.Dests[addr] != entry || entry.State != state || entry.Conns != 1 || entry.RTTObs != 1 ||
		entry.MinRTT != 50 || entry.MinHCT != 60 || state.Stats.Obs != 1 || state.Stats.Predict != 1 {
		t.Fatalf("successful observation lost identity or metadata: %+v, %+v", entry, state.Stats)
	}
	for i := 0; i < 2; i++ {
		p, err = c.plan(addr, 1280, 2, cPktDefault)
		if err != nil || p.Decision.Why != "k_range" || p.Decision.DecIndex != i+2 {
			t.Fatalf("large observed k fallback: %+v, %v", p.Decision, err)
		}
		if c.Dests[addr] != entry || entry.State != state {
			t.Fatal("successful decision replaced entry or learner pointer")
		}
	}
}

func TestP3CacheInvalidLearnerReturnsErrorWithoutMetadataChanges(t *testing.T) {
	for _, nilState := range []bool{false, true} {
		c, err := loadDestCache3("")
		if err != nil {
			t.Fatal(err)
		}
		state := newP3State()
		if nilState {
			state = nil
		} else {
			state.Post = nil
		}
		entry := &cache3Entry{State: state, MinRTT: 50, RTTObs: 1, MinHCT: 60, Conns: 1}
		c.Dests["x"] = entry
		before, err := json.Marshal(c.Dests)
		if err != nil {
			t.Fatal(err)
		}
		if _, _, err := c.observe("x", p3Action{}, 40, true, 2, 18000, 20, true, 1280, 2, cPktDefault); err == nil {
			t.Fatal("invalid learner accepted")
		}
		after, _ := json.Marshal(c.Dests)
		if !bytes.Equal(before, after) || c.Dests["x"] != entry || entry.State != state {
			t.Fatal("invalid learner call changed cache")
		}
	}
}

func TestP3GuardGapOverflowRejectedOnRestoreAndObserve(t *testing.T) {
	st := newP3State()
	st.GCommon = []float64{-1e308}
	st.GResid[p3Action{Lead: 1}.Key()] = []float64{1e308}
	if err := st.validate(); err == nil {
		t.Fatal("finite residuals with an infinite guard gap accepted")
	}
	path := filepath.Join(t.TempDir(), "cache.json")
	c := &destCache3{path: path, Dests: map[string]*cache3Entry{"x": {State: st}}}
	raw, err := json.Marshal(struct {
		Schema string                  `json:"schema"`
		Dests  map[string]*cache3Entry `json:"dests"`
	}{p3CacheSchema, c.Dests})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := loadDestCache3(path); err == nil || !strings.Contains(err.Error(), "guard residual gap") {
		t.Fatal("cache with an infinite derived guard gap accepted")
	}

	for _, common := range []float64{-1e308, -5e307} {
		st = newP3State()
		for i := 0; i < p3GuardMin; i++ {
			st.GCommon = append(st.GCommon, common)
		}
		if err := st.validate(); err != nil {
			t.Fatal(err)
		}
		before, _ := json.Marshal(st)
		pred := 0.0
		_, err := p3Observe(st, p3Action{}, 1e308, true, 2, 18000, 50, 1280, 2, cPktDefault, &pred)
		if common == -1e308 {
			if err == nil {
				t.Fatal("observation producing an infinite guard gap accepted")
			}
			after, _ := json.Marshal(st)
			if !bytes.Equal(before, after) {
				t.Fatal("guard gap rejection changed direct learner state")
			}
		} else {
			if err != nil || st.Stats.Obs != 1 || st.Stats.Resid != 1 {
				t.Fatalf("finite guard gap rejected: %v, %+v", err, st.Stats)
			}
			if err := st.validate(); err != nil {
				t.Fatal(err)
			}
		}
	}
}

func TestP3CacheLoaderRejectsMetadataAndTrailingDocuments(t *testing.T) {
	for _, field := range []string{"min_rtt_ms", "min_hct_ms", "rtt_observations", "conns"} {
		t.Run(field, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "cache.json")
			c, err := loadDestCache3(path)
			if err != nil {
				t.Fatal(err)
			}
			c.Dests["x"] = &cache3Entry{State: newP3State()}
			if err := c.save(); err != nil {
				t.Fatal(err)
			}
			raw, _ := os.ReadFile(path)
			bad := strings.Replace(string(raw), `"`+field+`":0`, `"`+field+`":-1`, 1)
			if bad == string(raw) {
				t.Fatal("metadata fixture field not found")
			}
			if err := os.WriteFile(path, []byte(bad), 0644); err != nil {
				t.Fatal(err)
			}
			if _, err := loadDestCache3(path); err == nil {
				t.Fatal("negative cache metadata accepted")
			}
		})
	}
	path := filepath.Join(t.TempDir(), "cache.json")
	c, err := loadDestCache3(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := c.save(); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(path)
	for _, suffix := range []string{"{}", "garbage", "{} trailing garbage", " \r\n\t "} {
		if err := os.WriteFile(path, append(append([]byte{}, raw...), []byte(suffix)...), 0644); err != nil {
			t.Fatal(err)
		}
		_, err := loadDestCache3(path)
		if strings.TrimSpace(suffix) == "" {
			if err != nil {
				t.Fatalf("trailing whitespace rejected: %v", err)
			}
		} else if err == nil {
			t.Fatalf("trailing data %q accepted", suffix)
		}
	}
}

func TestP3CacheSaveRejectsInvalidEntryWithoutChangingSavedFile(t *testing.T) {
	for _, field := range []string{"min_rtt", "min_hct", "rtt_obs", "conns", "state", "nonfinite_rtt", "nonfinite_hct"} {
		t.Run(field, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "cache.json")
			c, err := loadDestCache3(path)
			if err != nil {
				t.Fatal(err)
			}
			e := &cache3Entry{State: newP3State(), MinRTT: 50, RTTObs: 1, MinHCT: 60, Conns: 1}
			c.Dests["x"] = e
			if err := c.save(); err != nil {
				t.Fatal(err)
			}
			before, _ := os.ReadFile(path)
			switch field {
			case "min_rtt":
				e.MinRTT = -1
			case "min_hct":
				e.MinHCT = -1
			case "rtt_obs":
				e.RTTObs = -1
			case "conns":
				e.Conns = -1
			case "state":
				e.State.Post = nil
			case "nonfinite_rtt":
				e.MinRTT = math.NaN()
			case "nonfinite_hct":
				e.MinHCT = math.Inf(1)
			}
			if err := c.save(); err == nil {
				t.Fatal("invalid entry saved")
			}
			after, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(before, after) || c.Dests["x"] != e {
				t.Fatal("failed save changed saved file or memory entry")
			}
		})
	}
}

func TestP3ObserveNonfiniteTransferredBaselinePreservesState(t *testing.T) {
	st := newP3State()
	st.KHist = []int{2}
	st.SHist = []float64{18000}
	for i := 0; i < p3BaseMin; i++ {
		st.HCT["0,0,0"] = append(st.HCT["0,0,0"], math.MaxFloat64)
	}
	st.HCTSeq["0,0,0"] = 0
	st.Seq = 1
	before, _ := json.Marshal(st)
	if _, err := p3Observe(st, p3Action{Lead: 1}, 100, true, 2, 18000, 1e306, 1280, 0, cPktDefault, nil); err == nil {
		t.Fatal("infinite transferred baseline accepted")
	}
	after, _ := json.Marshal(st)
	if !bytes.Equal(before, after) {
		t.Fatal("baseline overflow rejection changed state")
	}
}
