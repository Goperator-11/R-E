package main

import (
	"encoding/json"
	"flag"
	"testing"
)

func TestAuto3ExplicitUplinkAndRowRoundTrip(t *testing.T) {
	for _, tc := range []struct {
		name string
		args []string
		want float64
		ok   bool
	}{
		{"missing", nil, 0, false},
		{"zero", []string{"-uplink-mbps", "0"}, 0, true},
		{"zero_equals", []string{"-uplink-mbps=0"}, 0, true},
		{"two", []string{"-uplink-mbps", "2"}, 2, true},
		{"default_explicit", []string{"-uplink-mbps", "10"}, 10, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			fs := flag.NewFlagSet(tc.name, flag.ContinueOnError)
			uplink := fs.Float64("uplink-mbps", uplinkMbpsDefault, "")
			if err := fs.Parse(tc.args); err != nil {
				t.Fatal(err)
			}
			explicit := map[string]bool{}
			fs.Visit(func(f *flag.Flag) { explicit[f.Name] = true })
			err := checkAuto3Uplink(explicit)
			if !tc.ok {
				if err == nil || err.Error() != "-fec auto3 needs explicit -uplink-mbps" {
					t.Fatalf("missing uplink: %v", err)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			row := auto3Row(trial{Arrivals: p3Arrivals{Src: "none"}}, auto3Plan{}, p3ObsInfo{Y: -1}, nil, 0)
			row.PolicyUplinkMbps = *uplink
			raw, err := json.Marshal(row)
			if err != nil {
				t.Fatal(err)
			}
			var fields map[string]json.RawMessage
			if err := json.Unmarshal(raw, &fields); err != nil {
				t.Fatal(err)
			}
			value, exists := fields["policy_uplink_mbps"]
			if !exists || string(value) == "null" {
				t.Fatalf("missing policy_uplink_mbps: %s", raw)
			}
			var got trial3
			if err := json.Unmarshal(raw, &got); err != nil {
				t.Fatal(err)
			}
			if got.PolicyUplinkMbps != tc.want {
				t.Fatalf("uplink round trip = %v, want %v", got.PolicyUplinkMbps, tc.want)
			}
		})
	}
}
