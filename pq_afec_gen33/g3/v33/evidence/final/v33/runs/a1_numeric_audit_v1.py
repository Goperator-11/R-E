import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
import collections
import hashlib
import json
import math
import statistics as st
root = Path(r'C:\dev\pq_afec_gen33')
sys.path.insert(0, str(root))
from padfec import policy, quantum
r = Path(r'C:\dev\codex_handoff\v33\runs')
g2 = Path(r'C:\dev\pq_afec\experiments\results')
g31 = Path(r'C:\dev\pq_afec_gen31')
inputs = {}
def read(p):
    raw = p.read_bytes()
    inputs[str(p)] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)
def units(p):
    raw = p.read_bytes()
    inputs[str(p)] = hashlib.sha256(raw).hexdigest()
    data = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert len({x['fp'] for x in data}) == 1
    assert len({x['key'] for x in data}) == len(data)
    return data
decisions = read(g31 / 'experiments/results/p31_gencompare_decisions.json')
h1 = []
offsets = []
for run in ('run1', 'run2'):
    for cond in ('S_bigcert', 'S_rtt200'):
        data = units(g31 / f'experiments/state/p31_{run}_{cond}_units.jsonl')
        strata = collections.defaultdict(lambda: collections.defaultdict(list))
        sizes = collections.defaultdict(list)
        for unit in data:
            value = unit['val']
            for segment in value['segments']:
                if segment['arm'] not in ('g2auto', 'g3auto'): continue
                assert all(row['ok'] for row in segment['rows'])
                strata[value['stratum']][segment['arm']].append(st.mean(row['ms'] for row in segment['rows']))
                der = value['servers'][segment['slot']]['cert_der']
                for row in segment['rows']:
                    sizes[segment['arm']].append(row['server_bytes'] - der)
        means = {arm:st.mean(st.mean(arms[arm]) for arms in strata.values()) for arm in ('g2auto', 'g3auto')}
        delta = means['g2auto'] - means['g3auto']
        stored = next(x for x in decisions['H1'][run]['tests'] if x['cond'] == cond)
        assert abs(delta - stored['est']) < 1e-9, (run, cond, delta, stored['est'])
        h1.append(dict(run=run, condition=cond, unit_count=len(data), means_ms=means, difference_ms=delta, stored_difference_ms=stored['est'], stored_interval={k:stored[k] for k in stored if 'lo' in k or 'hi' in k}))
        for arm, values in sizes.items():
            offsets.append(dict(run=run, condition=cond, arm=arm, count=len(values), min_B=min(values), median_B=st.median(values), max_B=max(values), definition='recorded row.server_bytes minus actual unit.servers[slot].cert_der; includes recorded transport accounting, not isolated TLS overhead'))
p3 = read(g2 / 'p3_effect.json')
drift = []
for row in p3['runs']:
    if row['loss'] != 0: continue
    y = row['samples']; n = len(y); q = n // 4; center = (n-1)/2; avg = st.mean(y)
    slope = sum((i-center)*(v-avg) for i,v in enumerate(y)) / sum((i-center)**2 for i in range(n))
    drift.append({**{k:row[k] for k in ('group','arm','m','n','p50')}, 'quartile_difference_ms': st.median(y[-q:])-st.median(y[:q]), 'linear_change_ms':slope*n})
p18 = read(g2 / 'p18_mmax.json')
p17 = read(g2 / 'p17_adaptive_value.json')
p15 = read(g2 / 'p15_v2policy.json')
model = []
for m in (1,2,3,4):
    c = quantum._candidate('parity',m,0,2*(1280-51)-10,1280,51,16,4032,None,2560,quantum.bin_index(2560),quantum.P_SERVER,k_floor=2,s0_base=policy.S0_BASE_MLKEM,c_pkt=policy.C_PKT_POLICY_DEFAULT,parity_bytes=policy.parity_datagram_bytes)
    model.append(policy.cost_of_v2(c,1280,50.0,0.15,3.0,None,0.0,k0=2)['j_ms'])
assert abs(model[1]-model[3]-p18['verdict'][1]['pred_gain_m2_to_m4']) < 1e-10
rounds = [policy.expected_rounds(2,m,0.15,3.0) for m in (1,2,3,4)]
def choice(p):
    x = policy.decide_v2(C=1100,cert_bytes=4032,rtt_ms=50,p=p,burst=1,s0=None,W=1280,s0_base=policy.S0_BASE_X25519,c_pkt=policy.C_PKT_POLICY_DEFAULT,uplink_mbps=0,max_ips=policy.QUICGO_MAX_IPS)['choice']
    return x['mode'],x['delta_per_dgram'],x['m']
lo,hi = 0.0,0.05
base = choice(1e-12)
for _ in range(60):
    mid = (lo+hi)/2
    if choice(mid) == base: lo = mid
    else: hi = mid
pad_rows = []
for row in p15['auto']:
    if row['cert'] == 4032 and row['loss'] == 0:
        for x in row['rounds']:
            pad_rows.append({k:x[k] for k in ('round','n','ips_used','m_used','added_bytes_mean','p_est')})
q17 = dict(rounded_rates=[0.12,0.104], assumed_equal_n_for_z079=(0.79/0.016)**2*2*0.112*0.888, z_by_equal_n={str(n):0.016/math.sqrt(2*0.112*0.888/n) for n in (485,2000,20000)}, note='Rounded percentages only; original valid denominators unavailable, not a recovered historical test')
cert = read(r / 'A1_certificate_v1/sizes.json')
ecdsa_sig = next(x['certificate_verify_signature_B'] for x in cert['algorithms'] if x['algorithm']=='ECDSA-P256')
mapping = []
for x in cert['algorithms']:
    equivalent = x['leaf_intermediate_der_B']+5+x['certificate_verify_signature_B']-ecdsa_sig
    mapping.append(dict(algorithm=x['algorithm'], leaf_intermediate_DER_B=x['leaf_intermediate_der_B'], measured_CV_signature_B=x['certificate_verify_signature_B'], synthetic_ECDSA_certsize_equivalent_B=equivalent, formula='sum(two DER)+one extra CertificateEntry overhead5+(measured CV signature-ECDSA signature72)', server_bytes_if_s0_1724_B=equivalent+1724, kind='calculated mapping with fixed historical s0 scenario, not a QUIC measurement'))
out = dict(status='PASS', kind='read_only_historical_reanalysis_and_explicit_calculation', H1=h1, original_decisions={k:decisions[k] for k in ('H2','H3','H4')}, observed_non_DER_offsets=offsets, p3_drift=drift, p3_lossless_comparisons=[x for x in p3['comparisons'] if x.get('loss')==0], p18=dict(verdict=p18['verdict'],checks=p18['checks'],hct_scope=p18['hct_scope'],trial_coverage=p18['trial_coverage'],model_recalculated=model), p17=[{k:x[k] for k in ('cond','gain_ms','oracle_gain_ms','oracle_gain_ci95_half_ms','oracle_verdict')} for x in p17['gain']], p15_pad_rounds=pad_rows, expected_rounds=rounds, pad_threshold_p=hi, q17=q17, gemodel_stationary=0.05/(0.05+0.5), certificate_mapping=mapping, inputs_sha256=inputs, model_sources_sha256={str(root/name):hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('padfec/policy.py','padfec/quantum.py','afec/channel.py')})
for path, expected in inputs.items(): assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
with (r/'A1_numeric_audit_v1.json').open('x',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(dict(status='PASS',H1=[x['difference_ms'] for x in h1],rounds=rounds,pad_threshold=hi,drift_range=[min(x['linear_change_ms'] for x in drift),max(x['linear_change_ms'] for x in drift)],p15=pad_rows,certificate_mapping=mapping),ensure_ascii=False))
