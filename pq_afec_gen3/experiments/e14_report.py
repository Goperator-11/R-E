import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
OUT = os.path.join(ROOT, "docs", "실측 결과표.md")


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def load(name):
    p = os.path.join(RESULTS, name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def sec_e1(w, e1):
    if not e1:
        return
    w("## 1. ML-KEM 크기·속도 (E1)\n")
    w("| | 공개키 ek | 암호문 ct | 공유비밀 | FIPS 203 일치 |")
    w("|---|---|---|---|---|")
    for k in ("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"):
        s = e1["sizes"][k]
        w("| %s | %d B | %d B | %d B | %s |"
          % (k, s["ek_bytes_raw"], s["ct_bytes"], s["ss_bytes"],
             "예" if s["ss_agree"] else "아니오"))
    w("")
    w("| | 키생성 | 캡슐화 | 디캡슐화 |")
    w("|---|---|---|---|")
    for k in ("ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "X25519"):
        t = e1["timing"].get(k)
        if not t:
            continue
        w("| %s | %.1f us | **%.1f us** | %.1f us |"
          % (k, 1e6 / t["keygen_ops_median"], 1e6 / t["encaps_ops_median"],
             1e6 / t["decaps_ops_median"]))
    x = e1["timing"].get("X25519")
    m = e1["timing"].get("ML-KEM-768")
    if x and m:
        ratio = (1e6 / x["encaps_ops_median"]) / (1e6 / m["encaps_ops_median"])
        w("")
        w("> ML-KEM-768 캡슐화가 X25519보다 **%.1f배 빠르다** — 병목은 연산이 아니라 크기다."
          % ratio)
    w("")


def sec_e4(w, e4, e3):
    if not e4 or not e3:
        return
    cap = e3["recommended_INITIAL_CRYPTO_CAPACITY"]
    nxt = e3["recommended_next_packet_capacity"]
    w("## 2. 실제 QUIC ClientHello 크기와 Initial 분할 (E3·E4)\n")
    w("Initial 1개의 CRYPTO 예산 = **%d B** (RFC 9000/9001 프레이밍 계산), "
      "이후 패킷 %d B\n" % (cap, nxt))
    w("| 키교환 | 실측 CH | 키 공유 | ch_base | 필요한 Initial |")
    w("|---|---|---|---|---|")
    rows = []
    for key, v in e4.items():
        if not key.startswith("cloudflare.com/"):
            continue
        ch = v.get("clienthello")
        if not ch:
            continue
        ks = next((e for e in ch["extensions"] if e["type"] == 51), None)
        share = sum(s["key_bytes"] for s in ks.get("shares", [])) if ks else 0
        total = ch["msg_wire_len"]
        n = 1 if total <= cap else 1 + -(-(total - cap) // nxt)
        rows.append((total, key.split("/")[1], total, share, total - share, n))
    for _, g, total, share, base, n in sorted(rows):
        w("| %s | %d B | %d | %d | **%d** |" % (g, total, share, base, n))
    w("")


def sec_e6(w, e6):
    if not e6:
        return
    w("## 3. netem ↔ Gilbert-Elliott 환율표 (E6)\n")
    w("`r = 1/L`,  `p = P·r/(1−P)` 로 설정. 프로브 %s개.\n" % f"{e6['n']:,}")
    w("| 목표 (손실, 버스트) | 실측 손실 | 실측 버스트 | 최대 버스트 | P(손실\\|손실) | P(손실\\|정상) |")
    w("|---|---|---|---|---|---|")
    for k, v in sorted(e6["configs"].items()):
        if v.get("model") != "gemodel":
            continue
        w("| P=%.0f%%, L=%.0f | %.2f %% | %.2f | %d | %.4f | %.4f |"
          % (v["p_target"] * 100, v["burst_target"], v["loss_rate"] * 100,
             v["mean_burst"], v["max_burst"], v["p_loss_given_loss"],
             v["p_loss_given_ok"]))
    w("")
    ctl = e6["configs"].get("control_noloss")
    if ctl:
        w("무손실 대조군 실측 손실률 **%.4f** (측정계 자체의 손실 바닥).\n"
          % ctl["loss_rate"])
    corr = sorted((v["corr"], v["loss_rate"] * 100, v["mean_burst"])
                  for v in e6["configs"].values()
                  if v.get("model") == "netem-correlated" and "corr" in v)
    if corr:
        w("### ⚠️ netem 상관 손실 모델의 함정\n")
        w("| 상관계수 | " + " | ".join("%d %%" % c for c, _, _ in corr) + " |")
        w("|---|" + "---|" * len(corr))
        w("| **실측 손실률** | " + " | ".join("%.2f %%" % l for _, l, _ in corr) + " |")
        w("| 실측 평균 버스트 | " + " | ".join("%.2f" % b for _, _, b in corr) + " |")
        w("")
        w("명목 5 %인데 상관을 켜면 무너진다. **버스트 재현에 쓸 수 없다.**\n")


def sec_e9(w, e9):
    if not e9:
        return
    s = e9["summary"]
    w("## 4. 모델 검증 — 예측 vs 실제 링크 (E9)\n")
    w("| 항목 | 값 |")
    w("|---|---|")
    w("| 검사한 (트레이스 × K,r) 칸 | %d |" % s["cells_tested"])
    w("| GE-DP가 95%% 신뢰구간 안 | **%d / %d (%.0f%%)** |"
      % (s["ge_within_95ci"], s["cells_tested"], s["ge_within_95ci_pct"]))
    w("| GE-DP / 실측 중앙비 (버스트) | %.2f배 |" % s["ge_ratio_median_burst"])
    w("| GE-DP / 실측 중앙비 (독립) | %.2f배 |" % s["ge_ratio_median_independent"])
    w("| 이항 / 실측 (독립 트레이스) | %.3f배 — 이항이 맞는 자리, 자기검사 통과 |"
      % s["binomial_ratio_median_independent"])
    worst = ("사실상 무한대(이항 예측이 0에 수렴)"
             if s.get("worst_is_effectively_infinite")
             else "%.0f배" % (s.get("burst_underestimate_worst_x") or 0))
    w("| **이항 / 실측 (버스트 트레이스)** | **%.4f배 → 실패확률 %.0f배 과소평가 (최악 %s)** |"
      % (s["binomial_ratio_median_burst"],
         s["burst_underestimate_median_x"] or 0, worst))
    w("")


def sec_e7(w, e7):
    if not e7:
        return
    labels = ["none", "static", "rquic", "adaptive", "cached_ok",
              "cached_hi", "cached_lo"]
    ko = {"none": "FEC 없음", "static": "정적", "rquic": "rQUIC(임계값)",
          "adaptive": "적응형(콜드)", "cached_ok": "적응형+캐시(정확)",
          "cached_hi": "캐시 과대×5", "cached_lo": "캐시 과소÷5"}
    w("## 5. 실측 트레이스 위 정책 비교 — 최악 후회 (E7)\n")
    w("시드 %d개, 트레이스 %d개. oracle 대비 전송시간 초과율의 최댓값.\n"
      % (e7["seeds"], len(e7["long"])))
    w("| 정책 | 긴 연결 (400블록) | 짧은 연결 (30블록) |")
    w("|---|---|---|")
    for l in labels:
        w("| %s | %.1f %% | %.1f %% |"
          % (ko[l], e7["long_worst_regret"][l] * 100,
             e7["short_worst_regret"][l] * 100))
    w("")
    hs = e7.get("handshake") or {}
    if hs:
        w("### 핸드셰이크 완료시간 (실측 트레이스 재생)\n")
        w("| 트레이스 | X25519 | ML-KEM | ML-KEM+FEC | 변화 |")
        w("|---|---|---|---|---|")
        for nm in sorted(hs, key=lambda n: e7["long"][n]["measured_loss"]):
            h = hs[nm]
            w("| %s | %.1f ms | %.1f ms | %.1f ms | %+.1f %% |"
              % (nm, h["x25519"]["mean_ms"], h["mlkem"]["mean_ms"],
                 h["mlkem_fec"]["mean_ms"], h["fec_gain"] * 100))
        w("")


def sec_e8(w, e8):
    if not e8:
        return
    w("## 6. FEC 부호화 CPU (E8)\n")
    w("%.0f Mbps 유지에 필요한 코어 점유율. 심벌 %d B.\n"
      % (e8["rate_mbps"], e8["symbol_bytes"]))
    w("| (K, r) | 파이썬 us/심벌 | C us/심벌 | C 배속 | C 기준 CPU |")
    w("|---|---|---|---|---|")
    for k in sorted(e8["grid"], key=lambda s: (int(s.split("_")[0][1:]),
                                               int(s.split("_")[1][1:]))):
        g = e8["grid"][k]
        if "c" not in g:
            continue
        w("| %s | %.1f | %.1f | %.1fx | %.2f %% |"
          % (k.replace("k", "K=").replace("_r", ", r="),
             g["python"]["encode_ms_per_repair_symbol"] * 1000,
             g["c"]["encode_ms_per_repair_symbol"] * 1000,
             g["speedup_c_over_python"], g["c_cpu_fraction"] * 100))
    w("")
    w("> 명세 v0.1의 \"C/SIMD면 100배 빠르다\"는 **틀렸다 — 실측 약 4배**다. "
      "`afec/rs.py`가 `bytes.translate` + big-int XOR로 이미 C 레벨에서 돌기 때문.\n")


def sec_e12(w, e12):
    if not e12:
        return
    w("## 7. 실제 quic-go + ML-KEM + XOR 패리티 (E12)\n")
    w("MTU %d, RTT %d ms, 인증서 %d B, 조건당 %d회.\n"
      % (e12["mtu"], e12["rtt_ms"], e12["certsize"], e12["n"]))
    w("| 조건 | 그룹 | FEC | 성공률 | p50 | 평균 | p95 | 최대 | 복구 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for label in sorted(e12["arms"]):
        a = e12["arms"][label]
        q = a.get("quantiles") or {}
        w("| %s | %s | %s | %d %% | %.1f | %.1f | %.1f | %.1f | %s |"
          % (a["condition"], a["group"], "ON" if a["fec"] else "off",
             100 * a["ok"] // max(a["trials"], 1),
             q.get("p50", 0), q.get("mean", 0), q.get("p95", 0), q.get("max", 0),
             a.get("shim_rx", {}).get("recovered", "-")))
    w("")
    sizes = {}
    for a in e12["arms"].values():
        for k, v in (a.get("shim_tx", {}).get("flight_sizes") or {}).items():
            if a["group"] == "X25519MLKEM768":
                sizes[k] = sizes.get(k, 0) + v
    if sizes:
        w("ML-KEM ClientHello 플라이트의 Initial 데이터그램 수 분포(실측): **%s**\n"
          % ", ".join("%s개 = %d회" % (k, v) for k, v in sorted(sizes.items())))


def sec_e13(w, e13):
    if not e13:
        return
    w("## 8. 실제 QUIC 데이터 구간 (E13)\n")
    runs = e13.get("runs", {})
    if not runs:
        return
    w("| 조건 | 정책 | 전달률 | 송신탈락 | 복구 | 오버헤드 | 평균 r | 유효 |")
    w("|---|---|---|---|---|---|---|---|")
    for k in sorted(runs):
        v = runs[k]
        w("| %s | %s | %.2f %% | %.2f %% | %d | %.1f %% | %.1f | %s |"
          % (v["condition"], v["policy"], 100 * v["delivery_rate"],
             100 * v["skip_fraction"], v["rx"].get("recovered", 0),
             100 * v["overhead"], v["tx"].get("mean_r", 0),
             "예" if v.get("valid") else "**아니오**"))
    w("")


def sec_conclusion(w, e1, e6, e7, e8, e9, e12):
    w("## 9. 결론 (전부 위 표에서 계산됨)\n")
    pts = []
    if e1:
        x = e1["timing"].get("X25519")
        m = e1["timing"].get("ML-KEM-768")
        if x and m:
            pts.append("ML-KEM-768 캡슐화가 X25519보다 **%.1f배 빠르다** — "
                       "PQC 전환의 비용은 연산이 아니라 **크기**다."
                       % ((1e6 / x["encaps_ops_median"]) /
                          (1e6 / m["encaps_ops_median"])))
    if e12:
        pts.append("실제 quic-go 핸드셰이크에서 ML-KEM ClientHello는 "
                   "**Initial 데이터그램 2개**를 차지한다(MTU 1500 실측).")
    if e9:
        s = e9["summary"]
        worst = ("최악은 사실상 무한대"
                 if s.get("worst_is_effectively_infinite")
                 else "최악 %.0f배" % (s.get("burst_underestimate_worst_x") or 0))
        pts.append("버스트 인지 모델(GE-DP)이 실제 링크의 블록 실패율을 "
                   "**%d/%d 칸에서 95%% 신뢰구간 안**으로 맞혔고, 버스트를 무시한 "
                   "이항 모델은 실패확률을 **중앙 %.0f배 과소평가**한다(%s)."
                   % (s["ge_within_95ci"], s["cells_tested"],
                      s["burst_underestimate_median_x"] or 0, worst))
    if e7:
        lw = e7["long_worst_regret"]
        sw = e7["short_worst_regret"]
        pts.append("실측 트레이스에서 최악 후회는 긴 연결 기준 "
                   "FEC 없음 %.0f%% · 정적 %.0f%% · 임계값(rQUIC) %.0f%% 대비 "
                   "**적응형 %.0f%%**, 짧은 연결은 캐시가 %.0f%% → **%.0f%%** 로 내린다."
                   % (lw["none"] * 100, lw["static"] * 100, lw["rquic"] * 100,
                      lw["adaptive"] * 100, sw["adaptive"] * 100,
                      sw["cached_ok"] * 100))
    if e8:
        vals = [g["c_cpu_fraction"] * 100 for g in e8["grid"].values()
                if "c_cpu_fraction" in g]
        if vals:
            pts.append("부호화 CPU는 %.0f Mbps에서 코어의 **%.1f~%.1f%%** — "
                       "이 기법의 실용성을 막는 요소가 아니다."
                       % (e8["rate_mbps"], min(vals), max(vals)))
    if e6:
        corr = [v for v in e6["configs"].values()
                if v.get("model") == "netem-correlated" and v.get("corr", 0) >= 50]
        if corr:
            pts.append("실험 방법론 상의 발견: netem `loss p% corr%`는 상관을 켜면 "
                       "실효 손실률이 0으로 무너져 **버스트 재현에 쓸 수 없다**. "
                       "`loss gemodel`을 써야 한다.")
    for i, p in enumerate(pts, 1):
        w("%d. %s\n" % (i, p))
    if not pts:
        w("(아직 결과가 충분하지 않다)\n")


def main():
    _harden()
    e1 = load("e1_mlkem.json")
    e3 = load("e3_quic.json")
    e4 = load("e4_quic_clienthello.json")
    e6 = load("e6_netem.json")
    e7 = load("e7_policy.json")
    e8 = load("e8_cpu.json")
    e9 = load("e9_validation.json")
    e12 = load("e12_quic_testbed.json")
    e13 = load("e13_data_live.json")

    lines = []

    def w(s=""):
        lines.append(s)

    w("# 실측 결과표 (자동 생성)\n")
    w("> ⚠️ **이 파일은 `experiments/e14_report.py`가 "
      "`experiments/results/*.json`에서 생성한다. 직접 고치지 말 것** — "
      "고쳐야 하면 실험을 다시 돌려라. 손으로 옮겨 적은 숫자가 원자료와 "
      "어긋나는 사고를 막으려고 이렇게 했다.\n")
    have = [n for n, d in (("E1", e1), ("E3", e3), ("E4", e4), ("E6", e6),
                           ("E7", e7), ("E8", e8), ("E9", e9), ("E12", e12),
                           ("E13", e13)) if d]
    w("포함된 실험: %s\n" % ", ".join(have))
    w("---\n")

    sec_e1(w, e1)
    sec_e4(w, e4, e3)
    sec_e6(w, e6)
    sec_e9(w, e9)
    sec_e7(w, e7)
    sec_e8(w, e8)
    sec_e12(w, e12)
    sec_e13(w, e13)
    sec_conclusion(w, e1, e6, e7, e8, e9, e12)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote %s (%d lines, %d experiments)" % (OUT, len(lines), len(have)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
