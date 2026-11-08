import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texbuild import compile_tex, ROOT

d = json.load(open(os.path.join(ROOT, 'data', 'fig3.json'), encoding='utf-8'))
x = sorted((r[0], r[2]) for r in d['sweep'] if r[1] == 'X25519')
h = sorted((r[0], r[2]) for r in d['sweep'] if r[1] == 'X25519MLKEM768')
ov = next(r for r in d['overview'] if r[0] == 4032)
rtt = [(r[0], r[1] - r[2]) for r in d['rtt']]
dx, dh = dict(x), dict(h)


def coords(pts):
    return ' '.join('(%g,%g)' % p for p in pts)


def seg(pts, a, b):
    return [p for p in pts if a <= p[0] <= b]


def riser(values, a, b):
    m = (a + b) / 2
    return [(m, values[a]), (m, values[b])]


lines = []
for r, g in rtt:
    if r < 20:
        lines.append(r'\node[font=\smallsize,anchor=west,inner sep=1.5pt] at (axis cs:%g,%g) {%.1f\%%};' % (r + 24, 20, 100 * g / r))
    elif r == 50:
        lines.append(r'\node[font=\smallsize,anchor=north west,inner sep=1.5pt] at (axis cs:%g,%g) {%.1f\%%};' % (r + 4, g + 3, 100 * g / r))
    else:
        lines.append(r'\node[font=\smallsize,anchor=north west,inner sep=1.5pt] at (axis cs:%g,%g) {%.1f\%%};' % (r + 4, g - 2, 100 * g / r))
pct = '\n'.join(lines)

XAX = r'''\addplot[x25519,forget plot] coordinates {%s};
\addplot[x25519,forget plot] coordinates {%s};
\addplot[x25519,forget plot] coordinates {%s};
\addplot[x25519,only marks,forget plot] coordinates {(%g,%g)};
\addplot[ink,line width=0.5pt,densely dotted,forget plot] coordinates {%s};
\addplot[ink,line width=0.5pt,densely dotted,forget plot] coordinates {%s};
''' % (coords(seg(x, 0, 3300)), coords(seg(x, 3400, 3500)), coords(seg(x, 4800, 99999)), ov[0], ov[1],
       coords(riser(dx, 3300, 3400)), coords([(3500, dx[3500]), (ov[0], ov[1]), (4800, dx[4800])]))
HAX = r'''\addplot[hybrid,forget plot] coordinates {%s};
\addplot[hybrid,forget plot] coordinates {%s};
\addplot[hybrid,only marks,forget plot] coordinates {(6000,%g)};
\addplot[hybrid,only marks,forget plot] coordinates {(%g,%g)};
\addplot[accent,line width=0.5pt,densely dotted,forget plot] coordinates {%s};
\addplot[accent,line width=0.5pt,densely dotted,forget plot] coordinates {%s};
''' % (coords(seg(h, 0, 3500)), coords(seg(h, 4800, 5900)), dh[6000], ov[0], ov[2],
       coords(riser(dh, 5900, 6000)), coords([(3500, dh[3500]), (ov[0], ov[2]), (4800, dh[4800])]))

tex = r'''\documentclass[border={1.5mm 0.6mm}]{standalone}
\input{figstyle.tex}
\begin{document}
\figsize
\begin{tikzpicture}
\path (-13mm,-13.2mm) rectangle (137mm,33.8mm);
\begin{axis}[name=A,at={(0,0)},anchor=south west,scale only axis,width=87mm,height=33mm,
  xmin=2800,xmax=6200,ymin=40,ymax=120,xtick={3000,3500,...,6000},ytick={40,60,...,120},
  xlabel={Server certificate size (B)},ylabel={Median HCT (ms)}]
%XAX%
%HAX%
\node[font=\smallsize,anchor=south] at (axis cs:4650,107) {X25519};
\node[font=\smallsize,anchor=north] at (axis cs:4650,53.5) {X25519MLKEM768};
\draw[{Latex[length=3pt,width=2pt]}-{Latex[length=3pt,width=2pt]},line width=0.4pt,ink] (axis cs:4650,58) -- (axis cs:4650,102.5);
\node[font=\smallsize,anchor=west] at (axis cs:4670,80) {gap $\approx$ 1 RTT};
\end{axis}
\node[anchor=north] at ($(A.south)+(0,-8.2mm)$) {\panel{a}};
\begin{axis}[name=B,at={(103mm,0)},anchor=south west,scale only axis,width=33mm,height=33mm,
  xmin=0,xmax=270,ymin=0,ymax=270,xtick={0,50,...,250},ytick={0,50,...,250},
  xlabel={RTT (ms)},ylabel={HCT gap (ms)}]
\addplot[midgray,line width=0.45pt,dashed,forget plot] coordinates {(0,0)(270,270)};
\addplot[x25519,only marks,forget plot] coordinates {%RTT%};
%PCT%
\node[font=\smallsize,rotate=45,anchor=south] at (axis cs:112,116) {gap $=$ RTT};
\end{axis}
\node[anchor=north] at ($(B.south)+(0,-8.2mm)$) {\panel{b}};
\pgfresetboundingbox
\path (-13mm,-13.2mm) rectangle (137mm,33.8mm);
\end{tikzpicture}
\end{document}
'''
tex = tex.replace('%XAX%', XAX).replace('%HAX%', HAX).replace('%RTT%', coords(rtt)).replace('%PCT%', pct)
p = os.path.join(ROOT, 'fig3_threshold.tex')
open(p, 'w', encoding='utf-8', newline='\n').write(tex)
sys.exit(0 if '--no-compile' in sys.argv[1:] or compile_tex(p) else 1)
