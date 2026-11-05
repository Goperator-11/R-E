package main

import (
	"bufio"
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"
	"time"
)

type connLogCloser struct{ closed int }

func (c *connLogCloser) Close() error { c.closed++; return nil }

func connLogLines(t *testing.T, data []byte) []map[string]any {
	t.Helper()
	var out []map[string]any
	scanner := bufio.NewScanner(bytes.NewReader(data))
	scanner.Buffer(make([]byte, 1<<16), 1<<20)
	for scanner.Scan() {
		var line map[string]any
		if err := json.Unmarshal(scanner.Bytes(), &line); err != nil {
			t.Fatalf("invalid JSONL line %q: %v", scanner.Text(), err)
		}
		out = append(out, line)
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	return out
}

func TestConnLogRecordsEveryAccountOnceBeforeExpiry(t *testing.T) {
	var buf bytes.Buffer
	s := &decodeConn{feedback: true}
	s.connLog = newConnLogger("memory", &buf, nil)
	peer := &net.UDPAddr{Port: 5555}
	start := time.Now()
	const total = 5000
	for i := 0; i < total; i++ {
		cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
		ca := s.acctLocked(peer, accountingPacket(0, cid, cid), false)
		if ca == nil {
			t.Fatalf("account %d missing", i)
		}
		ca.RxBytes = int64(i + 1)
		ca.TxSizes = []int{1200, 1200, i + 1}
		if len(s.feedbackLocked(accountingPacket(2, cid, cid), ca)) == 0 {
			t.Fatalf("feedback %d missing", i)
		}
		s.accountEndedLocked(ca, start, true)
	}
	raw, err := json.Marshal(s.report(false))
	if err != nil {
		t.Fatal(err)
	}
	var periodic map[string]any
	if err := json.Unmarshal(raw, &periodic); err != nil || len(periodic["conns"].(map[string]any)) != 0 {
		t.Fatal("periodic stats are expected to omit per-connection records")
	}
	s.flushConnLog(start.Add(accountRetention))
	if len(s.conns) != 0 {
		t.Fatalf("accounts left after retention: %d", len(s.conns))
	}
	lines := connLogLines(t, buf.Bytes())
	if len(lines) != total {
		t.Fatalf("conn-log has %d lines for %d connections", len(lines), total)
	}
	keys := map[string]bool{}
	rx := map[float64]bool{}
	reasons := map[string]int{}
	for _, line := range lines {
		key, _ := line["key"].(string)
		if key == "" || keys[key] {
			t.Fatalf("missing or duplicate key %v", line["key"])
		}
		keys[key] = true
		rx[line["rx_bytes"].(float64)] = true
		reasons[line["reason"].(string)]++
		sizes := line["tx_sizes"].([]any)
		if line["fb_sent"] != true || line["handshake_complete_ns"].(float64) == 0 || len(sizes) != 3 || sizes[2].(float64) != line["rx_bytes"].(float64) {
			t.Fatalf("record lost connection fields: %v", line)
		}
	}
	if len(rx) != total || reasons["lru"] != total-connAcctCap || reasons["expired"] != connAcctCap {
		t.Fatalf("reasons %v, distinct rx %d", reasons, len(rx))
	}
	report := s.report(true)
	raw, _ = json.Marshal(report)
	var final map[string]any
	json.Unmarshal(raw, &final)
	cl := final["conn_log"].(map[string]any)
	if cl["lines"].(float64) != total || cl["errors"].(float64) != 0 || cl["pending"].(float64) != 0 {
		t.Fatalf("conn_log report %v", cl)
	}
}

func TestConnLogSnapshotIsIndependentAndOncePerAccount(t *testing.T) {
	var buf bytes.Buffer
	closer := &connLogCloser{}
	s := &decodeConn{}
	s.connLog = newConnLogger("memory", &buf, closer)
	peer := &net.UDPAddr{Port: 5555}
	var accounts []*connAcct
	for i := 0; i < 3; i++ {
		cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
		ca := s.acctLocked(peer, accountingPacket(0, cid, cid), false)
		ca.TxSizes = []int{100 + i}
		ca.RxCRC = []uint32{uint32(i)}
		accounts = append(accounts, ca)
	}
	s.evictAccountLocked(accounts[0], false)
	accounts[0].TxSizes[0] = 999
	accounts[0].RxCRC[0] = 999
	accounts[0].RxBytes = 777
	s.evictAccountLocked(accounts[0], false)
	if len(s.connLogPending) != 1 {
		t.Fatalf("pending %d", len(s.connLogPending))
	}
	if err := s.finishConnLog(time.Now()); err != nil {
		t.Fatal(err)
	}
	accounts[1].TxSizes[0] = 555
	s.evictAccountLocked(accounts[1], true)
	s.flushConnLog(time.Now())
	if err := s.finishConnLog(time.Now()); err != nil || closer.closed != 1 {
		t.Fatal("logger closed more than once", err, closer.closed)
	}
	lines := connLogLines(t, buf.Bytes())
	if len(lines) != 3 {
		t.Fatalf("lines %d: %s", len(lines), buf.Bytes())
	}
	if lines[0]["reason"] != "expired" || lines[0]["tx_sizes"].([]any)[0].(float64) != 100 || lines[0]["rx_crc"].([]any)[0].(float64) != 0 || lines[0]["rx_bytes"].(float64) != 0 {
		t.Fatalf("expired snapshot changed after eviction: %v", lines[0])
	}
	for i, line := range lines[1:] {
		if line["reason"] != "shutdown" || line["tx_sizes"].([]any)[0].(float64) != float64(101+i) {
			t.Fatalf("shutdown line %d: %v", i, line)
		}
	}
	if s.connLog.lines.Load() != 3 {
		t.Fatalf("written %d", s.connLog.lines.Load())
	}
}

func TestConnLogShutdownThenExpiryKeepsOneLine(t *testing.T) {
	for _, c := range []struct {
		name   string
		finish time.Duration
		flush  time.Duration
	}{
		{"expiry inside finish", accountRetention, 0},
		{"expiry after finish", time.Second, 2 * accountRetention},
	} {
		var buf bytes.Buffer
		closer := &connLogCloser{}
		s := &decodeConn{}
		s.connLog = newConnLogger("memory", &buf, closer)
		peer := &net.UDPAddr{Port: 5555}
		start := time.Now()
		for i := 0; i < 2; i++ {
			cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
			ca := s.acctLocked(peer, accountingPacket(0, cid, cid), false)
			ca.TxSizes = []int{100 + i}
			s.accountEndedLocked(ca, start, true)
		}
		if err := s.finishConnLog(start.Add(c.finish)); err != nil {
			t.Fatal(c.name, err)
		}
		if c.flush > 0 {
			s.flushConnLog(start.Add(c.flush))
		}
		lines := connLogLines(t, buf.Bytes())
		keys := map[string]bool{}
		for _, line := range lines {
			if line["reason"] != "shutdown" {
				t.Fatalf("%s: account logged again after shutdown: %v", c.name, line)
			}
			keys[line["key"].(string)] = true
		}
		if len(lines) != 2 || len(keys) != 2 {
			t.Fatalf("%s: %d lines, %d keys: %s", c.name, len(lines), len(keys), buf.Bytes())
		}
		if s.connLog.lines.Load() != 2 || s.connLog.errors.Load() != 0 || len(s.connLogPending) != 0 || closer.closed != 1 {
			t.Fatalf("%s: lines %d errors %d pending %d closed %d", c.name, s.connLog.lines.Load(), s.connLog.errors.Load(), len(s.connLogPending), closer.closed)
		}
		if len(s.conns) != 0 {
			t.Fatalf("%s: %d accounts survived expiry", c.name, len(s.conns))
		}
	}
}

func TestConnLogDisabledByDefault(t *testing.T) {
	s := &decodeConn{}
	peer := &net.UDPAddr{Port: 5555}
	for i := 0; i < 3; i++ {
		cid := binary.BigEndian.AppendUint64(nil, uint64(i+1))
		s.evictAccountLocked(s.acctLocked(peer, accountingPacket(0, cid, cid), false), i%2 == 0)
	}
	s.flushConnLog(time.Now())
	if err := s.finishConnLog(time.Now()); err != nil || s.connLogPending != nil {
		t.Fatal("conn-log queued without the flag", err)
	}
	raw, _ := json.Marshal(s.report())
	var got map[string]any
	json.Unmarshal(raw, &got)
	if _, ok := got["conn_log"]; ok {
		t.Fatalf("report has conn_log without the flag: %s", raw)
	}
}

func TestConnLogFileIsNewAndClosed(t *testing.T) {
	dir := t.TempDir()
	existing := filepath.Join(dir, "old.jsonl")
	if err := os.WriteFile(existing, []byte("keep\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := openConnLog(existing); !errors.Is(err, os.ErrExist) {
		t.Fatal("conn-log overwrote an existing file", err)
	}
	if data, _ := os.ReadFile(existing); string(data) != "keep\n" {
		t.Fatal("existing file changed")
	}
	path := filepath.Join(dir, "conns.jsonl")
	l, err := openConnLog(path)
	if err != nil {
		t.Fatal(err)
	}
	s := &decodeConn{connLog: l}
	cid := []byte{1, 2, 3, 4, 5, 6, 7, 8}
	s.acctLocked(&net.UDPAddr{Port: 5555}, accountingPacket(0, cid, []byte{11}), false)
	if err := s.finishConnLog(time.Now()); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	lines := connLogLines(t, data)
	if len(lines) != 1 || lines[0]["reason"] != "shutdown" || lines[0]["initial_dcid"] != "0102030405060708" {
		t.Fatalf("file %s", data)
	}
}

func TestConnLogConcurrentFlushAndAccounting(t *testing.T) {
	var buf bytes.Buffer
	s := &decodeConn{}
	s.connLog = newConnLogger("memory", &buf, nil)
	const workers, each = 4, 200
	var wg sync.WaitGroup
	for worker := 0; worker < workers; worker++ {
		wg.Go(func() {
			for i := 0; i < each; i++ {
				cid := binary.BigEndian.AppendUint64(nil, uint64(worker*each+i+1))
				s.mu.Lock()
				ca := s.acctLocked(&net.UDPAddr{Port: 5555}, accountingPacket(0, cid, cid), false)
				if i%3 == 0 {
					s.evictAccountLocked(ca, false)
				}
				s.mu.Unlock()
			}
		})
	}
	wg.Go(func() {
		for i := 0; i < 50; i++ {
			s.flushConnLog(time.Now())
			if _, err := json.Marshal(s.report(i%2 == 0)); err != nil {
				t.Error(err)
			}
		}
	})
	wg.Wait()
	if err := s.finishConnLog(time.Now()); err != nil {
		t.Fatal(err)
	}
	lines := connLogLines(t, buf.Bytes())
	keys := map[string]bool{}
	for _, line := range lines {
		keys[line["key"].(string)] = true
	}
	if len(lines) != workers*each || len(keys) != workers*each {
		t.Fatalf("lines %d keys %d", len(lines), len(keys))
	}
}
