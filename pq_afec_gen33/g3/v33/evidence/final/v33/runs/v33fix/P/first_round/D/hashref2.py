import sys; sys.dont_write_bytecode=True; sys.stdout.reconfigure(encoding="utf-8")
import subprocess, re
from pathlib import Path
commits = open("commits.txt").read().split()
tok = re.compile(r"(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])")
def refs(text):
    toks = set(tok.findall(text))
    hit = set()
    for c in commits:
        for t in toks:
            if len(t) >= 7 and c.startswith(t):
                hit.add(c); break
    return hit
texts = {}
for p in [r"C:\dev\codex_handoff\v33\state\LOOP_STATE.json", r"C:\dev\codex_handoff\v33\state\JOURNAL.md", r"C:\dev\codex_handoff\v33\runs\MORNING_REPORT.md"]:
    texts[Path(p).name] = Path(p).read_text(encoding="utf-8", errors="replace")
texts["gen33 docs/*.md"] = "\n".join(Path(p).read_text(encoding="utf-8", errors="replace") for p in Path(r"C:\dev\pq_afec_gen33\docs").glob("*.md"))
out = subprocess.run(["git", "-C", r"C:\dev\pq_afec_gen33", "grep", "-h", "-o", "-I", "-E", "[0-9a-f]{7,40}", "HEAD", "--", "g3"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
texts["gen33 g3 (HEAD)"] = out
allhit = set()
for k, v in texts.items():
    h = refs(v); allhit |= h
    print(k, len(h))
print("any", len(allhit), "of", len(commits))
