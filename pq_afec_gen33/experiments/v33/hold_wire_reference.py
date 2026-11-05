import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import time

from experiments.v33.hold_reference import configurations, case_orders, run_case


FIELDS = ("complete", "used", "recovered", "delivered", "bytes_in", "bytes_to_stack",
          "held_bytes", "pending_bytes", "discard_bytes", "consumed_overhead", "terminal", "created_ns", "deadline_ns")


def canonical_output(decoder):
    result = decoder.result()
    return json.dumps({key: result[key] for key in FIELDS}, sort_keys=True, separators=(",", ":")).encode("ascii")


def generate(output):
    report_path = output.with_suffix(output.suffix + ".json")
    if output.exists() or report_path.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    paths = [Path(__file__).with_name(name) for name in ("hold_wire_reference.py", "hold_reference.py", "hold_decoder.py")]
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    digest = hashlib.sha256()
    groups = []
    with output.open("xb") as raw, gzip.GzipFile(fileobj=raw,mode="wb",mtime=0,filename="") as compressed:
        for k,m,lead in configurations():
            count, checked = 0, 0
            identifiers = hashlib.sha256()
            group_digest = hashlib.sha256()
            for order in case_orders(k+m):
                decoder = run_case(k,m,lead,order)
                code = "".join(map(str,order)) or "-"
                expected = hashlib.sha256(canonical_output(decoder)).hexdigest()
                row = f"{k}\t{m}\t{lead}\t{code}\t{expected}\n".encode("ascii")
                compressed.write(row)
                group_digest.update(row)
                digest.update(row)
                identifiers.update((",".join(map(str,order))+"\n").encode("ascii"))
                count += 1
                checked += len(decoder.events)
            assert count == sum(math.perm(k+m,r) for r in range(k+m+1))
            group = dict(k=k,m=m,lead=lead,cases=count,checked_transitions=checked,case_ids_sha256=identifiers.hexdigest(),rows_sha256=group_digest.hexdigest())
            groups.append(group)
            print(json.dumps(group),flush=True)
    assert sum(g["cases"] for g in groups) == 700116
    assert sources == {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result = {"schema":"m1-wire-reference-v1", "kind":"Python_expected_actual_ReadFrom_outputs", "go_checked":False,
              "sources_sha256":sources, "cases":700116,"groups":groups,"fields":FIELDS,
              "raw_sha256":digest.hexdigest(),"gzip_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
              "elapsed_seconds":time.monotonic()-started,
              "fixture":{"original_sizes":"1200+17*i", "parity_size":1331,"dcid_bytes":8,"scid_bytes":4,
                         "symbol_size":"1331-34-6*k", "arrival_ns":"(position+1)*1000", "finish":"deadline only, before TTL"}}
    with report_path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps({key:value for key,value in result.items() if key not in ("groups","sources_sha256")}),flush=True)
