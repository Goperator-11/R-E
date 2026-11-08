import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import re, hashlib, json
a = open(sys.argv[1], encoding="utf-8").read()
b = open(sys.argv[2], encoding="utf-8").read()
num = re.compile(r"\d+(?:\.\d+)*")
ta, tb = num.findall(a), num.findall(b)
links = re.compile(r"\]\(<[^>]*>\)|\]\([^)]*\)")
def excerpts(t):
    out, on = [], False
    for line in t.split("\n"):
        if line.startswith("| 항목 | 파일·행 | 현재 문장 발췌"):
            on = True; continue
        if not line.startswith("|"):
            on = False
        if on and not line.startswith("|---"):
            cells, cur, i = [], "", 0
            while i < len(line):
                ch = line[i]
                if ch == "\\" and i + 1 < len(line):
                    cur += line[i:i+2]; i += 2; continue
                if ch == "|":
                    cells.append(cur); cur = ""; i += 1; continue
                cur += ch; i += 1
            cells.append(cur)
            out.append((cells[2], cells[3]))
    return out
res = {"number_tokens_before": len(ta), "number_tokens_after": len(tb), "number_token_lists_equal": ta == tb,
       "number_token_sha_before": hashlib.sha256("\n".join(ta).encode()).hexdigest()[:16],
       "number_token_sha_after": hashlib.sha256("\n".join(tb).encode()).hexdigest()[:16],
       "links_equal": links.findall(a) == links.findall(b), "links": len(links.findall(a)),
       "excerpt_and_path_cells_equal": excerpts(a) == excerpts(b), "excerpt_rows": len(excerpts(a)),
       "lines_before": a.count("\n"), "lines_after": b.count("\n"),
       "hangul_digit_before": len(re.findall(r"[가-힣][0-9]", a)), "hangul_digit_after": len(re.findall(r"[가-힣][0-9]", b))}
print(json.dumps(res, ensure_ascii=False, indent=1))
