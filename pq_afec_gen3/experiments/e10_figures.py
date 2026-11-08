import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
FIGS = os.path.join(HERE, "figures")
os.makedirs(FIGS, exist_ok=True)

for cand in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
    if any(f.name == cand for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 130
plt.rcParams["savefig.bbox"] = "tight"

C_MAIN = "#1f4e79"
C_ALT = "#c0504d"
C_3 = "#9bbb59"
C_4 = "#8064a2"
C_GREY = "#808080"


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
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(fig, name):
    p = os.path.join(FIGS, name)
    fig.savefig(p)
    plt.close(fig)
    print("  " + p)
    return p


def fig_mlkem(e1):
    kems = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

    ek = [e1["sizes"][k]["ek_bytes_raw"] for k in kems]
    ct = [e1["sizes"][k]["ct_bytes"] for k in kems]
    x = range(len(kems))
    ax1.bar([i - 0.2 for i in x], ek, 0.4, label="공개키 (ek)", color=C_MAIN)
    ax1.bar([i + 0.2 for i in x], ct, 0.4, label="암호문 (ct)", color=C_ALT)
    ax1.axhline(32, color=C_GREY, ls="--", lw=1)
    ax1.text(2.45, 60, "X25519 = 32 B", ha="right", fontsize=8, color=C_GREY)
    ax1.axhline(1150, color="k", ls=":", lw=1.2)
    ax1.text(-0.45, 1190, "QUIC Initial 1개 예산 1150 B", fontsize=8)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels([k.replace("ML-KEM-", "") for k in kems])
    ax1.set_xlabel("ML-KEM 파라미터")
    ax1.set_ylabel("바이트")
    ax1.set_title("(가) 키 크기 — FIPS 203과 실측 일치")
    ax1.legend(fontsize=8)

    ops = ["keygen", "encaps", "decaps"]
    labels = {"keygen": "키생성", "encaps": "캡슐화", "decaps": "복호화"}
    width = 0.2
    for i, k in enumerate(kems + ["X25519"]):
        t = e1["timing"].get(k)
        if not t:
            continue
        vals = [1e6 / t["%s_ops_median" % o] for o in ops]
        color = [C_MAIN, C_ALT, C_3, C_GREY][i]
        ax2.bar([j + (i - 1.5) * width for j in range(3)], vals, width,
                label=k, color=color)
    ax2.set_xticks(range(3))
    ax2.set_xticklabels([labels[o] for o in ops])
    ax2.set_ylabel("마이크로초 (us)")
    ax2.set_title("(나) 연산 시간 — ML-KEM 캡슐화가 X25519보다 빠르다")
    ax2.legend(fontsize=8)
    fig.suptitle("연구 내용 1 : ML-KEM 성능 실측 (OpenSSL 3.5.5, i7-14700HX)",
                 fontsize=12)
    return save(fig, "fig1_mlkem_performance.png")


def fig_split(e4, e5, e3):
    cap = e3["recommended_INITIAL_CRYPTO_CAPACITY"]
    nxt = e3["recommended_next_packet_capacity"]
    fig, ax = plt.subplots(figsize=(9, 4.6))

    xs = list(range(100, 2600, 5))
    ys = [1 if v <= cap else 1 + -(-(v - cap) // nxt) for v in xs]
    ax.step(xs, ys, where="post", color=C_GREY, lw=1.4,
            label="필요한 Initial 패킷 수 (RFC 9000/9001 프레이밍)")

    pts = []
    for key, v in e4.items():
        if not key.startswith("cloudflare.com/"):
            continue
        ch = v.get("clienthello")
        if not ch:
            continue
        g = key.split("/")[1]
        pts.append((g, ch["msg_wire_len"]))
    for g, v in sorted(pts, key=lambda t: t[1]):
        n = 1 if v <= cap else 1 + -(-(v - cap) // nxt)
        ax.plot([v], [n], "o", color=C_MAIN, ms=7)
        ax.annotate(g, (v, n), textcoords="offset points", xytext=(4, 7),
                    fontsize=7.5, color=C_MAIN)

    if e5 and "quic" in e5:
        q = e5["quic"]
        v = q["ch_wire"]
        n = 1 if v <= cap else 1 + -(-(v - cap) // nxt)
        ax.plot([v], [n], "*", color=C_ALT, ms=16)
        ax.annotate("Chrome 실측\n(%d B)" % v, (v, n),
                    textcoords="offset points", xytext=(6, -22),
                    fontsize=8, color=C_ALT)

    ax.axvline(cap, color="k", ls=":", lw=1)
    ax.text(cap + 15, 2.6, "1150 B", fontsize=8)
    ax.set_xlabel("ClientHello 크기 (바이트, QUIC CRYPTO 스트림 실측)")
    ax.set_ylabel("Initial 패킷 수")
    ax.set_yticks([1, 2, 3])
    ax.set_ylim(0.6, 3.4)
    ax.set_title("연구 내용 1 : ML-KEM이 ClientHello를 몇 개의 Initial로 쪼개는가\n"
                 "(파란 점 = openssl 최소 CH, 별 = 실제 Chrome — 같은 KEM이라도 "
                 "클라이언트에 따라 갈린다)", fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.25)
    return save(fig, "fig2_clienthello_split.png")


def fig_exchange(e6):
    ge = [(k, v) for k, v in e6["configs"].items() if v.get("model") == "gemodel"]
    uni = [(k, v) for k, v in e6["configs"].items() if v.get("model") == "bernoulli"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3))

    for items, lbl, col, mk in ((uni, "netem loss p% (독립)", C_GREY, "s"),
                                (ge, "netem loss gemodel (버스트)", C_MAIN, "o")):
        xs = [v["p_target"] * 100 for _, v in items]
        ys = [v["loss_rate"] * 100 for _, v in items]
        ax1.plot(xs, ys, mk, color=col, label=lbl, ms=7)
    lim = [0, 11]
    ax1.plot(lim, lim, "k:", lw=1, label="y = x")
    ax1.set_xlabel("netem 설정 손실률 (%)")
    ax1.set_ylabel("실측 손실률 (%)")
    ax1.set_title("(가) 손실률")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.25)

    xs = [v["burst_target"] for _, v in ge]
    ys = [v["mean_burst"] for _, v in ge]
    ax2.plot(xs, ys, "o", color=C_MAIN, ms=7, label="gemodel")
    ax2.plot([1, 9], [1, 9], "k:", lw=1, label="y = x")
    ax2.set_xlabel("목표 평균 버스트 길이 L")
    ax2.set_ylabel("실측 평균 버스트 길이")
    ax2.set_title("(나) 버스트 길이")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.25)
    fig.suptitle("연구 내용 2 : netem ↔ Gilbert-Elliott 환율표 검증\n"
                 "r = 1/L,  p = P*r/(1-P) 로 설정하면 실측이 목표를 그대로 따라온다",
                 fontsize=11)
    return save(fig, "fig3_netem_ge_exchange.png")


def fig_corr_trap(e6):
    items = sorted(((v["corr"], v["loss_rate"] * 100)
                    for k, v in e6["configs"].items()
                    if v.get("model") == "netem-correlated" and "corr" in v))
    if not items:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    xs = [a for a, _ in items]
    ys = [b for _, b in items]
    ax.plot(xs, ys, "o-", color=C_ALT, lw=2, ms=8)
    ax.axhline(5.0, color=C_MAIN, ls="--", lw=1.5, label="설정한 명목 손실률 5%")
    for x, y in items:
        ax.annotate("%.2f%%" % y, (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8)
    ax.set_xlabel("netem `loss 5%% CORR%%` 의 상관계수 (%)")
    ax.set_ylabel("실측 손실률 (%)")
    ax.set_ylim(-0.4, 6)
    ax.set_title("[주의] netem 상관 손실 모델의 함정 (실측)\n"
                 "상관을 켜면 실효 손실률이 무너진다 — 버스트 재현에 쓸 수 없다",
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    return save(fig, "fig4_netem_correlation_trap.png")


def fig_validation(e9):
    fig, ax = plt.subplots(figsize=(6.6, 6.2))
    ge_x, ge_y, bi_x, bi_y = [], [], [], []
    for name, t in e9["traces"].items():
        for row in t["rows"]:
            if row["empirical"] <= 0:
                continue
            ge_x.append(row["empirical"]); ge_y.append(max(row["ge_model"], 1e-9))
            bi_x.append(row["empirical"]); bi_y.append(max(row["binomial"], 1e-9))
    ax.loglog(bi_x, bi_y, "s", color=C_GREY, ms=5, alpha=0.75,
              label="이항분포 (버스트 무시)")
    ax.loglog(ge_x, ge_y, "o", color=C_MAIN, ms=6, label="GE-DP (제안 모델)")
    lo = min(min(ge_x), min(bi_x)) * 0.4
    hi = max(max(ge_x), max(ge_y)) * 2.2
    ax.plot([lo, hi], [lo, hi], "k:", lw=1.2, label="완전 일치")
    ax.plot([lo, hi], [lo * 0.5, hi * 0.5], color="k", lw=0.6, alpha=0.4)
    ax.plot([lo, hi], [lo * 2, hi * 2], color="k", lw=0.6, alpha=0.4)
    ax.text(hi * 0.55, hi * 1.5, "×2", fontsize=8, alpha=0.6)
    ax.text(hi * 0.9, hi * 0.35, "×0.5", fontsize=8, alpha=0.6)
    ax.set_xlabel("실측 블록 실패율 (진짜 netem 링크)")
    ax.set_ylabel("모델 예측 블록 실패율")
    s = e9["summary"]
    ax.set_title("검증 : 모델이 진짜 링크를 맞히는가\n"
                 "GE-DP 중앙비 %.2f배 · 95%%CI 적중 %.0f%% · "
                 "이항은 %.0f배 과소평가"
                 % (s["ge_ratio_median_burst"], s["ge_within_95ci_pct"],
                    s["burst_underestimate_median_x"] or 0), fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.25, which="both")
    return save(fig, "fig5_model_validation.png")


def fig_regret(e7):
    labels = ["none", "static", "rquic", "adaptive", "cached_ok",
              "cached_hi", "cached_lo"]
    ko = {"none": "FEC 없음", "static": "정적 FEC", "rquic": "rQUIC(임계값)",
          "adaptive": "적응형(콜드)", "cached_ok": "적응형+캐시(정확)",
          "cached_hi": "캐시 과대(×5)", "cached_lo": "캐시 과소(÷5)"}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    for ax, span, title in ((axes[0], "long", "긴 연결 (400 블록)"),
                            (axes[1], "short", "짧은 연결 (30 블록)")):
        w = e7[span + "_worst_regret"]
        vals = [w[l] * 100 for l in labels]
        cols = [C_GREY, C_GREY, C_GREY, C_ALT, C_MAIN, C_4, C_4]
        bars = ax.bar(range(len(labels)), vals, color=cols)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + max(vals) * 0.02,
                    "%.0f%%" % v, ha="center", fontsize=8)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels([ko[l] for l in labels], rotation=30, ha="right",
                           fontsize=8)
        ax.set_ylabel("최악 후회 (oracle 대비 전송시간 초과 %)")
        ax.set_title(title)
        ax.grid(alpha=0.25, axis="y")
    fig.suptitle("연구 내용 4 : 실측 netem 트레이스 %d개에서의 최악 후회 "
                 "(시드 %d개)" % (len(e7["long"]), e7["seeds"]), fontsize=11)
    return save(fig, "fig6_worst_case_regret.png")


def fig_handshake(e7):
    hs = e7["handshake"]
    names = sorted(hs, key=lambda n: e7["long"][n]["measured_loss"])
    x = range(len(names))
    fig, ax = plt.subplots(figsize=(11, 4.4))
    w = 0.27
    a = [hs[n]["x25519"]["mean_ms"] for n in names]
    b = [hs[n]["mlkem"]["mean_ms"] for n in names]
    c = [hs[n]["mlkem_fec"]["mean_ms"] for n in names]
    ax.bar([i - w for i in x], a, w, label="X25519 (대조군)", color=C_GREY)
    ax.bar(list(x), b, w, label="ML-KEM (FEC 없음)", color=C_ALT)
    ax.bar([i + w for i in x], c, w, label="ML-KEM + 적응형 FEC", color=C_MAIN)
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("핸드셰이크 평균 완료시간 (ms)")
    ax.set_title("연구 내용 4 : 실측 손실 트레이스 위에서의 핸드셰이크 완료시간",
                 fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, axis="y")
    return save(fig, "fig7_handshake_time.png")


def fig_cpu(e8):
    keys = [k for k in e8["grid"] if "c" in e8["grid"][k]]
    keys.sort(key=lambda s: (int(s.split("_")[0][1:]), int(s.split("_")[1][1:])))
    if not keys:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.2))
    x = range(len(keys))
    py = [e8["grid"][k]["python"]["encode_ms_per_repair_symbol"] * 1000 for k in keys]
    c = [e8["grid"][k]["c"]["encode_ms_per_repair_symbol"] * 1000 for k in keys]
    ax1.bar([i - 0.2 for i in x], py, 0.4, label="파이썬 (afec/rs.py)", color=C_GREY)
    ax1.bar([i + 0.2 for i in x], c, 0.4, label="C (gcc -O3 -march=native)",
            color=C_MAIN)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels([k.replace("k", "K=").replace("_r", ", r=") for k in keys],
                        rotation=30, ha="right", fontsize=8)
    ax1.set_ylabel("이중화 심볼당 부호화 시간 (us)")
    ax1.set_title("(가) 부호화 비용 — C는 100배가 아니라 약 4배 빠르다", fontsize=10)
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.25, axis="y")

    cpu = [e8["grid"][k]["c_cpu_fraction"] * 100 for k in keys]
    ax2.bar(list(x), cpu, 0.55, color=C_MAIN)
    for i, v in zip(x, cpu):
        ax2.text(i, v + max(cpu) * 0.02, "%.1f%%" % v, ha="center", fontsize=8)
    ax2.set_xticks(list(x))
    ax2.set_xticklabels([k.replace("k", "K=").replace("_r", ", r=") for k in keys],
                        rotation=30, ha="right", fontsize=8)
    ax2.set_ylabel("코어 1개 점유율 (%)")
    ax2.set_title("(나) %.0f Mbps 유지에 드는 CPU (C 부호기)" % e8["rate_mbps"],
                  fontsize=10)
    ax2.grid(alpha=0.25, axis="y")
    fig.suptitle("연구 내용 4 : FEC 부호화 CPU 사용량 실측", fontsize=11)
    return save(fig, "fig8_cpu_cost.png")


def fig_testbed(e12):
    conds = []
    for label, arm in e12["arms"].items():
        if arm["condition"] not in conds:
            conds.append(arm["condition"])
    ko = {"noloss": "무손실", "uniform_p2": "독립 2%", "uniform_p5": "독립 5%",
          "uniform_p10": "독립 10%", "burst_p5_L4": "버스트 5%/L4",
          "burst_p5_L8": "버스트 5%/L8"}

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
    for ax, stat, title in ((axes[0], "mean", "(가) 평균 핸드셰이크 완료시간"),
                            (axes[1], "p99", "(나) p99 — 손실의 대가는 꼬리에 있다")):
        x = range(len(conds))
        w = 0.27
        series = [
            ("x25519", "nofec", "X25519 (대조군)", C_GREY),
            ("X25519MLKEM768", "nofec", "ML-KEM (FEC 없음)", C_ALT),
            ("X25519MLKEM768", "fec", "ML-KEM + XOR 패리티", C_MAIN),
        ]
        for si, (grp, fec, lbl, col) in enumerate(series):
            vals = []
            for c in conds:
                a = e12["arms"].get("%s/%s/%s" % (c, grp, fec))
                vals.append(a["quantiles"].get(stat, 0) if a and a["quantiles"] else 0)
            ax.bar([i + (si - 1) * w for i in x], vals, w, label=lbl, color=col)
        ax.set_xticks(list(x))
        ax.set_xticklabels([ko.get(c, c) for c in conds], rotation=25,
                           ha="right", fontsize=8)
        ax.set_ylabel("ms")
        ax.set_title(title, fontsize=10)
        ax.grid(alpha=0.25, axis="y")
        if stat == "mean":
            ax.legend(fontsize=8)
    fig.suptitle("실측 테스트베드 : quic-go + 진짜 ML-KEM + 진짜 XOR 패리티 "
                 "(netem, MTU 1500, RTT %.0fms, 조건당 n=%d)"
                 % (e12["rtt_ms"], e12["n"]), fontsize=11)
    return save(fig, "fig9_live_testbed.png")


def main():
    _harden()
    print("E10 - figures")
    e1, e3, e4 = load("e1_mlkem.json"), load("e3_quic.json"), load("e4_quic_clienthello.json")
    e5, e6, e7 = load("e5_browser_ch.json"), load("e6_netem.json"), load("e7_policy.json")
    e8, e9 = load("e8_cpu.json"), load("e9_validation.json")
    e12 = load("e12_quic_testbed.json")
    made = []
    if e1:
        made.append(fig_mlkem(e1))
    if e4 and e3:
        made.append(fig_split(e4, e5, e3))
    if e6:
        made.append(fig_exchange(e6))
        made.append(fig_corr_trap(e6))
    if e9:
        made.append(fig_validation(e9))
    if e7:
        made.append(fig_regret(e7))
        made.append(fig_handshake(e7))
    if e8:
        made.append(fig_cpu(e8))
    if e12:
        made.append(fig_testbed(e12))
    print("%d figures written to %s" % (len([m for m in made if m]), FIGS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
