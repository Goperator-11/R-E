# -*- coding: utf-8 -*-
"""수정 루프 - 돌리고 · 실패를 **분류**하고 · 고칠 것만 남기는 감독자.

loop2.py 는 단계를 돌린다. forever.py 는 같은 단계를 여러 라운드 돌려
결론이 흔들리는지 본다. **둘 다 "실패가 무엇인지" 는 안 가른다.**
이 파일이 그 자리를 맡는다.

왜 필요한가 - 이 저장소가 되풀이한 자(尺) 문제 다섯 형태
    (1) 못 잼      표본이 모자라 신뢰반폭이 기준을 넘는다      -> 결함 아님, 처방은 N 증가
    (2) 헐거움     자가 너무 느슨해 통과가 아무 말도 안 한다
    (3) 판정불능   비교 팔이 없어 구조적으로 통과 불가
    (4) 환경사고   로그오프·전원·다른 프로세스가 죽였다        -> 결함 아님, 그냥 다시 돌린다
    (5) 부하 자국  다른 실험과 겹쳐 돌아 수가 오염됐다          -> 결함 아님, 애초에 막아야 한다
  2026-08-26 라운드 13 에서 (4)를 결함으로 세어 60 분을 날릴 뻔했고
  (0xC000026B = 세션 로그오프), 같은 날 (5)로 잘못 잰 상수를 모형에 심을
  뻔했다. 그래서 이 감독자는 **분류를 코드로 못 박고**, 겹쳐 도는 것을
  잠금으로 막는다.

한 바퀴가 하는 일
    1. 잠금을 잡는다            - 측정이 둘 이상 겹쳐 돌면 (5)가 생긴다
    2. loop2 --loop --keep-going - 무효한 단계를 전부 돌린다 (실패해도 계속)
    3. 끝난 뒤 각 단계를 분류한다 - 환경사고 / 시간초과 / 표본부족 / 진짜결함
    4. 환경사고면 그 라운드를 **표본에서 빼고** 다시 돈다 (최대 --max-env-retry)
    5. 진짜결함이 하나라도 있으면 **멈추고** 진단서를 쓴다
       - 고치는 것은 사람(또는 Claude)의 판단이다. 자동으로 자를 늘리거나
         기준을 완화하는 짓은 하지 않는다. 그건 결함을 지우는 게 아니라
         결함을 못 보게 만드는 것이다.

산출물
    experiments/state/fixloop_triage.json   마지막 바퀴의 분류 결과 (정본)
    experiments/state/fixloop.log           바퀴마다 한 줄 (append-only)
    experiments/state/fixloop_round%02d.txt loop2 원문 출력

사용법
    python experiments/fixloop.py --status          지금 진단만 보기 (안 돌린다)
    python experiments/fixloop.py                   한 바퀴
    python experiments/fixloop.py --rounds 4        초록이 될 때까지 최대 4 바퀴
    python experiments/fixloop.py --detach --rounds 4
        떨어져 나가 돈다. **Claude 세션이 끝나도 살아남는다** - 2026-08-26
        15:12 에 띄운 루프가 세션 종료와 함께 p11 도중에 죽었다. 자식으로
        띄우면 세션의 프로세스 트리에 묶이기 때문이다.

끝 코드
    0  전부 초록
    1  진짜결함이 있다 (진단서를 보라)
    2  인자가 틀렸다
    3  환경사고가 재시도 한도까지 반복됐다 - 기계 쪽 문제다
    4  다른 인스턴스가 이미 돌고 있다
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(HERE, "state")
LOOP2_STATE = os.path.join(STATE_DIR, "loop2.json")
TRIAGE = os.path.join(STATE_DIR, "fixloop_triage.json")
JOURNAL = os.path.join(STATE_DIR, "fixloop.log")
LOCK = os.path.join(STATE_DIR, "fixloop.lock")
PY = sys.executable

# 환경사고로 볼 종료 코드. **좁게** 잡는다 - 넓게 잡으면 진짜 크래시를
# "환경 탓" 으로 지워 버리는, (4)와 정반대 방향의 같은 사고가 난다.
# 0xC0000005(접근 위반)·0xC0000409(스택 손상)는 일부러 뺐다. 그건 결함이다.
ENV_EXITS = {
    3221226091: "0xC000026B STATUS_DLL_INIT_FAILED_LOGOFF — 세션 로그오프가 죽였다",
    3221225786: "0xC000013A — Ctrl+C / 콘솔 닫힘",
    3221225794: "0xC0000142 — DLL 초기화 실패 (대개 종료 중)",
    3221225725: "0xC00000FD — 스택 넘침 (환경 아님일 수도, 로그를 보라)",
}
# 위 마지막 항목은 애매해서 넣되 진단서에 그렇게 적는다.
ENV_AMBIGUOUS = {3221225725}

# 실패한 검사 문장이 이 말을 담고 있으면 (1) 못 잼 이다. 결함이 아니라
# 표본 부족이고, 처방은 코드에 이미 있다(--precise).
SAMPLE_WORDS = ("반폭", "신뢰구간", "신뢰반폭", "표본이", "정밀도", "필요 N")

FAIL_LINE = re.compile(r"^\s*\[(실패|fail)\]\s*(.*)$")
SCORE_LINE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*통과\s*$")


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------- 잠금
def _alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20).stdout or ""
    except Exception:
        return True          # 못 물어보면 살아 있다고 본다 (겹치는 쪽이 더 나쁘다)
    return str(pid) in out


def _running_measurement():
    """지금 이 기계에서 **실제로 측정이 돌고 있나.** 잠금 파일과 무관하게 본다.

    🩸 2026-08-26 17:00 - 이 함수가 없어서 사고가 났다. 잠금 파일의 pid 가
       죽은 줄 알고(약한 liveness 검사가 거짓으로 '죽었다'고 했다) 잠금을
       **손으로 지우고** 두 번째 루프를 띄웠다. 옛 루프는 살아서 p15 를
       재고 있었고, 12 분간 측정 둘이 겹쳐 돌았다 - 잠금이 막으려던 바로
       그 일(부하 자국)을 잠금을 지워서 저지른 것이다.

       그래서 잠금을 **파일 하나에 걸지 않는다.** 진짜 근거는 프로세스다:
       WSL 안의 `qamp`(측정 그 자체)와 윈도우의 `loop2.py`/`fixloop.py`.
       파일이 없어도 이것들이 살아 있으면 새 루프를 띄우지 않는다.

    못 물어보면 **돌고 있다고 본다** - 겹쳐 도는 쪽이 훨씬 나쁘기 때문이다.
    """
    me = os.getpid()
    # (1) 측정 실체: WSL 안의 qamp
    try:
        # 🩸 `pgrep -f '/tmp/qamp'` 를 쓰면 **자기를 실행한 bash 를 잡는다**
        #    (그 셸의 cmdline 에 '/tmp/qamp' 라는 글자가 들어 있으므로).
        #    첫 시험에서 바로 거짓양성이 났고, 부를 때마다 pid 가 바뀌는 것이
        #    그 자국이었다. 이름으로 정확히 맞춘다.
        r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-lc",
                            "pgrep -x qamp | head -3"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        if (r.stdout or "").strip():
            return "WSL 안에서 qamp 가 돌고 있다 (pid %s)" % (
                " ".join((r.stdout or "").split()))
    except Exception:
        return "WSL 을 못 물어봤다 - 돌고 있다고 본다"
    # (2) 다른 루프 감독자/실행기
    # 🩸 같은 자기참조 함정이 여기에도 있다 - 이 질의 문자열 자체가
    #    'loop2.py' 를 담고 있어서 **powershell.exe 가 자기를 잡는다.**
    #    그래서 (a) 파이썬 프로세스로 한정하고 (b) 진단만 보는 --status /
    #    --selftest 는 뺀다(그건 측정이 아니다).
    ps = ("Get-CimInstance Win32_Process | "
          "Where-Object { $_.Name -like 'python*' -and "
          "$_.CommandLine -match 'loop2|fixloop' -and "
          "$_.CommandLine -notmatch '--status|--selftest' } | "
          "Select-Object -ExpandProperty ProcessId")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        pids = [int(x) for x in (r.stdout or "").split() if x.strip().isdigit()]
        pids = [p for p in pids if p != me]
        if pids:
            return "다른 루프가 돌고 있다 (pid %s)" % pids
    except Exception:
        pass
    return ""


def take_lock(force=False):
    """측정이 겹쳐 도는 것을 막는다.

    겹쳐 돌면 서버의 송신 결정이 늦어져 **측정값 자체가 바뀐다** — 2026-08-26
    에 q(d) 표에 심을 뻔한 38.7% 가 그 자국이었다. 잠금은 편의가 아니라
    측정의 타당성 장치다.

    `force` 는 잠금 파일만 무시한다. **프로세스 검사는 못 넘는다** - 살아
    있는 측정 위에 새 측정을 얹는 것은 어떤 이유로도 옳지 않기 때문이다.
    """
    busy = _running_measurement()
    if busy:
        print("측정이 이미 돌고 있다: %s" % busy)
        print("겹쳐 돌리면 두 측정이 서로를 느리게 만들어 **수가 바뀐다.**")
        print("정말 멈추려면 그 프로세스를 죽여라 (taskkill /PID <pid> /T /F).")
        return False
    if force and os.path.exists(LOCK):
        print("--force-unlock: 남은 잠금 파일을 넘겨받는다 (프로세스 검사는 통과했다).")
        try:
            os.remove(LOCK)
        except OSError:
            pass
    if os.path.exists(LOCK):
        try:
            with open(LOCK, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
        if _alive(old.get("pid")):
            print("이미 돌고 있다: pid %s (%s 시작). 겹쳐 돌리면 측정이 오염된다."
                  % (old.get("pid"), old.get("started")))
            print("정말 죽었다면 이 파일을 지워라: %s" % LOCK)
            return False
        print("잠금이 남아 있지만 pid %s 는 죽었다 - 넘겨받는다." % old.get("pid"))
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOCK, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "started": now()}, f, ensure_ascii=False)
    return True


def drop_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


# ----------------------------------------------------------------- 읽기
def loop2_state():
    try:
        with open(LOOP2_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"stages": {}, "history": []}


def stage_ids():
    """loop2 가 아는 단계 목록. loop2 를 정본으로 쓴다(두 곳에 안 적는다).

    🩸 status 를 loop2.stage_status() 로 받는 것이 요점이다. 상태 파일의
       `status: done` 만 보면 **지문이 어긋난 단계(코드가 바뀜)를 통과로
       센다.** 그건 옛 코드로 낸 초록이고, 이 저장소가 2026-08-20 감사에서
       잡은 사고가 정확히 그것이다.
    """
    sys.path.insert(0, HERE)
    import loop2                                   # noqa: E402
    st = loop2.load_state()
    stages = loop2.build_stages()
    out = []
    for s in stages:
        stt, note = loop2.stage_status(s, st)
        out.append((s.id, s.title, stt, note))
    return out


def fingerprints():
    """지금 이 순간 각 단계의 지문. 바퀴 앞뒤로 재서 대조한다.

    🩸 이 저장소에는 **바퀴가 도는 중에 소스를 고치는** 사고를 막을 것이
       아무것도 없었다. 그러면 한 단계는 옛 코드로, 다음 단계는 새 코드로
       돌면서 상태 파일에는 새 지문이 박힌다 - 즉 **섞인 결과가 초록으로
       기록된다.** 2026-08-20 감사의 구멍 2 와 같은 형태다(돌지 않은 코드의
       지문을 찍는 것). 자동으로 막지는 않는다(돌리는 사람을 멈춰 세우는
       비용이 더 크다). 대신 **바퀴가 끝날 때 반드시 드러나게** 한다.
    """
    sys.path.insert(0, HERE)
    import loop2                                   # noqa: E402
    return {s.id: s.fingerprint() for s in loop2.build_stages()}


def read_log(sid):
    p = os.path.join(STATE_DIR, "log2_%s.txt" % sid)
    if not os.path.exists(p):
        return "", 0
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read(), os.path.getsize(p)
    except OSError:
        return "", 0


def failed_checks(text):
    """로그에서 실패한 검사 문장만 뽑는다. 점수 줄도 같이 준다."""
    fails, score = [], None
    for ln in text.splitlines():
        m = FAIL_LINE.match(ln)
        if m:
            fails.append(m.group(2).strip())
            continue
        m = SCORE_LINE.match(ln)
        if m:
            score = (int(m.group(1)), int(m.group(2)))
    return fails, score


# ----------------------------------------------------------------- 분류
def classify(sid, rec, loop2_status, note, text, nbytes, round_rc=None):
    """한 단계의 실패를 한 갈래로 가른다.

    돌려주는 것: (갈래, 근거, 실패한 검사들, 처방)
    갈래: 통과 | 환경사고 | 시간초과 | 표본부족 | 진짜결함 | 안돌았음

    loop2_status 는 loop2.stage_status() 의 판정(done/stale/pending)이다.
    `rec["status"]` 가 아니라 이것을 쓴다 - 지문이 어긋난 단계를 통과로
    세지 않기 위해서다.
    """
    err = (rec or {}).get("error", "") or ""
    secs = float((rec or {}).get("seconds") or 0.0)

    if loop2_status == "done":
        return "통과", "", [], ""

    if not rec:
        return "안돌았음", "이 단계 기록이 없다 (%s)" % note, [], "돌려라"

    # 지문이 어긋났다 = 코드가 바뀌어 옛 결과를 못 믿는다. 실패가 아니다.
    if loop2_status == "stale":
        return ("안돌았음", "%s - 옛 결과라 못 믿는다" % note, [],
                "다시 돌려라. 통과로 세면 안 된다.")

    # --- 시간초과
    if err.startswith("timeout"):
        return ("시간초과", "%s (%.0f 초 돌다 잘림)" % (err, secs), [],
                "단계 timeout 을 늘리거나 표본을 줄여라. 자를 건드리지 마라.")

    # --- 환경사고: 종료 코드로 확정되는 것
    m = re.search(r"exit (\d+)", err)
    code = int(m.group(1)) if m else None
    if code in ENV_EXITS:
        note = "" if code not in ENV_AMBIGUOUS else " ⚠️ 애매하다 - 로그를 직접 봐라"
        return ("환경사고", "%s: %s%s" % (err, ENV_EXITS[code], note), [],
                "결함이 아니다. 다시 돌린다. 이 라운드는 표본에서 뺀다.")

    # --- 환경사고: 실행조차 못 한 자국 (0.1 초 · 로그 0 바이트)
    if secs < 2.0 and nbytes == 0:
        return ("환경사고",
                "%.1f 초 만에 끝나고 로그가 0 바이트 - 실행조차 못 했다 (%s)" % (secs, err),
                [], "결함이 아니다. 다시 돌린다.")

    # --- 상류가 무효라 건너뛴 것
    # 🩸 2026-09-01 - 이 조건은 **죽은 코드였다.** loop2 는 status 에
    #    "skipped" 를 **절대 안 쓴다** (loop2.py:1073-1076 이 쓰는 값은
    #    done / failed / stale_deps 셋뿐), err 도 "exit N" · "timeout Ns" ·
    #    "상류 무효: …" 뿐이라 "건너뜀" 이 들어갈 자리가 없다. 그래서
    #    **stale_deps 기록이 그대로 실패 갈래로 흘러 「진짜결함」으로
    #    보고됐다** - loop2 가 「돌긴 돌았는데 상류가 무효라 못 믿는다」고
    #    명시한 것을 결함으로 세는 꼴이다. history 에 실제 1 건 있다(p2, 08-21).
    if (rec or {}).get("status") in ("skipped", "stale_deps") or "상류 무효" in err:
        return ("안돌았음", "상류가 무효인 채로 돈 결과라 근거가 없다 (%s)" % err,
                [], "상류를 먼저 초록으로 만들어라.")

    # --- 로그가 깨졌으면 **분류 자체를 못 한다.** 이걸 결함으로 세면
    #     "왜 실패했는지 모르는 것" 을 "무엇이 틀렸는지 안다" 로 둔갑시킨다.
    #     (loop2.run_stage 가 자식 출력을 cp949 로 풀던 버그가 이걸 만들었다.
    #      2026-08-26 에 고쳤고, 이 검사는 같은 일이 또 생기면 잡는 그물이다.)
    broken = text.count("�")
    if broken > 20:
        return ("로그깨짐",
                "로그에 U+FFFD 가 %d 개 - 글자가 깨져 실패 사유를 못 읽는다 (%s)"
                % (broken, err),
                [], "이 단계를 다시 돌려라. 다시 깨지면 run_stage 의 encoding 을 봐라.")

    fails, score = failed_checks(text)

    # 🩸 2026-08-26 바퀴 1 이 이걸 가르쳤다. p17 이 28 분간 잘 돌다가
    #    **측정 도중에** 죽었는데(로그가 무제한 cyc3 에서 뚝 끊겨 있다)
    #    이 분류기가 "진짜결함" 으로 셌다. 정확히 이 저장소의 자 문제
    #    (4) - 환경사고를 결함으로 세는 것 - 을 내가 새로 저지른 것이다.
    #
    #    가르는 자국은 분명하다: 단계는 실패하든 통과하든 마지막에 반드시
    #    "N / M 통과" 를 찍는다. **그 줄도 없고 [실패] 줄도 없다면 검사에
    #    닿기 전에 죽은 것**이고, 그때는 무엇이 틀렸는지 아무 말도 할 수
    #    없다. 결함이라고 부르려면 최소한 검사가 돌았어야 한다.
    if not fails and score is None:
        return ("도중에죽음",
                "검사에 닿기 전에 끊겼다 - '%s' 줄도 [실패] 줄도 없다 "
                "(로그 %d B, %s, %.0f 초)%s"
                % ("N / M 통과", nbytes, err, secs,
                   "" if round_rc is None else
                   "  바퀴 자체의 종료 코드 %s" % round_rc),
                [], "다시 돌려라. 같은 자리에서 되풀이되면 그때가 결함이다.")

    # 검사는 다 돌았는데(점수 줄이 있는데) 실패한 검사가 안 보이면 그건 사고다
    if not fails:
        return ("진짜결함",
                "%s 인데 점수는 %s 이고 실패한 검사를 못 찾았다 (로그 %d B)"
                % (err, "%d/%d" % score, nbytes),
                [], "로그를 직접 봐라. 판정과 종료 코드가 어긋난다.")

    # --- 표본부족: 실패한 검사가 **전부** 정밀도 이야기일 때만
    def is_sample(s):
        return any(w in s for w in SAMPLE_WORDS)

    if all(is_sample(s) for s in fails):
        return ("표본부족",
                "실패 %d 건이 전부 정밀도 (%s)" % (len(fails), score and "%d/%d" % score),
                fails,
                "결함이 아니라 못 잰 것이다. --precise 로 N 을 늘려라. "
                "기준(자)을 완화하지 마라.")

    # --- 나머지는 진짜결함. 정밀도 실패가 섞여 있으면 같이 적는다.
    real = [s for s in fails if not is_sample(s)]
    return ("진짜결함",
            "실패 %d 건 중 진짜 %d 건 (%s)" % (len(fails), len(real),
                                            score and "%d/%d" % score),
            fails, "고쳐야 한다. 자를 늘리지 말고 무엇이 틀렸는지부터 찾아라.")


def triage(round_rc=None):
    st = loop2_state()
    rows = []
    for sid, title, stt, note in stage_ids():
        rec = st["stages"].get(sid)
        text, nbytes = read_log(sid)
        kind, why, fails, rx = classify(sid, rec, stt, note, text,
                                        nbytes, round_rc)
        rows.append({"stage": sid, "title": title, "kind": kind, "why": why,
                     "fails": fails, "prescription": rx, "loop2": stt,
                     "finished": (rec or {}).get("finished", ""),
                     "seconds": (rec or {}).get("seconds", 0)})
    return rows


def summarise(rows):
    order = ["진짜결함", "로그깨짐", "시간초과", "표본부족", "도중에죽음",
             "환경사고", "안돌았음", "통과"]
    by = {k: [r for r in rows if r["kind"] == k] for k in order}
    return by


def print_triage(rows):
    by = summarise(rows)
    print("=" * 96)
    print("수정 루프 진단서   %s" % now())
    print("=" * 96)
    for kind in ["진짜결함", "로그깨짐", "시간초과", "표본부족", "도중에죽음",
                 "환경사고", "안돌았음"]:
        items = by[kind]
        if not items:
            continue
        print("\n■ %s — %d 단계" % (kind, len(items)))
        for r in items:
            # 🩸 2026-09-01 - `finished` 를 rows 에 담아 두고도(401 행) 화면에
            #    한 번도 안 찍고 있었다. 그래서 **08-29 기록을 09-01 진단서에서
            #    읽고도 아무도 낡은 줄 몰랐다.** 언제 잰 것인지는 무엇을
            #    쟀는지만큼 중요하다.
            print("  [%s] %s   (기록 %s)"
                  % (r["stage"], r["title"][:52], r["finished"] or "없음"))
            print("        근거: %s" % r["why"])
            for s in r["fails"][:6]:
                print("        · %s" % s[:110])
            if r["prescription"]:
                print("        처방: %s" % r["prescription"])
    print("\n통과: %d 단계 | 남은 문제: %d 단계"
          % (len(by["통과"]),
             sum(len(by[k]) for k in ["진짜결함", "로그깨짐", "시간초과",
                                      "표본부족", "도중에죽음", "환경사고",
                                      "안돌았음"])))
    print("=" * 96)


def save_triage(rows, round_no, source_moved=()):
    by = summarise(rows)
    out = {"at": now(), "round": round_no,
           "counts": {k: len(v) for k, v in by.items()},
           "source_moved": list(source_moved),
           "rows": rows}
    tmp = TRIAGE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, TRIAGE)
    return out


def journal(line):
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write("%s  %s\n" % (now(), line))


# ----------------------------------------------------------------- 실행
def run_round(round_no, extra_args, tag=""):
    """loop2 를 한 바퀴. 출력은 파일로 흘리고 화면에도 꼬리를 남긴다.

    🩸 2026-08-26 - `tag` 가 없었다. 그래서 로그깨짐 재실행이 같은
       파일명으로 열려 **그 바퀴의 원문을 통째로 덮어썼다.** 바퀴 1 의
       기록(어느 단계가 언제 돌았는지)이 그렇게 사라졌고, 무슨 일이
       있었는지 loop2.json 의 history 로 되짚어야 했다. 진단 기록을
       지우는 것은 이 파일이 막으려던 바로 그 사고다.
    """
    log = os.path.join(STATE_DIR,
                       "fixloop_round%02d%s.txt" % (round_no, tag))
    cmd = [PY, "-u", os.path.join(HERE, "loop2.py"), "--loop", "--keep-going"]
    cmd += list(extra_args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    print("[바퀴 %d] %s" % (round_no, " ".join(cmd)), flush=True)
    t0 = time.time()
    # 🩸 자식을 **자기 프로세스 그룹**에 둔다. 콘솔 제어 이벤트(Ctrl+C)가
    #    그룹을 타고 번지면 측정 한 바퀴가 통째로 날아간다 - 2026-08-26 에
    #    p17 28 분째에서 실제로 그렇게 죽었다(0xC000013A).
    NEW_GROUP = 0x00000200
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=f,
                             stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL,
                             creationflags=NEW_GROUP)
        rc = p.wait()
    dt = time.time() - t0
    print("[바퀴 %d] loop2 끝 - exit %d, %.1f 분" % (round_no, rc, dt / 60.0),
          flush=True)
    return rc, dt, log


# ----------------------------------------------------------------- 자체시험
def _graph_order_violations():
    """(실행 순서, 위반 목록) — 상류보다 먼저 오는 단계를 찾는다.

    위반은 "s 가 상류 d 보다 먼저 온다" 를 "s<d" 로 적는다.
    """
    sys.path.insert(0, HERE)
    import loop2                                   # noqa: E402
    stages = loop2.build_stages()
    order = [x.id for x in stages]
    pos = {sid: i for i, sid in enumerate(order)}
    viol = []
    for x in stages:
        for d in x.deps:
            if d not in pos:
                viol.append("%s<%s(없음)" % (x.id, d))
            elif pos[d] > pos[x.id]:
                viol.append("%s<%s" % (x.id, d))
    return order, sorted(viol)


def selftest():
    """분류기를 지어낸 자료로 시험한다.

    이 감독자의 값어치는 통째로 classify() 에 있다. 검증 안 된 자로 재는
    것이 이 저장소가 되풀이한 실수라, 자를 먼저 잰다. 특히 **부정 검사**
    (틀린 쪽으로 안 새는지)를 같이 둔다 - 환경사고 목록을 넓게 잡으면
    진짜 크래시가 조용히 지워지기 때문이다.
    """
    n = bad = 0

    def check(name, got, want):
        nonlocal n, bad
        n += 1
        ok = got == want
        if not ok:
            bad += 1
        print("  [%s] %-52s %s" % ("ok  " if ok else "FAIL", name,
                                   "" if ok else "%s (기대 %s)" % (got, want)))

    L = "[통과] 1. 뭔가\n[실패] 2. 후회 추정의 95% 신뢰반폭이 1 ms 미만\n8 / 9 통과\n"
    R = "[실패] 7. auto 가 최적 m 을 고른다   불일치\n[통과] 8. 뭐\n7 / 10 통과\n"
    both = "[실패] 3. 대역이 걸렸다\n[실패] 9. 신뢰반폭이 1 ms 미만\n7 / 10 통과\n"

    def c(rec, st, note, text, nb):
        return classify("px", rec, st, note, text, nb)[0]

    check("지문 맞고 done 이면 통과",
          c({"status": "done"}, "done", "", "", 10), "통과")
    check("지문 어긋나면 통과가 아니라 안돌았음",
          c({"status": "done"}, "stale", "코드가 바뀜", L, 10), "안돌았음")
    check("기록 자체가 없으면 안돌았음",
          c(None, "pending", "한 번도 안 돌았음", "", 0), "안돌았음")

    # 🩸 2026-09-01 - **지문 구멍.** 바로 위 두 시험은 classify() 만 부르므로
    #    `loop2_status` 를 손으로 넣어 준다. 그래서 **그 값을 정하는 쪽이
    #    틀렸을 때는 아무 말도 못 한다.** 실제로 loop2.stage_status() 가
    #    status 를 지문보다 먼저 봐서, 지난번 failed 인 단계는 코드가 바뀌어도
    #    "pending" 으로 남았고 위 stale 갈래에 영영 못 왔다. 옛 코드에서 난
    #    실패가 지금 것처럼 「진짜결함」으로 보고됐다(08-29 의 p17·p18·p20).
    #    → 자를 만드는 쪽을 직접 시험한다.
    def _ss(rec_status, fp_ok):
        sys.path.insert(0, HERE)
        import loop2                               # noqa: E402
        s = loop2.build_stages()[0]
        st = {"stages": {s.id: {
            "status": rec_status,
            "fingerprint": s.fingerprint() if fp_ok else "옛지문",
            "finished": "2026-08-29 10:58"}}}
        return loop2.stage_status(s, st)[0]

    check("지문이 어긋나면 지난번 failed 도 stale 이다",
          _ss("failed", False), "stale")
    check("[부정] 지문이 맞으면 failed 는 그대로 pending 이다",
          _ss("failed", True), "pending")
    check("지문이 어긋나면 stale_deps 도 stale 이다",
          _ss("stale_deps", False), "stale")
    check("stale_deps 는 실패가 아니라 안돌았음이다",
          c({"status": "stale_deps", "error": "상류 무효: p1"},
            "pending", "", L, len(L)), "안돌았음")
    check("정밀도만 실패하면 표본부족",
          c({"status": "failed", "error": "exit 1", "seconds": 900},
            "pending", "", L, len(L)), "표본부족")
    check("검사 불일치면 진짜결함",
          c({"status": "failed", "error": "exit 1", "seconds": 900},
            "pending", "", R, len(R)), "진짜결함")
    check("[부정] 정밀도가 섞여 있어도 진짜가 하나면 진짜결함",
          c({"status": "failed", "error": "exit 1", "seconds": 900},
            "pending", "", both, len(both)), "진짜결함")
    check("로그오프 종료코드는 환경사고",
          c({"status": "failed", "error": "exit 3221226091", "seconds": 0.1},
            "pending", "", "", 0), "환경사고")
    check("[부정] 접근위반(0xC0000005)은 환경사고가 아니다",
          c({"status": "failed", "error": "exit 3221225477", "seconds": 30},
            "pending", "", R, len(R)), "진짜결함")
    check("0.1 초 · 로그 0 바이트는 환경사고",
          c({"status": "failed", "error": "exit 1", "seconds": 0.1},
            "pending", "", "", 0), "환경사고")
    check("[부정] 로그가 있으면 짧아도 환경사고가 아니다",
          c({"status": "failed", "error": "exit 1", "seconds": 0.1},
            "pending", "", R, len(R)), "진짜결함")
    check("시간초과는 따로 센다",
          c({"status": "failed", "error": "timeout 7200s", "seconds": 7200},
            "pending", "", R, len(R)), "시간초과")
    check("깨진 로그는 결함으로 세지 않는다",
          c({"status": "failed", "error": "exit 1", "seconds": 900},
            "pending", "", "�" * 60, 200), "로그깨짐")
    check("[부정] 깨짐이 적으면(20 이하) 그대로 분류한다",
          c({"status": "failed", "error": "exit 1", "seconds": 900},
            "pending", "", R + "�" * 3, len(R)), "진짜결함")

    # 🩸 바퀴 1(2026-08-26 16:23)이 가르친 것. p17 이 측정 도중에 끊겼는데
    #    "진짜결함"으로 셌다. 점수 줄이 없다 = 검사에 닿기 전에 죽었다.
    cut = ("### 조건 무제한\n   무제한 cyc3 손실15  m2 61.12  m3 57.35\n")
    check("검사에 닿기 전에 끊기면 도중에죽음",
          c({"status": "failed", "error": "exit 1", "seconds": 1680},
            "pending", "", cut, len(cut)), "도중에죽음")
    check("[부정] 점수 줄이 있으면 도중에죽음이 아니다",
          c({"status": "failed", "error": "exit 1", "seconds": 1680},
            "pending", "", cut + R, len(cut + R)), "진짜결함")
    check("[부정] 통과로 끝난 로그도 점수 줄이 있으니 도중에죽음이 아니다",
          c({"status": "failed", "error": "exit 1", "seconds": 900},
            "pending", "", "[통과] 1. 뭐\n10 / 10 통과\n", 40), "진짜결함")

    f, s = failed_checks(R)
    check("실패한 검사를 뽑는다", len(f), 1)
    check("점수 줄을 읽는다", s, (7, 10))

    # 🩸 2026-08-26 - **그래프 불변식**. loop2 의 `_cheap_first` 는 위상
    #    정렬이 아니라 "싼 단계를 앞으로 당기는" 재배치라, cheap 이 아닌
    #    단계는 선언 순서대로 돈다. 그래서 deps 에 상류를 적어도 **선언
    #    위치가 그 위에 있으면 순서가 뒤집힌다.** 그러면 그 단계는 상류의
    #    *옛* 결과를 읽고 done 이 되고, 다음 바퀴엔 둘 다 done 이라 아무도
    #    안 돈다 - 낡은 수치가 영원히 초록으로 남는다. p6 에 p17 을 더하다가
    #    실제로 이 자리를 밟았다. 조용히 깨지는 종류라 검사로 못 박는다.
    order, viol = _graph_order_violations()
    check("모든 단계가 자기 상류 뒤에 온다 (선언 순서 == 의존 순서)",
          viol, [])
    check("[부정] 그래프가 비어 있지 않다 (위 검사가 공허하지 않다)",
          len(order) > 10, True)

    print("\n%d checks, %d failed" % (n, bad))
    return 1 if bad else 0


def main():
    harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true",
                    help="안 돌리고 지금 상태만 분류해서 보여준다")
    ap.add_argument("--selftest", action="store_true",
                    help="분류기 자체를 시험한다 (측정 안 함)")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--max-env-retry", type=int, default=3,
                    help="환경사고로 날아간 바퀴를 몇 번까지 다시 돌릴지")
    ap.add_argument("--detach", action="store_true",
                    help="떨어져 나가 돈다 (세션이 끝나도 살아남는다)")
    ap.add_argument("--force-unlock", action="store_true",
                    help="남은 잠금 **파일**을 넘겨받는다. 살아 있는 측정 "
                         "프로세스는 이 옵션으로도 못 넘는다")
    # 🩸 nargs="*" 이면 `--loop2-arg --only p18` 에서 argparse 가 `--only` 를
    #    **자기 옵션으로 읽어** 인자 오류를 낸다. REMAINDER 로 두고 맨 뒤에
    #    적게 한다: `fixloop.py --rounds 1 --loop2-arg --only p18`
    ap.add_argument("--loop2-arg", nargs=argparse.REMAINDER, default=[],
                    help="이 뒤의 모든 인자를 loop2 에 그대로 넘긴다 "
                         "(맨 마지막에 적을 것. 예: --loop2-arg --only p18)")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if a.status:
        rows = triage()
        print_triage(rows)
        bad = ("진짜결함", "로그깨짐", "시간초과")
        return 0 if not any(r["kind"] in bad for r in rows) else 1

    if a.detach:
        # 자식이 잠금에서 걸러지긴 하지만, 여기서 먼저 막아야 **띄운 사람이
        # 그 사실을 본다.** 떨어져 나간 뒤에 거절당하면 로그 파일을 열어야
        # 알 수 있고, 그 사이 "띄웠다"고 착각한다.
        busy = _running_measurement()
        if busy:
            print("측정이 이미 돌고 있다: %s" % busy)
            print("새로 안 띄운다. 진행은 --status 로 봐라.")
            return 4
        return detach(a)

    if not take_lock(force=a.force_unlock):
        return 4
    try:
        return supervise(a)
    finally:
        drop_lock()


def detach(a):
    """자기 자신을 세션 밖으로 띄운다.

    🩸 2026-08-26 15:12 에 띄운 루프가 15:19 에 죽었다. 자식 프로세스로
       띄우면 Claude 세션이 끝날 때 프로세스 트리째 죽기 때문이다. 측정 한
       바퀴가 한 시간을 넘는데 세션 수명에 묶여 있으면 루프는 영영 못 끝난다.

    🩸 2026-08-26 16:23 - 두 번째 죽음. 이번엔 세션이 아니라 **콘솔**이었다.
       `DETACHED_PROCESS` 로 띄우면 그 프로세스는 콘솔이 아예 없고, 그 밑에서
       도는 `wsl.exe` 같은 콘솔 프로그램이 콘솔을 새로 만들었다 지운다.
       그 콘솔이 닫힐 때 오는 제어 이벤트에 loop2 가 `0xC000013A`
       (STATUS_CONTROL_C_EXIT)로 죽었다 - p17 측정 28 분째, 53 분짜리 바퀴가
       통째로 날아갔다.

       그래서 `CREATE_NEW_CONSOLE` 로 **자기 콘솔을 하나 갖게** 하고, 그 창은
       `SW_HIDE` 로 숨긴다. 콘솔의 수명이 이 프로세스에 묶이므로 자식이
       콘솔을 여닫아도 제어 이벤트가 안 온다. `CREATE_NEW_PROCESS_GROUP` 은
       그대로 둔다(Ctrl+C 전파를 끊는다).
    """
    NEW_CONSOLE = 0x00000010
    DETACHED = 0x00000008
    NEW_GROUP = 0x00000200
    BREAKAWAY = 0x01000000
    tried = []
    out = os.path.join(STATE_DIR, "fixloop_detached.txt")
    cmd = [PY, "-u", os.path.abspath(__file__),
           "--rounds", str(a.rounds), "--max-env-retry", str(a.max_env_retry)]
    if a.loop2_arg:
        cmd += ["--loop2-arg"] + list(a.loop2_arg)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    f = open(out, "a", encoding="utf-8", errors="replace")
    f.write("\n%s  ==== 분리 실행 시작 ====\n" % now())
    f.flush()
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0                      # SW_HIDE - 창은 안 뜬다
    # 콘솔을 가진 쪽을 **먼저** 시도한다. DETACHED 는 되돌아갈 자리로만 둔다.
    for flags in (NEW_CONSOLE | NEW_GROUP | BREAKAWAY,
                  NEW_CONSOLE | NEW_GROUP,
                  DETACHED | NEW_GROUP):
        try:
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=f,
                                 stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL,
                                 creationflags=flags, startupinfo=si,
                                 close_fds=True)
        except OSError:
            # 어느 조합이 왜 떨어졌는지 남긴다. 2026-08-27 에 이 침묵
            # 때문에 "BREAKAWAY 가 통한 줄" 알고 세 번째로 잃었다.
            tried.append("0x%08x" % flags)
            continue
        if flags & BREAKAWAY == 0:
            print("⚠ BREAKAWAY 가 안 통해 Job 안에 남는 조합으로 띄웠다"
                  " (시도 실패: %s). 이 세션이 끝나면 같이 죽을 수 있다 -"
                  " 2026-08-27 에 그렇게 p17 을 18 분째 잃었다."
                  % (", ".join(tried) or "없음"))
        print("떨어져 나갔다: pid %d" % p.pid)
        print("진행:  python experiments/fixloop.py --status")
        print("원문:  %s" % out)
        journal("분리 실행 pid %d (rounds=%d)" % (p.pid, a.rounds))
        return 0
    # 2026-08-27 **세 번째 죽음 - 그리고 진짜 원인.**
    #
    #   위 BREAKAWAY 는 부모의 Job 이 `JOB_OBJECT_LIMIT_BREAKAWAY_OK` 를
    #   갖고 있을 때만 통한다. 없으면 CreateProcess 가 실패하고 우리는
    #   **조용히 다음 조합(NEW_CONSOLE|NEW_GROUP)으로 떨어진다** - 그건
    #   Job 안에 그대로 남는 조합이라, 부모(Claude 세션)가 끝나면 Job 이
    #   닫히면서 같이 죽는다. 즉 「되돌아갈 자리」가 사실은 **아무것도
    #   막아 주지 않는 자리**였다.
    #
    #   2026-08-27 19:13 에 p17 측정 18 분째 그렇게 죽었다(그전 두 번과
    #   같은 증상, 다른 원인). 세 번 같은 자리에서 잃었으면 처방을 바꾼다.
    #
    #   **WMI 로 띄운다.** `Win32_Process.Create` 는 프로세스를 WmiPrvSE
    #   서비스가 만들어 주므로 우리 Job 에 처음부터 안 들어간다. 부모가
    #   WmiPrvSE 로 찍히는 것으로 확인할 수 있다.
    #   대가: stdout 을 파이프로 못 받는다 - 그래서 자식이 로그를 직접
    #   파일로 쓰게 리다이렉션을 명령줄에 넣는다.
    try:
        import shlex  # noqa: F401  (경로에 공백이 있어 인용이 필요하다)
        ps_cmd = (
            "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName "
            "Create -Arguments @{CommandLine='%s'; CurrentDirectory='%s'}; "
            "$r.ProcessId"
            % ((" ".join('\"%s\"' % c if " " in c else c for c in cmd)
                + " >> \"%s\" 2>&1" % out).replace("'", "''"),
               ROOT.replace("'", "''")))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                           capture_output=True, text=True, timeout=60)
        pid = (r.stdout or "").strip().splitlines()[-1:] or [""]
        if pid[0].isdigit():
            print("떨어져 나갔다 (WMI): pid %s" % pid[0])
            print("진행:  python experiments/fixloop.py --status")
            print("원문:  %s" % out)
            journal("분리 실행 pid %s (rounds=%d, WMI)" % (pid[0], a.rounds))
            return 0
    except Exception as e:  # noqa: BLE001
        print("WMI 분리 실행도 실패: %s" % e)

    print("분리 실행에 실패했다. 앞에서 그냥 돌려라 (--detach 빼고).")
    return 3


def supervise(a):
    # 🩸 감독자가 죽으면 잠금이 남고 바퀴가 통째로 없어진다. 콘솔 제어
    #    이벤트는 우리가 부른 것이 아니므로(아무도 Ctrl+C 를 안 눌렀다)
    #    무시한다. 정말 멈추려면 프로세스를 죽이거나 잠금 파일을 지운다.
    try:
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass
    env_retries = 0
    round_no = 0
    while round_no < a.rounds:
        round_no += 1
        fp0 = fingerprints()
        rc, dt, log = run_round(round_no, a.loop2_arg)
        moved = [sid for sid, h in fingerprints().items() if fp0.get(sid) != h]
        if moved:
            # 결과를 지우지는 않는다 - loop2 의 지문 규칙이 알아서 그 단계를
            # 무효로 만든다. 여기서 할 일은 **이 바퀴를 증거로 인용하지 못하게
            # 하는 것**이다. 조용히 지나가면 섞인 결과가 초록으로 남는다.
            print("\n⚠ 이 바퀴가 도는 중에 소스가 바뀌었다: %s" % ", ".join(moved))
            print("  이 바퀴의 그 단계 결과는 증거가 아니다. 다음 바퀴에서 다시 돈다.")
            journal("바퀴 %d 소스 변경 감지: %s" % (round_no, ", ".join(moved)))
        rows = triage(rc)
        out = save_triage(rows, round_no, moved)
        c = out["counts"]
        journal("바퀴 %d  exit %d  %.1f분  진짜결함 %d · 로그깨짐 %d · 표본부족 %d "
                "· 도중에죽음 %d · 환경사고 %d · 시간초과 %d · 안돌았음 %d · 통과 %d"
                % (round_no, rc, dt / 60.0, c["진짜결함"], c["로그깨짐"],
                   c["표본부족"], c["도중에죽음"], c["환경사고"], c["시간초과"],
                   c["안돌았음"], c["통과"]))
        print_triage(rows)

        # 도중에 죽은 것도 환경사고와 같은 처방이다 - 다시 돌린다. 다만
        # 갈래는 따로 둔다("죽은 이유를 안다" 와 "모른다" 는 다른 말이다).
        if c["환경사고"] or c["도중에죽음"]:
            env_retries += 1
            if env_retries > a.max_env_retry:
                print("환경사고/도중에죽음이 %d 번 되풀이됐다. 기계 쪽 문제다 - 멈춘다."
                      % env_retries)
                journal("환경사고 반복 %d 회 - 멈춤" % env_retries)
                return 3
            print("환경사고/도중에죽음이다. 이 바퀴는 표본에서 빼고 다시 돈다 (%d/%d)."
                  % (env_retries, a.max_env_retry))
            round_no -= 1          # 이 바퀴는 세지 않는다
            continue

        if c["로그깨짐"]:
            # 사유를 못 읽는 채로 "결함이다/아니다" 를 말하지 않는다.
            print("")
            print("로그가 깨져 실패 사유를 못 읽는다. 그 단계만 다시 돌린다.")
            journal("로그깨짐 %d 건 - 재실행" % c["로그깨짐"])
            for r in rows:
                if r["kind"] == "로그깨짐":
                    run_round(round_no, ["--only", r["stage"]],
                              tag="_재실행_%s" % r["stage"])
            rows = triage()
            out = save_triage(rows, round_no)
            c = out["counts"]
            print_triage(rows)

        if c["진짜결함"] or c["시간초과"]:
            print("\n진짜결함이 있다. 자동으로 못 고친다 - 판단이 필요하다.")
            print("진단서: %s" % TRIAGE)
            journal("진짜결함 %d 건으로 멈춤" % c["진짜결함"])
            return 1

        if c["표본부족"]:
            print("\n남은 것은 표본부족뿐이다. --precise 로 다시 돌려야 초록이 된다.")
            journal("표본부족 %d 건만 남음" % c["표본부족"])
            return 1

        if c["안돌았음"]:
            print("\n아직 안 돈 단계가 있다. 한 바퀴 더 돈다.")
            continue

        print("\n전부 초록이다.")
        journal("전부 초록 (바퀴 %d)" % round_no)
        return 0

    print("\n바퀴를 %d 번 다 돌았다. 진단서를 보라." % a.rounds)
    return 1


if __name__ == "__main__":
    sys.exit(main())
