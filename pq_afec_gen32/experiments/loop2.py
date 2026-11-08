from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from _journal import runtime_context, atomic_write_json as durable_write_json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(HERE, "state")
STATE = os.path.join(STATE_DIR, "loop2.json")

PY = sys.executable
def wsl_path(path):
    path = os.path.abspath(path).replace("\\", "/")
    if len(path) > 2 and path[1] == ":":
        return "/mnt/" + path[0].lower() + path[2:]
    return path


WSL_ROOT = shlex.quote(wsl_path(ROOT))
UNSHARE = "cd %s && unshare -Urnm python3 -u " % WSL_ROOT

def _sources(subdir, suffix, core):
    found = []
    d = os.path.join(ROOT, *subdir.split("/"))
    try:
        for name in os.listdir(d):
            if name.endswith(suffix):
                found.append(subdir + "/" + name)
    except OSError:
        pass
    return sorted(set(found) | set(core))


def python_sources():
    excluded = {".git", ".venv", "venv", "__pycache__", "_build", "state",
                "results", "round1_backup", "node_modules"}
    found = []
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in excluded)
        for name in names:
            if name.endswith(".py"):
                found.append(os.path.relpath(os.path.join(directory, name), ROOT).replace("\\", "/"))
    return sorted(found)


_PARSE_FAILED = []


def _module_rel(name):
    if not name:
        return None
    top = name.split(".")[0]
    rel = "experiments/" + top + ".py"
    if os.path.exists(os.path.join(ROOT, *rel.split("/"))):
        return rel
    return None


def _imports_of(rel):
    p = os.path.join(ROOT, *rel.split("/"))
    try:
        with open(p, "rb") as f:
            tree = ast.parse(f.read(), filename=p)
    except (OSError, SyntaxError, ValueError):
        return None
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for al in node.names:
                names.add(al.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                names.add(node.module)
    return names


def deps_py(*entries):
    seen, stack = set(), []
    for e in entries:
        rel = e if e.startswith("experiments/") else "experiments/" + e
        if rel not in seen:
            seen.add(rel)
            stack.append(rel)
    while stack:
        rel = stack.pop()
        names = _imports_of(rel)
        if names is None:
            if os.path.exists(os.path.join(ROOT, *rel.split("/"))):
                seen.add(rel + "#PARSE-FAILED")
                if rel not in _PARSE_FAILED:
                    _PARSE_FAILED.append(rel)
            continue
        for name in names:
            sub = _module_rel(name)
            if sub and sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return sorted(seen)


ALGO = _sources("padfec", ".py",
                ["padfec/__init__.py", "padfec/capacity.py",
                 "padfec/codec.py", "padfec/amplif.py", "padfec/policy.py",
                 "padfec/table.py"]) + _sources(
                     "afec", ".py",
                     ["afec/__init__.py", "afec/channel.py", "afec/rs.py"])


def _quicbed_go_sources():
    return _sources("experiments/quicbed", ".go",
                    ["experiments/quicbed/qamp.go",
                     "experiments/quicbed/policy.go",
                     "experiments/quicbed/pfail_table.go"])


BED = sorted(set(["experiments/padbed.py", "experiments/quicbed/build.sh",
                  "experiments/quicbed/go.mod", "experiments/quicbed/go.sum"]
                 + _quicbed_go_sources()))


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def fingerprint_from_provenance(provenance):
    h = hashlib.sha256()
    h.update(json.dumps(provenance["runtime_context"], sort_keys=True).encode())
    h.update(provenance["runner"].encode())
    h.update(json.dumps(provenance["command"], ensure_ascii=False).encode())
    for key in ("deps", "soft_deps", "outputs"):
        h.update(json.dumps(sorted(provenance[key]), ensure_ascii=False).encode())
    for rel, digest in sorted(provenance["source_hashes"].items()):
        h.update(rel.encode())
        h.update(bytes.fromhex(digest) if digest is not None else b"MISSING")
    return h.hexdigest()[:16]


class Stage(object):
    def __init__(self, sid, title, runner, cmd, outputs, scripts, deps=(),
                 timeout=7200, note="", soft_deps=()):
        self.id = sid
        self.title = title
        self.runner = runner
        self.cmd = cmd
        self.outputs = list(outputs)
        self.scripts = sorted(set(scripts))
        self.soft_deps = list(soft_deps)
        self.deps = sorted(set(list(deps) + list(soft_deps)))
        self.timeout = timeout
        self.note = note

    def provenance(self):
        sources = {}
        for rel in sorted(set(self.scripts) | {"experiments/loop2.py", "experiments/_journal.py"}):
            p = os.path.join(ROOT, rel)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    sources[rel] = hashlib.sha256(f.read()).hexdigest()
            else:
                sources[rel] = None
        return {"schema_version": 1, "runtime_context": runtime_context(),
                "runtime_scope": "loop2_launcher_and_forwarded_PADFEC_env",
                "runner": self.runner, "command": list(self.cmd) if isinstance(self.cmd, list) else self.cmd,
                "deps": sorted(self.deps), "soft_deps": sorted(self.soft_deps),
                "outputs": sorted(self.outputs), "source_hashes": sources}

    def fingerprint(self):
        return fingerprint_from_provenance(self.provenance())

    def outputs_present(self):
        return all(os.path.isfile(os.path.join(ROOT, o)) for o in self.outputs)

    def output_hashes(self):
        hashes = {}
        for output in self.outputs:
            with open(os.path.join(ROOT, output), "rb") as f:
                hashes[output] = hashlib.sha256(f.read()).hexdigest()
        return hashes

    def observe_outputs(self):
        observed = {}
        for rel in self.outputs:
            path = os.path.join(ROOT, rel)
            try:
                before = os.stat(path)
                with open(path, "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                after = os.stat(path)
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    observed[rel] = None
                    continue
                observed[rel] = {"sha256": digest, "size": after.st_size,
                                 "mtime_ns": after.st_mtime_ns,
                                 "ctime_ns": after.st_ctime_ns,
                                 "file_id": after.st_ino, "device": after.st_dev}
            except OSError:
                observed[rel] = None
        return observed


def result_provenance(stage, before, started_ns, source_consistent):
    after = stage.observe_outputs()
    return {"schema_version": 1, "source_consistent": source_consistent,
            "started_at_ns": started_ns, "finished_at_ns": time.time_ns(),
            "observation_scope": "exclusive_writer_before_after_file_observation",
            "outputs": {rel: {
                "before": before.get(rel), "after": observed,
                "written_during_run": bool(observed and observed != before.get(rel))}
                for rel, observed in after.items()}}


def _cheap_first(stages, cheap=("p4", "p5")):
    by_id = {s.id: s for s in stages}
    pend = [by_id[c] for c in cheap if c in by_id]
    rest = [s for s in stages if s.id not in cheap]
    out, placed = [], set()

    def _drain():
        moved = True
        while moved:
            moved = False
            for s in list(pend):
                if all(d in placed for d in s.deps):
                    out.append(s)
                    placed.add(s.id)
                    pend.remove(s)
                    moved = True

    _drain()
    for s in rest:
        out.append(s)
        placed.add(s.id)
        _drain()
    out.extend(pend)
    return out


def build_stages():
    S = []

    S.append(Stage(
        "lint", "모든 .py 가 파싱되는가 (루프 밖 파일까지)",
        "win", [PY, "-m", "compileall", "-q"] + python_sources(),
        outputs=[], scripts=python_sources(),
        timeout=300,
        note="파싱 안 되는 파일이 있으면 여기서 멈춘다"))

    S.append(Stage(
        "table", "확률표를 Go 로 심는다 (pfail_table.go 생성)",
        "win", [PY, "-m", "padfec.table",
                "experiments/quicbed/pfail_table.go"],
        outputs=["experiments/quicbed/pfail_table.go"],
        scripts=ALGO, timeout=600,
        note="이 단계가 빠지면 Go 가 옛 확률표로 돈다"))

    S.append(Stage(
        "build", "Go 테스트베드 빌드 (CGO_ENABLED=0, /tmp/qamp 로 복사)",
        "wsl", "cd %s && bash experiments/quicbed/build.sh" % WSL_ROOT,
        outputs=[], scripts=BED, deps=["table"], timeout=900))

    S.append(Stage(
        "gate", "관문 - 부호 자체시험 (Go) + 기준 구현 시험 (Python) "
                "+ 정책 격자 대조",
        "wsl",
        "cd %s && " % WSL_ROOT +
        "[ -x /tmp/qamp ] || cp \"$HOME/quicbed/bin/qamp\" /tmp/qamp; "
        "/tmp/qamp -mode selftest && "
        "python3 -u experiments/gate_go_parity.py",
        outputs=["experiments/results/gate_go_parity.json"],
        scripts=BED + ALGO + deps_py("gate_go_parity.py"),
        deps=["build"], timeout=3600,
        note="여기서 실패하면 아래 모든 측정의 근거가 없다"))

    S.append(Stage(
        "p0", "환경 확인 (문서 단계 0) + ML-KEM 동일성 (OpenSSL 3.5 상호운용)",
        "wsl-unshare", UNSHARE + "experiments/p0_env.py",
        outputs=["experiments/results/p0_env.json"],
        scripts=BED + deps_py("p0_env.py") + [
            "experiments/quicbed/mlkemcheck.go",
            "experiments/quicbed/mlkem_interop.sh"],
        deps=["gate"], timeout=1800,
        note="문서의 환경·절차·ML-KEM 이 우리 쪽에서 그대로 성립하는지 먼저 못박는다"))

    S.append(Stage(
        "p1", "첫 비행 구조 실측 - 자연 k, 비행 바이트, 용량 정리 대조",
        "wsl-unshare", UNSHARE + "experiments/p1_flight.py",
        outputs=["experiments/results/p1_flight.json"],
        scripts=BED + ALGO + deps_py("p1_flight.py"),
        deps=["p0"], timeout=3600))

    S.append(Stage(
        "p2", "증폭 임계 - off/buf/on 세 팔, 교환비, 바이트 회계",
        "wsl-unshare", UNSHARE + "experiments/p2_threshold.py",
        outputs=["experiments/results/p2_threshold.json"],
        scripts=BED + ALGO + deps_py("p2_threshold.py"),
        deps=["p1"], timeout=14400))

    S.append(Stage(
        "p3", "복구 동작 + 손실 조건 효과 (문서 단계 3-4)",
        "wsl-unshare", UNSHARE + "experiments/p3_effect.py",
        outputs=["experiments/results/p3_effect.json"],
        scripts=BED + ALGO + deps_py("p3_effect.py"),
        deps=["p1"], timeout=21600))

    S.append(Stage(
        "p7", "결정적 검증 - 소거를 우리가 만들고 반드시 그래야 할 결과와 대조",
        "wsl-unshare", UNSHARE + "experiments/p7_verify.py",
        outputs=["experiments/results/p7_verify.json"],
        scripts=BED + deps_py("p7_verify.py"),
        deps=["p1"], timeout=5400,
        note="긍정 시험뿐 아니라 부정 시험 - 못 고치게 만들면 정말 못 고쳐야 한다"))

    S.append(Stage(
        "p8", "반복 재현성 + 음성 대조 + 통계적 유의성",
        "wsl-unshare", UNSHARE + "experiments/p8_stability.py",
        outputs=["experiments/results/p8_stability.json"],
        scripts=BED + deps_py("p8_stability.py"),
        deps=["p1"], timeout=10800,
        note="한 번 잘 나온 수는 증거가 약하다 - 여러 번 재고, "
             "나오면 안 되는 곳에서 안 나오는지도 본다"))

    S.append(Stage(
        "p9", "환경 교차검증 - 문서 환경과 1차 환경에서 같은 값이 나오는가",
        "wsl-unshare", UNSHARE + "experiments/p9_crossenv.py",
        outputs=["experiments/results/p9_crossenv.json"],
        scripts=BED + deps_py("p9_crossenv.py") + [
            "experiments/quicbed/shim.py"],
        deps=["p1"], timeout=7200,
        note="결론이 하네스에 의존하면 그건 하네스의 성질이지 QUIC 의 성질이 아니다"))

    S.append(Stage(
        "p10", "완성도 - 미구현 재고조사 + 한 번도 안 해 본 영역",
        "wsl-unshare", UNSHARE + "experiments/p10_completeness.py",
        outputs=["experiments/results/p10_completeness.json"],
        scripts=BED + deps_py("p10_completeness.py"),
        deps=["p1"], timeout=7200,
        note="잘 되는 것 말고 아직 안 되는 것을 찾는다"))

    S.append(Stage(
        "p11", "폐루프 후회 - auto 가 최선 고정 m 만큼 하는가",
        "wsl-unshare", UNSHARE + "experiments/p11_adaptive.py",
        outputs=["experiments/results/p11_adaptive.json"],
        scripts=ALGO + deps_py("p11_adaptive.py") + BED,
        deps=["p1"], timeout=21600,
        note="후회는 두 값을 함께 본다(전 구간 / 수렴 후). 기준: 수렴 후 "
             "최악 후회 < 2 ms, 신뢰반폭 < 1 ms. 반폭이 안 내려가면 결함이 "
             "아니라 표본 부족이다(--precise 또는 PADFEC_P11_N)"))

    S.append(Stage(
        "p12", "양자 경계 절벽: ips 1279/1280/1281/1282/1300/1350/1450 "
               "임계 이분탐색",
        "wsl-unshare", UNSHARE + "experiments/p12_quantum.py",
        outputs=["experiments/results/p12_quantum.json"],
        scripts=ALGO + deps_py("p12_quantum.py") + BED,
        deps=["p1"], timeout=14400,
        note="명세 7절 1번 주장의 직접 시험. 1280 과 1279 는 같은 칸이어야 한다"))

    S.append(Stage(
        "p4", "모형 대 실측 대조 - 정책 예측이 맞았는가",
        "win", [PY, "experiments/p4_model.py"],
        outputs=["experiments/results/p4_model.json"],
        scripts=ALGO + deps_py("p4_model.py"),
        deps=["p2", "p3"], timeout=1800))

    S.append(Stage(
        "p5", "독립 감사 - Go/Python 교차검증, 용량정리 완전탐색, 불변식",
        "win", [PY, "experiments/p5_audit.py"],
        outputs=["experiments/results/p5_audit.json"],
        scripts=ALGO + deps_py("p5_audit.py") + [
            "experiments/quicbed/qamp.go"],
        deps=["gate"], timeout=3600))

    S.append(Stage(
        "p13", "B_eff 직접 측정 - 서버 첫 송신까지 도착한 클라 바이트 (명세 2.6)",
        "wsl-unshare", UNSHARE + "experiments/p13_beff.py",
        outputs=["experiments/results/p13_beff.json"],
        scripts=ALGO + deps_py("p13_beff.py") + BED,
        deps=["p1"], timeout=14400,
        note="명세 2.6 이 "
             "'반드시 직접 측정으로 확인해야 한다'고 한 항목. 통과 기준: "
             "x25519 on1 의 B_eff 가 (2560, 2986.7] 안"))

    S.append(Stage(
        "p14", "지배 보조정리 - 같은 Δ 에서 δ-패딩 팔 vs 패리티 팔",
        "wsl-unshare", UNSHARE + "experiments/p14_dominance.py",
        outputs=["experiments/results/p14_dominance.json"],
        scripts=ALGO + deps_py("p14_dominance.py") + BED,
        deps=["p1"], timeout=21600,
        note="통과 기준: 신용은 같고(임계 동일) 손실에서 패리티만 꼬리를 "
             "없앤다. 부정 시험으로 δ 팔의 복구는 0 이어야 한다"))

    S.append(Stage(
        "p16", "업링크 대역 실측 - J 의 t_tx 항에 출처를 만든다 (명세 3절)",
        "wsl-unshare", UNSHARE + "experiments/p16_uplink.py",
        outputs=["experiments/results/p16_uplink.json"],
        scripts=ALGO + deps_py("p16_uplink.py") + BED,
        deps=["p1"], timeout=3600,
        note="통과 기준: 무제한 조건은 팔별 Δ < 0.2 ms(대역 비용 없음), "
             "10 Mbps 조건은 임계경로 식이 팔별 0.25 ms 안. 부정 시험으로 "
             "옛 식(추가 바이트 전부)이 0.5 ms 넘게 어긋나야 한다"))

    S.append(Stage(
        "p17", "적응의 값어치 - 손실률이 변할 때 정책이 따라가는가",
        "wsl-unshare", UNSHARE + "experiments/p17_adaptive_value.py",
        outputs=["experiments/results/p17_adaptive_value.json"],
        scripts=ALGO + deps_py("p17_adaptive_value.py") + BED,
        deps=["p1"], timeout=21600,
        note="선택 기반 판정(적응률·적응 지연). 시간 이득은 정보로만 - "
             "이 표본으로는 시간으로 판정 불가(필요 N 약 4.6만/팔). "
             "조건 4 개(2Mbps·무제한·큰cert16000·RTT200)"))

    S.append(Stage(
        "p15", "v2 정책 후회 - δ·m 결합 정책 vs 최선 고정 조합",
        "wsl-unshare", UNSHARE + "experiments/p15_v2policy.py",
        outputs=["experiments/results/p15_v2policy.json"],
        scripts=ALGO + deps_py("p15_v2policy.py") + BED,
        deps=["p1"], timeout=21600,
        note="δ·m 결합 정책의 후회. 기준: 수렴 후 최악 후회 < 2 ms, "
             "신뢰반폭 < 1 ms. 반폭이 안 내려가면 표본 부족이다"
             "(--precise 또는 PADFEC_P15_N)"))

    S.append(Stage(
        "p18", "m_max 상한 - 고정팔 m=1..4 를 직접 재서 모형을 검증",
        "wsl-unshare", UNSHARE + "experiments/p18_mmax.py",
        outputs=["experiments/results/p18_mmax.json"],
        scripts=ALGO + deps_py("p18_mmax.py") + BED,
        deps=["p1"], timeout=21600,
        note="결정적 자리(cert 16,000·무손실 - m_max=2 정책이 포기하는 "
             "자리)는 작은 표본으로 판정되고, 손실 자리는 필요 표본이 "
             "커서 판정 불능으로 남을 수 있다"))

    S.append(Stage(
        "p20", "잔차 해부 - 모형이 어느 무리에서 틀리는가 + 필요 표본",
        "win", [PY, "experiments/p20_residual.py"],
        outputs=["experiments/results/p20_residual.json"],
        scripts=ALGO + deps_py("p20_residual.py"),
        deps=["p1"], soft_deps=["p15", "p16", "p17", "p18"],
        timeout=900,
        note="새 실측을 하지 않는다. 어긋난 자리를 이름 붙여 세는 것이 일이고, "
             "고칠지 더 잴지는 사람이 정한다"))

    S.append(Stage(
        "p19", "수치 출처 감사 - 보고된 수가 원자료에서 재계산되는가",
        "win", [PY, "experiments/p19_provenance.py"],
        outputs=["experiments/results/p19_provenance.json"],
        scripts=deps_py("p19_provenance.py"),
        soft_deps=["p3", "p7", "p11", "p14", "p15", "p16", "p17", "p18"],
        deps=[], timeout=600,
        note="요약 수치를 원자료에서 재계산해 대조한다. 불일치 0 이어야 한다"))

    S.append(Stage(
        "p6", "보고서 + PDF 요약",
        "win", [PY, "experiments/p6_report.py"],
        outputs=["docs/PADFEC 실측 보고서.md",
                 "docs/ML-KEM QUIC 핸드셰이크 FEC 요약.pdf",
                 "docs/PADFEC 보고서 출처.json"],
        scripts=ALGO + deps_py("p6_report.py"),
        deps=["p1", "p2", "p3", "p4", "p5", "p7", "p8", "p9", "p10",
              "p11", "p12", "p17", "p18"],
        soft_deps=["p13", "p15", "p16", "p19", "p20"],
        timeout=1800))

    return _cheap_first(S)


def atomic_write_json(path, obj):
    durable_write_json(path, obj)


def load_state():
    if not os.path.exists(STATE):
        return {"stages": {}, "history": []}
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        try:
            os.replace(STATE, STATE + ".corrupt")
        except OSError:
            pass
        return {"stages": {}, "history": []}


def stage_status(stage, st):
    rec = st["stages"].get(stage.id)
    if not rec:
        return "pending", "한 번도 안 돌았음"
    if rec.get("fingerprint") != stage.fingerprint():
        return "stale", "코드가 바뀜 (지난번 %s)" % rec.get("status", "?")
    if rec.get("status") != "done":
        return "pending", "지난번 %s" % rec.get("status", "?")
    if not stage.outputs_present():
        return "stale", "산출물이 없어짐"
    if rec.get("output_hashes") != stage.output_hashes():
        return "stale", "산출물 내용이 바뀌었거나 기록 지문이 없음"
    return "done", rec.get("finished", "")


def resolve(stages, st, force):
    need = set(force)
    for s in stages:
        if stage_status(s, st)[0] != "done":
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
    return [s.id for s in stages if s.id in need]


def dep_closure(stages, ids, hard_only=False):
    by_id = {s.id: s for s in stages}
    seen, stack = set(), [i for i in ids]
    while stack:
        s = by_id.get(stack.pop())
        if not s:
            continue
        soft = set(getattr(s, "soft_deps", ()))
        for d in s.deps:
            if hard_only and d in soft:
                continue
            if d not in seen:
                seen.add(d)
                stack.append(d)
    return [s.id for s in stages if s.id in seen]


def stale_upstream(stages, st, sid):
    by_id = {s.id: s for s in stages}
    bad = []
    for d in dep_closure(stages, [sid], hard_only=True):
        stt = stage_status(by_id[d], st)[0]
        if stt != "done":
            bad.append("%s(%s)" % (d, stt))
    return bad


def run_stage(stage):
    t0 = time.time()
    if stage.runner == "win":
        cmd = stage.cmd
        kw = dict(cwd=ROOT)
    else:
        cmd = ["wsl", "-d", "Ubuntu", "--", "bash", "-lc", stage.cmd]
        kw = {}
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    _pass = [k for k in env if k.startswith("PADFEC_")]
    if _pass:
        prev = env.get("WSLENV", "")
        names = ":".join(sorted(_pass))
        env["WSLENV"] = (prev + ":" + names) if prev else names
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=stage.timeout, env=env, **kw)
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        err = "" if ok else "exit %d" % p.returncode
        if ok and not stage.outputs_present():
            ok, err = False, "필수 산출물이 없다"
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (
            (e.stdout or b"").decode("utf-8", "replace"))
        ok, err = False, "timeout %ds" % stage.timeout
    dt = time.time() - t0
    os.makedirs(STATE_DIR, exist_ok=True)
    log = os.path.join(STATE_DIR, "log2_%s.txt" % stage.id)
    with open(log, "w", encoding="utf-8", errors="replace") as f:
        f.write(out or "")
    return ok, err, dt, out or "", log


def show_status(stages, st):
    print("=" * 94)
    print("PAD-FEC 루프 상태  (정본: %s)" % STATE)
    print("=" * 94)
    print("%-7s %-8s %-56s %s" % ("단계", "상태", "제목", "비고"))
    print("-" * 94)
    for s in stages:
        stt, note = stage_status(s, st)
        mark = {"done": "완료", "stale": "무효", "pending": "대기"}[stt]
        print("%-7s %-8s %-56s %s" % (s.id, mark, s.title[:56], note))
    print("-" * 94)
    todo = resolve(stages, st, [])
    print("남은 단계: %s" % (", ".join(todo) if todo else "없음 - 전부 완료"))


def main():
    print("The legacy loop2 CLI is disabled in gen32. Use the documented gen32 "
          "tests, isolated builder, parity gate and development replay.", file=sys.stderr)
    return 2


def historical_main():
    harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--force", nargs="*", default=[])
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--only-exact", action="store_true",
                    help="--only 를 글자 그대로 - 무효한 상류를 먼저 안 돌린다 "
                         "(디버깅용. 이 실행 결과는 done 으로 기록되지 않는다)")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--keep-going", action="store_true",
                    help="단계가 실패해도 다음으로 넘어간다")
    a = ap.parse_args()

    stages = build_stages()
    by_id = {s.id: s for s in stages}

    if a.only is not None and not a.only:
        print("--only 를 값 없이 줬다. 돌릴 단계를 적어야 한다: "
              "python experiments/loop2.py --only p1 p2")
        print("(전부 돌릴 거면 --only 를 빼고 --loop 를 쓴다. 있는 단계: %s)"
              % ", ".join(s.id for s in stages))
        return 2

    unknown = [x for x in list(a.only or []) + list(a.force)
               if x not in by_id]
    if unknown:
        print("모르는 단계: %s" % ", ".join(unknown))
        print("있는 단계: %s" % ", ".join(s.id for s in stages))
        return 2

    if a.only and a.force:
        print("--only 와 --force 는 같이 못 쓴다 (--only 분기는 force 를 "
              "조용히 버린다). 강제로 다시 돌릴 거면 --force 만 쓴다: "
              "python experiments/loop2.py --force %s" % " ".join(a.force))
        return 2

    if a.only_exact and not a.only:
        print("--only-exact 는 --only 와 함께만 쓴다 (--only 의 해석 방식을 "
              "바꾸는 수식어라 혼자서는 아무 뜻이 없다).")
        return 2

    if _PARSE_FAILED:
        print("⚠ import 훑기 실패(하류 의존이 지문에서 빠진다): %s"
              % ", ".join(_PARSE_FAILED))

    if a.reset:
        atomic_write_json(STATE, {"stages": {}, "history": []})
        print("상태 초기화 완료 (결과 파일은 그대로)")
        return 0

    st = load_state()
    if a.status:
        show_status(stages, st)
        return 0

    if a.only:
        want = list(a.only)
        pre = [sid for sid in dep_closure(stages, want, hard_only=True)
               if sid not in want
               and stage_status(by_id[sid], st)[0] != "done"]
        if a.only_exact:
            order = want
            if pre:
                print("⚠ --only-exact: 무효한 상류 %s 를 건너뛴다. "
                      "이 실행의 결과는 done 으로 기록되지 않는다." % ", ".join(pre))
        else:
            todo = set(pre) | set(want)
            order = [s.id for s in stages if s.id in todo]
            if pre:
                print("무효한 상류를 함께 돌린다: %s" % ", ".join(pre))
    else:
        order = resolve(stages, st, a.force)
    if not order:
        show_status(stages, st)
        return 0

    print("실행할 단계: %s" % ", ".join(order))
    skipped = []
    failed = []
    for sid in order:
        s = by_id[sid]
        print()
        print("=" * 94)
        print("[%s] %s" % (s.id, s.title))
        if s.note:
            print("     %s" % s.note)
        print("=" * 94)
        sys.stdout.flush()

        st = load_state()
        blocked = [] if a.only_exact else stale_upstream(stages, st, s.id)
        if blocked:
            print("건너뜀 - 상류가 무효라 이 단계의 결과는 근거가 없다: %s"
                  % ", ".join(blocked))
            skipped.append(s.id)
            sys.stdout.flush()
            continue

        run_provenance = s.provenance()
        run_fingerprint = fingerprint_from_provenance(run_provenance)
        before_outputs = s.observe_outputs()
        started_ns = time.time_ns()
        ok, err, dt, out, log = run_stage(s)
        source_consistent = s.provenance() == run_provenance
        published = result_provenance(s, before_outputs, started_ns, source_consistent)
        if not source_consistent:
            ok, err = False, "실행 중 소스 또는 환경이 바뀜"
        if not ok:
            failed.append(s.id)
        tail = "\n".join(out.strip().splitlines()[-25:])
        if tail:
            print(tail)
        st = load_state()
        bad = stale_upstream(stages, st, s.id) if ok else []
        status = "done" if ok else "failed"
        if bad:
            status = "stale_deps"
            err = "상류 무효: " + ", ".join(bad)
        st["stages"][s.id] = {
            "status": status,
            "fingerprint": run_fingerprint,
            "provenance": run_provenance,
            "result_provenance": published,
            "output_hashes": s.output_hashes() if ok else {},
            "finished": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "seconds": round(dt, 1), "error": err, "log": log,
        }
        st["history"].append({"stage": s.id, "ok": ok, "status": status,
                              "at": st["stages"][s.id]["finished"],
                              "seconds": round(dt, 1),
                              "stale_deps": bad})
        atomic_write_json(STATE, st)
        mark = {"done": "완료", "failed": "실패",
                "stale_deps": "완료(무효)"}[status]
        print("-> %s (%.1f초)%s  로그: %s"
              % (mark, dt, "" if ok and not bad else " " + err, log))
        if bad:
            print("   ↑ 돌긴 돌았지만 상류가 무효라 done 으로 기록하지 않았다. "
                  "다음 실행에서 상류부터 다시 돈다.")
        if not ok and not a.keep_going:
            print()
            print("여기서 멈춘다. 고친 뒤 같은 명령을 다시 실행하면 "
                  "이 단계부터 이어서 간다.")
            return 1
    print()
    if skipped:
        print("상류가 무효라 건너뛴 단계: %s" % ", ".join(skipped))
        print("(상태는 안 건드렸다. 상류를 되돌리면 그대로 이어서 돈다.)")
        show_status(stages, load_state())
        print("-> exit 3 (건너뛴 단계가 있다 - 이 실행은 완전한 한 바퀴가 아니다)")
        return 3
    show_status(stages, load_state())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
