from __future__ import annotations

import json
import hashlib
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from padfec import policy as POL
from padfec import quantum as QU

RES = os.path.join(ROOT, "experiments", "results")
STATE = os.path.join(ROOT, "experiments", "state")
OUT = os.path.join(RES, "p20_residual.json")

C_FALLBACK = {"x25519": 271, "X25519MLKEM768": 1448}

ALPHA = 0.05

INPUT_FILES = {"p15": "p15_v2policy.json", "p16": "p16_uplink.json",
               "p17": "p17_adaptive_value.json", "p18": "p18_mmax.json"}
P17_CONDITIONS = ("2Mbps", "RTT200", "무제한", "큰cert")
P18_CONDITIONS = ("m_max2포기·무손실", "임계사이·버스트3",
                  "임계위·무버스트", "임계위·2Mbps", "임계위·2Mbps·손실15")


def input_manifest(res, state):
    data, provenance, problems = {}, {}, []
    for stage, filename in INPUT_FILES.items():
        path = os.path.join(res, filename)
        entry = {"file": filename, "sha256": None, "available": False}
        try:
            with open(path, "rb") as f:
                raw = f.read()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("result is not an object")
            data[stage] = value
            entry.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                         available=True,
                         journal_provenance=value.get("journal_provenance"))
            if stage == "p17":
                journal_path = os.path.join(state, "p17_units.jsonl")
                with open(journal_path, "rb") as f:
                    journal_raw = f.read()
                journal = [json.loads(line) for line in journal_raw.splitlines()
                           if line.strip()]
                selected_fp, units = selected_p17_units(value, journal)
                entry["journal_selection"] = {
                    "file": "p17_units.jsonl",
                    "sha256": hashlib.sha256(journal_raw).hexdigest(),
                    "rule": "latest fingerprint, required to match result fingerprint",
                    "fingerprint": selected_fp,
                    "units": [{"key": u["key"], "run_id": u.get("run_id"),
                               "recorded_at": u.get("recorded_at"),
                               "value_sha256": hashlib.sha256(json.dumps(
                                   u["val"], sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode()).hexdigest()}
                              for u in units]}
                result_rows = {r["cond"]: r for r in value.get("rows", [])}
                if any(result_rows.get(u["val"]["cond"]) != u["val"] for u in units):
                    problems.append("p17 result rows differ from selected journal values")
        except (OSError, ValueError, KeyError, TypeError) as e:
            entry["error"] = "%s: %s" % (type(e).__name__, e)
            problems.append("%s input: %s" % (stage, entry["error"]))
        provenance[stage] = entry
    c_path = os.path.join(res, "p1_flight.json")
    try:
        with open(c_path, "rb") as f:
            raw = f.read()
        provenance["model_C"] = {"file": "p1_flight.json",
                                 "sha256": hashlib.sha256(raw).hexdigest(),
                                 "available": True}
    except OSError:
        provenance["model_C"] = {"file": "p1_flight.json", "sha256": None,
                                 "available": False, "source": "fallback"}
    return data, provenance, problems


def selected_p17_units(meta, journal):
    fingerprints = [r.get("fp") for r in journal if r.get("fp")]
    newest = fingerprints[-1] if fingerprints else None
    expected = meta.get("journal_fp") or (meta.get("journal_provenance") or {}).get("fingerprint")
    if not newest or not expected or newest != expected:
        raise ValueError("p17 result and selected journal fingerprint do not match")
    units = [r for r in journal if r.get("fp") == newest]
    keys = [r.get("key") for r in units]
    names = [(r.get("val") or {}).get("cond") for r in units]
    if (len(keys) != len(set(keys)) or len(names) != len(set(names))
            or set(names) != set(P17_CONDITIONS)):
        raise ValueError("p17 selected journal has missing or duplicate conditions")
    return newest, units


def p17_success_blocks(row, arm):
    samples = row["arms"][arm]["ms"]
    if (not isinstance(samples, list)
            or any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0
                   for x in samples)):
        raise ValueError("p17 successful latency array is invalid")
    offset, blocks = 0, []
    for segment in row["segments"]:
        if segment["arm"] != arm:
            continue
        recorded, success = segment["n"], segment.get("ok")
        if (type(recorded) is not int or type(success) is not int
                or not 0 <= success <= recorded):
            raise ValueError("p17 segment success denominator unavailable")
        block = samples[offset:offset + success]
        offset += success
        if len(block) != success:
            raise ValueError("p17 segment successful latency rows missing")
        segment_mean = segment.get("mean")
        if success:
            if (type(segment_mean) not in (int, float)
                    or not math.isfinite(segment_mean)
                    or abs(sum(block) / success - segment_mean) > 1e-6):
                raise ValueError("p17 segment successful latency mean mismatch")
        elif segment_mean is not None:
            raise ValueError("p17 empty successful segment has a mean")
        blocks.append((segment, block))
    if offset != len(samples):
        raise ValueError("p17 unassigned successful latency rows")
    return blocks


def source_coverage(data, conds, problems=()):
    failures = list(problems)
    expected, seen = {}, {}

    def positive_int(value):
        return type(value) is int and value > 0

    def add(stage, name, loss, arm, requested, recorded, success, samples):
        key = "%s|%s|loss%g" % (stage, name, loss)
        expected.setdefault(key, {})[arm] = {
            "requested_n": requested, "recorded_n": recorded,
            "successful_n": success, "failed_n": (
                recorded - success if type(recorded) is int and type(success) is int else None)}
        identity = (key, arm)
        seen[identity] = seen.get(identity, 0) + 1
        valid = (positive_int(requested) and type(recorded) is int
                 and type(success) is int and 0 <= success <= recorded == requested
                 and isinstance(samples, list) and len(samples) == success
                 and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in samples))
        if not valid:
            failures.append("%s %s: requested/recorded/success/latency denominator mismatch" % identity)

    for stage in INPUT_FILES:
        d = data.get(stage)
        if not isinstance(d, dict):
            failures.append("%s required input unavailable" % stage)
            continue
        try:
            if stage != "p17" and not positive_int(d.get("n")):
                failures.append("%s requested sample setting is invalid" % stage)
            if stage == "p17" and (not positive_int(d.get("cycles"))
                                    or not positive_int(d.get("n_per_seg"))):
                failures.append("p17 cycle or segment setting is invalid")
            if stage == "p15":
                rows = [r for r in d["rows"] if r.get("arm") in ("m0", "m1", "m2")]
                design = {(cert, loss, arm) for cert in (2955, 4032)
                          for loss in (0.0, 2.0, 5.0) for arm in ("m0", "m1", "m2")}
                if {(r["cert"], r["loss"], r["arm"]) for r in rows} != design:
                    failures.append("p15 missing or unexpected fixed-arm condition")
                for r in rows:
                    add(stage, "cert%d" % r["cert"], r["loss"], r["arm"],
                        d["n"], r["n"], r["ok"], r.get("ms"))
            elif stage == "p16":
                rows = d["arms"]
                design = {(cond, arm) for cond in ("무제한", "10Mbps")
                          for arm in ("base", "pad", "m1", "m2")}
                if {(r["cond"], r["arm"]) for r in rows} != design:
                    failures.append("p16 missing or unexpected fixed-arm condition")
                for r in rows:
                    add(stage, r["cond"], 0.0, r["arm"], 2 * d["n"], r["n"], r["ok"], r.get("ms"))
                    if r["arm"] == "pad" and p16_pad_input(r).get("model_input_error"):
                        failures.append("p16 %s fixed padding evidence unavailable" % r["cond"])
            elif stage == "p17":
                rows = d["rows"]
                if {r["cond"] for r in rows} != set(P17_CONDITIONS) or len(rows) != len(P17_CONDITIONS):
                    failures.append("p17 missing or duplicate condition")
                for r in rows:
                    if set(r["arms"]) != {"auto", "m0", "m1", "m2", "m3"}:
                        failures.append("p17 %s missing fixed arm" % r["cond"])
                    for arm in ("m0", "m1", "m2", "m3"):
                        by_loss = {}
                        blocks = p17_success_blocks(r, arm)
                        for segment, block in blocks:
                            by_loss.setdefault(segment["loss"], []).extend(block)
                        for loss in (2.0, 15.0):
                            segs = [s for s in r["segments"] if s["arm"] == arm and s["loss"] == loss]
                            n = d["cycles"] * d["n_per_seg"]
                            if len(segs) != d["cycles"]:
                                failures.append("p17 %s %s loss%g missing segment" % (r["cond"], arm, loss))
                            success = sum(s["ok"] for s in segs)
                            recorded = sum(s["n"] for s in segs)
                            add(stage, r["cond"], loss, arm, n, recorded, success, by_loss.get(loss, []))
            else:
                rows = d["rows"]
                if {r["cond"] for r in rows} != set(P18_CONDITIONS) or len(rows) != len(P18_CONDITIONS):
                    failures.append("p18 missing or duplicate condition")
                for r in rows:
                    nblock = max(40, d["n"] // 6) if r["cond"] == P18_CONDITIONS[0] else d["n"] * 3 if r["cond"] == P18_CONDITIONS[1] else d["n"]
                    if r["n_per_block"] != nblock or set(r["arms"]) != {"1", "2", "3", "4"}:
                        failures.append("p18 %s missing arm or block denominator" % r["cond"])
                    for arm, a in r["arms"].items():
                        segs = [s for s in r["segments"] if str(s["m"]) == str(arm)]
                        recorded = sum(s["n"] for s in segs)
                        if len(segs) != 4:
                            failures.append("p18 %s m%s missing segment" % (r["cond"], arm))
                        add(stage, r["cond"], r["loss"], "m%s" % arm,
                            nblock * 4, recorded, a["n"], a.get("ms"))
        except (KeyError, TypeError, ValueError, OverflowError) as e:
            failures.append("%s denominator unavailable: %s" % (stage, e))

    actual = {}
    for c in conds:
        name = c["cond"]
        if name in actual:
            failures.append("duplicate analysed condition: %s" % name)
        actual[name] = {}
        for a in c["arms"]:
            arm = a["arm"]
            if arm in actual[name]:
                failures.append("duplicate analysed arm: %s %s" % (name, arm))
            actual[name][arm] = a["n"]
            if arm not in expected.get(name, {}) or a["n"] != expected[name][arm]["successful_n"]:
                failures.append("analysed arm denominator mismatch: %s %s" % (name, arm))
    if set(actual) != set(expected):
        failures.append("analysed condition set differs from required input design")
    for name, arms in expected.items():
        if set(actual.get(name, {})) != set(arms):
            failures.append("missing analysed fixed arm: %s" % name)
    if any(count != 1 for count in seen.values()):
        failures.append("duplicate input condition/arm")
    return {"complete": not failures, "problems": failures, "expected": expected,
            "expected_conditions": 21, "expected_arms": 78,
            "analysed_conditions": len(actual),
            "analysed_arms": sum(len(arms) for arms in actual.values()),
            "latency_scope": "successful trials only; requested and failed counts remain separate"}


def measured_C(group):
    try:
        d = json.load(open(os.path.join(RES, "p1_flight.json"),
                          encoding="utf-8"))
    except Exception:
        return C_FALLBACK.get(group), "fallback"
    best = None
    for run in d.get("runs", []):
        if run.get("group") != group or not run.get("valid"):
            continue
        c = (run.get("decoded") or {}).get("crypto_total")
        if not c:
            continue
        if run.get("ips", 0) == 0:
            return int(c), "p1"
        best = int(c) if best is None else max(best, int(c))
    if best:
        return best, "p1"
    return C_FALLBACK.get(group), "fallback"


def mean(v):
    return (sum(v) / len(v)) if v else None


def se(v):
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    var = sum((x - mu) ** 2 for x in v) / (len(v) - 1)
    return math.sqrt(var / len(v))


def sd(v):
    if not v or len(v) < 2:
        return None
    mu = sum(v) / len(v)
    return math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1))


def trimmed_mean(v, frac=0.05):
    if not v:
        return None
    a = sorted(v)
    c = int(len(a) * frac)
    b = a[c:len(a) - c] if len(a) - 2 * c >= 1 else a
    return sum(b) / len(b)


def z_of(alpha=ALPHA):
    return statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)


def diff_ci(a, b, alpha=ALPHA):
    sa, sb = se(a), se(b)
    if sa is None or sb is None:
        return None, None
    return mean(a) - mean(b), z_of(alpha) * math.sqrt(sa * sa + sb * sb)


def n_needed(a, b, target_delta, alpha=ALPHA, power=0.80):
    if not target_delta:
        return None
    sa, sb = sd(a), sd(b)
    if sa is None or sb is None:
        return None
    s2 = (sa * sa + sb * sb) / 2.0
    za = z_of(alpha)
    zb = statistics.NormalDist().inv_cdf(power)
    d = abs(float(target_delta))
    if d < 0.01:
        return "분해능아래"
    n = int(math.ceil(2.0 * (za + zb) ** 2 * s2 / (d * d)))
    if n > 1000000:
        return "분해능아래"
    return n


def wilson(k, n, alpha=ALPHA):
    if n <= 0:
        return (0.0, 0.0, 0.0)
    z = z_of(alpha)
    ph = k / n
    den = 1.0 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (ph, max(0.0, c - h), min(1.0, c + h))


def classify(ms, base, rtt):
    t1 = base + 0.5 * rtt
    t2 = base + 2.5 * rtt
    out = {"ontime": [], "extra": [], "timeout": []}
    for x in ms:
        if x < t1:
            out["ontime"].append(x)
        elif x < t2:
            out["extra"].append(x)
        else:
            out["timeout"].append(x)
    return out, t1, t2


def model_arm(group, cert, rtt, loss_pct, burst, uplink, m, W=1280,
              max_steps=2, delta_per_dgram=0):
    C, src = measured_C(group)
    if C is None:
        return None
    s0_base = (POL.S0_BASE_MLKEM if "MLKEM" in group else POL.S0_BASE_X25519)
    try:
        d = POL.decide_v2(C=C, cert_bytes=cert, rtt_ms=rtt,
                          p=loss_pct / 100.0, burst=burst,
                          s0_base=s0_base, c_pkt=POL.C_PKT_POLICY_DEFAULT,
                          W=W, max_steps=max_steps, m_max=max(m, 1),
                          uplink_mbps=uplink)
    except Exception as e:
        return {"err": "%s: %s" % (type(e).__name__, e)}
    if delta_per_dgram:
        if (type(delta_per_dgram) is not int or delta_per_dgram < 0 or m != 0
                or W + delta_per_dgram > POL.QUICGO_MAX_IPS):
            return {"err": "지원하지 않는 고정 padding 구성"}
        base = next((c for c in d["candidates"] if c["mode"] == "none"), None)
        if base is None:
            return {"err": "고정 padding 평가의 기준 후보 없음"}
        k0 = base["k"]
        cand = QU._candidate(
            "pad", 0, delta_per_dgram, C, W, 51, 16, cert, None,
            k0 * W, QU.bin_index(k0 * W, QU.P_SERVER), QU.P_SERVER,
            k_floor=k0, s0_base=s0_base, c_pkt=POL.C_PKT_POLICY_DEFAULT,
            parity_bytes=POL.parity_datagram_bytes)
        c = dict(cand, **POL.cost_of_v2(
            cand, W, rtt, loss_pct / 100.0, burst,
            uplink_mbps=uplink, k0=k0))
    else:
        cs = [c for c in d["candidates"]
              if c["m"] == m and c.get("delta_per_dgram", 0) == 0
              and c["mode"] in ("none", "parity")]
        if not cs:
            return {"err": "m=%d, delta=0 후보 없음" % m}
        c = min(cs, key=lambda e: e["j_ms"])
    p_two = c.get("p_two_rtt", 0.0)
    p_pto = (c.get("p_fail_pto", 0.0) + c.get("p_fail_pto_sampled", 0.0))
    p_ack = c.get("p_fail_ack", 0.0)
    return {
        "C": C, "C_src": src,
        "j_ms": c["j_ms"], "base_ms": c.get("base_ms"),
        "stall_ms": c.get("stall_ms"), "tx_ms": c.get("tx_ms"),
        "p_fail": c.get("p_fail"),
        "chosen_by_policy": d["choice"]["m"],
        "fixed_delta_per_dgram": delta_per_dgram,
        "P_ontime": max(0.0, 1.0 - p_two - p_pto - p_ack),
        "P_extra": p_two + p_ack,
        "P_timeout": p_pto,
        "p_two_rtt": p_two,
    }


def analyse_condition(name, group, cert, rtt, loss_pct, burst, uplink,
                      arms, source):
    live = {k: v for k, v in arms.items() if v.get("ms")}
    if len(live) < 1:
        return None
    base = min(statistics.median(v["ms"]) for v in live.values())
    rows = []
    for aname, a in sorted(live.items()):
        ms = a["ms"]
        cls, t1, t2 = classify(ms, base, rtt)
        n = len(ms)
        if a.get("model_input_error"):
            mod = {"err": a["model_input_error"], "status": "unavailable"}
        else:
            mod = model_arm(group, cert, rtt, loss_pct, burst, uplink, a["m"],
                            delta_per_dgram=a.get("model_delta_per_dgram", 0))
        row = {
            "arm": aname, "m": a["m"], "n": n,
            "mean": mean(ms), "trimmed_mean": trimmed_mean(ms),
            "median": statistics.median(ms), "se": se(ms), "sd": sd(ms),
            "cut_ontime": t1, "cut_timeout": t2,
            "classes": {},
            "model": mod,
            "model_input_source": a.get("model_input_source", "fixed m, delta=0"),
        }
        for cname in ("ontime", "extra", "timeout"):
            v = cls[cname]
            ph, lo, hi = wilson(len(v), n)
            row["classes"][cname] = {
                "n": len(v), "frac": ph, "frac_lo": lo, "frac_hi": hi,
                "mean": mean(v),
                "share_ms": (ph * mean(v)) if v else 0.0,
            }
        if mod and "err" not in mod:
            row["class_residual"] = {}
            for cname, pkey in (("ontime", "P_ontime"),
                                ("extra", "P_extra"),
                                ("timeout", "P_timeout")):
                c = row["classes"][cname]
                pm = min(1.0, max(0.0, mod[pkey]))
                err_pp = 100.0 * (pm - c["frac"])
                row["class_residual"][cname] = {
                    "model": pm, "meas": c["frac"],
                    "err_pp": err_pp,
                    "outside_ci": (abs(err_pp) > 0.05
                                   and not (c["frac_lo"] <= pm <= c["frac_hi"])),
                }
        rows.append(row)

    pairs = []
    names = [r["arm"] for r in rows]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ai, aj = names[i], names[j]
            va, vb = live[ai]["ms"], live[aj]["ms"]
            dm, half = diff_ci(va, vb)
            ri = next(r for r in rows if r["arm"] == ai)
            rj = next(r for r in rows if r["arm"] == aj)
            mi = ri.get("model") or {}
            mj = rj.get("model") or {}
            dj = None
            if "j_ms" in mi and "j_ms" in mj:
                dj = mi["j_ms"] - mj["j_ms"]
            dt = None
            if ri["trimmed_mean"] is not None and rj["trimmed_mean"] is not None:
                dt = ri["trimmed_mean"] - rj["trimmed_mean"]
            verdict = "미판정"
            if dm is not None and half is not None:
                if half >= abs(dm):
                    verdict = "판정불능"
                elif dj is None:
                    verdict = "모형없음"
                elif abs(dj) < 1e-9:
                    verdict = "모형동점"
                elif (dj > 0) == (dm > 0):
                    verdict = "부호일치"
                else:
                    verdict = "부호반대"
            tgt = dj if (dj is not None and abs(dj) >= 1e-6) else dm
            need = n_needed(va, vb, tgt)
            by_class = {}
            for cname in ("ontime", "extra", "timeout"):
                by_class[cname] = (ri["classes"][cname]["share_ms"]
                                   - rj["classes"][cname]["share_ms"])
            pairs.append({
                "pair": "%s-%s" % (ai, aj),
                "meas_delta_ms": dm, "ci95_half_ms": half,
                "trimmed_delta_ms": dt,
                "model_delta_j_ms": dj,
                "residual_ms": (dm - dj) if (dm is not None and dj is not None)
                               else None,
                "verdict": verdict,
                "n_per_arm": min(len(va), len(vb)),
                "n_needed_per_arm": need,
                "n_target_delta_ms": tgt,
                "n_target_source": ("model_delta" if dj is not None and abs(dj) >= 1e-6
                                    else "observed_same_data_delta"),
                "delta_by_class_ms": by_class,
                "tail_share_of_delta": (
                    (by_class["timeout"] / dm) if dm not in (None, 0) else None),
            })
    return {
        "cond": name, "source": source, "group": group, "cert": cert,
        "rtt_ms": rtt, "loss_pct": loss_pct, "burst": burst,
        "uplink_mbps": uplink, "baseline_ms": base,
        "arms": rows, "pairs": pairs,
    }


def load_p17():
    path = os.path.join(STATE, "p17_units.jsonl")
    res = os.path.join(RES, "p17_adaptive_value.json")
    if not (os.path.exists(path) and os.path.exists(res)):
        return []
    meta = json.load(open(res, encoding="utf-8"))
    meta_rtt = meta["rtt_ms"]
    meta_cert = meta["cert"]
    group = meta["group"]
    conds_meta = {c["cond"]: c for c in (meta.get("conds") or [])}
    out = []
    _rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    _newest, _selected = selected_p17_units(meta, _rows)
    for _r in _selected:
        v = _r["val"]
        cond = v["cond"]
        cm = conds_meta.get(cond) or {}
        cert = v.get("cert", cm.get("cert", meta_cert))
        rtt = v.get("rtt_ms", cm.get("rtt_ms", meta_rtt))
        if v.get("up_policy") is not None:
            up, up_guessed = float(v["up_policy"]), False
        elif cm.get("up_policy") is not None:
            up, up_guessed = float(cm["up_policy"]), False
        else:
            up, up_guessed = (2.0 if "2Mbps" in cond else 0.0), True
        if up_guessed:
            print("   [p17|%s] uplink 를 조건 이름으로 추측했다 (%g) - 옛 세대 "
                  "저널이라 값이 없다" % (cond, up))
        for arm_name, a in v["arms"].items():
            if arm_name == "auto":
                continue
            blocks = [(s["loss"], block)
                      for s, block in p17_success_blocks(v, arm_name)]
            for loss in sorted(set(l for l, _ in blocks)):
                key = (cond, loss)
                sel = [x for l, b in blocks if l == loss for x in b]
                out.append((key, group, cert, rtt, loss, 1.0, up,
                            arm_name, int(arm_name[1:]), sel, "p17"))
    return out


def load_p18():
    res = os.path.join(RES, "p18_mmax.json")
    if not os.path.exists(res):
        return []
    d = json.load(open(res, encoding="utf-8"))
    rtt, group = d["rtt_ms"], d["group"]
    out = []
    for row in d.get("rows", []):
        for m_s, a in row["arms"].items():
            if not a.get("ms"):
                continue
            out.append(((row["cond"], row["loss"]), group, row["cert"], rtt,
                        row["loss"], row["burst"], row["uplink"],
                        "m%s" % m_s, int(m_s), a["ms"], "p18"))
    return out


def load_p15():
    res = os.path.join(RES, "p15_v2policy.json")
    if not os.path.exists(res):
        return []
    d = json.load(open(res, encoding="utf-8"))
    rtt, group = d["rtt_ms"], d["group"]
    out = []
    for row in d.get("rows", []):
        arm = row["arm"]
        if not row.get("ms") or not arm.startswith("m"):
            continue
        try:
            m = int(arm[1:])
        except ValueError:
            continue
        out.append(((("cert%d" % row["cert"]), row["loss"]), group,
                    row["cert"], rtt, row["loss"], 1.0, 0.0,
                    arm, m, row["ms"], "p15"))
    return out


def p16_pad_input(arm):
    ev = arm.get("ips_evidence") or {}
    ips, base, k = (ev.get("requested_ips"), ev.get("base_ips"),
                    ev.get("expected_k"))
    n, rows = ev.get("n_req"), ev.get("observations")
    valid = (type(ips) is int and type(base) is int and type(k) is int
             and 0 < base < ips <= 1452 and k == 1
             and ev.get("fec") == "off" and ev.get("configured_m") == 0
             and type(n) is int and n > 0 and isinstance(rows, list)
             and len(rows) == n == ev.get("n_rows") == arm.get("n")
             and all(isinstance(r, dict) for r in rows)
             and arm.get("ok") == n and not arm.get("err"))
    if valid:
        valid = all(
            r.get("ok") is True and r.get("ips_used") == ips
            and r.get("ips_eff") == ips
            and r.get("first_flight_datagrams") == k
            and r.get("first_flight_bytes") == ips * k
            and r.get("first_flight_parity_dgrams") == 0
            for r in rows)
    if not valid:
        return {"model_input_error": (
            "p16 pad의 명시적 IPS 설정과 완전한 첫 비행 관측 일치가 확인되지 않음"),
            "model_input_source": "unavailable"}
    if base != 1280:
        return {"model_input_error": "p16 pad의 기준 IPS가 지원 값 1280과 다름",
                "model_input_source": "unavailable"}
    return {"model_delta_per_dgram": ips - base,
            "model_input_source": "p16 ips_evidence: configuration and every client row"}


def load_p16():
    res = os.path.join(RES, "p16_uplink.json")
    if not os.path.exists(res):
        return []
    d = json.load(open(res, encoding="utf-8"))
    rtt, group, cert = d["rtt_ms"], d["group"], d["cert"]
    out = []
    for a in d.get("arms", []):
        if not a.get("ms"):
            continue
        arm = a["arm"]
        m = 0
        if arm.startswith("m"):
            try:
                m = int(arm[1:])
            except ValueError:
                m = 0
        up = a.get("rate_mbit", 0.0)
        evidence = p16_pad_input(a) if arm == "pad" else {}
        out.append((("%s" % a.get("cond", "?"), 0.0), group, cert, rtt,
                    0.0, 1.0, up, arm, m, a["ms"], "p16", evidence))
    return out


def residual_report(conds, input_coverage=None, input_provenance=None):
    checks = []
    diagnostics = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})

    def diagnose(name, detail):
        diagnostics.append({"check": name, "ok": None, "status": "diagnostic",
                            "gating": False, "detail": str(detail)})

    add("1. 읽을 조건이 있다", len(conds) > 0, "조건 %d 개" % len(conds))

    bad_mass = [(c["cond"], r["arm"], cn, cr["err_pp"])
                for c in conds for r in c["arms"]
                for cn, cr in (r.get("class_residual") or {}).items()
                if cr["outside_ci"]]
    diagnose("2. 부류 비율 잔차 (분류 정의가 달라 모형 적합성 판정 아님)",
        "구간 밖 %d 건 / 총 %d 건%s" % (
            len(bad_mass),
            sum(len(r.get("class_residual") or {}) for c in conds
                for r in c["arms"]),
            (" | 최악 " + ", ".join(
                "%s %s %s %+.1f%%p" % x for x in
                sorted(bad_mass, key=lambda t: -abs(t[3]))[:4])
             if bad_mass else "")))

    flips = [(c["cond"], p["pair"], p["meas_delta_ms"], p["model_delta_j_ms"],
              p["ci95_half_ms"], p["tail_share_of_delta"])
             for c in conds for p in c["pairs"] if p["verdict"] == "부호반대"]
    diagnose("3. 부호가 반대인 팔쌍 (개별 구간 기준 참고 진단)",
        ("%d 건" % len(flips)) + ("" if not flips else " | " + " ; ".join(
            "%s %s 측정 %+.2f vs 모형 %+.2f (반폭 %.2f, 꼬리몫 %s)"
            % (a, b, cd, md, h, ("%.0f%%" % (100 * ts)) if ts is not None else "-")
            for a, b, cd, md, h, ts in flips[:6])))

    missing_models = [(c["cond"], r["arm"], (r.get("model") or {}).get("err"))
                      for c in conds for r in c["arms"]
                      if not r.get("model") or r["model"].get("err")]
    if missing_models:
        diagnose("모형 입력 확인 불가 (해당 팔의 모형 비교 제외)",
                 "%d 팔 | %s" % (len(missing_models), "; ".join(
                     "%s %s: %s" % (cond, arm, err or "모형 없음")
                     for cond, arm, err in missing_models)))

    undecid = [p for c in conds for p in c["pairs"] if p["verdict"] == "판정불능"]
    _no_n = [p for p in undecid if p["n_needed_per_arm"] is None]
    _unmeas = [p for p in undecid
               if p["n_needed_per_arm"] == "분해능아래"]
    add("4. 판정 불능인 팔쌍은 필요 표본 또는 '분해능 아래'를 말한다",
        not _no_n,
        "판정불능 %d / 전체 %d 쌍 | 필요 표본 추정 %d · 분해능아래 %d · 무응답 %d"
        % (len(undecid), sum(len(c["pairs"]) for c in conds),
           len(undecid) - len(_unmeas) - len(_no_n), len(_unmeas),
           len(_no_n)))

    underpow = [(c["cond"], p["pair"], p["n_per_arm"], p["n_needed_per_arm"])
                for c in conds for p in c["pairs"]
                if isinstance(p["n_needed_per_arm"], int)
                and p["n_per_arm"] < p["n_needed_per_arm"]]
    unmeasurable = [(c["cond"], p["pair"]) for c in conds for p in c["pairs"]
                    if p["n_needed_per_arm"] == "분해능아래"]
    targets = {kind: sum(p.get("n_target_source") == kind
                         for c in conds for p in c["pairs"])
               for kind in ("model_delta", "observed_same_data_delta")}
    target_shortages = {kind: sum(
        p.get("n_target_source") == kind and isinstance(p["n_needed_per_arm"], int)
        and p["n_per_arm"] < p["n_needed_per_arm"]
        for c in conds for p in c["pairs"]) for kind in targets}
    add("5. 표본이 명시한 목표 크기를 잡기에 충분하다 (모형 또는 같은 자료의 관측차)",
        len(underpow) == 0,
        "모자란 쌍 %d 개 (분해능아래 %d 개는 뺌) | 모형 목표 %d, 관측 목표 %d%s" % (
            len(underpow), len(unmeasurable),
            target_shortages["model_delta"], target_shortages["observed_same_data_delta"],
            (" | 최악 " + ", ".join(
                "%s %s %d<%d" % x for x in
                sorted(underpow, key=lambda t: -(t[3] / max(1, t[2])))[:4])
             if underpow else "")))
    if input_coverage is not None:
        add("6. 네 입력의 필수 조건·팔·시행 분모가 완전하다",
            input_coverage["complete"],
            "조건 %d/%d, 팔 %d/%d | %s" % (
                input_coverage["analysed_conditions"], input_coverage["expected_conditions"],
                input_coverage["analysed_arms"], input_coverage["expected_arms"],
                "; ".join(input_coverage["problems"]) or "누락 없음"))

    out = {
        "alpha": ALPHA,
        "conds": conds,
        "checks": checks,
        "diagnostics": diagnostics,
        "sample_target_counts": {"all": targets, "underpowered": target_shortages,
                                 "observed_target_limit": "Same-data observed effects are exploratory targets, not independent model claims."},
        "input_coverage": input_coverage,
        "input_provenance": input_provenance,
        "classification_limits": {
            "same_event_definition_verified": False,
            "observed_basis": (
                "성공 지연만 사용. 조건 내 최저 팔 중앙값+0.5RTT 및 +2.5RTT로 "
                "구간 분류하며 실제 PTO·연결 실패 이벤트를 식별하지 않는다"),
            "model_basis": (
                "p_two_rtt·p_fail_ack·PTO 모형 경로 확률을 묶는다. "
                "관측 중앙값 기준과 같은 사건이라는 검증은 하지 않았다"),
            "fixed_pto_limit": (
                "고정 200.86ms PTO 항을 timeout에 배정하는 현행 규칙은 "
                "RTT 200ms의 관측 +2.5RTT 경계와 일치하지 않을 수 있다"),
            "p16_pad_input_limit": (
                "p16 pad는 명시적 IPS와 전체 시행의 ips_used·ips_eff·첫 비행 "
                "관측이 일치할 때만 고정 delta로 평가한다. 근거 없는 옛 자료는 "
                "unavailable이며 base 모형을 대신 넣지 않는다"),
            "inference_limit": (
                "개별 독립 표본 근사 구간이며 블록·다중 비교 보정이 없다. "
                "구간 밖 건수와 부호 일치는 모형 전체 정확도나 동등성 판정이 아니다"),
        },
        "gating_note": (
            "passed/total은 checks만 센다. diagnostics는 참고 진단이며 "
            "모형 적합성의 성공·실패로 집계하지 않는다. 표본 부족 기준은 유지한다"),
        "passed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
    }
    return out


def main():
    data, provenance, input_problems = input_manifest(RES, STATE)
    recs = []
    for loader in (load_p17, load_p18, load_p15, load_p16):
        try:
            recs.extend(loader())
        except Exception as e:
            input_problems.append("%s: %s" % (loader.__name__, e))
            print("  [경고] %s: %s" % (loader.__name__, e), flush=True)

    grouped = {}
    for rec in recs:
        key, group, cert, rtt, loss, burst, up, arm, m, ms, src = rec[:11]
        evidence = rec[11] if len(rec) > 11 else {}
        gkey = (src, key[0], key[1], group, cert, rtt, burst, up)
        grouped.setdefault(gkey, {})[arm] = {"m": m, "ms": ms, **evidence}

    conds = []
    for gkey, arms in sorted(grouped.items(), key=lambda kv: str(kv[0])):
        src, cname, loss, group, cert, rtt, burst, up = gkey
        r = analyse_condition("%s|%s|loss%g" % (src, cname, loss), group,
                              cert, rtt, loss, burst, up, arms, src)
        if r:
            conds.append(r)

    for entry in provenance.values():
        if not entry.get("available"):
            continue
        try:
            with open(os.path.join(RES, entry["file"]), "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            if digest != entry["sha256"]:
                input_problems.append("input changed while reading: %s" % entry["file"])
        except OSError as e:
            input_problems.append("input became unavailable: %s" % e)
        selection = entry.get("journal_selection")
        if selection:
            try:
                with open(os.path.join(STATE, selection["file"]), "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                if digest != selection["sha256"]:
                    input_problems.append("selected journal changed while reading")
            except OSError as e:
                input_problems.append("selected journal became unavailable: %s" % e)
    coverage = source_coverage(data, conds, input_problems)
    out = residual_report(conds, input_coverage=coverage, input_provenance=provenance)
    checks = out["checks"]
    from _journal import save_result
    save_result(OUT, out)

    print("P20 잔차 해부")
    for c in conds:
        print("  %-34s cert=%-6d up=%-4g burst=%g"
              % (c["cond"], c["cert"], c["uplink_mbps"], c["burst"]))
        for r in c["arms"]:
            mod = r.get("model") or {}
            cr = r.get("class_residual") or {}
            print("     %-5s n=%4d 평균 %8.3f (본체 %8.3f) | 모형 J %8.3f"
                  % (r["arm"], r["n"], r["mean"], r["trimmed_mean"],
                     mod.get("j_ms", float("nan"))))
            for cn in ("ontime", "extra", "timeout"):
                cc = r["classes"][cn]
                e = cr.get(cn)
                print("        %-8s 측정 %6.2f%% [%5.2f,%5.2f] 값 %8.3f"
                      "  모형 %6.2f%%  잔차 %+6.2f%%p%s"
                      % (cn, 100 * cc["frac"], 100 * cc["frac_lo"],
                         100 * cc["frac_hi"],
                         cc["mean"] if cc["mean"] is not None else float("nan"),
                         100 * e["model"] if e else float("nan"),
                         e["err_pp"] if e else float("nan"),
                         "  <-- 구간 밖" if e and e["outside_ci"] else ""))
        for p in c["pairs"]:
            print("     %-9s 측정 %+7.3f ±%5.3f | 본체 %+7.3f | 모형 %+7.3f"
                  " | 잔차 %+7.3f | %s | n %d (필요 %s) 꼬리몫 %s"
                  % (p["pair"], p["meas_delta_ms"], p["ci95_half_ms"],
                     p["trimmed_delta_ms"] if p["trimmed_delta_ms"] is not None
                     else float("nan"),
                     p["model_delta_j_ms"] if p["model_delta_j_ms"] is not None
                     else float("nan"),
                     p["residual_ms"] if p["residual_ms"] is not None
                     else float("nan"),
                     p["verdict"], p["n_per_arm"],
                     p["n_needed_per_arm"],
                     ("%.0f%%" % (100 * p["tail_share_of_delta"]))
                     if p["tail_share_of_delta"] is not None else "-"))
    print()
    for c in checks:
        print("[%s] %-58s %s" % ("통과" if c["ok"] else "실패",
                                 c["check"][:58], c["detail"][:90]))
    for d in out["diagnostics"]:
        print("[진단] %s %s" % (d["check"], d["detail"]))
    print("[한계] %s" % out["gating_note"])
    for detail in out["classification_limits"].values():
        if isinstance(detail, str):
            print("[한계] %s" % detail)
    print("-" * 100)
    print("%d / %d 통과" % (out["passed"], out["total"]))
    return 0 if out["passed"] == out["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
