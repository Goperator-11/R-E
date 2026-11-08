import difflib
from pathlib import Path
import re
import struct
import sys
import zlib

import olefile

sys.stdout.reconfigure(encoding='utf-8')
CTRL = (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)
FORBIDDEN = (
    'v3.3이 v3.2보다 낫다', '실측으로 개선 확인', '같은 바이트가 credit과 복구를 함께 산다', '어디서나 나쁘지 않다',
    '예측이 맞는다', '적응이 이득을 냈다', 'PQ handshake의 증폭 병목을 우리가 밝혔다', 'PTO 12.0% 대 10.4%, z=0.79',
    '무손실을 배워 parity를 끈다', '측정 대기', 'pending:', '제출 전 검색 기록을 갱신',
)
INTERNAL = re.compile(r'(?<![A-Za-z0-9_])(?:L1|L3|record_only|RT-\d+|F\d\d|BL-\d+|c1_seen|X1|X6|X9|D\d\d)(?![A-Za-z0-9_])')


def parse(data):
    out = []
    p = 0
    while p < len(data):
        h = struct.unpack('<I', data[p:p + 4])[0]
        t = h & 0x3FF
        l = (h >> 10) & 0x3FF
        s = (h >> 20) & 0xFFF
        p += 4
        if s == 0xFFF:
            s = struct.unpack('<I', data[p:p + 4])[0]
            p += 4
        out.append((t, l, data[p:p + s]))
        p += s
    return out


def para_text(pl):
    k = 0
    chars = []
    while k + 1 < len(pl):
        c = struct.unpack('<H', pl[k:k + 2])[0]
        if c in CTRL:
            k += 16
            continue
        if c >= 32:
            chars.append(chr(c))
        k += 2
    return ''.join(chars)


def load(path):
    o = olefile.OleFileIO(path)
    streams = {'/'.join(e): o.openstream(e).read() for e in o.listdir()}
    o.close()
    recs = parse(zlib.decompress(streams['BodyText/Section0'], -15))
    return streams, recs, [para_text(r[2]) for r in recs if r[0] == 67]


def main(base, new, errata):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_errata import read_rows
    rows = {row["id"]: (row["old"], row["new"]) for row in read_rows(Path(errata)) if row.get("적용") == "apply"}
    bs, br, bt = load(base)
    ns, nr, nt = load(new)
    errors = []
    same = [k for k in bs if k in ns and bs[k] == ns[k]]
    diff = [k for k in bs if k not in ns or bs[k] != ns[k]]
    print('streams same', len(same), 'different', diff)
    if set(diff) - {'BodyText/Section0', 'DocInfo', 'PrvText'}:
        errors.append('unexpected stream change')
    text = '\n'.join(nt)
    for rid, (old, newtext) in rows.items():
        for part in newtext.split('\n'):
            if part and part not in text:
                errors.append(f'{rid}: new missing')
        if old and old in text and old not in newtext:
            errors.append(f'{rid}: old still present')
    for phrase in FORBIDDEN:
        if phrase in text:
            errors.append('forbidden present: ' + phrase)
    for mark, n in (('【입력 필요', 2), ('【확인 필요', 1), ('PaperBanana', 2)):
        c = text.count(mark)
        print('marker', mark, c)
        if c != n:
            errors.append(f'marker {mark} count {c}, expected {n}')
    for m in ('—', '–'):
        if m in text:
            errors.append('dash present ' + m)
    hits = sorted(set(INTERNAL.findall(text)))
    print('internal id tokens', hits)
    for label, recs in (('base', br), ('new', nr)):
        tbl = sum(1 for r in recs if r[0] == 71 and r[2][:4] == b' lbt')
        pic = sum(1 for r in recs if r[0] == 85)
        print(label, 'records', len(recs), 'tables', tbl, 'pictures', pic, 'paras', sum(1 for r in recs if r[0] == 66))
    bad_bit29 = 0
    for i, (t, l, p) in enumerate(nr):
        if t == 71 and len(p) >= 8 and p[:4] in (b' lbt', b' osg'):
            attr = struct.unpack('<I', p[4:8])[0]
            has = bool(attr & 0x20000000)
            nxt = nr[i + 1][0] == 72
            if has != nxt:
                bad_bit29 += 1
    print('bit29 mismatch', bad_bit29)
    if bad_bit29:
        errors.append('bit29 mismatch')
    sm = difflib.SequenceMatcher(a=bt, b=nt, autojunk=False)
    changed = [op for op in sm.get_opcodes() if op[0] != 'equal']
    print('changed paragraph groups', len(changed), 'old paras', sum(op[2] - op[1] for op in changed), 'new paras', sum(op[4] - op[3] for op in changed))
    for e in errors:
        print('ERROR', e)
    print('PASS' if not errors else 'FAIL', len(errors))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
