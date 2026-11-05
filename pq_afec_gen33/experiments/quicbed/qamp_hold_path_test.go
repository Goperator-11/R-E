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
