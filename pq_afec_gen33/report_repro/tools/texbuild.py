import json, os, sys, time, urllib.request, urllib.error, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = 'tikz-figure-build'


def _multipart(fields):
    b = uuid.uuid4().hex
    out = []
    for k, v in fields:
        out.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n' % (b, k)).encode('utf-8'))
        out.append(v.encode('utf-8'))
        out.append(b'\r\n')
    out.append(('--%s--\r\n' % b).encode('utf-8'))
    return b, b''.join(out)


def _texlive(main, extra):
    fields = [('filecontents[]', main), ('filename[]', 'document.tex')]
    for name, content in extra.items():
        fields += [('filecontents[]', content), ('filename[]', name)]
    fields += [('engine', 'pdflatex'), ('return', 'pdf')]
    b, body = _multipart(fields)
    req = urllib.request.Request('https://texlive.net/cgi-bin/latexcgi', data=body,
                                 headers={'Content-Type': 'multipart/form-data; boundary=' + b, 'User-Agent': UA})
    r = urllib.request.urlopen(req, timeout=180)
    d = r.read()
    return d, r.geturl()


def _ytotech(main, extra):
    res = [{'main': True, 'path': 'document.tex', 'content': main}]
    for name, content in extra.items():
        res.append({'path': name, 'content': content})
    body = json.dumps({'compiler': 'pdflatex', 'resources': res}).encode('utf-8')
    req = urllib.request.Request('https://latex.ytotech.com/builds/sync', data=body,
                                 headers={'Content-Type': 'application/json', 'User-Agent': UA})
    r = urllib.request.urlopen(req, timeout=180)
    return r.read(), 'latex.ytotech.com'


def compile_tex(tex_path, dpi=600):
    import fitz

    src = open(tex_path, encoding='utf-8').read()
    extra = {}
    sty = os.path.join(ROOT, 'figstyle.tex')
    if os.path.exists(sty):
        extra['figstyle.tex'] = open(sty, encoding='utf-8').read()
    stem = os.path.splitext(tex_path)[0]
    errs = []
    for attempt in range(3):
        for name, fn in (('texlive.net', _texlive), ('ytotech', _ytotech)):
            try:
                d, where = fn(src, extra)
            except urllib.error.HTTPError as e:
                msg = e.read()
                errs.append('%s HTTP %s %s' % (name, e.code, msg[:4000].decode('utf-8', 'replace')))
                continue
            except Exception as e:
                errs.append('%s %r' % (name, e))
                continue
            if d[:4] == b'%PDF':
                open(stem + '.pdf', 'wb').write(d)
                doc = fitz.open(stem + '.pdf')
                pg = doc[0]
                w, h = pg.rect.width / 72 * 25.4, pg.rect.height / 72 * 25.4
                pix = pg.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                pix.set_dpi(dpi, dpi)
                pix.save(stem + '.png')
                print('OK %s via %s pages=%d size=%.1fx%.1f mm png=%dx%d' % (os.path.basename(stem), name, doc.page_count, w, h, pix.width, pix.height))
                return True
            log = d.decode('utf-8', 'replace')
            open(stem + '.log', 'w', encoding='utf-8').write(log)
            lines = [l for l in log.splitlines() if l.startswith('!') or 'Error' in l or l.startswith('l.')]
            print('LATEX ERROR via %s (see %s.log)' % (name, os.path.basename(stem)))
            print('\n'.join(lines[:30]))
            return False
        time.sleep(4 + attempt * 6)
    print('SERVICE ERROR', os.path.basename(stem))
    print('\n'.join(errs[-4:]))
    return False


if __name__ == '__main__':
    ok = True
    for p in sys.argv[1:]:
        ok = compile_tex(p) and ok
    sys.exit(0 if ok else 1)
