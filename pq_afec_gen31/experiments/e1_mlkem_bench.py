import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
os.makedirs(RESULTS, exist_ok=True)

FIPS203 = {
    "ML-KEM-512":  {"ek": 800,  "dk": 1632, "ct": 768,  "ss": 32},
    "ML-KEM-768":  {"ek": 1184, "dk": 2400, "ct": 1088, "ss": 32},
    "ML-KEM-1024": {"ek": 1568, "dk": 3168, "ct": 1568, "ss": 32},
}
KEMS = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
BASELINE = "X25519"


def _harden_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=False, **kw)


def openssl_version():
    r = run(["openssl", "version", "-a"])
    return r.stdout.decode("utf-8", "replace").strip()


def der_read_tlv(buf, i):
    tag = buf[i]
    i += 1
    n = buf[i]
    i += 1
    if n & 0x80:
        k = n & 0x7F
        n = int.from_bytes(buf[i:i + k], "big")
        i += k
    return tag, n, i, i + n


def spki_raw_pubkey_len(der):
    tag, ln, vs, nxt = der_read_tlv(der, 0)
    assert tag == 0x30, "SPKI must be SEQUENCE"
    i = vs
    tag, ln, vs2, i = der_read_tlv(der, i)
    assert tag == 0x30
    tag, ln, vs3, i = der_read_tlv(der, i)
    assert tag == 0x03, "expected BIT STRING"
    return ln - 1


def pkcs8_privkey_octets(der):
    tag, ln, vs, nxt = der_read_tlv(der, 0)
    assert tag == 0x30
    i = vs
    tag, ln, _, i = der_read_tlv(der, i)
    tag, ln, _, i = der_read_tlv(der, i)
    tag, ln, vs3, i = der_read_tlv(der, i)
    assert tag == 0x04, "expected OCTET STRING"
    return ln, der[vs3:vs3 + min(ln, 8)]


def measure_sizes(alg, workdir):
    sk_pem = os.path.join(workdir, "sk.pem")
    sk_der = os.path.join(workdir, "sk.der")
    pk_der = os.path.join(workdir, "pk.der")
    pk_pem = os.path.join(workdir, "pk.pem")
    ct = os.path.join(workdir, "ct.bin")
    ss1 = os.path.join(workdir, "ss1.bin")
    ss2 = os.path.join(workdir, "ss2.bin")

    r = run(["openssl", "genpkey", "-algorithm", alg, "-out", sk_pem])
    if r.returncode != 0:
        raise RuntimeError("genpkey %s failed: %s" % (alg, r.stderr.decode("utf-8", "replace")))
    run(["openssl", "pkey", "-in", sk_pem, "-outform", "DER", "-out", sk_der])
    run(["openssl", "pkey", "-in", sk_pem, "-pubout", "-out", pk_pem])
    run(["openssl", "pkey", "-in", sk_pem, "-pubout", "-outform", "DER", "-out", pk_der])

    r = run(["openssl", "pkeyutl", "-encap", "-inkey", pk_pem, "-pubin",
             "-out", ct, "-secret", ss1])
    if r.returncode != 0:
        raise RuntimeError("encap %s failed: %s" % (alg, r.stderr.decode("utf-8", "replace")))
    r = run(["openssl", "pkeyutl", "-decap", "-inkey", sk_pem, "-in", ct, "-secret", ss2])
    if r.returncode != 0:
        raise RuntimeError("decap %s failed: %s" % (alg, r.stderr.decode("utf-8", "replace")))

    with open(ss1, "rb") as f:
        s1 = f.read()
    with open(ss2, "rb") as f:
        s2 = f.read()
    with open(pk_der, "rb") as f:
        pkd = f.read()
    with open(sk_der, "rb") as f:
        skd = f.read()

    stored_sk_len, head = pkcs8_privkey_octets(skd)
    return {
        "alg": alg,
        "ct_bytes": os.path.getsize(ct),
        "ss_bytes": len(s1),
        "ss_agree": (s1 == s2),
        "ek_bytes_raw": spki_raw_pubkey_len(pkd),
        "ek_bytes_spki_der": len(pkd),
        "ek_bytes_pem": os.path.getsize(pk_pem),
        "sk_der_total": len(skd),
        "sk_stored_octets": stored_sk_len,
    }


SPEED_RE = re.compile(
    r"^\s*(\S+)\s+([0-9.]+)s\s+([0-9.]+)s\s+([0-9.]+)s\s+"
    r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*$")


def speed_once(alg, seconds):
    r = run(["openssl", "speed", "-kem-algorithms", "-seconds", str(seconds), alg])
    txt = (r.stdout + r.stderr).decode("utf-8", "replace")
    for line in txt.splitlines():
        m = SPEED_RE.match(line)
        if m and m.group(1) == alg:
            return {
                "keygen_s": float(m.group(2)),
                "encaps_s": float(m.group(3)),
                "decaps_s": float(m.group(4)),
                "keygen_ops": float(m.group(5)),
                "encaps_ops": float(m.group(6)),
                "decaps_ops": float(m.group(7)),
            }
    raise RuntimeError("could not parse speed output for %s:\n%s" % (alg, txt[-1500:]))


def measure_timing(alg, seconds, repeats):
    runs = []
    for i in range(repeats):
        runs.append(speed_once(alg, seconds))
        print("      rep %d/%d ok" % (i + 1, repeats))
    out = {"alg": alg, "repeats": repeats, "seconds_per_rep": seconds, "runs": runs}
    for key in ("keygen", "encaps", "decaps"):
        us = [r["%s_s" % key] * 1e6 for r in runs]
        ops = [r["%s_ops" % key] for r in runs]
        out["%s_us_median" % key] = statistics.median(us)
        out["%s_us_min" % key] = min(us)
        out["%s_us_max" % key] = max(us)
        out["%s_ops_median" % key] = statistics.median(ops)
        out["%s_ops_stdev" % key] = statistics.stdev(ops) if len(ops) > 1 else 0.0
    return out


def main():
    _harden_console()
    seconds = int(os.environ.get("E1_SECONDS", "3"))
    repeats = int(os.environ.get("E1_REPEATS", "5"))

    if shutil.which("openssl") is None:
        print("ERROR: openssl not on PATH")
        return 2

    print("=" * 78)
    print("E1 - ML-KEM performance measurement")
    print("=" * 78)
    ver = openssl_version()
    print(ver.splitlines()[0])
    print("")

    out = {
        "openssl_version": ver,
        "python": sys.version,
        "platform": sys.platform,
        "seconds_per_rep": seconds,
        "repeats": repeats,
        "sizes": {},
        "timing": {},
    }

    print("[a] sizes (real keygen + encap + decap)")
    with tempfile.TemporaryDirectory() as wd:
        for alg in KEMS:
            s = measure_sizes(alg, wd)
            out["sizes"][alg] = s
            ref = FIPS203[alg]
            ok_ek = "OK" if s["ek_bytes_raw"] == ref["ek"] else "MISMATCH"
            ok_ct = "OK" if s["ct_bytes"] == ref["ct"] else "MISMATCH"
            print("  %-12s ek=%5d (FIPS %4d %s)  ct=%5d (FIPS %4d %s)  ss=%d agree=%s"
                  % (alg, s["ek_bytes_raw"], ref["ek"], ok_ek,
                     s["ct_bytes"], ref["ct"], ok_ct,
                     s["ss_bytes"], s["ss_agree"]))
            print("               openssl stores sk as %d octets (FIPS expanded dk = %d)"
                  % (s["sk_stored_octets"], ref["dk"]))
    print("")

    print("[b] timing: openssl speed -kem-algorithms, %ds x %d reps" % (seconds, repeats))
    for alg in KEMS + [BASELINE]:
        print("    %s" % alg)
        try:
            out["timing"][alg] = measure_timing(alg, seconds, repeats)
        except Exception as e:
            print("      SKIP (%s)" % e)
    print("")

    print("-" * 78)
    print("%-13s %10s %10s %10s   %12s" %
          ("alg", "keygen us", "encaps us", "decaps us", "encaps ops/s"))
    print("-" * 78)
    for alg, t in out["timing"].items():
        print("%-13s %10.2f %10.2f %10.2f   %12.0f" %
              (alg, t["keygen_us_median"], t["encaps_us_median"],
               t["decaps_us_median"], t["encaps_ops_median"]))
    print("-" * 78)

    path = os.path.join(RESULTS, "e1_mlkem.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("saved: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
