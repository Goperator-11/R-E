#!/bin/bash
set -uo pipefail
source /mnt/c/Users/scien/AppData/Local/Temp/claude/C--Users-scien/98dad099-940c-4208-8359-61078035dc93/scratchpad/v33fix/B/goenv.sh
OUTD="$S/out/e2e"
rm -rf "$OUTD"
mkdir -p "$OUTD"
W="$T/e2e"
rm -rf "$W"
mkdir -p "$W"
bash "$S/stage.sh" "$S/src_head" "$S/src_mine" "$T/stage_e2e_fixed" > /dev/null
bash "$S/stage.sh" "$S/src_head" "" "$T/stage_e2e_head" > /dev/null
(cd "$T/stage_e2e_fixed" && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o "$W/qamp_fixed" ./cmd/qamp) || exit 1
(cd "$T/stage_e2e_head" && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o "$W/qamp_head" ./cmd/qamp) || exit 1
sha256sum "$W/qamp_fixed" "$W/qamp_head" | tee "$OUTD/binaries.txt"
PORT=$((47000 + RANDOM % 1000))

server() {
    local tag="$1" bin="$2"
    shift 2
    PORT=$((PORT + 1))
    "$bin" -mode server -addr "127.0.0.1:$PORT" -fec on -feedback -stats "$W/$tag.server.json" "$@" > /dev/null 2> "$W/$tag.server.err" &
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
    timeout 60 "$bin" -mode client -addr "127.0.0.1:$PORT" -n 4 -gap 25ms "$@" -stats "$W/$tag.client.json" > "$W/$tag.rows.jsonl" 2> "$W/$tag.client.err"
    echo "client_rc=$?"
}

summ() {
    local tag="$1"
    python3 - "$W/$tag.rows.jsonl" "$W/$tag.client.json" "$W/$tag.server.json" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
cl = json.load(open(sys.argv[2]))
sv = json.load(open(sys.argv[3]))
print("rows", len(rows), "ok", sum(r.get("ok", False) for r in rows),
      "server_bytes", [r.get("server_bytes") for r in rows],
      "fb_recv", cl.get("fb_recv"), "fb_magic_seen", cl.get("fb_magic_seen"),
      "srv_fb_sent", sv.get("fb_sent"), "srv_feedback_version", sv.get("feedback_version"),
      "srv_udp_path", sv.get("udp_path"), "srv_profile", sv.get("profile"))
EOF
}

for FROZEN in g3c_6baf2b52 gen32_85f54cf5 g2_d98b05d7; do
    FB="/home/scien/frozen/$FROZEN/qamp"
    for VAR in head_default fixed_default fixed_v2 fixed_sealed31 fixed_nofeedback; do
        case "$VAR" in
            head_default) server "$FROZEN.$VAR" "$W/qamp_head" ;;
            fixed_default) server "$FROZEN.$VAR" "$W/qamp_fixed" ;;
            fixed_v2) server "$FROZEN.$VAR" "$W/qamp_fixed" -feedback-version 2 ;;
            fixed_sealed31) server "$FROZEN.$VAR" "$W/qamp_fixed" -profile sealed31 ;;
            fixed_nofeedback)
                PORT=$((PORT + 1))
                "$W/qamp_fixed" -mode server -addr "127.0.0.1:$PORT" -fec on -stats "$W/$FROZEN.$VAR.server.json" > /dev/null 2> "$W/$FROZEN.$VAR.server.err" &
                SPID=$!
                for _ in $(seq 1 100); do grep -q READY "$W/$FROZEN.$VAR.server.err" && break; sleep 0.05; done
                ;;
        esac
        echo "== frozen client $FROZEN, server $VAR"
        client "$FROZEN.$VAR" "$FB" -fec on -m 1 -feedback
        sleep 0.3
        stop_server
        summ "$FROZEN.$VAR"
    done
done

echo "== gen33 fixed client on version 2 and version 3 servers"
for VAR in v3 v2; do
    if [ "$VAR" = v2 ]; then server "self.$VAR" "$W/qamp_fixed" -feedback-version 2; else server "self.$VAR" "$W/qamp_fixed"; fi
    client "self.$VAR" "$W/qamp_fixed" -fec on -layout v3 -m 2 -lead 1 -feedback
    sleep 0.3
    stop_server
    summ "self.$VAR"
    python3 - "$W/self.$VAR.rows.jsonl" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print("c1_version", [r["c1"]["version"] for r in rows], "arrivals", [(r["arrivals"]["src"], r["arrivals"]["sent"], r["arrivals"]["lost"]) for r in rows],
      "retrans_layout", sorted({r["retrans_layout"] for r in rows}), "tracer", sorted({r["observation"]["tracer"] for r in rows}))
EOF
done

echo "== sealed31 on both sides"
server "sealed" "$W/qamp_fixed" -profile sealed31 -conn-log "$W/sealed.conns.jsonl"
client "sealed" "$W/qamp_fixed" -profile sealed31 -fec on -layout v3 -m 2 -lead 1 -feedback
sleep 0.3
stop_server
summ "sealed"
python3 - "$W/sealed.rows.jsonl" "$W/sealed.conns.jsonl" "$W/sealed.server.json" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
conns = [json.loads(l) for l in open(sys.argv[2]) if l.strip()]
sv = json.load(open(sys.argv[3]))
print("profile", sorted({r.get("profile") for r in rows}), "wait_ms", sorted({r["feedback_wait_limit_ms"] for r in rows}),
      "tracer", sorted({r["observation"]["tracer"] for r in rows}), "pto_scope", sorted({r["observation"]["pto_count_scope"] for r in rows}),
      "packets", sorted({len(r["observation"]["packets"]) for r in rows}), "c1_version", [r["c1"]["version"] for r in rows],
      "expect", sorted({json.dumps(r["flight_expectation"]) for r in rows}))
print("conn_log_lines", len(conns), "reasons", sorted({c["reason"] for c in conns}), "keys_unique", len({c["key"] for c in conns}),
      "tx_sizes_nonempty", all(c["tx_sizes"] for c in conns), "server_conn_log", sv.get("conn_log"))
EOF

echo "== conn-log expiry before shutdown"
server "expiry" "$W/qamp_fixed" -conn-log "$W/expiry.conns.jsonl"
client "expiry" "$W/qamp_fixed" -fec on -m 1 -feedback
sleep 11.5
python3 - "$W/expiry.conns.jsonl" "$W/expiry.server.json" <<'EOF'
import json, sys
conns = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
sv = json.load(open(sys.argv[2]))
print("before_sigterm lines", len(conns), "reasons", sorted({c["reason"] for c in conns}), "periodic conns", len(sv["conns"]), "live", sv["conn_acct_live"], "expired", sv["conn_acct_expired"])
EOF
stop_server
python3 - "$W/expiry.conns.jsonl" <<'EOF'
import json, sys
conns = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print("after_sigterm lines", len(conns), "beff_stack", [c["beff_stack"] for c in conns], "tx_dgrams", [c["tx_dgrams"] for c in conns])
EOF

echo "== CLI refusals"
"$W/qamp_fixed" -mode server -profile sealed31 -udp-path oob > /dev/null 2> "$W/refuse1.err"; echo "sealed31+oob rc=$? $(cat "$W/refuse1.err")"
"$W/qamp_fixed" -mode client -feedback-version 2 > /dev/null 2> "$W/refuse2.err"; echo "client+feedback-version rc=$? $(cat "$W/refuse2.err")"
"$W/qamp_fixed" -mode client -revisit-guard -client-tracer=false -fec on -layout v3 -m 1 -decoder-support supported > /dev/null 2> "$W/refuse3.err"; echo "guard+notracer rc=$? $(cat "$W/refuse3.err")"
touch "$W/exists.jsonl"
timeout 5 "$W/qamp_fixed" -mode server -addr 127.0.0.1:$((PORT + 50)) -conn-log "$W/exists.jsonl" > /dev/null 2> "$W/refuse4.err"; echo "existing conn-log rc=$? $(tail -1 "$W/refuse4.err")"
"$W/qamp_fixed" -mode server -feedback-version 4 > /dev/null 2> "$W/refuse5.err"; echo "feedback-version 4 rc=$? $(cat "$W/refuse5.err")"
cp "$W"/*.json "$W"/*.jsonl "$W"/*.err "$OUTD/" 2>/dev/null
pkill -f "$W/qamp_" 2>/dev/null
echo done
