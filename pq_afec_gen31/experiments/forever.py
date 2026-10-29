# -*- coding: utf-8 -*-
"""라운드를 계속 돌리면서 결론이 흔들리는지 감시한다.

한 번 잘 나온 수는 증거가 약하다. 그래서 측정 단계를 **독립적으로** 반복하고,
매 라운드가 끝날 때마다 핵심 수를 한 줄로 남긴 뒤, 라운드 사이에서
결론이 바뀌는지 본다. 바뀌면 그 자체가 발견이다.

독립 반복을 만드는 법
    각 라운드 시작 때 단위 저널(state/p*_units.jsonl)을 비운다. 저널은
    한 라운드 **안에서** 중단 복구를 해 주고, 라운드 **사이에는** 재사용되지
    않는다. 소스는 건드리지 않으므로 단계 지문이 흔들리지 않는다.

🩸 2026-08-20 2차 감사 - "독립 반복"이 사실이 아니었다.
    analyse()/grouped_pass() 가 measured 도 not_done 도 안 봤다. loop2 는
    상류가 무효인 단계를 **건너뛰는데** results/*.json 에는 옛 파일이 남고,
    forever 는 그걸 읽어 history 한 줄을 append 했다. 즉 **아무것도 안 잰
    라운드가 표본에 들어가 "안정"에 표를 던졌다.**
    -> invalid_reasons() 로 걸러 내고, findings 맨 앞에 **유효 라운드 n 개**를
       명시한다. 표본이 2 개 미만인 항목은 "안정"이 아니라 **판정 보류**다
       (한 값은 언제나 자기 자신과 같으므로 n=1 의 "안정"은 동어반복이다).

산출물
    experiments/state/history.jsonl   라운드별 핵심 수 (append-only)
    experiments/results/stability_report.json  라운드 간 흔들림 요약

사용법
    python experiments/forever.py --rounds 8
    python experiments/forever.py --rounds 8 --resume     (이어서)
"""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE = os.path.join(HERE, "state")
RESULTS = os.path.join(HERE, "results")
HISTORY = os.path.join(STATE, "history.jsonl")

sys.path.insert(0, HERE)
import loop2                                       # noqa: E402

# 매 라운드 다시 재는 단계. p5(감사)는 측정이 아니라 순수 계산이라
# 라운드마다 돌려도 같은 답이 나오지만, 코드가 바뀌었을 때 걸리게 넣어 둔다.
# 🩸 p11(폐루프 후회) 과 p12(양자 경계 절벽) 는 2026-08-20 감사 전까지 여기에도
#    loop2.build_stages() 에도 없었다. 즉 루프 밖이었고, 그래서 손으로 한 번
#    돌린 결과가 그대로 인용되고 있었다.
# 🩸 2026-08-24 - p13~p19 가 이 목록에 없어서 **지속 루프가 새 단계를 한 번도
#    반복 검증하지 않았다.** 라운드 간 안정성 감시는 여기 적힌 단계에만
#    적용되므로, 목록에서 빠지면 그 단계는 "한 번 잘 나온 수"로 남는다.
#    🩸 2026-08-25 정정 - 아래 문장은 **더 이상 사실이 아니다.** p18 은
#    이제 MEASURE 에 들어 있다(m_max 를 2 -> 3 으로 올렸으므로 그 근거를
#    매 라운드 다시 재야 한다). 옛 문장을 남겨 둔다 - 왜 생각이 바뀌었는지
#    가 사라지면 다음 사람이 같은 판단을 되풀이한다:
#    (옛) p18(m_max 검증)은 상시 반복 대상이 아니라 뺀다 - 그것은 한 번 판정하면
#    되는 실험이고 25 분이 든다. 필요하면 손으로 돌린다.
# 2026-08-27 - **p20 을 더했다.** loop2 에는 등록했는데 여기 없어서,
#    상시 반복 루프(forever)는 잔차 해부를 **한 번도 안 돌렸다.**
#    등록처가 둘인데 한쪽만 고치는 사고 - 이 저장소가 반복해 온 형태다.
#    p20 은 새 측정을 안 하고 몇 초에 끝나므로 상시 대상으로 알맞다.
MEASURE = ["p1", "p2", "p3", "p7", "p8", "p9", "p10", "p11", "p12",
           "p4", "p5", "p13", "p14", "p16", "p17", "p15", "p18",
           "p20", "p6", "p19"]


def harden():
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


def _newest_mtime(outputs):
    """산출물 중 가장 최근에 쓰인 시각(epoch). 하나도 없으면 None.

    🩸 2026-08-20 3차 감사 (중대 2). '이 라운드에 실제로 새로 쓰였는가' 를
       판정하는 증거다. loop2 가 적는 status 로는 안 된다 - 타임아웃도
       크래시도 'failed' 로 적히는데, 그런 단계는 결과 파일을 안 쓰고 죽으므로
       지난 라운드 JSON 이 그 자리에 그대로 남는다.
    """
    newest = None
    for o in outputs or []:
        p = os.path.join(ROOT, *o.split("/"))
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return newest


def passcount(d):
    """[통과, 전체]. 셀 수 없으면 [None, None] 이 아니라 None 이다 -
    [None, None] 은 참으로 평가돼 "검사가 있었는데 결과가 비었다"로 보인다.

    🩸 2026-08-20 2차 감사. 위 주석대로 안 되고 있었다. 파일이 **있는데**
       passed/total 이 없으면(예: 스크립트가 중간에 죽어 {'x':1} 만 남은 파일)
       그대로 [None, None] 이 나왔고, grouped_pass 는 그걸 참으로 보고 한
       라운드로 셌으며, all(v == vals[0]) 은 [None,None]==[None,None] 이라
       **"안정"** 이라고 보고했다. 아무것도 안 센 것이 안정으로 둔갑한다.
    """
    if not d:
        return None
    passed, total = d.get("passed"), d.get("total")
    if passed is None or total is None:
        return None
    return [passed, total]


def _checks_of(d):
    """검사 목록. 파일이 없거나(크래시) checks 가 없으면 None.

    🩸 2026-08-20 3차 감사. 두 함수 모두 `(d or {}).get("checks", [])` 였다.
       그래서 **파일을 아예 못 읽은 라운드**(스크립트가 죽어 p11_adaptive.json
       이 없는 경우)가 `p11_failed_checks = []` 로 기록됐고, 그건 빈 목록이라
       "실패한 검사가 하나도 없다"로 읽힌다 - 아무것도 안 잰 것이 **무결점**으로
       둔갑한다. passcount() 가 [None, None] 대신 None 을 돌려주는 것과 정확히
       같은 이유다. 셀 수 없으면 0 이 아니라 '모름'이라고 적어야 한다.
    """
    if not d:
        return None
    checks = d.get("checks")
    if checks is None:
        return None
    return checks


def checknames(d):
    checks = _checks_of(d)
    if checks is None:
        return None
    return [str(c.get("check", ""))[:40] for c in checks]


def failednames(d):
    checks = _checks_of(d)
    if checks is None:
        return None
    return [str(c.get("check", ""))[:40] for c in checks if not c.get("ok")]


def jump_bytes(p12, group):
    """ips 1280 -> 1281 도약폭(B). 명세 7절 1번 주장의 숫자.

    p12_quantum.py 는 이 수를 configs[i]["jump_from_prev"] 에 넣는다
    (임계 중앙값의 직전 ips 대비 차). 최상위에 jump_bytes 를 따로 두면
    그쪽을 먼저 쓴다 - 남의 파일이라 형태가 바뀔 수 있어서.
    """
    if not p12:
        return None
    top = p12.get("jump_bytes")
    # 🩸 bool 은 int 의 하위형이다. jump_bytes=True 가 들어오면 도약폭 1 B 로
    #    조용히 통과해 band() 의 감시 띠(128 B) 안에 눌러앉는다. 같은 파일
    #    band() 는 이미 이 검사를 하고 있었는데 여기만 빠져 있었다.
    if isinstance(top, (int, float)) and not isinstance(top, bool):
        return top
    # 🩸 3차 감사. 위 bool 방어가 **최상위 경로에만** 있었다. 폴백으로 내려오면
    #    configs[i]["jump_from_prev"] 를 아무 검사 없이 그대로 돌려줬고, 거기
    #    True 가 들어오면 다시 도약폭 1 B 로 조용히 통과해 band() 의 감시 띠
    #    (128 B) 안에 눌러앉는다. 막을 거면 두 경로를 다 막아야 한다.
    for c in p12.get("configs", []):
        if c.get("group") == group and c.get("ips") == 1281:
            v = c.get("jump_from_prev")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
            return None
    return None


def snapshot(rnd):
    """이 라운드의 핵심 결론을 한 줄로 뽑는다."""
    p1, p2, p3 = load("p1_flight.json"), load("p2_threshold.json"), \
        load("p3_effect.json")
    p4, p5 = load("p4_model.json"), load("p5_audit.json")
    p7, p8 = load("p7_verify.json"), load("p8_stability.json")
    p11, p12 = load("p11_adaptive.json"), load("p12_quantum.json")

    def thr(group, arm):
        for r in (p2 or {}).get("thresholds", []):
            if r["group"] == group and r["arm"] == arm and r.get("threshold_lo"):
                return [r["threshold_lo"], r["threshold_hi"]]
        return None

    def eff(group, loss, arm, field):
        for r in (p3 or {}).get("runs", []):
            if (r["group"] == group and r["loss"] == loss
                    and r["burst"] == 1.0 and r["dir"] == "c2s"
                    and r["arm"] == arm and r.get("valid")):
                return r.get(field)
        return None

    return {
        "round": rnd,
        "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        # 1. 비행 구조 - 바뀌면 안 되는 값
        "k_mlkem": next((c["k"] for c in (p1 or {}).get("capacity_checks", [])
                         if c["group"] == "X25519MLKEM768" and c["ips"] == 0),
                        None),
        "C_mlkem": next((c["C"] for c in (p1 or {}).get("capacity_checks", [])
                         if c["group"] == "X25519MLKEM768" and c["ips"] == 0),
                        None),
        "any_inplace": (p1 or {}).get("any_inplace_feasible"),
        # 2. 임계
        "thr_off_mlkem": thr("X25519MLKEM768", "off"),
        "thr_on1_mlkem": thr("X25519MLKEM768", "on1"),
        "thr_off_x25519": thr("x25519", "off"),
        # 3. 효과 (c2s 2% 손실)
        "p95_off": eff("X25519MLKEM768", 2.0, "off", "p95"),
        "p95_on1": eff("X25519MLKEM768", 2.0, "on1", "p95"),
        "p99_off": eff("X25519MLKEM768", 2.0, "off", "p99"),
        "p99_on1": eff("X25519MLKEM768", 2.0, "on1", "p99"),
        # 4. 검증 통과 수
        "p4_threshold_hits": (p4 or {}).get("threshold_hits"),
        "p4_hct_mae": (p4 or {}).get("hct_mae_ms"),
        "p5_pass": passcount(p5),
        "p7_pass": passcount(p7),
        "p8_pass": passcount(p8),
        # 🩸 검사 항목의 이름 목록을 함께 남긴다. 이게 없으면 "검사 기준을
        # 고쳐서 통과 수가 바뀐 것"과 "결과가 흔들린 것"을 구분할 수 없다.
        # 실제로 p8 통과 수 [5,7]->[7,8]->[8,8] 이 흔들림으로 잡혔는데,
        # 내가 판정을 p99 로 바꾸고 netem 측정을 커널로 옮겼기 때문이었다.
        "p8_checks": checknames(p8),
        # 5. 폐루프 후회 (p11)
        # 🩸 두 수를 **둘 다** 적는다. 예전에 통과한 쪽(worst_regret_ms=3.605,
        #    기준 <5 ms)만 인용해서 실패한 쪽(수렴 후 worst_regret_late_ms=4.919,
        #    기준 <2 ms)을 가린 적이 있다. 하나만 적으면 또 그렇게 된다.
        #    (그 4.919 자체는 2026-08-26 에 판정불능의 자국으로 밝혀져
        #     1.014 로 내려갔다. 그래도 둘 다 적는 규칙은 그대로 옳다.)
        "p11_pass": passcount(p11),
        "p11_checks": checknames(p11),
        "p11_failed_checks": failednames(p11),
        "p11_worst_regret_ms": (p11 or {}).get("worst_regret_ms"),
        "p11_worst_regret_late_ms": (p11 or {}).get("worst_regret_late_ms"),
        # 🩸 2026-08-25 - 감시 띠를 자료가 정하게 하려면 그 수의 **정밀도**를
        #    같이 남겨야 한다. 옛 띠는 내가 손으로 고른 1.0 ms 였는데 p11 이
        #    스스로 신고한 95% 반폭은 2.6 ms 였다. 즉 측정 정밀도보다 좁은
        #    자로 흔들림을 판정하고 있었다(3 라운드 연속 흔들림 4 건).
        "p11_worst_regret_ci95_half_ms":
            (p11 or {}).get("worst_regret_ci95_half_ms"),
        "p11_worst_regret_late_ci95_half_ms":
            (p11 or {}).get("worst_regret_late_ci95_half_ms"),
        # 상한(조건들의 최대)도 같이 남긴다 - 위 둘이 없는 옛 라운드나
        # 조건이 사라진 경우의 대체용이고, 상한임을 이름으로 드러낸다.
        "p11_worst_ci95_half_ms": (p11 or {}).get("worst_ci95_half_ms"),
        # 6. 양자 경계 절벽 (p12) - 1280 -> 1281 에서 임계가 뛰는 폭.
        #    주 그룹은 x25519(k=1), 교차 확인은 ML-KEM(k=2) - 명세 8절 p12/p12b.
        #    따름정리대로면 k 와 무관하게 같은 자리에서 같은 크기로 뛰어야 한다.
        "p12_pass": passcount(p12),
        "p12_checks": checknames(p12),
        "p12_failed_checks": failednames(p12),
        "p12_jump_bytes": jump_bytes(p12, "x25519"),
        "p12_jump_bytes_mlkem": jump_bytes(p12, "X25519MLKEM768"),
        # 환경 교차검증 - 두 테스트베드가 같은 칸을 가리키는가
        "p9_agree": (load("p9_crossenv.json") or {}).get("all_agree"),
        "p9_A_mlkem": ((load("p9_crossenv.json") or {}).get("A", {})
                       .get("X25519MLKEM768", {}).get("threshold")),
        "p9_B_mlkem": ((load("p9_crossenv.json") or {}).get("B", {})
                       .get("X25519MLKEM768", {}).get("threshold")),
    }


def read_history():
    out = []
    if not os.path.exists(HISTORY):
        return out
    with open(HISTORY, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue          # 중간에 끊긴 마지막 줄은 버린다
    return out


def algo_fingerprint():
    """알고리즘 소스(padfec/*.py + quicbed/*.go)의 해시.

    🩸 2026-08-24 - 라운드 기록에 이것이 없어서 **다른 알고리즘으로 돈 라운드가
       한 표본에 섞였다.** history 의 앞선 10 라운드는 2026-08-20 것인데 그
       뒤로 패리티-ACK 결함 수정 등으로 격자 24.5% 의 선택이 바뀌었다.
       코드가 다르면 "라운드 간 안정"이라는 말 자체가 성립하지 않는다.
       loop2 의 단계 지문과 같은 원리이고, 여기서는 라운드 단위로 쓴다.
    """
    import glob as _g
    h = hashlib.sha256()
    files = []
    for pat in ("padfec/*.py", "experiments/quicbed/*.go"):
        files += _g.glob(os.path.join(ROOT, *pat.split("/")))
    for f in sorted(files):
        h.update(os.path.relpath(f, ROOT).replace("\\", "/").encode())
        with open(f, "rb") as fh:
            h.update(hashlib.sha256(fh.read()).digest())
    return h.hexdigest()[:12]


def append_history(rec):
    rec.setdefault("algo_fp", algo_fingerprint())
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


# snapshot() 이 **숫자를 읽어 오는** 단계. 이 중 하나라도 이번 라운드에 안
# 돌았으면 그 줄의 수는 옛 results/*.json 에서 온 것이므로 표본이 아니다.
# (p6=보고서, p10=재고조사, p13~p15=미작성 은 여기에 아무 수도 안 넣는다.)
SNAPSHOT_STAGES = ("p1", "p2", "p3", "p4", "p5", "p7", "p8", "p9", "p11", "p12")


def invalid_reasons(h):
    """이 라운드를 '독립 반복' 표본에서 빼야 하는 이유. 없으면 빈 목록.

    🩸 2026-08-20 2차 감사 (중대 2). analyse()/grouped_pass() 가 measured 도
       not_done 도 **전혀 안 봤다**. loop2 는 이제 상류가 무효인 단계를
       건너뛰는데 results/*.json 에는 옛 파일이 그대로 남는다. forever 는
       그걸 읽어 history 한 줄을 append 했고, analyse 는 그 줄을 다른 줄과
       똑같이 셌다 - 즉 **아무것도 안 잰 라운드가 '독립 반복' 표본에 들어갔다.**

    빼는 기준은 "검사에 통과했는가"가 아니라 **"이번 라운드에 실제로 쟀는가"**다.
    p11 은 지금 4개 중 1개가 실패하지만 그 단계는 돌았고 결과 파일도 새로
    썼다. 실패를 이유로 라운드를 통째로 버리면 표본이 영영 0 이 되고, 그건
    기준을 갈아 통과 수를 바꾸는 것과 같은 종류의 자기기만이다. 실패 자체는
    p11_failed_checks / p12_failed_checks 가 따로 추적한다.

    그래서 stage_raw(=loop2 가 기록한 날것의 status)를 본다.
        done        돌았고 통과       -> 표본
        failed      돌았고 못 통과    -> 표본 (수는 새것이다 - **단, 아래 참고**)
        stale_deps  돌긴 돌았는데 상류가 무효 -> 표본 아님
        없음/그 밖  한 번도 안 돌았다 -> 표본 아님
    여기에 stage_state 가 'stale'(코드가 바뀜)인 것도 뺀다 - 그 결과 파일은
    지금 코드로 만든 것이 아니다.

    🩸 2026-08-20 3차 감사 (중대 1). `--stop-on-fail` 이나 loop2 자체 예외로
       **rc 1/2 로 끝난 라운드**가 그대로 표본에 들어갔다. loop_skipped 는
       `rc == 3` 만 보고, rc 1/2 는 loop_exit 에 적히기만 할 뿐 여기서 **한 번도
       안 읽혔다.** rc 1 이면 loop2 는 실패한 단계에서 멈추므로 뒤 단계는 아예
       안 돌고, 안 돈 단계의 상태 기록도 안 건드려진다 - stage_raw 에는 지난
       라운드의 'done' 이 그대로 남아 어떤 사유도 안 잡혔다. 그래서 **한 단계도
       안 돈 라운드가 옛 results/*.json 을 다시 세어 '안정'에 표를 던졌다.**
       -> loop_exit 를 직접 본다. 0(완주)과 3(건너뜀; 위에서 따로 잡는다) 말고는
          완전한 한 바퀴가 아니다.

    🩸 (중대 2) 'failed' 를 "돌았고 결과 파일도 새로 썼다"로 단정한 것도 틀렸다.
       loop2.run_stage() 는 subprocess.TimeoutExpired 도 ok=False -> 'failed' 로
       적는다(p3 는 timeout 21600 s, p11/p12 는 14400~21600 s). 타임아웃으로
       죽은 단계는 결과 파일을 **안 쓰고** 죽는데, 라운드는 표본으로 채택되고
       snapshot() 은 **지난 라운드의 JSON 을 읽어 같은 수를 한 번 더 센다.**
       크래시도 마찬가지다.
       -> status 를 믿지 말고 **결과 파일 mtime** 을 라운드 시작 시각과 비교해
          "이번 라운드에 실제로 새로 쓰였는가"를 본다(main() 이 started_epoch
          와 out_mtime 을 줄에 박아 둔다). 안 쓰였으면 그 라운드는 표본이 아니다.

    옛 history 줄(measured/not_done/stage_raw/started_epoch 가 아예 없던
    라운드 0~9)은 판정할 근거가 없으므로 그대로 표본으로 둔다. 없는 근거를
    있는 척하지 않는다 - 대신 analyse() 가 그런 줄을 **'판정 근거 없음'으로
    따로 세어** '검증된 라운드'와 섞이지 않게 한다.
    """
    bad = []

    # 🩸 2026-08-24 - **다른 알고리즘으로 돈 라운드는 같은 표본이 아니다.**
    #    history 의 앞선 라운드들은 2026-08-20 것인데 그 뒤로 패리티-ACK 결함
    #    수정 등으로 격자 24.5% 의 선택이 바뀌었다. 코드가 다르면 "라운드 간
    #    안정"이라는 말 자체가 성립하지 않으므로 표본에서 뺀다.
    #    지문이 아예 없는 옛 라운드도 뺀다 - 어느 코드로 돌았는지 모르기 때문.
    _fp = h.get("algo_fp")
    if not _fp:
        bad.append("알고리즘 지문 없음(어느 코드로 돌았는지 알 수 없다)")
    elif _fp != algo_fingerprint():
        bad.append("알고리즘이 다르다(지문 %s != 현재 %s)"
                   % (_fp, algo_fingerprint()))
    if h.get("measured") is False:
        bad.append("아무것도 안 쟀다(상류 복구 실패)")
    if h.get("loop_skipped"):
        # 🩸 2026-08-25 - exit 3 을 **무조건** 무효로 보면 표본이 영원히 0 이
        #    된다. p11·p15 는 상시 N 에서 정밀도 검사가 구조적으로 실패하도록
        #    내가 만들었고("이 표본으로는 2 ms 를 판정할 수 없다"는 사실을
        #    드러내려고), 그러면 그 하류인 p6·p19 가 매번 건너뛰어져 exit 3 이
        #    난다. 라운드 10 이 실제로 그랬다 - **측정 단계는 전부 돌았는데**
        #    후처리 둘이 빠졌다는 이유로 라운드가 통째로 버려졌다.
        #    구분한다: 건너뛴 것이 **측정 단계**면 무효(잰 게 없다), 후처리
        #    (p6 보고서·p19 감사)뿐이면 표본으로 인정한다.
        _POST = {"p6", "p19"}
        _raw = h.get("stage_raw") or {}
        _skipped = [sid for sid in MEASURE
                    if _raw.get(sid) not in ("done", "failed")]
        _meas_skipped = [sid for sid in _skipped if sid not in _POST]
        if _meas_skipped:
            bad.append("loop2 가 **측정** 단계를 건너뜀(exit 3): %s"
                       % ", ".join(_meas_skipped))

    # 중대 1. rc 3 은 바로 위에서 잡으므로 여기서 두 번 세지 않는다.
    rc = h.get("loop_exit")
    if rc is not None and rc not in (0, 3):
        bad.append("loop2 가 완주하지 못했다(exit %s - 실패해서 멈췄거나 "
                   "인자 오류)" % rc)

    raw = h.get("stage_raw")
    state = h.get("stage_state") or {}
    started = h.get("started_epoch")
    mtimes = h.get("out_mtime")
    for sid in SNAPSHOT_STAGES:
        if raw is not None and sid in raw:
            if raw.get(sid) not in ("done", "failed"):
                bad.append("%s(안 돎:%s)" % (sid, raw.get(sid)))
                continue
        # 중대 2. status 가 뭐라고 적혔든, 결과 파일이 이번 라운드에 안 쓰였으면
        # snapshot() 이 읽은 수는 지난 라운드 것이다.
        if started is not None and mtimes is not None:
            m = mtimes.get(sid)
            if not isinstance(m, (int, float)) or isinstance(m, bool):
                bad.append("%s(결과 파일이 없다)" % sid)
                continue
            if m < started:
                bad.append("%s(결과 파일이 이번 라운드에 안 쓰였다)" % sid)
                continue
        v = state.get(sid)
        if v and v[0] == "stale":
            bad.append("%s(코드가 바뀐 뒤 안 돎)" % sid)

    if raw is None and not state:
        # stage_raw 도 stage_state 도 없는 옛 줄. not_done 만이라도 있으면 쓴다.
        for item in (h.get("not_done") or []):
            if item.split("(")[0] in SNAPSHOT_STAGES:
                bad.append(item)

    # 상태 파일 자체를 못 읽은 라운드(<상태를 못 읽음: ...>). 뭐가 돌았는지
    # 모르므로 표본으로 쓸 수 없다.
    for item in (h.get("not_done") or []):
        if item.startswith("<"):
            bad.append(item)
    return bad


def judgeable(h):
    """이 줄에 '이번 라운드에 실제로 쟀는가'를 판정할 근거가 있는가.

    🩸 2026-08-20 3차 감사. '유효 라운드 N 개' 라벨이 과장이었다. 기존 10
       라운드(0~9)는 measured / stage_raw / started_epoch 가 **아예 없어서**
       invalid_reasons() 가 볼 것이 하나도 없었고, 그래서 전부 **무조건**
       통과했다. 그런 줄은 '검증됨'이 아니라 '판정 근거 없음'이다. 둘을 같은
       통에 넣고 세면 근거 없는 줄이 표본 수를 부풀려 verdict(n>=2) 를 통과시킨다
       - 즉 "안정"이라는 말이 근거 없는 줄 위에 서게 된다.
       버리지는 않는다(없는 근거를 있는 척하지 않듯, 없는 결함도 지어내지
       않는다). 대신 **세는 자리에서 구분해 적는다.**
    """
    return (h.get("stage_raw") is not None
            or bool(h.get("stage_state"))
            or ("measured" in h)
            or h.get("started_epoch") is not None)


def split_rounds(hist):
    """(표본으로 쓸 라운드, [(라운드번호, 이유들), ...], 판정 근거가 있는 라운드)"""
    good, dropped = [], []
    for h in hist:
        why = invalid_reasons(h)
        if why:
            dropped.append((h.get("round"), why))
        else:
            good.append(h)
    return good, dropped, [h for h in good if judgeable(h)]


def verdict(n, same):
    """표본 수를 보고 판정한다.

    🩸 2026-08-20 2차 감사. 표본이 1 개뿐인데 "안정"이라고 적으면 그건 측정이
       아니라 동어반복이다 - 한 값은 언제나 자기 자신과 같다. 실제로 구멍 3 을
       고쳐 '최신 검사 기준 그룹'만 보게 된 직후 라운드는 늘 표본 1 개라,
       바뀐 기준이 전부 자동으로 "안정"으로 보고됐다.
       -> n<2 는 안정/흔들림을 말하지 않고 **판정 보류**로 남긴다.
    """
    if n < 2:
        return "판정 보류"
    return "안정" if same else "흔들림"


def grouped_pass(hist, pass_field, checks_field, label):
    """검사 이름 집합이 같은 라운드끼리만 통과 수를 비교한다.

    🩸 2026-08-20 감사 (구멍 3). 옛 코드는
           newest = max(groups.items(), key=lambda kv: len(kv[0]))
       였다. 이건 "최신"이 아니라 **검사 개수가 가장 많은** 그룹이고, 동률이면
       먼저 만난 것을 집는다. 실제 저장소에서 라운드 0~6 은 검사 이름이 0 개,
       라운드 7 은 8 개, 라운드 8~9 도 8 개였다 - 그래서 라벨은 "현행 검사
       기준"인데 실제로는 **폐기된 라운드 7 의 p99 이전 기준**을 가리켰다.
       -> **가장 최근 라운드가 속한 그룹**을 고른다.

    그리고 기준이 언제 어떻게 바뀌었는지를 보고서에 같이 싣는다. 감사에서
    "결과가 흔들린 것"과 "내가 자를 바꾼 것"을 구분하려면 그 둘이 필요하다.
    """
    seq = sorted([h for h in hist if h.get(pass_field)],
                 key=lambda h: h.get("round", -1))
    if not seq:
        return None

    groups = {}
    for h in seq:
        key = tuple(h.get(checks_field) or [])
        g = groups.setdefault(key, {"vals": [], "rounds": []})
        g["vals"].append(h[pass_field])
        g["rounds"].append(h.get("round"))

    # 기준이 바뀐 지점: 라운드 번호 + 들어온/빠진 검사 이름
    changes, prev = [], None
    for h in seq:
        key = tuple(h.get(checks_field) or [])
        if prev is not None and key != prev:
            changes.append({
                "round": h.get("round"),
                "added": [c for c in key if c not in prev],
                "removed": [c for c in prev if c not in key]})
        prev = key

    cur_key = max(groups,
                  key=lambda k: max([r for r in groups[k]["rounds"]
                                     if r is not None] or [-1]))
    cur = groups[cur_key]
    vals = cur["vals"]

    if changes:
        note = "검사 기준이 %d 번 바뀌었다 - " % len(changes) + " / ".join(
            "라운드 %s: +[%s] -[%s]"
            % (c["round"], ", ".join(c["added"]) or "없음",
               ", ".join(c["removed"]) or "없음") for c in changes)
        note += " / 아래 값은 최신 기준(라운드 %s)만 모은 것이다" % (
            ", ".join(str(r) for r in cur["rounds"]))
    else:
        note = "검사 기준이 한 번도 안 바뀌었다 (전 라운드 비교 가능)"

    same = all(v == vals[0] for v in vals)
    vd = verdict(len(vals), same)
    return {"field": pass_field, "label": label + " (최신 검사 기준)",
            "verdict": vd, "n": len(vals),
            "stable": None if vd == "판정 보류" else same, "values": vals,
            "rounds": cur["rounds"], "n_bases": len(groups),
            "basis_changes": changes, "checks": list(cur_key),
            "note": note}


def analyse(hist_all):
    """라운드 사이에서 흔들리는 것을 찾는다.

    🩸 2026-08-20 2차 감사 (중대 2). 여기가 measured/not_done 을 안 봐서
       아무것도 안 잰 라운드가 표본에 섞였다. 이제 split_rounds() 로 먼저
       걸러 내고, **몇 개가 표본으로 남았는지를 findings 맨 앞에 명시한다.**
       (걸러 낸 뒤 표본이 0~1 개면 아래 항목들은 전부 "판정 보류"로 나온다 -
        그게 "안정"이라고 적는 것보다 정직하다.)
    """
    findings = []
    hist, dropped, verified = split_rounds(hist_all)
    n_unjudged = len(hist) - len(verified)

    findings.append({
        "field": "valid_rounds",
        # 🩸 3차 감사. 옛 라벨은 "유효 라운드 (실제로 잰 라운드만)" 였는데,
        #    실제로는 **판정 근거가 없어 그냥 통과한 줄**이 대부분이었다.
        #    라벨이 데이터보다 세게 말하면 그 자체가 이 프로젝트가 반복해 온
        #    사고다. 두 통을 갈라 적는다.
        "label": "표본 라운드 (검증됨 + 판정 근거 없음)",
        "verdict": "정보", "stable": None, "n": len(hist),
        "n_verified": len(verified), "n_unjudged": n_unjudged,
        "verified_rounds": [h.get("round") for h in verified][-8:],
        "values": [h.get("round") for h in hist][-8:],
        "dropped": [{"round": r, "why": w} for r, w in dropped],
        "note": "전체 %d 라운드 중 표본 %d 개 = **실제로 쟀음이 검증된 %d 개** "
                "+ 판정 근거 없음 %d 개(stage_raw/measured/out_mtime 이 아예 "
                "없던 옛 줄 - '통과'가 아니라 '모름'이다). 제외 %d 개%s"
                % (len(hist_all), len(hist), len(verified), n_unjudged,
                   len(dropped),
                   (": " + " / ".join("라운드 %s(%s)" % (r, "; ".join(w))
                                      for r, w in dropped[-6:]))
                   if dropped else "")})

    def const(field, label, exact=True):
        vals = [h.get(field) for h in hist if h.get(field) is not None]
        if not vals:
            return
        same = all(v == vals[0] for v in vals)
        vd = verdict(len(vals), same)
        findings.append({"field": field, "label": label, "verdict": vd,
                         "n": len(vals),
                         "stable": None if vd == "판정 보류" else same,
                         "values": vals[-6:]})

    const("k_mlkem", "ML-KEM 첫 비행 데이터그램 수")
    const("any_inplace", "제자리(무비용) 배치 가능 여부")
    const("thr_off_mlkem", "ML-KEM 기준선 임계 구간")
    const("thr_on1_mlkem", "ML-KEM FEC(m=1) 임계 구간")
    const("thr_off_x25519", "x25519 기준선 임계 구간")
    const("p5_pass", "독립 감사 통과 수")
    const("p7_pass", "결정적 검증 통과 수")
    # p8/p11/p12 는 **같은 검사 집합 안에서만** 비교한다 (grouped_pass 주석 참고)
    for f in (grouped_pass(hist, "p8_pass", "p8_checks", "반복/음성대조 통과 수"),
              grouped_pass(hist, "p11_pass", "p11_checks", "폐루프 후회 통과 수"),
              grouped_pass(hist, "p12_pass", "p12_checks", "양자 경계 절벽 통과 수")):
        if f:
            findings.append(f)

    # 🩸 기준을 완화하는 대신 **어떤 검사가 실패 중인지**를 라운드마다 남긴다.
    #    실패 검사의 이름 집합이 흔들리면 그것도 발견이다.
    #    ⚠️ 정정 (2026-08-26). 여기 "+4.919 ms > 2 ms 로 실패 중" 이라고
    #    적혀 있었다. 그 수는 비교팔에 m3 가 없어서 생긴 **판정불능**의
    #    자국이었고, 팔을 고친 뒤 1.014 ms 로 통과한다. 지금 p11 이 실패하는
    #    것은 신뢰반폭(표본 부족) 하나뿐이다.
    const("p11_failed_checks", "폐루프에서 실패 중인 검사 이름")
    const("p9_agree", "두 환경 + 팀 자료가 같은 칸")
    const("p9_A_mlkem", "환경 A(문서) ML-KEM 임계")
    const("p9_B_mlkem", "환경 B(1차) ML-KEM 임계")

    # C 는 ClientHello 라 몇 바이트 흔들릴 수 있다 - 범위로 본다
    cs = [h["C_mlkem"] for h in hist if h.get("C_mlkem")]
    if cs:
        vd = verdict(len(cs), (max(cs) - min(cs)) <= 24)
        findings.append({"field": "C_mlkem", "label": "ML-KEM ClientHello C",
                         "verdict": vd, "n": len(cs),
                         "stable": (None if vd == "판정 보류"
                                    else (max(cs) - min(cs)) <= 24),
                         "values": cs[-6:],
                         "note": "최대-최소 %d B" % (max(cs) - min(cs))})

    def band(field, label, tol, unit, tol_field=None, tol_mult=2.0):
        """측정값이라 정확히 같을 수 없는 수 - 폭으로 본다.

        tol 은 **합격 기준이 아니라 흔들림 감시용 띠**다. 합격/불합격은 각
        실험 스크립트가 자기 기준으로 판정하고, 여기서는 라운드 사이에서
        그 수가 움직였는지만 본다. (이 프로젝트는 기준을 갈아 통과 수를
        바꾼 전례가 있어서, 판정과 감시를 섞지 않는다.)

        🩸 2026-08-25 - 띠를 **자료가 정하게** 바꿨다. 옛 tol 은 내가 손으로
           고른 상수(1.0 ms)였는데, p11 이 스스로 신고한 95% 반폭은 2.6 ms
           였다. **측정 정밀도보다 좁은 자로 흔들림을 판정**하고 있었고,
           3 라운드 연속으로 후회 관련 4 항목이 흔들림으로 찍혔다
           (폭 1.073 vs 띠 1.0). 그건 수가 움직인 게 아니라 자가 틀린 것이다.

           tol_field 가 있으면 그 라운드들이 신고한 반폭에서 띠를 뽑는다:
           두 라운드의 신뢰구간이 겹치면(|a-b| <= h_a + h_b) 두 값은 구별할
           수 없다 -> 띠 = tol_mult(=2) x max(반폭).

           **띠를 손으로 넓히는 것과 다르다.** 넓히는 건 통과할 때까지 자를
           바꾸는 것이고(이 저장소가 p8 통과 수에서 이미 겪었다), 이건 자의
           눈금을 측정이 신고한 정밀도에 맞추는 것이다. 그래서 판정 이름도
           나눈다 - 정밀도 띠 안은 "안정"이 아니라 **"정밀도 안"**(구별
           불가)이다:
             · 띠를 넘으면 -> 흔들린 게 **맞다**    (강한 주장)
             · 띠 안이면   -> 흔들렸는지 **모른다** (약한 주장)
           둘을 한 통에 넣으면 요약의 '안정' 수가 부풀려진다.
        """
        vals = [h.get(field) for h in hist
                if isinstance(h.get(field), (int, float))
                and not isinstance(h.get(field), bool)]
        if not vals:
            return
        basis, hw, tol_fixed = "고정", None, tol
        if tol_field:
            hs = [h.get(tol_field) for h in hist
                  if isinstance(h.get(tol_field), (int, float))
                  and not isinstance(h.get(tol_field), bool)
                  and h.get(tol_field) > 0]
            if hs:
                hw = max(hs)
                tol, basis = tol_mult * hw, "정밀도"
        spread = max(vals) - min(vals)
        inband = spread <= tol
        vd = verdict(len(vals), inband)
        if vd == "안정" and basis == "정밀도":
            vd = "정밀도 안"
        findings.append({"field": field, "label": label,
                         "verdict": vd, "n": len(vals),
                         "stable": None if vd == "판정 보류" else inband,
                         "values": [round(v, 3) for v in vals[-6:]],
                         "band_basis": basis, "band_tol": tol,
                         "band_halfwidth": hw, "band_fixed": tol_fixed,
                         "spread": spread,
                         "note": ("최대-최소 %.3f %s (감시 띠 %.3f %s = %s, "
                                  "판정 아님)"
                                  % (spread, unit, tol, unit,
                                     ("신고 반폭 %.3f x%g" % (hw, tol_mult))
                                     if basis == "정밀도"
                                     else "손으로 고른 고정값 - 이 수의 "
                                          "정밀도가 기록에 없다"))})

    band("p11_worst_regret_ms", "폐루프 최악 후회 (전 구간)", 1.0, "ms",
         tol_field="p11_worst_regret_ci95_half_ms")
    band("p11_worst_regret_late_ms", "폐루프 최악 후회 (수렴 후)", 1.0, "ms",
         tol_field="p11_worst_regret_late_ci95_half_ms")
    # 명세 2절 따름정리: 한 칸 = P = 1280 B (실측 모형 1245.5). 라운드마다
    # 이분탐색 해상도만큼 흔들리므로 폭으로 본다.
    band("p12_jump_bytes", "양자 경계 도약폭 x25519 (1280->1281)", 128, "B")
    band("p12_jump_bytes_mlkem", "같은 도약폭 ML-KEM (k=2 교차)", 128, "B")
    const("p12_failed_checks", "양자 경계에서 실패 중인 검사 이름")

    # 효과의 방향은 매 라운드 같아야 한다.
    # 🩸 p95 로 보면 안 된다. 이 손실률에서 95 분위는 "손실 없음(55 ms)"과
    # "하나 잃음(110 ms)" 의 경계에 정확히 놓여, 기준선 p95 자체가 라운드마다
    # 55 와 110 사이를 오간다. 통계량이 불안정한 것이지 효과가 없는 것이
    # 아니다 - p99 는 매 라운드 207 -> 56 으로 일관된다.
    for field, label in (("p99", "c2s 2% 손실에서 FEC 가 p99 를 줄인다"),
                         ("p95", "참고: 같은 조건의 p95 방향 (불안정)")):
        dirs = []
        for h in hist:
            a, b = h.get(field + "_off"), h.get(field + "_on1")
            if a is not None and b is not None:
                dirs.append(b < a)
        if dirs:
            if field == "p99":
                ok = all(dirs)
                vd = verdict(len(dirs), ok)
                st = None if vd == "판정 보류" else ok
                note = ""
            else:
                # 🩸 3차 감사. 옛 코드는 `ok = all(dirs) if field=='p99' else True`
                #    였다. p95 는 **값과 무관하게 언제나 True** 라 라운드마다
                #    자동으로 '안정' 한 표를 던졌다 - 참고용이라고 주석에 적어
                #    놓고 요약 숫자에서는 판정으로 세고 있었던 것이다.
                #    참고 항목은 판정 통에 넣지 않는다: verdict 를 '정보' 로
                #    두고, 대신 몇 번 줄었는지 사실만 적는다.
                vd, ok, st = "정보", None, None
                note = ("불연속면에 걸린 통계라 흔들리는 것이 정상. "
                        "%d 라운드 중 %d 회 감소 (판정 아님)"
                        % (len(dirs), sum(1 for d in dirs if d)))
            findings.append({
                "field": field + "_direction", "label": label,
                "verdict": vd, "n": len(dirs), "stable": st,
                "values": dirs[-8:], "note": note})
    return findings


def run_loop2(ids, keep_going, log_path):
    """loop2 를 하위 프로세스로 돌린다 (지문/상태 관리는 전부 loop2 가 정본)."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [sys.executable, os.path.join(HERE, "loop2.py"), "--only"] + list(ids)
    if keep_going:
        cmd.append("--keep-going")
    r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                       text=True, errors="replace")
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        f.write((r.stdout or "") + (r.stderr or ""))
    return r.returncode


def stale_prereqs():
    """MEASURE 가 (전이적으로) 의존하지만 MEASURE 에 없는 단계 중 무효인 것.

    🩸 2026-08-20 감사 (구멍 2-a). 여기가 비어 있었다. build 와 gate 는
       MEASURE 에 없고, 옛 loop2 는 --only 면 resolve() 를 건너뛰었으므로
       **10 라운드 내내 빌드가 한 번도 안 돌았다**(마지막 08-19 15:07).
       그 사이에 policy.go / pfail_table.go 를 고쳤다면 라운드는 옛 바이너리를
       계속 쟀고, 그러고도 매 라운드 "완료" 로 기록됐다.
       -> 라운드를 시작하기 **전에** 먼저 돌린다. 못 돌리면 라운드를 거부한다
          (측정을 강행해서 못 믿을 수를 history 에 쌓느니 멈추는 게 낫다).
    """
    stages = loop2.build_stages()
    by = {s.id: s for s in stages}
    st = loop2.load_state()
    pre = [sid for sid in loop2.dep_closure(stages, MEASURE)
           if sid not in MEASURE]
    return [sid for sid in pre
            if loop2.stage_status(by[sid], st)[0] != "done"]


def main():
    harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--stop-on-fail", action="store_true",
                    help="단계가 실패하면 멈춘다 (기본은 기록하고 계속)")
    a = ap.parse_args()

    hist = read_history()
    start = (max(h["round"] for h in hist) + 1) if hist else 0
    print("이미 끝난 라운드 %d 개. %d 번부터 %d 라운드 더 돈다."
          % (len(hist), start, a.rounds))
    sys.stdout.flush()

    for rnd in range(start, start + a.rounds):
        print()
        print("#" * 100)
        print("# 라운드 %d 시작  (%s)"
              % (rnd, datetime.datetime.now().strftime("%H:%M:%S")))
        print("#" * 100)
        sys.stdout.flush()

        # 측정 전에 상류(build/gate/p0)를 먼저 되돌린다. 무효한 바이너리로
        # 잰 수를 history 에 쌓으면 그 라운드는 증거가 아니라 소음이다.
        prereq = stale_prereqs()
        rebuilt = []
        if prereq:
            print("  ⚠ 무효한 상류: %s - 측정 전에 먼저 돌린다"
                  % ", ".join(prereq))
            sys.stdout.flush()
            plog = os.path.join(STATE, "forever_round%d_prereq.txt" % rnd)
            run_loop2(prereq, keep_going=False, log_path=plog)
            rebuilt = prereq
            still = stale_prereqs()
            if still:
                # 여기서 강행하면 "빌드 안 된 결과"가 최신으로 기록된다.
                # 그게 정확히 08-19 에 일어난 사고다. 그래서 거부한다.
                print("  ✗ 상류를 되돌리지 못했다: %s" % ", ".join(still))
                print("    이 라운드를 거부한다 (로그 %s). 상류를 고친 뒤 "
                      "같은 명령을 다시 실행하면 이어서 간다." % plog)
                snap = snapshot(rnd)
                snap["prereq_failed"] = still
                snap["prereq_rebuilt"] = rebuilt
                snap["measured"] = False
                append_history(snap)
                break

        # 독립 반복을 위해 단위 저널을 비운다. 소스는 건드리지 않는다.
        for f in glob.glob(os.path.join(STATE, "p*_units.jsonl")):
            try:
                os.unlink(f)
            except OSError:
                pass

        log = os.path.join(STATE, "forever_round%d.txt" % rnd)
        # 🩸 중대 2. 라운드가 언제 시작했는지를 박아 둔다. 이게 없으면
        #    results/*.json 이 **이번 라운드에** 쓰인 것인지 지난 라운드 것인지
        #    나중에 판정할 방법이 없다(타임아웃으로 죽은 단계도 status 는
        #    'failed' 로 적히므로 status 만으로는 구분이 안 된다).
        t_round_start = time.time()
        rc = run_loop2(MEASURE, keep_going=not a.stop_on_fail, log_path=log)

        snap = snapshot(rnd)
        snap["loop_exit"] = rc
        snap["started_epoch"] = t_round_start
        snap["prereq_rebuilt"] = rebuilt
        snap["measured"] = True
        # 🩸 loop2 는 이제 상류가 무효라 **건너뛴 단계가 있으면** 3 을 돌려준다
        #    (실패 1 / 인자오류 2 와 구분된다). 건너뛴 단계의 results/*.json 은
        #    옛 파일이므로 이 라운드는 독립 반복이 아니다 - 그 사실을 줄에
        #    박아 둬야 analyse() 가 나중에 걸러 낼 수 있다.
        snap["loop_skipped"] = (rc == 3)
        # 🩸 이 라운드가 끝난 시점의 단계 상태를 통째로 남긴다.
        #    아래 수들은 results/*.json 을 읽어서 뽑은 것인데, 그 파일이
        #    **이번 라운드에** 다시 쓰인 것인지 아닌지는 여기 없으면 알 수 없다.
        #    (상류가 무효면 loop2 가 그 단계를 건너뛰므로, 옛 파일이 그대로
        #     남아 이번 라운드 값처럼 보인다.) finished 시각을 같이 적어 둔다.
        try:
            _stages = loop2.build_stages()
            _st = loop2.load_state()
            snap["stage_state"] = {
                s.id: [loop2.stage_status(s, _st)[0],
                       (_st["stages"].get(s.id) or {}).get("finished")]
                for s in _stages}
            snap["not_done"] = ["%s(%s)" % (sid, v[0])
                                for sid, v in snap["stage_state"].items()
                                if v[0] != "done"]
            # 🩸 stage_status() 는 "실패" 와 "한 번도 안 돎" 을 둘 다
            #    pending 으로 뭉갠다. 그런데 그 둘은 표본 판정에서 정반대다 -
            #    실패한 단계는 **돌았고 결과 파일도 새로 썼고**, 안 돈 단계는
            #    옛 파일을 남긴다. 그래서 loop2 가 기록한 날것의 status 를
            #    같이 남긴다 (invalid_reasons() 가 이걸 본다).
            snap["stage_raw"] = {
                s.id: (_st["stages"].get(s.id) or {}).get("status")
                for s in _stages}
            # 🩸 중대 2. 각 단계 산출물의 mtime. status 가 'failed' 여도
            #    타임아웃/크래시면 결과 파일은 **안 쓰이고** 지난 라운드 것이
            #    그대로 남는다. 그걸 구분할 수 있는 유일한 증거가 이 시각이다.
            snap["out_mtime"] = {s.id: _newest_mtime(s.outputs)
                                 for s in _stages}
        except Exception as e:
            snap["stage_state"] = {}
            snap["stage_raw"] = None
            snap["out_mtime"] = None      # 모른다. 없다(=안 쓰였다)와 다르다.
            snap["not_done"] = ["<상태를 못 읽음: %s>" % e]
        append_history(snap)
        print("라운드 %d 끝 (exit %d). 로그 %s" % (rnd, rc, log))
        print("  ML-KEM 임계 기준선 %s / FEC %s | p95 %s -> %s | "
              "검증 p5 %s p7 %s p8 %s"
              % (snap["thr_off_mlkem"], snap["thr_on1_mlkem"],
                 snap["p95_off"], snap["p95_on1"], snap["p5_pass"],
                 snap["p7_pass"], snap["p8_pass"]))
        # 🩸 p11 은 두 수를 다 적는다. 통과한 쪽만 말하면 실패가 가려진다.
        print("  폐루프 p11 %s | 최악 후회 전구간 %s ms / 수렴후 %s ms%s"
              % (snap["p11_pass"], snap["p11_worst_regret_ms"],
                 snap["p11_worst_regret_late_ms"],
                 (" | 실패: " + "; ".join(snap["p11_failed_checks"]))
                 if snap["p11_failed_checks"] else ""))
        print("  양자경계 p12 %s | 도약폭 x25519 %s B / ML-KEM %s B%s"
              % (snap["p12_pass"], snap["p12_jump_bytes"],
                 snap["p12_jump_bytes_mlkem"],
                 (" | 실패: " + "; ".join(snap["p12_failed_checks"]))
                 if snap["p12_failed_checks"] else ""))
        if snap["not_done"]:
            print("  ⚠ done 아닌 단계: %s" % ", ".join(snap["not_done"]))
        sys.stdout.flush()

        hist = read_history()
        findings = analyse(hist)
        unstable = [f for f in findings if f.get("verdict") == "흔들림"]
        held = [f for f in findings if f.get("verdict") == "판정 보류"]
        stable = [f for f in findings if f.get("verdict") == "안정"]
        # 🩸 2026-08-25 - '정밀도 안'(구별 불가)은 안정과 **다른 통**이다.
        #    band() 주석 참고: 띠가 측정 정밀도에서 나왔으므로 띠 안에
        #    들어온 것은 '안 움직였다'가 아니라 '움직였는지 모른다'다.
        within = [f for f in findings if f.get("verdict") == "정밀도 안"]
        # 🩸 3차 감사. verdict=='정보' 행(valid_rounds, p95 방향)이 어느 통에도
        #    안 들어가 **네 수의 합이 findings 총수와 안 맞았다.** 요약이 항목을
        #    조용히 흘리면 "몇 개를 보고 있는지"부터 틀린다. 정보 통을 만들고,
        #    그래도 안 맞으면 남는 수를 그대로 드러낸다.
        info = [f for f in findings if f.get("verdict") == "정보"]
        rest = (len(findings) - len(stable) - len(unstable)
                - len(held) - len(info) - len(within))
        valid = next((f for f in findings
                      if f["field"] == "valid_rounds"), None)
        if findings:
            print("  라운드 간 안정성: 안정 %d / 정밀도 안(구별불가) %d / "
                  "흔들림 %d / 판정 보류 %d / "
                  "정보 %d%s = 총 %d 항목  (표본 %s 라운드 = 검증 %s + "
                  "판정근거없음 %s, 전체 %d 중)"
                  % (len(stable), len(within), len(unstable),
                     len(held), len(info),
                     (" / 분류 안 됨 %d" % rest) if rest else "",
                     len(findings),
                     (valid or {}).get("n", "?"),
                     (valid or {}).get("n_verified", "?"),
                     (valid or {}).get("n_unjudged", "?"), len(hist)))
            for f in unstable:
                print("  ⚠ 흔들림: %s -> %s  (%s)"
                      % (f["label"], f["values"], f.get("note", "")))
            for f in within:
                print("  · 정밀도 안(구별 불가): %s -> %s  (%s)"
                      % (f["label"], f["values"], f.get("note", "")))
            for d in (valid or {}).get("dropped", [])[-4:]:
                print("  ⚠ 표본에서 뺀 라운드 %s: %s"
                      % (d["round"], "; ".join(d["why"])))
        # 🩸 통짜로 쓰다 중간에 죽으면 반쯤 쓴 JSON 이 남아 다음에 읽을 때
        #    통째로 못 읽는다. loop2 가 상태 파일에 쓰는 방식과 같게 맞춘다.
        loop2.atomic_write_json(
            os.path.join(RESULTS, "stability_report.json"),
            {"history": hist, "findings": findings})
        sys.stdout.flush()

    print()
    print("=" * 100)
    hist = read_history()
    findings = analyse(hist)
    _valid = next((f for f in findings if f["field"] == "valid_rounds"), None)
    print("총 %d 라운드 (표본 %s 개 = 실제로 쟀음이 검증된 %s 개 + "
          "판정 근거 없는 %s 개). 안정성 요약"
          % (len(hist), (_valid or {}).get("n", "?"),
             (_valid or {}).get("n_verified", "?"),
             (_valid or {}).get("n_unjudged", "?")))
    if _valid and _valid.get("dropped"):
        for d in _valid["dropped"]:
            print("        제외 @라운드 %s  %s" % (d["round"], "; ".join(d["why"])))
    for f in findings:
        # 🩸 표본 n 을 같이 찍는다. n=1 인 "안정"은 동어반복이라 판정 보류다.
        print("  [%s] n=%-3s %-34s %s"
              % (f.get("verdict", "?"), f.get("n", "?"), f["label"],
                 f["values"]))
        # 검사 기준이 바뀐 이력은 반드시 같이 보인다. 이게 없으면 통과 수의
        # 변화가 "결과 변동"인지 "내가 자를 바꾼 것"인지 구분이 안 된다.
        for c in f.get("basis_changes", []):
            print("        기준 변경 @라운드 %s  +[%s]  -[%s]"
                  % (c["round"], ", ".join(c["added"]) or "없음",
                     ", ".join(c["removed"]) or "없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
