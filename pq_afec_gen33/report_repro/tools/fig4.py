import json, math, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texbuild import compile_tex, ROOT

d = json.load(open(os.path.join(ROOT, 'data', 'fig4.json'), encoding='utf-8'))
P, C, S0 = d['P'], d['c'], d['s0']
X, H = 'x25519', 'X25519MLKEM768'
STUB = 60


def coords(pts):
    return ' '.join('(%.2f,%.2f)' % p for p in pts)


def pts(rows, g):
    return sorted((r['B'], (r['lo'] + r['hi']) / 2) for r in rows if r['group'] == g)


def model(n, g):
    return n * P - S0[g] - n * C


def treads(g):
    arms = [r['B'] for r in d['padding_arms'] + d['parity_arms'] if r['group'] == g]
    seen = set(math.ceil(3 * b / P) for b in arms)
    a, b = min(arms) - STUB, max(arms) + STUB
    n = math.ceil(3 * a / P)
    out = []
    left = a
    while True:
        edge = n * P / 3
        right = min(edge, b)
        out.append((n, left, right, n in seen))
        if edge >= b:
            break
        left = edge
        n += 1
    return out


def stair(g, color):
    lines = []
    tr = treads(g)
    for i, (n, a, b, meas) in enumerate(tr):
        style = 'solid' if meas else 'densely dotted'
        lines.append(r'\addplot[%s,line width=0.4pt,%s,forget plot] coordinates {(%.2f,%.2f)(%.2f,%.2f)};' % (color, style, a, model(n, g), b, model(n, g)))
        if i + 1 < len(tr):
            nx = tr[i + 1]
            style2 = 'solid' if (meas and nx[3]) else 'densely dotted'
            lines.append(r'\addplot[%s,line width=0.4pt,%s,forget plot] coordinates {(%.2f,%.2f)(%.2f,%.2f)};' % (color, style2, b, model(n, g), b, model(nx[0], g)))
    return '\n'.join(lines)


def cliff(g):
    return sorted((r['W'], r['p50']) for r in d['cliff'] if r['group'] == g)


for r in d['padding_arms'] + d['parity_arms']:
    n = math.ceil(3 * r['B'] / P)
    t = model(n, r['group'])
    assert r['lo'] <= t <= r['hi'], r

cx, ch = cliff(X), cliff(H)
ws = sorted(set(w for w, _ in cx + ch))
idx = {w: i for i, w in enumerate(ws)}
dcx, dch = dict(cx), dict(ch)
drop_x, drop_h = dcx[1281] - dcx[1280], dch[1281] - dch[1280]
print('step X %.3f H %.3f' % (drop_x, drop_h))
OFF = 0.09
mid = idx[1280] + 0.5
step = [(idx[1280] - OFF, dcx[1280]), (mid, dcx[1280]), (mid, dcx[1281]), (idx[1281] - OFF, dcx[1281])]
ox, oh = pts(d['parity_arms'], X), pts(d['parity_arms'], H)

tex = r'''\documentclass[border={1.5mm 0.6mm}]{standalone}
\input{figstyle.tex}
\begin{document}
\figsize
\begin{tikzpicture}
\path (-13mm,-13.2mm) rectangle (137mm,34.8mm);
\begin{axis}[name=A,at={(0,0)},anchor=south west,scale only axis,width=66mm,height=34mm,
  xmin=1000,xmax=5500,ymin=2000,ymax=16000,xtick={1000,2000,...,5000},ytick={2000,6000,...,14000},
  xticklabel shift=1pt,
  xlabel={Bytes received by the server, $B$},ylabel={2-RTT boundary (B)}]
%SX%
%SH%
\addplot[x25519,only marks,forget plot] coordinates {%PX%};
\addplot[hybrid,only marks,forget plot] coordinates {%PH%};
\addplot[x25519open,forget plot] coordinates {%OX%};
\addplot[hybridopen,forget plot] coordinates {%OH%};
\node[font=\smallsize,anchor=south east,inner sep=1pt] at (axis cs:%OX1X%,%OX1Y%) {$m=1$};
\node[font=\smallsize,anchor=south east,inner sep=1pt] at (axis cs:%OX2X%,%OX2Y%) {$m=2$};
\node[font=\smallsize,anchor=north west,inner sep=1pt] at (axis cs:%OH1X%,%OH1Y%) {$m=1$};
\node[font=\smallsize,anchor=south east,inner sep=1pt] at (axis cs:%OH2X%,%OH2Y%) {$m=2$};
\node[font=\smallsize,anchor=south east,inner sep=1pt] at (axis cs:2090,6000) {X25519};
\node[font=\smallsize,anchor=north west,inner sep=1pt] at (axis cs:3080,8100) {X25519MLKEM768};
\addplot[x25519,only marks,forget plot] coordinates {(3760,5700)};
\addplot[hybrid,only marks,forget plot] coordinates {(3890,5700)};
\node[font=\smallsize,anchor=west,inner sep=1pt] at (axis cs:3990,5700) {padding arm};
\addplot[x25519open,forget plot] coordinates {(3760,4300)};
\addplot[hybridopen,forget plot] coordinates {(3890,4300)};
\node[font=\smallsize,anchor=west,inner sep=1pt] at (axis cs:3990,4300) {parity arm};
\addplot[ink,line width=0.4pt,forget plot] coordinates {(3690,2900)(3960,2900)};
\node[font=\smallsize,anchor=west,inner sep=1pt] at (axis cs:3990,2900) {model, Eq. (1)};
\end{axis}
\node[anchor=north] at ($(A.south)+(0,-8.2mm)$) {\panel{a}};
\begin{axis}[name=B,at={(80mm,0)},anchor=south west,scale only axis,width=56mm,height=34mm,
  xmin=-0.5,xmax=%XMAX%,ymin=40,ymax=120,xtick={%XT%},xticklabels={%XL%},xtick pos=bottom,ytick={40,60,...,120},
  xticklabel shift=1pt,
  xlabel={Client Initial size $W$ (B), not to scale},ylabel={Median HCT (ms)}]
\addplot[ink,line width=0.45pt,densely dotted,forget plot] coordinates {%CS%};
\addplot[x25519,only marks,forget plot] coordinates {%CX%};
\addplot[hybrid,only marks,forget plot] coordinates {%CH%};
\node[font=\smallsize,anchor=west,inner sep=1pt] at (axis cs:%MID%,80) {+1 B: $-51$ ms};
\node[font=\smallsize,inner sep=1pt] at (axis cs:0.5,97) {2 RTT};
\node[font=\smallsize,inner sep=1pt] at (axis cs:4,61) {1 RTT};
\addplot[x25519,only marks,forget plot] coordinates {(3.3,113.5)};
\node[font=\smallsize,anchor=west,inner sep=1pt] at (axis cs:3.48,113.5) {X25519};
\addplot[hybrid,only marks,forget plot] coordinates {(3.3,105.5)};
\node[font=\smallsize,anchor=west,inner sep=1pt] at (axis cs:3.48,105.5) {X25519MLKEM768};
\end{axis}
\node[anchor=north] at ($(B.south)+(0,-8.2mm)$) {\panel{b}};
\pgfresetboundingbox
\path (-13mm,-13.2mm) rectangle (137mm,34.8mm);
\end{tikzpicture}
\end{document}
'''
rep = {
    '%SX%': stair(X, 'ink'), '%SH%': stair(H, 'accent'),
    '%PX%': coords(pts(d['padding_arms'], X)), '%PH%': coords(pts(d['padding_arms'], H)),
    '%OX%': coords(ox), '%OH%': coords(oh),
    '%OX1X%': '%g' % (ox[0][0] - 45), '%OX1Y%': '%g' % (ox[0][1] + 190),
    '%OX2X%': '%g' % (ox[1][0] - 45), '%OX2Y%': '%g' % (ox[1][1] + 190),
    '%OH1X%': '%g' % (oh[0][0] + 45), '%OH1Y%': '%g' % (oh[0][1] - 190),
    '%OH2X%': '%g' % (oh[1][0] - 45), '%OH2Y%': '%g' % (oh[1][1] + 190),
    '%XMAX%': '%g' % (len(ws) - 0.5),
    '%XT%': ','.join(str(i) for i in range(len(ws))),
    '%XL%': ','.join('{%s}' % format(w, ',').replace(',', r'\mbox{,}') for w in ws),
    '%CS%': coords(step),
    '%CX%': coords([(idx[w] - OFF, v) for w, v in cx]),
    '%CH%': coords([(idx[w] + OFF, v) for w, v in ch]),
    '%MID%': '%g' % (mid + 0.08),
}
for k, v in rep.items():
    tex = tex.replace(k, v)
p = os.path.join(ROOT, 'fig4_staircase_cliff.tex')
open(p, 'w', encoding='utf-8', newline='\n').write(tex)
sys.exit(0 if '--no-compile' in sys.argv[1:] or compile_tex(p) else 1)
