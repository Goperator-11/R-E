package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"math"
	"net"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func cliClient(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	base := []string{"-mode", "client", "-fec", "auto3", "-addr", "127.0.0.1:1", "-n", "1", "-timeout", "200ms"}
	cmd := wiringMainCommand(t, ctx, append(base, args...)...)
	cmd.Dir = t.TempDir()
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	code := 0
	if err := cmd.Run(); err != nil {
		var exit *exec.ExitError
		if !errors.As(err, &exit) {
			t.Fatal(err)
		}
		code = exit.ExitCode()
	}
	return code, stdout.String(), stderr.String()
}

func TestCLIAuto3WithoutExplicitUplinkExitsTwo(t *testing.T) {
	code, stdout, stderr := cliClient(t)
	if code != 2 {
		t.Fatalf("exit %d, want 2, stderr %q", code, stderr)
	}
	if stdout != "" {
		t.Fatalf("stdout must stay empty: %q", stdout)
	}
	if !strings.Contains(stderr, "-fec auto3 needs explicit -uplink-mbps") {
		t.Fatalf("missing uplink message: %q", stderr)
	}
}

func TestCLIAuto3RowCarriesRequestedUplink(t *testing.T) {
	for _, tc := range []struct {
		flag string
		want float64
	}{{"2", 2}, {"7.5", 7.5}, {"0", 0}} {
		t.Run(tc.flag, func(t *testing.T) {
			code, stdout, stderr := cliClient(t, "-uplink-mbps", tc.flag)
			if code != 0 {
				t.Fatalf("exit %d, stderr %q", code, stderr)
			}
			lines := strings.Split(strings.TrimSpace(stdout), "\n")
			if len(lines) != 1 {
				t.Fatalf("want one row, got %d: %q", len(lines), stdout)
			}
			var fields map[string]json.RawMessage
			if err := json.Unmarshal([]byte(lines[0]), &fields); err != nil {
				t.Fatal(err)
			}
			raw, exists := fields["policy_uplink_mbps"]
			if !exists {
				t.Fatalf("row has no policy_uplink_mbps: %s", lines[0])
			}
			var got float64
			if err := json.Unmarshal(raw, &got); err != nil {
				t.Fatal(err)
			}
			if math.Abs(got-tc.want) > 1e-12 {
				t.Fatalf("policy_uplink_mbps = %v, want %v", got, tc.want)
			}
		})
	}
}

func TestCLIAuto3WarnsOnlyAboveParityCapForKOne(t *testing.T) {
	const warning = "auto3: no parity candidate above W 1407"
	for _, tc := range []struct {
		ips  string
		warn bool
	}{{"1406", false}, {"1407", false}, {"1408", true}, {"1452", true}} {
		t.Run(tc.ips, func(t *testing.T) {
			code, _, stderr := cliClient(t, "-uplink-mbps", "2", "-ips", tc.ips)
			if code != 0 {
				t.Fatalf("exit %d, stderr %q", code, stderr)
			}
			if strings.Contains(stderr, warning) != tc.warn {
				t.Fatalf("warning present = %v, want %v, stderr %q", !tc.warn, tc.warn, stderr)
			}
		})
	}
}

func TestCLIAuto3RejectsIPSOutsideQuicGoRange(t *testing.T) {
	for _, ips := range []string{"1199", "1453"} {
		t.Run(ips, func(t *testing.T) {
			code, stdout, stderr := cliClient(t, "-uplink-mbps", "2", "-ips", ips)
			if code != 2 || stdout != "" || !strings.Contains(stderr, "auto3: -fec auto3 needs 1200 <= InitialPacketSize <= 1452") {
				t.Fatalf("exit %d stdout %q stderr %q", code, stdout, stderr)
			}
		})
	}
}

func TestCLIAuto3ExploreRateMustBeFiniteAndNonNegative(t *testing.T) {
	const message = "auto3: -p3-explore-rate-ms must be finite and >= 0"
	for _, rate := range []string{"-0.05", "-1", "NaN", "+Inf"} {
		t.Run(rate, func(t *testing.T) {
			code, stdout, stderr := cliClient(t, "-uplink-mbps", "2", "-p3-explore-rate-ms", rate)
			if code != 2 || stdout != "" || !strings.Contains(stderr, message) {
				t.Fatalf("exit %d stdout %q stderr %q", code, stdout, stderr)
			}
		})
	}
	code, stdout, stderr := cliClient(t, "-uplink-mbps", "2", "-p3-explore-rate-ms", "0.05")
	if code != 0 || strings.Contains(stderr, message) || len(strings.Split(strings.TrimSpace(stdout), "\n")) != 1 {
		t.Fatalf("positive rate: exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

func TestCLIAuto3ExploreRateNeedsAuto3(t *testing.T) {
	const message = "auto3: -cache3 and -p3-explore-rate-ms need -fec auto3"
	for _, fec := range []string{"off", "fec", "auto"} {
		t.Run(fec, func(t *testing.T) {
			code, stdout, stderr := cliClient(t, "-fec", fec, "-p3-explore-rate-ms", "0.05")
			if code != 2 || stdout != "" || !strings.Contains(stderr, message) {
				t.Fatalf("exit %d stdout %q stderr %q", code, stdout, stderr)
			}
		})
	}
}

func TestFecMagicAtBodyNeedsInitialWithEmptyToken(t *testing.T) {
	valid := wireSizeParity(20, 2, 1394, fecVerLead)
	body := parseLongHdr(valid).bodyOff
	mutate := func(index int, value byte) []byte {
		packet := append([]byte(nil), valid...)
		packet[index] = value
		return packet
	}
	for _, tc := range []struct {
		name   string
		packet []byte
		magic  bool
	}{
		{"initial_empty_token", valid, true},
		{"initial_nonempty_token", mutate(body, 1), false},
		{"zero_rtt", mutate(0, 0xD3), false},
		{"handshake", mutate(0, 0xE3), false},
		{"retry", mutate(0, 0xF3), false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := fecMagicAtBody(tc.packet); got != tc.magic {
				t.Fatalf("fecMagicAtBody = %v, want %v", got, tc.magic)
			}
			if tc.magic {
				return
			}
			fed := &decodeConn{mode: "fec"}
			fed.feedOne(tc.packet)
			read := &decodeConn{mode: "fec"}
			read.PacketConn = &scriptConn{dgs: [][]byte{tc.packet}, addr: &net.UDPAddr{Port: 5555}}
			if _, _, err := read.ReadFrom(make([]byte, 1452)); err != nil {
				t.Fatal(err)
			}
			if fed.stats.FecParseFail != 0 || read.stats.FecParseFail != 0 {
				t.Fatalf("fec_parse_fail feedOne %d ReadFrom %d, want 0", fed.stats.FecParseFail, read.stats.FecParseFail)
			}
		})
	}
}

func TestP3GradeCutoffsMatchHandCalculation(t *testing.T) {
	c := &p3Ctx{K: 2, W: 1280, U: 2, RTT: 50, NNeed: 2}
	first, second, err := p3GradeCutoffs(c, p3Action{Delta: 0, Lead: 3, T: 1})
	if err != nil {
		t.Fatal(err)
	}
	const wantFirst = 75 + 26.212 + 3
	const wantSecond = wantFirst + 50 + 5.12
	if math.Abs(first-wantFirst) > 1e-9 || math.Abs(second-wantSecond) > 1e-9 {
		t.Fatalf("cutoffs %v %v, want %v %v", first, second, wantFirst, wantSecond)
	}
	noRate := &p3Ctx{K: 2, W: 1280, U: 0, RTT: 200, NNeed: 2}
	first, second, err = p3GradeCutoffs(noRate, p3Action{Lead: 1})
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(first-303) > 1e-9 || math.Abs(second-503) > 1e-9 {
		t.Fatalf("zero rate cutoffs %v %v, want 303 503", first, second)
	}
}
