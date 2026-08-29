# -*- coding: utf-8 -*-
"""PAD-FEC 연구 루프 (2차) - 중단해도 이어서 돌릴 수 있는 단계 실행기.

1차 pipeline.py 의 재개 방식을 그대로 가져오되, 단계를 새 연구 방향
(인수인계 문서 2026-08-18)에 맞춰 다시 짰다.

재개가 되는 이유
  각 단계는 상태와 **지문**을 experiments/state/loop2.json 에 남긴다.
  지문 = 실행기 + 명령줄 + 그 단계가 의존한다고 선언한 모든 소스 파일의
  SHA256. 그래서
    - 중간에 죽어도 done 인 단계는 건너뛴다
    - 알고리즘이나 측정 코드를 고치면 지문이 바뀌어 그 단계와 **하류 단계가
      전부** 다시 돈다 (1차에서 afec/ 를 고쳤는데 단계가 done 으로 남아
      옛 결과가 살아남은 사고가 있었다. 그래서 코드 해시를 지문에 섞는다)
    - 산출물 파일이 사라져도 stale 로 잡힌다

🩸 2026-08-20 감사 - 위 문단이 **거짓이었다**. 세 군데가 새고 있었다.
   1. 지문 밖의 소스: BED 에 qamp.go 만 있어서 policy.go / pfail_table.go /
      padfec/table.py 를 고쳐도 build 가 done 으로 남고 옛 바이너리 결과가
      살아남았다. -> 이제 quicbed/*.go 를 전부 훑고 table.py 를 ALGO 에 넣는다.
      🩸 1-(b) 2026-08-20 2차 감사. 위 조치는 padfec/*.py 와 quicbed/*.go 만
      막았고 **experiments/*.py 보조 모듈은 여전히 손으로 적고 있었다.**
      그래서 두 개가 빠져 있었다 - `_journal.py`(p1·p2·p3·p8·p9·p11·p12 가
      전부 `from _journal import Journal, code_fingerprint`. 단위 재사용
      판정과 code_fingerprint() 자체가 여기 있어서, 고치면 재사용 여부가
      통째로 바뀐다) 와 `e4_quic_decrypt.py`(p0·p1 이 `import
      e4_quic_decrypt as E4` 로 첫 비행 바이트와 C 를 직접 산출한다.
      명세 1절의 'B = k·W 실측'이 바로 이 코드의 출력이다).
      -> 목록에 둘을 더하는 것으로는 같은 사고가 또 난다. **각 진입
      스크립트의 import 를 `ast` 로 정적으로 훑어**(deps_py) experiments/
      안의 모듈을 전이적으로 자동 수집한다. 사람이 두 곳을 같이 고쳐야
      하는 구조를 없애는 것이 요점이다.
   2. --only 가 resolve() 를 통째로 건너뛰어, 상류가 무효여도 그냥 돌고
      **현재 지문으로 done 을 찍었다**. 빌드를 안 했는데 새 지문이 박히니
      "고치면 하류가 무효" 라는 전제 자체가 거짓이 됐다.
      -> --only 도 무효한 상류를 먼저 돌리고, 상류가 여전히 무효인 단계는
         아예 건너뛰며(결과 파일을 못 믿을 수로 덮어쓰지 않으려고),
         그래도 상류가 무효인 채로 돈 단계는 done 을 기록하지 않는다.
         자세한 이유는 main() 과 기록 지점의 주석에.
   3. p11(폐루프 후회) 이 어느 단계에도 없어서 루프 밖에 있었다. p12 도.

사용법
    python experiments/loop2.py --status      상태만 보기
    python experiments/loop2.py --loop        끝까지 (실패하면 멈춤)
    python experiments/loop2.py --force p3    특정 단계부터 다시
    python experiments/loop2.py --reset       상태 초기화 (결과 파일은 안 지움)

끝 코드
    0  전부 돌았다
    1  단계가 실패했고 --keep-going 이 없어서 멈췄다
    2  인자가 틀렸다 (모르는 단계 / --only 와 --force 같이 / --only-exact 혼자 /
       --only 를 값 없이)
    3  상류가 무효라 **건너뛴 단계가 있다** - 완전한 한 바퀴가 아니다.
       forever.py 가 이걸 보고 그 라운드를 표본에서 뺀다.
"""
from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(HERE, "state")
STATE = os.path.join(STATE_DIR, "loop2.json")
os.makedirs(STATE_DIR, exist_ok=True)

PY = sys.executable
# 문서 5절과 같은 형태: unshare -Urnm (=--user --map-root-user --net --mount)
UNSHARE = "cd /mnt/c/dev/pq_afec && unshare -Urnm python3 -u "

def _sources(subdir, suffix, core):
    """subdir 안의 suffix 파일을 전부 훑어 ROOT 기준 상대경로로 준다.

    하드코딩한 목록이 실제 소스와 어긋나는 것이 2026-08-20 감사에서 잡힌
    구멍 1 이었다. 사람이 두 곳(빌드 스크립트와 이 목록)을 같이 고쳐야 하는
    구조가 사고의 원인이므로, 목록을 사람 손에서 뗀다.

    지문이 **파일 목록 자체**에 의존하므로 반드시 정렬해서 결정론을 지킨다.
    core 는 훑기에 실패해도 반드시 들어간다 - 없으면 지문에 MISSING 으로
    남아 사라진 사실이 드러난다(조용히 지문이 약해지는 쪽이 더 위험하다).
    파일이 새로 생기거나 지워지면 목록이 바뀌어 지문도 바뀐다. 그것도 맞다.
    """
    found = []
    d = os.path.join(ROOT, *subdir.split("/"))
    try:
        for name in os.listdir(d):
            if name.endswith(suffix):
                found.append(subdir + "/" + name)
    except OSError:
        pass
    return sorted(set(found) | set(core))


# 훑기 자체가 실패한 파일. 조용히 넘기면 지문이 소리 없이 약해지므로 남긴다.
_PARSE_FAILED = []


def _module_rel(name):
    """모듈 이름 -> experiments/ 안의 .py 상대경로. 바깥 모듈이면 None.

    `from padfec import amplif` 의 padfec 처럼 experiments/ 밖의 것은 여기서
    걸러지고(ALGO 가 따로 담당한다), `import padbed as B` 나
    `from _journal import Journal` 처럼 experiments/ 안의 것만 남는다.
    """
    if not name:
        return None
    top = name.split(".")[0]
    rel = "experiments/" + top + ".py"
    if os.path.exists(os.path.join(ROOT, *rel.split("/"))):
        return rel
    return None


def _imports_of(rel):
    """rel 이 import 하는 모듈 이름 집합. 못 읽거나 못 파싱하면 None.

    ast 로 훑는 이유: 정규식으로 긁으면 p5_audit.py 처럼 Go 소스를 문자열로
    품은 파일에서 `import (` 를 import 문으로 오인한다. 반대로 함수 안의
    지연 import 는 놓친다. ast 는 둘 다 정확하다(표준 라이브러리다).
    ast.walk 이므로 최상위뿐 아니라 함수 안의 import 도 잡는다 - 지문은
    넓게 잡아 헛돌리는 쪽이 좁게 잡아 옛 결과를 살려 두는 쪽보다 안전하다.
    """
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
            if node.level:        # 상대 import - experiments/ 밖을 못 가리킨다
                continue
            if node.module:
                names.add(node.module)
    return names


def deps_py(*entries):
    """진입 스크립트가 (전이적으로) 끌어오는 experiments/*.py 를 전부 준다.

    🩸 구멍 1-(b) (2026-08-20 2차 감사). 보조 모듈 목록을 손으로 적고 있어서
       `_journal.py` 와 `e4_quic_decrypt.py` 가 지문에서 빠져 있었다. 둘 다
       측정의 뿌리다 - 전자는 단위 재사용 판정, 후자는 첫 비행 바이트 산출.
       고쳐도 단계가 done 으로 남아 옛 결과가 살아남는 구조였다.

       목록을 늘리는 대신 **읽어서 만든다.** p12 가 p2_threshold 를 가져다
       쓰듯 새 의존이 생겨도, import 만 쓰면 지문이 저절로 따라온다.

    전이적으로 따라가는 이유: p12 -> p2_threshold -> _journal 처럼 두 단계
    건너에 있는 모듈이 실제로 결과를 좌우한다. 직접 import 만 보면 그게 샌다.

    지문이 **파일 목록 자체**에 의존하므로 정렬해서 결정론을 지킨다.
    파일이 없으면 목록에는 남고 fingerprint() 가 MISSING 으로 찍는다 -
    조용히 사라지는 것보다 낫다(p13~p15 가 지금 그 상태다).
    """
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
            # 파일이 아예 없으면 fingerprint() 가 MISSING 으로 이미 드러낸다.
            # 있는데 못 파싱한 경우만 따로 표시한다 - 그때는 하류 의존이
            # 통째로 사라지므로 지문이 소리 없이 약해진다.
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


# padfec/*.py 전부. 🩸 table.py 는 experiments/quicbed/pfail_table.go 의
# **생성기**라 고치면 Go 가 조회하는 실패확률표가 통째로 바뀌는데도 감사
# 전까지 빠져 있었다. 새 모듈(quantum.py 처럼)이 생겨도 자동으로 잡히게 훑는다.
# 🩸 2026-08-29 - **`afec/` 가 빠져 있었다.** `padfec/policy.py` 는
#    `from afec.channel import GilbertElliott` 로 **손실 모형의 심장**을
#    가져다 쓰고(`padfec/codec.py` 는 `afec.rs` 의 GF(256) Cauchy RS 를
#    쓴다), 그런데도 지문에 없어서 **afec/ 를 고쳐도 모든 단계가 done 으로
#    남았다.** table.py 가 2026-08-25 감사 전까지 빠져 있던 것과 **같은 형태**
#    의 구멍이다 - "이 파일을 고치면 결과가 바뀌는가"가 판단 기준이어야 하고,
#    afec/channel.py 는 P_fail 전체를 좌우한다.
#    (2026-08-21 의 for_prior 경계 수정이 바로 이 파일에서 일어났다. 그때
#     지문이 안 바뀌었으니 그 회차 측정은 옛 채널로 잰 것이 섞여 있었을 수 있다.)
ALGO = _sources("padfec", ".py",
                ["padfec/__init__.py", "padfec/capacity.py",
                 "padfec/codec.py", "padfec/amplif.py", "padfec/policy.py",
                 "padfec/table.py"]) + _sources(
                     "afec", ".py",
                     ["afec/__init__.py", "afec/channel.py", "afec/rs.py"])


def _quicbed_go_sources():
    """qamp 바이너리에 컴파일돼 들어가는 .go 를 하나도 빠뜨리지 않기 위한 목록.

    build.sh 는 qamp.go / policy.go / pfail_table.go 를 **한 디렉터리
    (cmd/qamp)** 로 복사해 하나의 바이너리로 링크한다. 그런데 BED 에는
    qamp.go 만 있었다. 그래서 policy.go 나 pfail_table.go 를 고쳐도
    build 단계의 지문이 안 바뀌었고, build 는 done 으로 남았고, 측정은
    **옛 바이너리**로 돌았다. 1차에서 afec/ 를 고쳤을 때와 똑같은 사고다.

    하드코딩 대신 디렉터리를 훑는다 - 새 .go 가 build.sh 에 추가돼도 자동으로
    잡히기 때문이다(사람이 두 곳을 같이 고쳐야 하는 구조가 애초에 사고의
    원인이었다). 지문이 **파일 목록 자체**에 의존하므로 반드시 정렬해서
    결정론을 지킨다. 파일이 지워지면 목록이 줄어 지문이 바뀐다 - 그것도 맞다.
    """
    return _sources("experiments/quicbed", ".go",
                    ["experiments/quicbed/qamp.go",         # cmd/qamp/main.go
                     "experiments/quicbed/policy.go",       # cmd/qamp/policy.go
                     "experiments/quicbed/pfail_table.go"]) # cmd/qamp/pfail_table.go


BED = sorted(set(["experiments/padbed.py", "experiments/quicbed/build.sh"]
                 + _quicbed_go_sources()))


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


class Stage(object):
    def __init__(self, sid, title, runner, cmd, outputs, scripts, deps=(),
                 timeout=7200, note="", soft_deps=()):
        self.id = sid
        self.title = title
        self.runner = runner      # win | wsl | wsl-unshare
        self.cmd = cmd
        self.outputs = list(outputs)
        # BED / ALGO / deps_py() 가 겹치면 같은 파일이 두 번 들어온다. 중복이
        # 지문을 바꾸지는 않아야 하므로(같은 내용인데 해시가 달라지면 "코드가
        # 바뀜"이 거짓으로 뜬다) 여기서 한 번만 남긴다.
        self.scripts = sorted(set(scripts))
        # 🩸 2026-08-27 - `soft_deps` 는 **순서와 무효화에는 쓰되 막지는
        #    않는** 의존이다. deps 에 그대로 합치므로 지문·위상·무효 전이는
        #    한 글자도 안 바뀌고, 오직 `stale_upstream`(= 건너뛸지)만
        #    이것들을 빼고 본다.
        #
        #    왜 필요한가: **진단 단계는 상류가 붉을 때 가장 값이 크다.**
        #    p20(잔차 해부)이 p15~p18 의 원자료를 읽는데, 그 넷 중 하나라도
        #    실패하면 p20 이 건너뛰어진다 - 정확히 「왜 실패했는지 알고 싶은
        #    순간에 진단기가 안 도는」 구조다. 이 저장소가 2026-08-25 에 p19,
        #    08-26 에 p17 에서 겪은 「영원히 안 도는 단계」와 같은 형태다.
        #
        #    ⚠️ 이것은 「할 일 목록」 4-2(판정 로직 근본 수리)가 **아니다.**
        #    실패를 어떻게 판정하는지는 손대지 않았다. 단계가 스스로
        #    "나는 진단기다" 라고 밝혔을 때만 막지 않는 **옵트인**이라,
        #    이 표를 안 쓴 단계의 거동은 그대로다. 근본 수리(산출물 기준으로
        #    하류를 깨우기)는 여전히 남아 있다.
        self.soft_deps = list(soft_deps)
        self.deps = sorted(set(list(deps) + list(soft_deps)))
        self.timeout = timeout
        self.note = note

    def fingerprint(self):
        h = hashlib.sha256()
        h.update(self.runner.encode())
        h.update(json.dumps(self.cmd, ensure_ascii=False).encode())
        # 🩸 2026-08-20 2차 감사. deps 와 outputs 가 지문 밖에 있었다. 그래서
        #    **의존 그래프를 고쳐도 아무 단계도 무효가 되지 않았다** - 예컨대
        #    p4 의 deps 에서 p3 를 빼거나 p6 가 보는 산출물을 바꿔도 done 이
        #    그대로 남아, 새 그래프로는 한 번도 안 돌아 본 결과가 최신으로
        #    통했다. 실행기·명령줄과 똑같이 지문에 섞는다.
        h.update(json.dumps(sorted(self.deps), ensure_ascii=False).encode())
        h.update(json.dumps(sorted(self.outputs), ensure_ascii=False).encode())
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


def _cheap_first(stages, cheap=("p4", "p5")):
    """의존 순서를 지키면서 **측정을 안 하는 싼 단계**를 앞으로 당긴다.

    🩸 2026-08-21 - 2 차 실행에서 p4 가 `KeyError` 로 **0.2 초 만에**
    죽었다. 그런데 그 사실은 p10·p11·p12 를 다 돌린 **약 25 분 뒤**에야
    보였다. p4·p5 는 새로 측정하지 않고 앞 단계 결과만 읽으므로 상류가
    준비되는 즉시 돌 수 있다. 알고리즘을 고쳤을 때 그것이 실제로
    **돌아가기는 하는지**를 먼저 알아야 나머지 측정이 의미가 있다.

    의존은 그대로 지킨다 - 상류가 안 끝난 단계는 안 당겨진다.
    당길 자리가 없으면 원래 순서 그대로 뒤에 남는다.
    """
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

    # 🩸 순서 주의: 빌드가 먼저다. WSL 세션이 내려가면 /tmp 가 비므로
    # gate 가 /tmp/qamp 를 먼저 찾으면 "No such file" 로 죽는다.
    # 🩸 2026-08-21 - build.sh 는 Go 만 빌드한다. `pfail_table.go` 는
    #    `padfec/table.py` 의 **생성물**이라, policy.py 의 상수나
    #    table.py 를 고치고 사람이 `python -m padfec.table` 을 잊으면
    #    Go 가 옛 확률표로 돈다. 지금은 관문 격자 대조가 그걸 잡지만
    #    그건 **결과로 잡는 것**이지 원인을 막는 것이 아니다.
    #    표 생성을 단계로 만들어 순서를 루프가 보장하게 한다.
    #    (ALGO 가 안 바뀌면 생성물이 바이트 동일이라 build 는 재실행
    #     되지 않는다 - 헛돌지 않는다.)
    # 🩸 2026-08-21 - **파싱조차 안 되는 파일이 4 개 있었다.**
    #    넷 다 `os.path.join(...)` 의 닫는 괄호가 잘려 나간 것이고,
    #    그중 하나(_probe_trecover.py)는 비용식이 쓰는 상수
    #    T_recover = 200.86 ms 를 만든 탐침이다. 루프에 없는 파일이라
    #    **아무도 안 봤다** - 값은 명세에 남았는데 근거를 다시 밟을
    #    길이 끊겨 있었다.
    #    1 초짜리 검사로 이 부류를 통째로 막는다. 맨 앞에 둔다 -
    #    코드가 파싱도 안 되는데 측정을 40 분 돌릴 이유가 없다.
    #    지문이 **전 소스**라, 어떤 파일이 깨져도 다음 실행에서 드러난다.
    S.append(Stage(
        "lint", "모든 .py 가 파싱되는가 (루프 밖 파일까지)",
        "win", [PY, "-m", "compileall", "-q", "-x", "_build",
                "experiments", "padfec"],
        outputs=[], scripts=sorted(set(_sources("padfec", ".py", [])
                                      + _sources("experiments", ".py",
                                                 []))),
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
        "wsl", "bash /mnt/c/dev/pq_afec/experiments/quicbed/build.sh",
        outputs=[], scripts=BED, deps=["table"], timeout=900))

    # 🩸 2026-08-20 v2 이식 마무리. 관문이 부호(rsEncode/recoverOne)만 봤다.
    #    그런데 `-fec auto` 의 **결정**은 Go 안에서 나고 검증·보고·모형 탐색은
    #    Python padfec.policy 로 한다. 둘이 갈라지면 우리가 검증한 것과 실제로
    #    도는 것이 다른 물건이 되는데, 그걸 재는 자가 관문에 없었다.
    #    이 연구에서 이미 두 번 갈라졌다(1차 Cauchy 행렬, 2차 버스트 리터럴).
    #    격자 대조를 여기 붙인다 - 5,670 점에 0.6 초라 관문 비용이 사실상 0 이다.
    S.append(Stage(
        "gate", "관문 - 부호 자체시험 (Go) + 기준 구현 시험 (Python) "
                "+ 정책 격자 대조",
        "wsl",
        "cd /mnt/c/dev/pq_afec && "
        "[ -x /tmp/qamp ] || cp \"$HOME/quicbed/bin/qamp\" /tmp/qamp; "
        "/tmp/qamp -mode selftest && "
        "python3 -u experiments/gate_go_parity.py",
        outputs=["experiments/results/gate_go_parity.json"],
        scripts=BED + ALGO + deps_py("gate_go_parity.py"),
        deps=["build"], timeout=600,
        note="여기서 실패하면 아래 모든 측정의 근거가 없다"))

    S.append(Stage(
        "p0", "환경 확인 (문서 단계 0) + ML-KEM 동일성 (OpenSSL 3.5 상호운용)",
        "wsl-unshare", UNSHARE + "experiments/p0_env.py",
        outputs=["experiments/results/p0_env.json"],
        # deps_py 가 p0_env.py -> padbed.py, e4_quic_decrypt.py 를 자동으로
        # 끌어온다. .go/.sh 는 파이썬 import 가 아니므로 여기 손으로 적는다.
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

    # 🩸 p11 은 2026-08-20 감사 전까지 **루프 밖**에 있었다 - build_stages() 에도
    #    forever.py 의 MEASURE 에도 없어서, 폐루프 후회는 손으로 한 번 돌린
    #    결과가 그대로 인용되고 있었다. 기준은 **고치지 않는다** -
    #    이 프로젝트는 p8 에서 이미 기준을 갈아 통과 수를 바꾼 전례가 있고,
    #    그건 결과가 좋아진 게 아니라 자를 바꾼 것이었다. 실패한 채로 루프에
    #    넣고 --keep-going 으로 계속 돌린다. 실패 사실은 history 에 남는다.
    #
    #    ⚠️ 정정 (2026-08-26). 위에 "+4.919 ms > 2 ms 로 실패 중" 이라고
    #    적혀 있었다. **그 수는 결함이 아니라 판정불능의 자국이었다.**
    #    고정 비교팔이 m0..m2 뿐이라 정책이 실제로 고르는 m3 가 비교 집합에
    #    없었고, 그래서 없는 후회를 재고 있었다. 팔을 M_MAX_DEFAULT 에서
    #    파생하도록 고친 뒤 최악 후회는 **1.014 ms** 로 떨어졌고 이 검사는
    #    통과한다. 남은 실패는 신뢰반폭(표본 부족)뿐이다.
    #    옛 문장을 지우지 않고 남기는 이유: 이 수가 아래 p15 의 판단 근거로
    #    까지 번져 있었다. 틀린 수는 지워도 그 수를 인용한 곳에 살아남는다.
    S.append(Stage(
        "p11", "폐루프 후회 - auto 가 최선 고정 m 만큼 하는가",
        "wsl-unshare", UNSHARE + "experiments/p11_adaptive.py",
        outputs=["experiments/results/p11_adaptive.json"],
        scripts=ALGO + deps_py("p11_adaptive.py") + BED,
        deps=["p1"], timeout=21600,
        # 🩸 2026-08-26 - note 에서 **실측값을 뺐다.** "수렴 후 최악
        #    +1.014 ms" 를 박아 뒀는데 그 뒤 판이 +3.238 을 냈다. 즉 이
        #    줄은 단계 배너에 **현재처럼 찍히면서 실제 결과와 반대**를
        #    말하고 있었다("검사는 통과"). note 는 지문 밖이라 아무도
        #    무효화하지 않으므로 낡은 채 영원히 남는다. p18 의 관례대로
        #    **기준만** 적고 수는 결과에서 읽게 한다.
        note="후회는 두 값을 함께 본다(전 구간 / 수렴 후). 기준: 수렴 후 "
             "최악 후회 < 2 ms, 신뢰반폭 < 1 ms. 반폭이 안 내려가면 결함이 "
             "아니라 표본 부족이다(--precise 또는 PADFEC_P11_N)"))

    # p12 는 명세 8절의 헤드라인 검증(양자 경계 절벽, 1280 -> 1281 에서
    # 임계가 한 칸 ≈1,246 B 뛰는가)이다. 스크립트는 다른 사람이 만드는 중이라
    # 아직 없을 수 있다 - 그러면 지문에 MISSING 으로 남고 단계는 실패한다.
    # 그게 맞다. "없는 단계"보다 "실패한 단계"가 훨씬 잘 보인다.
    S.append(Stage(
        # 🩸 제목의 ips 목록이 실제와 달랐다. 1350 을 채운 뒤에도 **1450 이
        #    빠져 있었다** - 목록을 손으로 다시 적으면 또 어긋난다.
        #    p12_quantum.py 의
        #    MAIN_IPS = [1279, 1280, 1281, 1282, 1300, 1350, 1450] 이 정본이고,
        #    1350·1450 은 "1281 위쪽이 고원"이라는 검사에 실제로 들어가는 점이다.
        #    제목이 실험을 잘못 설명하면 --status 출력이 곧 거짓말이 된다.
        #    (제목은 show_status 가 [:56] 으로 자르므로 56 자 안에 넣는다 -
        #     잘리면 목록 끝의 1450 이 다시 안 보인다.)
        "p12", "양자 경계 절벽: ips 1279/1280/1281/1282/1300/1350/1450 "
               "임계 이분탐색",
        "wsl-unshare", UNSHARE + "experiments/p12_quantum.py",
        outputs=["experiments/results/p12_quantum.json"],
        # p12_quantum.py 는 p2_threshold.py 를 **모듈로 가져다 쓴다**
        # (이분탐색 루틴). 예전에는 그 사실을 손으로 적어야 했고, 그렇게
        # 적어도 p2 가 끌어오는 _journal.py 는 여전히 빠졌다. 이제 deps_py 가
        # p12 -> p2_threshold -> _journal 까지 전이적으로 훑는다.
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

    # 🩸 명세 8절의 p13·p14·p15 는 2026-08-20 2차 감사 전까지 **루프에 아예
    #    없었다**. 스크립트가 없다고 단계도 안 만들면, 안 한 검증이 목록에서
    #    통째로 사라져 "아직 안 했다"는 사실 자체가 안 보인다. 위 p12
    #    주석이 스스로 밝힌 논리를 그대로 적용한다 - **없는 단계보다 실패한
    #    단계가 훨씬 잘 보인다.** 스크립트가 없으면 deps_py 목록에 남아
    #    fingerprint() 가 MISSING 을 찍고, 단계는 매번 실패로 드러난다.
    #    특히 p13 은 명세 2.6 이 "반드시 직접 측정으로 확인해야 한다"고
    #    못박은 항목이다. 그 전까지 B_eff 재해석은 사후 가설일 뿐이다.
    #
    # 🩸 그런데 처음 등록할 때 이 셋을 p4·p5·p6 **앞**에 끼워 넣었다. 이 목록의
    #    순서가 곧 실행 순서이고, 셋은 스크립트가 없어 **반드시 실패**하므로,
    #    --keep-going 없이 돌리면 p13 에서 멈춰 **p4·p5·p6 가 영영 안 돈다.**
    #    미작성 단계를 드러내려다 이미 되는 검증을 막는 것은 본말전도다.
    #    셋 다 deps 는 p1 뿐이라 순서를 뒤로 미뤄도 위상 정렬은 그대로다.
    #    -> 맨 뒤로 옮긴다.
    S.append(Stage(
        "p13", "B_eff 직접 측정 - 서버 첫 송신까지 도착한 클라 바이트 (명세 2.6)",
        "wsl-unshare", UNSHARE + "experiments/p13_beff.py",
        outputs=["experiments/results/p13_beff.json"],
        scripts=ALGO + deps_py("p13_beff.py") + BED,
        deps=["p1"], timeout=14400,
        # 🩸 2026-08-26 - "스크립트 미작성" 은 옛말이다(p13_beff.py 가 있고
        #    돌았다). 기준만 남긴다.
        note="명세 2.6 이 "
             "'반드시 직접 측정으로 확인해야 한다'고 한 항목. 통과 기준: "
             "x25519 on1 의 B_eff 가 (2560, 2986.7] 안"))

    S.append(Stage(
        "p14", "지배 보조정리 - 같은 Δ 에서 δ-패딩 팔 vs 패리티 팔",
        "wsl-unshare", UNSHARE + "experiments/p14_dominance.py",
        outputs=["experiments/results/p14_dominance.json"],
        scripts=ALGO + deps_py("p14_dominance.py") + BED,
        deps=["p1"], timeout=21600,
        # 🩸 2026-08-26 - "스크립트 미작성" 은 옛말이다(p14_dominance.py 가
        #    있고 돌았다). p13·p15 와 **같은 형태**로 세 번째다 - note 는
        #    지문 밖이라 아무도 무효화하지 않으니, 사실이 바뀌면 사람이
        #    지워야 한다. 기준만 남긴다.
        note="통과 기준: 신용은 같고(임계 동일) 손실에서 패리티만 꼬리를 "
             "없앤다. 부정 시험으로 δ 팔의 복구는 0 이어야 한다"))

    # 🆕 2026-08-21. J 의 t_tx 항이 쓰는 업링크 대역에 **출처를 만든다.**
    #    그전까지 10 Mbps 가 Python 기본 인자와 Go 리터럴에 각각 박혀 있었고
    #    어디서도 측정된 적이 없었다. 정작 이 테스트베드는 netem 이 대역을 안
    #    걸어 그 비용이 존재하지 않았는데, 그 항이 "이득이 같으면 큰 m 을
    #    고르는 편향"을 막는 유일한 힘이라 결정의 43% 를 좌우했다.
    #    p16 은 (a) 기본 환경에 대역 비용이 없음을 재고 (b) 대역을 실제로
    #    걸었을 때 모형의 t_tx 식이 맞는지 대조한다.
    S.append(Stage(
        "p16", "업링크 대역 실측 - J 의 t_tx 항에 출처를 만든다 (명세 3절)",
        "wsl-unshare", UNSHARE + "experiments/p16_uplink.py",
        outputs=["experiments/results/p16_uplink.json"],
        scripts=ALGO + deps_py("p16_uplink.py") + BED,
        deps=["p1"], timeout=3600,
        note="통과 기준: 무제한 조건은 팔별 Δ < 0.2 ms(대역 비용 없음), "
             "10 Mbps 조건은 임계경로 식이 팔별 0.25 ms 안. 부정 시험으로 "
             "옛 식(추가 바이트 전부)이 0.5 ms 넘게 어긋나야 한다"))

    # 🩸 2026-08-23 신설. p11·p15 는 손실률을 **고정**해 두고 auto 와 최선
    #    고정팔을 비교한다 - 그러면 최선 고정팔이 늘 존재하므로 적응은
    #    따라잡을 수 있을 뿐 **이길 수 없다.** 6 회 실행 동안 "적응이
    #    필요한가"에 답할 수 없는 구조였는데 아무도 묻지 않았다(후회가 늘
    #    >= 0 이라는 사실 자체가 단서였다).
    #    p17 은 손실률이 **변하는** 시나리오 + 대역 제한(패리티가 공짜가
    #    아닌 조건)에서 적응의 값어치를 잰다. 판정은 시간이 아니라
    #    **선택**으로 한다 - 시간으로 재려면 팔당 46,398 연결이 필요하다.
    S.append(Stage(
        "p17", "적응의 값어치 - 손실률이 변할 때 정책이 따라가는가",
        "wsl-unshare", UNSHARE + "experiments/p17_adaptive_value.py",
        outputs=["experiments/results/p17_adaptive_value.json"],
        scripts=ALGO + deps_py("p17_adaptive_value.py") + BED,
        # 🩸 2026-08-26 - deps 를 ["p16"] -> ["p1"] 로 고쳤다. **p17 은 p16 의
        #    결과 파일을 읽지 않는다**(`grep p16_uplink p17_adaptive_value.py`
        #    → 0 건). 머리말이 "p16 이 잰 그 사실이 여기서 실험 설계로 돌아온다"
        #    라고 적은 것을 의존으로 옮겨 적은 것인데, 그건 **사람이 읽는 근거**
        #    이지 자료 흐름이 아니다.
        #
        #    대가가 실제로 났다: p16 은 0.25 ms 짜리 자로 판정하는데 자기 블록
        #    표류가 0.694 ms 라 **판정 불능으로 늘 붉어진다.** 그 붉은색이
        #    "상류 무효"로 번져 **30 분짜리 p17 실측이 통째로 건너뛰어졌다**
        #    (2026-08-26 22:34). p19 가 2026-08-25 에 겪은 「영원히 안 도는
        #    단계」와 같은 형태다 - 거기서 배운 처방("읽지 않는 것을 의존에
        #    넣지 마라")을 여기에도 적용한다.
        #
        #    형제 단계(p13·p14·p15·p18)가 전부 ["p1"] 이다. 같은 꼴로 맞춘다.
        # 🩸 2026-08-28 - 시간초과를 7200 -> 21600 으로 올렸다. **조건을 2 개
        #    에서 4 개로 늘렸기 때문**이다(큰cert 16000 · RTT200 추가 -
        #    근거는 p17_adaptive_value.py 의 CONDS 주석). 산수:
        #      옛 실측  조건 2 개 · N=150 -> 25 분 (2026-08-25 mtime 차)
        #      연결당 비용(핸드셰이크+gap) 2Mbps 102ms · 무제한 60ms
        #                                 큰cert 152ms · RTT200 252ms
        #      새 정밀도 N=450 -> 25 x (566/162) x 3 = 약 262 분 = 4.4 시간
        #    2 시간 자로는 **반드시 잘린다.** 6 시간이면 여유가 있다.
        #    시간초과는 목표가 아니라 안전망이므로 넉넉히 둔다 - 잘린 실측은
        #    표본부족이 아니라 **없는 것**이고, 그 사실이 로그에서 "시간초과"
        #    한 줄로만 남으면 원인까지 가는 데 또 한 바퀴가 든다.
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
        # ⚠️ 정정 (2026-08-26). 옛 note 는 "스크립트 미작성"이라고 적고 있었고
        # p11 의 4.919 ms 를 기준 유지의 근거로 인용했다. 둘 다 사실이 아니다 -
        # 스크립트는 있고(11 검사 중 10 통과), 4.919 는 판정불능의 자국이었다.
        # 기준을 완화하지 않는 이유는 그대로다: 자를 바꾸는 것은 결과를 바꾸는
        # 것이 아니라 결과를 못 보게 만드는 것이다.
        # 🩸 2026-08-26 - p11 과 같은 이유로 실측값을 뺐다.
        note="δ·m 결합 정책의 후회. 기준: 수렴 후 최악 후회 < 2 ms, "
             "신뢰반폭 < 1 ms. 반폭이 안 내려가면 표본 부족이다"
             "(--precise 또는 PADFEC_P15_N)"))

    # 🩸 2026-08-25 - p18 은 지금까지 **손으로만 돌아서** 지속 검증에 한 번도
    #    안 들어갔다. 등록 안 된 단계는 다시 재지 않는 단계다. 지금은
    #    검사 4·5·6 이 판정 불능으로 실패하는데, 그게 사실이므로 실패한
    #    채로 등록한다 - 통과시키려고 기준을 낮추지 않는다.
    S.append(Stage(
        "p18", "m_max 상한 - 고정팔 m=1..4 를 직접 재서 모형을 검증",
        "wsl-unshare", UNSHARE + "experiments/p18_mmax.py",
        outputs=["experiments/results/p18_mmax.json"],
        scripts=ALGO + deps_py("p18_mmax.py") + BED,
        deps=["p1"], timeout=21600,
        note="결정적 자리(cert 16,000·무손실 - m_max=2 정책이 포기하는 "
             "자리)는 작은 표본으로 판정되고, 손실 자리는 필요 표본이 "
             "커서 판정 불능으로 남을 수 있다"))

    # 🩸 2026-08-27 신설 - **잔차 해부.** 이 루프의 눈이 「검사가 붉다/푸르다」
    #    하나뿐이라, 붉어졌을 때 (a) 모형의 값이 틀렸다 (b) 모형의 선택이
    #    틀렸다 (c) 못 쟀다 가 구분되지 않았다. p20 은 새 실측을 하지 않고
    #    **이미 있는 원자료를 다시 읽어** 모형과 측정을 무리(1-RTT / 한 판 더 /
    #    시간초과)별로 갈라 대조하고, 팔쌍마다 필요 표본을 낸다.
    #    Windows 에서 몇 초에 돌고 root 도 WSL 도 필요 없다.
    #    deps 는 **읽는 것만** 적는다(p17 의 사고 이후 규칙).
    S.append(Stage(
        "p20", "잔차 해부 - 모형이 어느 무리에서 틀리는가 + 필요 표본",
        "win", [PY, "experiments/p20_residual.py"],
        outputs=["experiments/results/p20_residual.json"],
        scripts=ALGO + deps_py("p20_residual.py"),
        # p1 만 진짜 의존이다(실측 C 를 읽는다). 나머지 넷은 **원자료를
        # 읽지만 막지는 않는다** - 그것들이 붉을 때가 이 진단기가 가장
        # 필요한 순간이기 때문이다. soft_deps 는 순서와 무효화에는 그대로
        # 쓰이므로 p15~p18 이 다시 돌면 p20 도 다시 돈다.
        deps=["p1"], soft_deps=["p15", "p16", "p17", "p18"],
        timeout=900,
        note="새 실측을 하지 않는다. 어긋난 자리를 이름 붙여 세는 것이 일이고, "
             "고칠지 더 잴지는 사람이 정한다"))

    # 🩸 2026-08-26 - **p6 를 여기로 옮겼다** (그전 자리: p5 바로 뒤, p13 앞).
    #    `_cheap_first` 는 위상 정렬이 아니라 "싼 단계를 앞으로 당기는" 재배치라
    #    p6 처럼 cheap 이 아닌 단계는 **선언 순서대로** 돈다. 즉 deps 에 p17 을
    #    적어도 실행 순서는 안 바뀐다 - p6 가 p17 보다 먼저 돌아 **옛 p17 을
    #    읽고 done 이 되고**, 다음 바퀴엔 둘 다 done 이라 아무도 안 돈다.
    #    그러면 보고서가 옛 수치를 인용한 채 영원히 초록이다(2026-08-21 이
    #    p11·p12 에서 겪은 사고와 같은 형태, 이번엔 순서 쪽).
    #    deps 를 고치는 것만으로는 부족하고 **선언 위치도 같이** 옮겨야 한다.
    #    보고서는 모든 측정 뒤에 나오는 것이 맞으므로 p18 뒤가 제자리다.
    #    (p19 보다는 앞이어야 한다 - p19 가 보고된 수치를 원자료와 대조한다.)
    S.append(Stage(
        "p6", "보고서 + 바탕화면 한 장 요약",
        "win", [PY, "experiments/p6_report.py"],
        outputs=["docs/PADFEC 실측 보고서.md"],
        scripts=ALGO + deps_py("p6_report.py"),
        # 🩸 2026-08-21 - p6_report.py 는 p11_adaptive.json 과
        #    p12_quantum.json 을 **읽는데** deps 에 없었다. 그래서 그
        #    둘이 갱신돼도 보고서가 무효화되지 않고 옛 수치를 인용한
        #    채 남는다. 읽는 것을 전부 적는다.
        # 🩸 2026-08-26 - **p17 을 더했다.** 보고서가 p17 을 두 군데서 읽기
        #    시작했다: 9 장(오라클 이득 = 적응이 벌 수 있는 것)과 한계 절의
        #    자리 효과.
        #    (p13·p14·p15·p16·p18 은 아직 보고서가 읽지 않는다 - 읽지 않는
        #     것을 deps 에 넣으면 순서만 묶이고 사실과 어긋난다. 보고서에
        #     넣는 것은 별개 작업으로 남긴다.)
        deps=["p1", "p2", "p3", "p4", "p5", "p7", "p8", "p9", "p10",
              "p11", "p12", "p17"],
        timeout=1800))

    # 🩸 2026-08-24 신설. 이 저장소는 "측정이 잘 돌았는가"는 여러 자로 보는데
    #    **보고된 요약 수치가 그 측정의 원자료와 맞는지**를 보는 자가 없었다.
    #    그 틈에서 생길 수 있는 일: 요약만 갱신되고 원자료는 옛것, 상수가
    #    "측정값" 필드에 들어감, 결과가 소스 수정보다 먼저 만들어졌는데 최신으로
    #    인용됨, 판정 수치에 원자료가 없어 아무도 다시 셀 수 없음.
    #    p19 는 요약을 원자료에서 **다시 계산해 대조**한다(852 항목).
    #    음성 대조 확인: 수치 하나를 10% 조작하면 정확히 1 건을 잡는다.
    #    측정을 안 하므로 맨 뒤에 두고 win 러너로 돌린다(빠르다).
    S.append(Stage(
        "p19", "수치 출처 감사 - 보고된 수가 원자료에서 재계산되는가",
        "win", [PY, "experiments/p19_provenance.py"],
        outputs=["experiments/results/p19_provenance.json"],
        scripts=deps_py("p19_provenance.py"),
        # 🩸 2026-08-25 - deps 를 **비운다.** 처음엔 [p3,p11,p14,p15,p16] 로
        #    뒀는데, p11·p15 는 상시 N 에서 정밀도 검사 때문에 늘 실패하므로
        #    p19 가 매번 "상류 무효"로 건너뛰어졌다 — 즉 **영원히 안 도는
        #    단계**가 될 참이었다(라운드 10 에서 실제로 그랬다).
        #    p19 는 결과 파일의 수치가 원자료와 맞는지만 본다. 상류가
        #    실패했어도, 오히려 실패했을수록 검사할 가치가 있다. 실행 순서는
        #    목록에서 맨 뒤라는 것으로 이미 보장된다.
        deps=[], timeout=600,
        note="요약 수치를 원자료에서 재계산해 대조한다. 불일치 0 이어야 한다"))

    return _cheap_first(S)


# ---------------------------------------------------------------------- state
def atomic_write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


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
    if rec.get("status") != "done":
        return "pending", "지난번 %s" % rec.get("status", "?")
    if rec.get("fingerprint") != stage.fingerprint():
        return "stale", "코드가 바뀜"
    if not stage.outputs_present():
        return "stale", "산출물이 없어짐"
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
    """ids 가 (전이적으로) 의존하는 단계 전부. 자기 자신은 뺀다.

    직접 의존만 보면 안 되는 이유: 코드를 고쳐 p1 이 무효가 돼도 p2 의 지문은
    안 바뀌므로 p2 는 done 으로 남는다. 그 상태에서 p4(deps=p2,p3)만 보면
    "상류 멀쩡"으로 보인다. 무효는 전이한다.
    """
    by_id = {s.id: s for s in stages}
    seen, stack = set(), [i for i in ids]
    while stack:
        s = by_id.get(stack.pop())
        if not s:
            continue
        # hard_only - soft_deps 는 막는 판정에서 뺀다 (Stage.soft_deps 주석).
        soft = set(getattr(s, "soft_deps", ()))
        for d in s.deps:
            if hard_only and d in soft:
                continue
            if d not in seen:
                seen.add(d)
                stack.append(d)
    return [s.id for s in stages if s.id in seen]


def stale_upstream(stages, st, sid):
    """sid 의 상류 중 done 이 아닌 것 -> ["p1(stale)", ...]"""
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
    # 🩸 2026-08-28 - **WSL 단계에 환경변수가 안 넘어가고 있었다.**
    #    `wsl.exe` 는 부모의 환경을 그대로 물려주지 않는다. 넘길 이름을
    #    `WSLENV` 에 적어야만 건너간다. 그래서 문서(할 일 목록 1-2)가 적어 둔
    #        $env:PADFEC_P11_N=4000; python experiments/fixloop.py --detach
    #    는 **정밀도 실행이 아니라 평범한 실행**이었다 - 측정 단계는 전부
    #    WSL 안에서 돌고, 거기서 os.environ.get("PADFEC_P11_N") 이 언제나
    #    None 이었기 때문이다. 확인:
    #        PADFEC_P11_N=4000 wsl -d Ubuntu -- bash -lc 'echo ${PADFEC_P11_N}'
    #          -> 빈 값
    #        WSLENV=PADFEC_P11_N PADFEC_P11_N=4000 wsl ... -> 4000
    #    이 저장소가 쓰는 이름을 전부 태워 보낸다. 없는 이름은 무시된다.
    _pass = [k for k in env if k.startswith("PADFEC_")]
    if _pass:
        prev = env.get("WSLENV", "")
        names = ":".join(sorted(_pass))
        env["WSLENV"] = (prev + ":" + names) if prev else names
    try:
        # 🩸 2026-08-26 - `encoding` 을 안 주면 text=True 가 **부모의 로캘**
        #    (이 기계는 cp949)로 자식 출력을 푼다. 자식은 PYTHONIOENCODING=utf-8
        #    로 UTF-8 을 뱉으므로 전부 U+FFFD 로 뭉개져 로그에 박히고, 원래
        #    바이트는 되돌릴 수 없다(errors="replace" 라 조용히 지나간다).
        #    그래서 log2_*.txt 가 통째로 읽을 수 없는 글자였다 - 실패한 검사가
        #    무엇인지 **사람도 자동 분류기도 못 읽는다.** 진단 기록이 없으면
        #    루프는 "실패했다"까지만 알고 "왜"를 못 말한다.
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=stage.timeout, env=env, **kw)
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        err = "" if ok else "exit %d" % p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (
            (e.stdout or b"").decode("utf-8", "replace"))
        ok, err = False, "timeout %ds" % stage.timeout
    dt = time.time() - t0
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
    harden()
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--force", nargs="*", default=[])
    # 🩸 default 는 [] 가 아니라 None 이다. 옛 코드는 `--only` 를 값 없이 줘도
    #    a.only == [] 이 되어 falsy 로 떨어졌고, 그러면 아래 `if a.only:` 분기를
    #    안 타고 **resolve() 로 가서 전체 파이프라인이 조용히 돌았다.**
    #    "하나만 돌리려다 전부 도는" 방향의 사고라 더 나쁘다 - 그 실행은 몇
    #    시간짜리이고, 사용자는 한 단계만 돌았다고 믿는다. None 이면 "안 줬다",
    #    [] 면 "줬는데 비었다"로 구분되어 아래에서 거절할 수 있다.
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

    # 🩸 값 없는 --only 는 "전부 돌려라"가 아니라 **인자 실수**다. 조용히
    #    전체를 도는 대신 거절한다. 정말 전부 돌릴 거면 --loop 를 쓴다.
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

    # 🩸 2026-08-20 2차 감사. `--only p2 --force p1` 은 force 가 **조용히
    #    무시됐다** - a.only 분기가 resolve() 를 아예 안 부르므로 a.force 는
    #    unknown 검사에만 쓰이고 버려졌다. "다시 돌렸다고 믿었는데 안 돌았다"는
    #    이 루프에서 가장 비싼 종류의 거짓말이므로(구멍 2 가 정확히 그거였다)
    #    조용히 합치지 말고 거절한다. 둘 다 필요하면 --force 만 쓰면 된다 -
    #    resolve() 가 강제 단계와 그 하류를 알아서 순서대로 늘어놓는다.
    if a.only and a.force:
        print("--only 와 --force 는 같이 못 쓴다 (--only 분기는 force 를 "
              "조용히 버린다). 강제로 다시 돌릴 거면 --force 만 쓴다: "
              "python experiments/loop2.py --force %s" % " ".join(a.force))
        return 2

    # --only-exact 는 --only 를 해석하는 방식을 바꾸는 수식어다. --only 없이
    # 주면 아무 일도 안 하면서 "글자 그대로 돌렸다"는 착각만 남긴다.
    if a.only_exact and not a.only:
        print("--only-exact 는 --only 와 함께만 쓴다 (--only 의 해석 방식을 "
              "바꾸는 수식어라 혼자서는 아무 뜻이 없다).")
        return 2

    if _PARSE_FAILED:
        # 지문 훑기가 깨진 채로 도는 것은 구멍 1 로 되돌아가는 것이다.
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
        # 🩸 구멍 2 (2026-08-20 감사). 옛 코드: `order = a.only` - 끝.
        #    forever.py 가 `--only <MEASURE>` 로 부르는데 build/gate 는 MEASURE 에
        #    없으므로, 상류가 아무리 무효여도 그냥 측정이 돌았다. 실제로 10 라운드
        #    내내 build 가 한 번도 안 돌았다(마지막 08-19 15:07).
        #
        #    두 선택지 중 **(a) 먼저 다시 돌린다** 를 골랐다. (b) 라운드 거부는
        #    밤새 도는 루프를 그냥 멈춰 세워 그 밤의 데이터가 통째로 없어지는데,
        #    무효한 상류를 되돌리는 비용(build+gate 는 1 분 남짓)이 라운드
        #    하나(수십 분~시간)보다 압도적으로 싸기 때문이다. 즉 거부해서 얻는
        #    안전을 훨씬 싼 값에 살 수 있다.
        want = list(a.only)
        # 2026-08-27 - `hard_only=True` 로 본다. 안 그러면 `--only p20` 이
        #    soft_deps(p15~p18)를 **선행 필수**로 끌고 와, 막지 않으려고
        #    만든 표가 손으로 돌릴 때만 다시 막는 꼴이 된다.
        #    stale_upstream 과 같은 규칙을 써야 한 가지로 말한다.
        pre = [sid for sid in dep_closure(stages, want, hard_only=True)
               if sid not in want
               and stage_status(by_id[sid], st)[0] != "done"]
        if a.only_exact:
            order = want
            if pre:
                print("⚠ --only-exact: 무효한 상류 %s 를 건너뛴다. "
                      "이 실행의 결과는 done 으로 기록되지 않는다." % ", ".join(pre))
        else:
            # 🩸 pre + want 로 그냥 앞에 붙이면 안 된다. want 안에도 서로
            #    의존하는 단계가 있어서(p2 는 p1 에 의존) 상류가 want 의 뒤쪽
            #    단계보다 먼저 와 버리면, 상류가 아직 pending 인 채로 실행
            #    시점이 와서 그 단계가 통째로 건너뛰어진다. build_stages() 의
            #    나열 순서가 이미 위상 정렬이므로 그 순서로 다시 늘어놓는다.
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
    for sid in order:
        s = by_id[sid]
        print()
        print("=" * 94)
        print("[%s] %s" % (s.id, s.title))
        if s.note:
            print("     %s" % s.note)
        print("=" * 94)
        sys.stdout.flush()

        # 상류가 무효인 채로 도는 것은 시간 낭비를 넘어 **해롭다**. 측정
        # 스크립트는 results/*.json 을 덮어쓰므로, 못 믿을 수가 산출물 자리에
        # 남고 forever.py 의 라운드 요약이 그걸 읽어 history 에 쌓는다.
        # 그래서 아예 건너뛴다. --keep-going 으로 계속 도는 것과 충돌하지
        # 않는다 - p11 처럼 **아무도 의존하지 않는** 단계가 실패해도 뒤는
        # 그대로 돈다. 막히는 건 정말로 그 결과에 기대는 단계뿐이다.
        # 상태는 **건드리지 않는다**. 지난 실행의 정당한 done 기록을 여기서
        # 덮어쓰면 그것대로 거짓말이 된다.
        st = load_state()
        blocked = [] if a.only_exact else stale_upstream(stages, st, s.id)
        if blocked:
            print("건너뜀 - 상류가 무효라 이 단계의 결과는 근거가 없다: %s"
                  % ", ".join(blocked))
            skipped.append(s.id)
            sys.stdout.flush()
            continue

        ok, err, dt, out, log = run_stage(s)
        tail = "\n".join(out.strip().splitlines()[-25:])
        if tail:
            print(tail)
        st = load_state()
        # 🩸 구멍 2-(b). 성공했어도 상류가 무효인 채로 나온 결과에 **현재
        #    지문으로** done 을 찍으면, "코드를 고치면 하류가 자동 무효" 라는
        #    이 루프의 존재 이유가 거짓이 된다 (빌드를 안 했는데 새 지문이
        #    박히므로, 다음 실행은 옛 바이너리 결과를 최신으로 믿는다).
        #    그래서 done 이 아니라 stale_deps 로 남긴다 - 결과 파일은 그대로
        #    두되 기록만 안 하므로, 다음 실행에서 상류부터 다시 돈다.
        #    (a) 를 켜 두면 여기 걸릴 일이 거의 없다. 걸리는 경우는 같은 실행
        #    안에서 상류가 --keep-going 으로 실패하고 지나간 때다.
        bad = stale_upstream(stages, st, s.id) if ok else []
        status = "done" if ok else "failed"
        if bad:
            status = "stale_deps"
            err = "상류 무효: " + ", ".join(bad)
        st["stages"][s.id] = {
            "status": status,
            "fingerprint": s.fingerprint(),
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
        # 🩸 2026-08-20 2차 감사 (중대 2). 건너뛴 단계가 있어도 0 을 돌려주니,
        #    forever.py 는 "정상 종료"로 읽고 그 라운드를 다른 라운드와 똑같이
        #    history 에 쌓았다. 건너뛴 단계의 results/*.json 은 **옛 파일**이라
        #    그 라운드는 독립 반복이 아니다. 실패(1)·인자오류(2)와 구분되는
        #    3 을 돌려줘서 부르는 쪽이 그 사실을 알 수 있게 한다.
        print("-> exit 3 (건너뛴 단계가 있다 - 이 실행은 완전한 한 바퀴가 아니다)")
        return 3
    show_status(stages, load_state())
    return 0


if __name__ == "__main__":
    sys.exit(main())
