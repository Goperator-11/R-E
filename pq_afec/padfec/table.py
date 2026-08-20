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


def build():
    tab = {}
    for k in K_VALS:
        for m in M_VALS:
            for pi, p in enumerate(P_VALS):
                for li, L in enumerate(L_VALS):
                    tab[(k, m, pi, li)] = pfail(k, m, p, L)
    return tab


def emit_go(tab, out):
    w = out.write
    w("// 자동 생성 파일. 손대지 마라.\n")
    w("//   생성: python -m padfec.table > experiments/quicbed/pfail_table.go\n")
    w("//\n")
    w("// padfec/policy.py 의 Gilbert-Elliott 소거 분포를 그대로 담은 표다.\n")
    w("// Go 로 다시 구현하지 않는 이유는 table.py 의 머리말에 적었다 -\n")
    w("// 같은 알고리즘을 두 언어로 짜면 갈라지고, 이 연구에서 이미 겪었다.\n")
    w("package main\n\n")

    w("var pfailK = []int{%s}\n" % ", ".join(str(v) for v in K_VALS))
    w("var pfailM = []int{%s}\n" % ", ".join(str(v) for v in M_VALS))
    w("var pfailP = []float64{%s}\n"
      % ", ".join("%g" % v for v in P_VALS))
    w("var pfailL = []float64{%s}\n\n"
      % ", ".join("%g" % v for v in L_VALS))

    w("// pfailTable[k인덱스][m인덱스][p인덱스][L인덱스]\n")
    w("var pfailTable = [][][][]float64{\n")
    for k in K_VALS:
        w("\t{ // k=%d\n" % k)
        for m in M_VALS:
            w("\t\t{ // m=%d\n" % m)
            for pi, p in enumerate(P_VALS):
                vals = ", ".join("%.9g" % tab[(k, m, pi, li)]
                                 for li in range(len(L_VALS)))
                w("\t\t\t{%s}, // p=%g\n" % (vals, p))
            w("\t\t},\n")
        w("\t},\n")
    w("}\n")


def main():
    if len(sys.argv) < 2:
        sys.stderr.write('사용: python -m padfec.table <출력경로>' + chr(10))
        return 2
    tab = build()
    import io as _io
    with _io.open(sys.argv[1], 'w', encoding='utf-8', newline=chr(10)) as f:
        emit_go(tab, f)
    sys.stderr.write('wrote %s (%d 항목)' % (sys.argv[1], len(tab)) + chr(10))
    return 0


if __name__ == "__main__":
    sys.exit(main())
