import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from texbuild import compile_tex, ROOT

H = 42.6
YB, PITCH = 9.0, 6.5
YT = YB + 4 * PITCH
XL, XR = 25.0, 129.9
FL, FR = 43.0, 110.0
PW, PH, GAP, GGAP = 8.0, 4.8, 0.9, 2.8
GROUPS = [('par', 2, 'T'), ('org', 2, 'k'), ('par', 2, 'l')]

total = sum(n * PW + (n - 1) * GAP for _, n, _ in GROUPS) + (len(GROUPS) - 1) * GGAP
xmid = (FL + FR) / 2
x = xmid - total / 2
x0 = x
cells, spans = [], []
for kind, n, _ in GROUPS:
    start = x
    for i in range(n):
        cells.append(r'\draw[%s] (%.3f,%.3f) rectangle (%.3f,%.3f);' % (kind, x, YB - PH / 2, x + PW, YB + PH / 2))
        x += PW + GAP
    x -= GAP
    spans.append((start, x))
    x += GGAP
x1 = x - GGAP
yb = YB + PH / 2 + 0.6
braces = '\n'.join(r'\draw[brc] (%.3f,%.3f) -- (%.3f,%.3f);' % (a, yb, b, yb) for a, b in spans)
c = [(a + b) / 2 for a, b in spans]
yl = yb + 1.5
ynet = YB - PH / 2 - 1.6

labels = [
    (c[0], r'$T$ trailing parity', 'credit or rebuild'),
    (c[1], r'$k$ original Initials', 'ClientHello'),
    (c[2], r'$\ell$ lead parity', 'credit only'),
]
lab = []
for cx, a, b in labels:
    lab.append(r'\node[sml,anchor=base] at (%.3f,%.3f) {%s};' % (cx, yl + 3.1, a))
    lab.append(r'\node[sml,anchor=base] at (%.3f,%.3f) {%s};' % (cx, yl, b))

ys = [YB + i * PITCH for i in range(5)]
yr = [YB + i * (YT - YB) / 3 for i in range(4)]

tex = r'''\documentclass[border={1.5mm 0.6mm}]{standalone}
\input{figstyle.tex}
\tikzset{
  blk/.style={draw=ink,line width=0.45pt,fill=white,minimum height=5mm,inner sep=0pt,align=center,font=\figsize},
  bl/.style={blk,minimum width=33mm},
  br/.style={blk,minimum width=35mm},
  arr/.style={-{Latex[length=3pt,width=2pt]},line width=0.45pt,ink},
  grp/.style={draw=midgray,line width=0.4pt,dash pattern=on 2.4pt off 1.8pt},
  org/.style={draw=ink,line width=0.45pt,fill=white},
  par/.style={draw=ink,line width=0.45pt,preaction={fill=white},pattern=north east lines,pattern color=midgray},
  brc/.style={decorate,decoration={brace,amplitude=1.3pt},line width=0.4pt,ink},
  sml/.style={font=\smallsize,inner sep=0pt,align=center},
  lab/.style={font=\figsize,inner sep=0pt,align=center},
}
\begin{document}
\figsize
\begin{tikzpicture}[x=1mm,y=1mm]
\path (0,0) rectangle (150,%H%);
\draw[grp] (0.25,0.25) rectangle (%FL%,%TOPF%);
\draw[grp] (%FR%,0.25) rectangle (149.75,%TOPF%);
\node[lab] at (%XL%,2.6) {Client};
\node[lab] at (%XR%,2.6) {Server};
\node[bl] (dc) at (%XL%,%Y4%) {Destination cache};
\node[bl] (lp) at (%XL%,%Y3%) {Loss posterior};
\node[bl] (cm) at (%XL%,%Y2%) {Cost model $J(\delta,\ell,T)$};
\node[bl] (ac) at (%XL%,%Y1%) {Action $(\delta,\ell,T)$};
\node[bl] (pe) at (%XL%,%Y0%) {Pad to $W+\delta$, RS parity};
\draw[arr] (dc.south) -- (lp.north);
\draw[arr] (lp.south) -- (cm.north);
\draw[arr] (cm.south) -- (ac.north);
\draw[arr] (ac.south) -- (pe.north);
\draw[arr] (dc.west) -- (5.2,%Y4%) -- (5.2,%Y2%) -- (cm.west);
\node[sml,rotate=90] at (3.2,%Y3%) {$k$, $S$, min RTT};
\node[br] (dec) at (%XR%,%R0%) {FEC decoder, CRC check};
\node[br] (rb) at (%XR%,%R1%) {Received-byte count $B$};
\node[br] (gt) at (%XR%,%R2%) {Amplification gate $A(B)$};
\node[br] (tf) at (%XR%,%R3%) {Server flight packets};
\draw[arr] (dec.north) -- (rb.south);
\draw[arr] (rb.north) -- (gt.south);
\draw[arr] (gt.north) -- (tf.south);
\draw[arr] (pe.east) -- (dec.west);
\draw[arr] (tf.west) -- (dc.east);
%CELLS%
%BRACES%
%LAB%
\node[sml,anchor=north] at (%XM%,%YNET%) {netem, client to server: delay RTT/2, loss, rate};
\node[sml,anchor=north] at (%XM%,%YTL%) {netem, server to client: delay RTT/2};
\node[sml,anchor=south] at (%XM%,%YTU%) {client measures HCT, $k$, $S$, min RTT};
\pgfresetboundingbox
\path (0,0) rectangle (150,%H%);
\end{tikzpicture}
\end{document}
'''
rep = {
    '%H%': '%.2f' % H, '%TOPF%': '%.2f' % (H - 0.25), '%FL%': '%.2f' % FL, '%FR%': '%.2f' % FR,
    '%XL%': '%.2f' % XL, '%XR%': '%.2f' % XR, '%XM%': '%.3f' % xmid,
    '%Y0%': '%.3f' % ys[0], '%Y1%': '%.3f' % ys[1], '%Y2%': '%.3f' % ys[2], '%Y3%': '%.3f' % ys[3], '%Y4%': '%.3f' % ys[4],
    '%R0%': '%.3f' % yr[0], '%R1%': '%.3f' % yr[1], '%R2%': '%.3f' % yr[2], '%R3%': '%.3f' % yr[3],
    '%CELLS%': '\n'.join(cells), '%BRACES%': braces, '%LAB%': '\n'.join(lab),
    '%YNET%': '%.3f' % ynet, '%YTL%': '%.3f' % (YT - 0.8), '%YTU%': '%.3f' % (YT + 0.8),
}
for k, v in rep.items():
    tex = tex.replace(k, v)
p = os.path.join(ROOT, 'fig2_system.tex')
open(p, 'w', encoding='utf-8', newline='\n').write(tex)
sys.exit(0 if '--no-compile' in sys.argv[1:] or compile_tex(p) else 1)
