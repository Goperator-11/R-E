import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

BASE = Path("/mnt/c/dev/codex_handoff/v33/runs")
GO = Path("/home/scien/goroot")
QUIC = Path("/home/scien/go/pkg/mod/github.com/quic-go/quic-go@v0.61.0")
sources = {
    GO / "VERSION": [(1, 5)],
    GO / "src/crypto/mlkem/mlkem.go": [(18, 39)],
    GO / "src/crypto/tls/key_schedule.go": [(84, 110), (162, 215)],
    GO / "src/crypto/tls/handshake_client.go": [(126, 162)],
    QUIC / "internal/ackhandler/received_packet_tracker.go": [(14, 75)],
    QUIC / "packet_packer.go": [(316, 330)],
    QUIC / "internal/wire/extended_header.go": [(105, 145)],
    QUIC / "internal/protocol/packet_number.go": [(35, 63)],
}
files, contents = [], {}
for path, spans in sources.items():
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    content = raw.decode("utf-8")
    contents[str(path)] = content
    lines = content.splitlines()
    sections = [{"start_line": start, "end_line_inclusive": min(end, len(lines)), "text": "\n".join(lines[start - 1:end])} for start, end in spans]
    files.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "sections": sections})
mlkem = int(re.search(r"EncapsulationKeySize768\s*=\s*(\d+)", contents[str(GO / "src/crypto/mlkem/mlkem.go")]).group(1))
hybrid = re.search(r"case X25519MLKEM768:.*?\n\s*(\d+), mlkem.EncapsulationKeySize768", contents[str(GO / "src/crypto/tls/key_schedule.go")], re.S)
x25519 = int(hybrid.group(1))
assert (mlkem, x25519) == (1184, 32)
result = {"schema": "padfec.v33.j6_quic_source_read/1", "recorded_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
    "go_version_file": contents[str(GO / "VERSION")], "source_kind": "local_source_read_only", "files": files,
    "key_share_data_bytes": {"mlkem768_encapsulation_key": mlkem, "x25519_public_key": x25519, "sum": mlkem + x25519},
    "scope": "Local code constants and construction, no build, runtime key exchange, packet capture or generic k bound proof.",
    "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
out = BASE / "J6_quic_source_read_v1.json"
assert out.resolve().is_relative_to(BASE.resolve())
with out.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"out": str(out), "files": len(files), "go_version": result["go_version_file"], "key_share_data_bytes": result["key_share_data_bytes"], "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}))
