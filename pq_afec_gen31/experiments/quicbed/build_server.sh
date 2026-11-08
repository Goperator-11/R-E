#!/bin/bash
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SRC/build.sh" "$@"
