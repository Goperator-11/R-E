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

import hashlib
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

# 표 보간 근소차의 허용 한도 (ms).
#
# Go 는 결합 도착분포를 표에서 읽고 p 를 선형보간한다(padfec/table.py 의 규칙 -
# 확률 모형을 Go 로 다시 짜면 갈라지므로 표로 심는다). 표 마디 사이에서는
# 보간 오차가 남고, 아주 근소한 동점에서 m 하나가 갈릴 수 있다.
#
# **이 값은 완화가 아니라 새로 생긴 자다.** 그전 격자의 p 는 전부 표의 마디라
# 보간이 한 번도 안 돌았고, 따라서 "불일치 0 건" 이 이 경로를 하나도 안 지키고
# 있었다(감사 2026-08-21). 이제 마디 밖 p 를 넣어 경로를 밟게 하고, 대신 갈린
# 대가를 Python 자신의 J 로 재서 한도 안인지 본다.
#
# 한도 0.1 ms 의 근거 (실측 2026-08-21, 27,216 격자점):
#   실제 최대 대가        0.026 ms   (마디 밖 p=0.035·0.15 에서 38 건)
#   p11/p15 측정 잡음    ~1 ms      (후회 지표의 표준오차)
#   이 연구의 헤드라인    50 ms      (δ=1 이 사들이는 왕복 하나, RTT 50 ms)
# 즉 한도는 실측 최대의 4 배이면서 측정 잡음의 1/10, 헤드라인의 1/500 이다.
# 여기를 넘는 갈라짐은 보간으로 설명되지 않으므로 이식 결함으로 본다.
INTERP_TOL_MS = 0.1

# 결정이 **같은** 점에서 두 언어의 J 가 얼마나 갈려도 되는가.
#
# 2026-08-27 신설. 그전에는 이 관문이 `if py != go:` 안에서만 J 를 봤기
# 때문에, **결정을 안 뒤집는 J 어긋남은 원리적으로 안 보였다**(감사가
# 지적). Go 는 결합분포와 실패 비율을 표에서 읽고 p 를 선형보간하는데
# Python 은 정확히 계산하므로, 마디 사이에서는 J 가 반드시 조금 갈린다.
# 그 크기를 **재서 한도 안인지 보는 것**이 이 상수의 일이다.
#
# 값은 측정해서 정한다(아래 실행이 실제 최대치를 찍는다). 자를 먼저
# 정하고 결과를 맞추지 않는다 - 이 저장소의 규칙이다.
# 값은 **INTERP_TOL_MS 와 같은 예산**이다. 둘 다 "표를 선형보간해서 생기는
# 오차"를 재는 자이고, 다만 하나는 그 오차가 **결정**에 물리는 대가를,
# 다른 하나는 **J 자체**의 어긋남을 본다. 같은 원인에 두 개의 다른 자를
# 두면 어느 쪽이 진짜인지 아무도 모르게 된다.
#
# 2026-08-27 이 자를 처음 켜고 잰 값:
#     결정이 같은 점의 최대 |Go J - Py J| = 0.079466 ms
#     (k=3 cert=1000 rtt=100 **p=0.035** L=1 up=0 - p 가 표의 마디
#      0.03 과 0.05 **사이**라 보간이 가장 크게 도는 자리다)
#     한도 0.1 을 넘는 점 0 건.
# 결정에 물리는 대가는 그보다 훨씬 작다(위 근소차 96 건, 최대 0.0097 ms) -
# J 가 0.08 ms 갈려도 그 자리가 동점 경계에 걸터앉은 경우만 순위가 바뀌기
# 때문이다. **자를 좁히고 싶으면 표에 p 마디를 더한다**(2026-08-25 에
# 0.15 를 그렇게 더했다). 자를 넓히는 것은 처방이 아니다.
J_DIFF_TOL_MS = float(__import__("os").environ.get("PADFEC_GATE_JTOL")
                      or INTERP_TOL_MS)

# Python 쪽 h. Go 는 k 를 관측값으로 받으므로 이 값을 안 쓴다 - C 를 역산할
# 때만 필요하다. padfec.capacity.DEFAULT_H 와 decide_v2 기본값이 같은 51 이다.
H = capacity.DEFAULT_H


QUICBED = os.path.join(HERE, "quicbed")


def go_src_fingerprint():
    """quicbed 소스의 지문. `quicbed/build.sh` 가 뜨는 것과 **같은 식**이다.

    파일마다 `"<이름> <sha256>\\n"` 을 만들어 이어 붙이고 그 전체를 다시
    sha256 한다. 대상은 quicbed 의 `*.go` 전부 + `build.sh` 이고, 목록은
    훑어서 만든다 - `loop2.py` 의 `_sources` 와 같은 범위이고 같은 이유다
    (사람이 두 곳을 같이 고쳐야 하는 구조가 애초에 사고의 원인이었다).

    원본 바이트를 그대로 잰다(CRLF 를 안 벗긴다). 벗긴 뒤에 재면 bash 의
    `sed 's/\\r$//'` 과 여기의 정규화가 미묘하게 갈릴 수 있는데, 원본이 같으면
    벗긴 것도 같으므로 원본을 재는 쪽이 엄격하면서 단순하다.
    """
    names = sorted([n for n in os.listdir(QUICBED) if n.endswith(".go")]
                   + (["build.sh"]
                      if os.path.exists(os.path.join(QUICBED, "build.sh"))
                      else []))
    h = hashlib.sha256()
    for n in names:
        with open(os.path.join(QUICBED, n), "rb") as f:
            inner = hashlib.sha256(f.read()).hexdigest()
        h.update(("%s %s\n" % (n, inner)).encode())
    return h.hexdigest()


def built_fingerprint(win):
    """빌드된 바이너리 옆에 적힌 지문. 없으면 None."""
    if win:
        r = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc",
             'cat "$HOME/quicbed/bin/qamp.srcsha" 2>/dev/null'],
            capture_output=True, text=True, timeout=60)
        got = r.stdout.strip()
        return got or None
    import padbed as B                            # noqa: E402
    p = B.require_bin() + ".srcsha"
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read().strip() or None


def check_build_is_current(win):
    """🩸 2026-09-03 - **바이너리가 소스보다 낡았는지 먼저 본다.**

    이 관문은 빌드를 안 한다. 그런데 `padbed.require_bin()` 은 `/tmp/qamp` 가
    **있기만 하면** 낡았는지 안 묻고, `README` 가 안내하는 「관문만 따로」
    실행에는 빌드 단계가 아예 없다(`loop2.py` 로 돌면 `BED` 지문이 잡아 준다 -
    무방비인 것은 단독 실행 경로뿐이다).

    실제로 이 구멍에 사람이 빠졌다. 2026-08-29 `fcdd7a0` 이 반복 라운드 항과
    P_VALS 를 바꿨는데 Go 를 다시 안 빌드하고 관문을 돌리면:

        격자점 178,200 · 진짜 불일치 5,016 건 · J 최대 46.09 ms
        (최악점 k=3 cert=12000 rtt=100 p=0.2875 L=4 up=10)

    이 나온다. 다시 빌드하면 196,020 점에 불일치 0 건이다. 즉 **관문은 조용히
    통과한 게 아니라 붉어졌다** - 문제는 그 실패가 「진짜 불일치」라고 적혀
    있어서 **모형 결함으로 읽힌다**는 것이다. 멀쩡한 모형을 뜯게 만든다.
    열 수 검사(13 개)로는 못 잡는다 - 그 변경은 열 수를 안 건드렸다.

    조용히 초록이 되는 경우도 하나 있다. **격자만 넓히고 표는 안 바꾼** 세대
    차이라면 옛 바이너리가 더 적은 점을 내고 그 점들은 다 맞는다. 그러면
    「불일치 0 건」이 뜨는데 실제로는 덮는 범위가 줄어 있다. `grid_points` 가
    결과에 적히기는 하지만 아무도 그 수를 기대치와 대조하지 않았다.
    """
    want = go_src_fingerprint()
    got = built_fingerprint(win)
    if got == want:
        return want, got
    print("  FAIL  빌드된 Go 가 저장소 소스와 다르다 (또는 지문이 없다)")
    print("        소스 지문   %s" % want)
    print("        바이너리    %s" % (got or "없음 - 옛 build.sh 로 빌드됐다"))
    print()
    print("        이 상태로 나오는 불일치는 **이식 결함이 아니라 낡은")
    print("        바이너리**다. 모형을 뜯기 전에 먼저 다시 빌드해라:")
    print("            wsl -d Ubuntu -- bash experiments/quicbed/build.sh")
    return want, got


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
    if dump:
        # --dump 는 부정 시험용이다(일부러 낡거나 틀린 출력을 먹인다).
        # 지문 대조를 걸면 그 시험 자체가 안 돈다.
        src_sha = built_sha = None
        src_ok = True
        print("(--dump 실행 - 빌드 지문 대조를 건너뛴다)")
    else:
        src_sha, built_sha = check_build_is_current(os.name == "nt")
        src_ok = (src_sha == built_sha)
    lines, src = go_rows(dump)
    lines = [ln for ln in lines if ln.strip()]
    print("Go 격자점 %d 개  (%s)" % (len(lines), src))
    if not lines:
        print("  FAIL  Go 가 아무것도 안 찍었다")
        return 2

    bad, near, picks, deltas = [], [], {}, {}
    jdiff = []
    uplinks = set()
    for ln in lines:
        f = ln.split()
        # 🆕 2026-08-21: up(업링크 Mbps) 축이 8 번째 열로 들어왔다. 그전에는
        # 이 항이 양쪽에 리터럴 10 Mbps 로 박혀 있어서 **격자 대조가 이 항의
        # 갈라짐을 원리적으로 못 잡았다.** 열 수로 옛 형식을 걸러 낸다 -
        # 조용히 옛 덤프를 읽고 통과하면 자가 없는 것과 같다.
        # 2026-08-27: J 가 13 번째 열로 들어왔다. 그전에는 관문이 **결정만**
        # 봐서, 결정을 안 뒤집는 J 어긋남(표 보간 오차)이 원리적으로 안
        # 보였다. 열 수로 옛 형식을 걸러 낸다.
        if len(f) != 13:
            raise RuntimeError(
                "격자 줄의 열이 13 개가 아니다(%d 개): %r\n"
                "  옛 형식(11 열)이면 Go 를 다시 빌드해야 한다 - "
                "up(업링크) 축이 2026-08-21 에 추가됐다." % (len(f), ln))
        k, w, cert = int(f[0]), int(f[1]), int(f[2])
        s0b, rtt, p, l = float(f[3]), float(f[4]), float(f[5]), float(f[6])
        up = float(f[7])
        go = (f[8], int(f[9]), int(f[10]), int(f[11]))
        go_j = float(f[12])
        uplinks.add(up)

        C = c_for_k(k, w)
        assert capacity.natural_k(C, w, H) == k, (C, w, k)
        r = policy.decide_v2(C=C, cert_bytes=cert, rtt_ms=rtt, p=p, burst=l,
                             W=w, h=H, s0_base=s0b,
                             c_pkt=policy.C_PKT_POLICY_DEFAULT,
                             max_steps=policy.MAX_STEPS_DEFAULT,
                             m_max=policy.M_MAX_DEFAULT,
                             max_ips=policy.QUICGO_MAX_IPS,
                             uplink_mbps=up)
        c = r["choice"]
        py = (c["mode"], c["delta_per_dgram"], c["m"], c["W_eff"])
        # 2026-08-27 - **같은 후보의 J 를 직접 견준다.** 결정이 같아도 두
        #    언어의 J 가 갈릴 수 있고(Go 는 표+보간, Python 은 정확 계산),
        #    그 갈라짐은 여태 이 관문에 원리적으로 안 보였다 - 아래 비교가
        #    `if py != go:` 안에만 있었기 때문이다. Go 가 고른 후보를
        #    Python 후보 목록에서 찾아 J 를 뺀다.
        _jm = {(x["mode"], x["delta_per_dgram"], x["m"], x["W_eff"]):
               x["j_ms"] for x in r["candidates"]}
        if go in _jm:
            jdiff.append((abs(go_j - _jm[go]),
                          {"k": k, "cert": cert, "rtt": rtt, "p": p,
                           "burst": l, "up": up, "go_j": go_j,
                           "py_j": _jm[go]}))
        if py != go:
            # 🆕 2026-08-21. 불일치를 **두 종류로 가른다.**
            #
            #   진짜 불일치   Go 가 Python 에 없는 답을 내거나, 그 답이
            #                 Python 의 J 로 봐도 확실히 나쁘다 -> 이식 결함.
            #   보간 근소차   Go 는 결합분포를 **표에서 읽고 p 를 선형보간**
            #                 하는데 Python 은 정확히 계산한다. 표 마디 사이에서
            #                 아주 근소한 동점이 갈릴 수 있다. 그 대가를 Python
            #                 자신의 J 로 재서 한도 안이면 보간 오차로 분류한다.
            #
            # 🩸 왜 이 구분이 필요했나: 그전 격자의 p 값 {0, 0.005, 0.02, 0.05,
            #    0.2} 는 **전부 표의 마디**여서 보간이 한 번도 안 돌았다.
            #    "불일치 0 건" 이 보간 경로를 전혀 안 지키고 있었다(감사
            #    2026-08-21). 이제 마디 밖 p(0.007·0.035·0.15)를 격자에 넣고,
            #    대신 그 대가를 재서 보고한다.
            jmap = {(x["mode"], x["delta_per_dgram"], x["m"], x["W_eff"]):
                    x["j_ms"] for x in r["candidates"]}
            reg = None
            if go in jmap and py in jmap:
                reg = jmap[go] - jmap[py]
            rec = {"k": k, "w": w, "cert": cert, "s0_base": s0b,
                   "rtt_ms": rtt, "p": p, "burst": l, "uplink_mbps": up,
                   "go": list(go), "py": list(py),
                   "j_regret_ms": reg}
            if reg is not None and abs(reg) <= INTERP_TOL_MS:
                near.append(rec)
            else:
                bad.append(rec)
        picks[go[0]] = picks.get(go[0], 0) + 1
        if go[0] == "pad":
            deltas[go[1]] = deltas.get(go[1], 0) + 1

    worst_interp = max([abs(x["j_regret_ms"] or 0.0) for x in near], default=0.0)
    # 2026-08-27 - **결정이 같은 점에서의 J 어긋남.** 이 수가 이 관문의
    #    새 눈이다. 한도는 아래 J_DIFF_TOL_MS 이고, 근거는 그 상수 주석.
    # 튜플 정렬은 첫 원소가 같으면 dict 를 비교하려 든다. 키를 준다.
    jdiff.sort(key=lambda t: t[0], reverse=True)
    worst_j = jdiff[0][0] if jdiff else 0.0
    j_over = [x for x in jdiff if x[0] > J_DIFF_TOL_MS]
    ok = (not bad) and (not j_over)
    print()
    print("=== Python decide_v2 vs Go decide - (mode, delta, m, ips) 전부 ===")
    print(("  OK   " if ok else "  FAIL ")
          + "%d 격자점 중 진짜 불일치 %d 건" % (len(lines), len(bad)))
    print("       표 보간 근소차 %d 건 - Python J 기준 최대 대가 %.6f ms "
          "(한도 %.3f ms)" % (len(near), worst_interp, INTERP_TOL_MS))
    print("       결정이 같은 점의 J 어긋남 - 최대 %.6f ms "
          "(한도 %.3f), 한도 초과 %d 건 / %d 점"
          % (worst_j, J_DIFF_TOL_MS, len(j_over), len(jdiff)))
    for _d, _w in j_over[:3]:
        print("         k=%d cert=%d rtt=%g p=%g L=%g up=%g | Go J %.6f "
              "vs Py J %.6f | 차 %.6f ms"
              % (_w["k"], _w["cert"], _w["rtt"], _w["p"], _w["burst"],
                 _w["up"], _w["go_j"], _w["py_j"], _d))
    if near[:3]:
        for x in near[:3]:
            print("         p=%g rtt=%g up=%g | Go %s | Py %s | 대가 %.6f ms"
                  % (x["p"], x["rtt_ms"], x["uplink_mbps"], x["go"], x["py"],
                     x["j_regret_ms"]))
    for x in bad[:8]:
        print("     k=%d w=%d cert=%d s0b=%g rtt=%g p=%g L=%g up=%g | "
              "Go %s | Py %s"
              % (x["k"], x["w"], x["cert"], x["s0_base"], x["rtt_ms"],
                 x["p"], x["burst"], x["uplink_mbps"], x["go"], x["py"]))

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

    # 🆕 격자가 실제로 새 축을 훑었는지, 그리고 새 후보 가족(combo)이 실제로
    # 뽑히는지 확인한다. 축을 더해 놓고 한 값만 돌면 자를 늘린 척만 한 것이고,
    # combo 가 한 번도 안 뽑히면 결합 후보 이식이 대조되지 않은 것이다.
    up_ok = len(uplinks) >= 2
    if not up_ok:
        print("  FAIL  업링크 축이 %s 하나뿐이다 - 이 항의 갈라짐을 "
              "대조하지 못한다" % sorted(uplinks))
    combo_ok = picks.get("combo", 0) > 0
    if not combo_ok:
        print("  FAIL  combo(결합 δ·m) 후보가 한 번도 안 뽑혔다 - "
              "2026-08-21 이식이 격자에서 대조되지 않는다")

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
                       # 🩸 2026-09-03 - 아래 넷이 결과에 안 남고 stdout 에만
                       #    찍혔다. 2026-08-27 에 「결정이 같은 점의 J 어긋남」
                       #    이라는 눈을 새로 달아 놓고, 정작 그 눈이 본 것을
                       #    파일에 안 적은 것이다. 이 파일 머리말이 꾸짖는
                       #    바로 그 병("다음 사람에게는 문장만 남는다")이다.
                       #    지금 여유가 0.095/0.100 으로 5% 뿐이라 더욱
                       #    남겨야 한다 - 다음에 좁아지는 것을 이 수로만
                       #    알 수 있다.
                       "worst_j_diff_ms": worst_j,
                       "j_diff_over_tol": len(j_over),
                       "j_diff_tol_ms": J_DIFF_TOL_MS,
                       "j_diff_points": len(jdiff),
                       # 🩸 2026-09-03 - 어느 소스에서 빌드된 바이너리를 잰
                       #    것인지 같이 남긴다. 이게 없으면 「불일치 0 건」이
                       #    어느 세대의 0 건인지 나중에 알 길이 없다.
                       "go_src_sha256": src_sha,
                       "go_built_sha256": built_sha,
                       "go_build_current": bool(src_ok),
                       "mismatch": len(bad), "mismatches": bad[:50],
                       "interp_near_misses": len(near),
                       "interp_worst_j_regret_ms": worst_interp,
                       "interp_tol_ms": INTERP_TOL_MS,
                       "picks": picks, "pad_deltas": deltas,
                       "uplinks": sorted(uplinks),
                       "ok": bool(ok and pad_ok and up_ok and combo_ok
                                  and src_ok)}, f,
                      ensure_ascii=False, indent=1)
        print()
        print("wrote %s" % OUT)
    return 0 if (ok and pad_ok and up_ok and combo_ok and src_ok) else 1


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass
    sys.exit(main())
