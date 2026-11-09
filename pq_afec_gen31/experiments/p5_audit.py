from __future__ import annotations

import itertools
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from padfec import amplif, capacity, policy
from padfec.codec import FlightCode, unpack_footer

QAMP = os.path.join(HERE, "quicbed", "qamp.go")
QBED = os.path.join(HERE, "quicbed")
BUILD_SH = os.path.join(QBED, "build.sh")


def qamp_sources():
    out = []
    try:
        with open(BUILD_SH, encoding="utf-8") as f:
            for line in f:
                if "cmd/qamp/" not in line or "$SRC/" not in line:
                    continue
                name = line.split("$SRC/", 1)[1].split(chr(34), 1)[0]
                if name.endswith(".go"):
                    out.append(os.path.join(QBED, name))
    except OSError:
        pass
    if not out:
        out = [QAMP]
    return out

VEC_MAIN = """package main

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
)

func main() {
	gfInit()
	k, _ := strconv.Atoi(os.Args[1])
	m, _ := strconv.Atoi(os.Args[2])
	size, _ := strconv.Atoi(os.Args[3])
	seed, _ := strconv.Atoi(os.Args[4])
	src := make([][]byte, k)
	x := uint32(seed*2654435761 + 1)
	for i := range src {
		src[i] = make([]byte, size)
		for j := range src[i] {
			x ^= x << 13
			x ^= x >> 17
			x ^= x << 5
			src[i][j] = byte(x)
		}
	}
	pars := rsEncode(src, m, size)
	out := map[string]interface{}{}
	ss := []string{}
	for _, d := range src {
		ss = append(ss, hex.EncodeToString(d))
	}
	ps := []string{}
	for _, d := range pars {
		ps = append(ps, hex.EncodeToString(d))
	}
	rec := map[string]string{}
	for miss := 0; miss < k; miss++ {
		origs := map[int][]byte{}
		for i := range src {
			if i != miss {
				origs[i] = src[i]
			}
		}
		for j := range pars {
			r := recoverOne(k, m, j, miss, origs, pars[j], size)
			rec[fmt.Sprint(miss, ":", j)] = hex.EncodeToString(r)
		}
	}
	out["src"] = ss
	out["parity"] = ps
	out["recovered"] = rec
	b, _ := json.Marshal(out)
	fmt.Println(string(b))
}
"""


def build_vector_tool():
    tmp = tempfile.mkdtemp(prefix="padfec_audit_")
    for path in qamp_sources():
        src = open(path, encoding="utf-8").read()
        src = src.replace("func main() {",
                          "func qfecMainUnused() {", 1)
        with open(os.path.join(tmp, os.path.basename(path)), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(src)
    with open(os.path.join(tmp, "vec.go"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(VEC_MAIN)
    wsl_tmp = "/tmp/padfec_audit"
    script = (
        "export GOPATH=$HOME/gopath; "
        'export PATH="$HOME/goroot/bin:$PATH"; '
        "rm -rf %s && mkdir -p %s && "
        "cp %s/*.go %s/ && cd $HOME/quicbed && "
        "cp go.mod go.sum %s/ 2>/dev/null; cd %s && "
        "go mod edit -module padfecaudit 2>/dev/null; "
        "go mod tidy >/dev/null 2>&1; "
        "go build -o %s/qvec . && echo BUILD_OK"
        % (wsl_tmp, wsl_tmp, _wslpath(tmp), wsl_tmp, wsl_tmp, wsl_tmp,
           wsl_tmp))
    r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-lc", script],
                       capture_output=True, text=True, errors="replace")
    if "BUILD_OK" not in (r.stdout or ""):
        return None, (r.stdout or "") + (r.stderr or "")
    shutil.rmtree(tmp, ignore_errors=True)
    return wsl_tmp + "/qvec", ""


def _wslpath(win):
    p = win.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = "/mnt/" + p[0].lower() + p[2:]
    return p


def go_vectors(tool, k, m, size, seed):
    r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-lc",
                        "%s %d %d %d %d" % (tool, k, m, size, seed)],
                       capture_output=True, text=True, errors="replace")
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return None


def audit_cross(results):
    tool, err = build_vector_tool()
    if not tool:
        results.append({"check": "Go/Python 교차구현", "ok": False,
                        "detail": "감사용 빌드 실패: %s" % err[-400:]})
        return
    bad = []
    n = 0
    for k in (2, 3, 4):
        for m in (1, 2):
            for seed in (1, 2, 3):
                v = go_vectors(tool, k, m, 64, seed)
                if not v:
                    bad.append("k=%d m=%d seed=%d 벡터 없음" % (k, m, seed))
                    continue
                src = [bytes.fromhex(x) for x in v["src"]]
                gopar = [bytes.fromhex(x) for x in v["parity"]]
                pypar = FlightCode(k, m).encode(src)
                n += 1
                if gopar != pypar:
                    bad.append("k=%d m=%d seed=%d 패리티 불일치" % (k, m, seed))
                for miss in range(k):
                    for j in range(m):
                        got = bytes.fromhex(v["recovered"]["%d:%d" % (miss, j)])
                        if got != src[miss]:
                            bad.append("k=%d m=%d seed=%d miss=%d par=%d "
                                       "복원 불일치" % (k, m, seed, miss, j))
    results.append({"check": "Go/Python 교차구현 (%d 조합)" % n,
                    "ok": not bad, "detail": "; ".join(bad[:5]) or "전부 일치"})


def feasible_bruteforce(C, k, W, h, f, step=1):
    if k < 2:
        return False
    room = W - h - f
    if room <= 0:
        return False
    for cs in itertools.product(range(0, room + 1, step), repeat=k):
        if sum(cs) != C:
            continue
        for ps in itertools.product(*[range(0, room - c + 1, step)
                                      for c in cs]):
            ok = True
            for j in range(k):
                if sum(ps) - ps[j] < cs[j]:
                    ok = False
                    break
            if ok:
                return True
    return False


def audit_capacity(results):
    bad = []
    tested = 0
    random.seed(11)
    for k in (2, 3):
        for W in (20, 26):
            for h in (3, 5):
                for f in (1, 2):
                    room = W - h - f
                    for C in range(1, k * room + 1):
                        theo = C <= (k - 1) * room
                        brute = feasible_bruteforce(C, k, W, h, f)
                        tested += 1
                        if theo != brute:
                            bad.append("k=%d W=%d h=%d f=%d C=%d "
                                       "정리=%s 완전탐색=%s"
                                       % (k, W, h, f, C, theo, brute))
    results.append({
        "check": "용량 정리 완전탐색 대조 (%d 경우)" % tested,
        "ok": not bad,
        "detail": ("; ".join(bad[:5]) if bad else
                   "모든 경우에서 정리와 완전탐색이 일치 - 반례 없음")})

    n_true = n_false = 0
    for k in (2, 3):
        for W in (20, 26):
            for h in (3, 5):
                for f in (1, 2):
                    room = W - h - f
                    for C in range(1, k * room + 1):
                        if feasible_bruteforce(C, k, W, h, f):
                            n_true += 1
                        else:
                            n_false += 1
    results.append({
        "check": "[부정] 완전탐색이 가능/불가를 둘 다 낸다 (한쪽만이면 공허)",
        "ok": n_true > 0 and n_false > 0,
        "detail": "가능 %d 건 / 불가 %d 건" % (n_true, n_false)})

    edge = []
    for k in (2, 3, 4):
        for W in (20, 26, 30):
            for h in (3, 5):
                for f in (1, 2):
                    room = W - h - f
                    lim = (k - 1) * room
                    if lim < 1 or lim + 1 > k * room:
                        continue
                    if not feasible_bruteforce(lim, k, W, h, f):
                        edge.append("k=%d W=%d h=%d f=%d C=%d 이 불가로 나온다"
                                    % (k, W, h, f, lim))
                    if feasible_bruteforce(lim + 1, k, W, h, f):
                        edge.append("k=%d W=%d h=%d f=%d C=%d 가 가능으로 나온다"
                                    % (k, W, h, f, lim + 1))
    results.append({
        "check": "[부정] 경계 C=(k-1)(W-h-f) 에서 1 바이트로 정확히 갈린다",
        "ok": not edge,
        "detail": "; ".join(edge[:4]) or "전 설정에서 경계가 정확하다"})


def audit_invariants(results):
    d = [amplif.budget(cb + 1200) - amplif.budget(cb)
         for cb in (1200, 2400, 3600, 4800)]
    ok1 = all(abs(x - 3 * 1200) < 1e-9 for x in d)
    results.append({"check": "증폭 예산 기울기 = 3.00 (양자화 전)", "ok": ok1,
                    "detail": "차분 %s (기대 %d)" % (d, 3 * 1200)})

    bad = []
    for cb in range(1000, 8000, 137):
        b = amplif.budget(cb)
        a = amplif.allowed_bytes(cb)
        if not (b <= a < b + amplif.SERVER_PACKET_SIZE):
            bad.append("클라 %d: 예산 %d 허용 %d" % (cb, b, a))
        if a % amplif.SERVER_PACKET_SIZE != 0:
            bad.append("클라 %d: 허용 %d 이 패킷 배수가 아니다" % (cb, a))
    results.append({"check": "양자화 허용량이 [예산, 예산+패킷) 안의 패킷 배수",
                    "ok": not bad, "detail": "; ".join(bad[:3]) or "전부 통과"})

    bad = []
    for p in (0.0, 0.005, 0.02, 0.05, 0.2):
        for L in (1.0, 2.0, 5.0):
            pmf = policy.erasure_probs(6, p, L)
            if abs(sum(pmf) - 1.0) > 1e-9 or any(x < -1e-12 for x in pmf):
                bad.append("p=%.3f L=%.1f 합=%.6f" % (p, L, sum(pmf)))
    results.append({"check": "소거 분포가 확률 (합=1, 음수 없음)",
                    "ok": not bad, "detail": "; ".join(bad) or "전부 통과"})

    bad = []
    for p in (0.01, 0.05, 0.1):
        for L in (1.0, 3.0):
            v = [policy.p_unrecoverable(2, m, p, L) for m in (1, 2, 3)]
            if not all(v[i] >= v[i + 1] - 1e-12 for i in range(len(v) - 1)):
                bad.append("p=%.2f L=%.1f -> %s" % (p, L, v))
    results.append({"check": "복구 실패 확률이 m 에 대해 단조 감소",
                    "ok": not bad, "detail": "; ".join(bad) or "전부 통과"})

    bad = []
    for cert in (3000, 6800):
        prev = -1
        for p in (0.0, 0.005, 0.01, 0.02, 0.05):
            ch = policy.decide(1448, cert, 50.0, p, 1.0, 1730)["choice"]["m"]
            if ch < prev:
                bad.append("cert=%d p=%.3f 에서 m 이 %d -> %d 로 감소"
                           % (cert, p, prev, ch))
            prev = ch
    results.append({"check": "손실 증가 시 정책의 m 이 감소하지 않음",
                    "ok": not bad, "detail": "; ".join(bad) or "전부 통과"})

    ok5 = capacity.inplace_capacity(1) == 0 and not capacity.inplace_feasible(
        1, 1)
    results.append({"check": "k=1 비행은 제자리 보호 불가 (따름정리 1)",
                    "ok": ok5, "detail": "용량 %d"
                    % capacity.inplace_capacity(1)})

    P = FlightCode(2, 1).encode([bytes([0b01101001]), bytes([0b11010110])])[0]
    results.append({"check": "XOR 패리티가 인수인계 문서 손계산과 일치",
                    "ok": P == bytes([0b10111111]),
                    "detail": "계산 %s" % format(P[0], "08b")})


def audit_codec_properties(results):
    rnd = random.Random(20260819)
    bad = []
    n_ok = n_fail = 0
    for _ in range(400):
        k = rnd.choice([2, 3, 4, 5, 6])
        m = rnd.choice([1, 2, 3])
        if m > k:
            continue
        size = rnd.choice([64, 517, 1200, 1280])
        src = [bytes(rnd.randrange(256) for _ in range(size))
               for _ in range(k)]
        fc = FlightCode(k, m)
        par = fc.encode(src)
        allsym = {i: src[i] for i in range(k)}
        for j, pp in enumerate(par):
            allsym[k + j] = pp
        sizes = {i: size for i in range(k)}

        e = rnd.randint(1, m)
        lost = rnd.sample(range(k + m), e)
        recv = {i: v for i, v in allsym.items() if i not in lost}
        try:
            got = fc.decode(recv, sizes)
            n_ok += 1
            if got != src:
                bad.append("k=%d m=%d 소거%d 복원 불일치" % (k, m, e))
        except Exception as ex:
            bad.append("k=%d m=%d 소거%d 복원 실패: %s" % (k, m, e, ex))

        if k + m > m + 1:
            lost2 = rnd.sample(range(k + m), m + 1)
            recv2 = {i: v for i, v in allsym.items() if i not in lost2}
            try:
                got2 = fc.decode(recv2, sizes)
                if got2 == src:
                    bad.append("k=%d m=%d 소거%d 를 복원했다(불가능해야)"
                               % (k, m, m + 1))
                else:
                    bad.append("k=%d m=%d 소거%d 에서 **틀린 값을 조용히** "
                               "돌려줬다" % (k, m, m + 1))
            except Exception:
                n_fail += 1
    results.append({
        "check": "부호 성질 무작위 시험 (복원 %d회 / 정당한 실패 %d회)"
                 % (n_ok, n_fail),
        "ok": not bad, "detail": "; ".join(bad[:3]) or "전부 통과"})


def audit_false_positive(results):
    rnd = random.Random(4242)
    fp = 0
    trials = 20000
    for _ in range(trials):
        n = rnd.choice([64, 1200, 1280, 1350])
        d = bytes(rnd.randrange(256) for _ in range(n))
        if unpack_footer(d) is not None:
            fp += 1
    for _ in range(5000):
        d = bytearray([0xC3, 0, 0, 0, 1, 8])
        d += bytes(rnd.randrange(256) for _ in range(8))
        d += bytes([0, 0x00, 0x44, 0x00])
        d += bytes(rnd.randrange(256) for _ in range(1200))
        if unpack_footer(bytes(d)) is not None:
            fp += 1
    results.append({
        "check": "무작위/유사 QUIC 데이터그램 %d 개를 패리티로 오인하지 않는다"
                 % (trials + 5000),
        "ok": fp == 0, "detail": "오인 %d 건 (기대 0)" % fp})


def audit_amplif_monotone(results):
    bad = []
    prev_a = prev_t = None
    for cb in range(1000, 12000, 37):
        a = amplif.allowed_bytes(cb)
        t = amplif.threshold_cert(cb, 1736)
        if prev_a is not None and a < prev_a:
            bad.append("허용량이 클라 %d 에서 줄었다" % cb)
        if prev_t is not None and t < prev_t:
            bad.append("임계가 클라 %d 에서 줄었다" % cb)
        prev_a, prev_t = a, t
    results.append({"check": "허용량·임계가 클라이언트 바이트에 단조 증가",
                    "ok": not bad, "detail": "; ".join(bad[:3]) or "전부 통과"})


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    results = []
    audit_cross(results)
    audit_capacity(results)
    audit_codec_properties(results)
    audit_false_positive(results)
    audit_amplif_monotone(results)
    audit_invariants(results)

    print("=" * 92)
    print("PAD-FEC 독립 감사")
    print("=" * 92)
    npass = 0
    for r in results:
        mark = "통과" if r["ok"] else "실패"
        npass += 1 if r["ok"] else 0
        print("[%s] %-46s %s" % (mark, r["check"], r["detail"][:90]))
    print("-" * 92)
    print("%d / %d 통과" % (npass, len(results)))

    out = {"results": results, "passed": npass, "total": len(results)}
    path = os.path.join(HERE, "results", "p5_audit.json")
    from _journal import save_result
    save_result(path, out)
    print("saved:", path)
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
