# -*- coding: utf-8 -*-
"""정책이 쓰는 복구 실패 확률표를 Go 소스로 뽑아낸다.

왜 표인가
--------
폐루프를 닫으려면 결정이 **클라이언트 안에서** 일어나야 하고, 우리 클라이언트는
Go 다. 그런데 Gilbert-Elliott 소거 분포를 Go 로 다시 짜면 두 구현이 갈라진다 -
이번 연구에서 이미 Cauchy 생성행렬로 그 일을 겪었다(둘 다 MDS 였지만 서로
호환되지 않았고, 교차검증이 아니었으면 못 잡았다).

그래서 **다시 짜지 않는다.** 검증이 끝난 Python 모형으로 표를 만들어 Go 에
심고, Go 는 조회만 한다. 나머지(증폭 예산 산술)는 곱셈과 나눗셈뿐이라
그대로 옮겨도 갈라질 여지가 없다.

표 크기: k 4개 x m 3개 x p 11개 x L 4개 = 528 개. 심어도 부담이 없다.

사용
    python -m padfec.table experiments/quicbed/pfail_table.go

🩸 stdout 리다이렉션으로 쓰면 안 된다. 윈도우 콘솔이 cp949 라 한글 주석이
깨져 Go 가 "illegal UTF-8 encoding" 으로 거부한다. 파일을 직접 연다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from padfec import policy   # noqa: E402

K_VALS = [1, 2, 3, 4]
M_VALS = [0, 1, 2]
P_VALS = [0.0, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.20, 0.30]
L_VALS = [1.0, 2.0, 3.0, 5.0]


def pfail(k, m, p, L):
    """k+m 개 중 m 개를 넘게 잃어 복구가 안 될 확률.

    m = 0 은 이중화가 없다는 뜻이므로 '하나라도 잃으면 실패' 다.
    """
    if p <= 0.0:
        return 0.0
    if m == 0:
        return float(1.0 - policy.erasure_probs(k, p, L)[0])
    return policy.p_unrecoverable(k, m, p, L)


def joint(k, m, p, L):
    """P[a][b] = 원본 a 개·패리티 b 개 도착. policy.joint_arrival_pmf 그대로."""
    return policy.joint_arrival_pmf(k, m, p, L)


def build():
    tab, jtab = {}, {}
    for k in K_VALS:
        for m in M_VALS:
            for pi, p in enumerate(P_VALS):
                for li, L in enumerate(L_VALS):
                    tab[(k, m, pi, li)] = pfail(k, m, p, L)
                    jtab[(k, m, pi, li)] = joint(k, m, p, L)
    return tab, jtab


def emit_go(tab, jtab, out):
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

    w("var pfailK = []int{%s}\n" % ", ".join(str(v) for v in K_VALS))
    w("var pfailM = []int{%s}\n" % ", ".join(str(v) for v in M_VALS))
    w("var pfailP = []float64{%s}\n"
      % ", ".join("%g" % v for v in P_VALS))
    w("var pfailL = []float64{%s}\n\n"
      % ", ".join("%g" % v for v in L_VALS))

    # pfailTable 은 더 이상 내보내지 않는다(2026-08-20 감사). Go 가 P_fail 을
    # 별도 표에서 읽으면 기대 왕복 수와 다른 분포에서 나온다 - 그게 결함 1
    # 이었다. flightOutcome 이 jointTable 하나에서 둘 다 뽑는다.
    # Python 쪽 pfail() 은 v1 호환과 자체검증용으로 남겨 둔다.
    w("// jointTable[k인덱스][m인덱스][p인덱스][L인덱스] = 평탄화된 (k+1)x(m+1)\n")
    w("//   원소 [a*(m+1)+b] = 원본 a 개·패리티 b 개가 도착할 확률\n")
    w("var jointTable = [][][][][]float64{\n")
    for k in K_VALS:
        w("\t{ // k=%d\n" % k)
        for m in M_VALS:
            w("\t\t{ // m=%d\n" % m)
            for pi, p in enumerate(P_VALS):
                w("\t\t\t{ // p=%g\n" % p)
                for li, L in enumerate(L_VALS):
                    # %.17g = float64 왕복 정밀도. 9 자리로 찍으면
                    # Go 가 읽은 값이 Python 값과 ~1e-9 어긋나서
                    # '글자 단위로 맞춘다'는 약속이 검증 불가가 된다.
                    # 파일이 커지는 대신 두 구현이 비트 단위로 같아진다.
                    mat = jtab[(k, m, pi, li)]
                    flat = [mat[a_][b_] for a_ in range(k + 1)
                            for b_ in range(m + 1)]
                    w("\t\t\t\t{%s}, // L=%g\n"
                      % (", ".join("%.17g" % v for v in flat), L))
                w("\t\t\t},\n")
            w("\t\t},\n")
        w("\t},\n")
    w("}\n")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('사용: python -m padfec.table <출력경로>' + chr(10))
        return 2
    tab, jtab = build()
    import io as _io
    with _io.open(sys.argv[1], 'w', encoding='utf-8', newline=chr(10)) as f:
        emit_go(tab, jtab, f)
    sys.stderr.write('wrote %s (pfail %d + joint %d)'
                     % (sys.argv[1], len(tab), len(jtab)) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
