package main

import (
	"net"
	"sync"
	"time"
)

type holdQUICQueuedDatagram struct {
	data []byte
	addr net.Addr
	at   time.Time
}

type holdQUICPathConn struct {
	net.PacketConn
	mu       sync.Mutex
	next     time.Time
	delay    time.Duration
	rateKbps int64
	queue    chan holdQUICQueuedDatagram
	stop     chan struct{}
	done     chan struct{}
	closed   bool
}

func newHoldQUICPathConn(conn net.PacketConn, delay time.Duration, rateKbps int64) *holdQUICPathConn {
	c := &holdQUICPathConn{PacketConn: conn, delay: delay, rateKbps: rateKbps,
		queue: make(chan holdQUICQueuedDatagram, 256), stop: make(chan struct{}), done: make(chan struct{})}
	go c.run()
	return c
}

func (c *holdQUICPathConn) run() {
	defer close(c.done)
	for {
		select {
		case <-c.stop:
			return
		case packet := <-c.queue:
			timer := time.NewTimer(time.Until(packet.at))
			select {
			case <-c.stop:
				timer.Stop()
				return
			case <-timer.C:
			}
			c.PacketConn.WriteTo(packet.data, packet.addr)
		}
	}
}

func (c *holdQUICPathConn) WriteTo(b []byte, addr net.Addr) (int, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.closed {
		return 0, net.ErrClosed
	}
	now := time.Now()
	if c.next.Before(now) {
		c.next = now
	}
	if c.rateKbps > 0 {
		numerator := int64(len(b)) * 8000000
		c.next = c.next.Add(time.Duration((numerator + c.rateKbps - 1) / c.rateKbps))
	}
	packet := holdQUICQueuedDatagram{append([]byte(nil), b...), addr, c.next.Add(c.delay)}
	select {
	case c.queue <- packet:
		return len(b), nil
	default:
		return 0, &net.OpError{Op: "write", Net: "udp", Err: holdQUICPathOverflow{}}
	}
}

type holdQUICPathOverflow struct{}

func (holdQUICPathOverflow) Error() string { return "test path queue full" }

func (c *holdQUICPathConn) Close() error {
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return net.ErrClosed
	}
	c.closed = true
	close(c.stop)
	c.mu.Unlock()
	err := c.PacketConn.Close()
	<-c.done
	return err
}

type holdQUICArrivalClock struct {
	mu       sync.Mutex
	rateKbps int64
	expected int
	arrived  int
	at       time.Time
	reading  bool
}

func (c *holdQUICArrivalClock) now() time.Time {
	c.mu.Lock()
	defer c.mu.Unlock()
	t := time.Now()
	if c.arrived == 0 {
		return t
	}
	if c.arrived < c.expected || !c.reading || t.Before(c.at) {
		return c.at
	}
	return t
}

func (c *holdQUICArrivalClock) startRead() {
	c.mu.Lock()
	c.reading = true
	c.mu.Unlock()
}

func (c *holdQUICArrivalClock) arrive(n int) {
	c.mu.Lock()
	defer c.mu.Unlock()
	t := time.Now()
	switch {
	case c.arrived == 0:
		c.at = t
	case c.arrived < c.expected:
		if c.rateKbps > 0 {
			numerator := int64(n) * 8000000
			c.at = c.at.Add(time.Duration((numerator + c.rateKbps - 1) / c.rateKbps))
		}
	case t.After(c.at):
		c.at = t
	}
	c.arrived++
	c.reading = false
}

func (c *holdQUICArrivalClock) flightIncomplete() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.arrived > 0 && c.arrived < c.expected
}

type holdQUICArrivalConn struct {
	net.PacketConn
	clock *holdQUICArrivalClock
}

func (c *holdQUICArrivalConn) ReadFrom(b []byte) (int, net.Addr, error) {
	c.clock.startRead()
	n, addr, err := c.PacketConn.ReadFrom(b)
	if err == nil {
		c.clock.arrive(n)
	}
	return n, addr, err
}

func (c *holdQUICArrivalConn) SetReadDeadline(t time.Time) error {
	if c.clock.flightIncomplete() {
		t = time.Time{}
	}
	return c.PacketConn.SetReadDeadline(t)
}
