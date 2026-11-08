import sys, os, runpy, json, struct
sys.stdout.reconfigure(encoding='utf-8')
tools = sys.argv[1]
out_hwp = sys.argv[2]
label = sys.argv[3] if len(sys.argv) > 3 else 'run'
os.chdir(tools)
sys.path.insert(0, tools)
import engine as E
orig = E.recalc_table
rec = []
def wrap(doc, R, tag, ctrl, extra_min=None):
    r = orig(doc, R, tag, ctrl, extra_min)
    rec.append(list(r))
    return r
E.recalc_table = wrap
sys.argv = ['build_report.py', out_hwp]
stdout = sys.stdout
class Null:
    def write(self, *_):
        pass
    def flush(self):
        pass
sys.stdout = Null()
g = runpy.run_path(os.path.join(tools, 'build_report.py'), run_name='__main__')
sys.stdout = stdout
layout = g['layout']
doc = g['doc']
USABLE = E.USABLE_H
title_h = sum(rec[0])
head = g['head']
PS_BODY = g['PS_BODY']
vals = doc.ps_vals(PS_BODY)
ls = vals[6]
size = doc.cs_size(3)
pitch = size * ls / 100.0
ref_ps = doc.ps_vals(g['PS_REF'])
ref_size = doc.cs_size(g['CS_REF'])
ref_pitch = ref_size * ref_ps[6] / 100.0
print(label, 'title_table', title_h, 'head', round(head), 'pitch', pitch, 'ref_pitch', ref_pitch, 'usable', USABLE)
y = head + title_h + 400
page = 1
pages = []
cur = []
def place(kind, h, name, splittable, unit):
    global y, page, cur
    if splittable:
        lines = int(h // unit)
        extra = h - lines * unit
        while lines > 0:
            fit = int((USABLE - y) // unit)
            if fit <= 0:
                pages.append((page, cur, y))
                page += 1
                y = 0
                cur = []
                continue
            take = min(fit, lines)
            y += take * unit
            cur.append((kind, name, take))
            lines -= take
        y += extra
    else:
        if y + h > USABLE:
            pages.append((page, cur, y))
            page += 1
            y = 0
            cur = []
        y += h
        cur.append((kind, name, round(h)))
i = 0
n = len(layout)
while i < n:
    kind, h, name = layout[i]
    if kind in ('h1', 'h2'):
        need = h
        j = i + 1
        while j < n and layout[j][0] in ('h1', 'h2'):
            need += layout[j][1]
            j += 1
        if j < n:
            k2, h2, _ = layout[j]
            need += (2 * pitch) if k2 in ('p', 'ref') else h2
        if y + need > USABLE:
            pages.append((page, cur, y))
            page += 1
            y = 0
            cur = []
        y += h
        cur.append((kind, name, round(h)))
    elif kind == 'p':
        place(kind, h, name, True, pitch)
    elif kind == 'ref':
        place(kind, h, name, True, ref_pitch)
    else:
        place(kind, h, name, False, 0)
    i += 1
pages.append((page, cur, y))
for p, c, yy in pages:
    first = c[0] if c else None
    last = c[-1] if c else None
    print('p%02d(doc %d) fill %.3f free %.1f mm blocks %d | last %s:%s' % (p, p + 4, yy / USABLE, (USABLE - yy) / 283.465, len(c), last[0] if last else '', str(last[1])[:24] if last else ''))
tot = sum(h for _, h, _ in layout)
print('layout_sum_pages', round(tot / USABLE, 3), 'by_kind', {k: round(sum(h for kk, h, _ in layout if kk == k) / USABLE, 3) for k in ('p', 'h1', 'h2', 'eq', 'table', 'fig', 'ref', 'notice')})
print('summary rows', rec[2], 'sum', sum(rec[2]), 'pages', round((sum(rec[2]) + 2500) / USABLE, 3))
print('process pages', g['rowh'], round((sum(g['rowh']) + 3000) / USABLE, 3))
print('estimated_pages', len(pages), 'last_free_mm', round((USABLE - pages[-1][2]) / 283.465, 1))
