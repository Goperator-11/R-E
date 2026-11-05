package main

import "fmt"

type flightShape struct {
	Phase             string `json:"phase"`
	Rule              string `json:"rule"`
	Lead              int    `json:"lead"`
	Trail             int    `json:"trail"`
	OriginalImmediate bool   `json:"original_immediate"`
	PTOCountAtStart   int    `json:"pto_count_at_start"`
	PTOScope          string `json:"pto_scope"`
}

func checkRetransLayout(value string) error {
	if value != "original_first" && value != "repeat_first" {
		return fmt.Errorf("retrans-layout must be original_first or repeat_first: %q", value)
	}
	return nil
}

func (c *fecConn) retransLayout() string {
	if !c.v3() {
		return "not_applicable"
	}
	if c.retransMode == "" {
		return defaultRunSettings().RetransLayout
	}
	return c.retransMode
}

func (c *fecConn) flightShapeLocked() flightShape {
	s := flightShape{Phase: "first_bundle", Rule: "disabled", OriginalImmediate: c.mode == "off", PTOScope: "unavailable"}
	if c.stats.Flights > 0 {
		s.Phase = "pre_response_followup"
	}
	if c.srvBig {
		s.Phase = "post_response"
	}
	if c.observer != nil {
		c.observer.mu.Lock()
		s.PTOCountAtStart = c.observer.data.PTOCount
		s.PTOScope = c.observer.data.PTOScope
		c.observer.mu.Unlock()
	}
	if c.mode != "fec" {
		return s
	}
	s.Lead = c.firstLead()
	s.Trail = c.m - s.Lead
	s.Rule = "first_layout"
	if c.revisitGuard != nil {
		return c.revisitShapeLocked(s)
	}
	if !c.v3() {
		s.Rule = "v2_layout"
		return s
	}
	if c.curLater {
		s.Rule = "post_response_xor"
		s.Lead = 0
		s.Trail = min(1, s.Trail)
		s.OriginalImmediate = true
	} else if c.stats.Flights > 0 {
		s.Rule = c.retransLayout()
		if s.Rule == "original_first" {
			s.Lead = 0
			s.Trail = min(1, c.m)
		}
	}
	return s
}
