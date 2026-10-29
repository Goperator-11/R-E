#!/bin/bash
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
# Use the checked-in dependency versions and the same source fingerprint as
# the measurement runner. A separate go mod init/tidy would select new versions.
exec bash "$SRC/build.sh" "$@"
