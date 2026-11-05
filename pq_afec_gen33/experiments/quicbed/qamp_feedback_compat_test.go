package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"reflect"
	"testing"
)

func frozenV2ParseFeedback(d []byte) *fbRec {
	h := parseLongHdr(d)
	if !h.ok || h.typ != 0 {
		return nil
	}
	i := h.bodyOff
	if i >= len(d) || d[i] != 0x00 {
		return nil
	}
	i++
	if i+2 > len(d) || d[i]&0xC0 != 0x40 {
		return nil
	}
	blen := int(d[i]&0x3F)<<8 | int(d[i+1])
	i += 2
	if i+blen > len(d) || blen < fecMagicLen+8 {
		return nil
	}
	b := d[i : i+blen]
	if string(b[:fecMagicLen]) != string(fbMagic) || b[4] != 2 {
		return nil
	}
	nc := int(b[11] & 0x7f)
	if nc > fbCRCCap || blen != 12+4*nc {
		return nil
	}
	r := &fbRec{
		flight: binary.BigEndian.Uint16(b[5:7]),
		k:      b[7], rxOrig: b[8], rxPar: b[9], recov: b[10],
		truncated: b[11]&0x80 != 0,
	}
	for x := 0; x < nc; x++ {
		j := 12 + 4*x
		r.crcs = append(r.crcs, binary.BigEndian.Uint32(b[j:j+4]))
	}
	return r
}

func feedbackCompatReply(t *testing.T, version int, crcs, recovered []uint32) []byte {
	t.Helper()
	s := &decodeConn{feedback: true, feedbackVersion: version}
	cid := []byte{1, 2, 3, 4, 5, 6, 7, 8}
	ca := s.acctLocked(nil, accountingPacket(0, cid, []byte{11}), false)
	if ca == nil {
		t.Fatal("account missing")
	}
	ca.RxOrigN, ca.RxParityN, ca.RecovN = 2, 1, len(recovered)
	ca.RxCRC = append([]uint32(nil), crcs...)
	ca.RxCRCTruncated = len(crcs) > fbCRCCap
	if ca.RxCRCTruncated {
		ca.RxCRC = ca.RxCRC[:fbCRCCap]
	}
	ca.RecoveredCRC = append([]uint32(nil), recovered...)
	out := s.feedbackLocked(accountingPacket(2, cid, []byte{11}), ca)
	if len(out) == 0 || s.stats.FbSentN != 1 {
		t.Fatalf("version %d: no reply", version)
	}
	return out
}

func TestFeedbackFrozenParserReadsVersionTwo(t *testing.T) {
	legacy := append([]byte{0xC3, 0, 0, 0, 1, 1, 9, 1, 8, 0, 0x40, 16}, fbMagic...)
	legacy = append(legacy, 2, 0, 0, 3, 2, 1, 1, 1)
	legacy = binary.BigEndian.AppendUint32(legacy, 77)
	r := frozenV2ParseFeedback(legacy)
	if r == nil || !reflect.DeepEqual(r.crcs, []uint32{77}) || r.k != 3 || r.rxOrig != 2 || r.rxPar != 1 || r.recov != 1 {
		t.Fatalf("frozen copy rejected the gen31 wire form: %+v", r)
	}
	if x := parseFeedback(legacy); x == nil || x.version != 2 || !reflect.DeepEqual(x.crcs, r.crcs) || len(x.recovered) != 0 {
		t.Fatalf("gen33 client lost version 2: %+v", x)
	}
}

func TestFeedbackVersionTwoIsReadableByFrozenClients(t *testing.T) {
	crcs := []uint32{10, 11, 12}
	recovered := []uint32{13}
	v3 := feedbackCompatReply(t, 0, crcs, recovered)
	if frozenV2ParseFeedback(v3) != nil {
		t.Fatal("default reply should stay version 3 and unreadable by frozen clients")
	}
	explicit3 := feedbackCompatReply(t, fbVer, crcs, recovered)
	if !bytes.Equal(v3, explicit3) {
		t.Fatal("explicit version 3 differs from the default")
	}
	v2 := feedbackCompatReply(t, fbVerFrozen, crcs, recovered)
	old := frozenV2ParseFeedback(v2)
	if old == nil {
		t.Fatal("frozen gen-2/v3.1/v3.2 parser rejected the version 2 reply; it would count it as server bytes")
	}
	cur3, cur2 := parseFeedback(v3), parseFeedback(v2)
	if cur3 == nil || cur2 == nil || cur3.version != fbVer || cur2.version != fbVerFrozen {
		t.Fatalf("gen33 parser %+v %+v", cur3, cur2)
	}
	if !reflect.DeepEqual(old.crcs, crcs) || !reflect.DeepEqual(cur2.crcs, crcs) || !reflect.DeepEqual(cur3.crcs, crcs) {
		t.Fatal("physical CRC list changed between versions")
	}
	if old.k != cur3.k || old.rxOrig != cur3.rxOrig || old.rxPar != cur3.rxPar || old.recov != cur3.recov || old.truncated != cur3.truncated {
		t.Fatalf("counts differ: frozen %+v current %+v", old, cur3)
	}
	if len(cur2.recovered) != 0 || !reflect.DeepEqual(cur3.recovered, recovered) {
		t.Fatal("recovered list must exist only in version 3")
	}
	if len(v3)-len(v2) != 1+4*len(recovered) {
		t.Fatalf("version 2 is not version 3 minus the recovered section: %d %d", len(v2), len(v3))
	}
}

func TestFeedbackVersionTwoTruncationForFrozenClients(t *testing.T) {
	crcs := make([]uint32, fbCRCCap+1)
	for i := range crcs {
		crcs[i] = uint32(i + 1)
	}
	old := frozenV2ParseFeedback(feedbackCompatReply(t, fbVerFrozen, crcs, nil))
	if old == nil || !old.truncated || len(old.crcs) != fbCRCCap {
		t.Fatalf("frozen client cannot see truncation: %+v", old)
	}
}

func TestFeedbackVersionKeepsGen33Arrivals(t *testing.T) {
	orig := []uint32{10, 11}
	par := []uint32{12}
	evidence := func(reply []byte) (p3Arrivals, c1Observation) {
		c := &fecConn{ffOrigCRC: orig, ffParCRC: par, fbCount: 1, fbLast: parseFeedback(reply)}
		return c.arrivalEvidence(true)
	}
	a3, d3 := evidence(feedbackCompatReply(t, fbVer, []uint32{11, 12}, []uint32{10}))
	a2, d2 := evidence(feedbackCompatReply(t, fbVerFrozen, []uint32{11, 12}, []uint32{10}))
	if !reflect.DeepEqual(a3, a2) || a2.Src != "c1" || a2.Sent != 3 || a2.Lost != 1 || a2.Trunc {
		t.Fatalf("arrivals differ by reply version: %+v %+v", a3, a2)
	}
	if d3.Version != fbVer || d2.Version != fbVerFrozen || d3.RecoveredOriginal != 1 || d2.RecoveredOriginal != 0 || d2.Reason != "complete_crc_lists" {
		t.Fatalf("c1 rows %+v %+v", d3, d2)
	}
}

func TestFeedbackVersionValidationAndReport(t *testing.T) {
	for _, v := range []int{fbVerFrozen, fbVer} {
		if err := checkFeedbackVersion(v); err != nil {
			t.Fatal(v, err)
		}
	}
	for _, v := range []int{0, 1, 4, 255} {
		if checkFeedbackVersion(v) == nil {
			t.Fatal("accepted feedback version", v)
		}
	}
	for _, v := range []struct {
		version int
		want    float64
	}{{0, fbVer}, {fbVer, fbVer}, {fbVerFrozen, fbVerFrozen}} {
		raw, err := json.Marshal((&decodeConn{feedbackVersion: v.version}).report(false))
		if err != nil {
			t.Fatal(err)
		}
		var got map[string]any
		if err := json.Unmarshal(raw, &got); err != nil || got["feedback_version"] != v.want || got["profile"] != "default" {
			t.Fatalf("report %s", raw)
		}
	}
}
