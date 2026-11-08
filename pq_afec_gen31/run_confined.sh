#!/bin/sh
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
RES_PROPS="-p AllowedCPUs=$CPUS -p CPUAffinity=$CPUS  -p MemoryMax=$MEM -p LimitAS=$MEM -p CPUWeight=20"

have_systemd_user() {
    command -v systemd-run >/dev/null 2>&1 || return 1
    systemd-run --user --quiet --collect true >/dev/null 2>&1
}

sandbox_works() {
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
        exec systemd-run --user --quiet --wait --collect --pipe             $SANDBOX_PROPS $RES_PROPS             --working-directory="$PROJ" -- "$@"
    fi
    echo "[confined] tier 2: systemd resources only (sandbox unavailable)"
    echo "[confined] cpus=$CPUS mem=$MEM (taskset+ulimit)"
    KB=$(mem_to_kb "$MEM")
    PIN=""
    command -v taskset >/dev/null 2>&1 && PIN="taskset -c $CPUS"
    cd "$PROJ" || exit 1
    ulimit -v "$KB" 2>/dev/null
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
