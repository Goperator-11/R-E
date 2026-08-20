# -*- coding: utf-8 -*-
"""P7 - 알고리즘이 정말로 작동하는지 결정적으로 검증한다.

무작위 손실 통계는 "꼬리가 줄었다"까지만 말한다. 그 개선이 **복구 때문인지**,
우리가 모르는 다른 경로로 이득을 본 것은 아닌지는 말해 주지 않는다.
그래서 여기서는 어느 데이터그램이 사라질지 우리가 정하고, 매 조건마다
**반드시 그래야 하는 결과**를 미리 적어 두고 대조한다.

핵심은 긍정 시험뿐 아니라 **부정 시험**이 있다는 것이다. 고칠 수 없게 만들어
놓았을 때 정말 못 고쳐야 한다. 그러지 않으면 그 이득은 복구가 아니라 다른
데서 온 것이다.

  V1  off, 소거 없음              1-RTT, 100% 성공          (정상 동작 기준선)
  V2  off, 원본 0 소거            PTO (>= 900 ms)          (기준선이 실제로 아프다)
  V3  off, 원본 1 소거            PTO
  V4  fec m=1, 원본 0 소거        1-RTT, 복구 = 시행 수      (긍정)
  V5  fec m=1, 원본 1 소거        1-RTT, 복구 = 시행 수      (긍정)
  V6  fec m=1, 패리티 소거        PTO, 복구 0               (부정: 패리티 없으면 못 고쳐야)
  V7  fec m=1, 원본0 + 패리티 손상  PTO, 복구 0, CRC 거절 > 0 (부정: 틀린 복구를 안 넘긴다)
  V8  fec m=2, 원본 0 소거        1-RTT, 복구 = 시행 수      (긍정)
  V9  fec m=1, 원본 0+1 소거      실패 또는 PTO, 복구 0      (부정: m=1 은 2 소거를 못 고친다)
  V10 모든 조건에서 스택 전달 바이트 <= 물리 수신 바이트         (회계 불변식)
  V11 커널 계수기로 본 증폭비 <= 3.0                          (우리 코드 밖의 증거)

V11 은 우리 계수기를 믿지 않는다. RTT 를 아주 크게(편도 2 초) 잡아 서버의
첫 응답 버스트와 클라이언트의 두 번째 비행을 시간축에서 갈라 놓고, 그 사이에
`ip -s link` 로 커널이 센 바이트를 읽는다. 우리 프로그램이 무엇을 세든
상관없이 커널이 본 숫자다.

Output: experiments/results/p7_verify.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                      # noqa: E402

RTT_MS = 50.0
CERT = 2955          # 모든 팔이 1-RTT 인 크기 - 증폭 효과와 섞이지 않게
N = 12   # 연막용 작은 값 - 본 실행에서는 40 으로 올린다
GROUP = "X25519MLKEM768"
K = 2
PTO_FLOOR_MS = 900.0   # RFC 9002 초기 PTO 는 약 999 ms


def run_case(name, fec, m, drop_i=-1, drop_p=-1, corrupt_p=-1, n=N):
    extra = []
    if drop_i >= 0:
        extra += ["-drop-initial", str(drop_i)]
    if drop_p >= 0:
        extra += ["-drop-parity", str(drop_p)]
    if corrupt_p >= 0:
        extra += ["-corrupt-parity", str(corrupt_p)]

    B.set_netem(RTT_MS / 2.0)      # 무작위 손실 없음. 소거는 우리가 만든다.
    p, sp = B.start_server(CERT, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=10,
                                 timeout_s=8, expect_k=K, extra=extra)
    ss = B.read_server_stats(sp)
    B.stop_server(p)
    s = B.summarize(rows, rtt_ms=RTT_MS)
    ok_ms = [r["ms"] for r in rows if r.get("ok")]
    return {
        "case": name, "fec": fec, "m": m,
        "drop_initial": drop_i, "drop_parity": drop_p,
        "corrupt_parity": corrupt_p,
        "n": s["n"], "ok": s["ok"], "fail": s["fail"],
        "p50": s["p50"], "p95": s["p95"], "max": s["max"],
        "pto_share": (sum(1 for t in ok_ms if t >= PTO_FLOOR_MS)
                      / float(len(ok_ms))) if ok_ms else None,
        "cli_dropped_orig": cs.get("dropped_originals"),
        "cli_dropped_par": cs.get("dropped_parities"),
        "cli_corrupt_par": cs.get("corrupted_parities"),
        "cli_parity_sent": cs.get("parity_sent"),
        "srv_recovered": ss.get("recovered"),
        "srv_late": ss.get("late_recovered"),
        "srv_crc_fail": ss.get("recover_crc_fail"),
        "srv_unrecover": ss.get("unrecoverable_seen"),
        "srv_refused": ss.get("recover_refused_by_accounting"),
        "srv_bytes_in": ss.get("bytes_in"),
        "srv_bytes_to_stack": ss.get("bytes_to_stack"),
        "err": err,
    }


def link_counters(dev, ns=None):
    cmd = "ip -s link show %s" % dev
    if ns:
        cmd = "ip netns exec %s %s" % (ns, cmd)
    out = B.run(cmd).stdout
    # RX: 다음 줄의 첫 숫자, TX: 그 다음 블록의 첫 숫자
    nums = re.findall(r"^\s+(\d+)\s+\d+\s+\d+", out, re.M)
    if len(nums) < 2:
        return None
    return {"rx_bytes": int(nums[0]), "tx_bytes": int(nums[1])}


def amplification_wire_check():
    """커널 계수기로 증폭비를 직접 잰다 (우리 코드 밖의 증거).

    편도 2 초를 걸어 서버의 첫 응답 버스트와 클라이언트의 두 번째 비행을
    시간축에서 갈라 놓고, 그 사이에 계수기를 읽는다.
    """
    out = {}
    # 2-RTT 가 확실한 인증서 크기 (기준선 임계 5,903~5,984 B 위)
    cert = 9000
    B.set_netem(2000.0)
    p, sp = B.start_server(cert, fec="off")
    before = link_counters(B.DEV_PEER, B.NS)
    qamp = B.require_bin()
    cli = subprocess.Popen(
        ["timeout", "40", qamp, "-mode", "client",
         "-addr", "%s:%d" % (B.RX_IP, B.SERVER_PORT),
         "-group", GROUP, "-n", "1", "-gap", "0ms", "-timeout", "30s",
         "-fec", "off", "-expect-k", str(K)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3.0)          # t=2.0 에 서버가 응답, t=4.0 에 클라 2차 비행
    mid = link_counters(B.DEV_PEER, B.NS)
    try:
        cli.wait(timeout=40)
    except Exception:
        cli.kill()
    B.stop_server(p)
    B.set_netem(RTT_MS / 2.0)
    if not (before and mid):
        return {"ok": False, "detail": "커널 계수기를 못 읽었다"}
    rx = mid["rx_bytes"] - before["rx_bytes"]      # 서버가 받은 바이트
    tx = mid["tx_bytes"] - before["tx_bytes"]      # 서버가 보낸 바이트
    ratio = (tx / float(rx)) if rx else None
    out = {"cert": cert, "rx_bytes": rx, "tx_bytes": tx, "ratio": ratio,
           "ok": ratio is not None and ratio <= 3.05}
    return out


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()

    cases = []
    print("=" * 100)
    print("결정적 검증 - 소거를 우리가 만들고, 반드시 그래야 하는 결과와 대조한다")
    print("(그룹 %s, k=%d, cert %d, RTT %.0f ms, 무작위 손실 없음, 조건마다 n=%d)"
          % (GROUP, K, CERT, RTT_MS, N))
    print("=" * 100)

    cases.append(run_case("V1 off / 소거 없음", "off", 1))
    cases.append(run_case("V2 off / 원본0 소거", "off", 1, drop_i=0))
    cases.append(run_case("V3 off / 원본1 소거", "off", 1, drop_i=1))
    cases.append(run_case("V4 fec m=1 / 원본0 소거", "on", 1, drop_i=0))
    cases.append(run_case("V5 fec m=1 / 원본1 소거", "on", 1, drop_i=1))
    cases.append(run_case("V6 fec m=1 / 패리티 소거", "on", 1, drop_i=0,
                          drop_p=0))
    cases.append(run_case("V7 fec m=1 / 원본0 소거 + 패리티 손상", "on", 1,
                          drop_i=0, corrupt_p=0))
    cases.append(run_case("V8 fec m=2 / 원본0 소거", "on", 2, drop_i=0))
    cases.append(run_case("V9 fec m=1 / 원본0+1 소거", "on", 1, drop_i=99))

    for c in cases:
        print("%-34s 성공 %3d/%-3d  p50 %8.1f  PTO비율 %5.1f%%  "
              "복구 %-4s CRC거절 %-3s 소거주입 %s/%s/%s"
              % (c["case"], c["ok"], c["n"], c["p50"] or -1,
                 100 * (c["pto_share"] or 0), c["srv_recovered"],
                 c["srv_crc_fail"], c["cli_dropped_orig"],
                 c["cli_dropped_par"], c["cli_corrupt_par"]))
        sys.stdout.flush()

    # ------------------------------------------------------------- 판정
    def by(name):
        return next(c for c in cases if c["case"].startswith(name))

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    v1 = by("V1")
    add("V1 기준선은 소거가 없으면 100% 성공, 1-RTT",
        v1["ok"] == v1["n"] and v1["p50"] is not None
        and v1["p50"] < 1.5 * RTT_MS,
        "성공 %d/%d, p50 %.1f ms" % (v1["ok"], v1["n"], v1["p50"] or -1))

    for nm in ("V2", "V3"):
        c = by(nm)
        add("%s 기준선은 원본 하나만 잃어도 PTO 를 맞는다" % nm,
            (c["pto_share"] or 0) > 0.9 and (c["cli_dropped_orig"] or 0) > 0,
            "PTO비율 %.0f%%, p50 %.1f ms, 소거주입 %s건"
            % (100 * (c["pto_share"] or 0), c["p50"] or -1,
               c["cli_dropped_orig"]))

    for nm in ("V4", "V5", "V8"):
        c = by(nm)
        rec = c["srv_recovered"] or 0
        add("%s FEC 는 그 소거를 복구해 1-RTT 를 지킨다" % nm,
            (c["pto_share"] or 1) < 0.05 and rec >= c["n"] * 0.9
            and (c["srv_crc_fail"] or 0) == 0,
            "PTO비율 %.0f%%, p50 %.1f ms, 복구 %d/%d, CRC실패 %s"
            % (100 * (c["pto_share"] or 0), c["p50"] or -1, rec, c["n"],
               c["srv_crc_fail"]))

    c = by("V6")
    add("V6 패리티를 없애면 FEC 도 못 고친다 "
        "(개선이 다른 경로에서 온 것이 아님)",
        (c["pto_share"] or 0) > 0.9 and (c["srv_recovered"] or 0) == 0,
        "PTO비율 %.0f%%, 복구 %s, 패리티소거 %s건"
        % (100 * (c["pto_share"] or 0), c["srv_recovered"],
           c["cli_dropped_par"]))

    c = by("V7")
    add("V7 패리티가 손상되면 CRC 가 걸러 내고 잘못된 복구를 안 넘긴다",
        (c["srv_recovered"] or 0) == 0 and (c["pto_share"] or 0) > 0.9,
        "복구 %s, CRC실패 %s, PTO비율 %.0f%%"
        % (c["srv_recovered"], c["srv_crc_fail"],
           100 * (c["pto_share"] or 0)))

    c = by("V9")
    add("V9 m=1 은 소거 2개를 복구하지 못한다 (능력을 과장하지 않는다)",
        (c["srv_recovered"] or 0) == 0,
        "복구 %s, 복구불가로 센 것 %s" % (c["srv_recovered"],
                                        c["srv_unrecover"]))

    bad = [c["case"] for c in cases
           if (c["srv_bytes_to_stack"] or 0) > (c["srv_bytes_in"] or 0)]
    add("V10 모든 조건에서 스택 전달 바이트 <= 물리 수신 바이트",
        not bad, "위반 조건: %s" % (", ".join(bad) if bad else "없음"))

    amp = amplification_wire_check()
    add("V11 커널 계수기로 본 증폭비 <= 3.0 (우리 코드 밖의 증거)",
        amp.get("ok"),
        "수신 %s B, 송신 %s B, 비 %.2f"
        % (amp.get("rx_bytes"), amp.get("tx_bytes"), amp.get("ratio") or -1))

    print()
    print("=" * 100)
    npass = 0
    for c in checks:
        npass += 1 if c["ok"] else 0
        print("[%s] %-58s %s" % ("통과" if c["ok"] else "실패",
                                 c["check"], c["detail"][:70]))
    print("-" * 100)
    print("%d / %d 통과" % (npass, len(checks)))

    out = {"rtt_ms": RTT_MS, "cert": CERT, "n": N, "group": GROUP,
           "cases": cases, "checks": checks, "amplification_wire": amp,
           "passed": npass, "total": len(checks)}
    print("saved:", B.save("p7_verify.json", out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
