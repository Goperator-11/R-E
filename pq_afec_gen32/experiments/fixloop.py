from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(HERE, "state")
LOOP2_STATE = os.path.join(STATE_DIR, "loop2.json")
TRIAGE = os.path.join(STATE_DIR, "fixloop_triage.json")
JOURNAL = os.path.join(STATE_DIR, "fixloop.log")
LOCK = os.path.join(STATE_DIR, "fixloop.lock")
PY = sys.executable

ENV_EXITS = {
    3221226091: "0xC000026B STATUS_DLL_INIT_FAILED_LOGOFF — 세션 로그오프가 죽였다",
    3221225786: "0xC000013A — Ctrl+C / 콘솔 닫힘",
    3221225794: "0xC0000142 — DLL 초기화 실패 (대개 종료 중)",
    3221225725: "0xC00000FD — 스택 넘침 (환경 아님일 수도, 로그를 보라)",
}
ENV_AMBIGUOUS = {3221225725}

SAMPLE_WORDS = ("반폭", "신뢰구간", "신뢰반폭", "표본이", "정밀도", "필요 N")

FAIL_LINE = re.compile(r"^\s*\[(실패|fail|미흡)\]\s*(.*)$")
SCORE_LINE = re.compile(
    r"^\s*(?:새 영역 시험\s+)?(\d+)\s*/\s*(\d+)\s*통과(?:\s*\|.*)?\s*$")


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20).stdout or ""
    except Exception:
        return True
    return str(pid) in out


def _running_measurement():
    me = os.getpid()
    try:
        r = subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", "-lc",
                            "pgrep -x qamp | head -3"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        if (r.stdout or "").strip():
            return "WSL 안에서 qamp 가 돌고 있다 (pid %s)" % (
                " ".join((r.stdout or "").split()))
    except Exception:
        return "WSL 을 못 물어봤다 - 돌고 있다고 본다"
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


def loop2_state():
    try:
        with open(LOOP2_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"stages": {}, "history": []}


def stage_ids():
    sys.path.insert(0, HERE)
    import loop2
    st = loop2.load_state()
    stages = loop2.build_stages()
    out = []
    for s in stages:
        stt, note = loop2.stage_status(s, st)
        out.append((s.id, s.title, stt, note))
    return out


def fingerprints():
    sys.path.insert(0, HERE)
    import loop2
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
    fails, score = [], None
    for ln in text.splitlines():
        m = FAIL_LINE.match(ln)
        if m:
            failure = m.group(2).strip()
            if not re.match(r"재고\s*:", failure):
                fails.append(failure)
            continue
        m = SCORE_LINE.match(ln)
        if m:
            score = (int(m.group(1)), int(m.group(2)))
    return fails, score


def round_stage_scope(extra_args, log=None):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--only", nargs="*", default=None)
    selected, _ = parser.parse_known_args(list(extra_args))
    if log:
        try:
            with open(log, encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if line.startswith("실행할 단계:"):
                        return [sid.strip() for sid in line.split(":", 1)[1].split(",")
                                if sid.strip()]
        except OSError:
            pass
    return selected.only or None


def classify(sid, rec, loop2_status, note, text, nbytes, round_rc=None):
    err = (rec or {}).get("error", "") or ""
    secs = float((rec or {}).get("seconds") or 0.0)

    if loop2_status == "done":
        return "통과", "", [], ""

    if not rec:
        return "안돌았음", "이 단계 기록이 없다 (%s)" % note, [], "돌려라"

    if loop2_status == "stale":
        return ("안돌았음", "%s - 옛 결과라 못 믿는다" % note, [],
                "다시 돌려라. 통과로 세면 안 된다.")

    if (rec or {}).get("status") in ("skipped", "stale_deps") or "상류 무효" in err:
        return ("안돌았음", "상류가 무효인 채로 돈 결과라 근거가 없다 (%s)" % err,
                [], "상류를 먼저 확인하라.")

    fails, score = failed_checks(text)
    m = re.search(r"exit (-?\d+)", err)
    code = int(m.group(1)) if m else None
    completed = score is not None or code == 0

    if err.startswith("timeout"):
        return ("시간초과", "%s (%.0f 초 돌다 잘림)" % (err, secs), [],
                "단계 timeout 을 늘리거나 표본을 줄여라. 자를 건드리지 마라.")

    if not completed and code in ENV_EXITS:
        note = "" if code not in ENV_AMBIGUOUS else " ⚠️ 애매하다 - 로그를 직접 봐라"
        return ("환경사고", "%s: %s%s" % (err, ENV_EXITS[code], note), [],
                "결함이 아니다. 다시 돌린다. 이 라운드는 표본에서 뺀다.")

    if not completed and secs < 2.0 and nbytes == 0:
        return ("환경사고",
                "%.1f 초 만에 끝나고 로그가 0 바이트 - 실행조차 못 했다 (%s)" % (secs, err),
                [], "결함이 아니다. 다시 돌린다.")

    broken = text.count("�")
    if broken > 20:
        return ("로그깨짐",
                "로그에 U+FFFD 가 %d 개 - 글자가 깨져 실패 사유를 못 읽는다 (%s)"
                % (broken, err),
                [], "이 단계를 다시 돌려라. 다시 깨지면 run_stage 의 encoding 을 봐라.")

    if not fails and not completed:
        return ("도중에죽음",
                "완료 요약과 실패 검사를 확인하지 못했다 - '%s' 줄도 실패 표시도 없다 "
                "(로그 %d B, %s, %.0f 초)%s"
                % ("N / M 통과", nbytes, err, secs,
                   "" if round_rc is None else
                   "  바퀴 자체의 종료 코드 %s" % round_rc),
                [], "종료 원인을 확인하라. 완료된 실패를 지우려고 재측정하지 마라.")

    if not fails:
        return ("진짜결함",
                "%s 인데 점수는 %s 이고 실패한 검사를 못 찾았다 (로그 %d B)"
                % (err, "%d/%d" % score if score else "완료 점수 없음", nbytes),
                [], "로그를 직접 봐라. 판정과 종료 코드가 어긋난다.")

    def is_sample(s):
        return any(w in s for w in SAMPLE_WORDS)

    if all(is_sample(s) for s in fails):
        return ("표본부족",
                "실패 %d 건이 전부 정밀도 (%s)" % (len(fails), score and "%d/%d" % score),
                fails,
                "결함이 아니라 못 잰 것이다. --precise 로 N 을 늘려라. "
                "기준(자)을 완화하지 마라.")

    real = [s for s in fails if not is_sample(s)]
    return ("진짜결함",
            "실패 %d 건 중 진짜 %d 건 (%s)" % (len(fails), len(real),
                                            score and "%d/%d" % score),
            fails, "고쳐야 한다. 자를 늘리지 말고 무엇이 틀렸는지부터 찾아라.")


def triage(round_rc=None, selected=None):
    st = loop2_state()
    rows = []
    scope = None if selected is None else set(selected)
    for sid, title, stt, note in stage_ids():
        if scope is not None and sid not in scope:
            continue
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


def run_round(round_no, extra_args, tag=""):
    log = os.path.join(STATE_DIR,
                       "fixloop_round%02d%s.txt" % (round_no, tag))
    cmd = [PY, "-u", os.path.join(HERE, "loop2.py"), "--loop", "--keep-going"]
    cmd += list(extra_args)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    print("[바퀴 %d] %s" % (round_no, " ".join(cmd)), flush=True)
    t0 = time.time()
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


def _graph_order_violations():
    sys.path.insert(0, HERE)
    import loop2
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

    def _ss(rec_status, fp_ok):
        sys.path.insert(0, HERE)
        import loop2
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

    order, viol = _graph_order_violations()
    check("모든 단계가 자기 상류 뒤에 온다 (선언 순서 == 의존 순서)",
          viol, [])
    check("[부정] 그래프가 비어 있지 않다 (위 검사가 공허하지 않다)",
          len(order) > 10, True)

    print("\n%d checks, %d failed" % (n, bad))
    return 1 if bad else 0


def main():
    print("The legacy fixloop CLI is disabled in gen32. Use the documented gen32 "
          "tests, isolated builder, parity gate and development replay.", file=sys.stderr)
    return 2


def historical_main():
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
    ap.add_argument("--loop2-arg", nargs=argparse.REMAINDER, default=[],
                    help="이 뒤의 모든 인자를 loop2 에 그대로 넘긴다 "
                         "(맨 마지막에 적을 것. 예: --loop2-arg --only p18)")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if a.status:
        rows = triage(selected=round_stage_scope(a.loop2_arg))
        print_triage(rows)
        bad = ("진짜결함", "로그깨짐", "시간초과")
        return 0 if not any(r["kind"] in bad for r in rows) else 1

    if a.detach:
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


def detached_command(a):
    cmd = [PY, "-u", os.path.abspath(__file__),
           "--rounds", str(a.rounds), "--max-env-retry", str(a.max_env_retry)]
    if a.force_unlock:
        cmd.append("--force-unlock")
    if a.loop2_arg:
        cmd += ["--loop2-arg"] + list(a.loop2_arg)
    return cmd


def detached_launcher(cmd, out, env):
    settings = {k: v for k, v in env.items()
                if k.startswith("PADFEC_") or k in ("PYTHONIOENCODING", "PYTHONUNBUFFERED", "WSLENV")}
    fd, path = tempfile.mkstemp(prefix="fixloop_launcher_", suffix=".py", dir=STATE_DIR)
    source = ("import os, subprocess, sys\n"
              "env = dict(os.environ)\n"
              "env.update(%r)\n"
              "with open(%r, 'ab', buffering=0) as log:\n"
              "    result = subprocess.run(%r, cwd=%r, env=env, stdout=log, "
              "stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)\n"
              "sys.exit(result.returncode)\n" % (settings, out, cmd, ROOT))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(source)
    return [PY, "-u", path]


def detach(a):
    NEW_CONSOLE = 0x00000010
    NEW_GROUP = 0x00000200
    BREAKAWAY = 0x01000000
    tried = []
    out = os.path.join(STATE_DIR, "fixloop_detached.txt")
    cmd = detached_command(a)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    f = open(out, "a", encoding="utf-8", errors="replace")
    f.write("\n%s  ==== 분리 실행 시작 ====\n" % now())
    f.flush()
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    for flags in (NEW_CONSOLE | NEW_GROUP | BREAKAWAY,):
        try:
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=f,
                                 stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL,
                                 creationflags=flags, startupinfo=si,
                                 close_fds=True)
        except OSError:
            tried.append("0x%08x" % flags)
            continue
        print("떨어져 나갔다: pid %d" % p.pid)
        print("진행:  python experiments/fixloop.py --status")
        print("원문:  %s" % out)
        journal("분리 실행 pid %d (rounds=%d)" % (p.pid, a.rounds))
        f.close()
        return 0
    f.close()
    try:
        launcher = detached_launcher(cmd, out, env)
        ps_cmd = (
            "$startup = New-CimInstance -ClassName Win32_ProcessStartup "
            "-ClientOnly -Property @{ShowWindow=0}; "
            "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName "
            "Create -Arguments @{CommandLine='%s'; CurrentDirectory='%s'; "
            "ProcessStartupInformation=$startup}; "
            "if ($r.ReturnValue -eq 0) { $r.ProcessId } else { exit 1 }"
            % (subprocess.list2cmdline(launcher).replace("'", "''"),
               ROOT.replace("'", "''")))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd],
                           capture_output=True, text=True, timeout=60)
        pid = (r.stdout or "").strip().splitlines()[-1:] or [""]
        if r.returncode == 0 and pid[0].isdigit() and int(pid[0]) > 0:
            print("떨어져 나갔다 (WMI): pid %s" % pid[0])
            print("진행:  python experiments/fixloop.py --status")
            print("원문:  %s" % out)
            journal("분리 실행 pid %s (rounds=%d, WMI)" % (pid[0], a.rounds))
            return 0
    except Exception as e:
        print("WMI 분리 실행도 실패: %s" % e)

    print("분리 실행에 실패했다. 앞에서 그냥 돌려라 (--detach 빼고).")
    return 3


def supervise(a):
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
        tag = "_환경재시도%02d" % env_retries if env_retries else ""
        rc, dt, log = run_round(round_no, a.loop2_arg, tag=tag)
        moved = [sid for sid, h in fingerprints().items() if fp0.get(sid) != h]
        if moved:
            print("\n⚠ 이 바퀴가 도는 중에 소스가 바뀌었다: %s" % ", ".join(moved))
            print("  이 바퀴의 그 단계 결과는 증거가 아니다. 다음 바퀴에서 다시 돈다.")
            journal("바퀴 %d 소스 변경 감지: %s" % (round_no, ", ".join(moved)))
        scope = round_stage_scope(a.loop2_arg, log)
        rows = triage(rc, selected=scope)
        out = save_triage(rows, round_no, moved)
        c = out["counts"]
        journal("바퀴 %d  exit %d  %.1f분  진짜결함 %d · 로그깨짐 %d · 표본부족 %d "
                "· 도중에죽음 %d · 환경사고 %d · 시간초과 %d · 안돌았음 %d · 통과 %d"
                % (round_no, rc, dt / 60.0, c["진짜결함"], c["로그깨짐"],
                   c["표본부족"], c["도중에죽음"], c["환경사고"], c["시간초과"],
                   c["안돌았음"], c["통과"]))
        print_triage(rows)

        if c["진짜결함"] or c["시간초과"] or c["표본부족"]:
            print("\n검사 미통과 또는 정밀도 부족이 남았다. 원인을 검토한 뒤 판단하라.")
            print("진단서: %s" % TRIAGE)
            print("진단 갈래만으로 알고리즘 구현 결함이나 성능 개선을 확정하지 않는다.")
            journal("완료 실패/시간초과/표본부족으로 멈춤 (자동 재측정 없음)")
            return 1

        if c["환경사고"] or c["도중에죽음"]:
            env_retries += 1
            if env_retries > a.max_env_retry:
                print("환경사고/완료 미확인이 %d 번 되풀이됐다. 재시도 한도로 멈춘다."
                      % env_retries)
                journal("환경사고 반복 %d 회 - 멈춤" % env_retries)
                return 3
            print("환경사고/도중에죽음이다. 이 바퀴는 표본에서 빼고 다시 돈다 (%d/%d)."
                  % (env_retries, a.max_env_retry))
            round_no -= 1
            continue

        if c["로그깨짐"]:
            print("")
            print("로그가 깨져 실패 사유를 못 읽는다. 그 단계만 다시 돌린다.")
            journal("로그깨짐 %d 건 - 재실행" % c["로그깨짐"])
            for r in rows:
                if r["kind"] == "로그깨짐":
                    run_round(round_no, ["--only", r["stage"]],
                              tag="_재실행_%s" % r["stage"])
            rows = triage(selected=scope)
            out = save_triage(rows, round_no)
            c = out["counts"]
            print_triage(rows)

        if any(c[k] for k in ("진짜결함", "시간초과", "표본부족", "로그깨짐",
                              "환경사고", "도중에죽음")):
            print("\n재실행 뒤에도 실패 또는 완료 미확인이 남았다. 자동 재측정하지 않는다.")
            journal("재실행 뒤 남은 문제로 멈춤")
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
