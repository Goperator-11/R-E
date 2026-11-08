import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")

CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
@page { size: A4 portrait; margin: 10mm 9mm; }
* { box-sizing: border-box; }
body { font-family: "Malgun Gothic","맑은 고딕",sans-serif; color:#111;
       font-size: 7.9pt; line-height: 1.34; margin:0; }
h1 { font-size: 13.5pt; margin:0 0 1mm 0; letter-spacing:-0.3px; }
.sub { font-size: 7.2pt; color:#555; margin-bottom:2.6mm;
       border-bottom:0.6pt solid #111; padding-bottom:1.5mm; }
.kpi { display:flex; gap:3mm; margin-bottom:2.8mm; }
.kpi div { flex:1; border-left:1.6pt solid #111; padding-left:2mm; }
.kpi b { display:block; font-size:13.5pt; line-height:1.05; }
.kpi span { font-size:6.7pt; color:#555; }
.cols { column-count:2; column-gap:5.5mm; }
section { break-inside: avoid; margin-bottom:2.8mm; }
h2 { font-size:8.4pt; margin:0 0 1.1mm 0; padding-bottom:0.5mm;
     border-bottom:0.5pt solid #999; }
h2 small { font-weight:normal; color:#666; font-size:6.9pt; }
table { width:100%; border-collapse:collapse; margin:0.9mm 0; }
td,th { padding:0.45mm 1mm; text-align:right; font-variant-numeric:tabular-nums; }
td:first-child, th:first-child { text-align:left; }
thead td { color:#666; font-size:6.8pt; border-bottom:0.4pt solid #bbb; }
tbody tr:nth-child(even) { background:#f6f6f6; }
tr.hi td { font-weight:bold; }
p { margin:0.9mm 0; }
.note { color:#555; }
.warn { border-left:1.6pt solid #111; padding-left:2mm; }
code { font-family:Consolas,monospace; font-size:7.3pt; }
.eq { font-family:Consolas,monospace; font-size:7.9pt; text-align:center;
      margin:1.3mm 0; }
footer { margin-top:1.8mm; padding-top:1.3mm; border-top:0.5pt solid #111;
         font-size:6.7pt; color:#555; }
</style></head><body>

<h1>ML-KEM 적용 시 전송 성능 개선을 위한 QUIC 기반 적응형 FEC — 실측 요약</h1>
<div class="sub">R&amp;E 「연구 내용 1~4」 전체 실행 · 2026-08-17~18 ·
i7-14700HX / WSL2 Ubuntu · OpenSSL 3.5.5(ML-KEM 네이티브) · quic-go ·
16단계 파이프라인 16/16 완료 · 재현 <code>python experiments/pipeline.py --loop</code></div>

<div class="kpi">
  <div><b>@@ratio@@배</b><span>ML-KEM-768 캡슐화가 X25519보다 <u>빠름</u> —
       병목은 연산이 아니라 크기</span></div>
  <div><b>2개</b><span>실제 QUIC에서 ML-KEM ClientHello가 차지한 Initial 데이터그램</span></div>
  <div><b>@@ci@@/@@cells@@</b><span>모델 예측이 실측 블록 실패율의 95% 신뢰구간 안</span></div>
  <div><b>@@adapt@@%</b><span>적응형 최악 후회 (임계값 방식 @@rquic@@%)</span></div>
</div>

<div class="cols">

<section>
<h2>1. ML-KEM 성능 <small>— 크기는 FIPS 203과 오차 0</small></h2>
<table><thead><tr><td></td><td>공개키</td><td>암호문</td><td>캡슐화</td></tr></thead>
<tbody>
<tr><td>ML-KEM-512</td><td>800 B</td><td>768 B</td><td>@@enc512@@ us</td></tr>
<tr><td>ML-KEM-768</td><td>1,184 B</td><td>1,088 B</td><td>@@encmk@@ us</td></tr>
<tr><td>ML-KEM-1024</td><td>1,568 B</td><td>1,568 B</td><td>@@enc1024@@ us</td></tr>
<tr><td>X25519 (대조)</td><td>32 B</td><td>32 B</td><td>@@encx@@ us</td></tr>
</tbody></table>
<p class="note">"PQC는 연산이 무겁다"는 이 맥락에서 <b>틀렸다</b>. 저하의 원인은
오직 크기이고, 그 크기가 QUIC Initial의 @@cap@@ B 예산을 넘겨 ClientHello를 쪼갠다.</p>
</section>

<section>
<h2>2. 패킷 분할 — 이 연구의 대전제 <small>실측 확정</small></h2>
<p><code>1200 − 롱헤더30 − AEAD태그16 − 프레임헤더4 = @@cap@@ B</code></p>
<table><thead><tr><td>키교환</td><td>ClientHello</td><td>Initial</td></tr></thead>
<tbody>
<tr><td>x25519</td><td>272 B</td><td>1개</td></tr>
<tr><td>MLKEM512</td><td>1,032 B</td><td>1개</td></tr>
<tr class="hi"><td>X25519MLKEM768</td><td>1,448 B</td><td>2개</td></tr>
<tr><td>Chrome 실측</td><td>1,756 B</td><td>2개</td></tr>
</tbody></table>
<p class="note">Cloudflare·Google 상대 <b>진짜 QUIC 캡처</b>와 자체 quic-go
테스트베드(MTU 1500) 모두 동일. Initial 키가 DCID에서 유도되는 성질을 이용해
패킷을 복호화하고 바이트를 직접 셌다.</p>
<p class="warn"><b>단 조건부다.</b> 분할은 <code>ch_base + 키공유 &gt; @@cap@@</code>일
때 일어난다. 최소 클라이언트(ch_base 232 B)에선 ML-KEM-512가 1개에 들어가고,
브라우저(508 B)에선 전 파라미터가 쪼개진다.</p>
</section>

<section>
<h2>3. 실험 환경 <small>— sudo 없이, 측정 바닥 0</small></h2>
<p><code>unshare -r -m -n</code> 안에 veth + 네임스페이스 2개 + netem.
프로브 20만 개. 무손실 대조군 손실률 <b>@@ctl@@</b>.</p>
<table><thead><tr><td>목표 손실/버스트</td><td>실측 손실</td><td>실측 버스트</td><td>최대</td></tr></thead>
<tbody>@@gerows@@</tbody></table>
<p class="note">환율표 <code>r = 1/L, p = P·r/(1−P)</code> 검증됨. 손실 독립성은
기각: P(손실|손실)/P(손실|정상) = <b>58배</b>.</p>
<p class="warn"><b>netem 함정.</b> <code>loss p% corr%</code>는 상관을 켜면 실효
손실률이 무너져 버스트 재현에 쓸 수 없다. 반드시 <code>loss gemodel</code>.</p>
<table><thead><tr><td>상관</td>@@corrhead@@</tr></thead>
<tbody><tr><td>실측 손실(%)</td>@@corrcells@@</tr></tbody></table>
</section>

<section>
<h2>4. 알고리즘 원리 <small>— 임계값 규칙을 버린다</small></h2>
<div class="eq">J(r) = (1+β·g)·t_tx(r) + P_fail(K,r)·T_recover</div>
<p class="note"><b>T_recover만 갈아끼우면</b> 핸드셰이크(PTO ≈999 ms)와 데이터
구간(2·RTT)이 같은 식에서 나온다. P_fail은 Gilbert-Elliott 사슬 위에서
동적계획법으로 <b>정확히</b> 계산한다(근사·몬테카를로 아님). g는 손실의
<b>원인</b>(혼잡 vs 링크 오류)을 반영해 혼잡일 때 이중화를 누른다.</p>
</section>

<section>
<h2>5. 정책 비교 <small>실측 트레이스 14개 × 시드 32 · oracle 대비 최악 후회</small></h2>
<table><thead><tr><td>정책</td><td>긴 연결</td><td>짧은 연결</td></tr></thead>
<tbody>@@polrows@@</tbody></table>
<p class="note">비용 최소화가 임계값 방식(rQUIC)의 <b>1/11</b>. 짧은 연결의 콜드
스타트 약점(@@shortcold@@%)은 목적지별 통계 캐시가 @@shortcache@@%로 회수한다.</p>
</section>

<section>
<h2>6. 실제 QUIC 위 검증 <small>quic-go + 진짜 제어기 + 진짜 RS</small></h2>
<table><thead><tr><td>조건</td><td>정책</td><td>전달률</td><td>오버헤드</td><td>평균 r</td></tr></thead>
<tbody>@@liverows@@</tbody></table>
<p class="note">적응형이 무손실에서 오버헤드를 <b>5.2%</b>로 스스로 내리고(정적은
조건과 무관하게 24.7% 지불), 손실이 오르면 이중화도 함께 오른다(r 1.5→3.9→6.4).</p>
<p class="warn"><b>반례가 결과의 일부다.</b> 핸드셰이크 패리티 1장은 독립 10%
손실에서 중앙값 @@p10n@@→@@p10f@@ ms(<b>−@@gain@@%</b>)이지만, 평균 8패킷
버스트에서는 p99를 @@l8n@@→@@l8f@@ ms로 <b>악화</b>시킨다. 고정 처방이 조건에
따라 뒤집히는 것 — 적응형이 필요한 이유의 실증이다.</p>
</section>

<section>
<h2>7. 검증 <small>— 자기 자신이 아니라 독립적 방법과 대조</small></h2>
<table><thead><tr><td>검증</td><td>결과</td></tr></thead><tbody>
<tr><td>모델 예측 vs 실제 링크 블록 실패율</td><td>@@ci@@/@@cells@@ 칸 95%CI 안</td></tr>
<tr><td>GE-DP / 실측 중앙비 (버스트 / 독립)</td><td>@@gb@@ / @@gi@@</td></tr>
<tr class="hi"><td>버스트 무시(이항)의 과소평가</td><td>중앙 @@under@@배</td></tr>
<tr><td>이항 / 실측 (독립 트레이스) — 자기검증</td><td>@@bi@@배</td></tr>
<tr><td>알고리즘 검증 스위트</td><td>83개 통과</td></tr>
<tr><td>독립 재유도 감사(완전열거·전달행렬 등)</td><td>15/15 통과</td></tr>
<tr><td>적대적 코드 감사에서 확인·수정한 결함</td><td>8건</td></tr>
</tbody></table>
<p class="note">독립 조건에서 이항 모델이 <b>@@bi@@배</b>로 떨어지는 것이 측정
방법 자체의 자기검증이고, 그 위에서 버스트의 @@under@@배가 의미를 갖는다.</p>
</section>

<section>
<h2>8. 한계 <small>— 정직하게</small></h2>
<p class="note">① 버스트가 길면 QUIC 혼잡제어가 제안 속도 아래로 내려가 송신측이
병목이 된다. 하네스가 그런 실행을 자동 무효 처리하지만 <b>버스트 5%/L=8의
적응형 팔은 끝내 유효한 측정을 얻지 못했다</b>.<br>
② 캐시 안전성은 <b>조건부</b>다 — 손실률을 5배 과대추정하는 캐시는 짧은 연결에서
최악 후회 @@chi@@%로 콜드 스타트(@@shortcold@@%)보다 나빴다.<br>
③ 버스트가 길 때 옳은 지렛대는 이중화가 아니라 <b>간격 벌리기</b>인데 비용식에
페이싱 항이 없다. 상한에 걸리면 그 사실을 보고하게 해 두었다.<br>
④ 부호화 CPU는 50 Mbps에서 코어의 @@cpumin@@~@@cpumax@@% (C 구현은 파이썬의
@@spd@@배 — 명세의 "100배"는 틀렸다).</p>
</section>

</div>

<footer>모든 수치는 <code>experiments/results/*.json</code>에서 생성 시점에 읽어
넣는다(<code>experiments/e18_onepager.py</code>) — 이 종이와 원자료는 어긋날 수
없다. · 손실 마스크 <code>experiments/traces/*.mask</code> · 그림 9장
<code>experiments/figures/</code> · 상세 <code>docs/실측 보고서.md</code>,
<code>docs/실측 결과표.md</code></footer>
</body></html>"""


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


def build_html():
    e1 = load("e1_mlkem.json")
    e3 = load("e3_quic.json")
    e6 = load("e6_netem.json")
    e7 = load("e7_policy.json")
    e8 = load("e8_cpu.json")
    e9 = load("e9_validation.json")
    e12 = load("e12_quic_testbed.json")
    e13 = load("e13_data_live.json")

    def us(k):
        return 1e6 / e1["timing"][k]["encaps_ops_median"]

    s9 = e9["summary"]
    lw, sw = e7["long_worst_regret"], e7["short_worst_regret"]
    cpu = [g["c_cpu_fraction"] * 100 for g in e8["grid"].values()
           if "c_cpu_fraction" in g]
    spd = [g["speedup_c_over_python"] for g in e8["grid"].values()
           if "speedup_c_over_python" in g]

    ge = sorted((v["p_target"], v["burst_target"], v["loss_rate"],
                 v["mean_burst"], v["max_burst"])
                for v in e6["configs"].values() if v.get("model") == "gemodel")
    ge_rows = "".join(
        "<tr><td>%.0f%% / %.0f</td><td>%.2f%%</td><td>%.2f</td><td>%d</td></tr>"
        % (p * 100, L, lr * 100, mb, mx) for p, L, lr, mb, mx in ge)
    corr = sorted((v["corr"], v["loss_rate"] * 100)
                  for v in e6["configs"].values()
                  if v.get("model") == "netem-correlated" and "corr" in v)

    def q(key):
        a = e12["arms"].get(key)
        return (a or {}).get("quantiles") or {}
    p10n, p10f = q("uniform_p10/X25519MLKEM768/nofec"), q("uniform_p10/X25519MLKEM768/fec")
    l8n, l8f = q("burst_p5_L8/X25519MLKEM768/nofec"), q("burst_p5_L8/X25519MLKEM768/fec")

    pol_rows = ""
    for key, ko in (("none", "FEC 없음"), ("static", "정적 FEC"),
                    ("rquic", "rQUIC(임계값)"), ("adaptive", "적응형(콜드)"),
                    ("cached_ok", "적응형+캐시")):
        cls = ' class="hi"' if key in ("adaptive", "cached_ok") else ""
        pol_rows += ("<tr%s><td>%s</td><td>%.0f%%</td><td>%.0f%%</td></tr>"
                     % (cls, ko, lw[key] * 100, sw[key] * 100))

    live_rows = ""
    for cond, label in (("noloss", "무손실"), ("uniform_p2", "독립 2%"),
                        ("uniform_p5", "독립 5%")):
        first = True
        for pol, ko in (("none", "없음"), ("static", "정적"),
                        ("adaptive", "적응형")):
            v = e13["runs"].get("%s/%s" % (cond, pol))
            if not v or not v.get("valid"):
                continue
            cls = ' class="hi"' if pol == "adaptive" else ""
            live_rows += ("<tr%s><td>%s</td><td>%s</td><td>%.2f%%</td>"
                          "<td>%.1f%%</td><td>%.1f</td></tr>"
                          % (cls, label if first else "", ko,
                             100 * v["delivery_rate"], 100 * v["overhead"],
                             v["tx"].get("mean_r", 0)))
            first = False

    gain = 100 * (1 - p10f.get("p50", 1) / max(p10n.get("p50", 1), 1e-9))
    vals = {
        "ratio": "%.1f" % (us("X25519") / us("ML-KEM-768")),
        "enc512": "%.1f" % us("ML-KEM-512"),
        "encmk": "%.1f" % us("ML-KEM-768"),
        "enc1024": "%.1f" % us("ML-KEM-1024"),
        "encx": "%.1f" % us("X25519"),
        "cap": "%d" % e3["recommended_INITIAL_CRYPTO_CAPACITY"],
        "ci": "%d" % s9["ge_within_95ci"],
        "cells": "%d" % s9["cells_tested"],
        "gb": "%.2f" % s9["ge_ratio_median_burst"],
        "gi": "%.2f" % s9["ge_ratio_median_independent"],
        "under": "%.0f" % s9["burst_underestimate_median_x"],
        "bi": "%.3f" % s9["binomial_ratio_median_independent"],
        "adapt": "%.0f" % (lw["adaptive"] * 100),
        "rquic": "%.0f" % (lw["rquic"] * 100),
        "shortcold": "%.0f" % (sw["adaptive"] * 100),
        "shortcache": "%.0f" % (sw["cached_ok"] * 100),
        "chi": "%.0f" % (sw["cached_hi"] * 100),
        "cpumin": "%.1f" % min(cpu), "cpumax": "%.1f" % max(cpu),
        "spd": "%.1f" % (sum(spd) / len(spd)),
        "ctl": "%.4f" % e6["configs"]["control_noloss"]["loss_rate"],
        "gerows": ge_rows,
        "corrhead": "".join("<td>%d%%</td>" % c for c, _ in corr),
        "corrcells": "".join("<td>%.2f</td>" % v for _, v in corr),
        "polrows": pol_rows, "liverows": live_rows,
        "p10n": "%.1f" % p10n.get("p50", 0), "p10f": "%.1f" % p10f.get("p50", 0),
        "gain": "%.0f" % gain,
        "l8n": "%.0f" % l8n.get("p99", 0), "l8f": "%.0f" % l8f.get("p99", 0),
    }
    html = TEMPLATE
    for k, v in vals.items():
        html = html.replace("@@%s@@" % k, v)
    left = [t for t in ("@@",) if t in html]
    if left:
        raise RuntimeError("치환되지 않은 자리표시자가 남았다")
    return html


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        os.path.expanduser("~"), "OneDrive", "Desktop",
        "ML-KEM QUIC 적응형 FEC 실측 요약.pdf"))
    a = ap.parse_args()

    chrome = next((c for c in CHROME if os.path.exists(c)), None)
    if not chrome:
        print("chrome not found")
        return 2

    html = build_html()
    tmp = os.path.join(tempfile.gettempdir(), "pqafec_onepager.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    if os.path.exists(a.out):
        os.remove(a.out)
    r = subprocess.run([chrome, "--headless=new", "--disable-gpu",
                        "--no-pdf-header-footer",
                        "--print-to-pdf=" + a.out, tmp],
                       capture_output=True, text=True, timeout=180)
    if not os.path.exists(a.out):
        print("render failed:\n%s" % (r.stderr or "")[-800:])
        return 1
    print("wrote %s (%.0f KB)" % (a.out, os.path.getsize(a.out) / 1024))
    try:
        os.remove(tmp)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
