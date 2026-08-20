#!/bin/bash
BIN="$HOME/quicbed/bin"
"$BIN/qserver" -addr 127.0.0.1:4433 -certsize 2955 2>/tmp/qserver.log &
SРID=$!
sleep 1
head -3 /tmp/qserver.log
for g in x25519 X25519MLKEM768; do
  echo "--- $g ---"
  "$BIN/qclient" -addr 127.0.0.1:4433 -group "$g" -n 3 -gap 50ms
done
kill %1 2>/dev/null
wait 2>/dev/null
echo "smoke done"
