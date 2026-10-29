# -*- coding: utf-8 -*-
"""P17 - 적응의 **값어치**: 손실률이 변할 때 auto 가 최선 고정팔을 이기는가.

왜 이 단계가 필요한가
---------------------
p11·p15 는 조건마다 손실률을 **고정**해 두고 auto 와 최선 고정팔을 비교한다.
손실률이 고정이면 최선 고정팔이 언제나 존재하므로 **적응은 그것을 따라잡을
수 있을 뿐 이길 수 없다.** 그래서 두 단계의 후회는 구조적으로 >= 0 이고,
"적응이 필요한가"에는 답하지 못한다. 답하는 것은 "적응이 해를 끼치지 않는가"뿐.

적응이 이기려면 두 가지가 동시에 있어야 한다.
  (a) 손실률이 **변한다** — 아니면 고정팔 하나가 늘 최적이다.
  (b) 패리티가 **공짜가 아니다** — 아니면 최대 m 이 늘 최적이라 (a) 도 무의미.
      이 테스트베드는 기본이 대역 무제한이라 t_tx=0 이고 (b) 가 성립하지 않는다.
      p16 이 잰 그 사실이 여기서 실험 설계로 돌아온다.

🩸 2026-08-26 — 증폭신용 경주를 넣어 모형을 수리한 뒤, 위 (a)(b) 를 수로
   옮겨 **설계 공간을 전수로 훑었다.** 오라클 이득 = (구간마다 최선을 고르는
   정책) 대비 (최선 고정팔 하나) 의 차이, 50:50 스케줄:

       cert 3,000~30,000 (250 B 간격) × 업링크 0.25~10 Mbps 및 무제한
       × RTT 20/50/100/200 × 손실쌍 24 종  = 23,328 조합

   나온 것이 이 단계의 방향을 바꾼다:

   1. **FEC 가 왕복을 사는 영역(1-RTT 가 잡히는 자리)에서는 오라클 이득이
      어느 RTT 에서도 정확히 0.00 ms 다.** 이유가 분명하다 - 패리티가 일단
      왕복을 사면 그 값어치(≈1 RTT)가 패리티 하나의 직렬화(수 ms)를 압도
      하므로 **m 은 클수록 좋고, 손실률이 변해도 그 답이 안 바뀐다.**
      적응할 대상 자체가 없다.
   2. 이득이 나는 자리는 전부 **cert 가 커서 왕복을 못 사는 영역**이다
      (RTT 50 최대 1.77 ms, RTT 200 최대 7.10 ms). 거기서 갈리는 것은
      "왕복" 이 아니라 업링크 직렬화뿐이라 이 프로젝트의 본 현상이 아니다.
   3. 그래서 운용점을 그리로 옮기지 **않았다.** 지금 운용점(cert 9,000 ·
      2 Mbps · RTT 50)은 m>=2 가 1-RTT 를 잡아 J 가 100 -> 56 ms 로 떨어지는
      자리이고, 그것이 이 연구의 헤드라인이다. 1.8 ms 짜리 곁가지를 위해
      44 ms 짜리 본 현상을 버리는 것은 거꾸로 가는 것이다.

   결론: 이 단계는 이제 **"적응이 이긴다"를 보이는 실험이 아니라, 적응이
   벌 수 있는 것이 얼마인지를 재서 보고하는 실험**이다. 검사 6 이 그 값을
   재고, 지금 운용점에서 그 값은 0 이다. 그 0 이 결과다 - 자를 흔들어
   초록으로 만들 일이 아니다.
   (남은 연구 방향: 적응의 값어치는 손실률이 아니라 **버스트성**이나
    **RTT 변동**에 있을 수 있다. 이 단계는 손실률만 흔든다.)

🩸 2026-09-01 / 09-07 — **검사 6 을 다시 정의했다 (도현님 결정: 방향 (다)).**
   볼트 정본(03 프로젝트/우리 학술)이 못 박은 결론은 「패리티가 왕복을 사는
   자리에서는 손실 적응이 성립하지 않고 성립할 필요도 없다」이고, 08-29 실측이
   판별 축을 손실률이 아니라 **cert(신용이 묶이는가)** 로 지목했다
   (큰cert 16000 에서 최선 고정팔 m1, 나머지 셋 m3). 그런데 옛 검사 6 은
   시간 기반 오라클 이득(반폭 없음)을 손실 스케줄 하나로 재서, 참을 말하면서
   「실패」로 찍히고 있었다.

   새 검사 6 은 **선택 기반**이고 주장마다 다른 자를 쓴다 (자가 자의적인 것이
   아니라 재는 것이 다르다):
     - 「왕복을 샀다」(m0 대비 최선 고정팔의 개선 ≥ 0.9 RTT) 인 조건에서는
       두 손실 구간의 **실질 허용집합**(최선과 tol 1.0 ms 안)의 교집합이
       비어 있지 않아야 한다 = 고정 m 하나로 **충분**하다 (효과 크기의 주장이라
       고정 tol. 표본이 부족해도 안 헐거워진다).
     - 「못 샀다」(≤ 0.7 RTT) 인 조건에서는 **통계 허용집합**(짝지은 사이클
       블록 t 95% 로 최선보다 나쁘다고 말할 수 없는 팔)의 교집합이 비어야
       한다 = 적응이 **필요**하다 (잡음이 아니라는 주장이라 통계 자).
     - 그 사이(0.7~0.9)는 판정 불능으로 찍고 자를 억지로 하나로 만들지 않는다.
   두 무리가 다 있어야 검사가 공허하지 않다. 검사 7·8(적중률·적응 지연)은
   **적응이 필요한 조건**에서 판정한다 - 왕복을 산 자리에서는 고정 m 하나로도
   99% 가 나와 아무 말도 안 한다. 오라클 이득(시간)은 짝지은 반폭과 함께
   **정보로만** 찍는다 - 이 표본으로는 시간으로 못 가른다.

   ⚠️ 08-30 저널에 새 검사를 대 보면(드라이런) 큰cert 에서 검사 7·8 이 붉다:
   손실 15% 적중률 30.5%, 적응 지연 196/450. **적응이 값을 하는 유일한 자리에서
   정책이 그 값을 못 거둔다.** 그 실패는 참이므로 초록칠하지 않는다.

1 차 실행(2026-08-23, n=200)이 실제로 그것을 보였다:

    10Mbps  auto 60.304  최선 고정 m1 60.692   이득 **+0.388 ms**
    무제한   auto 57.902  최선 고정 m1 57.486   이득 **-0.416 ms**  <- 해롭다

두 수가 p11 이 독립적으로 잰 탐색세(+0.48~0.51)와 맞물린다:
  무제한 = 선택개선 0    - 탐색세 0.42 = -0.42   (실측 -0.416)
  10Mbps = 선택개선 +0.8 - 탐색세 0.42 = +0.38   (실측 +0.388)

⚠️ 그러나 1 차 설계는 **판정할 수 없었다** — 팔마다 전체 스케줄을 따로 돌려
   팔 간 간격이 ~54 초였고, 블록 간 표류가 1.67~3.29 ms 로 재려는 이득
   (0.4 ms)보다 컸다. 아래 2 차 설계가 그것을 고친다.

어떻게 재나 (2 차 설계)
-----------------------
**구간 안에서 팔을 인터리브하고, 자리를 라틴 방격으로 회전한다.**

  - 서버를 한 번만 띄우고 구간마다 네 팔을 연속으로 돌린다
    -> 팔 간 간격 54 초 -> ~14 초, 실행 시간도 절반
  - 구간 인덱스마다 순서를 한 칸씩 돌린다(회전). 구간이 팔 수와 같으므로
    **각 팔이 모든 자리를 정확히 한 번씩** 겪는다. 단순 뒤집기로는 안 된다 —
    auto 는 자리 0·3 만, m0 은 1·2 만 겪어 자리 효과가 팔에 균등하지 않다.
  - 자리 효과(순서 표류)를 직접 재서 이득과 나란히 보고한다. 표류가 이득보다
    크면 **판정 불능으로 드러낸다** — 통과시키지 않는다.

auto 의 목적지 캐시는 실행 내내 유지된다(그래야 적응을 잰다).

드라이런
--------
  PADFEC_P17_DRYRUN=1  측정을 안 하고 **저널에 있는 조건만으로** 검사를 다시 돌린다.
  PADFEC_P17_FP=<지문>  같이 주면 옛 세대 저널에 새 검사를 댈 수 있다.
  ⛔ 드라이런은 결과 파일을 **안 쓴다.** 측정 없이 만든 판정이 results/ 에 남으면
     p6 가 그것을 진짜 측정으로 읽는다. Windows 에서도 돈다(root·WSL 불필요).

통과 기준
---------
  1. 모든 팔·구간이 측정됐다        2. 서버 통계가 실제로 있었다
  3. 대역이 실제로 걸렸다 (같은 팔 m0 이 대역 조건에서 무제한보다 느리다)
  4. 손실 전환이 실제로 일어났다
  5. 고정팔들이 서로 갈린다 (안 갈리면 아래가 공허하다)
  6. 왕복을 산 조건은 고정 m 하나로 충분하고, 못 산 조건은 적응이 필요하다
  7. ⭐ 적응이 필요한 조건에서 auto 가 실측 허용집합 안의 m 을 과반 이상 고른다
  8. 적응이 필요한 조건에서 적응 지연이 구간 길이의 절반 미만이다
  9. [부정] 무제한에서는 적응이 벌 것이 없다 (오라클 이득 상한 <= 탐색세)
 10. 복구 CRC 실패 0
"""
import hashlib
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import padbed as B                               # noqa: E402
import blockstat as BST                          # noqa: E402
from padfec import policy as POL                 # noqa: E402
from _journal import Journal, code_fingerprint   # noqa: E402

RTT_MS = 50.0
GROUP = "X25519MLKEM768"
K = 2
# 🩸 2026-08-25 - 2955 -> 9000. 옛 자리는 **두 구간의 최적 m 이 둘 다 1**
#    이라 따라갈 것이 없었다(검사 6 이 계속 실패로 신고하고 있었다).
#    m_max=3 이 되면서 같은 2% <-> 15% 스케줄로 갈리는 자리가 생겼다:
#        cert 7,200~12,000 · 업링크 1~3 Mbps 에서 m=1 <-> m=3
#    9000 은 그 cert 구간의 가운데다. 손실 전이는 3%~5% 사이라
#    스케줄 2%/15% 가 양쪽에 여유를 두고 걸친다.
CERT = 9000          # 갈리는 구간(7,200~12,000)의 가운데.
CACHE = "/tmp/padfec/p17_cache.json"

N_DEFAULT = 150
N_PRECISE = 450
N = int(os.environ.get("PADFEC_P17_N")
        or (N_PRECISE if "--precise" in sys.argv else N_DEFAULT))

DRYRUN = os.environ.get("PADFEC_P17_DRYRUN") == "1"
FP_OVERRIDE = os.environ.get("PADFEC_P17_FP") or None

# (이름, fec, m)  auto 는 정책이 고른다
# 🩸 2026-08-25 - m3 을 더했다. 새 운용점의 고손실 구간 목표가 m=3 인데
#    고정팔에 m=3 이 없으면 "auto 가 최선 고정팔만큼 하는가"를 잴 수
#    없다 - 비교 대상이 아예 없으면 후회가 실제보다 좋게 나온다.
ARMS = [("auto", "auto", 1), ("m0", "off", 0), ("m1", "on", 1),
        ("m2", "on", 2), ("m3", "on", 3)]

# 손실 스케줄 한 사이클. 새 운용점(cert 9000 · 2 Mbps)에서 모형이 짚는
# 전이는 손실 3% ~ 5% 사이다(m=1 -> m=3). 2% / 15% 는 양쪽에 여유를 두고
# 걸친다.
#
# 🩸 2026-08-25 - 닫힘 조건을 적어 둔 주석이 **틀렸다.** 실제 코드는
#    `r = rot[loss] % len(ARMS)` 로 손실률마다 사이클당 한 번씩 돌리므로,
#    닫히려면 **CYCLES == len(ARMS)** 여야 한다(구간 수는 관계없다).
#    우연히 4 == 4 였을 뿐이라 아무도 몰랐다. 팔이 5 개가 됐으니 맞춘다.
SCHEDULE = [(2.0, N), (15.0, N)]
CYCLES = len(ARMS)  # 라틴 방격 닫힘: 손실률마다 각 팔이 각 자리 정확히 1 번

# 🩸 2026-08-25 - 10 Mbps -> 2 Mbps. 모형상 두 손실 구간의 최적 m 이
#    갈리는 대역은 **1~3 Mbps 뿐**이다(0.5 이하도, 4 이상도 안 갈린다).
#    10 Mbps 에서는 어떤 cert 에서도 안 갈려서 이 실험이 성립하지
#    않았다. 무제한 조건은 **음성 대조로 그대로 둔다** - 거기서는
#    여전히 안 갈리고, 그것이 "패리티가 공짜면 적응할 것이 없다"를
#    드러낸다(검사 9).
# 🩸 2026-08-28 - **cert 와 RTT 를 조건마다 준다.** 그전에는 둘 다 모듈
#    상수(CERT=9000, RTT_MS=50)라 이 단계가 **한 점에서만** 적응을 봤다.
#    "손실률이 변할 때 정책이 따라가는가"라는 주장은 운용점 하나가 아니라
#    운용점들에서 성립해야 하는데, 자가 한 점에 못박혀 있으면 그 주장을
#    시험할 수가 없다 - 통과해도 "이 cert·이 RTT 에서는"이라는 단서가 붙는다.
#
#    새로 더한 두 자리:
#      큰cert     16000. 9000 은 갈리는 구간(7,200~12,000)의 가운데라
#                 **m 이 실제로 바뀌는** 자리다. 16000 은 그 구간 위,
#                 즉 신용이 더 크게 묶이는 쪽이다(p18 이 같은 값을 쓴다).
#      RTT200     장거리. RTT 가 커지면 왕복 하나의 값이 커지므로 δ·m 의
#                 교환비가 달라진다. 우리 연구의 헤드라인이 "왕복 하나를
#                 지운다"이므로 RTT 축을 한 번도 안 흔들어 본 것은 구멍이다.
#
#    (이름, netem rate, 정책 uplink, cert, RTT)
CONDS = [
    ("2Mbps",   2.0, POL.UPLINK_CONSTRAINED_MBPS, 9000,  50.0),
    ("무제한",   0.0, POL.UPLINK_UNSHAPED,         9000,  50.0),
    ("큰cert",  2.0, POL.UPLINK_CONSTRAINED_MBPS, 16000, 50.0),
    ("RTT200",  2.0, POL.UPLINK_CONSTRAINED_MBPS, 9000,  200.0),
]

# p11 이 독립으로 잰 탐색세(0.42~0.51 ms). 오라클 이득이 이보다 작으면 어떤
# 정책도 못 이긴다. 검사 9 와 오라클 이득 정보 표시가 이 값을 쓴다.
PROBE_TAX_MS = 0.42
# 실질 허용집합의 자(최선과 이 안이면 같은 팔로 친다). p11 과 같은 관례.
TOL_MS = 1.0
# 「왕복을 샀다」 판정. m0 대비 최선 고정팔의 개선을 RTT 로 나눈 비.
BOUGHT_HI = 0.9      # 이 이상이면 샀다
BOUGHT_LO = 0.7      # 이 이하면 못 샀다. 사이는 판정 불능


def mean(v):
    return (sum(v) / len(v)) if v else None


FEEDBACK = os.environ.get("PADFEC_FEEDBACK") == "1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def cache_snapshot():
    """Record the actual cache state around each arm, outside HCT timing."""
    try:
        with open(CACHE, "rb") as stream:
            data = stream.read()
    except FileNotFoundError:
        return {"exists": False, "sha256": None, "state": None}
    except OSError as exc:
        return {"exists": None, "sha256": None, "state": None,
                "error": str(exc)}
    out = {"exists": True, "sha256": hashlib.sha256(data).hexdigest()}
    try:
        out["state"] = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        out["state"] = None
        out["error"] = "invalid cache JSON"
    return out


def trial_timeline(segment):
    """Keep failed and missing attempts at their original trial indices.

    Legacy success-only records are usable only if every trial succeeded.
    Missing original indices cannot be reconstructed from a compressed list.
    """
    n = segment.get("n_expected", segment.get("n"))
    if type(n) is not int or n <= 0:
        return [], "invalid_count"
    rows = segment.get("trial_records")
    if rows is None:
        mu = segment.get("m_used")
        if (segment.get("ok") == n == segment.get("n")
                and isinstance(mu, list) and len(mu) == n
                and all(type(x) is int and 0 <= x <= POL.M_MAX_DEFAULT for x in mu)):
            return list(mu), "legacy_all_success"
        return [None] * n, "legacy_missing_trial_indices"
    if not isinstance(rows, list):
        return [None] * n, "invalid_trial_records"
    choices = [None] * n
    seen, invalid = set(), False
    for row in rows:
        i = row.get("i") if isinstance(row, dict) else None
        if type(i) is not int or not 0 <= i < n:
            invalid = True
            continue
        if i in seen:
            invalid = True
            choices[i] = None
            continue
        seen.add(i)
        m = row.get("m_used")
        if type(m) is int and 0 <= m <= POL.M_MAX_DEFAULT:
            choices[i] = m
        else:
            invalid = True
    complete = not invalid and len(rows) == n and all(x is not None for x in choices)
    return choices, "all_attempts" if complete else "incomplete_trial_records"


def unit_complete(rec):
    """Accept exactly the planned segments and complete attempted-trial records."""
    if not isinstance(rec, dict) or not isinstance(rec.get("segments"), list):
        return False
    expected = {(c, loss, a): n for c in range(CYCLES)
                for loss, n in SCHEDULE for a, _f, _m in ARMS}
    seen = set()
    for s in rec.get("segments", []):
        if not isinstance(s, dict) or type(s.get("cycle")) is not int:
            return False
        key = (s.get("cycle"), s.get("loss"), s.get("arm"))
        if (key not in expected or key in seen or type(s.get("n")) is not int
                or s["n"] != expected[key] or s.get("err")):
            return False
        seen.add(key)
        if type(s.get("ok")) is not int or not 0 < s["ok"] <= s["n"]:
            return False
        if type(s.get("mean")) not in (int, float) or not math.isfinite(s["mean"]):
            return False
        choices, scope = trial_timeline(s)
        if len(choices) != expected[key] or scope not in ("all_attempts", "legacy_all_success"):
            return False
        if "trial_records" in s:
            rows = s["trial_records"]
            if any(type(x.get("ok")) is not bool
                   or type(x.get("ms")) not in (int, float)
                   or not math.isfinite(x["ms"]) or x["ms"] < 0 for x in rows):
                return False
            if sum(x["ok"] for x in rows) != s["ok"]:
                return False
    return (seen == set(expected) and bool(rec.get("srv_stats_present"))
            and type(rec.get("srv_crc_fail")) is int and rec["srv_crc_fail"] == 0
            and not rec.get("err"))


def unit_key(cond_name, rate, cert, rtt):
    """저널 키. 측정과 드라이런이 **같은 함수**로 키를 만들어야 한다.

    2026-09-07 감사 - 키에 PADFEC_FEEDBACK 이 없어서 피드백 켠 실행이 끈
    실행의 단위를 그대로 되읽었다(측정 없이 「피드백 결과」를 보고). 넣는다.
    """
    gap_ms = 50 if rate > 0 else 8
    return "%s|latin|n%d|c%d|g%d|cert%d|rtt%g|fb%d" % (
        cond_name, N, CYCLES, gap_ms, cert, rtt, int(FEEDBACK)), gap_ms


def run_interleaved(cond_name, rate, up_policy, cert, rtt, jr):
    """구간 안에서 팔을 인터리브하고 자리를 회전한다(라틴 방격)."""
    # 🩸 2026-08-26 - **연결 간격을 대역에 맞춘다.** gap 8 ms 로 연결을 붙여
    #    돌리면 앞 연결의 *뒤따르는* 패리티가 다음 연결의 첫 비행 뒤에 줄을
    #    선다. m 이 클수록 꼬리가 길어 더 밀리므로, 대역 제한이 걸린 조건에서
    #    **높은 m 에 불리한 편향**이 생긴다. 2 Mbps 에서 직접 쟀다
    #    (cert 9000, 팔당 120 연결, m3-m2 평균차):
    #
    #        gap  8 ms -> +5.11 ms   <- 패리티 하나 직렬화(5.32)와 같다
    #        gap 50 ms -> -1.04 ms
    #        gap600 ms -> +0.02 ms
    #
    #    즉 이건 악수의 비용이 아니라 **다음 연결에 떠넘긴 큐**다. gap>=50 에서
    #    사라진다. 이 편향 때문에 "auto 가 m=3 을 과선택한다"는 오진을 한 번
    #    했다 - 큐를 비우고 재니 2 Mbps 최선은 m3(71.00) 이었고 m2 는 73.13
    #    이었다. 무제한은 큐가 안 쌓이므로 8 ms 그대로 둔다(실행 시간).
    key, gap_ms = unit_key(cond_name, rate, cert, rtt)
    if jr.has(key):
        cached = jr.get(key)
        if unit_complete(cached) or DRYRUN:
            return cached
        print("   (저널 단위가 불완전해 다시 측정: %s)" % key)
    if DRYRUN:
        # 어느 N 의 단위가 있는지 보여 준다 - N 이 안 맞으면 「저널에 없음」만
        # 찍혀 이유를 알 수 없었다(--precise / PADFEC_P17_N).
        have = sorted(k for k in jr.keys() if k.startswith(cond_name + "|"))
        print("   (드라이런: 키 %s 없음. 이 지문의 %s 단위: %s)"
              % (key, cond_name, have or "없음"))
        return None
    try:
        os.unlink(CACHE)
    except OSError:
        pass
    acc = {a: [] for a, _f, _m in ARMS}
    seg, err = [], ""
    started_at = utc_now()
    # C1: PADFEC_FEEDBACK=1 이면 서버·클라 양쪽에 -feedback 을 준다.
    # 끄고 켠 결과를 나란히 둬야 "피드백이 적응률을 고쳤다"고 말할 수 있다.
    FB = ["-feedback"] if FEEDBACK else []
    p, sp = B.start_server(cert, fec="on", extra=FB)
    try:
        # 🩸 회전 카운터는 **손실률마다 따로** 센다. 하나로 세면 손실률이
        #    2 개일 때 같은 손실률의 회전이 0,2,0,2 로 건너뛰어 방격이 닫히지
        #    않는다(각 팔이 두 자리만 겪는다 - 고치기 전 실제로 그랬다).
        rot = {}
        for cyc in range(CYCLES):
            for loss, n_conn in SCHEDULE:
                B.set_netem(rtt / 2.0, loss_c2s=loss, rate_up_mbit=rate)
                r = rot.get(loss, 0) % len(ARMS)
                rot[loss] = rot.get(loss, 0) + 1
                order = ARMS[r:] + ARMS[:r]
                for pos, (aname, fec, m) in enumerate(order):
                    before = cache_snapshot()
                    segment_started_at = utc_now()
                    extra = (["-cache", CACHE, "-probe-every", "20"]
                             if fec == "auto" else []) + FB
                    rows, cs, e = B.run_client(
                        GROUP, n_conn, fec=fec, m=max(m, 1), gap_ms=gap_ms,
                        timeout_s=10, expect_k=K, extra=extra,
                        uplink_mbps=up_policy)
                    if e:
                        err = e
                    ok = [x["ms"] for x in rows if x.get("ok")]
                    acc[aname].extend(ok)
                    # 🩸 2026-08-23 - **선택을 기록한다.** 시간으로 적응을
                    #    판정하려면 팔당 46,398 연결이 필요하다(부트스트랩
                    #    직접 계산, 현재 1,200 - 39 배). 고손실 구간의 PTO
                    #    분산 때문이다. 그런데 재려는 것은 "정책이 채널 변화를
                    #    따라가는가"이고, 그것은 **선택**을 보면 잡음 없이
                    #    판정된다 - 시간을 거칠 필요가 없다.
                    mu = [x.get("m_used") for x in rows]
                    seg.append({"cycle": cyc, "loss": loss, "arm": aname,
                                "pos": pos, "n": len(rows), "ok": len(ok),
                                "n_expected": n_conn, "failed": len(rows) - len(ok),
                                "mean": mean(ok), "m_used": mu,
                                "trial_records": rows,
                                "choice_scope": "all_attempts",
                                "started_at": segment_started_at,
                                "finished_at": utc_now(),
                                "cache_before": before, "cache_after": cache_snapshot(),
                                "client_stats": cs, "err": e})

                print("   %-8s cyc%d 손실%-5g  %s" % (
                    cond_name, cyc, loss,
                    "  ".join("%s(자리%d) %.2f" % (s["arm"], s["pos"],
                                                 s["mean"] or -1)
                              for s in seg[-len(ARMS):])), flush=True)
    finally:
        B.stop_server(p)
    ss = B.read_server_stats(sp)
    # 🩸 2026-09-01 - 조건의 **입력 전부**를 저널에 남긴다(up_policy ·
    #    netem_rate_mbit). p20 이 이 저널을 읽어 모형을 다시 부르는데,
    #    그전에는 cert·RTT 를 모듈 상수로 읽고 uplink 는 **조건 이름으로
    #    추측**했다("2Mbps" in cond). 큰cert·RTT200 조건에서 세 값 중 둘이
    #    틀렸고, 모형이 맞는데도 틀린 것으로 나왔다. 값을 넘길 수 있으면
    #    넘긴다 - 추측하는 코드는 그 자체가 냄새다.
    rec = {"cond": cond_name, "cert": cert, "rtt_ms": rtt,
           "up_policy": up_policy, "netem_rate_mbit": rate,
           "gap_ms": gap_ms, "feedback": FEEDBACK,
           "started_at": started_at, "finished_at": utc_now(),
           "protocol": {"version": 2, "group": GROUP, "expected_k": K,
                        "n_per_segment": N, "cycles": CYCLES,
                        "schedule": SCHEDULE, "arms": ARMS,
                        "probe_every": 20, "cache_reset_per_condition": True,
                        "choice_scope": "all_attempts",
                        "latency_scope": "successful_attempts",
                        "comparison_scope": "exploratory_same_data_labels"},
           "arms": {a: {"n": len(v), "mean": mean(v), "p50": B.pctl(v, 0.5),
                        "p95": B.pctl(v, 0.95), "ms": v}
                    for a, v in acc.items()},
           "segments": seg, "srv_recovered": ss.get("recovered"),
           "server_stats": ss,
           "server_statistics_scope": "one condition total; presence is not a connection matching check",
           "srv_crc_fail": ss.get("recover_crc_fail"),
           "srv_stats_present": bool(ss), "err": err}
    # 🩸 2026-09-07 감사 - **완전한 단위만 저널에 남긴다** (p11·p15 와 같은 가드).
    #    그전에는 err 만 봤는데 run_client 가 반환코드를 안 봐서 잘린 단위가
    #    err="" 로 왔고, 그것이 저널에 박히면 이후 모든 실행(드라이런 포함)이
    #    측정 없이 그 불완전 단위를 되읽어 검사 1 이 영영 붉었다.
    n_seg = CYCLES * len(SCHEDULE) * len(ARMS)
    complete = unit_complete(rec)
    if complete:
        jr.record(key, rec)
    else:
        print("   (저널에 안 남긴다: err=%r 구간 %d/%d crc실패 %s)"
              % (err, len(seg), n_seg, ss.get("recover_crc_fail")))
    return rec


def optimal_m(loss_pct, up, cert=None, rtt=None):
    """모형이 말하는 이 구간의 최적 m. 정책 구현이 따라가야 할 목표값."""
    # 🩸 2026-08-25 - C 가 `1146` 으로 박혀 있었다(실측 1448, 그리고
    #    1146 은 어느 그룹의 값도 아니다). 여기서는 다행히 목표 m 이
    #    양쪽 다 1 이라 결론이 안 바뀌었지만, 모형은 k=1 로 돌고
    #    있었다. 측정 파일에서 읽는다 (padbed.measured_C 주석 참고).
    d = POL.decide_v2(C=B.measured_C(GROUP),
                      cert_bytes=CERT if cert is None else cert,
                      rtt_ms=RTT_MS if rtt is None else rtt,
                      p=loss_pct / 100.0, burst=1.0, s0_base=POL.S0_BASE_MLKEM,
                      c_pkt=POL.C_PKT_POLICY_DEFAULT, W=1280, max_steps=2,
                      m_max=POL.M_MAX_DEFAULT, uplink_mbps=up)
    return d["choice"]["m"]


# --------------------------------------------------------------- 블록 통계
#
# 🩸 2026-09-01 - 이 단계의 자는 전부 **사이클 블록**을 단위로 잰다.
#    한 사이클 안에서 다섯 팔이 연달아 돌므로(라틴 방격) 사이클 간 표류는
#    같은 사이클의 두 팔 차이에서 상쇄된다. 연결 하나하나를 독립 표본으로
#    치는 s/sqrt(n) 은 부하 자국·표류에서 불확실성을 2 배 넘게 과소평가한다
#    (p16 이 09-01 에 실측). 그리고 팔별 분산을 따로 쓴다 - 손실 15% 에서
#    m0 의 세그먼트 SD 가 7.263, m1 은 0.603 이라 등분산 가법모형(자리+팔
#    잔차)은 **관여하지 않는 팔의 분산으로 판정을 오염**시킨다. 그래서
#    「가법모형 잔차」자는 버렸고, 짝지은 사이클 차이만 쓴다.

def block_means(rec, arm, loss):
    """{사이클: 그 사이클·손실 구간에서 이 팔의 세그먼트 평균}."""
    out = {}
    for s in rec["segments"]:
        if s["arm"] == arm and s["loss"] == loss and s["mean"] is not None:
            out[s["cycle"]] = s["mean"]
    return out


def paired_ci(rec, a, b, loss, alpha=0.05):
    """팔 a - 팔 b 의 짝지은(사이클 블록) 차이와 t 반폭. (차이, 반폭, 블록수)"""
    ma, mb = block_means(rec, a, loss), block_means(rec, b, loss)
    cyc = sorted(set(ma) & set(mb))
    d = [ma[c] - mb[c] for c in cyc]
    if len(d) < 2:
        return (mean(d), None, len(d))
    mu = sum(d) / len(d)
    var = sum((x - mu) ** 2 for x in d) / (len(d) - 1)
    half = BST.t_crit(len(d) - 1, alpha) * math.sqrt(var / len(d))
    return (mu, half, len(d))


def fixed_arm_names():
    return [a for a, _f, _m in ARMS if a != "auto"]


def allowed_by_loss(rec, tol=TOL_MS, alpha=0.05):
    """구간별 허용집합 둘.

    실질 자(allowed): 최선 고정팔과 tol ms 안에 드는 팔 (효과 크기의 자).
    통계 자(allowed_stat): 짝지은 t 95% 로 최선보다 **나쁘다고 말할 수 없는**
      팔 (차이 - 반폭 <= 0). 잡음이 아니라는 주장의 자.

    🩸 2026-08-26. 옛 정답지는 `optimal_m()`, 즉 **모형의 argmin** 이었다.
       두 가지가 동시에 잘못됐다. (1) 모형이 틀린 자리에서는 폐루프가 맞혀도
       실패로 찍힌다. (2) argmin 은 이산 라벨이라 1·2 위가 0.29 ms 차이여도
       라벨은 갈린다 - 이 단계의 측정 분해능(반폭 1~2 ms)보다 곱다. p11 이
       2026-08-21 에 같은 문제를 이미 풀었다(허용집합 = 최선과 1 ms 안).
       정답지를 모형에서 떼어 **실측**에 붙인다.
    """
    out = {}
    for loss, _n in SCHEDULE:
        fixed = {}
        for a in fixed_arm_names():
            v = [s["mean"] for s in rec["segments"]
                 if s["arm"] == a and s["loss"] == loss
                 and s["mean"] is not None]
            if v:
                fixed[a] = mean(v)
        if not fixed:
            out[loss] = None
            continue
        best = min(fixed, key=lambda a: fixed[a])
        b = fixed[best]
        margins = {}
        stat = []
        for a in fixed:
            if a == best:
                margins[a] = {"diff": 0.0, "half": 0.0}
                stat.append(a)
                continue
            d, half, nb = paired_ci(rec, a, best, loss, alpha)
            margins[a] = {"diff": d, "half": half, "blocks": nb}
            if d is None:
                continue
            # 반폭이 없으면(블록 1 개) 통계 자는 말할 수 없다 -> 보수적으로 포함
            if half is None or (d - half) <= 0:
                stat.append(a)
        out[loss] = {"means": fixed,
                     "means_display_ms": {a: round(v, 3) for a, v in fixed.items()},
                     "best": best,
                     "allowed": sorted(a for a, v in fixed.items()
                                       if v - b < tol),
                     "allowed_stat": sorted(stat),
                     "margins": margins}
    return out


def intersections(alw):
    ls = [l for l, _n in SCHEDULE]
    if any(alw.get(l) is None for l in ls):
        return None, None
    tol = set(alw[ls[0]]["allowed"])
    st = set(alw[ls[0]]["allowed_stat"])
    for l in ls[1:]:
        tol &= set(alw[l]["allowed"])
        st &= set(alw[l]["allowed_stat"])
    return sorted(tol), sorted(st)


def bought_rtt(rec, rtt):
    """이 조건에서 패리티가 **왕복을 샀는가.** cert 는 대리변수고 진짜 기전은
    이것이다. m0(패리티 없음) 대비 최선 고정팔의 개선을 RTT 로 나눈다.
    0.9 이상이면 샀다, 0.7 이하면 못 샀다, 사이는 판정 불능(자를 억지로
    하나로 안 만든다)."""
    am = rec["arms"]
    fixed = {a: am[a]["mean"] for a in fixed_arm_names()
             if am.get(a) and am[a]["mean"] is not None}
    if "m0" not in fixed or len(fixed) < 2:
        return {"ratio": None, "label": "자료 없음", "best": None}
    best = min(fixed, key=lambda a: fixed[a])
    ratio = (fixed["m0"] - fixed[best]) / rtt
    if ratio >= BOUGHT_HI:
        lab = "샀다"
    elif ratio <= BOUGHT_LO:
        lab = "못 샀다"
    else:
        lab = "판정 불능"
    return {"ratio": ratio, "label": lab, "best": best}


def oracle_gain(rec, alw, alpha=0.05):
    """**적응이 벌 수 있는 것의 상한** — 구간마다 최선을 고르는 오라클이
    하나의 최선 고정팔보다 버는 ms (구간 가중치는 스케줄과 같은 50:50).

    짝지은 사이클 블록으로 반폭을 붙인다. 오라클 이득은 **관여하는 팔들의
    차이**로만 정해지므로(전체 최선 고정팔 vs 구간별 최선), 팔 라벨을 전체
    평균에서 정하고 사이클마다 같은 라벨로 이득을 계산해 그 분포로 t 반폭을
    낸다. 사이클 간 표류가 상쇄되고 관여하지 않는 팔(m0)의 분산이 안 들어온다.
    """
    ls = [l for l, _n in SCHEDULE]
    if any(alw.get(l) is None for l in ls):
        return None, None, None
    arms = set(alw[ls[0]]["means"])
    for l in ls[1:]:
        arms &= set(alw[l]["means"])
    if not arms:
        return None, None, None
    fixed_best = min(arms, key=lambda a: sum(alw[l]["means"][a] for l in ls))
    per_loss_best = {l: min(arms, key=lambda a: alw[l]["means"][a]) for l in ls}
    gain = sum(alw[l]["means"][fixed_best] - alw[l]["means"][per_loss_best[l]]
               for l in ls) / len(ls)
    # 사이클별 이득 (같은 라벨)
    cyc = None
    bm = {}
    for l in ls:
        for a in (fixed_best, per_loss_best[l]):
            bm[(l, a)] = block_means(rec, a, l)
            cyc = set(bm[(l, a)]) if cyc is None else cyc & set(bm[(l, a)])
    g = []
    for c in sorted(cyc or []):
        g.append(sum(bm[(l, fixed_best)][c] - bm[(l, per_loss_best[l])][c]
                     for l in ls) / len(ls))
    half = None
    if len(g) >= 2:
        mu = sum(g) / len(g)
        var = sum((x - mu) ** 2 for x in g) / (len(g) - 1)
        half = BST.t_crit(len(g) - 1, alpha) * math.sqrt(var / len(g))
    # The point estimate and its interval use the same matched cycles.
    gain = mean(g) if g else None
    return gain, half, {"fixed_best": fixed_best,
                        "point_scope": "unrounded matched cycle contrasts; same-data winner labels are exploratory",
                        "matched_cycles": sorted(cyc or []),
                        "per_loss_best": {("%g" % l): per_loss_best[l]
                                          for l in ls}}


def oracle_verdict(gain, half, tax=PROBE_TAX_MS):
    if gain is None:
        return "자료 없음"
    if half is None:
        return "반폭 없음"
    if gain + half <= tax:
        return "값 없다"
    if gain - half > tax:
        return "값 있다"
    return "판정 불능"


def variance_inflation(rec, loss, a, b, alpha=0.05):
    """판정을 가르는 대조(a-b)에서 **라틴 방격 가법모형(pooled)** 의 반폭이
    짝지은 반폭보다 몇 배 부푸는가. 자 선택이 자의적이지 않다는 것을 자료로
    매 실행 다시 보인다 - 09-01 에 큰cert 손실15 에서 m0 분산이 m1 의 145 배라
    pooled 가 29.8 배 부풀었다. 정보로만 찍는다."""
    rows = [{"arm": s["arm"], "pos": s["pos"], "block": s["cycle"],
             "value": s["mean"]}
            for s in rec["segments"] if s["loss"] == loss
            and s["mean"] is not None]
    an = BST.latin_anova(rows)
    _d, half_pool = BST.contrast(an, a, b, alpha) if an.get("ok") \
        else (None, None)
    _d2, half_pair, _nb = paired_ci(rec, a, b, loss, alpha)
    if not half_pool or not half_pair:
        return None
    return half_pool / half_pair


def adapt_stats(rec, up, alw):
    """auto 의 선택이 구간별 최선을 따라갔는가 — 시간이 아니라 선택으로 잰다.

    적중 = auto 가 그 구간의 **실측 허용집합** 안의 팔을 골랐다
    적응 지연 = 구간 시작 후 허용집합 안의 선택이 연속 10 회 나올 때까지
    모형의 argmin(`want_m_model`)은 **정보로만** 남긴다 - 모형과 실측이
    갈리는 자리를 나중에 찾을 수 있어야 하기 때문이다.
    """
    out = {}
    for loss, _n in SCHEDULE:
        # 🩸 2026-08-28 - cert·RTT 가 조건마다 달라졌으므로 **그 조건의 값**
        #    으로 모형을 물어야 한다. 모듈 상수로 물으면 큰cert·RTT200 조건
        #    에서 9000/50 의 답이 기록돼, 나중에 "모형과 실측이 갈린 자리"를
        #    찾을 때 **있지도 않은 어긋남**을 쫓게 된다.
        want = optimal_m(loss, up, rec.get("cert"), rec.get("rtt_ms"))
        ok_ms = set()
        if alw.get(loss):
            for a in alw[loss]["allowed"]:
                for nm, _f, mm in ARMS:
                    if nm == a:
                        ok_ms.add(mm)
        hits = tot = unknown = 0
        lags = []
        scopes = []
        for s in rec["segments"]:
            if s["arm"] != "auto" or s["loss"] != loss:
                continue
            mu, scope = trial_timeline(s)
            scopes.append(scope)
            tot += len(mu)
            unknown += sum(x is None for x in mu)
            hits += sum(1 for x in mu if x in ok_ms)
            lag, run = None, 0
            for i, x in enumerate(mu):
                run = run + 1 if x in ok_ms else 0
                if run >= 10:
                    lag = i - 9
                    break
            lags.append(lag)
        out[loss] = {"want_m_model": want,
                     "allowed": (alw.get(loss) or {}).get("allowed"),
                     "allowed_stat": (alw.get(loss) or {}).get("allowed_stat"),
                     "best_measured": (alw.get(loss) or {}).get("best"),
                     "hit_rate": (hits / tot) if tot else None,
                     "timeline_complete": bool(scopes) and all(
                         x in ("all_attempts", "legacy_all_success") for x in scopes),
                     "timeline_scopes": scopes, "unknown_choices": unknown,
                     "hit_rate_scope": "all_attempts_unknown_as_misses",
                     "n": tot, "lags": lags,
                     "lag_med": (statistics.median(x for x in lags if x is not None)
                                 if any(x is not None for x in lags) else None),
                     "lag_median_scope": "conditional on segments that adapted; never-adapted segments are not zero-lag observations",
                     "adapted_segments": sum(x is not None for x in lags),
                     "total_segments": len(lags),
                     "never_adapted": sum(1 for x in lags if x is None)}
    return out


def trial_inventory(rec):
    """Count actual k and current ACK observations independently of cached policy RTT."""
    records = [r for segment in rec.get("segments", []) for r in segment.get("trial_records", [])]
    expected = sum(segment.get("n_expected", segment.get("n", 0)) for segment in rec.get("segments", []))
    counts = {}
    valid = 0
    for row in records:
        k = row.get("first_flight_datagrams")
        label = str(k) if type(k) is int and k > 0 else "unknown"
        counts[label] = counts.get(label, 0) + 1
        rtt = row.get("path_rtt_ms")
        valid += int(row.get("path_rtt_valid") is True and
                     type(rtt) in (int, float) and math.isfinite(rtt) and rtt > 0)
    return {"n_expected": expected, "n_records": len(records),
            "n_missing_records": max(0, expected - len(records)),
            "actual_k_counts": counts, "current_ack_rtt_valid": valid,
            "current_ack_rtt_missing_or_invalid": len(records) - valid,
            "expected_k_scope": "flush hint, not a filter on actual observed k",
            "rtt_scope": "current connection ACK observation only; absence does not establish cached RTT absence or connection failure"}


def position_effect(rec):
    """자리(순서) 효과 — 팔에 무관하게 자리별 평균의 산포 (진단).

    라틴 방격이라 각 자리에 다섯 팔이 정확히 한 번씩 오므로, 자리별 평균의
    차이는 팔 효과가 상쇄된 **순수 순서 효과**다. 방격이 균형이면 팔 효과
    추정은 이것에 편향되지 않으므로 **판정에는 안 쓴다**(09-01 에 버린 자 ②).
    """
    worst = 0.0
    for loss, _n in SCHEDULE:
        by_pos = {}
        for s in rec["segments"]:
            if s["loss"] == loss and s["mean"] is not None:
                by_pos.setdefault(s["pos"], []).append(s["mean"])
        vals = [mean(v) for v in by_pos.values() if v]
        if len(vals) >= 2:
            worst = max(worst, max(vals) - min(vals))
    return worst


def main():
    if FP_OVERRIDE and not DRYRUN:
        print("PADFEC_P17_FP is allowed only with PADFEC_P17_DRYRUN=1; "
              "live measurements must use the current source fingerprint.", file=sys.stderr)
        return 2
    if not DRYRUN:
        B.harden()
        B.require_root()
        B.setup()
    else:
        B.harden()
        print("** 드라이런: 측정 안 함, 저널의 조건만 검사, 결과 파일 안 씀 **")

    fp = FP_OVERRIDE or code_fingerprint(
        ["experiments/p17_adaptive_value.py",
         "experiments/quicbed/qamp.go",
         "experiments/quicbed/policy.go",
         "experiments/quicbed/pfail_table.go",
         "experiments/quicbed/go.mod", "experiments/quicbed/go.sum",
         "experiments/quicbed/build.sh", "experiments/_journal.py",
         "experiments/blockstat.py", "experiments/padbed.py",
         "padfec/policy.py", "padfec/quantum.py",
         "experiments/results/p1_flight.json"], ROOT)
    jr = Journal(os.path.join(B.STATE, "p17_units.jsonl"), fp)

    out = {"rtt_ms": RTT_MS, "group": GROUP, "cert": CERT, "n_per_seg": N,
           "cycles": CYCLES, "schedule": SCHEDULE,
           "conds": [{"cond": c[0], "netem_rate_mbit": c[1], "up_policy": c[2],
                      "cert": c[3], "rtt_ms": c[4]} for c in CONDS],
           "probe_tax_ms": PROBE_TAX_MS, "tol_ms": TOL_MS,
           "bought_hi": BOUGHT_HI, "bought_lo": BOUGHT_LO,
           "dryrun": DRYRUN, "journal_fp": fp, "feedback": FEEDBACK,
           "analysis_scope": "exploratory_same_data_labels",
           "confirmatory": False,
           "rows": [], "gain": [], "checks": []}
    checks = out["checks"]

    def add(name, ok, detail, scope="existing_check"):
        checks.append({"check": name, "ok": bool(ok), "detail": detail,
                       "scope": scope, "confirmatory": False})
        print("[%s] %-64s %s" % ("통과" if ok else "실패", name, detail),
              flush=True)

    print("=" * 104)
    print("P17 적응의 값어치 - 손실 %s%% 교대 x%d 사이클, 구간당 n=%d "
          "(라틴 방격 인터리브)"
          % (" <-> ".join("%g" % l for l, _ in SCHEDULE), CYCLES, N))
    print("=" * 104)

    for cond_name, rate, up_policy, cert, rtt in CONDS:
        print()
        print("### 조건 %s (netem rate %g, 정책 uplink %g, cert %d, RTT %g)"
              % (cond_name, rate, up_policy, cert, rtt))
        rec = run_interleaved(cond_name, rate, up_policy, cert, rtt, jr)
        if rec is None:
            print("   (드라이런: 저널에 없음 - 건너뜀)")
            continue
        # 옛 세대 저널에는 up_policy·netem_rate 가 없다. 조건표에서 채우되
        # 채웠다는 사실을 남긴다(p20 이 같은 규칙을 쓴다).
        filled = False
        for k_, v_ in (("up_policy", up_policy), ("netem_rate_mbit", rate),
                       ("cert", cert), ("rtt_ms", rtt)):
            if k_ not in rec:
                rec[k_] = v_
                filled = True
        if filled:
            rec["inputs_filled_from_conds"] = True
        out["rows"].append(rec)

    for rec in out["rows"]:
        am = rec["arms"]
        if not all(am[a]["mean"] is not None for a in am):
            continue
        means = {a: am[a]["mean"] for a in am}
        # 🩸 2026-08-25 - 여기 팔 이름이 ("m0","m1","m2") 로 박혀 있었다.
        #    29 차에서 m3 을 더했는데 이 목록에 안 들어가서 **최선 고정팔
        #    후보에서 m3 이 빠졌다.** ARMS 에서 유도한다.
        fixed = {a: means[a] for a in fixed_arm_names() if a in means}
        best = min(fixed, key=lambda a: fixed[a])
        alw = allowed_by_loss(rec)
        tol_int, stat_int = intersections(alw)
        bought = bought_rtt(rec, rec["rtt_ms"])
        og, og_half, og_who = oracle_gain(rec, alw)
        # 적응이 필요한가.
        #   못 샀다: 통계 교집합이 비면 **필요**(잡음이 아니라고 말할 수 있다).
        #            통계 교집합은 있는데 실질 교집합이 비면 **판정 불능**
        #            (차이가 있어 보이지만 이 표본으로는 못 가른다 - 08-29 자료의
        #             큰cert 가 그랬다. 재면 뒤집힐 수 있다).
        #            실질 교집합까지 있으면 **불필요** = 주장과 어긋난다.
        #   샀다:   실질 교집합이 있으면 불필요, 없으면 판정 불능(자가 실질이라
        #            잡음으로 비었을 수 있다).
        if bought["label"] == "못 샀다" and stat_int is not None:
            if len(stat_int) == 0:
                needed = True
            elif tol_int:
                needed = False
            else:
                needed = None
        elif bought["label"] == "샀다" and tol_int is not None:
            needed = False if tol_int else None
        else:
            needed = None
        # 판정을 가르는 대조의 여유(차이 - 반폭). 0 에 가까우면 재면 뒤집힌다.
        hi_l0 = SCHEDULE[-1][0]
        margin_hi = None
        if alw.get(hi_l0):
            _b = alw[hi_l0]["best"]
            _ms = [(a, v["diff"], v["half"]) for a, v in alw[hi_l0]["margins"].items()
                   if a != _b and v.get("half") is not None]
            if _ms:
                margin_hi = min(((d - h), a) for a, d, h in _ms)
        # 판정을 가르는 대조의 분산 부풀림(정보). 고손실 구간에서 최선 vs
        # 저손실 구간 최선 (둘이 같으면 None).
        hi_l = SCHEDULE[-1][0]
        lo_l = SCHEDULE[0][0]
        vi = None
        if alw.get(hi_l) and alw.get(lo_l):
            a_hi, a_lo = alw[hi_l]["best"], alw[lo_l]["best"]
            if a_hi != a_lo:
                vi = variance_inflation(rec, hi_l, a_lo, a_hi)
        out["gain"].append({
            "cond": rec["cond"], "cert": rec["cert"], "rtt_ms": rec["rtt_ms"],
            "up_policy": rec.get("up_policy"),
            "netem_rate_mbit": rec.get("netem_rate_mbit"),
            "means": means, "best_fixed": best,
            "best_fixed_mean": fixed[best], "auto_mean": means["auto"],
            "gain_ms": fixed[best] - means["auto"],
            "pos_effect_ms": position_effect(rec),
            "allowed_by_loss": {("%g" % l): v for l, v in alw.items()},
            "intersection_tol": tol_int, "intersection_stat": stat_int,
            "bought_rtt": bought,
            "adapt_needed": needed,
            "deciding_margin_ms": (margin_hi[0] if margin_hi else None),
            "deciding_arm": (margin_hi[1] if margin_hi else None),
            "oracle_gain_ms": og, "oracle_gain_ci95_half_ms": og_half,
            "oracle_arms": og_who,
            "oracle_verdict": oracle_verdict(og, og_half),
            "variance_inflation_pooled_over_paired": vi,
            "adapt": adapt_stats(rec, rec.get("up_policy"), alw),
            "trial_inventory": trial_inventory(rec),
            "fixed_spread_ms": max(fixed.values()) - min(fixed.values()),
            "n_auto": am["auto"]["n"]})
        g = out["gain"][-1]
        print()
        print("   [%s] 최선 고정 %s %.3f | auto %.3f | 시간 이득 %+.3f ms "
              "(자리효과 %.3f, 진단)"
              % (g["cond"], best, fixed[best], means["auto"],
                 g["gain_ms"], g["pos_effect_ms"]))
        print("   %s 왕복 %s (%.2f RTT) | 실질 교집합 %s | 통계 교집합 %s | "
              "적응 %s | 고손실 판별 여유 %s"
              % (" " * len(g["cond"]), bought["label"],
                 bought["ratio"] if bought["ratio"] is not None else -1,
                 tol_int, stat_int,
                 {True: "필요", False: "불필요", None: "판정 불능"}[needed],
                 ("%+.3f ms (%s)" % (g["deciding_margin_ms"], g["deciding_arm"]))
                 if g["deciding_margin_ms"] is not None else "-"))

    print()
    print("-" * 104)
    g = {x["cond"]: x for x in out["gain"]}
    n_seg = len(CONDS) * CYCLES * len(SCHEDULE) * len(ARMS)
    got = sum(len(r["segments"]) for r in out["rows"])
    add("1. 모든 팔·구간이 측정됐다", got == n_seg
        and {r["cond"] for r in out["rows"]} == {c[0] for c in CONDS}
        and len(out["rows"]) == len(CONDS)
        and all(unit_complete(r) for r in out["rows"]),
        "%d/%d 구간" % (got, n_seg))
    add("2. 모든 조건에서 서버 통계가 실제로 있었다",
        all(r["srv_stats_present"] for r in out["rows"]) and out["rows"],
        "%d/%d" % (sum(1 for r in out["rows"] if r["srv_stats_present"]),
                   len(out["rows"])))

    lo = SCHEDULE[0][0]

    def seg_mean(cond, arm, loss):
        v = [s["mean"] for r in out["rows"] if r["cond"] == cond
             for s in r["segments"]
             if s["arm"] == arm and s["loss"] == loss and s["mean"] is not None]
        return mean(v)

    # 🩸 2026-08-26 - 재려는 것은 "netem 이 정말 대역을 거는가" 하나다.
    #    모형을 거치지 말고 **같은 팔을 두 조건에서** 비교한다. 패리티가 없는
    #    m0 이 제일 깨끗하다 - 첫 비행이 원본 k 개뿐이라 예상 지연이
    #    k·W/대역 으로 딱 떨어진다. 대역 조건과 무제한 조건은 cert·RTT 가
    #    같아야 비교가 성립한다 - 같은 (cert, RTT) 의 짝을 고른다.
    _free = next((c for c in CONDS if c[1] == 0), None)
    _shaped = next((c for c in CONDS if c[1] > 0 and _free
                    and c[3] == _free[3] and c[4] == _free[4]), None)
    sh0 = seg_mean(_shaped[0], "m0", lo) if _shaped else None
    fr0 = seg_mean(_free[0], "m0", lo) if _free else None
    _ser = ((K * 1280 * 8.0) / (_shaped[1] * 1e6) * 1e3) if _shaped else 0.0
    add("3. 대역이 실제로 걸렸다 (같은 팔 m0 이 %s 에서 무제한보다 느리다)"
        % (_shaped[0] if _shaped else "대역 조건 없음"),
        (sh0 is not None and fr0 is not None and (sh0 - fr0) > _ser / 2.0),
        ("m0: %s %.2f vs 무제한 %.2f (차이 %+.2f ms, 예상 직렬화 %.2f)"
         % (_shaped[0], sh0, fr0, sh0 - fr0, _ser))
        if (sh0 and fr0) else "자료 없음(대역 조건 %s)"
        % (_shaped[0] if _shaped else None))

    slo = [s["mean"] for r in out["rows"] for s in r["segments"]
           if s["loss"] == lo and s["mean"] is not None]
    shi = [s["mean"] for r in out["rows"] for s in r["segments"]
           if s["loss"] != lo and s["mean"] is not None]
    add("4. 손실 전환이 실제로 일어났다 (고손실 구간이 저손실보다 느리다)",
        slo and shi and mean(shi) > mean(slo),
        "저손실 %.2f vs 고손실 %.2f ms" % (mean(slo) or -1, mean(shi) or -1))

    # 🩸 2026-09-01 - 옛 코드는 `_shaped_name = next(...)` 로 **첫 대역 조건
    #    하나**(2Mbps)만 검사 5~8 에 먹였다. 큰cert·RTT200 은 재고서 버려졌다.
    #    이제 조건 전부를 본다.
    add("5. 고정팔들이 서로 갈린다 (안 갈리면 아래가 공허하다)",
        out["gain"] and all(x["fixed_spread_ms"] > 0.5 for x in out["gain"]),
        " | ".join("%s 산포 %.3f ms" % (x["cond"], x["fixed_spread_ms"])
                   for x in out["gain"]) or "자료 없음")

    # ================= 선택 기반 판정 (시간 기반은 아래에서 정보로만) =====
    #
    # 🩸 2026-09-01 검사 6 재정의 (머리말). 왕복을 산 조건은 고정 m 하나로
    #    충분해야 하고(실질 자), 못 산 조건은 적응이 필요해야 한다(통계 자).
    #    두 무리가 다 있어야 공허하지 않다.
    claim_ok, claim_detail = [], []
    n_bought = n_not = 0
    for x in out["gain"]:
        lab = x["bought_rtt"]["label"]
        if lab == "샀다":
            n_bought += 1
            ok = bool(x["intersection_tol"])
            claim_ok.append(ok)
            claim_detail.append("%s 샀다(%.2f RTT)→실질교집합 %s%s"
                                % (x["cond"], x["bought_rtt"]["ratio"],
                                   x["intersection_tol"],
                                   "" if ok else " <-- 고정 m 으로 부족"))
        elif lab == "못 샀다":
            if x["adapt_needed"] is None:
                claim_detail.append(
                    "%s 못 샀다(%.2f RTT)→통계교집합 %s 실질교집합 %s - 판정 불능"
                    "(고손실 여유 %s)"
                    % (x["cond"], x["bought_rtt"]["ratio"],
                       x["intersection_stat"], x["intersection_tol"],
                       ("%+.3f ms" % x["deciding_margin_ms"])
                       if x["deciding_margin_ms"] is not None else "-"))
                continue
            n_not += 1
            ok = bool(x["adapt_needed"])
            claim_ok.append(ok)
            claim_detail.append("%s 못 샀다(%.2f RTT)→통계교집합 %s(고손실 여유 %s)%s"
                                % (x["cond"], x["bought_rtt"]["ratio"],
                                   x["intersection_stat"],
                                   ("%+.3f ms" % x["deciding_margin_ms"])
                                   if x["deciding_margin_ms"] is not None else "-",
                                   "" if ok else " <-- 고정 m 하나로 충분하다"))
        else:
            claim_detail.append("%s 왕복 %s(%.2f RTT) - 판정 제외"
                                % (x["cond"], lab,
                                   x["bought_rtt"]["ratio"] or -1))
    add("6. 왕복을 산 조건은 고정 m 하나로 충분하고, 못 산 조건은 적응이 필요하다"
        + ("" if (n_bought and n_not) else "  [공허: 한 무리뿐]"),
        bool(claim_ok) and all(claim_ok) and n_bought > 0 and n_not > 0,
        " | ".join(claim_detail) if claim_detail else "자료 없음")

    # 검사 7·8 은 **적응이 필요한 조건**에서 판정한다. 하나도 없으면 전 조건
    # 으로 판정하되 공허 딱지를 단다 - 왕복을 산 자리에서는 고정 m 하나로도
    # 99% 가 나와 「정책이 똑똑하다」의 증거가 아니다.
    need = [x for x in out["gain"] if x["adapt_needed"] is True]
    vac = not need
    tgt = need if need else out["gain"]
    fallback_scope = "exploratory_all_conditions_no_required_adaptation" if vac else "required_adaptation_conditions_same_data_labels"
    out["adaptation_check_scope"] = {"checks": [7, 8], "scope": fallback_scope,
                                     "required_condition_count": len(need),
                                     "targets": [x["cond"] for x in tgt], "confirmatory": False}

    def worst_hit_of(x):
        a = x["adapt"]
        hs = [a[l]["hit_rate"] for l in a if a[l]["hit_rate"] is not None]
        return min(hs) if hs else None

    hits = [(x["cond"], worst_hit_of(x)) for x in tgt]
    timelines_complete = all(a["timeline_complete"] for x in tgt
                             for a in x["adapt"].values())
    worst_hit = min([h for _c, h in hits if h is not None] or [0])
    add("7. auto가 실측 허용집합 안의 m을 과반 이상 고른다"
        + ("  [탐색적 전체 조건 대체: 적응 필요 조건 없음]" if vac else " [적응 필요 조건]"),
        tgt and timelines_complete and worst_hit > 0.5,
        ("최악 적중률 %.1f%% | " % (100 * worst_hit)
         + "  ".join("%s: %s" % (x["cond"], "  ".join(
             "손실%g%%: 허용 %s(최선 %s, 모형 m=%d) 적중 %.1f%% (n=%d)"
             % (l, x["adapt"][l]["allowed"], x["adapt"][l]["best_measured"],
                x["adapt"][l]["want_m_model"],
                100 * (x["adapt"][l]["hit_rate"] or 0), x["adapt"][l]["n"])
             for l in sorted(x["adapt"]))) for x in tgt))
        if tgt else "자료 없음", scope=fallback_scope)

    lag_rows = []
    never = 0
    for x in tgt:
        a = x["adapt"]
        lag_rows.append((x["cond"], [a[l]["lag_med"] for l in sorted(a)]))
        never += sum(a[l]["never_adapted"] for l in a)
    lags = [v for _c, vs in lag_rows for v in vs if v is not None]
    add("8. 적응이 필요한 조건에서 적응 지연이 구간 길이의 절반 미만이다"
        + ("  [탐색적 전체 조건 대체: 적응 필요 조건 없음]" if vac else ""),
        tgt and timelines_complete and lags and max(lags) < N / 2 and never == 0,
        ("적응한 구간에 한정한 중앙 지연 %s (구간 %d) | 끝까지 적응 못 한 구간 %d"
         % (lag_rows, N, never)) if tgt else "자료 없음", scope=fallback_scope)

    # 검사 9: 무제한은 패리티가 공짜라 최대 m 이 늘 최적이고, 적응이 벌 것이
    # 0 이어야 한다. 오라클 이득의 **상한**(이득 + 반폭)이 탐색세 이하여야 한다.
    _free_name = _free[0] if _free else None
    gu = g.get(_free_name) if _free_name else None
    add("9. [부정] 무제한에서는 적응이 벌 것이 없다 (오라클 이득 상한 <= 탐색세 %.2f)"
        % PROBE_TAX_MS,
        gu and gu["oracle_gain_ms"] is not None
        and gu["oracle_gain_ci95_half_ms"] is not None
        and (gu["oracle_gain_ms"] + gu["oracle_gain_ci95_half_ms"])
        <= PROBE_TAX_MS,
        ("오라클 이득 %.3f ± %.3f ms -> %s | %s"
         % (gu["oracle_gain_ms"] if gu["oracle_gain_ms"] is not None
            else float("nan"),
            gu["oracle_gain_ci95_half_ms"]
            if gu["oracle_gain_ci95_half_ms"] is not None else float("nan"),
            gu["oracle_verdict"],
            " | ".join("손실%s: 최선 %s 허용 %s"
                       % (l, v["best"], v["allowed"])
                       for l, v in sorted(gu["allowed_by_loss"].items())
                       if v)))
        if gu else "자료 없음")

    # --- 시간 이득은 정보로만 (판정 안 함). 반폭과 함께 적는다.
    for x in out["gain"]:
        og, oh = x["oracle_gain_ms"], x["oracle_gain_ci95_half_ms"]
        print("   [정보] %-8s 오라클 이득 %s ms -> %s | auto 시간 이득 %+.3f | "
              "분산 부풀림(pooled/짝지은) %s"
              % (x["cond"],
                 ("%.3f ± %.3f" % (og, oh)) if (og is not None and oh is not None)
                 else ("%.3f" % og if og is not None else "-"),
                 x["oracle_verdict"], x["gain_ms"],
                 ("%.1f배" % x["variance_inflation_pooled_over_paired"])
                 if x["variance_inflation_pooled_over_paired"] else "-"))

    crc = sum(r["srv_crc_fail"] or 0 for r in out["rows"])
    add("10. 복구 CRC 실패 0", crc == 0, "총 %d 건" % crc)

    npass = sum(1 for c in checks if c["ok"])
    out["passed"], out["total"] = npass, len(checks)
    out["journal_provenance"] = jr.provenance()
    print("-" * 104)
    print("%d / %d 통과" % (npass, len(checks)))
    if DRYRUN:
        print("(드라이런: 결과 파일을 쓰지 않는다)")
    else:
        # 기본 N 보다 작은 실행(스모크)은 정본 파일을 덮지 않는다.
        _fname = ("smoke_" if N < N_DEFAULT else "") + "p17_adaptive_value.json"
        print("saved: %s" % B.save(_fname, out))
    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
