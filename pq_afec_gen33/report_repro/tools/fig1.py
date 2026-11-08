import json, math, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texbuild import compile_tex, ROOT

d = json.load(open(os.path.join(ROOT, 'data', 'fig4.json'), encoding='utf-8'))
P, C, S0 = d['P'], d['c'], d['s0']['x25519']
CERT = 4032


def A(b):
    return math.ceil(3 * b / P) * P


def S(n):
    return CERT + S0 + n * C


NEED = min(n for n in range(1, 20) if n * P >= S(n))
assert NEED == 4 and A(1280) == 3840 and A(1281) == 5120

RTT, PTO = 50.0, 200.0
OW = RTT / 2
BURST = 1.2
PAR = 4.0
X0, X1, TMAX = 31.0, 149.0, 265.0
K = (X1 - X0) / TMAX
RH = 8.4
PITCH = 13.0
TOP = 4.4
AX_GAP = 2.6
BOTTOM = 8.0
H = TOP + 3 * PITCH + RH + AX_GAP + BOTTOM


def X(t):
    return X0 + K * t


def yc(i):
    return H - TOP - i * PITCH


def ys(i):
    return yc(i) - RH


out = []


def rails(i, end):
    out.append(r'\draw[rail] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(0), yc(i), X(end), yc(i)))
    out.append(r'\draw[rail] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(0), ys(i), X(end), ys(i)))
    out.append(r'\node[sml,anchor=east] at (%.3f,%.3f) {Client};' % (X(0) - 0.8, yc(i)))
    out.append(r'\node[sml,anchor=east] at (%.3f,%.3f) {Server};' % (X(0) - 0.8, ys(i)))


def to_server(i, t, label=None, style='msg', side='above'):
    node = ''
    if label:
        node = r' node[sml,text=ink,sloped,pos=0.56,%s=0.2mm,inner sep=0.2mm] {%s}' % (side, label)
    out.append(r'\draw[%s] (%.3f,%.3f) --%s (%.3f,%.3f);' % (style, X(t), yc(i), node, X(t + OW), ys(i)))


def to_client(i, t, n, label=None):
    for j in range(n):
        tt = t + j * BURST
        node = ''
        if label and j == 0:
            node = r' node[sml,text=ink,sloped,pos=0.42,above=0.2mm,inner sep=0.2mm] {%s}' % label
        style = 'msg' if j == n - 1 else 'msgplain'
        out.append(r'\draw[%s] (%.3f,%.3f) --%s (%.3f,%.3f);' % (style, X(tt), ys(i), node, X(tt + OW), yc(i)))
    return t + (n - 1) * BURST + OW


def lost(i, t):
    f = 0.62
    xa, ya = X(t + f * OW), yc(i) - f * RH
    out.append(r'\draw[lostmsg] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(t), yc(i), xa, ya))
    out.append(r'\draw[cross] (%.3f,%.3f) -- (%.3f,%.3f) (%.3f,%.3f) -- (%.3f,%.3f);' % (xa - 0.5, ya - 0.5, xa + 0.5, ya + 0.5, xa - 0.5, ya + 0.5, xa + 0.5, ya - 0.5))
    return xa, ya


def done(i, t, label, anchor='south'):
    out.append(r'\draw[donetick] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(t), yc(i) - 1.0, X(t), yc(i) + 1.0))
    out.append(r'\node[sml,anchor=%s] at (%.3f,%.3f) {%s};' % (anchor, X(t), yc(i) + 1.2, label))


def note(i, t, text, width):
    out.append(r'\node[sml,anchor=west,align=left,text width=%.1fmm,fill=white,inner sep=0.5pt] at (%.3f,%.3f) {\hyphenpenalty=10000\exhyphenpenalty=10000 %s};' % (width, X(t), yc(i) - RH / 2, text))


def label(i, text):
    out.append(r'\node[lab,anchor=west,align=left] at (0,%.3f) {%s};' % (yc(i) - RH / 2, text))


label(0, r'(a) $\delta=0$')
t_a = 2 * OW + 2 * BURST
end = t_a + OW + OW
rails(0, end + 4)
to_server(0, 0, 'Initial')
to_client(0, OW, 3, '3 packets')
to_server(0, t_a, 'ACK + HS')
to_client(0, t_a + OW, 1, '4th')
done(0, end, r'HCT $\approx$ 2 RTT')
note(0, 113, r"${W=1{,}280}$~B, so ${A(B)=3{,}840}$~B and three packets leave. The fourth waits until the client's Handshake (HS) packet lifts the 3$\times$ limit.", 62)

label(1, r'(b) $\delta=1$')
end = to_client(1, OW, NEED, '4 packets')
rails(1, end + 4)
to_server(1, 0, 'Initial')
done(1, end, r'HCT $\approx$ 1 RTT')
note(1, 72, r'${W+\delta=1{,}281}$~B. One more byte raises ${A(B)=\lceil 3B/P\rceil P}$ to $5{,}120$~B, so all four packets leave at once.', 72)

label(2, r'(c) $\delta=1$,' + '\\\\' + 'Initial lost')
end = PTO + OW + (NEED - 1) * BURST + OW
rails(2, end + 4)
xa, ya = lost(2, 0)
out.append(r'\node[sml,anchor=west,inner sep=0.3pt] at (%.3f,%.3f) {Initial lost};' % (xa + 1.2, ya))
to_server(2, PTO + 0.0, None)
to_server(2, PTO + BURST, None)
out.append(r'\node[sml,anchor=east,align=right,inner sep=0.3pt] at (%.3f,%.3f) {2 probes};' % (X(PTO + 2), yc(2) - 5.6))
to_client(2, PTO + OW, NEED, '4 packets')
out.append(r'\draw[brc] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(0), yc(2) + 0.5, X(PTO), yc(2) + 0.5))
out.append(r'\node[sml,anchor=south,fill=white,inner sep=0.4pt] at (%.3f,%.3f) {PTO wait, 200 ms};' % (X(PTO / 2), yc(2) + 1.75))
done(2, end, r'HCT $\approx$ PTO + RTT', 'south east')
note(2, 49, r'The client learns of the loss only when PTO \mbox{expires}, then quic-go sends two probes.', 50)

label(3, r'(d) $\delta=1$ + parity,' + '\\\\' + 'Initial lost')
t_d = PAR + OW
end = to_client(3, t_d, NEED, '4 packets')
rails(3, end + 4)
xa, ya = lost(3, 0)
to_server(3, PAR, 'parity', 'paritymsg', 'above')
out.append(r'\draw[rebuilt] (%.3f,%.3f) rectangle (%.3f,%.3f);' % (X(t_d) - 0.7, ys(3) - 0.7, X(t_d) + 0.7, ys(3) + 0.7))
done(3, end, r'HCT $\approx$ 1 RTT')
note(3, 72, r'The server rebuilds the Initial (square). Only the rebuilt ${W+\delta=1{,}281}$~B counts, not the parity, so ${A(B)=5{,}120}$~B.', 72)

y_axis = ys(3) - AX_GAP
grid = []
ticks = []
for t in range(0, 251, 50):
    grid.append(r'\draw[gridline] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(t), y_axis, X(t), yc(0) + 0.3))
    ticks.append(r'\draw[axisline] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(t), y_axis, X(t), y_axis + 0.9))
    ticks.append(r'\node[lab,anchor=north] at (%.3f,%.3f) {%d};' % (X(t), y_axis - 0.5, t))
ticks.append(r'\draw[axisline] (%.3f,%.3f) -- (%.3f,%.3f);' % (X(0), y_axis, X(TMAX), y_axis))
ticks.append(r"\node[lab,anchor=north] at (%.3f,%.3f) {Time since the client's first send (ms)};" % (X(TMAX / 2), y_axis - 3.9))

tex = r'''\documentclass[border={1.5mm 0.6mm}]{standalone}
\input{figstyle.tex}
\tikzset{
  rail/.style={line width=0.55pt,ink},
  msg/.style={line width=0.45pt,ink,-{Latex[length=2.6pt,width=1.7pt]}},
  msgplain/.style={line width=0.45pt,ink},
  lostmsg/.style={line width=0.45pt,ink,dash pattern=on 1.6pt off 1.1pt},
  paritymsg/.style={line width=0.55pt,steel,-{Latex[length=2.6pt,width=1.7pt]}},
  cross/.style={line width=0.6pt,ink},
  rebuilt/.style={line width=0.5pt,steel,fill=white},
  donetick/.style={line width=0.9pt,ink},
  brc/.style={decorate,decoration={brace,amplitude=2.6pt},line width=0.4pt,ink},
  gridline/.style={line width=0.3pt,lightgray},
  axisline/.style={line width=0.45pt,ink},
  lab/.style={font=\figsize,inner sep=0pt},
  sml/.style={font=\smallsize,inner sep=0pt},
}
\begin{document}
\figsize
\begin{tikzpicture}[x=1mm,y=1mm]
\path (0,0) rectangle (150,%H%);
%GRID%
%BODY%
%TICKS%
\pgfresetboundingbox
\path (0,0) rectangle (150,%H%);
\end{tikzpicture}
\end{document}
'''
tex = tex.replace('%H%', '%.2f' % H).replace('%GRID%', '\n'.join(grid)).replace('%BODY%', '\n'.join(out)).replace('%TICKS%', '\n'.join(ticks))
p = os.path.join(ROOT, 'fig1_timing.tex')
open(p, 'w', encoding='utf-8', newline='\n').write(tex)
print('height %.1f' % H)
sys.exit(0 if '--no-compile' in sys.argv[1:] or compile_tex(p) else 1)
