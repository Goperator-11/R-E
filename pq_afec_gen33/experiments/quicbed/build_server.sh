#!/bin/bash
echo "Historical builder disabled in gen33; use build_gen33.sh" >&2
exit 2
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SRC/build.sh" "$@"
