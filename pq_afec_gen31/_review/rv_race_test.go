package main

import (
	"net"
	"sync"
	"testing"
	"time"
)

type rvLockedConn struct {
	net.PacketConn
	mu      sync.Mutex
	written [][]byte
	reads   [][]byte
	delay   time.Duration
}

func (c *rvLockedConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.mu.Lock()
	c.written = append(c.written, append([]byte(nil), b...))
	c.mu.Unlock()
	return len(b), nil
}

func (c *rvLockedConn) ReadFrom(b []byte) (int, net.Addr, error) {
	time.Sleep(c.delay)
	c.mu.Lock()
	defer c.mu.Unlock()
	if len(c.reads) == 0 {
		return 0, nil, net.ErrClosed
	}
	n := copy(b, c.reads[0])
	c.reads = c.reads[1:]
	return n, &net.UDPAddr{IP: net.IPv4(10, 9, 0, 1), Port: 1}, nil
}

func TestRvConcurrentWriteReadTimer(t *testing.T) {
	gfInit()
	addr := &net.UDPAddr{IP: net.IPv4(10, 9, 0, 2), Port: 44433}
	for _, layout := range []string{"v2", "v3"} {
		for rep := 0; rep < 20; rep++ {
			lead := -1
			if layout == "v3" {
				lead = 2
			}
			wc := &rvLockedConn{reads: [][]byte{rvInitial(rvSCID, rvDCID, 1252, 1), rvInitial(rvSCID, rvDCID, 1252, 2)},
				delay: 2 * time.Millisecond}
			fc := &fecConn{mode: "fec", m: 4, layout: layout, lead: lead, dropParity: -1, corruptParity: -1,
				parityDelay: 100 * time.Microsecond}
			fc.PacketConn = wc
			var wg sync.WaitGroup
			wg.Add(2)
			go func() {
				defer wg.Done()
				buf := make([]byte, 2000)
				for {
					if _, _, err := fc.ReadFrom(buf); err != nil {
						return
					}
				}
			}()
			go func() {
				defer wg.Done()
				for i := 0; i < 40; i++ {
					fc.WriteTo(rvInitial(rvDCID, rvSCID, 1200, byte(i)), addr)
					if i%3 == 2 {
						fc.WriteTo([]byte{0x41, 1, 2, 3}, addr)
					}
					time.Sleep(time.Duration(50+rep*10) * time.Microsecond)
					_ = fc.snapshot()
				}
			}()
			wg.Wait()
			time.Sleep(time.Millisecond)
			st := fc.snapshot()
			if st.Flights == 0 {
				t.Fatalf("%s: no flights", layout)
			}
		}
	}
}
