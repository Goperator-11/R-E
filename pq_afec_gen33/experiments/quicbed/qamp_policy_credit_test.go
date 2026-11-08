package main

import (
	"bytes"
	"net"
	"testing"
)

func TestPolicyCreditMatchesDecoder(t *testing.T) {
	gfInit()
	rows, complete, incomplete := 0, 0, 0
	for k := 1; k <= 4; k++ {
		for m := 1; m <= 4; m++ {
			for lead := 0; lead <= m; lead++ {
				dg, src := leadBuildFlight(fecVerLead, lead, m, k, byte(17*lead+5*m+k))
				originalBytes, pz := 0, 0
				for _, d := range src {
					originalBytes += len(d)
				}
				for _, d := range dg {
					if d.orig < 0 {
						if pz != 0 && pz != len(d.data) {
							t.Fatalf("k%d m%d lead%d: parity lengths %d and %d differ", k, m, lead, pz, len(d.data))
						}
						pz = len(d.data)
					}
				}
				for mask := 0; mask < 1<<len(dg); mask++ {
					rows++
					var send [][]byte
					arrived, leadArrived, trailArrived := 0, 0, 0
					for i, d := range dg {
						if mask&(1<<i) == 0 {
							continue
						}
						send = append(send, d.data)
						switch {
						case d.orig >= 0:
							arrived++
						case d.credit:
							leadArrived++
						default:
							trailArrived++
						}
					}
					wire := &auditConn{scriptConn: scriptConn{dgs: send,
						addr: &net.UDPAddr{IP: net.IPv4(10, 9, 0, 3), Port: 5555}}}
					sv := &decodeConn{mode: "fec"}
					sv.PacketConn = wire
					var got [][]byte
					handed := 0
					buf := make([]byte, 2000)
					for {
						n, _, err := sv.ReadFrom(buf)
						if err != nil {
							if err.Error() != "대본 끝" || wire.i != len(send) {
								t.Fatalf("k%d m%d lead%d mask%x: read ended with %v after %d/%d inputs", k, m, lead, mask, err, wire.i, len(send))
							}
							break
						}
						handed += n
						got = append(got, append([]byte(nil), buf[:n]...))
					}
					covered := true
					for _, original := range src {
						found := false
						for _, delivered := range got {
							if bytes.Equal(original, delivered) {
								found = true
								break
							}
						}
						covered = covered && found
					}
					miss := k - arrived
					ok := miss <= trailArrived
					if covered != ok {
						t.Fatalf("k%d m%d lead%d mask%x: originals complete %v, miss %d trail arrived %d", k, m, lead, mask, covered, miss, trailArrived)
					}
					if ok {
						complete++
						want := originalBytes + (leadArrived+trailArrived-miss)*pz
						if handed != want {
							t.Fatalf("k%d m%d lead%d mask%x: stack bytes %d, want %d (originals %d, lead %d, trail %d, miss %d, parity %d)", k, m, lead, mask, handed, want, originalBytes, leadArrived, trailArrived, miss, pz)
						}
					} else {
						incomplete++
					}
				}
			}
		}
	}
	if rows != 3840 {
		t.Fatalf("rows %d, want 3840", rows)
	}
	t.Logf("rows %d, complete %d, incomplete %d", rows, complete, incomplete)
}
