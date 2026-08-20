#!/bin/sh
# =========================================================================
# run_confined.sh - 공유 리눅스 서버에서 PQ-AFEC를 "가둬서" 돌리는 실행 래퍼
#
#   ./run_confined.sh                          # 기본: verify.py, CPU 0번, 1G
#   ./run_confined.sh -c 2-3 -m 2G -- python3 tune_cache.py 1.5
#   ./run_confined.sh -n -- python3 demo.py    # -n: 실제 실행 없이 계획만 출력
#
# 왜 필요한가: 이 서버는 공유 장비다. 알고리즘 코드 자체는 프로젝트 폴더
# 밖을 안 만지고(verify의 발자국 테스트가 보증), 소켓도 스레드도 안 쓰는
# 단일 코어 순수 계산이지만, 그래도 OS 수준에서 한 번 더 가둔다:
#
#   1단계(가능하면): systemd-run --user 샌드박스
#      - ProtectSystem=strict  : 시스템 전체가 읽기 전용
#      - ProtectHome=read-only : 홈도 읽기 전용
#      - ReadWritePaths=<이 폴더> : 쓰기는 프로젝트 폴더 안에서만 가능
#      - PrivateTmp, NoNewPrivileges
#      - AllowedCPUs / MemoryMax / CPUWeight=20 : 할당 코어 밖 사용 불가,
#        메모리 상한, 다른 사용자 작업에 항상 양보
#   * 코어 고정은 systemd의 AllowedCPUs에만 맡기지 않는다: cpuset 컨트롤러가
#     사용자 슬라이스에 위임 안 된 서버(흔함)에서는 그 속성이 "조용히" 무시된다
#     (WSL 실측). taskset은 비특권 syscall이라 어디서나 강제된다 - 이중 적용.
#   2단계(systemd 샌드박스가 안 되는 환경): 자원 제한만
#      - systemd-run --user --scope -p AllowedCPUs -p MemoryMax
#   3단계(systemd 자체가 없음): taskset -c + nice 19 + ulimit -v
#
# 어느 단계로 실행됐는지 시작할 때 출력한다. 출력은 ASCII만.
# =========================================================================
set -u

PROJ=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CPUS="0"
MEM="1G"
DRY=0

while [ $# -gt 0 ]; do
    case "$1" in
        -c) CPUS="$2"; shift 2 ;;
        -m) MEM="$2"; shift 2 ;;
        -n) DRY=1; shift ;;
        --) shift; break ;;
        -h|--help)
            sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown option: $1 (use -h)"; exit 2 ;;
    esac
done
[ $# -gt 0 ] || set -- python3 verify.py

mem_to_kb() {
    case "$1" in
        *G) echo $(( ${1%G} * 1024 * 1024 )) ;;
        *M) echo $(( ${1%M} * 1024 )) ;;
        *)  echo "$1" ;;
    esac
}

SANDBOX_PROPS="-p ProtectSystem=strict -p ProtectHome=read-only \
 -p ReadWritePaths=$PROJ -p PrivateTmp=yes -p NoNewPrivileges=yes"
# cgroup 위임이 안 되는 서버에서 AllowedCPUs/MemoryMax는 "조용히" 무시된다
# (WSL 실측). CPUAffinity(sched_setaffinity)와 LimitAS(rlimit)는 위임과
# 무관하게 커널이 강제하므로 둘 다 건다 - 되는 쪽이 잡는다.
RES_PROPS="-p AllowedCPUs=$CPUS -p CPUAffinity=$CPUS  -p MemoryMax=$MEM -p LimitAS=$MEM -p CPUWeight=20"

have_systemd_user() {
    command -v systemd-run >/dev/null 2>&1 || return 1
    systemd-run --user --quiet --collect true >/dev/null 2>&1
}

sandbox_works() {
    # shellcheck disable=SC2086
    systemd-run --user --quiet --wait --collect --pipe \
        $SANDBOX_PROPS $RES_PROPS true >/dev/null 2>&1
}

if [ "$DRY" = 1 ]; then
    echo "[dry-run] project dir : $PROJ"
    echo "[dry-run] cpus=$CPUS mem=$MEM cmd: $*"
    if have_systemd_user; then
        if sandbox_works; then echo "[dry-run] tier 1: systemd sandbox + resources"
        else echo "[dry-run] tier 2: systemd resources only"; fi
    else
        echo "[dry-run] tier 3: taskset/nice/ulimit"
    fi
    exit 0
fi

if have_systemd_user; then
    if sandbox_works; then
        echo "[confined] tier 1: systemd sandbox (fs read-only outside project)"
        echo "[confined] cpus=$CPUS mem=$MEM (CPUAffinity+LimitAS) dir=$PROJ"
        # shellcheck disable=SC2086
        exec systemd-run --user --quiet --wait --collect --pipe             $SANDBOX_PROPS $RES_PROPS             --working-directory="$PROJ" -- "$@"
    fi
    echo "[confined] tier 2: systemd resources only (sandbox unavailable)"
    echo "[confined] cpus=$CPUS mem=$MEM (taskset+ulimit)"
    KB=$(mem_to_kb "$MEM")
    PIN=""
    command -v taskset >/dev/null 2>&1 && PIN="taskset -c $CPUS"
    cd "$PROJ" || exit 1
    ulimit -v "$KB" 2>/dev/null
    # scope에는 exec 속성(CPUAffinity 등)이 안 걸리므로 바깥에서 건다
    # shellcheck disable=SC2086
    exec systemd-run --user --quiet --scope --collect         -p AllowedCPUs=$CPUS -p MemoryMax=$MEM -p CPUWeight=20 -- $PIN "$@"
fi

echo "[confined] tier 3: taskset/nice/ulimit (no systemd user manager)"
KB=$(mem_to_kb "$MEM")
echo "[confined] cpus=$CPUS vmem=${KB}KB nice=19"
cd "$PROJ" || exit 1
ulimit -v "$KB" 2>/dev/null || echo "[confined] warn: ulimit -v not supported"
if command -v taskset >/dev/null 2>&1; then
    exec nice -n 19 taskset -c "$CPUS" "$@"
fi
echo "[confined] warn: taskset missing, running with nice only"
exec nice -n 19 "$@"
