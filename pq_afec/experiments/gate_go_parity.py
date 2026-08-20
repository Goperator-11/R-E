# -*- coding: utf-8 -*-
"""관문 - Python 정책과 Go 정책이 **같은 결정을 내리는가**.

왜 관문인가
-----------
폐루프(`-fec auto`)의 결정은 **Go 안에서** 일어난다. 그런데 검증·보고·모형
탐색은 전부 Python `padfec.policy` 로 한다. 둘이 갈라지면 우리가 검증한 것과
실제로 도는 것이 다른 물건이 되고, 그 아래의 측정은 전부 근거를 잃는다.

이건 가정이 아니라 이 연구에서 두 번 실제로 일어난 일이다.

  1 차  Cauchy 생성행렬을 Go 와 Python 에 각각 짰다. 둘 다 MDS 라 각자는
        정상 동작했는데 **서로 호환이 안 됐다.** 교차검증이 없었으면 못 잡았다.
  2 차  `policy.go` 가 버스트를 `1.0` 리터럴로 박아 두고 Python 은 실제
        버스트를 썼다. 같은 입력에 다른 m 을 골랐다 - 90 조건 중 17 건.

그래서 확률 모형은 Go 에서 다시 짜지 않고 표로 심는다(`padfec/table.py`).
남은 증폭 예산 산술은 정수 연산뿐이라 옮겨 적었는데, **옮겨 적은 것이 맞는지는
여기서만 확인된다.** 실제로 v2 이식 때 `ceilDiv` 하나가 틀려(Python `//` 는
내림, Go `/` 는 0 쪽 절사) 5,670 격자점 중 92 건이 어긋났다.

🩸 이 대조를 그동안 임시 폴더의 일회용 프로그램으로 돌렸다. 세션이 끝나면
   사라지므로 다음 사람에게는 "불일치 0 건"이라는 **문장만** 남는다.
   `padfec/policy.py` 머리말은 "격자 대조로 못 박는다"고 적어 놓고 정작 그
   자를 저장소에 안 뒀던 셈이다. 이제 자가 여기 있고 관문에서 매번 돈다.

무엇을 대조하나
---------------
격자의 정본은 **Go 쪽**이다(`policy.go` 의 `policyGrid`). 여기서는 그 출력을
읽어 같은 입력으로 `decide_v2` 를 돌리고 고른 결과를 통째로 비교한다.
양쪽에 격자 목록을 각각 적으면 언젠가 갈라지기 때문이다.

  비교 대상: (mode, δ, m, InitialPacketSize) 네 개 전부

Go 는 k 를 관측값으로 받고 Python 은 C(ClientHello 바이트)에서 k 를 세므로,
`natural_k(C, W, h) == k` 가 되는 C 를 골라 준다. 그 외 입력은 전부 같다.

Output: experiments/results/gate_go_parity.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from padfec import capacity, policy              # noqa: E402

RESULTS = os.path.join(HERE, "results")
OUT = os.path.join(RESULTS, "gate_go_parity.json")

# Python 쪽 h. Go 는 k 를 관측값으로 받으므로 이 값을 안 쓴다 - C 를 역산할
# 때만 필요하다. padfec.capacity.DEFAULT_H 와 decide_v2 기본값이 같은 51 이다.
H = capacity.DEFAULT_H


def go_rows(dump=None):
    """Go 정책의 격자 결정을 읽어 온다.

    dump 를 주면 그 파일을 읽고, 아니면 qamp 를 직접 돌린다. WSL 안에서는
    padbed 와 **같은 경로 규칙**을 쓴다(/tmp/qamp -> ~/quicbed/bin/qamp).
    윈도우에서 부를 때는 WSL 을 거친다 - 바이너리가 거기 있기 때문이다.
    """
    if dump:
        with open(dump, encoding="utf-8") as f:
            return f.read().splitlines(), "dump:%s" % dump

    if os.name == "nt":
        # loop2/pipeline 이 쓰는 것과 같은 배포판을 쓴다.
        cmd = ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc",
               '"$HOME/quicbed/bin/qamp" -mode policygrid']
        src = "wsl:~/quicbed/bin/qamp"
    else:
        import padbed as B                        # noqa: E402
        cmd = [B.require_bin(), "-mode", "policygrid"]
        src = cmd[0]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError("qamp -mode policygrid 실패: %s" % r.stderr[-500:])
    return r.stdout.replace("\r", "").splitlines(), src


def c_for_k(k, w):
    """natural_k(C, w, H) == k 가 되는 C 하나. 구간 가운데를 고른다.

    가운데를 고르는 이유: 구간 끝은 h 를 한 바이트만 달리 봐도 k 가 바뀌는
    자리다. 대조에서 보고 싶은 것은 경계 처리가 아니라 **정책의 결정**이다.
    """
    per = w - H
    return ((k - 1) * per + 1 + k * per) // 2


def main():
    dump = None
    if "--dump" in sys.argv:
        dump = sys.argv[sys.argv.index("--dump") + 1]
    lines, src = go_rows(dump)
    lines = [ln for ln in lines if ln.strip()]
    print("Go 격자점 %d 개  (%s)" % (len(lines), src))
    if not lines:
        print("  FAIL  Go 가 아무것도 안 찍었다")
        return 2

    bad, picks, deltas = [], {}, {}
    for ln in lines:
        f = ln.split()
        k, w, cert = int(f[0]), int(f[1]), int(f[2])
        s0b, rtt, p, l = float(f[3]), float(f[4]), float(f[5]), float(f[6])
        go = (f[7], int(f[8]), int(f[9]), int(f[10]))

        C = c_for_k(k, w)
        assert capacity.natural_k(C, w, H) == k, (C, w, k)
        r = policy.decide_v2(C=C, cert_bytes=cert, rtt_ms=rtt, p=p, burst=l,
                             W=w, h=H, s0_base=s0b,
                             c_pkt=policy.C_PKT_POLICY_DEFAULT,
                             max_steps=policy.MAX_STEPS_DEFAULT, m_max=2,
                             max_ips=policy.QUICGO_MAX_IPS)
        c = r["choice"]
        py = (c["mode"], c["delta_per_dgram"], c["m"], c["W_eff"])
        if py != go:
            bad.append({"k": k, "w": w, "cert": cert, "s0_base": s0b,
                        "rtt_ms": rtt, "p": p, "burst": l,
                        "go": list(go), "py": list(py)})
        picks[go[0]] = picks.get(go[0], 0) + 1
        if go[0] == "pad":
            deltas[go[1]] = deltas.get(go[1], 0) + 1

    ok = not bad
    print()
    print("=== Python decide_v2 vs Go decide - (mode, delta, m, ips) 전부 ===")
    print(("  OK   " if ok else "  FAIL ")
          + "%d 격자점 중 불일치 %d 건" % (len(lines), len(bad)))
    for x in bad[:8]:
        print("     k=%d w=%d cert=%d s0b=%g rtt=%g p=%g L=%g | Go %s | Py %s"
              % (x["k"], x["w"], x["cert"], x["s0_base"], x["rtt_ms"],
                 x["p"], x["burst"], x["go"], x["py"]))

    # 일치만으로는 부족하다 - 양쪽이 나란히 아무것도 안 고르는 경우에도
    # 0 건이 나온다. 지렛대가 실제로 쓰이는지도 같이 찍는다.
    print()
    print("=== 지렛대가 실제로 선택되는가 (v2 이식의 목적) ===")
    for mode, n in sorted(picks.items(), key=lambda t: -t[1]):
        print("   %-8s %5d 건 (%.1f%%)" % (mode, n, 100.0 * n / len(lines)))
    if deltas:
        print("   pad 을 고른 판의 delta: %s"
              % sorted(deltas.items())[:8])
        print("   그중 delta=1 (1 바이트로 칸 올리기): %d 건"
              % deltas.get(1, 0))
    pad_ok = deltas.get(1, 0) > 0
    if not pad_ok:
        print("  FAIL  δ=1 을 고르는 판이 하나도 없다 - 헤드라인이 "
              "정책의 손에서 실현되지 않는다")

    # 🩸 --dump 로 돈 결과는 **기록하지 않는다.** 이 옵션의 주 용도는 부정
    # 시험(일부러 틀린 Go 출력을 먹여 관문이 잡는지 보는 것)이라, 그 FAIL 을
    # results/ 에 남기면 실제 바이너리가 틀린 것처럼 보인다. 이 파일은
    # "지금 빌드된 Go 가 무엇을 하는가"만 가리켜야 한다.
    if dump:
        print()
        print("(--dump 실행이라 %s 는 안 건드린다)" % os.path.basename(OUT))
    else:
        os.makedirs(RESULTS, exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"grid_points": len(lines), "source": src,
                       "mismatch": len(bad), "mismatches": bad[:50],
                       "picks": picks, "pad_deltas": deltas,
                       "ok": bool(ok and pad_ok)}, f,
                      ensure_ascii=False, indent=1)
        print()
        print("wrote %s" % OUT)
    return 0 if (ok and pad_ok) else 1


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass
    sys.exit(main())
