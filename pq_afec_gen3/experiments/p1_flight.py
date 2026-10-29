# -*- coding: utf-8 -*-
"""P1 - 클라이언트 첫 비행의 구조를 실측한다.

이 단계가 정하는 값들이 뒤의 모든 계산에 들어간다.

    k   첫 비행의 데이터그램 수     -> 증폭 예산 = 3 x (k x W)
    C   ClientHello 실내용 바이트   -> 용량 정리의 좌변
    h   패킷당 고정 비용            -> 용량 정리의 우변
    pad 버려지는 PADDING 바이트     -> 인수인계 문서 1-4 의 전제

**추정하지 않는다.** 클라이언트가 실제로 내보낸 첫 비행 데이터그램을 그대로
떠서(-dump-flight), RFC 9001 5.2 의 Initial 키로 복호해 프레임 단위로 센다.
Initial 키는 클라이언트가 고른 DCID 와 공개된 소금에서 유도되므로, 지나가던
관측자도 읽을 수 있다 - 우리가 클라이언트이니 더 말할 것도 없다.

인수인계 문서 1-3 의 결정적 실험(패딩만 늘려도 임계가 이동)을 재현하기 위해
InitialPacketSize 도 함께 훑는다.

Output: experiments/results/p1_flight.json
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                      # noqa: E402
import e4_quic_decrypt as E4            # noqa: E402
from padfec import capacity             # noqa: E402
from _journal import Journal, code_fingerprint  # noqa: E402

GROUPS = ["x25519", "secp256r1", "X25519MLKEM768"]
IPS_LIST = [0, 1200, 1350, 1450]        # 0 = quic-go 기본값(1280)
RTT_MS = 50.0
N = 10


def analyse_dump(path):
    """떠 놓은 첫 비행을 복호해 CRYPTO/PADDING 바이트를 센다."""
    with open(path, "rb") as f:
        blob = f.read()
    dgrams = []
    i = 0
    while i + 2 <= len(blob):
        ln = int.from_bytes(blob[i:i + 2], "big")
        i += 2
        if i + ln > len(blob):
            break
        dgrams.append(blob[i:i + ln])
        i += ln
    if not dgrams:
        return None

    # 첫 패킷의 DCID 가 이 연결의 original DCID 다.
    first = list(E4.iter_long_packets(dgrams[0]))
    if not first:
        return None
    _kind, _st, _pn, _end, dcid, _scid = first[0]
    keys = E4.initial_keys(bytes(dcid))["client"]

    out = {"k": len(dgrams), "datagrams": [], "crypto_total": 0,
           "padding_total": 0, "wire_total": 0, "overhead_total": 0}
    for d in dgrams:
        out["wire_total"] += len(d)
        rec = {"udp_bytes": len(d), "crypto": 0, "padding": 0,
               "other": 0, "packets": 0}
        for kind, st, pn_off, end, _dc, _sc in E4.iter_long_packets(d):
            if kind != "Initial" or pn_off is None:
                continue
            rec["packets"] += 1
            pt, _pn, _b0 = E4.decrypt_initial(d, st, pn_off, end, keys)
            if pt is None:
                continue
            for fr in E4.parse_frames(pt):
                name = fr.get("type")
                if name == "PADDING":
                    # e4 는 PADDING 을 "bytes" 로, CRYPTO 를 "length" 로 준다
                    rec["padding"] += fr.get("bytes", 0)
                elif name == "CRYPTO":
                    rec["crypto"] += fr.get("length", 0)
                else:
                    rec["other"] = rec.get("other", 0) + 1
        # 고정 비용 h = 와이어 - CRYPTO 데이터 - PADDING.
        # 롱헤더, 패킷번호, AEAD 태그, CRYPTO 프레임 머리가 전부 여기 든다.
        # 첫 비행에는 ACK/PING 이 없으므로 이 뺄셈이 곧 h 다(있으면 other 로 샌다).
        rec["overhead"] = rec["udp_bytes"] - rec["crypto"] - rec["padding"]
        out["crypto_total"] += rec["crypto"]
        out["padding_total"] += rec["padding"]
        out["overhead_total"] += rec["overhead"]
        out["datagrams"].append(rec)
    out["h_measured"] = (float(out["overhead_total"]) / len(dgrams)
                         if dgrams else None)
    return out


def main():
    B.harden()
    B.require_root()
    B.require_bin()
    B.setup()
    B.set_netem(RTT_MS / 2.0)

    fp = code_fingerprint(["experiments/p1_flight.py",
                           "experiments/quicbed/qamp.go",
                           "experiments/padbed.py"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p1_units.jsonl"), fp)

    runs = []
    for group in GROUPS:
        for ips in IPS_LIST:
            key = "%s|ips%d" % (group, ips)
            if jr.has(key):
                runs.append(jr.get(key))
                print("건너뜀(기록됨):", key)
                continue
            dump = os.path.join(B.WORK, "flight_%s_%d.bin" % (group, ips))
            try:
                os.unlink(dump)
            except OSError:
                pass
            p, sp = B.start_server(2955, fec="off")
            rows, cs, err = B.run_client(group, N, fec="off", ips=ips,
                                         gap_ms=20, dump=dump)
            B.stop_server(p)
            s = B.summarize(rows, rtt_ms=RTT_MS)
            det = analyse_dump(dump) if os.path.exists(dump) else None
            rec = {"group": group, "ips": ips, "n": s["n"], "ok": s["ok"],
                   "p50_ms": s["p50"], "kem_ids": s.get("kem_ids"),
                   "first_flight_datagrams": cs.get("first_flight_datagrams"),
                   "first_flight_bytes": cs.get("first_flight_bytes"),
                   "decoded": det}
            # 자체 점검: 손실이 없는데 실패한 시행이 있으면 그 자체가 결함이다
            rec["valid"] = (s["ok"] == s["n"] and det is not None
                            and det["k"] == cs.get("first_flight_datagrams"))
            if rec["valid"]:
                jr.record(key, rec)
            runs.append(rec)
            print("%-16s ips=%-5s k=%s  와이어=%s B  CRYPTO=%s  PADDING=%s  "
                  "h=%.0f  ok=%d/%d%s"
                  % (group, ips or "기본", rec["first_flight_datagrams"],
                     rec["first_flight_bytes"],
                     det["crypto_total"] if det else "?",
                     det["padding_total"] if det else "?",
                     det["h_measured"] if det else -1,
                     s["ok"], s["n"], "" if rec["valid"] else "  <-- 무효"))

    # ---------------------------------------------------------- 용량 정리 대조
    print()
    print("=" * 96)
    print("용량 정리 대조   C <= (k-1)(W - h - f)   [f = %d]" % capacity.DEFAULT_F)
    print("=" * 96)
    print("%-16s %-6s %-4s %-6s %-7s %-8s %-9s %-8s %s"
          % ("그룹", "IPS", "k", "C", "h실측", "채움률", "제자리용량",
             "제자리?", "필요 k / 추가 B"))
    checks = []
    for r in runs:
        det = r.get("decoded")
        if not det:
            continue
        k = det["k"]
        C = det["crypto_total"]
        W = int(r["first_flight_bytes"]) // k
        h = det["h_measured"]
        cap = capacity.inplace_capacity(k, W, h, capacity.DEFAULT_F)
        need = capacity.min_k_for_inplace(C, W, h, capacity.DEFAULT_F)
        k_model = capacity.natural_k(C, W, h)
        fill = float(C) / (k * (W - h))
        row = {"group": r["group"], "ips": r["ips"], "k": k, "k_model": k_model,
               "C": C, "W": W, "h": h, "capacity": cap,
               "feasible": C <= cap, "k_needed": need,
               "extra_bytes": (None if need is None
                               else max(0, need - k) * W),
               "fill": fill, "padding": det["padding_total"]}
        checks.append(row)
        print("%-16s %-6s %-4d %-6d %-7.1f %-7.0f%% %-9d %-8s %s"
              % (r["group"], r["ips"] or "기본", k, C, h, 100 * fill, cap,
                 "가능" if row["feasible"] else "불가",
                 ("k=%s (+%s B)" % (need, row["extra_bytes"]))
                 if need else "-"))

    k_model_ok = all(c["k"] == c["k_model"] for c in checks)
    any_feasible = any(c["feasible"] for c in checks)
    print()
    print("모형 k 가 실측 k 와 전부 일치: %s" % ("예" if k_model_ok else "아니오"))
    print("제자리(무비용) 배치가 가능한 설정: %s"
          % ("있음" if any_feasible else "없음 - 전 설정에서 용량 부등식 위반"))

    out = {"rtt_ms": RTT_MS, "n": N, "runs": runs, "capacity_checks": checks,
           "k_model_matches": k_model_ok, "any_inplace_feasible": any_feasible}
    path = B.save("p1_flight.json", out)
    print("saved:", path)
    return 0 if all(r.get("valid") for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
