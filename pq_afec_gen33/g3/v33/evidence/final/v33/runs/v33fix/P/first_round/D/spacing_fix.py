import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import re, json
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
H = "가-힣"
KEEP = ("버스트3",)
SPECIFIC = [
    ("2 Mbps와RTT200", "2 Mbps와 RTT200"),
    ("on2와off", "on2와 off"),
    ("아니다.100 kB", "아니다. 100 kB"),
    ("CV80 B·SH1220 B·기타150 B", "CV 80 B·SH 1220 B·기타 150 B"),
    ("ServerHello1220 B", "ServerHello 1220 B"),
    ("level9로", "level 9로"),
    ("proof512 B", "proof 512 B"),
    ("fallback8972 B", "fallback 8972 B"),
    ("1792통과·2건너뜀·historical32제외·하위4513통과다", "1792개 통과, 2개 건너뜀, historical 32개 제외, 하위 검사 4513개 통과다"),
    ("1792통과·2건너뜀·하위4513이며", "1792개 통과, 2개 건너뜀, 하위 검사 4513개이며"),
    ("18통과·6실패이며", "18개 통과·6개 실패이며"),
    ("1.214766,1.188659,1.114800,1.072777", "1.214766, 1.188659, 1.114800, 1.072777"),
    ("m1=1520회,m0=80회", "m1=1520회, m0=80회"),
    ("ms,m4=", "ms, m4="),
    ("ms,차이", "ms, 차이"),
    ("ms,블록", "ms, 블록"),
    ("Q-03,Q-04", "Q-03, Q-04"),
    ("R2,T7,X3", "R2, T7, X3"),
]
used = {a: 0 for a, _ in SPECIFIC}

def fix_segment(s):
    for a, b in SPECIFIC:
        if a in s:
            used[a] += s.count(a)
            s = s.replace(a, b)
    holders = {}
    for i, k in enumerate(KEEP):
        tok = f"\x00{i}\x00"
        holders[tok] = k
        s = s.replace(k, tok)
    s = re.sub(rf"([{H}])−([{H}])", r"\1 − \2", s)
    s = re.sub(rf"([{H}])\+(\S)", r"\1 + \2", s)
    s = re.sub(rf"([{H}])([0-9±−§])", r"\1 \2", s)
    for tok, k in holders.items():
        s = s.replace(tok, k)
    return s

def split_cells(line):
    cells, cur, i = [], "", 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur += line[i:i+2]; i += 2; continue
        if ch == "|":
            cells.append(cur); cur = ""; i += 1; continue
        cur += ch; i += 1
    cells.append(cur)
    return cells

def fix_outside_links(line):
    out, pos = [], 0
    for m in re.finditer(r"\]\(<[^>]*>\)|\]\([^)]*\)", line):
        out.append(fix_segment(line[pos:m.start()]))
        out.append(m.group())
        pos = m.end()
    out.append(fix_segment(line[pos:]))
    return "".join(out)

lines = text.split("\n")
in_corr = False
res = []
for line in lines:
    if line.startswith("| 항목 | 파일·행 | 현재 문장 발췌"):
        in_corr = True
        res.append(line); continue
    if not line.startswith("|"):
        in_corr = False
    if in_corr and not line.startswith("|---"):
        cells = split_cells(line)
        cells[1] = cells[1].replace(",", ", ")
        cells[4] = fix_outside_links(cells[4])
        cells[5] = fix_outside_links(cells[5])
        res.append("|".join(cells))
    else:
        res.append(fix_outside_links(line))
out = "\n".join(res)
open(dst, "w", encoding="utf-8", newline="\n").write(out)
print(json.dumps(used, ensure_ascii=False))
