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
N = 40
GROUP = "X25519MLKEM768"
K = 2
PTO_FLOOR_MS = 900.0   # RFC 9002 초기 PTO 는 약 999 ms


def run_case(name, fec, m, drop_i="", drop_p=-1, corrupt_p=-1, n=N):
    extra = []
    if drop_i:
        extra += ["-drop-initial", drop_i]
    if drop_p >= 0:
        extra += ["-drop-parity", str(drop_p)]
    if corrupt_p >= 0:
        extra += ["-corrupt-parity", str(corrupt_p)]

    B.set_netem(RTT_MS / 2.0)      # 무작위 손실 없음. 소거는 우리가 만든다.
    p, sp = B.start_server(CERT, fec=("on" if fec == "on" else fec))
    rows, cs, err = B.run_client(GROUP, n, fec=fec, m=m, gap_ms=10,
                                 timeout_s=8, expect_k=K, extra=extra)
    # 🩸 순서가 중요하다. 서버는 종료 신호를 받을 때 통계를 마지막으로
    # 기록하므로, **먼저 죽이고 나서 읽어야** 마지막 시행들이 반영된다.
    # 반대로 하면 복구 건수가 실제보다 적게 보고된다(40회 중 39회로 나왔다).
    B.stop_server(p)
    ss = B.read_server_stats(sp)
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


def amplification_wire_check(fec="off", m=1):
    """커널 계수기로 증폭비를 직접 잰다 (우리 코드 밖의 증거).

    편도 2 초를 걸어 서버의 첫 응답 버스트와 클라이언트의 두 번째 비행을
    시간축에서 갈라 놓고, 그 사이에 계수기를 읽는다.
    """
    out = {}
    # 2-RTT 가 확실한 인증서 크기 (기준선 임계 5,903~5,984 B 위)
    cert = 9000
    # 🩸 편도 지연을 PTO(약 999 ms)보다 **짧게** 잡아야 한다. 처음에 편도
    # 2 초를 썼더니 왕복이 4 초라 그 사이 클라이언트 PTO 가 두 번 터져
    # 첫 비행이 세 번 전송됐고, 수신 바이트가 2,560 이 아니라 10,576 로
    # 불어나 표본이 무의미해졌다. 편도 400 ms 면 왕복 800 ms < PTO 라
    # 재전송 없이 단계가 갈라진다.
    #    t=0.4  클라 비행이 v1 에 도착      (RX 증가)
    #    t=0.8  서버 버스트가 v1 을 떠남    (TX 증가)
    #    t=1.2  클라 2차 비행 도착
    ONE_WAY_MS = 400.0
    B.set_netem(ONE_WAY_MS)
    p, sp = B.start_server(cert, fec="off")
    base = link_counters(B.DEV_PEER, B.NS)
    qamp = B.require_bin()
    t0 = time.time()
    cli = subprocess.Popen(
        ["timeout", "40", qamp, "-mode", "client",
         "-addr", "%s:%d" % (B.RX_IP, B.SERVER_PORT),
         "-group", GROUP, "-n", "1", "-gap", "0ms", "-timeout", "30s",
         "-fec", fec, "-m", str(m), "-expect-k", str(K)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 🩸 한 시점만 찍으면 그 시점이 맞는지 알 수 없다. 두 번 틀린 뒤
    # (편도 2 초 -> 송신 0, 편도 0.4 초 -> 재전송 혼입) 타임라인으로 바꿨다.
    # 100 ms 마다 커널 계수기를 읽고, **클라이언트가 첫 비행만 보낸 동안**
    # 서버가 얼마나 내보냈는지를 그 수열에서 직접 고른다.
    timeline = []
    for _ in range(25):
        time.sleep(0.1)
        c = link_counters(B.DEV_PEER, B.NS)
        if not (c and base):
            continue
        timeline.append({"t": round(time.time() - t0, 2),
                         "rx": c["rx_bytes"] - base["rx_bytes"],
                         "tx": c["tx_bytes"] - base["tx_bytes"]})
    try:
        cli.wait(timeout=40)
    except Exception:
        cli.kill()
    B.stop_server(p)
    B.set_netem(RTT_MS / 2.0)

    # 🩸 한 시점을 골라 "그때가 첫 버스트다" 라고 주장하는 것은 두 번 틀렸다.
    # 위상을 분리하려 애쓰는 대신 **모든 시점에서 불변식을 본다.**
    # RFC 9000 8.1 이 요구하는 것은 정확히 이것이다:
    #     서버 누적 송신 <= 3 x 서버 누적 수신
    # 커널 계수기는 이더넷 프레임을 세므로 양쪽에 같은 42 B/패킷 머리가
    # 붙어 비율에는 거의 영향이 없다.
    worst = None
    for x in timeline:
        if x["rx"] <= 0:
            continue
        r = x["tx"] / float(x["rx"])
        if worst is None or r > worst["ratio"]:
            worst = {"t": x["t"], "rx": x["rx"], "tx": x["tx"], "ratio": r}
    if worst is None:
        return {"cert": cert, "fec": fec, "m": m, "timeline": timeline,
                "ok": False, "detail": "커널 계수기에서 트래픽을 못 봤다"}
    return {"cert": cert, "fec": fec, "m": m, "one_way_ms": ONE_WAY_MS,
            "timeline": timeline, "worst": worst,
            "max_ratio": worst["ratio"], "ok": worst["ratio"] <= 3.0}


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

    # 🩸 V0 은 규모를 키운 무손실 검사다. 이게 없어서 "손실 0 인데 복구
    # 352 건" 이라는 결함을 n=200 까지 키우고 나서야 발견했다. n<=60 에서는
    # 아무것도 만료되지 않아 깨끗해 보인다 - 규모가 곧 시험 조건이다.
    cases.append(run_case("V0 fec m=1 / 소거 없음 / 규모 n=200", "on", 1,
                          n=200))
    cases.append(run_case("V1 off / 소거 없음", "off", 1))
    cases.append(run_case("V2 off / 원본0 소거", "off", 1, drop_i="0"))
    cases.append(run_case("V3 off / 원본1 소거", "off", 1, drop_i="1"))
    cases.append(run_case("V4 fec m=1 / 원본0 소거", "on", 1, drop_i="0"))
    cases.append(run_case("V5 fec m=1 / 원본1 소거", "on", 1, drop_i="1"))
    cases.append(run_case("V6 fec m=1 / 패리티 소거", "on", 1, drop_i="0",
                          drop_p=0))
    cases.append(run_case("V7 fec m=1 / 원본0 소거 + 패리티 손상", "on", 1,
                          drop_i="0", corrupt_p=0))
    cases.append(run_case("V8 fec m=2 / 원본0 소거", "on", 2, drop_i="0"))
    cases.append(run_case("V9 fec m=1 / 원본0+1 소거", "on", 1, drop_i="0,1"))

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

    ONE_RTT = 1.5 * RTT_MS      # 이보다 작으면 왕복 한 번

    v0 = by("V0")
    add("V0 손실이 0 이면 규모를 키워도 복구가 0 이어야 한다 "
        "(유령 복구 금지)",
        (v0["srv_recovered"] or 0) == 0 and (v0["srv_late"] or 0) == 0
        and (v0["srv_crc_fail"] or 0) == 0 and v0["ok"] == v0["n"],
        "n=%d 성공 %d, 복구 %s, 늦은복구 %s, CRC거절 %s"
        % (v0["n"], v0["ok"], v0["srv_recovered"], v0["srv_late"],
           v0["srv_crc_fail"]))

    v1 = by("V1")
    add("V1 기준선은 소거가 없으면 100% 성공, 모든 시행이 1-RTT",
        v1["ok"] == v1["n"] and (v1["max"] or 1e9) < ONE_RTT,
        "성공 %d/%d, p50 %.1f ms, 최대 %.1f ms"
        % (v1["ok"], v1["n"], v1["p50"] or -1, v1["max"] or -1))

    # 🩸 처음에는 "원본 하나를 잃으면 PTO(약 999 ms)" 를 기대했는데 틀렸다.
    # 서버가 받은 것에 ACK 를 보내므로 클라이언트는 패킷번호 구멍으로 손실을
    # 알아채고 곧바로 재전송한다. 그래서 대가는 PTO 가 아니라 **왕복 추가**다.
    # 예상이 아니라 관측에 맞춘다 - 인수인계 문서 8절의 지침 그대로.
    for nm in ("V2", "V3"):
        c = by(nm)
        add("%s 기준선은 원본 하나만 잃어도 왕복을 더 쓴다" % nm,
            (c["p50"] or 0) >= ONE_RTT and (c["cli_dropped_orig"] or 0) > 0,
            "p50 %.1f ms (= %.1f RTT), 소거주입 %s건"
            % (c["p50"] or -1, (c["p50"] or 0) / RTT_MS,
               c["cli_dropped_orig"]))

    for nm in ("V4", "V5", "V8"):
        c = by(nm)
        rec = (c["srv_recovered"] or 0) + (c["srv_late"] or 0)
        add("%s FEC 는 그 소거를 복구해 **모든 시행**이 1-RTT" % nm,
            (c["max"] or 1e9) < ONE_RTT and rec >= c["n"]
            and (c["srv_crc_fail"] or 0) == 0,
            "최대 %.1f ms, 복구 %d/%d, CRC실패 %s"
            % (c["max"] or -1, rec, c["n"], c["srv_crc_fail"]))

    c = by("V6")
    add("V6 패리티를 없애면 FEC 도 못 고치고 기준선으로 돌아간다 "
        "(개선이 다른 경로에서 온 것이 아님)",
        (c["p50"] or 0) >= ONE_RTT and (c["srv_recovered"] or 0) == 0,
        "p50 %.1f ms, 복구 %s, 패리티소거 %s건"
        % (c["p50"] or -1, c["srv_recovered"], c["cli_dropped_par"]))

    c = by("V7")
    add("V7 패리티가 손상되면 CRC 가 걸러 내고 잘못된 복구를 안 넘긴다",
        (c["srv_recovered"] or 0) == 0 and (c["srv_crc_fail"] or 0) > 0
        and (c["p50"] or 0) >= ONE_RTT,
        "복구 %s, CRC거절 %s, p50 %.1f ms"
        % (c["srv_recovered"], c["srv_crc_fail"], c["p50"] or -1))

    c = by("V9")
    add("V9 m=1 은 소거 2개를 복구하지 못한다 (능력을 과장하지 않는다)",
        (c["srv_recovered"] or 0) == 0 and (c["cli_dropped_orig"] or 0) > 0
        and (c["p50"] or 0) >= ONE_RTT,
        "복구 %s, 소거주입 %s건, p50 %.1f ms"
        % (c["srv_recovered"], c["cli_dropped_orig"], c["p50"] or -1))

    bad = [c["case"] for c in cases
           if (c["srv_bytes_to_stack"] or 0) > (c["srv_bytes_in"] or 0)]
    add("V10 모든 조건에서 스택 전달 바이트 <= 물리 수신 바이트",
        not bad, "위반 조건: %s" % (", ".join(bad) if bad else "없음"))

    # FEC 를 켠 쪽도 반드시 본다. 우리 패리티가 예산을 부풀려 증폭 방어를
    # 깨뜨리는 것이 아닌지가 이 설계의 가장 큰 위험이기 때문이다.
    amp_off = amplification_wire_check("off", 1)
    amp_on = amplification_wire_check("on", 2)
    for nm, a in (("off", amp_off), ("fec m=2", amp_on)):
        w = a.get("worst") or {}
        add("V11 커널 계수기: %s 팔에서 **모든 시점** 서버송신 <= 3 x 서버수신"
            % nm, a.get("ok"),
            "최악 t=%.2fs 수신 %s B 송신 %s B 비 %.2f (한계 3.00)"
            % (w.get("t", -1), w.get("rx"), w.get("tx"),
               a.get("max_ratio") or -1))
    amp = {"off": amp_off, "fec_m2": amp_on}

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
