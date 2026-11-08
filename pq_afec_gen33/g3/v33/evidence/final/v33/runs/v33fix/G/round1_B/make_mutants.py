import sys
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import shutil
from pathlib import Path

S = Path(r"C:\Users\scien\AppData\Local\Temp\claude\C--Users-scien\98dad099-940c-4208-8359-61078035dc93\scratchpad\v33fix\B")
MINE = S / "src_mine"

MUTANTS = {
    "F1": ("qamp.go", "\tif r.version == fbVerFrozen {\n\t\tversion = fbVerFrozen\n\t}\n", ""),
    "F2": ("boundary.go", "\tif capacity {\n\t\ts.queueConnLogLocked(ca, \"lru\")\n\t} else {\n\t\ts.queueConnLogLocked(ca, \"expired\")\n\t}\n", ""),
    "F4": ("qamp.go", "RetransLayout: \"repeat_first\", FeedbackWait: time.Second", "RetransLayout: \"original_first\", FeedbackWait: time.Second"),
    "F5": ("qamp.go", "\t\t\tif extras.Kind == \"parity\" {\n\t\t\t\tc.ffParCRC = append(c.ffParCRC, crc32.ChecksumIEEE(pkt))\n\t\t\t}\n\t\t\tc.stats.DroppedPar++", "\t\t\tc.ffParCRC = append(c.ffParCRC, crc32.ChecksumIEEE(pkt))\n\t\t\tc.stats.DroppedPar++"),
    "BE6": ("qamp_preserved_test.go", "\tif os.Getenv(preserveTestArtifactsEnv) != \"1\" {\n\t\treturn t.TempDir()\n\t}\n", ""),
}

for name, (fname, old, new) in MUTANTS.items():
    out = S / f"mut_{name}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    src = (MINE / fname).read_text(encoding="utf-8")
    count = src.count(old)
    if count != 1:
        raise SystemExit(f"{name}: pattern count {count}")
    (out / fname).write_text(src.replace(old, new), encoding="utf-8", newline="\n")
    print(name, fname, "mutated")
