import json, math, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texbuild import compile_tex, ROOT

d = json.load(open(os.path.join(ROOT, 'data', 'fig6.json'), encoding='utf-8'))
A, B = d['v30_run1'], d['v31_run1']
MARGIN = A['S_bigcert']['c']


def f(x):
    return math.copysign(math.log10(1 + abs(x)), x)


SW = r'$\leftrightarrow$'
S15 = '2' + SW + '15'
S8 = '1' + SW + '8'
UL = 'unlimited'
GROUPS = [
    ('Primary (S)', [
        ('16,000', '50', '2', S15, 'S_bigcert', 'S_bigcert'),
        ('9,000', '200', '2', S15, 'S_rtt200', 'S_rtt200'),
    ]),
    ('Carried over (D)', [
        ('9,000', '50', '2', S15, 'D_p17_mbps2', 'D_p17_mbps2'),
        ('4,032', '50', UL, '15$^{\\dagger}$', 'D_p18_burst3', 'D_p18_burst3'),
        ('9,000', '50', UL, '5', 'D_p11_9000_l5', 'D_p11_9000_l5'),
        ('4,032$^{*}$', '50', UL, '5', 'D_p15_4032_l5', 'D_p15_4032_l5'),
    ]),
    ('Held out (H)', [
        ('6,000', '80', '10', S8, 'H_h_c6000_r80_u10', None),
        ('8,000', '120', '5', S8, 'H_h_c8000_r120_u5', None),
        ('6,000', '120', '10', S8, None, 'H_h_c6000_r120_u10'),
        ('8,000', '120', '10', S8, None, 'H_h_c8000_r120_u10'),
        ('12,000', '120', '5', S8, None, 'H_h_c12000_r120_u5'),
        ('14,000', '120', '5', S8, None, 'H_h_c14000_r120_u5'),
    ]),
]

for _, rows in GROUPS:
    for r in rows:
        if r[4]:
            assert r[4] in A, r[4]
        if r[5]:
            assert r[5] in B, r[5]

drawn30 = set(r[4] for _, rows in GROUPS for r in rows if r[4])
drawn31 = set(r[5] for _, rows in GROUPS for r in rows if r[5])
print('drawn', len(drawn30), len(drawn31), 'of', len(A), len(B))
print('undrawn min lo95', min(t['lo95'] for k, t in A.items() if k not in drawn30), min(t['lo95'] for k, t in B.items() if k not in drawn31))
for k in ('H_h_c12000_r120_u5', 'H_h_c14000_r120_u5'):
    print(k, B[k]['est'], B[k]['lo95'], B[k]['hi95'])

PAD = 0.4
HEAD = 3.0
DOUBLE = 4.6
SINGLE = 2.85
SUB = 2.15
BASE_SMALL = 0.82
BASE_FIG = 0.95
X0, X1 = 37.0, 123.0
TOP_H, BOTTOM_H = 6.2, 7.6
COL_CERT, COL_RTT, COL_UP, COL_LOSS = 8.6, 14.8, 26.4, 34.0
COL_EST, COL_LO, COL_HI = 132.0, 141.0, 149.6

allv = [t[k] for t in list(A.values()) + list(B.values()) for k in ('lo95', 'hi95')]
XMIN = f(-70)
XMAX = f(max(allv) * 1.15)

total = PAD * 2
for _, rows in GROUPS:
    total += HEAD
    for r in rows:
        total += DOUBLE if (r[4] and r[5]) else SINGLE
H = round(total, 3)


def num(v):
    s = '%.1f' % abs(v)
    return ('$-$' if v < 0 and float(s) != 0 else '') + s


def text(x, y, s, anchor, font=r'\smallsize'):
    return r'\node[font=%s,anchor=%s,inner sep=0pt] at (%.3fmm,%.3fmm) {%s};' % (font, anchor, x, y, s)


def small_row(y, cert, rtt, up, loss):
    b = y - BASE_SMALL
    return [text(COL_CERT, b, cert, 'base east'), text(COL_RTT, b, rtt, 'base east'),
            text(COL_UP, b, up, 'base east'), text(COL_LOSS, b, loss, 'base east')]


def numeric(y, t):
    b = y - BASE_SMALL
    return [text(COL_EST, b, num(t['est']), 'base east'),
            text(COL_LO, b, num(t['lo95']), 'base east'),
            text(COL_HI, b, num(t['hi95']), 'base east')]


def interval(y, t):
    return r'\addplot[ink,line width=0.45pt,forget plot] coordinates {(%.4f,%.3f)(%.4f,%.3f)};' % (f(t['lo95']), y, f(t['hi95']), y)


outer, lines, marks30, marks31 = [], [], [], []
y = H - PAD
heads = {}
for title, rows in GROUPS:
    heads[title] = y - HEAD / 2
    outer.append(text(0.2, y - HEAD / 2 - BASE_FIG, title, 'base west', r'\figsize'))
    y -= HEAD
    for cert, rtt, up, loss, k30, k31 in rows:
        both = k30 and k31
        h = DOUBLE if both else SINGLE
        c = y - h / 2
        outer += small_row(c, cert, rtt, up, loss)
        y30 = c + SUB / 2 if both else c
        y31 = c - SUB / 2 if both else c
        if k30:
            t = A[k30]
            lines.append(interval(y30, t))
            marks30.append('(%.4f,%.3f)' % (f(t['est']), y30))
            outer += numeric(y30, t)
        if k31:
            t = B[k31]
            lines.append(interval(y31, t))
            marks31.append('(%.4f,%.3f)' % (f(t['est']), y31))
            outer += numeric(y31, t)
        y -= h

mlab = r'\node[font=\smallsize,anchor=east,inner sep=0pt] at (axis cs:%.4f,%.3f) {margin $-1$ ms};' % (f(MARGIN) - 0.05, heads['Carried over (D)'])
x_zero = X0 + (0 - XMIN) / (XMAX - XMIN) * (X1 - X0)


def hdr(col, s):
    return r'\node[font=\smallsize,anchor=south east,inner sep=0pt,align=right] at (%.3fmm,%.3fmm) {%s};' % (col, H + 0.9, s)


headers = [
    hdr(COL_CERT, r'Cert\\(B)'), hdr(COL_RTT, r'RTT\\(ms)'), hdr(COL_UP, r'Uplink\\(Mbps)'), hdr(COL_LOSS, r'Loss\\(\%)'),
    text(x_zero - 1.2, H + 1.3, r'$\leftarrow$ gen-2 faster', 'base east'),
    text(x_zero + 1.2, H + 1.3, r'v3 faster $\rightarrow$', 'base west'),
    hdr(COL_EST, r'$\Delta$\\(ms)'),
    r'\node[font=\smallsize,anchor=south,inner sep=0pt,align=center] at (%.3fmm,%.3fmm) {95\%% CI\\(ms)};' % ((COL_LO + COL_HI) / 2 - 3.2, H + 0.9),
]
rules = [
    r'\draw[ink,line width=0.45pt] (0.1mm,%.3fmm) -- (%.3fmm,%.3fmm);' % (H, X0 - 1.4, H),
    r'\draw[ink,line width=0.45pt] (%.3fmm,%.3fmm) -- (149.9mm,%.3fmm);' % (X1 + 1.4, H, H),
    r'\draw[ink,line width=0.45pt] (0.1mm,0) -- (%.3fmm,0);' % (X0 - 1.4),
    r'\draw[ink,line width=0.45pt] (%.3fmm,0) -- (149.9mm,0);' % (X1 + 1.4),
]
TV = [-50, -10, -1, 0, 1, 10, 50, 100]
MV = [-20, -5, -2, 2, 5, 20]
key = [
    r'\addplot[genzero,forget plot] coordinates {(%.4f,%.3f)};' % (f(9), heads['Primary (S)']),
    r'\node[font=\smallsize,anchor=west,inner sep=0pt] at (axis cs:%.4f,%.3f) {v3.0};' % (f(9) + 0.07, heads['Primary (S)']),
    r'\addplot[genone,forget plot] coordinates {(%.4f,%.3f)};' % (f(30), heads['Primary (S)']),
    r'\node[font=\smallsize,anchor=west,inner sep=0pt] at (axis cs:%.4f,%.3f) {v3.1};' % (f(30) + 0.07, heads['Primary (S)']),
]

tex = r'''\documentclass[border={1.5mm 0.6mm}]{standalone}
\input{figstyle.tex}
\pgfplotsset{
  genzero/.style={ink,only marks,mark=diamond*,mark size=1.5pt,mark options={solid,fill=ink,line width=0.2pt}},
  genone/.style={ink,only marks,mark=triangle*,mark size=1.5pt,mark options={solid,fill=white,line width=0.45pt}},
}
\begin{document}
\figsize
\begin{tikzpicture}
\path (0,-%BOTTOM%mm) rectangle (150mm,%TOP%mm);
\begin{axis}[name=A,at={(%X0%mm,0)},anchor=south west,scale only axis,width=%W%mm,height=%H%mm,
  xmin=%XMIN%,xmax=%XMAX%,ymin=0,ymax=%H%,xtick={%XT%},xticklabels={%XL%},minor xtick={%XM%},xtick pos=bottom,
  ytick=\empty,
  xlabel style={inner ysep=0pt,yshift=-0.4mm},
  xlabel={$\Delta$ = gen-2 auto $-$ v3 auto (ms), signed log scale}]
\addplot[ink,line width=0.5pt,forget plot] coordinates {(0,0)(0,%H%)};
\addplot[ink,line width=0.45pt,dash pattern=on 2pt off 1.5pt,forget plot] coordinates {(%MARGIN%,0)(%MARGIN%,%H%)};
%LINES%
\addplot[genzero,forget plot] coordinates {%M30%};
\addplot[genone,forget plot] coordinates {%M31%};
%KEY%
%MLAB%
\end{axis}
%RULES%
%HEADERS%
%OUTER%
\pgfresetboundingbox
\path (0,-%BOTTOM%mm) rectangle (150mm,%TOP%mm);
\end{tikzpicture}
\end{document}
'''
rep = {
    '%BOTTOM%': '%g' % BOTTOM_H, '%TOP%': '%.3f' % (H + TOP_H), '%X0%': '%g' % X0, '%W%': '%g' % (X1 - X0),
    '%H%': '%.3f' % H, '%XMIN%': '%.4f' % XMIN, '%XMAX%': '%.4f' % XMAX,
    '%XT%': ','.join('%.4f' % f(v) for v in TV),
    '%XL%': ','.join('{$%d$}' % v for v in TV),
    '%XM%': ','.join('%.4f' % f(v) for v in MV),
    '%MARGIN%': '%.4f' % f(MARGIN), '%LINES%': '\n'.join(lines), '%M30%': ' '.join(marks30), '%M31%': ' '.join(marks31),
    '%KEY%': '\n'.join(key), '%MLAB%': mlab, '%RULES%': '\n'.join(rules),
    '%HEADERS%': '\n'.join(headers), '%OUTER%': '\n'.join(outer),
}
for k, v in rep.items():
    tex = tex.replace(k, v)
print('frame height %.2f mm, total %.2f mm' % (H, H + TOP_H + BOTTOM_H))
p = os.path.join(ROOT, 'fig6_forest.tex')
open(p, 'w', encoding='utf-8', newline='\n').write(tex)
sys.exit(0 if '--no-compile' in sys.argv[1:] or compile_tex(p) else 1)
