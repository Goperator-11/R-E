from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from padfec import policy

K_VALS = [1, 2, 3, 4]
M_VALS = [0, 1, 2, 3]
P_VALS = [0.0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.065, 0.08,
          0.10, 0.12, 0.135, 0.15, 0.1625, 0.175, 0.1875, 0.20, 0.2125,
          0.225, 0.2375, 0.25, 0.2625, 0.275, 0.2875, 0.30]
U_VALS = ([round(1.0 + 0.0625 * i, 4) for i in range(8)]
          + [round(1.5 + 0.125 * i, 3) for i in range(13)]
          + [3.5, 4.0, 4.5, 5.0])


def _clamp_p(p):
    return min(max(p, 0.0), 0.999)


def _L_of(p, u):
    return u / (1.0 - _clamp_p(p))


def pfail(k, m, p, L):
    if p <= 0.0:
        return 0.0
    if m == 0:
        return float(1.0 - policy.erasure_probs(k, p, L)[0])
    return policy.p_unrecoverable(k, m, p, L)


def joint(k, m, p, L):
    return policy.joint_arrival_pmf3c(k, m, p, L)


def _check_consistent():
    if max(M_VALS) != policy.M_MAX_DEFAULT:
        raise SystemExit(
            "표의 M_VALS 최대(%d) 와 policy.M_MAX_DEFAULT(%d) 가 다르다. "
            "둘을 맞춰라 - 안 맞으면 Go 가 실행 중에 죽는다."
            % (max(M_VALS), policy.M_MAX_DEFAULT))

    for _p in (0.05, 0.15, 0.20):
        _lo = policy.p_fail_of({"k": 2, "m": 1}, _p, _L_of(_p, 1.0) * 0.999)
        _at = policy.p_fail_of({"k": 2, "m": 1}, _p, _L_of(_p, 1.0))
        _hi = policy.p_fail_of({"k": 2, "m": 1}, _p, _L_of(_p, 1.0) * 1.05)
        if not (abs(_lo - _at) < 1e-12 and _hi > _at + 1e-9):
            raise SystemExit(
                "u 축의 전제가 깨졌다: p=%g 에서 꺾인 점이 L=1/(1-p)=%.4f 가 "
                "아니다 (왼쪽 %.6g, 그 점 %.6g, 오른쪽 %.6g). "
                "afec/channel.py 의 for_prior 경계가 바뀌었으면 "
                "padfec/table.py 의 U_VALS 좌표도 같이 고쳐야 한다."
                % (_p, _L_of(_p, 1.0), _lo, _at, _hi))

    for _p in P_VALS:
        for _k in K_VALS:
            for _m in M_VALS:
                _run = pfail(_k, _m, _p, policy.DEFAULT_ASSUMED_BURST)
                _node = pfail(_k, _m, _p, _L_of(_p, U_VALS[0]))
                if _run != _node:
                    raise SystemExit(
                        "실행 경로가 바뀐다: k=%d m=%d p=%g 에서 "
                        "burst=%g 의 값(%.17g)이 u=%g 마디의 값(%.17g)과 "
                        "다르다. 이 좌표 변경은 실행 경로를 안 건드려야 한다."
                        % (_k, _m, _p, policy.DEFAULT_ASSUMED_BURST,
                           _run, U_VALS[0], _node))


def fail_frac(k, m, p, L):
    a, b, c = policy.fail_split(k, m, p, L)
    tot = a + b + c
    if tot <= 0.0:
        a, b, c = policy.fail_split(k, m, 1e-9, L)
        tot = a + b + c
        if tot <= 0.0:
            return (1.0, 0.0, 0.0)
    return (a / tot, b / tot, c / tot)


def build():
    _check_consistent()
    tab, jtab, ftab, rtab = {}, {}, {}, {}
    for k in K_VALS:
        for m in M_VALS:
            for pi, p in enumerate(P_VALS):
                for li, u in enumerate(U_VALS):
                    L = _L_of(p, u)
                    tab[(k, m, pi, li)] = pfail(k, m, p, L)
                    jtab[(k, m, pi, li)] = joint(k, m, p, L)
                    ftab[(k, m, pi, li)] = fail_frac(k, m, p, L)
                    _R = policy.expected_rounds(k, m, p, L)
                    _pf = policy.p_fail_of({"k": k, "m": m}, p, L)
                    rtab[(k, m, pi, li)] = (
                        ((_R - 1.0) / _pf) if _pf > 1e-15 else 1.0)
    return tab, jtab, ftab, rtab


def emit_go(tab, jtab, ftab, rtab, out):
    w = out.write
    w("// 자동 생성 파일. 손대지 마라.\n")
    w("//   생성: python -m padfec.table experiments/quicbed/pfail_table.go\n")
    w("//\n")
    w("// padfec/policy.py 의 Gilbert-Elliott 분포를 그대로 담은 표다.\n")
    w("// Go 로 다시 구현하지 않는 이유는 table.py 의 머리말에 적었다 -\n")
    w("// 같은 알고리즘을 두 언어로 짜면 갈라지고, 이 연구에서 이미 겪었다.\n")
    w("//\n")
    w("// 2026-08-20 감사 결함 1·3 의 수리로 **결합 도착분포**를 새로 싣는다.\n")
    w("//   예전에는 Go 가 pfail 만 표에서 읽고 기대 왕복 수는 제 손으로\n")
    w("//   이항분포를 굴려 셌다. 한 비용식 안에 손실 모형이 둘이었고,\n")
    w("//   버스트가 있으면 두 항이 다른 세계를 봤다. 이제 둘 다 여기서 나온다.\n")
    w("package main\n\n")

    w("// Go 는 버스트를 관측할 수단이 없다. 그 사실을 호출부 리터럴로 숨기지\n")
    w("// 않고 이름 있는 값으로 둔다. 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const defaultAssumedBurst = %g\n\n" % policy.DEFAULT_ASSUMED_BURST)

    w("// 복구 실패 한 번의 대가. 2026-08-20 결정적 소거 실측\n")
    w("//   (experiments/_probe_trecover_rtt.py -> results/probe_trecover_rtt.json)\n")
    w("//   서버가 0 개 받음 -> ACK 없음 -> PTO.  RTT 와 무관한 상수.\n")
    w("//   1 개 이상       -> ACK -> 즉시 재전송. RTT 에 비례.\n")
    w("// 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const tPTONoAckMs = %.10g\n" % policy.T_PTO_NO_ACK_MS)
    w("const tAckRetxSlope = %.10g\n" % policy.T_ACK_RETX_SLOPE)
    w("const tAckRetxBaseMs = %.10g\n\n" % policy.T_ACK_RETX_BASE_MS)

    w("// 정책이 쓰는 상수. 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("//   quicgoMaxIPS  실측: -ips 1707 을 줘도 클라는 1452 로 깎아 보낸다\n")
    w("//   cPktDefault   서버 첫 비행 유효 모형 S_eff(n)=s0_base+n*c 의 기울기.\n")
    w("//                 **물리 바이트 수가 아니라 임계를 재현하는 유효값**이다\n")
    w("//                 (2026-08-21: quic-go 는 마지막 패킷이 작으면 한도를\n")
    w("//                  최대 +72 B 넘겨 보낸다. 그 여유를 유효 s0 가 흡수한다).\n")
    w("//                 임계 앵커 6 개 최소제곱. 패킷 직접 계수(40.55/41.39)와\n")
    w("//                 1.5 B/패킷 안에서 일치한다 - 근거는 padfec/policy.py.\n")
    w("const quicgoMaxIPS = %d\n" % policy.QUICGO_MAX_IPS)
    w("const maxStepsDefault = %d\n" % policy.MAX_STEPS_DEFAULT)
    w("const mMaxDefault = %d\n" % max(M_VALS))
    w("const cPktDefault = %.10g\n" % policy.C_PKT_POLICY_DEFAULT)

    w("\n// 업링크 대역 Mbps. J 의 t_tx 항이 쓴다. 0 이면 대역 제한 없음.\n")
    w("//   🩸 2026-08-21 - 그전에는 policy.go 안에 `10e6` 이 리터럴로 박혀\n")
    w("//   있었다. 어디서도 측정된 적 없는 수인데 격자 720 점 중 312 점\n")
    w("//   (43.3%) 의 선택을 좌우했고, 정작 이 테스트베드는 netem 이 대역을\n")
    w("//   안 걸어 실측과 25 배 어긋났다. 이제 `-uplink-mbps` 로 받고,\n")
    w("//   기본값 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const uplinkMbpsDefault = %.10g\n\n" % policy.UPLINK_MBPS_DEFAULT)

    w("// J 를 동점으로 볼 분해능(ms). 1 ns 로 두면 모형의 반올림 잡음이\n")
    w("// 정책을 정한다 - 실제로 그랬다(2026-08-21: 헤드라인 조건에서\n")
    w("// 0.0008 ms 차이로 1,325 B 를 더 사는 결정이 나왔다. 그 차이는\n")
    w("// 이 테스트베드의 측정 분해능 1 us 보다 작다).\n")
    w("// 정의는 padfec/policy.py 한 곳뿐이다.\n")
    w("const jTieMs = %.10g\n\n" % policy.J_TIE_MS)

    w("\n// 뒤따르는 패리티의 신용이 **송신 결정에 잡힐** 확률 q(d) 의 실측 표.\n")
    w("//   d = 패리티 바이트 / 업링크 대역 (ms). 마디 사이는 선형보간하고\n")
    w("//   마지막 마디 위는 0 이다. 이 표를 왜 함수꼴로 안 적는지, 어떻게\n")
    w("//   쟀는지는 padfec/policy.py 의 '경주' 절에 있다 - 정의는 거기 한 곳뿐이다.\n")
    w("//   실측 2026-08-26 probe_race2.py (cert 9000·k=2·RTT 50·손실 0%·gap 50).\n")
    w("var raceDelayMs = []float64{%s}\n"
      % ", ".join("%.17g" % v for v in policy.RACE_DELAY_MS))
    w("var raceWinQ = []float64{%s}\n\n"
      % ", ".join("%.17g" % v for v in policy.RACE_WIN_Q))

    w("var pfailK = []int{%s}\n" % ", ".join(str(v) for v in K_VALS))
    w("var pfailM = []int{%s}\n" % ", ".join(str(v) for v in M_VALS))
    w("var pfailP = []float64{%s}\n"
      % ", ".join("%g" % v for v in P_VALS))
    w("// 정규화 버스트 축. u = L*(1-p). 꺾인 점(독립<->GE 경계)이\n")
    w("// 모든 p 에서 u=1 에 오도록 잡은 좌표다 - 근거는 padfec/table.py\n")
    w("// 의 U_VALS 주석. **L 을 그대로 넣으면 안 된다.**\n")
    w("var pfailU = []float64{%s}\n\n"
      % ", ".join("%g" % v for v in U_VALS))

    w("// jointTable4[k인덱스][m인덱스][p인덱스][L인덱스] = 평탄화된 (k+1)x(m+1)x2\n")
    w("//   원소 [(a*(m+1)+b)*2 + r]\n")
    w("//     = 원본 a 개·패리티 b 개가 도착하고, 그중 **복구용 패리티**\n")
    w("//       (마지막으로 보낸 것, index m-1)의 도착 여부가 r 일 확률\n")
    w("//\n")
    w("// 🩸 2026-08-21 - 이름을 jointTable -> jointTable4 으로 바꿨다. 배치가\n")
    w("//   달라졌는데 이름이 같으면 옛 pfail_table.go 가 남아 있을 때 Go 가\n")
    w("//   **조용히 잘못 읽는다.** 이름을 바꾸면 컴파일이 깨져 드러난다.\n")
    w("//   왜 r 이 필요한가: 서버(qamp.go)는 마지막 패리티 하나로 소거 하나만\n")
    w("//   복구하고, 복구하면 그 패리티를 버리고 복구본(원본 크기)을 스택에\n")
    w("//   넘긴다. '몇 개 왔나' 만으로는 복구 여부도 신용 바이트도 정할 수 없다.\n")
    w("var jointTable4 = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{ // k=%d\n" % k)
        for m in M_VALS:
            w("\t\t{ // m=%d\n" % m)
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{ // p=%g\n" % p)
                for li, u in enumerate(U_VALS):
                    mat = jtab[(k, m, pi, li)]
                    gg = policy.recovery_group(k, m)
                    flat = [mat[a_][b_][c_] for a_ in range(k + 1)
                            for b_ in range(m + 1) for c_ in range(gg + 1)]
                    w("\t\t\t\t{%s}, // u=%g (L=%.4g)\n"
                      % (", ".join("%.17g" % v for v in flat),
                         u, _L_of(p, u)))
                w("\t\t\t},\n")
            w("\t\t},\n")
        w("\t},\n")
    w("}\n\n")

    NL = chr(10)
    w("// roundMultTable[k][m][p][u] = 반복 라운드 **배율** (R-1)/p_fail." + NL)
    w("// 재전송이 **또 실패**하는 경우를 세는 항이다. 옛 모형은 복구" + NL)
    w("// 라운드를 정확히 한 번만 청구했고, 그 오차가 m 에 따라 달라서" + NL)
    w("// m 끼리의 비교를 왜곡했다(p18 검사 6: 실측 +31.01 vs 예측 +13.51)." + NL)
    w("// 유도는 padfec/policy.py 의 expected_rounds - 맞춘 상수가 없다." + NL)
    w("// stall 항에 이 값을 곱한다. p=0 이면 1.0 (무손실 실측 불변)." + NL)
    w("// R 이 아니라 배율을 심는 이유: 보간한 R 을 보간한 p_fail 로" + NL)
    w("// 나누면 두 오차가 겹친다(관문 J 어긋남 0.096 -> 0.263 ms)." + NL)
    w("var roundMultTable = [][][][]float64{" + NL)
    for k in K_VALS:
        w(chr(9) + "{ // k=%d" % k + NL)
        for m in M_VALS:
            w(chr(9) * 2 + "{ // m=%d" % m + NL)
            for pi, p in enumerate(P_VALS):
                vals = ", ".join("%.17g" % rtab[(k, m, pi, li)]
                                 for li in range(len(U_VALS)))
                w(chr(9) * 3 + "{%s}, // p=%g" % (vals, p) + NL)
            w(chr(9) * 2 + "}," + NL)
        w(chr(9) + "}," + NL)
    w("}" + NL + NL)

    w("// RTT 표본이 있을 때의 첫 PTO 배율. RFC 9002 §5.3 + §6.2.1 에서\n")
    w("// **유도한** 값이지 맞춘 상수가 아니다 - 근거는 padfec/policy.py 의\n")
    w("// PTO_SAMPLED_RTT_MULT 주석에 있다.\n")
    w("const ptoSampledRttMult = %g\n\n" % policy.PTO_SAMPLED_RTT_MULT)

    w("// failFracTable[k][m][p][L] = {표본없는PTO, 표본있는PTO, 시간임계} 의 **비율**\n")
    w("//\n")
    w("// 실패 한 번의 대가는 **마지막 원본이 도착했는가**로 갈린다.\n")
    w("//   마지막 원본 도착 -> 그 ACK 이 시간 임계를 무장 -> 9/8·RTT\n")
    w("//   마지막 원본 유실, 앞의 것은 도착 -> 구멍을 못 봄 -> PTO(표본 있음) = 3·RTT\n")
    w("//   아무것도 없음 -> ACK 도 표본도 없음 -> PTO(표본 없음) = 상수\n")
    w("// 판별자가 jointTable4 의 축(a,b,r)에 없어서 표를 하나 더 싣는다.\n")
    w("// **확률이 아니라 비율**인 이유는 padfec/table.py 의 fail_frac 주석 참고.\n")
    w("var failFracTable = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{ // k=%d\n" % k)
        for m in M_VALS:
            w("\t\t{ // m=%d\n" % m)
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{ // p=%g\n" % p)
                for li, u in enumerate(U_VALS):
                    fr = ftab[(k, m, pi, li)]
                    w("\t\t\t\t{%s}, // u=%g (L=%.4g)\n"
                      % (", ".join("%.17g" % v for v in fr),
                         u, _L_of(p, u)))
                w("\t\t\t},\n")
            w("\t\t},\n")
        w("\t},\n")
    w("}\n")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('사용: python -m padfec.table <출력경로>' + chr(10))
        return 2
    tab, jtab, ftab, rtab = build()
    import io as _io
    with _io.open(sys.argv[1], 'w', encoding='utf-8', newline=chr(10)) as f:
        emit_go(tab, jtab, ftab, rtab, f)
    sys.stderr.write('wrote %s (pfail %d + joint %d + failfrac %d + rounds %d)'
                     % (sys.argv[1], len(tab), len(jtab), len(ftab),
                        len(rtab)) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
