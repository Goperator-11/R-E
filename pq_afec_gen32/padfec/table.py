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
    w("package main\n\n")

    w("const defaultAssumedBurst = %g\n\n" % policy.DEFAULT_ASSUMED_BURST)

    w("const tPTONoAckMs = %.10g\n" % policy.T_PTO_NO_ACK_MS)
    w("const tAckRetxSlope = %.10g\n" % policy.T_ACK_RETX_SLOPE)
    w("const tAckRetxBaseMs = %.10g\n\n" % policy.T_ACK_RETX_BASE_MS)

    w("const quicgoMaxIPS = %d\n" % policy.QUICGO_MAX_IPS)
    w("const maxStepsDefault = %d\n" % policy.MAX_STEPS_DEFAULT)
    w("const mMaxDefault = %d\n" % max(M_VALS))
    w("const cPktDefault = %.10g\n\n" % policy.C_PKT_POLICY_DEFAULT)
    w("const uplinkMbpsDefault = %.10g\n\n" % policy.UPLINK_MBPS_DEFAULT)

    w("const jTieMs = %.10g\n\n" % policy.J_TIE_MS)

    w("var raceDelayMs = []float64{%s}\n"
      % ", ".join("%.17g" % v for v in policy.RACE_DELAY_MS))
    w("var raceWinQ = []float64{%s}\n\n"
      % ", ".join("%.17g" % v for v in policy.RACE_WIN_Q))

    w("var pfailK = []int{%s}\n" % ", ".join(str(v) for v in K_VALS))
    w("var pfailM = []int{%s}\n" % ", ".join(str(v) for v in M_VALS))
    w("var pfailP = []float64{%s}\n"
      % ", ".join("%g" % v for v in P_VALS))
    w("var pfailU = []float64{%s}\n\n"
      % ", ".join("%g" % v for v in U_VALS))

    w("var jointTable4 = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{\n")
        for m in M_VALS:
            w("\t\t{\n")
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{\n")
                for li, u in enumerate(U_VALS):
                    mat = jtab[(k, m, pi, li)]
                    gg = policy.recovery_group(k, m)
                    flat = [mat[a_][b_][c_] for a_ in range(k + 1)
                            for b_ in range(m + 1) for c_ in range(gg + 1)]
                    w("\t\t\t\t{%s},\n"
                      % ", ".join("%.17g" % v for v in flat))
                w("\t\t\t},\n")
            w("\t\t},\n")
        w("\t},\n")
    w("}\n\n")

    NL = chr(10)
    w("var roundMultTable = [][][][]float64{" + NL)
    for k in K_VALS:
        w(chr(9) + "{" + NL)
        for m in M_VALS:
            w(chr(9) * 2 + "{" + NL)
            for pi, p in enumerate(P_VALS):
                vals = ", ".join("%.17g" % rtab[(k, m, pi, li)]
                                 for li in range(len(U_VALS)))
                w(chr(9) * 3 + "{%s}," % vals + NL)
            w(chr(9) * 2 + "}," + NL)
        w(chr(9) + "}," + NL)
    w("}" + NL + NL)

    w("const ptoSampledRttMult = %g\n\n" % policy.PTO_SAMPLED_RTT_MULT)

    w("var failFracTable = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{\n")
        for m in M_VALS:
            w("\t\t{\n")
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{\n")
                for li, u in enumerate(U_VALS):
                    fr = ftab[(k, m, pi, li)]
                    w("\t\t\t\t{%s},\n"
                      % ", ".join("%.17g" % v for v in fr))
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
