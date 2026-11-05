# -*- coding: utf-8 -*-
"""qamp.go 에 결정적 소거 주입 플래그를 추가한다. p3 가 끝난 뒤 적용한다.

왜 필요한가
-----------
지금까지의 손실 실험은 netem 무작위 손실이다. 통계적으로 "꼬리가 줄었다"는
보이지만, **그 개선이 정말 복구 때문인지**는 못 박지 못한다. 손실률이 낮으면
FEC 팔이 우연히 운이 좋았을 수도 있고, 우리가 모르는 다른 경로로 이득을
봤을 수도 있다. 1차 연구에서 "복구했다고 세었는데 응용까지 도달하지 않은"
결함을 두 번 겪은 것이 정확히 이런 종류다.

그래서 **어느 데이터그램을 없앨지 우리가 정한다.**

  -drop-initial N   첫 비행의 N 번째 원본을 보내지 않는다 (패리티 계산에는 포함)
  -drop-parity J    J 번째 패리티를 보내지 않는다
  -corrupt-parity J J 번째 패리티의 한 바이트를 뒤집어 보낸다

이 셋이 있으면 다음이 가능해진다.

  기준선(off) + 원본 1개 소거   -> 반드시 PTO 를 맞아야 한다 (기준선이 아프다)
  FEC(m=1)  + 원본 1개 소거   -> 반드시 복구되어 1-RTT 여야 한다
  FEC(m=1)  + 패리티 소거     -> 기준선과 같아야 한다 (다른 경로로 몰래 이득 X)
  FEC(m=1)  + 패리티 손상     -> CRC 가 걸러 내고 잘못된 복구를 안 넘겨야 한다
  FEC(m=1)  + 원본 2개 소거   -> 복구 불가여야 한다 (능력을 과장하지 않는다)

소거를 송신측에서 만드는 것과 링크에서 잃는 것은 서버 입장에서 구별되지
않는다 - 어차피 도착하지 않는다. 대신 **어느 것이 사라졌는지 우리가 안다**.
"""
import io
import os
import sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quicbed", "qamp.go")


def historical_patch():
    s = io.open(P, encoding="utf-8").read()
    n = 0

    # 구조체 필드
    old = """	// dumpPath: 첫 비행의 원본 데이터그램을 그대로 떨궈 둔다."""
    new = """	// 결정적 소거 주입 (검증 전용). -1 이면 아무것도 안 한다.
	// 첫 비행에만 적용한다 - 뒤따르는 ACK 비행까지 건드리면 무엇 때문에
	// 무엇이 벌어졌는지 알 수 없게 된다.
	dropInitial   int
	dropParity    int
	corruptParity int

	// dumpPath: 첫 비행의 원본 데이터그램을 그대로 떨궈 둔다."""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # 통계
    old = """	ParityFail   int            `json:"parity_fail"`"""
    new = """	ParityFail   int            `json:"parity_fail"`
	DroppedOrig  int            `json:"dropped_originals"`
	DroppedPar   int            `json:"dropped_parities"`
	CorruptPar   int            `json:"corrupted_parities"`"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # 첫 비행인지 기억
    old = """	c.stats.Flights++
	if c.stats.FlightSizes == nil {"""
    new = """	c.stats.Flights++
	isFirstFlight := c.stats.Flights == 1
	if c.stats.FlightSizes == nil {"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # 원본 전송에 소거 주입
    old = """	if sendMode == "buf" {
		// 대조군 'buf': 패리티 없이 버퍼링만 한다. 버퍼링 자체의 비용을
		// FEC 의 효과에서 떼어내기 위한 팔이다.
		for _, d := range fl {
			send(d)
		}
		return
	}"""
    new = """	// 결정적 소거: 이 원본을 보내지 않는다. 패리티 계산에는 이미 들어갔다.
	sendOrig := func(i int, d []byte) {
		if isFirstFlight && c.dropInitial == i {
			c.mu.Lock()
			c.stats.DroppedOrig++
			c.mu.Unlock()
			return
		}
		send(d)
	}

	if sendMode == "buf" {
		// 대조군 'buf': 패리티 없이 버퍼링만 한다. 버퍼링 자체의 비용을
		// FEC 의 효과에서 떼어내기 위한 팔이다.
		for i, d := range fl {
			sendOrig(i, d)
		}
		return
	}"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # off 모드는 WriteTo 에서 이미 보냈으므로 그쪽에도 소거를 건다
    old = """	var immediate int
	var ierr error
	if c.mode == "off" {
		immediate, ierr = c.PacketConn.WriteTo(b, addr)
		if ierr != nil {
			return immediate, ierr
		}
		c.countTx(len(b))
	}"""
    new = """	var immediate int
	var ierr error
	if c.mode == "off" {
		// off 모드도 결정적 소거를 받는다. 기준선이 실제로 아프다는 것을
		// 보여야 FEC 팔의 개선이 의미를 갖는다.
		c.mu.Lock()
		idx := len(c.flight)
		first := c.stats.Flights == 0
		c.mu.Unlock()
		if first && c.dropInitial == idx {
			c.mu.Lock()
			c.stats.DroppedOrig++
			c.mu.Unlock()
			immediate = len(b)
		} else {
			immediate, ierr = c.PacketConn.WriteTo(b, addr)
			if ierr != nil {
				return immediate, ierr
			}
			c.countTx(len(b))
		}
	}"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # 원본 루프 두 곳
    old = """	if k > 0 {
		send(fl[0])
	}
	if c.m >= 2 {
		emit(mk(0, pars[0]))
	}
	for i := 1; i < k; i++ {
		send(fl[i])
	}"""
    new = """	if k > 0 {
		sendOrig(0, fl[0])
	}
	if c.m >= 2 {
		emit(0, mk(0, pars[0]))
	}
	for i := 1; i < k; i++ {
		sendOrig(i, fl[i])
	}"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1
    else:
        old2 = """	if c.m >= 2 {
		emit(mk(0, pars[0]))
	}
	for i := 0; i < k; i++ {
		send(fl[i])
	}"""
        new2 = """	if c.m >= 2 {
		emit(0, mk(0, pars[0]))
	}
	for i := 0; i < k; i++ {
		sendOrig(i, fl[i])
	}"""
        if old2 in s:
            s = s.replace(old2, new2, 1)
            n += 1

    # emit 에 인덱스와 소거/손상 주입
    old = """	emit := func(pkt []byte) {
		err := send(pkt)"""
    new = """	emit := func(j int, pkt []byte) {
		if isFirstFlight && c.dropParity == j {
			c.mu.Lock()
			c.stats.DroppedPar++
			c.mu.Unlock()
			return
		}
		if isFirstFlight && c.corruptParity == j && len(pkt) > 8 {
			// 심볼 한가운데 한 바이트를 뒤집는다. CRC 가 걸러 내야 한다.
			pkt = append([]byte(nil), pkt...)
			pkt[len(pkt)/2] ^= 0xFF
			c.mu.Lock()
			c.stats.CorruptPar++
			c.mu.Unlock()
		}
		err := send(pkt)"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    old = """		emit(mk(j, pars[j]))"""
    new = """		emit(j, mk(j, pars[j]))"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # 생성자 + 플래그
    old = """			expectK:     expectK,"""
    new = """			expectK:     expectK,
			dropInitial: dropInitial, dropParity: dropParity,
			corruptParity: corruptParity,"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    old = """	mode string, m int, ips int, parityDelayUs int, expectK int,
	statsPath string, dumpPath string) {"""
    new = """	mode string, m int, ips int, parityDelayUs int, expectK int,
	statsPath string, dumpPath string,
	dropInitial, dropParity, corruptParity int) {"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    old = """	dump := flag.String("dump-flight", "", "첫 비행 원본 데이터그램을 이 파일에 기록")"""
    new = """	dump := flag.String("dump-flight", "", "첫 비행 원본 데이터그램을 이 파일에 기록")
	dropI := flag.Int("drop-initial", -1,
		"검증용: 첫 비행의 N 번째 원본을 보내지 않는다 (-1 = 안 함)")
	dropP := flag.Int("drop-parity", -1,
		"검증용: N 번째 패리티를 보내지 않는다 (-1 = 안 함)")
	corrP := flag.Int("corrupt-parity", -1,
		"검증용: N 번째 패리티의 한 바이트를 뒤집는다 (-1 = 안 함)")"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    old = """			*pdelay, *expectK, *stats, *dump)"""
    new = """			*pdelay, *expectK, *stats, *dump, *dropI, *dropP, *corrP)"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    # 집계
    old = """		agg.ParityFail += st.ParityFail"""
    new = """		agg.ParityFail += st.ParityFail
		agg.DroppedOrig += st.DroppedOrig
		agg.DroppedPar += st.DroppedPar
		agg.CorruptPar += st.CorruptPar"""
    if old in s:
        s = s.replace(old, new, 1)
        n += 1

    io.open(P, "w", encoding="utf-8", newline="\n").write(s)
    print("적용된 수정 %d 곳 (기대 13)" % n)
    return 0 if n == 13 else 1


def main():
    print("This historical source patch is disabled in gen33.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
