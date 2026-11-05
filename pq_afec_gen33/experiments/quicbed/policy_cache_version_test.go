package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestDestCacheVersionedRoundTrip(t *testing.T) {
	path := filepath.Join(preservedTempDir(t), "cache.json")
	c := adaptationCache(true)
	c.path = path
	c.observeRTT("test", 75)
	c.M["test"].PolicyDecisions = 7
	c.M["test"].SymLastC1Decision = 5
	c.save()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var file destCacheFile
	if json.Unmarshal(data, &file) != nil || file.StateVersion != destCacheStateVersion || file.Destinations == nil {
		t.Fatalf("cache lacks explicit version: %s", data)
	}
	loaded := newDestCache(path)
	if !reflect.DeepEqual(c.M, loaded.M) {
		t.Fatalf("cache round trip changed records: %v %v", c.M, loaded.M)
	}
}

func TestDestCacheLegacyMigrationPreservesProvenance(t *testing.T) {
	data := []byte(`{"test":{"k":2,"server_flight":10472,"min_hct_ms":50,"min_rtt_ms":40,"rtt_observations":3,"sym_obs":20,"sym_loss":2,"conns":8,"rtt_ewma_ms":90,"sym_c1_conns":7,"sym_last_c1_conn":8,"sym_last_c1_decision":4,"policy_decisions":4}}`)
	path := filepath.Join(preservedTempDir(t), "cache.json")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	c := newDestCache(path)
	st := c.M["test"]
	if st == nil || st.K != 2 || st.Conns != 8 || st.SymObs != 20 || st.SymLoss != 2 {
		t.Fatal("legacy observations were lost")
	}
	if st.RTTEstimate != 0 || st.SymC1Conns != 0 || st.SymLastC1Conn != 0 || st.SymLastC1Decision != 0 || st.PolicyDecisions != 0 {
		t.Fatal("unversioned provenance was accepted as current")
	}
	if rtt, source := policyRTT(*st); rtt != 40 || source != "quic_ack_min_rtt" || recentSymbolFeedback(*st, 20) {
		t.Fatalf("legacy state invented current RTT or C1: %g %s", rtt, source)
	}
	c.save()
	loaded := newDestCache(path)
	if !reflect.DeepEqual(c.M, loaded.M) {
		t.Fatal("migrated state did not survive versioned reload")
	}
	loaded.observeRTT("test", 80)
	loaded.observeSymbols("test", 2, 0, 50)
	if rtt, source := policyRTT(*loaded.M["test"]); rtt != 80 || source != "quic_ack_rtt_ewma" || !recentSymbolFeedback(*loaded.M["test"], 20) {
		t.Fatal("new observations failed to replace legacy provenance")
	}
}

func TestDestCacheRejectsIncompleteAndUnknownVersionsAtomically(t *testing.T) {
	for _, data := range []string{
		`null`, `[]`, `{"test":null}`, `{"ok":{"k":2},"bad":null}`,
		`{"ok":{"k":2},"bad":{"k":"wrong"}}`, `{"test":{"unknown":3}}`,
		`{"state_version":0,"destinations":{}}`, `{"state_version":2,"destinations":{}}`,
		`{"state_version":1}`, `{"destinations":{}}`,
		`{"state_version":1,"destinations":null}`, `{"state_version":1,"destinations":{"test":null}}`,
		`{"state_version":1,"destinations":{},"extra":1}`, `{"state_version":1,"destinations":{}} {}`,
	} {
		t.Run(data, func(t *testing.T) {
			path := filepath.Join(preservedTempDir(t), "cache.json")
			if err := os.WriteFile(path, []byte(data), 0600); err != nil {
				t.Fatal(err)
			}
			cache := newDestCache(path)
			if cache.M == nil || len(cache.M) != 0 {
				t.Fatalf("bad cache accepted partially: %s", data)
			}
			cache.observeRTT("new", 50)
			if len(cache.M) != 1 {
				t.Fatal("rejected cache cannot accept a new observation")
			}
			unchanged, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(unchanged, []byte(data)) {
				t.Fatal("read modified rejected cache on disk")
			}
		})
	}
}
