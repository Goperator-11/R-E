# -*- coding: utf-8 -*-
"""P0 - 인수인계 문서의 환경을 그대로 세우고, 문서 단계 0 을 그대로 확인한다.

문서 4절 단계 0
    go version                    # go1.26.5 확인
    CGO_ENABLED=0 go build -o qamp qamp.go && echo OK
    ./qamp -mode server -addr 127.0.0.1:44433 -group X25519 -certsize 3000 &
    sleep 1
    ./qamp -mode client -addr 127.0.0.1:44433 -group X25519 -n 5

문서 5절 환경
    unshare -Urnm / netns peer / veth v0,v1 / 10.9.0.1,2 / MTU 1500 /
    netem 양쪽 절반 / /tmp/qamp

문서 6절 함정 - 여기서 미리 걸러 낸다
    * MTU 변경이 loopback 에서는 조용히 무시된다 -> veth 로 눈으로 확인
    * veth 양끝이 다른 네임스페이스에 있어야 한다 -> 확인
    * pkill -f 는 부모 셸까지 죽인다 -> PID 로만 종료
    * 잔존 서버 프로세스가 결과를 오염시킨다 -> 시작 전 확인
    * 모든 실행에 timeout

ML-KEM 동일성
    "ML-KEM 도 똑같이 구현" 을 말로 두지 않고 두 가지로 보인다.
      크기   X25519MLKEM768 키셰어 = 32 + 1184 = 1216 B (FIPS 203)
      상호운용  Go crypto/tls <-> OpenSSL 3.5 가 실제로 핸드셰이크를 끝내는가

Output: experiments/results/p0_env.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                      # noqa: E402
import e4_quic_decrypt as E4            # noqa: E402

DOC_GO = "go1.26"          # 문서는 go1.26.5. 접두만 확인한다.
DOC_PORT = 44433
DOC_CERT = 3000


def sh(cmd, timeout=120):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def check(results, name, ok, detail=""):
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    print("[%s] %-52s %s" % ("통과" if ok else "실패", name, detail[:80]))
    sys.stdout.flush()


def key_share_sizes(dump_path):
    """떠 놓은 첫 비행에서 ClientHello 의 key_share 확장 크기를 읽는다."""
    with open(dump_path, "rb") as f:
        blob = f.read()
    dgrams, i = [], 0
    while i + 2 <= len(blob):
        ln = int.from_bytes(blob[i:i + 2], "big")
        i += 2
        if i + ln > len(blob):
            break
        dgrams.append(blob[i:i + ln])
        i += ln
    if not dgrams:
        return None
    first = list(E4.iter_long_packets(dgrams[0]))
    if not first:
        return None
    dcid = first[0][4]
    keys = E4.initial_keys(bytes(dcid))["client"]
    chunks = {}
    for d in dgrams:
        for kind, st, pn_off, end, _dc, _sc in E4.iter_long_packets(d):
            if kind != "Initial" or pn_off is None:
                continue
            pt, _pn, _b0 = E4.decrypt_initial(d, st, pn_off, end, keys)
            if pt is None:
                continue
            for fr in E4.parse_frames(pt):
                if fr.get("type") == "CRYPTO":
                    chunks[fr["offset"]] = fr["data"]
    if not chunks:
        return None
    msg = b""
    for off in sorted(chunks):
        if off != len(msg):
            return None
        msg += chunks[off]
    ch = E4.parse_client_hello(msg)
    out = {"clienthello_bytes": len(msg), "key_shares": []}
    for ext in ch.get("extensions", []):
        if ext.get("type") == 51:      # key_share
            out["key_share_ext_len"] = ext.get("len")
    # key_share 안의 개별 항목을 직접 뜯는다 (그룹별 길이가 필요하다)
    out["key_shares"] = _parse_key_share(msg)
    return out


def _parse_key_share(msg):
    """ClientHello 원문에서 key_share 항목 (group, len) 목록을 뽑는다."""
    # msg = handshake header(4) + body
    i = 4
    i += 2 + 32                                   # version + random
    sid = msg[i]; i += 1 + sid                    # legacy_session_id
    cs = int.from_bytes(msg[i:i + 2], "big"); i += 2 + cs
    cm = msg[i]; i += 1 + cm
    ext_total = int.from_bytes(msg[i:i + 2], "big"); i += 2
    end = i + ext_total
    out = []
    while i + 4 <= end:
        et = int.from_bytes(msg[i:i + 2], "big")
        el = int.from_bytes(msg[i + 2:i + 4], "big")
        body = msg[i + 4:i + 4 + el]
        i += 4 + el
        if et != 51:
            continue
        j = 2                                     # client_shares length
        while j + 4 <= len(body):
            grp = int.from_bytes(body[j:j + 2], "big")
            kl = int.from_bytes(body[j + 2:j + 4], "big")
            out.append({"group": grp, "key_bytes": kl})
            j += 4 + kl
    return out


def loopback_stage0():
    """Bounded READY wait and client run; always stop this server by PID."""
    rows, ready, returncode, error = [], False, None, ""
    with tempfile.TemporaryDirectory(prefix="padfec_p0_") as directory:
        stderr_path = os.path.join(directory, "server.stderr")
        with open(stderr_path, "wb") as stream:
            srv = subprocess.Popen(
                [B.QAMP, "-mode", "server", "-addr", "127.0.0.1:%d" % DOC_PORT,
                 "-certsize", str(DOC_CERT), "-fec", "off"],
                stdout=subprocess.DEVNULL, stderr=stream)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                with open(stderr_path, "rb") as stream:
                    ready = b"READY" in stream.read()
                if ready or srv.poll() is not None:
                    break
                time.sleep(.05)
            ready = ready and srv.poll() is None
            if ready:
                result = subprocess.run(
                    ["timeout", "60", B.QAMP, "-mode", "client",
                     "-addr", "127.0.0.1:%d" % DOC_PORT, "-group", "X25519",
                     "-n", "5", "-gap", "20ms", "-timeout", "10s"],
                    capture_output=True, text=True, timeout=90)
                returncode = result.returncode
                for line in result.stdout.splitlines():
                    if line.strip().startswith("{"):
                        rows.append(json.loads(line))
                if returncode:
                    error = "client exit %d: %s" % (returncode, result.stderr[-300:])
            else:
                error = "server did not become ready within 15 seconds"
        except (subprocess.TimeoutExpired, ValueError) as exc:
            error = str(exc)
        finally:
            B.stop_server(srv)
    successful = sum(1 for row in rows if row.get("ok"))
    info = {"ready": ready, "trials": len(rows), "ok": successful,
            "client_returncode": returncode, "error": error,
            "kem_ids": sorted({x.get("kem_id") for x in rows if x.get("kem_id") is not None})}
    return ready and not error and returncode == 0 and successful == len(rows) == 5, info


def main():
    B.harden()
    B.require_root()
    results = []
    info = {}

    # ------------------------------------------------------------ 도구 버전
    rc, out = sh("export PATH=\"$HOME/goroot/bin:$PATH\"; go version")
    info["go_version"] = out.strip()
    check(results, "Go 툴체인 (문서: go1.26.5)", rc == 0 and DOC_GO in out, out.strip())

    rc, out = sh("openssl version")
    info["openssl_version"] = out.strip()
    check(results, "OpenSSL (문서 환경: 3.5)", rc == 0 and "3.5" in out, out.strip())

    rc, out = sh("ls -la /tmp/qamp 2>&1 || true")
    B.require_bin()
    check(results, "문서 5절대로 /tmp/qamp 로 복사되어 있다",
          os.path.exists(B.QAMP), B.QAMP)

    # -------------------------------------------- 문서 5절 환경 (netns/veth)
    B.setup(mtu=1500)
    rc, out = sh("ip netns list")
    check(results, "네임스페이스 peer 생성", B.NS in out, out.strip())
    rc, out = sh("ip link show %s" % B.DEV_LOCAL)
    check(results, "veth v0 가 루트에 MTU 1500 으로 올라옴",
          "mtu 1500" in out and "UP" in out, out.split("\n")[0][:70])
    rc, out = sh("ip netns exec %s ip link show %s" % (B.NS, B.DEV_PEER))
    check(results, "veth v1 이 peer 안에 MTU 1500 으로 올라옴",
          "mtu 1500" in out and "UP" in out, out.split("\n")[0][:70])
    rc, out = sh("ip link show")
    check(results, "v1 이 루트 네임스페이스에 남아 있지 않다 "
                   "(같으면 커널이 loopback 으로 우회)",
          B.DEV_PEER not in out, "")

    B.set_netem(25.0)
    rc, out = sh("tc qdisc show dev %s" % B.DEV_LOCAL)
    ok = "netem" in out and "delay 25ms" in out
    check(results, "netem 이 v0 에 delay 25ms 로 걸림", ok, out.strip()[:70])
    rc, out2 = sh("ip netns exec %s tc qdisc show dev %s"
                  % (B.NS, B.DEV_PEER))
    ok2 = "netem" in out2 and "delay 25ms" in out2
    check(results, "netem 이 v1 에도 걸림 (양쪽 절반이라야 대칭 지연)",
          ok2, out2.strip()[:70])

    # ------------------------------------------------- 문서 단계 0 (loopback)
    # 문서 4절 그대로: 127.0.0.1:44433, X25519, certsize 3000, n=5.
    # 종료는 PID 로만 한다 (문서 6절: pkill -f 는 부모 셸까지 죽인다).
    ok, info["stage0"] = loopback_stage0()
    check(results, "문서 단계 0: 서버 기동 + 클라이언트 5회 성공", ok,
          "성공 %d/5, group_id %s"
          % (info["stage0"]["ok"], info["stage0"]["kem_ids"]))

    # -------------------------------------------------- ML-KEM 동일성 (크기)
    dump = os.path.join(B.WORK, "p0_flight_mlkem.bin")
    try:
        os.unlink(dump)
    except OSError:
        pass
    p, sp = B.start_server(DOC_CERT, fec="off")
    rows, cs, err = B.run_client("X25519MLKEM768", 3, fec="off", gap_ms=20,
                                 dump=dump)
    B.stop_server(p)
    ks = key_share_sizes(dump) if os.path.exists(dump) else None
    info["key_share"] = ks
    got = {e["group"]: e["key_bytes"] for e in (ks or {}).get("key_shares", [])}
    # 0x11EC = 4588 = X25519MLKEM768.  32(X25519) + 1184(ML-KEM-768 ek) = 1216
    complete = not err and len(rows) == 3 and all(x.get("ok") for x in rows)
    ok = complete and got.get(4588) == 1216
    check(results, "ClientHello key_share: X25519MLKEM768 = 1216 B "
                   "(= 32 + ML-KEM-768 캡슐화키 1184, FIPS 203)",
          ok, "실측 %s" % got)
    kem_ids = sorted(set(x.get("kem_id") for x in rows if x.get("ok")))
    info["negotiated_group_ids"] = kem_ids
    check(results, "QUIC 핸드셰이크에서 실제로 X25519MLKEM768(4588) 합의",
          complete and kem_ids == [4588], str(kem_ids))

    # ---------------------------------------------- ML-KEM 동일성 (상호운용)
    rc, out = sh("sed 's/\\r$//' %s/quicbed/mlkem_interop.sh > "
                 "/tmp/mlkem_interop.sh && bash /tmp/mlkem_interop.sh"
                 % HERE.replace("\\", "/"), timeout=240)
    info["interop_output"] = out[-1500:]
    ok_pq = rc == 0 and '"group":"X25519MLKEM768"' in out and '"ok":true' in out
    check(results, "상호운용: Go crypto/tls <-> OpenSSL 3.5 가 "
                   "X25519MLKEM768 로 핸드셰이크 완료", ok_pq,
          "두 독립 구현이 같은 공유비밀에 도달했다는 뜻")
    ok_size = rc == 0 and "캡슐화키 1184 B 포함 여부: 예" in out
    check(results, "OpenSSL ML-KEM-768 캡슐화키 1184 B (FIPS 203)", ok_size,
          "")

    npass = sum(1 for r in results if r["ok"])
    print()
    print("%d / %d 통과" % (npass, len(results)))
    out = {"results": results, "info": info,
           "passed": npass, "total": len(results)}
    print("saved:", B.save("p0_env.json", out))
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
