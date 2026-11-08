import sys
sys.dont_write_bytecode = True
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zlib

p = argparse.ArgumentParser()
p.add_argument('--dry-run', action='store_true')
args = p.parse_args()
public = Path('/mnt/c/dev/codex_handoff/v33/runs/A1_certificate_v1')
private = Path.home() / 'v33_runs/A1_certificate_v1/private'
algorithms = [('ML-DSA-44', 2420), ('ML-DSA-65', 3309), ('EC', None)]
log = []
def run(*cmd):
    result = subprocess.run(list(cmd), capture_output=True, text=True)
    log.append(dict(command=list(cmd), exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
    if result.returncode:
        raise RuntimeError(json.dumps(log[-1]))
    return result.stdout
version = run('openssl', 'version', '-a')
available = run('openssl', 'list', '-signature-algorithms')
assert 'ML-DSA-44' in available and 'ML-DSA-65' in available
if args.dry_run:
    print(json.dumps(dict(status='PASS', mode='dry_run', public=str(public), private=str(private), algorithms=[a for a,_ in algorithms], version=version)))
    raise SystemExit(0)
public.mkdir(parents=True, exist_ok=False)
private.mkdir(parents=True, exist_ok=False)
os.chmod(private, 0o700)
os.umask(0o077)
rows = []
def u24(n): return n.to_bytes(3, 'big')
try:
    for algo, expected_signature in algorithms:
        name = 'ECDSA-P256' if algo == 'EC' else algo
        out = public / name
        out.mkdir()
        secret = private / name
        secret.mkdir()
        ext = out / 'extensions.cnf'
        ext.write_text('[ca]\nbasicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n[leaf]\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:padfec.example\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
        for role in ('root', 'intermediate', 'leaf'):
            key = secret / (role + '.key')
            command = ['openssl', 'genpkey', '-algorithm', algo, '-out', str(key)]
            if algo == 'EC': command += ['-pkeyopt', 'ec_paramgen_curve:P-256']
            run(*command)
            csr = out / (role + '.csr')
            run('openssl', 'req', '-new', '-key', str(key), '-subj', '/CN=PADFEC A1 ' + name + ' ' + role, '-out', str(csr))
            cert = out / (role + '.pem')
            if role == 'root':
                run('openssl', 'req', '-new', '-x509', '-key', str(key), '-subj', '/CN=PADFEC A1 ' + name + ' root', '-set_serial', '1', '-days', '365', '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:1', '-addext', 'keyUsage=critical,keyCertSign,cRLSign', '-out', str(cert))
            else:
                issuer = 'root' if role == 'intermediate' else 'intermediate'
                run('openssl', 'x509', '-req', '-in', str(csr), '-CA', str(out / (issuer + '.pem')), '-CAkey', str(secret / (issuer + '.key')), '-set_serial', '2' if role == 'intermediate' else '3', '-days', '365', '-extfile', str(ext), '-extensions', 'ca' if role == 'intermediate' else 'leaf', '-out', str(cert))
            run('openssl', 'x509', '-in', str(cert), '-outform', 'DER', '-out', str(out / (role + '.der')))
        verify = run('openssl', 'verify', '-CAfile', str(out / 'root.pem'), '-untrusted', str(out / 'intermediate.pem'), str(out / 'leaf.pem'))
        payload = b' ' * 64 + b'TLS 1.3, server CertificateVerify' + b'\0' + hashlib.sha256(b'PADFEC A1 synthetic transcript').digest()
        (out / 'certificate_verify_input.bin').write_bytes(payload)
        sign = ['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(secret / 'leaf.key'), '-in', str(out / 'certificate_verify_input.bin'), '-out', str(out / 'certificate_verify_signature.bin')]
        if algo == 'EC': sign += ['-digest', 'sha256']
        run(*sign)
        run('openssl', 'pkey', '-in', str(secret / 'leaf.key'), '-pubout', '-out', str(out / 'leaf_public.pem'))
        verify_sign = ['openssl', 'pkeyutl', '-verify', '-rawin', '-pubin', '-inkey', str(out / 'leaf_public.pem'), '-in', str(out / 'certificate_verify_input.bin'), '-sigfile', str(out / 'certificate_verify_signature.bin')]
        if algo == 'EC': verify_sign += ['-digest', 'sha256']
        signature_verify = run(*verify_sign)
        sizes = {role:(out / (role + '.der')).stat().st_size for role in ('root', 'intermediate', 'leaf')}
        chain = [ (out / (role + '.der')).read_bytes() for role in ('leaf', 'intermediate') ]
        entries = b''.join(u24(len(cert)) + cert + b'\0\0' for cert in chain)
        body = b'\0' + u24(len(entries)) + entries
        certificate = b'\x0b' + u24(len(body)) + body
        (out / 'tls_certificate_message.bin').write_bytes(certificate)
        compressed = zlib.compress(body, 9)
        assert zlib.decompress(compressed) == body
        (out / 'certificate_body.zlib').write_bytes(compressed)
        signature = (out / 'certificate_verify_signature.bin').stat().st_size
        if expected_signature is not None: assert signature == expected_signature
        rows.append(dict(algorithm=name, certificate_der_B=sizes, leaf_intermediate_der_B=sum(sizes[x] for x in ('leaf', 'intermediate')), three_certificate_der_B=sum(sizes.values()), certificate_message_B=len(certificate), certificate_verify_signature_B=signature, certificate_verify_message_B=signature+8, certificate_and_verify_messages_B=len(certificate)+signature+8, zlib_compressed_certificate_message_B=12+len(compressed), chain_verified=verify.strip(), signature_verified=signature_verify.strip(), root_transmitted=False, ocsp_sct_added=False))
    files = [dict(path=p.relative_to(public).as_posix(), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(public.rglob('*')) if p.is_file()]
    result = dict(status='PASS', kind='generated_artifact_byte_measurement_no_network_handshake', recorded_utc=dt.datetime.now(dt.timezone.utc).isoformat(), openssl=version, algorithms=rows, private_keys_directory=str(private), private_keys_published=False, synthetic_tls_transcript=True, zlib_note='RFC8879 framing with algorithm1; computed bytes only, no negotiated transport', files=files)
    (public / 'sizes.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(status='PASS', algorithms=rows)))
finally:
    (public / 'commands.json').write_text(json.dumps(log, ensure_ascii=False, indent=2)+'\n')
