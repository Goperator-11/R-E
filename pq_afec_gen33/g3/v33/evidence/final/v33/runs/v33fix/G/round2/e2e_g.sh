#!/bin/bash
set -uo pipefail
source /mnt/c/Users/scien/AppData/Local/Temp/claude/C--Users-scien/98dad099-940c-4208-8359-61078035dc93/scratchpad/v33fix2/G-testbed/v2/goenv.sh
ORIG=/mnt/c/Users/scien/AppData/Local/Temp/claude/C--Users-scien/98dad099-940c-4208-8359-61078035dc93/scratchpad/v33fix2/G-testbed/orig/experiments/quicbed
OUTD="$S/out/e2e"
W="$BASE/e2e"
rm -rf "$OUTD" "$W"; mkdir -p "$OUTD" "$W"
rm -rf "$BASE/src_preG"; mkdir -p "$BASE/src_preG"
cp -r "$REPO/experiments/quicbed/." "$BASE/src_preG/"
cp "$ORIG/qamp.go" "$ORIG/flight_shape.go" "$BASE/src_preG/"
bash "$S/stage.sh" "$BASE/src_preG" "$BASE/stage_preG" || exit 1
(cd "$BASE/stage_preG" && go build -trimpath -buildvcs=false -o "$W/qamp_preG" ./cmd/qamp) || exit 1
rm -rf "$BASE/src_cur"; mkdir -p "$BASE/src_cur"
cp -r "$REPO/experiments/quicbed/." "$BASE/src_cur/"
bash "$S/stage.sh" "$BASE/src_cur" "$BASE/stage_cur" || exit 1
(cd "$BASE/stage_cur" && go build -trimpath -buildvcs=false -o "$W/qamp_cur" ./cmd/qamp) || exit 1
(cd "$W" && sha256sum qamp_cur qamp_preG) | tee "$OUTD/binaries.txt"
PORT=$((47000 + RANDOM % 1000))

server() {
    local tag="$1" bin="$2"
    shift 2
    PORT=$((PORT + 1))
    "$bin" -mode server -addr "127.0.0.1:$PORT" -stats "$W/$tag.server.json" "$@" > /dev/null 2> "$W/$tag.server.err" &
    SPID=$!
    for _ in $(seq 1 100); do
        grep -q READY "$W/$tag.server.err" 2>/dev/null && return 0
        sleep 0.05
    done
    echo "server $tag not ready" >&2
    cat "$W/$tag.server.err" >&2
    return 1
}

stop_server() {
    kill -TERM "$SPID" 2>/dev/null
    wait "$SPID" 2>/dev/null
}

client() {
    local tag="$1" bin="$2"
    shift 2
    timeout 90 "$bin" -mode client -addr "127.0.0.1:$PORT" "$@" -stats "$W/$tag.client.json" > "$W/$tag.rows.jsonl" 2> "$W/$tag.client.err"
    echo "client_rc=$?"
}

summ() {
    local tag="$1"
    python3 - "$W/$tag.rows.jsonl" "$W/$tag.server.json" "$W/$tag.conns.jsonl" <<'PY'
import json, os, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
sv = json.load(open(sys.argv[2]))
def uniq(f):
    return sorted({json.dumps(f(r), sort_keys=True) for r in rows})
print("rows", len(rows), "ok", sum(bool(r.get("ok")) for r in rows))
print("  profile", uniq(lambda r: r.get("profile", "<absent>")), "retrans_layout", uniq(lambda r: r.get("retrans_layout")),
      "wait_ms", uniq(lambda r: r.get("feedback_wait_limit_ms")))
print("  tracer", uniq(lambda r: r["observation"]["tracer"]), "pto_scope", uniq(lambda r: r["observation"]["pto_count_scope"]),
      "expectation", uniq(lambda r: r.get("flight_expectation")))
print("  arrivals_src", uniq(lambda r: r["arrivals"]["src"]), "c1_version", uniq(lambda r: r["c1"].get("version")),
      "parity_sent", [r.get("parity_sent") for r in rows], "later_parity_sent", [r.get("later_parity_sent") for r in rows])
print("  server profile", sv.get("profile"), "udp_path", sv.get("udp_path"), "feedback_version", sv.get("feedback_version"), "fb_sent", sv.get("fb_sent"))
if os.path.exists(sys.argv[3]):
    conns = [json.loads(l) for l in open(sys.argv[3]) if l.strip()]
    print("  conn_log lines", len(conns), "reasons", sorted({c["reason"] for c in conns}), "keys_unique", len({c["key"] for c in conns}))
PY
}

for B in cur preG; do
    BIN="$W/qamp_$B"
    echo "== $B sealed31 both sides, no -feedback (sealed v3.1 reproduction, m4L3)"
    server "$B.sealed" "$BIN" -profile sealed31 -fec on -conn-log "$W/$B.sealed.conns.jsonl"
    client "$B.sealed" "$BIN" -profile sealed31 -fec on -layout v3 -m 4 -lead 3 -expect-k 2 -gap 50ms -timeout 10s -n 4
    sleep 0.3; stop_server; summ "$B.sealed"
    echo "== $B sealed31 both sides with -feedback, auto3 (v33auto learning arm)"
    server "$B.sealedfb" "$BIN" -profile sealed31 -fec on -feedback
    client "$B.sealedfb" "$BIN" -profile sealed31 -fec auto3 -cache3 "$W/$B.c3.json" -feedback -n 4
    sleep 0.3; stop_server; summ "$B.sealedfb"
    echo "== $B default server and default client row"
    server "$B.default" "$BIN" -fec on
    client "$B.default" "$BIN" -fec on -layout v3 -m 2 -lead 1 -n 4
    sleep 0.3; stop_server; summ "$B.default"
    for L in default original_first; do
        echo "== $B forced pre-response follow-up, retrans-layout $L"
        EXTRA=()
        [ "$L" = original_first ] && EXTRA=(-retrans-layout original_first)
        server "$B.retrans_$L" "$BIN" -fec on
        client "$B.retrans_$L" "$BIN" -fec on -layout v3 -m 2 -lead 1 -expect-k 2 -drop-initial 0,1 -drop-parity 0 -n 3 "${EXTRA[@]}"
        sleep 0.3; stop_server; summ "$B.retrans_$L"
    done
done
cp "$W"/*.json "$W"/*.jsonl "$W"/*.err "$OUTD/" 2>/dev/null
pkill -f "$W/qamp_" 2>/dev/null
echo done
