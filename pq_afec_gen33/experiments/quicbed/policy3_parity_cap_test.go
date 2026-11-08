package main

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestParityCap(t *testing.T) {
	for i, want := range []int{1407, 1401, 1395, 1389} {
		if got := p3ParityCapW(i + 1); got != want {
			t.Fatalf("k=%d cap=%d, want %d", i+1, got, want)
		}
	}
}

func TestParityPossible(t *testing.T) {
	for k := 0; k <= 4; k++ {
		for _, w := range []int{1280, p3ParityCapW(k), p3ParityCapW(k) + 1} {
			for _, delta := range []int{0, 7} {
				t.Run(fmt.Sprintf("k%d/w%d/delta%d", k, w, delta), func(t *testing.T) {
					d := p3Decision{K: k, Action: p3Action{Delta: delta}}
					p := auto3PlanFor(d, w, 50, "quic_ack_min_rtt")
					row := auto3Row(trial{Arrivals: p3Arrivals{Src: "none"}}, p, p3ObsInfo{Y: -1}, nil, 0)
					data, err := json.Marshal(row)
					if err != nil {
						t.Fatal(err)
					}
					var raw map[string]any
					if err := json.Unmarshal(data, &raw); err != nil {
						t.Fatal(err)
					}
					value, exists := raw["policy_parity_possible"]
					if !exists {
						t.Fatal("policy_parity_possible omitted")
					}
					if k == 0 {
						if row.PolicyParityPossible != nil || value != nil {
							t.Fatalf("cold row must be null: %s", data)
						}
					} else if want := w <= p3ParityCapW(k); row.PolicyParityPossible == nil || *row.PolicyParityPossible != want || value != want {
						t.Fatalf("base W parity possibility mismatch: %s", data)
					}
				})
			}
		}
	}
}
