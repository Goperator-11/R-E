package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/quic-go/quic-go"
)

const wiringMainEnv = "QAMP_WIRING_TEST_MAIN_ARGS"

func TestMain(m *testing.M) {
	if raw, ok := os.LookupEnv(wiringMainEnv); ok {
		var args []string
		if err := json.Unmarshal([]byte(raw), &args); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(2)
		}
		os.Args = append([]string{"qamp"}, args...)
		flag.CommandLine = flag.NewFlagSet("qamp", flag.ExitOnError)
		main()
		os.Exit(0)
	}
	os.Exit(m.Run())
}

func TestWireRunClientCarriesResolvedSettings(t *testing.T) {
	sealed := clientWiring{ExpectK: 0, ExpectKSet: true, FeedbackWait: 200 * time.Millisecond, RetransLayout: "repeat_first", ClientTracer: false, Profile: profileSealed31}
	base := clientWiring{ExpectK: 0, ExpectKSet: false, FeedbackWait: time.Second, RetransLayout: "repeat_first", ClientTracer: true, Profile: ""}
	for _, c := range []struct {
		name     string
		profile  string
		explicit map[string]bool
		mutate   func(*runSettings)
		want     clientWiring
		udpPath  string
		fbVer    int
	}{
		{"default", "", nil, nil, base, "oob", fbVer},
		{"default by name", "default", nil, nil, base, "oob", fbVer},
		{"sealed31", profileSealed31, nil, nil, sealed, "basic", fbVerFrozen},
		{"profile beats unset flags", profileSealed31, nil, func(s *runSettings) {
			s.RetransLayout, s.FeedbackWait, s.ClientTracer, s.ExpectK = "original_first", 3*time.Second, true, 7
			s.UDPPath, s.FeedbackVersion = "oob", fbVer
		}, sealed, "basic", fbVerFrozen},
		{"explicit original_first", "", map[string]bool{"retrans-layout": true}, func(s *runSettings) { s.RetransLayout = "original_first" },
			clientWiring{FeedbackWait: time.Second, RetransLayout: "original_first", ClientTracer: true}, "oob", fbVer},
		{"explicit expect-k under sealed31", profileSealed31, map[string]bool{"expect-k": true}, func(s *runSettings) { s.ExpectK = 3 },
			clientWiring{ExpectK: 3, ExpectKSet: true, FeedbackWait: 200 * time.Millisecond, RetransLayout: "repeat_first", Profile: profileSealed31}, "basic", fbVerFrozen},
		{"explicit tracer off", "", map[string]bool{"client-tracer": true}, func(s *runSettings) { s.ClientTracer = false },
			clientWiring{FeedbackWait: time.Second, RetransLayout: "repeat_first"}, "oob", fbVer},
		{"explicit wait", "", map[string]bool{"feedback-wait": true}, func(s *runSettings) { s.FeedbackWait = 50 * time.Millisecond },
			clientWiring{FeedbackWait: 50 * time.Millisecond, RetransLayout: "repeat_first", ClientTracer: true}, "oob", fbVer},
		{"sealed31 with matching explicit values", profileSealed31, map[string]bool{"retrans-layout": true, "client-tracer": true, "feedback-wait": true}, func(s *runSettings) {
			s.RetransLayout, s.ClientTracer, s.FeedbackWait = "repeat_first", false, 200*time.Millisecond
		}, sealed, "basic", fbVerFrozen},
	} {
		flags := defaultRunSettings()
		if c.mutate != nil {
			c.mutate(&flags)
		}
		explicit := c.explicit
		if explicit == nil {
			explicit = map[string]bool{}
		}
		w, err := wireRun("client", c.profile, explicit, flags, false)
		if err != nil {
			t.Fatalf("%s: %v", c.name, err)
		}
		if w.Client != c.want {
			t.Fatalf("%s: runClient would get %+v, want %+v", c.name, w.Client, c.want)
		}
		if w.Profile != c.want.Profile || w.Settings.RetransLayout != w.Client.RetransLayout || w.Settings.FeedbackWait != w.Client.FeedbackWait || w.Settings.ClientTracer != w.Client.ClientTracer {
			t.Fatalf("%s: settings %+v disagree with client wiring %+v", c.name, w.Settings, w.Client)
		}
		if w.Settings.UDPPath != c.udpPath || w.Settings.FeedbackVersion != c.fbVer {
			t.Fatalf("%s: server settings %+v", c.name, w.Settings)
		}
		if checkRetransLayout(w.Client.RetransLayout) != nil {
			t.Fatalf("%s: runClient would get retrans-layout %q", c.name, w.Client.RetransLayout)
		}
	}
}

func TestWireRunRejectsLikeCLI(t *testing.T) {
	for _, c := range []struct {
		name     string
		mode     string
		profile  string
		explicit map[string]bool
		mutate   func(*runSettings)
		guard    bool
	}{
		{"unknown profile", "client", "sealed30", nil, nil, false},
		{"sealed31 with oob", "server", profileSealed31, map[string]bool{"udp-path": true}, func(s *runSettings) { s.UDPPath = "oob" }, false},
		{"sealed31 with original_first", "client", profileSealed31, map[string]bool{"retrans-layout": true}, func(s *runSettings) { s.RetransLayout = "original_first" }, false},
		{"sealed31 with tracer", "client", profileSealed31, map[string]bool{"client-tracer": true}, func(s *runSettings) { s.ClientTracer = true }, false},
		{"empty retrans-layout", "client", "", nil, func(s *runSettings) { s.RetransLayout = "" }, false},
		{"client feedback-version", "client", "", map[string]bool{"feedback-version": true}, nil, false},
		{"guard without tracer", "client", "", map[string]bool{"client-tracer": true}, func(s *runSettings) { s.ClientTracer = false }, true},
		{"guard under sealed31", "client", profileSealed31, nil, nil, true},
	} {
		flags := defaultRunSettings()
		if c.mutate != nil {
			c.mutate(&flags)
		}
		explicit := c.explicit
		if explicit == nil {
			explicit = map[string]bool{}
		}
		if w, err := wireRun(c.mode, c.profile, explicit, flags, c.guard); err == nil {
			t.Fatalf("%s: accepted %+v", c.name, w)
		}
	}
}

func TestClientWiringInstallsTracerOnlyWhenEnabled(t *testing.T) {
	for _, c := range []struct {
		profile string
		tracer  string
		scope   string
	}{
		{"", "memory_qlog", "qlog_loss_timer_expired_lower_bound"},
		{profileSealed31, "disabled", "tracer_disabled"},
	} {
		w, err := wireRun("client", c.profile, map[string]bool{}, defaultRunSettings(), false)
		if err != nil {
			t.Fatal(err)
		}
		qconf := &quic.Config{}
		observer := newMemoryTrace(time.Now())
		w.Client.installTracer(qconf, observer)
		got := observer.snapshot()
		if (qconf.Tracer != nil) != w.Client.ClientTracer || got.Tracer != c.tracer || got.PTOScope != c.scope {
			t.Fatalf("profile %q: tracer installed %v, observation %q %q", c.profile, qconf.Tracer != nil, got.Tracer, got.PTOScope)
		}
	}
	off := &quic.Config{}
	clientWiring{ClientTracer: false}.installTracer(off, newMemoryTrace(time.Now()))
	on := &quic.Config{}
	clientWiring{ClientTracer: true}.installTracer(on, newMemoryTrace(time.Now()))
	if off.Tracer != nil || on.Tracer == nil {
		t.Fatalf("installTracer ignored ClientTracer: off %v on %v", off.Tracer != nil, on.Tracer != nil)
	}
}

func wiringMainCommand(t *testing.T, ctx context.Context, args ...string) *exec.Cmd {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(args)
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.CommandContext(ctx, exe)
	cmd.Env = append(os.Environ(), wiringMainEnv+"="+string(raw))
	return cmd
}

func TestWiringMainLoopbackRows(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	probe, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	addr := probe.LocalAddr().String()
	probe.Close()
	statsPath := filepath.Join(t.TempDir(), "server.json")
	server := wiringMainCommand(t, ctx, "-mode", "server", "-profile", profileSealed31, "-fec", "on", "-addr", addr, "-stats", statsPath)
	stderr, err := server.StderrPipe()
	if err != nil {
		t.Fatal(err)
	}
	if err := server.Start(); err != nil {
		t.Fatal(err)
	}
	exited := make(chan error, 1)
	ready := make(chan bool, 1)
	go func() {
		scanner := bufio.NewScanner(stderr)
		seen := false
		for scanner.Scan() {
			if !seen && strings.HasPrefix(scanner.Text(), "READY") {
				seen = true
				ready <- true
			}
		}
		if !seen {
			ready <- false
		}
		io.Copy(io.Discard, stderr)
		exited <- server.Wait()
	}()
	defer server.Process.Kill()
	select {
	case ok := <-ready:
		if !ok {
			t.Fatal("server exited before READY")
		}
	case <-ctx.Done():
		t.Fatal("server not ready")
	}
	for _, c := range []struct {
		profile string
		tracer  string
		waitMS  float64
		source  string
	}{
		{profileSealed31, "disabled", 200, "explicit_timer"},
		{"", "memory_qlog", 1000, "timer_only"},
	} {
		args := []string{"-mode", "client", "-addr", addr, "-fec", "on", "-layout", "v3", "-m", "2", "-lead", "1", "-n", "1", "-timeout", "5s"}
		if c.profile != "" {
			args = append(args, "-profile", c.profile)
		}
		var out, errOut bytes.Buffer
		client := wiringMainCommand(t, ctx, args...)
		client.Stdout, client.Stderr = &out, &errOut
		if err := client.Run(); err != nil {
			t.Fatalf("client %q: %v %s", c.profile, err, errOut.Bytes())
		}
		var rows []map[string]any
		for _, line := range strings.Split(out.String(), "\n") {
			if strings.HasPrefix(line, "{") {
				var row map[string]any
				if err := json.Unmarshal([]byte(line), &row); err != nil {
					t.Fatal(err)
				}
				rows = append(rows, row)
			}
		}
		if len(rows) != 1 {
			t.Fatalf("client %q rows %d: %s", c.profile, len(rows), out.Bytes())
		}
		row := rows[0]
		obs, _ := row["observation"].(map[string]any)
		expect, _ := row["flight_expectation"].(map[string]any)
		profile, hasProfile := row["profile"]
		if row["ok"] != true || row["retrans_layout"] != "repeat_first" || row["feedback_wait_limit_ms"] != c.waitMS || obs["tracer"] != c.tracer || expect["source"] != c.source || hasProfile != (c.profile != "") || hasProfile && profile != c.profile {
			t.Fatalf("client %q row: ok %v retrans %v wait %v tracer %v expectation %v profile %v", c.profile, row["ok"], row["retrans_layout"], row["feedback_wait_limit_ms"], obs["tracer"], expect, profile)
		}
	}
	if err := server.Process.Signal(syscall.SIGTERM); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-exited:
		if err != nil {
			t.Fatal("server exit", err)
		}
	case <-ctx.Done():
		t.Fatal("server did not stop")
	}
	data, err := os.ReadFile(statsPath)
	if err != nil {
		t.Fatal(err)
	}
	var stats map[string]any
	if err := json.Unmarshal(data, &stats); err != nil {
		t.Fatal(err)
	}
	if stats["profile"] != profileSealed31 || stats["udp_path"] != "basic" || stats["feedback_version"] != float64(fbVerFrozen) {
		t.Fatalf("server stats profile %v udp_path %v feedback_version %v", stats["profile"], stats["udp_path"], stats["feedback_version"])
	}
}
