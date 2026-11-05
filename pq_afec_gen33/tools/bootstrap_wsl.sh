#!/bin/bash
set -euo pipefail
MODE=${1:---check}
if [ "$#" -gt 1 ] || { [ "$MODE" != --check ] && [ "$MODE" != --install ]; }; then
    echo 'usage: bootstrap_wsl.sh [--check|--install]' >&2
    exit 2
fi
VERSION=1.26.6
SHA=708effb774be8237570d0add163225abbdfaf4fca28b2611df167beba4feef89
DISTRO=${PADFEC_WSL_DISTRO:-Ubuntu}
TARGET=${PADFEC_GOROOT:-$HOME/goroot}
if [ -n "${WSL_DISTRO_NAME:-}" ] && [ "$WSL_DISTRO_NAME" != "$DISTRO" ]; then
    echo 'configured WSL distribution differs from running distribution' >&2
    exit 1
fi
if [ "$MODE" = --install ]; then
    if [ "$(uname -m)" != x86_64 ]; then
        echo 'this pinned archive supports linux-amd64 only' >&2
        exit 1
    fi
    if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
        echo "refusing to replace existing toolchain: $TARGET" >&2
        exit 1
    fi
    mkdir -p "$HOME/v33_runs/bootstrap"
    STAGE=$(mktemp -d "$HOME/v33_runs/bootstrap/install.XXXXXX")
    ARCHIVE="$STAGE/go$VERSION.linux-amd64.tar.gz"
    curl --fail --location --proto '=https' --output "$ARCHIVE" "https://go.dev/dl/go$VERSION.linux-amd64.tar.gz"
    printf '%s  %s\n' "$SHA" "$ARCHIVE" | sha256sum --check --strict
    tar -xzf "$ARCHIVE" -C "$STAGE"
    mkdir -p "$(dirname "$TARGET")"
    mv -T "$STAGE/go" "$TARGET"
    echo "verified archive preserved at $ARCHIVE"
fi
if [ ! -x "$TARGET/bin/go" ] && [ "$MODE" = --check ] && [ -z "${PADFEC_GOROOT:-}" ] && [ -x "$HOME/goroot$VERSION/bin/go" ]; then
    TARGET="$HOME/goroot$VERSION"
fi
export GOROOT="$TARGET" GOTOOLCHAIN=local
FAIL=0
echo "mode=$MODE distro=$DISTRO goroot=$GOROOT"
if [ -x "$GOROOT/bin/go" ] && [ "$("$GOROOT/bin/go" env GOVERSION)" = "go$VERSION" ]; then
    "$GOROOT/bin/go" version
    sha256sum "$GOROOT/bin/go"
else
    echo 'required Go toolchain missing or version mismatch' >&2
    FAIL=1
fi
for COMMAND in ip tc unshare; do
    if ! command -v "$COMMAND"; then
        echo "required command missing: $COMMAND (ip and tc are supplied by iproute2)" >&2
        FAIL=1
    fi
done
if [ "$FAIL" -eq 0 ]; then
    if ! unshare -Urnm -- sh -c 'ip link set lo up && tc qdisc add dev lo root netem delay 1ms && tc qdisc show dev lo'; then
        echo 'unprivileged netem check failed' >&2
        FAIL=1
    fi
fi
if [ "$FAIL" -eq 0 ]; then
    echo 'bootstrap_check=PASS'
else
    echo 'bootstrap_check=FAIL'
fi
exit "$FAIL"
