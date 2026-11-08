import json, math, os, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texbuild import compile_tex, ROOT

d = json.load(open(os.path.join(ROOT, 'data', 'fig5.json'), encoding='utf-8'))
arms = {a['arm']: a for a in d['arms']}
assert d['top']['group'] == 'x25519' and d['top']['cert'] == 4032 and d['top']['rtt_ms'] == 50.0
for a in arms.values():
    assert a['n'] == 400 and len(a['ms']) == 400 and a['meta']['loss'] == 5.0 and a['meta']['ok'] == 400


def share(arm, t):
    v = arms[arm]['ms']
    return 100.0 * sum(1 for x in v if x > t) / len(v)


def half_width(arm):
    v = arms[arm]['ms']
    return 1.96 * statistics.stdev(v) / math.sqrt(len(v))


def ccdf(arm, start=None):
    v = sorted(arms[arm]['ms'])
    n = len(v)
    pts = [(start, 100.0)] if start else []
    level = 100.0
    i = 0
    while i < n:
        x = v[i]
        j = i
        while j < n and v[j] == x:
            j += 1
        pts.append((x, level))
        if j < n:
            level = 100.0 * (n - j) / n
            pts.append((x, level))
        i = j
    return pts


def coords(pts):
    return ' '.join('(%.3f,%g)' % p for p in pts)


def plus(b):
    return '0 B' if b == 0 else '+{:,} B'.format(b).replace(',', r'\mbox{,}')


def bar(arm, y):
    return '(%.3f,%d) +- (%.3f,0)' % (arms[arm]['mean'], y, half_width(arm))


for arm, t, v in (('parity', 75, 12.0), ('pad', 75, 4.25), ('combo', 75, 0.75), ('base', 75, 100.0), ('base', 150, 7.5), ('parity', 150, 0.0)):
    assert abs(share(arm, t) - v) < 1e-9, (arm, t, share(arm, t))
assert sum(1 for x in arms['base']['ms'] if x > 300) == 1

ff = {arm: arms[arm]['meta']['ff_bytes_med'] for arm in arms}
added = {arm: ff[arm] - ff['base'] for arm in arms}
assert added['base'] == 0 and added['pad'] == 1 and added['parity'] == 1326
print('half widths', {a: round(half_width(a), 3) for a in arms}, 'added', added)

tex = r'''\documentclass[border={1.5mm 0.6mm}]{standalone}
\input{figstyle.tex}
\begin{document}
\figsize
\begin{tikzpicture}
\tikzset{
  armbase/.style={midgray,line width=0.55pt,dash pattern=on 4pt off 1.5pt,line join=miter},
  armpad/.style={ink,line width=0.5pt,dash pattern=on 1.6pt off 1.2pt,line join=miter},
  armpar/.style={steel,line width=0.55pt,dash pattern=on 3.2pt off 1pt on 0.7pt off 1pt,line join=miter},
  armcombo/.style={ink,line width=0.7pt,solid,line join=miter},
  guide/.style={midgray,line width=0.35pt,dash pattern=on 1.2pt off 1.4pt},
  val/.style={font=\smallsize,inner sep=0.3pt},
}
\path (-13mm,-13.2mm) rectangle (137mm,36.1mm);
\begin{axis}[name=A,at={(0,0)},anchor=south west,scale only axis,width=78mm,height=32mm,
  xmode=log,ymode=log,xmin=40,xmax=600,ymin=0.18,ymax=160,
  xtick={50,100,200,400},ytick={1,10,100},
  minor xtick={60,70,80,90,300,500},
  minor ytick={0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,2,3,4,5,6,7,8,9,20,30,40,50,60,70,80,90},
  log ticks with fixed point,
  xlabel={HCT $t$ (ms)},ylabel={Connections slower than $t$ (\%)}]
\addplot[guide,forget plot] coordinates {(75,0.18)(75,160)};
\addplot[guide,forget plot] coordinates {(150,0.18)(150,160)};
\addplot[armbase,forget plot] coordinates {%BASE%};
\addplot[armpad,forget plot] coordinates {%PAD%};
\addplot[armpar,forget plot] coordinates {%PAR%};
\addplot[armcombo,forget plot] coordinates {%COMBO%};
\coordinate (Z1) at (axis cs:54.8,160);
\coordinate (Z2) at (axis cs:106,160);
\coordinate (Z3) at (axis cs:300,160);
\node[val,anchor=south,fill=white,align=center] at ([yshift=0.5mm]axis cs:77,12) {parity ($m=1$)\\12\%};
\node[val,anchor=south east] at ([yshift=0.4mm]axis cs:246,7.5) {7.5\%};
\node[val,anchor=north east] at ([yshift=-0.35mm]axis cs:246,4.25) {4.25\%};
\node[val,anchor=south east] at ([yshift=0.4mm]axis cs:246,0.75) {0.75\%};
\node[val,anchor=west] at ([yshift=0.3mm]axis cs:268,7.5) {none};
\node[val,anchor=west] at ([yshift=-0.3mm]axis cs:268,4.25) {padding ($\delta=1$)};
\node[val,anchor=west] at (axis cs:268,0.75) {padding + parity};
\node[val,anchor=south] at ([yshift=0.3mm]axis cs:410,0.25) {1 of 400};
\end{axis}
\node[val,anchor=base] at ([yshift=1.2mm]Z1) {1 RTT};
\node[val,anchor=base] at ([yshift=1.2mm]Z2) {2 RTT};
\node[val,anchor=base] at ([yshift=1.2mm]Z3) {PTO wait};
\node[anchor=north] at ($(A.south)+(0,-8.2mm)$) {\panel{a}};
\begin{axis}[name=B,at={(103mm,0)},anchor=south west,scale only axis,width=33mm,height=32mm,
  xmin=45,xmax=125,ymin=0.4,ymax=4.6,
  xtick={60,80,100,120},ytick={1,2,3,4},
  major y tick style={draw=none},
  yticklabels={{padding + parity\\{\smallsize %B1%}},{parity ($m=1$)\\{\smallsize %B2%}},{padding ($\delta=1$)\\{\smallsize %B3%}},{none\\{\smallsize %B4%}}},
  yticklabel style={align=right,font=\smallsize},
  xlabel={Mean HCT (ms)}]
\addplot[x25519,only marks,forget plot,
  error bars/.cd,x dir=both,x explicit,error bar style={line width=0.45pt,ink,solid},
  error mark options={rotate=90,mark size=1.3pt,line width=0.45pt,ink}]
  coordinates {%FILLED%};
\addplot[x25519open,mark size=1.05pt,forget plot,
  error bars/.cd,x dir=both,x explicit,error bar style={line width=0.45pt,ink,solid},
  error mark options={rotate=90,mark size=1.3pt,line width=0.45pt,ink}]
  coordinates {%OPEN%};
\end{axis}
\node[anchor=north] at ($(B.south)+(0,-8.2mm)$) {\panel{b}};
\pgfresetboundingbox
\path (-13mm,-13.2mm) rectangle (137mm,36.1mm);
\end{tikzpicture}
\end{document}
'''
rep = {
    '%BASE%': coords(ccdf('base', 40)),
    '%PAD%': coords(ccdf('pad')),
    '%PAR%': coords(ccdf('parity')),
    '%COMBO%': coords(ccdf('combo')),
    '%B1%': plus(added['combo']), '%B2%': plus(added['parity']),
    '%B3%': plus(added['pad']), '%B4%': plus(added['base']),
    '%FILLED%': bar('base', 4) + ' ' + bar('pad', 3),
    '%OPEN%': bar('parity', 2) + ' ' + bar('combo', 1),
}
for k, v in rep.items():
    tex = tex.replace(k, v)
p = os.path.join(ROOT, 'fig5_levers.tex')
open(p, 'w', encoding='utf-8', newline='\n').write(tex)
sys.exit(0 if '--no-compile' in sys.argv[1:] or compile_tex(p) else 1)
