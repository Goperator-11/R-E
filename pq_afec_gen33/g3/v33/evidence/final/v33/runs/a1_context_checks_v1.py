import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import datetime as dt
import hashlib
import json

r = Path(r'C:\dev\codex_handoff\v33\runs')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
checks = []
for generation, stages in [('pq_afec_gen3', [0, 2]), ('pq_afec_gen31', [0, 2, 3])]:
    base = Path('C:/dev') / generation
    for stage in stages:
        source = base / f'g3/SEAL_stage{stage}.json'
        seal = json.loads(source.read_text(encoding='utf-8-sig'))
        fields = []
        for field in ('sha256', 'also_recorded_sha256'):
            records = []
            for relative, expected in seal.get(field, {}).items():
                p = base / relative
                actual = sha(p) if p.exists() else None
                records.append(dict(path=str(p), expected=expected, actual=actual, match=actual == expected))
            fields.append(dict(field=field, total=len(records), matched=sum(x['match'] for x in records), records=records))
        checks.append(dict(generation=generation, stage=stage, seal=str(source), seal_sha256=sha(source), fields=fields))
mtc = []
for level, pk, sig in [('44', 1312, 2420), ('65', 1952, 3309)]:
    for proof in (512, 800):
        tls = 1220 + 150 + pk + 300 + proof + sig
        mtc.append(dict(variant=f'MTC landmark ML-DSA-{level}', proof_assumption_B=proof, tls_estimate_B=tls, wire_estimate_B=tls * 1280 / 1230, synthetic_certsize_if_s0_1724_B=tls * 1280 / 1230 - 1724))
tls = 1220 + 150 + 1312 + 300 + 800 + 2 * 2420
mtc.append(dict(variant='MTC standalone ML-DSA-44 one extra CA signature hypothesis', proof_assumption_B=800, tls_estimate_B=tls, wire_estimate_B=tls * 1280 / 1230, synthetic_certsize_if_s0_1724_B=tls * 1280 / 1230 - 1724))
source = r.parent / 'evidence/audit-prior-art/s_estimates.py'
value = dict(status='PASS', kind='read_only_hash_check_and_explicit_size_hypotheses', recorded_kst=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(), seals=checks, mtc=mtc, classical_compressed_chain_scenario=dict(certificate_B=3200, verify_B=80, server_hello_B=1220, extra_B=150, tls_estimate_B=4650, wire_estimate_B=4650 * 1280 / 1230), estimate_assumptions=dict(server_hello_B=1220, extra_B=150, certificate_fields_B=300, packet_B=1280, crypto_payload_B=1230, proof_B=[512,800], all_sizes='assumed except FIPS key/signature sizes; no MTC transport measurement'), source=str(source), source_sha256=sha(source))
with (r / 'A1_context_checks_v1.json').open('x', encoding='utf-8') as f:
    json.dump(value, f, ensure_ascii=False, indent=2)
    f.write('\n')
print(json.dumps({**{k:v for k,v in value.items() if k != 'seals'}, 'seals':[{**{k:v for k,v in x.items() if k!='fields'}, 'fields':[{k:v for k,v in y.items() if k!='records'} for y in x['fields']]} for x in checks]}, ensure_ascii=False))
