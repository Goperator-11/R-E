import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(HERE, "state")
STATE = os.path.join(STATE_DIR, "pipeline.json")
RESULTS = os.path.join(HERE, "results")
WSL_ROOT = "/mnt/c/dev/pq_afec"

sys.path.insert(0, HERE)
from _journal import atomic_write_json


def _harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


class Stage(object):
    def __init__(self, sid, title, runner, cmd, outputs, scripts,
                 deps=(), timeout=7200, optional=False, note=""):
        self.id = sid
        self.title = title
        self.runner = runner
        self.cmd = cmd
        self.outputs = list(outputs)
        self.scripts = list(scripts)
        self.deps = list(deps)
        self.timeout = timeout
        self.optional = optional
        self.note = note

    def fingerprint(self):
        h = hashlib.sha256()
        h.update(self.runner.encode())
        h.update(json.dumps(self.cmd, ensure_ascii=False).encode())
        for rel in sorted(self.scripts):
            p = os.path.join(ROOT, rel)
            h.update(rel.encode())
            if os.path.exists(p):
                with open(p, "rb") as f:
                    h.update(hashlib.sha256(f.read()).digest())
            else:
                h.update(b"MISSING")
        return h.hexdigest()[:16]

    def outputs_present(self):
        return all(os.path.exists(os.path.join(ROOT, o)) for o in self.outputs)


def build_stages():
    py = sys.executable
    S = []

    S.append(Stage(
        "verify", "알고리즘 검증 스위트 (기준선, 후퇴 금지)",
        "win", [py, "verify.py"],
        outputs=[], scripts=["verify.py", "afec/controller.py", "afec/channel.py",
                             "afec/estimator.py", "afec/handshake.py",
                             "afec/cache.py", "afec/rs.py", "afec/sim.py"],
        timeout=1800,
        note="이게 실패하면 아래 모든 결과의 근거가 무너지므로 파이프라인을 멈춘다"))

    S.append(Stage(
        "e1", "ML-KEM 크기·속도 실측 (OpenSSL 3.5.5)",
        "win", [py, "experiments/e1_mlkem_bench.py"],
        outputs=["experiments/results/e1_mlkem.json"],
        scripts=["experiments/e1_mlkem_bench.py"], timeout=1800))

    S.append(Stage(
        "e2", "TLS 1.3 핸드셰이크 플라이트 바이트 실측",
        "win", [py, "experiments/e2_tls_flights.py"],
        outputs=["experiments/results/e2_tls_flights.json"],
        scripts=["experiments/e2_tls_flights.py"], timeout=2400))

    S.append(Stage(
        "e3", "QUIC Initial 프레이밍 + 공개 서버 실제 캡처",
        "win", [py, "experiments/e3_quic_capture.py"],
        outputs=["experiments/results/e3_quic.json"],
        scripts=["experiments/e3_quic_capture.py"], deps=["e2"], timeout=2400))

    S.append(Stage(
        "e4", "QUIC Initial 복호화 -> 진짜 ClientHello 바이트",
        "win", [py, "experiments/e4_quic_decrypt.py"],
        outputs=["experiments/results/e4_quic_clienthello.json"],
        scripts=["experiments/e4_quic_decrypt.py"], timeout=2400))

    S.append(Stage(
        "e5", "실제 Chrome ClientHello (TCP + QUIC)",
        "win", [py, "experiments/e5_browser_ch.py"],
        outputs=["experiments/results/e5_browser_ch.json"],
        scripts=["experiments/e5_browser_ch.py", "experiments/e4_quic_decrypt.py"],
        deps=["e4"], timeout=1200, optional=True,
        note="Chrome이 없거나 udp/443을 못 잡으면 건너뛴다"))

    S.append(Stage(
        "e6", "netem 손실 트레이스 수집 + GE 환율표",
        "wsl-unshare",
        "cd %s && unshare -r -m -n python3 -u experiments/e6_netem_traces.py "
        "--n 500000 --pps 10000" % WSL_ROOT,
        outputs=["experiments/results/e6_netem.json"],
        scripts=["experiments/e6_netem_traces.py", "experiments/probe.py"],
        timeout=5400,
        note="설정별로 결과를 병합하므로 중간에 멈춰도 남은 설정만 다시 돈다"))

    S.append(Stage(
        "e19", "RTT 스윕 + 네트워크 혼잡 재현 (계획서 요구)",
        "wsl-unshare",
        "cd %s && unshare -r -m -n python3 -u experiments/e19_rtt_congestion.py "
        "--rtts 10,20,50,100 --loads 50,80,100,120 --probe-n 20000" % WSL_ROOT,
        outputs=["experiments/results/e19_rtt_congestion.json"],
        scripts=["experiments/e19_rtt_congestion.py", "experiments/probe.py",
                 "afec/estimator.py", "afec/controller.py"],
        timeout=7200,
        note="1차에서 통째로 빠졌던 부분. 계획서 「연구 내용 2」는 손실만이 아니라 "
             "RTT 변화와 네트워크 혼잡도 재현하라고 한다. 혼잡은 비용식의 g 가 "
             "존재하는 이유이므로, 이걸 안 하면 설계의 핵심 주장이 미검증으로 남는다."))

    S.append(Stage(
        "e7", "실측 트레이스 위 정책 비교 (시드 64)",
        "wsl", "cd %s && python3 -u experiments/e7_policy_eval.py "
               "--seeds 64 --trials 20000" % WSL_ROOT,
        outputs=["experiments/results/e7_policy.json"],
        scripts=["experiments/e7_policy_eval.py", "afec/sim.py",
                 "afec/controller.py", "afec/estimator.py"],
        deps=["e6"], timeout=7200))

    S.append(Stage(
        "e8", "FEC 부호화 CPU 실측 (파이썬 vs C)",
        "wsl", "cd %s && python3 -u experiments/e8_cpu_cost.py" % WSL_ROOT,
        outputs=["experiments/results/e8_cpu.json"],
        scripts=["experiments/e8_cpu_cost.py", "experiments/rs_bench.c",
                 "afec/rs.py"],
        deps=["e1"], timeout=3600))

    S.append(Stage(
        "e9", "모델 예측 vs 실측 블록 실패율 (핵심 검증)",
        "wsl", "cd %s && python3 -u experiments/e9_model_validation.py" % WSL_ROOT,
        outputs=["experiments/results/e9_validation.json"],
        scripts=["experiments/e9_model_validation.py", "afec/channel.py"],
        deps=["e6"], timeout=3600))

    S.append(Stage(
        "quicbed", "quic-go 실험 바이너리 빌드",
        "wsl", "cd %s/experiments/quicbed && sed 's/\\r//' build.sh > /tmp/b.sh "
               "&& bash /tmp/b.sh" % WSL_ROOT,
        outputs=[], scripts=["experiments/quicbed/build.sh",
                             "experiments/quicbed/client.go",
                             "experiments/quicbed/server.go",
                             "experiments/quicbed/dataapp.go"],
        timeout=1800, optional=True,
        note="Go가 없으면 e12/e13을 건너뛴다"))

    S.append(Stage(
        "e12", "실제 quic-go + ML-KEM + XOR 패리티 (핸드셰이크)",
        "wsl-unshare",
        "cd %s && unshare -r -m -n python3 -u experiments/e12_quic_testbed.py "
        "--n 600" % WSL_ROOT,
        outputs=["experiments/results/e12_quic_testbed.json"],
        scripts=["experiments/e12_quic_testbed.py",
                 "experiments/quicbed/shim.py"],
        deps=["quicbed"], timeout=10800, optional=True))

    S.append(Stage(
        "e13", "실제 QUIC 데이터 구간 + 진짜 제어기/RS",
        "wsl-unshare",
        "cd %s && unshare -r -m -n python3 -u experiments/e13_data_phase_live.py "
        "--n 4000 --pps 40 --rate-mbps 50 --budget-ms 5 --timeout 240"
        % WSL_ROOT,
        outputs=["experiments/results/e13_data_live.json"],
        scripts=["experiments/e13_data_phase_live.py",
                 "experiments/quicbed/shim_data.py",
                 "experiments/quicbed/dataapp.go",
                 "afec/controller.py", "afec/estimator.py",
                 "afec/channel.py", "afec/rs.py"],
        deps=["quicbed"], timeout=10800, optional=True,
        note="⚠️ --pps 와 --rate-mbps 는 다른 것이다. pps 는 응용이 실제로 "
             "내보내는 속도(QUIC 혼잡제어에 걸리지 않도록 낮게), rate-mbps 는 "
             "제어기가 알아야 할 **링크 용량**(veth 는 기가비트급). 이 둘을 같게 "
             "두면 심볼 전송비가 회복 대가보다 커져 비용식이 정당하게 r=0 을 "
             "고르고, 실험이 알고리즘을 검증하지 못한다."))

    S.append(Stage(
        "e15", "모델 vs 실제 quic-go 방향 대조 (분위수별)",
        "wsl", "cd %s && python3 -u experiments/e15_reconcile.py" % WSL_ROOT,
        outputs=["experiments/results/e15_reconcile.json"],
        scripts=["experiments/e15_reconcile.py", "afec/sim.py"],
        deps=["e12", "e7"], timeout=3600,
        note="E7(모델 평균)과 E12(실측 중앙값)의 방향 차이가 같은 분포의 다른 통계인지 확인"))

    S.append(Stage(
        "e10", "보고서 그림 생성 (matplotlib)",
        "win", [py, "experiments/e10_figures.py"],
        outputs=["experiments/figures/fig1_mlkem_performance.png"],
        scripts=["experiments/e10_figures.py"],
        deps=["e1", "e3", "e4", "e6", "e7", "e8", "e9"], timeout=1800))

    S.append(Stage(
        "report", "실측 결과표 자동 생성 (JSON -> 표·결론)",
        "win", [py, "experiments/e14_report.py"],
        outputs=["docs/실측 결과표.md"],
        scripts=["experiments/e14_report.py"],
        deps=["e1", "e6", "e7", "e8", "e9", "e12", "e13", "e15", "e19"],
        timeout=1200))

    return S


def load_state():
    if not os.path.exists(STATE):
        return {"stages": {}, "history": []}
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        bad = STATE + ".corrupt"
        try:
            os.replace(STATE, bad)
            sys.stdout.write("state file was unreadable, moved to %s\n" % bad)
        except OSError:
            pass
        return {"stages": {}, "history": []}


def save_state(st):
    atomic_write_json(STATE, st)


def stage_status(stage, st):
    rec = st["stages"].get(stage.id)
    if not rec:
        return "pending", "한 번도 안 돌았음"
    if rec.get("status") != "done":
        return "pending", "지난번 %s" % rec.get("status", "?")
    if rec.get("fingerprint") != stage.fingerprint():
        return "stale", "스크립트가 바뀜"
    if not stage.outputs_present():
        return "stale", "산출물이 없어짐"
    return "done", rec.get("finished", "")


def resolve(stages, st, force):
    by_id = {s.id: s for s in stages}
    need = set(force)
    for s in stages:
        status, _ = stage_status(s, st)
        if status != "done":
            need.add(s.id)
    changed = True
    while changed:
        changed = False
        for s in stages:
            if s.id in need:
                continue
            if any(d in need for d in s.deps):
                need.add(s.id)
                changed = True
    order = [s.id for s in stages if s.id in need]
    return order, by_id


def run_stage(stage, verbose=True):
    t0 = time.time()
    if stage.runner == "win":
        cmd = stage.cmd
        proc_kw = dict(cwd=ROOT)
        shell = False
    else:
        cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-lc", stage.cmd]
        proc_kw = dict()
        shell = False
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=stage.timeout, env=env, shell=shell,
                           **proc_kw)
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        err = "" if ok else "exit %d" % p.returncode
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or "") if isinstance(e.stdout, str)
               else (e.stdout or b"").decode("utf-8", "replace"))
        ok = False
        err = "timeout after %ds" % stage.timeout
    dt = time.time() - t0
    log = os.path.join(STATE_DIR, "log_%s.txt" % stage.id)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        f.write(out)
    return ok, err, dt, out, log


def cmd_status(stages, st):
    print("=" * 92)
    print("PQ-AFEC 파이프라인 상태")
    print("=" * 92)
    print("%-9s %-8s %-46s %s" % ("stage", "state", "title", "note"))
    print("-" * 92)
    ndone = 0
    for s in stages:
        status, why = stage_status(s, st)
        if status == "done":
            ndone += 1
        rec = st["stages"].get(s.id, {})
        extra = why
        if status == "done" and rec.get("duration"):
            extra = "%.0fs" % rec["duration"]
        elif status != "done" and rec.get("error"):
            extra = rec["error"][:34]
        mark = {"done": "[완료]", "stale": "[갱신필요]", "pending": "[대기]"}[status]
        opt = " (선택)" if s.optional else ""
        print("%-9s %-10s %-46s %s" % (s.id, mark, (s.title + opt)[:46], extra))
    print("-" * 92)
    print("%d / %d 완료" % (ndone, len(stages)))
    return ndone


def main():
    _harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--loop", action="store_true",
                    help="전부 끝날 때까지 재시도하며 반복")
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--force", action="append", default=[],
                    help="이 단계를 (그리고 그 아래를) 다시 돌린다")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--reset", action="store_true", help="상태를 전부 지운다")
    ap.add_argument("--adopt", action="append", default=[],
                    help="이미 산출물이 있는 단계를 '완료'로 인수한다")
    a = ap.parse_args()

    stages = build_stages()
    if a.reset:
        if os.path.exists(STATE):
            os.remove(STATE)
        print("state cleared")
        return 0

    if a.adopt:
        st = load_state()
        by_id = {s.id: s for s in stages}
        for sid in a.adopt:
            s = by_id.get(sid)
            if not s:
                print("모르는 단계: %s" % sid)
                continue
            if s.outputs and not s.outputs_present():
                print("%-9s 인수 불가 - 산출물이 없다" % sid)
                continue
            st["stages"][sid] = {
                "status": "done", "fingerprint": s.fingerprint(),
                "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": 0.0, "adopted": True,
            }
            print("%-9s 인수됨" % sid)
        save_state(st)
        return 0

    st = load_state()
    if a.status:
        cmd_status(stages, st)
        return 0

    rounds = a.max_rounds if a.loop else 1
    for rnd in range(1, rounds + 1):
        st = load_state()
        order, by_id = resolve(stages, st, a.force if rnd == 1 else [])
        if a.only:
            order = [i for i in order if i in a.only]
        if not order:
            print("")
            print("할 일이 없다 - 전부 완료됨.")
            cmd_status(stages, st)
            return 0

        print("=" * 92)
        print("라운드 %d/%d : 실행할 단계 %d개 -> %s"
              % (rnd, rounds, len(order), ", ".join(order)))
        print("=" * 92)

        blocked = set()
        for sid in order:
            s = by_id[sid]
            if any(d in blocked for d in s.deps):
                print("[건너뜀] %-9s 선행 단계 실패" % sid)
                blocked.add(sid)
                continue

            st = load_state()
            st["stages"].setdefault(sid, {})
            st["stages"][sid].update({
                "status": "running",
                "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                "fingerprint": s.fingerprint(),
            })
            save_state(st)

            print("")
            print("[실행] %-9s %s" % (sid, s.title))
            ok, err, dt, out, log = run_stage(s)
            tail = [l for l in out.strip().splitlines() if l.strip()][-4:]
            for l in tail:
                print("        | %s" % l[:100])

            st = load_state()
            rec = st["stages"].setdefault(sid, {})
            rec["fingerprint"] = s.fingerprint()
            rec["duration"] = dt
            rec["log"] = os.path.relpath(log, ROOT)
            if ok and s.outputs_present():
                rec["status"] = "done"
                rec["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
                rec.pop("error", None)
                print("        -> 완료 (%.0f초)" % dt)
            else:
                rec["status"] = "failed"
                rec["error"] = err or "산출물 없음"
                print("        -> 실패: %s  (로그: %s)" % (rec["error"], rec["log"]))
                if s.optional:
                    print("        (선택 단계라 계속 진행한다)")
                else:
                    blocked.add(sid)
                    if sid == "verify":
                        st["history"].append("verify 실패로 중단")
                        save_state(st)
                        print("")
                        print("*** 검증이 실패했다. 다른 결과를 만들기 전에 "
                              "여기부터 고쳐야 한다. ***")
                        return 2
            st["history"].append({"stage": sid, "ok": bool(ok),
                                  "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                  "sec": round(dt, 1)})
            save_state(st)

        st = load_state()
        remaining = [s.id for s in stages
                     if stage_status(s, st)[0] != "done" and not s.optional]
        if not remaining:
            break
        if a.loop and rnd < rounds:
            print("")
            print("남은 단계 %s - 다음 라운드에서 재시도" % remaining)

    print("")
    cmd_status(stages, load_state())
    return 0


if __name__ == "__main__":
    sys.exit(main())
