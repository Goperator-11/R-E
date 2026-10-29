# -*- coding: utf-8 -*-
"""PAD-FEC 실측 하네스 - 네임스페이스, veth, netem, 서버/클라이언트 구동.

**인수인계 문서 5절의 검증된 구성을 글자 그대로 옮긴 것이다.**

    unshare -Urnm bash -c '
    mount -t tmpfs none /run 2>/dev/null; mkdir -p /run/netns
    ip netns add peer
    ip link add v0 type veth peer name v1
    ip link set v1 netns peer
    ip addr add 10.9.0.1/24 dev v0; ip link set v0 mtu 1500; ip link set v0 up
    ip netns exec peer sh -c "ip addr add 10.9.0.2/24 dev v1; ..."
    tc qdisc add dev v0 root netem delay 25ms loss 5%
    ip netns exec peer tc qdisc add dev v1 root netem delay 25ms loss 5%
    ip netns exec peer /tmp/qamp -mode server -addr 10.9.0.2:44433 ...
    timeout 300 /tmp/qamp -mode client -addr 10.9.0.2:44433 ...'

이름(peer, v0, v1), 주소(10.9.0.1/2), 포트(44433), 실행 경로(/tmp/qamp),
MTU(1500), netem 형태를 전부 문서와 같게 맞췄다. 심(shim) 프로세스는 없다 -
문서 3-3/3-4 가 지정한 대로 FEC 가 countConn 안에 들어갔기 때문이다.

문서 5절/6절의 함정을 그대로 반영했다.
  - loopback 은 MTU 변경을 조용히 무시한다 -> 반드시 veth 를 쓴다
  - veth 양끝을 서로 다른 네임스페이스에 둔다 (같으면 커널이 우회한다)
  - netem 을 양쪽에 절반씩 걸어야 대칭 지연이 된다
  - 모든 실행에 timeout 을 건다
  - 조건마다 서버를 새로 띄우고 반드시 죽인다 (잔존 프로세스가 결과를 오염)

방향별 손실
  veth-tx(루트 ns)의 netem  -> 클라이언트 -> 서버 방향
  veth-rx(rx ns)의 netem    -> 서버 -> 클라이언트 방향
우리 FEC 는 c2s 만 보호하므로, 두 방향을 따로 걸 수 있어야 메커니즘이
분리 관측된다.
"""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import time
from _journal import save_result

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS = os.path.join(HERE, "results")
STATE = os.path.join(HERE, "state")
QBED = os.path.join(HERE, "quicbed")
HOME = os.path.expanduser("~")
BIN = os.path.join(HOME, "quicbed", "bin")

# 문서와 같은 이름·주소·포트·경로
NS = "peer"
DEV_LOCAL, DEV_PEER = "v0", "v1"
TX_IP, RX_IP = "10.9.0.1", "10.9.0.2"
SERVER_PORT = 44433
QAMP = "/tmp/qamp"          # 문서 5절: 경로 공백 회피를 위해 /tmp 로 복사

# 실험환경 명세서 5절: CPU 코어를 4개에 고정한다.
#   "40코어 중 4개에 고정. 코어 간 이동에 따른 캐시 미스와 측정 분산 억제"
# 코어 수가 4 미만인 기계에서는 있는 만큼만 쓴다(taskset 이 실패하면 실험 자체가
# 안 도는 것보다 낫다 - 대신 무엇을 썼는지 env 에 남긴다).
def _cpu_list():
    try:
        cpus = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cpus = list(range(os.cpu_count() or 1))
    if not cpus:
        raise RuntimeError("사용할 수 있는 CPU가 없다")
    return ",".join(str(cpu) for cpu in cpus[:4])


CPU_LIST = _cpu_list()
TASKSET = ["taskset", "-c", CPU_LIST] if shutil.which("taskset") else []
WORK = "/tmp/padfec"

os.makedirs(RESULTS, exist_ok=True)
os.makedirs(STATE, exist_ok=True)


def harden():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("FAILED: %s | %s | %s" % (cmd, r.stdout, r.stderr))
    return r


def require_root():
    if os.geteuid() != 0:
        sys.stderr.write("네임스페이스가 필요하다: "
                         "unshare -r -m -n python3 ...\n")
        sys.exit(2)


def require_bin():
    """문서 5절대로 /tmp/qamp 를 쓰되, 없으면 빌드본에서 복사한다.

    WSL 은 세션이 내려가면 /tmp 를 비운다. 문서의 환경(상시 켜진 서버)
    에서는 한 번 복사해 두면 끝이지만 우리는 매번 확인해야 한다.
    이걸 안 챙겨서 timeout: failed to execute process 로 한 번 헛돌았다.
    """
    # 🩸 2026-09-03 - 여기가 `/tmp/qamp` 가 **있기만 하면** 그대로 썼다.
    #    낡았는지는 안 물었다. 그래서 build.sh 를 다시 돌린 뒤에도 /tmp 에
    #    옛 바이너리가 남아 있으면 측정이 그걸로 돌 수 있었다. 빌드본이 더
    #    새것이거나 크기가 다르면 덮어쓴다. 지문 파일도 같이 옮긴다 -
    #    관문이 그걸 읽어 소스와 대조한다(gate_go_parity.check_build_is_current).
    src = os.path.join(BIN, "qamp")
    if os.path.exists(src):
        def digest(path):
            with open(path, "rb") as f:
                return hashlib.file_digest(f, "sha256").digest()
        stale = (not os.path.exists(QAMP)
                 or digest(src) != digest(QAMP))
        if stale:
            shutil.copy2(src, QAMP)
            os.chmod(QAMP, 0o755)
        if os.path.exists(src + ".srcsha"):
            shutil.copy2(src + ".srcsha", QAMP + ".srcsha")
        elif os.path.exists(QAMP + ".srcsha"):
            os.remove(QAMP + ".srcsha")
    if not os.path.exists(QAMP):
        sys.stderr.write("%s 가 없다: quicbed/build.sh 를 먼저 실행" % QAMP)
        sys.stderr.write(chr(10))
        sys.exit(2)
    return QAMP



def setup(mtu=1500):
    """문서 5절 스크립트 그대로."""
    run("mount -t tmpfs none /run", check=False)
    os.makedirs("/run/netns", exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    run("ip netns del %s" % NS, check=False)
    run("ip netns add %s" % NS)
    run("ip link add %s type veth peer name %s" % (DEV_LOCAL, DEV_PEER))
    run("ip link set %s netns %s" % (DEV_PEER, NS))
    run("ip addr add %s/24 dev %s" % (TX_IP, DEV_LOCAL))
    run("ip link set %s mtu %d" % (DEV_LOCAL, mtu))
    run("ip link set %s up" % DEV_LOCAL)
    run("ip link set lo up")
    run("ip netns exec %s ip addr add %s/24 dev %s" % (NS, RX_IP, DEV_PEER))
    run("ip netns exec %s ip link set %s mtu %d" % (NS, DEV_PEER, mtu))
    run("ip netns exec %s ip link set %s up" % (NS, DEV_PEER))
    run("ip netns exec %s ip link set lo up" % NS)
    static_arp()
    verify_link(mtu)


def _mac(dev, ns=None):
    cmd = "ip link show %s" % dev
    if ns:
        cmd = "ip netns exec %s %s" % (ns, cmd)
    out = run(cmd).stdout
    for tok in out.split():
        if len(tok) == 17 and tok.count(":") == 5:
            return tok
    raise RuntimeError("MAC 을 못 읽었다: %s" % out)


def static_arp():
    """🩸 ARP 를 미리 박아 둔다.

    안 그러면 **각 링크 설정 후 첫 데이터그램이 주소 해석을 유발해 왕복
    하나를 더 쓴다.** 손실을 하나도 안 걸었는데 40 회 중 1 회가 2-RTT 로
    나오던 것이 이것이었다. 측정 잡음이 아니라 계통 오차이므로 없앤다.
    """
    ml = _mac(DEV_LOCAL)
    mp = _mac(DEV_PEER, NS)
    run("ip neigh replace %s lladdr %s dev %s nud permanent"
        % (RX_IP, mp, DEV_LOCAL))
    run("ip netns exec %s ip neigh replace %s lladdr %s dev %s nud permanent"
        % (NS, TX_IP, ml, DEV_PEER))


def verify_link(mtu):
    """MTU 가 실제로 걸렸는지 확인한다.

    문서 5절: "loopback(lo)은 MTU 변경이 커널에서 무시됩니다. exit 코드는
    0인데 실제로 적용되지 않아, 초기 실험이 통째로 무효가 되었던 적이
    있습니다." 그래서 exit 코드를 믿지 않고 ip link show 로 눈으로 본다.
    """
    r = run("ip link show %s" % DEV_LOCAL)
    if ("mtu %d" % mtu) not in r.stdout:
        raise RuntimeError("%s MTU 가 %d 로 안 걸렸다: %s"
                           % (DEV_LOCAL, mtu, r.stdout))
    r = run("ip netns exec %s ip link show %s" % (NS, DEV_PEER))
    if ("mtu %d" % mtu) not in r.stdout:
        raise RuntimeError("%s MTU 가 %d 로 안 걸렸다" % (DEV_PEER, mtu))
    # veth 양끝이 서로 다른 네임스페이스에 있는지도 확인한다.
    # 같은 곳에 두면 커널이 loopback 으로 우회한다(문서 5절).
    if DEV_PEER in run("ip link show").stdout:
        raise RuntimeError("%s 가 루트 네임스페이스에 남아 있다" % DEV_PEER)


def _netem_spec(one_way_ms, loss_pct, burst_len, rate_mbit=0.0):
    """문서 5절과 같은 형태: `netem delay 25ms loss 5%`.

    🆕 2026-08-21 - `rate` 를 선택적으로 붙일 수 있게 했다. **기본은 안 건다**
    (rate_mbit=0). 문서 5절 환경이 대역을 안 걸기 때문이고, p9(교차환경)가
    그 환경을 대조하므로 기본값을 바꾸면 안 된다.

    왜 필요했나: J 의 t_tx 항(추가 바이트의 직렬화 시간)은 "이득이 같으면 큰
    m 을 고르는 편향"을 막는 **유일한 힘**인데, 대역을 안 건 이 테스트베드에는
    그 비용이 아예 존재하지 않았다(실측 1,324 B 추가에 0.043 ms). 그래서
      (a) 모형이 청구하는 10 Mbps 가 측정과 25 배 어긋났고,
      (b) **패리티를 과하게 사도 벌점이 없어** 어떤 조건에서도 상수 정책
          m≡2 가 최선이거나 동률이 됐다 — 적응성을 잴 수 없는 환경이었다.
    rate 를 걸면 두 문제가 같이 없어진다. 그 환경은 **새 조건으로 따로** 돌린다.
    """
    spec = "netem delay %.3fms" % one_way_ms
    if rate_mbit and rate_mbit > 0:
        spec += " rate %gmbit" % float(rate_mbit)
    if loss_pct and loss_pct > 0:
        if burst_len and burst_len > 1:
            # gemodel p r : 좋은->나쁜 p, 나쁜->좋은 r.  평균 버스트 = 1/r,
            # 정상상태 손실률 = p/(p+r).
            r_ = 1.0 / float(burst_len)
            p_ = r_ * loss_pct / (100.0 - loss_pct)
            spec += " loss gemodel %.4f%% %.4f%%" % (p_ * 100.0, r_ * 100.0)
        else:
            # ⚠️ `loss p%% corr%%` 형태는 1차에서 실효 손실률을 무너뜨렸다.
            # 상관 인자를 빼고 순수 베르누이로만 쓴다.
            spec += " loss %.4f%%" % loss_pct
    return spec


def set_netem(one_way_ms, loss_c2s=0.0, loss_s2c=0.0, burst_len=1.0,
              rate_up_mbit=0.0, rate_down_mbit=0.0):
    """문서 5절대로 netem 을 양쪽에 절반씩 건다(그래야 대칭 지연이 된다).

    rate_up_mbit   클라이언트 -> 서버(업링크) 대역. 0 이면 안 건다(기본).
    rate_down_mbit 서버 -> 클라이언트 대역. 0 이면 안 건다(기본).

    ⚠️ 업링크에 rate 를 걸면 **정책에도 같은 값을 알려 줘야 한다**
       (`run_client(uplink_mbps=...)`). 안 그러면 모형이 없는 비용을 청구하거나
       있는 비용을 빼먹는다 - 그게 2026-08-21 에 고친 결함의 정체다.
    """
    run("tc qdisc del dev %s root" % DEV_LOCAL, check=False)
    run("ip netns exec %s tc qdisc del dev %s root" % (NS, DEV_PEER),
        check=False)
    run("tc qdisc add dev %s root %s"
        % (DEV_LOCAL, _netem_spec(one_way_ms, loss_c2s, burst_len,
                                  rate_up_mbit)))
    run("ip netns exec %s tc qdisc add dev %s root %s"
        % (NS, DEV_PEER, _netem_spec(one_way_ms, loss_s2c, burst_len,
                                     rate_down_mbit)))


def start_server(certsize, fec="off", stats_path=None, extra=()):
    qamp = require_bin()
    if stats_path is None:
        stats_path = os.path.join(WORK, "srv_stats.json")
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    cmd = ["ip", "netns", "exec", NS] + TASKSET + [qamp,
           "-mode", "server", "-addr", "%s:%d" % (RX_IP, SERVER_PORT),
           "-certsize", str(certsize), "-fec", fec, "-stats", stats_path]
    cmd += list(extra)
    # 🩸 2026-09-07 감사 - stderr 를 파이프로 받으면 (a) READY 대기가 readline
    #    에서 막혀 15 초 기한을 못 지키고 (b) READY 뒤로는 아무도 안 읽어 서버가
    #    로그를 한 줄이라도 더 찍으면 64 KB 파이프가 차서 서버가 멈춘다(클라
    #    시간초과로 보인다). 파일로 받고 파일을 기한 안에서 살핀다.
    err_path = os.path.join(WORK, "srv_stderr.txt")
    err_f = open(err_path, "wb")
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_f)
    err_f.close()
    deadline = time.monotonic() + 15
    ready = False
    while time.monotonic() < deadline:
        try:
            with open(err_path, "rb") as f:
                if b"READY" in f.read():
                    ready = True
                    break
        except OSError:
            pass
        if p.poll() is not None:
            break
        time.sleep(0.05)
    if not ready or p.poll() is not None:
        stop_server(p)
        with open(err_path, "rb") as f:
            diagnostic = f.read()[-1000:].decode("utf-8", "replace")
        raise RuntimeError("서버 준비 실패: %s" % diagnostic)
    return p, stats_path


def stop_server(p):
    if p is None:
        return
    try:
        p.terminate()
    except Exception:
        pass
    try:
        p.wait(timeout=3)
    except Exception:
        try:
            p.kill()
            p.wait(timeout=3)
        except Exception:
            pass


def run_client(group, n, fec="off", m=1, ips=0, gap_ms=25, timeout_s=12,
               stats_path=None, quiet=True, expect_k=0, dump=None,
               extra=(), warmup=0, uplink_mbps=0.0):
    """warmup - 명세 5절의 "워밍업 20~50회, 통계에서 제외".

    앞의 warmup 개 행을 버린다. 캐시·분기예측기·목적지 캐시가 데워지기 전의
    표본이 섞이면 p50/p95 가 위로 끌린다. **버리는 것도 기록에 남긴다** -
    조용히 버리면 표본 수가 왜 다른지 나중에 아무도 모른다.

    uplink_mbps - 이 실행의 **실제 업링크 대역**. 정책(J 의 t_tx 항)에 그대로
    넘긴다. 기본 0 = 대역 제한 없음이고, 그게 `set_netem` 의 기본 환경이다.

    🩸 2026-08-21. 그전에는 정책이 10 Mbps 를 리터럴로 박고 있었는데 이
       테스트베드에는 대역 제한이 아예 없었다. 모형이 없는 비용을 청구하니
       패리티를 과소 구매했고, p11·p15 의 실패 조건이 정확히 그것이었다.
       **환경과 모형이 같은 수를 보게 하는 것**이 이 인자의 목적이다.
       set_netem(rate_up_mbit=X) 를 쓰면 여기에도 X 를 줘야 한다.
    """
    if not isinstance(n, int) or n <= 0 or not 0 <= warmup < n:
        raise ValueError("n must be positive and 0 <= warmup < n")
    qamp = require_bin()
    if stats_path is None:
        stats_path = os.path.join(WORK, "cli_stats.json")
    try:
        os.unlink(stats_path)
    except OSError:
        pass
    # 문서 6절: 모든 실행에 timeout 을 붙인다.
    cmd = ["timeout", str(int(timeout_s * n + 120))] + TASKSET + [qamp,
           "-mode", "client",
           "-addr", "%s:%d" % (RX_IP, SERVER_PORT),
           "-group", group, "-n", str(n),
           "-fec", fec, "-m", str(m),
           "-gap", "%dms" % int(gap_ms),
           "-timeout", "%ds" % int(timeout_s),
           "-stats", stats_path,
           # 정책이 쓰는 업링크 대역. 여기서 **항상** 명시한다 - 안 주면
           # Go 가 생성 표의 기본값(10 Mbps)을 쓰는데, 이 테스트베드의
           # 기본 환경에는 대역 제한이 없어 그 값이 틀린다.
           "-uplink-mbps", ("%g" % float(uplink_mbps))]
    if ips:
        cmd += ["-ips", str(ips)]
    if expect_k:
        cmd += ["-expect-k", str(expect_k)]
    if dump:
        cmd += ["-dump-flight", dump]
    cmd += list(extra)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout_s * n + 180)
    except subprocess.TimeoutExpired:
        return [], {}, "timeout"
    rows = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    n_warm = 0
    if warmup > 0:
        n_warm = min(warmup, len(rows))
        rows = rows[n_warm:]
    stats = {}
    if os.path.exists(stats_path):
        try:
            stats = json.load(open(stats_path))
        except Exception:
            stats = {}
    stats["warmup_dropped"] = n_warm
    stats["cpu_list"] = CPU_LIST
    # 🩸 2026-09-07 감사 - **반환코드를 본다.** 그전에는 qamp 가 panic 으로
    #    죽어도, /tmp/qamp 가 없어 rc 127 이어도, 바깥 timeout(+120 초, 파이썬
    #    timeout +180 보다 먼저 죽인다)이 rc 124 로 죽여도 err="" 로 돌아왔다.
    #    행이 모자란 채 「깨끗한 실행」으로 보였고(08-26 배포판 함정의 「조용히
    #    0 건」이 정확히 이것이다) p17 은 그 불완전한 단위를 저널에 남겼다.
    #    행 수도 같이 본다.
    err = ""
    if r.returncode != 0:
        tail = (r.stderr or "")[-300:].strip().replace("\n", " | ")
        err = ("timeout(rc124)" if r.returncode == 124
               else "exit %d: %s" % (r.returncode, tail))
    elif len(rows) + n_warm != n:
        err = "rows %d != n %d" % (len(rows) + n_warm, n)
    return rows, stats, err


def read_server_stats(path):
    for _ in range(20):
        if os.path.exists(path):
            try:
                return json.load(open(path))
            except Exception:
                pass
        time.sleep(0.1)
    return {}


def pctl(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = int(q * (len(s) - 1))
    return s[i]


def summarize(rows, rtt_ms=None):
    ok = [r["ms"] for r in rows if r.get("ok")]
    out = {
        "n": len(rows),
        "ok": len(ok),
        "fail": len(rows) - len(ok),
        "p50": pctl(ok, 0.50), "p90": pctl(ok, 0.90),
        "p95": pctl(ok, 0.95), "p99": pctl(ok, 0.99),
        "min": min(ok) if ok else None, "max": max(ok) if ok else None,
        "mean": (sum(ok) / len(ok)) if ok else None,
    }
    if rtt_ms:
        # PTO 를 맞은 시행 비율. RFC 9002 의 초기 PTO 는 약 999 ms 이므로
        # RTT 의 몇 배가 아니라 절대 기준으로 세는 편이 덜 모호하다.
        out["pto_rate"] = (sum(1 for t in ok if t > rtt_ms + 500.0)
                           / float(len(ok))) if ok else None
        out["two_rtt_rate"] = (sum(1 for t in ok if t > 1.5 * rtt_ms)
                               / float(len(ok))) if ok else None
        out["rtt_multiple"] = (out["p50"] / rtt_ms) if out["p50"] else None
    if rows:
        kems = set(r.get("kem_id") for r in rows if r.get("ok"))
        out["kem_ids"] = sorted(x for x in kems if x is not None)
        dg = [r.get("initial_datagrams") for r in rows
              if r.get("initial_datagrams")]
        out["initial_datagrams_median"] = pctl(dg, 0.5)
    return out


def measured_C(group):
    """이 그룹의 ClientHello 크기(C)를 **측정 결과에서** 읽는다.

    🩸 2026-08-25 - p17·p18 이 X25519MLKEM768 을 재면서 모형에는
       `C=1146` 을 박아 넣고 있었다. 실측은 1448 이고(x25519 는 270),
       natural_k(1146)=1 vs natural_k(1448)=2 라 **모형이 k=1 로**
       계산했다. p18 의 '모형이 m=4 이득을 12 배 과대평가' 는 그래서
       생긴 허상이었다(바른 C 로는 예측 +2.38 / 실측 +1.43).

       p4 는 이미 p1_flight.json 에서 읽고 있었다. 창구를 하나로
       모으고, 없으면 **대체값으로 넘어가지 말고 죽는다** - 조용한
       대체값이 바로 이 사고를 만든 물건이다.
    """
    p = os.path.join(RESULTS, "p1_flight.json")
    if not os.path.exists(p):
        raise SystemExit(
            "measured_C: %s 가 없다. C 는 측정값이므로 지어낼 수 없다. "
            "먼저 p1 을 돌려라 (python experiments/loop2.py --only p1)."
            % p)
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    for c in d.get("capacity_checks", []):
        if c.get("group") == group and c.get("ips") == 0 \
                and isinstance(c.get("C"), int):
            return c["C"]
    raise SystemExit(
        "measured_C: p1_flight.json 에 그룹 %r 의 C 가 없다. "
        "있는 그룹: %s"
        % (group, [c.get("group") for c in d.get("capacity_checks", [])
                   if c.get("ips") == 0]))


def save(name, obj):
    return save_result(os.path.join(RESULTS, name), obj)
