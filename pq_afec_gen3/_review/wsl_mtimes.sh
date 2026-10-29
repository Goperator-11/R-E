#!/bin/bash
echo "== ~/quicbed files newer than 2026-10-02 09:00"
find "$HOME/quicbed" -newermt "2026-10-02 09:00" -type f 2>/dev/null | grep -v '/pkg/mod/' | head -20
ls -la --time-style=full-iso "$HOME/quicbed/bin/" 2>&1 | head
echo "== /tmp/qamp"
ls -la --time-style=full-iso /tmp/qamp 2>&1
echo "== ~/.codex newer"
find "$HOME/.codex" -newermt "2026-10-02 09:00" -type f 2>/dev/null | head
echo "== ~/quicbed_g3"
ls -la --time-style=full-iso "$HOME/quicbed_g3" "$HOME/quicbed_g3/cmd/qamp"
