package main

import (
	"encoding/binary"
	"fmt"
	"io"
	"net"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/net/ipv4"
	"golang.org/x/net/ipv6"
	"golang.org/x/sys/unix"
)

type packetMeta struct {
	oob   []byte
	flags int
}

func firstPacketMeta(metas []packetMeta) packetMeta {
	if len(metas) == 0 {
		return packetMeta{}
	}
	return metas[0]
}

func (m packetMeta) truncated(yes bool) packetMeta {
	if yes {
		m.flags |= unix.MSG_TRUNC
	}
	return m
}

func socketControl(level, kind int32, body []byte) []byte {
	b := make([]byte, unix.CmsgSpace(len(body)))
	h := (*unix.Cmsghdr)(unsafe.Pointer(&b[0]))
	h.Level, h.Type = level, kind
	h.SetLen(unix.CmsgLen(len(body)))
	copy(b[unix.CmsgLen(0):], body)
	return b
}

func (m packetMeta) recovery() packetMeta {
	var out packetMeta
	msgs, err := unix.ParseSocketControlMessage(m.oob)
	if err != nil {
		return out
	}
	for _, msg := range msgs {
		if (msg.Header.Level == unix.IPPROTO_IP && msg.Header.Type == unix.IP_PKTINFO && len(msg.Data) == 12) || (msg.Header.Level == unix.IPPROTO_IPV6 && msg.Header.Type == unix.IPV6_PKTINFO && len(msg.Data) == 20) {
			out.oob = append(out.oob, socketControl(msg.Header.Level, msg.Header.Type, msg.Data)...)
		}
	}
	return out
}

func (m packetMeta) reply() []byte {
	msgs, err := unix.ParseSocketControlMessage(m.oob)
	if err != nil {
		return nil
	}
	var out []byte
	for _, msg := range msgs {
		if msg.Header.Level == unix.IPPROTO_IP && msg.Header.Type == unix.IP_PKTINFO && len(msg.Data) == 12 {
			cm := ipv4.ControlMessage{Src: net.IP(msg.Data[8:12]), IfIndex: int(binary.NativeEndian.Uint32(msg.Data))}
			out = append(out, cm.Marshal()...)
		}
		if msg.Header.Level == unix.IPPROTO_IPV6 && msg.Header.Type == unix.IPV6_PKTINFO && len(msg.Data) == 20 {
			cm := ipv6.ControlMessage{Src: net.IP(msg.Data[:16]), IfIndex: int(binary.NativeEndian.Uint32(msg.Data[16:]))}
			out = append(out, cm.Marshal()...)
		}
	}
	return out
}

type udpMessageConn interface {
	net.PacketConn
	SyscallConn() (syscall.RawConn, error)
	SetReadBuffer(int) error
	SetWriteBuffer(int) error
	ReadMsgUDP([]byte, []byte) (int, int, int, *net.UDPAddr, error)
	WriteMsgUDP([]byte, []byte, *net.UDPAddr) (int, int, error)
}

type udpDecodeConn struct{ *decodeConn }

func newUDPDecodeConn(s *decodeConn, wire udpMessageConn) *udpDecodeConn {
	s.udp = wire
	return &udpDecodeConn{s}
}

func (c *udpDecodeConn) SyscallConn() (syscall.RawConn, error) { return c.udp.SyscallConn() }
func (c *udpDecodeConn) SetReadBuffer(n int) error             { return c.udp.SetReadBuffer(n) }
func (c *udpDecodeConn) SetWriteBuffer(n int) error            { return c.udp.SetWriteBuffer(n) }

func (s *decodeConn) readWire(b []byte) (int, net.Addr, error) {
	s.readMeta = packetMeta{}
	if s.udp == nil {
		return s.PacketConn.ReadFrom(b)
	}
	var oob [128]byte
	n, nn, flags, addr, err := s.udp.ReadMsgUDP(b, oob[:])
	if nn < 0 || nn > len(oob) || n < 0 || n > len(b) {
		return 0, nil, fmt.Errorf("invalid UDP read lengths %d/%d", n, nn)
	}
	s.readMeta = packetMeta{append([]byte(nil), oob[:nn]...), flags}
	if err == nil {
		s.mu.Lock()
		s.stats.UDPReadMsg++
		s.mu.Unlock()
	}
	return n, addr, err
}

func (c *udpDecodeConn) ReadMsgUDP(b, oob []byte) (int, int, int, *net.UDPAddr, error) {
	c.readMu.Lock()
	defer c.readMu.Unlock()
	n, addr, err := c.readFrom(b)
	m := c.readMeta
	nn := copy(oob, m.oob)
	flags := m.flags
	if nn < len(m.oob) {
		flags |= unix.MSG_CTRUNC
	}
	ua, ok := addr.(*net.UDPAddr)
	if err == nil && !ok {
		err = fmt.Errorf("decoder returned non-UDP peer %T", addr)
	}
	return n, nn, flags, ua, err
}

func (c *udpDecodeConn) ReadBatch(ms []ipv4.Message, flags int) (int, error) {
	if flags != 0 {
		return 0, syscall.EINVAL
	}
	if len(ms) == 0 {
		return 0, nil
	}
	m := &ms[0]
	var data []byte
	if len(m.Buffers) == 1 {
		data = m.Buffers[0]
	} else {
		total := 0
		for _, b := range m.Buffers {
			if len(b) > 65535-total {
				return 0, syscall.EINVAL
			}
			total += len(b)
		}
		if total == 0 {
			return 0, syscall.EINVAL
		}
		data = make([]byte, total)
	}
	n, nn, f, addr, err := c.ReadMsgUDP(data, m.OOB)
	m.N, m.NN, m.Flags, m.Addr = n, nn, f, addr
	if err != nil {
		return 0, err
	}
	if len(m.Buffers) != 1 {
		rest := data[:n]
		for _, b := range m.Buffers {
			rest = rest[copy(b, rest):]
		}
	}
	c.mu.Lock()
	c.stats.UDPReadBatch++
	c.mu.Unlock()
	return 1, nil
}

func udpSegmentSize(oob []byte) (int, error) {
	msgs, err := unix.ParseSocketControlMessage(oob)
	if err != nil {
		return 0, err
	}
	size := 0
	for _, msg := range msgs {
		if msg.Header.Level != unix.IPPROTO_UDP || msg.Header.Type != unix.UDP_SEGMENT {
			continue
		}
		if size != 0 || len(msg.Data) != 2 {
			return 0, syscall.EINVAL
		}
		size = int(binary.NativeEndian.Uint16(msg.Data))
		if size == 0 {
			return 0, syscall.EINVAL
		}
	}
	return size, nil
}

func (c *udpDecodeConn) WriteMsgUDP(b, oob []byte, addr *net.UDPAddr) (int, int, error) {
	size, err := udpSegmentSize(oob)
	if err != nil {
		return 0, 0, err
	}
	nn := 0
	n, err := c.serverWrite(b, addr, size, func() (int, error) {
		n, count, err := c.udp.WriteMsgUDP(b, oob, addr)
		nn = count
		return n, err
	})
	c.mu.Lock()
	if err == nil {
		c.stats.UDPWriteMsg++
	}
	c.mu.Unlock()
	return n, nn, err
}

func (s *decodeConn) serverWrite(b []byte, addr net.Addr, segmentSize int, send func() (int, error)) (int, error) {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	step := segmentSize
	if step == 0 {
		step = len(b)
	}
	if step <= 0 {
		return send()
	}
	s.mu.Lock()
	previous := map[*connAcct]connAcct{}
	unmapped := s.stats.ConnAcctUnmappedTX
	segments := 0
	for start := 0; start < len(b); start += step {
		end := min(start+step, len(b))
		n := end - start
		segments++
		ca := s.acctLocked(addr, b[start:end], true)
		if ca == nil {
			s.stats.ConnAcctUnmappedTX++
			continue
		}
		if _, ok := previous[ca]; !ok {
			previous[ca] = *ca
		}
		now := time.Now().UnixNano()
		if ca.TxDgrams == 0 {
			ca.FirstTxNs = now
			ca.BeffStack, ca.BeffPhys, ca.BeffOrig, ca.BeffParity, ca.BeffCredit = ca.Stack, ca.RxBytes, ca.RxOrig, ca.RxParity, ca.CreditN
		}
		if len(ca.TxRxTimeline) < connTimelineCap {
			ca.TxRxTimeline = append(ca.TxRxTimeline, ca.Stack)
			ca.TxSizes = append(ca.TxSizes, n)
			ca.TxNs = append(ca.TxNs, now)
		}
		ca.TxDgrams++
		ca.TxBytes += int64(n)
	}
	s.mu.Unlock()
	n, err := send()
	if err == nil && n != len(b) {
		err = io.ErrShortWrite
	}
	s.mu.Lock()
	if err != nil {
		s.stats.UDPWriteErrors++
		s.stats.ConnAcctUnmappedTX = unmapped
		for ca, old := range previous {
			ca.FirstTxNs = old.FirstTxNs
			ca.BeffStack, ca.BeffPhys, ca.BeffOrig, ca.BeffParity, ca.BeffCredit = old.BeffStack, old.BeffPhys, old.BeffOrig, old.BeffParity, old.BeffCredit
			ca.TxDgrams, ca.TxBytes = old.TxDgrams, old.TxBytes
			ca.TxRxTimeline, ca.TxSizes, ca.TxNs = old.TxRxTimeline, old.TxSizes, old.TxNs
		}
	} else if segmentSize > 0 {
		s.stats.UDPGSOCalls++
		s.stats.UDPGSOSegments += segments
	}
	s.mu.Unlock()
	if err == nil {
		for start := 0; start < len(b); start += step {
			s.countTx(min(step, len(b)-start))
		}
	}
	return n, err
}

func (s *decodeConn) udpPath() string {
	if s.udp == nil {
		return "basic"
	}
	return "oob_readmsg_batch1"
}
