package main

import (
	"bytes"
	"container/list"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/quic-go/quic-go"
	"github.com/quic-go/quic-go/qlogwriter"
)

const accountRetention = 10 * time.Second

type accountAlias struct {
	client bool
	cid    string
}

type accountLife struct {
	key      string
	lru      *list.Element
	expiry   *list.Element
	deadline time.Time
	aliases  []accountAlias
	evicted  bool
}

type accountBook struct {
	lru    list.List
	expiry list.List
	refs   map[accountAlias]int
}

func (s *decodeConn) accountBookLocked() *accountBook {
	if s.accounts == nil {
		s.accounts = &accountBook{refs: map[accountAlias]int{}}
	}
	return s.accounts
}

func (s *decodeConn) expireAccountsLocked(now time.Time) {
	b := s.accountBookLocked()
	for e := b.expiry.Front(); e != nil; e = b.expiry.Front() {
		ca := e.Value.(*connAcct)
		if now.Before(ca.life.deadline) {
			break
		}
		s.evictAccountLocked(ca, false)
	}
}

func (s *decodeConn) evictAccountLocked(ca *connAcct, capacity bool) {
	if ca == nil || ca.life == nil || ca.life.evicted {
		return
	}
	if capacity {
		s.queueConnLogLocked(ca, "lru")
	} else {
		s.queueConnLogLocked(ca, "expired")
	}
	b := s.accountBookLocked()
	life := ca.life
	life.evicted = true
	delete(s.conns, life.key)
	if life.lru != nil {
		b.lru.Remove(life.lru)
		life.lru = nil
	}
	if life.expiry != nil {
		b.expiry.Remove(life.expiry)
		life.expiry = nil
	}
	for _, alias := range life.aliases {
		index := s.serverCIDs
		if alias.client {
			index = s.clientCIDs
		}
		b.refs[alias]--
		if b.refs[alias] == 0 {
			delete(b.refs, alias)
			delete(index, alias.cid)
		} else if index[alias.cid] == ca {
			index[alias.cid] = nil
		}
	}
	life.aliases = nil
	if capacity {
		s.stats.ConnAcctEvictedLRU++
		if ca.HandshakeCompleteNS == 0 && ca.ClosedNS == 0 {
			s.stats.ConnAcctDropped++
		}
	} else {
		s.stats.ConnAcctExpired++
	}
}

func (s *decodeConn) registerAccountLocked(key string, ca *connAcct) {
	b := s.accountBookLocked()
	ca.life = &accountLife{key: key}
	ca.life.lru = b.lru.PushBack(ca)
}

func (s *decodeConn) accountEndedLocked(ca *connAcct, now time.Time, complete bool) {
	if ca == nil || ca.life == nil || ca.life.evicted {
		return
	}
	if complete && ca.HandshakeCompleteNS == 0 {
		ca.HandshakeCompleteNS = now.UnixNano()
		s.stats.ConnAcctCompleted++
	}
	if !complete && ca.ClosedNS == 0 {
		ca.ClosedNS = now.UnixNano()
	}
	if ca.life.expiry == nil {
		ca.life.deadline = now.Add(accountRetention)
		ca.life.expiry = s.accountBookLocked().expiry.PushBack(ca)
	}
}

func (ca *connAcct) clone() *connAcct {
	cp := *ca
	cp.life = nil
	cp.TxRxTimeline = append([]int64(nil), ca.TxRxTimeline...)
	cp.TxSizes = append([]int(nil), ca.TxSizes...)
	cp.TxNs = append([]int64(nil), ca.TxNs...)
	cp.RxCRC = append([]uint32(nil), ca.RxCRC...)
	cp.RecoveredCRC = append([]uint32(nil), ca.RecoveredCRC...)
	return &cp
}

type connLogEntry struct {
	Key      string `json:"key"`
	Reason   string `json:"reason"`
	LoggedNS int64  `json:"logged_ns"`
	*connAcct
}

type connLogger struct {
	mu     sync.Mutex
	path   string
	out    io.Writer
	closer io.Closer
	closed bool
	lines  atomic.Int64
	errors atomic.Int64
}

func newConnLogger(path string, out io.Writer, closer io.Closer) *connLogger {
	return &connLogger{path: path, out: out, closer: closer}
}

func openConnLog(path string) (*connLogger, error) {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
	if err != nil {
		return nil, err
	}
	return newConnLogger(path, f, f), nil
}

func (s *decodeConn) queueConnLogLocked(ca *connAcct, reason string) {
	if s.connLog == nil || ca == nil || ca.logged {
		return
	}
	ca.logged = true
	key := ""
	if ca.life != nil {
		key = ca.life.key
	}
	s.connLogPending = append(s.connLogPending, connLogEntry{Key: key, Reason: reason, LoggedNS: time.Now().UnixNano(), connAcct: ca.clone()})
}

func (s *decodeConn) flushConnLog(now time.Time) {
	l := s.connLog
	if l == nil {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	s.mu.Lock()
	if !s.closed {
		s.expireAccountsLocked(now)
	}
	batch := s.connLogPending
	s.connLogPending = nil
	s.mu.Unlock()
	if l.closed {
		l.errors.Add(int64(len(batch)))
		return
	}
	enc := json.NewEncoder(l.out)
	for i := range batch {
		if err := enc.Encode(&batch[i]); err != nil {
			l.errors.Add(1)
			continue
		}
		l.lines.Add(1)
	}
}

func (s *decodeConn) finishConnLog(now time.Time) error {
	l := s.connLog
	if l == nil {
		return nil
	}
	s.mu.Lock()
	b := s.accountBookLocked()
	for e := b.lru.Front(); e != nil; e = e.Next() {
		s.queueConnLogLocked(e.Value.(*connAcct), "shutdown")
	}
	s.mu.Unlock()
	s.flushConnLog(now)
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.closed {
		return nil
	}
	l.closed = true
	if l.closer != nil {
		return l.closer.Close()
	}
	return nil
}

func (s *decodeConn) connLogReportLocked() map[string]any {
	l := s.connLog
	if l == nil {
		return nil
	}
	return map[string]any{"path": l.path, "lines": l.lines.Load(), "errors": l.errors.Load(), "pending": len(s.connLogPending), "retention_ns": int64(accountRetention)}
}

type accountContextKey struct{}
type accountTrace struct {
	addressObserved bool
	addressVerified bool
	account         *connAcct
}

func (s *decodeConn) accountContext(ctx context.Context, info *quic.ClientInfo) (context.Context, error) {
	trace := &accountTrace{}
	if info != nil {
		trace.addressObserved, trace.addressVerified = true, info.AddrVerified
		s.mu.Lock()
		s.stats.TokenContexts++
		if info.AddrVerified {
			s.stats.AddressVerifiedContexts++
		}
		s.mu.Unlock()
	}
	return context.WithValue(ctx, accountContextKey{}, trace), nil
}

func (s *decodeConn) accountTracer(ctx context.Context, _ bool, id quic.ConnectionID) qlogwriter.Trace {
	trace, ok := ctx.Value(accountContextKey{}).(*accountTrace)
	if !ok {
		return nil
	}
	s.mu.Lock()
	trace.account = s.serverCIDs[string(id.Bytes())]
	if trace.account == nil {
		s.stats.ConnAcctTraceUnmapped++
	} else {
		trace.account.AddressValidationObserved = trace.addressObserved
		trace.account.AddressVerifiedAtStart = trace.addressVerified
	}
	s.mu.Unlock()
	context.AfterFunc(ctx, func() {
		s.mu.Lock()
		s.accountEndedLocked(trace.account, time.Now(), false)
		s.mu.Unlock()
	})
	return nil
}

func (s *decodeConn) accountAccepted(ctx context.Context) {
	trace, ok := ctx.Value(accountContextKey{}).(*accountTrace)
	if !ok {
		return
	}
	s.mu.Lock()
	s.accountEndedLocked(trace.account, time.Now(), true)
	s.mu.Unlock()
}

func samePeer(a, b net.Addr) bool {
	x, xok := a.(*net.UDPAddr)
	y, yok := b.(*net.UDPAddr)
	return xok && yok && x != nil && y != nil && x.Port == y.Port && x.Zone == y.Zone && x.IP.Equal(y.IP)
}

func (c *fecConn) acceptServerLocked(data []byte, addr net.Addr) bool {
	if !samePeer(addr, c.identityPeer) {
		c.stats.RxRejectedPeer++
		return false
	}
	if len(c.ownCID) == 0 || len(data) < 2 {
		c.stats.RxRejectedCID++
		return false
	}
	h := parseLongHdr(data)
	valid := h.ok && h.version == 1 && (bytes.Equal(h.dcid, c.ownCID) || c.ownCIDs[string(h.dcid)])
	if data[0]&0x80 == 0 {
		valid = data[0]&0x40 != 0 && len(data) > len(c.ownCID) && (bytes.Equal(data[1:1+len(c.ownCID)], c.ownCID) || c.ownCIDs[string(data[1:1+len(c.ownCID)])])
	}
	if !valid {
		c.stats.RxRejectedCID++
		return false
	}
	return true
}

const clientCIDCap = 64

type clientCIDGenerator struct {
	client *fecConn
}

func (g clientCIDGenerator) ConnectionIDLen() int { return serverConnIDLength }

func (g clientCIDGenerator) GenerateConnectionID() (quic.ConnectionID, error) {
	c := g.client
	c.mu.Lock()
	defer c.mu.Unlock()
	if len(c.ownCIDs) >= clientCIDCap {
		return quic.ConnectionID{}, errors.New("client connection ID storage limit")
	}
	if c.ownCIDs == nil {
		c.ownCIDs = map[string]bool{}
	}
	for attempt := 0; attempt < 4; attempt++ {
		id := make([]byte, serverConnIDLength)
		if _, err := rand.Read(id); err != nil {
			return quic.ConnectionID{}, err
		}
		if !c.ownCIDs[string(id)] {
			c.ownCIDs[string(id)] = true
			return quic.ConnectionIDFromBytes(id), nil
		}
	}
	return quic.ConnectionID{}, errors.New("client connection ID collision")
}

func (c *fecConn) checkFirstFlightLocked(data []byte, addr net.Addr, h longHdr) error {
	if h.ok && h.typ == 0 && c.identityPeer == nil {
		if a, ok := addr.(*net.UDPAddr); ok && a != nil {
			copyAddr := *a
			copyAddr.IP = append(net.IP(nil), a.IP...)
			c.identityPeer = &copyAddr
		}
		c.ownCID = append([]byte(nil), h.scid...)
	}
	if !c.serverSeen && ((h.ok && h.typ != 0) || (h.ok && hasHandshake(data))) {
		c.stats.FirstFlightNonInitialLong++
		return errors.New("non-Initial long header before server response")
	}
	return nil
}
