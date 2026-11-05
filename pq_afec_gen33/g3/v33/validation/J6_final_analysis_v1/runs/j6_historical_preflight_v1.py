import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import collections
import datetime as dt
import gzip
import hashlib
import json
import re
import statistics
from pathlib import Path

RUNS = Path(r"C:\dev\codex_handoff\v33\runs")
ARCHIVE = Path(r"C:\dev\padfec_archive")
ROOT = Path(r"C:\dev\pq_afec_gen33")
sys.path.insert(0, str(ROOT))
from padfec3 import learn3
from padfec import quantum

sha = lambda data: hashlib.sha256(data).hexdigest()
index_path = ARCHIVE / "INDEX.json"
index_bytes = index_path.read_bytes()
entries = [e for e in json.loads(index_bytes)["entries"] if re.fullmatch(r"v31_stage3/experiments/state/p31_run.*_units.jsonl", e["logical_path"])]
assert len(entries) == 25
inputs, medians, histograms, k_counts = [], collections.defaultdict(list), collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
rows_seen = 0
for entry in sorted(entries, key=lambda e: e["logical_path"]):
    path = (ARCHIVE / entry["archive_path"]).resolve()
    assert path.is_relative_to(ARCHIVE.resolve()) and entry["compression"] == "gzip"
    before = path.stat()
    stored = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert len(stored) == entry["stored_bytes"] and sha(stored) == entry["stored_sha256"]
    raw = gzip.decompress(stored)
    assert len(raw) == entry["original_bytes"] and sha(raw) == entry["original_sha256"]
    units = [json.loads(line) for line in raw.splitlines() if line.strip()]
    fingerprints = {unit["fp"] for unit in units}
    keys = {(unit["fp"], unit["key"]) for unit in units}
    assert len(fingerprints) == 1 and len(keys) == len(units)
    inputs.append({**entry, "units": len(units), "fingerprints": sorted(fingerprints), "duplicate_units": 0, "ignored_lines": 0})
    for unit in units:
        value = unit["val"]
        netem = value.get("netem", {})
        rtt = sum(float(match.group(1)) if (match := re.search(r"delay ([0-9.]+)ms", netem.get(direction, ""))) else 0.0 for direction in ("c2s", "s2c"))
        rate_match = re.search(r"rate ([0-9.]+)mbit", netem.get("c2s", ""))
        uplink = float(rate_match.group(1)) if rate_match else 0.0
        certs = {slot: info.get("cert_der") for slot, info in value.get("servers", {}).items()}
        for segment in value["segments"]:
            cert = certs.get(segment.get("slot"))
            for row in segment["rows"]:
                rows_seen += 1
                if not row.get("ok"):
                    continue
                k = row.get("first_flight_datagrams")
                k_counts[(row.get("group"), row.get("ips_eff"))][k] += 1
                if row["ms"] > 1.5 * rtt + 40 or row.get("initial_datagrams") != k + 1:
                    continue
                key = (value["cond"], uplink, rtt, cert, k)
                medians[key].append(row["server_bytes"])
                lead = row.get("first_flight_lead_dgrams")
                if lead is None:
                    lead = int((row.get("m_used") or 0) >= 2)
                hkey = (value["cond"], uplink, cert, segment["arm"], lead)
                histograms[hkey][(row["server_bytes"] - (cert or 0)) // 10 * 10] += 1
median_rows = []
for key, values in sorted(medians.items(), key=lambda x: str(x[0])):
    cond, uplink, rtt, cert, k = key
    median_rows.append({"condition": cond, "uplink_mbps": uplink, "rtt_ms": rtt, "cert_der_B": cert, "k": k, "n": len(values), "min_B": min(values), "median_B": statistics.median(values), "max_B": max(values), "median_minus_cert_B": statistics.median(values) - (cert or 0), "top_values": collections.Counter(values).most_common(6)})
hist_rows = []
for key, counts in sorted(histograms.items(), key=lambda x: str(x[0])):
    cond, uplink, cert, arm, lead = key
    hist_rows.append({"condition": cond, "uplink_mbps": uplink, "cert_der_B": cert, "arm": arm, "lead": lead, "n": sum(counts.values()), "histogram_10B": dict(sorted(counts.items())), "bins_1930_to_1950": sum(counts[x] for x in (1930, 1940, 1950)), "bins_1970_to_1990": sum(counts[x] for x in (1970, 1980, 1990))})
base_bin = quantum.bin_index(2 * 1280)
def need(s):
    v = float(s) - float(base_bin) * 41.983
    n = int(v / (1280.0 - 41.983))
    if float(n * 1280) < v + float(n) * 41.983:
        n += 1
    assert n == learn3.bin_needed_s(float(s), base_bin, 41.983)
    return n
flips = sum(need(s) != need(s + 41) for s in range(4000, 20000))
fixed = [{"name": name, "server_bytes_B": s, "n_need": need(s), "n_need_minus41": need(s - 41)} for name, s in (("S_bigcert", 18231), ("S_rtt200", 10992), ("c6000", 7908), ("c8000", 9950), ("c12000", 14072), ("c14000", 16149), ("p11_9000", 10992), ("p15_4032", 4678))]
mlkem = {str(ips): dict(counts) for (group, ips), counts in k_counts.items() if group == "X25519MLKEM768"}
expected_mlkem = {"1280": {2: 93992}, "1281": {2: 3596}, "1406": {2: 6}}
result = {
    "schema": "padfec.v33.j6_historical_preflight/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "data_kind": "historical_measurement_reanalysis", "index_sha256": sha(index_bytes), "inputs": inputs,
    "rows_seen": rows_seen, "server_bytes_groups": median_rows, "histogram_groups": hist_rows,
    "k_by_group_ips": [{"group": group, "ips_eff": ips, "counts": dict(counts)} for (group, ips), counts in sorted(k_counts.items(), key=lambda x: str(x[0]))],
    "n_need_scan": {"S_min_inclusive_B": 4000, "S_max_exclusive_B": 20000, "a_pre_B": 41, "base_bin": base_bin, "c_pkt_B": 41.983, "flips": flips, "total": 16000, "fraction": flips / 16000, "matches_source_four_decimals": round(flips / 16000, 4) == 0.0307, "fixed_conditions": fixed},
    "mlkem_counts_match_source": mlkem == expected_mlkem,
    "source_sha256": {str(path): sha(path.read_bytes()) for path in [Path(__file__), ROOT / "padfec3/learn3.py", ROOT / "padfec/quantum.py"] + [RUNS.parent / "evidence/audit-quicgo-source" / name for name in ("p04_srvbytes.py", "p06_hist.py", "p09_checks.py")]},
    "limits": ["과거 연결 단위 집계이며 개별 사전 ACK를 식별한 기록이 아니다.", "속도별 비교의 인증서 DER 크기가 다르므로 같은 인증서의 짝비교로 부르지 않는다.", "41 B를 빼는 산술 검사는 실제 CID 길이별 ACK 손실·계수를 검증하지 않는다.", "W1452의 ML-KEM k는 이 자료로 검증하지 않는다."],
}
assert result["n_need_scan"]["matches_source_four_decimals"]
assert all(row["n_need"] == row["n_need_minus41"] for row in fixed)
output = RUNS / "J6_historical_preflight_v1.json"
with output.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")
focus = [row for row in median_rows if row["condition"] in ("D_p17_mbps2", "D_p17_unlimited")]
focus_hist = [row for row in hist_rows if row["condition"] in ("D_p17_mbps2", "D_p17_unlimited") and row["arm"] == "g2auto"]
print(json.dumps({"output": str(output), "sha256": sha(output.read_bytes()), "sources": len(inputs), "rows_seen": rows_seen, "scan": result["n_need_scan"], "mlkem_counts_match_source": result["mlkem_counts_match_source"], "k_by_group_ips": result["k_by_group_ips"], "focus_medians": focus, "focus_histograms": focus_hist}, ensure_ascii=False))
